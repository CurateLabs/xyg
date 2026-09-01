//! View-dependent LOD decision math (§5/§28).
//!
//! Hosts validate and assemble string mode names; this module owns the
//! exact-vs-aggregate hysteresis decision and the screen-bounded aggregation
//! grid so Python and Node stay bit-identical
//! ([host-parity.md](../../spec/design/host-parity.md)).

/// Cap matching `python/xyg/config.py` `MAX_SCREEN_DIM`.
pub const MAX_SCREEN_DIM: i32 = 4096;
/// Floor matching `lod.screen_shape` — avoids zero-size aggregate grids.
pub const MIN_SCREEN_DIM: i32 = 16;
/// Default points-per-cell target (`DENSITY_TARGET_POINTS_PER_CELL`).
pub const DEFAULT_TARGET_PER_CELL: f64 = 16.0;
/// Default drill-exit hysteresis (`DRILL_EXIT_FACTOR`).
pub const DEFAULT_EXIT_FACTOR: f64 = 1.15;

/// Line/area M4 threshold (`python/xyg/config.py` `DECIMATION_THRESHOLD`).
pub const DECIMATION_THRESHOLD: u64 = 10_000;
/// Scatter density threshold (`SCATTER_DENSITY_THRESHOLD`). Strict `>` .
pub const SCATTER_DENSITY_THRESHOLD: u64 = 200_000;
/// Per-item-channel direct ceiling (`DIRECT_SOFT_CEILING`). Strict `>` .
pub const DIRECT_SOFT_CEILING: u64 = 2_000_000;

/// Compile-time payload kind: line/area/error-band (M4 vs direct).
pub const PAYLOAD_KIND_LINE: i32 = 0;
/// Compile-time payload kind: scatter (density vs direct).
pub const PAYLOAD_KIND_SCATTER: i32 = 1;

/// Ship every finite row.
pub const PAYLOAD_TIER_DIRECT: i32 = 0;
/// Ship M4-decimated windows (lines/areas over the threshold).
pub const PAYLOAD_TIER_DECIMATED: i32 = 1;
/// Ship a density grid (scatter over the threshold).
pub const PAYLOAD_TIER_DENSITY: i32 = 2;

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

/// Order a possibly flipped request window as `(lo_x, hi_x, lo_y, hi_y)`.
///
/// Matches Python `lod.normalize_window` / Node `normalizeWindow`.
pub fn normalize_window(
    x0: f64,
    x1: f64,
    y0: f64,
    y1: f64,
    require_area: bool,
) -> Result<(f64, f64, f64, f64), NormalizeWindowError> {
    if !x0.is_finite() || !x1.is_finite() || !y0.is_finite() || !y1.is_finite() {
        return Err(NormalizeWindowError::NonFinite);
    }
    let lo_x = x0.min(x1);
    let hi_x = x0.max(x1);
    let lo_y = y0.min(y1);
    let hi_y = y0.max(y1);
    if require_area && (lo_x == hi_x || lo_y == hi_y) {
        return Err(NormalizeWindowError::ZeroArea);
    }
    Ok((lo_x, hi_x, lo_y, hi_y))
}

/// Validation failure for [`normalize_window`].
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum NormalizeWindowError {
    NonFinite,
    ZeroArea,
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
        mode: if exact { MODE_DIRECT } else { MODE_AGGREGATE },
        grid_w,
        grid_h,
    })
}

/// Compile-time payload tier for one trace (§5/§28, ABI 122).
///
/// `force_density` is tri-state: `-1` auto, `0` false, `1` true. Polar
/// always ships direct (M4 buckets and density cells are not polar-aware).
/// Scatter uses `>` against `SCATTER_DENSITY_THRESHOLD`, or
/// `DIRECT_SOFT_CEILING` when `per_item_channels` is set.
pub fn payload_tier(
    kind: i32,
    n_points: u64,
    polar: bool,
    force_density: i32,
    force_direct: bool,
    per_item_channels: bool,
) -> Option<i32> {
    if !matches!(kind, PAYLOAD_KIND_LINE | PAYLOAD_KIND_SCATTER) {
        return None;
    }
    if !matches!(force_density, -1 | 0 | 1) {
        return None;
    }
    if polar || force_direct {
        return Some(PAYLOAD_TIER_DIRECT);
    }
    match kind {
        PAYLOAD_KIND_LINE => Some(if n_points > DECIMATION_THRESHOLD {
            PAYLOAD_TIER_DECIMATED
        } else {
            PAYLOAD_TIER_DIRECT
        }),
        PAYLOAD_KIND_SCATTER => {
            let density = match force_density {
                0 => false,
                1 => true,
                _ => {
                    let threshold = if per_item_channels {
                        DIRECT_SOFT_CEILING
                    } else {
                        SCATTER_DENSITY_THRESHOLD
                    };
                    n_points > threshold
                }
            };
            Some(if density {
                PAYLOAD_TIER_DENSITY
            } else {
                PAYLOAD_TIER_DIRECT
            })
        }
        _ => None,
    }
}

