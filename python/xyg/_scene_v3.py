"""Thin figure-to-Scene v12 compiler for the migrated core-mark subset.

Rust owns mapping, clipping, record semantics, SVG construction, and raster
display-list construction. This module only projects already-validated Figure
objects into the typed ABI and rejects features whose canonical Scene record
does not exist yet.
"""

from __future__ import annotations

import struct
from typing import Any, NoReturn

import numpy as np

from . import _native
from ._scene_marshal import pack_public_export_support as _pack_public_export_support

# Re-export observation helpers for existing imports (tests, scripts).
from ._scene_observations import (  # noqa: F401
    _ANNOTATION_TYPOGRAPHY_STYLE_KEYS,
    _POLAR_COLLISION_KEYS,
    _SCENE_AXIS_STYLE_KEYS,
    UnsupportedSceneV3,
    _admitted_fill_gradient,
    _admitted_fill_gradient_from_fill,
    _annotation_has_custom_typography,
    _annotation_has_markup,
    _channel_constant_css,
    _channel_end_rgba8,
    _classify_ribbon_color2,
    _colormap_stop_bytes,
    _constant_color,
    _density_aggregates_color,
    _fill_is_gradient_authoring,
    _heatmap_extent,
    _heatmap_grid_values,
    _heatmap_shape,
    _hexbin_cell_rgba8,
    _hexbin_count,
    _hexbin_packs_colormap_plane,
    _hexbin_packs_paint_plane,
    _hexbin_packs_rgba_plane,
    _hexbin_pitch,
    _item_apply_opacity,
    _item_fill_rgba8,
    _item_stroke_rgba8,
    _mesh_count,
    _mesh_joined_fill,
    _mesh_packs_paint_plane,
    _parse_scene_dash,
    _ribbon_color2_class_code,
    _ribbon_count,
    _ribbon_end_rgba_pair,
    _ribbon_packs_end_paints,
    _scatter_count,
    _scatter_packs_paint_plane,
    _scene_side_mask,
    _scene_tick_label_strategy,
    _significant_scene_axis_keys,
    _trace_column,
    _trace_source_color_css,
    _xyta_hexbin_plane_observations,
)
from ._scene_unpack import (  # noqa: F401
    _unpack_gradient_blob,
    _unpack_marker_blob,
    _unpack_xyas,
    _unpack_xycc,
    _xycc_tick_labels,
)
from .marks import _SYMBOL_CODES

# Host mark kinds that lower to Scene Rect (kind 2). Geometry is already
# x0/y0/x1/y1 columns on the Trace; Scene does not recompute bar stacking.
# Packing-family bits are ABI 236 `xyg_scene_kind_class`.
_SCENE_KIND_CLASS_RECT = 1 << 0
_SCENE_KIND_CLASS_BAND = 1 << 2
_SCENE_KIND_CLASS_RIBBON = 1 << 3
_SCENE_KIND_CLASS_POLYFILL = 1 << 4
_SCENE_KIND_CLASS_HEXBIN = 1 << 5
_SCENE_KIND_CLASS_HEATMAP = 1 << 6
_SCENE_KIND_CLASS_SCATTER = 1 << 8
_SCENE_KIND_CLASS_LINE = 1 << 9
_SCENE_KIND_CLASS_OPACITY = (
    _SCENE_KIND_CLASS_BAND
    | _SCENE_KIND_CLASS_RIBBON
    | _SCENE_KIND_CLASS_RECT
    | _SCENE_KIND_CLASS_HEATMAP
    | _SCENE_KIND_CLASS_SCATTER
    | _SCENE_KIND_CLASS_HEXBIN
    | _SCENE_KIND_CLASS_POLYFILL
)
# ABI 175 packs fill/stroke opacity channels for violin/box (XYMS already
# composites them). ABI 176 extends that packing to bar/column/histogram, the
# remaining PACK_RECT kinds. ABI 177 packs heatmap `fill_opacity` so lattice
# cells and colormap paints use the XYMS fill alpha. ABI 178 packs scatter
# `fill_opacity` / `stroke_opacity` on that same XYMS path. ABI 179 packs hexbin
# `fill_opacity` so HexCell PolyFills use the XYMS fill alpha. ABI 193 packs
# heatmap/hexbin `stroke_opacity` on that same XYMS path (authored `stroke` /
# `stroke_width` already packed). ABI 180 packs
# triangle_mesh `fill_opacity` / constant stroke on that same XYMS path.
# Cartesian hexbin centers expand onto PolyFill records (6-vertex cells) in
# Rust (`SceneExpansionMode::HexCell`). Hosts pack one compact center+pitch
# row per cell. Regular Cartesian heatmap cells expand onto Rect records in
# Rust (`SceneExpansionMode::HeatmapLattice`). Hosts pack extent plus
# rows/cols. Painted lattices (`HeatmapPainted`) add an XYHP sidecar.
# Cartesian tessellates cells and interns unique fills. Polar painted
# heatmaps inverse-raster to one Image blit covering the plot (ABI 192).
# Constant-style polar lattices still tessellate Rects to PolyFill wedges.
_XYMG_MAX_UTF8 = 64

# Each unjoined triangle or hex cell is one PolyFill group in the Rust browser
# painter. Keep the public route inside its canonical group budget; larger
# meshes and honeycombs remain on the compatibility path until Scene gains a
# compact multi-cell painter record.
# Regular heatmap cells are ordinary Rect records and share the histogram
# 10,000-bin public ceiling. Irregular grids stay on the compatibility
# exporters. Scalar-colormap and truecolor heatmaps tessellate those Rects
# with per-cell literal styles on cartesian Scene. Polar painted heatmaps
# inverse-raster to one plot-covering Image (ABI 192); the public cell cap
# for that blit is `MAX_SCENE_IMAGE_PIXELS` in Rust.
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
    "contour": 18,
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


