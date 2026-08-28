//! Compact Figure→Scene XYAD annotation framing (M2 #271 / #278).
//!
//! Hosts validate authoring keys (kind names, style allowlists, CSS, anchors)
//! and pass typed row meta plus concatenated UTF-8. Rust owns XYAT/XYAL/XYAR/
//! XYAC/XYAW table layout, version selection, the XYAD envelope, and
//! bounded-text rejection so Python and Node cannot drift on the decoration
//! envelope. ABI 148 owns family routing from packed XYAF v1 facts: wrap vs
//! text vs arrow vs callout vs rule/band/marker, stable-id tags, mark-style
//! defaults, domain expansion, and XYAD framing so those decisions cannot
//! drift across hosts. ABI 184 routes cartesian unwrapped text `dx`/`dy`/
//! `anchor` through XYAW with `wrap=0` (keep explicit newlines; apply the
//! offset and text-anchor). ABI 185 routes labelled cartesian marker
//! `dx`/`dy`/`anchor` the same way (keep the marker mark row; skip AttachedRow
//! for that label). ABI 187 routes cartesian unwrapped text `rotation`
//! through XYAW with `wrap=0` (nonzero rotation writes XYAW v2). ABI 188
//! routes labelled cartesian marker `rotation` the same way (nums[8]; markers
//! never wrap, and nums[15] stays stroke_width). Annotation `html` is the
//! #305 XYFS/XYEP pin (`XYG_SCENE_UNSUPPORTED_ANNOTATION_HTML`). `class_name`
//! is the #306 `SCENE_FEATURE_BROWSER_CSS` pin. Polar stays fail-closed.

