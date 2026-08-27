//! Polar (theta, r) → screen-pixel projection — spec/design/polar-axes.md §3.
//!
//! Screen space grows downward (`cy - rn * sin(a)`). Full-turn radius uses
//! `min(w, h) / 2` centred in the plot rect; partial sectors fill the bbox.

use crate::scene::{AxisScale, ScaleKind};

/// Packed layout/projection metrics written by [`polar_layout`].
pub const POLAR_METRICS_LEN: usize = 23;

pub const METRIC_CX: usize = 0;
pub const METRIC_CY: usize = 1;
pub const METRIC_RADIUS: usize = 2;
pub const METRIC_ZERO: usize = 3;
pub const METRIC_DIR: usize = 4;
pub const METRIC_UNIT_SCALE: usize = 5;
pub const METRIC_SECTOR_START: usize = 6;
pub const METRIC_SECTOR_END: usize = 7;
pub const METRIC_SECTOR_SPAN: usize = 8;
pub const METRIC_TURN: usize = 9;
pub const METRIC_FULL_SECTOR: usize = 10;
pub const METRIC_R_LO_COORD: usize = 11;
pub const METRIC_R_HI_COORD: usize = 12;
pub const METRIC_R_ORIGIN_COORD: usize = 13;
pub const METRIC_HOLE: usize = 14;
pub const METRIC_N_CATEGORIES: usize = 15;
pub const METRIC_SECTOR_A0: usize = 16;
pub const METRIC_SECTOR_A1: usize = 17;
pub const METRIC_R_LO: usize = 18;
pub const METRIC_R_HI: usize = 19;
pub const METRIC_R_SCALE_KIND: usize = 20;
pub const METRIC_R_CONSTANT: usize = 21;
pub const METRIC_R_MASK_NONPOSITIVE: usize = 22;

const THETA_ZERO_E: f64 = 0.0;
const THETA_ZERO_N: f64 = std::f64::consts::FRAC_PI_2;
const THETA_ZERO_W: f64 = std::f64::consts::PI;
const THETA_ZERO_S: f64 = -std::f64::consts::FRAC_PI_2;

/// Cardinal theta-zero labels accepted by hosts before packing a numeric angle.
pub fn theta_zero_from_label(label: &[u8]) -> Option<f64> {
    match label {
        b"E" => Some(THETA_ZERO_E),
        b"N" => Some(THETA_ZERO_N),
        b"W" => Some(THETA_ZERO_W),
        b"S" => Some(THETA_ZERO_S),
        _ => None,
    }
}

/// Inputs for disc layout and radial scale setup.
#[derive(Clone, Copy, Debug)]
pub struct PolarLayoutInput {
    pub plot_x: f64,
    pub plot_y: f64,
    pub plot_w: f64,
    pub plot_h: f64,
    /// 0 = radians, 1 = degrees.
    pub theta_unit: u32,
    /// Zero direction in radians, ccw from East.
    pub theta_zero: f64,
    /// 0 = counterclockwise, 1 = clockwise.
    pub theta_direction: u32,
    pub sector_start: f64,
    pub sector_end: f64,
    pub n_categories: u32,
    pub r_lo: f64,
    pub r_hi: f64,
    /// `NaN` selects `r_lo`.
    pub r_origin: f64,
    pub hole: f64,
    /// 0 = linear, 1 = log, 2 = symlog.
    pub r_scale_kind: u32,
    pub r_constant: f64,
    pub r_mask_nonpositive: bool,
}

fn scale_kind(code: u32) -> Option<ScaleKind> {
    match code {
        0 => Some(ScaleKind::Linear),
        1 => Some(ScaleKind::Log),
        2 => Some(ScaleKind::SymLog),
        _ => None,
    }
}

fn unit_scale(theta_unit: u32) -> Option<f64> {
    match theta_unit {
        0 => Some(1.0),
        1 => Some(std::f64::consts::PI / 180.0),
        _ => None,
    }
}

