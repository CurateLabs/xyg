//! Compact Figure→Scene XYSS packing (M2 #271).
//!
//! Hosts pass XYSD v1 trace sidecars plus an optional XYAO v1 annotation
//! envelope. Rust owns dash/linecap/marker/gradient XYSS record construction,
//! including annotation style_ref bases and omit-empty records, so Python and
//! Node cannot drift. Encoded Scene v31 is unchanged. Hosts splice annotation
//! styles and mark rows through ABI 159 (`XYAS`) and encode through ABI 160.

use crate::scene::{marker_glyph_text, XYDS_MAX_VALUES};
use crate::scene_annotations::{XYAO_MAGIC, XYAO_STYLE_BYTES, XYAO_V1_HEADER_BYTES, XYAO_VERSION};
use crate::scene_extras::{
    XYSS_HAS_CAP, XYSS_HAS_DASH, XYSS_HAS_GLYPH, XYSS_HAS_GRAD, XYSS_HAS_MARKER, XYSS_MAGIC,
    XYSS_RECORD_PREFIX_BYTES, XYSS_VERSION,
};
use crate::scene_trace_sidecars::{XYSD_HEADER_BYTES, XYSD_MAGIC, XYSD_PREFIX_BYTES, XYSD_VERSION};

const MAX_TRACES: usize = 4_096;
const LINECAP_NONE: u8 = 255;
const LINECAP_BUTT: u8 = 0;
const LINECAP_SQUARE: u8 = 2;

/// Why an XYSS style-sidecar pack request was rejected. Discriminants are the
/// C-ABI error codes (returned negated by `xyg_scene_pack_style_sidecars`).
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum StyleSidecarsCode {
    Length = 1,
    Version = 2,
    Limit = 3,
    Output = 4,
    Payload = 5,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct StyleSidecarsError {
    pub code: StyleSidecarsCode,
    pub index: u32,
}

impl StyleSidecarsError {
    fn new(code: StyleSidecarsCode, index: usize) -> Self {
        Self {
            code,
            index: index as u32,
        }
    }
}

fn read_u32(bytes: &[u8], offset: usize) -> Result<u32, StyleSidecarsError> {
    Ok(u32::from_le_bytes(
        bytes
            .get(offset..offset + 4)
            .ok_or(StyleSidecarsError::new(StyleSidecarsCode::Length, 0))?
            .try_into()
            .map_err(|_| StyleSidecarsError::new(StyleSidecarsCode::Length, 0))?,
    ))
}

fn take<'a>(rest: &mut &'a [u8], n: usize, index: usize) -> Result<&'a [u8], StyleSidecarsError> {
    if rest.len() < n {
        return Err(StyleSidecarsError::new(StyleSidecarsCode::Length, index));
    }
    let (head, tail) = rest.split_at(n);
    *rest = tail;
    Ok(head)
}

struct Record {
    style_ref: u32,
    flags: u8,
    dash_count: u8,
    linecap: u8,
    n_contours: u8,
    n_stops: u8,
    grad_dir: u8,
    plot_space: u8,
    filled: u8,
    dash: [f32; 8],
    remainder: Vec<u8>,
}

fn push_dash(record: &mut Record, values: &[f64], index: usize) -> Result<(), StyleSidecarsError> {
    if values.is_empty() {
        return Ok(());
    }
    if values.len() > XYDS_MAX_VALUES {
        return Err(StyleSidecarsError::new(StyleSidecarsCode::Limit, index));
    }
    record.flags |= XYSS_HAS_DASH;
    record.dash_count = values.len() as u8;
    for (slot, value) in record.dash.iter_mut().zip(values.iter()) {
        *slot = *value as f32;
    }
    Ok(())
}

fn push_cap(record: &mut Record, linecap: u8) {
    if linecap == LINECAP_BUTT || linecap == LINECAP_SQUARE {
        record.flags |= XYSS_HAS_CAP;
        record.linecap = linecap;
    }
}

