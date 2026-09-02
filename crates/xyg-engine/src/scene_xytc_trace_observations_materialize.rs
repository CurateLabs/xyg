//! XYTC trace observation materialize (M2 big-push 2 completion, ABI 325).
//!
//! Hosts marshal trace kind, style literals, and raw fill/dash/marker/ribbon
//! observations. Rust owns field-byte walks previously in Python
//! `_marshal_xytc_trace_record` and Node `marshalXyTcTraceRecord`.

use crate::kernels::{
    scene_gradient_spec_pack, scene_marker_blob_pack, scene_marker_glyph_admit,
    scene_ribbon_color2_classify, scene_xytc_paint_presence_pack,
    SCENE_RIBBON_COLOR2_GRADIENT,
};
use crate::scene_pack_orchestrate::{scene_xytc_trace_dispatch_plan, XytcTraceDispatchPlan};
use crate::scene_xytc_trace_pack::{XytcTracePackInput, XytcTraceStyleInput};

pub const SCENE_XYTC_TRACE_OBSERVATIONS_MAX_BYTES: usize = 1 << 20;

const XYTC_HAS_FILL: u32 = 1 << 0;
const XYTC_HAS_GRADIENT_SPEC: u32 = 1 << 19;

/// One gradient stop observation (position + CSS string).
#[derive(Clone, Debug)]
pub struct SceneXytcGradientStopIn<'a> {
    pub t: f64,
    pub css: &'a str,
}

/// Host-marshaled trace/style observations for XYTC materialize.
#[derive(Clone, Debug)]
pub struct SceneXytcTraceObservationsIn<'a> {
    pub show_legend: i32,
    pub kind: &'a str,
    pub has_name: i32,
    pub name: &'a str,
    pub marker_path_present: i32,
    pub use_density: i32,
    pub joined_fill: i32,
    pub symbol_is_int: i32,
    pub symbol_int: u16,
    pub symbol_text: Option<&'a str>,
    pub opacity: f64,
    pub fill_opacity: f64,
    pub stroke_opacity: f64,
    pub line_opacity: f64,
    pub has_stroke: i32,
    pub stroke_css: Option<&'a str>,
    pub has_line_color: i32,
    pub line_color: Option<&'a str>,
    pub has_color: i32,
    pub color_css: Option<&'a str>,
    pub has_size: i32,
    pub size: f64,
    pub has_size_ch: i32,
    pub has_size_ch_constant: i32,
    pub size_ch_constant: f64,
    pub has_stroke_width: i32,
    pub stroke_width: f64,
    pub has_width: i32,
    pub width: f64,
    pub has_line_width: i32,
    pub line_width: f64,
    pub has_hex_dx: i32,
    pub hex_dx: f64,
    pub has_hex_dy: i32,
    pub hex_dy: f64,
    pub has_stroke_perimeter: i32,
    pub stroke_perimeter_is_bool: i32,
    pub stroke_perimeter_true: i32,
    pub wedge_gap_raw: f64,
    pub dash_is_array: i32,
    pub dash_text: Option<&'a str>,
    pub dash_values: &'a [f64],
    pub has_fill: i32,
    pub fill_is_string: i32,
    pub fill_string: Option<&'a str>,
    pub fill_has_full_spec: i32,
    pub fill_space: Option<&'a str>,
    pub fill_dir: Option<&'a str>,
    pub fill_stops: &'a [SceneXytcGradientStopIn<'a>],
    pub fill_dict_gradient: Option<&'a str>,
    pub fill_dict_space: Option<&'a str>,
    pub marker_path_filled: i32,
    pub marker_contour_values: &'a [f64],
    pub marker_contour_lens: &'a [u32],
    pub marker_glyph: Option<&'a str>,
    pub has_color2: i32,
    pub kind_is_ribbon: i32,
    pub color2_source_const: Option<&'a str>,
    pub color2_target_const: Option<&'a str>,
    pub source_paint: &'a str,
    pub has_end_pair: i32,
    pub corner_radius_seq: i32,
    pub corner_radius_r0: f64,
    pub corner_radius_r1: f64,
    pub color_ch_present: i32,
    pub color_ch_has_constant: i32,
    pub color_ch_mode: Option<&'a str>,
    pub color_ch_constant: Option<&'a str>,
    pub linecap: Option<&'a str>,
    pub step: Option<&'a str>,
    pub curve: Option<&'a str>,
}

