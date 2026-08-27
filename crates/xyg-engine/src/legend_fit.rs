//! Composition `loc="best"` occupancy scoring (M2 #275 / ABI 120).
//!
//! Hosts walk traces, pack columns and label lengths, and resolve `best` once
//! before Scene packing so Python, Node, and the three renderers share one
//! placement. The algorithm matches `python/xyg/_legendfit.py`: Matplotlib
//! candidate order, display-space projection, drop-not-clamp off-plot marks,
//! 4096/512 sampling, and a 0.02 mean-occupancy tie band.

/// Matplotlib candidate names in preference order (corners, mid-edges, center).
pub const CANDIDATE_ORDER: [&str; 9] = [
    "upper right",
    "upper left",
    "lower left",
    "lower right",
    "center right",
    "center left",
    "lower center",
    "upper center",
    "center",
];

/// Mean-occupancy spread at or below which two boxes count as tied.
pub const TIE_BAND: f64 = 0.02;

/// Fallback when nothing is scorable; also candidate index 0.
pub const FALLBACK_INDEX: i32 = 0;

/// Stride a series longer than this *before* the finite scan.
pub const STRIDE_CAP: usize = 4096;

/// Cap finite pairs per series after the optional stride.
pub const FINITE_CAP: usize = 512;

const LOG_FLOOR: f64 = 1e-300;
const MAX_FOOTPRINT: f64 = 0.6;

/// Axis scale applied before occupancy is measured (display space, not values).
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
#[repr(i32)]
pub enum LegendScale {
    Linear = 0,
    Log = 1,
    Symlog = 2,
}

impl LegendScale {
    pub fn from_i32(v: i32) -> Option<Self> {
        match v {
            0 => Some(Self::Linear),
            1 => Some(Self::Log),
            2 => Some(Self::Symlog),
            _ => None,
        }
    }
}

/// Normalized [0, 1] occupancy sample for one series.
#[derive(Clone, Debug, PartialEq)]
pub struct NormalizedSeries {
    pub x: Vec<f64>,
    pub y: Vec<f64>,
}

/// Fractional legend box size from row count and the longest label.
pub fn legend_footprint(label_lens: &[u32]) -> (f64, f64) {
    let rows = label_lens.len().max(1) as f64;
    let max_len = label_lens.iter().copied().max().unwrap_or(4) as f64;
    (
        (0.12 + 0.03 * max_len).min(MAX_FOOTPRINT),
        (0.10 + 0.07 * rows).min(MAX_FOOTPRINT),
    )
}

/// Candidate rectangles `(x_lo, x_hi, y_lo, y_hi)` in the normalized plot box.
pub fn candidate_boxes(box_w: f64, box_h: f64) -> [(f64, f64, f64, f64); 9] {
    let cx_lo = 0.5 - box_w / 2.0;
    let cx_hi = 0.5 + box_w / 2.0;
    let cy_lo = 0.5 - box_h / 2.0;
    let cy_hi = 0.5 + box_h / 2.0;
    [
        (1.0 - box_w, 1.0, 1.0 - box_h, 1.0), // upper right
        (0.0, box_w, 1.0 - box_h, 1.0),       // upper left
        (0.0, box_w, 0.0, box_h),             // lower left
        (1.0 - box_w, 1.0, 0.0, box_h),       // lower right
        (1.0 - box_w, 1.0, cy_lo, cy_hi),     // center right
        (0.0, box_w, cy_lo, cy_hi),           // center left
        (cx_lo, cx_hi, 0.0, box_h),           // lower center
        (cx_lo, cx_hi, 1.0 - box_h, 1.0),     // upper center
        (cx_lo, cx_hi, cy_lo, cy_hi),         // center
    ]
}

fn display_transform(v: f64, scale: LegendScale, constant: f64) -> f64 {
    match scale {
        LegendScale::Linear => v,
        LegendScale::Log => v.max(LOG_FLOOR).log10(),
        LegendScale::Symlog => {
            let c = if constant == 0.0 { 1.0 } else { constant };
            v.signum() * (v.abs() / c).ln_1p()
        }
    }
}

/// NumPy `linspace(0, last, num, dtype=intp)`: last sample is exact, values
/// round half-to-even, matching occupancy sampling in `_legendfit.normalize`.
fn linspace_int_indices(last: usize, num: usize) -> Vec<usize> {
    if num == 0 {
        return Vec::new();
    }
    if num == 1 {
        return vec![0];
    }
    let last_f = last as f64;
    let div = (num - 1) as f64;
    let mut out = Vec::with_capacity(num);
    for i in 0..num {
        let v = if i + 1 == num {
            last_f
        } else {
            (i as f64) * last_f / div
        };
        out.push(round_half_even_nonneg(v).min(last));
    }
    out
}

fn round_half_even_nonneg(v: f64) -> usize {
    let floor = v.floor();
    let frac = v - floor;
    if frac < 0.5 {
        floor as usize
    } else if frac > 0.5 {
        floor as usize + 1
    } else {
        let f = floor as usize;
        if f % 2 == 0 {
            f
        } else {
            f + 1
        }
    }
}

