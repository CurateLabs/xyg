"""Thin figure-to-Scene v12 compiler for the migrated core-mark subset.

Rust owns mapping, clipping, record semantics, SVG construction, and raster
display-list construction. This module only projects already-validated Figure
objects into the typed ABI and rejects features whose canonical Scene record
does not exist yet.
"""

from __future__ import annotations

import struct
from typing import Any

import numpy as np

from . import _native
from .marks import _SYMBOL_CODES

# Host mark kinds that lower to Scene Rect (kind 2). Geometry is already
# x0/y0/x1/y1 columns on the Trace; Scene does not recompute bar stacking.
_RECT_KINDS = frozenset({"bar", "column", "histogram", "violin", "box"})
# Endpoint pairs that lower to disconnected Scene Polyline runs (kind 1).
_SEGMENT_KINDS = frozenset({"segments", "errorbar", "stem", "contour", "box_whisker", "box_median"})
# Top/base samples that lower to Scene Band (kind 3) filled polygons.
_BAND_KINDS = frozenset({"area", "error_band"})
# Host-tessellated flow bands also lower to Scene Band samples.
_RIBBON_KINDS = frozenset({"ribbon"})
# Independent triangles lower to Scene PolyFill (kind 4) vertex runs.
_POLYFILL_KINDS = frozenset({"triangle_mesh"})
# Cartesian hexbin centers expand onto PolyFill records (6-vertex cells) in
# Rust (`SceneExpansionMode::HexCell`). Hosts pack one compact center+pitch
# row per cell.
_HEXBIN_KINDS = frozenset({"hexbin"})
_HEXBIN_REDUCES = frozenset({"count", "mean", "sum"})
# Regular Cartesian heatmap cells expand onto Rect records in Rust
# (`SceneExpansionMode::HeatmapLattice`). Hosts pack extent plus rows/cols.
_HEATMAP_KINDS = frozenset({"heatmap"})
_POINT_KINDS = frozenset({"scatter", "line"})
_SUPPORTED_KINDS = (
    _POINT_KINDS
    | _RECT_KINDS
    | _SEGMENT_KINDS
    | _BAND_KINDS
    | _RIBBON_KINDS
    | _POLYFILL_KINDS
    | _HEXBIN_KINDS
    | _HEATMAP_KINDS
)
_STROKE_KINDS = frozenset({"line"}) | _SEGMENT_KINDS

# Each unjoined triangle or hex cell is one PolyFill group in the Rust browser
# painter. Keep the public route inside its canonical group budget; larger
# meshes and honeycombs remain on the compatibility path until Scene gains a
# compact multi-cell painter record.
_MAX_PUBLIC_TRIANGLE_MESHES = 1024
# Regular heatmap cells are ordinary Rect records and share the histogram
# 10,000-bin public ceiling. Colormap, polar, truecolor, and irregular grids
# stay on the compatibility exporters.
_MAX_PUBLIC_HEATMAP_CELLS = 10_000

_PUBLIC_EXPORT_KIND_CODES = {
    "scatter": 0,
    "line": 1,
    "bar": 2,
    "column": 3,
    "histogram": 4,
    "violin": 5,
    "box": 6,
    "box_whisker": 7,
    "box_median": 8,
    "segments": 9,
    "errorbar": 10,
    "stem": 11,
    "area": 12,
    "error_band": 13,
    "ribbon": 14,
    "triangle_mesh": 15,
    "hexbin": 16,
    "heatmap": 17,
}

_LEGEND_LOCATIONS = {
    "upper right": 0,
    "upper left": 1,
    "lower left": 2,
    "lower right": 3,
    "center right": 4,
    "center left": 5,
    "upper center": 6,
    "lower center": 7,
    "center": 8,
}


def _colorbar_input(figure: Any) -> bytes:
    """Frame only the small literal XYCB subset; Rust resolves all policy."""
    options = getattr(figure, "colorbar_options", None)
    if not options:
        return b""
    if not isinstance(options, dict) or set(options) - {
        "domain",
        "stops",
        "side",
        "title",
        "text_rgba",
        "ticks",
        "minor_ticks",
    }:
        raise UnsupportedSceneV3("Scene v19 colorbars require literal bounded RGBA stops")
    domain = options.get("domain")
    stops = options.get("stops")
    if not (
        isinstance(domain, (list, tuple))
        and len(domain) == 2
        and isinstance(stops, (list, tuple))
        and 2 <= len(stops) <= 16
    ):
        raise UnsupportedSceneV3(
            "Scene v19 colorbars require a two-value domain and 2-16 literal stops"
        )
    try:
        lo, hi = (float(domain[0]), float(domain[1]))
        parsed = [(float(item[0]), bytes(item[1])) for item in stops]
    except (TypeError, ValueError, IndexError):
        raise UnsupportedSceneV3(
            "Scene v19 colorbar stops are (finite value, RGBA[4]) pairs"
        ) from None
    if any(len(rgba) != 4 for _, rgba in parsed):
        raise UnsupportedSceneV3(
            "Scene v19 colorbar values must be finite and RGBA literals exactly four bytes"
        )
    horizontal = options.get("side", "right") == "bottom"
    if options.get("side", "right") not in {"right", "bottom"}:
        raise UnsupportedSceneV3("Scene v19 colorbars support only right or bottom placement")
    title = options.get("title", "")
    if not isinstance(title, str):
        raise UnsupportedSceneV3("Scene v19 colorbar title must be a string")
    title_b = title.encode("utf-8")
    try:
        text_rgba = bytes(options.get("text_rgba", (32, 32, 32, 255)))
    except (TypeError, ValueError):
        raise UnsupportedSceneV3(
            "Scene v19 colorbar text is bounded and uses literal RGBA"
        ) from None
    if len(title_b) > 4096 or len(text_rgba) != 4:
        raise UnsupportedSceneV3("Scene v19 colorbar text is bounded and uses literal RGBA")
    raw_ticks = options.get("ticks")
    if raw_ticks is None:
        ticks: list[float] = []
    elif not isinstance(raw_ticks, (list, tuple)) or len(raw_ticks) > 32:
        raise UnsupportedSceneV3("Scene v19 colorbar ticks are limited to 32 finite ordered values")
    else:
        try:
            ticks = [float(value) for value in raw_ticks]
        except (TypeError, ValueError):
            raise UnsupportedSceneV3(
                "Scene v19 colorbar ticks are limited to 32 finite ordered values"
            ) from None
    minor_ticks = options.get("minor_ticks", False)
    if not isinstance(minor_ticks, bool):
        raise UnsupportedSceneV3("Scene v19 colorbar minor_ticks must be a boolean")
    flags = int(horizontal) | (int(minor_ticks) << 2)
    stop_rgba = b"".join(rgba for _, rgba in parsed)
    try:
        return _native.scene_pack_colorbar(
            flags=flags,
            lo=lo,
            hi=hi,
            text_rgba=text_rgba,
            title=title_b,
            stop_values=[value for value, _ in parsed],
            stop_rgba=stop_rgba,
            ticks=ticks,
        )
    except ValueError as error:
        raise UnsupportedSceneV3(str(error)) from error


_ANNOTATION_FLAG_FILL = 1
_ANNOTATION_FLAG_BORDER = 2


def _annotation_style_flags(
    fill: tuple[int, int, int, int] | None,
    border: tuple[tuple[int, int, int, int], float] | None,
) -> int:
    flags = 0
    if fill is not None:
        flags |= _ANNOTATION_FLAG_FILL
    if border is not None:
        flags |= _ANNOTATION_FLAG_BORDER
    return flags


def _annotation_envelope(
    text_rows: list[
        tuple[
            float,
            float,
            tuple[int, int, int, int],
            tuple[int, int, int, int] | None,
            tuple[tuple[int, int, int, int], float] | None,
            bytes,
        ]
    ],
    attached_labels: list[
        tuple[
            int,
            tuple[int, int, int, int],
            tuple[int, int, int, int] | None,
            tuple[tuple[int, int, int, int], float] | None,
            str,
        ]
    ],
    straight_arrows: list[
        tuple[int, float, float, float, float, tuple[int, int, int, int], float, float]
    ],
    cartesian_callouts: list[
        tuple[
            float,
            float,
            float,
            float,
            tuple[int, int, int, int],
            float,
            float,
            int,
            bytes,
            tuple[int, int, int, int] | None,
            tuple[tuple[int, int, int, int], float] | None,
        ]
    ],
    wrapped_rows: list[
        tuple[
            float,
            float,
            float,
            float,
            float,
            tuple[int, int, int, int],
            tuple[int, int, int, int],
            tuple[int, int, int, int],
            float,
            int,
            int,
            bytes,
        ]
    ],
) -> bytes:
    """Frame collected annotation rows as XYAD bytes through Rust."""
    if not (text_rows or attached_labels or straight_arrows or cartesian_callouts or wrapped_rows):
        return b""
    zeros = (0, 0, 0, 0)

    def pack_fill(fill: tuple[int, int, int, int] | None) -> bytes:
        return bytes(fill or zeros)

    def pack_border(
        border: tuple[tuple[int, int, int, int], float] | None,
    ) -> tuple[bytes, float]:
        if border is None:
            return bytes(zeros), 0.0
        return bytes(border[0]), float(border[1])

    text_meta = bytearray()
    text_lens: list[int] = []
    texts = bytearray()
    for x, y, rgba, fill, border, encoded in text_rows:
        border_rgba, width = pack_border(border)
        text_meta.extend(
            struct.pack(
                "<dd4s4s4sdB3x",
                x,
                y,
                bytes(rgba),
                pack_fill(fill),
                border_rgba,
                width,
                _annotation_style_flags(fill, border),
            )
        )
        text_lens.append(len(encoded))
        texts.extend(encoded)
    attached_meta = bytearray()
    attached_lens: list[int] = []
    attached_texts = bytearray()
    for stable_id, rgba, fill, border, value in attached_labels:
        encoded = value.encode("utf-8")
        border_rgba, width = pack_border(border)
        attached_meta.extend(
            struct.pack(
                "<Q4s4s4sdB3x",
                int(stable_id),
                bytes(rgba),
                pack_fill(fill),
                border_rgba,
                width,
                _annotation_style_flags(fill, border),
            )
        )
        attached_lens.append(len(encoded))
        attached_texts.extend(encoded)
    arrow_meta = bytearray()
    for stable_id, x0, y0, x1, y1, rgba, opacity, width in straight_arrows:
        arrow_meta.extend(
            struct.pack("<Qdddd4sdd", int(stable_id), x0, y0, x1, y1, bytes(rgba), opacity, width)
        )
    callout_meta = bytearray()
    callout_lens: list[int] = []
    callout_texts = bytearray()
    for (
        x,
        y,
        dx,
        dy,
        rgba,
        opacity,
        width,
        anchor_code,
        encoded,
        fill,
        border,
    ) in cartesian_callouts:
        border_rgba, border_width = pack_border(border)
        callout_meta.extend(
            struct.pack(
                "<dddd4sddB3x4s4sdB3x",
                x,
                y,
                dx,
                dy,
                bytes(rgba),
                opacity,
                width,
                anchor_code,
                pack_fill(fill),
                border_rgba,
                border_width,
                _annotation_style_flags(fill, border),
            )
        )
        callout_lens.append(len(encoded))
        callout_texts.extend(encoded)
    wrapped_meta = bytearray()
    wrapped_lens: list[int] = []
    wrapped_texts = bytearray()
    for x, y, dx, dy, wrap, rgba, fill, border_rgba, border, kind, anchor, encoded in wrapped_rows:
        wrapped_meta.extend(
            struct.pack(
                "<ddddd4s4s4sdBB2x",
                x,
                y,
                dx,
                dy,
                wrap,
                bytes(rgba),
                bytes(fill),
                bytes(border_rgba),
                border,
                kind,
                anchor,
            )
        )
        wrapped_lens.append(len(encoded))
        wrapped_texts.extend(encoded)
    try:
        return _native.scene_pack_annotations(
            text_meta=bytes(text_meta),
            text_lens=text_lens,
            texts=bytes(texts),
            attached_meta=bytes(attached_meta),
            attached_lens=attached_lens,
            attached_texts=bytes(attached_texts),
            arrow_meta=bytes(arrow_meta),
            callout_meta=bytes(callout_meta),
            callout_lens=callout_lens,
            callout_texts=bytes(callout_texts),
            wrapped_meta=bytes(wrapped_meta),
            wrapped_lens=wrapped_lens,
            wrapped_texts=bytes(wrapped_texts),
        )
    except ValueError as error:
        raise UnsupportedSceneV3(str(error)) from error


