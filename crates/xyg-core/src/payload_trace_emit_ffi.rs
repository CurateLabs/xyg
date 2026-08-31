// Trace payload entry materialize C ABI (ABI 321+).

use xyg_engine::payload_trace_emit_materialize::{
    payload_trace_emit_materialize, PayloadTraceChannelIn, PayloadTraceColumnIn,
    PayloadTraceEmitMaterializeIn, PayloadTraceEmitMaterialized, PAYLOAD_TRACE_EMIT_MAX_BYTES,
    PAYLOAD_TRACE_EMIT_MAX_CHANNELS, PAYLOAD_TRACE_EMIT_MAX_GEOM,
};

unsafe fn trace_read_utf8<'a>(ptr: *const u8, len: usize) -> Option<&'a str> {
    if len == 0 { Some("") } else if ptr.is_null() { None } else {
        std::str::from_utf8(std::slice::from_raw_parts(ptr, len)).ok()
    }
}

unsafe fn trace_optional_f64<'a>(ptr: *const f64, len: usize) -> Option<&'a [f64]> {
    if len == 0 { Some(&[]) } else if ptr.is_null() { None } else {
        Some(std::slice::from_raw_parts(ptr, len))
    }
}

unsafe fn trace_optional_u32<'a>(ptr: *const u32, len: usize) -> Option<&'a [u32]> {
    if len == 0 { Some(&[]) } else if ptr.is_null() { None } else {
        Some(std::slice::from_raw_parts(ptr, len))
    }
}

#[repr(C)]
pub struct XygPayloadTraceColumnDesc {
    pub present: i32,
    pub values_len: usize,
    pub col_min: f64,
    pub col_max: f64,
    pub null_count: u64,
    pub sticky_offset: f64,
    pub kind_len: usize,
}

#[repr(C)]
pub struct XygPayloadTraceChannelDesc {
    pub present: i32,
    pub mode: i32,
    pub n_categories: usize,
    pub domain_lo: f64,
    pub domain_hi: f64,
    pub values_f64_len: usize,
    pub values_u8_len: usize,
    pub style_dtype_u8: i32,
    pub null_count: u64,
}

#[repr(C)]
pub struct XygPayloadTraceEmitIn {
    pub kind_len: usize,
    pub n_points: u64,
    pub segment_count: u64,
    pub polar: i32,
    pub force_density: i32,
    pub per_item: i32,
    pub x_axis_type: i32,
    pub y_axis_type: i32,
    pub x_axis_scale_len: usize,
    pub y_axis_scale_len: usize,
    pub xr0: f64,
    pub xr1: f64,
    pub px_width: u32,
    pub style_color_is_none: i32,
    pub has_trace_animation: i32,
    pub has_transition_keys: i32,
    pub has_tooltip_rows: i32,
    pub n_tooltip_rows: usize,
    pub orientation_len: usize,
    pub has_color2_ch: i32,
    pub has_color_ch: i32,
    pub has_stroke_ch: i32,
    pub has_style_channels: i32,
    pub heatmap_rows: u32,
    pub heatmap_cols: u32,
    pub has_rgba_grid: i32,
    pub borrow_heatmaps: i32,
    pub style_colormap_is_none: i32,
    pub grid_values_len: usize,
    pub grid_domain_lo: f64,
    pub grid_domain_hi: f64,
    pub max_rows: usize,
    pub bin_x_len: usize,
    pub bin_x0: f64,
    pub bin_x1: f64,
    pub transition_keys_len: usize,
}

#[repr(C)]
pub struct XygPayloadTraceGeomOut {
    pub registry_key: i32,
    pub nested: i32,
    pub dtype_code: i32,
    pub offset: f64,
    pub scale: f64,
    pub has_kind: i32,
    pub len: u32,
    pub bytes_offset: usize,
    pub bytes_len: usize,
}