fn turn(theta_unit: u32) -> Option<f64> {
    match theta_unit {
        0 => Some(2.0 * std::f64::consts::PI),
        1 => Some(360.0),
        _ => None,
    }
}

fn direction_sign(theta_direction: u32) -> Option<f64> {
    match theta_direction {
        0 => Some(1.0),
        1 => Some(-1.0),
        _ => None,
    }
}

fn build_r_scale(metrics: &[f64]) -> Option<AxisScale> {
    let kind = scale_kind(metrics[METRIC_R_SCALE_KIND] as u32)?;
    let constant = metrics[METRIC_R_CONSTANT];
    let mask = metrics[METRIC_R_MASK_NONPOSITIVE] >= 0.5;
    AxisScale::new(
        kind,
        metrics[METRIC_R_LO],
        metrics[METRIC_R_HI],
        0.0,
        1.0,
        constant,
        mask,
    )
    .ok()
}

/// Compute disc layout and pack projection metrics.
pub fn polar_layout(input: PolarLayoutInput, out: &mut [f64]) -> Option<usize> {
    if out.len() < POLAR_METRICS_LEN {
        return None;
    }
    let unit_scale = unit_scale(input.theta_unit)?;
    let turn = turn(input.theta_unit)?;
    let dir = direction_sign(input.theta_direction)?;
    let kind = scale_kind(input.r_scale_kind)?;
    if !input.theta_zero.is_finite()
        || !input.plot_w.is_finite()
        || !input.plot_h.is_finite()
        || !input.plot_x.is_finite()
        || !input.plot_y.is_finite()
        || input.plot_w <= 0.0
        || input.plot_h <= 0.0
        || !input.sector_start.is_finite()
        || !input.sector_end.is_finite()
        || !input.r_lo.is_finite()
        || !input.r_hi.is_finite()
        || !input.hole.is_finite()
        || input.hole < 0.0
        || input.hole > 1.0
    {
        return None;
    }
    let constant = if input.r_constant.is_finite() && input.r_constant > 0.0 {
        input.r_constant
    } else {
        1.0
    };
    let r_scale = AxisScale::new(
        kind,
        input.r_lo,
        input.r_hi,
        0.0,
        1.0,
        constant,
        input.r_mask_nonpositive,
    )
    .ok()?;
    let r_origin = if input.r_origin.is_nan() {
        input.r_lo
    } else if input.r_origin.is_finite() {
        input.r_origin
    } else {
        return None;
    };
    let r_lo_coord = r_scale.coord(input.r_lo);
    let r_hi_coord = r_scale.coord(input.r_hi);
    let r_origin_coord = r_scale.coord(r_origin);

    let sector_start = input.sector_start;
    let sector_end = input.sector_end;
    let sector_span = sector_end - sector_start;
    let full_sector = sector_span >= turn * (1.0 - 1e-9);
    let zero = input.theta_zero;
    let sector_a0 = zero + dir * unit_scale * sector_start;
    let sector_a1 = zero + dir * unit_scale * sector_end;

    let (cx, cy, radius) = if full_sector {
        let radius = input.plot_w.min(input.plot_h) / 2.0;
        let cx = input.plot_x + input.plot_w / 2.0;
        let cy = input.plot_y + input.plot_h / 2.0;
        (cx, cy, radius)
    } else {
        partial_sector_layout(
            input.plot_x,
            input.plot_y,
            input.plot_w,
            input.plot_h,
            sector_a0,
            sector_a1,
            &r_scale,
            input.r_lo,
            r_origin_coord,
            r_hi_coord,
            input.hole,
        )?
    };

    out[METRIC_CX] = cx;
    out[METRIC_CY] = cy;
    out[METRIC_RADIUS] = radius;
    out[METRIC_ZERO] = zero;
    out[METRIC_DIR] = dir;
    out[METRIC_UNIT_SCALE] = unit_scale;
    out[METRIC_SECTOR_START] = sector_start;
    out[METRIC_SECTOR_END] = sector_end;
    out[METRIC_SECTOR_SPAN] = sector_span;
    out[METRIC_TURN] = turn;
    out[METRIC_FULL_SECTOR] = if full_sector { 1.0 } else { 0.0 };
    out[METRIC_R_LO_COORD] = r_lo_coord;
    out[METRIC_R_HI_COORD] = r_hi_coord;
    out[METRIC_R_ORIGIN_COORD] = r_origin_coord;
    out[METRIC_HOLE] = input.hole;
    out[METRIC_N_CATEGORIES] = f64::from(input.n_categories);
    out[METRIC_SECTOR_A0] = sector_a0;
    out[METRIC_SECTOR_A1] = sector_a1;
    out[METRIC_R_LO] = input.r_lo;
    out[METRIC_R_HI] = input.r_hi;
    out[METRIC_R_SCALE_KIND] = f64::from(input.r_scale_kind);
    out[METRIC_R_CONSTANT] = constant;
    out[METRIC_R_MASK_NONPOSITIVE] = if input.r_mask_nonpositive { 1.0 } else { 0.0 };
    Some(POLAR_METRICS_LEN)
}

