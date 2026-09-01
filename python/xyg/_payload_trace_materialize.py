"""ABI 321 trace emit materialize: marshal Trace -> Rust -> PayloadWriter."""

from __future__ import annotations

import ctypes
from typing import TYPE_CHECKING, Any, cast

import numpy as np

from . import _native, channels
from ._payload_helpers import binning_coords, transition_entry, visible_sel
from ._trace import Trace
from .columns import Column
from .config import DENSITY_GRID, MAX_ANIMATION_MATCH_ROWS

if TYPE_CHECKING:
    from ._payload_writer import PayloadWriter

PAYLOAD_TRACE_EMIT_MAX_BYTES = 1 << 28
PAYLOAD_TRACE_EMIT_MAX_GEOM = 8
PAYLOAD_TRACE_EMIT_MAX_CHANNELS = 5
PAYLOAD_TRACE_EMIT_PATH_ENTRY = 0
PAYLOAD_TRACE_EMIT_PATH_DENSITY = 1
PAYLOAD_TRACE_EMIT_PATH_RECT_FALLBACK = 2
PAYLOAD_TRACE_EMIT_PATH_HEATMAP_RGBA = 3
PAYLOAD_TRACE_EMIT_PATH_HEATMAP_GRID = 4
_PAYLOAD_TRACE_COL_ATTRS = ("x", "y", "x0", "x1", "y0", "y1", "base")
_COL_REGISTRY = (
    "x",
    "y",
    "x0",
    "x1",
    "y0",
    "y1",
    "x2",
    "y2",
    "base",
    "target_y0",
    "target_y1",
    "pos",
    "value0",
    "value1",
)
_CHAN_REGISTRY = ("color", "size", "stroke", "channels", "color_target")


class _TraceColumnDesc(ctypes.Structure):
    _fields_ = [
        ("present", ctypes.c_int32),
        ("values_len", ctypes.c_size_t),
        ("col_min", ctypes.c_double),
        ("col_max", ctypes.c_double),
        ("null_count", ctypes.c_uint64),
        ("sticky_offset", ctypes.c_double),
        ("kind_len", ctypes.c_size_t),
    ]


class _TraceChannelDesc(ctypes.Structure):
    _fields_ = [
        ("present", ctypes.c_int32),
        ("mode", ctypes.c_int32),
        ("n_categories", ctypes.c_size_t),
        ("domain_lo", ctypes.c_double),
        ("domain_hi", ctypes.c_double),
        ("values_f64_len", ctypes.c_size_t),
        ("values_u8_len", ctypes.c_size_t),
        ("style_dtype_u8", ctypes.c_int32),
        ("null_count", ctypes.c_uint64),
    ]


class _TraceEmitIn(ctypes.Structure):
    _fields_ = [
        ("kind_len", ctypes.c_size_t),
        ("n_points", ctypes.c_uint64),
        ("segment_count", ctypes.c_uint64),
        ("polar", ctypes.c_int32),
        ("force_density", ctypes.c_int32),
        ("per_item", ctypes.c_int32),
        ("x_axis_type", ctypes.c_int32),
        ("y_axis_type", ctypes.c_int32),
        ("x_axis_scale_len", ctypes.c_size_t),
        ("y_axis_scale_len", ctypes.c_size_t),
        ("xr0", ctypes.c_double),
        ("xr1", ctypes.c_double),
        ("px_width", ctypes.c_uint32),
        ("style_color_is_none", ctypes.c_int32),
        ("has_trace_animation", ctypes.c_int32),
        ("has_transition_keys", ctypes.c_int32),
        ("has_tooltip_rows", ctypes.c_int32),
        ("n_tooltip_rows", ctypes.c_size_t),
        ("orientation_len", ctypes.c_size_t),
        ("has_color2_ch", ctypes.c_int32),
        ("has_color_ch", ctypes.c_int32),
        ("has_stroke_ch", ctypes.c_int32),
        ("has_style_channels", ctypes.c_int32),
        ("heatmap_rows", ctypes.c_uint32),
        ("heatmap_cols", ctypes.c_uint32),
        ("has_rgba_grid", ctypes.c_int32),
        ("borrow_heatmaps", ctypes.c_int32),
        ("style_colormap_is_none", ctypes.c_int32),
        ("grid_values_len", ctypes.c_size_t),
        ("grid_domain_lo", ctypes.c_double),
        ("grid_domain_hi", ctypes.c_double),
        ("max_rows", ctypes.c_size_t),
        ("bin_x_len", ctypes.c_size_t),
        ("bin_x0", ctypes.c_double),
        ("bin_x1", ctypes.c_double),
        ("transition_keys_len", ctypes.c_size_t),
    ]


