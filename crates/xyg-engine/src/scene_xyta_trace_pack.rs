//! Per-trace XYTA attach record packing (M2 big-push 2, ABI 318).

use crate::scene_trace_attach::{
    FLAG_DENSITY, FLAG_HAS_COLOR_CH, FLAG_HAS_DOMAIN, FLAG_HAS_FILL_OPACITY, FLAG_HAS_GRID,
    FLAG_HAS_OPACITY, FLAG_HAS_RGBA, FLAG_HAS_RGBA_GRID, FLAG_HAS_STYLE_COLOR, FLAG_HEATMAP,
    FLAG_MESH_FACES, FLAG_RIBBON_ENDS, FLAG_SCATTER_PAINT, FLAG_SHAPE, FLAG_TRUECOLOR,
    XYTA_PREFIX_BYTES,
};

pub const SCENE_XYTA_TRACE_PACK_MAX_RECORD: usize = 1 << 20;

#[derive(Clone, Debug)]
pub struct XytaTracePackInput<'a> {
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
    pub grid: &'a [u8],
    pub rgba: &'a [u8],
    pub rgba_grid: &'a [u8],
    pub x: &'a [u8],
    pub y: &'a [u8],
    pub mean_rgba: &'a [u8],
    pub idx: &'a [u8],
    pub lut: &'a [u8],
    pub cmap: &'a [u8],
    pub stops: &'a [u8],
    pub color_ch: &'a [u8],
    pub style_color: &'a [u8],
}

fn capped_u16(len: usize) -> u16 {
    u16::try_from(len.min(65535)).unwrap_or(65535)
}