fn partial_sector_layout(
    plot_x: f64,
    plot_y: f64,
    plot_w: f64,
    plot_h: f64,
    sector_a0: f64,
    sector_a1: f64,
    r_scale: &AxisScale,
    r_lo: f64,
    r_origin_coord: f64,
    r_hi_coord: f64,
    hole: f64,
) -> Option<(f64, f64, f64)> {
    let lo_angle = sector_a0.min(sector_a1);
    let hi_angle = sector_a0.max(sector_a1);
    let mut angles = vec![sector_a0, sector_a1];
    for cardinal in [
        0.0,
        std::f64::consts::FRAC_PI_2,
        std::f64::consts::PI,
        1.5 * std::f64::consts::PI,
    ] {
        let first = ((lo_angle - cardinal) / (2.0 * std::f64::consts::PI)).ceil() as i64;
        let last = ((hi_angle - cardinal) / (2.0 * std::f64::consts::PI)).floor() as i64;
        for turn_index in first..=last {
            angles.push(cardinal + (turn_index as f64) * 2.0 * std::f64::consts::PI);
        }
    }
    let inner = norm_radius_scalar(r_scale, r_lo, r_origin_coord, r_hi_coord, hole).clamp(0.0, 1.0);
    let mut xs = Vec::with_capacity(angles.len() * 2 + 1);
    let mut ys = Vec::with_capacity(angles.len() * 2 + 1);
    for &angle in &angles {
        xs.push(angle.cos());
        ys.push(-angle.sin());
        xs.push(inner * angle.cos());
        ys.push(-inner * angle.sin());
    }
    if inner <= 1e-12 {
        xs.push(0.0);
        ys.push(0.0);
    }
    let xmin = xs.iter().copied().fold(f64::INFINITY, f64::min);
    let xmax = xs.iter().copied().fold(f64::NEG_INFINITY, f64::max);
    let ymin = ys.iter().copied().fold(f64::INFINITY, f64::min);
    let ymax = ys.iter().copied().fold(f64::NEG_INFINITY, f64::max);
    let xspan = (xmax - xmin).max(1e-12);
    let yspan = (ymax - ymin).max(1e-12);
    let radius = (plot_w / xspan).min(plot_h / yspan);
    let left = plot_x + (plot_w - radius * xspan) / 2.0;
    let top = plot_y + (plot_h - radius * yspan) / 2.0;
    let cx = left - radius * xmin;
    let cy = top - radius * ymin;
    Some((cx, cy, radius))
}

fn theta_value(metrics: &[f64], theta: f64) -> f64 {
    let n_categories = metrics[METRIC_N_CATEGORIES] as u32;
    if n_categories == 0 {
        return theta;
    }
    let sector_start = metrics[METRIC_SECTOR_START];
    let sector_span = metrics[METRIC_SECTOR_SPAN];
    let full_sector = metrics[METRIC_FULL_SECTOR] >= 0.5;
    let divisor = if full_sector {
        f64::from(n_categories)
    } else {
        f64::from(n_categories.saturating_sub(1).max(1))
    };
    sector_start + theta * sector_span / divisor
}

