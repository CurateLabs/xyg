//! Compact Figure→Scene XYHP paint-plane packing (M2 #271 / #283).
//!
//! Hosts pack authored heatmap/density paint facts as XYHF v1. Rust owns
//! tessellation eligibility (truecolor inverse-raster stays skip), XYHP kind
//! routing (RGBA vs named colormap vs custom stops vs density vs mean-color),
//! density opacity composition, constant-color stop expansion, and the 24-byte
//! plane header so Python and Node cannot drift on painted-lattice sidecars.
//! ABI 186 reuses the heatmap family as a 1×N named/stop plane for cartesian
//! colormap hexbin; HexCell expansion interns those fills. Encoded Scene v31
//! is unchanged.

use crate::css::color_rgba8;
use crate::scene::{
    MAX_SCENE_IMAGE_PIXELS, XYHP_MAX_NAME_BYTES, XYHP_PAINT_COLORMAP, XYHP_PAINT_DENSITY,
    XYHP_PAINT_MEAN_COLOR, XYHP_PAINT_NAMED, XYHP_PAINT_RGBA, XYHP_PLANE_HEADER_BYTES,
};

pub const XYHF_MAGIC: &[u8; 4] = b"XYHF";
pub const XYHF_VERSION: u32 = 1;
pub const XYHF_V1_HEADER_BYTES: usize = 64;
pub const XYHF_FAMILY_HEATMAP: u8 = 0;
pub const XYHF_FAMILY_DENSITY: u8 = 1;

pub const XYHF_HAS_RGBA: u32 = 1 << 0;
pub const XYHF_HAS_RGBA_GRID: u32 = 1 << 1;
pub const XYHF_HAS_GRID: u32 = 1 << 2;
pub const XYHF_HAS_ENCODED: u32 = 1 << 3;
pub const XYHF_HAS_MEAN_RGBA: u32 = 1 << 4;
pub const XYHF_HAS_NAMED_CMAP: u32 = 1 << 5;
pub const XYHF_HAS_STOPS: u32 = 1 << 6;
pub const XYHF_HAS_TRUECOLOR: u32 = 1 << 7;
pub const XYHF_HAS_COLOR_CH: u32 = 1 << 8;
pub const XYHF_HAS_STYLE_COLOR: u32 = 1 << 9;
pub const XYHF_HAS_OPACITY: u32 = 1 << 10;
pub const XYHF_HAS_FILL_OPACITY: u32 = 1 << 11;
pub const XYHF_HAS_DOMAIN: u32 = 1 << 12;

const DEFAULT_DENSITY_OPACITY: f64 = 0.85;
const DEFAULT_FILL_OPACITY: f64 = 1.0;
const DEFAULT_COLORMAP: &[u8] = b"viridis";

/// Why an XYHF paint-fact request was rejected. Discriminants are the C-ABI
/// error codes (returned negated by `xyg_scene_pack_heatmap_facts`).
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum HeatmapFactError {
    Length = 1,
    Version = 2,
    Limit = 3,
    Output = 4,
    Shape = 5,
    Payload = 6,
}

fn read_u32(bytes: &[u8], offset: usize) -> Result<u32, HeatmapFactError> {
    Ok(u32::from_le_bytes(
        bytes
            .get(offset..offset + 4)
            .ok_or(HeatmapFactError::Length)?
            .try_into()
            .map_err(|_| HeatmapFactError::Length)?,
    ))
}

fn read_u64(bytes: &[u8], offset: usize) -> Result<u64, HeatmapFactError> {
    Ok(u64::from_le_bytes(
        bytes
            .get(offset..offset + 8)
            .ok_or(HeatmapFactError::Length)?
            .try_into()
            .map_err(|_| HeatmapFactError::Length)?,
    ))
}

fn read_f64(bytes: &[u8], offset: usize) -> Result<f64, HeatmapFactError> {
    Ok(f64::from_le_bytes(
        bytes
            .get(offset..offset + 8)
            .ok_or(HeatmapFactError::Length)?
            .try_into()
            .map_err(|_| HeatmapFactError::Length)?,
    ))
}

fn take<'a>(
    rest: &mut &'a [u8],
    n: usize,
) -> Result<&'a [u8], HeatmapFactError> {
    if rest.len() < n {
        return Err(HeatmapFactError::Length);
    }
    let (head, tail) = rest.split_at(n);
    *rest = tail;
    Ok(head)
}

fn take_len_prefixed<'a>(rest: &mut &'a [u8]) -> Result<&'a [u8], HeatmapFactError> {
    let header = take(rest, 4)?;
    let len = u32::from_le_bytes(
        header
            .try_into()
            .map_err(|_| HeatmapFactError::Length)?,
    ) as usize;
    take(rest, len)
}