_XYAF_KIND_CODES = {
    "text": 0,
    "arrow": 1,
    "callout": 2,
    "rule": 3,
    "band": 4,
    "marker": 5,
}
_XYAF_FACT_HAS_WRAP = 1 << 0
_XYAF_FACT_HAS_TEXT = 1 << 1
_XYAF_FACT_HAS_CLASS_NAME = 1 << 2
_XYAF_FACT_HAS_DX = 1 << 3
_XYAF_FACT_HAS_DY = 1 << 4
_XYAF_FACT_HAS_X = 1 << 5
_XYAF_FACT_HAS_Y = 1 << 6
_XYAF_FACT_HAS_X0 = 1 << 7
_XYAF_FACT_HAS_Y0 = 1 << 8
_XYAF_FACT_HAS_X1 = 1 << 9
_XYAF_FACT_HAS_Y1 = 1 << 10
_XYAF_FACT_HAS_VALUE = 1 << 11
_XYAF_FACT_HAS_START = 1 << 12
_XYAF_FACT_HAS_END = 1 << 13
_XYAF_FACT_HAS_SIZE = 1 << 14
_XYAF_FACT_HAS_AXIS = 1 << 15
_XYAF_FACT_HAS_SYMBOL = 1 << 16
_XYAF_FACT_HAS_ANCHOR = 1 << 17
_XYAF_FACT_HAS_ROTATION = 1 << 18
_XYAF_STYLE_COLOR = 1 << 0
_XYAF_STYLE_OPACITY = 1 << 1
_XYAF_STYLE_WIDTH = 1 << 2
_XYAF_STYLE_DASH = 1 << 3
_XYAF_STYLE_LINECAP = 1 << 4
_XYAF_STYLE_STROKE_COLOR = 1 << 5
_XYAF_STYLE_STROKE_WIDTH = 1 << 6
_XYAF_STYLE_LABEL_COLOR = 1 << 7
_XYAF_STYLE_LABEL_OPACITY = 1 << 8
_XYAF_STYLE_LABEL_BACKGROUND = 1 << 9
_XYAF_STYLE_LABEL_BORDER_COLOR = 1 << 10
_XYAF_STYLE_LABEL_BORDER_WIDTH = 1 << 11
_XYAF_STYLE_UNSUPPORTED = 1 << 31
_XYAF_HEADER = struct.Struct("<4sIIBBBBIIBBHI18d4s4s4s4s4sI8f")


def _pack_annotation_mark_row(
    kind_code: int,
    axis_code: int,
    symbol: int,
    style_ref: int,
    index: int,
    value0: float,
    value1: float,
    size: float,
) -> bytes:
    """One 40-byte authored rule/band/marker row for Rust domain expansion."""
    return struct.pack(
        "<BBBBIIxxxxddd",
        int(kind_code),
        int(axis_code),
        int(symbol),
        0,
        int(style_ref),
        int(index),
        float(value0),
        float(value1),
        float(size),
    )


def _append_annotation_marks(
    kinds: list[int],
    stable_ids: list[int],
    style_refs: list[int],
    diameters: list[float],
    symbols: list[int],
    expansion_modes: list[int],
    coordinates: list[list[float]],
    rows: bytes,
    x_domain: tuple[float, float],
    y_domain: tuple[float, float],
) -> None:
    if not rows:
        return
    (
        packed_kinds,
        packed_ids,
        packed_refs,
        packed_diameters,
        packed_symbols,
        packed_modes,
        coords,
    ) = _native.scene_pack_annotation_marks(rows, x_domain=x_domain, y_domain=y_domain)
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


def _annotation_number(values: dict[str, Any], key: str, default: Any, label: str) -> float:
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


def _annotation_color(style: dict[str, Any], key: str, default: str, label: str) -> str:
    raw = style.get(key, default)
    if not isinstance(raw, str) or not raw.strip():
        raise ValueError(f"Scene v12 annotation {label} must be a nonempty CSS color")
    return raw


def _annotation_allowed_style(kind: str, wrapped: bool, labelled: bool) -> set[str]:
    keys = (
        "color",
        "opacity",
        "width",
        "dash",
        "linecap",
        "stroke_color",
        "stroke_width",
        "label_color",
        "label_opacity",
        "label_background",
        "label_border_color",
        "label_border_width",
    )
    return {
        key for key in keys if _native.scene_annotation_style_admit(kind, wrapped, labelled, key)
    }


def _validate_xyaf_annotation_style(annotation: dict[str, Any]) -> None:
    """Fail closed on style keys the Scene admit table rejects (matches legacy _pack_xyaf)."""
    kind, style, wrapped, labelled, _kind_label = _xyaf_dispatch(annotation)
    skip_style = {"markup"} | _ANNOTATION_TYPOGRAPHY_STYLE_KEYS
    if kind in {"text", "marker"}:
        skip_style = skip_style | {"rotation"}
    unsupported = sorted(
        key
        for key, value in style.items()
        if key not in skip_style
        and value is not None
        and not _native.scene_annotation_style_admit(kind, wrapped, labelled, str(key))
    )
    if unsupported:
        if wrapped:
            raise UnsupportedSceneV3(f"Scene wrapped annotations do not encode {unsupported!r}")
        if kind == "arrow":
            raise UnsupportedSceneV3(f"Scene arrow style does not encode {unsupported!r}")
        if kind == "callout":
            raise UnsupportedSceneV3(f"Scene callout style does not encode {unsupported!r}")
        if kind == "text":
            raise UnsupportedSceneV3(
                "Scene v23 text annotations support only color, opacity, label_background, and label_border_*"
            )
        raise UnsupportedSceneV3(
            f"Scene v12 {kind} annotation style does not encode {unsupported!r}"
        )


def _xyaf_dispatch(annotation: dict[str, Any]) -> tuple[str, dict[str, Any], bool, bool, str]:
    kind = str(annotation.get("kind", ""))
    style = dict(annotation.get("style") or {})
    authored_wrap = kind in {"text", "callout"} and "wrap" in annotation
    layout_text = kind == "text" and any(
        key in annotation for key in ("dx", "dy", "anchor", "rotation")
    )
    dispatch = _native.scene_xyaf_annotation_dispatch_plan(
        kind=kind,
        authored_wrap=authored_wrap,
        layout_text=layout_text,
    )
    wrapped = bool(dispatch["wrapped"])
    labelled = annotation.get("text") not in (None, "")
    kind_label = "wrapped" if wrapped else kind
    return kind, style, wrapped, labelled, kind_label


