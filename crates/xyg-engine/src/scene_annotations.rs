//! Compact Figure→Scene XYAD annotation framing (M2 #271).
//!
//! Hosts validate authoring keys (kind names, style allowlists, CSS, anchors)
//! and pass typed row meta plus concatenated UTF-8. Rust owns XYAT/XYAL/XYAR/
//! XYAC/XYAW table layout, version selection, the XYAD envelope, and
//! bounded-text rejection so Python and Node cannot drift on the decoration
//! envelope.

use crate::scene::{
    MAX_AUTHORED_STRAIGHT_ARROWS, MAX_AUTHORED_TEXT_ANNOTATIONS, MAX_SCENE_ANNOTATION_INPUT_BYTES,
    MAX_SCENE_LABEL_TEXT_BYTES, MAX_SCENE_TEXT_BYTES,
};

pub const TEXT_META_BYTES: usize = 40;
pub const ATTACHED_META_BYTES: usize = 32;
pub const ARROW_META_BYTES: usize = 60;
pub const CALLOUT_META_BYTES: usize = 76;
pub const WRAPPED_META_BYTES: usize = 64;

const FLAG_FILL: u8 = 1 << 0;
const FLAG_BORDER: u8 = 1 << 1;
const FLAG_MASK: u8 = FLAG_FILL | FLAG_BORDER;

/// Why an annotation frame request was rejected. Discriminants are the C-ABI
/// error codes (returned negated by `xyg_scene_pack_annotations`).
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
#[allow(dead_code)] // Version is reserved for a future envelope; C ABI returns -2.
pub enum AnnotationError {
    Length = 1,
    Version = 2,
    Limit = 3,
    Output = 4,
    NonFinite = 5,
    Text = 6,
    Order = 7,
}

/// One freestanding XYAT row before framing.
#[derive(Clone, Copy, Debug, PartialEq)]
pub struct TextRow<'a> {
    pub x: f64,
    pub y: f64,
    pub rgba: [u8; 4],
    pub fill: [u8; 4],
    pub border_rgba: [u8; 4],
    pub border_width: f64,
    pub flags: u8,
    pub text: &'a [u8],
}

/// One XYAL attached-label row before framing.
#[derive(Clone, Copy, Debug, PartialEq)]
pub struct AttachedRow<'a> {
    pub stable_id: u64,
    pub rgba: [u8; 4],
    pub fill: [u8; 4],
    pub border_rgba: [u8; 4],
    pub border_width: f64,
    pub flags: u8,
    pub text: &'a [u8],
}

/// One XYAR straight-arrow row before framing.
#[derive(Clone, Copy, Debug, PartialEq)]
pub struct ArrowRow {
    pub stable_id: u64,
    pub x0: f64,
    pub y0: f64,
    pub x1: f64,
    pub y1: f64,
    pub rgba: [u8; 4],
    pub opacity: f64,
    pub width: f64,
}

/// One XYAC Cartesian callout row before framing.
#[derive(Clone, Copy, Debug, PartialEq)]
pub struct CalloutRow<'a> {
    pub x: f64,
    pub y: f64,
    pub dx: f64,
    pub dy: f64,
    pub rgba: [u8; 4],
    pub opacity: f64,
    pub width: f64,
    pub anchor: u8,
    pub fill: [u8; 4],
    pub border_rgba: [u8; 4],
    pub border_width: f64,
    pub flags: u8,
    pub text: &'a [u8],
}

/// One XYAW wrapped text/callout row before framing.
#[derive(Clone, Copy, Debug, PartialEq)]
pub struct WrappedRow<'a> {
    pub x: f64,
    pub y: f64,
    pub dx: f64,
    pub dy: f64,
    pub wrap: f64,
    pub rgba: [u8; 4],
    pub fill: [u8; 4],
    pub border_rgba: [u8; 4],
    pub border_width: f64,
    pub kind: u8,
    pub anchor: u8,
    pub text: &'a [u8],
}

