"""Thin figure-to-Scene v12 compiler for the migrated core-mark subset.

Rust owns mapping, clipping, record semantics, SVG construction, and raster
display-list construction. This module only projects already-validated Figure
objects into the typed ABI and rejects features whose canonical Scene record
does not exist yet.
"""

from __future__ import annotations

import math
import struct
from typing import Any, NoReturn

import numpy as np

from . import _native, channels
from .marks import _SYMBOL_CODES, _validated_marker_path

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
_XYFS_TRACE_UNSUPPORTED_KIND = 1 << 0
_XYFS_TRACE_NON_PRIMARY_AXIS = 1 << 1
_XYFS_TRACE_HIDDEN_OR_PER_ITEM = 1 << 2
_XYFS_TRACE_DENSITY = 1 << 3  # ABI 143 no longer sets this for polar density
_XYFS_TRACE_DASHED_MARKERS = 1 << 4
_XYFS_TRACE_RECT_GRADIENT = 1 << 5
_XYFS_TRACE_CORNER_RADIUS = 1 << 6
_XYFS_TRACE_WEDGE_GAP = 1 << 7
_XYFS_TRACE_JOINED_FILL = 1 << 8  # reserved; ABI 182 no longer fail-closes this bit
_XYFS_TRACE_CUSTOM_HEX_REDUCE = 1 << 9
_XYFS_TRACE_HEATMAP_COLORMAP = 1 << 10
_XYFS_TRACE_NON_CSS_FILL = 1 << 11
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

_XYEF_OBS_HAS_X = 1 << 0
_XYEF_OBS_HAS_Y = 1 << 1
_XYEF_OBS_X_FINITE = 1 << 2
_XYEF_OBS_Y_FINITE = 1 << 3
_XYEF_OBS_HAS_X0 = 1 << 4
_XYEF_OBS_HAS_Y0 = 1 << 5
_XYEF_OBS_HAS_X1 = 1 << 6
_XYEF_OBS_HAS_Y1 = 1 << 7
_XYEF_OBS_X0_FINITE = 1 << 8
_XYEF_OBS_Y0_FINITE = 1 << 9
_XYEF_OBS_X1_FINITE = 1 << 10
_XYEF_OBS_Y1_FINITE = 1 << 11
_XYEF_OBS_JOINED_FILL = 1 << 12
_XYEF_OBS_HEATMAP_TRUECOLOR = 1 << 13
_XYEF_OBS_HEATMAP_RGBA_GRID = 1 << 16
_XYEF_OBS_HEATMAP_SHAPE_OK = 1 << 17
_XYEF_OBS_HEATMAP_EXTENT_OK = 1 << 18
_XYEF_OBS_HEATMAP_FINITE = 1 << 19
_XYEF_OBS_STROKE_WIDTH_ONLY = 1 << 20
_XYEF_OBS_COMPANION_XY_MATCH = 1 << 21
_XYEF_OBS_COMPANION_AXES_MATCH = 1 << 22
_XYEF_OBS_SYMBOL_NON_STRING = 1 << 23
_XYEF_OBS_DENSITY_BLIT = 1 << 24

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
_XYAS_HEADER = struct.Struct("<4sIIIII")
_XYAS_STYLE = struct.Struct("<4s4sd")


class UnsupportedSceneV3(ValueError):
    """The figure uses a feature outside the currently migrated Scene subset."""


def _trace_column(trace: Any, name: str) -> np.ndarray | None:
    """Return one authored f64 column, or None when the host did not set it."""
    value = getattr(trace, name, None)
    if value is None:
        return None
    return np.asarray(getattr(value, "values", value), dtype=np.float64)


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