def _legend_input(
    figure: Any, entries: list[tuple[int, int, int, str]], styles: list[Any]
) -> bytes:
    if not figure.show_legend or not entries:
        return b""
    options = dict(figure.legend_options or {})
    unsupported = {
        key
        for key in options
        if key not in {"loc", "title", "ncols", "style", "highlight", "toggle"}
    }
    if unsupported or int(options.get("ncols") or 1) != 1:
        raise UnsupportedSceneV3(
            "Scene v12 primary legends do not yet encode anchors, multiple columns, or custom content"
        )
    if any(key in options and options[key] is not False for key in ("toggle", "highlight")):
        raise UnsupportedSceneV3(
            "Scene v12 primary legends are static; toggle and highlight must be false"
        )
    authored_loc = options.get("loc")
    loc = "upper right" if authored_loc is None else str(authored_loc)
    if loc not in _LEGEND_LOCATIONS:
        raise UnsupportedSceneV3(f"Scene v12 does not support legend location {loc!r}")
    style = dict(options.get("style") or {})
    unsupported_style = set(style) - {"background", "color", "font_size", "title_font_size"}
    if unsupported_style:
        raise UnsupportedSceneV3(
            "Scene v12 legends support only background, color, font_size, and title_font_size"
        )
    authored_font_size = style.get("font_size")
    authored_title_font_size = style.get("title_font_size")
    font_size = 0.0 if authored_font_size is None else float(authored_font_size)
    title_font_size = 0.0 if authored_title_font_size is None else float(authored_title_font_size)
    if not (
        (authored_font_size is None or 1.0 <= font_size <= 1000.0)
        and (authored_title_font_size is None or 1.0 <= title_font_size <= 1000.0)
    ):
        raise ValueError("legend font sizes must be finite and in [1, 1000]")
    title_value = options.get("title")
    if isinstance(title_value, bool):
        title_value = str(title_value).lower()
    title = str("" if title_value is None else title_value).encode("utf-8")
    labels = [label.encode("utf-8") for _, _, _, label in entries]
    if len(entries) > 128 or any(not label or len(label) > 4096 for label in labels):
        raise ValueError("Scene v12 legends are limited to 128 nonempty 4096-byte labels")
    text_bytes = len(title) + sum(map(len, labels))
    if text_bytes > _native.MAX_SCENE_LEGEND_INPUT_BYTES - 48 - 128 * 24 or len(title) > 4096:
        raise ValueError("Scene v12 legend text is limited to 16,384 UTF-8 bytes")
    flags = (
        int(authored_loc is not None)
        | (int(authored_font_size is not None) << 1)
        | (int(authored_title_font_size is not None) << 2)
        | (int("color" in style) << 3)
        | (int("background" in style) << 4)
    )
    text_rgba = bytes(_rgba(str(style["color"]), 1.0)) if "color" in style else bytes(4)
    frame_fill = bytes(_rgba(str(style["background"]), 1.0)) if "background" in style else bytes(4)
    meta = bytearray()
    blob = bytearray()
    label_lens: list[int] = []
    for (style_ref, kind, symbol, _), label in zip(entries, labels, strict=True):
        fill, stroke, _ = styles[style_ref]
        meta.extend(struct.pack("<IBB2x", int(style_ref), int(kind), int(symbol)))
        meta.extend(bytes(fill))
        meta.extend(bytes(stroke))
        label_lens.append(len(label))
        blob.extend(label)
    return _native.scene_pack_legend(
        loc=_LEGEND_LOCATIONS[loc],
        flags=flags,
        font_size=font_size,
        title_font_size=title_font_size,
        text_rgba=text_rgba,
        frame_fill_rgba=frame_fill,
        title=title,
        entry_meta=bytes(meta),
        label_lens=label_lens,
        labels=bytes(blob),
    )


_KIND_CODES = {
    "scatter": 0,
    "line": 1,
    "segments": 1,
    "errorbar": 1,
    "stem": 1,
    "contour": 1,
    "box_whisker": 1,
    "box_median": 1,
    "bar": 2,
    "column": 2,
    "histogram": 2,
    "violin": 2,
    "box": 2,
    "area": 3,
    "error_band": 3,
    "ribbon": 3,
    "triangle_mesh": 4,
    "hexbin": 4,
    "heatmap": 2,
}


class UnsupportedSceneV3(ValueError):
    """The figure uses a feature outside the currently migrated Scene subset."""


def _append_packed(
    kinds: list[int],
    stable_ids: list[int],
    style_refs: list[int],
    diameters: list[float],
    symbols: list[int],
    expansion_modes: list[int],
    coordinates: list[list[float]],
    pack_kind: int,
    columns: list[Any],
    **kwargs: Any,
) -> None:
    """Append Rust-packed Scene rows for one trace's geometry columns."""
    try:
        (
            packed_kinds,
            packed_ids,
            packed_refs,
            packed_diameters,
            packed_symbols,
            packed_modes,
            coords,
        ) = _native.scene_pack_trace(pack_kind, columns, **kwargs)
    except ValueError as error:
        raise UnsupportedSceneV3(str(error)) from error
    kinds.extend(int(value) for value in packed_kinds)
    stable_ids.extend(int(value) for value in packed_ids)
    style_refs.extend(int(value) for value in packed_refs)
    diameters.extend(float(value) for value in packed_diameters)
    symbols.extend(int(value) for value in packed_symbols)
    expansion_modes.extend(int(value) for value in packed_modes)
    for axis in range(4):
        coordinates[axis].extend(float(value) for value in coords[axis])


def _rgba(css: str, opacity: float) -> tuple[int, int, int, int]:
    return _native.css_color_rgba(css, opacity)


_STYLE_KIND_CODES = {
    **_PUBLIC_EXPORT_KIND_CODES,
    "contour": 18,
}
_MS_LINE_ONLY = 1 << 0
_MS_HAS_FILL = 1 << 1
_MS_HAS_STROKE = 1 << 2
_MS_HAS_LINE_COLOR = 1 << 3
_MS_HAS_STROKE_WIDTH = 1 << 5
_MS_HAS_WIDTH = 1 << 6
_MS_HAS_LINE_WIDTH = 1 << 7


def _pack_mark_style_record(
    trace: Any,
    opacity: float,
    fill_opacity: float,
    stroke_opacity: float,
    line_opacity: float,
    symbol_name: str,
) -> bytes:
    style = trace.style
    flags = 0
    if trace.kind == "scatter" and _SYMBOL_CODES[symbol_name] >= _SYMBOL_CODES["plus_line"]:
        flags |= _MS_LINE_ONLY
    fill_b = b""
    if "fill" in style:
        fill_value = style["fill"]
        if not isinstance(fill_value, str):
            raise UnsupportedSceneV3(f"Scene v12 does not yet encode {trace.kind} non-CSS fills")
        flags |= _MS_HAS_FILL
        fill_b = fill_value.encode("utf-8")
    stroke_b = b""
    if "stroke" in style:
        flags |= _MS_HAS_STROKE
        stroke_b = str(style["stroke"]).encode("utf-8")
    line_color_b = b""
    if "line_color" in style:
        flags |= _MS_HAS_LINE_COLOR
        line_color_b = str(style["line_color"]).encode("utf-8")
    color_b = _constant_color(trace, "#3987e5").encode("utf-8")
    stroke_width = width = line_width = 0.0
    if "stroke_width" in style:
        flags |= _MS_HAS_STROKE_WIDTH
        stroke_width = float(style["stroke_width"])
    if "width" in style:
        flags |= _MS_HAS_WIDTH
        width = float(style["width"])
    if "line_width" in style:
        flags |= _MS_HAS_LINE_WIDTH
        line_width = float(style["line_width"])
    prefix = struct.pack(
        "<BBH4f3d4H",
        _STYLE_KIND_CODES.get(trace.kind, 255),
        flags,
        0,
        float(opacity),
        float(fill_opacity),
        float(stroke_opacity),
        float(line_opacity),
        float(stroke_width),
        float(width),
        float(line_width),
        len(fill_b),
        len(stroke_b),
        len(line_color_b),
        len(color_b),
    )
    return prefix + fill_b + stroke_b + line_color_b + color_b


