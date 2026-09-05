//! Versioned, bounded multi-Scene static document (M2 #873).
//!
//! Native hosts marshal literal placement facts into `XYST`; Rust validates
//! the complete document and owns SVG structure, raster composition, PDF
//! lowering, and image encoding. No host renderer participates after this
//! boundary is selected.

use crate::colormap;
use crate::jpeg;
use crate::legend_layout::{legend_box_layout, LegendBoxLayout, LegendBoxRequest};
use crate::pdf;
use crate::png_encode;
use crate::raster;
use crate::scene::SceneDocument;
use crate::scene_static::{flatten_rgba_over_white, scene_static_export, SceneStaticFormat};
use crate::textblock;
use crate::webp;

const MAGIC: &[u8; 4] = b"XYST";
const VERSION: u32 = 1;
const HEADER_BYTES: usize = 64;
const PANEL_BYTES: usize = 104;
const FLAG_BACKGROUND: u32 = 1 << 0;
const FLAG_OPTIMIZE_PNG: u32 = 1 << 1;
const FLAG_TIGHT_CROP: u32 = 1 << 2;
const FLAG_TITLE_X_CENTER: u32 = 1 << 3;
const FLAGS: u32 =
    FLAG_BACKGROUND | FLAG_OPTIMIZE_PNG | FLAG_TIGHT_CROP | FLAG_TITLE_X_CENTER;
const PANEL_FLAG_X_CHROME_METRICS: u32 = 1 << 0;
const PANEL_FLAG_Y_CHROME_METRICS: u32 = 1 << 1;
const PANEL_FLAG_COLORBAR_LAYOUT: u32 = 1 << 2;
const PANEL_FLAG_ANNOTATION_FONT_SIZE: u32 = 1 << 3;
const PANEL_FLAG_ARROW_METRICS: u32 = 1 << 4;
const PANEL_FLAG_AXIS_SIDES: u32 = 1 << 5;
const PANEL_FLAG_ANNOTATION_TEXT_FLAGS: u32 = 1 << 6;
const PANEL_FLAG_ANNOTATION_PADDING: u32 = 1 << 7;
const PANEL_FLAG_TITLE_STYLE: u32 = 1 << 8;
const PANEL_FLAG_ANNOTATION_VERTICAL_ALIGN: u32 = 1 << 9;
const PANEL_FLAG_COLORBAR_LOG_SCALE: u32 = 1 << 10;
const PANEL_FLAG_COLORBAR_EXTEND_MIN: u32 = 1 << 11;
const PANEL_FLAG_COLORBAR_EXTEND_MAX: u32 = 1 << 12;
const PANEL_FLAG_COLORBAR_PYPLOT_LABEL: u32 = 1 << 13;
const PANEL_FLAG_COLORBAR_FILL_PLOT: u32 = 1 << 24;
const PANEL_FLAGS: u32 = PANEL_FLAG_X_CHROME_METRICS
    | PANEL_FLAG_Y_CHROME_METRICS
    | PANEL_FLAG_COLORBAR_LAYOUT
    | PANEL_FLAG_ANNOTATION_FONT_SIZE
    | PANEL_FLAG_ARROW_METRICS
    | PANEL_FLAG_AXIS_SIDES
    | PANEL_FLAG_ANNOTATION_TEXT_FLAGS
    | PANEL_FLAG_ANNOTATION_PADDING
    | PANEL_FLAG_TITLE_STYLE
    | PANEL_FLAG_ANNOTATION_VERTICAL_ALIGN
    | PANEL_FLAG_COLORBAR_LOG_SCALE
    | PANEL_FLAG_COLORBAR_EXTEND_MIN
    | PANEL_FLAG_COLORBAR_EXTEND_MAX
    | PANEL_FLAG_COLORBAR_PYPLOT_LABEL
    | PANEL_FLAG_COLORBAR_FILL_PLOT;
const MAX_PANELS: usize = 256;
const MAX_TITLE_BYTES: usize = 4096;
const MAX_DECORATION_BYTES: usize = 1 << 20;
const MAX_DOCUMENT_LABELS: usize = 64;
const MAX_DOCUMENT_BYTES: usize = 256 * 1024 * 1024;
const MAX_DIMENSION: usize = 65_535;
const MAX_PIXELS: usize = 268_435_456;

#[derive(Clone, Debug, Eq, PartialEq)]
pub enum StaticDocumentError {
    Header,
    Version,
    Flags,
    Limit,
    Panel,
    Title,
    Scene,
    Raster,
    Encode,
}

#[derive(Clone, Copy, Debug)]
struct PanelRecord {
    x: i32,
    y: i32,
    width: usize,
    height: usize,
    offset: usize,
    len: usize,
    metric_flags: u32,
    x_metrics: [f64; 3],
    y_metrics: [f64; 3],
    colorbar_layout: [f64; 3],
    annotation_font_size: f64,
    arrow_metrics: [f64; 3],
    axis_sides: u32,
    annotation_text_flags: u32,
    annotation_padding: f64,
    title_size: f64,
    title_rgba: [u8; 4],
    annotation_vertical_align: u32,
}

#[derive(Clone, Debug)]
struct DocumentLabel {
    x_fraction: f32,
    y_fraction: f32,
    size: f32,
    rotation: f32,
    opacity: f32,
    rgba: [u8; 4],
    anchor: u8,
    vertical_align: u8,
    text_flags: u8,
    text: String,
}

#[derive(Clone, Debug)]
struct DocumentLegendItem {
    kind: u8,
    dashed: bool,
    rgba: [u8; 4],
    width: f32,
    size: f32,
    opacity: f32,
    name: String,
}

#[derive(Clone, Debug)]
struct DocumentLegend {
    ncols: u32,
    font_size: f32,
    handle_length: f32,
    handle_text_pad: f32,
    padding_em: f32,
    row_gap_em: f32,
    border_pad: f32,
    anchor: Option<[f32; 2]>,
    text_rgba: [u8; 4],
    background_rgba: [u8; 4],
    border_rgba: [u8; 4],
    title: String,
    location: String,
    items: Vec<DocumentLegendItem>,
}

pub struct StaticDocument {
    width: usize,
    height: usize,
    flags: u32,
    background: [u8; 4],
    title_rgba: [u8; 4],
    title_size: f32,
    title_x: f32,
    title_y: f32,
    title_anchor: u8,
    title_flags: u8,
    title: String,
    labels: Vec<DocumentLabel>,
    legend: Option<DocumentLegend>,
    colorbar: Option<String>,
    crop_padding: usize,
    panels: Vec<(PanelRecord, SceneDocument, Vec<u8>)>,
}

fn u32_at(bytes: &[u8], at: usize) -> Result<u32, StaticDocumentError> {
    Ok(u32::from_le_bytes(
        bytes
            .get(at..at + 4)
            .ok_or(StaticDocumentError::Header)?
            .try_into()
            .unwrap(),
    ))
}

fn i32_at(bytes: &[u8], at: usize) -> Result<i32, StaticDocumentError> {
    Ok(i32::from_le_bytes(
        bytes
            .get(at..at + 4)
            .ok_or(StaticDocumentError::Header)?
            .try_into()
            .unwrap(),
    ))
}

fn f32_at(bytes: &[u8], at: usize) -> Result<f32, StaticDocumentError> {
    Ok(f32::from_le_bytes(
        bytes
            .get(at..at + 4)
            .ok_or(StaticDocumentError::Header)?
            .try_into()
            .unwrap(),
    ))
}