/// Whether the payload visible-row mask can drop anything for this trace.
///
/// Matches `_payload._visible_mask_needed`: log axes, a baseline with nulls,
/// or unfiltered columns whose zone maps recorded NaN/±inf.
pub fn payload_visible_needed(
    x_log: bool,
    y_log: bool,
    prefiltered: bool,
    x_has_nulls: bool,
    y_has_nulls: bool,
    has_base: bool,
    base_has_nulls: bool,
) -> bool {
    if x_log || y_log {
        return true;
    }
    if has_base && base_has_nulls {
        return true;
    }
    !prefiltered && (x_has_nulls || y_has_nulls)
}

/// Finite + log-positive + optional-baseline keep mask (§19).
///
/// Writes `n` bytes (`1` keep / `0` drop). Returns the keep count.
pub fn payload_visible_mask(
    x: &[f64],
    y: &[f64],
    x_log: bool,
    y_log: bool,
    base: Option<&[f64]>,
    out: &mut [u8],
) -> Option<usize> {
    if x.len() != y.len() {
        return None;
    }
    let n = x.len();
    if let Some(base) = base {
        if base.len() != n {
            return None;
        }
    }
    if out.len() < n {
        return None;
    }
    let mut kept = 0usize;
    for i in 0..n {
        let bv = base.map(|b| b[i]);
        let keep = row_visible(x[i], y[i], x_log, y_log, bv);
        out[i] = u8::from(keep);
        kept += usize::from(keep);
    }
    Some(kept)
}

/// Compile-time line M4 indices (ABI 204).
///
/// Owns the line `payload_tier` decision (including polar → direct), the
/// closed-window ulp (`hi + f64::EPSILON` so `[lo, hi]` includes the right
/// endpoint of a half-open M4 window), and optional nonlinear `bin_x`
/// buckets. Direct traces return an empty index list. Hosts still map scale
/// coordinates and gather extra columns.
pub fn payload_m4_indices(
    n_points: u64,
    polar: bool,
    x: &[f64],
    y: &[f64],
    x0: f64,
    x1: f64,
    n_buckets: usize,
    bin_x: Option<&[f64]>,
    bin_x0: f64,
    bin_x1: f64,
) -> Option<(i32, Vec<u32>)> {
    let tier = payload_tier(PAYLOAD_KIND_LINE, n_points, polar, -1, false, false)?;
    if tier == PAYLOAD_TIER_DIRECT {
        return Some((PAYLOAD_TIER_DIRECT, Vec::new()));
    }
    if x.len() != y.len() || x.len() > u32::MAX as usize || n_buckets == 0 {
        return None;
    }
    let (bx, b0, b1) = match bin_x {
        Some(bx) => {
            if bx.len() != x.len() {
                return None;
            }
            (bx, bin_x0, bin_x1)
        }
        None => (x, x0, x1),
    };
    let b1 = b1 + f64::EPSILON;
    if !(b0.is_finite() && b1.is_finite() && b1 > b0) {
        return None;
    }
    Some((
        PAYLOAD_TIER_DECIMATED,
        crate::kernels::m4_indices(bx, y, b0, b1, n_buckets),
    ))
}

/// Keep-all vs explicit keep indices (ABI 205).
///
/// `KeepAll` means the host ships every row without an N-index allocation.
/// `Indices` is the filtered/sampled/even subset, including the empty set.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum PayloadIndexSel {
    KeepAll,
    Indices(Vec<u32>),
}

fn row_visible(xv: f64, yv: f64, x_log: bool, y_log: bool, base: Option<f64>) -> bool {
    let mut keep = xv.is_finite() && yv.is_finite();
    if keep && x_log {
        keep = xv > 0.0;
    }
    if keep && y_log {
        keep = yv > 0.0;
    }
    if keep {
        if let Some(bv) = base {
            keep = if y_log {
                bv.is_finite() && bv > 0.0
            } else {
                bv.is_finite()
            };
        }
    }
    keep
}