fn parse_marker(blob: &[u8], record: &mut Record, index: usize) -> Result<(), StyleSidecarsError> {
    if blob.is_empty() {
        return Ok(());
    }
    if let Some(glyph) = marker_glyph_text(blob) {
        record.flags |= XYSS_HAS_GLYPH;
        record.n_contours = glyph.len() as u8;
        record.remainder.extend_from_slice(glyph.as_bytes());
        return Ok(());
    }
    if blob.len() < 8 {
        return Err(StyleSidecarsError::new(StyleSidecarsCode::Payload, index));
    }
    let n_contours = u32::from_le_bytes(blob[0..4].try_into().unwrap()) as usize;
    let filled = blob[4] != 0;
    let mut at = 8usize;
    let mut remainder = Vec::new();
    for _ in 0..n_contours {
        if at + 4 > blob.len() {
            return Err(StyleSidecarsError::new(StyleSidecarsCode::Payload, index));
        }
        let n_values = u32::from_le_bytes(blob[at..at + 4].try_into().unwrap()) as usize;
        at += 4;
        let bytes = n_values
            .checked_mul(8)
            .ok_or(StyleSidecarsError::new(StyleSidecarsCode::Limit, index))?;
        if at + bytes > blob.len() || n_values % 2 != 0 {
            return Err(StyleSidecarsError::new(StyleSidecarsCode::Payload, index));
        }
        remainder.extend_from_slice(&(n_values as u32 / 2).to_le_bytes());
        remainder.extend_from_slice(&0u32.to_le_bytes());
        remainder.extend_from_slice(&blob[at..at + bytes]);
        at += bytes;
    }
    record.flags |= XYSS_HAS_MARKER;
    record.n_contours = n_contours as u8;
    record.filled = u8::from(filled);
    record.remainder.extend_from_slice(&remainder);
    Ok(())
}

fn parse_gradient(
    blob: &[u8],
    record: &mut Record,
    index: usize,
) -> Result<(), StyleSidecarsError> {
    if blob.is_empty() {
        return Ok(());
    }
    if blob.len() < 4 {
        return Err(StyleSidecarsError::new(StyleSidecarsCode::Payload, index));
    }
    let space = blob[0];
    let dir = blob[1];
    let n_stops = blob[2] as usize;
    let at = 4usize;
    let need = n_stops
        .checked_mul(8)
        .ok_or(StyleSidecarsError::new(StyleSidecarsCode::Limit, index))?;
    if at + need > blob.len() {
        return Err(StyleSidecarsError::new(StyleSidecarsCode::Payload, index));
    }
    record.flags |= XYSS_HAS_GRAD;
    record.n_stops = n_stops as u8;
    record.grad_dir = dir;
    record.plot_space = u8::from(space != 0);
    record.remainder.extend_from_slice(&blob[at..at + need]);
    Ok(())
}

fn decode_f64s(bytes: &[u8], index: usize) -> Result<Vec<f64>, StyleSidecarsError> {
    if bytes.len() % 8 != 0 {
        return Err(StyleSidecarsError::new(StyleSidecarsCode::Length, index));
    }
    Ok(bytes
        .chunks_exact(8)
        .map(|chunk| f64::from_le_bytes(chunk.try_into().unwrap()))
        .collect())
}

fn record_from_xysd(
    prefix: &[u8],
    dash: &[u8],
    marker: &[u8],
    gradient: &[u8],
    style_ref: u32,
    index: usize,
) -> Result<Option<Record>, StyleSidecarsError> {
    let mut record = Record {
        style_ref,
        flags: 0,
        dash_count: 0,
        linecap: LINECAP_NONE,
        n_contours: 0,
        n_stops: 0,
        grad_dir: 0,
        plot_space: 0,
        filled: 0,
        dash: [0.0; 8],
        remainder: Vec::new(),
    };
    let linecap = prefix[16];
    push_dash(&mut record, &decode_f64s(dash, index)?, index)?;
    push_cap(&mut record, linecap);
    parse_marker(marker, &mut record, index)?;
    parse_gradient(gradient, &mut record, index)?;
    if record.flags == 0 {
        return Ok(None);
    }
    Ok(Some(record))
}