use crate::css::{apply_opacity_rgba8, color_rgba8};
use crate::scene::{
    MAX_AUTHORED_STRAIGHT_ARROWS, MAX_AUTHORED_TEXT_ANNOTATIONS, MAX_SCENE_ANNOTATION_INPUT_BYTES,
    MAX_SCENE_LABEL_TEXT_BYTES, MAX_SCENE_TEXT_BYTES,
};
use crate::scene_pack::{
    pack_annotation_marks, AnnotationMarkInput, PackError, ANN_KIND_BAND, ANN_KIND_MARKER,
    ANN_KIND_RULE, PACKED_SCENE_ROW_BYTES,
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
    pub rotation: f64,
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
            rotation: 0.0,
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
    let xyaw_v2 = input.wrapped.iter().any(|row| row.rotation != 0.0);
    for row in input.wrapped {
        require_finite(&[
            row.x,
            row.y,
            row.dx,
            row.dy,
            row.wrap,
            row.border_width,
            row.rotation,
        ])?;
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
        if xyaw_v2 {
            xyaw.extend_from_slice(&row.rotation.to_le_bytes());
        }
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
            if xyaw_v2 { 2 } else { 1 },
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

pub const XYAF_MAGIC: &[u8; 4] = b"XYAF";
pub const XYAF_VERSION: u32 = 1;
pub const XYAF_V1_HEADER_BYTES: usize = 232;
pub const XYAO_MAGIC: &[u8; 4] = b"XYAO";
pub const XYAO_VERSION: u32 = 1;
pub const XYAO_V1_HEADER_BYTES: usize = 32;
pub const XYAO_STYLE_BYTES: usize = 56;

pub const XYAF_KIND_TEXT: u8 = 0;
pub const XYAF_KIND_ARROW: u8 = 1;
pub const XYAF_KIND_CALLOUT: u8 = 2;
pub const XYAF_KIND_RULE: u8 = 3;
pub const XYAF_KIND_BAND: u8 = 4;
pub const XYAF_KIND_MARKER: u8 = 5;

const FACT_HAS_WRAP: u32 = 1 << 0;
const FACT_HAS_TEXT: u32 = 1 << 1;
const FACT_HAS_CLASS_NAME: u32 = 1 << 2;
const FACT_HAS_DX: u32 = 1 << 3;
const FACT_HAS_DY: u32 = 1 << 4;
const FACT_HAS_X: u32 = 1 << 5;
const FACT_HAS_Y: u32 = 1 << 6;
const FACT_HAS_X0: u32 = 1 << 7;
const FACT_HAS_Y0: u32 = 1 << 8;
const FACT_HAS_X1: u32 = 1 << 9;
const FACT_HAS_Y1: u32 = 1 << 10;
const FACT_HAS_VALUE: u32 = 1 << 11;
const FACT_HAS_START: u32 = 1 << 12;
const FACT_HAS_END: u32 = 1 << 13;
const FACT_HAS_SIZE: u32 = 1 << 14;
const FACT_HAS_AXIS: u32 = 1 << 15;
#[allow(dead_code)]
const FACT_HAS_SYMBOL: u32 = 1 << 16;
const FACT_HAS_ANCHOR: u32 = 1 << 17;
const FACT_HAS_ROTATION: u32 = 1 << 18;
const FACT_BITS: u32 = (1 << 19) - 1;

const STYLE_COLOR: u32 = 1 << 0;
const STYLE_OPACITY: u32 = 1 << 1;
const STYLE_WIDTH: u32 = 1 << 2;
const STYLE_DASH: u32 = 1 << 3;
const STYLE_LINECAP: u32 = 1 << 4;
const STYLE_STROKE_COLOR: u32 = 1 << 5;
const STYLE_STROKE_WIDTH: u32 = 1 << 6;
const STYLE_LABEL_COLOR: u32 = 1 << 7;
const STYLE_LABEL_OPACITY: u32 = 1 << 8;
const STYLE_LABEL_BACKGROUND: u32 = 1 << 9;
const STYLE_LABEL_BORDER_COLOR: u32 = 1 << 10;
const STYLE_LABEL_BORDER_WIDTH: u32 = 1 << 11;
const STYLE_UNSUPPORTED: u32 = 1 << 31;
const STYLE_KNOWN: u32 = (1 << 12) - 1;

const ANN_ID_PREFIX: u64 = 0x5859_0000_0000_0000;
const LINECAP_NONE: u8 = 255;
const ANCHOR_UNSET: u8 = 255;
const COLOR_RULE: &str = "#667085";
const COLOR_BAND: &str = "#64748b";
const COLOR_CALLOUT: &str = "#344054";

struct AnnotationFacts<'a> {
    index: u32,
    kind: u8,
    axis: u8,
    symbol: u8,
    anchor: u8,
    facts: u32,
    style_bits: u32,
    linecap: u8,
    dash_count: u8,
    nums: [f64; 18],
    color: [u8; 4],
    stroke_color: [u8; 4],
    label_color: [u8; 4],
    label_fill: [u8; 4],
    label_border: [u8; 4],
    dash: [f32; 8],
    text: &'a [u8],
}

struct StyleOut {
    fill: [u8; 4],
    stroke: [u8; 4],
    width: f64,
    dash_count: u8,
    linecap: u8,
    dash: [f32; 8],
}

fn pack_err(error: PackError) -> AnnotationError {
    match error {
        PackError::Length | PackError::UnknownKind => AnnotationError::Length,
        PackError::Version => AnnotationError::Version,
        PackError::Limit => AnnotationError::Limit,
        PackError::Output => AnnotationError::Output,
        PackError::NonFinite => AnnotationError::NonFinite,
    }
}

fn read_u32(bytes: &[u8], at: usize) -> Result<u32, AnnotationError> {
    let slice = bytes.get(at..at + 4).ok_or(AnnotationError::Length)?;
    Ok(u32::from_le_bytes(
        slice.try_into().map_err(|_| AnnotationError::Length)?,
    ))
}

fn read_f64(bytes: &[u8], at: usize) -> Result<f64, AnnotationError> {
    let slice = bytes.get(at..at + 8).ok_or(AnnotationError::Length)?;
    Ok(f64::from_le_bytes(
        slice.try_into().map_err(|_| AnnotationError::Length)?,
    ))
}

fn read_f32(bytes: &[u8], at: usize) -> Result<f32, AnnotationError> {
    let slice = bytes.get(at..at + 4).ok_or(AnnotationError::Length)?;
    Ok(f32::from_le_bytes(
        slice.try_into().map_err(|_| AnnotationError::Length)?,
    ))
}

fn read_rgba(bytes: &[u8], at: usize) -> Result<[u8; 4], AnnotationError> {
    let slice = bytes.get(at..at + 4).ok_or(AnnotationError::Length)?;
    Ok(slice.try_into().map_err(|_| AnnotationError::Length)?)
}

fn annotation_id(tag: u8, index: u32) -> u64 {
    ANN_ID_PREFIX | (u64::from(tag) << 40) | u64::from(index)
}

fn has(bits: u32, flag: u32) -> bool {
    bits & flag != 0
}

fn require_finite_value(value: f64) -> Result<f64, AnnotationError> {
    if value.is_finite() {
        Ok(value)
    } else {
        Err(AnnotationError::NonFinite)
    }
}

fn authored(row: &AnnotationFacts<'_>, flag: u32, index: usize) -> Result<Option<f64>, AnnotationError> {
    if has(row.facts, flag) {
        Ok(Some(require_finite_value(row.nums[index])?))
    } else {
        Ok(None)
    }
}

fn or_default(
    row: &AnnotationFacts<'_>,
    flag: u32,
    index: usize,
    default: f64,
) -> Result<f64, AnnotationError> {
    Ok(authored(row, flag, index)?.unwrap_or(default))
}

fn style_num(
    row: &AnnotationFacts<'_>,
    bit: u32,
    index: usize,
    default: f64,
) -> Result<f64, AnnotationError> {
    if has(row.style_bits, bit) {
        require_finite_value(row.nums[index])
    } else {
        Ok(default)
    }
}

fn require_flag(
    row: &AnnotationFacts<'_>,
    flag: u32,
    index: usize,
) -> Result<f64, AnnotationError> {
    authored(row, flag, index)?.ok_or(AnnotationError::Length)
}

fn unit_interval(value: f64) -> Result<f64, AnnotationError> {
    if (0.0..=1.0).contains(&value) {
        Ok(value)
    } else {
        Err(AnnotationError::Length)
    }
}

fn positive(value: f64) -> Result<f64, AnnotationError> {
    if value > 0.0 {
        Ok(value)
    } else {
        Err(AnnotationError::Length)
    }
}

fn nonnegative(value: f64) -> Result<f64, AnnotationError> {
    if value >= 0.0 {
        Ok(value)
    } else {
        Err(AnnotationError::Length)
    }
}

fn paint(
    row: &AnnotationFacts<'_>,
    present: u32,
    rgba: [u8; 4],
    default_css: &str,
    opacity: f64,
) -> [u8; 4] {
    if has(row.style_bits, present) {
        apply_opacity_rgba8(rgba, opacity as f32)
    } else {
        color_rgba8(default_css, opacity as f32)
    }
}

fn label_style(
    row: &AnnotationFacts<'_>,
) -> Result<(u8, [u8; 4], [u8; 4], [u8; 4], f64, [u8; 4]), AnnotationError> {
    let opacity = unit_interval(style_num(row, STYLE_LABEL_OPACITY, 16, 1.0)?)?;
    let rgba = paint(row, STYLE_LABEL_COLOR, row.label_color, COLOR_RULE, opacity);
    let has_fill = has(row.style_bits, STYLE_LABEL_BACKGROUND);
    let has_border_color = has(row.style_bits, STYLE_LABEL_BORDER_COLOR);
    let has_border_width = has(row.style_bits, STYLE_LABEL_BORDER_WIDTH);
    if has_border_color != has_border_width {
        return Err(AnnotationError::Order);
    }
    if has_border_color && !has_fill {
        return Err(AnnotationError::Order);
    }
    let fill = if has_fill { row.label_fill } else { [0; 4] };
    let border_rgba = if has_border_color {
        row.label_border
    } else {
        [0; 4]
    };
    let border_width = if has_border_width {
        positive(require_finite_value(row.nums[17])?)?
    } else {
        0.0
    };
    let mut flags = 0u8;
    if has_fill {
        flags |= FLAG_FILL;
    }
    if has_border_color {
        flags |= FLAG_BORDER;
    }
    Ok((flags, rgba, fill, border_rgba, border_width, rgba))
}

fn allowed_style(kind: u8, wrapped: bool, labelled: bool) -> u32 {
    let mut bits = STYLE_COLOR | STYLE_OPACITY;
    if wrapped {
        return bits | STYLE_LABEL_BACKGROUND | STYLE_LABEL_BORDER_COLOR | STYLE_LABEL_BORDER_WIDTH;
    }
    match kind {
        XYAF_KIND_ARROW => bits | STYLE_WIDTH,
        XYAF_KIND_CALLOUT => {
            bits | STYLE_WIDTH
                | STYLE_LABEL_BACKGROUND
                | STYLE_LABEL_BORDER_COLOR
                | STYLE_LABEL_BORDER_WIDTH
        }
        XYAF_KIND_TEXT => {
            bits | STYLE_LABEL_BACKGROUND | STYLE_LABEL_BORDER_COLOR | STYLE_LABEL_BORDER_WIDTH
        }
        XYAF_KIND_RULE => {
            bits |= STYLE_WIDTH | STYLE_DASH | STYLE_LINECAP;
            if labelled {
                bits |= STYLE_LABEL_COLOR
                    | STYLE_LABEL_OPACITY
                    | STYLE_LABEL_BACKGROUND
                    | STYLE_LABEL_BORDER_COLOR
                    | STYLE_LABEL_BORDER_WIDTH;
            }
            bits
        }
        XYAF_KIND_BAND => {
            if labelled {
                bits |= STYLE_LABEL_COLOR
                    | STYLE_LABEL_OPACITY
                    | STYLE_LABEL_BACKGROUND
                    | STYLE_LABEL_BORDER_COLOR
                    | STYLE_LABEL_BORDER_WIDTH;
            }
            bits
        }
        XYAF_KIND_MARKER => {
            bits |= STYLE_STROKE_COLOR | STYLE_STROKE_WIDTH;
            if labelled {
                bits |= STYLE_LABEL_COLOR
                    | STYLE_LABEL_OPACITY
                    | STYLE_LABEL_BACKGROUND
                    | STYLE_LABEL_BORDER_COLOR
                    | STYLE_LABEL_BORDER_WIDTH;
            }
            bits
        }
        _ => bits,
    }
}

fn parse_annotation_facts(bytes: &[u8]) -> Result<Vec<AnnotationFacts<'_>>, AnnotationError> {
    let mut out = Vec::new();
    let mut at = 0usize;
    while at < bytes.len() {
        if bytes.len() - at < XYAF_V1_HEADER_BYTES || bytes.get(at..at + 4) != Some(&XYAF_MAGIC[..])
        {
            return Err(AnnotationError::Length);
        }
        if read_u32(bytes, at + 4)? != XYAF_VERSION {
            return Err(AnnotationError::Version);
        }
        let index = read_u32(bytes, at + 8)?;
        let kind = bytes[at + 12];
        let axis = bytes[at + 13];
        let symbol = bytes[at + 14];
        let anchor = bytes[at + 15];
        let facts = read_u32(bytes, at + 16)?;
        let style_bits = read_u32(bytes, at + 20)?;
        let linecap = bytes[at + 24];
        let dash_count = bytes[at + 25];
        if bytes[at + 26] != 0 || bytes[at + 27] != 0 || kind > XYAF_KIND_MARKER {
            return Err(AnnotationError::Length);
        }
        if facts & !FACT_BITS != 0
            || style_bits & !(STYLE_KNOWN | STYLE_UNSUPPORTED) != 0
            || dash_count > 8
            || (linecap != LINECAP_NONE && linecap != 0 && linecap != 2)
            || (anchor != ANCHOR_UNSET && anchor > 2)
            || axis > 2
        {
            return Err(AnnotationError::Length);
        }
        let text_len = read_u32(bytes, at + 28)? as usize;
        let mut nums = [0.0f64; 18];
        for (i, slot) in nums.iter_mut().enumerate() {
            *slot = read_f64(bytes, at + 32 + i * 8)?;
        }
        let color = read_rgba(bytes, at + 176)?;
        let stroke_color = read_rgba(bytes, at + 180)?;
        let label_color = read_rgba(bytes, at + 184)?;
        let label_fill = read_rgba(bytes, at + 188)?;
        let label_border = read_rgba(bytes, at + 192)?;
        if bytes.get(at + 196..at + 200) != Some(&[0, 0, 0, 0]) {
            return Err(AnnotationError::Length);
        }
        let mut dash = [0.0f32; 8];
        for (i, slot) in dash.iter_mut().enumerate() {
            *slot = read_f32(bytes, at + 200 + i * 4)?;
        }
        let text_at = at + XYAF_V1_HEADER_BYTES;
        let text_end = text_at
            .checked_add(text_len)
            .ok_or(AnnotationError::Limit)?;
        if text_end > bytes.len() {
            return Err(AnnotationError::Length);
        }
        out.push(AnnotationFacts {
            index,
            kind,
            axis,
            symbol,
            anchor,
            facts,
            style_bits,
            linecap,
            dash_count,
            nums,
            color,
            stroke_color,
            label_color,
            label_fill,
            label_border,
            dash,
            text: &bytes[text_at..text_end],
        });
        at = text_end;
    }
    Ok(out)
}