/// Authoring literals for the primary Scene annotation envelope.
#[derive(Clone, Copy, Debug)]
pub struct AnnotationFrameInput<'a> {
    pub texts: &'a [TextRow<'a>],
    pub attached: &'a [AttachedRow<'a>],
    pub arrows: &'a [ArrowRow],
    pub callouts: &'a [CalloutRow<'a>],
    pub wrapped: &'a [WrappedRow<'a>],
}

fn require_text(bytes: &[u8], allow_cr: bool, budget: &mut usize) -> Result<(), AnnotationError> {
    if bytes.is_empty()
        || bytes.contains(&0)
        || (!allow_cr && bytes.contains(&b'\r'))
        || bytes.len() > MAX_SCENE_TEXT_BYTES
        || std::str::from_utf8(bytes).is_err()
    {
        return Err(AnnotationError::Text);
    }
    *budget = budget
        .checked_add(bytes.len())
        .ok_or(AnnotationError::Limit)?;
    Ok(())
}

fn require_finite(values: &[f64]) -> Result<(), AnnotationError> {
    if values.iter().all(|value| value.is_finite()) {
        Ok(())
    } else {
        Err(AnnotationError::NonFinite)
    }
}

fn require_style(flags: u8, border_width: f64) -> Result<(), AnnotationError> {
    if flags & !FLAG_MASK != 0 {
        return Err(AnnotationError::Length);
    }
    if flags & FLAG_BORDER != 0 {
        if flags & FLAG_FILL == 0 {
            return Err(AnnotationError::Order);
        }
        if !border_width.is_finite() || border_width <= 0.0 {
            return Err(AnnotationError::NonFinite);
        }
    } else if border_width != 0.0 {
        return Err(AnnotationError::Length);
    }
    Ok(())
}

fn style_version(flags: impl IntoIterator<Item = u8>, base: u32, fill: u32, border: u32) -> u32 {
    let mut combined = 0u8;
    for flag in flags {
        combined |= flag;
    }
    if combined & FLAG_BORDER != 0 {
        border
    } else if combined & FLAG_FILL != 0 {
        fill
    } else {
        base
    }
}

fn split_texts<'a>(lens: &[u32], bytes: &'a [u8]) -> Result<Vec<&'a [u8]>, AnnotationError> {
    let mut out = Vec::with_capacity(lens.len());
    let mut at = 0usize;
    for &len in lens {
        let end = at.checked_add(len as usize).ok_or(AnnotationError::Limit)?;
        out.push(bytes.get(at..end).ok_or(AnnotationError::Length)?);
        at = end;
    }
    if at != bytes.len() {
        return Err(AnnotationError::Length);
    }
    Ok(out)
}

fn require_meta_len(meta: &[u8], count: usize, row: usize) -> Result<(), AnnotationError> {
    if meta.len() == count.saturating_mul(row) {
        Ok(())
    } else {
        Err(AnnotationError::Length)
    }
}

fn f64_at(bytes: &[u8], offset: usize) -> f64 {
    f64::from_le_bytes(bytes[offset..offset + 8].try_into().unwrap())
}

fn u64_at(bytes: &[u8], offset: usize) -> u64 {
    u64::from_le_bytes(bytes[offset..offset + 8].try_into().unwrap())
}

fn rgba_at(bytes: &[u8], offset: usize) -> [u8; 4] {
    bytes[offset..offset + 4].try_into().unwrap()
}

/// Parse compact XYAT row meta (`n * 40` bytes) plus concatenated labels.
pub fn text_rows_from_meta<'a>(
    meta: &'a [u8],
    lens: &[u32],
    texts: &'a [u8],
) -> Result<Vec<TextRow<'a>>, AnnotationError> {
    require_meta_len(meta, lens.len(), TEXT_META_BYTES)?;
    let parts = split_texts(lens, texts)?;
    let mut rows = Vec::with_capacity(lens.len());
    for (index, chunk) in meta.chunks_exact(TEXT_META_BYTES).enumerate() {
        if chunk[37..40] != [0; 3] {
            return Err(AnnotationError::Length);
        }
        rows.push(TextRow {
            x: f64_at(chunk, 0),
            y: f64_at(chunk, 8),
            rgba: rgba_at(chunk, 16),
            fill: rgba_at(chunk, 20),
            border_rgba: rgba_at(chunk, 24),
            border_width: f64_at(chunk, 28),
            flags: chunk[36],
            text: parts[index],
        });
    }
    Ok(rows)
}

