//! Figure-compile XYFS v2 support materialize (M2 Push 3A completion, ABI 322).
//!
//! Hosts marshal figure/annotation/trace observations. Rust owns figure-level
//! flag assembly, per-trace allowlist bits, axis key rows, and
//! [`scene_figure_support_pack`] envelope layout.

use crate::kernels::{
    scene_curve_classify, scene_dash_admit, scene_heatmap_colormap_admit,
    scene_hidden_or_per_item_admit, scene_hexbin_reduce_admit, scene_kind_admit,
    scene_linecap_admit, scene_marker_glyph_admit, scene_rect_extra_flags,
    scene_tick_label_strategy,
};
use crate::scene_pack_orchestrate::scene_figure_support_trace_dispatch_plan;
use crate::scene_figure_support_pack::{
    scene_figure_support_pack, FigureSupportAxisInput, FigureSupportTraceInput,
};
use crate::scene_pack_orchestrate::scene_figure_support_figure_plan;

pub use crate::scene_figure_support_pack::SCENE_FIGURE_SUPPORT_PACK_MAX
    as SCENE_FIGURE_SUPPORT_MATERIALIZE_MAX;

const OBS_POLAR: u32 = 1 << 0;
const OBS_CUSTOM_FONT: u32 = 1 << 1;
const OBS_BROWSER_CSS: u32 = 1 << 2;
const OBS_DATA_DRIVEN: u32 = 1 << 3;
const OBS_COLORBAR: u32 = 1 << 4;
const OBS_EXTRA_LEGENDS: u32 = 1 << 5;
const OBS_ANNOTATION_COLLISION: u32 = 1 << 6;
const OBS_ANNOTATION_TEXT: u32 = 1 << 7;
const OBS_ANNOTATION_HTML: u32 = 1 << 8;
const OBS_ANNOTATION_MARKUP: u32 = 1 << 9;

const TRACE_UNSUPPORTED_KIND: u16 = 1 << 0;
const TRACE_NON_PRIMARY_AXIS: u16 = 1 << 1;
const TRACE_HIDDEN_OR_PER_ITEM: u16 = 1 << 2;
const TRACE_DASHED_MARKERS: u16 = 1 << 4;
const TRACE_CUSTOM_HEX_REDUCE: u16 = 1 << 9;
const TRACE_HEATMAP_COLORMAP: u16 = 1 << 10;
const TRACE_NON_CSS_FILL: u16 = 1 << 11;

const POLAR_COLLISION_KEYS: &[&str] = &[
    "tick_label_strategy",
    "collision",
    "tick_label_min_gap",
    "tick_label_angle",
    "tick_label_anchor",
];

/// One annotation observation row.
#[derive(Clone, Copy, Debug, Default)]
pub struct FigureSupportAnnotationObs {
    pub has_html: i32,
    pub has_collision: i32,
    pub has_markup: i32,
    pub has_custom_typography: i32,
    pub has_class_name: i32,
    pub kind_is_supported_text: i32,
    pub has_text: i32,
}

/// One trace observation row for allowlist assembly.
#[derive(Clone, Debug, Default)]
pub struct FigureSupportTraceObs<'a> {
    pub kind: &'a str,
    pub x_axis: &'a str,
    pub y_axis: &'a str,
    pub hidden: i32,
    pub has_per_item_channels: i32,
    pub density_aggregates_color: i32,
    pub marker_glyph_present: i32,
    pub marker_glyph: Option<&'a str>,
    pub marker_path_present: i32,
    pub marker_path_valid: i32,
    pub marker_path_filled_small: i32,
    pub curve_present: i32,
    pub curve: Option<&'a str>,
    pub linecap_present: i32,
    pub linecap: Option<&'a str>,
    pub dash_present: i32,
    pub dash_text: Option<&'a str>,
    pub dash_is_array: i32,
    pub fill_present: i32,
    pub fill_is_string: i32,
    pub fill_gradient_admitted: i32,
    pub hexbin_reduce: Option<&'a str>,
    pub heatmap_truecolor: i32,
    pub heatmap_has_colormap: i32,
    pub heatmap_has_rgba_grid: i32,
    pub heatmap_has_rgba: i32,
    pub rect_gradient_fail: i32,
    pub corner_radius_values: &'a [f64],
    pub corner_radius_seq: i32,
    pub wedge_gap: f64,
    pub ribbon_color2_fail: i32,
    pub color_channel_unsupported: i32,
}

