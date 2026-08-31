"""ctypes bindings for scene bulk packers (ABI 321-324)."""

from __future__ import annotations

import ctypes
import struct
from collections.abc import Mapping, Sequence
from typing import Any

import numpy as np

_lib = None
_ptr_u8 = None
_ptr_f64 = None
_optional_u8_ptr = None
SCENE_XYCF_PACK_MAX = 1 << 20
SCENE_FIGURE_SUPPORT_PACK_MAX = 1 << 18
SCENE_POLAR_INPUT_PACK_MAX = 92
SCENE_XYAF_BULK_PACK_MAX = 1 << 22
SCENE_XYTA_TRACE_OBSERVATIONS_MAX_BYTES = 1 << 22
SCENE_XYTA_TRACE_PACK_MAX_RECORD = 1 << 22


def init(native: Any) -> None:
    """Wire host pointers after ``xyg._native`` finishes loading the cdylib."""
    global _lib, _ptr_u8, _ptr_f64, _optional_u8_ptr
    global SCENE_XYCF_PACK_MAX, SCENE_FIGURE_SUPPORT_PACK_MAX, SCENE_XYAF_BULK_PACK_MAX
    global SCENE_XYTA_TRACE_OBSERVATIONS_MAX_BYTES, SCENE_XYTA_TRACE_PACK_MAX_RECORD
    _lib = native._lib
    _ptr_u8 = native._ptr_u8
    _ptr_f64 = native._ptr_f64
    _optional_u8_ptr = native._optional_u8_ptr
    SCENE_XYCF_PACK_MAX = native.SCENE_XYCF_PACK_MAX
    SCENE_FIGURE_SUPPORT_PACK_MAX = native.SCENE_FIGURE_SUPPORT_PACK_MAX
    SCENE_XYAF_BULK_PACK_MAX = getattr(native, "SCENE_XYAF_BULK_PACK_MAX", 1 << 22)
    SCENE_XYTA_TRACE_OBSERVATIONS_MAX_BYTES = getattr(
        native, "SCENE_XYTA_TRACE_OBSERVATIONS_MAX_BYTES", 1 << 22
    )
    SCENE_XYTA_TRACE_PACK_MAX_RECORD = getattr(native, "SCENE_XYTA_TRACE_PACK_MAX_RECORD", 1 << 22)


class _XygStringRef(ctypes.Structure):
    _fields_ = [
        ("ptr", ctypes.c_void_p),
        ("len", ctypes.c_size_t),
    ]


class _XygChromeAxisStyleIn(ctypes.Structure):
    _fields_ = [
        ("grid_color", _XygStringRef),
        ("grid_width_present", ctypes.c_int32),
        ("grid_width", ctypes.c_double),
        ("grid_opacity_present", ctypes.c_int32),
        ("grid_opacity", ctypes.c_float),
        ("axis_color", _XygStringRef),
        ("axis_width_present", ctypes.c_int32),
        ("axis_width", ctypes.c_double),
        ("tick_color", _XygStringRef),
        ("tick_width_present", ctypes.c_int32),
        ("tick_width", ctypes.c_double),
        ("tick_length_present", ctypes.c_int32),
        ("tick_length", ctypes.c_double),
        ("tick_direction", _XygStringRef),
        ("tick_label_color", _XygStringRef),
        ("label_color", _XygStringRef),
    ]


class _XygChromeAxisIn(ctypes.Structure):
    _fields_ = [
        ("side_code", ctypes.c_uint8),
        ("tick_sides_mask", ctypes.c_uint8),
        ("label_sides_mask", ctypes.c_uint8),
        ("style", _XygChromeAxisStyleIn),
        ("minor_style", _XygChromeAxisStyleIn),
    ]


class _XygChromeCollisionAxisIn(ctypes.Structure):
    _fields_ = [
        ("strategy", _XygStringRef),
        ("collision", _XygStringRef),
        ("anchor", _XygStringRef),
        ("min_gap_present", ctypes.c_int32),
        ("min_gap", ctypes.c_double),
        ("angle_present", ctypes.c_int32),
        ("angle", ctypes.c_double),
        ("tick_kind_category", ctypes.c_int32),
    ]


class _XygChromeLegendIn(ctypes.Structure):
    _fields_ = [
        ("unsupported_keys", ctypes.c_int32),
        ("toggle", ctypes.c_int32),
        ("highlight", ctypes.c_int32),
        ("loc", _XygStringRef),
        ("title", _XygStringRef),
        ("ncols", ctypes.c_uint32),
        ("unsupported_style", ctypes.c_int32),
        ("font_size_present", ctypes.c_int32),
        ("font_size", ctypes.c_double),
        ("title_font_size_present", ctypes.c_int32),
        ("title_font_size", ctypes.c_double),
        ("color", _XygStringRef),
        ("background", _XygStringRef),
    ]


class _XygChromeColorbarIn(ctypes.Structure):
    _fields_ = [
        ("domain_lo", ctypes.c_double),
        ("domain_hi", ctypes.c_double),
        ("stop_count", ctypes.c_uint32),
        ("side_bottom", ctypes.c_int32),
        ("invalid_side", ctypes.c_int32),
        ("minor_ticks", ctypes.c_int32),
        ("title", _XygStringRef),
        ("text_rgba", ctypes.c_uint8 * 4),
        ("tick_count", ctypes.c_uint32),
    ]


class _XygSceneChromePackIn(ctypes.Structure):
    _fields_ = [
        ("width", ctypes.c_double),
        ("height", ctypes.c_double),
        ("show_legend", ctypes.c_int32),
        ("colorbar_ok", ctypes.c_int32),
        ("polar", ctypes.c_int32),
        ("has_margins", ctypes.c_int32),
        ("margin_left", ctypes.c_double),
        ("margin_right", ctypes.c_double),
        ("margin_top", ctypes.c_double),
        ("margin_bottom", ctypes.c_double),
        ("has_padding", ctypes.c_int32),
        ("pad_left", ctypes.c_double),
        ("pad_right", ctypes.c_double),
        ("pad_top", ctypes.c_double),
        ("pad_bottom", ctypes.c_double),
        ("title", _XygStringRef),
        ("x_label", _XygStringRef),
        ("y_label", _XygStringRef),
        ("x_format", _XygStringRef),
        ("y_format", _XygStringRef),
        ("x_scale_kind", ctypes.c_uint32),
        ("y_scale_kind", ctypes.c_uint32),
        ("x_lo", ctypes.c_double),
        ("x_hi", ctypes.c_double),
        ("x_constant", ctypes.c_double),
        ("y_lo", ctypes.c_double),
        ("y_hi", ctypes.c_double),
        ("y_constant", ctypes.c_double),
        ("x_nonpositive_mask", ctypes.c_uint8),
        ("y_nonpositive_mask", ctypes.c_uint8),
        ("x_tick_kind", ctypes.c_uint8),
        ("y_tick_kind", ctypes.c_uint8),
        ("x_axis", _XygChromeAxisIn),
        ("y_axis", _XygChromeAxisIn),
        ("x_major_len", ctypes.c_size_t),
        ("y_major_len", ctypes.c_size_t),
        ("x_minor_len", ctypes.c_size_t),
        ("y_minor_len", ctypes.c_size_t),
        ("x_tick_label_count", ctypes.c_uint32),
        ("y_tick_label_count", ctypes.c_uint32),
        ("x_collision", _XygChromeCollisionAxisIn),
        ("y_collision", _XygChromeCollisionAxisIn),
        ("chart_background", _XygStringRef),
        ("plot_background", _XygStringRef),
        ("legend", _XygChromeLegendIn),
        ("colorbar_present", ctypes.c_int32),
        ("colorbar", _XygChromeColorbarIn),
    ]


