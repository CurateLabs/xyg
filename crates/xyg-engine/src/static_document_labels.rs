//! XYDA document-label authoring policy (M2 #873; dossier §21/§28).
//! Emits XYDD label records; hosts only marshal optional authored facts.
use crate::css::{color_rgba8, parse_color, Checked};

const MAX_BYTES: usize = 2 * 1024 * 1024;
const MAX_TEXT: usize = 4096;

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum DocumentLabelsError {
    Header,
    Version,
    Flags,
    Limit,
    Text,
    Style,
}
impl DocumentLabelsError {
    pub fn reason(self) -> &'static str {
        match self {
            Self::Header => "XYG_STATIC_DOCUMENT_LABELS_HEADER",
            Self::Version => "XYG_STATIC_DOCUMENT_LABELS_VERSION",
            Self::Flags => "XYG_STATIC_DOCUMENT_LABELS_FLAGS",
            Self::Limit => "XYG_STATIC_DOCUMENT_LABELS_LIMIT",
            Self::Text => "XYG_STATIC_DOCUMENT_LABELS_TEXT",
            Self::Style => "XYG_STATIC_UNSUPPORTED_FIGURE_LABEL_STYLE",
        }
    }
}
type Result<T> = std::result::Result<T, DocumentLabelsError>;
struct Reader<'a> {
    bytes: &'a [u8],
    at: usize,
}
impl<'a> Reader<'a> {
    fn take(&mut self, n: usize) -> Result<&'a [u8]> {
        let end = self.at.checked_add(n).ok_or(DocumentLabelsError::Limit)?;
        let out = self
            .bytes
            .get(self.at..end)
            .ok_or(DocumentLabelsError::Header)?;
        self.at = end;
        Ok(out)
    }
    fn u32(&mut self) -> Result<u32> {
        Ok(u32::from_le_bytes(self.take(4)?.try_into().unwrap()))
    }
    fn number(&mut self, present: bool, default: f64) -> Result<f64> {
        let raw: [u8; 8] = self.take(8)?.try_into().unwrap();
        let value = if present {
            f64::from_le_bytes(raw)
        } else if raw == [0; 8] {
            default
        } else {
            return Err(DocumentLabelsError::Flags);
        };
        if value.is_finite() && (value as f32).is_finite() {
            Ok(value)
        } else {
            Err(DocumentLabelsError::Style)
        }
    }
    fn text(&mut self) -> Result<Option<&'a str>> {
        let len = self.u32()?;
        if len == u32::MAX {
            return Ok(None);
        }
        if len as usize > MAX_TEXT {
            return Err(DocumentLabelsError::Limit);
        }
        let bytes = self.take(len as usize)?;
        if bytes.contains(&0) {
            return Err(DocumentLabelsError::Text);
        }
        Ok(Some(
            std::str::from_utf8(bytes).map_err(|_| DocumentLabelsError::Text)?,
        ))
    }
}