/// One axis option key row.
#[derive(Clone, Debug)]
pub struct FigureSupportAxisObs<'a> {
    pub axis_code: u8,
    pub keys: Vec<String>,
    pub tick_label_strategy: Option<&'a str>,
    pub collision: Option<&'a str>,
}

/// Host-marshaled figure support input.
#[derive(Clone, Debug)]
pub struct SceneFigureSupportMaterializeIn<'a> {
    pub polar: i32,
    pub colorbar_unsupported: i32,
    pub has_custom_font: i32,
    pub has_browser_css: i32,
    pub has_extra_legends: i32,
    pub annotations: &'a [FigureSupportAnnotationObs],
    pub axes: &'a [FigureSupportAxisObs<'a>],
    pub traces: &'a [FigureSupportTraceObs<'a>],
}

fn significant_axis_keys(axis: &FigureSupportAxisObs<'_>, polar: bool) -> Vec<String> {
    let mut keys = axis.keys.clone();
    if polar {
        let strategy = axis
            .tick_label_strategy
            .or(axis.collision)
            .unwrap_or("auto");
        let code = scene_tick_label_strategy(strategy);
        if matches!(code, 5 | 6 | 0) {
            keys.retain(|key| !POLAR_COLLISION_KEYS.contains(&key.as_str()));
        }
    }
    keys
}

fn trace_support_flags(trace: &FigureSupportTraceObs<'_>, polar: bool) -> Result<u16, i32> {
    let mut flags = 0u16;
    let mut dispatch = crate::scene_pack_orchestrate::FigureSupportTraceDispatchPlan {
        kind_class: 0,
        probe_marker_glyph: 0,
        probe_marker_path: 0,
        probe_curve_smooth: 0,
        probe_rect_extra: 0,
        probe_hexbin_reduce: 0,
        probe_heatmap_colormap: 0,
        probe_non_css_fill: 0,
    };
    if scene_figure_support_trace_dispatch_plan(
        trace.kind,
        trace.marker_glyph_present,
        trace.marker_path_present,
        trace.curve_present,
        trace.fill_present,
        &mut dispatch,
    ) == 0
    {
        return Err(-1);
    }
    if scene_kind_admit(trace.kind) == 0 {
        flags |= TRACE_UNSUPPORTED_KIND;
    }
    if trace.x_axis != "x" || trace.y_axis != "y" {
        flags |= TRACE_NON_PRIMARY_AXIS;
    }
    if scene_hidden_or_per_item_admit(
        trace.hidden,
        trace.has_per_item_channels,
        trace.density_aggregates_color,
    ) != 0
    {
        flags |= TRACE_HIDDEN_OR_PER_ITEM;
    }
    if dispatch.probe_marker_glyph != 0 {
        let glyph_ok = trace
            .marker_glyph
            .map(|g| scene_marker_glyph_admit(g) != 0)
            .unwrap_or(false);
        if trace.kind != "scatter" || trace.marker_path_present != 0 || !glyph_ok {
            flags |= TRACE_DASHED_MARKERS;
        }
    }
    if dispatch.probe_marker_path != 0 {
        if trace.kind != "scatter" {
            flags |= TRACE_DASHED_MARKERS;
        } else if trace.marker_path_valid == 0 || trace.marker_path_filled_small != 0 {
            flags |= TRACE_DASHED_MARKERS;
        }
    }
    if let Some(curve) = trace.curve {
        let curve_code = scene_curve_classify(curve);
        if curve_code == 1 {
            if dispatch.probe_curve_smooth == 0 {
                flags |= TRACE_DASHED_MARKERS;
            }
        } else if curve_code != 0 {
            flags |= TRACE_DASHED_MARKERS;
        }
    }
    if let Some(linecap) = trace.linecap {
        if scene_linecap_admit(linecap).is_none() {
            flags |= TRACE_DASHED_MARKERS;
        }
    }
    if trace.dash_present != 0 {
        let admit = if trace.dash_is_array != 0 {
            scene_dash_admit("", &[], true)
        } else {
            scene_dash_admit(trace.dash_text.unwrap_or(""), &[], false)
        };
        if admit.is_none() {
            flags |= TRACE_DASHED_MARKERS;
        }
    }
    if dispatch.probe_rect_extra != 0 {
        flags |= scene_rect_extra_flags(
            trace.kind,
            polar,
            trace.rect_gradient_fail != 0,
            trace.corner_radius_values,
            trace.corner_radius_seq != 0,
            trace.wedge_gap,
        ) as u16;
    }
    if dispatch.probe_hexbin_reduce != 0
        && scene_hexbin_reduce_admit(trace.hexbin_reduce.unwrap_or("")) == 0
    {
        flags |= TRACE_CUSTOM_HEX_REDUCE;
    }
    if dispatch.probe_heatmap_colormap != 0
        && scene_heatmap_colormap_admit(
            trace.heatmap_truecolor,
            trace.heatmap_has_colormap,
            trace.heatmap_has_rgba_grid,
            trace.heatmap_has_rgba,
        ) != 0
    {
        flags |= TRACE_HEATMAP_COLORMAP;
    }
    if dispatch.probe_non_css_fill != 0
        && trace.fill_is_string == 0
        && trace.fill_gradient_admitted == 0
    {
        flags |= TRACE_NON_CSS_FILL;
    }
    Ok(flags)
}

