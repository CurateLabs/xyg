//! Compact Figure→Scene annotation splice (M2 #271).
//!
//! Hosts pass packed product rows (ABI 156), `XYSD` v1 trace styles (ABI 157),
//! and an optional `XYAO` v1 envelope (ABI 148). Rust owns appending
//! annotation styles and 56-byte mark rows and extracting `XYAD`, so Python
//! and Node cannot drift. Encoded Scene v31 is unchanged. Hosts unpack `XYAS`
//! once for batch encode; chrome/legend still read original-trace `XYSD`.

use crate::scene::{MAX_SCENE_MARKS, MAX_SCENE_STYLES, SCENE_STYLE_RECORD_BYTES};
use crate::scene_annotations::{XYAO_MAGIC, XYAO_STYLE_BYTES, XYAO_V1_HEADER_BYTES, XYAO_VERSION};
use crate::scene_pack::PACKED_SCENE_ROW_BYTES;
use crate::scene_trace_sidecars::{XYSD_HEADER_BYTES, XYSD_MAGIC, XYSD_PREFIX_BYTES, XYSD_VERSION};

pub const XYAS_MAGIC: &[u8; 4] = b"XYAS";
pub const XYAS_VERSION: u32 = 1;
pub const XYAS_HEADER_BYTES: usize = 24;

/// Why an XYAS annotation-splice request was rejected. Discriminants are the
/// C-ABI error codes (returned negated by `xyg_scene_splice_annotations`).
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum AnnotationSpliceCode {
    Length = 1,
    Version = 2,
    Limit = 3,
    Output = 4,
    Payload = 5,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct AnnotationSpliceError {
    pub code: AnnotationSpliceCode,
    pub index: u32,
}

impl AnnotationSpliceError {
    fn new(code: AnnotationSpliceCode, index: usize) -> Self {
        Self {
            code,
            index: index as u32,
        }
    }
}

fn read_u32(bytes: &[u8], offset: usize) -> Result<u32, AnnotationSpliceError> {
    Ok(u32::from_le_bytes(
        bytes
            .get(offset..offset + 4)
            .ok_or(AnnotationSpliceError::new(AnnotationSpliceCode::Length, 0))?
            .try_into()
            .map_err(|_| AnnotationSpliceError::new(AnnotationSpliceCode::Length, 0))?,
    ))
}

fn take<'a>(
    rest: &mut &'a [u8],
    n: usize,
    index: usize,
) -> Result<&'a [u8], AnnotationSpliceError> {
    if rest.len() < n {
        return Err(AnnotationSpliceError::new(
            AnnotationSpliceCode::Length,
            index,
        ));
    }
    let (head, tail) = rest.split_at(n);
    *rest = tail;
    Ok(head)
}

fn parse_rows(bytes: &[u8]) -> Result<&[u8], AnnotationSpliceError> {
    if bytes.len() % PACKED_SCENE_ROW_BYTES != 0 {
        return Err(AnnotationSpliceError::new(AnnotationSpliceCode::Length, 0));
    }
    let n_rows = bytes.len() / PACKED_SCENE_ROW_BYTES;
    if n_rows > MAX_SCENE_MARKS {
        return Err(AnnotationSpliceError::new(AnnotationSpliceCode::Limit, 0));
    }
    Ok(bytes)
}

