//! Compact Figure→Scene product-row packing (M2 #271).
//!
//! Hosts pack authored kind, polar/cartesian coords, trace id, and the
//! canonical `x`/`y`/`x0`/`y0`/`x1`/`y1`/`base` columns as XYCL v1 against
//! an XYTT attach bundle. Rust owns XYPK construction, scatter-only
//! symbol/diameter, density domain-endpoint column rewrite, and
//! `pack_product_facts` so Python and Node cannot drift. Encoded Scene v31
//! is unchanged.
//!
//! #1006 / #1009: the product encoder passes a [`LineLodFrame`] read from the
//! Scene's own XYCF, and a cartesian `line` above `DECIMATION_THRESHOLD`
//! takes the browser payload's M4 tier here, in canonical f64 before
//! packing and step/curve expansion (dossier §28).

use crate::lod_plan::{
    payload_m4_indices, payload_tier, payload_visible_indices, screen_shape, PayloadIndexSel,
    MIN_SCREEN_DIM, PAYLOAD_KIND_LINE, PAYLOAD_TIER_DECIMATED,
};
use crate::scene::MAX_SCENE_MARKS;
use crate::scene_pack::{
    pack_product_facts, PackError, PackedSceneRow, XYPK_MAGIC, XYPK_V1_HEADER_BYTES, XYPK_VERSION,
};
use crate::scene_trace_attach::{XYTT_HEADER_BYTES, XYTT_MAGIC, XYTT_PREFIX_BYTES, XYTT_VERSION};
use crate::scene_trace_compile::XYTO_MAGIC;

pub const XYCL_MAGIC: &[u8; 4] = b"XYCL";
pub const XYCL_VERSION: u32 = 1;
pub const XYCL_HEADER_BYTES: usize = 16;
pub const XYCL_PREFIX_BYTES: usize = 48;
/// XYCL prefix byte 3 bit: a `segments` trace's `base` column carries graph
/// edge ends (`edge_route::EDGE_ENDS_STRIDE` values per segment) (#33). Rust
/// routes them into `PACK_EDGE_SEGMENT`.
pub const XYCL_EDGE_ENDS: u8 = 1 << 0;

const MAX_TRACES: usize = 4_096;
const MAX_KIND: usize = 32;
const COORDS_POLAR: u8 = 1;

/// Why an XYCL row-pack request was rejected. Discriminants are the C-ABI
/// error codes (returned negated by `xyg_scene_pack_trace_rows`).
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum TraceRowsCode {
    Length = 1,
    Version = 2,
    Limit = 3,
    Output = 4,
    NonFinite = 5,
    UnknownKind = 6,
    TraceCount = 7,
    Kind = 8,
    Coords = 9,
    /// A line above the decimation threshold cannot take the browser's M4
    /// tier (x not sorted ascending, or outside its axis binning space)
    /// (#1006). Only the product encoder decimates, so the stepwise C ABI
    /// never returns this code.
    Lod = 10,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct TraceRowsError {
    pub code: TraceRowsCode,
    pub index: u32,
}

impl TraceRowsError {
    fn new(code: TraceRowsCode, index: usize) -> Self {
        Self {
            code,
            index: index as u32,
        }
    }
}

struct AttachedTrace {
    diameter: f64,
    symbol: u16,
    authored_step: u16,
    fact_bits: u32,
    hex_dx: f64,
    hex_dy: f64,
    density_len: u32,
    grid_rows: u32,
    grid_cols: u32,
    rewrite: [f64; 4],
}

struct ColumnInput {
    kind: String,
    coords: u8,
    edge_ends: bool,
    trace_id: u64,
    x: Vec<f64>,
    y: Vec<f64>,
    x0: Vec<f64>,
    y0: Vec<f64>,
    x1: Vec<f64>,
    y1: Vec<f64>,
    base: Vec<f64>,
}

fn read_u16(bytes: &[u8], offset: usize) -> Result<u16, TraceRowsError> {
    Ok(u16::from_le_bytes(
        bytes
            .get(offset..offset + 2)
            .ok_or(TraceRowsError::new(TraceRowsCode::Length, 0))?
            .try_into()
            .map_err(|_| TraceRowsError::new(TraceRowsCode::Length, 0))?,
    ))
}

fn read_u32(bytes: &[u8], offset: usize) -> Result<u32, TraceRowsError> {
    Ok(u32::from_le_bytes(
        bytes
            .get(offset..offset + 4)
            .ok_or(TraceRowsError::new(TraceRowsCode::Length, 0))?
            .try_into()
            .map_err(|_| TraceRowsError::new(TraceRowsCode::Length, 0))?,
    ))
}

fn read_f64(bytes: &[u8], offset: usize) -> Result<f64, TraceRowsError> {
    Ok(f64::from_le_bytes(
        bytes
            .get(offset..offset + 8)
            .ok_or(TraceRowsError::new(TraceRowsCode::Length, 0))?
            .try_into()
            .map_err(|_| TraceRowsError::new(TraceRowsCode::Length, 0))?,
    ))
}

fn take<'a>(rest: &mut &'a [u8], n: usize, index: usize) -> Result<&'a [u8], TraceRowsError> {
    if rest.len() < n {
        return Err(TraceRowsError::new(TraceRowsCode::Length, index));
    }
    let (head, tail) = rest.split_at(n);
    *rest = tail;
    Ok(head)
}

