// XYTA trace observation materialize C ABI (ABI 323).

use xyg_engine::scene_xyta_trace_observations_materialize::{
    scene_xyta_trace_observations_materialize, SceneXytaColorChannelIn,
    SceneXytaColormapInput, SceneXytaStyleChannelIn, SceneXytaTraceObservationsIn,
    SceneXytaTraceObservationsOut, SCENE_XYTA_TRACE_OBSERVATIONS_MAX_BYTES,
};
use xyg_engine::scene_pack_orchestrate::XytaTraceDispatchPlan;

unsafe fn xyta_optional_i64<'a>(ptr: *const i64, len: usize) -> Option<&'a [i64]> {
    if len == 0 {
        Some(&[])
    } else if ptr.is_null() {
        None
    } else {
        Some(std::slice::from_raw_parts(ptr, len))
    }
}

/// Color/style channel descriptor for XYTA observation materialize.
#[repr(C)]
pub struct XygSceneXytaColorChannelDesc {
    pub present: i32,
    pub mode_len: usize,
    pub constant_len: usize,
    pub colormap_len: usize,
    pub has_domain: i32,
    pub domain_lo: f64,
    pub domain_hi: f64,
    pub values_f64_len: usize,
    pub rgba_u8_len: usize,
    pub codes_u8_len: usize,
    pub codes_i64_len: usize,
    pub palette_count: usize,
    pub n_categories: usize,
}

/// Style-side channel descriptor (opacity / stroke_width).
#[repr(C)]
pub struct XygSceneXytaStyleChannelDesc {
    pub present: i32,
    pub values_f64_len: usize,
}

/// Scalar/style header for XYTA observation materialize.
#[repr(C)]
pub struct XygSceneXytaTraceObservationsIn {
    pub trace_id: u32,
    pub pack_heatmap: i32,
    pub pack_hexbin_colormap: i32,
    pub pack_hexbin_rgba: i32,
    pub pack_ribbon_ends: i32,
    pub pack_mesh_faces: i32,
    pub pack_scatter_paint: i32,
    pub pack_density: i32,
    pub domain_x0: f64,
    pub domain_x1: f64,
    pub domain_y0: f64,
    pub domain_y1: f64,
    pub point_count: usize,
    pub fallback_color_len: usize,
    pub style_color_len: usize,
    pub style_stroke_len: usize,
    pub style_stroke_width: f64,
    pub has_style_stroke_width: i32,
    pub style_opacity: f32,
    pub has_style_opacity: i32,
    pub style_fill_opacity: f32,
    pub has_style_fill_opacity: i32,
    pub style_truecolor: i32,
    pub style_domain_lo: f64,
    pub style_domain_hi: f64,
    pub has_style_domain: i32,
    pub style_colormap_mode: i32,
    pub style_colormap_named_len: usize,
    pub style_colormap_stops_len: usize,
    pub grid_shape_rows: f64,
    pub grid_shape_cols: f64,
    pub has_grid_shape: i32,
    pub grid_values_len: usize,
    pub rgba_u8_len: usize,
    pub rgba_grid_f64_len: usize,
    pub x_values_len: usize,
    pub y_values_len: usize,
}

