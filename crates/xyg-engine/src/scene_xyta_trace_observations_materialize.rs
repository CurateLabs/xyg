//! XYTA trace observation materialize (M2 Push 2 completion, ABI 323).
//!
//! Hosts marshal trace kind, dispatch flags, and raw column/channel handles.
//! Rust owns hexbin/heatmap/ribbon/mesh/scatter/density plane packing previously
//! in Python `_marshal_xyta_trace_record` and Node `marshalXyTaTraceRecord`.

use crate::colormap::colormap_named_stops;
use crate::css;
use crate::density_emit::density_mean_color_wire_admit;
use crate::kernels::{
    clip_quantize_u8, scene_heatmap_shape_admit, scene_item_apply_opacity, scene_item_fill_t,
    scene_item_widths_admit, scene_xyta_colormap_pack,
};
use crate::scene_pack_orchestrate::XytaTraceDispatchPlan;

pub const SCENE_XYTA_TRACE_OBSERVATIONS_MAX_BYTES: usize = 1 << 22;

const DEFAULT_COLOR: &str = "#3987e5";
const DEFAULT_PALETTE: [&str; 8] = [
    "#3987e5", "#008300", "#d55181", "#c48300", "#199e70", "#d95926", "#9085e9", "#e66767",
];

/// Authored colormap: named string or explicit RGB stop bytes (len % 3 == 0).
#[derive(Clone, Debug)]
pub enum SceneXytaColormapInput<'a> {
    None,
    Named(&'a str),
    Stops(&'a [u8]),
}

/// Color channel observations for XYTA materialize.
#[derive(Clone, Debug, Default)]
pub struct SceneXytaColorChannelIn<'a> {
    pub present: i32,
    pub mode: &'a str,
    pub constant: Option<&'a str>,
    pub colormap: Option<&'a str>,
    pub domain_lo: f64,
    pub domain_hi: f64,
    pub has_domain: i32,
    pub values_f64: &'a [f64],
    pub rgba_u8: &'a [u8],
    pub codes_u8: &'a [u8],
    pub codes_i64: &'a [i64],
    pub palette: &'a [&'a str],
    pub n_categories: usize,
}

/// Style-side channel (opacity, artist_alpha, stroke_width).
#[derive(Clone, Debug, Default)]
pub struct SceneXytaStyleChannelIn<'a> {
    pub present: i32,
    pub values_f64: &'a [f64],
}

/// Host-marshaled trace observations for XYTA attach materialize.
#[derive(Clone, Debug)]
pub struct SceneXytaTraceObservationsIn<'a> {
    pub trace_id: u32,
    pub dispatch: XytaTraceDispatchPlan,
    pub domain_x0: f64,
    pub domain_x1: f64,
    pub domain_y0: f64,
    pub domain_y1: f64,
    pub point_count: usize,
    pub fallback_color: &'a str,
    pub style_color: Option<&'a str>,
    pub style_stroke: Option<&'a str>,
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
    pub style_colormap: SceneXytaColormapInput<'a>,
    pub grid_shape_rows: f64,
    pub grid_shape_cols: f64,
    pub has_grid_shape: i32,
    pub grid_values: &'a [f64],
    pub rgba_u8: &'a [u8],
    pub rgba_grid_f64: &'a [f64],
    pub x_values: &'a [f64],
    pub y_values: &'a [f64],
    pub color_ch: SceneXytaColorChannelIn<'a>,
    pub stroke_ch: SceneXytaColorChannelIn<'a>,
    pub color2_ch: SceneXytaColorChannelIn<'a>,
    pub opacity_ch: SceneXytaStyleChannelIn<'a>,
    pub artist_alpha_ch: SceneXytaStyleChannelIn<'a>,
    pub stroke_width_ch: SceneXytaStyleChannelIn<'a>,
}

/// Materialized blobs + scalars for [`scene_xyta_trace_pack`].
#[derive(Clone, Debug, Default)]
pub struct SceneXytaTraceObservationsOut {
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
    pub grid: Vec<u8>,
    pub rgba: Vec<u8>,
    pub rgba_grid: Vec<u8>,
    pub x: Vec<u8>,
    pub y: Vec<u8>,
    pub mean_rgba: Vec<u8>,
    pub idx: Vec<u8>,
    pub lut: Vec<u8>,
    pub cmap: Vec<u8>,
    pub stops: Vec<u8>,
    pub color_ch: Vec<u8>,
    pub style_color: Vec<u8>,
}

