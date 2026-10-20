//! XYAS static annotation normalization (M2 #873; dossier §21/§28).
//! Returns mechanical patches and a per-label typography/box table, never
//! rendered geometry.
use crate::css::{color_rgba8, parse_color, Checked};
use crate::scene::MAX_SCENE_CHROME_LENGTH;
use crate::scene_annotations::{label_slots, LabelSlotRow};
use std::collections::BTreeMap;

const MAX_BYTES: usize = 2 * 1024 * 1024;
const MAX_TEXT: usize = 4096;
const MAX_ROWS: usize = 128;
const MAX_STYLES: usize = 64;
const ROW_WRAP: u32 = 1;
const ROW_LAYOUT: u32 = 2;
const ROW_FLAGS: u32 = ROW_WRAP | ROW_LAYOUT;

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum AnnotationStyleError {
    Header,
    Version,
    Flags,
    Limit,
    Text,
    Mathtext,
    Font,
    Typography,
    Vertical,
    Bbox,
    Boxstyle,
    Style,
}
impl AnnotationStyleError {
    pub fn reason(self) -> &'static str {
        match self {
            Self::Header => "XYG_STATIC_ANNOTATION_STYLE_HEADER",
            Self::Version => "XYG_STATIC_ANNOTATION_STYLE_VERSION",
            Self::Flags => "XYG_STATIC_ANNOTATION_STYLE_FLAGS",
            Self::Limit => "XYG_STATIC_ANNOTATION_STYLE_LIMIT",
            Self::Text => "XYG_STATIC_ANNOTATION_STYLE_TEXT",
            Self::Mathtext => "XYG_STATIC_UNSUPPORTED_MATHTEXT_STYLE",
            Self::Font => "XYG_STATIC_UNSUPPORTED_CUSTOM_FONT",
            Self::Typography => "XYG_STATIC_UNSUPPORTED_ANNOTATION_TYPOGRAPHY",
            Self::Vertical => "XYG_STATIC_UNSUPPORTED_ANNOTATION_VERTICAL_ALIGN",
            Self::Bbox => "XYG_STATIC_UNSUPPORTED_ANNOTATION_BBOX",
            Self::Boxstyle => "XYG_STATIC_UNSUPPORTED_ANNOTATION_BOXSTYLE",
            Self::Style => "XYG_STATIC_UNSUPPORTED_ANNOTATION_STYLE",
        }
    }
}
type Result<T> = std::result::Result<T, AnnotationStyleError>;

#[derive(Clone, Copy, Debug, PartialEq)]
enum Value<'a> {
    Null,
    Text(&'a str),
    Number(f64),
    Bool(bool),
    Opaque,
}
struct Reader<'a> {
    bytes: &'a [u8],
    at: usize,
}
impl<'a> Reader<'a> {
    fn take(&mut self, n: usize) -> Result<&'a [u8]> {
        let end = self.at.checked_add(n).ok_or(AnnotationStyleError::Limit)?;
        let value = self
            .bytes
            .get(self.at..end)
            .ok_or(AnnotationStyleError::Header)?;
        self.at = end;
        Ok(value)
    }
    fn u32(&mut self) -> Result<u32> {
        Ok(u32::from_le_bytes(self.take(4)?.try_into().unwrap()))
    }
    fn text(&mut self, optional: bool) -> Result<Option<&'a str>> {
        let n = self.u32()?;
        if optional && n == u32::MAX {
            return Ok(None);
        }
        if n as usize > MAX_TEXT {
            return Err(AnnotationStyleError::Limit);
        }
        let bytes = self.take(n as usize)?;
        if bytes.contains(&0) {
            return Err(AnnotationStyleError::Text);
        }
        Ok(Some(
            std::str::from_utf8(bytes).map_err(|_| AnnotationStyleError::Text)?,
        ))
    }
    fn value(&mut self) -> Result<Value<'a>> {
        match self.u32()? {
            0 => Ok(Value::Null),
            1 => Ok(Value::Text(self.text(false)?.unwrap())),
            2 => Ok(Value::Number(f64::from_le_bytes(
                self.take(8)?.try_into().unwrap(),
            ))),
            3 => match self.u32()? {
                0 => Ok(Value::Bool(false)),
                1 => Ok(Value::Bool(true)),
                _ => Err(AnnotationStyleError::Flags),
            },
            4 => Ok(Value::Opaque),
            _ => Err(AnnotationStyleError::Flags),
        }
    }
}

