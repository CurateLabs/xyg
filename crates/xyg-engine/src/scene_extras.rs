//! Compact Figure→Scene extras packing (M2 #271).
//!
//! Hosts pack authored dash/linecap/marker_path/gradient facts as XYSS v1 plus
//! already-framed XYPL bytes. ABI 150 wraps framed XYHP; ABI 161 wraps XYHP
//! from packed XYSD planes so hosts do not unpack sidecar paint. Rust owns
//! XYDS/XYLC/XYMP/XYGR/XYMG table layout, concat order, omit-empty rules, and XYEX
//! wrapping so Python and Node cannot drift on the extras pointer. Encoded
//! Scene v31 keeps XYMG (glyph sidecar) like XYGR so SVG/raster can emit text
//! markers. ABI 170 admits constant scatter `marker_glyph`.

use crate::polar::{XYPL_MAGIC, XYPL_V1_BYTES};
use crate::scene::{
    MAX_SCENE_STYLES, XYDS_MAGIC, XYDS_MAX_VALUES, XYDS_VERSION, XYEX_MAGIC, XYEX_VERSION,
    XYEX_VERSION_DASH, XYGR_DIR_LEFT, XYGR_FLAG_PLOT_SPACE, XYGR_MAGIC, XYGR_MAX_STOPS,
    XYGR_VERSION, XYHP_MAGIC, XYLC_MAGIC, XYLC_VERSION, XYMG_MAGIC, XYMG_VERSION, XYMP_MAGIC,
    XYMP_MAX_CONTOURS, XYMP_MAX_VERTICES, XYMP_VERSION, XYMP_VERTEX_LIMIT,
};

pub const XYSS_MAGIC: &[u8; 4] = b"XYSS";
pub const XYSS_VERSION: u32 = 1;
pub const XYSS_V1_HEADER_BYTES: usize = 16;
pub const XYSS_RECORD_PREFIX_BYTES: usize = 48;

pub const XYSS_HAS_DASH: u8 = 1 << 0;
pub const XYSS_HAS_CAP: u8 = 1 << 1;
pub const XYSS_HAS_MARKER: u8 = 1 << 2;
pub const XYSS_HAS_GRAD: u8 = 1 << 3;
pub const XYSS_HAS_GLYPH: u8 = 1 << 4;

const LINECAP_BUTT: u8 = 0;
const LINECAP_SQUARE: u8 = 2;

/// Why an extras/sidecar packing request was rejected. Discriminants are the
/// C-ABI error codes (returned negated by `xyg_scene_pack_scene_extras`).
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ExtrasError {
    Length = 1,
    Version = 2,
    Limit = 3,
    Output = 4,
    Shape = 5,
    Payload = 6,
}

fn read_u32(bytes: &[u8], offset: usize) -> Result<u32, ExtrasError> {
    Ok(u32::from_le_bytes(
        bytes
            .get(offset..offset + 4)
            .ok_or(ExtrasError::Length)?
            .try_into()
            .map_err(|_| ExtrasError::Length)?,
    ))
}

fn take<'a>(rest: &mut &'a [u8], n: usize) -> Result<&'a [u8], ExtrasError> {
    if rest.len() < n {
        return Err(ExtrasError::Length);
    }
    let (head, tail) = rest.split_at(n);
    *rest = tail;
    Ok(head)
}

struct DashEntry {
    style_ref: u32,
    count: u8,
    values: [f32; 8],
}

struct CapEntry {
    style_ref: u32,
    cap: u8,
}

struct MarkerEntry {
    style_ref: u32,
    filled: bool,
    contours: Vec<Vec<(f64, f64)>>,
}

struct GradEntry {
    style_ref: u32,
    plot_space: bool,
    dir: u8,
    stops: Vec<(f32, [u8; 4])>,
}

struct GlyphEntry {
    style_ref: u32,
    glyph: Vec<u8>,
}