def _validate_xyaf_annotation_values(annotation: dict[str, Any]) -> None:
    """Fail closed on authored annotation geometry/style values (matches legacy _pack_xyaf)."""
    kind, style, wrapped, labelled, kind_label = _xyaf_dispatch(annotation)
    if kind == "arrow" and labelled:
        raise UnsupportedSceneV3("Scene arrows do not encode text or class_name")
    required = {
        "arrow": (
            ("x0", "arrow x0"),
            ("y0", "arrow y0"),
            ("x1", "arrow x1"),
            ("y1", "arrow y1"),
        ),
        "callout": (("x", "callout x"), ("y", "callout y")),
        "text": (("x", "text x"), ("y", "text y")),
        "rule": (("value", "rule value"),),
        "band": (("start", "band start"), ("end", "band end")),
        "marker": (("x", "marker x"), ("y", "marker y")),
    }.get(kind, ())
    if wrapped:
        required = (("x", "wrapped x"), ("y", "wrapped y"))
    for key, label in required:
        _annotation_number(annotation, key, None, label)
    for key, label in (
        ("dx", "wrapped dx" if wrapped else "callout dx"),
        ("dy", "wrapped dy" if wrapped else "callout dy"),
        ("size", "marker size"),
    ):
        if key in annotation:
            value = _annotation_number(annotation, key, None, label)
            if kind == "marker" and key == "size" and (not np.isfinite(value) or value <= 0):
                raise ValueError("Scene v12 marker annotation size must be finite and positive")
    if kind == "text" and "rotation" in annotation:
        rotation = _annotation_number(annotation, "rotation", None, "text rotation")
        if not np.isfinite(rotation):
            raise ValueError("Scene v16 text annotation rotation must be finite")
    if kind == "marker" and "rotation" in annotation:
        rotation = _annotation_number(annotation, "rotation", None, "marker rotation")
        if not np.isfinite(rotation):
            raise ValueError("Scene v16 marker annotation rotation must be finite")
    if kind in {"rule", "band"}:
        axis_name = annotation.get("axis")
        if axis_name not in {"x", "y"}:
            raise ValueError(f"Scene v12 {kind} annotation axis must be 'x' or 'y'")
    if kind == "marker" and "symbol" in annotation:
        symbol_name = annotation.get("symbol")
        if not isinstance(symbol_name, str):
            raise ValueError("Scene v12 annotation marker symbol must be a supported string name")
        if symbol_name not in _SYMBOL_CODES:
            raise UnsupportedSceneV3(f"Scene v12 does not support marker symbol {symbol_name!r}")
    if "anchor" in annotation or kind == "callout" or wrapped:
        anchor_name = annotation.get("anchor", "start")
        if anchor_name not in {"start", "middle", "end"}:
            raise UnsupportedSceneV3(
                "Scene wrapped annotation anchor must be start, middle, or end"
                if wrapped
                else "Scene callout anchor must be start, middle, or end"
            )
    for key in (
        "color",
        "stroke_color",
        "label_color",
        "label_background",
        "label_border_color",
    ):
        if key in style:
            _annotation_color(style, key, "", f"{kind_label} {key.replace('_', ' ')}")
    if "opacity" in style:
        opacity = _annotation_number(style, "opacity", None, f"{kind_label} opacity")
        if not np.isfinite(opacity) or not 0.0 <= opacity <= 1.0:
            if kind == "arrow":
                raise ValueError("Scene arrow opacity must be in [0, 1] and width must be positive")
            if wrapped:
                raise ValueError("Scene wrapped annotation opacity must be in [0, 1]")
            if kind == "callout":
                raise ValueError(
                    "Scene callout opacity must be in [0, 1] and width must be positive"
                )
            raise ValueError(f"Scene v12 {kind} annotation opacity must be finite and in [0, 1]")
    if "width" in style:
        width = _annotation_number(style, "width", None, f"{kind_label} width")
        if kind in {"arrow", "callout"} and (not np.isfinite(width) or width <= 0):
            raise ValueError(
                "Scene arrow opacity must be in [0, 1] and width must be positive"
                if kind == "arrow"
                else "Scene callout opacity must be in [0, 1] and width must be positive"
            )
        if kind == "rule" and (not np.isfinite(width) or width <= 0):
            raise ValueError("Scene v12 rule annotation width must be finite and nonnegative")
    if "stroke_width" in style:
        stroke_width = _annotation_number(style, "stroke_width", None, f"{kind} width")
        if not np.isfinite(stroke_width) or stroke_width < 0:
            raise ValueError(f"Scene v12 {kind} annotation width must be finite and nonnegative")
    if "label_opacity" in style:
        label_opacity = _annotation_number(style, "label_opacity", None, f"{kind} label opacity")
        if not np.isfinite(label_opacity) or not 0.0 <= label_opacity <= 1.0:
            raise ValueError(
                f"Scene v16 {kind} annotation label opacity must be finite and in [0, 1]"
            )
    if "label_border_width" in style:
        border_width = _annotation_number(
            style, "label_border_width", None, f"{kind_label} label border width"
        )
        if not np.isfinite(border_width) or border_width <= 0:
            raise ValueError("Scene v23 label border width must be positive and finite")


def _raise_xyaf_bulk_error(error: _native.SceneXyafBulkPackError, annotations: list[Any]) -> None:
    code = int(error.code)
    index = int(error.index)
    annotation = annotations[index] if 0 <= index < len(annotations) else {}
    kind = str(annotation.get("kind", ""))
    if code == -3:
        raise UnsupportedSceneV3(
            f"Scene v12 annotations support rule, band, and unlabeled marker only; {kind!r} is deferred"
        )
    if code == -7:
        raise UnsupportedSceneV3("Scene arrows do not encode text or class_name")
    if code == -5:
        if kind == "callout":
            raise UnsupportedSceneV3("Scene callouts require nonempty NUL-free text")
        if kind == "text":
            raise UnsupportedSceneV3("Scene v16 text annotations require nonempty NUL-free text")
        raise UnsupportedSceneV3("Scene v16 annotation labels require nonempty NUL-free text")
    if code == -4:
        raise UnsupportedSceneV3(
            "Scene v23 text annotations support only color, opacity, label_background, and label_border_*"
            if kind == "text"
            else f"Scene v12 {kind} annotation style does not encode unsupported keys"
        )
    if code == -8:
        raise UnsupportedSceneV3("Scene v12 rule annotation dash is not a constant pattern")
    if code == -9:
        raise UnsupportedSceneV3("Scene v12 rule annotation linecap is not a Scene cap")
    if code == -10:
        symbol_name = str(annotation.get("symbol", "circle"))
        raise UnsupportedSceneV3(f"Scene v12 does not support marker symbol {symbol_name!r}")
    if code == -11:
        raise UnsupportedSceneV3("Scene callout anchor must be start, middle, or end")
    if code == -12:
        raise UnsupportedSceneV3("Scene v23 label border requires color and width")
    if code == -13:
        raise ValueError(f"Scene v12 {kind} annotation axis must be 'x' or 'y'")
    if code == -6:
        style = dict(annotation.get("style") or {})
        if "label_opacity" in style:
            raise ValueError(
                f"Scene v16 {kind} annotation label opacity must be finite and in [0, 1]"
            )
        if "opacity" in style:
            raise ValueError(f"Scene v12 {kind} annotation opacity must be finite and in [0, 1]")
        if "label_border_width" in style:
            raise ValueError("Scene v23 label border width must be positive and finite")
        if "width" in style and kind == "rule":
            raise ValueError("Scene v12 rule annotation width must be finite and nonnegative")
        raise ValueError(f"Scene v12 annotation values are invalid at index {index}")
    raise ValueError("invalid scene annotation packing")


