// XYTC trace observation materialize C ABI (ABI 325).

use xyg_engine::scene_xytc_trace_observations_materialize::{
    scene_xytc_trace_observations_materialize, SceneXytcGradientStopIn,
    SceneXytcTraceObservationsIn, SceneXytcTraceObservationsOut,
    SCENE_XYTC_TRACE_OBSERVATIONS_MAX_BYTES,
};

/// Scalar/style header for XYTC observation materialize.
#[repr(C)]
pub struct XygSceneXytcTraceObservationsIn {
    pub show_legend: i32,
    pub has_name: i32,
    pub marker_path_present: i32,
    pub use_density: i32,
    pub joined_fill: i32,
    pub symbol_is_int: i32,
    pub symbol_int: u16,
    pub opacity: f64,
    pub fill_opacity: f64,
    pub stroke_opacity: f64,
    pub line_opacity: f64,
    pub has_stroke: i32,
    pub has_line_color: i32,
    pub has_color: i32,
    pub has_size: i32,
    pub size: f64,
    pub has_size_ch: i32,
    pub has_size_ch_constant: i32,
    pub size_ch_constant: f64,
    pub has_stroke_width: i32,
    pub stroke_width: f64,
    pub has_width: i32,
    pub width: f64,
    pub has_line_width: i32,
    pub line_width: f64,
    pub has_hex_dx: i32,
    pub hex_dx: f64,
    pub has_hex_dy: i32,
    pub hex_dy: f64,
    pub has_stroke_perimeter: i32,
    pub stroke_perimeter_is_bool: i32,
    pub stroke_perimeter_true: i32,
    pub wedge_gap_raw: f64,
    pub dash_is_array: i32,
    pub has_fill: i32,
    pub fill_is_string: i32,
    pub fill_has_full_spec: i32,
    pub fill_stop_count: usize,
    pub marker_path_filled: i32,
    pub marker_contour_count: usize,
    pub has_color2: i32,
    pub kind_is_ribbon: i32,
    pub has_end_pair: i32,
    pub corner_radius_seq: i32,
    pub corner_radius_r0: f64,
    pub corner_radius_r1: f64,
    pub color_ch_present: i32,
    pub color_ch_has_constant: i32,
    pub kind_len: usize,
    pub name_len: usize,
    pub symbol_len: usize,
    pub stroke_len: usize,
    pub line_color_len: usize,
    pub color_css_len: usize,
    pub dash_len: usize,
    pub dash_values_len: usize,
    pub fill_string_len: usize,
    pub fill_space_len: usize,
    pub fill_dir_len: usize,
    pub fill_stop_t_len: usize,
    pub fill_stop_css_len: usize,
    pub fill_stop_css_lens_len: usize,
    pub fill_dict_gradient_len: usize,
    pub fill_dict_space_len: usize,
    pub marker_values_len: usize,
    pub marker_lens_len: usize,
    pub marker_glyph_len: usize,
    pub source_paint_len: usize,
    pub color2_source_const_len: usize,
    pub color2_target_const_len: usize,
    pub color_mode_len: usize,
    pub color_const_len: usize,
    pub linecap_len: usize,
    pub step_len: usize,
    pub curve_len: usize,
}

