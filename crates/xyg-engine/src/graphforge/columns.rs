//! Typed extraction from validated Arrow columns. Every reader checks the
//! column's Arrow type first and reports `GF_RESULT_SCHEMA_MISMATCH` with the
//! field name and actual type; values never appear in diagnostics.

use super::{parse_uuid_text, GfError, GfResult, Uuid};
use crate::arrow_ipc::{Array, Column, DataType};

fn mismatch(column: &Column<'_, '_>, expected: &str) -> GfError {
    GfError::new(
        "GF_RESULT_SCHEMA_MISMATCH",
        format!(
            "field \"{}\" is {}; expected {expected}",
            column.field.name,
            column.field.type_name()
        ),
    )
    .with_field(&column.field.name)
}

fn uuid_at(array: &Array<'_>, row: usize, utf8: bool) -> Option<Option<Uuid>> {
    if !array.is_valid(row) {
        return Some(None);
    }
    if utf8 {
        let text = std::str::from_utf8(array.var(row)?).ok()?;
        return parse_uuid_text(text).map(Some);
    }
    Some(Some(array.fixed(row)?.try_into().ok()?))
}

/// UUIDs from `FixedSizeBinary(16)`, or canonical hyphenated `Utf8` text when
/// `allow_text` (flat base tables written by hand or older exporters).
/// Nulls stay `None`; malformed text is `GF_RESULT_UUID_INVALID`.
pub fn uuids(column: &Column<'_, '_>, allow_text: bool) -> GfResult<Vec<Option<Uuid>>> {
    let utf8 = match column.field.data_type {
        DataType::FixedSizeBinary(16) => false,
        DataType::Utf8 { .. } if allow_text => true,
        _ => return Err(mismatch(column, "FixedSizeBinary(16) UUIDs")),
    };
    let mut out = Vec::with_capacity(column.len());
    column.for_each::<GfError>(|array, row| {
        let value = uuid_at(array, row, utf8).ok_or_else(|| {
            GfError::new(
                "GF_RESULT_UUID_INVALID",
                format!("field \"{}\" holds a malformed UUID", column.field.name),
            )
            .with_field(&column.field.name)
        })?;
        out.push(value);
        Ok(())
    })?;
    Ok(out)
}

/// Numeric values as f64 (floats of any width, integers of any width).
pub fn f64s(column: &Column<'_, '_>) -> GfResult<Vec<Option<f64>>> {
    let decode: fn(&[u8]) -> f64 = match column.field.data_type {
        DataType::Float { bits: 64 } => |b| f64::from_le_bytes(b.try_into().unwrap()),
        DataType::Float { bits: 32 } => |b| f64::from(f32::from_le_bytes(b.try_into().unwrap())),
        DataType::Float { bits: 16 } => |b| half_to_f64(u16::from_le_bytes(b.try_into().unwrap())),
        DataType::Int { signed: true, .. } => |b| sign_extend(b) as f64,
        DataType::Int { signed: false, .. } => |b| zero_extend(b) as f64,
        _ => return Err(mismatch(column, "a numeric type")),
    };
    let mut out = Vec::with_capacity(column.len());
    column.for_each::<GfError>(|array, row| {
        out.push(if array.is_valid(row) {
            Some(decode(array.fixed(row).unwrap()))
        } else {
            None
        });
        Ok(())
    })?;
    Ok(out)
}

/// Integer values as i64; unsigned values above `i64::MAX` fail closed.
pub fn i64s(column: &Column<'_, '_>) -> GfResult<Vec<Option<i64>>> {
    let DataType::Int { signed, .. } = column.field.data_type else {
        return Err(mismatch(column, "an integer type"));
    };
    let mut out = Vec::with_capacity(column.len());
    column.for_each::<GfError>(|array, row| {
        if !array.is_valid(row) {
            out.push(None);
            return Ok(());
        }
        let bytes = array.fixed(row).unwrap();
        let value = if signed {
            sign_extend(bytes)
        } else {
            i64::try_from(zero_extend(bytes)).map_err(|_| {
                GfError::new(
                    "GF_RESULT_VALUE_RANGE",
                    format!(
                        "field \"{}\" holds an integer above the i64 range",
                        column.field.name
                    ),
                )
                .with_field(&column.field.name)
            })?
        };
        out.push(Some(value));
        Ok(())
    })?;
    Ok(out)
}

