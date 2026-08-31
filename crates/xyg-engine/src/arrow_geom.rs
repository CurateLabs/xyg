//! Annotation arrow path geometry (ABI 217) and style CSV pack (ABI 254).
//!
//! Owns matplotlib connectionstyle control points, label-clearance trim,
//! quadratic/elbow shaft samples, tapered shafts, and endpoint decorations
//! so Python `_arrowgeom.py` and ChartView `51_annotations.ts` cannot drift.
//! ABI 254 owns comma-separated `start_offset` / `label_clear` packing so
//! Python `_pack_style` and Node `packArrowStyle` cannot drift. ChartView
//! still parses those strings until WASM.

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

/// Parse a comma-separated f64 list. Empty tokens, non-finite parts, and
/// invalid floats fail the whole string (Python `_csv_floats` / `_number`).
fn csv_floats(text: &str) -> Option<Vec<f64>> {
    let mut values = Vec::new();
    for part in text.split(',') {
        let Ok(value) = part.trim().parse::<f64>() else {
            return None;
        };
        if !value.is_finite() {
            return None;
        }
        values.push(value);
    }
    Some(values)
}

/// Packed style: start_ox/oy, angle_a/b, curve, gap_start/end,
/// clear_l/r/u/d, elbow. NaN = absent. `start_offset` needs exactly two
/// finite parts; `label_clear` needs exactly four non-negative finite parts.
pub fn arrow_style_pack(
    start_offset: Option<&str>,
    start_angle: f64,
    end_angle: f64,
    curve: f64,
    gap_start: f64,
    gap_end: f64,
    label_clear: Option<&str>,
    elbow: f64,
    out: &mut [f64],
) -> bool {
    if out.len() != ARROW_STYLE_LEN {
        return false;
    }
    out.fill(f64::NAN);
    if let Some(text) = start_offset {
        if let Some(parts) = csv_floats(text) {
            if parts.len() == 2 {
                out[0] = parts[0];
                out[1] = parts[1];
            }
        }
    }
    if start_angle.is_finite() {
        out[2] = start_angle;
    }
    if end_angle.is_finite() {
        out[3] = end_angle;
    }
    if curve.is_finite() {
        out[4] = curve;
    }
    if gap_start.is_finite() {
        out[5] = gap_start;
    }
    if gap_end.is_finite() {
        out[6] = gap_end;
    }
    if let Some(text) = label_clear {
        if let Some(parts) = csv_floats(text) {
            if parts.len() == 4 && parts.iter().all(|value| *value >= 0.0) {
                out[7] = parts[0];
                out[8] = parts[1];
                out[9] = parts[2];
                out[10] = parts[3];
            }
        }
    }
    if elbow.is_finite() {
        out[11] = elbow;
    }
    true
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

/// Meta slots for [`arrow_shapes`] / ABI 257: shaft count, taper count,
/// head kind, head count, tail kind, tail count. Shaft and taper are
/// mutually exclusive (one count is zero).
pub const ARROW_SHAPES_META_LEN: usize = 6;

fn authored_head_size(raw: f64) -> f64 {
    let base = if raw.is_finite() { raw } else { 8.0 };
    base.max(4.0)
}

fn end_kind_code(kind: ArrowEndKind) -> i32 {
    match kind {
        ArrowEndKind::None => 0,
        ArrowEndKind::Fill => 1,
        ArrowEndKind::Stroke => 2,
    }
}

/// Shaft or taper polyline plus endpoint decorations for one arrow/callout.
///
/// `style` is the 12-slot ABI 254 pack. `head_size` NaN selects 8.0 before
/// the `max(4.0, …)` clamp. `width_start` / `width_end` NaN mean no taper.
/// `elbow_authoring` mirrors Python `style.get("elbow")` for shaft sampling.
/// Probe with empty `out_x`/`out_y`; returns the total point count.
pub fn arrow_shapes(
    x0: f64,
    y0: f64,
    x1: f64,
    y1: f64,
    style: &[f64],
    head_style: &str,
    tail_style: &str,
    head_size: f64,
    width_start: f64,
    width_end: f64,
    elbow_authoring: bool,
    out_meta: &mut [i32],
    out_x: &mut [f64],
    out_y: &mut [f64],
) -> Option<usize> {
    if out_meta.len() < ARROW_SHAPES_META_LEN {
        return None;
    }
    let geom = arrow_geometry(x0, y0, x1, y1, style)?;
    let head = authored_head_size(head_size);
    let head_style = if head_style.is_empty() {
        "triangle"
    } else {
        head_style
    };
    let tail_style = if tail_style.is_empty() {
        "none"
    } else {
        tail_style
    };

    let shaft_n = arrow_shaft_points(
        geom.p0,
        geom.p1,
        geom.control,
        elbow_authoring,
        0,
        &mut [],
        &mut [],
    )?;
    let mut shaft_x = vec![0.0; shaft_n];
    let mut shaft_y = vec![0.0; shaft_n];
    arrow_shaft_points(
        geom.p0,
        geom.p1,
        geom.control,
        elbow_authoring,
        0,
        &mut shaft_x,
        &mut shaft_y,
    )?;

    let taper_requested = width_start.is_finite() || width_end.is_finite();
    let mut taper_x: Vec<f64> = Vec::new();
    let mut taper_y: Vec<f64> = Vec::new();
    if taper_requested {
        if head_style == "triangle" {
            let trim = head * (PI / 6.0).cos();
            let trimmed_n = arrow_trim_polyline_end(&shaft_x, &shaft_y, trim, &mut [], &mut [])?;
            let mut trimmed_x = vec![0.0; trimmed_n];
            let mut trimmed_y = vec![0.0; trimmed_n];
            arrow_trim_polyline_end(&shaft_x, &shaft_y, trim, &mut trimmed_x, &mut trimmed_y)?;
            shaft_x = trimmed_x;
            shaft_y = trimmed_y;
        }
        let w0 = if width_start.is_finite() { width_start } else { 1.0 };
        let w1 = if width_end.is_finite() { width_end } else { 1.0 };
        let taper_n = arrow_taper_polygon(&shaft_x, &shaft_y, w0, w1, &mut [], &mut [])?;
        taper_x.resize(taper_n, 0.0);
        taper_y.resize(taper_n, 0.0);
        arrow_taper_polygon(&shaft_x, &shaft_y, w0, w1, &mut taper_x, &mut taper_y)?;
    }

    let (head_kind, head_n) = arrow_end_decoration(
        geom.p1,
        geom.dir1,
        head_style,
        head,
        &mut [],
        &mut [],
    )?;
    let mut head_x = vec![0.0; head_n];
    let mut head_y = vec![0.0; head_n];
    if head_n > 0 {
        arrow_end_decoration(
            geom.p1,
            geom.dir1,
            head_style,
            head,
            &mut head_x,
            &mut head_y,
        )?;
    }

    let (tail_kind, tail_n) = arrow_end_decoration(
        geom.p0,
        geom.dir0,
        tail_style,
        head,
        &mut [],
        &mut [],
    )?;
    let mut tail_x = vec![0.0; tail_n];
    let mut tail_y = vec![0.0; tail_n];
    if tail_n > 0 {
        arrow_end_decoration(
            geom.p0,
            geom.dir0,
            tail_style,
            head,
            &mut tail_x,
            &mut tail_y,
        )?;
    }

    let shaft_count = if taper_requested { 0 } else { shaft_n };
    let taper_count = if taper_requested { taper_x.len() } else { 0 };
    let total = shaft_count + taper_count + head_n + tail_n;

    out_meta[0] = i32::try_from(shaft_count).ok()?;
    out_meta[1] = i32::try_from(taper_count).ok()?;
    out_meta[2] = end_kind_code(head_kind);
    out_meta[3] = i32::try_from(head_n).ok()?;
    out_meta[4] = end_kind_code(tail_kind);
    out_meta[5] = i32::try_from(tail_n).ok()?;

    if out_x.is_empty() && out_y.is_empty() {
        return Some(total);
    }
    if out_x.len() < total || out_y.len() < total {
        return None;
    }

    let mut offset = 0usize;
    if shaft_count > 0 {
        for index in 0..shaft_count {
            out_x[offset + index] = shaft_x[index];
            out_y[offset + index] = shaft_y[index];
        }
        offset += shaft_count;
    }
    if taper_count > 0 {
        for index in 0..taper_count {
            out_x[offset + index] = taper_x[index];
            out_y[offset + index] = taper_y[index];
        }
        offset += taper_count;
    }
    if head_n > 0 {
        for index in 0..head_n {
            out_x[offset + index] = head_x[index];
            out_y[offset + index] = head_y[index];
        }
        offset += head_n;
    }
    if tail_n > 0 {
        for index in 0..tail_n {
            out_x[offset + index] = tail_x[index];
            out_y[offset + index] = tail_y[index];
        }
    }
    Some(total)
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
    fn style_pack_writes_finite_csv_and_numeric_slots() {
        let mut packed = [0.0; ARROW_STYLE_LEN];
        assert!(arrow_style_pack(
            Some("50,-7"),
            10.0,
            90.0,
            0.3,
            1.0,
            2.0,
            Some("2.8,90,2.8,17"),
            1.0,
            &mut packed,
        ));
        assert_eq!(packed[0], 50.0);
        assert_eq!(packed[1], -7.0);
        assert_eq!(packed[2], 10.0);
        assert_eq!(packed[3], 90.0);
        assert_eq!(packed[4], 0.3);
        assert_eq!(packed[5], 1.0);
        assert_eq!(packed[6], 2.0);
        assert_eq!(&packed[7..11], &[2.8, 90.0, 2.8, 17.0]);
        assert_eq!(packed[11], 1.0);
    }

    #[test]
    fn style_pack_rejects_malformed_start_offset() {
        for bad in ["", "5", "5,x", "1,", "1,2,3", "nan,1", "1,inf"] {
            let mut packed = [0.0; ARROW_STYLE_LEN];
            assert!(arrow_style_pack(
                Some(bad),
                f64::NAN,
                f64::NAN,
                f64::NAN,
                f64::NAN,
                f64::NAN,
                None,
                f64::NAN,
                &mut packed,
            ));
            assert!(packed[0].is_nan());
            assert!(packed[1].is_nan());
        }
    }

    #[test]
    fn style_pack_rejects_malformed_label_clear() {
        for bad in ["", "1,2,3", "1,2,3,x", "1,2,3,-4", "1,2,3,", "1,,2,3"] {
            let mut packed = [0.0; ARROW_STYLE_LEN];
            assert!(arrow_style_pack(
                None,
                f64::NAN,
                f64::NAN,
                f64::NAN,
                f64::NAN,
                f64::NAN,
                Some(bad),
                f64::NAN,
                &mut packed,
            ));
            assert!(packed[7..11].iter().all(|value| value.is_nan()));
        }
    }

    #[test]
    fn style_pack_trims_csv_whitespace() {
        let mut packed = [0.0; ARROW_STYLE_LEN];
        assert!(arrow_style_pack(
            Some(" 50 , -7 "),
            f64::NAN,
            f64::NAN,
            f64::NAN,
            f64::NAN,
            f64::NAN,
            Some(" 2.8, 90, 2.8, 17 "),
            f64::NAN,
            &mut packed,
        ));
        assert_eq!(packed[0], 50.0);
        assert_eq!(packed[1], -7.0);
        assert_eq!(&packed[7..11], &[2.8, 90.0, 2.8, 17.0]);
    }

    #[test]
    fn style_pack_rejects_wrong_out_len() {
        let mut packed = [0.0; 11];
        assert!(!arrow_style_pack(
            None,
            f64::NAN,
            f64::NAN,
            f64::NAN,
            f64::NAN,
            f64::NAN,
            None,
            f64::NAN,
            &mut packed,
        ));
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

    #[test]
    fn arrow_shapes_linear_shaft_and_triangle_head() {
        let style = [f64::NAN; ARROW_STYLE_LEN];
        let mut meta = [0i32; ARROW_SHAPES_META_LEN];
        let total = arrow_shapes(
            0.0,
            0.0,
            100.0,
            0.0,
            &style,
            "triangle",
            "none",
            f64::NAN,
            f64::NAN,
            f64::NAN,
            false,
            &mut meta,
            &mut [],
            &mut [],
        )
        .unwrap();
        assert_eq!(meta[0], 2);
        assert_eq!(meta[1], 0);
        assert_eq!(meta[2], 1);
        assert_eq!(meta[3], 3);
        assert_eq!(meta[4], 0);
        assert_eq!(meta[5], 0);
        assert_eq!(total, 5);
        let mut xs = vec![0.0; total];
        let mut ys = vec![0.0; total];
        arrow_shapes(
            0.0,
            0.0,
            100.0,
            0.0,
            &style,
            "triangle",
            "none",
            f64::NAN,
            f64::NAN,
            f64::NAN,
            false,
            &mut meta,
            &mut xs,
            &mut ys,
        )
        .unwrap();
        assert_eq!(xs[0], 0.0);
        assert_eq!(xs[1], 100.0);
        assert_eq!(xs[2], 100.0);
    }

    #[test]
    fn arrow_shapes_taper_replaces_shaft() {
        let style = [f64::NAN; ARROW_STYLE_LEN];
        let mut meta = [0i32; ARROW_SHAPES_META_LEN];
        let total = arrow_shapes(
            0.0,
            0.0,
            40.0,
            0.0,
            &style,
            "triangle",
            "none",
            8.0,
            2.0,
            1.0,
            false,
            &mut meta,
            &mut [],
            &mut [],
        )
        .unwrap();
        assert_eq!(meta[0], 0);
        assert!(meta[1] > 0);
        assert_eq!(meta[2], 1);
        assert_eq!(total, meta[1] as usize + 3);
    }
}
