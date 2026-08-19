//! Versioned, bounded canonical scene records and deterministic SVG emission.
//!
//! This first vertical slice owns the built-in scatter-mark scene. Hosts still
//! coerce author input and resolve paint channels, but marker geometry,
//! stroke-inclusive sizing, validation, bounds, and SVG construction live here.

use crate::css;
use crate::svg::push_num;
use std::fmt::Write;

pub const SCENE_VERSION: u32 = 1;
pub const MAX_SCENE_MARKS: usize = 2_000_000;
pub const MAX_AXIS_TICKS: usize = 200;

#[derive(Clone, Debug, PartialEq)]
pub struct AxisTicks {
    pub ticks: Vec<f64>,
    pub labeled: Vec<f64>,
    pub step: f64,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum ScaleKind {
    Linear,
    Log,
    SymLog,
}

#[derive(Clone, Copy, Debug)]
pub struct AxisScale {
    kind: ScaleKind,
    px0: f64,
    coord_lo: f64,
    coord_span: f64,
    px_delta: f64,
    constant: f64,
    mask_nonpositive: bool,
}

impl AxisScale {
    pub fn new(
        kind: ScaleKind,
        lo: f64,
        hi: f64,
        px0: f64,
        px1: f64,
        constant: f64,
        mask_nonpositive: bool,
    ) -> Result<Self, SceneError> {
        if [lo, hi, px0, px1, constant]
            .iter()
            .any(|value| !value.is_finite())
            || constant <= 0.0
        {
            return Err(SceneError::NonFinite);
        }
        let mut scale = Self {
            kind,
            px0,
            coord_lo: 0.0,
            coord_span: 1.0,
            px_delta: px1 - px0,
            constant,
            mask_nonpositive,
        };
        let coord_lo = scale.coord(lo);
        let coord_hi = scale.coord(hi);
        scale.coord_lo = coord_lo;
        scale.coord_span = if coord_hi == coord_lo {
            1.0
        } else {
            coord_hi - coord_lo
        };
        Ok(scale)
    }

    pub fn coord(self, value: f64) -> f64 {
        if value.is_nan() {
            return f64::NAN;
        }
        match self.kind {
            ScaleKind::Linear => value,
            ScaleKind::Log if value > 0.0 => value.log10(),
            ScaleKind::Log if self.mask_nonpositive => f64::NAN,
            ScaleKind::Log => 1e-300_f64.log10(),
            ScaleKind::SymLog => value.signum() * (value.abs() / self.constant).ln_1p(),
        }
    }

    pub fn value(self, coord: f64) -> f64 {
        match self.kind {
            ScaleKind::Linear => coord,
            ScaleKind::Log => 10_f64.powf(coord),
            ScaleKind::SymLog => coord.signum() * self.constant * coord.abs().exp_m1(),
        }
    }