def _resolve_mark_style(
    trace: Any,
    opacity: float,
    fill_opacity: float,
    stroke_opacity: float,
    line_opacity: float,
    symbol_name: str,
) -> tuple[tuple[int, int, int, int], tuple[int, int, int, int], float]:
    record = _pack_mark_style_record(
        trace, opacity, fill_opacity, stroke_opacity, line_opacity, symbol_name
    )
    header = struct.pack("<4sIII", b"XYMS", 1, 1, 0)
    return _native.scene_resolve_mark_styles(header + record)[0]


def _constant_color(trace: Any, fallback: str) -> str:
    channel = trace.color_ch
    if getattr(trace, "color2_ch", None) is not None:
        raise UnsupportedSceneV3("Scene v12 does not yet encode two-ended ribbon gradients")
    if channel is None:
        return str(trace.style.get("color", fallback))
    if channel.mode != "constant" or channel.constant is None:
        raise UnsupportedSceneV3("Scene v12 does not yet support data-driven paint channels")
    return channel.constant


_SCENE_AXIS_STYLE_KEYS = frozenset(
    {
        "grid_color",
        "grid_width",
        "grid_opacity",
        "axis_color",
        "axis_width",
        "tick_color",
        "tick_width",
        "tick_length",
        "tick_direction",
        "tick_label_color",
        "label_color",
    }
)

_CH_HAS_CHART_BG = 1 << 0
_CH_HAS_PLOT_BG = 1 << 1
_CH_PAINT_AXIS = 1 << 0
_CH_PAINT_GRID = 1 << 1
_CH_PAINT_TICK = 1 << 2
_CH_PAINT_MINOR_GRID = 1 << 3
_CH_PAINT_MINOR_TICK = 1 << 4
_CH_PAINT_LABEL = 1 << 5
_CH_WIDTH_AXIS = 1 << 0
_CH_WIDTH_GRID = 1 << 1
_CH_WIDTH_TICK = 1 << 2
_CH_WIDTH_TICK_LENGTH = 1 << 3
_CH_WIDTH_MINOR_GRID = 1 << 4
_CH_WIDTH_MINOR_TICK = 1 << 5
_CH_WIDTH_MINOR_TICK_LENGTH = 1 << 6
_CH_DEFAULT_PAINTS = (
    "#202020",
    "#202020",
    "#202020",
    "transparent",
    "#202020",
    "#202020",
)
_CH_DEFAULT_WIDTHS = (1.0, 1.0, 1.0, 4.0, 1.0, 1.0, 0.0)


def _scene_side_mask(
    values: Any,
    name: str,
    axis_id: str,
    allowed: tuple[str, str],
    side_code: int,
) -> int:
    if values is None:
        return 1 << side_code
    if any(value not in allowed for value in values):
        raise UnsupportedSceneV3(
            f"Scene v12 {axis_id} axis {name} must contain only {list(allowed)!r}"
        )
    return sum(1 << index for index, candidate in enumerate(allowed) if candidate in values)


def _pack_chrome_axis(axis_id: str, options: dict[str, Any]) -> bytes:
    style = dict(options.get("style") or {})
    minor = dict(options.get("minor_style") or {})
    for label, authored in (("style", style), ("minor_style", minor)):
        unsupported = set(authored) - _SCENE_AXIS_STYLE_KEYS
        if unsupported:
            raise UnsupportedSceneV3(
                f"Scene v12 does not yet encode {axis_id} axis {label} keys {sorted(unsupported)!r}"
            )
    side = options.get("side", "bottom" if axis_id == "x" else "left")
    allowed = ("bottom", "top") if axis_id == "x" else ("left", "right")
    if side not in allowed:
        raise UnsupportedSceneV3(f"Scene v12 {axis_id} axis side must be one of {list(allowed)!r}")
    side_code = 0 if side in {"bottom", "left"} else 1
    tick_sides = options.get("tick_sides")
    label_sides = options.get("tick_label_sides")
    directions = {"out": 0, "in": 1, "inout": 2}
    paint_flags = 0
    if "axis_color" in style:
        paint_flags |= _CH_PAINT_AXIS
    if "grid_color" in style:
        paint_flags |= _CH_PAINT_GRID
    if "tick_color" in style:
        paint_flags |= _CH_PAINT_TICK
    if "grid_color" in minor:
        paint_flags |= _CH_PAINT_MINOR_GRID
    if "tick_color" in minor:
        paint_flags |= _CH_PAINT_MINOR_TICK
    if "tick_label_color" in style or "label_color" in style:
        paint_flags |= _CH_PAINT_LABEL
    width_flags = 0
    width_keys = (
        ("axis_width", style, _CH_WIDTH_AXIS),
        ("grid_width", style, _CH_WIDTH_GRID),
        ("tick_width", style, _CH_WIDTH_TICK),
        ("tick_length", style, _CH_WIDTH_TICK_LENGTH),
        ("grid_width", minor, _CH_WIDTH_MINOR_GRID),
        ("tick_width", minor, _CH_WIDTH_MINOR_TICK),
        ("tick_length", minor, _CH_WIDTH_MINOR_TICK_LENGTH),
    )
    widths = []
    for key, source, flag in width_keys:
        if key in source:
            width_flags |= flag
            widths.append(float(source[key]))
        else:
            widths.append(_CH_DEFAULT_WIDTHS[len(widths)])
    paints = (
        str(style.get("axis_color", _CH_DEFAULT_PAINTS[0])),
        str(style.get("grid_color", _CH_DEFAULT_PAINTS[1])),
        str(style.get("tick_color", _CH_DEFAULT_PAINTS[2])),
        str(minor.get("grid_color", _CH_DEFAULT_PAINTS[3])),
        str(minor.get("tick_color", _CH_DEFAULT_PAINTS[4])),
        str(style.get("tick_label_color", style.get("label_color", _CH_DEFAULT_PAINTS[5]))),
    )
    paint_bytes = [value.encode("utf-8") for value in paints]
    prefix = struct.pack(
        "<8B2f7d6H",
        side_code,
        _scene_side_mask(tick_sides, "tick_sides", axis_id, allowed, side_code),
        _scene_side_mask(label_sides, "tick_label_sides", axis_id, allowed, side_code),
        directions.get(str(style.get("tick_direction", "out")), 255),
        directions.get(str(minor.get("tick_direction", "out")), 255),
        paint_flags,
        width_flags,
        0,
        float(style.get("grid_opacity", 1.0)),
        float(minor.get("grid_opacity", 1.0)),
        *widths,
        *[len(value) for value in paint_bytes],
    )
    return prefix + b"".join(paint_bytes)


def _scene_chrome_style(figure: Any) -> bytes:
    """Pack authored chrome literals; Rust owns the 200-byte Scene style."""
    figure_style = getattr(figure, "style", None) or {}
    flags = 2 << 8
    chart_b = b""
    plot_b = b""
    if "background" in figure_style:
        flags |= _CH_HAS_CHART_BG
        chart_b = str(figure_style.get("background") or "transparent").encode("utf-8")
    if "--chart-bg" in figure_style:
        flags |= _CH_HAS_PLOT_BG
        plot_b = str(figure_style.get("--chart-bg") or "transparent").encode("utf-8")
    x_rec = _pack_chrome_axis("x", figure.axis_options["x"])
    y_rec = _pack_chrome_axis("y", figure.axis_options["y"])
    header = struct.pack("<4sIIHH", b"XYCH", 1, flags, len(chart_b), len(plot_b))
    return _native.scene_resolve_chrome_style(header + chart_b + plot_b + x_rec + y_rec)


def _reject_rect_extras(style: dict[str, Any], kind: str) -> None:
    fill = style.get("fill")
    if isinstance(fill, dict):
        raise UnsupportedSceneV3(f"Scene v12 does not yet encode {kind} gradient fills")
    radius = style.get("corner_radius", 0.0)
    if isinstance(radius, (list, tuple)):
        if any(float(value) != 0.0 for value in radius):
            raise UnsupportedSceneV3(f"Scene v12 does not yet encode {kind} corner_radius")
    elif float(radius) != 0.0:
        raise UnsupportedSceneV3(f"Scene v12 does not yet encode {kind} corner_radius")
    if float(style.get("wedge_gap", 0.0) or 0.0) != 0.0:
        raise UnsupportedSceneV3(f"Scene v12 does not yet encode {kind} wedge_gap")


def _rect_columns(trace: Any) -> list[np.ndarray]:
    if any(value is None for value in (trace.x0, trace.y0, trace.x1, trace.y1)):
        raise ValueError(f"{trace.kind} Scene v12 compilation requires four rectangle columns")
    arrays = [trace.x0.values, trace.y0.values, trace.x1.values, trace.y1.values]
    lengths = {len(column) for column in arrays}
    if len(lengths) != 1:
        raise UnsupportedSceneV3(f"Scene v12 {trace.kind} rectangle columns must have equal length")
    return arrays


def _segment_columns(trace: Any) -> list[np.ndarray]:
    if any(value is None for value in (trace.x0, trace.y0, trace.x1, trace.y1)):
        raise ValueError(f"{trace.kind} Scene v12 compilation requires four endpoint columns")
    arrays = [trace.x0.values, trace.y0.values, trace.x1.values, trace.y1.values]
    lengths = {len(column) for column in arrays}
    if len(lengths) != 1:
        raise UnsupportedSceneV3(f"Scene v12 {trace.kind} endpoint columns must have equal length")
    return arrays


def _hexbin_pitch(style: dict[str, Any]) -> tuple[float, float]:
    """Return the finite data-space hex cell pitch, or fail closed."""
    raw_dx = style.get("hex_dx", style.get("dx"))
    raw_dy = style.get("hex_dy", style.get("dy"))
    if raw_dx is None or raw_dy is None:
        raise UnsupportedSceneV3("Scene v12 hexbin requires finite hex_dx/hex_dy cell pitch")
    dx = float(raw_dx)
    dy = float(raw_dy)
    if not np.isfinite(dx) or not np.isfinite(dy) or dx <= 0.0 or dy <= 0.0:
        raise UnsupportedSceneV3("Scene v12 hexbin requires finite hex_dx/hex_dy cell pitch")
    return dx, dy


def _heatmap_uses_colormap(trace: Any) -> bool:
    """Return whether a heatmap still needs the compatibility colormap path."""
    style = getattr(trace, "style", None) or {}
    return bool(
        style.get("truecolor")
        or style.get("colormap") is not None
        or getattr(trace, "rgba_grid", None) is not None
        or getattr(trace, "rgba", None) is not None
    )