def _pack_xyaf_bulk(annotations: list[Any]) -> bytes:
    """Marshal annotations and bulk-pack XYAF via Rust (ABI 324)."""
    if not annotations:
        return b""
    normalized: list[dict[str, Any]] = []
    for annotation in annotations:
        ann = dict(annotation)
        kind = str(ann.get("kind", ""))
        style = dict(ann.get("style") or {})
        if (
            kind in {"text", "marker"}
            and "rotation" not in ann
            and style.get("rotation") is not None
        ):
            ann["rotation"] = style["rotation"]
        _validate_xyaf_annotation_style(ann)
        _validate_xyaf_annotation_values(ann)
        normalized.append(ann)
    try:
        return _native.scene_xyaf_bulk_pack(normalized)
    except _native.SceneXyafBulkPackError as error:
        _raise_xyaf_bulk_error(error, normalized)


def _pack_xyaf(annotation: dict[str, Any], index: int) -> bytes:
    """Pack one authored annotation as XYAF v1 via ``xyg_scene_xyaf_bulk_pack`` (ABI 324).

    Annotation ``class_name`` is an XYFS observation (ABI 165 / #306), not an
    XYAF field. Scene SVG/raster do not encode CSS classes. Product encode
    reports ``XYG_SCENE_UNSUPPORTED_BROWSER_CSS``.
    Annotation ``collision`` is XYFS ``OBS_ANNOTATION_COLLISION`` (#307);
    Scene does not encode annotation collision. Product encode reports
    ``XYG_SCENE_UNSUPPORTED_ANNOTATION_COLLISION``.
    Annotation ``markup`` is XYFS ``OBS_ANNOTATION_MARKUP`` (#308); Scene
    owns literal text only. Product encode reports
    ``XYG_SCENE_UNSUPPORTED_ANNOTATION_MARKUP``.
    Annotation custom typography is XYFS ``OBS_CUSTOM_FONT`` (#309); Scene
    SVG/raster use the built-in default font. Product encode reports
    ``XYG_SCENE_UNSUPPORTED_CUSTOM_FONT``. Text/marker ``style.rotation``
    lifts onto the ABI 187/188 top-level rotation field.
    Annotation ``html`` is XYFS ``OBS_ANNOTATION_HTML`` (#305); Scene SVG/raster
    own literal text only. Product encode reports
    ``XYG_SCENE_UNSUPPORTED_ANNOTATION_HTML``.
    """
    annotation = dict(annotation)
    kind = annotation.get("kind")
    style = dict(annotation.get("style") or {})
    if (
        str(kind) in {"text", "marker"}
        and "rotation" not in annotation
        and style.get("rotation") is not None
    ):
        annotation["rotation"] = style["rotation"]
    try:
        return _native.scene_xyaf_bulk_pack([annotation], indices=[int(index)])
    except _native.SceneXyafBulkPackError as error:
        _raise_xyaf_bulk_error(error, [annotation])


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
        if not isinstance(fill_value, str) or str(fill_value).strip().lower().startswith(
            "linear-gradient("
        ):
            admitted = _admitted_fill_gradient(trace)
            if admitted is None:
                raise UnsupportedSceneV3(
                    f"Scene v12 does not yet encode {trace.kind} non-CSS fills"
                )
            fill_value = _gradient_solid_css(admitted)
        flags |= _MS_HAS_FILL
        fill_b = str(fill_value).encode("utf-8")
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


def _scene_chrome_style(figure: Any) -> bytes:
    """Pack authored chrome literals; Rust owns the 200-byte Scene style."""
    from ._scene_marshal import scene_chrome_style

    return scene_chrome_style(figure)


def _pack_chrome_facts(
    figure: Any,
    *,
    width: int,
    height: int,
    margins: tuple[float, float, float, float] | None,
    colorbar_ok: bool,
) -> bytes:
    """Marshal chrome observations and bulk-pack XYCF via Rust (ABI 321)."""
    from ._scene_marshal import pack_chrome_facts

    return pack_chrome_facts(
        figure,
        width=width,
        height=height,
        margins=margins,
        colorbar_ok=colorbar_ok,
    )


def _rect_extra_flags(style: dict[str, Any], kind: str, polar: bool) -> int:
    """Pack Scene-unsupported rect extras as XYFS v2 trace flags."""
    fill = style.get("fill")
    gradient_fail = (
        isinstance(fill, dict) and _admitted_fill_gradient_from_fill(fill, "#3987e5") is None
    )
    radius = style.get("corner_radius", 0.0)
    if isinstance(radius, (list, tuple)):
        values = [float(value) for value in radius]
        radius_seq = True
    else:
        values = [float(radius)]
        radius_seq = False
    gap = float(style.get("wedge_gap", 0.0) or 0.0)
    return _native.scene_rect_extra_flags(kind, polar, gradient_fail, values, radius_seq, gap)


def _admitted_marker_glyph(glyph: Any) -> bytes | None:
    """Pack a constant scatter marker_glyph, or None when Scene cannot own it.

    ABI 191 admits multi-character UTF-8 up to 64 bytes. Combined marker_path
    stays fail-closed at the caller. Empty, NUL, and newline stay off this path.
    """
    if not isinstance(glyph, str):
        return None
    if not _native.scene_marker_glyph_admit(glyph):
        return None
    return glyph.encode("utf-8")


def _item_widths(trace: Any, n: int) -> bytes | None:
    width_ch = (getattr(trace, "style_channels", None) or {}).get("stroke_width")
    if width_ch is not None:
        values = np.ascontiguousarray(
            np.asarray(getattr(width_ch, "values", None), dtype=np.float64).reshape(-1)
        )
        if not _native.scene_item_widths_admit(values, n, 0.0):
            return None
        return values.tobytes()
    style = getattr(trace, "style", None) or {}
    width = float(style.get("stroke_width", 0.0) or 0.0)
    if not _native.scene_item_widths_admit(None, n, width):
        return None
    return np.full(n, width, dtype=np.float64).tobytes()