fn cells(rows: u32, cols: u32) -> Result<usize, HeatmapFactError> {
    let rows = rows as usize;
    let cols = cols as usize;
    if rows == 0 || cols == 0 {
        return Err(HeatmapFactError::Shape);
    }
    let n = rows.checked_mul(cols).ok_or(HeatmapFactError::Limit)?;
    if n > MAX_SCENE_IMAGE_PIXELS {
        return Err(HeatmapFactError::Limit);
    }
    Ok(n)
}

fn f64_unit_to_u8(value: f64) -> u8 {
    if !value.is_finite() {
        return 0;
    }
    (value * 255.0).round().clamp(0.0, 255.0) as u8
}

fn encode_plane(stable_id: u64, rows: u32, cols: u32, kind: u32, payload: &[u8]) -> Vec<u8> {
    let mut out = Vec::with_capacity(XYHP_PLANE_HEADER_BYTES + payload.len());
    out.extend_from_slice(&stable_id.to_le_bytes());
    out.extend_from_slice(&rows.to_le_bytes());
    out.extend_from_slice(&cols.to_le_bytes());
    out.extend_from_slice(&kind.to_le_bytes());
    out.extend_from_slice(&(payload.len() as u32).to_le_bytes());
    out.extend_from_slice(payload);
    out
}

fn colormap_payload(lo: f64, hi: f64, count: u32, flag: u32, body: &[u8], extra: &[u8]) -> Vec<u8> {
    let mut payload = Vec::with_capacity(24 + body.len() + extra.len());
    payload.extend_from_slice(&lo.to_le_bytes());
    payload.extend_from_slice(&hi.to_le_bytes());
    payload.extend_from_slice(&count.to_le_bytes());
    payload.extend_from_slice(&flag.to_le_bytes());
    payload.extend_from_slice(body);
    payload.extend_from_slice(extra);
    payload
}

fn named_bytes(name: &[u8]) -> Result<&[u8], HeatmapFactError> {
    if name.is_empty() {
        Ok(DEFAULT_COLORMAP)
    } else if name.len() > XYHP_MAX_NAME_BYTES {
        Err(HeatmapFactError::Payload)
    } else {
        Ok(name)
    }
}

fn heatmap_eligible(flags: u32) -> bool {
    if flags & XYHF_HAS_RGBA_GRID != 0 {
        return true;
    }
    if flags & XYHF_HAS_TRUECOLOR != 0 {
        return false;
    }
    flags & (XYHF_HAS_NAMED_CMAP | XYHF_HAS_STOPS | XYHF_HAS_RGBA) != 0
}

fn rgba_from_grid(values: &[u8], n: usize) -> Result<Vec<u8>, HeatmapFactError> {
    let need = n
        .checked_mul(4)
        .and_then(|pixels| pixels.checked_mul(8))
        .ok_or(HeatmapFactError::Limit)?;
    if values.len() != need {
        return Err(HeatmapFactError::Shape);
    }
    let mut rgba = vec![0u8; n * 4];
    for index in 0..n * 4 {
        let at = index * 8;
        let value = f64::from_le_bytes(
            values[at..at + 8]
                .try_into()
                .map_err(|_| HeatmapFactError::Length)?,
        );
        rgba[index] = f64_unit_to_u8(value);
    }
    Ok(rgba)
}

