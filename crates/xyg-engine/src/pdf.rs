//! Closed-subset SVG → vector PDF converter (M2 #274).
//!
//! Ports `python/xyg/_pdf.py` so public static PDF (Scene and compatibility)
//! is Rust-owned. The accepted SVG vocabulary is the same closed generator
//! subset: unknown elements/attributes fail with
//! `unsupported SVG feature: …`. Hosts only coerce UTF-8 and call the ABI.

use std::collections::HashMap;
use std::io::{Cursor, Write};

use flate2::write::ZlibEncoder;
use flate2::Compression;

use crate::css::{self, Checked};

const PX_TO_PT: f64 = 0.75;
const DEFAULT_FONT_SIZE: f64 = 16.0;
const KAPPA: f64 = 0.5522847498307936;
const PNG_SIG: &[u8] = b"\x89PNG\r\n\x1a\n";

const HELV: [u16; 224] = [
    278, 278, 355, 556, 556, 889, 667, 191, 333, 333, 389, 584, 278, 333, 278, 278, 556, 556, 556,
    556, 556, 556, 556, 556, 556, 556, 278, 278, 584, 584, 584, 556, 1015, 667, 667, 722, 722, 667,
    611, 778, 722, 278, 500, 667, 556, 833, 722, 778, 667, 778, 722, 667, 611, 722, 667, 944, 667,
    667, 611, 278, 278, 278, 469, 556, 333, 556, 556, 500, 556, 556, 278, 556, 556, 222, 222, 500,
    222, 833, 556, 556, 556, 556, 333, 500, 278, 556, 500, 722, 500, 500, 500, 334, 260, 334, 584,
    350, 556, 350, 222, 556, 333, 1000, 556, 556, 333, 1000, 667, 333, 1000, 350, 611, 350, 350,
    222, 222, 333, 333, 350, 556, 1000, 333, 1000, 500, 333, 944, 350, 500, 667, 278, 333, 556,
    556, 556, 556, 260, 556, 333, 737, 370, 556, 584, 333, 737, 333, 400, 584, 333, 333, 333, 556,
    537, 278, 333, 333, 365, 556, 834, 834, 834, 611, 667, 667, 667, 667, 667, 667, 1000, 722, 667,
    667, 667, 667, 278, 278, 278, 278, 722, 722, 778, 778, 778, 778, 778, 584, 778, 722, 722, 722,
    722, 667, 667, 611, 556, 556, 556, 556, 556, 556, 889, 500, 556, 556, 556, 556, 278, 278, 278,
    278, 556, 556, 556, 556, 556, 556, 556, 584, 611, 556, 556, 556, 556, 500, 556, 500,
];
const HELV_BOLD: [u16; 224] = [
    278, 333, 474, 556, 556, 889, 722, 238, 333, 333, 389, 584, 278, 333, 278, 278, 556, 556, 556,
    556, 556, 556, 556, 556, 556, 556, 333, 333, 584, 584, 584, 611, 975, 722, 722, 722, 722, 667,
    611, 778, 722, 278, 556, 722, 611, 833, 722, 778, 667, 778, 722, 667, 611, 722, 667, 944, 667,
    667, 611, 333, 278, 333, 584, 556, 333, 556, 611, 556, 611, 556, 333, 611, 611, 278, 278, 556,
    278, 889, 611, 611, 611, 611, 389, 556, 333, 611, 556, 778, 556, 556, 500, 389, 280, 389, 584,
    350, 556, 350, 278, 556, 500, 1000, 556, 556, 333, 1000, 667, 333, 1000, 350, 611, 350, 350,
    278, 278, 500, 500, 350, 556, 1000, 333, 1000, 556, 333, 944, 350, 500, 667, 278, 333, 556,
    556, 556, 556, 280, 556, 333, 737, 370, 556, 584, 333, 737, 333, 400, 584, 333, 333, 333, 611,
    556, 278, 333, 333, 365, 556, 834, 834, 834, 611, 722, 722, 722, 722, 722, 722, 1000, 722, 667,
    667, 667, 667, 278, 278, 278, 278, 722, 722, 778, 778, 778, 778, 778, 584, 778, 722, 722, 722,
    722, 667, 667, 611, 556, 556, 556, 556, 556, 556, 889, 556, 556, 556, 556, 556, 278, 278, 278,
    278, 611, 611, 611, 611, 611, 611, 611, 584, 611, 611, 611, 611, 611, 556, 611, 556,
];

const INERT_A11Y: &[&str] = &["aria-hidden", "aria-label", "role"];
const PAINT_ATTRS: &[&str] = &[
    "fill",
    "fill-opacity",
    "opacity",
    "stroke",
    "stroke-width",
    "stroke-opacity",
    "stroke-dasharray",
    "stroke-linecap",
    "stroke-linejoin",
];

#[derive(Debug, Clone)]
struct Elem {
    name: String,
    attrs: Vec<(String, String)>,
    children: Vec<Elem>,
    text: String,
    tail: String,
}

impl Elem {
    fn attr(&self, name: &str) -> Option<&str> {
        self.attrs
            .iter()
            .find(|(key, _)| key == name)
            .map(|(_, value)| value.as_str())
    }
}

type PdfResult<T> = Result<T, String>;

fn unsupported(what: impl Into<String>) -> String {
    format!("unsupported SVG feature: {}", what.into())
}

fn fail<T>(what: impl Into<String>) -> PdfResult<T> {
    Err(unsupported(what))
}

/// Convert an xy-generated SVG document into a single-page vector PDF.
pub fn svg_to_pdf(svg: &str) -> PdfResult<Vec<u8>> {
    let root = parse_xml(svg).map_err(|err| unsupported(format!("unparseable XML ({err})")))?;
    Converter::new().run(&root)
}

fn fmt_num(value: f64) -> String {
    if !value.is_finite() {
        return "0".into();
    }
    let formatted = format!("{value:.4}");
    let trimmed = formatted.trim_end_matches('0').trim_end_matches('.');
    if trimmed.is_empty() || trimmed == "-0" {
        "0".into()
    } else {
        trimmed.to_string()
    }
}

fn parse_float(value: Option<&str>, default: f64, what: &str) -> PdfResult<f64> {
    let Some(raw) = value else {
        return Ok(default);
    };
    raw.parse::<f64>()
        .map_err(|_| unsupported(format!("{what} {raw:?}")))
}

fn rgba_css(css: &str) -> PdfResult<(f64, f64, f64, f64)> {
    match css::parse_color(css) {
        Ok(Checked::Parsed(Some(rgba))) => Ok((
            f64::from(rgba[0]),
            f64::from(rgba[1]),
            f64::from(rgba[2]),
            f64::from(rgba[3]),
        )),
        _ => fail(format!("color {css:?}")),
    }
}

fn text_width_px(data: &[u8], size: f64, bold: bool) -> f64 {
    let table = if bold { &HELV_BOLD } else { &HELV };
    let mut sum = 0u32;
    for &byte in data {
        if byte >= 32 {
            sum += u32::from(table[byte as usize - 32]);
        }
    }
    size * f64::from(sum) / 1000.0
}

fn pdf_string(data: &[u8]) -> String {
    let mut out = String::from("(");
    for &byte in data {
        match byte {
            b'(' | b')' | b'\\' => {
                out.push('\\');
                out.push(byte as char);
            }
            32..=126 => out.push(byte as char),
            _ => out.push_str(&format!("\\{byte:03o}")),
        }
    }
    out.push(')');
    out
}

fn encode_cp1252(text: &str) -> Vec<u8> {
    text.chars()
        .map(|ch| {
            let code = ch as u32;
            if code < 0x80 {
                return code as u8;
            }
            if (0xA0..=0xFF).contains(&code) {
                return code as u8;
            }
            match ch {
                '\u{20AC}' => 0x80,
                '\u{201A}' => 0x82,
                '\u{0192}' => 0x83,
                '\u{201E}' => 0x84,
                '\u{2026}' => 0x85,
                '\u{2020}' => 0x86,
                '\u{2021}' => 0x87,
                '\u{02C6}' => 0x88,
                '\u{2030}' => 0x89,
                '\u{0160}' => 0x8A,
                '\u{2039}' => 0x8B,
                '\u{0152}' => 0x8C,
                '\u{017D}' => 0x8E,
                '\u{2018}' => 0x91,
                '\u{2019}' => 0x92,
                '\u{201C}' => 0x93,
                '\u{201D}' => 0x94,
                '\u{2022}' => 0x95,
                '\u{2013}' => 0x96,
                '\u{2014}' => 0x97,
                '\u{02DC}' => 0x98,
                '\u{2122}' => 0x99,
                '\u{0161}' => 0x9A,
                '\u{203A}' => 0x9B,
                '\u{0153}' => 0x9C,
                '\u{017E}' => 0x9E,
                '\u{0178}' => 0x9F,
                _ => b'?',
            }
        })
        .collect()
}

fn numbers(input: &str) -> Vec<f64> {
    let mut out = Vec::new();
    let bytes = input.as_bytes();
    let mut index = 0;
    while index < bytes.len() {
        let start = index;
        let c = bytes[index];
        if c == b'+' || c == b'-' || c == b'.' || c.is_ascii_digit() {
            index += 1;
            while index < bytes.len()
                && (bytes[index].is_ascii_digit()
                    || bytes[index] == b'.'
                    || bytes[index] == b'e'
                    || bytes[index] == b'E'
                    || bytes[index] == b'+'
                    || bytes[index] == b'-')
            {
                if (bytes[index] == b'+' || bytes[index] == b'-')
                    && bytes[index - 1] != b'e'
                    && bytes[index - 1] != b'E'
                {
                    break;
                }
                index += 1;
            }
            if let Ok(value) = input[start..index].parse::<f64>() {
                out.push(value);
            }
            continue;
        }
        index += 1;
    }
    out
}