fn encode_xyds(entries: &[DashEntry]) -> Result<Vec<u8>, ExtrasError> {
    if entries.is_empty() {
        return Ok(Vec::new());
    }
    if entries.len() > MAX_SCENE_STYLES {
        return Err(ExtrasError::Limit);
    }
    let mut out = Vec::from(*XYDS_MAGIC);
    out.extend_from_slice(&XYDS_VERSION.to_le_bytes());
    out.extend_from_slice(&(entries.len() as u32).to_le_bytes());
    out.extend_from_slice(&0u32.to_le_bytes());
    let mut seen = std::collections::BTreeSet::new();
    for entry in entries {
        if entry.count < 2
            || entry.count as usize > XYDS_MAX_VALUES
            || !seen.insert(entry.style_ref)
        {
            return Err(ExtrasError::Payload);
        }
        out.extend_from_slice(&entry.style_ref.to_le_bytes());
        out.extend_from_slice(&(u32::from(entry.count)).to_le_bytes());
        for index in 0..entry.count as usize {
            let value = entry.values[index];
            if !value.is_finite() || value <= 0.0 {
                return Err(ExtrasError::Payload);
            }
            out.extend_from_slice(&value.to_le_bytes());
        }
    }
    Ok(out)
}

fn encode_xylc(entries: &[CapEntry]) -> Result<Vec<u8>, ExtrasError> {
    if entries.is_empty() {
        return Ok(Vec::new());
    }
    if entries.len() > MAX_SCENE_STYLES {
        return Err(ExtrasError::Limit);
    }
    let mut out = Vec::from(*XYLC_MAGIC);
    out.extend_from_slice(&XYLC_VERSION.to_le_bytes());
    out.extend_from_slice(&(entries.len() as u32).to_le_bytes());
    out.extend_from_slice(&0u32.to_le_bytes());
    let mut seen = std::collections::BTreeSet::new();
    for entry in entries {
        if (entry.cap != LINECAP_BUTT && entry.cap != LINECAP_SQUARE)
            || !seen.insert(entry.style_ref)
        {
            return Err(ExtrasError::Payload);
        }
        out.extend_from_slice(&entry.style_ref.to_le_bytes());
        out.push(entry.cap);
        out.extend_from_slice(&[0u8, 0, 0]);
    }
    Ok(out)
}

fn encode_xymp(entries: &[MarkerEntry]) -> Result<Vec<u8>, ExtrasError> {
    if entries.is_empty() {
        return Ok(Vec::new());
    }
    if entries.len() > MAX_SCENE_STYLES {
        return Err(ExtrasError::Limit);
    }
    let mut out = Vec::from(*XYMP_MAGIC);
    out.extend_from_slice(&XYMP_VERSION.to_le_bytes());
    out.extend_from_slice(&(entries.len() as u32).to_le_bytes());
    out.extend_from_slice(&0u32.to_le_bytes());
    let mut seen = std::collections::BTreeSet::new();
    for entry in entries {
        let n_vertices: usize = entry.contours.iter().map(Vec::len).sum();
        if entry.contours.is_empty()
            || entry.contours.len() > XYMP_MAX_CONTOURS
            || n_vertices < 2
            || n_vertices > XYMP_MAX_VERTICES
            || !seen.insert(entry.style_ref)
        {
            return Err(ExtrasError::Payload);
        }
        out.extend_from_slice(&entry.style_ref.to_le_bytes());
        out.extend_from_slice(&(u32::from(entry.filled)).to_le_bytes());
        out.extend_from_slice(&(entry.contours.len() as u32).to_le_bytes());
        out.extend_from_slice(&(n_vertices as u32).to_le_bytes());
        for contour in &entry.contours {
            if contour.len() < 2 || (entry.filled && contour.len() < 3) {
                return Err(ExtrasError::Payload);
            }
            out.extend_from_slice(&(contour.len() as u32).to_le_bytes());
            out.extend_from_slice(&0u32.to_le_bytes());
            for &(x, y) in contour {
                if !x.is_finite()
                    || !y.is_finite()
                    || x.abs() > XYMP_VERTEX_LIMIT
                    || y.abs() > XYMP_VERTEX_LIMIT
                {
                    return Err(ExtrasError::Payload);
                }
                out.extend_from_slice(&x.to_le_bytes());
                out.extend_from_slice(&y.to_le_bytes());
            }
        }
    }
    Ok(out)
}

