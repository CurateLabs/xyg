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
}