fn path_tokens(data: &str) -> Vec<String> {
    let mut out = Vec::new();
    let bytes = data.as_bytes();
    let mut index = 0;
    while index < bytes.len() {
        let c = bytes[index];
        if c.is_ascii_alphabetic() {
            out.push((c as char).to_string());
            index += 1;
            continue;
        }
        if c == b'+' || c == b'-' || c == b'.' || c.is_ascii_digit() {
            let start = index;
            index += 1;
            while index < bytes.len()
                && (bytes[index].is_ascii_digit()
                    || bytes[index] == b'.'
                    || bytes[index] == b'e'
                    || bytes[index] == b'E'
                    || bytes[index] == b'+'
                    || bytes[index] == b'-')
            {
                if (bytes[index] == b'+' || bytes[index] == b'-')
                    && bytes[index - 1] != b'e'
                    && bytes[index - 1] != b'E'
                {
                    break;
                }
                index += 1;
            }
            out.push(data[start..index].to_string());
            continue;
        }
        index += 1;
    }
    out
}

fn url_id(raw: &str) -> Option<&str> {
    let trimmed = raw.trim();
    let rest = trimmed.strip_prefix("url(#")?.strip_suffix(')')?;
    if rest.is_empty() || rest.contains(')') {
        return None;
    }
    Some(rest)
}

fn parse_rotate(transform: &str) -> Option<(f64, Option<(f64, f64)>)> {
    let trimmed = transform.trim();
    let inner = trimmed.strip_prefix("rotate(")?.strip_suffix(')')?.trim();
    let parts: Vec<&str> = inner
        .split(|c: char| c.is_whitespace() || c == ',')
        .filter(|part| !part.is_empty())
        .collect();
    if parts.len() == 1 {
        return Some((parts[0].parse().ok()?, None));
    }
    if parts.len() == 3 {
        return Some((
            parts[0].parse().ok()?,
            Some((parts[1].parse().ok()?, parts[2].parse().ok()?)),
        ));
    }
    None
}

fn allowed_attrs(tag: &str) -> &'static [&'static str] {
    match tag {
        "svg" => &[
            "width",
            "height",
            "viewBox",
            "font-family",
            "font-size",
            "xmlns",
        ],
        "svg-nested" => &["x", "y", "width", "height", "viewBox"],
        "defs" => &[],
        "clipPath" => &["id"],
        "clip-circle" => &["cx", "cy", "r"],
        "clip-path-shape" => &["d", "clip-rule"],
        "clip-rect" => &["x", "y", "width", "height"],
        "linearGradient" => &["id", "x1", "y1", "x2", "y2", "gradientUnits"],
        "stop" => &["offset", "stop-color", "stop-opacity"],
        "g" => &[
            "clip-path",
            "fill",
            "fill-opacity",
            "stroke-opacity",
            "opacity",
        ],
        "rect" => &[
            "x",
            "y",
            "width",
            "height",
            "rx",
            "fill",
            "fill-opacity",
            "opacity",
            "stroke",
            "stroke-width",
            "stroke-opacity",
            "stroke-dasharray",
            "stroke-linecap",
            "stroke-linejoin",
        ],
        "circle" => &[
            "cx",
            "cy",
            "r",
            "fill",
            "fill-opacity",
            "opacity",
            "stroke",
            "stroke-width",
            "stroke-opacity",
            "stroke-dasharray",
            "stroke-linecap",
            "stroke-linejoin",
        ],
        "line" => &[
            "x1",
            "y1",
            "x2",
            "y2",
            "fill",
            "fill-opacity",
            "opacity",
            "stroke",
            "stroke-width",
            "stroke-opacity",
            "stroke-dasharray",
            "stroke-linecap",
            "stroke-linejoin",
        ],
        "path" | "polyline" | "polygon" => PAINT_ATTRS,
        "path-d" => &["d"],
        "text" => &[
            "x",
            "y",
            "transform",
            "text-anchor",
            "font-size",
            "font-weight",
            "fill",
            "fill-opacity",
        ],
        "tspan" => &["x", "y", "dy"],
        "image" => &[
            "x",
            "y",
            "width",
            "height",
            "preserveAspectRatio",
            "style",
            "href",
        ],
        _ => &[],
    }
}

fn check_attrs(el: &Elem, tag: &str, extra: &[&str]) -> PdfResult<()> {
    let allowed = extra;
    for (name, _) in &el.attrs {
        if name.starts_with("data-") || INERT_A11Y.contains(&name.as_str()) {
            continue;
        }
        if name == "xmlns" || name.starts_with("xmlns:") {
            continue;
        }
        if !allowed.iter().any(|key| *key == name) {
            return fail(format!("<{tag}> attribute {name:?}"));
        }
    }
    Ok(())
}

#[derive(Clone)]
enum Seg {
    M(f64, f64),
    L(f64, f64),
    C(f64, f64, f64, f64, f64, f64),
    Z,
}

fn arc_cubics(
    x1: f64,
    y1: f64,
    mut rx: f64,
    mut ry: f64,
    phi_deg: f64,
    large: bool,
    sweep: bool,
    x2: f64,
    y2: f64,
) -> Vec<Seg> {
    if rx == 0.0 || ry == 0.0 || (x1 == x2 && y1 == y2) {
        return vec![Seg::L(x2, y2)];
    }
    rx = rx.abs();
    ry = ry.abs();
    let phi = phi_deg.to_radians();
    let (cosp, sinp) = (phi.cos(), phi.sin());
    let dx2 = (x1 - x2) / 2.0;
    let dy2 = (y1 - y2) / 2.0;
    let x1p = cosp * dx2 + sinp * dy2;
    let y1p = -sinp * dx2 + cosp * dy2;
    let lam = (x1p / rx).powi(2) + (y1p / ry).powi(2);
    if lam > 1.0 {
        let scale = lam.sqrt();
        rx *= scale;
        ry *= scale;
    }
    let num = rx * rx * ry * ry - rx * rx * y1p * y1p - ry * ry * x1p * x1p;
    let den = rx * rx * y1p * y1p + ry * ry * x1p * x1p;
    let mut co = if den == 0.0 {
        0.0
    } else {
        (num / den).max(0.0).sqrt()
    };
    if large == sweep {
        co = -co;
    }
    let cxp = co * rx * y1p / ry;
    let cyp = -co * ry * x1p / rx;
    let cx = cosp * cxp - sinp * cyp + (x1 + x2) / 2.0;
    let cy = sinp * cxp + cosp * cyp + (y1 + y2) / 2.0;
    let angle = |ux: f64, uy: f64, vx: f64, vy: f64| {
        let dot = ux * vx + uy * vy;
        let norm = (ux.hypot(uy)) * (vx.hypot(vy));
        let mut a = if norm == 0.0 {
            0.0
        } else {
            (dot / norm).clamp(-1.0, 1.0).acos()
        };
        if ux * vy - uy * vx < 0.0 {
            a = -a;
        }
        a
    };
    let theta1 = angle(1.0, 0.0, (x1p - cxp) / rx, (y1p - cyp) / ry);
    let mut dtheta = angle(
        (x1p - cxp) / rx,
        (y1p - cyp) / ry,
        (-x1p - cxp) / rx,
        (-y1p - cyp) / ry,
    )
    .rem_euclid(std::f64::consts::TAU);
    if !sweep && dtheta > 0.0 {
        dtheta -= std::f64::consts::TAU;
    } else if sweep && dtheta < 0.0 {
        dtheta += std::f64::consts::TAU;
    }
    let n = ((dtheta.abs() / (std::f64::consts::PI / 2.0)).ceil() as i32).max(1);
    let step = dtheta / f64::from(n);
    let mut out = Vec::new();
    for i in 0..n {
        let t0 = theta1 + f64::from(i) * step;
        let t1 = theta1 + f64::from(i + 1) * step;
        let alpha = 4.0 / 3.0 * ((t1 - t0) / 4.0).tan();
        let point = |t: f64| {
            let (ct, st) = (t.cos(), t.sin());
            (
                cx + rx * ct * cosp - ry * st * sinp,
                cy + rx * ct * sinp + ry * st * cosp,
            )
        };
        let deriv = |t: f64| {
            let (ct, st) = (t.cos(), t.sin());
            (
                -rx * st * cosp - ry * ct * sinp,
                -rx * st * sinp + ry * ct * cosp,
            )
        };
        let (p0x, p0y) = point(t0);
        let (p1x, p1y) = point(t1);
        let (d0x, d0y) = deriv(t0);
        let (d1x, d1y) = deriv(t1);
        out.push(Seg::C(
            p0x + alpha * d0x,
            p0y + alpha * d0y,
            p1x - alpha * d1x,
            p1y - alpha * d1y,
            p1x,
            p1y,
        ));
    }
    out
}

fn parse_path(d: &str) -> PdfResult<Vec<Seg>> {
    let tokens = path_tokens(d);
    let mut segs = Vec::new();
    let mut i = 0;
    let mut cx = 0.0;
    let mut cy = 0.0;
    let mut cmd: Option<char> = None;
    let take = |i: &mut usize, n: usize, tokens: &[String], d: &str| -> PdfResult<Vec<f64>> {
        if *i + n > tokens.len()
            || tokens[*i..*i + n]
                .iter()
                .any(|t| t.chars().all(char::is_alphabetic))
        {
            return fail(format!("path data {:?}", &d[..d.len().min(40)]));
        }
        let mut vals = Vec::with_capacity(n);
        for _ in 0..n {
            vals.push(
                tokens[*i]
                    .parse::<f64>()
                    .map_err(|_| unsupported(format!("path data {:?}", &d[..d.len().min(40)])))?,
            );
            *i += 1;
        }
        Ok(vals)
    };
    while i < tokens.len() {
        let tok = &tokens[i];
        if tok.chars().all(char::is_alphabetic) && tok.len() == 1 {
            let next = tok.chars().next().unwrap();
            if !matches!(next, 'M' | 'L' | 'C' | 'A' | 'H' | 'V' | 'Z') {
                return fail(format!("path command {next:?}"));
            }
            cmd = Some(next);
            i += 1;
            if next == 'Z' {
                segs.push(Seg::Z);
                cmd = None;
            }
            continue;
        }
        let Some(current) = cmd else {
            return fail(format!("path data {:?}", &d[..d.len().min(40)]));
        };
        match current {
            'M' => {
                let vals = take(&mut i, 2, &tokens, d)?;
                cx = vals[0];
                cy = vals[1];
                segs.push(Seg::M(cx, cy));
                cmd = Some('L');
            }
            'L' => {
                let vals = take(&mut i, 2, &tokens, d)?;
                cx = vals[0];
                cy = vals[1];
                segs.push(Seg::L(cx, cy));
            }
            'H' => {
                let vals = take(&mut i, 1, &tokens, d)?;
                cx = vals[0];
                segs.push(Seg::L(cx, cy));
            }
            'V' => {
                let vals = take(&mut i, 1, &tokens, d)?;
                cy = vals[0];
                segs.push(Seg::L(cx, cy));
            }
            'C' => {
                let vals = take(&mut i, 6, &tokens, d)?;
                cx = vals[4];
                cy = vals[5];
                segs.push(Seg::C(vals[0], vals[1], vals[2], vals[3], vals[4], vals[5]));
            }
            'A' => {
                let vals = take(&mut i, 7, &tokens, d)?;
                for piece in arc_cubics(
                    cx,
                    cy,
                    vals[0],
                    vals[1],
                    vals[2],
                    vals[3] != 0.0,
                    vals[4] != 0.0,
                    vals[5],
                    vals[6],
                ) {
                    segs.push(piece);
                }
                cx = vals[5];
                cy = vals[6];
            }
            _ => return fail(format!("path command {current:?}")),
        }
    }
    Ok(segs)
}

