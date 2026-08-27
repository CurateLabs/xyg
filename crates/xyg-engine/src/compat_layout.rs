//! Compatibility static-export plot layout (M2 #275 / ABI 126).
//!
//! SVG, raster, and pyplot share these padding, title-band, colorbar, right-y,
//! and polar-recut formulas. Hosts still iterate axes, format `_tick_text`,
//! measure rooms through ABI 125, resolve CSS visibility, and decide whether
//! a polar legend gutter is reserved.

use crate::layout_rooms::AXIS_TEXT_EDGE_PAD;

/// Canvas width below which static exporters use compact gutters.
pub const COMPACT_WIDTH: f64 = 520.0;
/// Smallest plot side the combination formulas will emit.
pub const PLOT_MIN: f64 = 40.0;

pub const PAD_TOP_COMPACT: f64 = 6.0;
pub const PAD_RIGHT_COMPACT: f64 = 8.0;
pub const PAD_BOTTOM_COMPACT: f64 = 36.0;
pub const PAD_LEFT_COMPACT: f64 = 46.0;
pub const PAD_TOP: f64 = 10.0;
pub const PAD_RIGHT: f64 = 14.0;
pub const PAD_BOTTOM: f64 = 42.0;
pub const PAD_LEFT: f64 = 62.0;

pub const TITLE_BAND_COMPACT: f64 = 26.0;
pub const TITLE_BAND: f64 = 30.0;
pub const X_TOP_FLOOR_COMPACT: f64 = 26.0;
pub const X_TOP_FLOOR: f64 = 32.0;
pub const X_BOTTOM_FLOOR_COMPACT: f64 = 36.0;
pub const X_BOTTOM_FLOOR: f64 = 42.0;
pub const RIGHT_Y_COMPACT: f64 = 42.0;
pub const RIGHT_Y: f64 = 54.0;

pub const COLORBAR_NONE: u32 = 0;
pub const COLORBAR_AXES_HORIZONTAL: u32 = 1;
pub const COLORBAR_AXES_VERTICAL: u32 = 2;
pub const COLORBAR_FIGURE_HORIZONTAL: u32 = 3;
pub const COLORBAR_FIGURE_VERTICAL: u32 = 4;

pub const LEGEND_SIDE_NONE: u32 = 0;
pub const LEGEND_SIDE_LEFT: u32 = 1;
pub const LEGEND_SIDE_RIGHT: u32 = 2;
pub const LEGEND_SIDE_BOTTOM: u32 = 3;

pub const POLAR_LABEL_ROOM: f64 = 30.0;
pub const POLAR_LABEL_ROOM_MAX: f64 = 90.0;
pub const POLAR_TICK_GAP: f64 = 8.0;
pub const POLAR_LEGEND_ROOM_FRACTION: f64 = 0.22;
pub const POLAR_LEGEND_ROOM_MIN: f64 = 120.0;
pub const POLAR_LEGEND_ROOM_MAX: f64 = 200.0;
pub const POLAR_LEGEND_BAND: f64 = 64.0;

pub const DEFAULT_PADDING_LEN: usize = 4;
pub const RECUT_OUT_LEN: usize = 9;

/// Whether a canvas width uses compact static gutters.
pub fn is_compact(width: f64) -> Option<bool> {
    width.is_finite().then_some(width < COMPACT_WIDTH)
}

/// Default `(top, right, bottom, left)` when the spec did not author padding.
pub fn default_padding(compact: bool) -> [f64; 4] {
    if compact {
        [
            PAD_TOP_COMPACT,
            PAD_RIGHT_COMPACT,
            PAD_BOTTOM_COMPACT,
            PAD_LEFT_COMPACT,
        ]
    } else {
        [PAD_TOP, PAD_RIGHT, PAD_BOTTOM, PAD_LEFT]
    }
}

/// Width a chart title wraps at, from authored/default horizontal gutters.
pub fn title_wrap_width(width: f64, left: f64, right: f64) -> Option<f64> {
    if ![width, left, right].iter().all(|value| value.is_finite()) {
        return None;
    }
    Some(PLOT_MIN.max(width - left - right))
}

/// Outward title-band room for one title entry after the host measured height.
pub fn title_room(
    compact: bool,
    block_height: f64,
    pad: f64,
    automatic_y: bool,
    y: f64,
) -> Option<f64> {
    if ![block_height, pad, y].iter().all(|value| value.is_finite())
        || block_height < 0.0
        || pad < 0.0
    {
        return None;
    }
    let candidate = if automatic_y {
        (if compact {
            TITLE_BAND_COMPACT
        } else {
            TITLE_BAND
        })
        .max(block_height + pad)
    } else if y >= 1.0 {
        block_height + pad
    } else {
        0.0
    };
    Some(candidate.max(0.0))
}

