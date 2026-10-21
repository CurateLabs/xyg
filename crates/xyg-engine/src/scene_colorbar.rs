//! Compact Figure→Scene XYCB colorbar framing (M2 #271).
//!
//! Hosts validate authoring keys (`side`, title type, `minor_ticks` type)
//! and pass domain, stops, ticks, title, and text RGBA. Rust owns the XYCB
//! v2 header, stop/tick tables, domain-span checks, and bounded-text
//! rejection so Python and Node cannot drift on the colorbar envelope.

use crate::colormap;
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

/// Evenly spaced, strictly increasing stop values with bit-exact endpoints.
///
/// Uses `lo + (hi - lo) * i / n` while `(hi - lo) * i` is finite and
/// `lo * (1 - t) + hi * t` when that product overflows (domains such as
/// `[-1.7e308, 1.7e308]`), clamps into the
/// domain, and lifts any value that rounding left at or below its predecessor
/// to the next representable f64. A domain with too few representable values
/// between its endpoints for `count` samples is rejected as `Order` rather
/// than dropping samples.
fn uniform_stop_values(lo: f64, hi: f64, count: usize) -> Result<Vec<f64>, ColorbarError> {
    let last = count - 1;
    let mut values = Vec::with_capacity(count);
    values.push(lo);
    for index in 1..last {
        let t = index as f64 / last as f64;
        // Keep the historical single-rounding form wherever the span and the
        // scaled product are finite so ordinary domains frame byte-identically.
        let scaled = (hi - lo) * index as f64;
        let ideal = if scaled.is_finite() {
            lo + scaled / last as f64
        } else {
            lo * (1.0 - t) + hi * t
        };
        let previous = *values.last().unwrap();
        // Interpolation must land strictly inside the domain; anything else is
        // a defect, not something to paper over by lifting.
        if !ideal.is_finite() || ideal >= hi {
            return Err(ColorbarError::Order);
        }
        // Lift only when rounding left the value at or below its predecessor.
        let value = if ideal > previous {
            ideal
        } else {
            previous.next_up()
        };
        if value >= hi {
            return Err(ColorbarError::Order);
        }
        values.push(value);
    }
    values.push(hi);
    Ok(values)
}