fn f64_bytes_len(count: u32, index: usize) -> Result<usize, TraceRowsError> {
    (count as usize)
        .checked_mul(8)
        .ok_or(TraceRowsError::new(TraceRowsCode::Limit, index))
}

fn decode_f64s(bytes: &[u8], index: usize) -> Result<Vec<f64>, TraceRowsError> {
    if bytes.len() % 8 != 0 {
        return Err(TraceRowsError::new(TraceRowsCode::Length, index));
    }
    Ok(bytes
        .chunks_exact(8)
        .map(|chunk| f64::from_le_bytes(chunk.try_into().unwrap()))
        .collect())
}

fn pack_error(error: PackError, index: usize) -> TraceRowsError {
    let code = match error {
        PackError::Length => TraceRowsCode::Length,
        PackError::Version => TraceRowsCode::Version,
        PackError::Limit => TraceRowsCode::Limit,
        PackError::Output => TraceRowsCode::Output,
        PackError::NonFinite => TraceRowsCode::NonFinite,
        PackError::UnknownKind => TraceRowsCode::UnknownKind,
    };
    TraceRowsError::new(code, index)
}

fn parse_xytt(bytes: &[u8]) -> Result<Vec<AttachedTrace>, TraceRowsError> {
    if bytes.len() < XYTT_HEADER_BYTES || bytes.get(..4) != Some(&XYTT_MAGIC[..]) {
        return Err(TraceRowsError::new(TraceRowsCode::Length, 0));
    }
    if read_u32(bytes, 4)? != XYTT_VERSION {
        return Err(TraceRowsError::new(TraceRowsCode::Version, 0));
    }
    let n_traces = read_u32(bytes, 8)? as usize;
    if n_traces > MAX_TRACES {
        return Err(TraceRowsError::new(TraceRowsCode::Limit, 0));
    }
    let mut at = XYTT_HEADER_BYTES;
    let mut traces = Vec::with_capacity(n_traces);
    for index in 0..n_traces {
        if at
            .checked_add(XYTT_PREFIX_BYTES)
            .is_none_or(|end| end > bytes.len())
        {
            return Err(TraceRowsError::new(TraceRowsCode::Length, index));
        }
        if bytes.get(at..at + 4) != Some(&XYTO_MAGIC[..]) {
            return Err(TraceRowsError::new(TraceRowsCode::Length, index));
        }
        let diameter = read_f64(bytes, at + 24)?;
        let symbol = read_u16(bytes, at + 32)?;
        let authored_step = read_u16(bytes, at + 38)?;
        let fact_bits = read_u32(bytes, at + 40)?;
        let dash_count = read_u32(bytes, at + 44)? as usize;
        let marker_len = read_u32(bytes, at + 52)? as usize;
        let gradient_len = read_u32(bytes, at + 56)? as usize;
        let hex_dx = read_f64(bytes, at + 60)?;
        let hex_dy = read_f64(bytes, at + 68)?;
        let heatmap_len = read_u32(bytes, at + 160)? as usize;
        let density_len = read_u32(bytes, at + 164)?;
        let grid_rows = read_u32(bytes, at + 168)?;
        let grid_cols = read_u32(bytes, at + 172)?;
        let rewrite = [
            read_f64(bytes, at + 176)?,
            read_f64(bytes, at + 184)?,
            read_f64(bytes, at + 192)?,
            read_f64(bytes, at + 200)?,
        ];
        at += XYTT_PREFIX_BYTES;
        let skip = dash_count
            .checked_mul(8)
            .and_then(|n| n.checked_add(marker_len))
            .and_then(|n| n.checked_add(gradient_len))
            .and_then(|n| n.checked_add(heatmap_len))
            .and_then(|n| n.checked_add(density_len as usize))
            .ok_or(TraceRowsError::new(TraceRowsCode::Limit, index))?;
        if at.checked_add(skip).is_none_or(|end| end > bytes.len()) {
            return Err(TraceRowsError::new(TraceRowsCode::Length, index));
        }
        at += skip;
        traces.push(AttachedTrace {
            diameter,
            symbol,
            authored_step,
            fact_bits,
            hex_dx,
            hex_dy,
            density_len,
            grid_rows,
            grid_cols,
            rewrite,
        });
    }
    if at != bytes.len() {
        return Err(TraceRowsError::new(TraceRowsCode::Length, 0));
    }
    Ok(traces)
}

