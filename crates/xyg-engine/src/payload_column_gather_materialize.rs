//! Payload geometry column gather + offset ship (M2 Push 3B, ABI 320).
//!
//! Hosts marshal raw f64 trace columns, optional row ``sel``, and per-column
//! ship metadata; Rust gathers and encodes offset-f32 / f64 wire buffers.

use crate::kernels::{self, encode_f32_into, encoded_column_meta, scale_pins_offset};
use crate::payload_emit::{
    PAYLOAD_COL_SCALE_X, PAYLOAD_COL_SCALE_Y, PAYLOAD_COL_SHIP_F64, PAYLOAD_COL_SHIP_OFFSET,
    PAYLOAD_COL_SHIP_VALUES,
};

pub const PAYLOAD_COLUMN_GATHER_MATERIALIZE_MAX: usize = 8;
pub const PAYLOAD_COLUMN_MATERIALIZE_MAX_BYTES: usize = 1 << 28;

/// One geometry column to gather and ship.
#[derive(Clone, Copy, Debug)]
pub struct PayloadColumnMaterializeIn<'a> {
    pub ship_method: i32,
    pub ship_scale: i32,
    pub values: &'a [f64],
    pub col_min: f64,
    pub col_max: f64,
    pub kind: Option<&'a str>,
    /// ``Column.suggest_offset()`` for offset ship; ignored for ``ship_values``.
    pub sticky_offset: f64,
    /// Axis scale name: ``linear``, ``log``, ``symlog``, etc.
    pub axis_scale: &'a str,
}

/// One encoded geometry column returned to the host.
#[derive(Clone, Debug, PartialEq)]
pub struct PayloadColumnMaterializeOut {
    /// ``0`` = f32 offset geometry, ``1`` = canonical f64.
    pub dtype_code: i32,
    pub offset: f64,
    pub scale: f64,
    pub has_kind: i32,
    pub len: u32,
    pub bytes: Vec<u8>,
}

fn gather_f64(values: &[f64], sel: Option<&[u32]>) -> Result<Vec<f64>, i32> {
    let Some(sel) = sel else {
        return Ok(values.to_vec());
    };
    if sel.is_empty() {
        return Ok(Vec::new());
    }
    let mut out = Vec::with_capacity(sel.len());
    for &idx in sel {
        let i = idx as usize;
        if i >= values.len() {
            return Err(-1);
        }
        out.push(values[i]);
    }
    Ok(out)
}

fn min_max(values: &[f64]) -> (f64, f64) {
    if values.is_empty() {
        return (0.0, 0.0);
    }
    let mut lo = f64::INFINITY;
    let mut hi = f64::NEG_INFINITY;
    for &v in values {
        if v.is_finite() {
            lo = lo.min(v);
            hi = hi.max(v);
        }
    }
    if !lo.is_finite() || !hi.is_finite() {
        (0.0, 0.0)
    } else {
        (lo, hi)
    }
}

fn encode_offset_column(
    values: &[f64],
    col_min: f64,
    col_max: f64,
    kind: Option<&str>,
    sticky_offset: f64,
    axis_scale: &str,
) -> Result<(Vec<u8>, f64, f64, i32), i32> {
    let pin = scale_pins_offset(axis_scale);
    let offset = if pin {
        kernels::geometry_offset(true, col_min, col_max)
    } else {
        sticky_offset
    };
    let (meta_offset, scale, has_kind) = encoded_column_meta(offset, col_min, col_max, kind);
    let mut enc = vec![0f32; values.len()];
    encode_f32_into(values, meta_offset, scale, &mut enc);
    let bytes: Vec<u8> = enc
        .iter()
        .flat_map(|v| v.to_le_bytes())
        .collect();
    Ok((bytes, meta_offset, scale, i32::from(has_kind)))
}

fn encode_values_column(
    values: &[f64],
    kind: Option<&str>,
    axis_scale: &str,
) -> Result<(Vec<u8>, f64, f64, i32), i32> {
    let (lo, hi) = min_max(values);
    encode_offset_column(values, lo, hi, kind, 0.0, axis_scale)
}

/// Gather ``columns`` with optional ``sel`` and return encoded wire bytes.
///
/// Error codes: ``-1`` invalid args, ``-2`` output exceeds cap.
pub fn payload_column_gather_materialize(
    sel: Option<&[u32]>,
    columns: &[PayloadColumnMaterializeIn<'_>],
) -> Result<Vec<PayloadColumnMaterializeOut>, i32> {
    if columns.is_empty() || columns.len() > PAYLOAD_COLUMN_GATHER_MATERIALIZE_MAX {
        return Err(-1);
    }
    for col in columns {
        if col.ship_scale != PAYLOAD_COL_SCALE_X && col.ship_scale != PAYLOAD_COL_SCALE_Y {
            return Err(-1);
        }
        if col.values.is_empty() && sel.map(|s| !s.is_empty()).unwrap_or(false) {
            return Err(-1);
        }
    }
    let mut out = Vec::with_capacity(columns.len());
    for col in columns {
        let gathered = gather_f64(col.values, sel)?;
        let materialized = match col.ship_method {
            PAYLOAD_COL_SHIP_OFFSET => encode_offset_column(
                &gathered,
                col.col_min,
                col.col_max,
                col.kind,
                col.sticky_offset,
                col.axis_scale,
            )?,
            PAYLOAD_COL_SHIP_VALUES => {
                encode_values_column(&gathered, col.kind, col.axis_scale)?
            }
            PAYLOAD_COL_SHIP_F64 => {
                let bytes: Vec<u8> = gathered.iter().flat_map(|v| v.to_le_bytes()).collect();
                (bytes, 0.0, 1.0, 0)
            }
            _ => return Err(-1),
        };
        let (bytes, offset, scale, has_kind) = materialized;
        if bytes.len() > PAYLOAD_COLUMN_MATERIALIZE_MAX_BYTES {
            return Err(-2);
        }
        let len = match col.ship_method {
            PAYLOAD_COL_SHIP_F64 => gathered.len() as u32,
            _ => (bytes.len() / 4) as u32,
        };
        out.push(PayloadColumnMaterializeOut {
            dtype_code: if col.ship_method == PAYLOAD_COL_SHIP_F64 {
                1
            } else {
                0
            },
            offset,
            scale,
            has_kind,
            len,
            bytes,
        });
    }
    Ok(out)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn gathers_and_offset_encodes_xy() {
        let x = [0.0, 1.0, 2.0];
        let y = [10.0, 20.0, 30.0];
        let cols = [
            PayloadColumnMaterializeIn {
                ship_method: PAYLOAD_COL_SHIP_OFFSET,
                ship_scale: PAYLOAD_COL_SCALE_X,
                values: &x,
                col_min: 0.0,
                col_max: 2.0,
                kind: Some("float"),
                sticky_offset: 1.0,
                axis_scale: "linear",
            },
            PayloadColumnMaterializeIn {
                ship_method: PAYLOAD_COL_SHIP_OFFSET,
                ship_scale: PAYLOAD_COL_SCALE_Y,
                values: &y,
                col_min: 10.0,
                col_max: 30.0,
                kind: Some("float"),
                sticky_offset: 20.0,
                axis_scale: "linear",
            },
        ];
        let out = payload_column_gather_materialize(Some(&[0, 2]), &cols).unwrap();
        assert_eq!(out.len(), 2);
        assert_eq!(out[0].len, 2);
        assert_eq!(out[1].len, 2);
    }
}
