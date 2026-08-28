//! Compact Figure→Scene per-trace compile packing (M2 #271).
//!
//! Hosts pack authored kind/style literals as XYTC v1. Rust owns opacity
//! applicability, symbol codes, constant-color vs channel vs density fallback,
//! dash presets, linecap, marker-path admission, diameter, legend kind, step,
//! curve-smooth and stroke-perimeter bits, hex pitch, fill-gradient admission,
//! and XYMS mark-style resolve so Python and Node cannot drift. ABI 166 packs
//! cartesian bar/column/histogram `corner_radius` into the XYTO reserved
//! trailer so encode can tessellate rounded Rects. ABI 167 packs polar
//! `wedge_gap` into that same trailer. ABI 168 tessellates polar
//! bar/column/histogram `corner_radius` from those same packed radii.
//! ABI 173 packs heatmap `corner_radius` into that same trailer so cartesian
//! heatmap Rects tessellate through `rounded_rect_poly` and polar heatmap
//! wedges reuse `polar_wedge_points`. ABI 174 packs violin/box
//! `corner_radius` on that same Rect tessellation. Per-item radius channels
//! stay fail-closed.
//! ABI 170 admits constant scatter `marker_glyph` as UTF-8 in the existing
//! XYTR marker blob (`FLAG_HAS_GLYPH`); encoded Scene keeps XYMG so SVG/raster
//! emit `<text>` / `OP_TEXT` instead of a disc.
//! Encoded Scene v31 is unchanged.

use crate::css::{self, Checked};
use crate::scene_style::{self, MarkStyleError, ResolvedMarkStyle};

pub const XYTC_MAGIC: &[u8; 4] = b"XYTC";
pub const XYTC_VERSION: u32 = 1;
pub const XYTC_HEADER_BYTES: usize = 16;
pub const XYTR_MAGIC: &[u8; 4] = b"XYTR";
pub const XYTR_VERSION: u16 = 1;
pub const XYTR_PREFIX_BYTES: usize = 160;
pub const XYTO_MAGIC: &[u8; 4] = b"XYTO";
pub const XYTO_VERSION: u32 = 1;
pub const XYTO_HEADER_BYTES: usize = 16;
pub const XYTO_PREFIX_BYTES: usize = 160;

pub const FLAG_HAS_FILL: u32 = 1 << 0;
pub const FLAG_HAS_STROKE: u32 = 1 << 1;
pub const FLAG_HAS_LINE_COLOR: u32 = 1 << 2;
pub const FLAG_HAS_STROKE_WIDTH: u32 = 1 << 3;
pub const FLAG_HAS_WIDTH: u32 = 1 << 4;
pub const FLAG_HAS_LINE_WIDTH: u32 = 1 << 5;
pub const FLAG_HAS_SIZE: u32 = 1 << 6;
pub const FLAG_HAS_SIZE_CH: u32 = 1 << 7;
pub const FLAG_HAS_HEX: u32 = 1 << 8;
pub const FLAG_PERIMETER_TRUE: u32 = 1 << 9;
pub const FLAG_PERIMETER_INVALID: u32 = 1 << 10;
pub const FLAG_COLOR_CH: u32 = 1 << 11;
pub const FLAG_COLOR_CH_CONSTANT: u32 = 1 << 12;
pub const FLAG_COLOR2: u32 = 1 << 13;
pub const FLAG_USE_DENSITY: u32 = 1 << 14;
pub const FLAG_SHOW_LEGEND: u32 = 1 << 15;
pub const FLAG_HAS_NAME: u32 = 1 << 16;
pub const FLAG_HAS_DASH_PATTERN: u32 = 1 << 17;
pub const FLAG_HAS_MARKER: u32 = 1 << 18;
pub const FLAG_HAS_GRADIENT_SPEC: u32 = 1 << 19;
pub const FLAG_HAS_FILL_DICT: u32 = 1 << 20;
pub const FLAG_SYMBOL_INT: u32 = 1 << 21;
pub const FLAG_HAS_CORNER_RADIUS: u32 = 1 << 22;
pub const FLAG_HAS_WEDGE_GAP: u32 = 1 << 23;
pub const FLAG_HAS_GLYPH: u32 = 1 << 24;

pub const FACT_STROKE_PERIMETER: u32 = 1;
pub const FACT_CURVE_SMOOTH: u32 = 2;

const MAX_TRACES: usize = 4_096;
const MAX_TEXT: usize = 4_096;
const MAX_PATTERN: usize = 8;
const PLUS_LINE_CODE: u16 = 15;
const DEFAULT_COLOR: &str = "#3987e5";
const DEFAULT_DIAMETER: f64 = 4.0;
const MS_LINE_ONLY: u8 = 1 << 0;
const MS_HAS_FILL: u8 = 1 << 1;
const MS_HAS_STROKE: u8 = 1 << 2;
const MS_HAS_LINE_COLOR: u8 = 1 << 3;
const MS_HAS_STROKE_WIDTH: u8 = 1 << 5;
const MS_HAS_WIDTH: u8 = 1 << 6;
const MS_HAS_LINE_WIDTH: u8 = 1 << 7;
const LINECAP_NONE: u8 = 255;

const SYMBOL_NAMES: [&str; 19] = [
    "circle",
    "square",
    "diamond",
    "triangle",
    "cross",
    "hexagon",
    "pentagon",
    "star",
    "triangle_down",
    "triangle_left",
    "triangle_right",
    "x",
    "point",
    "pixel",
    "thin_diamond",
    "plus_line",
    "x_line",
    "horizontal_line",
    "vertical_line",
];

/// Why an XYTC compile request was rejected. Discriminants are the C-ABI
/// error codes (returned negated by `xyg_scene_pack_trace_compile`).
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum TraceCompileCode {
    Length = 1,
    Version = 2,
    Limit = 3,
    Output = 4,
    Opacity = 5,
    Symbol = 6,
    Step = 7,
    Perimeter = 8,
    Hex = 9,
    Color = 10,
    Fill = 11,
    OpacityChannel = 12,
    DataDriven = 13,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct TraceCompileError {
    pub code: TraceCompileCode,
    pub index: u32,
}

impl TraceCompileError {
    fn new(code: TraceCompileCode, index: usize) -> Self {
        Self {
            code,
            index: index as u32,
        }
    }
}

struct Input<'a> {
    kind: &'a str,
    flags: u32,
    name: &'a str,
    symbol: &'a str,
    symbol_int: u16,
    opacity: f64,
    fill_opacity: f64,
    stroke_opacity: f64,
    line_opacity: f64,
    size: f64,
    size_ch: f64,
    stroke_width: f64,
    width: f64,
    line_width: f64,
    hex_dx: f64,
    hex_dy: f64,
    dash: &'a str,
    linecap: &'a str,
    step: &'a str,
    curve: &'a str,
    fill_css: &'a str,
    stroke_css: &'a str,
    line_color: &'a str,
    color_css: &'a str,
    color_mode: &'a str,
    color_const: &'a str,
    fill_space: &'a str,
    dash_pattern: Vec<f64>,
    marker_blob: &'a [u8],
    gradient_blob: &'a [u8],
    r_tip: f64,
    r_base: f64,
    wedge_gap: f64,
}

struct Compiled {
    fill: [u8; 4],
    stroke: [u8; 4],
    stroke_width: f64,
    diameter: f64,
    symbol: u16,
    legend_kind: u8,
    legend_include: u8,
    legend_symbol: u16,
    authored_step: u16,
    fact_bits: u32,
    dash: Option<Vec<f64>>,
    linecap: Option<u8>,
    marker: Option<Vec<u8>>,
    gradient: Option<Vec<u8>>,
    hex_dx: f64,
    hex_dy: f64,
    r_tip: f64,
    r_base: f64,
    tip_policy: u8,
    wedge_gap: f64,
}

