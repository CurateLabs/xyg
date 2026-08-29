//! Compatibility geometry helpers (M2 #279 / ABI 121).
//!
//! One cubic, one Fritsch–Carlson tangent construction, one rounded-rect
//! tessellation, and one step/stairs expand shared by Scene ribbon expansion
//! and the host SVG/raster fallbacks. Hosts still map through their scale
//! objects; this module owns the coordinate-free flattening so Python and Node
//! cannot drift.

use std::collections::{BTreeSet, HashMap};

/// Segments per ribbon edge. Product policy, not view-adaptive: a flow
/// diagram has tens of links, so the ceiling is free, and a view-dependent
/// count would have to be recorded per §28 rather than chosen silently.
pub const RIBBON_STEPS: usize = 96;

/// Samples per smooth Bézier span when flattening a monotone-cubic Hermite
/// (`np.linspace(0, 1, 16, endpoint=False)`, interior points plus each knot).
pub const BEZIER_STEPS: usize = 16;

/// Arc samples per rounded-rect corner (including both end angles).
pub const ROUNDED_RECT_ARC_STEPS: usize = 5;

/// Hard ceiling on an authored ribbon/curve sample count.
pub const MAX_STEPS: usize = 4096;

/// Cubic Bézier scalar at `t ∈ [0, 1]` with controls `p0..p3`.
#[inline]
pub fn cubic_bezier(t: f64, p0: f64, p1: f64, p2: f64, p3: f64) -> f64 {
    let u = 1.0 - t;
    u.powi(3) * p0 + 3.0 * u.powi(2) * t * p1 + 3.0 * u * t.powi(2) * p2 + t.powi(3) * p3
}

/// d3 `curveBumpX` sample: both controls sit at the horizontal midpoint and
/// hold their own end's y, so the edge leaves and arrives horizontally.
#[inline]
pub fn curve_bump_x(t: f64, x0: f64, x1: f64, ya: f64, yb: f64) -> (f64, f64) {
    let mid = (x0 + x1) * 0.5;
    (
        cubic_bezier(t, x0, mid, mid, x1),
        cubic_bezier(t, ya, ya, yb, yb),
    )
}

/// Flatten one bump-X edge into `steps + 1` samples, including both ends.
pub fn ribbon_edge(
    x0: f64,
    x1: f64,
    ya: f64,
    yb: f64,
    steps: usize,
    out_x: &mut [f64],
    out_y: &mut [f64],
) -> Option<usize> {
    if steps == 0 || steps > MAX_STEPS {
        return None;
    }
    let n = steps + 1;
    if out_x.len() < n || out_y.len() < n {
        return None;
    }
    for sample in 0..=steps {
        let t = sample as f64 / steps as f64;
        let (x, y) = curve_bump_x(t, x0, x1, ya, yb);
        out_x[sample] = x;
        out_y[sample] = y;
    }
    Some(n)
}

/// Closed flow-band polygon: upper edge, then reversed lower edge.
pub fn ribbon_polygon(
    x0: f64,
    x1: f64,
    src_lo: f64,
    src_hi: f64,
    dst_lo: f64,
    dst_hi: f64,
    steps: usize,
    out_x: &mut [f64],
    out_y: &mut [f64],
) -> Option<usize> {
    let n_edge = steps.checked_add(1)?;
    let need = n_edge.checked_mul(2)?;
    if out_x.len() < need || out_y.len() < need {
        return None;
    }
    ribbon_edge(
        x0,
        x1,
        src_hi,
        dst_hi,
        steps,
        &mut out_x[..n_edge],
        &mut out_y[..n_edge],
    )?;
    ribbon_edge(
        x0,
        x1,
        src_lo,
        dst_lo,
        steps,
        &mut out_x[n_edge..need],
        &mut out_y[n_edge..need],
    )?;
    out_x[n_edge..need].reverse();
    out_y[n_edge..need].reverse();
    Some(need)
}

