//! Static legend box packing (M2 #275 / ABI 124).
//!
//! Hosts resolve CSS font-size / em paddings and pack entry strings. This
//! module owns column sizing, measured ellipsis, and loc / bbox-to-anchor
//! placement so SVG, raster, and Node cannot drift from `_svg._legend_layout`.

use crate::scene::scene_text_advance;

/// Nominal average advance at [`LEGEND_FONT_PX`].
pub const LEGEND_CHAR_WIDTH: f64 = 6.2;
/// Font size at which [`LEGEND_CHAR_WIDTH`] is the average advance.
pub const LEGEND_FONT_PX: f64 = 11.0;
/// Subpixel slack so a label that fits to the last ulp is not ellipsized.
pub const LEGEND_FIT_EPS: f64 = 1e-9;
/// Unanchored inset from the plot edges.
pub const INSET: f64 = 6.0;
/// Line box as a fraction of font size (`font_size * 1.03`).
pub const TEXT_H_EM: f64 = 1.03;
pub const DEFAULT_BORDERPAD_EM: f64 = 0.4;
pub const DEFAULT_LABELSPACING_EM: f64 = 0.5;
pub const DEFAULT_HANDLELENGTH_EM: f64 = 2.0;
pub const DEFAULT_HANDLETEXTPAD_EM: f64 = 0.8;
pub const COLUMN_GAP_EM: f64 = 2.0;
pub const MIN_TEXT_CHARS: f64 = 4.0;
pub const DEFAULT_SWATCH_H: f64 = 8.0;

pub const METRICS_LEN: usize = 17;
pub const METRIC_PAD: usize = 0;
pub const METRIC_HANDLE: usize = 1;
pub const METRIC_GAP: usize = 2;
pub const METRIC_COLUMN_GAP: usize = 3;
pub const METRIC_ROW_GAP: usize = 4;
pub const METRIC_FONT_SIZE: usize = 5;
pub const METRIC_TEXT_H: usize = 6;
pub const METRIC_LINE_H: usize = 7;
pub const METRIC_SWATCH_H: usize = 8;
pub const METRIC_NCOLS: usize = 9;
pub const METRIC_TITLE_H: usize = 10;
pub const METRIC_CELL_W: usize = 11;
pub const METRIC_BOX_W: usize = 12;
pub const METRIC_BOX_H: usize = 13;
pub const METRIC_X: usize = 14;
pub const METRIC_Y: usize = 15;
pub const METRIC_VISIBLE: usize = 16;

/// Packed static legend geometry after column fit and loc placement.
#[derive(Clone, Debug, PartialEq)]
pub struct LegendBoxLayout {
    pub pad: f64,
    pub handle: f64,
    pub gap: f64,
    pub column_gap: f64,
    pub row_gap: f64,
    pub font_size: f64,
    pub text_h: f64,
    pub line_h: f64,
    pub swatch_h: f64,
    pub ncols: u32,
    pub title: Option<String>,
    pub title_h: f64,
    pub cell_w: f64,
    pub column_widths: Vec<f64>,
    pub column_offsets: Vec<f64>,
    pub box_w: f64,
    pub box_h: f64,
    pub x: f64,
    pub y: f64,
    pub visible_count: u32,
    pub names: Vec<String>,
}

/// Inputs hosts have already resolved from CSS / options.
#[derive(Clone, Copy, Debug)]
pub struct LegendBoxRequest<'a> {
    pub plot_x: f64,
    pub plot_y: f64,
    pub plot_w: f64,
    pub plot_h: f64,
    pub names: &'a [&'a str],
    pub title: Option<&'a str>,
    pub loc: &'a str,
    pub font_size: f64,
    pub handlelength: Option<f64>,
    pub handletextpad: Option<f64>,
    pub handleheight: Option<f64>,
    pub ncols: u32,
    pub padding_em: f64,
    pub row_gap_em: f64,
    pub anchor: Option<(f64, f64, f64, f64)>,
    pub border_axes_pad: f64,
}

fn char_width(font_size: f64) -> f64 {
    font_size * (LEGEND_CHAR_WIDTH / LEGEND_FONT_PX)
}

fn legend_text_width(text: &str, width: f64) -> f64 {
    let font_size = width * (LEGEND_FONT_PX / LEGEND_CHAR_WIDTH);
    scene_text_advance(text, font_size)
}