def _pack_xyaf(annotation: dict[str, Any], index: int) -> bytes:
    """Pack one authored annotation as XYAF v1; Rust classifies the family.

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
    ABI 184 packs cartesian unwrapped text ``dx``/``dy``/``anchor`` as XYAW
    with ``wrap=0`` so Rust applies the offset without wrapping. ABI 185
    packs labelled cartesian marker ``dx``/``dy``/``anchor`` the same way
    (Rust keeps the marker mark row and skips AttachedRow). ABI 187 packs
    cartesian unwrapped text ``rotation`` as XYAW with ``wrap=0`` (nonzero
    rotation writes XYAW v2 / XYLB v6). ABI 188 packs labelled cartesian marker
    ``rotation`` the same way (nums[8]; markers never wrap, and nums[15] stays
    ``stroke_width``). ABI 189 packs raw heatmap/hexbin XYTA observations;
    Rust owns cell-fill tessellation eligibility on the XYFS probe.
    """
    annotation = dict(annotation)
    kind = annotation.get("kind")
    kind_code = _XYAF_KIND_CODES.get(str(kind) if kind is not None else "")
    if kind_code is None:
        raise UnsupportedSceneV3(
            f"Scene v12 annotations support rule, band, and unlabeled marker only; {kind!r} is deferred"
        )
    style = dict(annotation.get("style") or {})
    if (
        str(kind) in {"text", "marker"}
        and "rotation" not in annotation
        and style.get("rotation") is not None
    ):
        annotation["rotation"] = style["rotation"]
    authored_wrap = kind in {"text", "callout"} and "wrap" in annotation
    layout_text = kind == "text" and any(
        key in annotation for key in ("dx", "dy", "anchor", "rotation")
    )
    wrapped = authored_wrap or layout_text
    attached_text = annotation.get("text")
    labelled = attached_text not in (None, "")
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
    skip_style = {"markup"} | _ANNOTATION_TYPOGRAPHY_STYLE_KEYS
    if str(kind) in {"text", "marker"}:
        skip_style = skip_style | {"rotation"}
    unsupported = sorted(
        key
        for key, value in style.items()
        if key not in skip_style
        and value is not None
        and not _native.scene_annotation_style_admit(str(kind), wrapped, labelled, str(key))
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
        if "wrap" in annotation:
            nums[8] = take_num(annotation, "wrap", "wrapped width")
        else:
            nums[8] = 0.0
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
    if str(kind) == "text" and "rotation" in annotation:
        nums[15] = take_num(annotation, "rotation", "text rotation")
        facts |= _XYAF_FACT_HAS_ROTATION
        if not np.isfinite(nums[15]):
            raise ValueError("Scene v16 text annotation rotation must be finite")
    if str(kind) == "marker" and "rotation" in annotation:
        nums[8] = take_num(annotation, "rotation", "marker rotation")
        facts |= _XYAF_FACT_HAS_ROTATION
        if not np.isfinite(nums[8]):
            raise ValueError("Scene v16 marker annotation rotation must be finite")
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
        dash_or_reject = _parse_scene_dash(style.get("dash"))
        if isinstance(dash_or_reject, list):
            parsed_dash = [float(value) for value in dash_or_reject]
            style_bits |= _XYAF_STYLE_DASH
        elif dash_or_reject is None:
            parsed_dash = None
        else:
            raise UnsupportedSceneV3("Scene v12 rule annotation dash is not a constant pattern")
        cap_or_reject = _parse_scene_linecap(style.get("linecap"))
        if cap_or_reject is None:
            parsed_cap = None
        elif isinstance(cap_or_reject, int) and not isinstance(cap_or_reject, bool):
            parsed_cap = cap_or_reject
            style_bits |= _XYAF_STYLE_LINECAP
        else:
            raise UnsupportedSceneV3("Scene v12 rule annotation linecap is not a Scene cap")
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
    if _classify_ribbon_color2(trace) == "fail":
        raise UnsupportedSceneV3("Scene v12 does not yet encode two-ended ribbon gradients")
    if channel is None:
        return str(trace.style.get("color", fallback))
    if channel.mode != "constant" or channel.constant is None:
        if str(getattr(trace, "kind", "") or "") == "scatter" and trace.use_density():
            return str((getattr(trace, "style", None) or {}).get("color", fallback))
        if (
            _hexbin_packs_paint_plane(trace)
            or _ribbon_packs_end_paints(trace)
            or _mesh_packs_paint_plane(trace)
            or _scatter_packs_paint_plane(trace)
        ):
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


def _pack_xych(figure: Any) -> bytes:
    """Pack authored XYCH v1 chrome literals; Rust owns the 200-byte Scene style."""
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
    return header + chart_b + plot_b + x_rec + y_rec


def _scene_chrome_style(figure: Any) -> bytes:
    """Pack authored chrome literals; Rust owns the 200-byte Scene style."""
    return _native.scene_resolve_chrome_style(_pack_xych(figure))


_XYCF_HEADER = struct.Struct("<4sIII10d2I6dBBH15I2dII4s4sIIII2d4sI")
_XYCC_HEADER = struct.Struct("<4sIII4d16I48x")
_XYCF_FLAG_AUTHORED_MARGINS = 1 << 0
_XYCF_FLAG_PADDING = 1 << 1
_XYCF_FLAG_X_MAJOR_AUTO = 1 << 2
_XYCF_FLAG_Y_MAJOR_AUTO = 1 << 3
_XYCF_FLAG_X_TICK_LABELS = 1 << 4
_XYCF_FLAG_Y_TICK_LABELS = 1 << 5
_XYCF_FLAG_HAS_CHROME = 1 << 6
_XYCF_FLAG_HAS_LEGEND = 1 << 7
_XYCF_FLAG_HAS_COLORBAR = 1 << 8
_XYCF_LEGEND_AUTHORED_LOC = 1 << 0
_XYCF_LEGEND_AUTHORED_FONT = 1 << 1
_XYCF_LEGEND_AUTHORED_TITLE_FONT = 1 << 2
_XYCF_LEGEND_AUTHORED_COLOR = 1 << 3
_XYCF_LEGEND_AUTHORED_BACKGROUND = 1 << 4
_XYCF_LEGEND_UNSUPPORTED_KEYS = 1 << 5
_XYCF_LEGEND_TOGGLE = 1 << 6
_XYCF_LEGEND_HIGHLIGHT = 1 << 7
_XYCF_LEGEND_SHOW = 1 << 8
_XYCF_LEGEND_UNSUPPORTED_STYLE = 1 << 9
_XYCF_CB_HORIZONTAL = 1 << 1
_XYCF_CB_MINOR = 1 << 2
_XYCF_CB_UNSUPPORTED = 1 << 3
_XYCF_CB_INVALID_SIDE = 1 << 4
_SCENE_TICK_STRATEGIES = {
    "auto": 0,
    "hide": 1,
    "rotate": 2,
    "stagger": 3,
    "preserve": 4,
    "none": 5,
    "off": 6,
}
_SCENE_TICK_STRATEGY_NAMES = (
    "auto",
    "hide",
    "rotate",
    "stagger",
    "preserve",
    "none",
    "off",
)
_POLAR_COLLISION_KEYS = {
    "tick_label_strategy",
    "collision",
    "tick_label_min_gap",
    "tick_label_angle",
    "tick_label_anchor",
}


def _put_f64s(buf: bytearray, values: list[float]) -> None:
    for value in values:
        buf.extend(struct.pack("<d", float(value)))


def _put_tick_labels(buf: bytearray, labels: list[str] | tuple[str, ...] | None) -> int:
    if not labels:
        return 0
    for label in labels:
        encoded = str(label).encode("utf-8")
        buf.extend(len(encoded).to_bytes(4, "little"))
        buf.extend(encoded)
    return len(labels)


def _xycc_tick_labels(blob: bytes) -> list[str] | None:
    if not blob:
        return None
    if len(blob) < 12 or blob[:4] != b"XYTL":
        raise ValueError("invalid scene chrome packing")
    count = int.from_bytes(blob[8:12], "little")
    at = 12
    labels: list[str] = []
    for _ in range(count):
        length = int.from_bytes(blob[at : at + 4], "little")
        at += 4
        labels.append(blob[at : at + length].decode("utf-8"))
        at += length
    if at != len(blob):
        raise ValueError("invalid scene chrome packing")
    return labels


def _unpack_xycc(blob: bytes) -> dict[str, Any]:
    """Split Rust-owned XYCC chrome into encode-ready chrome fields."""
    if len(blob) < _XYCC_HEADER.size or blob[:4] != b"XYCC":
        raise ValueError("invalid scene chrome packing")
    (
        _magic,
        version,
        _flags,
        _reserved,
        margin_left,
        margin_right,
        margin_top,
        margin_bottom,
        chrome_len,
        title_len,
        xlabel_len,
        ylabel_len,
        x_major_count,
        x_major_auto,
        x_minor_count,
        y_major_count,
        y_major_auto,
        y_minor_count,
        x_labels_len,
        y_labels_len,
        x_format_len,
        y_format_len,
        legend_len,
        colorbar_len,
    ) = _XYCC_HEADER.unpack_from(blob)
    if version != 1:
        raise ValueError("invalid scene chrome facts version")
    at = _XYCC_HEADER.size

    def take(length: int) -> bytes:
        nonlocal at
        chunk = blob[at : at + length]
        at += length
        return chunk

    chrome_style = take(chrome_len)
    title = take(title_len).decode("utf-8")
    x_label = take(xlabel_len).decode("utf-8")
    y_label = take(ylabel_len).decode("utf-8")
    x_major = (
        list(struct.unpack(f"<{x_major_count}d", take(x_major_count * 8))) if x_major_count else []
    )
    x_minor = (
        list(struct.unpack(f"<{x_minor_count}d", take(x_minor_count * 8))) if x_minor_count else []
    )
    y_major = (
        list(struct.unpack(f"<{y_major_count}d", take(y_major_count * 8))) if y_major_count else []
    )
    y_minor = (
        list(struct.unpack(f"<{y_minor_count}d", take(y_minor_count * 8))) if y_minor_count else []
    )
    x_tick_labels = _xycc_tick_labels(take(x_labels_len))
    y_tick_labels = _xycc_tick_labels(take(y_labels_len))
    x_format_b = take(x_format_len)
    y_format_b = take(y_format_len)
    legend_input = take(legend_len)
    colorbar_input = take(colorbar_len)
    if at != len(blob):
        raise ValueError("invalid scene chrome packing")
    return {
        "margins": (margin_left, margin_right, margin_top, margin_bottom),
        "chrome_style": chrome_style,
        "title": title,
        "x_label": x_label,
        "y_label": y_label,
        "x_major_ticks": None if x_major_auto else x_major,
        "x_minor_ticks": x_minor,
        "y_major_ticks": None if y_major_auto else y_major,
        "y_minor_ticks": y_minor,
        "x_tick_labels": x_tick_labels,
        "y_tick_labels": y_tick_labels,
        "x_format": None if not x_format_b else x_format_b.decode("utf-8"),
        "y_format": None if not y_format_b else y_format_b.decode("utf-8"),
        "legend_input": legend_input,
        "colorbar_input": colorbar_input,
    }


def _scene_tick_label_strategy(options: dict[str, Any]) -> str:
    raw = options.get("tick_label_strategy")
    if raw is None:
        raw = options.get("collision")
    code = _native.scene_tick_label_strategy(str(raw or "auto"))
    if 0 <= code < len(_SCENE_TICK_STRATEGY_NAMES):
        return _SCENE_TICK_STRATEGY_NAMES[code]
    return "auto"


def _scene_tick_anchor_code(options: dict[str, Any]) -> int | None:
    raw = options.get("tick_label_anchor")
    if raw is None:
        return None
    return _native.scene_tick_anchor(str(raw))


def _pack_tick_collision(xa: dict[str, Any], ya: dict[str, Any], figure: Any) -> tuple[int, bytes]:
    """Pack XYCF bytes 12–15 plus optional 32-byte extras (ABI 203)."""
    x_strategy = _SCENE_TICK_STRATEGIES[_scene_tick_label_strategy(xa)]
    y_strategy = _SCENE_TICK_STRATEGIES[_scene_tick_label_strategy(ya)]
    x_anchor = _scene_tick_anchor_code(xa)
    y_anchor = _scene_tick_anchor_code(ya)
    x_gap = xa.get("tick_label_min_gap")
    y_gap = ya.get("tick_label_min_gap")
    x_angle = xa.get("tick_label_angle")
    y_angle = ya.get("tick_label_angle")
    extras = x_gap is not None or y_gap is not None or x_angle is not None or y_angle is not None
    flags = 0
    if extras:
        flags |= 1
    if figure._axis_kind("x") == "category":
        flags |= 1 << 1
    if figure._axis_kind("y") == "category":
        flags |= 1 << 2
    if x_anchor is not None:
        flags |= 1 << 3
    if y_anchor is not None:
        flags |= 1 << 4
    header = (
        x_strategy
        | (y_strategy << 8)
        | ((x_anchor or 0) << 16)
        | ((y_anchor or 0) << 20)
        | (flags << 24)
    )
    extra = b""
    if extras:
        extra = struct.pack(
            "<4d",
            8.0 if x_gap is None else float(x_gap),
            4.0 if y_gap is None else float(y_gap),
            float("nan") if x_angle is None else float(x_angle),
            float("nan") if y_angle is None else float(y_angle),
        )
    return header, extra


def _pack_chrome_facts(
    figure: Any,
    *,
    width: int,
    height: int,
    margins: tuple[float, float, float, float] | None,
    colorbar_ok: bool,
) -> bytes:
    """Pack authored XYCF v1 chrome facts; Rust owns XYCC layout and legend paints."""
    flags = _XYCF_FLAG_HAS_CHROME | _XYCF_FLAG_X_MAJOR_AUTO | _XYCF_FLAG_Y_MAJOR_AUTO
    kind_codes = {"linear": 0, "log": 1, "symlog": 2}
    xa = figure.axis_options["x"]
    ya = figure.axis_options["y"]
    x_scale = figure._axis_scale("x")
    y_scale = figure._axis_scale("y")
    x_lo, x_hi = (float(value) for value in figure._range("x"))
    y_lo, y_hi = (float(value) for value in figure._range("y"))
    authored_margins = (0.0, 0.0, 0.0, 0.0)
    if margins is not None:
        flags |= _XYCF_FLAG_AUTHORED_MARGINS
        authored_margins = (
            float(margins[0]),
            float(margins[1]),
            float(margins[2]),
            float(margins[3]),
        )
    padding = (0.0, 0.0, 0.0, 0.0)
    pad = getattr(figure, "padding", None)
    if isinstance(pad, (list, tuple)) and len(pad) == 4:
        flags |= _XYCF_FLAG_PADDING
        padding = (float(pad[0]), float(pad[1]), float(pad[2]), float(pad[3]))
    title = str(figure.title or "").encode("utf-8")
    x_label = str(figure.x_label or xa.get("label") or "").encode("utf-8")
    y_label = str(figure.y_label or ya.get("label") or "").encode("utf-8")
    x_format = b"" if xa.get("format") is None else str(xa.get("format")).encode("utf-8")
    y_format = b"" if ya.get("format") is None else str(ya.get("format")).encode("utf-8")
    tick_kind_code = {"linear": 0, "time": 1, "category": 2}
    tick_kinds = tick_kind_code.get(figure._axis_kind("x"), 0) | (
        tick_kind_code.get(figure._axis_kind("y"), 0) << 8
    )
    x_major: list[float] = []
    y_major: list[float] = []
    if xa.get("tick_values") is not None:
        flags &= ~_XYCF_FLAG_X_MAJOR_AUTO
        # ABI 199: Rust pack_figure_chrome filters through the tick window.
        x_major = [float(value) for value in xa.get("tick_values")]
    if ya.get("tick_values") is not None:
        flags &= ~_XYCF_FLAG_Y_MAJOR_AUTO
        y_major = [float(value) for value in ya.get("tick_values")]
    x_minor = [float(value) for value in (xa.get("minor_tick_values") or ())]
    y_minor = [float(value) for value in (ya.get("minor_tick_values") or ())]
    # ABI 200: Rust pack_figure_chrome filters authored minors through the tick window.
    # ABI 201: product encode passes packed XYPL so polar theta uses the modular sector.
    # ABI 202: hosts pack domain tick-kind (linear/time/category) in XYCF 154–155.
    # ABI 203: hosts pack ABI 123 collision strategy/anchor/gaps in XYCF 12–15.
    x_labels = xa.get("tick_labels")
    y_labels = ya.get("tick_labels")
    collision_header, collision_extra = _pack_tick_collision(xa, ya, figure)
    if x_labels is not None:
        flags |= _XYCF_FLAG_X_TICK_LABELS
    if y_labels is not None:
        flags |= _XYCF_FLAG_Y_TICK_LABELS
    chrome = _pack_xych(figure)
    legend_loc = b""
    legend_title = b""
    legend_ncols = 1
    legend_font_size = 0.0
    legend_title_font_size = 0.0
    legend_flags = 0
    legend_text_rgba = b"\x00\x00\x00\x00"
    legend_frame_rgba = b"\x00\x00\x00\x00"
    legend_meta = b""
    legend_lens: list[int] = []
    legend_blob = b""
    legend_count = 0
    if figure.show_legend:
        flags |= _XYCF_FLAG_HAS_LEGEND
        legend_flags |= _XYCF_LEGEND_SHOW
        options = dict(figure.legend_options or {})
        unsupported = {
            key
            for key in options
            if key not in {"loc", "title", "ncols", "style", "highlight", "toggle"}
        }
        if unsupported:
            legend_flags |= _XYCF_LEGEND_UNSUPPORTED_KEYS
        legend_ncols = int(options.get("ncols") or 1)
        if "toggle" in options and options["toggle"] is not False:
            legend_flags |= _XYCF_LEGEND_TOGGLE
        if "highlight" in options and options["highlight"] is not False:
            legend_flags |= _XYCF_LEGEND_HIGHLIGHT
        authored_loc = options.get("loc")
        if authored_loc is not None:
            legend_flags |= _XYCF_LEGEND_AUTHORED_LOC
            # ABI 197: Rust encode_product settles loc="best" from XYCL/XYNM.
            legend_loc = str(authored_loc).encode("utf-8")
        style = dict(options.get("style") or {})
        if set(style) - {"background", "color", "font_size", "title_font_size"}:
            legend_flags |= _XYCF_LEGEND_UNSUPPORTED_STYLE
        authored_font_size = style.get("font_size")
        authored_title_font_size = style.get("title_font_size")
        if authored_font_size is not None:
            legend_flags |= _XYCF_LEGEND_AUTHORED_FONT
            legend_font_size = float(authored_font_size)
        if authored_title_font_size is not None:
            legend_flags |= _XYCF_LEGEND_AUTHORED_TITLE_FONT
            legend_title_font_size = float(authored_title_font_size)
        title_value = options.get("title")
        if isinstance(title_value, bool):
            title_value = str(title_value).lower()
        legend_title = str("" if title_value is None else title_value).encode("utf-8")
        if "color" in style:
            legend_flags |= _XYCF_LEGEND_AUTHORED_COLOR
            legend_text_rgba = bytes(_rgba(str(style["color"]), 1.0))
        if "background" in style:
            legend_flags |= _XYCF_LEGEND_AUTHORED_BACKGROUND
            legend_frame_rgba = bytes(_rgba(str(style["background"]), 1.0))
    colorbar_obs = 0
    colorbar_stop_count = 0
    colorbar_tick_count = 0
    colorbar_title = b""
    colorbar_lo = 0.0
    colorbar_hi = 0.0
    colorbar_text_rgba = bytes((32, 32, 32, 255))
    colorbar_stops: list[tuple[float, bytes]] = []
    colorbar_ticks: list[float] = []
    options = getattr(figure, "colorbar_options", None)
    if colorbar_ok and options:
        flags |= _XYCF_FLAG_HAS_COLORBAR
        domain = options.get("domain")
        stops = options.get("stops")
        colorbar_lo, colorbar_hi = (float(domain[0]), float(domain[1]))
        parsed = [(float(item[0]), bytes(item[1])) for item in stops]
        colorbar_stops = parsed
        colorbar_stop_count = len(parsed)
        side = options.get("side", "right")
        if side == "bottom":
            colorbar_obs |= _XYCF_CB_HORIZONTAL
        elif side not in {"right", "bottom"}:
            colorbar_obs |= _XYCF_CB_INVALID_SIDE
        if options.get("minor_ticks"):
            colorbar_obs |= _XYCF_CB_MINOR
        colorbar_title = str(options.get("title", "")).encode("utf-8")
        colorbar_text_rgba = bytes(options.get("text_rgba", (32, 32, 32, 255)))
        raw_ticks = options.get("ticks")
        if raw_ticks is not None:
            colorbar_ticks = [float(value) for value in raw_ticks]
            colorbar_tick_count = len(colorbar_ticks)
    header = _XYCF_HEADER.pack(
        b"XYCF",
        1,
        flags,
        collision_header,
        float(width),
        float(height),
        *authored_margins,
        *padding,
        kind_codes[x_scale],
        kind_codes[y_scale],
        x_lo,
        x_hi,
        float(xa.get("constant") or 1.0),
        y_lo,
        y_hi,
        float(ya.get("constant") or 1.0),
        1 if xa.get("nonpositive", "clip") == "mask" else 0,
        1 if ya.get("nonpositive", "clip") == "mask" else 0,
        tick_kinds,
        len(title),
        len(x_label),
        len(y_label),
        len(x_format),
        len(y_format),
        len(x_major),
        len(x_minor),
        len(y_major),
        len(y_minor),
        0 if x_labels is None else len(x_labels),
        0 if y_labels is None else len(y_labels),
        len(chrome),
        len(legend_loc),
        len(legend_title),
        legend_ncols,
        legend_font_size,
        legend_title_font_size,
        legend_flags,
        legend_count,
        legend_text_rgba,
        legend_frame_rgba,
        colorbar_obs,
        colorbar_stop_count,
        colorbar_tick_count,
        len(colorbar_title),
        colorbar_lo,
        colorbar_hi,
        colorbar_text_rgba,
        0,
    )
    payload = bytearray(header)
    payload.extend(title)
    payload.extend(x_label)
    payload.extend(y_label)
    payload.extend(x_format)
    payload.extend(y_format)
    _put_f64s(payload, x_major)
    _put_f64s(payload, x_minor)
    _put_f64s(payload, y_major)
    _put_f64s(payload, y_minor)
    _put_tick_labels(payload, None if x_labels is None else list(x_labels))
    _put_tick_labels(payload, None if y_labels is None else list(y_labels))
    payload.extend(chrome)
    payload.extend(legend_loc)
    payload.extend(legend_title)
    payload.extend(legend_meta)
    for length in legend_lens:
        payload.extend(int(length).to_bytes(4, "little"))
    payload.extend(legend_blob)
    for value, rgba in colorbar_stops:
        payload.extend(struct.pack("<d", value))
        payload.extend(rgba)
    _put_f64s(payload, colorbar_ticks)
    payload.extend(colorbar_title)
    payload.extend(collision_extra)
    return bytes(payload)


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


def _density_aggregates_color(trace: Any) -> bool:
    """LOD doc §2: density scatter aggregates a color channel into the blit."""
    if str(getattr(trace, "kind", "") or "") != "scatter" or not trace.use_density():
        return False
    return set(trace.per_item_channel_names()) <= {"color"}


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


def _figure_trace_support_flags(trace: Any, polar: bool = False) -> tuple[int, str]:
    """Observe per-trace Scene allowlist bits; Rust owns the diagnostic."""
    kind = str(getattr(trace, "kind", "") or "mark")
    style = getattr(trace, "style", None) or {}
    flags = 0
    kind_class = _native.scene_kind_class(kind)
    if not _native.scene_kind_admit(kind):
        flags |= _XYFS_TRACE_UNSUPPORTED_KIND
    if getattr(trace, "x_axis", "x") != "x" or getattr(trace, "y_axis", "y") != "y":
        flags |= _XYFS_TRACE_NON_PRIMARY_AXIS
    if getattr(trace, "hidden", False) or (
        trace.has_per_item_channels() and not _density_aggregates_color(trace)
    ):
        flags |= _XYFS_TRACE_HIDDEN_OR_PER_ITEM
    if style.get("marker_glyph") is not None:
        glyph = style.get("marker_glyph")
        if (
            kind != "scatter"
            or style.get("marker_path") is not None
            or _admitted_marker_glyph(glyph) is None
        ):
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
        curve_code = _native.scene_curve_classify(curve)
        if curve_code == 1:
            if not (kind_class & (_SCENE_KIND_CLASS_LINE | _SCENE_KIND_CLASS_BAND)):
                flags |= _XYFS_TRACE_DASHED_MARKERS
        elif curve_code != 0:
            flags |= _XYFS_TRACE_DASHED_MARKERS
    linecap = style.get("linecap")
    if linecap is not None and _parse_scene_linecap(linecap) is False:
        flags |= _XYFS_TRACE_DASHED_MARKERS
    dash = style.get("dash")
    if dash is not None and _parse_scene_dash(dash) is False:
        flags |= _XYFS_TRACE_DASHED_MARKERS
    if kind_class & (_SCENE_KIND_CLASS_RECT | _SCENE_KIND_CLASS_HEATMAP):
        flags |= _rect_extra_flags(style, kind, polar)
    if kind_class & _SCENE_KIND_CLASS_HEXBIN and not _native.scene_hexbin_reduce_admit(
        style.get("reduce")
    ):
        flags |= _XYFS_TRACE_CUSTOM_HEX_REDUCE
    if kind_class & _SCENE_KIND_CLASS_HEATMAP and _heatmap_uses_colormap(trace):
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
    if not _native.scene_hexbin_pitch_admit(dx, dy):
        raise UnsupportedSceneV3("Scene v12 hexbin requires finite hex_dx/hex_dy cell pitch")
    return dx, dy


def _hexbin_packs_colormap_plane(trace: Any) -> bool:
    """Return whether hosts should pack this hexbin's metric as an XYTA plane.

    Rust owns tessellation vs fail-closed from the packed plane (ABI 189).
    Missing colormap or length mismatch fail closed in XYFS/attach rather than
    in this packer. Polar uses the same 1×N plane (ABI 194).
    """
    if not (
        _native.scene_kind_class(str(getattr(trace, "kind", "") or "")) & _SCENE_KIND_CLASS_HEXBIN
    ):
        return False
    channel = getattr(trace, "color_ch", None)
    if channel is None:
        return False
    return _native.scene_hexbin_colormap_plane_admit(
        getattr(channel, "mode", None),
        1 if getattr(channel, "values", None) is not None else 0,
    )


def _hexbin_count(trace: Any) -> int:
    column = _trace_column(trace, "x")
    return 0 if column is None else int(len(column))


def _hexbin_cell_rgba8(trace: Any) -> bytes | None:
    """Pack one RGBA8 pixel per occupied hex cell."""
    n = _hexbin_count(trace)
    fallback = str((getattr(trace, "style", None) or {}).get("color", "#3987e5"))
    return _channel_end_rgba8(getattr(trace, "color_ch", None), n, fallback)


def _hexbin_packs_rgba_plane(trace: Any) -> bool:
    """Return whether hosts should pack this hexbin's per-cell RGBA as XYTA.

    Categorical and `direct_rgba` channels intern onto HexCell PolyFills as a
    1×N XYHP RGBA plane (ABI 194). Constant paint stays on the shared style.
    """
    if not (
        _native.scene_kind_class(str(getattr(trace, "kind", "") or "")) & _SCENE_KIND_CLASS_HEXBIN
    ):
        return False
    channel = getattr(trace, "color_ch", None)
    if channel is None:
        return False
    if not _native.scene_hexbin_rgba_plane_admit(getattr(channel, "mode", None)):
        return False
    return _hexbin_cell_rgba8(trace) is not None


def _hexbin_packs_paint_plane(trace: Any) -> bool:
    return _hexbin_packs_colormap_plane(trace) or _hexbin_packs_rgba_plane(trace)


def _scatter_count(trace: Any) -> int:
    column = _trace_column(trace, "x")
    return 0 if column is None else int(len(column))


def _scatter_packs_paint_plane(trace: Any) -> bool:
    """Return whether hosts should pack per-point scatter paint as XYTA.

    Per-item fill/stroke/width/opacity intern onto Scatter records as XYHP
    kind 7 (ABI 196). Per-item size and symbol stay fail-closed. Density
    scatter keeps the blit path. Paint-channel names are ABI 241.
    """
    if str(getattr(trace, "kind", "") or "") != "scatter":
        return False
    if getattr(trace, "use_density", lambda: False)():
        return False
    names = set(getattr(trace, "per_item_channel_names", lambda: ())())
    if not names:
        return False
    return all(_native.scene_scatter_paint_channel_admit(name) for name in names)


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


def _mesh_count(trace: Any) -> int:
    column = _trace_column(trace, "x0")
    return 0 if column is None else int(len(column))


def _mesh_joined_fill(trace: Any) -> bool:
    return bool((getattr(trace, "style", None) or {}).get("joined_fill"))


def _mesh_packs_paint_plane(trace: Any) -> bool:
    """Return whether hosts should pack per-face mesh paint as XYTA.

    Custom `role` is identity metadata. Per-item fill/stroke/width intern onto
    TriangleFace PolyFills as XYHP kind 6 (ABI 195). `joined_fill` stays one
    ring and cannot represent per-face paint. Kind / joined / per-item admit
    is ABI 244; field picking and per-item gathering stay host.
    """
    return _native.scene_mesh_paint_plane_admit(
        str(getattr(trace, "kind", "") or ""),
        1 if _mesh_joined_fill(trace) else 0,
        1 if bool(getattr(trace, "has_per_item_channels", lambda: False)()) else 0,
    )


def _item_apply_opacity(trace: Any, packed: bytes, n: int) -> bytes | None:
    channels = getattr(trace, "style_channels", None) or {}
    opacity_ch = channels.get("opacity")
    artist_ch = channels.get("artist_alpha")
    if opacity_ch is None and artist_ch is None:
        return packed
    artist = None
    if artist_ch is not None:
        artist = np.asarray(getattr(artist_ch, "values", None), dtype=np.float64).reshape(-1)
    opacity = None
    if opacity_ch is not None:
        opacity = np.asarray(getattr(opacity_ch, "values", None), dtype=np.float64).reshape(-1)
    return _native.scene_item_apply_opacity(packed, n, artist, opacity)


def _item_fill_rgba8(trace: Any, n: int) -> bytes | None:
    fallback = str((getattr(trace, "style", None) or {}).get("color", "#3987e5"))
    channel = getattr(trace, "color_ch", None)
    packed = _channel_end_rgba8(channel, n, fallback)
    if packed is None and channel is not None and getattr(channel, "mode", None) == "continuous":
        values = getattr(channel, "values", None)
        if values is None:
            return None
        scalars = np.ascontiguousarray(np.asarray(values, dtype=np.float64).reshape(-1))
        domain = getattr(channel, "domain", None)
        domain_pair = None
        if domain is not None and len(domain) == 2:
            domain_pair = (float(domain[0]), float(domain[1]))
        t = _native.scene_item_fill_t(scalars, n, domain_pair)
        if t is None:
            return None
        cmap = getattr(channel, "colormap", None) or "viridis"
        try:
            stops = _native.colormap_stops(str(cmap))
            image = _native.colormap_rgba(t, n, 1, stops, 255)
        except (TypeError, ValueError):
            return None
        packed = np.ascontiguousarray(image).reshape(-1).tobytes()
    if packed is None:
        return None
    return _item_apply_opacity(trace, packed, n)


def _item_stroke_rgba8(trace: Any, fills: bytes, n: int) -> bytes | None:
    stroke_ch = getattr(trace, "stroke_ch", None)
    if stroke_ch is not None and getattr(stroke_ch, "mode", None) == "match_fill":
        return fills
    fallback = str((getattr(trace, "style", None) or {}).get("stroke") or "transparent")
    packed = _channel_end_rgba8(stroke_ch, n, fallback)
    if packed is not None:
        return packed
    if stroke_ch is None:
        return _channel_end_rgba8(None, n, fallback)
    return None


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


def _mesh_face_fill_rgba8(trace: Any) -> bytes | None:
    return _item_fill_rgba8(trace, _mesh_count(trace))


def _mesh_face_stroke_rgba8(trace: Any, fills: bytes) -> bytes | None:
    return _item_stroke_rgba8(trace, fills, _mesh_count(trace))


def _mesh_face_widths(trace: Any) -> bytes | None:
    return _item_widths(trace, _mesh_count(trace))


def _heatmap_uses_colormap(trace: Any) -> bool:
    """Return whether a heatmap still needs the compatibility colormap path."""
    style = getattr(trace, "style", None) or {}
    return _native.scene_heatmap_colormap_admit(
        1 if style.get("truecolor") else 0,
        1 if style.get("colormap") is not None else 0,
        1 if getattr(trace, "rgba_grid", None) is not None else 0,
        1 if getattr(trace, "rgba", None) is not None else 0,
    )


def _heatmap_shape(trace: Any) -> tuple[int, int]:
    """Return the finite rows x cols lattice, or fail closed."""
    shape = getattr(trace, "grid_shape", None)
    if shape is None or len(shape) != 2:
        raise UnsupportedSceneV3("Scene v12 heatmap requires a rows x cols grid_shape")
    rows_f, cols_f = float(shape[0]), float(shape[1])
    if not _native.scene_heatmap_shape_admit(rows_f, cols_f):
        raise UnsupportedSceneV3("Scene v12 heatmap requires a positive grid_shape")
    return int(rows_f), int(cols_f)


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
    if not _native.scene_heatmap_extent_admit(x0, x1, y0, y1):
        raise UnsupportedSceneV3("Scene v12 heatmap requires a finite increasing cell extent")
    return x0, x1, y0, y1


def _colormap_stop_bytes(colormap: Any, label: str) -> bytes:
    stops = np.ascontiguousarray(
        [(int(red), int(green), int(blue)) for red, green, blue in colormap],
        dtype=np.uint8,
    )
    if stops.ndim != 2 or stops.shape[1] != 3 or stops.shape[0] < 1:
        raise UnsupportedSceneV3(f"Scene {label} colormap requires RGB stops")
    return np.ascontiguousarray(stops).tobytes()


def _pack_xyta_colormap(style: dict[str, Any]) -> tuple[int, bytes, bytes]:
    flags = 0
    cmap = b""
    stops = b""
    colormap = style.get("colormap")
    if isinstance(colormap, str):
        flags |= _XYTA_HAS_NAMED_CMAP
        cmap = colormap.encode("utf-8")
    elif colormap is not None:
        flags |= _XYTA_HAS_STOPS
        try:
            stops = _colormap_stop_bytes(colormap, "heatmap")
        except (TypeError, ValueError, UnsupportedSceneV3):
            stops = b""
    return flags, cmap, stops


def _pack_xyta(figure: Any) -> bytes:
    """Pack authored heatmap/density attach facts as XYTA v1; Rust emits XYTT."""
    traces = list(getattr(figure, "traces", None) or [])
    records = bytearray(_XYTA_HEADER.pack(b"XYTA", 1, len(traces), 0))
    nan = float("nan")
    for trace in traces:
        style = getattr(trace, "style", None) or {}
        flags = 0
        kind_class = _native.scene_kind_class(str(trace.kind))
        rows = cols = 0
        grid = b""
        rgba = b""
        rgba_grid = b""
        x = b""
        y = b""
        mean_rgba = b""
        idx = b""
        lut = b""
        cmap = b""
        stops = b""
        color_ch_b = b""
        style_color = b""
        domain_x0 = domain_x1 = domain_y0 = domain_y1 = nan
        cmap_lo = cmap_hi = nan
        opacity = fill_opacity = nan
        if kind_class & _SCENE_KIND_CLASS_HEATMAP:
            flags |= _XYTA_HEATMAP
            shape = getattr(trace, "grid_shape", None)
            if shape is not None and len(shape) == 2:
                flags |= _XYTA_SHAPE
                try:
                    rows_f, cols_f = float(shape[0]), float(shape[1])
                except (TypeError, ValueError):
                    rows = cols = 0
                else:
                    if _native.scene_heatmap_shape_admit(rows_f, cols_f):
                        rows, cols = int(rows_f), int(cols_f)
            raw_grid = getattr(trace, "grid", None)
            if raw_grid is not None:
                flags |= _XYTA_HAS_GRID
                grid = np.ascontiguousarray(
                    np.asarray(getattr(raw_grid, "values", raw_grid), dtype=np.float64).reshape(-1)
                ).tobytes()
            packed = getattr(trace, "rgba", None)
            if packed is not None:
                flags |= _XYTA_HAS_RGBA
                rgba = np.ascontiguousarray(
                    np.asarray(packed, dtype=np.uint8).reshape(-1)
                ).tobytes()
            planes = getattr(trace, "rgba_grid", None)
            if planes is not None:
                flags |= _XYTA_HAS_RGBA_GRID
                if len(planes) == 4:
                    channels_f64 = [
                        np.asarray(getattr(plane, "values", plane), dtype=np.float64).reshape(-1)
                        for plane in planes
                    ]
                    rgba_grid = np.ascontiguousarray(np.stack(channels_f64, axis=-1)).tobytes()
            cmap_flags, cmap, stops = _pack_xyta_colormap(style)
            flags |= cmap_flags
            if style.get("truecolor"):
                flags |= _XYTA_TRUECOLOR
            domain = style.get("domain")
            if domain is not None and len(domain) == 2:
                flags |= _XYTA_HAS_DOMAIN
                cmap_lo, cmap_hi = float(domain[0]), float(domain[1])
        elif kind_class & _SCENE_KIND_CLASS_HEXBIN and _hexbin_packs_colormap_plane(trace):
            channel = trace.color_ch
            values = np.ascontiguousarray(np.asarray(channel.values, dtype=np.float64).reshape(-1))
            flags |= _XYTA_HEATMAP | _XYTA_SHAPE | _XYTA_HAS_GRID
            rows, cols = 1, int(values.size)
            grid = values.tobytes()
            cmap_flags, cmap, stops = _pack_xyta_colormap({"colormap": channel.colormap})
            flags |= cmap_flags
            domain = getattr(channel, "domain", None)
            if domain is not None and len(domain) == 2:
                flags |= _XYTA_HAS_DOMAIN
                cmap_lo, cmap_hi = float(domain[0]), float(domain[1])
        elif kind_class & _SCENE_KIND_CLASS_HEXBIN and _hexbin_packs_rgba_plane(trace):
            packed = _hexbin_cell_rgba8(trace)
            if packed is not None:
                n = len(packed) // 4
                flags |= _XYTA_HEATMAP | _XYTA_SHAPE | _XYTA_HAS_GRID | _XYTA_HAS_RGBA
                rows, cols = 1, n
                grid = np.zeros(n, dtype=np.float64).tobytes()
                rgba = packed
        elif (
            kind_class & _SCENE_KIND_CLASS_RIBBON
            and str(getattr(figure, "coords", "cartesian") or "cartesian") != "polar"
            and _ribbon_packs_end_paints(trace)
        ):
            ends = _ribbon_end_rgba_pair(trace)
            if ends is not None:
                source, target = ends
                flags |= _XYTA_RIBBON_ENDS | _XYTA_SHAPE | _XYTA_HAS_RGBA
                rows, cols = 1, len(source) // 4
                rgba = source
                mean_rgba = target
        elif _mesh_packs_paint_plane(trace):
            fills = _mesh_face_fill_rgba8(trace)
            strokes = _mesh_face_stroke_rgba8(trace, fills or b"")
            widths = _mesh_face_widths(trace)
            if fills is not None and strokes is not None and widths is not None:
                n = len(fills) // 4
                flags |= _XYTA_MESH_FACES | _XYTA_SHAPE | _XYTA_HAS_RGBA
                rows, cols = 1, n
                rgba = fills
                mean_rgba = strokes
                x = widths
        elif _scatter_packs_paint_plane(trace):
            fills = _scatter_point_fill_rgba8(trace)
            strokes = _scatter_point_stroke_rgba8(trace, fills or b"")
            widths = _scatter_point_widths(trace)
            if fills is not None and strokes is not None and widths is not None:
                n = len(fills) // 4
                flags |= _XYTA_SCATTER_PAINT | _XYTA_SHAPE | _XYTA_HAS_RGBA
                rows, cols = 1, n
                rgba = fills
                mean_rgba = strokes
                x = widths
        elif trace.kind == "scatter" and trace.use_density():
            flags |= _XYTA_DENSITY
            xv = _trace_column(trace, "x")
            yv = _trace_column(trace, "y")
            if xv is not None:
                x = np.ascontiguousarray(xv, dtype=np.float64).tobytes()
            if yv is not None:
                y = np.ascontiguousarray(yv, dtype=np.float64).tobytes()
            xr0, xr1 = (float(value) for value in figure._range("x"))
            yr0, yr1 = (float(value) for value in figure._range("y"))
            domain_x0, domain_x1, domain_y0, domain_y1 = xr0, xr1, yr0, yr1
            cmap_flags, cmap, stops = _pack_xyta_colormap(style)
            flags |= cmap_flags
            channel = getattr(trace, "color_ch", None)
            if channel is not None and channel.mode == "constant" and channel.constant is not None:
                flags |= _XYTA_HAS_COLOR_CH
                color_ch_b = str(channel.constant).encode("utf-8")
            if style.get("color") is not None:
                flags |= _XYTA_HAS_STYLE_COLOR
                style_color = str(style.get("color")).encode("utf-8")
            if "opacity" in style:
                flags |= _XYTA_HAS_OPACITY
                opacity = float(style["opacity"])
            if "fill_opacity" in style:
                flags |= _XYTA_HAS_FILL_OPACITY
                fill_opacity = float(style["fill_opacity"])
            bin_colors = channels.resolve_bin_colors(channel, None)
            if bin_colors:
                if "rgba" in bin_colors:
                    mean_rgba = np.ascontiguousarray(
                        np.asarray(bin_colors["rgba"], dtype=np.uint8).reshape(-1)
                    ).tobytes()
                if "idx" in bin_colors:
                    idx = np.ascontiguousarray(
                        np.asarray(bin_colors["idx"], dtype=np.uint8).reshape(-1)
                    ).tobytes()
                if "lut" in bin_colors:
                    lut = np.ascontiguousarray(
                        np.asarray(bin_colors["lut"], dtype=np.uint8).reshape(-1)
                    ).tobytes()
        records.extend(
            _XYTA_PREFIX.pack(
                flags,
                int(getattr(trace, "id", 0)) & 0xFFFFFFFF,
                int(rows),
                int(cols),
                len(grid) // 8,
                len(rgba),
                len(rgba_grid) // 8,
                len(x) // 8,
                len(y) // 8,
                len(mean_rgba),
                len(idx),
                len(lut),
                min(len(cmap), 65535),
                min(len(stops), 65535),
                min(len(color_ch_b), 65535),
                min(len(style_color), 65535),
                float(domain_x0),
                float(domain_x1),
                float(domain_y0),
                float(domain_y1),
                float(cmap_lo),
                float(cmap_hi),
                float(opacity),
                float(fill_opacity),
            )
        )
        records.extend(grid)
        records.extend(rgba)
        records.extend(rgba_grid)
        records.extend(cmap[:65535])
        records.extend(stops[:65535])
        records.extend(color_ch_b[:65535])
        records.extend(style_color[:65535])
        records.extend(x)
        records.extend(y)
        records.extend(mean_rgba)
        records.extend(idx)
        records.extend(lut)
    return bytes(records)


def _pack_xycl_column(column: np.ndarray | None) -> tuple[int, bytes]:
    if column is None or len(column) == 0:
        return 0, b""
    arr = np.ascontiguousarray(np.asarray(column, dtype=np.float64).reshape(-1))
    return int(arr.size), arr.tobytes()


def _pack_xycl(figure: Any) -> bytes:
    """Pack authored kind/coords/id plus canonical columns as XYCL v1."""
    traces = list(getattr(figure, "traces", None) or [])
    coords = 1 if str(getattr(figure, "coords", "cartesian") or "cartesian") == "polar" else 0
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


def _parse_scene_dash(value: Any) -> list[float] | None | bool:
    """Return a 2–8 length pattern, None for solid, False if unusable on Scene."""
    if value is None:
        return None
    if isinstance(value, str):
        if not value:
            return False
        return _native.scene_dash_admit(value)
    if isinstance(value, (list, tuple)):
        try:
            lengths = [float(part) for part in value]
        except (TypeError, ValueError):
            return False
        return _native.scene_dash_admit("", lengths, use_lengths=True)
    return False


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


def _fill_is_gradient_authoring(fill: Any) -> bool:
    if isinstance(fill, dict):
        return True
    if not isinstance(fill, str):
        return False
    return _native.scene_linear_gradient_prefix(fill)


def _admitted_fill_gradient_from_fill(fill: Any, mark_color: str) -> dict[str, Any] | None:
    """Return a resolved XYGR payload, or None to keep the fill fail-closed."""
    spec: dict[str, Any] | None
    if isinstance(fill, dict) and {"space", "dir", "stops"} <= set(fill):
        spec = fill
    elif isinstance(fill, dict):
        extra = [key for key in fill if key not in {"gradient", "space"}]
        if extra:
            return None
        gradient = fill.get("gradient")
        if not isinstance(gradient, str):
            return None
        raw_space = fill.get("space", "mark")
        space = "mark" if raw_space is None else str(raw_space)
        code, spec = _native.scene_parse_linear_gradient(gradient, space)
        if code != 1:
            return None
    elif isinstance(fill, str):
        code, spec = _native.scene_parse_linear_gradient(fill, "mark")
        if code != 1:
            return None
    else:
        return None
    if not spec:
        return None
    space = spec.get("space")
    direction = spec.get("dir")
    stops = spec.get("stops")
    if not isinstance(stops, (list, tuple)):
        return None
    ts: list[float] = []
    css_stops: list[str] = []
    for stop in stops:
        if not isinstance(stop, (list, tuple)) or len(stop) != 2:
            return None
        try:
            ts.append(float(stop[0]))
        except (TypeError, ValueError):
            return None
        css_stops.append(str(stop[1]))
    rgba = _native.scene_fill_gradient_admit(
        str(space),
        str(direction),
        ts,
        css_stops,
        mark_color,
    )
    if rgba is None:
        return None
    resolved = [(ts[i], rgba[i]) for i in range(len(ts))]
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


def _channel_constant_css(channel: Any) -> str | None:
    if channel is None:
        return None
    if getattr(channel, "mode", None) != "constant":
        return None
    constant = getattr(channel, "constant", None)
    if constant is None:
        return None
    return str(constant)


def _trace_source_color_css(trace: Any) -> str:
    css = _channel_constant_css(getattr(trace, "color_ch", None))
    if css is not None:
        return css
    return str((getattr(trace, "style", None) or {}).get("color") or "#3987e5")


def _classify_ribbon_color2(trace: Any) -> str:
    """Classify two-ended ribbon paint: absent, solid, gradient, ends, or fail."""
    color2 = getattr(trace, "color2_ch", None)
    has_color2 = color2 is not None
    kind_is_ribbon = str(getattr(trace, "kind", "") or "") == "ribbon"
    target = _channel_constant_css(color2) if has_color2 else None
    source_const = _channel_constant_css(getattr(trace, "color_ch", None))
    source_paint = _trace_source_color_css(trace)
    has_fill = "fill" in (getattr(trace, "style", None) or {})
    both_const = target is not None and source_const is not None
    has_end_pair = False
    if has_color2 and kind_is_ribbon and not both_const and not has_fill:
        has_end_pair = _ribbon_end_rgba_pair(trace) is not None
    return _native.scene_ribbon_color2_classify(
        has_color2,
        kind_is_ribbon,
        source_const,
        target,
        source_paint,
        has_fill,
        has_end_pair,
    )


def _ribbon_count(trace: Any) -> int:
    raw = getattr(trace, "count", None)
    if raw is not None:
        try:
            return int(raw)
        except (TypeError, ValueError):
            pass
    column = _trace_column(trace, "x0")
    return 0 if column is None else int(len(column))


def _channel_end_rgba8(channel: Any, n: int, fallback: str) -> bytes | None:
    """Pack n RGBA8 pixels from a constant or direct_rgba channel."""
    if n < 1:
        return None
    if channel is None:
        rgba = _native.css_color_rgba(fallback, 1.0)
        return bytes(rgba) * n
    mode = getattr(channel, "mode", None)
    if mode == "constant":
        css = getattr(channel, "constant", None)
        if css is None:
            return None
        try:
            rgba = _native.css_color_rgba(str(css), 1.0)
        except ValueError:
            return None
        return bytes(rgba) * n
    if mode == "direct_rgba":
        packed = getattr(channel, "rgba", None)
        if packed is None:
            return None
        values = np.asarray(packed)
        if values.ndim == 1 and values.size == n * 4:
            values = values.reshape(n, 4)
        if values.shape != (n, 4):
            return None
        if values.dtype == np.uint8:
            return np.ascontiguousarray(values).tobytes()
        return np.ascontiguousarray(channels._quantized_rgba8(values.astype(np.float64))).tobytes()
    if mode == "categorical":
        try:
            resolved = channels.resolve_direct_rgba(channel)
        except (TypeError, ValueError):
            return None
        return _channel_end_rgba8(resolved, n, fallback)
    return None


def _ribbon_end_rgba_pair(trace: Any) -> tuple[bytes, bytes] | None:
    n = _ribbon_count(trace)
    if n < 1:
        return None
    fallback = _trace_source_color_css(trace)
    source = _channel_end_rgba8(getattr(trace, "color_ch", None), n, fallback)
    target = _channel_end_rgba8(getattr(trace, "color2_ch", None), n, fallback)
    if source is None or target is None:
        return None
    return source, target


def _ribbon_packs_end_paints(trace: Any, polar: bool = False) -> bool:
    """Return whether hosts should pack this ribbon's source/target RGBA8 ends.

    Polar stays off this path. Rust intern unique pairs onto Band+XYGR (ABI 190).
    """
    if polar or str(getattr(trace, "kind", "") or "") != "ribbon":
        return False
    return _classify_ribbon_color2(trace) == "ends"


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
_XYTO_ENVELOPE = struct.Struct("<4sIII")
_XYTO_PREFIX = struct.Struct("<4s2H4s4s2dHBBHHII4BII2d84x")
_XYTA_HEADER = struct.Struct("<4sIII")
_XYTA_PREFIX = struct.Struct("<II2i8I4H6d2f16x")
_XYTT_ENVELOPE = struct.Struct("<4sIII")
_XYTT_EXTRA = struct.Struct("<IIII4d")
_XYCL_HEADER = struct.Struct("<4sIII")
_XYCL_PREFIX = struct.Struct("<HBxIQ7I4x")
_XYNM_HEADER = struct.Struct("<4sIII")
_XYNM_PREFIX = struct.Struct("<H")
_XYSD_HEADER = struct.Struct("<4sIII")
_XYSD_PREFIX = struct.Struct("<4s4sdBBH6I4x")
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
_XYTO_LINECAP_NONE = 255
_GRAD_DIR_FROM_CODE = {0: "down", 1: "up", 2: "right", 3: "left"}


def _pack_marker_blob(value: Any) -> bytes | None:
    if not isinstance(value, dict):
        return None
    contours = value.get("contours")
    if not isinstance(contours, (list, tuple)):
        return None
    payload = bytearray(struct.pack("<I", len(contours)))
    payload.append(1 if value.get("filled", True) else 0)
    payload.extend(b"\0\0\0")
    try:
        for contour in contours:
            values = [float(item) for item in contour]
            payload.extend(struct.pack("<I", len(values)))
            if values:
                payload.extend(struct.pack(f"<{len(values)}d", *values))
    except (TypeError, ValueError):
        return None
    return bytes(payload)


def _pack_gradient_spec(fill: dict[str, Any]) -> bytes | None:
    space = _native.scene_gradient_space(fill.get("space"))
    direction = _native.scene_gradient_dir(fill.get("dir"))
    stops = fill.get("stops")
    if not isinstance(stops, (list, tuple)):
        return None
    payload = bytearray(bytes((space, direction, len(stops) & 0xFF, 0)))
    try:
        for stop in stops:
            if not isinstance(stop, (list, tuple)) or len(stop) != 2:
                return None
            css = str(stop[1]).encode("utf-8")
            payload.extend(struct.pack("<dH", float(stop[0]), len(css)))
            payload.extend(css)
    except (TypeError, ValueError):
        return None
    return bytes(payload)


def _pack_xytc(figure: Any) -> bytes:
    """Pack authored per-trace style literals as XYTC v1; Rust compiles XYTO."""
    traces = list(getattr(figure, "traces", None) or [])
    records = bytearray(_XYTC_HEADER.pack(b"XYTC", 1, len(traces), 0))
    show_legend = bool(getattr(figure, "show_legend", True))
    nan = float("nan")
    for trace in traces:
        style = getattr(trace, "style", None) or {}
        flags = 0
        kind_name = str(trace.kind)
        kind = kind_name.encode("utf-8")
        kind_class = _native.scene_kind_class(kind_name)
        name = str(trace.name) if getattr(trace, "name", None) else ""
        if name:
            flags |= _XYTC_HAS_NAME
        name_b = name.encode("utf-8")
        symbol = str(style.get("symbol", "circle") or "")
        symbol_b = symbol.encode("utf-8")
        opacity = float(style.get("opacity", 1.0))
        fill_opacity = stroke_opacity = line_opacity = 1.0
        if kind_class & _SCENE_KIND_CLASS_OPACITY:
            fill_opacity = float(style.get("fill_opacity", 1.0))
            stroke_opacity = float(style.get("stroke_opacity", 1.0))
        if kind_class & _SCENE_KIND_CLASS_BAND:
            line_opacity = float(style.get("line_opacity", 1.0))
        size = nan
        if "size" in style:
            flags |= _XYTC_HAS_SIZE
            size = float(style["size"])
        size_ch_value = nan
        size_ch = getattr(trace, "size_ch", None)
        if size_ch is not None:
            flags |= _XYTC_HAS_SIZE_CH
            if getattr(size_ch, "constant", None) is not None:
                size_ch_value = float(size_ch.constant)
        stroke_width = width = line_width = 0.0
        if "stroke_width" in style:
            flags |= _XYTC_HAS_STROKE_WIDTH
            stroke_width = float(style["stroke_width"])
        if "width" in style:
            flags |= _XYTC_HAS_WIDTH
            width = float(style["width"])
        if "line_width" in style:
            flags |= _XYTC_HAS_LINE_WIDTH
            line_width = float(style["line_width"])
        hex_dx = hex_dy = nan
        if kind_class & _SCENE_KIND_CLASS_HEXBIN:
            flags |= _XYTC_HAS_HEX
            raw_dx = style.get("hex_dx", style.get("dx"))
            raw_dy = style.get("hex_dy", style.get("dy"))
            if raw_dx is not None:
                hex_dx = float(raw_dx)
            if raw_dy is not None:
                hex_dy = float(raw_dy)
        if kind_class & _SCENE_KIND_CLASS_BAND and "stroke_perimeter" in style:
            perimeter = style["stroke_perimeter"]
            if not isinstance(perimeter, bool):
                flags |= _XYTC_PERIMETER_INVALID
            elif perimeter:
                flags |= _XYTC_PERIMETER_TRUE
        dash_b = b""
        dash_pattern: list[float] = []
        dash = style.get("dash")
        if isinstance(dash, str):
            dash_b = dash.encode("utf-8")
        elif isinstance(dash, (list, tuple)):
            flags |= _XYTC_HAS_DASH_PATTERN
            try:
                dash_pattern = [float(part) for part in dash]
            except (TypeError, ValueError):
                dash_pattern = []
        linecap_b = str(style["linecap"]).encode("utf-8") if "linecap" in style else b""
        step_b = str(style["step"]).encode("utf-8") if style.get("step") is not None else b""
        curve_b = str(style["curve"]).encode("utf-8") if style.get("curve") is not None else b""
        fill_css = b""
        fill_space = b""
        gradient_blob = b""
        if "fill" in style:
            flags |= _XYTC_HAS_FILL
            fill = style["fill"]
            if isinstance(fill, str):
                fill_css = fill.encode("utf-8")
            elif isinstance(fill, dict) and {"space", "dir", "stops"} <= set(fill):
                flags |= _XYTC_HAS_GRADIENT_SPEC
                gradient_blob = _pack_gradient_spec(fill) or b""
            elif isinstance(fill, dict):
                flags |= _XYTC_HAS_FILL_DICT
                fill_css = str(fill.get("gradient") or "").encode("utf-8")
                fill_space = str(fill.get("space") or "mark").encode("utf-8")
        stroke_css = str(style["stroke"]).encode("utf-8") if "stroke" in style else b""
        if "stroke" in style:
            flags |= _XYTC_HAS_STROKE
        line_color = str(style["line_color"]).encode("utf-8") if "line_color" in style else b""
        if "line_color" in style:
            flags |= _XYTC_HAS_LINE_COLOR
        color_css = str(style["color"]).encode("utf-8") if "color" in style else b""
        color_mode = b""
        color_const = b""
        channel = getattr(trace, "color_ch", None)
        if channel is not None:
            flags |= _XYTC_COLOR_CH
            color_mode = str(getattr(channel, "mode", "") or "").encode("utf-8")
            if getattr(channel, "constant", None) is not None:
                flags |= _XYTC_COLOR_CH_CONSTANT
                color_const = str(channel.constant).encode("utf-8")
        color2_class = _classify_ribbon_color2(trace)
        if color2_class == "fail":
            flags |= _XYTC_COLOR2
        elif color2_class == "gradient":
            if flags & (_XYTC_HAS_FILL | _XYTC_HAS_GRADIENT_SPEC):
                flags |= _XYTC_COLOR2
            else:
                spec = _ribbon_color2_gradient_spec(trace)
                packed_gradient = _pack_gradient_spec(spec) if spec is not None else None
                if packed_gradient:
                    flags |= _XYTC_HAS_FILL | _XYTC_HAS_GRADIENT_SPEC
                    gradient_blob = packed_gradient
                else:
                    flags |= _XYTC_COLOR2
        if trace.kind == "scatter" and trace.use_density():
            flags |= _XYTC_USE_DENSITY
        if show_legend:
            flags |= _XYTC_SHOW_LEGEND
        marker_blob = b""
        if trace.kind == "scatter" and style.get("marker_path") is not None:
            packed_marker = _pack_marker_blob(style.get("marker_path"))
            if packed_marker:
                flags |= _XYTC_HAS_MARKER
                marker_blob = packed_marker
        elif trace.kind == "scatter":
            packed_glyph = _admitted_marker_glyph(style.get("marker_glyph"))
            if packed_glyph is not None:
                flags |= _XYTC_HAS_GLYPH
                marker_blob = packed_glyph
        if str(trace.kind) == "triangle_mesh" and style.get("joined_fill"):
            flags |= _XYTC_JOINED_FILL
        r_tip = 0.0
        r_base = 0.0
        wedge_gap = 0.0
        if str(trace.kind) in {"bar", "column", "histogram", "heatmap", "violin", "box"}:
            radius = style.get("corner_radius", 0.0)
            if isinstance(radius, (list, tuple)) and len(radius) == 2:
                r_tip = float(radius[0])
                r_base = float(radius[1])
            else:
                r_tip = r_base = float(radius or 0.0)
            if r_tip or r_base:
                flags |= _XYTC_HAS_CORNER_RADIUS
            if str(trace.kind) in {"bar", "column", "histogram"}:
                wedge_gap = float(style.get("wedge_gap", 0.0) or 0.0)
                if wedge_gap:
                    flags |= _XYTC_HAS_WEDGE_GAP
        records.extend(
            _XYTR_PREFIX.pack(
                b"XYTR",
                1,
                len(kind),
                flags,
                len(name_b),
                len(symbol_b),
                opacity,
                fill_opacity,
                stroke_opacity,
                line_opacity,
                size,
                size_ch_value,
                stroke_width,
                width,
                line_width,
                hex_dx,
                hex_dy,
                len(dash_b),
                len(linecap_b),
                len(step_b),
                len(curve_b),
                len(fill_css),
                len(stroke_css),
                len(line_color),
                len(color_css),
                len(color_mode),
                len(color_const),
                len(fill_space),
                0,
                len(dash_pattern),
                len(marker_blob),
                len(gradient_blob),
                r_tip,
                r_base,
                wedge_gap,
            )
        )
        records.extend(kind)
        records.extend(name_b)
        records.extend(symbol_b)
        records.extend(dash_b)
        records.extend(linecap_b)
        records.extend(step_b)
        records.extend(curve_b)
        records.extend(fill_css)
        records.extend(stroke_css)
        records.extend(line_color)
        records.extend(color_css)
        records.extend(color_mode)
        records.extend(color_const)
        records.extend(fill_space)
        if dash_pattern:
            records.extend(struct.pack(f"<{len(dash_pattern)}d", *dash_pattern))
        records.extend(marker_blob)
        records.extend(gradient_blob)
    return bytes(records)


def _unpack_marker_blob(blob: bytes) -> dict[str, Any] | None:
    if len(blob) < 8:
        return None
    n_contours = struct.unpack_from("<I", blob, 0)[0]
    filled = blob[4] != 0
    at = 8
    contours: list[list[float]] = []
    for _ in range(int(n_contours)):
        n_values = struct.unpack_from("<I", blob, at)[0]
        at += 4
        values = list(struct.unpack_from(f"<{n_values}d", blob, at))
        at += int(n_values) * 8
        contours.append(values)
    return {"contours": contours, "filled": bool(filled)}


def _unpack_gradient_blob(blob: bytes) -> dict[str, Any] | None:
    if len(blob) < 4:
        return None
    space, direction, n_stops = blob[0], blob[1], blob[2]
    at = 4
    stops: list[tuple[float, tuple[int, int, int, int]]] = []
    for _ in range(int(n_stops)):
        t = float(struct.unpack_from("<f", blob, at)[0])
        rgba = (int(blob[at + 4]), int(blob[at + 5]), int(blob[at + 6]), int(blob[at + 7]))
        at += 8
        stops.append((t, rgba))
    return {
        "space": "plot" if space else "mark",
        "dir": _GRAD_DIR_FROM_CODE.get(int(direction), "down"),
        "stops": stops,
    }


def _unpack_xyto(blob: bytes) -> list[dict[str, Any]]:
    """Split Rust-owned XYTO compile output into per-trace Scene fields."""
    if len(blob) < _XYTO_ENVELOPE.size or blob[:4] != b"XYTO":
        raise ValueError("invalid scene trace compile packing")
    _magic, version, n_traces, _reserved = _XYTO_ENVELOPE.unpack_from(blob, 0)
    if version != 1:
        raise ValueError("invalid scene trace compile facts version")
    at = _XYTO_ENVELOPE.size
    compiled: list[dict[str, Any]] = []
    for _ in range(int(n_traces)):
        (
            magic,
            rec_version,
            _rec_reserved,
            fill,
            stroke,
            stroke_width,
            diameter,
            symbol,
            legend_kind,
            legend_include,
            legend_symbol,
            authored_step,
            fact_bits,
            dash_count,
            linecap,
            has_marker,
            has_gradient,
            _pad,
            marker_len,
            gradient_len,
            hex_dx,
            hex_dy,
        ) = _XYTO_PREFIX.unpack_from(blob, at)
        if magic != b"XYTO" or rec_version != 1:
            raise ValueError("invalid scene trace compile packing")
        at += _XYTO_PREFIX.size
        dash = None
        if dash_count:
            dash = list(struct.unpack(f"<{dash_count}d", blob[at : at + dash_count * 8]))
            at += int(dash_count) * 8
        marker = blob[at : at + marker_len]
        at += int(marker_len)
        gradient = blob[at : at + gradient_len]
        at += int(gradient_len)
        compiled.append(
            {
                "style": (tuple(fill), tuple(stroke), float(stroke_width)),
                "dash": dash,
                "linecap": None if linecap == _XYTO_LINECAP_NONE else int(linecap),
                "marker_path": _unpack_marker_blob(marker) if has_marker and marker else None,
                "fill_gradient": _unpack_gradient_blob(gradient)
                if has_gradient and gradient
                else None,
                "diameter": float(diameter),
                "symbol": int(symbol),
                "legend_kind": int(legend_kind),
                "legend_include": bool(legend_include),
                "legend_symbol": int(legend_symbol),
                "authored_step": int(authored_step),
                "fact_bits": int(fact_bits),
                "hex_dx": float(hex_dx),
                "hex_dy": float(hex_dy),
            }
        )
    if at != len(blob):
        raise ValueError("invalid scene trace compile packing")
    return compiled


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


def _unpack_xytt(blob: bytes) -> list[dict[str, Any]]:
    """Split Rust-owned XYTT attach output into per-trace Scene fields."""
    if len(blob) < _XYTT_ENVELOPE.size or blob[:4] != b"XYTT":
        raise ValueError("invalid scene trace attach packing")
    _magic, version, n_traces, _reserved = _XYTT_ENVELOPE.unpack_from(blob, 0)
    if version != 1:
        raise ValueError("invalid scene trace attach facts version")
    at = _XYTT_ENVELOPE.size
    attached: list[dict[str, Any]] = []
    for _ in range(int(n_traces)):
        (
            magic,
            rec_version,
            _rec_reserved,
            fill,
            stroke,
            stroke_width,
            diameter,
            symbol,
            legend_kind,
            legend_include,
            legend_symbol,
            authored_step,
            fact_bits,
            dash_count,
            linecap,
            has_marker,
            has_gradient,
            _pad,
            marker_len,
            gradient_len,
            hex_dx,
            hex_dy,
        ) = _XYTO_PREFIX.unpack_from(blob, at)
        if magic != b"XYTO" or rec_version != 1:
            raise ValueError("invalid scene trace attach packing")
        heatmap_len, density_len, grid_rows, grid_cols, x0, x1, y0, y1 = _XYTT_EXTRA.unpack_from(
            blob, at + _XYTO_PREFIX.size
        )
        at += _XYTO_PREFIX.size + _XYTT_EXTRA.size
        dash = None
        if dash_count:
            dash = list(struct.unpack(f"<{dash_count}d", blob[at : at + dash_count * 8]))
            at += int(dash_count) * 8
        marker = blob[at : at + marker_len]
        at += int(marker_len)
        gradient = blob[at : at + gradient_len]
        at += int(gradient_len)
        heatmap = blob[at : at + heatmap_len]
        at += int(heatmap_len)
        density = blob[at : at + density_len]
        at += int(density_len)
        columns = None
        if density_len:
            columns = [
                np.asarray([x0, x1], dtype=np.float64),
                np.asarray([y0, y1], dtype=np.float64),
                None,
                None,
                None,
                None,
                None,
            ]
        attached.append(
            {
                "style": (tuple(fill), tuple(stroke), float(stroke_width)),
                "dash": dash,
                "linecap": None if linecap == _XYTO_LINECAP_NONE else int(linecap),
                "marker_path": _unpack_marker_blob(marker) if has_marker and marker else None,
                "fill_gradient": _unpack_gradient_blob(gradient)
                if has_gradient and gradient
                else None,
                "diameter": float(diameter),
                "symbol": int(symbol),
                "legend_kind": int(legend_kind),
                "legend_include": bool(legend_include),
                "legend_symbol": int(legend_symbol),
                "authored_step": int(authored_step),
                "fact_bits": int(fact_bits),
                "hex_dx": float(hex_dx),
                "hex_dy": float(hex_dy),
                "heatmap": bytes(heatmap) if heatmap_len else b"",
                "density": bytes(density) if density_len else b"",
                "grid_rows": float(grid_rows),
                "grid_cols": float(grid_cols),
                "columns": columns,
            }
        )
    if at != len(blob):
        raise ValueError("invalid scene trace attach packing")
    return attached


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


def _unpack_xysd(blob: bytes) -> dict[str, Any]:
    """Split Rust-owned XYSD sidecar output into per-trace Scene fields."""
    if len(blob) < _XYSD_HEADER.size or blob[:4] != b"XYSD":
        raise ValueError("invalid scene sidecar packing")
    _magic, version, n_traces, _reserved = _XYSD_HEADER.unpack_from(blob, 0)
    if version != 1:
        raise ValueError("invalid scene sidecar facts version")
    at = _XYSD_HEADER.size
    styles: list[tuple[tuple[int, ...], tuple[int, ...], float]] = []
    dashes: list[list[float] | None] = []
    linecaps: list[int | None] = []
    marker_paths: list[dict[str, Any] | None] = []
    fill_gradients: list[dict[str, Any] | None] = []
    planes: list[bytes] = []
    legend: list[tuple[int, int, int, str]] = []
    for index in range(int(n_traces)):
        if at + _XYSD_PREFIX.size > len(blob):
            raise ValueError("invalid scene sidecar packing")
        (
            fill,
            stroke,
            stroke_width,
            linecap,
            legend_kind,
            legend_symbol,
            dash_len,
            marker_len,
            gradient_len,
            plane_len,
            name_len,
            _reserved_len,
        ) = _XYSD_PREFIX.unpack_from(blob, at)
        at += _XYSD_PREFIX.size
        need = int(dash_len) + int(marker_len) + int(gradient_len) + int(plane_len) + int(name_len)
        if at + need > len(blob):
            raise ValueError("invalid scene sidecar packing")
        dash_blob = blob[at : at + dash_len]
        at += int(dash_len)
        marker = blob[at : at + marker_len]
        at += int(marker_len)
        gradient = blob[at : at + gradient_len]
        at += int(gradient_len)
        plane = blob[at : at + plane_len]
        at += int(plane_len)
        name = blob[at : at + name_len]
        at += int(name_len)
        styles.append((tuple(fill), tuple(stroke), float(stroke_width)))
        dashes.append(
            list(struct.unpack(f"<{len(dash_blob) // 8}d", dash_blob)) if dash_blob else None
        )
        linecaps.append(None if linecap == _XYTO_LINECAP_NONE else int(linecap))
        marker_paths.append(_unpack_marker_blob(marker) if marker else None)
        fill_gradients.append(_unpack_gradient_blob(gradient) if gradient else None)
        if plane:
            planes.append(bytes(plane))
        if name:
            legend.append((index, int(legend_kind), int(legend_symbol), name.decode("utf-8")))
    if at != len(blob):
        raise ValueError("invalid scene sidecar packing")
    return {
        "styles": styles,
        "dashes": dashes,
        "linecaps": linecaps,
        "marker_paths": marker_paths,
        "fill_gradients": fill_gradients,
        "planes": planes,
        "legend": legend,
    }


def _raise_trace_sidecars(error: _native.SceneTraceSidecarsError) -> NoReturn:
    if error.code == -2:
        raise ValueError("invalid scene sidecar facts version") from error
    raise ValueError("invalid scene sidecar packing") from error


def _raise_annotation_splice(error: _native.SceneAnnotationSpliceError) -> NoReturn:
    if error.code == -2:
        raise ValueError("invalid scene annotation splice version") from error
    raise ValueError("invalid scene annotation splice packing") from error


def _unpack_xyas(blob: bytes) -> dict[str, Any]:
    """Split Rust-owned XYAS splice output into Scene styles, rows, and XYAD."""
    if len(blob) < _XYAS_HEADER.size or blob[:4] != b"XYAS":
        raise ValueError("invalid scene annotation splice packing")
    _magic, version, n_styles, n_rows, xyad_len, _reserved = _XYAS_HEADER.unpack_from(blob, 0)
    if version != 1:
        raise ValueError("invalid scene annotation splice version")
    at = _XYAS_HEADER.size
    need = int(n_styles) * _XYAS_STYLE.size + int(n_rows) * 56 + int(xyad_len)
    if at + need > len(blob):
        raise ValueError("invalid scene annotation splice packing")
    styles: list[tuple[tuple[int, ...], tuple[int, ...], float]] = []
    for _ in range(int(n_styles)):
        fill, stroke, width = _XYAS_STYLE.unpack_from(blob, at)
        styles.append((tuple(fill), tuple(stroke), float(width)))
        at += _XYAS_STYLE.size
    kinds: list[int] = []
    stable_ids: list[int] = []
    style_refs: list[int] = []
    diameters: list[float] = []
    symbols: list[int] = []
    expansion_modes: list[int] = []
    coordinates: list[list[float]] = [[], [], [], []]
    if n_rows:
        raw = np.frombuffer(blob[at : at + int(n_rows) * 56], dtype=np.uint8).reshape(
            int(n_rows), 56
        )
        kinds.extend(int(value) for value in raw[:, 0])
        symbols.extend(int(value) for value in raw[:, 1])
        expansion_modes.extend(int(value) for value in raw[:, 2])
        style_refs.extend(int(value) for value in np.frombuffer(raw[:, 4:8].tobytes(), dtype="<u4"))
        stable_ids.extend(
            int(value) for value in np.frombuffer(raw[:, 8:16].tobytes(), dtype="<u8")
        )
        nums = np.frombuffer(raw[:, 16:56].tobytes(), dtype="<f8").reshape(-1, 5)
        diameters.extend(float(value) for value in nums[:, 0])
        for axis in range(4):
            coordinates[axis].extend(float(value) for value in nums[:, axis + 1])
        at += int(n_rows) * 56
    xyad = bytes(blob[at : at + int(xyad_len)])
    if at + int(xyad_len) != len(blob):
        raise ValueError("invalid scene annotation splice packing")
    return {
        "styles": styles,
        "kinds": kinds,
        "stable_ids": stable_ids,
        "style_refs": style_refs,
        "diameters": diameters,
        "symbols": symbols,
        "expansion_modes": expansion_modes,
        "coordinates": coordinates,
        "xyad": xyad,
    }


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

    # Hosts pack XYTC, XYTA, XYNM, XYCL, XYAF, XYCF, polar, and XYFS; Rust owns
    # compile, attach, sidecars, rows, annotation facts, style sidecars,
    # splice, XYCC/extras packing, viewport/axis scalars, assembled encode,
    # and the figure-compile support probe (ABI 165). Earlier ABIs 148–164
    # remain available for tests. Empty XYFS skips the probe.
    x_span = tuple(float(value) for value in figure._range("x"))
    y_span = tuple(float(value) for value in figure._range("y"))
    x_domain = (x_span[0], x_span[1])
    y_domain = (y_span[0], y_span[1])
    annotation_facts = bytearray()
    for annotation_index, annotation in enumerate(annotations):
        annotation_facts.extend(_pack_xyaf(annotation, annotation_index))
    w = int(width if width is not None else figure.width)
    h = int(height if height is not None else figure.height)
    try:
        return _native.scene_encode_product(
            compile_facts=_pack_xytc(figure),
            attach_facts=_pack_xyta(figure),
            names=_pack_xynm(figure),
            columns=_pack_xycl(figure),
            annotation_facts=bytes(annotation_facts),
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
            polar=_pack_polar_scene_input(figure),
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


def _significant_scene_axis_keys(options: dict[str, Any], *, polar: bool = False) -> list[str]:
    keys = [str(key) for key, value in options.items() if value not in (None, False, [], {})]
    if polar and _scene_tick_label_strategy(options) in {"none", "off", "auto"}:
        keys = [key for key in keys if key not in _POLAR_COLLISION_KEYS]
    return keys


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


def _annotation_has_markup(annotation: Any) -> bool:
    if not isinstance(annotation, dict):
        return False
    if annotation.get("markup") not in (None, ""):
        return True
    style = annotation.get("style") or {}
    return isinstance(style, dict) and style.get("markup") not in (None, "")


_ANNOTATION_TYPOGRAPHY_STYLE_KEYS = frozenset(
    {
        "font_family",
        "font_size",
        "font_weight",
        "font_style",
        "fontFamily",
        "fontSize",
        "fontWeight",
        "fontStyle",
    }
)


def _annotation_has_custom_typography(annotation: Any) -> bool:
    if not isinstance(annotation, dict):
        return False
    style = annotation.get("style") or {}
    if not isinstance(style, dict):
        style = {}
    for key in _ANNOTATION_TYPOGRAPHY_STYLE_KEYS:
        if style.get(key) not in (None, "", False):
            return True
        if annotation.get(key) not in (None, "", False):
            return True
    return False


def _pack_figure_support(
    figure: Any,
    annotations: list[Any],
    colorbar_unsupported: bool,
) -> bytes:
    """Pack literal figure observations, axis keys, and per-trace allowlist flags.

    Scene static SVG/PNG/PDF measure and paint DejaVu Sans (#288). Custom
    ``font-family`` sets ``CUSTOM_FONT``; chart ``class_name`` / ``class_names``,
    ``chrome_styles``, extra ``style`` keys, and annotation ``class_name`` set
    ``BROWSER_CSS``. Rust reports the stable fail-closed diagnostics. Live
    browser widgets still apply CSS outside this encoder.
    """
    flags = 0
    if figure.coords != "cartesian":
        flags |= 1 << 0
    chrome_styles = getattr(figure, "chrome_styles", None) or {}
    if any("font-family" in (style or {}) for style in chrome_styles.values()) or any(
        _annotation_has_custom_typography(annotation) for annotation in annotations
    ):
        flags |= 1 << 1
    if (
        getattr(figure, "class_name", None)
        or getattr(figure, "class_names", None)
        or chrome_styles
        or set(getattr(figure, "style", None) or {}) - {"background", "--chart-bg"}
        or any(annotation.get("class_name") not in (None, "") for annotation in annotations)
    ):
        flags |= 1 << 2
    if any(annotation.get("html") not in (None, "") for annotation in annotations):
        flags |= 1 << 8
    if any(annotation.get("collision") not in (None, "") for annotation in annotations):
        flags |= 1 << 6
    if any(_annotation_has_markup(annotation) for annotation in annotations):
        flags |= 1 << 9
    if any(
        _classify_ribbon_color2(trace) == "fail"
        or (
            getattr(trace, "color_ch", None) is not None
            and (trace.color_ch.mode != "constant" or trace.color_ch.constant is None)
            and not (str(getattr(trace, "kind", "") or "") == "scatter" and trace.use_density())
            and not _hexbin_packs_paint_plane(trace)
            and not _mesh_packs_paint_plane(trace)
            and not _scatter_packs_paint_plane(trace)
            and not (
                str(getattr(figure, "coords", "cartesian") or "cartesian") != "polar"
                and _ribbon_packs_end_paints(trace)
            )
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
        keys = _significant_scene_axis_keys(options, polar=flags & 1 != 0)
        payload.extend(bytes((axis_code, 0, 0, 0)))
        payload.extend(len(keys).to_bytes(4, "little"))
        _xyep_put_keys(payload, keys)
    for trace in traces:
        trace_flags, kind = _figure_trace_support_flags(trace, flags & 1 != 0)
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
    if column is None:
        return False
    return _native.scene_finite_all(column.values)


def _pack_public_export_support(
    figure: Any,
    *,
    width: int | None = None,
    height: int | None = None,
) -> bytes:
    """Pack authored XYEF facts; Rust owns the XYEP envelope (ABI 152)."""
    flags = 0
    if width is None and not isinstance(figure.width, int):
        flags |= 1 << 0
    if height is None and not isinstance(figure.height, int):
        flags |= 1 << 1
    if getattr(figure, "chrome_styles", None):
        flags |= 1 << 2
    if getattr(figure, "title_options", None):
        flags |= 1 << 3
    if getattr(figure, "coords", "cartesian") == "polar":
        flags |= 1 << 4
    style_keys = [str(key) for key in (getattr(figure, "style", None) or {})]
    legend_keys = [str(key) for key in (getattr(figure, "legend_options", None) or {})]
    colorbar_keys = [str(key) for key in (getattr(figure, "colorbar_options", None) or {})]
    annotations = list(getattr(figure, "annotations", None) or [])
    traces = list(getattr(figure, "traces", None) or [])
    payload = bytearray(b"XYEF")
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
    for annotation in annotations:
        if not isinstance(annotation, dict):
            payload.extend(struct.pack("<B3sHH", 1, b"", 0, 0))
            continue
        kind_b = str(annotation.get("kind") or "").encode("utf-8")[:256]
        fields = [str(key) for key in annotation]
        if _annotation_has_markup(annotation) and "markup" not in fields:
            fields.append("markup")
        payload.extend(struct.pack("<B3sHH", 0, b"", len(kind_b), len(fields)))
        payload.extend(kind_b)
        _xyep_put_keys(payload, fields)
    for trace_index, trace in enumerate(traces):
        style = getattr(trace, "style", None) or {}
        opacity = float(style.get("opacity", 1.0))
        if not np.isfinite(opacity) or not 0.0 <= opacity <= 1.0:
            raise ValueError("trace opacity must be finite and in [0, 1]")
        prev = traces[trace_index - 1] if trace_index else None
        prev2 = traces[trace_index - 2] if trace_index >= 2 else None
        prev3 = traces[trace_index - 3] if trace_index >= 3 else None
        xv = _xyep_column(trace, "x")
        yv = _xyep_column(trace, "y")
        x0 = _xyep_column(trace, "x0")
        y0 = _xyep_column(trace, "y0")
        x1 = _xyep_column(trace, "x1")
        y1 = _xyep_column(trace, "y1")
        obs = 0
        if xv is not None:
            obs |= _XYEF_OBS_HAS_X
        if yv is not None:
            obs |= _XYEF_OBS_HAS_Y
        if _xyep_finite(xv):
            obs |= _XYEF_OBS_X_FINITE
        if _xyep_finite(yv):
            obs |= _XYEF_OBS_Y_FINITE
        if x0 is not None:
            obs |= _XYEF_OBS_HAS_X0
        if y0 is not None:
            obs |= _XYEF_OBS_HAS_Y0
        if x1 is not None:
            obs |= _XYEF_OBS_HAS_X1
        if y1 is not None:
            obs |= _XYEF_OBS_HAS_Y1
        if _xyep_finite(x0):
            obs |= _XYEF_OBS_X0_FINITE
        if _xyep_finite(y0):
            obs |= _XYEF_OBS_Y0_FINITE
        if _xyep_finite(x1):
            obs |= _XYEF_OBS_X1_FINITE
        if _xyep_finite(y1):
            obs |= _XYEF_OBS_Y1_FINITE
        if style.get("joined_fill"):
            obs |= _XYEF_OBS_JOINED_FILL
        heatmap_rows = heatmap_cols = heatmap_values = 0
        if trace.kind == "heatmap":
            style_truecolor = bool(style.get("truecolor"))
            if style_truecolor:
                obs |= _XYEF_OBS_HEATMAP_TRUECOLOR
            if getattr(trace, "rgba_grid", None) is not None:
                obs |= _XYEF_OBS_HEATMAP_RGBA_GRID
            try:
                heatmap_rows, heatmap_cols = _heatmap_shape(trace)
                values = _heatmap_grid_values(trace)
                _heatmap_extent(trace)
                obs |= _XYEF_OBS_HEATMAP_SHAPE_OK
                obs |= _XYEF_OBS_HEATMAP_EXTENT_OK
                heatmap_values = int(values.size)
                if _native.scene_finite_all(values):
                    obs |= _XYEF_OBS_HEATMAP_FINITE
            except (UnsupportedSceneV3, ValueError, TypeError):
                heatmap_rows = heatmap_cols = heatmap_values = 0
        if style.get("stroke_width") is not None and style.get("stroke") is None:
            obs |= _XYEF_OBS_STROKE_WIDTH_ONLY
        if (
            prev is not None
            and xv is not None
            and yv is not None
            and _xyep_column(prev, "x1") is not None
            and _xyep_column(prev, "y1") is not None
            and np.array_equal(xv.values, prev.x1.values)
            and np.array_equal(yv.values, prev.y1.values)
        ):
            obs |= _XYEF_OBS_COMPANION_XY_MATCH
        if prev is not None and trace.x_axis == prev.x_axis and trace.y_axis == prev.y_axis:
            obs |= _XYEF_OBS_COMPANION_AXES_MATCH
        symbol = style.get("symbol", "circle")
        if not isinstance(symbol, str):
            obs |= _XYEF_OBS_SYMBOL_NON_STRING
            symbol = ""
        if (
            trace.kind == "scatter"
            and getattr(figure, "coords", "cartesian") == "cartesian"
            and trace.use_density()
        ):
            obs |= _XYEF_OBS_DENSITY_BLIT
        role = style.get("role")
        role_s = "" if role is None else str(role)
        reduce = style.get("reduce")
        reduce_s = "" if reduce is None else str(reduce)
        try:
            hex_dx, hex_dy = (
                _hexbin_pitch(style)
                if _native.scene_kind_class(str(trace.kind)) & _SCENE_KIND_CLASS_HEXBIN
                else (float("nan"), float("nan"))
            )
        except UnsupportedSceneV3:
            hex_dx = hex_dy = float("nan")
        style_keys_tr = [str(key) for key, value in style.items() if value is not None]
        kind_b = str(trace.kind).encode("utf-8")[:256]
        step_b = str(style.get("step") or "").encode("utf-8")[:256]
        role_b = role_s.encode("utf-8")[:256]
        symbol_b = (symbol.encode("utf-8") if isinstance(symbol, str) else b"")[:256]
        reduce_b = reduce_s.encode("utf-8")[:256]
        prev_b = (str(prev.kind).encode("utf-8") if prev is not None else b"")[:256]
        prev2_b = (str(prev2.kind).encode("utf-8") if prev2 is not None else b"")[:256]
        prev3_b = (str(prev3.kind).encode("utf-8") if prev3 is not None else b"")[:256]
        payload.extend(
            struct.pack(
                "<I6I3I10H4x2d",
                obs,
                _xyep_len(xv),
                _xyep_len(yv),
                _xyep_len(x0),
                _xyep_len(y0),
                _xyep_len(x1),
                _xyep_len(y1),
                heatmap_rows,
                heatmap_cols,
                heatmap_values,
                len(style_keys_tr),
                len(kind_b),
                len(step_b),
                len(role_b),
                len(symbol_b),
                len(reduce_b),
                len(prev_b),
                len(prev2_b),
                len(prev3_b),
                0,
                hex_dx,
                hex_dy,
            )
        )
        payload.extend(kind_b)
        payload.extend(step_b)
        payload.extend(role_b)
        payload.extend(symbol_b)
        payload.extend(reduce_b)
        payload.extend(prev_b)
        payload.extend(prev2_b)
        payload.extend(prev3_b)
        _xyep_put_keys(payload, style_keys_tr)
    return _native.scene_pack_public_export(bytes(payload))


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