/// Resolve bounded XYDA v1 into concatenated 40-byte XYDD label records/text.
pub fn resolve_packed(bytes: &[u8]) -> Result<Vec<u8>> {
    if bytes.len() > MAX_BYTES {
        return Err(DocumentLabelsError::Limit);
    }
    let mut r = Reader { bytes, at: 0 };
    if r.take(4)? != b"XYDA" {
        return Err(DocumentLabelsError::Header);
    }
    if r.u32()? != 1 {
        return Err(DocumentLabelsError::Version);
    }
    let count = r.u32()?;
    if count > 64 {
        return Err(DocumentLabelsError::Limit);
    }
    if r.u32()? != 0 {
        return Err(DocumentLabelsError::Flags);
    }
    let mut out = Vec::new();
    for _ in 0..count {
        let flags = r.u32()?;
        if flags & !31 != 0 || r.u32()? != 0 {
            return Err(DocumentLabelsError::Flags);
        }
        let x = r.number(flags & 1 != 0, 0.5)?;
        let y = r.number(flags & 2 != 0, 0.5)?;
        let size = r.number(flags & 4 != 0, 12.0)?;
        let rotation = r.number(flags & 8 != 0, 0.0)?;
        let opacity = r.number(flags & 16 != 0, 1.0)?;
        if !(1.0..=4096.0).contains(&size) || !(0.0..=1.0).contains(&opacity) {
            return Err(DocumentLabelsError::Style);
        }
        let text = r.text()?.unwrap_or("");
        let family = r
            .text()?
            .unwrap_or("system-ui,sans-serif")
            .to_lowercase()
            .replace(' ', "");
        if !matches!(
            family.as_str(),
            "system-ui,sans-serif" | "dejavusans" | "sans-serif"
        ) {
            return Err(DocumentLabelsError::Style);
        }
        let anchor = match r.text()?.unwrap_or("middle") {
            "start" => 0,
            "middle" => 1,
            "end" => 2,
            _ => return Err(DocumentLabelsError::Style),
        };
        let vertical = match r.text()?.unwrap_or("center") {
            "top" => 0,
            "baseline" => 1,
            "bottom" => 2,
            "center" | "center_baseline" => 3,
            _ => return Err(DocumentLabelsError::Style),
        };
        let italic = match r.text()?.unwrap_or("normal").to_lowercase().as_str() {
            "normal" => 0,
            "italic" | "oblique" => 1,
            _ => return Err(DocumentLabelsError::Style),
        };
        let bold = match r.text()?.unwrap_or("normal").to_lowercase().as_str() {
            "normal" | "regular" | "book" | "400" => 0,
            "bold" | "semibold" | "demibold" | "heavy" | "black" | "600" | "700" | "800"
            | "900" => 2,
            _ => return Err(DocumentLabelsError::Style),
        };
        let color = r.text()?.unwrap_or("#262626");
        if !matches!(parse_color(color), Ok(Checked::Parsed(Some(_)))) {
            return Err(DocumentLabelsError::Style);
        }
        for value in [x, y, size, rotation, opacity] {
            out.extend_from_slice(&(value as f32).to_le_bytes());
        }
        out.extend_from_slice(&color_rgba8(color, 1.0));
        out.extend_from_slice(&[anchor, vertical, italic | bold, 0]);
        out.extend_from_slice(&(text.len() as u32).to_le_bytes());
        out.extend_from_slice(&[0; 8]);
        out.extend_from_slice(text.as_bytes());
    }
    if r.at != bytes.len() {
        return Err(DocumentLabelsError::Header);
    }
    Ok(out)
}

