//! Compact Figure→Scene row packing (M2 #271).
//!
//! Hosts validate authoring (axis keys, hidden traces, density, style
//! allowlists) and pass literal columns plus product kind/flags. Rust owns
//! product-kind → pack-kind mapping, Scene record kinds, stable-id splitting,
//! expansion-mode assignment, heatmap lattice framing, ribbon/triangle
//! doubling, rule/band/marker domain expansion, and finite-coordinate
//! rejection so Python and Node cannot drift on the packed row contract.
//! ABI 140 maps line `step_mode=4` onto expansion `CurveFlatten=11`.
//! ABI 141 maps band `step_mode=4` onto expansion `BandFlatten=12`.
//! ABI 142 admits cartesian mean-color density as XYHP paint kind 4 on the
//! existing `DensityBlit` Image blit (no new pack kind).
//! ABI 144 admits cartesian `error_band(curve="smooth")` on that same
//! `BandFlatten` mapping; polar `curve="smooth"` line/area/error_band pack as
//! identity chords (no `step_mode=4`).
//! ABI 145 admits constant `marker_path` via an XYMP extras sidecar;
//! tessellation is Scene-owned after pixel mapping (no new pack kind).
//! ABI 146 admits constant mark `fill` linear-gradients via an XYGR extras
//! sidecar (no new pack kind); encoded Scene keeps XYGR.
//! ABI 147 owns product packing facts from packed XYPK v1: hosts pass authored
//! kind, coords, step, curve-smooth, stroke-perimeter, density/heatmap paint
//! presence, hex pitch, and grid shape; Rust resolves flags, `step_mode`, and
//! extra0/extra1 so Python and Node cannot drift on cartesian-vs-polar smooth
//! or painted-vs-lattice heatmap dispatch. ABI 148 lives in
//! `scene_annotations.rs`: XYAF v1 facts pack wrap/text/arrow/callout/rule
//! routing so those families cannot drift. ABI 149 lives in
//! `scene_heatmap.rs`: XYHF v1 facts pack heatmap/density XYHP kind routing
//! so painted-lattice sidecars cannot drift. ABI 150 lives in
//! `scene_extras.rs`: XYSS v1 facts pack XYDS/XYLC/XYMP/XYGR layout, concat
//! order, omit-empty, and XYEX wrapping so extras cannot drift. ABI 151 lives
//! in `scene_density.rs`: Scene density blit owns `bin_2d`, `density_log_u8`,
//! optional mean-color, and XYDE wrapping. ABI 152 owns public-export
//! XYEP layout, kind/step/annotation codes, and flag derivation from packed
//! XYEF v1.

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
pub const PACK_HEATMAP_PAINTED: u8 = 9;
pub const PACK_DENSITY_BLIT: u8 = 10;

pub const FLAG_STROKE_PERIMETER: u8 = 1 << 0;
pub const FLAG_HEATMAP_PAINTED: u8 = 1 << 1;
pub const FLAG_DENSITY_BLIT: u8 = 1 << 2;
const PACK_FLAGS: u8 = FLAG_STROKE_PERIMETER | FLAG_HEATMAP_PAINTED | FLAG_DENSITY_BLIT;

pub const XYPK_MAGIC: &[u8; 4] = b"XYPK";
pub const XYPK_VERSION: u32 = 1;
pub const XYPK_V1_HEADER_BYTES: usize = 64;
pub const FACT_STROKE_PERIMETER: u8 = 1 << 0;
pub const FACT_CURVE_SMOOTH: u8 = 1 << 1;
pub const FACT_DENSITY_PLANE: u8 = 1 << 2;
pub const FACT_HEATMAP_PAINT: u8 = 1 << 3;
const FACT_BITS: u8 =
    FACT_STROKE_PERIMETER | FACT_CURVE_SMOOTH | FACT_DENSITY_PLANE | FACT_HEATMAP_PAINT;
pub const COORDS_CARTESIAN: u8 = 0;
pub const COORDS_POLAR: u8 = 1;

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
const EXP_HEATMAP_PAINTED: u8 = 9;
const EXP_DENSITY_BLIT: u8 = 10;
const EXP_CURVE_FLATTEN: u8 = 11;
const EXP_BAND_FLATTEN: u8 = 12;

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
    UnknownKind = 6,
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

/// Canonical host envelope for one product-kind trace.
///
/// Column slots are `x`, `y`, `x0`, `y0`, `x1`, `y1`, `base`. Unused slots
/// may be empty. Rust maps `kind` plus flags onto `pack_trace` column order.
#[derive(Clone, Copy)]
pub struct ProductPackInput<'a> {
    pub kind: &'a str,
    pub flags: u8,
    pub step_mode: u8,
    pub symbol: u8,
    pub style_ref: u32,
    pub trace_id: u64,
    pub diameter: f64,
    pub extra0: f64,
    pub extra1: f64,
    pub x: &'a [f64],
    pub y: &'a [f64],
    pub x0: &'a [f64],
    pub y0: &'a [f64],
    pub x1: &'a [f64],
    pub y1: &'a [f64],
    pub base: &'a [f64],
}