fn encode_xygr(entries: &[GradEntry]) -> Result<Vec<u8>, ExtrasError> {
    if entries.is_empty() {
        return Ok(Vec::new());
    }
    if entries.len() > MAX_SCENE_STYLES {
        return Err(ExtrasError::Limit);
    }
    let mut out = Vec::from(*XYGR_MAGIC);
    out.extend_from_slice(&XYGR_VERSION.to_le_bytes());
    out.extend_from_slice(&(entries.len() as u32).to_le_bytes());
    out.extend_from_slice(&0u32.to_le_bytes());
    let mut seen = std::collections::BTreeSet::new();
    for entry in entries {
        if entry.stops.len() < 2
            || entry.stops.len() > XYGR_MAX_STOPS
            || entry.dir > XYGR_DIR_LEFT as u8
            || !seen.insert(entry.style_ref)
        {
            return Err(ExtrasError::Payload);
        }
        let mut flags = u32::from(entry.dir);
        if entry.plot_space {
            flags |= XYGR_FLAG_PLOT_SPACE;
        }
        out.extend_from_slice(&entry.style_ref.to_le_bytes());
        out.extend_from_slice(&flags.to_le_bytes());
        out.extend_from_slice(&(entry.stops.len() as u32).to_le_bytes());
        out.extend_from_slice(&0u32.to_le_bytes());
        let mut prev_t = f32::NEG_INFINITY;
        for &(t, rgba) in &entry.stops {
            if !t.is_finite() || !(0.0..=1.0).contains(&t) || t < prev_t {
                return Err(ExtrasError::Payload);
            }
            out.extend_from_slice(&t.to_le_bytes());
            out.extend_from_slice(&rgba);
            prev_t = t;
        }
    }
    Ok(out)
}

fn encode_xymg(entries: &[GlyphEntry]) -> Result<Vec<u8>, ExtrasError> {
    if entries.is_empty() {
        return Ok(Vec::new());
    }
    if entries.len() > MAX_SCENE_STYLES {
        return Err(ExtrasError::Limit);
    }
    let mut out = Vec::from(*XYMG_MAGIC);
    out.extend_from_slice(&XYMG_VERSION.to_le_bytes());
    out.extend_from_slice(&(entries.len() as u32).to_le_bytes());
    out.extend_from_slice(&0u32.to_le_bytes());
    let mut seen = std::collections::BTreeSet::new();
    for entry in entries {
        if entry.glyph.is_empty()
            || entry.glyph.len() > crate::scene::XYMG_MAX_UTF8
            || std::str::from_utf8(&entry.glyph)
                .ok()
                .and_then(|text| {
                    let mut chars = text.chars();
                    let ch = chars.next()?;
                    (chars.next().is_none() && ch != '\0' && ch != '\n' && ch != '\r').then_some(())
                })
                .is_none()
            || !seen.insert(entry.style_ref)
        {
            return Err(ExtrasError::Payload);
        }
        out.extend_from_slice(&entry.style_ref.to_le_bytes());
        out.extend_from_slice(&(entry.glyph.len() as u32).to_le_bytes());
        let mut padded = [0u8; 4];
        padded[..entry.glyph.len()].copy_from_slice(&entry.glyph);
        out.extend_from_slice(&padded);
    }
    Ok(out)
}