fn f64_bytes(values: &[f64]) -> Vec<u8> {
    values
        .iter()
        .flat_map(|v| v.to_le_bytes())
        .collect::<Vec<u8>>()
}

fn pack_colormap(style: &SceneXytaColormapInput<'_>) -> (u32, Vec<u8>, Vec<u8>) {
    match style {
        SceneXytaColormapInput::Named(name) => {
            let (flags, cmap, stops) = scene_xyta_colormap_pack(1, name.as_bytes(), &[]);
            (flags, cmap, stops)
        }
        SceneXytaColormapInput::Stops(flat) => {
            let (flags, cmap, stops) = scene_xyta_colormap_pack(2, &[], flat);
            (flags, cmap, stops)
        }
        SceneXytaColormapInput::None => {
            let (flags, cmap, stops) = scene_xyta_colormap_pack(0, &[], &[]);
            (flags, cmap, stops)
        }
    }
}

fn palette_rows_rgba8(palette: &[&str], rows: usize) -> Vec<u8> {
    let n = rows.max(1);
    let mut out = vec![0u8; n * 4];
    for i in 0..n {
        let entry = palette.get(i % palette.len()).copied().unwrap_or(DEFAULT_COLOR);
        let rgba = css::color_rgba8(entry, 1.0);
        out[i * 4..i * 4 + 4].copy_from_slice(&rgba);
    }
    out
}

fn quantize_unit_u8(values: &[f64], lo: f64, hi: f64) -> Option<Vec<u8>> {
    if values.is_empty() {
        return Some(Vec::new());
    }
    let mut scratch = vec![0.0f32; values.len()];
    crate::kernels::normalize_f32_into(values, lo, hi, 0.0, &mut scratch);
    let unit: Vec<f64> = scratch.iter().map(|v| f64::from(*v)).collect();
    let mut out = vec![0u8; values.len()];
    if clip_quantize_u8(&unit, &mut out) == 0 {
        return None;
    }
    Some(out)
}

fn colormap_lut_rgba8(name: &str) -> Vec<u8> {
    let stops = colormap_named_stops(name);
    let mut t = vec![0.0f64; 256];
    for (i, slot) in t.iter_mut().enumerate() {
        *slot = i as f64 / 255.0;
    }
    let mut out = vec![0u8; 256 * 4];
    crate::kernels::colormap_rgba_into(&t, 256, 1, &stops, 255, &mut out);
    out
}

fn channel_end_rgba8(channel: &SceneXytaColorChannelIn<'_>, n: usize, fallback: &str) -> Option<Vec<u8>> {
    if n < 1 {
        return None;
    }
    let replicate = |css: &str| -> Option<Vec<u8>> {
        let rgba = css::color_rgba8(css, 1.0);
        Some(rgba.repeat(n))
    };
    if channel.present == 0 {
        return replicate(fallback);
    }
    match channel.mode {
        "constant" => {
            let css = channel.constant?;
            replicate(css)
        }
        "direct_rgba" => {
            let packed = channel.rgba_u8;
            if packed.len() == n * 4 {
                return Some(packed.to_vec());
            }
            if !channel.values_f64.is_empty() && channel.values_f64.len() == n * 4 {
                let mut out = vec![0u8; n * 4];
                if clip_quantize_u8(channel.values_f64, &mut out) == 0 {
                    return None;
                }
                return Some(out);
            }
            None
        }
        "categorical" => {
            let palette: Vec<&str> = if channel.palette.is_empty() {
                DEFAULT_PALETTE.to_vec()
            } else {
                channel.palette.to_vec()
            };
            let mod_len = palette.len().max(1);
            let mut rgba = Vec::with_capacity(n * 4);
            if !channel.codes_u8.is_empty() {
                for i in 0..n {
                    let code = channel.codes_u8.get(i).copied().unwrap_or(0) as usize;
                    let css = palette[code % mod_len];
                    rgba.extend_from_slice(&css::color_rgba8(css, 1.0));
                }
            } else if !channel.codes_i64.is_empty() {
                for i in 0..n {
                    let code = channel.codes_i64.get(i).copied().unwrap_or(0);
                    let idx = ((code % mod_len as i64) + mod_len as i64) as usize % mod_len;
                    let css = palette[idx];
                    rgba.extend_from_slice(&css::color_rgba8(css, 1.0));
                }
            } else {
                return None;
            }
            Some(rgba)
        }
        _ => None,
    }
}

