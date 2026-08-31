// Scene chrome/support/polar bulk pack C ABI (ABI 321-322).

use xyg_engine::scene_chrome_pack;
use xyg_engine::scene_figure_support_materialize;
use xyg_engine::scene_polar_input_pack;
use xyg_engine::scene_xyaf_bulk_pack::{self, XyafBulkAnnotationObs, XyafBulkStyleObs};

fn scene_optional_bytes<'a>(ptr: *const u8, len: usize) -> Option<&'a [u8]> {
    if len == 0 {
        Some(&[])
    } else if ptr.is_null() {
        None
    } else {
        Some(unsafe { std::slice::from_raw_parts(ptr, len) })
    }
}

fn scene_optional_f64<'a>(ptr: *const f64, len: usize) -> Option<&'a [f64]> {
    if len == 0 {
        Some(&[])
    } else if ptr.is_null() {
        None
    } else {
        Some(unsafe { std::slice::from_raw_parts(ptr, len) })
    }
}

unsafe fn scene_read_utf8<'a>(ptr: *const u8, len: usize) -> Option<&'a str> {
    if len == 0 {
        Some("")
    } else if ptr.is_null() {
        None
    } else {
        std::str::from_utf8(std::slice::from_raw_parts(ptr, len)).ok()
    }
}

/// Host string sidecar for scene bulk packers (ABI 321+).
#[repr(C)]
pub struct XygStringRef {
    pub ptr: *const u8,
    pub len: usize,
}

/// Axis style observation for ``xyg_scene_chrome_pack`` (ABI 321).
#[repr(C)]
pub struct XygChromeAxisStyleIn {
    pub grid_color: XygStringRef,
    pub grid_width_present: i32,
    pub grid_width: f64,
    pub grid_opacity_present: i32,
    pub grid_opacity: f32,
    pub axis_color: XygStringRef,
    pub axis_width_present: i32,
    pub axis_width: f64,
    pub tick_color: XygStringRef,
    pub tick_width_present: i32,
    pub tick_width: f64,
    pub tick_length_present: i32,
    pub tick_length: f64,
    pub tick_direction: XygStringRef,
    pub tick_label_color: XygStringRef,
    pub label_color: XygStringRef,
}

/// One axis observation for ``xyg_scene_chrome_pack`` (ABI 321).
#[repr(C)]
pub struct XygChromeAxisIn {
    pub side_code: u8,
    pub tick_sides_mask: u8,
    pub label_sides_mask: u8,
    pub style: XygChromeAxisStyleIn,
    pub minor_style: XygChromeAxisStyleIn,
}

/// Tick-collision observation for one axis (ABI 321).
#[repr(C)]
pub struct XygChromeCollisionAxisIn {
    pub strategy: XygStringRef,
    pub collision: XygStringRef,
    pub anchor: XygStringRef,
    pub min_gap_present: i32,
    pub min_gap: f64,
    pub angle_present: i32,
    pub angle: f64,
    pub tick_kind_category: i32,
}

/// Legend observation for ``xyg_scene_chrome_pack`` (ABI 321).
#[repr(C)]
pub struct XygChromeLegendIn {
    pub unsupported_keys: i32,
    pub toggle: i32,
    pub highlight: i32,
    pub loc: XygStringRef,
    pub title: XygStringRef,
    pub ncols: u32,
    pub unsupported_style: i32,
    pub font_size_present: i32,
    pub font_size: f64,
    pub title_font_size_present: i32,
    pub title_font_size: f64,
    pub color: XygStringRef,
    pub background: XygStringRef,
}

/// Colorbar observation for ``xyg_scene_chrome_pack`` (ABI 321).
#[repr(C)]
pub struct XygChromeColorbarIn {
    pub domain_lo: f64,
    pub domain_hi: f64,
    pub stop_count: u32,
    pub side_bottom: i32,
    pub invalid_side: i32,
    pub minor_ticks: i32,
    pub title: XygStringRef,
    pub text_rgba: [u8; 4],
    pub tick_count: u32,
}

/// Host-marshaled chrome pack header for ``xyg_scene_chrome_pack`` (ABI 321).
#[repr(C)]
pub struct XygSceneChromePackIn {
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
    pub title: XygStringRef,
    pub x_label: XygStringRef,
    pub y_label: XygStringRef,
    pub x_format: XygStringRef,
    pub y_format: XygStringRef,
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
    pub x_axis: XygChromeAxisIn,
    pub y_axis: XygChromeAxisIn,
    pub x_major_len: usize,
    pub y_major_len: usize,
    pub x_minor_len: usize,
    pub y_minor_len: usize,
    pub x_tick_label_count: u32,
    pub y_tick_label_count: u32,
    pub x_collision: XygChromeCollisionAxisIn,
    pub y_collision: XygChromeCollisionAxisIn,
    pub chart_background: XygStringRef,
    pub plot_background: XygStringRef,
    pub legend: XygChromeLegendIn,
    pub colorbar_present: i32,
    pub colorbar: XygChromeColorbarIn,
}