/// Fuse ABI 122 needed + mask into keep indices (ABI 205).
///
/// `KeepAll` (`out_keep_all = 1`) means the host must not allocate N indices.
/// When a scan can drop rows, indices are original positions in `x`/`y`.
pub fn payload_visible_indices(
    x: &[f64],
    y: &[f64],
    x_log: bool,
    y_log: bool,
    base: Option<&[f64]>,
    prefiltered: bool,
    x_has_nulls: bool,
    y_has_nulls: bool,
    has_base: bool,
    base_has_nulls: bool,
) -> Option<PayloadIndexSel> {
    if x.len() != y.len() || x.len() > u32::MAX as usize {
        return None;
    }
    let base_vals = if has_base {
        let base = base?;
        if base.len() != x.len() {
            return None;
        }
        Some(base)
    } else if base.is_some() {
        return None;
    } else {
        None
    };
    if !payload_visible_needed(
        x_log,
        y_log,
        prefiltered,
        x_has_nulls,
        y_has_nulls,
        has_base,
        base_has_nulls,
    ) {
        return Some(PayloadIndexSel::KeepAll);
    }
    let n = x.len();
    let mut idx = Vec::new();
    for i in 0..n {
        let bv = base_vals.map(|b| b[i]);
        if row_visible(x[i], y[i], x_log, y_log, bv) {
            idx.push(i as u32);
        }
    }
    if idx.len() == n {
        Some(PayloadIndexSel::KeepAll)
    } else {
        Some(PayloadIndexSel::Indices(idx))
    }
}

/// Stem/errorbar emit count budget: `max(1024, floor(px_width) * 4)` (ABI 214).
///
/// Matches Python `max(1024, int(px_width) * 4)` and Node
/// `Math.max(1024, Math.floor(Number(pxWidth)) * 4)` for the finite
/// non-negative widths hosts actually pass. Non-finite widths return `None`.
/// Negative finite widths still yield `1024` because `max(1024, negative)` is
/// `1024`. Saturates below `usize::MAX` so that sentinel stays the FFI error.
pub fn payload_segment_budget(px_width: f64) -> Option<usize> {
    if !px_width.is_finite() {
        return None;
    }
    if px_width < 0.0 {
        return Some(1024);
    }
    let floor = px_width.floor();
    if floor >= (u64::MAX / 4) as f64 {
        return Some(usize::MAX - 1);
    }
    let width = floor as u64;
    Some(width.saturating_mul(4).max(1024) as usize)
}

/// Errorbar role-block keep indices (ABI 215).
///
/// Segments ship as `seg_per` concatenated groups of `n_points`. When
/// `n_segments % n_points != 0` the host keeps every row. Otherwise this
/// takes ABI 205 even indices of the points and expands
/// `chosen[i] + k * n_points` for `k` in `0..seg_per` (Python concatenate /
/// Node nested `k`/`i` loop).
pub fn payload_errorbar_indices(
    n_segments: usize,
    n_points: usize,
    budget: usize,
) -> Option<PayloadIndexSel> {
    if n_points == 0
        || budget == 0
        || n_points > u32::MAX as usize
        || n_segments > u32::MAX as usize
        || budget > u32::MAX as usize
    {
        return None;
    }
    if n_segments % n_points != 0 {
        return Some(PayloadIndexSel::KeepAll);
    }
    let seg_per = n_segments / n_points;
    if seg_per == 0 {
        return Some(PayloadIndexSel::KeepAll);
    }
    match payload_even_indices(n_points, budget)? {
        PayloadIndexSel::KeepAll => Some(PayloadIndexSel::KeepAll),
        PayloadIndexSel::Indices(chosen) => {
            let out_len = chosen.len().checked_mul(seg_per)?;
            let mut out = Vec::with_capacity(out_len);
            for k in 0..seg_per {
                let base = (k as u32).checked_mul(n_points as u32)?;
                for &idx in &chosen {
                    out.push(idx.checked_add(base)?);
                }
            }
            Some(PayloadIndexSel::Indices(out))
        }
    }
}

const ERRORBAR_ROLE_XOR_LO: u32 = 0x9E3779B9;
const ERRORBAR_ROLE_XOR_HI: u32 = 0x85EBCA6B;

