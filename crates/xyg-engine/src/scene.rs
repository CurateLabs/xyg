//! Versioned, bounded canonical scene records and deterministic SVG emission.
//!
//! This first vertical slice owns the built-in scatter-mark scene. Hosts still
//! coerce author input and resolve paint channels, but marker geometry,
//! stroke-inclusive sizing, validation, bounds, and SVG construction live here.

use crate::css;
use crate::svg::push_num;
use std::fmt::Write;

pub const SCENE_VERSION: u32 = 16;
pub const MAX_SCENE_MARKS: usize = 2_000_000;
pub const MAX_AXIS_TICKS: usize = 200;
pub const MAX_SCENE_STYLES: usize = 65_536;
pub const MAX_SCENE_TEXT_BYTES: usize = 4_096;
pub const SCENE_BATCH_HEADER_BYTES: usize = 160;
pub const SCENE_STYLE_RECORD_BYTES: usize = 16;
pub const SCENE_BATCH_RECORD_BYTES: usize = 56;
/// Fixed chrome trailer before UTF-8 labels and authored tick payloads (Scene v9).
pub const SCENE_CHROME_TRAILER_BYTES: usize = 248;
pub const SCENE_CHROME_STYLE_INPUT_BYTES: usize = 200;
pub const MAX_SCENE_CHROME_LENGTH: f64 = 1_000.0;
pub const BROWSER_PAINTER_VERSION: u32 = 11;
pub const BROWSER_PAINTER_HEADER_BYTES: usize = 300;
pub const BROWSER_PAINTER_TRACE_BYTES: usize = 64;
pub const BROWSER_PAINTER_TICK_BYTES: usize = 16;
/// Hard ceiling on browser-side trace objects created from one painter output.
/// A valid Scene can alternate run identity/style on every record, so this is
/// independent of the byte arena and prevents O(records) ChartView/GL objects.
pub const MAX_BROWSER_PAINTER_TRACES: usize = 1024;
pub const MAX_SCENE_LEGEND_ENTRIES: usize = 128;
pub const MAX_SCENE_LEGEND_TEXT_BYTES: usize = 16_384;
pub const MAX_SCENE_LABELS: usize = 128;
pub const MAX_SCENE_LABEL_TEXT_BYTES: usize = 8_192;
pub const MAX_AUTHORED_TEXT_ANNOTATIONS: usize = 128;
/// Literal color tables are deliberately small so every renderer can consume
/// exactly the same resolved Scene decoration without a host colormap registry.
pub const MAX_SCENE_COLORBAR_STOPS: usize = 16;
pub const MAX_SCENE_COLORBAR_TEXT_BYTES: usize = 4_096;
const SCENE_LABEL_HEADER_BYTES: usize = 16;
const SCENE_LABEL_RECORD_BYTES: usize = 40;
pub const SCENE_SUPPORT_REQUEST_VERSION: u32 = 1;
pub const SCENE_FEATURE_POLAR: u64 = 1 << 0;
pub const SCENE_FEATURE_CUSTOM_FONT: u64 = 1 << 1;
pub const SCENE_FEATURE_BROWSER_CSS: u64 = 1 << 2;
pub const SCENE_FEATURE_GRADIENT: u64 = 1 << 3;
pub const SCENE_FEATURE_COLORBAR: u64 = 1 << 4;
pub const SCENE_FEATURE_EXTRA_LEGEND: u64 = 1 << 5;
pub const SCENE_FEATURE_AUTHORED_TICK_LABELS: u64 = 1 << 6;
pub const SCENE_FEATURE_LABELED_ANNOTATION: u64 = 1 << 7;
pub const SCENE_FEATURE_CALLOUT_OR_ARROW: u64 = 1 << 8;
pub const SCENE_FEATURE_MASK: u64 = (1 << 9) - 1;

/// Return Rust's stable, ordered diagnostic for the first unsupported authored
/// Scene feature. An empty slice means the bounded Cartesian subset is
/// supported. Hosts only project literal feature-presence bits; they do not
/// choose support policy or wording.
pub fn scene_support_reason(version: u32, features: u64) -> Result<&'static str, SceneError> {
    if version != SCENE_SUPPORT_REQUEST_VERSION || features & !SCENE_FEATURE_MASK != 0 {
        return Err(SceneError::Version);
    }
    let reasons = [
        (SCENE_FEATURE_POLAR, "XYG_SCENE_UNSUPPORTED_POLAR: Scene v12 supports Cartesian coordinates only"),
        (SCENE_FEATURE_CUSTOM_FONT, "XYG_SCENE_UNSUPPORTED_CUSTOM_FONT: Scene v12 does not encode custom font resources"),
        (SCENE_FEATURE_BROWSER_CSS, "XYG_SCENE_UNSUPPORTED_BROWSER_CSS: Scene v12 does not encode browser-only CSS or class behavior"),
        (SCENE_FEATURE_GRADIENT, "XYG_SCENE_UNSUPPORTED_GRADIENT: Scene v12 supports solid literal paints only"),
        // A host sets this bit only when its literal XYCB framing is malformed
        // or outside the bounded Scene subset; valid XYCB is consumed by Rust.
        (SCENE_FEATURE_COLORBAR, "XYG_SCENE_UNSUPPORTED_COLORBAR: colorbar requires bounded literal RGBA Scene framing"),
        (SCENE_FEATURE_EXTRA_LEGEND, "XYG_SCENE_UNSUPPORTED_EXTRA_LEGEND: Scene v12 supports one primary static legend only"),
        (SCENE_FEATURE_CALLOUT_OR_ARROW, "XYG_SCENE_UNSUPPORTED_CALLOUT_ARROW: Scene v12 does not yet encode callouts or arrows"),
    ];
    Ok(reasons
        .into_iter()
        .find_map(|(flag, reason)| (features & flag != 0).then_some(reason))
        .unwrap_or(""))
}
const SCENE_ANNOTATION_ID_MASK: u64 = 0xffff_0000_0000_0000;
const SCENE_ANNOTATION_ID_PREFIX: u64 = 0x5859_0000_0000_0000;

fn is_scene_annotation_id(stable_id: u64) -> bool {
    stable_id & SCENE_ANNOTATION_ID_MASK == SCENE_ANNOTATION_ID_PREFIX
}

fn scene_edge_eq(actual: f64, expected: f64) -> bool {
    (actual - expected).abs() <= 8.0 * f64::EPSILON * actual.abs().max(expected.abs()).max(1.0)
}
const SCENE_LEGEND_HEADER_BYTES: usize = 48;
const SCENE_LEGEND_ENTRY_BYTES: usize = 24;
pub const MAX_SCENE_LEGEND_INPUT_BYTES: usize = SCENE_LEGEND_HEADER_BYTES
    + MAX_SCENE_LEGEND_ENTRIES * SCENE_LEGEND_ENTRY_BYTES
    + MAX_SCENE_LEGEND_TEXT_BYTES;
const MAX_BROWSER_LEGEND_PATH_BYTES: usize = 256;
pub const BROWSER_PAINTER_MAX_LEGEND_BYTES: usize = 57424;
const _: () = assert!(
    BROWSER_PAINTER_MAX_LEGEND_BYTES
        == MAX_SCENE_LEGEND_INPUT_BYTES
            + 32
            + MAX_SCENE_LEGEND_ENTRIES * (40 + MAX_BROWSER_LEGEND_PATH_BYTES)
);

#[derive(Clone, Debug, PartialEq)]
pub struct SceneLabel {
    pub stable_id: u64,
    pub x: f64,
    pub y: f64,
    pub font_size: f64,
    pub rgba: [u8; 4],
    pub text: String,
}

fn encode_scene_labels(labels: &[SceneLabel]) -> Result<Vec<u8>, SceneError> {
    if labels.is_empty() {
        return Ok(Vec::new());
    }
    let text_bytes = labels.iter().try_fold(0usize, |total, label| {
        total.checked_add(label.text.len()).ok_or(SceneError::Limit)
    })?;
    if labels.len() > MAX_SCENE_LABELS || text_bytes > MAX_SCENE_LABEL_TEXT_BYTES {
        return Err(SceneError::Limit);
    }
    let mut out = Vec::with_capacity(
        SCENE_LABEL_HEADER_BYTES + labels.len() * SCENE_LABEL_RECORD_BYTES + text_bytes,
    );
    out.extend_from_slice(b"XYLB");
    out.extend_from_slice(&1u32.to_le_bytes());
    out.extend_from_slice(&(labels.len() as u32).to_le_bytes());
    out.extend_from_slice(&(text_bytes as u32).to_le_bytes());
    for label in labels {
        if label.text.is_empty()
            || label.text.contains('\0')
            || !label.x.is_finite()
            || !label.y.is_finite()
            || !label.font_size.is_finite()
            || !(1.0..=MAX_SCENE_CHROME_LENGTH).contains(&label.font_size)
        {
            return Err(SceneError::NonFinite);
        }
        out.extend_from_slice(&label.stable_id.to_le_bytes());
        out.extend_from_slice(&label.x.to_le_bytes());
        out.extend_from_slice(&label.y.to_le_bytes());
        out.extend_from_slice(&label.font_size.to_le_bytes());
        out.extend_from_slice(&label.rgba);
        out.extend_from_slice(&(label.text.len() as u32).to_le_bytes());
    }
    for label in labels {
        out.extend_from_slice(label.text.as_bytes());
    }
    Ok(out)
}