unsafe fn string_ref_opt<'a>(value: &XygStringRef) -> Option<&'a str> {
    if value.len == 0 {
        Some("")
    } else {
        scene_read_utf8(value.ptr, value.len)
    }
}

unsafe fn opt_str<'a>(value: &XygStringRef) -> Result<Option<&'a str>, i32> {
    if value.len == 0 {
        Ok(None)
    } else {
        scene_read_utf8(value.ptr, value.len).map(Some).ok_or(-1)
    }
}

unsafe fn chrome_style_from_c(value: &XygChromeAxisStyleIn) -> Result<scene_chrome_pack::ChromeAxisStyleInput<'_>, i32> {
    Ok(scene_chrome_pack::ChromeAxisStyleInput {
        grid_color: opt_str(&value.grid_color)?,
        grid_width: if value.grid_width_present != 0 {
            Some(value.grid_width)
        } else {
            None
        },
        grid_opacity: if value.grid_opacity_present != 0 {
            Some(value.grid_opacity)
        } else {
            None
        },
        axis_color: opt_str(&value.axis_color)?,
        axis_width: if value.axis_width_present != 0 {
            Some(value.axis_width)
        } else {
            None
        },
        tick_color: opt_str(&value.tick_color)?,
        tick_width: if value.tick_width_present != 0 {
            Some(value.tick_width)
        } else {
            None
        },
        tick_length: if value.tick_length_present != 0 {
            Some(value.tick_length)
        } else {
            None
        },
        tick_direction: opt_str(&value.tick_direction)?,
        tick_label_color: opt_str(&value.tick_label_color)?,
        label_color: opt_str(&value.label_color)?,
    })
}

unsafe fn chrome_axis_from_c(value: &XygChromeAxisIn) -> Result<scene_chrome_pack::ChromeAxisInput<'_>, i32> {
    Ok(scene_chrome_pack::ChromeAxisInput {
        side_code: value.side_code,
        tick_sides_mask: value.tick_sides_mask,
        label_sides_mask: value.label_sides_mask,
        style: chrome_style_from_c(&value.style)?,
        minor_style: chrome_style_from_c(&value.minor_style)?,
    })
}

unsafe fn collision_from_c(value: &XygChromeCollisionAxisIn) -> Result<scene_chrome_pack::ChromeCollisionAxisInput<'_>, i32> {
    Ok(scene_chrome_pack::ChromeCollisionAxisInput {
        strategy_raw: opt_str(&value.strategy)?,
        collision_raw: opt_str(&value.collision)?,
        anchor_raw: opt_str(&value.anchor)?,
        min_gap: if value.min_gap_present != 0 {
            Some(value.min_gap)
        } else {
            None
        },
        angle: if value.angle_present != 0 {
            Some(value.angle)
        } else {
            None
        },
        tick_kind_category: value.tick_kind_category,
    })
}

unsafe fn read_tick_labels(refs: *const XygStringRef, count: u32) -> Result<Vec<String>, i32> {
    if count == 0 {
        return Ok(Vec::new());
    }
    if refs.is_null() {
        return Err(-1);
    }
    let mut out = Vec::with_capacity(count as usize);
    for index in 0..count as usize {
        let item = &*refs.add(index);
        let Some(text) = scene_read_utf8(item.ptr, item.len) else {
            return Err(-1);
        };
        out.push(text.to_string());
    }
    Ok(out)
}

macro_rules! abi {
    ($expr:expr) => {
        match $expr {
            Ok(value) => value,
            Err(code) => return code,
        }
    };
}

