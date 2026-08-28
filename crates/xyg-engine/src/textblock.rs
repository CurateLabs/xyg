//! Newline-delimited chrome measurement (M2 #275 / ABI 125).
//!
//! Axis titles and tick labels are text blocks, not strings. SVG, raster, and
//! pyplot reserve the same DejaVu footprint through this module so a wrapped
//! title cannot be clipped while layout reserved one line.

use crate::scene::scene_text_advance;

/// CSS `line-height` used for chrome blocks (`_textblock.LINE_HEIGHT`).
pub const LINE_HEIGHT: f64 = 1.2;
/// Embedded DejaVu metrics at [`BASE_PX`].
pub const BASE_PX: f64 = 16.0;
pub const ASCENT: f64 = 15.0;
pub const DESCENT: f64 = 4.0;

pub const METRICS_LEN: usize = 6;
pub const METRIC_WIDTH: usize = 0;
pub const METRIC_HEIGHT: usize = 1;
pub const METRIC_LINE_STEP: usize = 2;
pub const METRIC_ASCENT: usize = 3;
pub const METRIC_DESCENT: usize = 4;
pub const METRIC_LINE_COUNT: usize = 5;

/// Measured newline-delimited block in the embedded face.
#[derive(Clone, Debug, PartialEq)]
pub struct TextBlock {
    pub lines: Vec<String>,
    pub width: f64,
    pub height: f64,
    pub line_step: f64,
    pub ascent: f64,
    pub descent: f64,
}

impl TextBlock {
    pub fn line_count(&self) -> usize {
        self.lines.len()
    }

    pub fn metrics(&self) -> [f64; METRICS_LEN] {
        let mut out = [0.0; METRICS_LEN];
        out[METRIC_WIDTH] = self.width;
        out[METRIC_HEIGHT] = self.height;
        out[METRIC_LINE_STEP] = self.line_step;
        out[METRIC_ASCENT] = self.ascent;
        out[METRIC_DESCENT] = self.descent;
        out[METRIC_LINE_COUNT] = self.line_count() as f64;
        out
    }
}

/// Normalize CR/LF then split, preserving authored empty lines.
pub fn split_lines(text: &str) -> Vec<String> {
    let normalized = text.replace("\r\n", "\n").replace('\r', "\n");
    if normalized.is_empty() {
        return vec![String::new()];
    }
    normalized.split('\n').map(str::to_string).collect()
}

/// Greedy word wrap of already newline-split lines, at `max_width` px.
///
/// Authored newlines are hard breaks. Other whitespace collapses to one
/// space. A single word wider than `max_width` keeps its own line.
pub fn wrap_lines(lines: &[String], font_size: f64, max_width: f64) -> Option<Vec<String>> {
    if !font_size.is_finite() || font_size < 0.0 || !max_width.is_finite() {
        return None;
    }
    let size = font_size.max(0.0);
    let mut wrapped = Vec::new();
    for line in lines {
        let words: Vec<&str> = line.split_whitespace().collect();
        if words.is_empty() {
            wrapped.push(String::new());
            continue;
        }
        let mut current = words[0].to_string();
        for word in &words[1..] {
            let candidate = format!("{current} {word}");
            if scene_text_advance(&candidate, size) <= max_width {
                current = candidate;
            } else {
                wrapped.push(current);
                current = (*word).to_string();
            }
        }
        wrapped.push(current);
    }
    Some(wrapped)
}

/// Measure a newline-delimited block. `max_width` is `None` when wrapping is off.
pub fn measure(
    text: &str,
    font_size: f64,
    line_height: f64,
    max_width: Option<f64>,
) -> Option<TextBlock> {
    if !font_size.is_finite() || font_size < 0.0 || !line_height.is_finite() {
        return None;
    }
    let size = font_size.max(0.0);
    let mut lines = split_lines(text);
    if let Some(limit) = max_width {
        if limit.is_finite() && limit > 0.0 {
            lines = wrap_lines(&lines, size, limit)?;
        }
    }
    let line_step = size * line_height;
    let ascent = size * ASCENT / BASE_PX;
    let descent = size * DESCENT / BASE_PX;
    let width = lines
        .iter()
        .map(|line| scene_text_advance(line, size))
        .fold(0.0, f64::max);
    let height = line_step.max(lines.len() as f64 * line_step);
    Some(TextBlock {
        lines,
        width,
        height,
        line_step,
        ascent,
        descent,
    })
}

/// Axis-aligned `(width, height)` after rotating `block`.
pub fn rotated_extent(width: f64, height: f64, angle_degrees: f64) -> Option<(f64, f64)> {
    if ![width, height, angle_degrees]
        .iter()
        .all(|value| value.is_finite())
    {
        return None;
    }
    let angle = angle_degrees.abs() * std::f64::consts::PI / 180.0;
    let cosine = angle.cos().abs();
    let sine = angle.sin().abs();
    Some((
        cosine * width + sine * height,
        sine * width + cosine * height,
    ))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn crlf_normalizes_to_the_same_lines_as_lf() {
        let a = measure("first\r\nsecond", 12.0, LINE_HEIGHT, None).unwrap();
        let b = measure("first\nsecond", 12.0, LINE_HEIGHT, None).unwrap();
        assert_eq!(a.lines, b.lines);
        assert_eq!(a.line_count(), 2);
    }

    #[test]
    fn wrap_keeps_an_unbreakable_word() {
        let lines = wrap_lines(
            &[String::from("unbreakablesupercalifragilistic")],
            14.0,
            10.0,
        )
        .unwrap();
        assert_eq!(lines, vec![String::from("unbreakablesupercalifragilistic")]);
    }

    #[test]
    fn rotated_extent_swaps_at_ninety_degrees() {
        let (w, h) = rotated_extent(10.0, 4.0, 90.0).unwrap();
        assert!((w - 4.0).abs() < 1e-12);
        assert!((h - 10.0).abs() < 1e-12);
    }
}