fn wrap_extras(polar: &[u8], paint: &[u8], dash: &[u8]) -> Result<Vec<u8>, ExtrasError> {
    if polar.is_empty() && paint.is_empty() && dash.is_empty() {
        return Ok(Vec::new());
    }
    if !polar.is_empty() {
        if polar.len() != XYPL_V1_BYTES || polar.get(..4) != Some(&XYPL_MAGIC[..]) {
            return Err(ExtrasError::Shape);
        }
    }
    if !paint.is_empty() && paint.get(..4) != Some(&XYHP_MAGIC[..]) {
        return Err(ExtrasError::Shape);
    }
    if polar.is_empty() && paint.is_empty() {
        return Ok(dash.to_vec());
    }
    if paint.is_empty() && dash.is_empty() {
        return Ok(polar.to_vec());
    }
    if polar.is_empty() && dash.is_empty() {
        return Ok(paint.to_vec());
    }
    if dash.is_empty() {
        let mut out = Vec::with_capacity(16 + polar.len() + paint.len());
        out.extend_from_slice(XYEX_MAGIC);
        out.extend_from_slice(&XYEX_VERSION.to_le_bytes());
        out.extend_from_slice(&(polar.len() as u32).to_le_bytes());
        out.extend_from_slice(&(paint.len() as u32).to_le_bytes());
        out.extend_from_slice(polar);
        out.extend_from_slice(paint);
        return Ok(out);
    }
    let mut out = Vec::with_capacity(20 + polar.len() + paint.len() + dash.len());
    out.extend_from_slice(XYEX_MAGIC);
    out.extend_from_slice(&XYEX_VERSION_DASH.to_le_bytes());
    out.extend_from_slice(&(polar.len() as u32).to_le_bytes());
    out.extend_from_slice(&(paint.len() as u32).to_le_bytes());
    out.extend_from_slice(&(dash.len() as u32).to_le_bytes());
    out.extend_from_slice(polar);
    out.extend_from_slice(paint);
    out.extend_from_slice(dash);
    Ok(out)
}

fn parse_xyss(
    bytes: &[u8],
) -> Result<
    (
        Vec<DashEntry>,
        Vec<CapEntry>,
        Vec<MarkerEntry>,
        Vec<GradEntry>,
        Vec<GlyphEntry>,
    ),
    ExtrasError,