fn decode_decorations(
    bytes: &[u8],
) -> Result<(Vec<DocumentLabel>, Option<DocumentLegend>, Option<String>), StaticDocumentError> {
    if bytes.is_empty() {
        return Ok((Vec::new(), None, None));
    }
    if bytes.len() < 32 || &bytes[..4] != b"XYDD" || u32_at(bytes, 4)? != 1 {
        return Err(StaticDocumentError::Panel);
    }
    let count = u32_at(bytes, 8)? as usize;
    let legend_len = u32_at(bytes, 12)? as usize;
    let colorbar_len = u32_at(bytes, 16)? as usize;
    if count > MAX_DOCUMENT_LABELS
        || legend_len > MAX_DECORATION_BYTES
        || colorbar_len > 256
        || bytes[20..32] != [0; 12]
    {
        return Err(StaticDocumentError::Limit);
    }
    let mut at = 32usize;
    let mut labels = Vec::with_capacity(count);
    for _ in 0..count {
        let record = bytes.get(at..at + 40).ok_or(StaticDocumentError::Panel)?;
        let text_len = u32_at(record, 28)? as usize;
        if record[27] != 0 || u32_at(record, 32)? != 0 || u32_at(record, 36)? != 0 {
            return Err(StaticDocumentError::Panel);
        }
        let end = at
            .checked_add(40)
            .and_then(|value| value.checked_add(text_len))
            .ok_or(StaticDocumentError::Limit)?;
        let text = std::str::from_utf8(bytes.get(at + 40..end).ok_or(StaticDocumentError::Panel)?)
            .map_err(|_| StaticDocumentError::Title)?
            .to_owned();
        let label = DocumentLabel {
            x_fraction: f32_at(record, 0)?,
            y_fraction: f32_at(record, 4)?,
            size: f32_at(record, 8)?,
            rotation: f32_at(record, 12)?,
            opacity: f32_at(record, 16)?,
            rgba: record[20..24].try_into().unwrap(),
            anchor: record[24],
            vertical_align: record[25],
            text_flags: record[26],
            text,
        };
        if !label.x_fraction.is_finite()
            || !label.y_fraction.is_finite()
            || !label.size.is_finite()
            || !(1.0..=4096.0).contains(&label.size)
            || !label.rotation.is_finite()
            || !label.opacity.is_finite()
            || !(0.0..=1.0).contains(&label.opacity)
            || label.anchor > 2
            || label.vertical_align > 3
            || label.text_flags & !0b11 != 0
            || label.text.bytes().any(|byte| byte == 0)
        {
            return Err(StaticDocumentError::Title);
        }
        labels.push(label);
        at = end;
    }
    let legend_end = at
        .checked_add(legend_len)
        .ok_or(StaticDocumentError::Limit)?;
    let legend = if legend_len == 0 {
        None
    } else {
        Some(decode_document_legend(
            bytes
                .get(at..legend_end)
                .ok_or(StaticDocumentError::Panel)?,
        )?)
    };
    let colorbar_end = legend_end
        .checked_add(colorbar_len)
        .ok_or(StaticDocumentError::Limit)?;
    if colorbar_end != bytes.len() {
        return Err(StaticDocumentError::Panel);
    }
    let colorbar = if colorbar_len == 0 {
        None
    } else {
        Some(
            std::str::from_utf8(&bytes[legend_end..colorbar_end])
                .map_err(|_| StaticDocumentError::Title)?
                .to_owned(),
        )
    };
    Ok((labels, legend, colorbar))
}

fn decode_document_legend(bytes: &[u8]) -> Result<DocumentLegend, StaticDocumentError> {
    if bytes.len() < 64 {
        return Err(StaticDocumentError::Panel);
    }
    let item_count = u32_at(bytes, 0)? as usize;
    let title_len = u32_at(bytes, 4)? as usize;
    let location_len = u32_at(bytes, 8)? as usize;
    let ncols = u32_at(bytes, 12)?;
    if item_count > 256 || ncols == 0 || ncols > 256 || bytes[60] > 1 || bytes[61..64] != [0; 3] {
        return Err(StaticDocumentError::Limit);
    }
    let numeric = [
        f32_at(bytes, 16)?,
        f32_at(bytes, 20)?,
        f32_at(bytes, 24)?,
        f32_at(bytes, 28)?,
        f32_at(bytes, 32)?,
        f32_at(bytes, 36)?,
    ];
    let anchor = [f32_at(bytes, 52)?, f32_at(bytes, 56)?];
    if numeric.iter().any(|value| !value.is_finite())
        || numeric[0] <= 0.0
        || numeric[1..].iter().any(|value| *value < 0.0)
        || anchor.iter().any(|value| !value.is_finite())
        || (bytes[60] == 0 && anchor != [0.0; 2])
    {
        return Err(StaticDocumentError::Panel);
    }
    let title_at = 64usize;
    let location_at = title_at
        .checked_add(title_len)
        .ok_or(StaticDocumentError::Limit)?;
    let items_at = location_at
        .checked_add(location_len)
        .ok_or(StaticDocumentError::Limit)?;
    let title = std::str::from_utf8(
        bytes
            .get(title_at..location_at)
            .ok_or(StaticDocumentError::Panel)?,
    )
    .map_err(|_| StaticDocumentError::Title)?
    .to_owned();
    let location = std::str::from_utf8(
        bytes
            .get(location_at..items_at)
            .ok_or(StaticDocumentError::Panel)?,
    )
    .map_err(|_| StaticDocumentError::Title)?
    .to_owned();
    let mut at = items_at;
    let mut items = Vec::with_capacity(item_count);
    for _ in 0..item_count {
        let record = bytes.get(at..at + 28).ok_or(StaticDocumentError::Panel)?;
        let name_len = u32_at(record, 20)? as usize;
        let end = at
            .checked_add(28)
            .and_then(|value| value.checked_add(name_len))
            .ok_or(StaticDocumentError::Limit)?;
        let item = DocumentLegendItem {
            kind: record[0],
            dashed: record[1] != 0,
            rgba: record[4..8].try_into().unwrap(),
            width: f32_at(record, 8)?,
            size: f32_at(record, 12)?,
            opacity: f32_at(record, 16)?,
            name: std::str::from_utf8(bytes.get(at + 28..end).ok_or(StaticDocumentError::Panel)?)
                .map_err(|_| StaticDocumentError::Title)?
                .to_owned(),
        };
        if item.kind > 2
            || record[2..4] != [0; 2]
            || u32_at(record, 24)? != 0
            || !item.width.is_finite()
            || item.width < 0.0
            || !item.size.is_finite()
            || item.size <= 0.0
            || !item.opacity.is_finite()
            || !(0.0..=1.0).contains(&item.opacity)
        {
            return Err(StaticDocumentError::Panel);
        }
        items.push(item);
        at = end;
    }
    if at != bytes.len() || title.bytes().any(|byte| byte == 0) || location.is_empty() {
        return Err(StaticDocumentError::Panel);
    }
    Ok(DocumentLegend {
        ncols,
        font_size: numeric[0],
        handle_length: numeric[1],
        handle_text_pad: numeric[2],
        padding_em: numeric[3],
        row_gap_em: numeric[4],
        border_pad: numeric[5],
        anchor: (bytes[60] != 0).then_some(anchor),
        text_rgba: bytes[40..44].try_into().unwrap(),
        background_rgba: bytes[44..48].try_into().unwrap(),
        border_rgba: bytes[48..52].try_into().unwrap(),
        title,
        location,
        items,
    })
}