/// Fritsch–Carlson monotone-cubic tangents (NumPy / d3 / `xyMonotoneTangents`).
pub fn monotone_tangents(x: &[f64], y: &[f64], out: &mut [f64]) -> Option<usize> {
    if x.len() != y.len() {
        return None;
    }
    let n = x.len();
    if n < 2 {
        return None;
    }
    if out.len() < n {
        return None;
    }
    let mut d = vec![0.0; n - 1];
    for i in 0..n - 1 {
        let dx = x[i + 1] - x[i];
        let dy = y[i + 1] - y[i];
        d[i] = if dx > 0.0 { dy / dx } else { 0.0 };
    }
    out[0] = d[0];
    out[n - 1] = d[n - 2];
    for i in 1..n - 1 {
        out[i] = if d[i - 1] * d[i] <= 0.0 {
            0.0
        } else {
            (d[i - 1] + d[i]) * 0.5
        };
    }
    for i in 0..n - 1 {
        if d[i] == 0.0 {
            out[i] = 0.0;
            out[i + 1] = 0.0;
            continue;
        }
        let a = out[i] / d[i];
        let b = out[i + 1] / d[i];
        let s = a * a + b * b;
        if s > 9.0 {
            let t = 3.0 / s.sqrt();
            out[i] = t * a * d[i];
            out[i + 1] = t * b * d[i];
        }
    }
    Some(n)
}

/// Data-space Hermite flatten matching `_scene.curve_points` (smooth branch).
///
/// `bezier_steps` is the linspace count (`BEZIER_STEPS` = 16): each span
/// contributes that many interior-plus-end samples after the shared start.
pub fn curve_flatten(
    x: &[f64],
    y: &[f64],
    bezier_steps: usize,
    out_x: &mut [f64],
    out_y: &mut [f64],
) -> Option<usize> {
    if x.len() != y.len() {
        return None;
    }
    if !(2..=256).contains(&bezier_steps) {
        return None;
    }
    let n = x.len();
    if n == 0 {
        return Some(0);
    }
    if out_x.is_empty() || out_y.is_empty() {
        return None;
    }
    out_x[0] = x[0];
    out_y[0] = y[0];
    if n == 1 {
        return Some(1);
    }
    let mut m = vec![0.0; n];
    monotone_tangents(x, y, &mut m)?;
    let mut written = 1usize;
    let mut push = |px: f64, py: f64| -> Option<()> {
        if written >= out_x.len() || written >= out_y.len() {
            return None;
        }
        out_x[written] = px;
        out_y[written] = py;
        written += 1;
        Some(())
    };
    for i in 0..n - 1 {
        let h = x[i + 1] - x[i];
        if h <= 0.0 {
            push(x[i + 1], y[i + 1])?;
            continue;
        }
        let p0x = x[i];
        let p0y = y[i];
        let p3x = x[i + 1];
        let p3y = y[i + 1];
        let c1x = x[i] + h / 3.0;
        let c1y = y[i] + m[i] * h / 3.0;
        let c2x = x[i + 1] - h / 3.0;
        let c2y = y[i + 1] - m[i + 1] * h / 3.0;
        for k in 1..bezier_steps {
            let t = k as f64 / bezier_steps as f64;
            push(
                cubic_bezier(t, p0x, c1x, c2x, p3x),
                cubic_bezier(t, p0y, c1y, c2y, p3y),
            )?;
        }
        push(p3x, p3y)?;
    }
    Some(written)
}

/// Authored step/stairs mode: `1` pre, `2` mid, `3` post (Scene `step_mode`).
pub const STEP_PRE: u8 = 1;
pub const STEP_MID: u8 = 2;
pub const STEP_POST: u8 = 3;