class _TraceGeomOut(ctypes.Structure):
    _fields_ = [
        ("registry_key", ctypes.c_int32),
        ("nested", ctypes.c_int32),
        ("dtype_code", ctypes.c_int32),
        ("offset", ctypes.c_double),
        ("scale", ctypes.c_double),
        ("has_kind", ctypes.c_int32),
        ("len", ctypes.c_uint32),
        ("bytes_offset", ctypes.c_size_t),
        ("bytes_len", ctypes.c_size_t),
    ]


class _TraceChannelOut(ctypes.Structure):
    _fields_ = [
        ("registry_key", ctypes.c_int32),
        ("buf_kind", ctypes.c_int32),
        ("mark_dtype_u8", ctypes.c_int32),
        ("ship_palette", ctypes.c_int32),
        ("set_n", ctypes.c_int32),
        ("len", ctypes.c_uint32),
        ("bytes_offset", ctypes.c_size_t),
        ("bytes_len", ctypes.c_size_t),
    ]


class _TraceEmitOut(ctypes.Structure):
    _fields_ = [
        ("emit_path", ctypes.c_int32),
        ("tier", ctypes.c_int32),
        ("n_marks", ctypes.c_uint64),
        ("decimation_px", ctypes.c_uint32),
        ("apply_palette_default", ctypes.c_int32),
        ("attach_animation", ctypes.c_int32),
        ("attach_transition", ctypes.c_int32),
        ("attach_tooltip", ctypes.c_int32),
        ("filter_tooltip_by_sel", ctypes.c_int32),
        ("tooltip_length_ok", ctypes.c_int32),
        ("clear_shipped_sel", ctypes.c_int32),
        ("set_shipped_sel", ctypes.c_int32),
        ("drill_mode_false", ctypes.c_int32),
        ("attempt_role_keys", ctypes.c_int32),
        ("animation_fallback", ctypes.c_int32),
        ("n_geometry", ctypes.c_size_t),
        ("n_channels", ctypes.c_size_t),
        ("transition_lo_offset", ctypes.c_size_t),
        ("transition_lo_len", ctypes.c_size_t),
        ("transition_hi_offset", ctypes.c_size_t),
        ("transition_hi_len", ctypes.c_size_t),
        ("has_bar", ctypes.c_int32),
        ("bar_orientation", ctypes.c_int32),
        ("bar_value_axis", ctypes.c_int32),
        ("bar_width", ctypes.c_double),
        ("bar_has_value0_const", ctypes.c_int32),
        ("bar_value0_const", ctypes.c_double),
        ("bar_n_geom", ctypes.c_size_t),
        ("has_heatmap", ctypes.c_int32),
        ("heatmap_w", ctypes.c_uint32),
        ("heatmap_h", ctypes.c_uint32),
        ("heatmap_attach_color", ctypes.c_int32),
        ("heatmap_attach_encoding", ctypes.c_int32),
        ("heatmap_borrow_canonical", ctypes.c_int32),
        ("heatmap_grid_offset", ctypes.c_size_t),
        ("heatmap_grid_len", ctypes.c_size_t),
    ]


def _column_desc(col: Column | None):
    if col is None:
        return _TraceColumnDesc(), np.empty(0, dtype=np.float64), b""
    arr = np.ascontiguousarray(col.values, dtype=np.float64).reshape(-1)
    kind_b = str(col.kind).encode("utf-8")
    return (
        _TraceColumnDesc(
            1,
            len(arr),
            float(col.min),
            float(col.max),
            int(col.zone.null_count),
            float(col.suggest_offset()),
            len(kind_b),
        ),
        arr,
        kind_b,
    )


def _style_wire_channel(ch: Any):
    if not ch:
        return None
    if isinstance(ch, dict):
        if not ch:
            return None
        return next(iter(ch.values()))
    return ch


