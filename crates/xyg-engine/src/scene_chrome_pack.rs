//! Figure chrome XYCF bulk pack (M2 Push 3A completion, ABI 321).
//!
//! Hosts marshal figure/axis/legend/colorbar literals. Rust owns XYCF flag
//! assembly, XYCH axis records, tick-collision header, and
//! [`scene_xycf_pack`] concat.

use crate::css;
use crate::kernels::{scene_tick_anchor, scene_tick_label_strategy};
use crate::scene_pack_orchestrate::{scene_xycf_figure_plan, XycfFigurePlan};
use crate::scene::tick_label_table;
use crate::scene_style;
use crate::scene_xycf_pack::{scene_xycf_pack, XycfPackHeader, XycfPackSidecars, SCENE_XYCF_PACK_MAX};
use crate::scene_y2::{SceneY2Metrics, SceneY2Wire};

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
/// Minimum gap between y (and y2) tick labels when none is authored.
const DEFAULT_Y_MIN_GAP: f64 = 4.0;
/// Constant of a log/symlog axis when none is authored.
const DEFAULT_SCALE_CONSTANT: f64 = 1.0;
/// Side code (1 = high/right) of a secondary y axis whose side is not authored.
const Y2_DEFAULT_SIDE_CODE: u8 = 1;

/// Axis role for [`resolve_axis_side_code`]: bottom/top x axis.
pub const AXIS_SIDE_ROLE_X: i32 = 0;
/// Axis role for [`resolve_axis_side_code`]: primary y axis (left/right).
pub const AXIS_SIDE_ROLE_Y: i32 = 1;
/// Axis role for [`resolve_axis_side_code`]: secondary y axis (left/right).
pub const AXIS_SIDE_ROLE_Y2: i32 = 2;

/// Resolve an axis side code (0 = low: bottom/left, 1 = high: top/right) from
/// the authored side (`None` = unauthored). This is the single owner of the
/// default-side policy: x is bottom, the primary y is left, and an unauthored
/// y2 is the right side. Static Scene export (`pack_y2_sidecar`) and the live
/// payload (via `xyg_payload_axis_side_resolve`) both read it. `None` is
/// returned for an unknown role or an authored code outside 0/1.
pub fn resolve_axis_side_code(role: i32, authored: Option<u8>) -> Option<u8> {
    if let Some(code) = authored {
        return (code <= 1 && (AXIS_SIDE_ROLE_X..=AXIS_SIDE_ROLE_Y2).contains(&role)).then_some(code);
    }
    match role {
        AXIS_SIDE_ROLE_X | AXIS_SIDE_ROLE_Y => Some(0),
        AXIS_SIDE_ROLE_Y2 => Some(Y2_DEFAULT_SIDE_CODE),
        _ => None,
    }
}
/// Byte range of the y axis record inside the 200-byte resolved Scene style.
const SCENE_STYLE_Y_AXIS: std::ops::Range<usize> = 112..200;
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

/// Resolved XYCO typography/paint facts copied into the `XYY2` metrics block.
#[derive(Clone, Copy, Debug)]
pub struct ChromeY2Metrics {
    pub tick_size: f64,
    pub title_size: f64,
    pub padding: f64,
    pub text_flags: u32,
    pub tick_rgba: Option<[u8; 4]>,
    pub title_rgba: Option<[u8; 4]>,
}

/// Authored secondary right-hand y axis. Hosts marshal presence and authored
/// values only; scale constant, tick policy defaults, the axis chrome record and
/// the `XYY2` layout are Rust's, and the same collision code serves y and y2.
#[derive(Clone, Debug)]
pub struct ChromeY2Input<'a> {
    pub scale_kind: u32,
    pub lo: f64,
    pub hi: f64,
    pub constant: Option<f64>,
    pub nonpositive_mask: u8,
    /// The chrome axis observation. Its side code and tick/label side masks only
    /// count where the matching `*_authored` flag is set: an unauthored y2 side is
    /// the right side, and an unauthored mask is that side, decided here.
    pub axis: ChromeAxisInput<'a>,
    pub side_authored: bool,
    pub tick_sides_authored: bool,
    pub label_sides_authored: bool,
    pub collision: ChromeCollisionAxisInput<'a>,
    pub major: Option<&'a [f64]>,
    pub minor: &'a [f64],
    pub tick_labels: Option<&'a [&'a str]>,
    pub title: Option<&'a str>,
    pub format: Option<&'a str>,
    pub metrics: Option<ChromeY2Metrics>,
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
    /// Optional secondary right-hand y axis, appended as an `XYY2` sidecar.
    pub y2: Option<ChromeY2Input<'a>>,
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
            ya.min_gap.unwrap_or(DEFAULT_Y_MIN_GAP),
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