class _XygFigureSupportAnnotationObs(ctypes.Structure):
    _fields_ = [
        ("has_html", ctypes.c_int32),
        ("has_collision", ctypes.c_int32),
        ("has_markup", ctypes.c_int32),
        ("has_custom_typography", ctypes.c_int32),
        ("has_class_name", ctypes.c_int32),
        ("kind_is_supported_text", ctypes.c_int32),
        ("has_text", ctypes.c_int32),
    ]


class _XygFigureSupportAxisObsIn(ctypes.Structure):
    _fields_ = [
        ("axis_code", ctypes.c_uint8),
        ("key_count", ctypes.c_uint32),
        ("strategy", _XygStringRef),
        ("collision", _XygStringRef),
    ]


class _XygFigureSupportTraceObsIn(ctypes.Structure):
    _fields_ = [
        ("kind", _XygStringRef),
        ("x_axis", _XygStringRef),
        ("y_axis", _XygStringRef),
        ("hidden", ctypes.c_int32),
        ("has_per_item_channels", ctypes.c_int32),
        ("density_aggregates_color", ctypes.c_int32),
        ("marker_glyph_present", ctypes.c_int32),
        ("marker_glyph", _XygStringRef),
        ("marker_path_present", ctypes.c_int32),
        ("marker_path_valid", ctypes.c_int32),
        ("marker_path_filled_small", ctypes.c_int32),
        ("curve_present", ctypes.c_int32),
        ("curve", _XygStringRef),
        ("linecap_present", ctypes.c_int32),
        ("linecap", _XygStringRef),
        ("dash_present", ctypes.c_int32),
        ("dash_text", _XygStringRef),
        ("dash_is_array", ctypes.c_int32),
        ("fill_present", ctypes.c_int32),
        ("fill_is_string", ctypes.c_int32),
        ("fill_gradient_admitted", ctypes.c_int32),
        ("hexbin_reduce", _XygStringRef),
        ("heatmap_truecolor", ctypes.c_int32),
        ("heatmap_has_colormap", ctypes.c_int32),
        ("heatmap_has_rgba_grid", ctypes.c_int32),
        ("heatmap_has_rgba", ctypes.c_int32),
        ("rect_gradient_fail", ctypes.c_int32),
        ("corner_radius_len", ctypes.c_size_t),
        ("corner_radius_seq", ctypes.c_int32),
        ("wedge_gap", ctypes.c_double),
        ("ribbon_color2_fail", ctypes.c_int32),
        ("color_channel_unsupported", ctypes.c_int32),
    ]


class _XygScenePolarInputPackIn(ctypes.Structure):
    _fields_ = [
        ("polar", ctypes.c_int32),
        ("theta_unit", ctypes.c_uint32),
        ("theta_direction", ctypes.c_uint32),
        ("n_categories", ctypes.c_uint32),
        ("grid_shape", ctypes.c_uint8),
        ("r_scale_kind", ctypes.c_uint32),
        ("r_mask_nonpositive", ctypes.c_int32),
        ("sector_start", ctypes.c_double),
        ("sector_end", ctypes.c_double),
        ("r_lo", ctypes.c_double),
        ("r_hi", ctypes.c_double),
        ("r_origin_is_nan", ctypes.c_int32),
        ("r_origin", ctypes.c_double),
        ("hole", ctypes.c_double),
        ("r_constant", ctypes.c_double),
        ("theta_zero_is_label", ctypes.c_int32),
        ("theta_zero_label", _XygStringRef),
        ("theta_zero_numeric", ctypes.c_double),
    ]


def _string_ref(value: str | None) -> tuple[_XygStringRef, bytes]:
    if value is None:
        return _XygStringRef(0, 0), b""
    encoded = value.encode("utf-8")
    arr = np.frombuffer(encoded, dtype=np.uint8)
    return _XygStringRef(_ptr_u8(arr), len(encoded)), encoded


def _chrome_axis_style(style: Mapping[str, Any]) -> _XygChromeAxisStyleIn:
    def opt(key: str) -> _XygStringRef:
        raw = style.get(key)
        return _string_ref(None if raw is None else str(raw))[0]

    return _XygChromeAxisStyleIn(
        opt("grid_color"),
        1 if "grid_width" in style else 0,
        float(style.get("grid_width", 0.0)),
        1 if "grid_opacity" in style else 0,
        float(style.get("grid_opacity", 0.0)),
        opt("axis_color"),
        1 if "axis_width" in style else 0,
        float(style.get("axis_width", 0.0)),
        opt("tick_color"),
        1 if "tick_width" in style else 0,
        float(style.get("tick_width", 0.0)),
        1 if "tick_length" in style else 0,
        float(style.get("tick_length", 0.0)),
        opt("tick_direction"),
        opt("tick_label_color"),
        opt("label_color"),
    )


def _chrome_axis(axis: Mapping[str, Any]) -> _XygChromeAxisIn:
    style = dict(axis.get("style") or {})
    minor = dict(axis.get("minor_style") or {})
    return _XygChromeAxisIn(
        int(axis["side_code"]) & 0xFF,
        int(axis["tick_sides_mask"]) & 0xFF,
        int(axis["label_sides_mask"]) & 0xFF,
        _chrome_axis_style(style),
        _chrome_axis_style(minor),
    )


def _collision_axis(collision: Mapping[str, Any]) -> _XygChromeCollisionAxisIn:
    min_gap = collision.get("min_gap")
    angle = collision.get("angle")
    return _XygChromeCollisionAxisIn(
        _string_ref(collision.get("strategy"))[0],
        _string_ref(collision.get("collision"))[0],
        _string_ref(collision.get("anchor"))[0],
        1 if min_gap is not None else 0,
        float(min_gap if min_gap is not None else 0.0),
        1 if angle is not None else 0,
        float(angle if angle is not None else 0.0),
        1 if collision.get("tick_kind_category") else 0,
    )