/// Materialized XYTC pack inputs returned by ABI 325.
#[repr(C)]
pub struct XygSceneXytcTraceObservationsOut {
    pub show_legend: i32,
    pub has_name: i32,
    pub marker_path_present: i32,
    pub use_density: i32,
    pub joined_fill: i32,
    pub marker_packed: i32,
    pub glyph_packed: i32,
    pub color2_class: i32,
    pub color2_gradient_packed: i32,
    pub symbol_is_int: i32,
    pub symbol_int: u16,
    pub opacity: f64,
    pub fill_opacity: f64,
    pub stroke_opacity: f64,
    pub line_opacity: f64,
    pub has_stroke: i32,
    pub has_line_color: i32,
    pub has_size: i32,
    pub size: f64,
    pub has_size_ch: i32,
    pub has_size_ch_constant: i32,
    pub size_ch_constant: f64,
    pub has_stroke_width: i32,
    pub stroke_width: f64,
    pub has_width: i32,
    pub width: f64,
    pub has_line_width: i32,
    pub line_width: f64,
    pub has_hex_dx: i32,
    pub hex_dx: f64,
    pub has_hex_dy: i32,
    pub hex_dy: f64,
    pub has_stroke_perimeter: i32,
    pub stroke_perimeter_is_bool: i32,
    pub stroke_perimeter_true: i32,
    pub dash_is_array: i32,
    pub has_fill: i32,
    pub fill_kind: i32,
    pub color_ch_present: i32,
    pub color_ch_has_constant: i32,
    pub radius_seq: i32,
    pub r0: f64,
    pub r1: f64,
    pub wedge_gap_raw: f64,
    pub kind_len: usize,
    pub name_len: usize,
    pub marker_blob_len: usize,
    pub color2_gradient_len: usize,
    pub symbol_len: usize,
    pub dash_len: usize,
    pub dash_pattern_len: usize,
    pub linecap_len: usize,
    pub step_len: usize,
    pub curve_len: usize,
    pub fill_css_len: usize,
    pub fill_space_len: usize,
    pub fill_gradient_len: usize,
    pub stroke_len: usize,
    pub line_color_len: usize,
    pub color_css_len: usize,
    pub color_mode_len: usize,
    pub color_const_len: usize,
    pub kind_off: usize,
    pub name_off: usize,
    pub marker_blob_off: usize,
    pub color2_gradient_off: usize,
    pub symbol_off: usize,
    pub dash_off: usize,
    pub dash_pattern_off: usize,
    pub linecap_off: usize,
    pub step_off: usize,
    pub curve_off: usize,
    pub fill_css_off: usize,
    pub fill_space_off: usize,
    pub fill_gradient_off: usize,
    pub stroke_off: usize,
    pub line_color_off: usize,
    pub color_css_off: usize,
    pub color_mode_off: usize,
    pub color_const_off: usize,
}