/// Bulk-pack XYCF v1 chrome facts (ABI 321).
#[allow(clippy::too_many_arguments)]
#[no_mangle]
pub unsafe extern "C" fn xyg_scene_chrome_pack(
    input: *const XygSceneChromePackIn,
    x_major: *const f64,
    y_major: *const f64,
    x_minor: *const f64,
    y_minor: *const f64,
    x_tick_labels: *const XygStringRef,
    y_tick_labels: *const XygStringRef,
    colorbar_stops: *const u8,
    colorbar_ticks: *const f64,
    out: *mut u8,
    out_cap: usize,
    out_len: *mut usize,
) -> i32 {
    if input.is_null() || out_len.is_null() {
        return -1;
    }
    let input = &*input;
    if out_cap > 0 && out.is_null() {
        return -1;
    }
    let Some(title) = string_ref_opt(&input.title) else {
        return -1;
    };
    let Some(x_label) = string_ref_opt(&input.x_label) else {
        return -1;
    };
    let Some(y_label) = string_ref_opt(&input.y_label) else {
        return -1;
    };
    let Some(x_format) = string_ref_opt(&input.x_format) else {
        return -1;
    };
    let Some(y_format) = string_ref_opt(&input.y_format) else {
        return -1;
    };
    let Some(x_major_b) = scene_optional_f64(x_major, input.x_major_len) else {
        return -1;
    };
    let Some(y_major_b) = scene_optional_f64(y_major, input.y_major_len) else {
        return -1;
    };
    let Some(x_minor_b) = scene_optional_f64(x_minor, input.x_minor_len) else {
        return -1;
    };
    let Some(y_minor_b) = scene_optional_f64(y_minor, input.y_minor_len) else {
        return -1;
    };
    let x_tick_label_vec = abi!(read_tick_labels(x_tick_labels, input.x_tick_label_count));
    let y_tick_label_vec = abi!(read_tick_labels(y_tick_labels, input.y_tick_label_count));
    let x_tick_refs: Vec<&str> = x_tick_label_vec.iter().map(String::as_str).collect();
    let y_tick_refs: Vec<&str> = y_tick_label_vec.iter().map(String::as_str).collect();
    let x_axis = abi!(chrome_axis_from_c(&input.x_axis));
    let y_axis = abi!(chrome_axis_from_c(&input.y_axis));
    let x_collision = abi!(collision_from_c(&input.x_collision));
    let y_collision = abi!(collision_from_c(&input.y_collision));
    let leg = &input.legend;
    let legend = scene_chrome_pack::ChromeLegendInput {
        unsupported_keys: leg.unsupported_keys,
        toggle: leg.toggle,
        highlight: leg.highlight,
        loc: abi!(opt_str(&leg.loc)),
        title: abi!(opt_str(&leg.title)),
        ncols: leg.ncols,
        unsupported_style: leg.unsupported_style,
        font_size: if leg.font_size_present != 0 {
            Some(leg.font_size)
        } else {
            None
        },
        title_font_size: if leg.title_font_size_present != 0 {
            Some(leg.title_font_size)
        } else {
            None
        },
        color: abi!(opt_str(&leg.color)),
        background: abi!(opt_str(&leg.background)),
    };
    let mut colorbar_stops_owned: Vec<scene_chrome_pack::ChromeColorbarStop> = Vec::new();
    let mut colorbar_ticks_owned: Vec<f64> = Vec::new();
    let colorbar = if input.colorbar_present != 0 {
        let cb = &input.colorbar;
        let stop_count = cb.stop_count as usize;
        let Some(stops_blob) = scene_optional_bytes(colorbar_stops, stop_count * 12) else {
            return -1;
        };
        colorbar_stops_owned = Vec::with_capacity(stop_count);
        for index in 0..stop_count {
            let at = index * 12;
            let value = f64::from_le_bytes(stops_blob[at..at + 8].try_into().unwrap());
            let rgba: [u8; 4] = stops_blob[at + 8..at + 12].try_into().unwrap();
            colorbar_stops_owned.push(scene_chrome_pack::ChromeColorbarStop { value, rgba });
        }
        let tick_count = cb.tick_count as usize;
        let Some(ticks) = scene_optional_f64(colorbar_ticks, tick_count) else {
            return -1;
        };
        colorbar_ticks_owned = ticks.to_vec();
        Some(scene_chrome_pack::ChromeColorbarInput {
            domain_lo: cb.domain_lo,
            domain_hi: cb.domain_hi,
            stops: &colorbar_stops_owned,
            side_bottom: cb.side_bottom,
            invalid_side: cb.invalid_side,
            minor_ticks: cb.minor_ticks,
            title: abi!(opt_str(&cb.title)),
            text_rgba: cb.text_rgba,
            ticks: if tick_count == 0 {
                None
            } else {
                Some(colorbar_ticks_owned.as_slice())
            },
        })
    } else {
        None
    };
    let pack_input = scene_chrome_pack::SceneChromePackInput {
        width: input.width,
        height: input.height,
        show_legend: input.show_legend,
        colorbar_ok: input.colorbar_ok,
        polar: input.polar,
        has_margins: input.has_margins,
        margin_left: input.margin_left,
        margin_right: input.margin_right,
        margin_top: input.margin_top,
        margin_bottom: input.margin_bottom,
        has_padding: input.has_padding,
        pad_left: input.pad_left,
        pad_right: input.pad_right,
        pad_top: input.pad_top,
        pad_bottom: input.pad_bottom,
        title,
        x_label,
        y_label,
        x_format: abi!(opt_str(&input.x_format)),
        y_format: abi!(opt_str(&input.y_format)),
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
        x_tick_kind: input.x_tick_kind,
        y_tick_kind: input.y_tick_kind,
        x_axis,
        y_axis,
        x_major: if input.x_major_len == 0 {
            None
        } else {
            Some(x_major_b)
        },
        y_major: if input.y_major_len == 0 {
            None
        } else {
            Some(y_major_b)
        },
        x_minor: x_minor_b,
        y_minor: y_minor_b,
        x_tick_labels: if x_tick_refs.is_empty() {
            None
        } else {
            Some(x_tick_refs.as_slice())
        },
        y_tick_labels: if y_tick_refs.is_empty() {
            None
        } else {
            Some(y_tick_refs.as_slice())
        },
        x_collision,
        y_collision,
        chart_background: abi!(opt_str(&input.chart_background)),
        plot_background: abi!(opt_str(&input.plot_background)),
        legend,
        colorbar,
    };
    match scene_chrome_pack::scene_chrome_pack(&pack_input) {
        Ok(packed) => {
            if packed.len() > out_cap {
                return -2;
            }
            if !packed.is_empty() {
                std::ptr::copy_nonoverlapping(packed.as_ptr(), out, packed.len());
            }
            *out_len = packed.len();
            0
        }
        Err(-1) => -1,
        Err(code) => code,
    }
}