/// Pack one XYHF v1 heatmap/density fact record into one XYHP plane body.
///
/// Empty input and ineligible truecolor inverse-raster return an empty plane
/// so hosts omit `FACT_HEATMAP_PAINT`. Output is the 24-byte plane header plus
/// payload, not the XYHP envelope.
pub fn pack_heatmap_facts(bytes: &[u8]) -> Result<Vec<u8>, HeatmapFactError> {
    if bytes.is_empty() {
        return Ok(Vec::new());
    }
    if bytes.len() < XYHF_V1_HEADER_BYTES || bytes.get(..4) != Some(&XYHF_MAGIC[..]) {
        return Err(HeatmapFactError::Length);
    }
    if read_u32(bytes, 4)? != XYHF_VERSION {
        return Err(HeatmapFactError::Version);
    }
    let stable_id = read_u64(bytes, 8)?;
    let rows = read_u32(bytes, 16)?;
    let cols = read_u32(bytes, 20)?;
    let flags = read_u32(bytes, 24)?;
    let family = bytes[28];
    let lo = read_f64(bytes, 32)?;
    let hi = read_f64(bytes, 40)?;
    let opacity = read_f64(bytes, 48)?;
    let fill_opacity = read_f64(bytes, 56)?;
    let n = cells(rows, cols)?;
    let mut rest = bytes.get(XYHF_V1_HEADER_BYTES..).unwrap_or(&[]);

    let rgba = if flags & XYHF_HAS_RGBA != 0 {
        Some(take(&mut rest, n * 4)?)
    } else {
        None
    };
    let rgba_grid = if flags & XYHF_HAS_RGBA_GRID != 0 {
        Some(take(&mut rest, n * 4 * 8)?)
    } else {
        None
    };
    let grid = if flags & XYHF_HAS_GRID != 0 {
        Some(take(&mut rest, n * 8)?)
    } else {
        None
    };
    let encoded = if flags & XYHF_HAS_ENCODED != 0 {
        Some(take(&mut rest, n)?)
    } else {
        None
    };
    let mean_rgba = if flags & XYHF_HAS_MEAN_RGBA != 0 {
        Some(take(&mut rest, n * 4)?)
    } else {
        None
    };
    let named = if flags & XYHF_HAS_NAMED_CMAP != 0 {
        Some(take_len_prefixed(&mut rest)?)
    } else {
        None
    };
    let stops = if flags & XYHF_HAS_STOPS != 0 {
        let raw = take_len_prefixed(&mut rest)?;
        if raw.is_empty() || raw.len() % 3 != 0 {
            return Err(HeatmapFactError::Payload);
        }
        Some(raw)
    } else {
        None
    };
    let color_ch = if flags & XYHF_HAS_COLOR_CH != 0 {
        Some(take_len_prefixed(&mut rest)?)
    } else {
        None
    };
    let style_color = if flags & XYHF_HAS_STYLE_COLOR != 0 {
        Some(take_len_prefixed(&mut rest)?)
    } else {
        None
    };
    if !rest.is_empty() {
        return Err(HeatmapFactError::Length);
    }

    match family {
        XYHF_FAMILY_HEATMAP => {
            if !heatmap_eligible(flags) {
                return Ok(Vec::new());
            }
            if let Some(packed) = rgba {
                return Ok(encode_plane(
                    stable_id,
                    rows,
                    cols,
                    XYHP_PAINT_RGBA,
                    packed,
                ));
            }
            if let Some(values) = rgba_grid {
                let packed = rgba_from_grid(values, n)?;
                return Ok(encode_plane(
                    stable_id,
                    rows,
                    cols,
                    XYHP_PAINT_RGBA,
                    &packed,
                ));
            }
            let values = grid.ok_or(HeatmapFactError::Payload)?;
            if let Some(name) = named {
                let name = named_bytes(name)?;
                let payload = colormap_payload(
                    lo,
                    hi,
                    name.len() as u32,
                    0,
                    values,
                    name,
                );
                return Ok(encode_plane(
                    stable_id,
                    rows,
                    cols,
                    XYHP_PAINT_NAMED,
                    &payload,
                ));
            }
            let stops = stops.ok_or(HeatmapFactError::Payload)?;
            let payload = colormap_payload(
                lo,
                hi,
                (stops.len() / 3) as u32,
                0,
                values,
                stops,
            );
            Ok(encode_plane(
                stable_id,
                rows,
                cols,
                XYHP_PAINT_COLORMAP,
                &payload,
            ))
        }
        XYHF_FAMILY_DENSITY => {
            let encoded = encoded.ok_or(HeatmapFactError::Shape)?;
            let density_opacity = if flags & XYHF_HAS_OPACITY != 0 {
                opacity
            } else {
                DEFAULT_DENSITY_OPACITY
            } * if flags & XYHF_HAS_FILL_OPACITY != 0 {
                fill_opacity
            } else {
                DEFAULT_FILL_OPACITY
            };
            if let Some(mean) = mean_rgba {
                let payload = colormap_payload(lo, density_opacity, 0, 0, encoded, mean);
                return Ok(encode_plane(
                    stable_id,
                    rows,
                    cols,
                    XYHP_PAINT_MEAN_COLOR,
                    &payload,
                ));
            }
            let constant = color_ch.filter(|css| !css.is_empty()).or_else(|| {
                if named.is_none() && stops.is_none() {
                    style_color.filter(|css| !css.is_empty())
                } else {
                    None
                }
            });
            if let Some(css) = constant {
                let css = std::str::from_utf8(css).map_err(|_| HeatmapFactError::Payload)?;
                let rgba = color_rgba8(css, 1.0);
                let extra = [rgba[0], rgba[1], rgba[2], rgba[0], rgba[1], rgba[2]];
                let payload = colormap_payload(lo, density_opacity, 2, 1, encoded, &extra);
                return Ok(encode_plane(
                    stable_id,
                    rows,
                    cols,
                    XYHP_PAINT_DENSITY,
                    &payload,
                ));
            }
            if named.is_some() || stops.is_none() {
                let name = named_bytes(named.unwrap_or(DEFAULT_COLORMAP))?;
                let payload = colormap_payload(
                    lo,
                    density_opacity,
                    name.len() as u32,
                    0,
                    encoded,
                    name,
                );
                return Ok(encode_plane(
                    stable_id,
                    rows,
                    cols,
                    XYHP_PAINT_DENSITY,
                    &payload,
                ));
            }
            let stops = stops.ok_or(HeatmapFactError::Payload)?;
            let payload = colormap_payload(
                lo,
                density_opacity,
                (stops.len() / 3) as u32,
                1,
                encoded,
                stops,
            );
            Ok(encode_plane(
                stable_id,
                rows,
                cols,
                XYHP_PAINT_DENSITY,
                &payload,
            ))
        }
        _ => Err(HeatmapFactError::Version),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn header(
        family: u8,
        flags: u32,
        rows: u32,
        cols: u32,
        lo: f64,
        hi: f64,
        opacity: f64,
        fill_opacity: f64,
    ) -> Vec<u8> {
        let mut out = Vec::from(*XYHF_MAGIC);
        out.extend_from_slice(&XYHF_VERSION.to_le_bytes());
        out.extend_from_slice(&9u64.to_le_bytes());
        out.extend_from_slice(&rows.to_le_bytes());
        out.extend_from_slice(&cols.to_le_bytes());
        out.extend_from_slice(&flags.to_le_bytes());
        out.push(family);
        out.extend_from_slice(&[0, 0, 0]);
        out.extend_from_slice(&lo.to_le_bytes());
        out.extend_from_slice(&hi.to_le_bytes());
        out.extend_from_slice(&opacity.to_le_bytes());
        out.extend_from_slice(&fill_opacity.to_le_bytes());
        out
    }

    #[test]
    fn named_heatmap_plane_uses_kind_2() {
        let mut facts = header(
            XYHF_FAMILY_HEATMAP,
            XYHF_HAS_GRID | XYHF_HAS_NAMED_CMAP | XYHF_HAS_DOMAIN,
            1,
            2,
            0.0,
            1.0,
            f64::NAN,
            f64::NAN,
        );
        facts.extend_from_slice(&0.25f64.to_le_bytes());
        facts.extend_from_slice(&0.75f64.to_le_bytes());
        let name = b"viridis";
        facts.extend_from_slice(&(name.len() as u32).to_le_bytes());
        facts.extend_from_slice(name);
        let plane = pack_heatmap_facts(&facts).unwrap();
        assert_eq!(
            u32::from_le_bytes(plane[16..20].try_into().unwrap()),
            XYHP_PAINT_NAMED
        );
        assert_eq!(&plane[24 + 24 + 16..], name);
    }

    #[test]
    fn truecolor_without_rgba_grid_skips_paint() {
        let facts = header(
            XYHF_FAMILY_HEATMAP,
            XYHF_HAS_TRUECOLOR,
            1,
            1,
            f64::NAN,
            f64::NAN,
            f64::NAN,
            f64::NAN,
        );
        assert!(pack_heatmap_facts(&facts).unwrap().is_empty());
    }

    #[test]
    fn density_constant_color_beats_named_colormap() {
        let mut facts = header(
            XYHF_FAMILY_DENSITY,
            XYHF_HAS_ENCODED | XYHF_HAS_NAMED_CMAP | XYHF_HAS_COLOR_CH | XYHF_HAS_OPACITY,
            1,
            1,
            10.0,
            f64::NAN,
            0.5,
            f64::NAN,
        );
        facts.push(7);
        let name = b"plasma";
        facts.extend_from_slice(&(name.len() as u32).to_le_bytes());
        facts.extend_from_slice(name);
        let color = b"#ff0000";
        facts.extend_from_slice(&(color.len() as u32).to_le_bytes());
        facts.extend_from_slice(color);
        let plane = pack_heatmap_facts(&facts).unwrap();
        assert_eq!(
            u32::from_le_bytes(plane[16..20].try_into().unwrap()),
            XYHP_PAINT_DENSITY
        );
        assert_eq!(&plane[plane.len() - 6..], &[255, 0, 0, 255, 0, 0]);
        let opacity = f64::from_le_bytes(plane[32..40].try_into().unwrap());
        assert!((opacity - 0.5).abs() < 1e-12);
    }

    #[test]
    fn density_composes_default_opacity() {
        let mut facts = header(
            XYHF_FAMILY_DENSITY,
            XYHF_HAS_ENCODED,
            1,
            1,
            4.0,
            f64::NAN,
            f64::NAN,
            f64::NAN,
        );
        facts.push(3);
        let plane = pack_heatmap_facts(&facts).unwrap();
        let opacity = f64::from_le_bytes(plane[32..40].try_into().unwrap());
        assert!((opacity - 0.85).abs() < 1e-12);
        assert_eq!(&plane[plane.len() - 7..], b"viridis");
    }
}