fn parse_column(bytes: &[u8], at: &mut usize, index: usize) -> Result<ColumnInput, TraceRowsError> {
    if at
        .checked_add(XYCL_PREFIX_BYTES)
        .is_none_or(|end| end > bytes.len())
    {
        return Err(TraceRowsError::new(TraceRowsCode::Length, index));
    }
    let prefix = &bytes[*at..*at + XYCL_PREFIX_BYTES];
    *at += XYCL_PREFIX_BYTES;
    let kind_len = u16::from_le_bytes(prefix[0..2].try_into().unwrap()) as usize;
    let coords = prefix[2];
    if coords > COORDS_POLAR {
        return Err(TraceRowsError::new(TraceRowsCode::Coords, index));
    }
    let column_flags = prefix[3];
    if column_flags & !XYCL_EDGE_ENDS != 0 {
        return Err(TraceRowsError::new(TraceRowsCode::Length, index));
    }
    let trace_id = u64::from_le_bytes(prefix[8..16].try_into().unwrap());
    let n_x = u32::from_le_bytes(prefix[16..20].try_into().unwrap());
    let n_y = u32::from_le_bytes(prefix[20..24].try_into().unwrap());
    let n_x0 = u32::from_le_bytes(prefix[24..28].try_into().unwrap());
    let n_y0 = u32::from_le_bytes(prefix[28..32].try_into().unwrap());
    let n_x1 = u32::from_le_bytes(prefix[32..36].try_into().unwrap());
    let n_y1 = u32::from_le_bytes(prefix[36..40].try_into().unwrap());
    let n_base = u32::from_le_bytes(prefix[40..44].try_into().unwrap());
    if kind_len == 0 || kind_len > MAX_KIND {
        return Err(TraceRowsError::new(TraceRowsCode::Kind, index));
    }
    let mut rest = bytes
        .get(*at..)
        .ok_or(TraceRowsError::new(TraceRowsCode::Length, index))?;
    let kind_bytes = take(&mut rest, kind_len, index)?;
    let kind = std::str::from_utf8(kind_bytes)
        .map_err(|_| TraceRowsError::new(TraceRowsCode::Kind, index))?
        .to_owned();
    if kind.contains('\0') {
        return Err(TraceRowsError::new(TraceRowsCode::Kind, index));
    }
    let x = take(&mut rest, f64_bytes_len(n_x, index)?, index)?;
    let y = take(&mut rest, f64_bytes_len(n_y, index)?, index)?;
    let x0 = take(&mut rest, f64_bytes_len(n_x0, index)?, index)?;
    let y0 = take(&mut rest, f64_bytes_len(n_y0, index)?, index)?;
    let x1 = take(&mut rest, f64_bytes_len(n_x1, index)?, index)?;
    let y1 = take(&mut rest, f64_bytes_len(n_y1, index)?, index)?;
    let base = take(&mut rest, f64_bytes_len(n_base, index)?, index)?;
    *at = bytes.len() - rest.len();
    Ok(ColumnInput {
        kind,
        coords,
        edge_ends: column_flags & XYCL_EDGE_ENDS != 0,
        trace_id,
        x: decode_f64s(x, index)?,
        y: decode_f64s(y, index)?,
        x0: decode_f64s(x0, index)?,
        y0: decode_f64s(y0, index)?,
        x1: decode_f64s(x1, index)?,
        y1: decode_f64s(y1, index)?,
        base: decode_f64s(base, index)?,
    })
}

/// Axis scale codes shared with XYCF (`0` linear, `1` log, `2` symlog).
const SCALE_LOG: u32 = 1;
const SCALE_SYMLOG: u32 = 2;

/// Static line M4 inputs (#1006), resolved from the Scene's own XYCF so a
/// decimated static line takes exactly the browser payload's first-paint
/// tier: the same `payload_tier`, the same `payload_m4_indices` kernel, the
/// same bucket count (the figure's CSS width clamped by `screen_shape`, the
/// browser's `_resolve_px_width`), and the same x window (the resolved x
/// axis domain, binned in axis coordinates on log/symlog axes).
#[derive(Clone, Copy, Debug, PartialEq)]
pub struct LineLodFrame {
    pub buckets: usize,
    pub x_kind: u32,
    pub x_lo: f64,
    pub x_hi: f64,
    pub x_constant: f64,
    pub y_log: bool,
}

impl LineLodFrame {
    pub fn new(
        viewport_width: f64,
        x_kind: u32,
        x_lo: f64,
        x_hi: f64,
        x_constant: f64,
        y_kind: u32,
    ) -> Self {
        // `as` truncates like Python `int(width)` and saturates non-finite
        // widths; `screen_shape` then clamps to [16, 4096].
        let width = if viewport_width.is_finite() {
            viewport_width as i32
        } else {
            0
        };
        let (buckets, _) = screen_shape(width, MIN_SCREEN_DIM);
        Self {
            buckets: buckets as usize,
            x_kind,
            x_lo: x_lo.min(x_hi),
            x_hi: x_lo.max(x_hi),
            x_constant,
            y_log: y_kind == SCALE_LOG,
        }
    }

    /// The browser's `_axis_coord` for the x axis (`binning_coords`).
    fn x_coord(&self, value: f64) -> f64 {
        match self.x_kind {
            SCALE_LOG => {
                if value > 0.0 {
                    value.log10()
                } else {
                    f64::NAN
                }
            }
            SCALE_SYMLOG => {
                let constant = if self.x_constant != 0.0 && !self.x_constant.is_nan() {
                    self.x_constant
                } else {
                    1.0
                };
                value.signum() * (value.abs() / constant).ln_1p()
            }
            _ => value,
        }
    }
}