def scene_chrome_pack(**kwargs: Any) -> bytes:
    """Bulk-pack XYCF v1 chrome facts via ``xyg_scene_chrome_pack`` (ABI 321)."""
    keepers: list[bytes] = []
    title_ref, title_b = _string_ref(str(kwargs["title"]))
    keepers.append(title_b)
    x_label_ref, x_label_b = _string_ref(str(kwargs["x_label"]))
    keepers.append(x_label_b)
    y_label_ref, y_label_b = _string_ref(str(kwargs["y_label"]))
    keepers.append(y_label_b)
    x_format_ref, x_format_b = _string_ref(kwargs.get("x_format"))
    keepers.append(x_format_b)
    y_format_ref, y_format_b = _string_ref(kwargs.get("y_format"))
    keepers.append(y_format_b)
    chart_bg_ref, chart_bg_b = _string_ref(kwargs.get("chart_background"))
    keepers.append(chart_bg_b)
    plot_bg_ref, plot_bg_b = _string_ref(kwargs.get("plot_background"))
    keepers.append(plot_bg_b)
    legend_kw = kwargs["legend"]
    leg_loc_ref, leg_loc_b = _string_ref(legend_kw.get("loc"))
    keepers.append(leg_loc_b)
    leg_title_ref, leg_title_b = _string_ref(legend_kw.get("title"))
    keepers.append(leg_title_b)
    leg_color_ref, leg_color_b = _string_ref(legend_kw.get("color"))
    keepers.append(leg_color_b)
    leg_bg_ref, leg_bg_b = _string_ref(legend_kw.get("background"))
    keepers.append(leg_bg_b)
    legend = _XygChromeLegendIn(
        1 if legend_kw.get("unsupported_keys") else 0,
        1 if legend_kw.get("toggle") else 0,
        1 if legend_kw.get("highlight") else 0,
        leg_loc_ref,
        leg_title_ref,
        int(legend_kw.get("ncols", 1)),
        1 if legend_kw.get("unsupported_style") else 0,
        1 if legend_kw.get("font_size") is not None else 0,
        float(legend_kw.get("font_size") or 0.0),
        1 if legend_kw.get("title_font_size") is not None else 0,
        float(legend_kw.get("title_font_size") or 0.0),
        leg_color_ref,
        leg_bg_ref,
    )
    colorbar_present = 0
    colorbar = _XygChromeColorbarIn()
    colorbar_stops_blob = b""
    colorbar_ticks_arr = np.empty(0, dtype=np.float64)
    colorbar_cb_title_ref = _XygStringRef(0, 0)
    cb_payload = kwargs.get("colorbar")
    if cb_payload:
        colorbar_present = 1
        cb_title_ref, cb_title_b = _string_ref(cb_payload.get("title"))
        keepers.append(cb_title_b)
        colorbar_cb_title_ref = cb_title_ref
        stops = cb_payload.get("stops") or []
        colorbar_stops_blob = b"".join(
            struct.pack("<d", float(value)) + bytes(rgba[:4].ljust(4, b"\0"))
            for value, rgba in stops
        )
        ticks = cb_payload.get("ticks")
        if ticks is not None:
            colorbar_ticks_arr = np.ascontiguousarray(ticks, dtype=np.float64)
        colorbar = _XygChromeColorbarIn(
            float(cb_payload["domain_lo"]),
            float(cb_payload["domain_hi"]),
            len(stops),
            1 if cb_payload.get("side_bottom") else 0,
            1 if cb_payload.get("invalid_side") else 0,
            1 if cb_payload.get("minor_ticks") else 0,
            colorbar_cb_title_ref,
            (ctypes.c_uint8 * 4).from_buffer_copy(
                bytes(cb_payload.get("text_rgba", (32, 32, 32, 255)))[:4]
            ),
            len(colorbar_ticks_arr),
        )
    margins = kwargs["margins"]
    padding = kwargs["padding"]
    pack_in = _XygSceneChromePackIn(
        float(kwargs["width"]),
        float(kwargs["height"]),
        1 if kwargs.get("show_legend", True) else 0,
        1 if kwargs.get("colorbar_ok", True) else 0,
        1 if kwargs.get("polar") else 0,
        1 if kwargs.get("has_margins") else 0,
        float(margins[0]),
        float(margins[1]),
        float(margins[2]),
        float(margins[3]),
        1 if kwargs.get("has_padding") else 0,
        float(padding[0]),
        float(padding[1]),
        float(padding[2]),
        float(padding[3]),
        title_ref,
        x_label_ref,
        y_label_ref,
        x_format_ref,
        y_format_ref,
        int(kwargs["x_scale_kind"]),
        int(kwargs["y_scale_kind"]),
        float(kwargs["x_lo"]),
        float(kwargs["x_hi"]),
        float(kwargs["x_constant"]),
        float(kwargs["y_lo"]),
        float(kwargs["y_hi"]),
        float(kwargs["y_constant"]),
        int(kwargs["x_nonpositive_mask"]),
        int(kwargs["y_nonpositive_mask"]),
        int(kwargs["x_tick_kind"]),
        int(kwargs["y_tick_kind"]),
        _chrome_axis(kwargs["x_axis"]),
        _chrome_axis(kwargs["y_axis"]),
        len(kwargs.get("x_major") or ()),
        len(kwargs.get("y_major") or ()),
        len(kwargs.get("x_minor") or ()),
        len(kwargs.get("y_minor") or ()),
        len(kwargs.get("x_tick_labels") or ()),
        len(kwargs.get("y_tick_labels") or ()),
        _collision_axis(kwargs["x_collision"]),
        _collision_axis(kwargs["y_collision"]),
        chart_bg_ref,
        plot_bg_ref,
        legend,
        colorbar_present,
        colorbar,
    )
    x_major = (
        np.ascontiguousarray(kwargs["x_major"], dtype=np.float64)
        if kwargs.get("x_major") is not None
        else np.empty(0, dtype=np.float64)
    )
    y_major = (
        np.ascontiguousarray(kwargs["y_major"], dtype=np.float64)
        if kwargs.get("y_major") is not None
        else np.empty(0, dtype=np.float64)
    )
    x_minor = np.ascontiguousarray(kwargs.get("x_minor") or (), dtype=np.float64)
    y_minor = np.ascontiguousarray(kwargs.get("y_minor") or (), dtype=np.float64)
    x_tick_labels = kwargs.get("x_tick_labels")
    y_tick_labels = kwargs.get("y_tick_labels")
    x_label_refs = (_XygStringRef * len(x_tick_labels or ()))()
    y_label_refs = (_XygStringRef * len(y_tick_labels or ()))()
    for index, label in enumerate(x_tick_labels or ()):
        ref, encoded = _string_ref(str(label))
        keepers.append(encoded)
        x_label_refs[index] = ref
    for index, label in enumerate(y_tick_labels or ()):
        ref, encoded = _string_ref(str(label))
        keepers.append(encoded)
        y_label_refs[index] = ref
    stops_ptr, stops_len = _optional_u8_ptr(colorbar_stops_blob)
    out = np.zeros(SCENE_XYCF_PACK_MAX, dtype=np.uint8)
    out_len = ctypes.c_size_t(0)
    code = int(
        _lib.xyg_scene_chrome_pack(
            ctypes.byref(pack_in),
            _ptr_f64(x_major) if len(x_major) else 0,
            _ptr_f64(y_major) if len(y_major) else 0,
            _ptr_f64(x_minor) if len(x_minor) else 0,
            _ptr_f64(y_minor) if len(y_minor) else 0,
            ctypes.cast(x_label_refs, ctypes.c_void_p) if len(x_label_refs) else 0,
            ctypes.cast(y_label_refs, ctypes.c_void_p) if len(y_label_refs) else 0,
            stops_ptr if stops_len else 0,
            _ptr_f64(colorbar_ticks_arr) if len(colorbar_ticks_arr) else 0,
            _ptr_u8(out),
            len(out),
            ctypes.byref(out_len),
        )
    )
    del keepers
    if code == -2:
        raise ValueError("scene_chrome_pack output buffer too small")
    if code != 0:
        raise ValueError("invalid scene_chrome_pack arguments")
    return bytes(out[: int(out_len.value)])


