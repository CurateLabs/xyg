"""Thin figure-to-Scene v12 compiler for the migrated core-mark subset.

Rust owns mapping, clipping, record semantics, SVG construction, and raster
display-list construction. This module only projects already-validated Figure
objects into the typed ABI and rejects features whose canonical Scene record
does not exist yet.
"""

from __future__ import annotations

import math
import struct
from typing import Any

import numpy as np

from . import _native, _validate, channels
from .marks import _SYMBOL_CODES, _validated_marker_path

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
# Painted lattices (`HeatmapPainted`) add an XYHP sidecar; Rust tessellates
# cells and interns unique fills. Polar encode maps those Rects to PolyFill.
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
_XYFS_TRACE_UNSUPPORTED_KIND = 1 << 0
_XYFS_TRACE_NON_PRIMARY_AXIS = 1 << 1
_XYFS_TRACE_HIDDEN_OR_PER_ITEM = 1 << 2
_XYFS_TRACE_DENSITY = 1 << 3  # ABI 143 no longer sets this for polar density
_XYFS_TRACE_DASHED_MARKERS = 1 << 4
_XYFS_TRACE_RECT_GRADIENT = 1 << 5
_XYFS_TRACE_CORNER_RADIUS = 1 << 6
_XYFS_TRACE_WEDGE_GAP = 1 << 7
_XYFS_TRACE_JOINED_FILL = 1 << 8
_XYFS_TRACE_CUSTOM_HEX_REDUCE = 1 << 9
_XYFS_TRACE_HEATMAP_COLORMAP = 1 << 10
_XYFS_TRACE_NON_CSS_FILL = 1 << 11
_SCENE_DASH_PRESETS: dict[str, list[float] | None] = {
    "solid": None,
    "dashed": [6.0, 4.0],
    "dotted": [1.5, 3.0],
    "dashdot": [6.0, 3.0, 1.5, 3.0],
}

# Each unjoined triangle or hex cell is one PolyFill group in the Rust browser
# painter. Keep the public route inside its canonical group budget; larger
# meshes and honeycombs remain on the compatibility path until Scene gains a
# compact multi-cell painter record.
_MAX_PUBLIC_TRIANGLE_MESHES = 1024
# Regular heatmap cells are ordinary Rect records and share the histogram
# 10,000-bin public ceiling. Irregular grids stay on the compatibility
# exporters. Scalar-colormap and truecolor heatmaps tessellate those Rects
# with per-cell literal styles (polar encode then maps Rects to PolyFill
# annular sectors).
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


_XYPK_FACT_STROKE_PERIMETER = 1
_XYPK_FACT_CURVE_SMOOTH = 2
_XYPK_FACT_DENSITY_PLANE = 4
_XYPK_FACT_HEATMAP_PAINT = 8

_XYHF_HEADER = struct.Struct("<4sIQIIIB3x4d")
_XYHF_FAMILY_HEATMAP = 0
_XYHF_FAMILY_DENSITY = 1
_XYHF_HAS_RGBA = 1 << 0
_XYHF_HAS_RGBA_GRID = 1 << 1
_XYHF_HAS_GRID = 1 << 2
_XYHF_HAS_ENCODED = 1 << 3
_XYHF_HAS_MEAN_RGBA = 1 << 4
_XYHF_HAS_NAMED_CMAP = 1 << 5
_XYHF_HAS_STOPS = 1 << 6
_XYHF_HAS_TRUECOLOR = 1 << 7
_XYHF_HAS_COLOR_CH = 1 << 8
_XYHF_HAS_STYLE_COLOR = 1 << 9
_XYHF_HAS_OPACITY = 1 << 10
_XYHF_HAS_FILL_OPACITY = 1 << 11
_XYHF_HAS_DOMAIN = 1 << 12

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
_XYAO_HEADER = struct.Struct("<4sIIIIIII")
_XYAO_STYLE = struct.Struct("<4s4sdBB6x8f")


class UnsupportedSceneV3(ValueError):
    """The figure uses a feature outside the currently migrated Scene subset."""


def _trace_column(trace: Any, name: str) -> np.ndarray | None:
    """Return one authored f64 column, or None when the host did not set it."""
    value = getattr(trace, name, None)
    if value is None:
        return None
    return np.asarray(getattr(value, "values", value), dtype=np.float64)


def _append_packed(
    kinds: list[int],
    stable_ids: list[int],
    style_refs: list[int],
    diameters: list[float],
    symbols: list[int],
    expansion_modes: list[int],
    coordinates: list[list[float]],
    trace: Any,
    *,
    facts: bytes,
    columns: list[np.ndarray | None] | None = None,
) -> None:
    """Append Rust-packed Scene rows for one product-kind geometry envelope."""
    if columns is None:
        columns = [
            _trace_column(trace, "x"),
            _trace_column(trace, "y"),
            _trace_column(trace, "x0"),
            _trace_column(trace, "y0"),
            _trace_column(trace, "x1"),
            _trace_column(trace, "y1"),
            _trace_column(trace, "base"),
        ]
    try:
        (
            packed_kinds,
            packed_ids,
            packed_refs,
            packed_diameters,
            packed_symbols,
            packed_modes,
            coords,
        ) = _native.scene_pack_product_facts(facts, columns)
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
    allowed = {"color", "opacity"}
    if wrapped:
        return allowed | {"label_background", "label_border_color", "label_border_width"}
    if kind == "arrow":
        return allowed | {"width"}
    if kind in {"callout", "text"}:
        allowed |= {"label_background", "label_border_color", "label_border_width"}
        if kind == "callout":
            allowed.add("width")
        return allowed
    if kind == "rule":
        allowed |= {"width", "dash", "linecap"}
    elif kind == "marker":
        allowed |= {"stroke_color", "stroke_width"}
    if labelled and kind in {"rule", "band", "marker"}:
        allowed |= {
            "label_color",
            "label_opacity",
            "label_background",
            "label_border_color",
            "label_border_width",
        }
    return allowed


