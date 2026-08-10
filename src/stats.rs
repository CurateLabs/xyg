//! Quantiles, Tukey box-plot statistics, violin density, and histogram edges.
//!
//! Hosts assemble geometry from these numbers; the rank math stays in Rust so
//! Python and Node share one implementation
//! ([host-parity.md](../../spec/design/host-parity.md), rust-engine §6).

/// Fixed 5-tap smooth kernel used by the violin mark (Python legacy defaults).
const VIOLIN_KERNEL: [f64; 5] = [1.0, 2.0, 3.0, 2.0, 1.0];

/// Violin density: histogram + coverage-normalized convolution.
#[derive(Clone, Debug, PartialEq)]
pub struct ViolinDensity {
    pub edges: Vec<f64>,
    pub density: Vec<f64>,
}

/// Histogram edge estimator. `Auto` matches NumPy's `bins="auto"`.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
#[repr(i32)]
pub enum HistogramEdgesMethod {
    /// NumPy `bins="auto"`: `min(max(fd, sqrt/2), sturges)` bandwidths.
    Auto = 0,
    /// NumPy `bins="sturges"`: `ptp / (log2(n) + 1)`.
    Sturges = 1,
}

impl HistogramEdgesMethod {
    pub fn from_i32(v: i32) -> Option<Self> {
        match v {
            0 => Some(Self::Auto),
            1 => Some(Self::Sturges),
            _ => None,
        }
    }
}

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

/// Bounded-resolution violin density matching the prior NumPy path.
///
/// Builds a uniform histogram over `[lo, hi]` (auto from finite samples when
/// both bounds are non-finite), convolves with `[1,2,3,2,1]` in `same` mode,
/// and divides by the truncated-kernel coverage so edge bins keep full weight.
/// `n_bins` must be in `4..=1024`. Returns `None` when there is no finite
/// sample or `n_bins` is out of range.
pub fn violin_density(data: &[f64], n_bins: usize) -> Option<ViolinDensity> {
    if !(4..=1024).contains(&n_bins) {
        return None;
    }
    let finite: Vec<f64> = data.iter().copied().filter(|v| v.is_finite()).collect();
    if finite.is_empty() {
        return None;
    }
    let mut lo = finite.iter().copied().fold(f64::INFINITY, f64::min);
    let mut hi = finite.iter().copied().fold(f64::NEG_INFINITY, f64::max);
    if lo == hi {
        lo -= 0.5;
        hi += 0.5;
    }
    let width = (hi - lo) / n_bins as f64;
    let mut counts = vec![0.0f64; n_bins];
    for &v in &finite {
        let mut bin = ((v - lo) / width).floor() as isize;
        if v == hi {
            bin = n_bins as isize - 1;
        }
        if bin >= 0 && (bin as usize) < n_bins {
            counts[bin as usize] += 1.0;
        }
    }
    let mut coverage = vec![0.0f64; n_bins];
    let ones = vec![1.0f64; n_bins];
    convolve_same(&ones, &VIOLIN_KERNEL, &mut coverage);
    let mut density = vec![0.0f64; n_bins];
    convolve_same(&counts, &VIOLIN_KERNEL, &mut density);
    for i in 0..n_bins {
        density[i] /= coverage[i];
    }
    let mut edges = Vec::with_capacity(n_bins + 1);
    for i in 0..=n_bins {
        edges.push(lo + i as f64 * width);
    }
    // Match np.linspace endpoint exactly.
    edges[n_bins] = hi;
    Some(ViolinDensity { edges, density })
}

/// NumPy-style `mode="same"` convolution into `out` (len = signal len).
fn convolve_same(signal: &[f64], kernel: &[f64], out: &mut [f64]) {
    debug_assert_eq!(signal.len(), out.len());
    let k = kernel.len();
    let mid = k / 2;
    for i in 0..signal.len() {
        let mut acc = 0.0;
        for (j, &kv) in kernel.iter().enumerate() {
            let s = i as isize + j as isize - mid as isize;
            if s >= 0 && (s as usize) < signal.len() {
                acc += signal[s as usize] * kv;
            }
        }
        out[i] = acc;
    }
}

/// Uniform histogram edges via Sturges or NumPy `bins="auto"`.
///
/// When `range` is `None`, outer edges come from the finite sample min/max
/// (empty → `[0, 1]`; constant → expand by ±0.5). When `range` is `Some`,
/// estimators use only samples inside that interval. Returns `None` on a
/// non-increasing or non-finite explicit range.
pub fn histogram_edges(
    data: &[f64],
    range: Option<(f64, f64)>,
    method: HistogramEdgesMethod,
) -> Option<Vec<f64>> {
    let (first_edge, last_edge, trimmed) = outer_edges(data, range)?;
    let n_bins = if trimmed.is_empty() {
        1
    } else {
        let width = match method {
            HistogramEdgesMethod::Sturges => sturges_width(&trimmed),
            HistogramEdgesMethod::Auto => auto_width(&trimmed),
        };
        if width > 0.0 {
            let delta = last_edge - first_edge;
            let n = (delta / width).ceil() as usize;
            n.max(1)
        } else {
            1
        }
    };
    let mut edges = Vec::with_capacity(n_bins + 1);
    let width = (last_edge - first_edge) / n_bins as f64;
    for i in 0..=n_bins {
        edges.push(first_edge + i as f64 * width);
    }
    edges[n_bins] = last_edge;
    Some(edges)
}

