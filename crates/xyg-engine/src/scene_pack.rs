//! Compact Figure→Scene row packing (M2 #271).
//!
//! Hosts validate authoring (axis keys, hidden traces, density, style
//! allowlists) and pass literal columns plus kind/flags. Rust owns Scene
//! record kinds, stable-id splitting, expansion-mode assignment, heatmap
//! lattice framing, ribbon/triangle doubling, and finite-coordinate
//! rejection so Python and Node cannot drift on the packed row contract.

use crate::scene::MAX_SCENE_MARKS;

pub const PACKED_SCENE_ROW_BYTES: usize = 56;

pub const PACK_SCATTER: u8 = 0;
pub const PACK_LINE: u8 = 1;
pub const PACK_RECT: u8 = 2;
pub const PACK_BAND: u8 = 3;
pub const PACK_RIBBON: u8 = 4;
pub const PACK_TRIANGLE: u8 = 5;
pub const PACK_HEXBIN: u8 = 6;
pub const PACK_HEATMAP: u8 = 7;
pub const PACK_SEGMENT: u8 = 8;

pub const FLAG_STROKE_PERIMETER: u8 = 1 << 0;

const KIND_SCATTER: u8 = 0;
const KIND_POLYLINE: u8 = 1;
const KIND_RECT: u8 = 2;
const KIND_BAND: u8 = 3;
const KIND_POLYFILL: u8 = 4;

const EXP_NONE: u8 = 0;
const EXP_RIBBON: u8 = 4;
const EXP_HEX: u8 = 5;
const EXP_HEATMAP: u8 = 6;
const EXP_SEGMENT: u8 = 7;
const EXP_TRIANGLE: u8 = 8;

/// Why a pack request was rejected. Discriminants are the C-ABI error codes
/// (returned negated by `xyg_scene_pack_trace`).
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
#[allow(dead_code)] // Version is reserved for a future envelope; C ABI returns -2.
pub enum PackError {
    Length = 1,
    Version = 2,
    Limit = 3,
    Output = 4,
    NonFinite = 5,
}

/// One packed Scene row before `xyg_scene_batch_encode`.
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct PackedSceneRow {
    pub kind: u8,
    pub symbol: u8,
    pub expansion_mode: u8,
    pub style_ref: u32,
    pub stable_id: u64,
    pub diameter: f64,
    pub x0: f64,
    pub y0: f64,
    pub x1: f64,
    pub y1: f64,
}

impl PackedSceneRow {
    pub fn to_bytes(self) -> [u8; PACKED_SCENE_ROW_BYTES] {
        let mut out = [0u8; PACKED_SCENE_ROW_BYTES];
        out[0] = self.kind;
        out[1] = self.symbol;
        out[2] = self.expansion_mode;
        out[4..8].copy_from_slice(&self.style_ref.to_le_bytes());
        out[8..16].copy_from_slice(&self.stable_id.to_le_bytes());
        out[16..24].copy_from_slice(&self.diameter.to_le_bytes());
        out[24..32].copy_from_slice(&self.x0.to_le_bytes());
        out[32..40].copy_from_slice(&self.y0.to_le_bytes());
        out[40..48].copy_from_slice(&self.x1.to_le_bytes());
        out[48..56].copy_from_slice(&self.y1.to_le_bytes());
        out
    }
}

/// Authoring literals for one trace's geometry columns.
#[derive(Clone, Copy)]
pub struct TracePackInput<'a> {
    pub pack_kind: u8,
    pub flags: u8,
    pub step_mode: u8,
    pub symbol: u8,
    pub style_ref: u32,
    pub trace_id: u64,
    pub diameter: f64,
    pub extra0: f64,
    pub extra1: f64,
    pub columns: &'a [&'a [f64]],
}

