//! Tick-label collision layout and authored tick-window policy (M2 #276).
//!
//! Collision thinning (ABI 123) owns auto / hide / rotate / stagger so SVG,
//! raster, and Node cannot drift from ChartView `_layoutTickLabels`. Authored
//! tick-window resolve/filter (ABI 128) owns linear vs modular angular
//! containment so seam-crossing polar sectors keep the same spokes as marks.
//! ABI 199 Scene product encode filters authored cartesian majors through
//! that window and pairs `tick_labels` during chrome pack. ABI 200 filters
//! authored cartesian minors (`require_finite`). ABI 201 filters polar theta
//! majors/minors through the modular sector window and formats Scene polar
//! theta labels with `format_angular_tick`. ABI 202 materializes ABI 130
//! time/angular formats onto Scene `XYTL` during product encode. ABI 203
//! runs ABI 123 collision at Scene SVG/raster emit for cartesian
//! `tick_label_strategy` and aliases `collision`; polar rim auto/hide/
//! rotate/stagger/preserve stay fail-closed. Secondary axes stay fail-closed.
//! Tick-label formatting (ABI 130) owns Cartesian linear/log/time/number-spec
//! and angular/category defaults via `xyg_tick_format`. Hosts still map values
//! to pixels on the compatibility `_svg` path; Scene product-path authored
//! `tick_labels` pair during chrome pack.

use crate::scene::scene_text_advance;

/// CSS line-box height used by `_textblock.measure` / ChartView.
pub const LINE_HEIGHT: f64 = 1.2;
/// Floor on measured label width (`max(font_size * 0.7, advance)`).
pub const MIN_LABEL_WIDTH_EM: f64 = 0.7;
/// `auto` on a categorical x axis rotates when `n <= 16`.
pub const AUTO_CATEGORY_ROTATE_MAX: usize = 16;
/// `auto` on any x axis staggers when `n <= 24`.
pub const AUTO_STAGGER_MAX: usize = 24;
/// Default rotation when strategy is rotate and no explicit angle is set.
pub const DEFAULT_ROTATE_DEG: f64 = 35.0;

pub const STRATEGY_AUTO: u32 = 0;
pub const STRATEGY_HIDE: u32 = 1;
pub const STRATEGY_ROTATE: u32 = 2;
pub const STRATEGY_STAGGER: u32 = 3;
pub const STRATEGY_PRESERVE: u32 = 4;
pub const STRATEGY_NONE: u32 = 5;
pub const STRATEGY_OFF: u32 = 6;

pub const SIDE_BOTTOM: u32 = 0;
pub const SIDE_TOP: u32 = 1;
pub const SIDE_LEFT: u32 = 2;
pub const SIDE_RIGHT: u32 = 3;

pub const ANCHOR_START: u32 = 0;
pub const ANCHOR_CENTER: u32 = 1;
pub const ANCHOR_END: u32 = 2;

pub const FLAG_IS_X: u32 = 1;
pub const FLAG_CATEGORY: u32 = 2;

/// One kept tick after collision thinning.
#[derive(Clone, Debug, PartialEq)]
pub struct TickLabelItem {
    pub index: u32,
    pub angle: f64,
    pub row: u32,
}

#[derive(Clone, Copy)]
struct Candidate {
    index: usize,
    pos: f64,
    angle: f64,
    row: u32,
}

fn label_size(text: &str, font_size: f64) -> (f64, f64) {
    let normalized = text.replace("\r\n", "\n").replace('\r', "\n");
    let lines: Vec<&str> = normalized.split('\n').collect();
    let mut width: f64 = 0.0;
    for line in &lines {
        width = width.max(scene_text_advance(line, font_size));
    }
    width = width.max(font_size * MIN_LABEL_WIDTH_EM);
    let line_step = font_size * LINE_HEIGHT;
    let height = (lines.len() as f64 * line_step).max(line_step);
    (width, height)
}

fn extent(text: &str, angle_deg: f64, is_x: bool, font_size: f64) -> f64 {
    let (width, height) = label_size(text, font_size);
    let angle = angle_deg.abs() * std::f64::consts::PI / 180.0;
    if is_x {
        angle.cos().abs() * width + angle.sin().abs() * height
    } else {
        angle.sin().abs() * width + angle.cos().abs() * height
    }
}