fn write_xytc_observations_out(
    materialized: &SceneXytcTraceObservationsOut,
    summary: &mut XygSceneXytcTraceObservationsOut,
    out_bytes: *mut u8,
    out_cap: usize,
    out_len: *mut usize,
) -> Result<(), i32> {
    let mut blob: Vec<u8> = Vec::new();
    let append = |blob: &mut Vec<u8>, chunk: &[u8]| -> usize {
        let off = blob.len();
        blob.extend_from_slice(chunk);
        off
    };
    let append_f64 = |blob: &mut Vec<u8>, values: &[f64]| -> usize {
        let off = blob.len();
        for value in values {
            blob.extend_from_slice(&value.to_le_bytes());
        }
        off
    };
    summary.show_legend = materialized.show_legend;
    summary.has_name = materialized.has_name;
    summary.marker_path_present = materialized.marker_path_present;
    summary.use_density = materialized.use_density;
    summary.joined_fill = materialized.joined_fill;
    summary.marker_packed = materialized.marker_packed;
    summary.glyph_packed = materialized.glyph_packed;
    summary.color2_class = materialized.color2_class;
    summary.color2_gradient_packed = materialized.color2_gradient_packed;
    summary.symbol_is_int = materialized.symbol_is_int;
    summary.symbol_int = materialized.symbol_int;
    summary.opacity = materialized.opacity;
    summary.fill_opacity = materialized.fill_opacity;
    summary.stroke_opacity = materialized.stroke_opacity;
    summary.line_opacity = materialized.line_opacity;
    summary.has_stroke = materialized.has_stroke;
    summary.has_line_color = materialized.has_line_color;
    summary.has_size = materialized.has_size;
    summary.size = materialized.size;
    summary.has_size_ch = materialized.has_size_ch;
    summary.has_size_ch_constant = materialized.has_size_ch_constant;
    summary.size_ch_constant = materialized.size_ch_constant;
    summary.has_stroke_width = materialized.has_stroke_width;
    summary.stroke_width = materialized.stroke_width;
    summary.has_width = materialized.has_width;
    summary.width = materialized.width;
    summary.has_line_width = materialized.has_line_width;
    summary.line_width = materialized.line_width;
    summary.has_hex_dx = materialized.has_hex_dx;
    summary.hex_dx = materialized.hex_dx;
    summary.has_hex_dy = materialized.has_hex_dy;
    summary.hex_dy = materialized.hex_dy;
    summary.has_stroke_perimeter = materialized.has_stroke_perimeter;
    summary.stroke_perimeter_is_bool = materialized.stroke_perimeter_is_bool;
    summary.stroke_perimeter_true = materialized.stroke_perimeter_true;
    summary.dash_is_array = materialized.dash_is_array;
    summary.has_fill = materialized.has_fill;
    summary.fill_kind = materialized.fill_kind;
    summary.color_ch_present = materialized.color_ch_present;
    summary.color_ch_has_constant = materialized.color_ch_has_constant;
    summary.radius_seq = materialized.radius_seq;
    summary.r0 = materialized.r0;
    summary.r1 = materialized.r1;
    summary.wedge_gap_raw = materialized.wedge_gap_raw;
    summary.kind_off = append(&mut blob, &materialized.kind);
    summary.kind_len = materialized.kind.len();
    summary.name_off = append(&mut blob, &materialized.name);
    summary.name_len = materialized.name.len();
    summary.marker_blob_off = append(&mut blob, &materialized.marker_blob);
    summary.marker_blob_len = materialized.marker_blob.len();
    summary.color2_gradient_off = append(&mut blob, &materialized.color2_gradient_blob);
    summary.color2_gradient_len = materialized.color2_gradient_blob.len();
    summary.symbol_off = append(&mut blob, &materialized.symbol_b);
    summary.symbol_len = materialized.symbol_b.len();
    summary.dash_off = append(&mut blob, &materialized.dash_b);
    summary.dash_len = materialized.dash_b.len();
    summary.dash_pattern_off = append_f64(&mut blob, &materialized.dash_pattern);
    summary.dash_pattern_len = materialized.dash_pattern.len();
    summary.linecap_off = append(&mut blob, &materialized.linecap_b);
    summary.linecap_len = materialized.linecap_b.len();
    summary.step_off = append(&mut blob, &materialized.step_b);
    summary.step_len = materialized.step_b.len();
    summary.curve_off = append(&mut blob, &materialized.curve_b);
    summary.curve_len = materialized.curve_b.len();
    summary.fill_css_off = append(&mut blob, &materialized.fill_css);
    summary.fill_css_len = materialized.fill_css.len();
    summary.fill_space_off = append(&mut blob, &materialized.fill_space);
    summary.fill_space_len = materialized.fill_space.len();
    summary.fill_gradient_off = append(&mut blob, &materialized.fill_gradient_blob);
    summary.fill_gradient_len = materialized.fill_gradient_blob.len();
    summary.stroke_off = append(&mut blob, &materialized.stroke_css);
    summary.stroke_len = materialized.stroke_css.len();
    summary.line_color_off = append(&mut blob, &materialized.line_color_b);
    summary.line_color_len = materialized.line_color_b.len();
    summary.color_css_off = append(&mut blob, &materialized.color_css);
    summary.color_css_len = materialized.color_css.len();
    summary.color_mode_off = append(&mut blob, &materialized.color_mode);
    summary.color_mode_len = materialized.color_mode.len();
    summary.color_const_off = append(&mut blob, &materialized.color_const);
    summary.color_const_len = materialized.color_const.len();
    if blob.len() > out_cap.min(SCENE_XYTC_TRACE_OBSERVATIONS_MAX_BYTES) {
        return Err(-2);
    }
    if !blob.is_empty() {
        if out_bytes.is_null() {
            return Err(-1);
        }
        unsafe {
            std::ptr::copy_nonoverlapping(blob.as_ptr(), out_bytes, blob.len());
        }
    }
    unsafe {
        *out_len = blob.len();
    }
    Ok(())
}