/// Materialized XYTA pack inputs returned by ABI 323.
#[repr(C)]
pub struct XygSceneXytaTraceObservationsOut {
    pub trace_id: u32,
    pub pack_heatmap: i32,
    pub pack_hexbin_colormap: i32,
    pub pack_hexbin_rgba: i32,
    pub pack_ribbon_ends: i32,
    pub pack_mesh_faces: i32,
    pub pack_scatter_paint: i32,
    pub pack_density: i32,
    pub grid_shape_rows: f64,
    pub grid_shape_cols: f64,
    pub has_grid_shape: i32,
    pub has_grid: i32,
    pub has_rgba: i32,
    pub has_rgba_grid: i32,
    pub truecolor: i32,
    pub has_cmap_domain: i32,
    pub cmap_lo: f64,
    pub cmap_hi: f64,
    pub has_color_ch: i32,
    pub has_style_color: i32,
    pub has_opacity: i32,
    pub has_fill_opacity: i32,
    pub opacity: f32,
    pub fill_opacity: f32,
    pub domain_x0: f64,
    pub domain_x1: f64,
    pub domain_y0: f64,
    pub domain_y1: f64,
    pub cmap_flags: u32,
    pub rows: i32,
    pub cols: i32,
    pub grid_len: usize,
    pub rgba_len: usize,
    pub rgba_grid_len: usize,
    pub x_len: usize,
    pub y_len: usize,
    pub mean_rgba_len: usize,
    pub idx_len: usize,
    pub lut_len: usize,
    pub cmap_len: usize,
    pub stops_len: usize,
    pub color_ch_len: usize,
    pub style_color_len: usize,
    pub grid_off: usize,
    pub rgba_off: usize,
    pub rgba_grid_off: usize,
    pub x_off: usize,
    pub y_off: usize,
    pub mean_rgba_off: usize,
    pub idx_off: usize,
    pub lut_off: usize,
    pub cmap_off: usize,
    pub stops_off: usize,
    pub color_ch_off: usize,
    pub style_color_off: usize,
}

unsafe fn xyta_read_palette<'a>(
    ptr: *const *const u8,
    lens: *const usize,
    count: usize,
) -> Option<Vec<&'a str>> {
    if count == 0 {
        return Some(Vec::new());
    }
    if ptr.is_null() || lens.is_null() {
        return None;
    }
    let ptrs = std::slice::from_raw_parts(ptr, count);
    let lengths = std::slice::from_raw_parts(lens, count);
    let mut out = Vec::with_capacity(count);
    for (&p, &len) in ptrs.iter().zip(lengths.iter()) {
        out.push(read_utf8(p, len)?);
    }
    Some(out)
}

unsafe fn xyta_color_channel_from_c<'a>(
    desc: &XygSceneXytaColorChannelDesc,
    mode: *const u8,
    constant: *const u8,
    colormap: *const u8,
    values_f64: *const f64,
    rgba_u8: *const u8,
    codes_u8: *const u8,
    codes_i64: *const i64,
    palette: &'a [&'a str],
) -> Result<SceneXytaColorChannelIn<'a>, i32> {
    Ok(SceneXytaColorChannelIn {
        present: desc.present,
        mode: read_utf8(mode, desc.mode_len).ok_or(-1)?,
        constant: if desc.constant_len == 0 {
            None
        } else {
            Some(read_utf8(constant, desc.constant_len).ok_or(-1)?)
        },
        colormap: if desc.colormap_len == 0 {
            None
        } else {
            Some(read_utf8(colormap, desc.colormap_len).ok_or(-1)?)
        },
        domain_lo: desc.domain_lo,
        domain_hi: desc.domain_hi,
        has_domain: desc.has_domain,
        values_f64: optional_f64(values_f64, desc.values_f64_len).ok_or(-1)?,
        rgba_u8: optional_bytes(rgba_u8, desc.rgba_u8_len).ok_or(-1)?,
        codes_u8: optional_bytes(codes_u8, desc.codes_u8_len).ok_or(-1)?,
        codes_i64: xyta_optional_i64(codes_i64, desc.codes_i64_len).ok_or(-1)?,
        palette,
        n_categories: desc.n_categories,
    })
}

