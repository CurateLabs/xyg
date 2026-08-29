//! Polar (theta, r) → screen-pixel projection — spec/design/polar-axes.md §3.
//!
//! Screen space grows downward (`cy - rn * sin(a)`). Full-turn radius uses
//! `min(w, h) / 2` centred in the plot rect; partial sectors fill the bbox.
//! Scene v26 packs host authoring as XYPL v1; Rust calls [`polar_layout`] with
//! the finalized plot rect and never trusts host-computed cx/cy/R.

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

/// XYPL v1 host→Rust authoring envelope (ABI 133 / Scene v26).
pub const XYPL_MAGIC: &[u8; 4] = b"XYPL";
pub const XYPL_VERSION: u32 = 1;
pub const XYPL_V1_BYTES: usize = 92;

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

/// Host-packed polar authoring. Plot rect is filled in by Rust at encode time.
#[derive(Clone, Copy, Debug, PartialEq)]
pub struct PolarEnvelope {
    pub theta_unit: u32,
    pub theta_direction: u32,
    pub n_categories: u32,
    pub r_scale_kind: u32,
    pub grid_shape: u8,
    pub r_mask_nonpositive: bool,
    pub theta_zero: f64,
    pub sector_start: f64,
    pub sector_end: f64,
    pub r_lo: f64,
    pub r_hi: f64,
    pub r_origin: f64,
    pub hole: f64,
    pub r_constant: f64,
}

impl PolarEnvelope {
    pub fn layout_input(
        self,
        plot_x: f64,
        plot_y: f64,
        plot_w: f64,
        plot_h: f64,
    ) -> PolarLayoutInput {
        PolarLayoutInput {
            plot_x,
            plot_y,
            plot_w,
            plot_h,
            theta_unit: self.theta_unit,
            theta_zero: self.theta_zero,
            theta_direction: self.theta_direction,
            sector_start: self.sector_start,
            sector_end: self.sector_end,
            n_categories: self.n_categories,
            r_lo: self.r_lo,
            r_hi: self.r_hi,
            r_origin: self.r_origin,
            hole: self.hole,
            r_scale_kind: self.r_scale_kind,
            r_constant: self.r_constant,
            r_mask_nonpositive: self.r_mask_nonpositive,
        }
    }
}

fn read_u32(bytes: &[u8], offset: usize) -> Option<u32> {
    Some(u32::from_le_bytes(
        bytes.get(offset..offset + 4)?.try_into().ok()?,
    ))
}

fn read_f64(bytes: &[u8], offset: usize) -> Option<f64> {
    Some(f64::from_le_bytes(
        bytes.get(offset..offset + 8)?.try_into().ok()?,
    ))
}

/// Parse a bounded XYPL v1 envelope. Malformed magic/version/enums/nonfinite
/// required fields fail closed.
pub fn parse_xypl(bytes: &[u8]) -> Option<PolarEnvelope> {
    if bytes.len() != XYPL_V1_BYTES || bytes.get(..4) != Some(&XYPL_MAGIC[..]) {
        return None;
    }
    if read_u32(bytes, 4)? != XYPL_VERSION {
        return None;
    }
    let theta_unit = read_u32(bytes, 8)?;
    let theta_direction = read_u32(bytes, 12)?;
    let n_categories = read_u32(bytes, 16)?;
    let r_scale_kind = read_u32(bytes, 20)?;
    let grid_shape = *bytes.get(24)?;
    let r_mask = *bytes.get(25)?;
    let pad = u16::from_le_bytes(bytes.get(26..28)?.try_into().ok()?);
    if pad != 0
        || !matches!(theta_unit, 0 | 1)
        || !matches!(theta_direction, 0 | 1)
        || !matches!(r_scale_kind, 0 | 1 | 2)
        || !matches!(grid_shape, 0 | 1)
        || !matches!(r_mask, 0 | 1)
    {
        return None;
    }
    let theta_zero = read_f64(bytes, 28)?;
    let sector_start = read_f64(bytes, 36)?;
    let sector_end = read_f64(bytes, 44)?;
    let r_lo = read_f64(bytes, 52)?;
    let r_hi = read_f64(bytes, 60)?;
    let r_origin = read_f64(bytes, 68)?;
    let hole = read_f64(bytes, 76)?;
    let r_constant = read_f64(bytes, 84)?;
    if !theta_zero.is_finite()
        || !sector_start.is_finite()
        || !sector_end.is_finite()
        || !r_lo.is_finite()
        || !r_hi.is_finite()
        || !hole.is_finite()
        || hole < 0.0
        || hole > 1.0
        || !(r_origin.is_finite() || r_origin.is_nan())
        || !(r_constant.is_finite() || r_constant.is_nan())
    {
        return None;
    }
    Some(PolarEnvelope {
        theta_unit,
        theta_direction,
        n_categories,
        r_scale_kind,
        grid_shape,
        r_mask_nonpositive: r_mask != 0,
        theta_zero,
        sector_start,
        sector_end,
        r_lo,
        r_hi,
        r_origin,
        hole,
        r_constant,
    })
}

