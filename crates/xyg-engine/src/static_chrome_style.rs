//! XYCS static chrome-style projection (#1004; dossier §21/§28).
//!
//! Hosts marshal authored title / axis-title / tick-label slot styles, the
//! root theme and per-axis overrides as tagged facts. This module is the only
//! owner of admission, the precedence rule and the resolved text decisions
//! (size, paint, normal/bold, normal/italic) that Scene / StaticDocument
//! consume for SVG, raster and PDF. Validation is bounded and atomic: the
//! first violation returns a stable reason and no partial result.
//!
//! Precedence, highest first (absent = missing key, null, or empty text):
//! * axis title size / paint: axis style `label_size` / `label_color`, then
//!   the `axis_title` slot, then the root theme (`--chart-text`, paint only),
//!   then the canonical default (size 12, Scene paint).
//! * tick-label size / paint: axis style `tick_label_size` (alias
//!   `tick_size`) / `tick_label_color`, then the `tick_label` slot, then the
//!   root theme (paint only), then the canonical default (size 12, Scene
//!   paint).
//! * title size / paint: the `title` slot, then the root theme, then the
//!   canonical default (size 14, `#262626`).
//! * weight and style come only from the slot; tick padding only from the
//!   axis style (default 4).
//!
//! Root `font-size` is admitted and validated but inert: the canonical theme
//! gives every chrome slot an explicit pixel size, so it never reaches them.
use crate::css::{color_rgba8, parse_color, Checked};
use crate::scene::MAX_SCENE_CHROME_LENGTH;
use std::collections::BTreeMap;

const MAX_BYTES: usize = 256 * 1024;
const MAX_TEXT: usize = 4096;
const MAX_ENTRIES: usize = 64;
const MAX_SLOTS: usize = 8;

const DEFAULT_TICK_SIZE: f64 = 12.0;
const DEFAULT_LABEL_SIZE: f64 = 12.0;
const DEFAULT_TICK_PADDING: f64 = 4.0;
const DEFAULT_TITLE_SIZE: f64 = 14.0;
const DEFAULT_TITLE_RGBA: [u8; 4] = [0x26, 0x26, 0x26, 0xff];
const SIZE_KEYS: [&str; 4] = ["tick_label_size", "tick_size", "label_size", "tick_padding"];

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum ChromeStyleError {
    Header,
    Version,
    Flags,
    Limit,
    Text,
    BrowserCss,
    CustomFont,
    Slot,
    FontSize,
    Color,
    FontWeight,
    FontStyle,
    AxisStyle,
}

impl ChromeStyleError {
    pub fn reason(self) -> &'static str {
        match self {
            Self::Header => "XYG_STATIC_CHROME_STYLE_HEADER",
            Self::Version => "XYG_STATIC_CHROME_STYLE_VERSION",
            Self::Flags => "XYG_STATIC_CHROME_STYLE_FLAGS",
            Self::Limit => "XYG_STATIC_CHROME_STYLE_LIMIT",
            Self::Text => "XYG_STATIC_CHROME_STYLE_TEXT",
            Self::BrowserCss => "XYG_STATIC_UNSUPPORTED_BROWSER_CSS",
            Self::CustomFont => "XYG_STATIC_UNSUPPORTED_CUSTOM_FONT",
            Self::Slot => "XYG_STATIC_UNSUPPORTED_CHROME_STYLE",
            Self::FontSize => "XYG_STATIC_UNSUPPORTED_CHROME_FONT_SIZE",
            Self::Color => "XYG_STATIC_UNSUPPORTED_CHROME_COLOR",
            Self::FontWeight => "XYG_STATIC_UNSUPPORTED_CHROME_FONT_WEIGHT",
            Self::FontStyle => "XYG_STATIC_UNSUPPORTED_CHROME_FONT_STYLE",
            Self::AxisStyle => "XYG_STATIC_UNSUPPORTED_CHROME_AXIS_STYLE",
        }
    }
}
type Result<T> = std::result::Result<T, ChromeStyleError>;

#[derive(Clone, Copy, Debug, PartialEq)]
enum Value<'a> {
    Null,
    Text(&'a str),
    Number(f64),
    Bool(bool),
    Opaque,
}
type Entries<'a> = BTreeMap<&'a str, Value<'a>>;

