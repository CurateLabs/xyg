//! Quantiles and Tukey box-plot statistics.
//!
//! Hosts assemble geometry from these numbers; the rank math stays in Rust so
//! Python and Node share one implementation
//! ([host-parity.md](../../spec/design/host-parity.md), rust-engine §6).

/// Tukey box-plot summary: quartiles, observation-clipped whiskers, outliers.
#[derive(Clone, Debug, PartialEq)]
pub struct BoxStats {
    pub q1: f64,
    pub median: f64,
    pub q3: f64,
    pub low: f64,
    pub high: f64,
    pub outliers: Vec<f64>,
}

/// Linear (NumPy default) quantiles for probabilities in `[0, 1]`.
///
/// Non-finite samples are skipped. Empty finite input yields `NaN` for every
/// probability. Invalid probabilities (non-finite or outside `[0, 1]`) return
/// `None`.
pub fn quantiles(data: &[f64], probs: &[f64]) -> Option<Vec<f64>> {
    for &p in probs {
        if !p.is_finite() || !(0.0..=1.0).contains(&p) {
            return None;
        }
    }
    let mut finite: Vec<f64> = data.iter().copied().filter(|v| v.is_finite()).collect();
    if finite.is_empty() {
        return Some(vec![f64::NAN; probs.len()]);
    }
    finite.sort_by(|a, b| a.partial_cmp(b).unwrap_or(std::cmp::Ordering::Equal));
    Some(
        probs
            .iter()
            .map(|&p| quantile_sorted(&finite, p))
            .collect(),
    )
}

/// Linear interpolation on a non-empty ascending finite slice.
fn quantile_sorted(sorted: &[f64], p: f64) -> f64 {
    debug_assert!(!sorted.is_empty());
    debug_assert!((0.0..=1.0).contains(&p));
    let n = sorted.len();
    if n == 1 {
        return sorted[0];
    }
    let pos = (n - 1) as f64 * p;
    let lo = pos.floor() as usize;
    let hi = pos.ceil() as usize;
    if lo == hi {
        return sorted[lo];
    }
    let frac = pos - lo as f64;
    sorted[lo] * (1.0 - frac) + sorted[hi] * frac
}

/// Tukey hinges: Q1/median/Q3, whiskers at extreme observations inside the
/// 1.5·IQR fences, and outliers beyond those whiskers.
///
/// Matches `python/xy/marks._distribution_stats` (prior NumPy percentile path).
pub fn box_stats(data: &[f64]) -> BoxStats {
    let mut finite: Vec<f64> = data.iter().copied().filter(|v| v.is_finite()).collect();
    if finite.is_empty() {
        return BoxStats {
            q1: f64::NAN,
            median: f64::NAN,
            q3: f64::NAN,
            low: f64::NAN,
            high: f64::NAN,
            outliers: Vec::new(),
        };
    }
    finite.sort_by(|a, b| a.partial_cmp(b).unwrap_or(std::cmp::Ordering::Equal));
    let q1 = quantile_sorted(&finite, 0.25);
    let median = quantile_sorted(&finite, 0.5);
    let q3 = quantile_sorted(&finite, 0.75);
    let iqr = q3 - q1;
    let lo_fence = q1 - 1.5 * iqr;
    let hi_fence = q3 + 1.5 * iqr;
    // Whiskers end at the most extreme observation inside the fence (not the
    // bare fence). Both selections are non-empty for finite data: min ≤ q1 and
    // q3 ≤ max always hold for linear quartiles on the same sample.
    let low = finite
        .iter()
        .copied()
        .filter(|&v| v >= lo_fence)
        .fold(f64::INFINITY, f64::min);
    let high = finite
        .iter()
        .copied()
        .filter(|&v| v <= hi_fence)
        .fold(f64::NEG_INFINITY, f64::max);
    let outliers: Vec<f64> = finite
        .iter()
        .copied()
        .filter(|&v| v < low || v > high)
        .collect();
    BoxStats {
        q1,
        median,
        q3,
        low,
        high,
        outliers,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn quantiles_match_numpy_linear_fixture() {
        let data = [0.0, 10.0, 11.0, 12.0, 13.0, 14.0, 40.0];
        let q = quantiles(&data, &[0.25, 0.5, 0.75]).unwrap();
        assert!((q[0] - 10.5).abs() < 1e-12);
        assert!((q[1] - 12.0).abs() < 1e-12);
        assert!((q[2] - 13.5).abs() < 1e-12);
    }

    #[test]
    fn quantiles_skip_non_finite_and_reject_bad_probs() {
        let data = [1.0, f64::NAN, 3.0, f64::INFINITY, 5.0];
        let q = quantiles(&data, &[0.0, 1.0]).unwrap();
        assert_eq!(q[0], 1.0);
        assert_eq!(q[1], 5.0);
        assert!(quantiles(&data, &[f64::NAN]).is_none());
        assert!(quantiles(&data, &[-0.1]).is_none());
        assert!(quantiles(&data, &[1.1]).is_none());
    }

    #[test]
    fn empty_quantiles_are_nan() {
        let q = quantiles(&[], &[0.5]).unwrap();
        assert!(q[0].is_nan());
        let q = quantiles(&[f64::NAN], &[0.25, 0.75]).unwrap();
        assert!(q.iter().all(|v| v.is_nan()));
    }

    #[test]
    fn box_stats_tukey_whiskers_and_outliers() {
        let data = [0.0, 10.0, 11.0, 12.0, 13.0, 14.0, 40.0];
        let s = box_stats(&data);
        assert!((s.q1 - 10.5).abs() < 1e-12);
        assert!((s.median - 12.0).abs() < 1e-12);
        assert!((s.q3 - 13.5).abs() < 1e-12);
        let iqr = s.q3 - s.q1;
        let inside: Vec<f64> = data
            .iter()
            .copied()
            .filter(|&v| v >= s.q1 - 1.5 * iqr && v <= s.q3 + 1.5 * iqr)
            .collect();
        assert_eq!(s.low, inside.iter().copied().fold(f64::INFINITY, f64::min));
        assert_eq!(
            s.high,
            inside.iter().copied().fold(f64::NEG_INFINITY, f64::max)
        );
        assert_eq!(s.low, 10.0);
        assert_eq!(s.high, 14.0);
        assert_eq!(s.outliers, vec![0.0, 40.0]);
    }

    #[test]
    fn box_stats_empty_is_nan() {
        let s = box_stats(&[]);
        assert!(s.q1.is_nan() && s.outliers.is_empty());
    }
}