def _heatmap_shape(trace: Any) -> tuple[int, int]:
    """Return the finite rows x cols lattice, or fail closed."""
    shape = getattr(trace, "grid_shape", None)
    if shape is None or len(shape) != 2:
        raise UnsupportedSceneV3("Scene v12 heatmap requires a rows x cols grid_shape")
    rows, cols = int(shape[0]), int(shape[1])
    if rows < 1 or cols < 1:
        raise UnsupportedSceneV3("Scene v12 heatmap requires a positive grid_shape")
    return rows, cols


def _heatmap_grid_values(trace: Any) -> np.ndarray:
    """Return the authored scalar grid as a flat finite-checkable column."""
    grid = getattr(trace, "grid", None)
    if grid is None:
        raise ValueError("heatmap Scene v12 compilation requires a scalar grid")
    return np.asarray(getattr(grid, "values", grid), dtype=np.float64)


def _heatmap_extent(trace: Any) -> tuple[float, float, float, float]:
    """Return the finite increasing cell rectangle covered by the grid."""
    if trace.x is None or trace.y is None:
        raise ValueError("heatmap Scene v12 compilation requires range columns")
    xv = np.asarray(getattr(trace.x, "values", trace.x), dtype=np.float64)
    yv = np.asarray(getattr(trace.y, "values", trace.y), dtype=np.float64)
    if len(xv) != 2 or len(yv) != 2:
        raise UnsupportedSceneV3("Scene v12 heatmap range columns must be two endpoints")
    x0, x1 = float(xv[0]), float(xv[1])
    y0, y1 = float(yv[0]), float(yv[1])
    if not np.isfinite([x0, x1, y0, y1]).all() or x0 >= x1 or y0 >= y1:
        raise UnsupportedSceneV3("Scene v12 heatmap requires a finite increasing cell extent")
    return x0, x1, y0, y1


def _band_columns(trace: Any) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    if trace.x is None or trace.y is None or trace.base is None:
        raise ValueError(f"{trace.kind} Scene v12 compilation requires x, y, and base columns")
    xv = np.asarray(trace.x.values, dtype=np.float64)
    yv = np.asarray(trace.y.values, dtype=np.float64)
    base = np.asarray(trace.base.values, dtype=np.float64)
    if not (len(xv) == len(yv) == len(base)):
        raise UnsupportedSceneV3(f"Scene v12 {trace.kind} band columns must have equal length")
    return xv, yv, base