#[repr(C)]
pub struct XygPayloadTraceChannelOut {
    pub registry_key: i32,
    pub buf_kind: i32,
    pub mark_dtype_u8: i32,
    pub ship_palette: i32,
    pub set_n: i32,
    pub len: u32,
    pub bytes_offset: usize,
    pub bytes_len: usize,
}

#[repr(C)]
pub struct XygPayloadTraceEmitOut {
    pub emit_path: i32,
    pub tier: i32,
    pub n_marks: u64,
    pub decimation_px: u32,
    pub apply_palette_default: i32,
    pub attach_animation: i32,
    pub attach_transition: i32,
    pub attach_tooltip: i32,
    pub filter_tooltip_by_sel: i32,
    pub tooltip_length_ok: i32,
    pub clear_shipped_sel: i32,
    pub set_shipped_sel: i32,
    pub drill_mode_false: i32,
    pub attempt_role_keys: i32,
    pub animation_fallback: i32,
    pub n_geometry: usize,
    pub n_channels: usize,
    pub transition_lo_offset: usize,
    pub transition_lo_len: usize,
    pub transition_hi_offset: usize,
    pub transition_hi_len: usize,
    pub has_bar: i32,
    pub bar_orientation: i32,
    pub bar_value_axis: i32,
    pub bar_width: f64,
    pub bar_has_value0_const: i32,
    pub bar_value0_const: f64,
    pub bar_n_geom: usize,
    pub has_heatmap: i32,
    pub heatmap_w: u32,
    pub heatmap_h: u32,
    pub heatmap_attach_color: i32,
    pub heatmap_attach_encoding: i32,
    pub heatmap_borrow_canonical: i32,
    pub heatmap_grid_offset: usize,
    pub heatmap_grid_len: usize,
}

unsafe fn trace_column_from_c<'a>(desc: &XygPayloadTraceColumnDesc, values: *const f64, kind_ptr: *const u8) -> Result<PayloadTraceColumnIn<'a>, i32> {
    if desc.present == 0 { return Ok(PayloadTraceColumnIn::default()); }
    if desc.values_len > 0 && values.is_null() { return Err(-1); }
    let values_slice = if desc.values_len == 0 { &[][..] } else { std::slice::from_raw_parts(values, desc.values_len) };
    let kind = if desc.kind_len == 0 { None } else if kind_ptr.is_null() { return Err(-1); } else { trace_read_utf8(kind_ptr, desc.kind_len) };
    Ok(PayloadTraceColumnIn { present: desc.present, values: values_slice, col_min: desc.col_min, col_max: desc.col_max, null_count: desc.null_count, sticky_offset: desc.sticky_offset, kind })
}

unsafe fn trace_channel_from_c<'a>(desc: &XygPayloadTraceChannelDesc, values_f64: *const f64, values_u8: *const u8) -> Result<PayloadTraceChannelIn<'a>, i32> {
    if desc.present == 0 { return Ok(PayloadTraceChannelIn::default()); }
    if desc.values_f64_len > 0 && values_f64.is_null() { return Err(-1); }
    if desc.values_u8_len > 0 && values_u8.is_null() { return Err(-1); }
    let f64_slice = if desc.values_f64_len == 0 { &[][..] } else { std::slice::from_raw_parts(values_f64, desc.values_f64_len) };
    let u8_slice = if desc.values_u8_len == 0 { &[][..] } else { std::slice::from_raw_parts(values_u8, desc.values_u8_len) };
    Ok(PayloadTraceChannelIn { present: desc.present, mode: desc.mode, n_categories: desc.n_categories, domain_lo: desc.domain_lo, domain_hi: desc.domain_hi, values_f64: f64_slice, values_u8: u8_slice, style_dtype_u8: desc.style_dtype_u8, null_count: desc.null_count })
}