unsafe fn xytc_read_fill_stops<'a>(
    stop_count: usize,
    stop_t: *const f64,
    stop_t_len: usize,
    stop_css: *const u8,
    stop_css_len: usize,
    stop_css_lens: *const u32,
    stop_css_lens_len: usize,
) -> Result<Vec<SceneXytcGradientStopIn<'a>>, i32> {
    if stop_count == 0 {
        return Ok(Vec::new());
    }
    if stop_t_len != stop_count
        || stop_css_lens_len != stop_count
        || stop_count > 255
    {
        return Err(-1);
    }
    let t_slice = optional_f64(stop_t, stop_t_len).ok_or(-1)?;
    let css_bytes = optional_bytes(stop_css, stop_css_len).ok_or(-1)?;
    let lens = std::slice::from_raw_parts(stop_css_lens, stop_css_lens_len);
    let mut css_off = 0usize;
    let mut out = Vec::with_capacity(stop_count);
    for (&t, &len) in t_slice.iter().zip(lens.iter()) {
        let len = len as usize;
        if css_off.saturating_add(len) > css_bytes.len() {
            return Err(-1);
        }
        let css = read_utf8(css_bytes[css_off..css_off + len].as_ptr(), len).ok_or(-1)?;
        out.push(SceneXytcGradientStopIn { t, css });
        css_off += len;
    }
    if css_off != css_bytes.len() {
        return Err(-1);
    }
    Ok(out)
}

