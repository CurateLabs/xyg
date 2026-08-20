//! Deterministic directed multigraph edge routing for paint (#33).
//!
//! Hosts call this after [`crate::graph::build_render`] so Direct-tier
//! parallels, reciprocal pairs, and self-loops become visibly distinct
//! segments with optional arrowheads. Rust owns the geometry; hosts only
//! upload the returned columns.

use std::collections::HashMap;

/// Maximum paint segments emitted per source edge by [`edge_route_segments`].
/// Self-loops expand to three sides; directed non-loops add two arrow wings.
pub const EDGE_ROUTE_SEGMENTS_PER_EDGE: usize = 5;

/// Route render-graph edges into paint segments with deterministic multi-edge
/// separation, self-loop geometry, and optional directed arrowheads (#33).
///
/// Parallel and reciprocal edges that share an undirected endpoint pair receive
/// symmetric perpendicular offsets ranked by source edge index. Self-loops emit
/// a three-segment triangular loop. When `arrow_size > 0` and `directed`, each
/// non-loop edge also emits two arrowhead wing segments; the shaft shortens so
/// the tip meets the geometric endpoint.
///
/// Writes `out_*` columns of equal length and returns the segment count. Each
/// `out_edge_index[i]` is the source edge index that produced segment `i`.
/// Caller buffers must hold at least `sources.len() * EDGE_ROUTE_SEGMENTS_PER_EDGE`
/// slots (hosts may allocate that ceiling).
#[allow(clippy::too_many_arguments)] // mirrors the C ABI buffer list
pub fn edge_route_segments(
    n_nodes: u64,
    x: &[f64],
    y: &[f64],
    sources: &[u64],
    targets: &[u64],
    directed: bool,
    separation: f64,
    loop_radius: f64,
    arrow_size: f64,
    out_x0: &mut [f64],
    out_y0: &mut [f64],
    out_x1: &mut [f64],
    out_y1: &mut [f64],
    out_edge_index: &mut [u64],
) -> Option<u64> {
    let Ok(n) = usize::try_from(n_nodes) else {
        return None;
    };
    if x.len() != n || y.len() != n || sources.len() != targets.len() {
        return None;
    }
    if !separation.is_finite()
        || separation < 0.0
        || !loop_radius.is_finite()
        || loop_radius < 0.0
        || !arrow_size.is_finite()
        || arrow_size < 0.0
    {
        return None;
    }
    let e = sources.len();
    let capacity = e.checked_mul(EDGE_ROUTE_SEGMENTS_PER_EDGE)?;
    if out_x0.len() < capacity
        || out_y0.len() < capacity
        || out_x1.len() < capacity
        || out_y1.len() < capacity
        || out_edge_index.len() < capacity
    {
        return None;
    }

    // Bundle ranks: undirected key so reciprocal + parallel siblings separate.
    let mut bundles: HashMap<(u64, u64), Vec<usize>> = HashMap::new();
    for (i, (&s, &t)) in sources.iter().zip(targets.iter()).enumerate() {
        if s >= n_nodes || t >= n_nodes {
            return None;
        }
        let key = if s <= t { (s, t) } else { (t, s) };
        bundles.entry(key).or_default().push(i);
    }
    let mut rank = vec![0i32; e];
    let mut bundle_size = vec![1i32; e];
    for members in bundles.values_mut() {
        members.sort_unstable();
        let size = members.len() as i32;
        for (r, &idx) in members.iter().enumerate() {
            rank[idx] = r as i32;
            bundle_size[idx] = size;
        }
    }

    let mut written = 0usize;
    let mut emit = |edge_i: u64, x0: f64, y0: f64, x1: f64, y1: f64| {
        if !x0.is_finite() || !y0.is_finite() || !x1.is_finite() || !y1.is_finite() {
            return;
        }
        out_x0[written] = x0;
        out_y0[written] = y0;
        out_x1[written] = x1;
        out_y1[written] = y1;
        out_edge_index[written] = edge_i;
        written += 1;
    };

    for i in 0..e {
        let s = sources[i] as usize;
        let t = targets[i] as usize;
        let sx = x[s];
        let sy = y[s];
        let tx = x[t];
        let ty = y[t];
        if !sx.is_finite() || !sy.is_finite() || !tx.is_finite() || !ty.is_finite() {
            continue;
        }
        let edge_i = i as u64;
        let size = bundle_size[i];
        let offset = if size <= 1 || separation == 0.0 {
            0.0
        } else {
            (rank[i] as f64 - 0.5 * (size - 1) as f64) * separation
        };

        if s == t {
            // Triangular self-loop, oriented by bundle rank for stacked loops.
            let r = if loop_radius > 0.0 {
                loop_radius
            } else {
                separation.max(0.35)
            };
            let theta = std::f64::consts::FRAC_PI_2
                + (rank[i] as f64) * (std::f64::consts::TAU / size.max(1) as f64);
            let (st, ct) = theta.sin_cos();
            let cx = sx + r * ct;
            let cy = sy + r * st;
            let px = -st;
            let py = ct;
            let a_x = cx + 0.7 * r * px;
            let a_y = cy + 0.7 * r * py;
            let b_x = cx - 0.7 * r * px;
            let b_y = cy - 0.7 * r * py;
            emit(edge_i, sx, sy, a_x, a_y);
            emit(edge_i, a_x, a_y, b_x, b_y);
            emit(edge_i, b_x, b_y, sx, sy);
            continue;
        }

        let dx = tx - sx;
        let dy = ty - sy;
        let len = dx.hypot(dy);
        if len == 0.0 {
            continue;
        }
        let ux = -dy / len;
        let uy = dx / len;
        let x0 = sx + offset * ux;
        let y0 = sy + offset * uy;
        let mut x1 = tx + offset * ux;
        let mut y1 = ty + offset * uy;

        if directed && arrow_size > 0.0 {
            let inset = arrow_size.min(0.45 * len);
            let inv = 1.0 / len;
            let tip_x = x1;
            let tip_y = y1;
            x1 -= dx * inv * inset;
            y1 -= dy * inv * inset;
            // Shaft stops short of the tip so the arrowhead owns the endpoint.
            emit(edge_i, x0, y0, x1, y1);
            let back_x = tip_x - dx * inv * arrow_size;
            let back_y = tip_y - dy * inv * arrow_size;
            let wing = arrow_size * 0.45;
            emit(edge_i, tip_x, tip_y, back_x + ux * wing, back_y + uy * wing);
            emit(edge_i, tip_x, tip_y, back_x - ux * wing, back_y - uy * wing);
        } else {
            emit(edge_i, x0, y0, x1, y1);
        }
    }

    Some(written as u64)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn separates_parallels_and_emits_loop_and_arrows() {
        let x = [0.0, 2.0, 4.0];
        let y = [0.0, 0.0, 0.0];
        let sources = [0u64, 0, 2];
        let targets = [1u64, 1, 2];
        let cap = sources.len() * EDGE_ROUTE_SEGMENTS_PER_EDGE;
        let mut ox0 = vec![0.0; cap];
        let mut oy0 = vec![0.0; cap];
        let mut ox1 = vec![0.0; cap];
        let mut oy1 = vec![0.0; cap];
        let mut eidx = vec![0u64; cap];
        let n = edge_route_segments(
            3,
            &x,
            &y,
            &sources,
            &targets,
            true,
            0.2,
            0.5,
            0.15,
            &mut ox0,
            &mut oy0,
            &mut ox1,
            &mut oy1,
            &mut eidx,
        )
        .expect("route");
        // Two parallel edges × (shaft + 2 wings) + one 3-segment loop = 9.
        assert_eq!(n, 9);
        let shaft0_y = oy0[0];
        let shaft1_y = oy0[3];
        assert!((shaft0_y - shaft1_y).abs() > 1e-9);
        let loop_segs = eidx[..n as usize].iter().filter(|&&e| e == 2).count();
        assert_eq!(loop_segs, 3);
    }
}