fn outer_edges(data: &[f64], range: Option<(f64, f64)>) -> Option<(f64, f64, Vec<f64>)> {
    let finite: Vec<f64> = data.iter().copied().filter(|v| v.is_finite()).collect();
    let (mut first, mut last) = if let Some((lo, hi)) = range {
        if !(lo.is_finite() && hi.is_finite()) || hi < lo {
            return None;
        }
        (lo, hi)
    } else if finite.is_empty() {
        (0.0, 1.0)
    } else {
        let lo = finite.iter().copied().fold(f64::INFINITY, f64::min);
        let hi = finite.iter().copied().fold(f64::NEG_INFINITY, f64::max);
        (lo, hi)
    };
    if first == last {
        first -= 0.5;
        last += 0.5;
    }
    let trimmed: Vec<f64> = if range.is_some() {
        finite
            .into_iter()
            .filter(|&v| v >= first && v <= last)
            .collect()
    } else {
        finite
    };
    Some((first, last, trimmed))
}

fn ptp(data: &[f64]) -> f64 {
    let lo = data.iter().copied().fold(f64::INFINITY, f64::min);
    let hi = data.iter().copied().fold(f64::NEG_INFINITY, f64::max);
    hi - lo
}

fn sturges_width(data: &[f64]) -> f64 {
    ptp(data) / ((data.len() as f64).log2() + 1.0)
}

fn fd_width(data: &[f64]) -> f64 {
    let mut sorted = data.to_vec();
    sorted.sort_by(|a, b| a.partial_cmp(b).unwrap_or(std::cmp::Ordering::Equal));
    let q1 = quantile_sorted(&sorted, 0.25);
    let q3 = quantile_sorted(&sorted, 0.75);
    2.0 * (q3 - q1) * (data.len() as f64).powf(-1.0 / 3.0)
}

fn sqrt_width(data: &[f64]) -> f64 {
    ptp(data) / (data.len() as f64).sqrt()
}

/// NumPy `_hist_bin_auto`: `min(max(fd, sqrt/2), sturges)` bandwidths.
fn auto_width(data: &[f64]) -> f64 {
    let fd = fd_width(data);
    let sturges = sturges_width(data);
    let sqrt = sqrt_width(data);
    let fd_corrected = fd.max(sqrt / 2.0);
    fd_corrected.min(sturges)
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

    #[test]
    fn violin_density_matches_python_kernel_fixture() {
        let data: Vec<f64> = (0..20).map(|i| i as f64).collect();
        let got = violin_density(&data, 8).unwrap();
        assert_eq!(got.edges.len(), 9);
        assert_eq!(got.density.len(), 8);
        // Coverage-normalized smooth: peak interior, no edge pinch to zero.
        assert!(got.density[0] > 0.0);
        assert!(got.density[7] > 0.0);
        let peak = got.density.iter().copied().fold(0.0_f64, f64::max);
        assert!(peak > 0.0);
        // Constant data expands the span by ±0.5.
        let c = violin_density(&[3.0, 3.0, 3.0], 4).unwrap();
        assert!((c.edges[0] - 2.5).abs() < 1e-12);
        assert!((c.edges[4] - 3.5).abs() < 1e-12);
        assert!(violin_density(&[], 8).is_none());
        assert!(violin_density(&[1.0], 3).is_none());
    }

    #[test]
    fn histogram_edges_auto_matches_numpy_fixture() {
        let data: Vec<f64> = (1..=10).map(|i| i as f64).collect();
        let edges = histogram_edges(&data, None, HistogramEdgesMethod::Auto).unwrap();
        assert_eq!(edges.len(), 6); // 5 bins
        assert!((edges[0] - 1.0).abs() < 1e-12);
        assert!((edges[5] - 10.0).abs() < 1e-12);
        let sturges = histogram_edges(&data, None, HistogramEdgesMethod::Sturges).unwrap();
        assert_eq!(sturges.len(), edges.len());
        // Empty without range → single bin over [0, 1] (NumPy auto).
        let empty = histogram_edges(&[], None, HistogramEdgesMethod::Auto).unwrap();
        assert_eq!(empty, vec![0.0, 1.0]);
    }
}