/// Parse compact XYAL row meta (`n * 32` bytes) plus concatenated labels.
pub fn attached_rows_from_meta<'a>(
    meta: &'a [u8],
    lens: &[u32],
    texts: &'a [u8],
) -> Result<Vec<AttachedRow<'a>>, AnnotationError> {
    require_meta_len(meta, lens.len(), ATTACHED_META_BYTES)?;
    let parts = split_texts(lens, texts)?;
    let mut rows = Vec::with_capacity(lens.len());
    for (index, chunk) in meta.chunks_exact(ATTACHED_META_BYTES).enumerate() {
        if chunk[29..32] != [0; 3] {
            return Err(AnnotationError::Length);
        }
        rows.push(AttachedRow {
            stable_id: u64_at(chunk, 0),
            rgba: rgba_at(chunk, 8),
            fill: rgba_at(chunk, 12),
            border_rgba: rgba_at(chunk, 16),
            border_width: f64_at(chunk, 20),
            flags: chunk[28],
            text: parts[index],
        });
    }
    Ok(rows)
}

/// Parse compact XYAR row meta (`n * 60` bytes).
pub fn arrow_rows_from_meta(meta: &[u8]) -> Result<Vec<ArrowRow>, AnnotationError> {
    if meta.len() % ARROW_META_BYTES != 0 {
        return Err(AnnotationError::Length);
    }
    Ok(meta
        .chunks_exact(ARROW_META_BYTES)
        .map(|chunk| ArrowRow {
            stable_id: u64_at(chunk, 0),
            x0: f64_at(chunk, 8),
            y0: f64_at(chunk, 16),
            x1: f64_at(chunk, 24),
            y1: f64_at(chunk, 32),
            rgba: rgba_at(chunk, 40),
            opacity: f64_at(chunk, 44),
            width: f64_at(chunk, 52),
        })
        .collect())
}

/// Parse compact XYAC row meta (`n * 76` bytes) plus concatenated labels.
pub fn callout_rows_from_meta<'a>(
    meta: &'a [u8],
    lens: &[u32],
    texts: &'a [u8],
) -> Result<Vec<CalloutRow<'a>>, AnnotationError> {
    require_meta_len(meta, lens.len(), CALLOUT_META_BYTES)?;
    let parts = split_texts(lens, texts)?;
    let mut rows = Vec::with_capacity(lens.len());
    for (index, chunk) in meta.chunks_exact(CALLOUT_META_BYTES).enumerate() {
        if chunk[53..56] != [0; 3] || chunk[73..76] != [0; 3] {
            return Err(AnnotationError::Length);
        }
        rows.push(CalloutRow {
            x: f64_at(chunk, 0),
            y: f64_at(chunk, 8),
            dx: f64_at(chunk, 16),
            dy: f64_at(chunk, 24),
            rgba: rgba_at(chunk, 32),
            opacity: f64_at(chunk, 36),
            width: f64_at(chunk, 44),
            anchor: chunk[52],
            fill: rgba_at(chunk, 56),
            border_rgba: rgba_at(chunk, 60),
            border_width: f64_at(chunk, 64),
            flags: chunk[72],
            text: parts[index],
        });
    }
    Ok(rows)
}