def _scatter_point_fill_rgba8(trace: Any) -> bytes | None:
    return _item_fill_rgba8(trace, _scatter_count(trace))


def _scatter_point_stroke_rgba8(trace: Any, fills: bytes) -> bytes | None:
    n = _scatter_count(trace)
    packed = _item_stroke_rgba8(trace, fills, n)
    if packed is None:
        return None
    stroke_ch = getattr(trace, "stroke_ch", None)
    if stroke_ch is not None and getattr(stroke_ch, "mode", None) == "match_fill":
        return packed
    return _item_apply_opacity(trace, packed, n)


def _scatter_point_widths(trace: Any) -> bytes | None:
    return _item_widths(trace, _scatter_count(trace))


def _mesh_face_fill_rgba8(trace: Any) -> bytes | None:
    return _item_fill_rgba8(trace, _mesh_count(trace))


def _mesh_face_stroke_rgba8(trace: Any, fills: bytes) -> bytes | None:
    return _item_stroke_rgba8(trace, fills, _mesh_count(trace))


def _mesh_face_widths(trace: Any) -> bytes | None:
    return _item_widths(trace, _mesh_count(trace))


def _pack_xyta_colormap(style: dict[str, Any]) -> tuple[int, bytes, bytes]:
    colormap = style.get("colormap")
    if isinstance(colormap, str):
        mode = 1
        named = colormap.encode("utf-8")
        stop_rgb = b""
    elif colormap is not None:
        mode = 2
        named = b""
        try:
            stop_rgb = _colormap_stop_bytes(colormap, "heatmap")
        except (TypeError, ValueError, UnsupportedSceneV3):
            stop_rgb = b""
    else:
        mode = 0
        named = b""
        stop_rgb = b""
    return _native.scene_xyta_colormap_pack(mode, named, stop_rgb)


def _marshal_xyta_trace_record(trace: Any, figure: Any, *, polar: bool) -> bytes:
    """Marshal one attach trace and pack an XYTA record via Rust (ABI 323→318)."""
    from xyg._scene_marshal import marshal_xyta_trace_obs

    obs = marshal_xyta_trace_obs(trace, figure, polar=polar)
    materialized = _native.scene_xyta_trace_observations_materialize(obs)
    return _native.scene_xyta_trace_pack(**materialized)


def _pack_xyta(figure: Any) -> bytes:
    """Pack authored heatmap/density attach facts as XYTA v1; Rust emits XYTT."""
    traces = list(getattr(figure, "traces", None) or [])
    records = bytearray(_XYTA_HEADER.pack(b"XYTA", 1, len(traces), 0))
    figure_plan = _native.scene_xyta_figure_plan(
        polar=str(getattr(figure, "coords", "cartesian") or "cartesian") == "polar"
    )
    polar = figure_plan["polar"]
    for trace in traces:
        records.extend(_marshal_xyta_trace_record(trace, figure, polar=polar))
    return bytes(records)


def _pack_xycl_column(column: np.ndarray | None) -> tuple[int, bytes]:
    if column is None or len(column) == 0:
        return 0, b""
    arr = np.ascontiguousarray(np.asarray(column, dtype=np.float64).reshape(-1))
    return int(arr.size), arr.tobytes()


def _pack_xycl(figure: Any) -> bytes:
    """Pack authored kind/coords/id plus canonical columns as XYCL v1."""
    traces = list(getattr(figure, "traces", None) or [])
    figure_plan = _native.scene_xycl_figure_plan(
        polar=str(getattr(figure, "coords", "cartesian") or "cartesian") == "polar"
    )
    coords = 1 if figure_plan["polar"] else 0
    records = bytearray(_XYCL_HEADER.pack(b"XYCL", 1, len(traces), 0))
    for trace in traces:
        kind = str(trace.kind).encode("utf-8")
        packed = [
            _pack_xycl_column(_trace_column(trace, name))
            for name in ("x", "y", "x0", "y0", "x1", "y1", "base")
        ]
        records.extend(
            _XYCL_PREFIX.pack(
                len(kind),
                coords,
                0,
                int(trace.id),
                *(count for count, _payload in packed),
            )
        )
        records.extend(kind)
        for _count, payload in packed:
            records.extend(payload)
    return bytes(records)


def _pack_xynm(figure: Any) -> bytes:
    """Pack authored legend names as XYNM v1; Rust owns legend-name gating."""
    traces = list(getattr(figure, "traces", None) or [])
    _native.scene_xynm_figure_plan(show_legend=bool(getattr(figure, "show_legend", True)))
    records = bytearray(_XYNM_HEADER.pack(b"XYNM", 1, len(traces), 0))
    for trace in traces:
        name = getattr(trace, "name", None)
        raw = b"" if name is None else str(name).encode("utf-8")
        records.extend(_XYNM_PREFIX.pack(len(raw)))
        records.extend(raw)
    return bytes(records)


def _pack_xyhp(planes: list[bytes]) -> bytes:
    """Wrap painted-heatmap planes in an XYHP v1 envelope."""
    if not planes:
        return b""
    return struct.pack("<4sIII", b"XYHP", 1, len(planes), 0) + b"".join(planes)


def _parse_scene_linecap(value: Any) -> int | None | bool:
    """Return 0=butt or 2=square, None for round/omitted, False if unusable."""
    if value is None:
        return None
    name = str(value)
    if not name.strip():
        return False
    return _native.scene_linecap_admit(name)


_XYSS_HAS_DASH = 1 << 0
_XYSS_HAS_CAP = 1 << 1
_XYSS_HAS_MARKER = 1 << 2
_XYSS_HAS_GRAD = 1 << 3