/// Source rows a static `line` keeps under the browser's M4 tier, or `None`
/// when the browser ships it direct (at most `DECIMATION_THRESHOLD` points,
/// polar, or not a line) (#1006).
///
/// Mirrors `payload_trace_emit_materialize`'s `PAYLOAD_GATHER_M4` branch:
/// `payload_m4_indices` over the x window, then `payload_visible_indices`
/// with the decimated prefilter (log axes drop non-positive rows). Static
/// export additionally fails closed where the browser kernel's own
/// preconditions do not hold, instead of drawing an arbitrary subset:
/// non-finite x/y keep the shared `NonFinite` row reason (Scene encodes no
/// missing-data breaks and §19 forbids bridging a hole), and binning
/// coordinates that are not ascending fail as `Lod`.
fn line_m4_rows(
    input: &ColumnInput,
    lod: &LineLodFrame,
    index: usize,
) -> Result<Option<Vec<u32>>, TraceRowsError> {
    let n = input.x.len();
    if input.kind != "line"
        || input.coords == COORDS_POLAR
        || payload_tier(PAYLOAD_KIND_LINE, n as u64, false, -1, false, false)
            != Some(PAYLOAD_TIER_DECIMATED)
    {
        return Ok(None);
    }
    if input.y.len() != n {
        return Err(TraceRowsError::new(TraceRowsCode::Length, index));
    }
    if !input
        .x
        .iter()
        .chain(&input.y)
        .all(|value| value.is_finite())
    {
        return Err(TraceRowsError::new(TraceRowsCode::NonFinite, index));
    }
    let lod_error = TraceRowsError::new(TraceRowsCode::Lod, index);
    let (lo, hi) = (lod.x_lo, lod.x_hi);
    let mut bin_x = None;
    let (mut b0, mut b1) = (lo, hi);
    if lod.x_kind == SCALE_LOG || lod.x_kind == SCALE_SYMLOG {
        let (c0, c1) = (lod.x_coord(lo), lod.x_coord(hi));
        if c0.is_finite() && c1.is_finite() && c1 > c0 {
            bin_x = Some(
                input
                    .x
                    .iter()
                    .map(|&v| lod.x_coord(v))
                    .collect::<Vec<f64>>(),
            );
            (b0, b1) = (c0, c1);
        }
    }
    let keys = bin_x.as_deref().unwrap_or(&input.x);
    if !keys.iter().all(|value| value.is_finite()) || keys.windows(2).any(|w| w[1] < w[0]) {
        return Err(lod_error);
    }
    let (tier, mut keep) = payload_m4_indices(
        n as u64,
        false,
        &input.x,
        &input.y,
        lo,
        hi,
        lod.buckets,
        bin_x.as_deref(),
        b0,
        b1,
    )
    .ok_or(lod_error)?;
    if tier != PAYLOAD_TIER_DECIMATED {
        return Ok(None);
    }
    let x_log = lod.x_kind == SCALE_LOG;
    // Product rows are all on the primary y axis today (Scene v33 y2 rows
    // are not yet selected by the product encoder, #1032).
    let y_log = lod.y_log;
    if x_log || y_log {
        let xg: Vec<f64> = keep.iter().map(|&i| input.x[i as usize]).collect();
        let yg: Vec<f64> = keep.iter().map(|&i| input.y[i as usize]).collect();
        match payload_visible_indices(
            &xg, &yg, x_log, y_log, None, true, false, false, false, false,
        )
        .ok_or(lod_error)?
        {
            PayloadIndexSel::KeepAll => {}
            PayloadIndexSel::Indices(visible) => {
                keep = visible.iter().map(|&i| keep[i as usize]).collect();
            }
        }
    }
    Ok(Some(keep))
}

fn gather_rows(column: &mut Vec<f64>, n: usize, keep: &[u32]) {
    if column.len() == n {
        *column = keep.iter().map(|&i| column[i as usize]).collect();
    }
}

fn write_xypk(
    kind: &str,
    style_ref: u32,
    coords: u8,
    symbol: u8,
    authored_step: u8,
    facts: u8,
    trace_id: u64,
    diameter: f64,
    hex_dx: f64,
    hex_dy: f64,
    grid_rows: f64,
    grid_cols: f64,
) -> Vec<u8> {
    let mut out = Vec::with_capacity(XYPK_V1_HEADER_BYTES + kind.len());
    out.extend_from_slice(XYPK_MAGIC);
    out.extend_from_slice(&XYPK_VERSION.to_le_bytes());
    out.extend_from_slice(&style_ref.to_le_bytes());
    out.push(coords);
    out.push(symbol);
    out.push(authored_step);
    out.push(facts);
    out.extend_from_slice(&trace_id.to_le_bytes());
    out.extend_from_slice(&diameter.to_le_bytes());
    out.extend_from_slice(&hex_dx.to_le_bytes());
    out.extend_from_slice(&hex_dy.to_le_bytes());
    out.extend_from_slice(&grid_rows.to_le_bytes());
    out.extend_from_slice(&grid_cols.to_le_bytes());
    out.extend_from_slice(kind.as_bytes());
    out
}