#[cfg(test)]
mod tests {
    use super::*;
    fn request(fields: [Option<&str>; 7]) -> Vec<u8> {
        let mut out = b"XYDA".to_vec();
        for value in [1_u32, 1, 0] {
            out.extend_from_slice(&value.to_le_bytes());
        }
        out.extend_from_slice(&[0; 48]);
        for field in fields {
            out.extend_from_slice(&field.map_or(u32::MAX, |s| s.len() as u32).to_le_bytes());
            if let Some(value) = field {
                out.extend_from_slice(value.as_bytes());
            }
        }
        out
    }
    #[test]
    fn default_label_and_empty_array_have_exact_record_bytes() {
        let out = resolve_packed(&request([None; 7])).unwrap();
        let mut expected = Vec::new();
        for value in [0.5_f32, 0.5, 12.0, 0.0, 1.0] {
            expected.extend_from_slice(&value.to_le_bytes());
        }
        expected.extend_from_slice(&[38, 38, 38, 255, 1, 3, 0, 0]);
        expected.extend_from_slice(&[0; 12]);
        assert_eq!(out, expected);
        let mut empty = request([None; 7]);
        empty.truncate(16);
        empty[8..12].copy_from_slice(&0u32.to_le_bytes());
        assert_eq!(resolve_packed(&empty).unwrap(), b"");
    }
    #[test]
    fn every_alignment_and_text_style_maps_natively() {
        for (anchor, code) in [("start", 0), ("middle", 1), ("end", 2)] {
            for (vertical, vcode) in [
                ("top", 0),
                ("baseline", 1),
                ("bottom", 2),
                ("center", 3),
                ("center_baseline", 3),
            ] {
                for (weight, bold) in [
                    ("normal", 0),
                    ("regular", 0),
                    ("book", 0),
                    ("400", 0),
                    ("bold", 2),
                    ("semibold", 2),
                    ("demibold", 2),
                    ("heavy", 2),
                    ("black", 2),
                    ("600", 2),
                    ("700", 2),
                    ("800", 2),
                    ("900", 2),
                ] {
                    let request = request([
                        Some("雪 & é"),
                        Some("DejaVu Sans"),
                        Some(anchor),
                        Some(vertical),
                        Some("Oblique"),
                        Some(weight),
                        Some("#01020380"),
                    ]);
                    let out = resolve_packed(&request).unwrap();
                    assert_eq!(&out[20..28], &[1, 2, 3, 128, code, vcode, 1 | bold, 0]);
                    assert_eq!(&out[40..], "雪 & é".as_bytes());
                }
            }
        }
    }
    #[test]
    fn numeric_facts_preserve_outside_placement_and_rotations() {
        let mut input = request([None; 7]);
        input[16..20].copy_from_slice(&31u32.to_le_bytes());
        let values = [-0.5_f64, 1.5, 4096.0, 450.0, 0.25];
        for (index, value) in values.into_iter().enumerate() {
            input[24 + index * 8..32 + index * 8].copy_from_slice(&value.to_le_bytes());
        }
        let out = resolve_packed(&input).unwrap();
        for (index, expected) in values.into_iter().enumerate() {
            assert_eq!(
                f32::from_le_bytes(out[index * 4..index * 4 + 4].try_into().unwrap()),
                expected as f32
            );
        }
    }
    #[test]
    fn nonfinite_narrowing_and_invalid_style_never_emit_records() {
        for index in 0..5 {
            for value in [f64::NAN, f64::INFINITY, 1e300] {
                let mut input = request([None; 7]);
                input[16..20].copy_from_slice(&(1u32 << index).to_le_bytes());
                input[24 + index * 8..32 + index * 8].copy_from_slice(&value.to_le_bytes());
                assert_eq!(resolve_packed(&input), Err(DocumentLabelsError::Style));
            }
        }
        for (index, value) in [
            (1, "Arial"),
            (2, "left"),
            (3, "middle"),
            (4, "slanted"),
            (5, "500"),
            (6, "var(--ink)"),
        ] {
            let mut fields = [None; 7];
            fields[index] = Some(value);
            assert_eq!(
                resolve_packed(&request(fields)),
                Err(DocumentLabelsError::Style)
            );
        }
        for (index, value) in [
            (2, 0.0_f64),
            (2, 4097.0),
            (4, -0.1),
            (4, 1.1),
            (2, 0.99999999),
            (2, 4096.0001),
            (4, -1e-50),
            (4, 1.00000001),
        ] {
            let mut input = request([None; 7]);
            input[16..20].copy_from_slice(&(1u32 << index).to_le_bytes());
            input[24 + index * 8..32 + index * 8].copy_from_slice(&value.to_le_bytes());
            assert_eq!(resolve_packed(&input), Err(DocumentLabelsError::Style));
        }
    }
    #[test]
    fn framing_limits_reserved_and_text_are_checked_before_output() {
        let input = request([None; 7]);
        for n in 0..input.len() {
            assert!(resolve_packed(&input[..n]).is_err());
        }
        for (at, value, error) in [
            (4, 2, DocumentLabelsError::Version),
            (8, 65, DocumentLabelsError::Limit),
            (12, 1, DocumentLabelsError::Flags),
            (16, 32, DocumentLabelsError::Flags),
            (20, 1, DocumentLabelsError::Flags),
            (24, 1, DocumentLabelsError::Flags),
            (64, 4097, DocumentLabelsError::Limit),
        ] {
            let mut bad = input.clone();
            bad[at..at + 4].copy_from_slice(&(value as u32).to_le_bytes());
            assert_eq!(resolve_packed(&bad), Err(error));
        }
        for byte in [0, 255] {
            let mut bad = request([Some("x"), None, None, None, None, None, None]);
            bad[68] = byte;
            assert_eq!(resolve_packed(&bad), Err(DocumentLabelsError::Text));
        }
        let mut bad = input.clone();
        bad.push(0);
        assert_eq!(resolve_packed(&bad), Err(DocumentLabelsError::Header));
        bad.resize(MAX_BYTES + 1, 0);
        assert_eq!(resolve_packed(&bad), Err(DocumentLabelsError::Limit));
    }
}