> {
    if bytes.is_empty() {
        return Ok((Vec::new(), Vec::new(), Vec::new(), Vec::new(), Vec::new()));
    }
    if bytes.len() < XYSS_V1_HEADER_BYTES || bytes.get(..4) != Some(&XYSS_MAGIC[..]) {
        return Err(ExtrasError::Length);
    }
    if read_u32(bytes, 4)? != XYSS_VERSION {
        return Err(ExtrasError::Version);
    }
    let n_records = read_u32(bytes, 8)? as usize;
    if read_u32(bytes, 12)? != 0 || n_records > MAX_SCENE_STYLES {
        return Err(ExtrasError::Limit);
    }
    let mut rest = bytes.get(XYSS_V1_HEADER_BYTES..).unwrap_or(&[]);
    let mut dashes = Vec::new();
    let mut caps = Vec::new();
    let mut markers = Vec::new();
    let mut grads = Vec::new();
    let mut glyphs = Vec::new();
    let mut seen = std::collections::BTreeSet::new();
    for _ in 0..n_records {
        let prefix = take(&mut rest, XYSS_RECORD_PREFIX_BYTES)?;
        let style_ref = read_u32(prefix, 0)?;
        if !seen.insert(style_ref) {
            return Err(ExtrasError::Payload);
        }
        let flags = prefix[4];
        let dash_count = prefix[5];
        let linecap = prefix[6];
        let n_contours = prefix[7] as usize;
        let n_stops = prefix[8] as usize;
        let grad_dir = prefix[9];
        let plot_space = prefix[10];
        let filled = prefix[11] != 0;
        if flags
            & !(XYSS_HAS_DASH | XYSS_HAS_CAP | XYSS_HAS_MARKER | XYSS_HAS_GRAD | XYSS_HAS_GLYPH)
            != 0
            || flags == 0
            || (flags & XYSS_HAS_MARKER != 0 && flags & XYSS_HAS_GLYPH != 0)
            || (flags & XYSS_HAS_MARKER == 0 && flags & XYSS_HAS_GLYPH == 0 && n_contours != 0)
            || (flags & XYSS_HAS_GRAD == 0 && n_stops != 0)
            || (flags & XYSS_HAS_MARKER != 0 && n_contours == 0)
            || (flags & XYSS_HAS_GLYPH != 0 && !(1..=4).contains(&n_contours))
            || (flags & XYSS_HAS_GRAD != 0 && n_stops == 0)
        {
            return Err(ExtrasError::Payload);
        }
        if flags & XYSS_HAS_DASH != 0 {
            if dash_count < 2 || dash_count as usize > XYDS_MAX_VALUES {
                return Err(ExtrasError::Payload);
            }
            let mut values = [0.0f32; 8];
            for index in 0..dash_count as usize {
                let at = 16 + index * 4;
                values[index] = f32::from_le_bytes(
                    prefix[at..at + 4]
                        .try_into()
                        .map_err(|_| ExtrasError::Length)?,
                );
            }
            dashes.push(DashEntry {
                style_ref,
                count: dash_count,
                values,
            });
        }
        if flags & XYSS_HAS_CAP != 0 {
            caps.push(CapEntry {
                style_ref,
                cap: linecap,
            });
        }
        if flags & XYSS_HAS_MARKER != 0 {
            let mut contours = Vec::with_capacity(n_contours);
            for _ in 0..n_contours {
                let header = take(&mut rest, 8)?;
                let n_pairs = read_u32(header, 0)? as usize;
                if read_u32(header, 4)? != 0 {
                    return Err(ExtrasError::Payload);
                }
                let coords = take(
                    &mut rest,
                    n_pairs.checked_mul(16).ok_or(ExtrasError::Limit)?,
                )?;
                let mut contour = Vec::with_capacity(n_pairs);
                for index in 0..n_pairs {
                    let at = index * 16;
                    let x = f64::from_le_bytes(
                        coords[at..at + 8]
                            .try_into()
                            .map_err(|_| ExtrasError::Length)?,
                    );
                    let y = f64::from_le_bytes(
                        coords[at + 8..at + 16]
                            .try_into()
                            .map_err(|_| ExtrasError::Length)?,
                    );
                    contour.push((x, y));
                }
                contours.push(contour);
            }
            markers.push(MarkerEntry {
                style_ref,
                filled,
                contours,
            });
        }
        if flags & XYSS_HAS_GLYPH != 0 {
            let raw = take(&mut rest, n_contours)?;
            if std::str::from_utf8(raw)
                .ok()
                .and_then(|text| {
                    let mut chars = text.chars();
                    let ch = chars.next()?;
                    (chars.next().is_none() && ch != '\0' && ch != '\n' && ch != '\r').then_some(())
                })
                .is_none()
            {
                return Err(ExtrasError::Payload);
            }
            glyphs.push(GlyphEntry {
                style_ref,
                glyph: raw.to_vec(),
            });
        }
        if flags & XYSS_HAS_GRAD != 0 {
            let raw = take(&mut rest, n_stops.checked_mul(8).ok_or(ExtrasError::Limit)?)?;
            let mut stops = Vec::with_capacity(n_stops);
            for index in 0..n_stops {
                let at = index * 8;
                let t = f32::from_le_bytes(
                    raw[at..at + 4]
                        .try_into()
                        .map_err(|_| ExtrasError::Length)?,
                );
                stops.push((t, [raw[at + 4], raw[at + 5], raw[at + 6], raw[at + 7]]));
            }
            grads.push(GradEntry {
                style_ref,
                plot_space: plot_space != 0,
                dir: grad_dir,
                stops,
            });
        }
    }
    if !rest.is_empty() {
        return Err(ExtrasError::Length);
    }
    Ok((dashes, caps, markers, grads, glyphs))
}