impl StaticDocument {
    pub fn decode(bytes: &[u8]) -> Result<Self, StaticDocumentError> {
        if bytes.len() < HEADER_BYTES || bytes.len() > MAX_DOCUMENT_BYTES || &bytes[..4] != MAGIC {
            return Err(StaticDocumentError::Header);
        }
        if u32_at(bytes, 4)? != VERSION {
            return Err(StaticDocumentError::Version);
        }
        let width = u32_at(bytes, 8)? as usize;
        let height = u32_at(bytes, 12)? as usize;
        let flags = u32_at(bytes, 16)?;
        let panel_count = u32_at(bytes, 20)? as usize;
        let title_len = u32_at(bytes, 24)? as usize;
        let decorations_len = u32_at(bytes, 52)? as usize;
        let crop_padding = u32_at(bytes, 56)? as usize;
        if flags & !FLAGS != 0 || bytes[60..64] != [0; 4] {
            return Err(StaticDocumentError::Flags);
        }
        if width == 0
            || height == 0
            || width > MAX_DIMENSION
            || height > MAX_DIMENSION
            || panel_count == 0
            || panel_count > MAX_PANELS
            || title_len > MAX_TITLE_BYTES
            || decorations_len > MAX_DECORATION_BYTES
            || crop_padding > MAX_DIMENSION
        {
            return Err(StaticDocumentError::Limit);
        }
        let table_end = HEADER_BYTES
            .checked_add(
                panel_count
                    .checked_mul(PANEL_BYTES)
                    .ok_or(StaticDocumentError::Limit)?,
            )
            .ok_or(StaticDocumentError::Limit)?;
        let decorations_at = table_end
            .checked_add(title_len)
            .ok_or(StaticDocumentError::Limit)?;
        let scenes_at = decorations_at
            .checked_add(decorations_len)
            .ok_or(StaticDocumentError::Limit)?;
        if scenes_at > bytes.len() {
            return Err(StaticDocumentError::Header);
        }
        let title = std::str::from_utf8(&bytes[table_end..decorations_at])
            .map_err(|_| StaticDocumentError::Title)?
            .to_owned();
        if title.bytes().any(|byte| byte == 0) {
            return Err(StaticDocumentError::Title);
        }
        let title_size = f32_at(bytes, 36)?;
        let raw_title_x = f32_at(bytes, 40)?;
        let title_y = f32_at(bytes, 44)?;
        let title_anchor = bytes[48];
        let title_flags = bytes[49];
        if bytes[50..52] != [0; 2]
            || title_anchor > 2
            || title_flags & !0b11 != 0
            || !title_size.is_finite()
            || !raw_title_x.is_finite()
            || !title_y.is_finite()
            || (!title.is_empty() && title_size <= 0.0)
        {
            return Err(StaticDocumentError::Title);
        }
        if flags & FLAG_TITLE_X_CENTER != 0 && bytes[40..44] != [0; 4] {
            return Err(StaticDocumentError::Flags);
        }
        let title_x = if flags & FLAG_TITLE_X_CENTER != 0 {
            width as f32 / 2.0
        } else {
            raw_title_x
        };
        let background: [u8; 4] = bytes[28..32].try_into().unwrap();
        let title_rgba: [u8; 4] = bytes[32..36].try_into().unwrap();
        let (labels, legend, colorbar) = decode_decorations(&bytes[decorations_at..scenes_at])?;
        let mut panels = Vec::with_capacity(panel_count);
        let mut expected_offset = 0usize;
        for index in 0..panel_count {
            let at = HEADER_BYTES + index * PANEL_BYTES;
            let record = PanelRecord {
                x: i32_at(bytes, at)?,
                y: i32_at(bytes, at + 4)?,
                width: u32_at(bytes, at + 8)? as usize,
                height: u32_at(bytes, at + 12)? as usize,
                offset: u32_at(bytes, at + 16)? as usize,
                len: u32_at(bytes, at + 20)? as usize,
                metric_flags: u32_at(bytes, at + 24)?,
                annotation_font_size: f64::from(f32_at(bytes, at + 28)?),
                x_metrics: [
                    f64::from(f32_at(bytes, at + 32)?),
                    f64::from(f32_at(bytes, at + 36)?),
                    f64::from(f32_at(bytes, at + 40)?),
                ],
                y_metrics: [
                    f64::from(f32_at(bytes, at + 44)?),
                    f64::from(f32_at(bytes, at + 48)?),
                    f64::from(f32_at(bytes, at + 52)?),
                ],
                colorbar_layout: [
                    f64::from(f32_at(bytes, at + 56)?),
                    f64::from(f32_at(bytes, at + 60)?),
                    f64::from(f32_at(bytes, at + 64)?),
                ],
                arrow_metrics: [
                    f64::from(f32_at(bytes, at + 68)?),
                    f64::from(f32_at(bytes, at + 72)?),
                    f64::from(f32_at(bytes, at + 76)?),
                ],
                axis_sides: u32_at(bytes, at + 80)?,
                annotation_text_flags: u32_at(bytes, at + 84)?,
                annotation_padding: f64::from(f32_at(bytes, at + 88)?),
                title_size: f64::from(f32_at(bytes, at + 92)?),
                title_rgba: bytes[at + 96..at + 100].try_into().unwrap(),
                annotation_vertical_align: u32_at(bytes, at + 100)?,
            };
            if record.width == 0
                || record.height == 0
                || record.len == 0
                || record.offset != expected_offset
                || i64::from(record.x) >= width as i64
                || i64::from(record.y) >= height as i64
                || i64::from(record.x) + record.width as i64 <= 0
                || i64::from(record.y) + record.height as i64 <= 0
                || record.metric_flags & !PANEL_FLAGS != 0
                || (record.metric_flags & PANEL_FLAG_X_CHROME_METRICS == 0
                    && bytes[at + 32..at + 44] != [0; 12])
                || (record.metric_flags & PANEL_FLAG_Y_CHROME_METRICS == 0
                    && bytes[at + 44..at + 56] != [0; 12])
                || (record.metric_flags & PANEL_FLAG_COLORBAR_LAYOUT == 0
                    && bytes[at + 56..at + 68] != [0; 12])
                || (record.metric_flags & PANEL_FLAG_ANNOTATION_FONT_SIZE == 0
                    && u32_at(bytes, at + 28)? != 0)
                || (record.metric_flags & PANEL_FLAG_ARROW_METRICS == 0
                    && bytes[at + 68..at + 80] != [0; 12])
                || (record.metric_flags & PANEL_FLAG_AXIS_SIDES == 0 && record.axis_sides != 0)
                || record.axis_sides & !0x0303 != 0
                || record.annotation_text_flags & !0b11 != 0
                || (record.metric_flags & PANEL_FLAG_ANNOTATION_TEXT_FLAGS == 0
                    && record.annotation_text_flags != 0)
                || (record.metric_flags & PANEL_FLAG_ANNOTATION_PADDING == 0
                    && u32_at(bytes, at + 88)? != 0)
                || (record.metric_flags & PANEL_FLAG_TITLE_STYLE == 0
                    && bytes[at + 92..at + 100] != [0; 8])
                || record.annotation_vertical_align > 3
                || (record.metric_flags & PANEL_FLAG_ANNOTATION_VERTICAL_ALIGN == 0
                    && record.annotation_vertical_align != 0)
            {
                return Err(StaticDocumentError::Panel);
            }
            let start = scenes_at
                .checked_add(record.offset)
                .ok_or(StaticDocumentError::Limit)?;
            let end = start
                .checked_add(record.len)
                .ok_or(StaticDocumentError::Limit)?;
            let scene_bytes = bytes
                .get(start..end)
                .ok_or(StaticDocumentError::Panel)?
                .to_vec();
            let mut scene =
                SceneDocument::decode(&scene_bytes).map_err(|_| StaticDocumentError::Scene)?;
            let (scene_width, scene_height) = scene.viewport_size();
            if scene_width != record.width as f64 || scene_height != record.height as f64 {
                return Err(StaticDocumentError::Panel);
            }
            scene
                .apply_static_chrome_metrics(
                    (record.metric_flags & PANEL_FLAG_X_CHROME_METRICS != 0)
                        .then_some(record.x_metrics),
                    (record.metric_flags & PANEL_FLAG_Y_CHROME_METRICS != 0)
                        .then_some(record.y_metrics),
                )
                .map_err(|_| StaticDocumentError::Panel)?;
            scene
                .apply_static_colorbar_layout(
                    (record.metric_flags & PANEL_FLAG_COLORBAR_LAYOUT != 0)
                        .then_some(record.colorbar_layout),
                    record.metric_flags & PANEL_FLAG_COLORBAR_FILL_PLOT != 0,
                )
                .map_err(|_| StaticDocumentError::Panel)?;
            let colorbar_style_flags = record.metric_flags
                & (PANEL_FLAG_COLORBAR_LOG_SCALE
                    | PANEL_FLAG_COLORBAR_EXTEND_MIN
                    | PANEL_FLAG_COLORBAR_EXTEND_MAX
                    | PANEL_FLAG_COLORBAR_PYPLOT_LABEL);
            if colorbar_style_flags != 0 {
                scene
                    .apply_static_colorbar_style(
                        colorbar_style_flags & PANEL_FLAG_COLORBAR_LOG_SCALE != 0,
                        u8::from(colorbar_style_flags & PANEL_FLAG_COLORBAR_EXTEND_MIN != 0)
                            | (u8::from(
                                colorbar_style_flags & PANEL_FLAG_COLORBAR_EXTEND_MAX != 0,
                            ) << 1),
                        colorbar_style_flags & PANEL_FLAG_COLORBAR_PYPLOT_LABEL != 0,
                    )
                    .map_err(|_| StaticDocumentError::Panel)?;
            }
            scene
                .apply_static_annotation_font_size(
                    (record.metric_flags & PANEL_FLAG_ANNOTATION_FONT_SIZE != 0)
                        .then_some(record.annotation_font_size),
                )
                .map_err(|_| StaticDocumentError::Panel)?;
            scene
                .apply_static_arrow_metrics(
                    (record.metric_flags & PANEL_FLAG_ARROW_METRICS != 0)
                        .then_some(record.arrow_metrics),
                )
                .map_err(|_| StaticDocumentError::Panel)?;
            scene
                .apply_static_axis_sides(
                    (record.metric_flags & PANEL_FLAG_AXIS_SIDES != 0)
                        .then_some((record.axis_sides & 0xff) as u8),
                    (record.metric_flags & PANEL_FLAG_AXIS_SIDES != 0)
                        .then_some(((record.axis_sides >> 8) & 0xff) as u8),
                )
                .map_err(|_| StaticDocumentError::Panel)?;
            scene
                .apply_static_annotation_text_flags(
                    (record.metric_flags & PANEL_FLAG_ANNOTATION_TEXT_FLAGS != 0)
                        .then_some(record.annotation_text_flags as u8),
                )
                .map_err(|_| StaticDocumentError::Panel)?;
            scene
                .apply_static_annotation_padding(
                    (record.metric_flags & PANEL_FLAG_ANNOTATION_PADDING != 0)
                        .then_some(record.annotation_padding),
                )
                .map_err(|_| StaticDocumentError::Panel)?;
            scene
                .apply_static_title_style(
                    (record.metric_flags & PANEL_FLAG_TITLE_STYLE != 0)
                        .then_some((record.title_size, record.title_rgba)),
                )
                .map_err(|_| StaticDocumentError::Panel)?;
            scene
                .apply_static_annotation_vertical_align(
                    (record.metric_flags & PANEL_FLAG_ANNOTATION_VERTICAL_ALIGN != 0)
                        .then_some(record.annotation_vertical_align as u8),
                )
                .map_err(|_| StaticDocumentError::Panel)?;
            if flags & FLAG_BACKGROUND != 0 {
                scene.clear_backgrounds();
            }
            expected_offset = record
                .offset
                .checked_add(record.len)
                .ok_or(StaticDocumentError::Limit)?;
            panels.push((record, scene, scene_bytes));
        }
        if scenes_at.checked_add(expected_offset) != Some(bytes.len()) {
            return Err(StaticDocumentError::Panel);
        }
        Ok(Self {
            width,
            height,
            flags,
            background,
            title_rgba,
            title_size,
            title_x,
            title_y,
            title_anchor,
            title_flags,
            title,
            labels,
            legend,
            colorbar,
            crop_padding,
            panels,
        })
    }