/// Pack a validated XYPL v1 envelope (host tests / encode sidecar).
pub fn encode_xypl(envelope: &PolarEnvelope) -> [u8; XYPL_V1_BYTES] {
    let mut out = [0u8; XYPL_V1_BYTES];
    out[..4].copy_from_slice(XYPL_MAGIC);
    out[4..8].copy_from_slice(&XYPL_VERSION.to_le_bytes());
    out[8..12].copy_from_slice(&envelope.theta_unit.to_le_bytes());
    out[12..16].copy_from_slice(&envelope.theta_direction.to_le_bytes());
    out[16..20].copy_from_slice(&envelope.n_categories.to_le_bytes());
    out[20..24].copy_from_slice(&envelope.r_scale_kind.to_le_bytes());
    out[24] = envelope.grid_shape;
    out[25] = u8::from(envelope.r_mask_nonpositive);
    out[26..28].copy_from_slice(&0u16.to_le_bytes());
    for (offset, value) in [
        envelope.theta_zero,
        envelope.sector_start,
        envelope.sector_end,
        envelope.r_lo,
        envelope.r_hi,
        envelope.r_origin,
        envelope.hole,
        envelope.r_constant,
    ]
    .into_iter()
    .enumerate()
    {
        let at = 28 + offset * 8;
        out[at..at + 8].copy_from_slice(&value.to_le_bytes());
    }
    out
}

/// Layout polar metrics from an XYPL envelope and the finalized plot rect.
pub fn layout_from_xypl(
    bytes: &[u8],
    plot_x: f64,
    plot_y: f64,
    plot_w: f64,
    plot_h: f64,
    metrics: &mut [f64],
) -> Option<PolarEnvelope> {
    let envelope = parse_xypl(bytes)?;
    polar_layout(
        envelope.layout_input(plot_x, plot_y, plot_w, plot_h),
        metrics,
    )?;
    Some(envelope)
}

/// Project one (theta, r) pair to screen pixels.
pub fn polar_project_one(metrics: &[f64], theta: f64, r: f64) -> Option<(f64, f64)> {
    let mut x = [0.0];
    let mut y = [0.0];
    polar_project(metrics, &[theta], &[r], &mut x, &mut y)?;
    Some((x[0], y[0]))
}

/// Combined angular and radial visibility for one data point.
pub fn polar_point_visible(metrics: &[f64], theta: f64, r: f64) -> bool {
    let mut out = [0u8];
    polar_position_mask(metrics, &[theta], &[r], &mut out) == Some(1) && out[0] != 0
}

/// Subdivisions across one full turn when flattening polar bar arcs.
pub const POLAR_BAR_SEGMENTS: usize = 96;
/// Floor on a single wedge so a hairline slice still brackets the true arc.
pub const POLAR_BAR_SEGMENTS_MIN: usize = 2;

/// Span-proportional flattening count matching `config.polar_bar_segments`.
///
/// `ceil(96 · |span| / turn)` clamped to `[2, 96]`. Degenerate `turn` or
/// non-finite `span` pays the full-turn count so a wide wedge is never
/// under-subdivided.
pub fn polar_bar_segments(span: f64, turn: f64) -> usize {
    if !(turn > 0.0) || !span.is_finite() {
        return POLAR_BAR_SEGMENTS;
    }
    let scaled = (POLAR_BAR_SEGMENTS as f64 * span.abs() / turn).ceil();
    if !scaled.is_finite() {
        return POLAR_BAR_SEGMENTS;
    }
    (scaled as usize).clamp(POLAR_BAR_SEGMENTS_MIN, POLAR_BAR_SEGMENTS)
}