/// Pack attached `XYTT` v1 plus authored `XYCL` v1 columns into Scene rows.
///
/// The stepwise C ABI packs every authored row; only the product encoder
/// decimates ([`pack_trace_rows_with_lod`]).
pub fn pack_trace_rows(
    attached: &[u8],
    columns: &[u8],
) -> Result<Vec<PackedSceneRow>, TraceRowsError> {
    pack_trace_rows_with_lod(attached, columns, None)
}

/// [`pack_trace_rows`] that also applies the browser's line M4 tier when the
/// product encoder supplies the Scene's [`LineLodFrame`] (#1006, dossier
/// §28). Lines at or below `DECIMATION_THRESHOLD` pack unchanged.
pub fn pack_trace_rows_with_lod(
    attached: &[u8],
    columns: &[u8],
    lod: Option<&LineLodFrame>,
) -> Result<Vec<PackedSceneRow>, TraceRowsError> {
    let traces = parse_xytt(attached)?;
    if columns.len() < XYCL_HEADER_BYTES || columns.get(..4) != Some(&XYCL_MAGIC[..]) {
        return Err(TraceRowsError::new(TraceRowsCode::Length, 0));
    }
    if read_u32(columns, 4)? != XYCL_VERSION {
        return Err(TraceRowsError::new(TraceRowsCode::Version, 0));
    }
    let n_traces = read_u32(columns, 8)? as usize;
    if n_traces != traces.len() {
        return Err(TraceRowsError::new(TraceRowsCode::TraceCount, 0));
    }
    if n_traces > MAX_TRACES {
        return Err(TraceRowsError::new(TraceRowsCode::Limit, 0));
    }
    let mut at = XYCL_HEADER_BYTES;
    let mut rows = Vec::new();
    for (index, attached) in traces.iter().enumerate() {
        let mut input = parse_column(columns, &mut at, index)?;
        if let Some(keep) = lod
            .map(|lod| line_m4_rows(&input, lod, index))
            .transpose()?
            .flatten()
        {
            let n = input.x.len();
            for column in [
                &mut input.x,
                &mut input.y,
                &mut input.x0,
                &mut input.y0,
                &mut input.x1,
                &mut input.y1,
                &mut input.base,
            ] {
                gather_rows(column, n, &keep);
            }
        }
        let mut symbol = attached.symbol as u8;
        let mut diameter = attached.diameter;
        if input.kind != "scatter" {
            symbol = 0;
            diameter = 0.0;
        }
        let (x, y) = if attached.density_len > 0 {
            (
                vec![attached.rewrite[0], attached.rewrite[1]],
                vec![attached.rewrite[2], attached.rewrite[3]],
            )
        } else {
            (input.x, input.y)
        };
        // Graph edge ends ride `base` (EDGE_ENDS_STRIDE per segment) into
        // PACK_EDGE_SEGMENT (#33).
        let mut fact_bits = attached.fact_bits as u8;
        if input.edge_ends {
            let n = input.x0.len();
            let expected = n
                .checked_mul(crate::edge_route::EDGE_ENDS_STRIDE)
                .ok_or(TraceRowsError::new(TraceRowsCode::Limit, index))?;
            if input.kind != "segments"
                || input.coords == COORDS_POLAR
                || input.base.len() != expected
            {
                return Err(TraceRowsError::new(TraceRowsCode::Length, index));
            }
            fact_bits |= crate::scene_pack::FACT_EDGE_ENDS;
        }
        let base = input.base.clone();
        let facts = write_xypk(
            &input.kind,
            index as u32,
            input.coords,
            symbol,
            attached.authored_step as u8,
            fact_bits,
            input.trace_id,
            diameter,
            attached.hex_dx,
            attached.hex_dy,
            f64::from(attached.grid_rows),
            f64::from(attached.grid_cols),
        );
        let packed = pack_product_facts(
            &facts, &x, &y, &input.x0, &input.y0, &input.x1, &input.y1, &base,
        )
        .map_err(|error| pack_error(error, index))?;
        rows.extend(packed);
    }
    if at != columns.len() {
        return Err(TraceRowsError::new(TraceRowsCode::Length, 0));
    }
    if rows.len() > MAX_SCENE_MARKS {
        return Err(TraceRowsError::new(TraceRowsCode::Limit, 0));
    }
    Ok(rows)
}

