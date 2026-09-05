//! Native pyplot panel gutters and outside reservations (M2 #873; dossier §21).
//! XYPC/XYPO framing is specified in `spec/design/static-panel-chrome.md`.

use crate::{compat_layout, layout_rooms, textblock};

pub const HEADER_BYTES: usize = 200;
pub const MAX_BYTES: usize = 1 << 20;
const MAX_LABELS: usize = 4096;
const MAX_TEXT: usize = 4096;
const MAX_DIMENSION: f64 = 65_535.0;
const Y_LABELS_VISIBLE: u32 = 1;
const X_TOP: u32 = 2;
const RIGHT_SECONDARY: u32 = 4;
const AUTHORED_Y_LABEL_OFFSET: u32 = 8;
const MEASURED_GUTTERS: u32 = 16;

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum PanelChromeError {
    Header,
    Version,
    Flags,
    Limit,
    Text,
    Facts,
    BrowserCss,
    CustomFont,
}

impl PanelChromeError {
    pub fn reason(self) -> &'static str {
        match self {
            Self::Header => "XYG_STATIC_CHROME_HEADER",
            Self::Version => "XYG_STATIC_CHROME_VERSION",
            Self::Flags => "XYG_STATIC_CHROME_FLAGS",
            Self::Limit => "XYG_STATIC_CHROME_LIMIT",
            Self::Text => "XYG_STATIC_CHROME_TEXT",
            Self::Facts => "XYG_STATIC_CHROME_FACTS",
            Self::BrowserCss => "XYG_STATIC_UNSUPPORTED_BROWSER_CHROME",
            Self::CustomFont => "XYG_STATIC_UNSUPPORTED_CUSTOM_FONT",
        }
    }
}

fn u32_at(bytes: &[u8], at: usize) -> u32 {
    u32::from_le_bytes(bytes[at..at + 4].try_into().unwrap())
}

fn f64_at(bytes: &[u8], at: usize) -> f64 {
    f64::from_le_bytes(bytes[at..at + 8].try_into().unwrap())
}

struct Reader<'a> {
    bytes: &'a [u8],
    at: usize,
}

impl<'a> Reader<'a> {
    fn take(&mut self, len: usize) -> Result<&'a [u8], PanelChromeError> {
        let end = self.at.checked_add(len).ok_or(PanelChromeError::Limit)?;
        let slice = self
            .bytes
            .get(self.at..end)
            .ok_or(PanelChromeError::Header)?;
        self.at = end;
        Ok(slice)
    }

    fn text(&mut self, len: usize) -> Result<&'a str, PanelChromeError> {
        if len > MAX_TEXT {
            return Err(PanelChromeError::Limit);
        }
        let value = std::str::from_utf8(self.take(len)?).map_err(|_| PanelChromeError::Text)?;
        if value.contains('\0') {
            return Err(PanelChromeError::Text);
        }
        Ok(value)
    }

    fn labels(&mut self, count: usize) -> Result<Vec<&'a str>, PanelChromeError> {
        (0..count)
            .map(|_| {
                let len = u32_at(self.take(4)?, 0) as usize;
                self.text(len)
            })
            .collect()
    }
}

fn measure(text: &str, size: f64) -> Result<textblock::TextBlock, PanelChromeError> {
    textblock::measure(text, size.max(0.0), textblock::LINE_HEIGHT, None)
        .ok_or(PanelChromeError::Facts)
}