fn write_materialized(materialized: &PayloadTraceEmitMaterialized, summary: *mut XygPayloadTraceEmitOut, geom_out: *mut XygPayloadTraceGeomOut, geom_cap: usize, chan_out: *mut XygPayloadTraceChannelOut, chan_cap: usize, out_bytes: *mut u8, out_bytes_cap: usize, out_bytes_len: *mut usize) -> Result<(), i32> {
    if summary.is_null() || out_bytes_len.is_null() { return Err(-1); }
    let summary = unsafe { &mut *summary };
    summary.emit_path = materialized.emit_path;
    summary.tier = materialized.tier;
    summary.n_marks = materialized.n_marks;
    summary.decimation_px = materialized.decimation_px;
    summary.apply_palette_default = materialized.apply_palette_default;
    summary.attach_animation = materialized.attach_animation;
    summary.attach_transition = materialized.attach_transition;
    summary.attach_tooltip = materialized.attach_tooltip;
    summary.filter_tooltip_by_sel = materialized.filter_tooltip_by_sel;
    summary.tooltip_length_ok = materialized.tooltip_length_ok;
    summary.clear_shipped_sel = materialized.clear_shipped_sel;
    summary.set_shipped_sel = materialized.set_shipped_sel;
    summary.drill_mode_false = materialized.drill_mode_false;
    summary.attempt_role_keys = materialized.attempt_role_keys;
    summary.animation_fallback = materialized.animation_fallback;
    summary.heatmap_attach_color = materialized.heatmap_attach_color;
    summary.heatmap_attach_encoding = materialized.heatmap_attach_encoding;
    summary.heatmap_borrow_canonical = materialized.heatmap_borrow_canonical;
    summary.has_bar = i32::from(materialized.bar.is_some());
    if let Some(bar) = &materialized.bar {
        summary.bar_orientation = bar.orientation;
        summary.bar_value_axis = bar.value_axis;
        summary.bar_width = bar.width;
        summary.bar_has_value0_const = bar.has_value0_const;
        summary.bar_value0_const = bar.value0_const;
    }
    summary.has_heatmap = i32::from(materialized.heatmap.is_some());
    let mut blob: Vec<u8> = Vec::new();
    let n_geom = materialized.geometry.len().min(geom_cap).min(PAYLOAD_TRACE_EMIT_MAX_GEOM);
    summary.n_geometry = n_geom;
    if n_geom > 0 && geom_out.is_null() { return Err(-1); }
    for (idx, geom) in materialized.geometry.iter().take(n_geom).enumerate() {
        let bytes_offset = blob.len();
        blob.extend_from_slice(&geom.column.bytes);
        let out_geom = unsafe { &mut *geom_out.add(idx) };
        out_geom.registry_key = geom.registry_key;
        out_geom.nested = geom.nested;
        out_geom.dtype_code = geom.column.dtype_code;
        out_geom.offset = geom.column.offset;
        out_geom.scale = geom.column.scale;
        out_geom.has_kind = geom.column.has_kind;
        out_geom.len = geom.column.len;
        out_geom.bytes_offset = bytes_offset;
        out_geom.bytes_len = geom.column.bytes.len();
    }
    if let Some(hm) = &materialized.heatmap {
        summary.heatmap_grid_offset = blob.len();
        blob.extend_from_slice(&hm.grid_buf.bytes);
        summary.heatmap_grid_len = hm.grid_buf.bytes.len();
    }
    let n_chan = materialized.channels.len().min(chan_cap).min(PAYLOAD_TRACE_EMIT_MAX_CHANNELS);
    summary.n_channels = n_chan;
    if n_chan > 0 && chan_out.is_null() { return Err(-1); }
    for (idx, ch) in materialized.channels.iter().take(n_chan).enumerate() {
        let bytes_offset = blob.len();
        blob.extend_from_slice(&ch.wire.bytes);
        let out_ch = unsafe { &mut *chan_out.add(idx) };
        out_ch.registry_key = ch.registry_key;
        out_ch.buf_kind = ch.wire.buf_kind;
        out_ch.mark_dtype_u8 = ch.wire.mark_dtype_u8;
        out_ch.ship_palette = ch.wire.ship_palette;
        out_ch.set_n = ch.wire.set_n;
        out_ch.len = ch.wire.len;
        out_ch.bytes_offset = bytes_offset;
        out_ch.bytes_len = ch.wire.bytes.len();
    }
    if !materialized.transition_lo.is_empty() {
        summary.transition_lo_offset = blob.len();
        summary.transition_lo_len = materialized.transition_lo.len();
        blob.extend_from_slice(&materialized.transition_lo);
    }
    if !materialized.transition_hi.is_empty() {
        summary.transition_hi_offset = blob.len();
        summary.transition_hi_len = materialized.transition_hi.len();
        blob.extend_from_slice(&materialized.transition_hi);
    }
    if blob.len() > out_bytes_cap.min(PAYLOAD_TRACE_EMIT_MAX_BYTES) { return Err(-2); }
    if !blob.is_empty() {
        if out_bytes.is_null() { return Err(-1); }
        unsafe { std::ptr::copy_nonoverlapping(blob.as_ptr(), out_bytes, blob.len()); }
    }
    unsafe { *out_bytes_len = blob.len(); }
    Ok(())
}