fn segments_bbox(segs: &[Seg]) -> (f64, f64, f64, f64) {
    let mut xs = Vec::new();
    let mut ys = Vec::new();
    let mut px = 0.0;
    let mut py = 0.0;
    for seg in segs {
        match *seg {
            Seg::M(x, y) | Seg::L(x, y) => {
                px = x;
                py = y;
                xs.push(px);
                ys.push(py);
            }
            Seg::C(c1x, c1y, c2x, c2y, ex, ey) => {
                let (x0, y0) = (px, py);
                for t in [0.25f64, 0.5, 0.75] {
                    let mt = 1.0 - t;
                    xs.push(
                        mt.powi(3) * x0
                            + 3.0 * mt * mt * t * c1x
                            + 3.0 * mt * t * t * c2x
                            + t.powi(3) * ex,
                    );
                    ys.push(
                        mt.powi(3) * y0
                            + 3.0 * mt * mt * t * c1y
                            + 3.0 * mt * t * t * c2y
                            + t.powi(3) * ey,
                    );
                }
                xs.push(ex);
                ys.push(ey);
                px = ex;
                py = ey;
            }
            Seg::Z => {}
        }
    }
    if xs.is_empty() {
        return (0.0, 0.0, 0.0, 0.0);
    }
    (
        xs.iter().copied().fold(f64::INFINITY, f64::min),
        ys.iter().copied().fold(f64::INFINITY, f64::min),
        xs.iter().copied().fold(f64::NEG_INFINITY, f64::max),
        ys.iter().copied().fold(f64::NEG_INFINITY, f64::max),
    )
}

fn rect_segments(x: f64, y: f64, w: f64, h: f64, rx: f64) -> Vec<Seg> {
    if rx <= 0.0 {
        return vec![
            Seg::M(x, y),
            Seg::L(x + w, y),
            Seg::L(x + w, y + h),
            Seg::L(x, y + h),
            Seg::Z,
        ];
    }
    let r = rx.min(w / 2.0).min(h / 2.0);
    let k = KAPPA * r;
    vec![
        Seg::M(x + r, y),
        Seg::L(x + w - r, y),
        Seg::C(x + w - r + k, y, x + w, y + r - k, x + w, y + r),
        Seg::L(x + w, y + h - r),
        Seg::C(x + w, y + h - r + k, x + w - r + k, y + h, x + w - r, y + h),
        Seg::L(x + r, y + h),
        Seg::C(x + r - k, y + h, x, y + h - r + k, x, y + h - r),
        Seg::L(x, y + r),
        Seg::C(x, y + r - k, x + r - k, y, x + r, y),
        Seg::Z,
    ]
}

fn circle_segments(cx: f64, cy: f64, r: f64) -> Vec<Seg> {
    let k = KAPPA * r;
    vec![
        Seg::M(cx + r, cy),
        Seg::C(cx + r, cy + k, cx + k, cy + r, cx, cy + r),
        Seg::C(cx - k, cy + r, cx - r, cy + k, cx - r, cy),
        Seg::C(cx - r, cy - k, cx - k, cy - r, cx, cy - r),
        Seg::C(cx + k, cy - r, cx + r, cy - k, cx + r, cy),
        Seg::Z,
    ]
}

fn parse_points(points: &str) -> PdfResult<Vec<(f64, f64)>> {
    let values = numbers(points);
    if values.len() % 2 == 1 {
        return fail(format!("points list {:?}", &points[..points.len().min(40)]));
    }
    Ok(values.chunks_exact(2).map(|c| (c[0], c[1])).collect())
}

fn decode_png(data: &[u8]) -> PdfResult<(u32, u32, Vec<u8>, Option<Vec<u8>>)> {
    if data.len() < 8 || &data[..8] != PNG_SIG {
        return fail("embedded image is not a PNG");
    }
    let mut decoder = png::Decoder::new(Cursor::new(data));
    decoder.set_transformations(png::Transformations::EXPAND);
    let mut reader = decoder
        .read_info()
        .map_err(|_| unsupported("embedded PNG missing IHDR"))?;
    let mut buf = vec![
        0u8;
        reader
            .output_buffer_size()
            .ok_or_else(|| unsupported("embedded PNG payload size"))?
    ];
    let info = reader
        .next_frame(&mut buf)
        .map_err(|_| unsupported("embedded PNG payload size"))?;
    let w = info.width;
    let h = info.height;
    let (rgb, alpha) = match info.color_type {
        png::ColorType::Rgba => {
            let mut rgb = Vec::with_capacity((w * h * 3) as usize);
            let mut alpha = Vec::with_capacity((w * h) as usize);
            for px in buf[..info.buffer_size()].chunks_exact(4) {
                rgb.extend_from_slice(&px[..3]);
                alpha.push(px[3]);
            }
            let alpha = if alpha.iter().all(|&a| a == 255) {
                None
            } else {
                Some(alpha)
            };
            (rgb, alpha)
        }
        png::ColorType::Rgb => (buf[..info.buffer_size()].to_vec(), None),
        png::ColorType::Indexed | png::ColorType::Grayscale | png::ColorType::GrayscaleAlpha => {
            return fail(format!(
                "embedded PNG color type {:?}/depth {:?}",
                info.color_type, info.bit_depth
            ));
        }
    };
    Ok((w, h, rgb, alpha))
}

fn decode_data_url_png(href: &str) -> PdfResult<(u32, u32, Vec<u8>, Option<Vec<u8>>)> {
    const PREFIX: &str = "data:image/png;base64,";
    let encoded = href
        .strip_prefix(PREFIX)
        .ok_or_else(|| unsupported("<image> href (only embedded base64 PNG)"))?;
    let bytes = decode_base64(encoded)?;
    decode_png(&bytes)
}

fn decode_base64(input: &str) -> PdfResult<Vec<u8>> {
    let cleaned: Vec<u8> = input.bytes().filter(|b| !b.is_ascii_whitespace()).collect();
    if cleaned.len() % 4 != 0 {
        return fail("embedded image is not a PNG");
    }
    let val = |b: u8| -> PdfResult<u8> {
        match b {
            b'A'..=b'Z' => Ok(b - b'A'),
            b'a'..=b'z' => Ok(b - b'a' + 26),
            b'0'..=b'9' => Ok(b - b'0' + 52),
            b'+' => Ok(62),
            b'/' => Ok(63),
            b'=' => Ok(0),
            _ => fail("embedded image is not a PNG"),
        }
    };
    let mut out = Vec::with_capacity(cleaned.len() / 4 * 3);
    for chunk in cleaned.chunks_exact(4) {
        let n = (u32::from(val(chunk[0])?) << 18)
            | (u32::from(val(chunk[1])?) << 12)
            | (u32::from(val(chunk[2])?) << 6)
            | u32::from(val(chunk[3])?);
        out.push(((n >> 16) & 0xFF) as u8);
        if chunk[2] != b'=' {
            out.push(((n >> 8) & 0xFF) as u8);
        }
        if chunk[3] != b'=' {
            out.push((n & 0xFF) as u8);
        }
    }
    Ok(out)
}

fn zlib_compress(payload: &[u8]) -> Vec<u8> {
    let mut encoder = ZlibEncoder::new(Vec::new(), Compression::new(6));
    encoder.write_all(payload).expect("zlib write");
    encoder.finish().expect("zlib finish")
}

struct Pdf {
    objects: HashMap<u32, Vec<u8>>,
    next: u32,
}

impl Pdf {
    fn new() -> Self {
        Self {
            objects: HashMap::new(),
            next: 5,
        }
    }

    fn reserve(&mut self) -> u32 {
        let num = self.next;
        self.next += 1;
        num
    }

    fn put(&mut self, num: u32, body: &str) {
        self.objects
            .insert(num, format!("{num} 0 obj\n{body}\nendobj\n").into_bytes());
    }

    fn put_stream(&mut self, num: u32, extra: &str, payload: &[u8]) {
        let data = zlib_compress(payload);
        let mut bytes = format!(
            "{num} 0 obj\n<< {extra}/Length {} /Filter /FlateDecode >>\nstream\n",
            data.len()
        )
        .into_bytes();
        bytes.extend_from_slice(&data);
        bytes.extend_from_slice(b"\nendstream\nendobj\n");
        self.objects.insert(num, bytes);
    }