/// Resolve complete authored gutter facts. Optional measured gutters must come
/// from the Rust Scene layout query; the host only passes that result through.
pub fn resolve_packed(bytes: &[u8]) -> Result<Vec<u8>, PanelChromeError> {
    if bytes.len() < HEADER_BYTES || bytes.len() > MAX_BYTES || &bytes[..4] != b"XYPC" {
        return Err(PanelChromeError::Header);
    }
    if u32_at(bytes, 4) != 1 {
        return Err(PanelChromeError::Version);
    }
    let flags = u32_at(bytes, 8);
    let rows = u32_at(bytes, 12);
    let x_count = u32_at(bytes, 16) as usize;
    let y_count = u32_at(bytes, 20) as usize;
    let title_count = u32_at(bytes, 24) as usize;
    let x_label_len = u32_at(bytes, 28) as usize;
    let y_label_len = u32_at(bytes, 32) as usize;
    let unsupported = u32_at(bytes, 36);
    let direction = u32_at(bytes, 40);
    let colorbar = u32_at(bytes, 44);
    let colorbar_flags = u32_at(bytes, 48);
    let compact_hint = u32_at(bytes, 52);
    if flags & !31 != 0
        || unsupported > 2
        || direction > 2
        || colorbar > 4
        || colorbar_flags & !3 != 0
        || compact_hint > 2
        || bytes[56..64] != [0; 8]
        || (colorbar == 0 && colorbar_flags != 0)
    {
        return Err(PanelChromeError::Flags);
    }
    if rows > 256 || x_count > MAX_LABELS || y_count > MAX_LABELS || title_count > 3 {
        return Err(PanelChromeError::Limit);
    }
    let values: [f64; 17] = std::array::from_fn(|index| f64_at(bytes, 64 + index * 8));
    if values
        .iter()
        .any(|value| !value.is_finite() || value.abs() > MAX_DIMENSION)
        || values[0] <= 0.0
        || values[1] < 0.0
        || values[2] <= 0.0
        || values[3] < 0.0
        || (rows == 0) != (values[1] == 0.0)
        || (flags & AUTHORED_Y_LABEL_OFFSET == 0 && bytes[160..168] != [0; 8])
        || (flags & MEASURED_GUTTERS == 0 && bytes[168..200] != [0; 32])
        || (flags & MEASURED_GUTTERS != 0 && values[13..17].iter().any(|v| *v < 0.0))
    {
        return Err(PanelChromeError::Facts);
    }
    let mut reader = Reader {
        bytes,
        at: HEADER_BYTES,
    };
    let x_label = reader.text(x_label_len)?;
    let y_label = reader.text(y_label_len)?;
    let x_labels = reader.labels(x_count)?;
    let y_labels = reader.labels(y_count)?;
    let mut titles = Vec::with_capacity(title_count);
    for _ in 0..title_count {
        let record = reader.take(32)?;
        let size = f64_at(record, 0);
        let pad = f64_at(record, 8);
        let y = f64_at(record, 16);
        let automatic = u32_at(record, 24);
        if automatic > 1
            || [size, pad, y]
                .iter()
                .any(|v| !v.is_finite() || v.abs() > MAX_DIMENSION)
        {
            return Err(PanelChromeError::Facts);
        }
        let text = reader.text(u32_at(record, 28) as usize)?;
        titles.push((size, pad, y, automatic != 0, text));
    }
    if reader.at != bytes.len() {
        return Err(PanelChromeError::Header);
    }
    match unsupported {
        1 => return Err(PanelChromeError::BrowserCss),
        2 => return Err(PanelChromeError::CustomFont),
        _ => {}
    }
    let compact = match compact_hint {
        1 => true,
        2 => false,
        _ => compat_layout::is_compact(values[0] + 54.0).ok_or(PanelChromeError::Facts)?,
    };
    let [top, right, bottom, mut left] = compat_layout::default_padding(compact);
    if flags & Y_LABELS_VISIBLE != 0 && !y_labels.is_empty() {
        let tick_width =
            layout_rooms::y_tick_label_extent(&y_labels, values[7].max(0.0), values[8])
                .ok_or(PanelChromeError::Facts)?;
        let tick_length = values[10].max(0.0);
        let outward = match direction {
            1 => 0.0,
            2 => tick_length / 2.0,
            _ => tick_length,
        };
        let mut needed =
            layout_rooms::AXIS_TEXT_EDGE_PAD + outward + values[11].max(0.0) + tick_width;
        if !y_label.is_empty() {
            let offset = if flags & AUTHORED_Y_LABEL_OFFSET != 0 {
                values[12]
            } else {
                0.4 * values[9]
            };
            needed += offset + measure(y_label, values[9])?.height;
        }
        left = left.max(needed);
    }
    let mut title_room = 0.0_f64;
    for (size, pad, y, automatic, text) in titles {
        let height = measure(text, size)?.height;
        let candidate = if automatic {
            (if compact { 26.0_f64 } else { 30.0_f64 }).max(height + pad)
        } else if y >= 1.0 {
            (height + pad).max(0.0)
        } else {
            0.0
        };
        title_room = title_room.max(candidate);
    }
    let mut multiline = 0.0_f64;
    for label in x_labels {
        let block = measure(label, values[4])?;
        if block.line_count() <= 1 {
            continue;
        }
        let first = measure(&block.lines[0], values[4])?;
        let (_, full_h) = textblock::rotated_extent(block.width, block.height, values[5])
            .ok_or(PanelChromeError::Facts)?;
        let (_, first_h) = textblock::rotated_extent(first.width, first.height, values[5])
            .ok_or(PanelChromeError::Facts)?;
        multiline = multiline.max(full_h - first_h);
    }
    if !x_label.is_empty() {
        let block = measure(x_label, values[6])?;
        multiline =
            multiline.max((block.line_count() - 1) as f64 * values[6] * textblock::LINE_HEIGHT);
    }
    let (mut extra_right, colorbar_bottom) =
        compat_layout::colorbar_extra(colorbar, colorbar_flags & 1 != 0, colorbar_flags & 2 != 0)
            .ok_or(PanelChromeError::Facts)?;
    if flags & RIGHT_SECONDARY != 0 {
        extra_right += compat_layout::right_y_room(compact);
    }
    let extra_top = title_room
        + if flags & X_TOP != 0 {
            (if compact { 26.0 } else { 32.0 }) + multiline
        } else {
            0.0
        };
    let extra_bottom = colorbar_bottom + if flags & X_TOP == 0 { multiline } else { 0.0 };
    let defaults = [
        left,
        top + extra_top,
        right + extra_right,
        (bottom + extra_bottom).max(values[3] * values[2] / 72.0),
    ];
    let probe_w = if rows == 0 {
        0.0
    } else {
        (values[0] + defaults[0] + defaults[2])
            .round_ties_even()
            .max(120.0)
    };
    let probe_h = if rows == 0 {
        0.0
    } else {
        (values[1] / f64::from(rows)).round_ties_even().max(120.0)
    };
    let gutters: [f64; 4] = std::array::from_fn(|index| {
        if flags & MEASURED_GUTTERS != 0 {
            defaults[index].max(values[13 + index])
        } else {
            defaults[index]
        }
    });
    let output_values = [
        gutters[0],
        gutters[1],
        gutters[2],
        gutters[3],
        extra_top,
        extra_right,
        extra_bottom,
        probe_w,
        probe_h,
    ];
    if output_values
        .iter()
        .any(|v| !v.is_finite() || *v < 0.0 || *v > MAX_DIMENSION)
    {
        return Err(PanelChromeError::Limit);
    }
    let mut out = Vec::with_capacity(88);
    out.extend_from_slice(b"XYPO");
    for value in [1_u32, u32::from(compact), 0] {
        out.extend_from_slice(&value.to_le_bytes());
    }
    for value in output_values {
        out.extend_from_slice(&value.to_le_bytes());
    }
    Ok(out)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn frame(
        x_label: &str,
        y_label: &str,
        x_ticks: &[&str],
        y_ticks: &[&str],
        titles: &[(f64, f64, f64, bool, &str)],
    ) -> Vec<u8> {
        let mut out = vec![0; HEADER_BYTES];
        out[..4].copy_from_slice(b"XYPC");
        for (at, value) in [
            (4, 1_u32),
            (8, Y_LABELS_VISIBLE),
            (12, 2),
            (16, x_ticks.len() as u32),
            (20, y_ticks.len() as u32),
            (24, titles.len() as u32),
            (28, x_label.len() as u32),
            (32, y_label.len() as u32),
        ] {
            out[at..at + 4].copy_from_slice(&value.to_le_bytes());
        }
        for (index, value) in [
            300.0_f64, 600.0, 72.0, 0.0, 11.0, 0.0, 12.0, 11.0, 0.0, 12.0, 0.0, 4.0, 0.0, 0.0, 0.0,
            0.0, 0.0,
        ]
        .iter()
        .enumerate()
        {
            out[64 + index * 8..72 + index * 8].copy_from_slice(&value.to_le_bytes());
        }
        out.extend_from_slice(x_label.as_bytes());
        out.extend_from_slice(y_label.as_bytes());
        for label in x_ticks.iter().chain(y_ticks) {
            out.extend_from_slice(&(label.len() as u32).to_le_bytes());
            out.extend_from_slice(label.as_bytes());
        }
        for &(size, pad, y, automatic, title) in titles {
            for value in [size, pad, y] {
                out.extend_from_slice(&value.to_le_bytes());
            }
            out.extend_from_slice(&u32::from(automatic).to_le_bytes());
            out.extend_from_slice(&(title.len() as u32).to_le_bytes());
            out.extend_from_slice(title.as_bytes());
        }
        out
    }

    fn result(input: &[u8]) -> [f64; 9] {
        let output = resolve_packed(input).unwrap();
        assert_eq!(&output[..4], b"XYPO");
        assert_eq!(output.len(), 88);
        std::array::from_fn(|index| f64_at(&output, 16 + index * 8))
    }

    #[test]
    fn compact_regular_defaults_and_probe_dimensions_are_exact() {
        let mut input = frame("", "", &[], &[], &[]);
        assert_eq!(
            result(&input),
            [46.0, 6.0, 8.0, 36.0, 0.0, 0.0, 0.0, 354.0, 300.0]
        );
        input[64..72].copy_from_slice(&466.0_f64.to_le_bytes());
        assert_eq!(
            result(&input),
            [62.0, 10.0, 14.0, 42.0, 0.0, 0.0, 0.0, 542.0, 300.0]
        );
        input[52..56].copy_from_slice(&1u32.to_le_bytes());
        assert_eq!(result(&input)[..4], [46.0, 6.0, 8.0, 36.0]);
    }

    #[test]
    fn multiline_titles_colorbars_secondary_axes_and_table_reserve_combine() {
        let mut input = frame(
            "first\nsecond",
            "",
            &["alpha\nbeta"],
            &[],
            &[(14.0, 6.0, 1.0, true, "Title")],
        );
        input[8..12].copy_from_slice(&(Y_LABELS_VISIBLE | RIGHT_SECONDARY).to_le_bytes());
        input[44..48].copy_from_slice(&4u32.to_le_bytes());
        input[48..52].copy_from_slice(&3u32.to_le_bytes());
        let values = result(&input);
        assert_eq!(&values[..3], &[46.0, 32.0, 130.0]);
        assert!((values[3] - 50.4).abs() < 1e-12);
        assert_eq!(values[4], 26.0);
        assert_eq!(values[5], 122.0);
        input[80..88].copy_from_slice(&144.0_f64.to_le_bytes());
        input[88..96].copy_from_slice(&80.0_f64.to_le_bytes());
        assert_eq!(result(&input)[3], 160.0);
        input[8..12].copy_from_slice(&(Y_LABELS_VISIBLE | RIGHT_SECONDARY | X_TOP).to_le_bytes());
        assert!((result(&input)[1] - 72.4).abs() < 1e-12);
    }

    #[test]
    fn tick_directions_and_authored_title_offset_preserve_gutter_differences() {
        let mut input = frame(
            "",
            "vertical\nunits",
            &[],
            &["a deliberately long tick label"],
            &[],
        );
        input[144..152].copy_from_slice(&6.0_f64.to_le_bytes());
        let outside = result(&input)[0];
        input[40..44].copy_from_slice(&1u32.to_le_bytes());
        assert_eq!(outside - result(&input)[0], 6.0);
        input[40..44].copy_from_slice(&2u32.to_le_bytes());
        assert_eq!(outside - result(&input)[0], 3.0);
        input[8..12].copy_from_slice(&(Y_LABELS_VISIBLE | AUTHORED_Y_LABEL_OFFSET).to_le_bytes());
        input[160..168].copy_from_slice(&9.8_f64.to_le_bytes());
        assert!((result(&input)[0] - (outside - 3.0) - 5.0).abs() < 1e-12);
        input[8..12].copy_from_slice(&AUTHORED_Y_LABEL_OFFSET.to_le_bytes());
        assert_eq!(result(&input)[0], 46.0);
    }

    #[test]
    fn measured_scene_gutters_are_combined_without_changing_probe_geometry() {
        let mut input = frame("", "", &[], &[], &[]);
        let original = result(&input);
        input[8..12].copy_from_slice(&(Y_LABELS_VISIBLE | MEASURED_GUTTERS).to_le_bytes());
        for (index, value) in [100.0_f64, 60.0, 140.0, 170.0].iter().enumerate() {
            input[168 + index * 8..176 + index * 8].copy_from_slice(&value.to_le_bytes());
        }
        let resolved = result(&input);
        assert_eq!(resolved[..4], [100.0, 60.0, 140.0, 170.0]);
        assert_eq!(resolved[7..], original[7..]);
    }

    #[test]
    fn unsupported_chrome_and_malformed_inputs_fail_closed() {
        let valid = frame("x", "y", &["tick"], &[], &[(14.0, 6.0, 1.0, true, "Title")]);
        for length in 0..valid.len() {
            assert!(resolve_packed(&valid[..length]).is_err());
        }
        let mut extra = valid.clone();
        extra.push(0);
        assert_eq!(resolve_packed(&extra), Err(PanelChromeError::Header));
        for (value, reason) in [
            (1u32, PanelChromeError::BrowserCss),
            (2, PanelChromeError::CustomFont),
        ] {
            let mut input = valid.clone();
            input[36..40].copy_from_slice(&value.to_le_bytes());
            assert_eq!(resolve_packed(&input), Err(reason));
        }
        for offset in [56, 160, 168] {
            let mut input = valid.clone();
            input[offset] = 1;
            assert!(resolve_packed(&input).is_err());
        }
        for offset in (64..200).step_by(8) {
            let mut input = valid.clone();
            input[offset..offset + 8].copy_from_slice(&f64::NAN.to_le_bytes());
            assert_eq!(resolve_packed(&input), Err(PanelChromeError::Facts));
        }
        let mut input = valid.clone();
        *input.last_mut().unwrap() = 0;
        assert_eq!(resolve_packed(&input), Err(PanelChromeError::Text));
        let mut input = valid;
        *input.last_mut().unwrap() = 255;
        assert_eq!(resolve_packed(&input), Err(PanelChromeError::Text));
    }
}