    pub fn pixel(self, value: f64) -> f64 {
        self.px0 + (self.coord(value) - self.coord_lo) / self.coord_span * self.px_delta
    }
}

pub fn linear_ticks(lo: f64, hi: f64, target: usize) -> Result<AxisTicks, SceneError> {
    if !lo.is_finite() || !hi.is_finite() || target == 0 || target > MAX_AXIS_TICKS {
        return Err(SceneError::NonFinite);
    }
    let (a, b) = if lo <= hi { (lo, hi) } else { (hi, lo) };
    if a == b {
        return Ok(AxisTicks {
            ticks: vec![a],
            labeled: vec![a],
            step: 1.0,
        });
    }
    let rough = (b - a) / target as f64;
    let magnitude = 10_f64.powf(rough.abs().log10().floor());
    let step = [1.0, 2.0, 2.5, 5.0, 10.0]
        .into_iter()
        .map(|m| m * magnitude)
        .find(|candidate| rough <= candidate * (1.0 + 1e-12))
        .unwrap_or(10.0 * magnitude);
    let mut value = (a / step).ceil() * step;
    let mut ticks = Vec::with_capacity(target.saturating_add(2).min(MAX_AXIS_TICKS));
    while value <= b + step * 1e-9 && ticks.len() < MAX_AXIS_TICKS {
        ticks.push(if value.abs() < step * 1e-9 {
            0.0
        } else {
            value
        });
        value += step;
    }
    Ok(AxisTicks {
        labeled: ticks.clone(),
        ticks,
        step,
    })
}

pub fn log_ticks(lo: f64, hi: f64, target: usize) -> Result<AxisTicks, SceneError> {
    if !lo.is_finite()
        || !hi.is_finite()
        || lo <= 0.0
        || hi <= 0.0
        || target == 0
        || target > MAX_AXIS_TICKS
    {
        return Err(SceneError::NonFinite);
    }
    let (a, b) = if lo <= hi { (lo, hi) } else { (hi, lo) };
    let e0 = a.log10().floor() as i32;
    let e1 = b.log10().ceil() as i32;
    let multipliers: &[f64] = if (e1 - e0).max(1) <= (target as i32).max(2) {
        &[1.0, 2.0, 5.0]
    } else {
        &[1.0]
    };
    let label_every = (((e1 - e0 + 1) as f64 / target as f64).ceil() as i32).max(1);
    let mut ticks = Vec::new();
    let mut labeled = Vec::new();
    'outer: for exponent in e0..=e1 {
        let base = 10_f64.powi(exponent);
        for multiplier in multipliers {
            let value = multiplier * base;
            if value >= a * (1.0 - 1e-12) && value <= b * (1.0 + 1e-12) {
                ticks.push(value);
                if *multiplier == 1.0 && (exponent - e0) % label_every == 0 {
                    labeled.push(value);
                }
            }
            if ticks.len() >= MAX_AXIS_TICKS {
                break 'outer;
            }
        }
    }
    if labeled.is_empty() {
        labeled.clone_from(&ticks);
    }
    Ok(AxisTicks {
        ticks,
        labeled,
        step: 1.0,
    })
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
#[repr(u8)]
pub enum ScatterSymbol {
    Circle = 0,
    Square = 1,
    Diamond = 2,
    Triangle = 3,
    Cross = 4,
    Hexagon = 5,
    Pentagon = 6,
    Star = 7,
    TriangleDown = 8,
    TriangleLeft = 9,
    TriangleRight = 10,
    Point = 11,
    Pixel = 12,
    ThinDiamond = 13,
    PlusLine = 14,
    XLine = 15,
    HorizontalLine = 16,
    VerticalLine = 17,
    X = 18,
}

impl ScatterSymbol {
    fn from_code(value: u8) -> Self {
        match value {
            1 => Self::Square,
            2 => Self::Diamond,
            3 => Self::Triangle,
            4 => Self::Cross,
            5 => Self::Hexagon,
            6 => Self::Pentagon,
            7 => Self::Star,
            8 => Self::TriangleDown,
            9 => Self::TriangleLeft,
            10 => Self::TriangleRight,
            11 => Self::Point,
            12 => Self::Pixel,
            13 => Self::ThinDiamond,
            14 => Self::PlusLine,
            15 => Self::XLine,
            16 => Self::HorizontalLine,
            17 => Self::VerticalLine,
            18 => Self::X,
            _ => Self::Circle,
        }
    }

