//! Capped canonical-row localization over existing chunk zone maps (§5/§22/§27/§28).
//! No row-sized scratch, candidate expansion, ingest sort, or derived f32 index.
use crate::lod_plan::{drill_decision, DEFAULT_EXIT_FACTOR, SCATTER_DENSITY_THRESHOLD};

/// Existing spatial refinement candidate policy (`SPATIAL_EXACT_MAX_POINTS`).
pub const SCAN_ROW_BUDGET: u64 = 80_000_000;

pub fn point_cap(in_drill: bool) -> usize {
    let threshold =
        SCATTER_DENSITY_THRESHOLD as f64 * if in_drill { DEFAULT_EXIT_FACTOR } else { 1.0 };
    let cap = threshold.floor() as usize;
    debug_assert_eq!(
        drill_decision(
            cap as u64,
            SCATTER_DENSITY_THRESHOLD as f64,
            in_drill,
            DEFAULT_EXIT_FACTOR
        ),
        Some(true)
    );
    cap
}

/// Approximate counts admit work only; they never certify a point count.
/// Unknown estimates (-1) require an outresolved finest pyramid source.
pub fn admit(estimate: f64, in_drill: bool, refinement: bool) -> Option<bool> {
    if !estimate.is_finite() || estimate < -1.0 {
        return None;
    }
    Some(refinement || (estimate >= 0.0 && estimate <= point_cap(in_drill) as f64 * 1.5))
}