def _pack_xyss(
    dashes: list[list[float] | None],
    linecaps: list[int | None],
    marker_paths: list[dict[str, Any] | None],
    fill_gradients: list[dict[str, Any] | None],
) -> bytes:
    """Pack authored dash/linecap/marker_path/gradient facts as XYSS v1."""
    n_records = max(len(dashes), len(linecaps), len(marker_paths), len(fill_gradients), 0)
    records: list[bytes] = []
    for index in range(n_records):
        pattern = dashes[index] if index < len(dashes) else None
        cap = linecaps[index] if index < len(linecaps) else None
        path = marker_paths[index] if index < len(marker_paths) else None
        gradient = fill_gradients[index] if index < len(fill_gradients) else None
        flags = 0
        dash_count = 0
        dash_values = [0.0] * 8
        linecap = 255
        n_contours = 0
        n_stops = 0
        grad_dir = 0
        plot_space = 0
        filled = 0
        remainder = bytearray()
        if pattern:
            flags |= _XYSS_HAS_DASH
            dash_count = len(pattern)
            for offset, value in enumerate(pattern):
                dash_values[offset] = float(value)
        if cap in (0, 2):
            flags |= _XYSS_HAS_CAP
            linecap = int(cap)
        if path:
            flags |= _XYSS_HAS_MARKER
            contours = path["contours"]
            n_contours = len(contours)
            filled = 1 if path.get("filled", True) else 0
            for contour in contours:
                values = [float(value) for value in contour]
                remainder.extend(struct.pack("<II", len(values) // 2, 0))
                remainder.extend(struct.pack(f"<{len(values)}d", *values))
        if gradient:
            flags |= _XYSS_HAS_GRAD
            stops = gradient["stops"]
            n_stops = len(stops)
            grad_dir = _native.scene_gradient_dir(gradient["dir"])
            plot_space = 1 if _native.scene_gradient_space(gradient.get("space")) == 1 else 0
            for t, rgba in stops:
                remainder.extend(struct.pack("<f4B", float(t), rgba[0], rgba[1], rgba[2], rgba[3]))
        if not flags:
            continue
        records.append(
            struct.pack(
                "<IBBBBBBBBI8f",
                int(index),
                flags,
                dash_count,
                linecap,
                n_contours,
                n_stops,
                grad_dir,
                plot_space,
                filled,
                0,
                *dash_values,
            )
            + bytes(remainder)
        )
    if not records:
        return b""
    out = bytearray(struct.pack("<4sIII", b"XYSS", 1, len(records), 0))
    for record in records:
        out.extend(record)
    return bytes(out)


def _ribbon_color2_gradient_spec(trace: Any) -> dict[str, Any] | None:
    if _classify_ribbon_color2(trace) != "gradient":
        return None
    target = _channel_constant_css(getattr(trace, "color2_ch", None))
    if target is None:
        return None
    return {
        "space": "mark",
        "dir": "right",
        "stops": [(0.0, _trace_source_color_css(trace)), (1.0, target)],
    }


def _gradient_solid_css(gradient: dict[str, Any]) -> str:
    packed: list[int] = []
    for _t, rgba in gradient["stops"]:
        packed.extend((int(rgba[0]), int(rgba[1]), int(rgba[2]), int(rgba[3])))
    css = _native.scene_gradient_solid_css(packed)
    return "rgb(0,0,0)" if css is None else css


_XYTC_HEADER = struct.Struct("<4sIII")
_XYTR_PREFIX = struct.Struct("<4s2HI2H11d12H3I2df")
_XYTA_HEADER = struct.Struct("<4sIII")
_XYTA_PREFIX = struct.Struct("<II2i8I4H6d2f16x")
_XYCL_HEADER = struct.Struct("<4sIII")
_XYCL_PREFIX = struct.Struct("<HBxIQ7I4x")
_XYNM_HEADER = struct.Struct("<4sIII")
_XYNM_PREFIX = struct.Struct("<H")
_XYTA_HEATMAP = 1 << 0
_XYTA_DENSITY = 1 << 1
_XYTA_HAS_RGBA = 1 << 2
_XYTA_HAS_RGBA_GRID = 1 << 3
_XYTA_HAS_GRID = 1 << 4
_XYTA_TRUECOLOR = 1 << 5
_XYTA_HAS_NAMED_CMAP = 1 << 6
_XYTA_HAS_STOPS = 1 << 7
_XYTA_HAS_COLOR_CH = 1 << 8
_XYTA_HAS_STYLE_COLOR = 1 << 9
_XYTA_HAS_OPACITY = 1 << 10
_XYTA_HAS_FILL_OPACITY = 1 << 11
_XYTA_HAS_DOMAIN = 1 << 12
_XYTA_SHAPE = 1 << 13
_XYTA_RIBBON_ENDS = 1 << 14
_XYTA_MESH_FACES = 1 << 15
_XYTA_SCATTER_PAINT = 1 << 16
_XYTC_HAS_FILL = 1 << 0
_XYTC_HAS_STROKE = 1 << 1
_XYTC_HAS_LINE_COLOR = 1 << 2
_XYTC_HAS_STROKE_WIDTH = 1 << 3
_XYTC_HAS_WIDTH = 1 << 4
_XYTC_HAS_LINE_WIDTH = 1 << 5
_XYTC_HAS_SIZE = 1 << 6
_XYTC_HAS_SIZE_CH = 1 << 7
_XYTC_HAS_HEX = 1 << 8
_XYTC_PERIMETER_TRUE = 1 << 9
_XYTC_PERIMETER_INVALID = 1 << 10
_XYTC_COLOR_CH = 1 << 11
_XYTC_COLOR_CH_CONSTANT = 1 << 12
_XYTC_COLOR2 = 1 << 13
_XYTC_USE_DENSITY = 1 << 14
_XYTC_SHOW_LEGEND = 1 << 15
_XYTC_HAS_NAME = 1 << 16
_XYTC_HAS_DASH_PATTERN = 1 << 17
_XYTC_HAS_MARKER = 1 << 18
_XYTC_HAS_GRADIENT_SPEC = 1 << 19
_XYTC_HAS_FILL_DICT = 1 << 20
_XYTC_HAS_CORNER_RADIUS = 1 << 22
_XYTC_HAS_WEDGE_GAP = 1 << 23
_XYTC_HAS_GLYPH = 1 << 24
_XYTC_JOINED_FILL = 1 << 25


def _pack_marker_blob(value: Any) -> bytes | None:
    if not isinstance(value, dict):
        return None
    contours = value.get("contours")
    if not isinstance(contours, (list, tuple)):
        return None
    values: list[float] = []
    lens: list[int] = []
    try:
        for contour in contours:
            if not isinstance(contour, (list, tuple)):
                return None
            floats = [float(item) for item in contour]
            values.extend(floats)
            lens.append(len(floats))
    except (TypeError, ValueError):
        return None
    filled = 1 if value.get("filled", True) else 0
    return _native.scene_marker_blob_pack(filled, values, lens)


def _pack_gradient_spec(fill: dict[str, Any]) -> bytes | None:
    stops = fill.get("stops")
    if not isinstance(stops, (list, tuple)):
        return None
    stop_t: list[float] = []
    css_parts: list[bytes] = []
    css_lens: list[int] = []
    try:
        for stop in stops:
            if not isinstance(stop, (list, tuple)) or len(stop) != 2:
                return None
            stop_t.append(float(stop[0]))
            css = str(stop[1]).encode("utf-8")
            css_parts.append(css)
            css_lens.append(len(css))
    except (TypeError, ValueError):
        return None
    space = fill.get("space")
    dir_ = fill.get("dir")
    return _native.scene_gradient_spec_pack(
        b"" if space is None else str(space).encode("utf-8"),
        b"" if dir_ is None else str(dir_).encode("utf-8"),
        stop_t,
        b"".join(css_parts),
        css_lens,
    )


_COLOR2_CLASS_TO_CODE = {
    "absent": 0,
    "solid": 1,
    "gradient": 2,
    "ends": 3,
    "fail": 4,
}


def _xytc_fill_kind(style: dict[str, Any]) -> int:
    if "fill" not in style:
        return 0
    fill = style["fill"]
    if isinstance(fill, str):
        return 1
    if isinstance(fill, dict) and {"space", "dir", "stops"} <= set(fill):
        return 2
    if isinstance(fill, dict):
        return 3
    return 1


def _marshal_xytc_trace_record(trace: Any, *, show_legend: bool) -> bytes:
    """Marshal one trace and pack an XYTR record via Rust (ABI 317)."""
    from xyg._scene_marshal import marshal_xytc_trace_obs

    obs = marshal_xytc_trace_obs(trace, show_legend=show_legend)
    materialized = _native.scene_xytc_trace_observations_materialize(obs)
    return _native.scene_xytc_trace_pack(**materialized)


def _pack_xytc(figure: Any) -> bytes:
    """Pack authored per-trace style literals as XYTC v1; Rust compiles XYTO."""
    traces = list(getattr(figure, "traces", None) or [])
    records = bytearray(_XYTC_HEADER.pack(b"XYTC", 1, len(traces), 0))
    figure_plan = _native.scene_xytc_figure_plan(
        show_legend=bool(getattr(figure, "show_legend", True))
    )
    show_legend = figure_plan["show_legend"]
    for trace in traces:
        records.extend(_marshal_xytc_trace_record(trace, show_legend=show_legend))
    return bytes(records)


def _raise_trace_compile(error: _native.SceneTraceCompileError, figure: Any) -> NoReturn:
    traces = list(getattr(figure, "traces", None) or [])
    trace = traces[error.index] if 0 <= error.index < len(traces) else None
    style = getattr(trace, "style", None) or {} if trace is not None else {}
    if error.code == -5:
        raise ValueError("trace opacity must be finite and in [0, 1]") from error
    if error.code == -12:
        raise ValueError("trace opacity channels must be finite and in [0, 1]") from error
    if error.code == -6:
        symbol = str(style.get("symbol", "circle"))
        raise UnsupportedSceneV3(f"Scene v12 does not support scatter symbol {symbol!r}") from error
    if error.code == -7:
        raise UnsupportedSceneV3(
            f"Scene v12 does not support step mode {style.get('step')!r}"
        ) from error
    if error.code == -8:
        raise UnsupportedSceneV3("Scene v25 area stroke_perimeter must be a boolean") from error
    if error.code == -9:
        raise UnsupportedSceneV3(
            "Scene v12 hexbin requires finite hex_dx/hex_dy cell pitch"
        ) from error
    if error.code == -10:
        raise UnsupportedSceneV3(
            "Scene v12 does not yet encode two-ended ribbon gradients"
        ) from error
    if error.code == -11:
        kind = getattr(trace, "kind", "mark") if trace is not None else "mark"
        raise UnsupportedSceneV3(f"Scene v12 does not yet encode {kind} non-CSS fills") from error
    if error.code == -13:
        raise UnsupportedSceneV3(
            "Scene v12 does not yet support data-driven paint channels"
        ) from error
    if error.code == -2:
        raise ValueError("invalid scene trace compile facts version") from error
    raise ValueError("invalid scene trace compile packing") from error


def _raise_trace_attach(error: _native.SceneTraceAttachError, figure: Any) -> NoReturn:
    if error.code == -5:
        raise UnsupportedSceneV3("Scene v12 heatmap requires a rows x cols grid_shape") from error
    if error.code == -6:
        raise UnsupportedSceneV3("Scene v12 heatmap requires a positive grid_shape") from error
    if error.code == -7:
        raise ValueError("heatmap Scene v12 compilation requires a scalar grid") from error
    if error.code == -8:
        raise UnsupportedSceneV3("Scene v12 heatmap grid must match rows x cols") from error
    if error.code == -9:
        raise UnsupportedSceneV3(
            "Scene v12 does not yet encode missing-data breaks or nonfinite coordinates"
        ) from error
    if error.code == -10:
        raise UnsupportedSceneV3("Scene heatmap RGBA plane must match rows x cols") from error
    if error.code == -11:
        raise UnsupportedSceneV3("Scene heatmap truecolor requires four RGBA planes") from error
    if error.code == -12:
        traces = list(getattr(figure, "traces", None) or [])
        trace = traces[error.index] if 0 <= error.index < len(traces) else None
        label = "density" if getattr(trace, "kind", None) == "scatter" else "heatmap"
        raise UnsupportedSceneV3(f"Scene {label} colormap requires RGB stops") from error
    if error.code == -13:
        raise ValueError("Scene density columns must have equal length") from error
    if error.code == -14:
        raise ValueError("Scene density mean-color source is invalid") from error
    if error.code == -2:
        raise ValueError("invalid scene trace attach facts version") from error
    raise ValueError("invalid scene trace attach packing") from error


def _raise_trace_rows(error: _native.SceneTraceRowsError) -> NoReturn:
    if error.code == -5:
        raise UnsupportedSceneV3(
            "Scene v12 does not yet encode missing-data breaks or nonfinite coordinates"
        ) from error
    if error.code == -6:
        raise UnsupportedSceneV3("Scene v12 does not support product kind") from error
    if error.code == -1:
        raise UnsupportedSceneV3("invalid scene trace packing") from error
    if error.code == -2:
        raise ValueError("invalid scene trace column facts version") from error
    raise ValueError("invalid scene trace column packing") from error


def _raise_trace_sidecars(error: _native.SceneTraceSidecarsError) -> NoReturn:
    if error.code == -2:
        raise ValueError("invalid scene sidecar facts version") from error
    raise ValueError("invalid scene sidecar packing") from error


def _raise_annotation_splice(error: _native.SceneAnnotationSpliceError) -> NoReturn:
    if error.code == -2:
        raise ValueError("invalid scene annotation splice version") from error
    raise ValueError("invalid scene annotation splice packing") from error


def figure_scene(
    figure: Any,
    *,
    width: int | None = None,
    height: int | None = None,
    margins: tuple[float, float, float, float] | None = None,
) -> bytes:
    """Compile migrated cartesian marks plus x/y axes to Scene v12."""
    annotations = list(getattr(figure, "annotations", None) or [])
    colorbar_unsupported = False
    try:
        _colorbar_input(figure)
    except UnsupportedSceneV3:
        colorbar_unsupported = True

    polar = str(getattr(figure, "coords", "cartesian") or "cartesian") == "polar"
    attach_plan = _native.scene_encode_product_attach_plan(polar=polar)

    # Hosts pack XYTC, XYTA, XYNM, XYCL, XYAF, XYCF, polar, and XYFS; Rust owns
    # compile, attach, sidecars, rows, annotation facts, style sidecars,
    # splice, XYCC/extras packing, viewport/axis scalars, assembled encode,
    # and the figure-compile support probe (ABI 165). Earlier ABIs 148–164
    # remain available for tests. Empty XYFS skips the probe.
    x_span = tuple(float(value) for value in figure._range("x"))
    y_span = tuple(float(value) for value in figure._range("y"))
    x_domain = (x_span[0], x_span[1])
    y_domain = (y_span[0], y_span[1])
    annotation_facts = _pack_xyaf_bulk(annotations)
    w = int(width if width is not None else figure.width)
    h = int(height if height is not None else figure.height)
    try:
        return _native.scene_encode_product(
            compile_facts=_pack_xytc(figure),
            attach_facts=_pack_xyta(figure),
            names=_pack_xynm(figure),
            columns=_pack_xycl(figure),
            annotation_facts=annotation_facts,
            style_ref_base=len(figure.traces),
            x_domain=x_domain,
            y_domain=y_domain,
            chrome_facts=_pack_chrome_facts(
                figure,
                width=w,
                height=h,
                margins=margins,
                colorbar_ok=not colorbar_unsupported,
            ),
            polar=_pack_polar_scene_input(figure) if attach_plan["attach_xypl"] else b"",
            figure_support=_pack_figure_support(figure, annotations, colorbar_unsupported),
        )
    except _native.SceneFigureSupportError as error:
        raise UnsupportedSceneV3(str(error)) from error
    except _native.SceneTraceCompileError as error:
        _raise_trace_compile(error, figure)
    except _native.SceneTraceAttachError as error:
        _raise_trace_attach(error, figure)
    except _native.SceneTraceSidecarsError as error:
        _raise_trace_sidecars(error)
    except _native.SceneTraceRowsError as error:
        _raise_trace_rows(error)
    except _native.SceneAnnotationFactsError as error:
        raise UnsupportedSceneV3(str(error)) from error
    except _native.SceneStyleSidecarsError as error:
        if error.code == -2:
            raise ValueError("invalid scene style sidecar facts version") from error
        raise ValueError("invalid scene style sidecar packing") from error
    except _native.SceneAnnotationSpliceError as error:
        _raise_annotation_splice(error)
    except _native.SceneEncodeAssembledError as error:
        raise ValueError("invalid canonical scene batch") from error
    except ValueError as error:
        message = str(error)
        if message.startswith(("Scene v12 ", "Scene v19 ")):
            raise UnsupportedSceneV3(message) from error
        raise


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
    quality: int | None = None,
) -> bytes | None:
    """Render one supported public static format from the canonical Scene.

    This is the only selection seam for the migrated public SVG/PNG/PDF/JPEG/WebP
    subset.  It returns ``None`` only after the explicit support predicate
    selects compatibility *before* Scene compilation.  Once selected, every
    compiler or consumer error propagates: it is never a request to retry a
    compatibility renderer. The router reuses the predicate's compiled batch
    rather than compiling a second Scene for SVG, raster, or PDF consumers.
    Format dispatch is ABI 164 ``scene_static_export``. Explicit Scene callers
    still use ``figure_svg`` / ``figure_raster_commands``.
    """
    reason, scene = _public_scene_or_reason(figure, width=width, height=height)
    if reason is not None or scene is None:
        return None
    w = int(width if width is not None else figure.width)
    h = int(height if height is not None else figure.height)
    width_px = max(1, int(round(w * float(scale))))
    height_px = max(1, int(round(h * float(scale))))
    return _native.scene_static_export(
        scene,
        format,
        scale=scale,
        width=width_px,
        height=height_px,
        quality=90 if quality is None else int(quality),
    )


def _pack_polar_scene_input(figure: Any) -> bytes:
    """Marshal polar axis literals and pack XYPL via Rust (ABI 322)."""
    from ._scene_marshal import pack_polar_scene_input

    return pack_polar_scene_input(figure)


def _pack_figure_support(
    figure: Any,
    annotations: list[Any],
    colorbar_unsupported: bool,
) -> bytes:
    """Marshal figure support observations and materialize XYFS via Rust (ABI 322)."""
    from ._scene_marshal import pack_figure_support

    return pack_figure_support(figure, annotations, colorbar_unsupported)


def _public_scene_or_reason(
    figure: Any,
    *,
    width: int | None = None,
    height: int | None = None,
) -> tuple[str | None, bytes | None]:
    """Compile the public Scene once, or return the support diagnostic.

    The predicate must still compile so it cannot disagree with the encoder.
    Product routers reuse the compiled batch instead of encoding a second time.
    """
    envelope = _pack_public_export_support(figure, width=width, height=height)
    reason = _native.scene_public_export_reason(envelope)
    if reason:
        return reason, None
    try:
        scene = figure_scene(figure, width=width, height=height)
    except UnsupportedSceneV3 as unsupported:
        if str(unsupported) == "invalid canonical scene plot layout":
            return "XYG_SCENE_UNSUPPORTED_VIEWPORT", None
        return str(unsupported), None
    except ValueError as exc:
        if str(exc) == "invalid canonical scene plot layout":
            return "XYG_SCENE_UNSUPPORTED_VIEWPORT", None
        raise
    return None, scene


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

    Hosts pack authored XYEF facts (viewport flags, keys, axis codes, and
    column observations). Rust owns XYEP layout, kind/step/annotation codes,
    flag derivation, allowlists, check order, the public PolyFill group budget,
    and diagnostic wording. After that preflight the predicate still compiles
    the Scene so it cannot disagree with the encoder. ``public_static_export``
    and facet SVG/raster reuse that compiled batch rather than compiling a second
    Scene.
    """
    return _public_scene_or_reason(figure, width=width, height=height)[0]
