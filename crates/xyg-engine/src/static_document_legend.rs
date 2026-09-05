//! Static-document legend policy from authored XYDL facts (dossier §21/§28).
//! Hosts carry optional literals; defaults, glyph choice, paint, and framing
//! live here. Output is the existing XYDD legend block, not Scene's XYLG wire.
use crate::css::{color_rgba8, parse_color, Checked};

const MAX_BYTES: usize = 2 * 1024 * 1024;
const MAX_TEXT: usize = 4096;
const MAX_ITEMS: usize = 256;

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum DocumentLegendError {
    Header,
    Version,
    Flags,
    Limit,
    Text,
    Style,
    Anchor,
}
impl DocumentLegendError {
    pub fn reason(self) -> &'static str {
        match self {
            Self::Header => "XYG_STATIC_DOCUMENT_LEGEND_HEADER",
            Self::Version => "XYG_STATIC_DOCUMENT_LEGEND_VERSION",
            Self::Flags => "XYG_STATIC_DOCUMENT_LEGEND_FLAGS",
            Self::Limit => "XYG_STATIC_DOCUMENT_LEGEND_LIMIT",
            Self::Text => "XYG_STATIC_DOCUMENT_LEGEND_TEXT",
            Self::Style => "XYG_STATIC_UNSUPPORTED_FIGURE_LEGEND_STYLE",
            Self::Anchor => "XYG_STATIC_UNSUPPORTED_PANEL_LEGEND_ANCHOR",
        }
    }
}
type Result<T> = std::result::Result<T, DocumentLegendError>;

struct Reader<'a> {
    bytes: &'a [u8],
    at: usize,
}
impl<'a> Reader<'a> {
    fn take(&mut self, n: usize) -> Result<&'a [u8]> {
        let end = self.at.checked_add(n).ok_or(DocumentLegendError::Limit)?;
        let out = self
            .bytes
            .get(self.at..end)
            .ok_or(DocumentLegendError::Header)?;
        self.at = end;
        Ok(out)
    }
    fn u32(&mut self) -> Result<u32> {
        Ok(u32::from_le_bytes(self.take(4)?.try_into().unwrap()))
    }
    fn number(&mut self, present: bool, default: f64) -> Result<f64> {
        let raw: [u8; 8] = self.take(8)?.try_into().unwrap();
        if !present {
            return if raw == [0; 8] {
                Ok(default)
            } else {
                Err(DocumentLegendError::Flags)
            };
        }
        let value = f64::from_le_bytes(raw);
        if value.is_finite() {
            Ok(value)
        } else {
            Err(DocumentLegendError::Style)
        }
    }
    fn text(&mut self) -> Result<Option<&'a str>> {
        let n = self.u32()?;
        if n == u32::MAX {
            return Ok(None);
        }
        if n as usize > MAX_TEXT {
            return Err(DocumentLegendError::Limit);
        }
        let bytes = self.take(n as usize)?;
        if bytes.contains(&0) {
            return Err(DocumentLegendError::Text);
        }
        Ok(Some(
            std::str::from_utf8(bytes).map_err(|_| DocumentLegendError::Text)?,
        ))
    }
}

fn css_number(value: Option<&str>, suffix: &str, default: f64) -> Result<f64> {
    let value = value
        .and_then(|value| value.trim().strip_suffix(suffix))
        .and_then(|value| value.trim().parse::<f64>().ok())
        .unwrap_or(default);
    if value.is_finite() {
        Ok(value)
    } else {
        Err(DocumentLegendError::Style)
    }
}
fn paint(value: Option<&str>, default: &str) -> Result<[u8; 4]> {
    let value = value.unwrap_or(default);
    if matches!(parse_color(value), Ok(Checked::Parsed(Some(_)))) {
        Ok(color_rgba8(value, 1.0))
    } else {
        Err(DocumentLegendError::Style)
    }
}
fn output_f32(out: &mut Vec<u8>, value: f64, positive: bool) -> Result<()> {
    if !value.is_finite() || value < 0.0 || (positive && value == 0.0) {
        return Err(DocumentLegendError::Style);
    }
    let value = value as f32;
    if !value.is_finite() || value < 0.0 || (positive && value == 0.0) {
        return Err(DocumentLegendError::Style);
    }
    out.extend_from_slice(&value.to_le_bytes());
    Ok(())
}
fn alpha(mut rgba: [u8; 4], opacity: f64) -> [u8; 4] {
    // Preserve Python's f64 round-to-even at exact half-alpha boundaries.
    rgba[3] = (f64::from(rgba[3]) * opacity.clamp(0.0, 1.0)).round_ties_even() as u8;
    rgba
}