/// Expanded vertex count for compact length `n`. `n < 2` is identity.
pub fn step_arrays_len(n: usize, mode: u8) -> Option<usize> {
    if n < 2 {
        return match mode {
            STEP_PRE | STEP_MID | STEP_POST => Some(n),
            _ => None,
        };
    }
    match mode {
        STEP_PRE | STEP_POST => n.checked_mul(2)?.checked_sub(1),
        STEP_MID => n.checked_mul(3)?.checked_sub(2),
        _ => None,
    }
}

/// Expand compact `(x, y)` vertices into a step polyline (ABI 211).
///
/// Matches compatibility `_svg._step_arrays` / ChartView `_stepArrays`:
/// pre holds the new y at the previous x, mid transitions at the midpoint,
/// post holds the previous y at the new x. Empty `out_x`/`out_y` is a size
/// probe. Length mismatch or an unknown mode returns `None`.
pub fn step_arrays(
    x: &[f64],
    y: &[f64],
    mode: u8,
    out_x: &mut [f64],
    out_y: &mut [f64],
) -> Option<usize> {
    if x.len() != y.len() {
        return None;
    }
    let n = x.len();
    let need = step_arrays_len(n, mode)?;
    if out_x.is_empty() && out_y.is_empty() {
        return Some(need);
    }
    if out_x.len() < need || out_y.len() < need {
        return None;
    }
    if n < 2 {
        if n == 1 {
            out_x[0] = x[0];
            out_y[0] = y[0];
        }
        return Some(n);
    }
    out_x[0] = x[0];
    out_y[0] = y[0];
    let mut written = 1usize;
    for i in 1..n {
        match mode {
            STEP_PRE => {
                out_x[written] = x[i - 1];
                out_y[written] = y[i];
                written += 1;
                out_x[written] = x[i];
                out_y[written] = y[i];
                written += 1;
            }
            STEP_MID => {
                let mid = (x[i - 1] + x[i]) * 0.5;
                out_x[written] = mid;
                out_y[written] = y[i - 1];
                written += 1;
                out_x[written] = mid;
                out_y[written] = y[i];
                written += 1;
                out_x[written] = x[i];
                out_y[written] = y[i];
                written += 1;
            }
            STEP_POST => {
                out_x[written] = x[i];
                out_y[written] = y[i - 1];
                written += 1;
                out_x[written] = x[i];
                out_y[written] = y[i];
                written += 1;
            }
            _ => return None,
        }
    }
    debug_assert_eq!(written, need);
    Some(need)
}

fn push_arc(
    cx: f64,
    cy: f64,
    r: f64,
    a0: f64,
    a1: f64,
    steps: usize,
    out_x: &mut [f64],
    out_y: &mut [f64],
    written: &mut usize,
) -> Option<()> {
    if r <= 0.0 {
        if *written >= out_x.len() || *written >= out_y.len() {
            return None;
        }
        out_x[*written] = cx;
        out_y[*written] = cy;
        *written += 1;
        return Some(());
    }
    if steps == 0 {
        return None;
    }
    for i in 0..steps {
        if *written >= out_x.len() || *written >= out_y.len() {
            return None;
        }
        let a = if steps == 1 {
            a0
        } else {
            a0 + (a1 - a0) * (i as f64) / ((steps - 1) as f64)
        };
        out_x[*written] = cx + r * a.cos();
        out_y[*written] = cy + r * a.sin();
        *written += 1;
    }
    Some(())
}