    fn serialize(&self) -> Vec<u8> {
        let mut out = b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n".to_vec();
        let mut numbers: Vec<u32> = self.objects.keys().copied().collect();
        numbers.sort_unstable();
        let mut offsets = HashMap::new();
        for num in &numbers {
            offsets.insert(*num, out.len());
            out.extend_from_slice(&self.objects[num]);
        }
        let xref_pos = out.len();
        let size = numbers.last().copied().unwrap_or(0) + 1;
        out.extend_from_slice(format!("xref\n0 {size}\n").as_bytes());
        out.extend_from_slice(b"0000000000 65535 f \n");
        for num in 1..size {
            out.extend_from_slice(format!("{:010} 00000 n \n", offsets[&num]).as_bytes());
        }
        out.extend_from_slice(
            format!("trailer\n<< /Size {size} /Root 1 0 R >>\nstartxref\n{xref_pos}\n%%EOF\n")
                .as_bytes(),
        );
        out
    }
}

#[derive(Clone)]
struct State {
    fill: String,
    fill_opacity: f64,
    stroke_opacity: f64,
    opacity: f64,
    font_size: f64,
    font_weight: f64,
}

impl State {
    fn new() -> Self {
        Self {
            fill: "#000000".into(),
            fill_opacity: 1.0,
            stroke_opacity: 1.0,
            opacity: 1.0,
            font_size: DEFAULT_FONT_SIZE,
            font_weight: 400.0,
        }
    }
}

#[derive(Clone)]
enum Clip {
    Rect(f64, f64, f64, f64),
    Circle(f64, f64, f64),
    Path(Vec<Seg>, String),
}

#[derive(Clone)]
struct Gradient {
    units: String,
    x1: Option<String>,
    y1: Option<String>,
    x2: Option<String>,
    y2: Option<String>,
    stops: Vec<(f64, (f64, f64, f64), f64)>,
}

enum Paint {
    Solid(f64, f64, f64, f64),
    Gradient(String),
}

struct Converter {
    pdf: Pdf,
    ops: Vec<String>,
    clips: HashMap<String, Clip>,
    gradients: HashMap<String, Gradient>,
    fonts: Vec<(String, String, u32)>,
    gstates: Vec<(String, String, u32)>,
    gstate_keys: HashMap<String, usize>,
    shadings: Vec<(String, u32, bool, String)>,
    shading_keys: HashMap<String, usize>,
    smask_forms: HashMap<String, u32>,
    images: Vec<(String, u32)>,
    cache_stack: Vec<HashMap<String, String>>,
}

impl Converter {
    fn new() -> Self {
        Self {
            pdf: Pdf::new(),
            ops: Vec::new(),
            clips: HashMap::new(),
            gradients: HashMap::new(),
            fonts: Vec::new(),
            gstates: Vec::new(),
            gstate_keys: HashMap::new(),
            shadings: Vec::new(),
            shading_keys: HashMap::new(),
            smask_forms: HashMap::new(),
            images: Vec::new(),
            cache_stack: vec![HashMap::new()],
        }
    }

    fn cache(&mut self) -> &mut HashMap<String, String> {
        self.cache_stack.last_mut().unwrap()
    }

    fn append_circle_path(&mut self, cx: f64, cy: f64, radius: f64) {
        let k = KAPPA * radius;
        let (x0, x1) = (cx - radius, cx + radius);
        let (y0, y1) = (cy - radius, cy + radius);
        self.ops.push(format!("{} {} m", fmt_num(x1), fmt_num(cy)));
        self.ops.push(format!(
            "{} {} {} {} {} {} c",
            fmt_num(x1),
            fmt_num(cy + k),
            fmt_num(cx + k),
            fmt_num(y1),
            fmt_num(cx),
            fmt_num(y1)
        ));
        self.ops.push(format!(
            "{} {} {} {} {} {} c",
            fmt_num(cx - k),
            fmt_num(y1),
            fmt_num(x0),
            fmt_num(cy + k),
            fmt_num(x0),
            fmt_num(cy)
        ));
        self.ops.push(format!(
            "{} {} {} {} {} {} c",
            fmt_num(x0),
            fmt_num(cy - k),
            fmt_num(cx - k),
            fmt_num(y0),
            fmt_num(cx),
            fmt_num(y0)
        ));
        self.ops.push(format!(
            "{} {} {} {} {} {} c",
            fmt_num(cx + k),
            fmt_num(y0),
            fmt_num(x1),
            fmt_num(cy - k),
            fmt_num(x1),
            fmt_num(cy)
        ));
        self.ops.push("h".into());
    }

    fn push(&mut self) {
        self.ops.push("q".into());
        let top = self.cache_stack.last().cloned().unwrap_or_default();
        self.cache_stack.push(top);
    }

    fn pop(&mut self) {
        self.ops.push("Q".into());
        self.cache_stack.pop();
    }

    fn set(&mut self, key: &str, value: String, op: String) {
        if self.cache().get(key) != Some(&value) {
            self.ops.push(op);
            self.cache().insert(key.into(), value);
        }
    }

    fn set_gs(&mut self, ca: f64, ca_stroke: f64) {
        let name = self.gs_plain(ca, ca_stroke);
        self.set("gs", name.clone(), format!("/{name} gs"));
    }

    fn set_fill_rgb(&mut self, rgb: (f64, f64, f64)) {
        let key = format!(
            "{} {} {}",
            fmt_num((rgb.0 * 1e4).round() / 1e4),
            fmt_num((rgb.1 * 1e4).round() / 1e4),
            fmt_num((rgb.2 * 1e4).round() / 1e4)
        );
        self.set(
            "fill_rgb",
            key,
            format!(
                "{} {} {} rg",
                fmt_num(rgb.0),
                fmt_num(rgb.1),
                fmt_num(rgb.2)
            ),
        );
    }

    fn set_stroke_rgb(&mut self, rgb: (f64, f64, f64)) {
        let key = format!(
            "{} {} {}",
            fmt_num((rgb.0 * 1e4).round() / 1e4),
            fmt_num((rgb.1 * 1e4).round() / 1e4),
            fmt_num((rgb.2 * 1e4).round() / 1e4)
        );
        self.set(
            "stroke_rgb",
            key,
            format!(
                "{} {} {} RG",
                fmt_num(rgb.0),
                fmt_num(rgb.1),
                fmt_num(rgb.2)
            ),
        );
    }

    fn set_stroke_params(&mut self, width: f64, cap: i32, join: i32, dash: Option<&[f64]>) {
        self.set(
            "w",
            fmt_num((width * 1e4).round() / 1e4),
            format!("{} w", fmt_num(width)),
        );
        self.set("J", cap.to_string(), format!("{cap} J"));
        self.set("j", join.to_string(), format!("{join} j"));
        let dash_key = dash
            .map(|d| {
                d.iter()
                    .map(|v| fmt_num((*v * 1e4).round() / 1e4))
                    .collect::<Vec<_>>()
                    .join(" ")
            })
            .unwrap_or_default();
        let dash_op = if let Some(d) = dash {
            format!(
                "[{}] 0 d",
                d.iter().map(|v| fmt_num(*v)).collect::<Vec<_>>().join(" ")
            )
        } else {
            "[] 0 d".into()
        };
        self.set("d", dash_key, dash_op);
    }

    fn font(&mut self, bold: bool) -> String {
        let base = if bold { "Helvetica-Bold" } else { "Helvetica" };
        if let Some((_, name, _)) = self.fonts.iter().find(|(b, _, _)| b == base) {
            return name.clone();
        }
        let num = self.pdf.reserve();
        let name = format!("F{}", self.fonts.len() + 1);
        self.pdf.put(
            num,
            &format!(
                "<< /Type /Font /Subtype /Type1 /BaseFont /{base} /Encoding /WinAnsiEncoding >>"
            ),
        );
        self.fonts.push((base.into(), name.clone(), num));
        name
    }

    fn gs_plain(&mut self, ca: f64, ca_stroke: f64) -> String {
        let key = format!(
            "plain:{}:{}",
            fmt_num((ca * 1e4).round() / 1e4),
            fmt_num((ca_stroke * 1e4).round() / 1e4)
        );
        if let Some(&idx) = self.gstate_keys.get(&key) {
            return self.gstates[idx].1.clone();
        }
        let num = self.pdf.reserve();
        let name = format!("G{}", self.gstates.len() + 1);
        self.pdf.put(
            num,
            &format!(
                "<< /Type /ExtGState /ca {} /CA {} >>",
                fmt_num(ca),
                fmt_num(ca_stroke)
            ),
        );
        self.gstate_keys.insert(key, self.gstates.len());
        self.gstates.push((String::new(), name.clone(), num));
        name
    }

    fn function_dict(stops: &[(f64, Vec<f64>)]) -> String {
        let vals = |v: &[f64]| v.iter().map(|c| fmt_num(*c)).collect::<Vec<_>>().join(" ");
        if stops.len() == 2 {
            return format!(
                "<< /FunctionType 2 /Domain [0 1] /C0 [{}] /C1 [{}] /N 1 >>",
                vals(&stops[0].1),
                vals(&stops[1].1)
            );
        }
        let pieces: Vec<String> = stops
            .windows(2)
            .map(|pair| {
                format!(
                    "<< /FunctionType 2 /Domain [0 1] /C0 [{}] /C1 [{}] /N 1 >>",
                    vals(&pair[0].1),
                    vals(&pair[1].1)
                )
            })
            .collect();
        let bounds = stops[1..stops.len() - 1]
            .iter()
            .map(|(t, _)| fmt_num(*t))
            .collect::<Vec<_>>()
            .join(" ");
        let encode = vec!["0 1"; pieces.len()].join(" ");
        format!(
            "<< /FunctionType 3 /Domain [0 1] /Functions [{}] /Bounds [{bounds}] /Encode [{encode}] >>",
            pieces.join(" ")
        )
    }

    fn normalize_stops(stops: &[(f64, Vec<f64>)]) -> Vec<(f64, Vec<f64>)> {
        let mut out: Vec<(f64, Vec<f64>)> = Vec::new();
        let mut prev = -1.0;
        for (mut t, v) in stops.iter().cloned() {
            t = t.clamp(0.0, 1.0);
            if t <= prev {
                t = prev + 1e-4;
                if t > 1.0 {
                    continue;
                }
            }
            out.push((t, v));
            prev = t;
        }
        if out.is_empty() {
            out = vec![
                (0.0, stops[0].1.clone()),
                (1.0, stops.last().unwrap().1.clone()),
            ];
        }
        if out[0].0 > 0.0 {
            out.insert(0, (0.0, out[0].1.clone()));
        }
        if out.last().unwrap().0 < 1.0 {
            let last = out.last().unwrap().1.clone();
            out.push((1.0, last));
        }
        if out.len() == 1 {
            let last = out[0].1.clone();
            out.push((1.0, last));
        }
        out
    }