    pub fn export(
        &self,
        format: SceneStaticFormat,
        scale: f64,
        quality: i32,
    ) -> Result<Vec<u8>, StaticDocumentError> {
        if self.flags == 0
            && self.title.is_empty()
            && self.labels.is_empty()
            && self.legend.is_none()
            && self.colorbar.is_none()
            && self.panels.len() == 1
        {
            let (record, _scene, encoded) = &self.panels[0];
            if record.x == 0
                && record.y == 0
                && record.width == self.width
                && record.height == self.height
                && record.metric_flags == 0
            {
                return scene_static_export(
                    encoded,
                    format,
                    scale,
                    if matches!(format, SceneStaticFormat::Svg | SceneStaticFormat::Pdf) {
                        self.width
                    } else {
                        scaled_dimension(self.width, scale)?
                    },
                    if matches!(format, SceneStaticFormat::Svg | SceneStaticFormat::Pdf) {
                        self.height
                    } else {
                        scaled_dimension(self.height, scale)?
                    },
                    quality,
                )
                .map_err(|_| StaticDocumentError::Encode);
            }
        }
        match format {
            SceneStaticFormat::Svg => Ok(self.to_svg().into_bytes()),
            SceneStaticFormat::Pdf => {
                pdf::svg_to_pdf(&self.to_svg()).map_err(|_| StaticDocumentError::Encode)
            }
            SceneStaticFormat::Png | SceneStaticFormat::Jpeg | SceneStaticFormat::Webp => {
                self.export_raster(format, scale, quality)
            }
        }
    }