/// Compact floor plus measured x-axis room for one side.
///
/// Returns `(reserved, measured_bottom_contrib)`. `measured_bottom_contrib` is
/// the raw measured room on the bottom side and 0 on the top side.
pub fn x_axis_side_room(compact: bool, top: bool, measured: f64) -> Option<(f64, f64)> {
    if !measured.is_finite() || measured < 0.0 {
        return None;
    }
    if top {
        let floor = if compact {
            X_TOP_FLOOR_COMPACT
        } else {
            X_TOP_FLOOR
        };
        Some((floor.max(measured), 0.0))
    } else {
        let floor = if compact {
            X_BOTTOM_FLOOR_COMPACT
        } else {
            X_BOTTOM_FLOOR
        };
        Some((floor.max(measured), measured))
    }
}

/// Extra `(right, bottom)` claimed by a colorbar after host resolved kind.
pub fn colorbar_extra(kind: u32, has_label: bool, pad_zero: bool) -> Option<(f64, f64)> {
    let label_h = if has_label { 16.0 } else { 0.0 };
    let label_v = if has_label { 18.0 } else { 0.0 };
    match kind {
        COLORBAR_NONE => Some((0.0, 0.0)),
        COLORBAR_AXES_HORIZONTAL => Some((0.0, 24.0 + label_h)),
        COLORBAR_AXES_VERTICAL => Some((44.0 + label_v, 0.0)),
        COLORBAR_FIGURE_HORIZONTAL => Some((0.0, (if pad_zero { 18.0 } else { 38.0 }) + label_h)),
        COLORBAR_FIGURE_VERTICAL => Some(((if pad_zero { 62.0 } else { 86.0 }) + label_v, 0.0)),
        _ => None,
    }
}

/// Shared right-side y-axis gutter.
pub fn right_y_room(compact: bool) -> f64 {
    if compact {
        RIGHT_Y_COMPACT
    } else {
        RIGHT_Y
    }
}

/// Polar legend side-gutter width on a `width`-px canvas.
pub fn polar_legend_room(width: f64) -> Option<f64> {
    if !width.is_finite() || width < 0.0 {
        return None;
    }
    let scaled = (width * POLAR_LEGEND_ROOM_FRACTION).floor();
    Some(POLAR_LEGEND_ROOM_MAX.min(POLAR_LEGEND_ROOM_MIN.max(scaled)))
}

/// Compact charts reserve a bottom band; otherwise loc chooses left vs right.
pub fn polar_legend_reserve(compact: bool, loc_has_left: bool, width: f64) -> Option<(u32, f64)> {
    if compact {
        Some((LEGEND_SIDE_BOTTOM, POLAR_LEGEND_BAND))
    } else {
        let side = if loc_has_left {
            LEGEND_SIDE_LEFT
        } else {
            LEGEND_SIDE_RIGHT
        };
        Some((side, polar_legend_room(width)?))
    }
}

/// Uniform angular-label inset. `widest` is `None` when no authored labels.
pub fn polar_label_room(widest: Option<f64>) -> Option<f64> {
    let Some(widest) = widest else {
        return Some(POLAR_LABEL_ROOM);
    };
    if !widest.is_finite() || widest < 0.0 {
        return None;
    }
    Some(
        POLAR_LABEL_ROOM_MAX
            .min(POLAR_LABEL_ROOM.max(widest + POLAR_TICK_GAP + AXIS_TEXT_EDGE_PAD)),
    )
}

/// Cartesian plot rect plus optional polar legend box after recut.
#[derive(Clone, Debug, PartialEq)]
pub struct PolarPlot {
    pub x: f64,
    pub y: f64,
    pub w: f64,
    pub h: f64,
    pub top_axis_room: f64,
    pub legend_box: Option<[f64; 4]>,
}