    fn shading(
        &mut self,
        coords: (f64, f64, f64, f64),
        stops: &[(f64, Vec<f64>)],
        gray: bool,
    ) -> (String, u32) {
        let stops = Self::normalize_stops(stops);
        let key = format!(
            "{}:{}:{}",
            gray,
            [coords.0, coords.1, coords.2, coords.3]
                .iter()
                .map(|c| fmt_num((*c * 1e4).round() / 1e4))
                .collect::<Vec<_>>()
                .join(","),
            stops
                .iter()
                .map(|(t, v)| format!(
                    "{}:{}",
                    fmt_num((*t * 1e6).round() / 1e6),
                    v.iter()
                        .map(|c| fmt_num((*c * 1e6).round() / 1e6))
                        .collect::<Vec<_>>()
                        .join(",")
                ))
                .collect::<Vec<_>>()
                .join("|")
        );
        if let Some(&idx) = self.shading_keys.get(&key) {
            return (self.shadings[idx].0.clone(), self.shadings[idx].1);
        }
        let num = self.pdf.reserve();
        let name = format!("Sh{}", self.shadings.len() + 1);
        let space = if gray { "/DeviceGray" } else { "/DeviceRGB" };
        let coords_s = format!(
            "{} {} {} {}",
            fmt_num(coords.0),
            fmt_num(coords.1),
            fmt_num(coords.2),
            fmt_num(coords.3)
        );
        self.pdf.put(
            num,
            &format!(
                "<< /ShadingType 2 /ColorSpace {space} /Coords [{coords_s}] /Extend [true true] /Function {} >>",
                Self::function_dict(&stops)
            ),
        );
        self.shading_keys.insert(key, self.shadings.len());
        self.shadings.push((name.clone(), num, gray, String::new()));
        (name, num)
    }

    fn gs_gradient(
        &mut self,
        coords: (f64, f64, f64, f64),
        alpha_stops: &[(f64, Vec<f64>)],
        bbox: (f64, f64, f64, f64),
        ca: f64,
    ) -> String {
        let (gray_name, gray_num) = self.shading(coords, alpha_stops, true);
        let form_key = format!(
            "{}:{}",
            gray_num,
            [bbox.0, bbox.1, bbox.2, bbox.3]
                .iter()
                .map(|v| fmt_num((*v * 1e4).round() / 1e4))
                .collect::<Vec<_>>()
                .join(",")
        );
        let form_num = if let Some(&num) = self.smask_forms.get(&form_key) {
            num
        } else {
            let form_num = self.pdf.reserve();
            let bbox_s = format!(
                "{} {} {} {}",
                fmt_num(bbox.0),
                fmt_num(bbox.1),
                fmt_num(bbox.2),
                fmt_num(bbox.3)
            );
            self.pdf.put_stream(
                form_num,
                &format!(
                    "/Type /XObject /Subtype /Form /BBox [{bbox_s}] /Group << /S /Transparency /CS /DeviceGray >> /Resources << /Shading << /{gray_name} {gray_num} 0 R >> >> "
                ),
                format!("/{gray_name} sh").as_bytes(),
            );
            self.smask_forms.insert(form_key, form_num);
            form_num
        };
        let key = format!("smask:{form_num}:{}", fmt_num((ca * 1e4).round() / 1e4));
        if let Some(&idx) = self.gstate_keys.get(&key) {
            return self.gstates[idx].1.clone();
        }
        let num = self.pdf.reserve();
        let name = format!("G{}", self.gstates.len() + 1);
        self.pdf.put(
            num,
            &format!(
                "<< /Type /ExtGState /ca {} /CA {} /SMask << /S /Luminosity /G {form_num} 0 R >> >>",
                fmt_num(ca),
                fmt_num(ca)
            ),
        );
        self.gstate_keys.insert(key, self.gstates.len());
        self.gstates.push((String::new(), name.clone(), num));
        name
    }

    fn image_xobject(&mut self, w: u32, h: u32, rgb: &[u8], alpha: Option<&[u8]>) -> String {
        let smask_ref = if let Some(alpha) = alpha {
            let smask_num = self.pdf.reserve();
            self.pdf.put_stream(
                smask_num,
                &format!(
                    "/Type /XObject /Subtype /Image /Width {w} /Height {h} /ColorSpace /DeviceGray /BitsPerComponent 8 /Interpolate false "
                ),
                alpha,
            );
            format!("/SMask {smask_num} 0 R ")
        } else {
            String::new()
        };
        let num = self.pdf.reserve();
        self.pdf.put_stream(
            num,
            &format!(
                "/Type /XObject /Subtype /Image /Width {w} /Height {h} /ColorSpace /DeviceRGB /BitsPerComponent 8 /Interpolate false {smask_ref}"
            ),
            rgb,
        );
        let name = format!("Im{}", self.images.len() + 1);
        self.images.push((name.clone(), num));
        name
    }

    fn collect_defs(&mut self, root: &Elem) -> PdfResult<()> {
        fn walk(this: &mut Converter, el: &Elem) -> PdfResult<()> {
            match el.name.as_str() {
                "clipPath" => {
                    check_attrs(el, "clipPath", allowed_attrs("clipPath"))?;
                    let cid = el.attr("id").ok_or_else(|| {
                        unsupported("<clipPath> without a single <rect>, <circle> or <path>")
                    })?;
                    if el.children.len() != 1 {
                        return fail("<clipPath> without a single <rect>, <circle> or <path>");
                    }
                    let shape = &el.children[0];
                    match shape.name.as_str() {
                        "path" => {
                            check_attrs(shape, "clipPath path", allowed_attrs("clip-path-shape"))?;
                            let d = shape
                                .attr("d")
                                .ok_or_else(|| unsupported("<clipPath> path without d"))?;
                            let rule = shape.attr("clip-rule").unwrap_or("nonzero");
                            if rule != "nonzero" && rule != "evenodd" {
                                return fail(format!("clip-rule {rule:?}"));
                            }
                            this.clips
                                .insert(cid.into(), Clip::Path(parse_path(d)?, rule.into()));
                        }
                        "circle" => {
                            check_attrs(shape, "clipPath circle", allowed_attrs("clip-circle"))?;
                            this.clips.insert(
                                cid.into(),
                                Clip::Circle(
                                    parse_float(shape.attr("cx"), 0.0, "clip cx")?,
                                    parse_float(shape.attr("cy"), 0.0, "clip cy")?,
                                    parse_float(shape.attr("r"), 0.0, "clip r")?,
                                ),
                            );
                        }
                        "rect" => {
                            check_attrs(shape, "clipPath rect", allowed_attrs("clip-rect"))?;
                            this.clips.insert(
                                cid.into(),
                                Clip::Rect(
                                    parse_float(shape.attr("x"), 0.0, "clip x")?,
                                    parse_float(shape.attr("y"), 0.0, "clip y")?,
                                    parse_float(shape.attr("width"), 0.0, "clip width")?,
                                    parse_float(shape.attr("height"), 0.0, "clip height")?,
                                ),
                            );
                        }
                        _ => return fail("<clipPath> without a single <rect>, <circle> or <path>"),
                    }
                }
                "linearGradient" => {
                    check_attrs(el, "linearGradient", allowed_attrs("linearGradient"))?;
                    let gid = el
                        .attr("id")
                        .ok_or_else(|| unsupported("<linearGradient> without id"))?;
                    let units = el.attr("gradientUnits").unwrap_or("objectBoundingBox");
                    if units != "objectBoundingBox" && units != "userSpaceOnUse" {
                        return fail(format!("gradientUnits {units:?}"));
                    }
                    let mut stops = Vec::new();
                    for stop in &el.children {
                        if stop.name != "stop" {
                            return fail(format!("<linearGradient> child <{}>", stop.name));
                        }
                        check_attrs(stop, "stop", allowed_attrs("stop"))?;
                        let offset = grad_fraction(stop.attr("offset"), 0.0)?;
                        let (r, g, b, a) = rgba_css(stop.attr("stop-color").unwrap_or("#000000"))?;
                        let alpha =
                            a * parse_float(stop.attr("stop-opacity"), 1.0, "stop-opacity")?;
                        stops.push((offset, (r, g, b), alpha));
                    }
                    if stops.is_empty() {
                        return fail("<linearGradient> without stops");
                    }
                    this.gradients.insert(
                        gid.into(),
                        Gradient {
                            units: units.into(),
                            x1: el.attr("x1").map(str::to_string),
                            y1: el.attr("y1").map(str::to_string),
                            x2: el.attr("x2").map(str::to_string),
                            y2: el.attr("y2").map(str::to_string),
                            stops,
                        },
                    );
                }
                _ => {}
            }
            for child in &el.children {
                walk(this, child)?;
            }
            Ok(())
        }
        walk(self, root)
    }

    fn emit_segments(&mut self, segs: &[Seg]) {
        for seg in segs {
            match *seg {
                Seg::M(x, y) => self.ops.push(format!("{} {} m", fmt_num(x), fmt_num(y))),
                Seg::L(x, y) => self.ops.push(format!("{} {} l", fmt_num(x), fmt_num(y))),
                Seg::C(a, b, c, d, e, f) => self.ops.push(format!(
                    "{} {} {} {} {} {} c",
                    fmt_num(a),
                    fmt_num(b),
                    fmt_num(c),
                    fmt_num(d),
                    fmt_num(e),
                    fmt_num(f)
                )),
                Seg::Z => self.ops.push("h".into()),
            }
        }
    }