/// Annotation observation for ``xyg_scene_figure_support_materialize`` (ABI 322).
#[repr(C)]
pub struct XygFigureSupportAnnotationObs {
    pub has_html: i32,
    pub has_collision: i32,
    pub has_markup: i32,
    pub has_custom_typography: i32,
    pub has_class_name: i32,
    pub kind_is_supported_text: i32,
    pub has_text: i32,
}

/// Axis observation for ``xyg_scene_figure_support_materialize`` (ABI 322).
#[repr(C)]
pub struct XygFigureSupportAxisObsIn {
    pub axis_code: u8,
    pub key_count: u32,
    pub strategy: XygStringRef,
    pub collision: XygStringRef,
}

/// Trace observation for ``xyg_scene_figure_support_materialize`` (ABI 322).
#[repr(C)]
pub struct XygFigureSupportTraceObsIn {
    pub kind: XygStringRef,
    pub x_axis: XygStringRef,
    pub y_axis: XygStringRef,
    pub hidden: i32,
    pub has_per_item_channels: i32,
    pub density_aggregates_color: i32,
    pub marker_glyph_present: i32,
    pub marker_glyph: XygStringRef,
    pub marker_path_present: i32,
    pub marker_path_valid: i32,
    pub marker_path_filled_small: i32,
    pub curve_present: i32,
    pub curve: XygStringRef,
    pub linecap_present: i32,
    pub linecap: XygStringRef,
    pub dash_present: i32,
    pub dash_text: XygStringRef,
    pub dash_is_array: i32,
    pub fill_present: i32,
    pub fill_is_string: i32,
    pub fill_gradient_admitted: i32,
    pub hexbin_reduce: XygStringRef,
    pub heatmap_truecolor: i32,
    pub heatmap_has_colormap: i32,
    pub heatmap_has_rgba_grid: i32,
    pub heatmap_has_rgba: i32,
    pub rect_gradient_fail: i32,
    pub corner_radius_len: usize,
    pub corner_radius_seq: i32,
    pub wedge_gap: f64,
    pub ribbon_color2_fail: i32,
    pub color_channel_unsupported: i32,
}

