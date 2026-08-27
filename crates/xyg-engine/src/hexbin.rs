//! Hexagonal binning (matplotlib-compatible lattice assignment).
//!
//! Two overlapping lattices — an integer grid and a half-cell offset grid —
//! compete in the hex metric; each finite point joins the nearer center.
//! ABI 102 also owns the composition ingress: finite-pair filtering, automatic
//! domain padding, and the default `int(width / √3)` grid height. Hosts assemble
//! color/geometry from the occupied cells
//! ([rust-engine.md](../spec/design/rust-engine.md)).

/// Reduction applied to optional per-point `C` values inside each hex cell.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
#[repr(i32)]
pub enum HexReduce {
    /// Cell metric is the observation count (`C` ignored).
    Count = 0,
    /// Mean of finite `C` values in the cell (requires `C`).
    Mean = 1,
    /// Sum of finite `C` values in the cell (requires `C`).
    Sum = 2,
}

impl HexReduce {
    pub fn from_i32(v: i32) -> Option<Self> {
        match v {
            0 => Some(Self::Count),
            1 => Some(Self::Mean),
            2 => Some(Self::Sum),
            _ => None,
        }
    }
}

/// Occupied (or threshold-passing) hex cells.
#[derive(Clone, Debug, PartialEq)]
pub struct HexbinResult {
    pub centers_x: Vec<f64>,
    pub centers_y: Vec<f64>,
    pub metrics: Vec<f64>,
    pub counts: Vec<f64>,
    pub dx: f64,
    pub dy: f64,
}

/// Maximum grid dimension accepted by the ABI (matches the Python mark).
pub const MAX_GRID: usize = 2048;

/// Resolved lattice size and data domain after finite-pair ingress.
#[derive(Clone, Copy, Debug, PartialEq)]
pub struct HexbinIngress {
    pub grid_w: usize,
    pub grid_h: usize,
    pub x0: f64,
    pub x1: f64,
    pub y0: f64,
    pub y1: f64,
}

/// Matplotlib `int(nx / sqrt(3))`, floored at 2 so the lattice ABI stays valid.
///
/// Python previously used `int(w / √3)` while Node used `Math.round(w / √3)`.
/// Truncation toward zero is the matplotlib / Python contract and is now the
/// only host-visible default.
pub fn default_grid_height(grid_w: usize) -> usize {
    ((grid_w as f64 / 3.0_f64.sqrt()).trunc() as usize).max(2)
}

/// Shared automatic-domain pad (Python `Figure._auto_domain` / ABI 100 binned ECDF).
///
/// A constant nonzero span widens by 5% of its absolute value; zero or a
/// non-useful pad falls back to plus/minus 0.5. Non-representable intervals
/// return `None`.
pub fn pad_auto_domain(lo: f64, hi: f64) -> Option<(f64, f64)> {
    if lo == hi {
        let mut pad = lo.abs() * 0.05;
        let mut left = lo - pad;
        let mut right = hi + pad;
        if !(pad.is_finite() && pad > 0.0 && left < lo && right > hi) {
            pad = 0.5;
            left = lo - pad;
            right = hi + pad;
        }
        if !(left.is_finite() && right.is_finite() && right > left && (right - left).is_finite()) {
            return None;
        }
        Some((left, right))
    } else if hi > lo && (hi - lo).is_finite() {
        Some((lo, hi))
    } else {
        None
    }
}

fn finite_increasing_range(lo: f64, hi: f64) -> bool {
    lo.is_finite() && hi.is_finite() && hi > lo && (hi - lo).is_finite()
}