fn pair_finite(x: f64, y: f64) -> bool {
    x.is_finite() && y.is_finite()
}

/// Sample a series and project it into the normalized plot box.
///
/// Off-plot marks are dropped, not clamped. Returns `None` when no finite
/// visible pair remains, or when the displayed domain is not strictly ordered.
pub fn normalize(
    x: &[f64],
    y: &[f64],
    x_domain: (f64, f64),
    y_domain: (f64, f64),
    x_reverse: bool,
    y_reverse: bool,
    x_scale: LegendScale,
    y_scale: LegendScale,
    x_constant: f64,
    y_constant: f64,
) -> Option<NormalizedSeries> {
    if x.len() != y.len() {
        return None;
    }
    let n = x.len();
    if n == 0 {
        return None;
    }

    let mut sample_idx: Option<Vec<usize>> = None;
    if n > STRIDE_CAP {
        let strided = linspace_int_indices(n - 1, STRIDE_CAP);
        if strided
            .iter()
            .any(|&i| pair_finite(x[i.min(n - 1)], y[i.min(n - 1)]))
        {
            sample_idx = Some(strided);
        }
    }

    let mut finite: Vec<usize> = match sample_idx {
        Some(idx) => idx
            .into_iter()
            .filter(|&i| {
                let i = i.min(n - 1);
                pair_finite(x[i], y[i])
            })
            .collect(),
        None => (0..n).filter(|&i| pair_finite(x[i], y[i])).collect(),
    };
    if finite.len() > FINITE_CAP {
        let pick = linspace_int_indices(finite.len() - 1, FINITE_CAP);
        finite = pick
            .into_iter()
            .map(|i| finite[i.min(finite.len() - 1)])
            .collect();
    }
    if finite.is_empty() {
        return None;
    }

    let xlo = display_transform(x_domain.0, x_scale, x_constant);
    let xhi = display_transform(x_domain.1, x_scale, x_constant);
    let ylo = display_transform(y_domain.0, y_scale, y_constant);
    let yhi = display_transform(y_domain.1, y_scale, y_constant);
    if !(xlo.is_finite() && xhi.is_finite() && ylo.is_finite() && yhi.is_finite()) {
        return None;
    }
    if xhi <= xlo || yhi <= ylo {
        return None;
    }
    let xspan = xhi - xlo;
    let yspan = yhi - ylo;

    let mut xs = Vec::with_capacity(finite.len());
    let mut ys = Vec::with_capacity(finite.len());
    for i in finite {
        let xn = (display_transform(x[i], x_scale, x_constant) - xlo) / xspan;
        let yn = (display_transform(y[i], y_scale, y_constant) - ylo) / yspan;
        if xn.is_finite()
            && yn.is_finite()
            && (0.0..=1.0).contains(&xn)
            && (0.0..=1.0).contains(&yn)
        {
            xs.push(if x_reverse { 1.0 - xn } else { xn });
            ys.push(if y_reverse { 1.0 - yn } else { yn });
        }
    }
    if xs.is_empty() {
        return None;
    }
    Some(NormalizedSeries { x: xs, y: ys })
}

/// Least-occupied candidate index (0..=8) for concatenated normalized series.
///
/// `starts[i]` is the first index of series `i`; the last series runs to
/// `xs.len()`. Empty series are skipped. No scorable series → [`FALLBACK_INDEX`].
pub fn best_loc(xs: &[f64], ys: &[f64], starts: &[usize], label_lens: &[u32]) -> i32 {
    if xs.len() != ys.len() {
        return FALLBACK_INDEX;
    }
    let n = xs.len();
    if starts.is_empty() {
        return FALLBACK_INDEX;
    }
    let (box_w, box_h) = legend_footprint(label_lens);
    let boxes = candidate_boxes(box_w, box_h);
    let mut scores = [0.0_f64; 9];
    let mut used = 0usize;
    for (i, &start) in starts.iter().enumerate() {
        let end = if i + 1 < starts.len() {
            starts[i + 1]
        } else {
            n
        };
        if start > end || end > n {
            continue;
        }
        let count = end - start;
        if count == 0 {
            continue;
        }
        let denom = count as f64;
        used += 1;
        for (c, &(xl, xh, yl, yh)) in boxes.iter().enumerate() {
            let mut inside = 0usize;
            for k in start..end {
                let xn = xs[k];
                let yn = ys[k];
                if xn >= xl && xn <= xh && yn >= yl && yn <= yh {
                    inside += 1;
                }
            }
            scores[c] += (inside as f64) / denom;
        }
    }
    if used == 0 {
        return FALLBACK_INDEX;
    }
    let inv = 1.0 / (used as f64);
    for score in scores.iter_mut() {
        *score *= inv;
    }
    let floor = scores.iter().copied().fold(f64::INFINITY, f64::min);
    scores
        .iter()
        .position(|&score| score <= floor + TIE_BAND)
        .map(|i| i as i32)
        .unwrap_or(FALLBACK_INDEX)
}