fn read_u16(bytes: &[u8], offset: usize) -> Result<u16, TraceCompileError> {
    Ok(u16::from_le_bytes(
        bytes
            .get(offset..offset + 2)
            .ok_or(TraceCompileError::new(TraceCompileCode::Length, 0))?
            .try_into()
            .map_err(|_| TraceCompileError::new(TraceCompileCode::Length, 0))?,
    ))
}

fn read_u32(bytes: &[u8], offset: usize) -> Result<u32, TraceCompileError> {
    Ok(u32::from_le_bytes(
        bytes
            .get(offset..offset + 4)
            .ok_or(TraceCompileError::new(TraceCompileCode::Length, 0))?
            .try_into()
            .map_err(|_| TraceCompileError::new(TraceCompileCode::Length, 0))?,
    ))
}

fn read_f64(bytes: &[u8], offset: usize) -> Result<f64, TraceCompileError> {
    Ok(f64::from_le_bytes(
        bytes
            .get(offset..offset + 8)
            .ok_or(TraceCompileError::new(TraceCompileCode::Length, 0))?
            .try_into()
            .map_err(|_| TraceCompileError::new(TraceCompileCode::Length, 0))?,
    ))
}

fn read_f32(bytes: &[u8], offset: usize) -> Result<f32, TraceCompileError> {
    Ok(f32::from_le_bytes(
        bytes
            .get(offset..offset + 4)
            .ok_or(TraceCompileError::new(TraceCompileCode::Length, 0))?
            .try_into()
            .map_err(|_| TraceCompileError::new(TraceCompileCode::Length, 0))?,
    ))
}

fn take<'a>(
    bytes: &'a [u8],
    at: &mut usize,
    len: usize,
    index: usize,
) -> Result<&'a [u8], TraceCompileError> {
    let start = *at;
    let end = start
        .checked_add(len)
        .ok_or(TraceCompileError::new(TraceCompileCode::Limit, index))?;
    let slice = bytes
        .get(start..end)
        .ok_or(TraceCompileError::new(TraceCompileCode::Length, index))?;
    *at = end;
    Ok(slice)
}

fn utf8<'a>(bytes: &'a [u8], index: usize) -> Result<&'a str, TraceCompileError> {
    std::str::from_utf8(bytes).map_err(|_| TraceCompileError::new(TraceCompileCode::Length, index))
}

fn take_text<'a>(
    bytes: &'a [u8],
    at: &mut usize,
    len: usize,
    index: usize,
) -> Result<&'a str, TraceCompileError> {
    if len > MAX_TEXT {
        return Err(TraceCompileError::new(TraceCompileCode::Limit, index));
    }
    utf8(take(bytes, at, len, index)?, index)
}

fn is_band(kind: &str) -> bool {
    matches!(kind, "area" | "error_band")
}

fn is_ribbon(kind: &str) -> bool {
    kind == "ribbon"
}

fn is_stroke(kind: &str) -> bool {
    matches!(
        kind,
        "line" | "segments" | "errorbar" | "stem" | "contour" | "box_whisker" | "box_median"
    )
}

fn kind_code(kind: &str) -> u8 {
    match kind {
        "scatter" => 0,
        "line" => 1,
        "bar" => 2,
        "column" => 3,
        "histogram" => 4,
        "violin" => 5,
        "box" => 6,
        "box_whisker" => 7,
        "box_median" => 8,
        "segments" => 9,
        "errorbar" => 10,
        "stem" => 11,
        "area" => 12,
        "error_band" => 13,
        "ribbon" => 14,
        "triangle_mesh" => 15,
        "hexbin" => 16,
        "heatmap" => 17,
        "contour" => 18,
        _ => 255,
    }
}

fn symbol_code(
    name: &str,
    symbol_int: u16,
    flags: u32,
    index: usize,
) -> Result<u16, TraceCompileError> {
    if !name.is_empty() {
        for (code, candidate) in SYMBOL_NAMES.iter().enumerate() {
            if name == *candidate {
                return Ok(code as u16);
            }
        }
        return Err(TraceCompileError::new(TraceCompileCode::Symbol, index));
    }
    if flags & FLAG_SYMBOL_INT != 0 {
        if (symbol_int as usize) < SYMBOL_NAMES.len() {
            return Ok(symbol_int);
        }
        return Err(TraceCompileError::new(TraceCompileCode::Symbol, index));
    }
    Ok(0)
}

fn in_unit_interval(value: f64) -> bool {
    value.is_finite() && (0.0..=1.0).contains(&value)
}

fn parse_dash(text: &str, pattern: &[f64], flags: u32) -> Option<Vec<f64>> {
    if flags & FLAG_HAS_DASH_PATTERN != 0 {
        return admit_dash_lengths(pattern);
    }
    if text.is_empty() {
        return None;
    }
    let lowered = text.trim().to_ascii_lowercase();
    match lowered.as_str() {
        "solid" => None,
        "dashed" => Some(vec![6.0, 4.0]),
        "dotted" => Some(vec![1.5, 3.0]),
        "dashdot" => Some(vec![6.0, 3.0, 1.5, 3.0]),
        _ => {
            let lengths: Vec<f64> = text
                .split(',')
                .map(str::trim)
                .filter(|part| !part.is_empty())
                .filter_map(|part| part.parse().ok())
                .collect();
            if lengths.iter().any(|value| !value.is_finite()) {
                return None;
            }
            admit_dash_lengths(&lengths)
        }
    }
}

fn admit_dash_lengths(lengths: &[f64]) -> Option<Vec<f64>> {
    if !(2..=MAX_PATTERN).contains(&lengths.len()) {
        return None;
    }
    if lengths
        .iter()
        .any(|value| !value.is_finite() || *value <= 0.0)
    {
        return None;
    }
    Some(lengths.to_vec())
}

fn parse_linecap(text: &str) -> Option<u8> {
    if text.is_empty() {
        return None;
    }
    match text.trim().to_ascii_lowercase().as_str() {
        "butt" => Some(0),
        "square" => Some(2),
        "round" => None,
        _ => None,
    }
}

fn parse_step(kind: &str, text: &str, index: usize) -> Result<u16, TraceCompileError> {
    if kind != "line" || text.is_empty() {
        return Ok(0);
    }
    Ok(match text.trim() {
        "pre" => 1,
        "mid" => 2,
        "post" => 3,
        _ => return Err(TraceCompileError::new(TraceCompileCode::Step, index)),
    })
}

fn curve_smooth(kind: &str, text: &str) -> bool {
    (kind == "line" || is_band(kind))
        && !text.is_empty()
        && text.trim().eq_ignore_ascii_case("smooth")
}

fn hex_pitch(kind: &str, dx: f64, dy: f64, index: usize) -> Result<(f64, f64), TraceCompileError> {
    if kind != "hexbin" {
        return Ok((0.0, 0.0));
    }
    if dx.is_finite() && dy.is_finite() && dx > 0.0 && dy > 0.0 {
        return Ok((dx, dy));
    }
    Err(TraceCompileError::new(TraceCompileCode::Hex, index))
}

