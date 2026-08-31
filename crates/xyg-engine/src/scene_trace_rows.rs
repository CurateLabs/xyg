//! Compact Figure→Scene product-row packing (M2 #271).
//!
//! Hosts pack authored kind, polar/cartesian coords, trace id, and the
//! canonical `x`/`y`/`x0`/`y0`/`x1`/`y1`/`base` columns as XYCL v1 against
//! an XYTT attach bundle. Rust owns XYPK construction, scatter-only
//! symbol/diameter, density domain-endpoint column rewrite, and
//! `pack_product_facts` so Python and Node cannot drift. Encoded Scene v31
//! is unchanged.

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
pub fn pack_trace_rows(
    attached: &[u8],
    columns: &[u8],
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
        let input = parse_column(columns, &mut at, index)?;
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
        let facts = write_xypk(
            &input.kind,
            index as u32,
            input.coords,
            symbol,
            attached.authored_step as u8,
            attached.fact_bits as u8,
            input.trace_id,
            diameter,
            attached.hex_dx,
            attached.hex_dy,
            f64::from(attached.grid_rows),
            f64::from(attached.grid_cols),
        );
        let packed = pack_product_facts(
            &facts,
            &x,
            &y,
            &input.x0,
            &input.y0,
            &input.x1,
            &input.y1,
            &input.base,
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