/// Integers as exact decimal text plus their f64 value (unsigned values
/// above `i64::MAX` keep their exact text).
pub fn int_texts(column: &Column<'_, '_>) -> GfResult<Vec<Option<(String, f64)>>> {
    let DataType::Int { signed, .. } = column.field.data_type else {
        return Err(mismatch(column, "an integer type"));
    };
    let mut out = Vec::with_capacity(column.len());
    column.for_each::<GfError>(|array, row| {
        out.push(array.is_valid(row).then(|| {
            let bytes = array.fixed(row).unwrap();
            if signed {
                let v = sign_extend(bytes);
                (v.to_string(), v as f64)
            } else {
                let v = zero_extend(bytes);
                (v.to_string(), v as f64)
            }
        }));
        Ok(())
    })?;
    Ok(out)
}

pub fn bools(column: &Column<'_, '_>) -> GfResult<Vec<Option<bool>>> {
    if column.field.data_type != DataType::Bool {
        return Err(mismatch(column, "Bool"));
    }
    let mut out = Vec::with_capacity(column.len());
    column.for_each::<GfError>(|array, row| {
        out.push(array.is_valid(row).then(|| array.bool_value(row).unwrap()));
        Ok(())
    })?;
    Ok(out)
}

/// UTF-8 text values (validated by the reader).
pub fn texts<'a>(column: &Column<'_, 'a>) -> GfResult<Vec<Option<&'a str>>> {
    if !matches!(column.field.data_type, DataType::Utf8 { .. }) {
        return Err(mismatch(column, "Utf8"));
    }
    let mut out = Vec::with_capacity(column.len());
    column.for_each::<GfError>(|array, row| {
        out.push(
            array
                .is_valid(row)
                .then(|| std::str::from_utf8(array.var(row).unwrap()).unwrap()),
        );
        Ok(())
    })?;
    Ok(out)
}

/// Flattened lists of UUIDs: `(offsets, values)` with `offsets.len() ==
/// rows + 1`; a null list is empty and reported in `nulls`. Null items fail.
pub struct UuidLists {
    pub offsets: Vec<usize>,
    pub values: Vec<Uuid>,
    pub nulls: usize,
}

pub fn uuid_lists(column: &Column<'_, '_>) -> GfResult<UuidLists> {
    let is_list = matches!(column.field.data_type, DataType::List { .. });
    if !is_list || column.field.children[0].data_type != DataType::FixedSizeBinary(16) {
        return Err(mismatch(column, "List<FixedSizeBinary(16)>"));
    }
    let mut out = UuidLists {
        offsets: vec![0],
        values: Vec::new(),
        nulls: 0,
    };
    column.for_each::<GfError>(|array, row| {
        if array.is_valid(row) {
            let (start, end) = array.list_range(row).unwrap();
            let child = array.list_child().unwrap();
            for item in start..end {
                if !child.is_valid(item) {
                    return Err(GfError::new(
                        "GF_RESULT_NULL_IDENTITY",
                        format!("field \"{}\" contains a null UUID", column.field.name),
                    )
                    .with_field(&column.field.name));
                }
                out.values
                    .push(child.fixed(item).unwrap().try_into().unwrap());
            }
        } else {
            out.nulls += 1;
        }
        out.offsets.push(out.values.len());
        Ok(())
    })?;
    Ok(out)
}