/// Materialize XYFS v2 figure support from host observations (ABI 322).
#[allow(clippy::too_many_arguments)]
#[no_mangle]
pub unsafe extern "C" fn xyg_scene_figure_support_materialize(
    polar: i32,
    colorbar_unsupported: i32,
    has_custom_font: i32,
    has_browser_css: i32,
    has_extra_legends: i32,
    annotations: *const XygFigureSupportAnnotationObs,
    annotation_count: usize,
    axes: *const XygFigureSupportAxisObsIn,
    axis_count: usize,
    axis_keys_blob: *const u8,
    axis_keys_len: usize,
    traces: *const XygFigureSupportTraceObsIn,
    trace_count: usize,
    corner_radius: *const f64,
    out: *mut u8,
    out_cap: usize,
    out_len: *mut usize,
) -> i32 {
    if out_len.is_null() {
        return -1;
    }
    if out_cap > 0 && out.is_null() {
        return -1;
    }
    let Some(keys_bytes) = scene_optional_bytes(axis_keys_blob, axis_keys_len) else {
        return -1;
    };
    let mut ann_vec = Vec::with_capacity(annotation_count);
    if annotation_count > 0 {
        if annotations.is_null() {
            return -1;
        }
        for index in 0..annotation_count {
            let row = &*annotations.add(index);
            ann_vec.push(scene_figure_support_materialize::FigureSupportAnnotationObs {
                has_html: row.has_html,
                has_collision: row.has_collision,
                has_markup: row.has_markup,
                has_custom_typography: row.has_custom_typography,
                has_class_name: row.has_class_name,
                kind_is_supported_text: row.kind_is_supported_text,
                has_text: row.has_text,
            });
        }
    }
    let mut axis_obs = Vec::with_capacity(axis_count);
    let mut keys_at = 0usize;
    if axis_count > 0 {
        if axes.is_null() {
            return -1;
        }
        for index in 0..axis_count {
            let row = &*axes.add(index);
            let mut keys = Vec::with_capacity(row.key_count as usize);
            let mut at = keys_at;
            for _ in 0..row.key_count {
                if at + 2 > keys_bytes.len() {
                    return -1;
                }
                let key_len = u16::from_le_bytes(keys_bytes[at..at + 2].try_into().unwrap()) as usize;
                at += 2;
                if at + key_len > keys_bytes.len() {
                    return -1;
                }
                let key = match std::str::from_utf8(&keys_bytes[at..at + key_len]) {
                    Ok(text) => text.to_string(),
                    Err(_) => return -1,
                };
                keys.push(key);
                at += key_len;
            }
            keys_at = at;
            axis_obs.push(scene_figure_support_materialize::FigureSupportAxisObs {
                axis_code: row.axis_code,
                keys,
                tick_label_strategy: abi!(opt_str(&row.strategy)),
                collision: abi!(opt_str(&row.collision)),
            });
        }
    }
    let mut trace_obs = Vec::with_capacity(trace_count);
    if trace_count > 0 {
        if traces.is_null() {
            return -1;
        }
        for index in 0..trace_count {
            let row = &*traces.add(index);
            let Some(kind) = string_ref_opt(&row.kind) else {
                return -1;
            };
            let Some(x_axis) = string_ref_opt(&row.x_axis) else {
                return -1;
            };
            let Some(y_axis) = string_ref_opt(&row.y_axis) else {
                return -1;
            };
            let Some(radius) = scene_optional_f64(corner_radius, row.corner_radius_len) else {
                return -1;
            };
            trace_obs.push(scene_figure_support_materialize::FigureSupportTraceObs {
                kind,
                x_axis,
                y_axis,
                hidden: row.hidden,
                has_per_item_channels: row.has_per_item_channels,
                density_aggregates_color: row.density_aggregates_color,
                marker_glyph_present: row.marker_glyph_present,
                marker_glyph: abi!(opt_str(&row.marker_glyph)),
                marker_path_present: row.marker_path_present,
                marker_path_valid: row.marker_path_valid,
                marker_path_filled_small: row.marker_path_filled_small,
                curve_present: row.curve_present,
                curve: abi!(opt_str(&row.curve)),
                linecap_present: row.linecap_present,
                linecap: abi!(opt_str(&row.linecap)),
                dash_present: row.dash_present,
                dash_text: abi!(opt_str(&row.dash_text)),
                dash_is_array: row.dash_is_array,
                fill_present: row.fill_present,
                fill_is_string: row.fill_is_string,
                fill_gradient_admitted: row.fill_gradient_admitted,
                hexbin_reduce: abi!(opt_str(&row.hexbin_reduce)),
                heatmap_truecolor: row.heatmap_truecolor,
                heatmap_has_colormap: row.heatmap_has_colormap,
                heatmap_has_rgba_grid: row.heatmap_has_rgba_grid,
                heatmap_has_rgba: row.heatmap_has_rgba,
                rect_gradient_fail: row.rect_gradient_fail,
                corner_radius_values: radius,
                corner_radius_seq: row.corner_radius_seq,
                wedge_gap: row.wedge_gap,
                ribbon_color2_fail: row.ribbon_color2_fail,
                color_channel_unsupported: row.color_channel_unsupported,
            });
        }
    }
    let materialize = scene_figure_support_materialize::SceneFigureSupportMaterializeIn {
        polar,
        colorbar_unsupported,
        has_custom_font,
        has_browser_css,
        has_extra_legends,
        annotations: &ann_vec,
        axes: &axis_obs,
        traces: &trace_obs,
    };
    match scene_figure_support_materialize::scene_figure_support_materialize(&materialize) {
        Ok(packed) => {
            if packed.len() > out_cap {
                return -2;
            }
            if !packed.is_empty() {
                std::ptr::copy_nonoverlapping(packed.as_ptr(), out, packed.len());
            }
            *out_len = packed.len();
            0
        }
        Err(-1) => -1,
        Err(code) => code,
    }
}