    fn to_svg(&self) -> String {
        let mut out = format!(
            "<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"{}\" height=\"{}\" viewBox=\"0 0 {} {}\">",
            self.width, self.height, self.width, self.height
        );
        if self.flags & FLAG_BACKGROUND != 0 {
            out.push_str(&format!(
                "<rect width=\"{}\" height=\"{}\" fill=\"{}\"/>",
                self.width,
                self.height,
                document_background_css(self.background)
            ));
        }
        if !self.title.is_empty() {
            let anchor = ["start", "middle", "end"][self.title_anchor as usize];
            for (line, text) in self.title.split('\n').enumerate() {
                out.push_str(&format!(
                    "<text data-xy-static-title=\"\" x=\"{}\" y=\"{}\" text-anchor=\"{}\" font-size=\"{}\" fill=\"{}\"{}{}>",
                    self.title_x,
                    self.title_y + line as f32 * self.title_size * 1.2,
                    anchor,
                    self.title_size,
                    rgba_css(self.title_rgba),
                    if self.title_flags & 1 != 0 { " font-style=\"italic\"" } else { "" },
                    if self.title_flags & 2 != 0 { " font-weight=\"700\"" } else { "" },
                ));
                push_escaped(&mut out, text);
                out.push_str("</text>");
            }
        }
        for (index, (record, scene, _encoded)) in self.panels.iter().enumerate() {
            let svg = scene.to_svg();
            let start = svg.find('>').map(|at| at + 1).unwrap_or(0);
            let end = svg.rfind("</svg>").unwrap_or(svg.len());
            let prefix = format!("xy-doc-{index}-xy-scene-");
            let inner = svg[start..end].replace("xy-scene-", &prefix);
            out.push_str(&format!(
                "<svg x=\"{}\" y=\"{}\" data-xy-static-panel=\"{}\" width=\"{}\" height=\"{}\" viewBox=\"0 0 {} {}\">{} </svg>",
                record.x,
                record.y,
                index,
                record.width,
                record.height,
                record.width,
                record.height,
                inner
            ));
        }
        if let Some(name) = &self.colorbar {
            let stops = colormap::colormap_named_stops(name);
            out.push_str("<defs><linearGradient id=\"xy-static-colorbar\">");
            let denominator = stops.len().saturating_sub(1).max(1);
            for (index, rgb) in stops.iter().enumerate() {
                out.push_str("<stop offset=\"");
                out.push_str(&(index as f64 / denominator as f64).to_string());
                out.push_str("\" stop-color=\"rgb(");
                out.push_str(&format!("{},{},{}", rgb[0], rgb[1], rgb[2]));
                out.push_str(")\"/>");
            }
            out.push_str("</linearGradient></defs><rect data-xy-static-colorbar=\"\" x=\"");
            out.push_str(&(self.width as f64 * 0.15).floor().to_string());
            out.push_str("\" y=\"");
            out.push_str(&(self.height.saturating_sub(40)).to_string());
            out.push_str("\" width=\"");
            out.push_str(&(self.width as f64 * 0.7).floor().to_string());
            out.push_str("\" height=\"16\" fill=\"url(#xy-static-colorbar)\"/>");
        }
        for label in &self.labels {
            let Some((x, baseline, block)) = self.document_label_layout(label) else {
                continue;
            };
            let anchor = ["start", "middle", "end"][label.anchor as usize];
            let rgba = label_rgba(label);
            out.push_str("<text data-xy-static-label=\"\" x=\"");
            out.push_str(&x.to_string());
            out.push_str("\" y=\"");
            out.push_str(&baseline.to_string());
            out.push_str("\" text-anchor=\"");
            out.push_str(anchor);
            out.push_str("\" font-size=\"");
            out.push_str(&label.size.to_string());
            out.push_str("\" fill=\"");
            out.push_str(&rgba_css(rgba));
            out.push('"');
            if label.text_flags & 1 != 0 {
                out.push_str(" font-style=\"italic\"");
            }
            if label.text_flags & 2 != 0 {
                out.push_str(" font-weight=\"700\"");
            }
            if label.rotation != 0.0 {
                out.push_str(" transform=\"rotate(");
                out.push_str(&(-label.rotation).to_string());
                out.push(' ');
                out.push_str(&x.to_string());
                out.push(' ');
                out.push_str(&baseline.to_string());
                out.push_str(")\"");
            }
            out.push('>');
            for (index, line) in block.lines.iter().enumerate() {
                if index == 0 {
                    push_escaped(&mut out, line);
                } else {
                    out.push_str("<tspan x=\"");
                    out.push_str(&x.to_string());
                    out.push_str("\" dy=\"");
                    out.push_str(&block.line_step.to_string());
                    out.push_str("\">");
                    push_escaped(&mut out, line);
                    out.push_str("</tspan>");
                }
            }
            out.push_str("</text>");
        }
        if let Some((legend, layout)) = self.document_legend_layout() {
            out.push_str("<g data-xy-static-legend=\"\"><rect x=\"");
            out.push_str(&layout.x.to_string());
            out.push_str("\" y=\"");
            out.push_str(&layout.y.to_string());
            out.push_str("\" width=\"");
            out.push_str(&layout.box_w.to_string());
            out.push_str("\" height=\"");
            out.push_str(&layout.box_h.to_string());
            out.push_str("\" fill=\"");
            out.push_str(&rgba_css(legend.background_rgba));
            out.push_str("\" stroke=\"");
            out.push_str(&rgba_css(legend.border_rgba));
            out.push_str("\"/>");
            if let Some(title) = &layout.title {
                out.push_str("<text x=\"");
                out.push_str(&(layout.x + layout.box_w * 0.5).to_string());
                out.push_str("\" y=\"");
                out.push_str(&(layout.y + layout.pad * 0.5 + layout.font_size * 0.82).to_string());
                out.push_str("\" text-anchor=\"middle\" font-size=\"");
                out.push_str(&layout.font_size.to_string());
                out.push_str("\" fill=\"");
                out.push_str(&rgba_css(legend.text_rgba));
                out.push_str("\">");
                push_escaped(&mut out, title);
                out.push_str("</text>");
            }
            for (index, item) in legend
                .items
                .iter()
                .take(layout.visible_count as usize)
                .enumerate()
            {
                let column = index % layout.ncols as usize;
                let row = index / layout.ncols as usize;
                let x = layout.x + layout.column_offsets[column];
                let y = layout.y + layout.pad * 0.5 + layout.title_h + row as f64 * layout.line_h;
                let center_y = y + layout.text_h * 0.5;
                let rgba = legend_item_rgba(item);
                match item.kind {
                    0 => {
                        out.push_str("<line x1=\"");
                        out.push_str(&x.to_string());
                        out.push_str("\" y1=\"");
                        out.push_str(&center_y.to_string());
                        out.push_str("\" x2=\"");
                        out.push_str(&(x + layout.handle).to_string());
                        out.push_str("\" y2=\"");
                        out.push_str(&center_y.to_string());
                        out.push_str("\" stroke=\"");
                        out.push_str(&rgba_css(rgba));
                        out.push_str("\" stroke-width=\"");
                        out.push_str(&item.width.to_string());
                        if item.dashed {
                            out.push_str("\" stroke-dasharray=\"4,3");
                        }
                        out.push_str("\"/>");
                    }
                    1 => {
                        out.push_str("<circle cx=\"");
                        out.push_str(&(x + layout.handle * 0.5).to_string());
                        out.push_str("\" cy=\"");
                        out.push_str(&center_y.to_string());
                        out.push_str("\" r=\"");
                        out.push_str(&(f64::from(item.size) * 0.5).to_string());
                        out.push_str("\" fill=\"");
                        out.push_str(&rgba_css(rgba));
                        out.push_str("\"/>");
                    }
                    _ => {
                        out.push_str("<rect x=\"");
                        out.push_str(&x.to_string());
                        out.push_str("\" y=\"");
                        out.push_str(&(center_y - layout.swatch_h * 0.5).to_string());
                        out.push_str("\" width=\"");
                        out.push_str(&layout.handle.to_string());
                        out.push_str("\" height=\"");
                        out.push_str(&layout.swatch_h.to_string());
                        out.push_str("\" fill=\"");
                        out.push_str(&rgba_css(rgba));
                        out.push_str("\"/>");
                    }
                }
                out.push_str("<text x=\"");
                out.push_str(&(x + layout.handle + layout.gap).to_string());
                out.push_str("\" y=\"");
                out.push_str(&(y + layout.font_size * 0.82).to_string());
                out.push_str("\" font-size=\"");
                out.push_str(&layout.font_size.to_string());
                out.push_str("\" fill=\"");
                out.push_str(&rgba_css(legend.text_rgba));
                out.push_str("\">");
                push_escaped(&mut out, &layout.names[index]);
                out.push_str("</text>");
            }
            out.push_str("</g>");
        }
        out.push_str("</svg>");
        out
    }