/// CW outline polygon for a rect with independent tip/base corner radii.
///
/// `tip_top` puts the value end (tip radius) on the top edge. Zero radii
/// collapse each corner to a single vertex (four-point rectangle).
pub fn rounded_rect_poly(
    x: f64,
    y: f64,
    w: f64,
    h: f64,
    r_tip: f64,
    r_base: f64,
    tip_top: bool,
    out_x: &mut [f64],
    out_y: &mut [f64],
) -> Option<usize> {
    let half_w = w.abs() * 0.5;
    let half_h = h.abs() * 0.5;
    let rt = r_tip.max(0.0).min(half_w).min(half_h);
    let rb = r_base.max(0.0).min(half_w).min(half_h);
    let (top_r, bot_r) = if tip_top { (rt, rb) } else { (rb, rt) };
    let mut written = 0usize;
    let pi = std::f64::consts::PI;
    push_arc(
        x + top_r,
        y + top_r,
        top_r,
        pi,
        1.5 * pi,
        ROUNDED_RECT_ARC_STEPS,
        out_x,
        out_y,
        &mut written,
    )?;
    push_arc(
        x + w - top_r,
        y + top_r,
        top_r,
        1.5 * pi,
        2.0 * pi,
        ROUNDED_RECT_ARC_STEPS,
        out_x,
        out_y,
        &mut written,
    )?;
    push_arc(
        x + w - bot_r,
        y + h - bot_r,
        bot_r,
        0.0,
        0.5 * pi,
        ROUNDED_RECT_ARC_STEPS,
        out_x,
        out_y,
        &mut written,
    )?;
    push_arc(
        x + bot_r,
        y + h - bot_r,
        bot_r,
        0.5 * pi,
        pi,
        ROUNDED_RECT_ARC_STEPS,
        out_x,
        out_y,
        &mut written,
    )?;
    Some(written)
}

/// Recover one exterior walk from a connected tessellated polygon.
///
/// Compatibility `_paint.triangle_mesh_boundary`: internal edges occur an even
/// number of times; odd-count edges form the boundary. A disconnected mesh or
/// a hole returns `None` so the packer keeps per-triangle `TriangleFace` rows.
pub fn triangle_mesh_boundary(
    x0: &[f64],
    y0: &[f64],
    x1: &[f64],
    y1: &[f64],
    x2: &[f64],
    y2: &[f64],
) -> Option<Vec<(f64, f64)>> {
    let n = x0
        .len()
        .min(y0.len())
        .min(x1.len())
        .min(y1.len())
        .min(x2.len())
        .min(y2.len());
    if n == 0 {
        return None;
    }
    let mut min = f64::INFINITY;
    let mut max = f64::NEG_INFINITY;
    let mut coords: Vec<(f64, f64)> = Vec::with_capacity(n.saturating_mul(3));
    for index in 0..n {
        let points = [
            (x0[index], y0[index]),
            (x1[index], y1[index]),
            (x2[index], y2[index]),
        ];
        for (x, y) in points {
            if !x.is_finite() || !y.is_finite() {
                return None;
            }
            min = min.min(x).min(y);
            max = max.max(x).max(y);
            coords.push((x, y));
        }
    }
    let span = max - min;
    let tolerance = (span * 2e-5).max(1e-12);
    let mut buckets: HashMap<(i64, i64), Vec<usize>> = HashMap::new();
    let mut points_by_key: Vec<(f64, f64)> = Vec::new();
    let vertex_key = |point: (f64, f64),
                      buckets: &mut HashMap<(i64, i64), Vec<usize>>,
                      points_by_key: &mut Vec<(f64, f64)>|
     -> usize {
        let cell = (
            (point.0 / tolerance).floor() as i64,
            (point.1 / tolerance).floor() as i64,
        );
        let mut best: Option<usize> = None;
        let mut best_distance = f64::INFINITY;
        for dx in -1..=1 {
            for dy in -1..=1 {
                if let Some(candidates) = buckets.get(&(cell.0 + dx, cell.1 + dy)) {
                    for &candidate in candidates {
                        let other = points_by_key[candidate];
                        let delta_x = (point.0 - other.0).abs();
                        let delta_y = (point.1 - other.1).abs();
                        if delta_x <= tolerance && delta_y <= tolerance {
                            let distance = delta_x * delta_x + delta_y * delta_y;
                            if distance < best_distance {
                                best = Some(candidate);
                                best_distance = distance;
                            }
                        }
                    }
                }
            }
        }
        if let Some(key) = best {
            return key;
        }
        let key = points_by_key.len();
        points_by_key.push(point);
        buckets.entry(cell).or_default().push(key);
        key
    };
    let mut edge_counts: HashMap<(usize, usize), usize> = HashMap::new();
    let mut edge_order: Vec<(usize, usize)> = Vec::new();
    for index in 0..n {
        let points = [
            coords[index * 3],
            coords[index * 3 + 1],
            coords[index * 3 + 2],
        ];
        let keys = [
            vertex_key(points[0], &mut buckets, &mut points_by_key),
            vertex_key(points[1], &mut buckets, &mut points_by_key),
            vertex_key(points[2], &mut buckets, &mut points_by_key),
        ];
        for edge_i in 0..3 {
            let start = keys[edge_i];
            let end = keys[(edge_i + 1) % 3];
            let edge = if start <= end {
                (start, end)
            } else {
                (end, start)
            };
            if !edge_counts.contains_key(&edge) {
                edge_order.push(edge);
            }
            *edge_counts.entry(edge).or_insert(0) += 1;
        }
    }
    let boundary: Vec<(usize, usize)> = edge_order
        .into_iter()
        .filter(|edge| edge.0 != edge.1 && edge_counts.get(edge).copied().unwrap_or(0) % 2 == 1)
        .collect();
    if boundary.len() < 3 {
        return None;
    }
    let mut adjacency: HashMap<usize, BTreeSet<usize>> = HashMap::new();
    for &(start, end) in &boundary {
        adjacency.entry(start).or_default().insert(end);
        adjacency.entry(end).or_default().insert(start);
    }
    if adjacency.values().any(|neighbors| neighbors.len() % 2 == 1) {
        return None;
    }
    let first = boundary[0].0;
    let mut stack = vec![first];
    let mut walk: Vec<usize> = Vec::new();
    while let Some(&current) = stack.last() {
        if let Some(neighbors) = adjacency.get_mut(&current) {
            if let Some(following) = neighbors.iter().copied().next() {
                neighbors.remove(&following);
                if let Some(back) = adjacency.get_mut(&following) {
                    back.remove(&current);
                }
                stack.push(following);
                continue;
            }
        }
        walk.push(stack.pop().expect("stack occupied"));
    }
    if walk.len() != boundary.len() + 1 || walk.first() != walk.last() {
        return None;
    }
    walk.reverse();
    Some(
        walk[..walk.len() - 1]
            .iter()
            .map(|&key| points_by_key[key])
            .collect(),
    )
}