    fn resolve_paint(&self, raw: Option<&str>) -> PdfResult<Option<Paint>> {
        let Some(raw) = raw else {
            return Ok(None);
        };
        if raw.trim() == "none" {
            return Ok(None);
        }
        if let Some(gid) = url_id(raw) {
            if !self.gradients.contains_key(gid) {
                return fail(format!("paint reference {raw:?}"));
            }
            return Ok(Some(Paint::Gradient(gid.into())));
        }
        let (r, g, b, a) = rgba_css(raw)?;
        Ok(Some(Paint::Solid(r, g, b, a)))
    }

    fn gradient_coords(
        &self,
        grad: &Gradient,
        bbox: (f64, f64, f64, f64),
    ) -> PdfResult<(f64, f64, f64, f64)> {
        if grad.units == "userSpaceOnUse" {
            return Ok((
                parse_float(grad.x1.as_deref(), 0.0, "gradient x1")?,
                parse_float(grad.y1.as_deref(), 0.0, "gradient y1")?,
                parse_float(grad.x2.as_deref(), 1.0, "gradient x2")?,
                parse_float(grad.y2.as_deref(), 0.0, "gradient y2")?,
            ));
        }
        let (x0, y0, x1, y1) = bbox;
        let fx1 = grad_fraction(grad.x1.as_deref(), 0.0)?;
        let fy1 = grad_fraction(grad.y1.as_deref(), 0.0)?;
        let fx2 = grad_fraction(grad.x2.as_deref(), 1.0)?;
        let fy2 = grad_fraction(grad.y2.as_deref(), 0.0)?;
        Ok((
            x0 + fx1 * (x1 - x0),
            y0 + fy1 * (y1 - y0),
            x0 + fx2 * (x1 - x0),
            y0 + fy2 * (y1 - y0),
        ))
    }

    fn paint_gradient_fill(&mut self, segs: &[Seg], gid: &str, ca: f64) -> PdfResult<()> {
        let grad = self
            .gradients
            .get(gid)
            .cloned()
            .ok_or_else(|| unsupported(format!("paint reference {gid:?}")))?;
        let bbox = segments_bbox(segs);
        let coords = self.gradient_coords(&grad, bbox)?;
        let color_stops: Vec<(f64, Vec<f64>)> = grad
            .stops
            .iter()
            .map(|(t, rgb, _)| (*t, vec![rgb.0, rgb.1, rgb.2]))
            .collect();
        let (name, _) = self.shading(coords, &color_stops, false);
        let has_alpha = grad.stops.iter().any(|(_, _, a)| *a < 1.0);
        self.push();
        self.emit_segments(segs);
        self.ops.push("W n".into());
        if has_alpha {
            let alpha_stops: Vec<(f64, Vec<f64>)> =
                grad.stops.iter().map(|(t, _, a)| (*t, vec![*a])).collect();
            let gs = self.gs_gradient(coords, &alpha_stops, bbox, ca);
            self.set("gs", gs.clone(), format!("/{gs} gs"));
        } else {
            self.set_gs(ca, ca);
        }
        self.ops.push(format!("/{name} sh"));
        self.pop();
        Ok(())
    }

    fn render_shape(&mut self, el: &Elem, tag: &str, state: &State) -> PdfResult<()> {
        let allowed = if tag == "path" || tag == "polyline" || tag == "polygon" {
            let mut keys = Vec::from(PAINT_ATTRS);
            if tag == "path" {
                keys.push("d");
            } else {
                keys.push("points");
            }
            keys
        } else {
            allowed_attrs(tag).to_vec()
        };
        check_attrs(el, tag, &allowed)?;
        let (segs, fillable) = match tag {
            "rect" => (
                rect_segments(
                    parse_float(el.attr("x"), 0.0, "x")?,
                    parse_float(el.attr("y"), 0.0, "y")?,
                    parse_float(el.attr("width"), 0.0, "width")?,
                    parse_float(el.attr("height"), 0.0, "height")?,
                    parse_float(el.attr("rx"), 0.0, "rx")?,
                ),
                true,
            ),
            "circle" => (
                circle_segments(
                    parse_float(el.attr("cx"), 0.0, "cx")?,
                    parse_float(el.attr("cy"), 0.0, "cy")?,
                    parse_float(el.attr("r"), 0.0, "r")?,
                ),
                true,
            ),
            "line" => (
                vec![
                    Seg::M(
                        parse_float(el.attr("x1"), 0.0, "x1")?,
                        parse_float(el.attr("y1"), 0.0, "y1")?,
                    ),
                    Seg::L(
                        parse_float(el.attr("x2"), 0.0, "x2")?,
                        parse_float(el.attr("y2"), 0.0, "y2")?,
                    ),
                ],
                false,
            ),
            "path" => {
                let d = el
                    .attr("d")
                    .ok_or_else(|| unsupported("<path> without d"))?;
                (parse_path(d)?, true)
            }
            _ => {
                let points = el
                    .attr("points")
                    .ok_or_else(|| unsupported(format!("<{tag}> without points")))?;
                let pts = parse_points(points)?;
                if pts.is_empty() {
                    return Ok(());
                }
                let mut segs = vec![Seg::M(pts[0].0, pts[0].1)];
                segs.extend(pts.iter().skip(1).map(|p| Seg::L(p.0, p.1)));
                if tag == "polygon" {
                    segs.push(Seg::Z);
                }
                (segs, true)
            }
        };
        let opacity = state.opacity * parse_float(el.attr("opacity"), 1.0, "opacity")?;
        let fill_op =
            opacity * parse_float(el.attr("fill-opacity"), state.fill_opacity, "fill-opacity")?;
        let stroke_op = opacity
            * parse_float(
                el.attr("stroke-opacity"),
                state.stroke_opacity,
                "stroke-opacity",
            )?;
        let mut fill = if fillable {
            self.resolve_paint(el.attr("fill").or(Some(state.fill.as_str())))?
        } else {
            None
        };
        let stroke = self.resolve_paint(el.attr("stroke"))?;
        let stroke_width = parse_float(el.attr("stroke-width"), 1.0, "stroke-width")?;
        if matches!(stroke, Some(Paint::Gradient(_))) {
            return fail("gradient stroke");
        }
        let do_stroke = stroke.is_some() && stroke_width > 0.0;
        let cap_name = el.attr("stroke-linecap").unwrap_or("butt");
        let join_name = el.attr("stroke-linejoin").unwrap_or("miter");
        let cap = match cap_name {
            "butt" => 0,
            "round" => 1,
            "square" => 2,
            _ => return fail(format!("stroke-linecap {cap_name:?}")),
        };
        let join = match join_name {
            "miter" => 0,
            "round" => 1,
            "bevel" => 2,
            _ => return fail(format!("stroke-linejoin {join_name:?}")),
        };
        let mut dash = el.attr("stroke-dasharray").map(numbers);
        if let Some(values) = &dash {
            if !values.iter().any(|v| *v > 0.0) {
                dash = None;
            }
        }
        if let Some(Paint::Gradient(gid)) = &fill {
            let gid = gid.clone();
            self.paint_gradient_fill(&segs, &gid, fill_op)?;
            fill = None;
        }
        if fill.is_none() && !do_stroke {
            return Ok(());
        }
        let mut ca = 1.0;
        if let Some(Paint::Solid(r, g, b, a)) = &fill {
            ca = fill_op * a;
            self.set_fill_rgb((*r, *g, *b));
        }
        let mut ca_stroke = 1.0;
        if do_stroke {
            if let Some(Paint::Solid(r, g, b, a)) = &stroke {
                ca_stroke = stroke_op * a;
                self.set_stroke_rgb((*r, *g, *b));
                self.set_stroke_params(stroke_width, cap, join, dash.as_deref());
            }
        }
        self.set_gs(ca, ca_stroke);
        self.emit_segments(&segs);
        self.ops.push(if fill.is_some() && do_stroke {
            "B".into()
        } else if fill.is_some() {
            "f".into()
        } else {
            "S".into()
        });
        Ok(())
    }

    fn render_text(&mut self, el: &Elem, state: &State) -> PdfResult<()> {
        check_attrs(el, "text", allowed_attrs("text"))?;
        let font_size = parse_float(el.attr("font-size"), state.font_size, "font-size")?;
        let bold = weight(el.attr("font-weight"), state.font_weight)? >= 600.0;
        let anchor = el.attr("text-anchor").unwrap_or("start");
        if !matches!(anchor, "start" | "middle" | "end") {
            return fail(format!("text-anchor {anchor:?}"));
        }
        let fill = self.resolve_paint(el.attr("fill").or(Some(state.fill.as_str())))?;
        let Some(Paint::Solid(red, green, blue, alpha)) = fill else {
            return fail("text fill paint");
        };
        let ca = state.opacity
            * parse_float(el.attr("fill-opacity"), state.fill_opacity, "fill-opacity")?
            * alpha;
        let mut angle = 0.0;
        let mut center = None;
        if let Some(transform) = el.attr("transform") {
            let parsed = parse_rotate(transform)
                .ok_or_else(|| unsupported(format!("transform {transform:?}")))?;
            angle = parsed.0;
            center = parsed.1;
        }
        let mut runs: Vec<(f64, f64, String)> = Vec::new();
        if !el.children.is_empty() {
            if !el.text.trim().is_empty() {
                return fail("<text> mixing direct text and <tspan>");
            }
            let inherited_x = parse_float(el.attr("x"), 0.0, "x")?;
            let mut inherited_y = parse_float(el.attr("y"), 0.0, "y")?;
            for ts in &el.children {
                if ts.name != "tspan" {
                    return fail(format!("<text> child <{}>", ts.name));
                }
                check_attrs(ts, "tspan", allowed_attrs("tspan"))?;
                if !ts.children.is_empty() {
                    return fail("nested <tspan>");
                }
                if ts.attr("y").is_some() && ts.attr("dy").is_some() {
                    return fail("<tspan> combining y and dy");
                }
                let x = parse_float(ts.attr("x"), inherited_x, "tspan x")?;
                if ts.attr("y").is_some() {
                    inherited_y = parse_float(ts.attr("y"), inherited_y, "tspan y")?;
                } else if ts.attr("dy").is_some() {
                    inherited_y += parse_float(ts.attr("dy"), 0.0, "tspan dy")?;
                }
                runs.push((x, inherited_y, ts.text.clone()));
            }
        } else {
            runs.push((
                parse_float(el.attr("x"), 0.0, "x")?,
                parse_float(el.attr("y"), 0.0, "y")?,
                el.text.clone(),
            ));
        }
        let font_name = self.font(bold);
        let theta = angle.to_radians();
        let (cos_t, sin_t) = (theta.cos(), theta.sin());
        for (mut x, mut y, s) in runs {
            let data = encode_cp1252(&s);
            if data.is_empty() {
                continue;
            }
            if let Some((cx, cy)) = center {
                let nx = cx + cos_t * (x - cx) - sin_t * (y - cy);
                let ny = cy + sin_t * (x - cx) + cos_t * (y - cy);
                x = nx;
                y = ny;
            }
            let width = text_width_px(&data, font_size, bold);
            let dx = if anchor == "middle" {
                -width / 2.0
            } else if anchor == "end" {
                -width
            } else {
                0.0
            };
            let tx = x + dx * cos_t;
            let ty = y + dx * sin_t;
            self.set_gs(ca, ca);
            self.set_fill_rgb((red, green, blue));
            self.ops.push("BT".into());
            self.ops
                .push(format!("/{font_name} {} Tf", fmt_num(font_size)));
            self.ops.push(format!(
                "{} {} {} {} {} {} Tm",
                fmt_num(cos_t),
                fmt_num(sin_t),
                fmt_num(sin_t),
                fmt_num(-cos_t),
                fmt_num(tx),
                fmt_num(ty)
            ));
            self.ops.push(format!("{} Tj", pdf_string(&data)));
            self.ops.push("ET".into());
        }
        Ok(())
    }