/// Materialized pack inputs for [`scene_xytc_trace_pack`].
#[derive(Clone, Debug, Default)]
pub struct SceneXytcTraceObservationsOut {
    pub show_legend: i32,
    pub kind: Vec<u8>,
    pub has_name: i32,
    pub name: Vec<u8>,
    pub marker_path_present: i32,
    pub use_density: i32,
    pub joined_fill: i32,
    pub marker_packed: i32,
    pub glyph_packed: i32,
    pub marker_blob: Vec<u8>,
    pub color2_class: i32,
    pub color2_gradient_blob: Vec<u8>,
    pub color2_gradient_packed: i32,
    pub symbol_is_int: i32,
    pub symbol_int: u16,
    pub symbol_b: Vec<u8>,
    pub opacity: f64,
    pub fill_opacity: f64,
    pub stroke_opacity: f64,
    pub line_opacity: f64,
    pub has_stroke: i32,
    pub has_line_color: i32,
    pub has_size: i32,
    pub size: f64,
    pub has_size_ch: i32,
    pub has_size_ch_constant: i32,
    pub size_ch_constant: f64,
    pub has_stroke_width: i32,
    pub stroke_width: f64,
    pub has_width: i32,
    pub width: f64,
    pub has_line_width: i32,
    pub line_width: f64,
    pub has_hex_dx: i32,
    pub hex_dx: f64,
    pub has_hex_dy: i32,
    pub hex_dy: f64,
    pub has_stroke_perimeter: i32,
    pub stroke_perimeter_is_bool: i32,
    pub stroke_perimeter_true: i32,
    pub dash_is_array: i32,
    pub dash_b: Vec<u8>,
    pub dash_pattern: Vec<f64>,
    pub linecap_b: Vec<u8>,
    pub step_b: Vec<u8>,
    pub curve_b: Vec<u8>,
    pub has_fill: i32,
    pub fill_kind: i32,
    pub fill_css: Vec<u8>,
    pub fill_space: Vec<u8>,
    pub fill_gradient_blob: Vec<u8>,
    pub stroke_css: Vec<u8>,
    pub line_color_b: Vec<u8>,
    pub color_css: Vec<u8>,
    pub color_ch_present: i32,
    pub color_ch_has_constant: i32,
    pub color_mode: Vec<u8>,
    pub color_const: Vec<u8>,
    pub radius_seq: i32,
    pub r0: f64,
    pub r1: f64,
    pub wedge_gap_raw: f64,
}

fn xytc_fill_kind(input: &SceneXytcTraceObservationsIn<'_>) -> i32 {
    if input.has_fill == 0 {
        return 0;
    }
    if input.fill_is_string != 0 {
        return 1;
    }
    if input.fill_has_full_spec != 0 {
        return 2;
    }
    3
}

