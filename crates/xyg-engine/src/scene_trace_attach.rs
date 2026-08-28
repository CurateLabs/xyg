//! Compact Figure→Scene heatmap/density attach packing (M2 #271).
//!
//! Hosts pack authored heatmap grids, density columns, colormaps, and
//! paint-plane literals as XYTA v1 against an XYTO compile bundle. Rust owns
//! heatmap shape/extent/finite fail-closed checks, XYHF remainder concat
//! order, density skip (empty/non-increasing domain), density XYHF flag
//! packing, `FACT_HEATMAP_PAINT` / `FACT_DENSITY_PLANE`, density
//! symbol/diameter zeroing, and domain-endpoint column rewrite so Python and
//! Node cannot drift. ABI 186 reuses `FLAG_HEATMAP` / `FACT_HEATMAP_PAINT` for
//! cartesian colormap hexbin as a 1×N XYHP plane. Encoded Scene v31 is unchanged.

use crate::kernels::BinColorSource;
use crate::scene_density::{self, pack_density_grid, DensityGridError, XYDE_HAS_MEAN_RGBA};
use crate::scene_heatmap::{
    pack_heatmap_facts, HeatmapFactError, XYHF_FAMILY_DENSITY, XYHF_FAMILY_HEATMAP,
    XYHF_HAS_COLOR_CH, XYHF_HAS_DOMAIN, XYHF_HAS_ENCODED, XYHF_HAS_FILL_OPACITY, XYHF_HAS_GRID,
    XYHF_HAS_MEAN_RGBA, XYHF_HAS_NAMED_CMAP, XYHF_HAS_OPACITY, XYHF_HAS_RGBA, XYHF_HAS_RGBA_GRID,
    XYHF_HAS_STOPS, XYHF_HAS_STYLE_COLOR, XYHF_HAS_TRUECOLOR, XYHF_MAGIC, XYHF_V1_HEADER_BYTES,
    XYHF_VERSION,
};
use crate::scene_pack::{FACT_DENSITY_PLANE, FACT_HEATMAP_PAINT};
use crate::scene_trace_compile::{XYTO_HEADER_BYTES, XYTO_MAGIC, XYTO_PREFIX_BYTES, XYTO_VERSION};

pub const XYTA_MAGIC: &[u8; 4] = b"XYTA";
pub const XYTA_VERSION: u32 = 1;
pub const XYTA_HEADER_BYTES: usize = 16;
pub const XYTA_PREFIX_BYTES: usize = 128;
pub const XYTT_MAGIC: &[u8; 4] = b"XYTT";
pub const XYTT_VERSION: u32 = 1;
pub const XYTT_HEADER_BYTES: usize = 16;
pub const XYTT_PREFIX_BYTES: usize = 208;

pub const FLAG_HEATMAP: u32 = 1 << 0;
pub const FLAG_DENSITY: u32 = 1 << 1;
pub const FLAG_HAS_RGBA: u32 = 1 << 2;
pub const FLAG_HAS_RGBA_GRID: u32 = 1 << 3;
pub const FLAG_HAS_GRID: u32 = 1 << 4;
pub const FLAG_TRUECOLOR: u32 = 1 << 5;
pub const FLAG_HAS_NAMED_CMAP: u32 = 1 << 6;
pub const FLAG_HAS_STOPS: u32 = 1 << 7;
pub const FLAG_HAS_COLOR_CH: u32 = 1 << 8;
pub const FLAG_HAS_STYLE_COLOR: u32 = 1 << 9;
pub const FLAG_HAS_OPACITY: u32 = 1 << 10;
pub const FLAG_HAS_FILL_OPACITY: u32 = 1 << 11;
pub const FLAG_HAS_DOMAIN: u32 = 1 << 12;
pub const FLAG_SHAPE: u32 = 1 << 13;

const MAX_TRACES: usize = 4_096;
const NAN: f64 = f64::NAN;

/// Why an XYTA attach request was rejected. Discriminants are the C-ABI
/// error codes (returned negated by `xyg_scene_pack_trace_attach`).
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum TraceAttachCode {
    Length = 1,
    Version = 2,
    Limit = 3,
    Output = 4,
    HeatmapShape = 5,
    HeatmapPositive = 6,
    HeatmapGrid = 7,
    HeatmapMatch = 8,
    HeatmapFinite = 9,
    HeatmapRgba = 10,
    HeatmapPlanes = 11,
    HeatmapCmap = 12,
    DensityCols = 13,
    DensitySource = 14,
    HeatmapPack = 15,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct TraceAttachError {
    pub code: TraceAttachCode,
    pub index: u32,
}

impl TraceAttachError {
    fn new(code: TraceAttachCode, index: usize) -> Self {
        Self {
            code,
            index: index as u32,
        }
    }
}

struct CompiledTrace {
    prefix: Vec<u8>,
    payloads: Vec<u8>,
}

struct AttachInput<'a> {
    flags: u32,
    stable_id: u32,
    rows: i32,
    cols: i32,
    grid: &'a [u8],
    rgba: &'a [u8],
    rgba_grid: &'a [u8],
    x: &'a [u8],
    y: &'a [u8],
    mean_rgba: &'a [u8],
    idx: &'a [u8],
    lut: &'a [u8],
    cmap: &'a [u8],
    stops: &'a [u8],
    color_ch: &'a [u8],
    style_color: &'a [u8],
    domain_x0: f64,
    domain_x1: f64,
    domain_y0: f64,
    domain_y1: f64,
    cmap_lo: f64,
    cmap_hi: f64,
    opacity: f32,
    fill_opacity: f32,
}

fn read_u16(bytes: &[u8], offset: usize) -> Result<u16, TraceAttachError> {
    Ok(u16::from_le_bytes(
        bytes
            .get(offset..offset + 2)
            .ok_or(TraceAttachError::new(TraceAttachCode::Length, 0))?
            .try_into()
            .map_err(|_| TraceAttachError::new(TraceAttachCode::Length, 0))?,
    ))
}