fn pack_xych(input: &SceneChromePackInput<'_>, y_axis: &ChromeAxisInput<'_>) -> Vec<u8> {
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
    let y_rec = pack_chrome_axis(y_axis);
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

/// Build the `XYY2` sidecar (data-valued domain) from authored y2 facts. The axis
/// chrome record is the y record of the Scene style resolved from the y2 style,
/// exactly as the primary y style resolves; nothing is validated here, so the
/// Scene encoder rejects invalid values identically for every host.
fn pack_y2_sidecar(input: &SceneChromePackInput<'_>, y2: &ChromeY2Input<'_>) -> Result<Vec<u8>, i32> {
    let mut axis = y2.axis.clone();
    if !y2.side_authored {
        axis.side_code = resolve_axis_side_code(AXIS_SIDE_ROLE_Y2, None).expect("y2 role always has a default side");
    }
    if !y2.tick_sides_authored {
        axis.tick_sides_mask = 1 << axis.side_code;
    }
    if !y2.label_sides_authored {
        axis.label_sides_mask = 1 << axis.side_code;
    }
    let style = scene_style::resolve_chrome_style(&pack_xych(input, &axis)).map_err(|_| -1)?;
    let authored_anchor = y2.collision.anchor_raw.is_some();
    let labels = y2.tick_labels.map(|labels| tick_label_table(labels.iter().copied()));
    let metrics = y2.metrics;
    Ok(SceneY2Wire {
        kind: y2.scale_kind,
        lo: y2.lo,
        hi: y2.hi,
        constant: y2.constant.unwrap_or(DEFAULT_SCALE_CONSTANT),
        mask: y2.nonpositive_mask != 0,
        chrome: &style[SCENE_STYLE_Y_AXIS],
        metrics: metrics.map(|m| SceneY2Metrics {
            tick_size: m.tick_size,
            title_size: m.title_size,
            padding: m.padding,
        }),
        text_flags: metrics.map_or(0, |m| m.text_flags),
        tick_rgba: metrics.and_then(|m| m.tick_rgba),
        title_rgba: metrics.and_then(|m| m.title_rgba),
        tick_strategy: tick_strategy_code(&y2.collision),
        tick_anchor: if authored_anchor {
            tick_anchor_nibble(&y2.collision)
        } else {
            0
        },
        tick_anchor_authored: authored_anchor,
        tick_category: y2.collision.tick_kind_category != 0,
        tick_min_gap: y2.collision.min_gap.unwrap_or(DEFAULT_Y_MIN_GAP),
        tick_angle: y2.collision.angle,
        major_ticks: y2.major,
        minor_ticks: y2.minor,
        labels: labels.as_deref().unwrap_or(&[]),
        title: y2.title.unwrap_or(""),
        format: y2.format.unwrap_or(""),
    }
    .write())
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
    let chrome = pack_xych(input, &input.y_axis);
    let y2_sidecar = input
        .y2
        .as_ref()
        .map(|y2| pack_y2_sidecar(input, y2))
        .transpose()?
        .unwrap_or_default();
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
        y2: &y2_sidecar,
    };
    scene_xycf_pack(&header, &sidecars)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn axis_side_resolution_owns_the_default_policy() {
        assert_eq!(resolve_axis_side_code(AXIS_SIDE_ROLE_X, None), Some(0));
        assert_eq!(resolve_axis_side_code(AXIS_SIDE_ROLE_Y, None), Some(0));
        assert_eq!(resolve_axis_side_code(AXIS_SIDE_ROLE_Y2, None), Some(1));
        assert_eq!(resolve_axis_side_code(AXIS_SIDE_ROLE_Y2, Some(0)), Some(0));
        assert_eq!(resolve_axis_side_code(AXIS_SIDE_ROLE_Y2, Some(1)), Some(1));
        assert_eq!(resolve_axis_side_code(AXIS_SIDE_ROLE_Y2, Some(2)), None);
        assert_eq!(resolve_axis_side_code(3, None), None);
    }

    fn default_axis() -> ChromeAxisInput<'static> {
        ChromeAxisInput {
            side_code: 0,
            tick_sides_mask: 1,
            label_sides_mask: 1,
            style: ChromeAxisStyleInput::default(),
            minor_style: ChromeAxisStyleInput::default(),
        }
    }

    fn minimal_input(y2: Option<ChromeY2Input<'static>>) -> SceneChromePackInput<'static> {
        SceneChromePackInput {
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
            y2,
        }
    }

    #[test]
    fn packs_minimal_chrome() {
        let packed = scene_chrome_pack(&minimal_input(None)).unwrap();
        assert_eq!(&packed[..4], b"XYCF");
        assert!(crate::scene_chrome::xycf_y2_sidecar(&packed).unwrap().is_none());
    }

    fn y2_input() -> ChromeY2Input<'static> {
        ChromeY2Input {
            scale_kind: 0,
            lo: 0.0,
            hi: 100.0,
            constant: None,
            nonpositive_mask: 0,
            axis: ChromeAxisInput {
                side_code: 1,
                tick_sides_mask: 2,
                label_sides_mask: 2,
                style: ChromeAxisStyleInput::default(),
                minor_style: ChromeAxisStyleInput::default(),
            },
            side_authored: true,
            tick_sides_authored: true,
            label_sides_authored: true,
            collision: ChromeCollisionAxisInput::default(),
            major: None,
            minor: &[],
            tick_labels: None,
            title: None,
            format: None,
            metrics: None,
        }
    }

    fn decoded_y2(y2: ChromeY2Input<'static>) -> Result<crate::scene_y2::SceneY2Axis, crate::scene::SceneError> {
        let packed = scene_chrome_pack(&minimal_input(Some(y2))).unwrap();
        let sidecar = crate::scene_chrome::xycf_y2_sidecar(&packed).unwrap().unwrap();
        crate::scene_y2::SceneY2Axis::decode(sidecar, crate::scene_y2::SceneY2Domain::Data, 300.0, 0.0)
    }

    #[test]
    fn y2_defaults_are_rust_owned_and_match_the_primary_axis_policy() {
        let axis = decoded_y2(y2_input()).unwrap();
        // Unauthored facts resolve here, never in a host.
        assert_eq!(axis.tick_min_gap, DEFAULT_Y_MIN_GAP);
        assert_eq!(axis.tick_strategy, 0);
        assert!(!axis.tick_anchor_authored);
        assert_eq!(axis.tick_angle, None);
        assert!(axis.major_ticks.is_none() && axis.tick_labels.is_none());
        assert_eq!(axis.scale.wire_scale(true).3, DEFAULT_SCALE_CONSTANT);
        // The same strategy code serves y and y2: `strategy` wins over `collision`.
        let collision = ChromeCollisionAxisInput {
            collision_raw: Some("hide"),
            ..Default::default()
        };
        let mut y2 = y2_input();
        y2.collision = collision.clone();
        assert_eq!(decoded_y2(y2).unwrap().tick_strategy, tick_strategy_code(&collision));
        let mut both = collision.clone();
        both.strategy_raw = Some("rotate");
        let mut y2 = y2_input();
        y2.collision = both.clone();
        let strategy = decoded_y2(y2).unwrap().tick_strategy;
        assert_eq!(strategy, tick_strategy_code(&both));
        assert_ne!(strategy, tick_strategy_code(&collision));
        // Authored values pass through untouched.
        let authored = ChromeCollisionAxisInput {
            min_gap: Some(9.0),
            angle: Some(30.0),
            anchor_raw: Some("end"),
            ..Default::default()
        };
        let mut y2 = y2_input();
        y2.collision = authored;
        let axis = decoded_y2(y2).unwrap();
        assert_eq!(axis.tick_min_gap, 9.0);
        assert_eq!(axis.tick_angle, Some(30.0));
        assert!(axis.tick_anchor_authored);
    }

    #[test]
    fn an_unauthored_y2_side_is_the_right_side_and_masks_follow_it() {
        // Hosts pass absent facts with placeholder codes; Rust ignores them.
        let mut y2 = y2_input();
        y2.axis.side_code = 0;
        y2.axis.tick_sides_mask = 0b01;
        y2.axis.label_sides_mask = 0b01;
        y2.side_authored = false;
        y2.tick_sides_authored = false;
        y2.label_sides_authored = false;
        let axis = decoded_y2(y2.clone()).expect("an unauthored side is admitted as right");
        assert_eq!(axis.axis.side, crate::scene::AxisSide::High);
        assert_eq!((axis.axis.tick_sides, axis.axis.tick_label_sides), (0b10, 0b10));
        // The explicit right side resolves to the identical axis record.
        let explicit = decoded_y2(y2_input()).unwrap();
        assert_eq!(
            (axis.axis.side, axis.axis.tick_sides, axis.axis.tick_label_sides),
            (explicit.axis.side, explicit.axis.tick_sides, explicit.axis.tick_label_sides)
        );
        // An authored left side is not overridden: the Scene refuses it.
        y2.side_authored = true;
        y2.tick_sides_authored = true;
        y2.label_sides_authored = true;
        assert!(decoded_y2(y2).is_err());
    }

    #[test]
    fn y2_invalid_authored_values_are_rejected_by_the_scene_not_defaulted() {
        use crate::scene::SceneError;
        let with = |mutate: &dyn Fn(&mut ChromeY2Input<'static>)| {
            let mut y2 = y2_input();
            mutate(&mut y2);
            decoded_y2(y2).err()
        };
        assert!(decoded_y2(y2_input()).is_ok());
        // An authored zero constant is passed through, not turned into the default.
        assert!(with(&|y2| y2.constant = Some(0.0)).is_some());
        assert!(with(&|y2| y2.constant = Some(-2.0)).is_some());
        assert!(with(&|y2| y2.hi = f64::INFINITY).is_some());
        assert!(matches!(
            with(&|y2| y2.collision.angle = Some(f64::INFINITY)),
            Some(SceneError::NonFinite)
        ));
    }
}