fn ellipsize(text: &str, max_width: f64, width: f64) -> String {
    if legend_text_width(text, width) <= max_width + LEGEND_FIT_EPS {
        return text.to_string();
    }
    let chars: Vec<char> = text.chars().collect();
    let mut keep = 0usize;
    for index in 1..chars.len() {
        let candidate: String = chars[..index]
            .iter()
            .chain(['.', '.', '.'].iter())
            .collect();
        if legend_text_width(&candidate, width) > max_width + LEGEND_FIT_EPS {
            break;
        }
        keep = index;
    }
    if keep > 0 {
        return chars[..keep].iter().chain(['.', '.', '.'].iter()).collect();
    }
    for count in [3, 2, 1] {
        let dots = ".".repeat(count);
        if legend_text_width(&dots, width) <= max_width + LEGEND_FIT_EPS {
            return dots;
        }
    }
    String::new()
}

fn contains_loc(loc: &str, token: &str) -> bool {
    loc.contains(token)
}

fn loc_tokens(loc: &str) -> bool {
    loc.split(|ch: char| ch.is_whitespace() || ch == '-' || ch == '_')
        .any(|part| part.eq_ignore_ascii_case("top"))
}

/// Pack a static legend box. `None` on non-finite or negative geometry.
pub fn legend_box_layout(request: LegendBoxRequest<'_>) -> Option<LegendBoxLayout> {
    let LegendBoxRequest {
        plot_x,
        plot_y,
        plot_w,
        plot_h,
        names,
        title,
        loc,
        font_size,
        handlelength,
        handletextpad,
        handleheight,
        ncols: requested_ncols,
        padding_em,
        row_gap_em,
        anchor,
        border_axes_pad,
    } = request;
    if ![
        plot_x,
        plot_y,
        plot_w,
        plot_h,
        font_size,
        padding_em,
        row_gap_em,
        border_axes_pad,
    ]
    .iter()
    .all(|value| value.is_finite())
        || plot_w <= 0.0
        || plot_h <= 0.0
        || font_size < 0.0
        || padding_em < 0.0
        || row_gap_em < 0.0
        || border_axes_pad < 0.0
    {
        return None;
    }
    if let Some(value) = handlelength {
        if !value.is_finite() {
            return None;
        }
    }
    if let Some(value) = handletextpad {
        if !value.is_finite() {
            return None;
        }
    }
    if let Some(value) = handleheight {
        if !value.is_finite() {
            return None;
        }
    }
    if let Some((ax, ay, aw, ah)) = anchor {
        if ![ax, ay, aw, ah].iter().all(|value| value.is_finite()) {
            return None;
        }
    }

    let width = char_width(font_size);
    let text_h = font_size * TEXT_H_EM;
    let pad = 2.0 * padding_em * font_size;
    let handle = handlelength.unwrap_or(DEFAULT_HANDLELENGTH_EM).max(0.0) * font_size;
    let gap = handletextpad.unwrap_or(DEFAULT_HANDLETEXTPAD_EM).max(0.0) * font_size;
    let column_gap = COLUMN_GAP_EM * font_size;
    let row_gap = row_gap_em * font_size;
    let mut line_h = text_h + row_gap;
    let mut swatch_h = DEFAULT_SWATCH_H;
    if let Some(handle_h) = handleheight {
        swatch_h = DEFAULT_SWATCH_H.max(LEGEND_FONT_PX * handle_h);
        line_h = line_h.max(swatch_h + 2.0);
    }

    let n = names.len();
    let mut ncols = n.min(requested_ncols.max(1) as usize);
    let title_h = if title.is_some() { line_h } else { 0.0 };
    let available_w = if anchor.is_some() {
        plot_w.max(1.0)
    } else {
        (plot_w - 2.0 * INSET).max(1.0)
    };
    let min_column_w = handle + gap + MIN_TEXT_CHARS * width;
    if ncols > 0
        && ncols as f64 * min_column_w + (ncols as f64 - 1.0) * column_gap + pad > available_w
    {
        let denom = min_column_w + column_gap;
        let max_fit = if denom > 0.0 {
            ((available_w - pad + column_gap).max(0.0) / denom).floor() as usize
        } else {
            1
        };
        ncols = ncols.min(max_fit.max(1));
    }
    if n == 0 {
        ncols = 0;
    }

    let natural_text_widths: Vec<f64> = (0..ncols)
        .map(|column| {
            names
                .iter()
                .skip(column)
                .step_by(ncols)
                .map(|name| legend_text_width(name, width))
                .fold(0.0, f64::max)
        })
        .collect();
    let available_text_w =
        (available_w - pad - ncols as f64 * (handle + gap) - (ncols as f64 - 1.0) * column_gap)
            .max(0.0);
    let minimum_text_w = MIN_TEXT_CHARS * width;
    let mut text_widths: Vec<f64> = natural_text_widths
        .iter()
        .map(|w| (*w).min(minimum_text_w))
        .collect();
    let remaining = (available_text_w - text_widths.iter().sum::<f64>()).max(0.0);
    let needs: Vec<f64> = natural_text_widths
        .iter()
        .zip(text_widths.iter())
        .map(|(natural, current)| (*natural - *current).max(0.0))
        .collect();
    let needed: f64 = needs.iter().sum();
    if needed > 0.0 {
        let scale = (remaining / needed).min(1.0);
        for (current, need) in text_widths.iter_mut().zip(needs.iter()) {
            *current += *need * scale;
        }
    }
    let mut column_widths: Vec<f64> = text_widths.iter().map(|w| handle + gap + *w).collect();
    let mut box_w = if ncols == 0 {
        pad.min(available_w)
    } else {
        available_w.min(column_widths.iter().sum::<f64>() + (ncols as f64 - 1.0) * column_gap + pad)
    };
    let title_text = title.map(str::to_string);
    if let Some(ref raw_title) = title_text {
        let title_w = legend_text_width(raw_title, width) + pad;
        if title_w > box_w && ncols > 0 {
            let extra = (available_w - box_w).min(title_w - box_w);
            for width_slot in &mut column_widths {
                *width_slot += extra / ncols as f64;
            }
            for width_slot in &mut text_widths {
                *width_slot += extra / ncols as f64;
            }
            box_w += extra;
        }
    }
    let mut column_offsets = Vec::with_capacity(ncols);
    let mut cursor = pad / 2.0;
    for col_w in &column_widths {
        column_offsets.push(cursor);
        cursor += *col_w + column_gap;
    }

    let nrows = if ncols == 0 { 0 } else { n.div_ceil(ncols) };
    let available_h = (plot_h - 2.0 * INSET).max(1.0);
    let mut visible_rows = nrows;
    let content_rows = nrows + usize::from(title_text.is_some());
    let natural_box_h =
        content_rows as f64 * text_h + (content_rows.saturating_sub(1) as f64) * row_gap + pad;
    if natural_box_h > available_h {
        let title_room = if title_text.is_some() {
            text_h + row_gap
        } else {
            0.0
        };
        let available_entries_h = (available_h - pad - title_room).max(0.0);
        visible_rows = if line_h > 0.0 {
            ((available_entries_h + row_gap) / line_h).floor().max(0.0) as usize
        } else {
            0
        };
    }
    let visible_count = if ncols == 0 {
        0
    } else {
        n.min(visible_rows * ncols)
    };
    let visible_content_rows = visible_rows + usize::from(title_text.is_some());
    let box_h = available_h.min(
        visible_content_rows as f64 * text_h
            + (visible_content_rows.saturating_sub(1) as f64) * row_gap
            + pad,
    );

    let loc = if loc.is_empty() { "upper right" } else { loc };
    let loc_tokens_upper = contains_loc(loc, "upper") || loc_tokens(loc);
    let loc_is_lower = contains_loc(loc, "lower")
        || loc
            .split(|ch: char| ch.is_whitespace() || ch == '-' || ch == '_')
            .any(|part| part.eq_ignore_ascii_case("bottom"));
    let loc_is_upper = loc_tokens_upper;

    let (x, y) = if let Some((ax, ay, aw, ah)) = anchor {
        let hx = if contains_loc(loc, "left") {
            0.0
        } else if contains_loc(loc, "right") {
            1.0
        } else {
            0.5
        };
        let vy = if loc_is_lower {
            0.0
        } else if loc_is_upper {
            1.0
        } else {
            0.5
        };
        let target_x = plot_x + (ax + hx * aw) * plot_w;
        let target_y = plot_y + (1.0 - ay - vy * ah) * plot_h;
        let mut x = target_x - hx * box_w;
        let mut y = target_y - (1.0 - vy) * box_h;
        x += if hx == 0.0 {
            border_axes_pad
        } else if hx == 1.0 {
            -border_axes_pad
        } else {
            0.0
        };
        y += if vy == 1.0 {
            border_axes_pad
        } else if vy == 0.0 {
            -border_axes_pad
        } else {
            0.0
        };
        (x, y)
    } else {
        let mut x = if contains_loc(loc, "left") {
            plot_x + INSET
        } else if contains_loc(loc, "right") {
            plot_x + plot_w - box_w - INSET
        } else {
            plot_x + (plot_w - box_w) / 2.0
        };
        let mut y = if loc_is_upper {
            plot_y + INSET
        } else if loc_is_lower {
            plot_y + plot_h - box_h - INSET
        } else {
            plot_y + (plot_h - box_h) / 2.0
        };
        x = x.max(plot_x + INSET).min(plot_x + plot_w - box_w - INSET);
        y = y.max(plot_y + INSET).min(plot_y + plot_h - box_h - INSET);
        (x, y)
    };

    let ellipsized_title = title_text
        .as_ref()
        .map(|raw| ellipsize(raw, (box_w - pad).max(0.0), width));
    let ellipsized_names: Vec<String> = names
        .iter()
        .take(visible_count)
        .enumerate()
        .map(|(index, name)| {
            let col = if ncols == 0 { 0 } else { index % ncols };
            ellipsize(name, text_widths[col], width)
        })
        .collect();
    let cell_w = column_widths.iter().copied().fold(0.0, f64::max);

    Some(LegendBoxLayout {
        pad,
        handle,
        gap,
        column_gap,
        row_gap,
        font_size,
        text_h,
        line_h,
        swatch_h,
        ncols: ncols as u32,
        title: ellipsized_title,
        title_h,
        cell_w,
        column_widths,
        column_offsets,
        box_w,
        box_h,
        x,
        y,
        visible_count: visible_count as u32,
        names: ellipsized_names,
    })
}