pub fn candidate_name(index: i32) -> Option<&'static str> {
    CANDIDATE_ORDER.get(index as usize).copied()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn log_decades_spread_evenly() {
        let decades = [1.0, 10.0, 100.0, 1000.0, 10000.0];
        let got = normalize(
            &decades,
            &decades,
            (1.0, 10000.0),
            (1.0, 10000.0),
            false,
            false,
            LegendScale::Log,
            LegendScale::Log,
            1.0,
            1.0,
        )
        .unwrap();
        let expected = [0.0, 0.25, 0.5, 0.75, 1.0];
        for (a, b) in got.x.iter().zip(expected.iter()) {
            assert!((a - b).abs() < 1e-12);
        }
    }

    #[test]
    fn off_plot_marks_are_dropped() {
        let values = [0.0, 0.5, 1.0, 50.0, 99.0];
        let got = normalize(
            &values,
            &values,
            (0.0, 1.0),
            (0.0, 1.0),
            false,
            false,
            LegendScale::Linear,
            LegendScale::Linear,
            1.0,
            1.0,
        )
        .unwrap();
        assert_eq!(got.x, vec![0.0, 0.5, 1.0]);
    }

    #[test]
    fn entirely_off_plot_is_none() {
        let values = [50.0, 60.0];
        assert!(normalize(
            &values,
            &values,
            (0.0, 1.0),
            (0.0, 1.0),
            false,
            false,
            LegendScale::Linear,
            LegendScale::Linear,
            1.0,
            1.0,
        )
        .is_none());
    }

    #[test]
    fn rising_diagonal_picks_upper_left() {
        let x = [0.0, 0.5, 1.0];
        let got = normalize(
            &x,
            &x,
            (0.0, 1.0),
            (0.0, 1.0),
            false,
            false,
            LegendScale::Linear,
            LegendScale::Linear,
            1.0,
            1.0,
        )
        .unwrap();
        assert_eq!(
            best_loc(&got.x, &got.y, &[0], &[1]),
            CANDIDATE_ORDER
                .iter()
                .position(|&n| n == "upper left")
                .unwrap() as i32
        );
    }

    #[test]
    fn falling_diagonal_picks_upper_right() {
        let x = [0.0, 0.5, 1.0];
        let y = [1.0, 0.5, 0.0];
        let got = normalize(
            &x,
            &y,
            (0.0, 1.0),
            (0.0, 1.0),
            false,
            false,
            LegendScale::Linear,
            LegendScale::Linear,
            1.0,
            1.0,
        )
        .unwrap();
        assert_eq!(best_loc(&got.x, &got.y, &[0], &[1]), FALLBACK_INDEX);
    }

    #[test]
    fn empty_series_falls_back() {
        assert_eq!(best_loc(&[], &[], &[], &[]), FALLBACK_INDEX);
    }

    #[test]
    fn sparse_finite_points_survive_stride() {
        let n = 20_000;
        let x: Vec<f64> = (0..n).map(|i| i as f64 / (n - 1) as f64).collect();
        let mut y = vec![f64::NAN; n];
        y[3] = 0.99;
        y[7] = 0.98;
        assert!(normalize(
            &x,
            &y,
            (0.0, 1.0),
            (0.0, 1.0),
            false,
            false,
            LegendScale::Linear,
            LegendScale::Linear,
            1.0,
            1.0,
        )
        .is_some());
    }

    #[test]
    fn log_fixture_differs_from_linear() {
        let xs = [5000.0, 7500.0, 1.0, 3000.0, 8000.0];
        let ys = [7000.0, 4.0, 8000.0, 3600.0, 2000.0];
        let domain = (1.0, 10000.0);
        let raw = normalize(
            &xs,
            &ys,
            domain,
            domain,
            false,
            false,
            LegendScale::Linear,
            LegendScale::Linear,
            1.0,
            1.0,
        )
        .unwrap();
        let logged = normalize(
            &xs,
            &ys,
            domain,
            domain,
            false,
            false,
            LegendScale::Log,
            LegendScale::Log,
            1.0,
            1.0,
        )
        .unwrap();
        assert_eq!(best_loc(&raw.x, &raw.y, &[0], &[1]), FALLBACK_INDEX);
        assert_eq!(
            candidate_name(best_loc(&logged.x, &logged.y, &[0], &[1])),
            Some("lower left")
        );
    }

    #[test]
    fn symlog_constant_changes_positions() {
        let values = [0.0, 1.0, 10.0, 100.0];
        let a = normalize(
            &values,
            &values,
            (0.0, 100.0),
            (0.0, 100.0),
            false,
            false,
            LegendScale::Symlog,
            LegendScale::Symlog,
            1.0,
            1.0,
        )
        .unwrap();
        let b = normalize(
            &values,
            &values,
            (0.0, 100.0),
            (0.0, 100.0),
            false,
            false,
            LegendScale::Symlog,
            LegendScale::Symlog,
            25.0,
            25.0,
        )
        .unwrap();
        assert!((a.x[1] - 0.15).abs() < 0.01);
        assert!((b.x[1] - 0.024).abs() < 0.01);
        assert!((a.x[1] - b.x[1]).abs() > 0.05);
    }
}