fn angle(metrics: &[f64], theta: f64) -> f64 {
    let th = theta_value(metrics, theta) * metrics[METRIC_UNIT_SCALE];
    metrics[METRIC_ZERO] + metrics[METRIC_DIR] * th
}

fn norm_radius_scalar(
    r_scale: &AxisScale,
    r: f64,
    r_origin_coord: f64,
    r_hi_coord: f64,
    hole: f64,
) -> f64 {
    let coord = r_scale.coord(r);
    let span = r_hi_coord - r_origin_coord;
    if span.abs() <= 1e-30 {
        return f64::NAN;
    }
    let base = (coord - r_origin_coord) / span;
    hole + (1.0 - hole) * base
}

fn norm_radius_from_metrics(metrics: &[f64], r: f64) -> f64 {
    let r_scale = match build_r_scale(metrics) {
        Some(scale) => scale,
        None => return f64::NAN,
    };
    norm_radius_scalar(
        &r_scale,
        r,
        metrics[METRIC_R_ORIGIN_COORD],
        metrics[METRIC_R_HI_COORD],
        metrics[METRIC_HOLE],
    )
}

/// Project `(theta, r)` data pairs to screen pixels.
pub fn polar_project(
    metrics: &[f64],
    theta: &[f64],
    r: &[f64],
    out_x: &mut [f64],
    out_y: &mut [f64],
) -> Option<usize> {
    let n = theta.len();
    if metrics.len() < POLAR_METRICS_LEN || r.len() != n || out_x.len() < n || out_y.len() < n {
        return None;
    }
    let cx = metrics[METRIC_CX];
    let cy = metrics[METRIC_CY];
    let radius = metrics[METRIC_RADIUS];
    for index in 0..n {
        let a = angle(metrics, theta[index]);
        let rn = norm_radius_from_metrics(metrics, r[index]) * radius;
        out_x[index] = cx + rn * a.cos();
        out_y[index] = cy - rn * a.sin();
    }
    Some(n)
}

fn angular_value_visible(metrics: &[f64], raw: f64) -> bool {
    if !raw.is_finite() {
        return false;
    }
    if metrics[METRIC_FULL_SECTOR] >= 0.5 {
        return true;
    }
    let turn = metrics[METRIC_TURN];
    let offset = (raw - metrics[METRIC_SECTOR_START]).rem_euclid(turn);
    offset <= metrics[METRIC_SECTOR_SPAN] + turn * 1e-9
}

/// Which angular values fall in the authored sector.
pub fn polar_theta_visible_mask(metrics: &[f64], theta: &[f64], out: &mut [u8]) -> Option<usize> {
    let n = theta.len();
    if metrics.len() < POLAR_METRICS_LEN || out.len() < n {
        return None;
    }
    for (mask, &th) in out.iter_mut().zip(theta) {
        let raw = theta_value(metrics, th);
        *mask = u8::from(angular_value_visible(metrics, raw));
    }
    Some(n)
}

/// Which radii have an honest polar position (`rn` cull epsilon `1e-6`).
pub fn polar_visible_mask(metrics: &[f64], r: &[f64], out: &mut [u8]) -> Option<usize> {
    let n = r.len();
    if metrics.len() < POLAR_METRICS_LEN || out.len() < n {
        return None;
    }
    let r_scale = build_r_scale(metrics)?;
    let lo = metrics[METRIC_R_LO_COORD].min(metrics[METRIC_R_HI_COORD]);
    let hi = metrics[METRIC_R_LO_COORD].max(metrics[METRIC_R_HI_COORD]);
    for (mask, &rv) in out.iter_mut().zip(r) {
        let coord = r_scale.coord(rv);
        *mask = u8::from(coord.is_finite() && coord >= lo - 1e-6 && coord <= hi + 1e-6);
    }
    Some(n)
}