/// Host-marshaled polar input for ``xyg_scene_polar_input_pack`` (ABI 322).
#[repr(C)]
pub struct XygScenePolarInputPackIn {
    pub polar: i32,
    pub theta_unit: u32,
    pub theta_direction: u32,
    pub n_categories: u32,
    pub grid_shape: u8,
    pub r_scale_kind: u32,
    pub r_mask_nonpositive: i32,
    pub sector_start: f64,
    pub sector_end: f64,
    pub r_lo: f64,
    pub r_hi: f64,
    pub r_origin_is_nan: i32,
    pub r_origin: f64,
    pub hole: f64,
    pub r_constant: f64,
    pub theta_zero_is_label: i32,
    pub theta_zero_label: XygStringRef,
    pub theta_zero_numeric: f64,
}

/// Pack XYPL v1 polar authoring (ABI 322).
#[no_mangle]
pub unsafe extern "C" fn xyg_scene_polar_input_pack(
    input: *const XygScenePolarInputPackIn,
    out: *mut u8,
    out_cap: usize,
    out_len: *mut usize,
) -> i32 {
    if input.is_null() || out_len.is_null() {
        return -1;
    }
    let input = &*input;
    if out_cap > 0 && out.is_null() {
        return -1;
    }
    let Some(label) = scene_optional_bytes(input.theta_zero_label.ptr, input.theta_zero_label.len) else {
        return -1;
    };
    let pack_in = scene_polar_input_pack::ScenePolarInputPackIn {
        polar: input.polar,
        theta_unit: input.theta_unit,
        theta_direction: input.theta_direction,
        n_categories: input.n_categories,
        grid_shape: input.grid_shape,
        r_scale_kind: input.r_scale_kind,
        r_mask_nonpositive: input.r_mask_nonpositive,
        sector_start: input.sector_start,
        sector_end: input.sector_end,
        r_lo: input.r_lo,
        r_hi: input.r_hi,
        r_origin_is_nan: input.r_origin_is_nan,
        r_origin: input.r_origin,
        hole: input.hole,
        r_constant: input.r_constant,
        theta_zero_is_label: input.theta_zero_is_label,
        theta_zero_label_len: input.theta_zero_label.len,
        theta_zero_numeric: input.theta_zero_numeric,
    };
    match scene_polar_input_pack::scene_polar_input_pack(&pack_in, label) {
        Ok(packed) => {
            if packed.len() > out_cap {
                return -2;
            }
            if !packed.is_empty() {
                std::ptr::copy_nonoverlapping(packed.as_ptr(), out, packed.len());
            }
            *out_len = packed.len();
            0
        }
        Err(-1) => -1,
        Err(code) => code,
    }
}

/// Style observation for ``xyg_scene_xyaf_bulk_pack`` (ABI 324).
#[repr(C)]
pub struct XygXyafBulkStyleIn {
    pub color: XygStringRef,
    pub stroke_color: XygStringRef,
    pub label_color: XygStringRef,
    pub label_background: XygStringRef,
    pub label_border_color: XygStringRef,
    pub dash: XygStringRef,
    pub linecap: XygStringRef,
    pub opacity_present: i32,
    pub opacity: f64,
    pub width_present: i32,
    pub width: f64,
    pub stroke_width_present: i32,
    pub stroke_width: f64,
    pub label_opacity_present: i32,
    pub label_opacity: f64,
    pub label_border_width_present: i32,
    pub label_border_width: f64,
    pub rotation_present: i32,
    pub rotation: f64,
    pub extra_style_key_count: u32,
}

/// One annotation observation for ``xyg_scene_xyaf_bulk_pack`` (ABI 324).
#[repr(C)]
pub struct XygXyafBulkAnnotationIn {
    pub kind: XygStringRef,
    pub text: XygStringRef,
    pub x_present: i32,
    pub x: f64,
    pub y_present: i32,
    pub y: f64,
    pub x0_present: i32,
    pub x0: f64,
    pub y0_present: i32,
    pub y0: f64,
    pub x1_present: i32,
    pub x1: f64,
    pub y1_present: i32,
    pub y1: f64,
    pub value_present: i32,
    pub value: f64,
    pub start_present: i32,
    pub start: f64,
    pub end_present: i32,
    pub end: f64,
    pub dx_present: i32,
    pub dx: f64,
    pub dy_present: i32,
    pub dy: f64,
    pub size_present: i32,
    pub size: f64,
    pub wrap_present: i32,
    pub wrap: f64,
    pub rotation_present: i32,
    pub rotation: f64,
    pub anchor_present: i32,
    pub anchor: XygStringRef,
    pub axis_present: i32,
    pub axis: XygStringRef,
    pub symbol_present: i32,
    pub symbol: XygStringRef,
    pub index_override_present: i32,
    pub index_override: u32,
    pub style: XygXyafBulkStyleIn,
}

