//! Quantiles, Tukey box-plot statistics, violin density, histogram edges, and
//! wind-rose directional/speed binning.
//!
//! Hosts assemble geometry from these numbers; the rank math stays in Rust so
//! Python and Node share one implementation
//! ([host-parity.md](../../spec/design/host-parity.md), rust-engine §6).

use crate::kernels;

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

/// Maximum number of uniform histogram bins produced by automatic edge resolution.
pub const MAX_HISTOGRAM_BINS: usize = 10_000;

/// Compact right-continuous coordinates for a uniformly binned ECDF.
#[derive(Clone, Debug, PartialEq)]
pub struct BinnedEcdf {
    pub x: Vec<f64>,
    pub cumulative: Vec<f64>,
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
    Some(probs.iter().map(|&p| quantile_sorted(&finite, p)).collect())
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
/// Matches `python/xyg/marks._distribution_stats` (prior NumPy percentile path).
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

/// Maximum combined grouped-box output rows. Each active group charges one
/// body, three whisker/cap segments, one median, and every statistical outlier.
pub const MAX_BOX_GEOMETRY_ROWS: usize = 10_000;

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum BoxOrientation {
    Vertical,
    Horizontal,
}

#[derive(Clone, Debug, PartialEq)]
pub struct GroupedBoxGeometry {
    pub active_groups: Vec<usize>,
    /// Group-major `[q1, median, q3, low, high]`.
    pub stats: Vec<f64>,
    /// Group-major offsets into `outlier_values` and the optional position planes.
    pub outlier_offsets: Vec<usize>,
    pub outlier_values: Vec<f64>,
    pub body_x0: Vec<f64>,
    pub body_y0: Vec<f64>,
    pub body_x1: Vec<f64>,
    pub body_y1: Vec<f64>,
    pub whisker_x0: Vec<f64>,
    pub whisker_y0: Vec<f64>,
    pub whisker_x1: Vec<f64>,
    pub whisker_y1: Vec<f64>,
    pub median_x0: Vec<f64>,
    pub median_y0: Vec<f64>,
    pub median_x1: Vec<f64>,
    pub median_y1: Vec<f64>,
    pub outlier_x: Vec<f64>,
    pub outlier_y: Vec<f64>,
}

fn box_outlier_jitter(group: usize, index: usize, width: f64) -> f64 {
    // SplitMix64 is used only as a deterministic coordinate mixer. Group and
    // within-group index make placement independent of host RNG state.
    let mut z = (group as u64)
        .wrapping_mul(0x9e37_79b9_7f4a_7c15)
        .wrapping_add(index as u64)
        .wrapping_add(0x9e37_79b9_7f4a_7c15);
    z = (z ^ (z >> 30)).wrapping_mul(0xbf58_476d_1ce4_e5b9);
    z = (z ^ (z >> 27)).wrapping_mul(0x94d0_49bb_1331_11eb);
    z ^= z >> 31;
    let unit = (z >> 11) as f64 * (1.0 / ((1_u64 << 53) as f64));
    (unit * 2.0 - 1.0) * width * 0.12
}

/// Compile grouped canonical samples into ordinary Scene body, whisker/cap,
/// median, and optional outlier geometry. Hosts retain coercion, category
/// factorization, literal styles, and trace assembly only.
pub fn grouped_box_geometry(
    values: &[f64],
    offsets: &[usize],
    centers: &[f64],
    width: f64,
    orientation: BoxOrientation,
    show_outliers: bool,
) -> Option<GroupedBoxGeometry> {
    if offsets.len() != centers.len().checked_add(1)?
        || offsets.first() != Some(&0)
        || offsets.last() != Some(&values.len())
        || offsets.windows(2).any(|pair| pair[0] > pair[1])
        || centers.iter().any(|value| !value.is_finite())
        || !width.is_finite()
        || width <= 0.0
    {
        return None;
    }
    let mut out = GroupedBoxGeometry {
        active_groups: vec![],
        stats: vec![],
        outlier_offsets: vec![0],
        outlier_values: vec![],
        body_x0: vec![],
        body_y0: vec![],
        body_x1: vec![],
        body_y1: vec![],
        whisker_x0: vec![],
        whisker_y0: vec![],
        whisker_x1: vec![],
        whisker_y1: vec![],
        median_x0: vec![],
        median_y0: vec![],
        median_x1: vec![],
        median_y1: vec![],
        outlier_x: vec![],
        outlier_y: vec![],
    };
    for (group, (&start, &end)) in offsets.iter().zip(&offsets[1..]).enumerate() {
        let stats = box_stats(values.get(start..end)?);
        if !stats.q1.is_finite() {
            continue;
        }
        let next_rows = out
            .active_groups
            .len()
            .checked_add(1)?
            .checked_mul(5)?
            .checked_add(out.outlier_values.len())?
            .checked_add(stats.outliers.len())?;
        if next_rows > MAX_BOX_GEOMETRY_ROWS {
            return None;
        }
        let center = centers[group];
        let half = width * 0.5;
        let cap = width * 0.3;
        let (body, whiskers, median) = match orientation {
            BoxOrientation::Vertical => (
                (center - half, stats.q1, center + half, stats.q3),
                [
                    (center, stats.low, center, stats.high),
                    (center - cap, stats.low, center + cap, stats.low),
                    (center - cap, stats.high, center + cap, stats.high),
                ],
                (center - half, stats.median, center + half, stats.median),
            ),
            BoxOrientation::Horizontal => (
                (stats.q1, center - half, stats.q3, center + half),
                [
                    (stats.low, center, stats.high, center),
                    (stats.low, center - cap, stats.low, center + cap),
                    (stats.high, center - cap, stats.high, center + cap),
                ],
                (stats.median, center - half, stats.median, center + half),
            ),
        };
        let coordinates = [
            body.0,
            body.1,
            body.2,
            body.3,
            median.0,
            median.1,
            median.2,
            median.3,
            whiskers[0].0,
            whiskers[0].1,
            whiskers[0].2,
            whiskers[0].3,
            whiskers[1].0,
            whiskers[1].1,
            whiskers[1].2,
            whiskers[1].3,
            whiskers[2].0,
            whiskers[2].1,
            whiskers[2].2,
            whiskers[2].3,
        ];
        if coordinates.iter().any(|value| !value.is_finite()) {
            return None;
        }
        out.active_groups.push(group);
        out.stats
            .extend_from_slice(&[stats.q1, stats.median, stats.q3, stats.low, stats.high]);
        out.body_x0.push(body.0);
        out.body_y0.push(body.1);
        out.body_x1.push(body.2);
        out.body_y1.push(body.3);
        for segment in whiskers {
            out.whisker_x0.push(segment.0);
            out.whisker_y0.push(segment.1);
            out.whisker_x1.push(segment.2);
            out.whisker_y1.push(segment.3);
        }
        out.median_x0.push(median.0);
        out.median_y0.push(median.1);
        out.median_x1.push(median.2);
        out.median_y1.push(median.3);
        for (index, value) in stats.outliers.iter().copied().enumerate() {
            out.outlier_values.push(value);
            if show_outliers {
                let jitter = box_outlier_jitter(group, index, width);
                let (x, y) = match orientation {
                    BoxOrientation::Vertical => (center + jitter, value),
                    BoxOrientation::Horizontal => (value, center + jitter),
                };
                if !x.is_finite() || !y.is_finite() {
                    return None;
                }
                out.outlier_x.push(x);
                out.outlier_y.push(y);
            }
        }
        out.outlier_offsets.push(out.outlier_values.len());
    }
    (!out.active_groups.is_empty()).then_some(out)
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

pub const MAX_VIOLIN_RECTS: usize = 10_000;

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum ViolinOrientation {
    Vertical,
    Horizontal,
}

#[derive(Clone, Debug, PartialEq)]
pub struct ViolinRects {
    pub x0: Vec<f64>,
    pub y0: Vec<f64>,
    pub x1: Vec<f64>,
    pub y1: Vec<f64>,
    pub active_groups: Vec<usize>,
    pub edges: Vec<f64>,
    pub density: Vec<f64>,
}

/// Compile grouped canonical samples into bounded ordinary Scene Rect geometry.
/// Hosts retain only coercion/factorization; density normalization, orientation,
/// width policy, empty-group handling, and final coordinates are Rust-owned.
pub fn violin_rects(
    values: &[f64],
    offsets: &[usize],
    centers: &[f64],
    bins: usize,
    width: f64,
    orientation: ViolinOrientation,
) -> Option<ViolinRects> {
    if offsets.len() != centers.len().checked_add(1)?
        || offsets.first() != Some(&0)
        || offsets.last() != Some(&values.len())
        || offsets.windows(2).any(|p| p[0] > p[1])
        || centers.iter().any(|v| !v.is_finite())
        || !width.is_finite()
        || width <= 0.0
        || !(4..=1024).contains(&bins)
    {
        return None;
    }
    let mut out = ViolinRects {
        x0: vec![],
        y0: vec![],
        x1: vec![],
        y1: vec![],
        active_groups: vec![],
        edges: vec![],
        density: vec![],
    };
    for (group, (&start, &end)) in offsets.iter().zip(&offsets[1..]).enumerate() {
        let result = match violin_density(values.get(start..end)?, bins) {
            Some(v) => v,
            None => continue,
        };
        if out.x0.len().checked_add(bins)? > MAX_VIOLIN_RECTS {
            return None;
        }
        let peak = result.density.iter().copied().fold(0.0, f64::max);
        let peak = if peak == 0.0 { 1.0 } else { peak };
        out.active_groups.push(group);
        out.edges.extend_from_slice(&result.edges);
        out.density.extend_from_slice(&result.density);
        for i in 0..bins {
            let half = width * 0.5 * result.density[i] / peak;
            let (x0, y0, x1, y1) = match orientation {
                ViolinOrientation::Vertical => (
                    centers[group] - half,
                    result.edges[i],
                    centers[group] + half,
                    result.edges[i + 1],
                ),
                ViolinOrientation::Horizontal => (
                    result.edges[i],
                    centers[group] - half,
                    result.edges[i + 1],
                    centers[group] + half,
                ),
            };
            if [x0, y0, x1, y1].iter().any(|v| !v.is_finite()) {
                return None;
            }
            out.x0.push(x0);
            out.y0.push(y0);
            out.x1.push(x1);
            out.y1.push(y1);
        }
    }
    (!out.active_groups.is_empty()).then_some(out)
}

/// NumPy-style `mode="same"` convolution into `out` (len = signal len).
#[allow(clippy::needless_range_loop)] // i indexes signal and out with a signed kernel offset
fn convolve_same(signal: &[f64], kernel: &[f64], out: &mut [f64]) {
    debug_assert_eq!(signal.len(), out.len());
    let k = kernel.len();
    let mid = k / 2;
    for (i, dest) in out.iter_mut().enumerate() {
        let mut acc = 0.0;
        for (j, &kv) in kernel.iter().enumerate() {
            let s = i as isize + j as isize - mid as isize;
            if s >= 0 && (s as usize) < signal.len() {
                acc += signal[s as usize] * kv;
            }
        }
        *dest = acc;
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
    if n_bins > MAX_HISTOGRAM_BINS {
        return None;
    }
    let mut edges = Vec::with_capacity(n_bins + 1);
    let width = (last_edge - first_edge) / n_bins as f64;
    for i in 0..=n_bins {
        edges.push(first_edge + i as f64 * width);
    }
    edges[n_bins] = last_edge;
    Some(edges)
}

/// Uniformly binned ECDF coordinates with a zero anchor and occupied-bin
/// right edges. Non-finite samples are ignored. An authored range preserves
/// the host contract by normalizing in-range mass over every finite sample.
pub fn binned_ecdf(data: &[f64], n_bins: usize, range: Option<(f64, f64)>) -> Option<BinnedEcdf> {
    if data.is_empty() || n_bins == 0 || n_bins > MAX_HISTOGRAM_BINS {
        return None;
    }
    let mut finite_count = 0u64;
    let mut finite_lo = f64::INFINITY;
    let mut finite_hi = f64::NEG_INFINITY;
    for &value in data {
        if value.is_finite() {
            finite_count += 1;
            finite_lo = finite_lo.min(value);
            finite_hi = finite_hi.max(value);
        }
    }
    if finite_count == 0 {
        return None;
    }
    let (lo, hi) = if let Some((lo, hi)) = range {
        if !(lo.is_finite() && hi.is_finite() && hi > lo && (hi - lo).is_finite()) {
            return None;
        }
        (lo, hi)
    } else if finite_lo == finite_hi {
        let mut pad = finite_lo.abs() * 0.05;
        let mut lo = finite_lo - pad;
        let mut hi = finite_hi + pad;
        if !(pad.is_finite() && pad > 0.0 && lo < finite_lo && hi > finite_hi) {
            pad = 0.5;
            lo = finite_lo - pad;
            hi = finite_hi + pad;
        }
        if !(lo.is_finite() && hi.is_finite() && hi > lo && (hi - lo).is_finite()) {
            return None;
        }
        (lo, hi)
    } else {
        if !(finite_hi > finite_lo && (finite_hi - finite_lo).is_finite()) {
            return None;
        }
        (finite_lo, finite_hi)
    };

    let scale = n_bins as f64 / (hi - lo);
    if !(scale.is_finite() && scale > 0.0) {
        return None;
    }
    let mut counts = vec![0.0; n_bins];
    kernels::histogram_uniform(data, lo, hi, &mut counts);
    let width = (hi - lo) / n_bins as f64;
    if !(width.is_finite() && width > 0.0) {
        return None;
    }
    let mut x = Vec::with_capacity(n_bins + 1);
    let mut cumulative = Vec::with_capacity(n_bins + 1);
    x.push(lo);
    cumulative.push(0.0);
    let mut acc = 0.0;
    for (index, count) in counts.into_iter().enumerate() {
        acc += count;
        if count > 0.0 {
            let right = if index + 1 == n_bins {
                hi
            } else {
                lo + (index + 1) as f64 * width
            };
            if !right.is_finite() || right <= *x.last().unwrap_or(&lo) {
                return None;
            }
            x.push(right);
            cumulative.push(acc / finite_count as f64);
        }
    }
    Some(BinnedEcdf { x, cumulative })
}

/// Integrate histogram bin heights into a left-to-right cumulative series.
///
/// Count heights accumulate directly. Density heights integrate each bin's
/// density times its authored width, yielding empirical cumulative mass.
/// Validation completes before `out` is touched so callers never observe a
/// partial series.
pub fn histogram_cumulative_into(
    heights: &[f64],
    edges: &[f64],
    density: bool,
    out: &mut [f64],
) -> bool {
    if heights.is_empty()
        || out.len() != heights.len()
        || edges.len() != heights.len().saturating_add(1)
    {
        return false;
    }

    let mut cumulative = 0.0;
    for (index, &height) in heights.iter().enumerate() {
        let lo = edges[index];
        let hi = edges[index + 1];
        if !(height.is_finite() && height >= 0.0 && lo.is_finite() && hi.is_finite() && hi > lo) {
            return false;
        }
        let contribution = if density {
            let width = hi - lo;
            if !(width.is_finite() && width > 0.0) {
                return false;
            }
            height * width
        } else {
            height
        };
        cumulative += contribution;
        if !contribution.is_finite() || !cumulative.is_finite() {
            return false;
        }
    }

    cumulative = 0.0;
    for (index, (&height, value)) in heights.iter().zip(out.iter_mut()).enumerate() {
        let contribution = if density {
            height * (edges[index + 1] - edges[index])
        } else {
            height
        };
        cumulative += contribution;
        *value = cumulative;
    }
    true
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

/// Maximum angular sectors accepted by [`wind_rose_bins`] (0.1° bins).
pub const WIND_ROSE_MAX_SECTORS: usize = 3600;
/// Maximum speed-band upper edges accepted by [`wind_rose_bins`].
pub const WIND_ROSE_MAX_EDGES: usize = 256;

/// Sector centres + per-band counts for a wind rose.
///
/// `counts` is row-major `[band][sector]` with length `edges.len() * centres.len()`.
/// Hosts assemble stacked polar bars; this kernel only bins
/// ([polar-axes.md](../../spec/design/polar-axes.md)).
#[derive(Clone, Debug, PartialEq)]
pub struct WindRoseBins {
    pub edges: Vec<f64>,
    pub centres: Vec<f64>,
    pub counts: Vec<f64>,
    pub n_obs: usize,
}

/// Bin compass bearings (degrees) and speeds into sector × speed-band counts.
///
/// When `speed_edges` is `None`, quartile upper edges are derived from the
/// finite speeds (3-significant-figure rounding, top edge ceiled to cover the
/// fastest observation — matching the Python `xyg.wind_rose` factory). When
/// `Some`, edges are uniqued/sorted and must be finite with the top edge at
/// least the fastest finite speed. Directions use north-zero, clockwise sector
/// centres: a bearing of 0 belongs to the sector centred on north.
///
/// Returns `None` on length mismatch, `sectors` outside `3..=WIND_ROSE_MAX_SECTORS`,
/// no finite observations, empty/invalid authored edges, or too many edges.
pub fn wind_rose_bins(
    directions: &[f64],
    speeds: &[f64],
    sectors: usize,
    speed_edges: Option<&[f64]>,
) -> Option<WindRoseBins> {
    if directions.len() != speeds.len() {
        return None;
    }
    if !(3..=WIND_ROSE_MAX_SECTORS).contains(&sectors) {
        return None;
    }
    let mut bearings = Vec::with_capacity(directions.len());
    let mut magnitudes = Vec::with_capacity(speeds.len());
    for (&d, &s) in directions.iter().zip(speeds.iter()) {
        if d.is_finite() && s.is_finite() {
            bearings.push(d);
            magnitudes.push(s);
        }
    }
    if bearings.is_empty() {
        return None;
    }
    let n_obs = bearings.len();
    let fastest = magnitudes.iter().copied().fold(f64::NEG_INFINITY, f64::max);

    let edges = match speed_edges {
        None => auto_speed_edges(&magnitudes, fastest)?,
        Some(raw) => {
            if raw.is_empty() || raw.len() > WIND_ROSE_MAX_EDGES {
                return None;
            }
            if raw.iter().any(|v| !v.is_finite()) {
                return None;
            }
            let mut edges = raw.to_vec();
            unique_sorted_f64(&mut edges);
            if edges.is_empty() {
                return None;
            }
            if edges[edges.len() - 1] < fastest {
                return None;
            }
            edges
        }
    };
    if edges.is_empty() || edges.len() > WIND_ROSE_MAX_EDGES {
        return None;
    }

    let width = 360.0 / sectors as f64;
    let centres: Vec<f64> = (0..sectors).map(|i| i as f64 * width).collect();
    let n_bands = edges.len();
    let mut counts = vec![0.0f64; n_bands * sectors];
    let half = width * 0.5;
    for (&bearing, &speed) in bearings.iter().zip(magnitudes.iter()) {
        let wrapped = bearing.rem_euclid(360.0);
        let sector = ((wrapped + half) / width).floor() as isize;
        let sector = sector.rem_euclid(sectors as isize) as usize;
        let mut lower = f64::NEG_INFINITY;
        for (band, &upper) in edges.iter().enumerate() {
            if speed > lower && speed <= upper {
                counts[band * sectors + sector] += 1.0;
                break;
            }
            lower = upper;
        }
    }
    Some(WindRoseBins {
        edges,
        centres,
        counts,
        n_obs,
    })
}

/// Quartile upper edges with Python `float(f"{v:.3g}")` rounding and a ceiled top.
fn auto_speed_edges(magnitudes: &[f64], fastest: f64) -> Option<Vec<f64>> {
    let probs = [0.25, 0.5, 0.75, 1.0];
    let quartiles = quantiles(magnitudes, &probs)?;
    let mut edges: Vec<f64> = quartiles.into_iter().map(round_3g).collect();
    unique_sorted_f64(&mut edges);
    if edges.is_empty() {
        return None;
    }
    if fastest > 0.0 {
        let unit = 10f64.powf(fastest.log10().floor() - 2.0);
        if unit.is_finite() && unit > 0.0 {
            let last = edges.len() - 1;
            edges[last] = (fastest / unit).ceil() * unit;
        }
    }
    Some(edges)
}

/// Match Python `float(f"{value:.3g}")` via equivalent `{:.2e}` formatting.
fn round_3g(value: f64) -> f64 {
    if !value.is_finite() || value == 0.0 {
        return value;
    }
    format!("{value:.2e}").parse::<f64>().unwrap_or(value)
}

fn unique_sorted_f64(values: &mut Vec<f64>) {
    values.sort_by(|a, b| a.partial_cmp(b).unwrap_or(std::cmp::Ordering::Equal));
    values.dedup_by(|a, b| a == b);
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
    fn violin_rects_own_group_filter_normalization_orientation_and_bounds() {
        let values = [1.0, f64::NAN, 2.0, f64::INFINITY, 3.0, 4.0];
        let offsets = [0, 3, 4, 6];
        let vertical = violin_rects(
            &values,
            &offsets,
            &[0.0, 1.0, 2.0],
            4,
            0.8,
            ViolinOrientation::Vertical,
        )
        .unwrap();
        assert_eq!(vertical.active_groups, [0, 2]);
        assert_eq!(vertical.x0.len(), 8);
        assert_eq!(vertical.edges.len(), 10);
        assert_eq!(vertical.density.len(), 8);
        assert!(vertical.x0.iter().zip(&vertical.x1).all(|(a, b)| a <= b));
        let horizontal = violin_rects(
            &values,
            &offsets,
            &[0.0, 1.0, 2.0],
            4,
            0.8,
            ViolinOrientation::Horizontal,
        )
        .unwrap();
        assert_eq!(vertical.y0, horizontal.x0);
        assert_eq!(vertical.y1, horizontal.x1);
        assert_eq!(vertical.x0, horizontal.y0);
        assert_eq!(vertical.x1, horizontal.y1);
        assert!(violin_rects(
            &values,
            &[1, 6],
            &[0.0],
            4,
            0.8,
            ViolinOrientation::Vertical
        )
        .is_none());
        assert!(violin_rects(
            &values,
            &[0, 7],
            &[0.0],
            4,
            0.8,
            ViolinOrientation::Vertical
        )
        .is_none());
        assert!(violin_rects(
            &values,
            &[0, 6],
            &[f64::NAN],
            4,
            0.8,
            ViolinOrientation::Vertical
        )
        .is_none());
        assert!(violin_rects(
            &values,
            &[0, 6],
            &[0.0],
            3,
            0.8,
            ViolinOrientation::Vertical
        )
        .is_none());
        assert!(violin_rects(
            &values,
            &[0, 6],
            &[0.0],
            4,
            0.0,
            ViolinOrientation::Vertical
        )
        .is_none());
    }

    #[test]
    fn violin_rects_enforce_the_ten_thousand_record_contract() {
        let groups = MAX_VIOLIN_RECTS / 4;
        let values = vec![1.0; groups];
        let offsets: Vec<usize> = (0..=groups).collect();
        let centers: Vec<f64> = (0..groups).map(|v| v as f64).collect();
        assert_eq!(
            violin_rects(
                &values,
                &offsets,
                &centers,
                4,
                0.8,
                ViolinOrientation::Vertical
            )
            .unwrap()
            .x0
            .len(),
            MAX_VIOLIN_RECTS
        );
        let values = vec![1.0; groups + 1];
        let offsets: Vec<usize> = (0..=groups + 1).collect();
        let centers: Vec<f64> = (0..=groups).map(|v| v as f64).collect();
        assert!(violin_rects(
            &values,
            &offsets,
            &centers,
            4,
            0.8,
            ViolinOrientation::Vertical
        )
        .is_none());
    }

    #[test]
    fn grouped_box_geometry_owns_orientation_order_and_outlier_placement() {
        let values = [1.0, 2.0, 3.0, 100.0, f64::NAN, 4.0, 5.0, 6.0];
        let offsets = [0, 4, 5, 8];
        let centers = [10.0, 20.0, 30.0];
        let vertical = grouped_box_geometry(
            &values,
            &offsets,
            &centers,
            2.0,
            BoxOrientation::Vertical,
            true,
        )
        .unwrap();
        assert_eq!(vertical.active_groups, [0, 2]);
        assert_eq!(vertical.body_x0, [9.0, 29.0]);
        assert_eq!(vertical.whisker_x0.len(), 6);
        assert_eq!(vertical.median_x0.len(), 2);
        assert_eq!(vertical.outlier_offsets, [0, 1, 1]);
        assert_eq!(vertical.outlier_values, [100.0]);
        assert!((9.76..=10.24).contains(&vertical.outlier_x[0]));
        assert_eq!(vertical.outlier_y, [100.0]);
        assert_eq!(
            vertical,
            grouped_box_geometry(
                &values,
                &offsets,
                &centers,
                2.0,
                BoxOrientation::Vertical,
                true,
            )
            .unwrap()
        );

        let horizontal = grouped_box_geometry(
            &values,
            &offsets,
            &centers,
            2.0,
            BoxOrientation::Horizontal,
            true,
        )
        .unwrap();
        assert_eq!(horizontal.body_y0, vertical.body_x0);
        assert_eq!(horizontal.body_y1, vertical.body_x1);
        assert_eq!(horizontal.body_x0, vertical.body_y0);
        assert_eq!(horizontal.body_x1, vertical.body_y1);
        assert_eq!(horizontal.outlier_x, vertical.outlier_y);
        assert_eq!(horizontal.outlier_y, vertical.outlier_x);

        let hidden = grouped_box_geometry(
            &values,
            &offsets,
            &centers,
            2.0,
            BoxOrientation::Vertical,
            false,
        )
        .unwrap();
        assert_eq!(hidden.outlier_values, [100.0]);
        assert!(hidden.outlier_x.is_empty() && hidden.outlier_y.is_empty());
    }

    #[test]
    fn grouped_box_geometry_rejects_malformed_and_overflowing_inputs() {
        let values = [1.0, 2.0];
        for offsets in [&[1, 2][..], &[0, 3][..], &[0, 2, 1][..]] {
            assert!(grouped_box_geometry(
                &values,
                offsets,
                &[0.0],
                0.6,
                BoxOrientation::Vertical,
                true,
            )
            .is_none());
        }
        assert!(grouped_box_geometry(
            &values,
            &[0, 2],
            &[f64::NAN],
            0.6,
            BoxOrientation::Vertical,
            true,
        )
        .is_none());
        assert!(grouped_box_geometry(
            &values,
            &[0, 2],
            &[f64::MAX],
            f64::MAX,
            BoxOrientation::Vertical,
            true,
        )
        .is_none());
        assert!(grouped_box_geometry(
            &values,
            &[0, 2],
            &[0.0],
            0.0,
            BoxOrientation::Vertical,
            true,
        )
        .is_none());
        assert!(grouped_box_geometry(
            &[f64::NAN],
            &[0, 1],
            &[0.0],
            0.6,
            BoxOrientation::Vertical,
            true,
        )
        .is_none());

        let groups = MAX_BOX_GEOMETRY_ROWS / 5;
        let values = vec![1.0; groups];
        let offsets: Vec<usize> = (0..=groups).collect();
        let centers: Vec<f64> = (0..groups).map(|value| value as f64).collect();
        assert!(grouped_box_geometry(
            &values,
            &offsets,
            &centers,
            0.6,
            BoxOrientation::Vertical,
            false,
        )
        .is_some());
        let values = vec![1.0; groups + 1];
        let offsets: Vec<usize> = (0..=groups + 1).collect();
        let centers: Vec<f64> = (0..=groups).map(|value| value as f64).collect();
        assert!(grouped_box_geometry(
            &values,
            &offsets,
            &centers,
            0.6,
            BoxOrientation::Vertical,
            false,
        )
        .is_none());
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

    #[test]
    fn binned_ecdf_filters_compacts_and_anchors_right_edges() {
        let result = binned_ecdf(&[0.0, 0.2, f64::NAN, 0.2, 0.9], 4, None).unwrap();
        assert_eq!(result.x, vec![0.0, 0.225, 0.9]);
        assert_eq!(result.cumulative, vec![0.0, 0.75, 1.0]);

        let constant = binned_ecdf(&[7.0, 7.0], 2, None).unwrap();
        assert_eq!(constant.x, vec![6.65, 7.0]);
        assert_eq!(constant.cumulative, vec![0.0, 1.0]);

        let zero = binned_ecdf(&[0.0], 2, None).unwrap();
        assert_eq!(zero.x, vec![-0.5, 0.5]);
        assert_eq!(zero.cumulative, vec![0.0, 1.0]);

        let tiny_value = f64::from_bits(1);
        let tiny = binned_ecdf(&[tiny_value], 2, None).unwrap();
        assert_eq!(tiny.x, vec![tiny_value - 0.5, tiny_value + 0.5]);
        assert_eq!(tiny.cumulative, vec![0.0, 1.0]);
    }

    #[test]
    fn binned_ecdf_authored_range_uses_all_finite_mass() {
        let result =
            binned_ecdf(&[-1.0, 0.25, 0.75, 2.0, f64::INFINITY], 2, Some((0.0, 1.0))).unwrap();
        assert_eq!(result.x, vec![0.0, 0.5, 1.0]);
        assert_eq!(result.cumulative, vec![0.0, 0.25, 0.5]);

        let outside = binned_ecdf(&[-2.0, 2.0], 4, Some((0.0, 1.0))).unwrap();
        assert_eq!(outside.x, vec![0.0]);
        assert_eq!(outside.cumulative, vec![0.0]);
    }

    #[test]
    fn histogram_cumulative_integrates_counts_and_variable_width_density() {
        let mut counts = [-1.0; 3];
        assert!(histogram_cumulative_into(
            &[2.0, 1.0, 1.0],
            &[0.0, 1.0, 2.0, 3.0],
            false,
            &mut counts,
        ));
        assert_eq!(counts, [2.0, 3.0, 4.0]);

        let mut density = [-1.0; 2];
        assert!(histogram_cumulative_into(
            &[0.5, 0.25],
            &[0.0, 1.0, 3.0],
            true,
            &mut density,
        ));
        assert_eq!(density, [0.5, 1.0]);
    }

    #[test]
    fn histogram_cumulative_rejects_invalid_bins_without_partial_output() {
        for (heights, edges, density) in [
            (vec![], vec![0.0], false),
            (vec![1.0], vec![0.0], false),
            (vec![-1.0], vec![0.0, 1.0], false),
            (vec![f64::NAN], vec![0.0, 1.0], false),
            (vec![1.0], vec![1.0, 1.0], false),
            (vec![1.0], vec![-f64::MAX, f64::MAX], true),
            (vec![f64::MAX, f64::MAX], vec![0.0, 1.0, 2.0], false),
        ] {
            let mut out = vec![-7.0; heights.len()];
            assert!(!histogram_cumulative_into(
                &heights, &edges, density, &mut out,
            ));
            assert_eq!(out, vec![-7.0; heights.len()]);
        }
    }

    #[test]
    fn binned_ecdf_enforces_domain_and_step_capacity_contracts() {
        assert!(binned_ecdf(&[f64::NAN], 1, None).is_none());
        assert!(binned_ecdf(&[0.0], 0, None).is_none());
        assert!(binned_ecdf(&[0.0], MAX_HISTOGRAM_BINS + 1, None).is_none());
        assert!(binned_ecdf(&[0.0], 1, Some((0.0, 0.0))).is_none());
        assert!(binned_ecdf(&[-f64::MAX, f64::MAX], 1, None).is_none());
        assert!(binned_ecdf(&[f64::MAX], 2, None).is_none());
        assert!(binned_ecdf(&[-f64::MAX], 2, None).is_none());
        assert!(binned_ecdf(&[0.0, 2.0e-309, 1.0e-308], 2, None).is_none());

        for safe_domain in [[1.0e-300, 2.0e-300], [1.0e300, 1.1e300]] {
            let result = binned_ecdf(&safe_domain, 2, None).unwrap();
            assert!(result.x.windows(2).all(|pair| pair[1] > pair[0]));
            assert!(result.x.into_iter().all(f64::is_finite));
            assert_eq!(result.cumulative.last(), Some(&1.0));
        }

        let values: Vec<f64> = (0..MAX_HISTOGRAM_BINS)
            .map(|index| index as f64 + 0.5)
            .collect();
        let maximum = binned_ecdf(
            &values,
            MAX_HISTOGRAM_BINS,
            Some((0.0, MAX_HISTOGRAM_BINS as f64)),
        )
        .unwrap();
        assert_eq!(maximum.x.len(), MAX_HISTOGRAM_BINS + 1);
        assert_eq!(maximum.cumulative.last(), Some(&1.0));
    }

    #[test]
    fn histogram_edges_enforces_resource_bound() {
        let data = [0.0, 1.0];
        let at_bound = histogram_edges(
            &data,
            Some((0.0, MAX_HISTOGRAM_BINS as f64 / 2.0)),
            HistogramEdgesMethod::Auto,
        )
        .unwrap();
        assert_eq!(at_bound.len(), MAX_HISTOGRAM_BINS + 1);
        assert!(histogram_edges(
            &data,
            Some((0.0, MAX_HISTOGRAM_BINS as f64 / 2.0 + 0.5)),
            HistogramEdgesMethod::Auto,
        )
        .is_none());
    }

    #[test]
    fn wind_rose_bins_centres_on_north_and_stacks_bands() {
        let directions = [0.0, 0.0, 90.0];
        let speeds = [1.0, 1.0, 1.0];
        let r = wind_rose_bins(&directions, &speeds, 4, Some(&[2.0])).unwrap();
        assert_eq!(r.centres, vec![0.0, 90.0, 180.0, 270.0]);
        assert_eq!(r.edges, vec![2.0]);
        assert_eq!(r.n_obs, 3);
        assert_eq!(r.counts, vec![2.0, 1.0, 0.0, 0.0]);
    }

    #[test]
    fn wind_rose_bins_rejects_authored_edges_that_drop_observations() {
        let directions = [10.0, 10.0, 10.0];
        let speeds = [5.0, 15.0, 25.0];
        assert!(wind_rose_bins(&directions, &speeds, 4, Some(&[10.0, 20.0])).is_none());
        let ok = wind_rose_bins(&directions, &speeds, 4, Some(&[10.0, 20.0, 30.0])).unwrap();
        assert_eq!(ok.edges, vec![10.0, 20.0, 30.0]);
        assert_eq!(ok.counts.iter().sum::<f64>(), 3.0);
    }

    #[test]
    fn wind_rose_auto_edges_cover_fastest_observation() {
        let directions = [0.0, 90.0, 180.0, 270.0];
        let speeds = [1.0, 2.0, 3.0, 17.01699109];
        let r = wind_rose_bins(&directions, &speeds, 4, None).unwrap();
        assert!(r.edges[r.edges.len() - 1] + 1e-12 >= 17.01699109);
        assert_eq!(r.counts.iter().sum::<f64>(), 4.0);
    }

    #[test]
    fn round_3g_matches_python_float_format() {
        let cases = [
            (1.92111796, 1.92),
            (3.31646642, 3.32),
            (5.07235186, 5.07),
            (17.01699109, 17.0),
            (0.001235, 0.00123),
            (12345.6, 12300.0),
            (9.995, 9.99),
            (0.9995, 1.0),
        ];
        for (v, expected) in cases {
            let got = round_3g(v);
            assert!(
                (got - expected).abs() <= 1e-12 * expected.abs().max(1.0),
                "round_3g({v}) = {got}, expected {expected}"
            );
        }
    }
}
