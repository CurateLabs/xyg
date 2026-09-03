//! Figure chrome XYCF bulk pack (M2 Push 3A completion, ABI 321).
//!
//! Hosts marshal figure/axis/legend/colorbar literals. Rust owns XYCF flag
//! assembly, XYCH axis records, tick-collision header, and
//! [`scene_xycf_pack`] concat.

use crate::css;
use crate::kernels::{scene_tick_anchor, scene_tick_label_strategy};
use crate::scene_pack_orchestrate::{scene_xycf_figure_plan, XycfFigurePlan};
use crate::scene_xycf_pack::{scene_xycf_pack, XycfPackHeader, XycfPackSidecars, SCENE_XYCF_PACK_MAX};

pub const SCENE_CHROME_PACK_MAX: usize = SCENE_XYCF_PACK_MAX;

const XYCF_FLAG_AUTHORED_MARGINS: u32 = 1 << 0;
const XYCF_FLAG_PADDING: u32 = 1 << 1;
const XYCF_FLAG_X_MAJOR_AUTO: u32 = 1 << 2;
const XYCF_FLAG_Y_MAJOR_AUTO: u32 = 1 << 3;
const XYCF_FLAG_X_TICK_LABELS: u32 = 1 << 4;
const XYCF_FLAG_Y_TICK_LABELS: u32 = 1 << 5;
const XYCF_FLAG_HAS_CHROME: u32 = 1 << 6;
const XYCF_FLAG_HAS_LEGEND: u32 = 1 << 7;
const XYCF_FLAG_HAS_COLORBAR: u32 = 1 << 8;
const LEGEND_AUTHORED_LOC: u32 = 1 << 0;
const LEGEND_AUTHORED_FONT: u32 = 1 << 1;
const LEGEND_AUTHORED_TITLE_FONT: u32 = 1 << 2;
const LEGEND_AUTHORED_COLOR: u32 = 1 << 3;
const LEGEND_AUTHORED_BACKGROUND: u32 = 1 << 4;
const LEGEND_UNSUPPORTED_KEYS: u32 = 1 << 5;
const LEGEND_TOGGLE: u32 = 1 << 6;
const LEGEND_HIGHLIGHT: u32 = 1 << 7;
const LEGEND_SHOW: u32 = 1 << 8;
const LEGEND_UNSUPPORTED_STYLE: u32 = 1 << 9;
const CB_HORIZONTAL: u32 = 1 << 1;
const CB_MINOR: u32 = 1 << 2;
const CB_INVALID_SIDE: u32 = 1 << 4;
const CH_HAS_CHART_BG: u32 = 1 << 0;
const CH_HAS_PLOT_BG: u32 = 1 << 1;
const CH_PAINT_AXIS: u8 = 1 << 0;
const CH_PAINT_GRID: u8 = 1 << 1;
const CH_PAINT_TICK: u8 = 1 << 2;
const CH_PAINT_MINOR_GRID: u8 = 1 << 3;
const CH_PAINT_MINOR_TICK: u8 = 1 << 4;
const CH_PAINT_LABEL: u8 = 1 << 5;
const CH_WIDTH_AXIS: u8 = 1 << 0;
const CH_WIDTH_GRID: u8 = 1 << 1;
const CH_WIDTH_TICK: u8 = 1 << 2;
const CH_WIDTH_TICK_LENGTH: u8 = 1 << 3;
const CH_WIDTH_MINOR_GRID: u8 = 1 << 4;
const CH_WIDTH_MINOR_TICK: u8 = 1 << 5;
const CH_WIDTH_MINOR_TICK_LENGTH: u8 = 1 << 6;
const DEFAULT_PAINTS: [&str; 6] = ["#202020", "#202020", "#202020", "transparent", "#202020", "#202020"];
const DEFAULT_WIDTHS: [f64; 7] = [1.0, 1.0, 1.0, 4.0, 1.0, 1.0, 0.0];
const MAX_TICK_LABELS: usize = 256;
const MAX_COLORBAR_STOPS: usize = 16;
const MAX_COLORBAR_TICKS: usize = 32;