fn collide(
    items: &[Candidate],
    texts: &[&str],
    is_x: bool,
    anchor: u32,
    font_size: f64,
    min_gap: f64,
) -> bool {
    let mut rows: Vec<Vec<Candidate>> = Vec::new();
    for item in items {
        let row = item.row as usize;
        if row >= rows.len() {
            rows.resize(row + 1, Vec::new());
        }
        rows[row].push(*item);
    }
    for row in &mut rows {
        if row.is_empty() {
            continue;
        }
        row.sort_by(|a, b| a.pos.total_cmp(&b.pos));
        if is_x && anchor != ANCHOR_CENTER {
            for pair in row.windows(2) {
                let prev = pair[0];
                let curr = pair[1];
                let spacing = curr.pos - prev.pos;
                let angle = curr.angle.abs() * std::f64::consts::PI / 180.0;
                if angle != 0.0 {
                    if spacing * angle.sin() < font_size * LINE_HEIGHT + min_gap {
                        return true;
                    }
                } else {
                    let lead = if anchor == ANCHOR_END { curr } else { prev };
                    let (width, _) = label_size(texts[lead.index], font_size);
                    if spacing < width + min_gap {
                        return true;
                    }
                }
            }
        } else {
            let mut last_end = f64::NEG_INFINITY;
            for item in row.iter() {
                let half = extent(texts[item.index], item.angle, is_x, font_size) / 2.0;
                let start = item.pos - half;
                if start < last_end + min_gap {
                    return true;
                }
                last_end = item.pos + half;
            }
        }
    }
    false
}

fn to_items(candidates: &[Candidate]) -> Vec<TickLabelItem> {
    candidates
        .iter()
        .map(|item| TickLabelItem {
            index: item.index as u32,
            angle: item.angle,
            row: item.row,
        })
        .collect()
}

/// Collision-thin tick labels. `explicit_angle` is `None` when unset.
pub fn tick_label_layout(
    positions: &[f64],
    labels: &[&str],
    strategy: u32,
    side: u32,
    anchor: u32,
    is_x: bool,
    category: bool,
    font_size: f64,
    min_gap: f64,
    explicit_angle: Option<f64>,
) -> Option<Vec<TickLabelItem>> {
    if positions.len() != labels.len() {
        return None;
    }
    if !matches!(strategy, STRATEGY_AUTO..=STRATEGY_OFF)
        || !matches!(side, SIDE_BOTTOM..=SIDE_RIGHT)
        || !matches!(anchor, ANCHOR_START..=ANCHOR_END)
    {
        return None;
    }
    if !font_size.is_finite() || font_size < 0.0 || !min_gap.is_finite() {
        return None;
    }
    if let Some(angle) = explicit_angle {
        if !angle.is_finite() {
            return None;
        }
    }
    if positions.iter().any(|pos| !pos.is_finite()) {
        return None;
    }
    if strategy == STRATEGY_NONE || strategy == STRATEGY_OFF {
        return Some(Vec::new());
    }
    let n = positions.len();
    let base_angle = explicit_angle.unwrap_or(0.0);
    let mut items: Vec<Candidate> = (0..n)
        .map(|index| Candidate {
            index,
            pos: positions[index],
            angle: base_angle,
            row: 0,
        })
        .collect();
    if n <= 1 {
        return Some(to_items(&items));
    }
    if strategy == STRATEGY_PRESERVE {
        return Some(to_items(&items));
    }

    let mut resolved = strategy;
    if resolved == STRATEGY_AUTO {
        if !collide(&items, labels, is_x, anchor, font_size, min_gap) {
            return Some(to_items(&items));
        }
        resolved = if is_x && category && n <= AUTO_CATEGORY_ROTATE_MAX {
            STRATEGY_ROTATE
        } else if is_x && n <= AUTO_STAGGER_MAX {
            STRATEGY_STAGGER
        } else {
            STRATEGY_HIDE
        };
    }

    if resolved == STRATEGY_ROTATE && is_x {
        let angle = explicit_angle.unwrap_or(if side == SIDE_TOP {
            DEFAULT_ROTATE_DEG
        } else {
            -DEFAULT_ROTATE_DEG
        });
        for item in &mut items {
            item.angle = angle;
            item.row = 0;
        }
    } else if resolved == STRATEGY_STAGGER && is_x {
        for (index, item) in items.iter_mut().enumerate() {
            item.row = (index % 2) as u32;
        }
    }

    if collide(&items, labels, is_x, anchor, font_size, min_gap) {
        for stride in 2..=n {
            let reduced: Vec<Candidate> = items.iter().step_by(stride).copied().collect();
            if !collide(&reduced, labels, is_x, anchor, font_size, min_gap) {
                return Some(to_items(&reduced));
            }
        }
        return Some(to_items(&items[..1]));
    }
    Some(to_items(&items))
}