/// Re-cut a cartesian plot rect into a polar disc, matching `_svg._recut_polar_plot`.
pub fn recut_polar_plot(
    mut plot: PolarPlot,
    mut width: f64,
    mut height: f64,
    legend_side: u32,
    legend_room: f64,
    polar_label_room: f64,
    authored_padding: bool,
    y_titled: bool,
    keeps_bottom: bool,
) -> Option<PolarPlot> {
    if ![
        plot.x,
        plot.y,
        plot.w,
        plot.h,
        plot.top_axis_room,
        width,
        height,
        legend_room,
        polar_label_room,
    ]
    .iter()
    .all(|value| value.is_finite())
        || width <= 0.0
        || height <= 0.0
        || legend_room < 0.0
        || polar_label_room < 0.0
        || !matches!(
            legend_side,
            LEGEND_SIDE_NONE | LEGEND_SIDE_LEFT | LEGEND_SIDE_RIGHT | LEGEND_SIDE_BOTTOM
        )
    {
        return None;
    }
    let mut canvas_x0 = 0.0;
    if legend_side != LEGEND_SIDE_NONE && legend_room > 0.0 {
        let box_rect = match legend_side {
            LEGEND_SIDE_LEFT => {
                canvas_x0 = legend_room;
                plot.x = plot.x.max(legend_room);
                [0.0, plot.y, legend_room, plot.h]
            }
            LEGEND_SIDE_RIGHT => {
                width -= legend_room;
                [width, plot.y, legend_room, plot.h]
            }
            LEGEND_SIDE_BOTTOM => {
                height -= legend_room;
                [plot.x, height, plot.w, legend_room]
            }
            _ => return None,
        };
        plot.legend_box = Some(box_rect);
        plot.w = PLOT_MIN.max(plot.w.min(width - plot.x));
        plot.h = PLOT_MIN.max(plot.h.min(height - plot.y));
    }
    let reserved_top = plot.y;
    let reserved_right = width - plot.x - plot.w;
    let reserved_bottom = height - plot.y - plot.h;
    let room = polar_label_room;
    if authored_padding {
        let left = plot.x + room;
        let right = plot.x + plot.w - room;
        let top = plot.y + room;
        let bottom = plot.y + plot.h - room;
        let box_w = right - left;
        let box_h = bottom - top;
        if box_w >= PLOT_MIN && box_h >= PLOT_MIN {
            plot.x = left;
            plot.y = top;
            plot.w = box_w;
            plot.h = box_h;
            plot.top_axis_room += room;
        }
        return Some(plot);
    }
    let side = room.max(reserved_right);
    let left = (if y_titled { side.max(plot.x) } else { side }).max(canvas_x0 + room);
    let right = width - side;
    let bottom_reserve = if keeps_bottom {
        reserved_bottom
    } else {
        reserved_bottom.min(reserved_top)
    };
    let bottom = height - room.max(bottom_reserve);
    let top = reserved_top + room;
    let box_w = right - left;
    let box_h = bottom - top;
    if box_w < PLOT_MIN || box_h < PLOT_MIN {
        let margin = 4.0_f64.min(width / 8.0).min(height / 8.0);
        plot.x = margin;
        plot.y = margin.max(reserved_top.min(height / 4.0));
        plot.w = 8.0_f64.max(width - 2.0 * margin);
        plot.h = 8.0_f64.max(height - plot.y - margin);
        return Some(plot);
    }
    plot.x = left;
    plot.y = top;
    plot.w = box_w;
    plot.h = box_h;
    plot.top_axis_room += room;
    if let Some(box_rect) = plot.legend_box.as_mut() {
        if legend_side == LEGEND_SIDE_LEFT || legend_side == LEGEND_SIDE_RIGHT {
            box_rect[1] = plot.y;
            box_rect[3] = plot.h;
        } else if legend_side == LEGEND_SIDE_BOTTOM {
            box_rect[0] = plot.x;
            box_rect[2] = plot.w;
        }
    }
    Some(plot)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn compact_default_padding_matches_static_exporters() {
        assert_eq!(default_padding(true), [6.0, 8.0, 36.0, 46.0]);
        assert_eq!(default_padding(false), [10.0, 14.0, 42.0, 62.0]);
        assert_eq!(is_compact(519.0), Some(true));
        assert_eq!(is_compact(520.0), Some(false));
    }

    #[test]
    fn title_wrap_width_is_a_floor_of_forty() {
        assert_eq!(title_wrap_width(100.0, 40.0, 40.0), Some(40.0));
        assert_eq!(title_wrap_width(200.0, 46.0, 14.0), Some(140.0));
    }

    #[test]
    fn polar_legend_room_clamps_fraction() {
        assert_eq!(polar_legend_room(400.0), Some(120.0));
        assert_eq!(polar_legend_room(1000.0), Some(200.0));
        let mid = polar_legend_room(700.0).unwrap();
        assert!((mid - (700.0 * POLAR_LEGEND_ROOM_FRACTION).floor()).abs() < 1e-12);
    }

    #[test]
    fn recut_authored_padding_insets_by_label_room() {
        let plot = PolarPlot {
            x: 0.0,
            y: 0.0,
            w: 200.0,
            h: 200.0,
            top_axis_room: 10.0,
            legend_box: None,
        };
        let out = recut_polar_plot(
            plot,
            200.0,
            200.0,
            LEGEND_SIDE_NONE,
            0.0,
            30.0,
            true,
            false,
            false,
        )
        .unwrap();
        assert_eq!(out.x, 30.0);
        assert_eq!(out.y, 30.0);
        assert_eq!(out.w, 140.0);
        assert_eq!(out.h, 140.0);
        assert_eq!(out.top_axis_room, 40.0);
    }
}