/// Float vectors: `(dimensions, row-major values)`; a null row or null item
/// is NaN-filled and counted in `nulls`. Ragged lists fail closed.
pub struct Vectors {
    pub dimensions: usize,
    pub values: Vec<f64>,
    pub nulls: usize,
}

pub fn vectors(column: &Column<'_, '_>) -> GfResult<Vectors> {
    let fixed = match column.field.data_type {
        DataType::FixedSizeList(n) => Some(n),
        DataType::List { .. } => None,
        _ => return Err(mismatch(column, "a list of floats")),
    };
    let item = &column.field.children[0];
    let decode: fn(&[u8]) -> f64 = match item.data_type {
        DataType::Float { bits: 64 } => |b| f64::from_le_bytes(b.try_into().unwrap()),
        DataType::Float { bits: 32 } => |b| f64::from(f32::from_le_bytes(b.try_into().unwrap())),
        DataType::Float { bits: 16 } => |b| half_to_f64(u16::from_le_bytes(b.try_into().unwrap())),
        _ => return Err(mismatch(column, "a list of floats")),
    };
    let mut out = Vectors {
        dimensions: fixed.unwrap_or(0),
        values: Vec::new(),
        nulls: 0,
    };
    let mut known = fixed.is_some();
    column.for_each::<GfError>(|array, row| {
        if !array.is_valid(row) {
            out.nulls += 1;
            out.values
                .extend(std::iter::repeat_n(f64::NAN, out.dimensions));
            return Ok(());
        }
        let (start, end) = array.list_range(row).unwrap();
        if !known {
            out.dimensions = end - start;
            known = true;
        }
        if end - start != out.dimensions {
            return Err(GfError::new(
                "GF_RESULT_SCHEMA_MISMATCH",
                format!(
                    "field \"{}\" has vectors of different lengths",
                    column.field.name
                ),
            )
            .with_field(&column.field.name));
        }
        let child = array.list_child().unwrap();
        for i in start..end {
            out.values.push(if child.is_valid(i) {
                decode(child.fixed(i).unwrap())
            } else {
                out.nulls += 1;
                f64::NAN
            });
        }
        Ok(())
    })?;
    Ok(out)
}

fn sign_extend(bytes: &[u8]) -> i64 {
    match bytes.len() {
        1 => i64::from(bytes[0] as i8),
        2 => i64::from(i16::from_le_bytes(bytes.try_into().unwrap())),
        4 => i64::from(i32::from_le_bytes(bytes.try_into().unwrap())),
        _ => i64::from_le_bytes(bytes.try_into().unwrap()),
    }
}

fn zero_extend(bytes: &[u8]) -> u64 {
    let mut buf = [0u8; 8];
    buf[..bytes.len()].copy_from_slice(bytes);
    u64::from_le_bytes(buf)
}

fn half_to_f64(bits: u16) -> f64 {
    let sign = if bits & 0x8000 != 0 { -1.0 } else { 1.0 };
    let exponent = i32::from((bits >> 10) & 0x1f);
    let fraction = f64::from(bits & 0x3ff);
    match exponent {
        0 => sign * fraction * 2f64.powi(-24),
        31 if fraction == 0.0 => sign * f64::INFINITY,
        31 => f64::NAN,
        _ => sign * (1.0 + fraction / 1024.0) * 2f64.powi(exponent - 15),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn half_floats_decode() {
        assert_eq!(half_to_f64(0x3c00), 1.0);
        assert_eq!(half_to_f64(0xc000), -2.0);
        assert_eq!(half_to_f64(0x0001), 2f64.powi(-24));
        assert!(half_to_f64(0x7e00).is_nan());
        assert_eq!(half_to_f64(0x7c00), f64::INFINITY);
    }

    #[test]
    fn integers_extend() {
        assert_eq!(sign_extend(&[0xff]), -1);
        assert_eq!(zero_extend(&[0xff]), 255);
        assert_eq!(sign_extend(&(-5i32).to_le_bytes()), -5);
    }
}