    fn is_line(self) -> bool {
        matches!(
            self,
            Self::PlusLine | Self::XLine | Self::HorizontalLine | Self::VerticalLine
        )
    }
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum SceneError {
    Length,
    Limit,
    NonFinite,
    NegativeSize,
    InvalidPaint,
}

pub struct ScatterScene<'a> {
    x: &'a [f64],
    y: &'a [f64],
    diameter: &'a [f64],
    fill_rgba: &'a [u8],
    stroke_rgba: &'a [u8],
    stroke_width: &'a [f64],
    symbols: &'a [u8],
    visible: Option<&'a [u8]>,
    fill_css: Option<&'a str>,
    stroke_css: Option<&'a str>,
}

impl<'a> ScatterScene<'a> {
    #[allow(clippy::too_many_arguments)]
    pub fn new(
        x: &'a [f64],
        y: &'a [f64],
        diameter: &'a [f64],
        fill_rgba: &'a [u8],
        stroke_rgba: &'a [u8],
        stroke_width: &'a [f64],
        symbols: &'a [u8],
        visible: Option<&'a [u8]>,
        fill_css: Option<&'a str>,
        stroke_css: Option<&'a str>,
    ) -> Result<Self, SceneError> {
        let len = x.len();
        if len > MAX_SCENE_MARKS {
            return Err(SceneError::Limit);
        }
        let rgba_len = len.checked_mul(4).ok_or(SceneError::Limit)?;
        if y.len() != len
            || diameter.len() != len
            || fill_rgba.len() != rgba_len
            || stroke_rgba.len() != rgba_len
            || stroke_width.len() != len
            || symbols.len() != len
            || visible.is_some_and(|items| items.len() != len)
        {
            return Err(SceneError::Length);
        }
        if x.iter()
            .chain(y)
            .chain(diameter)
            .chain(stroke_width)
            .any(|value| !value.is_finite())
        {
            return Err(SceneError::NonFinite);
        }
        if diameter.iter().any(|value| *value < 0.0)
            || stroke_width.iter().any(|value| *value < 0.0)
        {
            return Err(SceneError::NegativeSize);
        }
        if fill_css.is_some_and(|value| css::parse_color(value).is_err())
            || stroke_css.is_some_and(|value| css::parse_color(value).is_err())
        {
            return Err(SceneError::InvalidPaint);
        }
        Ok(Self {
            x,
            y,
            diameter,
            fill_rgba,
            stroke_rgba,
            stroke_width,
            symbols,
            visible,
            fill_css,
            stroke_css,
        })
    }