fn parse_xysd(bytes: &[u8]) -> Result<Vec<Option<Record>>, StyleSidecarsError> {
    if bytes.len() < XYSD_HEADER_BYTES || bytes.get(..4) != Some(&XYSD_MAGIC[..]) {
        return Err(StyleSidecarsError::new(StyleSidecarsCode::Length, 0));
    }
    if read_u32(bytes, 4)? != XYSD_VERSION {
        return Err(StyleSidecarsError::new(StyleSidecarsCode::Version, 0));
    }
    let n_traces = read_u32(bytes, 8)? as usize;
    if n_traces > MAX_TRACES {
        return Err(StyleSidecarsError::new(StyleSidecarsCode::Limit, 0));
    }
    let mut rest = bytes
        .get(XYSD_HEADER_BYTES..)
        .ok_or(StyleSidecarsError::new(StyleSidecarsCode::Length, 0))?;
    let mut records = Vec::with_capacity(n_traces);
    for index in 0..n_traces {
        let prefix = take(&mut rest, XYSD_PREFIX_BYTES, index)?;
        let dash_len = u32::from_le_bytes(prefix[20..24].try_into().unwrap()) as usize;
        let marker_len = u32::from_le_bytes(prefix[24..28].try_into().unwrap()) as usize;
        let gradient_len = u32::from_le_bytes(prefix[28..32].try_into().unwrap()) as usize;
        let plane_len = u32::from_le_bytes(prefix[32..36].try_into().unwrap()) as usize;
        let name_len = u32::from_le_bytes(prefix[36..40].try_into().unwrap()) as usize;
        let radius_len = u32::from_le_bytes(prefix[40..44].try_into().unwrap()) as usize;
        let dash = take(&mut rest, dash_len, index)?;
        let marker = take(&mut rest, marker_len, index)?;
        let gradient = take(&mut rest, gradient_len, index)?;
        let _plane = take(&mut rest, plane_len, index)?;
        let _name = take(&mut rest, name_len, index)?;
        let _radius = take(&mut rest, radius_len, index)?;
        records.push(record_from_xysd(
            prefix,
            dash,
            marker,
            gradient,
            index as u32,
            index,
        )?);
    }
    if !rest.is_empty() {
        return Err(StyleSidecarsError::new(StyleSidecarsCode::Length, 0));
    }
    Ok(records)
}

fn parse_xyao(bytes: &[u8]) -> Result<Vec<Option<Record>>, StyleSidecarsError> {
    if bytes.is_empty() {
        return Ok(Vec::new());
    }
    if bytes.len() < XYAO_V1_HEADER_BYTES || bytes.get(..4) != Some(&XYAO_MAGIC[..]) {
        return Err(StyleSidecarsError::new(StyleSidecarsCode::Length, 0));
    }
    if read_u32(bytes, 4)? != XYAO_VERSION {
        return Err(StyleSidecarsError::new(StyleSidecarsCode::Version, 0));
    }
    let n_styles = read_u32(bytes, 8)? as usize;
    let n_rows = read_u32(bytes, 12)? as usize;
    let xyad_len = read_u32(bytes, 16)? as usize;
    let style_ref_base = read_u32(bytes, 24)?;
    let mut rest = bytes
        .get(XYAO_V1_HEADER_BYTES..)
        .ok_or(StyleSidecarsError::new(StyleSidecarsCode::Length, 0))?;
    let mut records = Vec::with_capacity(n_styles);
    for index in 0..n_styles {
        let style = take(&mut rest, XYAO_STYLE_BYTES, index)?;
        let dash_count = style[16] as usize;
        let linecap = style[17];
        if dash_count > XYDS_MAX_VALUES {
            return Err(StyleSidecarsError::new(StyleSidecarsCode::Limit, index));
        }
        let mut dash = Vec::with_capacity(dash_count);
        for slot in 0..dash_count {
            let at = 24 + slot * 4;
            dash.push(f32::from_le_bytes(style[at..at + 4].try_into().unwrap()) as f64);
        }
        let mut record = Record {
            style_ref: style_ref_base.saturating_add(index as u32),
            flags: 0,
            dash_count: 0,
            linecap: LINECAP_NONE,
            n_contours: 0,
            n_stops: 0,
            grad_dir: 0,
            plot_space: 0,
            filled: 0,
            dash: [0.0; 8],
            remainder: Vec::new(),
        };
        push_dash(&mut record, &dash, index)?;
        push_cap(&mut record, linecap);
        records.push(if record.flags == 0 {
            None
        } else {
            Some(record)
        });
    }
    let skip = n_rows
        .checked_mul(56)
        .and_then(|n| n.checked_add(xyad_len))
        .ok_or(StyleSidecarsError::new(StyleSidecarsCode::Limit, 0))?;
    let _ = take(&mut rest, skip, 0)?;
    if !rest.is_empty() {
        return Err(StyleSidecarsError::new(StyleSidecarsCode::Length, 0));
    }
    Ok(records)
}