struct Reader<'a> {
    bytes: &'a [u8],
    at: usize,
}
impl<'a> Reader<'a> {
    fn take(&mut self, n: usize) -> Result<&'a [u8]> {
        let end = self.at.checked_add(n).ok_or(ChromeStyleError::Limit)?;
        let value = self
            .bytes
            .get(self.at..end)
            .ok_or(ChromeStyleError::Header)?;
        self.at = end;
        Ok(value)
    }
    fn u32(&mut self) -> Result<u32> {
        Ok(u32::from_le_bytes(self.take(4)?.try_into().unwrap()))
    }
    fn text(&mut self) -> Result<&'a str> {
        let n = self.u32()? as usize;
        if n > MAX_TEXT {
            return Err(ChromeStyleError::Limit);
        }
        let bytes = self.take(n)?;
        if bytes.contains(&0) {
            return Err(ChromeStyleError::Text);
        }
        std::str::from_utf8(bytes).map_err(|_| ChromeStyleError::Text)
    }
    fn value(&mut self) -> Result<Value<'a>> {
        match self.u32()? {
            0 => Ok(Value::Null),
            1 => Ok(Value::Text(self.text()?)),
            2 => Ok(Value::Number(f64::from_le_bytes(
                self.take(8)?.try_into().unwrap(),
            ))),
            3 => match self.u32()? {
                0 => Ok(Value::Bool(false)),
                1 => Ok(Value::Bool(true)),
                _ => Err(ChromeStyleError::Flags),
            },
            4 => Ok(Value::Opaque),
            _ => Err(ChromeStyleError::Flags),
        }
    }
    fn entries(&mut self) -> Result<Entries<'a>> {
        let count = self.u32()? as usize;
        if count > MAX_ENTRIES {
            return Err(ChromeStyleError::Limit);
        }
        let mut entries = BTreeMap::new();
        for _ in 0..count {
            let key = self.text()?;
            let value = self.value()?;
            if entries.insert(key, value).is_some() {
                return Err(ChromeStyleError::Flags);
            }
        }
        Ok(entries)
    }
}

/// Missing, null and empty text are the same "not authored" fact.
fn authored<'a>(entries: &Entries<'a>, key: &str) -> Option<Value<'a>> {
    match entries.get(key).copied() {
        None | Some(Value::Null) | Some(Value::Text("")) => None,
        value => value,
    }
}

fn paint(value: Value<'_>) -> Result<[u8; 4]> {
    let Value::Text(text) = value else {
        return Err(ChromeStyleError::Color);
    };
    if !matches!(parse_color(text), Ok(Checked::Parsed(Some(_)))) {
        return Err(ChromeStyleError::Color);
    }
    Ok(color_rgba8(text, 1.0))
}

fn pixel_size(value: Value<'_>) -> Result<f64> {
    let Value::Text(text) = value else {
        return Err(ChromeStyleError::FontSize);
    };
    let n: f64 = text
        .trim()
        .strip_suffix("px")
        .ok_or(ChromeStyleError::FontSize)?
        .trim()
        .parse()
        .map_err(|_| ChromeStyleError::FontSize)?;
    bounded(n, 1.0, MAX_SCENE_CHROME_LENGTH, ChromeStyleError::FontSize)
}

fn axis_number(value: Value<'_>, lo: f64, hi: f64) -> Result<f64> {
    let n = match value {
        Value::Number(n) => n,
        Value::Text(text) => text
            .trim()
            .parse()
            .map_err(|_| ChromeStyleError::AxisStyle)?,
        _ => return Err(ChromeStyleError::AxisStyle),
    };
    bounded(n, lo, hi, ChromeStyleError::AxisStyle)
}

fn bounded(n: f64, lo: f64, hi: f64, error: ChromeStyleError) -> Result<f64> {
    if n.is_finite() && (lo..=hi).contains(&n) {
        Ok(n)
    } else {
        Err(error)
    }
}

fn family_is_dejavu(text: &str) -> bool {
    matches!(
        text.to_lowercase().as_str(),
        "dejavu sans" | "dejavusans" | "sans-serif"
    )
}

#[derive(Default)]
struct Slot {
    size: Option<f64>,
    rgba: Option<[u8; 4]>,
    flags: u8,
}

fn slot(entries: &Entries<'_>) -> Result<Slot> {
    if entries.keys().any(|key| {
        !matches!(
            *key,
            "font-size" | "color" | "font-weight" | "font-style" | "font-family"
        )
    }) {
        return Err(ChromeStyleError::Slot);
    }
    if let Some(family) = authored(entries, "font-family") {
        if !matches!(family, Value::Text(text) if family_is_dejavu(text)) {
            return Err(ChromeStyleError::CustomFont);
        }
    }
    let bold = match authored(entries, "font-weight") {
        None => 0,
        Some(Value::Text(text)) => match text.to_lowercase().as_str() {
            "normal" | "400" => 0,
            "bold" | "700" => 2,
            _ => return Err(ChromeStyleError::FontWeight),
        },
        Some(Value::Number(n)) if n == 400.0 => 0,
        Some(Value::Number(n)) if n == 700.0 => 2,
        Some(_) => return Err(ChromeStyleError::FontWeight),
    };
    let italic = match authored(entries, "font-style") {
        None => 0,
        Some(Value::Text(text)) => match text.to_lowercase().as_str() {
            "normal" => 0,
            "italic" => 1,
            _ => return Err(ChromeStyleError::FontStyle),
        },
        Some(_) => return Err(ChromeStyleError::FontStyle),
    };
    Ok(Slot {
        size: authored(entries, "font-size").map(pixel_size).transpose()?,
        rgba: authored(entries, "color").map(paint).transpose()?,
        flags: bold | italic,
    })
}