impl LegendBoxLayout {
    pub fn metrics(&self) -> [f64; METRICS_LEN] {
        let mut out = [0.0; METRICS_LEN];
        out[METRIC_PAD] = self.pad;
        out[METRIC_HANDLE] = self.handle;
        out[METRIC_GAP] = self.gap;
        out[METRIC_COLUMN_GAP] = self.column_gap;
        out[METRIC_ROW_GAP] = self.row_gap;
        out[METRIC_FONT_SIZE] = self.font_size;
        out[METRIC_TEXT_H] = self.text_h;
        out[METRIC_LINE_H] = self.line_h;
        out[METRIC_SWATCH_H] = self.swatch_h;
        out[METRIC_NCOLS] = f64::from(self.ncols);
        out[METRIC_TITLE_H] = self.title_h;
        out[METRIC_CELL_W] = self.cell_w;
        out[METRIC_BOX_W] = self.box_w;
        out[METRIC_BOX_H] = self.box_h;
        out[METRIC_X] = self.x;
        out[METRIC_Y] = self.y;
        out[METRIC_VISIBLE] = f64::from(self.visible_count);
        out
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn request<'a>(names: &'a [&'a str], title: Option<&'a str>) -> LegendBoxRequest<'a> {
        LegendBoxRequest {
            plot_x: 0.0,
            plot_y: 0.0,
            plot_w: 560.0,
            plot_h: 400.0,
            names,
            title,
            loc: "lower left",
            font_size: 11.0,
            handlelength: None,
            handletextpad: None,
            handleheight: None,
            ncols: 1,
            padding_em: DEFAULT_BORDERPAD_EM,
            row_gap_em: DEFAULT_LABELSPACING_EM,
            anchor: None,
            border_axes_pad: 0.0,
        }
    }