fn item_apply_opacity(
    packed: &[u8],
    n: usize,
    opacity_ch: &SceneXytaStyleChannelIn<'_>,
    artist_ch: &SceneXytaStyleChannelIn<'_>,
) -> Option<Vec<u8>> {
    let mut out = vec![0u8; packed.len()];
    let artist = if artist_ch.present != 0 {
        Some(artist_ch.values_f64)
    } else {
        None
    };
    let opacity = if opacity_ch.present != 0 {
        Some(opacity_ch.values_f64)
    } else {
        None
    };
    if scene_item_apply_opacity(packed, n, artist, opacity, &mut out) {
        Some(out)
    } else {
        None
    }
}

fn item_fill_rgba8(
    channel: &SceneXytaColorChannelIn<'_>,
    n: usize,
    fallback: &str,
    opacity_ch: &SceneXytaStyleChannelIn<'_>,
    artist_ch: &SceneXytaStyleChannelIn<'_>,
) -> Option<Vec<u8>> {
    let mut packed = channel_end_rgba8(channel, n, fallback)?;
    if channel.present != 0
        && channel.mode == "continuous"
        && !channel.values_f64.is_empty()
    {
        let domain = if channel.has_domain != 0 {
            Some((channel.domain_lo, channel.domain_hi))
        } else {
            None
        };
        let mut t = vec![0.0f64; n];
        if !scene_item_fill_t(channel.values_f64, n, domain, &mut t) {
            return None;
        }
        let name = channel.colormap.unwrap_or("viridis");
        let stops = colormap_named_stops(name);
        let mut rgba = vec![0u8; n * 4];
        if !crate::kernels::colormap_rgba_into(&t, n, 1, &stops, 255, &mut rgba) {
            return None;
        }
        packed = rgba;
    }
    item_apply_opacity(&packed, n, opacity_ch, artist_ch)
}

fn item_stroke_rgba8(
    stroke: &SceneXytaColorChannelIn<'_>,
    fills: &[u8],
    n: usize,
    fallback: &str,
) -> Option<Vec<u8>> {
    if stroke.present != 0 && stroke.mode == "match_fill" {
        return Some(fills.to_vec());
    }
    if let Some(packed) = channel_end_rgba8(stroke, n, fallback) {
        return Some(packed);
    }
    if stroke.present == 0 {
        return channel_end_rgba8(
            &SceneXytaColorChannelIn {
                present: 0,
                mode: "",
                ..Default::default()
            },
            n,
            fallback,
        );
    }
    None
}

fn item_widths(
    stroke_width_ch: &SceneXytaStyleChannelIn<'_>,
    n: usize,
    scalar: f64,
    has_scalar: i32,
) -> Option<Vec<u8>> {
    let values = if stroke_width_ch.present != 0 {
        Some(stroke_width_ch.values_f64)
    } else {
        None
    };
    let admit = if let Some(values) = values {
        scene_item_widths_admit(Some(values), n, 0.0)
    } else if has_scalar != 0 {
        scene_item_widths_admit(None, n, scalar)
    } else {
        scene_item_widths_admit(None, n, 0.0)
    };
    if admit == 0 {
        return None;
    }
    if let Some(values) = values {
        Some(f64_bytes(values))
    } else {
        Some(f64_bytes(&vec![scalar; n]))
    }
}