fn inner_fraction(metrics: &[f64]) -> f64 {
    norm_radius_from_metrics(metrics, metrics[METRIC_R_LO]).clamp(0.0, 1.0)
}

/// Visible screen-angle interval for an authored angular band.
///
/// Full-sector charts convert both endpoints directly. Partial sectors clip
/// the data interval onto the authored sector (searching one turn either
/// side of the nearest wrap) before converting to screen angles.
pub fn wedge_angles(metrics: &[f64], theta0: f64, theta1: f64) -> Option<(f64, f64)> {
    if metrics.len() < POLAR_METRICS_LEN {
        return None;
    }
    let raw0 = theta_value(metrics, theta0);
    let raw1 = theta_value(metrics, theta1);
    if !raw0.is_finite() || !raw1.is_finite() {
        return None;
    }
    let zero = metrics[METRIC_ZERO];
    let dir = metrics[METRIC_DIR];
    let unit_scale = metrics[METRIC_UNIT_SCALE];
    if metrics[METRIC_FULL_SECTOR] >= 0.5 {
        return Some((
            zero + dir * unit_scale * raw0,
            zero + dir * unit_scale * raw1,
        ));
    }
    let low = raw0.min(raw1);
    let high = raw0.max(raw1);
    let midpoint = (low + high) / 2.0;
    let sector_midpoint = (metrics[METRIC_SECTOR_START] + metrics[METRIC_SECTOR_END]) / 2.0;
    let turn = metrics[METRIC_TURN];
    if !(turn > 0.0) || !turn.is_finite() {
        return None;
    }
    let nearest_turn = ((sector_midpoint - midpoint) / turn).round();
    let mut best: Option<(f64, f64)> = None;
    let mut best_span = -1.0;
    for delta in [-1.0, 0.0, 1.0] {
        let turn_index = nearest_turn + delta;
        let shifted_low = low + turn_index * turn;
        let shifted_high = high + turn_index * turn;
        let clipped_low = metrics[METRIC_SECTOR_START].max(shifted_low);
        let clipped_high = metrics[METRIC_SECTOR_END].min(shifted_high);
        let span = clipped_high - clipped_low;
        if span > best_span && span > 1e-12 {
            best = Some((clipped_low, clipped_high));
            best_span = span;
        }
    }
    let (clipped0, clipped1) = if raw0 <= raw1 {
        best?
    } else {
        let (lo, hi) = best?;
        (hi, lo)
    };
    Some((
        zero + dir * unit_scale * clipped0,
        zero + dir * unit_scale * clipped1,
    ))
}

/// Annular sector with rounded corners, sampled in the unrolled (arc, radial)
/// frame then rolled back to screen pixels. Matches `_svg._rounded_wedge_points`.
fn rounded_wedge_points(
    cx: f64,
    cy: f64,
    inner: f64,
    outer: f64,
    a0: f64,
    a1: f64,
    corner_radius: f64,
    steps: usize,
    wedge_gap: f64,
) -> Vec<(f64, f64)> {
    let r_mid = (inner + outer) / 2.0;
    let hr = (outer - inner) / 2.0;
    let sweep = (a1 - a0).abs();
    let mid = (a0 + a1) / 2.0;
    let sign = if a1 >= a0 { 1.0 } else { -1.0 };
    let gap_half = wedge_gap.max(0.0) / 2.0;
    let half_angle = |lr: f64| -> f64 {
        let dist = r_mid + lr;
        if dist <= 1e-9 {
            return 0.0;
        }
        let ha_px = (sweep * 0.5 * dist - gap_half).max(0.0);
        let rad = corner_radius.min(hr).min(ha_px);
        let over = lr.abs() - (hr - rad);
        let half_px = if over <= 0.0 {
            ha_px
        } else {
            (ha_px - rad) + (rad * rad - over * over).max(0.0).sqrt()
        };
        half_px / dist
    };
    let at = |dist: f64, angle: f64| -> (f64, f64) {
        (cx + dist * angle.cos(), cy - dist * angle.sin())
    };
    let mut out = Vec::with_capacity(4 * steps);
    let outer_ha = half_angle(hr);
    for i in 0..=steps {
        let t = i as f64 / steps as f64;
        out.push(at(outer, mid - sign * outer_ha + sign * outer_ha * 2.0 * t));
    }
    for i in 1..=steps {
        let lr = hr - 2.0 * hr * (i as f64 / steps as f64);
        out.push(at(r_mid + lr, mid + sign * half_angle(lr)));
    }
    let inner_ha = half_angle(-hr);
    for i in 1..=steps {
        let t = i as f64 / steps as f64;
        out.push(at(inner, mid + sign * inner_ha - sign * inner_ha * 2.0 * t));
    }
    for i in 1..steps {
        let lr = -hr + 2.0 * hr * (i as f64 / steps as f64);
        out.push(at(r_mid + lr, mid - sign * half_angle(lr)));
    }
    out
}