unsafe fn read_style_extra_keys<'a>(
    blob: &'a [u8],
    key_count: u32,
) -> Result<(Vec<String>, usize), i32> {
    let mut extra_keys = Vec::with_capacity(key_count as usize);
    let mut at = 0usize;
    for _ in 0..key_count {
        if at + 2 > blob.len() {
            return Err(-1);
        }
        let key_len = u16::from_le_bytes(blob[at..at + 2].try_into().unwrap()) as usize;
        at += 2;
        if at + key_len > blob.len() {
            return Err(-1);
        }
        let key = match std::str::from_utf8(&blob[at..at + key_len]) {
            Ok(text) => text.to_string(),
            Err(_) => return Err(-1),
        };
        extra_keys.push(key);
        at += key_len;
    }
    Ok((extra_keys, at))
}

struct XyafBulkAnnotationOwned {
    kind: String,
    text: Option<String>,
    x: Option<f64>,
    y: Option<f64>,
    x0: Option<f64>,
    y0: Option<f64>,
    x1: Option<f64>,
    y1: Option<f64>,
    value: Option<f64>,
    start: Option<f64>,
    end: Option<f64>,
    dx: Option<f64>,
    dy: Option<f64>,
    size: Option<f64>,
    wrap: Option<f64>,
    rotation: Option<f64>,
    anchor: Option<String>,
    axis: Option<String>,
    symbol: Option<String>,
    style_extra_keys: Vec<String>,
    style_color: Option<String>,
    style_stroke_color: Option<String>,
    style_label_color: Option<String>,
    style_label_background: Option<String>,
    style_label_border_color: Option<String>,
    style_dash: Option<String>,
    style_linecap: Option<String>,
    style_opacity: Option<f64>,
    style_width: Option<f64>,
    style_stroke_width: Option<f64>,
    style_label_opacity: Option<f64>,
    style_label_border_width: Option<f64>,
    style_rotation: Option<f64>,
    record_index: Option<u32>,
}

impl XyafBulkAnnotationOwned {
    fn obs(&self) -> XyafBulkAnnotationObs<'_> {
        XyafBulkAnnotationObs {
            kind: &self.kind,
            text: self.text.as_deref(),
            x: self.x,
            y: self.y,
            x0: self.x0,
            y0: self.y0,
            x1: self.x1,
            y1: self.y1,
            value: self.value,
            start: self.start,
            end: self.end,
            dx: self.dx,
            dy: self.dy,
            size: self.size,
            wrap: self.wrap,
            rotation: self.rotation,
            anchor: self.anchor.as_deref(),
            axis: self.axis.as_deref(),
            symbol: self.symbol.as_deref(),
            record_index: self.record_index,
            style: XyafBulkStyleObs {
                color: self.style_color.as_deref(),
                stroke_color: self.style_stroke_color.as_deref(),
                label_color: self.style_label_color.as_deref(),
                label_background: self.style_label_background.as_deref(),
                label_border_color: self.style_label_border_color.as_deref(),
                dash: self.style_dash.as_deref(),
                linecap: self.style_linecap.as_deref(),
                opacity: self.style_opacity,
                width: self.style_width,
                stroke_width: self.style_stroke_width,
                label_opacity: self.style_label_opacity,
                label_border_width: self.style_label_border_width,
                rotation: self.style_rotation,
                extra_keys: &self.style_extra_keys,
            },
        }
    }
}