fn encode_style(style: &StyleOut) -> [u8; XYAO_STYLE_BYTES] {
    let mut out = [0u8; XYAO_STYLE_BYTES];
    out[0..4].copy_from_slice(&style.fill);
    out[4..8].copy_from_slice(&style.stroke);
    out[8..16].copy_from_slice(&style.width.to_le_bytes());
    out[16] = style.dash_count;
    out[17] = style.linecap;
    for (i, value) in style.dash.iter().enumerate() {
        let at = 24 + i * 4;
        out[at..at + 4].copy_from_slice(&value.to_le_bytes());
    }
    out
}

/// Pack concatenated XYAF v1 facts into an XYAO v1 envelope.
///
/// Hosts coerce authoring (numbers, CSS, dash/linecap names). Rust owns wrap
/// vs text vs arrow vs callout vs rule/band/marker routing, stable-id tags,
/// style defaults, mark-row expansion, and XYAD framing. ABI 184 routes
/// cartesian unwrapped text `dx`/`dy`/`anchor` through XYAW with `wrap=0`.
/// ABI 185 routes labelled cartesian marker `dx`/`dy`/`anchor` through XYAW
/// with `wrap=0` while keeping the marker mark row. ABI 187 routes cartesian
/// unwrapped text `rotation` through XYAW with `wrap=0` (nonzero rotation
/// writes XYAW v2). ABI 188 routes labelled cartesian marker `rotation`
/// through that same XYAW path (nums[8]; wrap is unused on markers).
pub fn pack_annotation_facts(
    facts: &[u8],
    style_ref_base: u32,
    x0: f64,
    x1: f64,
    y0: f64,
    y1: f64,
) -> Result<Vec<u8>, AnnotationError> {
    if facts.is_empty() {
        return Ok(Vec::new());
    }
    if ![x0, x1, y0, y1].iter().all(|value| value.is_finite()) {
        return Err(AnnotationError::NonFinite);
    }
    let parsed = parse_annotation_facts(facts)?;
    let mut texts = Vec::new();
    let mut attached = Vec::new();
    let mut arrows = Vec::new();
    let mut callouts = Vec::new();
    let mut wrapped = Vec::new();
    let mut styles = Vec::new();
    let mut mark_inputs = Vec::new();
    for row in &parsed {
        if has(row.facts, FACT_HAS_CLASS_NAME) || row.style_bits & STYLE_UNSUPPORTED != 0 {
            return Err(AnnotationError::Order);
        }
        let has_wrap = has(row.facts, FACT_HAS_WRAP);
        let text_layout = row.kind == XYAF_KIND_TEXT
            && (has(row.facts, FACT_HAS_DX)
                || has(row.facts, FACT_HAS_DY)
                || has(row.facts, FACT_HAS_ANCHOR)
                || has(row.facts, FACT_HAS_ROTATION));
        let wrapped_kind = ((row.kind == XYAF_KIND_TEXT || row.kind == XYAF_KIND_CALLOUT)
            && has_wrap)
            || text_layout;
        let labelled = has(row.facts, FACT_HAS_TEXT) && !row.text.is_empty();
        if row.style_bits & !allowed_style(row.kind, wrapped_kind, labelled) != 0 {
            return Err(AnnotationError::Order);
        }
        if wrapped_kind {
            let opacity = unit_interval(style_num(row, STYLE_OPACITY, 13, 1.0)?)?;
            let wrap = if has_wrap {
                nonnegative(require_flag(row, FACT_HAS_WRAP, 8)?)?
            } else {
                0.0
            };
            let x = require_flag(row, FACT_HAS_X, 0)?;
            let y = require_flag(row, FACT_HAS_Y, 1)?;
            let (dx_default, dy_default, css) = if row.kind == XYAF_KIND_CALLOUT {
                (36.0, -30.0, COLOR_CALLOUT)
            } else {
                (0.0, 0.0, COLOR_RULE)
            };
            let dx = or_default(row, FACT_HAS_DX, 6, dx_default)?;
            let dy = or_default(row, FACT_HAS_DY, 7, dy_default)?;
            if row.text.is_empty() {
                return Err(AnnotationError::Text);
            }
            let anchor = if row.anchor == ANCHOR_UNSET { 0 } else { row.anchor };
            let (_, _, fill, border_rgba, border_width, _) = label_style(row)?;
            let rotation = or_default(row, FACT_HAS_ROTATION, 15, 0.0)?;
            wrapped.push(WrappedRow {
                x,
                y,
                dx,
                dy,
                wrap,
                rgba: paint(row, STYLE_COLOR, row.color, css, opacity),
                fill,
                border_rgba,
                border_width,
                kind: u8::from(row.kind == XYAF_KIND_CALLOUT),
                anchor,
                rotation,
                text: row.text,
            });
            continue;
        }
        match row.kind {
            XYAF_KIND_TEXT => {
                let opacity = unit_interval(style_num(row, STYLE_OPACITY, 13, 1.0)?)?;
                if row.text.is_empty() {
                    return Err(AnnotationError::Text);
                }
                let (flags, _, fill, border_rgba, border_width, _) = label_style(row)?;
                texts.push(TextRow {
                    x: require_flag(row, FACT_HAS_X, 0)?,
                    y: require_flag(row, FACT_HAS_Y, 1)?,
                    rgba: paint(row, STYLE_COLOR, row.color, COLOR_RULE, opacity),
                    fill,
                    border_rgba,
                    border_width,
                    flags,
                    text: row.text,
                });
            }
            XYAF_KIND_ARROW => {
                if labelled {
                    return Err(AnnotationError::Order);
                }
                let opacity = unit_interval(style_num(row, STYLE_OPACITY, 13, 1.0)?)?;
                let width = positive(style_num(row, STYLE_WIDTH, 14, 1.5)?)?;
                arrows.push(ArrowRow {
                    stable_id: annotation_id(5, row.index),
                    x0: require_flag(row, FACT_HAS_X0, 2)?,
                    y0: require_flag(row, FACT_HAS_Y0, 3)?,
                    x1: require_flag(row, FACT_HAS_X1, 4)?,
                    y1: require_flag(row, FACT_HAS_Y1, 5)?,
                    rgba: paint(row, STYLE_COLOR, row.color, COLOR_RULE, 1.0),
                    opacity,
                    width,
                });
            }
            XYAF_KIND_CALLOUT => {
                if row.text.is_empty() {
                    return Err(AnnotationError::Text);
                }
                let opacity = unit_interval(style_num(row, STYLE_OPACITY, 13, 1.0)?)?;
                let width = positive(style_num(row, STYLE_WIDTH, 14, 1.5)?)?;
                let (flags, _, fill, border_rgba, border_width, _) = label_style(row)?;
                callouts.push(CalloutRow {
                    x: require_flag(row, FACT_HAS_X, 0)?,
                    y: require_flag(row, FACT_HAS_Y, 1)?,
                    dx: or_default(row, FACT_HAS_DX, 6, 36.0)?,
                    dy: or_default(row, FACT_HAS_DY, 7, -30.0)?,
                    rgba: paint(row, STYLE_COLOR, row.color, COLOR_CALLOUT, 1.0),
                    opacity,
                    width,
                    anchor: if row.anchor == ANCHOR_UNSET { 0 } else { row.anchor },
                    fill,
                    border_rgba,
                    border_width,
                    flags,
                    text: row.text,
                });
            }
            XYAF_KIND_RULE | XYAF_KIND_BAND | XYAF_KIND_MARKER => {
                let default_opacity = if row.kind == XYAF_KIND_BAND { 0.14 } else { 1.0 };
                let opacity = unit_interval(style_num(row, STYLE_OPACITY, 13, default_opacity)?)?;
                let css = if row.kind == XYAF_KIND_BAND {
                    COLOR_BAND
                } else {
                    COLOR_RULE
                };
                let color = paint(row, STYLE_COLOR, row.color, css, opacity);
                let stroke = if has(row.style_bits, STYLE_STROKE_COLOR) {
                    apply_opacity_rgba8(row.stroke_color, opacity as f32)
                } else {
                    color
                };
                let default_width = if row.kind == XYAF_KIND_BAND { 0.0 } else { 1.5 };
                let width_flag = if row.kind == XYAF_KIND_MARKER {
                    STYLE_STROKE_WIDTH
                } else {
                    STYLE_WIDTH
                };
                let width_index = if row.kind == XYAF_KIND_MARKER { 15 } else { 14 };
                let width = if has(row.style_bits, width_flag) {
                    nonnegative(require_finite_value(row.nums[width_index])?)?
                } else {
                    default_width
                };
                if row.kind == XYAF_KIND_RULE && width == 0.0 {
                    return Err(AnnotationError::Length);
                }
                let fill = if row.kind == XYAF_KIND_RULE {
                    [0, 0, 0, 0]
                } else {
                    color
                };
                let style_ref = style_ref_base
                    .checked_add(u32::try_from(styles.len()).map_err(|_| AnnotationError::Limit)?)
                    .ok_or(AnnotationError::Limit)?;
                let dash_count = if row.kind == XYAF_KIND_RULE {
                    row.dash_count
                } else {
                    0
                };
                let linecap = if row.kind == XYAF_KIND_RULE {
                    row.linecap
                } else {
                    LINECAP_NONE
                };
                styles.push(StyleOut {
                    fill,
                    stroke,
                    width,
                    dash_count,
                    linecap,
                    dash: row.dash,
                });
                let (mark_kind, axis, symbol, value0, value1, size, tag) = match row.kind {
                    XYAF_KIND_RULE => {
                        if !has(row.facts, FACT_HAS_AXIS) || (row.axis != 1 && row.axis != 2) {
                            return Err(AnnotationError::Length);
                        }
                        (
                            ANN_KIND_RULE,
                            row.axis - 1,
                            0,
                            require_flag(row, FACT_HAS_VALUE, 9)?,
                            0.0,
                            0.0,
                            1u8,
                        )
                    }
                    XYAF_KIND_BAND => {
                        if !has(row.facts, FACT_HAS_AXIS) || (row.axis != 1 && row.axis != 2) {
                            return Err(AnnotationError::Length);
                        }
                        (
                            ANN_KIND_BAND,
                            row.axis - 1,
                            0,
                            require_flag(row, FACT_HAS_START, 10)?,
                            require_flag(row, FACT_HAS_END, 11)?,
                            0.0,
                            if row.axis == 2 { 4 } else { 2 },
                        )
                    }
                    _ => (
                        ANN_KIND_MARKER,
                        0,
                        row.symbol,
                        require_flag(row, FACT_HAS_X, 0)?,
                        require_flag(row, FACT_HAS_Y, 1)?,
                        positive(or_default(row, FACT_HAS_SIZE, 12, 8.0)?)?,
                        3u8,
                    ),
                };
                mark_inputs.push(AnnotationMarkInput {
                    kind: mark_kind,
                    axis,
                    symbol,
                    style_ref,
                    index: row.index,
                    value0,
                    value1,
                    size,
                });
                if labelled {
                    let (flags, rgba, fill, border_rgba, border_width, _) = label_style(row)?;
                    let layout = has(row.facts, FACT_HAS_DX)
                        || has(row.facts, FACT_HAS_DY)
                        || has(row.facts, FACT_HAS_ANCHOR)
                        || has(row.facts, FACT_HAS_ROTATION);
                    if layout && row.kind == XYAF_KIND_MARKER {
                        wrapped.push(WrappedRow {
                            x: require_flag(row, FACT_HAS_X, 0)?,
                            y: require_flag(row, FACT_HAS_Y, 1)?,
                            dx: or_default(row, FACT_HAS_DX, 6, 0.0)?,
                            dy: or_default(row, FACT_HAS_DY, 7, 0.0)?,
                            wrap: 0.0,
                            rgba,
                            fill,
                            border_rgba,
                            border_width,
                            kind: 0,
                            anchor: if row.anchor == ANCHOR_UNSET {
                                0
                            } else {
                                row.anchor
                            },
                            // Markers never set FACT_HAS_WRAP; nums[8] is rotation.
                            rotation: or_default(row, FACT_HAS_ROTATION, 8, 0.0)?,
                            text: row.text,
                        });
                    } else {
                        attached.push(AttachedRow {
                            stable_id: annotation_id(tag, row.index),
                            rgba,
                            fill,
                            border_rgba,
                            border_width,
                            flags,
                            text: row.text,
                        });
                    }
                }
            }
            _ => return Err(AnnotationError::Length),
        }
    }
    let packed_marks = pack_annotation_marks(&mark_inputs, x0, x1, y0, y1).map_err(pack_err)?;
    let xyad = pack_annotations(AnnotationFrameInput {
        texts: &texts,
        attached: &attached,
        arrows: &arrows,
        callouts: &callouts,
        wrapped: &wrapped,
    })?;
    let n_styles = u32::try_from(styles.len()).map_err(|_| AnnotationError::Limit)?;
    let n_mark_rows = u32::try_from(packed_marks.len()).map_err(|_| AnnotationError::Limit)?;
    let xyad_len = u32::try_from(xyad.len()).map_err(|_| AnnotationError::Limit)?;
    let total = XYAO_V1_HEADER_BYTES
        .checked_add(styles.len().saturating_mul(XYAO_STYLE_BYTES))
        .and_then(|value| value.checked_add(packed_marks.len().saturating_mul(PACKED_SCENE_ROW_BYTES)))
        .and_then(|value| value.checked_add(xyad.len()))
        .ok_or(AnnotationError::Limit)?;
    let mut out = Vec::with_capacity(total);
    out.extend_from_slice(XYAO_MAGIC);
    out.extend_from_slice(&XYAO_VERSION.to_le_bytes());
    out.extend_from_slice(&n_styles.to_le_bytes());
    out.extend_from_slice(&n_mark_rows.to_le_bytes());
    out.extend_from_slice(&xyad_len.to_le_bytes());
    out.extend_from_slice(&0u32.to_le_bytes());
    out.extend_from_slice(&style_ref_base.to_le_bytes());
    out.extend_from_slice(&0u32.to_le_bytes());
    for style in &styles {
        out.extend_from_slice(&encode_style(style));
    }
    for row in &packed_marks {
        out.extend_from_slice(&row.to_bytes());
    }
    out.extend_from_slice(&xyad);
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
            rotation: 0.0,
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

    fn pack_xyaf(
        kind: u8,
        index: u32,
        facts: u32,
        style_bits: u32,
        axis: u8,
        nums: [f64; 18],
        color: [u8; 4],
        text: &[u8],
    ) -> Vec<u8> {
        let mut out = vec![0u8; XYAF_V1_HEADER_BYTES + text.len()];
        out[..4].copy_from_slice(XYAF_MAGIC);
        out[4..8].copy_from_slice(&XYAF_VERSION.to_le_bytes());
        out[8..12].copy_from_slice(&index.to_le_bytes());
        out[12] = kind;
        out[13] = axis;
        out[15] = ANCHOR_UNSET;
        out[16..20].copy_from_slice(&facts.to_le_bytes());
        out[20..24].copy_from_slice(&style_bits.to_le_bytes());
        out[24] = LINECAP_NONE;
        out[28..32].copy_from_slice(&(text.len() as u32).to_le_bytes());
        for (i, value) in nums.iter().enumerate() {
            let at = 32 + i * 8;
            out[at..at + 8].copy_from_slice(&value.to_le_bytes());
        }
        out[176..180].copy_from_slice(&color);
        out[XYAF_V1_HEADER_BYTES..].copy_from_slice(text);
        out
    }

    #[test]
    fn annotation_facts_route_text_and_arrow_into_xyao() {
        let mut nums = [f64::NAN; 18];
        nums[0] = 0.5;
        nums[1] = 0.25;
        let text = pack_xyaf(
            XYAF_KIND_TEXT,
            0,
            FACT_HAS_X | FACT_HAS_Y | FACT_HAS_TEXT,
            STYLE_COLOR,
            0,
            nums,
            [102, 112, 133, 255],
            b"hi",
        );
        let mut arrow_nums = [f64::NAN; 18];
        arrow_nums[2] = 0.0;
        arrow_nums[3] = 0.0;
        arrow_nums[4] = 1.0;
        arrow_nums[5] = 1.0;
        let arrow = pack_xyaf(
            XYAF_KIND_ARROW,
            1,
            FACT_HAS_X0 | FACT_HAS_Y0 | FACT_HAS_X1 | FACT_HAS_Y1,
            STYLE_COLOR,
            0,
            arrow_nums,
            [102, 112, 133, 255],
            b"",
        );
        let mut facts = text;
        facts.extend_from_slice(&arrow);
        let packed = pack_annotation_facts(&facts, 3, 0.0, 10.0, -1.0, 1.0).unwrap();
        assert_eq!(&packed[..4], b"XYAO");
        assert_eq!(u32::from_le_bytes(packed[8..12].try_into().unwrap()), 0);
        assert_eq!(u32::from_le_bytes(packed[12..16].try_into().unwrap()), 0);
        let xyad_len = u32::from_le_bytes(packed[16..20].try_into().unwrap()) as usize;
        let xyad = &packed[XYAO_V1_HEADER_BYTES..XYAO_V1_HEADER_BYTES + xyad_len];
        assert_eq!(&xyad[..4], b"XYAD");
        assert!(xyad.windows(4).any(|window| window == b"XYAT"));
        assert!(xyad.windows(4).any(|window| window == b"XYAR"));
        assert!(xyad.windows(2).any(|window| window == b"hi"));
    }

    #[test]
    fn annotation_facts_expand_rule_and_default_wrapped_text_offset() {
        let mut rule_nums = [f64::NAN; 18];
        rule_nums[9] = 1.5;
        let rule = pack_xyaf(
            XYAF_KIND_RULE,
            7,
            FACT_HAS_VALUE | FACT_HAS_AXIS,
            STYLE_COLOR,
            1,
            rule_nums,
            [102, 112, 133, 255],
            b"",
        );
        let mut wrap_nums = [f64::NAN; 18];
        wrap_nums[0] = 0.5;
        wrap_nums[1] = 0.5;
        wrap_nums[8] = 96.0;
        let wrapped = pack_xyaf(
            XYAF_KIND_TEXT,
            0,
            FACT_HAS_WRAP | FACT_HAS_X | FACT_HAS_Y | FACT_HAS_TEXT,
            STYLE_COLOR,
            0,
            wrap_nums,
            [102, 112, 133, 255],
            b"wrap",
        );
        let packed_rule = pack_annotation_facts(&rule, 2, 0.0, 10.0, -1.0, 1.0).unwrap();
        assert_eq!(u32::from_le_bytes(packed_rule[8..12].try_into().unwrap()), 1);
        assert_eq!(
            u32::from_le_bytes(packed_rule[12..16].try_into().unwrap()),
            2
        );
        let style_ref = u32::from_le_bytes(packed_rule[32 + 56 + 4..32 + 56 + 8].try_into().unwrap());
        assert_eq!(style_ref, 2);
        let packed_wrap = pack_annotation_facts(&wrapped, 0, 0.0, 1.0, 0.0, 1.0).unwrap();
        let xyad_len = u32::from_le_bytes(packed_wrap[16..20].try_into().unwrap()) as usize;
        let xyad = &packed_wrap[XYAO_V1_HEADER_BYTES..XYAO_V1_HEADER_BYTES + xyad_len];
        assert!(xyad.windows(4).any(|window| window == b"XYAW"));
        assert_eq!(u32::from_le_bytes(xyad[4..8].try_into().unwrap()), 3);
        assert_eq!(&xyad[xyad.len() - 4..], b"wrap");
    }

    #[test]
    fn annotation_facts_route_unwrapped_text_layout_through_xyaw() {
        let mut nums = [f64::NAN; 18];
        nums[0] = 0.5;
        nums[1] = 0.5;
        nums[6] = 6.0;
        let text = pack_xyaf(
            XYAF_KIND_TEXT,
            0,
            FACT_HAS_X | FACT_HAS_Y | FACT_HAS_DX | FACT_HAS_TEXT,
            STYLE_COLOR,
            0,
            nums,
            [102, 112, 133, 255],
            b"offset",
        );
        let packed = pack_annotation_facts(&text, 0, 0.0, 1.0, 0.0, 1.0).unwrap();
        let xyad_len = u32::from_le_bytes(packed[16..20].try_into().unwrap()) as usize;
        let xyad = &packed[XYAO_V1_HEADER_BYTES..XYAO_V1_HEADER_BYTES + xyad_len];
        assert!(xyad.windows(4).any(|window| window == b"XYAW"));
        assert_eq!(&xyad[xyad.len() - 6..], b"offset");
        let xyaw_at = xyad.windows(4).position(|window| window == b"XYAW").unwrap();
        let row = &xyad[xyaw_at + 12..];
        let wrap = f64::from_le_bytes(row[32..40].try_into().unwrap());
        let dx = f64::from_le_bytes(row[16..24].try_into().unwrap());
        assert_eq!(wrap, 0.0);
        assert_eq!(dx, 6.0);
    }

    #[test]
    fn annotation_facts_route_unwrapped_text_rotation_through_xyaw() {
        let mut nums = [f64::NAN; 18];
        nums[0] = 0.5;
        nums[1] = 0.5;
        nums[15] = 30.0;
        let text = pack_xyaf(
            XYAF_KIND_TEXT,
            0,
            FACT_HAS_X | FACT_HAS_Y | FACT_HAS_ROTATION | FACT_HAS_TEXT,
            STYLE_COLOR,
            0,
            nums,
            [102, 112, 133, 255],
            b"rotated",
        );
        let packed = pack_annotation_facts(&text, 0, 0.0, 1.0, 0.0, 1.0).unwrap();
        let xyad_len = u32::from_le_bytes(packed[16..20].try_into().unwrap()) as usize;
        let xyad = &packed[XYAO_V1_HEADER_BYTES..XYAO_V1_HEADER_BYTES + xyad_len];
        assert!(xyad.windows(4).any(|window| window == b"XYAW"));
        assert_eq!(&xyad[xyad.len() - 7..], b"rotated");
        let xyaw_at = xyad.windows(4).position(|window| window == b"XYAW").unwrap();
        assert_eq!(u32::from_le_bytes(xyad[xyaw_at + 4..xyaw_at + 8].try_into().unwrap()), 2);
        let row = &xyad[xyaw_at + 12..];
        let wrap = f64::from_le_bytes(row[32..40].try_into().unwrap());
        let rotation = f64::from_le_bytes(row[64..72].try_into().unwrap());
        assert_eq!(wrap, 0.0);
        assert_eq!(rotation, 30.0);
    }

    #[test]
    fn annotation_facts_route_labelled_marker_layout_through_xyaw() {
        let mut nums = [f64::NAN; 18];
        nums[0] = 0.5;
        nums[1] = 0.5;
        nums[7] = -8.0;
        let marker = pack_xyaf(
            XYAF_KIND_MARKER,
            0,
            FACT_HAS_X | FACT_HAS_Y | FACT_HAS_DY | FACT_HAS_TEXT,
            STYLE_COLOR,
            0,
            nums,
            [37, 99, 235, 255],
            b"pin",
        );
        let packed = pack_annotation_facts(&marker, 0, 0.0, 1.0, 0.0, 1.0).unwrap();
        assert_eq!(u32::from_le_bytes(packed[8..12].try_into().unwrap()), 1);
        assert_eq!(u32::from_le_bytes(packed[12..16].try_into().unwrap()), 1);
        let xyad_len = u32::from_le_bytes(packed[16..20].try_into().unwrap()) as usize;
        let xyad_at = XYAO_V1_HEADER_BYTES + XYAO_STYLE_BYTES + PACKED_SCENE_ROW_BYTES;
        let xyad = &packed[xyad_at..xyad_at + xyad_len];
        assert!(xyad.windows(4).any(|window| window == b"XYAW"));
        assert_eq!(&xyad[xyad.len() - 3..], b"pin");
        let xyaw_at = xyad.windows(4).position(|window| window == b"XYAW").unwrap();
        let row = &xyad[xyaw_at + 12..];
        let wrap = f64::from_le_bytes(row[32..40].try_into().unwrap());
        let dy = f64::from_le_bytes(row[24..32].try_into().unwrap());
        assert_eq!(wrap, 0.0);
        assert_eq!(dy, -8.0);
        let xyal_at = xyad.windows(4).position(|window| window == b"XYAL").unwrap();
        let xyal_count = u32::from_le_bytes(xyad[xyal_at + 8..xyal_at + 12].try_into().unwrap());
        assert_eq!(xyal_count, 0);
    }

    #[test]
    fn annotation_facts_route_labelled_marker_rotation_through_xyaw() {
        let mut nums = [f64::NAN; 18];
        nums[0] = 0.5;
        nums[1] = 0.5;
        nums[8] = 30.0;
        nums[15] = 1.5;
        let marker = pack_xyaf(
            XYAF_KIND_MARKER,
            0,
            FACT_HAS_X | FACT_HAS_Y | FACT_HAS_ROTATION | FACT_HAS_TEXT,
            STYLE_COLOR | STYLE_STROKE_WIDTH,
            0,
            nums,
            [37, 99, 235, 255],
            b"rotated",
        );
        let packed = pack_annotation_facts(&marker, 0, 0.0, 1.0, 0.0, 1.0).unwrap();
        assert_eq!(u32::from_le_bytes(packed[12..16].try_into().unwrap()), 1);
        let xyad_len = u32::from_le_bytes(packed[16..20].try_into().unwrap()) as usize;
        let xyad_at = XYAO_V1_HEADER_BYTES + XYAO_STYLE_BYTES + PACKED_SCENE_ROW_BYTES;
        let xyad = &packed[xyad_at..xyad_at + xyad_len];
        assert!(xyad.windows(4).any(|window| window == b"XYAW"));
        assert_eq!(&xyad[xyad.len() - 7..], b"rotated");
        let xyaw_at = xyad.windows(4).position(|window| window == b"XYAW").unwrap();
        assert_eq!(
            u32::from_le_bytes(xyad[xyaw_at + 4..xyaw_at + 8].try_into().unwrap()),
            2
        );
        let row = &xyad[xyaw_at + 12..];
        let wrap = f64::from_le_bytes(row[32..40].try_into().unwrap());
        let rotation = f64::from_le_bytes(row[64..72].try_into().unwrap());
        assert_eq!(wrap, 0.0);
        assert_eq!(rotation, 30.0);
    }
}