enum Patch {
    Remove(&'static str),
    Text(&'static str, String),
    Number(&'static str, f64),
}
fn strip<'a>(
    style: &BTreeMap<&str, Value<'a>>,
    key: &'static str,
    patches: &mut Vec<Patch>,
) -> Option<Value<'a>> {
    let value = style.get(key).copied();
    if value.is_some() {
        patches.push(Patch::Remove(key));
    }
    value
}
fn alias<'a>(
    style: &BTreeMap<&str, Value<'a>>,
    primary: &'static str,
    secondary: &'static str,
    patches: &mut Vec<Patch>,
) -> Option<Value<'a>> {
    let first = strip(style, primary, patches);
    let second = strip(style, secondary, patches);
    first.or(second)
}
fn absent(value: Option<Value<'_>>) -> bool {
    matches!(value, None | Some(Value::Null))
}
fn empty_default(value: Option<Value<'_>>) -> bool {
    matches!(
        value,
        None | Some(Value::Null | Value::Text("") | Value::Bool(false))
    ) || matches!(value, Some(Value::Number(n)) if n == 0.0)
}
fn word(value: Option<Value<'_>>) -> Result<String> {
    if empty_default(value) {
        Ok("normal".into())
    } else if let Some(Value::Text(text)) = value {
        Ok(text.to_lowercase())
    } else {
        Err(AnnotationStyleError::Typography)
    }
}
fn number(value: Value<'_>, error: AnnotationStyleError) -> Result<f64> {
    let n = match value {
        Value::Number(n) => n,
        Value::Bool(value) => u8::from(value) as f64,
        Value::Text(text) => text.trim().parse().map_err(|_| error)?,
        _ => return Err(error),
    };
    if n.is_finite() {
        Ok(n)
    } else {
        Err(error)
    }
}
fn bounded(n: f64, lo: f64, hi: f64, error: AnnotationStyleError) -> Result<f64> {
    if n.is_finite() && (lo..=hi).contains(&n) && (n as f32).is_finite() {
        Ok(n)
    } else {
        Err(error)
    }
}
fn paint(value: Value<'_>, error: AnnotationStyleError) -> Result<String> {
    let Value::Text(text) = value else {
        return Err(error);
    };
    if !matches!(parse_color(text), Ok(Checked::Parsed(Some(_)))) {
        return Err(error);
    }
    let [r, g, b, a] = color_rgba8(text, 1.0);
    Ok(format!("#{r:02x}{g:02x}{b:02x}{a:02x}"))
}
fn pixels(value: Value<'_>) -> Result<f64> {
    let Value::Text(text) = value else {
        return Err(AnnotationStyleError::Bbox);
    };
    number(
        Value::Text(text.strip_suffix("px").ok_or(AnnotationStyleError::Bbox)?),
        AnnotationStyleError::Bbox,
    )
}
fn put_text(out: &mut Vec<u8>, text: &str) {
    out.extend_from_slice(&(text.len() as u32).to_le_bytes());
    out.extend_from_slice(text.as_bytes());
}

/// One label's resolved typography/box facts, in XYAO label-table order.
#[derive(Clone, Copy, Default)]
struct LabelEntry {
    typography: Option<(f32, u8, u8)>,
    padding: Option<(f32, f32)>,
}
const ENTRY_TYPOGRAPHY: u32 = 1;
const ENTRY_PADDING: u32 = 2;
/// Bytes of one XYAO / XYST label-table entry.
pub const LABEL_ENTRY_BYTES: usize = 20;

/// CSS `padding` shorthand (`<v>px` or `<v>px <h>px`) as `(horizontal, vertical)`.
fn padding_pair(value: Value<'_>) -> Result<(f64, f64)> {
    let Value::Text(text) = value else {
        return Err(AnnotationStyleError::Bbox);
    };
    let mut parts = text.split(' ');
    let vertical = pixels(Value::Text(parts.next().unwrap_or("")))?;
    let horizontal = match parts.next() {
        Some(part) => pixels(Value::Text(part))?,
        None => vertical,
    };
    if parts.next().is_some() {
        return Err(AnnotationStyleError::Bbox);
    }
    Ok((horizontal, vertical))
}