/// Scan finite pairs and resolve grid height plus data domain.
///
/// `grid_h = None` selects [`default_grid_height`]. `range = None` pads the
/// finite x/y extents independently. A present `C` column also requires a
/// finite `C` value to count as a pair, matching the previous host filter.
/// Returns `None` when there is no finite pair or the arguments are invalid.
pub fn hexbin_ingress(
    x: &[f64],
    y: &[f64],
    c: Option<&[f64]>,
    grid_w: usize,
    grid_h: Option<usize>,
    range: Option<((f64, f64), (f64, f64))>,
) -> Option<HexbinIngress> {
    if x.len() != y.len() {
        return None;
    }
    if let Some(c) = c {
        if c.len() != x.len() {
            return None;
        }
    }
    if !(2..=MAX_GRID).contains(&grid_w) {
        return None;
    }
    let grid_h = grid_h.unwrap_or_else(|| default_grid_height(grid_w));
    if !(2..=MAX_GRID).contains(&grid_h) {
        return None;
    }

    let mut xmin = f64::INFINITY;
    let mut xmax = f64::NEG_INFINITY;
    let mut ymin = f64::INFINITY;
    let mut ymax = f64::NEG_INFINITY;
    let mut any = false;
    for i in 0..x.len() {
        let xv = x[i];
        let yv = y[i];
        if !xv.is_finite() || !yv.is_finite() {
            continue;
        }
        if let Some(c) = c {
            if !c[i].is_finite() {
                continue;
            }
        }
        any = true;
        xmin = xmin.min(xv);
        xmax = xmax.max(xv);
        ymin = ymin.min(yv);
        ymax = ymax.max(yv);
    }
    if !any {
        return None;
    }

    let ((x0, x1), (y0, y1)) = if let Some(((x0, x1), (y0, y1))) = range {
        if !(finite_increasing_range(x0, x1) && finite_increasing_range(y0, y1)) {
            return None;
        }
        ((x0, x1), (y0, y1))
    } else {
        (pad_auto_domain(xmin, xmax)?, pad_auto_domain(ymin, ymax)?)
    };

    Some(HexbinIngress {
        grid_w,
        grid_h,
        x0,
        x1,
        y0,
        y1,
    })
}

/// Composition hexbin: resolve ingress, then bin the raw columns.
///
/// `grid_h = None` and `range = None` select the Rust-owned defaults. Hosts
/// pass unfiltered source columns; non-finite rows are ignored here and again
/// during lattice assignment.
#[allow(clippy::too_many_arguments)]
pub fn hexbin_with_policy(
    x: &[f64],
    y: &[f64],
    c: Option<&[f64]>,
    grid_w: usize,
    grid_h: Option<usize>,
    range: Option<((f64, f64), (f64, f64))>,
    mincnt: usize,
    reduce: HexReduce,
) -> Option<HexbinResult> {
    let ingress = hexbin_ingress(x, y, c, grid_w, grid_h, range)?;
    hexbin(
        x,
        y,
        c,
        ingress.grid_w,
        ingress.grid_h,
        ingress.x0,
        ingress.x1,
        ingress.y0,
        ingress.y1,
        mincnt,
        reduce,
    )
}