/// Canonical `x`/`y` columns from packed `XYCL` v1, for `loc="best"` occupancy.
pub(crate) fn xycl_xy_series(columns: &[u8]) -> Result<Vec<(Vec<f64>, Vec<f64>)>, TraceRowsError> {
    if columns.is_empty() {
        return Ok(Vec::new());
    }
    if columns.len() < XYCL_HEADER_BYTES || columns.get(..4) != Some(&XYCL_MAGIC[..]) {
        return Err(TraceRowsError::new(TraceRowsCode::Length, 0));
    }
    if read_u32(columns, 4)? != XYCL_VERSION {
        return Err(TraceRowsError::new(TraceRowsCode::Version, 0));
    }
    let n_traces = read_u32(columns, 8)? as usize;
    if n_traces > MAX_TRACES {
        return Err(TraceRowsError::new(TraceRowsCode::Limit, 0));
    }
    let mut at = XYCL_HEADER_BYTES;
    let mut series = Vec::with_capacity(n_traces);
    for index in 0..n_traces {
        let input = parse_column(columns, &mut at, index)?;
        series.push((input.x, input.y));
    }
    if at != columns.len() {
        return Err(TraceRowsError::new(TraceRowsCode::Length, 0));
    }
    Ok(series)
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::scene_trace_attach::{self, pack_trace_attach, FLAG_DENSITY};
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

    fn empty_attach(compiled: &[u8], n: u32) -> Vec<u8> {
        let mut facts = vec![0u8; scene_trace_attach::XYTA_HEADER_BYTES];
        facts[..4].copy_from_slice(scene_trace_attach::XYTA_MAGIC);
        facts[4..8].copy_from_slice(&scene_trace_attach::XYTA_VERSION.to_le_bytes());
        facts[8..12].copy_from_slice(&n.to_le_bytes());
        if n == 1 {
            facts.extend_from_slice(&vec![0u8; scene_trace_attach::XYTA_PREFIX_BYTES]);
        }
        pack_trace_attach(compiled, &facts).unwrap()
    }

    fn xycl_header(n: u32) -> Vec<u8> {
        let mut facts = vec![0u8; XYCL_HEADER_BYTES];
        facts[..4].copy_from_slice(XYCL_MAGIC);
        facts[4..8].copy_from_slice(&XYCL_VERSION.to_le_bytes());
        facts[8..12].copy_from_slice(&n.to_le_bytes());
        facts
    }

    fn push_f64s(out: &mut Vec<u8>, values: &[f64]) {
        for value in values {
            out.extend_from_slice(&value.to_le_bytes());
        }
    }

    fn xycl_trace(
        kind: &str,
        coords: u8,
        trace_id: u64,
        x: &[f64],
        y: &[f64],
        x0: &[f64],
        y0: &[f64],
        x1: &[f64],
        y1: &[f64],
        base: &[f64],
    ) -> Vec<u8> {
        let mut prefix = vec![0u8; XYCL_PREFIX_BYTES];
        prefix[0..2].copy_from_slice(&(kind.len() as u16).to_le_bytes());
        prefix[2] = coords;
        prefix[8..16].copy_from_slice(&trace_id.to_le_bytes());
        prefix[16..20].copy_from_slice(&(x.len() as u32).to_le_bytes());
        prefix[20..24].copy_from_slice(&(y.len() as u32).to_le_bytes());
        prefix[24..28].copy_from_slice(&(x0.len() as u32).to_le_bytes());
        prefix[28..32].copy_from_slice(&(y0.len() as u32).to_le_bytes());
        prefix[32..36].copy_from_slice(&(x1.len() as u32).to_le_bytes());
        prefix[36..40].copy_from_slice(&(y1.len() as u32).to_le_bytes());
        prefix[40..44].copy_from_slice(&(base.len() as u32).to_le_bytes());
        let mut out = prefix;
        out.extend_from_slice(kind.as_bytes());
        push_f64s(&mut out, x);
        push_f64s(&mut out, y);
        push_f64s(&mut out, x0);
        push_f64s(&mut out, y0);
        push_f64s(&mut out, x1);
        push_f64s(&mut out, y1);
        push_f64s(&mut out, base);
        out
    }

    fn line_columns(coords: u8, x: &[f64], y: &[f64]) -> Vec<u8> {
        let mut columns = xycl_header(1);
        columns.extend_from_slice(&xycl_trace(
            "line",
            coords,
            5,
            x,
            y,
            &[],
            &[],
            &[],
            &[],
            &[],
        ));
        columns
    }

    #[test]
    fn static_line_lod_is_the_browser_payload_m4_tier() {
        // #1006: the static row packer keeps exactly the rows the browser
        // payload's `payload_m4_indices` keeps for the same x window and
        // bucket count, in source order, before any expansion.
        let attached = empty_attach(&compile_kind("line"), 1);
        let n = 50_000usize;
        let x: Vec<f64> = (0..n).map(|i| i as f64 * 0.5).collect();
        let y: Vec<f64> = (0..n)
            .map(|i| ((i * 7_919) % 1_009) as f64 - (i % 97) as f64)
            .collect();
        let lod = LineLodFrame::new(720.0, 0, x[n - 1], 0.0, 1.0, 0);
        assert_eq!(lod.buckets, 720);
        assert_eq!((lod.x_lo, lod.x_hi), (0.0, x[n - 1]));
        let columns = line_columns(0, &x, &y);
        let rows = pack_trace_rows_with_lod(&attached, &columns, Some(&lod)).unwrap();
        let (tier, idx) =
            payload_m4_indices(n as u64, false, &x, &y, 0.0, x[n - 1], 720, None, 0.0, 0.0)
                .unwrap();
        assert_eq!(tier, PAYLOAD_TIER_DECIMATED);
        assert!(idx.len() <= 4 * 720 && idx.len() > 720);
        assert_eq!(rows.len(), idx.len());
        for (row, &i) in rows.iter().zip(&idx) {
            assert_eq!((row.x0, row.y0), (x[i as usize], y[i as usize]));
            assert_eq!(row.stable_id, 5);
        }

        // Without a frame (stepwise ABI), at or below the threshold, and on
        // polar coordinates every row packs unchanged.
        let full = pack_trace_rows(&attached, &columns).unwrap();
        assert_eq!(full.len(), n);
        let small = line_columns(0, &x[..10_000], &y[..10_000]);
        assert_eq!(
            pack_trace_rows_with_lod(&attached, &small, Some(&lod)).unwrap(),
            pack_trace_rows(&attached, &small).unwrap()
        );
        let radians: Vec<f64> = (0..n).map(|i| i as f64 / n as f64).collect();
        let polar = line_columns(COORDS_POLAR, &radians, &radians);
        let rows = pack_trace_rows_with_lod(&attached, &polar, Some(&lod)).unwrap();
        assert_eq!(rows.len(), n);

        // Wider viewports clamp like the browser's `screen_shape`.
        assert_eq!(
            LineLodFrame::new(9_000.0, 0, 0.0, 1.0, 1.0, 0).buckets,
            4_096
        );
        assert_eq!(LineLodFrame::new(4.0, 0, 0.0, 1.0, 1.0, 0).buckets, 16);
    }

    #[test]
    fn static_line_lod_bins_log_x_in_axis_coordinates() {
        let attached = empty_attach(&compile_kind("line"), 1);
        let n = 20_000usize;
        let x: Vec<f64> = (0..n).map(|i| 1.0 + i as f64).collect();
        let y: Vec<f64> = (0..n).map(|i| ((i * 31) % 211) as f64 + 1.0).collect();
        let lod = LineLodFrame::new(400.0, SCALE_LOG, 1.0, n as f64, 1.0, 0);
        let rows =
            pack_trace_rows_with_lod(&attached, &line_columns(0, &x, &y), Some(&lod)).unwrap();
        let bin: Vec<f64> = x.iter().map(|v| v.log10()).collect();
        let (_, idx) = payload_m4_indices(
            n as u64,
            false,
            &x,
            &y,
            1.0,
            n as f64,
            400,
            Some(&bin),
            0.0,
            (n as f64).log10(),
        )
        .unwrap();
        assert_eq!(rows.len(), idx.len());
        assert!(rows
            .iter()
            .zip(&idx)
            .all(|(row, &i)| row.x0 == x[i as usize] && row.y0 == y[i as usize]));
    }

    #[test]
    fn static_line_lod_fails_closed_outside_the_kernel_contract() {
        let attached = empty_attach(&compile_kind("line"), 1);
        let n = 10_001usize;
        let lod = LineLodFrame::new(320.0, 0, 0.0, n as f64, 1.0, 0);
        let x: Vec<f64> = (0..n).map(|i| i as f64).collect();
        let mut y = x.clone();
        y[17] = f64::NAN;
        let error =
            pack_trace_rows_with_lod(&attached, &line_columns(0, &x, &y), Some(&lod)).unwrap_err();
        assert_eq!(error.code, TraceRowsCode::NonFinite);
        let mut unsorted = x.clone();
        unsorted.swap(3, 4);
        let error =
            pack_trace_rows_with_lod(&attached, &line_columns(0, &unsorted, &x), Some(&lod))
                .unwrap_err();
        assert_eq!(error.code, TraceRowsCode::Lod);
        // A log x axis cannot bin non-positive x.
        let log = LineLodFrame::new(320.0, SCALE_LOG, 1.0, n as f64, 1.0, 0);
        let error =
            pack_trace_rows_with_lod(&attached, &line_columns(0, &x, &x), Some(&log)).unwrap_err();
        assert_eq!(error.code, TraceRowsCode::Lod);
    }

    #[test]
    fn empty_rows_emit_no_marks() {
        let attached = empty_attach(&empty_compile(), 0);
        let rows = pack_trace_rows(&attached, &xycl_header(0)).unwrap();
        assert!(rows.is_empty());
    }

    #[test]
    fn scatter_keeps_one_row_per_point() {
        let attached = empty_attach(&compile_kind("scatter"), 1);
        let mut columns = xycl_header(1);
        columns.extend_from_slice(&xycl_trace(
            "scatter",
            0,
            7,
            &[0.0, 1.0],
            &[2.0, 3.0],
            &[],
            &[],
            &[],
            &[],
            &[],
        ));
        let rows = pack_trace_rows(&attached, &columns).unwrap();
        assert_eq!(rows.len(), 2);
        assert!(rows.iter().all(|row| row.kind == 0 && row.stable_id == 7));
        assert!(rows
            .iter()
            .all(|row| row.style_ref == 0 && row.diameter == 4.0));
        assert_eq!(rows[0].x0, 0.0);
        assert_eq!(rows[0].y0, 2.0);
        assert_eq!(rows[1].x0, 1.0);
        assert_eq!(rows[1].y0, 3.0);
    }

    #[test]
    fn non_scatter_zeros_symbol_and_diameter() {
        let attached = empty_attach(&compile_kind("line"), 1);
        let mut columns = xycl_header(1);
        columns.extend_from_slice(&xycl_trace(
            "line",
            0,
            3,
            &[0.0, 1.0],
            &[0.0, 1.0],
            &[],
            &[],
            &[],
            &[],
            &[],
        ));
        let rows = pack_trace_rows(&attached, &columns).unwrap();
        assert_eq!(rows.len(), 2);
        assert!(rows
            .iter()
            .all(|row| row.symbol == 0 && row.diameter == 0.0 && row.kind == 1));
    }

    #[test]
    fn density_rewrite_overrides_host_columns() {
        let mut attach = vec![0u8; scene_trace_attach::XYTA_HEADER_BYTES];
        attach[..4].copy_from_slice(scene_trace_attach::XYTA_MAGIC);
        attach[4..8].copy_from_slice(&scene_trace_attach::XYTA_VERSION.to_le_bytes());
        attach[8..12].copy_from_slice(&1u32.to_le_bytes());
        let mut prefix = vec![0u8; scene_trace_attach::XYTA_PREFIX_BYTES];
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
        let attached = pack_trace_attach(&compile_kind("scatter"), &attach).unwrap();
        let density_len = u32::from_le_bytes(
            attached[XYTT_HEADER_BYTES + 164..XYTT_HEADER_BYTES + 168]
                .try_into()
                .unwrap(),
        );
        assert!(density_len > 0);
        let mut columns = xycl_header(1);
        columns.extend_from_slice(&xycl_trace(
            "scatter",
            0,
            9,
            &[100.0, 200.0, 300.0],
            &[100.0, 200.0, 300.0],
            &[],
            &[],
            &[],
            &[],
            &[],
        ));
        let rows = pack_trace_rows(&attached, &columns).unwrap();
        assert_eq!(rows.len(), 2);
        assert_eq!(rows[0].x0, 0.0);
        assert_eq!(rows[0].y0, 0.0);
        assert_eq!(rows[0].x1, 1.0);
        assert_eq!(rows[0].y1, 1.0);
        assert_eq!(rows[0].symbol, 0);
        assert_eq!(rows[0].expansion_mode, 10);
    }

    #[test]
    fn density_source_above_the_xyta_budget_bins_canonical_columns() {
        // #1006: a density scatter whose XYTA record omitted the x/y source
        // (over the 4 MiB record budget) still takes the density tier from
        // its canonical XYCL columns instead of one record per point.
        let mut attach = vec![0u8; scene_trace_attach::XYTA_HEADER_BYTES];
        attach[..4].copy_from_slice(scene_trace_attach::XYTA_MAGIC);
        attach[4..8].copy_from_slice(&scene_trace_attach::XYTA_VERSION.to_le_bytes());
        attach[8..12].copy_from_slice(&1u32.to_le_bytes());
        let mut prefix = vec![0u8; scene_trace_attach::XYTA_PREFIX_BYTES];
        prefix[..4].copy_from_slice(&FLAG_DENSITY.to_le_bytes());
        prefix[56..64].copy_from_slice(&0.0f64.to_le_bytes());
        prefix[64..72].copy_from_slice(&1.0f64.to_le_bytes());
        prefix[72..80].copy_from_slice(&0.0f64.to_le_bytes());
        prefix[80..88].copy_from_slice(&1.0f64.to_le_bytes());
        attach.extend_from_slice(&prefix);
        let mut columns = xycl_header(1);
        columns.extend_from_slice(&xycl_trace(
            "scatter",
            0,
            9,
            &[0.25, 0.75, 0.5],
            &[0.25, 0.75, 0.5],
            &[],
            &[],
            &[],
            &[],
            &[],
        ));
        let stepwise = pack_trace_attach(&compile_kind("scatter"), &attach).unwrap();
        assert_eq!(pack_trace_rows(&stepwise, &columns).unwrap().len(), 3);
        let attached = scene_trace_attach::pack_trace_attach_with_columns(
            &compile_kind("scatter"),
            &attach,
            &columns,
        )
        .unwrap();
        let rows = pack_trace_rows(&attached, &columns).unwrap();
        assert_eq!(rows.len(), 2);
        assert_eq!(rows[0].expansion_mode, 10);
    }

    #[test]
    fn count_mismatch_is_trace_count() {
        let attached = empty_attach(&empty_compile(), 0);
        let err = pack_trace_rows(&attached, &xycl_header(1)).unwrap_err();
        assert_eq!(err.code, TraceRowsCode::TraceCount);
    }

    #[test]
    fn polar_coords_above_one_is_coords_error() {
        let attached = empty_attach(&compile_kind("scatter"), 1);
        let mut columns = xycl_header(1);
        columns.extend_from_slice(&xycl_trace(
            "scatter",
            2,
            1,
            &[0.0],
            &[1.0],
            &[],
            &[],
            &[],
            &[],
            &[],
        ));
        let err = pack_trace_rows(&attached, &columns).unwrap_err();
        assert_eq!(err.code, TraceRowsCode::Coords);
    }
}
