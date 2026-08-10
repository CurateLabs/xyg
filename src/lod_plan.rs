//! View-dependent LOD decision math (§5/§28).
//!
//! Hosts validate and assemble string mode names; this module owns the
//! exact-vs-aggregate hysteresis decision and the screen-bounded aggregation
//! grid so Python and Node stay bit-identical
//! ([host-parity.md](../../spec/design/host-parity.md)).

/// Cap matching `python/xy/config.py` `MAX_SCREEN_DIM`.
pub const MAX_SCREEN_DIM: i32 = 4096;
/// Floor matching `lod.screen_shape` — avoids zero-size aggregate grids.
pub const MIN_SCREEN_DIM: i32 = 16;
/// Default points-per-cell target (`DENSITY_TARGET_POINTS_PER_CELL`).
pub const DEFAULT_TARGET_PER_CELL: f64 = 16.0;
/// Default drill-exit hysteresis (`DRILL_EXIT_FACTOR`).
pub const DEFAULT_EXIT_FACTOR: f64 = 1.15;

/// Wire/tier mode: ship direct marks (points, candles, …).
pub const MODE_DIRECT: u32 = 0;
/// Wire/tier mode: ship an aggregate (density, buckets, …).
pub const MODE_AGGREGATE: u32 = 1;

/// Chart-agnostic tier decision for a viewport (numeric half of `LodPlan`).
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct LodPlan {
    pub exact: bool,
    pub mode: u32,
    pub grid_w: i32,
    pub grid_h: i32,
}

/// Clamp a browser/client screen shape to `[MIN_SCREEN_DIM, MAX_SCREEN_DIM]`.
///
/// Matches `lod.screen_shape`: non-positive dimensions floor to the minimum
/// rather than erroring (host validation already rejected non-finite inputs).
pub fn screen_shape(w: i32, h: i32) -> (i32, i32) {
    (
        w.clamp(MIN_SCREEN_DIM, MAX_SCREEN_DIM),
        h.clamp(MIN_SCREEN_DIM, MAX_SCREEN_DIM),
    )
}

/// Hysteresis-guarded drill decision: stay in exact marks until the visible
/// count clearly exceeds the budget again (§5).
pub fn drill_decision(visible: u64, budget: f64, in_drill: bool, exit_factor: f64) -> Option<bool> {
    if !budget.is_finite() || budget <= 0.0 {
        return None;
    }
    if !exit_factor.is_finite() || exit_factor <= 0.0 {
        return None;
    }
    let factor = if in_drill { exit_factor } else { 1.0 };
    let threshold = budget * factor;
    if !threshold.is_finite() {
        return None;
    }
    // Compare in f64; visible fits exactly in f64 up to 2^53.
    Some((visible as f64) <= threshold)
}

/// Keep aggregation grids screen-bounded, but avoid one-pixel bins when the
/// visible count is only barely over the direct budget.
pub fn grid_shape(w: i32, h: i32, visible: u64, target_per_cell: f64) -> Option<(i32, i32)> {
    if !target_per_cell.is_finite() || target_per_cell <= 0.0 {
        return None;
    }
    let (w, h) = screen_shape(w, h);
    let requested = (w as i64).checked_mul(h as i64)?;
    if visible == 0 {
        return Some((w, h));
    }
    let ceil_cells = ((visible as f64) / target_per_cell).ceil();
    if !ceil_cells.is_finite() || ceil_cells < 0.0 {
        return None;
    }
    let cells = ceil_cells as i64;
    let floor = (MIN_SCREEN_DIM as i64) * (MIN_SCREEN_DIM as i64);
    let target = requested.min(cells.max(floor));
    if target >= requested {
        return Some((w, h));
    }
    let scale = (target as f64 / requested as f64).sqrt();
    if !scale.is_finite() {
        return None;
    }
    // Python uses `int(round(...))` — banker's rounding at .5. Match with
    // `round_ties_even` so dual-host grids stay identical.
    let gw = ((w as f64) * scale).round_ties_even() as i32;
    let gh = ((h as f64) * scale).round_ties_even() as i32;
    Some((gw.max(MIN_SCREEN_DIM), gh.max(MIN_SCREEN_DIM)))
}

/// Build the reusable numeric tier decision for a viewport.
pub fn plan(
    visible: u64,
    budget: f64,
    in_drill: bool,
    exit_factor: f64,
    px_w: i32,
    px_h: i32,
    target_per_cell: f64,
) -> Option<LodPlan> {
    let exact = drill_decision(visible, budget, in_drill, exit_factor)?;
    let (grid_w, grid_h) = grid_shape(px_w, px_h, visible, target_per_cell)?;
    Some(LodPlan {
        exact,
        mode: if exact {
            MODE_DIRECT
        } else {
            MODE_AGGREGATE
        },
        grid_w,
        grid_h,
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn drill_hysteresis_matches_python_fixtures() {
        assert_eq!(drill_decision(100_000, 200_000.0, false, 1.15), Some(true));
        assert_eq!(drill_decision(350_000, 200_000.0, false, 1.15), Some(false));
        // 225k <= 200k * 1.15 = 230k while drilled → stay exact
        assert_eq!(drill_decision(225_000, 200_000.0, true, 1.15), Some(true));
        // 240k > 230k → exit drill
        assert_eq!(drill_decision(240_000, 200_000.0, true, 1.15), Some(false));
    }

    #[test]
    fn grid_shape_shrinks_when_visible_is_modest() {
        let (gw, gh) = grid_shape(1200, 800, 350_000, 16.0).unwrap();
        assert!(gw < 1200 && gh < 800);
        assert!(gw >= MIN_SCREEN_DIM && gh >= MIN_SCREEN_DIM);
        // Full screen when the target would exceed the pixel grid.
        assert_eq!(grid_shape(64, 48, 0, 16.0), Some((64, 48)));
        assert_eq!(grid_shape(64, 48, 64 * 48 * 16, 16.0), Some((64, 48)));
    }

    #[test]
    fn plan_records_direct_and_aggregate() {
        let direct = plan(100_000, 200_000.0, false, 1.15, 1200, 800, 16.0).unwrap();
        assert!(direct.exact);
        assert_eq!(direct.mode, MODE_DIRECT);

        let aggregate = plan(350_000, 200_000.0, false, 1.15, 1200, 800, 16.0).unwrap();
        assert!(!aggregate.exact);
        assert_eq!(aggregate.mode, MODE_AGGREGATE);
        assert!(aggregate.grid_w < 1200);
    }

    #[test]
    fn screen_shape_clamps_including_non_positive() {
        assert_eq!(screen_shape(0, 10), (16, 16));
        assert_eq!(screen_shape(8, 10_000), (16, MAX_SCREEN_DIM));
    }

    #[test]
    fn rejects_non_finite_policy() {
        assert!(drill_decision(10, f64::NAN, false, 1.15).is_none());
        assert!(grid_shape(64, 48, 10, 0.0).is_none());
    }
}