#[allow(clippy::too_many_arguments)]
#[no_mangle]
pub unsafe extern "C" fn xyg_scene_xytc_trace_observations_materialize(
    input: *const XygSceneXytcTraceObservationsIn,
    kind: *const u8,
    name: *const u8,
    symbol: *const u8,
    stroke: *const u8,
    line_color: *const u8,
    color_css: *const u8,
    dash: *const u8,
    dash_values: *const f64,
    fill_string: *const u8,
    fill_space: *const u8,
    fill_dir: *const u8,
    fill_stop_t: *const f64,
    fill_stop_css: *const u8,
    fill_stop_css_lens: *const u32,
    fill_dict_gradient: *const u8,
    fill_dict_space: *const u8,
    marker_values: *const f64,
    marker_lens: *const u32,
    marker_glyph: *const u8,
    source_paint: *const u8,
    color2_source_const: *const u8,
    color2_target_const: *const u8,
    color_mode: *const u8,
    color_const: *const u8,
    linecap: *const u8,
    step: *const u8,
    curve: *const u8,
    summary: *mut XygSceneXytcTraceObservationsOut,
    out_bytes: *mut u8,
    out_cap: usize,
    out_len: *mut usize,
) -> i32 {
    if input.is_null() || summary.is_null() || out_len.is_null() {
        return -1;
    }
    let header = &*input;
    let kind_text = match read_utf8(kind, header.kind_len) {
        Some(v) => v,
        None => return -1,
    };
    let name_text = read_utf8(name, header.name_len).unwrap_or("");
    let symbol_text = read_utf8(symbol, header.symbol_len);
    let stroke_text = read_utf8(stroke, header.stroke_len);
    let line_color_text = read_utf8(line_color, header.line_color_len);
    let color_css_text = read_utf8(color_css, header.color_css_len);
    let dash_text = read_utf8(dash, header.dash_len);
    let dash_values_slice = match optional_f64(dash_values, header.dash_values_len) {
        Some(v) => v,
        None => return -1,
    };
    let fill_string_text = read_utf8(fill_string, header.fill_string_len);
    let fill_space_text = read_utf8(fill_space, header.fill_space_len);
    let fill_dir_text = read_utf8(fill_dir, header.fill_dir_len);
    let fill_stops = match xytc_read_fill_stops(
        header.fill_stop_count,
        fill_stop_t,
        header.fill_stop_t_len,
        fill_stop_css,
        header.fill_stop_css_len,
        fill_stop_css_lens,
        header.fill_stop_css_lens_len,
    ) {
        Ok(v) => v,
        Err(code) => return code,
    };
    let fill_stops_refs: Vec<SceneXytcGradientStopIn<'_>> = fill_stops
        .iter()
        .map(|stop| SceneXytcGradientStopIn {
            t: stop.t,
            css: stop.css,
        })
        .collect();
    let fill_dict_gradient_text = read_utf8(fill_dict_gradient, header.fill_dict_gradient_len);
    let fill_dict_space_text = read_utf8(fill_dict_space, header.fill_dict_space_len);
    let marker_values_slice = match optional_f64(marker_values, header.marker_values_len) {
        Some(v) => v,
        None => return -1,
    };
    let marker_lens_slice = if header.marker_lens_len == 0 {
        &[][..]
    } else if marker_lens.is_null() {
        return -1;
    } else {
        std::slice::from_raw_parts(marker_lens, header.marker_lens_len)
    };
    if header.marker_contour_count != marker_lens_slice.len() {
        return -1;
    }
    let marker_glyph_text = read_utf8(marker_glyph, header.marker_glyph_len);
    let source_paint_text = match read_utf8(source_paint, header.source_paint_len) {
        Some(v) => v,
        None => return -1,
    };
    let color2_source_text = read_utf8(color2_source_const, header.color2_source_const_len);
    let color2_target_text = read_utf8(color2_target_const, header.color2_target_const_len);
    let color_mode_text = read_utf8(color_mode, header.color_mode_len);
    let color_const_text = read_utf8(color_const, header.color_const_len);
    let linecap_text = read_utf8(linecap, header.linecap_len);
    let step_text = read_utf8(step, header.step_len);
    let curve_text = read_utf8(curve, header.curve_len);
    let materialize_in = SceneXytcTraceObservationsIn {
        show_legend: header.show_legend,
        kind: kind_text,
        has_name: header.has_name,
        name: name_text,
        marker_path_present: header.marker_path_present,
        use_density: header.use_density,
        joined_fill: header.joined_fill,
        symbol_is_int: header.symbol_is_int,
        symbol_int: header.symbol_int,
        symbol_text,
        opacity: header.opacity,
        fill_opacity: header.fill_opacity,
        stroke_opacity: header.stroke_opacity,
        line_opacity: header.line_opacity,
        has_stroke: header.has_stroke,
        stroke_css: stroke_text,
        has_line_color: header.has_line_color,
        line_color: line_color_text,
        has_color: header.has_color,
        color_css: color_css_text,
        has_size: header.has_size,
        size: header.size,
        has_size_ch: header.has_size_ch,
        has_size_ch_constant: header.has_size_ch_constant,
        size_ch_constant: header.size_ch_constant,
        has_stroke_width: header.has_stroke_width,
        stroke_width: header.stroke_width,
        has_width: header.has_width,
        width: header.width,
        has_line_width: header.has_line_width,
        line_width: header.line_width,
        has_hex_dx: header.has_hex_dx,
        hex_dx: header.hex_dx,
        has_hex_dy: header.has_hex_dy,
        hex_dy: header.hex_dy,
        has_stroke_perimeter: header.has_stroke_perimeter,
        stroke_perimeter_is_bool: header.stroke_perimeter_is_bool,
        stroke_perimeter_true: header.stroke_perimeter_true,
        wedge_gap_raw: header.wedge_gap_raw,
        dash_is_array: header.dash_is_array,
        dash_text,
        dash_values: dash_values_slice,
        has_fill: header.has_fill,
        fill_is_string: header.fill_is_string,
        fill_string: fill_string_text,
        fill_has_full_spec: header.fill_has_full_spec,
        fill_space: fill_space_text,
        fill_dir: fill_dir_text,
        fill_stops: &fill_stops_refs,
        fill_dict_gradient: fill_dict_gradient_text,
        fill_dict_space: fill_dict_space_text,
        marker_path_filled: header.marker_path_filled,
        marker_contour_values: marker_values_slice,
        marker_contour_lens: marker_lens_slice,
        marker_glyph: marker_glyph_text,
        has_color2: header.has_color2,
        kind_is_ribbon: header.kind_is_ribbon,
        color2_source_const: color2_source_text,
        color2_target_const: color2_target_text,
        source_paint: source_paint_text,
        has_end_pair: header.has_end_pair,
        corner_radius_seq: header.corner_radius_seq,
        corner_radius_r0: header.corner_radius_r0,
        corner_radius_r1: header.corner_radius_r1,
        color_ch_present: header.color_ch_present,
        color_ch_has_constant: header.color_ch_has_constant,
        color_ch_mode: color_mode_text,
        color_ch_constant: color_const_text,
        linecap: linecap_text,
        step: step_text,
        curve: curve_text,
    };
    let materialized = match scene_xytc_trace_observations_materialize(&materialize_in) {
        Ok(v) => v,
        Err(code) => return code,
    };
    match write_xytc_observations_out(&materialized, &mut *summary, out_bytes, out_cap, out_len) {
        Ok(()) => 0,
        Err(code) => code,
    }
}