fn read_u32(bytes: &[u8], offset: usize) -> Result<u32, TraceAttachError> {
    Ok(u32::from_le_bytes(
        bytes
            .get(offset..offset + 4)
            .ok_or(TraceAttachError::new(TraceAttachCode::Length, 0))?
            .try_into()
            .map_err(|_| TraceAttachError::new(TraceAttachCode::Length, 0))?,
    ))
}

fn read_i32(bytes: &[u8], offset: usize) -> Result<i32, TraceAttachError> {
    Ok(i32::from_le_bytes(
        bytes
            .get(offset..offset + 4)
            .ok_or(TraceAttachError::new(TraceAttachCode::Length, 0))?
            .try_into()
            .map_err(|_| TraceAttachError::new(TraceAttachCode::Length, 0))?,
    ))
}

fn read_f32(bytes: &[u8], offset: usize) -> Result<f32, TraceAttachError> {
    Ok(f32::from_le_bytes(
        bytes
            .get(offset..offset + 4)
            .ok_or(TraceAttachError::new(TraceAttachCode::Length, 0))?
            .try_into()
            .map_err(|_| TraceAttachError::new(TraceAttachCode::Length, 0))?,
    ))
}

fn read_f64(bytes: &[u8], offset: usize) -> Result<f64, TraceAttachError> {
    Ok(f64::from_le_bytes(
        bytes
            .get(offset..offset + 8)
            .ok_or(TraceAttachError::new(TraceAttachCode::Length, 0))?
            .try_into()
            .map_err(|_| TraceAttachError::new(TraceAttachCode::Length, 0))?,
    ))
}

fn take<'a>(rest: &mut &'a [u8], n: usize, index: usize) -> Result<&'a [u8], TraceAttachError> {
    if rest.len() < n {
        return Err(TraceAttachError::new(TraceAttachCode::Length, index));
    }
    let (head, tail) = rest.split_at(n);
    *rest = tail;
    Ok(head)
}

fn f64_bytes_len(count: u32, index: usize) -> Result<usize, TraceAttachError> {
    (count as usize)
        .checked_mul(8)
        .ok_or(TraceAttachError::new(TraceAttachCode::Limit, index))
}

fn parse_xyto(bytes: &[u8]) -> Result<Vec<CompiledTrace>, TraceAttachError> {
    if bytes.len() < XYTO_HEADER_BYTES || bytes.get(..4) != Some(&XYTO_MAGIC[..]) {
        return Err(TraceAttachError::new(TraceAttachCode::Length, 0));
    }
    if read_u32(bytes, 4)? != XYTO_VERSION {
        return Err(TraceAttachError::new(TraceAttachCode::Version, 0));
    }
    let n_traces = read_u32(bytes, 8)? as usize;
    if n_traces > MAX_TRACES {
        return Err(TraceAttachError::new(TraceAttachCode::Limit, 0));
    }
    let mut at = XYTO_HEADER_BYTES;
    let mut traces = Vec::with_capacity(n_traces);
    for index in 0..n_traces {
        if at
            .checked_add(XYTO_PREFIX_BYTES)
            .is_none_or(|end| end > bytes.len())
        {
            return Err(TraceAttachError::new(TraceAttachCode::Length, index));
        }
        if bytes.get(at..at + 4) != Some(&XYTO_MAGIC[..]) {
            return Err(TraceAttachError::new(TraceAttachCode::Length, index));
        }
        let dash_count = read_u32(bytes, at + 44)? as usize;
        let marker_len = read_u32(bytes, at + 52)? as usize;
        let gradient_len = read_u32(bytes, at + 56)? as usize;
        let payload_len = dash_count
            .checked_mul(8)
            .and_then(|n| n.checked_add(marker_len))
            .and_then(|n| n.checked_add(gradient_len))
            .ok_or(TraceAttachError::new(TraceAttachCode::Limit, index))?;
        let prefix = bytes[at..at + XYTO_PREFIX_BYTES].to_vec();
        at += XYTO_PREFIX_BYTES;
        if at
            .checked_add(payload_len)
            .is_none_or(|end| end > bytes.len())
        {
            return Err(TraceAttachError::new(TraceAttachCode::Length, index));
        }
        let payloads = bytes[at..at + payload_len].to_vec();
        at += payload_len;
        traces.push(CompiledTrace { prefix, payloads });
    }
    if at != bytes.len() {
        return Err(TraceAttachError::new(TraceAttachCode::Length, 0));
    }
    Ok(traces)
}