fn constant_color<'a>(input: &'a Input<'a>, index: usize) -> Result<&'a str, TraceCompileError> {
    if input.flags & FLAG_COLOR2 != 0 {
        return Err(TraceCompileError::new(TraceCompileCode::Color, index));
    }
    if input.flags & FLAG_COLOR_CH == 0 {
        return Ok(if input.color_css.is_empty() {
            DEFAULT_COLOR
        } else {
            input.color_css
        });
    }
    if input.flags & FLAG_COLOR_CH_CONSTANT != 0 && !input.color_const.is_empty() {
        return Ok(input.color_const);
    }
    if input.color_mode == "constant" && !input.color_const.is_empty() {
        return Ok(input.color_const);
    }
    if input.kind == "scatter" && input.flags & FLAG_USE_DENSITY != 0 {
        return Ok(if input.color_css.is_empty() {
            DEFAULT_COLOR
        } else {
            input.color_css
        });
    }
    Err(TraceCompileError::new(TraceCompileCode::DataDriven, index))
}

fn fill_is_gradient_authoring(input: &Input<'_>) -> bool {
    if input.flags & (FLAG_HAS_GRADIENT_SPEC | FLAG_HAS_FILL_DICT) != 0 {
        return true;
    }
    input
        .fill_css
        .trim()
        .to_ascii_lowercase()
        .starts_with("linear-gradient(")
}

fn split_top_level(text: &str) -> Vec<&str> {
    let mut parts = Vec::new();
    let mut start = 0usize;
    let mut depth = 0i32;
    for (index, ch) in text.char_indices() {
        match ch {
            '(' => depth += 1,
            ')' => depth = (depth - 1).max(0),
            ',' if depth == 0 => {
                let part = text[start..index].trim();
                if !part.is_empty() {
                    parts.push(part);
                }
                start = index + ch.len_utf8();
            }
            _ => {}
        }
    }
    let part = text[start..].trim();
    if !part.is_empty() {
        parts.push(part);
    }
    parts
}

fn gradient_dir(name: &str) -> Option<u8> {
    match name {
        "down" | "to bottom" => Some(0),
        "up" | "to top" => Some(1),
        "right" | "to right" => Some(2),
        "left" | "to left" => Some(3),
        _ => None,
    }
}

fn parse_gradient_stop(item: &str) -> Option<(Option<f64>, &str)> {
    let item = item.trim();
    if let Some((color, pos)) = item.rsplit_once(char::is_whitespace) {
        if pos.ends_with('%') {
            let value: f64 = pos[..pos.len() - 1].parse().ok()?;
            if !value.is_finite() {
                return None;
            }
            return Some((Some(value / 100.0).map(|t| t.clamp(0.0, 1.0)), color.trim()));
        }
    }
    Some((None, item))
}

fn resolve_stop_positions(positions: &[Option<f64>]) -> Option<Vec<f64>> {
    let count = positions.len();
    if count == 0 {
        return None;
    }
    let mut anchors: Vec<(usize, f64)> = positions
        .iter()
        .enumerate()
        .filter_map(|(index, value)| value.map(|t| (index, t)))
        .collect();
    if !positions[0].is_some() {
        anchors.push((0, 0.0));
    }
    if !positions[count - 1].is_some() {
        anchors.push((count - 1, 1.0));
    }
    anchors.sort_by_key(|(index, _)| *index);
    let mut prev = 0.0;
    for anchor in &mut anchors {
        prev = anchor.1.max(prev);
        anchor.1 = prev;
    }
    let mut resolved = vec![0.0; count];
    for pair in anchors.windows(2) {
        let (i0, v0) = pair[0];
        let (i1, v1) = pair[1];
        let span = (i1 - i0) as f64;
        for k in i0..i1 {
            resolved[k] = if span == 0.0 {
                v0
            } else {
                v0 + (v1 - v0) * (k - i0) as f64 / span
            };
        }
    }
    if let Some((_, last)) = anchors.last() {
        resolved[count - 1] = *last;
    }
    Some(resolved)
}

fn admit_stop_color(css: &str, mark_color: &str) -> Option<[u8; 4]> {
    let lowered = css.trim();
    let resolved = if lowered.is_empty() || lowered.eq_ignore_ascii_case("currentcolor") {
        mark_color
    } else {
        lowered
    };
    if resolved.to_ascii_lowercase().contains("var(") {
        return None;
    }
    match css::parse_color(resolved) {
        Ok(Checked::Parsed(Some(_))) | Ok(Checked::Passthrough) => {
            Some(css::color_rgba8(resolved, 1.0))
        }
        _ => None,
    }
}

fn parse_linear_gradient(css: &str, space: &str) -> Option<(u8, u8, Vec<(f64, String)>)> {
    let text = css.trim();
    let lowered = text.to_ascii_lowercase();
    if !lowered.starts_with("linear-gradient(") || !text.ends_with(')') {
        return None;
    }
    let inner = &text["linear-gradient(".len()..text.len() - 1];
    let mut args = split_top_level(inner);
    if args.is_empty() {
        return None;
    }
    let mut dir_name = "down";
    let first = args[0].trim().to_ascii_lowercase();
    if let Some(name) = match first.as_str() {
        "to top" => Some("up"),
        "to bottom" => Some("down"),
        "to left" => Some("left"),
        "to right" => Some("right"),
        _ => None,
    } {
        dir_name = name;
        args.remove(0);
    } else if first.starts_with("to ") || first.ends_with("deg") {
        return None;
    }
    if (dir_name == "left" || dir_name == "right") && space == "mark" {
        return None;
    }
    if !(2..=8).contains(&args.len()) {
        return None;
    }
    let mut positions = Vec::new();
    let mut colors = Vec::new();
    for item in args {
        let (pos, color) = parse_gradient_stop(item)?;
        if color.is_empty() {
            return None;
        }
        positions.push(pos);
        colors.push(color.to_string());
    }
    let resolved = resolve_stop_positions(&positions)?;
    let dir = gradient_dir(dir_name)?;
    let space_code = match space {
        "plot" => 1,
        "mark" => 0,
        _ => return None,
    };
    Some((
        space_code,
        dir,
        resolved
            .into_iter()
            .zip(colors)
            .map(|(t, color)| (t, color))
            .collect(),
    ))
}

fn parse_gradient_blob(
    blob: &[u8],
    index: usize,
) -> Result<Option<(u8, u8, Vec<(f64, String)>)>, TraceCompileError> {
    if blob.is_empty() {
        return Ok(None);
    }
    if blob.len() < 4 {
        return Err(TraceCompileError::new(TraceCompileCode::Fill, index));
    }
    let space = blob[0];
    let dir = blob[1];
    let n_stops = blob[2] as usize;
    if space > 1 || dir > 3 || !(2..=8).contains(&n_stops) {
        return Ok(None);
    }
    let mut at = 4usize;
    let mut stops = Vec::with_capacity(n_stops);
    for _ in 0..n_stops {
        if at + 10 > blob.len() {
            return Ok(None);
        }
        let t = f64::from_le_bytes(blob[at..at + 8].try_into().unwrap());
        at += 8;
        let css_len = u16::from_le_bytes(blob[at..at + 2].try_into().unwrap()) as usize;
        at += 2;
        if at + css_len > blob.len() {
            return Ok(None);
        }
        let css = utf8(&blob[at..at + css_len], index)?.to_string();
        at += css_len;
        stops.push((t, css));
    }
    Ok(Some((space, dir, stops)))
}

fn encode_gradient(space: u8, dir: u8, stops: &[(f64, [u8; 4])]) -> Vec<u8> {
    let mut out = vec![space, dir, stops.len() as u8, 0];
    for (t, rgba) in stops {
        out.extend_from_slice(&(*t as f32).to_le_bytes());
        out.extend_from_slice(rgba);
    }
    out
}