fn resolve_bin_colors(
    channel: &SceneXytaColorChannelIn<'_>,
) -> Option<(Option<Vec<u8>>, Option<Vec<u8>>, Option<Vec<u8>>)> {
    if channel.present == 0 {
        return None;
    }
    if density_mean_color_wire_admit(1, channel.mode) == 0 {
        return None;
    }
    match channel.mode {
        "direct_rgba" => {
            let rgba = if !channel.rgba_u8.is_empty() {
                channel.rgba_u8.to_vec()
            } else if !channel.values_f64.is_empty() {
                let mut out = vec![0u8; channel.values_f64.len()];
                if clip_quantize_u8(channel.values_f64, &mut out) == 0 {
                    return None;
                }
                out
            } else {
                return None;
            };
            Some((Some(rgba), None, None))
        }
        "continuous" => {
            let idx = quantize_unit_u8(
                channel.values_f64,
                channel.domain_lo,
                channel.domain_hi,
            )?;
            let lut = colormap_lut_rgba8(channel.colormap.unwrap_or("viridis"));
            Some((None, Some(idx), Some(lut)))
        }
        "categorical" => {
            let palette: Vec<&str> = if channel.palette.is_empty() {
                DEFAULT_PALETTE.to_vec()
            } else {
                channel.palette.to_vec()
            };
            if !channel.codes_u8.is_empty() {
                let lut = palette_rows_rgba8(&palette, channel.n_categories.max(1));
                Some((None, Some(channel.codes_u8.to_vec()), Some(lut)))
            } else if !channel.codes_i64.is_empty() {
                let mod_len = palette.len().max(1);
                let idx: Vec<u8> = channel
                    .codes_i64
                    .iter()
                    .map(|code| code.rem_euclid(mod_len as i64) as u8)
                    .collect();
                let lut = palette_rows_rgba8(&palette, mod_len);
                Some((None, Some(idx), Some(lut)))
            } else {
                None
            }
        }
        _ => None,
    }
}

fn scatter_point_stroke_rgba8(
    stroke: &SceneXytaColorChannelIn<'_>,
    fills: &[u8],
    n: usize,
    fallback: &str,
    opacity_ch: &SceneXytaStyleChannelIn<'_>,
    artist_ch: &SceneXytaStyleChannelIn<'_>,
) -> Option<Vec<u8>> {
    let packed = item_stroke_rgba8(stroke, fills, n, fallback)?;
    if stroke.present != 0 && stroke.mode == "match_fill" {
        return Some(packed);
    }
    item_apply_opacity(&packed, n, opacity_ch, artist_ch)
}