/// Resolve one named colormap and frame its canonical stops without host-side
/// stop interpolation. `flags` uses the same horizontal/minor input bits as
/// [`pack_colorbar`].
pub fn pack_named_colorbar(
    flags: u8,
    lo: f64,
    hi: f64,
    text_rgba: [u8; 4],
    title: &[u8],
    name: &str,
    ticks: &[f64],
) -> Result<Vec<u8>, ColorbarError> {
    if name.is_empty() || name.as_bytes().contains(&0) {
        return Err(ColorbarError::Length);
    }
    let colors = colormap::colormap_named_stops(name);
    if !(2..=MAX_SCENE_COLORBAR_STOPS).contains(&colors.len()) {
        return Err(ColorbarError::Limit);
    }
    let color_count = colors.len();
    if flags & !FLAG_INPUT_MASK != 0 {
        return Err(ColorbarError::Length);
    }
    if !lo.is_finite() || !hi.is_finite() || lo >= hi {
        return Err(ColorbarError::NonFinite);
    }
    let values = uniform_stop_values(lo, hi, color_count)?;
    let stops: Vec<ColorbarStop> = colors
        .into_iter()
        .zip(values)
        .map(|(rgb, value)| ColorbarStop {
            value,
            rgba: [rgb[0], rgb[1], rgb[2], 255],
        })
        .collect();
    pack_colorbar(ColorbarFrameInput {
        flags,
        lo,
        hi,
        text_rgba,
        title,
        stops: &stops,
        ticks,
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    const PINNED_BITS: [u64; 11] = [
        0xbfffe94e3e6304db,
        0xbff7b194274b7b5a,
        0xbfeef3b42067e3b2,
        0xbfdd087fe471a160,
        0x3faeb343bf642520,
        0x3fe25aa86a255556,
        0x3ff1650e4c2a342b,
        0x3ff99cc86341bdaf,
        0x4000ea413d2ca396,
        0x4005061e48b86856,
        0x400921fb54442d18,
    ];

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

    #[test]
    fn named_colorbar_owns_stop_positions_and_rgba() {
        let framed = pack_named_colorbar(
            FLAG_HORIZONTAL | FLAG_MINOR_TICKS,
            -2.0,
            2.0,
            [1, 2, 3, 255],
            b"Intensity",
            "viridis",
            &[-2.0, 0.0, 2.0],
        )
        .unwrap();
        assert_eq!(&framed[..4], b"XYCB");
        let count = u32::from_le_bytes(framed[12..16].try_into().unwrap()) as usize;
        assert!(count >= 2);
        assert_eq!(
            f64::from_le_bytes(framed[COLORBAR_HEADER_BYTES..][..8].try_into().unwrap()),
            -2.0
        );
        let last = COLORBAR_HEADER_BYTES + (count - 1) * COLORBAR_STOP_BYTES;
        assert_eq!(
            f64::from_le_bytes(framed[last..last + 8].try_into().unwrap()),
            2.0
        );
    }

    fn named_values(lo: f64, hi: f64, name: &str) -> Result<Vec<f64>, ColorbarError> {
        let framed = pack_named_colorbar(0, lo, hi, [32, 32, 32, 255], b"", name, &[])?;
        let count = u32::from_le_bytes(framed[12..16].try_into().unwrap()) as usize;
        Ok((0..count)
            .map(|index| {
                let at = COLORBAR_HEADER_BYTES + index * COLORBAR_STOP_BYTES;
                f64::from_le_bytes(framed[at..at + 8].try_into().unwrap())
            })
            .collect())
    }

    /// Bar fraction of `v` computed with halved terms so it cannot overflow.
    fn fraction(v: f64, lo: f64, hi: f64) -> f64 {
        (v / 2.0 - lo / 2.0) / (hi / 2.0 - lo / 2.0)
    }

    fn assert_full_palette(values: &[f64], lo: f64, hi: f64, name: &str) {
        assert_eq!(values.len(), colormap::colormap_named_stops(name).len());
        assert_eq!(values[0], lo);
        assert_eq!(*values.last().unwrap(), hi);
        assert!(
            values.windows(2).all(|pair| pair[0] < pair[1]),
            "{values:?}"
        );
        if values.len() > 2 && hi / 2.0 - lo / 2.0 > 1e-300 && hi.is_finite() {
            let n = (values.len() - 1) as f64;
            for (index, &v) in values.iter().enumerate() {
                let want = index as f64 / n;
                assert!(
                    (fraction(v, lo, hi) - want).abs() < 1e-9,
                    "stop {index} of {lo:e}..{hi:e}: {} vs {want}",
                    fraction(v, lo, hi)
                );
            }
        }
    }

    #[test]
    fn named_colorbar_survives_extreme_finite_domains() {
        for (lo, hi) in [
            (0.0, 1.7e308),
            (-1.7e308, 1.7e308),
            (-f64::MAX, f64::MAX),
            (-f64::MAX, 0.0),
            (f64::MAX / 2.0, f64::MAX),
            (-f64::MIN_POSITIVE, f64::MIN_POSITIVE),
            (0.0, f64::from_bits(1) * 64.0),
        ] {
            for name in ["viridis", "viridis_r", "blues"] {
                let values = named_values(lo, hi, name).unwrap();
                assert_full_palette(&values, lo, hi, name);
            }
        }
    }

    #[test]
    fn named_colorbar_spacing_is_uniform_on_wide_domains() {
        for (lo, hi) in [
            (0.0, 1.7e308),
            (-f64::MAX, 0.0),
            (f64::MAX / 2.0, f64::MAX),
            (-f64::MAX, f64::MAX),
        ] {
            let values = named_values(lo, hi, "viridis").unwrap();
            assert_full_palette(&values, lo, hi, "viridis");
        }
    }

    #[test]
    fn named_colorbar_flags_are_checked_before_the_domain() {
        assert_eq!(
            pack_named_colorbar(0x80, 2.0, 1.0, [0; 4], b"", "viridis", &[]),
            Err(ColorbarError::Length)
        );
    }

    #[test]
    fn named_colorbar_pins_ordinary_non_unit_domain_bit_patterns() {
        // Captured from the pre-#888 formula `lo + (hi - lo) * i / n`.
        let values =
            named_values(-1.994_459_384_630_593_8, 3.141_592_653_589_793, "viridis").unwrap();
        let bits: Vec<u64> = values.iter().map(|v| v.to_bits()).collect();
        assert_eq!(bits, PINNED_BITS);
    }

    #[test]
    fn named_colorbar_keeps_ordinary_domain_bytes() {
        let values = named_values(0.0, 1.0, "viridis").unwrap();
        let expected: Vec<f64> = (0..values.len())
            .map(|index| match index {
                0 => 0.0,
                last if last + 1 == values.len() => 1.0,
                _ => index as f64 / (values.len() - 1) as f64,
            })
            .collect();
        assert_eq!(values, expected);
    }

    #[test]
    fn named_colorbar_adjacent_domains_keep_every_sample_or_reject() {
        // Exactly enough representable values: every palette sample survives.
        let lo = 1.0_f64;
        let mut hi = lo;
        for _ in 0..10 {
            hi = hi.next_up();
        }
        let values = named_values(lo, hi, "viridis").unwrap();
        assert_full_palette(&values, lo, hi, "viridis");
        // Fewer representable values than samples: stable Order, no silent
        // drop and no endpoint-only substitution.
        for steps in [1, 2, 9] {
            let mut hi = lo;
            for _ in 0..steps {
                hi = hi.next_up();
            }
            assert_eq!(
                pack_named_colorbar(0, lo, hi, [32, 32, 32, 255], b"", "viridis", &[]),
                Err(ColorbarError::Order),
                "{steps} ulps"
            );
        }
    }

    #[test]
    fn named_colorbar_rejects_equal_reversed_and_non_finite_domains() {
        for (lo, hi) in [
            (1.0, 1.0),
            (2.0, 1.0),
            (f64::NAN, 1.0),
            (0.0, f64::INFINITY),
            (f64::NEG_INFINITY, 0.0),
        ] {
            assert_eq!(
                pack_named_colorbar(0, lo, hi, [32, 32, 32, 255], b"", "viridis", &[]),
                Err(ColorbarError::NonFinite)
            );
        }
    }

    #[test]
    fn named_colorbar_pins_non_unit_domain_endpoints_bit_exact() {
        let lo = -1.994_459_384_630_593_8;
        let hi = -0.000_799_789_190_698_674_3;
        let framed = pack_named_colorbar(0, lo, hi, [32, 32, 32, 255], b"", "blues", &[]).unwrap();
        let count = u32::from_le_bytes(framed[12..16].try_into().unwrap()) as usize;
        let last = COLORBAR_HEADER_BYTES + (count - 1) * COLORBAR_STOP_BYTES;
        assert_eq!(
            f64::from_le_bytes(framed[COLORBAR_HEADER_BYTES..][..8].try_into().unwrap()),
            lo
        );
        assert_eq!(
            f64::from_le_bytes(framed[last..last + 8].try_into().unwrap()),
            hi
        );
    }
}