fn admit_gradient(
    input: &Input<'_>,
    mark_color: &str,
    index: usize,
) -> Result<Option<Vec<u8>>, TraceCompileError> {
    if !fill_is_gradient_authoring(input) {
        return Ok(None);
    }
    let parsed = if input.flags & FLAG_HAS_GRADIENT_SPEC != 0 {
        parse_gradient_blob(input.gradient_blob, index)?
    } else {
        let space = if input.fill_space.is_empty() {
            "mark"
        } else {
            input.fill_space
        };
        parse_linear_gradient(input.fill_css, space)
    };
    let Some((space, dir, stops)) = parsed else {
        return Ok(None);
    };
    if (dir == 2 || dir == 3) && space == 0 {
        return Ok(None);
    }
    let mut resolved = Vec::new();
    let mut prev_t = -1.0;
    for (t, css) in stops {
        if !t.is_finite() || !(0.0..=1.0).contains(&t) || t < prev_t {
            return Ok(None);
        }
        let Some(rgba) = admit_stop_color(&css, mark_color) else {
            return Ok(None);
        };
        resolved.push((t, rgba));
        prev_t = t;
    }
    if !(2..=8).contains(&resolved.len()) {
        return Ok(None);
    }
    Ok(Some(encode_gradient(space, dir, &resolved)))
}

fn gradient_solid_css(blob: &[u8]) -> String {
    if blob.len() < 4 {
        return "rgb(0,0,0)".to_string();
    }
    let n_stops = blob[2] as usize;
    let mut at = 4usize;
    for _ in 0..n_stops {
        if at + 8 > blob.len() {
            break;
        }
        at += 4;
        let r = blob[at];
        let g = blob[at + 1];
        let b = blob[at + 2];
        let a = blob[at + 3];
        at += 4;
        if a > 0 {
            return format!("rgb({r},{g},{b})");
        }
    }
    "rgb(0,0,0)".to_string()
}

fn admit_glyph(blob: &[u8], kind: &str) -> Option<Vec<u8>> {
    if kind != "scatter" {
        return None;
    }
    let text = std::str::from_utf8(blob).ok()?;
    let mut chars = text.chars();
    let ch = chars.next()?;
    if chars.next().is_some() || ch == '\0' || ch == '\n' || ch == '\r' {
        return None;
    }
    Some(blob.to_vec())
}

fn admit_marker(blob: &[u8], kind: &str) -> Option<Vec<u8>> {
    if kind != "scatter" || blob.len() < 8 {
        return None;
    }
    let n_contours = u32::from_le_bytes(blob[0..4].try_into().ok()?) as usize;
    if !(1..=32).contains(&n_contours) {
        return None;
    }
    let filled = blob[4] != 0;
    let mut at = 8usize;
    let mut total_vertices = 0usize;
    let mut contours: Vec<Vec<f64>> = Vec::with_capacity(n_contours);
    for _ in 0..n_contours {
        if at + 4 > blob.len() {
            return None;
        }
        let n_values = u32::from_le_bytes(blob[at..at + 4].try_into().ok()?) as usize;
        at += 4;
        if n_values < 4 || n_values % 2 != 0 || at + n_values * 8 > blob.len() {
            return None;
        }
        let mut values = Vec::with_capacity(n_values);
        for _ in 0..n_values {
            let value = f64::from_le_bytes(blob[at..at + 8].try_into().ok()?);
            if !value.is_finite() || value.abs() > 0.500001 {
                return None;
            }
            values.push(value);
            at += 8;
        }
        total_vertices += n_values / 2;
        contours.push(values);
    }
    if total_vertices > 96 {
        return None;
    }
    if filled && contours.iter().any(|contour| contour.len() < 6) {
        return None;
    }
    Some(blob.to_vec())
}

fn resolve_style(
    input: &Input<'_>,
    symbol: u16,
    fill_css: &str,
    color: &str,
    index: usize,
) -> Result<ResolvedMarkStyle, TraceCompileError> {
    let mut flags = 0u8;
    if input.kind == "scatter" && symbol >= PLUS_LINE_CODE {
        flags |= MS_LINE_ONLY;
    }
    let fill = if input.flags & FLAG_HAS_FILL != 0 {
        flags |= MS_HAS_FILL;
        fill_css.as_bytes()
    } else {
        b""
    };
    let stroke = if input.flags & FLAG_HAS_STROKE != 0 {
        flags |= MS_HAS_STROKE;
        input.stroke_css.as_bytes()
    } else {
        b""
    };
    let line_color = if input.flags & FLAG_HAS_LINE_COLOR != 0 {
        flags |= MS_HAS_LINE_COLOR;
        input.line_color.as_bytes()
    } else {
        b""
    };
    if input.flags & FLAG_HAS_STROKE_WIDTH != 0 {
        flags |= MS_HAS_STROKE_WIDTH;
    }
    if input.flags & FLAG_HAS_WIDTH != 0 {
        flags |= MS_HAS_WIDTH;
    }
    if input.flags & FLAG_HAS_LINE_WIDTH != 0 {
        flags |= MS_HAS_LINE_WIDTH;
    }
    let color_b = color.as_bytes();
    if fill.len() > u16::MAX as usize
        || stroke.len() > u16::MAX as usize
        || line_color.len() > u16::MAX as usize
        || color_b.len() > u16::MAX as usize
    {
        return Err(TraceCompileError::new(TraceCompileCode::Limit, index));
    }
    let stroke_width = if input.flags & FLAG_HAS_STROKE_WIDTH != 0 {
        input.stroke_width
    } else {
        0.0
    };
    let width = if input.flags & FLAG_HAS_WIDTH != 0 {
        input.width
    } else {
        0.0
    };
    let line_width = if input.flags & FLAG_HAS_LINE_WIDTH != 0 {
        input.line_width
    } else {
        0.0
    };
    let mut record =
        Vec::with_capacity(52 + fill.len() + stroke.len() + line_color.len() + color_b.len());
    record.push(kind_code(input.kind));
    record.push(flags);
    record.extend_from_slice(&0u16.to_le_bytes());
    record.extend_from_slice(&(input.opacity as f32).to_le_bytes());
    record.extend_from_slice(&(input.fill_opacity as f32).to_le_bytes());
    record.extend_from_slice(&(input.stroke_opacity as f32).to_le_bytes());
    record.extend_from_slice(&(input.line_opacity as f32).to_le_bytes());
    record.extend_from_slice(&stroke_width.to_le_bytes());
    record.extend_from_slice(&width.to_le_bytes());
    record.extend_from_slice(&line_width.to_le_bytes());
    record.extend_from_slice(&(fill.len() as u16).to_le_bytes());
    record.extend_from_slice(&(stroke.len() as u16).to_le_bytes());
    record.extend_from_slice(&(line_color.len() as u16).to_le_bytes());
    record.extend_from_slice(&(color_b.len() as u16).to_le_bytes());
    record.extend_from_slice(fill);
    record.extend_from_slice(stroke);
    record.extend_from_slice(line_color);
    record.extend_from_slice(color_b);
    let mut envelope = Vec::with_capacity(16 + record.len());
    envelope.extend_from_slice(b"XYMS");
    envelope.extend_from_slice(&1u32.to_le_bytes());
    envelope.extend_from_slice(&1u32.to_le_bytes());
    envelope.extend_from_slice(&0u32.to_le_bytes());
    envelope.extend_from_slice(&record);
    match scene_style::resolve_mark_styles(&envelope) {
        Ok(mut styles) => styles
            .pop()
            .ok_or(TraceCompileError::new(TraceCompileCode::Length, index)),
        Err(MarkStyleError::Version) => {
            Err(TraceCompileError::new(TraceCompileCode::Version, index))
        }
        Err(MarkStyleError::Limit) => Err(TraceCompileError::new(TraceCompileCode::Limit, index)),
        Err(_) => Err(TraceCompileError::new(TraceCompileCode::Length, index)),
    }
}