def figure_scene(
    figure: Any,
    *,
    width: int | None = None,
    height: int | None = None,
    margins: tuple[float, float, float, float] | None = None,
) -> bytes:
    """Compile migrated cartesian marks plus x/y axes to Scene v12."""
    annotations = list(getattr(figure, "annotations", None) or [])
    features = 0
    if figure.coords != "cartesian":
        features |= 1 << 0
    chrome_styles = getattr(figure, "chrome_styles", None) or {}
    if any("font-family" in (style or {}) for style in chrome_styles.values()):
        features |= 1 << 1
    if (
        getattr(figure, "class_name", None)
        or getattr(figure, "class_names", None)
        or chrome_styles
        or set(getattr(figure, "style", None) or {}) - {"background", "--chart-bg"}
        or any(annotation.get("class_name") not in (None, "") for annotation in annotations)
    ):
        features |= 1 << 2
    if any(
        isinstance((getattr(trace, "style", None) or {}).get("fill"), dict)
        or getattr(trace, "color2_ch", None) is not None
        or (
            getattr(trace, "color_ch", None) is not None
            and (trace.color_ch.mode != "constant" or trace.color_ch.constant is None)
        )
        for trace in figure.traces
    ):
        features |= 1 << 3
    try:
        colorbar_input = _colorbar_input(figure)
    except UnsupportedSceneV3:
        colorbar_input = b""
        features |= 1 << 4
    if figure.extra_legends:
        features |= 1 << 5
    if any(
        annotation.get("kind") not in {"callout", "arrow", "text"}
        and annotation.get("text") not in (None, "")
        for annotation in annotations
    ):
        features |= 1 << 7
    reason = _native.scene_support_reason(features)
    if reason:
        raise UnsupportedSceneV3(reason)
    if set(figure.axis_options) != {"x", "y"}:
        raise UnsupportedSceneV3("Scene v12 figure compilation currently supports exactly x/y axes")
    for options in figure.axis_options.values():
        supported_axis_keys = {
            "type",
            "constant",
            "domain",
            "nonpositive",
            "label",
            "side",
            "tick_sides",
            "tick_label_sides",
            "style",
            "minor_style",
            "tick_values",
            "tick_labels",
            "minor_tick_values",
            "format",
        }
        if any(
            key not in supported_axis_keys and value not in (None, False, [], {})
            for key, value in options.items()
        ):
            raise UnsupportedSceneV3(
                "Scene v12 does not yet encode tick formatting, collision policy, or advanced axis layout"
            )
    unsupported = next(
        (trace.kind for trace in figure.traces if trace.kind not in _SUPPORTED_KINDS), None
    )
    if unsupported is not None:
        raise UnsupportedSceneV3(f"Scene v12 figure compilation does not yet support {unsupported}")

    kinds: list[int] = []
    stable_ids: list[int] = []
    style_refs: list[int] = []
    styles: list[tuple[tuple[int, ...], tuple[int, ...], float]] = []
    diameters: list[float] = []
    symbols: list[int] = []
    coordinates: list[list[float]] = [[], [], [], []]
    expansion_modes: list[int] = []
    legend_entries: list[tuple[int, int, int, str]] = []
    for trace in figure.traces:
        if trace.x_axis != "x" or trace.y_axis != "y":
            raise UnsupportedSceneV3("Scene v12 currently supports only the primary x/y axes")
        if trace.hidden or trace.has_per_item_channels():
            raise UnsupportedSceneV3(
                "Scene v12 does not yet encode hidden or per-item styled marks"
            )
        if trace.kind == "scatter" and trace.use_density():
            raise UnsupportedSceneV3("Scene v12 does not yet encode density-tier scatter")
        style = trace.style
        if any(key in style for key in ("dash", "curve", "linecap", "marker_path", "marker_glyph")):
            raise UnsupportedSceneV3(
                "Scene v12 does not yet encode dashed, curved, or authored markers"
            )
        if trace.kind in _RECT_KINDS:
            _reject_rect_extras(style, trace.kind)
        if trace.kind in _POLYFILL_KINDS and style.get("joined_fill"):
            raise UnsupportedSceneV3("Scene v12 does not yet encode joined triangle-mesh fills")
        if trace.kind in _HEXBIN_KINDS and style.get("reduce") not in _HEXBIN_REDUCES:
            raise UnsupportedSceneV3("Scene v12 does not yet encode custom hexbin reducers")
        if trace.kind in _HEATMAP_KINDS:
            _reject_rect_extras(style, trace.kind)
            if _heatmap_uses_colormap(trace):
                raise UnsupportedSceneV3("Scene v12 does not yet encode heatmap colormap")
        opacity = float(style.get("opacity", 1.0))
        if not np.isfinite(opacity) or not 0.0 <= opacity <= 1.0:
            raise ValueError("trace opacity must be finite and in [0, 1]")
        if "fill" in style and not isinstance(style["fill"], str):
            raise UnsupportedSceneV3(f"Scene v12 does not yet encode {trace.kind} non-CSS fills")
        fill_opacity = stroke_opacity = line_opacity = 1.0
        if trace.kind in _BAND_KINDS | _RIBBON_KINDS:
            fill_opacity = float(style.get("fill_opacity", 1.0))
            stroke_opacity = float(style.get("stroke_opacity", 1.0))
        if trace.kind in _BAND_KINDS:
            line_opacity = float(style.get("line_opacity", 1.0))
        if trace.kind in _BAND_KINDS | _RIBBON_KINDS and any(
            not np.isfinite(value) or not 0.0 <= value <= 1.0
            for value in (fill_opacity, stroke_opacity, line_opacity)
        ):
            raise ValueError("trace opacity channels must be finite and in [0, 1]")
        symbol_name = str(style.get("symbol", "circle"))
        if symbol_name not in _SYMBOL_CODES:
            raise UnsupportedSceneV3(f"Scene v12 does not support scatter symbol {symbol_name!r}")
        fill, stroke, stroke_width = _resolve_mark_style(
            trace, opacity, fill_opacity, stroke_opacity, line_opacity, symbol_name
        )
        styles.append((fill, stroke, stroke_width))
        style_ref = len(styles) - 1
        diameter = (
            float(trace.size_ch.constant)
            if trace.kind == "scatter" and trace.size_ch is not None
            else float(style.get("size", 4.0))
        )
        if trace.name and figure.show_legend:
            legend_kind = 0 if trace.kind == "scatter" else 1 if trace.kind in _STROKE_KINDS else 2
            legend_entries.append(
                (
                    style_ref,
                    legend_kind,
                    _SYMBOL_CODES[symbol_name] if legend_kind == 0 else 0,
                    str(trace.name),
                )
            )

        if trace.kind in _RIBBON_KINDS:
            if any(
                value is None
                for value in (trace.x0, trace.x1, trace.y0, trace.y1, trace.x, trace.y)
            ):
                raise ValueError("ribbon Scene v12 compilation requires six geometry columns")
            columns = [
                np.asarray(trace.x0.values, dtype=np.float64),
                np.asarray(trace.x1.values, dtype=np.float64),
                np.asarray(trace.y0.values, dtype=np.float64),
                np.asarray(trace.y1.values, dtype=np.float64),
                np.asarray(trace.x.values, dtype=np.float64),
                np.asarray(trace.y.values, dtype=np.float64),
            ]
            if len({len(column) for column in columns}) != 1:
                raise UnsupportedSceneV3("Scene v12 ribbon columns must have equal length")
            _append_packed(
                kinds,
                stable_ids,
                style_refs,
                diameters,
                symbols,
                expansion_modes,
                coordinates,
                4,
                columns,
                style_ref=style_ref,
                trace_id=int(trace.id),
            )
            continue

        if trace.kind in _POLYFILL_KINDS:
            if any(
                value is None
                for value in (trace.x0, trace.y0, trace.x1, trace.y1, trace.x, trace.y)
            ):
                raise ValueError("triangle_mesh Scene v12 compilation requires six vertex columns")
            columns = [
                np.asarray(trace.x0.values, dtype=np.float64),
                np.asarray(trace.y0.values, dtype=np.float64),
                np.asarray(trace.x1.values, dtype=np.float64),
                np.asarray(trace.y1.values, dtype=np.float64),
                np.asarray(trace.x.values, dtype=np.float64),
                np.asarray(trace.y.values, dtype=np.float64),
            ]
            if len({len(column) for column in columns}) != 1:
                raise UnsupportedSceneV3("Scene v12 triangle_mesh columns must have equal length")
            _append_packed(
                kinds,
                stable_ids,
                style_refs,
                diameters,
                symbols,
                expansion_modes,
                coordinates,
                5,
                columns,
                style_ref=style_ref,
                trace_id=int(trace.id),
            )
            continue

        if trace.kind in _HEXBIN_KINDS:
            if trace.x is None or trace.y is None:
                raise ValueError("hexbin Scene v12 compilation requires center columns")
            xv = np.asarray(trace.x.values, dtype=np.float64)
            yv = np.asarray(trace.y.values, dtype=np.float64)
            if len(xv) != len(yv):
                raise UnsupportedSceneV3("Scene v12 hexbin columns must have equal length")
            dx, dy = _hexbin_pitch(style)
            _append_packed(
                kinds,
                stable_ids,
                style_refs,
                diameters,
                symbols,
                expansion_modes,
                coordinates,
                6,
                [xv, yv],
                style_ref=style_ref,
                trace_id=int(trace.id),
                extra0=dx,
                extra1=dy,
            )
            continue

        if trace.kind in _HEATMAP_KINDS:
            rows, cols = _heatmap_shape(trace)
            values = _heatmap_grid_values(trace)
            if values.size != rows * cols:
                raise UnsupportedSceneV3("Scene v12 heatmap grid must match rows x cols")
            if not np.isfinite(values).all():
                raise UnsupportedSceneV3(
                    "Scene v12 does not yet encode missing-data breaks or nonfinite coordinates"
                )
            x0, x1, y0, y1 = _heatmap_extent(trace)
            _append_packed(
                kinds,
                stable_ids,
                style_refs,
                diameters,
                symbols,
                expansion_modes,
                coordinates,
                7,
                [
                    np.asarray([x0], dtype=np.float64),
                    np.asarray([y0], dtype=np.float64),
                    np.asarray([x1], dtype=np.float64),
                    np.asarray([y1], dtype=np.float64),
                ],
                style_ref=style_ref,
                trace_id=int(trace.id),
                extra0=float(rows),
                extra1=float(cols),
            )
            continue

        if trace.kind in _BAND_KINDS:
            xv, yv, base = _band_columns(trace)
            stroke_perimeter = style.get("stroke_perimeter", False)
            if not isinstance(stroke_perimeter, bool):
                raise UnsupportedSceneV3("Scene v25 area stroke_perimeter must be a boolean")
            _append_packed(
                kinds,
                stable_ids,
                style_refs,
                diameters,
                symbols,
                expansion_modes,
                coordinates,
                3,
                [xv, yv, base],
                flags=1 if stroke_perimeter else 0,
                style_ref=style_ref,
                trace_id=int(trace.id),
            )
            continue

        if trace.kind in _RECT_KINDS:
            arrays = _rect_columns(trace)
            _append_packed(
                kinds,
                stable_ids,
                style_refs,
                diameters,
                symbols,
                expansion_modes,
                coordinates,
                2,
                arrays,
                style_ref=style_ref,
                trace_id=int(trace.id),
            )
            continue

        if trace.kind in _SEGMENT_KINDS:
            arrays = _segment_columns(trace)
            _append_packed(
                kinds,
                stable_ids,
                style_refs,
                diameters,
                symbols,
                expansion_modes,
                coordinates,
                8,
                arrays,
                style_ref=style_ref,
                trace_id=int(trace.id),
            )
            continue

        xv = np.asarray(trace.x.values, dtype=np.float64)
        yv = np.asarray(trace.y.values, dtype=np.float64)
        where = style.get("step")
        step_mode = 0
        if where is not None:
            if trace.kind != "line":
                raise UnsupportedSceneV3("Scene v12 step expansion applies only to line traces")
            if where not in {"pre", "post", "mid"}:
                raise UnsupportedSceneV3(f"Scene v12 does not support step mode {where!r}")
            step_mode = {"pre": 1, "mid": 2, "post": 3}[where]
        _append_packed(
            kinds,
            stable_ids,
            style_refs,
            diameters,
            symbols,
            expansion_modes,
            coordinates,
            0 if trace.kind == "scatter" else 1,
            [xv, yv],
            step_mode=step_mode,
            symbol=_SYMBOL_CODES[symbol_name] if trace.kind == "scatter" else 0,
            style_ref=style_ref,
            trace_id=int(trace.id),
            diameter=diameter if trace.kind == "scatter" else 0.0,
        )

    # Scene v12's bounded primary-annotation subset is represented by ordinary
    # canonical records with a reserved stable-id namespace. Rust therefore
    # remains the sole owner of scale projection, clipping, painter lowering,
    # SVG/raster order and marker geometry; hosts only coerce authored values.
    annotation_prefix = 0x5859000000000000
    x_domain = tuple(float(value) for value in figure._range("x"))
    y_domain = tuple(float(value) for value in figure._range("y"))

    def annotation_number(values: dict[str, Any], key: str, default: Any, label: str) -> float:
        raw = values.get(key, default)
        if (
            raw is None
            or isinstance(raw, (bool, np.bool_))
            or (isinstance(raw, str) and not raw.strip())
        ):
            raise ValueError(f"Scene v12 annotation {label} must be numeric")
        try:
            value = float(raw)
        except (TypeError, ValueError) as error:
            raise ValueError(f"Scene v12 annotation {label} must be numeric") from error
        return value

    def annotation_color(style: dict[str, Any], key: str, default: str, label: str) -> str:
        raw = style.get(key, default)
        if not isinstance(raw, str) or not raw.strip():
            raise ValueError(f"Scene v12 annotation {label} must be a nonempty CSS color")
        return raw

    # XYAL v2 carries only literal RGBA paint with the annotation identity and
    # text. Rust still owns the anchor, clipping, typography, and paint order.
    attached_labels: list[
        tuple[
            int,
            tuple[int, int, int, int],
            tuple[int, int, int, int] | None,
            tuple[tuple[int, int, int, int], float] | None,
            str,
        ]
    ] = []
    straight_arrows: list[
        tuple[int, float, float, float, float, tuple[int, int, int, int], float, float]
    ] = []
    # XYAC v1 is deliberately a compact host framing seam.  Every layout,
    # projection, label placement, connector shape, clipping, and paint-order
    # decision remains in Rust.  One row is little-endian
    # ``dddd4sddB3xI`` (60 fixed bytes) followed by its UTF-8 text:
    # data x/y, pixel dx/dy, literal RGBA, opacity, width, anchor code
    # (start=0/middle=1/end=2), three required zero bytes, and u32 text
    # byte length. Rust derives the callout identity from record order.
    cartesian_callouts: list[
        tuple[
            float,
            float,
            float,
            float,
            tuple[int, int, int, int],
            float,
            float,
            int,
            bytes,
            tuple[int, int, int, int] | None,
            tuple[tuple[int, int, int, int], float] | None,
        ]
    ] = []
    wrapped_annotations: list[dict[str, Any]] = []
    for annotation_index, annotation in enumerate(annotations):
        kind = annotation.get("kind")
        if kind in {"text", "callout"} and "wrap" in annotation:
            wrapped_annotations.append(annotation)
            continue
        if kind == "text":
            continue
        if kind == "arrow":
            if annotation.get("text") not in (None, "") or annotation.get("class_name") not in (
                None,
                "",
            ):
                raise UnsupportedSceneV3("Scene arrows do not encode text or class_name")
            style = dict(annotation.get("style") or {})
            bad = sorted(
                key
                for key, value in style.items()
                if key not in {"color", "opacity", "width"} and value is not None
            )
            if bad:
                raise UnsupportedSceneV3(f"Scene arrow style does not encode {bad!r}")
            opacity = annotation_number(style, "opacity", 1.0, "arrow opacity")
            width_value = annotation_number(style, "width", 1.5, "arrow width")
            if (
                not np.isfinite(opacity)
                or not 0 <= opacity <= 1
                or not np.isfinite(width_value)
                or width_value <= 0
            ):
                raise ValueError("Scene arrow opacity must be in [0, 1] and width must be positive")
            straight_arrows.append(
                (
                    annotation_prefix | (5 << 40) | annotation_index,
                    annotation_number(annotation, "x0", None, "arrow x0"),
                    annotation_number(annotation, "y0", None, "arrow y0"),
                    annotation_number(annotation, "x1", None, "arrow x1"),
                    annotation_number(annotation, "y1", None, "arrow y1"),
                    _rgba(annotation_color(style, "color", "#667085", "arrow color"), 1.0),
                    opacity,
                    width_value,
                )
            )
            continue
        if kind == "callout":
            if annotation.get("class_name") not in (None, ""):
                raise UnsupportedSceneV3("Scene callouts do not encode class_name")
            value = annotation.get("text")
            if not isinstance(value, str) or not value or "\0" in value:
                raise UnsupportedSceneV3("Scene callouts require nonempty NUL-free text")
            encoded = value.encode("utf-8")
            if len(encoded) > 4096:
                raise UnsupportedSceneV3("Scene callouts are limited to 4,096 UTF-8 bytes")
            style = dict(annotation.get("style") or {})
            bad = sorted(
                key
                for key, style_value in style.items()
                if key
                not in {
                    "color",
                    "opacity",
                    "width",
                    "label_background",
                    "label_border_color",
                    "label_border_width",
                }
                and style_value is not None
            )
            if bad:
                raise UnsupportedSceneV3(f"Scene callout style does not encode {bad!r}")
            opacity = annotation_number(style, "opacity", 1.0, "callout opacity")
            width_value = annotation_number(style, "width", 1.5, "callout width")
            if (
                not np.isfinite(opacity)
                or not 0 <= opacity <= 1
                or not np.isfinite(width_value)
                or width_value <= 0
            ):
                raise ValueError(
                    "Scene callout opacity must be in [0, 1] and width must be positive"
                )
            anchor = annotation.get("anchor", "start")
            anchor_code = {"start": 0, "middle": 1, "end": 2}.get(anchor)
            if anchor_code is None:
                raise UnsupportedSceneV3("Scene callout anchor must be start, middle, or end")
            x = annotation_number(annotation, "x", None, "callout x")
            y = annotation_number(annotation, "y", None, "callout y")
            dx = annotation_number(annotation, "dx", 36.0, "callout dx")
            dy = annotation_number(annotation, "dy", -30.0, "callout dy")
            if not all(np.isfinite(number) for number in (x, y, dx, dy)):
                raise ValueError("Scene callout coordinates and offsets must be finite")
            label_background = style.get("label_background")
            label_fill = (
                _rgba(
                    annotation_color(style, "label_background", "", "callout label background"), 1.0
                )
                if label_background is not None
                else None
            )
            border_color = style.get("label_border_color")
            border_width = style.get("label_border_width")
            if (border_color is None) != (border_width is None):
                raise UnsupportedSceneV3("Scene v23 label border requires color and width")
            label_border = (
                (
                    _rgba(
                        annotation_color(style, "label_border_color", "", "callout label border"),
                        1.0,
                    ),
                    annotation_number(
                        style, "label_border_width", None, "callout label border width"
                    ),
                )
                if border_color is not None
                else None
            )
            if label_border is not None and (
                not np.isfinite(label_border[1]) or label_border[1] <= 0
            ):
                raise ValueError("Scene v23 label border width must be positive and finite")
            if label_border is not None and label_fill is None:
                raise UnsupportedSceneV3("Scene v23 label border requires label_background")
            cartesian_callouts.append(
                (
                    x,
                    y,
                    dx,
                    dy,
                    _rgba(annotation_color(style, "color", "#344054", "callout color"), 1.0),
                    opacity,
                    width_value,
                    anchor_code,
                    encoded,
                    label_fill,
                    label_border,
                )
            )
            continue
        if kind not in {"rule", "band", "marker"}:
            raise UnsupportedSceneV3(
                f"Scene v12 annotations support rule, band, and unlabeled marker only; {kind!r} is deferred"
            )
        attached_text = annotation.get("text")
        if attached_text not in (None, "") and (
            not isinstance(attached_text, str) or "\0" in attached_text
        ):
            raise UnsupportedSceneV3("Scene v16 annotation labels require nonempty NUL-free text")
        if annotation.get("class_name") not in (None, ""):
            raise UnsupportedSceneV3("Scene v12 annotations do not encode class_name")
        style = dict(annotation.get("style") or {})
        allowed = {"color", "opacity"}
        if attached_text not in (None, ""):
            allowed |= {
                "label_color",
                "label_opacity",
                "label_background",
                "label_border_color",
                "label_border_width",
            }
        if kind == "rule":
            allowed.add("width")
        elif kind == "marker":
            allowed |= {"stroke_color", "stroke_width"}
        unsupported_style = sorted(
            key for key, value in style.items() if key not in allowed and value is not None
        )
        if unsupported_style:
            raise UnsupportedSceneV3(
                f"Scene v12 {kind} annotation style does not encode {unsupported_style!r}"
            )
        opacity = annotation_number(
            style, "opacity", 0.14 if kind == "band" else 1.0, f"{kind} opacity"
        )
        if not np.isfinite(opacity) or not 0.0 <= opacity <= 1.0:
            raise ValueError(f"Scene v12 {kind} annotation opacity must be finite and in [0, 1]")
        color = annotation_color(
            style, "color", "#64748b" if kind == "band" else "#667085", f"{kind} color"
        )
        fill = _rgba(color, opacity) if kind != "rule" else (0, 0, 0, 0)
        stroke_color = annotation_color(style, "stroke_color", color, f"{kind} stroke color")
        stroke = _rgba(stroke_color, opacity)
        width_key = "width" if kind == "rule" else "stroke_width"
        width_value = annotation_number(
            style, width_key, 1.5 if kind != "band" else 0.0, f"{kind} width"
        )
        if not np.isfinite(width_value) or width_value < 0 or (kind == "rule" and width_value == 0):
            raise ValueError(f"Scene v12 {kind} annotation width must be finite and nonnegative")
        styles.append((fill, stroke, width_value))
        style_ref = len(styles) - 1
        tag = (
            4
            if kind == "band" and annotation.get("axis") == "y"
            else {"rule": 1, "band": 2, "marker": 3}[kind]
        )
        stable_id = annotation_prefix | (tag << 40) | annotation_index
        if attached_text not in (None, ""):
            encoded_text = attached_text.encode("utf-8")
            if len(encoded_text) > 4096:
                raise UnsupportedSceneV3(
                    "Scene v16 annotation labels are limited to 4,096 UTF-8 bytes"
                )
            label_opacity = annotation_number(style, "label_opacity", 1.0, f"{kind} label opacity")
            if not np.isfinite(label_opacity) or not 0.0 <= label_opacity <= 1.0:
                raise ValueError(
                    f"Scene v16 {kind} annotation label opacity must be finite and in [0, 1]"
                )
            label_color = annotation_color(style, "label_color", "#667085", f"{kind} label color")
            label_background = style.get("label_background")
            label_fill = (
                _rgba(
                    annotation_color(style, "label_background", "", f"{kind} label background"), 1.0
                )
                if label_background is not None
                else None
            )
            border_color = style.get("label_border_color")
            border_width = style.get("label_border_width")
            if (border_color is None) != (border_width is None):
                raise UnsupportedSceneV3("Scene v23 label border requires color and width")
            label_border = (
                (
                    _rgba(
                        annotation_color(style, "label_border_color", "", f"{kind} label border"),
                        1.0,
                    ),
                    annotation_number(
                        style, "label_border_width", None, f"{kind} label border width"
                    ),
                )
                if border_color is not None
                else None
            )
            if label_border is not None and (
                not np.isfinite(label_border[1]) or label_border[1] <= 0
            ):
                raise ValueError("Scene v23 label border width must be positive and finite")
            if label_border is not None and label_fill is None:
                raise UnsupportedSceneV3("Scene v23 label border requires label_background")
            attached_labels.append(
                (
                    stable_id,
                    _rgba(label_color, label_opacity),
                    label_fill,
                    label_border,
                    attached_text,
                )
            )

        def append_record(
            record_kind: int,
            a: float,
            b: float,
            c: float,
            d: float,
            *,
            size: float = 0.0,
            symbol: int = 0,
            annotation_kind: str = kind,
            annotation_stable_id: int = stable_id,
            annotation_style_ref: int = style_ref,
        ) -> None:
            values = (a, b, c, d, size)
            if not all(np.isfinite(value) for value in values):
                raise ValueError(f"Scene v12 {annotation_kind} annotation geometry must be finite")
            kinds.append(record_kind)
            stable_ids.append(annotation_stable_id)
            style_refs.append(annotation_style_ref)
            diameters.append(size)
            symbols.append(symbol)
            expansion_modes.append(0)
            for destination, value in zip(coordinates, (a, b, c, d), strict=True):
                destination.append(float(value))

        if kind == "rule":
            axis_name = annotation.get("axis")
            if axis_name not in {"x", "y"}:
                raise ValueError("Scene v12 rule annotation axis must be 'x' or 'y'")
            value = annotation_number(annotation, "value", None, f"{kind} value")
            if axis_name == "x":
                append_record(1, value, y_domain[0], 0.0, 0.0)
                append_record(1, value, y_domain[1], 0.0, 0.0)
            else:
                append_record(1, x_domain[0], value, 0.0, 0.0)
                append_record(1, x_domain[1], value, 0.0, 0.0)
        elif kind == "band":
            axis_name = annotation.get("axis")
            if axis_name not in {"x", "y"}:
                raise ValueError("Scene v12 band annotation axis must be 'x' or 'y'")
            start = annotation_number(annotation, "start", None, f"{kind} start")
            end = annotation_number(annotation, "end", None, f"{kind} end")
            if axis_name == "x":
                append_record(2, start, y_domain[0], end, y_domain[1])
            else:
                append_record(2, x_domain[0], start, x_domain[1], end)
        else:
            symbol_name = str(annotation.get("symbol", "circle"))
            if symbol_name not in _SYMBOL_CODES:
                raise UnsupportedSceneV3(
                    f"Scene v12 does not support marker symbol {symbol_name!r}"
                )
            size = annotation_number(annotation, "size", 8.0, f"{kind} size")
            if not np.isfinite(size) or size <= 0:
                raise ValueError("Scene v12 marker annotation size must be finite and positive")
            append_record(
                0,
                annotation_number(annotation, "x", None, f"{kind} x"),
                annotation_number(annotation, "y", None, f"{kind} y"),
                0.0,
                0.0,
                size=size,
                symbol=_SYMBOL_CODES[symbol_name],
            )

    w = int(width if width is not None else figure.width)
    h = int(height if height is not None else figure.height)
    fill_rgba = [channel for fill, _, _ in styles for channel in fill]
    stroke_rgba = [channel for _, stroke, _ in styles for channel in stroke]
    stroke_width = [value for _, _, value in styles]
    kind_codes = {"linear": 0, "log": 1, "symlog": 2}

    def axis(axis_id: str, stable_id: int) -> tuple[int, int, float, float, float, bool]:
        scale = figure._axis_scale(axis_id)
        options = figure.axis_options[axis_id]
        return (
            stable_id,
            kind_codes[scale],
            *figure._range(axis_id),
            float(options.get("constant") or 1.0),
            options.get("nonpositive", "clip") == "mask",
        )

    x_axis = axis("x", 1)
    y_axis = axis("y", 2)
    title = str(figure.title or "")
    x_label = str(figure.x_label or figure.axis_options.get("x", {}).get("label") or "")
    y_label = str(figure.y_label or figure.axis_options.get("y", {}).get("label") or "")
    if margins is None:
        authored = None
        if getattr(figure, "padding", None) is not None:
            pad = figure.padding
            if isinstance(pad, (list, tuple)) and len(pad) == 4:
                authored = (float(pad[0]), float(pad[1]), float(pad[2]), float(pad[3]))
        left, right, top, bottom = _native.scene_plot_layout(
            viewport=(w, h),
            x_axis=x_axis[1:],
            y_axis=y_axis[1:],
            title=title,
            x_label=x_label,
            y_label=y_label,
            padding=authored,
            colorbar_side=("bottom" if colorbar_input[8] & 1 else "right")
            if colorbar_input
            else None,
            x_format=None
            if figure.axis_options["x"].get("tick_labels") is not None
            else figure.axis_options["x"].get("format"),
            y_format=None
            if figure.axis_options["y"].get("tick_labels") is not None
            else figure.axis_options["y"].get("format"),
        )
    else:
        left, right, top, bottom = margins
    text_annotations = [
        annotation
        for annotation in annotations
        if annotation.get("kind") == "text" and "wrap" not in annotation
    ]
    if len(cartesian_callouts) > 128:
        raise UnsupportedSceneV3("Scene callouts are limited to 128 entries")
    text_rows: list[
        tuple[
            float,
            float,
            tuple[int, int, int, int],
            tuple[int, int, int, int] | None,
            tuple[tuple[int, int, int, int], float] | None,
            bytes,
        ]
    ] = []
    for annotation in text_annotations:
        value = annotation.get("text")
        if not isinstance(value, str) or not value or "\0" in value:
            raise UnsupportedSceneV3("Scene v16 text annotations require nonempty NUL-free text")
        encoded = value.encode("utf-8")
        if len(encoded) > 4096:
            raise UnsupportedSceneV3("Scene v16 text annotations are limited to 4,096 UTF-8 bytes")
        x = annotation_number(annotation, "x", None, "text x")
        y = annotation_number(annotation, "y", None, "text y")
        style = dict(annotation.get("style") or {})
        if set(style) - {
            "color",
            "opacity",
            "label_background",
            "label_border_color",
            "label_border_width",
        }:
            raise UnsupportedSceneV3(
                "Scene v23 text annotations support only color, opacity, label_background, and label_border_*"
            )
        rgba = _rgba(
            annotation_color(style, "color", "#667085", "text color"),
            annotation_number(style, "opacity", 1.0, "text opacity"),
        )
        label_background = style.get("label_background")
        label_fill = (
            _rgba(annotation_color(style, "label_background", "", "text label background"), 1.0)
            if label_background is not None
            else None
        )
        border_color, border_width = (
            style.get("label_border_color"),
            style.get("label_border_width"),
        )
        if (border_color is None) != (border_width is None):
            raise UnsupportedSceneV3("Scene v23 label border requires color and width")
        label_border = (
            (
                _rgba(annotation_color(style, "label_border_color", "", "text label border"), 1.0),
                annotation_number(style, "label_border_width", None, "text label border width"),
            )
            if border_color is not None
            else None
        )
        if label_border is not None and (not np.isfinite(label_border[1]) or label_border[1] <= 0):
            raise ValueError("Scene v23 label border width must be positive and finite")
        if label_border is not None and label_fill is None:
            raise UnsupportedSceneV3("Scene v23 label border requires label_background")
        text_rows.append((x, y, rgba, label_fill, label_border, encoded))
    wrapped_rows: list[
        tuple[
            float,
            float,
            float,
            float,
            float,
            tuple[int, int, int, int],
            tuple[int, int, int, int],
            tuple[int, int, int, int],
            float,
            int,
            int,
            bytes,
        ]
    ] = []
    for annotation in wrapped_annotations:
        kind = annotation["kind"]
        if annotation.get("class_name") not in (None, ""):
            raise UnsupportedSceneV3("Scene wrapped annotations do not encode class_name")
        text = annotation.get("text")
        if not isinstance(text, str) or not text or "\0" in text or "\r" in text:
            raise UnsupportedSceneV3("Scene wrapped annotations require nonempty NUL-free LF text")
        encoded = text.encode("utf-8")
        if len(encoded) > 4096:
            raise UnsupportedSceneV3("Scene wrapped annotations are limited to 4,096 UTF-8 bytes")
        style = dict(annotation.get("style") or {})
        if style.get("color") is None:
            style.pop("color", None)
        allowed = {
            "color",
            "opacity",
            "label_background",
            "label_border_color",
            "label_border_width",
        }
        bad = sorted(
            key for key, value in style.items() if key not in allowed and value is not None
        )
        if bad:
            raise UnsupportedSceneV3(f"Scene wrapped annotations do not encode {bad!r}")
        x, y = (
            annotation_number(annotation, "x", None, "wrapped x"),
            annotation_number(annotation, "y", None, "wrapped y"),
        )
        dx = annotation_number(annotation, "dx", 36.0 if kind == "callout" else 0.0, "wrapped dx")
        dy = annotation_number(annotation, "dy", -30.0 if kind == "callout" else 0.0, "wrapped dy")
        wrap = annotation_number(annotation, "wrap", None, "wrapped width")
        if not all(np.isfinite(value) for value in (x, y, dx, dy, wrap)) or wrap < 0:
            raise ValueError(
                "Scene wrapped annotation coordinates and wrap must be finite; wrap must be nonnegative"
            )
        anchor = {"start": 0, "middle": 1, "end": 2}.get(annotation.get("anchor", "start"))
        if anchor is None:
            raise UnsupportedSceneV3(
                "Scene wrapped annotation anchor must be start, middle, or end"
            )
        opacity = annotation_number(style, "opacity", 1.0, "wrapped opacity")
        if not np.isfinite(opacity) or not 0 <= opacity <= 1:
            raise ValueError("Scene wrapped annotation opacity must be in [0, 1]")
        rgba = _rgba(
            annotation_color(
                style, "color", "#344054" if kind == "callout" else "#667085", "wrapped color"
            ),
            opacity,
        )
        fill = (
            _rgba(annotation_color(style, "label_background", "", "wrapped background"), 1.0)
            if style.get("label_background") is not None
            else (0, 0, 0, 0)
        )
        border_color, border_width = (
            style.get("label_border_color"),
            style.get("label_border_width"),
        )
        if (border_color is None) != (border_width is None):
            raise UnsupportedSceneV3("Scene wrapped label border requires color and width")
        border_rgba = (
            _rgba(annotation_color(style, "label_border_color", "", "wrapped border"), 1.0)
            if border_color is not None
            else (0, 0, 0, 0)
        )
        border = annotation_number(style, "label_border_width", 0.0, "wrapped border width")
        if border_color is not None and (not np.isfinite(border) or border <= 0):
            raise ValueError("Scene wrapped label border width must be positive and finite")
        if border_color is not None and fill[3] == 0:
            raise UnsupportedSceneV3("Scene wrapped label border requires label_background")
        wrapped_rows.append(
            (
                x,
                y,
                dx,
                dy,
                wrap,
                rgba,
                fill,
                border_rgba,
                border,
                int(kind == "callout"),
                int(anchor),
                encoded,
            )
        )
    framed_annotations = _annotation_envelope(
        text_rows,
        attached_labels,
        straight_arrows,
        cartesian_callouts,
        wrapped_rows,
    )
    return _native.scene_batch_encode(
        viewport=(w, h),
        margins=(left, right, top, bottom),
        x_axis=x_axis,
        y_axis=y_axis,
        kinds=kinds,
        stable_ids=stable_ids,
        style_refs=style_refs,
        fill_rgba=fill_rgba,
        stroke_rgba=stroke_rgba,
        stroke_width=stroke_width,
        diameter=diameters,
        symbols=symbols,
        expansion_modes=expansion_modes,
        x0=coordinates[0],
        y0=coordinates[1],
        x1=coordinates[2],
        y1=coordinates[3],
        title=title,
        x_label=x_label,
        y_label=y_label,
        chrome_style=_scene_chrome_style(figure),
        x_major_ticks=figure.axis_options["x"].get("tick_values"),
        x_tick_labels=figure.axis_options["x"].get("tick_labels"),
        x_format=figure.axis_options["x"].get("format"),
        x_minor_ticks=figure.axis_options["x"].get("minor_tick_values") or (),
        y_major_ticks=figure.axis_options["y"].get("tick_values"),
        y_tick_labels=figure.axis_options["y"].get("tick_labels"),
        y_format=figure.axis_options["y"].get("format"),
        y_minor_ticks=figure.axis_options["y"].get("minor_tick_values") or (),
        legend_input=_legend_input(figure, legend_entries, styles),
        colorbar_input=colorbar_input,
        authored_text_annotations=bytes(framed_annotations)
        if text_annotations
        or attached_labels
        or straight_arrows
        or cartesian_callouts
        or wrapped_annotations
        else b"",
    )


