//! Payload paint/style channel wire materialize (M2 Push 3B, ABI 320).
//!
//! Hosts marshal channel values, optional ``sel``, and ABI 312 wire policy;
//! Rust gathers, transforms, and returns u8/f32 wire buffers.

use crate::kernels::{clip_quantize_u8, normalize_f32_into};
use crate::payload_emit::{
    PAYLOAD_CHAN_BUF_F32, PAYLOAD_CHAN_BUF_NONE, PAYLOAD_CHAN_BUF_U8, PAYLOAD_CHAN_MODE_CATEGORICAL,
    PAYLOAD_CHAN_MODE_CONSTANT, PAYLOAD_CHAN_MODE_CONTINUOUS, PAYLOAD_CHAN_MODE_DIRECT,
    PAYLOAD_CHAN_MODE_DIRECT_RGBA, PAYLOAD_CHAN_MODE_MATCH_FILL, PAYLOAD_CHAN_MAX_CATEGORIES_U8,
    PAYLOAD_CHAN_WIRE_ROLE_COLOR, PAYLOAD_CHAN_WIRE_ROLE_SIZE, PAYLOAD_CHAN_WIRE_ROLE_STYLE,
    PAYLOAD_CHAN_XFORM_NORMALIZE, PAYLOAD_CHAN_XFORM_NONE, PAYLOAD_CHAN_XFORM_QUANTIZE_U8,
    PAYLOAD_CHAN_XFORM_RAW, PAYLOAD_CHAN_XFORM_RGBA_PACK, payload_channel_wire_encode,
};

pub const PAYLOAD_CHANNEL_MATERIALIZE_MAX_BYTES: usize = 1 << 28;