fn compile_one(input: Input<'_>, index: usize) -> Result<Compiled, TraceCompileError> {
    if !in_unit_interval(input.opacity) {
        return Err(TraceCompileError::new(TraceCompileCode::Opacity, index));
    }
    if is_band(input.kind) || is_ribbon(input.kind) {
        if !in_unit_interval(input.fill_opacity)
            || !in_unit_interval(input.stroke_opacity)
            || !in_unit_interval(input.line_opacity)
        {
            return Err(TraceCompileError::new(
                TraceCompileCode::OpacityChannel,
                index,
            ));
        }
    }
    let symbol = symbol_code(input.symbol, input.symbol_int, input.flags, index)?;
    let color = constant_color(&input, index)?;
    let admitted = admit_gradient(&input, color, index)?;
    if input.flags & FLAG_HAS_FILL != 0 && fill_is_gradient_authoring(&input) && admitted.is_none()
    {
        return Err(TraceCompileError::new(TraceCompileCode::Fill, index));
    }
    if input.flags & FLAG_HAS_FILL != 0
        && input.fill_css.is_empty()
        && !fill_is_gradient_authoring(&input)
    {
        return Err(TraceCompileError::new(TraceCompileCode::Fill, index));
    }
    let fill_css_owned;
    let fill_css: &str = if let Some(ref blob) = admitted {
        fill_css_owned = gradient_solid_css(blob);
        &fill_css_owned
    } else {
        input.fill_css
    };
    let style = resolve_style(&input, symbol, fill_css, color, index)?;
    if is_band(input.kind) && input.flags & FLAG_PERIMETER_INVALID != 0 {
        return Err(TraceCompileError::new(TraceCompileCode::Perimeter, index));
    }
    let mut fact_bits = 0u32;
    if is_band(input.kind) && input.flags & FLAG_PERIMETER_TRUE != 0 {
        fact_bits |= FACT_STROKE_PERIMETER;
    }
    if curve_smooth(input.kind, input.curve) {
        fact_bits |= FACT_CURVE_SMOOTH;
    }
    let authored_step = parse_step(input.kind, input.step, index)?;
    let (hex_dx, hex_dy) = hex_pitch(input.kind, input.hex_dx, input.hex_dy, index)?;
    let diameter = if input.kind == "scatter" {
        if input.flags & FLAG_HAS_SIZE_CH != 0 && input.size_ch.is_finite() {
            input.size_ch
        } else if input.flags & FLAG_HAS_SIZE != 0 && input.size.is_finite() {
            input.size
        } else {
            DEFAULT_DIAMETER
        }
    } else {
        0.0
    };
    let pack_symbol = if input.kind == "scatter" { symbol } else { 0 };
    let legend_kind: u8 = if input.kind == "scatter" {
        0
    } else if is_stroke(input.kind) {
        1
    } else {
        2
    };
    let legend_include = u8::from(
        input.flags & FLAG_SHOW_LEGEND != 0
            && input.flags & FLAG_HAS_NAME != 0
            && !input.name.is_empty(),
    );
    let legend_symbol = if legend_kind == 0 { symbol } else { 0 };
    let (r_tip, r_base, tip_policy) = admit_corner_radius(&input, index)?;
    let wedge_gap = admit_wedge_gap(&input, index)?;
    Ok(Compiled {
        fill: style.fill,
        stroke: style.stroke,
        stroke_width: style.stroke_width,
        diameter,
        symbol: pack_symbol,
        legend_kind,
        legend_include,
        legend_symbol,
        authored_step,
        fact_bits,
        dash: parse_dash(input.dash, &input.dash_pattern, input.flags),
        linecap: parse_linecap(input.linecap),
        marker: if input.flags & FLAG_HAS_GLYPH != 0 {
            if input.flags & FLAG_HAS_MARKER != 0 {
                return Err(TraceCompileError::new(TraceCompileCode::Symbol, index));
            }
            Some(
                admit_glyph(input.marker_blob, input.kind)
                    .ok_or(TraceCompileError::new(TraceCompileCode::Symbol, index))?,
            )
        } else if input.flags & FLAG_HAS_MARKER != 0 {
            admit_marker(input.marker_blob, input.kind)
        } else {
            None
        },
        gradient: admitted,
        hex_dx,
        hex_dy,
        r_tip,
        r_base,
        tip_policy,
        wedge_gap,
    })
}

fn parse_trace<'a>(
    bytes: &'a [u8],
    at: &mut usize,
    index: usize,
) -> Result<Input<'a>, TraceCompileError> {
    let prefix = take(bytes, at, XYTR_PREFIX_BYTES, index)?;
    if prefix.get(..4) != Some(&XYTR_MAGIC[..]) {
        return Err(TraceCompileError::new(TraceCompileCode::Length, index));
    }
    if read_u16(prefix, 4)? != XYTR_VERSION {
        return Err(TraceCompileError::new(TraceCompileCode::Version, index));
    }
    let kind_len = read_u16(prefix, 6)? as usize;
    let flags = read_u32(prefix, 8)?;
    let name_len = read_u16(prefix, 12)? as usize;
    let symbol_len = read_u16(prefix, 14)? as usize;
    let opacity = read_f64(prefix, 16)?;
    let fill_opacity = read_f64(prefix, 24)?;
    let stroke_opacity = read_f64(prefix, 32)?;
    let line_opacity = read_f64(prefix, 40)?;
    let size = read_f64(prefix, 48)?;
    let size_ch = read_f64(prefix, 56)?;
    let stroke_width = read_f64(prefix, 64)?;
    let width = read_f64(prefix, 72)?;
    let line_width = read_f64(prefix, 80)?;
    let hex_dx = read_f64(prefix, 88)?;
    let hex_dy = read_f64(prefix, 96)?;
    let dash_len = read_u16(prefix, 104)? as usize;
    let linecap_len = read_u16(prefix, 106)? as usize;
    let step_len = read_u16(prefix, 108)? as usize;
    let curve_len = read_u16(prefix, 110)? as usize;
    let fill_css_len = read_u16(prefix, 112)? as usize;
    let stroke_css_len = read_u16(prefix, 114)? as usize;
    let line_color_len = read_u16(prefix, 116)? as usize;
    let color_css_len = read_u16(prefix, 118)? as usize;
    let color_mode_len = read_u16(prefix, 120)? as usize;
    let color_const_len = read_u16(prefix, 122)? as usize;
    let fill_space_len = read_u16(prefix, 124)? as usize;
    let symbol_int = read_u16(prefix, 126)?;
    let dash_pattern_count = read_u32(prefix, 128)? as usize;
    let marker_len = read_u32(prefix, 132)? as usize;
    let gradient_len = read_u32(prefix, 136)? as usize;
    let kind = take_text(bytes, at, kind_len, index)?;
    let name = take_text(bytes, at, name_len, index)?;
    let symbol = take_text(bytes, at, symbol_len, index)?;
    let dash = take_text(bytes, at, dash_len, index)?;
    let linecap = take_text(bytes, at, linecap_len, index)?;
    let step = take_text(bytes, at, step_len, index)?;
    let curve = take_text(bytes, at, curve_len, index)?;
    let fill_css = take_text(bytes, at, fill_css_len, index)?;
    let stroke_css = take_text(bytes, at, stroke_css_len, index)?;
    let line_color = take_text(bytes, at, line_color_len, index)?;
    let color_css = take_text(bytes, at, color_css_len, index)?;
    let color_mode = take_text(bytes, at, color_mode_len, index)?;
    let color_const = take_text(bytes, at, color_const_len, index)?;
    let fill_space = take_text(bytes, at, fill_space_len, index)?;
    if dash_pattern_count > MAX_PATTERN {
        return Err(TraceCompileError::new(TraceCompileCode::Limit, index));
    }
    let pattern_bytes = take(bytes, at, dash_pattern_count.saturating_mul(8), index)?;
    let mut dash_pattern = Vec::with_capacity(dash_pattern_count);
    for chunk in pattern_bytes.chunks_exact(8) {
        dash_pattern.push(f64::from_le_bytes(chunk.try_into().unwrap()));
    }
    let marker_blob = take(bytes, at, marker_len, index)?;
    let gradient_blob = take(bytes, at, gradient_len, index)?;
    let r_tip = read_f64(prefix, 140)?;
    let r_base = read_f64(prefix, 148)?;
    Ok(Input {
        kind,
        flags,
        name,
        symbol,
        symbol_int,
        opacity,
        fill_opacity,
        stroke_opacity,
        line_opacity,
        size,
        size_ch,
        stroke_width,
        width,
        line_width,
        hex_dx,
        hex_dy,
        dash,
        linecap,
        step,
        curve,
        fill_css,
        stroke_css,
        line_color,
        color_css,
        color_mode,
        color_const,
        fill_space,
        dash_pattern,
        marker_blob,
        gradient_blob,
        r_tip,
        r_base,
        wedge_gap: f64::from(read_f32(prefix, 156)?),
    })
}

