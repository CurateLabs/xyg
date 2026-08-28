//! Compact Figure→Scene XYCB colorbar framing (M2 #271).
//!
//! Hosts validate authoring keys (`side`, title type, `minor_ticks` type)
//! and pass domain, stops, ticks, title, and text RGBA. Rust owns the XYCB
//! v2 header, stop/tick tables, domain-span checks, and bounded-text
//! rejection so Python and Node cannot drift on the colorbar envelope.

use crate::scene::{
    MAX_SCENE_COLORBAR_INPUT_BYTES, MAX_SCENE_COLORBAR_STOPS, MAX_SCENE_COLORBAR_TEXT_BYTES,
    MAX_SCENE_COLORBAR_TICKS,
};

pub const COLORBAR_HEADER_BYTES: usize = 56;
pub const COLORBAR_STOP_BYTES: usize = 12;
pub const COLORBAR_TICK_BYTES: usize = 8;

const XYCB: &[u8; 4] = b"XYCB";
const XYCB_VERSION: u32 = 2;
const FLAG_HORIZONTAL: u8 = 1 << 0;
const FLAG_V2: u8 = 1 << 1;
const FLAG_MINOR_TICKS: u8 = 1 << 2;
const FLAG_AUTHORED_TICKS: u8 = 1 << 3;
const FLAG_INPUT_MASK: u8 = FLAG_HORIZONTAL | FLAG_MINOR_TICKS;

/// Why a colorbar frame request was rejected. Discriminants are the C-ABI
/// error codes (returned negated by `xyg_scene_pack_colorbar`).
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
#[allow(dead_code)] // Version is reserved for a future envelope; C ABI returns -2.
pub enum ColorbarError {
    Length = 1,
    Version = 2,
    Limit = 3,
    Output = 4,
    NonFinite = 5,
    Order = 6,
    Ticks = 7,
}

/// One literal RGBA stop before XYCB framing.
#[derive(Clone, Copy, Debug, PartialEq)]
pub struct ColorbarStop {
    pub value: f64,
    pub rgba: [u8; 4],
}

/// Authoring literals for one primary Scene colorbar.
#[derive(Clone, Copy, Debug)]
pub struct ColorbarFrameInput<'a> {
    pub flags: u8,
    pub lo: f64,
    pub hi: f64,
    pub text_rgba: [u8; 4],
    pub title: &'a [u8],
    pub stops: &'a [ColorbarStop],
    pub ticks: &'a [f64],
}

fn require_ordered(values: &[f64], lo: f64, hi: f64, ticks: bool) -> Result<(), ColorbarError> {
    let mut previous = f64::NEG_INFINITY;
    for &value in values {
        if !value.is_finite() {
            return Err(ColorbarError::NonFinite);
        }
        if value < lo || value > hi || value <= previous {
            return Err(if ticks {
                ColorbarError::Ticks
            } else {
                ColorbarError::Order
            });
        }
        previous = value;
    }
    Ok(())
}

/// Number of XYCB bytes one framed colorbar will emit.
pub fn packed_colorbar_len(
    n_stops: usize,
    n_ticks: usize,
    title_len: usize,
) -> Result<usize, ColorbarError> {
    let stops = n_stops
        .checked_mul(COLORBAR_STOP_BYTES)
        .ok_or(ColorbarError::Limit)?;
    let ticks = n_ticks
        .checked_mul(COLORBAR_TICK_BYTES)
        .ok_or(ColorbarError::Limit)?;
    COLORBAR_HEADER_BYTES
        .checked_add(stops)
        .and_then(|value| value.checked_add(ticks))
        .and_then(|value| value.checked_add(title_len))
        .ok_or(ColorbarError::Limit)
}