/// Flatten an annular sector `(theta0, theta1, r0, r1)` to screen pixels.
///
/// Radii clamp into the visible `[inner_fraction, 1]` interval. The polygon
/// is the outer arc then the reversed inner arc; an inner radius of zero
/// includes the disc centre. `wedge_gap` is a constant pixel gap (ABI 167):
/// each radial edge insets by `gap / (2 r)` radians so neighbouring slices
/// stay a fixed screen distance apart from hole to rim. `corner_radius` is a
/// pixel rounding radius (ABI 168): when the inner radius is positive, the
/// wedge unrolls into an (arc, radial) rectangle, rounds there, and rolls
/// back so corners follow the arc. Pie slices from the origin stay sharp.
pub fn polar_wedge_points(
    metrics: &[f64],
    theta0: f64,
    theta1: f64,
    r0: f64,
    r1: f64,
    wedge_gap: f64,
    corner_radius: f64,
) -> Vec<(f64, f64)> {
    if metrics.len() < POLAR_METRICS_LEN {
        return Vec::new();
    }
    let floor = inner_fraction(metrics);
    let lo_frac = norm_radius_from_metrics(metrics, r0);
    let hi_frac = norm_radius_from_metrics(metrics, r1);
    if !floor.is_finite() || !lo_frac.is_finite() || !hi_frac.is_finite() {
        return Vec::new();
    }
    let (lo_frac, hi_frac) = if lo_frac <= hi_frac {
        (lo_frac, hi_frac)
    } else {
        (hi_frac, lo_frac)
    };
    let radius = metrics[METRIC_RADIUS];
    let outer = floor.max(hi_frac).min(1.0) * radius;
    let inner = floor.max(lo_frac).min(1.0) * radius;
    if !outer.is_finite() || !inner.is_finite() || outer <= 0.0 || outer <= inner {
        return Vec::new();
    }
    let Some((a0, a1)) = wedge_angles(metrics, theta0, theta1) else {
        return Vec::new();
    };
    if !a0.is_finite() || !a1.is_finite() {
        return Vec::new();
    }
    let steps = polar_bar_segments(a1 - a0, 2.0 * std::f64::consts::PI);
    let cx = metrics[METRIC_CX];
    let cy = metrics[METRIC_CY];
    if corner_radius > 0.0 && inner > 0.0 {
        return rounded_wedge_points(
            cx,
            cy,
            inner,
            outer,
            a0,
            a1,
            corner_radius,
            steps,
            wedge_gap,
        );
    }
    let half = wedge_gap.max(0.0) / 2.0;
    let sign = if a1 >= a0 { 1.0 } else { -1.0 };
    let span = (a1 - a0).abs();
    let inset = |at_radius: f64| -> f64 {
        if half <= 0.0 || at_radius <= 1e-9 {
            0.0
        } else {
            sign * (half / at_radius).min(span / 2.0)
        }
    };
    let arc = |at_radius: f64, reverse: bool, out: &mut Vec<(f64, f64)>| {
        let delta = inset(at_radius);
        let (start, end) = if reverse {
            (a1 - delta, a0 + delta)
        } else {
            (a0 + delta, a1 - delta)
        };
        for i in 0..=steps {
            let t = i as f64 / steps as f64;
            let angle = start + (end - start) * t;
            out.push((cx + at_radius * angle.cos(), cy - at_radius * angle.sin()));
        }
    };
    let mut out = Vec::with_capacity(if inner <= 0.0 {
        steps + 2
    } else {
        2 * (steps + 1)
    });
    if inner <= 0.0 {
        out.push((cx, cy));
        arc(outer, false, &mut out);
    } else {
        arc(outer, false, &mut out);
        arc(inner, true, &mut out);
    }
    out
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

/// Cap matching the compatibility polar inverse-raster exporters.
pub const POLAR_HEATMAP_MAX_DIMENSION: u32 = 4096;

fn theta_from_angle(metrics: &[f64], angle: f64, near: f64) -> f64 {
    let dir = metrics[METRIC_DIR];
    let unit = metrics[METRIC_UNIT_SCALE];
    let turn = metrics[METRIC_TURN];
    let raw = (angle - metrics[METRIC_ZERO]) / (dir * unit);
    let wrapped = near + (raw - near).rem_euclid(turn);
    let n_categories = metrics[METRIC_N_CATEGORIES] as u32;
    if n_categories == 0 {
        return wrapped;
    }
    let sector_start = metrics[METRIC_SECTOR_START];
    let sector_span = metrics[METRIC_SECTOR_SPAN];
    let divisor = if metrics[METRIC_FULL_SECTOR] >= 0.5 {
        f64::from(n_categories)
    } else {
        f64::from(n_categories.saturating_sub(1).max(1))
    };
    (wrapped - sector_start) * divisor / if sector_span == 0.0 { 1.0 } else { sector_span }
}

fn radius_value(metrics: &[f64], normalized: f64) -> Option<f64> {
    let r_scale = build_r_scale(metrics)?;
    let hole = metrics[METRIC_HOLE];
    let base = (normalized - hole) / (1.0 - hole).max(1e-30);
    let coord = metrics[METRIC_R_ORIGIN_COORD]
        + base * (metrics[METRIC_R_HI_COORD] - metrics[METRIC_R_ORIGIN_COORD]);
    Some(r_scale.value(coord))
}

/// One visible output pixel mapped onto a source heatmap cell.
///
/// `source_index` is row-major with source row 0 at the radial-range bottom
/// (`source_y * grid_w + source_x`), matching compatibility `_heatmap_rgba_samples`.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct PolarHeatmapHit {
    pub row: u32,
    pub col: u32,
    pub source_index: u32,
}