    #[test]
    fn titled_short_entries_keep_classes_prefix() {
        let names = ["1", "2", "3", "4"];
        let laid = legend_box_layout(request(&names, Some("Classes"))).unwrap();
        let title = laid.title.as_deref().unwrap();
        assert!(title.starts_with("Clas"), "title was {title}");
        assert!(legend_text_width(title, LEGEND_CHAR_WIDTH) <= laid.box_w - laid.pad + 1e-9);
    }

    #[test]
    fn wide_entries_keep_the_full_title() {
        let names = ["alpha", "beta", "gamma"];
        let laid = legend_box_layout(request(&names, Some("Classes"))).unwrap();
        assert_eq!(laid.title.as_deref(), Some("Classes"));
    }

    #[test]
    fn narrow_plot_ellipsizes_wide_labels() {
        let names = ["Wmmmmmmmmmmmmmmmmmmmm", "iiiiiiiiiiiiiiiiiiii"];
        let laid = legend_box_layout(LegendBoxRequest {
            plot_w: 150.0,
            loc: "upper right",
            ..request(&names, None)
        })
        .unwrap();
        assert!(laid.names.iter().any(|name| name.ends_with("...")));
        let text_x = laid.column_offsets[0] + laid.handle + laid.gap;
        for rendered in &laid.names {
            assert!(text_x + legend_text_width(rendered, LEGEND_CHAR_WIDTH) <= laid.box_w + 1e-9);
        }
    }

    #[test]
    fn upper_right_sits_in_the_inset_corner() {
        let names = ["line"];
        let laid = legend_box_layout(LegendBoxRequest {
            loc: "upper right",
            ..request(&names, None)
        })
        .unwrap();
        assert!((laid.x + laid.box_w + INSET - 560.0).abs() < 1e-9);
        assert!((laid.y - INSET).abs() < 1e-9);
    }
}