def scene_figure_support_materialize(
    *,
    polar: bool,
    colorbar_unsupported: bool,
    has_custom_font: bool,
    has_browser_css: bool,
    has_extra_legends: bool,
    annotations: Sequence[Mapping[str, Any]],
    axes: Sequence[Mapping[str, Any]],
    traces: Sequence[Mapping[str, Any]],
) -> bytes:
    """Materialize XYFS v2 figure support via ``xyg_scene_figure_support_materialize`` (ABI 322)."""
    keepers: list[bytes] = []
    ann_rows = (_XygFigureSupportAnnotationObs * len(annotations))()
    for index, row in enumerate(annotations):
        ann_rows[index] = _XygFigureSupportAnnotationObs(
            1 if row.get("has_html") else 0,
            1 if row.get("has_collision") else 0,
            1 if row.get("has_markup") else 0,
            1 if row.get("has_custom_typography") else 0,
            1 if row.get("has_class_name") else 0,
            1 if row.get("kind_is_supported_text") else 0,
            1 if row.get("has_text") else 0,
        )
    axis_keys_blob = bytearray()
    axis_rows = (_XygFigureSupportAxisObsIn * len(axes))()
    for index, row in enumerate(axes):
        strategy_ref, strategy_b = _string_ref(row.get("tick_label_strategy"))
        collision_ref, collision_b = _string_ref(row.get("collision"))
        keepers.extend([strategy_b, collision_b])
        keys = list(row.get("keys") or ())
        for key in keys:
            encoded = str(key).encode("utf-8")
            axis_keys_blob.extend(len(encoded).to_bytes(2, "little"))
            axis_keys_blob.extend(encoded)
        axis_rows[index] = _XygFigureSupportAxisObsIn(
            int(row["axis_code"]) & 0xFF,
            len(keys),
            strategy_ref,
            collision_ref,
        )
    trace_rows = (_XygFigureSupportTraceObsIn * len(traces))()
    corner_radius_values: list[float] = []
    for index, row in enumerate(traces):
        kind_ref, kind_b = _string_ref(str(row.get("kind", "mark")))
        x_axis_ref, x_axis_b = _string_ref(str(row.get("x_axis", "x")))
        y_axis_ref, y_axis_b = _string_ref(str(row.get("y_axis", "y")))
        glyph_ref, glyph_b = _string_ref(row.get("marker_glyph"))
        curve_ref, curve_b = _string_ref(row.get("curve"))
        linecap_ref, linecap_b = _string_ref(row.get("linecap"))
        dash_ref, dash_b = _string_ref(row.get("dash_text"))
        reduce_ref, reduce_b = _string_ref(row.get("hexbin_reduce"))
        keepers.extend([kind_b, x_axis_b, y_axis_b, glyph_b, curve_b, linecap_b, dash_b, reduce_b])
        radius = [float(v) for v in row.get("corner_radius_values") or (0.0,)]
        corner_radius_values.extend(radius)
        trace_rows[index] = _XygFigureSupportTraceObsIn(
            kind_ref,
            x_axis_ref,
            y_axis_ref,
            1 if row.get("hidden") else 0,
            1 if row.get("has_per_item_channels") else 0,
            1 if row.get("density_aggregates_color") else 0,
            1 if row.get("marker_glyph_present") else 0,
            glyph_ref,
            1 if row.get("marker_path_present") else 0,
            1 if row.get("marker_path_valid") else 0,
            1 if row.get("marker_path_filled_small") else 0,
            1 if row.get("curve_present") else 0,
            curve_ref,
            1 if row.get("linecap_present") else 0,
            linecap_ref,
            1 if row.get("dash_present") else 0,
            dash_ref,
            1 if row.get("dash_is_array") else 0,
            1 if row.get("fill_present") else 0,
            1 if row.get("fill_is_string") else 0,
            1 if row.get("fill_gradient_admitted") else 0,
            reduce_ref,
            1 if row.get("heatmap_truecolor") else 0,
            1 if row.get("heatmap_has_colormap") else 0,
            1 if row.get("heatmap_has_rgba_grid") else 0,
            1 if row.get("heatmap_has_rgba") else 0,
            1 if row.get("rect_gradient_fail") else 0,
            len(radius),
            1 if row.get("corner_radius_seq") else 0,
            float(row.get("wedge_gap", 0.0)),
            1 if row.get("ribbon_color2_fail") else 0,
            1 if row.get("color_channel_unsupported") else 0,
        )
    keys_blob = bytes(axis_keys_blob)
    keys_ptr, keys_len = _optional_u8_ptr(keys_blob)
    radius_arr = np.ascontiguousarray(corner_radius_values, dtype=np.float64)
    out = np.zeros(SCENE_FIGURE_SUPPORT_PACK_MAX, dtype=np.uint8)
    out_len = ctypes.c_size_t(0)
    code = int(
        _lib.xyg_scene_figure_support_materialize(
            1 if polar else 0,
            1 if colorbar_unsupported else 0,
            1 if has_custom_font else 0,
            1 if has_browser_css else 0,
            1 if has_extra_legends else 0,
            ctypes.cast(ann_rows, ctypes.c_void_p) if len(ann_rows) else 0,
            len(annotations),
            ctypes.cast(axis_rows, ctypes.c_void_p) if len(axis_rows) else 0,
            len(axes),
            keys_ptr,
            keys_len,
            ctypes.cast(trace_rows, ctypes.c_void_p) if len(trace_rows) else 0,
            len(traces),
            _ptr_f64(radius_arr) if len(radius_arr) else 0,
            _ptr_u8(out),
            len(out),
            ctypes.byref(out_len),
        )
    )
    del keepers
    if code == -2:
        raise ValueError("scene_figure_support_materialize output buffer too small")
    if code != 0:
        raise ValueError("invalid scene_figure_support_materialize arguments")
    return bytes(out[: int(out_len.value)])


def scene_polar_input_pack(**kwargs: Any) -> bytes:
    """Pack XYPL v1 polar authoring via ``xyg_scene_polar_input_pack`` (ABI 322)."""
    label_ref, label_b = _string_ref(kwargs.get("theta_zero_label"))
    pack_in = _XygScenePolarInputPackIn(
        1 if kwargs.get("polar") else 0,
        int(kwargs["theta_unit"]),
        int(kwargs["theta_direction"]),
        int(kwargs["n_categories"]),
        int(kwargs["grid_shape"]) & 0xFF,
        int(kwargs["r_scale_kind"]),
        1 if kwargs.get("r_mask_nonpositive") else 0,
        float(kwargs["sector_start"]),
        float(kwargs["sector_end"]),
        float(kwargs["r_lo"]),
        float(kwargs["r_hi"]),
        1 if kwargs.get("r_origin_is_nan") else 0,
        float(kwargs["r_origin"]),
        float(kwargs["hole"]),
        float(kwargs["r_constant"]),
        1 if kwargs.get("theta_zero_is_label") else 0,
        label_ref,
        float(kwargs["theta_zero_numeric"]),
    )
    out = np.zeros(SCENE_POLAR_INPUT_PACK_MAX, dtype=np.uint8)
    out_len = ctypes.c_size_t(0)
    code = int(
        _lib.xyg_scene_polar_input_pack(
            ctypes.byref(pack_in),
            _ptr_u8(out),
            len(out),
            ctypes.byref(out_len),
        )
    )
    del label_b
    if code == -2:
        raise ValueError("scene_polar_input_pack output buffer too small")
    if code != 0:
        raise ValueError("invalid scene_polar_input_pack arguments")
    return bytes(out[: int(out_len.value)])


class _XygSceneXytaColorChannelDesc(ctypes.Structure):
    _fields_ = [
        ("present", ctypes.c_int32),
        ("mode_len", ctypes.c_size_t),
        ("constant_len", ctypes.c_size_t),
        ("colormap_len", ctypes.c_size_t),
        ("has_domain", ctypes.c_int32),
        ("domain_lo", ctypes.c_double),
        ("domain_hi", ctypes.c_double),
        ("values_f64_len", ctypes.c_size_t),
        ("rgba_u8_len", ctypes.c_size_t),
        ("codes_u8_len", ctypes.c_size_t),
        ("codes_i64_len", ctypes.c_size_t),
        ("palette_count", ctypes.c_size_t),
        ("n_categories", ctypes.c_size_t),
    ]


class _XygSceneXytaStyleChannelDesc(ctypes.Structure):
    _fields_ = [
        ("present", ctypes.c_int32),
        ("values_f64_len", ctypes.c_size_t),
    ]


