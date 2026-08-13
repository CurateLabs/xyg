//! Hexagonal binning (matplotlib-compatible lattice assignment).
//!
//! Two overlapping lattices — an integer grid and a half-cell offset grid —
//! compete in the hex metric; each finite point joins the nearer center.
//! Hosts assemble color/geometry from the occupied cells
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

/// Bin `(x, y)` into a matplotlib-style hex lattice.
///
/// `mincnt` keeps cells with `count >= mincnt`. When `C` is absent the metric
/// equals the count; when present, `reduce` must be [`HexReduce::Mean`] or
/// [`HexReduce::Sum`]. Non-finite coordinates (and non-finite `C` when provided)
/// are skipped. Returns `None` on invalid arguments (bad grid, non-increasing
/// range, mean/sum without `C`).
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
    if grid_w < 2 || grid_h < 2 || grid_w > MAX_GRID || grid_h > MAX_GRID {
        return None;
    }
    if !(x0.is_finite() && x1.is_finite() && y0.is_finite() && y1.is_finite()) || !(x1 > x0 && y1 > y0)
    {
        return None;
    }
    match reduce {
        HexReduce::Count => {}
        HexReduce::Mean | HexReduce::Sum => {
            if c.is_none() {
                return None;
            }
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
            if ix1 >= 0
                && iy1 >= 0
                && (ix1 as usize) <= grid_w
                && (iy1 as usize) <= grid_h
            {
                let flat = (iy1 as usize) * (grid_w + 1) + (ix1 as usize);
                count1[flat] += 1;
                if let Some(v) = cv {
                    sum1[flat] += v;
                }
                assigned += 1;
            }
        } else if ix2 >= 0
            && iy2 >= 0
            && (ix2 as usize) < grid_w
            && (iy2 as usize) < grid_h
        {
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
        let r = hexbin(
            &x,
            &y,
            None,
            4,
            4,
            0.0,
            1.0,
            0.0,
            1.0,
            1,
            HexReduce::Count,
        )
        .unwrap();
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
        assert!(hexbin(&[0.0], &[0.0], None, 4, 4, 0.0, 1.0, 0.0, 1.0, 0, HexReduce::Mean).is_none());
        assert!(hexbin(&[0.0], &[0.0], None, 1, 4, 0.0, 1.0, 0.0, 1.0, 0, HexReduce::Count).is_none());
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
}
