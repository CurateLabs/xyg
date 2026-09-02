//! Per-trace XYTC (XYTR) record packing (M2 big-push 2, ABI 317).
//!
//! Hosts marshal style literals and pre-packed marker/gradient blobs. Rust owns
//! dispatch orchestration, sub-kernel flag assembly, and XYTR prefix/payload
//! concat so Python/Node cannot drift on field-byte walks.

use crate::kernels::{
    scene_xytc_color2_flags_pack, scene_xytc_color_channel_pack, scene_xytc_dash_pattern_pack,
    scene_xytc_hex_pitch_pack, scene_xytc_meta_flags_pack, scene_xytc_numeric_style_pack,
    scene_xytc_opacity_pack, scene_xytc_paint_presence_pack, scene_xytc_radius_pack,
    scene_xytc_stroke_perimeter_pack, scene_xytc_symbol_int_pack, SCENE_KIND_CLASS_BAND,
    SCENE_KIND_CLASS_HEXBIN, SCENE_KIND_CLASS_HEATMAP, SCENE_KIND_CLASS_POLYFILL,
    SCENE_KIND_CLASS_RECT, SCENE_KIND_CLASS_RIBBON, SCENE_KIND_CLASS_SCATTER,
};
use crate::scene_pack_orchestrate::{scene_xytc_trace_dispatch_plan, XytcTraceDispatchPlan};
use crate::scene_trace_compile::{XYTR_MAGIC, XYTR_PREFIX_BYTES, XYTR_VERSION};

const SCENE_KIND_CLASS_OPACITY: i32 = SCENE_KIND_CLASS_BAND
    | SCENE_KIND_CLASS_RIBBON
    | SCENE_KIND_CLASS_RECT
    | SCENE_KIND_CLASS_HEATMAP
    | SCENE_KIND_CLASS_SCATTER
    | SCENE_KIND_CLASS_HEXBIN
    | SCENE_KIND_CLASS_POLYFILL;

pub const SCENE_XYTC_TRACE_PACK_MAX_RECORD: usize = 1 << 20;

/// Host-marshaled style literals for one XYTC trace row.
#[derive(Clone, Debug)]
pub struct XytcTraceStyleInput<'a> {
    pub symbol_is_int: i32,
    pub symbol_int: u16,
    pub symbol_b: &'a [u8],
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
    pub dash_b: &'a [u8],
    pub dash_pattern: &'a [f64],
    pub linecap_b: &'a [u8],
    pub step_b: &'a [u8],
    pub curve_b: &'a [u8],
    pub has_fill: i32,
    pub fill_kind: i32,
    pub fill_css: &'a [u8],
    pub fill_space: &'a [u8],
    pub fill_gradient_blob: &'a [u8],
    pub stroke_css: &'a [u8],
    pub line_color: &'a [u8],
    pub color_css: &'a [u8],
    pub color_ch_present: i32,
    pub color_ch_has_constant: i32,
    pub color_mode: &'a [u8],
    pub color_const: &'a [u8],
    pub radius_seq: i32,
    pub r0: f64,
    pub r1: f64,
    pub wedge_gap_raw: f64,
}

/// Host-marshaled trace facts for one XYTC row.
#[derive(Clone, Debug)]
pub struct XytcTracePackInput<'a> {
    pub show_legend: i32,
    pub kind: &'a str,
    pub has_name: i32,
    pub name: &'a [u8],
    pub marker_path_present: i32,
    pub use_density: i32,
    pub joined_fill: i32,
    pub marker_packed: i32,
    pub glyph_packed: i32,
    pub marker_blob: &'a [u8],
    pub color2_class: i32,
    pub color2_gradient_blob: &'a [u8],
    pub color2_gradient_packed: i32,
    pub style: XytcTraceStyleInput<'a>,
}