class _XygSceneXytaTraceObservationsIn(ctypes.Structure):
    _fields_ = [
        ("trace_id", ctypes.c_uint32),
        ("pack_heatmap", ctypes.c_int32),
        ("pack_hexbin_colormap", ctypes.c_int32),
        ("pack_hexbin_rgba", ctypes.c_int32),
        ("pack_ribbon_ends", ctypes.c_int32),
        ("pack_mesh_faces", ctypes.c_int32),
        ("pack_scatter_paint", ctypes.c_int32),
        ("pack_density", ctypes.c_int32),
        ("domain_x0", ctypes.c_double),
        ("domain_x1", ctypes.c_double),
        ("domain_y0", ctypes.c_double),
        ("domain_y1", ctypes.c_double),
        ("point_count", ctypes.c_size_t),
        ("fallback_color_len", ctypes.c_size_t),
        ("style_color_len", ctypes.c_size_t),
        ("style_stroke_len", ctypes.c_size_t),
        ("style_stroke_width", ctypes.c_double),
        ("has_style_stroke_width", ctypes.c_int32),
        ("style_opacity", ctypes.c_float),
        ("has_style_opacity", ctypes.c_int32),
        ("style_fill_opacity", ctypes.c_float),
        ("has_style_fill_opacity", ctypes.c_int32),
        ("style_truecolor", ctypes.c_int32),
        ("style_domain_lo", ctypes.c_double),
        ("style_domain_hi", ctypes.c_double),
        ("has_style_domain", ctypes.c_int32),
        ("style_colormap_mode", ctypes.c_int32),
        ("style_colormap_named_len", ctypes.c_size_t),
        ("style_colormap_stops_len", ctypes.c_size_t),
        ("grid_shape_rows", ctypes.c_double),
        ("grid_shape_cols", ctypes.c_double),
        ("has_grid_shape", ctypes.c_int32),
        ("grid_values_len", ctypes.c_size_t),
        ("rgba_u8_len", ctypes.c_size_t),
        ("rgba_grid_f64_len", ctypes.c_size_t),
        ("x_values_len", ctypes.c_size_t),
        ("y_values_len", ctypes.c_size_t),
    ]


class _XygSceneXytaTraceObservationsOut(ctypes.Structure):
    _fields_ = [
        ("trace_id", ctypes.c_uint32),
        ("pack_heatmap", ctypes.c_int32),
        ("pack_hexbin_colormap", ctypes.c_int32),
        ("pack_hexbin_rgba", ctypes.c_int32),
        ("pack_ribbon_ends", ctypes.c_int32),
        ("pack_mesh_faces", ctypes.c_int32),
        ("pack_scatter_paint", ctypes.c_int32),
        ("pack_density", ctypes.c_int32),
        ("grid_shape_rows", ctypes.c_double),
        ("grid_shape_cols", ctypes.c_double),
        ("has_grid_shape", ctypes.c_int32),
        ("has_grid", ctypes.c_int32),
        ("has_rgba", ctypes.c_int32),
        ("has_rgba_grid", ctypes.c_int32),
        ("truecolor", ctypes.c_int32),
        ("has_cmap_domain", ctypes.c_int32),
        ("cmap_lo", ctypes.c_double),
        ("cmap_hi", ctypes.c_double),
        ("has_color_ch", ctypes.c_int32),
        ("has_style_color", ctypes.c_int32),
        ("has_opacity", ctypes.c_int32),
        ("has_fill_opacity", ctypes.c_int32),
        ("opacity", ctypes.c_float),
        ("fill_opacity", ctypes.c_float),
        ("domain_x0", ctypes.c_double),
        ("domain_x1", ctypes.c_double),
        ("domain_y0", ctypes.c_double),
        ("domain_y1", ctypes.c_double),
        ("cmap_flags", ctypes.c_uint32),
        ("rows", ctypes.c_int32),
        ("cols", ctypes.c_int32),
        ("grid_len", ctypes.c_size_t),
        ("rgba_len", ctypes.c_size_t),
        ("rgba_grid_len", ctypes.c_size_t),
        ("x_len", ctypes.c_size_t),
        ("y_len", ctypes.c_size_t),
        ("mean_rgba_len", ctypes.c_size_t),
        ("idx_len", ctypes.c_size_t),
        ("lut_len", ctypes.c_size_t),
        ("cmap_len", ctypes.c_size_t),
        ("stops_len", ctypes.c_size_t),
        ("color_ch_len", ctypes.c_size_t),
        ("style_color_len", ctypes.c_size_t),
        ("grid_off", ctypes.c_size_t),
        ("rgba_off", ctypes.c_size_t),
        ("rgba_grid_off", ctypes.c_size_t),
        ("x_off", ctypes.c_size_t),
        ("y_off", ctypes.c_size_t),
        ("mean_rgba_off", ctypes.c_size_t),
        ("idx_off", ctypes.c_size_t),
        ("lut_off", ctypes.c_size_t),
        ("cmap_off", ctypes.c_size_t),
        ("stops_off", ctypes.c_size_t),
        ("color_ch_off", ctypes.c_size_t),
        ("style_color_off", ctypes.c_size_t),
    ]


def _xyta_palette_ptrs(
    palette: Sequence[str],
) -> tuple[ctypes.Array | None, ctypes.Array | None, list[bytes]]:
    if not palette:
        return None, None, []
    keepers: list[bytes] = []
    ptrs = (ctypes.c_void_p * len(palette))()
    lens = (ctypes.c_size_t * len(palette))()
    for index, entry in enumerate(palette):
        encoded = str(entry).encode("utf-8")
        keepers.append(encoded)
        arr = np.frombuffer(encoded, dtype=np.uint8)
        ptrs[index] = _ptr_u8(arr)
        lens[index] = len(encoded)
    return ptrs, lens, keepers


def _xyta_color_channel_side(
    channel: Mapping[str, Any],
) -> tuple[
    _XygSceneXytaColorChannelDesc,
    bytes,
    bytes,
    bytes,
    np.ndarray,
    bytes,
    bytes,
    np.ndarray,
    ctypes.Array | None,
    ctypes.Array | None,
    list[bytes],
]:
    mode_b = str(channel.get("mode") or "").encode("utf-8")
    constant = channel.get("constant")
    constant_b = b"" if constant is None else str(constant).encode("utf-8")
    colormap = channel.get("colormap")
    colormap_b = b"" if colormap is None else str(colormap).encode("utf-8")
    values_f64 = np.ascontiguousarray(
        channel.get("values_f64", np.empty(0, dtype=np.float64)), dtype=np.float64
    ).reshape(-1)
    rgba_u8 = channel.get("rgba_u8") or b""
    codes_u8 = channel.get("codes_u8") or b""
    codes_i64 = np.ascontiguousarray(
        channel.get("codes_i64", np.empty(0, dtype=np.int64)), dtype=np.int64
    ).reshape(-1)
    palette = [str(entry) for entry in (channel.get("palette") or ())]
    ptrs, lens, keepers = _xyta_palette_ptrs(palette)
    desc = _XygSceneXytaColorChannelDesc(
        1 if channel.get("present") else 0,
        len(mode_b),
        len(constant_b),
        len(colormap_b),
        1 if channel.get("has_domain") else 0,
        float(channel.get("domain_lo", 0.0)),
        float(channel.get("domain_hi", 0.0)),
        len(values_f64),
        len(rgba_u8),
        len(codes_u8),
        len(codes_i64),
        len(palette),
        int(channel.get("n_categories") or 0),
    )
    return desc, mode_b, constant_b, colormap_b, values_f64, rgba_u8, codes_u8, codes_i64, ptrs, lens, keepers


def _xyta_style_channel_side(
    channel: Mapping[str, Any],
) -> tuple[_XygSceneXytaStyleChannelDesc, np.ndarray]:
    values_f64 = np.ascontiguousarray(
        channel.get("values_f64", np.empty(0, dtype=np.float64)), dtype=np.float64
    ).reshape(-1)
    return (
        _XygSceneXytaStyleChannelDesc(
            1 if channel.get("present") else 0,
            len(values_f64),
        ),
        values_f64,
    )