/// Errorbar role-qualified transition keys (ABI 257).
///
/// Hosts pass per-segment point indices and role ids after decimation gather.
/// Returns ``None`` when layouts are invalid; returns ``Some(Err(true))`` when
/// XOR-qualified ``(lo, hi)`` pairs collide.
pub fn payload_errorbar_role_keys(
    point_keys_lo: &[u32],
    point_keys_hi: &[u32],
    segment_sources: &[u32],
    segment_roles: &[u32],
    out_lo: &mut [u32],
    out_hi: &mut [u32],
) -> Option<Result<usize, bool>> {
    let n = segment_sources.len();
    if n != segment_roles.len() || n > out_lo.len() || n > out_hi.len() {
        return None;
    }
    if point_keys_lo.len() != point_keys_hi.len() {
        return None;
    }
    let n_points = point_keys_lo.len();
    if n_points == 0 && n > 0 {
        return None;
    }
    use std::collections::HashSet;
    let mut seen = HashSet::with_capacity(n);
    for i in 0..n {
        let point = segment_sources[i] as usize;
        if point >= n_points {
            return None;
        }
        let role = segment_roles[i];
        let lo = point_keys_lo[point] ^ role.wrapping_mul(ERRORBAR_ROLE_XOR_LO);
        let hi = point_keys_hi[point] ^ role.wrapping_mul(ERRORBAR_ROLE_XOR_HI);
        if !seen.insert((lo, hi)) {
            return Some(Err(true));
        }
        out_lo[i] = lo;
        out_hi[i] = hi;
    }
    Some(Ok(n))
}

/// Errorbar segment role/source maps (ABI 261).
///
/// When ``n_segments % n_points == 0`` and ``seg_per >= 1``, writes
/// ``out_sources[i] = i % n_points`` and ``out_roles[i] = i / n_points``
/// (matching ``np.tile(np.arange(n_points), seg_per)`` /
/// ``np.repeat(np.arange(seg_per), n_points)``). Sets ``out_applicable`` to
/// ``1``; otherwise ``0`` without writing outputs.
pub fn payload_errorbar_role_maps(
    n_segments: usize,
    n_points: usize,
    out_sources: &mut [u32],
    out_roles: &mut [u32],
    out_applicable: &mut i32,
) -> i32 {
    if n_points == 0 || n_points > u32::MAX as usize {
        return 0;
    }
    if n_segments % n_points != 0 {
        *out_applicable = 0;
        return 1;
    }
    let seg_per = n_segments / n_points;
    if seg_per == 0 {
        *out_applicable = 0;
        return 1;
    }
    if out_sources.len() < n_segments || out_roles.len() < n_segments {
        return 0;
    }
    for i in 0..n_segments {
        out_sources[i] = (i % n_points) as u32;
        out_roles[i] = (i / n_points) as u32;
    }
    *out_applicable = 1;
    1
}

const PAYLOAD_BAR_WIDTH_RTOL: f64 = 1e-5;
const PAYLOAD_BAR_WIDTH_ATOL: f64 = 1e-8;

fn payload_f64_allclose(a: f64, b: f64) -> bool {
    (a - b).abs() <= PAYLOAD_BAR_WIDTH_ATOL + PAYLOAD_BAR_WIDTH_RTOL * b.abs()
}

/// Bar/column compact emit admit (ABI 274).
///
/// Hosts pass bar edge widths and baseline ``value0`` columns after finite
/// filtering. ``out_compact`` is ``1`` when uniform finite positive width allows
/// the nested ``bar`` spec; ``0`` means fall back to per-rect geometry.
/// ``out_has_value0_const`` is ``1`` when every baseline is finite and equal.
pub fn payload_bar_compact_admit(
    widths: &[f64],
    value0: &[f64],
    out_width: &mut f64,
    out_value0_const: &mut f64,
    out_has_value0_const: &mut i32,
    out_compact: &mut i32,
) -> i32 {
    *out_has_value0_const = 0;
    *out_value0_const = f64::NAN;
    let width = if widths.is_empty() {
        1.0
    } else {
        let first = widths[0];
        if !first.is_finite() || first <= 0.0 {
            *out_width = f64::NAN;
            *out_compact = 0;
            return 1;
        }
        if !widths
            .iter()
            .all(|&w| payload_f64_allclose(w, first))
        {
            *out_width = f64::NAN;
            *out_compact = 0;
            return 1;
        }
        first
    };
    *out_width = width;
    *out_compact = 1;
    if !value0.is_empty() {
        let first = value0[0];
        if value0.iter().all(|v| v.is_finite()) && value0.iter().all(|&v| v == first) {
            *out_has_value0_const = 1;
            *out_value0_const = first;
        }
    }
    1
}

/// Transition-key shipping admit (ABI 259).
///
/// Hosts pass row counts after gather/selection. Returns ``0`` when keys may
/// ship, ``1`` for ``snap:aggregate``, ``2`` for ``snap:key-limit``, ``3`` for
/// ``index:key-count-mismatch``. ``max_rows`` is the host ``MAX_ANIMATION_MATCH_ROWS``.
pub const PAYLOAD_TRANSITION_SHIP: i32 = 0;
pub const PAYLOAD_TRANSITION_SNAP_AGGREGATE: i32 = 1;
pub const PAYLOAD_TRANSITION_SNAP_KEY_LIMIT: i32 = 2;
pub const PAYLOAD_TRANSITION_KEY_COUNT_MISMATCH: i32 = 3;