def figure_svg(figure: Any, **options: Any) -> str:
    return _native.scene_svg(figure_scene(figure, **options))


def figure_raster_commands(figure: Any, *, scale: float = 1.0, **options: Any) -> bytes:
    return _native.scene_raster_commands(figure_scene(figure, **options), scale)


def public_static_export(
    figure: Any,
    format: str,
    *,
    width: int | None = None,
    height: int | None = None,
    scale: float = 1.0,
) -> bytes | None:
    """Render one supported public static format from the canonical Scene.

    This is the only selection seam for the migrated public SVG/PNG/PDF
    subset.  It returns ``None`` only after the explicit support predicate
    selects compatibility *before* Scene compilation.  Once selected, every
    compiler or consumer error propagates: it is never a request to retry a
    compatibility renderer.
    """
    if scene_export_support_reason(figure, width=width, height=height) is not None:
        return None
    if format == "svg":
        return figure_svg(figure, width=width, height=height).encode("utf-8")
    if format == "png":
        from . import kernels

        commands = figure_raster_commands(figure, width=width, height=height, scale=scale)
        w = int(width if width is not None else figure.width)
        h = int(height if height is not None else figure.height)
        return kernels.rasterize_png(
            commands,
            max(1, int(round(w * float(scale)))),
            max(1, int(round(h * float(scale)))),
        )
    if format == "pdf":
        return _native.svg_to_pdf(figure_svg(figure, width=width, height=height))
    raise ValueError(f"Scene public static format must be svg, png, or pdf, got {format!r}")


