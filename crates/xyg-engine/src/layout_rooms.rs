//! Measured Cartesian axis gutters (M2 #275 / ABI 125).
//!
//! Hosts still format `_tick_text`, resolve CSS visibility / tick offsets,
//! and iterate axes. Column combination of title + tick ink + edge overhang
//! lives here so SVG, raster, and pyplot cannot drift from `_svg._*room`.

use crate::textblock::{self, LINE_HEIGHT};

/// Smallest gap between the canvas edge and the outermost axis ink.
pub const AXIS_TEXT_EDGE_PAD: f64 = 4.0;
/// Gap between the y title's ink and the nearest tick label, as a fraction
/// of the title font size.
pub const Y_TITLE_TICK_GAP: f64 = 0.4;

pub const ANCHOR_START: u32 = 0;
pub const ANCHOR_CENTER: u32 = 1;
pub const ANCHOR_END: u32 = 2;

/// Widest rotated x-extent of y tick labels.
pub fn y_tick_label_extent(labels: &[&str], font_size: f64, angle: f64) -> Option<f64> {
    if !font_size.is_finite() || font_size < 0.0 || !angle.is_finite() {
        return None;
    }
    let mut room: f64 = 0.0;
    for label in labels {
        let block = textblock::measure(label, font_size, LINE_HEIGHT, None)?;
        let (extent, _) = textblock::rotated_extent(block.width, block.height, angle)?;
        room = room.max(extent);
    }
    Some(room)
}

/// Left gutter needed by one y axis after the host has resolved tick ink.
///
/// `title` is `None` when the outside title is absent or invisible. A zero
/// tick pair with no title returns 0 so a host `max` loop can skip it.
pub fn y_axis_left_room(
    tick_offset: f64,
    tick_room: f64,
    title: Option<&str>,
    title_font_size: f64,
    title_gap: f64,
) -> Option<f64> {
    if ![tick_offset, tick_room, title_font_size, title_gap]
        .iter()
        .all(|value| value.is_finite())
        || tick_offset < 0.0
        || tick_room < 0.0
        || title_font_size < 0.0
        || title_gap < 0.0
    {
        return None;
    }
    let Some(title) = title.filter(|text| !text.is_empty()) else {
        if tick_offset == 0.0 && tick_room == 0.0 {
            return Some(0.0);
        }
        return Some(AXIS_TEXT_EDGE_PAD + tick_offset + tick_room);
    };
    let block = textblock::measure(title, title_font_size, LINE_HEIGHT, None)?;
    Some(
        AXIS_TEXT_EDGE_PAD
            + block.ascent
            + block.descent
            + (block.line_count().saturating_sub(1) as f64) * block.line_step
            + title_gap
            + tick_offset
            + tick_room,
    )
}

/// Outward room needed by an outside x-axis title. `top` is true for `side="top"`.
pub fn x_axis_title_room(
    title: Option<&str>,
    font_size: f64,
    offset: f64,
    top: bool,
) -> Option<f64> {
    if !font_size.is_finite() || font_size < 0.0 || !offset.is_finite() {
        return None;
    }
    let Some(title) = title.filter(|text| !text.is_empty()) else {
        return Some(0.0);
    };
    let block = textblock::measure(title, font_size, LINE_HEIGHT, None)?;
    if top {
        Some(AXIS_TEXT_EDGE_PAD + 34.0 + offset - font_size * 0.82 + block.ascent)
    } else {
        Some(
            AXIS_TEXT_EDGE_PAD
                + 24.0
                + offset
                + font_size * 0.82
                + (block.line_count().saturating_sub(1) as f64) * block.line_step
                + block.descent,
        )
    }
}