#[allow(clippy::too_many_arguments)]
#[no_mangle]
pub unsafe extern "C" fn xyg_payload_trace_emit_materialize(
    emit_in: *const XygPayloadTraceEmitIn,
    kind: *const u8,
    x_axis_scale: *const u8,
    y_axis_scale: *const u8,
    orientation: *const u8,
    columns: *const XygPayloadTraceColumnDesc,
    column_values: *const *const f64,
    column_kinds: *const *const u8,
    color_ch: *const XygPayloadTraceChannelDesc,
    stroke_ch: *const XygPayloadTraceChannelDesc,
    color2_ch: *const XygPayloadTraceChannelDesc,
    size_ch: *const XygPayloadTraceChannelDesc,
    style_channels: *const XygPayloadTraceChannelDesc,
    color_f64: *const f64,
    stroke_f64: *const f64,
    color2_f64: *const f64,
    size_f64: *const f64,
    style_f64: *const f64,
    color_u8: *const u8,
    stroke_u8: *const u8,
    color2_u8: *const u8,
    size_u8: *const u8,
    style_u8: *const u8,
    transition_lo: *const u32,
    transition_hi: *const u32,
    bin_x: *const f64,
    grid_values: *const f64,
    summary: *mut XygPayloadTraceEmitOut,
    geom_out: *mut XygPayloadTraceGeomOut,
    geom_cap: usize,
    chan_out: *mut XygPayloadTraceChannelOut,
    chan_cap: usize,
    out_bytes: *mut u8,
    out_bytes_cap: usize,
    out_bytes_len: *mut usize,
) -> i32 {
    if emit_in.is_null() || columns.is_null() || column_values.is_null() || color_ch.is_null() || stroke_ch.is_null() || color2_ch.is_null() || size_ch.is_null() || style_channels.is_null() || summary.is_null() || out_bytes_len.is_null() { return -1; }
    let header = &*emit_in;
    let kind_text = match trace_read_utf8(kind, header.kind_len) { Some(v) => v, None => return -1 };
    let x_scale = match trace_read_utf8(x_axis_scale, header.x_axis_scale_len) { Some(v) => v, None => return -1 };
    let y_scale = match trace_read_utf8(y_axis_scale, header.y_axis_scale_len) { Some(v) => v, None => return -1 };
    let orient = match trace_read_utf8(orientation, header.orientation_len) { Some(v) => v, None => return -1 };
    let col_descs = std::slice::from_raw_parts(columns, 7);
    let col_ptrs = std::slice::from_raw_parts(column_values, 7);
    let kind_ptrs = if column_kinds.is_null() { [std::ptr::null(); 7] } else { let p = std::slice::from_raw_parts(column_kinds, 7); [p[0], p[1], p[2], p[3], p[4], p[5], p[6]] };
    let mut cols = std::array::from_fn(|_| PayloadTraceColumnIn::default());
    for (idx, desc) in col_descs.iter().enumerate() {
        cols[idx] = match trace_column_from_c(desc, col_ptrs[idx], kind_ptrs[idx]) { Ok(v) => v, Err(code) => return code };
    }
    let color = match trace_channel_from_c(&*color_ch, color_f64, color_u8) { Ok(v) => v, Err(code) => return code };
    let stroke = match trace_channel_from_c(&*stroke_ch, stroke_f64, stroke_u8) { Ok(v) => v, Err(code) => return code };
    let color2 = match trace_channel_from_c(&*color2_ch, color2_f64, color2_u8) { Ok(v) => v, Err(code) => return code };
    let size = match trace_channel_from_c(&*size_ch, size_f64, size_u8) { Ok(v) => v, Err(code) => return code };
    let style = match trace_channel_from_c(&*style_channels, style_f64, style_u8) { Ok(v) => v, Err(code) => return code };
    let transition_lo_slice = match trace_optional_u32(transition_lo, header.transition_keys_len) { Some(v) => v, None => return -1 };
    let transition_hi_slice = match trace_optional_u32(transition_hi, header.transition_keys_len) { Some(v) => v, None => return -1 };
    let bin_x_slice = match trace_optional_f64(bin_x, header.bin_x_len) { Some(v) => v, None => return -1 };
    let grid_slice = match trace_optional_f64(grid_values, header.grid_values_len) { Some(v) => v, None => return -1 };
    let inp = PayloadTraceEmitMaterializeIn {
        kind: kind_text, n_points: header.n_points, segment_count: header.segment_count, polar: header.polar, force_density: header.force_density, per_item: header.per_item,
        x_axis_type: header.x_axis_type, y_axis_type: header.y_axis_type, x_axis_scale: x_scale, y_axis_scale: y_scale, xr0: header.xr0, xr1: header.xr1, px_width: header.px_width,
        style_color_is_none: header.style_color_is_none, has_trace_animation: header.has_trace_animation, has_transition_keys: header.has_transition_keys,
        has_tooltip_rows: header.has_tooltip_rows, n_tooltip_rows: header.n_tooltip_rows, orientation: orient, has_color2_ch: header.has_color2_ch, has_color_ch: header.has_color_ch,
        has_stroke_ch: header.has_stroke_ch, has_style_channels: header.has_style_channels, color_ch: color, stroke_ch: stroke, color2_ch: color2, size_ch: size, style_channels: style,
        transition_keys_lo: if header.transition_keys_len == 0 { None } else { Some(transition_lo_slice) },
        transition_keys_hi: if header.transition_keys_len == 0 { None } else { Some(transition_hi_slice) },
        columns: cols,
        bin_x: if header.bin_x_len == 0 { None } else { Some(bin_x_slice) }, bin_x0: header.bin_x0, bin_x1: header.bin_x1,
        heatmap_rows: header.heatmap_rows, heatmap_cols: header.heatmap_cols, has_rgba_grid: header.has_rgba_grid, borrow_heatmaps: header.borrow_heatmaps,
        style_colormap_is_none: header.style_colormap_is_none, grid_values: if header.grid_values_len == 0 { None } else { Some(grid_slice) },
        grid_domain_lo: header.grid_domain_lo, grid_domain_hi: header.grid_domain_hi, max_rows: header.max_rows,
    };
    let materialized = match payload_trace_emit_materialize(&inp) { Ok(v) => v, Err(code) => return code };
    match write_materialized(&materialized, summary, geom_out, geom_cap, chan_out, chan_cap, out_bytes, out_bytes_cap, out_bytes_len) {
        Ok(()) => 0,
        Err(code) => code,
    }
}