fn parse_attach<'a>(
    bytes: &'a [u8],
    at: &mut usize,
    index: usize,
) -> Result<AttachInput<'a>, TraceAttachError> {
    let start = *at;
    if start
        .checked_add(XYTA_PREFIX_BYTES)
        .is_none_or(|end| end > bytes.len())
    {
        return Err(TraceAttachError::new(TraceAttachCode::Length, index));
    }
    let flags = read_u32(bytes, start)?;
    let stable_id = read_u32(bytes, start + 4)?;
    let rows = read_i32(bytes, start + 8)?;
    let cols = read_i32(bytes, start + 12)?;
    let n_grid = read_u32(bytes, start + 16)?;
    let n_rgba = read_u32(bytes, start + 20)?;
    let n_rgba_grid = read_u32(bytes, start + 24)?;
    let n_x = read_u32(bytes, start + 28)?;
    let n_y = read_u32(bytes, start + 32)?;
    let n_mean_rgba = read_u32(bytes, start + 36)?;
    let n_idx = read_u32(bytes, start + 40)?;
    let n_lut = read_u32(bytes, start + 44)?;
    let n_cmap = read_u16(bytes, start + 48)? as usize;
    let n_stops = read_u16(bytes, start + 50)? as usize;
    let n_color_ch = read_u16(bytes, start + 52)? as usize;
    let n_style_color = read_u16(bytes, start + 54)? as usize;
    let domain_x0 = read_f64(bytes, start + 56)?;
    let domain_x1 = read_f64(bytes, start + 64)?;
    let domain_y0 = read_f64(bytes, start + 72)?;
    let domain_y1 = read_f64(bytes, start + 80)?;
    let cmap_lo = read_f64(bytes, start + 88)?;
    let cmap_hi = read_f64(bytes, start + 96)?;
    let opacity = read_f32(bytes, start + 104)?;
    let fill_opacity = read_f32(bytes, start + 108)?;
    *at = start + XYTA_PREFIX_BYTES;
    let mut rest = bytes
        .get(*at..)
        .ok_or(TraceAttachError::new(TraceAttachCode::Length, index))?;
    let grid = take(&mut rest, f64_bytes_len(n_grid, index)?, index)?;
    let rgba = take(&mut rest, n_rgba as usize, index)?;
    let rgba_grid = take(&mut rest, f64_bytes_len(n_rgba_grid, index)?, index)?;
    let cmap = take(&mut rest, n_cmap, index)?;
    let stops = take(&mut rest, n_stops, index)?;
    let color_ch = take(&mut rest, n_color_ch, index)?;
    let style_color = take(&mut rest, n_style_color, index)?;
    let x = take(&mut rest, f64_bytes_len(n_x, index)?, index)?;
    let y = take(&mut rest, f64_bytes_len(n_y, index)?, index)?;
    let mean_rgba = take(&mut rest, n_mean_rgba as usize, index)?;
    let idx = take(&mut rest, n_idx as usize, index)?;
    let lut = take(&mut rest, n_lut as usize, index)?;
    *at = bytes.len() - rest.len();
    Ok(AttachInput {
        flags,
        stable_id,
        rows,
        cols,
        grid,
        rgba,
        rgba_grid,
        x,
        y,
        mean_rgba,
        idx,
        lut,
        cmap,
        stops,
        color_ch,
        style_color,
        domain_x0,
        domain_x1,
        domain_y0,
        domain_y1,
        cmap_lo,
        cmap_hi,
        opacity,
        fill_opacity,
    })
}

fn put_prefixed(out: &mut Vec<u8>, payload: &[u8]) {
    out.extend_from_slice(&(payload.len() as u32).to_le_bytes());
    out.extend_from_slice(payload);
}

fn write_xyhf(
    family: u8,
    flags: u32,
    stable_id: u64,
    rows: u32,
    cols: u32,
    lo: f64,
    hi: f64,
    opacity: f64,
    fill_opacity: f64,
    remainder: &[u8],
) -> Vec<u8> {
    let mut out = vec![0u8; XYHF_V1_HEADER_BYTES];
    out[..4].copy_from_slice(XYHF_MAGIC);
    out[4..8].copy_from_slice(&XYHF_VERSION.to_le_bytes());
    out[8..16].copy_from_slice(&stable_id.to_le_bytes());
    out[16..20].copy_from_slice(&rows.to_le_bytes());
    out[20..24].copy_from_slice(&cols.to_le_bytes());
    out[24..28].copy_from_slice(&flags.to_le_bytes());
    out[28] = family;
    out[32..40].copy_from_slice(&lo.to_le_bytes());
    out[40..48].copy_from_slice(&hi.to_le_bytes());
    out[48..56].copy_from_slice(&opacity.to_le_bytes());
    out[56..64].copy_from_slice(&fill_opacity.to_le_bytes());
    out.extend_from_slice(remainder);
    out
}

fn heatmap_fact_error(error: HeatmapFactError, index: usize) -> TraceAttachError {
    match error {
        HeatmapFactError::Payload => TraceAttachError::new(TraceAttachCode::HeatmapCmap, index),
        _ => TraceAttachError::new(TraceAttachCode::HeatmapPack, index),
    }
}

fn density_grid_error(error: DensityGridError, index: usize) -> TraceAttachError {
    match error {
        DensityGridError::Shape => TraceAttachError::new(TraceAttachCode::DensityCols, index),
        DensityGridError::Payload => TraceAttachError::new(TraceAttachCode::DensitySource, index),
        _ => TraceAttachError::new(TraceAttachCode::HeatmapPack, index),
    }
}

fn as_f64s(bytes: &[u8], index: usize) -> Result<Vec<f64>, TraceAttachError> {
    if bytes.len() % 8 != 0 {
        return Err(TraceAttachError::new(TraceAttachCode::Length, index));
    }
    Ok(bytes
        .chunks_exact(8)
        .map(|chunk| f64::from_le_bytes(chunk.try_into().unwrap()))
        .collect())
}

fn cells(rows: i32, cols: i32, index: usize) -> Result<usize, TraceAttachError> {
    let rows = usize::try_from(rows)
        .map_err(|_| TraceAttachError::new(TraceAttachCode::HeatmapPositive, index))?;
    let cols = usize::try_from(cols)
        .map_err(|_| TraceAttachError::new(TraceAttachCode::HeatmapPositive, index))?;
    rows.checked_mul(cols)
        .ok_or(TraceAttachError::new(TraceAttachCode::Limit, index))
}

fn or_fact(prefix: &mut [u8], bit: u8) {
    let mut facts = u32::from_le_bytes(prefix[40..44].try_into().unwrap());
    facts |= u32::from(bit);
    prefix[40..44].copy_from_slice(&facts.to_le_bytes());
}

fn zero_scatter_draw(prefix: &mut [u8]) {
    prefix[24..32].copy_from_slice(&0.0f64.to_le_bytes());
    prefix[32..34].copy_from_slice(&0u16.to_le_bytes());
}