#[derive(Clone, Debug, Default)]
pub struct ChromeAxisStyleInput<'a> {
    pub grid_color: Option<&'a str>,
    pub grid_width: Option<f64>,
    pub grid_opacity: Option<f32>,
    pub axis_color: Option<&'a str>,
    pub axis_width: Option<f64>,
    pub tick_color: Option<&'a str>,
    pub tick_width: Option<f64>,
    pub tick_length: Option<f64>,
    pub tick_direction: Option<&'a str>,
    pub tick_label_color: Option<&'a str>,
    pub label_color: Option<&'a str>,
}

#[derive(Clone, Debug)]
pub struct ChromeAxisInput<'a> {
    pub side_code: u8,
    pub tick_sides_mask: u8,
    pub label_sides_mask: u8,
    pub style: ChromeAxisStyleInput<'a>,
    pub minor_style: ChromeAxisStyleInput<'a>,
}

#[derive(Clone, Debug, Default)]
pub struct ChromeLegendInput<'a> {
    pub unsupported_keys: i32,
    pub toggle: i32,
    pub highlight: i32,
    pub loc: Option<&'a str>,
    pub title: Option<&'a str>,
    pub ncols: u32,
    pub unsupported_style: i32,
    pub font_size: Option<f64>,
    pub title_font_size: Option<f64>,
    pub color: Option<&'a str>,
    pub background: Option<&'a str>,
}

#[derive(Clone, Copy, Debug)]
pub struct ChromeColorbarStop {
    pub value: f64,
    pub rgba: [u8; 4],
}

#[derive(Clone, Debug, Default)]
pub struct ChromeColorbarInput<'a> {
    pub domain_lo: f64,
    pub domain_hi: f64,
    pub stops: &'a [ChromeColorbarStop],
    pub side_bottom: i32,
    pub invalid_side: i32,
    pub minor_ticks: i32,
    pub title: Option<&'a str>,
    pub text_rgba: [u8; 4],
    pub ticks: Option<&'a [f64]>,
}

#[derive(Clone, Debug, Default)]
pub struct ChromeCollisionAxisInput<'a> {
    pub strategy_raw: Option<&'a str>,
    pub collision_raw: Option<&'a str>,
    pub anchor_raw: Option<&'a str>,
    pub min_gap: Option<f64>,
    pub angle: Option<f64>,
    pub tick_kind_category: i32,
}

#[derive(Clone, Debug)]
pub struct SceneChromePackInput<'a> {
    pub width: f64,
    pub height: f64,
    pub show_legend: i32,
    pub colorbar_ok: i32,
    pub polar: i32,
    pub has_margins: i32,
    pub margin_left: f64,
    pub margin_right: f64,
    pub margin_top: f64,
    pub margin_bottom: f64,
    pub has_padding: i32,
    pub pad_left: f64,
    pub pad_right: f64,
    pub pad_top: f64,
    pub pad_bottom: f64,
    pub title: &'a str,
    pub x_label: &'a str,
    pub y_label: &'a str,
    pub x_format: Option<&'a str>,
    pub y_format: Option<&'a str>,
    pub x_scale_kind: u32,
    pub y_scale_kind: u32,
    pub x_lo: f64,
    pub x_hi: f64,
    pub x_constant: f64,
    pub y_lo: f64,
    pub y_hi: f64,
    pub y_constant: f64,
    pub x_nonpositive_mask: u8,
    pub y_nonpositive_mask: u8,
    pub x_tick_kind: u8,
    pub y_tick_kind: u8,
    pub x_axis: ChromeAxisInput<'a>,
    pub y_axis: ChromeAxisInput<'a>,
    pub x_major: Option<&'a [f64]>,
    pub y_major: Option<&'a [f64]>,
    pub x_minor: &'a [f64],
    pub y_minor: &'a [f64],
    pub x_tick_labels: Option<&'a [&'a str]>,
    pub y_tick_labels: Option<&'a [&'a str]>,
    pub x_collision: ChromeCollisionAxisInput<'a>,
    pub y_collision: ChromeCollisionAxisInput<'a>,
    pub chart_background: Option<&'a str>,
    pub plot_background: Option<&'a str>,
    pub legend: ChromeLegendInput<'a>,
    pub colorbar: Option<ChromeColorbarInput<'a>>,
}