/// The pyplot legend slot is styled by the legend product path; this only
/// admits its closed key set so no unknown property is silently dropped.
fn legend_slot(entries: &Entries<'_>) -> Result<()> {
    if entries.keys().any(|key| {
        !matches!(
            *key,
            "fontSize"
                | "background"
                | "borderColor"
                | "borderStyle"
                | "borderWidth"
                | "--xy-legend-frame-alpha"
                | "padding"
                | "rowGap"
        )
    }) {
        return Err(ChromeStyleError::Slot);
    }
    Ok(())
}

fn root_text_paint(root: &Entries<'_>) -> Result<Option<[u8; 4]>> {
    if root.keys().any(|key| {
        !matches!(
            *key,
            "background"
                | "--chart-bg"
                | "--chart-grid"
                | "--chart-axis"
                | "--chart-text"
                | "font-family"
                | "font-size"
        )
    }) {
        return Err(ChromeStyleError::BrowserCss);
    }
    if let Some(family) = authored(root, "font-family") {
        let accepted = matches!(family, Value::Text(text)
        if matches!(
            text.to_lowercase().replace(' ', "").as_str(),
            "dejavusans,sans-serif" | "system-ui,sans-serif" | "sans-serif"
        ));
        if !accepted {
            return Err(ChromeStyleError::CustomFont);
        }
    }
    authored(root, "font-size").map(pixel_size).transpose()?;
    authored(root, "--chart-text").map(paint).transpose()
}

struct Axis {
    tick_size: f64,
    label_size: f64,
    tick_padding: f64,
    tick_rgba: Option<[u8; 4]>,
    title_rgba: Option<[u8; 4]>,
    removed_style: Vec<&'static str>,
    removed_minor: Vec<&'static str>,
}

fn axis(
    style: &Entries<'_>,
    minor: &Entries<'_>,
    tick_slot: &Slot,
    title_slot: &Slot,
    root_paint: Option<[u8; 4]>,
) -> Result<Axis> {
    let size = |key: &str| {
        authored(style, key)
            .map(|v| axis_number(v, 1.0, MAX_SCENE_CHROME_LENGTH))
            .transpose()
    };
    let tick_size = match size("tick_label_size")? {
        Some(n) => Some(n),
        None => size("tick_size")?,
    };
    let label_size = size("label_size")?;
    let tick_padding = authored(style, "tick_padding")
        .map(|v| axis_number(v, -MAX_SCENE_CHROME_LENGTH, MAX_SCENE_CHROME_LENGTH))
        .transpose()?;
    let color = |key: &str| authored(style, key).map(paint).transpose();
    let removed = |entries: &Entries<'_>| {
        SIZE_KEYS
            .into_iter()
            .filter(|key| entries.contains_key(key))
            .collect::<Vec<_>>()
    };
    Ok(Axis {
        tick_size: tick_size.or(tick_slot.size).unwrap_or(DEFAULT_TICK_SIZE),
        label_size: label_size.or(title_slot.size).unwrap_or(DEFAULT_LABEL_SIZE),
        tick_padding: tick_padding.unwrap_or(DEFAULT_TICK_PADDING),
        tick_rgba: color("tick_label_color")?.or(tick_slot.rgba).or(root_paint),
        title_rgba: color("label_color")?.or(title_slot.rgba).or(root_paint),
        removed_style: removed(style),
        removed_minor: removed(minor),
    })
}

fn put_text(out: &mut Vec<u8>, text: &str) {
    out.extend_from_slice(&(text.len() as u32).to_le_bytes());
    out.extend_from_slice(text.as_bytes());
}