fn attach_heatmap(
    input: &AttachInput<'_>,
    compiled: &mut CompiledTrace,
    index: usize,
) -> Result<(Vec<u8>, u32, u32), TraceAttachError> {
    if input.flags & FLAG_SHAPE == 0 {
        return Err(TraceAttachError::new(TraceAttachCode::HeatmapShape, index));
    }
    if input.rows < 1 || input.cols < 1 {
        return Err(TraceAttachError::new(
            TraceAttachCode::HeatmapPositive,
            index,
        ));
    }
    let n = cells(input.rows, input.cols, index)?;
    if input.flags & FLAG_HAS_GRID == 0 || input.grid.len() != n.saturating_mul(8) {
        if input.flags & FLAG_HAS_GRID == 0 || input.grid.is_empty() {
            return Err(TraceAttachError::new(TraceAttachCode::HeatmapGrid, index));
        }
        return Err(TraceAttachError::new(TraceAttachCode::HeatmapMatch, index));
    }
    for chunk in input.grid.chunks_exact(8) {
        let value = f64::from_le_bytes(chunk.try_into().unwrap());
        if !value.is_finite() {
            return Err(TraceAttachError::new(TraceAttachCode::HeatmapFinite, index));
        }
    }
    if input.flags & FLAG_HAS_RGBA != 0 && input.rgba.len() != n.saturating_mul(4) {
        return Err(TraceAttachError::new(TraceAttachCode::HeatmapRgba, index));
    }
    if input.flags & FLAG_HAS_RGBA_GRID != 0 && input.rgba_grid.len() != n.saturating_mul(32) {
        return Err(TraceAttachError::new(TraceAttachCode::HeatmapPlanes, index));
    }
    if input.flags & FLAG_HAS_STOPS != 0 && (input.stops.len() < 3 || input.stops.len() % 3 != 0) {
        return Err(TraceAttachError::new(TraceAttachCode::HeatmapCmap, index));
    }
    let rows = input.rows as u32;
    let cols = input.cols as u32;
    let mut flags = XYHF_HAS_GRID;
    let mut remainder = Vec::new();
    if input.flags & FLAG_HAS_RGBA != 0 {
        flags |= XYHF_HAS_RGBA;
        remainder.extend_from_slice(input.rgba);
    }
    if input.flags & FLAG_HAS_RGBA_GRID != 0 {
        flags |= XYHF_HAS_RGBA_GRID;
        remainder.extend_from_slice(input.rgba_grid);
    }
    remainder.extend_from_slice(input.grid);
    if input.flags & FLAG_HAS_NAMED_CMAP != 0 {
        flags |= XYHF_HAS_NAMED_CMAP;
        put_prefixed(&mut remainder, input.cmap);
    } else if input.flags & FLAG_HAS_STOPS != 0 {
        flags |= XYHF_HAS_STOPS;
        put_prefixed(&mut remainder, input.stops);
    }
    if input.flags & FLAG_TRUECOLOR != 0 {
        flags |= XYHF_HAS_TRUECOLOR;
    }
    let mut lo = NAN;
    let mut hi = NAN;
    if input.flags & FLAG_HAS_DOMAIN != 0 {
        flags |= XYHF_HAS_DOMAIN;
        lo = input.cmap_lo;
        hi = input.cmap_hi;
    }
    let plane = pack_heatmap_facts(&write_xyhf(
        XYHF_FAMILY_HEATMAP,
        flags,
        u64::from(input.stable_id),
        rows,
        cols,
        lo,
        hi,
        NAN,
        NAN,
        &remainder,
    ))
    .map_err(|error| heatmap_fact_error(error, index))?;
    if !plane.is_empty() {
        or_fact(&mut compiled.prefix, FACT_HEATMAP_PAINT);
    }
    Ok((plane, rows, cols))
}