fn tick_strategy_code(axis: &ChromeCollisionAxisInput<'_>) -> u8 {
    let raw = axis.strategy_raw.or(axis.collision_raw).unwrap_or("auto");
    scene_tick_label_strategy(raw).clamp(0, 6) as u8
}

fn tick_anchor_nibble(axis: &ChromeCollisionAxisInput<'_>) -> u8 {
    axis.anchor_raw
        .and_then(|text| {
            let code = scene_tick_anchor(text);
            (code >= 0).then_some(code as u8)
        })
        .unwrap_or(0)
}

fn pack_tick_collision(xa: &ChromeCollisionAxisInput<'_>, ya: &ChromeCollisionAxisInput<'_>) -> (u32, Vec<u8>) {
    let x_strategy = tick_strategy_code(xa);
    let y_strategy = tick_strategy_code(ya);
    let x_anchor = tick_anchor_nibble(xa);
    let y_anchor = tick_anchor_nibble(ya);
    let extras = xa.min_gap.is_some() || ya.min_gap.is_some() || xa.angle.is_some() || ya.angle.is_some();
    let mut flags = 0u32;
    if extras {
        flags |= 1;
    }
    if xa.tick_kind_category != 0 {
        flags |= 1 << 1;
    }
    if ya.tick_kind_category != 0 {
        flags |= 1 << 2;
    }
    if xa.anchor_raw.is_some() {
        flags |= 1 << 3;
    }
    if ya.anchor_raw.is_some() {
        flags |= 1 << 4;
    }
    let header = u32::from(x_strategy)
        | (u32::from(y_strategy) << 8)
        | (u32::from(x_anchor) << 16)
        | (u32::from(y_anchor) << 20)
        | (flags << 24);
    let extra = if extras {
        let mut buf = [0u8; 32];
        for (i, value) in [
            xa.min_gap.unwrap_or(8.0),
            ya.min_gap.unwrap_or(4.0),
            xa.angle.unwrap_or(f64::NAN),
            ya.angle.unwrap_or(f64::NAN),
        ]
        .iter()
        .enumerate()
        {
            buf[i * 8..(i + 1) * 8].copy_from_slice(&value.to_le_bytes());
        }
        buf.to_vec()
    } else {
        Vec::new()
    };
    (header, extra)
}

fn tick_direction_code(raw: Option<&str>) -> u8 {
    match raw.unwrap_or("out") {
        "out" => 0,
        "in" => 1,
        "inout" => 2,
        _ => 255,
    }
}

fn style_width(source: &ChromeAxisStyleInput<'_>, key: &str) -> Option<f64> {
    match key {
        "axis_width" => source.axis_width,
        "grid_width" => source.grid_width,
        "tick_width" => source.tick_width,
        "tick_length" => source.tick_length,
        _ => None,
    }
}