#[cfg(test)]
mod tests {
    use super::*;

    fn assert_close(got: &[f64], expected: &[f64]) {
        assert_eq!(got.len(), expected.len());
        for (a, b) in got.iter().zip(expected) {
            assert!((a - b).abs() <= 1e-12 * (1.0 + b.abs()), "{a} != {b}");
        }
    }

    #[test]
    fn ribbon_edge_matches_python_steps_8() {
        let mut xs = [0.0; 9];
        let mut ys = [0.0; 9];
        assert_eq!(
            ribbon_edge(0.0, 10.0, 1.0, 3.0, 8, &mut xs, &mut ys),
            Some(9)
        );
        assert_close(
            &xs,
            &[
                0.0, 1.66015625, 2.96875, 4.04296875, 5.0, 5.95703125, 7.03125, 8.33984375, 10.0,
            ],
        );
        assert_close(
            &ys,
            &[
                1.0, 1.0859375, 1.3125, 1.6328125, 2.0, 2.3671875, 2.6875, 2.9140625, 3.0,
            ],
        );
    }

    #[test]
    fn ribbon_polygon_upper_then_reversed_lower() {
        let mut xs = [0.0; 10];
        let mut ys = [0.0; 10];
        assert_eq!(
            ribbon_polygon(0.0, 10.0, 0.0, 1.0, 2.0, 4.0, 4, &mut xs, &mut ys),
            Some(10)
        );
        assert_close(
            &xs,
            &[
                0.0, 2.96875, 5.0, 7.03125, 10.0, 10.0, 7.03125, 5.0, 2.96875, 0.0,
            ],
        );
        assert_close(
            &ys,
            &[
                1.0, 1.46875, 2.5, 3.53125, 4.0, 2.0, 1.6875, 1.0, 0.3125, 0.0,
            ],
        );
    }