fn admit_corner_radius(
    input: &Input<'_>,
    index: usize,
) -> Result<(f64, f64, u8), TraceCompileError> {
    let r_tip = input.r_tip;
    let r_base = input.r_base;
    if r_tip == 0.0 && r_base == 0.0 {
        return Ok((0.0, 0.0, 0));
    }
    if !matches!(
        input.kind,
        "bar" | "column" | "histogram" | "heatmap" | "violin" | "box"
    ) {
        return Ok((0.0, 0.0, 0));
    }
    if !r_tip.is_finite() || !r_base.is_finite() || r_tip < 0.0 || r_base < 0.0 {
        return Err(TraceCompileError::new(TraceCompileCode::Length, index));
    }
    let tip_policy = u8::from(input.kind == "bar");
    Ok((r_tip, r_base, tip_policy))
}

fn admit_wedge_gap(input: &Input<'_>, index: usize) -> Result<f64, TraceCompileError> {
    let gap = input.wedge_gap;
    if gap == 0.0 {
        return Ok(0.0);
    }
    if !matches!(input.kind, "bar" | "column" | "histogram") {
        return Ok(0.0);
    }
    if !gap.is_finite() || gap < 0.0 {
        return Err(TraceCompileError::new(TraceCompileCode::Length, index));
    }
    Ok(gap)
}

fn write_compiled(out: &mut Vec<u8>, compiled: &Compiled) {
    let mut prefix = vec![0u8; XYTO_PREFIX_BYTES];
    prefix[..4].copy_from_slice(XYTO_MAGIC);
    prefix[4..6].copy_from_slice(&1u16.to_le_bytes());
    prefix[8..12].copy_from_slice(&compiled.fill);
    prefix[12..16].copy_from_slice(&compiled.stroke);
    prefix[16..24].copy_from_slice(&compiled.stroke_width.to_le_bytes());
    prefix[24..32].copy_from_slice(&compiled.diameter.to_le_bytes());
    prefix[32..34].copy_from_slice(&compiled.symbol.to_le_bytes());
    prefix[34] = compiled.legend_kind;
    prefix[35] = compiled.legend_include;
    prefix[36..38].copy_from_slice(&compiled.legend_symbol.to_le_bytes());
    prefix[38..40].copy_from_slice(&compiled.authored_step.to_le_bytes());
    prefix[40..44].copy_from_slice(&compiled.fact_bits.to_le_bytes());
    let dash = compiled.dash.as_deref().unwrap_or(&[]);
    prefix[44..48].copy_from_slice(&(dash.len() as u32).to_le_bytes());
    prefix[48] = compiled.linecap.unwrap_or(LINECAP_NONE);
    prefix[49] = u8::from(compiled.marker.is_some());
    prefix[50] = u8::from(compiled.gradient.is_some());
    let marker = compiled.marker.as_deref().unwrap_or(&[]);
    let gradient = compiled.gradient.as_deref().unwrap_or(&[]);
    prefix[52..56].copy_from_slice(&(marker.len() as u32).to_le_bytes());
    prefix[56..60].copy_from_slice(&(gradient.len() as u32).to_le_bytes());
    prefix[60..68].copy_from_slice(&compiled.hex_dx.to_le_bytes());
    prefix[68..76].copy_from_slice(&compiled.hex_dy.to_le_bytes());
    prefix[76..84].copy_from_slice(&compiled.r_tip.to_le_bytes());
    prefix[84..92].copy_from_slice(&compiled.r_base.to_le_bytes());
    prefix[92] = compiled.tip_policy;
    prefix[96..104].copy_from_slice(&compiled.wedge_gap.to_le_bytes());
    out.extend_from_slice(&prefix);
    for value in dash {
        out.extend_from_slice(&value.to_le_bytes());
    }
    out.extend_from_slice(marker);
    out.extend_from_slice(gradient);
}

