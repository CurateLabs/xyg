//! Versioned, bounded canonical scene records and deterministic SVG emission.
//!
//! This first vertical slice owns the built-in scatter-mark scene. Hosts still
//! coerce author input and resolve paint channels, but marker geometry,
//! stroke-inclusive sizing, validation, bounds, and SVG construction live here.

use crate::colormap;
use crate::compat_layout;
use crate::css;
use crate::geom;
use crate::kernels::{
    colormap_color, density_mean_color_rgba_into, density_rgba_into, normalize_one_f32,
};
use crate::polar::{self, POLAR_METRICS_LEN, XYPL_MAGIC, XYPL_V1_BYTES};
use crate::svg::push_num;
use std::collections::hash_map::Entry;
use std::collections::HashMap;
use std::fmt::Write;

pub const SCENE_VERSION: u32 = 31;
pub const MAX_SCENE_MARKS: usize = 2_000_000;
pub const MAX_AXIS_TICKS: usize = 200;
pub const MAX_SCENE_STYLES: usize = 65_536;
pub const MAX_SCENE_TEXT_BYTES: usize = 4_096;
/// Authored numeric axis formats are bounded authoring input. They compile to
/// ordinary canonical tick labels and never reach Scene consumers verbatim.
pub const MAX_SCENE_AXIS_FORMAT_BYTES: usize = 256;
/// Shared upper bound of the existing browser fixed-decimal compatibility
/// formatter and the bounded canonical tick-label resource contract.
const MAX_NUMERIC_TICK_FORMAT_PRECISION: usize = 100;
pub const SCENE_BATCH_HEADER_BYTES: usize = 160;
pub const SCENE_STYLE_RECORD_BYTES: usize = 16;
pub const SCENE_BATCH_RECORD_BYTES: usize = 56;
/// Fixed chrome trailer before UTF-8 labels and authored tick payloads (Scene v9).
pub const SCENE_CHROME_TRAILER_BYTES: usize = 248;
pub const SCENE_CHROME_STYLE_INPUT_BYTES: usize = 200;
pub const MAX_SCENE_CHROME_LENGTH: f64 = 1_000.0;
pub const BROWSER_PAINTER_VERSION: u32 = 14;
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
/// The bounded straight-arrow ingress shares the annotation resource ceiling.
pub const MAX_AUTHORED_STRAIGHT_ARROWS: usize = 128;
/// Worst-case XYAD envelope the ABI 112 packer may emit (v3 header plus five
/// section headers, maximum row tables, and the shared text budgets).
pub const MAX_SCENE_ANNOTATION_INPUT_BYTES: usize = 28
    + 12
    + MAX_AUTHORED_TEXT_ANNOTATIONS * 40
    + MAX_SCENE_TEXT_BYTES
    + 12
    + MAX_AUTHORED_TEXT_ANNOTATIONS * 32
    + MAX_SCENE_TEXT_BYTES
    + 12
    + MAX_AUTHORED_STRAIGHT_ARROWS * 60
    + 12
    + MAX_AUTHORED_TEXT_ANNOTATIONS * 76
    + MAX_SCENE_LABEL_TEXT_BYTES
    + 12
    + MAX_AUTHORED_TEXT_ANNOTATIONS * 68
    + MAX_SCENE_LABEL_TEXT_BYTES;
/// Literal color tables are deliberately small so every renderer can consume
/// exactly the same resolved Scene decoration without a host colormap registry.
pub const MAX_SCENE_COLORBAR_STOPS: usize = 16;
pub const MAX_SCENE_COLORBAR_TICKS: usize = 32;
pub const MAX_SCENE_COLORBAR_TEXT_BYTES: usize = 4_096;
/// `format_tick` has a short, bounded finite-f64 representation; keep the
/// painter frame ceiling explicit so every decoder can reject before allocating.
pub const MAX_SCENE_COLORBAR_TICK_LABEL_BYTES: usize = 32;
pub const MAX_SCENE_COLORBAR_MINOR_TICKS: usize = (MAX_SCENE_COLORBAR_TICKS - 1) * 4;
pub const MAX_SCENE_COLORBAR_PAINTER_BYTES: usize = MAX_SCENE_COLORBAR_INPUT_BYTES
    + 24 // XYRG v1
    + 16 // XYCT v1 header
    + (MAX_SCENE_COLORBAR_TICKS + MAX_SCENE_COLORBAR_MINOR_TICKS) * 16
    + MAX_SCENE_COLORBAR_TICKS * MAX_SCENE_COLORBAR_TICK_LABEL_BYTES;
const SCENE_LABEL_HEADER_BYTES: usize = 16;
const SCENE_LABEL_RECORD_BYTES: usize = 40;
const SCENE_LABEL_BOX_RECORD_BYTES: usize = 84;
const SCENE_LABEL_WRAPPED_RECORD_BYTES: usize = 104;
const CALLOUT_LABEL_BOX_INSET: f64 = 3.0;
const WRAPPED_LABEL_LINE_HEIGHT: f64 = 1.2;
const MAX_WRAPPED_LABEL_LINES: usize = 16;
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
        (SCENE_FEATURE_POLAR, "XYG_SCENE_UNSUPPORTED_POLAR: Scene v26 supports polar line, scatter, area, bar, column, errorbar, heatmap, and contour only"),
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
const SCENE_ANNOTATION_TAG_STRAIGHT_ARROW: u8 = 5;
const SCENE_ANNOTATION_TAG_CARTESIAN_CALLOUT: u8 = 6;
const STRAIGHT_ARROW_HEAD_LENGTH: f64 = 8.0;
const STRAIGHT_ARROW_HEAD_HALF_WIDTH: f64 = 4.0;

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
struct SceneLabelBox {
    x: f64,
    y: f64,
    width: f64,
    height: f64,
    rgba: [u8; 4],
    border: Option<SceneLabelBorder>,
}

/// A literal, bounded label-box stroke. Rust owns the rectangle it paints.
#[derive(Clone, Debug, PartialEq)]
struct SceneLabelBorder {
    rgba: [u8; 4],
    width: f64,
}

type AttachedLabelRow = (
    u64,
    [u8; 4],
    Option<[u8; 4]>,
    Option<SceneLabelBorder>,
    String,
);
type WrappedAnnotationRows = (
    Vec<SceneLabel>,
    Vec<Option<SceneLabelBox>>,
    Vec<CartesianCallout>,
);

#[derive(Clone, Debug, PartialEq)]
pub struct SceneLabel {
    pub stable_id: u64,
    pub x: f64,
    pub y: f64,
    pub font_size: f64,
    pub rgba: [u8; 4],
    /// SVG/CSS text-anchor code: start (0), middle (1), or end (2).
    /// This is owned output metadata, never a host pixel placement seam.
    pub anchor: u8,
    pub text: String,
}

fn encode_scene_labels(
    labels: &[SceneLabel],
    backgrounds: &[Option<SceneLabelBox>],
) -> Result<Vec<u8>, SceneError> {
    if labels.len() != backgrounds.len() {
        return Err(SceneError::Length);
    }
    if labels.is_empty() {
        return Ok(Vec::new());
    }
    let text_bytes = labels.iter().try_fold(0usize, |total, label| {
        total.checked_add(label.text.len()).ok_or(SceneError::Limit)
    })?;
    if labels.len() > MAX_SCENE_LABELS || text_bytes > MAX_SCENE_LABEL_TEXT_BYTES {
        return Err(SceneError::Limit);
    }
    let version = if labels.iter().any(|label| label.text.contains('\n')) {
        5
    } else if backgrounds
        .iter()
        .flatten()
        .any(|background| background.border.is_some())
    {
        4
    } else if backgrounds.iter().any(Option::is_some) {
        3
    } else if labels.iter().any(|label| label.anchor != 0) {
        2
    } else {
        1
    };
    let record_bytes = match version {
        1 => SCENE_LABEL_RECORD_BYTES,
        2 => 44,
        3 => SCENE_LABEL_BOX_RECORD_BYTES,
        4 => SCENE_LABEL_BOX_RECORD_BYTES + 16,
        5 => SCENE_LABEL_WRAPPED_RECORD_BYTES,
        _ => unreachable!(),
    };
    let mut out =
        Vec::with_capacity(SCENE_LABEL_HEADER_BYTES + labels.len() * record_bytes + text_bytes);
    out.extend_from_slice(b"XYLB");
    out.extend_from_slice(&(version as u32).to_le_bytes());
    out.extend_from_slice(&(labels.len() as u32).to_le_bytes());
    out.extend_from_slice(&(text_bytes as u32).to_le_bytes());
    for (label, background) in labels.iter().zip(backgrounds) {
        if label.text.is_empty()
            || label.text.contains('\0')
            || !label.x.is_finite()
            || !label.y.is_finite()
            || !label.font_size.is_finite()
            || !(1.0..=MAX_SCENE_CHROME_LENGTH).contains(&label.font_size)
            || label.anchor > 2
            || background.as_ref().is_some_and(|background| {
                ![
                    background.x,
                    background.y,
                    background.width,
                    background.height,
                ]
                .into_iter()
                .all(f64::is_finite)
                    || background.width <= 0.0
                    || background.height <= 0.0
                    || background.border.as_ref().is_some_and(|border| {
                        !border.width.is_finite() || border.width <= 0.0 || border.rgba[3] == 0
                    })
            })
        {
            return Err(SceneError::NonFinite);
        }
        out.extend_from_slice(&label.stable_id.to_le_bytes());
        out.extend_from_slice(&label.x.to_le_bytes());
        out.extend_from_slice(&label.y.to_le_bytes());
        out.extend_from_slice(&label.font_size.to_le_bytes());
        out.extend_from_slice(&label.rgba);
        if version >= 2 {
            out.push(label.anchor);
            out.extend_from_slice(&[0; 3]);
        }
        out.extend_from_slice(&(label.text.len() as u32).to_le_bytes());
        if version >= 3 {
            let background = background.as_ref();
            out.push(u8::from(background.is_some()));
            out.extend_from_slice(&[0; 3]);
            if let Some(background) = background {
                out.extend_from_slice(&background.x.to_le_bytes());
                out.extend_from_slice(&background.y.to_le_bytes());
                out.extend_from_slice(&background.width.to_le_bytes());
                out.extend_from_slice(&background.height.to_le_bytes());
                out.extend_from_slice(&background.rgba);
                if version >= 4 {
                    if let Some(border) = &background.border {
                        out.push(1);
                        out.extend_from_slice(&[0; 3]);
                        out.extend_from_slice(&border.rgba);
                        out.extend_from_slice(&border.width.to_le_bytes());
                    } else {
                        out.extend_from_slice(&[0; 16]);
                    }
                }
            } else {
                out.extend_from_slice(&[0; 36]);
                if version >= 4 {
                    out.extend_from_slice(&[0; 16]);
                }
            }
        }
        if version == 5 {
            let lines = label.text.split('\n').count();
            if lines == 0
                || lines > MAX_WRAPPED_LABEL_LINES
                || label.text.split('\n').any(str::is_empty)
            {
                return Err(SceneError::Limit);
            }
            out.extend_from_slice(&(lines as u32).to_le_bytes());
        }
    }
    for label in labels {
        out.extend_from_slice(label.text.as_bytes());
    }
    Ok(out)
}

fn decode_scene_labels(
    bytes: &[u8],
) -> Result<(Vec<SceneLabel>, Vec<Option<SceneLabelBox>>), SceneError> {
    if bytes.is_empty() {
        return Ok((Vec::new(), Vec::new()));
    }
    if bytes.len() < SCENE_LABEL_HEADER_BYTES || &bytes[..4] != b"XYLB" {
        return Err(SceneError::Length);
    }
    let version = batch_u32(bytes, 4)?;
    if !(1..=5).contains(&version) {
        return Err(SceneError::Length);
    }
    let record_bytes = match version {
        1 => SCENE_LABEL_RECORD_BYTES,
        2 => 44,
        3 => SCENE_LABEL_BOX_RECORD_BYTES,
        4 => SCENE_LABEL_BOX_RECORD_BYTES + 16,
        5 => SCENE_LABEL_WRAPPED_RECORD_BYTES,
        _ => unreachable!(),
    };
    let count = batch_u32(bytes, 8)? as usize;
    let text_bytes = batch_u32(bytes, 12)? as usize;
    if count > MAX_SCENE_LABELS || text_bytes > MAX_SCENE_LABEL_TEXT_BYTES {
        return Err(SceneError::Limit);
    }
    let table_end = SCENE_LABEL_HEADER_BYTES
        .checked_add(count.checked_mul(record_bytes).ok_or(SceneError::Limit)?)
        .ok_or(SceneError::Limit)?;
    if table_end.checked_add(text_bytes) != Some(bytes.len()) {
        return Err(SceneError::Length);
    }
    let mut text_at = table_end;
    let mut labels = Vec::with_capacity(count);
    let mut backgrounds = Vec::with_capacity(count);
    for index in 0..count {
        let at = SCENE_LABEL_HEADER_BYTES + index * record_bytes;
        let anchor = if version == 1 {
            0
        } else {
            if bytes[at + 37..at + 40] != [0; 3] || bytes[at + 36] > 2 {
                return Err(SceneError::Length);
            }
            bytes[at + 36]
        };
        let len = batch_u32(bytes, at + if version == 1 { 36 } else { 40 })? as usize;
        let background = if version >= 3 {
            let flags = bytes[at + 44];
            if flags & !1 != 0 || bytes[at + 45..at + 48] != [0; 3] {
                return Err(SceneError::Length);
            }
            let values = [
                batch_f64(bytes, at + 48)?,
                batch_f64(bytes, at + 56)?,
                batch_f64(bytes, at + 64)?,
                batch_f64(bytes, at + 72)?,
            ];
            let rgba: [u8; 4] = bytes[at + 80..at + 84].try_into().unwrap();
            let border = if version >= 4 {
                let border_flags = bytes[at + 84];
                let border_rgba: [u8; 4] = bytes[at + 88..at + 92].try_into().unwrap();
                let border_width = batch_f64(bytes, at + 92)?;
                if border_flags & !1 != 0 || bytes[at + 85..at + 88] != [0; 3] {
                    return Err(SceneError::Length);
                }
                if border_flags == 0 {
                    if border_rgba != [0; 4] || border_width != 0.0 {
                        return Err(SceneError::Length);
                    }
                    None
                } else if !border_width.is_finite() || border_width <= 0.0 || border_rgba[3] == 0 {
                    return Err(SceneError::Length);
                } else {
                    Some(SceneLabelBorder {
                        rgba: border_rgba,
                        width: border_width,
                    })
                }
            } else {
                None
            };
            if flags == 0 {
                if border.is_some() {
                    return Err(SceneError::Length);
                }
                if values != [0.0; 4] || rgba != [0; 4] {
                    return Err(SceneError::Length);
                }
                None
            } else if !values.into_iter().all(f64::is_finite)
                || values[2] <= 0.0
                || values[3] <= 0.0
            {
                return Err(SceneError::Length);
            } else {
                Some(SceneLabelBox {
                    x: values[0],
                    y: values[1],
                    width: values[2],
                    height: values[3],
                    rgba,
                    border,
                })
            }
        } else {
            None
        };
        let lines = if version == 5 {
            batch_u32(bytes, at + 100)? as usize
        } else {
            1
        };
        let end = text_at.checked_add(len).ok_or(SceneError::Limit)?;
        let text = std::str::from_utf8(bytes.get(text_at..end).ok_or(SceneError::Length)?)
            .map_err(|_| SceneError::Length)?
            .to_owned();
        if version == 5
            && (lines == 0
                || lines > MAX_WRAPPED_LABEL_LINES
                || text.split('\n').count() != lines
                || text.split('\n').any(str::is_empty))
        {
            return Err(SceneError::Length);
        }
        labels.push(SceneLabel {
            stable_id: batch_u64(bytes, at)?,
            x: batch_f64(bytes, at + 8)?,
            y: batch_f64(bytes, at + 16)?,
            font_size: batch_f64(bytes, at + 24)?,
            rgba: bytes[at + 32..at + 36].try_into().unwrap(),
            anchor,
            text,
        });
        backgrounds.push(background);
        text_at = end;
    }
    encode_scene_labels(&labels, &backgrounds)?;
    Ok((labels, backgrounds))
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
const SCENE_COLORBAR_TICK_BYTES: usize = 8;
pub const MAX_SCENE_COLORBAR_INPUT_BYTES: usize = SCENE_COLORBAR_HEADER_BYTES
    + MAX_SCENE_COLORBAR_STOPS * SCENE_COLORBAR_STOP_BYTES
    + MAX_SCENE_COLORBAR_TICKS * SCENE_COLORBAR_TICK_BYTES
    + MAX_SCENE_COLORBAR_TEXT_BYTES;

/// A bounded, host-neutral banded colour scale. The author supplies only
/// literal RGBA stops, a bounded title, and a right/bottom side. Rust derives
/// label text and screen geometry from the optional bounded major values.
#[derive(Clone, Debug, PartialEq)]
pub struct SceneColorbar {
    pub horizontal: bool,
    pub domain: [f64; 2],
    pub stops: Vec<(f64, [u8; 4])>,
    /// `None` means Rust selects deterministic linear major ticks.
    pub ticks: Option<Vec<f64>>,
    pub minor_ticks: bool,
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
            || u32::from_le_bytes(bytes[4..8].try_into().unwrap()) != 2
            || bytes[9..12] != [0; 3]
            || bytes[52..56] != [0; 4]
        {
            return Err(SceneError::Length);
        }
        let flags = bytes[8];
        if flags & !0x0f != 0 || flags & 2 == 0 {
            return Err(SceneError::Length);
        }
        let stop_count = u32::from_le_bytes(bytes[12..16].try_into().unwrap()) as usize;
        let tick_count = u32::from_le_bytes(bytes[16..20].try_into().unwrap()) as usize;
        let title_len = u32::from_le_bytes(bytes[20..24].try_into().unwrap()) as usize;
        if (flags & 8 != 0) != (tick_count != 0)
            || !(2..=MAX_SCENE_COLORBAR_STOPS).contains(&stop_count)
            || tick_count > MAX_SCENE_COLORBAR_TICKS
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
        let mut ticks = Vec::with_capacity(tick_count);
        let mut previous = f64::NEG_INFINITY;
        for index in 0..tick_count {
            let at = table_end + index * 8;
            let value = f64_at(at);
            if !value.is_finite() || value < domain[0] || value > domain[1] || value <= previous {
                return Err(SceneError::Length);
            }
            previous = value;
            ticks.push(value);
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
            ticks: (flags & 8 != 0).then_some(ticks),
            minor_ticks: flags & 4 != 0,
            title,
            text_rgba: bytes[40..44].try_into().unwrap(),
        }))
    }

    fn encode(&self) -> Result<Vec<u8>, SceneError> {
        let mut out = Vec::with_capacity(
            SCENE_COLORBAR_HEADER_BYTES
                + self.stops.len() * SCENE_COLORBAR_STOP_BYTES
                + self.ticks.as_ref().map_or(0, Vec::len) * 8
                + self.title.len(),
        );
        out.extend_from_slice(b"XYCB");
        out.extend_from_slice(&2u32.to_le_bytes());
        let ticks = self.ticks.as_deref().unwrap_or_default();
        out.push(
            u8::from(self.horizontal)
                | 2
                | (u8::from(self.minor_ticks) << 2)
                | (u8::from(!ticks.is_empty()) << 3),
        );
        out.extend_from_slice(&[0; 3]);
        out.extend_from_slice(&(self.stops.len() as u32).to_le_bytes());
        out.extend_from_slice(&(ticks.len() as u32).to_le_bytes());
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
        for value in ticks {
            out.extend_from_slice(&value.to_le_bytes());
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
    push_raster_stroke_dash(out, points, width, rgba, scale, &[], LINECAP_ROUND)
}

fn push_raster_dash(out: &mut Vec<u8>, dash: &[f32], scale: f64) -> Result<(), SceneError> {
    out.extend_from_slice(&(dash.len() as u32).to_le_bytes());
    for value in dash {
        push_raster_f32(out, f64::from(*value), scale)?;
    }
    Ok(())
}

fn push_raster_stroke_dash(
    out: &mut Vec<u8>,
    points: [(f64, f64); 2],
    width: f64,
    rgba: [u8; 4],
    scale: f64,
    dash: &[f32],
    linecap: u8,
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
    push_raster_dash(out, dash, scale)?;
    out.push(linecap);
    Ok(())
}

fn push_raster_polyline(
    out: &mut Vec<u8>,
    points: &[(f64, f64)],
    width: f64,
    rgba: [u8; 4],
    scale: f64,
    closed: bool,
) -> Result<(), SceneError> {
    if points.len() < 2 {
        return Ok(());
    }
    let count = points.len() + usize::from(closed);
    out.push(3);
    out.extend_from_slice(&(count as u32).to_le_bytes());
    for &(x, y) in points {
        push_raster_f32(out, x, scale)?;
        push_raster_f32(out, y, scale)?;
    }
    if closed {
        push_raster_f32(out, points[0].0, scale)?;
        push_raster_f32(out, points[0].1, scale)?;
    }
    push_raster_f32(out, width, scale)?;
    out.extend_from_slice(&rgba);
    out.push(u8::from(closed));
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
            ScaleKind::SymLog => symlog_ticks(lo, hi, self.constant, target),
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

/// Symmetric-log ticks generated in scale-coordinate space, then returned in
/// canonical f64 data units. `constant` is the positive width of the linear
/// region around zero.
pub fn symlog_ticks(
    lo: f64,
    hi: f64,
    constant: f64,
    target: usize,
) -> Result<AxisTicks, SceneError> {
    if !lo.is_finite()
        || !hi.is_finite()
        || !constant.is_finite()
        || constant <= 0.0
        || target == 0
        || target > MAX_AXIS_TICKS
    {
        return Err(SceneError::NonFinite);
    }
    let coordinate = |value: f64| value.signum() * (value.abs() / constant).ln_1p();
    let value = |coordinate: f64| coordinate.signum() * constant * coordinate.abs().exp_m1();
    let coordinates = linear_ticks(coordinate(lo), coordinate(hi), target)?;
    let mut ticks: Vec<f64> = coordinates.ticks.iter().map(|tick| value(*tick)).collect();
    if ticks.iter().any(|tick| !tick.is_finite()) {
        return Err(SceneError::NonFinite);
    }
    if lo.min(hi) <= 0.0 && lo.max(hi) >= 0.0 && !ticks.iter().any(|tick| tick.abs() < 1e-12) {
        if ticks.len() >= MAX_AXIS_TICKS {
            return Err(SceneError::Limit);
        }
        ticks.push(0.0);
        ticks.sort_by(|a, b| {
            if lo > hi {
                b.total_cmp(a)
            } else {
                a.total_cmp(b)
            }
        });
    }
    let step = value(coordinates.step).abs();
    if !step.is_finite() {
        return Err(SceneError::NonFinite);
    }
    Ok(AxisTicks {
        labeled: ticks.clone(),
        ticks,
        step,
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
/// first-of-month calendar ticks. Compatibility hosts consume this function
/// through the shared native/WASM tick boundaries.
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
) -> Result<(Vec<SceneLabel>, Vec<Option<SceneLabelBox>>), SceneError> {
    if bytes.is_empty() {
        return Ok((Vec::new(), Vec::new()));
    }
    if bytes.len() < 12 || &bytes[..4] != b"XYAT" {
        return Err(SceneError::Length);
    }
    let version = batch_u32(bytes, 4)?;
    if !(1..=4).contains(&version) {
        return Err(SceneError::Length);
    }
    let count = batch_u32(bytes, 8)? as usize;
    if count > MAX_AUTHORED_TEXT_ANNOTATIONS {
        return Err(SceneError::Limit);
    }
    let mut at = 12usize;
    let mut total = 0usize;
    let mut labels = Vec::with_capacity(count);
    let mut backgrounds = Vec::with_capacity(count);
    for index in 0..count {
        let fixed_bytes = match version {
            1 => 24,
            2 => 28,
            3 => 40,
            _ => unreachable!(),
        };
        let end_fixed = at.checked_add(fixed_bytes).ok_or(SceneError::Limit)?;
        let fixed = bytes.get(at..end_fixed).ok_or(SceneError::Length)?;
        let x = f64::from_le_bytes(fixed[0..8].try_into().unwrap());
        let y = f64::from_le_bytes(fixed[8..16].try_into().unwrap());
        let background = if version >= 2 {
            let rgba: [u8; 4] = fixed[20..24].try_into().unwrap();
            (rgba[3] != 0).then_some(rgba)
        } else {
            None
        };
        let border = if version == 3 {
            let rgba: [u8; 4] = fixed[24..28].try_into().unwrap();
            let width = f64::from_le_bytes(fixed[28..36].try_into().unwrap());
            if rgba[3] == 0 {
                if width != 0.0 {
                    return Err(SceneError::Length);
                }
                None
            } else if !width.is_finite() || width <= 0.0 {
                return Err(SceneError::Length);
            } else {
                Some(SceneLabelBorder { rgba, width })
            }
        } else {
            None
        };
        let len_at = match version {
            1 => 20,
            2 => 24,
            3 => 36,
            _ => unreachable!(),
        };
        let len = u32::from_le_bytes(fixed[len_at..len_at + 4].try_into().unwrap()) as usize;
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
        let label = SceneLabel {
            stable_id: 0x5859_0400_0000_0000 | index as u64,
            x: px,
            y: py,
            font_size: 12.0,
            rgba: fixed[16..20].try_into().unwrap(),
            anchor: 0,
            text: text.to_owned(),
        };
        backgrounds.push(match (background, border) {
            (Some(fill), border) => resolved_callout_label_background(
                label.x,
                label.y,
                label.font_size,
                label.anchor,
                &label.text,
                fill,
                border,
                layout,
            )?,
            (None, Some(_)) => return Err(SceneError::Length),
            (None, None) => None,
        });
        labels.push(label);
        at = end;
    }
    if at != bytes.len() {
        return Err(SceneError::Length);
    }
    Ok((labels, backgrounds))
}

/// Decode the bounded, host-authored literal paint for labels attached to
/// canonical Scene annotation records. Rust retains placement and typography
/// policy; hosts only supply an already-resolved RGBA literal and text.
fn decode_xyal_rows(bytes: &[u8]) -> Result<Vec<AttachedLabelRow>, SceneError> {
    if bytes.is_empty() {
        return Ok(Vec::new());
    }
    if bytes.len() < 12 || &bytes[..4] != b"XYAL" {
        return Err(SceneError::Length);
    }
    let version = batch_u32(bytes, 4)?;
    if !(1..=4).contains(&version) {
        return Err(SceneError::Length);
    }
    let count = batch_u32(bytes, 8)? as usize;
    if count > MAX_AUTHORED_TEXT_ANNOTATIONS {
        return Err(SceneError::Limit);
    }
    let mut at = 12usize;
    let mut total = 0usize;
    let mut seen = std::collections::BTreeSet::new();
    let mut rows = Vec::with_capacity(count);
    for _ in 0..count {
        let fixed_bytes = match version {
            1 => 12,
            2 => 16,
            3 => 20,
            4 => 32,
            _ => unreachable!(),
        };
        let fixed_end = at.checked_add(fixed_bytes).ok_or(SceneError::Limit)?;
        let fixed = bytes.get(at..fixed_end).ok_or(SceneError::Length)?;
        let stable_id = u64::from_le_bytes(fixed[..8].try_into().unwrap());
        let rgba = if version == 1 {
            [102, 112, 133, 255]
        } else {
            fixed[8..12].try_into().unwrap()
        };
        let background = if version >= 3 {
            let rgba: [u8; 4] = fixed[12..16].try_into().unwrap();
            (rgba[3] != 0).then_some(rgba)
        } else {
            None
        };
        let border = if version == 4 {
            let rgba: [u8; 4] = fixed[16..20].try_into().unwrap();
            let width = f64::from_le_bytes(fixed[20..28].try_into().unwrap());
            if rgba[3] == 0 {
                if width != 0.0 {
                    return Err(SceneError::Length);
                }
                None
            } else if !width.is_finite() || width <= 0.0 {
                return Err(SceneError::Length);
            } else {
                Some(SceneLabelBorder { rgba, width })
            }
        } else {
            None
        };
        let len_at = if version == 1 {
            8
        } else if version == 2 {
            12
        } else if version == 3 {
            16
        } else {
            28
        };
        let len = u32::from_le_bytes(fixed[len_at..len_at + 4].try_into().unwrap()) as usize;
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
        if background.is_none() && border.is_some() {
            return Err(SceneError::Length);
        }
        rows.push((stable_id, rgba, background, border, text.to_owned()));
        at = end;
    }
    if at != bytes.len() {
        return Err(SceneError::Length);
    }
    Ok(rows)
}

/// Decode labels attached to existing canonical Scene v12 annotation records.
/// `XYAL` contains identities, literal paint, and text only: Rust derives every
/// anchor from validated Scene geometry, so hosts cannot choose pixels or placement policy.
fn decode_xyal(
    bytes: &[u8],
    document: &SceneDocument,
) -> Result<(Vec<SceneLabel>, Vec<Option<SceneLabelBox>>), SceneError> {
    let rows = decode_xyal_rows(bytes)?;
    let mut labels = Vec::with_capacity(rows.len());
    let mut backgrounds = Vec::with_capacity(rows.len());
    for (index, (stable_id, rgba, background, border, text)) in rows.into_iter().enumerate() {
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
        let label = SceneLabel {
            stable_id: 0x5859_0500_0000_0000 | index as u64,
            x,
            y,
            font_size: 12.0,
            rgba,
            anchor: 0,
            text,
        };
        backgrounds.push(match background {
            Some(fill) => resolved_callout_label_background(
                label.x,
                label.y,
                label.font_size,
                label.anchor,
                &label.text,
                fill,
                border,
                document.layout,
            )?,
            None => None,
        });
        labels.push(label);
    }
    Ok((labels, backgrounds))
}

/// Decode the bounded annotation-decoration envelope.  The envelope keeps
/// standalone `XYAT` and attached `XYAL` records independently versioned.
struct AnnotationEnvelope {
    labels: Vec<SceneLabel>,
    label_backgrounds: Vec<Option<SceneLabelBox>>,
    arrows: Vec<StraightArrow>,
    callouts: Vec<CartesianCallout>,
}

/// Decode the v24 bounded wrapped-label seam.  Hosts contribute only literal
/// text, a width constraint, and author offsets; line breaking, metrics,
/// projection, boxes, and callout geometry remain Rust-owned.
fn decode_xyaw(
    bytes: &[u8],
    x_scale: AxisScale,
    y_scale: AxisScale,
    layout: PlotLayout,
) -> Result<WrappedAnnotationRows, SceneError> {
    if bytes.is_empty() {
        return Ok((Vec::new(), Vec::new(), Vec::new()));
    }
    if bytes.len() < 12 || &bytes[..4] != b"XYAW" || batch_u32(bytes, 4)? != 1 {
        return Err(SceneError::Length);
    }
    let count = batch_u32(bytes, 8)? as usize;
    if count > MAX_AUTHORED_TEXT_ANNOTATIONS {
        return Err(SceneError::Limit);
    }
    let mut at = 12usize;
    let mut total = 0usize;
    let mut labels = Vec::new();
    let mut backgrounds = Vec::new();
    let mut callouts = Vec::new();
    for index in 0..count {
        let fixed = bytes
            .get(at..at.checked_add(68).ok_or(SceneError::Limit)?)
            .ok_or(SceneError::Length)?;
        let x = batch_f64(fixed, 0)?;
        let y = batch_f64(fixed, 8)?;
        let dx = batch_f64(fixed, 16)?;
        let dy = batch_f64(fixed, 24)?;
        let wrap = batch_f64(fixed, 32)?;
        let rgba: [u8; 4] = fixed[40..44].try_into().unwrap();
        let fill: [u8; 4] = fixed[44..48].try_into().unwrap();
        let border_rgba: [u8; 4] = fixed[48..52].try_into().unwrap();
        let border_width = batch_f64(fixed, 52)?;
        let kind = fixed[60];
        let anchor = fixed[61];
        if fixed[62..64] != [0; 2]
            || kind > 1
            || anchor > 2
            || ![x, y, dx, dy, wrap, border_width]
                .into_iter()
                .all(f64::is_finite)
            || wrap < 0.0
        {
            return Err(SceneError::Length);
        }
        let len = batch_u32(fixed, 64)? as usize;
        let end = at
            .checked_add(68)
            .and_then(|v| v.checked_add(len))
            .ok_or(SceneError::Limit)?;
        let authored = std::str::from_utf8(bytes.get(at + 68..end).ok_or(SceneError::Length)?)
            .map_err(|_| SceneError::Length)?;
        total = total.checked_add(len).ok_or(SceneError::Limit)?;
        if authored.is_empty()
            || authored.contains('\0')
            || authored.contains('\r')
            || total > MAX_SCENE_LABEL_TEXT_BYTES
        {
            return Err(SceneError::Limit);
        }
        let mut lines = Vec::new();
        for explicit in authored.split('\n') {
            if explicit.is_empty() {
                return Err(SceneError::Length);
            }
            if wrap == 0.0 {
                lines.push(explicit.to_owned());
                continue;
            }
            let mut line = String::new();
            for word in explicit.split_ascii_whitespace() {
                let candidate = if line.is_empty() {
                    word.to_owned()
                } else {
                    format!("{line} {word}")
                };
                if text_advance(&candidate, 12.0) <= wrap {
                    line = candidate;
                } else if line.is_empty() {
                    return Err(SceneError::Limit);
                } else {
                    lines.push(std::mem::take(&mut line));
                    line.push_str(word);
                }
            }
            if line.is_empty() {
                return Err(SceneError::Length);
            }
            lines.push(line);
        }
        if lines.len() > MAX_WRAPPED_LABEL_LINES {
            return Err(SceneError::Limit);
        }
        let text = lines.join("\n");
        let px = x_scale.pixel(x);
        let py = y_scale.pixel(y);
        let lx = px + dx;
        let ly = py + dy;
        if ![px, py, lx, ly].into_iter().all(f64::is_finite)
            || px < layout.left
            || px > layout.right
            || py < layout.top
            || py > layout.bottom
            || lx < layout.left
            || lx > layout.right
            || ly < layout.top
            || ly > layout.bottom
        {
            return Err(SceneError::Length);
        }
        let border = if border_rgba[3] == 0 {
            if border_width != 0.0 {
                return Err(SceneError::Length);
            }
            None
        } else if border_width <= 0.0 {
            return Err(SceneError::Length);
        } else {
            Some(SceneLabelBorder {
                rgba: border_rgba,
                width: border_width,
            })
        };
        if fill[3] == 0 && border.is_some() {
            return Err(SceneError::Length);
        }
        let stable_id = 0x5859_0700_0000_0000 | index as u64;
        let label = SceneLabel {
            stable_id,
            x: lx,
            y: ly,
            font_size: 12.0,
            rgba,
            anchor,
            text,
        };
        let background = resolved_callout_label_background(
            lx,
            ly,
            12.0,
            anchor,
            &label.text,
            fill,
            border,
            layout,
        )?;
        if kind == 0 {
            labels.push(label);
            backgrounds.push(background);
        } else {
            let (base, head) = straight_arrow_points(lx, ly, px, py)?;
            let _ = (base, head);
            callouts.push(CartesianCallout {
                stable_id,
                start: [px, py],
                tip: [lx, ly],
                rgba,
                width: 1.5,
                label,
                label_background: background,
            });
        }
        at = end;
    }
    if at != bytes.len() {
        return Err(SceneError::Length);
    }
    Ok((labels, backgrounds, callouts))
}

fn decode_annotation_envelope(
    bytes: &[u8],
    document: &SceneDocument,
) -> Result<AnnotationEnvelope, SceneError> {
    if bytes.is_empty() {
        return Ok(AnnotationEnvelope {
            labels: Vec::new(),
            label_backgrounds: Vec::new(),
            arrows: Vec::new(),
            callouts: Vec::new(),
        });
    }
    if bytes.len() < 20 || &bytes[..4] != b"XYAD" {
        return Err(SceneError::Length);
    }
    let version = batch_u32(bytes, 4)?;
    if !(1..=3).contains(&version) {
        return Err(SceneError::Length);
    }
    let xyat_len = batch_u32(bytes, 8)? as usize;
    let xyal_len = batch_u32(bytes, 12)? as usize;
    let xyar_len = batch_u32(bytes, 16)? as usize;
    let xyac_len = if version == 1 {
        0
    } else {
        if bytes.len() < 24 {
            return Err(SceneError::Length);
        }
        batch_u32(bytes, 20)? as usize
    };
    let xyaw_len = if version == 3 {
        if bytes.len() < 28 {
            return Err(SceneError::Length);
        }
        batch_u32(bytes, 24)? as usize
    } else {
        0
    };
    let payload_start: usize = if version == 1 {
        20
    } else if version == 2 {
        24
    } else {
        28
    };
    let xyat_end = payload_start
        .checked_add(xyat_len)
        .ok_or(SceneError::Limit)?;
    let xyal_end = xyat_end.checked_add(xyal_len).ok_or(SceneError::Limit)?;
    let xyar_end = xyal_end.checked_add(xyar_len).ok_or(SceneError::Limit)?;
    let xyac_end = xyar_end.checked_add(xyac_len).ok_or(SceneError::Limit)?;
    let end = xyac_end.checked_add(xyaw_len).ok_or(SceneError::Limit)?;
    if end != bytes.len() {
        return Err(SceneError::Length);
    }
    let (mut labels, mut label_backgrounds) = decode_xyat(
        &bytes[payload_start..xyat_end],
        document.x_scale,
        document.y_scale,
        document.layout,
    )?;
    let (mut attached, mut attached_backgrounds) =
        decode_xyal(&bytes[xyat_end..xyal_end], document)?;
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
    label_backgrounds.append(&mut attached_backgrounds);
    let mut callouts = decode_xyac(
        &bytes[xyar_end..xyac_end],
        document.x_scale,
        document.y_scale,
        document.layout,
    )?;
    let (mut wrapped, mut wrapped_backgrounds, mut wrapped_callouts) = decode_xyaw(
        &bytes[xyac_end..end],
        document.x_scale,
        document.y_scale,
        document.layout,
    )?;
    labels.append(&mut wrapped);
    label_backgrounds.append(&mut wrapped_backgrounds);
    callouts.append(&mut wrapped_callouts);
    if labels
        .iter()
        .chain(callouts.iter().map(|callout| &callout.label))
        .try_fold(0usize, |total, label| {
            total.checked_add(label.text.len()).ok_or(SceneError::Limit)
        })?
        > MAX_SCENE_LABEL_TEXT_BYTES
    {
        return Err(SceneError::Limit);
    }
    Ok(AnnotationEnvelope {
        labels,
        label_backgrounds,
        arrows: decode_xyar(&bytes[xyal_end..xyar_end])?,
        callouts,
    })
}

type SceneChromeTrailer = (
    SceneChromeStyle,
    SceneChromeText,
    Option<SceneLegend>,
    Option<SceneColorbar>,
    Vec<SceneLabel>,
    Vec<Option<SceneLabelBox>>,
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
    let (labels, label_backgrounds) = decode_scene_labels(&bytes[label_start..total])?;
    Ok((
        chrome,
        text,
        legend,
        colorbar,
        labels,
        label_backgrounds,
        total,
    ))
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

fn polar_legend_loc_has_left(location: LegendLocation) -> bool {
    matches!(
        location,
        LegendLocation::UpperLeft | LegendLocation::LowerLeft | LegendLocation::CenterLeft
    )
}

fn polar_legend_box_after_recut(
    layout: PlotLayout,
    legend: Option<&SceneLegend>,
) -> Option<[f64; 4]> {
    let legend = legend?;
    let compact = compat_layout::is_compact(layout.viewport_width)?;
    let (side, room) = compat_layout::polar_legend_reserve(
        compact,
        polar_legend_loc_has_left(legend.location),
        layout.viewport_width,
    )?;
    if side == compat_layout::LEGEND_SIDE_NONE || room <= 0.0 {
        return None;
    }
    match side {
        compat_layout::LEGEND_SIDE_LEFT => Some([
            0.0,
            layout.top,
            room,
            layout.bottom - layout.top,
        ]),
        compat_layout::LEGEND_SIDE_RIGHT => Some([
            layout.viewport_width - room,
            layout.top,
            room,
            layout.bottom - layout.top,
        ]),
        compat_layout::LEGEND_SIDE_BOTTOM => Some([
            layout.left,
            layout.viewport_height - room,
            layout.right - layout.left,
            room,
        ]),
        _ => None,
    }
}

fn recut_polar_scene_layout(
    layout: PlotLayout,
    legend: Option<&SceneLegend>,
    text: &SceneChromeText,
    colorbar: Option<&SceneColorbar>,
    chrome: &SceneChromeStyle,
) -> Result<(PlotLayout, Option<[f64; 4]>), SceneError> {
    let compact = compat_layout::is_compact(layout.viewport_width).ok_or(SceneError::NonFinite)?;
    let (legend_side, legend_room) = if let Some(legend) = legend {
        compat_layout::polar_legend_reserve(
            compact,
            polar_legend_loc_has_left(legend.location),
            layout.viewport_width,
        )
        .ok_or(SceneError::NonFinite)?
    } else {
        (compat_layout::LEGEND_SIDE_NONE, 0.0)
    };
    let labels_hidden =
        chrome.x_axis.tick_label_sides == 0 || chrome.x_axis.label_rgba[3] == 0;
    let polar_label_room = if labels_hidden {
        0.0
    } else {
        let widest = chrome.x_tick_labels.as_ref().map(|labels| {
            labels
                .iter()
                .map(|label| text_advance(label, chrome.label_font_size))
                .fold(0.0_f64, f64::max)
        });
        compat_layout::polar_label_room(widest).ok_or(SceneError::NonFinite)?
    };
    let recut = compat_layout::recut_polar_plot(
        compat_layout::PolarPlot {
            x: layout.left,
            y: layout.top,
            w: layout.right - layout.left,
            h: layout.bottom - layout.top,
            top_axis_room: layout.top,
            legend_box: None,
        },
        layout.viewport_width,
        layout.viewport_height,
        legend_side,
        legend_room,
        polar_label_room,
        false,
        !text.y_label.is_empty(),
        !text.x_label.is_empty() || colorbar.is_some_and(|bar| bar.horizontal),
    )
    .ok_or(SceneError::NonFinite)?;
    let recut_layout = PlotLayout::new(
        layout.viewport_width,
        layout.viewport_height,
        recut.x,
        layout.viewport_width - (recut.x + recut.w),
        recut.y,
        layout.viewport_height - (recut.y + recut.h),
    )?;
    Ok((recut_layout, recut.legend_box))
}

fn resolved_legend_bounds(
    layout: PlotLayout,
    legend: &SceneLegend,
    polar_legend_box: Option<[f64; 4]>,
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
    let (plot_left, plot_top, plot_right, plot_bottom) = match polar_legend_box {
        Some([bx, by, bw, bh]) => (bx, by, bx + bw, by + bh),
        None => (layout.left, layout.top, layout.right, layout.bottom),
    };
    if !width.is_finite()
        || !height.is_finite()
        || width > plot_right - plot_left - 16.0
        || height > plot_bottom - plot_top - 16.0
    {
        return Err(SceneError::Limit);
    }
    let (mut x, mut y) = (plot_left + 8.0, plot_top + 8.0);
    match legend.location {
        LegendLocation::UpperRight => x = plot_right - width - 8.0,
        LegendLocation::UpperLeft => {}
        LegendLocation::LowerLeft => y = plot_bottom - height - 8.0,
        LegendLocation::LowerRight => {
            x = plot_right - width - 8.0;
            y = plot_bottom - height - 8.0;
        }
        LegendLocation::CenterRight => {
            x = plot_right - width - 8.0;
            y = (plot_top + plot_bottom - height) * 0.5;
        }
        LegendLocation::CenterLeft => y = (plot_top + plot_bottom - height) * 0.5,
        LegendLocation::UpperCenter => x = (plot_left + plot_right - width) * 0.5,
        LegendLocation::LowerCenter => {
            x = (plot_left + plot_right - width) * 0.5;
            y = plot_bottom - height - 8.0;
        }
        LegendLocation::Center => {
            x = (plot_left + plot_right - width) * 0.5;
            y = (plot_top + plot_bottom - height) * 0.5;
        }
    }
    Ok((x, y, width, height))
}

fn legend_swatch_rgba(rgba: [u8; 4]) -> [u8; 4] {
    if rgba[3] == 0 {
        rgba
    } else {
        [rgba[0], rgba[1], rgba[2], 255]
    }
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

/// Fully resolved colorbar tick geometry. This is deliberately computed before
/// every renderer so DOM/WASM consumers never select ticks, format labels, or
/// subdivide minor intervals themselves.
#[derive(Clone, Debug, PartialEq)]
struct ResolvedColorbarTicks {
    majors: Vec<(f64, f64, String)>,
    minors: Vec<(f64, f64)>,
}

fn resolved_colorbar_ticks(
    colorbar: &SceneColorbar,
    bounds: (f64, f64, f64, f64),
) -> Result<ResolvedColorbarTicks, SceneError> {
    let (x, y, width, height) = bounds;
    let length = if colorbar.horizontal { width } else { height };
    let values = match &colorbar.ticks {
        Some(values) => values.clone(),
        None => {
            linear_ticks(
                colorbar.domain[0],
                colorbar.domain[1],
                ((length / 48.0).floor() as usize + 1).clamp(2, 8),
            )?
            .labeled
        }
    };
    if values.len() > MAX_SCENE_COLORBAR_TICKS {
        return Err(SceneError::Limit);
    }
    let step = values
        .windows(2)
        .next()
        .map(|pair| (pair[1] - pair[0]).abs())
        .filter(|step| step.is_finite() && *step > 0.0)
        .unwrap_or((colorbar.domain[1] - colorbar.domain[0]).abs());
    let pixel = |value: f64| {
        let fraction = (value - colorbar.domain[0]) / (colorbar.domain[1] - colorbar.domain[0]);
        if colorbar.horizontal {
            x + width * fraction
        } else {
            y + height * (1.0 - fraction)
        }
    };
    let majors = values
        .iter()
        .map(|value| {
            let label = format_tick(*value, step, ScaleKind::Linear);
            (label.len() <= MAX_SCENE_COLORBAR_TICK_LABEL_BYTES)
                .then_some((*value, pixel(*value), label))
                .ok_or(SceneError::Limit)
        })
        .collect::<Result<Vec<_>, _>>()?;
    let mut minors = Vec::new();
    if colorbar.minor_ticks {
        for pair in values.windows(2) {
            for subdivision in 1..5 {
                let value = pair[0] + (pair[1] - pair[0]) * subdivision as f64 / 5.0;
                minors.push((value, pixel(value)));
            }
        }
    }
    Ok(ResolvedColorbarTicks { majors, minors })
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
    let (_chrome, _text, legend, _colorbar, _labels, _label_backgrounds, total) =
        read_chrome_trailer(bytes, body)?;
    if let Some(legend) = legend {
        if legend.entries.iter().any(|entry| entry.style_ref >= styles) {
            return Err(SceneError::Length);
        }
    }
    let (xypl, xyim, xyds) = scene_sidecars_after_chrome(bytes, total)?;

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
    if !xypl.is_empty() {
        let layout = PlotLayout::new(
            viewport_width,
            viewport_height,
            left,
            viewport_width - right,
            top,
            viewport_height - bottom,
        )?;
        PolarSceneState::from_xypl(xypl, layout)?;
    }
    let images = parse_xyim(xyim)?;
    let (dash_bytes, cap_bytes, marker_bytes, grad_bytes, glyph_bytes) = split_style_sidecars(xyds)?;
    let dashes = parse_xyds(dash_bytes)?;
    let caps = parse_xylc(cap_bytes)?;
    let markers = parse_xymp(marker_bytes)?;
    let gradients = parse_xygr(grad_bytes)?;
    let glyphs = parse_xymg(glyph_bytes)?;
    if dashes
        .iter()
        .any(|entry| entry.style_ref as usize >= styles)
        || caps.iter().any(|entry| entry.style_ref as usize >= styles)
        || markers
            .iter()
            .any(|entry| entry.style_ref as usize >= styles)
        || gradients
            .iter()
            .any(|entry| entry.style_ref as usize >= styles)
        || glyphs.iter().any(|entry| entry.style_ref as usize >= styles)
    {
        return Err(SceneError::Length);
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
        if visible > 1 || !matches!(bytes[offset + 3], 0..=6 | 0x80) {
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
                if symbol > ScatterSymbol::VerticalLine as u8
                    || coords[2] != 0.0
                    || coords[3] != 0.0
                {
                    return Err(SceneError::Length);
                }
            }
            SceneRecordKind::Polyline => {
                if symbol != 0 || diameter != 0.0 || coords[2] != 0.0 || coords[3] != 0.0 {
                    return Err(SceneError::Length);
                }
            }
            SceneRecordKind::Rect | SceneRecordKind::Image => {
                if symbol != 0
                    || diameter != 0.0
                    || (visible != 0 && (coords[0] > coords[2] || coords[1] > coords[3]))
                {
                    return Err(SceneError::Length);
                }
                if kind == SceneRecordKind::Image {
                    let stable_id = batch_u64(bytes, offset + 8)?;
                    if !images.iter().any(|image| image.stable_id == stable_id) {
                        return Err(SceneError::Length);
                    }
                }
            }
            SceneRecordKind::Band => {
                let outline = BandOutline::from_code(symbol)?;
                let style_offset = styles_offset + style * SCENE_STYLE_RECORD_BYTES;
                let stroke_width = batch_f64(bytes, style_offset + 8)?;
                let stroke_alpha = bytes[style_offset + 7];
                if diameter != 0.0
                    || (outline != BandOutline::None && (stroke_width == 0.0 || stroke_alpha == 0))
                {
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
    if !xypl.is_empty() && !images.is_empty() {
        return Err(SceneError::Length);
    }
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
            5 | 6 if run_end - annotation_cursor == 5 => {
                let mut arrow = [EncodedRecord {
                    kind: SceneRecordKind::Scatter,
                    visible: false,
                    symbol: 0,
                    style_ref: 0,
                    stable_id: 0,
                    coordinates: [0.0; 4],
                    diameter: 0.0,
                    annotation_tag: 0,
                }; 5];
                for (row, record) in arrow.iter_mut().enumerate() {
                    let at = records_offset + (annotation_cursor + row) * SCENE_BATCH_RECORD_BYTES;
                    record.kind = SceneRecordKind::from_code(bytes[at])?;
                    record.visible = bytes[at + 1] != 0;
                    record.symbol = bytes[at + 2];
                    record.annotation_tag = bytes[at + 3];
                    record.style_ref = batch_u32(bytes, at + 4)? as usize;
                    record.stable_id = batch_u64(bytes, at + 8)?;
                    record.coordinates = [
                        batch_f64(bytes, at + 16)?,
                        batch_f64(bytes, at + 24)?,
                        batch_f64(bytes, at + 32)?,
                        batch_f64(bytes, at + 40)?,
                    ];
                    record.diameter = batch_f64(bytes, at + 48)?;
                }
                if !valid_straight_arrow_run(&arrow) {
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
    /// One axis-aligned image blit. Coordinates are the screen rectangle;
    /// pixels live in the trailing XYIM sidecar keyed by stable id (Scene v27).
    Image = 5,
}

/// Rust-owned outline topology for a Scene Band run (Scene v25).
///
/// The code reuses the Band record's formerly-reserved `symbol` byte.  Hosts
/// select from the bounded authored modes; Rust canonicalizes an invisible
/// stroke to `None` and owns every consumer's resulting path topology.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
#[repr(u8)]
pub enum BandOutline {
    None = 0,
    Top = 1,
    Perimeter = 2,
}

impl BandOutline {
    fn from_code(value: u8) -> Result<Self, SceneError> {
        match value {
            0 => Ok(Self::None),
            1 => Ok(Self::Top),
            2 => Ok(Self::Perimeter),
            _ => Err(SceneError::Length),
        }
    }

    fn canonical(value: u8, stroke_width: f64, stroke_alpha: u8) -> Result<Self, SceneError> {
        let requested = Self::from_code(value)?;
        Ok(if stroke_width == 0.0 || stroke_alpha == 0 {
            Self::None
        } else {
            requested
        })
    }
}

impl SceneRecordKind {
    fn from_code(value: u8) -> Result<Self, SceneError> {
        match value {
            0 => Ok(Self::Scatter),
            1 => Ok(Self::Polyline),
            2 => Ok(Self::Rect),
            3 => Ok(Self::Band),
            4 => Ok(Self::PolyFill),
            5 => Ok(Self::Image),
            _ => Err(SceneError::Length),
        }
    }
}

/// Compact authored expansion mode accepted by the whole-Scene ABI. The enum is
/// deliberately not serialized into Scene: Rust expands compact step,
/// ribbon, hex-cell, heatmap-lattice, painted-heatmap, segment-pair,
/// triangle-face, density-blit, curve-flatten, and band-flatten inputs to
/// ordinary canonical records before Scene v31 encoding.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
#[repr(u8)]
pub enum SceneExpansionMode {
    None = 0,
    /// Compact polyline or band step-before vertices.
    Pre = 1,
    /// Compact polyline or band step-mid vertices.
    Mid = 2,
    /// Compact polyline or band step-after vertices.
    Post = 3,
    /// Two adjacent Band rows describe upper then lower cubic edge endpoints.
    Ribbon = 4,
    /// One PolyFill row is a hexbin center plus `hex_dx`/`hex_dy` pitch.
    HexCell = 5,
    /// Two Rect rows carry a regular lattice extent plus rows then cols.
    HeatmapLattice = 6,
    /// One Polyline row is a disconnected endpoint pair.
    SegmentPair = 7,
    /// Two PolyFill rows are one triangle face: `(x0,y0,x1,y1)` then `(x2,y2,0,0)`.
    TriangleFace = 8,
    /// Two Rect rows like [`Self::HeatmapLattice`], plus an XYHP paint plane
    /// keyed by stable id. Rust tessellates cells and interns unique fills.
    HeatmapPainted = 9,
    /// Two Rect rows like [`Self::HeatmapLattice`], plus an XYHP density plane
    /// (log-u8 colormap or log-u8 + mean-color RGBA). Cartesian batches emit
    /// one Image record and an XYIM RGBA sidecar. Polar batches (ABI 143)
    /// skip empty cells and intern occupied fills as Rects so `with_polar`
    /// tessellates annular-sector PolyFill wedges; Image+XYPL stays forbidden.
    DensityBlit = 10,
    /// Compact polyline knots flatten through `geom::curve_flatten` into a
    /// denser Polyline run (`SCENE_CURVE_STEPS` samples per increasing span).
    /// Runs shorter than three vertices stay identity so `n<3` smooth lines
    /// match the compatibility `curve_points` fallback.
    CurveFlatten = 11,
    /// Compact Band knots flatten top (`y0`) and base (`y1`) through
    /// `geom::curve_flatten` into a denser Band run. Shared `x0` (`x0==x1`)
    /// parameterization matches cartesian `area(curve="smooth")` and
    /// `error_band(curve="smooth")`. Polar smooth stays identity chords
    /// (polar-axes.md §5). `n<3` stays identity so short filled bands match
    /// the compatibility fallback.
    BandFlatten = 12,
}

impl SceneExpansionMode {
    fn from_code(value: u8) -> Result<Self, SceneError> {
        match value {
            0 => Ok(Self::None),
            1 => Ok(Self::Pre),
            2 => Ok(Self::Mid),
            3 => Ok(Self::Post),
            4 => Ok(Self::Ribbon),
            5 => Ok(Self::HexCell),
            6 => Ok(Self::HeatmapLattice),
            7 => Ok(Self::SegmentPair),
            8 => Ok(Self::TriangleFace),
            9 => Ok(Self::HeatmapPainted),
            10 => Ok(Self::DensityBlit),
            11 => Ok(Self::CurveFlatten),
            12 => Ok(Self::BandFlatten),
            _ => Err(SceneError::Length),
        }
    }

    fn expected_kind(self) -> Option<u8> {
        match self {
            Self::None => None,
            Self::Pre | Self::Mid | Self::Post | Self::SegmentPair | Self::CurveFlatten => {
                Some(SceneRecordKind::Polyline as u8)
            }
            Self::Ribbon | Self::BandFlatten => Some(SceneRecordKind::Band as u8),
            Self::HexCell | Self::TriangleFace => Some(SceneRecordKind::PolyFill as u8),
            Self::HeatmapLattice | Self::HeatmapPainted | Self::DensityBlit => {
                Some(SceneRecordKind::Rect as u8)
            }
        }
    }

    fn allows_nonzero_diameter(self) -> bool {
        matches!(
            self,
            Self::HeatmapLattice | Self::HeatmapPainted | Self::DensityBlit
        )
    }
}

/// Fixed segments per canonical ribbon edge. The count is product policy: it
/// is intentionally view-independent and shared by every Scene consumer.
pub const SCENE_RIBBON_STEPS: usize = geom::RIBBON_STEPS;

/// Fixed samples per compact smooth-polyline span. Same product count as
/// `geom::BEZIER_STEPS` and the retired host `curve_flatten` path.
pub const SCENE_CURVE_STEPS: usize = geom::BEZIER_STEPS;

fn curve_flatten_required(x: &[f64]) -> Result<usize, SceneError> {
    let n = x.len();
    if n < 3 {
        return Ok(n);
    }
    let mut written = 1usize;
    for window in x.windows(2) {
        let extra = if window[1] - window[0] <= 0.0 {
            1
        } else {
            SCENE_CURVE_STEPS
        };
        written = written.checked_add(extra).ok_or(SceneError::Limit)?;
    }
    Ok(written)
}

/// Pointy-top hexagon ring as fractions of `hex_dx`/`hex_dy`. Same contract as
/// the retired Python/Node Scene packers and `js/src/50_chartview.ts`.
pub const SCENE_HEXBIN_RING: [(f64, f64); 6] = [
    (0.0, -1.0 / 3.0),
    (0.5, -1.0 / 6.0),
    (0.5, 1.0 / 6.0),
    (0.0, 1.0 / 3.0),
    (-0.5, 1.0 / 6.0),
    (-0.5, -1.0 / 6.0),
];

/// XYHP v1 painted-heatmap sidecar (ABI 134). Hosts pack one plane per
/// `HeatmapPainted` lattice; Rust tessellates cells and interns unique fills.
/// Kind 2 packs a colormap name instead of RGB stops (ABI 135).
pub const XYHP_MAGIC: &[u8; 4] = b"XYHP";
pub const XYHP_VERSION: u32 = 1;
pub const XYHP_V1_HEADER_BYTES: usize = 16;
pub const XYHP_PLANE_HEADER_BYTES: usize = 24;
pub const XYHP_PAINT_RGBA: u32 = 0;
pub const XYHP_PAINT_COLORMAP: u32 = 1;
pub const XYHP_PAINT_NAMED: u32 = 2;
pub const XYHP_PAINT_DENSITY: u32 = 3;
pub const XYHP_PAINT_MEAN_COLOR: u32 = 4;
pub const XYHP_MAX_NAME_BYTES: usize = 64;
/// XYIM v1 image-blit sidecar (ABI 137 / Scene v27). One RGBA8 plane per
/// `DensityBlit` Image record, keyed by stable id, image-top-first.
pub const XYIM_MAGIC: &[u8; 4] = b"XYIM";
pub const XYIM_VERSION: u32 = 1;
pub const XYIM_V1_HEADER_BYTES: usize = 16;
pub const XYIM_PLANE_HEADER_BYTES: usize = 24;
pub const XYIM_FORMAT_RGBA8: u32 = 0;
pub const MAX_SCENE_IMAGE_PIXELS: usize = 2_000_000;
/// XYEX v1 wraps optional XYPL polar bytes plus optional XYHP paint so
/// `xyg_scene_batch_encode` stays at Koffi's 64-parameter ceiling.
/// XYEX v2 adds a dash length so constant dash, linecap, and authored-marker
/// sidecars ride the same extras pointer as XYDS/XYLC/XYMP (ABI 138–145)
/// without a 65th ABI argument.
pub const XYEX_MAGIC: &[u8; 4] = b"XYEX";
pub const XYEX_VERSION: u32 = 1;
pub const XYEX_VERSION_DASH: u32 = 2;
pub const XYEX_V1_HEADER_BYTES: usize = 16;
pub const XYEX_V2_HEADER_BYTES: usize = 20;
/// XYDS v1 constant-dash sidecar (ABI 138 / Scene v28). One entry per dashed
/// host style_ref; solid styles are omitted. Appended after XYIM so undashed
/// Cartesian scenes only change the Scene version u32.
pub const XYDS_MAGIC: &[u8; 4] = b"XYDS";
pub const XYDS_VERSION: u32 = 1;
pub const XYDS_V1_HEADER_BYTES: usize = 16;
pub const XYDS_MAX_VALUES: usize = 8;
/// XYLC v1 constant-linecap sidecar (ABI 139 / Scene v29). One entry per
/// non-round host style_ref (`0=butt`, `2=square`); round (`1`) is omitted.
/// Concatenated after XYDS in the extras dash slot and the encoded Scene.
pub const XYLC_MAGIC: &[u8; 4] = b"XYLC";
pub const XYLC_VERSION: u32 = 1;
pub const XYLC_V1_HEADER_BYTES: usize = 16;
pub const XYLC_ENTRY_BYTES: usize = 8;
pub const LINECAP_BUTT: u8 = 0;
pub const LINECAP_ROUND: u8 = 1;
pub const LINECAP_SQUARE: u8 = 2;
/// XYMP v1 authored-marker sidecar (ABI 145). One entry per host style_ref
/// that carries a constant validated `marker_path`. Concatenated after XYLC
/// in the extras dash slot. Encoded Scene does not keep XYMP: `prepared_mark_records`
/// tessellates scatter centres to PolyFill/Polyline (v31 kinds).
pub const XYMP_MAGIC: &[u8; 4] = b"XYMP";
pub const XYMP_VERSION: u32 = 1;
pub const XYMP_V1_HEADER_BYTES: usize = 16;
pub const XYMP_MAX_CONTOURS: usize = 32;
pub const XYMP_MAX_VERTICES: usize = 96;
pub const XYMP_VERTEX_LIMIT: f64 = 0.500001;
/// XYGR v1 constant linear-gradient fill sidecar (ABI 146). One entry per
/// host style_ref that carries a validated mark `fill` `{space, dir, stops}`.
/// Concatenated after XYMP in the extras dash slot. Encoded Scene keeps XYGR
/// (paint sidecar) so SVG/raster can emit `<linearGradient>` / `OP_FILL_POLY_GRAD`.
/// ABI 183 admits constant ribbon `color2_ch` as this same XYGR mark-space
/// `dir=right` two-stop fill. Data-driven / per-item `color2_ch` and explicit
/// `FLAG_COLOR2` stay fail-closed.
pub const XYGR_MAGIC: &[u8; 4] = b"XYGR";
pub const XYGR_VERSION: u32 = 1;
pub const XYGR_V1_HEADER_BYTES: usize = 16;
pub const XYGR_ENTRY_BYTES: usize = 16;
pub const XYGR_STOP_BYTES: usize = 8;
pub const XYGR_MAX_STOPS: usize = 8;
pub const XYGR_DIR_DOWN: u32 = 0;
pub const XYGR_DIR_UP: u32 = 1;
pub const XYGR_DIR_RIGHT: u32 = 2;
pub const XYGR_DIR_LEFT: u32 = 3;
pub const XYGR_FLAG_PLOT_SPACE: u32 = 1 << 2;
/// XYMG v1 authored-glyph sidecar (ABI 170). One entry per host style_ref
/// that carries a constant single-character `marker_glyph`. Concatenated
/// after XYGR in the extras dash slot. Encoded Scene keeps XYMG so SVG
/// emits `<text>` and raster emits `OP_TEXT` instead of a disc. Combined
/// `marker_path` + `marker_glyph` stays fail-closed.
pub const XYMG_MAGIC: &[u8; 4] = b"XYMG";
pub const XYMG_VERSION: u32 = 1;
pub const XYMG_V1_HEADER_BYTES: usize = 16;
pub const XYMG_ENTRY_BYTES: usize = 12;
pub const XYMG_MAX_UTF8: usize = 4;

/// One XYHP paint plane keyed by the compact lattice's stable identity.
#[derive(Clone, Copy, Debug)]
struct HeatmapPaintPlane<'a> {
    stable_id: u64,
    rows: usize,
    cols: usize,
    kind: u32,
    payload: &'a [u8],
}

/// Owned style table after painted-heatmap intern. `None` from expansion means
/// the caller should keep the authored fill/stroke arrays.
#[derive(Debug, Clone, PartialEq)]
pub struct ExpandedSceneStyles {
    pub fill_rgba: Vec<u8>,
    pub stroke_rgba: Vec<u8>,
    pub stroke_width: Vec<f64>,
}

/// One decoded density/image blit plane. RGBA8 is image-top-first, `width*height*4`.
#[derive(Debug, Clone, PartialEq)]
pub struct SceneImage {
    pub stable_id: u64,
    pub width: u32,
    pub height: u32,
    pub rgba: Vec<u8>,
}

fn scene_read_u32(bytes: &[u8], offset: usize) -> Result<u32, SceneError> {
    Ok(u32::from_le_bytes(
        bytes
            .get(offset..offset + 4)
            .ok_or(SceneError::Length)?
            .try_into()
            .map_err(|_| SceneError::Length)?,
    ))
}

fn scene_read_u64(bytes: &[u8], offset: usize) -> Result<u64, SceneError> {
    Ok(u64::from_le_bytes(
        bytes
            .get(offset..offset + 8)
            .ok_or(SceneError::Length)?
            .try_into()
            .map_err(|_| SceneError::Length)?,
    ))
}

fn scene_read_f64(bytes: &[u8], offset: usize) -> Result<f64, SceneError> {
    Ok(f64::from_le_bytes(
        bytes
            .get(offset..offset + 8)
            .ok_or(SceneError::Length)?
            .try_into()
            .map_err(|_| SceneError::Length)?,
    ))
}

/// Split a host extras payload into polar XYPL, XYHP paint, and style-sidecar
/// bytes. Empty input is Cartesian with no paint or dash. Raw XYPL (92 bytes)
/// stays valid polar-only authoring. Raw XYHP is Cartesian painted heatmaps.
/// Raw XYDS, raw XYLC, raw XYMP, raw XYGR, raw XYMG, or XYDS+XYLC+XYMP+XYGR+XYMG concat occupy
/// the dash slot. XYEX v1 wraps polar+paint; XYEX v2 `dash_len` covers those
/// style sidecars.
pub fn split_scene_extras(bytes: &[u8]) -> Option<(&[u8], &[u8], &[u8])> {
    if bytes.is_empty() {
        return Some((&[], &[], &[]));
    }
    if bytes.len() == XYPL_V1_BYTES && bytes.get(..4) == Some(&XYPL_MAGIC[..]) {
        return Some((bytes, &[], &[]));
    }
    if bytes.get(..4) == Some(&XYHP_MAGIC[..]) {
        return Some((&[], bytes, &[]));
    }
    if bytes.get(..4) == Some(&XYDS_MAGIC[..])
        || bytes.get(..4) == Some(&XYLC_MAGIC[..])
        || bytes.get(..4) == Some(&XYMP_MAGIC[..])
        || bytes.get(..4) == Some(&XYGR_MAGIC[..])
        || bytes.get(..4) == Some(&XYMG_MAGIC[..])
    {
        return Some((&[], &[], bytes));
    }
    if bytes.get(..4) != Some(&XYEX_MAGIC[..]) {
        return None;
    }
    let version = u32::from_le_bytes(bytes.get(4..8)?.try_into().ok()?);
    let polar_len = u32::from_le_bytes(bytes.get(8..12)?.try_into().ok()?) as usize;
    let paint_len = u32::from_le_bytes(bytes.get(12..16)?.try_into().ok()?) as usize;
    let (header_bytes, dash_len) = if version == XYEX_VERSION {
        (XYEX_V1_HEADER_BYTES, 0usize)
    } else if version == XYEX_VERSION_DASH {
        if bytes.len() < XYEX_V2_HEADER_BYTES {
            return None;
        }
        (
            XYEX_V2_HEADER_BYTES,
            u32::from_le_bytes(bytes.get(16..20)?.try_into().ok()?) as usize,
        )
    } else {
        return None;
    };
    if polar_len != 0 && polar_len != XYPL_V1_BYTES {
        return None;
    }
    let polar_end = header_bytes.checked_add(polar_len)?;
    let paint_end = polar_end.checked_add(paint_len)?;
    let dash_end = paint_end.checked_add(dash_len)?;
    if dash_end != bytes.len() {
        return None;
    }
    let polar = &bytes[header_bytes..polar_end];
    let paint = &bytes[polar_end..paint_end];
    let dash = &bytes[paint_end..dash_end];
    if polar_len == XYPL_V1_BYTES && polar.get(..4) != Some(&XYPL_MAGIC[..]) {
        return None;
    }
    if paint_len > 0 && paint.get(..4) != Some(&XYHP_MAGIC[..]) {
        return None;
    }
    if dash_len > 0
        && dash.get(..4) != Some(&XYDS_MAGIC[..])
        && dash.get(..4) != Some(&XYLC_MAGIC[..])
        && dash.get(..4) != Some(&XYMP_MAGIC[..])
        && dash.get(..4) != Some(&XYGR_MAGIC[..])
        && dash.get(..4) != Some(&XYMG_MAGIC[..])
    {
        return None;
    }
    Some((polar, paint, dash))
}

fn parse_heatmap_paint(bytes: &[u8]) -> Result<Vec<HeatmapPaintPlane<'_>>, SceneError> {
    if bytes.is_empty() {
        return Ok(Vec::new());
    }
    if bytes.len() < XYHP_V1_HEADER_BYTES || bytes.get(..4) != Some(&XYHP_MAGIC[..]) {
        return Err(SceneError::Length);
    }
    if scene_read_u32(bytes, 4)? != XYHP_VERSION {
        return Err(SceneError::Version);
    }
    let n_planes = scene_read_u32(bytes, 8)? as usize;
    if scene_read_u32(bytes, 12)? != 0 {
        return Err(SceneError::Length);
    }
    if n_planes == 0 {
        return Err(SceneError::Length);
    }
    let mut planes = Vec::with_capacity(n_planes);
    let mut cursor = XYHP_V1_HEADER_BYTES;
    for _ in 0..n_planes {
        let header_end = cursor
            .checked_add(XYHP_PLANE_HEADER_BYTES)
            .ok_or(SceneError::Limit)?;
        if header_end > bytes.len() {
            return Err(SceneError::Length);
        }
        let stable_id = scene_read_u64(bytes, cursor)?;
        let rows = scene_read_u32(bytes, cursor + 8)? as usize;
        let cols = scene_read_u32(bytes, cursor + 12)? as usize;
        let kind = scene_read_u32(bytes, cursor + 16)?;
        let payload_len = scene_read_u32(bytes, cursor + 20)? as usize;
        if rows == 0
            || cols == 0
            || !matches!(
                kind,
                XYHP_PAINT_RGBA
                    | XYHP_PAINT_COLORMAP
                    | XYHP_PAINT_NAMED
                    | XYHP_PAINT_DENSITY
                    | XYHP_PAINT_MEAN_COLOR
            )
        {
            return Err(SceneError::Length);
        }
        let payload_end = header_end.checked_add(payload_len).ok_or(SceneError::Limit)?;
        let payload = bytes.get(header_end..payload_end).ok_or(SceneError::Length)?;
        let cells = rows.checked_mul(cols).ok_or(SceneError::Limit)?;
        if kind == XYHP_PAINT_RGBA {
            if payload_len != cells.checked_mul(4).ok_or(SceneError::Limit)? {
                return Err(SceneError::Length);
            }
        } else if kind == XYHP_PAINT_DENSITY {
            if payload_len < 24 {
                return Err(SceneError::Length);
            }
            let count = scene_read_u32(payload, 16)? as usize;
            let subkind = scene_read_u32(payload, 20)?;
            if count == 0 || subkind > 1 {
                return Err(SceneError::Length);
            }
            let tail_bytes = if subkind == 0 {
                if count > XYHP_MAX_NAME_BYTES {
                    return Err(SceneError::Limit);
                }
                count
            } else {
                count.checked_mul(3).ok_or(SceneError::Limit)?
            };
            let expected = 24usize
                .checked_add(cells)
                .and_then(|value| value.checked_add(tail_bytes))
                .ok_or(SceneError::Limit)?;
            if payload_len != expected {
                return Err(SceneError::Length);
            }
        } else if kind == XYHP_PAINT_MEAN_COLOR {
            if payload_len < 24 {
                return Err(SceneError::Length);
            }
            if scene_read_u32(payload, 20)? != 0 {
                return Err(SceneError::Length);
            }
            let rgba_bytes = cells.checked_mul(4).ok_or(SceneError::Limit)?;
            let expected = 24usize
                .checked_add(cells)
                .and_then(|value| value.checked_add(rgba_bytes))
                .ok_or(SceneError::Limit)?;
            if payload_len != expected {
                return Err(SceneError::Length);
            }
        } else {
            // lo, hi, count, pad, values[cells], RGB stops or UTF-8 name
            if payload_len < 24 {
                return Err(SceneError::Length);
            }
            let count = scene_read_u32(payload, 16)? as usize;
            if count == 0 || scene_read_u32(payload, 20)? != 0 {
                return Err(SceneError::Length);
            }
            let values_bytes = cells.checked_mul(8).ok_or(SceneError::Limit)?;
            let tail_bytes = if kind == XYHP_PAINT_NAMED {
                if count > XYHP_MAX_NAME_BYTES {
                    return Err(SceneError::Limit);
                }
                count
            } else {
                count.checked_mul(3).ok_or(SceneError::Limit)?
            };
            let expected = 24usize
                .checked_add(values_bytes)
                .and_then(|value| value.checked_add(tail_bytes))
                .ok_or(SceneError::Limit)?;
            if payload_len != expected {
                return Err(SceneError::Length);
            }
        }
        if planes.iter().any(|plane: &HeatmapPaintPlane<'_>| plane.stable_id == stable_id) {
            return Err(SceneError::Length);
        }
        planes.push(HeatmapPaintPlane {
            stable_id,
            rows,
            cols,
            kind,
            payload,
        });
        cursor = payload_end;
    }
    if cursor != bytes.len() {
        return Err(SceneError::Length);
    }
    Ok(planes)
}

fn style_rgba4(table: &[u8], index: u32) -> Result<[u8; 4], SceneError> {
    let start = (index as usize).checked_mul(4).ok_or(SceneError::Limit)?;
    let slice = table.get(start..start + 4).ok_or(SceneError::Length)?;
    Ok([slice[0], slice[1], slice[2], slice[3]])
}

fn intern_heatmap_fill(
    styles: &mut ExpandedSceneStyles,
    intern: &mut HashMap<[u8; 4], u32>,
    fill: [u8; 4],
    stroke: [u8; 4],
    stroke_width: f64,
) -> Result<u32, SceneError> {
    if let Some(existing) = intern.get(&fill) {
        return Ok(*existing);
    }
    let index = styles.stroke_width.len();
    if index >= MAX_SCENE_STYLES {
        return Err(SceneError::Limit);
    }
    let style_ref = u32::try_from(index).map_err(|_| SceneError::Limit)?;
    styles.fill_rgba.extend_from_slice(&fill);
    styles.stroke_rgba.extend_from_slice(&stroke);
    styles.stroke_width.push(stroke_width);
    intern.insert(fill, style_ref);
    Ok(style_ref)
}

fn padded_colormap_domain(lo: f64, hi: f64) -> [f64; 2] {
    if lo.is_finite() && hi.is_finite() && lo != hi {
        [lo, hi]
    } else if lo.is_finite() {
        [lo - 0.5, hi + 0.5]
    } else {
        [0.0, 1.0]
    }
}

fn heatmap_colormap_domain(lo: f64, hi: f64, values: impl Iterator<Item = f64>) -> [f64; 2] {
    if lo.is_finite() && hi.is_finite() && lo != hi {
        return [lo, hi];
    }
    let mut min = f64::INFINITY;
    let mut max = f64::NEG_INFINITY;
    for value in values {
        if value.is_finite() {
            min = min.min(value);
            max = max.max(value);
        }
    }
    padded_colormap_domain(min, max)
}

fn heatmap_payload_values(payload: &[u8], cells: usize) -> Result<Vec<f64>, SceneError> {
    let mut values = Vec::with_capacity(cells);
    for index in 0..cells {
        values.push(scene_read_f64(payload, 24 + index * 8)?);
    }
    Ok(values)
}

fn heatmap_paint_fills(plane: HeatmapPaintPlane<'_>, alpha: u8) -> Result<Vec<[u8; 4]>, SceneError> {
    if plane.kind == XYHP_PAINT_DENSITY || plane.kind == XYHP_PAINT_MEAN_COLOR {
        return Err(SceneError::Length);
    }
    let cells = plane.rows.checked_mul(plane.cols).ok_or(SceneError::Limit)?;
    let mut fills = Vec::with_capacity(cells);
    if plane.kind == XYHP_PAINT_RGBA {
        for row in 0..plane.rows {
            let src_row = plane.rows - 1 - row;
            for col in 0..plane.cols {
                let start = (src_row * plane.cols + col) * 4;
                let slice = plane.payload.get(start..start + 4).ok_or(SceneError::Length)?;
                fills.push([slice[0], slice[1], slice[2], slice[3]]);
            }
        }
        return Ok(fills);
    }
    let values = heatmap_payload_values(plane.payload, cells)?;
    let domain = heatmap_colormap_domain(
        scene_read_f64(plane.payload, 0)?,
        scene_read_f64(plane.payload, 8)?,
        values.iter().copied(),
    );
    let count = scene_read_u32(plane.payload, 16)? as usize;
    let tail_off = 24usize
        .checked_add(cells.checked_mul(8).ok_or(SceneError::Limit)?)
        .ok_or(SceneError::Limit)?;
    let stops = if plane.kind == XYHP_PAINT_NAMED {
        let name_bytes = plane
            .payload
            .get(tail_off..tail_off + count)
            .ok_or(SceneError::Length)?;
        let name = std::str::from_utf8(name_bytes).map_err(|_| SceneError::Length)?;
        colormap::colormap_named_stops(name)
    } else {
        let stops_end = tail_off
            .checked_add(count.checked_mul(3).ok_or(SceneError::Limit)?)
            .ok_or(SceneError::Limit)?;
        let stop_bytes = plane
            .payload
            .get(tail_off..stops_end)
            .ok_or(SceneError::Length)?;
        let mut stops = Vec::with_capacity(count);
        for chunk in stop_bytes.chunks_exact(3) {
            stops.push([chunk[0], chunk[1], chunk[2]]);
        }
        if stops.is_empty() {
            return Err(SceneError::Length);
        }
        stops
    };
    for value in values {
        if !value.is_finite() {
            fills.push([0, 0, 0, 0]);
            continue;
        }
        let t = f64::from(normalize_one_f32(value, domain[0], domain[1], f32::NAN));
        fills.push(if t.is_nan() {
            [0, 0, 0, 0]
        } else {
            colormap_color(t, &stops, alpha)
        });
    }
    Ok(fills)
}

fn density_blit_plane(plane: &HeatmapPaintPlane<'_>, rows: usize, cols: usize) -> bool {
    matches!(plane.kind, XYHP_PAINT_DENSITY | XYHP_PAINT_MEAN_COLOR)
        && plane.rows == rows
        && plane.cols == cols
}

fn density_occupied_cells(rgba: &[u8]) -> usize {
    rgba.chunks_exact(4).filter(|pixel| pixel[3] != 0).count()
}

fn density_data_cell_fill(rgba: &[u8], cols: usize, rows: usize, col: usize, row: usize) -> [u8; 4] {
    let image_row = rows - 1 - row;
    let start = (image_row * cols + col) * 4;
    [rgba[start], rgba[start + 1], rgba[start + 2], rgba[start + 3]]
}

fn push_polar_density_cells(
    output: &mut ExpandedSceneRecords,
    painted_styles: &mut ExpandedSceneStyles,
    intern: &mut HashMap<[u8; 4], u32>,
    stable_id: u64,
    image: &SceneImage,
    rows: usize,
    cols: usize,
    x0: f64,
    y0: f64,
    dx: f64,
    dy: f64,
) -> Result<(), SceneError> {
    let rgba = &image.rgba;
    for row in 0..rows {
        for col in 0..cols {
            let fill = density_data_cell_fill(rgba, cols, rows, col, row);
            if fill[3] == 0 {
                continue;
            }
            let cell_style = intern_heatmap_fill(painted_styles, intern, fill, [0, 0, 0, 0], 0.0)?;
            output.push_heatmap_cell(
                stable_id,
                cell_style,
                x0 + col as f64 * dx,
                y0 + row as f64 * dy,
                x0 + (col + 1) as f64 * dx,
                y0 + (row + 1) as f64 * dy,
            );
        }
    }
    Ok(())
}

fn density_image_from_plane(plane: HeatmapPaintPlane<'_>) -> Result<SceneImage, SceneError> {
    match plane.kind {
        XYHP_PAINT_DENSITY => density_colormap_image_from_plane(plane),
        XYHP_PAINT_MEAN_COLOR => density_mean_color_image_from_plane(plane),
        _ => Err(SceneError::Length),
    }
}

fn density_colormap_image_from_plane(
    plane: HeatmapPaintPlane<'_>,
) -> Result<SceneImage, SceneError> {
    if plane.kind != XYHP_PAINT_DENSITY {
        return Err(SceneError::Length);
    }
    let cells = plane.rows.checked_mul(plane.cols).ok_or(SceneError::Limit)?;
    if cells == 0 || cells > MAX_SCENE_IMAGE_PIXELS {
        return Err(SceneError::Limit);
    }
    if plane.payload.len() < 24 {
        return Err(SceneError::Length);
    }
    let maximum = scene_read_f64(plane.payload, 0)?;
    let opacity = scene_read_f64(plane.payload, 8)?;
    let count = scene_read_u32(plane.payload, 16)? as usize;
    let subkind = scene_read_u32(plane.payload, 20)?;
    let encoded_end = 24usize.checked_add(cells).ok_or(SceneError::Limit)?;
    let encoded = plane
        .payload
        .get(24..encoded_end)
        .ok_or(SceneError::Length)?;
    let tail = plane.payload.get(encoded_end..).ok_or(SceneError::Length)?;
    let stops = if subkind == 0 {
        let name = std::str::from_utf8(tail).map_err(|_| SceneError::Length)?;
        if name.len() != count {
            return Err(SceneError::Length);
        }
        colormap::colormap_named_stops(name)
    } else if subkind == 1 {
        if tail.len() != count.checked_mul(3).ok_or(SceneError::Limit)? {
            return Err(SceneError::Length);
        }
        let mut stops = Vec::with_capacity(count);
        for chunk in tail.chunks_exact(3) {
            stops.push([chunk[0], chunk[1], chunk[2]]);
        }
        if stops.is_empty() {
            return Err(SceneError::Length);
        }
        stops
    } else {
        return Err(SceneError::Length);
    };
    let mut rgba = vec![0u8; cells.checked_mul(4).ok_or(SceneError::Limit)?];
    if !density_rgba_into(encoded, plane.cols, plane.rows, maximum, &stops, opacity, &mut rgba)
    {
        return Err(SceneError::Length);
    }
    Ok(SceneImage {
        stable_id: plane.stable_id,
        width: u32::try_from(plane.cols).map_err(|_| SceneError::Limit)?,
        height: u32::try_from(plane.rows).map_err(|_| SceneError::Limit)?,
        rgba,
    })
}

fn density_mean_color_image_from_plane(
    plane: HeatmapPaintPlane<'_>,
) -> Result<SceneImage, SceneError> {
    if plane.kind != XYHP_PAINT_MEAN_COLOR {
        return Err(SceneError::Length);
    }
    let cells = plane.rows.checked_mul(plane.cols).ok_or(SceneError::Limit)?;
    if cells == 0 || cells > MAX_SCENE_IMAGE_PIXELS {
        return Err(SceneError::Limit);
    }
    if plane.payload.len() < 24 {
        return Err(SceneError::Length);
    }
    let maximum = scene_read_f64(plane.payload, 0)?;
    let opacity = scene_read_f64(plane.payload, 8)?;
    if scene_read_u32(plane.payload, 20)? != 0 {
        return Err(SceneError::Length);
    }
    let encoded_end = 24usize.checked_add(cells).ok_or(SceneError::Limit)?;
    let rgba_end = encoded_end
        .checked_add(cells.checked_mul(4).ok_or(SceneError::Limit)?)
        .ok_or(SceneError::Limit)?;
    if plane.payload.len() != rgba_end {
        return Err(SceneError::Length);
    }
    let encoded = plane
        .payload
        .get(24..encoded_end)
        .ok_or(SceneError::Length)?;
    let mean_rgba = plane
        .payload
        .get(encoded_end..rgba_end)
        .ok_or(SceneError::Length)?;
    let mut rgba = vec![0u8; cells.checked_mul(4).ok_or(SceneError::Limit)?];
    if !density_mean_color_rgba_into(
        encoded,
        mean_rgba,
        plane.cols,
        plane.rows,
        maximum,
        opacity,
        &mut rgba,
    ) {
        return Err(SceneError::Length);
    }
    Ok(SceneImage {
        stable_id: plane.stable_id,
        width: u32::try_from(plane.cols).map_err(|_| SceneError::Limit)?,
        height: u32::try_from(plane.rows).map_err(|_| SceneError::Limit)?,
        rgba,
    })
}

fn encode_xyim(images: &[SceneImage]) -> Result<Vec<u8>, SceneError> {
    if images.is_empty() {
        return Ok(Vec::new());
    }
    let mut out = Vec::new();
    out.extend_from_slice(XYIM_MAGIC);
    out.extend_from_slice(&XYIM_VERSION.to_le_bytes());
    out.extend_from_slice(&(images.len() as u32).to_le_bytes());
    out.extend_from_slice(&0u32.to_le_bytes());
    for image in images {
        let pixels = (image.width as usize)
            .checked_mul(image.height as usize)
            .and_then(|n| n.checked_mul(4))
            .ok_or(SceneError::Limit)?;
        if image.rgba.len() != pixels || pixels == 0 || pixels / 4 > MAX_SCENE_IMAGE_PIXELS {
            return Err(SceneError::Length);
        }
        out.extend_from_slice(&image.stable_id.to_le_bytes());
        out.extend_from_slice(&image.width.to_le_bytes());
        out.extend_from_slice(&image.height.to_le_bytes());
        out.extend_from_slice(&XYIM_FORMAT_RGBA8.to_le_bytes());
        out.extend_from_slice(&(pixels as u32).to_le_bytes());
        out.extend_from_slice(&image.rgba);
    }
    Ok(out)
}

fn parse_xyim_envelope(bytes: &[u8]) -> Result<(Vec<SceneImage>, usize), SceneError> {
    if bytes.is_empty() {
        return Ok((Vec::new(), 0));
    }
    if bytes.len() < XYIM_V1_HEADER_BYTES || bytes.get(..4) != Some(&XYIM_MAGIC[..]) {
        return Err(SceneError::Length);
    }
    if scene_read_u32(bytes, 4)? != XYIM_VERSION {
        return Err(SceneError::Version);
    }
    let n_planes = scene_read_u32(bytes, 8)? as usize;
    if scene_read_u32(bytes, 12)? != 0 || n_planes == 0 {
        return Err(SceneError::Length);
    }
    let mut images = Vec::with_capacity(n_planes);
    let mut cursor = XYIM_V1_HEADER_BYTES;
    for _ in 0..n_planes {
        let header_end = cursor
            .checked_add(XYIM_PLANE_HEADER_BYTES)
            .ok_or(SceneError::Limit)?;
        if header_end > bytes.len() {
            return Err(SceneError::Length);
        }
        let stable_id = scene_read_u64(bytes, cursor)?;
        let width = scene_read_u32(bytes, cursor + 8)?;
        let height = scene_read_u32(bytes, cursor + 12)?;
        let format = scene_read_u32(bytes, cursor + 16)?;
        let byte_len = scene_read_u32(bytes, cursor + 20)? as usize;
        if format != XYIM_FORMAT_RGBA8 || width == 0 || height == 0 {
            return Err(SceneError::Length);
        }
        let pixels = (width as usize)
            .checked_mul(height as usize)
            .and_then(|n| n.checked_mul(4))
            .ok_or(SceneError::Limit)?;
        if byte_len != pixels || pixels / 4 > MAX_SCENE_IMAGE_PIXELS {
            return Err(SceneError::Length);
        }
        let payload_end = header_end.checked_add(byte_len).ok_or(SceneError::Limit)?;
        let rgba = bytes
            .get(header_end..payload_end)
            .ok_or(SceneError::Length)?
            .to_vec();
        if images.iter().any(|image: &SceneImage| image.stable_id == stable_id) {
            return Err(SceneError::Length);
        }
        images.push(SceneImage {
            stable_id,
            width,
            height,
            rgba,
        });
        cursor = payload_end;
    }
    Ok((images, cursor))
}

fn parse_xyim(bytes: &[u8]) -> Result<Vec<SceneImage>, SceneError> {
    if bytes.is_empty() {
        return Ok(Vec::new());
    }
    let (images, cursor) = parse_xyim_envelope(bytes)?;
    if cursor != bytes.len() {
        return Err(SceneError::Length);
    }
    Ok(images)
}

#[derive(Clone, Copy, Debug, PartialEq)]
struct StyleDash {
    style_ref: u32,
    count: u8,
    values: [f32; 8],
}

#[cfg(test)]
fn encode_xyds(entries: &[StyleDash]) -> Result<Vec<u8>, SceneError> {
    if entries.is_empty() {
        return Ok(Vec::new());
    }
    if entries.len() > MAX_SCENE_STYLES {
        return Err(SceneError::Limit);
    }
    let mut seen = std::collections::BTreeSet::new();
    let mut out = Vec::new();
    out.extend_from_slice(XYDS_MAGIC);
    out.extend_from_slice(&XYDS_VERSION.to_le_bytes());
    out.extend_from_slice(&(entries.len() as u32).to_le_bytes());
    out.extend_from_slice(&0u32.to_le_bytes());
    for entry in entries {
        if entry.count < 2
            || entry.count as usize > XYDS_MAX_VALUES
            || !seen.insert(entry.style_ref)
        {
            return Err(SceneError::Length);
        }
        out.extend_from_slice(&entry.style_ref.to_le_bytes());
        out.extend_from_slice(&(u32::from(entry.count)).to_le_bytes());
        for index in 0..entry.count as usize {
            let value = entry.values[index];
            if !value.is_finite() || value <= 0.0 {
                return Err(SceneError::NonFinite);
            }
            out.extend_from_slice(&value.to_le_bytes());
        }
    }
    Ok(out)
}

fn parse_xyds_prefix(bytes: &[u8]) -> Result<(Vec<StyleDash>, usize), SceneError> {
    if bytes.len() < XYDS_V1_HEADER_BYTES || bytes.get(..4) != Some(&XYDS_MAGIC[..]) {
        return Err(SceneError::Length);
    }
    if scene_read_u32(bytes, 4)? != XYDS_VERSION {
        return Err(SceneError::Version);
    }
    let n_entries = scene_read_u32(bytes, 8)? as usize;
    if scene_read_u32(bytes, 12)? != 0 || n_entries == 0 || n_entries > MAX_SCENE_STYLES {
        return Err(SceneError::Length);
    }
    let mut entries = Vec::with_capacity(n_entries);
    let mut seen = std::collections::BTreeSet::new();
    let mut cursor = XYDS_V1_HEADER_BYTES;
    for _ in 0..n_entries {
        if cursor.checked_add(8).ok_or(SceneError::Limit)? > bytes.len() {
            return Err(SceneError::Length);
        }
        let style_ref = scene_read_u32(bytes, cursor)?;
        let count = scene_read_u32(bytes, cursor + 4)? as usize;
        if count < 2 || count > XYDS_MAX_VALUES || !seen.insert(style_ref) {
            return Err(SceneError::Length);
        }
        cursor += 8;
        let values_end = cursor.checked_add(count * 4).ok_or(SceneError::Limit)?;
        if values_end > bytes.len() {
            return Err(SceneError::Length);
        }
        let mut values = [0.0f32; 8];
        for slot in values.iter_mut().take(count) {
            *slot = f32::from_le_bytes(
                bytes[cursor..cursor + 4]
                    .try_into()
                    .map_err(|_| SceneError::Length)?,
            );
            if !slot.is_finite() || *slot <= 0.0 {
                return Err(SceneError::NonFinite);
            }
            cursor += 4;
        }
        entries.push(StyleDash {
            style_ref,
            count: count as u8,
            values,
        });
    }
    Ok((entries, cursor))
}

fn parse_xyds(bytes: &[u8]) -> Result<Vec<StyleDash>, SceneError> {
    if bytes.is_empty() {
        return Ok(Vec::new());
    }
    let (entries, end) = parse_xyds_prefix(bytes)?;
    if end != bytes.len() {
        return Err(SceneError::Length);
    }
    Ok(entries)
}

#[derive(Clone, Copy, Debug, PartialEq)]
struct StyleCap {
    style_ref: u32,
    cap: u8,
}

#[cfg(test)]
fn encode_xylc(entries: &[StyleCap]) -> Result<Vec<u8>, SceneError> {
    if entries.is_empty() {
        return Ok(Vec::new());
    }
    if entries.len() > MAX_SCENE_STYLES {
        return Err(SceneError::Limit);
    }
    let mut seen = std::collections::BTreeSet::new();
    let mut out = Vec::new();
    out.extend_from_slice(XYLC_MAGIC);
    out.extend_from_slice(&XYLC_VERSION.to_le_bytes());
    out.extend_from_slice(&(entries.len() as u32).to_le_bytes());
    out.extend_from_slice(&0u32.to_le_bytes());
    for entry in entries {
        if (entry.cap != LINECAP_BUTT && entry.cap != LINECAP_SQUARE) || !seen.insert(entry.style_ref)
        {
            return Err(SceneError::Length);
        }
        out.extend_from_slice(&entry.style_ref.to_le_bytes());
        out.push(entry.cap);
        out.extend_from_slice(&[0u8, 0, 0]);
    }
    Ok(out)
}

fn parse_xylc_prefix(bytes: &[u8]) -> Result<(Vec<StyleCap>, usize), SceneError> {
    if bytes.len() < XYLC_V1_HEADER_BYTES || bytes.get(..4) != Some(&XYLC_MAGIC[..]) {
        return Err(SceneError::Length);
    }
    if scene_read_u32(bytes, 4)? != XYLC_VERSION {
        return Err(SceneError::Version);
    }
    let n_entries = scene_read_u32(bytes, 8)? as usize;
    if scene_read_u32(bytes, 12)? != 0 || n_entries == 0 || n_entries > MAX_SCENE_STYLES {
        return Err(SceneError::Length);
    }
    let mut entries = Vec::with_capacity(n_entries);
    let mut seen = std::collections::BTreeSet::new();
    let mut cursor = XYLC_V1_HEADER_BYTES;
    for _ in 0..n_entries {
        let end = cursor
            .checked_add(XYLC_ENTRY_BYTES)
            .ok_or(SceneError::Limit)?;
        if end > bytes.len() {
            return Err(SceneError::Length);
        }
        let style_ref = scene_read_u32(bytes, cursor)?;
        let cap = bytes[cursor + 4];
        if (cap != LINECAP_BUTT && cap != LINECAP_SQUARE)
            || bytes[cursor + 5..cursor + 8] != [0, 0, 0]
            || !seen.insert(style_ref)
        {
            return Err(SceneError::Length);
        }
        cursor = end;
        entries.push(StyleCap { style_ref, cap });
    }
    Ok((entries, cursor))
}

fn parse_xylc(bytes: &[u8]) -> Result<Vec<StyleCap>, SceneError> {
    if bytes.is_empty() {
        return Ok(Vec::new());
    }
    let (entries, end) = parse_xylc_prefix(bytes)?;
    if end != bytes.len() {
        return Err(SceneError::Length);
    }
    Ok(entries)
}

#[derive(Clone, Debug, PartialEq)]
struct AuthoredMarkerPath {
    filled: bool,
    contours: Vec<Vec<(f64, f64)>>,
}

struct StyleMarkerPath {
    style_ref: u32,
    path: AuthoredMarkerPath,
}

fn parse_xymp_prefix(bytes: &[u8]) -> Result<(Vec<StyleMarkerPath>, usize), SceneError> {
    if bytes.len() < XYMP_V1_HEADER_BYTES || bytes.get(..4) != Some(&XYMP_MAGIC[..]) {
        return Err(SceneError::Length);
    }
    if scene_read_u32(bytes, 4)? != XYMP_VERSION {
        return Err(SceneError::Version);
    }
    let n_entries = scene_read_u32(bytes, 8)? as usize;
    if scene_read_u32(bytes, 12)? != 0 || n_entries == 0 || n_entries > MAX_SCENE_STYLES {
        return Err(SceneError::Length);
    }
    let mut entries = Vec::with_capacity(n_entries);
    let mut seen = std::collections::BTreeSet::new();
    let mut cursor = XYMP_V1_HEADER_BYTES;
    for _ in 0..n_entries {
        if cursor.checked_add(16).ok_or(SceneError::Limit)? > bytes.len() {
            return Err(SceneError::Length);
        }
        let style_ref = scene_read_u32(bytes, cursor)?;
        let flags = scene_read_u32(bytes, cursor + 4)?;
        let n_contours = scene_read_u32(bytes, cursor + 8)? as usize;
        let n_vertices = scene_read_u32(bytes, cursor + 12)? as usize;
        if flags > 1
            || n_contours == 0
            || n_contours > XYMP_MAX_CONTOURS
            || n_vertices < 2
            || n_vertices > XYMP_MAX_VERTICES
            || !seen.insert(style_ref)
        {
            return Err(SceneError::Length);
        }
        cursor += 16;
        let filled = flags == 1;
        let mut contours = Vec::with_capacity(n_contours);
        let mut counted = 0usize;
        for _ in 0..n_contours {
            if cursor.checked_add(8).ok_or(SceneError::Limit)? > bytes.len() {
                return Err(SceneError::Length);
            }
            let n_verts = scene_read_u32(bytes, cursor)? as usize;
            if scene_read_u32(bytes, cursor + 4)? != 0
                || n_verts < 2
                || (filled && n_verts < 3)
            {
                return Err(SceneError::Length);
            }
            cursor += 8;
            let values_end = cursor
                .checked_add(n_verts.checked_mul(16).ok_or(SceneError::Limit)?)
                .ok_or(SceneError::Limit)?;
            if values_end > bytes.len() {
                return Err(SceneError::Length);
            }
            let mut contour = Vec::with_capacity(n_verts);
            for _ in 0..n_verts {
                let x = scene_read_f64(bytes, cursor)?;
                let y = scene_read_f64(bytes, cursor + 8)?;
                if !x.is_finite()
                    || !y.is_finite()
                    || x.abs() > XYMP_VERTEX_LIMIT
                    || y.abs() > XYMP_VERTEX_LIMIT
                {
                    return Err(SceneError::NonFinite);
                }
                contour.push((x, y));
                cursor += 16;
            }
            counted = counted.checked_add(n_verts).ok_or(SceneError::Limit)?;
            contours.push(contour);
        }
        if counted != n_vertices {
            return Err(SceneError::Length);
        }
        entries.push(StyleMarkerPath {
            style_ref,
            path: AuthoredMarkerPath { filled, contours },
        });
    }
    Ok((entries, cursor))
}

fn parse_xymp(bytes: &[u8]) -> Result<Vec<StyleMarkerPath>, SceneError> {
    if bytes.is_empty() {
        return Ok(Vec::new());
    }
    let (entries, end) = parse_xymp_prefix(bytes)?;
    if end != bytes.len() {
        return Err(SceneError::Length);
    }
    Ok(entries)
}

#[cfg(test)]
fn encode_xymp(entries: &[StyleMarkerPath]) -> Result<Vec<u8>, SceneError> {
    if entries.is_empty() {
        return Ok(Vec::new());
    }
    if entries.len() > MAX_SCENE_STYLES {
        return Err(SceneError::Limit);
    }
    let mut seen = std::collections::BTreeSet::new();
    let mut out = Vec::new();
    out.extend_from_slice(XYMP_MAGIC);
    out.extend_from_slice(&XYMP_VERSION.to_le_bytes());
    out.extend_from_slice(&(entries.len() as u32).to_le_bytes());
    out.extend_from_slice(&0u32.to_le_bytes());
    for entry in entries {
        let n_vertices: usize = entry.path.contours.iter().map(Vec::len).sum();
        if entry.path.contours.is_empty()
            || entry.path.contours.len() > XYMP_MAX_CONTOURS
            || n_vertices < 2
            || n_vertices > XYMP_MAX_VERTICES
            || !seen.insert(entry.style_ref)
        {
            return Err(SceneError::Length);
        }
        out.extend_from_slice(&entry.style_ref.to_le_bytes());
        out.extend_from_slice(&(u32::from(entry.path.filled)).to_le_bytes());
        out.extend_from_slice(&(entry.path.contours.len() as u32).to_le_bytes());
        out.extend_from_slice(&(n_vertices as u32).to_le_bytes());
        for contour in &entry.path.contours {
            if contour.len() < 2 || (entry.path.filled && contour.len() < 3) {
                return Err(SceneError::Length);
            }
            out.extend_from_slice(&(contour.len() as u32).to_le_bytes());
            out.extend_from_slice(&0u32.to_le_bytes());
            for &(x, y) in contour {
                if !x.is_finite()
                    || !y.is_finite()
                    || x.abs() > XYMP_VERTEX_LIMIT
                    || y.abs() > XYMP_VERTEX_LIMIT
                {
                    return Err(SceneError::NonFinite);
                }
                out.extend_from_slice(&x.to_le_bytes());
                out.extend_from_slice(&y.to_le_bytes());
            }
        }
    }
    Ok(out)
}

#[derive(Clone, Debug, PartialEq)]
struct AuthoredGradient {
    plot_space: bool,
    dir: u8,
    stops: Vec<(f32, [u8; 4])>,
}

struct StyleGradient {
    style_ref: u32,
    gradient: AuthoredGradient,
}

fn parse_xygr_prefix(bytes: &[u8]) -> Result<(Vec<StyleGradient>, usize), SceneError> {
    if bytes.len() < XYGR_V1_HEADER_BYTES || bytes.get(..4) != Some(&XYGR_MAGIC[..]) {
        return Err(SceneError::Length);
    }
    if scene_read_u32(bytes, 4)? != XYGR_VERSION {
        return Err(SceneError::Version);
    }
    let n_entries = scene_read_u32(bytes, 8)? as usize;
    if scene_read_u32(bytes, 12)? != 0 || n_entries == 0 || n_entries > MAX_SCENE_STYLES {
        return Err(SceneError::Length);
    }
    let mut entries = Vec::with_capacity(n_entries);
    let mut seen = std::collections::BTreeSet::new();
    let mut cursor = XYGR_V1_HEADER_BYTES;
    for _ in 0..n_entries {
        if cursor
            .checked_add(XYGR_ENTRY_BYTES)
            .ok_or(SceneError::Limit)?
            > bytes.len()
        {
            return Err(SceneError::Length);
        }
        let style_ref = scene_read_u32(bytes, cursor)?;
        let flags = scene_read_u32(bytes, cursor + 4)?;
        let n_stops = scene_read_u32(bytes, cursor + 8)? as usize;
        if scene_read_u32(bytes, cursor + 12)? != 0
            || flags & !0b111 != 0
            || (flags & 0b11) > XYGR_DIR_LEFT
            || n_stops < 2
            || n_stops > XYGR_MAX_STOPS
            || !seen.insert(style_ref)
        {
            return Err(SceneError::Length);
        }
        cursor += XYGR_ENTRY_BYTES;
        let stops_end = cursor
            .checked_add(n_stops.checked_mul(XYGR_STOP_BYTES).ok_or(SceneError::Limit)?)
            .ok_or(SceneError::Limit)?;
        if stops_end > bytes.len() {
            return Err(SceneError::Length);
        }
        let mut stops = Vec::with_capacity(n_stops);
        let mut prev_t = f32::NEG_INFINITY;
        for _ in 0..n_stops {
            let t = f32::from_le_bytes(
                bytes[cursor..cursor + 4]
                    .try_into()
                    .map_err(|_| SceneError::Length)?,
            );
            if !t.is_finite() || !(0.0..=1.0).contains(&t) || t < prev_t {
                return Err(SceneError::NonFinite);
            }
            let rgba = [
                bytes[cursor + 4],
                bytes[cursor + 5],
                bytes[cursor + 6],
                bytes[cursor + 7],
            ];
            stops.push((t, rgba));
            prev_t = t;
            cursor += XYGR_STOP_BYTES;
        }
        entries.push(StyleGradient {
            style_ref,
            gradient: AuthoredGradient {
                plot_space: flags & XYGR_FLAG_PLOT_SPACE != 0,
                dir: (flags & 0b11) as u8,
                stops,
            },
        });
    }
    Ok((entries, cursor))
}

fn parse_xygr(bytes: &[u8]) -> Result<Vec<StyleGradient>, SceneError> {
    if bytes.is_empty() {
        return Ok(Vec::new());
    }
    let (entries, end) = parse_xygr_prefix(bytes)?;
    if end != bytes.len() {
        return Err(SceneError::Length);
    }
    Ok(entries)
}

#[cfg(test)]
fn encode_xygr(entries: &[StyleGradient]) -> Result<Vec<u8>, SceneError> {
    if entries.is_empty() {
        return Ok(Vec::new());
    }
    if entries.len() > MAX_SCENE_STYLES {
        return Err(SceneError::Limit);
    }
    let mut seen = std::collections::BTreeSet::new();
    let mut out = Vec::new();
    out.extend_from_slice(XYGR_MAGIC);
    out.extend_from_slice(&XYGR_VERSION.to_le_bytes());
    out.extend_from_slice(&(entries.len() as u32).to_le_bytes());
    out.extend_from_slice(&0u32.to_le_bytes());
    for entry in entries {
        if entry.gradient.stops.len() < 2
            || entry.gradient.stops.len() > XYGR_MAX_STOPS
            || entry.gradient.dir > XYGR_DIR_LEFT as u8
            || !seen.insert(entry.style_ref)
        {
            return Err(SceneError::Length);
        }
        let mut flags = u32::from(entry.gradient.dir);
        if entry.gradient.plot_space {
            flags |= XYGR_FLAG_PLOT_SPACE;
        }
        out.extend_from_slice(&entry.style_ref.to_le_bytes());
        out.extend_from_slice(&flags.to_le_bytes());
        out.extend_from_slice(&(entry.gradient.stops.len() as u32).to_le_bytes());
        out.extend_from_slice(&0u32.to_le_bytes());
        let mut prev_t = f32::NEG_INFINITY;
        for &(t, rgba) in &entry.gradient.stops {
            if !t.is_finite() || !(0.0..=1.0).contains(&t) || t < prev_t {
                return Err(SceneError::NonFinite);
            }
            out.extend_from_slice(&t.to_le_bytes());
            out.extend_from_slice(&rgba);
            prev_t = t;
        }
    }
    Ok(out)
}

struct StyleMarkerGlyph {
    style_ref: u32,
    glyph: String,
}

fn marker_glyph_text(bytes: &[u8]) -> Option<&str> {
    let text = std::str::from_utf8(bytes).ok()?;
    let mut chars = text.chars();
    let ch = chars.next()?;
    if chars.next().is_some() || ch == '\0' || ch == '\n' || ch == '\r' {
        return None;
    }
    Some(text)
}

fn parse_xymg_prefix(bytes: &[u8]) -> Result<(Vec<StyleMarkerGlyph>, usize), SceneError> {
    if bytes.len() < XYMG_V1_HEADER_BYTES || bytes.get(..4) != Some(&XYMG_MAGIC[..]) {
        return Err(SceneError::Length);
    }
    if scene_read_u32(bytes, 4)? != XYMG_VERSION {
        return Err(SceneError::Version);
    }
    let n_entries = scene_read_u32(bytes, 8)? as usize;
    if scene_read_u32(bytes, 12)? != 0 || n_entries == 0 || n_entries > MAX_SCENE_STYLES {
        return Err(SceneError::Length);
    }
    let mut entries = Vec::with_capacity(n_entries);
    let mut seen = std::collections::BTreeSet::new();
    let mut cursor = XYMG_V1_HEADER_BYTES;
    for _ in 0..n_entries {
        if cursor
            .checked_add(XYMG_ENTRY_BYTES)
            .ok_or(SceneError::Limit)?
            > bytes.len()
        {
            return Err(SceneError::Length);
        }
        let style_ref = scene_read_u32(bytes, cursor)?;
        let glyph_len = scene_read_u32(bytes, cursor + 4)? as usize;
        if glyph_len == 0
            || glyph_len > XYMG_MAX_UTF8
            || !seen.insert(style_ref)
        {
            return Err(SceneError::Length);
        }
        let glyph = marker_glyph_text(&bytes[cursor + 8..cursor + 8 + glyph_len])
            .ok_or(SceneError::Length)?
            .to_string();
        cursor += XYMG_ENTRY_BYTES;
        entries.push(StyleMarkerGlyph { style_ref, glyph });
    }
    Ok((entries, cursor))
}

fn parse_xymg(bytes: &[u8]) -> Result<Vec<StyleMarkerGlyph>, SceneError> {
    if bytes.is_empty() {
        return Ok(Vec::new());
    }
    let (entries, end) = parse_xymg_prefix(bytes)?;
    if end != bytes.len() {
        return Err(SceneError::Length);
    }
    Ok(entries)
}

#[cfg(test)]
fn encode_xymg(entries: &[StyleMarkerGlyph]) -> Result<Vec<u8>, SceneError> {
    if entries.is_empty() {
        return Ok(Vec::new());
    }
    if entries.len() > MAX_SCENE_STYLES {
        return Err(SceneError::Limit);
    }
    let mut seen = std::collections::BTreeSet::new();
    let mut out = Vec::new();
    out.extend_from_slice(XYMG_MAGIC);
    out.extend_from_slice(&XYMG_VERSION.to_le_bytes());
    out.extend_from_slice(&(entries.len() as u32).to_le_bytes());
    out.extend_from_slice(&0u32.to_le_bytes());
    for entry in entries {
        let bytes = entry.glyph.as_bytes();
        if marker_glyph_text(bytes).is_none() || !seen.insert(entry.style_ref) {
            return Err(SceneError::Length);
        }
        out.extend_from_slice(&entry.style_ref.to_le_bytes());
        out.extend_from_slice(&(bytes.len() as u32).to_le_bytes());
        let mut padded = [0u8; 4];
        padded[..bytes.len()].copy_from_slice(bytes);
        out.extend_from_slice(&padded);
    }
    Ok(out)
}

fn split_style_sidecars(
    bytes: &[u8],
) -> Result<(&[u8], &[u8], &[u8], &[u8], &[u8]), SceneError> {
    if bytes.is_empty() {
        return Ok((&[], &[], &[], &[], &[]));
    }
    let mut offset = 0usize;
    let dash = if bytes.get(..4) == Some(&XYDS_MAGIC[..]) {
        let (_, end) = parse_xyds_prefix(bytes)?;
        offset = end;
        bytes.get(..end).ok_or(SceneError::Length)?
    } else {
        &[][..]
    };
    let cap = if bytes.get(offset..offset.saturating_add(4)) == Some(&XYLC_MAGIC[..]) {
        let (_, end) = parse_xylc_prefix(&bytes[offset..])?;
        let cap = bytes.get(offset..offset + end).ok_or(SceneError::Length)?;
        offset += end;
        cap
    } else {
        &[][..]
    };
    let markers = if bytes.get(offset..offset.saturating_add(4)) == Some(&XYMP_MAGIC[..]) {
        let (_, end) = parse_xymp_prefix(&bytes[offset..])?;
        let markers = bytes.get(offset..offset + end).ok_or(SceneError::Length)?;
        offset += end;
        markers
    } else {
        &[][..]
    };
    let gradients = if bytes.get(offset..offset.saturating_add(4)) == Some(&XYGR_MAGIC[..]) {
        let (_, end) = parse_xygr_prefix(&bytes[offset..])?;
        let gradients = bytes.get(offset..offset + end).ok_or(SceneError::Length)?;
        offset += end;
        gradients
    } else {
        &[][..]
    };
    let glyphs = if bytes.get(offset..offset.saturating_add(4)) == Some(&XYMG_MAGIC[..]) {
        let (_, end) = parse_xymg_prefix(&bytes[offset..])?;
        let glyphs = bytes.get(offset..offset + end).ok_or(SceneError::Length)?;
        offset += end;
        glyphs
    } else {
        &[][..]
    };
    if offset != bytes.len() {
        return Err(SceneError::Length);
    }
    Ok((dash, cap, markers, gradients, glyphs))
}

fn apply_style_dashes(styles: &mut [EncodedStyle], entries: &[StyleDash]) -> Result<(), SceneError> {
    for entry in entries {
        let index = usize::try_from(entry.style_ref).map_err(|_| SceneError::Length)?;
        let style = styles.get_mut(index).ok_or(SceneError::Length)?;
        style.dash = entry.values;
        style.dash_count = entry.count;
    }
    Ok(())
}

fn apply_style_caps(styles: &mut [EncodedStyle], entries: &[StyleCap]) -> Result<(), SceneError> {
    for entry in entries {
        let index = usize::try_from(entry.style_ref).map_err(|_| SceneError::Length)?;
        let style = styles.get_mut(index).ok_or(SceneError::Length)?;
        style.linecap = entry.cap;
    }
    Ok(())
}

fn apply_style_sidecars(
    styles: &mut [EncodedStyle],
    bytes: &[u8],
) -> Result<(Vec<Option<AuthoredGradient>>, Vec<Option<String>>), SceneError> {
    let (dash, cap, markers, grads, glyphs) = split_style_sidecars(bytes)?;
    apply_style_dashes(styles, &parse_xyds(dash)?)?;
    apply_style_caps(styles, &parse_xylc(cap)?)?;
    let marker_entries = parse_xymp(markers)?;
    let gradient_entries = parse_xygr(grads)?;
    let glyph_entries = parse_xymg(glyphs)?;
    if marker_entries
        .iter()
        .any(|entry| entry.style_ref as usize >= styles.len())
        || gradient_entries
            .iter()
            .any(|entry| entry.style_ref as usize >= styles.len())
        || glyph_entries
            .iter()
            .any(|entry| entry.style_ref as usize >= styles.len())
    {
        return Err(SceneError::Length);
    }
    for entry in marker_entries {
        if !entry.path.filled {
            let style = &mut styles[entry.style_ref as usize];
            style.stroke = style.fill;
            if style.stroke_width <= 0.0 {
                style.stroke_width = 1.0;
            }
        }
    }
    let mut gradients = vec![None; styles.len()];
    for entry in gradient_entries {
        gradients[entry.style_ref as usize] = Some(entry.gradient);
    }
    let mut marker_glyphs = vec![None; styles.len()];
    for entry in glyph_entries {
        marker_glyphs[entry.style_ref as usize] = Some(entry.glyph);
    }
    Ok((gradients, marker_glyphs))
}

fn scene_sidecars_after_chrome(
    bytes: &[u8],
    total: usize,
) -> Result<(&[u8], &[u8], &[u8]), SceneError> {
    let rest = bytes.get(total..).unwrap_or(&[]);
    let (xypl, after) = if rest.len() >= XYPL_V1_BYTES && rest.get(..4) == Some(&XYPL_MAGIC[..]) {
        (&rest[..XYPL_V1_BYTES], &rest[XYPL_V1_BYTES..])
    } else {
        (&[][..], rest)
    };
    if after.is_empty() {
        return Ok((xypl, after, after));
    }
    if after.get(..4) == Some(&XYDS_MAGIC[..])
        || after.get(..4) == Some(&XYLC_MAGIC[..])
        || after.get(..4) == Some(&XYMP_MAGIC[..])
        || after.get(..4) == Some(&XYGR_MAGIC[..])
        || after.get(..4) == Some(&XYMG_MAGIC[..])
    {
        split_style_sidecars(after)?;
        return Ok((xypl, &[][..], after));
    }
    let (images, xyim_end) = parse_xyim_envelope(after)?;
    if images.is_empty() || xyim_end == 0 {
        return Err(SceneError::Length);
    }
    let xyim = after.get(..xyim_end).ok_or(SceneError::Length)?;
    let xyds = after.get(xyim_end..).ok_or(SceneError::Length)?;
    if !xyds.is_empty() {
        split_style_sidecars(xyds)?;
    }
    Ok((xypl, xyim, xyds))
}

fn heatmap_lattice_extent(
    input: &SceneExpansionInput<'_>,
    cursor: usize,
) -> Result<(usize, usize, f64, f64, f64, f64), SceneError> {
    if input.x0[cursor] >= input.x1[cursor]
        || input.y0[cursor] >= input.y1[cursor]
        || input.x0[cursor + 1] != 0.0
        || input.y0[cursor + 1] != 0.0
        || input.x1[cursor + 1] != 0.0
        || input.y1[cursor + 1] != 0.0
    {
        return Err(SceneError::Length);
    }
    let rows = exact_positive_usize(input.diameter[cursor])?;
    let cols = exact_positive_usize(input.diameter[cursor + 1])?;
    Ok((
        rows,
        cols,
        input.x0[cursor],
        input.y0[cursor],
        input.x1[cursor],
        input.y1[cursor],
    ))
}

fn take_paint_plane<'a>(
    planes: &mut [Option<HeatmapPaintPlane<'a>>],
    stable_id: u64,
) -> Result<HeatmapPaintPlane<'a>, SceneError> {
    for slot in planes.iter_mut() {
        match slot {
            Some(plane) if plane.stable_id == stable_id => {
                return Ok(slot.take().expect("matched paint plane"));
            }
            _ => {}
        }
    }
    Err(SceneError::Length)
}

fn exact_positive_usize(value: f64) -> Result<usize, SceneError> {
    if !value.is_finite() || value < 1.0 || value.fract() != 0.0 {
        return Err(SceneError::Length);
    }
    let count = value as usize;
    if count as f64 != value {
        return Err(SceneError::Limit);
    }
    Ok(count)
}

fn scene_expansion_run_end(stable_ids: &[u64], start: usize) -> usize {
    let stable_id = stable_ids[start];
    stable_ids[start + 1..]
        .iter()
        .position(|candidate| *candidate != stable_id)
        .map_or(stable_ids.len(), |offset| start + 1 + offset)
}

fn scene_expansion_group_end(
    stable_ids: &[u64],
    kinds: &[u8],
    expansion_modes: &[u8],
    start: usize,
) -> usize {
    let stable_id = stable_ids[start];
    let kind = kinds[start];
    let mode = expansion_modes[start];
    stable_ids[start + 1..]
        .iter()
        .zip(kinds[start + 1..].iter())
        .zip(expansion_modes[start + 1..].iter())
        .position(|((candidate_id, candidate_kind), candidate_mode)| {
            *candidate_id != stable_id || *candidate_kind != kind || *candidate_mode != mode
        })
        .map_or(stable_ids.len(), |offset| start + 1 + offset)
}

/// Borrowed record columns entering Rust-owned compact record expansion.
pub struct SceneExpansionInput<'a> {
    pub kinds: &'a [u8],
    pub stable_ids: &'a [u64],
    pub style_refs: &'a [u32],
    pub diameter: &'a [f64],
    pub symbols: &'a [u8],
    pub x0: &'a [f64],
    pub y0: &'a [f64],
    pub x1: &'a [f64],
    pub y1: &'a [f64],
    pub expansion_modes: &'a [u8],
}

/// Owned canonical record columns after compact authoring records are expanded.
#[derive(Debug, PartialEq)]
pub struct ExpandedSceneRecords {
    pub kinds: Vec<u8>,
    pub stable_ids: Vec<u64>,
    pub style_refs: Vec<u32>,
    pub diameter: Vec<f64>,
    pub symbols: Vec<u8>,
    pub x0: Vec<f64>,
    pub y0: Vec<f64>,
    pub x1: Vec<f64>,
    pub y1: Vec<f64>,
}

impl ExpandedSceneRecords {
    fn with_capacity(capacity: usize) -> Self {
        Self {
            kinds: Vec::with_capacity(capacity),
            stable_ids: Vec::with_capacity(capacity),
            style_refs: Vec::with_capacity(capacity),
            diameter: Vec::with_capacity(capacity),
            symbols: Vec::with_capacity(capacity),
            x0: Vec::with_capacity(capacity),
            y0: Vec::with_capacity(capacity),
            x1: Vec::with_capacity(capacity),
            y1: Vec::with_capacity(capacity),
        }
    }

    fn push_source(&mut self, input: &SceneExpansionInput<'_>, index: usize) {
        self.kinds.push(input.kinds[index]);
        self.stable_ids.push(input.stable_ids[index]);
        self.style_refs.push(input.style_refs[index]);
        self.diameter.push(input.diameter[index]);
        self.symbols.push(input.symbols[index]);
        self.x0.push(input.x0[index]);
        self.y0.push(input.y0[index]);
        self.x1.push(input.x1[index]);
        self.y1.push(input.y1[index]);
    }

    fn push_step(&mut self, stable_id: u64, style_ref: u32, x: f64, y: f64) {
        self.kinds.push(SceneRecordKind::Polyline as u8);
        self.stable_ids.push(stable_id);
        self.style_refs.push(style_ref);
        self.diameter.push(0.0);
        self.symbols.push(0);
        self.x0.push(x);
        self.y0.push(y);
        self.x1.push(0.0);
        self.y1.push(0.0);
    }

    fn push_ribbon_sample(
        &mut self,
        stable_id: u64,
        style_ref: u32,
        outline: u8,
        top: [f64; 2],
        base: [f64; 2],
    ) {
        self.kinds.push(SceneRecordKind::Band as u8);
        self.stable_ids.push(stable_id);
        self.style_refs.push(style_ref);
        self.diameter.push(0.0);
        self.symbols.push(outline);
        self.x0.push(top[0]);
        self.y0.push(top[1]);
        self.x1.push(base[0]);
        self.y1.push(base[1]);
    }

    fn push_hex_vertex(&mut self, stable_id: u64, style_ref: u32, x: f64, y: f64) {
        self.kinds.push(SceneRecordKind::PolyFill as u8);
        self.stable_ids.push(stable_id);
        self.style_refs.push(style_ref);
        self.diameter.push(0.0);
        self.symbols.push(0);
        self.x0.push(x);
        self.y0.push(y);
        self.x1.push(0.0);
        self.y1.push(0.0);
    }

    fn push_heatmap_cell(
        &mut self,
        stable_id: u64,
        style_ref: u32,
        x0: f64,
        y0: f64,
        x1: f64,
        y1: f64,
    ) {
        self.kinds.push(SceneRecordKind::Rect as u8);
        self.stable_ids.push(stable_id);
        self.style_refs.push(style_ref);
        self.diameter.push(0.0);
        self.symbols.push(0);
        self.x0.push(x0);
        self.y0.push(y0);
        self.x1.push(x1);
        self.y1.push(y1);
    }

    fn push_image(&mut self, stable_id: u64, style_ref: u32, x0: f64, y0: f64, x1: f64, y1: f64) {
        self.kinds.push(SceneRecordKind::Image as u8);
        self.stable_ids.push(stable_id);
        self.style_refs.push(style_ref);
        self.diameter.push(0.0);
        self.symbols.push(0);
        self.x0.push(x0);
        self.y0.push(y0);
        self.x1.push(x1);
        self.y1.push(y1);
    }
}

/// Expand compact step runs, two-row ribbon pairs, hex-cell centers,
/// heatmap lattices, disconnected endpoint pairs, and triangle faces into
/// canonical Scene records. Ribbon cubics are evaluated in axis-transformed
/// space, as required by the public ribbon contract; the inverse transform
/// produces values that the existing Scene encoder maps to those same
/// canonical pixels. Hex rings, heatmap cells, segments, and triangle faces
/// expand in data space so the encoder maps the same vertices the retired
/// host packers emitted.
pub fn expand_scene_records(
    input: SceneExpansionInput<'_>,
    x_scale: AxisScale,
    y_scale: AxisScale,
) -> Result<ExpandedSceneRecords, SceneError> {
    expand_scene_records_painted(input, x_scale, y_scale, &[], &[], &[], &[], false)
        .map(|(records, _styles, _images)| records)
}

/// Expand compact authoring, including ABI 134 painted heatmap lattices,
/// ABI 137 density image blits, and ABI 186 colormap hexbin HexCell fills.
/// When any `HeatmapPainted`, `DensityBlit`, or painted `HexCell` group is
/// present, `paint` must be a valid XYHP envelope. `polar` selects ABI 143
/// occupied-cell Rect tessellation instead of a Cartesian Image blit.
pub fn expand_scene_records_painted(
    input: SceneExpansionInput<'_>,
    x_scale: AxisScale,
    y_scale: AxisScale,
    fill_rgba: &[u8],
    stroke_rgba: &[u8],
    stroke_width: &[f64],
    paint: &[u8],
    polar: bool,
) -> Result<(ExpandedSceneRecords, Option<ExpandedSceneStyles>, Vec<SceneImage>), SceneError> {
    let len = input.kinds.len();
    if [
        input.stable_ids.len(),
        input.style_refs.len(),
        input.diameter.len(),
        input.symbols.len(),
        input.x0.len(),
        input.y0.len(),
        input.x1.len(),
        input.y1.len(),
        input.expansion_modes.len(),
    ]
    .into_iter()
    .any(|column_len| column_len != len)
    {
        return Err(SceneError::Length);
    }

    let mut has_painted = false;
    let mut has_density = false;
    let mut has_hex = false;
    for mode in input.expansion_modes {
        match SceneExpansionMode::from_code(*mode)? {
            SceneExpansionMode::HeatmapPainted => has_painted = true,
            SceneExpansionMode::DensityBlit => has_density = true,
            SceneExpansionMode::HexCell => has_hex = true,
            _ => {}
        }
    }
    let intern_density = has_density && polar;
    let intern_hex = has_hex && !paint.is_empty();
    if has_painted || intern_density || intern_hex {
        if fill_rgba.len() != stroke_width.len().saturating_mul(4)
            || stroke_rgba.len() != fill_rgba.len()
            || stroke_width.is_empty()
        {
            return Err(SceneError::Length);
        }
    } else if !has_density && !paint.is_empty() {
        return Err(SceneError::Length);
    }
    let mut paint_planes: Vec<Option<HeatmapPaintPlane<'_>>> = parse_heatmap_paint(paint)?
        .into_iter()
        .map(Some)
        .collect();
    if (has_painted || has_density) && paint_planes.is_empty() {
        return Err(SceneError::Length);
    }
    let mut painted_styles = (has_painted || intern_density || intern_hex).then(|| ExpandedSceneStyles {
        fill_rgba: fill_rgba.to_vec(),
        stroke_rgba: stroke_rgba.to_vec(),
        stroke_width: stroke_width.to_vec(),
    });
    let mut images = Vec::new();
    let mut hex_fills: HashMap<u64, Vec<[u8; 4]>> = HashMap::new();
    let mut hex_intern: HashMap<[u8; 4], u32> = HashMap::new();

    // Stable identity is the canonical Polyline run boundary. Reject any
    // attempt to switch step mode inside one contiguous same-kind identity
    // before a zero-mode prefix and stepped suffix could be emitted as one
    // path. Distinct kinds that reuse an identity (stem vertices then
    // stem-markers) stay separate expansion groups.
    let mut run_cursor = 0usize;
    while run_cursor < len {
        let run_end = scene_expansion_run_end(input.stable_ids, run_cursor);
        let mode = SceneExpansionMode::from_code(input.expansion_modes[run_cursor])?;
        let same_kind = input.kinds[run_cursor..run_end]
            .iter()
            .all(|kind| *kind == input.kinds[run_cursor]);
        if same_kind
            && input.expansion_modes[run_cursor..run_end]
                .iter()
                .any(|candidate| SceneExpansionMode::from_code(*candidate) != Ok(mode))
        {
            return Err(SceneError::Length);
        }
        run_cursor = run_end;
    }

    let mut expanded_len = 0usize;
    let mut cursor = 0usize;
    while cursor < len {
        let mode = SceneExpansionMode::from_code(input.expansion_modes[cursor])?;
        if mode == SceneExpansionMode::None {
            expanded_len = expanded_len.checked_add(1).ok_or(SceneError::Limit)?;
            cursor += 1;
            continue;
        }
        let style_ref = input.style_refs[cursor];
        let run_end =
            scene_expansion_group_end(input.stable_ids, input.kinds, input.expansion_modes, cursor);
        let band_step = matches!(
            mode,
            SceneExpansionMode::Pre | SceneExpansionMode::Mid | SceneExpansionMode::Post
        ) && input.kinds[cursor] == SceneRecordKind::Band as u8;
        let expected_kind = if band_step {
            SceneRecordKind::Band as u8
        } else {
            mode.expected_kind().expect("nonzero expansion mode")
        };
        for index in cursor..run_end {
            if input.kinds[index] != expected_kind
                || input.style_refs[index] != style_ref
                || SceneExpansionMode::from_code(input.expansion_modes[index])? != mode
                || (!mode.allows_nonzero_diameter() && input.diameter[index] != 0.0)
                || (!matches!(
                    mode,
                    SceneExpansionMode::Ribbon | SceneExpansionMode::BandFlatten
                ) && !band_step
                    && input.symbols[index] != 0)
            {
                return Err(SceneError::Length);
            }
            if !input.x0[index].is_finite()
                || !input.y0[index].is_finite()
                || !input.x1[index].is_finite()
                || !input.y1[index].is_finite()
            {
                return Err(SceneError::NonFinite);
            }
            if matches!(
                mode,
                SceneExpansionMode::Pre
                    | SceneExpansionMode::Mid
                    | SceneExpansionMode::Post
                    | SceneExpansionMode::CurveFlatten
            ) && !band_step
                && (input.x1[index] != 0.0 || input.y1[index] != 0.0)
            {
                return Err(SceneError::Length);
            }
            if (mode == SceneExpansionMode::BandFlatten || band_step)
                && (input.symbols[index] != input.symbols[cursor]
                    || input.x0[index] != input.x1[index]
                    || BandOutline::from_code(input.symbols[index]).is_err())
            {
                return Err(SceneError::Length);
            }
            if mode == SceneExpansionMode::HexCell
                && (input.x1[index] <= 0.0 || input.y1[index] <= 0.0)
            {
                return Err(SceneError::Length);
            }
        }
        let run_len = run_end - cursor;
        let required = match mode {
            SceneExpansionMode::None => unreachable!(),
            SceneExpansionMode::Pre | SceneExpansionMode::Post => run_len
                .checked_mul(2)
                .and_then(|value| value.checked_sub(1))
                .ok_or(SceneError::Limit)?,
            SceneExpansionMode::Mid => run_len
                .checked_mul(3)
                .and_then(|value| value.checked_sub(2))
                .ok_or(SceneError::Limit)?,
            SceneExpansionMode::Ribbon => {
                if run_len != 2
                    || input.symbols[cursor] != input.symbols[cursor + 1]
                    || BandOutline::from_code(input.symbols[cursor]).is_err()
                    || input.x0[cursor] != input.x0[cursor + 1]
                    || input.x1[cursor] != input.x1[cursor + 1]
                {
                    return Err(SceneError::Length);
                }
                SCENE_RIBBON_STEPS + 1
            }
            SceneExpansionMode::HexCell => {
                if run_len != 1 {
                    return Err(SceneError::Length);
                }
                SCENE_HEXBIN_RING.len()
            }
            SceneExpansionMode::HeatmapLattice => {
                if run_len != 2 {
                    return Err(SceneError::Length);
                }
                let (rows, cols, _, _, _, _) = heatmap_lattice_extent(&input, cursor)?;
                rows.checked_mul(cols).ok_or(SceneError::Limit)?
            }
            SceneExpansionMode::HeatmapPainted => {
                if run_len != 2 {
                    return Err(SceneError::Length);
                }
                let (rows, cols, _, _, _, _) = heatmap_lattice_extent(&input, cursor)?;
                let plane = paint_planes
                    .iter()
                    .flatten()
                    .find(|plane| plane.stable_id == input.stable_ids[cursor])
                    .ok_or(SceneError::Length)?;
                if plane.rows != rows || plane.cols != cols {
                    return Err(SceneError::Length);
                }
                let style_index = input.style_refs[cursor] as usize;
                if style_index >= stroke_width.len() {
                    return Err(SceneError::Length);
                }
                rows.checked_mul(cols).ok_or(SceneError::Limit)?
            }
            SceneExpansionMode::DensityBlit => {
                if run_len != 2 {
                    return Err(SceneError::Length);
                }
                let (rows, cols, _, _, _, _) = heatmap_lattice_extent(&input, cursor)?;
                let plane = paint_planes
                    .iter()
                    .flatten()
                    .find(|plane| plane.stable_id == input.stable_ids[cursor])
                    .ok_or(SceneError::Length)?;
                if !density_blit_plane(plane, rows, cols) {
                    return Err(SceneError::Length);
                }
                if polar {
                    let image = density_image_from_plane(*plane)?;
                    density_occupied_cells(&image.rgba)
                } else {
                    1
                }
            }
            SceneExpansionMode::SegmentPair => {
                if run_len != 1 {
                    return Err(SceneError::Length);
                }
                2
            }
            SceneExpansionMode::TriangleFace => {
                if run_len != 2 || input.x1[cursor + 1] != 0.0 || input.y1[cursor + 1] != 0.0 {
                    return Err(SceneError::Length);
                }
                3
            }
            SceneExpansionMode::CurveFlatten | SceneExpansionMode::BandFlatten => {
                curve_flatten_required(&input.x0[cursor..run_end])?
            }
        };
        expanded_len = expanded_len
            .checked_add(required)
            .ok_or(SceneError::Limit)?;
        cursor = run_end;
    }
    if expanded_len > MAX_SCENE_MARKS {
        return Err(SceneError::Limit);
    }

    let mut output = ExpandedSceneRecords::with_capacity(expanded_len);
    cursor = 0;
    while cursor < len {
        let mode = SceneExpansionMode::from_code(input.expansion_modes[cursor])?;
        if mode == SceneExpansionMode::None {
            output.push_source(&input, cursor);
            cursor += 1;
            continue;
        }
        let stable_id = input.stable_ids[cursor];
        let style_ref = input.style_refs[cursor];
        let run_end =
            scene_expansion_group_end(input.stable_ids, input.kinds, input.expansion_modes, cursor);
        if mode == SceneExpansionMode::Ribbon {
            let upper = cursor;
            let lower = cursor + 1;
            let cx0 = x_scale.coord(input.x0[upper]);
            let cx1 = x_scale.coord(input.x1[upper]);
            let upper_y0 = y_scale.coord(input.y0[upper]);
            let upper_y1 = y_scale.coord(input.y1[upper]);
            let lower_y0 = y_scale.coord(input.y0[lower]);
            let lower_y1 = y_scale.coord(input.y1[lower]);
            if [cx0, cx1, upper_y0, upper_y1, lower_y0, lower_y1]
                .into_iter()
                .any(|value| !value.is_finite())
            {
                return Err(SceneError::NonFinite);
            }
            let midpoint = (cx0 + cx1) * 0.5;
            if !midpoint.is_finite() {
                return Err(SceneError::NonFinite);
            }
            for sample in 0..=SCENE_RIBBON_STEPS {
                let t = sample as f64 / SCENE_RIBBON_STEPS as f64;
                let x_coord = geom::cubic_bezier(t, cx0, midpoint, midpoint, cx1);
                let top_y_coord = geom::cubic_bezier(t, upper_y0, upper_y0, upper_y1, upper_y1);
                let base_y_coord = geom::cubic_bezier(t, lower_y0, lower_y0, lower_y1, lower_y1);
                let top = [x_scale.value(x_coord), y_scale.value(top_y_coord)];
                let base = [x_scale.value(x_coord), y_scale.value(base_y_coord)];
                if top.into_iter().chain(base).any(|value| !value.is_finite()) {
                    return Err(SceneError::NonFinite);
                }
                output.push_ribbon_sample(stable_id, style_ref, input.symbols[upper], top, base);
            }
            cursor = run_end;
            continue;
        }
        if mode == SceneExpansionMode::HexCell {
            let cx = input.x0[cursor];
            let cy = input.y0[cursor];
            let dx = input.x1[cursor];
            let dy = input.y1[cursor];
            let mut cell_style = style_ref;
            if intern_hex {
                let parent = stable_id >> 32;
                let cell_index = (stable_id & 0xffff_ffff) as usize;
                if let Entry::Vacant(slot) = hex_fills.entry(parent) {
                    if let Ok(plane) = take_paint_plane(&mut paint_planes, parent) {
                        let alpha = style_rgba4(fill_rgba, style_ref)?[3];
                        slot.insert(heatmap_paint_fills(plane, alpha)?);
                    }
                }
                if let Some(fills) = hex_fills.get(&parent) {
                    let fill = *fills.get(cell_index).ok_or(SceneError::Length)?;
                    cell_style = intern_heatmap_fill(
                        painted_styles.as_mut().ok_or(SceneError::Length)?,
                        &mut hex_intern,
                        fill,
                        style_rgba4(stroke_rgba, style_ref)?,
                        *stroke_width
                            .get(style_ref as usize)
                            .ok_or(SceneError::Length)?,
                    )?;
                }
            }
            for (rx, ry) in SCENE_HEXBIN_RING {
                output.push_hex_vertex(stable_id, cell_style, cx + rx * dx, cy + ry * dy);
            }
            cursor = run_end;
            continue;
        }
        if mode == SceneExpansionMode::DensityBlit {
            let (rows, cols, x0, y0, x1, y1) = heatmap_lattice_extent(&input, cursor)?;
            let plane = take_paint_plane(&mut paint_planes, stable_id)?;
            if !density_blit_plane(&plane, rows, cols) {
                return Err(SceneError::Length);
            }
            if polar {
                let dx = (x1 - x0) / cols as f64;
                let dy = (y1 - y0) / rows as f64;
                if !dx.is_finite() || !dy.is_finite() {
                    return Err(SceneError::NonFinite);
                }
                let image = density_image_from_plane(plane)?;
                let mut intern: HashMap<[u8; 4], u32> = HashMap::new();
                push_polar_density_cells(
                    &mut output,
                    painted_styles.as_mut().ok_or(SceneError::Length)?,
                    &mut intern,
                    stable_id,
                    &image,
                    rows,
                    cols,
                    x0,
                    y0,
                    dx,
                    dy,
                )?;
            } else {
                images.push(density_image_from_plane(plane)?);
                output.push_image(stable_id, style_ref, x0, y0, x1, y1);
            }
            cursor = run_end;
            continue;
        }
        if mode == SceneExpansionMode::HeatmapLattice
            || mode == SceneExpansionMode::HeatmapPainted
        {
            let (rows, cols, x0, y0, x1, y1) = heatmap_lattice_extent(&input, cursor)?;
            let dx = (x1 - x0) / cols as f64;
            let dy = (y1 - y0) / rows as f64;
            if !dx.is_finite() || !dy.is_finite() {
                return Err(SceneError::NonFinite);
            }
            let fills = if mode == SceneExpansionMode::HeatmapPainted {
                let plane = take_paint_plane(&mut paint_planes, stable_id)?;
                if plane.rows != rows || plane.cols != cols {
                    return Err(SceneError::Length);
                }
                Some(heatmap_paint_fills(plane, style_rgba4(fill_rgba, style_ref)?[3])?)
            } else {
                None
            };
            let painted = fills.as_ref().map(|values| (values, stroke_rgba, stroke_width));
            let mut intern: HashMap<[u8; 4], u32> = HashMap::new();
            for row in 0..rows {
                for col in 0..cols {
                    let cell_style = if let Some((fills, stroke_table, widths)) = painted {
                        intern_heatmap_fill(
                            painted_styles.as_mut().ok_or(SceneError::Length)?,
                            &mut intern,
                            fills[row * cols + col],
                            style_rgba4(stroke_table, style_ref)?,
                            *widths.get(style_ref as usize).ok_or(SceneError::Length)?,
                        )?
                    } else {
                        style_ref
                    };
                    output.push_heatmap_cell(
                        stable_id,
                        cell_style,
                        x0 + col as f64 * dx,
                        y0 + row as f64 * dy,
                        x0 + (col + 1) as f64 * dx,
                        y0 + (row + 1) as f64 * dy,
                    );
                }
            }
            cursor = run_end;
            continue;
        }
        if mode == SceneExpansionMode::SegmentPair {
            output.push_step(stable_id, style_ref, input.x0[cursor], input.y0[cursor]);
            output.push_step(stable_id, style_ref, input.x1[cursor], input.y1[cursor]);
            cursor = run_end;
            continue;
        }
        if mode == SceneExpansionMode::TriangleFace {
            output.push_hex_vertex(stable_id, style_ref, input.x0[cursor], input.y0[cursor]);
            output.push_hex_vertex(stable_id, style_ref, input.x1[cursor], input.y1[cursor]);
            output.push_hex_vertex(
                stable_id,
                style_ref,
                input.x0[cursor + 1],
                input.y0[cursor + 1],
            );
            cursor = run_end;
            continue;
        }
        if mode == SceneExpansionMode::CurveFlatten {
            let compact_x = &input.x0[cursor..run_end];
            let compact_y = &input.y0[cursor..run_end];
            if compact_x.len() < 3 {
                for index in cursor..run_end {
                    output.push_step(stable_id, style_ref, input.x0[index], input.y0[index]);
                }
                cursor = run_end;
                continue;
            }
            let required = curve_flatten_required(compact_x)?;
            let mut flat_x = vec![0.0; required];
            let mut flat_y = vec![0.0; required];
            let written = geom::curve_flatten(
                compact_x,
                compact_y,
                SCENE_CURVE_STEPS,
                &mut flat_x,
                &mut flat_y,
            )
            .ok_or(SceneError::Length)?;
            if written != required {
                return Err(SceneError::Length);
            }
            for index in 0..written {
                if !flat_x[index].is_finite() || !flat_y[index].is_finite() {
                    return Err(SceneError::NonFinite);
                }
                output.push_step(stable_id, style_ref, flat_x[index], flat_y[index]);
            }
            cursor = run_end;
            continue;
        }
        if mode == SceneExpansionMode::BandFlatten {
            let compact_x = &input.x0[cursor..run_end];
            let compact_top = &input.y0[cursor..run_end];
            let compact_base = &input.y1[cursor..run_end];
            let outline = input.symbols[cursor];
            if compact_x.len() < 3 {
                for index in cursor..run_end {
                    output.push_source(&input, index);
                }
                cursor = run_end;
                continue;
            }
            let required = curve_flatten_required(compact_x)?;
            let mut flat_x = vec![0.0; required];
            let mut flat_top = vec![0.0; required];
            let mut flat_base = vec![0.0; required];
            let written_top = geom::curve_flatten(
                compact_x,
                compact_top,
                SCENE_CURVE_STEPS,
                &mut flat_x,
                &mut flat_top,
            )
            .ok_or(SceneError::Length)?;
            let mut unused_x = vec![0.0; required];
            let written_base = geom::curve_flatten(
                compact_x,
                compact_base,
                SCENE_CURVE_STEPS,
                &mut unused_x,
                &mut flat_base,
            )
            .ok_or(SceneError::Length)?;
            if written_top != required || written_base != required {
                return Err(SceneError::Length);
            }
            for index in 0..written_top {
                if !flat_x[index].is_finite()
                    || !flat_top[index].is_finite()
                    || !flat_base[index].is_finite()
                {
                    return Err(SceneError::NonFinite);
                }
                output.push_ribbon_sample(
                    stable_id,
                    style_ref,
                    outline,
                    [flat_x[index], flat_top[index]],
                    [flat_x[index], flat_base[index]],
                );
            }
            cursor = run_end;
            continue;
        }
        if matches!(
            mode,
            SceneExpansionMode::Pre | SceneExpansionMode::Mid | SceneExpansionMode::Post
        ) && input.kinds[cursor] == SceneRecordKind::Band as u8
        {
            let outline = input.symbols[cursor];
            output.push_ribbon_sample(
                stable_id,
                style_ref,
                outline,
                [input.x0[cursor], input.y0[cursor]],
                [input.x1[cursor], input.y1[cursor]],
            );
            for index in cursor + 1..run_end {
                let previous = index - 1;
                let previous_x = input.x0[previous];
                let previous_top = input.y0[previous];
                let previous_base = input.y1[previous];
                let current_x = input.x0[index];
                let current_top = input.y0[index];
                let current_base = input.y1[index];
                match mode {
                    SceneExpansionMode::Pre => {
                        output.push_ribbon_sample(
                            stable_id,
                            style_ref,
                            outline,
                            [previous_x, current_top],
                            [previous_x, current_base],
                        );
                        output.push_ribbon_sample(
                            stable_id,
                            style_ref,
                            outline,
                            [current_x, current_top],
                            [current_x, current_base],
                        );
                    }
                    SceneExpansionMode::Mid => {
                        let midpoint = (previous_x + current_x) * 0.5;
                        if !midpoint.is_finite() {
                            return Err(SceneError::NonFinite);
                        }
                        output.push_ribbon_sample(
                            stable_id,
                            style_ref,
                            outline,
                            [midpoint, previous_top],
                            [midpoint, previous_base],
                        );
                        output.push_ribbon_sample(
                            stable_id,
                            style_ref,
                            outline,
                            [midpoint, current_top],
                            [midpoint, current_base],
                        );
                        output.push_ribbon_sample(
                            stable_id,
                            style_ref,
                            outline,
                            [current_x, current_top],
                            [current_x, current_base],
                        );
                    }
                    SceneExpansionMode::Post => {
                        output.push_ribbon_sample(
                            stable_id,
                            style_ref,
                            outline,
                            [current_x, previous_top],
                            [current_x, previous_base],
                        );
                        output.push_ribbon_sample(
                            stable_id,
                            style_ref,
                            outline,
                            [current_x, current_top],
                            [current_x, current_base],
                        );
                    }
                    SceneExpansionMode::None
                    | SceneExpansionMode::Ribbon
                    | SceneExpansionMode::HexCell
                    | SceneExpansionMode::HeatmapLattice
                    | SceneExpansionMode::HeatmapPainted
                    | SceneExpansionMode::DensityBlit
                    | SceneExpansionMode::SegmentPair
                    | SceneExpansionMode::TriangleFace
                    | SceneExpansionMode::CurveFlatten
                    | SceneExpansionMode::BandFlatten => unreachable!(),
                }
            }
            cursor = run_end;
            continue;
        }
        output.push_step(stable_id, style_ref, input.x0[cursor], input.y0[cursor]);
        for index in cursor + 1..run_end {
            let previous = index - 1;
            let previous_x = input.x0[previous];
            let previous_y = input.y0[previous];
            let current_x = input.x0[index];
            let current_y = input.y0[index];
            match mode {
                SceneExpansionMode::Pre => {
                    output.push_step(stable_id, style_ref, previous_x, current_y);
                    output.push_step(stable_id, style_ref, current_x, current_y);
                }
                SceneExpansionMode::Mid => {
                    // Preserve the historical host contract exactly. If this
                    // addition overflows, reject rather than emitting infinity.
                    let midpoint = (previous_x + current_x) * 0.5;
                    if !midpoint.is_finite() {
                        return Err(SceneError::NonFinite);
                    }
                    output.push_step(stable_id, style_ref, midpoint, previous_y);
                    output.push_step(stable_id, style_ref, midpoint, current_y);
                    output.push_step(stable_id, style_ref, current_x, current_y);
                }
                SceneExpansionMode::Post => {
                    output.push_step(stable_id, style_ref, current_x, previous_y);
                    output.push_step(stable_id, style_ref, current_x, current_y);
                }
                SceneExpansionMode::None
                | SceneExpansionMode::Ribbon
                | SceneExpansionMode::HexCell
                | SceneExpansionMode::HeatmapLattice
                | SceneExpansionMode::HeatmapPainted
                | SceneExpansionMode::DensityBlit
                | SceneExpansionMode::SegmentPair
                | SceneExpansionMode::TriangleFace
                | SceneExpansionMode::CurveFlatten
                | SceneExpansionMode::BandFlatten => unreachable!(),
            }
        }
        cursor = run_end;
    }
    if paint_planes.iter().any(Option::is_some) {
        return Err(SceneError::Length);
    }
    debug_assert_eq!(output.kinds.len(), expanded_len);
    Ok((output, painted_styles, images))
}

/// Cartesian bar/column/histogram/heatmap/violin/box corner radii and polar `wedge_gap` /
/// `corner_radius` in pixels (ABI 166 / ABI 167 / ABI 168 / ABI 173 / ABI 174). `force_tip_top`
/// matches compatibility horizontal bars (`tip_top or horizontal`). Polar
/// Rects apply `wedge_gap` and, when inner radius is positive, `r_tip.max(r_base)`.
#[derive(Clone, Copy, Debug, PartialEq)]
pub struct SceneCornerRadius {
    pub r_tip: f64,
    pub r_base: f64,
    pub force_tip_top: bool,
    pub wedge_gap: f64,
}

fn tessellate_rounded_rect_record(
    out: &mut Vec<PreparedMarkRecord>,
    mapped: [f64; 4],
    radius: SceneCornerRadius,
    annotation_tag: u8,
    style_ref: u32,
    stable_id: u64,
    symbol: u8,
) -> bool {
    let x = mapped[0].min(mapped[2]);
    let y = mapped[1].min(mapped[3]);
    let w = (mapped[2] - mapped[0]).abs();
    let h = (mapped[3] - mapped[1]).abs();
    if !x.is_finite() || !y.is_finite() || !w.is_finite() || !h.is_finite() || w <= 0.0 || h <= 0.0
    {
        return false;
    }
    let half_w = w * 0.5;
    let half_h = h * 0.5;
    let r_tip = radius.r_tip.min(half_w).min(half_h);
    let r_base = radius.r_base.min(half_w).min(half_h);
    if r_tip <= 0.0 && r_base <= 0.0 {
        return false;
    }
    let tip_top = radius.force_tip_top || mapped[3] <= mapped[1];
    let mut xs = [0.0; 20];
    let mut ys = [0.0; 20];
    let Some(written) =
        geom::rounded_rect_poly(x, y, w, h, r_tip, r_base, tip_top, &mut xs, &mut ys)
    else {
        return false;
    };
    if written < 3 || out.len().saturating_add(written) > MAX_SCENE_MARKS {
        return false;
    }
    for index in 0..written {
        let px = xs[index];
        let py = ys[index];
        let visible = px.is_finite() && py.is_finite();
        out.push(PreparedMarkRecord {
            kind: SceneRecordKind::PolyFill,
            visible,
            symbol,
            annotation_tag,
            style_ref,
            stable_id,
            coordinates: if visible {
                [px, py, 0.0, 0.0]
            } else {
                [0.0; 4]
            },
            diameter: 0.0,
        });
    }
    true
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
    label_backgrounds: Vec<Option<SceneLabelBox>>,
    arrows: Vec<StraightArrow>,
    callouts: Vec<CartesianCallout>,
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
    polar: Option<PolarSceneState>,
    images: Vec<SceneImage>,
    dashes: Vec<u8>,
    marker_paths: Vec<Option<AuthoredMarkerPath>>,
    corner_radii: Vec<Option<SceneCornerRadius>>,
}

#[derive(Clone, Debug)]
struct PolarSceneState {
    metrics: [f64; POLAR_METRICS_LEN],
    grid_shape: u8,
    xypl: Vec<u8>,
    legend_box: Option<[f64; 4]>,
}

impl PolarSceneState {
    fn from_xypl(bytes: &[u8], layout: PlotLayout) -> Result<Self, SceneError> {
        let mut metrics = [0.0; POLAR_METRICS_LEN];
        let envelope = polar::layout_from_xypl(
            bytes,
            layout.left,
            layout.top,
            layout.right - layout.left,
            layout.bottom - layout.top,
            &mut metrics,
        )
        .ok_or(SceneError::Length)?;
        Ok(Self {
            metrics,
            grid_shape: envelope.grid_shape,
            xypl: bytes.to_vec(),
            legend_box: None,
        })
    }

    fn project(&self, theta: f64, r: f64) -> Option<(f64, f64)> {
        polar::polar_project_one(&self.metrics, theta, r)
    }

    fn visible(&self, theta: f64, r: f64) -> bool {
        polar::polar_point_visible(&self.metrics, theta, r)
    }

    fn cx(&self) -> f64 {
        self.metrics[polar::METRIC_CX]
    }

    fn cy(&self) -> f64 {
        self.metrics[polar::METRIC_CY]
    }

    fn radius(&self) -> f64 {
        self.metrics[polar::METRIC_RADIUS]
    }

    fn hole(&self) -> f64 {
        self.metrics[polar::METRIC_HOLE]
    }

    fn full_sector(&self) -> bool {
        self.metrics[polar::METRIC_FULL_SECTOR] >= 0.5
    }

    fn sector_a0(&self) -> f64 {
        self.metrics[polar::METRIC_SECTOR_A0]
    }

    fn sector_a1(&self) -> f64 {
        self.metrics[polar::METRIC_SECTOR_A1]
    }

    fn r_lo(&self) -> f64 {
        self.metrics[polar::METRIC_R_LO]
    }

    fn r_hi(&self) -> f64 {
        self.metrics[polar::METRIC_R_HI]
    }

    fn inner_radius(&self) -> f64 {
        let rn = polar::polar_project_one(
            &self.metrics,
            self.metrics[polar::METRIC_SECTOR_START],
            self.r_lo(),
        )
        .map(|(x, y)| (x - self.cx()).hypot(y - self.cy()))
        .unwrap_or(self.hole() * self.radius());
        rn.max(0.0)
    }

    fn radius_px(&self, r: f64) -> f64 {
        polar::polar_project_one(&self.metrics, self.metrics[polar::METRIC_SECTOR_START], r)
            .map(|(x, y)| (x - self.cx()).hypot(y - self.cy()))
            .unwrap_or(0.0)
    }

    fn ring_points(&self, r: f64, steps: usize) -> Vec<(f64, f64)> {
        let rn = self.radius_px(r);
        if rn <= 0.0 {
            return Vec::new();
        }
        let n = steps.max(2);
        let count = if self.full_sector() { n } else { n + 1 };
        let a0 = self.sector_a0();
        let span = self.sector_a1() - a0;
        (0..count)
            .map(|i| {
                let a = a0 + span * i as f64 / n as f64;
                (self.cx() + rn * a.cos(), self.cy() - rn * a.sin())
            })
            .collect()
    }

    fn polygon_ring(&self, r: f64, thetas: &[f64]) -> Vec<(f64, f64)> {
        thetas
            .iter()
            .filter_map(|theta| self.project(*theta, r))
            .collect()
    }

    fn spoke_ends(&self, theta: f64) -> Option<((f64, f64), (f64, f64))> {
        let inner = self.project(theta, self.r_lo())?;
        let outer = self.project(theta, self.r_hi())?;
        Some((inner, outer))
    }
}

impl<'a> SceneBatch<'a> {
    /// Attach bounded authored decorations before canonical Scene encoding.
    pub fn with_authored_annotations(mut self, bytes: &[u8]) -> Result<Self, SceneError> {
        if bytes.is_empty() {
            return Ok(self);
        }
        if self.polar.is_some() {
            return Err(SceneError::Length);
        }
        if bytes.len() < 20 || &bytes[..4] != b"XYAD" {
            return Err(SceneError::Length);
        }
        let version = batch_u32(bytes, 4)?;
        if !(1..=3).contains(&version) {
            return Err(SceneError::Length);
        }
        let xyat_len = batch_u32(bytes, 8)? as usize;
        let xyal_len = batch_u32(bytes, 12)? as usize;
        let xyar_len = batch_u32(bytes, 16)? as usize;
        let xyac_len = if version == 1 {
            0
        } else {
            if bytes.len() < 24 {
                return Err(SceneError::Length);
            }
            batch_u32(bytes, 20)? as usize
        };
        let xyaw_len = if version == 3 {
            if bytes.len() < 28 {
                return Err(SceneError::Length);
            }
            batch_u32(bytes, 24)? as usize
        } else {
            0
        };
        let start: usize = if version == 1 {
            20
        } else if version == 2 {
            24
        } else {
            28
        };
        let xyat_end = start.checked_add(xyat_len).ok_or(SceneError::Limit)?;
        let xyal_end = xyat_end.checked_add(xyal_len).ok_or(SceneError::Limit)?;
        let xyar_end = xyal_end.checked_add(xyar_len).ok_or(SceneError::Limit)?;
        let xyac_end = xyar_end.checked_add(xyac_len).ok_or(SceneError::Limit)?;
        let end = xyac_end.checked_add(xyaw_len).ok_or(SceneError::Limit)?;
        if end != bytes.len() {
            return Err(SceneError::Length);
        }
        let (mut labels, mut label_backgrounds) = decode_xyat(
            &bytes[start..xyat_end],
            self.x_scale,
            self.y_scale,
            self.layout,
        )?;
        let attached = &bytes[xyat_end..xyal_end];
        if !attached.is_empty() {
            for (index, (stable_id, rgba, background, border, text)) in
                decode_xyal_rows(attached)?.into_iter().enumerate()
            {
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
                let label = SceneLabel {
                    stable_id: 0x5859_0500_0000_0000 | index as u64,
                    x,
                    y,
                    font_size: 12.0,
                    rgba,
                    anchor: 0,
                    text,
                };
                label_backgrounds.push(match background {
                    Some(fill) => resolved_callout_label_background(
                        label.x,
                        label.y,
                        label.font_size,
                        label.anchor,
                        &label.text,
                        fill,
                        border,
                        self.layout,
                    )?,
                    None => None,
                });
                labels.push(label);
            }
        }
        if labels.len() > MAX_SCENE_LABELS {
            return Err(SceneError::Limit);
        }
        if labels.iter().try_fold(0usize, |total, label| {
            total.checked_add(label.text.len()).ok_or(SceneError::Limit)
        })? > MAX_SCENE_LABEL_TEXT_BYTES
        {
            return Err(SceneError::Limit);
        }
        for (index, label) in labels.iter_mut().enumerate() {
            if label.stable_id >> 40 == 0x0058_5904 {
                label.stable_id = 0x5859_0400_0000_0000 | index as u64;
            }
        }
        self.labels = labels;
        self.label_backgrounds = label_backgrounds;
        let arrows = decode_xyar(&bytes[xyal_end..xyar_end])?;
        if self
            .stroke_width
            .len()
            .checked_add(arrows.len())
            .ok_or(SceneError::Limit)?
            > MAX_SCENE_STYLES
            || self
                .kinds
                .len()
                .checked_add(arrows.len().checked_mul(5).ok_or(SceneError::Limit)?)
                .ok_or(SceneError::Limit)?
                > MAX_SCENE_MARKS
            || arrows.iter().any(|arrow| {
                self.stable_ids.contains(&arrow.stable_id)
                    || !self.x_scale.pixel(arrow.x0).is_finite()
                    || !self.y_scale.pixel(arrow.y0).is_finite()
                    || !self.x_scale.pixel(arrow.x1).is_finite()
                    || !self.y_scale.pixel(arrow.y1).is_finite()
                    || straight_arrow_points(
                        self.x_scale.pixel(arrow.x0),
                        self.y_scale.pixel(arrow.y0),
                        self.x_scale.pixel(arrow.x1),
                        self.y_scale.pixel(arrow.y1),
                    )
                    .is_err()
            })
        {
            return Err(SceneError::Length);
        }
        self.arrows = arrows;
        let mut callouts = decode_xyac(
            &bytes[xyar_end..xyac_end],
            self.x_scale,
            self.y_scale,
            self.layout,
        )?;
        let callout_records = callouts.len().checked_mul(5).ok_or(SceneError::Limit)?;
        let total_styles = self
            .stroke_width
            .len()
            .checked_add(self.arrows.len())
            .and_then(|value| value.checked_add(callouts.len()))
            .ok_or(SceneError::Limit)?;
        let total_records = self
            .kinds
            .len()
            .checked_add(self.arrows.len().checked_mul(5).ok_or(SceneError::Limit)?)
            .and_then(|value| value.checked_add(callout_records))
            .ok_or(SceneError::Limit)?;
        if total_styles > MAX_SCENE_STYLES
            || total_records > MAX_SCENE_MARKS
            || self
                .labels
                .len()
                .checked_add(callouts.len())
                .ok_or(SceneError::Limit)?
                > MAX_SCENE_LABELS
        {
            return Err(SceneError::Limit);
        }
        // Callout labels are carried by `callouts` until encoding, where their
        // resolved backgrounds are emitted in the matching XYLB entries.  Do
        // not also append them to `self.labels`: that would duplicate labels
        // and lose the background on the first copy during a Scene round trip.
        let (mut wrapped, mut wrapped_backgrounds, mut wrapped_callouts) = decode_xyaw(
            &bytes[xyac_end..end],
            self.x_scale,
            self.y_scale,
            self.layout,
        )?;
        self.labels.append(&mut wrapped);
        self.label_backgrounds.append(&mut wrapped_backgrounds);
        callouts.append(&mut wrapped_callouts);
        self.callouts = callouts;
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
        encode_scene_labels(&labels, &vec![None; labels.len()])?;
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
            resolved_legend_bounds(layout, value, None)?;
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
            if style_refs[index] as usize >= style_count {
                return Err(SceneError::Length);
            }
            match kind {
                SceneRecordKind::Scatter => {
                    if symbols[index] > ScatterSymbol::VerticalLine as u8 {
                        return Err(SceneError::Length);
                    }
                }
                SceneRecordKind::Band => {
                    BandOutline::from_code(symbols[index])?;
                    if diameter[index] != 0.0 {
                        return Err(SceneError::Length);
                    }
                }
                _ if diameter[index] != 0.0 || symbols[index] != 0 => {
                    return Err(SceneError::Length);
                }
                _ => {}
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
                    Ok(SceneRecordKind::Rect | SceneRecordKind::Band | SceneRecordKind::Image)
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
            label_backgrounds: vec![None; labels.len()],
            labels,
            arrows: Vec::new(),
            callouts: Vec::new(),
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
            polar: None,
            images: Vec::new(),
            dashes: Vec::new(),
            marker_paths: Vec::new(),
            corner_radii: Vec::new(),
        })
    }

    /// Attach decoded density/image blit planes. Empty keeps the Scene without
    /// Image records. Polar scenes reject image blits.
    pub fn with_images(mut self, images: Vec<SceneImage>) -> Result<Self, SceneError> {
        if images.is_empty() {
            return Ok(self);
        }
        if self.polar.is_some() {
            return Err(SceneError::Length);
        }
        self.images = images;
        Ok(self)
    }

    /// Attach a host-packed XYDS/XYLC/XYMP/XYGR/XYMG style sidecar. Empty keeps every
    /// style solid, round-capped, built-in-symbol, ungraded, and disc-marked. Style refs
    /// address the host style table before arrow/callout extras. XYMP is
    /// consumed at encode (tessellate scatter) and stripped from the encoded
    /// sidecar; XYGR and XYMG are kept so SVG/raster can paint linear-gradient
    /// fills and glyph markers.
    pub fn with_dashes(mut self, bytes: &[u8]) -> Result<Self, SceneError> {
        if bytes.is_empty() {
            return Ok(self);
        }
        let (dash, cap, markers, grads, glyphs) = split_style_sidecars(bytes)?;
        let dash_entries = parse_xyds(dash)?;
        let cap_entries = parse_xylc(cap)?;
        let marker_entries = parse_xymp(markers)?;
        let gradient_entries = parse_xygr(grads)?;
        let glyph_entries = parse_xymg(glyphs)?;
        let style_count = self.stroke_width.len();
        if dash_entries
            .iter()
            .any(|entry| entry.style_ref as usize >= style_count)
            || cap_entries
                .iter()
                .any(|entry| entry.style_ref as usize >= style_count)
            || marker_entries
                .iter()
                .any(|entry| entry.style_ref as usize >= style_count)
            || gradient_entries
                .iter()
                .any(|entry| entry.style_ref as usize >= style_count)
            || glyph_entries
                .iter()
                .any(|entry| entry.style_ref as usize >= style_count)
        {
            return Err(SceneError::Length);
        }
        let mut kept = Vec::with_capacity(dash.len() + cap.len() + grads.len() + glyphs.len());
        kept.extend_from_slice(dash);
        kept.extend_from_slice(cap);
        kept.extend_from_slice(grads);
        kept.extend_from_slice(glyphs);
        self.dashes = kept;
        let mut paths = vec![None; style_count];
        for entry in marker_entries {
            paths[entry.style_ref as usize] = Some(entry.path);
        }
        self.marker_paths = paths;
        Ok(self)
    }

    /// Attach per-style cartesian `corner_radius` and polar `wedge_gap` /
    /// `corner_radius` in pixels. Empty keeps every cartesian Rect axis-aligned
    /// and every polar wedge ungapped and unrounded. Encoded Scene does not
    /// keep a radius sidecar: rounded bars become PolyFill vertices after
    /// pixel mapping; gapped or rounded polar wedges tessellate during
    /// `polar_wedge_points`.
    pub fn with_corner_radii(
        mut self,
        radii: Vec<Option<SceneCornerRadius>>,
    ) -> Result<Self, SceneError> {
        if radii.is_empty() {
            return Ok(self);
        }
        let style_count = self.stroke_width.len();
        if radii.len() > style_count {
            return Err(SceneError::Length);
        }
        let mut table = vec![None; style_count];
        for (index, radius) in radii.into_iter().enumerate() {
            if let Some(radius) = radius {
                if !radius.r_tip.is_finite()
                    || !radius.r_base.is_finite()
                    || !radius.wedge_gap.is_finite()
                    || radius.r_tip < 0.0
                    || radius.r_base < 0.0
                    || radius.wedge_gap < 0.0
                {
                    return Err(SceneError::Length);
                }
                table[index] = Some(radius);
            }
        }
        self.corner_radii = table;
        Ok(self)
    }

    /// Attach a host-packed XYPL v1 polar envelope. Empty bytes keep Cartesian
    /// mapping. Labeled-annotation extras fail closed. Polar Rects — including
    /// heatmap-lattice cells — tessellate to PolyFill annular sectors at encode.
    /// Rust recuts the cartesian plot rect (`recut_polar_plot`) before
    /// `polar_layout` so the inscribed disc and optional legend gutter match
    /// compatibility static export.
    pub fn with_polar(mut self, bytes: &[u8]) -> Result<Self, SceneError> {
        if bytes.is_empty() {
            return Ok(self);
        }
        if !self.arrows.is_empty() || !self.callouts.is_empty() || !self.labels.is_empty() {
            return Err(SceneError::Length);
        }
        if self.kinds.iter().any(|kind| {
            SceneRecordKind::from_code(*kind) == Ok(SceneRecordKind::Image)
        }) || !self.images.is_empty()
        {
            return Err(SceneError::Length);
        }
        let (layout, legend_box) = recut_polar_scene_layout(
            self.layout,
            self.legend.as_ref(),
            &self.text,
            self.colorbar.as_ref(),
            &self.chrome,
        )?;
        self.layout = layout;
        if let Some(legend) = &self.legend {
            resolved_legend_bounds(self.layout, legend, legend_box)?;
        }
        let mut polar = PolarSceneState::from_xypl(bytes, self.layout)?;
        polar.legend_box = legend_box;
        self.polar = Some(polar);
        Ok(self)
    }

    fn prepared_mark_records(&self) -> Vec<PreparedMarkRecord> {
        let mut out = Vec::with_capacity(self.kinds.len());
        for index in 0..self.kinds.len() {
            let kind = SceneRecordKind::from_code(self.kinds[index]).expect("validated kind");
            if let Some(polar) = &self.polar {
                if kind == SceneRecordKind::Rect {
                    let extra = self
                        .corner_radii
                        .get(self.style_refs[index] as usize)
                        .and_then(|value| value.as_ref());
                    let wedge_gap = extra.map(|value| value.wedge_gap).unwrap_or(0.0);
                    let corner_radius = extra
                        .map(|value| value.r_tip.max(value.r_base))
                        .unwrap_or(0.0);
                    let points = polar::polar_wedge_points(
                        &polar.metrics,
                        self.x0[index],
                        self.x1[index],
                        self.y0[index],
                        self.y1[index],
                        wedge_gap,
                        corner_radius,
                    );
                    if points.len() < 3
                        || points
                            .iter()
                            .any(|(px, py)| !px.is_finite() || !py.is_finite())
                        || out.len().saturating_add(points.len()) > MAX_SCENE_MARKS
                    {
                        continue;
                    }
                    let annotation_tag = if !self.annotations_from_ids {
                        0x80
                    } else if is_scene_annotation_id(self.stable_ids[index]) {
                        ((self.stable_ids[index] >> 40) & 0xff) as u8
                    } else {
                        0
                    };
                    let mark_id = self.stable_ids[index]
                        .wrapping_shl(32)
                        | ((index as u64) << 8);
                    for (px, py) in points {
                        let visible = px.is_finite() && py.is_finite();
                        out.push(PreparedMarkRecord {
                            kind: SceneRecordKind::PolyFill,
                            visible,
                            symbol: self.symbols[index],
                            annotation_tag,
                            style_ref: self.style_refs[index],
                            stable_id: mark_id,
                            coordinates: if visible {
                                [px, py, 0.0, 0.0]
                            } else {
                                [0.0; 4]
                            },
                            diameter: 0.0,
                        });
                    }
                    continue;
                }
            }
            let mapped = if let Some(polar) = &self.polar {
                match kind {
                    SceneRecordKind::Scatter
                    | SceneRecordKind::Polyline
                    | SceneRecordKind::PolyFill => match polar.project(self.x0[index], self.y0[index])
                    {
                        Some((px, py)) => [px, py, 0.0, 0.0],
                        None => [f64::NAN, f64::NAN, 0.0, 0.0],
                    },
                    SceneRecordKind::Band => {
                        match (
                            polar.project(self.x0[index], self.y0[index]),
                            polar.project(self.x1[index], self.y1[index]),
                        ) {
                            (Some((x0, y0)), Some((x1, y1))) => [x0, y0, x1, y1],
                            _ => [f64::NAN, f64::NAN, f64::NAN, f64::NAN],
                        }
                    }
                    SceneRecordKind::Rect => unreachable!("polar Rects tessellate before mapping"),
                    SceneRecordKind::Image => [f64::NAN, f64::NAN, f64::NAN, f64::NAN],
                }
            } else {
                match kind {
                    SceneRecordKind::Scatter
                    | SceneRecordKind::Polyline
                    | SceneRecordKind::PolyFill => [
                        self.x_scale.pixel(self.x0[index]),
                        self.y_scale.pixel(self.y0[index]),
                        0.0,
                        0.0,
                    ],
                    SceneRecordKind::Rect | SceneRecordKind::Band | SceneRecordKind::Image => [
                        self.x_scale.pixel(self.x0[index]),
                        self.y_scale.pixel(self.y0[index]),
                        self.x_scale.pixel(self.x1[index]),
                        self.y_scale.pixel(self.y1[index]),
                    ],
                }
            };
            let polar_visible = self.polar.as_ref().is_none_or(|polar| match kind {
                SceneRecordKind::Band => {
                    polar.visible(self.x0[index], self.y0[index])
                        || polar.visible(self.x1[index], self.y1[index])
                }
                SceneRecordKind::Rect | SceneRecordKind::Image => false,
                _ => polar.visible(self.x0[index], self.y0[index]),
            });
            let visible = mapped.iter().all(|value| value.is_finite())
                && polar_visible
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
                    SceneRecordKind::Rect | SceneRecordKind::Image => {
                        self.polar.is_none()
                            && mapped[0].min(mapped[2]) <= self.layout.right
                            && mapped[0].max(mapped[2]) >= self.layout.left
                            && mapped[1].min(mapped[3]) <= self.layout.bottom
                            && mapped[1].max(mapped[3]) >= self.layout.top
                    }
                };
            let symbol = if kind == SceneRecordKind::Band {
                let style = self.style_refs[index] as usize;
                BandOutline::canonical(
                    self.symbols[index],
                    self.stroke_width[style],
                    self.stroke_rgba[style * 4 + 3],
                )
                .expect("validated Band outline") as u8
            } else {
                self.symbols[index]
            };
            let annotation_tag = if !self.annotations_from_ids {
                0x80
            } else if is_scene_annotation_id(self.stable_ids[index]) {
                ((self.stable_ids[index] >> 40) & 0xff) as u8
            } else {
                0
            };
            let coordinates = if !visible {
                [0.0; 4]
            } else {
                match kind {
                    SceneRecordKind::Scatter
                    | SceneRecordKind::Polyline
                    | SceneRecordKind::PolyFill => [mapped[0], mapped[1], 0.0, 0.0],
                    SceneRecordKind::Rect | SceneRecordKind::Image => [
                        mapped[0].min(mapped[2]),
                        mapped[1].min(mapped[3]),
                        mapped[0].max(mapped[2]),
                        mapped[1].max(mapped[3]),
                    ],
                    SceneRecordKind::Band => mapped,
                }
            };
            if kind == SceneRecordKind::Rect && self.polar.is_none() && visible {
                if let Some(radius) = self
                    .corner_radii
                    .get(self.style_refs[index] as usize)
                    .and_then(|value| value.as_ref())
                    .copied()
                    .filter(|radius| radius.r_tip > 0.0 || radius.r_base > 0.0)
                {
                    let mark_id = self.stable_ids[index]
                        .wrapping_shl(32)
                        | ((index as u64) << 8);
                    if tessellate_rounded_rect_record(
                        &mut out,
                        mapped,
                        radius,
                        annotation_tag,
                        self.style_refs[index],
                        mark_id,
                        symbol,
                    ) {
                        continue;
                    }
                }
            }
            if kind == SceneRecordKind::Scatter {
                if let Some(path) = self
                    .marker_paths
                    .get(self.style_refs[index] as usize)
                    .and_then(|value| value.as_ref())
                {
                    if visible {
                        let style = self.style_refs[index] as usize;
                        let mut stroke_w = self.stroke_width[style];
                        if !path.filled && stroke_w <= 0.0 {
                            stroke_w = 1.0;
                        }
                        let scale = (self.diameter[index] - stroke_w).max(0.0);
                        let cx = mapped[0];
                        let cy = mapped[1];
                        let emit_kind = if path.filled {
                            SceneRecordKind::PolyFill
                        } else {
                            SceneRecordKind::Polyline
                        };
                        for (contour_index, contour) in path.contours.iter().enumerate() {
                            if out.len().saturating_add(contour.len()) > MAX_SCENE_MARKS {
                                break;
                            }
                            let mark_id = self.stable_ids[index]
                                .wrapping_shl(32)
                                | ((index as u64) << 8)
                                | (contour_index as u64);
                            for &(unit_x, unit_y) in contour {
                                out.push(PreparedMarkRecord {
                                    kind: emit_kind,
                                    visible: true,
                                    symbol: 0,
                                    annotation_tag,
                                    style_ref: self.style_refs[index],
                                    stable_id: mark_id,
                                    coordinates: [cx + scale * unit_x, cy - scale * unit_y, 0.0, 0.0],
                                    diameter: 0.0,
                                });
                            }
                        }
                    }
                    continue;
                }
            }
            out.push(PreparedMarkRecord {
                kind,
                visible,
                symbol,
                annotation_tag,
                style_ref: self.style_refs[index],
                stable_id: self.stable_ids[index],
                coordinates,
                diameter: self.diameter[index],
            });
        }
        out
    }

    pub fn encode(&self) -> Vec<u8> {
        let marks = self.prepared_mark_records();
        let mut labels = self.labels.clone();
        let mut label_backgrounds = self.label_backgrounds.clone();
        for callout in &self.callouts {
            labels.push(callout.label.clone());
            label_backgrounds.push(callout.label_background.clone());
        }
        let label_bytes =
            encode_scene_labels(&labels, &label_backgrounds).expect("validated Scene labels");
        let mut out = Vec::with_capacity(
            SCENE_BATCH_HEADER_BYTES
                + (self.stroke_width.len() + self.arrows.len() + self.callouts.len())
                    * SCENE_STYLE_RECORD_BYTES
                + (marks.len() + (self.arrows.len() + self.callouts.len()) * 5)
                    * SCENE_BATCH_RECORD_BYTES
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
        out.extend_from_slice(
            &((marks.len() + (self.arrows.len() + self.callouts.len()) * 5) as u64)
                .to_le_bytes(),
        );
        out.extend_from_slice(
            &((self.stroke_width.len() + self.arrows.len() + self.callouts.len()) as u64)
                .to_le_bytes(),
        );
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
            let filled = self
                .marker_paths
                .get(index)
                .and_then(|value| value.as_ref())
                .is_none_or(|path| path.filled);
            let fill = &self.fill_rgba[index * 4..index * 4 + 4];
            let stroke = if filled {
                &self.stroke_rgba[index * 4..index * 4 + 4]
            } else {
                fill
            };
            let stroke_width = if filled {
                self.stroke_width[index]
            } else {
                self.stroke_width[index].max(1.0)
            };
            out.extend_from_slice(fill);
            out.extend_from_slice(stroke);
            out.extend_from_slice(&stroke_width.to_le_bytes());
        }
        for arrow in &self.arrows {
            let rgba = straight_arrow_alpha(arrow.rgba, arrow.opacity).expect("validated arrow");
            out.extend_from_slice(&rgba);
            out.extend_from_slice(&rgba);
            out.extend_from_slice(&arrow.width.to_le_bytes());
        }
        for callout in &self.callouts {
            out.extend_from_slice(&callout.rgba);
            out.extend_from_slice(&callout.rgba);
            out.extend_from_slice(&callout.width.to_le_bytes());
        }

        for mark in &marks {
            out.push(mark.kind as u8);
            out.push(u8::from(mark.visible));
            out.push(mark.symbol);
            out.push(mark.annotation_tag);
            out.extend_from_slice(&mark.style_ref.to_le_bytes());
            out.extend_from_slice(&mark.stable_id.to_le_bytes());
            for value in mark.coordinates {
                out.extend_from_slice(&value.to_le_bytes());
            }
            out.extend_from_slice(&mark.diameter.to_le_bytes());
        }
        for (arrow_index, arrow) in self.arrows.iter().enumerate() {
            let start_x = self.x_scale.pixel(arrow.x0);
            let start_y = self.y_scale.pixel(arrow.y0);
            let tip_x = self.x_scale.pixel(arrow.x1);
            let tip_y = self.y_scale.pixel(arrow.y1);
            let (base, head) =
                straight_arrow_points(start_x, start_y, tip_x, tip_y).expect("validated arrow");
            let style_ref = (self.stroke_width.len() + arrow_index) as u32;
            let write = |out: &mut Vec<u8>, kind: SceneRecordKind, point: [f64; 2]| {
                out.push(kind as u8);
                out.push(1);
                out.push(0);
                out.push(SCENE_ANNOTATION_TAG_STRAIGHT_ARROW);
                out.extend_from_slice(&style_ref.to_le_bytes());
                out.extend_from_slice(&arrow.stable_id.to_le_bytes());
                out.extend_from_slice(&point[0].to_le_bytes());
                out.extend_from_slice(&point[1].to_le_bytes());
                out.extend_from_slice(&0.0f64.to_le_bytes());
                out.extend_from_slice(&0.0f64.to_le_bytes());
                out.extend_from_slice(&0.0f64.to_le_bytes());
            };
            write(&mut out, SceneRecordKind::Polyline, [start_x, start_y]);
            write(&mut out, SceneRecordKind::Polyline, base);
            for point in head {
                write(&mut out, SceneRecordKind::PolyFill, point);
            }
        }
        for (callout_index, callout) in self.callouts.iter().enumerate() {
            let (base, head) = straight_arrow_points(
                callout.tip[0],
                callout.tip[1],
                callout.start[0],
                callout.start[1],
            )
            .expect("validated callout");
            let style_ref = (self.stroke_width.len() + self.arrows.len() + callout_index) as u32;
            let write = |out: &mut Vec<u8>, kind: SceneRecordKind, point: [f64; 2]| {
                out.push(kind as u8);
                out.push(1);
                out.push(0);
                out.push(SCENE_ANNOTATION_TAG_CARTESIAN_CALLOUT);
                out.extend_from_slice(&style_ref.to_le_bytes());
                out.extend_from_slice(&callout.stable_id.to_le_bytes());
                out.extend_from_slice(&point[0].to_le_bytes());
                out.extend_from_slice(&point[1].to_le_bytes());
                out.extend_from_slice(&0.0f64.to_le_bytes());
                out.extend_from_slice(&0.0f64.to_le_bytes());
                out.extend_from_slice(&0.0f64.to_le_bytes());
            };
            write(&mut out, SceneRecordKind::Polyline, callout.tip);
            write(&mut out, SceneRecordKind::Polyline, base);
            for point in head {
                write(&mut out, SceneRecordKind::PolyFill, point);
            }
        }
        write_chrome_trailer(
            &mut out,
            &self.chrome,
            &self.text,
            self.legend.as_ref(),
            self.colorbar.as_ref(),
            &label_bytes,
        );
        if let Some(polar) = &self.polar {
            out.extend_from_slice(&polar.xypl);
        }
        out.extend_from_slice(&encode_xyim(&self.images).expect("validated Scene images"));
        out.extend_from_slice(&self.dashes);
        out
    }
}

#[derive(Clone, Copy)]
struct EncodedStyle {
    fill: [u8; 4],
    stroke: [u8; 4],
    stroke_width: f64,
    dash: [f32; 8],
    dash_count: u8,
    linecap: u8,
}

impl EncodedStyle {
    fn solid(fill: [u8; 4], stroke: [u8; 4], stroke_width: f64) -> Self {
        Self {
            fill,
            stroke,
            stroke_width,
            dash: [0.0; 8],
            dash_count: 0,
            linecap: LINECAP_ROUND,
        }
    }

    fn dash_values(&self) -> &[f32] {
        &self.dash[..self.dash_count as usize]
    }
}

fn rewrite_transparent_stops(stops: &[(f32, [u8; 4])]) -> Vec<(f32, [u8; 4])> {
    let opaque = |rgba: [u8; 4]| rgba[3] > 0;
    let mut out = Vec::with_capacity(stops.len());
    for (index, &(t, rgba)) in stops.iter().enumerate() {
        if opaque(rgba) {
            out.push((t, rgba));
            continue;
        }
        let previous = (0..index)
            .rev()
            .find_map(|j| opaque(stops[j].1).then_some(stops[j].1));
        let following = ((index + 1)..stops.len())
            .find_map(|j| opaque(stops[j].1).then_some(stops[j].1));
        let hue = previous.or(following).unwrap_or(rgba);
        out.push((t, [hue[0], hue[1], hue[2], 0]));
        if let (Some(prev), Some(next)) = (previous, following) {
            if prev[0] != next[0] || prev[1] != next[1] || prev[2] != next[2] {
                out.push((t, [next[0], next[1], next[2], 0]));
            }
        }
    }
    out
}

fn gradient_svg_ends(gradient: &AuthoredGradient, layout: PlotLayout) -> (bool, f64, f64, f64, f64) {
    let ends = match gradient.dir as u32 {
        XYGR_DIR_UP => (0.0, 1.0, 0.0, 0.0),
        XYGR_DIR_RIGHT => (0.0, 0.0, 1.0, 0.0),
        XYGR_DIR_LEFT => (1.0, 0.0, 0.0, 0.0),
        _ => (0.0, 0.0, 0.0, 1.0),
    };
    if gradient.plot_space {
        let x = layout.left;
        let y = layout.top;
        let w = layout.right - layout.left;
        let h = layout.bottom - layout.top;
        (
            true,
            x + ends.0 * w,
            y + ends.1 * h,
            x + ends.2 * w,
            y + ends.3 * h,
        )
    } else {
        (false, ends.0, ends.1, ends.2, ends.3)
    }
}

fn points_bbox(points: &[(f64, f64)]) -> (f64, f64, f64, f64) {
    let mut min_x = f64::INFINITY;
    let mut min_y = f64::INFINITY;
    let mut max_x = f64::NEG_INFINITY;
    let mut max_y = f64::NEG_INFINITY;
    for &(x, y) in points {
        min_x = min_x.min(x);
        min_y = min_y.min(y);
        max_x = max_x.max(x);
        max_y = max_y.max(y);
    }
    if !min_x.is_finite() {
        return (0.0, 0.0, 0.0, 0.0);
    }
    (min_x, min_y, (max_x - min_x).max(0.0), (max_y - min_y).max(0.0))
}

fn gradient_raster_line(
    gradient: &AuthoredGradient,
    bbox: (f64, f64, f64, f64),
    layout: PlotLayout,
) -> (f64, f64, f64, f64) {
    let (x, y, w, h) = if gradient.plot_space {
        (
            layout.left,
            layout.top,
            layout.right - layout.left,
            layout.bottom - layout.top,
        )
    } else {
        bbox
    };
    let cx = x + w * 0.5;
    let cy = y + h * 0.5;
    match gradient.dir as u32 {
        XYGR_DIR_UP => (cx, y + h, cx, y),
        XYGR_DIR_RIGHT => (x, cy, x + w, cy),
        XYGR_DIR_LEFT => (x + w, cy, x, cy),
        _ => (cx, y, cx, y + h),
    }
}

#[derive(Clone, Copy)]
struct PreparedMarkRecord {
    kind: SceneRecordKind,
    visible: bool,
    symbol: u8,
    annotation_tag: u8,
    style_ref: u32,
    stable_id: u64,
    coordinates: [f64; 4],
    diameter: f64,
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

/// Bounded authoring input for one canonical straight-arrow annotation.
///
/// Coordinates are Cartesian data values. Rust projects them and derives the
/// fixed screen-space head; callers never provide pixels or head geometry.
#[derive(Clone, Copy, Debug, PartialEq)]
pub struct StraightArrow {
    pub stable_id: u64,
    pub x0: f64,
    pub y0: f64,
    pub x1: f64,
    pub y1: f64,
    pub rgba: [u8; 4],
    pub opacity: f64,
    pub width: f64,
}

fn straight_arrow_points(
    start_x: f64,
    start_y: f64,
    tip_x: f64,
    tip_y: f64,
) -> Result<([f64; 2], [[f64; 2]; 3]), SceneError> {
    let dx = tip_x - start_x;
    let dy = tip_y - start_y;
    let length = dx.hypot(dy);
    if !length.is_finite() || length <= STRAIGHT_ARROW_HEAD_LENGTH {
        return Err(SceneError::Length);
    }
    let ux = dx / length;
    let uy = dy / length;
    let base_x = tip_x - ux * STRAIGHT_ARROW_HEAD_LENGTH;
    let base_y = tip_y - uy * STRAIGHT_ARROW_HEAD_LENGTH;
    let side_x = -uy * STRAIGHT_ARROW_HEAD_HALF_WIDTH;
    let side_y = ux * STRAIGHT_ARROW_HEAD_HALF_WIDTH;
    Ok((
        [base_x, base_y],
        [
            [tip_x, tip_y],
            [base_x + side_x, base_y + side_y],
            [base_x - side_x, base_y - side_y],
        ],
    ))
}

fn straight_arrow_alpha(rgba: [u8; 4], opacity: f64) -> Result<[u8; 4], SceneError> {
    if !opacity.is_finite() || !(0.0..=1.0).contains(&opacity) {
        return Err(SceneError::NonFinite);
    }
    let alpha = (f64::from(rgba[3]) * opacity).round();
    Ok([rgba[0], rgba[1], rgba[2], alpha as u8])
}

fn decode_xyar(bytes: &[u8]) -> Result<Vec<StraightArrow>, SceneError> {
    if bytes.is_empty() {
        return Ok(Vec::new());
    }
    if bytes.len() < 12 || &bytes[..4] != b"XYAR" || batch_u32(bytes, 4)? != 1 {
        return Err(SceneError::Length);
    }
    let count = batch_u32(bytes, 8)? as usize;
    if count > MAX_AUTHORED_STRAIGHT_ARROWS || bytes.len() != 12 + count * 60 {
        return Err(SceneError::Limit);
    }
    let mut arrows = Vec::with_capacity(count);
    let mut ids = std::collections::BTreeSet::new();
    for index in 0..count {
        let at = 12 + index * 60;
        let arrow = StraightArrow {
            stable_id: batch_u64(bytes, at)?,
            x0: batch_f64(bytes, at + 8)?,
            y0: batch_f64(bytes, at + 16)?,
            x1: batch_f64(bytes, at + 24)?,
            y1: batch_f64(bytes, at + 32)?,
            rgba: bytes[at + 40..at + 44].try_into().unwrap(),
            opacity: batch_f64(bytes, at + 44)?,
            width: batch_f64(bytes, at + 52)?,
        };
        if !ids.insert(arrow.stable_id)
            || ![
                arrow.x0,
                arrow.y0,
                arrow.x1,
                arrow.y1,
                arrow.opacity,
                arrow.width,
            ]
            .iter()
            .all(|value| value.is_finite())
            || !(0.0..=1.0).contains(&arrow.opacity)
            || arrow.width <= 0.0
        {
            return Err(SceneError::Length);
        }
        arrows.push(arrow);
    }
    Ok(arrows)
}

/// Rust-resolved Cartesian callout. `XYAC` contains only raw data anchors,
/// screen-space offsets and literal paint; this owned form is the sole input
/// to Scene record and label generation.
#[derive(Clone, Debug)]
struct CartesianCallout {
    stable_id: u64,
    start: [f64; 2],
    tip: [f64; 2],
    rgba: [u8; 4],
    width: f64,
    label: SceneLabel,
    label_background: Option<SceneLabelBox>,
}

// The literal frame fields stay separate here so the decoder remains aligned
// with the versioned XYAC record layout.
#[allow(clippy::too_many_arguments)]
fn resolved_callout_label_background(
    x: f64,
    y: f64,
    font_size: f64,
    anchor: u8,
    text: &str,
    rgba: [u8; 4],
    border: Option<SceneLabelBorder>,
    layout: PlotLayout,
) -> Result<Option<SceneLabelBox>, SceneError> {
    if rgba[3] == 0 && border.is_none() {
        return Ok(None);
    }
    let advance = text
        .split('\n')
        .map(|line| text_advance(line, font_size))
        .fold(0.0, f64::max);
    let lines = text.split('\n').count() as f64;
    let left = match anchor {
        0 => x,
        1 => x - advance * 0.5,
        2 => x - advance,
        _ => return Err(SceneError::Length),
    } - CALLOUT_LABEL_BOX_INSET;
    let top = y - font_size - CALLOUT_LABEL_BOX_INSET;
    let width = advance + 2.0 * CALLOUT_LABEL_BOX_INSET;
    let height = font_size * WRAPPED_LABEL_LINE_HEIGHT * lines + 2.0 * CALLOUT_LABEL_BOX_INSET;
    if ![left, top, width, height].into_iter().all(f64::is_finite)
        || width <= 0.0
        || height <= 0.0
        || left < 0.0
        || top < 0.0
        || left + width > layout.viewport_width
        || top + height > layout.viewport_height
    {
        return Err(SceneError::Limit);
    }
    Ok(Some(SceneLabelBox {
        x: left,
        y: top,
        width,
        height,
        rgba,
        border,
    }))
}

/// Decode XYAC v1/v2/v3. Version 1 has a 60-byte fixed row; version 2 adds a
/// literal callout-label background RGBA at bytes 60..64. No identity crosses
/// this seam: Rust assigns the tag-6 identity in wire order, preventing host
/// records from selecting canonical Scene IDs.
fn decode_xyac(
    bytes: &[u8],
    x_scale: AxisScale,
    y_scale: AxisScale,
    layout: PlotLayout,
) -> Result<Vec<CartesianCallout>, SceneError> {
    if bytes.is_empty() {
        return Ok(Vec::new());
    }
    if bytes.len() < 12 || &bytes[..4] != b"XYAC" {
        return Err(SceneError::Length);
    }
    let version = batch_u32(bytes, 4)?;
    if !(1..=3).contains(&version) {
        return Err(SceneError::Length);
    }
    let fixed_bytes = match version {
        1 => 60,
        2 => 64,
        3 => 76,
        _ => unreachable!(),
    };
    let count = batch_u32(bytes, 8)? as usize;
    if count > MAX_AUTHORED_TEXT_ANNOTATIONS {
        return Err(SceneError::Limit);
    }
    let mut at = 12usize;
    let mut total = 0usize;
    let mut out = Vec::with_capacity(count);
    for index in 0..count {
        let fixed_end = at.checked_add(fixed_bytes).ok_or(SceneError::Limit)?;
        let fixed = bytes.get(at..fixed_end).ok_or(SceneError::Length)?;
        if fixed[53..56] != [0; 3] {
            return Err(SceneError::Length);
        }
        let x = f64::from_le_bytes(fixed[0..8].try_into().unwrap());
        let y = f64::from_le_bytes(fixed[8..16].try_into().unwrap());
        let dx = f64::from_le_bytes(fixed[16..24].try_into().unwrap());
        let dy = f64::from_le_bytes(fixed[24..32].try_into().unwrap());
        let rgba: [u8; 4] = fixed[32..36].try_into().unwrap();
        let opacity = f64::from_le_bytes(fixed[36..44].try_into().unwrap());
        let width = f64::from_le_bytes(fixed[44..52].try_into().unwrap());
        let anchor = fixed[52];
        let text_len = u32::from_le_bytes(fixed[56..60].try_into().unwrap()) as usize;
        let label_background = if version >= 2 {
            fixed[60..64].try_into().unwrap()
        } else {
            [0; 4]
        };
        let border = if version == 3 {
            let rgba: [u8; 4] = fixed[64..68].try_into().unwrap();
            let width = f64::from_le_bytes(fixed[68..76].try_into().unwrap());
            if rgba[3] == 0 {
                if width != 0.0 {
                    return Err(SceneError::Length);
                }
                None
            } else if !width.is_finite() || width <= 0.0 {
                return Err(SceneError::Length);
            } else {
                Some(SceneLabelBorder { rgba, width })
            }
        } else {
            None
        };
        if label_background[3] == 0 && border.is_some() {
            return Err(SceneError::Length);
        }
        let end = fixed_end.checked_add(text_len).ok_or(SceneError::Limit)?;
        let text = std::str::from_utf8(bytes.get(fixed_end..end).ok_or(SceneError::Length)?)
            .map_err(|_| SceneError::Length)?;
        total = total.checked_add(text_len).ok_or(SceneError::Limit)?;
        if ![x, y, dx, dy, opacity, width]
            .iter()
            .all(|value| value.is_finite())
            || !(0.0..=1.0).contains(&opacity)
            || width <= 0.0
            || anchor > 2
            || text.is_empty()
            || text.contains('\0')
            || total > MAX_SCENE_LABEL_TEXT_BYTES
        {
            return Err(SceneError::Length);
        }
        let start = [x_scale.pixel(x), y_scale.pixel(y)];
        let tip = [start[0] + dx, start[1] + dy];
        if !start
            .iter()
            .chain(tip.iter())
            .all(|value| value.is_finite())
            || start[0] < layout.left
            || start[0] > layout.right
            || start[1] < layout.top
            || start[1] > layout.bottom
            || tip[0] < layout.left
            || tip[0] > layout.right
            || tip[1] < layout.top
            || tip[1] > layout.bottom
        {
            return Err(SceneError::Length);
        }
        // Validate the fixed canonical head before any output state is built.
        straight_arrow_points(tip[0], tip[1], start[0], start[1])?;
        let stable_id = 0x5859_0600_0000_0000 | index as u64;
        let label_rgba = straight_arrow_alpha(rgba, opacity)?;
        out.push(CartesianCallout {
            stable_id,
            start,
            tip,
            rgba: label_rgba,
            width,
            label: SceneLabel {
                stable_id,
                x: tip[0],
                y: tip[1],
                font_size: 12.0,
                rgba: label_rgba,
                anchor,
                text: text.to_owned(),
            },
            label_background: resolved_callout_label_background(
                tip[0],
                tip[1],
                12.0,
                anchor,
                text,
                label_background,
                border,
                layout,
            )?,
        });
        at = end;
    }
    if at != bytes.len() {
        return Err(SceneError::Length);
    }
    Ok(out)
}

fn valid_straight_arrow_run(records: &[EncodedRecord]) -> bool {
    if records.len() != 5
        || records[0].kind != SceneRecordKind::Polyline
        || records[1].kind != SceneRecordKind::Polyline
        || records[2..]
            .iter()
            .any(|record| record.kind != SceneRecordKind::PolyFill)
    {
        return false;
    }
    let first = records[0];
    if records.iter().any(|record| {
        !matches!(
            record.annotation_tag,
            SCENE_ANNOTATION_TAG_STRAIGHT_ARROW | SCENE_ANNOTATION_TAG_CARTESIAN_CALLOUT
        ) || record.stable_id != first.stable_id
            || record.style_ref != first.style_ref
            || record.visible != first.visible
            || record.symbol != 0
            || record.diameter != 0.0
    }) {
        return false;
    }
    if !first.visible {
        return records.iter().all(|record| record.coordinates == [0.0; 4]);
    }
    let start = [records[0].coordinates[0], records[0].coordinates[1]];
    let base = [records[1].coordinates[0], records[1].coordinates[1]];
    let tip = [records[2].coordinates[0], records[2].coordinates[1]];
    let Ok((expected_base, expected_head)) =
        straight_arrow_points(start[0], start[1], tip[0], tip[1])
    else {
        return false;
    };
    scene_edge_eq(base[0], expected_base[0])
        && scene_edge_eq(base[1], expected_base[1])
        && records[2..]
            .iter()
            .zip(expected_head.iter())
            .all(|(record, expected)| {
                scene_edge_eq(record.coordinates[0], expected[0])
                    && scene_edge_eq(record.coordinates[1], expected[1])
                    && record.coordinates[2] == 0.0
                    && record.coordinates[3] == 0.0
            })
}

// Scene v12 tag 0x80 marks literal per-row identity, so it is intentionally
// excluded from grouping: callers use kind/style for those run boundaries,
// while legacy and annotation records additionally require stable-ID equality.
fn same_record_run(left: EncodedRecord, right: EncodedRecord) -> bool {
    left.annotation_tag == right.annotation_tag
        && (left.annotation_tag == 0x80 || left.stable_id == right.stable_id)
        && (left.kind != SceneRecordKind::Band || left.symbol == right.symbol)
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

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
struct NumericTickFormat<'a> {
    prefix: &'a str,
    suffix: &'a str,
    digits: usize,
    grouped: bool,
    percent: bool,
}

impl<'a> NumericTickFormat<'a> {
    /// Parse the deliberately small public numeric grammar:
    /// `<prefix>(,).N[f|%]<suffix>`. Invalid syntax is not an error; callers
    /// preserve the public contract by falling back to the default formatter.
    fn parse(value: &'a str) -> Option<Self> {
        if value.len() > MAX_SCENE_AXIS_FORMAT_BYTES || value.contains('\0') {
            return None;
        }
        let (before_dot, after_dot) = value.split_once('.')?;
        if after_dot.contains('.') {
            return None;
        }
        let (prefix, grouped) = before_dot
            .strip_suffix(',')
            .map_or((before_dot, false), |prefix| (prefix, true));
        if prefix.contains([',', '%']) {
            return None;
        }
        let digit_bytes = after_dot
            .as_bytes()
            .iter()
            .take_while(|byte| byte.is_ascii_digit())
            .count();
        if digit_bytes == 0 {
            return None;
        }
        let digits = after_dot[..digit_bytes].parse::<usize>().ok()?;
        if digits > MAX_NUMERIC_TICK_FORMAT_PRECISION {
            return None;
        }
        let mut rest = &after_dot[digit_bytes..];
        let explicit_f = rest.starts_with('f');
        if explicit_f {
            rest = &rest[1..];
        }
        let percent = rest.starts_with('%');
        if percent {
            rest = &rest[1..];
        }
        if rest.contains([',', '.', '%'])
            || (!explicit_f && !percent && (!prefix.is_empty() || !rest.is_empty()))
        {
            return None;
        }
        Some(Self {
            prefix,
            suffix: rest,
            digits,
            grouped,
            percent,
        })
    }

    fn fixed_number(self, value: f64) -> Option<String> {
        let value = if self.percent { value * 100.0 } else { value };
        if !value.is_finite() {
            return None;
        }
        let raw = format!("{value:.digits$}", digits = self.digits);
        if !self.grouped {
            return Some(raw);
        }
        let (sign, unsigned) = raw
            .strip_prefix('-')
            .map_or(("", raw.as_str()), |value| ("-", value));
        let (integer, fraction) = unsigned
            .split_once('.')
            .map_or((unsigned, None), |(integer, fraction)| {
                (integer, Some(fraction))
            });
        let mut grouped = String::with_capacity(raw.len() + integer.len() / 3);
        grouped.push_str(sign);
        let leading = integer.len() % 3;
        if leading != 0 {
            grouped.push_str(&integer[..leading]);
        }
        for chunk in integer.as_bytes()[leading..].chunks(3) {
            if grouped.len() > sign.len() {
                grouped.push(',');
            }
            grouped.push_str(std::str::from_utf8(chunk).expect("ASCII fixed integer"));
        }
        if let Some(fraction) = fraction {
            grouped.push('.');
            grouped.push_str(fraction);
        }
        Some(grouped)
    }

    fn format(self, value: f64, step: f64, kind: ScaleKind) -> String {
        let Some(number) = self.fixed_number(value) else {
            return format_tick(value, step, kind);
        };
        if kind == ScaleKind::Log
            && value > 0.0
            && value < 1.0
            && number
                .replace(',', "")
                .parse::<f64>()
                .is_ok_and(|value| value == 0.0)
        {
            return format_tick(value, step, kind);
        }
        format!(
            "{}{number}{}{}",
            self.prefix,
            if self.percent { "%" } else { "" },
            self.suffix
        )
    }
}

/// Resolve one primary Cartesian numeric tick label. Authored invalid syntax
/// deliberately falls back to the same deterministic default formatter.
pub fn format_numeric_tick(value: f64, step: f64, kind: ScaleKind, format: Option<&str>) -> String {
    format.and_then(NumericTickFormat::parse).map_or_else(
        || format_tick(value, step, kind),
        |format| format.format(value, step, kind),
    )
}

/// Format an angular tick without locale-dependent host APIs.
pub fn format_angular_tick(value: f64, step: f64, degrees: bool, format: Option<&str>) -> String {
    if let Some(format) = format.and_then(NumericTickFormat::parse) {
        return format.format(value, step, ScaleKind::Linear);
    }
    if degrees {
        return format!(
            "{}\u{00b0}",
            format_tick(
                value,
                if step == 0.0 { 1.0 } else { step },
                ScaleKind::Linear
            )
        );
    }
    if value.abs() < 1e-12 {
        return "0".to_owned();
    }
    let fraction = value / std::f64::consts::PI;
    for denominator in [1_i32, 2, 3, 4, 6, 8, 12] {
        let scaled = fraction * f64::from(denominator);
        let numerator = scaled.round() as i64;
        if numerator != 0 && (scaled - numerator as f64).abs() < 1e-6 {
            let magnitude = if numerator.abs() == 1 {
                String::new()
            } else {
                numerator.abs().to_string()
            };
            let body = format!(
                "{}{}\u{03c0}",
                if numerator < 0 { "-" } else { "" },
                magnitude
            );
            return if denominator == 1 {
                body
            } else {
                format!("{body}/{denominator}")
            };
        }
    }
    format_tick(value, 0.01, ScaleKind::Linear)
}

const UTC_MONTH_SHORT: [&str; 12] = [
    "Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
];
const UTC_MONTH_LONG: [&str; 12] = [
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
];

fn utc_parts(ms: f64) -> Option<(i32, usize, u32, u32, u32, u32)> {
    if !ms.is_finite() || ms.abs() > 8_640_000_000_000_000.0 {
        return None;
    }
    let whole_ms = ms.floor() as i64;
    let days = whole_ms.div_euclid(MS_D as i64);
    let day_ms = whole_ms.rem_euclid(MS_D as i64);
    let z = days + 719_468;
    let era = if z >= 0 { z } else { z - 146_096 } / 146_097;
    let doe = z - era * 146_097;
    let yoe = (doe - doe / 1_460 + doe / 36_524 - doe / 146_096) / 365;
    let mut year = yoe + era * 400;
    let doy = doe - (365 * yoe + yoe / 4 - yoe / 100);
    let mp = (5 * doy + 2) / 153;
    let day = doy - (153 * mp + 2) / 5 + 1;
    let month = if mp < 10 { mp + 3 } else { mp - 9 };
    if month <= 2 {
        year += 1;
    }
    let hour = day_ms / 3_600_000;
    let minute = day_ms % 3_600_000 / 60_000;
    let second = day_ms % 60_000 / 1_000;
    let milli = day_ms % 1_000;
    Some((
        year as i32,
        (month - 1) as usize,
        day as u32,
        hour as u32,
        minute as u32,
        second as u32 * 1000 + milli as u32,
    ))
}

/// Format a UTC-millisecond tick with the same bounded grammar as browser axes.
pub fn format_time_tick(value: f64, step: f64, format: Option<&str>) -> String {
    let Some((year, month, day, hour, minute, second_millis)) = utc_parts(value) else {
        return String::new();
    };
    let second = second_millis / 1000;
    let millis = second_millis % 1000;
    if let Some(pattern) = format {
        let mut out = String::with_capacity(pattern.len().saturating_add(16));
        let mut chars = pattern.chars().peekable();
        while let Some(ch) = chars.next() {
            if ch != '%' {
                out.push(ch);
                continue;
            }
            match chars.peek().copied() {
                Some('Y') => {
                    chars.next();
                    out.push_str(&year.to_string());
                }
                Some('m') => {
                    chars.next();
                    out.push_str(&format!("{:02}", month + 1));
                }
                Some('d') => {
                    chars.next();
                    out.push_str(&format!("{day:02}"));
                }
                Some('H') => {
                    chars.next();
                    out.push_str(&format!("{hour:02}"));
                }
                Some('M') => {
                    chars.next();
                    out.push_str(&format!("{minute:02}"));
                }
                Some('S') => {
                    chars.next();
                    out.push_str(&format!("{second:02}"));
                }
                Some('b') => {
                    chars.next();
                    out.push_str(UTC_MONTH_SHORT[month]);
                }
                Some('B') => {
                    chars.next();
                    out.push_str(UTC_MONTH_LONG[month]);
                }
                _ => out.push('%'),
            }
        }
        return out;
    }
    if step >= 28.0 * MS_D {
        if month == 0 {
            year.to_string()
        } else {
            format!("{} {year}", UTC_MONTH_SHORT[month])
        }
    } else if step >= MS_D {
        format!("{} {day:02}", UTC_MONTH_SHORT[month])
    } else if step >= MS_M {
        format!("{hour:02}:{minute:02}")
    } else if step >= MS_S {
        format!("{hour:02}:{minute:02}:{second:02}")
    } else {
        format!("{minute:02}:{second:02}.{millis:03}")
    }
}

pub const TICK_FORMAT_KIND_NUMERIC: u32 = 0;
pub const TICK_FORMAT_KIND_TIME: u32 = 1;
pub const TICK_FORMAT_KIND_CATEGORY: u32 = 2;

pub const TICK_FORMAT_SCALE_LINEAR: u32 = 0;
pub const TICK_FORMAT_SCALE_LOG: u32 = 1;

pub const TICK_FORMAT_THETA_NONE: u32 = 0;
pub const TICK_FORMAT_THETA_DEGREES: u32 = 1;
pub const TICK_FORMAT_THETA_RADIANS: u32 = 2;

/// Resolve one category tick label from a rounded index.
pub fn format_category_tick(value: f64, categories: &[String]) -> String {
    let index = value.round() as i64;
    if index >= 0 {
        let index = index as usize;
        if let Some(label) = categories.get(index) {
            return label.clone();
        }
    }
    String::new()
}

/// Format one axis tick label using the same branch order as host `_fmt_axis`
/// / browser `fmtAxis`: category wins, then angular `theta_unit`, then time,
/// then numeric with optional log-scale collapse.
pub fn format_axis_tick(
    value: f64,
    step: f64,
    kind: u32,
    scale: u32,
    theta_unit: u32,
    format: Option<&str>,
    categories: &[String],
) -> String {
    if kind == TICK_FORMAT_KIND_CATEGORY {
        return format_category_tick(value, categories);
    }
    if theta_unit != TICK_FORMAT_THETA_NONE {
        let degrees = theta_unit == TICK_FORMAT_THETA_DEGREES;
        return format_angular_tick(value, step, degrees, format);
    }
    if kind == TICK_FORMAT_KIND_TIME {
        return format_time_tick(value, step, format);
    }
    let scale_kind = if scale == TICK_FORMAT_SCALE_LOG {
        ScaleKind::Log
    } else {
        ScaleKind::Linear
    };
    format_numeric_tick(value, step, scale_kind, format)
}

/// Compile bounded authored numeric formats into the existing canonical major
/// positions and `XYTL` labels. Explicit authored labels retain precedence.
/// Automatic minor positions are materialized too so log grids do not change
/// when automatic majors become explicit canonical positions.
pub fn resolve_numeric_tick_formats(
    layout: PlotLayout,
    x_scale: AxisScale,
    y_scale: AxisScale,
    chrome: &mut SceneChromeStyle,
    x_format: Option<&str>,
    y_format: Option<&str>,
) -> Result<(), SceneError> {
    let resolve = |scale: AxisScale,
                   length: f64,
                   is_x: bool,
                   pixel_min: f64,
                   pixel_max: f64,
                   major: &mut Option<Vec<f64>>,
                   minor: &mut Vec<f64>,
                   labels: &mut Option<Vec<String>>,
                   authored_format: Option<&str>|
     -> Result<(), SceneError> {
        let Some(format) = authored_format.and_then(NumericTickFormat::parse) else {
            return Ok(());
        };
        if labels.is_some() {
            return Ok(());
        }
        let resolved = resolved_axis_ticks(
            scale,
            length,
            is_x,
            pixel_min,
            pixel_max,
            major.as_deref(),
            minor,
        )?;
        if major.is_none() {
            *minor = resolved
                .ticks
                .iter()
                .copied()
                .filter(|value| !resolved.labeled.contains(value))
                .collect();
            *major = Some(resolved.labeled.clone());
        }
        let values = major.as_deref().unwrap_or_default();
        *labels = Some(
            values
                .iter()
                .map(|value| format.format(*value, resolved.step, scale.kind))
                .collect(),
        );
        Ok(())
    };
    resolve(
        x_scale,
        layout.right - layout.left,
        true,
        layout.left,
        layout.right,
        &mut chrome.x_major_ticks,
        &mut chrome.x_minor_ticks,
        &mut chrome.x_tick_labels,
        x_format,
    )?;
    resolve(
        y_scale,
        layout.bottom - layout.top,
        false,
        layout.top,
        layout.bottom,
        &mut chrome.y_major_ticks,
        &mut chrome.y_minor_ticks,
        &mut chrome.y_tick_labels,
        y_format,
    )?;
    chrome.clone().validated()?;
    Ok(())
}

#[cfg(feature = "raster")]
fn encode_base64(bytes: &[u8]) -> String {
    const TABLE: &[u8] = b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
    let mut out = String::with_capacity(bytes.len().div_ceil(3) * 4);
    let mut index = 0usize;
    while index + 3 <= bytes.len() {
        let n = (u32::from(bytes[index]) << 16)
            | (u32::from(bytes[index + 1]) << 8)
            | u32::from(bytes[index + 2]);
        out.push(TABLE[((n >> 18) & 63) as usize] as char);
        out.push(TABLE[((n >> 12) & 63) as usize] as char);
        out.push(TABLE[((n >> 6) & 63) as usize] as char);
        out.push(TABLE[(n & 63) as usize] as char);
        index += 3;
    }
    match bytes.len() - index {
        1 => {
            let n = u32::from(bytes[index]) << 16;
            out.push(TABLE[((n >> 18) & 63) as usize] as char);
            out.push(TABLE[((n >> 12) & 63) as usize] as char);
            out.push('=');
            out.push('=');
        }
        2 => {
            let n = (u32::from(bytes[index]) << 16) | (u32::from(bytes[index + 1]) << 8);
            out.push(TABLE[((n >> 18) & 63) as usize] as char);
            out.push(TABLE[((n >> 12) & 63) as usize] as char);
            out.push(TABLE[((n >> 6) & 63) as usize] as char);
            out.push('=');
        }
        _ => {}
    }
    out
}

fn scene_image_by_id<'a>(images: &'a [SceneImage], stable_id: u64) -> Option<&'a SceneImage> {
    images.iter().find(|image| image.stable_id == stable_id)
}

fn push_svg_line(out: &mut String, x1: f64, y1: f64, x2: f64, y2: f64, paint: &str, width: f64) {
    push_svg_line_dash(out, x1, y1, x2, y2, paint, width, &[], LINECAP_ROUND);
}

fn linecap_svg_name(cap: u8) -> &'static str {
    match cap {
        LINECAP_BUTT => "butt",
        LINECAP_SQUARE => "square",
        _ => "round",
    }
}

fn push_svg_line_dash(
    out: &mut String,
    x1: f64,
    y1: f64,
    x2: f64,
    y2: f64,
    paint: &str,
    width: f64,
    dash: &[f32],
    linecap: u8,
) {
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
    push_svg_dasharray(out, dash);
    if linecap != LINECAP_ROUND {
        out.push_str("\" stroke-linecap=\"");
        out.push_str(linecap_svg_name(linecap));
    }
    out.push_str("\"/>");
}

fn push_svg_dasharray(out: &mut String, dash: &[f32]) {
    if dash.is_empty() {
        return;
    }
    out.push_str("\" stroke-dasharray=\"");
    for (index, value) in dash.iter().enumerate() {
        if index > 0 {
            out.push(',');
        }
        push_num(out, f64::from(*value));
    }
}

fn push_polar_sector_path(out: &mut String, polar: &PolarSceneState, outer: f64, inner: f64) {
    let cx = polar.cx();
    let cy = polar.cy();
    let a0 = polar.sector_a0();
    let a1 = polar.sector_a1();
    let at = |radius: f64, angle: f64| (cx + radius * angle.cos(), cy - radius * angle.sin());
    if polar.full_sector() {
        let (x0, y0) = at(outer, a0);
        let (xm, ym) = at(outer, a0 + std::f64::consts::PI);
        out.push('M');
        push_num(out, x0);
        out.push(' ');
        push_num(out, y0);
        out.push_str(" A ");
        push_num(out, outer);
        out.push(' ');
        push_num(out, outer);
        out.push_str(" 0 1 0 ");
        push_num(out, xm);
        out.push(' ');
        push_num(out, ym);
        out.push_str(" A ");
        push_num(out, outer);
        out.push(' ');
        push_num(out, outer);
        out.push_str(" 0 1 0 ");
        push_num(out, x0);
        out.push(' ');
        push_num(out, y0);
        out.push_str(" Z");
        if inner > 1e-9 {
            let (ix0, iy0) = at(inner, a0);
            let (ixm, iym) = at(inner, a0 + std::f64::consts::PI);
            out.push_str(" M ");
            push_num(out, ix0);
            out.push(' ');
            push_num(out, iy0);
            out.push_str(" A ");
            push_num(out, inner);
            out.push(' ');
            push_num(out, inner);
            out.push_str(" 0 1 1 ");
            push_num(out, ixm);
            out.push(' ');
            push_num(out, iym);
            out.push_str(" A ");
            push_num(out, inner);
            out.push(' ');
            push_num(out, inner);
            out.push_str(" 0 1 1 ");
            push_num(out, ix0);
            out.push(' ');
            push_num(out, iy0);
            out.push_str(" Z");
        }
        return;
    }
    let sweep = u8::from(a1 <= a0);
    let large = u8::from((a1 - a0).abs() > std::f64::consts::PI);
    let (ox0, oy0) = at(outer, a0);
    let (ox1, oy1) = at(outer, a1);
    if inner <= 1e-9 {
        out.push('M');
        push_num(out, cx);
        out.push(' ');
        push_num(out, cy);
        out.push_str(" L ");
        push_num(out, ox0);
        out.push(' ');
        push_num(out, oy0);
        out.push_str(" A ");
        push_num(out, outer);
        out.push(' ');
        push_num(out, outer);
        out.push_str(" 0 ");
        out.push(char::from(b'0' + large));
        out.push(' ');
        out.push(char::from(b'0' + sweep));
        out.push(' ');
        push_num(out, ox1);
        out.push(' ');
        push_num(out, oy1);
        out.push_str(" Z");
        return;
    }
    let (ix1, iy1) = at(inner, a1);
    let (ix0, iy0) = at(inner, a0);
    out.push('M');
    push_num(out, ox0);
    out.push(' ');
    push_num(out, oy0);
    out.push_str(" A ");
    push_num(out, outer);
    out.push(' ');
    push_num(out, outer);
    out.push_str(" 0 ");
    out.push(char::from(b'0' + large));
    out.push(' ');
    out.push(char::from(b'0' + sweep));
    out.push(' ');
    push_num(out, ox1);
    out.push(' ');
    push_num(out, oy1);
    out.push_str(" L ");
    push_num(out, ix1);
    out.push(' ');
    push_num(out, iy1);
    out.push_str(" A ");
    push_num(out, inner);
    out.push(' ');
    push_num(out, inner);
    out.push_str(" 0 ");
    out.push(char::from(b'0' + large));
    out.push(' ');
    out.push(char::from(b'0' + (1 - sweep)));
    out.push(' ');
    push_num(out, ix0);
    out.push(' ');
    push_num(out, iy0);
    out.push_str(" Z");
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
    label_backgrounds: Vec<Option<SceneLabelBox>>,
    styles: Vec<EncodedStyle>,
    records: Vec<EncodedRecord>,
    raster_mark_capacity: usize,
    polar: Option<PolarSceneState>,
    images: Vec<SceneImage>,
    gradients: Vec<Option<AuthoredGradient>>,
    marker_glyphs: Vec<Option<String>>,
}

impl SceneDocument {
    /// Add Rust-resolved Cartesian callout leaders and their shared labels.
    /// The leader is the same fixed-head primitive contract as an authored
    /// arrow, but tag 6 makes its semantic identity explicit to all consumers.
    fn with_cartesian_callouts(
        mut self,
        callouts: &[CartesianCallout],
    ) -> Result<Self, SceneError> {
        if callouts.len() > MAX_AUTHORED_TEXT_ANNOTATIONS
            || self
                .records
                .len()
                .checked_add(callouts.len().checked_mul(5).ok_or(SceneError::Limit)?)
                .ok_or(SceneError::Limit)?
                > MAX_SCENE_MARKS
            || self
                .styles
                .len()
                .checked_add(callouts.len())
                .ok_or(SceneError::Limit)?
                > MAX_SCENE_STYLES
            || self
                .labels
                .len()
                .checked_add(callouts.len())
                .ok_or(SceneError::Limit)?
                > MAX_SCENE_LABELS
        {
            return Err(SceneError::Limit);
        }
        for callout in callouts {
            if self
                .records
                .iter()
                .any(|record| record.stable_id == callout.stable_id)
                || self
                    .labels
                    .iter()
                    .any(|label| label.stable_id == callout.stable_id)
                || callout.label.stable_id != callout.stable_id
                || callout.label.anchor > 2
            {
                return Err(SceneError::Length);
            }
            let (base, head) = straight_arrow_points(
                callout.tip[0],
                callout.tip[1],
                callout.start[0],
                callout.start[1],
            )?;
            let style_ref = self.styles.len();
            self.styles.push(EncodedStyle::solid(
                callout.rgba,
                callout.rgba,
                callout.width,
            ));
            let record = |kind, coordinates| EncodedRecord {
                kind,
                visible: true,
                symbol: 0,
                style_ref,
                stable_id: callout.stable_id,
                coordinates,
                diameter: 0.0,
                annotation_tag: SCENE_ANNOTATION_TAG_CARTESIAN_CALLOUT,
            };
            self.records.push(record(
                SceneRecordKind::Polyline,
                [callout.tip[0], callout.tip[1], 0.0, 0.0],
            ));
            self.records.push(record(
                SceneRecordKind::Polyline,
                [base[0], base[1], 0.0, 0.0],
            ));
            for point in head {
                self.records.push(record(
                    SceneRecordKind::PolyFill,
                    [point[0], point[1], 0.0, 0.0],
                ));
            }
            self.labels.push(callout.label.clone());
            self.label_backgrounds
                .push(callout.label_background.clone());
        }
        Ok(self)
    }

    /// Add bounded Cartesian arrows as canonical shaft and head primitives.
    ///
    /// The arrowhead is fixed in screen space and derived after Rust projects
    /// the data endpoints. This narrow seam deliberately accepts neither text
    /// nor callout placement/style policy.
    pub fn with_straight_arrows(mut self, arrows: &[StraightArrow]) -> Result<Self, SceneError> {
        if arrows.len() > MAX_AUTHORED_STRAIGHT_ARROWS
            || self
                .records
                .len()
                .checked_add(arrows.len().checked_mul(5).ok_or(SceneError::Limit)?)
                .ok_or(SceneError::Limit)?
                > MAX_SCENE_MARKS
        {
            return Err(SceneError::Limit);
        }
        let mut ids = std::collections::BTreeSet::new();
        for arrow in arrows {
            if !ids.insert(arrow.stable_id)
                || self
                    .records
                    .iter()
                    .any(|record| record.stable_id == arrow.stable_id)
                || !arrow.x0.is_finite()
                || !arrow.y0.is_finite()
                || !arrow.x1.is_finite()
                || !arrow.y1.is_finite()
                || !arrow.width.is_finite()
                || arrow.width <= 0.0
            {
                return Err(SceneError::Length);
            }
            let start_x = self.x_scale.pixel(arrow.x0);
            let start_y = self.y_scale.pixel(arrow.y0);
            let tip_x = self.x_scale.pixel(arrow.x1);
            let tip_y = self.y_scale.pixel(arrow.y1);
            if !start_x.is_finite()
                || !start_y.is_finite()
                || !tip_x.is_finite()
                || !tip_y.is_finite()
            {
                return Err(SceneError::NonFinite);
            }
            let (base, head) = straight_arrow_points(start_x, start_y, tip_x, tip_y)?;
            let rgba = straight_arrow_alpha(arrow.rgba, arrow.opacity)?;
            let style_ref = self.styles.len();
            if style_ref >= MAX_SCENE_STYLES {
                return Err(SceneError::Limit);
            }
            self.styles.push(EncodedStyle::solid(rgba, rgba, arrow.width));
            let record = |kind, coordinates| EncodedRecord {
                kind,
                visible: true,
                symbol: 0,
                style_ref,
                stable_id: arrow.stable_id,
                coordinates,
                diameter: 0.0,
                annotation_tag: SCENE_ANNOTATION_TAG_STRAIGHT_ARROW,
            };
            self.records.push(record(
                SceneRecordKind::Polyline,
                [start_x, start_y, 0.0, 0.0],
            ));
            self.records.push(record(
                SceneRecordKind::Polyline,
                [base[0], base[1], 0.0, 0.0],
            ));
            for point in head {
                self.records.push(record(
                    SceneRecordKind::PolyFill,
                    [point[0], point[1], 0.0, 0.0],
                ));
            }
        }
        Ok(self)
    }

    /// Add bounded XYAT decorations to an already validated canonical Scene.
    ///
    /// The Scene remains the source of its layout and scales: the envelope
    /// carries data coordinates only, which are projected here before any
    /// browser consumer observes them.
    pub fn with_authored_annotations(mut self, bytes: &[u8]) -> Result<Self, SceneError> {
        let existing = self.labels.len();
        let envelope = decode_annotation_envelope(bytes, &self)?;
        let mut labels = envelope.labels;
        if existing
            .checked_add(labels.len())
            .and_then(|count| count.checked_add(envelope.callouts.len()))
            .ok_or(SceneError::Limit)?
            > MAX_SCENE_LABELS
        {
            return Err(SceneError::Limit);
        }
        for (index, label) in labels.iter_mut().enumerate() {
            label.stable_id = 0x5859_0400_0000_0000 | (existing + index) as u64;
        }
        self.labels.append(&mut labels);
        self.label_backgrounds.extend(envelope.label_backgrounds);
        self = self.with_straight_arrows(&envelope.arrows)?;
        self = self.with_cartesian_callouts(&envelope.callouts)?;
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
        let ticks = resolved_colorbar_ticks(colorbar, (x, y, width, height))?;
        out.extend_from_slice(b"XYCT");
        out.extend_from_slice(&1u32.to_le_bytes());
        out.extend_from_slice(&(ticks.majors.len() as u32).to_le_bytes());
        out.extend_from_slice(&(ticks.minors.len() as u32).to_le_bytes());
        for (value, position, label) in &ticks.majors {
            out.extend_from_slice(&value.to_le_bytes());
            out.extend_from_slice(&checked_f32(*position)?.to_le_bytes());
            out.extend_from_slice(&(label.len() as u32).to_le_bytes());
        }
        for (value, position) in &ticks.minors {
            out.extend_from_slice(&value.to_le_bytes());
            out.extend_from_slice(&checked_f32(*position)?.to_le_bytes());
            out.extend_from_slice(&0u32.to_le_bytes());
        }
        for (_, _, label) in &ticks.majors {
            out.extend_from_slice(label.as_bytes());
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
        let (chrome, text, legend, colorbar, labels, label_backgrounds, total) =
            read_chrome_trailer(bytes, body)?;
        let (xypl, xyim, xyds) = scene_sidecars_after_chrome(bytes, total)?;
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
        let mut polar = if xypl.is_empty() {
            None
        } else {
            Some(PolarSceneState::from_xypl(xypl, layout)?)
        };
        if let Some(state) = polar.as_mut() {
            state.legend_box = polar_legend_box_after_recut(layout, legend.as_ref());
        }
        let images = parse_xyim(xyim)?;
        if polar.is_some() && !images.is_empty() {
            return Err(SceneError::Length);
        }
        if labels.iter().any(|label| {
            label.x < 0.0
                || label.x > layout.viewport_width
                || label.y < 0.0
                || label.y > layout.viewport_height
        }) || label_backgrounds.iter().flatten().any(|background| {
            background.x < 0.0
                || background.y < 0.0
                || background.x + background.width > layout.viewport_width
                || background.y + background.height > layout.viewport_height
        }) {
            return Err(SceneError::Length);
        }
        if let Some(value) = &legend {
            resolved_legend_bounds(
                layout,
                value,
                polar.as_ref().and_then(|state| state.legend_box),
            )?;
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
            styles.push(EncodedStyle::solid(
                bytes[offset..offset + 4].try_into().expect("bounded style"),
                bytes[offset + 4..offset + 8]
                    .try_into()
                    .expect("bounded style"),
                stroke_width,
            ));
            offset += SCENE_STYLE_RECORD_BYTES;
        }
        let (gradients, marker_glyphs) = apply_style_sidecars(&mut styles, xyds)?;
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
            if !matches!(annotation_tag, 0..=6 | 0x80)
                || (kind == SceneRecordKind::Scatter && symbol > ScatterSymbol::VerticalLine as u8)
                || (kind == SceneRecordKind::Band && BandOutline::from_code(symbol).is_err())
                || (!matches!(kind, SceneRecordKind::Scatter | SceneRecordKind::Band)
                    && symbol != 0)
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
            if kind == SceneRecordKind::Band
                && symbol != BandOutline::None as u8
                && (styles[style_ref].stroke_width == 0.0 || styles[style_ref].stroke[3] == 0)
            {
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
                    && matches!(kind, SceneRecordKind::Rect | SceneRecordKind::Image)
                    && (coordinates[0] > coordinates[2] || coordinates[1] > coordinates[3]))
                || (kind == SceneRecordKind::Image
                    && !images.iter().any(|image| image.stable_id == stable_id))
                || (!visible && coordinates != [0.0; 4])
            {
                return Err(SceneError::NonFinite);
            }
            if visible {
                let record_capacity = match kind {
                    SceneRecordKind::Scatter => 26,
                    SceneRecordKind::Polyline => {
                        27 + styles[style_ref].dash_count as usize * 4
                    }
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
                        21 + if symbol != BandOutline::None as u8 {
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
                    SceneRecordKind::Image => {
                        let image = images
                            .iter()
                            .find(|image| image.stable_id == stable_id)
                            .expect("validated image plane");
                        26usize.saturating_add(image.rgba.len())
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
                5 | 6 if run_end - annotation_cursor == 5 => {
                    if !valid_straight_arrow_run(&records[annotation_cursor..run_end]) {
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
            label_backgrounds,
            styles,
            records,
            raster_mark_capacity,
            polar,
            images,
            gradients,
            marker_glyphs,
        })
    }

    pub fn record_count(&self) -> usize {
        self.records.len()
    }

    pub fn style_count(&self) -> usize {
        self.styles.len()
    }

    fn style_glyph(&self, style_ref: usize) -> Option<&str> {
        self.marker_glyphs
            .get(style_ref)
            .and_then(|value| value.as_deref())
    }

    fn painter_glyph_labels(&self) -> (Vec<SceneLabel>, Vec<Option<SceneLabelBox>>) {
        let mut labels = self.labels.clone();
        let mut backgrounds = self.label_backgrounds.clone();
        for record in &self.records {
            if !record.visible || record.kind != SceneRecordKind::Scatter {
                continue;
            }
            let Some(glyph) = self.style_glyph(record.style_ref) else {
                continue;
            };
            let style = self.styles[record.style_ref];
            let geometry = MarkerGeometry::new(
                ScatterSymbol::from_code(record.symbol),
                record.diameter,
                style.stroke_width,
            );
            labels.push(SceneLabel {
                stable_id: record.stable_id,
                x: record.coordinates[0],
                y: record.coordinates[1],
                font_size: geometry.radius * 2.0,
                rgba: style.fill,
                anchor: 1,
                text: glyph.to_string(),
            });
            backgrounds.push(None);
        }
        (labels, backgrounds)
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
        resolved_legend_bounds(
            self.layout,
            legend,
            self.polar.as_ref().and_then(|state| state.legend_box),
        )
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
                SceneRecordKind::Polyline => push_svg_line_dash(
                    out,
                    x + 8.0,
                    swatch_y,
                    x + 28.0,
                    swatch_y,
                    &rgba_css(style.stroke),
                    style.stroke_width.max(1.0),
                    style.dash_values(),
                    style.linecap,
                ),
                SceneRecordKind::Scatter => {
                    let symbol = ScatterSymbol::from_code(entry.symbol);
                    let geometry = MarkerGeometry::new(symbol, 8.0, style.stroke_width);
                    if let Some(glyph) = self.style_glyph(entry.style_ref) {
                        push_marker_glyph_svg(
                            out,
                            x + 18.0,
                            swatch_y,
                            geometry.radius * 2.0,
                            legend_swatch_rgba(style.fill),
                            style.stroke,
                            geometry.stroke_width,
                            glyph,
                        );
                    } else {
                        push_symbol(out, symbol, x + 18.0, swatch_y, geometry.radius);
                        if symbol.is_line() {
                            out.push_str(" fill=\"none\"");
                        } else {
                            push_paint(out, "fill", legend_swatch_rgba(style.fill), None);
                        }
                        if geometry.stroke_width > 0.0 || symbol.is_line() {
                            push_paint(out, "stroke", style.stroke, None);
                            out.push_str(" stroke-width=\"");
                            push_num(out, geometry.stroke_width);
                            out.push('"');
                        }
                        out.push_str("/>");
                    }
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
        let ticks = resolved_colorbar_ticks(colorbar, (x, y, width, height))
            .expect("validated colorbar tick geometry");
        for (_, position) in &ticks.minors {
            let (x0, y0, x1, y1) = if colorbar.horizontal {
                (*position, y + height, *position, y + height + 3.0)
            } else {
                (x + width, *position, x + width + 3.0, *position)
            };
            out.push_str("<line data-xy-slot=\"colorbar_minor_tick\" x1=\"");
            push_num(out, x0);
            out.push_str("\" y1=\"");
            push_num(out, y0);
            out.push_str("\" x2=\"");
            push_num(out, x1);
            out.push_str("\" y2=\"");
            push_num(out, y1);
            out.push_str("\" stroke=\"");
            out.push_str(&rgba_css(colorbar.text_rgba));
            out.push_str("\" stroke-width=\"1\"/>");
        }
        for (_, position, label) in &ticks.majors {
            let (x0, y0, x1, y1, tx, ty, anchor) = if colorbar.horizontal {
                (
                    *position,
                    y + height,
                    *position,
                    y + height + 6.0,
                    *position,
                    y + height + 17.0,
                    "middle",
                )
            } else {
                (
                    x + width,
                    *position,
                    x + width + 6.0,
                    *position,
                    x + width + 9.0,
                    *position + 4.0,
                    "start",
                )
            };
            out.push_str("<line data-xy-slot=\"colorbar_tick\" x1=\"");
            push_num(out, x0);
            out.push_str("\" y1=\"");
            push_num(out, y0);
            out.push_str("\" x2=\"");
            push_num(out, x1);
            out.push_str("\" y2=\"");
            push_num(out, y1);
            out.push_str("\" stroke=\"");
            out.push_str(&rgba_css(colorbar.text_rgba));
            out.push_str("\" stroke-width=\"1\"/>");
            out.push_str("<text data-xy-slot=\"colorbar_tick\" x=\"");
            push_num(out, tx);
            out.push_str("\" y=\"");
            push_num(out, ty);
            out.push_str("\" text-anchor=\"");
            out.push_str(anchor);
            out.push_str("\" fill=\"");
            out.push_str(&rgba_css(colorbar.text_rgba));
            out.push_str("\" font-size=\"11\">");
            push_escaped_attribute(out, label);
            out.push_str("</text>");
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
        for (label, background) in self.labels.iter().zip(&self.label_backgrounds) {
            if let Some(background) = background {
                out.push_str(
                    "<rect data-xy-slot=\"annotation_label_box\" aria-hidden=\"true\" x=\"",
                );
                push_num(out, background.x);
                out.push_str("\" y=\"");
                push_num(out, background.y);
                out.push_str("\" width=\"");
                push_num(out, background.width);
                out.push_str("\" height=\"");
                push_num(out, background.height);
                out.push_str("\" fill=\"");
                out.push_str(&rgba_css(background.rgba));
                if let Some(border) = &background.border {
                    out.push_str("\" stroke=\"");
                    out.push_str(&rgba_css(border.rgba));
                    out.push_str("\" stroke-width=\"");
                    push_num(out, border.width);
                }
                out.push_str("\"/>");
            }
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
            if label.anchor != 0 {
                out.push_str("\" text-anchor=\"");
                out.push_str(match label.anchor {
                    1 => "middle",
                    2 => "end",
                    _ => unreachable!(),
                });
            }
            out.push_str("\">");
            if label.text.contains('\n') {
                for (index, line) in label.text.split('\n').enumerate() {
                    out.push_str("<tspan x=\"");
                    push_num(out, label.x);
                    out.push('"');
                    if index != 0 {
                        out.push_str(" dy=\"");
                        push_num(out, label.font_size * WRAPPED_LABEL_LINE_HEIGHT);
                        out.push('"');
                    }
                    out.push('>');
                    push_escaped_attribute(out, line);
                    out.push_str("</tspan>");
                }
            } else {
                push_escaped_attribute(out, &label.text);
            }
            out.push_str("</text>");
        }
        out.push_str("</g>");
    }

    fn append_svg_plot_clip(&self, out: &mut String) {
        out.push_str("<defs><clipPath id=\"xy-scene-plot\"");
        if let Some(polar) = &self.polar {
            let cx = polar.cx();
            let cy = polar.cy();
            let radius = polar.radius();
            let inner = polar.inner_radius();
            if polar.full_sector() {
                if inner > 1e-9 {
                    out.push_str(" clip-rule=\"evenodd\"><circle cx=\"");
                    push_num(out, cx);
                    out.push_str("\" cy=\"");
                    push_num(out, cy);
                    out.push_str("\" r=\"");
                    push_num(out, radius);
                    out.push_str("\"/><circle cx=\"");
                    push_num(out, cx);
                    out.push_str("\" cy=\"");
                    push_num(out, cy);
                    out.push_str("\" r=\"");
                    push_num(out, inner);
                    out.push_str("\"/>");
                } else {
                    out.push_str("><circle cx=\"");
                    push_num(out, cx);
                    out.push_str("\" cy=\"");
                    push_num(out, cy);
                    out.push_str("\" r=\"");
                    push_num(out, radius);
                    out.push_str("\"/>");
                }
            } else {
                out.push_str("><path d=\"");
                push_polar_sector_path(out, polar, radius, inner);
                out.push_str("\"/>");
            }
        } else {
            out.push_str("><rect x=\"");
            push_num(out, self.layout.left);
            out.push_str("\" y=\"");
            push_num(out, self.layout.top);
            out.push_str("\" width=\"");
            push_num(out, self.layout.right - self.layout.left);
            out.push_str("\" height=\"");
            push_num(out, self.layout.bottom - self.layout.top);
            out.push_str("\"/>");
        }
        out.push_str("</clipPath>");
        self.append_svg_gradients(out);
        out.push_str("</defs>");
    }

    fn style_gradient(&self, style_ref: usize) -> Option<&AuthoredGradient> {
        self.gradients.get(style_ref).and_then(Option::as_ref)
    }

    fn append_svg_gradients(&self, out: &mut String) {
        for (index, gradient) in self.gradients.iter().enumerate() {
            let Some(gradient) = gradient else {
                continue;
            };
            let (user_space, x1, y1, x2, y2) = gradient_svg_ends(gradient, self.layout);
            out.push_str("<linearGradient id=\"xy-scene-g");
            let _ = write!(out, "{index}");
            out.push('"');
            if user_space {
                out.push_str(" gradientUnits=\"userSpaceOnUse\"");
            }
            out.push_str(" x1=\"");
            push_num(out, x1);
            out.push_str("\" y1=\"");
            push_num(out, y1);
            out.push_str("\" x2=\"");
            push_num(out, x2);
            out.push_str("\" y2=\"");
            push_num(out, y2);
            out.push_str("\">");
            for (t, rgba) in rewrite_transparent_stops(&gradient.stops) {
                out.push_str("<stop offset=\"");
                push_num(out, f64::from(t) * 100.0);
                out.push_str("%\" stop-color=\"rgb(");
                let _ = write!(out, "{},{},{}", rgba[0], rgba[1], rgba[2]);
                out.push_str(")\"");
                if rgba[3] < 255 {
                    out.push_str(" stop-opacity=\"");
                    push_num(out, f64::from(rgba[3]) / 255.0);
                    out.push('"');
                }
                out.push_str("/>");
            }
            out.push_str("</linearGradient>");
        }
    }

    fn push_svg_fill(&self, out: &mut String, style: EncodedStyle, style_ref: usize) {
        if self.style_gradient(style_ref).is_some() {
            out.push_str(" fill=\"url(#xy-scene-g");
            let _ = write!(out, "{style_ref}");
            out.push_str(")\"");
        } else {
            push_paint(out, "fill", style.fill, None);
        }
    }

    fn push_raster_poly_fill(
        &self,
        out: &mut Vec<u8>,
        points: &[(f64, f64)],
        style: EncodedStyle,
        style_ref: usize,
        scale: f64,
    ) -> Result<(), SceneError> {
        if points.len() < 3 {
            return Ok(());
        }
        if let Some(gradient) = self.style_gradient(style_ref) {
            let bbox = points_bbox(points);
            let (g0x, g0y, g1x, g1y) = gradient_raster_line(gradient, bbox, self.layout);
            let stops = rewrite_transparent_stops(&gradient.stops);
            out.push(2); // OP_FILL_POLY_GRAD
            out.extend_from_slice(&(points.len() as u32).to_le_bytes());
            for &(x, y) in points {
                push_raster_f32(out, x, scale)?;
                push_raster_f32(out, y, scale)?;
            }
            push_raster_f32(out, g0x, scale)?;
            push_raster_f32(out, g0y, scale)?;
            push_raster_f32(out, g1x, scale)?;
            push_raster_f32(out, g1y, scale)?;
            out.extend_from_slice(&(stops.len() as u32).to_le_bytes());
            for (t, rgba) in stops {
                out.extend_from_slice(&t.to_le_bytes());
                out.extend_from_slice(&rgba);
            }
            return Ok(());
        }
        out.push(1); // OP_FILL_POLY
        out.extend_from_slice(&(points.len() as u32).to_le_bytes());
        for &(x, y) in points {
            push_raster_f32(out, x, scale)?;
            push_raster_f32(out, y, scale)?;
        }
        out.extend_from_slice(&style.fill);
        Ok(())
    }

    fn append_svg_polar_grid(&self, out: &mut String, x_ticks: &AxisTicks, y_ticks: &AxisTicks) {
        let Some(polar) = &self.polar else {
            return;
        };
        let r_style = self.chrome.y_axis;
        let t_style = self.chrome.x_axis;
        if SceneAxisChromeStyle::visible_stroke(r_style.grid_rgba, r_style.grid_width) {
            for value in &y_ticks.labeled {
                let rn = polar.radius_px(*value);
                if rn <= 0.0 {
                    continue;
                }
                if polar.grid_shape == 1 {
                    let points = polar.polygon_ring(*value, &x_ticks.labeled);
                    if points.len() < 2 {
                        continue;
                    }
                    let tag = if polar.full_sector() {
                        "polygon"
                    } else {
                        "polyline"
                    };
                    out.push_str("<");
                    out.push_str(tag);
                    out.push_str(" data-xy-grid=\"ring\" points=\"");
                    for (i, (x, y)) in points.iter().enumerate() {
                        if i > 0 {
                            out.push(' ');
                        }
                        push_num(out, *x);
                        out.push(',');
                        push_num(out, *y);
                    }
                    out.push_str("\" fill=\"none\" stroke=\"");
                    out.push_str(&rgba_css(r_style.grid_rgba));
                    out.push_str("\" stroke-width=\"");
                    push_num(out, r_style.grid_width);
                    out.push_str("\"/>");
                } else if polar.full_sector() {
                    out.push_str("<circle data-xy-grid=\"ring\" cx=\"");
                    push_num(out, polar.cx());
                    out.push_str("\" cy=\"");
                    push_num(out, polar.cy());
                    out.push_str("\" r=\"");
                    push_num(out, rn);
                    out.push_str("\" fill=\"none\" stroke=\"");
                    out.push_str(&rgba_css(r_style.grid_rgba));
                    out.push_str("\" stroke-width=\"");
                    push_num(out, r_style.grid_width);
                    out.push_str("\"/>");
                } else {
                    let a0 = polar.sector_a0();
                    let a1 = polar.sector_a1();
                    let x0 = polar.cx() + rn * a0.cos();
                    let y0 = polar.cy() - rn * a0.sin();
                    let x1 = polar.cx() + rn * a1.cos();
                    let y1 = polar.cy() - rn * a1.sin();
                    let large = u8::from((a1 - a0).abs() > std::f64::consts::PI);
                    let sweep = u8::from(a1 <= a0);
                    out.push_str("<path data-xy-grid=\"ring\" d=\"M ");
                    push_num(out, x0);
                    out.push(' ');
                    push_num(out, y0);
                    out.push_str(" A ");
                    push_num(out, rn);
                    out.push(' ');
                    push_num(out, rn);
                    out.push_str(" 0 ");
                    out.push(char::from(b'0' + large));
                    out.push(' ');
                    out.push(char::from(b'0' + sweep));
                    out.push(' ');
                    push_num(out, x1);
                    out.push(' ');
                    push_num(out, y1);
                    out.push_str("\" fill=\"none\" stroke=\"");
                    out.push_str(&rgba_css(r_style.grid_rgba));
                    out.push_str("\" stroke-width=\"");
                    push_num(out, r_style.grid_width);
                    out.push_str("\"/>");
                }
            }
        }
        if SceneAxisChromeStyle::visible_stroke(t_style.grid_rgba, t_style.grid_width) {
            for value in &x_ticks.labeled {
                if let Some(((x0, y0), (x1, y1))) = polar.spoke_ends(*value) {
                    out.push_str("<line data-xy-grid=\"spoke\" x1=\"");
                    push_num(out, x0);
                    out.push_str("\" y1=\"");
                    push_num(out, y0);
                    out.push_str("\" x2=\"");
                    push_num(out, x1);
                    out.push_str("\" y2=\"");
                    push_num(out, y1);
                    out.push_str("\" stroke=\"");
                    out.push_str(&rgba_css(t_style.grid_rgba));
                    out.push_str("\" stroke-width=\"");
                    push_num(out, t_style.grid_width);
                    out.push_str("\"/>");
                }
            }
        }
    }

    fn append_svg_polar_frame(&self, out: &mut String, x_ticks: &AxisTicks) {
        let Some(polar) = &self.polar else {
            return;
        };
        let style = self.chrome.x_axis;
        if !SceneAxisChromeStyle::visible_stroke(style.axis_rgba, style.axis_width) {
            return;
        }
        if polar.full_sector() && polar.inner_radius() <= 1e-9 && polar.grid_shape != 1 {
            out.push_str("<circle data-xy-frame=\"polar\" cx=\"");
            push_num(out, polar.cx());
            out.push_str("\" cy=\"");
            push_num(out, polar.cy());
            out.push_str("\" r=\"");
            push_num(out, polar.radius());
            out.push_str("\" fill=\"none\" stroke=\"");
            out.push_str(&rgba_css(style.axis_rgba));
            out.push_str("\" stroke-width=\"");
            push_num(out, style.axis_width);
            out.push_str("\"/>");
            return;
        }
        out.push_str("<path data-xy-frame=\"polar\" d=\"");
        if polar.grid_shape == 1 {
            let points = polar.polygon_ring(polar.r_hi(), &x_ticks.labeled);
            if let Some((x, y)) = points.first() {
                out.push('M');
                push_num(out, *x);
                out.push(' ');
                push_num(out, *y);
                for (x, y) in points.iter().skip(1) {
                    out.push_str(" L ");
                    push_num(out, *x);
                    out.push(' ');
                    push_num(out, *y);
                }
                if polar.full_sector() {
                    out.push_str(" Z");
                }
            }
        } else {
            push_polar_sector_path(out, polar, polar.radius(), polar.inner_radius());
        }
        out.push_str("\" fill=\"none\" stroke=\"");
        out.push_str(&rgba_css(style.axis_rgba));
        out.push_str("\" stroke-width=\"");
        push_num(out, style.axis_width);
        out.push_str("\"/>");
    }

    fn append_svg_polar_tick_labels(
        &self,
        out: &mut String,
        x_ticks: &AxisTicks,
        y_ticks: &AxisTicks,
    ) {
        let Some(polar) = &self.polar else {
            return;
        };
        const POLAR_TICK_GAP: f64 = 8.0;
        const POLAR_RLABEL_DEG: f64 = 22.5;
        let size = self.chrome.label_font_size;
        let theta_style = self.chrome.x_axis;
        let r_style = self.chrome.y_axis;
        if theta_style.tick_label_sides != 0 && theta_style.label_rgba[3] != 0 {
            for (index, value) in x_ticks.labeled.iter().enumerate() {
                let Some((x_rim, y_rim)) = polar.project(*value, polar.r_hi()) else {
                    continue;
                };
                let dx = x_rim - polar.cx();
                let dy = polar.cy() - y_rim;
                let angle = dy.atan2(dx);
                let x = polar.cx() + (polar.radius() + POLAR_TICK_GAP) * angle.cos();
                let y = polar.cy() - (polar.radius() + POLAR_TICK_GAP) * angle.sin();
                let cos_a = angle.cos();
                let sin_a = angle.sin();
                let anchor = if cos_a.abs() < 0.3 {
                    "middle"
                } else if cos_a > 0.0 {
                    "start"
                } else {
                    "end"
                };
                let dy_nudge = if sin_a.abs() < 0.3 {
                    0.0
                } else if sin_a > 0.0 {
                    -0.1 * size
                } else {
                    0.8 * size
                };
                out.push_str("<text data-xy-tick=\"theta\" x=\"");
                push_num(out, x);
                out.push_str("\" y=\"");
                push_num(out, y + dy_nudge);
                out.push_str("\" fill=\"");
                out.push_str(&rgba_css(theta_style.label_rgba));
                out.push_str("\" font-size=\"");
                push_num(out, size);
                out.push_str("\" text-anchor=\"");
                out.push_str(anchor);
                out.push_str("\">");
                push_escaped_attribute(out, &self.axis_tick_label(true, index, *value, x_ticks));
                out.push_str("</text>");
            }
        }
        if r_style.tick_label_sides != 0 && r_style.label_rgba[3] != 0 {
            let mut angle = polar.metrics[polar::METRIC_ZERO]
                + polar.metrics[polar::METRIC_DIR] * POLAR_RLABEL_DEG.to_radians();
            if !polar.full_sector() {
                let a0 = polar.sector_a0();
                let a1 = polar.sector_a1();
                let lo = a0.min(a1);
                let hi = a0.max(a1);
                if angle < lo || angle > hi {
                    angle = (a0 + a1) / 2.0;
                }
            }
            for (index, value) in y_ticks.labeled.iter().enumerate() {
                let rn = polar.radius_px(*value);
                if rn <= 0.0 {
                    continue;
                }
                out.push_str("<text data-xy-tick=\"r\" x=\"");
                push_num(out, polar.cx() + rn * angle.cos() + 3.0);
                out.push_str("\" y=\"");
                push_num(out, polar.cy() - rn * angle.sin() - 3.0);
                out.push_str("\" fill=\"");
                out.push_str(&rgba_css(r_style.label_rgba));
                out.push_str("\" font-size=\"");
                push_num(out, size);
                out.push_str("\" text-anchor=\"start\">");
                push_escaped_attribute(out, &self.axis_tick_label(false, index, *value, y_ticks));
                out.push_str("</text>");
            }
        }
    }

    fn append_svg_grid(&self, out: &mut String, x_ticks: &AxisTicks, y_ticks: &AxisTicks) {
        if self.polar.is_some() {
            self.append_svg_polar_grid(out, x_ticks, y_ticks);
            return;
        }
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
        out.push_str("\">");
        self.append_svg_plot_clip(&mut out);
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
                    if let Some(glyph) = self.style_glyph(record.style_ref) {
                        push_marker_glyph_svg(
                            &mut out,
                            record.coordinates[0],
                            record.coordinates[1],
                            geometry.radius * 2.0,
                            style.fill,
                            style.stroke,
                            geometry.stroke_width,
                            glyph,
                        );
                    } else {
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
                    }
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
                    self.push_svg_fill(&mut out, style, record.style_ref);
                    if style.stroke_width > 0.0 {
                        push_paint(&mut out, "stroke", style.stroke, None);
                        out.push_str(" stroke-width=\"");
                        push_num(&mut out, style.stroke_width);
                        out.push('"');
                    }
                    out.push_str("/>");
                    index += 1;
                }
                SceneRecordKind::Image => {
                    #[cfg(feature = "raster")]
                    if let Some(image) = scene_image_by_id(&self.images, record.stable_id) {
                        if let Ok(png) = crate::png_encode::encode_png(
                            &image.rgba,
                            image.width as usize,
                            image.height as usize,
                            4,
                            crate::png_encode::PNG_MODE_TRUECOLOR,
                            6,
                        ) {
                            let x = record.coordinates[0];
                            let y = record.coordinates[1];
                            let width = record.coordinates[2] - record.coordinates[0];
                            let height = record.coordinates[3] - record.coordinates[1];
                            out.push_str("<image x=\"");
                            push_num(&mut out, x);
                            out.push_str("\" y=\"");
                            push_num(&mut out, y);
                            out.push_str("\" width=\"");
                            push_num(&mut out, width);
                            out.push_str("\" height=\"");
                            push_num(&mut out, height);
                            out.push_str(
                                "\" preserveAspectRatio=\"none\" style=\"image-rendering:pixelated\" href=\"data:image/png;base64,",
                            );
                            out.push_str(&encode_base64(&png));
                            out.push_str("\"/>");
                        }
                    }
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
                        self.push_svg_fill(&mut out, style, record.style_ref);
                        if record.symbol == BandOutline::Perimeter as u8 {
                            push_paint(&mut out, "stroke", style.stroke, None);
                            out.push_str(" stroke-width=\"");
                            push_num(&mut out, style.stroke_width);
                            out.push('"');
                        } else {
                            out.push_str(" stroke=\"none\"");
                        }
                        out.push_str("/>");
                        if record.symbol == BandOutline::Top as u8 {
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
                            out.push('"');
                            out.push_str(" fill=\"none\"");
                            push_paint(&mut out, "stroke", style.stroke, None);
                            out.push_str(" stroke-width=\"");
                            push_num(&mut out, style.stroke_width);
                            out.push_str("\"/>");
                        }
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
                        self.push_svg_fill(&mut out, style, record.style_ref);
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
                    push_svg_dasharray(&mut out, style.dash_values());
                    out.push_str("\" stroke-linecap=\"");
                    out.push_str(linecap_svg_name(style.linecap));
                    out.push_str("\" stroke-linejoin=\"round\"/>");
                }
            }
        }
        out.push_str("</g>");
        if self.polar.is_some() {
            self.append_svg_polar_frame(&mut out, &x_ticks);
            self.append_svg_polar_tick_labels(&mut out, &x_ticks, &y_ticks);
        } else if self.chrome.x_axis.has_visible_axis() || self.chrome.y_axis.has_visible_axis() {
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

    fn append_raster_polar_grid(
        &self,
        out: &mut Vec<u8>,
        scale: f64,
        polar: &PolarSceneState,
        x_ticks: &AxisTicks,
        y_ticks: &AxisTicks,
    ) -> Result<(), SceneError> {
        let r_style = self.chrome.y_axis;
        let t_style = self.chrome.x_axis;
        if SceneAxisChromeStyle::visible_stroke(r_style.grid_rgba, r_style.grid_width) {
            for value in &y_ticks.labeled {
                let points = if polar.grid_shape == 1 {
                    polar.polygon_ring(*value, &x_ticks.labeled)
                } else {
                    polar.ring_points(*value, 64)
                };
                if points.len() < 2 {
                    continue;
                }
                push_raster_polyline(
                    out,
                    &points,
                    r_style.grid_width,
                    r_style.grid_rgba,
                    scale,
                    polar.full_sector(),
                )?;
            }
        }
        if SceneAxisChromeStyle::visible_stroke(t_style.grid_rgba, t_style.grid_width) {
            for value in &x_ticks.labeled {
                if let Some((start, end)) = polar.spoke_ends(*value) {
                    push_raster_stroke(out, [start, end], t_style.grid_width, t_style.grid_rgba, scale)?;
                }
            }
        }
        if SceneAxisChromeStyle::visible_stroke(t_style.axis_rgba, t_style.axis_width) {
            let frame = if polar.grid_shape == 1 {
                polar.polygon_ring(polar.r_hi(), &x_ticks.labeled)
            } else {
                polar.ring_points(polar.r_hi(), 64)
            };
            if frame.len() >= 2 {
                push_raster_polyline(
                    out,
                    &frame,
                    t_style.axis_width,
                    t_style.axis_rgba,
                    scale,
                    polar.full_sector(),
                )?;
            }
        }
        const POLAR_TICK_GAP: f64 = 8.0;
        const POLAR_RLABEL_DEG: f64 = 22.5;
        let size = self.chrome.label_font_size;
        if t_style.tick_label_sides != 0 && t_style.label_rgba[3] != 0 {
            for (index, value) in x_ticks.labeled.iter().enumerate() {
                let Some((x_rim, y_rim)) = polar.project(*value, polar.r_hi()) else {
                    continue;
                };
                let dx = x_rim - polar.cx();
                let dy = polar.cy() - y_rim;
                let angle = dy.atan2(dx);
                let x = polar.cx() + (polar.radius() + POLAR_TICK_GAP) * angle.cos();
                let y = polar.cy() - (polar.radius() + POLAR_TICK_GAP) * angle.sin();
                let cos_a = angle.cos();
                let sin_a = angle.sin();
                let anchor = if cos_a.abs() < 0.3 {
                    1u8
                } else if cos_a > 0.0 {
                    0
                } else {
                    2
                };
                let dy_nudge = if sin_a.abs() < 0.3 {
                    0.0
                } else if sin_a > 0.0 {
                    -0.1 * size
                } else {
                    0.8 * size
                };
                let text = self.axis_tick_label(true, index, *value, x_ticks);
                out.push(6);
                push_raster_f32(out, x, scale)?;
                push_raster_f32(out, y + dy_nudge, scale)?;
                out.push(anchor);
                push_raster_f32(out, size, scale)?;
                out.extend_from_slice(&t_style.label_rgba);
                out.extend_from_slice(&(text.len() as u32).to_le_bytes());
                out.extend_from_slice(text.as_bytes());
            }
        }
        if r_style.tick_label_sides != 0 && r_style.label_rgba[3] != 0 {
            let mut angle = polar.metrics[polar::METRIC_ZERO]
                + polar.metrics[polar::METRIC_DIR] * POLAR_RLABEL_DEG.to_radians();
            if !polar.full_sector() {
                let a0 = polar.sector_a0();
                let a1 = polar.sector_a1();
                let lo = a0.min(a1);
                let hi = a0.max(a1);
                if angle < lo || angle > hi {
                    angle = (a0 + a1) / 2.0;
                }
            }
            for (index, value) in y_ticks.labeled.iter().enumerate() {
                let rn = polar.radius_px(*value);
                if rn <= 0.0 {
                    continue;
                }
                let text = self.axis_tick_label(false, index, *value, y_ticks);
                out.push(6);
                push_raster_f32(out, polar.cx() + rn * angle.cos() + 3.0, scale)?;
                push_raster_f32(out, polar.cy() - rn * angle.sin() - 3.0, scale)?;
                out.push(0);
                push_raster_f32(out, size, scale)?;
                out.extend_from_slice(&r_style.label_rgba);
                out.extend_from_slice(&(text.len() as u32).to_le_bytes());
                out.extend_from_slice(text.as_bytes());
            }
        }
        Ok(())
    }

    #[inline(never)]
    fn append_raster_grid(
        &self,
        out: &mut Vec<u8>,
        scale: f64,
        x_ticks: &AxisTicks,
        y_ticks: &AxisTicks,
    ) -> Result<(), SceneError> {
        if let Some(polar) = &self.polar {
            return self.append_raster_polar_grid(out, scale, polar, x_ticks, y_ticks);
        }
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
        if self.polar.is_some() {
            return Ok(());
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
        let label_capacity = self.labels.iter().zip(&self.label_backgrounds).fold(
            0usize,
            |total, (label, background)| {
                total
                    .saturating_add(30)
                    .saturating_add(label.text.len())
                    .saturating_add(usize::from(background.is_some()).saturating_mul(41))
                    .saturating_add(
                        usize::from(
                            background
                                .as_ref()
                                .and_then(|value| value.border.as_ref())
                                .is_some(),
                        )
                        .saturating_mul(59),
                    )
            },
        );
        let colorbar_capacity = self.colorbar.as_ref().map_or(0, |value| {
            let bands = value
                .stops
                .len()
                .saturating_sub(1)
                // Raster polygon: opcode + vertex count + four (x, y) f32
                // pairs + RGBA = 41 bytes per literal color band.
                .saturating_mul(41)
                .saturating_add(value.title.len())
                .saturating_add(64);
            // Each resolved major emits a stroke plus bounded built-in text;
            // four minors per adjacent major pair emit strokes. Reserve the
            // product ceiling so the append-only display list never reallocates
            // or rejects a valid bounded XYCB v2 record after validation.
            bands
                .saturating_add(MAX_SCENE_COLORBAR_TICKS.saturating_mul(96))
                .saturating_add(
                    MAX_SCENE_COLORBAR_TICKS
                        .saturating_sub(1)
                        .saturating_mul(4)
                        .saturating_mul(35),
                )
        });
        let polar_ring_capacity = if self.polar.is_some() {
            // Polar rings and the outer frame are 64-vertex closed polylines
            // (~560 bytes), not the 35-byte two-point strokes cartesian grid
            // capacity assumes. Spokes stay inside the existing stroke budget.
            y_ticks
                .labeled
                .len()
                .saturating_add(1)
                .saturating_mul(560)
        } else {
            0
        };
        self.raster_mark_capacity
            .saturating_add(chrome_capacity)
            .saturating_add(polar_ring_capacity)
            .saturating_add(legend_capacity)
            .saturating_add(colorbar_capacity)
            .saturating_add(label_capacity)
    }

    fn append_raster_labels(&self, out: &mut Vec<u8>, scale: f64) -> Result<(), SceneError> {
        for (label, background) in self.labels.iter().zip(&self.label_backgrounds) {
            if let Some(background) = background {
                out.push(1);
                out.extend_from_slice(&4u32.to_le_bytes());
                for (x, y) in [
                    (background.x, background.y),
                    (background.x + background.width, background.y),
                    (
                        background.x + background.width,
                        background.y + background.height,
                    ),
                    (background.x, background.y + background.height),
                ] {
                    push_raster_f32(out, x, scale)?;
                    push_raster_f32(out, y, scale)?;
                }
                out.extend_from_slice(&background.rgba);
                if let Some(border) = &background.border {
                    // Repeat the rectangle as a Rust-owned closed polyline for
                    // the native command consumer; no host derives geometry.
                    out.push(3); // OP_STROKE
                    out.extend_from_slice(&5u32.to_le_bytes());
                    for (x, y) in [
                        (background.x, background.y),
                        (background.x + background.width, background.y),
                        (
                            background.x + background.width,
                            background.y + background.height,
                        ),
                        (background.x, background.y + background.height),
                        (background.x, background.y),
                    ] {
                        push_raster_f32(out, x, scale)?;
                        push_raster_f32(out, y, scale)?;
                    }
                    push_raster_f32(out, border.width, scale)?;
                    out.extend_from_slice(&border.rgba);
                    out.push(1); // closed
                    out.extend_from_slice(&0u32.to_le_bytes()); // no dash
                    out.push(1); // round cap
                }
            }
            for (index, line) in label.text.split('\n').enumerate() {
                out.push(6);
                push_raster_f32(out, label.x, scale)?;
                push_raster_f32(
                    out,
                    label.y + index as f64 * label.font_size * WRAPPED_LABEL_LINE_HEIGHT,
                    scale,
                )?;
                out.push(label.anchor);
                push_raster_f32(out, label.font_size, scale)?;
                out.extend_from_slice(&label.rgba);
                out.extend_from_slice(&(line.len() as u32).to_le_bytes());
                out.extend_from_slice(line.as_bytes());
            }
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
                SceneRecordKind::Polyline => push_raster_stroke_dash(
                    out,
                    [(x + 8.0, swatch_y), (x + 28.0, swatch_y)],
                    style.stroke_width.max(1.0),
                    style.stroke,
                    scale,
                    style.dash_values(),
                    style.linecap,
                )?,
                SceneRecordKind::Scatter => {
                    let geometry = MarkerGeometry::new(
                        ScatterSymbol::from_code(entry.symbol),
                        8.0,
                        style.stroke_width,
                    );
                    if let Some(glyph) = self.style_glyph(entry.style_ref) {
                        let font_size = geometry.radius * 2.0;
                        out.push(6);
                        push_raster_f32(out, x + 18.0, scale)?;
                        push_raster_f32(out, swatch_y + font_size * 0.34, scale)?;
                        out.push(1);
                        push_raster_f32(out, font_size, scale)?;
                        out.extend_from_slice(&legend_swatch_rgba(style.fill));
                        out.extend_from_slice(&(glyph.len() as u32).to_le_bytes());
                        out.extend_from_slice(glyph.as_bytes());
                    } else {
                        out.push(4);
                        push_raster_f32(out, x + 18.0, scale)?;
                        push_raster_f32(out, swatch_y, scale)?;
                        push_raster_f32(out, geometry.radius, scale)?;
                        out.push(entry.symbol);
                        out.extend_from_slice(&legend_swatch_rgba(style.fill));
                        push_raster_f32(out, geometry.stroke_width, scale)?;
                        out.extend_from_slice(&style.stroke);
                    }
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
        let ticks = resolved_colorbar_ticks(colorbar, (x, y, width, height))?;
        for (_, position) in &ticks.minors {
            let points = if colorbar.horizontal {
                [(*position, y + height), (*position, y + height + 3.0)]
            } else {
                [(x + width, *position), (x + width + 3.0, *position)]
            };
            push_raster_stroke(out, points, 1.0, colorbar.text_rgba, scale)?;
        }
        for (_, position, label) in &ticks.majors {
            let (points, text_x, text_y, anchor) = if colorbar.horizontal {
                (
                    [(*position, y + height), (*position, y + height + 6.0)],
                    *position,
                    y + height + 17.0,
                    1,
                )
            } else {
                (
                    [(x + width, *position), (x + width + 6.0, *position)],
                    x + width + 9.0,
                    *position + 4.0,
                    0,
                )
            };
            push_raster_stroke(out, points, 1.0, colorbar.text_rgba, scale)?;
            out.push(6);
            push_raster_f32(out, text_x, scale)?;
            push_raster_f32(out, text_y, scale)?;
            out.push(anchor);
            push_raster_f32(out, 11.0, scale)?;
            out.extend_from_slice(&colorbar.text_rgba);
            out.extend_from_slice(&(label.len() as u32).to_le_bytes());
            out.extend_from_slice(label.as_bytes());
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
                    if let Some(glyph) = self.style_glyph(record.style_ref) {
                        let font_size = geometry.radius * 2.0;
                        out.push(6);
                        push_raster_f32(out, record.coordinates[0], scale)?;
                        push_raster_f32(
                            out,
                            record.coordinates[1] + font_size * 0.34,
                            scale,
                        )?;
                        out.push(1);
                        push_raster_f32(out, font_size, scale)?;
                        out.extend_from_slice(&style.fill);
                        out.extend_from_slice(&(glyph.len() as u32).to_le_bytes());
                        out.extend_from_slice(glyph.as_bytes());
                    } else {
                        out.push(4);
                        push_raster_f32(out, record.coordinates[0], scale)?;
                        push_raster_f32(out, record.coordinates[1], scale)?;
                        push_raster_f32(out, geometry.radius, scale)?;
                        out.push(record.symbol);
                        out.extend_from_slice(&style.fill);
                        push_raster_f32(out, geometry.stroke_width, scale)?;
                        out.extend_from_slice(&style.stroke);
                    }
                    index += 1;
                }
                SceneRecordKind::Rect => {
                    let points = [
                        (record.coordinates[0], record.coordinates[1]),
                        (record.coordinates[2], record.coordinates[1]),
                        (record.coordinates[2], record.coordinates[3]),
                        (record.coordinates[0], record.coordinates[3]),
                    ];
                    self.push_raster_poly_fill(
                        out,
                        &points,
                        style,
                        record.style_ref,
                        scale,
                    )?;
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
                SceneRecordKind::Image => {
                    if let Some(image) = scene_image_by_id(&self.images, record.stable_id) {
                        out.push(5); // OP_IMAGE
                        push_raster_f32(out, record.coordinates[0], scale)?;
                        push_raster_f32(out, record.coordinates[1], scale)?;
                        push_raster_f32(
                            out,
                            record.coordinates[2] - record.coordinates[0],
                            scale,
                        )?;
                        push_raster_f32(
                            out,
                            record.coordinates[3] - record.coordinates[1],
                            scale,
                        )?;
                        out.extend_from_slice(&image.width.to_le_bytes());
                        out.extend_from_slice(&image.height.to_le_bytes());
                        out.push(1); // nearest / pixelated
                        out.extend_from_slice(&image.rgba);
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
                        let mut points = Vec::with_capacity(run.len() * 2);
                        for point in run {
                            points.push((point.coordinates[0], point.coordinates[1]));
                        }
                        for point in run.iter().rev() {
                            points.push((point.coordinates[2], point.coordinates[3]));
                        }
                        self.push_raster_poly_fill(out, &points, style, style_ref, scale)?;
                        if record.symbol != BandOutline::None as u8 {
                            let perimeter = record.symbol == BandOutline::Perimeter as u8;
                            let stroke_count = if perimeter { count } else { run.len() as u32 };
                            out.push(3); // OP_STROKE
                            out.extend_from_slice(&stroke_count.to_le_bytes());
                            for point in run {
                                push_raster_f32(out, point.coordinates[0], scale)?;
                                push_raster_f32(out, point.coordinates[1], scale)?;
                            }
                            if perimeter {
                                for point in run.iter().rev() {
                                    push_raster_f32(out, point.coordinates[2], scale)?;
                                    push_raster_f32(out, point.coordinates[3], scale)?;
                                }
                            }
                            push_raster_f32(out, style.stroke_width, scale)?;
                            out.extend_from_slice(&style.stroke);
                            out.push(u8::from(perimeter)); // closed only for perimeter
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
                        let points: Vec<(f64, f64)> = run
                            .iter()
                            .map(|point| (point.coordinates[0], point.coordinates[1]))
                            .collect();
                        self.push_raster_poly_fill(out, &points, style, style_ref, scale)?;
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
                        push_raster_dash(out, style.dash_values(), scale)?;
                        out.push(style.linecap);
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
                    if self.style_glyph(record.style_ref).is_some() {
                        continue;
                    }
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
                SceneRecordKind::Image => continue,
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
        let (paint_labels, paint_backgrounds) = self.painter_glyph_labels();
        let label_bytes = encode_scene_labels(&paint_labels, &paint_backgrounds)?;
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
            out[descriptor + 2] = if group.annotation_tag <= 6 {
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

fn push_marker_glyph_svg(
    out: &mut String,
    cx: f64,
    cy: f64,
    font_size: f64,
    fill: [u8; 4],
    stroke: [u8; 4],
    stroke_width: f64,
    glyph: &str,
) {
    out.push_str("<text x=\"");
    push_num(out, cx);
    out.push_str("\" y=\"");
    push_num(out, cy);
    out.push_str("\" font-family=\"DejaVu Sans\" font-size=\"");
    push_num(out, font_size);
    out.push_str("\" text-anchor=\"middle\" dominant-baseline=\"central\"");
    push_paint(out, "fill", fill, None);
    if stroke_width > 0.0 {
        push_paint(out, "stroke", stroke, None);
        out.push_str(" stroke-width=\"");
        push_num(out, stroke_width);
        out.push('"');
    }
    out.push('>');
    push_escaped_attribute(out, glyph);
    out.push_str("</text>");
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
    pub x_format: Option<&'a str>,
    pub y_kind: ScaleKind,
    pub y_lo: f64,
    pub y_hi: f64,
    pub y_constant: f64,
    pub y_mask_nonpositive: bool,
    pub y_format: Option<&'a str>,
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
        x_format,
        y_kind,
        y_lo,
        y_hi,
        y_constant,
        y_mask_nonpositive,
        y_format,
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
            &format_numeric_tick(*value, y_ticks.step, y_kind, y_format),
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
        let first_w = text_advance(
            &format_numeric_tick(first, x_ticks.step, x_kind, x_format),
            LABEL_FONT_PX,
        );
        let last_w = text_advance(
            &format_numeric_tick(last, x_ticks.step, x_kind, x_format),
            LABEL_FONT_PX,
        );
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

    fn test_linear_x_scale() -> AxisScale {
        AxisScale::new(ScaleKind::Linear, 0.0, 10.0, 0.0, 100.0, 1.0, false).unwrap()
    }

    fn test_linear_y_scale() -> AxisScale {
        AxisScale::new(ScaleKind::Linear, 0.0, 10.0, 100.0, 0.0, 1.0, false).unwrap()
    }

    // Keep every borrowed column explicit so this fixture mirrors the Scene ABI.
    #[allow(clippy::too_many_arguments)]
    fn compact_step_input<'a>(
        kinds: &'a [u8],
        ids: &'a [u64],
        styles: &'a [u32],
        zeros: &'a [f64],
        symbols: &'a [u8],
        x: &'a [f64],
        y: &'a [f64],
        modes: &'a [u8],
    ) -> SceneExpansionInput<'a> {
        SceneExpansionInput {
            kinds,
            stable_ids: ids,
            style_refs: styles,
            diameter: zeros,
            symbols,
            x0: x,
            y0: y,
            x1: zeros,
            y1: zeros,
            expansion_modes: modes,
        }
    }

    #[test]
    fn compact_steps_expand_in_exact_pre_mid_post_order() {
        let kinds = [1u8; 3];
        let ids = [42u64; 3];
        let styles = [7u32; 3];
        let zeros = [0.0; 3];
        let symbols = [0u8; 3];
        let x = [0.0, 2.0, 4.0];
        let y = [10.0, 20.0, 30.0];
        let cases = [
            (
                1u8,
                vec![
                    (0.0, 10.0),
                    (0.0, 20.0),
                    (2.0, 20.0),
                    (2.0, 30.0),
                    (4.0, 30.0),
                ],
            ),
            (
                2u8,
                vec![
                    (0.0, 10.0),
                    (1.0, 10.0),
                    (1.0, 20.0),
                    (2.0, 20.0),
                    (3.0, 20.0),
                    (3.0, 30.0),
                    (4.0, 30.0),
                ],
            ),
            (
                3u8,
                vec![
                    (0.0, 10.0),
                    (2.0, 10.0),
                    (2.0, 20.0),
                    (4.0, 20.0),
                    (4.0, 30.0),
                ],
            ),
        ];
        for (mode, expected) in cases {
            let modes = [mode; 3];
            let expanded = expand_scene_records(
                compact_step_input(&kinds, &ids, &styles, &zeros, &symbols, &x, &y, &modes),
                test_linear_x_scale(),
                test_linear_y_scale(),
            )
            .unwrap();
            assert_eq!(
                expanded.x0.into_iter().zip(expanded.y0).collect::<Vec<_>>(),
                expected
            );
            assert!(expanded.kinds.iter().all(|kind| *kind == 1));
            assert!(expanded.stable_ids.iter().all(|id| *id == 42));
            assert!(expanded.style_refs.iter().all(|style| *style == 7));
        }
    }

    #[test]
    fn curve_flatten_expansion_emits_expected_vertex_count() {
        let kinds = [1u8; 3];
        let ids = [42u64; 3];
        let styles = [7u32; 3];
        let zeros = [0.0; 3];
        let symbols = [0u8; 3];
        let x = [0.0, 1.0, 2.0];
        let y = [0.0, 1.0, 0.5];
        let modes = [SceneExpansionMode::CurveFlatten as u8; 3];
        let expanded = expand_scene_records(
            compact_step_input(&kinds, &ids, &styles, &zeros, &symbols, &x, &y, &modes),
            test_linear_x_scale(),
            test_linear_y_scale(),
        )
        .unwrap();
        let expected = 1 + (x.len() - 1) * SCENE_CURVE_STEPS;
        assert_eq!(expanded.kinds.len(), expected);
        assert_eq!(expanded.x0[0], 0.0);
        assert_eq!(expanded.y0[0], 0.0);
        assert_eq!(expanded.x0[SCENE_CURVE_STEPS], 1.0);
        assert_eq!(expanded.y0[SCENE_CURVE_STEPS], 1.0);
        assert_eq!(expanded.x0[expected - 1], 2.0);
        assert_eq!(expanded.y0[expected - 1], 0.5);
        assert!(expanded.kinds.iter().all(|kind| *kind == 1));
        assert!(expanded.stable_ids.iter().all(|id| *id == 42));

        let short = expand_scene_records(
            compact_step_input(
                &[1, 1],
                &[9, 9],
                &[0, 0],
                &[0.0, 0.0],
                &[0, 0],
                &[0.0, 1.0],
                &[0.0, 1.0],
                &[
                    SceneExpansionMode::CurveFlatten as u8,
                    SceneExpansionMode::CurveFlatten as u8,
                ],
            ),
            test_linear_x_scale(),
            test_linear_y_scale(),
        )
        .unwrap();
        assert_eq!(short.x0, [0.0, 1.0]);
        assert_eq!(short.y0, [0.0, 1.0]);
    }

    fn compact_band_input<'a>(
        kinds: &'a [u8],
        ids: &'a [u64],
        styles: &'a [u32],
        zeros: &'a [f64],
        symbols: &'a [u8],
        x: &'a [f64],
        y: &'a [f64],
        base: &'a [f64],
        modes: &'a [u8],
    ) -> SceneExpansionInput<'a> {
        SceneExpansionInput {
            kinds,
            stable_ids: ids,
            style_refs: styles,
            diameter: zeros,
            symbols,
            x0: x,
            y0: y,
            x1: x,
            y1: base,
            expansion_modes: modes,
        }
    }

    #[test]
    fn band_flatten_expansion_emits_expected_vertex_count() {
        let kinds = [3u8; 3];
        let ids = [42u64; 3];
        let styles = [7u32; 3];
        let zeros = [0.0; 3];
        let symbols = [BandOutline::Top as u8; 3];
        let x = [0.0, 1.0, 2.0];
        let y = [0.0, 1.0, 0.5];
        let base = [0.0, 0.0, 0.0];
        let modes = [SceneExpansionMode::BandFlatten as u8; 3];
        let expanded = expand_scene_records(
            compact_band_input(&kinds, &ids, &styles, &zeros, &symbols, &x, &y, &base, &modes),
            test_linear_x_scale(),
            test_linear_y_scale(),
        )
        .unwrap();
        let expected = 1 + (x.len() - 1) * SCENE_CURVE_STEPS;
        assert_eq!(expanded.kinds.len(), expected);
        assert_eq!(expanded.x0[0], 0.0);
        assert_eq!(expanded.y0[0], 0.0);
        assert_eq!(expanded.x1[0], 0.0);
        assert_eq!(expanded.y1[0], 0.0);
        assert_eq!(expanded.x0[SCENE_CURVE_STEPS], 1.0);
        assert_eq!(expanded.y0[SCENE_CURVE_STEPS], 1.0);
        assert_eq!(expanded.x0[expected - 1], 2.0);
        assert_eq!(expanded.y0[expected - 1], 0.5);
        assert!(expanded.kinds.iter().all(|kind| *kind == 3));
        assert!(expanded.stable_ids.iter().all(|id| *id == 42));
        assert!(expanded.symbols.iter().all(|symbol| *symbol == BandOutline::Top as u8));
        assert!(expanded
            .x0
            .iter()
            .zip(expanded.x1.iter())
            .all(|(left, right)| left == right));

        let short = expand_scene_records(
            compact_band_input(
                &[3, 3],
                &[9, 9],
                &[0, 0],
                &[0.0, 0.0],
                &[BandOutline::Top as u8, BandOutline::Top as u8],
                &[0.0, 1.0],
                &[0.0, 1.0],
                &[0.0, 0.0],
                &[
                    SceneExpansionMode::BandFlatten as u8,
                    SceneExpansionMode::BandFlatten as u8,
                ],
            ),
            test_linear_x_scale(),
            test_linear_y_scale(),
        )
        .unwrap();
        assert_eq!(short.x0, [0.0, 1.0]);
        assert_eq!(short.y0, [0.0, 1.0]);
        assert_eq!(short.y1, [0.0, 0.0]);
        assert!(short.kinds.iter().all(|kind| *kind == 3));
    }

    #[test]
    fn band_step_mid_expansion_emits_expected_vertices() {
        let kinds = [3u8; 3];
        let ids = [42u64; 3];
        let styles = [7u32; 3];
        let zeros = [0.0; 3];
        let symbols = [BandOutline::Top as u8; 3];
        let x = [0.0, 1.0, 2.0];
        let y = [0.0, 1.0, 0.5];
        let base = [0.0, 0.0, 0.0];
        let modes = [SceneExpansionMode::Mid as u8; 3];
        let expanded = expand_scene_records(
            compact_band_input(&kinds, &ids, &styles, &zeros, &symbols, &x, &y, &base, &modes),
            test_linear_x_scale(),
            test_linear_y_scale(),
        )
        .unwrap();
        assert_eq!(expanded.kinds.len(), 7);
        assert_eq!(expanded.x0, [0.0, 0.5, 0.5, 1.0, 1.5, 1.5, 2.0]);
        assert_eq!(expanded.y0, [0.0, 0.0, 1.0, 1.0, 1.0, 0.5, 0.5]);
        assert_eq!(expanded.y1, [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]);
        assert!(expanded.kinds.iter().all(|kind| *kind == 3));
        assert!(expanded
            .x0
            .iter()
            .zip(expanded.x1.iter())
            .all(|(left, right)| left == right));
        assert!(expanded
            .symbols
            .iter()
            .all(|symbol| *symbol == BandOutline::Top as u8));
    }

    #[test]
    fn compact_steps_preserve_empty_singleton_and_distinct_runs() {
        let empty = expand_scene_records(
            SceneExpansionInput {
                kinds: &[],
                stable_ids: &[],
                style_refs: &[],
                diameter: &[],
                symbols: &[],
                x0: &[],
                y0: &[],
                x1: &[],
                y1: &[],
                expansion_modes: &[],
            },
            test_linear_x_scale(),
            test_linear_y_scale(),
        )
        .unwrap();
        assert!(empty.kinds.is_empty());

        let singleton = expand_scene_records(
            compact_step_input(&[1], &[9], &[0], &[0.0], &[0], &[3.0], &[4.0], &[2]),
            test_linear_x_scale(),
            test_linear_y_scale(),
        )
        .unwrap();
        assert_eq!(singleton.x0, [3.0]);
        assert_eq!(singleton.y0, [4.0]);

        let separate = expand_scene_records(
            compact_step_input(
                &[1, 1],
                &[9, 10],
                &[0, 0],
                &[0.0, 0.0],
                &[0, 0],
                &[3.0, 5.0],
                &[4.0, 6.0],
                &[2, 2],
            ),
            test_linear_x_scale(),
            test_linear_y_scale(),
        )
        .unwrap();
        assert_eq!(separate.x0, [3.0, 5.0]);
        assert_eq!(separate.stable_ids, [9, 10]);
    }

    #[test]
    fn compact_steps_fail_closed_for_malformed_nonfinite_and_overflow() {
        let base = |kinds: &[u8], styles: &[u32], x: &[f64], modes: &[u8]| {
            let len = kinds.len();
            let ids = vec![1u64; len];
            let zeros = vec![0.0; len];
            let symbols = vec![0u8; len];
            let y = vec![1.0; len];
            expand_scene_records(
                compact_step_input(kinds, &ids, styles, &zeros, &symbols, x, &y, modes),
                test_linear_x_scale(),
                test_linear_y_scale(),
            )
        };
        assert_eq!(base(&[0], &[0], &[1.0], &[1]), Err(SceneError::Length));
        assert_eq!(base(&[1], &[0], &[1.0], &[4]), Err(SceneError::Length));
        assert_eq!(base(&[1], &[0], &[1.0], &[12]), Err(SceneError::Length));
        assert_eq!(base(&[1], &[0], &[1.0], &[13]), Err(SceneError::Length));
        assert_eq!(
            base(&[1, 1], &[0, 1], &[1.0, 2.0], &[1, 1]),
            Err(SceneError::Length)
        );
        assert_eq!(
            base(&[1, 1], &[0, 0], &[1.0, 2.0], &[1, 3]),
            Err(SceneError::Length)
        );
        assert_eq!(
            base(&[1, 1], &[0, 0], &[1.0, 2.0], &[0, 1]),
            Err(SceneError::Length)
        );
        assert_eq!(
            base(&[1], &[0], &[f64::NAN], &[1]),
            Err(SceneError::NonFinite)
        );
        assert_eq!(
            base(&[1, 1], &[0, 0], &[f64::MAX, f64::MAX], &[2, 2]),
            Err(SceneError::NonFinite)
        );
        let kinds = [1u8];
        let ids = [1u64];
        let styles = [0u32];
        let zeros = [0.0f64];
        let symbols = [0u8];
        let values = [1.0f64];
        let modes = [1u8];
        let nonzero = [2.0f64];
        let rejected_reserved = |x1: &[f64], y1: &[f64]| {
            let mut input = compact_step_input(
                &kinds, &ids, &styles, &zeros, &symbols, &values, &values, &modes,
            );
            input.x1 = x1;
            input.y1 = y1;
            expand_scene_records(input, test_linear_x_scale(), test_linear_y_scale())
        };
        assert_eq!(rejected_reserved(&nonzero, &zeros), Err(SceneError::Length));
        assert_eq!(rejected_reserved(&zeros, &nonzero), Err(SceneError::Length));
        let nonfinite = [f64::NAN];
        assert_eq!(
            rejected_reserved(&nonfinite, &zeros),
            Err(SceneError::NonFinite)
        );
    }

    #[test]
    fn compact_step_expansion_enforces_the_canonical_record_budget() {
        let len = MAX_SCENE_MARKS / 3 + 2;
        let kinds = vec![1u8; len];
        let ids = vec![1u64; len];
        let styles = vec![0u32; len];
        let zeros = vec![0.0; len];
        let symbols = vec![0u8; len];
        let modes = vec![2u8; len];
        assert_eq!(
            expand_scene_records(
                compact_step_input(&kinds, &ids, &styles, &zeros, &symbols, &zeros, &zeros, &modes),
                test_linear_x_scale(),
                test_linear_y_scale(),
            ),
            Err(SceneError::Limit)
        );
    }

    fn compact_hex_input<'a>(
        ids: &'a [u64],
        styles: &'a [u32],
        x0: &'a [f64],
        y0: &'a [f64],
        x1: &'a [f64],
        y1: &'a [f64],
        modes: &'a [u8],
    ) -> SceneExpansionInput<'a> {
        SceneExpansionInput {
            kinds: &[4],
            stable_ids: ids,
            style_refs: styles,
            diameter: &[0.0],
            symbols: &[0],
            x0,
            y0,
            x1,
            y1,
            expansion_modes: modes,
        }
    }

    #[test]
    fn compact_hex_cell_expands_the_canonical_pointy_top_ring() {
        let expanded = expand_scene_records(
            compact_hex_input(&[42], &[7], &[10.0], &[20.0], &[6.0], &[12.0], &[5]),
            test_linear_x_scale(),
            test_linear_y_scale(),
        )
        .unwrap();
        let expected: Vec<(f64, f64)> = SCENE_HEXBIN_RING
            .iter()
            .map(|(rx, ry)| (10.0 + rx * 6.0, 20.0 + ry * 12.0))
            .collect();
        assert_eq!(
            expanded.x0.into_iter().zip(expanded.y0).collect::<Vec<_>>(),
            expected
        );
        assert!(expanded.kinds.iter().all(|kind| *kind == 4));
        assert!(expanded.stable_ids.iter().all(|id| *id == 42));
        assert!(expanded.x1.iter().all(|value| *value == 0.0));
        assert!(expanded.y1.iter().all(|value| *value == 0.0));
    }

    #[test]
    fn compact_hex_cell_rejects_shared_identity_and_nonpositive_pitch() {
        let kinds = [4u8, 4];
        let ids = [1u64, 1];
        let styles = [0u32, 0];
        let zeros = [0.0, 0.0];
        let symbols = [0u8, 0];
        let x0 = [1.0, 2.0];
        let y0 = [3.0, 4.0];
        let pitch = [1.0, 1.0];
        let modes = [5u8, 5];
        let shared = SceneExpansionInput {
            kinds: &kinds,
            stable_ids: &ids,
            style_refs: &styles,
            diameter: &zeros,
            symbols: &symbols,
            x0: &x0,
            y0: &y0,
            x1: &pitch,
            y1: &pitch,
            expansion_modes: &modes,
        };
        assert_eq!(
            expand_scene_records(shared, test_linear_x_scale(), test_linear_y_scale()),
            Err(SceneError::Length)
        );
        assert_eq!(
            expand_scene_records(
                compact_hex_input(&[1], &[0], &[0.0], &[0.0], &[0.0], &[1.0], &[5]),
                test_linear_x_scale(),
                test_linear_y_scale(),
            ),
            Err(SceneError::Length)
        );
    }

    #[test]
    fn compact_hex_cell_interns_named_colormap_fills() {
        let paint = xyhp_named(
            0,
            1,
            2,
            f64::NAN,
            f64::NAN,
            &[0.0, 1.0],
            "binary",
        );
        let kinds = [4u8, 4];
        let ids = [0u64, 1];
        let styles = [0u32, 0];
        let zeros = [0.0, 0.0];
        let symbols = [0u8, 0];
        let x0 = [10.0, 20.0];
        let y0 = [30.0, 40.0];
        let pitch = [1.0, 1.0];
        let modes = [5u8, 5];
        let (expanded, painted, _images) = expand_scene_records_painted(
            SceneExpansionInput {
                kinds: &kinds,
                stable_ids: &ids,
                style_refs: &styles,
                diameter: &zeros,
                symbols: &symbols,
                x0: &x0,
                y0: &y0,
                x1: &pitch,
                y1: &pitch,
                expansion_modes: &modes,
            },
            test_linear_x_scale(),
            test_linear_y_scale(),
            &[255, 0, 0, 200],
            &[0, 0, 0, 0],
            &[0.0],
            &paint,
            false,
        )
        .unwrap();
        let styles = painted.unwrap();
        assert_eq!(expanded.style_refs, [1, 1, 1, 1, 1, 1, 2, 2, 2, 2, 2, 2]);
        assert_eq!(&styles.fill_rgba[4..8], &[255, 255, 255, 200]);
        assert_eq!(&styles.fill_rgba[8..12], &[0, 0, 0, 200]);
        assert!(expanded.kinds.iter().all(|kind| *kind == 4));
    }

    #[test]
    fn compact_heatmap_lattice_emits_row_major_rects() {
        let kinds = [2u8, 2];
        let ids = [9u64, 9];
        let styles = [3u32, 3];
        let diameter = [2.0, 3.0];
        let symbols = [0u8, 0];
        let x0 = [0.0, 0.0];
        let y0 = [10.0, 0.0];
        let x1 = [6.0, 0.0];
        let y1 = [14.0, 0.0];
        let modes = [6u8, 6];
        let expanded = expand_scene_records(
            SceneExpansionInput {
                kinds: &kinds,
                stable_ids: &ids,
                style_refs: &styles,
                diameter: &diameter,
                symbols: &symbols,
                x0: &x0,
                y0: &y0,
                x1: &x1,
                y1: &y1,
                expansion_modes: &modes,
            },
            test_linear_x_scale(),
            test_linear_y_scale(),
        )
        .unwrap();
        assert_eq!(expanded.kinds.len(), 6);
        assert_eq!(expanded.x0, [0.0, 2.0, 4.0, 0.0, 2.0, 4.0]);
        assert_eq!(expanded.y0, [10.0, 10.0, 10.0, 12.0, 12.0, 12.0]);
        assert_eq!(expanded.x1, [2.0, 4.0, 6.0, 2.0, 4.0, 6.0]);
        assert_eq!(expanded.y1, [12.0, 12.0, 12.0, 14.0, 14.0, 14.0]);
        assert!(expanded.stable_ids.iter().all(|id| *id == 9));
        assert!(expanded.style_refs.iter().all(|style| *style == 3));
    }

    fn xyhp_rgba(stable_id: u64, rows: u32, cols: u32, rgba: &[u8]) -> Vec<u8> {
        let mut out = Vec::new();
        out.extend_from_slice(b"XYHP");
        out.extend_from_slice(&1u32.to_le_bytes());
        out.extend_from_slice(&1u32.to_le_bytes());
        out.extend_from_slice(&0u32.to_le_bytes());
        out.extend_from_slice(&stable_id.to_le_bytes());
        out.extend_from_slice(&rows.to_le_bytes());
        out.extend_from_slice(&cols.to_le_bytes());
        out.extend_from_slice(&XYHP_PAINT_RGBA.to_le_bytes());
        out.extend_from_slice(&(rgba.len() as u32).to_le_bytes());
        out.extend_from_slice(rgba);
        out
    }

    fn xyhp_colormap(
        stable_id: u64,
        rows: u32,
        cols: u32,
        lo: f64,
        hi: f64,
        values: &[f64],
        stops: &[[u8; 3]],
    ) -> Vec<u8> {
        let mut payload = Vec::new();
        payload.extend_from_slice(&lo.to_le_bytes());
        payload.extend_from_slice(&hi.to_le_bytes());
        payload.extend_from_slice(&(stops.len() as u32).to_le_bytes());
        payload.extend_from_slice(&0u32.to_le_bytes());
        for value in values {
            payload.extend_from_slice(&value.to_le_bytes());
        }
        for stop in stops {
            payload.extend_from_slice(stop);
        }
        let mut out = Vec::new();
        out.extend_from_slice(b"XYHP");
        out.extend_from_slice(&1u32.to_le_bytes());
        out.extend_from_slice(&1u32.to_le_bytes());
        out.extend_from_slice(&0u32.to_le_bytes());
        out.extend_from_slice(&stable_id.to_le_bytes());
        out.extend_from_slice(&rows.to_le_bytes());
        out.extend_from_slice(&cols.to_le_bytes());
        out.extend_from_slice(&XYHP_PAINT_COLORMAP.to_le_bytes());
        out.extend_from_slice(&(payload.len() as u32).to_le_bytes());
        out.extend_from_slice(&payload);
        out
    }

    fn xyhp_named(
        stable_id: u64,
        rows: u32,
        cols: u32,
        lo: f64,
        hi: f64,
        values: &[f64],
        name: &str,
    ) -> Vec<u8> {
        let name_bytes = name.as_bytes();
        let mut payload = Vec::new();
        payload.extend_from_slice(&lo.to_le_bytes());
        payload.extend_from_slice(&hi.to_le_bytes());
        payload.extend_from_slice(&(name_bytes.len() as u32).to_le_bytes());
        payload.extend_from_slice(&0u32.to_le_bytes());
        for value in values {
            payload.extend_from_slice(&value.to_le_bytes());
        }
        payload.extend_from_slice(name_bytes);
        let mut out = Vec::new();
        out.extend_from_slice(b"XYHP");
        out.extend_from_slice(&1u32.to_le_bytes());
        out.extend_from_slice(&1u32.to_le_bytes());
        out.extend_from_slice(&0u32.to_le_bytes());
        out.extend_from_slice(&stable_id.to_le_bytes());
        out.extend_from_slice(&rows.to_le_bytes());
        out.extend_from_slice(&cols.to_le_bytes());
        out.extend_from_slice(&XYHP_PAINT_NAMED.to_le_bytes());
        out.extend_from_slice(&(payload.len() as u32).to_le_bytes());
        out.extend_from_slice(&payload);
        out
    }

    fn xyhp_density(
        stable_id: u64,
        rows: u32,
        cols: u32,
        maximum: f64,
        opacity: f64,
        encoded: &[u8],
        name: &str,
    ) -> Vec<u8> {
        let name_bytes = name.as_bytes();
        let mut payload = Vec::new();
        payload.extend_from_slice(&maximum.to_le_bytes());
        payload.extend_from_slice(&opacity.to_le_bytes());
        payload.extend_from_slice(&(name_bytes.len() as u32).to_le_bytes());
        payload.extend_from_slice(&0u32.to_le_bytes());
        payload.extend_from_slice(encoded);
        payload.extend_from_slice(name_bytes);
        let mut out = Vec::new();
        out.extend_from_slice(b"XYHP");
        out.extend_from_slice(&1u32.to_le_bytes());
        out.extend_from_slice(&1u32.to_le_bytes());
        out.extend_from_slice(&0u32.to_le_bytes());
        out.extend_from_slice(&stable_id.to_le_bytes());
        out.extend_from_slice(&rows.to_le_bytes());
        out.extend_from_slice(&cols.to_le_bytes());
        out.extend_from_slice(&XYHP_PAINT_DENSITY.to_le_bytes());
        out.extend_from_slice(&(payload.len() as u32).to_le_bytes());
        out.extend_from_slice(&payload);
        out
    }

    fn xyhp_mean_color(
        stable_id: u64,
        rows: u32,
        cols: u32,
        maximum: f64,
        opacity: f64,
        encoded: &[u8],
        mean_rgba: &[u8],
    ) -> Vec<u8> {
        let mut payload = Vec::new();
        payload.extend_from_slice(&maximum.to_le_bytes());
        payload.extend_from_slice(&opacity.to_le_bytes());
        payload.extend_from_slice(&0u32.to_le_bytes());
        payload.extend_from_slice(&0u32.to_le_bytes());
        payload.extend_from_slice(encoded);
        payload.extend_from_slice(mean_rgba);
        let mut out = Vec::new();
        out.extend_from_slice(b"XYHP");
        out.extend_from_slice(&1u32.to_le_bytes());
        out.extend_from_slice(&1u32.to_le_bytes());
        out.extend_from_slice(&0u32.to_le_bytes());
        out.extend_from_slice(&stable_id.to_le_bytes());
        out.extend_from_slice(&rows.to_le_bytes());
        out.extend_from_slice(&cols.to_le_bytes());
        out.extend_from_slice(&XYHP_PAINT_MEAN_COLOR.to_le_bytes());
        out.extend_from_slice(&(payload.len() as u32).to_le_bytes());
        out.extend_from_slice(&payload);
        out
    }

    #[test]
    fn compact_heatmap_painted_interns_image_top_rgba() {
        // Image-top-first 2x2: top row red/green, bottom blue/white.
        let rgba = [
            255, 0, 0, 255, 0, 255, 0, 255, 0, 0, 255, 255, 255, 255, 255, 255,
        ];
        let paint = xyhp_rgba(9, 2, 2, &rgba);
        let kinds = [2u8, 2];
        let ids = [9u64, 9];
        let styles = [0u32, 0];
        let diameter = [2.0, 2.0];
        let symbols = [0u8, 0];
        let x0 = [0.0, 0.0];
        let y0 = [0.0, 0.0];
        let x1 = [2.0, 0.0];
        let y1 = [2.0, 0.0];
        let modes = [9u8, 9];
        let fill = [10u8, 20, 30, 200];
        let stroke = [1u8, 2, 3, 4];
        let width = [1.5_f64];
        let (expanded, painted, _images) = expand_scene_records_painted(
            SceneExpansionInput {
                kinds: &kinds,
                stable_ids: &ids,
                style_refs: &styles,
                diameter: &diameter,
                symbols: &symbols,
                x0: &x0,
                y0: &y0,
                x1: &x1,
                y1: &y1,
                expansion_modes: &modes,
            },
            test_linear_x_scale(),
            test_linear_y_scale(),
            &fill,
            &stroke,
            &width,
            &paint,
            false,
        )
        .unwrap();
        let styles = painted.unwrap();
        assert_eq!(expanded.kinds.len(), 4);
        assert_eq!(expanded.x0, [0.0, 1.0, 0.0, 1.0]);
        assert_eq!(expanded.y0, [0.0, 0.0, 1.0, 1.0]);
        // Lattice row 0 is y0 (bottom) = image bottom = blue/white.
        assert_eq!(&styles.fill_rgba[4..8], &[0, 0, 255, 255]);
        assert_eq!(&styles.fill_rgba[8..12], &[255, 255, 255, 255]);
        assert_eq!(&styles.fill_rgba[12..16], &[255, 0, 0, 255]);
        assert_eq!(&styles.fill_rgba[16..20], &[0, 255, 0, 255]);
        assert_eq!(expanded.style_refs, [1, 2, 3, 4]);
        assert_eq!(&styles.stroke_rgba[4..8], &[1, 2, 3, 4]);
    }

    #[test]
    fn compact_density_blit_emits_one_image_record() {
        let encoded = [0u8, 255, 128, 64];
        let paint = xyhp_density(7, 2, 2, 10.0, 0.85, &encoded, "viridis");
        let (expanded, painted, images) = expand_scene_records_painted(
            SceneExpansionInput {
                kinds: &[2, 2],
                stable_ids: &[7, 7],
                style_refs: &[0, 0],
                diameter: &[2.0, 2.0],
                symbols: &[0, 0],
                x0: &[0.0, 0.0],
                y0: &[1.0, 0.0],
                x1: &[4.0, 0.0],
                y1: &[3.0, 0.0],
                expansion_modes: &[10, 10],
            },
            test_linear_x_scale(),
            test_linear_y_scale(),
            &[0, 0, 0, 255],
            &[0, 0, 0, 0],
            &[0.0],
            &paint,
            false,
        )
        .unwrap();
        assert!(painted.is_none());
        assert_eq!(expanded.kinds, [SceneRecordKind::Image as u8]);
        assert_eq!(expanded.x0, [0.0]);
        assert_eq!(expanded.y0, [1.0]);
        assert_eq!(expanded.x1, [4.0]);
        assert_eq!(expanded.y1, [3.0]);
        assert_eq!(images.len(), 1);
        assert_eq!(images[0].stable_id, 7);
        assert_eq!(images[0].width, 2);
        assert_eq!(images[0].height, 2);
        assert_eq!(images[0].rgba.len(), 16);
        assert_eq!(images[0].rgba[11], 0); // encoded 0 (bottom-left) is transparent
        assert!(images[0].rgba[15] > 0); // encoded 255 (bottom-right) is opaque-ish
    }

    #[test]
    fn compact_mean_color_density_blit_emits_physical_alpha_image() {
        let encoded = [0u8, 255, 128, 1];
        let mean = [
            255, 0, 0, 255, 0, 255, 0, 255, 0, 0, 255, 0, 10, 20, 30, 255,
        ];
        let paint = xyhp_mean_color(7, 2, 2, 10.0, 0.72, &encoded, &mean);
        let (expanded, painted, images) = expand_scene_records_painted(
            SceneExpansionInput {
                kinds: &[2, 2],
                stable_ids: &[7, 7],
                style_refs: &[0, 0],
                diameter: &[2.0, 2.0],
                symbols: &[0, 0],
                x0: &[0.0, 0.0],
                y0: &[1.0, 0.0],
                x1: &[4.0, 0.0],
                y1: &[3.0, 0.0],
                expansion_modes: &[10, 10],
            },
            test_linear_x_scale(),
            test_linear_y_scale(),
            &[0, 0, 0, 255],
            &[0, 0, 0, 0],
            &[0.0],
            &paint,
            false,
        )
        .unwrap();
        assert!(painted.is_none());
        assert_eq!(expanded.kinds, [SceneRecordKind::Image as u8]);
        assert_eq!(images.len(), 1);
        assert_eq!(&images[0].rgba[8..12], &[255, 0, 0, 0]);
        assert_eq!(images[0].rgba[12], 0);
        assert_eq!(images[0].rgba[13], 255);
        assert!(images[0].rgba[15] > 0);
        assert_eq!(&images[0].rgba[0..4], &[0, 0, 255, 0]);
    }

    #[test]
    fn compact_polar_density_blit_emits_occupied_rects_not_image() {
        let encoded = [0u8, 255, 0, 128];
        let paint = xyhp_density(7, 2, 2, 10.0, 0.85, &encoded, "viridis");
        let (expanded, painted, images) = expand_scene_records_painted(
            SceneExpansionInput {
                kinds: &[2, 2],
                stable_ids: &[7, 7],
                style_refs: &[0, 0],
                diameter: &[2.0, 2.0],
                symbols: &[0, 0],
                x0: &[0.0, 0.0],
                y0: &[0.0, 0.0],
                x1: &[std::f64::consts::PI, 0.0],
                y1: &[1.0, 0.0],
                expansion_modes: &[10, 10],
            },
            test_linear_x_scale(),
            test_linear_y_scale(),
            &[0, 0, 0, 255],
            &[0, 0, 0, 0],
            &[0.0],
            &paint,
            true,
        )
        .unwrap();
        let styles = painted.unwrap();
        assert!(images.is_empty());
        assert_eq!(expanded.kinds.len(), 2);
        assert!(expanded
            .kinds
            .iter()
            .all(|kind| *kind == SceneRecordKind::Rect as u8));
        assert!(styles.stroke_width.iter().skip(1).all(|width| *width == 0.0));

        let layout = PlotLayout::new(400.0, 400.0, 0.0, 0.0, 0.0, 0.0).unwrap();
        let x = AxisScale::new(
            ScaleKind::Linear,
            0.0,
            std::f64::consts::PI,
            0.0,
            400.0,
            1.0,
            false,
        )
        .unwrap();
        let y = AxisScale::new(ScaleKind::Linear, 0.0, 1.0, 400.0, 0.0, 1.0, false).unwrap();
        let envelope = polar::PolarEnvelope {
            theta_unit: 0,
            theta_direction: 0,
            n_categories: 0,
            r_scale_kind: 0,
            grid_shape: 0,
            r_mask_nonpositive: false,
            theta_zero: 0.0,
            sector_start: 0.0,
            sector_end: std::f64::consts::PI,
            r_lo: 0.0,
            r_hi: 1.0,
            r_origin: f64::NAN,
            hole: 0.0,
            r_constant: 1.0,
        };
        let xypl = polar::encode_xypl(&envelope);
        let encoded_scene = SceneBatch::new(
            layout,
            1,
            2,
            x,
            y,
            &expanded.kinds,
            &expanded.stable_ids,
            &expanded.style_refs,
            &styles.fill_rgba,
            &styles.stroke_rgba,
            &styles.stroke_width,
            &expanded.diameter,
            &expanded.symbols,
            &expanded.x0,
            &expanded.y0,
            &expanded.x1,
            &expanded.y1,
        )
        .unwrap()
        .with_polar(&xypl)
        .unwrap()
        .encode();
        let document = SceneDocument::decode(&encoded_scene).unwrap();
        assert!(document.images.is_empty());
        assert!(document
            .records
            .iter()
            .all(|record| record.kind == SceneRecordKind::PolyFill));
        assert!(document.records.len() >= 6);
        let svg = document.to_svg();
        assert!(svg.contains("<path d=\"M"));
        assert!(!svg.contains("<image"));
        assert!(!svg.contains("<rect x="));
    }

    #[test]
    fn compact_heatmap_painted_colormap_maps_values_row_zero_to_y0() {
        let paint = xyhp_colormap(
            4,
            2,
            1,
            0.0,
            1.0,
            &[0.0, 1.0],
            &[[0, 0, 0], [255, 255, 255]],
        );
        let (expanded, painted, _images) = expand_scene_records_painted(
            SceneExpansionInput {
                kinds: &[2, 2],
                stable_ids: &[4, 4],
                style_refs: &[0, 0],
                diameter: &[2.0, 1.0],
                symbols: &[0, 0],
                x0: &[0.0, 0.0],
                y0: &[0.0, 0.0],
                x1: &[1.0, 0.0],
                y1: &[2.0, 0.0],
                expansion_modes: &[9, 9],
            },
            test_linear_x_scale(),
            test_linear_y_scale(),
            &[255, 0, 0, 180],
            &[0, 0, 0, 0],
            &[0.0],
            &paint,
            false,
        )
        .unwrap();
        let styles = painted.unwrap();
        assert_eq!(expanded.style_refs, [1, 2]);
        assert_eq!(&styles.fill_rgba[4..8], &[0, 0, 0, 180]);
        assert_eq!(&styles.fill_rgba[8..12], &[255, 255, 255, 180]);
    }

    #[test]
    fn compact_heatmap_painted_named_colormap_resolves_in_rust() {
        let paint = xyhp_named(
            5,
            1,
            2,
            f64::NAN,
            f64::NAN,
            &[0.0, 1.0],
            "binary",
        );
        let (expanded, painted, _images) = expand_scene_records_painted(
            SceneExpansionInput {
                kinds: &[2, 2],
                stable_ids: &[5, 5],
                style_refs: &[0, 0],
                diameter: &[1.0, 2.0],
                symbols: &[0, 0],
                x0: &[0.0, 0.0],
                y0: &[0.0, 0.0],
                x1: &[2.0, 0.0],
                y1: &[1.0, 0.0],
                expansion_modes: &[9, 9],
            },
            test_linear_x_scale(),
            test_linear_y_scale(),
            &[255, 0, 0, 200],
            &[0, 0, 0, 0],
            &[0.0],
            &paint,
            false,
        )
        .unwrap();
        let styles = painted.unwrap();
        assert_eq!(expanded.style_refs, [1, 2]);
        assert_eq!(&styles.fill_rgba[4..8], &[255, 255, 255, 200]);
        assert_eq!(&styles.fill_rgba[8..12], &[0, 0, 0, 200]);
    }

    #[test]
    fn split_scene_extras_accepts_xypl_xyhp_xyex_and_xyds() {
        assert_eq!(split_scene_extras(&[]), Some((&[][..], &[][..], &[][..])));
        let xyhp = xyhp_rgba(1, 1, 1, &[1, 2, 3, 4]);
        let (polar, paint, dash) = split_scene_extras(&xyhp).unwrap();
        assert!(polar.is_empty());
        assert_eq!(paint, xyhp.as_slice());
        assert!(dash.is_empty());
        let mut extras = Vec::new();
        extras.extend_from_slice(b"XYEX");
        extras.extend_from_slice(&1u32.to_le_bytes());
        extras.extend_from_slice(&0u32.to_le_bytes());
        extras.extend_from_slice(&(xyhp.len() as u32).to_le_bytes());
        extras.extend_from_slice(&xyhp);
        let (polar, paint, dash) = split_scene_extras(&extras).unwrap();
        assert!(polar.is_empty());
        assert_eq!(paint, xyhp.as_slice());
        assert!(dash.is_empty());
        let xyds = encode_xyds(&[StyleDash {
            style_ref: 0,
            count: 2,
            values: [6.0, 4.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
        }])
        .unwrap();
        let (polar, paint, dash) = split_scene_extras(&xyds).unwrap();
        assert!(polar.is_empty() && paint.is_empty());
        assert_eq!(dash, xyds.as_slice());
        let mut extras_v2 = Vec::new();
        extras_v2.extend_from_slice(b"XYEX");
        extras_v2.extend_from_slice(&2u32.to_le_bytes());
        extras_v2.extend_from_slice(&0u32.to_le_bytes());
        extras_v2.extend_from_slice(&0u32.to_le_bytes());
        extras_v2.extend_from_slice(&(xyds.len() as u32).to_le_bytes());
        extras_v2.extend_from_slice(&xyds);
        let (polar, paint, dash) = split_scene_extras(&extras_v2).unwrap();
        assert!(polar.is_empty() && paint.is_empty());
        assert_eq!(dash, xyds.as_slice());
        let xylc = encode_xylc(&[StyleCap {
            style_ref: 0,
            cap: LINECAP_BUTT,
        }])
        .unwrap();
        let (polar, paint, dash) = split_scene_extras(&xylc).unwrap();
        assert!(polar.is_empty() && paint.is_empty());
        assert_eq!(dash, xylc.as_slice());
        let mut combined = xyds.clone();
        combined.extend_from_slice(&xylc);
        let (polar, paint, dash) = split_scene_extras(&combined).unwrap();
        assert!(polar.is_empty() && paint.is_empty());
        assert_eq!(dash, combined.as_slice());
        let mut extras_v2_caps = Vec::new();
        extras_v2_caps.extend_from_slice(b"XYEX");
        extras_v2_caps.extend_from_slice(&2u32.to_le_bytes());
        extras_v2_caps.extend_from_slice(&0u32.to_le_bytes());
        extras_v2_caps.extend_from_slice(&0u32.to_le_bytes());
        extras_v2_caps.extend_from_slice(&(combined.len() as u32).to_le_bytes());
        extras_v2_caps.extend_from_slice(&combined);
        let (polar, paint, dash) = split_scene_extras(&extras_v2_caps).unwrap();
        assert!(polar.is_empty() && paint.is_empty());
        assert_eq!(dash, combined.as_slice());
        assert!(split_scene_extras(b"nope").is_none());
    }

    #[test]
    fn constant_dash_sidecar_reaches_svg_and_raster() {
        let layout = PlotLayout::new(240.0, 160.0, 20.0, 20.0, 20.0, 20.0).unwrap();
        let x_scale = AxisScale::new(ScaleKind::Linear, 0.0, 1.0, 20.0, 220.0, 1.0, false).unwrap();
        let y_scale = AxisScale::new(ScaleKind::Linear, 0.0, 1.0, 140.0, 20.0, 1.0, false).unwrap();
        let xyds = encode_xyds(&[StyleDash {
            style_ref: 0,
            count: 2,
            values: [6.0, 4.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
        }])
        .unwrap();
        let encoded = SceneBatch::new(
            layout,
            1,
            2,
            x_scale,
            y_scale,
            &[SceneRecordKind::Polyline as u8, SceneRecordKind::Polyline as u8],
            &[11, 11],
            &[0, 0],
            &[0, 0, 0, 0],
            &[37, 99, 235, 255],
            &[1.5],
            &[0.0, 0.0],
            &[0, 0],
            &[0.0, 1.0],
            &[0.0, 1.0],
            &[0.0, 0.0],
            &[0.0, 0.0],
        )
        .unwrap()
        .with_dashes(&xyds)
        .unwrap()
        .encode();
        assert_eq!(&encoded[4..8], &31u32.to_le_bytes());
        assert!(encoded.windows(4).any(|window| window == b"XYDS"));
        let document = SceneDocument::decode(&encoded).unwrap();
        let svg = document.to_svg();
        assert!(svg.contains("stroke-dasharray=\"6,4\""));
        let raster = document.to_raster_commands(1.0).unwrap();
        assert!(raster.windows(4).any(|window| window == &2u32.to_le_bytes()));
        let undashed = SceneBatch::new(
            layout,
            1,
            2,
            x_scale,
            y_scale,
            &[SceneRecordKind::Polyline as u8, SceneRecordKind::Polyline as u8],
            &[11, 11],
            &[0, 0],
            &[0, 0, 0, 0],
            &[37, 99, 235, 255],
            &[1.5],
            &[0.0, 0.0],
            &[0, 0],
            &[0.0, 1.0],
            &[0.0, 1.0],
            &[0.0, 0.0],
            &[0.0, 0.0],
        )
        .unwrap()
        .encode();
        assert_eq!(&undashed[4..8], &31u32.to_le_bytes());
        assert!(!undashed.windows(4).any(|window| window == b"XYDS"));
    }

    #[test]
    fn constant_linecap_sidecar_reaches_svg_and_raster() {
        let layout = PlotLayout::new(240.0, 160.0, 20.0, 20.0, 20.0, 20.0).unwrap();
        let x_scale = AxisScale::new(ScaleKind::Linear, 0.0, 1.0, 20.0, 220.0, 1.0, false).unwrap();
        let y_scale = AxisScale::new(ScaleKind::Linear, 0.0, 1.0, 140.0, 20.0, 1.0, false).unwrap();
        let xylc = encode_xylc(&[StyleCap {
            style_ref: 0,
            cap: LINECAP_BUTT,
        }])
        .unwrap();
        let encoded = SceneBatch::new(
            layout,
            1,
            2,
            x_scale,
            y_scale,
            &[SceneRecordKind::Polyline as u8, SceneRecordKind::Polyline as u8],
            &[11, 11],
            &[0, 0],
            &[0, 0, 0, 0],
            &[37, 99, 235, 255],
            &[1.5],
            &[0.0, 0.0],
            &[0, 0],
            &[0.0, 1.0],
            &[0.0, 1.0],
            &[0.0, 0.0],
            &[0.0, 0.0],
        )
        .unwrap()
        .with_dashes(&xylc)
        .unwrap()
        .encode();
        assert_eq!(&encoded[4..8], &31u32.to_le_bytes());
        assert!(encoded.windows(4).any(|window| window == b"XYLC"));
        let document = SceneDocument::decode(&encoded).unwrap();
        let svg = document.to_svg();
        assert!(svg.contains("stroke-linecap=\"butt\""));
        let raster = document.to_raster_commands(1.0).unwrap();
        assert!(raster.contains(&LINECAP_BUTT));
        let round_default = SceneBatch::new(
            layout,
            1,
            2,
            x_scale,
            y_scale,
            &[SceneRecordKind::Polyline as u8, SceneRecordKind::Polyline as u8],
            &[11, 11],
            &[0, 0],
            &[0, 0, 0, 0],
            &[37, 99, 235, 255],
            &[1.5],
            &[0.0, 0.0],
            &[0, 0],
            &[0.0, 1.0],
            &[0.0, 1.0],
            &[0.0, 0.0],
            &[0.0, 0.0],
        )
        .unwrap()
        .encode();
        assert!(!round_default.windows(4).any(|window| window == b"XYLC"));
        let round_svg = SceneDocument::decode(&round_default).unwrap().to_svg();
        assert!(round_svg.contains("stroke-linecap=\"round\""));
        assert!(!round_svg.contains("stroke-linecap=\"butt\""));
    }

    #[test]
    fn constant_marker_path_tessellates_after_pixel_mapping() {
        let layout = PlotLayout::new(240.0, 160.0, 20.0, 20.0, 20.0, 20.0).unwrap();
        let x_scale = AxisScale::new(ScaleKind::Linear, 0.0, 1.0, 20.0, 220.0, 1.0, false).unwrap();
        let y_scale = AxisScale::new(ScaleKind::Linear, 0.0, 1.0, 140.0, 20.0, 1.0, false).unwrap();
        let diamond = encode_xymp(&[StyleMarkerPath {
            style_ref: 0,
            path: AuthoredMarkerPath {
                filled: true,
                contours: vec![vec![(-0.5, 0.0), (0.0, 0.5), (0.5, 0.0), (0.0, -0.5)]],
            },
        }])
        .unwrap();
        let encoded = SceneBatch::new_with_decorations_colorbar(
            layout,
            1,
            2,
            x_scale,
            y_scale,
            SceneChromeStyle::default(),
            SceneChromeText::default(),
            None,
            None,
            Vec::new(),
            &[SceneRecordKind::Scatter as u8],
            &[11],
            &[0],
            &[51, 102, 153, 255],
            &[0, 0, 0, 0],
            &[0.0],
            &[4.0],
            &[0],
            &[0.5],
            &[0.5],
            &[0.0],
            &[0.0],
        )
        .unwrap()
        .with_dashes(&diamond)
        .unwrap()
        .encode();
        assert_eq!(&encoded[4..8], &31u32.to_le_bytes());
        assert!(!encoded.windows(4).any(|window| window == b"XYMP"));
        let svg = SceneDocument::decode(&encoded).unwrap().to_svg();
        assert!(svg.contains("<path d=\"M "));
        assert!(svg.contains(" Z\""));
        assert!(svg.contains("stroke=\"none\""));

        let plus = encode_xymp(&[StyleMarkerPath {
            style_ref: 0,
            path: AuthoredMarkerPath {
                filled: false,
                contours: vec![
                    vec![(-0.5, 0.0), (0.5, 0.0)],
                    vec![(0.0, -0.5), (0.0, 0.5)],
                ],
            },
        }])
        .unwrap();
        let encoded_plus = SceneBatch::new_with_decorations_colorbar(
            layout,
            1,
            2,
            x_scale,
            y_scale,
            SceneChromeStyle::default(),
            SceneChromeText::default(),
            None,
            None,
            Vec::new(),
            &[SceneRecordKind::Scatter as u8],
            &[11],
            &[0],
            &[51, 102, 153, 255],
            &[0, 0, 0, 0],
            &[0.0],
            &[4.0],
            &[0],
            &[0.5],
            &[0.5],
            &[0.0],
            &[0.0],
        )
        .unwrap()
        .with_dashes(&plus)
        .unwrap()
        .encode();
        assert!(!encoded_plus.windows(4).any(|window| window == b"XYMP"));
        let plus_svg = SceneDocument::decode(&encoded_plus).unwrap().to_svg();
        assert_eq!(plus_svg.matches("<polyline ").count(), 2);
        assert!(plus_svg.contains("stroke-width=\"1\""));
        assert!(plus_svg.contains("fill=\"none\""));
    }

    #[test]
    fn constant_marker_glyph_keeps_xymg_and_emits_text() {
        let layout = PlotLayout::new(240.0, 160.0, 20.0, 20.0, 20.0, 20.0).unwrap();
        let x_scale = AxisScale::new(ScaleKind::Linear, 0.0, 1.0, 20.0, 220.0, 1.0, false).unwrap();
        let y_scale = AxisScale::new(ScaleKind::Linear, 0.0, 1.0, 140.0, 20.0, 1.0, false).unwrap();
        let xymg = encode_xymg(&[StyleMarkerGlyph {
            style_ref: 0,
            glyph: "A".to_string(),
        }])
        .unwrap();
        let encoded = SceneBatch::new_with_decorations_colorbar(
            layout,
            1,
            2,
            x_scale,
            y_scale,
            SceneChromeStyle::default(),
            SceneChromeText::default(),
            None,
            None,
            Vec::new(),
            &[SceneRecordKind::Scatter as u8],
            &[11],
            &[0],
            &[51, 102, 153, 255],
            &[0, 0, 0, 0],
            &[0.0],
            &[12.0],
            &[0],
            &[0.5],
            &[0.5],
            &[0.0],
            &[0.0],
        )
        .unwrap()
        .with_dashes(&xymg)
        .unwrap()
        .encode();
        assert_eq!(&encoded[4..8], &31u32.to_le_bytes());
        assert!(encoded.windows(4).any(|window| window == b"XYMG"));
        let svg = SceneDocument::decode(&encoded).unwrap().to_svg();
        assert!(svg.contains("font-family=\"DejaVu Sans\""));
        assert!(svg.contains("dominant-baseline=\"central\""));
        assert!(svg.contains("text-anchor=\"middle\""));
        assert!(svg.contains(">A</text>"));
        assert!(!svg.contains("<circle "));
    }

    #[test]
    fn constant_linear_gradient_fill_reaches_svg_and_raster() {
        let layout = PlotLayout::new(240.0, 160.0, 20.0, 20.0, 20.0, 20.0).unwrap();
        let x_scale = AxisScale::new(ScaleKind::Linear, 0.0, 1.0, 20.0, 220.0, 1.0, false).unwrap();
        let y_scale = AxisScale::new(ScaleKind::Linear, 0.0, 1.0, 140.0, 20.0, 1.0, false).unwrap();
        let xygr = encode_xygr(&[StyleGradient {
            style_ref: 0,
            gradient: AuthoredGradient {
                plot_space: false,
                dir: XYGR_DIR_DOWN as u8,
                stops: vec![(0.0, [0, 0, 0, 255]), (1.0, [255, 255, 255, 255])],
            },
        }])
        .unwrap();
        let encoded = SceneBatch::new_with_decorations_colorbar(
            layout,
            1,
            2,
            x_scale,
            y_scale,
            SceneChromeStyle::default(),
            SceneChromeText::default(),
            None,
            None,
            Vec::new(),
            &[SceneRecordKind::Rect as u8],
            &[11],
            &[0],
            &[0, 0, 0, 255],
            &[0, 0, 0, 0],
            &[0.0],
            &[0.0],
            &[0],
            &[0.2],
            &[0.2],
            &[0.8],
            &[0.8],
        )
        .unwrap()
        .with_dashes(&xygr)
        .unwrap()
        .encode();
        assert_eq!(&encoded[4..8], &31u32.to_le_bytes());
        assert!(encoded.windows(4).any(|window| window == b"XYGR"));
        let document = SceneDocument::decode(&encoded).unwrap();
        let svg = document.to_svg();
        assert!(svg.contains("<linearGradient id=\"xy-scene-g0\""));
        assert!(svg.contains("fill=\"url(#xy-scene-g0)\""));
        assert!(svg.contains("stop-color=\"rgb(0,0,0)\""));
        assert!(svg.contains("stop-color=\"rgb(255,255,255)\""));
        let commands = document.to_raster_commands(1.0).unwrap();
        assert!(commands.contains(&2));

        let transparent = encode_xygr(&[StyleGradient {
            style_ref: 0,
            gradient: AuthoredGradient {
                plot_space: false,
                dir: XYGR_DIR_DOWN as u8,
                stops: vec![(0.0, [255, 0, 0, 255]), (1.0, [0, 0, 0, 0])],
            },
        }])
        .unwrap();
        let encoded_t = SceneBatch::new_with_decorations_colorbar(
            layout,
            1,
            2,
            x_scale,
            y_scale,
            SceneChromeStyle::default(),
            SceneChromeText::default(),
            None,
            None,
            Vec::new(),
            &[SceneRecordKind::Rect as u8],
            &[11],
            &[0],
            &[255, 0, 0, 255],
            &[0, 0, 0, 0],
            &[0.0],
            &[0.0],
            &[0],
            &[0.2],
            &[0.2],
            &[0.8],
            &[0.8],
        )
        .unwrap()
        .with_dashes(&transparent)
        .unwrap()
        .encode();
        let transparent_svg = SceneDocument::decode(&encoded_t).unwrap().to_svg();
        assert!(transparent_svg.contains("stop-color=\"rgb(255,0,0)\" stop-opacity=\"0\""));
        assert!(!transparent_svg.contains("stop-color=\"rgb(0,0,0)\" stop-opacity=\"0\""));
    }

    #[test]
    fn compact_segment_pair_emits_two_polyline_vertices() {
        let expanded = expand_scene_records(
            SceneExpansionInput {
                kinds: &[1],
                stable_ids: &[11],
                style_refs: &[4],
                diameter: &[0.0],
                symbols: &[0],
                x0: &[0.25],
                y0: &[0.5],
                x1: &[1.25],
                y1: &[1.5],
                expansion_modes: &[7],
            },
            test_linear_x_scale(),
            test_linear_y_scale(),
        )
        .unwrap();
        assert_eq!(expanded.kinds, [1, 1]);
        assert_eq!(expanded.stable_ids, [11, 11]);
        assert_eq!(expanded.style_refs, [4, 4]);
        assert_eq!(expanded.x0, [0.25, 1.25]);
        assert_eq!(expanded.y0, [0.5, 1.5]);
        assert_eq!(expanded.x1, [0.0, 0.0]);
        assert_eq!(expanded.y1, [0.0, 0.0]);
    }

    #[test]
    fn compact_segment_pair_keeps_later_scatter_with_reused_identity() {
        let kinds = [1u8, 0, 0];
        let ids = [1u64, 1, 1];
        let styles = [0u32, 1, 1];
        let diameter = [0.0, 4.0, 4.0];
        let symbols = [0u8, 0, 0];
        let x0 = [0.0, 0.0, 1.0];
        let y0 = [0.0, 1.0, 2.0];
        let x1 = [0.0, 0.0, 0.0];
        let y1 = [1.0, 0.0, 0.0];
        let modes = [7u8, 0, 0];
        let expanded = expand_scene_records(
            SceneExpansionInput {
                kinds: &kinds,
                stable_ids: &ids,
                style_refs: &styles,
                diameter: &diameter,
                symbols: &symbols,
                x0: &x0,
                y0: &y0,
                x1: &x1,
                y1: &y1,
                expansion_modes: &modes,
            },
            test_linear_x_scale(),
            test_linear_y_scale(),
        )
        .unwrap();
        assert_eq!(expanded.kinds, [1, 1, 0, 0]);
        assert_eq!(expanded.stable_ids, [1, 1, 1, 1]);
        assert_eq!(expanded.x0, [0.0, 0.0, 0.0, 1.0]);
        assert_eq!(expanded.y0, [0.0, 1.0, 1.0, 2.0]);
        assert_eq!(expanded.diameter, [0.0, 0.0, 4.0, 4.0]);
    }

    #[test]
    fn compact_segment_pair_rejects_shared_identity() {
        let kinds = [1u8, 1];
        let ids = [1u64, 1];
        let styles = [0u32, 0];
        let zeros = [0.0, 0.0];
        let symbols = [0u8, 0];
        let x0 = [0.0, 1.0];
        let y0 = [0.0, 1.0];
        let x1 = [0.5, 1.5];
        let y1 = [0.5, 1.5];
        let modes = [7u8, 7];
        assert_eq!(
            expand_scene_records(
                SceneExpansionInput {
                    kinds: &kinds,
                    stable_ids: &ids,
                    style_refs: &styles,
                    diameter: &zeros,
                    symbols: &symbols,
                    x0: &x0,
                    y0: &y0,
                    x1: &x1,
                    y1: &y1,
                    expansion_modes: &modes,
                },
                test_linear_x_scale(),
                test_linear_y_scale(),
            ),
            Err(SceneError::Length)
        );
    }

    #[test]
    fn compact_triangle_face_emits_three_polyfill_vertices() {
        let kinds = [4u8, 4];
        let ids = [21u64, 21];
        let styles = [2u32, 2];
        let zeros = [0.0, 0.0];
        let symbols = [0u8, 0];
        let x0 = [-0.25, 0.25];
        let y0 = [0.25, 1.25];
        let x1 = [0.75, 0.0];
        let y1 = [0.25, 0.0];
        let modes = [8u8, 8];
        let expanded = expand_scene_records(
            SceneExpansionInput {
                kinds: &kinds,
                stable_ids: &ids,
                style_refs: &styles,
                diameter: &zeros,
                symbols: &symbols,
                x0: &x0,
                y0: &y0,
                x1: &x1,
                y1: &y1,
                expansion_modes: &modes,
            },
            test_linear_x_scale(),
            test_linear_y_scale(),
        )
        .unwrap();
        assert_eq!(expanded.kinds, [4, 4, 4]);
        assert_eq!(expanded.stable_ids, [21, 21, 21]);
        assert_eq!(expanded.x0, [-0.25, 0.75, 0.25]);
        assert_eq!(expanded.y0, [0.25, 0.25, 1.25]);
        assert_eq!(expanded.x1, [0.0, 0.0, 0.0]);
        assert_eq!(expanded.y1, [0.0, 0.0, 0.0]);
    }

    #[test]
    fn compact_triangle_face_rejects_nonzero_second_endpoint() {
        let kinds = [4u8, 4];
        let ids = [21u64, 21];
        let styles = [2u32, 2];
        let zeros = [0.0, 0.0];
        let symbols = [0u8, 0];
        let x0 = [-0.25, 0.25];
        let y0 = [0.25, 1.25];
        let x1 = [0.75, 0.5];
        let y1 = [0.25, 0.0];
        let modes = [8u8, 8];
        assert_eq!(
            expand_scene_records(
                SceneExpansionInput {
                    kinds: &kinds,
                    stable_ids: &ids,
                    style_refs: &styles,
                    diameter: &zeros,
                    symbols: &symbols,
                    x0: &x0,
                    y0: &y0,
                    x1: &x1,
                    y1: &y1,
                    expansion_modes: &modes,
                },
                test_linear_x_scale(),
                test_linear_y_scale(),
            ),
            Err(SceneError::Length)
        );
    }

    #[allow(clippy::too_many_arguments)]
    fn compact_ribbon_input<'a>(
        ids: &'a [u64],
        styles: &'a [u32],
        symbols: &'a [u8],
        x0: &'a [f64],
        y0: &'a [f64],
        x1: &'a [f64],
        y1: &'a [f64],
        modes: &'a [u8],
    ) -> SceneExpansionInput<'a> {
        SceneExpansionInput {
            kinds: &[3, 3],
            stable_ids: ids,
            style_refs: styles,
            diameter: &[0.0, 0.0],
            symbols,
            x0,
            y0,
            x1,
            y1,
            expansion_modes: modes,
        }
    }

    #[test]
    fn compact_ribbon_expands_in_transformed_space_with_stable_identity() {
        let x_scale = AxisScale::new(ScaleKind::Log, 1.0, 100.0, 0.0, 100.0, 1.0, false).unwrap();
        let y_scale = AxisScale::new(ScaleKind::Log, 1.0, 1000.0, 100.0, 0.0, 1.0, false).unwrap();
        let expanded = expand_scene_records(
            compact_ribbon_input(
                &[42, 42],
                &[7, 7],
                &[2, 2],
                &[1.0, 1.0],
                &[10.0, 1.0],
                &[100.0, 100.0],
                &[1000.0, 100.0],
                &[4, 4],
            ),
            x_scale,
            y_scale,
        )
        .unwrap();

        assert_eq!(expanded.kinds.len(), SCENE_RIBBON_STEPS + 1);
        assert!(expanded.kinds.iter().all(|kind| *kind == 3));
        assert!(expanded.stable_ids.iter().all(|stable_id| *stable_id == 42));
        assert!(expanded.style_refs.iter().all(|style_ref| *style_ref == 7));
        assert!(expanded.symbols.iter().all(|symbol| *symbol == 2));
        assert_eq!((expanded.x0[0], expanded.x1[0]), (1.0, 1.0));
        assert_eq!((expanded.y0[0], expanded.y1[0]), (10.0, 1.0));
        assert_eq!(
            (
                expanded.x0[SCENE_RIBBON_STEPS],
                expanded.x1[SCENE_RIBBON_STEPS]
            ),
            (100.0, 100.0)
        );
        assert_eq!(
            (
                expanded.y0[SCENE_RIBBON_STEPS],
                expanded.y1[SCENE_RIBBON_STEPS]
            ),
            (1000.0, 100.0)
        );

        let midpoint = SCENE_RIBBON_STEPS / 2;
        assert!((expanded.x0[midpoint] - 10.0).abs() < 1e-12);
        assert!((expanded.y0[midpoint] - 100.0).abs() < 1e-12);
        assert!((expanded.y1[midpoint] - 10.0).abs() < 1e-12);
        assert_ne!(expanded.y0[midpoint], 505.0);
    }

    #[test]
    fn compact_ribbon_symlog_midpoint_is_exactly_scale_lowered() {
        let y_scale =
            AxisScale::new(ScaleKind::SymLog, 0.0, 1000.0, 100.0, 0.0, 2.0, false).unwrap();
        let expanded = expand_scene_records(
            compact_ribbon_input(
                &[9, 9],
                &[0, 0],
                &[1, 1],
                &[0.0, 0.0],
                &[10.0, 1.0],
                &[10.0, 10.0],
                &[1000.0, 100.0],
                &[4, 4],
            ),
            test_linear_x_scale(),
            y_scale,
        )
        .unwrap();
        let midpoint = SCENE_RIBBON_STEPS / 2;
        let expected_top = y_scale.value((y_scale.coord(10.0) + y_scale.coord(1000.0)) * 0.5);
        let expected_base = y_scale.value((y_scale.coord(1.0) + y_scale.coord(100.0)) * 0.5);
        assert!((expanded.y0[midpoint] - expected_top).abs() < 1e-12);
        assert!((expanded.y1[midpoint] - expected_base).abs() < 1e-12);
        assert_ne!(expanded.y0[midpoint], 505.0);
    }

    #[test]
    fn compact_ribbon_preserves_source_order_across_adjacent_pairs() {
        let expanded = expand_scene_records(
            SceneExpansionInput {
                kinds: &[0, 3, 3, 3, 3],
                stable_ids: &[1, 7, 7, 8, 8],
                style_refs: &[0, 2, 2, 3, 3],
                diameter: &[4.0, 0.0, 0.0, 0.0, 0.0],
                symbols: &[0, 2, 2, 1, 1],
                x0: &[5.0, 0.0, 0.0, 2.0, 2.0],
                y0: &[5.0, 2.0, 1.0, 4.0, 3.0],
                x1: &[0.0, 1.0, 1.0, 8.0, 8.0],
                y1: &[0.0, 3.0, 2.0, 5.0, 4.0],
                expansion_modes: &[0, 4, 4, 4, 4],
            },
            test_linear_x_scale(),
            test_linear_y_scale(),
        )
        .unwrap();
        assert_eq!(expanded.stable_ids[0], 1);
        assert!(expanded.stable_ids[1..SCENE_RIBBON_STEPS + 2]
            .iter()
            .all(|stable_id| *stable_id == 7));
        assert!(expanded.stable_ids[SCENE_RIBBON_STEPS + 2..]
            .iter()
            .all(|stable_id| *stable_id == 8));
        assert_eq!(expanded.style_refs[1], 2);
        assert_eq!(expanded.style_refs[SCENE_RIBBON_STEPS + 2], 3);
        assert_eq!(expanded.symbols[1], 2);
        assert_eq!(expanded.symbols[SCENE_RIBBON_STEPS + 2], 1);
    }

    #[test]
    fn compact_ribbon_fails_closed_for_malformed_pairs_and_budget() {
        let rejected = |ids: &[u64],
                        styles: &[u32],
                        symbols: &[u8],
                        x0: &[f64],
                        y0: &[f64],
                        x1: &[f64],
                        y1: &[f64],
                        modes: &[u8]| {
            expand_scene_records(
                compact_ribbon_input(ids, styles, symbols, x0, y0, x1, y1, modes),
                test_linear_x_scale(),
                test_linear_y_scale(),
            )
        };
        assert_eq!(
            rejected(
                &[1, 2],
                &[0, 0],
                &[2, 2],
                &[0.0, 0.0],
                &[2.0, 1.0],
                &[1.0, 1.0],
                &[3.0, 2.0],
                &[4, 4]
            ),
            Err(SceneError::Length)
        );
        assert_eq!(
            rejected(
                &[1, 1],
                &[0, 1],
                &[2, 2],
                &[0.0, 0.0],
                &[2.0, 1.0],
                &[1.0, 1.0],
                &[3.0, 2.0],
                &[4, 4]
            ),
            Err(SceneError::Length)
        );
        assert_eq!(
            rejected(
                &[1, 1],
                &[0, 0],
                &[2, 1],
                &[0.0, 0.0],
                &[2.0, 1.0],
                &[1.0, 1.0],
                &[3.0, 2.0],
                &[4, 4]
            ),
            Err(SceneError::Length)
        );
        assert_eq!(
            rejected(
                &[1, 1],
                &[0, 0],
                &[2, 2],
                &[0.0, 0.5],
                &[2.0, 1.0],
                &[1.0, 1.0],
                &[3.0, 2.0],
                &[4, 4]
            ),
            Err(SceneError::Length)
        );
        assert_eq!(
            rejected(
                &[1, 1],
                &[0, 0],
                &[2, 2],
                &[0.0, 0.0],
                &[f64::NAN, 1.0],
                &[1.0, 1.0],
                &[3.0, 2.0],
                &[4, 4]
            ),
            Err(SceneError::NonFinite)
        );
        assert_eq!(
            rejected(
                &[1, 1],
                &[0, 0],
                &[2, 2],
                &[0.0, 0.0],
                &[2.0, 1.0],
                &[1.0, 1.0],
                &[3.0, 2.0],
                &[4, 3]
            ),
            Err(SceneError::Length)
        );

        let pair_count = MAX_SCENE_MARKS / (SCENE_RIBBON_STEPS + 1) + 1;
        let len = pair_count * 2;
        let ids = (0..pair_count)
            .flat_map(|id| [id as u64, id as u64])
            .collect::<Vec<_>>();
        let kinds = vec![3; len];
        let styles = vec![0; len];
        let diameter = vec![0.0; len];
        let symbols = vec![2; len];
        let x0 = vec![0.0; len];
        let y0 = vec![1.0; len];
        let x1 = vec![1.0; len];
        let y1 = vec![2.0; len];
        let modes = vec![4; len];
        let input = SceneExpansionInput {
            kinds: &kinds,
            stable_ids: &ids,
            style_refs: &styles,
            diameter: &diameter,
            symbols: &symbols,
            x0: &x0,
            y0: &y0,
            x1: &x1,
            y1: &y1,
            expansion_modes: &modes,
        };
        assert_eq!(
            expand_scene_records(input, test_linear_x_scale(), test_linear_y_scale()),
            Err(SceneError::Limit)
        );
    }

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
            x_format: None,
            y_kind: ScaleKind::Linear,
            y_lo: 0.0,
            y_hi: 5.0,
            y_constant: 1.0,
            y_mask_nonpositive: false,
            y_format: None,
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
    fn cartesian_scene_margins_measure_the_rust_resolved_numeric_labels() {
        let request = CartesianLayoutRequest {
            viewport_width: 640.0,
            viewport_height: 360.0,
            authored_padding: None,
            title: "",
            x_label: "",
            y_label: "",
            x_kind: ScaleKind::Linear,
            x_lo: 0.0,
            x_hi: 1.0,
            x_constant: 1.0,
            x_mask_nonpositive: false,
            x_format: None,
            y_kind: ScaleKind::Linear,
            y_lo: 0.0,
            y_hi: 100_000.0,
            y_constant: 1.0,
            y_mask_nonpositive: false,
            y_format: None,
            colorbar_side: ColorbarSide::None,
        };
        let plain = cartesian_scene_margins(request).unwrap();
        let formatted = cartesian_scene_margins(CartesianLayoutRequest {
            x_format: Some(".1%"),
            y_format: Some("$,.0f USD"),
            ..request
        })
        .unwrap();
        assert!(
            formatted.0 > plain.0,
            "plain={plain:?} formatted={formatted:?}"
        );
        assert!(
            formatted.1 >= plain.1,
            "plain={plain:?} formatted={formatted:?}"
        );
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
            x_format: None,
            y_kind: ScaleKind::Linear,
            y_lo: 0.0,
            y_hi: 1.0,
            y_constant: 1.0,
            y_mask_nonpositive: false,
            y_format: None,
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
        assert_eq!(SCENE_VERSION, 31);
        assert_eq!(
            scene.to_svg(),
            "<g><circle cx=\"10\" cy=\"11\" r=\"3\" fill=\"rgb(37,99,235)\" stroke=\"rgb(0,0,0)\" stroke-width=\"2\"/><path d=\"M 15.5 21 H 24.5 M 20 16.5 V 25.5\" fill=\"none\" stroke=\"rgb(17,24,39)\" stroke-opacity=\"0.25\" stroke-width=\"1\"/></g>"
        );
    }

    #[test]
    fn straight_arrow_lowers_to_a_valid_fixed_head_run_for_all_rust_consumers() {
        let layout = PlotLayout::new(240.0, 160.0, 20.0, 20.0, 20.0, 20.0).unwrap();
        let x_scale = AxisScale::new(ScaleKind::Linear, 0.0, 1.0, 20.0, 220.0, 1.0, false).unwrap();
        let y_scale = AxisScale::new(ScaleKind::Linear, 0.0, 1.0, 140.0, 20.0, 1.0, false).unwrap();
        let scene = SceneBatch::new(
            layout,
            1,
            2,
            x_scale,
            y_scale,
            &[SceneRecordKind::Scatter as u8],
            &[7],
            &[0],
            &[1, 2, 3, 255],
            &[1, 2, 3, 255],
            &[0.0],
            &[4.0],
            &[0],
            &[0.5],
            &[0.5],
            &[0.0],
            &[0.0],
        )
        .unwrap()
        .encode();
        let document = SceneDocument::decode(&scene)
            .unwrap()
            .with_straight_arrows(&[StraightArrow {
                stable_id: 0x5859_0500_0000_0001,
                x0: 0.1,
                y0: 0.1,
                x1: 0.9,
                y1: 0.9,
                rgba: [10, 20, 30, 200],
                opacity: 0.5,
                width: 2.0,
            }])
            .unwrap();
        let arrow = &document.records[1..];
        assert!(valid_straight_arrow_run(arrow));
        assert_eq!(
            document.styles[arrow[0].style_ref].stroke,
            [10, 20, 30, 100]
        );
        assert!(document.to_svg().contains("<polyline points="));
        assert!(document.to_svg().contains("<path d=\"M "));
        assert!(document.to_raster_commands(1.0).unwrap().len() > 100);
        assert!(
            document.to_browser_painter(64 * 1024).unwrap().len() > BROWSER_PAINTER_HEADER_BYTES
        );

        let mut malformed = arrow.to_vec();
        malformed[2].coordinates[0] += 1.0;
        assert!(!valid_straight_arrow_run(&malformed));
        assert!(SceneDocument::decode(&scene)
            .unwrap()
            .with_straight_arrows(&[StraightArrow {
                stable_id: 9,
                x0: 0.5,
                y0: 0.5,
                x1: 0.5,
                y1: 0.5,
                rgba: [0, 0, 0, 255],
                opacity: 1.0,
                width: 1.0,
            }])
            .is_err());
        assert!(SceneDocument::decode(&scene)
            .unwrap()
            .with_straight_arrows(&[StraightArrow {
                stable_id: 10,
                x0: 0.1,
                y0: 0.1,
                x1: 0.9,
                y1: 0.9,
                rgba: [0, 0, 0, 255],
                opacity: 1.1,
                width: 1.0,
            }])
            .is_err());
    }

    #[test]
    fn cartesian_callout_xyac_v1_derives_tag_six_leader_and_anchored_label() {
        let layout = PlotLayout::new(240.0, 160.0, 20.0, 20.0, 20.0, 20.0).unwrap();
        let x_scale = AxisScale::new(ScaleKind::Linear, 0.0, 1.0, 20.0, 220.0, 1.0, false).unwrap();
        let y_scale = AxisScale::new(ScaleKind::Linear, 0.0, 1.0, 140.0, 20.0, 1.0, false).unwrap();
        let scene = SceneBatch::new(
            layout,
            1,
            2,
            x_scale,
            y_scale,
            &[SceneRecordKind::Scatter as u8],
            &[7],
            &[0],
            &[1, 2, 3, 255],
            &[1, 2, 3, 255],
            &[0.0],
            &[4.0],
            &[0],
            &[0.5],
            &[0.5],
            &[0.0],
            &[0.0],
        )
        .unwrap()
        .encode();
        let mut xyac = Vec::new();
        xyac.extend_from_slice(b"XYAC");
        xyac.extend_from_slice(&1u32.to_le_bytes());
        xyac.extend_from_slice(&1u32.to_le_bytes());
        for value in [0.5f64, 0.5, 36.0, -30.0] {
            xyac.extend_from_slice(&value.to_le_bytes());
        }
        xyac.extend_from_slice(&[10, 20, 30, 200]);
        xyac.extend_from_slice(&0.5f64.to_le_bytes());
        xyac.extend_from_slice(&2.0f64.to_le_bytes());
        xyac.push(2);
        xyac.extend_from_slice(&[0; 3]);
        xyac.extend_from_slice(&4u32.to_le_bytes());
        xyac.extend_from_slice(b"note");
        let mut envelope = Vec::new();
        envelope.extend_from_slice(b"XYAD");
        envelope.extend_from_slice(&2u32.to_le_bytes());
        envelope.extend_from_slice(&0u32.to_le_bytes());
        envelope.extend_from_slice(&0u32.to_le_bytes());
        envelope.extend_from_slice(&0u32.to_le_bytes());
        envelope.extend_from_slice(&(xyac.len() as u32).to_le_bytes());
        envelope.extend_from_slice(&xyac);
        let document = SceneDocument::decode(&scene)
            .unwrap()
            .with_authored_annotations(&envelope)
            .unwrap();
        let run = &document.records[1..];
        assert!(valid_straight_arrow_run(run));
        assert_eq!(
            run[0].annotation_tag,
            SCENE_ANNOTATION_TAG_CARTESIAN_CALLOUT
        );
        assert_eq!(run[0].stable_id, 0x5859_0600_0000_0000);
        assert_eq!(run[0].coordinates[..2], [156.0, 50.0]);
        assert_eq!(run[2].coordinates[..2], [120.0, 80.0]);
        assert_eq!(document.labels[0].anchor, 2);
        assert!(document.to_svg().contains("text-anchor=\"end\""));
        let painter = document.to_browser_painter(64 * 1024).unwrap();
        assert_eq!(
            painter[BROWSER_PAINTER_HEADER_BYTES + BROWSER_PAINTER_TRACE_BYTES + 2],
            SCENE_ANNOTATION_TAG_CARTESIAN_CALLOUT
        );
        assert!(painter.windows(4).any(|window| window == b"XYLB"));
        let mut malformed = envelope.clone();
        // XYAC's reserved bytes are fail-closed, not ignored future payload.
        malformed[24 + 12 + 53] = 1;
        assert_eq!(
            SceneDocument::decode(&scene)
                .unwrap()
                .with_authored_annotations(&malformed)
                .err(),
            Some(SceneError::Length)
        );
        let batch_scene = SceneBatch::new(
            layout,
            1,
            2,
            x_scale,
            y_scale,
            &[SceneRecordKind::Scatter as u8],
            &[7],
            &[0],
            &[1, 2, 3, 255],
            &[1, 2, 3, 255],
            &[0.0],
            &[4.0],
            &[0],
            &[0.5],
            &[0.5],
            &[0.0],
            &[0.0],
        )
        .unwrap()
        .with_authored_annotations(&envelope)
        .unwrap()
        .encode();
        assert_eq!(SceneDocument::decode(&batch_scene).err(), None);
    }

    #[test]
    fn cartesian_callout_xyac_v2_resolves_and_serializes_literal_label_box() {
        let layout = PlotLayout::new(240.0, 160.0, 20.0, 20.0, 20.0, 20.0).unwrap();
        let x_scale = AxisScale::new(ScaleKind::Linear, 0.0, 1.0, 20.0, 220.0, 1.0, false).unwrap();
        let y_scale = AxisScale::new(ScaleKind::Linear, 0.0, 1.0, 140.0, 20.0, 1.0, false).unwrap();
        let scene = SceneBatch::new(
            layout,
            1,
            2,
            x_scale,
            y_scale,
            &[SceneRecordKind::Scatter as u8],
            &[7],
            &[0],
            &[1, 2, 3, 255],
            &[1, 2, 3, 255],
            &[0.0],
            &[4.0],
            &[0],
            &[0.5],
            &[0.5],
            &[0.0],
            &[0.0],
        )
        .unwrap()
        .encode();
        let mut xyac = Vec::new();
        xyac.extend_from_slice(b"XYAC");
        xyac.extend_from_slice(&2u32.to_le_bytes());
        xyac.extend_from_slice(&1u32.to_le_bytes());
        for value in [0.5f64, 0.5, 36.0, -30.0] {
            xyac.extend_from_slice(&value.to_le_bytes());
        }
        xyac.extend_from_slice(&[10, 20, 30, 200]);
        xyac.extend_from_slice(&0.5f64.to_le_bytes());
        xyac.extend_from_slice(&2.0f64.to_le_bytes());
        xyac.push(2);
        xyac.extend_from_slice(&[0; 3]);
        xyac.extend_from_slice(&4u32.to_le_bytes());
        xyac.extend_from_slice(&[4, 5, 6, 128]);
        xyac.extend_from_slice(b"note");
        let mut envelope = Vec::new();
        envelope.extend_from_slice(b"XYAD");
        envelope.extend_from_slice(&2u32.to_le_bytes());
        envelope.extend_from_slice(&0u32.to_le_bytes());
        envelope.extend_from_slice(&0u32.to_le_bytes());
        envelope.extend_from_slice(&0u32.to_le_bytes());
        envelope.extend_from_slice(&(xyac.len() as u32).to_le_bytes());
        envelope.extend_from_slice(&xyac);
        let document = SceneDocument::decode(&scene)
            .unwrap()
            .with_authored_annotations(&envelope)
            .unwrap();
        let background = document.label_backgrounds[0].as_ref().unwrap();
        assert_eq!(background.rgba, [4, 5, 6, 128]);
        assert!(background.x < document.labels[0].x);
        assert!(background.y < document.labels[0].y);
        assert!(background.width > 0.0 && background.height > 0.0);
        let svg = document.to_svg();
        assert!(svg.contains("data-xy-slot=\"annotation_label_box\""));
        assert!(
            svg.find("<rect data-xy-slot=\"annotation_label_box\"")
                .unwrap()
                < svg.find("<text data-xy-slot=\"graph_label\"").unwrap()
        );
        let raster = document.to_raster_commands(1.0).unwrap();
        assert!(raster.windows(4).any(|window| window == [4, 5, 6, 128]));
        let painter = document.to_browser_painter(64 * 1024).unwrap();
        let label = painter
            .windows(4)
            .position(|window| window == b"XYLB")
            .unwrap();
        assert_eq!(
            u32::from_le_bytes(painter[label + 4..label + 8].try_into().unwrap()),
            3
        );
        let record = label + SCENE_LABEL_HEADER_BYTES;
        assert_eq!(painter[record + 44], 1);
        assert_eq!(&painter[record + 80..record + 84], &[4, 5, 6, 128]);

        let round_trip_scene = SceneBatch::new(
            layout,
            1,
            2,
            x_scale,
            y_scale,
            &[SceneRecordKind::Scatter as u8],
            &[7],
            &[0],
            &[1, 2, 3, 255],
            &[1, 2, 3, 255],
            &[0.0],
            &[4.0],
            &[0],
            &[0.5],
            &[0.5],
            &[0.0],
            &[0.0],
        )
        .unwrap()
        .with_authored_annotations(&envelope)
        .unwrap()
        .encode();
        let round_trip = SceneDocument::decode(&round_trip_scene).unwrap();
        assert_eq!(
            round_trip.label_backgrounds[0].as_ref().unwrap().rgba,
            [4, 5, 6, 128]
        );

        let mut malformed = envelope;
        malformed[24 + 4..24 + 8].copy_from_slice(&3u32.to_le_bytes());
        assert_eq!(
            SceneDocument::decode(&scene)
                .unwrap()
                .with_authored_annotations(&malformed)
                .err(),
            Some(SceneError::Length)
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
            &[0; 10],
            &[1, 2, 3, 4, 5, 6, 7, 8, 9, 10],
            &[0; 10],
            &[0; 4],
            &[0; 4],
            &[0.0],
            &[20.0; 10],
            &[
                ScatterSymbol::Diamond as u8,
                ScatterSymbol::Diamond as u8,
                ScatterSymbol::ThinDiamond as u8,
                ScatterSymbol::ThinDiamond as u8,
                ScatterSymbol::TriangleRight as u8,
                ScatterSymbol::TriangleRight as u8,
                ScatterSymbol::TriangleLeft as u8,
                ScatterSymbol::TriangleLeft as u8,
                ScatterSymbol::TriangleDown as u8,
                ScatterSymbol::TriangleDown as u8,
            ],
            &[
                -12.0, -14.2, 40.0, 40.0, -9.9, -10.1, 89.9, 90.1, 40.0, 40.0,
            ],
            &[
                40.0, 40.0, -12.0, -14.2, 40.0, 40.0, 40.0, 40.0, -9.9, -10.1,
            ],
            &[0.0; 10],
            &[0.0; 10],
        )
        .unwrap();
        let encoded = batch.encode();
        let records = SCENE_BATCH_HEADER_BYTES + SCENE_STYLE_RECORD_BYTES;
        assert_eq!(encoded[records + 1], 1);
        assert_eq!(encoded[records + SCENE_BATCH_RECORD_BYTES + 1], 0);
        assert_eq!(encoded[records + 2 * SCENE_BATCH_RECORD_BYTES + 1], 1);
        assert_eq!(encoded[records + 3 * SCENE_BATCH_RECORD_BYTES + 1], 0);
        for index in [4, 6, 8] {
            assert_eq!(encoded[records + index * SCENE_BATCH_RECORD_BYTES + 1], 1);
            assert_eq!(
                encoded[records + (index + 1) * SCENE_BATCH_RECORD_BYTES + 1],
                0
            );
        }

        let line = MarkerGeometry::new(ScatterSymbol::PlusLine, 0.0, 0.0);
        assert_eq!(line.radius, 0.0);
        assert_eq!(line.stroke_width, 1.0);
        assert_eq!(line.extent_x, 0.5);
        assert_eq!(line.extent_y, 0.5);

        // An authored non-zero stroke is part of the outer marker diameter:
        // the path shrinks by half the width and clipping adds it back. Keep
        // the exact overlap boundary pinned for the public scatter-stroke route.
        let stroked = SceneBatch::new(
            layout,
            1,
            2,
            scale,
            scale,
            &[0; 2],
            &[11, 12],
            &[0; 2],
            &[51, 102, 153, 255],
            &[255, 136, 0, 255],
            &[6.0],
            &[20.0; 2],
            &[ScatterSymbol::Circle as u8; 2],
            &[-9.9, -10.1],
            &[40.0; 2],
            &[0.0; 2],
            &[0.0; 2],
        )
        .unwrap()
        .encode();
        assert_eq!(stroked[records + 1], 1);
        assert_eq!(stroked[records + SCENE_BATCH_RECORD_BYTES + 1], 0);
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
            &[0.0],
            &[8.0; 19],
            &codes,
            &x,
            &[0.5; 19],
            &[0.0; 19],
            &[0.0; 19],
        )
        .unwrap()
        .encode();
        assert_eq!(validate_scene_batch(&encoded).unwrap().records, 19);
        let document = SceneDocument::decode(&encoded).unwrap();
        let commands = document.to_raster_commands(1.0).unwrap();
        let painter = document.to_browser_painter(64 * 1024).unwrap();
        assert_eq!(u32::from_le_bytes(painter[20..24].try_into().unwrap()), 19);
        let grid_count = linear_ticks(0.0, 18.0, 3).unwrap().ticks.len()
            + linear_ticks(0.0, 1.0, 3).unwrap().ticks.len();
        let mut offset = 82 + 17 + grid_count * 35; // two backgrounds, clip, grid
        for code in 0..=18 {
            assert_eq!(commands[offset], 4);
            assert_eq!(commands[offset + 13], code);
            assert_eq!(
                f32::from_le_bytes(commands[offset + 18..offset + 22].try_into().unwrap()),
                if code >= ScatterSymbol::PlusLine as u8 {
                    1.0
                } else {
                    0.0
                }
            );
            let descriptor =
                BROWSER_PAINTER_HEADER_BYTES + code as usize * BROWSER_PAINTER_TRACE_BYTES;
            assert_eq!(painter[descriptor], SceneRecordKind::Scatter as u8);
            assert_eq!(painter[descriptor + 1], code);
            assert_eq!(
                f32::from_le_bytes(
                    painter[descriptor + 40..descriptor + 44]
                        .try_into()
                        .unwrap()
                ),
                if code >= ScatterSymbol::PlusLine as u8 {
                    1.0
                } else {
                    0.0
                }
            );
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
    fn canonical_symlog_ticks_share_axis_scale_policy_and_fail_closed() {
        let expected = 2.0 * 1.0_f64.exp_m1();
        let ticks = symlog_ticks(-10.0, 10.0, 2.0, 4).unwrap();
        assert_eq!(ticks.ticks, vec![-expected, 0.0, expected]);
        assert_eq!(ticks.labeled, ticks.ticks);
        assert_eq!(ticks.step, expected);

        let scale = AxisScale::new(ScaleKind::SymLog, -10.0, 10.0, 0.0, 320.0, 2.0, false).unwrap();
        assert_eq!(scale.ticks(320.0, true).unwrap(), ticks);

        let boundary = symlog_ticks(-1e12, 1e12, 1.0, MAX_AXIS_TICKS).unwrap();
        assert!(!boundary.ticks.is_empty());
        assert!(boundary.ticks.len() <= MAX_AXIS_TICKS);
        for (lo, hi, constant, target) in [
            (-1.0, 1.0, 1.0, 0),
            (-1.0, 1.0, 1.0, MAX_AXIS_TICKS + 1),
            (-1.0, 1.0, 0.0, 6),
            (-1.0, 1.0, -1.0, 6),
            (-1.0, 1.0, f64::NAN, 6),
            (-1.0, 1.0, f64::INFINITY, 6),
            (f64::NAN, 1.0, 1.0, 6),
            (-1.0, f64::INFINITY, 1.0, 6),
        ] {
            assert_eq!(
                symlog_ticks(lo, hi, constant, target),
                Err(SceneError::NonFinite)
            );
        }
    }

    #[test]
    fn bounded_numeric_tick_format_owns_affixes_grouping_percent_and_fallback() {
        assert_eq!(
            format_numeric_tick(12_345.678, 1.0, ScaleKind::Linear, Some("$,.1f ms")),
            "$12,345.7 ms"
        );
        assert_eq!(
            format_numeric_tick(0.125, 0.1, ScaleKind::Linear, Some(".1%")),
            "12.5%"
        );
        assert_eq!(
            format_numeric_tick(-2_500.4, 1.0, ScaleKind::SymLog, Some("€,.0f EUR")),
            "€-2,500 EUR"
        );
        assert_eq!(
            format_numeric_tick(0.125, 0.1, ScaleKind::Linear, Some("$.1x")),
            format_numeric_tick(0.125, 0.1, ScaleKind::Linear, None)
        );
        assert_eq!(
            format_numeric_tick(0.001, 1.0, ScaleKind::Log, Some("$,.0f USD")),
            format_numeric_tick(0.001, 1.0, ScaleKind::Log, None)
        );
        assert_eq!(
            format_numeric_tick(
                1.0,
                1.0,
                ScaleKind::Linear,
                Some(&"x".repeat(MAX_SCENE_AXIS_FORMAT_BYTES + 1))
            ),
            "1"
        );
        let boundary = format!(".{MAX_NUMERIC_TICK_FORMAT_PRECISION}f");
        let boundary_label = format_numeric_tick(1.25, 1.0, ScaleKind::Linear, Some(&boundary));
        assert_eq!(boundary_label.len(), MAX_NUMERIC_TICK_FORMAT_PRECISION + 2);
        assert!(boundary_label.starts_with("1.25"));
        let oversized = format!(".{}f", MAX_NUMERIC_TICK_FORMAT_PRECISION + 1);
        assert_eq!(
            format_numeric_tick(1.25, 1.0, ScaleKind::Linear, Some(&oversized)),
            format_numeric_tick(1.25, 1.0, ScaleKind::Linear, None)
        );
    }

    #[test]
    fn angular_and_utc_time_labels_are_deterministic_and_authored_formats_win() {
        assert_eq!(
            format_angular_tick(std::f64::consts::PI / 2.0, 1.0, false, None),
            "π/2"
        );
        assert_eq!(format_angular_tick(22.5, 22.5, true, None), "22.5°");
        assert_eq!(format_angular_tick(0.125, 1.0, true, Some(".1%")), "12.5%");
        assert_eq!(format_time_tick(0.0, 60_000.0, None), "00:00");
        assert_eq!(
            format_time_tick(0.0, 86_400_000.0, Some("%Y-%m-%d %H:%M:%S %b %B")),
            "1970-01-01 00:00:00 Jan January"
        );
        assert_eq!(format_time_tick(-1.0, 1.0, None), "59:59.999");
    }

    #[test]
    fn axis_tick_format_matches_host_branch_order() {
        let cats = ["a", "b", "c"].map(str::to_owned);
        assert_eq!(
            format_axis_tick(
                1.0,
                1.0,
                TICK_FORMAT_KIND_CATEGORY,
                TICK_FORMAT_SCALE_LINEAR,
                TICK_FORMAT_THETA_DEGREES,
                None,
                &cats,
            ),
            "b"
        );
        assert_eq!(
            format_axis_tick(
                std::f64::consts::FRAC_PI_2,
                1.0,
                TICK_FORMAT_KIND_NUMERIC,
                TICK_FORMAT_SCALE_LINEAR,
                TICK_FORMAT_THETA_RADIANS,
                None,
                &[],
            ),
            "π/2"
        );
        assert_eq!(
            format_axis_tick(
                0.001,
                1.0,
                TICK_FORMAT_KIND_NUMERIC,
                TICK_FORMAT_SCALE_LOG,
                TICK_FORMAT_THETA_NONE,
                Some("$,.0f"),
                &[],
            ),
            format_numeric_tick(0.001, 1.0, ScaleKind::Log, None)
        );
        assert_eq!(
            format_axis_tick(
                0.0,
                86_400_000.0,
                TICK_FORMAT_KIND_TIME,
                TICK_FORMAT_SCALE_LINEAR,
                TICK_FORMAT_THETA_NONE,
                Some("%Y-%m-%d"),
                &[],
            ),
            "1970-01-01"
        );
    }

    #[test]
    fn numeric_tick_formats_materialize_canonical_labels_and_preserve_authored_labels() {
        let layout = PlotLayout::new(420.0, 260.0, 50.0, 20.0, 20.0, 40.0).unwrap();
        let x = AxisScale::new(
            ScaleKind::Log,
            0.1,
            100.0,
            layout.left,
            layout.right,
            1.0,
            false,
        )
        .unwrap();
        let y = AxisScale::new(
            ScaleKind::SymLog,
            -10.0,
            10.0,
            layout.bottom,
            layout.top,
            2.0,
            false,
        )
        .unwrap();
        let mut chrome = SceneChromeStyle::default();
        resolve_numeric_tick_formats(layout, x, y, &mut chrome, Some("$,.0f"), Some(".1f units"))
            .unwrap();
        assert!(chrome
            .x_major_ticks
            .as_ref()
            .is_some_and(|ticks| !ticks.is_empty()));
        assert!(!chrome.x_minor_ticks.is_empty());
        assert_eq!(
            chrome.x_major_ticks.as_ref().unwrap().len(),
            chrome.x_tick_labels.as_ref().unwrap().len()
        );
        assert_eq!(chrome.x_tick_labels.as_ref().unwrap()[0], "0.1");
        assert!(chrome
            .y_tick_labels
            .as_ref()
            .unwrap()
            .iter()
            .all(|label| label.ends_with(" units")));

        let mut authored = SceneChromeStyle {
            x_major_ticks: Some(vec![0.1, 1.0]),
            x_tick_labels: Some(vec!["low".into(), "high".into()]),
            ..SceneChromeStyle::default()
        };
        resolve_numeric_tick_formats(layout, x, y, &mut authored, Some("$,.0f"), None).unwrap();
        assert_eq!(authored.x_major_ticks, Some(vec![0.1, 1.0]));
        assert_eq!(
            authored.x_tick_labels,
            Some(vec!["low".into(), "high".into()])
        );
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
    fn scene_v25_band_outline_mode_is_canonical_and_shared_by_consumers() {
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
        let encode = |outline: BandOutline, width: f64, alpha: u8| {
            SceneBatch::new(
                layout,
                1,
                2,
                x,
                y,
                &[3, 3],
                &[9, 9],
                &[0, 0],
                &[57, 99, 235, 180],
                &[17, 24, 39, alpha],
                &[width],
                &[0.0, 0.0],
                &[outline as u8, outline as u8],
                &[0.0, 2.0],
                &[1.0, 1.5],
                &[0.0, 2.0],
                &[0.0, 0.0],
            )
            .unwrap()
            .encode()
        };

        let top = encode(BandOutline::Top, 1.2, 255);
        let perimeter = encode(BandOutline::Perimeter, 1.2, 255);
        let none = encode(BandOutline::Top, 1.2, 0);
        let first_record = SCENE_BATCH_HEADER_BYTES + SCENE_STYLE_RECORD_BYTES;
        assert_eq!(top[first_record + 2], BandOutline::Top as u8);
        assert_eq!(perimeter[first_record + 2], BandOutline::Perimeter as u8);
        assert_eq!(none[first_record + 2], BandOutline::None as u8);

        let top_document = SceneDocument::decode(&top).unwrap();
        let perimeter_document = SceneDocument::decode(&perimeter).unwrap();
        let none_document = SceneDocument::decode(&none).unwrap();
        let top_svg = top_document.to_svg();
        let perimeter_svg = perimeter_document.to_svg();
        let none_svg = none_document.to_svg();
        assert_eq!(top_svg.matches("<path d=\"").count(), 2);
        assert_eq!(perimeter_svg.matches("<path d=\"").count(), 1);
        assert_eq!(none_svg.matches("<path d=\"").count(), 1);
        assert!(top_svg.contains("stroke=\"none\"") && top_svg.contains("fill=\"none\""));
        assert!(!perimeter_svg.contains("stroke=\"none\""));
        assert!(none_svg.contains("stroke=\"none\""));

        let top_raster = top_document.to_raster_commands(1.0).unwrap();
        let perimeter_raster = perimeter_document.to_raster_commands(1.0).unwrap();
        let none_raster = none_document.to_raster_commands(1.0).unwrap();
        let grid_count = top_document.resolved_axis_ticks(true).unwrap().ticks.len()
            + top_document.resolved_axis_ticks(false).unwrap().ticks.len();
        let mark_offset = 82 + 17 + grid_count * 35;
        let stroke_offset = mark_offset + 41;
        assert_eq!(top_raster[mark_offset], 1);
        assert_eq!(top_raster[stroke_offset], 3);
        assert_eq!(
            u32::from_le_bytes(
                top_raster[stroke_offset + 1..stroke_offset + 5]
                    .try_into()
                    .unwrap()
            ),
            2
        );
        assert_eq!(top_raster[stroke_offset + 29], 0);
        assert_eq!(perimeter_raster[stroke_offset], 3);
        assert_eq!(
            u32::from_le_bytes(
                perimeter_raster[stroke_offset + 1..stroke_offset + 5]
                    .try_into()
                    .unwrap()
            ),
            4
        );
        assert_eq!(perimeter_raster[stroke_offset + 45], 1);
        assert_ne!(none_raster[stroke_offset], 3);
        assert_eq!(
            top_document.to_browser_painter(16_384).unwrap()[BROWSER_PAINTER_HEADER_BYTES + 1],
            BandOutline::Top as u8
        );
        assert_eq!(
            perimeter_document.to_browser_painter(16_384).unwrap()
                [BROWSER_PAINTER_HEADER_BYTES + 1],
            BandOutline::Perimeter as u8
        );
        assert_eq!(
            none_document.to_browser_painter(16_384).unwrap()[BROWSER_PAINTER_HEADER_BYTES + 1],
            BandOutline::None as u8
        );
    }

    #[test]
    fn scene_v7_polyfill_triangle_runs_drive_every_consumer_and_clip() {
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
        let legend = SceneLegend {
            location: LegendLocation::UpperRight,
            title: String::new(),
            font_size: 11.0,
            title_font_size: 12.0,
            text_rgba: [32, 32, 32, 255],
            frame_fill_rgba: [255, 255, 255, 230],
            frame_stroke_rgba: [32, 32, 32, 71],
            entries: vec![SceneLegendEntry {
                style_ref: 0,
                kind: SceneRecordKind::PolyFill,
                symbol: 0,
                fill_rgba: [34, 197, 94, 191],
                stroke_rgba: [0, 0, 0, 0],
                label: "literal mesh".into(),
            }],
        };
        let batch = SceneBatch::new_with_decorations(
            layout,
            1,
            2,
            x,
            y,
            SceneChromeStyle::default(),
            SceneChromeText::default(),
            Some(legend),
            &[4, 4, 4, 4, 4, 4],
            &[9, 9, 9, 10, 10, 10],
            &[0, 0, 0, 0, 0, 0],
            &[34, 197, 94, 191],
            &[0, 0, 0, 0],
            &[0.0],
            &[0.0; 6],
            &[0; 6],
            &[-0.25, 0.75, 0.25, 1.0, 2.25, 1.5],
            &[0.25, 0.25, 1.25, 0.5, 0.5, 1.75],
            &[0.0; 6],
            &[0.0; 6],
        )
        .unwrap();
        let encoded = batch.encode();
        assert_eq!(
            u32::from_le_bytes(encoded[4..8].try_into().unwrap()),
            SCENE_VERSION
        );
        let document = SceneDocument::decode(&encoded).unwrap();
        let svg = document.to_svg();
        assert_eq!(svg.matches("<path d=\"M ").count(), 2);
        assert_eq!(svg.matches(" Z\"").count(), 2);
        assert!(svg.contains("<g clip-path=\"url(#xy-scene-plot)\">"));
        assert!(svg.contains("role=\"listitem\"") && svg.contains("literal mesh"));

        let commands = document.to_raster_commands(1.0).unwrap();
        assert_eq!(commands[82], 0); // canonical plot clip follows two backgrounds
        let grid_count = linear_ticks(0.0, 1.0, 3).unwrap().ticks.len() * 2;
        let mark_offset = 82 + 17 + grid_count * 35;
        assert_eq!(commands[mark_offset], 1);
        assert_eq!(
            u32::from_le_bytes(
                commands[mark_offset + 1..mark_offset + 5]
                    .try_into()
                    .unwrap()
            ),
            3
        );
        assert_eq!(commands[mark_offset + 33], 1);
        assert!(commands.windows(12).any(|window| window == b"literal mesh"));

        let painter = document.to_browser_painter(64 * 1024).unwrap();
        assert_eq!(u32::from_le_bytes(painter[20..24].try_into().unwrap()), 2);
        for group in 0..2 {
            let descriptor = BROWSER_PAINTER_HEADER_BYTES + group * BROWSER_PAINTER_TRACE_BYTES;
            assert_eq!(painter[descriptor], SceneRecordKind::PolyFill as u8);
            assert_eq!(
                u32::from_le_bytes(painter[descriptor + 4..descriptor + 8].try_into().unwrap()),
                3
            );
            assert_eq!(
                &painter[descriptor + 32..descriptor + 36],
                &[34, 197, 94, 191]
            );
            assert_eq!(&painter[descriptor + 36..descriptor + 40], &[0, 0, 0, 0]);
            assert_eq!(
                f32::from_le_bytes(
                    painter[descriptor + 40..descriptor + 44]
                        .try_into()
                        .unwrap()
                ),
                0.0
            );
            let id_offset = u32::from_le_bytes(
                painter[descriptor + 24..descriptor + 28]
                    .try_into()
                    .unwrap(),
            ) as usize;
            assert!((0..3).all(|row| {
                u32::from_le_bytes(
                    painter[id_offset + row * 4..id_offset + row * 4 + 4]
                        .try_into()
                        .unwrap(),
                ) == 9 + group as u32
            }));
        }
        let first_x_offset = u32::from_le_bytes(
            painter[BROWSER_PAINTER_HEADER_BYTES + 8..BROWSER_PAINTER_HEADER_BYTES + 12]
                .try_into()
                .unwrap(),
        ) as usize;
        assert!(
            f32::from_le_bytes(
                painter[first_x_offset..first_x_offset + 4]
                    .try_into()
                    .unwrap()
            ) < layout.left as f32
        );
        assert!(painter.windows(4).any(|window| window == b"XYLG"));
    }

    #[test]
    fn polyfill_browser_groups_honor_the_canonical_trace_budget() {
        let make_document = |triangle_count: usize| {
            let layout = PlotLayout::new(120.0, 100.0, 10.0, 10.0, 10.0, 10.0).unwrap();
            let record_count = triangle_count * 3;
            let mut stable_ids = Vec::with_capacity(record_count);
            for triangle in 0..triangle_count as u64 {
                stable_ids.extend_from_slice(&[triangle, triangle, triangle]);
            }
            SceneDocument::decode(
                &SceneBatch::new_with_decorations(
                    layout,
                    1,
                    2,
                    AxisScale::new(ScaleKind::Linear, 0.0, 1.0, 10.0, 110.0, 1.0, false).unwrap(),
                    AxisScale::new(ScaleKind::Linear, 0.0, 1.0, 90.0, 10.0, 1.0, false).unwrap(),
                    SceneChromeStyle::default(),
                    SceneChromeText::default(),
                    None,
                    &vec![SceneRecordKind::PolyFill as u8; record_count],
                    &stable_ids,
                    &vec![0; record_count],
                    &[34, 197, 94, 255],
                    &[0, 0, 0, 0],
                    &[0.0],
                    &vec![0.0; record_count],
                    &vec![0; record_count],
                    &vec![0.5; record_count],
                    &vec![0.5; record_count],
                    &vec![0.0; record_count],
                    &vec![0.0; record_count],
                )
                .unwrap()
                .encode(),
            )
            .unwrap()
        };
        assert_eq!(
            u32::from_le_bytes(
                make_document(MAX_BROWSER_PAINTER_TRACES)
                    .to_browser_painter(1024 * 1024)
                    .unwrap()[20..24]
                    .try_into()
                    .unwrap()
            ) as usize,
            MAX_BROWSER_PAINTER_TRACES
        );
        assert_eq!(
            make_document(MAX_BROWSER_PAINTER_TRACES + 1).to_browser_painter(1024 * 1024),
            Err(SceneError::PainterTraceLimit)
        );
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
    fn polar_scatter_encodes_projected_points_and_svg_rings() {
        let layout = PlotLayout::new(400.0, 400.0, 0.0, 0.0, 0.0, 0.0).unwrap();
        let x = AxisScale::new(ScaleKind::Linear, 0.0, std::f64::consts::PI * 2.0, 0.0, 400.0, 1.0, false)
            .unwrap();
        let y = AxisScale::new(ScaleKind::Linear, 0.0, 1.0, 400.0, 0.0, 1.0, false).unwrap();
        let envelope = polar::PolarEnvelope {
            theta_unit: 0,
            theta_direction: 0,
            n_categories: 0,
            r_scale_kind: 0,
            grid_shape: 0,
            r_mask_nonpositive: false,
            theta_zero: 0.0,
            sector_start: 0.0,
            sector_end: std::f64::consts::PI * 2.0,
            r_lo: 0.0,
            r_hi: 1.0,
            r_origin: f64::NAN,
            hole: 0.0,
            r_constant: 1.0,
        };
        let xypl = polar::encode_xypl(&envelope);
        let kinds = [SceneRecordKind::Scatter as u8];
        let ids = [1u64];
        let styles = [0u32];
        let fill = [37u8, 99, 235, 255];
        let stroke = [0u8, 0, 0, 255];
        let widths = [0.0f64];
        let diameter = [8.0f64];
        let symbols = [0u8];
        let x0 = [0.0f64];
        let y0 = [1.0f64];
        let zeros = [0.0f64];
        let encoded = SceneBatch::new(
            layout,
            1,
            2,
            x,
            y,
            &kinds,
            &ids,
            &styles,
            &fill,
            &stroke,
            &widths,
            &diameter,
            &symbols,
            &x0,
            &y0,
            &zeros,
            &zeros,
        )
        .unwrap()
        .with_polar(&xypl)
        .unwrap()
        .encode();
        assert_eq!(
            u32::from_le_bytes(encoded[4..8].try_into().unwrap()),
            SCENE_VERSION
        );
        assert_eq!(&encoded[encoded.len() - polar::XYPL_V1_BYTES..encoded.len() - polar::XYPL_V1_BYTES + 4], b"XYPL");
        let document = SceneDocument::decode(&encoded).unwrap();
        let record = document.records[0];
        assert!(record.visible);
        // Recut insets polar_label_room (30px) on a 400² zero-margin plot.
        assert!((record.coordinates[0] - 370.0).abs() < 1e-6);
        assert!((record.coordinates[1] - 200.0).abs() < 1e-6);
        let svg = document.to_svg();
        assert!(svg.contains("data-xy-grid=\"ring\"") || svg.contains("<circle"));
        assert!(svg.contains("clipPath"));
        assert!(!svg.contains("<clipPath id=\"xy-scene-plot\"><rect"));
        SceneDocument::decode(&encoded).unwrap();
    }

    #[test]
    fn polar_encode_recuts_cartesian_gutters_to_compat_plot() {
        let layout = PlotLayout::new(400.0, 400.0, 46.0, 8.0, 6.0, 36.0).unwrap();
        let chrome = SceneChromeStyle::default_style();
        let text = SceneChromeText::default();
        let (recut, legend_box) =
            recut_polar_scene_layout(layout, None, &text, None, &chrome).unwrap();
        assert!(legend_box.is_none());
        assert!((recut.left - 30.0).abs() < 1e-9);
        assert!((recut.top - 36.0).abs() < 1e-9);
        assert!((recut.right - 370.0).abs() < 1e-9);
        assert!((recut.bottom - 370.0).abs() < 1e-9);
    }

    #[test]
    fn cartesian_bar_tessellates_rounded_rect_to_polyfill() {
        let layout = PlotLayout::new(240.0, 160.0, 20.0, 20.0, 10.0, 20.0).unwrap();
        let x = AxisScale::new(ScaleKind::Linear, 0.0, 2.0, 20.0, 220.0, 1.0, false).unwrap();
        let y = AxisScale::new(ScaleKind::Linear, 0.0, 3.0, 140.0, 10.0, 1.0, false).unwrap();
        let kinds = [SceneRecordKind::Rect as u8, SceneRecordKind::Rect as u8];
        let ids = [1u64, 1];
        let styles = [0u32, 0];
        let fill = [34u8, 197, 94, 255];
        let stroke = [0u8, 0, 0, 255];
        let widths = [0.0f64];
        let diameter = [0.0f64, 0.0];
        let symbols = [0u8, 0];
        let x0 = [0.2f64, 1.2];
        let y0 = [0.0f64, 0.0];
        let x1 = [0.8f64, 1.8];
        let y1 = [2.0f64, 3.0];
        let encoded = SceneBatch::new(
            layout,
            1,
            2,
            x,
            y,
            &kinds,
            &ids,
            &styles,
            &fill,
            &stroke,
            &widths,
            &diameter,
            &symbols,
            &x0,
            &y0,
            &x1,
            &y1,
        )
        .unwrap()
        .with_corner_radii(vec![Some(SceneCornerRadius {
            r_tip: 8.0,
            r_base: 0.0,
            force_tip_top: false,
            wedge_gap: 0.0,
        })])
        .unwrap()
        .encode();
        let document = SceneDocument::decode(&encoded).unwrap();
        assert!(document
            .records
            .iter()
            .all(|record| record.kind == SceneRecordKind::PolyFill));
        assert!(document.records.len() >= 6);
        let svg = document.to_svg();
        assert_eq!(svg.matches("<path d=\"M").count(), 2);
        assert!(svg.contains("<clipPath id=\"xy-scene-plot\"><rect"));
        assert!(!document
            .records
            .iter()
            .any(|record| record.kind == SceneRecordKind::Rect));
    }

    #[test]
    fn polar_bar_tessellates_rect_to_polyfill_wedge() {
        let layout = PlotLayout::new(400.0, 400.0, 0.0, 0.0, 0.0, 0.0).unwrap();
        let x = AxisScale::new(ScaleKind::Linear, 0.0, std::f64::consts::PI * 2.0, 0.0, 400.0, 1.0, false)
            .unwrap();
        let y = AxisScale::new(ScaleKind::Linear, 0.0, 1.0, 400.0, 0.0, 1.0, false).unwrap();
        let envelope = polar::PolarEnvelope {
            theta_unit: 0,
            theta_direction: 0,
            n_categories: 0,
            r_scale_kind: 0,
            grid_shape: 0,
            r_mask_nonpositive: false,
            theta_zero: 0.0,
            sector_start: 0.0,
            sector_end: std::f64::consts::PI * 2.0,
            r_lo: 0.0,
            r_hi: 1.0,
            r_origin: f64::NAN,
            hole: 0.0,
            r_constant: 1.0,
        };
        let xypl = polar::encode_xypl(&envelope);
        let kinds = [SceneRecordKind::Rect as u8];
        let ids = [1u64];
        let styles = [0u32];
        let fill = [37u8, 99, 235, 255];
        let stroke = [0u8, 0, 0, 255];
        let widths = [0.0f64];
        let diameter = [0.0f64];
        let symbols = [0u8];
        let x0 = [0.0f64];
        let y0 = [0.0f64];
        let x1 = [std::f64::consts::FRAC_PI_2];
        let y1 = [1.0f64];
        let encoded = SceneBatch::new(
            layout,
            1,
            2,
            x,
            y,
            &kinds,
            &ids,
            &styles,
            &fill,
            &stroke,
            &widths,
            &diameter,
            &symbols,
            &x0,
            &y0,
            &x1,
            &y1,
        )
        .unwrap()
        .with_polar(&xypl)
        .unwrap()
        .encode();
        let document = SceneDocument::decode(&encoded).unwrap();
        assert!(document.records.len() >= 3);
        assert!(document
            .records
            .iter()
            .all(|record| record.kind == SceneRecordKind::PolyFill));
        assert!(document.records.iter().all(|record| record.visible));
        assert!(document
            .records
            .iter()
            .all(|record| record.coordinates[0].is_finite() && record.coordinates[1].is_finite()));
        let svg = document.to_svg();
        assert!(svg.contains("<path d=\"M"));
        assert!(!svg.contains("<rect x="));
        assert!(svg.contains("data-xy-grid=\"ring\"") || svg.contains("<circle"));
        assert!(document.to_raster_commands(1.0).unwrap().len() > 100);
    }

    #[test]
    fn polar_bar_wedge_gap_keeps_adjacent_slices_separate() {
        let layout = PlotLayout::new(400.0, 400.0, 0.0, 0.0, 0.0, 0.0).unwrap();
        let x = AxisScale::new(
            ScaleKind::Linear,
            0.0,
            std::f64::consts::PI * 2.0,
            0.0,
            400.0,
            1.0,
            false,
        )
        .unwrap();
        let y = AxisScale::new(ScaleKind::Linear, 0.0, 1.0, 400.0, 0.0, 1.0, false).unwrap();
        let envelope = polar::PolarEnvelope {
            theta_unit: 0,
            theta_direction: 0,
            n_categories: 0,
            r_scale_kind: 0,
            grid_shape: 0,
            r_mask_nonpositive: false,
            theta_zero: 0.0,
            sector_start: 0.0,
            sector_end: std::f64::consts::PI * 2.0,
            r_lo: 0.0,
            r_hi: 1.0,
            r_origin: f64::NAN,
            hole: 0.0,
            r_constant: 1.0,
        };
        let xypl = polar::encode_xypl(&envelope);
        let kinds = [SceneRecordKind::Rect as u8, SceneRecordKind::Rect as u8];
        let ids = [1u64, 1];
        let styles = [0u32, 0];
        let fill = [37u8, 99, 235, 255];
        let stroke = [0u8, 0, 0, 255];
        let widths = [0.0f64];
        let diameter = [0.0f64, 0.0];
        let symbols = [0u8, 0];
        let x0 = [0.0f64, std::f64::consts::FRAC_PI_2];
        let y0 = [0.25f64, 0.25];
        let x1 = [std::f64::consts::FRAC_PI_2, std::f64::consts::PI];
        let y1 = [1.0f64, 1.0];
        let encoded = SceneBatch::new(
            layout,
            1,
            2,
            x,
            y,
            &kinds,
            &ids,
            &styles,
            &fill,
            &stroke,
            &widths,
            &diameter,
            &symbols,
            &x0,
            &y0,
            &x1,
            &y1,
        )
        .unwrap()
        .with_polar(&xypl)
        .unwrap()
        .with_corner_radii(vec![Some(SceneCornerRadius {
            r_tip: 0.0,
            r_base: 0.0,
            force_tip_top: false,
            wedge_gap: 12.0,
        })])
        .unwrap()
        .encode();
        let document = SceneDocument::decode(&encoded).unwrap();
        assert!(document
            .records
            .iter()
            .all(|record| record.kind == SceneRecordKind::PolyFill));
        let svg = document.to_svg();
        assert_eq!(svg.matches("<path d=\"M").count(), 2);
    }

    #[test]
    fn polar_bar_corner_radius_keeps_adjacent_slices_separate() {
        let layout = PlotLayout::new(400.0, 400.0, 0.0, 0.0, 0.0, 0.0).unwrap();
        let x = AxisScale::new(
            ScaleKind::Linear,
            0.0,
            std::f64::consts::PI * 2.0,
            0.0,
            400.0,
            1.0,
            false,
        )
        .unwrap();
        let y = AxisScale::new(ScaleKind::Linear, 0.0, 1.0, 400.0, 0.0, 1.0, false).unwrap();
        let envelope = polar::PolarEnvelope {
            theta_unit: 0,
            theta_direction: 0,
            n_categories: 0,
            r_scale_kind: 0,
            grid_shape: 0,
            r_mask_nonpositive: false,
            theta_zero: 0.0,
            sector_start: 0.0,
            sector_end: std::f64::consts::PI * 2.0,
            r_lo: 0.0,
            r_hi: 1.0,
            r_origin: f64::NAN,
            hole: 0.25,
            r_constant: 1.0,
        };
        let xypl = polar::encode_xypl(&envelope);
        let kinds = [SceneRecordKind::Rect as u8, SceneRecordKind::Rect as u8];
        let ids = [1u64, 1];
        let styles = [0u32, 0];
        let fill = [37u8, 99, 235, 255];
        let stroke = [0u8, 0, 0, 255];
        let widths = [0.0f64];
        let diameter = [0.0f64, 0.0];
        let symbols = [0u8, 0];
        let x0 = [0.0f64, std::f64::consts::FRAC_PI_2];
        let y0 = [0.0f64, 0.0];
        let x1 = [std::f64::consts::FRAC_PI_2, std::f64::consts::PI];
        let y1 = [1.0f64, 1.0];
        let encoded = SceneBatch::new(
            layout,
            1,
            2,
            x,
            y,
            &kinds,
            &ids,
            &styles,
            &fill,
            &stroke,
            &widths,
            &diameter,
            &symbols,
            &x0,
            &y0,
            &x1,
            &y1,
        )
        .unwrap()
        .with_polar(&xypl)
        .unwrap()
        .with_corner_radii(vec![Some(SceneCornerRadius {
            r_tip: 14.0,
            r_base: 14.0,
            force_tip_top: false,
            wedge_gap: 0.0,
        })])
        .unwrap()
        .encode();
        let document = SceneDocument::decode(&encoded).unwrap();
        assert!(document
            .records
            .iter()
            .all(|record| record.kind == SceneRecordKind::PolyFill));
        let svg = document.to_svg();
        assert_eq!(svg.matches("<path d=\"M").count(), 2);
        assert!(!svg.contains("<rect x="));
    }

    #[test]
    fn polar_heatmap_lattice_tessellates_to_polyfill_wedges() {
        let kinds = [SceneRecordKind::Rect as u8, SceneRecordKind::Rect as u8];
        let ids = [9u64, 9];
        let styles = [0u32, 0];
        let diameter = [2.0, 2.0];
        let symbols = [0u8, 0];
        let x0 = [0.0, 0.0];
        let y0 = [0.0, 0.0];
        let x1 = [std::f64::consts::PI, 0.0];
        let y1 = [1.0, 0.0];
        let modes = [
            SceneExpansionMode::HeatmapLattice as u8,
            SceneExpansionMode::HeatmapLattice as u8,
        ];
        let expanded = expand_scene_records(
            SceneExpansionInput {
                kinds: &kinds,
                stable_ids: &ids,
                style_refs: &styles,
                diameter: &diameter,
                symbols: &symbols,
                x0: &x0,
                y0: &y0,
                x1: &x1,
                y1: &y1,
                expansion_modes: &modes,
            },
            test_linear_x_scale(),
            test_linear_y_scale(),
        )
        .unwrap();
        assert_eq!(expanded.kinds.len(), 4);
        assert!(expanded
            .kinds
            .iter()
            .all(|kind| *kind == SceneRecordKind::Rect as u8));

        let layout = PlotLayout::new(400.0, 400.0, 0.0, 0.0, 0.0, 0.0).unwrap();
        let x = AxisScale::new(
            ScaleKind::Linear,
            0.0,
            std::f64::consts::PI,
            0.0,
            400.0,
            1.0,
            false,
        )
        .unwrap();
        let y = AxisScale::new(ScaleKind::Linear, 0.0, 1.0, 400.0, 0.0, 1.0, false).unwrap();
        let envelope = polar::PolarEnvelope {
            theta_unit: 0,
            theta_direction: 0,
            n_categories: 0,
            r_scale_kind: 0,
            grid_shape: 0,
            r_mask_nonpositive: false,
            theta_zero: 0.0,
            sector_start: 0.0,
            sector_end: std::f64::consts::PI,
            r_lo: 0.0,
            r_hi: 1.0,
            r_origin: f64::NAN,
            hole: 0.0,
            r_constant: 1.0,
        };
        let xypl = polar::encode_xypl(&envelope);
        let fill = [37u8, 99, 235, 255];
        let stroke = [0u8, 0, 0, 255];
        let widths = [0.0f64];
        let encoded = SceneBatch::new(
            layout,
            1,
            2,
            x,
            y,
            &expanded.kinds,
            &expanded.stable_ids,
            &expanded.style_refs,
            &fill,
            &stroke,
            &widths,
            &expanded.diameter,
            &expanded.symbols,
            &expanded.x0,
            &expanded.y0,
            &expanded.x1,
            &expanded.y1,
        )
        .unwrap()
        .with_polar(&xypl)
        .unwrap()
        .encode();
        let document = SceneDocument::decode(&encoded).unwrap();
        assert!(document.records.len() >= 12);
        assert!(document
            .records
            .iter()
            .all(|record| record.kind == SceneRecordKind::PolyFill));
        let svg = document.to_svg();
        assert!(svg.contains("<path d=\"M"));
        assert!(!svg.contains("<rect x="));
        assert!(document.to_raster_commands(1.0).unwrap().len() > 100);
    }

    #[test]
    fn cartesian_scene_v26_still_decodes_without_polar_sidecar() {
        let layout = PlotLayout::new(200.0, 120.0, 20.0, 10.0, 20.0, 20.0).unwrap();
        let x = AxisScale::new(ScaleKind::Linear, 0.0, 1.0, layout.left, layout.right, 1.0, false)
            .unwrap();
        let y = AxisScale::new(ScaleKind::Linear, 0.0, 1.0, layout.bottom, layout.top, 1.0, false)
            .unwrap();
        let encoded = SceneBatch::new(
            layout,
            1,
            2,
            x,
            y,
            &[SceneRecordKind::Scatter as u8],
            &[1],
            &[0],
            &[1, 2, 3, 255],
            &[0, 0, 0, 255],
            &[0.0],
            &[4.0],
            &[0],
            &[0.5],
            &[0.5],
            &[0.0],
            &[0.0],
        )
        .unwrap()
        .encode();
        assert_eq!(
            u32::from_le_bytes(encoded[4..8].try_into().unwrap()),
            SCENE_VERSION
        );
        assert_ne!(&encoded[encoded.len().saturating_sub(4)..], b"XYPL");
        let document = SceneDocument::decode(&encoded).unwrap();
        assert!(document.polar.is_none());
        assert!(validate_scene_batch(&encoded).is_ok());
    }

    #[test]
    fn xyat_v2_envelope_preserves_canonical_chrome_trailer() {
        let layout = PlotLayout::new(120.0, 90.0, 10.0, 10.0, 10.0, 10.0).unwrap();
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
        let chrome = SceneChromeStyle {
            chart_background_rgba: [240, 248, 255, 255],
            plot_background_rgba: [248, 250, 252, 255],
            ..SceneChromeStyle::default()
        };
        let batch = SceneBatch::new_with_chrome(
            layout,
            1,
            2,
            x,
            y,
            chrome.clone(),
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
        .unwrap();
        let mut xyat = Vec::new();
        xyat.extend_from_slice(b"XYAT");
        xyat.extend_from_slice(&2u32.to_le_bytes());
        xyat.extend_from_slice(&1u32.to_le_bytes());
        xyat.extend_from_slice(&0.5f64.to_le_bytes());
        xyat.extend_from_slice(&0.5f64.to_le_bytes());
        xyat.extend_from_slice(&[1, 2, 3, 255]);
        xyat.extend_from_slice(&[255, 255, 255, 255]);
        xyat.extend_from_slice(&4u32.to_le_bytes());
        xyat.extend_from_slice(b"note");
        let mut envelope = Vec::new();
        envelope.extend_from_slice(b"XYAD");
        envelope.extend_from_slice(&1u32.to_le_bytes());
        envelope.extend_from_slice(&(xyat.len() as u32).to_le_bytes());
        envelope.extend_from_slice(&0u32.to_le_bytes());
        envelope.extend_from_slice(&0u32.to_le_bytes());
        envelope.extend_from_slice(&xyat);

        let decorated = batch.with_authored_annotations(&envelope).unwrap().encode();
        let body = SCENE_BATCH_HEADER_BYTES;
        assert_eq!(
            &decorated[body..body + 8],
            &[240, 248, 255, 255, 248, 250, 252, 255]
        );
        let painter = SceneDocument::decode(&decorated)
            .unwrap()
            .to_browser_painter(16_384)
            .unwrap();
        let style_input = chrome.style_input();
        assert_eq!(&painter[64..72], &style_input[..8]);
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
        for code in 0..=ScatterSymbol::VerticalLine as u8 {
            let mut symbol_legend = legend.clone();
            symbol_legend.entries[0].symbol = code;
            let symbol_encoded = build(symbol_legend).unwrap().encode();
            let symbol_document = SceneDocument::decode(&symbol_encoded).unwrap();
            assert!(symbol_document.to_svg().contains("role=\"listitem\""));
            assert!(symbol_document.to_raster_commands(1.0).is_ok());
            assert!(symbol_document
                .to_browser_painter(16_384)
                .unwrap()
                .windows(4)
                .any(|bytes| bytes == b"XYLG"));
        }
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
    fn scene_v19_colorbar_is_literal_bounded_and_rejects_unsorted_stops() {
        let colorbar = SceneColorbar {
            horizontal: false,
            domain: [0.0, 1.0],
            stops: vec![(0.0, [0, 0, 0, 255]), (1.0, [255, 255, 255, 255])],
            ticks: None,
            minor_ticks: false,
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
        let ticked = SceneColorbar {
            ticks: Some(vec![0.0, 0.5, 1.0]),
            minor_ticks: true,
            ..colorbar.clone()
        };
        assert_eq!(
            SceneColorbar::from_input(&ticked.encode().unwrap()),
            Ok(Some(ticked))
        );
        let resolved = resolved_colorbar_ticks(
            &SceneColorbar {
                ticks: Some(vec![0.0, 0.5, 1.0]),
                minor_ticks: true,
                ..colorbar.clone()
            },
            (100.0, 10.0, 14.0, 80.0),
        )
        .unwrap();
        assert_eq!(
            resolved
                .majors
                .iter()
                .map(|tick| tick.2.as_str())
                .collect::<Vec<_>>(),
            ["0.0", "0.5", "1.0"]
        );
        assert_eq!(resolved.minors.len(), 8);
        let maximum = SceneColorbar {
            stops: (0..MAX_SCENE_COLORBAR_STOPS)
                .map(|index| (index as f64 / 15.0, [index as u8, 0, 0, 255]))
                .collect(),
            ticks: Some(
                (0..MAX_SCENE_COLORBAR_TICKS)
                    .map(|index| index as f64 / 31.0)
                    .collect(),
            ),
            title: "x".repeat(MAX_SCENE_COLORBAR_TEXT_BYTES),
            ..colorbar.clone()
        };
        let maximum_encoded = maximum.encode().unwrap();
        assert_eq!(maximum_encoded.len(), MAX_SCENE_COLORBAR_INPUT_BYTES);
        assert_eq!(
            SceneColorbar::from_input(&maximum_encoded),
            Ok(Some(maximum))
        );
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
            ticks: None,
            minor_ticks: false,
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

    #[test]
    fn xyaw_v1_resolves_wrapped_literal_lines_and_rejects_unbreakable_tokens() {
        let layout = PlotLayout::new(240.0, 160.0, 20.0, 20.0, 20.0, 20.0).unwrap();
        let x = AxisScale::new(ScaleKind::Linear, 0.0, 1.0, 20.0, 220.0, 1.0, false).unwrap();
        let y = AxisScale::new(ScaleKind::Linear, 0.0, 1.0, 140.0, 20.0, 1.0, false).unwrap();
        let text = b"one two";
        let mut frame = b"XYAW\x01\0\0\0\x01\0\0\0".to_vec();
        for value in [0.5f64, 0.5, 0.0, 0.0, 24.0] {
            frame.extend_from_slice(&value.to_le_bytes());
        }
        frame.extend_from_slice(&[1, 2, 3, 255, 255, 255, 255, 255, 0, 0, 0, 0]);
        frame.extend_from_slice(&0.0f64.to_le_bytes());
        frame.extend_from_slice(&[0, 0, 0, 0]);
        frame.extend_from_slice(&(text.len() as u32).to_le_bytes());
        frame.extend_from_slice(text);
        let (labels, boxes, callouts) = decode_xyaw(&frame, x, y, layout).unwrap();
        assert_eq!(labels[0].text, "one\ntwo");
        assert!(boxes[0].is_some());
        assert!(callouts.is_empty());
        frame[12 + 32..12 + 40].copy_from_slice(&1.0f64.to_le_bytes());
        assert!(decode_xyaw(&frame, x, y, layout).is_err());
    }
}