    #[test]
    fn monotone_tangents_sign_change_zeros_interiors() {
        let x = [0.0, 1.0, 2.0, 3.0, 4.0];
        let y = [0.0, 1.0, 0.5, 2.0, 1.5];
        let mut m = [0.0; 5];
        assert_eq!(monotone_tangents(&x, &y, &mut m), Some(5));
        assert_close(&m, &[1.0, 0.0, 0.0, 0.0, -0.5]);
    }

    #[test]
    fn curve_flatten_keeps_knots_and_15_interiors() {
        let x = [0.0, 1.0, 2.0, 3.0, 4.0];
        let y = [0.0, 1.0, 0.5, 2.0, 1.5];
        let mut ox = [0.0; 65];
        let mut oy = [0.0; 65];
        assert_eq!(
            curve_flatten(&x, &y, BEZIER_STEPS, &mut ox, &mut oy),
            Some(65)
        );
        assert_eq!((ox[0], oy[0]), (0.0, 0.0));
        assert_eq!((ox[16], oy[16]), (1.0, 1.0));
        assert_eq!((ox[64], oy[64]), (4.0, 1.5));
        assert!((ox[1] - 0.0625).abs() < 1e-15);
        assert!((oy[1] - 0.066162109375).abs() < 1e-15);
    }

    #[test]
    fn curve_flatten_zero_width_span_is_a_single_vertex() {
        let x = [0.0, 0.0, 1.0];
        let y = [0.0, 1.0, 2.0];
        let mut ox = [0.0; 32];
        let mut oy = [0.0; 32];
        assert_eq!(
            curve_flatten(&x, &y, BEZIER_STEPS, &mut ox, &mut oy),
            Some(18)
        );
        assert_eq!((ox[0], oy[0]), (0.0, 0.0));
        assert_eq!((ox[1], oy[1]), (0.0, 1.0));
        assert_eq!((ox[17], oy[17]), (1.0, 2.0));
    }

    #[test]
    fn rounded_rect_zero_radii_is_four_corners() {
        let mut xs = [0.0; 20];
        let mut ys = [0.0; 20];
        assert_eq!(
            rounded_rect_poly(0.0, 0.0, 4.0, 3.0, 0.0, 0.0, true, &mut xs, &mut ys),
            Some(4)
        );
        assert_eq!(&xs[..4], &[0.0, 4.0, 4.0, 0.0]);
        assert_eq!(&ys[..4], &[0.0, 0.0, 3.0, 3.0]);
    }

    #[test]
    fn rounded_rect_independent_tip_base_radii() {
        let mut xs = [0.0; 20];
        let mut ys = [0.0; 20];
        assert_eq!(
            rounded_rect_poly(1.0, 2.0, 10.0, 6.0, 2.0, 1.0, true, &mut xs, &mut ys),
            Some(20)
        );
        assert!((xs[0] - 1.0).abs() < 1e-12);
        assert!((ys[0] - 4.0).abs() < 1e-12);
        assert!((xs[19] - 1.0).abs() < 1e-12);
        assert!((ys[19] - 7.0).abs() < 1e-12);
        assert!((xs[4] - 3.0).abs() < 1e-12);
        assert!((ys[4] - 2.0).abs() < 1e-12);
    }