/// Resolved packing fields from one XYPK v1 envelope.
#[derive(Clone, Copy, Debug, PartialEq)]
pub struct ProductFacts<'a> {
    pub kind: &'a str,
    pub flags: u8,
    pub step_mode: u8,
    pub symbol: u8,
    pub style_ref: u32,
    pub trace_id: u64,
    pub diameter: f64,
    pub extra0: f64,
    pub extra1: f64,
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
        PACK_HEATMAP | PACK_HEATMAP_PAINTED | PACK_DENSITY_BLIT => 2,
        _ => return Err(PackError::Length),
    };
    if count > MAX_SCENE_MARKS {
        return Err(PackError::Limit);
    }
    Ok(count)
}

/// Map a public product kind plus packing flags to a compact pack kind.
pub fn resolve_pack_kind(kind: &str, flags: u8) -> Result<u8, PackError> {
    if flags & !PACK_FLAGS != 0 {
        return Err(PackError::Length);
    }
    let painted = flags & FLAG_HEATMAP_PAINTED != 0;
    let density = flags & FLAG_DENSITY_BLIT != 0;
    if painted && density {
        return Err(PackError::Length);
    }
    let pack_kind = match kind {
        "scatter" => {
            if density {
                PACK_DENSITY_BLIT
            } else {
                PACK_SCATTER
            }
        }
        "line" => PACK_LINE,
        "bar" | "column" | "histogram" | "violin" | "box" => PACK_RECT,
        "area" | "error_band" => PACK_BAND,
        "ribbon" => PACK_RIBBON,
        "triangle_mesh" => PACK_TRIANGLE,
        "hexbin" => PACK_HEXBIN,
        "heatmap" => {
            if painted {
                PACK_HEATMAP_PAINTED
            } else {
                PACK_HEATMAP
            }
        }
        "segments" | "errorbar" | "stem" | "contour" | "box_whisker" | "box_median" => PACK_SEGMENT,
        _ => return Err(PackError::UnknownKind),
    };
    if painted && pack_kind != PACK_HEATMAP_PAINTED {
        return Err(PackError::Length);
    }
    if density && pack_kind != PACK_DENSITY_BLIT {
        return Err(PackError::Length);
    }
    Ok(pack_kind)
}

/// Pack one product-kind trace from the canonical host column envelope.
pub fn pack_product(input: ProductPackInput<'_>) -> Result<Vec<PackedSceneRow>, PackError> {
    let pack_kind = resolve_pack_kind(input.kind, input.flags)?;
    let flags = input.flags & FLAG_STROKE_PERIMETER;
    let pack = |columns: &[&[f64]]| {
        pack_trace(TracePackInput {
            pack_kind,
            flags,
            step_mode: input.step_mode,
            symbol: input.symbol,
            style_ref: input.style_ref,
            trace_id: input.trace_id,
            diameter: input.diameter,
            extra0: input.extra0,
            extra1: input.extra1,
            columns,
        })
    };
    match pack_kind {
        PACK_SCATTER | PACK_LINE | PACK_HEXBIN => {
            require_used(&[input.x, input.y])?;
            pack(&[input.x, input.y])
        }
        PACK_RECT | PACK_SEGMENT => {
            require_used(&[input.x0, input.y0, input.x1, input.y1])?;
            pack(&[input.x0, input.y0, input.x1, input.y1])
        }
        PACK_BAND => {
            require_used(&[input.x, input.y, input.base])?;
            pack(&[input.x, input.y, input.base])
        }
        PACK_RIBBON => {
            require_used(&[input.x0, input.x1, input.y0, input.y1, input.x, input.y])?;
            pack(&[input.x0, input.x1, input.y0, input.y1, input.x, input.y])
        }
        PACK_TRIANGLE => {
            require_used(&[input.x0, input.y0, input.x1, input.y1, input.x, input.y])?;
            pack(&[input.x0, input.y0, input.x1, input.y1, input.x, input.y])
        }
        PACK_HEATMAP | PACK_HEATMAP_PAINTED | PACK_DENSITY_BLIT => {
            let extent = heatmap_extent_columns(&input)?;
            pack(&[
                extent[0].as_slice(),
                extent[1].as_slice(),
                extent[2].as_slice(),
                extent[3].as_slice(),
            ])
        }
        _ => Err(PackError::Length),
    }
}

fn read_u32_at(bytes: &[u8], at: usize) -> Result<u32, PackError> {
    let slice = bytes.get(at..at + 4).ok_or(PackError::Length)?;
    Ok(u32::from_le_bytes(
        slice.try_into().map_err(|_| PackError::Length)?,
    ))
}