/// Bin `(x, y)` into a matplotlib-style hex lattice.
///
/// `mincnt` keeps cells with `count >= mincnt`. When `C` is absent the metric
/// equals the count; when present, `reduce` must be [`HexReduce::Mean`] or
/// [`HexReduce::Sum`]. Non-finite coordinates (and non-finite `C` when provided)
/// are skipped. Returns `None` on invalid arguments (bad grid, non-increasing
/// range, mean/sum without `C`).
#[allow(clippy::too_many_arguments)] // mirrors the C ABI kernel entry point
pub fn hexbin(
    x: &[f64],
    y: &[f64],
    c: Option<&[f64]>,
    grid_w: usize,
    grid_h: usize,
    x0: f64,
    x1: f64,
    y0: f64,
    y1: f64,
    mincnt: usize,
    reduce: HexReduce,
) -> Option<HexbinResult> {
    if x.len() != y.len() {
        return None;
    }
    if let Some(c) = c {
        if c.len() != x.len() {
            return None;
        }
    }
    if !(2..=MAX_GRID).contains(&grid_w) || !(2..=MAX_GRID).contains(&grid_h) {
        return None;
    }
    if !(x0.is_finite() && x1.is_finite() && y0.is_finite() && y1.is_finite() && x1 > x0 && y1 > y0)
    {
        return None;
    }
    match reduce {
        HexReduce::Count => {}
        HexReduce::Mean | HexReduce::Sum => {
            c?;
        }
    }

    let dx = (x1 - x0) / grid_w as f64;
    let dy = (y1 - y0) / grid_h as f64;
    let n1 = (grid_w + 1) * (grid_h + 1);
    let n2 = grid_w * grid_h;
    let mut count1 = vec![0u64; n1];
    let mut count2 = vec![0u64; n2];
    let mut sum1 = if matches!(reduce, HexReduce::Mean | HexReduce::Sum) {
        vec![0.0f64; n1]
    } else {
        Vec::new()
    };
    let mut sum2 = if matches!(reduce, HexReduce::Mean | HexReduce::Sum) {
        vec![0.0f64; n2]
    } else {
        Vec::new()
    };
    let mut assigned = 0u64;

    for i in 0..x.len() {
        let xv = x[i];
        let yv = y[i];
        if !xv.is_finite() || !yv.is_finite() {
            continue;
        }
        let cv = if let Some(c) = c {
            let v = c[i];
            if !v.is_finite() {
                continue;
            }
            Some(v)
        } else {
            None
        };
        let fx = (xv - x0) * grid_w as f64 / (x1 - x0);
        let fy = (yv - y0) * grid_h as f64 / (y1 - y0);
        let ix1 = rint(fx);
        let iy1 = rint(fy);
        let ix2 = fx.floor() as i64;
        let iy2 = fy.floor() as i64;
        let d1 = (fx - ix1 as f64).powi(2) + 3.0 * (fy - iy1 as f64).powi(2);
        let d2 = (fx - ix2 as f64 - 0.5).powi(2) + 3.0 * (fy - iy2 as f64 - 0.5).powi(2);
        let use_first = d1 < d2;
        if use_first {
            if ix1 >= 0 && iy1 >= 0 && (ix1 as usize) <= grid_w && (iy1 as usize) <= grid_h {
                let flat = (iy1 as usize) * (grid_w + 1) + (ix1 as usize);
                count1[flat] += 1;
                if let Some(v) = cv {
                    sum1[flat] += v;
                }
                assigned += 1;
            }
        } else if ix2 >= 0 && iy2 >= 0 && (ix2 as usize) < grid_w && (iy2 as usize) < grid_h {
            let flat = (iy2 as usize) * grid_w + (ix2 as usize);
            count2[flat] += 1;
            if let Some(v) = cv {
                sum2[flat] += v;
            }
            assigned += 1;
        }
    }

    // Matplotlib-compatible: when every finite point falls outside the lattice,
    // emit nothing (host raises) even if mincnt == 0 would otherwise ship the
    // full zero honeycomb.
    if assigned == 0 {
        return Some(HexbinResult {
            centers_x: Vec::new(),
            centers_y: Vec::new(),
            metrics: Vec::new(),
            counts: Vec::new(),
            dx,
            dy,
        });
    }

    let threshold = mincnt as u64;
    let mut centers_x = Vec::new();
    let mut centers_y = Vec::new();
    let mut metrics = Vec::new();
    let mut counts = Vec::new();

    for flat in 0..n1 {
        let cnt = count1[flat];
        if cnt < threshold {
            continue;
        }
        let ix = flat % (grid_w + 1);
        let iy = flat / (grid_w + 1);
        centers_x.push(x0 + ix as f64 * dx);
        centers_y.push(y0 + iy as f64 * dy);
        counts.push(cnt as f64);
        metrics.push(match reduce {
            HexReduce::Count => cnt as f64,
            HexReduce::Sum => {
                if cnt == 0 {
                    0.0
                } else {
                    sum1[flat]
                }
            }
            HexReduce::Mean => {
                if cnt == 0 {
                    f64::NAN
                } else {
                    sum1[flat] / cnt as f64
                }
            }
        });
    }
    for flat in 0..n2 {
        let cnt = count2[flat];
        if cnt < threshold {
            continue;
        }
        let ix = flat % grid_w;
        let iy = flat / grid_w;
        centers_x.push(x0 + (ix as f64 + 0.5) * dx);
        centers_y.push(y0 + (iy as f64 + 0.5) * dy);
        counts.push(cnt as f64);
        metrics.push(match reduce {
            HexReduce::Count => cnt as f64,
            HexReduce::Sum => {
                if cnt == 0 {
                    0.0
                } else {
                    sum2[flat]
                }
            }
            HexReduce::Mean => {
                if cnt == 0 {
                    f64::NAN
                } else {
                    sum2[flat] / cnt as f64
                }
            }
        });
    }

    Some(HexbinResult {
        centers_x,
        centers_y,
        metrics,
        counts,
        dx,
        dy,
    })
}

