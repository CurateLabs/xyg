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
from ._scene_annotations import (
    colorbar_input as _colorbar_input,
)
from ._scene_annotations import (
    pack_xyaf_bulk as _pack_xyaf_bulk,
)
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