unsafe fn xyaf_annotation_owned_from_c(
    row: &XygXyafBulkAnnotationIn,
    extra_keys_blob: &[u8],
) -> Result<(XyafBulkAnnotationOwned, usize), i32> {
    let Some(kind) = string_ref_opt(&row.kind) else {
        return Err(-1);
    };
    let text = opt_str(&row.text)?.map(str::to_string);
    let (style_extra_keys, consumed) =
        read_style_extra_keys(extra_keys_blob, row.style.extra_style_key_count)?;
    let style = &row.style;
    Ok((
        XyafBulkAnnotationOwned {
            kind: kind.to_string(),
            text,
            x: if row.x_present != 0 { Some(row.x) } else { None },
            y: if row.y_present != 0 { Some(row.y) } else { None },
            x0: if row.x0_present != 0 { Some(row.x0) } else { None },
            y0: if row.y0_present != 0 { Some(row.y0) } else { None },
            x1: if row.x1_present != 0 { Some(row.x1) } else { None },
            y1: if row.y1_present != 0 { Some(row.y1) } else { None },
            value: if row.value_present != 0 { Some(row.value) } else { None },
            start: if row.start_present != 0 { Some(row.start) } else { None },
            end: if row.end_present != 0 { Some(row.end) } else { None },
            dx: if row.dx_present != 0 { Some(row.dx) } else { None },
            dy: if row.dy_present != 0 { Some(row.dy) } else { None },
            size: if row.size_present != 0 { Some(row.size) } else { None },
            wrap: if row.wrap_present != 0 { Some(row.wrap) } else { None },
            rotation: if row.rotation_present != 0 {
                Some(row.rotation)
            } else {
                None
            },
            anchor: opt_str(&row.anchor)?.map(str::to_string),
            axis: opt_str(&row.axis)?.map(str::to_string),
            symbol: opt_str(&row.symbol)?.map(str::to_string),
            style_extra_keys,
            style_color: opt_str(&style.color)?.map(str::to_string),
            style_stroke_color: opt_str(&style.stroke_color)?.map(str::to_string),
            style_label_color: opt_str(&style.label_color)?.map(str::to_string),
            style_label_background: opt_str(&style.label_background)?.map(str::to_string),
            style_label_border_color: opt_str(&style.label_border_color)?.map(str::to_string),
            style_dash: opt_str(&style.dash)?.map(str::to_string),
            style_linecap: opt_str(&style.linecap)?.map(str::to_string),
            style_opacity: if style.opacity_present != 0 {
                Some(style.opacity)
            } else {
                None
            },
            style_width: if style.width_present != 0 {
                Some(style.width)
            } else {
                None
            },
            style_stroke_width: if style.stroke_width_present != 0 {
                Some(style.stroke_width)
            } else {
                None
            },
            style_label_opacity: if style.label_opacity_present != 0 {
                Some(style.label_opacity)
            } else {
                None
            },
            style_label_border_width: if style.label_border_width_present != 0 {
                Some(style.label_border_width)
            } else {
                None
            },
            style_rotation: if style.rotation_present != 0 {
                Some(style.rotation)
            } else {
                None
            },
            record_index: if row.index_override_present != 0 {
                Some(row.index_override)
            } else {
                None
            },
        },
        consumed,
    ))
}

/// Bulk-pack authored annotations into concatenated XYAF v1 records (ABI 324).
#[no_mangle]
pub unsafe extern "C" fn xyg_scene_xyaf_bulk_pack(
    annotations: *const XygXyafBulkAnnotationIn,
    annotation_count: usize,
    extra_style_keys_blob: *const u8,
    extra_style_keys_len: usize,
    out: *mut u8,
    out_cap: usize,
    out_len: *mut usize,
    error_index: *mut u32,
) -> i32 {
    if out_len.is_null() {
        return -1;
    }
    if out_cap > 0 && out.is_null() {
        return -1;
    }
    let Some(keys_bytes) = scene_optional_bytes(extra_style_keys_blob, extra_style_keys_len) else {
        return -1;
    };
    let mut owned_rows: Vec<XyafBulkAnnotationOwned> = Vec::with_capacity(annotation_count);
    let mut keys_at = 0usize;
    if annotation_count > 0 {
        if annotations.is_null() {
            return -1;
        }
        for index in 0..annotation_count {
            let row = &*annotations.add(index);
            let slice = &keys_bytes[keys_at..];
            match xyaf_annotation_owned_from_c(row, slice) {
                Ok((owned, consumed)) => {
                    keys_at += consumed;
                    owned_rows.push(owned);
                }
                Err(code) => {
                    if !error_index.is_null() {
                        *error_index = index as u32;
                    }
                    return code;
                }
            }
        }
    }
    let ann_refs: Vec<_> = owned_rows.iter().map(XyafBulkAnnotationOwned::obs).collect();
    match scene_xyaf_bulk_pack::scene_xyaf_bulk_pack(&ann_refs) {
        Ok(packed) => {
            if packed.len() > out_cap {
                if !error_index.is_null() {
                    *error_index = 0;
                }
                return -2;
            }
            if !packed.is_empty() {
                std::ptr::copy_nonoverlapping(packed.as_ptr(), out, packed.len());
            }
            *out_len = packed.len();
            0
        }
        Err(err) => {
            if !error_index.is_null() {
                *error_index = err.index;
            }
            err.abi_code()
        }
    }
}