/// Capacity needed to hold every cell of both lattices (mincnt = 0).
pub fn hexbin_capacity(grid_w: usize, grid_h: usize) -> usize {
    (grid_w + 1)
        .saturating_mul(grid_h + 1)
        .saturating_add(grid_w.saturating_mul(grid_h))
}

/// NumPy/`rint` banker's rounding (ties to even).
fn rint(v: f64) -> i64 {
    let floor = v.floor();
    let frac = v - floor;
    if frac < 0.5 {
        floor as i64
    } else if frac > 0.5 {
        floor as i64 + 1
    } else {
        // Exactly halfway: pick the even integer.
        let lo = floor as i64;
        if lo.rem_euclid(2) == 0 {
            lo
        } else {
            lo + 1
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn count_bins_match_matplotlib_style_fixture() {
        let x = [0.1, 0.5, 0.9, 0.2];
        let y = [0.1, 0.5, 0.9, 0.8];
        let r = hexbin(&x, &y, None, 4, 4, 0.0, 1.0, 0.0, 1.0, 1, HexReduce::Count).unwrap();
        assert_eq!(r.counts.len(), 4);
        assert!((r.dx - 0.25).abs() < 1e-12);
        assert!((r.dy - 0.25).abs() < 1e-12);
        assert_eq!(r.counts.iter().sum::<f64>(), 4.0);
        // Flat indices keep1=[12,16], keep2=[0,15] from the reference script.
        assert!((r.centers_x[0] - 0.5).abs() < 1e-12); // flat 12 → ix=2,iy=2
        assert!((r.centers_y[0] - 0.5).abs() < 1e-12);
        assert!((r.centers_x[1] - 0.25).abs() < 1e-12); // flat 16 → ix=1, iy=3
        assert!((r.centers_y[1] - 0.75).abs() < 1e-12);
        assert!((r.centers_x[2] - 0.125).abs() < 1e-12); // offset flat 0
        assert!((r.centers_y[2] - 0.125).abs() < 1e-12);
        assert!((r.centers_x[3] - 0.875).abs() < 1e-12); // offset flat 15 → ix=3,iy=3
        assert!((r.centers_y[3] - 0.875).abs() < 1e-12);
    }

    #[test]
    fn mean_and_sum_reduce_c() {
        let x = [0.1, 0.15, 0.9];
        let y = [0.1, 0.12, 0.9];
        let c = [2.0, 4.0, 10.0];
        let mean = hexbin(
            &x,
            &y,
            Some(&c),
            4,
            4,
            0.0,
            1.0,
            0.0,
            1.0,
            1,
            HexReduce::Mean,
        )
        .unwrap();
        let sum = hexbin(
            &x,
            &y,
            Some(&c),
            4,
            4,
            0.0,
            1.0,
            0.0,
            1.0,
            1,
            HexReduce::Sum,
        )
        .unwrap();
        assert_eq!(mean.counts.len(), sum.counts.len());
        let total_count: f64 = mean.counts.iter().sum();
        assert_eq!(total_count, 3.0);
        let total_sum: f64 = sum.metrics.iter().sum();
        assert!((total_sum - 16.0).abs() < 1e-12);
        for (m, s, n) in mean
            .metrics
            .iter()
            .zip(sum.metrics.iter())
            .zip(mean.counts.iter())
            .map(|((m, s), n)| (m, s, n))
        {
            assert!((m * n - s).abs() < 1e-12);
        }
    }

    #[test]
    fn rejects_mean_without_c_and_bad_grid() {
        assert!(hexbin(
            &[0.0],
            &[0.0],
            None,
            4,
            4,
            0.0,
            1.0,
            0.0,
            1.0,
            0,
            HexReduce::Mean
        )
        .is_none());
        assert!(hexbin(
            &[0.0],
            &[0.0],
            None,
            1,
            4,
            0.0,
            1.0,
            0.0,
            1.0,
            0,
            HexReduce::Count
        )
        .is_none());
    }

    #[test]
    fn mincnt_zero_emits_full_honeycomb_when_points_land() {
        let r = hexbin(
            &[0.5],
            &[0.5],
            None,
            2,
            2,
            0.0,
            1.0,
            0.0,
            1.0,
            0,
            HexReduce::Count,
        )
        .unwrap();
        assert_eq!(r.centers_x.len(), hexbin_capacity(2, 2));
        assert_eq!(r.counts.iter().sum::<f64>(), 1.0);
    }

    #[test]
    fn out_of_range_points_yield_empty_even_with_mincnt_zero() {
        let r = hexbin(
            &[0.0, 0.1],
            &[0.0, 0.1],
            None,
            4,
            4,
            10.0,
            11.0,
            10.0,
            11.0,
            0,
            HexReduce::Count,
        )
        .unwrap();
        assert!(r.centers_x.is_empty());
    }

    #[test]
    fn default_grid_height_matches_matplotlib_truncation() {
        assert_eq!(default_grid_height(2), 2);
        assert_eq!(default_grid_height(5), 2);
        assert_eq!(default_grid_height(16), 9);
        assert_eq!(default_grid_height(64), 36);
        assert_eq!(default_grid_height(100), 57);
        // The former Node `Math.round(5 / √3)` produced 3; Rust keeps int().
        assert_ne!(
            default_grid_height(5),
            ((5.0 / 3.0_f64.sqrt()).round() as usize).max(2)
        );
    }

    #[test]
    fn auto_domain_pads_constant_nonzero_by_five_percent() {
        let (lo, hi) = pad_auto_domain(20.0, 20.0).unwrap();
        assert!((lo - 19.0).abs() < 1e-12);
        assert!((hi - 21.0).abs() < 1e-12);
        let (zlo, zhi) = pad_auto_domain(0.0, 0.0).unwrap();
        assert_eq!((zlo, zhi), (-0.5, 0.5));
    }

    #[test]
    fn ingress_skips_nonfinite_pairs_and_c_then_resolves_auto_policy() {
        let x = [f64::NAN, 10.0, f64::INFINITY, 10.0];
        let y = [0.0, 4.0, 1.0, 4.0];
        let c = [1.0, 2.0, 3.0, f64::NAN];
        let ingress = hexbin_ingress(&x, &y, Some(&c), 16, None, None).unwrap();
        assert_eq!(ingress.grid_w, 16);
        assert_eq!(ingress.grid_h, 9);
        assert!((ingress.x0 - 9.5).abs() < 1e-12);
        assert!((ingress.x1 - 10.5).abs() < 1e-12);
        assert!((ingress.y0 - 3.8).abs() < 1e-12);
        assert!((ingress.y1 - 4.2).abs() < 1e-12);
        assert!(hexbin_ingress(&[f64::NAN], &[1.0], None, 8, None, None).is_none());
        assert!(hexbin_ingress(
            &[1.0],
            &[1.0],
            None,
            8,
            None,
            Some(((1.0, 1.0), (0.0, 1.0)))
        )
        .is_none());
    }

    #[test]
    fn with_policy_auto_matches_explicit_resolved_ingress() {
        let x = [0.0, 1.0, f64::NAN];
        let y = [2.0, 3.0, 4.0];
        let auto = hexbin_with_policy(&x, &y, None, 8, None, None, 1, HexReduce::Count).unwrap();
        let ingress = hexbin_ingress(&x, &y, None, 8, None, None).unwrap();
        let explicit = hexbin(
            &x,
            &y,
            None,
            ingress.grid_w,
            ingress.grid_h,
            ingress.x0,
            ingress.x1,
            ingress.y0,
            ingress.y1,
            1,
            HexReduce::Count,
        )
        .unwrap();
        assert_eq!(auto.centers_x, explicit.centers_x);
        assert_eq!(auto.centers_y, explicit.centers_y);
        assert_eq!(auto.counts, explicit.counts);
        assert_eq!(auto.dx, explicit.dx);
        assert_eq!(auto.dy, explicit.dy);
    }
}
