"""ctypes bindings for scene bulk packers (ABI 321-322)."""

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


def init(native: Any) -> None:
    """Wire host pointers after ``xyg._native`` finishes loading the cdylib."""
    global _lib, _ptr_u8, _ptr_f64, _optional_u8_ptr
    global SCENE_XYCF_PACK_MAX, SCENE_FIGURE_SUPPORT_PACK_MAX
    _lib = native._lib
    _ptr_u8 = native._ptr_u8
    _ptr_f64 = native._ptr_f64
    _optional_u8_ptr = native._optional_u8_ptr
    SCENE_XYCF_PACK_MAX = native.SCENE_XYCF_PACK_MAX
    SCENE_FIGURE_SUPPORT_PACK_MAX = native.SCENE_FIGURE_SUPPORT_PACK_MAX


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