def scene_xyta_trace_observations_materialize(obs: Mapping[str, Any]) -> dict[str, Any]:
    """Materialize XYTA trace observations via ``xyg_scene_xyta_trace_observations_materialize`` (ABI 323)."""
    dispatch = obs["dispatch"]
    fallback_b = str(obs["fallback_color"]).encode("utf-8")
    style_color = obs.get("style_color")
    style_color_b = b"" if style_color is None else str(style_color).encode("utf-8")
    style_stroke = obs.get("style_stroke")
    style_stroke_b = b"" if style_stroke is None else str(style_stroke).encode("utf-8")
    style_colormap_mode = int(obs.get("style_colormap_mode") or 0)
    style_colormap_named_b = str(obs.get("style_colormap_named") or "").encode("utf-8")
    style_colormap_stops = obs.get("style_colormap_stops") or b""
    grid_values = np.ascontiguousarray(
        obs.get("grid_values", np.empty(0, dtype=np.float64)), dtype=np.float64
    ).reshape(-1)
    rgba_u8 = obs.get("rgba_u8") or b""
    rgba_grid_f64 = np.ascontiguousarray(
        obs.get("rgba_grid_f64", np.empty(0, dtype=np.float64)), dtype=np.float64
    ).reshape(-1)
    x_values = np.ascontiguousarray(
        obs.get("x_values", np.empty(0, dtype=np.float64)), dtype=np.float64
    ).reshape(-1)
    y_values = np.ascontiguousarray(
        obs.get("y_values", np.empty(0, dtype=np.float64)), dtype=np.float64
    ).reshape(-1)
    style_domain = obs.get("style_domain")
    has_style_domain = style_domain is not None and len(style_domain) == 2
    pack_in = _XygSceneXytaTraceObservationsIn(
        int(obs["trace_id"]) & 0xFFFFFFFF,
        int(dispatch["pack_heatmap"]),
        int(dispatch["pack_hexbin_colormap"]),
        int(dispatch["pack_hexbin_rgba"]),
        int(dispatch["pack_ribbon_ends"]),
        int(dispatch["pack_mesh_faces"]),
        int(dispatch["pack_scatter_paint"]),
        int(dispatch["pack_density"]),
        float(obs["domain_x0"]),
        float(obs["domain_x1"]),
        float(obs["domain_y0"]),
        float(obs["domain_y1"]),
        int(obs.get("point_count") or 0),
        len(fallback_b),
        len(style_color_b),
        len(style_stroke_b),
        float(obs.get("style_stroke_width") or 0.0),
        1 if obs.get("has_style_stroke_width") else 0,
        ctypes.c_float(float(obs.get("style_opacity") or float("nan"))),
        1 if obs.get("has_style_opacity") else 0,
        ctypes.c_float(float(obs.get("style_fill_opacity") or float("nan"))),
        1 if obs.get("has_style_fill_opacity") else 0,
        1 if obs.get("style_truecolor") else 0,
        float(style_domain[0]) if has_style_domain else 0.0,
        float(style_domain[1]) if has_style_domain else 0.0,
        1 if has_style_domain else 0,
        style_colormap_mode,
        len(style_colormap_named_b) if style_colormap_mode == 1 else 0,
        len(style_colormap_stops) if style_colormap_mode == 2 else 0,
        float(obs.get("grid_shape_rows") or 0.0),
        float(obs.get("grid_shape_cols") or 0.0),
        1 if obs.get("has_grid_shape") else 0,
        len(grid_values),
        len(rgba_u8),
        len(rgba_grid_f64),
        len(x_values),
        len(y_values),
    )
    color_side = _xyta_color_channel_side(obs["color_ch"])
    stroke_side = _xyta_color_channel_side(obs["stroke_ch"])
    color2_side = _xyta_color_channel_side(obs["color2_ch"])
    opacity_desc, opacity_values = _xyta_style_channel_side(obs["opacity_ch"])
    artist_desc, artist_values = _xyta_style_channel_side(obs["artist_alpha_ch"])
    stroke_width_desc, stroke_width_values = _xyta_style_channel_side(obs["stroke_width_ch"])
    keepers = [
        fallback_b,
        style_color_b,
        style_stroke_b,
        style_colormap_named_b,
        style_colormap_stops,
        rgba_u8,
        color_side[1],
        color_side[2],
        color_side[3],
        color_side[5],
        color_side[6],
        stroke_side[1],
        stroke_side[2],
        stroke_side[3],
        stroke_side[5],
        stroke_side[6],
        color2_side[1],
        color2_side[2],
        color2_side[3],
        color2_side[5],
        color2_side[6],
        *color_side[10],
        *stroke_side[10],
        *color2_side[10],
    ]
    summary = _XygSceneXytaTraceObservationsOut()
    out_bytes = np.zeros(SCENE_XYTA_TRACE_OBSERVATIONS_MAX_BYTES, dtype=np.uint8)
    out_len = ctypes.c_size_t(0)
    code = int(
        _lib.xyg_scene_xyta_trace_observations_materialize(
            ctypes.byref(pack_in),
            _ptr_u8(np.frombuffer(fallback_b, dtype=np.uint8)),
            _ptr_u8(np.frombuffer(style_color_b, dtype=np.uint8)) if style_color_b else 0,
            _ptr_u8(np.frombuffer(style_stroke_b, dtype=np.uint8)) if style_stroke_b else 0,
            _ptr_u8(np.frombuffer(style_colormap_named_b, dtype=np.uint8))
            if style_colormap_mode == 1 and style_colormap_named_b
            else 0,
            _ptr_u8(np.frombuffer(style_colormap_stops, dtype=np.uint8))
            if style_colormap_mode == 2 and style_colormap_stops
            else 0,
            _ptr_f64(grid_values) if len(grid_values) else 0,
            _ptr_u8(np.frombuffer(rgba_u8, dtype=np.uint8)) if rgba_u8 else 0,
            _ptr_f64(rgba_grid_f64) if len(rgba_grid_f64) else 0,
            _ptr_f64(x_values) if len(x_values) else 0,
            _ptr_f64(y_values) if len(y_values) else 0,
            ctypes.byref(color_side[0]),
            _ptr_u8(np.frombuffer(color_side[1], dtype=np.uint8)) if color_side[1] else 0,
            _ptr_u8(np.frombuffer(color_side[2], dtype=np.uint8)) if color_side[2] else 0,
            _ptr_u8(np.frombuffer(color_side[3], dtype=np.uint8)) if color_side[3] else 0,
            _ptr_f64(color_side[4]) if len(color_side[4]) else 0,
            _ptr_u8(np.frombuffer(color_side[5], dtype=np.uint8)) if color_side[5] else 0,
            _ptr_u8(np.frombuffer(color_side[6], dtype=np.uint8)) if color_side[6] else 0,
            color_side[7].ctypes.data if len(color_side[7]) else 0,
            ctypes.cast(color_side[8], ctypes.c_void_p) if color_side[8] is not None else 0,
            ctypes.cast(color_side[9], ctypes.c_void_p) if color_side[9] is not None else 0,
            ctypes.byref(stroke_side[0]),
            _ptr_u8(np.frombuffer(stroke_side[1], dtype=np.uint8)) if stroke_side[1] else 0,
            _ptr_u8(np.frombuffer(stroke_side[2], dtype=np.uint8)) if stroke_side[2] else 0,
            _ptr_u8(np.frombuffer(stroke_side[3], dtype=np.uint8)) if stroke_side[3] else 0,
            _ptr_f64(stroke_side[4]) if len(stroke_side[4]) else 0,
            _ptr_u8(np.frombuffer(stroke_side[5], dtype=np.uint8)) if stroke_side[5] else 0,
            _ptr_u8(np.frombuffer(stroke_side[6], dtype=np.uint8)) if stroke_side[6] else 0,
            stroke_side[7].ctypes.data if len(stroke_side[7]) else 0,
            ctypes.cast(stroke_side[8], ctypes.c_void_p) if stroke_side[8] is not None else 0,
            ctypes.cast(stroke_side[9], ctypes.c_void_p) if stroke_side[9] is not None else 0,
            ctypes.byref(color2_side[0]),
            _ptr_u8(np.frombuffer(color2_side[1], dtype=np.uint8)) if color2_side[1] else 0,
            _ptr_u8(np.frombuffer(color2_side[2], dtype=np.uint8)) if color2_side[2] else 0,
            _ptr_u8(np.frombuffer(color2_side[3], dtype=np.uint8)) if color2_side[3] else 0,
            _ptr_f64(color2_side[4]) if len(color2_side[4]) else 0,
            _ptr_u8(np.frombuffer(color2_side[5], dtype=np.uint8)) if color2_side[5] else 0,
            _ptr_u8(np.frombuffer(color2_side[6], dtype=np.uint8)) if color2_side[6] else 0,
            color2_side[7].ctypes.data if len(color2_side[7]) else 0,
            ctypes.cast(color2_side[8], ctypes.c_void_p) if color2_side[8] is not None else 0,
            ctypes.cast(color2_side[9], ctypes.c_void_p) if color2_side[9] is not None else 0,
            ctypes.byref(opacity_desc),
            _ptr_f64(opacity_values) if len(opacity_values) else 0,
            ctypes.byref(artist_desc),
            _ptr_f64(artist_values) if len(artist_values) else 0,
            ctypes.byref(stroke_width_desc),
            _ptr_f64(stroke_width_values) if len(stroke_width_values) else 0,
            ctypes.byref(summary),
            _ptr_u8(out_bytes),
            len(out_bytes),
            ctypes.byref(out_len),
        )
    )
    del keepers
    if code == -2:
        raise ValueError("scene_xyta_trace_observations_materialize output buffer too small")
    if code != 0:
        raise ValueError("invalid scene_xyta_trace_observations_materialize arguments")
    blob = bytes(out_bytes[: int(out_len.value)])

    def _slice(off: int, length: int) -> bytes:
        return blob[off : off + length] if length else b""

    return {
        "trace_id": int(summary.trace_id),
        "pack_heatmap": bool(summary.pack_heatmap),
        "pack_hexbin_colormap": bool(summary.pack_hexbin_colormap),
        "pack_hexbin_rgba": bool(summary.pack_hexbin_rgba),
        "pack_ribbon_ends": bool(summary.pack_ribbon_ends),
        "pack_mesh_faces": bool(summary.pack_mesh_faces),
        "pack_scatter_paint": bool(summary.pack_scatter_paint),
        "pack_density": bool(summary.pack_density),
        "grid_shape_rows": float(summary.grid_shape_rows),
        "grid_shape_cols": float(summary.grid_shape_cols),
        "has_grid_shape": bool(summary.has_grid_shape),
        "has_grid": bool(summary.has_grid),
        "has_rgba": bool(summary.has_rgba),
        "has_rgba_grid": bool(summary.has_rgba_grid),
        "truecolor": bool(summary.truecolor),
        "has_cmap_domain": bool(summary.has_cmap_domain),
        "cmap_lo": float(summary.cmap_lo),
        "cmap_hi": float(summary.cmap_hi),
        "has_color_ch": bool(summary.has_color_ch),
        "has_style_color": bool(summary.has_style_color),
        "has_opacity": bool(summary.has_opacity),
        "has_fill_opacity": bool(summary.has_fill_opacity),
        "opacity": float(summary.opacity),
        "fill_opacity": float(summary.fill_opacity),
        "domain_x0": float(summary.domain_x0),
        "domain_x1": float(summary.domain_x1),
        "domain_y0": float(summary.domain_y0),
        "domain_y1": float(summary.domain_y1),
        "cmap_flags": int(summary.cmap_flags),
        "rows": int(summary.rows),
        "cols": int(summary.cols),
        "grid": _slice(int(summary.grid_off), int(summary.grid_len)),
        "rgba": _slice(int(summary.rgba_off), int(summary.rgba_len)),
        "rgba_grid": _slice(int(summary.rgba_grid_off), int(summary.rgba_grid_len)),
        "x": _slice(int(summary.x_off), int(summary.x_len)),
        "y": _slice(int(summary.y_off), int(summary.y_len)),
        "mean_rgba": _slice(int(summary.mean_rgba_off), int(summary.mean_rgba_len)),
        "idx": _slice(int(summary.idx_off), int(summary.idx_len)),
        "lut": _slice(int(summary.lut_off), int(summary.lut_len)),
        "cmap": _slice(int(summary.cmap_off), int(summary.cmap_len)),
        "stops": _slice(int(summary.stops_off), int(summary.stops_len)),
        "color_ch": _slice(int(summary.color_ch_off), int(summary.color_ch_len)),
        "style_color": _slice(int(summary.style_color_off), int(summary.style_color_len)),
    }