/// Combined angular and radial visibility mask.
pub fn polar_position_mask(
    metrics: &[f64],
    theta: &[f64],
    r: &[f64],
    out: &mut [u8],
) -> Option<usize> {
    let n = theta.len();
    if metrics.len() < POLAR_METRICS_LEN || r.len() != n || out.len() < n {
        return None;
    }
    let mut theta_mask = vec![0u8; n];
    let mut radius_mask = vec![0u8; n];
    polar_theta_visible_mask(metrics, theta, &mut theta_mask)?;
    polar_visible_mask(metrics, r, &mut radius_mask)?;
    for index in 0..n {
        out[index] = theta_mask[index] & radius_mask[index];
    }
    Some(n)
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::f64::consts::{FRAC_PI_2, PI};

    fn default_input() -> PolarLayoutInput {
        PolarLayoutInput {
            plot_x: 0.0,
            plot_y: 0.0,
            plot_w: 400.0,
            plot_h: 400.0,
            theta_unit: 0,
            theta_zero: THETA_ZERO_E,
            theta_direction: 0,
            sector_start: 0.0,
            sector_end: 2.0 * PI,
            n_categories: 0,
            r_lo: 0.0,
            r_hi: 1.0,
            r_origin: f64::NAN,
            hole: 0.0,
            r_scale_kind: 0,
            r_constant: 1.0,
            r_mask_nonpositive: false,
        }
    }

    fn project_point(metrics: &[f64], theta: f64, r: f64) -> (f64, f64) {
        let mut x = [0.0];
        let mut y = [0.0];
        polar_project(metrics, &[theta], &[r], &mut x, &mut y).unwrap();
        (x[0], y[0])
    }

    #[test]
    fn default_cardinals_match_fixture() {
        let mut metrics = [0.0; POLAR_METRICS_LEN];
        polar_layout(default_input(), &mut metrics).unwrap();
        let (px, py) = project_point(&metrics, 0.0, 1.0);
        assert!((px - 400.0).abs() < 1e-9, "east px");
        assert!((py - 200.0).abs() < 1e-9, "east py");
        let (px, py) = project_point(&metrics, FRAC_PI_2, 1.0);
        assert!((px - 200.0).abs() < 1e-9, "north px");
        assert!((py - 0.0).abs() < 1e-9, "north py");
        let (px, py) = project_point(&metrics, PI, 1.0);
        assert!((px - 0.0).abs() < 1e-9, "west px");
        assert!((py - 200.0).abs() < 1e-9, "west py");
        let (px, py) = project_point(&metrics, -FRAC_PI_2, 1.0);
        assert!((px - 200.0).abs() < 1e-9, "south px");
        assert!((py - 400.0).abs() < 1e-9, "south py");
        let (px, py) = project_point(&metrics, 0.0, 0.0);
        assert!((px - 200.0).abs() < 1e-9, "centre px");
        assert!((py - 200.0).abs() < 1e-9, "centre py");
    }

    #[test]
    fn zero_north_rotates_cardinals() {
        let mut input = default_input();
        input.theta_zero = THETA_ZERO_N;
        let mut metrics = [0.0; POLAR_METRICS_LEN];
        polar_layout(input, &mut metrics).unwrap();
        let (px, py) = project_point(&metrics, 0.0, 1.0);
        assert!((px - 200.0).abs() < 1e-9);
        assert!((py - 0.0).abs() < 1e-9);
        let (px, py) = project_point(&metrics, FRAC_PI_2, 1.0);
        assert!((px - 0.0).abs() < 1e-9);
        assert!((py - 200.0).abs() < 1e-9);
    }

    #[test]
    fn screen_y_grows_down() {
        let mut metrics = [0.0; POLAR_METRICS_LEN];
        polar_layout(default_input(), &mut metrics).unwrap();
        let (_, up) = project_point(&metrics, FRAC_PI_2, 1.0);
        let (_, down) = project_point(&metrics, -FRAC_PI_2, 1.0);
        let (_, centre) = project_point(&metrics, 0.0, 0.0);
        assert!(up < centre && centre < down);
    }
}
