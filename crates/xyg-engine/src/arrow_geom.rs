//! Annotation arrow path geometry (ABI 217).
//!
//! Owns matplotlib connectionstyle control points, label-clearance trim,
//! quadratic/elbow shaft samples, tapered shafts, and endpoint decorations
//! so Python `_arrowgeom.py` and ChartView `51_annotations.ts` cannot drift.
//! Hosts still parse comma-separated `start_offset` / `label_clear` strings.

use std::f64::consts::PI;

/// Packed style length: start_ox, start_oy, angle_a, angle_b, curve,
/// gap_start, gap_end, clear_l, clear_r, clear_u, clear_d, elbow.
pub const ARROW_STYLE_LEN: usize = 12;

/// Packed geometry length: p0x, p0y, p1x, p1y, cx, cy, has_control,
/// dir0x, dir0y, dir1x, dir1y.
pub const ARROW_GEOM_LEN: usize = 11;

/// Default quadratic shaft samples (`range(24 + 1)` in Python / JS).
pub const ARROW_SHAFT_SAMPLES: usize = 24;

/// Hard ceiling on an authored shaft sample count.
pub const ARROW_MAX_SAMPLES: usize = 4096;

#[derive(Clone, Copy, Debug, PartialEq)]
pub struct ArrowGeom {
    pub p0: (f64, f64),
    pub p1: (f64, f64),
    pub control: Option<(f64, f64)>,
    pub elbow: bool,
    pub dir0: (f64, f64),
    pub dir1: (f64, f64),
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum ArrowEndKind {
    None,
    Fill,
    Stroke,
}

fn toward(px: f64, py: f64, qx: f64, qy: f64) -> (f64, f64) {
    let d = (qx - px).hypot(qy - py);
    let d = if d == 0.0 { 1.0 } else { d };
    ((qx - px) / d, (qy - py) / d)
}

fn label_clear_exit(style: &[f64], tangent: (f64, f64)) -> f64 {
    let extents = [style[7], style[8], style[9], style[10]];
    if extents.iter().any(|part| !part.is_finite() || *part < 0.0) {
        return 0.0;
    }
    let [left, right, up, down] = extents;
    let (tx, ty) = tangent;
    let exit_x = if tx > 1e-9 {
        right / tx
    } else if tx < -1e-9 {
        left / -tx
    } else {
        f64::INFINITY
    };
    let exit_y = if ty > 1e-9 {
        down / ty
    } else if ty < -1e-9 {
        up / -ty
    } else {
        f64::INFINITY
    };
    let exit_distance = exit_x.min(exit_y);
    if exit_distance.is_finite() {
        exit_distance
    } else {
        0.0
    }
}

fn gap_or_zero(value: f64) -> f64 {
    if value.is_finite() {
        value.max(0.0)
    } else {
        0.0
    }
}

/// Connectionstyle control point, gaps, and endpoint tangents.
pub fn arrow_geometry(x0: f64, y0: f64, x1: f64, y1: f64, style: &[f64]) -> Option<ArrowGeom> {
    if !style.is_empty() && style.len() != ARROW_STYLE_LEN {
        return None;
    }
    let style = if style.is_empty() {
        [f64::NAN; ARROW_STYLE_LEN]
    } else {
        let mut packed = [0.0; ARROW_STYLE_LEN];
        packed.copy_from_slice(style);
        packed
    };
    let mut x0 = x0;
    let mut y0 = y0;
    if style[0].is_finite() && style[1].is_finite() {
        x0 += style[0];
        y0 += style[1];
    }
    let angle_a = style[2];
    let angle_b = style[3];
    let curve = style[4];
    let mut control = None;
    if angle_a.is_finite() && angle_b.is_finite() {
        let a = -angle_a * PI / 180.0;
        let b = -angle_b * PI / 180.0;
        let denom = a.cos() * b.sin() - a.sin() * b.cos();
        if denom.abs() > 1e-6 {
            let t = ((x1 - x0) * b.sin() - (y1 - y0) * b.cos()) / denom;
            control = Some((x0 + t * a.cos(), y0 + t * a.sin()));
        }
    } else if curve.is_finite() && curve != 0.0 {
        let dx = x1 - x0;
        let dy = y1 - y0;
        control = Some(((x0 + x1) / 2.0 + curve * dy, (y0 + y1) / 2.0 - curve * dx));
    }
    let t0 = match control {
        Some((cx, cy)) => toward(x0, y0, cx, cy),
        None => toward(x0, y0, x1, y1),
    };
    let t1 = match control {
        Some((cx, cy)) => toward(x1, y1, cx, cy),
        None => toward(x1, y1, x0, y0),
    };
    let gap_start = gap_or_zero(style[5]).max(label_clear_exit(&style, t0));
    let gap_end = gap_or_zero(style[6]);
    let trim = gap_start + gap_end < (x1 - x0).hypot(y1 - y0) * 0.9;
    let p0 = if trim {
        (x0 + gap_start * t0.0, y0 + gap_start * t0.1)
    } else {
        (x0, y0)
    };
    let p1 = if trim {
        (x1 + gap_end * t1.0, y1 + gap_end * t1.1)
    } else {
        (x1, y1)
    };
    let dir1 = match control {
        Some((cx, cy)) => toward(cx, cy, p1.0, p1.1),
        None => toward(p0.0, p0.1, p1.0, p1.1),
    };
    let dir0 = match control {
        Some((cx, cy)) => toward(cx, cy, p0.0, p0.1),
        None => toward(p1.0, p1.1, p0.0, p0.1),
    };
    Some(ArrowGeom {
        p0,
        p1,
        control,
        elbow: style[11].is_finite() && style[11] != 0.0,
        dir0,
        dir1,
    })
}

pub fn write_arrow_geometry(geom: &ArrowGeom, out: &mut [f64]) -> Option<usize> {
    if out.len() < ARROW_GEOM_LEN {
        return None;
    }
    out[0] = geom.p0.0;
    out[1] = geom.p0.1;
    out[2] = geom.p1.0;
    out[3] = geom.p1.1;
    match geom.control {
        Some((cx, cy)) => {
            out[4] = cx;
            out[5] = cy;
            out[6] = 1.0;
        }
        None => {
            out[4] = 0.0;
            out[5] = 0.0;
            out[6] = 0.0;
        }
    }
    out[7] = geom.dir0.0;
    out[8] = geom.dir0.1;
    out[9] = geom.dir1.0;
    out[10] = geom.dir1.1;
    Some(ARROW_GEOM_LEN)
}

fn shaft_count(control: bool, elbow: bool, samples: usize) -> usize {
    if !control {
        2
    } else if elbow {
        3
    } else {
        samples + 1
    }
}

/// Shaft polyline. `samples == 0` selects [`ARROW_SHAFT_SAMPLES`].
pub fn arrow_shaft_points(
    p0: (f64, f64),
    p1: (f64, f64),
    control: Option<(f64, f64)>,
    elbow: bool,
    samples: usize,
    out_x: &mut [f64],
    out_y: &mut [f64],
) -> Option<usize> {
    let samples = if samples == 0 {
        ARROW_SHAFT_SAMPLES
    } else {
        samples
    };
    if samples > ARROW_MAX_SAMPLES {
        return None;
    }
    let n = shaft_count(control.is_some(), elbow, samples);
    if out_x.is_empty() && out_y.is_empty() {
        return Some(n);
    }
    if out_x.len() < n || out_y.len() < n {
        return None;
    }
    match control {
        None => {
            out_x[0] = p0.0;
            out_y[0] = p0.1;
            out_x[1] = p1.0;
            out_y[1] = p1.1;
        }
        Some((cx, cy)) if elbow => {
            out_x[0] = p0.0;
            out_y[0] = p0.1;
            out_x[1] = cx;
            out_y[1] = cy;
            out_x[2] = p1.0;
            out_y[2] = p1.1;
        }
        Some((cx, cy)) => {
            for index in 0..=samples {
                let t = index as f64 / samples as f64;
                let u = 1.0 - t;
                out_x[index] = u * u * p0.0 + 2.0 * u * t * cx + t * t * p1.0;
                out_y[index] = u * u * p0.1 + 2.0 * u * t * cy + t * t * p1.1;
            }
        }
    }
    Some(n)
}

fn end_kind(style: &str) -> ArrowEndKind {
    match style {
        "none" => ArrowEndKind::None,
        "bar" | "v" => ArrowEndKind::Stroke,
        _ => ArrowEndKind::Fill,
    }
}

fn end_count(style: &str) -> usize {
    match style {
        "none" => 0,
        "bar" => 2,
        _ => 3,
    }
}

/// One endpoint decoration. `direction` is the unit tangent INTO the point.
pub fn arrow_end_decoration(
    point: (f64, f64),
    direction: (f64, f64),
    style: &str,
    head: f64,
    out_x: &mut [f64],
    out_y: &mut [f64],
) -> Option<(ArrowEndKind, usize)> {
    let kind = end_kind(style);
    let n = end_count(style);
    if out_x.is_empty() && out_y.is_empty() {
        return Some((kind, n));
    }
    if n == 0 {
        return Some((kind, 0));
    }
    if out_x.len() < n || out_y.len() < n {
        return None;
    }
    let (px, py) = point;
    let angle = direction.1.atan2(direction.0);
    if style == "bar" {
        out_x[0] = px - (head / 2.0) * angle.sin();
        out_y[0] = py + (head / 2.0) * angle.cos();
        out_x[1] = px + (head / 2.0) * angle.sin();
        out_y[1] = py - (head / 2.0) * angle.cos();
        return Some((kind, 2));
    }
    let mut wings = [(0.0, 0.0); 2];
    for (i, side) in [1.0, -1.0].into_iter().enumerate() {
        wings[i] = (
            px - head * (angle - side * PI / 6.0).cos(),
            py - head * (angle - side * PI / 6.0).sin(),
        );
    }
    if style == "v" {
        out_x[0] = wings[0].0;
        out_y[0] = wings[0].1;
        out_x[1] = px;
        out_y[1] = py;
        out_x[2] = wings[1].0;
        out_y[2] = wings[1].1;
    } else {
        out_x[0] = px;
        out_y[0] = py;
        out_x[1] = wings[0].0;
        out_y[1] = wings[0].1;
        out_x[2] = wings[1].0;
        out_y[2] = wings[1].1;
    }
    Some((kind, 3))
}

/// Filled taper whose width interpolates from `width_start` to `width_end`.
pub fn arrow_taper_polygon(
    x: &[f64],
    y: &[f64],
    width_start: f64,
    width_end: f64,
    out_x: &mut [f64],
    out_y: &mut [f64],
) -> Option<usize> {
    if x.len() != y.len() {
        return None;
    }
    let count = x.len();
    let n = count.saturating_mul(2);
    if out_x.is_empty() && out_y.is_empty() {
        return Some(n);
    }
    if out_x.len() < n || out_y.len() < n {
        return None;
    }
    if count == 0 {
        return Some(0);
    }
    let denom = (count - 1).max(1) as f64;
    for index in 0..count {
        let px = x[index];
        let py = y[index];
        let prev = if index == 0 { 0 } else { index - 1 };
        let next = (index + 1).min(count - 1);
        let d = (x[next] - x[prev]).hypot(y[next] - y[prev]);
        let d = if d == 0.0 { 1.0 } else { d };
        let nx = -(y[next] - y[prev]) / d;
        let ny = (x[next] - x[prev]) / d;
        let half = (width_start + (width_end - width_start) * (index as f64 / denom)) / 2.0;
        out_x[index] = px + half * nx;
        out_y[index] = py + half * ny;
        out_x[n - 1 - index] = px - half * nx;
        out_y[n - 1 - index] = py - half * ny;
    }
    Some(n)
}

/// Remove `trim` px of arclength from the polyline's end.
pub fn arrow_trim_polyline_end(
    x: &[f64],
    y: &[f64],
    trim: f64,
    out_x: &mut [f64],
    out_y: &mut [f64],
) -> Option<usize> {
    if x.len() != y.len() {
        return None;
    }
    let n = x.len();
    if trim <= 0.0 || n < 2 {
        if out_x.is_empty() && out_y.is_empty() {
            return Some(n);
        }
        if out_x.len() < n || out_y.len() < n {
            return None;
        }
        out_x[..n].copy_from_slice(x);
        out_y[..n].copy_from_slice(y);
        return Some(n);
    }
    let mut xs: Vec<f64> = x.to_vec();
    let mut ys: Vec<f64> = y.to_vec();
    let mut remaining = trim;
    while xs.len() >= 2 {
        let last = xs.len() - 1;
        let ax = xs[last - 1];
        let ay = ys[last - 1];
        let bx = xs[last];
        let by = ys[last];
        let seg = (bx - ax).hypot(by - ay);
        if seg > remaining {
            let t = 1.0 - remaining / seg;
            xs[last] = ax + t * (bx - ax);
            ys[last] = ay + t * (by - ay);
            break;
        }
        remaining -= seg;
        xs.pop();
        ys.pop();
    }
    if xs.len() < 2 {
        xs = vec![x[0], x[0]];
        ys = vec![y[0], y[0]];
    }
    let written = xs.len();
    if out_x.is_empty() && out_y.is_empty() {
        return Some(written);
    }
    if out_x.len() < written || out_y.len() < written {
        return None;
    }
    out_x[..written].copy_from_slice(&xs);
    out_y[..written].copy_from_slice(&ys);
    Some(written)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn packed_clear(left: f64, right: f64, up: f64, down: f64) -> [f64; ARROW_STYLE_LEN] {
        let mut style = [f64::NAN; ARROW_STYLE_LEN];
        style[7] = left;
        style[8] = right;
        style[9] = up;
        style[10] = down;
        style
    }

    #[test]
    fn label_clear_trims_start_along_departure_tangent() {
        let geom =
            arrow_geometry(0.0, 0.0, 300.0, 0.0, &packed_clear(2.8, 90.0, 2.8, 17.0)).unwrap();
        assert!((geom.p0.0 - 90.0).abs() < 1e-12);
        assert_eq!(geom.p0.1, 0.0);
        assert_eq!(geom.p1, (300.0, 0.0));
    }

    #[test]
    fn label_clear_is_direction_dependent() {
        let geom =
            arrow_geometry(0.0, 0.0, -300.0, 0.0, &packed_clear(2.8, 90.0, 2.8, 17.0)).unwrap();
        assert!((geom.p0.0 + 2.8).abs() < 1e-12);
    }

    #[test]
    fn label_clear_never_swallows_short_arrows() {
        let geom =
            arrow_geometry(0.0, 0.0, 50.0, 0.0, &packed_clear(2.8, 90.0, 2.8, 17.0)).unwrap();
        assert_eq!(geom.p0, (0.0, 0.0));
    }

    #[test]
    fn elbow_shaft_is_three_points() {
        let mut style = [f64::NAN; ARROW_STYLE_LEN];
        style[2] = 0.0;
        style[3] = 90.0;
        style[11] = 1.0;
        let geom = arrow_geometry(0.0, 0.0, 10.0, 10.0, &style).unwrap();
        assert!(geom.elbow);
        assert!(geom.control.is_some());
        let mut xs = [0.0; 3];
        let mut ys = [0.0; 3];
        let n = arrow_shaft_points(
            geom.p0,
            geom.p1,
            geom.control,
            geom.elbow,
            24,
            &mut xs,
            &mut ys,
        )
        .unwrap();
        assert_eq!(n, 3);
        assert_eq!((xs[0], ys[0]), (0.0, 0.0));
        assert_eq!((xs[2], ys[2]), (10.0, 10.0));
    }

    #[test]
    fn quadratic_shaft_keeps_25_samples() {
        let mut style = [f64::NAN; ARROW_STYLE_LEN];
        style[4] = 0.3;
        let geom = arrow_geometry(0.0, 0.0, 10.0, 10.0, &style).unwrap();
        let n = arrow_shaft_points(
            geom.p0,
            geom.p1,
            geom.control,
            geom.elbow,
            0,
            &mut [],
            &mut [],
        )
        .unwrap();
        assert_eq!(n, 25);
    }

    #[test]
    fn trim_that_eats_the_polyline_keeps_a_degenerate_pair() {
        let x = [0.0, 1.0];
        let y = [0.0, 0.0];
        let mut ox = [0.0; 2];
        let mut oy = [0.0; 2];
        let n = arrow_trim_polyline_end(&x, &y, 10.0, &mut ox, &mut oy).unwrap();
        assert_eq!(n, 2);
        assert_eq!(ox, [0.0, 0.0]);
        assert_eq!(oy, [0.0, 0.0]);
    }
}