fn read_u64_at(bytes: &[u8], at: usize) -> Result<u64, PackError> {
    let slice = bytes.get(at..at + 8).ok_or(PackError::Length)?;
    Ok(u64::from_le_bytes(
        slice.try_into().map_err(|_| PackError::Length)?,
    ))
}

fn read_f64_at(bytes: &[u8], at: usize) -> Result<f64, PackError> {
    let slice = bytes.get(at..at + 8).ok_or(PackError::Length)?;
    Ok(f64::from_le_bytes(
        slice.try_into().map_err(|_| PackError::Length)?,
    ))
}

/// Parse XYPK v1 and resolve flags, step_mode, and extras from authored facts.
///
/// Header is 64 bytes; remaining UTF-8 is the product kind name.
pub fn parse_product_facts(bytes: &[u8]) -> Result<ProductFacts<'_>, PackError> {
    if bytes.len() < XYPK_V1_HEADER_BYTES || bytes.get(..4) != Some(&XYPK_MAGIC[..]) {
        return Err(PackError::Length);
    }
    if read_u32_at(bytes, 4)? != XYPK_VERSION {
        return Err(PackError::Version);
    }
    let style_ref = read_u32_at(bytes, 8)?;
    let coords = bytes[12];
    let mut symbol = bytes[13];
    let authored_step = bytes[14];
    let facts = bytes[15];
    if coords > COORDS_POLAR || facts & !FACT_BITS != 0 || authored_step > 3 {
        return Err(PackError::Length);
    }
    let trace_id = read_u64_at(bytes, 16)?;
    let mut diameter = read_f64_at(bytes, 24)?;
    let hex_dx = read_f64_at(bytes, 32)?;
    let hex_dy = read_f64_at(bytes, 40)?;
    let grid_rows = read_f64_at(bytes, 48)?;
    let grid_cols = read_f64_at(bytes, 56)?;
    let kind =
        std::str::from_utf8(&bytes[XYPK_V1_HEADER_BYTES..]).map_err(|_| PackError::Length)?;
    if kind.is_empty() || kind.len() > 32 || kind.contains('\0') {
        return Err(PackError::Length);
    }
    let density = facts & FACT_DENSITY_PLANE != 0;
    if density {
        symbol = 0;
        diameter = 0.0;
    }
    let mut flags = 0u8;
    if facts & FACT_STROKE_PERIMETER != 0 && matches!(kind, "area" | "error_band") {
        flags |= FLAG_STROKE_PERIMETER;
    }
    if facts & FACT_HEATMAP_PAINT != 0 {
        flags |= FLAG_HEATMAP_PAINTED;
    }
    if density {
        flags |= FLAG_DENSITY_BLIT;
    }
    let mut step_mode = authored_step;
    if authored_step == 0
        && facts & FACT_CURVE_SMOOTH != 0
        && coords == COORDS_CARTESIAN
        && matches!(kind, "line" | "area" | "error_band")
    {
        step_mode = 4;
    }
    let (extra0, extra1) = if kind == "hexbin" {
        (hex_dx, hex_dy)
    } else if kind == "heatmap" || density {
        (grid_rows, grid_cols)
    } else {
        (0.0, 0.0)
    };
    Ok(ProductFacts {
        kind,
        flags,
        step_mode,
        symbol,
        style_ref,
        trace_id,
        diameter,
        extra0,
        extra1,
    })
}

/// Pack one product-kind trace from packed XYPK facts plus canonical columns.
pub fn pack_product_facts(
    facts: &[u8],
    x: &[f64],
    y: &[f64],
    x0: &[f64],
    y0: &[f64],
    x1: &[f64],
    y1: &[f64],
    base: &[f64],
) -> Result<Vec<PackedSceneRow>, PackError> {
    let parsed = parse_product_facts(facts)?;
    pack_product(ProductPackInput {
        kind: parsed.kind,
        flags: parsed.flags,
        step_mode: parsed.step_mode,
        symbol: parsed.symbol,
        style_ref: parsed.style_ref,
        trace_id: parsed.trace_id,
        diameter: parsed.diameter,
        extra0: parsed.extra0,
        extra1: parsed.extra1,
        x,
        y,
        x0,
        y0,
        x1,
        y1,
        base,
    })
}