    fn render_image(&mut self, el: &Elem, state: &State) -> PdfResult<()> {
        check_attrs(el, "image", allowed_attrs("image"))?;
        if el.attr("preserveAspectRatio").unwrap_or("none") != "none" {
            return fail(format!(
                "preserveAspectRatio {:?}",
                el.attr("preserveAspectRatio").unwrap_or("")
            ));
        }
        let style = el.attr("style").unwrap_or("").trim().trim_end_matches(';');
        if style != "" && style != "image-rendering:pixelated" {
            return fail(format!("<image> style {style:?}"));
        }
        let href = el.attr("href").unwrap_or("");
        let (w_px, h_px, rgb, alpha) = decode_data_url_png(href)?;
        let name = self.image_xobject(w_px, h_px, &rgb, alpha.as_deref());
        let x = parse_float(el.attr("x"), 0.0, "x")?;
        let y = parse_float(el.attr("y"), 0.0, "y")?;
        let w = parse_float(el.attr("width"), 0.0, "width")?;
        let h = parse_float(el.attr("height"), 0.0, "height")?;
        self.push();
        if state.opacity < 1.0 {
            self.set_gs(state.opacity, state.opacity);
        }
        self.ops.push(format!(
            "{} 0 0 {} {} {} cm",
            fmt_num(w),
            fmt_num(-h),
            fmt_num(x),
            fmt_num(y + h)
        ));
        self.ops.push(format!("/{name} Do"));
        self.pop();
        Ok(())
    }

    fn render_g(&mut self, el: &Elem, state: &State) -> PdfResult<()> {
        check_attrs(el, "g", allowed_attrs("g"))?;
        let mut child = state.clone();
        if let Some(fill) = el.attr("fill") {
            child.fill = fill.into();
        }
        child.fill_opacity =
            parse_float(el.attr("fill-opacity"), state.fill_opacity, "fill-opacity")?;
        child.stroke_opacity = parse_float(
            el.attr("stroke-opacity"),
            state.stroke_opacity,
            "stroke-opacity",
        )?;
        child.opacity = state.opacity * parse_float(el.attr("opacity"), 1.0, "opacity")?;
        let mut clipped = false;
        if let Some(clip_ref) = el.attr("clip-path") {
            let gid =
                url_id(clip_ref).ok_or_else(|| unsupported(format!("clip-path {clip_ref:?}")))?;
            let clip = self
                .clips
                .get(gid)
                .cloned()
                .ok_or_else(|| unsupported(format!("clip-path {clip_ref:?}")))?;
            self.push();
            let mut clip_op = "W n";
            match clip {
                Clip::Circle(cx, cy, radius) => {
                    self.append_circle_path(cx, cy, radius);
                }
                Clip::Path(segs, rule) => {
                    let evenodd = rule == "evenodd";
                    self.emit_segments(&segs);
                    if evenodd {
                        clip_op = "W* n";
                    }
                }
                Clip::Rect(x, y, w, h) => {
                    self.ops.push(format!(
                        "{} {} {} {} re",
                        fmt_num(x),
                        fmt_num(y),
                        fmt_num(w),
                        fmt_num(h)
                    ));
                }
            }
            self.ops.push(clip_op.into());
            clipped = true;
        }
        self.render_children(el, &child)?;
        if clipped {
            self.pop();
        }
        Ok(())
    }

    fn render_nested_svg(&mut self, el: &Elem, state: &State) -> PdfResult<()> {
        check_attrs(el, "svg", allowed_attrs("svg-nested"))?;
        let x = parse_float(el.attr("x"), 0.0, "x")?;
        let y = parse_float(el.attr("y"), 0.0, "y")?;
        let w = parse_float(el.attr("width"), 0.0, "width")?;
        let h = parse_float(el.attr("height"), 0.0, "height")?;
        let vb = numbers(el.attr("viewBox").unwrap_or(""));
        if vb.len() != 4 || vb[0] != 0.0 || vb[1] != 0.0 || vb[2] <= 0.0 || vb[3] <= 0.0 {
            return fail(format!("viewBox {:?}", el.attr("viewBox").unwrap_or("")));
        }
        let (sx, sy) = (w / vb[2], h / vb[3]);
        self.push();
        self.ops.push(format!(
            "{} 0 0 {} {} {} cm",
            fmt_num(sx),
            fmt_num(sy),
            fmt_num(x),
            fmt_num(y)
        ));
        self.ops
            .push(format!("0 0 {} {} re", fmt_num(vb[2]), fmt_num(vb[3])));
        self.ops.push("W n".into());
        self.render_children(el, state)?;
        self.pop();
        Ok(())
    }

    fn render_children(&mut self, el: &Elem, state: &State) -> PdfResult<()> {
        for child in &el.children {
            self.render_element(child, state)?;
            if !child.tail.trim().is_empty() {
                return fail("stray text content");
            }
        }
        Ok(())
    }

    fn render_element(&mut self, el: &Elem, state: &State) -> PdfResult<()> {
        match el.name.as_str() {
            "defs" | "clipPath" | "linearGradient" => return Ok(()),
            "g" => self.render_g(el, state)?,
            "rect" | "circle" | "line" | "path" | "polyline" | "polygon" => {
                if !el.text.trim().is_empty() {
                    return fail("stray text content");
                }
                self.render_shape(el, &el.name, state)?;
            }
            "text" => self.render_text(el, state)?,
            "image" => self.render_image(el, state)?,
            "svg" => self.render_nested_svg(el, state)?,
            other => return fail(format!("<{other}>")),
        }
        if matches!(el.name.as_str(), "g" | "svg") && !el.text.trim().is_empty() {
            return fail("stray text content");
        }
        Ok(())
    }

    fn run(mut self, root: &Elem) -> PdfResult<Vec<u8>> {
        if root.name != "svg" {
            return fail(format!("root <{}>", root.name));
        }
        check_attrs(root, "svg", allowed_attrs("svg"))?;
        let width = parse_float(root.attr("width"), -1.0, "svg width")?;
        let height = parse_float(root.attr("height"), -1.0, "svg height")?;
        if width <= 0.0 || height <= 0.0 {
            return fail("svg without positive pixel width/height");
        }
        let vb = numbers(root.attr("viewBox").unwrap_or(""));
        if !vb.is_empty() && (vb.len() != 4 || vb != [0.0, 0.0, width, height]) {
            return fail(format!(
                "root viewBox {:?}",
                root.attr("viewBox").unwrap_or("")
            ));
        }
        self.collect_defs(root)?;
        let mut state = State::new();
        state.font_size = parse_float(root.attr("font-size"), DEFAULT_FONT_SIZE, "font-size")?;
        let page_w = width * PX_TO_PT;
        let page_h = height * PX_TO_PT;
        self.push();
        self.ops.push(format!(
            "{} 0 0 {} 0 {} cm",
            fmt_num(PX_TO_PT),
            fmt_num(-PX_TO_PT),
            fmt_num(page_h)
        ));
        if !root.text.trim().is_empty() {
            return fail("stray text content");
        }
        self.render_children(root, &state)?;
        self.pop();
        let content = self.ops.join("\n").into_bytes();
        self.pdf.put(1, "<< /Type /Catalog /Pages 2 0 R >>");
        self.pdf.put(2, "<< /Type /Pages /Kids [3 0 R] /Count 1 >>");
        let mut resources = Vec::new();
        if !self.fonts.is_empty() {
            let entries = self
                .fonts
                .iter()
                .map(|(_, name, num)| format!("/{name} {num} 0 R"))
                .collect::<Vec<_>>()
                .join(" ");
            resources.push(format!("/Font << {entries} >>"));
        }
        if !self.gstates.is_empty() {
            let entries = self
                .gstates
                .iter()
                .map(|(_, name, num)| format!("/{name} {num} 0 R"))
                .collect::<Vec<_>>()
                .join(" ");
            resources.push(format!("/ExtGState << {entries} >>"));
        }
        let color_shadings: Vec<_> = self
            .shadings
            .iter()
            .filter(|(_, _, gray, _)| !*gray)
            .map(|(name, num, _, _)| (name.clone(), *num))
            .collect();
        if !color_shadings.is_empty() {
            let entries = color_shadings
                .iter()
                .map(|(name, num)| format!("/{name} {num} 0 R"))
                .collect::<Vec<_>>()
                .join(" ");
            resources.push(format!("/Shading << {entries} >>"));
        }
        if !self.images.is_empty() {
            let entries = self
                .images
                .iter()
                .map(|(name, num)| format!("/{name} {num} 0 R"))
                .collect::<Vec<_>>()
                .join(" ");
            resources.push(format!("/XObject << {entries} >>"));
        }
        self.pdf.put(
            3,
            &format!(
                "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {} {}] /Resources << {} >> /Contents 4 0 R >>",
                fmt_num(page_w),
                fmt_num(page_h),
                resources.join(" ")
            ),
        );
        self.pdf.put_stream(4, "", &content);
        Ok(self.pdf.serialize())
    }
}