/// Validate XYDL v1 and return the exact legacy XYDD legend block.
pub fn resolve_packed(bytes: &[u8]) -> Result<Vec<u8>> {
    if bytes.len() > MAX_BYTES {
        return Err(DocumentLegendError::Limit);
    }
    let mut r = Reader { bytes, at: 0 };
    if r.take(4)? != b"XYDL" {
        return Err(DocumentLegendError::Header);
    }
    if r.u32()? != 1 {
        return Err(DocumentLegendError::Version);
    }
    let flags = r.u32()?;
    let count = r.u32()? as usize;
    let raw_ncols = r.u32()?;
    if flags & !31 != 0 || r.u32()? != 0 || (flags & 1 == 0 && raw_ncols != 0) {
        return Err(DocumentLegendError::Flags);
    }
    let ncols = if flags & 1 != 0 {
        (raw_ncols as i32).max(1) as u32
    } else {
        1
    };
    if count > MAX_ITEMS || ncols > MAX_ITEMS as u32 {
        return Err(DocumentLegendError::Limit);
    }
    let handle_length = r.number(flags & 2 != 0, 2.0)?;
    let handle_pad = r.number(flags & 4 != 0, 0.8)?;
    let border_pad = r.number(flags & 8 != 0, 0.0)?.max(0.0);
    let anchor_error = |error| match error {
        DocumentLegendError::Style => DocumentLegendError::Anchor,
        other => other,
    };
    let anchor_x = r.number(flags & 16 != 0, 0.0).map_err(anchor_error)?;
    let anchor_y = r.number(flags & 16 != 0, 0.0).map_err(anchor_error)?;
    let title = r.text()?.unwrap_or("");
    let loc = r.text()?.unwrap_or("upper right");
    let figure_loc = r.text()?;
    let font = css_number(r.text()?, "px", 11.0)?;
    let padding = css_number(r.text()?, "em", 0.4)?;
    let row_gap = css_number(r.text()?, "em", 0.5)?;
    let text = paint(r.text()?, "#262626")?;
    let background_css = r.text()?;
    let background = paint(background_css, "#808080")?;
    let border = paint(r.text()?, "#cccccc")?;
    let frame_alpha = match r.text()? {
        None => {
            if background_css.is_some() {
                1.0
            } else {
                0.08
            }
        }
        Some(value) => value
            .trim()
            .parse::<f64>()
            .map_err(|_| DocumentLegendError::Style)?,
    };
    if !frame_alpha.is_finite() || r.text()?.is_some() {
        return Err(DocumentLegendError::Style);
    }
    let loc = if figure_loc == Some("outside right upper") {
        "upper right"
    } else {
        loc
    };
    if loc.is_empty() {
        return Err(DocumentLegendError::Style);
    }
    let mut out = Vec::new();
    for n in [count as u32, title.len() as u32, loc.len() as u32, ncols] {
        out.extend_from_slice(&n.to_le_bytes());
    }
    for (n, positive) in [
        (font, true),
        (handle_length, false),
        (handle_pad, false),
        (padding, false),
        (row_gap, false),
        (border_pad, false),
    ] {
        output_f32(&mut out, n, positive)?;
    }
    out.extend_from_slice(&text);
    out.extend_from_slice(&alpha(background, frame_alpha));
    out.extend_from_slice(&alpha(border, frame_alpha));
    for value in [anchor_x, anchor_y] {
        let value = value as f32;
        if !value.is_finite() {
            return Err(DocumentLegendError::Anchor);
        }
        out.extend_from_slice(&value.to_le_bytes());
    }
    out.extend_from_slice(&[u8::from(flags & 16 != 0), 0, 0, 0]);
    out.extend_from_slice(title.as_bytes());
    out.extend_from_slice(loc.as_bytes());
    for _ in 0..count {
        let flags = r.u32()?;
        if flags & !31 != 0 || r.u32()? != 0 {
            return Err(DocumentLegendError::Flags);
        }
        let width = r.number(flags & 1 != 0, 1.5)?;
        let stroke_width = r.number(flags & 2 != 0, 1.5)?;
        let size = r.number(flags & 4 != 0, 8.0)?;
        let opacity = r.number(flags & 8 != 0, 1.0)?.clamp(0.0, 1.0);
        let kind = r.text()?.unwrap_or("line");
        let name = r.text()?.unwrap_or("");
        let rgba = paint(r.text()?, "#4c78a8")?;
        let symbol = r.text()?.unwrap_or("circle");
        let kind = match kind {
            "line" | "segments" | "step" | "stairs" | "errorbar" | "stem" => 0,
            "scatter" if symbol == "circle" => 1,
            "scatter" => return Err(DocumentLegendError::Style),
            _ => 2,
        };
        out.extend_from_slice(&[kind, u8::from(flags & 16 != 0), 0, 0]);
        out.extend_from_slice(&rgba);
        output_f32(
            &mut out,
            if flags & 1 != 0 { width } else { stroke_width },
            false,
        )?;
        output_f32(&mut out, size, true)?;
        output_f32(&mut out, opacity, false)?;
        out.extend_from_slice(&(name.len() as u32).to_le_bytes());
        out.extend_from_slice(&[0; 4]);
        out.extend_from_slice(name.as_bytes());
    }
    if r.at != bytes.len() {
        return Err(DocumentLegendError::Header);
    }
    if count == 0 {
        out.clear();
    }
    Ok(out)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn text(out: &mut Vec<u8>, value: Option<&str>) {
        out.extend_from_slice(
            &value
                .map_or(u32::MAX, |value| value.len() as u32)
                .to_le_bytes(),
        );
        if let Some(value) = value {
            out.extend_from_slice(value.as_bytes());
        }
    }
    fn request(style: [Option<&str>; 11], kinds: &[&str]) -> Vec<u8> {
        let mut out = b"XYDL".to_vec();
        for n in [1, 0, kinds.len() as u32, 0, 0] {
            out.extend_from_slice(&n.to_le_bytes());
        }
        out.extend_from_slice(&[0; 40]);
        for value in style {
            text(&mut out, value);
        }
        for kind in kinds {
            out.extend_from_slice(&[0; 40]);
            for value in [Some(*kind), Some("key"), None, None] {
                text(&mut out, value);
            }
        }
        out
    }
    fn f32_at(bytes: &[u8], at: usize) -> f32 {
        f32::from_le_bytes(bytes[at..at + 4].try_into().unwrap())
    }

    #[test]
    fn defaults_match_existing_document_legend_wire() {
        let out = resolve_packed(&request([None; 11], &["line"])).unwrap();
        assert_eq!(out.len(), 64 + 11 + 28 + 3);
        assert_eq!(
            &out[..16],
            &[1, 0, 0, 0, 0, 0, 0, 0, 11, 0, 0, 0, 1, 0, 0, 0]
        );
        assert_eq!(f32_at(&out, 16), 11.0);
        assert_eq!(f32_at(&out, 20), 2.0);
        assert_eq!(f32_at(&out, 24), 0.8);
        assert_eq!(
            &out[40..52],
            &[38, 38, 38, 255, 128, 128, 128, 20, 204, 204, 204, 20]
        );
        assert_eq!(&out[64..75], b"upper right");
        assert_eq!(&out[75..83], &[0, 0, 0, 0, 76, 120, 168, 255]);
        assert_eq!(f32_at(&out, 83), 1.5);
        assert_eq!(f32_at(&out, 87), 8.0);
        assert_eq!(f32_at(&out, 91), 1.0);
        assert_eq!(&out[103..], b"key");
        assert!(resolve_packed(&request([None; 11], &[]))
            .unwrap()
            .is_empty());
    }
    #[test]
    fn classifies_all_line_kinds_scatter_and_fill() {
        let kinds = [
            "line", "segments", "step", "stairs", "errorbar", "stem", "scatter", "bar", "area",
        ];
        let out = resolve_packed(&request([None; 11], &kinds)).unwrap();
        for (i, expected) in [0, 0, 0, 0, 0, 0, 1, 2, 2].into_iter().enumerate() {
            assert_eq!(out[75 + i * 31], expected);
        }
    }
    #[test]
    fn resolves_css_frame_alpha_and_outside_location_in_rust() {
        let mut style = [None; 11];
        style[0] = Some("t");
        style[1] = Some("lower left");
        style[2] = Some("outside right upper");
        style[3] = Some(" 14px ");
        style[4] = Some("0.75em");
        style[5] = Some("invalid");
        style[7] = Some("#01020305");
        style[9] = Some("0.5");
        let out = resolve_packed(&request(style, &["line"])).unwrap();
        assert_eq!(f32_at(&out, 16), 14.0);
        assert_eq!(f32_at(&out, 28), 0.75);
        assert_eq!(f32_at(&out, 32), 0.5);
        assert_eq!(&out[44..48], &[1, 2, 3, 2]);
        assert_eq!(&out[64..76], b"tupper right");
    }
    #[test]
    fn numeric_presence_precedence_clamps_and_anchor_are_native() {
        let mut input = request([None; 11], &["line"]);
        input[8..12].copy_from_slice(&31u32.to_le_bytes());
        input[16..20].copy_from_slice(&(-5_i32).to_le_bytes());
        for (at, value) in [(24, 3.0_f64), (32, 1.0), (40, -4.0), (48, -0.5), (56, 1.5)] {
            input[at..at + 8].copy_from_slice(&value.to_le_bytes());
        }
        let item = 64 + 11 * 4;
        input[item..item + 4].copy_from_slice(&27u32.to_le_bytes());
        for (offset, value) in [(8, 4.0_f64), (16, 7.0), (32, 2.0)] {
            input[item + offset..item + offset + 8].copy_from_slice(&value.to_le_bytes());
        }
        let out = resolve_packed(&input).unwrap();
        assert_eq!(out[12], 1);
        assert_eq!(f32_at(&out, 36), 0.0);
        assert_eq!(f32_at(&out, 52), -0.5);
        assert_eq!(out[60], 1);
        assert_eq!(out[76], 1);
        assert_eq!(f32_at(&out, 83), 4.0);
        assert_eq!(f32_at(&out, 91), 1.0);
    }
    #[test]
    fn header_text_resource_and_narrowing_failures_are_explicit() {
        let input = request([None; 11], &["line"]);
        for (at, value, expected) in [
            (4, 2u32, DocumentLegendError::Version),
            (8, 32, DocumentLegendError::Flags),
            (12, 257, DocumentLegendError::Limit),
            (20, 1, DocumentLegendError::Flags),
            (64, 4097, DocumentLegendError::Limit),
            (64 + 11 * 4, 32, DocumentLegendError::Flags),
        ] {
            let mut bad = input.clone();
            bad[at..at + 4].copy_from_slice(&value.to_le_bytes());
            assert_eq!(resolve_packed(&bad), Err(expected));
        }
        let mut bad = input.clone();
        bad[8..12].copy_from_slice(&1u32.to_le_bytes());
        bad[16..20].copy_from_slice(&257u32.to_le_bytes());
        assert_eq!(resolve_packed(&bad), Err(DocumentLegendError::Limit));
        bad.resize(MAX_BYTES + 1, 0);
        assert_eq!(resolve_packed(&bad), Err(DocumentLegendError::Limit));
        let mut style = [None; 11];
        style[0] = Some("x");
        for byte in [0, 255] {
            let mut bad = request(style, &["line"]);
            bad[68] = byte;
            assert_eq!(resolve_packed(&bad), Err(DocumentLegendError::Text));
        }
        for value in [f64::NAN, f64::INFINITY, 1e300] {
            for at in [48, 56] {
                let mut bad = input.clone();
                bad[8..12].copy_from_slice(&16u32.to_le_bytes());
                bad[at..at + 8].copy_from_slice(&value.to_le_bytes());
                assert_eq!(resolve_packed(&bad), Err(DocumentLegendError::Anchor));
            }
            let mut bad = input.clone();
            bad[8..12].copy_from_slice(&2u32.to_le_bytes());
            bad[24..32].copy_from_slice(&value.to_le_bytes());
            assert_eq!(resolve_packed(&bad), Err(DocumentLegendError::Style));
        }
        let mut bad = input.clone();
        bad[8..12].copy_from_slice(&2u32.to_le_bytes());
        bad[24..32].copy_from_slice(&(-1e-50_f64).to_le_bytes());
        assert_eq!(resolve_packed(&bad), Err(DocumentLegendError::Style));
        let mut bad = input;
        let item = 64 + 11 * 4;
        bad[item..item + 4].copy_from_slice(&1u32.to_le_bytes());
        bad[item + 8..item + 16].copy_from_slice(&(-1e-50_f64).to_le_bytes());
        assert_eq!(resolve_packed(&bad), Err(DocumentLegendError::Style));
    }

    #[test]
    fn rejects_browser_styles_fonts_nonfinite_and_malformed_facts() {
        for (index, value) in [(3, "NaNpx"), (7, "var(--paint)"), (9, "inf"), (10, "Arial")] {
            let mut style = [None; 11];
            style[index] = Some(value);
            assert_eq!(
                resolve_packed(&request(style, &["line"])),
                Err(DocumentLegendError::Style)
            );
        }
        let input = request([None; 11], &["line"]);
        for len in 0..input.len() {
            assert!(resolve_packed(&input[..len]).is_err());
        }
        for at in [20, 24, 64 + 11 * 4 + 8] {
            let mut bad = input.clone();
            bad[at] = 1;
            assert_eq!(resolve_packed(&bad), Err(DocumentLegendError::Flags));
        }
        let mut bad = input.clone();
        bad.push(0);
        assert_eq!(resolve_packed(&bad), Err(DocumentLegendError::Header));
        let mut bad = request([None; 11], &["scatter"]);
        bad.truncate(bad.len() - 4);
        text(&mut bad, Some("diamond"));
        assert_eq!(resolve_packed(&bad), Err(DocumentLegendError::Style));
    }
}