fn parse_xysd_styles(
    bytes: &[u8],
) -> Result<Vec<[u8; SCENE_STYLE_RECORD_BYTES]>, AnnotationSpliceError> {
    if bytes.is_empty() {
        return Ok(Vec::new());
    }
    if bytes.len() < XYSD_HEADER_BYTES || bytes.get(..4) != Some(&XYSD_MAGIC[..]) {
        return Err(AnnotationSpliceError::new(AnnotationSpliceCode::Length, 0));
    }
    if read_u32(bytes, 4)? != XYSD_VERSION {
        return Err(AnnotationSpliceError::new(AnnotationSpliceCode::Version, 0));
    }
    let n_traces = read_u32(bytes, 8)? as usize;
    if n_traces > MAX_SCENE_STYLES {
        return Err(AnnotationSpliceError::new(AnnotationSpliceCode::Limit, 0));
    }
    let mut rest = bytes
        .get(XYSD_HEADER_BYTES..)
        .ok_or(AnnotationSpliceError::new(AnnotationSpliceCode::Length, 0))?;
    let mut styles = Vec::with_capacity(n_traces);
    for index in 0..n_traces {
        let prefix = take(&mut rest, XYSD_PREFIX_BYTES, index)?;
        let mut style = [0u8; SCENE_STYLE_RECORD_BYTES];
        style.copy_from_slice(&prefix[..SCENE_STYLE_RECORD_BYTES]);
        styles.push(style);
        let dash_len = u32::from_le_bytes(prefix[20..24].try_into().unwrap()) as usize;
        let marker_len = u32::from_le_bytes(prefix[24..28].try_into().unwrap()) as usize;
        let gradient_len = u32::from_le_bytes(prefix[28..32].try_into().unwrap()) as usize;
        let plane_len = u32::from_le_bytes(prefix[32..36].try_into().unwrap()) as usize;
        let name_len = u32::from_le_bytes(prefix[36..40].try_into().unwrap()) as usize;
        let _ = take(&mut rest, dash_len, index)?;
        let _ = take(&mut rest, marker_len, index)?;
        let _ = take(&mut rest, gradient_len, index)?;
        let _ = take(&mut rest, plane_len, index)?;
        let _ = take(&mut rest, name_len, index)?;
    }
    if !rest.is_empty() {
        return Err(AnnotationSpliceError::new(AnnotationSpliceCode::Length, 0));
    }
    Ok(styles)
}

struct AnnotationTail {
    styles: Vec<[u8; SCENE_STYLE_RECORD_BYTES]>,
    rows: Vec<u8>,
    xyad: Vec<u8>,
}

fn parse_xyao(bytes: &[u8]) -> Result<AnnotationTail, AnnotationSpliceError> {
    if bytes.is_empty() {
        return Ok(AnnotationTail {
            styles: Vec::new(),
            rows: Vec::new(),
            xyad: Vec::new(),
        });
    }
    if bytes.len() < XYAO_V1_HEADER_BYTES || bytes.get(..4) != Some(&XYAO_MAGIC[..]) {
        return Err(AnnotationSpliceError::new(AnnotationSpliceCode::Length, 0));
    }
    if read_u32(bytes, 4)? != XYAO_VERSION {
        return Err(AnnotationSpliceError::new(AnnotationSpliceCode::Version, 0));
    }
    let n_styles = read_u32(bytes, 8)? as usize;
    let n_rows = read_u32(bytes, 12)? as usize;
    let xyad_len = read_u32(bytes, 16)? as usize;
    if n_styles > MAX_SCENE_STYLES || n_rows > MAX_SCENE_MARKS {
        return Err(AnnotationSpliceError::new(AnnotationSpliceCode::Limit, 0));
    }
    let mut rest = bytes
        .get(XYAO_V1_HEADER_BYTES..)
        .ok_or(AnnotationSpliceError::new(AnnotationSpliceCode::Length, 0))?;
    let mut styles = Vec::with_capacity(n_styles);
    for index in 0..n_styles {
        let style = take(&mut rest, XYAO_STYLE_BYTES, index)?;
        let mut record = [0u8; SCENE_STYLE_RECORD_BYTES];
        record.copy_from_slice(&style[..SCENE_STYLE_RECORD_BYTES]);
        styles.push(record);
    }
    let row_bytes = n_rows
        .checked_mul(PACKED_SCENE_ROW_BYTES)
        .ok_or(AnnotationSpliceError::new(AnnotationSpliceCode::Limit, 0))?;
    let rows = take(&mut rest, row_bytes, 0)?.to_vec();
    let xyad = take(&mut rest, xyad_len, 0)?.to_vec();
    if !rest.is_empty() {
        return Err(AnnotationSpliceError::new(AnnotationSpliceCode::Payload, 0));
    }
    Ok(AnnotationTail { styles, rows, xyad })
}