pub fn scene_xyta_trace_pack(input: &XytaTracePackInput<'_>) -> Result<Vec<u8>, i32> {
    let mut flags = input.cmap_flags;
    let rows = input.rows;
    let cols = input.cols;
    if input.pack_heatmap != 0 {
        flags |= FLAG_HEATMAP;
        if input.has_grid_shape != 0 {
            flags |= FLAG_SHAPE;
        }
        if input.has_grid != 0 {
            flags |= FLAG_HAS_GRID;
        }
        if input.has_rgba != 0 {
            flags |= FLAG_HAS_RGBA;
        }
        if input.has_rgba_grid != 0 {
            flags |= FLAG_HAS_RGBA_GRID;
        }
        if input.truecolor != 0 {
            flags |= FLAG_TRUECOLOR;
        }
        if input.has_cmap_domain != 0 {
            flags |= FLAG_HAS_DOMAIN;
        }
    } else if input.pack_hexbin_colormap != 0 {
        flags |= FLAG_HEATMAP | FLAG_SHAPE | FLAG_HAS_GRID;
        if input.has_cmap_domain != 0 {
            flags |= FLAG_HAS_DOMAIN;
        }
    } else if input.pack_hexbin_rgba != 0 {
        flags |= FLAG_HEATMAP | FLAG_SHAPE | FLAG_HAS_GRID | FLAG_HAS_RGBA;
    } else if input.pack_ribbon_ends != 0 {
        flags |= FLAG_RIBBON_ENDS | FLAG_SHAPE | FLAG_HAS_RGBA;
    } else if input.pack_mesh_faces != 0 {
        flags |= FLAG_MESH_FACES | FLAG_SHAPE | FLAG_HAS_RGBA;
    } else if input.pack_scatter_paint != 0 {
        flags |= FLAG_SCATTER_PAINT | FLAG_SHAPE | FLAG_HAS_RGBA;
    } else if input.pack_density != 0 {
        flags |= FLAG_DENSITY;
        if input.has_color_ch != 0 {
            flags |= FLAG_HAS_COLOR_CH;
        }
        if input.has_style_color != 0 {
            flags |= FLAG_HAS_STYLE_COLOR;
        }
        if input.has_opacity != 0 {
            flags |= FLAG_HAS_OPACITY;
        }
        if input.has_fill_opacity != 0 {
            flags |= FLAG_HAS_FILL_OPACITY;
        }
    }
    let n_grid = u32::try_from(input.grid.len() / 8).map_err(|_| -1)?;
    let n_rgba = u32::try_from(input.rgba.len()).map_err(|_| -1)?;
    let n_rgba_grid = u32::try_from(input.rgba_grid.len() / 8).map_err(|_| -1)?;
    let n_x = u32::try_from(input.x.len() / 8).map_err(|_| -1)?;
    let n_y = u32::try_from(input.y.len() / 8).map_err(|_| -1)?;
    let n_mean_rgba = u32::try_from(input.mean_rgba.len()).map_err(|_| -1)?;
    let n_idx = u32::try_from(input.idx.len()).map_err(|_| -1)?;
    let n_lut = u32::try_from(input.lut.len()).map_err(|_| -1)?;
    let n_cmap = capped_u16(input.cmap.len());
    let n_stops = capped_u16(input.stops.len());
    let n_color_ch = capped_u16(input.color_ch.len());
    let n_style_color = capped_u16(input.style_color.len());
    let total = XYTA_PREFIX_BYTES
        .checked_add(input.grid.len())
        .and_then(|n| n.checked_add(input.rgba.len()))
        .and_then(|n| n.checked_add(input.rgba_grid.len()))
        .and_then(|n| n.checked_add(usize::from(n_cmap)))
        .and_then(|n| n.checked_add(usize::from(n_stops)))
        .and_then(|n| n.checked_add(usize::from(n_color_ch)))
        .and_then(|n| n.checked_add(usize::from(n_style_color)))
        .and_then(|n| n.checked_add(input.x.len()))
        .and_then(|n| n.checked_add(input.y.len()))
        .and_then(|n| n.checked_add(input.mean_rgba.len()))
        .and_then(|n| n.checked_add(input.idx.len()))
        .and_then(|n| n.checked_add(input.lut.len()))
        .ok_or(-1)?;
    if total > SCENE_XYTA_TRACE_PACK_MAX_RECORD {
        return Err(-1);
    }
    let mut out = vec![0u8; total];
    out[0..4].copy_from_slice(&flags.to_le_bytes());
    out[4..8].copy_from_slice(&input.trace_id.to_le_bytes());
    out[8..12].copy_from_slice(&rows.to_le_bytes());
    out[12..16].copy_from_slice(&cols.to_le_bytes());
    out[16..20].copy_from_slice(&n_grid.to_le_bytes());
    out[20..24].copy_from_slice(&n_rgba.to_le_bytes());
    out[24..28].copy_from_slice(&n_rgba_grid.to_le_bytes());
    out[28..32].copy_from_slice(&n_x.to_le_bytes());
    out[32..36].copy_from_slice(&n_y.to_le_bytes());
    out[36..40].copy_from_slice(&n_mean_rgba.to_le_bytes());
    out[40..44].copy_from_slice(&n_idx.to_le_bytes());
    out[44..48].copy_from_slice(&n_lut.to_le_bytes());
    out[48..50].copy_from_slice(&n_cmap.to_le_bytes());
    out[50..52].copy_from_slice(&n_stops.to_le_bytes());
    out[52..54].copy_from_slice(&n_color_ch.to_le_bytes());
    out[54..56].copy_from_slice(&n_style_color.to_le_bytes());
    out[56..64].copy_from_slice(&input.domain_x0.to_le_bytes());
    out[64..72].copy_from_slice(&input.domain_x1.to_le_bytes());
    out[72..80].copy_from_slice(&input.domain_y0.to_le_bytes());
    out[80..88].copy_from_slice(&input.domain_y1.to_le_bytes());
    out[88..96].copy_from_slice(&input.cmap_lo.to_le_bytes());
    out[96..104].copy_from_slice(&input.cmap_hi.to_le_bytes());
    out[104..108].copy_from_slice(&input.opacity.to_le_bytes());
    out[108..112].copy_from_slice(&input.fill_opacity.to_le_bytes());
    let mut at = XYTA_PREFIX_BYTES;
    for chunk in [
        input.grid,
        input.rgba,
        input.rgba_grid,
        &input.cmap[..usize::from(n_cmap)],
        &input.stops[..usize::from(n_stops)],
        &input.color_ch[..usize::from(n_color_ch)],
        &input.style_color[..usize::from(n_style_color)],
        input.x,
        input.y,
        input.mean_rgba,
        input.idx,
        input.lut,
    ] {
        out[at..at + chunk.len()].copy_from_slice(chunk);
        at += chunk.len();
    }
    Ok(out)
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::scene_trace_attach::FLAG_DENSITY;

    #[test]
    fn density_branch_sets_density_flag() {
        let input = XytaTracePackInput {
            trace_id: 7,
            pack_heatmap: 0,
            pack_hexbin_colormap: 0,
            pack_hexbin_rgba: 0,
            pack_ribbon_ends: 0,
            pack_mesh_faces: 0,
            pack_scatter_paint: 0,
            pack_density: 1,
            grid_shape_rows: 0.0,
            grid_shape_cols: 0.0,
            has_grid_shape: 0,
            has_grid: 0,
            has_rgba: 0,
            has_rgba_grid: 0,
            truecolor: 0,
            has_cmap_domain: 0,
            cmap_lo: 0.0,
            cmap_hi: 1.0,
            has_color_ch: 0,
            has_style_color: 0,
            has_opacity: 0,
            has_fill_opacity: 0,
            opacity: 1.0,
            fill_opacity: 1.0,
            domain_x0: 0.0,
            domain_x1: 1.0,
            domain_y0: 0.0,
            domain_y1: 1.0,
            cmap_flags: 0,
            rows: 0,
            cols: 0,
            grid: b"",
            rgba: b"",
            rgba_grid: b"",
            x: b"",
            y: b"",
            mean_rgba: b"",
            idx: b"",
            lut: b"",
            cmap: b"",
            stops: b"",
            color_ch: b"",
            style_color: b"",
        };
        let record = scene_xyta_trace_pack(&input).unwrap();
        let flags = u32::from_le_bytes(record[0..4].try_into().unwrap());
        assert_ne!(flags & FLAG_DENSITY, 0);
    }
}