def _channel_desc(ch: Any):
    ch = _style_wire_channel(ch)
    if not ch:
        return _TraceChannelDesc(), np.empty(0, dtype=np.float64), np.empty(0, dtype=np.uint8)
    if getattr(ch, "mode", None) is None and getattr(ch, "values", None) is not None:
        mode = 5
        f64 = np.ascontiguousarray(ch.values, dtype=np.float64).reshape(-1)
        dom = (0.0, 1.0)
        u8 = np.empty(0, dtype=np.uint8)
        return (
            _TraceChannelDesc(
                1,
                mode,
                0,
                float(dom[0]),
                float(dom[1]),
                len(f64),
                len(u8),
                int(getattr(ch, "dtype", "") == "u8"),
                0,
            ),
            f64,
            u8,
        )
    mode = {
        "constant": 0,
        "continuous": 1,
        "categorical": 2,
        "direct_rgba": 3,
        "match_fill": 4,
        "direct": 5,
    }[ch.mode]
    dom = getattr(ch, "domain", None) or (0.0, 1.0)
    f64, u8 = np.empty(0, dtype=np.float64), np.empty(0, dtype=np.uint8)
    if ch.mode == "continuous" and ch.values is not None:
        f64 = np.ascontiguousarray(ch.values, dtype=np.float64).reshape(-1)
    elif ch.mode == "categorical" and ch.codes is not None:
        u8 = np.ascontiguousarray(ch.codes, dtype=np.uint8).reshape(-1)
    elif ch.mode == "direct_rgba":
        rgba = getattr(ch, "rgba", None)
        if rgba is not None:
            f64 = np.ascontiguousarray(rgba, dtype=np.float64).reshape(-1)
    elif ch.mode == "direct" and getattr(ch, "values", None) is not None:
        f64 = np.ascontiguousarray(ch.values, dtype=np.float64).reshape(-1)
    return (
        _TraceChannelDesc(
            1,
            mode,
            len(getattr(ch, "categories", []) or []),
            float(dom[0]),
            float(dom[1]),
            len(f64),
            len(u8),
            int(getattr(ch, "dtype", "") == "u8"),
            0,
        ),
        f64,
        u8,
    )