fn figure_level_flags(input: &SceneFigureSupportMaterializeIn<'_>) -> Result<u32, i32> {
    let mut flags = 0u32;
    let mut plan_polar = 0;
    if scene_figure_support_figure_plan(input.polar, &mut plan_polar) == 0 {
        return Err(-1);
    }
    if plan_polar != 0 {
        flags |= OBS_POLAR;
    }
    if input.has_custom_font != 0 {
        flags |= OBS_CUSTOM_FONT;
    }
    if input.has_browser_css != 0 {
        flags |= OBS_BROWSER_CSS;
    }
    if input.annotations.iter().any(|a| a.has_html != 0) {
        flags |= OBS_ANNOTATION_HTML;
    }
    if input.annotations.iter().any(|a| a.has_collision != 0) {
        flags |= OBS_ANNOTATION_COLLISION;
    }
    if input.annotations.iter().any(|a| a.has_markup != 0) {
        flags |= OBS_ANNOTATION_MARKUP;
    }
    let polar = plan_polar != 0;
    if input.traces.iter().any(|trace| {
        trace.ribbon_color2_fail != 0
            || trace.color_channel_unsupported != 0
            || (trace.fill_present != 0
                && trace.fill_is_string == 0
                && trace.fill_gradient_admitted == 0)
    }) {
        flags |= OBS_DATA_DRIVEN;
    }
    if input.colorbar_unsupported != 0 {
        flags |= OBS_COLORBAR;
    }
    if input.has_extra_legends != 0 {
        flags |= OBS_EXTRA_LEGENDS;
    }
    if input
        .annotations
        .iter()
        .any(|a| a.kind_is_supported_text == 0 && a.has_text != 0)
    {
        flags |= OBS_ANNOTATION_TEXT;
    }
    let _ = polar;
    Ok(flags)
}

/// Materialize XYFS v2 from host observations. Returns ``-1`` invalid args,
/// ``-2`` over cap.
pub fn scene_figure_support_materialize(
    input: &SceneFigureSupportMaterializeIn<'_>,
) -> Result<Vec<u8>, i32> {
    let flags = figure_level_flags(input)?;
    let polar = input.polar != 0;
    let mut axes = Vec::with_capacity(input.axes.len());
    for axis in input.axes {
        axes.push(FigureSupportAxisInput {
            axis_code: axis.axis_code,
            keys: significant_axis_keys(axis, polar),
        });
    }
    let mut traces = Vec::with_capacity(input.traces.len());
    for trace in input.traces {
        traces.push(FigureSupportTraceInput {
            trace_flags: trace_support_flags(trace, polar)?,
            kind: trace.kind.to_string(),
        });
    }
    scene_figure_support_pack(flags, &axes, &traces)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn materializes_minimal_xyfs() {
        let axes = [FigureSupportAxisObs {
            axis_code: 0,
            keys: vec!["label".to_string(), "side".to_string()],
            tick_label_strategy: None,
            collision: None,
        }];
        let traces = [FigureSupportTraceObs {
            kind: "scatter",
            x_axis: "x",
            y_axis: "y",
            ..Default::default()
        }];
        let input = SceneFigureSupportMaterializeIn {
            polar: 0,
            colorbar_unsupported: 0,
            has_custom_font: 0,
            has_browser_css: 0,
            has_extra_legends: 0,
            annotations: &[],
            axes: &axes,
            traces: &traces,
        };
        let packed = scene_figure_support_materialize(&input).unwrap();
        assert_eq!(&packed[..4], b"XYFS");
    }
}