pub const THETA_NONE: u32 = 0;
pub const THETA_DEGREES: u32 = 1;
pub const THETA_RADIANS: u32 = 2;
pub const KIND_LINEAR: u32 = 0;
pub const KIND_CATEGORY: u32 = 1;

/// Resolve the value window ticks are drawn in.
///
/// `sector_lo`/`sector_hi` are NaN when the axis did not author a sector.
pub fn tick_window(
    range_lo: f64,
    range_hi: f64,
    theta_unit: u32,
    kind: u32,
    n_categories: u32,
    sector_lo: f64,
    sector_hi: f64,
) -> Option<(f64, f64)> {
    if !matches!(theta_unit, THETA_NONE | THETA_DEGREES | THETA_RADIANS)
        || !matches!(kind, KIND_LINEAR | KIND_CATEGORY)
        || !range_lo.is_finite()
        || !range_hi.is_finite()
    {
        return None;
    }
    if theta_unit == THETA_NONE {
        return Some((range_lo, range_hi));
    }
    if kind == KIND_CATEGORY {
        return Some((0.0, f64::from(n_categories.saturating_sub(1))));
    }
    if sector_lo.is_nan() && sector_hi.is_nan() {
        return Some((range_lo, range_hi));
    }
    if sector_lo.is_finite() && sector_hi.is_finite() {
        return Some((sector_lo, sector_hi));
    }
    None
}

/// Whether `value` falls inside the tick window, matching `_svg._tick_window_filter`.
pub fn tick_in_window(value: f64, lo: f64, hi: f64, theta_unit: u32, kind: u32) -> Option<bool> {
    if !lo.is_finite()
        || !hi.is_finite()
        || !matches!(theta_unit, THETA_NONE | THETA_DEGREES | THETA_RADIANS)
        || !matches!(kind, KIND_LINEAR | KIND_CATEGORY)
    {
        return None;
    }
    let low = lo.min(hi);
    let high = lo.max(hi);
    if theta_unit == THETA_NONE || kind == KIND_CATEGORY {
        return Some(value >= low && value <= high);
    }
    let turn = if theta_unit == THETA_DEGREES {
        360.0
    } else {
        2.0 * std::f64::consts::PI
    };
    let span = high - low;
    Some((value - low).rem_euclid(turn) <= span + turn * 1e-9)
}

/// Compact `values` that fall inside the window into `out`.
pub fn filter_tick_values(
    values: &[f64],
    lo: f64,
    hi: f64,
    theta_unit: u32,
    kind: u32,
    require_finite: bool,
    out: &mut [f64],
) -> Option<usize> {
    if out.len() < values.len() {
        return None;
    }
    let mut written = 0;
    for &value in values {
        if require_finite && !value.is_finite() {
            continue;
        }
        if tick_in_window(value, lo, hi, theta_unit, kind)? {
            out[written] = value;
            written += 1;
        }
    }
    Some(written)
}