pub fn scene_xyta_trace_observations_materialize(
    input: &SceneXytaTraceObservationsIn<'_>,
) -> Result<SceneXytaTraceObservationsOut, i32> {
    let mut out = SceneXytaTraceObservationsOut {
        trace_id: input.trace_id,
        pack_heatmap: input.dispatch.pack_heatmap,
        pack_hexbin_colormap: input.dispatch.pack_hexbin_colormap,
        pack_hexbin_rgba: input.dispatch.pack_hexbin_rgba,
        pack_ribbon_ends: input.dispatch.pack_ribbon_ends,
        pack_mesh_faces: input.dispatch.pack_mesh_faces,
        pack_scatter_paint: input.dispatch.pack_scatter_paint,
        pack_density: input.dispatch.pack_density,
        domain_x0: input.domain_x0,
        domain_x1: input.domain_x1,
        domain_y0: input.domain_y0,
        domain_y1: input.domain_y1,
        ..Default::default()
    };
    let fallback = if input.fallback_color.is_empty() {
        DEFAULT_COLOR
    } else {
        input.fallback_color
    };
    if input.dispatch.pack_heatmap != 0 {
        if input.has_grid_shape != 0 {
            out.has_grid_shape = 1;
            out.grid_shape_rows = input.grid_shape_rows;
            out.grid_shape_cols = input.grid_shape_cols;
            if scene_heatmap_shape_admit(input.grid_shape_rows, input.grid_shape_cols) != 0 {
                out.rows = input.grid_shape_rows as i32;
                out.cols = input.grid_shape_cols as i32;
            }
        }
        if !input.grid_values.is_empty() {
            out.has_grid = 1;
            out.grid = f64_bytes(input.grid_values);
        }
        if !input.rgba_u8.is_empty() {
            out.has_rgba = 1;
            out.rgba = input.rgba_u8.to_vec();
        }
        if !input.rgba_grid_f64.is_empty() {
            out.has_rgba_grid = 1;
            out.rgba_grid = f64_bytes(input.rgba_grid_f64);
        }
        let (cmap_flags, cmap, stops) = pack_colormap(&input.style_colormap);
        out.cmap_flags = cmap_flags;
        out.cmap = cmap;
        out.stops = stops;
        if input.style_truecolor != 0 {
            out.truecolor = 1;
        }
        if input.has_style_domain != 0 {
            out.has_cmap_domain = 1;
            out.cmap_lo = input.style_domain_lo;
            out.cmap_hi = input.style_domain_hi;
        }
    } else if input.dispatch.pack_hexbin_colormap != 0 {
        let values = input.color_ch.values_f64;
        out.rows = 1;
        out.cols = i32::try_from(values.len()).map_err(|_| -1)?;
        out.has_grid = 1;
        out.grid = f64_bytes(values);
        let cmap_input = if let Some(name) = input.color_ch.colormap {
            SceneXytaColormapInput::Named(name)
        } else {
            SceneXytaColormapInput::None
        };
        let (cmap_flags, cmap, stops) = pack_colormap(&cmap_input);
        out.cmap_flags = cmap_flags;
        out.cmap = cmap;
        out.stops = stops;
        if input.color_ch.has_domain != 0 {
            out.has_cmap_domain = 1;
            out.cmap_lo = input.color_ch.domain_lo;
            out.cmap_hi = input.color_ch.domain_hi;
        }
    } else if input.dispatch.pack_hexbin_rgba != 0 {
        if let Some(packed) = channel_end_rgba8(&input.color_ch, input.point_count, fallback) {
            let n = packed.len() / 4;
            out.rows = 1;
            out.cols = i32::try_from(n).map_err(|_| -1)?;
            out.has_grid = 1;
            out.has_rgba = 1;
            out.grid = f64_bytes(&vec![0.0; n]);
            out.rgba = packed;
        }
    } else if input.dispatch.pack_ribbon_ends != 0 {
        let n = input.point_count;
        if n >= 1 {
            let source = channel_end_rgba8(&input.color_ch, n, fallback);
            let target = channel_end_rgba8(&input.color2_ch, n, fallback);
            if let (Some(source), Some(target)) = (source, target) {
                out.rows = 1;
                out.cols = i32::try_from(source.len() / 4).map_err(|_| -1)?;
                out.has_rgba = 1;
                out.rgba = source;
                out.mean_rgba = target;
            }
        }
    } else if input.dispatch.pack_mesh_faces != 0 {
        let n = input.point_count;
        let fills = item_fill_rgba8(
            &input.color_ch,
            n,
            fallback,
            &input.opacity_ch,
            &input.artist_alpha_ch,
        );
        let strokes = fills.as_ref().and_then(|fills| {
            item_stroke_rgba8(
                &input.stroke_ch,
                fills,
                n,
                input.style_stroke.unwrap_or("transparent"),
            )
        });
        let widths = item_widths(
            &input.stroke_width_ch,
            n,
            input.style_stroke_width,
            input.has_style_stroke_width,
        );
        if let (Some(fills), Some(strokes), Some(widths)) = (fills, strokes, widths) {
            let count = fills.len() / 4;
            out.rows = 1;
            out.cols = i32::try_from(count).map_err(|_| -1)?;
            out.has_rgba = 1;
            out.rgba = fills;
            out.mean_rgba = strokes;
            out.x = widths;
        }
    } else if input.dispatch.pack_scatter_paint != 0 {
        let n = input.point_count;
        let fills = item_fill_rgba8(
            &input.color_ch,
            n,
            fallback,
            &input.opacity_ch,
            &input.artist_alpha_ch,
        );
        let strokes = fills.as_ref().and_then(|fills| {
            scatter_point_stroke_rgba8(
                &input.stroke_ch,
                fills,
                n,
                input.style_stroke.unwrap_or("transparent"),
                &input.opacity_ch,
                &input.artist_alpha_ch,
            )
        });
        let widths = item_widths(
            &input.stroke_width_ch,
            n,
            input.style_stroke_width,
            input.has_style_stroke_width,
        );
        if let (Some(fills), Some(strokes), Some(widths)) = (fills, strokes, widths) {
            let count = fills.len() / 4;
            out.rows = 1;
            out.cols = i32::try_from(count).map_err(|_| -1)?;
            out.has_rgba = 1;
            out.rgba = fills;
            out.mean_rgba = strokes;
            out.x = widths;
        }
    } else if input.dispatch.pack_density != 0 {
        if !input.x_values.is_empty() {
            out.x = f64_bytes(input.x_values);
        }
        if !input.y_values.is_empty() {
            out.y = f64_bytes(input.y_values);
        }
        let (cmap_flags, cmap, stops) = pack_colormap(&input.style_colormap);
        out.cmap_flags = cmap_flags;
        out.cmap = cmap;
        out.stops = stops;
        if input.color_ch.present != 0
            && input.color_ch.mode == "constant"
            && input.color_ch.constant.is_some()
        {
            out.has_color_ch = 1;
            out.color_ch = input.color_ch.constant.unwrap().as_bytes().to_vec();
        }
        if let Some(css) = input.style_color {
            out.has_style_color = 1;
            out.style_color = css.as_bytes().to_vec();
        }
        if input.has_style_opacity != 0 {
            out.has_opacity = 1;
            out.opacity = input.style_opacity;
        }
        if input.has_style_fill_opacity != 0 {
            out.has_fill_opacity = 1;
            out.fill_opacity = input.style_fill_opacity;
        }
        if let Some((rgba, idx, lut)) = resolve_bin_colors(&input.color_ch) {
            if let Some(rgba) = rgba {
                out.mean_rgba = rgba;
            }
            if let Some(idx) = idx {
                out.idx = idx;
            }
            if let Some(lut) = lut {
                out.lut = lut;
            }
        }
    }
    let total = out.grid.len()
        + out.rgba.len()
        + out.rgba_grid.len()
        + out.x.len()
        + out.y.len()
        + out.mean_rgba.len()
        + out.idx.len()
        + out.lut.len()
        + out.cmap.len()
        + out.stops.len()
        + out.color_ch.len()
        + out.style_color.len();
    if total > SCENE_XYTA_TRACE_OBSERVATIONS_MAX_BYTES {
        return Err(-1);
    }
    Ok(out)
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::scene_pack_orchestrate::XytaTraceDispatchPlan;

    fn empty_color_ch<'a>() -> SceneXytaColorChannelIn<'a> {
        SceneXytaColorChannelIn {
            present: 0,
            mode: "",
            ..Default::default()
        }
    }

    fn minimal_input<'a>(
        dispatch: XytaTraceDispatchPlan,
        color_ch: SceneXytaColorChannelIn<'a>,
        x_values: &'a [f64],
        y_values: &'a [f64],
    ) -> SceneXytaTraceObservationsIn<'a> {
        SceneXytaTraceObservationsIn {
            trace_id: 1,
            dispatch,
            domain_x0: 0.0,
            domain_x1: 1.0,
            domain_y0: 0.0,
            domain_y1: 1.0,
            point_count: x_values.len(),
            fallback_color: DEFAULT_COLOR,
            style_color: None,
            style_stroke: None,
            style_stroke_width: 0.0,
            has_style_stroke_width: 0,
            style_opacity: 1.0,
            has_style_opacity: 0,
            style_fill_opacity: 1.0,
            has_style_fill_opacity: 0,
            style_truecolor: 0,
            style_domain_lo: 0.0,
            style_domain_hi: 1.0,
            has_style_domain: 0,
            style_colormap: SceneXytaColormapInput::None,
            grid_shape_rows: 0.0,
            grid_shape_cols: 0.0,
            has_grid_shape: 0,
            grid_values: &[],
            rgba_u8: &[],
            rgba_grid_f64: &[],
            x_values,
            y_values,
            color_ch,
            stroke_ch: empty_color_ch(),
            color2_ch: empty_color_ch(),
            opacity_ch: SceneXytaStyleChannelIn::default(),
            artist_alpha_ch: SceneXytaStyleChannelIn::default(),
            stroke_width_ch: SceneXytaStyleChannelIn::default(),
        }
    }

    #[test]
    fn density_branch_resolves_continuous_bin_colors() {
        let input = minimal_input(
            XytaTraceDispatchPlan {
                pack_density: 1,
                ..Default::default()
            },
            SceneXytaColorChannelIn {
                present: 1,
                mode: "continuous",
                colormap: Some("viridis"),
                domain_lo: 0.0,
                domain_hi: 1.0,
                has_domain: 1,
                values_f64: &[0.0, 1.0],
                ..Default::default()
            },
            &[0.1, 0.9],
            &[0.2, 0.8],
        );
        let out = scene_xyta_trace_observations_materialize(&input).unwrap();
        assert_eq!(out.pack_density, 1);
        assert!(!out.idx.is_empty());
        assert_eq!(out.lut.len(), 256 * 4);
    }
}