fn require_cols<'a>(columns: &'a [&'a [f64]], count: usize) -> Result<&'a [&'a [f64]], PackError> {
    if columns.len() < count {
        return Err(PackError::Length);
    }
    let used = &columns[..count];
    if used.iter().any(|column| column.len() != used[0].len()) {
        return Err(PackError::Length);
    }
    Ok(used)
}

fn require_finite(columns: &[&[f64]]) -> Result<(), PackError> {
    if columns
        .iter()
        .any(|column| column.iter().any(|value| !value.is_finite()))
    {
        return Err(PackError::NonFinite);
    }
    Ok(())
}

fn split_id(trace_id: u64, index: usize) -> Result<u64, PackError> {
    let index = u64::try_from(index).map_err(|_| PackError::Limit)?;
    if index > u64::from(u32::MAX) {
        return Err(PackError::Limit);
    }
    Ok((trace_id << 32) | index)
}

fn push_row(out: &mut Vec<PackedSceneRow>, row: PackedSceneRow) -> Result<(), PackError> {
    if out.len() >= MAX_SCENE_MARKS {
        return Err(PackError::Limit);
    }
    out.push(row);
    Ok(())
}

/// Number of Scene rows one packed trace will emit.
pub fn packed_row_count(pack_kind: u8, n: usize) -> Result<usize, PackError> {
    let count = match pack_kind {
        PACK_SCATTER | PACK_LINE | PACK_RECT | PACK_BAND | PACK_HEXBIN | PACK_SEGMENT => n,
        PACK_RIBBON | PACK_TRIANGLE => n.checked_mul(2).ok_or(PackError::Limit)?,
        PACK_HEATMAP => 2,
        _ => return Err(PackError::Length),
    };
    if count > MAX_SCENE_MARKS {
        return Err(PackError::Limit);
    }
    Ok(count)
}

/// Pack one trace's columns into Scene rows (kind, id, coords, expansion).
pub fn pack_trace(input: TracePackInput<'_>) -> Result<Vec<PackedSceneRow>, PackError> {
    if input.flags & !FLAG_STROKE_PERIMETER != 0 {
        return Err(PackError::Length);
    }
    if input.step_mode > 3 {
        return Err(PackError::Length);
    }
    if input.pack_kind != PACK_LINE && input.step_mode != 0 {
        return Err(PackError::Length);
    }
    match input.pack_kind {
        PACK_SCATTER => pack_xy(input, KIND_SCATTER, input.symbol, input.diameter, EXP_NONE),
        PACK_LINE => pack_xy(input, KIND_POLYLINE, 0, 0.0, input.step_mode),
        PACK_RECT => pack_quad(input, KIND_RECT, 0, 0.0, EXP_NONE, false),
        PACK_SEGMENT => pack_quad(input, KIND_POLYLINE, 0, 0.0, EXP_SEGMENT, true),
        PACK_BAND => pack_band(input),
        PACK_RIBBON => pack_ribbon(input),
        PACK_TRIANGLE => pack_triangle(input),
        PACK_HEXBIN => pack_hexbin(input),
        PACK_HEATMAP => pack_heatmap(input),
        _ => Err(PackError::Length),
    }
}

fn pack_xy(
    input: TracePackInput<'_>,
    kind: u8,
    symbol: u8,
    diameter: f64,
    expansion: u8,
) -> Result<Vec<PackedSceneRow>, PackError> {
    let cols = require_cols(input.columns, 2)?;
    require_finite(cols)?;
    let mut out = Vec::with_capacity(cols[0].len());
    for index in 0..cols[0].len() {
        push_row(
            &mut out,
            PackedSceneRow {
                kind,
                symbol,
                expansion_mode: expansion,
                style_ref: input.style_ref,
                stable_id: input.trace_id,
                diameter,
                x0: cols[0][index],
                y0: cols[1][index],
                x1: 0.0,
                y1: 0.0,
            },
        )?;
    }
    Ok(out)
}

fn pack_quad(
    input: TracePackInput<'_>,
    kind: u8,
    symbol: u8,
    diameter: f64,
    expansion: u8,
    split_ids: bool,
) -> Result<Vec<PackedSceneRow>, PackError> {
    let cols = require_cols(input.columns, 4)?;
    require_finite(cols)?;
    let mut out = Vec::with_capacity(cols[0].len());
    for index in 0..cols[0].len() {
        let stable_id = if split_ids {
            split_id(input.trace_id, index)?
        } else {
            input.trace_id
        };
        push_row(
            &mut out,
            PackedSceneRow {
                kind,
                symbol,
                expansion_mode: expansion,
                style_ref: input.style_ref,
                stable_id,
                diameter,
                x0: cols[0][index],
                y0: cols[1][index],
                x1: cols[2][index],
                y1: cols[3][index],
            },
        )?;
    }
    Ok(out)
}

fn pack_band(input: TracePackInput<'_>) -> Result<Vec<PackedSceneRow>, PackError> {
    let cols = require_cols(input.columns, 3)?;
    require_finite(cols)?;
    let outline = if input.flags & FLAG_STROKE_PERIMETER != 0 {
        2
    } else {
        1
    };
    let mut out = Vec::with_capacity(cols[0].len());
    for index in 0..cols[0].len() {
        let x = cols[0][index];
        push_row(
            &mut out,
            PackedSceneRow {
                kind: KIND_BAND,
                symbol: outline,
                expansion_mode: EXP_NONE,
                style_ref: input.style_ref,
                stable_id: input.trace_id,
                diameter: 0.0,
                x0: x,
                y0: cols[1][index],
                x1: x,
                y1: cols[2][index],
            },
        )?;
    }
    Ok(out)
}

fn pack_ribbon(input: TracePackInput<'_>) -> Result<Vec<PackedSceneRow>, PackError> {
    let cols = require_cols(input.columns, 6)?;
    require_finite(cols)?;
    let mut out = Vec::with_capacity(cols[0].len().saturating_mul(2));
    for index in 0..cols[0].len() {
        let stable_id = split_id(input.trace_id, index)?;
        let x0 = cols[0][index];
        let x1 = cols[1][index];
        let source_lo = cols[2][index];
        let source_hi = cols[3][index];
        let target_lo = cols[4][index];
        let target_hi = cols[5][index];
        for (start_y, end_y) in [(source_hi, target_hi), (source_lo, target_lo)] {
            push_row(
                &mut out,
                PackedSceneRow {
                    kind: KIND_BAND,
                    symbol: 2,
                    expansion_mode: EXP_RIBBON,
                    style_ref: input.style_ref,
                    stable_id,
                    diameter: 0.0,
                    x0,
                    y0: start_y,
                    x1,
                    y1: end_y,
                },
            )?;
        }
    }
    Ok(out)
}

fn pack_triangle(input: TracePackInput<'_>) -> Result<Vec<PackedSceneRow>, PackError> {
    let cols = require_cols(input.columns, 6)?;
    require_finite(cols)?;
    let mut out = Vec::with_capacity(cols[0].len().saturating_mul(2));
    for index in 0..cols[0].len() {
        let stable_id = split_id(input.trace_id, index)?;
        push_row(
            &mut out,
            PackedSceneRow {
                kind: KIND_POLYFILL,
                symbol: 0,
                expansion_mode: EXP_TRIANGLE,
                style_ref: input.style_ref,
                stable_id,
                diameter: 0.0,
                x0: cols[0][index],
                y0: cols[1][index],
                x1: cols[2][index],
                y1: cols[3][index],
            },
        )?;
        push_row(
            &mut out,
            PackedSceneRow {
                kind: KIND_POLYFILL,
                symbol: 0,
                expansion_mode: EXP_TRIANGLE,
                style_ref: input.style_ref,
                stable_id,
                diameter: 0.0,
                x0: cols[4][index],
                y0: cols[5][index],
                x1: 0.0,
                y1: 0.0,
            },
        )?;
    }
    Ok(out)
}

fn pack_hexbin(input: TracePackInput<'_>) -> Result<Vec<PackedSceneRow>, PackError> {
    let cols = require_cols(input.columns, 2)?;
    require_finite(cols)?;
    if !input.extra0.is_finite()
        || !input.extra1.is_finite()
        || input.extra0 <= 0.0
        || input.extra1 <= 0.0
    {
        return Err(PackError::NonFinite);
    }
    let mut out = Vec::with_capacity(cols[0].len());
    for index in 0..cols[0].len() {
        push_row(
            &mut out,
            PackedSceneRow {
                kind: KIND_POLYFILL,
                symbol: 0,
                expansion_mode: EXP_HEX,
                style_ref: input.style_ref,
                stable_id: split_id(input.trace_id, index)?,
                diameter: 0.0,
                x0: cols[0][index],
                y0: cols[1][index],
                x1: input.extra0,
                y1: input.extra1,
            },
        )?;
    }
    Ok(out)
}

fn pack_heatmap(input: TracePackInput<'_>) -> Result<Vec<PackedSceneRow>, PackError> {
    let cols = require_cols(input.columns, 4)?;
    if cols[0].len() != 1 {
        return Err(PackError::Length);
    }
    require_finite(cols)?;
    let rows = input.extra0;
    let cols_n = input.extra1;
    if !(rows.is_finite() && cols_n.is_finite() && rows >= 1.0 && cols_n >= 1.0)
        || rows.fract() != 0.0
        || cols_n.fract() != 0.0
    {
        return Err(PackError::NonFinite);
    }
    let x0 = cols[0][0];
    let y0 = cols[1][0];
    let x1 = cols[2][0];
    let y1 = cols[3][0];
    if x0 >= x1 || y0 >= y1 {
        return Err(PackError::NonFinite);
    }
    let mut out = Vec::with_capacity(2);
    push_row(
        &mut out,
        PackedSceneRow {
            kind: KIND_RECT,
            symbol: 0,
            expansion_mode: EXP_HEATMAP,
            style_ref: input.style_ref,
            stable_id: input.trace_id,
            diameter: rows,
            x0,
            y0,
            x1,
            y1,
        },
    )?;
    push_row(
        &mut out,
        PackedSceneRow {
            kind: KIND_RECT,
            symbol: 0,
            expansion_mode: EXP_HEATMAP,
            style_ref: input.style_ref,
            stable_id: input.trace_id,
            diameter: cols_n,
            x0: 0.0,
            y0: 0.0,
            x1: 0.0,
            y1: 0.0,
        },
    )?;
    Ok(out)
}

/// Encode packed rows into the C-ABI output buffer. Returns the row count.
pub fn encode_packed_rows(rows: &[PackedSceneRow], out: &mut [u8]) -> Result<i32, PackError> {
    let needed = rows
        .len()
        .checked_mul(PACKED_SCENE_ROW_BYTES)
        .ok_or(PackError::Limit)?;
    if out.len() < needed {
        return Err(PackError::Output);
    }
    for (index, row) in rows.iter().enumerate() {
        let start = index * PACKED_SCENE_ROW_BYTES;
        out[start..start + PACKED_SCENE_ROW_BYTES].copy_from_slice(&row.to_bytes());
    }
    i32::try_from(rows.len()).map_err(|_| PackError::Limit)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn scatter_keeps_one_row_per_point() {
        let x = [0.0, 1.0];
        let y = [2.0, 3.0];
        let rows = pack_trace(TracePackInput {
            pack_kind: PACK_SCATTER,
            flags: 0,
            step_mode: 0,
            symbol: 4,
            style_ref: 1,
            trace_id: 7,
            diameter: 6.0,
            extra0: 0.0,
            extra1: 0.0,
            columns: &[&x, &y],
        })
        .unwrap();
        assert_eq!(rows.len(), 2);
        assert_eq!(rows[1].kind, KIND_SCATTER);
        assert_eq!(rows[1].symbol, 4);
        assert_eq!(rows[1].stable_id, 7);
        assert_eq!(rows[1].diameter, 6.0);
        assert_eq!(
            (rows[1].x0, rows[1].y0, rows[1].x1, rows[1].y1),
            (1.0, 3.0, 0.0, 0.0)
        );
    }

    #[test]
    fn ribbon_emits_upper_then_lower_with_split_ids() {
        let x0 = [0.0];
        let x1 = [1.0];
        let y0 = [2.0];
        let y1 = [4.0];
        let tx = [3.0];
        let ty = [5.0];
        let rows = pack_trace(TracePackInput {
            pack_kind: PACK_RIBBON,
            flags: 0,
            step_mode: 0,
            symbol: 0,
            style_ref: 0,
            trace_id: 1,
            diameter: 0.0,
            extra0: 0.0,
            extra1: 0.0,
            columns: &[&x0, &x1, &y0, &y1, &tx, &ty],
        })
        .unwrap();
        assert_eq!(rows.len(), 2);
        assert_eq!(rows[0].expansion_mode, EXP_RIBBON);
        assert_eq!(rows[0].stable_id, (1 << 32) | 0);
        assert_eq!((rows[0].y0, rows[0].y1), (4.0, 5.0));
        assert_eq!((rows[1].y0, rows[1].y1), (2.0, 3.0));
    }

    #[test]
    fn heatmap_frames_extent_then_shape() {
        let x0 = [1.0];
        let y0 = [2.0];
        let x1 = [3.0];
        let y1 = [4.0];
        let rows = pack_trace(TracePackInput {
            pack_kind: PACK_HEATMAP,
            flags: 0,
            step_mode: 0,
            symbol: 0,
            style_ref: 9,
            trace_id: 11,
            diameter: 0.0,
            extra0: 2.0,
            extra1: 3.0,
            columns: &[&x0, &y0, &x1, &y1],
        })
        .unwrap();
        assert_eq!(rows.len(), 2);
        assert_eq!(rows[0].diameter, 2.0);
        assert_eq!(rows[1].diameter, 3.0);
        assert_eq!(rows[0].stable_id, 11);
        assert_eq!(rows[1].expansion_mode, EXP_HEATMAP);
        assert_eq!(
            (rows[1].x0, rows[1].y0, rows[1].x1, rows[1].y1),
            (0.0, 0.0, 0.0, 0.0)
        );
    }

    #[test]
    fn nonfinite_coordinates_fail_closed() {
        let x = [0.0, f64::NAN];
        let y = [1.0, 2.0];
        assert_eq!(
            pack_trace(TracePackInput {
                pack_kind: PACK_LINE,
                flags: 0,
                step_mode: 0,
                symbol: 0,
                style_ref: 0,
                trace_id: 0,
                diameter: 0.0,
                extra0: 0.0,
                extra1: 0.0,
                columns: &[&x, &y],
            }),
            Err(PackError::NonFinite)
        );
    }
}