/// Measured x tick-label band after collision layout. `title_room` is the
/// independently measured title; `label_offset` is the host-resolved spine gap.
pub fn x_tick_label_room(
    labels: &[&str],
    angles: &[f64],
    rows: &[u32],
    font_size: f64,
    label_offset: f64,
    title_room: f64,
) -> Option<f64> {
    if labels.len() != angles.len() || labels.len() != rows.len() {
        return None;
    }
    if ![font_size, label_offset, title_room]
        .iter()
        .all(|value| value.is_finite())
        || font_size < 0.0
        || label_offset < 0.0
        || title_room < 0.0
        || angles.iter().any(|angle| !angle.is_finite())
    {
        return None;
    }
    if labels.is_empty() {
        return Some(title_room);
    }
    let mut extent: f64 = 0.0;
    let mut max_row = 0u32;
    for ((label, angle), row) in labels.iter().zip(angles.iter()).zip(rows.iter()) {
        let block = textblock::measure(label, font_size, LINE_HEIGHT, None)?;
        let (_, height) = textblock::rotated_extent(block.width, block.height, *angle)?;
        extent = extent.max(height);
        max_row = max_row.max(*row);
    }
    let tick_room =
        AXIS_TEXT_EDGE_PAD + label_offset + f64::from(max_row) * (font_size + 4.0) + extent;
    Some(title_room.max(tick_room))
}

/// Canvas-edge overhang from one axis's laid-out x tick labels.
pub fn x_tick_label_edge_rooms(
    plot_w: f64,
    positions: &[f64],
    labels: &[&str],
    angles: &[f64],
    anchors: &[u32],
    font_size: f64,
) -> Option<(f64, f64)> {
    let n = positions.len();
    if n != labels.len() || n != angles.len() || n != anchors.len() {
        return None;
    }
    if !plot_w.is_finite()
        || plot_w <= 0.0
        || !font_size.is_finite()
        || font_size < 0.0
        || positions.iter().any(|pos| !pos.is_finite())
        || angles.iter().any(|angle| !angle.is_finite())
        || anchors
            .iter()
            .any(|anchor| !matches!(*anchor, ANCHOR_START | ANCHOR_CENTER | ANCHOR_END))
    {
        return None;
    }
    let mut left: f64 = 0.0;
    let mut right: f64 = 0.0;
    for i in 0..n {
        let block = textblock::measure(labels[i], font_size, LINE_HEIGHT, None)?;
        let (x0, x1) = match anchors[i] {
            ANCHOR_END => (-block.width, 0.0),
            ANCHOR_CENTER => (-block.width / 2.0, block.width / 2.0),
            _ => (0.0, block.width),
        };
        let y0 = -block.ascent;
        let y1 = block.descent + (block.line_count().saturating_sub(1) as f64) * block.line_step;
        let radians = angles[i].to_radians();
        let cosine = radians.cos();
        let sine = radians.sin();
        let mut min_x = f64::INFINITY;
        let mut max_x = f64::NEG_INFINITY;
        for x in [x0, x1] {
            for y in [y0, y1] {
                let rotated = x * cosine - y * sine;
                min_x = min_x.min(rotated);
                max_x = max_x.max(rotated);
            }
        }
        let position = positions[i];
        left = left.max(AXIS_TEXT_EDGE_PAD - position - min_x);
        right = right.max(AXIS_TEXT_EDGE_PAD + position + max_x - plot_w);
    }
    Some((left.max(0.0).ceil(), right.max(0.0).ceil()))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn titled_y_axis_adds_ascent_descent_and_tick_ink() {
        let font = 12.0;
        let room = y_axis_left_room(7.0, 23.0, Some("Y"), font, Y_TITLE_TICK_GAP * font).unwrap();
        let block = textblock::measure("Y", font, LINE_HEIGHT, None).unwrap();
        let expected = AXIS_TEXT_EDGE_PAD
            + block.ascent
            + block.descent
            + Y_TITLE_TICK_GAP * font
            + 7.0
            + 23.0;
        assert!((room - expected).abs() < 1e-12);
    }

    #[test]
    fn empty_title_and_zero_ticks_reserve_nothing() {
        assert_eq!(y_axis_left_room(0.0, 0.0, None, 12.0, 0.0), Some(0.0));
    }

    #[test]
    fn bottom_title_includes_baseline_conversion() {
        let room = x_axis_title_room(Some("X"), 12.0, 0.0, false).unwrap();
        assert!(room > 24.0);
    }
}