def _xyep_put_keys(buf: bytearray, keys: list[str]) -> None:
    for key in keys:
        encoded = str(key).encode("utf-8")
        if len(encoded) > 256:
            encoded = encoded[:256]
        buf.extend(len(encoded).to_bytes(2, "little"))
        buf.extend(encoded)


def _xyep_column(trace: Any, name: str) -> Any:
    return getattr(trace, name, None)


def _xyep_len(column: Any) -> int:
    return 0 if column is None else int(len(column.values))


def _xyep_finite(column: Any) -> bool:
    return column is not None and bool(np.isfinite(column.values).all())


def _xyep_kind(kind: str) -> int:
    return _PUBLIC_EXPORT_KIND_CODES.get(kind, 255)


def _pack_public_export_support(
    figure: Any,
    *,
    width: int | None = None,
    height: int | None = None,
) -> bytes:
    """Pack literal figure metadata for Rust's public-export predicate."""
    flags = 0
    if width is None and not isinstance(figure.width, int):
        flags |= 1 << 0
    if height is None and not isinstance(figure.height, int):
        flags |= 1 << 1
    if getattr(figure, "chrome_styles", None):
        flags |= 1 << 2
    if getattr(figure, "title_options", None):
        flags |= 1 << 3
    style_keys = [str(key) for key in (getattr(figure, "style", None) or {})]
    legend_keys = [str(key) for key in (getattr(figure, "legend_options", None) or {})]
    colorbar_keys = [str(key) for key in (getattr(figure, "colorbar_options", None) or {})]
    annotations = list(getattr(figure, "annotations", None) or [])
    traces = list(getattr(figure, "traces", None) or [])
    payload = bytearray(b"XYEP")
    payload.extend((1).to_bytes(4, "little"))
    payload.extend(flags.to_bytes(4, "little"))
    payload.extend(len(style_keys).to_bytes(4, "little"))
    payload.extend(len(legend_keys).to_bytes(4, "little"))
    payload.extend(len(colorbar_keys).to_bytes(4, "little"))
    payload.extend(len(figure.axis_options).to_bytes(4, "little"))
    payload.extend(len(annotations).to_bytes(4, "little"))
    payload.extend(len(traces).to_bytes(4, "little"))
    _xyep_put_keys(payload, style_keys)
    _xyep_put_keys(payload, legend_keys)
    _xyep_put_keys(payload, colorbar_keys)
    for axis_id, options in figure.axis_options.items():
        axis_code = 0 if axis_id == "x" else 1 if axis_id == "y" else 255
        resolved = figure._axis_kind(axis_id)
        resolved_code = {"linear": 0, "time": 1, "category": 2}.get(resolved, 255)
        authored = options.get("type")
        authored_code = {None: 0, "linear": 1, "log": 2, "symlog": 3}.get(authored, 255)
        side = options.get("side")
        side_code = {None: 0, "bottom": 1, "left": 2, "top": 3, "right": 4}.get(side, 255)
        keys = [str(key) for key, value in options.items() if value not in (None, False)]
        payload.extend(
            bytes(
                (
                    axis_code,
                    resolved_code,
                    authored_code,
                    int(options.get("domain") is not None),
                    side_code,
                    0,
                )
            )
        )
        payload.extend(len(keys).to_bytes(2, "little"))
        _xyep_put_keys(payload, keys)
    annotation_kinds = {
        "text": 1,
        "rule": 2,
        "band": 3,
        "marker": 4,
        "arrow": 5,
        "callout": 6,
    }
    for annotation in annotations:
        if not isinstance(annotation, dict):
            payload.extend(bytes((0, 1 << 4)))
            payload.extend((0).to_bytes(2, "little"))
            continue
        kind_code = annotation_kinds.get(str(annotation.get("kind")), 0)
        flags_ann = 0
        if "wrap" in annotation:
            flags_ann |= 1 << 0
        if "dx" in annotation:
            flags_ann |= 1 << 1
        if "dy" in annotation:
            flags_ann |= 1 << 2
        if "anchor" in annotation:
            flags_ann |= 1 << 3
        fields = [str(key) for key in annotation]
        payload.extend(bytes((kind_code, flags_ann)))
        payload.extend(len(fields).to_bytes(2, "little"))
        _xyep_put_keys(payload, fields)
    for trace_index, trace in enumerate(traces):
        style = getattr(trace, "style", None) or {}
        opacity = float(style.get("opacity", 1.0))
        if not np.isfinite(opacity) or not 0.0 <= opacity <= 1.0:
            raise ValueError("trace opacity must be finite and in [0, 1]")
        kind_code = _xyep_kind(trace.kind)
        step = {"pre": 1, "mid": 2, "post": 3}.get(style.get("step"), 0)
        prev = traces[trace_index - 1] if trace_index else None
        prev2 = traces[trace_index - 2] if trace_index >= 2 else None
        prev3 = traces[trace_index - 3] if trace_index >= 3 else None
        xv = _xyep_column(trace, "x")
        yv = _xyep_column(trace, "y")
        x0 = _xyep_column(trace, "x0")
        y0 = _xyep_column(trace, "y0")
        x1 = _xyep_column(trace, "x1")
        y1 = _xyep_column(trace, "y1")
        mesh = (x0, y0, x1, y1, xv, yv)
        flags_tr = 0
        if xv is not None:
            flags_tr |= 1 << 0
        if yv is not None:
            flags_tr |= 1 << 1
        if xv is not None and yv is not None and _xyep_len(xv) == _xyep_len(yv):
            flags_tr |= 1 << 2
        if _xyep_finite(xv):
            flags_tr |= 1 << 3
        if _xyep_finite(yv):
            flags_tr |= 1 << 4
        if None not in (x0, y0, x1, y1):
            flags_tr |= 1 << 5
            lengths = {_xyep_len(column) for column in (x0, y0, x1, y1)}
            if len(lengths) == 1:
                flags_tr |= 1 << 6
        if all(column is not None for column in mesh):
            flags_tr |= 1 << 7
            mesh_lengths = {_xyep_len(column) for column in mesh}
            if len(mesh_lengths) == 1:
                flags_tr |= 1 << 8
            if all(_xyep_finite(column) for column in mesh):
                flags_tr |= 1 << 9
        if style.get("joined_fill"):
            flags_tr |= 1 << 10
        heatmap_rows = heatmap_cols = heatmap_values = 0
        if trace.kind == "heatmap":
            if _heatmap_uses_colormap(trace):
                flags_tr |= 1 << 11
            try:
                heatmap_rows, heatmap_cols = _heatmap_shape(trace)
                values = _heatmap_grid_values(trace)
                _heatmap_extent(trace)
                flags_tr |= 1 << 12
                flags_tr |= 1 << 13
                heatmap_values = int(values.size)
                if np.isfinite(values).all():
                    flags_tr |= 1 << 14
            except (UnsupportedSceneV3, ValueError, TypeError):
                heatmap_rows = heatmap_cols = heatmap_values = 0
        if xv is not None and yv is not None and _xyep_len(xv) == _xyep_len(yv):
            flags_tr |= 1 << 15
        if _xyep_finite(xv) and _xyep_finite(yv):
            flags_tr |= 1 << 16
        if style.get("stroke_width") is not None and style.get("stroke") is None:
            flags_tr |= 1 << 17
        if (
            prev is not None
            and xv is not None
            and yv is not None
            and _xyep_column(prev, "x1") is not None
            and _xyep_column(prev, "y1") is not None
            and np.array_equal(xv.values, prev.x1.values)
            and np.array_equal(yv.values, prev.y1.values)
        ):
            flags_tr |= 1 << 18
        if prev is not None and trace.x_axis == prev.x_axis and trace.y_axis == prev.y_axis:
            flags_tr |= 1 << 19
        if _xyep_finite(xv) and _xyep_finite(yv):
            flags_tr |= 1 << 20
        symbol = style.get("symbol", "circle")
        if not isinstance(symbol, str):
            flags_tr |= 1 << 21
            symbol = ""
        role = style.get("role")
        role_s = "" if role is None else str(role)
        reduce = style.get("reduce")
        reduce_s = "" if reduce is None else str(reduce)
        try:
            hex_dx, hex_dy = (
                _hexbin_pitch(style) if trace.kind == "hexbin" else (float("nan"), float("nan"))
            )
        except UnsupportedSceneV3:
            hex_dx = hex_dy = float("nan")
        style_keys = [str(key) for key, value in style.items() if value is not None]
        n_mesh = _xyep_len(xv) if flags_tr & (1 << 7) else 0
        payload.extend(
            struct.pack(
                "<BBBBBBHIIIIIIIIIIHHHHdd",
                kind_code,
                step,
                255 if prev is None else _xyep_kind(prev.kind),
                255 if prev2 is None else _xyep_kind(prev2.kind),
                255 if prev3 is None else _xyep_kind(prev3.kind),
                0,
                0,
                flags_tr,
                _xyep_len(xv) if xv is not None else n_mesh,
                _xyep_len(yv),
                _xyep_len(x0),
                _xyep_len(y0),
                _xyep_len(x1),
                _xyep_len(y1),
                heatmap_rows,
                heatmap_cols,
                heatmap_values,
                len(style_keys),
                len(role_s.encode("utf-8")),
                len(symbol.encode("utf-8")) if isinstance(symbol, str) else 0,
                len(reduce_s.encode("utf-8")),
                hex_dx,
                hex_dy,
            )
        )
        payload.extend(role_s.encode("utf-8"))
        payload.extend(symbol.encode("utf-8") if isinstance(symbol, str) else b"")
        payload.extend(reduce_s.encode("utf-8"))
        _xyep_put_keys(payload, style_keys)
    return bytes(payload)