def emit_trace_materialized(
    figure: Any,
    t: Trace,
    pw: "PayloadWriter",
    xr: tuple[float, float],
    yr: tuple[float, float],
    px_width: int,
) -> dict[str, Any]:
    kind_b = t.kind.encode("utf-8")
    x_scale_b = figure._axis_scale(t.x_axis).encode("utf-8")
    y_scale_b = figure._axis_scale(t.y_axis).encode("utf-8")
    orient_b = str(t.style.get("orientation", "vertical")).encode("utf-8")
    col_descs, col_arrs, col_kinds = [], [], []
    for attr in _PAYLOAD_TRACE_COL_ATTRS:
        col = getattr(t, attr, None)
        desc, arr, kind = _column_desc(col if isinstance(col, Column) else None)
        col_descs.append(desc)
        col_arrs.append(arr)
        col_kinds.append(kind)
    ch_descs = {
        name: _channel_desc(ch)
        for name, ch in (
            ("color", t.color_ch),
            ("stroke", t.stroke_ch),
            ("color2", t.color2_ch),
            ("size", t.size_ch),
            ("style", t.style_channels),
        )
    }
    transition_lo = transition_hi = None
    if t.transition_keys is not None:
        tk = np.asarray(t.transition_keys, dtype=np.uint32)
        transition_lo = np.ascontiguousarray(tk[:, 0], dtype=np.uint32)
        transition_hi = np.ascontiguousarray(tk[:, 1], dtype=np.uint32)
    bin_x_arr = None
    bin_x0 = bin_x1 = 0.0
    if t.kind in ("line", "area", "error_band"):
        bx, (bin_x0, bin_x1) = binning_coords(figure, t.x_axis, t.x.values, xr)
        if bx is not t.x.values:
            bin_x_arr = np.ascontiguousarray(bx, dtype=np.float64)
    grid_arr = None
    domain = (0.0, 1.0)
    if t.kind == "heatmap" and t.grid is not None:
        grid_arr = np.ascontiguousarray(t.grid.values, dtype=np.float64).reshape(-1)
        domain = tuple(t.style.get("domain", (0.0, 1.0)))
    emit_in = _TraceEmitIn(
        len(kind_b),
        int(t.n_points),
        int(t.count or 0),
        int(figure.coords == "polar"),
        int(t.payload_force_density()),
        int(t.has_per_item_channels()),
        _native._payload_axis_type_code(figure._axis_scale(t.x_axis)),
        _native._payload_axis_type_code(figure._axis_scale(t.y_axis)),
        len(x_scale_b),
        len(y_scale_b),
        float(xr[0]),
        float(xr[1]),
        int(px_width),
        int(t.style.get("color") is None),
        int(t.animation is not None),
        int(t.transition_keys is not None),
        int(t.tooltip_rows is not None),
        len(t.tooltip_rows) if t.tooltip_rows is not None else 0,
        len(orient_b),
        int(t.color2_ch is not None),
        int(t.color_ch is not None),
        int(t.stroke_ch is not None),
        int(bool(t.style_channels)),
        int(t.grid_shape[0]) if t.grid_shape else 0,
        int(t.grid_shape[1]) if t.grid_shape else 0,
        int(t.rgba_grid is not None),
        int(pw.borrow_heatmaps),
        int(t.style.get("colormap") is None),
        len(grid_arr) if grid_arr is not None else 0,
        float(domain[0]),
        float(domain[1]),
        MAX_ANIMATION_MATCH_ROWS,
        len(bin_x_arr) if bin_x_arr is not None else 0,
        float(bin_x0),
        float(bin_x1),
        len(transition_lo) if transition_lo is not None else 0,
    )
    col_ptrs = (ctypes.c_void_p * 7)(*(a.ctypes.data if len(a) else None for a in col_arrs))
    kind_ptrs = (ctypes.c_void_p * 7)(
        *(np.frombuffer(k, dtype=np.uint8).ctypes.data if k else 0 for k in col_kinds)
    )
    summary = _TraceEmitOut()
    geom_out = (_TraceGeomOut * PAYLOAD_TRACE_EMIT_MAX_GEOM)()
    chan_out = (_TraceChannelOut * PAYLOAD_TRACE_EMIT_MAX_CHANNELS)()
    out_bytes = np.zeros(PAYLOAD_TRACE_EMIT_MAX_BYTES, dtype=np.uint8)
    out_len = ctypes.c_size_t(0)
    code = int(
        _native._lib.xyg_payload_trace_emit_materialize(
            ctypes.byref(emit_in),
            kind_b,
            x_scale_b,
            y_scale_b,
            orient_b,
            (_TraceColumnDesc * 7)(*col_descs),
            col_ptrs,
            kind_ptrs,
            ctypes.byref(ch_descs["color"][0]),
            ctypes.byref(ch_descs["stroke"][0]),
            ctypes.byref(ch_descs["color2"][0]),
            ctypes.byref(ch_descs["size"][0]),
            ctypes.byref(ch_descs["style"][0]),
            _native._ptr_f64(ch_descs["color"][1]),
            _native._ptr_f64(ch_descs["stroke"][1]),
            _native._ptr_f64(ch_descs["color2"][1]),
            _native._ptr_f64(ch_descs["size"][1]),
            _native._ptr_f64(ch_descs["style"][1]),
            _native._ptr_u8(ch_descs["color"][2]),
            _native._ptr_u8(ch_descs["stroke"][2]),
            _native._ptr_u8(ch_descs["color2"][2]),
            _native._ptr_u8(ch_descs["size"][2]),
            _native._ptr_u8(ch_descs["style"][2]),
            _native._ptr_u32(transition_lo) if transition_lo is not None else _native._null_u32(),
            _native._ptr_u32(transition_hi) if transition_hi is not None else _native._null_u32(),
            _native._ptr_f64(bin_x_arr) if bin_x_arr is not None else 0,
            _native._ptr_f64(grid_arr) if grid_arr is not None else 0,
            ctypes.byref(summary),
            geom_out,
            PAYLOAD_TRACE_EMIT_MAX_GEOM,
            chan_out,
            PAYLOAD_TRACE_EMIT_MAX_CHANNELS,
            _native._ptr_u8(out_bytes),
            len(out_bytes),
            ctypes.byref(out_len),
        )
    )
    if code != 0:
        raise ValueError(f"payload_trace_emit_materialize failed ({code}) for kind {t.kind!r}")
    blob = bytes(out_bytes[: int(out_len.value)])
    path = int(summary.emit_path)
    if path == PAYLOAD_TRACE_EMIT_PATH_DENSITY:
        if summary.clear_shipped_sel:
            t.shipped_sel = None
        if summary.drill_mode_false:
            t.drill_mode = False
        entry = figure._density_trace_spec(t, xr, yr, *DENSITY_GRID, pw)
        return transition_entry(entry, t, pw) if summary.attach_transition else entry
    if path == PAYLOAD_TRACE_EMIT_PATH_RECT_FALLBACK:
        saved = t.kind
        try:
            t.kind = "rect"
            return emit_trace_materialized(figure, t, pw, xr, yr, px_width)
        finally:
            t.kind = saved
    tier = "direct" if int(summary.tier) == 0 else "decimated"
    style = dict(t.style)
    if summary.apply_palette_default:
        style["color"] = figure.palette_color(t.id)
    entry: dict[str, Any] = {
        "id": t.id,
        "kind": t.kind,
        "name": t.name,
        "style": style,
        "tier": tier,
        "n_points": t.n_points,
        "n_marks": int(summary.n_marks),
        "x_axis": t.x_axis,
        "y_axis": t.y_axis,
    }
    if summary.decimation_px:
        entry["decimation_px"] = int(summary.decimation_px)
    if summary.attach_animation and t.animation is not None:
        entry["animation"] = dict(t.animation)
    target: dict[str, Any] = entry
    if summary.has_bar:
        bar_spec = {
            "orientation": "vertical" if summary.bar_orientation == 0 else "horizontal",
            "value_axis": "y" if summary.bar_value_axis == 0 else "x",
            "width": float(summary.bar_width),
        }
        if summary.bar_has_value0_const:
            bar_spec["value0_const"] = float(summary.bar_value0_const)
        entry["bar"] = bar_spec
        target = bar_spec
    for idx in range(int(summary.n_geometry)):
        geom = geom_out[idx]
        key = _COL_REGISTRY[int(geom.registry_key)]
        dtype = "<f8" if geom.dtype_code == 1 else "<f4"
        enc = np.frombuffer(
            blob[geom.bytes_offset : geom.bytes_offset + geom.bytes_len], dtype=dtype
        )
        meta: dict[str, Any] = {"len": int(geom.len)}
        if geom.dtype_code == 1:
            meta["dtype"] = "f64"
        else:
            meta["offset"] = float(geom.offset)
            meta["scale"] = float(geom.scale)
            if geom.has_kind:
                meta["kind"] = (col_kinds[idx] if idx < len(col_kinds) else b"").decode("utf-8")
        col_idx = pw._append_from_materialized(enc, meta)
        shipped = {"col": col_idx, **pw.columns[col_idx]} if int(geom.nested) else col_idx
        cast(dict[str, Any], target)[key] = shipped
    for idx in range(int(summary.n_channels)):
        wire = chan_out[idx]
        key = _CHAN_REGISTRY[int(wire.registry_key)]
        if wire.buf_kind == 0:
            if key == "color":
                entry["color"] = t.color_ch.spec() if t.color_ch else {"mode": "constant"}
            elif key == "size":
                entry["size"] = t.size_ch.spec() if t.size_ch else {"mode": "constant"}
            elif key == "color_target":
                entry["color_target"] = t.color2_ch.spec() if t.color2_ch else {"mode": "constant"}
            continue
        raw = blob[wire.bytes_offset : wire.bytes_offset + wire.bytes_len]
        buf = (
            pw.ship_u8(np.frombuffer(raw, dtype=np.uint8))
            if wire.buf_kind == 1
            else pw.ship_scalar(np.frombuffer(raw, dtype="<f4"))
        )
        spec: dict[str, Any] = {"buf": buf}
        if wire.mark_dtype_u8:
            spec["dtype"] = "u8"
        if wire.ship_palette:
            cc = t.color_ch
            cats = getattr(cc, "categories", None) or () if cc else ()
            spec["palette"] = channels.categorical_palette(cc.colors, len(cats)) if cc else True
        if wire.set_n:
            spec["n"] = int(wire.len)
        if key == "color":
            entry["color"] = {**(t.color_ch.spec() if t.color_ch else {"mode": "constant"}), **spec}
        elif key == "size":
            entry["size"] = {**(t.size_ch.spec() if t.size_ch else {"mode": "constant"}), **spec}
        elif key == "stroke":
            entry["stroke"] = spec
        elif key == "channels":
            entry["channels"] = spec
        elif key == "color_target":
            entry["color_target"] = {
                **(t.color2_ch.spec() if t.color2_ch else {"mode": "constant"}),
                **spec,
            }
    if summary.attach_transition and summary.transition_lo_len:
        lo = np.frombuffer(
            blob[
                summary.transition_lo_offset : summary.transition_lo_offset
                + summary.transition_lo_len
            ],
            dtype="<u4",
        )
        hi = np.frombuffer(
            blob[
                summary.transition_hi_offset : summary.transition_hi_offset
                + summary.transition_hi_len
            ],
            dtype="<u4",
        )
        if not summary.attach_animation:
            entry["keys"] = {"lo": pw.ship_u32(lo), "hi": pw.ship_u32(hi)}
        else:
            entry.setdefault("keys", {})
            entry["keys"]["lo"] = pw.ship_u32(lo)
            entry["keys"]["hi"] = pw.ship_u32(hi)
    elif summary.attach_transition and summary.animation_fallback:
        entry["animation_fallback"] = int(summary.animation_fallback)
    sel: np.ndarray | None = None
    if summary.set_shipped_sel or summary.filter_tooltip_by_sel:
        base_col = getattr(t, "base", None)
        base_arr = base_col.values if isinstance(base_col, Column) else None
        sel = visible_sel(
            figure,
            t,
            t.x.values,
            t.y.values,
            base=base_arr,
            prefiltered=int(summary.tier) != 0,
            base_column=base_col if isinstance(base_col, Column) else None,
        )
    if summary.attach_tooltip:
        tooltip_rows = t.tooltip_rows
        if tooltip_rows is not None:
            entry["tooltip_rows"] = [
                dict(tooltip_rows[i])
                for i in (
                    range(len(tooltip_rows))
                    if not summary.filter_tooltip_by_sel
                    else (int(i) for i in (sel if sel is not None else []))
                )
            ]
    elif t.tooltip_rows is not None and not summary.tooltip_length_ok:
        raise ValueError(
            f"{t.kind} tooltip rows must match geometry ({len(t.tooltip_rows)} != {t.n_points})"
        )
    if path == PAYLOAD_TRACE_EMIT_PATH_HEATMAP_RGBA:
        rgba_grid = t.rgba_grid
        grid_shape = t.grid_shape
        if rgba_grid is None or grid_shape is None:
            raise ValueError("heatmap rgba grid missing for rgba emit path")
        entry["heatmap"] = {
            "rgba_bufs": [pw.ship_scalar(column.values) for column in rgba_grid],
            "w": int(grid_shape[1]),
            "h": int(grid_shape[0]),
            "x_range": list(t.style["x_range"]),
            "y_range": list(t.style["y_range"]),
        }
        return entry
    if path == PAYLOAD_TRACE_EMIT_PATH_HEATMAP_GRID and summary.has_heatmap:
        grid_shape = t.grid_shape
        grid = t.grid
        if grid_shape is None or grid is None:
            raise ValueError("heatmap grid missing for grid emit path")
        rows, cols = grid_shape
        raw = blob[
            summary.heatmap_grid_offset : summary.heatmap_grid_offset + summary.heatmap_grid_len
        ]
        if summary.heatmap_borrow_canonical:
            buf_idx = pw.borrow_f64(grid.values)
            encoding = "canonical-f64"
        else:
            buf_idx = pw.ship_scalar(np.frombuffer(raw, dtype="<f4"))
            encoding = None
        cmap = t.style.get("colormap")
        if summary.heatmap_attach_color and cmap is None:
            from ._raster import _parse_color

            red, green, blue, _alpha = _parse_color(str(t.style.get("color", "#3987e5")), 1.0)
            cmap = [[red, green, blue], [red, green, blue]]
        entry["heatmap"] = {
            "buf": buf_idx,
            "w": int(cols),
            "h": int(rows),
            "x_range": list(t.style["x_range"]),
            "y_range": list(t.style["y_range"]),
            "colormap": cmap,
            "domain": list(domain),
            **({"enc": encoding} if summary.heatmap_attach_encoding and encoding else {}),
        }
        if summary.heatmap_attach_color:
            entry["color"] = {"mode": "continuous", "colormap": cmap, "domain": list(domain)}
        return entry
    if summary.set_shipped_sel:
        t.shipped_sel = sel
    return entry