/// Resolve a complete bounded batch atomically into XYAO v2.
pub fn resolve_packed(bytes: &[u8]) -> Result<Vec<u8>> {
    if bytes.len() > MAX_BYTES {
        return Err(AnnotationStyleError::Limit);
    }
    let mut reader = Reader { bytes, at: 0 };
    if reader.take(4)? != b"XYAS" {
        return Err(AnnotationStyleError::Header);
    }
    if reader.u32()? != 2 {
        return Err(AnnotationStyleError::Version);
    }
    let count = reader.u32()? as usize;
    if count > MAX_ROWS {
        return Err(AnnotationStyleError::Limit);
    }
    if reader.u32()? != 0 {
        return Err(AnnotationStyleError::Flags);
    }
    let mut rows = Vec::with_capacity(count);
    let mut slot_rows = Vec::with_capacity(count);
    let mut pending: Vec<LabelEntry> = Vec::with_capacity(count);
    for _ in 0..count {
        let entries = reader.u32()? as usize;
        if entries > MAX_STYLES {
            return Err(AnnotationStyleError::Limit);
        }
        let row_flags = reader.u32()?;
        if row_flags & !ROW_FLAGS != 0 {
            return Err(AnnotationStyleError::Flags);
        }
        let text = reader.text(true)?;
        let kind = reader.text(true)?;
        let mut style = BTreeMap::new();
        for _ in 0..entries {
            let key = reader.text(false)?.unwrap();
            let value = reader.value()?;
            if style.insert(key, value).is_some() {
                return Err(AnnotationStyleError::Flags);
            }
        }
        if kind == Some("text") && text.is_none_or(str::is_empty) {
            rows.push((true, Vec::new()));
            continue;
        }
        if !empty_default(style.get("math_italic_ranges").copied()) {
            return Err(AnnotationStyleError::Mathtext);
        }
        let mut patches = Vec::new();
        let family = alias(&style, "font_family", "fontFamily", &mut patches);
        if !matches!(
            family,
            None | Some(
                Value::Null
                    | Value::Text("" | "system-ui,sans-serif" | "DejaVu Sans" | "sans-serif")
            )
        ) {
            return Err(AnnotationStyleError::Font);
        }
        let font_style = word(alias(&style, "font_style", "fontStyle", &mut patches))?;
        let italic = match font_style.as_str() {
            "normal" => 0,
            "italic" | "oblique" => 1,
            _ => return Err(AnnotationStyleError::Typography),
        };
        let raw_weight = alias(&style, "font_weight", "fontWeight", &mut patches);
        let weight = match raw_weight {
            Some(Value::Number(n)) if matches!(n, 400.0 | 600.0 | 700.0 | 800.0 | 900.0) => {
                format!("{n:.0}")
            }
            _ => word(raw_weight)?,
        };
        let bold = match weight.as_str() {
            "normal" | "regular" | "book" | "400" => 0,
            "bold" | "semibold" | "demibold" | "heavy" | "black" | "600" | "700" | "800"
            | "900" => 2,
            _ => return Err(AnnotationStyleError::Typography),
        };
        let font_size = alias(&style, "font_size", "fontSize", &mut patches);
        let mut entry = LabelEntry::default();
        let labelled = text.is_some_and(|text| !text.is_empty())
            && matches!(kind, Some("text" | "callout" | "rule" | "band" | "marker"));
        if kind == Some("text") {
            if let Some(color) = strip(&style, "label_color", &mut patches) {
                patches.push(Patch::Text(
                    "color",
                    paint(color, AnnotationStyleError::Style)?,
                ));
            }
        }
        let align = strip(&style, "vertical_align", &mut patches);
        if labelled {
            let font_size = if absent(font_size) {
                12.0
            } else {
                number(font_size.unwrap(), AnnotationStyleError::Typography)?
            };
            let font_size = bounded(
                font_size,
                1.0,
                MAX_SCENE_CHROME_LENGTH,
                AnnotationStyleError::Typography,
            )?;
            let align = match align {
                None | Some(Value::Text("baseline")) => 0,
                Some(Value::Text("top")) => 1,
                Some(Value::Text("bottom")) => 2,
                Some(Value::Text("center" | "center_baseline")) => 3,
                _ => return Err(AnnotationStyleError::Vertical),
            };
            entry.typography = Some((font_size as f32, (italic | bold) as u8, align));
        }
        let rotation = style
            .get("rotation")
            .copied()
            .filter(|value| *value != Value::Null);
        if let Some(value) = rotation {
            let n = number(value, AnnotationStyleError::Style)?.rem_euclid(360.0);
            patches.push(Patch::Number(
                "rotation",
                if n == 0.0 || n == 360.0 { 0.0 } else { n },
            ));
        }
        // CSS-like box keys. `border_radius` is the Matplotlib `round` boxstyle;
        // the Scene label box is a rectangle, so it fails closed.
        let radius = strip(&style, "border_radius", &mut patches);
        if !empty_default(radius) {
            return Err(AnnotationStyleError::Boxstyle);
        }
        let background = strip(&style, "background", &mut patches);
        let border = strip(&style, "border", &mut patches);
        let raw_padding = strip(&style, "padding", &mut patches);
        if !absent(background) {
            patches.push(Patch::Text(
                "label_background",
                paint(background.unwrap(), AnnotationStyleError::Bbox)?,
            ));
        }
        if !absent(border) {
            let Some(Value::Text(border)) = border else {
                return Err(AnnotationStyleError::Bbox);
            };
            let (width, color) = border
                .split_once(" solid ")
                .ok_or(AnnotationStyleError::Bbox)?;
            let width = pixels(Value::Text(width))?;
            if width <= 0.0 || !(width as f32).is_finite() || width as f32 == 0.0 {
                return Err(AnnotationStyleError::Bbox);
            }
            patches.push(Patch::Number("label_border_width", width));
            patches.push(Patch::Text(
                "label_border_color",
                paint(Value::Text(color), AnnotationStyleError::Bbox)?,
            ));
        }
        let boxed = !absent(background) || !absent(style.get("label_background").copied());
        if !absent(raw_padding) {
            let (horizontal, vertical) = padding_pair(raw_padding.unwrap())?;
            entry.padding = Some((
                bounded(
                    horizontal,
                    0.0,
                    MAX_SCENE_CHROME_LENGTH,
                    AnnotationStyleError::Bbox,
                )? as f32,
                bounded(
                    vertical,
                    0.0,
                    MAX_SCENE_CHROME_LENGTH,
                    AnnotationStyleError::Bbox,
                )? as f32,
            ));
        } else if boxed {
            entry.padding = Some((3.0, 3.0));
        }
        let kind_name = kind.unwrap_or("");
        let layout_key = row_flags & ROW_LAYOUT != 0;
        // Non-data text routes through the laid-out (XYAW) label slot, like
        // the Scene annotation pack does; the Scene pack validates the value.
        let non_data_space = matches!(
            style.get("coordinate_space").copied(),
            Some(Value::Text(space)) if space != "data"
        );
        slot_rows.push(LabelSlotRow {
            kind: kind_name,
            authored_wrap: row_flags & ROW_WRAP != 0,
            layout: layout_key
                || (matches!(kind_name, "text" | "marker") && rotation.is_some())
                || (kind_name == "text" && non_data_space),
            labelled: text.is_some_and(|text| !text.is_empty()),
        });
        pending.push(entry);
        rows.push((false, patches));
    }
    if reader.at != bytes.len() {
        return Err(AnnotationStyleError::Header);
    }
    let (slots, label_count) = label_slots(&slot_rows);
    let mut table = vec![LabelEntry::default(); label_count as usize];
    for (slot, entry) in slots.into_iter().zip(pending) {
        if let Some(slot) = slot {
            table[slot as usize] = entry;
        }
    }
    let mut out = b"XYAO".to_vec();
    for value in [2, count as u32, label_count] {
        out.extend_from_slice(&value.to_le_bytes());
    }
    for (drop, patches) in rows {
        out.extend_from_slice(&u32::from(drop).to_le_bytes());
        out.extend_from_slice(&(patches.len() as u32).to_le_bytes());
        for patch in patches {
            match patch {
                Patch::Remove(key) => {
                    put_text(&mut out, key);
                    out.extend_from_slice(&0_u32.to_le_bytes());
                }
                Patch::Text(key, value) => {
                    put_text(&mut out, key);
                    out.extend_from_slice(&1_u32.to_le_bytes());
                    put_text(&mut out, &value);
                }
                Patch::Number(key, value) => {
                    put_text(&mut out, key);
                    out.extend_from_slice(&2_u32.to_le_bytes());
                    out.extend_from_slice(&value.to_le_bytes());
                }
            }
        }
    }
    for entry in table {
        let present = (u32::from(entry.typography.is_some()) * ENTRY_TYPOGRAPHY)
            | (u32::from(entry.padding.is_some()) * ENTRY_PADDING);
        let (size, flags, align) = entry.typography.unwrap_or((0.0, 0, 0));
        let (pad_x, pad_y) = entry.padding.unwrap_or((0.0, 0.0));
        out.extend_from_slice(&present.to_le_bytes());
        for value in [size, pad_x, pad_y] {
            out.extend_from_slice(&value.to_le_bytes());
        }
        out.extend_from_slice(&[flags, align, 0, 0]);
    }
    Ok(out)
}

