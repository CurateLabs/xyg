//! Compatibility geometry helpers (M2 #279 / ABI 121).
//!
//! One cubic, one Fritsch–Carlson tangent construction, and one rounded-rect
//! tessellation shared by Scene ribbon expansion and the host SVG/raster
//! fallbacks. Hosts still map through their scale objects; this module owns
//! the coordinate-free flattening so Python and Node cannot drift.

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
    fn rejects_zero_steps_and_short_buffers() {
        let mut xs = [0.0; 1];
        let mut ys = [0.0; 1];
        assert!(ribbon_edge(0.0, 1.0, 0.0, 1.0, 0, &mut xs, &mut ys).is_none());
        assert!(ribbon_edge(0.0, 1.0, 0.0, 1.0, 8, &mut xs, &mut ys).is_none());
        assert!(monotone_tangents(&[0.0], &[0.0], &mut [0.0]).is_none());
        assert!(curve_flatten(&[0.0, 1.0], &[0.0], 16, &mut xs, &mut ys).is_none());
    }
}