fn decode_scene_labels(bytes: &[u8]) -> Result<Vec<SceneLabel>, SceneError> {
    if bytes.is_empty() {
        return Ok(Vec::new());
    }
    if bytes.len() < SCENE_LABEL_HEADER_BYTES || &bytes[..4] != b"XYLB" || batch_u32(bytes, 4)? != 1
    {
        return Err(SceneError::Length);
    }
    let count = batch_u32(bytes, 8)? as usize;
    let text_bytes = batch_u32(bytes, 12)? as usize;
    if count > MAX_SCENE_LABELS || text_bytes > MAX_SCENE_LABEL_TEXT_BYTES {
        return Err(SceneError::Limit);
    }
    let table_end = SCENE_LABEL_HEADER_BYTES
        .checked_add(
            count
                .checked_mul(SCENE_LABEL_RECORD_BYTES)
                .ok_or(SceneError::Limit)?,
        )
        .ok_or(SceneError::Limit)?;
    if table_end.checked_add(text_bytes) != Some(bytes.len()) {
        return Err(SceneError::Length);
    }
    let mut text_at = table_end;
    let mut labels = Vec::with_capacity(count);
    for index in 0..count {
        let at = SCENE_LABEL_HEADER_BYTES + index * SCENE_LABEL_RECORD_BYTES;
        let len = batch_u32(bytes, at + 36)? as usize;
        let end = text_at.checked_add(len).ok_or(SceneError::Limit)?;
        let text = std::str::from_utf8(bytes.get(text_at..end).ok_or(SceneError::Length)?)
            .map_err(|_| SceneError::Length)?
            .to_owned();
        labels.push(SceneLabel {
            stable_id: batch_u64(bytes, at)?,
            x: batch_f64(bytes, at + 8)?,
            y: batch_f64(bytes, at + 16)?,
            font_size: batch_f64(bytes, at + 24)?,
            rgba: bytes[at + 32..at + 36].try_into().unwrap(),
            text,
        });
        text_at = end;
    }
    encode_scene_labels(&labels)?;
    Ok(labels)
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
#[repr(u8)]
pub enum LegendLocation {
    UpperRight = 0,
    UpperLeft = 1,
    LowerLeft = 2,
    LowerRight = 3,
    CenterRight = 4,
    CenterLeft = 5,
    UpperCenter = 6,
    LowerCenter = 7,
    Center = 8,
}

impl LegendLocation {
    fn from_code(value: u8) -> Result<Self, SceneError> {
        match value {
            0 => Ok(Self::UpperRight),
            1 => Ok(Self::UpperLeft),
            2 => Ok(Self::LowerLeft),
            3 => Ok(Self::LowerRight),
            4 => Ok(Self::CenterRight),
            5 => Ok(Self::CenterLeft),
            6 => Ok(Self::UpperCenter),
            7 => Ok(Self::LowerCenter),
            8 => Ok(Self::Center),
            _ => Err(SceneError::Length),
        }
    }
}

#[derive(Clone, Debug, PartialEq)]
pub struct SceneLegendEntry {
    pub style_ref: usize,
    pub kind: SceneRecordKind,
    pub symbol: u8,
    pub fill_rgba: [u8; 4],
    pub stroke_rgba: [u8; 4],
    pub label: String,
}

#[derive(Clone, Debug, PartialEq)]
pub struct SceneLegend {
    pub location: LegendLocation,
    pub title: String,
    pub font_size: f64,
    pub title_font_size: f64,
    pub text_rgba: [u8; 4],
    pub frame_fill_rgba: [u8; 4],
    pub frame_stroke_rgba: [u8; 4],
    pub entries: Vec<SceneLegendEntry>,
}

impl SceneLegend {
    fn validate_constructed(&self) -> Result<(), SceneError> {
        if self.entries.iter().any(|entry| {
            (entry.kind == SceneRecordKind::Scatter
                && entry.symbol > ScatterSymbol::VerticalLine as u8)
                || (entry.kind != SceneRecordKind::Scatter && entry.symbol != 0)
        }) {
            return Err(SceneError::Length);
        }
        let text_bytes = self
            .title
            .len()
            .checked_add(self.entries.iter().map(|entry| entry.label.len()).sum())
            .ok_or(SceneError::Limit)?;
        if self.entries.is_empty()
            || self.entries.len() > MAX_SCENE_LEGEND_ENTRIES
            || self.title.len() > MAX_SCENE_TEXT_BYTES
            || self.title.contains('\0')
            || text_bytes > MAX_SCENE_LEGEND_TEXT_BYTES
            || !(1.0..=MAX_SCENE_CHROME_LENGTH).contains(&self.font_size)
            || !(1.0..=MAX_SCENE_CHROME_LENGTH).contains(&self.title_font_size)
            || self.entries.iter().any(|entry| {
                entry.label.is_empty()
                    || entry.label.len() > MAX_SCENE_TEXT_BYTES
                    || entry.label.contains('\0')
            })
        {
            return Err(SceneError::Limit);
        }
        Ok(())
    }
    pub fn from_input(bytes: &[u8], style_count: usize) -> Result<Option<Self>, SceneError> {
        Self::parse(bytes, style_count, true)
    }

    fn from_canonical(bytes: &[u8], style_count: usize) -> Result<Option<Self>, SceneError> {
        Self::parse(bytes, style_count, false)
    }

    fn parse(
        bytes: &[u8],
        style_count: usize,
        resolve_defaults: bool,
    ) -> Result<Option<Self>, SceneError> {
        if bytes.is_empty() {
            return Ok(None);
        }
        if bytes.len() < SCENE_LEGEND_HEADER_BYTES || &bytes[..4] != b"XYLG" {
            return Err(SceneError::Length);
        }
        let u32_at = |offset| u32::from_le_bytes(bytes[offset..offset + 4].try_into().unwrap());
        let f64_at = |offset| f64::from_le_bytes(bytes[offset..offset + 8].try_into().unwrap());
        let authored = bytes[5];
        if bytes[6..8] != [0; 2]
            || bytes[44..48] != [0; 4]
            || (!resolve_defaults && authored != 0)
            || (resolve_defaults && authored & !0x3f != 0)
        {
            return Err(SceneError::Length);
        }
        let location = if !resolve_defaults || authored & 1 != 0 {
            LegendLocation::from_code(bytes[4])?
        } else if bytes[4] == 0 {
            LegendLocation::UpperRight
        } else {
            return Err(SceneError::Length);
        };
        let count = u32_at(8) as usize;
        let title_len = u32_at(12) as usize;
        let input_font_size = f64_at(16);
        let font_size = if !resolve_defaults || authored & 2 != 0 {
            input_font_size
        } else if input_font_size == 0.0 {
            11.0
        } else {
            return Err(SceneError::Length);
        };
        let input_title_font_size = f64_at(24);
        let title_font_size = if !resolve_defaults || authored & 4 != 0 {
            input_title_font_size
        } else if input_title_font_size == 0.0 {
            font_size
        } else {
            return Err(SceneError::Length);
        };
        if count == 0
            || count > MAX_SCENE_LEGEND_ENTRIES
            || title_len > MAX_SCENE_TEXT_BYTES
            || !font_size.is_finite()
            || !(1.0..=MAX_SCENE_CHROME_LENGTH).contains(&font_size)
            || !title_font_size.is_finite()
            || !(1.0..=MAX_SCENE_CHROME_LENGTH).contains(&title_font_size)
        {
            return Err(SceneError::Limit);
        }
        let table_end = SCENE_LEGEND_HEADER_BYTES
            .checked_add(
                count
                    .checked_mul(SCENE_LEGEND_ENTRY_BYTES)
                    .ok_or(SceneError::Limit)?,
            )
            .ok_or(SceneError::Limit)?;
        if table_end > bytes.len() {
            return Err(SceneError::Length);
        }
        let text = bytes.get(table_end..).ok_or(SceneError::Length)?;
        if text.len() > MAX_SCENE_LEGEND_TEXT_BYTES || text.contains(&0) {
            return Err(SceneError::Limit);
        }
        let title = String::from_utf8(text.get(..title_len).ok_or(SceneError::Length)?.to_vec())
            .map_err(|_| SceneError::Length)?;
        let mut expected = title_len;
        let mut entries = Vec::with_capacity(count);
        for index in 0..count {
            let offset = SCENE_LEGEND_HEADER_BYTES + index * SCENE_LEGEND_ENTRY_BYTES;
            let style_ref = u32_at(offset) as usize;
            let kind = SceneRecordKind::from_code(bytes[offset + 4])?;
            let symbol = bytes[offset + 5];
            if bytes[offset + 6..offset + 8] != [0; 2]
                || style_ref >= style_count
                || (kind == SceneRecordKind::Scatter && symbol > ScatterSymbol::VerticalLine as u8)
                || (kind != SceneRecordKind::Scatter && symbol != 0)
            {
                return Err(SceneError::Length);
            }
            let label_offset = u32_at(offset + 8) as usize;
            let label_len = u32_at(offset + 12) as usize;
            if label_offset != expected || label_len == 0 || label_len > MAX_SCENE_TEXT_BYTES {
                return Err(SceneError::Length);
            }
            let end = label_offset
                .checked_add(label_len)
                .ok_or(SceneError::Limit)?;
            let label = String::from_utf8(
                text.get(label_offset..end)
                    .ok_or(SceneError::Length)?
                    .to_vec(),
            )
            .map_err(|_| SceneError::Length)?;
            expected = end;
            entries.push(SceneLegendEntry {
                style_ref,
                kind,
                symbol,
                fill_rgba: bytes[offset + 16..offset + 20].try_into().unwrap(),
                stroke_rgba: bytes[offset + 20..offset + 24].try_into().unwrap(),
                label,
            });
        }
        if expected != text.len() {
            return Err(SceneError::Length);
        }
        let resolved_paint = |range: std::ops::Range<usize>, bit, default| {
            let value: [u8; 4] = bytes[range].try_into().unwrap();
            if !resolve_defaults || authored & bit != 0 {
                Ok(value)
            } else if value == [0; 4] {
                Ok(default)
            } else {
                Err(SceneError::Length)
            }
        };
        Ok(Some(Self {
            location,
            title,
            font_size,
            title_font_size,
            text_rgba: resolved_paint(32..36, 8, [32, 32, 32, 255])?,
            frame_fill_rgba: resolved_paint(36..40, 16, [255, 255, 255, 230])?,
            frame_stroke_rgba: resolved_paint(40..44, 32, [32, 32, 32, 71])?,
            entries,
        }))
    }

    fn encode(&self) -> Vec<u8> {
        let mut out =
            vec![0; SCENE_LEGEND_HEADER_BYTES + self.entries.len() * SCENE_LEGEND_ENTRY_BYTES];
        out[..4].copy_from_slice(b"XYLG");
        out[4] = self.location as u8;
        out[8..12].copy_from_slice(&(self.entries.len() as u32).to_le_bytes());
        out[12..16].copy_from_slice(&(self.title.len() as u32).to_le_bytes());
        out[16..24].copy_from_slice(&self.font_size.to_le_bytes());
        out[24..32].copy_from_slice(&self.title_font_size.to_le_bytes());
        out[32..36].copy_from_slice(&self.text_rgba);
        out[36..40].copy_from_slice(&self.frame_fill_rgba);
        out[40..44].copy_from_slice(&self.frame_stroke_rgba);
        let mut text_offset = self.title.len();
        out.extend_from_slice(self.title.as_bytes());
        for (index, entry) in self.entries.iter().enumerate() {
            let offset = SCENE_LEGEND_HEADER_BYTES + index * SCENE_LEGEND_ENTRY_BYTES;
            out[offset..offset + 4].copy_from_slice(&(entry.style_ref as u32).to_le_bytes());
            out[offset + 4] = entry.kind as u8;
            out[offset + 5] = entry.symbol;
            out[offset + 8..offset + 12].copy_from_slice(&(text_offset as u32).to_le_bytes());
            out[offset + 12..offset + 16]
                .copy_from_slice(&(entry.label.len() as u32).to_le_bytes());
            out[offset + 16..offset + 20].copy_from_slice(&entry.fill_rgba);
            out[offset + 20..offset + 24].copy_from_slice(&entry.stroke_rgba);
            out.extend_from_slice(entry.label.as_bytes());
            text_offset += entry.label.len();
        }
        out
    }
}

const SCENE_COLORBAR_HEADER_BYTES: usize = 56;
const SCENE_COLORBAR_STOP_BYTES: usize = 12;
pub const MAX_SCENE_COLORBAR_INPUT_BYTES: usize = SCENE_COLORBAR_HEADER_BYTES
    + MAX_SCENE_COLORBAR_STOPS * SCENE_COLORBAR_STOP_BYTES
    + MAX_SCENE_COLORBAR_TEXT_BYTES;

/// A bounded, host-neutral banded colour scale. The author supplies only
/// literal RGBA stops, a bounded title, and a right/bottom side; the record
/// has no tick, label, minor-tick, or continuous-gradient semantics.
#[derive(Clone, Debug, PartialEq)]
pub struct SceneColorbar {
    pub horizontal: bool,
    pub domain: [f64; 2],
    pub stops: Vec<(f64, [u8; 4])>,
    pub title: String,
    pub text_rgba: [u8; 4],
}

impl SceneColorbar {
    pub fn from_input(bytes: &[u8]) -> Result<Option<Self>, SceneError> {
        if bytes.is_empty() {
            return Ok(None);
        }
        if bytes.len() < SCENE_COLORBAR_HEADER_BYTES
            || &bytes[..4] != b"XYCB"
            || u32::from_le_bytes(bytes[4..8].try_into().unwrap()) != 1
            || bytes[9..12] != [0; 3]
            || bytes[52..56] != [0; 4]
        {
            return Err(SceneError::Length);
        }
        let flags = bytes[8];
        if flags & !0x03 != 0 || flags & 2 == 0 {
            return Err(SceneError::Length);
        }
        let stop_count = u32::from_le_bytes(bytes[12..16].try_into().unwrap()) as usize;
        let tick_count = u32::from_le_bytes(bytes[16..20].try_into().unwrap()) as usize;
        let title_len = u32::from_le_bytes(bytes[20..24].try_into().unwrap()) as usize;
        if !(2..=MAX_SCENE_COLORBAR_STOPS).contains(&stop_count)
            || tick_count != 0
            || title_len > MAX_SCENE_COLORBAR_TEXT_BYTES
        {
            return Err(SceneError::Limit);
        }
        let f64_at = |offset| f64::from_le_bytes(bytes[offset..offset + 8].try_into().unwrap());
        let domain = [f64_at(24), f64_at(32)];
        if !domain[0].is_finite() || !domain[1].is_finite() || domain[0] >= domain[1] {
            return Err(SceneError::NonFinite);
        }
        let table_end = SCENE_COLORBAR_HEADER_BYTES
            .checked_add(
                stop_count
                    .checked_mul(SCENE_COLORBAR_STOP_BYTES)
                    .ok_or(SceneError::Limit)?,
            )
            .ok_or(SceneError::Limit)?;
        let ticks_end = table_end
            .checked_add(tick_count.checked_mul(8).ok_or(SceneError::Limit)?)
            .ok_or(SceneError::Limit)?;
        let end = ticks_end.checked_add(title_len).ok_or(SceneError::Limit)?;
        if end != bytes.len() {
            return Err(SceneError::Length);
        }
        let mut stops = Vec::with_capacity(stop_count);
        let mut previous = f64::NEG_INFINITY;
        for index in 0..stop_count {
            let at = SCENE_COLORBAR_HEADER_BYTES + index * SCENE_COLORBAR_STOP_BYTES;
            let value = f64_at(at);
            if !value.is_finite() || value < domain[0] || value > domain[1] || value <= previous {
                return Err(SceneError::Length);
            }
            previous = value;
            stops.push((value, bytes[at + 8..at + 12].try_into().unwrap()));
        }
        if stops.first().unwrap().0 != domain[0] || stops.last().unwrap().0 != domain[1] {
            return Err(SceneError::Length);
        }
        let title = std::str::from_utf8(&bytes[ticks_end..end])
            .map_err(|_| SceneError::Length)?
            .to_owned();
        if title.contains('\0') {
            return Err(SceneError::Length);
        }
        Ok(Some(Self {
            horizontal: flags & 1 != 0,
            domain,
            stops,
            title,
            text_rgba: bytes[40..44].try_into().unwrap(),
        }))
    }

    fn encode(&self) -> Result<Vec<u8>, SceneError> {
        let mut out = Vec::with_capacity(
            SCENE_COLORBAR_HEADER_BYTES
                + self.stops.len() * SCENE_COLORBAR_STOP_BYTES
                + self.title.len(),
        );
        out.extend_from_slice(b"XYCB");
        out.extend_from_slice(&1u32.to_le_bytes());
        out.push(u8::from(self.horizontal) | 2);
        out.extend_from_slice(&[0; 3]);
        out.extend_from_slice(&(self.stops.len() as u32).to_le_bytes());
        out.extend_from_slice(&0u32.to_le_bytes());
        out.extend_from_slice(&(self.title.len() as u32).to_le_bytes());
        for value in self.domain {
            out.extend_from_slice(&value.to_le_bytes());
        }
        out.extend_from_slice(&self.text_rgba);
        out.extend_from_slice(&[0; 12]);
        for (value, rgba) in &self.stops {
            out.extend_from_slice(&value.to_le_bytes());
            out.extend_from_slice(rgba);
        }
        out.extend_from_slice(self.title.as_bytes());
        // Reuse the strict decoder as the single validation authority.
        Self::from_input(&out)?;
        Ok(out)
    }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
#[repr(u8)]
pub enum AxisSide {
    Low = 0,
    High = 1,
}

impl AxisSide {
    fn from_code(value: u8) -> Result<Self, SceneError> {
        match value {
            0 => Ok(Self::Low),
            1 => Ok(Self::High),
            _ => Err(SceneError::Length),
        }
    }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
#[repr(u8)]
pub enum TickDirection {
    Out = 0,
    In = 1,
    InOut = 2,
}

impl TickDirection {
    fn from_code(value: u8) -> Result<Self, SceneError> {
        match value {
            0 => Ok(Self::Out),
            1 => Ok(Self::In),
            2 => Ok(Self::InOut),
            _ => Err(SceneError::Length),
        }
    }
}

#[derive(Clone, Copy, Debug, PartialEq)]
pub struct SceneAxisChromeStyle {
    pub side: AxisSide,
    /// Bit 0 is the low side (bottom/left), bit 1 the high side (top/right).
    pub tick_sides: u8,
    pub tick_label_sides: u8,
    pub major_direction: TickDirection,
    pub minor_direction: TickDirection,
    pub axis_rgba: [u8; 4],
    pub grid_rgba: [u8; 4],
    pub tick_rgba: [u8; 4],
    pub minor_grid_rgba: [u8; 4],
    pub minor_tick_rgba: [u8; 4],
    pub label_rgba: [u8; 4],
    pub axis_width: f64,
    pub grid_width: f64,
    pub tick_width: f64,
    pub tick_length: f64,
    pub minor_grid_width: f64,
    pub minor_tick_width: f64,
    pub minor_tick_length: f64,
}

impl SceneAxisChromeStyle {
    #[inline]
    fn visible_stroke(rgba: [u8; 4], width: f64) -> bool {
        rgba[3] != 0 && width > 0.0
    }

    fn has_visible_grid(self) -> bool {
        Self::visible_stroke(self.grid_rgba, self.grid_width)
            || Self::visible_stroke(self.minor_grid_rgba, self.minor_grid_width)
    }

    fn has_visible_axis(self) -> bool {
        Self::visible_stroke(self.axis_rgba, self.axis_width)
            || (self.tick_sides != 0
                && self.tick_length > 0.0
                && Self::visible_stroke(self.tick_rgba, self.tick_width))
            || (self.minor_tick_length > 0.0
                && Self::visible_stroke(self.minor_tick_rgba, self.minor_tick_width))
            || (self.tick_label_sides != 0 && self.label_rgba[3] != 0)
    }

    fn default_style(side: AxisSide) -> Self {
        Self {
            side,
            tick_sides: 1 << side as u8,
            tick_label_sides: 1 << side as u8,
            major_direction: TickDirection::Out,
            minor_direction: TickDirection::Out,
            axis_rgba: [32, 32, 32, 140],
            grid_rgba: [32, 32, 32, 36],
            tick_rgba: [32, 32, 32, 140],
            minor_grid_rgba: [0; 4],
            minor_tick_rgba: [32, 32, 32, 140],
            label_rgba: [32, 32, 32, 217],
            axis_width: 1.0,
            grid_width: 1.0,
            tick_width: 1.0,
            tick_length: 4.0,
            minor_grid_width: 1.0,
            minor_tick_width: 1.0,
            minor_tick_length: 0.0,
        }
    }

    fn validated(self) -> Result<Self, SceneError> {
        if self.tick_sides & !0b11 != 0 || self.tick_label_sides & !0b11 != 0 {
            return Err(SceneError::Length);
        }
        if [
            self.axis_width,
            self.grid_width,
            self.tick_width,
            self.tick_length,
            self.minor_grid_width,
            self.minor_tick_width,
            self.minor_tick_length,
        ]
        .into_iter()
        .any(|value| !value.is_finite() || !(0.0..=MAX_SCENE_CHROME_LENGTH).contains(&value))
        {
            return Err(SceneError::NonFinite);
        }
        Ok(self)
    }
}

/// Authored Cartesian backgrounds, axis sides, and major/minor chrome.
#[derive(Clone, Debug, PartialEq)]
pub struct SceneChromeStyle {
    pub chart_background_rgba: [u8; 4],
    pub plot_background_rgba: [u8; 4],
    pub label_rgba: [u8; 4],
    pub label_font_size: f64,
    pub x_axis: SceneAxisChromeStyle,
    pub y_axis: SceneAxisChromeStyle,
    /// `None` requests Rust's bounded automatic major ticks; `Some` is authored.
    pub x_major_ticks: Option<Vec<f64>>,
    pub x_minor_ticks: Vec<f64>,
    pub y_major_ticks: Option<Vec<f64>>,
    pub y_minor_ticks: Vec<f64>,
    /// Exact UTF-8 labels for authored major positions. `None` retains Rust's
    /// deterministic numeric formatter; strings are never a host paint policy.
    pub x_tick_labels: Option<Vec<String>>,
    pub y_tick_labels: Option<Vec<String>>,
}

impl SceneChromeStyle {
    pub fn default_style() -> Self {
        Self {
            chart_background_rgba: [0; 4],
            plot_background_rgba: [0; 4],
            label_rgba: [32, 32, 32, 217], // ≈ 0.85
            label_font_size: 12.0,
            x_axis: SceneAxisChromeStyle::default_style(AxisSide::Low),
            y_axis: SceneAxisChromeStyle::default_style(AxisSide::Low),
            x_major_ticks: None,
            x_minor_ticks: Vec::new(),
            y_major_ticks: None,
            y_minor_ticks: Vec::new(),
            x_tick_labels: None,
            y_tick_labels: None,
        }
    }

    pub fn validated(self) -> Result<Self, SceneError> {
        if !self.label_font_size.is_finite()
            || self.label_font_size <= 0.0
            || self.label_font_size > MAX_SCENE_CHROME_LENGTH
        {
            return Err(SceneError::NonFinite);
        }
        self.x_axis.validated()?;
        self.y_axis.validated()?;
        for values in [
            self.x_major_ticks.as_deref().unwrap_or(&[]),
            &self.x_minor_ticks,
            self.y_major_ticks.as_deref().unwrap_or(&[]),
            &self.y_minor_ticks,
        ] {
            if values.len() > MAX_AXIS_TICKS || values.iter().any(|value| !value.is_finite()) {
                return Err(SceneError::Limit);
            }
        }
        for values in [self.x_major_ticks.as_deref(), self.y_major_ticks.as_deref()]
            .into_iter()
            .flatten()
        {
            for (index, value) in values.iter().enumerate() {
                if values[..index].contains(value) {
                    return Err(SceneError::Length);
                }
            }
        }
        for (ticks, labels) in [
            (self.x_major_ticks.as_deref(), self.x_tick_labels.as_deref()),
            (self.y_major_ticks.as_deref(), self.y_tick_labels.as_deref()),
        ] {
            if let Some(labels) = labels {
                let Some(ticks) = ticks else {
                    return Err(SceneError::Length);
                };
                if labels.len() != ticks.len()
                    || labels.len() > MAX_AXIS_TICKS
                    || labels.iter().any(|label| {
                        label.is_empty()
                            || label.contains('\0')
                            || label.len() > MAX_SCENE_TEXT_BYTES
                    })
                    || labels.iter().map(String::len).sum::<usize>() > MAX_SCENE_TEXT_BYTES
                {
                    return Err(SceneError::Limit);
                }
            }
        }
        Ok(self)
    }

    pub fn from_style_input(
        bytes: &[u8],
        x_major_ticks: Option<Vec<f64>>,
        x_minor_ticks: Vec<f64>,
        y_major_ticks: Option<Vec<f64>>,
        y_minor_ticks: Vec<f64>,
    ) -> Result<Self, SceneError> {
        if bytes.len() != SCENE_CHROME_STYLE_INPUT_BYTES || bytes[12..16] != [0; 4] {
            return Err(SceneError::Length);
        }
        let label_font_size = f64::from_le_bytes(bytes[16..24].try_into().unwrap());
        Self {
            chart_background_rgba: bytes[0..4].try_into().unwrap(),
            plot_background_rgba: bytes[4..8].try_into().unwrap(),
            label_rgba: bytes[8..12].try_into().unwrap(),
            label_font_size,
            x_axis: read_axis_chrome_style(bytes, 24)?,
            y_axis: read_axis_chrome_style(bytes, 112)?,
            x_major_ticks,
            x_minor_ticks,
            y_major_ticks,
            y_minor_ticks,
            x_tick_labels: None,
            y_tick_labels: None,
        }
        .validated()
    }

    pub fn style_input(&self) -> Vec<u8> {
        let mut out = Vec::with_capacity(SCENE_CHROME_STYLE_INPUT_BYTES);
        write_chrome_style_input(&mut out, self);
        out
    }
}

impl Default for SceneChromeStyle {
    fn default() -> Self {
        Self::default_style()
    }
}

/// Optional figure title and axis labels owned by the Scene v9 trailer.
#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub struct SceneChromeText {
    pub title: String,
    pub x_label: String,
    pub y_label: String,
}

impl SceneChromeText {
    pub fn from_parts(title: &str, x_label: &str, y_label: &str) -> Result<Self, SceneError> {
        for value in [title, x_label, y_label] {
            if value.len() > MAX_SCENE_TEXT_BYTES || value.contains('\0') {
                return Err(SceneError::Limit);
            }
        }
        Ok(Self {
            title: title.to_owned(),
            x_label: x_label.to_owned(),
            y_label: y_label.to_owned(),
        })
    }

    fn encoded_bytes(&self) -> usize {
        SCENE_CHROME_TRAILER_BYTES + self.title.len() + self.x_label.len() + self.y_label.len()
    }
}

fn read_axis_chrome_style(bytes: &[u8], offset: usize) -> Result<SceneAxisChromeStyle, SceneError> {
    let axis = bytes.get(offset..offset + 88).ok_or(SceneError::Length)?;
    if axis[5..8] != [0; 3] {
        return Err(SceneError::Length);
    }
    let f64_at = |inner| f64::from_le_bytes(axis[inner..inner + 8].try_into().unwrap());
    SceneAxisChromeStyle {
        side: AxisSide::from_code(axis[0])?,
        tick_sides: axis[1],
        tick_label_sides: axis[2],
        major_direction: TickDirection::from_code(axis[3])?,
        minor_direction: TickDirection::from_code(axis[4])?,
        axis_rgba: axis[8..12].try_into().unwrap(),
        grid_rgba: axis[12..16].try_into().unwrap(),
        tick_rgba: axis[16..20].try_into().unwrap(),
        minor_grid_rgba: axis[20..24].try_into().unwrap(),
        minor_tick_rgba: axis[24..28].try_into().unwrap(),
        label_rgba: axis[28..32].try_into().unwrap(),
        axis_width: f64_at(32),
        grid_width: f64_at(40),
        tick_width: f64_at(48),
        tick_length: f64_at(56),
        minor_grid_width: f64_at(64),
        minor_tick_width: f64_at(72),
        minor_tick_length: f64_at(80),
    }
    .validated()
}

#[derive(Clone, Debug, PartialEq)]
pub struct AxisTicks {
    pub ticks: Vec<f64>,
    pub labeled: Vec<f64>,
    pub step: f64,
}

fn push_raster_f32(out: &mut Vec<u8>, value: f64, scale: f64) -> Result<(), SceneError> {
    let scaled = value * scale;
    if !scaled.is_finite() {
        return Err(SceneError::NonFinite);
    }
    let narrowed = scaled as f32;
    if !narrowed.is_finite() {
        return Err(SceneError::NonFinite);
    }
    out.extend_from_slice(&narrowed.to_le_bytes());
    Ok(())
}

fn checked_f32(value: f64) -> Result<f32, SceneError> {
    let value = value as f32;
    value
        .is_finite()
        .then_some(value)
        .ok_or(SceneError::NonFinite)
}

fn push_raster_stroke(
    out: &mut Vec<u8>,
    points: [(f64, f64); 2],
    width: f64,
    rgba: [u8; 4],
    scale: f64,
) -> Result<(), SceneError> {
    out.push(3);
    out.extend_from_slice(&2u32.to_le_bytes());
    for (x, y) in points {
        push_raster_f32(out, x, scale)?;
        push_raster_f32(out, y, scale)?;
    }
    push_raster_f32(out, width, scale)?;
    out.extend_from_slice(&rgba);
    out.push(0);
    out.extend_from_slice(&0u32.to_le_bytes());
    out.push(1);
    Ok(())
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum ScaleKind {
    Linear,
    Log,
    SymLog,
}

#[derive(Clone, Copy, Debug)]
pub struct AxisScale {
    kind: ScaleKind,
    px0: f64,
    coord_lo: f64,
    coord_span: f64,
    px_delta: f64,
    constant: f64,
    mask_nonpositive: bool,
}

impl AxisScale {
    pub fn new(
        kind: ScaleKind,
        lo: f64,
        hi: f64,
        px0: f64,
        px1: f64,
        constant: f64,
        mask_nonpositive: bool,
    ) -> Result<Self, SceneError> {
        if [lo, hi, px0, px1, constant]
            .iter()
            .any(|value| !value.is_finite())
            || constant <= 0.0
        {
            return Err(SceneError::NonFinite);
        }
        let mut scale = Self {
            kind,
            px0,
            coord_lo: 0.0,
            coord_span: 1.0,
            px_delta: px1 - px0,
            constant,
            mask_nonpositive,
        };
        let coord_lo = scale.coord(lo);
        let coord_hi = scale.coord(hi);
        if !coord_lo.is_finite() || !coord_hi.is_finite() {
            return Err(SceneError::NonFinite);
        }
        scale.coord_lo = coord_lo;
        scale.coord_span = if coord_hi == coord_lo {
            1.0
        } else {
            coord_hi - coord_lo
        };
        Ok(scale)
    }

    #[inline(always)]
    pub fn coord(self, value: f64) -> f64 {
        if value.is_nan() {
            return f64::NAN;
        }
        match self.kind {
            ScaleKind::Linear => value,
            ScaleKind::Log if value > 0.0 => value.log10(),
            ScaleKind::Log if self.mask_nonpositive => f64::NAN,
            ScaleKind::Log => 1e-300_f64.log10(),
            ScaleKind::SymLog => value.signum() * (value.abs() / self.constant).ln_1p(),
        }
    }

    pub fn value(self, coord: f64) -> f64 {
        match self.kind {
            ScaleKind::Linear => coord,
            ScaleKind::Log => 10_f64.powf(coord),
            ScaleKind::SymLog => coord.signum() * self.constant * coord.abs().exp_m1(),
        }
    }

    fn domain(self) -> (f64, f64) {
        (
            self.value(self.coord_lo),
            self.value(self.coord_lo + self.coord_span),
        )
    }

    fn ticks(self, length_px: f64, is_x: bool) -> Result<AxisTicks, SceneError> {
        let (lo, hi) = self.domain();
        let divisor = if is_x { 80.0 } else { 45.0 };
        let target = ((length_px / divisor) as usize).clamp(3, MAX_AXIS_TICKS);
        match self.kind {
            ScaleKind::Log => log_ticks(lo, hi, target),
            ScaleKind::Linear => linear_ticks(lo, hi, target),
            ScaleKind::SymLog => {
                let coordinates = linear_ticks(self.coord(lo), self.coord(hi), target)?;
                let mut ticks: Vec<f64> = coordinates
                    .ticks
                    .iter()
                    .map(|coordinate| self.value(*coordinate))
                    .collect();
                if lo.min(hi) <= 0.0
                    && lo.max(hi) >= 0.0
                    && !ticks.iter().any(|value| value.abs() < 1e-12)
                {
                    ticks.push(0.0);
                    ticks.sort_by(|a, b| {
                        if lo > hi {
                            b.total_cmp(a)
                        } else {
                            a.total_cmp(b)
                        }
                    });
                }
                Ok(AxisTicks {
                    labeled: ticks.clone(),
                    ticks,
                    step: self.value(coordinates.step).abs(),
                })
            }
        }
    }

    #[inline(always)]
    pub fn pixel(self, value: f64) -> f64 {
        self.px0 + (self.coord(value) - self.coord_lo) / self.coord_span * self.px_delta
    }
}

fn resolved_axis_ticks(
    scale: AxisScale,
    length: f64,
    is_x: bool,
    pixel_min: f64,
    pixel_max: f64,
    authored_major: Option<&[f64]>,
    authored_minor: &[f64],
) -> Result<AxisTicks, SceneError> {
    let automatic = scale.ticks(length, is_x)?;
    let mut labeled = authored_major
        .map(ToOwned::to_owned)
        .unwrap_or_else(|| automatic.labeled.clone());
    let in_plot = |value: &f64| {
        let pixel = scale.pixel(*value);
        pixel.is_finite() && pixel >= pixel_min && pixel <= pixel_max
    };
    labeled.retain(in_plot);
    let mut ticks = labeled.clone();
    let minor = if authored_minor.is_empty() && authored_major.is_none() {
        automatic
            .ticks
            .into_iter()
            .filter(|value| !automatic.labeled.contains(value))
            .collect::<Vec<_>>()
    } else {
        authored_minor.to_vec()
    };
    ticks.extend(minor.into_iter().filter(in_plot));
    if ticks.len() > MAX_AXIS_TICKS {
        return Err(SceneError::Limit);
    }
    let step = labeled
        .windows(2)
        .next()
        .map(|pair| (pair[1] - pair[0]).abs())
        .filter(|step| step.is_finite() && *step > 0.0)
        .unwrap_or(automatic.step);
    Ok(AxisTicks {
        ticks,
        labeled,
        step,
    })
}

pub fn linear_ticks(lo: f64, hi: f64, target: usize) -> Result<AxisTicks, SceneError> {
    if !lo.is_finite() || !hi.is_finite() || target == 0 || target > MAX_AXIS_TICKS {
        return Err(SceneError::NonFinite);
    }
    let (a, b) = if lo <= hi { (lo, hi) } else { (hi, lo) };
    if a == b {
        return Ok(AxisTicks {
            ticks: vec![a],
            labeled: vec![a],
            step: 1.0,
        });
    }
    let rough = (b - a) / target as f64;
    let magnitude = 10_f64.powf(rough.abs().log10().floor());
    let step = [1.0, 2.0, 2.5, 5.0, 10.0]
        .into_iter()
        .map(|m| m * magnitude)
        .find(|candidate| rough <= candidate * (1.0 + 1e-12))
        .unwrap_or(10.0 * magnitude);
    let mut value = (a / step).ceil() * step;
    let mut ticks = Vec::with_capacity(target.saturating_add(2).min(MAX_AXIS_TICKS));
    while value <= b + step * 1e-9 && ticks.len() < MAX_AXIS_TICKS {
        ticks.push(if value.abs() < step * 1e-9 {
            0.0
        } else {
            value
        });
        value += step;
    }
    Ok(AxisTicks {
        labeled: ticks.clone(),
        ticks,
        step,
    })
}

pub fn log_ticks(lo: f64, hi: f64, target: usize) -> Result<AxisTicks, SceneError> {
    if !lo.is_finite()
        || !hi.is_finite()
        || lo <= 0.0
        || hi <= 0.0
        || target == 0
        || target > MAX_AXIS_TICKS
    {
        return Err(SceneError::NonFinite);
    }
    let (a, b) = if lo <= hi { (lo, hi) } else { (hi, lo) };
    let e0 = a.log10().floor() as i32;
    let e1 = b.log10().ceil() as i32;
    let multipliers: &[f64] = if (e1 - e0).max(1) <= (target as i32).max(2) {
        &[1.0, 2.0, 5.0]
    } else {
        &[1.0]
    };
    let label_every = (((e1 - e0 + 1) as f64 / target as f64).ceil() as i32).max(1);
    let mut ticks = Vec::new();
    let mut labeled = Vec::new();
    'outer: for exponent in e0..=e1 {
        let base = 10_f64.powi(exponent);
        for multiplier in multipliers {
            let value = multiplier * base;
            if value >= a * (1.0 - 1e-12) && value <= b * (1.0 + 1e-12) {
                ticks.push(value);
                if *multiplier == 1.0 && (exponent - e0) % label_every == 0 {
                    labeled.push(value);
                }
            }
            if ticks.len() >= MAX_AXIS_TICKS {
                break 'outer;
            }
        }
    }
    if labeled.is_empty() {
        labeled.clone_from(&ticks);
    }
    Ok(AxisTicks {
        ticks,
        labeled,
        step: 1.0,
    })
}

/// Category-index ticks for discrete axes. `n_categories` is the category count;
/// `lo`/`hi` are the visible domain in index space.
pub fn category_ticks(
    lo: f64,
    hi: f64,
    n_categories: usize,
    target: usize,
) -> Result<AxisTicks, SceneError> {
    if !lo.is_finite()
        || !hi.is_finite()
        || n_categories == 0
        || target == 0
        || target > MAX_AXIS_TICKS
    {
        return Err(SceneError::NonFinite);
    }
    let start = lo.min(hi).ceil().max(0.0) as isize;
    let stop = lo.max(hi).floor().min((n_categories - 1) as f64) as isize;
    if stop < start {
        return Ok(AxisTicks {
            ticks: Vec::new(),
            labeled: Vec::new(),
            step: 1.0,
        });
    }
    let visible = (stop - start + 1) as usize;
    let step = ((visible as f64 / target as f64).ceil() as usize).max(1);
    let mut ticks = Vec::with_capacity(((visible / step) + 1).min(MAX_AXIS_TICKS));
    let mut value = start;
    while value <= stop && ticks.len() < MAX_AXIS_TICKS {
        ticks.push(value as f64);
        value += step as isize;
    }
    Ok(AxisTicks {
        labeled: ticks.clone(),
        ticks,
        step: step as f64,
    })
}

const DEGREE_STEPS: &[f64] = &[
    1.0, 2.0, 5.0, 10.0, 15.0, 30.0, 45.0, 60.0, 90.0, 120.0, 180.0, 360.0,
];
const RADIAN_STEPS: &[f64] = &[
    std::f64::consts::PI / 12.0,
    std::f64::consts::PI / 8.0,
    std::f64::consts::PI / 6.0,
    std::f64::consts::PI / 4.0,
    std::f64::consts::PI / 3.0,
    std::f64::consts::PI / 2.0,
    2.0 * std::f64::consts::PI / 3.0,
    std::f64::consts::PI,
    2.0 * std::f64::consts::PI,
];

/// Angular ticks on a human-readable degree or radian ladder.
pub fn angular_ticks(
    lo: f64,
    hi: f64,
    degrees: bool,
    target: usize,
) -> Result<AxisTicks, SceneError> {
    if !lo.is_finite() || !hi.is_finite() || target == 0 || target > MAX_AXIS_TICKS {
        return Err(SceneError::NonFinite);
    }
    let (a, b) = if lo <= hi { (lo, hi) } else { (hi, lo) };
    if a == b {
        return Ok(AxisTicks {
            ticks: vec![a],
            labeled: vec![a],
            step: 1.0,
        });
    }
    let ladder = if degrees { DEGREE_STEPS } else { RADIAN_STEPS };
    let rough = (b - a) / target as f64;
    let step = ladder
        .iter()
        .copied()
        .find(|candidate| *candidate >= rough * (1.0 - 1e-12))
        .unwrap_or(*ladder.last().unwrap());
    let mut value = (a / step).ceil() * step;
    let mut ticks = Vec::with_capacity(target.saturating_add(2).min(MAX_AXIS_TICKS));
    while value <= b + step * 1e-9 && ticks.len() < MAX_AXIS_TICKS {
        ticks.push(if value.abs() < step * 1e-9 {
            0.0
        } else {
            value
        });
        value += step;
    }
    let turn = if degrees {
        360.0
    } else {
        2.0 * std::f64::consts::PI
    };
    if ticks.len() > 1 && (ticks[ticks.len() - 1] - ticks[0] - turn).abs() < step * 1e-9 {
        ticks.pop();
    }
    Ok(AxisTicks {
        labeled: ticks.clone(),
        ticks,
        step,
    })
}

const MS_S: f64 = 1_000.0;
const MS_M: f64 = 60_000.0;
const MS_H: f64 = 3_600_000.0;
const MS_D: f64 = 86_400_000.0;
const MAX_TIME_TICKS: usize = 1_000;

const TIME_STEPS: &[f64] = &[
    1.0,
    2.0,
    5.0,
    10.0,
    20.0,
    50.0,
    100.0,
    200.0,
    500.0,
    MS_S,
    2.0 * MS_S,
    5.0 * MS_S,
    10.0 * MS_S,
    15.0 * MS_S,
    30.0 * MS_S,
    MS_M,
    2.0 * MS_M,
    5.0 * MS_M,
    10.0 * MS_M,
    15.0 * MS_M,
    30.0 * MS_M,
    MS_H,
    2.0 * MS_H,
    3.0 * MS_H,
    6.0 * MS_H,
    12.0 * MS_H,
    MS_D,
    2.0 * MS_D,
    7.0 * MS_D,
    14.0 * MS_D,
];

const MONTH_STEPS: &[i32] = &[1, 2, 3, 6, 12, 24, 60, 120];

/// UTC civil date from milliseconds since Unix epoch → (year, month0) with month0 in 0..=11.
fn utc_year_month0_from_ms(ms: f64) -> (i32, i32) {
    // Howard Hinnant civil_from_days.
    let z = (ms / MS_D).floor() as i64 + 719_468;
    let era = if z >= 0 { z } else { z - 146_096 } / 146_097;
    let doe = (z - era * 146_097) as u64;
    let yoe = (doe - doe / 1_460 + doe / 36_524 - doe / 146_096) / 365;
    let mut y = yoe as i64 + era * 400;
    let doy = doe - (365 * yoe + yoe / 4 - yoe / 100);
    let mp = (5 * doy + 2) / 153;
    let month = if mp < 10 { mp + 3 } else { mp - 9 }; // 1..=12
    if month <= 2 {
        y += 1;
    }
    (y as i32, month as i32 - 1)
}

/// First-of-month UTC milliseconds for year and month0 (0..=11).
fn utc_ms_from_year_month0(year: i32, month0: i32) -> f64 {
    // Howard Hinnant days_from_civil for day = 1.
    let mut y = i64::from(year);
    let m = i64::from(month0) + 1; // 1..=12
    if m <= 2 {
        y -= 1;
    }
    let era = if y >= 0 { y } else { y - 399 } / 400;
    let yoe = (y - era * 400) as u64;
    let doy = (153 * if m > 2 { m - 3 } else { m + 9 } + 2) as u64 / 5;
    let doe = yoe * 365 + yoe / 4 - yoe / 100 + doy;
    let days = era * 146_097 + doe as i64 - 719_468;
    days as f64 * MS_D
}

fn calendar_ticks(lo: f64, hi: f64, rough: f64) -> AxisTicks {
    let months_rough = rough / (30.0 * MS_D);
    let step_m = MONTH_STEPS
        .iter()
        .copied()
        .find(|candidate| f64::from(*candidate) >= months_rough)
        .unwrap_or(*MONTH_STEPS.last().unwrap());
    let (year, month0) = utc_year_month0_from_ms(lo);
    // Year-local month alignment matches Python `_calendar_ticks` and JS
    // `calendarTicks` (ceil month0 onto `step_m`, then walk `year + m/12`).
    let mut month_index =
        ((f64::from(month0) / f64::from(step_m)).ceil() as i64) * i64::from(step_m);
    let mut ticks = Vec::new();
    while ticks.len() <= MAX_TIME_TICKS {
        let t = utc_ms_from_year_month0(
            year + (month_index.div_euclid(12)) as i32,
            month_index.rem_euclid(12) as i32,
        );
        if t > hi {
            break;
        }
        if t >= lo {
            ticks.push(t);
        }
        month_index += i64::from(step_m);
    }
    AxisTicks {
        labeled: ticks.clone(),
        ticks,
        step: f64::from(step_m) * 30.0 * MS_D,
    }
}

/// Time-axis ticks in UTC milliseconds since Unix epoch.
///
/// Sub-fortnight spans use a fixed millisecond ladder; longer spans use
/// first-of-month calendar ticks (matching Python `_time_ticks` / JS `timeTicks`).
pub fn time_ticks(lo: f64, hi: f64, target: usize) -> Result<AxisTicks, SceneError> {
    if !lo.is_finite() || !hi.is_finite() || target == 0 || target > MAX_AXIS_TICKS {
        return Err(SceneError::NonFinite);
    }
    let (a, b) = if lo <= hi { (lo, hi) } else { (hi, lo) };
    let rough = (b - a) / target as f64;
    if rough > 14.0 * MS_D {
        return Ok(calendar_ticks(a, b, rough));
    }
    let step = TIME_STEPS
        .iter()
        .copied()
        .find(|candidate| *candidate >= rough)
        .unwrap_or(*TIME_STEPS.last().unwrap());
    let mut value = (a / step).ceil() * step;
    let mut ticks = Vec::with_capacity(target.saturating_add(2).min(MAX_AXIS_TICKS));
    while value <= b && ticks.len() < MAX_AXIS_TICKS {
        ticks.push(value);
        value += step;
    }
    Ok(AxisTicks {
        labeled: ticks.clone(),
        ticks,
        step,
    })
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
#[repr(u8)]
pub enum ScatterSymbol {
    Circle = 0,
    Square = 1,
    Diamond = 2,
    Triangle = 3,
    Cross = 4,
    Hexagon = 5,
    Pentagon = 6,
    Star = 7,
    TriangleDown = 8,
    TriangleLeft = 9,
    TriangleRight = 10,
    X = 11,
    Point = 12,
    Pixel = 13,
    ThinDiamond = 14,
    PlusLine = 15,
    XLine = 16,
    HorizontalLine = 17,
    VerticalLine = 18,
}

impl ScatterSymbol {
    fn from_code(value: u8) -> Self {
        match value {
            1 => Self::Square,
            2 => Self::Diamond,
            3 => Self::Triangle,
            4 => Self::Cross,
            5 => Self::Hexagon,
            6 => Self::Pentagon,
            7 => Self::Star,
            8 => Self::TriangleDown,
            9 => Self::TriangleLeft,
            10 => Self::TriangleRight,
            11 => Self::X,
            12 => Self::Point,
            13 => Self::Pixel,
            14 => Self::ThinDiamond,
            15 => Self::PlusLine,
            16 => Self::XLine,
            17 => Self::HorizontalLine,
            18 => Self::VerticalLine,
            _ => Self::Circle,
        }
    }

    fn is_line(self) -> bool {
        matches!(
            self,
            Self::PlusLine | Self::XLine | Self::HorizontalLine | Self::VerticalLine
        )
    }
}

#[derive(Clone, Copy, Debug, PartialEq)]
struct MarkerGeometry {
    radius: f64,
    stroke_width: f64,
    extent_x: f64,
    extent_y: f64,
}

impl MarkerGeometry {
    /// Canonical built-in marker geometry shared by Scene v1 SVG and v3
    /// clipping. `diameter` is the authored outer size. Line-only symbols get
    /// the historical implicit 1px stroke when the authored stroke is zero.
    #[inline(always)]
    fn new(symbol: ScatterSymbol, diameter: f64, authored_stroke: f64) -> Self {
        let stroke_width = if symbol.is_line() && authored_stroke <= 0.0 {
            1.0
        } else {
            authored_stroke
        };
        let radius = (diameter / 2.0 - stroke_width / 2.0).max(0.0);
        let (path_x, path_y) = match symbol {
            ScatterSymbol::Diamond => {
                let extent = std::f64::consts::SQRT_2 * radius;
                (extent, extent)
            }
            ScatterSymbol::ThinDiamond => (
                std::f64::consts::SQRT_2 * radius * 0.6,
                std::f64::consts::SQRT_2 * radius,
            ),
            ScatterSymbol::XLine => {
                let extent = 0.707 * radius;
                (extent, extent)
            }
            ScatterSymbol::HorizontalLine => (radius, 0.0),
            ScatterSymbol::VerticalLine => (0.0, radius),
            _ => (radius, radius),
        };
        let stroke_extent = stroke_width / 2.0;
        Self {
            radius,
            stroke_width,
            extent_x: path_x + stroke_extent,
            extent_y: path_y + stroke_extent,
        }
    }
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum SceneError {
    Length,
    Limit,
    PainterTraceLimit,
    NonFinite,
    NegativeSize,
    InvalidPaint,
    Version,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct SceneBatchSummary {
    pub records: usize,
    pub styles: usize,
}

fn batch_u32(bytes: &[u8], offset: usize) -> Result<u32, SceneError> {
    let raw = bytes
        .get(offset..offset + 4)
        .ok_or(SceneError::Length)?
        .try_into()
        .map_err(|_| SceneError::Length)?;
    Ok(u32::from_le_bytes(raw))
}

fn batch_u64(bytes: &[u8], offset: usize) -> Result<u64, SceneError> {
    let raw = bytes
        .get(offset..offset + 8)
        .ok_or(SceneError::Length)?
        .try_into()
        .map_err(|_| SceneError::Length)?;
    Ok(u64::from_le_bytes(raw))
}

fn batch_f64(bytes: &[u8], offset: usize) -> Result<f64, SceneError> {
    let raw = bytes
        .get(offset..offset + 8)
        .ok_or(SceneError::Length)?
        .try_into()
        .map_err(|_| SceneError::Length)?;
    Ok(f64::from_le_bytes(raw))
}

/// Bounded host framing for authored major labels.  The host only supplies
/// length-prefixed UTF-8; Rust validates and owns all use of the strings.
pub fn decode_tick_labels(bytes: &[u8]) -> Result<Option<Vec<String>>, SceneError> {
    if bytes.is_empty() {
        return Ok(None);
    }
    if bytes.len() < 12 || &bytes[..4] != b"XYTL" || batch_u32(bytes, 4)? != 1 {
        return Err(SceneError::Length);
    }
    let count = batch_u32(bytes, 8)? as usize;
    if count > MAX_AXIS_TICKS {
        return Err(SceneError::Limit);
    }
    let mut at = 12usize;
    let mut total = 0usize;
    let mut labels = Vec::with_capacity(count);
    for _ in 0..count {
        let length = batch_u32(bytes, at)? as usize;
        at = at.checked_add(4).ok_or(SceneError::Limit)?;
        let end = at.checked_add(length).ok_or(SceneError::Limit)?;
        let text = std::str::from_utf8(bytes.get(at..end).ok_or(SceneError::Length)?)
            .map_err(|_| SceneError::Length)?;
        total = total.checked_add(length).ok_or(SceneError::Limit)?;
        if text.is_empty()
            || text.contains('\0')
            || length > MAX_SCENE_TEXT_BYTES
            || total > MAX_SCENE_TEXT_BYTES
        {
            return Err(SceneError::Limit);
        }
        labels.push(text.to_owned());
        at = end;
    }
    if at != bytes.len() {
        return Err(SceneError::Length);
    }
    Ok(Some(labels))
}

pub fn encode_tick_labels(labels: Option<&[String]>) -> Result<Vec<u8>, SceneError> {
    let Some(labels) = labels else {
        return Ok(Vec::new());
    };
    if labels.len() > MAX_AXIS_TICKS {
        return Err(SceneError::Limit);
    }
    let total = labels.iter().try_fold(0usize, |sum, label| {
        sum.checked_add(label.len()).ok_or(SceneError::Limit)
    })?;
    if total > MAX_SCENE_TEXT_BYTES
        || labels.iter().any(|label| {
            label.is_empty() || label.contains('\0') || label.len() > MAX_SCENE_TEXT_BYTES
        })
    {
        return Err(SceneError::Limit);
    }
    let mut out = Vec::with_capacity(12 + labels.len() * 4 + total);
    out.extend_from_slice(b"XYTL");
    out.extend_from_slice(&1u32.to_le_bytes());
    out.extend_from_slice(&(labels.len() as u32).to_le_bytes());
    for label in labels {
        out.extend_from_slice(&(label.len() as u32).to_le_bytes());
        out.extend_from_slice(label.as_bytes());
    }
    Ok(out)
}

/// Decode bounded host-framed Cartesian text annotations and project them in
/// Rust. `XYAT` deliberately carries data coordinates, never host-resolved
/// pixels; the returned `SceneLabel`s are the canonical SVG/raster/painter
/// decoration shared by every consumer.
fn decode_xyat(
    bytes: &[u8],
    x_scale: AxisScale,
    y_scale: AxisScale,
    layout: PlotLayout,
) -> Result<Vec<SceneLabel>, SceneError> {
    if bytes.is_empty() {
        return Ok(Vec::new());
    }
    if bytes.len() < 12 || &bytes[..4] != b"XYAT" || batch_u32(bytes, 4)? != 1 {
        return Err(SceneError::Length);
    }
    let count = batch_u32(bytes, 8)? as usize;
    if count > MAX_AUTHORED_TEXT_ANNOTATIONS {
        return Err(SceneError::Limit);
    }
    let mut at = 12usize;
    let mut total = 0usize;
    let mut labels = Vec::with_capacity(count);
    for index in 0..count {
        let end_fixed = at.checked_add(24).ok_or(SceneError::Limit)?;
        let fixed = bytes.get(at..end_fixed).ok_or(SceneError::Length)?;
        let x = f64::from_le_bytes(fixed[0..8].try_into().unwrap());
        let y = f64::from_le_bytes(fixed[8..16].try_into().unwrap());
        let len = u32::from_le_bytes(fixed[20..24].try_into().unwrap()) as usize;
        let end = end_fixed.checked_add(len).ok_or(SceneError::Limit)?;
        let text = std::str::from_utf8(bytes.get(end_fixed..end).ok_or(SceneError::Length)?)
            .map_err(|_| SceneError::Length)?;
        total = total.checked_add(len).ok_or(SceneError::Limit)?;
        if !x.is_finite()
            || !y.is_finite()
            || text.is_empty()
            || text.contains('\0')
            || total > MAX_SCENE_TEXT_BYTES
        {
            return Err(SceneError::Limit);
        }
        let px = x_scale.pixel(x);
        let py = y_scale.pixel(y);
        if !px.is_finite()
            || !py.is_finite()
            || px < layout.left
            || px > layout.right
            || py < layout.top
            || py > layout.bottom
        {
            return Err(SceneError::Length);
        }
        labels.push(SceneLabel {
            stable_id: 0x5859_0400_0000_0000 | index as u64,
            x: px,
            y: py,
            font_size: 12.0,
            rgba: fixed[16..20].try_into().unwrap(),
            text: text.to_owned(),
        });
        at = end;
    }
    if at != bytes.len() {
        return Err(SceneError::Length);
    }
    Ok(labels)
}

/// Decode labels attached to existing canonical Scene v12 annotation records.
/// `XYAL` contains identities and text only: Rust derives every anchor from the
/// validated Scene geometry, so hosts cannot choose pixels or placement policy.
fn decode_xyal(bytes: &[u8], document: &SceneDocument) -> Result<Vec<SceneLabel>, SceneError> {
    if bytes.is_empty() {
        return Ok(Vec::new());
    }
    if bytes.len() < 12 || &bytes[..4] != b"XYAL" || batch_u32(bytes, 4)? != 1 {
        return Err(SceneError::Length);
    }
    let count = batch_u32(bytes, 8)? as usize;
    if count > MAX_AUTHORED_TEXT_ANNOTATIONS {
        return Err(SceneError::Limit);
    }
    let mut at = 12usize;
    let mut total = 0usize;
    let mut seen = std::collections::BTreeSet::new();
    let mut labels = Vec::with_capacity(count);
    for index in 0..count {
        let fixed_end = at.checked_add(12).ok_or(SceneError::Limit)?;
        let fixed = bytes.get(at..fixed_end).ok_or(SceneError::Length)?;
        let stable_id = u64::from_le_bytes(fixed[..8].try_into().unwrap());
        let len = u32::from_le_bytes(fixed[8..12].try_into().unwrap()) as usize;
        let end = fixed_end.checked_add(len).ok_or(SceneError::Limit)?;
        let text = std::str::from_utf8(bytes.get(fixed_end..end).ok_or(SceneError::Length)?)
            .map_err(|_| SceneError::Length)?;
        total = total.checked_add(len).ok_or(SceneError::Limit)?;
        if !seen.insert(stable_id)
            || text.is_empty()
            || text.contains('\0')
            || total > MAX_SCENE_TEXT_BYTES
        {
            return Err(SceneError::Limit);
        }
        let records: Vec<_> = document
            .records
            .iter()
            .filter(|record| {
                record.stable_id == stable_id
                    && record.annotation_tag != 0
                    && record.annotation_tag != 0x80
            })
            .collect();
        let first = *records.first().ok_or(SceneError::Length)?;
        let (x, y) = match first.annotation_tag {
            1 if records.len() == 2 && first.kind == SceneRecordKind::Polyline => {
                let next = *records.get(1).ok_or(SceneError::Length)?;
                if first.coordinates[0] == next.coordinates[0] {
                    (first.coordinates[0], document.layout.top)
                } else if first.coordinates[1] == next.coordinates[1] {
                    (document.layout.right, first.coordinates[1])
                } else {
                    return Err(SceneError::Length);
                }
            }
            2 | 4 if records.len() == 1 && first.kind == SceneRecordKind::Rect => (
                (first.coordinates[0] + first.coordinates[2]) / 2.0,
                (first.coordinates[1] + first.coordinates[3]) / 2.0,
            ),
            3 if records.len() == 1 && first.kind == SceneRecordKind::Scatter => {
                (first.coordinates[0], first.coordinates[1])
            }
            _ => return Err(SceneError::Length),
        };
        labels.push(SceneLabel {
            stable_id: 0x5859_0500_0000_0000 | index as u64,
            x,
            y,
            font_size: 12.0,
            rgba: [102, 112, 133, 255],
            text: text.to_owned(),
        });
        at = end;
    }
    if at != bytes.len() {
        return Err(SceneError::Length);
    }
    Ok(labels)
}

/// Decode the bounded annotation-decoration envelope.  The envelope keeps
/// standalone `XYAT` and attached `XYAL` records independently versioned.
fn decode_annotation_envelope(
    bytes: &[u8],
    document: &SceneDocument,
) -> Result<Vec<SceneLabel>, SceneError> {
    if bytes.is_empty() {
        return Ok(Vec::new());
    }
    if bytes.len() < 20 || &bytes[..4] != b"XYAD" || batch_u32(bytes, 4)? != 1 {
        return Err(SceneError::Length);
    }
    let xyat_len = batch_u32(bytes, 8)? as usize;
    let xyal_len = batch_u32(bytes, 12)? as usize;
    if batch_u32(bytes, 16)? != 0 {
        return Err(SceneError::Length);
    }
    let xyat_end = 20usize.checked_add(xyat_len).ok_or(SceneError::Limit)?;
    let end = xyat_end.checked_add(xyal_len).ok_or(SceneError::Limit)?;
    if end != bytes.len() {
        return Err(SceneError::Length);
    }
    let mut labels = decode_xyat(
        &bytes[20..xyat_end],
        document.x_scale,
        document.y_scale,
        document.layout,
    )?;
    let mut attached = decode_xyal(&bytes[xyat_end..end], document)?;
    if labels
        .len()
        .checked_add(attached.len())
        .ok_or(SceneError::Limit)?
        > MAX_SCENE_LABELS
    {
        return Err(SceneError::Limit);
    }
    for (index, label) in labels.iter_mut().enumerate() {
        label.stable_id = 0x5859_0400_0000_0000 | index as u64;
    }
    for (index, label) in attached.iter_mut().enumerate() {
        label.stable_id = 0x5859_0500_0000_0000 | index as u64;
    }
    labels.append(&mut attached);
    Ok(labels)
}

type SceneChromeTrailer = (
    SceneChromeStyle,
    SceneChromeText,
    Option<SceneLegend>,
    Option<SceneColorbar>,
    Vec<SceneLabel>,
    usize,
);

fn read_chrome_trailer(bytes: &[u8], body_end: usize) -> Result<SceneChromeTrailer, SceneError> {
    let trailer = bytes
        .get(body_end..body_end + SCENE_CHROME_TRAILER_BYTES)
        .ok_or(SceneError::Length)?;
    if trailer[12..16] != [0; 4] {
        return Err(SceneError::Length);
    }
    let label_font_size = f64::from_le_bytes(trailer[16..24].try_into().unwrap());
    let read_axis = |offset: usize| -> Result<SceneAxisChromeStyle, SceneError> {
        if trailer[offset + 5..offset + 8] != [0; 3] {
            return Err(SceneError::Length);
        }
        let f64_at = |inner| {
            f64::from_le_bytes(
                trailer[offset + inner..offset + inner + 8]
                    .try_into()
                    .unwrap(),
            )
        };
        SceneAxisChromeStyle {
            side: AxisSide::from_code(trailer[offset])?,
            tick_sides: trailer[offset + 1],
            tick_label_sides: trailer[offset + 2],
            major_direction: TickDirection::from_code(trailer[offset + 3])?,
            minor_direction: TickDirection::from_code(trailer[offset + 4])?,
            axis_rgba: trailer[offset + 8..offset + 12].try_into().unwrap(),
            grid_rgba: trailer[offset + 12..offset + 16].try_into().unwrap(),
            tick_rgba: trailer[offset + 16..offset + 20].try_into().unwrap(),
            minor_grid_rgba: trailer[offset + 20..offset + 24].try_into().unwrap(),
            minor_tick_rgba: trailer[offset + 24..offset + 28].try_into().unwrap(),
            label_rgba: trailer[offset + 28..offset + 32].try_into().unwrap(),
            axis_width: f64_at(32),
            grid_width: f64_at(40),
            tick_width: f64_at(48),
            tick_length: f64_at(56),
            minor_grid_width: f64_at(64),
            minor_tick_width: f64_at(72),
            minor_tick_length: f64_at(80),
        }
        .validated()
    };
    let title_len = u32::from_le_bytes(trailer[200..204].try_into().unwrap()) as usize;
    let xlabel_len = u32::from_le_bytes(trailer[204..208].try_into().unwrap()) as usize;
    let ylabel_len = u32::from_le_bytes(trailer[208..212].try_into().unwrap()) as usize;
    let counts = [212, 216, 220, 224]
        .map(|offset| u32::from_le_bytes(trailer[offset..offset + 4].try_into().unwrap()));
    let legend_len = u32::from_le_bytes(trailer[228..232].try_into().unwrap()) as usize;
    let label_len = u32::from_le_bytes(trailer[232..236].try_into().unwrap()) as usize;
    let colorbar_len = u32::from_le_bytes(trailer[236..240].try_into().unwrap()) as usize;
    let x_tick_label_len = u32::from_le_bytes(trailer[240..244].try_into().unwrap()) as usize;
    let y_tick_label_len = u32::from_le_bytes(trailer[244..248].try_into().unwrap()) as usize;
    if legend_len > MAX_SCENE_LEGEND_INPUT_BYTES || colorbar_len > MAX_SCENE_COLORBAR_INPUT_BYTES {
        return Err(SceneError::Limit);
    }
    if counts[1] == u32::MAX || counts[3] == u32::MAX {
        return Err(SceneError::Length);
    }
    for count in counts {
        if count != u32::MAX && count as usize > MAX_AXIS_TICKS {
            return Err(SceneError::Limit);
        }
    }
    if title_len > MAX_SCENE_TEXT_BYTES
        || xlabel_len > MAX_SCENE_TEXT_BYTES
        || ylabel_len > MAX_SCENE_TEXT_BYTES
    {
        return Err(SceneError::Limit);
    }
    let text_start = body_end + SCENE_CHROME_TRAILER_BYTES;
    let tick_count = counts
        .into_iter()
        .filter(|count| *count != u32::MAX)
        .try_fold(0usize, |total, count| total.checked_add(count as usize))
        .ok_or(SceneError::Limit)?;
    let label_table_start = text_start
        .checked_add(title_len)
        .and_then(|value| value.checked_add(xlabel_len))
        .and_then(|value| value.checked_add(ylabel_len))
        .ok_or(SceneError::Limit)?;
    let values_start = label_table_start
        .checked_add(x_tick_label_len)
        .and_then(|value| value.checked_add(y_tick_label_len))
        .ok_or(SceneError::Limit)?;
    let content_end = values_start
        .checked_add(tick_count.checked_mul(8).ok_or(SceneError::Limit)?)
        .ok_or(SceneError::Limit)?;
    let colorbar_start = content_end
        .checked_add(legend_len)
        .ok_or(SceneError::Limit)?;
    let label_start = colorbar_start
        .checked_add(colorbar_len)
        .ok_or(SceneError::Limit)?;
    let total = label_start
        .checked_add(label_len)
        .ok_or(SceneError::Limit)?;
    if bytes.len() < total {
        return Err(SceneError::Length);
    }
    let title_bytes = &bytes[text_start..text_start + title_len];
    let xlabel_bytes = &bytes[text_start + title_len..text_start + title_len + xlabel_len];
    let ylabel_bytes = &bytes
        [text_start + title_len + xlabel_len..text_start + title_len + xlabel_len + ylabel_len];
    if title_bytes.contains(&0) || xlabel_bytes.contains(&0) || ylabel_bytes.contains(&0) {
        return Err(SceneError::Length);
    }
    let text = SceneChromeText {
        title: String::from_utf8(title_bytes.to_vec()).map_err(|_| SceneError::Length)?,
        x_label: String::from_utf8(xlabel_bytes.to_vec()).map_err(|_| SceneError::Length)?,
        y_label: String::from_utf8(ylabel_bytes.to_vec()).map_err(|_| SceneError::Length)?,
    };
    let x_tick_labels =
        decode_tick_labels(&bytes[label_table_start..label_table_start + x_tick_label_len])?;
    let y_tick_labels =
        decode_tick_labels(&bytes[label_table_start + x_tick_label_len..values_start])?;
    let mut values_at = values_start;
    let mut read_values = |count: u32| -> Result<Option<Vec<f64>>, SceneError> {
        if count == u32::MAX {
            return Ok(None);
        }
        let mut values = Vec::with_capacity(count as usize);
        for _ in 0..count {
            let value = f64::from_le_bytes(bytes[values_at..values_at + 8].try_into().unwrap());
            if !value.is_finite() {
                return Err(SceneError::NonFinite);
            }
            values.push(value);
            values_at += 8;
        }
        Ok(Some(values))
    };
    let x_major_ticks = read_values(counts[0])?;
    let x_minor_ticks = read_values(counts[1])?.unwrap_or_default();
    let y_major_ticks = read_values(counts[2])?;
    let y_minor_ticks = read_values(counts[3])?.unwrap_or_default();
    let chrome = SceneChromeStyle {
        chart_background_rgba: trailer[0..4].try_into().unwrap(),
        plot_background_rgba: trailer[4..8].try_into().unwrap(),
        label_rgba: trailer[8..12].try_into().unwrap(),
        label_font_size,
        x_axis: read_axis(24)?,
        y_axis: read_axis(112)?,
        x_major_ticks,
        x_minor_ticks,
        y_major_ticks,
        y_minor_ticks,
        x_tick_labels,
        y_tick_labels,
    }
    .validated()?;
    let legend = SceneLegend::from_canonical(&bytes[content_end..colorbar_start], usize::MAX)?;
    let colorbar = SceneColorbar::from_input(&bytes[colorbar_start..label_start])?;
    let labels = decode_scene_labels(&bytes[label_start..total])?;
    Ok((chrome, text, legend, colorbar, labels, total))
}

fn write_chrome_style_input(out: &mut Vec<u8>, chrome: &SceneChromeStyle) {
    out.extend_from_slice(&chrome.chart_background_rgba);
    out.extend_from_slice(&chrome.plot_background_rgba);
    out.extend_from_slice(&chrome.label_rgba);
    out.extend_from_slice(&[0; 4]);
    out.extend_from_slice(&chrome.label_font_size.to_le_bytes());
    let write_axis = |out: &mut Vec<u8>, axis: &SceneAxisChromeStyle| {
        out.extend_from_slice(&[
            axis.side as u8,
            axis.tick_sides,
            axis.tick_label_sides,
            axis.major_direction as u8,
            axis.minor_direction as u8,
            0,
            0,
            0,
        ]);
        out.extend_from_slice(&axis.axis_rgba);
        out.extend_from_slice(&axis.grid_rgba);
        out.extend_from_slice(&axis.tick_rgba);
        out.extend_from_slice(&axis.minor_grid_rgba);
        out.extend_from_slice(&axis.minor_tick_rgba);
        out.extend_from_slice(&axis.label_rgba);
        for value in [
            axis.axis_width,
            axis.grid_width,
            axis.tick_width,
            axis.tick_length,
            axis.minor_grid_width,
            axis.minor_tick_width,
            axis.minor_tick_length,
        ] {
            out.extend_from_slice(&value.to_le_bytes());
        }
    };
    write_axis(out, &chrome.x_axis);
    write_axis(out, &chrome.y_axis);
}

fn write_chrome_trailer(
    out: &mut Vec<u8>,
    chrome: &SceneChromeStyle,
    text: &SceneChromeText,
    legend: Option<&SceneLegend>,
    colorbar: Option<&SceneColorbar>,
    label_bytes: &[u8],
) {
    write_chrome_style_input(out, chrome);
    out.extend_from_slice(&(text.title.len() as u32).to_le_bytes());
    out.extend_from_slice(&(text.x_label.len() as u32).to_le_bytes());
    out.extend_from_slice(&(text.y_label.len() as u32).to_le_bytes());
    for (values, automatic) in [
        (
            chrome.x_major_ticks.as_deref().unwrap_or(&[]),
            chrome.x_major_ticks.is_none(),
        ),
        (&chrome.x_minor_ticks, false),
        (
            chrome.y_major_ticks.as_deref().unwrap_or(&[]),
            chrome.y_major_ticks.is_none(),
        ),
        (&chrome.y_minor_ticks, false),
    ] {
        out.extend_from_slice(
            &(if automatic {
                u32::MAX
            } else {
                values.len() as u32
            })
            .to_le_bytes(),
        );
    }
    let legend_bytes = legend.map(SceneLegend::encode).unwrap_or_default();
    let colorbar_bytes = colorbar
        .map(SceneColorbar::encode)
        .transpose()
        .expect("validated Scene colorbar")
        .unwrap_or_default();
    let x_tick_label_bytes =
        encode_tick_labels(chrome.x_tick_labels.as_deref()).expect("validated tick labels");
    let y_tick_label_bytes =
        encode_tick_labels(chrome.y_tick_labels.as_deref()).expect("validated tick labels");
    out.extend_from_slice(&(legend_bytes.len() as u32).to_le_bytes());
    out.extend_from_slice(&(label_bytes.len() as u32).to_le_bytes());
    out.extend_from_slice(&(colorbar_bytes.len() as u32).to_le_bytes());
    out.extend_from_slice(&(x_tick_label_bytes.len() as u32).to_le_bytes());
    out.extend_from_slice(&(y_tick_label_bytes.len() as u32).to_le_bytes());
    out.extend_from_slice(text.title.as_bytes());
    out.extend_from_slice(text.x_label.as_bytes());
    out.extend_from_slice(text.y_label.as_bytes());
    out.extend_from_slice(&x_tick_label_bytes);
    out.extend_from_slice(&y_tick_label_bytes);
    for values in [
        chrome.x_major_ticks.as_deref().unwrap_or(&[]),
        &chrome.x_minor_ticks,
        chrome.y_major_ticks.as_deref().unwrap_or(&[]),
        &chrome.y_minor_ticks,
    ] {
        for value in values {
            out.extend_from_slice(&value.to_le_bytes());
        }
    }
    out.extend_from_slice(&legend_bytes);
    out.extend_from_slice(&colorbar_bytes);
    out.extend_from_slice(label_bytes);
}

fn resolved_legend_bounds(
    layout: PlotLayout,
    legend: &SceneLegend,
) -> Result<(f64, f64, f64, f64), SceneError> {
    let widest = legend
        .entries
        .iter()
        .map(|entry| text_advance(&entry.label, legend.font_size))
        .chain(std::iter::once(text_advance(
            &legend.title,
            legend.title_font_size,
        )))
        .fold(0.0_f64, f64::max);
    let width = 36.0 + widest;
    let title_rows = usize::from(!legend.title.is_empty());
    let height = 12.0
        + legend.entries.len() as f64 * (legend.font_size + 6.0)
        + title_rows as f64 * (legend.title_font_size + 6.0);
    if !width.is_finite()
        || !height.is_finite()
        || width > layout.right - layout.left - 16.0
        || height > layout.bottom - layout.top - 16.0
    {
        return Err(SceneError::Limit);
    }
    let (mut x, mut y) = (layout.left + 8.0, layout.top + 8.0);
    match legend.location {
        LegendLocation::UpperRight => x = layout.right - width - 8.0,
        LegendLocation::UpperLeft => {}
        LegendLocation::LowerLeft => y = layout.bottom - height - 8.0,
        LegendLocation::LowerRight => {
            x = layout.right - width - 8.0;
            y = layout.bottom - height - 8.0;
        }
        LegendLocation::CenterRight => {
            x = layout.right - width - 8.0;
            y = (layout.top + layout.bottom - height) * 0.5;
        }
        LegendLocation::CenterLeft => y = (layout.top + layout.bottom - height) * 0.5,
        LegendLocation::UpperCenter => x = (layout.left + layout.right - width) * 0.5,
        LegendLocation::LowerCenter => {
            x = (layout.left + layout.right - width) * 0.5;
            y = layout.bottom - height - 8.0;
        }
        LegendLocation::Center => {
            x = (layout.left + layout.right - width) * 0.5;
            y = (layout.top + layout.bottom - height) * 0.5;
        }
    }
    Ok((x, y, width, height))
}

/// Resolved screen-space bounds for the bounded right/bottom colorbar. This is
/// intentionally the only placement policy; hosts receive the result, never
/// margins or a colormap layout decision.
fn resolved_colorbar_bounds(
    layout: PlotLayout,
    colorbar: &SceneColorbar,
) -> Result<(f64, f64, f64, f64), SceneError> {
    // The canonical colorbar occupies only the caller-provided outer gutter.
    // It must never shrink the already-resolved plot a second time.
    let title = text_advance(&colorbar.title, 11.0);
    let (x, y, width, height) = if colorbar.horizontal {
        if layout.viewport_height - layout.bottom < COLORBAR_OUTER_GUTTER + COLORBAR_THICKNESS {
            return Err(SceneError::Limit);
        }
        (
            layout.left,
            layout.bottom + COLORBAR_OUTER_GUTTER,
            layout.right - layout.left,
            COLORBAR_THICKNESS,
        )
    } else {
        if layout.viewport_width - layout.right < COLORBAR_OUTER_GUTTER + COLORBAR_THICKNESS {
            return Err(SceneError::Limit);
        }
        (
            layout.right + COLORBAR_OUTER_GUTTER,
            layout.top,
            COLORBAR_THICKNESS,
            layout.bottom - layout.top,
        )
    };
    if ![x, y, width, height, title].into_iter().all(f64::is_finite)
        || (colorbar.horizontal && width < 16.0)
        || (!colorbar.horizontal && height < 16.0)
        || x < 0.0
        || y < 0.0
        || x + width > layout.viewport_width
        || y + height > layout.viewport_height
    {
        return Err(SceneError::Limit);
    }
    Ok((x, y, width, height))
}

/// Validate a serialized canonical Scene v9 batch without allocating.
///
/// The direct-browser adapter uses this decoder as its first exact scene seam:
/// TypeScript does not guess record offsets or accept a provisional browser
/// schema. Future WASM compute exports will produce this same Rust-owned batch.
pub fn validate_scene_batch(bytes: &[u8]) -> Result<SceneBatchSummary, SceneError> {
    if bytes.get(..4) != Some(b"XYGS") {
        return Err(SceneError::Length);
    }
    if batch_u32(bytes, 4)? != SCENE_VERSION {
        return Err(SceneError::Version);
    }
    if batch_u32(bytes, 8)? as usize != SCENE_BATCH_HEADER_BYTES
        || batch_u32(bytes, 12)? as usize != SCENE_BATCH_RECORD_BYTES
    {
        return Err(SceneError::Length);
    }

    let records = usize::try_from(batch_u64(bytes, 16)?).map_err(|_| SceneError::Limit)?;
    let styles = usize::try_from(batch_u64(bytes, 24)?).map_err(|_| SceneError::Limit)?;
    if records > MAX_SCENE_MARKS || styles > MAX_SCENE_STYLES {
        return Err(SceneError::Limit);
    }
    let body = SCENE_BATCH_HEADER_BYTES
        .checked_add(
            styles
                .checked_mul(SCENE_STYLE_RECORD_BYTES)
                .ok_or(SceneError::Limit)?,
        )
        .and_then(|value| {
            records
                .checked_mul(SCENE_BATCH_RECORD_BYTES)
                .and_then(|record_bytes| value.checked_add(record_bytes))
        })
        .ok_or(SceneError::Limit)?;
    let (_chrome, _text, legend, _colorbar, _labels, total) = read_chrome_trailer(bytes, body)?;
    if let Some(legend) = legend {
        if legend.entries.iter().any(|entry| entry.style_ref >= styles) {
            return Err(SceneError::Length);
        }
    }
    if bytes.len() != total {
        return Err(SceneError::Length);
    }

    let viewport_width = batch_f64(bytes, 32)?;
    let viewport_height = batch_f64(bytes, 40)?;
    let left = batch_f64(bytes, 48)?;
    let top = batch_f64(bytes, 56)?;
    let right = batch_f64(bytes, 64)?;
    let bottom = batch_f64(bytes, 72)?;
    if [viewport_width, viewport_height, left, top, right, bottom]
        .iter()
        .any(|value| !value.is_finite())
        || viewport_width <= 0.0
        || viewport_height <= 0.0
        || left < 0.0
        || top < 0.0
        || right <= left
        || bottom <= top
        || right > viewport_width
        || bottom > viewport_height
    {
        return Err(SceneError::NonFinite);
    }

    for axis in [96usize, 104] {
        let kind = bytes[axis];
        let mask = bytes[axis + 1];
        if kind > ScaleKind::SymLog as u8
            || mask > 1
            || bytes[axis + 2..axis + 8].iter().any(|value| *value != 0)
        {
            return Err(SceneError::Length);
        }
    }
    let transformed = [
        batch_f64(bytes, 112)?,
        batch_f64(bytes, 120)?,
        batch_f64(bytes, 128)?,
        batch_f64(bytes, 136)?,
    ];
    let constants = [batch_f64(bytes, 144)?, batch_f64(bytes, 152)?];
    if transformed.iter().any(|value| !value.is_finite())
        || transformed[0] == transformed[1]
        || transformed[2] == transformed[3]
        || constants
            .iter()
            .any(|value| !value.is_finite() || *value <= 0.0)
    {
        return Err(SceneError::NonFinite);
    }

    let styles_offset = SCENE_BATCH_HEADER_BYTES;
    for index in 0..styles {
        let offset = styles_offset + index * SCENE_STYLE_RECORD_BYTES;
        let stroke_width = batch_f64(bytes, offset + 8)?;
        if !stroke_width.is_finite() || stroke_width < 0.0 {
            return Err(SceneError::NegativeSize);
        }
    }

    let records_offset = styles_offset + styles * SCENE_STYLE_RECORD_BYTES;
    for index in 0..records {
        let offset = records_offset + index * SCENE_BATCH_RECORD_BYTES;
        let kind = SceneRecordKind::from_code(bytes[offset])?;
        let visible = bytes[offset + 1];
        let symbol = bytes[offset + 2];
        if visible > 1 || !matches!(bytes[offset + 3], 0..=4 | 0x80) {
            return Err(SceneError::Length);
        }
        let style = batch_u32(bytes, offset + 4)? as usize;
        if style >= styles {
            return Err(SceneError::Length);
        }
        let coords = [
            batch_f64(bytes, offset + 16)?,
            batch_f64(bytes, offset + 24)?,
            batch_f64(bytes, offset + 32)?,
            batch_f64(bytes, offset + 40)?,
        ];
        let diameter = batch_f64(bytes, offset + 48)?;
        if coords.iter().any(|value| !value.is_finite()) || !diameter.is_finite() || diameter < 0.0
        {
            return Err(SceneError::NonFinite);
        }
        if visible == 0
            && bytes[offset + 16..offset + 48]
                .iter()
                .any(|value| *value != 0)
        {
            return Err(SceneError::Length);
        }
        match kind {
            SceneRecordKind::Scatter => {
                if symbol > ScatterSymbol::X as u8 || coords[2] != 0.0 || coords[3] != 0.0 {
                    return Err(SceneError::Length);
                }
            }
            SceneRecordKind::Polyline => {
                if symbol != 0 || diameter != 0.0 || coords[2] != 0.0 || coords[3] != 0.0 {
                    return Err(SceneError::Length);
                }
            }
            SceneRecordKind::Rect => {
                if symbol != 0
                    || diameter != 0.0
                    || (visible != 0 && (coords[0] > coords[2] || coords[1] > coords[3]))
                {
                    return Err(SceneError::Length);
                }
            }
            SceneRecordKind::Band => {
                if symbol != 0 || diameter != 0.0 {
                    return Err(SceneError::Length);
                }
            }
            SceneRecordKind::PolyFill => {
                if symbol != 0 || diameter != 0.0 || coords[2] != 0.0 || coords[3] != 0.0 {
                    return Err(SceneError::Length);
                }
            }
        }
    }

    // Keep this allocation-free seam equivalent to SceneDocument::decode for
    // the reserved Scene v12 annotation namespace. A batch that validates here
    // must never fail later only because its annotation runs were malformed.
    let mut annotation_cursor = 0;
    let mut annotations_started = false;
    while annotation_cursor < records {
        let offset = records_offset + annotation_cursor * SCENE_BATCH_RECORD_BYTES;
        let stable_id = batch_u64(bytes, offset + 8)?;
        let tag = bytes[offset + 3];
        if tag == 0 || tag == 0x80 {
            if annotations_started {
                return Err(SceneError::Length);
            }
            annotation_cursor += 1;
            continue;
        }
        annotations_started = true;
        let mut run_end = annotation_cursor + 1;
        while run_end < records {
            let candidate = records_offset + run_end * SCENE_BATCH_RECORD_BYTES;
            if bytes[candidate + 3] != tag || batch_u64(bytes, candidate + 8)? != stable_id {
                break;
            }
            run_end += 1;
        }
        let kind = SceneRecordKind::from_code(bytes[offset])?;
        let visible = bytes[offset + 1];
        let style_ref = batch_u32(bytes, offset + 4)?;
        let coordinates = [
            batch_f64(bytes, offset + 16)?,
            batch_f64(bytes, offset + 24)?,
            batch_f64(bytes, offset + 32)?,
            batch_f64(bytes, offset + 40)?,
        ];
        match tag {
            1 if kind == SceneRecordKind::Polyline && run_end - annotation_cursor == 2 => {
                let next = offset + SCENE_BATCH_RECORD_BYTES;
                let next_coordinates = [batch_f64(bytes, next + 16)?, batch_f64(bytes, next + 24)?];
                if SceneRecordKind::from_code(bytes[next])? != SceneRecordKind::Polyline
                    || batch_u32(bytes, next + 4)? != style_ref
                    || bytes[next + 1] != visible
                    || (visible != 0
                        && !((coordinates[0] == next_coordinates[0])
                            ^ (coordinates[1] == next_coordinates[1])))
                {
                    return Err(SceneError::Length);
                }
            }
            2 if kind == SceneRecordKind::Rect && run_end - annotation_cursor == 1 => {
                if visible != 0
                    && (!scene_edge_eq(coordinates[1], top)
                        || !scene_edge_eq(coordinates[3], bottom))
                {
                    return Err(SceneError::Length);
                }
            }
            3 if kind == SceneRecordKind::Scatter && run_end - annotation_cursor == 1 => {}
            4 if kind == SceneRecordKind::Rect && run_end - annotation_cursor == 1 => {
                if visible != 0
                    && (!scene_edge_eq(coordinates[0], left)
                        || !scene_edge_eq(coordinates[2], right))
                {
                    return Err(SceneError::Length);
                }
            }
            _ => return Err(SceneError::Length),
        }
        annotation_cursor = run_end;
    }

    Ok(SceneBatchSummary { records, styles })
}

#[derive(Clone, Copy, Debug, PartialEq)]
pub struct PlotLayout {
    pub viewport_width: f64,
    pub viewport_height: f64,
    pub left: f64,
    pub top: f64,
    pub right: f64,
    pub bottom: f64,
}

impl PlotLayout {
    pub fn new(
        viewport_width: f64,
        viewport_height: f64,
        margin_left: f64,
        margin_right: f64,
        margin_top: f64,
        margin_bottom: f64,
    ) -> Result<Self, SceneError> {
        if [
            viewport_width,
            viewport_height,
            margin_left,
            margin_right,
            margin_top,
            margin_bottom,
        ]
        .iter()
        .any(|value| !value.is_finite() || *value < 0.0)
            || viewport_width <= margin_left + margin_right
            || viewport_height <= margin_top + margin_bottom
        {
            return Err(SceneError::NonFinite);
        }
        Ok(Self {
            viewport_width,
            viewport_height,
            left: margin_left,
            top: margin_top,
            right: viewport_width - margin_right,
            bottom: viewport_height - margin_bottom,
        })
    }
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
#[repr(u8)]
pub enum SceneRecordKind {
    Scatter = 0,
    Polyline = 1,
    Rect = 2,
    /// Filled band: each record is one (top, base) sample; consecutive same
    /// stable-id/style_ref runs form a closed polygon (tops forward, bases reverse).
    Band = 3,
    /// Filled polygon vertex: consecutive same stable-id/style_ref runs with
    /// at least three vertices form one closed fill (triangle mesh hosts emit
    /// one three-vertex run per triangle).
    PolyFill = 4,
}

impl SceneRecordKind {
    fn from_code(value: u8) -> Result<Self, SceneError> {
        match value {
            0 => Ok(Self::Scatter),
            1 => Ok(Self::Polyline),
            2 => Ok(Self::Rect),
            3 => Ok(Self::Band),
            4 => Ok(Self::PolyFill),
            _ => Err(SceneError::Length),
        }
    }
}

pub struct SceneBatch<'a> {
    layout: PlotLayout,
    x_axis_id: u64,
    y_axis_id: u64,
    x_scale: AxisScale,
    y_scale: AxisScale,
    chrome: SceneChromeStyle,
    text: SceneChromeText,
    legend: Option<SceneLegend>,
    colorbar: Option<SceneColorbar>,
    labels: Vec<SceneLabel>,
    kinds: &'a [u8],
    stable_ids: &'a [u64],
    style_refs: &'a [u32],
    fill_rgba: &'a [u8],
    stroke_rgba: &'a [u8],
    stroke_width: &'a [f64],
    diameter: &'a [f64],
    symbols: &'a [u8],
    x0: &'a [f64],
    y0: &'a [f64],
    x1: &'a [f64],
    y1: &'a [f64],
    annotations_from_ids: bool,
}

impl<'a> SceneBatch<'a> {
    /// Attach bounded authored decorations before canonical Scene encoding.
    pub fn with_authored_annotations(mut self, bytes: &[u8]) -> Result<Self, SceneError> {
        if bytes.is_empty() {
            return Ok(self);
        }
        if bytes.len() < 20
            || &bytes[..4] != b"XYAD"
            || batch_u32(bytes, 4)? != 1
            || batch_u32(bytes, 16)? != 0
        {
            return Err(SceneError::Length);
        }
        let xyat_len = batch_u32(bytes, 8)? as usize;
        let xyal_len = batch_u32(bytes, 12)? as usize;
        let xyat_end = 20usize.checked_add(xyat_len).ok_or(SceneError::Limit)?;
        let end = xyat_end.checked_add(xyal_len).ok_or(SceneError::Limit)?;
        if end != bytes.len() {
            return Err(SceneError::Length);
        }
        let mut labels = decode_xyat(
            &bytes[20..xyat_end],
            self.x_scale,
            self.y_scale,
            self.layout,
        )?;
        let attached = &bytes[xyat_end..end];
        if !attached.is_empty() {
            if attached.len() < 12 || &attached[..4] != b"XYAL" || batch_u32(attached, 4)? != 1 {
                return Err(SceneError::Length);
            }
            let count = batch_u32(attached, 8)? as usize;
            if count > MAX_AUTHORED_TEXT_ANNOTATIONS {
                return Err(SceneError::Limit);
            }
            let mut at = 12usize;
            let mut total = 0usize;
            let mut seen = std::collections::BTreeSet::new();
            for index in 0..count {
                let fixed_end = at.checked_add(12).ok_or(SceneError::Limit)?;
                let fixed = attached.get(at..fixed_end).ok_or(SceneError::Length)?;
                let stable_id = u64::from_le_bytes(fixed[..8].try_into().unwrap());
                let len = u32::from_le_bytes(fixed[8..12].try_into().unwrap()) as usize;
                let text_end = fixed_end.checked_add(len).ok_or(SceneError::Limit)?;
                let text = std::str::from_utf8(
                    attached
                        .get(fixed_end..text_end)
                        .ok_or(SceneError::Length)?,
                )
                .map_err(|_| SceneError::Length)?;
                total = total.checked_add(len).ok_or(SceneError::Limit)?;
                if !seen.insert(stable_id)
                    || text.is_empty()
                    || text.contains('\0')
                    || total > MAX_SCENE_TEXT_BYTES
                {
                    return Err(SceneError::Limit);
                }
                let indices: Vec<_> = self
                    .stable_ids
                    .iter()
                    .enumerate()
                    .filter_map(|(i, id)| (*id == stable_id).then_some(i))
                    .collect();
                let first_index = *indices.first().ok_or(SceneError::Length)?;
                let tag = ((stable_id >> 40) & 0xff) as u8;
                let (x, y) = match tag {
                    1 if indices.len() == 2
                        && self.kinds[first_index] == SceneRecordKind::Polyline as u8 =>
                    {
                        let next = indices[1];
                        let x0 = self.x_scale.pixel(self.x0[first_index]);
                        let y0 = self.y_scale.pixel(self.y0[first_index]);
                        let x1 = self.x_scale.pixel(self.x0[next]);
                        let y1 = self.y_scale.pixel(self.y0[next]);
                        if x0 == x1 {
                            (x0, self.layout.top)
                        } else if y0 == y1 {
                            (self.layout.right, y0)
                        } else {
                            return Err(SceneError::Length);
                        }
                    }
                    2 | 4
                        if indices.len() == 1
                            && self.kinds[first_index] == SceneRecordKind::Rect as u8 =>
                    {
                        (
                            (self.x_scale.pixel(self.x0[first_index])
                                + self.x_scale.pixel(self.x1[first_index]))
                                / 2.0,
                            (self.y_scale.pixel(self.y0[first_index])
                                + self.y_scale.pixel(self.y1[first_index]))
                                / 2.0,
                        )
                    }
                    3 if indices.len() == 1
                        && self.kinds[first_index] == SceneRecordKind::Scatter as u8 =>
                    {
                        (
                            self.x_scale.pixel(self.x0[first_index]),
                            self.y_scale.pixel(self.y0[first_index]),
                        )
                    }
                    _ => return Err(SceneError::Length),
                };
                if !x.is_finite() || !y.is_finite() {
                    return Err(SceneError::Length);
                }
                labels.push(SceneLabel {
                    stable_id: 0x5859_0500_0000_0000 | index as u64,
                    x,
                    y,
                    font_size: 12.0,
                    rgba: [102, 112, 133, 255],
                    text: text.to_owned(),
                });
                at = text_end;
            }
            if at != attached.len() {
                return Err(SceneError::Length);
            }
        }
        if labels.len() > MAX_SCENE_LABELS {
            return Err(SceneError::Limit);
        }
        for (index, label) in labels.iter_mut().enumerate() {
            if label.stable_id >> 40 == 0x5859_04 {
                label.stable_id = 0x5859_0400_0000_0000 | index as u64;
            }
        }
        self.labels = labels;
        Ok(self)
    }

    #[allow(clippy::too_many_arguments)]
    pub fn new(
        layout: PlotLayout,
        x_axis_id: u64,
        y_axis_id: u64,
        x_scale: AxisScale,
        y_scale: AxisScale,
        kinds: &'a [u8],
        stable_ids: &'a [u64],
        style_refs: &'a [u32],
        fill_rgba: &'a [u8],
        stroke_rgba: &'a [u8],
        stroke_width: &'a [f64],
        diameter: &'a [f64],
        symbols: &'a [u8],
        x0: &'a [f64],
        y0: &'a [f64],
        x1: &'a [f64],
        y1: &'a [f64],
    ) -> Result<Self, SceneError> {
        Self::new_with_chrome(
            layout,
            x_axis_id,
            y_axis_id,
            x_scale,
            y_scale,
            SceneChromeStyle::default(),
            SceneChromeText::default(),
            kinds,
            stable_ids,
            style_refs,
            fill_rgba,
            stroke_rgba,
            stroke_width,
            diameter,
            symbols,
            x0,
            y0,
            x1,
            y1,
        )
    }

    #[allow(clippy::too_many_arguments)]
    pub fn new_with_chrome(
        layout: PlotLayout,
        x_axis_id: u64,
        y_axis_id: u64,
        x_scale: AxisScale,
        y_scale: AxisScale,
        chrome: SceneChromeStyle,
        text: SceneChromeText,
        kinds: &'a [u8],
        stable_ids: &'a [u64],
        style_refs: &'a [u32],
        fill_rgba: &'a [u8],
        stroke_rgba: &'a [u8],
        stroke_width: &'a [f64],
        diameter: &'a [f64],
        symbols: &'a [u8],
        x0: &'a [f64],
        y0: &'a [f64],
        x1: &'a [f64],
        y1: &'a [f64],
    ) -> Result<Self, SceneError> {
        Self::new_with_decorations(
            layout,
            x_axis_id,
            y_axis_id,
            x_scale,
            y_scale,
            chrome,
            text,
            None,
            kinds,
            stable_ids,
            style_refs,
            fill_rgba,
            stroke_rgba,
            stroke_width,
            diameter,
            symbols,
            x0,
            y0,
            x1,
            y1,
        )
    }

    #[allow(clippy::too_many_arguments)]
    pub fn new_with_decorations(
        layout: PlotLayout,
        x_axis_id: u64,
        y_axis_id: u64,
        x_scale: AxisScale,
        y_scale: AxisScale,
        chrome: SceneChromeStyle,
        text: SceneChromeText,
        legend: Option<SceneLegend>,
        kinds: &'a [u8],
        stable_ids: &'a [u64],
        style_refs: &'a [u32],
        fill_rgba: &'a [u8],
        stroke_rgba: &'a [u8],
        stroke_width: &'a [f64],
        diameter: &'a [f64],
        symbols: &'a [u8],
        x0: &'a [f64],
        y0: &'a [f64],
        x1: &'a [f64],
        y1: &'a [f64],
    ) -> Result<Self, SceneError> {
        Self::new_with_decorations_impl(
            layout,
            x_axis_id,
            y_axis_id,
            x_scale,
            y_scale,
            chrome,
            text,
            legend,
            None,
            Vec::new(),
            kinds,
            stable_ids,
            style_refs,
            fill_rgba,
            stroke_rgba,
            stroke_width,
            diameter,
            symbols,
            x0,
            y0,
            x1,
            y1,
            true,
        )
    }

    #[allow(clippy::too_many_arguments)]
    pub fn new_with_decorations_and_labels(
        layout: PlotLayout,
        x_axis_id: u64,
        y_axis_id: u64,
        x_scale: AxisScale,
        y_scale: AxisScale,
        chrome: SceneChromeStyle,
        text: SceneChromeText,
        legend: Option<SceneLegend>,
        labels: Vec<SceneLabel>,
        kinds: &'a [u8],
        stable_ids: &'a [u64],
        style_refs: &'a [u32],
        fill_rgba: &'a [u8],
        stroke_rgba: &'a [u8],
        stroke_width: &'a [f64],
        diameter: &'a [f64],
        symbols: &'a [u8],
        x0: &'a [f64],
        y0: &'a [f64],
        x1: &'a [f64],
        y1: &'a [f64],
    ) -> Result<Self, SceneError> {
        Self::new_with_decorations_impl(
            layout,
            x_axis_id,
            y_axis_id,
            x_scale,
            y_scale,
            chrome,
            text,
            legend,
            None,
            labels,
            kinds,
            stable_ids,
            style_refs,
            fill_rgba,
            stroke_rgba,
            stroke_width,
            diameter,
            symbols,
            x0,
            y0,
            x1,
            y1,
            true,
        )
    }

    /// Identical to `new_with_decorations_and_labels`, with the already
    /// framed literal colorbar supplied by a thin binding.  Keeping this
    /// separate preserves older internal callers while making colorbar
    /// admission explicit at the Rust authority boundary.
    #[allow(clippy::too_many_arguments)]
    pub fn new_with_decorations_colorbar(
        layout: PlotLayout,
        x_axis_id: u64,
        y_axis_id: u64,
        x_scale: AxisScale,
        y_scale: AxisScale,
        chrome: SceneChromeStyle,
        text: SceneChromeText,
        legend: Option<SceneLegend>,
        colorbar: Option<SceneColorbar>,
        labels: Vec<SceneLabel>,
        kinds: &'a [u8],
        stable_ids: &'a [u64],
        style_refs: &'a [u32],
        fill_rgba: &'a [u8],
        stroke_rgba: &'a [u8],
        stroke_width: &'a [f64],
        diameter: &'a [f64],
        symbols: &'a [u8],
        x0: &'a [f64],
        y0: &'a [f64],
        x1: &'a [f64],
        y1: &'a [f64],
    ) -> Result<Self, SceneError> {
        Self::new_with_decorations_impl(
            layout,
            x_axis_id,
            y_axis_id,
            x_scale,
            y_scale,
            chrome,
            text,
            legend,
            colorbar,
            labels,
            kinds,
            stable_ids,
            style_refs,
            fill_rgba,
            stroke_rgba,
            stroke_width,
            diameter,
            symbols,
            x0,
            y0,
            x1,
            y1,
            true,
        )
    }

    #[allow(clippy::too_many_arguments)]
    pub fn new_with_chrome_literal_ids(
        layout: PlotLayout,
        x_axis_id: u64,
        y_axis_id: u64,
        x_scale: AxisScale,
        y_scale: AxisScale,
        chrome: SceneChromeStyle,
        text: SceneChromeText,
        kinds: &'a [u8],
        stable_ids: &'a [u64],
        style_refs: &'a [u32],
        fill_rgba: &'a [u8],
        stroke_rgba: &'a [u8],
        stroke_width: &'a [f64],
        diameter: &'a [f64],
        symbols: &'a [u8],
        x0: &'a [f64],
        y0: &'a [f64],
        x1: &'a [f64],
        y1: &'a [f64],
    ) -> Result<Self, SceneError> {
        Self::new_with_decorations_impl(
            layout,
            x_axis_id,
            y_axis_id,
            x_scale,
            y_scale,
            chrome,
            text,
            None,
            None,
            Vec::new(),
            kinds,
            stable_ids,
            style_refs,
            fill_rgba,
            stroke_rgba,
            stroke_width,
            diameter,
            symbols,
            x0,
            y0,
            x1,
            y1,
            false,
        )
    }

    #[allow(clippy::too_many_arguments)]
    fn new_with_decorations_impl(
        layout: PlotLayout,
        x_axis_id: u64,
        y_axis_id: u64,
        x_scale: AxisScale,
        y_scale: AxisScale,
        chrome: SceneChromeStyle,
        text: SceneChromeText,
        legend: Option<SceneLegend>,
        colorbar: Option<SceneColorbar>,
        labels: Vec<SceneLabel>,
        kinds: &'a [u8],
        stable_ids: &'a [u64],
        style_refs: &'a [u32],
        fill_rgba: &'a [u8],
        stroke_rgba: &'a [u8],
        stroke_width: &'a [f64],
        diameter: &'a [f64],
        symbols: &'a [u8],
        x0: &'a [f64],
        y0: &'a [f64],
        x1: &'a [f64],
        y1: &'a [f64],
        annotations_from_ids: bool,
    ) -> Result<Self, SceneError> {
        let chrome = chrome.validated()?;
        encode_scene_labels(&labels)?;
        if labels.iter().any(|label| {
            label.x < 0.0
                || label.x > layout.viewport_width
                || label.y < 0.0
                || label.y > layout.viewport_height
        }) {
            return Err(SceneError::Length);
        }
        let len = kinds.len();
        if len > MAX_SCENE_MARKS {
            return Err(SceneError::Limit);
        }
        let style_count = stroke_width.len();
        if style_count > MAX_SCENE_STYLES
            || fill_rgba.len() != style_count.saturating_mul(4)
            || stroke_rgba.len() != style_count.saturating_mul(4)
        {
            return Err(SceneError::Limit);
        }
        if let Some(value) = &legend {
            value.validate_constructed()?;
            if value.entries.iter().any(|entry| {
                entry.style_ref >= style_count
                    || entry.fill_rgba != fill_rgba[entry.style_ref * 4..entry.style_ref * 4 + 4]
                    || entry.stroke_rgba
                        != stroke_rgba[entry.style_ref * 4..entry.style_ref * 4 + 4]
            }) {
                return Err(SceneError::Length);
            }
            resolved_legend_bounds(layout, value)?;
        }
        if let Some(value) = &colorbar {
            value.encode()?;
            resolved_colorbar_bounds(layout, value)?;
        }
        if [
            stable_ids.len(),
            style_refs.len(),
            diameter.len(),
            symbols.len(),
            x0.len(),
            y0.len(),
            x1.len(),
            y1.len(),
        ]
        .into_iter()
        .any(|value| value != len)
            || kinds
                .iter()
                .any(|kind| SceneRecordKind::from_code(*kind).is_err())
        {
            return Err(SceneError::Length);
        }
        for (index, kind) in kinds.iter().enumerate() {
            let kind = SceneRecordKind::from_code(*kind)?;
            if style_refs[index] as usize >= style_count
                || (kind == SceneRecordKind::Scatter
                    && symbols[index] > ScatterSymbol::VerticalLine as u8)
                || (kind != SceneRecordKind::Scatter
                    && (diameter[index] != 0.0 || symbols[index] != 0))
            {
                return Err(SceneError::Length);
            }
        }
        // Scene v12 annotation records use ordinary paint primitives but a
        // reserved identity namespace. Validate their complete geometry here,
        // before any consumer can mistake a malformed annotation for a trace.
        let mut annotation_index = 0;
        let mut annotations_started = false;
        while annotations_from_ids && annotation_index < len {
            let id = stable_ids[annotation_index];
            if !is_scene_annotation_id(id) {
                if annotations_started {
                    return Err(SceneError::Length);
                }
                annotation_index += 1;
                continue;
            }
            annotations_started = true;
            let tag = ((id >> 40) & 0xff) as u8;
            let kind = SceneRecordKind::from_code(kinds[annotation_index])?;
            let run_end = stable_ids[annotation_index + 1..]
                .iter()
                .position(|candidate| *candidate != id)
                .map_or(len, |offset| annotation_index + 1 + offset);
            match tag {
                1 if kind == SceneRecordKind::Polyline && run_end - annotation_index == 2 => {
                    let next = annotation_index + 1;
                    if SceneRecordKind::from_code(kinds[next])? != SceneRecordKind::Polyline
                        || !((x0[annotation_index] == x0[next])
                            ^ (y0[annotation_index] == y0[next]))
                        || style_refs[annotation_index] != style_refs[next]
                    {
                        return Err(SceneError::Length);
                    }
                }
                2 if kind == SceneRecordKind::Rect && run_end - annotation_index == 1 => {
                    let py0 = y_scale.pixel(y0[annotation_index]);
                    let py1 = y_scale.pixel(y1[annotation_index]);
                    if !((scene_edge_eq(py0, layout.top) && scene_edge_eq(py1, layout.bottom))
                        || (scene_edge_eq(py0, layout.bottom) && scene_edge_eq(py1, layout.top)))
                    {
                        return Err(SceneError::Length);
                    }
                }
                3 if kind == SceneRecordKind::Scatter && run_end - annotation_index == 1 => {}
                4 if kind == SceneRecordKind::Rect && run_end - annotation_index == 1 => {
                    let px0 = x_scale.pixel(x0[annotation_index]);
                    let px1 = x_scale.pixel(x1[annotation_index]);
                    if !((scene_edge_eq(px0, layout.left) && scene_edge_eq(px1, layout.right))
                        || (scene_edge_eq(px0, layout.right) && scene_edge_eq(px1, layout.left)))
                    {
                        return Err(SceneError::Length);
                    }
                }
                _ => return Err(SceneError::Length),
            }
            annotation_index = run_end;
        }
        if kinds.iter().enumerate().any(|(index, kind)| {
            !x0[index].is_finite()
                || !y0[index].is_finite()
                || (matches!(
                    SceneRecordKind::from_code(*kind),
                    Ok(SceneRecordKind::Rect | SceneRecordKind::Band)
                ) && (!x1[index].is_finite() || !y1[index].is_finite()))
        }) || diameter
            .iter()
            .chain(stroke_width)
            .any(|value| !value.is_finite() || *value < 0.0)
        {
            return Err(SceneError::NonFinite);
        }
        resolved_axis_ticks(
            x_scale,
            layout.right - layout.left,
            true,
            layout.left,
            layout.right,
            chrome.x_major_ticks.as_deref(),
            &chrome.x_minor_ticks,
        )?;
        resolved_axis_ticks(
            y_scale,
            layout.bottom - layout.top,
            false,
            layout.top,
            layout.bottom,
            chrome.y_major_ticks.as_deref(),
            &chrome.y_minor_ticks,
        )?;
        Ok(Self {
            layout,
            x_axis_id,
            y_axis_id,
            x_scale,
            y_scale,
            chrome,
            text,
            legend,
            colorbar,
            labels,
            kinds,
            stable_ids,
            style_refs,
            fill_rgba,
            stroke_rgba,
            stroke_width,
            diameter,
            symbols,
            x0,
            y0,
            x1,
            y1,
            annotations_from_ids,
        })
    }

    pub fn encode(&self) -> Vec<u8> {
        let label_bytes = encode_scene_labels(&self.labels).expect("validated Scene labels");
        let mut out = Vec::with_capacity(
            SCENE_BATCH_HEADER_BYTES
                + self.stroke_width.len() * SCENE_STYLE_RECORD_BYTES
                + self.kinds.len() * SCENE_BATCH_RECORD_BYTES
                + self.text.encoded_bytes()
                + encode_tick_labels(self.chrome.x_tick_labels.as_deref())
                    .map_or(0, |value| value.len())
                + encode_tick_labels(self.chrome.y_tick_labels.as_deref())
                    .map_or(0, |value| value.len())
                + self.legend.as_ref().map_or(0, |value| value.encode().len())
                + label_bytes.len()
                + [
                    self.chrome.x_major_ticks.as_deref().unwrap_or(&[]).len(),
                    self.chrome.x_minor_ticks.len(),
                    self.chrome.y_major_ticks.as_deref().unwrap_or(&[]).len(),
                    self.chrome.y_minor_ticks.len(),
                ]
                .into_iter()
                .sum::<usize>()
                    * 8,
        );
        out.extend_from_slice(b"XYGS");
        out.extend_from_slice(&SCENE_VERSION.to_le_bytes());
        out.extend_from_slice(&(SCENE_BATCH_HEADER_BYTES as u32).to_le_bytes());
        out.extend_from_slice(&(SCENE_BATCH_RECORD_BYTES as u32).to_le_bytes());
        out.extend_from_slice(&(self.kinds.len() as u64).to_le_bytes());
        out.extend_from_slice(&(self.stroke_width.len() as u64).to_le_bytes());
        for value in [
            self.layout.viewport_width,
            self.layout.viewport_height,
            self.layout.left,
            self.layout.top,
            self.layout.right,
            self.layout.bottom,
        ] {
            out.extend_from_slice(&value.to_le_bytes());
        }
        out.extend_from_slice(&self.x_axis_id.to_le_bytes());
        out.extend_from_slice(&self.y_axis_id.to_le_bytes());
        // AxisScene records: kind/mask, transformed domain, and symlog constant.
        out.push(self.x_scale.kind as u8);
        out.push(u8::from(self.x_scale.mask_nonpositive));
        out.extend_from_slice(&[0; 6]);
        out.push(self.y_scale.kind as u8);
        out.push(u8::from(self.y_scale.mask_nonpositive));
        out.extend_from_slice(&[0; 6]);
        out.extend_from_slice(&self.x_scale.coord_lo.to_le_bytes());
        out.extend_from_slice(&(self.x_scale.coord_lo + self.x_scale.coord_span).to_le_bytes());
        out.extend_from_slice(&self.y_scale.coord_lo.to_le_bytes());
        out.extend_from_slice(&(self.y_scale.coord_lo + self.y_scale.coord_span).to_le_bytes());
        out.extend_from_slice(&self.x_scale.constant.to_le_bytes());
        out.extend_from_slice(&self.y_scale.constant.to_le_bytes());
        debug_assert_eq!(out.len(), SCENE_BATCH_HEADER_BYTES);

        for index in 0..self.stroke_width.len() {
            out.extend_from_slice(&self.fill_rgba[index * 4..index * 4 + 4]);
            out.extend_from_slice(&self.stroke_rgba[index * 4..index * 4 + 4]);
            out.extend_from_slice(&self.stroke_width[index].to_le_bytes());
        }

        for index in 0..self.kinds.len() {
            let kind = SceneRecordKind::from_code(self.kinds[index]).expect("validated kind");
            let mapped = match kind {
                SceneRecordKind::Scatter
                | SceneRecordKind::Polyline
                | SceneRecordKind::PolyFill => [
                    self.x_scale.pixel(self.x0[index]),
                    self.y_scale.pixel(self.y0[index]),
                    0.0,
                    0.0,
                ],
                SceneRecordKind::Rect | SceneRecordKind::Band => [
                    self.x_scale.pixel(self.x0[index]),
                    self.y_scale.pixel(self.y0[index]),
                    self.x_scale.pixel(self.x1[index]),
                    self.y_scale.pixel(self.y1[index]),
                ],
            };
            let visible = mapped.iter().all(|value| value.is_finite())
                && match kind {
                    SceneRecordKind::Polyline
                    | SceneRecordKind::Band
                    | SceneRecordKind::PolyFill => true,
                    SceneRecordKind::Scatter => {
                        let style = self.style_refs[index] as usize;
                        let geometry = MarkerGeometry::new(
                            ScatterSymbol::from_code(self.symbols[index]),
                            self.diameter[index],
                            self.stroke_width[style],
                        );
                        mapped[0] + geometry.extent_x >= self.layout.left
                            && mapped[0] - geometry.extent_x <= self.layout.right
                            && mapped[1] + geometry.extent_y >= self.layout.top
                            && mapped[1] - geometry.extent_y <= self.layout.bottom
                    }
                    SceneRecordKind::Rect => {
                        mapped[0].min(mapped[2]) <= self.layout.right
                            && mapped[0].max(mapped[2]) >= self.layout.left
                            && mapped[1].min(mapped[3]) <= self.layout.bottom
                            && mapped[1].max(mapped[3]) >= self.layout.top
                    }
                };
            out.push(kind as u8);
            out.push(u8::from(visible));
            out.push(self.symbols[index]);
            out.push(if !self.annotations_from_ids {
                0x80
            } else if is_scene_annotation_id(self.stable_ids[index]) {
                ((self.stable_ids[index] >> 40) & 0xff) as u8
            } else {
                0
            });
            out.extend_from_slice(&self.style_refs[index].to_le_bytes());
            out.extend_from_slice(&self.stable_ids[index].to_le_bytes());
            let record_coordinates = if !visible {
                [0.0; 4]
            } else {
                match kind {
                    SceneRecordKind::Scatter
                    | SceneRecordKind::Polyline
                    | SceneRecordKind::PolyFill => [mapped[0], mapped[1], 0.0, 0.0],
                    SceneRecordKind::Rect => [
                        mapped[0].min(mapped[2]),
                        mapped[1].min(mapped[3]),
                        mapped[0].max(mapped[2]),
                        mapped[1].max(mapped[3]),
                    ],
                    // Keep top/base sample order — winding matters for the fill.
                    SceneRecordKind::Band => mapped,
                }
            };
            for value in record_coordinates {
                out.extend_from_slice(&value.to_le_bytes());
            }
            out.extend_from_slice(&self.diameter[index].to_le_bytes());
        }
        write_chrome_trailer(
            &mut out,
            &self.chrome,
            &self.text,
            self.legend.as_ref(),
            self.colorbar.as_ref(),
            &label_bytes,
        );
        out
    }
}

#[derive(Clone, Copy)]
struct EncodedStyle {
    fill: [u8; 4],
    stroke: [u8; 4],
    stroke_width: f64,
}

#[derive(Clone, Copy)]
struct EncodedRecord {
    kind: SceneRecordKind,
    visible: bool,
    symbol: u8,
    style_ref: usize,
    stable_id: u64,
    coordinates: [f64; 4],
    diameter: f64,
    annotation_tag: u8,
}

// Scene v12 tag 0x80 marks literal per-row identity, so it is intentionally
// excluded from grouping: callers use kind/style for those run boundaries,
// while legacy and annotation records additionally require stable-ID equality.
fn same_record_run(left: EncodedRecord, right: EncodedRecord) -> bool {
    left.annotation_tag == right.annotation_tag
        && (left.annotation_tag == 0x80 || left.stable_id == right.stable_id)
}

fn format_tick(value: f64, step: f64, kind: ScaleKind) -> String {
    let magnitude = value.abs();
    if magnitude >= 1e6 || (magnitude != 0.0 && magnitude < 1e-4) {
        let mut text = format!("{value:.1e}");
        text = text
            .replace("e+0", "e")
            .replace("e-0", "e-")
            .replace("e+", "e");
        return text;
    }
    let mut decimals = if kind == ScaleKind::Log && magnitude > 0.0 && magnitude < 1.0 {
        (-magnitude.log10()).ceil().clamp(0.0, 8.0) as usize
    } else if step != 0.0 {
        (-step.abs().log10()).ceil().clamp(0.0, 8.0) as usize
    } else {
        0
    };
    while kind != ScaleKind::Log && decimals < 8 {
        let factor = 10_f64.powi(decimals as i32);
        let rounded = (step * factor).round() / factor;
        if (rounded - step).abs() <= step.abs() / 1000.0 {
            break;
        }
        decimals += 1;
    }
    format!("{value:.decimals$}")
}

fn push_svg_line(out: &mut String, x1: f64, y1: f64, x2: f64, y2: f64, paint: &str, width: f64) {
    out.push_str("<line x1=\"");
    push_num(out, x1);
    out.push_str("\" y1=\"");
    push_num(out, y1);
    out.push_str("\" x2=\"");
    push_num(out, x2);
    out.push_str("\" y2=\"");
    push_num(out, y2);
    out.push_str("\" stroke=\"");
    out.push_str(paint);
    out.push_str("\" stroke-width=\"");
    push_num(out, width);
    out.push_str("\"/>");
}

fn rgba_css(rgba: [u8; 4]) -> String {
    format!(
        "rgba({},{},{},{:.6})",
        rgba[0],
        rgba[1],
        rgba[2],
        f64::from(rgba[3]) / 255.0
    )
}

fn tick_span(direction: TickDirection, length: f64) -> (f64, f64) {
    match direction {
        TickDirection::Out => (0.0, length),
        TickDirection::In => (length, 0.0),
        TickDirection::InOut => (length * 0.5, length * 0.5),
    }
}

fn push_svg_chrome_text(out: &mut String, document: &SceneDocument) {
    let chrome = &document.chrome;
    let text = &document.text;
    let layout = &document.layout;
    if !text.title.is_empty() {
        out.push_str("<g data-xy-chrome=\"title\"><text x=\"");
        push_num(out, 0.5 * (layout.left + layout.right));
        out.push_str("\" y=\"");
        push_num(out, (layout.top * 0.55).max(chrome.label_font_size));
        out.push_str("\" fill=\"");
        out.push_str(&rgba_css(chrome.label_rgba));
        out.push_str("\" font-size=\"");
        push_num(out, chrome.label_font_size + 2.0);
        out.push_str("\" text-anchor=\"middle\">");
        push_escaped_attribute(out, &text.title);
        out.push_str("</text></g>");
    }
    if !text.x_label.is_empty() {
        out.push_str("<g data-xy-chrome=\"x-label\"><text x=\"");
        push_num(out, 0.5 * (layout.left + layout.right));
        out.push_str("\" y=\"");
        push_num(out, layout.viewport_height - 6.0);
        out.push_str("\" fill=\"");
        out.push_str(&rgba_css(chrome.x_axis.label_rgba));
        out.push_str("\" font-size=\"");
        push_num(out, chrome.label_font_size);
        out.push_str("\" text-anchor=\"middle\">");
        push_escaped_attribute(out, &text.x_label);
        out.push_str("</text></g>");
    }
    if !text.y_label.is_empty() {
        let x = (layout.left * 0.35).max(chrome.label_font_size);
        let y = 0.5 * (layout.top + layout.bottom);
        out.push_str("<g data-xy-chrome=\"y-label\"><text x=\"");
        push_num(out, x);
        out.push_str("\" y=\"");
        push_num(out, y);
        out.push_str("\" fill=\"");
        out.push_str(&rgba_css(chrome.y_axis.label_rgba));
        out.push_str("\" font-size=\"");
        push_num(out, chrome.label_font_size);
        out.push_str("\" text-anchor=\"middle\" transform=\"rotate(-90 ");
        push_num(out, x);
        out.push(' ');
        push_num(out, y);
        out.push_str(")\">");
        push_escaped_attribute(out, &text.y_label);
        out.push_str("</text></g>");
    }
}

/// Validated, owned Scene v9 document consumed identically by vector and
/// raster export. Hosts never reinterpret record geometry after encoding.
pub struct SceneDocument {
    layout: PlotLayout,
    x_scale: AxisScale,
    y_scale: AxisScale,
    chrome: SceneChromeStyle,
    text: SceneChromeText,
    legend: Option<SceneLegend>,
    colorbar: Option<SceneColorbar>,
    labels: Vec<SceneLabel>,
    styles: Vec<EncodedStyle>,
    records: Vec<EncodedRecord>,
    raster_mark_capacity: usize,
}

impl SceneDocument {
    /// Add bounded XYAT decorations to an already validated canonical Scene.
    ///
    /// The Scene remains the source of its layout and scales: the envelope
    /// carries data coordinates only, which are projected here before any
    /// browser consumer observes them.
    pub fn with_authored_annotations(mut self, bytes: &[u8]) -> Result<Self, SceneError> {
        let existing = self.labels.len();
        let mut labels = decode_annotation_envelope(bytes, &self)?;
        if existing
            .checked_add(labels.len())
            .ok_or(SceneError::Limit)?
            > MAX_SCENE_LABELS
        {
            return Err(SceneError::Limit);
        }
        for (index, label) in labels.iter_mut().enumerate() {
            label.stable_id = 0x5859_0400_0000_0000 | (existing + index) as u64;
        }
        self.labels.append(&mut labels);
        Ok(self)
    }

    fn painter_colorbar_bytes(&self) -> Result<Vec<u8>, SceneError> {
        let Some(colorbar) = &self.colorbar else {
            return Ok(Vec::new());
        };
        let mut out = colorbar.encode()?;
        let (x, y, width, height) = resolved_colorbar_bounds(self.layout, colorbar)?;
        out.extend_from_slice(b"XYRG");
        out.extend_from_slice(&1u32.to_le_bytes());
        for value in [x, y, width, height] {
            out.extend_from_slice(&checked_f32(value)?.to_le_bytes());
        }
        Ok(out)
    }
    fn painter_legend_bytes(&self) -> Result<Vec<u8>, SceneError> {
        let Some(legend) = &self.legend else {
            return Ok(Vec::new());
        };
        let mut out = legend.encode();
        let (x, y, width, height) = self.legend_bounds(legend)?;
        out.extend_from_slice(b"XYRG");
        out.extend_from_slice(&1u32.to_le_bytes());
        for value in [x, y, width, height] {
            out.extend_from_slice(&checked_f32(value)?.to_le_bytes());
        }
        let mut row_y = y + 8.0;
        let title_baseline = if legend.title.is_empty() {
            0.0
        } else {
            row_y += legend.title_font_size;
            let value = row_y;
            row_y += 6.0;
            value
        };
        out.extend_from_slice(&checked_f32(x + 8.0)?.to_le_bytes());
        out.extend_from_slice(&checked_f32(title_baseline)?.to_le_bytes());
        let mut paths = Vec::new();
        for entry in &legend.entries {
            row_y += legend.font_size;
            let swatch_y = row_y - legend.font_size * 0.35;
            let style = self.styles[entry.style_ref];
            let (primitive, fill_none, x0, y0, x1, y1) = match entry.kind {
                SceneRecordKind::Polyline => (0u32, true, x + 8.0, swatch_y, x + 28.0, swatch_y),
                SceneRecordKind::Scatter => {
                    let symbol = ScatterSymbol::from_code(entry.symbol);
                    let radius = MarkerGeometry::new(symbol, 8.0, style.stroke_width).radius;
                    if matches!(symbol, ScatterSymbol::Square | ScatterSymbol::Pixel) {
                        (
                            1u32,
                            false,
                            x + 18.0 - radius,
                            swatch_y - radius,
                            radius * 2.0,
                            radius * 2.0,
                        )
                    } else if matches!(symbol, ScatterSymbol::Circle | ScatterSymbol::Point) {
                        (2u32, false, x + 18.0, swatch_y, radius, 0.0)
                    } else {
                        (3u32, symbol.is_line(), x + 18.0, swatch_y, radius, 0.0)
                    }
                }
                _ => (1u32, false, x + 10.0, swatch_y - 4.0, 16.0, 8.0),
            };
            for value in [x + 34.0, row_y, x0, y0, x1, y1] {
                out.extend_from_slice(&checked_f32(value)?.to_le_bytes());
            }
            out.extend_from_slice(&primitive.to_le_bytes());
            out.extend_from_slice(&u32::from(fill_none).to_le_bytes());
            out.extend_from_slice(&checked_f32(style.stroke_width.max(1.0))?.to_le_bytes());
            let path = if entry.kind == SceneRecordKind::Scatter {
                let mut element = String::new();
                push_symbol(
                    &mut element,
                    ScatterSymbol::from_code(entry.symbol),
                    x + 18.0,
                    swatch_y,
                    MarkerGeometry::new(
                        ScatterSymbol::from_code(entry.symbol),
                        8.0,
                        style.stroke_width,
                    )
                    .radius,
                );
                element
                    .split_once(" d=\"")
                    .and_then(|(_, rest)| rest.split_once('"'))
                    .map(|(path, _)| path.as_bytes().to_vec())
                    .unwrap_or_default()
            } else {
                Vec::new()
            };
            if path.len() > MAX_BROWSER_LEGEND_PATH_BYTES {
                return Err(SceneError::Limit);
            }
            out.extend_from_slice(&(path.len() as u32).to_le_bytes());
            paths.push(path);
            row_y += 6.0;
        }
        for path in paths {
            out.extend_from_slice(&path);
        }
        Ok(out)
    }

    pub fn decode(bytes: &[u8]) -> Result<Self, SceneError> {
        if bytes.len() < SCENE_BATCH_HEADER_BYTES || &bytes[..4] != b"XYGS" {
            return Err(SceneError::Length);
        }
        let u32_at = |offset| {
            u32::from_le_bytes(
                bytes[offset..offset + 4]
                    .try_into()
                    .expect("bounded header"),
            )
        };
        let u64_at = |offset| {
            u64::from_le_bytes(
                bytes[offset..offset + 8]
                    .try_into()
                    .expect("bounded header"),
            )
        };
        let f64_at = |offset| {
            f64::from_le_bytes(
                bytes[offset..offset + 8]
                    .try_into()
                    .expect("bounded header"),
            )
        };
        if u32_at(4) != SCENE_VERSION {
            return Err(SceneError::Version);
        }
        if u32_at(8) as usize != SCENE_BATCH_HEADER_BYTES
            || u32_at(12) as usize != SCENE_BATCH_RECORD_BYTES
        {
            return Err(SceneError::Length);
        }
        let record_count = usize::try_from(u64_at(16)).map_err(|_| SceneError::Limit)?;
        let style_count = usize::try_from(u64_at(24)).map_err(|_| SceneError::Limit)?;
        if record_count > MAX_SCENE_MARKS || style_count > MAX_SCENE_STYLES {
            return Err(SceneError::Limit);
        }
        let body = SCENE_BATCH_HEADER_BYTES
            .checked_add(
                style_count
                    .checked_mul(SCENE_STYLE_RECORD_BYTES)
                    .ok_or(SceneError::Limit)?,
            )
            .and_then(|value| {
                value.checked_add(record_count.checked_mul(SCENE_BATCH_RECORD_BYTES)?)
            })
            .ok_or(SceneError::Limit)?;
        let (chrome, text, legend, colorbar, labels, total) = read_chrome_trailer(bytes, body)?;
        if bytes.len() != total {
            return Err(SceneError::Length);
        }
        let viewport_width = f64_at(32);
        let viewport_height = f64_at(40);
        let left = f64_at(48);
        let top = f64_at(56);
        let right = f64_at(64);
        let bottom = f64_at(72);
        let layout = PlotLayout::new(
            viewport_width,
            viewport_height,
            left,
            viewport_width - right,
            top,
            viewport_height - bottom,
        )?;
        if labels.iter().any(|label| {
            label.x < 0.0
                || label.x > layout.viewport_width
                || label.y < 0.0
                || label.y > layout.viewport_height
        }) {
            return Err(SceneError::Length);
        }
        if let Some(value) = &legend {
            resolved_legend_bounds(layout, value)?;
        }
        if let Some(value) = &colorbar {
            resolved_colorbar_bounds(layout, value)?;
        }
        if bytes[96] > ScaleKind::SymLog as u8
            || bytes[104] > ScaleKind::SymLog as u8
            || !matches!(bytes[97], 0 | 1)
            || !matches!(bytes[105], 0 | 1)
            || bytes[98..104] != [0; 6]
            || bytes[106..112] != [0; 6]
            || (112..160)
                .step_by(8)
                .any(|offset| !f64_at(offset).is_finite())
            || f64_at(144) <= 0.0
            || f64_at(152) <= 0.0
        {
            return Err(SceneError::NonFinite);
        }
        let scale_kind = |code| match code {
            0 => Ok(ScaleKind::Linear),
            1 => Ok(ScaleKind::Log),
            2 => Ok(ScaleKind::SymLog),
            _ => Err(SceneError::Length),
        };
        let x_kind = scale_kind(bytes[96])?;
        let y_kind = scale_kind(bytes[104])?;
        let x_scale = AxisScale::new(
            x_kind,
            AxisScale {
                kind: x_kind,
                px0: layout.left,
                coord_lo: f64_at(112),
                coord_span: f64_at(120) - f64_at(112),
                px_delta: layout.right - layout.left,
                constant: f64_at(144),
                mask_nonpositive: bytes[97] == 1,
            }
            .value(f64_at(112)),
            AxisScale {
                kind: x_kind,
                px0: layout.left,
                coord_lo: f64_at(112),
                coord_span: f64_at(120) - f64_at(112),
                px_delta: layout.right - layout.left,
                constant: f64_at(144),
                mask_nonpositive: bytes[97] == 1,
            }
            .value(f64_at(120)),
            layout.left,
            layout.right,
            f64_at(144),
            bytes[97] == 1,
        )?;
        let y_scale = AxisScale::new(
            y_kind,
            AxisScale {
                kind: y_kind,
                px0: layout.bottom,
                coord_lo: f64_at(128),
                coord_span: f64_at(136) - f64_at(128),
                px_delta: layout.top - layout.bottom,
                constant: f64_at(152),
                mask_nonpositive: bytes[105] == 1,
            }
            .value(f64_at(128)),
            AxisScale {
                kind: y_kind,
                px0: layout.bottom,
                coord_lo: f64_at(128),
                coord_span: f64_at(136) - f64_at(128),
                px_delta: layout.top - layout.bottom,
                constant: f64_at(152),
                mask_nonpositive: bytes[105] == 1,
            }
            .value(f64_at(136)),
            layout.bottom,
            layout.top,
            f64_at(152),
            bytes[105] == 1,
        )?;
        let mut styles = Vec::with_capacity(style_count);
        let mut offset = SCENE_BATCH_HEADER_BYTES;
        for _ in 0..style_count {
            let stroke_width = f64::from_le_bytes(
                bytes[offset + 8..offset + 16]
                    .try_into()
                    .expect("bounded style"),
            );
            if !stroke_width.is_finite() || stroke_width < 0.0 {
                return Err(SceneError::NonFinite);
            }
            styles.push(EncodedStyle {
                fill: bytes[offset..offset + 4].try_into().expect("bounded style"),
                stroke: bytes[offset + 4..offset + 8]
                    .try_into()
                    .expect("bounded style"),
                stroke_width,
            });
            offset += SCENE_STYLE_RECORD_BYTES;
        }
        if legend.as_ref().is_some_and(|value| {
            value.entries.iter().any(|entry| {
                entry.style_ref >= styles.len()
                    || entry.fill_rgba != styles[entry.style_ref].fill
                    || entry.stroke_rgba != styles[entry.style_ref].stroke
            })
        }) {
            return Err(SceneError::Length);
        }
        let mut records = Vec::with_capacity(record_count);
        let mut raster_mark_capacity = 0usize;
        for _ in 0..record_count {
            let kind = SceneRecordKind::from_code(bytes[offset])?;
            let visible = match bytes[offset + 1] {
                0 => false,
                1 => true,
                _ => return Err(SceneError::Length),
            };
            let symbol = bytes[offset + 2];
            let annotation_tag = bytes[offset + 3];
            if !matches!(annotation_tag, 0..=4 | 0x80)
                || (kind == SceneRecordKind::Scatter && symbol > ScatterSymbol::VerticalLine as u8)
                || (kind != SceneRecordKind::Scatter && symbol != 0)
            {
                return Err(SceneError::Length);
            }
            let style_ref = u32::from_le_bytes(
                bytes[offset + 4..offset + 8]
                    .try_into()
                    .expect("bounded record"),
            ) as usize;
            if style_ref >= styles.len() {
                return Err(SceneError::Length);
            }
            let stable_id = u64::from_le_bytes(
                bytes[offset + 8..offset + 16]
                    .try_into()
                    .expect("bounded record"),
            );
            let mut coordinates = [0.0; 4];
            for (index, value) in coordinates.iter_mut().enumerate() {
                *value = f64::from_le_bytes(
                    bytes[offset + 16 + index * 8..offset + 24 + index * 8]
                        .try_into()
                        .expect("bounded record"),
                );
            }
            let diameter = f64::from_le_bytes(
                bytes[offset + 48..offset + 56]
                    .try_into()
                    .expect("bounded record"),
            );
            if coordinates.iter().any(|value| !value.is_finite())
                || !diameter.is_finite()
                || diameter < 0.0
                || (kind != SceneRecordKind::Scatter && diameter != 0.0)
                || (matches!(
                    kind,
                    SceneRecordKind::Scatter
                        | SceneRecordKind::Polyline
                        | SceneRecordKind::PolyFill
                ) && coordinates[2..] != [0.0, 0.0])
                || (visible
                    && kind == SceneRecordKind::Rect
                    && (coordinates[0] > coordinates[2] || coordinates[1] > coordinates[3]))
                || (!visible && coordinates != [0.0; 4])
            {
                return Err(SceneError::NonFinite);
            }
            if visible {
                let record_capacity = match kind {
                    SceneRecordKind::Scatter => 26,
                    SceneRecordKind::Polyline => 27,
                    SceneRecordKind::Rect => {
                        41 + if styles[style_ref].stroke_width > 0.0 {
                            51
                        } else {
                            0
                        }
                    }
                    // Worst-case per-sample share of a closed Band fill (and optional
                    // stroke): a two-sample run emits 41 fill bytes, so reserve 21 each.
                    SceneRecordKind::Band => {
                        21 + if styles[style_ref].stroke_width > 0.0 {
                            26
                        } else {
                            0
                        }
                    }
                    // Three-vertex fill is 33 bytes; reserve 11 per vertex (+stroke share).
                    SceneRecordKind::PolyFill => {
                        11 + if styles[style_ref].stroke_width > 0.0 {
                            18
                        } else {
                            0
                        }
                    }
                };
                raster_mark_capacity = raster_mark_capacity.saturating_add(record_capacity);
            }
            records.push(EncodedRecord {
                kind,
                visible,
                symbol,
                style_ref,
                stable_id,
                coordinates,
                diameter,
                annotation_tag,
            });
            offset += SCENE_BATCH_RECORD_BYTES;
        }
        let mut annotation_cursor = 0;
        let mut annotations_started = false;
        while annotation_cursor < records.len() {
            let record = records[annotation_cursor];
            if record.annotation_tag == 0 || record.annotation_tag == 0x80 {
                if annotations_started {
                    return Err(SceneError::Length);
                }
                annotation_cursor += 1;
                continue;
            }
            annotations_started = true;
            let tag = record.annotation_tag;
            let run_end = records[annotation_cursor + 1..]
                .iter()
                .position(|candidate| {
                    candidate.annotation_tag != tag || candidate.stable_id != record.stable_id
                })
                .map_or(records.len(), |value| annotation_cursor + 1 + value);
            match tag {
                1 if record.kind == SceneRecordKind::Polyline
                    && run_end - annotation_cursor == 2 =>
                {
                    let next = records[annotation_cursor + 1];
                    if next.kind != SceneRecordKind::Polyline
                        || record.style_ref != next.style_ref
                        || record.visible != next.visible
                        || (record.visible
                            && !((record.coordinates[0] == next.coordinates[0])
                                ^ (record.coordinates[1] == next.coordinates[1])))
                    {
                        return Err(SceneError::Length);
                    }
                }
                2 if record.kind == SceneRecordKind::Rect && run_end - annotation_cursor == 1 => {
                    if record.visible
                        && (!scene_edge_eq(record.coordinates[1], layout.top)
                            || !scene_edge_eq(record.coordinates[3], layout.bottom))
                    {
                        return Err(SceneError::Length);
                    }
                }
                3 if record.kind == SceneRecordKind::Scatter
                    && run_end - annotation_cursor == 1 => {}
                4 if record.kind == SceneRecordKind::Rect && run_end - annotation_cursor == 1 => {
                    if record.visible
                        && (!scene_edge_eq(record.coordinates[0], layout.left)
                            || !scene_edge_eq(record.coordinates[2], layout.right))
                    {
                        return Err(SceneError::Length);
                    }
                }
                _ => return Err(SceneError::Length),
            }
            annotation_cursor = run_end;
        }
        Ok(Self {
            layout,
            x_scale,
            y_scale,
            chrome,
            text,
            legend,
            colorbar,
            labels,
            styles,
            records,
            raster_mark_capacity,
        })
    }

    pub fn record_count(&self) -> usize {
        self.records.len()
    }

    pub fn style_count(&self) -> usize {
        self.styles.len()
    }

    fn resolved_axis_ticks(&self, is_x: bool) -> Result<AxisTicks, SceneError> {
        let (scale, length, pixel_min, pixel_max, authored_major, authored_minor) = if is_x {
            (
                self.x_scale,
                self.layout.right - self.layout.left,
                self.layout.left,
                self.layout.right,
                self.chrome.x_major_ticks.as_deref(),
                self.chrome.x_minor_ticks.as_slice(),
            )
        } else {
            (
                self.y_scale,
                self.layout.bottom - self.layout.top,
                self.layout.top,
                self.layout.bottom,
                self.chrome.y_major_ticks.as_deref(),
                self.chrome.y_minor_ticks.as_slice(),
            )
        };
        resolved_axis_ticks(
            scale,
            length,
            is_x,
            pixel_min,
            pixel_max,
            authored_major,
            authored_minor,
        )
    }

    fn minor_ticks(ticks: &AxisTicks) -> impl Iterator<Item = f64> + '_ {
        ticks
            .ticks
            .iter()
            .copied()
            .filter(|value| !ticks.labeled.contains(value))
    }

    fn axis_tick_label(&self, is_x: bool, index: usize, value: f64, ticks: &AxisTicks) -> String {
        let authored = if is_x {
            self.chrome.x_tick_labels.as_deref()
        } else {
            self.chrome.y_tick_labels.as_deref()
        };
        let authored_ticks = if is_x {
            self.chrome.x_major_ticks.as_deref()
        } else {
            self.chrome.y_major_ticks.as_deref()
        };
        if let (Some(labels), Some(values)) = (authored, authored_ticks) {
            // `index` is only the resolved/final labelled-tick index; never
            // use it as an authored-table index because off-domain major
            // positions are intentionally filtered by Rust.
            return values
                .iter()
                .position(|candidate| *candidate == value)
                .and_then(|position| labels.get(position))
                .cloned()
                .unwrap_or_default();
        }
        let _ = index;
        format_tick(
            value,
            ticks.step,
            if is_x {
                self.x_scale.kind
            } else {
                self.y_scale.kind
            },
        )
    }

    fn legend_bounds(&self, legend: &SceneLegend) -> Result<(f64, f64, f64, f64), SceneError> {
        resolved_legend_bounds(self.layout, legend)
    }

    fn append_svg_legend(&self, out: &mut String) {
        let Some(legend) = &self.legend else {
            return;
        };
        let (x, y, width, height) = self.legend_bounds(legend).expect("validated legend fit");
        out.push_str("<g data-xy-chrome=\"legend\" role=\"list\"><rect x=\"");
        push_num(out, x);
        out.push_str("\" y=\"");
        push_num(out, y);
        out.push_str("\" width=\"");
        push_num(out, width);
        out.push_str("\" height=\"");
        push_num(out, height);
        out.push_str("\" fill=\"");
        out.push_str(&rgba_css(legend.frame_fill_rgba));
        out.push_str("\" stroke=\"");
        out.push_str(&rgba_css(legend.frame_stroke_rgba));
        out.push_str("\"/>");
        let mut row_y = y + 8.0;
        if !legend.title.is_empty() {
            row_y += legend.title_font_size;
            out.push_str("<text data-xy-slot=\"legend_title\" x=\"");
            push_num(out, x + 8.0);
            out.push_str("\" y=\"");
            push_num(out, row_y);
            out.push_str("\" fill=\"");
            out.push_str(&rgba_css(legend.text_rgba));
            out.push_str("\" font-size=\"");
            push_num(out, legend.title_font_size);
            out.push_str("\">");
            push_escaped_attribute(out, &legend.title);
            out.push_str("</text>");
            row_y += 6.0;
        }
        for entry in &legend.entries {
            row_y += legend.font_size;
            let style = self.styles[entry.style_ref];
            let swatch_y = row_y - legend.font_size * 0.35;
            match entry.kind {
                SceneRecordKind::Polyline => push_svg_line(
                    out,
                    x + 8.0,
                    swatch_y,
                    x + 28.0,
                    swatch_y,
                    &rgba_css(style.stroke),
                    style.stroke_width.max(1.0),
                ),
                SceneRecordKind::Scatter => {
                    let symbol = ScatterSymbol::from_code(entry.symbol);
                    let geometry = MarkerGeometry::new(symbol, 8.0, style.stroke_width);
                    push_symbol(out, symbol, x + 18.0, swatch_y, geometry.radius);
                    if symbol.is_line() {
                        out.push_str(" fill=\"none\"");
                    } else {
                        push_paint(out, "fill", style.fill, None);
                    }
                    if geometry.stroke_width > 0.0 || symbol.is_line() {
                        push_paint(out, "stroke", style.stroke, None);
                        out.push_str(" stroke-width=\"");
                        push_num(out, geometry.stroke_width);
                        out.push('"');
                    }
                    out.push_str("/>");
                }
                _ => {
                    out.push_str("<rect x=\"");
                    push_num(out, x + 10.0);
                    out.push_str("\" y=\"");
                    push_num(out, swatch_y - 4.0);
                    out.push_str("\" width=\"16\" height=\"8\" fill=\"");
                    out.push_str(&rgba_css(style.fill));
                    out.push_str("\"/>");
                }
            }
            out.push_str("<text data-xy-slot=\"legend_label\" role=\"listitem\" x=\"");
            push_num(out, x + 34.0);
            out.push_str("\" y=\"");
            push_num(out, row_y);
            out.push_str("\" fill=\"");
            out.push_str(&rgba_css(legend.text_rgba));
            out.push_str("\" font-size=\"");
            push_num(out, legend.font_size);
            out.push_str("\">");
            push_escaped_attribute(out, &entry.label);
            out.push_str("</text>");
            row_y += 6.0;
        }
        out.push_str("</g>");
    }

    fn append_svg_colorbar(&self, out: &mut String) {
        let Some(colorbar) = &self.colorbar else {
            return;
        };
        let (x, y, width, height) =
            resolved_colorbar_bounds(self.layout, colorbar).expect("validated colorbar fit");
        out.push_str("<g data-xy-chrome=\"colorbar\" role=\"img\" aria-label=\"Color scale");
        if !colorbar.title.is_empty() {
            out.push_str(": ");
            push_escaped_attribute(out, &colorbar.title);
        }
        out.push_str("\">");
        for index in 0..colorbar.stops.len() - 1 {
            let (lo, paint) = colorbar.stops[index];
            let (hi, _) = colorbar.stops[index + 1];
            let fraction = (lo - colorbar.domain[0]) / (colorbar.domain[1] - colorbar.domain[0]);
            let next = (hi - colorbar.domain[0]) / (colorbar.domain[1] - colorbar.domain[0]);
            let (rx, ry, rw, rh) = if colorbar.horizontal {
                (x + width * fraction, y, width * (next - fraction), height)
            } else {
                (
                    x,
                    y + height * (1.0 - next),
                    width,
                    height * (next - fraction),
                )
            };
            out.push_str("<rect data-xy-slot=\"colorbar_band\" x=\"");
            push_num(out, rx);
            out.push_str("\" y=\"");
            push_num(out, ry);
            out.push_str("\" width=\"");
            push_num(out, rw);
            out.push_str("\" height=\"");
            push_num(out, rh);
            out.push_str("\" fill=\"");
            out.push_str(&rgba_css(paint));
            out.push_str("\"/>");
        }
        if !colorbar.title.is_empty() {
            out.push_str("<text data-xy-slot=\"colorbar_title\" x=\"");
            push_num(out, x);
            out.push_str("\" y=\"");
            push_num(
                out,
                if colorbar.horizontal {
                    y + height + 14.0
                } else {
                    y - 6.0
                },
            );
            out.push_str("\" fill=\"");
            out.push_str(&rgba_css(colorbar.text_rgba));
            out.push_str("\" font-size=\"11\">");
            push_escaped_attribute(out, &colorbar.title);
            out.push_str("</text>");
        }
        out.push_str("</g>");
    }

    fn append_svg_labels(&self, out: &mut String) {
        if self.labels.is_empty() {
            return;
        }
        out.push_str(
            "<g data-xy-chrome=\"graph_labels\" role=\"list\" aria-label=\"Graph labels\">",
        );
        for label in &self.labels {
            out.push_str("<text data-xy-slot=\"graph_label\" data-xy-stable-id=\"");
            out.push_str(&label.stable_id.to_string());
            out.push_str("\" role=\"listitem\" x=\"");
            push_num(out, label.x);
            out.push_str("\" y=\"");
            push_num(out, label.y);
            out.push_str("\" fill=\"");
            out.push_str(&rgba_css(label.rgba));
            out.push_str("\" font-size=\"");
            push_num(out, label.font_size);
            out.push_str("\">");
            push_escaped_attribute(out, &label.text);
            out.push_str("</text>");
        }
        out.push_str("</g>");
    }

    fn append_svg_grid(&self, out: &mut String, x_ticks: &AxisTicks, y_ticks: &AxisTicks) {
        for (ticks, scale, style, is_x) in [
            (x_ticks, self.x_scale, self.chrome.x_axis, true),
            (y_ticks, self.y_scale, self.chrome.y_axis, false),
        ] {
            if SceneAxisChromeStyle::visible_stroke(style.grid_rgba, style.grid_width) {
                for value in &ticks.labeled {
                    let p = scale.pixel(*value);
                    let (x1, y1, x2, y2) = if is_x {
                        (p, self.layout.top, p, self.layout.bottom)
                    } else {
                        (self.layout.left, p, self.layout.right, p)
                    };
                    push_svg_line(
                        out,
                        x1,
                        y1,
                        x2,
                        y2,
                        &rgba_css(style.grid_rgba),
                        style.grid_width,
                    );
                }
            }
            if SceneAxisChromeStyle::visible_stroke(style.minor_grid_rgba, style.minor_grid_width) {
                for value in Self::minor_ticks(ticks) {
                    let p = scale.pixel(value);
                    let (x1, y1, x2, y2) = if is_x {
                        (p, self.layout.top, p, self.layout.bottom)
                    } else {
                        (self.layout.left, p, self.layout.right, p)
                    };
                    push_svg_line(
                        out,
                        x1,
                        y1,
                        x2,
                        y2,
                        &rgba_css(style.minor_grid_rgba),
                        style.minor_grid_width,
                    );
                }
            }
        }
    }

    pub fn to_svg(&self) -> String {
        let mut out = String::with_capacity(self.records.len().saturating_mul(96));
        out.push_str("<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"");
        push_num(&mut out, self.layout.viewport_width);
        out.push_str("\" height=\"");
        push_num(&mut out, self.layout.viewport_height);
        out.push_str("\" viewBox=\"0 0 ");
        push_num(&mut out, self.layout.viewport_width);
        out.push(' ');
        push_num(&mut out, self.layout.viewport_height);
        out.push_str("\"><defs><clipPath id=\"xy-scene-plot\"><rect x=\"");
        push_num(&mut out, self.layout.left);
        out.push_str("\" y=\"");
        push_num(&mut out, self.layout.top);
        out.push_str("\" width=\"");
        push_num(&mut out, self.layout.right - self.layout.left);
        out.push_str("\" height=\"");
        push_num(&mut out, self.layout.bottom - self.layout.top);
        out.push_str("\"/></clipPath></defs>");
        for (kind, x, y, width, height, paint) in [
            (
                "chart-background",
                0.0,
                0.0,
                self.layout.viewport_width,
                self.layout.viewport_height,
                self.chrome.chart_background_rgba,
            ),
            (
                "plot-background",
                self.layout.left,
                self.layout.top,
                self.layout.right - self.layout.left,
                self.layout.bottom - self.layout.top,
                self.chrome.plot_background_rgba,
            ),
        ] {
            out.push_str("<rect data-xy-chrome=\"");
            out.push_str(kind);
            out.push_str("\" x=\"");
            push_num(&mut out, x);
            out.push_str("\" y=\"");
            push_num(&mut out, y);
            out.push_str("\" width=\"");
            push_num(&mut out, width);
            out.push_str("\" height=\"");
            push_num(&mut out, height);
            out.push_str("\" fill=\"");
            out.push_str(&rgba_css(paint));
            out.push_str("\"/>");
        }
        let x_ticks = self.resolved_axis_ticks(true).unwrap_or(AxisTicks {
            ticks: Vec::new(),
            labeled: Vec::new(),
            step: 1.0,
        });
        let y_ticks = self.resolved_axis_ticks(false).unwrap_or(AxisTicks {
            ticks: Vec::new(),
            labeled: Vec::new(),
            step: 1.0,
        });
        if self.chrome.x_axis.has_visible_grid() || self.chrome.y_axis.has_visible_grid() {
            out.push_str("<g data-xy-chrome=\"grid\">");
            self.append_svg_grid(&mut out, &x_ticks, &y_ticks);
            out.push_str("</g>");
        }
        out.push_str("<g clip-path=\"url(#xy-scene-plot)\">");
        let mut index = 0;
        while index < self.records.len() {
            let record = self.records[index];
            if !record.visible {
                index += 1;
                continue;
            }
            let style = self.styles[record.style_ref];
            match record.kind {
                SceneRecordKind::Scatter => {
                    let symbol = ScatterSymbol::from_code(record.symbol);
                    let geometry = MarkerGeometry::new(symbol, record.diameter, style.stroke_width);
                    push_symbol(
                        &mut out,
                        symbol,
                        record.coordinates[0],
                        record.coordinates[1],
                        geometry.radius,
                    );
                    if symbol.is_line() {
                        out.push_str(" fill=\"none\"");
                    } else {
                        push_paint(&mut out, "fill", style.fill, None);
                    }
                    if geometry.stroke_width > 0.0 || symbol.is_line() {
                        push_paint(&mut out, "stroke", style.stroke, None);
                        out.push_str(" stroke-width=\"");
                        push_num(&mut out, geometry.stroke_width);
                        out.push('"');
                    }
                    out.push_str("/>");
                    index += 1;
                }
                SceneRecordKind::Rect => {
                    out.push_str("<rect x=\"");
                    push_num(&mut out, record.coordinates[0]);
                    out.push_str("\" y=\"");
                    push_num(&mut out, record.coordinates[1]);
                    out.push_str("\" width=\"");
                    push_num(&mut out, record.coordinates[2] - record.coordinates[0]);
                    out.push_str("\" height=\"");
                    push_num(&mut out, record.coordinates[3] - record.coordinates[1]);
                    out.push('"');
                    push_paint(&mut out, "fill", style.fill, None);
                    if style.stroke_width > 0.0 {
                        push_paint(&mut out, "stroke", style.stroke, None);
                        out.push_str(" stroke-width=\"");
                        push_num(&mut out, style.stroke_width);
                        out.push('"');
                    }
                    out.push_str("/>");
                    index += 1;
                }
                SceneRecordKind::Band => {
                    let style_ref = record.style_ref;
                    let start = index;
                    while index < self.records.len() {
                        let point = self.records[index];
                        if point.kind != SceneRecordKind::Band
                            || !same_record_run(record, point)
                            || point.style_ref != style_ref
                            || !point.visible
                        {
                            break;
                        }
                        index += 1;
                    }
                    let run = &self.records[start..index];
                    if run.len() >= 2 {
                        out.push_str("<path d=\"M ");
                        push_num(&mut out, run[0].coordinates[0]);
                        out.push(' ');
                        push_num(&mut out, run[0].coordinates[1]);
                        for point in &run[1..] {
                            out.push_str(" L ");
                            push_num(&mut out, point.coordinates[0]);
                            out.push(' ');
                            push_num(&mut out, point.coordinates[1]);
                        }
                        for point in run.iter().rev() {
                            out.push_str(" L ");
                            push_num(&mut out, point.coordinates[2]);
                            out.push(' ');
                            push_num(&mut out, point.coordinates[3]);
                        }
                        out.push_str(" Z\"");
                        push_paint(&mut out, "fill", style.fill, None);
                        if style.stroke_width > 0.0 {
                            push_paint(&mut out, "stroke", style.stroke, None);
                            out.push_str(" stroke-width=\"");
                            push_num(&mut out, style.stroke_width);
                            out.push('"');
                        } else {
                            out.push_str(" stroke=\"none\"");
                        }
                        out.push_str("/>");
                    }
                }
                SceneRecordKind::PolyFill => {
                    let style_ref = record.style_ref;
                    let start = index;
                    while index < self.records.len() {
                        let point = self.records[index];
                        if point.kind != SceneRecordKind::PolyFill
                            || !same_record_run(record, point)
                            || point.style_ref != style_ref
                            || !point.visible
                        {
                            break;
                        }
                        index += 1;
                    }
                    let run = &self.records[start..index];
                    if run.len() >= 3 {
                        out.push_str("<path d=\"M ");
                        push_num(&mut out, run[0].coordinates[0]);
                        out.push(' ');
                        push_num(&mut out, run[0].coordinates[1]);
                        for point in &run[1..] {
                            out.push_str(" L ");
                            push_num(&mut out, point.coordinates[0]);
                            out.push(' ');
                            push_num(&mut out, point.coordinates[1]);
                        }
                        out.push_str(" Z\"");
                        push_paint(&mut out, "fill", style.fill, None);
                        if style.stroke_width > 0.0 {
                            push_paint(&mut out, "stroke", style.stroke, None);
                            out.push_str(" stroke-width=\"");
                            push_num(&mut out, style.stroke_width);
                            out.push('"');
                        } else {
                            out.push_str(" stroke=\"none\"");
                        }
                        out.push_str("/>");
                    }
                }
                SceneRecordKind::Polyline => {
                    out.push_str("<polyline points=\"");
                    let style_ref = record.style_ref;
                    while index < self.records.len() {
                        let point = self.records[index];
                        if point.kind != SceneRecordKind::Polyline
                            || !same_record_run(record, point)
                            || point.style_ref != style_ref
                            || !point.visible
                        {
                            break;
                        }
                        if index > 0 {
                            out.push(' ');
                        }
                        push_num(&mut out, point.coordinates[0]);
                        out.push(',');
                        push_num(&mut out, point.coordinates[1]);
                        index += 1;
                    }
                    out.push_str("\" fill=\"none\"");
                    push_paint(&mut out, "stroke", style.stroke, None);
                    out.push_str(" stroke-width=\"");
                    push_num(&mut out, style.stroke_width);
                    out.push_str("\" stroke-linecap=\"round\" stroke-linejoin=\"round\"/>");
                }
            }
        }
        out.push_str("</g>");
        if self.chrome.x_axis.has_visible_axis() || self.chrome.y_axis.has_visible_axis() {
            out.push_str("<g data-xy-chrome=\"axes\">");
            for (is_x, ticks, scale, style) in [
                (true, &x_ticks, self.x_scale, self.chrome.x_axis),
                (false, &y_ticks, self.y_scale, self.chrome.y_axis),
            ] {
                let (major_in, major_out) = tick_span(style.major_direction, style.tick_length);
                let (minor_in, minor_out) =
                    tick_span(style.minor_direction, style.minor_tick_length);
                for side_code in 0..2 {
                    if style.tick_sides & (1 << side_code) != 0
                        && style.tick_length > 0.0
                        && SceneAxisChromeStyle::visible_stroke(style.tick_rgba, style.tick_width)
                    {
                        for value in &ticks.labeled {
                            let p = scale.pixel(*value);
                            let edge = if is_x {
                                if side_code == 0 {
                                    self.layout.bottom
                                } else {
                                    self.layout.top
                                }
                            } else if side_code == 0 {
                                self.layout.left
                            } else {
                                self.layout.right
                            };
                            let sign = if side_code == 0 { 1.0 } else { -1.0 };
                            let (x1, y1, x2, y2) = if is_x {
                                (p, edge - sign * major_in, p, edge + sign * major_out)
                            } else {
                                (edge - sign * major_out, p, edge + sign * major_in, p)
                            };
                            push_svg_line(
                                &mut out,
                                x1,
                                y1,
                                x2,
                                y2,
                                &rgba_css(style.tick_rgba),
                                style.tick_width,
                            );
                        }
                    }
                    if style.tick_label_sides & (1 << side_code) != 0 && style.label_rgba[3] != 0 {
                        for (label_index, value) in ticks.labeled.iter().enumerate() {
                            let p = scale.pixel(*value);
                            let edge = if is_x {
                                if side_code == 0 {
                                    self.layout.bottom + 16.0
                                } else {
                                    self.layout.top - 7.0
                                }
                            } else if side_code == 0 {
                                self.layout.left - 8.0
                            } else {
                                self.layout.right + 8.0
                            };
                            out.push_str("<text x=\"");
                            push_num(&mut out, if is_x { p } else { edge });
                            out.push_str("\" y=\"");
                            push_num(&mut out, if is_x { edge } else { p + 4.0 });
                            out.push_str("\" fill=\"");
                            out.push_str(&rgba_css(style.label_rgba));
                            out.push_str("\" font-size=\"");
                            push_num(&mut out, self.chrome.label_font_size);
                            out.push_str("\" text-anchor=\"");
                            out.push_str(if is_x {
                                "middle"
                            } else if side_code == 0 {
                                "end"
                            } else {
                                "start"
                            });
                            out.push_str("\">");
                            push_escaped_attribute(
                                &mut out,
                                &self.axis_tick_label(is_x, label_index, *value, ticks),
                            );
                            out.push_str("</text>");
                        }
                    }
                }
                let side_code = style.side as u8;
                if style.minor_tick_length > 0.0
                    && SceneAxisChromeStyle::visible_stroke(
                        style.minor_tick_rgba,
                        style.minor_tick_width,
                    )
                {
                    for value in Self::minor_ticks(ticks) {
                        let p = scale.pixel(value);
                        let edge = if is_x {
                            if side_code == 0 {
                                self.layout.bottom
                            } else {
                                self.layout.top
                            }
                        } else if side_code == 0 {
                            self.layout.left
                        } else {
                            self.layout.right
                        };
                        let sign = if side_code == 0 { 1.0 } else { -1.0 };
                        let (x1, y1, x2, y2) = if is_x {
                            (p, edge - sign * minor_in, p, edge + sign * minor_out)
                        } else {
                            (edge - sign * minor_out, p, edge + sign * minor_in, p)
                        };
                        push_svg_line(
                            &mut out,
                            x1,
                            y1,
                            x2,
                            y2,
                            &rgba_css(style.minor_tick_rgba),
                            style.minor_tick_width,
                        );
                    }
                }
                let edge = if is_x {
                    if style.side == AxisSide::Low {
                        self.layout.bottom
                    } else {
                        self.layout.top
                    }
                } else if style.side == AxisSide::Low {
                    self.layout.left
                } else {
                    self.layout.right
                };
                let (x1, y1, x2, y2) = if is_x {
                    (self.layout.left, edge, self.layout.right, edge)
                } else {
                    (edge, self.layout.top, edge, self.layout.bottom)
                };
                if SceneAxisChromeStyle::visible_stroke(style.axis_rgba, style.axis_width) {
                    push_svg_line(
                        &mut out,
                        x1,
                        y1,
                        x2,
                        y2,
                        &rgba_css(style.axis_rgba),
                        style.axis_width,
                    );
                }
            }
            out.push_str("</g>");
        }
        push_svg_chrome_text(&mut out, self);
        self.append_svg_labels(&mut out);
        self.append_svg_legend(&mut out);
        self.append_svg_colorbar(&mut out);
        out.push_str("</svg>");
        out
    }

    #[inline(never)]
    fn append_raster_grid(
        &self,
        out: &mut Vec<u8>,
        scale: f64,
        x_ticks: &AxisTicks,
        y_ticks: &AxisTicks,
    ) -> Result<(), SceneError> {
        if SceneAxisChromeStyle::visible_stroke(
            self.chrome.x_axis.grid_rgba,
            self.chrome.x_axis.grid_width,
        ) {
            for value in &x_ticks.labeled {
                let x = self.x_scale.pixel(*value);
                push_raster_stroke(
                    out,
                    [(x, self.layout.top), (x, self.layout.bottom)],
                    self.chrome.x_axis.grid_width,
                    self.chrome.x_axis.grid_rgba,
                    scale,
                )?;
            }
        }
        if SceneAxisChromeStyle::visible_stroke(
            self.chrome.x_axis.minor_grid_rgba,
            self.chrome.x_axis.minor_grid_width,
        ) {
            for value in Self::minor_ticks(x_ticks) {
                let x = self.x_scale.pixel(value);
                push_raster_stroke(
                    out,
                    [(x, self.layout.top), (x, self.layout.bottom)],
                    self.chrome.x_axis.minor_grid_width,
                    self.chrome.x_axis.minor_grid_rgba,
                    scale,
                )?;
            }
        }
        if SceneAxisChromeStyle::visible_stroke(
            self.chrome.y_axis.grid_rgba,
            self.chrome.y_axis.grid_width,
        ) {
            for value in &y_ticks.labeled {
                let y = self.y_scale.pixel(*value);
                push_raster_stroke(
                    out,
                    [(self.layout.left, y), (self.layout.right, y)],
                    self.chrome.y_axis.grid_width,
                    self.chrome.y_axis.grid_rgba,
                    scale,
                )?;
            }
        }
        if SceneAxisChromeStyle::visible_stroke(
            self.chrome.y_axis.minor_grid_rgba,
            self.chrome.y_axis.minor_grid_width,
        ) {
            for value in Self::minor_ticks(y_ticks) {
                let y = self.y_scale.pixel(value);
                push_raster_stroke(
                    out,
                    [(self.layout.left, y), (self.layout.right, y)],
                    self.chrome.y_axis.minor_grid_width,
                    self.chrome.y_axis.minor_grid_rgba,
                    scale,
                )?;
            }
        }
        Ok(())
    }

    #[inline(never)]
    fn append_raster_axes(
        &self,
        out: &mut Vec<u8>,
        scale: f64,
        x_ticks: &AxisTicks,
        y_ticks: &AxisTicks,
    ) -> Result<(), SceneError> {
        out.push(0);
        for value in [
            0.0,
            0.0,
            self.layout.viewport_width,
            self.layout.viewport_height,
        ] {
            push_raster_f32(out, value, scale)?;
        }
        for (is_x, ticks, axis_scale, style) in [
            (true, x_ticks, self.x_scale, self.chrome.x_axis),
            (false, y_ticks, self.y_scale, self.chrome.y_axis),
        ] {
            let edge = if is_x {
                if style.side == AxisSide::Low {
                    self.layout.bottom
                } else {
                    self.layout.top
                }
            } else if style.side == AxisSide::Low {
                self.layout.left
            } else {
                self.layout.right
            };
            let spine = if is_x {
                [(self.layout.left, edge), (self.layout.right, edge)]
            } else {
                [(edge, self.layout.top), (edge, self.layout.bottom)]
            };
            if SceneAxisChromeStyle::visible_stroke(style.axis_rgba, style.axis_width) {
                push_raster_stroke(out, spine, style.axis_width, style.axis_rgba, scale)?;
            }
            let (major_in, major_out) = tick_span(style.major_direction, style.tick_length);
            for side_code in 0..2 {
                if style.tick_sides & (1 << side_code) != 0
                    && style.tick_length > 0.0
                    && SceneAxisChromeStyle::visible_stroke(style.tick_rgba, style.tick_width)
                {
                    let tick_edge = if is_x {
                        if side_code == 0 {
                            self.layout.bottom
                        } else {
                            self.layout.top
                        }
                    } else if side_code == 0 {
                        self.layout.left
                    } else {
                        self.layout.right
                    };
                    let sign = if side_code == 0 { 1.0 } else { -1.0 };
                    for value in &ticks.labeled {
                        let p = axis_scale.pixel(*value);
                        let segment = if is_x {
                            [
                                (p, tick_edge - sign * major_in),
                                (p, tick_edge + sign * major_out),
                            ]
                        } else {
                            [
                                (tick_edge - sign * major_out, p),
                                (tick_edge + sign * major_in, p),
                            ]
                        };
                        push_raster_stroke(out, segment, style.tick_width, style.tick_rgba, scale)?;
                    }
                }
            }
            let (minor_in, minor_out) = tick_span(style.minor_direction, style.minor_tick_length);
            let sign = if style.side == AxisSide::Low {
                1.0
            } else {
                -1.0
            };
            if style.minor_tick_length > 0.0
                && SceneAxisChromeStyle::visible_stroke(
                    style.minor_tick_rgba,
                    style.minor_tick_width,
                )
            {
                for value in Self::minor_ticks(ticks) {
                    let p = axis_scale.pixel(value);
                    let segment = if is_x {
                        [(p, edge - sign * minor_in), (p, edge + sign * minor_out)]
                    } else {
                        [(edge - sign * minor_out, p), (edge + sign * minor_in, p)]
                    };
                    push_raster_stroke(
                        out,
                        segment,
                        style.minor_tick_width,
                        style.minor_tick_rgba,
                        scale,
                    )?;
                }
            }
            for side_code in 0..2 {
                if style.tick_label_sides & (1 << side_code) == 0 || style.label_rgba[3] == 0 {
                    continue;
                }
                for (label_index, value) in ticks.labeled.iter().enumerate() {
                    let p = axis_scale.pixel(*value);
                    let (x, y, anchor) = if is_x {
                        (
                            p,
                            if side_code == 0 {
                                self.layout.bottom + 16.0
                            } else {
                                self.layout.top - 7.0
                            },
                            1,
                        )
                    } else if side_code == 0 {
                        (self.layout.left - 8.0, p + 4.0, 2)
                    } else {
                        (self.layout.right + 8.0, p + 4.0, 0)
                    };
                    let text = self.axis_tick_label(is_x, label_index, *value, ticks);
                    out.push(6);
                    push_raster_f32(out, x, scale)?;
                    push_raster_f32(out, y, scale)?;
                    out.push(anchor);
                    push_raster_f32(out, self.chrome.label_font_size, scale)?;
                    out.extend_from_slice(&style.label_rgba);
                    out.extend_from_slice(&(text.len() as u32).to_le_bytes());
                    out.extend_from_slice(text.as_bytes());
                }
            }
        }
        self.append_raster_chrome_text(out, scale)?;
        Ok(())
    }

    #[inline(never)]
    fn append_raster_chrome_text(&self, out: &mut Vec<u8>, scale: f64) -> Result<(), SceneError> {
        let push_label = |out: &mut Vec<u8>,
                          x: f64,
                          y: f64,
                          anchor: u8,
                          size: f64,
                          rgba: [u8; 4],
                          label: &str|
         -> Result<(), SceneError> {
            if label.is_empty() {
                return Ok(());
            }
            out.push(6);
            push_raster_f32(out, x, scale)?;
            push_raster_f32(out, y, scale)?;
            out.push(anchor);
            push_raster_f32(out, size, scale)?;
            out.extend_from_slice(&rgba);
            out.extend_from_slice(&(label.len() as u32).to_le_bytes());
            out.extend_from_slice(label.as_bytes());
            Ok(())
        };
        push_label(
            out,
            0.5 * (self.layout.left + self.layout.right),
            (self.layout.top * 0.55).max(self.chrome.label_font_size),
            1,
            self.chrome.label_font_size + 2.0,
            self.chrome.label_rgba,
            &self.text.title,
        )?;
        push_label(
            out,
            0.5 * (self.layout.left + self.layout.right),
            self.layout.viewport_height - 6.0,
            1,
            self.chrome.label_font_size,
            self.chrome.x_axis.label_rgba,
            &self.text.x_label,
        )?;
        // Anchor 0x81 = middle + 90° CCW for y-axis titles.
        push_label(
            out,
            (self.layout.left * 0.35).max(self.chrome.label_font_size),
            0.5 * (self.layout.top + self.layout.bottom),
            0x81,
            self.chrome.label_font_size,
            self.chrome.y_axis.label_rgba,
            &self.text.y_label,
        )?;
        Ok(())
    }

    fn raster_command_capacity(&self, x_ticks: &AxisTicks, y_ticks: &AxisTicks) -> usize {
        let label_capacity = |ticks: &AxisTicks, kind: ScaleKind| {
            ticks.labeled.iter().fold(0usize, |capacity, value| {
                capacity.saturating_add(
                    57usize.saturating_add(format_tick(*value, ticks.step, kind).len()),
                )
            })
        };
        let stroke_count = x_ticks
            .ticks
            .len()
            .saturating_add(y_ticks.ticks.len())
            .saturating_add(
                x_ticks
                    .labeled
                    .len()
                    .saturating_mul(self.chrome.x_axis.tick_sides.count_ones() as usize),
            )
            .saturating_add(
                y_ticks
                    .labeled
                    .len()
                    .saturating_mul(self.chrome.y_axis.tick_sides.count_ones() as usize),
            )
            .saturating_add(Self::minor_ticks(x_ticks).count())
            .saturating_add(Self::minor_ticks(y_ticks).count())
            .saturating_add(2);
        let chrome_capacity = stroke_count
            .saturating_mul(35)
            .saturating_add(
                label_capacity(x_ticks, self.x_scale.kind)
                    .saturating_mul(self.chrome.x_axis.tick_label_sides.count_ones() as usize),
            )
            .saturating_add(
                label_capacity(y_ticks, self.y_scale.kind)
                    .saturating_mul(self.chrome.y_axis.tick_label_sides.count_ones() as usize),
            )
            .saturating_add(186);
        let legend_capacity = self.legend.as_ref().map_or(0, |legend| {
            256usize.saturating_add(legend.title.len()).saturating_add(
                legend
                    .entries
                    .iter()
                    .map(|entry| 128usize.saturating_add(entry.label.len()))
                    .sum(),
            )
        });
        let label_capacity = self.labels.iter().fold(0usize, |total, label| {
            total.saturating_add(22).saturating_add(label.text.len())
        });
        let colorbar_capacity = self.colorbar.as_ref().map_or(0, |value| {
            value
                .stops
                .len()
                .saturating_sub(1)
                // Raster polygon: opcode + vertex count + four (x, y) f32
                // pairs + RGBA = 41 bytes per literal color band.
                .saturating_mul(41)
                .saturating_add(value.title.len())
                .saturating_add(64)
        });
        self.raster_mark_capacity
            .saturating_add(chrome_capacity)
            .saturating_add(legend_capacity)
            .saturating_add(colorbar_capacity)
            .saturating_add(label_capacity)
    }

    fn append_raster_labels(&self, out: &mut Vec<u8>, scale: f64) -> Result<(), SceneError> {
        for label in &self.labels {
            out.push(6);
            push_raster_f32(out, label.x, scale)?;
            push_raster_f32(out, label.y, scale)?;
            out.push(0);
            push_raster_f32(out, label.font_size, scale)?;
            out.extend_from_slice(&label.rgba);
            out.extend_from_slice(&(label.text.len() as u32).to_le_bytes());
            out.extend_from_slice(label.text.as_bytes());
        }
        Ok(())
    }

    fn append_raster_legend(&self, out: &mut Vec<u8>, scale: f64) -> Result<(), SceneError> {
        let Some(legend) = &self.legend else {
            return Ok(());
        };
        let (x, y, width, height) = self.legend_bounds(legend)?;
        let points = [
            (x, y),
            (x + width, y),
            (x + width, y + height),
            (x, y + height),
        ];
        out.push(1);
        out.extend_from_slice(&4u32.to_le_bytes());
        for (px, py) in points {
            push_raster_f32(out, px, scale)?;
            push_raster_f32(out, py, scale)?;
        }
        out.extend_from_slice(&legend.frame_fill_rgba);
        push_raster_stroke(
            out,
            [(x, y), (x + width, y)],
            1.0,
            legend.frame_stroke_rgba,
            scale,
        )?;
        push_raster_stroke(
            out,
            [(x + width, y), (x + width, y + height)],
            1.0,
            legend.frame_stroke_rgba,
            scale,
        )?;
        push_raster_stroke(
            out,
            [(x + width, y + height), (x, y + height)],
            1.0,
            legend.frame_stroke_rgba,
            scale,
        )?;
        push_raster_stroke(
            out,
            [(x, y + height), (x, y)],
            1.0,
            legend.frame_stroke_rgba,
            scale,
        )?;
        let mut row_y = y + 8.0;
        let push_text =
            |out: &mut Vec<u8>, label: &str, size: f64, baseline: f64| -> Result<(), SceneError> {
                if label.is_empty() {
                    return Ok(());
                }
                out.push(6);
                push_raster_f32(out, x + 8.0, scale)?;
                push_raster_f32(out, baseline, scale)?;
                out.push(0);
                push_raster_f32(out, size, scale)?;
                out.extend_from_slice(&legend.text_rgba);
                out.extend_from_slice(&(label.len() as u32).to_le_bytes());
                out.extend_from_slice(label.as_bytes());
                Ok(())
            };
        if !legend.title.is_empty() {
            row_y += legend.title_font_size;
            push_text(out, &legend.title, legend.title_font_size, row_y)?;
            row_y += 6.0;
        }
        for entry in &legend.entries {
            row_y += legend.font_size;
            let style = self.styles[entry.style_ref];
            let swatch_y = row_y - legend.font_size * 0.35;
            match entry.kind {
                SceneRecordKind::Polyline => push_raster_stroke(
                    out,
                    [(x + 8.0, swatch_y), (x + 28.0, swatch_y)],
                    style.stroke_width.max(1.0),
                    style.stroke,
                    scale,
                )?,
                SceneRecordKind::Scatter => {
                    let geometry = MarkerGeometry::new(
                        ScatterSymbol::from_code(entry.symbol),
                        8.0,
                        style.stroke_width,
                    );
                    out.push(4);
                    push_raster_f32(out, x + 18.0, scale)?;
                    push_raster_f32(out, swatch_y, scale)?;
                    push_raster_f32(out, geometry.radius, scale)?;
                    out.push(entry.symbol);
                    out.extend_from_slice(&style.fill);
                    push_raster_f32(out, geometry.stroke_width, scale)?;
                    out.extend_from_slice(&style.stroke);
                }
                _ => {
                    out.push(1);
                    out.extend_from_slice(&4u32.to_le_bytes());
                    for (px, py) in [
                        (x + 10.0, swatch_y - 4.0),
                        (x + 26.0, swatch_y - 4.0),
                        (x + 26.0, swatch_y + 4.0),
                        (x + 10.0, swatch_y + 4.0),
                    ] {
                        push_raster_f32(out, px, scale)?;
                        push_raster_f32(out, py, scale)?;
                    }
                    out.extend_from_slice(&style.fill);
                }
            }
            out.push(6);
            push_raster_f32(out, x + 34.0, scale)?;
            push_raster_f32(out, row_y, scale)?;
            out.push(0);
            push_raster_f32(out, legend.font_size, scale)?;
            out.extend_from_slice(&legend.text_rgba);
            out.extend_from_slice(&(entry.label.len() as u32).to_le_bytes());
            out.extend_from_slice(entry.label.as_bytes());
            row_y += 6.0;
        }
        Ok(())
    }

    fn append_raster_colorbar(&self, out: &mut Vec<u8>, scale: f64) -> Result<(), SceneError> {
        let Some(colorbar) = &self.colorbar else {
            return Ok(());
        };
        let (x, y, width, height) = resolved_colorbar_bounds(self.layout, colorbar)?;
        let span = colorbar.domain[1] - colorbar.domain[0];
        for index in 0..colorbar.stops.len() - 1 {
            let (lo, rgba) = colorbar.stops[index];
            let (hi, _) = colorbar.stops[index + 1];
            let a = (lo - colorbar.domain[0]) / span;
            let b = (hi - colorbar.domain[0]) / span;
            let (rx, ry, rw, rh) = if colorbar.horizontal {
                (x + width * a, y, width * (b - a), height)
            } else {
                (x, y + height * (1.0 - b), width, height * (b - a))
            };
            out.push(1);
            out.extend_from_slice(&4u32.to_le_bytes());
            for (px, py) in [(rx, ry), (rx + rw, ry), (rx + rw, ry + rh), (rx, ry + rh)] {
                push_raster_f32(out, px, scale)?;
                push_raster_f32(out, py, scale)?;
            }
            out.extend_from_slice(&rgba);
        }
        if !colorbar.title.is_empty() {
            out.push(6);
            push_raster_f32(out, x, scale)?;
            push_raster_f32(
                out,
                if colorbar.horizontal {
                    y + height + 14.0
                } else {
                    y - 6.0
                },
                scale,
            )?;
            out.push(0);
            push_raster_f32(out, 11.0, scale)?;
            out.extend_from_slice(&colorbar.text_rgba);
            out.extend_from_slice(&(colorbar.title.len() as u32).to_le_bytes());
            out.extend_from_slice(colorbar.title.as_bytes());
        }
        Ok(())
    }

    #[inline(never)]
    fn append_raster_marks(&self, out: &mut Vec<u8>, scale: f64) -> Result<(), SceneError> {
        let mut index = 0;
        while index < self.records.len() {
            let record = self.records[index];
            if !record.visible {
                index += 1;
                continue;
            }
            let style = self.styles[record.style_ref];
            match record.kind {
                SceneRecordKind::Scatter => {
                    let geometry = MarkerGeometry::new(
                        ScatterSymbol::from_code(record.symbol),
                        record.diameter,
                        style.stroke_width,
                    );
                    out.push(4);
                    push_raster_f32(out, record.coordinates[0], scale)?;
                    push_raster_f32(out, record.coordinates[1], scale)?;
                    push_raster_f32(out, geometry.radius, scale)?;
                    out.push(record.symbol);
                    out.extend_from_slice(&style.fill);
                    push_raster_f32(out, geometry.stroke_width, scale)?;
                    out.extend_from_slice(&style.stroke);
                    index += 1;
                }
                SceneRecordKind::Rect => {
                    let points = [
                        (record.coordinates[0], record.coordinates[1]),
                        (record.coordinates[2], record.coordinates[1]),
                        (record.coordinates[2], record.coordinates[3]),
                        (record.coordinates[0], record.coordinates[3]),
                    ];
                    out.push(1);
                    out.extend_from_slice(&4u32.to_le_bytes());
                    for (x, y) in points {
                        push_raster_f32(out, x, scale)?;
                        push_raster_f32(out, y, scale)?;
                    }
                    out.extend_from_slice(&style.fill);
                    if style.stroke_width > 0.0 {
                        out.push(3);
                        out.extend_from_slice(&4u32.to_le_bytes());
                        for (x, y) in points {
                            push_raster_f32(out, x, scale)?;
                            push_raster_f32(out, y, scale)?;
                        }
                        push_raster_f32(out, style.stroke_width, scale)?;
                        out.extend_from_slice(&style.stroke);
                        out.push(1);
                        out.extend_from_slice(&0u32.to_le_bytes());
                        out.push(1);
                    }
                    index += 1;
                }
                SceneRecordKind::Band => {
                    let start = index;
                    let style_ref = record.style_ref;
                    while index < self.records.len() {
                        let point = self.records[index];
                        if point.kind != SceneRecordKind::Band
                            || !same_record_run(record, point)
                            || point.style_ref != style_ref
                            || !point.visible
                        {
                            break;
                        }
                        index += 1;
                    }
                    let run = &self.records[start..index];
                    if run.len() >= 2 {
                        let count = (run.len() * 2) as u32;
                        out.push(1); // OP_FILL_POLY
                        out.extend_from_slice(&count.to_le_bytes());
                        for point in run {
                            push_raster_f32(out, point.coordinates[0], scale)?;
                            push_raster_f32(out, point.coordinates[1], scale)?;
                        }
                        for point in run.iter().rev() {
                            push_raster_f32(out, point.coordinates[2], scale)?;
                            push_raster_f32(out, point.coordinates[3], scale)?;
                        }
                        out.extend_from_slice(&style.fill);
                        if style.stroke_width > 0.0 {
                            out.push(3); // OP_STROKE
                            out.extend_from_slice(&count.to_le_bytes());
                            for point in run {
                                push_raster_f32(out, point.coordinates[0], scale)?;
                                push_raster_f32(out, point.coordinates[1], scale)?;
                            }
                            for point in run.iter().rev() {
                                push_raster_f32(out, point.coordinates[2], scale)?;
                                push_raster_f32(out, point.coordinates[3], scale)?;
                            }
                            push_raster_f32(out, style.stroke_width, scale)?;
                            out.extend_from_slice(&style.stroke);
                            out.push(1); // closed
                            out.extend_from_slice(&0u32.to_le_bytes());
                            out.push(1);
                        }
                    }
                }
                SceneRecordKind::PolyFill => {
                    let start = index;
                    let style_ref = record.style_ref;
                    while index < self.records.len() {
                        let point = self.records[index];
                        if point.kind != SceneRecordKind::PolyFill
                            || !same_record_run(record, point)
                            || point.style_ref != style_ref
                            || !point.visible
                        {
                            break;
                        }
                        index += 1;
                    }
                    let run = &self.records[start..index];
                    if run.len() >= 3 {
                        let count = run.len() as u32;
                        out.push(1); // OP_FILL_POLY
                        out.extend_from_slice(&count.to_le_bytes());
                        for point in run {
                            push_raster_f32(out, point.coordinates[0], scale)?;
                            push_raster_f32(out, point.coordinates[1], scale)?;
                        }
                        out.extend_from_slice(&style.fill);
                        if style.stroke_width > 0.0 {
                            out.push(3); // OP_STROKE
                            out.extend_from_slice(&count.to_le_bytes());
                            for point in run {
                                push_raster_f32(out, point.coordinates[0], scale)?;
                                push_raster_f32(out, point.coordinates[1], scale)?;
                            }
                            push_raster_f32(out, style.stroke_width, scale)?;
                            out.extend_from_slice(&style.stroke);
                            out.push(1); // closed
                            out.extend_from_slice(&0u32.to_le_bytes());
                            out.push(1);
                        }
                    }
                }
                SceneRecordKind::Polyline => {
                    let start = index;
                    let style_ref = record.style_ref;
                    while index < self.records.len() {
                        let point = self.records[index];
                        if point.kind != SceneRecordKind::Polyline
                            || !same_record_run(record, point)
                            || point.style_ref != style_ref
                            || !point.visible
                        {
                            break;
                        }
                        index += 1;
                    }
                    let count = index - start;
                    if count >= 2 && style.stroke_width > 0.0 {
                        out.push(3);
                        out.extend_from_slice(&(count as u32).to_le_bytes());
                        for point in &self.records[start..index] {
                            push_raster_f32(out, point.coordinates[0], scale)?;
                            push_raster_f32(out, point.coordinates[1], scale)?;
                        }
                        push_raster_f32(out, style.stroke_width, scale)?;
                        out.extend_from_slice(&style.stroke);
                        out.push(0);
                        out.extend_from_slice(&0u32.to_le_bytes());
                        out.push(1);
                    }
                }
            }
        }
        Ok(())
    }

    pub fn to_raster_commands(&self, scale: f64) -> Result<Vec<u8>, SceneError> {
        if !scale.is_finite() || scale <= 0.0 {
            return Err(SceneError::NonFinite);
        }
        let x_ticks = self.resolved_axis_ticks(true)?;
        let y_ticks = self.resolved_axis_ticks(false)?;
        // Grid strokes are 35 bytes each. Labeled ticks add another stroke
        // plus a bounded text command; reserve their space up front so adding
        // constant-size chrome never copies the full mark command buffer.
        let reserved_capacity = self.raster_command_capacity(&x_ticks, &y_ticks);
        let mut out = Vec::with_capacity(reserved_capacity);
        let f32_push = |out: &mut Vec<u8>, value: f64| -> Result<(), SceneError> {
            let scaled = value * scale;
            if !scaled.is_finite() {
                return Err(SceneError::NonFinite);
            }
            let narrowed = scaled as f32;
            if !narrowed.is_finite() {
                return Err(SceneError::NonFinite);
            }
            out.extend_from_slice(&narrowed.to_le_bytes());
            Ok(())
        };
        let push_background = |out: &mut Vec<u8>,
                               x: f64,
                               y: f64,
                               w: f64,
                               h: f64,
                               rgba: [u8; 4]|
         -> Result<(), SceneError> {
            out.push(1);
            out.extend_from_slice(&4u32.to_le_bytes());
            for (px, py) in [(x, y), (x + w, y), (x + w, y + h), (x, y + h)] {
                push_raster_f32(out, px, scale)?;
                push_raster_f32(out, py, scale)?;
            }
            out.extend_from_slice(&rgba);
            Ok(())
        };
        push_background(
            &mut out,
            0.0,
            0.0,
            self.layout.viewport_width,
            self.layout.viewport_height,
            self.chrome.chart_background_rgba,
        )?;
        push_background(
            &mut out,
            self.layout.left,
            self.layout.top,
            self.layout.right - self.layout.left,
            self.layout.bottom - self.layout.top,
            self.chrome.plot_background_rgba,
        )?;
        out.push(0);
        f32_push(&mut out, self.layout.left)?;
        f32_push(&mut out, self.layout.top)?;
        f32_push(&mut out, self.layout.right - self.layout.left)?;
        f32_push(&mut out, self.layout.bottom - self.layout.top)?;
        self.append_raster_grid(&mut out, scale, &x_ticks, &y_ticks)?;
        self.append_raster_marks(&mut out, scale)?;
        // Reset the plot clip before chrome, then draw the canonical bottom
        // and left axes through the same display-list primitive as line marks.
        self.append_raster_axes(&mut out, scale, &x_ticks, &y_ticks)?;
        self.append_raster_labels(&mut out, scale)?;
        self.append_raster_legend(&mut out, scale)?;
        self.append_raster_colorbar(&mut out, scale)?;
        if out.len() > reserved_capacity {
            return Err(SceneError::Limit);
        }
        Ok(out)
    }

    /// Lower Scene v9 to the browser painter's column model.
    ///
    /// The fixed descriptor table is O(trace runs); all O(record) coordinate
    /// and stable-id work happens here in Rust and lands directly in packed
    /// little-endian f32/u32 columns. TypeScript only creates descriptor-sized
    /// views and never decodes or re-encodes individual Scene records.
    pub fn to_browser_painter(&self, max_bytes: usize) -> Result<Vec<u8>, SceneError> {
        #[derive(Clone, Copy)]
        struct Group {
            start: usize,
            end: usize,
            kind: SceneRecordKind,
            style_ref: usize,
            symbol: u8,
            diameter: f64,
            annotation_tag: u8,
        }

        let f32_value = |value: f64| -> Result<f32, SceneError> {
            let value = value as f32;
            value
                .is_finite()
                .then_some(value)
                .ok_or(SceneError::NonFinite)
        };
        // Serialize every AxisTicks::ticks position so log minor grid lines
        // match SVG/raster consumers. Labels attach only for AxisTicks::labeled
        // (empty UTF-8 for unlabeled minor ticks).
        let browser_ticks = |is_x: bool, scale: AxisScale, axis: AxisTicks| {
            axis.ticks
                .iter()
                .copied()
                .map(|value| {
                    let major = axis.labeled.contains(&value);
                    let label = if major {
                        let index = axis
                            .labeled
                            .iter()
                            .position(|candidate| *candidate == value)
                            .ok_or(SceneError::Length)?;
                        self.axis_tick_label(is_x, index, value, &axis)
                    } else {
                        String::new()
                    };
                    Ok((f32_value(scale.pixel(value))?, label, major))
                })
                .collect::<Result<Vec<_>, SceneError>>()
        };
        let x_ticks = browser_ticks(true, self.x_scale, self.resolved_axis_ticks(true)?)?;
        let y_ticks = browser_ticks(false, self.y_scale, self.resolved_axis_ticks(false)?)?;

        let mut groups = Vec::new();
        let mut index = 0;
        while index < self.records.len() {
            let record = self.records[index];
            if !record.visible {
                index += 1;
                continue;
            }
            let start = index;
            index += 1;
            match record.kind {
                SceneRecordKind::Polyline => {
                    while index < self.records.len() {
                        let next = self.records[index];
                        if !next.visible
                            || next.kind != SceneRecordKind::Polyline
                            || !same_record_run(record, next)
                            || next.style_ref != record.style_ref
                        {
                            break;
                        }
                        index += 1;
                    }
                }
                SceneRecordKind::Scatter => {
                    while index < self.records.len() {
                        let next = self.records[index];
                        if !next.visible
                            || next.kind != SceneRecordKind::Scatter
                            || next.style_ref != record.style_ref
                            || next.symbol != record.symbol
                            || next.diameter.to_bits() != record.diameter.to_bits()
                            || !same_record_run(record, next)
                        {
                            break;
                        }
                        index += 1;
                    }
                }
                SceneRecordKind::Rect => {
                    while index < self.records.len() {
                        let next = self.records[index];
                        if !next.visible
                            || next.kind != SceneRecordKind::Rect
                            || next.style_ref != record.style_ref
                            || !same_record_run(record, next)
                        {
                            break;
                        }
                        index += 1;
                    }
                }
                SceneRecordKind::Band => {
                    if record.coordinates[0] != record.coordinates[2] {
                        return Err(SceneError::Length);
                    }
                    while index < self.records.len() {
                        let next = self.records[index];
                        if !next.visible
                            || next.kind != SceneRecordKind::Band
                            || !same_record_run(record, next)
                            || next.style_ref != record.style_ref
                        {
                            break;
                        }
                        // Browser area paint uses one x column with a y-base; reject
                        // bands whose base x differs from the top sample.
                        if next.coordinates[0] != next.coordinates[2] {
                            return Err(SceneError::Length);
                        }
                        index += 1;
                    }
                }
                SceneRecordKind::PolyFill => {
                    while index < self.records.len() {
                        let next = self.records[index];
                        if !next.visible
                            || next.kind != SceneRecordKind::PolyFill
                            || !same_record_run(record, next)
                            || next.style_ref != record.style_ref
                        {
                            break;
                        }
                        index += 1;
                    }
                    if index - start < 3 {
                        return Err(SceneError::Length);
                    }
                }
            }
            groups.push(Group {
                start,
                end: index,
                kind: record.kind,
                style_ref: record.style_ref,
                symbol: record.symbol,
                diameter: record.diameter,
                annotation_tag: record.annotation_tag,
            });
            if groups.len() > MAX_BROWSER_PAINTER_TRACES {
                return Err(SceneError::PainterTraceLimit);
            }
        }

        let descriptors = groups
            .len()
            .checked_mul(BROWSER_PAINTER_TRACE_BYTES)
            .ok_or(SceneError::Limit)?;
        let mut required = BROWSER_PAINTER_HEADER_BYTES
            .checked_add(descriptors)
            .ok_or(SceneError::Limit)?;
        for group in &groups {
            let columns = if matches!(group.kind, SceneRecordKind::Rect | SceneRecordKind::Band) {
                6
            } else {
                4
            };
            required = required
                .checked_add(
                    (group.end - group.start)
                        .checked_mul(columns * 4)
                        .ok_or(SceneError::Limit)?,
                )
                .ok_or(SceneError::Limit)?;
        }
        let tick_count = x_ticks
            .len()
            .checked_add(y_ticks.len())
            .ok_or(SceneError::Limit)?;
        required = required
            .checked_add(
                tick_count
                    .checked_mul(BROWSER_PAINTER_TICK_BYTES)
                    .ok_or(SceneError::Limit)?,
            )
            .ok_or(SceneError::Limit)?;
        for (_, label, _) in x_ticks.iter().chain(&y_ticks) {
            required = required.checked_add(label.len()).ok_or(SceneError::Limit)?;
        }
        required = required
            .checked_add(self.text.title.len())
            .and_then(|value| value.checked_add(self.text.x_label.len()))
            .and_then(|value| value.checked_add(self.text.y_label.len()))
            .ok_or(SceneError::Limit)?;
        let legend_bytes = self.painter_legend_bytes()?;
        let colorbar_bytes = self.painter_colorbar_bytes()?;
        let label_bytes = encode_scene_labels(&self.labels)?;
        required = required
            .checked_add(legend_bytes.len())
            .and_then(|value| value.checked_add(colorbar_bytes.len()))
            .and_then(|value| value.checked_add(label_bytes.len()))
            .ok_or(SceneError::Limit)?;
        if required > max_bytes {
            return Err(SceneError::Limit);
        }
        let mut out = Vec::with_capacity(required);
        out.resize(BROWSER_PAINTER_HEADER_BYTES + descriptors, 0);
        out[0..4].copy_from_slice(b"XYPB");
        out[4..8].copy_from_slice(&BROWSER_PAINTER_VERSION.to_le_bytes());
        out[8..12].copy_from_slice(&SCENE_VERSION.to_le_bytes());
        out[12..16].copy_from_slice(&(BROWSER_PAINTER_HEADER_BYTES as u32).to_le_bytes());
        out[16..20].copy_from_slice(&(BROWSER_PAINTER_TRACE_BYTES as u32).to_le_bytes());
        out[20..24].copy_from_slice(&(groups.len() as u32).to_le_bytes());
        for (slot, value) in [
            self.layout.viewport_width,
            self.layout.viewport_height,
            self.layout.left,
            self.layout.top,
            self.layout.right,
            self.layout.bottom,
        ]
        .into_iter()
        .enumerate()
        {
            out[24 + slot * 4..28 + slot * 4].copy_from_slice(&f32_value(value)?.to_le_bytes());
        }
        out[48..52].copy_from_slice(&(x_ticks.len() as u32).to_le_bytes());
        out[52..56].copy_from_slice(&(y_ticks.len() as u32).to_le_bytes());

        for (group_index, group) in groups.iter().enumerate() {
            let descriptor =
                BROWSER_PAINTER_HEADER_BYTES + group_index * BROWSER_PAINTER_TRACE_BYTES;
            out[descriptor] = group.kind as u8;
            out[descriptor + 1] = group.symbol;
            out[descriptor + 2] = if group.annotation_tag <= 4 {
                group.annotation_tag
            } else {
                0
            };
            let count = group.end - group.start;
            out[descriptor + 4..descriptor + 8].copy_from_slice(&(count as u32).to_le_bytes());
            let coordinate_columns =
                if matches!(group.kind, SceneRecordKind::Rect | SceneRecordKind::Band) {
                    4
                } else {
                    2
                };
            for column in 0..coordinate_columns {
                let column_offset = out.len();
                out[descriptor + 8 + column * 4..descriptor + 12 + column * 4]
                    .copy_from_slice(&(column_offset as u32).to_le_bytes());
                for record in &self.records[group.start..group.end] {
                    out.extend_from_slice(&f32_value(record.coordinates[column])?.to_le_bytes());
                }
            }
            for (column, high) in [false, true].into_iter().enumerate() {
                let column_offset = out.len();
                out[descriptor + 24 + column * 4..descriptor + 28 + column * 4]
                    .copy_from_slice(&(column_offset as u32).to_le_bytes());
                for record in &self.records[group.start..group.end] {
                    let word = if high {
                        (record.stable_id >> 32) as u32
                    } else {
                        record.stable_id as u32
                    };
                    out.extend_from_slice(&word.to_le_bytes());
                }
            }
            let style = self.styles[group.style_ref];
            out[descriptor + 32..descriptor + 36].copy_from_slice(&style.fill);
            out[descriptor + 36..descriptor + 40].copy_from_slice(&style.stroke);
            let stroke_width = if group.kind == SceneRecordKind::Scatter {
                MarkerGeometry::new(
                    ScatterSymbol::from_code(group.symbol),
                    group.diameter,
                    style.stroke_width,
                )
                .stroke_width
            } else {
                style.stroke_width
            };
            out[descriptor + 40..descriptor + 44]
                .copy_from_slice(&f32_value(stroke_width)?.to_le_bytes());
            out[descriptor + 44..descriptor + 48]
                .copy_from_slice(&f32_value(group.diameter)?.to_le_bytes());
        }
        let tick_offset = out.len();
        let tick_bytes = tick_count
            .checked_mul(BROWSER_PAINTER_TICK_BYTES)
            .ok_or(SceneError::Limit)?;
        let string_offset = tick_offset
            .checked_add(tick_bytes)
            .ok_or(SceneError::Limit)?;
        out[56..60].copy_from_slice(&(tick_offset as u32).to_le_bytes());
        out[60..64].copy_from_slice(&(string_offset as u32).to_le_bytes());
        let mut chrome_input = Vec::with_capacity(SCENE_CHROME_STYLE_INPUT_BYTES);
        write_chrome_style_input(&mut chrome_input, &self.chrome);
        debug_assert_eq!(chrome_input.len(), SCENE_CHROME_STYLE_INPUT_BYTES);
        out[64..264].copy_from_slice(&chrome_input);
        for (offset, value) in [
            (264, self.text.title.len()),
            (268, self.text.x_label.len()),
            (272, self.text.y_label.len()),
        ] {
            out[offset..offset + 4].copy_from_slice(&(value as u32).to_le_bytes());
        }
        out[280..284].copy_from_slice(&(legend_bytes.len() as u32).to_le_bytes());
        out[284..288].copy_from_slice(&(colorbar_bytes.len() as u32).to_le_bytes());
        out[288..292].copy_from_slice(&(label_bytes.len() as u32).to_le_bytes());
        out.resize(string_offset, 0);
        out.extend_from_slice(self.text.title.as_bytes());
        out.extend_from_slice(self.text.x_label.as_bytes());
        out.extend_from_slice(self.text.y_label.as_bytes());
        for (tick_index, (position, label, major)) in x_ticks.iter().chain(&y_ticks).enumerate() {
            let descriptor = tick_offset + tick_index * BROWSER_PAINTER_TICK_BYTES;
            let label_offset = out.len();
            out[descriptor..descriptor + 4].copy_from_slice(&position.to_le_bytes());
            out[descriptor + 4..descriptor + 8]
                .copy_from_slice(&(label_offset as u32).to_le_bytes());
            out[descriptor + 8..descriptor + 12]
                .copy_from_slice(&(label.len() as u32).to_le_bytes());
            out[descriptor + 12..descriptor + 16].copy_from_slice(&u32::from(*major).to_le_bytes());
            out.extend_from_slice(label.as_bytes());
        }
        out.extend_from_slice(&legend_bytes);
        out.extend_from_slice(&colorbar_bytes);
        out.extend_from_slice(&label_bytes);
        debug_assert_eq!(out.len(), required);
        Ok(out)
    }
}

pub struct ScatterScene<'a> {
    x: &'a [f64],
    y: &'a [f64],
    diameter: &'a [f64],
    fill_rgba: &'a [u8],
    stroke_rgba: &'a [u8],
    stroke_width: &'a [f64],
    symbols: &'a [u8],
    visible: Option<&'a [u8]>,
    fill_css: Option<&'a str>,
    stroke_css: Option<&'a str>,
}

impl<'a> ScatterScene<'a> {
    #[allow(clippy::too_many_arguments)]
    pub fn new(
        x: &'a [f64],
        y: &'a [f64],
        diameter: &'a [f64],
        fill_rgba: &'a [u8],
        stroke_rgba: &'a [u8],
        stroke_width: &'a [f64],
        symbols: &'a [u8],
        visible: Option<&'a [u8]>,
        fill_css: Option<&'a str>,
        stroke_css: Option<&'a str>,
    ) -> Result<Self, SceneError> {
        let len = x.len();
        if len > MAX_SCENE_MARKS {
            return Err(SceneError::Limit);
        }
        let rgba_len = len.checked_mul(4).ok_or(SceneError::Limit)?;
        if y.len() != len
            || diameter.len() != len
            || fill_rgba.len() != rgba_len
            || stroke_rgba.len() != rgba_len
            || stroke_width.len() != len
            || symbols.len() != len
            || visible.is_some_and(|items| items.len() != len)
        {
            return Err(SceneError::Length);
        }
        if x.iter()
            .chain(y)
            .chain(diameter)
            .chain(stroke_width)
            .any(|value| !value.is_finite())
        {
            return Err(SceneError::NonFinite);
        }
        if diameter.iter().any(|value| *value < 0.0)
            || stroke_width.iter().any(|value| *value < 0.0)
        {
            return Err(SceneError::NegativeSize);
        }
        if fill_css.is_some_and(|value| css::parse_color(value).is_err())
            || stroke_css.is_some_and(|value| css::parse_color(value).is_err())
        {
            return Err(SceneError::InvalidPaint);
        }
        Ok(Self {
            x,
            y,
            diameter,
            fill_rgba,
            stroke_rgba,
            stroke_width,
            symbols,
            visible,
            fill_css,
            stroke_css,
        })
    }

    pub fn to_svg(&self) -> String {
        let mut out = String::with_capacity(self.x.len().saturating_mul(112));
        out.push_str("<g>");
        for index in 0..self.x.len() {
            if self.visible.is_some_and(|items| items[index] == 0) {
                continue;
            }
            let symbol = ScatterSymbol::from_code(self.symbols[index]);
            let geometry =
                MarkerGeometry::new(symbol, self.diameter[index], self.stroke_width[index]);
            push_symbol(
                &mut out,
                symbol,
                self.x[index],
                self.y[index],
                geometry.radius,
            );
            let fill = rgba_at(self.fill_rgba, index);
            let stroke = rgba_at(self.stroke_rgba, index);
            if symbol.is_line() {
                out.push_str(" fill=\"none\"");
            } else {
                push_paint(&mut out, "fill", fill, self.fill_css);
            }
            if geometry.stroke_width > 0.0 || symbol.is_line() {
                push_paint(&mut out, "stroke", stroke, self.stroke_css);
                out.push_str(" stroke-width=\"");
                push_num(&mut out, geometry.stroke_width);
                out.push('"');
            }
            out.push_str("/>");
        }
        out.push_str("</g>");
        out
    }
}

fn rgba_at(values: &[u8], index: usize) -> [u8; 4] {
    let offset = index * 4;
    [
        values[offset],
        values[offset + 1],
        values[offset + 2],
        values[offset + 3],
    ]
}

fn push_paint(out: &mut String, name: &str, rgba: [u8; 4], css: Option<&str>) {
    write!(out, " {name}=\"").expect("writing to String cannot fail");
    if let Some(value) = css {
        push_escaped_attribute(out, value);
    } else {
        write!(out, "rgb({},{},{})", rgba[0], rgba[1], rgba[2])
            .expect("writing to String cannot fail");
    }
    out.push('"');
    if rgba[3] < 255 {
        write!(out, " {name}-opacity=\"").expect("writing to String cannot fail");
        push_num(out, f64::from(rgba[3]) / 255.0);
        out.push('"');
    }
}

fn push_escaped_attribute(out: &mut String, value: &str) {
    for character in value.chars() {
        match character {
            '&' => out.push_str("&amp;"),
            '<' => out.push_str("&lt;"),
            '>' => out.push_str("&gt;"),
            '"' => out.push_str("&quot;"),
            _ => out.push(character),
        }
    }
}

fn point(out: &mut String, x: f64, y: f64) {
    push_num(out, x);
    out.push(' ');
    push_num(out, y);
}

fn push_symbol(out: &mut String, symbol: ScatterSymbol, cx: f64, cy: f64, radius: f64) {
    match symbol {
        ScatterSymbol::Circle | ScatterSymbol::Point => {
            out.push_str("<circle cx=\"");
            push_num(out, cx);
            out.push_str("\" cy=\"");
            push_num(out, cy);
            out.push_str("\" r=\"");
            push_num(out, radius);
            out.push('"');
        }
        ScatterSymbol::Square | ScatterSymbol::Pixel => {
            out.push_str("<rect x=\"");
            push_num(out, cx - radius);
            out.push_str("\" y=\"");
            push_num(out, cy - radius);
            out.push_str("\" width=\"");
            push_num(out, radius * 2.0);
            out.push_str("\" height=\"");
            push_num(out, radius * 2.0);
            out.push('"');
        }
        ScatterSymbol::Diamond | ScatterSymbol::ThinDiamond => {
            let dx = std::f64::consts::SQRT_2
                * radius
                * if symbol == ScatterSymbol::ThinDiamond {
                    0.6
                } else {
                    1.0
                };
            let dy = std::f64::consts::SQRT_2 * radius;
            out.push_str("<path d=\"M ");
            point(out, cx, cy - dy);
            out.push_str(" L ");
            point(out, cx + dx, cy);
            out.push_str(" L ");
            point(out, cx, cy + dy);
            out.push_str(" L ");
            point(out, cx - dx, cy);
            out.push_str(" Z\"");
        }
        ScatterSymbol::Triangle
        | ScatterSymbol::TriangleDown
        | ScatterSymbol::TriangleLeft
        | ScatterSymbol::TriangleRight => push_triangle(out, symbol, cx, cy, radius),
        ScatterSymbol::Cross => push_cross(out, cx, cy, radius),
        ScatterSymbol::X => push_x(out, cx, cy, radius),
        ScatterSymbol::PlusLine => {
            out.push_str("<path d=\"M ");
            point(out, cx - radius, cy);
            out.push_str(" H ");
            push_num(out, cx + radius);
            out.push_str(" M ");
            point(out, cx, cy - radius);
            out.push_str(" V ");
            push_num(out, cy + radius);
            out.push('"');
        }
        ScatterSymbol::XLine => {
            let delta = 0.707 * radius;
            out.push_str("<path d=\"M ");
            point(out, cx - delta, cy - delta);
            out.push_str(" L ");
            point(out, cx + delta, cy + delta);
            out.push_str(" M ");
            point(out, cx + delta, cy - delta);
            out.push_str(" L ");
            point(out, cx - delta, cy + delta);
            out.push('"');
        }
        ScatterSymbol::HorizontalLine | ScatterSymbol::VerticalLine => {
            out.push_str("<path d=\"M ");
            if symbol == ScatterSymbol::HorizontalLine {
                point(out, cx - radius, cy);
                out.push_str(" H ");
                push_num(out, cx + radius);
            } else {
                point(out, cx, cy - radius);
                out.push_str(" V ");
                push_num(out, cy + radius);
            }
            out.push('"');
        }
        ScatterSymbol::Pentagon => push_regular_polygon(out, cx, cy, radius, 5, -90.0, 1.0),
        ScatterSymbol::Hexagon => push_regular_polygon(out, cx, cy, radius, 6, -90.0, 1.0),
        ScatterSymbol::Star => push_regular_polygon(out, cx, cy, radius, 10, -90.0, 0.45),
    }
}

fn push_triangle(out: &mut String, symbol: ScatterSymbol, cx: f64, cy: f64, r: f64) {
    let points = match symbol {
        ScatterSymbol::Triangle => [(cx, cy - r), (cx + r, cy + r), (cx - r, cy + r)],
        ScatterSymbol::TriangleDown => [(cx, cy + r), (cx + r, cy - r), (cx - r, cy - r)],
        ScatterSymbol::TriangleLeft => [(cx - r, cy), (cx + r, cy - r), (cx + r, cy + r)],
        _ => [(cx + r, cy), (cx - r, cy - r), (cx - r, cy + r)],
    };
    out.push_str("<path d=\"M ");
    point(out, points[0].0, points[0].1);
    for item in &points[1..] {
        out.push_str(" L ");
        point(out, item.0, item.1);
    }
    out.push_str(" Z\"");
}

fn push_cross(out: &mut String, cx: f64, cy: f64, r: f64) {
    let d = 0.34 * r;
    out.push_str("<path d=\"M ");
    point(out, cx - d, cy - r);
    write!(out, " H ").expect("writing to String cannot fail");
    push_num(out, cx + d);
    out.push_str(" V ");
    push_num(out, cy - d);
    out.push_str(" H ");
    push_num(out, cx + r);
    out.push_str(" V ");
    push_num(out, cy + d);
    out.push_str(" H ");
    push_num(out, cx + d);
    out.push_str(" V ");
    push_num(out, cy + r);
    out.push_str(" H ");
    push_num(out, cx - d);
    out.push_str(" V ");
    push_num(out, cy + d);
    out.push_str(" H ");
    push_num(out, cx - r);
    out.push_str(" V ");
    push_num(out, cy - d);
    out.push_str(" H ");
    push_num(out, cx - d);
    out.push_str(" Z\"");
}

fn push_x(out: &mut String, cx: f64, cy: f64, r: f64) {
    let outer = 0.72 * r;
    let inner = 0.28 * r;
    let points = [
        (cx - outer, cy - r),
        (cx, cy - inner),
        (cx + outer, cy - r),
        (cx + r, cy - outer),
        (cx + inner, cy),
        (cx + r, cy + outer),
        (cx + outer, cy + r),
        (cx, cy + inner),
        (cx - outer, cy + r),
        (cx - r, cy + outer),
        (cx - inner, cy),
        (cx - r, cy - outer),
    ];
    out.push_str("<path d=\"M ");
    point(out, points[0].0, points[0].1);
    for item in &points[1..] {
        out.push_str(" L ");
        point(out, item.0, item.1);
    }
    out.push_str(" Z\"");
}

fn push_regular_polygon(
    out: &mut String,
    cx: f64,
    cy: f64,
    radius: f64,
    vertices: usize,
    start_degrees: f64,
    inner_ratio: f64,
) {
    out.push_str("<path d=\"M ");
    for index in 0..vertices {
        if index != 0 {
            out.push_str(" L ");
        }
        let point_radius = if inner_ratio < 1.0 && index % 2 == 1 {
            radius * inner_ratio
        } else {
            radius
        };
        let angle = (start_degrees + index as f64 * 360.0 / vertices as f64).to_radians();
        point(
            out,
            cx + point_radius * angle.cos(),
            cy + point_radius * angle.sin(),
        );
    }
    out.push_str(" Z\"");
}

/// DejaVu Sans advances at BASE_PX=16 for printable ASCII (matches
/// `python/xyg/_fontmetrics.py` / `font.rs` so native and WASM gutters agree
/// without pulling the raster coverage atlas into the browser adapter).
const ASCII_ADVANCES: [i32; 95] = [
    5, 6, 7, 13, 10, 15, 12, 4, 6, 6, 8, 13, 5, 6, 5, 5, 10, 10, 10, 10, 10, 10, 10, 10, 10, 10, 5,
    5, 13, 13, 13, 8, 16, 11, 11, 11, 12, 10, 9, 12, 12, 5, 5, 10, 9, 14, 12, 13, 10, 13, 11, 10,
    10, 12, 11, 16, 11, 10, 11, 6, 5, 6, 13, 8, 8, 10, 10, 9, 10, 10, 6, 10, 10, 4, 4, 9, 4, 16,
    10, 10, 10, 10, 7, 8, 6, 10, 9, 13, 9, 9, 8, 10, 5, 10, 13,
];
const FONT_BASE_PX: f64 = 16.0;
const MISSING_ADVANCE: i32 = 16; // U+FFFD width at BASE_PX

fn text_advance(text: &str, font_size: f64) -> f64 {
    let mut units = 0_i32;
    for ch in text.chars() {
        let code = ch as u32;
        units += if (32..=126).contains(&code) {
            ASCII_ADVANCES[(code - 32) as usize]
        } else {
            MISSING_ADVANCE
        };
    }
    font_size * f64::from(units) / FONT_BASE_PX
}

const AXIS_TEXT_EDGE_PAD: f64 = 4.0;
const Y_TITLE_TICK_GAP: f64 = 0.4;
const LABEL_FONT_PX: f64 = 12.0;
const COLORBAR_OUTER_GUTTER: f64 = 28.0;
const COLORBAR_THICKNESS: f64 = 14.0;

/// Deterministic built-in chrome measurement. Hosts must not substitute a DOM
/// measurement for canonical Scene gutters.
pub fn scene_text_advance(text: &str, font_size: f64) -> f64 {
    text_advance(text, font_size)
}

/// Literal colorbar side supplied by thin host framing. Rust owns the
/// resulting margin reservation.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum ColorbarSide {
    None,
    Right,
    Bottom,
}

/// Inputs for [`cartesian_scene_margins`].
#[derive(Clone, Copy, Debug)]
pub struct CartesianLayoutRequest<'a> {
    pub viewport_width: f64,
    pub viewport_height: f64,
    pub authored_padding: Option<[f64; 4]>,
    pub title: &'a str,
    pub x_label: &'a str,
    pub y_label: &'a str,
    pub x_kind: ScaleKind,
    pub x_lo: f64,
    pub x_hi: f64,
    pub x_constant: f64,
    pub x_mask_nonpositive: bool,
    pub y_kind: ScaleKind,
    pub y_lo: f64,
    pub y_hi: f64,
    pub y_constant: f64,
    pub y_mask_nonpositive: bool,
    pub colorbar_side: ColorbarSide,
}

/// Cartesian default gutters for the Scene-eligible export subset.
///
/// Mirrors `_svg.layout()` for primary x/y, default sides, no colorbar, and
/// no secondary axes: compact/regular pads or authored `(top, right, bottom,
/// left)` padding, title band, measured default tick labels, and outside
/// axis-title rooms. Hosts must not invent Scene margins once this lands.
pub fn cartesian_scene_margins(
    request: CartesianLayoutRequest<'_>,
) -> Result<(f64, f64, f64, f64), SceneError> {
    let CartesianLayoutRequest {
        viewport_width,
        viewport_height,
        authored_padding,
        title,
        x_label,
        y_label,
        x_kind,
        x_lo,
        x_hi,
        x_constant,
        x_mask_nonpositive,
        y_kind,
        y_lo,
        y_hi,
        y_constant,
        y_mask_nonpositive,
        colorbar_side,
    } = request;
    if ![viewport_width, viewport_height]
        .iter()
        .all(|value| value.is_finite() && *value > 0.0)
    {
        return Err(SceneError::NonFinite);
    }
    if let Some(padding) = authored_padding {
        if padding
            .iter()
            .any(|value| !value.is_finite() || *value < 0.0)
        {
            return Err(SceneError::NonFinite);
        }
    }
    let compact = viewport_width < 520.0;
    let (mut top, mut right, mut bottom, mut left) = match authored_padding {
        Some([top, right, bottom, left]) => (top, right, bottom, left),
        None if compact => (6.0, 8.0, 36.0, 46.0),
        None => (10.0, 14.0, 42.0, 62.0),
    };
    let title_wrap = (viewport_width - left - right).max(40.0);
    if !title.is_empty() {
        let width = text_advance(title, 14.0);
        let lines = if width <= title_wrap {
            1.0
        } else {
            (width / title_wrap).ceil().max(1.0)
        };
        let height = lines * 14.0 * 1.2;
        top += {
            let floor = if compact { 26.0_f64 } else { 30.0_f64 };
            floor.max(height + 8.0)
        };
    }

    let provisional_w = (viewport_width - left - right).max(40.0);
    let provisional_h = (viewport_height - top - bottom).max(40.0);
    let x_scale = AxisScale::new(
        x_kind,
        x_lo,
        x_hi,
        0.0,
        provisional_w,
        x_constant,
        x_mask_nonpositive,
    )?;
    let y_scale = AxisScale::new(
        y_kind,
        y_lo,
        y_hi,
        provisional_h,
        0.0,
        y_constant,
        y_mask_nonpositive,
    )?;
    let x_ticks = x_scale.ticks(provisional_w, true)?;
    let y_ticks = y_scale.ticks(provisional_h, false)?;

    let mut tick_label_width = 0.0_f64;
    for value in &y_ticks.labeled {
        tick_label_width = tick_label_width.max(text_advance(
            &format_tick(*value, y_ticks.step, y_kind),
            LABEL_FONT_PX,
        ));
    }
    let y_tick_room = if y_ticks.labeled.is_empty() {
        0.0
    } else {
        AXIS_TEXT_EDGE_PAD + 8.0 + tick_label_width
    };
    let left_needed = if y_label.is_empty() {
        y_tick_room
    } else {
        AXIS_TEXT_EDGE_PAD + LABEL_FONT_PX * 1.2 + Y_TITLE_TICK_GAP * LABEL_FONT_PX + y_tick_room
    };
    left = left.max(left_needed);

    let x_tick_room = if x_ticks.labeled.is_empty() {
        0.0
    } else {
        AXIS_TEXT_EDGE_PAD + 8.0 + LABEL_FONT_PX
    };
    let bottom_needed = if x_label.is_empty() {
        x_tick_room
    } else {
        (AXIS_TEXT_EDGE_PAD + 24.0 + LABEL_FONT_PX * 0.82 + LABEL_FONT_PX * 0.2).max(x_tick_room)
    };
    bottom = bottom.max(bottom_needed);

    match colorbar_side {
        ColorbarSide::None => {}
        ColorbarSide::Right => right = right.max(COLORBAR_OUTER_GUTTER + COLORBAR_THICKNESS),
        ColorbarSide::Bottom => bottom = bottom.max(COLORBAR_OUTER_GUTTER + COLORBAR_THICKNESS),
    }

    // Terminal x-label overhang against the spine ends (two passes).
    for _ in 0..2 {
        let plot_w = (viewport_width - left - right).max(40.0);
        let x_scale = AxisScale::new(
            x_kind,
            x_lo,
            x_hi,
            0.0,
            plot_w,
            x_constant,
            x_mask_nonpositive,
        )?;
        let x_ticks = x_scale.ticks(plot_w, true)?;
        if x_ticks.labeled.is_empty() {
            break;
        }
        let first = x_ticks.labeled[0];
        let last = *x_ticks.labeled.last().expect("non-empty");
        let first_w = text_advance(&format_tick(first, x_ticks.step, x_kind), LABEL_FONT_PX);
        let last_w = text_advance(&format_tick(last, x_ticks.step, x_kind), LABEL_FONT_PX);
        let first_x = x_scale.pixel(first);
        let last_x = x_scale.pixel(last);
        let next_left = left.max(AXIS_TEXT_EDGE_PAD + first_w * 0.5 - first_x);
        let next_right = right.max(AXIS_TEXT_EDGE_PAD + last_x + last_w * 0.5 - plot_w);
        if (next_left - left).abs() < 1e-9 && (next_right - right).abs() < 1e-9 {
            break;
        }
        left = next_left;
        right = next_right;
    }

    PlotLayout::new(viewport_width, viewport_height, left, right, top, bottom)?;
    Ok((left, right, top, bottom))
}

#[cfg(test)]
mod tests {
    use super::*;

    fn raster_text_count(commands: &[u8]) -> Option<usize> {
        let mut offset = 0usize;
        let mut texts = 0usize;
        let read_u32 = |offset: &mut usize| -> Option<usize> {
            let end = offset.checked_add(4)?;
            let value = u32::from_le_bytes(commands.get(*offset..end)?.try_into().ok()?) as usize;
            *offset = end;
            Some(value)
        };
        while offset < commands.len() {
            let operation = *commands.get(offset)?;
            offset += 1;
            let bytes = match operation {
                0 => 16,
                1 => read_u32(&mut offset)?.checked_mul(8)?.checked_add(4)?,
                3 => {
                    let points = read_u32(&mut offset)?;
                    offset = offset.checked_add(points.checked_mul(8)?.checked_add(9)?)?;
                    let dashes = read_u32(&mut offset)?;
                    dashes.checked_mul(4)?.checked_add(1)?
                }
                4 => 25,
                6 => {
                    offset = offset.checked_add(17)?;
                    texts += 1;
                    read_u32(&mut offset)?
                }
                _ => return None,
            };
            offset = offset.checked_add(bytes)?;
            if offset > commands.len() {
                return None;
            }
        }
        Some(texts)
    }

    #[test]
    fn cartesian_scene_margins_match_compact_defaults() {
        let (left, right, top, bottom) = cartesian_scene_margins(CartesianLayoutRequest {
            viewport_width: 320.0,
            viewport_height: 240.0,
            authored_padding: None,
            title: "",
            x_label: "",
            y_label: "",
            x_kind: ScaleKind::Linear,
            x_lo: 0.0,
            x_hi: 4.0,
            x_constant: 1.0,
            x_mask_nonpositive: false,
            y_kind: ScaleKind::Linear,
            y_lo: 0.0,
            y_hi: 5.0,
            y_constant: 1.0,
            y_mask_nonpositive: false,
            colorbar_side: ColorbarSide::None,
        })
        .unwrap();
        assert!(left >= 46.0, "left={left}");
        assert!(right >= 8.0, "right={right}");
        assert!(top >= 6.0, "top={top}");
        assert!(bottom >= 36.0, "bottom={bottom}");
        PlotLayout::new(320.0, 240.0, left, right, top, bottom).unwrap();
    }

    #[test]
    fn cartesian_scene_margins_reserve_the_literal_colorbar_lane() {
        let request = |colorbar_side| CartesianLayoutRequest {
            viewport_width: 320.0,
            viewport_height: 240.0,
            authored_padding: None,
            title: "",
            x_label: "",
            y_label: "",
            x_kind: ScaleKind::Linear,
            x_lo: 0.0,
            x_hi: 1.0,
            x_constant: 1.0,
            x_mask_nonpositive: false,
            y_kind: ScaleKind::Linear,
            y_lo: 0.0,
            y_hi: 1.0,
            y_constant: 1.0,
            y_mask_nonpositive: false,
            colorbar_side,
        };
        let right = cartesian_scene_margins(request(ColorbarSide::Right)).unwrap();
        let bottom = cartesian_scene_margins(request(ColorbarSide::Bottom)).unwrap();
        assert!(right.1 >= COLORBAR_OUTER_GUTTER + COLORBAR_THICKNESS);
        assert!(bottom.3 >= COLORBAR_OUTER_GUTTER + COLORBAR_THICKNESS);
    }

    #[test]
    fn scatter_scene_is_versioned_bounded_and_deterministic() {
        let scene = ScatterScene::new(
            &[10.0, 20.0],
            &[11.0, 21.0],
            &[8.0, 10.0],
            &[37, 99, 235, 255, 239, 68, 68, 128],
            &[0, 0, 0, 255, 17, 24, 39, 64],
            &[2.0, 0.0],
            &[ScatterSymbol::Circle as u8, ScatterSymbol::PlusLine as u8],
            None,
            None,
            None,
        )
        .unwrap();
        assert_eq!(SCENE_VERSION, 16);
        assert_eq!(
            scene.to_svg(),
            "<g><circle cx=\"10\" cy=\"11\" r=\"3\" fill=\"rgb(37,99,235)\" stroke=\"rgb(0,0,0)\" stroke-width=\"2\"/><path d=\"M 15.5 21 H 24.5 M 20 16.5 V 25.5\" fill=\"none\" stroke=\"rgb(17,24,39)\" stroke-opacity=\"0.25\" stroke-width=\"1\"/></g>"
        );
    }

    #[test]
    fn scene_v3_batch_encodes_layout_axes_and_all_core_record_kinds() {
        let layout = PlotLayout::new(640.0, 480.0, 40.0, 20.0, 10.0, 30.0).unwrap();
        let x_scale =
            AxisScale::new(ScaleKind::Linear, 0.0, 10.0, 40.0, 620.0, 1.0, false).unwrap();
        let y_scale =
            AxisScale::new(ScaleKind::Linear, 0.0, 10.0, 450.0, 10.0, 1.0, false).unwrap();
        let batch = SceneBatch::new(
            layout,
            11,
            12,
            x_scale,
            y_scale,
            &[0, 1, 1, 2],
            &[101, 201, 201, 301],
            &[1, 2, 2, 3],
            &[0; 16],
            &[0; 16],
            &[0.0, 2.0, 1.0, 0.0],
            &[16.0, 0.0, 0.0, 0.0],
            &[ScatterSymbol::Diamond as u8, 0, 0, 0],
            &[-0.1, -1.0, 10.0, 2.0],
            &[5.0, 1.0, 9.0, 3.0],
            &[-0.1, -1.0, 10.0, 4.0],
            &[5.0, 1.0, 9.0, 7.0],
        )
        .unwrap();
        let encoded = batch.encode();
        assert_eq!(&encoded[..4], b"XYGS");
        assert_eq!(
            u32::from_le_bytes(encoded[4..8].try_into().unwrap()),
            SCENE_VERSION
        );
        assert_eq!(u64::from_le_bytes(encoded[16..24].try_into().unwrap()), 4);
        assert_eq!(
            encoded.len(),
            SCENE_BATCH_HEADER_BYTES
                + 4 * SCENE_STYLE_RECORD_BYTES
                + 4 * SCENE_BATCH_RECORD_BYTES
                + SCENE_CHROME_TRAILER_BYTES
        );
        assert_eq!(u64::from_le_bytes(encoded[24..32].try_into().unwrap()), 4);
        assert_eq!(u64::from_le_bytes(encoded[80..88].try_into().unwrap()), 11);
        assert_eq!(u64::from_le_bytes(encoded[88..96].try_into().unwrap()), 12);
        let records = SCENE_BATCH_HEADER_BYTES + 4 * SCENE_STYLE_RECORD_BYTES;
        // The diamond center maps left of the plot, but its canonical
        // symbol-specific extent overlaps and must remain renderable.
        assert_eq!(encoded[records + 1], 1);
        assert_eq!(encoded[records + 2], ScatterSymbol::Diamond as u8);
        assert_eq!(
            f64::from_le_bytes(encoded[records + 48..records + 56].try_into().unwrap()),
            16.0
        );
        assert_eq!(encoded[records + SCENE_BATCH_RECORD_BYTES + 1], 1);
        assert_eq!(&encoded[records + 32..records + 48], &[0; 16]);
        let line0 = records + SCENE_BATCH_RECORD_BYTES;
        let line1 = line0 + SCENE_BATCH_RECORD_BYTES;
        assert_eq!(
            u64::from_le_bytes(encoded[line0 + 8..line0 + 16].try_into().unwrap()),
            201
        );
        assert_eq!(
            u64::from_le_bytes(encoded[line1 + 8..line1 + 16].try_into().unwrap()),
            201
        );
        assert_eq!(&encoded[line0 + 32..line0 + 48], &[0; 16]);
        let rect = line1 + SCENE_BATCH_RECORD_BYTES;
        let rect_coords: Vec<f64> = (0..4)
            .map(|slot| {
                f64::from_le_bytes(
                    encoded[rect + 16 + slot * 8..rect + 24 + slot * 8]
                        .try_into()
                        .unwrap(),
                )
            })
            .collect();
        assert_eq!(rect_coords, vec![156.0, 142.0, 272.0, 318.0]);
        assert_eq!(
            validate_scene_batch(&encoded),
            Ok(SceneBatchSummary {
                records: 4,
                styles: 4
            })
        );

        let mut incompatible = encoded.clone();
        incompatible[4..8].copy_from_slice(&(SCENE_VERSION + 1).to_le_bytes());
        assert_eq!(
            validate_scene_batch(&incompatible),
            Err(SceneError::Version)
        );

        let mut bad_style = encoded.clone();
        bad_style[records + 4..records + 8].copy_from_slice(&99u32.to_le_bytes());
        assert_eq!(validate_scene_batch(&bad_style), Err(SceneError::Length));

        let mut nonfinite = encoded.clone();
        nonfinite[records + 16..records + 24].copy_from_slice(&f64::NAN.to_le_bytes());
        assert_eq!(validate_scene_batch(&nonfinite), Err(SceneError::NonFinite));
        assert_eq!(
            validate_scene_batch(&encoded[..encoded.len() - 1]),
            Err(SceneError::Length)
        );
    }

    #[test]
    fn browser_painter_keeps_same_style_annotations_as_distinct_descriptors() {
        let layout = PlotLayout::new(240.0, 160.0, 20.1, 20.3, 20.1, 20.3).unwrap();
        let x_scale = AxisScale::new(
            ScaleKind::Linear,
            0.0,
            1.0,
            layout.left,
            layout.right,
            1.0,
            false,
        )
        .unwrap();
        let y_scale = AxisScale::new(
            ScaleKind::Linear,
            0.0,
            1.0,
            layout.bottom,
            layout.top,
            1.0,
            false,
        )
        .unwrap();
        let marker = SCENE_ANNOTATION_ID_PREFIX | (3 << 40);
        let band = SCENE_ANNOTATION_ID_PREFIX | (2 << 40);
        let rule = SCENE_ANNOTATION_ID_PREFIX | (1 << 40);
        let valid_rule = SceneBatch::new_with_chrome(
            layout,
            1,
            2,
            x_scale,
            y_scale,
            SceneChromeStyle::default(),
            SceneChromeText::default(),
            &[1, 1],
            &[rule, rule],
            &[0, 0],
            &[0, 0, 0, 0],
            &[255, 0, 0, 255],
            &[1.0],
            &[0.0, 0.0],
            &[0, 0],
            &[0.25, 0.25],
            &[0.0, 1.0],
            &[0.0, 0.0],
            &[0.0, 0.0],
        )
        .unwrap()
        .encode();
        let mut malformed_rule = valid_rule;
        malformed_rule
            [SCENE_BATCH_HEADER_BYTES + SCENE_STYLE_RECORD_BYTES + SCENE_BATCH_RECORD_BYTES] =
            SceneRecordKind::Scatter as u8;
        assert_eq!(
            SceneDocument::decode(&malformed_rule).err(),
            Some(SceneError::Length)
        );
        assert_eq!(
            validate_scene_batch(&malformed_rule),
            Err(SceneError::Length)
        );
        assert_eq!(
            SceneBatch::new_with_chrome(
                layout,
                1,
                2,
                x_scale,
                y_scale,
                SceneChromeStyle::default(),
                SceneChromeText::default(),
                &[1, 0],
                &[rule, rule],
                &[0, 0],
                &[0, 0, 0, 0],
                &[255, 0, 0, 255],
                &[1.0],
                &[0.0, 0.0],
                &[0, 0],
                &[0.25, 0.25],
                &[0.0, 1.0],
                &[0.0, 0.0],
                &[0.0, 0.0],
            )
            .err(),
            Some(SceneError::Length)
        );
        let encoded = SceneBatch::new_with_chrome(
            layout,
            1,
            2,
            x_scale,
            y_scale,
            SceneChromeStyle::default(),
            SceneChromeText::default(),
            &[0, 0, 2, 2],
            &[marker, marker | 1, band | 2, band | 3],
            &[0, 0, 1, 1],
            &[37, 99, 235, 255, 100, 116, 139, 36],
            &[255, 255, 255, 255, 100, 116, 139, 36],
            &[1.0, 0.0],
            &[8.0, 8.0, 0.0, 0.0],
            &[0, 0, 0, 0],
            &[0.2, 0.8, 0.1, 0.6],
            &[0.3, 0.7, 0.0, 0.0],
            &[0.0, 0.0, 0.2, 0.9],
            &[0.0, 0.0, 1.0, 1.0],
        )
        .unwrap()
        .encode();
        let painter = SceneDocument::decode(&encoded)
            .unwrap()
            .to_browser_painter(16_384)
            .unwrap();
        assert_eq!(u32::from_le_bytes(painter[20..24].try_into().unwrap()), 4);
    }

    #[test]
    fn scene_v3_document_drives_svg_and_raster_from_same_records() {
        let layout = PlotLayout::new(120.0, 100.0, 10.0, 10.0, 10.0, 10.0).unwrap();
        let sx = AxisScale::new(ScaleKind::Linear, 0.0, 10.0, 10.0, 110.0, 1.0, false).unwrap();
        let sy = AxisScale::new(ScaleKind::Linear, 0.0, 10.0, 90.0, 10.0, 1.0, false).unwrap();
        let encoded = SceneBatch::new(
            layout,
            1,
            2,
            sx,
            sy,
            &[0, 1, 1, 2],
            &[10, 20, 20, 30],
            &[0, 1, 1, 2],
            &[57, 135, 229, 255, 0, 0, 0, 0, 57, 135, 229, 180],
            &[0, 0, 0, 255, 239, 68, 68, 255, 0, 0, 0, 255],
            &[1.0, 2.0, 1.0],
            &[8.0, 0.0, 0.0, 0.0],
            &[2, 0, 0, 0],
            &[2.0, 1.0, 8.0, 4.0],
            &[3.0, 2.0, 7.0, 1.0],
            &[0.0, 0.0, 0.0, 6.0],
            &[0.0, 0.0, 0.0, 5.0],
        )
        .unwrap()
        .encode();
        let document = SceneDocument::decode(&encoded).unwrap();
        let svg = document.to_svg();
        assert!(svg.starts_with("<svg "));
        assert!(
            svg.contains("<path d=\"M ")
                && svg.contains("<polyline points=\"")
                && svg.contains("<rect x=\"")
        );
        let x_ticks = document.x_scale.ticks(100.0, true).unwrap();
        let y_ticks = document.y_scale.ticks(80.0, false).unwrap();
        let reserved_capacity = document.raster_command_capacity(&x_ticks, &y_ticks);
        let commands = document.to_raster_commands(2.0).unwrap();
        assert!(commands.len() <= reserved_capacity);
        assert!(commands.capacity() >= reserved_capacity);
        assert!(commands.contains(&4)); // point
        assert!(commands.contains(&3)); // polyline + axes
        assert!(commands.contains(&1)); // rectangle fill
        assert!(crate::raster::rasterize_into(
            &commands,
            240,
            200,
            &mut vec![0; 240 * 200 * 4]
        ));
        let painter = document.to_browser_painter(4096).unwrap();
        let painter_len = painter.len();
        assert_eq!(&painter[..4], b"XYPB");
        assert_eq!(u32::from_le_bytes(painter[20..24].try_into().unwrap()), 3);
        assert_eq!(
            [
                painter[BROWSER_PAINTER_HEADER_BYTES],
                painter[BROWSER_PAINTER_HEADER_BYTES + BROWSER_PAINTER_TRACE_BYTES],
                painter[BROWSER_PAINTER_HEADER_BYTES + 2 * BROWSER_PAINTER_TRACE_BYTES],
            ],
            [0, 1, 2]
        );
        assert_eq!(
            u32::from_le_bytes(
                painter[BROWSER_PAINTER_HEADER_BYTES + 200..BROWSER_PAINTER_HEADER_BYTES + 204]
                    .try_into()
                    .unwrap()
            ),
            10
        );
        assert_eq!(
            u32::from_le_bytes(
                painter[BROWSER_PAINTER_HEADER_BYTES + 224..BROWSER_PAINTER_HEADER_BYTES + 228]
                    .try_into()
                    .unwrap()
            ),
            20
        );
        assert_eq!(
            u32::from_le_bytes(
                painter[BROWSER_PAINTER_HEADER_BYTES + 256..BROWSER_PAINTER_HEADER_BYTES + 260]
                    .try_into()
                    .unwrap()
            ),
            30
        );
        assert!(u32::from_le_bytes(painter[48..52].try_into().unwrap()) >= 3);
        assert!(u32::from_le_bytes(painter[52..56].try_into().unwrap()) >= 3);
        assert_eq!(
            document.to_browser_painter(painter_len - 1),
            Err(SceneError::Limit)
        );

        let mut malformed = encoded;
        malformed[4] = 99;
        assert!(SceneDocument::decode(&malformed).is_err());
        let mut bad_reserved = malformed.clone();
        bad_reserved[4..8].copy_from_slice(&SCENE_VERSION.to_le_bytes());
        bad_reserved[98] = 1;
        assert!(SceneDocument::decode(&bad_reserved).is_err());
        let mut bad_kind = bad_reserved.clone();
        bad_kind[98] = 0;
        bad_kind[SCENE_BATCH_HEADER_BYTES + 3 * SCENE_STYLE_RECORD_BYTES] = 9;
        assert!(SceneDocument::decode(&bad_kind).is_err());
        assert!(SceneDocument::decode(&bad_kind[..bad_kind.len() - 1]).is_err());
    }

    #[test]
    fn browser_painter_rejects_record_fragmentation_before_descriptor_allocation() {
        let make_document = |count: usize| {
            let layout = PlotLayout::new(120.0, 100.0, 10.0, 10.0, 10.0, 10.0).unwrap();
            let sx = AxisScale::new(ScaleKind::Linear, 0.0, 1.0, 10.0, 110.0, 1.0, false).unwrap();
            let sy = AxisScale::new(ScaleKind::Linear, 0.0, 1.0, 90.0, 10.0, 1.0, false).unwrap();
            let symbols: Vec<u8> = (0..count).map(|index| (index % 2) as u8).collect();
            let coordinates = vec![0.5; count];
            let zeros = vec![0.0; count];
            let encoded = SceneBatch::new(
                layout,
                1,
                2,
                sx,
                sy,
                &vec![0; count],
                &vec![7; count],
                &vec![0; count],
                &[57, 135, 229, 255],
                &[0, 0, 0, 0],
                &[0.0],
                &vec![4.0; count],
                &symbols,
                &coordinates,
                &coordinates,
                &zeros,
                &zeros,
            )
            .unwrap()
            .encode();
            SceneDocument::decode(&encoded).unwrap()
        };
        let boundary = make_document(MAX_BROWSER_PAINTER_TRACES);
        let painter = boundary.to_browser_painter(1024 * 1024).unwrap();
        assert_eq!(
            u32::from_le_bytes(painter[20..24].try_into().unwrap()) as usize,
            MAX_BROWSER_PAINTER_TRACES
        );
        let fragmented = make_document(MAX_BROWSER_PAINTER_TRACES + 1);
        assert_eq!(
            fragmented.to_browser_painter(1024 * 1024),
            Err(SceneError::PainterTraceLimit)
        );
    }

    #[test]
    fn polyline_style_changes_are_canonical_run_breaks_for_all_consumers() {
        let encode = |style_refs: &[u32; 4]| {
            SceneBatch::new(
                PlotLayout::new(120.0, 100.0, 10.0, 10.0, 10.0, 10.0).unwrap(),
                1,
                2,
                AxisScale::new(ScaleKind::Linear, 0.0, 3.0, 10.0, 110.0, 1.0, false).unwrap(),
                AxisScale::new(ScaleKind::Linear, 0.0, 3.0, 90.0, 10.0, 1.0, false).unwrap(),
                &[1, 1, 1, 1],
                &[7, 7, 7, 7],
                style_refs,
                &[0; 8],
                &[239, 68, 68, 255, 37, 99, 235, 255],
                &[2.0, 2.0],
                &[0.0; 4],
                &[0; 4],
                &[0.0, 1.0, 2.0, 3.0],
                &[0.0, 1.0, 1.0, 2.0],
                &[0.0; 4],
                &[0.0; 4],
            )
            .unwrap()
            .encode()
        };
        let same = SceneDocument::decode(&encode(&[0, 0, 0, 0])).unwrap();
        let split = SceneDocument::decode(&encode(&[0, 0, 1, 1])).unwrap();
        assert_eq!(same.to_svg().matches("<polyline ").count(), 1);
        assert_eq!(split.to_svg().matches("<polyline ").count(), 2);
        assert!(
            split.to_raster_commands(1.0).unwrap().len()
                > same.to_raster_commands(1.0).unwrap().len()
        );
    }

    #[test]
    fn scene_raster_rejects_every_nonrepresentable_f32_lowering() {
        let encoded = SceneBatch::new(
            PlotLayout::new(100.0, 80.0, 10.0, 10.0, 10.0, 10.0).unwrap(),
            1,
            2,
            AxisScale::new(ScaleKind::Linear, 0.0, 1.0, 10.0, 90.0, 1.0, false).unwrap(),
            AxisScale::new(ScaleKind::Linear, 0.0, 1.0, 70.0, 10.0, 1.0, false).unwrap(),
            &[0],
            &[1],
            &[0],
            &[0, 0, 0, 255],
            &[0, 0, 0, 255],
            &[1.0],
            &[8.0],
            &[0],
            &[0.5],
            &[0.5],
            &[0.0],
            &[0.0],
        )
        .unwrap()
        .encode();
        let document = SceneDocument::decode(&encoded).unwrap();
        assert_eq!(
            document.to_raster_commands(f64::MAX),
            Err(SceneError::NonFinite)
        );

        let mut extreme_coordinate = encoded.clone();
        let record = SCENE_BATCH_HEADER_BYTES + SCENE_STYLE_RECORD_BYTES;
        extreme_coordinate[record + 16..record + 24].copy_from_slice(&f64::MAX.to_le_bytes());
        assert_eq!(
            SceneDocument::decode(&extreme_coordinate)
                .unwrap()
                .to_raster_commands(1.0),
            Err(SceneError::NonFinite)
        );

        let mut extreme_width = encoded;
        extreme_width[SCENE_BATCH_HEADER_BYTES + 8..SCENE_BATCH_HEADER_BYTES + 16]
            .copy_from_slice(&f64::MAX.to_le_bytes());
        assert_eq!(
            SceneDocument::decode(&extreme_width)
                .unwrap()
                .to_raster_commands(1.0),
            Err(SceneError::NonFinite)
        );

        let huge_layout = PlotLayout::new(f64::MAX, f64::MAX, 0.0, 0.0, 0.0, 0.0).unwrap();
        let huge = SceneBatch::new(
            huge_layout,
            1,
            2,
            AxisScale::new(ScaleKind::Linear, 0.0, 1.0, 0.0, f64::MAX, 1.0, false).unwrap(),
            AxisScale::new(ScaleKind::Linear, 0.0, 1.0, f64::MAX, 0.0, 1.0, false).unwrap(),
            &[],
            &[],
            &[],
            &[],
            &[],
            &[],
            &[],
            &[],
            &[],
            &[],
            &[],
            &[],
        )
        .unwrap()
        .encode();
        assert_eq!(
            SceneDocument::decode(&huge)
                .unwrap()
                .to_raster_commands(1.0),
            Err(SceneError::NonFinite)
        );
    }

    #[test]
    fn canonical_symbol_extents_drive_scene_clipping() {
        let layout = PlotLayout::new(100.0, 100.0, 10.0, 10.0, 10.0, 10.0).unwrap();
        let scale = AxisScale::new(ScaleKind::Linear, 0.0, 80.0, 10.0, 90.0, 1.0, false).unwrap();
        let batch = SceneBatch::new(
            layout,
            1,
            2,
            scale,
            scale,
            &[0, 0, 0, 0],
            &[1, 2, 3, 4],
            &[0; 4],
            &[0; 4],
            &[0; 4],
            &[0.0],
            &[20.0; 4],
            &[
                ScatterSymbol::Diamond as u8,
                ScatterSymbol::Diamond as u8,
                ScatterSymbol::ThinDiamond as u8,
                ScatterSymbol::ThinDiamond as u8,
            ],
            &[-12.0, -14.2, 40.0, 40.0],
            &[40.0, 40.0, -12.0, -14.2],
            &[0.0; 4],
            &[0.0; 4],
        )
        .unwrap();
        let encoded = batch.encode();
        let records = SCENE_BATCH_HEADER_BYTES + SCENE_STYLE_RECORD_BYTES;
        assert_eq!(encoded[records + 1], 1);
        assert_eq!(encoded[records + SCENE_BATCH_RECORD_BYTES + 1], 0);
        assert_eq!(encoded[records + 2 * SCENE_BATCH_RECORD_BYTES + 1], 1);
        assert_eq!(encoded[records + 3 * SCENE_BATCH_RECORD_BYTES + 1], 0);

        let line = MarkerGeometry::new(ScatterSymbol::PlusLine, 0.0, 0.0);
        assert_eq!(line.radius, 0.0);
        assert_eq!(line.stroke_width, 1.0);
        assert_eq!(line.extent_x, 0.5);
        assert_eq!(line.extent_y, 0.5);
    }

    #[test]
    fn log_mask_maps_only_coordinates_used_by_each_record_kind() {
        let layout = PlotLayout::new(100.0, 100.0, 10.0, 10.0, 10.0, 10.0).unwrap();
        let scale = AxisScale::new(ScaleKind::Log, 1.0, 10.0, 10.0, 90.0, 1.0, true).unwrap();
        let batch = SceneBatch::new(
            layout,
            1,
            2,
            scale,
            scale,
            &[0, 1, 1, 1, 2, 2],
            &[1, 20, 20, 20, 30, 31],
            &[0; 6],
            &[0; 4],
            &[0; 4],
            &[0.0],
            &[6.0, 0.0, 0.0, 0.0, 0.0, 0.0],
            &[0; 6],
            &[2.0, 2.0, 0.0, 4.0, 2.0, 2.0],
            &[2.0; 6],
            &[0.0, 0.0, 0.0, 0.0, 8.0, 0.0],
            &[0.0, 0.0, 0.0, 0.0, 8.0, 8.0],
        )
        .unwrap();
        let encoded = batch.encode();
        let records = SCENE_BATCH_HEADER_BYTES + SCENE_STYLE_RECORD_BYTES;
        let flags: Vec<u8> = (0..6)
            .map(|index| encoded[records + index * SCENE_BATCH_RECORD_BYTES + 1])
            .collect();
        assert_eq!(flags, vec![1, 1, 0, 1, 1, 0]);
        // Reserved zeros never enter log-mask mapping and are always emitted
        // as zero. The masked middle vertex breaks the stable-id 20 run.
        for index in [0, 1, 3] {
            let record = records + index * SCENE_BATCH_RECORD_BYTES;
            assert_eq!(&encoded[record + 32..record + 48], &[0; 16]);
        }
        assert_eq!(
            &encoded[records + 2 * SCENE_BATCH_RECORD_BYTES + 16
                ..records + 2 * SCENE_BATCH_RECORD_BYTES + 48],
            &[0; 32]
        );
    }

    #[test]
    fn scene_v3_batch_rejects_bad_bounds_lengths_kinds_and_nonfinite_input() {
        assert_eq!(
            PlotLayout::new(10.0, 10.0, 6.0, 4.0, 0.0, 0.0),
            Err(SceneError::NonFinite)
        );
        let layout = PlotLayout::new(10.0, 10.0, 1.0, 1.0, 1.0, 1.0).unwrap();
        let scale = AxisScale::new(ScaleKind::Linear, 0.0, 1.0, 1.0, 9.0, 1.0, false).unwrap();
        assert_eq!(
            SceneBatch::new(
                layout,
                1,
                2,
                scale,
                scale,
                &[9],
                &[1],
                &[0],
                &[0; 4],
                &[0; 4],
                &[0.0],
                &[1.0],
                &[0],
                &[0.0],
                &[0.0],
                &[0.0],
                &[0.0]
            )
            .err(),
            Some(SceneError::Length)
        );
        assert_eq!(
            SceneBatch::new(
                layout,
                1,
                2,
                scale,
                scale,
                &[0],
                &[],
                &[0],
                &[0; 4],
                &[0; 4],
                &[0.0],
                &[1.0],
                &[0],
                &[0.0],
                &[0.0],
                &[0.0],
                &[0.0]
            )
            .err(),
            Some(SceneError::Length)
        );
        assert_eq!(
            SceneBatch::new(
                layout,
                1,
                2,
                scale,
                scale,
                &[0],
                &[1],
                &[0],
                &[0; 4],
                &[0; 4],
                &[0.0],
                &[1.0],
                &[0],
                &[f64::NAN],
                &[0.0],
                &[0.0],
                &[0.0]
            )
            .err(),
            Some(SceneError::NonFinite)
        );
        let invalid_record = |style_ref, diameter, symbol| {
            SceneBatch::new(
                layout,
                1,
                2,
                scale,
                scale,
                &[0],
                &[1],
                &[style_ref],
                &[0; 4],
                &[0; 4],
                &[0.0],
                &[diameter],
                &[symbol],
                &[0.0],
                &[0.0],
                &[0.0],
                &[0.0],
            )
            .err()
        };
        assert_eq!(invalid_record(1, 1.0, 0), Some(SceneError::Length));
        assert_eq!(invalid_record(0, 1.0, 19), Some(SceneError::Length));
        assert_eq!(invalid_record(0, -1.0, 0), Some(SceneError::NonFinite));
        assert_eq!(
            SceneBatch::new(
                layout,
                1,
                2,
                scale,
                scale,
                &[],
                &[],
                &[],
                &[],
                &[],
                &vec![0.0; MAX_SCENE_STYLES + 1],
                &[],
                &[],
                &[],
                &[],
                &[],
                &[],
            )
            .err(),
            Some(SceneError::Limit)
        );
    }

    #[test]
    fn scatter_scene_rejects_bad_lengths_nonfinite_and_negative_sizes() {
        assert_eq!(
            ScatterScene::new(
                &[1.0],
                &[],
                &[1.0],
                &[0; 4],
                &[0; 4],
                &[0.0],
                &[0],
                None,
                None,
                None,
            )
            .err(),
            Some(SceneError::Length)
        );
        assert_eq!(
            ScatterScene::new(
                &[f64::NAN],
                &[1.0],
                &[1.0],
                &[0; 4],
                &[0; 4],
                &[0.0],
                &[0],
                None,
                None,
                None,
            )
            .err(),
            Some(SceneError::NonFinite)
        );
        assert_eq!(
            ScatterScene::new(
                &[1.0],
                &[1.0],
                &[-1.0],
                &[0; 4],
                &[0; 4],
                &[0.0],
                &[0],
                None,
                None,
                None,
            )
            .err(),
            Some(SceneError::NegativeSize)
        );
    }

    #[test]
    fn scatter_scene_rejects_limit_and_invalid_paint() {
        let too_many = vec![0.0; MAX_SCENE_MARKS + 1];
        assert_eq!(
            ScatterScene::new(&too_many, &[], &[], &[], &[], &[], &[], None, None, None,).err(),
            Some(SceneError::Limit)
        );
        assert_eq!(
            ScatterScene::new(
                &[1.0],
                &[1.0],
                &[1.0],
                &[0; 4],
                &[0; 4],
                &[0.0],
                &[0],
                None,
                Some("not-a-color"),
                None,
            )
            .err(),
            Some(SceneError::InvalidPaint)
        );
    }

    #[test]
    fn scatter_scene_hides_marks_and_preserves_constant_css_paint() {
        let scene = ScatterScene::new(
            &[10.0, 20.0],
            &[11.0, 21.0],
            &[8.0, 10.0],
            &[37, 99, 235, 255, 239, 68, 68, 128],
            &[0; 8],
            &[0.0, 0.0],
            &[ScatterSymbol::Circle as u8, ScatterSymbol::Circle as u8],
            Some(&[0, 1]),
            Some("var(--brand)"),
            None,
        )
        .unwrap();
        assert_eq!(
            scene.to_svg(),
            "<g><circle cx=\"20\" cy=\"21\" r=\"5\" fill=\"var(--brand)\" fill-opacity=\"0.5\"/></g>"
        );

        let mut escaped = String::new();
        push_escaped_attribute(&mut escaped, "&<>\"");
        assert_eq!(escaped, "&amp;&lt;&gt;&quot;");
    }

    #[test]
    fn symbol_shape_families_have_deterministic_svg() {
        let mut outputs = Vec::new();
        for symbol in [
            ScatterSymbol::Square,
            ScatterSymbol::Diamond,
            ScatterSymbol::Triangle,
            ScatterSymbol::Cross,
            ScatterSymbol::X,
            ScatterSymbol::Pentagon,
            ScatterSymbol::Star,
        ] {
            let mut output = String::new();
            push_symbol(&mut output, symbol, 10.0, 20.0, 2.0);
            outputs.push(output);
        }
        assert!(outputs.iter().map(String::as_str).eq([
            "<rect x=\"8\" y=\"18\" width=\"4\" height=\"4\"",
            "<path d=\"M 10 17.17 L 12.83 20 L 10 22.83 L 7.17 20 Z\"",
            "<path d=\"M 10 18 L 12 22 L 8 22 Z\"",
            "<path d=\"M 9.32 18 H 10.68 V 19.32 H 12 V 20.68 H 10.68 V 22 H 9.32 V 20.68 H 8 V 19.32 H 9.32 Z\"",
            "<path d=\"M 8.56 18 L 10 19.44 L 11.44 18 L 12 18.56 L 10.56 20 L 12 21.44 L 11.44 22 L 10 20.56 L 8.56 22 L 8 21.44 L 9.44 20 L 8 18.56 Z\"",
            "<path d=\"M 10 18 L 11.9 19.38 L 11.18 21.62 L 8.82 21.62 L 8.1 19.38 Z\"",
            "<path d=\"M 10 18 L 10.53 19.27 L 11.9 19.38 L 10.86 20.28 L 11.18 21.62 L 10 20.9 L 8.82 21.62 L 9.14 20.28 L 8.1 19.38 L 9.47 19.27 Z\"",
        ]));
    }

    #[test]
    fn all_nineteen_symbol_codes_match_svg_and_raster_contract() {
        let mut svg_shapes = Vec::new();
        for code in 0..=18 {
            let symbol = ScatterSymbol::from_code(code);
            assert_eq!(symbol as u8, code);
            let mut shape = String::new();
            push_symbol(&mut shape, symbol, 10.0, 20.0, 2.0);
            svg_shapes.push(shape);
        }
        assert!(svg_shapes[11].contains(" L ")); // x
        assert!(svg_shapes[12].starts_with("<circle")); // point
        assert!(svg_shapes[13].starts_with("<rect")); // pixel
        assert!(svg_shapes[14].contains(" Z\"")); // thin diamond
        assert!(svg_shapes[15].contains(" H ") && svg_shapes[15].contains(" V "));
        assert!(svg_shapes[16].matches(" L ").count() == 2);
        assert!(svg_shapes[17].contains(" H "));
        assert!(svg_shapes[18].contains(" V "));

        let codes: Vec<u8> = (0..=18).collect();
        let x: Vec<f64> = (0..=18).map(f64::from).collect();
        let encoded = SceneBatch::new(
            PlotLayout::new(220.0, 80.0, 10.0, 10.0, 10.0, 10.0).unwrap(),
            1,
            2,
            AxisScale::new(ScaleKind::Linear, 0.0, 18.0, 10.0, 210.0, 1.0, false).unwrap(),
            AxisScale::new(ScaleKind::Linear, 0.0, 1.0, 70.0, 10.0, 1.0, false).unwrap(),
            &[0; 19],
            &(0..19).collect::<Vec<_>>(),
            &[0; 19],
            &[57, 135, 229, 255],
            &[0, 0, 0, 255],
            &[1.0],
            &[8.0; 19],
            &codes,
            &x,
            &[0.5; 19],
            &[0.0; 19],
            &[0.0; 19],
        )
        .unwrap()
        .encode();
        let commands = SceneDocument::decode(&encoded)
            .unwrap()
            .to_raster_commands(1.0)
            .unwrap();
        let grid_count = linear_ticks(0.0, 18.0, 3).unwrap().ticks.len()
            + linear_ticks(0.0, 1.0, 3).unwrap().ticks.len();
        let mut offset = 82 + 17 + grid_count * 35; // two backgrounds, clip, grid
        for code in 0..=18 {
            assert_eq!(commands[offset], 4);
            assert_eq!(commands[offset + 13], code);
            offset += 26;
        }
    }

    #[test]
    fn canonical_linear_and_log_ticks_match_public_policy() {
        assert_eq!(
            linear_ticks(-0.9, 5.1, 6).unwrap(),
            AxisTicks {
                ticks: vec![0.0, 1.0, 2.0, 3.0, 4.0, 5.0],
                labeled: vec![0.0, 1.0, 2.0, 3.0, 4.0, 5.0],
                step: 1.0,
            }
        );
        let log = log_ticks(0.1, 100.0, 6).unwrap();
        assert_eq!(
            log.ticks,
            vec![0.1, 0.2, 0.5, 1.0, 2.0, 5.0, 10.0, 20.0, 50.0, 100.0]
        );
        assert_eq!(log.labeled, vec![0.1, 1.0, 10.0, 100.0]);
        assert_eq!(log.step, 1.0);
    }

    #[test]
    fn category_and_angular_ticks_match_host_policy() {
        assert_eq!(
            category_ticks(-0.5, 9.5, 10, 5).unwrap().ticks,
            vec![0.0, 2.0, 4.0, 6.0, 8.0]
        );
        let degrees = angular_ticks(0.0, 360.0, true, 8).unwrap();
        assert_eq!(degrees.step, 45.0);
        assert_eq!(degrees.ticks.first().copied(), Some(0.0));
        assert!(!degrees.ticks.iter().any(|v| (*v - 360.0).abs() < 1e-9));
        let radians = angular_ticks(0.0, std::f64::consts::TAU, false, 8).unwrap();
        assert!((radians.step - std::f64::consts::FRAC_PI_4).abs() < 1e-12);
    }

    #[test]
    fn time_ticks_match_host_fixed_and_calendar_policy() {
        let hour = time_ticks(0.0, 3.0 * MS_H, 6).unwrap();
        assert_eq!(hour.step, 30.0 * MS_M);
        assert_eq!(
            hour.ticks,
            vec![
                0.0,
                30.0 * MS_M,
                MS_H,
                90.0 * MS_M,
                2.0 * MS_H,
                150.0 * MS_M,
                3.0 * MS_H
            ]
        );

        // ~two years → six-month calendar ticks (months_rough ≈ 4.06 → step_m = 6).
        let lo = utc_ms_from_year_month0(2020, 0);
        let hi = utc_ms_from_year_month0(2022, 0);
        let cal = time_ticks(lo, hi, 6).unwrap();
        assert_eq!(cal.step, 6.0 * 30.0 * MS_D);
        assert_eq!(
            cal.ticks,
            vec![
                lo,
                utc_ms_from_year_month0(2020, 6),
                utc_ms_from_year_month0(2021, 0),
                utc_ms_from_year_month0(2021, 6),
                hi,
            ]
        );
        assert_eq!(utc_year_month0_from_ms(lo), (2020, 0));
        assert_eq!(utc_year_month0_from_ms(hi), (2022, 0));
    }

    #[test]
    fn scene_v6_band_fills_closed_path_from_top_and_base() {
        let layout = PlotLayout::new(200.0, 120.0, 20.0, 10.0, 20.0, 20.0).unwrap();
        let x = AxisScale::new(
            ScaleKind::Linear,
            0.0,
            2.0,
            layout.left,
            layout.right,
            1.0,
            false,
        )
        .unwrap();
        let y = AxisScale::new(
            ScaleKind::Linear,
            0.0,
            2.0,
            layout.bottom,
            layout.top,
            1.0,
            false,
        )
        .unwrap();
        let batch = SceneBatch::new(
            layout,
            1,
            2,
            x,
            y,
            &[3, 3],
            &[9, 9],
            &[0, 0],
            &[57, 99, 235, 180],
            &[0, 0, 0, 0],
            &[0.0],
            &[0.0, 0.0],
            &[0, 0],
            &[0.0, 2.0],
            &[1.0, 1.5],
            &[0.0, 2.0],
            &[0.0, 0.0],
        )
        .unwrap();
        let encoded = batch.encode();
        assert_eq!(
            u32::from_le_bytes(encoded[4..8].try_into().unwrap()),
            SCENE_VERSION
        );
        let svg = SceneDocument::decode(&encoded).unwrap().to_svg();
        assert!(svg.contains("<path d=\"M "));
        assert!(svg.contains(" Z\""));
        let commands = SceneDocument::decode(&encoded)
            .unwrap()
            .to_raster_commands(1.0)
            .unwrap();
        assert!(commands.contains(&1), "band fill poly opcode missing");
    }

    #[test]
    fn scene_v7_polyfill_closes_triangle_path() {
        let layout = PlotLayout::new(200.0, 120.0, 20.0, 10.0, 20.0, 20.0).unwrap();
        let x = AxisScale::new(
            ScaleKind::Linear,
            0.0,
            1.0,
            layout.left,
            layout.right,
            1.0,
            false,
        )
        .unwrap();
        let y = AxisScale::new(
            ScaleKind::Linear,
            0.0,
            1.0,
            layout.bottom,
            layout.top,
            1.0,
            false,
        )
        .unwrap();
        let batch = SceneBatch::new(
            layout,
            1,
            2,
            x,
            y,
            &[4, 4, 4],
            &[9, 9, 9],
            &[0, 0, 0],
            &[34, 197, 94, 255],
            &[0, 0, 0, 0],
            &[0.0],
            &[0.0, 0.0, 0.0],
            &[0, 0, 0],
            &[0.0, 1.0, 0.5],
            &[0.0, 0.0, 1.0],
            &[0.0, 0.0, 0.0],
            &[0.0, 0.0, 0.0],
        )
        .unwrap();
        let encoded = batch.encode();
        assert_eq!(
            u32::from_le_bytes(encoded[4..8].try_into().unwrap()),
            SCENE_VERSION
        );
        let svg = SceneDocument::decode(&encoded).unwrap().to_svg();
        assert!(svg.contains("<path d=\"M "));
        assert!(svg.contains(" Z\""));
        let commands = SceneDocument::decode(&encoded)
            .unwrap()
            .to_raster_commands(1.0)
            .unwrap();
        assert!(commands.contains(&1));
    }

    #[test]
    fn scene_v5_encodes_authored_chrome_text() {
        let layout = PlotLayout::new(200.0, 120.0, 40.0, 20.0, 20.0, 30.0).unwrap();
        let x = AxisScale::new(
            ScaleKind::Linear,
            0.0,
            1.0,
            layout.left,
            layout.right,
            1.0,
            false,
        )
        .unwrap();
        let y = AxisScale::new(
            ScaleKind::Linear,
            0.0,
            1.0,
            layout.bottom,
            layout.top,
            1.0,
            false,
        )
        .unwrap();
        let text = SceneChromeText::from_parts("Hello", "x", "y").unwrap();
        let batch = SceneBatch::new_with_chrome(
            layout,
            1,
            2,
            x,
            y,
            SceneChromeStyle::default(),
            text,
            &[],
            &[],
            &[],
            &[],
            &[],
            &[],
            &[],
            &[],
            &[],
            &[],
            &[],
            &[],
        )
        .unwrap();
        let encoded = batch.encode();
        assert_eq!(
            u32::from_le_bytes(encoded[4..8].try_into().unwrap()),
            SCENE_VERSION
        );
        assert!(encoded.ends_with(b"Helloxy"));
        let svg = SceneDocument::decode(&encoded).unwrap().to_svg();
        assert!(svg.contains("data-xy-chrome=\"title\""));
        assert!(svg.contains("Hello"));
        assert!(svg.contains("data-xy-chrome=\"x-label\""));
        assert!(svg.contains("data-xy-chrome=\"y-label\""));
    }

    #[test]
    fn explicit_hidden_cartesian_chrome_is_not_emitted_or_mistaken_for_polar() {
        let layout = PlotLayout::new(200.0, 120.0, 40.0, 20.0, 20.0, 30.0).unwrap();
        let x = AxisScale::new(
            ScaleKind::Linear,
            0.0,
            1.0,
            layout.left,
            layout.right,
            1.0,
            false,
        )
        .unwrap();
        let y = AxisScale::new(
            ScaleKind::Linear,
            0.0,
            1.0,
            layout.bottom,
            layout.top,
            1.0,
            false,
        )
        .unwrap();
        let mut chrome = SceneChromeStyle::default();
        for axis in [&mut chrome.x_axis, &mut chrome.y_axis] {
            axis.tick_sides = 0;
            axis.tick_label_sides = 0;
            axis.axis_rgba[3] = 0;
            axis.grid_rgba[3] = 0;
            axis.minor_grid_rgba[3] = 0;
            axis.minor_tick_rgba[3] = 0;
            axis.label_rgba[3] = 0;
            axis.axis_width = 0.0;
            axis.grid_width = 0.0;
            axis.tick_width = 0.0;
            axis.tick_length = 0.0;
            axis.minor_grid_width = 0.0;
            axis.minor_tick_width = 0.0;
            axis.minor_tick_length = 0.0;
        }
        let encoded = SceneBatch::new_with_chrome(
            layout,
            1,
            2,
            x,
            y,
            chrome,
            SceneChromeText::from_parts("Cartesian title", "", "").unwrap(),
            &[],
            &[],
            &[],
            &[],
            &[],
            &[],
            &[],
            &[],
            &[],
            &[],
            &[],
            &[],
        )
        .unwrap()
        .encode();
        let document = SceneDocument::decode(&encoded).unwrap();
        let svg = document.to_svg();
        assert!(!svg.contains("data-xy-chrome=\"grid\""));
        assert!(!svg.contains("data-xy-chrome=\"axes\""));
        assert!(svg.contains("data-xy-chrome=\"title\""));
        assert!(svg.contains("Cartesian title"));
        assert!(!document.to_raster_commands(1.0).unwrap().is_empty());
    }

    #[test]
    fn scene_v8_cartesian_chrome_round_trips_all_consumers_and_bounds() {
        let layout = PlotLayout::new(200.0, 120.0, 30.0, 20.0, 20.0, 25.0).unwrap();
        let x = AxisScale::new(
            ScaleKind::Linear,
            0.0,
            1.0,
            layout.left,
            layout.right,
            1.0,
            false,
        )
        .unwrap();
        let y = AxisScale::new(
            ScaleKind::Linear,
            0.0,
            1.0,
            layout.bottom,
            layout.top,
            1.0,
            false,
        )
        .unwrap();
        let mut chrome = SceneChromeStyle {
            chart_background_rgba: [1, 2, 3, 255],
            plot_background_rgba: [4, 5, 6, 128],
            ..SceneChromeStyle::default()
        };
        chrome.x_axis.side = AxisSide::High;
        chrome.x_axis.tick_sides = 0b11;
        chrome.x_axis.tick_label_sides = 0b10;
        chrome.x_axis.major_direction = TickDirection::InOut;
        chrome.x_axis.minor_direction = TickDirection::In;
        chrome.x_axis.tick_length = 8.0;
        chrome.x_axis.minor_tick_length = 3.0;
        chrome.x_axis.minor_grid_rgba = [7, 8, 9, 255];
        chrome.x_major_ticks = Some(vec![0.0, 1.0]);
        chrome.x_minor_ticks = vec![0.5];
        let style_input = chrome.style_input();
        let encoded = SceneBatch::new_with_chrome(
            layout,
            1,
            2,
            x,
            y,
            chrome,
            SceneChromeText::from_parts("Chart", "Horizontal", "Vertical").unwrap(),
            &[],
            &[],
            &[],
            &[],
            &[],
            &[],
            &[],
            &[],
            &[],
            &[],
            &[],
            &[],
        )
        .unwrap()
        .encode();
        let document = SceneDocument::decode(&encoded).unwrap();
        let svg = document.to_svg();
        assert!(svg.contains("data-xy-chrome=\"chart-background\""));
        assert!(svg.contains("fill=\"rgba(1,2,3,1.000000)\""));
        assert!(svg.contains("fill=\"rgba(4,5,6,0.501961)\""));
        assert!(svg.contains("stroke=\"rgba(7,8,9,1.000000)\""));
        assert!(svg.contains("y1=\"24\""));
        assert!(svg.contains("y2=\"16\""));
        let raster = document.to_raster_commands(1.0).unwrap();
        assert_eq!(&raster[37..41], &[1, 2, 3, 255]);
        assert_eq!(&raster[78..82], &[4, 5, 6, 128]);
        let painter = document.to_browser_painter(16_384).unwrap();
        assert_eq!(&painter[64..264], style_input.as_slice());
        assert_eq!(u32::from_le_bytes(painter[264..268].try_into().unwrap()), 5);
        assert_eq!(
            u32::from_le_bytes(painter[268..272].try_into().unwrap()),
            10
        );
        assert_eq!(u32::from_le_bytes(painter[272..276].try_into().unwrap()), 8);
        let tick_offset = u32::from_le_bytes(painter[56..60].try_into().unwrap()) as usize;
        let string_offset = u32::from_le_bytes(painter[60..64].try_into().unwrap()) as usize;
        assert_eq!(
            &painter[string_offset..string_offset + 23],
            b"ChartHorizontalVertical"
        );
        let flags = (0..3)
            .map(|index| {
                u32::from_le_bytes(
                    painter[tick_offset + index * 16 + 12..tick_offset + index * 16 + 16]
                        .try_into()
                        .unwrap(),
                )
            })
            .collect::<Vec<_>>();
        assert_eq!(flags, vec![1, 1, 0]);

        let mut malformed = encoded.clone();
        let trailer = SCENE_BATCH_HEADER_BYTES;
        malformed[trailer + 24 + 1] = 4;
        assert_eq!(
            SceneDocument::decode(&malformed).err(),
            Some(SceneError::Length)
        );
        let mut automatic_minor = encoded.clone();
        automatic_minor[trailer + 216..trailer + 220].copy_from_slice(&u32::MAX.to_le_bytes());
        assert_eq!(
            SceneDocument::decode(&automatic_minor).err(),
            Some(SceneError::Length)
        );
        let mut invalid = SceneChromeStyle::default();
        invalid.x_axis.tick_length = MAX_SCENE_CHROME_LENGTH + 1.0;
        assert_eq!(invalid.validated().err(), Some(SceneError::NonFinite));

        let too_many_resolved = SceneChromeStyle {
            x_minor_ticks: vec![0.5; MAX_AXIS_TICKS],
            ..SceneChromeStyle::default()
        };
        assert_eq!(
            SceneBatch::new_with_chrome(
                layout,
                1,
                2,
                x,
                y,
                too_many_resolved,
                SceneChromeText::default(),
                &[],
                &[],
                &[],
                &[],
                &[],
                &[],
                &[],
                &[],
                &[],
                &[],
                &[],
                &[],
            )
            .err(),
            Some(SceneError::Limit)
        );
    }

    #[test]
    fn scene_v9_primary_legend_is_bounded_and_shared_by_all_consumers() {
        let layout = PlotLayout::new(240.0, 160.0, 30.0, 20.0, 20.0, 30.0).unwrap();
        let x = AxisScale::new(
            ScaleKind::Linear,
            0.0,
            1.0,
            layout.left,
            layout.right,
            1.0,
            false,
        )
        .unwrap();
        let y = AxisScale::new(
            ScaleKind::Linear,
            0.0,
            1.0,
            layout.bottom,
            layout.top,
            1.0,
            false,
        )
        .unwrap();
        let legend = SceneLegend {
            location: LegendLocation::UpperRight,
            title: "Series".into(),
            font_size: 11.0,
            title_font_size: 12.0,
            text_rgba: [32, 32, 32, 255],
            frame_fill_rgba: [255, 255, 255, 230],
            frame_stroke_rgba: [32, 32, 32, 71],
            entries: vec![SceneLegendEntry {
                style_ref: 0,
                kind: SceneRecordKind::Scatter,
                symbol: 0,
                fill_rgba: [57, 135, 229, 255],
                stroke_rgba: [0, 0, 0, 0],
                label: "observed".into(),
            }],
        };
        let build = |legend| {
            SceneBatch::new_with_decorations(
                layout,
                1,
                2,
                x,
                y,
                SceneChromeStyle::default(),
                SceneChromeText::default(),
                Some(legend),
                &[0],
                &[7],
                &[0],
                &[57, 135, 229, 255],
                &[0, 0, 0, 0],
                &[0.0],
                &[6.0],
                &[0],
                &[0.5],
                &[0.5],
                &[0.0],
                &[0.0],
            )
        };
        let encoded = build(legend.clone()).unwrap().encode();
        let document = SceneDocument::decode(&encoded).unwrap();
        let svg = document.to_svg();
        assert!(svg.contains("data-xy-chrome=\"legend\""));
        assert!(svg.contains("role=\"listitem\""));
        assert!(svg.contains("observed"));
        assert!(document
            .to_raster_commands(1.0)
            .unwrap()
            .windows(8)
            .any(|bytes| bytes == b"observed"));
        let painter = document.to_browser_painter(16_384).unwrap();
        assert!(painter.windows(4).any(|bytes| bytes == b"XYLG"));
        let geometry = painter
            .windows(4)
            .position(|bytes| bytes == b"XYRG")
            .unwrap();
        assert_eq!(
            u32::from_le_bytes(painter[geometry + 4..geometry + 8].try_into().unwrap()),
            1
        );
        let painter_x =
            f32::from_le_bytes(painter[geometry + 8..geometry + 12].try_into().unwrap());
        assert!(painter_x >= layout.left as f32 + 8.0);

        let mut too_tall = legend.clone();
        too_tall.entries = vec![too_tall.entries[0].clone(); MAX_SCENE_LEGEND_ENTRIES];
        assert_eq!(build(too_tall).err(), Some(SceneError::Limit));
        let mut too_many = legend.clone();
        too_many.entries = vec![too_many.entries[0].clone(); MAX_SCENE_LEGEND_ENTRIES + 1];
        assert_eq!(build(too_many).err(), Some(SceneError::Limit));
        let mut high_font = legend.clone();
        high_font.font_size = 1000.0;
        assert_eq!(build(high_font).err(), Some(SceneError::Limit));
        let mut too_wide = legend.clone();
        too_wide.entries[0].label = "wide".repeat(128);
        assert_eq!(build(too_wide).err(), Some(SceneError::Limit));
        let mut nul_label = legend.clone();
        nul_label.entries[0].label = "bad\0label".into();
        assert_eq!(build(nul_label).err(), Some(SceneError::Limit));
        let mut boundary_symbol = legend.clone();
        boundary_symbol.entries[0].symbol = ScatterSymbol::VerticalLine as u8;
        let boundary_encoded = build(boundary_symbol).unwrap().encode();
        assert!(SceneDocument::decode(&boundary_encoded).is_ok());
        let mut invalid_scatter = legend.clone();
        invalid_scatter.entries[0].symbol = ScatterSymbol::VerticalLine as u8 + 1;
        assert_eq!(build(invalid_scatter).err(), Some(SceneError::Length));
        let mut invalid_non_scatter = legend.clone();
        invalid_non_scatter.entries[0].kind = SceneRecordKind::Polyline;
        invalid_non_scatter.entries[0].symbol = 1;
        assert_eq!(build(invalid_non_scatter).err(), Some(SceneError::Length));
        let mut malformed = encoded.clone();
        let legend_start = malformed
            .windows(4)
            .position(|bytes| bytes == b"XYLG")
            .unwrap();
        malformed[legend_start + 4] = 99;
        assert!(matches!(
            validate_scene_batch(&malformed),
            Err(SceneError::Length)
        ));
    }

    #[test]
    fn viewport_density_and_symlog_coordinate_ticks_match_both_consumers() {
        let narrow = AxisScale::new(ScaleKind::Linear, 0.0, 100.0, 0.0, 200.0, 1.0, false)
            .unwrap()
            .ticks(200.0, true)
            .unwrap();
        let wide = AxisScale::new(ScaleKind::Linear, 0.0, 100.0, 0.0, 1_000.0, 1.0, false)
            .unwrap()
            .ticks(1_000.0, true)
            .unwrap();
        assert!(wide.ticks.len() > narrow.ticks.len());

        for (lo, hi) in [(-100.0, 10.0), (10.0, -100.0)] {
            let layout = PlotLayout::new(420.0, 260.0, 50.0, 20.0, 20.0, 40.0).unwrap();
            let x_scale = AxisScale::new(
                ScaleKind::SymLog,
                lo,
                hi,
                layout.left,
                layout.right,
                2.0,
                false,
            )
            .unwrap();
            let ticks = x_scale.ticks(layout.right - layout.left, true).unwrap();
            assert!(ticks.ticks.iter().any(|value| value.abs() < 1e-12));
            let coordinate_ticks = linear_ticks(x_scale.coord(lo), x_scale.coord(hi), 4).unwrap();
            for (actual, coordinate) in ticks.ticks.iter().zip(&coordinate_ticks.ticks) {
                assert!((actual - x_scale.value(*coordinate)).abs() < 1e-12);
            }

            let encoded = SceneBatch::new(
                layout,
                1,
                2,
                x_scale,
                AxisScale::new(
                    ScaleKind::SymLog,
                    -1.0,
                    1.0,
                    layout.bottom,
                    layout.top,
                    1.0,
                    false,
                )
                .unwrap(),
                &[],
                &[],
                &[],
                &[],
                &[],
                &[],
                &[],
                &[],
                &[],
                &[],
                &[],
                &[],
            )
            .unwrap()
            .encode();
            let document = SceneDocument::decode(&encoded).unwrap();
            let svg_labels = document.to_svg().matches("<text ").count();
            let raster_labels = raster_text_count(&document.to_raster_commands(1.0).unwrap());
            assert_eq!(raster_labels, Some(svg_labels));
            assert!(svg_labels >= 4);
        }
    }

    #[test]
    fn canonical_axis_scales_map_and_invert_all_numeric_kinds() {
        let linear = AxisScale::new(ScaleKind::Linear, 0.0, 10.0, 20.0, 120.0, 1.0, false).unwrap();
        assert_eq!(linear.pixel(5.0), 70.0);
        let log = AxisScale::new(ScaleKind::Log, 0.1, 100.0, 0.0, 300.0, 1.0, false).unwrap();
        assert_eq!(log.pixel(1.0), 100.0);
        assert_eq!(log.coord(-1.0), -300.0);
        let masked = AxisScale::new(ScaleKind::Log, 0.1, 100.0, 0.0, 300.0, 1.0, true).unwrap();
        assert!(masked.coord(0.0).is_nan());
        let symlog =
            AxisScale::new(ScaleKind::SymLog, -10.0, 10.0, 0.0, 100.0, 2.0, false).unwrap();
        let coordinate = symlog.coord(-4.0);
        assert!((symlog.value(coordinate) + 4.0).abs() < 1e-12);
        assert!((symlog.pixel(0.0) - 50.0).abs() < 1e-12);
    }

    #[test]
    fn precomputed_pixel_invariants_preserve_reference_mapping() {
        for (kind, lo, hi, px0, px1, constant, mask, values) in [
            (
                ScaleKind::Linear,
                10.0,
                -2.0,
                700.0,
                20.0,
                1.0,
                false,
                vec![-2.0, 0.0, 10.0, f64::NAN],
            ),
            (
                ScaleKind::Linear,
                4.0,
                4.0,
                8.0,
                18.0,
                1.0,
                false,
                vec![4.0, 5.0],
            ),
            (
                ScaleKind::Log,
                0.1,
                100.0,
                0.0,
                300.0,
                1.0,
                false,
                vec![-1.0, 0.1, 1.0, 100.0, f64::NAN],
            ),
            (
                ScaleKind::Log,
                0.1,
                100.0,
                300.0,
                0.0,
                1.0,
                true,
                vec![0.0, 0.1, 10.0],
            ),
            (
                ScaleKind::SymLog,
                -20.0,
                20.0,
                5.0,
                405.0,
                2.0,
                false,
                vec![-20.0, -1.0, 0.0, 7.0, 20.0],
            ),
        ] {
            let scale = AxisScale::new(kind, lo, hi, px0, px1, constant, mask).unwrap();
            let low = scale.coord(lo);
            let high = scale.coord(hi);
            let span = if high == low { 1.0 } else { high - low };
            for value in values {
                let expected = px0 + (scale.coord(value) - low) / span * (px1 - px0);
                let actual = scale.pixel(value);
                assert!(
                    (expected.is_nan() && actual.is_nan())
                        || expected.to_bits() == actual.to_bits(),
                    "{kind:?} value {value}: expected {expected:?}, got {actual:?}"
                );
            }
        }
    }

    #[test]
    fn scene_support_predicate_is_stable_ordered_and_fail_closed() {
        assert_eq!(scene_support_reason(1, 0), Ok(""));
        assert_eq!(
            scene_support_reason(
                1,
                SCENE_FEATURE_AUTHORED_TICK_LABELS | SCENE_FEATURE_CUSTOM_FONT,
            ),
            Ok("XYG_SCENE_UNSUPPORTED_CUSTOM_FONT: Scene v12 does not encode custom font resources")
        );
        assert_eq!(scene_support_reason(2, 0), Err(SceneError::Version));
        assert_eq!(scene_support_reason(1, 1 << 63), Err(SceneError::Version));
    }

    #[test]
    fn scene_v13_colorbar_is_literal_bounded_and_rejects_unsorted_stops() {
        let colorbar = SceneColorbar {
            horizontal: false,
            domain: [0.0, 1.0],
            stops: vec![(0.0, [0, 0, 0, 255]), (1.0, [255, 255, 255, 255])],
            title: "Intensity".to_owned(),
            text_rgba: [32, 32, 32, 255],
        };
        let encoded = colorbar.encode().unwrap();
        assert_eq!(
            SceneColorbar::from_input(&encoded),
            Ok(Some(colorbar.clone()))
        );
        let mut malformed = encoded;
        malformed[68..76].copy_from_slice(&(-1.0f64).to_le_bytes());
        assert!(SceneColorbar::from_input(&malformed).is_err());
        let mut unsupported_ticks = colorbar.encode().unwrap();
        unsupported_ticks[8] |= 4;
        assert!(SceneColorbar::from_input(&unsupported_ticks).is_err());
        let mut nonzero_tick_count = colorbar.encode().unwrap();
        nonzero_tick_count[16..20].copy_from_slice(&1u32.to_le_bytes());
        assert!(SceneColorbar::from_input(&nonzero_tick_count).is_err());
        let mut unsupported_continuous = colorbar.encode().unwrap();
        unsupported_continuous[8] &= !2;
        assert!(SceneColorbar::from_input(&unsupported_continuous).is_err());
    }

    #[test]
    fn scene_v13_colorbar_requires_the_selected_outer_gutter() {
        let colorbar = SceneColorbar {
            horizontal: false,
            domain: [0.0, 1.0],
            stops: vec![(0.0, [0, 0, 0, 255]), (1.0, [255, 255, 255, 128])],
            title: String::new(),
            text_rgba: [32, 32, 32, 96],
        };
        let insufficient = PlotLayout::new(120.0, 100.0, 10.0, 10.0, 10.0, 10.0).unwrap();
        assert_eq!(
            resolved_colorbar_bounds(insufficient, &colorbar),
            Err(SceneError::Limit)
        );

        let right_gutter = PlotLayout::new(140.0, 100.0, 10.0, 42.0, 10.0, 10.0).unwrap();
        assert_eq!(
            resolved_colorbar_bounds(right_gutter, &colorbar),
            Ok((126.0, 10.0, 14.0, 80.0))
        );

        let bottom = SceneColorbar {
            horizontal: true,
            ..colorbar
        };
        let bottom_gutter = PlotLayout::new(140.0, 100.0, 10.0, 10.0, 10.0, 42.0).unwrap();
        assert_eq!(
            resolved_colorbar_bounds(bottom_gutter, &bottom),
            Ok((10.0, 86.0, 120.0, 14.0))
        );
    }
}