/// Pack polar XYPL, XYHP paint, and XYSS style-sidecar facts into the extras
/// pointer payload (`XYEX` or a raw single sidecar).
pub fn pack_scene_extras(polar: &[u8], paint: &[u8], facts: &[u8]) -> Result<Vec<u8>, ExtrasError> {
    let (dashes, caps, markers, grads, glyphs) = parse_xyss(facts)?;
    let mut dash = encode_xyds(&dashes)?;
    dash.extend_from_slice(&encode_xylc(&caps)?);
    dash.extend_from_slice(&encode_xymp(&markers)?);
    dash.extend_from_slice(&encode_xygr(&grads)?);
    dash.extend_from_slice(&encode_xymg(&glyphs)?);
    wrap_extras(polar, paint, &dash)
}

fn map_xysd(error: crate::scene_trace_sidecars::TraceSidecarsError) -> ExtrasError {
    match error.code {
        crate::scene_trace_sidecars::TraceSidecarsCode::Version => ExtrasError::Version,
        crate::scene_trace_sidecars::TraceSidecarsCode::Limit => ExtrasError::Limit,
        _ => ExtrasError::Length,
    }
}

fn xyhp_envelope_from_xysd(xysd: &[u8]) -> Result<Vec<u8>, ExtrasError> {
    let records = crate::scene_trace_sidecars::parse_xysd_records(xysd).map_err(map_xysd)?;
    let mut planes = Vec::new();
    for record in &records {
        if !record.plane.is_empty() {
            planes.push(record.plane.as_slice());
        }
    }
    if planes.is_empty() {
        return Ok(Vec::new());
    }
    let mut out = vec![0u8; 16];
    out[..4].copy_from_slice(XYHP_MAGIC);
    out[4..8].copy_from_slice(&1u32.to_le_bytes());
    out[8..12].copy_from_slice(&(planes.len() as u32).to_le_bytes());
    for plane in planes {
        out.extend_from_slice(plane);
    }
    Ok(out)
}