#[cfg(test)]
mod tests {
    use super::*;

    type Row<'a> = (Option<&'a str>, Option<&'a str>, Vec<(&'a str, Value<'a>)>);
    fn frame_flags(rows: &[(u32, Row<'_>)]) -> Vec<u8> {
        let mut out = b"XYAS".to_vec();
        for n in [2, rows.len() as u32, 0] {
            out.extend(n.to_le_bytes());
        }
        for (flags, (text, kind, entries)) in rows {
            out.extend((entries.len() as u32).to_le_bytes());
            out.extend(flags.to_le_bytes());
            for text in [text, kind] {
                if let Some(text) = text {
                    put_text(&mut out, text);
                } else {
                    out.extend(u32::MAX.to_le_bytes());
                }
            }
            for (key, value) in entries {
                put_text(&mut out, key);
                match value {
                    Value::Null => out.extend(0_u32.to_le_bytes()),
                    Value::Text(text) => {
                        out.extend(1_u32.to_le_bytes());
                        put_text(&mut out, text);
                    }
                    Value::Number(n) => {
                        out.extend(2_u32.to_le_bytes());
                        out.extend(n.to_le_bytes());
                    }
                    Value::Bool(b) => {
                        out.extend(3_u32.to_le_bytes());
                        out.extend(u32::from(*b).to_le_bytes());
                    }
                    Value::Opaque => out.extend(4_u32.to_le_bytes()),
                }
            }
        }
        out
    }
    fn frame(rows: &[Row<'_>]) -> Vec<u8> {
        frame_flags(&rows.iter().map(|row| (0, row.clone())).collect::<Vec<_>>())
    }
    fn text_row<'a>(entries: Vec<(&'a str, Value<'a>)>) -> Row<'a> {
        (Some("hello"), Some("text"), entries)
    }
    fn u32_at(bytes: &[u8], at: usize) -> u32 {
        u32::from_le_bytes(bytes[at..at + 4].try_into().unwrap())
    }
    fn f32_at(bytes: &[u8], at: usize) -> f32 {
        f32::from_le_bytes(bytes[at..at + 4].try_into().unwrap())
    }
    type Patches<'a> = Vec<(String, Value<'a>)>;
    /// Decode XYAO v2 into per-row `(drop, patches)` and the label table.
    fn parse(bytes: &[u8]) -> (Vec<(u32, Patches<'_>)>, Vec<[u8; LABEL_ENTRY_BYTES]>) {
        assert_eq!(&bytes[..4], b"XYAO");
        assert_eq!(u32_at(bytes, 4), 2);
        let (count, labels) = (u32_at(bytes, 8), u32_at(bytes, 12));
        let mut reader = Reader { bytes, at: 16 };
        let mut rows = Vec::new();
        for _ in 0..count {
            let drop = reader.u32().unwrap();
            let mut values = Vec::new();
            for _ in 0..reader.u32().unwrap() {
                let key = reader.text(false).unwrap().unwrap().to_owned();
                let value = match reader.u32().unwrap() {
                    0 => Value::Null,
                    1 => Value::Text(reader.text(false).unwrap().unwrap()),
                    2 => Value::Number(f64::from_le_bytes(
                        reader.take(8).unwrap().try_into().unwrap(),
                    )),
                    _ => panic!("invalid patch opcode"),
                };
                values.push((key, value));
            }
            rows.push((drop, values));
        }
        let table = (0..labels)
            .map(|_| reader.take(LABEL_ENTRY_BYTES).unwrap().try_into().unwrap())
            .collect();
        assert_eq!(reader.at, bytes.len());
        (rows, table)
    }
    fn patches(bytes: &[u8]) -> Patches<'_> {
        parse(bytes).0.remove(0).1
    }
    /// `(present, size, pad_x, pad_y, text flags, vertical align)`.
    fn entry(raw: &[u8; LABEL_ENTRY_BYTES]) -> (u32, f32, f32, f32, u8, u8) {
        (
            u32_at(raw, 0),
            f32_at(raw, 4),
            f32_at(raw, 8),
            f32_at(raw, 12),
            raw[16],
            raw[17],
        )
    }
    #[test]
    fn empty_and_default_golden() {
        let mut expected = b"XYAO".to_vec();
        for n in [2_u32, 0, 0] {
            expected.extend(n.to_le_bytes());
        }
        assert_eq!(resolve_packed(&frame(&[])).unwrap(), expected);
        let bytes = resolve_packed(&frame(&[text_row(vec![])])).unwrap();
        expected[8..16].copy_from_slice(&[1, 0, 0, 0, 1, 0, 0, 0]);
        expected.extend([0; 8]);
        expected.extend(1_u32.to_le_bytes());
        expected.extend(12_f32.to_le_bytes());
        expected.extend([0; 12]);
        assert_eq!(bytes, expected);
    }
    #[test]
    fn aliases_null_precedence_and_css_patch_golden() {
        let bytes = resolve_packed(&frame(&[text_row(vec![
            ("font_family", Value::Null),
            ("fontFamily", Value::Text("custom")),
            ("font_style", Value::Text("ITALIC")),
            ("font_weight", Value::Text("700")),
            ("font_size", Value::Number(18.0)),
            ("vertical_align", Value::Text("center_baseline")),
            ("label_color", Value::Text("red")),
            ("rotation", Value::Number(-450.0)),
            ("background", Value::Text("#ffffff")),
            ("border", Value::Text("2px solid black")),
            ("padding", Value::Text("4px")),
            ("unknown", Value::Opaque),
        ])]))
        .unwrap();
        let (rows, table) = parse(&bytes);
        assert_eq!(entry(&table[0]), (3, 18.0, 4.0, 4.0, 3, 3));
        assert_eq!(
            rows[0].1,
            vec![
                ("font_family".into(), Value::Null),
                ("fontFamily".into(), Value::Null),
                ("font_style".into(), Value::Null),
                ("font_weight".into(), Value::Null),
                ("font_size".into(), Value::Null),
                ("label_color".into(), Value::Null),
                ("color".into(), Value::Text("#ff0000ff")),
                ("vertical_align".into(), Value::Null),
                ("rotation".into(), Value::Number(270.0)),
                ("background".into(), Value::Null),
                ("border".into(), Value::Null),
                ("padding".into(), Value::Null),
                ("label_background".into(), Value::Text("#ffffffff")),
                ("label_border_width".into(), Value::Number(2.0)),
                ("label_border_color".into(), Value::Text("#000000ff")),
            ]
        );
    }
    #[test]
    fn admitted_typography_is_per_label() {
        for (weight, expected) in [(400.0, 0), (600.0, 2), (700.0, 2), (800.0, 2), (900.0, 2)] {
            let bytes = resolve_packed(&frame(&[text_row(vec![(
                "font_weight",
                Value::Number(weight),
            )])]))
            .unwrap();
            assert_eq!(entry(&parse(&bytes).1[0]).4, expected);
        }
        for style in ["normal", "italic", "oblique"] {
            for weight in [
                "normal", "regular", "book", "400", "bold", "semibold", "demibold", "heavy",
                "black", "600", "700", "800", "900",
            ] {
                for align in ["baseline", "top", "bottom", "center", "center_baseline"] {
                    assert!(resolve_packed(&frame(&[text_row(vec![
                        ("fontStyle", Value::Text(style)),
                        ("fontWeight", Value::Text(weight)),
                        ("vertical_align", Value::Text(align))
                    ])]))
                    .is_ok());
                }
            }
        }
        // Heterogeneous typography is carried per label, never rejected.
        let bytes = resolve_packed(&frame(&[
            text_row(vec![]),
            text_row(vec![("font_size", Value::Number(13.0))]),
            text_row(vec![("font_style", Value::Text("italic"))]),
            text_row(vec![("font_weight", Value::Text("bold"))]),
            text_row(vec![("vertical_align", Value::Text("top"))]),
        ]))
        .unwrap();
        let table = parse(&bytes).1;
        let facts: Vec<_> = table.iter().map(entry).collect();
        assert_eq!(
            facts,
            vec![
                (1, 12.0, 0.0, 0.0, 0, 0),
                (1, 13.0, 0.0, 0.0, 0, 0),
                (1, 12.0, 0.0, 0.0, 1, 0),
                (1, 12.0, 0.0, 0.0, 2, 0),
                (1, 12.0, 0.0, 0.0, 0, 1),
            ]
        );
    }
    #[test]
    fn box_padding_is_per_label_and_two_axis() {
        let bytes = resolve_packed(&frame(&[
            text_row(vec![("background", Value::Text("white"))]),
            text_row(vec![("label_background", Value::Text("white"))]),
            text_row(vec![
                ("background", Value::Text("white")),
                ("padding", Value::Text("5px")),
            ]),
            text_row(vec![
                ("background", Value::Text("white")),
                ("padding", Value::Text("2px 6.5px")),
            ]),
            text_row(vec![]),
        ]))
        .unwrap();
        let facts: Vec<_> = parse(&bytes).1.iter().map(entry).collect();
        assert_eq!(
            facts,
            vec![
                (3, 12.0, 3.0, 3.0, 0, 0),
                (3, 12.0, 3.0, 3.0, 0, 0),
                (3, 12.0, 5.0, 5.0, 0, 0),
                (3, 12.0, 6.5, 2.0, 0, 0),
                (1, 12.0, 0.0, 0.0, 0, 0),
            ]
        );
        for padding in ["1px 2px 3px", "1px  2px", "1 2px", "2px 3"] {
            assert_eq!(
                resolve_packed(&frame(&[text_row(vec![("padding", Value::Text(padding))])])),
                Err(AnnotationStyleError::Bbox),
                "{padding}"
            );
        }
    }
    #[test]
    fn non_data_coordinate_space_text_takes_the_laid_out_label_slot() {
        let sized = |size: f64, space: Option<&'static str>| {
            let mut entries = vec![("font_size", Value::Number(size))];
            if let Some(space) = space {
                entries.push(("coordinate_space", Value::Text(space)));
            }
            entries
        };
        // No host layout flag: the style value alone routes the text row to
        // the XYAW slot, after the XYAT rows, as the Scene annotation pack does.
        let rows = [
            (0, (Some("a"), Some("text"), sized(21.0, Some("axes_fraction")))),
            (0, (Some("b"), Some("text"), sized(22.0, None))),
            (0, (Some("c"), Some("text"), sized(23.0, Some("data")))),
            (0, (Some("d"), Some("text"), sized(24.0, Some("yaxis_transform")))),
        ];
        let table = parse(&resolve_packed(&frame_flags(&rows)).unwrap()).1;
        let sizes: Vec<_> = table.iter().map(|raw| entry(raw).1).collect();
        assert_eq!(sizes, vec![22.0, 23.0, 21.0, 24.0]);
    }
    #[test]
    fn label_table_follows_scene_label_order() {
        let sized = |size: f64| vec![("font_size", Value::Number(size))];
        let rows = [
            (0, (Some("callout"), Some("callout"), sized(31.0))),
            (0, (Some("plain"), Some("text"), sized(21.0))),
            (ROW_WRAP, (Some("wrapped"), Some("text"), sized(22.0))),
            (0, (Some("plain"), Some("text"), sized(23.0))),
            (0, (None, Some("arrow"), vec![])),
            (0, (Some("rule"), Some("rule"), sized(41.0))),
            (ROW_LAYOUT, (Some("laid out"), Some("text"), sized(24.0))),
            (0, (Some("marker"), Some("marker"), sized(42.0))),
            (ROW_LAYOUT, (Some("moved"), Some("marker"), sized(43.0))),
            (0, (Some("callout"), Some("callout"), sized(32.0))),
            (ROW_WRAP, (Some("callout"), Some("callout"), sized(33.0))),
            // A rule without text has no label, so no table entry.
            (0, (None, Some("rule"), sized(99.0))),
        ];
        let table = parse(&resolve_packed(&frame_flags(&rows)).unwrap()).1;
        // XYAT text, XYAL rule/marker, XYAW text and laid-out marker,
        // XYAC callouts, then XYAW callouts.
        let sizes: Vec<_> = table.iter().map(|raw| entry(raw).1).collect();
        assert_eq!(
            sizes,
            vec![
                21.0, 23.0, // XYAT: rows 1 and 3
                41.0, 42.0, // XYAL: rule row 5 and marker row 7
                22.0, 24.0, 43.0, // XYAW: rows 2, 6 and laid-out marker row 8
                31.0, 32.0, // XYAC: rows 0 and 9
                33.0, // wrapped callout: row 10
            ]
        );
    }
    #[test]
    fn numeric_bounds_precede_narrowing_and_rotation_is_finite() {
        for n in [
            f64::NAN,
            f64::INFINITY,
            f64::NEG_INFINITY,
            0.999999999,
            1000.000001,
        ] {
            assert_eq!(
                resolve_packed(&frame(&[text_row(vec![("font_size", Value::Number(n))])])),
                Err(AnnotationStyleError::Typography)
            );
        }
        for value in [
            "-0.000000000000000000001px",
            "1000.000001px",
            "NaNpx",
            "infpx",
        ] {
            assert_eq!(
                resolve_packed(&frame(&[text_row(vec![("padding", Value::Text(value))])])),
                Err(AnnotationStyleError::Bbox)
            );
        }
        for value in ["0px solid red", "1e-100px solid red", "1e100px solid red"] {
            assert_eq!(
                resolve_packed(&frame(&[text_row(vec![("border", Value::Text(value))])])),
                Err(AnnotationStyleError::Bbox)
            );
        }
        for n in [-720.0, -0.0, 720.0] {
            let bytes =
                resolve_packed(&frame(&[text_row(vec![("rotation", Value::Number(n))])])).unwrap();
            assert_eq!(
                patches(&bytes),
                vec![("rotation".into(), Value::Number(0.0))]
            );
        }
        assert_eq!(
            resolve_packed(&frame(&[text_row(vec![(
                "rotation",
                Value::Number(f64::NAN)
            )])])),
            Err(AnnotationStyleError::Style)
        );
    }
    #[test]
    fn semantic_errors_and_lossless_unconsumed_facts() {
        for (key, value, error) in [
            (
                "font_family",
                Value::Text("Arial"),
                AnnotationStyleError::Font,
            ),
            (
                "font_style",
                Value::Text(" italic"),
                AnnotationStyleError::Typography,
            ),
            (
                "font_weight",
                Value::Number(700.5),
                AnnotationStyleError::Typography,
            ),
            (
                "vertical_align",
                Value::Null,
                AnnotationStyleError::Vertical,
            ),
            (
                "math_italic_ranges",
                Value::Opaque,
                AnnotationStyleError::Mathtext,
            ),
            (
                "background",
                Value::Text("var(--color)"),
                AnnotationStyleError::Bbox,
            ),
            ("label_color", Value::Null, AnnotationStyleError::Style),
            (
                "border_radius",
                Value::Number(5.0),
                AnnotationStyleError::Boxstyle,
            ),
        ] {
            assert_eq!(
                resolve_packed(&frame(&[text_row(vec![(key, value)])])),
                Err(error)
            );
        }
        // A zero radius is the square boxstyle: stripped, not rejected.
        let bytes = resolve_packed(&frame(&[text_row(vec![(
            "border_radius",
            Value::Number(0.0),
        )])]))
        .unwrap();
        assert_eq!(patches(&bytes), vec![("border_radius".into(), Value::Null)]);
        let bytes = resolve_packed(&frame(&[(
            None,
            Some("text"),
            vec![("font_family", Value::Opaque)],
        )]))
        .unwrap();
        let (rows, table) = parse(&bytes);
        assert_eq!((rows, table.len()), (vec![(1, vec![])], 0));
        let bytes = resolve_packed(&frame(&[(
            None,
            Some("arrow"),
            vec![
                ("font_size", Value::Opaque),
                ("vertical_align", Value::Opaque),
                ("unknown", Value::Number(f64::NAN)),
            ],
        )]))
        .unwrap();
        let (rows, table) = parse(&bytes);
        assert!(table.is_empty());
        assert_eq!(
            rows[0].1,
            vec![
                ("font_size".into(), Value::Null),
                ("vertical_align".into(), Value::Null)
            ]
        );
    }
    #[test]
    fn framing_and_limits_fail_closed() {
        let bytes = frame(&[text_row(vec![
            ("rotation", Value::Number(12.0)),
            ("unknown", Value::Bool(true)),
        ])]);
        for n in 0..bytes.len() {
            assert!(resolve_packed(&bytes[..n]).is_err(), "prefix {n}");
        }
        let mut trailing = bytes.clone();
        trailing.push(0);
        assert_eq!(resolve_packed(&trailing), Err(AnnotationStyleError::Header));
        for (offset, value, error) in [
            (4, 1, AnnotationStyleError::Version),
            (4, 3, AnnotationStyleError::Version),
            (8, 129, AnnotationStyleError::Limit),
            (12, 1, AnnotationStyleError::Flags),
            (16, 65, AnnotationStyleError::Limit),
            (20, 4, AnnotationStyleError::Flags),
            (24, 4097, AnnotationStyleError::Limit),
        ] {
            let mut bad = bytes.clone();
            bad[offset..offset + 4].copy_from_slice(&u32::to_le_bytes(value));
            assert_eq!(resolve_packed(&bad), Err(error));
        }
        assert_eq!(
            resolve_packed(&frame(&[(Some("a\0b"), Some("text"), vec![])])),
            Err(AnnotationStyleError::Text)
        );
        let mut invalid = frame(&[text_row(vec![])]);
        invalid[28] = 255;
        assert_eq!(resolve_packed(&invalid), Err(AnnotationStyleError::Text));
        assert_eq!(
            resolve_packed(&frame(&[text_row(vec![
                ("a", Value::Null),
                ("a", Value::Null)
            ])])),
            Err(AnnotationStyleError::Flags)
        );
        let mut bad_bool = frame(&[text_row(vec![("unknown", Value::Bool(true))])]);
        let n = bad_bool.len();
        bad_bool[n - 4..].copy_from_slice(&2_u32.to_le_bytes());
        assert_eq!(resolve_packed(&bad_bool), Err(AnnotationStyleError::Flags));
        let mut bad_type = frame(&[text_row(vec![("unknown", Value::Null)])]);
        let n = bad_type.len();
        bad_type[n - 4..].copy_from_slice(&5_u32.to_le_bytes());
        assert_eq!(resolve_packed(&bad_type), Err(AnnotationStyleError::Flags));
        let long = "x".repeat(MAX_TEXT);
        assert!(resolve_packed(&frame(&[(Some(&long), Some("text"), vec![])])).is_ok());
        let keys: Vec<_> = (0..MAX_STYLES).map(|n| format!("key{n}")).collect();
        assert!(resolve_packed(&frame(&[text_row(
            keys.iter()
                .map(|key| (key.as_str(), Value::Opaque))
                .collect()
        )]))
        .is_ok());
        assert_eq!(
            resolve_packed(&vec![0; MAX_BYTES + 1]),
            Err(AnnotationStyleError::Limit)
        );
        assert!(resolve_packed(&frame(&vec![text_row(vec![]); MAX_ROWS])).is_ok());
    }
}