fn attach_density(
    input: &AttachInput<'_>,
    compiled: &mut CompiledTrace,
    index: usize,
) -> Result<(Vec<u8>, u32, u32, Option<[f64; 4]>), TraceAttachError> {
    let x = as_f64s(input.x, index)?;
    let y = as_f64s(input.y, index)?;
    if x.len() != y.len() {
        return Err(TraceAttachError::new(TraceAttachCode::DensityCols, index));
    }
    if x.is_empty() {
        return Ok((Vec::new(), 0, 0, None));
    }
    let lut = if input.lut.is_empty() {
        Vec::new()
    } else {
        if input.lut.len() % 4 != 0 {
            return Err(TraceAttachError::new(TraceAttachCode::DensitySource, index));
        }
        input
            .lut
            .chunks_exact(4)
            .map(|chunk| [chunk[0], chunk[1], chunk[2], chunk[3]])
            .collect::<Vec<[u8; 4]>>()
    };
    let colors = if !input.mean_rgba.is_empty() {
        Some(BinColorSource::Rgba(input.mean_rgba))
    } else if !input.idx.is_empty() && !lut.is_empty() {
        Some(BinColorSource::Indexed {
            idx: input.idx,
            lut: lut.as_slice(),
        })
    } else if !input.idx.is_empty() || !input.lut.is_empty() {
        return Err(TraceAttachError::new(TraceAttachCode::DensitySource, index));
    } else {
        None
    };
    let packed = pack_density_grid(
        &x,
        &y,
        input.domain_x0,
        input.domain_x1,
        input.domain_y0,
        input.domain_y1,
        colors,
    )
    .map_err(|error| density_grid_error(error, index))?;
    if packed.is_empty() {
        return Ok((Vec::new(), 0, 0, None));
    }
    if packed.len() < scene_density::XYDE_V1_HEADER_BYTES
        || packed.get(..4) != Some(&scene_density::XYDE_MAGIC[..])
    {
        return Err(TraceAttachError::new(TraceAttachCode::HeatmapPack, index));
    }
    let cols = u32::from_le_bytes(packed[8..12].try_into().unwrap());
    let rows = u32::from_le_bytes(packed[12..16].try_into().unwrap());
    let de_flags = u32::from_le_bytes(packed[16..20].try_into().unwrap());
    let maximum = f64::from_le_bytes(packed[24..32].try_into().unwrap());
    let n = (rows as usize)
        .checked_mul(cols as usize)
        .ok_or(TraceAttachError::new(TraceAttachCode::Limit, index))?;
    let encoded_end = scene_density::XYDE_V1_HEADER_BYTES
        .checked_add(n)
        .ok_or(TraceAttachError::new(TraceAttachCode::Limit, index))?;
    if packed.len() < encoded_end {
        return Err(TraceAttachError::new(TraceAttachCode::Length, index));
    }
    let encoded = &packed[scene_density::XYDE_V1_HEADER_BYTES..encoded_end];
    let mean = if de_flags & XYDE_HAS_MEAN_RGBA != 0 {
        let end = encoded_end
            .checked_add(n.saturating_mul(4))
            .ok_or(TraceAttachError::new(TraceAttachCode::Limit, index))?;
        if packed.len() < end {
            return Err(TraceAttachError::new(TraceAttachCode::Length, index));
        }
        Some(&packed[encoded_end..end])
    } else {
        None
    };
    if input.flags & FLAG_HAS_STOPS != 0 && (input.stops.len() < 3 || input.stops.len() % 3 != 0) {
        return Err(TraceAttachError::new(TraceAttachCode::HeatmapCmap, index));
    }
    let mut flags = XYHF_HAS_ENCODED;
    let mut remainder = Vec::from(encoded);
    if let Some(rgba) = mean {
        flags |= XYHF_HAS_MEAN_RGBA;
        remainder.extend_from_slice(rgba);
    }
    if input.flags & FLAG_HAS_NAMED_CMAP != 0 {
        flags |= XYHF_HAS_NAMED_CMAP;
        put_prefixed(&mut remainder, input.cmap);
    } else if input.flags & FLAG_HAS_STOPS != 0 {
        flags |= XYHF_HAS_STOPS;
        put_prefixed(&mut remainder, input.stops);
    }
    if input.flags & FLAG_HAS_COLOR_CH != 0 {
        flags |= XYHF_HAS_COLOR_CH;
        put_prefixed(&mut remainder, input.color_ch);
    }
    if input.flags & FLAG_HAS_STYLE_COLOR != 0 {
        flags |= XYHF_HAS_STYLE_COLOR;
        put_prefixed(&mut remainder, input.style_color);
    }
    let mut opacity = NAN;
    let mut fill_opacity = NAN;
    if input.flags & FLAG_HAS_OPACITY != 0 {
        flags |= XYHF_HAS_OPACITY;
        opacity = f64::from(input.opacity);
    }
    if input.flags & FLAG_HAS_FILL_OPACITY != 0 {
        flags |= XYHF_HAS_FILL_OPACITY;
        fill_opacity = f64::from(input.fill_opacity);
    }
    let plane = pack_heatmap_facts(&write_xyhf(
        XYHF_FAMILY_DENSITY,
        flags,
        u64::from(input.stable_id),
        rows,
        cols,
        maximum,
        NAN,
        opacity,
        fill_opacity,
        &remainder,
    ))
    .map_err(|error| heatmap_fact_error(error, index))?;
    if plane.is_empty() {
        return Ok((Vec::new(), 0, 0, None));
    }
    or_fact(&mut compiled.prefix, FACT_DENSITY_PLANE);
    zero_scatter_draw(&mut compiled.prefix);
    Ok((
        plane,
        rows,
        cols,
        Some([
            input.domain_x0,
            input.domain_x1,
            input.domain_y0,
            input.domain_y1,
        ]),
    ))
}

fn write_attached(
    out: &mut Vec<u8>,
    compiled: &CompiledTrace,
    heatmap: &[u8],
    density: &[u8],
    grid_rows: u32,
    grid_cols: u32,
    rewrite: Option<[f64; 4]>,
) {
    let mut prefix = vec![0u8; XYTT_PREFIX_BYTES];
    prefix[..XYTO_PREFIX_BYTES].copy_from_slice(&compiled.prefix);
    prefix[160..164].copy_from_slice(&(heatmap.len() as u32).to_le_bytes());
    prefix[164..168].copy_from_slice(&(density.len() as u32).to_le_bytes());
    prefix[168..172].copy_from_slice(&grid_rows.to_le_bytes());
    prefix[172..176].copy_from_slice(&grid_cols.to_le_bytes());
    let coords = rewrite.unwrap_or([NAN, NAN, NAN, NAN]);
    prefix[176..184].copy_from_slice(&coords[0].to_le_bytes());
    prefix[184..192].copy_from_slice(&coords[1].to_le_bytes());
    prefix[192..200].copy_from_slice(&coords[2].to_le_bytes());
    prefix[200..208].copy_from_slice(&coords[3].to_le_bytes());
    out.extend_from_slice(&prefix);
    out.extend_from_slice(&compiled.payloads);
    out.extend_from_slice(heatmap);
    out.extend_from_slice(density);
}

/// How packed XYTA cell-fill facts tessellate on the product Scene.
///
/// ABI 189: hosts pack raw heatmap/hexbin attach observations; Rust decides
/// whether those facts intern onto per-cell paints (and therefore whether
/// XYFS `PER_ITEM` / `HEATMAP_COLORMAP` bits fail closed).
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum CellFillTessellation {
    None,
    Heatmap,
    Hexbin,
}

fn classify_cell_fill(input: &AttachInput<'_>) -> CellFillTessellation {
    if input.flags & FLAG_DENSITY != 0 || input.flags & FLAG_HEATMAP == 0 {
        return CellFillTessellation::None;
    }
    if input.flags & FLAG_HAS_RGBA_GRID != 0 {
        return CellFillTessellation::Heatmap;
    }
    if input.flags & FLAG_TRUECOLOR != 0 {
        return CellFillTessellation::None;
    }
    let has_paint = input.flags & FLAG_HAS_NAMED_CMAP != 0
        || input.flags & FLAG_HAS_STOPS != 0
        || input.flags & FLAG_HAS_RGBA != 0;
    if !has_paint {
        return CellFillTessellation::None;
    }
    if input.flags & FLAG_SHAPE != 0
        && input.flags & FLAG_HAS_GRID != 0
        && input.rows == 1
        && input.cols >= 1
        && input.flags & FLAG_HAS_RGBA == 0
    {
        return CellFillTessellation::Hexbin;
    }
    CellFillTessellation::Heatmap
}