/// Pack polar XYPL, XYSD paint planes, and XYSS facts into extras.
///
/// Rust wraps nonempty XYSD planes as XYHP v1 so hosts do not unpack sidecar
/// paint on the product path.
pub fn pack_scene_extras_from_sidecars(
    polar: &[u8],
    xysd: &[u8],
    facts: &[u8],
) -> Result<Vec<u8>, ExtrasError> {
    let paint = xyhp_envelope_from_xysd(xysd)?;
    pack_scene_extras(polar, &paint, facts)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn xyss_header(n: u32) -> Vec<u8> {
        let mut out = Vec::from(*XYSS_MAGIC);
        out.extend_from_slice(&XYSS_VERSION.to_le_bytes());
        out.extend_from_slice(&n.to_le_bytes());
        out.extend_from_slice(&0u32.to_le_bytes());
        out
    }

    fn dash_record(style_ref: u32, values: &[f32]) -> Vec<u8> {
        let mut prefix = vec![0u8; XYSS_RECORD_PREFIX_BYTES];
        prefix[..4].copy_from_slice(&style_ref.to_le_bytes());
        prefix[4] = XYSS_HAS_DASH;
        prefix[5] = values.len() as u8;
        prefix[6] = 255;
        for (index, value) in values.iter().enumerate() {
            prefix[16 + index * 4..20 + index * 4].copy_from_slice(&value.to_le_bytes());
        }
        prefix
    }

    #[test]
    fn dash_facts_encode_xyds_and_wrap_as_raw() {
        let mut facts = xyss_header(1);
        facts.extend_from_slice(&dash_record(0, &[4.0, 2.0]));
        let extras = pack_scene_extras(&[], &[], &facts).unwrap();
        assert_eq!(&extras[..4], XYDS_MAGIC);
        assert_eq!(u32::from_le_bytes(extras[8..12].try_into().unwrap()), 1);
    }

    #[test]
    fn empty_inputs_are_empty_extras() {
        assert!(pack_scene_extras(&[], &[], &[]).unwrap().is_empty());
    }

    #[test]
    fn polar_and_paint_wrap_xyex_v1() {
        let mut polar = vec![0u8; XYPL_V1_BYTES];
        polar[..4].copy_from_slice(XYPL_MAGIC);
        let mut paint = vec![0u8; 16];
        paint[..4].copy_from_slice(XYHP_MAGIC);
        let extras = pack_scene_extras(&polar, &paint, &[]).unwrap();
        assert_eq!(&extras[..4], XYEX_MAGIC);
        assert_eq!(u32::from_le_bytes(extras[4..8].try_into().unwrap()), 1);
        assert_eq!(
            u32::from_le_bytes(extras[8..12].try_into().unwrap()),
            XYPL_V1_BYTES as u32
        );
    }

    #[test]
    fn dash_with_paint_wraps_xyex_v2() {
        let mut paint = vec![0u8; 16];
        paint[..4].copy_from_slice(XYHP_MAGIC);
        let mut facts = xyss_header(1);
        facts.extend_from_slice(&dash_record(3, &[1.0, 3.0, 1.0, 3.0]));
        let extras = pack_scene_extras(&[], &paint, &facts).unwrap();
        assert_eq!(&extras[..4], XYEX_MAGIC);
        assert_eq!(u32::from_le_bytes(extras[4..8].try_into().unwrap()), 2);
        assert_eq!(u32::from_le_bytes(extras[12..16].try_into().unwrap()), 16);
        assert!(u32::from_le_bytes(extras[16..20].try_into().unwrap()) > 0);
    }

    fn cap_record(style_ref: u32, cap: u8) -> Vec<u8> {
        let mut prefix = vec![0u8; XYSS_RECORD_PREFIX_BYTES];
        prefix[..4].copy_from_slice(&style_ref.to_le_bytes());
        prefix[4] = XYSS_HAS_CAP;
        prefix[6] = cap;
        prefix
    }

    fn marker_record(style_ref: u32) -> Vec<u8> {
        let mut prefix = vec![0u8; XYSS_RECORD_PREFIX_BYTES];
        prefix[..4].copy_from_slice(&style_ref.to_le_bytes());
        prefix[4] = XYSS_HAS_MARKER;
        prefix[7] = 1;
        prefix[11] = 1;
        let mut out = prefix;
        out.extend_from_slice(&3u32.to_le_bytes());
        out.extend_from_slice(&0u32.to_le_bytes());
        for &(x, y) in &[(-0.2f64, -0.2f64), (0.2, -0.2), (0.0, 0.2)] {
            out.extend_from_slice(&x.to_le_bytes());
            out.extend_from_slice(&y.to_le_bytes());
        }
        out
    }

    fn grad_record(style_ref: u32) -> Vec<u8> {
        let mut prefix = vec![0u8; XYSS_RECORD_PREFIX_BYTES];
        prefix[..4].copy_from_slice(&style_ref.to_le_bytes());
        prefix[4] = XYSS_HAS_GRAD;
        prefix[8] = 2;
        prefix[9] = 0;
        let mut out = prefix;
        out.extend_from_slice(&0.0f32.to_le_bytes());
        out.extend_from_slice(&[255, 0, 0, 255]);
        out.extend_from_slice(&1.0f32.to_le_bytes());
        out.extend_from_slice(&[0, 0, 255, 255]);
        out
    }

    #[test]
    fn linecap_facts_encode_xylc() {
        let mut facts = xyss_header(1);
        facts.extend_from_slice(&cap_record(1, LINECAP_BUTT));
        let extras = pack_scene_extras(&[], &[], &facts).unwrap();
        assert_eq!(&extras[..4], XYLC_MAGIC);
        assert_eq!(extras[16], 1);
        assert_eq!(extras[20], LINECAP_BUTT);
    }

    #[test]
    fn marker_and_gradient_facts_concat_in_sidecar_order() {
        let mut facts = xyss_header(2);
        facts.extend_from_slice(&marker_record(0));
        facts.extend_from_slice(&grad_record(1));
        let extras = pack_scene_extras(&[], &[], &facts).unwrap();
        assert_eq!(&extras[..4], XYMP_MAGIC);
        assert!(extras.windows(4).any(|window| window == XYGR_MAGIC));
    }

    fn glyph_record(style_ref: u32, glyph: &str) -> Vec<u8> {
        let mut prefix = vec![0u8; XYSS_RECORD_PREFIX_BYTES];
        prefix[..4].copy_from_slice(&style_ref.to_le_bytes());
        prefix[4] = XYSS_HAS_GLYPH;
        prefix[7] = glyph.len() as u8;
        let mut out = prefix;
        out.extend_from_slice(glyph.as_bytes());
        out
    }

    #[test]
    fn glyph_facts_encode_xymg() {
        let mut facts = xyss_header(1);
        facts.extend_from_slice(&glyph_record(0, "A"));
        let extras = pack_scene_extras(&[], &[], &facts).unwrap();
        assert_eq!(&extras[..4], XYMG_MAGIC);
        assert_eq!(u32::from_le_bytes(extras[8..12].try_into().unwrap()), 1);
    }

    #[test]
    fn duplicate_style_ref_is_payload() {
        let mut facts = xyss_header(2);
        facts.extend_from_slice(&dash_record(0, &[2.0, 1.0]));
        facts.extend_from_slice(&cap_record(0, LINECAP_SQUARE));
        assert_eq!(
            pack_scene_extras(&[], &[], &facts),
            Err(ExtrasError::Payload)
        );
    }

    #[test]
    fn invalid_polar_envelope_is_shape() {
        let polar = vec![0u8; 8];
        assert_eq!(pack_scene_extras(&polar, &[], &[]), Err(ExtrasError::Shape));
    }

    fn xysd_with_plane(plane: &[u8]) -> Vec<u8> {
        let mut out = vec![0u8; 16];
        out[..4].copy_from_slice(b"XYSD");
        out[4..8].copy_from_slice(&1u32.to_le_bytes());
        out[8..12].copy_from_slice(&1u32.to_le_bytes());
        let mut prefix = vec![0u8; 48];
        prefix[32..36].copy_from_slice(&(plane.len() as u32).to_le_bytes());
        out.extend_from_slice(&prefix);
        out.extend_from_slice(plane);
        out
    }

    #[test]
    fn sidecars_wrap_xysd_planes_as_xyhp() {
        let mut plane = Vec::new();
        plane.extend_from_slice(&9u64.to_le_bytes());
        plane.extend_from_slice(&1u32.to_le_bytes());
        plane.extend_from_slice(&1u32.to_le_bytes());
        plane.extend_from_slice(&0u32.to_le_bytes());
        plane.extend_from_slice(&4u32.to_le_bytes());
        plane.extend_from_slice(&[1, 2, 3, 4]);
        let xysd = xysd_with_plane(&plane);
        let extras = pack_scene_extras_from_sidecars(&[], &xysd, &[]).unwrap();
        assert_eq!(&extras[..4], XYHP_MAGIC);
        assert_eq!(u32::from_le_bytes(extras[4..8].try_into().unwrap()), 1);
        assert_eq!(u32::from_le_bytes(extras[8..12].try_into().unwrap()), 1);
        assert_eq!(&extras[16..], plane.as_slice());
        let mut paint = vec![0u8; 16];
        paint[..4].copy_from_slice(XYHP_MAGIC);
        paint[4..8].copy_from_slice(&1u32.to_le_bytes());
        paint[8..12].copy_from_slice(&1u32.to_le_bytes());
        paint.extend_from_slice(&plane);
        assert_eq!(extras, pack_scene_extras(&[], &paint, &[]).unwrap());
    }

    #[test]
    fn empty_sidecars_match_empty_paint() {
        assert!(pack_scene_extras_from_sidecars(&[], &[], &[])
            .unwrap()
            .is_empty());
    }
}