fn write_xytr_record(
    kind: &[u8],
    flags: u32,
    name: &[u8],
    symbol_b: &[u8],
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
    dash_b: &[u8],
    linecap_b: &[u8],
    step_b: &[u8],
    curve_b: &[u8],
    fill_css: &[u8],
    stroke_css: &[u8],
    line_color: &[u8],
    color_css: &[u8],
    color_mode: &[u8],
    color_const: &[u8],
    fill_space: &[u8],
    symbol_int: u16,
    dash_pattern: &[f64],
    marker_blob: &[u8],
    gradient_blob: &[u8],
    r_tip: f64,
    r_base: f64,
    wedge_gap: f32,
) -> Vec<u8> {
    let mut out = Vec::with_capacity(
        XYTR_PREFIX_BYTES
            + kind.len()
            + name.len()
            + symbol_b.len()
            + dash_b.len()
            + linecap_b.len()
            + step_b.len()
            + curve_b.len()
            + fill_css.len()
            + stroke_css.len()
            + line_color.len()
            + color_css.len()
            + color_mode.len()
            + color_const.len()
            + fill_space.len()
            + dash_pattern.len() * 8
            + marker_blob.len()
            + gradient_blob.len(),
    );
    let mut prefix = vec![0u8; XYTR_PREFIX_BYTES];
    prefix[..4].copy_from_slice(XYTR_MAGIC);
    prefix[4..6].copy_from_slice(&XYTR_VERSION.to_le_bytes());
    prefix[6..8].copy_from_slice(&(kind.len() as u16).to_le_bytes());
    prefix[8..12].copy_from_slice(&flags.to_le_bytes());
    prefix[12..14].copy_from_slice(&(name.len() as u16).to_le_bytes());
    prefix[14..16].copy_from_slice(&(symbol_b.len() as u16).to_le_bytes());
    prefix[16..24].copy_from_slice(&opacity.to_le_bytes());
    prefix[24..32].copy_from_slice(&fill_opacity.to_le_bytes());
    prefix[32..40].copy_from_slice(&stroke_opacity.to_le_bytes());
    prefix[40..48].copy_from_slice(&line_opacity.to_le_bytes());
    prefix[48..56].copy_from_slice(&size.to_le_bytes());
    prefix[56..64].copy_from_slice(&size_ch.to_le_bytes());
    prefix[64..72].copy_from_slice(&stroke_width.to_le_bytes());
    prefix[72..80].copy_from_slice(&width.to_le_bytes());
    prefix[80..88].copy_from_slice(&line_width.to_le_bytes());
    prefix[88..96].copy_from_slice(&hex_dx.to_le_bytes());
    prefix[96..104].copy_from_slice(&hex_dy.to_le_bytes());
    prefix[104..106].copy_from_slice(&(dash_b.len() as u16).to_le_bytes());
    prefix[106..108].copy_from_slice(&(linecap_b.len() as u16).to_le_bytes());
    prefix[108..110].copy_from_slice(&(step_b.len() as u16).to_le_bytes());
    prefix[110..112].copy_from_slice(&(curve_b.len() as u16).to_le_bytes());
    prefix[112..114].copy_from_slice(&(fill_css.len() as u16).to_le_bytes());
    prefix[114..116].copy_from_slice(&(stroke_css.len() as u16).to_le_bytes());
    prefix[116..118].copy_from_slice(&(line_color.len() as u16).to_le_bytes());
    prefix[118..120].copy_from_slice(&(color_css.len() as u16).to_le_bytes());
    prefix[120..122].copy_from_slice(&(color_mode.len() as u16).to_le_bytes());
    prefix[122..124].copy_from_slice(&(color_const.len() as u16).to_le_bytes());
    prefix[124..126].copy_from_slice(&(fill_space.len() as u16).to_le_bytes());
    prefix[126..128].copy_from_slice(&symbol_int.to_le_bytes());
    prefix[128..132].copy_from_slice(&(dash_pattern.len() as u32).to_le_bytes());
    prefix[132..136].copy_from_slice(&(marker_blob.len() as u32).to_le_bytes());
    prefix[136..140].copy_from_slice(&(gradient_blob.len() as u32).to_le_bytes());
    prefix[140..148].copy_from_slice(&r_tip.to_le_bytes());
    prefix[148..156].copy_from_slice(&r_base.to_le_bytes());
    prefix[156..160].copy_from_slice(&wedge_gap.to_le_bytes());
    out.extend_from_slice(&prefix);
    out.extend_from_slice(kind);
    out.extend_from_slice(name);
    out.extend_from_slice(symbol_b);
    out.extend_from_slice(dash_b);
    out.extend_from_slice(linecap_b);
    out.extend_from_slice(step_b);
    out.extend_from_slice(curve_b);
    out.extend_from_slice(fill_css);
    out.extend_from_slice(stroke_css);
    out.extend_from_slice(line_color);
    out.extend_from_slice(color_css);
    out.extend_from_slice(color_mode);
    out.extend_from_slice(color_const);
    out.extend_from_slice(fill_space);
    for value in dash_pattern {
        out.extend_from_slice(&value.to_le_bytes());
    }
    out.extend_from_slice(marker_blob);
    out.extend_from_slice(gradient_blob);
    out
}