fn encode_xyss(records: &[Record]) -> Vec<u8> {
    if records.is_empty() {
        return Vec::new();
    }
    let mut out = Vec::from(*XYSS_MAGIC);
    out.extend_from_slice(&XYSS_VERSION.to_le_bytes());
    out.extend_from_slice(&(records.len() as u32).to_le_bytes());
    out.extend_from_slice(&0u32.to_le_bytes());
    for record in records {
        let mut prefix = vec![0u8; XYSS_RECORD_PREFIX_BYTES];
        prefix[0..4].copy_from_slice(&record.style_ref.to_le_bytes());
        prefix[4] = record.flags;
        prefix[5] = record.dash_count;
        prefix[6] = record.linecap;
        prefix[7] = record.n_contours;
        prefix[8] = record.n_stops;
        prefix[9] = record.grad_dir;
        prefix[10] = record.plot_space;
        prefix[11] = record.filled;
        for (slot, value) in record.dash.iter().enumerate() {
            let at = 16 + slot * 4;
            prefix[at..at + 4].copy_from_slice(&value.to_le_bytes());
        }
        out.extend_from_slice(&prefix);
        out.extend_from_slice(&record.remainder);
    }
    out
}

/// Pack XYSD v1 plus optional XYAO v1 into XYSS v1 style-sidecar facts.
pub fn pack_style_sidecars(xysd: &[u8], xyao: &[u8]) -> Result<Vec<u8>, StyleSidecarsError> {
    let mut records = Vec::new();
    for record in parse_xysd(xysd)? {
        if let Some(record) = record {
            records.push(record);
        }
    }
    for record in parse_xyao(xyao)? {
        if let Some(record) = record {
            records.push(record);
        }
    }
    Ok(encode_xyss(&records))
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::scene_trace_sidecars::{
        pack_trace_sidecars, XYNM_HEADER_BYTES, XYNM_MAGIC, XYNM_VERSION,
    };

    fn empty_xysd() -> Vec<u8> {
        let mut xytt = vec![0u8; 16];
        xytt[..4].copy_from_slice(b"XYTT");
        xytt[4..8].copy_from_slice(&1u32.to_le_bytes());
        let mut xynm = vec![0u8; XYNM_HEADER_BYTES];
        xynm[..4].copy_from_slice(XYNM_MAGIC);
        xynm[4..8].copy_from_slice(&XYNM_VERSION.to_le_bytes());
        pack_trace_sidecars(&xytt, &xynm).unwrap()
    }

    fn xysd_with_dash() -> Vec<u8> {
        let mut prefix = vec![0u8; 208];
        prefix[..4].copy_from_slice(b"XYTO");
        prefix[4..6].copy_from_slice(&1u16.to_le_bytes());
        prefix[8..12].copy_from_slice(&[0, 0, 0, 255]);
        prefix[12..16].copy_from_slice(&[0, 0, 0, 255]);
        prefix[16..24].copy_from_slice(&1.0f64.to_le_bytes());
        prefix[44..48].copy_from_slice(&2u32.to_le_bytes());
        prefix[48] = LINECAP_NONE;
        let mut xytt = vec![0u8; 16];
        xytt[..4].copy_from_slice(b"XYTT");
        xytt[4..8].copy_from_slice(&1u32.to_le_bytes());
        xytt[8..12].copy_from_slice(&1u32.to_le_bytes());
        xytt.extend_from_slice(&prefix);
        xytt.extend_from_slice(&1.0f64.to_le_bytes());
        xytt.extend_from_slice(&2.0f64.to_le_bytes());
        let mut xynm = vec![0u8; XYNM_HEADER_BYTES];
        xynm[..4].copy_from_slice(XYNM_MAGIC);
        xynm[4..8].copy_from_slice(&XYNM_VERSION.to_le_bytes());
        xynm[8..12].copy_from_slice(&1u32.to_le_bytes());
        xynm.extend_from_slice(&0u16.to_le_bytes());
        pack_trace_sidecars(&xytt, &xynm).unwrap()
    }

    #[test]
    fn empty_inputs_emit_no_xyss() {
        let packed = pack_style_sidecars(&empty_xysd(), &[]).unwrap();
        assert!(packed.is_empty());
    }

    #[test]
    fn dash_trace_emits_xyss_record() {
        let packed = pack_style_sidecars(&xysd_with_dash(), &[]).unwrap();
        assert_eq!(&packed[..4], XYSS_MAGIC);
        assert_eq!(u32::from_le_bytes(packed[8..12].try_into().unwrap()), 1);
        assert_eq!(packed[16 + 4], XYSS_HAS_DASH);
        assert_eq!(packed[16 + 5], 2);
        assert_eq!(f32::from_le_bytes(packed[32..36].try_into().unwrap()), 1.0);
        assert_eq!(f32::from_le_bytes(packed[36..40].try_into().unwrap()), 2.0);
    }

    #[test]
    fn round_linecap_alone_omits_record() {
        let mut prefix = vec![0u8; 208];
        prefix[..4].copy_from_slice(b"XYTO");
        prefix[4..6].copy_from_slice(&1u16.to_le_bytes());
        prefix[8..12].copy_from_slice(&[0, 0, 0, 255]);
        prefix[12..16].copy_from_slice(&[0, 0, 0, 255]);
        prefix[16..24].copy_from_slice(&1.0f64.to_le_bytes());
        prefix[48] = 1;
        let mut xytt = vec![0u8; 16];
        xytt[..4].copy_from_slice(b"XYTT");
        xytt[4..8].copy_from_slice(&1u32.to_le_bytes());
        xytt[8..12].copy_from_slice(&1u32.to_le_bytes());
        xytt.extend_from_slice(&prefix);
        let mut xynm = vec![0u8; XYNM_HEADER_BYTES];
        xynm[..4].copy_from_slice(XYNM_MAGIC);
        xynm[4..8].copy_from_slice(&XYNM_VERSION.to_le_bytes());
        xynm[8..12].copy_from_slice(&1u32.to_le_bytes());
        xynm.extend_from_slice(&0u16.to_le_bytes());
        let xysd = pack_trace_sidecars(&xytt, &xynm).unwrap();
        let packed = pack_style_sidecars(&xysd, &[]).unwrap();
        assert!(packed.is_empty());
    }

    #[test]
    fn annotation_dash_uses_style_ref_base() {
        let mut xyao = vec![0u8; XYAO_V1_HEADER_BYTES + XYAO_STYLE_BYTES];
        xyao[..4].copy_from_slice(XYAO_MAGIC);
        xyao[4..8].copy_from_slice(&XYAO_VERSION.to_le_bytes());
        xyao[8..12].copy_from_slice(&1u32.to_le_bytes());
        xyao[24..28].copy_from_slice(&3u32.to_le_bytes());
        xyao[XYAO_V1_HEADER_BYTES + 16] = 2;
        xyao[XYAO_V1_HEADER_BYTES + 17] = LINECAP_NONE;
        xyao[XYAO_V1_HEADER_BYTES + 24..XYAO_V1_HEADER_BYTES + 28]
            .copy_from_slice(&4.0f32.to_le_bytes());
        xyao[XYAO_V1_HEADER_BYTES + 28..XYAO_V1_HEADER_BYTES + 32]
            .copy_from_slice(&2.0f32.to_le_bytes());
        let packed = pack_style_sidecars(&empty_xysd(), &xyao).unwrap();
        assert_eq!(&packed[..4], XYSS_MAGIC);
        assert_eq!(u32::from_le_bytes(packed[16..20].try_into().unwrap()), 3);
        assert_eq!(packed[20], XYSS_HAS_DASH);
    }
}