_ADMITTED_XYAF_STYLE_KEYS = frozenset(
    {
        "color",
        "stroke_color",
        "label_color",
        "label_background",
        "label_border_color",
        "dash",
        "linecap",
        "opacity",
        "width",
        "stroke_width",
        "label_opacity",
        "label_border_width",
        "rotation",
    }
)


class _XygXyafBulkStyleIn(ctypes.Structure):
    _fields_ = [
        ("color", _XygStringRef),
        ("stroke_color", _XygStringRef),
        ("label_color", _XygStringRef),
        ("label_background", _XygStringRef),
        ("label_border_color", _XygStringRef),
        ("dash", _XygStringRef),
        ("linecap", _XygStringRef),
        ("opacity_present", ctypes.c_int32),
        ("opacity", ctypes.c_double),
        ("width_present", ctypes.c_int32),
        ("width", ctypes.c_double),
        ("stroke_width_present", ctypes.c_int32),
        ("stroke_width", ctypes.c_double),
        ("label_opacity_present", ctypes.c_int32),
        ("label_opacity", ctypes.c_double),
        ("label_border_width_present", ctypes.c_int32),
        ("label_border_width", ctypes.c_double),
        ("rotation_present", ctypes.c_int32),
        ("rotation", ctypes.c_double),
        ("extra_style_key_count", ctypes.c_uint32),
    ]


class _XygXyafBulkAnnotationIn(ctypes.Structure):
    _fields_ = [
        ("kind", _XygStringRef),
        ("text", _XygStringRef),
        ("x_present", ctypes.c_int32),
        ("x", ctypes.c_double),
        ("y_present", ctypes.c_int32),
        ("y", ctypes.c_double),
        ("x0_present", ctypes.c_int32),
        ("x0", ctypes.c_double),
        ("y0_present", ctypes.c_int32),
        ("y0", ctypes.c_double),
        ("x1_present", ctypes.c_int32),
        ("x1", ctypes.c_double),
        ("y1_present", ctypes.c_int32),
        ("y1", ctypes.c_double),
        ("value_present", ctypes.c_int32),
        ("value", ctypes.c_double),
        ("start_present", ctypes.c_int32),
        ("start", ctypes.c_double),
        ("end_present", ctypes.c_int32),
        ("end", ctypes.c_double),
        ("dx_present", ctypes.c_int32),
        ("dx", ctypes.c_double),
        ("dy_present", ctypes.c_int32),
        ("dy", ctypes.c_double),
        ("size_present", ctypes.c_int32),
        ("size", ctypes.c_double),
        ("wrap_present", ctypes.c_int32),
        ("wrap", ctypes.c_double),
        ("rotation_present", ctypes.c_int32),
        ("rotation", ctypes.c_double),
        ("anchor_present", ctypes.c_int32),
        ("anchor", _XygStringRef),
        ("axis_present", ctypes.c_int32),
        ("axis", _XygStringRef),
        ("symbol_present", ctypes.c_int32),
        ("symbol", _XygStringRef),
        ("index_override_present", ctypes.c_int32),
        ("index_override", ctypes.c_uint32),
        ("style", _XygXyafBulkStyleIn),
    ]