pub fn payload_transition_keys_admit(
    has_keys: i32,
    tier_direct: i32,
    n_keys: usize,
    n_marks: usize,
    max_rows: usize,
) -> i32 {
    if has_keys == 0 {
        return PAYLOAD_TRANSITION_SHIP;
    }
    if tier_direct == 0 {
        return PAYLOAD_TRANSITION_SNAP_AGGREGATE;
    }
    if n_keys == n_marks {
        if n_keys > max_rows {
            return PAYLOAD_TRANSITION_SNAP_KEY_LIMIT;
        }
        return PAYLOAD_TRANSITION_SHIP;
    }
    PAYLOAD_TRANSITION_KEY_COUNT_MISMATCH
}

/// NumPy `linspace(0, n-1, count, dtype=np.int64)` as u32 (ABI 205).
///
/// Truncates toward 0 and pins the last element to `n-1`. When `n <= count`
/// the host keeps every row (`KeepAll`) instead of materializing 0..n-1.
pub fn payload_even_indices(n: usize, count: usize) -> Option<PayloadIndexSel> {
    if n > u32::MAX as usize || count > u32::MAX as usize || count == 0 {
        return None;
    }
    if n <= count {
        return Some(PayloadIndexSel::KeepAll);
    }
    let mut idx = vec![0u32; count];
    if count == 1 {
        return Some(PayloadIndexSel::Indices(idx));
    }
    let stop = (n - 1) as f64;
    let step = stop / (count - 1) as f64;
    for (i, slot) in idx.iter_mut().enumerate() {
        *slot = (i as f64 * step) as u32;
    }
    idx[count - 1] = (n - 1) as u32;
    Some(PayloadIndexSel::Indices(idx))
}

fn sample_fraction(level: u32, base: f64, growth: f64) -> Option<f64> {
    if !(base > 0.0 && base <= 1.0 && base.is_finite()) {
        return None;
    }
    if !(growth >= 1.0 && growth.is_finite()) {
        return None;
    }
    if base >= 1.0 || (growth - 1.0).abs() == 0.0 {
        return Some(base.min(1.0));
    }
    let Ok(level_i) = i32::try_from(level) else {
        return Some(1.0);
    };
    let frac = base * growth.powi(level_i);
    if !frac.is_finite() {
        return Some(1.0);
    }
    Some(frac.min(1.0))
}