def scene_export_support_reason(
    figure: Any,
    *,
    width: int | None = None,
    height: int | None = None,
) -> str | None:
    """Return why a figure cannot compile to the canonical Rust Scene, or ``None``.

    This is the single support predicate the #117 public static-export router
    consults before selecting the Rust Scene path over the compatibility
    ``_svg`` / ``_raster`` renderers. It reports the stable
    ``XYG_SCENE_UNSUPPORTED_*`` diagnostic (or the compiler's own bounded
    message) so callers can log or surface an actionable reason for the fallback.

    Hosts only pack literal figure metadata. Rust owns the public-subset
    allowlists, check order, and diagnostic wording. After that preflight the
    predicate still compiles the Scene so it cannot disagree with the encoder,
    and it asks the browser painter to enforce the shared PolyFill group budget.
    """
    envelope = _pack_public_export_support(figure, width=width, height=height)
    reason = _native.scene_public_export_reason(envelope)
    if reason:
        return reason
    public_triangle_mesh_count = 0
    for trace in getattr(figure, "traces", None) or []:
        if trace.kind in _POLYFILL_KINDS:
            mesh = (
                getattr(trace, "x0", None),
                getattr(trace, "y0", None),
                getattr(trace, "x1", None),
                getattr(trace, "y1", None),
                getattr(trace, "x", None),
                getattr(trace, "y", None),
            )
            if all(column is not None for column in mesh):
                public_triangle_mesh_count += len(mesh[0].values)
        elif trace.kind in _HEXBIN_KINDS and trace.x is not None:
            public_triangle_mesh_count += len(trace.x.values)
    try:
        scene = figure_scene(figure, width=width, height=height)
    except UnsupportedSceneV3 as unsupported:
        return str(unsupported)
    except ValueError as exc:
        if str(exc) == "invalid canonical scene plot layout":
            return "XYG_SCENE_UNSUPPORTED_VIEWPORT"
        raise
    if public_triangle_mesh_count:
        try:
            _native.scene_browser_painter(scene)
        except ValueError as exc:
            if str(exc) == "invalid canonical scene for browser painter":
                return "XYG_SCENE_UNSUPPORTED_PUBLIC_TRIANGLE_MESH"
            raise
    return None