/// Uniform area-scaled count used solely to admit a bounded exact query.
/// This estimate never establishes exact count, empty status, or drill state.
pub fn estimate(rows: u64, extent: [f64; 4], window: [f64; 4]) -> Option<f64> {
    if !extent.iter().chain(window.iter()).all(|v| v.is_finite())
        || extent[1] <= extent[0]
        || extent[3] <= extent[2]
        || window[1] < window[0]
        || window[3] < window[2]
    {
        return None;
    }
    let ratio = |a: f64, b: f64, lo: f64, hi: f64| {
        ((b.min(hi) - a.max(lo)).max(0.0) / (hi - lo)).clamp(0.0, 1.0)
    };
    let count = rows as f64
        * ratio(window[0], window[1], extent[0], extent[1])
        * ratio(window[2], window[3], extent[2], extent[3]);
    count.is_finite().then_some(count)
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Status {
    Complete = 0,
    Overflow = 1,
    ScanBudget = 2,
}

#[derive(Debug, Clone, Copy)]
pub struct Observation {
    pub status: Status,
    /// Defined only on Complete. A refused prefix is never an exact count.
    pub count: Option<usize>,
    pub candidate_rows: u64,
    pub candidate_chunks: u64,
    pub rows_read: u64,
}

fn valid_zone(lo: f64, hi: f64) -> bool {
    (lo.is_finite() && hi.is_finite() && lo <= hi)
        || (lo == f64::INFINITY && hi == f64::NEG_INFINITY)
}
fn overlaps(i: usize, planes: [&[f64]; 4], window: [f64; 4]) -> bool {
    planes[0][i] <= window[1]
        && planes[1][i] >= window[0]
        && planes[2][i] <= window[3]
        && planes[3][i] >= window[2]
}

/// Preflight touches O(chunks) metadata, never canonical coordinates. Admission
/// checks the total candidate rows before the first coordinate load.
fn preflight(
    n: usize,
    chunk_size: usize,
    planes: [&[f64]; 4],
    window: [f64; 4],
) -> Option<Observation> {
    if n > u32::MAX as usize
        || chunk_size == 0
        || !window.iter().all(|v| v.is_finite())
        || window[0] > window[1]
        || window[2] > window[3]
    {
        return None;
    }
    let chunks = n.div_ceil(chunk_size);
    if planes.iter().any(|p| p.len() != chunks) {
        return None;
    }
    let mut obs = Observation {
        status: Status::Complete,
        count: Some(0),
        candidate_rows: 0,
        candidate_chunks: 0,
        rows_read: 0,
    };
    for i in 0..chunks {
        if !valid_zone(planes[0][i], planes[1][i]) || !valid_zone(planes[2][i], planes[3][i]) {
            return None;
        }
        if overlaps(i, planes, window) {
            obs.candidate_chunks += 1;
            obs.candidate_rows += (n - i * chunk_size).min(chunk_size) as u64;
        }
    }
    if obs.candidate_rows > SCAN_ROW_BUDGET {
        obs.status = Status::ScanBudget;
        obs.count = None;
    }
    Some(obs)
}

/// Inclusive f64 rectangle predicate; non-finite rows never match. Returned IDs
/// ascend in canonical source order. Only Complete makes `out[..count]` valid.
/// Overflow and ScanBudget leave any output prefix undefined, never exact.
pub fn query(
    x: &[f64],
    y: &[f64],
    chunk_size: usize,
    planes: [&[f64]; 4],
    window: [f64; 4],
    in_drill: bool,
    out: &mut [u32],
) -> Option<Observation> {
    let cap = point_cap(in_drill);
    if x.len() != y.len() || out.len() < cap {
        return None;
    }
    let mut obs = preflight(x.len(), chunk_size, planes, window)?;
    if obs.status != Status::Complete {
        return Some(obs);
    }
    let mut count = 0;
    for i in 0..planes[0].len() {
        if !overlaps(i, planes, window) {
            continue;
        }
        let start = i * chunk_size;
        for row in start..start + (x.len() - start).min(chunk_size) {
            let (xv, yv) = (x[row], y[row]);
            obs.rows_read += 1;
            if xv.is_finite()
                && yv.is_finite()
                && xv >= window[0]
                && xv <= window[1]
                && yv >= window[2]
                && yv <= window[3]
            {
                if count == cap {
                    obs.status = Status::Overflow;
                    obs.count = None;
                    return Some(obs);
                }
                out[count] = row as u32;
                count += 1;
            }
        }
    }
    obs.count = Some(count);
    Some(obs)
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn canonical_order_endpoints_nan_empty_and_pruning() {
        let x = [0., 1., f64::NAN, 3., 100., 101.];
        let y = [0., 1., 2., 3., 100., 101.];
        let p = [
            &[0., 3., 100.][..],
            &[1., 3., 101.][..],
            &[0., 2., 100.][..],
            &[1., 3., 101.][..],
        ];
        let mut out = vec![0; point_cap(false)];
        let obs = query(&x, &y, 2, p, [0., 3., 0., 3.], false, &mut out).unwrap();
        assert_eq!(obs.count, Some(3));
        assert_eq!(&out[..3], &[0, 1, 3]);
        assert_eq!(
            (obs.candidate_rows, obs.candidate_chunks, obs.rows_read),
            (4, 2, 4)
        );
        let obs = query(&x, &y, 2, p, [20., 30., 20., 30.], false, &mut out).unwrap();
        assert_eq!(obs.count, Some(0));
        assert_eq!(obs.rows_read, 0);
        assert_eq!(
            query(&[], &[], 2, [&[]; 4], [0., 0., 0., 0.], false, &mut out)
                .unwrap()
                .count,
            Some(0)
        );
    }
    #[test]
    fn threshold_and_hysteresis_match_existing_policy() {
        for in_drill in [false, true] {
            let cap = point_cap(in_drill);
            let x = vec![0.; cap + 1];
            let y = vec![0.; cap + 1];
            let p = [&[0.][..]; 4];
            let mut out = vec![0; cap];
            let obs = query(&x, &y, x.len(), p, [0., 1., 0., 1.], in_drill, &mut out).unwrap();
            assert_eq!(obs.status, Status::Overflow);
            assert_eq!(obs.count, None);
            assert_eq!(obs.rows_read, cap as u64 + 1);
            let obs = query(
                &x[..cap],
                &y[..cap],
                cap,
                p,
                [0., 1., 0., 1.],
                in_drill,
                &mut out,
            )
            .unwrap();
            assert_eq!(obs.count, Some(cap));
        }
        assert_eq!(point_cap(false), 200_000);
    }
    #[test]
    fn budget_preflight_never_reads_source_or_certifies_a_prefix() {
        let n = SCAN_ROW_BUDGET as usize + 1;
        let chunk = 65_536;
        let lo = vec![0.; n.div_ceil(chunk)];
        let hi = vec![1.; lo.len()];
        let obs = preflight(n, chunk, [&lo, &hi, &lo, &hi], [0., 1., 0., 1.]).unwrap();
        assert_eq!(obs.status, Status::ScanBudget);
        assert_eq!(obs.count, None);
        assert_eq!(obs.candidate_rows, n as u64);
        assert_eq!(obs.rows_read, 0);
        assert!(preflight(2, 0, [&[]; 4], [0.; 4]).is_none());
        assert!(preflight(2, 2, [&[f64::NAN]; 4], [0.; 4]).is_none());
        assert_eq!(admit(-1., false, false), Some(false));
        assert_eq!(admit(100_000_000., false, true), Some(true));
        assert_eq!(admit(300_001., false, false), Some(false));
        assert!(admit(f64::NAN, false, true).is_none());
    }
}