/// Pack one authored XYTR v1 record. Returns ``-1`` on invalid args.
pub fn scene_xytc_trace_pack(input: &XytcTracePackInput<'_>) -> Result<Vec<u8>, i32> {
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
    let style = &input.style;
    let kind_bytes = input.kind.as_bytes();
    let mut flags = scene_xytc_symbol_int_pack(style.symbol_is_int).ok_or(-1)?;
    let opacity_kind_class = if dispatch.pack_opacity != 0 {
        dispatch.kind_class
    } else {
        0
    };
    let (fill_opacity, stroke_opacity, line_opacity) = scene_xytc_opacity_pack(
        i32::from(opacity_kind_class & SCENE_KIND_CLASS_OPACITY != 0),
        i32::from(opacity_kind_class & SCENE_KIND_CLASS_BAND != 0),
        style.fill_opacity,
        style.stroke_opacity,
        style.line_opacity,
    )
    .ok_or(-1)?;
    let numeric = scene_xytc_numeric_style_pack(
        style.has_size,
        style.has_size_ch,
        style.has_size_ch_constant,
        style.has_stroke_width,
        style.has_width,
        style.has_line_width,
        style.size,
        style.size_ch_constant,
        style.stroke_width,
        style.width,
        style.line_width,
    )
    .ok_or(-1)?;
    flags |= numeric.flags;
    let mut hex_dx = f64::NAN;
    let mut hex_dy = f64::NAN;
    if dispatch.pack_hex_pitch != 0 {
        let (hex_flags, dx, dy) = scene_xytc_hex_pitch_pack(
            1,
            style.has_hex_dx,
            style.has_hex_dy,
            style.hex_dx,
            style.hex_dy,
        )
        .ok_or(-1)?;
        flags |= hex_flags;
        hex_dx = dx;
        hex_dy = dy;
    }
    if dispatch.pack_stroke_perimeter != 0 {
        flags |= scene_xytc_stroke_perimeter_pack(
            1,
            style.has_stroke_perimeter,
            style.stroke_perimeter_is_bool,
            style.stroke_perimeter_true,
        )
        .ok_or(-1)?;
    }
    flags |= scene_xytc_dash_pattern_pack(style.dash_is_array).ok_or(-1)?;
    flags |= scene_xytc_paint_presence_pack(
        style.has_fill,
        style.fill_kind,
        style.has_stroke,
        style.has_line_color,
    )
    .ok_or(-1)?;
    if style.color_ch_present != 0 {
        flags |= scene_xytc_color_channel_pack(1, style.color_ch_has_constant).ok_or(-1)?;
    }
    let mut gradient_blob = style.fill_gradient_blob.to_vec();
    if dispatch.pack_color2 != 0 {
        if input.color2_gradient_packed != 0 {
            gradient_blob = input.color2_gradient_blob.to_vec();
        }
        flags |= scene_xytc_color2_flags_pack(
            input.color2_class,
            flags,
            input.color2_gradient_packed,
        )
        .ok_or(-1)?;
    }
    flags |= scene_xytc_meta_flags_pack(
        input.has_name,
        input.show_legend,
        input.kind,
        input.use_density,
        input.joined_fill,
        input.marker_path_present,
        input.marker_packed,
        input.glyph_packed,
    )
    .ok_or(-1)?;
    let mut r_tip = 0.0;
    let mut r_base = 0.0;
    let mut wedge_gap = 0.0f32;
    if dispatch.pack_radius != 0 {
        let (radius_flags, tip, base, gap) = scene_xytc_radius_pack(
            input.kind,
            style.radius_seq,
            style.r0,
            style.r1,
            style.wedge_gap_raw,
        )
        .ok_or(-1)?;
        flags |= radius_flags;
        r_tip = tip;
        r_base = base;
        wedge_gap = gap as f32;
    }
    let record = write_xytr_record(
        kind_bytes,
        flags,
        input.name,
        style.symbol_b,
        style.opacity,
        fill_opacity,
        stroke_opacity,
        line_opacity,
        numeric.size,
        numeric.size_ch_value,
        numeric.stroke_width,
        numeric.width,
        numeric.line_width,
        hex_dx,
        hex_dy,
        style.dash_b,
        style.linecap_b,
        style.step_b,
        style.curve_b,
        style.fill_css,
        style.stroke_css,
        style.line_color,
        style.color_css,
        style.color_mode,
        style.color_const,
        style.fill_space,
        style.symbol_int,
        style.dash_pattern,
        input.marker_blob,
        &gradient_blob,
        r_tip,
        r_base,
        wedge_gap,
    );
    if record.len() > SCENE_XYTC_TRACE_PACK_MAX_RECORD {
        return Err(-1);
    }
    Ok(record)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn scatter_style<'a>() -> XytcTraceStyleInput<'a> {
        XytcTraceStyleInput {
            symbol_is_int: 0,
            symbol_int: 0,
            symbol_b: b"circle",
            opacity: 1.0,
            fill_opacity: 1.0,
            stroke_opacity: 1.0,
            line_opacity: 1.0,
            has_stroke: 0,
            has_line_color: 0,
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
            dash_is_array: 0,
            dash_b: b"",
            dash_pattern: &[],
            linecap_b: b"",
            step_b: b"",
            curve_b: b"",
            has_fill: 0,
            fill_kind: 0,
            fill_css: b"",
            fill_space: b"",
            fill_gradient_blob: b"",
            stroke_css: b"",
            line_color: b"",
            color_css: b"",
            color_ch_present: 0,
            color_ch_has_constant: 0,
            color_mode: b"",
            color_const: b"",
            radius_seq: 1,
            r0: 0.0,
            r1: 0.0,
            wedge_gap_raw: 0.0,
        }
    }

    #[test]
    fn scatter_default_record_has_xytr_magic() {
        let style = scatter_style();
        let input = XytcTracePackInput {
            show_legend: 1,
            kind: "scatter",
            has_name: 0,
            name: b"",
            marker_path_present: 0,
            use_density: 0,
            joined_fill: 0,
            marker_packed: 0,
            glyph_packed: 0,
            marker_blob: b"",
            color2_class: 0,
            color2_gradient_blob: b"",
            color2_gradient_packed: 0,
            style,
        };
        let record = scene_xytc_trace_pack(&input).unwrap();
        assert_eq!(&record[..4], XYTR_MAGIC);
    }
}
