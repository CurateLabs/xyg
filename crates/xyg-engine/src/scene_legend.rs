//! Compact Figure→Scene XYLG legend framing (M2 #271).
//!
//! Hosts validate authoring keys (`ncols`, `toggle`, location names) and
//! pass loc/flags, font sizes, paints, title, and per-entry meta plus
//! concatenated labels. Rust owns the XYLG header, entry table, text
//! offsets, and bounded-text rejection so Python and Node cannot drift on
//! the legend envelope.

use crate::scene::{MAX_SCENE_LEGEND_ENTRIES, MAX_SCENE_LEGEND_TEXT_BYTES, MAX_SCENE_TEXT_BYTES};

pub const LEGEND_HEADER_BYTES: usize = 48;
pub const LEGEND_ENTRY_BYTES: usize = 24;
pub const LEGEND_META_BYTES: usize = 16;

const XYLG: &[u8; 4] = b"XYLG";
const FLAG_AUTHORED_LOC: u8 = 1 << 0;
const FLAG_AUTHORED_FONT: u8 = 1 << 1;
const FLAG_AUTHORED_TITLE_FONT: u8 = 1 << 2;
const FLAG_AUTHORED_COLOR: u8 = 1 << 3;
const FLAG_AUTHORED_BACKGROUND: u8 = 1 << 4;
const FLAG_MASK: u8 = FLAG_AUTHORED_LOC
    | FLAG_AUTHORED_FONT
    | FLAG_AUTHORED_TITLE_FONT
    | FLAG_AUTHORED_COLOR
    | FLAG_AUTHORED_BACKGROUND;

/// Why a legend frame request was rejected. Discriminants are the C-ABI
/// error codes (returned negated by `xyg_scene_pack_legend`).
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
#[allow(dead_code)] // Version is reserved for a future envelope; C ABI returns -2.
pub enum LegendError {
    Length = 1,
    Version = 2,
    Limit = 3,
    Output = 4,
    Font = 5,
    Location = 6,
}

/// One legend entry before XYLG framing.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct LegendEntry<'a> {
    pub style_ref: u32,
    pub kind: u8,
    pub symbol: u8,
    pub fill_rgba: [u8; 4],
    pub stroke_rgba: [u8; 4],
    pub label: &'a [u8],
}

/// Authoring literals for one primary Scene legend.
#[derive(Clone, Copy, Debug)]
pub struct LegendFrameInput<'a> {
    pub loc: u8,
    pub flags: u8,
    pub font_size: f64,
    pub title_font_size: f64,
    pub text_rgba: [u8; 4],
    pub frame_fill_rgba: [u8; 4],
    pub title: &'a [u8],
    pub entries: &'a [LegendEntry<'a>],
}

fn require_font(authored: bool, size: f64) -> Result<(), LegendError> {
    if authored {
        if size.is_finite() && (1.0..=1000.0).contains(&size) {
            Ok(())
        } else {
            Err(LegendError::Font)
        }
    } else if size == 0.0 {
        Ok(())
    } else {
        Err(LegendError::Font)
    }
}

/// Number of XYLG bytes one framed legend will emit.
pub fn packed_legend_len(n_entries: usize, text_len: usize) -> Result<usize, LegendError> {
    let table = n_entries
        .checked_mul(LEGEND_ENTRY_BYTES)
        .ok_or(LegendError::Limit)?;
    LEGEND_HEADER_BYTES
        .checked_add(table)
        .and_then(|value| value.checked_add(text_len))
        .ok_or(LegendError::Limit)
}

/// Frame a primary Scene legend as XYLG bytes.
pub fn pack_legend(input: LegendFrameInput<'_>) -> Result<Vec<u8>, LegendError> {
    if input.entries.is_empty() {
        return Ok(Vec::new());
    }
    if input.flags & !FLAG_MASK != 0 {
        return Err(LegendError::Length);
    }
    if input.loc > 8 {
        return Err(LegendError::Location);
    }
    require_font(input.flags & FLAG_AUTHORED_FONT != 0, input.font_size)?;
    require_font(
        input.flags & FLAG_AUTHORED_TITLE_FONT != 0,
        input.title_font_size,
    )?;
    if input.entries.len() > MAX_SCENE_LEGEND_ENTRIES {
        return Err(LegendError::Limit);
    }
    if input.title.len() > MAX_SCENE_TEXT_BYTES || input.title.contains(&0) {
        return Err(LegendError::Limit);
    }
    let mut labels_len = 0usize;
    for entry in input.entries {
        if entry.label.is_empty()
            || entry.label.len() > MAX_SCENE_TEXT_BYTES
            || entry.label.contains(&0)
        {
            return Err(LegendError::Limit);
        }
        labels_len = labels_len
            .checked_add(entry.label.len())
            .ok_or(LegendError::Limit)?;
    }
    let text_len = input
        .title
        .len()
        .checked_add(labels_len)
        .ok_or(LegendError::Limit)?;
    if text_len > MAX_SCENE_LEGEND_TEXT_BYTES {
        return Err(LegendError::Limit);
    }
    let total = packed_legend_len(input.entries.len(), text_len)?;
    let mut out = vec![0u8; total];
    out[..4].copy_from_slice(XYLG);
    out[4] = input.loc;
    out[5] = input.flags;
    out[8..12].copy_from_slice(&(input.entries.len() as u32).to_le_bytes());
    out[12..16].copy_from_slice(&(input.title.len() as u32).to_le_bytes());
    out[16..24].copy_from_slice(&input.font_size.to_le_bytes());
    out[24..32].copy_from_slice(&input.title_font_size.to_le_bytes());
    if input.flags & FLAG_AUTHORED_COLOR != 0 {
        out[32..36].copy_from_slice(&input.text_rgba);
    }
    if input.flags & FLAG_AUTHORED_BACKGROUND != 0 {
        out[36..40].copy_from_slice(&input.frame_fill_rgba);
    }
    let mut text_offset = input.title.len() as u32;
    for (index, entry) in input.entries.iter().enumerate() {
        let at = LEGEND_HEADER_BYTES + index * LEGEND_ENTRY_BYTES;
        out[at..at + 4].copy_from_slice(&entry.style_ref.to_le_bytes());
        out[at + 4] = entry.kind;
        out[at + 5] = entry.symbol;
        out[at + 8..at + 12].copy_from_slice(&text_offset.to_le_bytes());
        out[at + 12..at + 16].copy_from_slice(&(entry.label.len() as u32).to_le_bytes());
        out[at + 16..at + 20].copy_from_slice(&entry.fill_rgba);
        out[at + 20..at + 24].copy_from_slice(&entry.stroke_rgba);
        text_offset = text_offset
            .checked_add(entry.label.len() as u32)
            .ok_or(LegendError::Limit)?;
    }
    let text_at = LEGEND_HEADER_BYTES + input.entries.len() * LEGEND_ENTRY_BYTES;
    out[text_at..text_at + input.title.len()].copy_from_slice(input.title);
    let mut label_at = text_at + input.title.len();
    for entry in input.entries {
        out[label_at..label_at + entry.label.len()].copy_from_slice(entry.label);
        label_at += entry.label.len();
    }
    Ok(out)
}