/// Output image size for polar inverse-raster, capped at [`POLAR_HEATMAP_MAX_DIMENSION`].
pub fn polar_heatmap_output_size(
    plot_w: f64,
    plot_h: f64,
    output_scale: f64,
) -> Option<(u32, u32)> {
    if !plot_w.is_finite()
        || !plot_h.is_finite()
        || plot_w <= 0.0
        || plot_h <= 0.0
        || !output_scale.is_finite()
        || output_scale <= 0.0
    {
        return None;
    }
    let out_w = (plot_w * output_scale)
        .ceil()
        .clamp(1.0, f64::from(POLAR_HEATMAP_MAX_DIMENSION)) as u32;
    let out_h = (plot_h * output_scale)
        .ceil()
        .clamp(1.0, f64::from(POLAR_HEATMAP_MAX_DIMENSION)) as u32;
    Some((out_w, out_h))
}

/// Screen-bounded inverse map of a polar heatmap grid (polar-axes.md §3.2).
///
/// Work is bounded by output pixels: each visible plot sample yields one
/// source-cell index. Hosts color those indices; Scene paints a prebuilt
/// image-top-first RGBA grid through [`polar_heatmap_inverse_raster`].
pub fn polar_heatmap_inverse_hits(
    metrics: &[f64],
    plot_x: f64,
    plot_y: f64,
    plot_w: f64,
    plot_h: f64,
    grid_w: u32,
    grid_h: u32,
    x0: f64,
    y0: f64,
    x1: f64,
    y1: f64,
    output_scale: f64,
) -> Option<(u32, u32, Vec<PolarHeatmapHit>)> {
    if metrics.len() < POLAR_METRICS_LEN {
        return None;
    }
    if grid_w == 0 || grid_h == 0 {
        return None;
    }
    if !x0.is_finite() || !x1.is_finite() || !y0.is_finite() || !y1.is_finite() {
        return None;
    }
    let (out_w, out_h) = polar_heatmap_output_size(plot_w, plot_h, output_scale)?;
    let cx = metrics[METRIC_CX];
    let cy = metrics[METRIC_CY];
    let radius = metrics[METRIC_RADIUS].max(1e-30);
    let inner = inner_fraction(metrics);
    let x_span = if x1 > x0 { x1 - x0 } else { 1.0 };
    let y_span = if y1 > y0 { y1 - y0 } else { 1.0 };
    let near = theta_value(metrics, x0);
    let mut hits = Vec::new();
    let dx_step = plot_w / f64::from(out_w);
    let dy_step = plot_h / f64::from(out_h);
    let source_w = grid_w as usize;
    for row in 0..out_h {
        let y = plot_y + (f64::from(row) + 0.5) * dy_step;
        let dy = cy - y;
        for col in 0..out_w {
            let x = plot_x + (f64::from(col) + 0.5) * dx_step;
            let dx = x - cx;
            let normalized = dy.hypot(dx) / radius;
            if !(normalized >= inner - 1e-9 && normalized <= 1.0 + 1e-9) {
                continue;
            }
            let angle = dy.atan2(dx);
            let theta = theta_from_angle(metrics, angle, near);
            let Some(radial) = radius_value(metrics, normalized) else {
                continue;
            };
            let fx = (theta - x0) / x_span;
            let fy = (radial - y0) / y_span;
            let raw_theta = theta_value(metrics, theta);
            if !fx.is_finite()
                || !fy.is_finite()
                || !angular_value_visible(metrics, raw_theta)
                || !(0.0..=1.0).contains(&fx)
                || !(0.0..=1.0).contains(&fy)
            {
                continue;
            }
            let source_x =
                ((fx * f64::from(grid_w)).floor() as i64).clamp(0, i64::from(grid_w) - 1) as usize;
            let source_y =
                ((fy * f64::from(grid_h)).floor() as i64).clamp(0, i64::from(grid_h) - 1) as usize;
            let source_index = u32::try_from(source_y.checked_mul(source_w)?.checked_add(source_x)?)
                .ok()?;
            hits.push(PolarHeatmapHit {
                row,
                col,
                source_index,
            });
        }
    }
    Some((out_w, out_h, hits))
}