/// Walk packed `XYTA` v1 and report per-trace cell-fill tessellation.
pub fn xyta_cell_fill_tessellation(
    attach: &[u8],
) -> Result<Vec<CellFillTessellation>, TraceAttachError> {
    if attach.is_empty() {
        return Ok(Vec::new());
    }
    if attach.len() < XYTA_HEADER_BYTES || attach.get(..4) != Some(&XYTA_MAGIC[..]) {
        return Err(TraceAttachError::new(TraceAttachCode::Length, 0));
    }
    if read_u32(attach, 4)? != XYTA_VERSION {
        return Err(TraceAttachError::new(TraceAttachCode::Version, 0));
    }
    let n_traces = read_u32(attach, 8)? as usize;
    if n_traces > MAX_TRACES {
        return Err(TraceAttachError::new(TraceAttachCode::Limit, 0));
    }
    let mut at = XYTA_HEADER_BYTES;
    let mut out = Vec::with_capacity(n_traces);
    for index in 0..n_traces {
        let input = parse_attach(attach, &mut at, index)?;
        out.push(classify_cell_fill(&input));
    }
    if at != attach.len() {
        return Err(TraceAttachError::new(TraceAttachCode::Length, 0));
    }
    Ok(out)
}

/// Pack compiled `XYTO` v1 plus authored `XYTA` v1 attach facts into `XYTT` v1.
pub fn pack_trace_attach(compiled: &[u8], attach: &[u8]) -> Result<Vec<u8>, TraceAttachError> {
    let mut traces = parse_xyto(compiled)?;
    if attach.len() < XYTA_HEADER_BYTES || attach.get(..4) != Some(&XYTA_MAGIC[..]) {
        return Err(TraceAttachError::new(TraceAttachCode::Length, 0));
    }
    if read_u32(attach, 4)? != XYTA_VERSION {
        return Err(TraceAttachError::new(TraceAttachCode::Version, 0));
    }
    let n_traces = read_u32(attach, 8)? as usize;
    if n_traces != traces.len() {
        return Err(TraceAttachError::new(TraceAttachCode::Length, 0));
    }
    if n_traces > MAX_TRACES {
        return Err(TraceAttachError::new(TraceAttachCode::Limit, 0));
    }
    let mut at = XYTA_HEADER_BYTES;
    let mut attached = Vec::with_capacity(n_traces);
    for index in 0..n_traces {
        let input = parse_attach(attach, &mut at, index)?;
        let compiled = &mut traces[index];
        let mut heatmap = Vec::new();
        let mut density = Vec::new();
        let mut grid_rows = 0u32;
        let mut grid_cols = 0u32;
        let mut rewrite = None;
        if input.flags & FLAG_HEATMAP != 0 {
            let (plane, rows, cols) = attach_heatmap(&input, compiled, index)?;
            heatmap = plane;
            grid_rows = rows;
            grid_cols = cols;
        } else if input.flags & FLAG_DENSITY != 0 {
            let (plane, rows, cols, coords) = attach_density(&input, compiled, index)?;
            density = plane;
            grid_rows = rows;
            grid_cols = cols;
            rewrite = coords;
        }
        attached.push((heatmap, density, grid_rows, grid_cols, rewrite));
    }
    if at != attach.len() {
        return Err(TraceAttachError::new(TraceAttachCode::Length, 0));
    }
    let mut out = Vec::new();
    out.extend_from_slice(XYTT_MAGIC);
    out.extend_from_slice(&XYTT_VERSION.to_le_bytes());
    out.extend_from_slice(&(n_traces as u32).to_le_bytes());
    out.extend_from_slice(&0u32.to_le_bytes());
    for (compiled, (heatmap, density, grid_rows, grid_cols, rewrite)) in
        traces.iter().zip(attached.into_iter())
    {
        write_attached(
            &mut out, compiled, &heatmap, &density, grid_rows, grid_cols, rewrite,
        );
    }
    Ok(out)
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::scene_trace_compile::{self, pack_trace_compile, XYTC_MAGIC, XYTC_VERSION};

    fn empty_compile() -> Vec<u8> {
        let mut facts = vec![0u8; 16];
        facts[..4].copy_from_slice(XYTC_MAGIC);
        facts[4..8].copy_from_slice(&XYTC_VERSION.to_le_bytes());
        pack_trace_compile(&facts).unwrap()
    }

    fn compile_kind(kind: &str) -> Vec<u8> {
        let mut prefix = vec![0u8; scene_trace_compile::XYTR_PREFIX_BYTES];
        prefix[..4].copy_from_slice(scene_trace_compile::XYTR_MAGIC);
        prefix[4..6].copy_from_slice(&1u16.to_le_bytes());
        prefix[6..8].copy_from_slice(&(kind.len() as u16).to_le_bytes());
        prefix[16..24].copy_from_slice(&1.0f64.to_le_bytes());
        prefix[24..32].copy_from_slice(&1.0f64.to_le_bytes());
        prefix[32..40].copy_from_slice(&1.0f64.to_le_bytes());
        prefix[40..48].copy_from_slice(&1.0f64.to_le_bytes());
        prefix[48..56].copy_from_slice(&f64::NAN.to_le_bytes());
        prefix[56..64].copy_from_slice(&f64::NAN.to_le_bytes());
        prefix[88..96].copy_from_slice(&f64::NAN.to_le_bytes());
        prefix[96..104].copy_from_slice(&f64::NAN.to_le_bytes());
        let mut facts = Vec::new();
        facts.extend_from_slice(XYTC_MAGIC);
        facts.extend_from_slice(&XYTC_VERSION.to_le_bytes());
        facts.extend_from_slice(&1u32.to_le_bytes());
        facts.extend_from_slice(&0u32.to_le_bytes());
        facts.extend_from_slice(&prefix);
        facts.extend_from_slice(kind.as_bytes());
        pack_trace_compile(&facts).unwrap()
    }

    fn scatter_compile() -> Vec<u8> {
        compile_kind("scatter")
    }

    fn heatmap_compile() -> Vec<u8> {
        compile_kind("heatmap")
    }

    fn xyta_header(n: u32) -> Vec<u8> {
        let mut facts = vec![0u8; XYTA_HEADER_BYTES];
        facts[..4].copy_from_slice(XYTA_MAGIC);
        facts[4..8].copy_from_slice(&XYTA_VERSION.to_le_bytes());
        facts[8..12].copy_from_slice(&n.to_le_bytes());
        facts
    }

    #[test]
    fn empty_attach_emits_xytt() {
        let packed = pack_trace_attach(&empty_compile(), &xyta_header(0)).unwrap();
        assert_eq!(&packed[..4], XYTT_MAGIC);
        assert_eq!(u32::from_le_bytes(packed[8..12].try_into().unwrap()), 0);
    }

    #[test]
    fn heatmap_missing_shape_is_shape_error() {
        let mut attach = xyta_header(1);
        let mut prefix = vec![0u8; XYTA_PREFIX_BYTES];
        prefix[..4].copy_from_slice(&FLAG_HEATMAP.to_le_bytes());
        attach.extend_from_slice(&prefix);
        let err = pack_trace_attach(&heatmap_compile(), &attach).unwrap_err();
        assert_eq!(err.code, TraceAttachCode::HeatmapShape);
    }

    #[test]
    fn heatmap_nonfinite_grid_is_finite_error() {
        let mut attach = xyta_header(1);
        let mut prefix = vec![0u8; XYTA_PREFIX_BYTES];
        let flags = FLAG_HEATMAP | FLAG_SHAPE | FLAG_HAS_GRID;
        prefix[..4].copy_from_slice(&flags.to_le_bytes());
        prefix[8..12].copy_from_slice(&1i32.to_le_bytes());
        prefix[12..16].copy_from_slice(&1i32.to_le_bytes());
        prefix[16..20].copy_from_slice(&1u32.to_le_bytes());
        attach.extend_from_slice(&prefix);
        attach.extend_from_slice(&f64::NAN.to_le_bytes());
        let err = pack_trace_attach(&heatmap_compile(), &attach).unwrap_err();
        assert_eq!(err.code, TraceAttachCode::HeatmapFinite);
    }

    #[test]
    fn named_heatmap_sets_paint_bit() {
        let mut attach = xyta_header(1);
        let mut prefix = vec![0u8; XYTA_PREFIX_BYTES];
        let flags = FLAG_HEATMAP | FLAG_SHAPE | FLAG_HAS_GRID | FLAG_HAS_NAMED_CMAP;
        prefix[..4].copy_from_slice(&flags.to_le_bytes());
        prefix[8..12].copy_from_slice(&2i32.to_le_bytes());
        prefix[12..16].copy_from_slice(&2i32.to_le_bytes());
        prefix[16..20].copy_from_slice(&4u32.to_le_bytes());
        prefix[48..50].copy_from_slice(&(b"viridis".len() as u16).to_le_bytes());
        attach.extend_from_slice(&prefix);
        for value in [0.0f64, 1.0, 2.0, 3.0] {
            attach.extend_from_slice(&value.to_le_bytes());
        }
        attach.extend_from_slice(b"viridis");
        let packed = pack_trace_attach(&heatmap_compile(), &attach).unwrap();
        assert_eq!(&packed[..4], XYTT_MAGIC);
        let facts = u32::from_le_bytes(
            packed[XYTT_HEADER_BYTES + 40..XYTT_HEADER_BYTES + 44]
                .try_into()
                .unwrap(),
        );
        assert_ne!(facts & u32::from(FACT_HEATMAP_PAINT), 0);
        let heatmap_len = u32::from_le_bytes(
            packed[XYTT_HEADER_BYTES + 160..XYTT_HEADER_BYTES + 164]
                .try_into()
                .unwrap(),
        );
        assert!(heatmap_len > 0);
        assert_eq!(
            u32::from_le_bytes(
                packed[XYTT_HEADER_BYTES + 168..XYTT_HEADER_BYTES + 172]
                    .try_into()
                    .unwrap()
            ),
            2
        );
    }

    #[test]
    fn density_bad_domain_skips_blit() {
        let mut attach = xyta_header(1);
        let mut prefix = vec![0u8; XYTA_PREFIX_BYTES];
        prefix[..4].copy_from_slice(&FLAG_DENSITY.to_le_bytes());
        prefix[28..32].copy_from_slice(&1u32.to_le_bytes());
        prefix[32..36].copy_from_slice(&1u32.to_le_bytes());
        prefix[56..64].copy_from_slice(&1.0f64.to_le_bytes());
        prefix[64..72].copy_from_slice(&1.0f64.to_le_bytes());
        prefix[72..80].copy_from_slice(&0.0f64.to_le_bytes());
        prefix[80..88].copy_from_slice(&1.0f64.to_le_bytes());
        attach.extend_from_slice(&prefix);
        attach.extend_from_slice(&0.5f64.to_le_bytes());
        attach.extend_from_slice(&0.5f64.to_le_bytes());
        let packed = pack_trace_attach(&scatter_compile(), &attach).unwrap();
        let facts = u32::from_le_bytes(
            packed[XYTT_HEADER_BYTES + 40..XYTT_HEADER_BYTES + 44]
                .try_into()
                .unwrap(),
        );
        assert_eq!(facts & u32::from(FACT_DENSITY_PLANE), 0);
        let diameter = f64::from_le_bytes(
            packed[XYTT_HEADER_BYTES + 24..XYTT_HEADER_BYTES + 32]
                .try_into()
                .unwrap(),
        );
        assert_eq!(diameter, 4.0);
    }

    #[test]
    fn density_points_zero_diameter_and_rewrite_domain() {
        let mut attach = xyta_header(1);
        let mut prefix = vec![0u8; XYTA_PREFIX_BYTES];
        prefix[..4].copy_from_slice(&FLAG_DENSITY.to_le_bytes());
        prefix[28..32].copy_from_slice(&2u32.to_le_bytes());
        prefix[32..36].copy_from_slice(&2u32.to_le_bytes());
        prefix[56..64].copy_from_slice(&0.0f64.to_le_bytes());
        prefix[64..72].copy_from_slice(&1.0f64.to_le_bytes());
        prefix[72..80].copy_from_slice(&0.0f64.to_le_bytes());
        prefix[80..88].copy_from_slice(&1.0f64.to_le_bytes());
        attach.extend_from_slice(&prefix);
        for value in [0.25f64, 0.75, 0.25, 0.75] {
            attach.extend_from_slice(&value.to_le_bytes());
        }
        let packed = pack_trace_attach(&scatter_compile(), &attach).unwrap();
        let facts = u32::from_le_bytes(
            packed[XYTT_HEADER_BYTES + 40..XYTT_HEADER_BYTES + 44]
                .try_into()
                .unwrap(),
        );
        assert_ne!(facts & u32::from(FACT_DENSITY_PLANE), 0);
        let diameter = f64::from_le_bytes(
            packed[XYTT_HEADER_BYTES + 24..XYTT_HEADER_BYTES + 32]
                .try_into()
                .unwrap(),
        );
        assert_eq!(diameter, 0.0);
        let density_len = u32::from_le_bytes(
            packed[XYTT_HEADER_BYTES + 164..XYTT_HEADER_BYTES + 168]
                .try_into()
                .unwrap(),
        );
        assert!(density_len > 0);
        let x0 = f64::from_le_bytes(
            packed[XYTT_HEADER_BYTES + 176..XYTT_HEADER_BYTES + 184]
                .try_into()
                .unwrap(),
        );
        let x1 = f64::from_le_bytes(
            packed[XYTT_HEADER_BYTES + 184..XYTT_HEADER_BYTES + 192]
                .try_into()
                .unwrap(),
        );
        assert_eq!((x0, x1), (0.0, 1.0));
    }

    fn xyta_one(
        flags: u32,
        rows: i32,
        cols: i32,
        grid: &[f64],
        cmap: &[u8],
        extra_flags: u32,
        rgba_grid_count: u32,
    ) -> Vec<u8> {
        let mut attach = xyta_header(1);
        let mut prefix = vec![0u8; XYTA_PREFIX_BYTES];
        prefix[..4].copy_from_slice(&(flags | extra_flags).to_le_bytes());
        prefix[8..12].copy_from_slice(&rows.to_le_bytes());
        prefix[12..16].copy_from_slice(&cols.to_le_bytes());
        prefix[16..20].copy_from_slice(&(grid.len() as u32).to_le_bytes());
        prefix[24..28].copy_from_slice(&rgba_grid_count.to_le_bytes());
        prefix[48..50].copy_from_slice(&(cmap.len() as u16).to_le_bytes());
        attach.extend_from_slice(&prefix);
        for value in grid {
            attach.extend_from_slice(&value.to_le_bytes());
        }
        for _ in 0..rgba_grid_count {
            attach.extend_from_slice(&0.0f64.to_le_bytes());
        }
        attach.extend_from_slice(cmap);
        attach
    }

    #[test]
    fn empty_xyta_has_no_cell_fill_tessellation() {
        assert_eq!(
            xyta_cell_fill_tessellation(&[]).unwrap(),
            Vec::<CellFillTessellation>::new()
        );
    }

    #[test]
    fn xyta_classifies_heatmap_hexbin_and_truecolor_cell_fills() {
        let named = FLAG_HEATMAP | FLAG_SHAPE | FLAG_HAS_GRID | FLAG_HAS_NAMED_CMAP;
        assert_eq!(
            xyta_cell_fill_tessellation(&xyta_one(
                named,
                2,
                2,
                &[0.0, 1.0, 2.0, 3.0],
                b"viridis",
                0,
                0
            ))
            .unwrap(),
            vec![CellFillTessellation::Heatmap]
        );
        assert_eq!(
            xyta_cell_fill_tessellation(&xyta_one(named, 1, 3, &[0.0, 1.0, 2.0], b"viridis", 0, 0))
                .unwrap(),
            vec![CellFillTessellation::Hexbin]
        );
        assert_eq!(
            xyta_cell_fill_tessellation(&xyta_one(
                FLAG_HEATMAP | FLAG_SHAPE | FLAG_HAS_GRID,
                1,
                3,
                &[0.0, 1.0, 2.0],
                b"",
                0,
                0
            ))
            .unwrap(),
            vec![CellFillTessellation::None]
        );
        assert_eq!(
            xyta_cell_fill_tessellation(&xyta_one(
                FLAG_HEATMAP | FLAG_TRUECOLOR | FLAG_SHAPE,
                2,
                2,
                &[],
                b"",
                0,
                0
            ))
            .unwrap(),
            vec![CellFillTessellation::None]
        );
        assert_eq!(
            xyta_cell_fill_tessellation(&xyta_one(
                FLAG_HEATMAP | FLAG_TRUECOLOR | FLAG_HAS_RGBA_GRID,
                0,
                0,
                &[],
                b"",
                0,
                1
            ))
            .unwrap(),
            vec![CellFillTessellation::Heatmap]
        );
        assert!(xyta_cell_fill_tessellation(b"XXXX").is_err());
    }
}