/// Resolve one bounded XYCS v1 frame atomically into XYCO v1.
///
/// XYCS: `"XYCS"`, version 1, flags (bit 0 = the panel has a title, bit 1 =
/// admit the pyplot-owned `legend` slot key set), 0, root
/// theme entries, slot count then `(name, entries)`, then the x and y axis
/// `(style entries, minor-style entries)`. Entries are `count` then
/// `(key text, tagged value)`; values tag 0 null, 1 text, 2 f64, 3 bool,
/// 4 opaque.
///
/// XYCO: `"XYCO"`, version 1, flags (bit 0 = title), the XYST `chrome_text`
/// word, four paints (x tick, y tick, x title, y title; zero when absent),
/// title size (f64) and paint, then x and y `(tick, title, padding)` f64s and
/// the axis-style keys the host must drop from `style` / `minor_style`
/// because XYST, not the Scene wire, carries them.
pub fn resolve_packed(bytes: &[u8]) -> Result<Vec<u8>> {
    if bytes.len() > MAX_BYTES {
        return Err(ChromeStyleError::Limit);
    }
    let mut reader = Reader { bytes, at: 0 };
    if reader.take(4)? != b"XYCS" {
        return Err(ChromeStyleError::Header);
    }
    if reader.u32()? != 1 {
        return Err(ChromeStyleError::Version);
    }
    let flags = reader.u32()?;
    if flags & !0b11 != 0 || reader.u32()? != 0 {
        return Err(ChromeStyleError::Flags);
    }
    let has_title = flags & 1 != 0;
    let admit_legend = flags & 2 != 0;
    let root = reader.entries()?;
    let slot_count = reader.u32()? as usize;
    if slot_count > MAX_SLOTS {
        return Err(ChromeStyleError::Limit);
    }
    let mut slots: BTreeMap<&str, Slot> = BTreeMap::new();
    for _ in 0..slot_count {
        let name = reader.text()?;
        let entries = reader.entries()?;
        if name == "legend" && admit_legend {
            legend_slot(&entries)?;
            continue;
        }
        if !matches!(name, "title" | "axis_title" | "tick_label") {
            return Err(ChromeStyleError::Slot);
        }
        if slots.insert(name, slot(&entries)?).is_some() {
            return Err(ChromeStyleError::Flags);
        }
    }
    let mut axes = Vec::with_capacity(2);
    let mut axis_entries = Vec::with_capacity(2);
    for _ in 0..2 {
        axis_entries.push((reader.entries()?, reader.entries()?));
    }
    if reader.at != bytes.len() {
        return Err(ChromeStyleError::Header);
    }
    let root_paint = root_text_paint(&root)?;
    let empty = Slot::default();
    let tick_slot = slots.get("tick_label").unwrap_or(&empty);
    let title_slot = slots.get("axis_title").unwrap_or(&empty);
    for (style, minor) in &axis_entries {
        axes.push(axis(style, minor, tick_slot, title_slot, root_paint)?);
    }
    let panel_title = slots.get("title").unwrap_or(&empty);
    let title_size = panel_title.size.unwrap_or(DEFAULT_TITLE_SIZE);
    let title_rgba = panel_title
        .rgba
        .or(root_paint)
        .unwrap_or(DEFAULT_TITLE_RGBA);

    // XYST chrome_text: 2-bit flags for title, x/y title, x/y tick (bits
    // 0..10), then paint-present bits for x tick, y tick, x title, y title.
    let mut chrome_text = 0u32;
    let mut paints = [[0u8; 4]; 4];
    if has_title {
        chrome_text |= u32::from(panel_title.flags);
    }
    for (index, axis) in axes.iter().enumerate() {
        chrome_text |= u32::from(title_slot.flags) << (2 + 2 * index);
        chrome_text |= u32::from(tick_slot.flags) << (6 + 2 * index);
        for (offset, color) in [(0, axis.tick_rgba), (2, axis.title_rgba)] {
            if let Some(rgba) = color {
                chrome_text |= 1 << (10 + offset + index);
                paints[offset + index] = rgba;
            }
        }
    }

    let mut out = Vec::with_capacity(128);
    out.extend_from_slice(b"XYCO");
    out.extend_from_slice(&1u32.to_le_bytes());
    out.extend_from_slice(&u32::from(has_title).to_le_bytes());
    out.extend_from_slice(&chrome_text.to_le_bytes());
    for paint in paints {
        out.extend_from_slice(&paint);
    }
    out.extend_from_slice(&title_size.to_le_bytes());
    out.extend_from_slice(&title_rgba);
    for axis in &axes {
        for value in [axis.tick_size, axis.label_size, axis.tick_padding] {
            out.extend_from_slice(&value.to_le_bytes());
        }
    }
    for axis in &axes {
        for removed in [&axis.removed_style, &axis.removed_minor] {
            out.extend_from_slice(&(removed.len() as u32).to_le_bytes());
            for key in removed {
                put_text(&mut out, key);
            }
        }
    }
    Ok(out)
}