/// Density-overlay sample of implicit ids `0..n` (ABI 205).
///
/// Owns `min(1, target/n)`, `_sample_fraction(level, base, growth)`,
/// `sample_threshold`, and `sample_range_indices`. `KeepAll` means every
/// implicit id ships (n <= target at level 0).
pub fn payload_sample_target_indices(
    n: usize,
    target: usize,
    seed: u64,
    level: u32,
    growth: f64,
) -> Option<PayloadIndexSel> {
    if n > u32::MAX as usize || target == 0 {
        return None;
    }
    if n == 0 {
        return Some(PayloadIndexSel::Indices(Vec::new()));
    }
    let base = (target as f64 / n as f64).min(1.0);
    let fraction = sample_fraction(level, base, growth)?;
    if fraction >= 1.0 {
        return Some(PayloadIndexSel::KeepAll);
    }
    let threshold = crate::kernels::sample_threshold(fraction);
    let cap = n.min((target * 2).max(64));
    let mut out = vec![0u32; cap];
    let written = crate::kernels::sample_range_indices_into(n, seed, threshold, &mut out);
    if written > out.len() {
        out.resize(written, 0);
        let written = crate::kernels::sample_range_indices_into(n, seed, threshold, &mut out);
        out.truncate(written);
    } else {
        out.truncate(written);
    }
    Some(PayloadIndexSel::Indices(out))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn normalize_window_orders_and_validates() {
        assert_eq!(
            normalize_window(5.0, 1.0, 4.0, 2.0, true),
            Ok((1.0, 5.0, 2.0, 4.0))
        );
        assert_eq!(
            normalize_window(1.0, 1.0, 2.0, 3.0, false),
            Ok((1.0, 1.0, 2.0, 3.0))
        );
        assert_eq!(
            normalize_window(1.0, 1.0, 2.0, 3.0, true),
            Err(NormalizeWindowError::ZeroArea)
        );
        assert_eq!(
            normalize_window(f64::NAN, 1.0, 2.0, 3.0, true),
            Err(NormalizeWindowError::NonFinite)
        );
    }

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

    #[test]
    fn payload_tier_line_polar_and_threshold() {
        assert_eq!(
            payload_tier(PAYLOAD_KIND_LINE, 10_000, false, -1, false, false),
            Some(PAYLOAD_TIER_DIRECT)
        );
        assert_eq!(
            payload_tier(PAYLOAD_KIND_LINE, 10_001, false, -1, false, false),
            Some(PAYLOAD_TIER_DECIMATED)
        );
        assert_eq!(
            payload_tier(PAYLOAD_KIND_LINE, 50_000, true, -1, false, false),
            Some(PAYLOAD_TIER_DIRECT)
        );
    }

    #[test]
    fn payload_tier_scatter_strict_gt_and_per_item_ceiling() {
        assert_eq!(
            payload_tier(
                PAYLOAD_KIND_SCATTER,
                SCATTER_DENSITY_THRESHOLD,
                false,
                -1,
                false,
                false
            ),
            Some(PAYLOAD_TIER_DIRECT)
        );
        assert_eq!(
            payload_tier(
                PAYLOAD_KIND_SCATTER,
                SCATTER_DENSITY_THRESHOLD + 1,
                false,
                -1,
                false,
                false
            ),
            Some(PAYLOAD_TIER_DENSITY)
        );
        assert_eq!(
            payload_tier(
                PAYLOAD_KIND_SCATTER,
                SCATTER_DENSITY_THRESHOLD + 1,
                false,
                -1,
                false,
                true
            ),
            Some(PAYLOAD_TIER_DIRECT)
        );
        assert_eq!(
            payload_tier(PAYLOAD_KIND_SCATTER, 10, false, 1, false, false),
            Some(PAYLOAD_TIER_DENSITY)
        );
        assert_eq!(
            payload_tier(PAYLOAD_KIND_SCATTER, 10, true, 1, false, false),
            Some(PAYLOAD_TIER_DIRECT)
        );
        assert_eq!(
            payload_tier(PAYLOAD_KIND_SCATTER, 1_000_000, false, 0, false, false),
            Some(PAYLOAD_TIER_DIRECT)
        );
        assert!(payload_tier(99, 1, false, -1, false, false).is_none());
    }

    #[test]
    fn payload_visible_mask_drops_nonpositive_on_log() {
        let x = [1.0, -2.0, 3.0, 0.0, 5.0];
        let y = [1.0, 2.0, 3.0, 4.0, 5.0];
        let mut out = [0u8; 5];
        assert_eq!(
            payload_visible_mask(&x, &y, true, false, None, &mut out),
            Some(3)
        );
        assert_eq!(&out, &[1, 0, 1, 0, 1]);
        assert!(!payload_visible_needed(
            false, false, true, false, false, false, false
        ));
        assert!(payload_visible_needed(
            true, false, true, false, false, false, false
        ));
    }

    #[test]
    fn payload_m4_indices_polar_stays_direct() {
        let x: Vec<f64> = (0..10_001).map(|i| i as f64).collect();
        let y = vec![1.0; 10_001];
        let (tier, idx) =
            payload_m4_indices(10_001, true, &x, &y, 0.0, 10_000.0, 64, None, 0.0, 0.0).unwrap();
        assert_eq!(tier, PAYLOAD_TIER_DIRECT);
        assert!(idx.is_empty());
    }

    #[test]
    fn payload_m4_indices_closed_window_matches_m4_plus_eps() {
        let x: Vec<f64> = (0..10_001).map(|i| i as f64).collect();
        let y: Vec<f64> = x.iter().map(|v| v.sin()).collect();
        let (tier, idx) =
            payload_m4_indices(10_001, false, &x, &y, 0.0, 10_000.0, 64, None, 0.0, 0.0).unwrap();
        assert_eq!(tier, PAYLOAD_TIER_DECIMATED);
        let expected = crate::kernels::m4_indices(&x, &y, 0.0, 10_000.0 + f64::EPSILON, 64);
        assert_eq!(idx, expected);
        let (empty_tier, empty_idx) = payload_m4_indices(
            10_001, false, &x, &y, 20_000.0, 21_000.0, 64, None, 0.0, 0.0,
        )
        .unwrap();
        assert_eq!(empty_tier, PAYLOAD_TIER_DECIMATED);
        assert!(empty_idx.is_empty());
    }

    #[test]
    fn payload_m4_indices_uses_bin_x_window() {
        let x: Vec<f64> = (0..10_001)
            .map(|i| 10.0_f64.powf(i as f64 / 5_000.0))
            .collect();
        let y = vec![1.0; 10_001];
        let bx: Vec<f64> = x.iter().map(|v| v.log10()).collect();
        let (tier, idx) = payload_m4_indices(
            10_001,
            false,
            &x,
            &y,
            x[0],
            x[x.len() - 1],
            32,
            Some(&bx),
            bx[0],
            bx[bx.len() - 1],
        )
        .unwrap();
        assert_eq!(tier, PAYLOAD_TIER_DECIMATED);
        let expected =
            crate::kernels::m4_indices(&bx, &y, bx[0], bx[bx.len() - 1] + f64::EPSILON, 32);
        assert_eq!(idx, expected);
    }

    #[test]
    fn payload_visible_indices_keep_all_and_log_drop() {
        let x = [1.0, -2.0, 3.0, 0.0, 5.0];
        let y = [1.0, 2.0, 3.0, 4.0, 5.0];
        assert_eq!(
            payload_visible_indices(&x, &y, false, false, None, true, false, false, false, false),
            Some(PayloadIndexSel::KeepAll)
        );
        assert_eq!(
            payload_visible_indices(&x, &y, true, false, None, true, false, false, false, false),
            Some(PayloadIndexSel::Indices(vec![0, 2, 4]))
        );
        let all_pos = [1.0, 2.0, 3.0];
        assert_eq!(
            payload_visible_indices(
                &all_pos, &all_pos, true, false, None, true, false, false, false, false
            ),
            Some(PayloadIndexSel::KeepAll)
        );
    }

    #[test]
    fn payload_segment_budget_matches_host_max() {
        assert_eq!(payload_segment_budget(100.0), Some(1024));
        assert_eq!(payload_segment_budget(256.0), Some(1024));
        assert_eq!(payload_segment_budget(256.9), Some(1024));
        assert_eq!(payload_segment_budget(257.0), Some(1028));
        assert_eq!(payload_segment_budget(0.0), Some(1024));
        assert_eq!(payload_segment_budget(-10.7), Some(1024));
        assert!(payload_segment_budget(f64::NAN).is_none());
        assert!(payload_segment_budget(f64::INFINITY).is_none());
    }

    #[test]
    fn payload_errorbar_indices_expands_even_keep_across_roles() {
        assert_eq!(
            payload_errorbar_indices(33, 11, 20),
            Some(PayloadIndexSel::KeepAll)
        );
        assert_eq!(
            payload_errorbar_indices(10, 3, 2),
            Some(PayloadIndexSel::KeepAll)
        );
        assert_eq!(
            payload_errorbar_indices(33, 11, 4),
            Some(PayloadIndexSel::Indices(vec![
                0, 3, 6, 10, 11, 14, 17, 21, 22, 25, 28, 32
            ]))
        );
        assert!(payload_errorbar_indices(33, 0, 4).is_none());
        assert!(payload_errorbar_indices(33, 11, 0).is_none());
    }

    #[test]
    fn payload_errorbar_role_maps_matches_host_tile_repeat() {
        let mut sources = [0u32; 6];
        let mut roles = [0u32; 6];
        let mut applicable = -1;
        assert_eq!(
            payload_errorbar_role_maps(6, 3, &mut sources, &mut roles, &mut applicable),
            1
        );
        assert_eq!(applicable, 1);
        assert_eq!(sources, [0, 1, 2, 0, 1, 2]);
        assert_eq!(roles, [0, 0, 0, 1, 1, 1]);
        applicable = -1;
        assert_eq!(
            payload_errorbar_role_maps(10, 3, &mut sources, &mut roles, &mut applicable),
            1
        );
        assert_eq!(applicable, 0);
        assert_eq!(payload_errorbar_role_maps(6, 0, &mut sources, &mut roles, &mut applicable), 0);
    }

    #[test]
    fn payload_errorbar_role_keys_matches_host_xor_mix() {
        let point_lo = [10u32, 20];
        let point_hi = [30u32, 40];
        let sources = [0u32, 1, 0, 1];
        let roles = [0u32, 0, 1, 1];
        let mut out_lo = [0u32; 4];
        let mut out_hi = [0u32; 4];
        assert_eq!(
            payload_errorbar_role_keys(
                &point_lo,
                &point_hi,
                &sources,
                &roles,
                &mut out_lo,
                &mut out_hi,
            ),
            Some(Ok(4))
        );
        assert_eq!(out_lo, [10, 20, 10 ^ ERRORBAR_ROLE_XOR_LO, 20 ^ ERRORBAR_ROLE_XOR_LO]);
        assert_eq!(out_hi, [30, 40, 30 ^ ERRORBAR_ROLE_XOR_HI, 40 ^ ERRORBAR_ROLE_XOR_HI]);
    }

    #[test]
    fn payload_errorbar_role_keys_rejects_collisions() {
        let point_lo = [0u32, 0x9E3779B9];
        let point_hi = [0u32, 0x85EBCA6B];
        let sources = [1u32, 0];
        let roles = [0u32, 1];
        let mut out_lo = [0u32; 2];
        let mut out_hi = [0u32; 2];
        assert_eq!(
            payload_errorbar_role_keys(
                &point_lo,
                &point_hi,
                &sources,
                &roles,
                &mut out_lo,
                &mut out_hi,
            ),
            Some(Err(true))
        );
    }

    #[test]
    fn payload_errorbar_role_keys_rejects_expanded_errorbar_collisions() {
        let point_lo = [0u32, 0x9E3779B9];
        let point_hi = [0u32, 0x85EBCA6B];
        let sources = [0u32, 1, 0, 1, 0, 1];
        let roles = [0u32, 0, 1, 1, 2, 2];
        let mut out_lo = [0u32; 6];
        let mut out_hi = [0u32; 6];
        assert_eq!(
            payload_errorbar_role_keys(
                &point_lo,
                &point_hi,
                &sources,
                &roles,
                &mut out_lo,
                &mut out_hi,
            ),
            Some(Err(true))
        );
    }

    #[test]
    fn payload_bar_compact_admit_uniform_width_and_const_baseline() {
        let mut width = 0.0;
        let mut value0_const = 0.0;
        let mut has_value0_const = 0;
        let mut compact = 0;
        assert_eq!(
            payload_bar_compact_admit(
                &[0.8, 0.8, 0.8],
                &[0.0, 0.0, 0.0],
                &mut width,
                &mut value0_const,
                &mut has_value0_const,
                &mut compact,
            ),
            1
        );
        assert_eq!(compact, 1);
        assert_eq!(width, 0.8);
        assert_eq!(has_value0_const, 1);
        assert_eq!(value0_const, 0.0);
    }

    #[test]
    fn payload_bar_compact_admit_rejects_non_uniform_width() {
        let mut width = 0.0;
        let mut value0_const = 0.0;
        let mut has_value0_const = 0;
        let mut compact = 0;
        assert_eq!(
            payload_bar_compact_admit(
                &[0.8, 0.9],
                &[],
                &mut width,
                &mut value0_const,
                &mut has_value0_const,
                &mut compact,
            ),
            1
        );
        assert_eq!(compact, 0);
        assert!(width.is_nan());
        assert_eq!(has_value0_const, 0);
    }

    #[test]
    fn payload_transition_keys_admit_matches_host_policy() {
        assert_eq!(
            payload_transition_keys_admit(1, 0, 10, 10, 200_000),
            PAYLOAD_TRANSITION_SNAP_AGGREGATE,
        );
        assert_eq!(
            payload_transition_keys_admit(1, 1, 200_001, 200_001, 200_000),
            PAYLOAD_TRANSITION_SNAP_KEY_LIMIT,
        );
        assert_eq!(
            payload_transition_keys_admit(1, 1, 10, 9, 200_000),
            PAYLOAD_TRANSITION_KEY_COUNT_MISMATCH,
        );
        assert_eq!(
            payload_transition_keys_admit(1, 1, 10, 10, 200_000),
            PAYLOAD_TRANSITION_SHIP,
        );
        assert_eq!(payload_transition_keys_admit(0, 0, 0, 0, 200_000), PAYLOAD_TRANSITION_SHIP);
    }

    #[test]
    fn payload_even_indices_matches_numpy_int64_linspace() {
        assert_eq!(payload_even_indices(4, 10), Some(PayloadIndexSel::KeepAll));
        assert_eq!(
            payload_even_indices(11, 4),
            Some(PayloadIndexSel::Indices(vec![0, 3, 6, 10]))
        );
        let n = 10_000usize;
        let count = 1024usize;
        let PayloadIndexSel::Indices(idx) = payload_even_indices(n, count).unwrap() else {
            panic!("expected indices");
        };
        assert_eq!(idx[0], 0);
        assert_eq!(*idx.last().unwrap(), (n - 1) as u32);
        assert_eq!(idx.len(), count);
    }

    #[test]
    fn payload_sample_target_indices_keep_all_and_seed() {
        assert_eq!(
            payload_sample_target_indices(100, 8_192, 0, 0, 2.0),
            Some(PayloadIndexSel::KeepAll)
        );
        let PayloadIndexSel::Indices(idx) =
            payload_sample_target_indices(10_000, 8_192, 0, 0, 2.0).unwrap()
        else {
            panic!("expected sample");
        };
        assert!(!idx.is_empty());
        assert!(idx.len() < 10_000);
        assert!(idx.windows(2).all(|w| w[0] < w[1]));
        let expected = crate::kernels::sample_range_indices(
            10_000,
            0,
            crate::kernels::sample_threshold(8_192.0 / 10_000.0),
        );
        assert_eq!(idx, expected);
    }
}