def _marshal_xyaf_style(
    style: dict[str, Any],
    keepers: list[bytes],
    *,
    skip_rotation: bool,
) -> tuple[_XygXyafBulkStyleIn, bytes]:
    extra_blob = bytearray()
    extra_keys: list[str] = []
    typography = {
        "font_family",
        "font_size",
        "font_weight",
        "font_style",
        "fontFamily",
        "fontSize",
        "fontWeight",
        "fontStyle",
    }
    for key, value in style.items():
        if value is None or key in {"markup", *typography} or (skip_rotation and key == "rotation"):
            continue
        if key not in _ADMITTED_XYAF_STYLE_KEYS:
            extra_keys.append(str(key))
    for key in sorted(extra_keys):
        encoded = key.encode("utf-8")
        extra_blob.extend(len(encoded).to_bytes(2, "little"))
        extra_blob.extend(encoded)

    def opt_css(key: str) -> _XygStringRef:
        raw = style.get(key)
        if raw is None:
            return _XygStringRef(0, 0)
        ref, encoded = _string_ref(str(raw))
        keepers.append(encoded)
        return ref

    def opt_num(key: str) -> tuple[int, float]:
        if key not in style or style[key] is None:
            return 0, 0.0
        return 1, float(style[key])

    opacity_present, opacity = opt_num("opacity")
    width_present, width = opt_num("width")
    stroke_width_present, stroke_width = opt_num("stroke_width")
    label_opacity_present, label_opacity = opt_num("label_opacity")
    label_border_width_present, label_border_width = opt_num("label_border_width")
    rotation_present, rotation = opt_num("rotation")
    return (
        _XygXyafBulkStyleIn(
            opt_css("color"),
            opt_css("stroke_color"),
            opt_css("label_color"),
            opt_css("label_background"),
            opt_css("label_border_color"),
            opt_css("dash") if isinstance(style.get("dash"), str) else _XygStringRef(0, 0),
            opt_css("linecap") if style.get("linecap") is not None else _XygStringRef(0, 0),
            opacity_present,
            opacity,
            width_present,
            width,
            stroke_width_present,
            stroke_width,
            label_opacity_present,
            label_opacity,
            label_border_width_present,
            label_border_width,
            rotation_present if not skip_rotation else 0,
            rotation,
            len(extra_keys),
        ),
        bytes(extra_blob),
    )


def _marshal_xyaf_annotation(
    annotation: dict[str, Any],
    *,
    index_override: int | None = None,
) -> tuple[_XygXyafBulkAnnotationIn, bytes, list[bytes]]:
    annotation = dict(annotation)
    kind = str(annotation.get("kind", ""))
    style = dict(annotation.get("style") or {})
    skip_rotation = kind in {"text", "marker"}
    keepers: list[bytes] = []
    style_in, extra_blob = _marshal_xyaf_style(style, keepers, skip_rotation=skip_rotation)

    def opt_str_field(key: str) -> _XygStringRef:
        raw = annotation.get(key)
        if raw is None:
            return _XygStringRef(0, 0)
        ref, encoded = _string_ref(str(raw))
        keepers.append(encoded)
        return ref

    def opt_num_field(key: str) -> tuple[int, float]:
        if key not in annotation:
            return 0, 0.0
        return 1, float(annotation[key])

    text = annotation.get("text")
    text_ref, text_b = _string_ref(str(text) if text not in (None, "") else None)
    keepers.append(text_b)
    kind_ref, kind_b = _string_ref(kind)
    keepers.append(kind_b)
    x_present, x = opt_num_field("x")
    y_present, y = opt_num_field("y")
    x0_present, x0 = opt_num_field("x0")
    y0_present, y0 = opt_num_field("y0")
    x1_present, x1 = opt_num_field("x1")
    y1_present, y1 = opt_num_field("y1")
    value_present, value = opt_num_field("value")
    start_present, start = opt_num_field("start")
    end_present, end = opt_num_field("end")
    dx_present, dx = opt_num_field("dx")
    dy_present, dy = opt_num_field("dy")
    size_present, size = opt_num_field("size")
    wrap_present, wrap = opt_num_field("wrap")
    rotation_present, rotation = opt_num_field("rotation")
    row = _XygXyafBulkAnnotationIn(
        kind_ref,
        text_ref,
        x_present,
        x,
        y_present,
        y,
        x0_present,
        x0,
        y0_present,
        y0,
        x1_present,
        x1,
        y1_present,
        y1,
        value_present,
        value,
        start_present,
        start,
        end_present,
        end,
        dx_present,
        dx,
        dy_present,
        dy,
        size_present,
        size,
        wrap_present,
        wrap,
        rotation_present,
        rotation,
        1 if "anchor" in annotation else 0,
        opt_str_field("anchor") if "anchor" in annotation else _XygStringRef(0, 0),
        1 if "axis" in annotation else 0,
        opt_str_field("axis") if "axis" in annotation else _XygStringRef(0, 0),
        1 if "symbol" in annotation else 0,
        opt_str_field("symbol") if "symbol" in annotation else _XygStringRef(0, 0),
        1 if index_override is not None else 0,
        int(index_override or 0) & 0xFFFFFFFF,
        style_in,
    )
    return row, extra_blob, keepers


class SceneXyafBulkPackError(ValueError):
    """Bulk XYAF pack failure from ``xyg_scene_xyaf_bulk_pack`` (ABI 324)."""

    def __init__(self, code: int, index: int) -> None:
        self.code = int(code)
        self.index = int(index)
        super().__init__(f"scene xyaf bulk pack failed: code={code} index={index}")


def scene_xyaf_bulk_pack(
    annotations: Sequence[Mapping[str, Any]],
    *,
    indices: Sequence[int] | None = None,
) -> bytes:
    """Bulk-pack authored annotations via ``xyg_scene_xyaf_bulk_pack`` (ABI 324)."""
    if indices is not None and len(indices) != len(annotations):
        raise ValueError("xyaf bulk pack indices length mismatch")
    rows = (_XygXyafBulkAnnotationIn * len(annotations))()
    extra_blob = bytearray()
    keepers: list[bytes] = []
    for pos, annotation in enumerate(annotations):
        index_override = None if indices is None else int(indices[pos])
        row, blob, row_keepers = _marshal_xyaf_annotation(
            dict(annotation), index_override=index_override
        )
        rows[pos] = row
        extra_blob.extend(blob)
        keepers.extend(row_keepers)
    keys_ptr, keys_len = _optional_u8_ptr(bytes(extra_blob))
    out = np.zeros(SCENE_XYAF_BULK_PACK_MAX, dtype=np.uint8)
    out_len = ctypes.c_size_t(0)
    error_index = ctypes.c_uint32(0)
    code = int(
        _lib.xyg_scene_xyaf_bulk_pack(
            ctypes.cast(rows, ctypes.c_void_p) if len(rows) else 0,
            len(annotations),
            keys_ptr,
            keys_len,
            _ptr_u8(out),
            len(out),
            ctypes.byref(out_len),
            ctypes.byref(error_index),
        )
    )
    del keepers, rows
    if code == -2:
        raise ValueError("scene_xyaf_bulk_pack output buffer too small")
    if code != 0:
        raise SceneXyafBulkPackError(code, int(error_index.value))
    return bytes(out[: int(out_len.value)])