/// Parse compact XYAW row meta (`n * 64` bytes) plus concatenated labels.
pub fn wrapped_rows_from_meta<'a>(
    meta: &'a [u8],
    lens: &[u32],
    texts: &'a [u8],
) -> Result<Vec<WrappedRow<'a>>, AnnotationError> {
    require_meta_len(meta, lens.len(), WRAPPED_META_BYTES)?;
    let parts = split_texts(lens, texts)?;
    let mut rows = Vec::with_capacity(lens.len());
    for (index, chunk) in meta.chunks_exact(WRAPPED_META_BYTES).enumerate() {
        if chunk[62..64] != [0; 2] {
            return Err(AnnotationError::Length);
        }
        rows.push(WrappedRow {
            x: f64_at(chunk, 0),
            y: f64_at(chunk, 8),
            dx: f64_at(chunk, 16),
            dy: f64_at(chunk, 24),
            wrap: f64_at(chunk, 32),
            rgba: rgba_at(chunk, 40),
            fill: rgba_at(chunk, 44),
            border_rgba: rgba_at(chunk, 48),
            border_width: f64_at(chunk, 52),
            kind: chunk[60],
            anchor: chunk[61],
            text: parts[index],
        });
    }
    Ok(rows)
}

fn push_section(out: &mut Vec<u8>, magic: &[u8; 4], version: u32, count: u32, body: &[u8]) {
    out.extend_from_slice(magic);
    out.extend_from_slice(&version.to_le_bytes());
    out.extend_from_slice(&count.to_le_bytes());
    out.extend_from_slice(body);
}

fn fill_bytes(flags: u8, fill: [u8; 4]) -> [u8; 4] {
    if flags & FLAG_FILL != 0 {
        fill
    } else {
        [0; 4]
    }
}

fn border_pair(flags: u8, rgba: [u8; 4], width: f64) -> ([u8; 4], f64) {
    if flags & FLAG_BORDER != 0 {
        (rgba, width)
    } else {
        ([0; 4], 0.0)
    }
}