/// Indices of authored tick values that fall inside the window.
pub fn filter_tick_indices(
    values: &[f64],
    lo: f64,
    hi: f64,
    theta_unit: u32,
    kind: u32,
    require_finite: bool,
) -> Option<Vec<usize>> {
    let mut indices = Vec::with_capacity(values.len());
    for (index, &value) in values.iter().enumerate() {
        if require_finite && !value.is_finite() {
            continue;
        }
        if tick_in_window(value, lo, hi, theta_unit, kind)? {
            indices.push(index);
        }
    }
    Some(indices)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn labels<'a>(texts: &'a [&'a str]) -> Vec<&'a str> {
        texts.to_vec()
    }

    #[test]
    fn none_and_off_drop_every_label() {
        let pos = [0.0, 10.0];
        let texts = labels(&["a", "b"]);
        assert!(tick_label_layout(
            &pos,
            &texts,
            STRATEGY_NONE,
            SIDE_BOTTOM,
            ANCHOR_CENTER,
            true,
            false,
            11.0,
            8.0,
            None,
        )
        .unwrap()
        .is_empty());
        assert!(tick_label_layout(
            &pos,
            &texts,
            STRATEGY_OFF,
            SIDE_BOTTOM,
            ANCHOR_CENTER,
            true,
            false,
            11.0,
            8.0,
            None,
        )
        .unwrap()
        .is_empty());
    }

    #[test]
    fn preserve_keeps_colliding_labels() {
        let pos: Vec<f64> = (0..9).map(|i| 100.0 + i as f64 * 10.0).collect();
        let owned: Vec<String> = (0..9).map(|i| format!("Category_Name_{i:02}")).collect();
        let texts: Vec<&str> = owned.iter().map(String::as_str).collect();
        let kept = tick_label_layout(
            &pos,
            &texts,
            STRATEGY_PRESERVE,
            SIDE_BOTTOM,
            ANCHOR_CENTER,
            true,
            true,
            11.0,
            8.0,
            Some(-30.0),
        )
        .unwrap();
        assert_eq!(kept.len(), 9);
    }

    #[test]
    fn end_anchor_rotate_keeps_wide_categorical_labels() {
        let pos: Vec<f64> = (0..9).map(|i| 100.0 + i as f64 * 90.0).collect();
        let owned: Vec<String> = (0..9).map(|i| format!("Category_Name_{i:02}")).collect();
        let texts: Vec<&str> = owned.iter().map(String::as_str).collect();
        let kept = tick_label_layout(
            &pos,
            &texts,
            STRATEGY_ROTATE,
            SIDE_BOTTOM,
            ANCHOR_END,
            true,
            true,
            11.0,
            8.0,
            Some(-30.0),
        )
        .unwrap();
        assert_eq!(kept.len(), 9);
    }

    #[test]
    fn centered_rotate_downsamples_the_same_geometry() {
        let pos: Vec<f64> = (0..9).map(|i| 100.0 + i as f64 * 90.0).collect();
        let owned: Vec<String> = (0..9).map(|i| format!("Category_Name_{i:02}")).collect();
        let texts: Vec<&str> = owned.iter().map(String::as_str).collect();
        let kept = tick_label_layout(
            &pos,
            &texts,
            STRATEGY_ROTATE,
            SIDE_BOTTOM,
            ANCHOR_CENTER,
            true,
            true,
            11.0,
            8.0,
            Some(-30.0),
        )
        .unwrap();
        assert!(kept.len() < 9);
        assert!(!kept.is_empty());
    }

    #[test]
    fn seam_crossing_degree_sector_keeps_far_side_ticks() {
        let values = [300.0, 330.0, 0.0, 30.0, 60.0, 200.0];
        let mut out = [0.0; 6];
        let n = filter_tick_values(
            &values,
            300.0,
            420.0,
            THETA_DEGREES,
            KIND_LINEAR,
            false,
            &mut out,
        )
        .unwrap();
        assert_eq!(&out[..n], &[300.0, 330.0, 0.0, 30.0, 60.0]);
    }

    #[test]
    fn linear_window_rejects_outside_and_nan() {
        let values = [0.0, 45.0, 90.0, 200.0, -10.0, f64::NAN];
        let mut out = [0.0; 6];
        let n = filter_tick_values(
            &values,
            0.0,
            180.0,
            THETA_NONE,
            KIND_LINEAR,
            false,
            &mut out,
        )
        .unwrap();
        assert_eq!(&out[..n], &[0.0, 45.0, 90.0]);
        let (lo, hi) = tick_window(
            1.0,
            2.0,
            THETA_DEGREES,
            KIND_CATEGORY,
            4,
            f64::NAN,
            f64::NAN,
        )
        .unwrap();
        assert_eq!((lo, hi), (0.0, 3.0));
    }
}