/// Pack authored `XYTC` v1 trace-compile facts into the `XYTO` v1 bundle.
pub fn pack_trace_compile(bytes: &[u8]) -> Result<Vec<u8>, TraceCompileError> {
    if bytes.len() < XYTC_HEADER_BYTES {
        return Err(TraceCompileError::new(TraceCompileCode::Length, 0));
    }
    if bytes.get(..4) != Some(&XYTC_MAGIC[..]) {
        return Err(TraceCompileError::new(TraceCompileCode::Length, 0));
    }
    let version = read_u32(bytes, 4)?;
    if version != XYTC_VERSION {
        return Err(TraceCompileError::new(TraceCompileCode::Version, 0));
    }
    let n_traces = read_u32(bytes, 8)? as usize;
    if n_traces > MAX_TRACES {
        return Err(TraceCompileError::new(TraceCompileCode::Limit, 0));
    }
    let mut at = XYTC_HEADER_BYTES;
    let mut compiled = Vec::with_capacity(n_traces);
    for index in 0..n_traces {
        let input = parse_trace(bytes, &mut at, index)?;
        compiled.push(compile_one(input, index)?);
    }
    if at != bytes.len() {
        return Err(TraceCompileError::new(TraceCompileCode::Length, 0));
    }
    let mut out = Vec::new();
    out.extend_from_slice(XYTO_MAGIC);
    out.extend_from_slice(&XYTO_VERSION.to_le_bytes());
    out.extend_from_slice(&(n_traces as u32).to_le_bytes());
    out.extend_from_slice(&0u32.to_le_bytes());
    for item in &compiled {
        write_compiled(&mut out, item);
    }
    Ok(out)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn prefix(kind: &str, flags: u32, opacity: f64, symbol: &str) -> (Vec<u8>, Vec<u8>) {
        let mut head = vec![0u8; XYTR_PREFIX_BYTES];
        head[..4].copy_from_slice(XYTR_MAGIC);
        head[4..6].copy_from_slice(&XYTR_VERSION.to_le_bytes());
        head[6..8].copy_from_slice(&(kind.len() as u16).to_le_bytes());
        head[8..12].copy_from_slice(&flags.to_le_bytes());
        head[14..16].copy_from_slice(&(symbol.len() as u16).to_le_bytes());
        head[16..24].copy_from_slice(&opacity.to_le_bytes());
        head[24..32].copy_from_slice(&1.0f64.to_le_bytes());
        head[32..40].copy_from_slice(&1.0f64.to_le_bytes());
        head[40..48].copy_from_slice(&1.0f64.to_le_bytes());
        head[48..56].copy_from_slice(&f64::NAN.to_le_bytes());
        head[56..64].copy_from_slice(&f64::NAN.to_le_bytes());
        head[88..96].copy_from_slice(&f64::NAN.to_le_bytes());
        head[96..104].copy_from_slice(&f64::NAN.to_le_bytes());
        let mut payload = Vec::new();
        payload.extend_from_slice(kind.as_bytes());
        payload.extend_from_slice(symbol.as_bytes());
        (head, payload)
    }

    fn envelope(kind: &str, flags: u32, opacity: f64, symbol: &str) -> Vec<u8> {
        let (head, payload) = prefix(kind, flags, opacity, symbol);
        let mut out = Vec::new();
        out.extend_from_slice(XYTC_MAGIC);
        out.extend_from_slice(&XYTC_VERSION.to_le_bytes());
        out.extend_from_slice(&1u32.to_le_bytes());
        out.extend_from_slice(&0u32.to_le_bytes());
        out.extend_from_slice(&head);
        out.extend_from_slice(&payload);
        out
    }

    #[test]
    fn empty_facts_emit_xyto() {
        let mut facts = vec![0u8; XYTC_HEADER_BYTES];
        facts[..4].copy_from_slice(XYTC_MAGIC);
        facts[4..8].copy_from_slice(&XYTC_VERSION.to_le_bytes());
        let packed = pack_trace_compile(&facts).unwrap();
        assert_eq!(&packed[..4], XYTO_MAGIC);
        assert_eq!(u32::from_le_bytes(packed[8..12].try_into().unwrap()), 0);
    }

    #[test]
    fn default_scatter_uses_circle_and_brand_blue() {
        let packed = pack_trace_compile(&envelope("scatter", 0, 1.0, "circle")).unwrap();
        let fill = &packed[XYTO_HEADER_BYTES + 8..XYTO_HEADER_BYTES + 12];
        assert_eq!(fill, &css::color_rgba8("#3987e5", 1.0));
        let diameter = f64::from_le_bytes(
            packed[XYTO_HEADER_BYTES + 24..XYTO_HEADER_BYTES + 32]
                .try_into()
                .unwrap(),
        );
        assert_eq!(diameter, 4.0);
        let symbol = u16::from_le_bytes(
            packed[XYTO_HEADER_BYTES + 32..XYTO_HEADER_BYTES + 34]
                .try_into()
                .unwrap(),
        );
        assert_eq!(symbol, 0);
    }

    #[test]
    fn bad_opacity_is_opacity_error() {
        let err = pack_trace_compile(&envelope("scatter", 0, 1.5, "circle")).unwrap_err();
        assert_eq!(err.code, TraceCompileCode::Opacity);
    }

    #[test]
    fn unknown_symbol_is_symbol_error() {
        let err = pack_trace_compile(&envelope("scatter", 0, 1.0, "nope")).unwrap_err();
        assert_eq!(err.code, TraceCompileCode::Symbol);
    }

    #[test]
    fn dashed_preset_emits_pattern() {
        let (mut head, mut payload) = prefix("line", 0, 1.0, "");
        head[104..106].copy_from_slice(&(b"dashed".len() as u16).to_le_bytes());
        payload.extend_from_slice(b"dashed");
        let mut facts = Vec::new();
        facts.extend_from_slice(XYTC_MAGIC);
        facts.extend_from_slice(&XYTC_VERSION.to_le_bytes());
        facts.extend_from_slice(&1u32.to_le_bytes());
        facts.extend_from_slice(&0u32.to_le_bytes());
        facts.extend_from_slice(&head);
        facts.extend_from_slice(&payload);
        let packed = pack_trace_compile(&facts).unwrap();
        let dash_count = u32::from_le_bytes(
            packed[XYTO_HEADER_BYTES + 44..XYTO_HEADER_BYTES + 48]
                .try_into()
                .unwrap(),
        );
        assert_eq!(dash_count, 2);
        let at = XYTO_HEADER_BYTES + XYTO_PREFIX_BYTES;
        let a = f64::from_le_bytes(packed[at..at + 8].try_into().unwrap());
        let b = f64::from_le_bytes(packed[at + 8..at + 16].try_into().unwrap());
        assert_eq!((a, b), (6.0, 4.0));
    }

    #[test]
    fn hexbin_requires_positive_pitch() {
        let err = pack_trace_compile(&envelope("hexbin", 0, 1.0, "")).unwrap_err();
        assert_eq!(err.code, TraceCompileCode::Hex);
    }

    #[test]
    fn line_step_mid_is_two() {
        let (mut head, mut payload) = prefix("line", 0, 1.0, "");
        head[108..110].copy_from_slice(&(b"mid".len() as u16).to_le_bytes());
        payload.extend_from_slice(b"mid");
        let mut facts = Vec::new();
        facts.extend_from_slice(XYTC_MAGIC);
        facts.extend_from_slice(&XYTC_VERSION.to_le_bytes());
        facts.extend_from_slice(&1u32.to_le_bytes());
        facts.extend_from_slice(&0u32.to_le_bytes());
        facts.extend_from_slice(&head);
        facts.extend_from_slice(&payload);
        let packed = pack_trace_compile(&facts).unwrap();
        let step = u16::from_le_bytes(
            packed[XYTO_HEADER_BYTES + 38..XYTO_HEADER_BYTES + 40]
                .try_into()
                .unwrap(),
        );
        assert_eq!(step, 2);
    }

    #[test]
    fn two_ended_color_is_color_error() {
        let err = pack_trace_compile(&envelope("ribbon", FLAG_COLOR2, 1.0, "")).unwrap_err();
        assert_eq!(err.code, TraceCompileCode::Color);
    }

    #[test]
    fn plus_line_is_line_only_stroke() {
        let packed = pack_trace_compile(&envelope("scatter", 0, 1.0, "plus_line")).unwrap();
        let stroke = &packed[XYTO_HEADER_BYTES + 12..XYTO_HEADER_BYTES + 16];
        assert_eq!(stroke, &css::color_rgba8("#3987e5", 1.0));
        let fill = &packed[XYTO_HEADER_BYTES + 8..XYTO_HEADER_BYTES + 12];
        assert_eq!(fill, &css::color_rgba8("#3987e5", 1.0));
        let width = f64::from_le_bytes(
            packed[XYTO_HEADER_BYTES + 16..XYTO_HEADER_BYTES + 24]
                .try_into()
                .unwrap(),
        );
        assert_eq!(width, 0.0);
        let symbol = u16::from_le_bytes(
            packed[XYTO_HEADER_BYTES + 32..XYTO_HEADER_BYTES + 34]
                .try_into()
                .unwrap(),
        );
        assert_eq!(symbol, PLUS_LINE_CODE);
    }

    #[test]
    fn linear_gradient_fill_admits_xygr_payload() {
        let css = "linear-gradient(to bottom, #ff0000, #0000ff)";
        let (mut head, mut payload) = prefix("bar", FLAG_HAS_FILL, 1.0, "");
        head[112..114].copy_from_slice(&(css.len() as u16).to_le_bytes());
        payload.extend_from_slice(css.as_bytes());
        let mut facts = Vec::new();
        facts.extend_from_slice(XYTC_MAGIC);
        facts.extend_from_slice(&XYTC_VERSION.to_le_bytes());
        facts.extend_from_slice(&1u32.to_le_bytes());
        facts.extend_from_slice(&0u32.to_le_bytes());
        facts.extend_from_slice(&head);
        facts.extend_from_slice(&payload);
        let packed = pack_trace_compile(&facts).unwrap();
        assert_eq!(packed[XYTO_HEADER_BYTES + 50], 1);
        let grad_len = u32::from_le_bytes(
            packed[XYTO_HEADER_BYTES + 56..XYTO_HEADER_BYTES + 60]
                .try_into()
                .unwrap(),
        );
        assert_eq!(grad_len, 4 + 2 * 8);
    }

    #[test]
    fn cartesian_bar_packs_corner_radius_into_xyto_trailer() {
        let (mut head, payload) = prefix("bar", FLAG_HAS_CORNER_RADIUS, 1.0, "");
        head[140..148].copy_from_slice(&4.0f64.to_le_bytes());
        head[148..156].copy_from_slice(&1.0f64.to_le_bytes());
        let mut facts = Vec::new();
        facts.extend_from_slice(XYTC_MAGIC);
        facts.extend_from_slice(&XYTC_VERSION.to_le_bytes());
        facts.extend_from_slice(&1u32.to_le_bytes());
        facts.extend_from_slice(&0u32.to_le_bytes());
        facts.extend_from_slice(&head);
        facts.extend_from_slice(&payload);
        let packed = pack_trace_compile(&facts).unwrap();
        let r_tip = f64::from_le_bytes(
            packed[XYTO_HEADER_BYTES + 76..XYTO_HEADER_BYTES + 84]
                .try_into()
                .unwrap(),
        );
        let r_base = f64::from_le_bytes(
            packed[XYTO_HEADER_BYTES + 84..XYTO_HEADER_BYTES + 92]
                .try_into()
                .unwrap(),
        );
        assert_eq!(r_tip, 4.0);
        assert_eq!(r_base, 1.0);
        assert_eq!(packed[XYTO_HEADER_BYTES + 92], 1);
    }

    #[test]
    fn heatmap_packs_corner_radius_into_xyto_trailer() {
        let (mut head, payload) = prefix("heatmap", FLAG_HAS_CORNER_RADIUS, 1.0, "");
        head[140..148].copy_from_slice(&6.0f64.to_le_bytes());
        head[148..156].copy_from_slice(&6.0f64.to_le_bytes());
        let mut facts = Vec::new();
        facts.extend_from_slice(XYTC_MAGIC);
        facts.extend_from_slice(&XYTC_VERSION.to_le_bytes());
        facts.extend_from_slice(&1u32.to_le_bytes());
        facts.extend_from_slice(&0u32.to_le_bytes());
        facts.extend_from_slice(&head);
        facts.extend_from_slice(&payload);
        let packed = pack_trace_compile(&facts).unwrap();
        let r_tip = f64::from_le_bytes(
            packed[XYTO_HEADER_BYTES + 76..XYTO_HEADER_BYTES + 84]
                .try_into()
                .unwrap(),
        );
        let r_base = f64::from_le_bytes(
            packed[XYTO_HEADER_BYTES + 84..XYTO_HEADER_BYTES + 92]
                .try_into()
                .unwrap(),
        );
        assert_eq!(r_tip, 6.0);
        assert_eq!(r_base, 6.0);
        assert_eq!(packed[XYTO_HEADER_BYTES + 92], 0);
    }

    #[test]
    fn violin_packs_corner_radius_into_xyto_trailer() {
        let (mut head, payload) = prefix("violin", FLAG_HAS_CORNER_RADIUS, 1.0, "");
        head[140..148].copy_from_slice(&4.0f64.to_le_bytes());
        head[148..156].copy_from_slice(&4.0f64.to_le_bytes());
        let mut facts = Vec::new();
        facts.extend_from_slice(XYTC_MAGIC);
        facts.extend_from_slice(&XYTC_VERSION.to_le_bytes());
        facts.extend_from_slice(&1u32.to_le_bytes());
        facts.extend_from_slice(&0u32.to_le_bytes());
        facts.extend_from_slice(&head);
        facts.extend_from_slice(&payload);
        let packed = pack_trace_compile(&facts).unwrap();
        let r_tip = f64::from_le_bytes(
            packed[XYTO_HEADER_BYTES + 76..XYTO_HEADER_BYTES + 84]
                .try_into()
                .unwrap(),
        );
        let r_base = f64::from_le_bytes(
            packed[XYTO_HEADER_BYTES + 84..XYTO_HEADER_BYTES + 92]
                .try_into()
                .unwrap(),
        );
        assert_eq!(r_tip, 4.0);
        assert_eq!(r_base, 4.0);
        // Violin/box share PACK_RECT tessellation but not bar tip-top policy.
        assert_eq!(packed[XYTO_HEADER_BYTES + 92], 0);
    }

    #[test]
    fn box_packs_corner_radius_into_xyto_trailer() {
        let (mut head, payload) = prefix("box", FLAG_HAS_CORNER_RADIUS, 1.0, "");
        head[140..148].copy_from_slice(&5.0f64.to_le_bytes());
        head[148..156].copy_from_slice(&5.0f64.to_le_bytes());
        let mut facts = Vec::new();
        facts.extend_from_slice(XYTC_MAGIC);
        facts.extend_from_slice(&XYTC_VERSION.to_le_bytes());
        facts.extend_from_slice(&1u32.to_le_bytes());
        facts.extend_from_slice(&0u32.to_le_bytes());
        facts.extend_from_slice(&head);
        facts.extend_from_slice(&payload);
        let packed = pack_trace_compile(&facts).unwrap();
        let r_tip = f64::from_le_bytes(
            packed[XYTO_HEADER_BYTES + 76..XYTO_HEADER_BYTES + 84]
                .try_into()
                .unwrap(),
        );
        let r_base = f64::from_le_bytes(
            packed[XYTO_HEADER_BYTES + 84..XYTO_HEADER_BYTES + 92]
                .try_into()
                .unwrap(),
        );
        assert_eq!(r_tip, 5.0);
        assert_eq!(r_base, 5.0);
        assert_eq!(packed[XYTO_HEADER_BYTES + 92], 0);
    }

    #[test]
    fn polar_bar_packs_wedge_gap_into_xyto_trailer() {
        let (mut head, payload) = prefix("bar", FLAG_HAS_WEDGE_GAP, 1.0, "");
        head[156..160].copy_from_slice(&12.0f32.to_le_bytes());
        let mut facts = Vec::new();
        facts.extend_from_slice(XYTC_MAGIC);
        facts.extend_from_slice(&XYTC_VERSION.to_le_bytes());
        facts.extend_from_slice(&1u32.to_le_bytes());
        facts.extend_from_slice(&0u32.to_le_bytes());
        facts.extend_from_slice(&head);
        facts.extend_from_slice(&payload);
        let packed = pack_trace_compile(&facts).unwrap();
        let gap = f64::from_le_bytes(
            packed[XYTO_HEADER_BYTES + 96..XYTO_HEADER_BYTES + 104]
                .try_into()
                .unwrap(),
        );
        assert_eq!(gap, 12.0);
    }
}