    fn document_label_layout(
        &self,
        label: &DocumentLabel,
    ) -> Option<(f64, f64, textblock::TextBlock)> {
        let block = textblock::measure(
            &label.text,
            f64::from(label.size),
            textblock::LINE_HEIGHT,
            None,
        )?;
        let desired = (1.0 - f64::from(label.y_fraction)) * self.height as f64;
        let trailing = (block.line_count().saturating_sub(1)) as f64 * block.line_step;
        let baseline = match label.vertical_align {
            0 => desired + block.ascent,
            1 => desired,
            2 => desired - trailing - block.descent,
            _ => desired + (block.ascent - trailing - block.descent) * 0.5,
        };
        Some((
            f64::from(label.x_fraction) * self.width as f64,
            baseline,
            block,
        ))
    }

    fn document_legend_layout(&self) -> Option<(&DocumentLegend, LegendBoxLayout)> {
        let legend = self.legend.as_ref()?;
        let names: Vec<&str> = legend.items.iter().map(|item| item.name.as_str()).collect();
        let layout = legend_box_layout(LegendBoxRequest {
            plot_x: 0.0,
            plot_y: 0.0,
            plot_w: self.width as f64,
            plot_h: self.height as f64,
            names: &names,
            title: (!legend.title.is_empty()).then_some(legend.title.as_str()),
            loc: &legend.location,
            font_size: f64::from(legend.font_size),
            handlelength: Some(f64::from(legend.handle_length)),
            handletextpad: Some(f64::from(legend.handle_text_pad)),
            handleheight: None,
            ncols: legend.ncols,
            padding_em: f64::from(legend.padding_em),
            row_gap_em: f64::from(legend.row_gap_em),
            anchor: legend
                .anchor
                .map(|anchor| (f64::from(anchor[0]), f64::from(anchor[1]), 0.0, 0.0)),
            border_axes_pad: f64::from(legend.border_pad),
        })?;
        Some((legend, layout))
    }

    fn export_raster(
        &self,
        format: SceneStaticFormat,
        scale: f64,
        quality: i32,
    ) -> Result<Vec<u8>, StaticDocumentError> {
        if !scale.is_finite() || scale <= 0.0 {
            return Err(StaticDocumentError::Raster);
        }
        let mut width = scaled_dimension(self.width, scale)?;
        let mut height = scaled_dimension(self.height, scale)?;
        if width
            .checked_mul(height)
            .filter(|count| *count <= MAX_PIXELS)
            .is_none()
        {
            return Err(StaticDocumentError::Limit);
        }
        let len = width
            .checked_mul(height)
            .and_then(|count| count.checked_mul(4))
            .ok_or(StaticDocumentError::Limit)?;
        let mut canvas = vec![0u8; len];
        let base = if self.flags & FLAG_BACKGROUND != 0 {
            self.background
        } else {
            [255, 255, 255, 255]
        };
        for pixel in canvas.chunks_exact_mut(4) {
            pixel.copy_from_slice(&base);
        }
        for (record, scene, _encoded) in &self.panels {
            let panel_width = scaled_dimension(record.width, scale)?;
            let panel_height = scaled_dimension(record.height, scale)?;
            let panel_len = panel_width
                .checked_mul(panel_height)
                .filter(|count| *count <= MAX_PIXELS)
                .and_then(|count| count.checked_mul(4))
                .ok_or(StaticDocumentError::Limit)?;
            let mut panel = vec![0u8; panel_len];
            let commands = scene
                .to_raster_commands(scale)
                .map_err(|_| StaticDocumentError::Scene)?;
            if !raster::rasterize_into(&commands, panel_width, panel_height, &mut panel) {
                return Err(StaticDocumentError::Raster);
            }
            composite(
                &mut canvas,
                width,
                height,
                &panel,
                panel_width,
                panel_height,
                scaled_signed_coordinate(record.x, scale)?,
                scaled_signed_coordinate(record.y, scale)?,
            );
        }
        if let Some(name) = &self.colorbar {
            let stops = colormap::colormap_named_stops(name);
            let x0 = (width as f64 * 0.15).floor() as usize;
            let x1 = (width as f64 * 0.85).floor() as usize;
            let y0 = height.saturating_sub(scaled_coordinate(40, scale)?);
            let bar_height = scaled_dimension(16, scale)?;
            if !stops.is_empty() && x1 > x0 {
                for y in y0..(y0 + bar_height).min(height) {
                    for x in x0..x1.min(width) {
                        let stop = ((x - x0) * stops.len() / (x1 - x0)).min(stops.len() - 1);
                        let at = (y * width + x) * 4;
                        canvas[at..at + 3].copy_from_slice(&stops[stop]);
                        canvas[at + 3] = 255;
                    }
                }
            }
        }
        if !self.title.is_empty() || !self.labels.is_empty() || self.legend.is_some() {
            let mut overlay = vec![0u8; len];
            let mut commands = Vec::new();
            for (line, text) in self.title.split('\n').enumerate() {
                commands.push(if self.title_flags == 0 { 6 } else { 17 });
                commands.extend_from_slice(&(self.title_x * scale as f32).to_le_bytes());
                commands.extend_from_slice(
                    &((self.title_y + line as f32 * self.title_size * 1.2) * scale as f32)
                        .to_le_bytes(),
                );
                commands.push(self.title_anchor);
                commands.extend_from_slice(&(self.title_size * scale as f32).to_le_bytes());
                if self.title_flags != 0 {
                    commands.extend_from_slice(&0f32.to_le_bytes());
                    commands.push(self.title_flags);
                    commands.extend_from_slice(&0u32.to_le_bytes());
                }
                commands.extend_from_slice(&self.title_rgba);
                commands.extend_from_slice(&(text.len() as u32).to_le_bytes());
                commands.extend_from_slice(text.as_bytes());
            }
            for label in &self.labels {
                let Some((x, baseline, block)) = self.document_label_layout(label) else {
                    return Err(StaticDocumentError::Raster);
                };
                let rgba = label_rgba(label);
                for (index, line) in block.lines.iter().enumerate() {
                    commands.push(17);
                    commands.extend_from_slice(&((x * scale) as f32).to_le_bytes());
                    let y = ((baseline + index as f64 * block.line_step) * scale) as f32;
                    commands.extend_from_slice(&y.to_le_bytes());
                    commands.push(label.anchor);
                    commands.extend_from_slice(&(label.size * scale as f32).to_le_bytes());
                    commands.extend_from_slice(&(-label.rotation).to_le_bytes());
                    commands.push(label.text_flags);
                    commands.extend_from_slice(&0u32.to_le_bytes());
                    commands.extend_from_slice(&rgba);
                    commands.extend_from_slice(&(line.len() as u32).to_le_bytes());
                    commands.extend_from_slice(line.as_bytes());
                }
            }
            if let Some((legend, layout)) = self.document_legend_layout() {
                push_document_rect(
                    &mut commands,
                    layout.x,
                    layout.y,
                    layout.box_w,
                    layout.box_h,
                    legend.background_rgba,
                    scale,
                );
                for (x0, y0, x1, y1) in [
                    (layout.x, layout.y, layout.x + layout.box_w, layout.y),
                    (
                        layout.x + layout.box_w,
                        layout.y,
                        layout.x + layout.box_w,
                        layout.y + layout.box_h,
                    ),
                    (
                        layout.x + layout.box_w,
                        layout.y + layout.box_h,
                        layout.x,
                        layout.y + layout.box_h,
                    ),
                    (layout.x, layout.y + layout.box_h, layout.x, layout.y),
                ] {
                    push_document_line(
                        &mut commands,
                        x0,
                        y0,
                        x1,
                        y1,
                        1.0,
                        legend.border_rgba,
                        false,
                        scale,
                    );
                }
                if let Some(title) = &layout.title {
                    push_document_text(
                        &mut commands,
                        layout.x + layout.box_w * 0.5,
                        layout.y + layout.pad * 0.5 + layout.font_size * 0.82,
                        1,
                        layout.font_size,
                        legend.text_rgba,
                        title,
                        scale,
                    );
                }
                for (index, item) in legend
                    .items
                    .iter()
                    .take(layout.visible_count as usize)
                    .enumerate()
                {
                    let column = index % layout.ncols as usize;
                    let row = index / layout.ncols as usize;
                    let x = layout.x + layout.column_offsets[column];
                    let y =
                        layout.y + layout.pad * 0.5 + layout.title_h + row as f64 * layout.line_h;
                    let center_y = y + layout.text_h * 0.5;
                    let rgba = legend_item_rgba(item);
                    match item.kind {
                        0 => push_document_line(
                            &mut commands,
                            x,
                            center_y,
                            x + layout.handle,
                            center_y,
                            f64::from(item.width),
                            rgba,
                            item.dashed,
                            scale,
                        ),
                        1 => push_document_point(
                            &mut commands,
                            x + layout.handle * 0.5,
                            center_y,
                            f64::from(item.size) * 0.5,
                            rgba,
                            scale,
                        ),
                        _ => push_document_rect(
                            &mut commands,
                            x,
                            center_y - layout.swatch_h * 0.5,
                            layout.handle,
                            layout.swatch_h,
                            rgba,
                            scale,
                        ),
                    }
                    push_document_text(
                        &mut commands,
                        x + layout.handle + layout.gap,
                        y + layout.font_size * 0.82,
                        0,
                        layout.font_size,
                        legend.text_rgba,
                        &layout.names[index],
                        scale,
                    );
                }
            }
            if !raster::rasterize_into(&commands, width, height, &mut overlay) {
                return Err(StaticDocumentError::Raster);
            }
            composite(&mut canvas, width, height, &overlay, width, height, 0, 0);
        }
        if self.flags & FLAG_TIGHT_CROP != 0 {
            let padding = scaled_coordinate(self.crop_padding, scale)?;
            if let Some((cropped, cropped_width, cropped_height)) =
                crop_to_content(&canvas, width, height, base, padding)
            {
                canvas = cropped;
                width = cropped_width;
                height = cropped_height;
            }
        }
        match format {
            SceneStaticFormat::Png => png_encode::encode_png(
                &canvas,
                width,
                height,
                4,
                if self.flags & FLAG_OPTIMIZE_PNG != 0 {
                    0
                } else {
                    1
                },
                if self.flags & FLAG_OPTIMIZE_PNG != 0 {
                    9
                } else {
                    1
                },
            )
            .map_err(|_| StaticDocumentError::Encode),
            SceneStaticFormat::Jpeg => {
                let rgb = flatten_rgba_over_white(&canvas, width, height)
                    .map_err(|_| StaticDocumentError::Encode)?;
                jpeg::encode_jpeg(&rgb, width, height, 3, quality)
                    .map_err(|_| StaticDocumentError::Encode)
            }
            SceneStaticFormat::Webp => webp::encode_webp(&canvas, width, height, 4)
                .map_err(|_| StaticDocumentError::Encode),
            SceneStaticFormat::Svg | SceneStaticFormat::Pdf => unreachable!(),
        }
    }
}