fn pack_gradient_spec(
    space: Option<&str>,
    dir: Option<&str>,
    stops: &[SceneXytcGradientStopIn<'_>],
) -> Option<Vec<u8>> {
    if stops.is_empty() {
        return None;
    }
    let mut stop_t = Vec::with_capacity(stops.len());
    let mut css = Vec::new();
    let mut css_lens = Vec::with_capacity(stops.len());
    for stop in stops {
        stop_t.push(stop.t);
        let bytes = stop.css.as_bytes();
        css_lens.push(u32::try_from(bytes.len()).ok()?);
        css.extend_from_slice(bytes);
    }
    let mut out = vec![0u8; 4 + stops.len() * 10 + css.len()];
    let written = scene_gradient_spec_pack(
        space.unwrap_or(""),
        dir.unwrap_or(""),
        &stop_t,
        &css,
        &css_lens,
        &mut out,
    );
    if written <= 0 {
        return None;
    }
    out.truncate(written as usize);
    Some(out)
}

fn materialize_fill(input: &SceneXytcTraceObservationsIn<'_>) -> (i32, Vec<u8>, Vec<u8>, Vec<u8>) {
    let fill_kind = xytc_fill_kind(input);
    if input.has_fill == 0 {
        return (fill_kind, Vec::new(), Vec::new(), Vec::new());
    }
    if input.fill_is_string != 0 {
        return (
            fill_kind,
            input.fill_string.unwrap_or("").as_bytes().to_vec(),
            Vec::new(),
            Vec::new(),
        );
    }
    if input.fill_has_full_spec != 0 {
        let blob = pack_gradient_spec(input.fill_space, input.fill_dir, input.fill_stops)
            .unwrap_or_default();
        return (fill_kind, Vec::new(), Vec::new(), blob);
    }
    let fill_css = input.fill_dict_gradient.unwrap_or("").as_bytes().to_vec();
    let fill_space = input
        .fill_dict_space
        .unwrap_or("mark")
        .as_bytes()
        .to_vec();
    (fill_kind, fill_css, fill_space, Vec::new())
}

fn materialize_dash(input: &SceneXytcTraceObservationsIn<'_>) -> (i32, Vec<u8>, Vec<f64>) {
    if input.dash_is_array != 0 {
        return (1, Vec::new(), input.dash_values.to_vec());
    }
    (
        0,
        input.dash_text.unwrap_or("").as_bytes().to_vec(),
        Vec::new(),
    )
}

fn materialize_marker(
    dispatch: &XytcTraceDispatchPlan,
    input: &SceneXytcTraceObservationsIn<'_>,
) -> (i32, i32, Vec<u8>) {
    if dispatch.marker_path_branch != 0 {
        let mut out = vec![0u8; 8 + input.marker_contour_values.len() * 8 + input.marker_contour_lens.len() * 4];
        let written = scene_marker_blob_pack(
            input.marker_path_filled,
            input.marker_contour_values,
            input.marker_contour_lens,
            &mut out,
        );
        if written > 0 {
            out.truncate(written as usize);
            return (1, 0, out);
        }
        return (0, 0, Vec::new());
    }
    if dispatch.marker_glyph_branch != 0 {
        if let Some(glyph) = input.marker_glyph {
            if scene_marker_glyph_admit(glyph) != 0 {
                return (0, 1, glyph.as_bytes().to_vec());
            }
        }
    }
    (0, 0, Vec::new())
}

fn materialize_color2(
    dispatch: &XytcTraceDispatchPlan,
    input: &SceneXytcTraceObservationsIn<'_>,
    fill_kind: i32,
) -> (i32, i32, Vec<u8>) {
    let color2_class = scene_ribbon_color2_classify(
        input.has_color2 != 0,
        input.kind_is_ribbon != 0,
        optional_css(input.color2_source_const),
        optional_css(input.color2_target_const),
        input.source_paint,
        input.has_fill != 0,
        input.has_end_pair != 0,
    );
    if dispatch.pack_color2 == 0 {
        return (color2_class, 0, Vec::new());
    }
    let paint_flags = scene_xytc_paint_presence_pack(
        input.has_fill,
        fill_kind,
        input.has_stroke,
        input.has_line_color,
    )
    .unwrap_or(0);
    let color2_target = optional_css(input.color2_target_const);
    if color2_class != SCENE_RIBBON_COLOR2_GRADIENT {
        return (color2_class, 0, Vec::new());
    }
    if paint_flags & (XYTC_HAS_FILL | XYTC_HAS_GRADIENT_SPEC) != 0 {
        return (color2_class, 0, Vec::new());
    }
    let Some(target) = color2_target else {
        return (color2_class, 0, Vec::new());
    };
    let stops = [
        SceneXytcGradientStopIn {
            t: 0.0,
            css: input.source_paint,
        },
        SceneXytcGradientStopIn { t: 1.0, css: target },
    ];
    if let Some(blob) = pack_gradient_spec(Some("mark"), Some("right"), &stops) {
        if !blob.is_empty() {
            return (color2_class, 1, blob);
        }
    }
    (color2_class, 0, Vec::new())
}

fn optional_css(text: Option<&str>) -> Option<&str> {
    text.filter(|value| !value.is_empty())
}

fn materialize_symbol(input: &SceneXytcTraceObservationsIn<'_>) -> (i32, u16, Vec<u8>) {
    if input.symbol_is_int != 0 {
        return (1, input.symbol_int, Vec::new());
    }
    let text = input.symbol_text.unwrap_or("circle");
    (0, 0, text.as_bytes().to_vec())
}

fn optional_bytes(text: Option<&str>) -> Vec<u8> {
    text.map(|value| value.as_bytes().to_vec())
        .unwrap_or_default()
}

pub fn scene_xytc_trace_observations_materialize(
    input: &SceneXytcTraceObservationsIn<'_>,
) -> Result<SceneXytcTraceObservationsOut, i32> {
    let mut dispatch = XytcTraceDispatchPlan {
        kind_class: 0,
        pack_opacity: 0,
        pack_hex_pitch: 0,
        pack_stroke_perimeter: 0,
        pack_color2: 0,
        pack_radius: 0,
        marker_path_branch: 0,
        marker_glyph_branch: 0,
        meta_use_density: 0,
        meta_joined_fill: 0,
    };
    if scene_xytc_trace_dispatch_plan(
        input.kind,
        input.marker_path_present,
        input.use_density,
        input.joined_fill,
        &mut dispatch,
    ) == 0
    {
        return Err(-1);
    }
    let (fill_kind, fill_css, fill_space, fill_gradient_blob) = materialize_fill(input);
    let (dash_is_array, dash_b, dash_pattern) = materialize_dash(input);
    let (marker_packed, glyph_packed, marker_blob) = materialize_marker(&dispatch, input);
    let (color2_class, color2_gradient_packed, color2_gradient_blob) =
        materialize_color2(&dispatch, input, fill_kind);
    let (symbol_is_int, symbol_int, symbol_b) = materialize_symbol(input);

    let out = SceneXytcTraceObservationsOut {
        show_legend: input.show_legend,
        kind: input.kind.as_bytes().to_vec(),
        has_name: input.has_name,
        name: input.name.as_bytes().to_vec(),
        marker_path_present: input.marker_path_present,
        use_density: input.use_density,
        joined_fill: input.joined_fill,
        marker_packed,
        glyph_packed,
        marker_blob,
        color2_class,
        color2_gradient_blob,
        color2_gradient_packed,
        symbol_is_int,
        symbol_int,
        symbol_b,
        opacity: input.opacity,
        fill_opacity: input.fill_opacity,
        stroke_opacity: input.stroke_opacity,
        line_opacity: input.line_opacity,
        has_stroke: input.has_stroke,
        has_line_color: input.has_line_color,
        has_size: input.has_size,
        size: input.size,
        has_size_ch: input.has_size_ch,
        has_size_ch_constant: input.has_size_ch_constant,
        size_ch_constant: input.size_ch_constant,
        has_stroke_width: input.has_stroke_width,
        stroke_width: input.stroke_width,
        has_width: input.has_width,
        width: input.width,
        has_line_width: input.has_line_width,
        line_width: input.line_width,
        has_hex_dx: input.has_hex_dx,
        hex_dx: input.hex_dx,
        has_hex_dy: input.has_hex_dy,
        hex_dy: input.hex_dy,
        has_stroke_perimeter: input.has_stroke_perimeter,
        stroke_perimeter_is_bool: input.stroke_perimeter_is_bool,
        stroke_perimeter_true: input.stroke_perimeter_true,
        dash_is_array,
        dash_b,
        dash_pattern,
        linecap_b: optional_bytes(input.linecap),
        step_b: optional_bytes(input.step),
        curve_b: optional_bytes(input.curve),
        has_fill: input.has_fill,
        fill_kind,
        fill_css,
        fill_space,
        fill_gradient_blob,
        stroke_css: optional_bytes(input.stroke_css),
        line_color_b: optional_bytes(input.line_color),
        color_css: optional_bytes(input.color_css),
        color_ch_present: input.color_ch_present,
        color_ch_has_constant: input.color_ch_has_constant,
        color_mode: optional_bytes(input.color_ch_mode),
        color_const: optional_bytes(input.color_ch_constant),
        radius_seq: input.corner_radius_seq,
        r0: input.corner_radius_r0,
        r1: input.corner_radius_r1,
        wedge_gap_raw: input.wedge_gap_raw,
    };
    let total = out.kind.len()
        + out.name.len()
        + out.marker_blob.len()
        + out.color2_gradient_blob.len()
        + out.symbol_b.len()
        + out.dash_b.len()
        + out.dash_pattern.len() * 8
        + out.linecap_b.len()
        + out.step_b.len()
        + out.curve_b.len()
        + out.fill_css.len()
        + out.fill_space.len()
        + out.fill_gradient_blob.len()
        + out.stroke_css.len()
        + out.line_color_b.len()
        + out.color_css.len()
        + out.color_mode.len()
        + out.color_const.len();
    if total > SCENE_XYTC_TRACE_OBSERVATIONS_MAX_BYTES {
        return Err(-1);
    }
    Ok(out)
}

impl SceneXytcTraceObservationsOut {
    pub fn pack_input<'a>(&'a self) -> XytcTracePackInput<'a> {
        XytcTracePackInput {
            show_legend: self.show_legend,
            kind: std::str::from_utf8(&self.kind).unwrap_or(""),
            has_name: self.has_name,
            name: &self.name,
            marker_path_present: self.marker_path_present,
            use_density: self.use_density,
            joined_fill: self.joined_fill,
            marker_packed: self.marker_packed,
            glyph_packed: self.glyph_packed,
            marker_blob: &self.marker_blob,
            color2_class: self.color2_class,
            color2_gradient_blob: &self.color2_gradient_blob,
            color2_gradient_packed: self.color2_gradient_packed,
            style: XytcTraceStyleInput {
                symbol_is_int: self.symbol_is_int,
                symbol_int: self.symbol_int,
                symbol_b: &self.symbol_b,
                opacity: self.opacity,
                fill_opacity: self.fill_opacity,
                stroke_opacity: self.stroke_opacity,
                line_opacity: self.line_opacity,
                has_stroke: self.has_stroke,
                has_line_color: self.has_line_color,
                has_size: self.has_size,
                size: self.size,
                has_size_ch: self.has_size_ch,
                has_size_ch_constant: self.has_size_ch_constant,
                size_ch_constant: self.size_ch_constant,
                has_stroke_width: self.has_stroke_width,
                stroke_width: self.stroke_width,
                has_width: self.has_width,
                width: self.width,
                has_line_width: self.has_line_width,
                line_width: self.line_width,
                has_hex_dx: self.has_hex_dx,
                hex_dx: self.hex_dx,
                has_hex_dy: self.has_hex_dy,
                hex_dy: self.hex_dy,
                has_stroke_perimeter: self.has_stroke_perimeter,
                stroke_perimeter_is_bool: self.stroke_perimeter_is_bool,
                stroke_perimeter_true: self.stroke_perimeter_true,
                dash_is_array: self.dash_is_array,
                dash_b: &self.dash_b,
                dash_pattern: &self.dash_pattern,
                linecap_b: &self.linecap_b,
                step_b: &self.step_b,
                curve_b: &self.curve_b,
                has_fill: self.has_fill,
                fill_kind: self.fill_kind,
                fill_css: &self.fill_css,
                fill_space: &self.fill_space,
                fill_gradient_blob: &self.fill_gradient_blob,
                stroke_css: &self.stroke_css,
                line_color: &self.line_color_b,
                color_css: &self.color_css,
                color_ch_present: self.color_ch_present,
                color_ch_has_constant: self.color_ch_has_constant,
                color_mode: &self.color_mode,
                color_const: &self.color_const,
                radius_seq: self.radius_seq,
                r0: self.r0,
                r1: self.r1,
                wedge_gap_raw: self.wedge_gap_raw,
            },
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::scene_xytc_trace_pack::scene_xytc_trace_pack;

    fn minimal_input<'a>(kind: &'a str) -> SceneXytcTraceObservationsIn<'a> {
        SceneXytcTraceObservationsIn {
            show_legend: 1,
            kind,
            has_name: 0,
            name: "",
            marker_path_present: 0,
            use_density: 0,
            joined_fill: 0,
            symbol_is_int: 0,
            symbol_int: 0,
            symbol_text: Some("circle"),
            opacity: 1.0,
            fill_opacity: 1.0,
            stroke_opacity: 1.0,
            line_opacity: 1.0,
            has_stroke: 0,
            stroke_css: None,
            has_line_color: 0,
            line_color: None,
            has_color: 0,
            color_css: None,
            has_size: 0,
            size: f64::NAN,
            has_size_ch: 0,
            has_size_ch_constant: 0,
            size_ch_constant: f64::NAN,
            has_stroke_width: 0,
            stroke_width: 0.0,
            has_width: 0,
            width: 0.0,
            has_line_width: 0,
            line_width: 0.0,
            has_hex_dx: 0,
            hex_dx: f64::NAN,
            has_hex_dy: 0,
            hex_dy: f64::NAN,
            has_stroke_perimeter: 0,
            stroke_perimeter_is_bool: 0,
            stroke_perimeter_true: 0,
            wedge_gap_raw: 0.0,
            dash_is_array: 0,
            dash_text: None,
            dash_values: &[],
            has_fill: 0,
            fill_is_string: 0,
            fill_string: None,
            fill_has_full_spec: 0,
            fill_space: None,
            fill_dir: None,
            fill_stops: &[],
            fill_dict_gradient: None,
            fill_dict_space: None,
            marker_path_filled: 1,
            marker_contour_values: &[],
            marker_contour_lens: &[],
            marker_glyph: None,
            has_color2: 0,
            kind_is_ribbon: 0,
            color2_source_const: None,
            color2_target_const: None,
            source_paint: "#3987e5",
            has_end_pair: 0,
            corner_radius_seq: 1,
            corner_radius_r0: 0.0,
            corner_radius_r1: 0.0,
            color_ch_present: 0,
            color_ch_has_constant: 0,
            color_ch_mode: None,
            color_ch_constant: None,
            linecap: None,
            step: None,
            curve: None,
        }
    }

    #[test]
    fn scatter_default_materializes_to_valid_xytr_record() {
        let input = minimal_input("scatter");
        let materialized = scene_xytc_trace_observations_materialize(&input).unwrap();
        let record = scene_xytc_trace_pack(&materialized.pack_input()).unwrap();
        assert_eq!(&record[..4], b"XYTR");
    }

    #[test]
    fn ribbon_gradient_color2_materializes_gradient_blob() {
        let input = SceneXytcTraceObservationsIn {
            kind: "ribbon",
            kind_is_ribbon: 1,
            has_color2: 1,
            color2_source_const: Some("#336699"),
            color2_target_const: Some("#34d399"),
            source_paint: "#336699",
            ..minimal_input("ribbon")
        };
        let materialized = scene_xytc_trace_observations_materialize(&input).unwrap();
        assert_eq!(materialized.color2_class, SCENE_RIBBON_COLOR2_GRADIENT);
        assert_eq!(materialized.color2_gradient_packed, 1);
        assert!(!materialized.color2_gradient_blob.is_empty());
    }

    #[test]
    fn fill_gradient_spec_materializes_blob() {
        let stops = [
            SceneXytcGradientStopIn {
                t: 0.0,
                css: "#ff0000",
            },
            SceneXytcGradientStopIn {
                t: 1.0,
                css: "#0000ff",
            },
        ];
        let input = SceneXytcTraceObservationsIn {
            has_fill: 1,
            fill_has_full_spec: 1,
            fill_space: Some("mark"),
            fill_dir: Some("right"),
            fill_stops: &stops,
            ..minimal_input("area")
        };
        let materialized = scene_xytc_trace_observations_materialize(&input).unwrap();
        assert_eq!(materialized.fill_kind, 2);
        assert!(!materialized.fill_gradient_blob.is_empty());
    }
}