/// Frame primary Scene annotations as XYAD bytes.
pub fn pack_annotations(input: AnnotationFrameInput<'_>) -> Result<Vec<u8>, AnnotationError> {
    if input.texts.is_empty()
        && input.attached.is_empty()
        && input.arrows.is_empty()
        && input.callouts.is_empty()
        && input.wrapped.is_empty()
    {
        return Ok(Vec::new());
    }
    if input.texts.len() > MAX_AUTHORED_TEXT_ANNOTATIONS
        || input.attached.len() > MAX_AUTHORED_TEXT_ANNOTATIONS
        || input.arrows.len() > MAX_AUTHORED_STRAIGHT_ARROWS
        || input.callouts.len() > MAX_AUTHORED_TEXT_ANNOTATIONS
        || input.wrapped.len() > MAX_AUTHORED_TEXT_ANNOTATIONS
    {
        return Err(AnnotationError::Limit);
    }

    let mut text_budget = 0usize;
    let xyat_version = style_version(input.texts.iter().map(|row| row.flags), 1, 2, 3);
    let mut xyat = Vec::new();
    for row in input.texts {
        require_finite(&[row.x, row.y])?;
        require_style(row.flags, row.border_width)?;
        require_text(row.text, true, &mut text_budget)?;
        xyat.extend_from_slice(&row.x.to_le_bytes());
        xyat.extend_from_slice(&row.y.to_le_bytes());
        xyat.extend_from_slice(&row.rgba);
        if xyat_version >= 2 {
            xyat.extend_from_slice(&fill_bytes(row.flags, row.fill));
        }
        if xyat_version >= 3 {
            let (rgba, width) = border_pair(row.flags, row.border_rgba, row.border_width);
            xyat.extend_from_slice(&rgba);
            xyat.extend_from_slice(&width.to_le_bytes());
        }
        xyat.extend_from_slice(&(row.text.len() as u32).to_le_bytes());
        xyat.extend_from_slice(row.text);
    }
    if text_budget > MAX_SCENE_TEXT_BYTES {
        return Err(AnnotationError::Limit);
    }

    let mut attached_budget = 0usize;
    let mut seen = std::collections::BTreeSet::new();
    let xyal_version = style_version(input.attached.iter().map(|row| row.flags), 2, 3, 4);
    let mut xyal = Vec::new();
    for row in input.attached {
        require_style(row.flags, row.border_width)?;
        require_text(row.text, true, &mut attached_budget)?;
        if !seen.insert(row.stable_id) {
            return Err(AnnotationError::Order);
        }
        xyal.extend_from_slice(&row.stable_id.to_le_bytes());
        xyal.extend_from_slice(&row.rgba);
        if xyal_version >= 3 {
            xyal.extend_from_slice(&fill_bytes(row.flags, row.fill));
        }
        if xyal_version >= 4 {
            let (rgba, width) = border_pair(row.flags, row.border_rgba, row.border_width);
            xyal.extend_from_slice(&rgba);
            xyal.extend_from_slice(&width.to_le_bytes());
        }
        xyal.extend_from_slice(&(row.text.len() as u32).to_le_bytes());
        xyal.extend_from_slice(row.text);
    }
    if attached_budget > MAX_SCENE_TEXT_BYTES {
        return Err(AnnotationError::Limit);
    }

    let mut xyar = Vec::new();
    let mut arrow_ids = std::collections::BTreeSet::new();
    for row in input.arrows {
        require_finite(&[row.x0, row.y0, row.x1, row.y1, row.opacity, row.width])?;
        if !(0.0..=1.0).contains(&row.opacity) || row.width <= 0.0 {
            return Err(AnnotationError::NonFinite);
        }
        if !arrow_ids.insert(row.stable_id) {
            return Err(AnnotationError::Order);
        }
        xyar.extend_from_slice(&row.stable_id.to_le_bytes());
        xyar.extend_from_slice(&row.x0.to_le_bytes());
        xyar.extend_from_slice(&row.y0.to_le_bytes());
        xyar.extend_from_slice(&row.x1.to_le_bytes());
        xyar.extend_from_slice(&row.y1.to_le_bytes());
        xyar.extend_from_slice(&row.rgba);
        xyar.extend_from_slice(&row.opacity.to_le_bytes());
        xyar.extend_from_slice(&row.width.to_le_bytes());
    }

    let mut callout_budget = 0usize;
    let xyac_version = style_version(input.callouts.iter().map(|row| row.flags), 1, 2, 3);
    let mut xyac = Vec::new();
    for row in input.callouts {
        require_finite(&[row.x, row.y, row.dx, row.dy, row.opacity, row.width])?;
        require_style(row.flags, row.border_width)?;
        require_text(row.text, true, &mut callout_budget)?;
        if !(0.0..=1.0).contains(&row.opacity) || row.width <= 0.0 || row.anchor > 2 {
            return Err(AnnotationError::NonFinite);
        }
        xyac.extend_from_slice(&row.x.to_le_bytes());
        xyac.extend_from_slice(&row.y.to_le_bytes());
        xyac.extend_from_slice(&row.dx.to_le_bytes());
        xyac.extend_from_slice(&row.dy.to_le_bytes());
        xyac.extend_from_slice(&row.rgba);
        xyac.extend_from_slice(&row.opacity.to_le_bytes());
        xyac.extend_from_slice(&row.width.to_le_bytes());
        xyac.push(row.anchor);
        xyac.extend_from_slice(&[0, 0, 0]);
        xyac.extend_from_slice(&(row.text.len() as u32).to_le_bytes());
        if xyac_version >= 2 {
            xyac.extend_from_slice(&fill_bytes(row.flags, row.fill));
        }
        if xyac_version >= 3 {
            let (rgba, width) = border_pair(row.flags, row.border_rgba, row.border_width);
            xyac.extend_from_slice(&rgba);
            xyac.extend_from_slice(&width.to_le_bytes());
        }
        xyac.extend_from_slice(row.text);
    }
    if callout_budget > MAX_SCENE_LABEL_TEXT_BYTES {
        return Err(AnnotationError::Limit);
    }

    let mut wrapped_budget = 0usize;
    let mut xyaw = Vec::new();
    for row in input.wrapped {
        require_finite(&[row.x, row.y, row.dx, row.dy, row.wrap, row.border_width])?;
        require_text(row.text, false, &mut wrapped_budget)?;
        if row.wrap < 0.0 || row.kind > 1 || row.anchor > 2 {
            return Err(AnnotationError::NonFinite);
        }
        let has_border = row.border_rgba[3] != 0;
        if has_border {
            if row.fill[3] == 0 || !row.border_width.is_finite() || row.border_width <= 0.0 {
                return Err(AnnotationError::Order);
            }
        } else if row.border_width != 0.0 {
            return Err(AnnotationError::Length);
        }
        xyaw.extend_from_slice(&row.x.to_le_bytes());
        xyaw.extend_from_slice(&row.y.to_le_bytes());
        xyaw.extend_from_slice(&row.dx.to_le_bytes());
        xyaw.extend_from_slice(&row.dy.to_le_bytes());
        xyaw.extend_from_slice(&row.wrap.to_le_bytes());
        xyaw.extend_from_slice(&row.rgba);
        xyaw.extend_from_slice(&row.fill);
        xyaw.extend_from_slice(&if has_border { row.border_rgba } else { [0; 4] });
        xyaw.extend_from_slice(&(if has_border { row.border_width } else { 0.0 }).to_le_bytes());
        xyaw.push(row.kind);
        xyaw.push(row.anchor);
        xyaw.extend_from_slice(&[0, 0]);
        xyaw.extend_from_slice(&(row.text.len() as u32).to_le_bytes());
        xyaw.extend_from_slice(row.text);
    }
    if wrapped_budget > MAX_SCENE_LABEL_TEXT_BYTES {
        return Err(AnnotationError::Limit);
    }

    let mut xyat_section = Vec::new();
    push_section(
        &mut xyat_section,
        b"XYAT",
        xyat_version,
        input.texts.len() as u32,
        &xyat,
    );
    let mut xyal_section = Vec::new();
    push_section(
        &mut xyal_section,
        b"XYAL",
        xyal_version,
        input.attached.len() as u32,
        &xyal,
    );
    let mut xyar_section = Vec::new();
    push_section(
        &mut xyar_section,
        b"XYAR",
        1,
        input.arrows.len() as u32,
        &xyar,
    );
    let mut xyac_section = Vec::new();
    push_section(
        &mut xyac_section,
        b"XYAC",
        xyac_version,
        input.callouts.len() as u32,
        &xyac,
    );
    let xyad_v3 = !input.wrapped.is_empty();
    let mut xyaw_section = Vec::new();
    if xyad_v3 {
        push_section(
            &mut xyaw_section,
            b"XYAW",
            1,
            input.wrapped.len() as u32,
            &xyaw,
        );
    }
    let header: usize = if xyad_v3 { 28 } else { 24 };
    let total = header
        .checked_add(xyat_section.len())
        .and_then(|value| value.checked_add(xyal_section.len()))
        .and_then(|value| value.checked_add(xyar_section.len()))
        .and_then(|value| value.checked_add(xyac_section.len()))
        .and_then(|value| value.checked_add(xyaw_section.len()))
        .ok_or(AnnotationError::Limit)?;
    if total > MAX_SCENE_ANNOTATION_INPUT_BYTES {
        return Err(AnnotationError::Limit);
    }
    let mut out = Vec::with_capacity(total);
    out.extend_from_slice(b"XYAD");
    out.extend_from_slice(&(if xyad_v3 { 3u32 } else { 2u32 }).to_le_bytes());
    out.extend_from_slice(&(xyat_section.len() as u32).to_le_bytes());
    out.extend_from_slice(&(xyal_section.len() as u32).to_le_bytes());
    out.extend_from_slice(&(xyar_section.len() as u32).to_le_bytes());
    out.extend_from_slice(&(xyac_section.len() as u32).to_le_bytes());
    if xyad_v3 {
        out.extend_from_slice(&(xyaw_section.len() as u32).to_le_bytes());
    }
    out.extend_from_slice(&xyat_section);
    out.extend_from_slice(&xyal_section);
    out.extend_from_slice(&xyar_section);
    out.extend_from_slice(&xyac_section);
    out.extend_from_slice(&xyaw_section);
    Ok(out)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn empty_input() -> AnnotationFrameInput<'static> {
        AnnotationFrameInput {
            texts: &[],
            attached: &[],
            arrows: &[],
            callouts: &[],
            wrapped: &[],
        }
    }

    #[test]
    fn empty_rows_emit_no_bytes() {
        assert!(pack_annotations(empty_input()).unwrap().is_empty());
    }

    #[test]
    fn frames_plain_text_as_xyad_v2_xyat_v1() {
        let text = TextRow {
            x: 0.5,
            y: 0.25,
            rgba: [102, 112, 133, 255],
            fill: [0; 4],
            border_rgba: [0; 4],
            border_width: 0.0,
            flags: 0,
            text: b"hi",
        };
        let framed = pack_annotations(AnnotationFrameInput {
            texts: &[text],
            ..empty_input()
        })
        .unwrap();
        assert_eq!(&framed[..4], b"XYAD");
        assert_eq!(u32::from_le_bytes(framed[4..8].try_into().unwrap()), 2);
        let xyat_len = u32::from_le_bytes(framed[8..12].try_into().unwrap()) as usize;
        let at = 24;
        assert_eq!(&framed[at..at + 4], b"XYAT");
        assert_eq!(
            u32::from_le_bytes(framed[at + 4..at + 8].try_into().unwrap()),
            1
        );
        assert_eq!(&framed[at + 12 + 24..at + xyat_len], b"hi");
        assert_eq!(&framed[at + xyat_len..at + xyat_len + 4], b"XYAL");
        assert_eq!(
            u32::from_le_bytes(
                framed[at + xyat_len + 4..at + xyat_len + 8]
                    .try_into()
                    .unwrap()
            ),
            2
        );
    }

    #[test]
    fn mixed_fill_selects_xyat_v2_with_transparent_row() {
        let rows = [
            TextRow {
                x: 0.0,
                y: 0.0,
                rgba: [1, 2, 3, 255],
                fill: [0; 4],
                border_rgba: [0; 4],
                border_width: 0.0,
                flags: 0,
                text: b"a",
            },
            TextRow {
                x: 1.0,
                y: 1.0,
                rgba: [4, 5, 6, 255],
                fill: [18, 52, 86, 255],
                border_rgba: [0; 4],
                border_width: 0.0,
                flags: FLAG_FILL,
                text: b"b",
            },
        ];
        let framed = pack_annotations(AnnotationFrameInput {
            texts: &rows,
            ..empty_input()
        })
        .unwrap();
        let at = 24;
        assert_eq!(
            u32::from_le_bytes(framed[at + 4..at + 8].try_into().unwrap()),
            2
        );
        let first = at + 12;
        assert_eq!(&framed[first + 20..first + 24], &[0, 0, 0, 0]);
        let second = first + 28 + 1;
        assert_eq!(&framed[second + 20..second + 24], &[18, 52, 86, 255]);
    }

    #[test]
    fn wrapped_rows_select_xyad_v3() {
        let wrapped = WrappedRow {
            x: 0.5,
            y: 0.5,
            dx: 0.0,
            dy: 0.0,
            wrap: 80.0,
            rgba: [102, 112, 133, 255],
            fill: [0; 4],
            border_rgba: [0; 4],
            border_width: 0.0,
            kind: 0,
            anchor: 0,
            text: b"wrap",
        };
        let framed = pack_annotations(AnnotationFrameInput {
            wrapped: &[wrapped],
            ..empty_input()
        })
        .unwrap();
        assert_eq!(u32::from_le_bytes(framed[4..8].try_into().unwrap()), 3);
        assert_eq!(&framed[framed.len() - 4..], b"wrap");
        assert!(framed.windows(4).any(|window| window == b"XYAW"));
    }

    #[test]
    fn border_without_fill_is_rejected() {
        let text = TextRow {
            x: 0.0,
            y: 0.0,
            rgba: [1, 2, 3, 255],
            fill: [0; 4],
            border_rgba: [0, 0, 0, 255],
            border_width: 1.0,
            flags: FLAG_BORDER,
            text: b"x",
        };
        assert_eq!(
            pack_annotations(AnnotationFrameInput {
                texts: &[text],
                ..empty_input()
            }),
            Err(AnnotationError::Order)
        );
    }
}