fn pack_chrome_axis(axis: &ChromeAxisInput<'_>) -> Vec<u8> {
    let style = &axis.style;
    let minor = &axis.minor_style;
    let mut paint_flags = 0u8;
    if style.axis_color.is_some() {
        paint_flags |= CH_PAINT_AXIS;
    }
    if style.grid_color.is_some() {
        paint_flags |= CH_PAINT_GRID;
    }
    if style.tick_color.is_some() {
        paint_flags |= CH_PAINT_TICK;
    }
    if minor.grid_color.is_some() {
        paint_flags |= CH_PAINT_MINOR_GRID;
    }
    if minor.tick_color.is_some() {
        paint_flags |= CH_PAINT_MINOR_TICK;
    }
    if style.tick_label_color.is_some() || style.label_color.is_some() {
        paint_flags |= CH_PAINT_LABEL;
    }
    let width_specs: [(&ChromeAxisStyleInput, &str, u8, usize); 7] = [
        (style, "axis_width", CH_WIDTH_AXIS, 0),
        (style, "grid_width", CH_WIDTH_GRID, 1),
        (style, "tick_width", CH_WIDTH_TICK, 2),
        (style, "tick_length", CH_WIDTH_TICK_LENGTH, 3),
        (minor, "grid_width", CH_WIDTH_MINOR_GRID, 4),
        (minor, "tick_width", CH_WIDTH_MINOR_TICK, 5),
        (minor, "tick_length", CH_WIDTH_MINOR_TICK_LENGTH, 6),
    ];
    let mut width_flags = 0u8;
    let mut widths = DEFAULT_WIDTHS;
    for (source, key, flag, index) in width_specs {
        if let Some(v) = style_width(source, key) {
            width_flags |= flag;
            widths[index] = v;
        }
    }
    let paints: [&str; 6] = [
        style.axis_color.unwrap_or(DEFAULT_PAINTS[0]),
        style.grid_color.unwrap_or(DEFAULT_PAINTS[1]),
        style.tick_color.unwrap_or(DEFAULT_PAINTS[2]),
        minor.grid_color.unwrap_or(DEFAULT_PAINTS[3]),
        minor.tick_color.unwrap_or(DEFAULT_PAINTS[4]),
        style
            .tick_label_color
            .or(style.label_color)
            .unwrap_or(DEFAULT_PAINTS[5]),
    ];
    let paint_bytes: Vec<&[u8]> = paints.iter().map(|s| s.as_bytes()).collect();
    let grid_opacity = style.grid_opacity.unwrap_or(1.0);
    let minor_grid_opacity = minor.grid_opacity.unwrap_or(1.0);
    let mut out = Vec::with_capacity(84 + paint_bytes.iter().map(|b| b.len()).sum::<usize>());
    out.extend_from_slice(&[
        axis.side_code,
        axis.tick_sides_mask,
        axis.label_sides_mask,
        tick_direction_code(style.tick_direction),
        tick_direction_code(minor.tick_direction),
        paint_flags,
        width_flags,
        0,
    ]);
    out.extend_from_slice(&grid_opacity.to_le_bytes());
    out.extend_from_slice(&minor_grid_opacity.to_le_bytes());
    for width in widths {
        out.extend_from_slice(&width.to_le_bytes());
    }
    for blob in &paint_bytes {
        out.extend_from_slice(&(blob.len() as u16).to_le_bytes());
    }
    for blob in paint_bytes {
        out.extend_from_slice(blob);
    }
    out
}

fn pack_xych(input: &SceneChromePackInput<'_>) -> Vec<u8> {
    let mut flags = 2u32 << 8;
    let mut chart_b = b"".as_ref();
    let mut plot_b = b"".as_ref();
    if let Some(bg) = input.chart_background {
        flags |= CH_HAS_CHART_BG;
        chart_b = bg.as_bytes();
    }
    if let Some(bg) = input.plot_background {
        flags |= CH_HAS_PLOT_BG;
        plot_b = bg.as_bytes();
    }
    let x_rec = pack_chrome_axis(&input.x_axis);
    let y_rec = pack_chrome_axis(&input.y_axis);
    let mut out = Vec::with_capacity(16 + chart_b.len() + plot_b.len() + x_rec.len() + y_rec.len());
    out.extend_from_slice(b"XYCH");
    out.extend_from_slice(&1u32.to_le_bytes());
    out.extend_from_slice(&flags.to_le_bytes());
    out.extend_from_slice(&(chart_b.len() as u16).to_le_bytes());
    out.extend_from_slice(&(plot_b.len() as u16).to_le_bytes());
    out.extend_from_slice(chart_b);
    out.extend_from_slice(plot_b);
    out.extend_from_slice(&x_rec);
    out.extend_from_slice(&y_rec);
    out
}