fn scaled_dimension(value: usize, scale: f64) -> Result<usize, StaticDocumentError> {
    let value = (value as f64 * scale).round();
    if !value.is_finite() || value < 1.0 || value > MAX_DIMENSION as f64 {
        return Err(StaticDocumentError::Limit);
    }
    Ok(value as usize)
}

fn scaled_coordinate(value: usize, scale: f64) -> Result<usize, StaticDocumentError> {
    let value = (value as f64 * scale).round();
    if !value.is_finite() || value < 0.0 || value > MAX_DIMENSION as f64 {
        return Err(StaticDocumentError::Limit);
    }
    Ok(value as usize)
}

fn scaled_signed_coordinate(value: i32, scale: f64) -> Result<isize, StaticDocumentError> {
    let value = (f64::from(value) * scale).round();
    if !value.is_finite() || value.abs() > MAX_DIMENSION as f64 {
        return Err(StaticDocumentError::Limit);
    }
    Ok(value as isize)
}

fn push_document_f32(out: &mut Vec<u8>, value: f64, scale: f64) {
    out.extend_from_slice(&((value * scale) as f32).to_le_bytes());
}

fn push_document_rect(
    out: &mut Vec<u8>,
    x: f64,
    y: f64,
    width: f64,
    height: f64,
    rgba: [u8; 4],
    scale: f64,
) {
    out.push(1);
    out.extend_from_slice(&4u32.to_le_bytes());
    for (px, py) in [
        (x, y),
        (x + width, y),
        (x + width, y + height),
        (x, y + height),
    ] {
        push_document_f32(out, px, scale);
        push_document_f32(out, py, scale);
    }
    out.extend_from_slice(&rgba);
}

#[allow(clippy::too_many_arguments)]
fn push_document_line(
    out: &mut Vec<u8>,
    x0: f64,
    y0: f64,
    x1: f64,
    y1: f64,
    width: f64,
    rgba: [u8; 4],
    dashed: bool,
    scale: f64,
) {
    out.push(3);
    out.extend_from_slice(&2u32.to_le_bytes());
    for (x, y) in [(x0, y0), (x1, y1)] {
        push_document_f32(out, x, scale);
        push_document_f32(out, y, scale);
    }
    push_document_f32(out, width, scale);
    out.extend_from_slice(&rgba);
    out.push(0);
    out.extend_from_slice(&(if dashed { 2u32 } else { 0 }).to_le_bytes());
    if dashed {
        push_document_f32(out, 4.0, scale);
        push_document_f32(out, 3.0, scale);
    }
    out.push(1);
}

fn push_document_point(out: &mut Vec<u8>, x: f64, y: f64, radius: f64, rgba: [u8; 4], scale: f64) {
    out.push(4);
    push_document_f32(out, x, scale);
    push_document_f32(out, y, scale);
    push_document_f32(out, radius, scale);
    out.push(0);
    out.extend_from_slice(&rgba);
    push_document_f32(out, 0.0, scale);
    out.extend_from_slice(&[0; 4]);
}