/// Decode packed 16-byte entry meta plus concatenated labels.
pub fn entries_from_meta<'a>(
    meta: &'a [u8],
    label_lens: &'a [u32],
    labels: &'a [u8],
) -> Result<Vec<LegendEntry<'a>>, LegendError> {
    if meta.len() != label_lens.len().saturating_mul(LEGEND_META_BYTES) {
        return Err(LegendError::Length);
    }
    let mut offset = 0usize;
    let mut entries = Vec::with_capacity(label_lens.len());
    for (index, &len) in label_lens.iter().enumerate() {
        let len = usize::try_from(len).map_err(|_| LegendError::Limit)?;
        let end = offset.checked_add(len).ok_or(LegendError::Limit)?;
        let label = labels.get(offset..end).ok_or(LegendError::Length)?;
        let at = index * LEGEND_META_BYTES;
        let style_ref = u32::from_le_bytes(meta[at..at + 4].try_into().unwrap());
        let mut fill = [0u8; 4];
        let mut stroke = [0u8; 4];
        fill.copy_from_slice(&meta[at + 8..at + 12]);
        stroke.copy_from_slice(&meta[at + 12..at + 16]);
        entries.push(LegendEntry {
            style_ref,
            kind: meta[at + 4],
            symbol: meta[at + 5],
            fill_rgba: fill,
            stroke_rgba: stroke,
            label,
        });
        offset = end;
    }
    if offset != labels.len() {
        return Err(LegendError::Length);
    }
    Ok(entries)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn empty_entries_emit_no_bytes() {
        let framed = pack_legend(LegendFrameInput {
            loc: 0,
            flags: 0,
            font_size: 0.0,
            title_font_size: 0.0,
            text_rgba: [0; 4],
            frame_fill_rgba: [0; 4],
            title: b"",
            entries: &[],
        })
        .unwrap();
        assert!(framed.is_empty());
    }

    #[test]
    fn frames_header_entry_and_label() {
        let label = b"series";
        let entry = LegendEntry {
            style_ref: 1,
            kind: 0,
            symbol: 3,
            fill_rgba: [0x39, 0x87, 0xe5, 255],
            stroke_rgba: [0, 0, 0, 0],
            label,
        };
        let framed = pack_legend(LegendFrameInput {
            loc: 1,
            flags: FLAG_AUTHORED_LOC | FLAG_AUTHORED_COLOR,
            font_size: 0.0,
            title_font_size: 0.0,
            text_rgba: [32, 32, 32, 255],
            frame_fill_rgba: [0; 4],
            title: b"",
            entries: &[entry],
        })
        .unwrap();
        assert_eq!(&framed[..4], b"XYLG");
        assert_eq!(framed[4], 1);
        assert_eq!(framed[5], FLAG_AUTHORED_LOC | FLAG_AUTHORED_COLOR);
        assert_eq!(&framed[32..36], &[32, 32, 32, 255]);
        assert_eq!(&framed[36..40], &[0, 0, 0, 0]);
        let at = LEGEND_HEADER_BYTES;
        assert_eq!(&framed[at..at + 4], &1u32.to_le_bytes());
        assert_eq!(framed[at + 4], 0);
        assert_eq!(framed[at + 5], 3);
        assert_eq!(&framed[at + 8..at + 12], &0u32.to_le_bytes());
        assert_eq!(&framed[at + 12..at + 16], &6u32.to_le_bytes());
        assert_eq!(&framed[at + 16..at + 20], &[0x39, 0x87, 0xe5, 255]);
        assert_eq!(&framed[at + LEGEND_ENTRY_BYTES..], label);
    }

    #[test]
    fn authored_font_must_be_in_range() {
        assert_eq!(
            pack_legend(LegendFrameInput {
                loc: 0,
                flags: FLAG_AUTHORED_FONT,
                font_size: 0.5,
                title_font_size: 0.0,
                text_rgba: [0; 4],
                frame_fill_rgba: [0; 4],
                title: b"",
                entries: &[LegendEntry {
                    style_ref: 0,
                    kind: 1,
                    symbol: 0,
                    fill_rgba: [0; 4],
                    stroke_rgba: [0; 4],
                    label: b"a",
                }],
            }),
            Err(LegendError::Font)
        );
    }
}