fn encode_xyas(
    styles: &[[u8; SCENE_STYLE_RECORD_BYTES]],
    rows: &[u8],
    xyad: &[u8],
) -> Result<Vec<u8>, AnnotationSpliceError> {
    let n_rows = rows.len() / PACKED_SCENE_ROW_BYTES;
    if styles.len() > MAX_SCENE_STYLES || n_rows > MAX_SCENE_MARKS {
        return Err(AnnotationSpliceError::new(AnnotationSpliceCode::Limit, 0));
    }
    let mut out = Vec::from(*XYAS_MAGIC);
    out.extend_from_slice(&XYAS_VERSION.to_le_bytes());
    out.extend_from_slice(&(styles.len() as u32).to_le_bytes());
    out.extend_from_slice(&(n_rows as u32).to_le_bytes());
    out.extend_from_slice(&(xyad.len() as u32).to_le_bytes());
    out.extend_from_slice(&0u32.to_le_bytes());
    for style in styles {
        out.extend_from_slice(style);
    }
    out.extend_from_slice(rows);
    out.extend_from_slice(xyad);
    Ok(out)
}

/// Pack product rows plus XYSD v1 plus optional XYAO v1 into XYAS v1.
pub fn splice_annotations(
    rows: &[u8],
    xysd: &[u8],
    xyao: &[u8],
) -> Result<Vec<u8>, AnnotationSpliceError> {
    let product_rows = parse_rows(rows)?;
    let mut styles = parse_xysd_styles(xysd)?;
    let tail = parse_xyao(xyao)?;
    let n_styles = styles
        .len()
        .checked_add(tail.styles.len())
        .ok_or(AnnotationSpliceError::new(AnnotationSpliceCode::Limit, 0))?;
    let n_rows = (product_rows.len() / PACKED_SCENE_ROW_BYTES)
        .checked_add(tail.rows.len() / PACKED_SCENE_ROW_BYTES)
        .ok_or(AnnotationSpliceError::new(AnnotationSpliceCode::Limit, 0))?;
    if n_styles > MAX_SCENE_STYLES || n_rows > MAX_SCENE_MARKS {
        return Err(AnnotationSpliceError::new(AnnotationSpliceCode::Limit, 0));
    }
    styles.extend_from_slice(&tail.styles);
    let mut spliced_rows = Vec::with_capacity(product_rows.len() + tail.rows.len());
    spliced_rows.extend_from_slice(product_rows);
    spliced_rows.extend_from_slice(&tail.rows);
    encode_xyas(&styles, &spliced_rows, &tail.xyad)
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

    fn one_style_xysd() -> Vec<u8> {
        let mut packed = vec![0u8; XYSD_HEADER_BYTES + XYSD_PREFIX_BYTES];
        packed[..4].copy_from_slice(XYSD_MAGIC);
        packed[4..8].copy_from_slice(&XYSD_VERSION.to_le_bytes());
        packed[8..12].copy_from_slice(&1u32.to_le_bytes());
        packed[XYSD_HEADER_BYTES..XYSD_HEADER_BYTES + 4].copy_from_slice(&[1, 2, 3, 4]);
        packed[XYSD_HEADER_BYTES + 4..XYSD_HEADER_BYTES + 8].copy_from_slice(&[5, 6, 7, 8]);
        packed[XYSD_HEADER_BYTES + 8..XYSD_HEADER_BYTES + 16]
            .copy_from_slice(&1.5f64.to_le_bytes());
        packed
    }

    #[test]
    fn empty_inputs_emit_xyas_header() {
        let packed = splice_annotations(&[], &empty_xysd(), &[]).unwrap();
        assert_eq!(&packed[..4], XYAS_MAGIC);
        assert_eq!(
            u32::from_le_bytes(packed[4..8].try_into().unwrap()),
            XYAS_VERSION
        );
        assert_eq!(u32::from_le_bytes(packed[8..12].try_into().unwrap()), 0);
        assert_eq!(u32::from_le_bytes(packed[12..16].try_into().unwrap()), 0);
        assert_eq!(u32::from_le_bytes(packed[16..20].try_into().unwrap()), 0);
        assert_eq!(packed.len(), XYAS_HEADER_BYTES);
    }

    #[test]
    fn xysd_styles_and_rows_copy_through() {
        let mut row = vec![0u8; PACKED_SCENE_ROW_BYTES];
        row[0] = 3;
        row[4..8].copy_from_slice(&0u32.to_le_bytes());
        let packed = splice_annotations(&row, &one_style_xysd(), &[]).unwrap();
        assert_eq!(u32::from_le_bytes(packed[8..12].try_into().unwrap()), 1);
        assert_eq!(u32::from_le_bytes(packed[12..16].try_into().unwrap()), 1);
        assert_eq!(
            &packed[XYAS_HEADER_BYTES..XYAS_HEADER_BYTES + 4],
            &[1, 2, 3, 4]
        );
        assert_eq!(
            f64::from_le_bytes(
                packed[XYAS_HEADER_BYTES + 8..XYAS_HEADER_BYTES + 16]
                    .try_into()
                    .unwrap()
            ),
            1.5
        );
        let row_at = XYAS_HEADER_BYTES + SCENE_STYLE_RECORD_BYTES;
        assert_eq!(packed[row_at], 3);
        assert_eq!(
            packed.len(),
            XYAS_HEADER_BYTES + SCENE_STYLE_RECORD_BYTES + PACKED_SCENE_ROW_BYTES
        );
    }

    #[test]
    fn xyao_appends_styles_rows_and_xyad() {
        let mut xyao =
            vec![0u8; XYAO_V1_HEADER_BYTES + XYAO_STYLE_BYTES + PACKED_SCENE_ROW_BYTES + 4];
        xyao[..4].copy_from_slice(XYAO_MAGIC);
        xyao[4..8].copy_from_slice(&XYAO_VERSION.to_le_bytes());
        xyao[8..12].copy_from_slice(&1u32.to_le_bytes());
        xyao[12..16].copy_from_slice(&1u32.to_le_bytes());
        xyao[16..20].copy_from_slice(&4u32.to_le_bytes());
        xyao[24..28].copy_from_slice(&1u32.to_le_bytes());
        let style_at = XYAO_V1_HEADER_BYTES;
        xyao[style_at..style_at + 4].copy_from_slice(&[9, 9, 9, 255]);
        xyao[style_at + 4..style_at + 8].copy_from_slice(&[0, 0, 0, 255]);
        xyao[style_at + 8..style_at + 16].copy_from_slice(&2.0f64.to_le_bytes());
        let row_at = style_at + XYAO_STYLE_BYTES;
        xyao[row_at] = 7;
        xyao[row_at + 4..row_at + 8].copy_from_slice(&1u32.to_le_bytes());
        xyao[row_at + PACKED_SCENE_ROW_BYTES..].copy_from_slice(b"XYAD");
        let packed = splice_annotations(&[], &one_style_xysd(), &xyao).unwrap();
        assert_eq!(u32::from_le_bytes(packed[8..12].try_into().unwrap()), 2);
        assert_eq!(u32::from_le_bytes(packed[12..16].try_into().unwrap()), 1);
        assert_eq!(u32::from_le_bytes(packed[16..20].try_into().unwrap()), 4);
        let second = XYAS_HEADER_BYTES + SCENE_STYLE_RECORD_BYTES;
        assert_eq!(&packed[second..second + 4], &[9, 9, 9, 255]);
        let packed_row = second + SCENE_STYLE_RECORD_BYTES;
        assert_eq!(packed[packed_row], 7);
        assert_eq!(&packed[packed.len() - 4..], b"XYAD");
    }

    #[test]
    fn misaligned_rows_are_length_errors() {
        let error = splice_annotations(&[0u8; 10], &empty_xysd(), &[]).unwrap_err();
        assert_eq!(error.code, AnnotationSpliceCode::Length);
    }
}