    #[test]
    fn step_arrays_pre_mid_post_match_host_vertices() {
        let x = [0.0, 1.0, 2.0];
        let y = [10.0, 20.0, 30.0];
        let mut xs = [0.0; 8];
        let mut ys = [0.0; 8];
        assert_eq!(step_arrays_len(3, STEP_PRE), Some(5));
        assert_eq!(step_arrays(&x, &y, STEP_PRE, &mut xs, &mut ys), Some(5));
        assert_eq!(&xs[..5], &[0.0, 0.0, 1.0, 1.0, 2.0]);
        assert_eq!(&ys[..5], &[10.0, 20.0, 20.0, 30.0, 30.0]);
        assert_eq!(step_arrays_len(3, STEP_MID), Some(7));
        assert_eq!(step_arrays(&x, &y, STEP_MID, &mut xs, &mut ys), Some(7));
        assert_eq!(&xs[..7], &[0.0, 0.5, 0.5, 1.0, 1.5, 1.5, 2.0]);
        assert_eq!(&ys[..7], &[10.0, 10.0, 20.0, 20.0, 20.0, 30.0, 30.0]);
        assert_eq!(step_arrays_len(3, STEP_POST), Some(5));
        assert_eq!(step_arrays(&x, &y, STEP_POST, &mut xs, &mut ys), Some(5));
        assert_eq!(&xs[..5], &[0.0, 1.0, 1.0, 2.0, 2.0]);
        assert_eq!(&ys[..5], &[10.0, 10.0, 20.0, 20.0, 30.0]);
        assert_eq!(step_arrays(&x, &y, STEP_POST, &mut [], &mut []), Some(5));
        assert_eq!(
            step_arrays(&x[..1], &y[..1], STEP_PRE, &mut xs, &mut ys),
            Some(1)
        );
        assert_eq!(xs[0], 0.0);
        assert_eq!(ys[0], 10.0);
        assert!(step_arrays(&x, &y, 0, &mut xs, &mut ys).is_none());
        assert!(step_arrays(&x, &y[..2], STEP_POST, &mut xs, &mut ys).is_none());
        assert!(step_arrays_len(usize::MAX / 2, STEP_MID).is_none());
    }

    #[test]
    fn rejects_zero_steps_and_short_buffers() {
        let mut xs = [0.0; 1];
        let mut ys = [0.0; 1];
        assert!(ribbon_edge(0.0, 1.0, 0.0, 1.0, 0, &mut xs, &mut ys).is_none());
        assert!(ribbon_edge(0.0, 1.0, 0.0, 1.0, 8, &mut xs, &mut ys).is_none());
        assert!(monotone_tangents(&[0.0], &[0.0], &mut [0.0]).is_none());
        assert!(curve_flatten(&[0.0, 1.0], &[0.0], 16, &mut xs, &mut ys).is_none());
    }

    #[test]
    fn triangle_mesh_boundary_rejects_nonfinite() {
        assert!(
            triangle_mesh_boundary(&[0.0], &[0.0], &[1.0], &[0.0], &[f64::NAN], &[1.0],).is_none()
        );
        assert!(
            triangle_mesh_boundary(&[0.0], &[0.0], &[1.0], &[0.0], &[f64::INFINITY], &[1.0],)
                .is_none()
        );
    }

    #[test]
    fn triangle_mesh_boundary_merges_vertices_across_bucket_edges() {
        let lower = 0.9999e-5;
        let upper = 1.0001e-5;
        let boundary = triangle_mesh_boundary(
            &[lower, upper],
            &[lower, upper],
            &[1.0, 1.0],
            &[0.0, 1.0],
            &[1.0, 0.0],
            &[1.0, 1.0],
        )
        .unwrap();
        assert_eq!(boundary.len(), 4);
    }

    #[test]
    fn triangle_mesh_boundary_joins_a_quad() {
        let boundary = triangle_mesh_boundary(
            &[0.0, 1.0],
            &[0.0, 0.0],
            &[1.0, 1.0],
            &[0.0, 1.0],
            &[0.0, 0.0],
            &[1.0, 1.0],
        )
        .unwrap();
        assert_eq!(boundary.len(), 4);
    }
}