fn require_used<'a>(columns: &'a [&'a [f64]]) -> Result<&'a [&'a [f64]], PackError> {
    let used = require_cols(columns, columns.len())?;
    if used[0].is_empty() {
        return Err(PackError::Length);
    }
    Ok(used)
}

fn heatmap_extent_columns(input: &ProductPackInput<'_>) -> Result<[Vec<f64>; 4], PackError> {
    let (x0, y0, x1, y1) = if input.x.len() == 2 && input.y.len() == 2 {
        (input.x[0], input.y[0], input.x[1], input.y[1])
    } else if input.x0.len() == 1
        && input.y0.len() == 1
        && input.x1.len() == 1
        && input.y1.len() == 1
    {
        (input.x0[0], input.y0[0], input.x1[0], input.y1[0])
    } else {
        return Err(PackError::Length);
    };
    Ok([vec![x0], vec![y0], vec![x1], vec![y1]])
}

/// Pack one trace's columns into Scene rows (kind, id, coords, expansion).
pub fn pack_trace(input: TracePackInput<'_>) -> Result<Vec<PackedSceneRow>, PackError> {
    if input.flags & !FLAG_STROKE_PERIMETER != 0 {
        return Err(PackError::Length);
    }
    if input.step_mode > 4 {
        return Err(PackError::Length);
    }
    if input.step_mode != 0 && input.pack_kind != PACK_LINE && input.pack_kind != PACK_BAND {
        return Err(PackError::Length);
    }
    if input.pack_kind == PACK_BAND && input.step_mode != 0 && input.step_mode != 4 {
        return Err(PackError::Length);
    }
    match input.pack_kind {
        PACK_SCATTER => pack_xy(input, KIND_SCATTER, input.symbol, input.diameter, EXP_NONE),
        PACK_LINE => {
            let expansion = if input.step_mode == 4 {
                EXP_CURVE_FLATTEN
            } else {
                input.step_mode
            };
            pack_xy(input, KIND_POLYLINE, 0, 0.0, expansion)
        }
        PACK_RECT => pack_quad(input, KIND_RECT, 0, 0.0, EXP_NONE, false),
        PACK_SEGMENT => pack_quad(input, KIND_POLYLINE, 0, 0.0, EXP_SEGMENT, true),
        PACK_BAND => pack_band(input),
        PACK_RIBBON => pack_ribbon(input),
        PACK_TRIANGLE => pack_triangle(input),
        PACK_HEXBIN => pack_hexbin(input),
        PACK_HEATMAP => pack_heatmap(input, EXP_HEATMAP),
        PACK_HEATMAP_PAINTED => pack_heatmap(input, EXP_HEATMAP_PAINTED),
        PACK_DENSITY_BLIT => pack_heatmap(input, EXP_DENSITY_BLIT),
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
    let expansion = if input.step_mode == 4 {
        EXP_BAND_FLATTEN
    } else {
        EXP_NONE
    };
    let mut out = Vec::with_capacity(cols[0].len());
    for index in 0..cols[0].len() {
        let x = cols[0][index];
        push_row(
            &mut out,
            PackedSceneRow {
                kind: KIND_BAND,
                symbol: outline,
                expansion_mode: expansion,
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

fn pack_heatmap(
    input: TracePackInput<'_>,
    expansion: u8,
) -> Result<Vec<PackedSceneRow>, PackError> {
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
            expansion_mode: expansion,
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
            expansion_mode: expansion,
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

pub const ANN_MARK_ROW_BYTES: usize = 40;
pub const ANN_KIND_RULE: u8 = 1;
pub const ANN_KIND_BAND: u8 = 2;
pub const ANN_KIND_MARKER: u8 = 3;
const ANN_AXIS_X: u8 = 0;
const ANN_AXIS_Y: u8 = 1;
const ANN_ID_PREFIX: u64 = 0x5859_0000_0000_0000;

/// One authored rule/band/marker before domain expansion.
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct AnnotationMarkInput {
    pub kind: u8,
    pub axis: u8,
    pub symbol: u8,
    pub style_ref: u32,
    pub index: u32,
    pub value0: f64,
    pub value1: f64,
    pub size: f64,
}

fn annotation_stable_id(tag: u8, index: u32) -> u64 {
    ANN_ID_PREFIX | (u64::from(tag) << 40) | u64::from(index)
}

fn parse_annotation_mark_row(bytes: &[u8]) -> Result<AnnotationMarkInput, PackError> {
    if bytes.len() != ANN_MARK_ROW_BYTES {
        return Err(PackError::Length);
    }
    if bytes[3] != 0 || bytes[12..16] != [0, 0, 0, 0] {
        return Err(PackError::Length);
    }
    Ok(AnnotationMarkInput {
        kind: bytes[0],
        axis: bytes[1],
        symbol: bytes[2],
        style_ref: u32::from_le_bytes(bytes[4..8].try_into().unwrap()),
        index: u32::from_le_bytes(bytes[8..12].try_into().unwrap()),
        value0: f64::from_le_bytes(bytes[16..24].try_into().unwrap()),
        value1: f64::from_le_bytes(bytes[24..32].try_into().unwrap()),
        size: f64::from_le_bytes(bytes[32..40].try_into().unwrap()),
    })
}

/// Parse a packed `ANN_MARK_ROW_BYTES` table.
pub fn parse_annotation_mark_rows(bytes: &[u8]) -> Result<Vec<AnnotationMarkInput>, PackError> {
    if bytes.len() % ANN_MARK_ROW_BYTES != 0 {
        return Err(PackError::Length);
    }
    bytes
        .chunks_exact(ANN_MARK_ROW_BYTES)
        .map(parse_annotation_mark_row)
        .collect()
}

fn push_ann_row(
    out: &mut Vec<PackedSceneRow>,
    kind: u8,
    symbol: u8,
    style_ref: u32,
    stable_id: u64,
    diameter: f64,
    x0: f64,
    y0: f64,
    x1: f64,
    y1: f64,
) -> Result<(), PackError> {
    if ![x0, y0, x1, y1, diameter]
        .iter()
        .all(|value| value.is_finite())
    {
        return Err(PackError::NonFinite);
    }
    push_row(
        out,
        PackedSceneRow {
            kind,
            symbol,
            expansion_mode: EXP_NONE,
            style_ref,
            stable_id,
            diameter,
            x0,
            y0,
            x1,
            y1,
        },
    )
}

/// Expand authored rule/band/marker scalars across the primary axis domains
/// into ordinary Scene polyline/rect/scatter rows. Hosts pack kind, axis,
/// style ref, index, and scalars; Rust owns tags, domain spanning, and
/// finite rejection.
pub fn pack_annotation_marks(
    rows: &[AnnotationMarkInput],
    x0: f64,
    x1: f64,
    y0: f64,
    y1: f64,
) -> Result<Vec<PackedSceneRow>, PackError> {
    if ![x0, x1, y0, y1].iter().all(|value| value.is_finite()) {
        return Err(PackError::NonFinite);
    }
    let mut out = Vec::new();
    for row in rows {
        match row.kind {
            ANN_KIND_RULE => {
                if row.axis != ANN_AXIS_X && row.axis != ANN_AXIS_Y {
                    return Err(PackError::Length);
                }
                let stable_id = annotation_stable_id(1, row.index);
                let (ax, ay, bx, by) = if row.axis == ANN_AXIS_X {
                    (row.value0, y0, row.value0, y1)
                } else {
                    (x0, row.value0, x1, row.value0)
                };
                push_ann_row(
                    &mut out,
                    KIND_POLYLINE,
                    0,
                    row.style_ref,
                    stable_id,
                    0.0,
                    ax,
                    ay,
                    0.0,
                    0.0,
                )?;
                push_ann_row(
                    &mut out,
                    KIND_POLYLINE,
                    0,
                    row.style_ref,
                    stable_id,
                    0.0,
                    bx,
                    by,
                    0.0,
                    0.0,
                )?;
            }
            ANN_KIND_BAND => {
                if row.axis != ANN_AXIS_X && row.axis != ANN_AXIS_Y {
                    return Err(PackError::Length);
                }
                let tag = if row.axis == ANN_AXIS_Y { 4 } else { 2 };
                let stable_id = annotation_stable_id(tag, row.index);
                let (ax, ay, bx, by) = if row.axis == ANN_AXIS_X {
                    (row.value0, y0, row.value1, y1)
                } else {
                    (x0, row.value0, x1, row.value1)
                };
                push_ann_row(
                    &mut out,
                    KIND_RECT,
                    0,
                    row.style_ref,
                    stable_id,
                    0.0,
                    ax,
                    ay,
                    bx,
                    by,
                )?;
            }
            ANN_KIND_MARKER => {
                if !row.size.is_finite() || row.size <= 0.0 {
                    return Err(PackError::Length);
                }
                let stable_id = annotation_stable_id(3, row.index);
                push_ann_row(
                    &mut out,
                    KIND_SCATTER,
                    row.symbol,
                    row.style_ref,
                    stable_id,
                    row.size,
                    row.value0,
                    row.value1,
                    0.0,
                    0.0,
                )?;
            }
            _ => return Err(PackError::Length),
        }
    }
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
    fn painted_heatmap_frames_extent_with_painted_mode() {
        let x0 = [1.0];
        let y0 = [2.0];
        let x1 = [3.0];
        let y1 = [4.0];
        let rows = pack_trace(TracePackInput {
            pack_kind: PACK_HEATMAP_PAINTED,
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
        assert_eq!(rows[0].expansion_mode, EXP_HEATMAP_PAINTED);
        assert_eq!(rows[1].expansion_mode, EXP_HEATMAP_PAINTED);
        assert_eq!(rows[0].diameter, 2.0);
        assert_eq!(rows[1].diameter, 3.0);
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

    #[test]
    fn smooth_line_packs_curve_flatten_expansion() {
        let x = [0.0, 1.0, 2.0];
        let y = [0.0, 1.0, 0.5];
        let rows = pack_trace(TracePackInput {
            pack_kind: PACK_LINE,
            flags: 0,
            step_mode: 4,
            symbol: 0,
            style_ref: 0,
            trace_id: 11,
            diameter: 0.0,
            extra0: 0.0,
            extra1: 0.0,
            columns: &[&x, &y],
        })
        .unwrap();
        assert_eq!(rows.len(), 3);
        assert!(rows
            .iter()
            .all(|row| row.expansion_mode == EXP_CURVE_FLATTEN && row.kind == KIND_POLYLINE));
        assert_eq!(
            pack_trace(TracePackInput {
                pack_kind: PACK_LINE,
                flags: 0,
                step_mode: 5,
                symbol: 0,
                style_ref: 0,
                trace_id: 0,
                diameter: 0.0,
                extra0: 0.0,
                extra1: 0.0,
                columns: &[&x, &y],
            }),
            Err(PackError::Length)
        );
    }

    #[test]
    fn smooth_area_packs_band_flatten_expansion() {
        let x = [0.0, 1.0, 2.0];
        let y = [0.0, 1.0, 0.5];
        let base = [0.0, 0.0, 0.0];
        let rows = pack_trace(TracePackInput {
            pack_kind: PACK_BAND,
            flags: 0,
            step_mode: 4,
            symbol: 0,
            style_ref: 0,
            trace_id: 11,
            diameter: 0.0,
            extra0: 0.0,
            extra1: 0.0,
            columns: &[&x, &y, &base],
        })
        .unwrap();
        assert_eq!(rows.len(), 3);
        assert!(rows.iter().all(|row| {
            row.expansion_mode == EXP_BAND_FLATTEN
                && row.kind == KIND_BAND
                && row.x0 == row.x1
                && row.symbol == 1
        }));
        assert_eq!(
            pack_trace(TracePackInput {
                pack_kind: PACK_BAND,
                flags: 0,
                step_mode: 1,
                symbol: 0,
                style_ref: 0,
                trace_id: 0,
                diameter: 0.0,
                extra0: 0.0,
                extra1: 0.0,
                columns: &[&x, &y, &base],
            }),
            Err(PackError::Length)
        );
    }

    fn ann_row(
        kind: u8,
        axis: u8,
        symbol: u8,
        style_ref: u32,
        index: u32,
        value0: f64,
        value1: f64,
        size: f64,
    ) -> AnnotationMarkInput {
        AnnotationMarkInput {
            kind,
            axis,
            symbol,
            style_ref,
            index,
            value0,
            value1,
            size,
        }
    }

    #[test]
    fn rule_spans_the_opposite_axis_domain() {
        let rows = pack_annotation_marks(
            &[ann_row(ANN_KIND_RULE, ANN_AXIS_X, 0, 3, 7, 1.5, 0.0, 0.0)],
            0.0,
            4.0,
            10.0,
            20.0,
        )
        .unwrap();
        assert_eq!(rows.len(), 2);
        assert_eq!(rows[0].kind, KIND_POLYLINE);
        assert_eq!(rows[0].style_ref, 3);
        assert_eq!(rows[0].stable_id, ANN_ID_PREFIX | (1 << 40) | 7);
        assert_eq!(
            (rows[0].x0, rows[0].y0, rows[1].x0, rows[1].y0),
            (1.5, 10.0, 1.5, 20.0)
        );
    }

    #[test]
    fn y_band_uses_tag_four_and_spans_x_domain() {
        let rows = pack_annotation_marks(
            &[ann_row(ANN_KIND_BAND, ANN_AXIS_Y, 0, 1, 2, 3.0, 5.0, 0.0)],
            0.0,
            10.0,
            -1.0,
            1.0,
        )
        .unwrap();
        assert_eq!(rows.len(), 1);
        assert_eq!(rows[0].kind, KIND_RECT);
        assert_eq!(rows[0].stable_id, ANN_ID_PREFIX | (4 << 40) | 2);
        assert_eq!(
            (rows[0].x0, rows[0].y0, rows[0].x1, rows[0].y1),
            (0.0, 3.0, 10.0, 5.0)
        );
    }

    #[test]
    fn marker_keeps_authored_point_size_and_symbol() {
        let rows = pack_annotation_marks(
            &[ann_row(ANN_KIND_MARKER, 0, 4, 8, 9, 1.0, 2.0, 6.0)],
            0.0,
            1.0,
            0.0,
            1.0,
        )
        .unwrap();
        assert_eq!(rows.len(), 1);
        assert_eq!(rows[0].kind, KIND_SCATTER);
        assert_eq!(rows[0].symbol, 4);
        assert_eq!(rows[0].diameter, 6.0);
        assert_eq!(rows[0].stable_id, ANN_ID_PREFIX | (3 << 40) | 9);
        assert_eq!((rows[0].x0, rows[0].y0), (1.0, 2.0));
    }

    #[test]
    fn annotation_marks_reject_bad_kind_and_nonfinite_domain() {
        assert_eq!(
            pack_annotation_marks(&[ann_row(9, 0, 0, 0, 0, 0.0, 0.0, 1.0)], 0.0, 1.0, 0.0, 1.0),
            Err(PackError::Length)
        );
        assert_eq!(
            pack_annotation_marks(
                &[ann_row(ANN_KIND_RULE, 0, 0, 0, 0, 0.0, 0.0, 0.0)],
                0.0,
                f64::NAN,
                0.0,
                1.0
            ),
            Err(PackError::NonFinite)
        );
    }

    #[test]
    fn product_kind_maps_heatmap_paint_flag() {
        assert_eq!(resolve_pack_kind("scatter", 0).unwrap(), PACK_SCATTER);
        assert_eq!(resolve_pack_kind("column", 0).unwrap(), PACK_RECT);
        assert_eq!(resolve_pack_kind("contour", 0).unwrap(), PACK_SEGMENT);
        assert_eq!(resolve_pack_kind("heatmap", 0).unwrap(), PACK_HEATMAP);
        assert_eq!(
            resolve_pack_kind("heatmap", FLAG_HEATMAP_PAINTED).unwrap(),
            PACK_HEATMAP_PAINTED
        );
        assert_eq!(
            resolve_pack_kind("line", FLAG_HEATMAP_PAINTED),
            Err(PackError::Length)
        );
        assert_eq!(
            resolve_pack_kind("scatter", FLAG_DENSITY_BLIT).unwrap(),
            PACK_DENSITY_BLIT
        );
        assert_eq!(
            resolve_pack_kind("heatmap", FLAG_DENSITY_BLIT),
            Err(PackError::Length)
        );
        assert_eq!(
            resolve_pack_kind("scatter", FLAG_HEATMAP_PAINTED | FLAG_DENSITY_BLIT),
            Err(PackError::Length)
        );
        assert_eq!(resolve_pack_kind("density", 0), Err(PackError::UnknownKind));
    }

    #[test]
    fn pack_product_scatter_matches_pack_trace() {
        let x = [0.0, 1.0];
        let y = [2.0, 3.0];
        let packed = pack_product(ProductPackInput {
            kind: "scatter",
            flags: 0,
            step_mode: 0,
            symbol: 4,
            style_ref: 1,
            trace_id: 7,
            diameter: 6.0,
            extra0: 0.0,
            extra1: 0.0,
            x: &x,
            y: &y,
            x0: &[],
            y0: &[],
            x1: &[],
            y1: &[],
            base: &[],
        })
        .unwrap();
        let direct = pack_trace(TracePackInput {
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
        assert_eq!(packed, direct);
    }

    #[test]
    fn pack_product_heatmap_reads_range_endpoints() {
        let x = [1.0, 3.0];
        let y = [2.0, 4.0];
        let rows = pack_product(ProductPackInput {
            kind: "heatmap",
            flags: FLAG_HEATMAP_PAINTED,
            step_mode: 0,
            symbol: 0,
            style_ref: 9,
            trace_id: 11,
            diameter: 0.0,
            extra0: 2.0,
            extra1: 3.0,
            x: &x,
            y: &y,
            x0: &[],
            y0: &[],
            x1: &[],
            y1: &[],
            base: &[],
        })
        .unwrap();
        assert_eq!(rows.len(), 2);
        assert_eq!(rows[0].expansion_mode, EXP_HEATMAP_PAINTED);
        assert_eq!(rows[0].diameter, 2.0);
        assert_eq!(rows[1].diameter, 3.0);
        assert_eq!(
            (rows[0].x0, rows[0].y0, rows[0].x1, rows[0].y1),
            (1.0, 2.0, 3.0, 4.0)
        );
    }

    #[test]
    fn pack_product_density_blit_uses_extent_envelope() {
        let x0 = [0.0];
        let y0 = [1.0];
        let x1 = [2.0];
        let y1 = [3.0];
        let rows = pack_product(ProductPackInput {
            kind: "scatter",
            flags: FLAG_DENSITY_BLIT,
            step_mode: 0,
            symbol: 0,
            style_ref: 0,
            trace_id: 4,
            diameter: 0.0,
            extra0: 384.0,
            extra1: 512.0,
            x: &[],
            y: &[],
            x0: &x0,
            y0: &y0,
            x1: &x1,
            y1: &y1,
            base: &[],
        })
        .unwrap();
        assert_eq!(rows.len(), 2);
        assert_eq!(rows[0].kind, KIND_RECT);
        assert_eq!(rows[0].expansion_mode, EXP_DENSITY_BLIT);
        assert_eq!(rows[0].diameter, 384.0);
        assert_eq!(rows[1].diameter, 512.0);
        assert_eq!(
            (rows[0].x0, rows[0].y0, rows[0].x1, rows[0].y1),
            (0.0, 1.0, 2.0, 3.0)
        );
    }

    #[test]
    fn pack_product_ribbon_remaps_canonical_envelope() {
        let x0 = [0.0];
        let x1 = [1.0];
        let y0 = [2.0];
        let y1 = [4.0];
        let x = [3.0];
        let y = [5.0];
        let packed = pack_product(ProductPackInput {
            kind: "ribbon",
            flags: 0,
            step_mode: 0,
            symbol: 0,
            style_ref: 0,
            trace_id: 1,
            diameter: 0.0,
            extra0: 0.0,
            extra1: 0.0,
            x: &x,
            y: &y,
            x0: &x0,
            y0: &y0,
            x1: &x1,
            y1: &y1,
            base: &[],
        })
        .unwrap();
        assert_eq!(packed.len(), 2);
        assert_eq!(packed[0].expansion_mode, EXP_RIBBON);
        assert_eq!((packed[0].y0, packed[0].y1), (4.0, 5.0));
        assert_eq!((packed[1].y0, packed[1].y1), (2.0, 3.0));
    }

    #[test]
    fn pack_product_rejects_empty_required_columns() {
        assert_eq!(
            pack_product(ProductPackInput {
                kind: "bar",
                flags: 0,
                step_mode: 0,
                symbol: 0,
                style_ref: 0,
                trace_id: 0,
                diameter: 0.0,
                extra0: 0.0,
                extra1: 0.0,
                x: &[],
                y: &[],
                x0: &[0.0, 1.0],
                y0: &[0.0, 0.0],
                x1: &[],
                y1: &[1.0, 2.0],
                base: &[],
            }),
            Err(PackError::Length)
        );
    }

    fn xypk_bytes(
        kind: &str,
        style_ref: u32,
        coords: u8,
        symbol: u8,
        step: u8,
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
        out.push(step);
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

    #[test]
    fn product_facts_apply_cartesian_smooth_and_ignore_polar() {
        let cartesian_bytes = xypk_bytes(
            "line",
            3,
            COORDS_CARTESIAN,
            0,
            0,
            FACT_CURVE_SMOOTH,
            9,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
        );
        let cartesian = parse_product_facts(&cartesian_bytes).unwrap();
        assert_eq!(cartesian.step_mode, 4);
        assert_eq!(cartesian.flags, 0);
        let polar_bytes = xypk_bytes(
            "line",
            3,
            COORDS_POLAR,
            0,
            0,
            FACT_CURVE_SMOOTH,
            9,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
        );
        let polar = parse_product_facts(&polar_bytes).unwrap();
        assert_eq!(polar.step_mode, 0);
        let stepped_bytes = xypk_bytes(
            "line",
            1,
            COORDS_CARTESIAN,
            0,
            1,
            FACT_CURVE_SMOOTH,
            2,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
        );
        let stepped = parse_product_facts(&stepped_bytes).unwrap();
        assert_eq!(stepped.step_mode, 1);
    }

    #[test]
    fn product_facts_select_heatmap_paint_hex_and_density_extras() {
        let painted_bytes = xypk_bytes(
            "heatmap",
            4,
            COORDS_CARTESIAN,
            0,
            0,
            FACT_HEATMAP_PAINT,
            8,
            0.0,
            0.0,
            0.0,
            3.0,
            5.0,
        );
        let painted = parse_product_facts(&painted_bytes).unwrap();
        assert_eq!(painted.flags, FLAG_HEATMAP_PAINTED);
        assert_eq!((painted.extra0, painted.extra1), (3.0, 5.0));
        let hex_bytes = xypk_bytes(
            "hexbin",
            0,
            COORDS_CARTESIAN,
            0,
            0,
            0,
            1,
            0.0,
            0.5,
            0.25,
            9.0,
            9.0,
        );
        let hex = parse_product_facts(&hex_bytes).unwrap();
        assert_eq!((hex.extra0, hex.extra1), (0.5, 0.25));
        let density_bytes = xypk_bytes(
            "scatter",
            2,
            COORDS_CARTESIAN,
            4,
            0,
            FACT_DENSITY_PLANE,
            7,
            6.0,
            0.0,
            0.0,
            384.0,
            512.0,
        );
        let density = parse_product_facts(&density_bytes).unwrap();
        assert_eq!(density.flags, FLAG_DENSITY_BLIT);
        assert_eq!(density.symbol, 0);
        assert_eq!(density.diameter, 0.0);
        assert_eq!((density.extra0, density.extra1), (384.0, 512.0));
    }

    #[test]
    fn pack_product_facts_flattens_cartesian_smooth_line() {
        let x = [0.0, 1.0, 2.0];
        let y = [0.0, 1.0, 0.0];
        let facts = xypk_bytes(
            "line",
            1,
            COORDS_CARTESIAN,
            0,
            0,
            FACT_CURVE_SMOOTH,
            11,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
        );
        let rows = pack_product_facts(&facts, &x, &y, &[], &[], &[], &[], &[]).unwrap();
        assert_eq!(rows.len(), 3);
        assert!(rows
            .iter()
            .all(|row| row.expansion_mode == EXP_CURVE_FLATTEN));
        assert!(rows
            .iter()
            .all(|row| row.style_ref == 1 && row.stable_id == 11));
    }
}