/// Frame a primary Scene colorbar as XYCB v2 bytes.
pub fn pack_colorbar(input: ColorbarFrameInput<'_>) -> Result<Vec<u8>, ColorbarError> {
    if input.flags & !FLAG_INPUT_MASK != 0 {
        return Err(ColorbarError::Length);
    }
    if !input.lo.is_finite() || !input.hi.is_finite() || input.lo >= input.hi {
        return Err(ColorbarError::NonFinite);
    }
    if !(2..=MAX_SCENE_COLORBAR_STOPS).contains(&input.stops.len()) {
        return Err(ColorbarError::Limit);
    }
    if input.ticks.len() > MAX_SCENE_COLORBAR_TICKS {
        return Err(ColorbarError::Limit);
    }
    if input.title.len() > MAX_SCENE_COLORBAR_TEXT_BYTES || input.title.contains(&0) {
        return Err(ColorbarError::Limit);
    }
    let stop_values: Vec<f64> = input.stops.iter().map(|stop| stop.value).collect();
    require_ordered(&stop_values, input.lo, input.hi, false)?;
    if input.stops.first().unwrap().value != input.lo
        || input.stops.last().unwrap().value != input.hi
    {
        return Err(ColorbarError::Order);
    }
    require_ordered(input.ticks, input.lo, input.hi, true)?;
    let total = packed_colorbar_len(input.stops.len(), input.ticks.len(), input.title.len())?;
    if total > MAX_SCENE_COLORBAR_INPUT_BYTES {
        return Err(ColorbarError::Limit);
    }
    let mut out = vec![0u8; total];
    out[..4].copy_from_slice(XYCB);
    out[4..8].copy_from_slice(&XYCB_VERSION.to_le_bytes());
    out[8] = input.flags
        | FLAG_V2
        | if input.ticks.is_empty() {
            0
        } else {
            FLAG_AUTHORED_TICKS
        };
    out[12..16].copy_from_slice(&(input.stops.len() as u32).to_le_bytes());
    out[16..20].copy_from_slice(&(input.ticks.len() as u32).to_le_bytes());
    out[20..24].copy_from_slice(&(input.title.len() as u32).to_le_bytes());
    out[24..32].copy_from_slice(&input.lo.to_le_bytes());
    out[32..40].copy_from_slice(&input.hi.to_le_bytes());
    out[40..44].copy_from_slice(&input.text_rgba);
    for (index, stop) in input.stops.iter().enumerate() {
        let at = COLORBAR_HEADER_BYTES + index * COLORBAR_STOP_BYTES;
        out[at..at + 8].copy_from_slice(&stop.value.to_le_bytes());
        out[at + 8..at + 12].copy_from_slice(&stop.rgba);
    }
    let ticks_at = COLORBAR_HEADER_BYTES + input.stops.len() * COLORBAR_STOP_BYTES;
    for (index, &value) in input.ticks.iter().enumerate() {
        let at = ticks_at + index * COLORBAR_TICK_BYTES;
        out[at..at + 8].copy_from_slice(&value.to_le_bytes());
    }
    let title_at = ticks_at + input.ticks.len() * COLORBAR_TICK_BYTES;
    out[title_at..].copy_from_slice(input.title);
    Ok(out)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn frames_v2_header_stops_ticks_and_title() {
        let stops = [
            ColorbarStop {
                value: 0.0,
                rgba: [0, 0, 0, 255],
            },
            ColorbarStop {
                value: 1.0,
                rgba: [255, 255, 255, 255],
            },
        ];
        let ticks = [0.0, 0.5, 1.0];
        let framed = pack_colorbar(ColorbarFrameInput {
            flags: FLAG_MINOR_TICKS,
            lo: 0.0,
            hi: 1.0,
            text_rgba: [32, 32, 32, 255],
            title: b"",
            stops: &stops,
            ticks: &ticks,
        })
        .unwrap();
        assert_eq!(&framed[..4], b"XYCB");
        assert_eq!(u32::from_le_bytes(framed[4..8].try_into().unwrap()), 2);
        assert_eq!(framed[8], 0b1110);
        assert_eq!(u32::from_le_bytes(framed[16..20].try_into().unwrap()), 3);
        let ticks_at = COLORBAR_HEADER_BYTES + 2 * COLORBAR_STOP_BYTES;
        assert_eq!(
            f64::from_le_bytes(framed[ticks_at..ticks_at + 8].try_into().unwrap()),
            0.0
        );
        assert_eq!(
            f64::from_le_bytes(framed[ticks_at + 8..ticks_at + 16].try_into().unwrap()),
            0.5
        );
        assert_eq!(
            f64::from_le_bytes(framed[ticks_at + 16..ticks_at + 24].try_into().unwrap()),
            1.0
        );
    }

    #[test]
    fn stops_must_span_the_domain() {
        let stops = [
            ColorbarStop {
                value: 0.1,
                rgba: [0, 0, 0, 255],
            },
            ColorbarStop {
                value: 1.0,
                rgba: [255, 255, 255, 255],
            },
        ];
        assert_eq!(
            pack_colorbar(ColorbarFrameInput {
                flags: 0,
                lo: 0.0,
                hi: 1.0,
                text_rgba: [32, 32, 32, 255],
                title: b"",
                stops: &stops,
                ticks: &[],
            }),
            Err(ColorbarError::Order)
        );
    }

    #[test]
    fn bottom_side_sets_horizontal_flag() {
        let stops = [
            ColorbarStop {
                value: 0.0,
                rgba: [0, 0, 0, 255],
            },
            ColorbarStop {
                value: 1.0,
                rgba: [255, 255, 255, 128],
            },
        ];
        let framed = pack_colorbar(ColorbarFrameInput {
            flags: FLAG_HORIZONTAL,
            lo: 0.0,
            hi: 1.0,
            text_rgba: [32, 32, 32, 255],
            title: b"scale",
            stops: &stops,
            ticks: &[],
        })
        .unwrap();
        assert_eq!(framed[8] & FLAG_HORIZONTAL, FLAG_HORIZONTAL);
        assert_eq!(framed[8] & FLAG_AUTHORED_TICKS, 0);
        assert_eq!(&framed[framed.len() - 5..], b"scale");
    }
}