def _pack_xyaf(annotation: dict[str, Any], index: int) -> bytes:
    """Pack one authored annotation as XYAF v1; Rust classifies the family."""
    kind = annotation.get("kind")
    kind_code = _XYAF_KIND_CODES.get(str(kind) if kind is not None else "")
    if kind_code is None:
        raise UnsupportedSceneV3(
            f"Scene v12 annotations support rule, band, and unlabeled marker only; {kind!r} is deferred"
        )
    wrapped = kind in {"text", "callout"} and "wrap" in annotation
    attached_text = annotation.get("text")
    labelled = attached_text not in (None, "")
    if annotation.get("class_name") not in (None, ""):
        if kind == "arrow":
            raise UnsupportedSceneV3("Scene arrows do not encode class_name")
        if kind == "callout":
            raise UnsupportedSceneV3("Scene callouts do not encode class_name")
        if wrapped:
            raise UnsupportedSceneV3("Scene wrapped annotations do not encode class_name")
        raise UnsupportedSceneV3("Scene v12 annotations do not encode class_name")
    if kind == "arrow" and labelled:
        raise UnsupportedSceneV3("Scene arrows do not encode text or class_name")
    encoded = b""
    if labelled:
        if not isinstance(attached_text, str) or "\0" in attached_text:
            if wrapped:
                raise UnsupportedSceneV3(
                    "Scene wrapped annotations require nonempty NUL-free LF text"
                )
            if kind == "text":
                raise UnsupportedSceneV3(
                    "Scene v16 text annotations require nonempty NUL-free text"
                )
            if kind == "callout":
                raise UnsupportedSceneV3("Scene callouts require nonempty NUL-free text")
            raise UnsupportedSceneV3("Scene v16 annotation labels require nonempty NUL-free text")
        if wrapped and "\r" in attached_text:
            raise UnsupportedSceneV3("Scene wrapped annotations require nonempty NUL-free LF text")
        encoded = attached_text.encode("utf-8")
        if len(encoded) > 4096:
            if wrapped:
                raise UnsupportedSceneV3(
                    "Scene wrapped annotations are limited to 4,096 UTF-8 bytes"
                )
            if kind == "text":
                raise UnsupportedSceneV3(
                    "Scene v16 text annotations are limited to 4,096 UTF-8 bytes"
                )
            if kind == "callout":
                raise UnsupportedSceneV3("Scene callouts are limited to 4,096 UTF-8 bytes")
            raise UnsupportedSceneV3("Scene v16 annotation labels are limited to 4,096 UTF-8 bytes")
    elif kind in {"text", "callout"}:
        raise UnsupportedSceneV3(
            "Scene callouts require nonempty NUL-free text"
            if kind == "callout"
            else "Scene v16 text annotations require nonempty NUL-free text"
        )
    style = dict(annotation.get("style") or {})
    allowed = _annotation_allowed_style(str(kind), wrapped, labelled)
    unsupported = sorted(
        key for key, value in style.items() if key not in allowed and value is not None
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

    def take_num(source: dict[str, Any], key: str, label: str) -> float:
        return _annotation_number(source, key, None, label)

    nums = [float("nan")] * 18
    facts = 0
    style_bits = 0
    color = stroke = label_color = label_fill = label_border = bytes(4)
    if labelled:
        facts |= _XYAF_FACT_HAS_TEXT
    if wrapped:
        facts |= _XYAF_FACT_HAS_WRAP
        nums[8] = take_num(annotation, "wrap", "wrapped width")
    required = {
        "arrow": (
            ("x0", 2, _XYAF_FACT_HAS_X0, "arrow x0"),
            ("y0", 3, _XYAF_FACT_HAS_Y0, "arrow y0"),
            ("x1", 4, _XYAF_FACT_HAS_X1, "arrow x1"),
            ("y1", 5, _XYAF_FACT_HAS_Y1, "arrow y1"),
        ),
        "callout": (
            ("x", 0, _XYAF_FACT_HAS_X, "callout x"),
            ("y", 1, _XYAF_FACT_HAS_Y, "callout y"),
        ),
        "text": (
            ("x", 0, _XYAF_FACT_HAS_X, "text x"),
            ("y", 1, _XYAF_FACT_HAS_Y, "text y"),
        ),
        "rule": (("value", 9, _XYAF_FACT_HAS_VALUE, "rule value"),),
        "band": (
            ("start", 10, _XYAF_FACT_HAS_START, "band start"),
            ("end", 11, _XYAF_FACT_HAS_END, "band end"),
        ),
        "marker": (
            ("x", 0, _XYAF_FACT_HAS_X, "marker x"),
            ("y", 1, _XYAF_FACT_HAS_Y, "marker y"),
        ),
    }[str(kind)]
    if wrapped:
        required = (
            ("x", 0, _XYAF_FACT_HAS_X, "wrapped x"),
            ("y", 1, _XYAF_FACT_HAS_Y, "wrapped y"),
        )
    for key, slot, flag, label in required:
        nums[slot] = take_num(annotation, key, label)
        facts |= flag
    for key, slot, flag, label in (
        ("dx", 6, _XYAF_FACT_HAS_DX, "wrapped dx" if wrapped else "callout dx"),
        ("dy", 7, _XYAF_FACT_HAS_DY, "wrapped dy" if wrapped else "callout dy"),
        ("size", 12, _XYAF_FACT_HAS_SIZE, "marker size"),
    ):
        if key in annotation:
            nums[slot] = take_num(annotation, key, label)
            facts |= flag
    axis_code = 0
    if str(kind) in {"rule", "band"}:
        axis_name = annotation.get("axis")
        if axis_name not in {"x", "y"}:
            raise ValueError(f"Scene v12 {kind} annotation axis must be 'x' or 'y'")
        axis_code = 1 if axis_name == "x" else 2
        facts |= _XYAF_FACT_HAS_AXIS
    symbol = 0
    if str(kind) == "marker":
        symbol_name = str(annotation.get("symbol", "circle"))
        if symbol_name not in _SYMBOL_CODES:
            raise UnsupportedSceneV3(f"Scene v12 does not support marker symbol {symbol_name!r}")
        symbol = _SYMBOL_CODES[symbol_name]
        if "symbol" in annotation:
            facts |= _XYAF_FACT_HAS_SYMBOL
        if "size" in annotation and (not np.isfinite(nums[12]) or nums[12] <= 0):
            raise ValueError("Scene v12 marker annotation size must be finite and positive")
    anchor = 255
    if "anchor" in annotation or str(kind) == "callout" or wrapped:
        anchor_name = annotation.get("anchor", "start")
        anchor_code = {"start": 0, "middle": 1, "end": 2}.get(anchor_name)
        if anchor_code is None:
            raise UnsupportedSceneV3(
                "Scene wrapped annotation anchor must be start, middle, or end"
                if wrapped
                else "Scene callout anchor must be start, middle, or end"
            )
        anchor = int(anchor_code)
        facts |= _XYAF_FACT_HAS_ANCHOR
    kind_label = "wrapped" if wrapped else str(kind)
    if "opacity" in style:
        nums[13] = take_num(style, "opacity", f"{kind_label} opacity")
        style_bits |= _XYAF_STYLE_OPACITY
        if not np.isfinite(nums[13]) or not 0.0 <= nums[13] <= 1.0:
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
        nums[14] = take_num(style, "width", f"{kind_label} width")
        style_bits |= _XYAF_STYLE_WIDTH
        if kind in {"arrow", "callout"} and (not np.isfinite(nums[14]) or nums[14] <= 0):
            raise ValueError(
                "Scene arrow opacity must be in [0, 1] and width must be positive"
                if kind == "arrow"
                else "Scene callout opacity must be in [0, 1] and width must be positive"
            )
        if kind == "rule" and (not np.isfinite(nums[14]) or nums[14] <= 0):
            raise ValueError("Scene v12 rule annotation width must be finite and nonnegative")
    if "stroke_width" in style:
        nums[15] = take_num(style, "stroke_width", f"{kind} width")
        style_bits |= _XYAF_STYLE_STROKE_WIDTH
        if not np.isfinite(nums[15]) or nums[15] < 0:
            raise ValueError(f"Scene v12 {kind} annotation width must be finite and nonnegative")
    if "label_opacity" in style:
        nums[16] = take_num(style, "label_opacity", f"{kind} label opacity")
        style_bits |= _XYAF_STYLE_LABEL_OPACITY
        if not np.isfinite(nums[16]) or not 0.0 <= nums[16] <= 1.0:
            raise ValueError(
                f"Scene v16 {kind} annotation label opacity must be finite and in [0, 1]"
            )
    if "label_border_width" in style:
        nums[17] = take_num(style, "label_border_width", f"{kind_label} label border width")
        style_bits |= _XYAF_STYLE_LABEL_BORDER_WIDTH
        if not np.isfinite(nums[17]) or nums[17] <= 0:
            raise ValueError("Scene v23 label border width must be positive and finite")
    for key, bit in (
        ("color", _XYAF_STYLE_COLOR),
        ("stroke_color", _XYAF_STYLE_STROKE_COLOR),
        ("label_color", _XYAF_STYLE_LABEL_COLOR),
        ("label_background", _XYAF_STYLE_LABEL_BACKGROUND),
        ("label_border_color", _XYAF_STYLE_LABEL_BORDER_COLOR),
    ):
        if key in style:
            packed = bytes(
                _rgba(
                    _annotation_color(style, key, "", f"{kind_label} {key.replace('_', ' ')}"),
                    1.0,
                )
            )
            style_bits |= bit
            if key == "color":
                color = packed
            elif key == "stroke_color":
                stroke = packed
            elif key == "label_color":
                label_color = packed
            elif key == "label_background":
                label_fill = packed
            else:
                label_border = packed
    border_color_present = style.get("label_border_color") is not None
    border_width_present = style.get("label_border_width") is not None
    if border_color_present != border_width_present:
        raise UnsupportedSceneV3(
            "Scene wrapped label border requires color and width"
            if wrapped
            else "Scene v23 label border requires color and width"
        )
    parsed_dash: list[float] | None = None
    parsed_cap: int | None = None
    if kind == "rule":
        parsed_dash = _parse_scene_dash(style.get("dash"))
        if parsed_dash is False:
            raise UnsupportedSceneV3("Scene v12 rule annotation dash is not a constant pattern")
        if parsed_dash:
            style_bits |= _XYAF_STYLE_DASH
        parsed_cap = _parse_scene_linecap(style.get("linecap"))
        if parsed_cap is False:
            raise UnsupportedSceneV3("Scene v12 rule annotation linecap is not a Scene cap")
        if parsed_cap is not None:
            style_bits |= _XYAF_STYLE_LINECAP
    dash = [0.0] * 8
    dash_count = 0
    if parsed_dash:
        dash_count = len(parsed_dash)
        dash[:dash_count] = [float(value) for value in parsed_dash]
    linecap = 255 if parsed_cap is None else int(parsed_cap)
    return (
        _XYAF_HEADER.pack(
            b"XYAF",
            1,
            int(index),
            int(kind_code),
            int(axis_code),
            int(symbol) & 0xFF,
            int(anchor) & 0xFF,
            int(facts),
            int(style_bits),
            int(linecap) & 0xFF,
            int(dash_count) & 0xFF,
            0,
            len(encoded),
            *[float(value) for value in nums],
            color,
            stroke,
            label_color,
            label_fill,
            label_border,
            0,
            *[float(value) for value in dash],
        )
        + encoded
    )


def _apply_xyao(
    payload: bytes,
    kinds: list[int],
    stable_ids: list[int],
    style_refs: list[int],
    diameters: list[float],
    symbols: list[int],
    expansion_modes: list[int],
    coordinates: list[list[float]],
    styles: list[tuple[tuple[int, ...], tuple[int, ...], float]],
    dashes: list[list[float] | None],
    linecaps: list[int | None],
) -> bytes:
    """Splice XYAO styles and mark rows into the figure Scene arrays."""
    if not payload:
        return b""
    magic, version, n_styles, n_rows, xyad_len, _reserved, _base, _pad = _XYAO_HEADER.unpack_from(
        payload, 0
    )
    if magic != b"XYAO" or version != 1:
        raise ValueError("invalid scene annotation packing")
    at = _XYAO_HEADER.size
    for _ in range(int(n_styles)):
        fill, stroke, width, dash_count, cap, *dash_values = _XYAO_STYLE.unpack_from(payload, at)
        styles.append((tuple(fill), tuple(stroke), float(width)))
        dashes.append(
            [float(value) for value in dash_values[: int(dash_count)]] if dash_count else None
        )
        linecaps.append(None if cap == 255 else int(cap))
        at += _XYAO_STYLE.size
    mark_end = at + int(n_rows) * 56
    mark_bytes = payload[at:mark_end]
    xyad = payload[mark_end : mark_end + int(xyad_len)]
    if n_rows:
        raw = np.frombuffer(mark_bytes, dtype=np.uint8).reshape(int(n_rows), 56)
        kinds.extend(int(value) for value in raw[:, 0])
        symbols.extend(int(value) for value in raw[:, 1])
        expansion_modes.extend(int(value) for value in raw[:, 2])
        style_refs.extend(
            int(value) for value in raw[:, 4:8].copy().view("<u4").reshape(int(n_rows))
        )
        stable_ids.extend(
            int(value) for value in raw[:, 8:16].copy().view("<u8").reshape(int(n_rows))
        )
        nums = raw[:, 16:56].copy().view("<f8").reshape(int(n_rows), 5)
        diameters.extend(float(value) for value in nums[:, 0])
        for axis in range(4):
            coordinates[axis].extend(float(value) for value in nums[:, axis + 1])
    return bytes(xyad)


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


def _constant_color(trace: Any, fallback: str) -> str:
    channel = trace.color_ch
    if getattr(trace, "color2_ch", None) is not None:
        raise UnsupportedSceneV3("Scene v12 does not yet encode two-ended ribbon gradients")
    if channel is None:
        return str(trace.style.get("color", fallback))
    if channel.mode != "constant" or channel.constant is None:
        if str(getattr(trace, "kind", "") or "") == "scatter" and trace.use_density():
            return str((getattr(trace, "style", None) or {}).get("color", fallback))
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


def _rect_extra_flags(style: dict[str, Any]) -> int:
    """Pack Scene-unsupported rect extras as XYFS v2 trace flags."""
    flags = 0
    fill = style.get("fill")
    if isinstance(fill, dict) and _admitted_fill_gradient_from_fill(fill, "#3987e5") is None:
        flags |= _XYFS_TRACE_RECT_GRADIENT
    radius = style.get("corner_radius", 0.0)
    if isinstance(radius, (list, tuple)):
        if any(float(value) != 0.0 for value in radius):
            flags |= _XYFS_TRACE_CORNER_RADIUS
    elif float(radius) != 0.0:
        flags |= _XYFS_TRACE_CORNER_RADIUS
    if float(style.get("wedge_gap", 0.0) or 0.0) != 0.0:
        flags |= _XYFS_TRACE_WEDGE_GAP
    return flags


def _density_aggregates_color(trace: Any) -> bool:
    """LOD doc §2: density scatter aggregates a color channel into the blit."""
    if str(getattr(trace, "kind", "") or "") != "scatter" or not trace.use_density():
        return False
    return set(trace.per_item_channel_names()) <= {"color"}


def _figure_trace_support_flags(trace: Any) -> tuple[int, str]:
    """Observe per-trace Scene allowlist bits; Rust owns the diagnostic."""
    kind = str(getattr(trace, "kind", "") or "mark")
    style = getattr(trace, "style", None) or {}
    flags = 0
    if kind not in _SUPPORTED_KINDS:
        flags |= _XYFS_TRACE_UNSUPPORTED_KIND
    if getattr(trace, "x_axis", "x") != "x" or getattr(trace, "y_axis", "y") != "y":
        flags |= _XYFS_TRACE_NON_PRIMARY_AXIS
    if getattr(trace, "hidden", False) or (
        trace.has_per_item_channels() and not _density_aggregates_color(trace)
    ):
        flags |= _XYFS_TRACE_HIDDEN_OR_PER_ITEM
    if style.get("marker_glyph") is not None:
        flags |= _XYFS_TRACE_DASHED_MARKERS
    marker_path = style.get("marker_path")
    if marker_path is not None:
        if kind != "scatter":
            flags |= _XYFS_TRACE_DASHED_MARKERS
        else:
            try:
                validated = _validated_marker_path(marker_path)
            except ValueError:
                flags |= _XYFS_TRACE_DASHED_MARKERS
            else:
                if validated["filled"] and any(
                    len(contour) < 6 for contour in validated["contours"]
                ):
                    flags |= _XYFS_TRACE_DASHED_MARKERS
    curve = style.get("curve")
    if curve is not None:
        curve_name = str(curve).strip().lower()
        if curve_name == "smooth":
            if kind not in {"line", "area", "error_band"} or style.get("step") is not None:
                flags |= _XYFS_TRACE_DASHED_MARKERS
        elif curve_name != "linear":
            flags |= _XYFS_TRACE_DASHED_MARKERS
    linecap = style.get("linecap")
    if linecap is not None and str(linecap).strip().lower() not in {"butt", "round", "square"}:
        flags |= _XYFS_TRACE_DASHED_MARKERS
    dash = style.get("dash")
    if dash is not None and _parse_scene_dash(dash) is False:
        flags |= _XYFS_TRACE_DASHED_MARKERS
    if kind in _RECT_KINDS or kind in _HEATMAP_KINDS:
        flags |= _rect_extra_flags(style)
    if kind in _POLYFILL_KINDS and style.get("joined_fill"):
        flags |= _XYFS_TRACE_JOINED_FILL
    if kind in _HEXBIN_KINDS and style.get("reduce") not in _HEXBIN_REDUCES:
        flags |= _XYFS_TRACE_CUSTOM_HEX_REDUCE
    if (
        kind in _HEATMAP_KINDS
        and _heatmap_uses_colormap(trace)
        and not _heatmap_tessellates_cell_fills(trace)
    ):
        flags |= _XYFS_TRACE_HEATMAP_COLORMAP
    if (
        "fill" in style
        and not isinstance(style["fill"], str)
        and _admitted_fill_gradient(trace) is None
    ):
        flags |= _XYFS_TRACE_NON_CSS_FILL
    return flags, kind


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


def _curve_is_smooth(style: dict[str, Any]) -> bool:
    curve = style.get("curve")
    return curve is not None and str(curve).strip().lower() == "smooth"


def _pack_xypk(
    trace: Any,
    figure: Any,
    *,
    style_ref: int,
    symbol: int,
    diameter: float,
    authored_step: int,
    facts: int,
    hex_dx: float,
    hex_dy: float,
    grid_rows: float,
    grid_cols: float,
) -> bytes:
    """Pack authored product facts; Rust resolves flags, step_mode, and extras."""
    kind = str(trace.kind).encode("utf-8")
    coords = 1 if str(getattr(figure, "coords", "cartesian") or "cartesian") == "polar" else 0
    return (
        struct.pack(
            "<4sIIBBBBQddddd",
            b"XYPK",
            1,
            int(style_ref),
            coords,
            int(symbol) & 0xFF,
            int(authored_step) & 0xFF,
            int(facts) & 0xFF,
            int(trace.id),
            float(diameter),
            float(hex_dx),
            float(hex_dy),
            float(grid_rows),
            float(grid_cols),
        )
        + kind
    )


def _heatmap_uses_colormap(trace: Any) -> bool:
    """Return whether a heatmap still needs the compatibility colormap path."""
    style = getattr(trace, "style", None) or {}
    return bool(
        style.get("truecolor")
        or style.get("colormap") is not None
        or getattr(trace, "rgba_grid", None) is not None
        or getattr(trace, "rgba", None) is not None
    )


def _heatmap_tessellates_cell_fills(trace: Any) -> bool:
    """Return whether Scene can resolve this heatmap to per-cell paints.

    Scalar colormaps, packed RGBA, and truecolor RGBA planes become compact
    `HeatmapPainted` lattices. Polar encode tessellates those Rects to PolyFill
    annular sectors. Scene has no image-blit record for inverse sampling.
    """
    style = getattr(trace, "style", None) or {}
    if getattr(trace, "rgba_grid", None) is not None:
        return True
    if style.get("truecolor"):
        return False
    return bool(style.get("colormap") is not None or getattr(trace, "rgba", None) is not None)


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


def _pack_xyhf(
    *,
    family: int,
    flags: int,
    stable_id: int,
    rows: int,
    cols: int,
    lo: float,
    hi: float,
    opacity: float,
    fill_opacity: float,
    remainder: bytes,
) -> bytes:
    """Pack authored heatmap/density paint facts; Rust owns XYHP kind routing."""
    return (
        _XYHF_HEADER.pack(
            b"XYHF",
            1,
            int(stable_id),
            int(rows),
            int(cols),
            int(flags),
            int(family),
            float(lo),
            float(hi),
            float(opacity),
            float(fill_opacity),
        )
        + remainder
    )


def _pack_xyhf_prefixed(payload: bytes) -> bytes:
    return struct.pack("<I", len(payload)) + payload


def _colormap_stop_bytes(colormap: Any, label: str) -> bytes:
    stops = np.ascontiguousarray(
        [(int(red), int(green), int(blue)) for red, green, blue in colormap],
        dtype=np.uint8,
    )
    if stops.ndim != 2 or stops.shape[1] != 3 or stops.shape[0] < 1:
        raise UnsupportedSceneV3(f"Scene {label} colormap requires RGB stops")
    return np.ascontiguousarray(stops).tobytes()


def _heatmap_paint_plane(
    trace: Any,
    values: np.ndarray,
    rows: int,
    cols: int,
    stable_id: int,
) -> bytes:
    """Pack one XYHF v1 heatmap record. Rust emits the XYHP plane or skips."""
    style = getattr(trace, "style", None) or {}
    flags = _XYHF_HAS_GRID
    remainder = bytearray(np.ascontiguousarray(values.reshape(-1), dtype=np.float64).tobytes())
    packed = getattr(trace, "rgba", None)
    planes = getattr(trace, "rgba_grid", None)
    if packed is not None:
        flags |= _XYHF_HAS_RGBA
        remainder[0:0] = np.ascontiguousarray(
            np.asarray(packed, dtype=np.uint8).reshape(rows, cols, 4)
        ).tobytes()
    if planes is not None:
        if len(planes) != 4:
            raise UnsupportedSceneV3("Scene heatmap truecolor requires four RGBA planes")
        flags |= _XYHF_HAS_RGBA_GRID
        channels_f64 = [
            np.asarray(getattr(plane, "values", plane), dtype=np.float64).reshape(rows, cols)
            for plane in planes
        ]
        grid_rgba = np.ascontiguousarray(np.stack(channels_f64, axis=-1))
        rgba_offset = rows * cols * 4 if packed is not None else 0
        remainder[rgba_offset:rgba_offset] = grid_rgba.tobytes()
    colormap = style.get("colormap")
    if isinstance(colormap, str):
        flags |= _XYHF_HAS_NAMED_CMAP
        remainder.extend(_pack_xyhf_prefixed(colormap.encode("utf-8")))
    elif colormap is not None:
        flags |= _XYHF_HAS_STOPS
        remainder.extend(_pack_xyhf_prefixed(_colormap_stop_bytes(colormap, "heatmap")))
    if style.get("truecolor"):
        flags |= _XYHF_HAS_TRUECOLOR
    domain = style.get("domain")
    if domain is None or len(domain) != 2:
        lo, hi = float("nan"), float("nan")
    else:
        flags |= _XYHF_HAS_DOMAIN
        lo, hi = float(domain[0]), float(domain[1])
    try:
        return _native.scene_pack_heatmap_facts(
            _pack_xyhf(
                family=_XYHF_FAMILY_HEATMAP,
                flags=flags,
                stable_id=stable_id,
                rows=rows,
                cols=cols,
                lo=lo,
                hi=hi,
                opacity=float("nan"),
                fill_opacity=float("nan"),
                remainder=bytes(remainder),
            )
        )
    except ValueError as error:
        raise UnsupportedSceneV3(str(error)) from error


def _density_paint_plane(
    trace: Any,
    encoded: np.ndarray,
    rows: int,
    cols: int,
    maximum: float,
    stable_id: int,
    mean_rgba: np.ndarray | None = None,
) -> bytes:
    """Pack one XYHF v1 density record. Rust owns kind/opacity/colormap routing."""
    style = getattr(trace, "style", None) or {}
    encoded_u8 = np.ascontiguousarray(np.asarray(encoded, dtype=np.uint8).reshape(-1))
    if encoded_u8.size != rows * cols:
        raise UnsupportedSceneV3("Scene density grid must match DENSITY_GRID")
    flags = _XYHF_HAS_ENCODED
    remainder = bytearray(encoded_u8.tobytes())
    if mean_rgba is not None:
        rgba_u8 = np.ascontiguousarray(np.asarray(mean_rgba, dtype=np.uint8).reshape(-1))
        if rgba_u8.size != rows * cols * 4:
            raise UnsupportedSceneV3("Scene mean-color plane must match DENSITY_GRID")
        flags |= _XYHF_HAS_MEAN_RGBA
        remainder.extend(rgba_u8.tobytes())
    colormap = style.get("colormap")
    if isinstance(colormap, str):
        flags |= _XYHF_HAS_NAMED_CMAP
        remainder.extend(_pack_xyhf_prefixed(colormap.encode("utf-8")))
    elif colormap is not None:
        flags |= _XYHF_HAS_STOPS
        remainder.extend(_pack_xyhf_prefixed(_colormap_stop_bytes(colormap, "density")))
    channel = getattr(trace, "color_ch", None)
    if channel is not None and channel.mode == "constant" and channel.constant is not None:
        flags |= _XYHF_HAS_COLOR_CH
        remainder.extend(_pack_xyhf_prefixed(str(channel.constant).encode("utf-8")))
    if style.get("color") is not None:
        flags |= _XYHF_HAS_STYLE_COLOR
        remainder.extend(_pack_xyhf_prefixed(str(style.get("color")).encode("utf-8")))
    opacity = float("nan")
    fill_opacity = float("nan")
    if "opacity" in style:
        flags |= _XYHF_HAS_OPACITY
        opacity = float(style["opacity"])
    if "fill_opacity" in style:
        flags |= _XYHF_HAS_FILL_OPACITY
        fill_opacity = float(style["fill_opacity"])
    try:
        return _native.scene_pack_heatmap_facts(
            _pack_xyhf(
                family=_XYHF_FAMILY_DENSITY,
                flags=flags,
                stable_id=stable_id,
                rows=rows,
                cols=cols,
                lo=float(maximum),
                hi=float("nan"),
                opacity=opacity,
                fill_opacity=fill_opacity,
                remainder=bytes(remainder),
            )
        )
    except ValueError as error:
        raise UnsupportedSceneV3(str(error)) from error


def _density_blit_pack(
    figure: Any, trace: Any
) -> tuple[float, float, bytes, list[np.ndarray | None]] | None:
    """Pack constant-style density as one compact Image lattice.

    Cartesian Scene expansion emits one Image blit. Polar Scene expansion
    (ABI 143) tessellates occupied cells to PolyFill wedges instead.
    """
    if not trace.use_density():
        return None
    xv = _trace_column(trace, "x")
    yv = _trace_column(trace, "y")
    if xv is None or yv is None or len(xv) != len(yv) or len(xv) == 0:
        return None
    xr0, xr1 = (float(value) for value in figure._range("x"))
    yr0, yr1 = (float(value) for value in figure._range("y"))
    if not (
        math.isfinite(xr0) and math.isfinite(xr1) and math.isfinite(yr0) and math.isfinite(yr1)
    ):
        return None
    if xr1 <= xr0 or yr1 <= yr0:
        return None
    bin_colors = channels.resolve_bin_colors(getattr(trace, "color_ch", None), None)
    packed = _native.scene_pack_density_grid(xv, yv, xr0, xr1, yr0, yr1, **(bin_colors or {}))
    if packed is None:
        return None
    encoded, gmax, mean_rgba, rows, cols = packed
    plane = _density_paint_plane(
        trace, encoded, int(rows), int(cols), float(gmax), int(trace.id), mean_rgba
    )
    columns: list[np.ndarray | None] = [
        np.asarray([xr0, xr1], dtype=np.float64),
        np.asarray([yr0, yr1], dtype=np.float64),
        None,
        None,
        None,
        None,
        None,
    ]
    return float(rows), float(cols), plane, columns


def _pack_xyhp(planes: list[bytes]) -> bytes:
    """Wrap painted-heatmap planes in an XYHP v1 envelope."""
    if not planes:
        return b""
    return struct.pack("<4sIII", b"XYHP", 1, len(planes), 0) + b"".join(planes)


def _parse_scene_dash(value: Any) -> list[float] | None | bool:
    """Return a 2–8 length pattern, None for solid, False if unusable on Scene."""
    if value is None:
        return None
    if isinstance(value, str):
        preset = _SCENE_DASH_PRESETS.get(value.strip().lower())
        if value.strip().lower() in _SCENE_DASH_PRESETS:
            return preset
        parts = [part.strip() for part in value.split(",") if part.strip()]
        try:
            lengths = [float(part) for part in parts]
        except ValueError:
            return False
    elif isinstance(value, (list, tuple)):
        try:
            lengths = [float(part) for part in value]
        except (TypeError, ValueError):
            return False
    else:
        return False
    if not 2 <= len(lengths) <= 8:
        return False
    if any(not np.isfinite(length) or length <= 0.0 for length in lengths):
        return False
    return lengths


def _parse_scene_linecap(value: Any) -> int | None | bool:
    """Return 0=butt or 2=square, None for round/omitted, False if unusable."""
    if value is None:
        return None
    name = str(value).strip().lower()
    if name == "butt":
        return 0
    if name == "square":
        return 2
    if name == "round":
        return None
    return False


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
            grad_dir = _GRAD_DIR_CODES[gradient["dir"]]
            plot_space = 1 if gradient.get("space") == "plot" else 0
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


def _fill_is_gradient_authoring(fill: Any) -> bool:
    if isinstance(fill, dict):
        return True
    return isinstance(fill, str) and fill.strip().lower().startswith("linear-gradient(")


_GRAD_DIR_CODES = {"down": 0, "up": 1, "right": 2, "left": 3}


def _admitted_fill_gradient_from_fill(fill: Any, mark_color: str) -> dict[str, Any] | None:
    """Return a resolved XYGR payload, or None to keep the fill fail-closed."""
    spec: dict[str, Any] | None
    if isinstance(fill, dict) and {"space", "dir", "stops"} <= set(fill):
        spec = fill
    else:
        try:
            spec = _validate.mark_fill(fill, "fill")
        except (TypeError, ValueError):
            return None
    if not spec:
        return None
    space = spec.get("space")
    direction = spec.get("dir")
    stops = spec.get("stops")
    if space not in {"mark", "plot"} or direction not in _GRAD_DIR_CODES:
        return None
    if not isinstance(stops, (list, tuple)) or not 2 <= len(stops) <= 8:
        return None
    resolved: list[tuple[float, tuple[int, int, int, int]]] = []
    prev_t = -1.0
    for stop in stops:
        if not isinstance(stop, (list, tuple)) or len(stop) != 2:
            return None
        try:
            t = float(stop[0])
        except (TypeError, ValueError):
            return None
        if not math.isfinite(t) or t < 0.0 or t > 1.0 or t < prev_t:
            return None
        css = str(stop[1]).strip()
        lowered = css.lower()
        if "var(" in lowered:
            return None
        if lowered in {"currentcolor", ""}:
            css = mark_color
        try:
            rgba = _native.css_color_rgba(css, 1.0)
        except ValueError:
            return None
        resolved.append((t, rgba))
        prev_t = t
    return {"space": space, "dir": direction, "stops": resolved}


def _admitted_fill_gradient(trace: Any) -> dict[str, Any] | None:
    fill = (getattr(trace, "style", None) or {}).get("fill")
    if fill is None or not _fill_is_gradient_authoring(fill):
        return None
    try:
        mark_color = _constant_color(trace, "#3987e5")
    except UnsupportedSceneV3:
        return None
    return _admitted_fill_gradient_from_fill(fill, mark_color)


def _gradient_solid_css(gradient: dict[str, Any]) -> str:
    for _t, rgba in gradient["stops"]:
        if rgba[3] > 0:
            return f"rgb({rgba[0]},{rgba[1]},{rgba[2]})"
    return "rgb(0,0,0)"


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
        colorbar_input = _colorbar_input(figure)
    except UnsupportedSceneV3:
        colorbar_input = b""
        colorbar_unsupported = True
    reason = _native.scene_figure_support_reason(
        _pack_figure_support(figure, annotations, colorbar_unsupported)
    )
    if reason:
        raise UnsupportedSceneV3(reason)

    kinds: list[int] = []
    stable_ids: list[int] = []
    style_refs: list[int] = []
    styles: list[tuple[tuple[int, ...], tuple[int, ...], float]] = []
    dashes: list[list[float] | None] = []
    linecaps: list[int | None] = []
    marker_paths: list[dict[str, Any] | None] = []
    fill_gradients: list[dict[str, Any] | None] = []
    diameters: list[float] = []
    symbols: list[int] = []
    coordinates: list[list[float]] = [[], [], [], []]
    expansion_modes: list[int] = []
    legend_entries: list[tuple[int, int, int, str]] = []
    heatmap_paint_planes: list[bytes] = []
    for trace in figure.traces:
        style = trace.style
        opacity = float(style.get("opacity", 1.0))
        if not np.isfinite(opacity) or not 0.0 <= opacity <= 1.0:
            raise ValueError("trace opacity must be finite and in [0, 1]")
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
        parsed_dash = _parse_scene_dash(style.get("dash"))
        dashes.append(None if parsed_dash is False else parsed_dash)
        parsed_cap = _parse_scene_linecap(style.get("linecap"))
        linecaps.append(None if parsed_cap is False else parsed_cap)
        marker_path = None
        raw_marker_path = style.get("marker_path")
        if trace.kind == "scatter" and raw_marker_path is not None:
            try:
                marker_path = _validated_marker_path(raw_marker_path)
            except ValueError:
                marker_path = None
            if (
                marker_path is not None
                and marker_path["filled"]
                and any(len(contour) < 6 for contour in marker_path["contours"])
            ):
                marker_path = None
        marker_paths.append(marker_path)
        fill_gradients.append(_admitted_fill_gradient(trace))
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

        pack_symbol = 0
        pack_diameter = 0.0
        pack_columns = None
        authored_step = 0
        fact_bits = 0
        hex_dx = hex_dy = 0.0
        grid_rows = grid_cols = 0.0
        if trace.kind in _HEATMAP_KINDS:
            rows, cols = _heatmap_shape(trace)
            values = _heatmap_grid_values(trace)
            if values.size != rows * cols:
                raise UnsupportedSceneV3("Scene v12 heatmap grid must match rows x cols")
            if not np.isfinite(values).all():
                raise UnsupportedSceneV3(
                    "Scene v12 does not yet encode missing-data breaks or nonfinite coordinates"
                )
            grid_rows, grid_cols = float(rows), float(cols)
            plane = _heatmap_paint_plane(trace, values, rows, cols, int(trace.id))
            if plane:
                heatmap_paint_planes.append(plane)
                fact_bits |= _XYPK_FACT_HEATMAP_PAINT
        elif trace.kind in _HEXBIN_KINDS:
            hex_dx, hex_dy = _hexbin_pitch(style)
        elif trace.kind in _BAND_KINDS:
            stroke_perimeter = style.get("stroke_perimeter", False)
            if not isinstance(stroke_perimeter, bool):
                raise UnsupportedSceneV3("Scene v25 area stroke_perimeter must be a boolean")
            if stroke_perimeter:
                fact_bits |= _XYPK_FACT_STROKE_PERIMETER
            if _curve_is_smooth(style):
                fact_bits |= _XYPK_FACT_CURVE_SMOOTH
        elif trace.kind == "line":
            where = style.get("step")
            if where is not None:
                if where not in {"pre", "post", "mid"}:
                    raise UnsupportedSceneV3(f"Scene v12 does not support step mode {where!r}")
                authored_step = {"pre": 1, "mid": 2, "post": 3}[where]
            if _curve_is_smooth(style):
                fact_bits |= _XYPK_FACT_CURVE_SMOOTH
        elif trace.kind == "scatter":
            pack_symbol = _SYMBOL_CODES[symbol_name]
            pack_diameter = diameter
            density_pack = _density_blit_pack(figure, trace)
            if density_pack is not None:
                grid_rows, grid_cols, plane, pack_columns = density_pack
                fact_bits |= _XYPK_FACT_DENSITY_PLANE
                heatmap_paint_planes.append(plane)
                pack_symbol = 0
                pack_diameter = 0.0
        _append_packed(
            kinds,
            stable_ids,
            style_refs,
            diameters,
            symbols,
            expansion_modes,
            coordinates,
            trace,
            columns=pack_columns,
            facts=_pack_xypk(
                trace,
                figure,
                style_ref=style_ref,
                symbol=pack_symbol,
                diameter=pack_diameter,
                authored_step=authored_step,
                facts=fact_bits,
                hex_dx=hex_dx,
                hex_dy=hex_dy,
                grid_rows=grid_rows,
                grid_cols=grid_cols,
            ),
        )

    # Scene v12's bounded primary-annotation subset is represented by ordinary
    # canonical records with a reserved stable-id namespace. Hosts pack XYAF
    # authored facts; Rust owns wrap/text/arrow/callout/rule routing, tags,
    # defaults, mark expansion, and XYAD framing (ABI 148). Hosts pack XYHF
    # heatmap/density paint facts; Rust owns XYHP kind routing (ABI 149).
    # Hosts pack XYSS sidecar facts plus framed XYPL/XYHP; Rust owns
    # XYDS/XYLC/XYMP/XYGR layout, concat order, and XYEX wrapping (ABI 150).
    # Hosts pass density columns; Rust owns bin_2d / density_log_u8 / mean-color
    # (ABI 151).
    x_domain = tuple(float(value) for value in figure._range("x"))
    y_domain = tuple(float(value) for value in figure._range("y"))
    annotation_facts = bytearray()
    for annotation_index, annotation in enumerate(annotations):
        annotation_facts.extend(_pack_xyaf(annotation, annotation_index))
    try:
        annotation_output = (
            _native.scene_pack_annotation_facts(
                bytes(annotation_facts),
                style_ref_base=len(styles),
                x_domain=x_domain,
                y_domain=y_domain,
            )
            if annotation_facts
            else b""
        )
    except ValueError as error:
        raise UnsupportedSceneV3(str(error)) from error
    framed_annotations = _apply_xyao(
        annotation_output,
        kinds,
        stable_ids,
        style_refs,
        diameters,
        symbols,
        expansion_modes,
        coordinates,
        styles,
        dashes,
        linecaps,
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
        authored_text_annotations=bytes(framed_annotations),
        polar_input=_native.scene_pack_scene_extras(
            _pack_polar_scene_input(figure),
            _pack_xyhp(heatmap_paint_planes),
            _pack_xyss(dashes, linecaps, marker_paths, fill_gradients),
        ),
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
    quality: int | None = None,
) -> bytes | None:
    """Render one supported public static format from the canonical Scene.

    This is the only selection seam for the migrated public SVG/PNG/PDF/JPEG/WebP
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
    if format in {"jpeg", "webp"}:
        from . import kernels

        commands = figure_raster_commands(figure, width=width, height=height, scale=scale)
        w = max(1, int(round(int(width if width is not None else figure.width) * float(scale))))
        h = max(1, int(round(int(height if height is not None else figure.height) * float(scale))))
        rgba = kernels.rasterize(commands, w, h)
        if format == "jpeg":
            rgb = _flatten_jpeg_background(rgba)
            return _native.encode_jpeg(rgb, quality=90 if quality is None else int(quality))
        return _native.encode_webp(rgba)
    raise ValueError(
        f"Scene public static format must be svg, png, pdf, jpeg, or webp, got {format!r}"
    )


def _flatten_jpeg_background(rgba: np.ndarray) -> np.ndarray:
    """Composite leftover Scene alpha over white before JPEG encode."""
    alpha = rgba[..., 3:4].astype(np.uint16)
    rgb = (rgba[..., :3].astype(np.uint16) * alpha + 255 * (255 - alpha) + 127) // 255
    return rgb.astype(np.uint8)


def _significant_scene_axis_keys(options: dict[str, Any]) -> list[str]:
    return [str(key) for key, value in options.items() if value not in (None, False, [], {})]


def _pack_polar_scene_input(figure: Any) -> bytes:
    """Pack XYPL v1 polar authoring. Rust owns disc layout from the plot rect."""
    if getattr(figure, "coords", "cartesian") != "polar":
        return b""
    xa = figure.axis_options.get("x") or {}
    ya = figure.axis_options.get("y") or {}
    unit = str(xa.get("theta_unit", "radians"))
    turn = 360.0 if unit == "degrees" else 2.0 * math.pi
    sector = xa.get("sector") or (0.0, turn)
    sector_start, sector_end = float(sector[0]), float(sector[1])
    categories = tuple(xa.get("categories") or ())
    r_lo, r_hi = figure._range("y")
    origin = ya.get("r_origin")
    r_origin = float("nan") if origin is None else float(origin)
    hole = float(ya.get("hole") or 0.0)
    scale_kind, constant, mask_nonpositive = _native._polar_r_scale(ya)
    grid = str(xa.get("grid_shape", "circular"))
    grid_shape = 1 if grid == "linear" else 0
    return struct.pack(
        "<4s5I2BHdddddddd",
        b"XYPL",
        1,
        _native._polar_theta_unit(unit),
        _native._polar_theta_direction(xa.get("theta_direction")),
        len(categories),
        scale_kind,
        grid_shape,
        1 if mask_nonpositive else 0,
        0,
        _native._polar_theta_zero(xa.get("theta_zero", "E")),
        sector_start,
        sector_end,
        float(r_lo),
        float(r_hi),
        r_origin,
        hole,
        constant,
    )


def _pack_figure_support(
    figure: Any,
    annotations: list[Any],
    colorbar_unsupported: bool,
) -> bytes:
    """Pack literal figure observations, axis keys, and per-trace allowlist flags."""
    flags = 0
    if figure.coords != "cartesian":
        flags |= 1 << 0
    chrome_styles = getattr(figure, "chrome_styles", None) or {}
    if any("font-family" in (style or {}) for style in chrome_styles.values()):
        flags |= 1 << 1
    if (
        getattr(figure, "class_name", None)
        or getattr(figure, "class_names", None)
        or chrome_styles
        or set(getattr(figure, "style", None) or {}) - {"background", "--chart-bg"}
        or any(annotation.get("class_name") not in (None, "") for annotation in annotations)
    ):
        flags |= 1 << 2
    if any(
        getattr(trace, "color2_ch", None) is not None
        or (
            getattr(trace, "color_ch", None) is not None
            and (trace.color_ch.mode != "constant" or trace.color_ch.constant is None)
            and not (str(getattr(trace, "kind", "") or "") == "scatter" and trace.use_density())
        )
        or (
            _fill_is_gradient_authoring((getattr(trace, "style", None) or {}).get("fill"))
            and _admitted_fill_gradient(trace) is None
        )
        for trace in figure.traces
    ):
        flags |= 1 << 3
    if colorbar_unsupported:
        flags |= 1 << 4
    if figure.extra_legends:
        flags |= 1 << 5
    if any(
        annotation.get("kind") not in {"callout", "arrow", "text"}
        and annotation.get("text") not in (None, "")
        for annotation in annotations
    ):
        flags |= 1 << 7
    traces = list(getattr(figure, "traces", None) or [])
    payload = bytearray(b"XYFS")
    payload.extend((2).to_bytes(4, "little"))
    payload.extend(flags.to_bytes(4, "little"))
    payload.extend(len(figure.axis_options).to_bytes(4, "little"))
    payload.extend(len(traces).to_bytes(4, "little"))
    for axis_id, options in figure.axis_options.items():
        axis_code = 0 if axis_id == "x" else 1 if axis_id == "y" else 255
        keys = _significant_scene_axis_keys(options)
        payload.extend(bytes((axis_code, 0, 0, 0)))
        payload.extend(len(keys).to_bytes(4, "little"))
        _xyep_put_keys(payload, keys)
    for trace in traces:
        trace_flags, kind = _figure_trace_support_flags(trace)
        encoded = str(kind).encode("utf-8")[:32]
        payload.extend(trace_flags.to_bytes(2, "little"))
        payload.extend(bytes((len(encoded), 0)))
        payload.extend((0).to_bytes(4, "little"))
        payload.extend(encoded)
    return bytes(payload)


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
            if _heatmap_uses_colormap(trace) and not _heatmap_tessellates_cell_fills(trace):
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
        if (
            trace.kind == "scatter"
            and getattr(figure, "coords", "cartesian") == "cartesian"
            and trace.use_density()
        ):
            flags_tr |= 1 << 22
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