/// Wire buffer materialization result for one channel slice.
#[derive(Clone, Debug, PartialEq)]
pub struct PayloadChannelMaterializeOut {
    pub buf_kind: i32,
    pub mark_dtype_u8: i32,
    pub ship_palette: i32,
    pub set_n: i32,
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

fn gather_u8(values: &[u8], sel: Option<&[u32]>) -> Result<Vec<u8>, i32> {
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

fn fold_codes_u8(codes: &[f64], n_palette: usize) -> Vec<u8> {
    let n = n_palette.max(1);
    codes
        .iter()
        .map(|&code| (code as i64).rem_euclid(n as i64) as u8)
        .collect()
}

/// Materialize one channel wire buffer from host-marshaled values.
///
/// ``role`` / ``mode`` follow ABI 312. ``domain_lo``/``domain_hi`` apply to
/// continuous channels. Returns ``-1`` on invalid args, ``-2`` when over cap.
#[allow(clippy::too_many_arguments)]
pub fn payload_channel_materialize(
    role: i32,
    mode: i32,
    n_categories: usize,
    style_dtype_u8: i32,
    quantize_continuous: i32,
    domain_lo: f64,
    domain_hi: f64,
    n_palette: usize,
    sel: Option<&[u32]>,
    values_f64: &[f64],
    values_u8: &[u8],
) -> Result<PayloadChannelMaterializeOut, i32> {
    let mut buf_kind = 0;
    let mut transform = 0;
    let mut mark_dtype_u8 = 0;
    let mut ship_palette = 0;
    let mut set_n = 0;
    if payload_channel_wire_encode(
        role,
        mode,
        n_categories,
        style_dtype_u8,
        quantize_continuous,
        &mut buf_kind,
        &mut transform,
        &mut mark_dtype_u8,
        &mut ship_palette,
        &mut set_n,
    ) == 0
    {
        return Err(-1);
    }
    if buf_kind == PAYLOAD_CHAN_BUF_NONE {
        return Ok(PayloadChannelMaterializeOut {
            buf_kind,
            mark_dtype_u8,
            ship_palette,
            set_n,
            len: 0,
            bytes: Vec::new(),
        });
    }
    let bytes = match transform {
        PAYLOAD_CHAN_XFORM_NONE => Vec::new(),
        PAYLOAD_CHAN_XFORM_RGBA_PACK => {
            let gathered = gather_f64(values_f64, sel)?;
            if gathered.len() % 4 != 0 {
                return Err(-1);
            }
            let mut out = vec![0u8; gathered.len()];
            if clip_quantize_u8(&gathered, &mut out) == 0 {
                return Err(-1);
            }
            out
        }
        PAYLOAD_CHAN_XFORM_NORMALIZE => {
            let gathered = gather_f64(values_f64, sel)?;
            let mut out = vec![0f32; gathered.len()];
            normalize_f32_into(&gathered, domain_lo, domain_hi, 0.0, &mut out);
            out.iter().flat_map(|v| v.to_le_bytes()).collect()
        }
        PAYLOAD_CHAN_XFORM_QUANTIZE_U8 => {
            let gathered = gather_f64(values_f64, sel)?;
            let mut unit = vec![0f32; gathered.len()];
            normalize_f32_into(&gathered, domain_lo, domain_hi, 0.0, &mut unit);
            let unit_f64: Vec<f64> = unit.iter().map(|&v| f64::from(v)).collect();
            let mut out = vec![0u8; unit_f64.len()];
            if clip_quantize_u8(&unit_f64, &mut out) == 0 {
                return Err(-1);
            }
            out
        }
        PAYLOAD_CHAN_XFORM_RAW => {
            if !values_u8.is_empty() {
                gather_u8(values_u8, sel)?
            } else if mode == PAYLOAD_CHAN_MODE_CATEGORICAL && mark_dtype_u8 != 0 {
                let gathered = gather_f64(values_f64, sel)?;
                if n_categories <= PAYLOAD_CHAN_MAX_CATEGORIES_U8 {
                    fold_codes_u8(&gathered, n_palette)
                } else {
                    gathered.iter().flat_map(|v| v.to_le_bytes()).collect()
                }
            } else {
                let gathered = gather_f64(values_f64, sel)?;
                if buf_kind == PAYLOAD_CHAN_BUF_U8 {
                    gathered.iter().map(|&v| v as u8).collect()
                } else if buf_kind == PAYLOAD_CHAN_BUF_F32 {
                    gathered
                        .iter()
                        .flat_map(|&v| (v as f32).to_le_bytes())
                        .collect()
                } else {
                    gathered.iter().flat_map(|v| v.to_le_bytes()).collect()
                }
            }
        }
        _ => return Err(-1),
    };
    if bytes.len() > PAYLOAD_CHANNEL_MATERIALIZE_MAX_BYTES {
        return Err(-2);
    }
    let len = if buf_kind == PAYLOAD_CHAN_BUF_F32 {
        (bytes.len() / 4) as u32
    } else {
        bytes.len() as u32
    };
    Ok(PayloadChannelMaterializeOut {
        buf_kind,
        mark_dtype_u8,
        ship_palette,
        set_n,
        len,
        bytes,
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn continuous_f32_materialize() {
        let values = [0.0, 0.5, 1.0];
        let out = payload_channel_materialize(
            PAYLOAD_CHAN_WIRE_ROLE_COLOR,
            PAYLOAD_CHAN_MODE_CONTINUOUS,
            0,
            0,
            0,
            0.0,
            1.0,
            0,
            None,
            &values,
            &[],
        )
        .unwrap();
        assert_eq!(out.buf_kind, PAYLOAD_CHAN_BUF_F32);
        assert_eq!(out.len, 3);
    }

    #[test]
    fn constant_emits_no_buffer() {
        let out = payload_channel_materialize(
            PAYLOAD_CHAN_WIRE_ROLE_COLOR,
            PAYLOAD_CHAN_MODE_CONSTANT,
            0,
            0,
            0,
            0.0,
            1.0,
            0,
            None,
            &[],
            &[],
        )
        .unwrap();
        assert_eq!(out.buf_kind, PAYLOAD_CHAN_BUF_NONE);
    }

    #[test]
    fn direct_style_f32_materialize_len() {
        let values = [2.0, 3.0];
        let out = payload_channel_materialize(
            PAYLOAD_CHAN_WIRE_ROLE_STYLE,
            PAYLOAD_CHAN_MODE_DIRECT,
            0,
            0,
            0,
            0.0,
            1.0,
            0,
            None,
            &values,
            &[],
        )
        .unwrap();
        assert_eq!(out.buf_kind, PAYLOAD_CHAN_BUF_F32);
        assert_eq!(out.len, 2);
        assert_eq!(out.bytes.len(), 8);
    }

    #[test]
    fn categorical_u8_materialize_from_codes() {
        let codes = [0u8, 1, 0, 1, 0];
        let out = payload_channel_materialize(
            PAYLOAD_CHAN_WIRE_ROLE_COLOR,
            PAYLOAD_CHAN_MODE_CATEGORICAL,
            2,
            0,
            0,
            0.0,
            1.0,
            0,
            None,
            &[],
            &codes,
        )
        .unwrap();
        assert_eq!(out.buf_kind, PAYLOAD_CHAN_BUF_U8);
        assert_eq!(out.len, 5);
        assert_eq!(out.bytes, codes);
        assert_eq!(out.ship_palette, 1);
    }
}