fn weight(value: Option<&str>, default: f64) -> PdfResult<f64> {
    match value {
        None => Ok(default),
        Some("bold") => Ok(700.0),
        Some("normal") => Ok(400.0),
        Some(raw) => parse_float(Some(raw), default, "font-weight"),
    }
}

fn grad_fraction(value: Option<&str>, default: f64) -> PdfResult<f64> {
    let Some(raw) = value else {
        return Ok(default);
    };
    let v = raw.trim();
    if let Some(stripped) = v.strip_suffix('%') {
        return Ok(parse_float(Some(stripped), default, "gradient coordinate")? / 100.0);
    }
    parse_float(Some(v), default, "gradient coordinate")
}

fn decode_entity(input: &str) -> PdfResult<(char, usize)> {
    if let Some(rest) = input.strip_prefix("amp;") {
        return Ok(('&', input.len() - rest.len()));
    }
    if let Some(rest) = input.strip_prefix("lt;") {
        return Ok(('<', input.len() - rest.len()));
    }
    if let Some(rest) = input.strip_prefix("gt;") {
        return Ok(('>', input.len() - rest.len()));
    }
    if let Some(rest) = input.strip_prefix("quot;") {
        return Ok(('"', input.len() - rest.len()));
    }
    if let Some(rest) = input.strip_prefix("apos;") {
        return Ok(('\'', input.len() - rest.len()));
    }
    if let Some(hex) = input
        .strip_prefix("#x")
        .or_else(|| input.strip_prefix("#X"))
    {
        if let Some(end) = hex.find(';') {
            let value =
                u32::from_str_radix(&hex[..end], 16).map_err(|_| unsupported("unparseable XML"))?;
            let ch = char::from_u32(value).ok_or_else(|| unsupported("unparseable XML"))?;
            return Ok((ch, 2 + end + 1));
        }
    } else if let Some(dec) = input.strip_prefix('#') {
        if let Some(end) = dec.find(';') {
            let value: u32 = dec[..end]
                .parse()
                .map_err(|_| unsupported("unparseable XML"))?;
            let ch = char::from_u32(value).ok_or_else(|| unsupported("unparseable XML"))?;
            return Ok((ch, 1 + end + 1));
        }
    }
    Err(unsupported("unparseable XML"))
}

fn unescape(raw: &str) -> PdfResult<String> {
    let mut out = String::new();
    let mut chars = raw.char_indices();
    while let Some((i, ch)) = chars.next() {
        if ch == '&' {
            let (decoded, eaten) = decode_entity(&raw[i + 1..])?;
            out.push(decoded);
            for _ in 0..eaten.saturating_sub(1) {
                chars.next();
            }
        } else {
            out.push(ch);
        }
    }
    Ok(out)
}

fn parse_xml(input: &str) -> PdfResult<Elem> {
    let mut parser = XmlParser {
        input,
        pos: 0,
        default_ns: String::new(),
    };
    parser.skip_prolog();
    parser.parse_element()
}

struct XmlParser<'a> {
    input: &'a str,
    pos: usize,
    default_ns: String,
}

impl<'a> XmlParser<'a> {
    fn rest(&self) -> &'a str {
        &self.input[self.pos..]
    }

    fn skip_ws(&mut self) {
        while let Some(c) = self.rest().chars().next() {
            if !c.is_whitespace() {
                break;
            }
            self.pos += c.len_utf8();
        }
    }

    fn skip_prolog(&mut self) {
        self.skip_ws();
        if self.rest().starts_with("<?xml") {
            if let Some(end) = self.rest().find("?>") {
                self.pos += end + 2;
            }
        }
        self.skip_ws();
        while self.rest().starts_with("<!--") {
            if let Some(end) = self.rest().find("-->") {
                self.pos += end + 3;
                self.skip_ws();
            } else {
                break;
            }
        }
    }

    fn parse_element(&mut self) -> PdfResult<Elem> {
        if !self.rest().starts_with('<') {
            return fail("unparseable XML");
        }
        self.pos += 1;
        if self.rest().starts_with('/') || self.rest().starts_with('!') {
            return fail("unparseable XML");
        }
        let name = self.parse_name()?;
        let mut attrs = Vec::new();
        loop {
            self.skip_ws();
            if self.rest().starts_with("/>") {
                self.pos += 2;
                let local = strip_ns(&name);
                return Ok(Elem {
                    name: local.into(),
                    attrs,
                    children: Vec::new(),
                    text: String::new(),
                    tail: String::new(),
                });
            }
            if self.rest().starts_with('>') {
                self.pos += 1;
                break;
            }
            let key = self.parse_name()?;
            self.skip_ws();
            if !self.rest().starts_with('=') {
                return fail("unparseable XML");
            }
            self.pos += 1;
            self.skip_ws();
            let value = self.parse_attr_value()?;
            if key == "xmlns" {
                self.default_ns = value.clone();
            } else if !key.starts_with("xmlns:") {
                attrs.push((strip_ns(&key).into(), value));
            }
        }
        let local = strip_ns(&name);
        let mut children = Vec::new();
        let mut text = String::new();
        let mut first_text = true;
        loop {
            if self.rest().starts_with("</") {
                self.pos += 2;
                let close = self.parse_name()?;
                self.skip_ws();
                if !self.rest().starts_with('>') || strip_ns(&close) != local {
                    return fail("unparseable XML");
                }
                self.pos += 1;
                break;
            }
            if self.rest().starts_with('<') {
                if self.rest().starts_with("<!--") {
                    if let Some(end) = self.rest().find("-->") {
                        self.pos += end + 3;
                        continue;
                    }
                    return fail("non-element XML node");
                }
                let mut child = self.parse_element()?;
                let tail = self.read_text_until_tag()?;
                child.tail = tail;
                children.push(child);
                first_text = false;
            } else {
                let chunk = self.read_text_until_tag()?;
                if first_text {
                    text = chunk;
                    first_text = false;
                }
            }
            if self.pos >= self.input.len() {
                return fail("unparseable XML");
            }
        }
        Ok(Elem {
            name: local.into(),
            attrs,
            children,
            text,
            tail: String::new(),
        })
    }

    fn parse_name(&mut self) -> PdfResult<String> {
        let rest = self.rest();
        let len = rest
            .chars()
            .take_while(|c| c.is_ascii_alphanumeric() || matches!(*c, ':' | '_' | '-' | '.'))
            .map(char::len_utf8)
            .sum();
        if len == 0 {
            return fail("unparseable XML");
        }
        let name = rest[..len].to_string();
        self.pos += len;
        Ok(name)
    }

    fn parse_attr_value(&mut self) -> PdfResult<String> {
        let quote = self
            .rest()
            .chars()
            .next()
            .ok_or_else(|| unsupported("unparseable XML"))?;
        if quote != '"' && quote != '\'' {
            return fail("unparseable XML");
        }
        self.pos += 1;
        let rest = self.rest();
        let end = rest
            .find(quote)
            .ok_or_else(|| unsupported("unparseable XML"))?;
        let raw = &rest[..end];
        self.pos += end + 1;
        unescape(raw)
    }

    fn read_text_until_tag(&mut self) -> PdfResult<String> {
        let rest = self.rest();
        let end = rest.find('<').unwrap_or(rest.len());
        let raw = &rest[..end];
        self.pos += end;
        unescape(raw)
    }
}

fn strip_ns(name: &str) -> &str {
    name.rsplit_once(':')
        .map(|(_, local)| local)
        .unwrap_or(name)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn fmt_num_matches_python_trim() {
        assert_eq!(fmt_num(0.75), "0.75");
        assert_eq!(fmt_num(1.0), "1");
        assert_eq!(fmt_num(-0.0), "0");
        assert_eq!(fmt_num(675.0), "675");
    }

    #[test]
    fn empty_svg_is_a_valid_page() {
        let pdf =
            svg_to_pdf(r#"<svg xmlns="http://www.w3.org/2000/svg" width="100" height="50"></svg>"#)
                .unwrap();
        assert!(pdf.starts_with(b"%PDF-1.4"));
        assert!(pdf
            .windows(b"/MediaBox [0 0 75 37.5]".len())
            .any(|w| w == b"/MediaBox [0 0 75 37.5]"));
    }

    #[test]
    fn unknown_element_fails_closed() {
        let err = svg_to_pdf(
            r#"<svg xmlns="http://www.w3.org/2000/svg" width="100" height="50"><foreignObject/></svg>"#,
        )
        .unwrap_err();
        assert!(err.contains("unsupported SVG feature"));
    }

    #[test]
    fn tspan_dy_offsets_survive() {
        let pdf = svg_to_pdf(
            r#"<svg xmlns="http://www.w3.org/2000/svg" width="100" height="50"><text x="2" y="12"><tspan x="2">first</tspan><tspan x="2" dy="14.4">second</tspan></text></svg>"#,
        )
        .unwrap();
        let decompressed = {
            use flate2::read::ZlibDecoder;
            use std::io::Read;
            let start = pdf.windows(7).position(|w| w == b"stream\n").unwrap() + 7;
            let end = pdf.windows(9).position(|w| w == b"endstream").unwrap();
            let payload = if pdf[end - 1] == b'\n' {
                &pdf[start..end - 1]
            } else {
                &pdf[start..end]
            };
            let mut decoder = ZlibDecoder::new(payload);
            let mut out = Vec::new();
            decoder.read_to_end(&mut out).unwrap();
            String::from_utf8(out).unwrap()
        };
        assert!(decompressed.contains("(first) Tj"));
        assert!(decompressed.contains("(second) Tj"));
        assert!(decompressed.contains("2 12 Tm"));
        assert!(decompressed.contains("2 26.4 Tm"));
    }
}