    pub fn to_svg(&self) -> String {
        let mut out = String::with_capacity(self.x.len().saturating_mul(112));
        out.push_str("<g>");
        for index in 0..self.x.len() {
            if self.visible.is_some_and(|items| items[index] == 0) {
                continue;
            }
            let symbol = ScatterSymbol::from_code(self.symbols[index]);
            let stroke_width = if symbol.is_line() && self.stroke_width[index] <= 0.0 {
                1.0
            } else {
                self.stroke_width[index]
            };
            let radius = (self.diameter[index] / 2.0 - stroke_width / 2.0).max(0.0);
            push_symbol(&mut out, symbol, self.x[index], self.y[index], radius);
            let fill = rgba_at(self.fill_rgba, index);
            let stroke = rgba_at(self.stroke_rgba, index);
            if symbol.is_line() {
                out.push_str(" fill=\"none\"");
            } else {
                push_paint(&mut out, "fill", fill, self.fill_css);
            }
            if stroke_width > 0.0 || symbol.is_line() {
                push_paint(&mut out, "stroke", stroke, self.stroke_css);
                out.push_str(" stroke-width=\"");
                push_num(&mut out, stroke_width);
                out.push('"');
            }
            out.push_str("/>");
        }
        out.push_str("</g>");
        out
    }
}

fn rgba_at(values: &[u8], index: usize) -> [u8; 4] {
    let offset = index * 4;
    [
        values[offset],
        values[offset + 1],
        values[offset + 2],
        values[offset + 3],
    ]
}

fn push_paint(out: &mut String, name: &str, rgba: [u8; 4], css: Option<&str>) {
    write!(out, " {name}=\"").expect("writing to String cannot fail");
    if let Some(value) = css {
        push_escaped_attribute(out, value);
    } else {
        write!(out, "rgb({},{},{})", rgba[0], rgba[1], rgba[2])
            .expect("writing to String cannot fail");
    }
    out.push('"');
    if rgba[3] < 255 {
        write!(out, " {name}-opacity=\"").expect("writing to String cannot fail");
        push_num(out, f64::from(rgba[3]) / 255.0);
        out.push('"');
    }
}

fn push_escaped_attribute(out: &mut String, value: &str) {
    for character in value.chars() {
        match character {
            '&' => out.push_str("&amp;"),
            '<' => out.push_str("&lt;"),
            '>' => out.push_str("&gt;"),
            '"' => out.push_str("&quot;"),
            _ => out.push(character),
        }
    }
}

fn point(out: &mut String, x: f64, y: f64) {
    push_num(out, x);
    out.push(' ');
    push_num(out, y);
}

fn push_symbol(out: &mut String, symbol: ScatterSymbol, cx: f64, cy: f64, radius: f64) {
    match symbol {
        ScatterSymbol::Circle | ScatterSymbol::Point => {
            out.push_str("<circle cx=\"");
            push_num(out, cx);
            out.push_str("\" cy=\"");
            push_num(out, cy);
            out.push_str("\" r=\"");
            push_num(out, radius);
            out.push('"');
        }
        ScatterSymbol::Square | ScatterSymbol::Pixel => {
            out.push_str("<rect x=\"");
            push_num(out, cx - radius);
            out.push_str("\" y=\"");
            push_num(out, cy - radius);
            out.push_str("\" width=\"");
            push_num(out, radius * 2.0);
            out.push_str("\" height=\"");
            push_num(out, radius * 2.0);
            out.push('"');
        }
        ScatterSymbol::Diamond | ScatterSymbol::ThinDiamond => {
            let dx = std::f64::consts::SQRT_2
                * radius
                * if symbol == ScatterSymbol::ThinDiamond {
                    0.6
                } else {
                    1.0
                };
            let dy = std::f64::consts::SQRT_2 * radius;
            out.push_str("<path d=\"M ");
            point(out, cx, cy - dy);
            out.push_str(" L ");
            point(out, cx + dx, cy);
            out.push_str(" L ");
            point(out, cx, cy + dy);
            out.push_str(" L ");
            point(out, cx - dx, cy);
            out.push_str(" Z\"");
        }
        ScatterSymbol::Triangle
        | ScatterSymbol::TriangleDown
        | ScatterSymbol::TriangleLeft
        | ScatterSymbol::TriangleRight => push_triangle(out, symbol, cx, cy, radius),
        ScatterSymbol::Cross => push_cross(out, cx, cy, radius),
        ScatterSymbol::X => push_x(out, cx, cy, radius),
        ScatterSymbol::PlusLine => {
            out.push_str("<path d=\"M ");
            point(out, cx - radius, cy);
            out.push_str(" H ");
            push_num(out, cx + radius);
            out.push_str(" M ");
            point(out, cx, cy - radius);
            out.push_str(" V ");
            push_num(out, cy + radius);
            out.push('"');
        }
        ScatterSymbol::XLine => {
            let delta = 0.707 * radius;
            out.push_str("<path d=\"M ");
            point(out, cx - delta, cy - delta);
            out.push_str(" L ");
            point(out, cx + delta, cy + delta);
            out.push_str(" M ");
            point(out, cx + delta, cy - delta);
            out.push_str(" L ");
            point(out, cx - delta, cy + delta);
            out.push('"');
        }
        ScatterSymbol::HorizontalLine | ScatterSymbol::VerticalLine => {
            out.push_str("<path d=\"M ");
            if symbol == ScatterSymbol::HorizontalLine {
                point(out, cx - radius, cy);
                out.push_str(" H ");
                push_num(out, cx + radius);
            } else {
                point(out, cx, cy - radius);
                out.push_str(" V ");
                push_num(out, cy + radius);
            }
            out.push('"');
        }
        ScatterSymbol::Pentagon => push_regular_polygon(out, cx, cy, radius, 5, -90.0, 1.0),
        ScatterSymbol::Hexagon => push_regular_polygon(out, cx, cy, radius, 6, -90.0, 1.0),
        ScatterSymbol::Star => push_regular_polygon(out, cx, cy, radius, 10, -90.0, 0.45),
    }
}

fn push_triangle(out: &mut String, symbol: ScatterSymbol, cx: f64, cy: f64, r: f64) {
    let points = match symbol {
        ScatterSymbol::Triangle => [(cx, cy - r), (cx + r, cy + r), (cx - r, cy + r)],
        ScatterSymbol::TriangleDown => [(cx, cy + r), (cx + r, cy - r), (cx - r, cy - r)],
        ScatterSymbol::TriangleLeft => [(cx - r, cy), (cx + r, cy - r), (cx + r, cy + r)],
        _ => [(cx + r, cy), (cx - r, cy - r), (cx - r, cy + r)],
    };
    out.push_str("<path d=\"M ");
    point(out, points[0].0, points[0].1);
    for item in &points[1..] {
        out.push_str(" L ");
        point(out, item.0, item.1);
    }
    out.push_str(" Z\"");
}

fn push_cross(out: &mut String, cx: f64, cy: f64, r: f64) {
    let d = 0.34 * r;
    out.push_str("<path d=\"M ");
    point(out, cx - d, cy - r);
    write!(out, " H ").expect("writing to String cannot fail");
    push_num(out, cx + d);
    out.push_str(" V ");
    push_num(out, cy - d);
    out.push_str(" H ");
    push_num(out, cx + r);
    out.push_str(" V ");
    push_num(out, cy + d);
    out.push_str(" H ");
    push_num(out, cx + d);
    out.push_str(" V ");
    push_num(out, cy + r);
    out.push_str(" H ");
    push_num(out, cx - d);
    out.push_str(" V ");
    push_num(out, cy + d);
    out.push_str(" H ");
    push_num(out, cx - r);
    out.push_str(" V ");
    push_num(out, cy - d);
    out.push_str(" H ");
    push_num(out, cx - d);
    out.push_str(" Z\"");
}

fn push_x(out: &mut String, cx: f64, cy: f64, r: f64) {
    let outer = 0.72 * r;
    let inner = 0.28 * r;
    let points = [
        (cx - outer, cy - r),
        (cx, cy - inner),
        (cx + outer, cy - r),
        (cx + r, cy - outer),
        (cx + inner, cy),
        (cx + r, cy + outer),
        (cx + outer, cy + r),
        (cx, cy + inner),
        (cx - outer, cy + r),
        (cx - r, cy + outer),
        (cx - inner, cy),
        (cx - r, cy - outer),
    ];
    out.push_str("<path d=\"M ");
    point(out, points[0].0, points[0].1);
    for item in &points[1..] {
        out.push_str(" L ");
        point(out, item.0, item.1);
    }
    out.push_str(" Z\"");
}

fn push_regular_polygon(
    out: &mut String,
    cx: f64,
    cy: f64,
    radius: f64,
    vertices: usize,
    start_degrees: f64,
    inner_ratio: f64,
) {
    out.push_str("<path d=\"M ");
    for index in 0..vertices {
        if index != 0 {
            out.push_str(" L ");
        }
        let point_radius = if inner_ratio < 1.0 && index % 2 == 1 {
            radius * inner_ratio
        } else {
            radius
        };
        let angle = (start_degrees + index as f64 * 360.0 / vertices as f64).to_radians();
        point(
            out,
            cx + point_radius * angle.cos(),
            cy + point_radius * angle.sin(),
        );
    }
    out.push_str(" Z\"");
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn scatter_scene_is_versioned_bounded_and_deterministic() {
        let scene = ScatterScene::new(
            &[10.0, 20.0],
            &[11.0, 21.0],
            &[8.0, 10.0],
            &[37, 99, 235, 255, 239, 68, 68, 128],
            &[0, 0, 0, 255, 17, 24, 39, 64],
            &[2.0, 0.0],
            &[ScatterSymbol::Circle as u8, ScatterSymbol::PlusLine as u8],
            None,
            None,
            None,
        )
        .unwrap();
        assert_eq!(SCENE_VERSION, 1);
        assert_eq!(
            scene.to_svg(),
            "<g><circle cx=\"10\" cy=\"11\" r=\"3\" fill=\"rgb(37,99,235)\" stroke=\"rgb(0,0,0)\" stroke-width=\"2\"/><path d=\"M 15.5 21 H 24.5 M 20 16.5 V 25.5\" fill=\"none\" stroke=\"rgb(17,24,39)\" stroke-opacity=\"0.25\" stroke-width=\"1\"/></g>"
        );
    }

    #[test]
    fn scatter_scene_rejects_bad_lengths_nonfinite_and_negative_sizes() {
        assert_eq!(
            ScatterScene::new(
                &[1.0],
                &[],
                &[1.0],
                &[0; 4],
                &[0; 4],
                &[0.0],
                &[0],
                None,
                None,
                None,
            )
            .err(),
            Some(SceneError::Length)
        );
        assert_eq!(
            ScatterScene::new(
                &[f64::NAN],
                &[1.0],
                &[1.0],
                &[0; 4],
                &[0; 4],
                &[0.0],
                &[0],
                None,
                None,
                None,
            )
            .err(),
            Some(SceneError::NonFinite)
        );
        assert_eq!(
            ScatterScene::new(
                &[1.0],
                &[1.0],
                &[-1.0],
                &[0; 4],
                &[0; 4],
                &[0.0],
                &[0],
                None,
                None,
                None,
            )
            .err(),
            Some(SceneError::NegativeSize)
        );
    }

    #[test]
    fn scatter_scene_rejects_limit_and_invalid_paint() {
        let too_many = vec![0.0; MAX_SCENE_MARKS + 1];
        assert_eq!(
            ScatterScene::new(&too_many, &[], &[], &[], &[], &[], &[], None, None, None,).err(),
            Some(SceneError::Limit)
        );
        assert_eq!(
            ScatterScene::new(
                &[1.0],
                &[1.0],
                &[1.0],
                &[0; 4],
                &[0; 4],
                &[0.0],
                &[0],
                None,
                Some("not-a-color"),
                None,
            )
            .err(),
            Some(SceneError::InvalidPaint)
        );
    }

    #[test]
    fn scatter_scene_hides_marks_and_preserves_constant_css_paint() {
        let scene = ScatterScene::new(
            &[10.0, 20.0],
            &[11.0, 21.0],
            &[8.0, 10.0],
            &[37, 99, 235, 255, 239, 68, 68, 128],
            &[0; 8],
            &[0.0, 0.0],
            &[ScatterSymbol::Circle as u8, ScatterSymbol::Circle as u8],
            Some(&[0, 1]),
            Some("var(--brand)"),
            None,
        )
        .unwrap();
        assert_eq!(
            scene.to_svg(),
            "<g><circle cx=\"20\" cy=\"21\" r=\"5\" fill=\"var(--brand)\" fill-opacity=\"0.5\"/></g>"
        );

        let mut escaped = String::new();
        push_escaped_attribute(&mut escaped, "&<>\"");
        assert_eq!(escaped, "&amp;&lt;&gt;&quot;");
    }

    #[test]
    fn symbol_shape_families_have_deterministic_svg() {
        let mut outputs = Vec::new();
        for symbol in [
            ScatterSymbol::Square,
            ScatterSymbol::Diamond,
            ScatterSymbol::Triangle,
            ScatterSymbol::Cross,
            ScatterSymbol::X,
            ScatterSymbol::Pentagon,
            ScatterSymbol::Star,
        ] {
            let mut output = String::new();
            push_symbol(&mut output, symbol, 10.0, 20.0, 2.0);
            outputs.push(output);
        }
        assert!(outputs.iter().map(String::as_str).eq([
            "<rect x=\"8\" y=\"18\" width=\"4\" height=\"4\"",
            "<path d=\"M 10 17.17 L 12.83 20 L 10 22.83 L 7.17 20 Z\"",
            "<path d=\"M 10 18 L 12 22 L 8 22 Z\"",
            "<path d=\"M 9.32 18 H 10.68 V 19.32 H 12 V 20.68 H 10.68 V 22 H 9.32 V 20.68 H 8 V 19.32 H 9.32 Z\"",
            "<path d=\"M 8.56 18 L 10 19.44 L 11.44 18 L 12 18.56 L 10.56 20 L 12 21.44 L 11.44 22 L 10 20.56 L 8.56 22 L 8 21.44 L 9.44 20 L 8 18.56 Z\"",
            "<path d=\"M 10 18 L 11.9 19.38 L 11.18 21.62 L 8.82 21.62 L 8.1 19.38 Z\"",
            "<path d=\"M 10 18 L 10.53 19.27 L 11.9 19.38 L 10.86 20.28 L 11.18 21.62 L 10 20.9 L 8.82 21.62 L 9.14 20.28 L 8.1 19.38 L 9.47 19.27 Z\"",
        ]));
    }

    #[test]
    fn canonical_linear_and_log_ticks_match_public_policy() {
        assert_eq!(
            linear_ticks(-0.9, 5.1, 6).unwrap(),
            AxisTicks {
                ticks: vec![0.0, 1.0, 2.0, 3.0, 4.0, 5.0],
                labeled: vec![0.0, 1.0, 2.0, 3.0, 4.0, 5.0],
                step: 1.0,
            }
        );
        let log = log_ticks(0.1, 100.0, 6).unwrap();
        assert_eq!(
            log.ticks,
            vec![0.1, 0.2, 0.5, 1.0, 2.0, 5.0, 10.0, 20.0, 50.0, 100.0]
        );
        assert_eq!(log.labeled, vec![0.1, 1.0, 10.0, 100.0]);
        assert_eq!(log.step, 1.0);
    }

    #[test]
    fn canonical_axis_scales_map_and_invert_all_numeric_kinds() {
        let linear = AxisScale::new(ScaleKind::Linear, 0.0, 10.0, 20.0, 120.0, 1.0, false).unwrap();
        assert_eq!(linear.pixel(5.0), 70.0);
        let log = AxisScale::new(ScaleKind::Log, 0.1, 100.0, 0.0, 300.0, 1.0, false).unwrap();
        assert_eq!(log.pixel(1.0), 100.0);
        assert_eq!(log.coord(-1.0), -300.0);
        let masked = AxisScale::new(ScaleKind::Log, 0.1, 100.0, 0.0, 300.0, 1.0, true).unwrap();
        assert!(masked.coord(0.0).is_nan());
        let symlog =
            AxisScale::new(ScaleKind::SymLog, -10.0, 10.0, 0.0, 100.0, 2.0, false).unwrap();
        let coordinate = symlog.coord(-4.0);
        assert!((symlog.value(coordinate) + 4.0).abs() < 1e-12);
        assert!((symlog.pixel(0.0) - 50.0).abs() < 1e-12);
    }

    #[test]
    fn precomputed_pixel_invariants_preserve_reference_mapping() {
        for (kind, lo, hi, px0, px1, constant, mask, values) in [
            (
                ScaleKind::Linear,
                10.0,
                -2.0,
                700.0,
                20.0,
                1.0,
                false,
                vec![-2.0, 0.0, 10.0, f64::NAN],
            ),
            (
                ScaleKind::Linear,
                4.0,
                4.0,
                8.0,
                18.0,
                1.0,
                false,
                vec![4.0, 5.0],
            ),
            (
                ScaleKind::Log,
                0.1,
                100.0,
                0.0,
                300.0,
                1.0,
                false,
                vec![-1.0, 0.1, 1.0, 100.0, f64::NAN],
            ),
            (
                ScaleKind::Log,
                0.1,
                100.0,
                300.0,
                0.0,
                1.0,
                true,
                vec![0.0, 0.1, 10.0],
            ),
            (
                ScaleKind::SymLog,
                -20.0,
                20.0,
                5.0,
                405.0,
                2.0,
                false,
                vec![-20.0, -1.0, 0.0, 7.0, 20.0],
            ),
        ] {
            let scale = AxisScale::new(kind, lo, hi, px0, px1, constant, mask).unwrap();
            let low = scale.coord(lo);
            let high = scale.coord(hi);
            let span = if high == low { 1.0 } else { high - low };
            for value in values {
                let expected = px0 + (scale.coord(value) - low) / span * (px1 - px0);
                let actual = scale.pixel(value);
                assert!(
                    (expected.is_nan() && actual.is_nan())
                        || expected.to_bits() == actual.to_bits(),
                    "{kind:?} value {value}: expected {expected:?}, got {actual:?}"
                );
            }
        }
    }
}