/// Screen-bounded inverse-raster of a polar heatmap grid (polar-axes.md §3.2).
///
/// `grid` is image-top-first RGBA8 (`width*height*4`). Source row 0 of the
/// canonical heatmap is the radial-range bottom, so this samples
/// `image_row = height - 1 - source_y`. Output covers the plot rect at
/// `output_scale` samples per logical pixel, capped at
/// [`POLAR_HEATMAP_MAX_DIMENSION`]. Work is bounded by output pixels.
pub fn polar_heatmap_inverse_raster(
    metrics: &[f64],
    plot_x: f64,
    plot_y: f64,
    plot_w: f64,
    plot_h: f64,
    grid: &[u8],
    grid_w: u32,
    grid_h: u32,
    x0: f64,
    y0: f64,
    x1: f64,
    y1: f64,
    output_scale: f64,
) -> Option<(u32, u32, Vec<u8>)> {
    let cells = (grid_w as usize).checked_mul(grid_h as usize)?;
    if grid.len() != cells.checked_mul(4)? {
        return None;
    }
    let (out_w, out_h, hits) = polar_heatmap_inverse_hits(
        metrics,
        plot_x,
        plot_y,
        plot_w,
        plot_h,
        grid_w,
        grid_h,
        x0,
        y0,
        x1,
        y1,
        output_scale,
    )?;
    let mut out = vec![
        0u8;
        (out_w as usize)
            .checked_mul(out_h as usize)?
            .checked_mul(4)?
    ];
    let source_w = grid_w as usize;
    let source_h = grid_h as usize;
    for hit in hits {
        let source_index = hit.source_index as usize;
        let source_y = source_index / source_w;
        let source_x = source_index % source_w;
        let image_row = source_h - 1 - source_y;
        let src = (image_row * source_w + source_x) * 4;
        let dst = (hit.row as usize * out_w as usize + hit.col as usize) * 4;
        out[dst..dst + 4].copy_from_slice(&grid[src..src + 4]);
    }
    Some((out_w, out_h, out))
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

    #[test]
    fn xypl_v1_roundtrip_and_rejects_malformed() {
        let envelope = PolarEnvelope {
            theta_unit: 0,
            theta_direction: 0,
            n_categories: 0,
            r_scale_kind: 0,
            grid_shape: 0,
            r_mask_nonpositive: false,
            theta_zero: 0.0,
            sector_start: 0.0,
            sector_end: 2.0 * PI,
            r_lo: 0.0,
            r_hi: 1.0,
            r_origin: f64::NAN,
            hole: 0.0,
            r_constant: 1.0,
        };
        let bytes = encode_xypl(&envelope);
        let parsed = parse_xypl(&bytes).unwrap();
        assert_eq!(parsed.theta_unit, 0);
        assert_eq!(parsed.grid_shape, 0);
        assert!(parsed.r_origin.is_nan());
        let mut bad = bytes;
        bad[0] = b'Z';
        assert!(parse_xypl(&bad).is_none());
        let mut version = bytes;
        version[4..8].copy_from_slice(&2u32.to_le_bytes());
        assert!(parse_xypl(&version).is_none());
        let mut unit = bytes;
        unit[8..12].copy_from_slice(&2u32.to_le_bytes());
        assert!(parse_xypl(&unit).is_none());
    }

    #[test]
    fn quarter_turn_outer_wedge_is_finite_and_uses_screen_y_down() {
        let mut metrics = [0.0; POLAR_METRICS_LEN];
        polar_layout(default_input(), &mut metrics).unwrap();
        let points = polar_wedge_points(&metrics, 0.0, FRAC_PI_2, 0.0, 1.0, 0.0, 0.0);
        assert!(points.len() >= 3);
        assert!(points.iter().all(|(x, y)| x.is_finite() && y.is_finite()));
        let cx = metrics[METRIC_CX];
        let cy = metrics[METRIC_CY];
        let radius = metrics[METRIC_RADIUS];
        assert!((points[0].0 - cx).abs() < 1e-9);
        assert!((points[0].1 - cy).abs() < 1e-9);
        let east = points[1];
        assert!((east.0 - (cx + radius)).abs() < 1e-6);
        assert!((east.1 - cy).abs() < 1e-6);
        let north = *points.last().unwrap();
        assert!((north.0 - cx).abs() < 1e-6);
        assert!((north.1 - (cy - radius)).abs() < 1e-6);
        assert!(north.1 < cy);
        assert_eq!(polar_bar_segments(FRAC_PI_2, 2.0 * PI), 24);
    }

    #[test]
    fn wedge_gap_insets_outer_arc_by_constant_pixels() {
        let mut metrics = [0.0; POLAR_METRICS_LEN];
        polar_layout(default_input(), &mut metrics).unwrap();
        let plain = polar_wedge_points(&metrics, 0.0, FRAC_PI_2, 0.25, 1.0, 0.0, 0.0);
        let gapped = polar_wedge_points(&metrics, 0.0, FRAC_PI_2, 0.25, 1.0, 12.0, 0.0);
        assert_eq!(plain.len(), gapped.len());
        assert!(gapped.len() >= 6);
        let radius = metrics[METRIC_RADIUS];
        let cx = metrics[METRIC_CX];
        let cy = metrics[METRIC_CY];
        let outer_start = gapped[0];
        let dx = outer_start.0 - cx;
        let dy = cy - outer_start.1;
        let angle = dy.atan2(dx);
        let expected = 12.0 / 2.0 / radius;
        assert!((angle - expected).abs() < 1e-6);
        assert!(plain[0].0 > gapped[0].0);
    }

    fn polygon_area(poly: &[(f64, f64)]) -> f64 {
        let mut total = 0.0;
        for index in 0..poly.len() {
            let (x0, y0) = poly[index];
            let (x1, y1) = poly[(index + 1) % poly.len()];
            total += x0 * y1 - x1 * y0;
        }
        total.abs() / 2.0
    }

    #[test]
    fn pie_from_origin_ignores_corner_radius() {
        let mut metrics = [0.0; POLAR_METRICS_LEN];
        polar_layout(default_input(), &mut metrics).unwrap();
        let plain = polar_wedge_points(&metrics, 0.0, FRAC_PI_2, 0.0, 1.0, 0.0, 0.0);
        let rounded = polar_wedge_points(&metrics, 0.0, FRAC_PI_2, 0.0, 1.0, 0.0, 14.0);
        assert_eq!(plain, rounded);
    }

    #[test]
    fn annular_corner_radius_insets_the_square_wedge() {
        let mut metrics = [0.0; POLAR_METRICS_LEN];
        polar_layout(default_input(), &mut metrics).unwrap();
        let square = polar_wedge_points(&metrics, 0.0, FRAC_PI_2, 0.25, 1.0, 0.0, 0.0);
        let rounded = polar_wedge_points(&metrics, 0.0, FRAC_PI_2, 0.25, 1.0, 0.0, 14.0);
        assert!(rounded.len() >= 3);
        let square_area = polygon_area(&square);
        let rounded_area = polygon_area(&rounded);
        assert!(rounded_area < square_area);
        assert!(square_area - rounded_area < 4.0 * 14.0 * 14.0);
        let cx = metrics[METRIC_CX];
        let cy = metrics[METRIC_CY];
        let radius = metrics[METRIC_RADIUS];
        for &(px, py) in &rounded {
            let dx = px - cx;
            let dy = cy - py;
            let dist = (dx * dx + dy * dy).sqrt();
            assert!(dist + 1e-6 >= 0.25 * radius);
            assert!(dist <= radius + 1e-6);
            let angle = dy.atan2(dx);
            assert!(angle >= -1e-6);
            assert!(angle <= FRAC_PI_2 + 1e-6);
        }
    }

    #[test]
    fn polar_heatmap_inverse_raster_fills_sector_and_masks_hole() {
        let mut input = default_input();
        input.hole = 0.4;
        input.sector_start = 0.0;
        input.sector_end = PI;
        let mut metrics = [0.0; POLAR_METRICS_LEN];
        polar_layout(input, &mut metrics).unwrap();
        // image-top-first 2×2: bottom-left red, bottom-right green, top-left blue, top-right white
        let grid = [
            0u8, 0, 255, 255, 255, 255, 255, 255, 255, 0, 0, 255, 0, 255, 0, 255,
        ];
        let (out_w, out_h, rgba) = polar_heatmap_inverse_raster(
            &metrics, 0.0, 0.0, 400.0, 400.0, &grid, 2, 2, 0.0, 0.0, PI, 1.0, 1.0,
        )
        .unwrap();
        assert_eq!(out_w, 400);
        assert_eq!(out_h, 400);
        let cx = metrics[METRIC_CX] as usize;
        let cy = metrics[METRIC_CY] as usize;
        let hole = (cy * out_w as usize + cx) * 4;
        assert_eq!(&rgba[hole..hole + 4], &[0, 0, 0, 0]);
        let (px, py) = project_point(&metrics, PI / 2.0, 0.7);
        let ix = px.round().clamp(0.0, f64::from(out_w - 1)) as usize;
        let iy = py.round().clamp(0.0, f64::from(out_h - 1)) as usize;
        let painted = (iy * out_w as usize + ix) * 4;
        assert_ne!(&rgba[painted..painted + 4], &[0, 0, 0, 0]);
        let south = ((out_h as usize - 1) * out_w as usize + out_w as usize / 2) * 4;
        assert_eq!(&rgba[south..south + 4], &[0, 0, 0, 0]);
    }

    #[test]
    fn polar_heatmap_inverse_hits_use_bottom_row_source_index() {
        let mut input = default_input();
        input.plot_w = 8.0;
        input.plot_h = 8.0;
        let mut metrics = [0.0; POLAR_METRICS_LEN];
        polar_layout(input, &mut metrics).unwrap();
        let (out_w, out_h, hits) = polar_heatmap_inverse_hits(
            &metrics, 0.0, 0.0, 8.0, 8.0, 2, 2, 0.0, 0.0, 2.0 * PI, 1.0, 1.0,
        )
        .unwrap();
        assert_eq!(out_w, 8);
        assert_eq!(out_h, 8);
        assert!(!hits.is_empty());
        assert!(hits.iter().all(|hit| hit.source_index < 4));
        assert!(hits.iter().all(|hit| hit.row < 8 && hit.col < 8));
    }
}