fn write_xyta_observations_out(
    materialized: &SceneXytaTraceObservationsOut,
    summary: &mut XygSceneXytaTraceObservationsOut,
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
    summary.trace_id = materialized.trace_id;
    summary.pack_heatmap = materialized.pack_heatmap;
    summary.pack_hexbin_colormap = materialized.pack_hexbin_colormap;
    summary.pack_hexbin_rgba = materialized.pack_hexbin_rgba;
    summary.pack_ribbon_ends = materialized.pack_ribbon_ends;
    summary.pack_mesh_faces = materialized.pack_mesh_faces;
    summary.pack_scatter_paint = materialized.pack_scatter_paint;
    summary.pack_density = materialized.pack_density;
    summary.grid_shape_rows = materialized.grid_shape_rows;
    summary.grid_shape_cols = materialized.grid_shape_cols;
    summary.has_grid_shape = materialized.has_grid_shape;
    summary.has_grid = materialized.has_grid;
    summary.has_rgba = materialized.has_rgba;
    summary.has_rgba_grid = materialized.has_rgba_grid;
    summary.truecolor = materialized.truecolor;
    summary.has_cmap_domain = materialized.has_cmap_domain;
    summary.cmap_lo = materialized.cmap_lo;
    summary.cmap_hi = materialized.cmap_hi;
    summary.has_color_ch = materialized.has_color_ch;
    summary.has_style_color = materialized.has_style_color;
    summary.has_opacity = materialized.has_opacity;
    summary.has_fill_opacity = materialized.has_fill_opacity;
    summary.opacity = materialized.opacity;
    summary.fill_opacity = materialized.fill_opacity;
    summary.domain_x0 = materialized.domain_x0;
    summary.domain_x1 = materialized.domain_x1;
    summary.domain_y0 = materialized.domain_y0;
    summary.domain_y1 = materialized.domain_y1;
    summary.cmap_flags = materialized.cmap_flags;
    summary.rows = materialized.rows;
    summary.cols = materialized.cols;
    summary.grid_off = append(&mut blob, &materialized.grid);
    summary.grid_len = materialized.grid.len();
    summary.rgba_off = append(&mut blob, &materialized.rgba);
    summary.rgba_len = materialized.rgba.len();
    summary.rgba_grid_off = append(&mut blob, &materialized.rgba_grid);
    summary.rgba_grid_len = materialized.rgba_grid.len();
    summary.x_off = append(&mut blob, &materialized.x);
    summary.x_len = materialized.x.len();
    summary.y_off = append(&mut blob, &materialized.y);
    summary.y_len = materialized.y.len();
    summary.mean_rgba_off = append(&mut blob, &materialized.mean_rgba);
    summary.mean_rgba_len = materialized.mean_rgba.len();
    summary.idx_off = append(&mut blob, &materialized.idx);
    summary.idx_len = materialized.idx.len();
    summary.lut_off = append(&mut blob, &materialized.lut);
    summary.lut_len = materialized.lut.len();
    summary.cmap_off = append(&mut blob, &materialized.cmap);
    summary.cmap_len = materialized.cmap.len();
    summary.stops_off = append(&mut blob, &materialized.stops);
    summary.stops_len = materialized.stops.len();
    summary.color_ch_off = append(&mut blob, &materialized.color_ch);
    summary.color_ch_len = materialized.color_ch.len();
    summary.style_color_off = append(&mut blob, &materialized.style_color);
    summary.style_color_len = materialized.style_color.len();
    if blob.len() > out_cap.min(SCENE_XYTA_TRACE_OBSERVATIONS_MAX_BYTES) {
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

#[allow(clippy::too_many_arguments)]
#[no_mangle]
pub unsafe extern "C" fn xyg_scene_xyta_trace_observations_materialize(
    input: *const XygSceneXytaTraceObservationsIn,
    fallback_color: *const u8,
    style_color: *const u8,
    style_stroke: *const u8,
    style_colormap_named: *const u8,
    style_colormap_stops: *const u8,
    grid_values: *const f64,
    rgba_u8: *const u8,
    rgba_grid_f64: *const f64,
    x_values: *const f64,
    y_values: *const f64,
    color_ch: *const XygSceneXytaColorChannelDesc,
    color_mode: *const u8,
    color_constant: *const u8,
    color_colormap: *const u8,
    color_values_f64: *const f64,
    color_rgba_u8: *const u8,
    color_codes_u8: *const u8,
    color_codes_i64: *const i64,
    color_palette_ptrs: *const *const u8,
    color_palette_lens: *const usize,
    stroke_ch: *const XygSceneXytaColorChannelDesc,
    stroke_mode: *const u8,
    stroke_constant: *const u8,
    stroke_colormap: *const u8,
    stroke_values_f64: *const f64,
    stroke_rgba_u8: *const u8,
    stroke_codes_u8: *const u8,
    stroke_codes_i64: *const i64,
    stroke_palette_ptrs: *const *const u8,
    stroke_palette_lens: *const usize,
    color2_ch: *const XygSceneXytaColorChannelDesc,
    color2_mode: *const u8,
    color2_constant: *const u8,
    color2_colormap: *const u8,
    color2_values_f64: *const f64,
    color2_rgba_u8: *const u8,
    color2_codes_u8: *const u8,
    color2_codes_i64: *const i64,
    color2_palette_ptrs: *const *const u8,
    color2_palette_lens: *const usize,
    opacity_ch: *const XygSceneXytaStyleChannelDesc,
    opacity_values: *const f64,
    artist_ch: *const XygSceneXytaStyleChannelDesc,
    artist_values: *const f64,
    stroke_width_ch: *const XygSceneXytaStyleChannelDesc,
    stroke_width_values: *const f64,
    summary: *mut XygSceneXytaTraceObservationsOut,
    out_bytes: *mut u8,
    out_cap: usize,
    out_len: *mut usize,
) -> i32 {
    if input.is_null()
        || color_ch.is_null()
        || stroke_ch.is_null()
        || color2_ch.is_null()
        || opacity_ch.is_null()
        || artist_ch.is_null()
        || stroke_width_ch.is_null()
        || summary.is_null()
        || out_len.is_null()
    {
        return -1;
    }
    let header = &*input;
    let fallback = match read_utf8(fallback_color, header.fallback_color_len) {
        Some(v) => v,
        None => return -1,
    };
    let style_color_text = read_utf8(style_color, header.style_color_len);
    let style_stroke_text = read_utf8(style_stroke, header.style_stroke_len);
    let mut style_colormap_stops_flat = Vec::new();
    let style_colormap = match header.style_colormap_mode {
        1 => match read_utf8(style_colormap_named, header.style_colormap_named_len) {
            Some(name) => SceneXytaColormapInput::Named(name),
            None => return -1,
        },
        2 => {
            let stops_bytes = match optional_bytes(style_colormap_stops, header.style_colormap_stops_len) {
                Some(v) => v,
                None => return -1,
            };
            if stops_bytes.len() % 3 != 0 || stops_bytes.is_empty() {
                return -1;
            }
            style_colormap_stops_flat = stops_bytes.to_vec();
            SceneXytaColormapInput::Stops(&style_colormap_stops_flat)
        }
        _ => SceneXytaColormapInput::None,
    };
    let color_palette = match xyta_read_palette(
        color_palette_ptrs,
        color_palette_lens,
        (*color_ch).palette_count,
    ) {
        Some(v) => v,
        None => return -1,
    };
    let stroke_palette = match xyta_read_palette(
        stroke_palette_ptrs,
        stroke_palette_lens,
        (*stroke_ch).palette_count,
    ) {
        Some(v) => v,
        None => return -1,
    };
    let color2_palette = match xyta_read_palette(
        color2_palette_ptrs,
        color2_palette_lens,
        (*color2_ch).palette_count,
    ) {
        Some(v) => v,
        None => return -1,
    };
    let color_palette_refs: Vec<&str> = color_palette.iter().copied().collect();
    let stroke_palette_refs: Vec<&str> = stroke_palette.iter().copied().collect();
    let color2_palette_refs: Vec<&str> = color2_palette.iter().copied().collect();
    let color_channel = match xyta_color_channel_from_c(
        &*color_ch,
        color_mode,
        color_constant,
        color_colormap,
        color_values_f64,
        color_rgba_u8,
        color_codes_u8,
        color_codes_i64,
        &color_palette_refs,
    ) {
        Ok(v) => v,
        Err(code) => return code,
    };
    let stroke_channel = match xyta_color_channel_from_c(
        &*stroke_ch,
        stroke_mode,
        stroke_constant,
        stroke_colormap,
        stroke_values_f64,
        stroke_rgba_u8,
        stroke_codes_u8,
        stroke_codes_i64,
        &stroke_palette_refs,
    ) {
        Ok(v) => v,
        Err(code) => return code,
    };
    let color2_channel = match xyta_color_channel_from_c(
        &*color2_ch,
        color2_mode,
        color2_constant,
        color2_colormap,
        color2_values_f64,
        color2_rgba_u8,
        color2_codes_u8,
        color2_codes_i64,
        &color2_palette_refs,
    ) {
        Ok(v) => v,
        Err(code) => return code,
    };
    let opacity_channel = SceneXytaStyleChannelIn {
        present: (*opacity_ch).present,
        values_f64: match optional_f64(opacity_values, (*opacity_ch).values_f64_len) {
            Some(v) => v,
            None => return -1,
        },
    };
    let artist_channel = SceneXytaStyleChannelIn {
        present: (*artist_ch).present,
        values_f64: match optional_f64(artist_values, (*artist_ch).values_f64_len) {
            Some(v) => v,
            None => return -1,
        },
    };
    let stroke_width_channel = SceneXytaStyleChannelIn {
        present: (*stroke_width_ch).present,
        values_f64: match optional_f64(stroke_width_values, (*stroke_width_ch).values_f64_len) {
            Some(v) => v,
            None => return -1,
        },
    };
    let grid_values_slice = match optional_f64(grid_values, header.grid_values_len) {
        Some(v) => v,
        None => return -1,
    };
    let rgba_u8_slice = match optional_bytes(rgba_u8, header.rgba_u8_len) {
        Some(v) => v,
        None => return -1,
    };
    let rgba_grid_slice = match optional_f64(rgba_grid_f64, header.rgba_grid_f64_len) {
        Some(v) => v,
        None => return -1,
    };
    let x_values_slice = match optional_f64(x_values, header.x_values_len) {
        Some(v) => v,
        None => return -1,
    };
    let y_values_slice = match optional_f64(y_values, header.y_values_len) {
        Some(v) => v,
        None => return -1,
    };
    let materialize_in = SceneXytaTraceObservationsIn {
        trace_id: header.trace_id,
        dispatch: XytaTraceDispatchPlan {
            kind_class: 0,
            pack_heatmap: header.pack_heatmap,
            pack_hexbin_colormap: header.pack_hexbin_colormap,
            pack_hexbin_rgba: header.pack_hexbin_rgba,
            pack_ribbon_ends: header.pack_ribbon_ends,
            pack_mesh_faces: header.pack_mesh_faces,
            pack_scatter_paint: header.pack_scatter_paint,
            pack_density: header.pack_density,
        },
        domain_x0: header.domain_x0,
        domain_x1: header.domain_x1,
        domain_y0: header.domain_y0,
        domain_y1: header.domain_y1,
        point_count: header.point_count,
        fallback_color: fallback,
        style_color: style_color_text,
        style_stroke: style_stroke_text,
        style_stroke_width: header.style_stroke_width,
        has_style_stroke_width: header.has_style_stroke_width,
        style_opacity: header.style_opacity,
        has_style_opacity: header.has_style_opacity,
        style_fill_opacity: header.style_fill_opacity,
        has_style_fill_opacity: header.has_style_fill_opacity,
        style_truecolor: header.style_truecolor,
        style_domain_lo: header.style_domain_lo,
        style_domain_hi: header.style_domain_hi,
        has_style_domain: header.has_style_domain,
        style_colormap,
        grid_shape_rows: header.grid_shape_rows,
        grid_shape_cols: header.grid_shape_cols,
        has_grid_shape: header.has_grid_shape,
        grid_values: grid_values_slice,
        rgba_u8: rgba_u8_slice,
        rgba_grid_f64: rgba_grid_slice,
        x_values: x_values_slice,
        y_values: y_values_slice,
        color_ch: color_channel,
        stroke_ch: stroke_channel,
        color2_ch: color2_channel,
        opacity_ch: opacity_channel,
        artist_alpha_ch: artist_channel,
        stroke_width_ch: stroke_width_channel,
    };
    let materialized = match scene_xyta_trace_observations_materialize(&materialize_in) {
        Ok(v) => v,
        Err(code) => return code,
    };
    match write_xyta_observations_out(&materialized, &mut *summary, out_bytes, out_cap, out_len) {
        Ok(()) => 0,
        Err(code) => code,
    }
}