fn put_tick_labels(labels: &[&str]) -> Result<Vec<u8>, i32> {
    if labels.len() > MAX_TICK_LABELS {
        return Err(-1);
    }
    let mut out = Vec::with_capacity(labels.len() * 4);
    for label in labels {
        let encoded = label.as_bytes();
        if encoded.len() > u16::MAX as usize {
            return Err(-1);
        }
        out.extend_from_slice(&(encoded.len() as u32).to_le_bytes());
        out.extend_from_slice(encoded);
    }
    Ok(out)
}

fn pack_colorbar_stops(stops: &[ChromeColorbarStop]) -> Result<Vec<u8>, i32> {
    if stops.len() > MAX_COLORBAR_STOPS {
        return Err(-1);
    }
    let mut out = Vec::with_capacity(stops.len() * 12);
    for stop in stops {
        out.extend_from_slice(&stop.value.to_le_bytes());
        out.extend_from_slice(&stop.rgba);
    }
    Ok(out)
}

/// Bulk-pack XYCF v1 chrome facts from host-marshaled figure literals.
pub fn scene_chrome_pack(input: &SceneChromePackInput<'_>) -> Result<Vec<u8>, i32> {
    let mut plan = XycfFigurePlan {
        show_legend: 0,
        attach_legend: 0,
        attach_colorbar: 0,
        polar: 0,
    };
    if scene_xycf_figure_plan(input.show_legend, input.colorbar_ok, input.polar, &mut plan) == 0 {
        return Err(-1);
    }
    let mut flags = XYCF_FLAG_HAS_CHROME | XYCF_FLAG_X_MAJOR_AUTO | XYCF_FLAG_Y_MAJOR_AUTO;
    if input.has_margins != 0 {
        flags |= XYCF_FLAG_AUTHORED_MARGINS;
    }
    if input.has_padding != 0 {
        flags |= XYCF_FLAG_PADDING;
    }
    let x_major = input.x_major.unwrap_or(&[]);
    let y_major = input.y_major.unwrap_or(&[]);
    if input.x_major.is_some() {
        flags &= !XYCF_FLAG_X_MAJOR_AUTO;
    }
    if input.y_major.is_some() {
        flags &= !XYCF_FLAG_Y_MAJOR_AUTO;
    }
    if input.x_tick_labels.is_some() {
        flags |= XYCF_FLAG_X_TICK_LABELS;
    }
    if input.y_tick_labels.is_some() {
        flags |= XYCF_FLAG_Y_TICK_LABELS;
    }
    let (collision_header, collision_extra) =
        pack_tick_collision(&input.x_collision, &input.y_collision);
    let chrome = pack_xych(input);
    let mut legend_loc = b"".as_ref();
    let mut legend_title = b"".as_ref();
    let mut legend_ncols = 1u32;
    let mut legend_font = 0.0f64;
    let mut legend_title_font = 0.0f64;
    let mut legend_flags = 0u32;
    let mut legend_text_rgba = [0u8; 4];
    let mut legend_frame_rgba = [0u8; 4];
    if plan.attach_legend != 0 {
        flags |= XYCF_FLAG_HAS_LEGEND;
        legend_flags |= LEGEND_SHOW;
        let leg = &input.legend;
        if leg.unsupported_keys != 0 {
            legend_flags |= LEGEND_UNSUPPORTED_KEYS;
        }
        legend_ncols = leg.ncols.max(1);
        if leg.toggle != 0 {
            legend_flags |= LEGEND_TOGGLE;
        }
        if leg.highlight != 0 {
            legend_flags |= LEGEND_HIGHLIGHT;
        }
        if let Some(loc) = leg.loc {
            legend_flags |= LEGEND_AUTHORED_LOC;
            legend_loc = loc.as_bytes();
        }
        if leg.unsupported_style != 0 {
            legend_flags |= LEGEND_UNSUPPORTED_STYLE;
        }
        if let Some(size) = leg.font_size {
            legend_flags |= LEGEND_AUTHORED_FONT;
            legend_font = size;
        }
        if let Some(size) = leg.title_font_size {
            legend_flags |= LEGEND_AUTHORED_TITLE_FONT;
            legend_title_font = size;
        }
        legend_title = leg.title.unwrap_or("").as_bytes();
        if let Some(color) = leg.color {
            legend_flags |= LEGEND_AUTHORED_COLOR;
            legend_text_rgba = css::color_rgba8(color, 1.0);
        }
        if let Some(bg) = leg.background {
            legend_flags |= LEGEND_AUTHORED_BACKGROUND;
            legend_frame_rgba = css::color_rgba8(bg, 1.0);
        }
    }
    let mut colorbar_obs = 0u32;
    let mut stop_count = 0u32;
    let mut tick_count = 0u32;
    let mut cb_title = b"".as_ref();
    let mut cb_lo = 0.0f64;
    let mut cb_hi = 0.0f64;
    let mut cb_text = [32u8, 32, 32, 255];
    let mut cb_stops_blob = Vec::new();
    let mut cb_ticks: Vec<f64> = Vec::new();
    if plan.attach_colorbar != 0 {
        let Some(ref cb) = input.colorbar else {
            return Err(-1);
        };
        flags |= XYCF_FLAG_HAS_COLORBAR;
        cb_lo = cb.domain_lo;
        cb_hi = cb.domain_hi;
        cb_stops_blob = pack_colorbar_stops(cb.stops)?;
        stop_count = cb.stops.len() as u32;
        if cb.side_bottom != 0 {
            colorbar_obs |= CB_HORIZONTAL;
        }
        if cb.invalid_side != 0 {
            colorbar_obs |= CB_INVALID_SIDE;
        }
        if cb.minor_ticks != 0 {
            colorbar_obs |= CB_MINOR;
        }
        cb_title = cb.title.unwrap_or("").as_bytes();
        cb_text = cb.text_rgba;
        if let Some(ticks) = cb.ticks {
            if ticks.len() > MAX_COLORBAR_TICKS {
                return Err(-1);
            }
            cb_ticks = ticks.to_vec();
            tick_count = ticks.len() as u32;
        }
    }
    let x_labels_blob = input
        .x_tick_labels
        .map(put_tick_labels)
        .transpose()?
        .unwrap_or_default();
    let y_labels_blob = input
        .y_tick_labels
        .map(put_tick_labels)
        .transpose()?
        .unwrap_or_default();
    let tick_kinds = u16::from(input.x_tick_kind) | (u16::from(input.y_tick_kind) << 8);
    let header = XycfPackHeader {
        flags,
        collision_header,
        width: input.width,
        height: input.height,
        margin_left: input.margin_left,
        margin_right: input.margin_right,
        margin_top: input.margin_top,
        margin_bottom: input.margin_bottom,
        pad_left: input.pad_left,
        pad_right: input.pad_right,
        pad_top: input.pad_top,
        pad_bottom: input.pad_bottom,
        x_scale_kind: input.x_scale_kind,
        y_scale_kind: input.y_scale_kind,
        x_lo: input.x_lo,
        x_hi: input.x_hi,
        x_constant: input.x_constant,
        y_lo: input.y_lo,
        y_hi: input.y_hi,
        y_constant: input.y_constant,
        x_nonpositive_mask: input.x_nonpositive_mask,
        y_nonpositive_mask: input.y_nonpositive_mask,
        tick_kinds,
        title_len: input.title.len() as u32,
        x_label_len: input.x_label.len() as u32,
        y_label_len: input.y_label.len() as u32,
        x_format_len: input.x_format.map(|s| s.len()).unwrap_or(0) as u32,
        y_format_len: input.y_format.map(|s| s.len()).unwrap_or(0) as u32,
        x_major_len: x_major.len() as u32,
        x_minor_len: input.x_minor.len() as u32,
        y_major_len: y_major.len() as u32,
        y_minor_len: input.y_minor.len() as u32,
        x_label_count: input.x_tick_labels.map(|l| l.len()).unwrap_or(0) as u32,
        y_label_count: input.y_tick_labels.map(|l| l.len()).unwrap_or(0) as u32,
        chrome_len: chrome.len() as u32,
        legend_loc_len: legend_loc.len() as u32,
        legend_title_len: legend_title.len() as u32,
        legend_ncols,
        legend_font_size: legend_font,
        legend_title_font_size: legend_title_font,
        legend_flags,
        legend_count: 0,
        legend_text_rgba,
        legend_frame_rgba,
        colorbar_obs,
        colorbar_stop_count: stop_count,
        colorbar_tick_count: tick_count,
        colorbar_title_len: cb_title.len() as u32,
        colorbar_lo: cb_lo,
        colorbar_hi: cb_hi,
        colorbar_text_rgba: cb_text,
    };
    let sidecars = XycfPackSidecars {
        title: input.title.as_bytes(),
        x_label: input.x_label.as_bytes(),
        y_label: input.y_label.as_bytes(),
        x_format: input.x_format.unwrap_or("").as_bytes(),
        y_format: input.y_format.unwrap_or("").as_bytes(),
        x_major,
        x_minor: input.x_minor,
        y_major,
        y_minor: input.y_minor,
        x_labels_blob: &x_labels_blob,
        y_labels_blob: &y_labels_blob,
        chrome: &chrome,
        legend_loc,
        legend_title,
        legend_meta: &[],
        legend_lens: &[],
        legend_blob: &[],
        colorbar_stops_blob: &cb_stops_blob,
        colorbar_ticks: &cb_ticks,
        colorbar_title: cb_title,
        collision_extra: &collision_extra,
    };
    scene_xycf_pack(&header, &sidecars)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn default_axis() -> ChromeAxisInput<'static> {
        ChromeAxisInput {
            side_code: 0,
            tick_sides_mask: 1,
            label_sides_mask: 1,
            style: ChromeAxisStyleInput::default(),
            minor_style: ChromeAxisStyleInput::default(),
        }
    }

    #[test]
    fn packs_minimal_chrome() {
        let input = SceneChromePackInput {
            width: 400.0,
            height: 300.0,
            show_legend: 0,
            colorbar_ok: 0,
            polar: 0,
            has_margins: 0,
            margin_left: 0.0,
            margin_right: 0.0,
            margin_top: 0.0,
            margin_bottom: 0.0,
            has_padding: 0,
            pad_left: 0.0,
            pad_right: 0.0,
            pad_top: 0.0,
            pad_bottom: 0.0,
            title: "",
            x_label: "",
            y_label: "",
            x_format: None,
            y_format: None,
            x_scale_kind: 0,
            y_scale_kind: 0,
            x_lo: 0.0,
            x_hi: 1.0,
            x_constant: 1.0,
            y_lo: 0.0,
            y_hi: 1.0,
            y_constant: 1.0,
            x_nonpositive_mask: 0,
            y_nonpositive_mask: 0,
            x_tick_kind: 0,
            y_tick_kind: 0,
            x_axis: default_axis(),
            y_axis: default_axis(),
            x_major: None,
            y_major: None,
            x_minor: &[],
            y_minor: &[],
            x_tick_labels: None,
            y_tick_labels: None,
            x_collision: ChromeCollisionAxisInput::default(),
            y_collision: ChromeCollisionAxisInput::default(),
            chart_background: None,
            plot_background: None,
            legend: ChromeLegendInput::default(),
            colorbar: None,
        };
        let packed = scene_chrome_pack(&input).unwrap();
        assert_eq!(&packed[..4], b"XYCF");
    }
}