fn push_document_text(
    out: &mut Vec<u8>,
    x: f64,
    y: f64,
    anchor: u8,
    size: f64,
    rgba: [u8; 4],
    text: &str,
    scale: f64,
) {
    out.push(6);
    push_document_f32(out, x, scale);
    push_document_f32(out, y, scale);
    out.push(anchor);
    push_document_f32(out, size, scale);
    out.extend_from_slice(&rgba);
    out.extend_from_slice(&(text.len() as u32).to_le_bytes());
    out.extend_from_slice(text.as_bytes());
}

fn composite(
    destination: &mut [u8],
    destination_width: usize,
    destination_height: usize,
    source: &[u8],
    source_width: usize,
    source_height: usize,
    x: isize,
    y: isize,
) {
    let source_x = (-x).max(0) as usize;
    let source_y = (-y).max(0) as usize;
    let destination_x = x.max(0) as usize;
    let destination_y = y.max(0) as usize;
    let rows = source_height
        .saturating_sub(source_y)
        .min(destination_height.saturating_sub(destination_y));
    let cols = source_width
        .saturating_sub(source_x)
        .min(destination_width.saturating_sub(destination_x));
    for row in 0..rows {
        for col in 0..cols {
            let src = ((source_y + row) * source_width + source_x + col) * 4;
            let dst = ((destination_y + row) * destination_width + destination_x + col) * 4;
            let alpha = u16::from(source[src + 3]);
            if alpha == 0 {
                continue;
            }
            if alpha == 255 {
                destination[dst..dst + 4].copy_from_slice(&source[src..src + 4]);
                continue;
            }
            let dst_alpha = u16::from(destination[dst + 3]);
            let out_alpha = alpha * 255 + dst_alpha * (255 - alpha);
            for channel in 0..3 {
                let numerator = u32::from(source[src + channel]) * u32::from(alpha) * 255
                    + u32::from(destination[dst + channel])
                        * u32::from(dst_alpha)
                        * u32::from(255 - alpha);
                destination[dst + channel] =
                    ((numerator + u32::from(out_alpha) / 2) / u32::from(out_alpha)) as u8;
            }
            destination[dst + 3] = ((out_alpha + 127) / 255) as u8;
        }
    }
}

fn crop_to_content(
    rgba: &[u8],
    width: usize,
    height: usize,
    background: [u8; 4],
    padding: usize,
) -> Option<(Vec<u8>, usize, usize)> {
    let mut min_x = width;
    let mut min_y = height;
    let mut max_x = 0usize;
    let mut max_y = 0usize;
    let mut found = false;
    for y in 0..height {
        for x in 0..width {
            let at = (y * width + x) * 4;
            if rgba[at..at + 4] == background {
                continue;
            }
            found = true;
            min_x = min_x.min(x);
            min_y = min_y.min(y);
            max_x = max_x.max(x);
            max_y = max_y.max(y);
        }
    }
    if !found {
        return None;
    }
    min_x = min_x.saturating_sub(padding);
    min_y = min_y.saturating_sub(padding);
    max_x = max_x.saturating_add(padding).min(width - 1);
    max_y = max_y.saturating_add(padding).min(height - 1);
    let cropped_width = max_x - min_x + 1;
    let cropped_height = max_y - min_y + 1;
    let mut out = Vec::with_capacity(cropped_width * cropped_height * 4);
    for y in min_y..=max_y {
        let start = (y * width + min_x) * 4;
        out.extend_from_slice(&rgba[start..start + cropped_width * 4]);
    }
    Some((out, cropped_width, cropped_height))
}

fn rgba_css(rgba: [u8; 4]) -> String {
    if rgba[3] == 255 {
        format!("rgb({},{},{})", rgba[0], rgba[1], rgba[2])
    } else {
        format!(
            "rgba({},{},{},{:.6})",
            rgba[0],
            rgba[1],
            rgba[2],
            f64::from(rgba[3]) / 255.0
        )
    }
}

fn document_background_css(rgba: [u8; 4]) -> String {
    if rgba[3] == 255 {
        format!("#{:02x}{:02x}{:02x}", rgba[0], rgba[1], rgba[2])
    } else {
        rgba_css(rgba)
    }
}

fn label_rgba(label: &DocumentLabel) -> [u8; 4] {
    let mut rgba = label.rgba;
    rgba[3] = (f32::from(rgba[3]) * label.opacity).round() as u8;
    rgba
}

fn legend_item_rgba(item: &DocumentLegendItem) -> [u8; 4] {
    let mut rgba = item.rgba;
    rgba[3] = (f32::from(rgba[3]) * item.opacity).round() as u8;
    rgba
}

fn push_escaped(out: &mut String, text: &str) {
    for ch in text.chars() {
        match ch {
            '&' => out.push_str("&amp;"),
            '<' => out.push_str("&lt;"),
            '>' => out.push_str("&gt;"),
            '"' => out.push_str("&quot;"),
            '\'' => out.push_str("&apos;"),
            _ => out.push(ch),
        }
    }
}

pub fn static_document_export(
    encoded: &[u8],
    format: SceneStaticFormat,
    scale: f64,
    quality: i32,
) -> Result<Vec<u8>, StaticDocumentError> {
    StaticDocument::decode(encoded)?.export(format, scale, quality)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn rejects_unknown_version_and_empty_panels() {
        let mut bytes = vec![0u8; HEADER_BYTES];
        bytes[..4].copy_from_slice(MAGIC);
        bytes[4..8].copy_from_slice(&2u32.to_le_bytes());
        assert!(matches!(
            StaticDocument::decode(&bytes),
            Err(StaticDocumentError::Version)
        ));
        bytes[4..8].copy_from_slice(&VERSION.to_le_bytes());
        bytes[8..12].copy_from_slice(&10u32.to_le_bytes());
        bytes[12..16].copy_from_slice(&10u32.to_le_bytes());
        assert!(matches!(
            StaticDocument::decode(&bytes),
            Err(StaticDocumentError::Limit)
        ));
    }

    #[test]
    fn rgba_css_is_stable() {
        assert_eq!(rgba_css([1, 2, 3, 255]), "rgb(1,2,3)");
        assert_eq!(rgba_css([1, 2, 3, 0]), "rgba(1,2,3,0.000000)");
    }

    #[test]
    fn styled_document_label_emits_well_formed_attributes() {
        let document = StaticDocument {
            width: 100,
            height: 80,
            flags: 0,
            background: [0; 4],
            title_rgba: [0; 4],
            title_size: 14.0,
            title_x: 50.0,
            title_y: 16.0,
            title_anchor: 1,
            title_flags: 0,
            title: String::new(),
            labels: vec![DocumentLabel {
                x_fraction: 0.5,
                y_fraction: 0.5,
                size: 12.0,
                rotation: 0.0,
                opacity: 1.0,
                rgba: [1, 2, 3, 255],
                anchor: 1,
                vertical_align: 3,
                text_flags: 3,
                text: "Label".into(),
            }],
            legend: None,
            colorbar: None,
            crop_padding: 0,
            panels: Vec::new(),
        };
        let svg = document.to_svg();
        assert!(svg.contains(
            "fill=\"rgb(1,2,3)\" font-style=\"italic\" font-weight=\"700\">Label</text>"
        ));
        assert!(!svg.contains("font-weight=\"700\"\">"));
    }
}
