//! Scene pack orchestration (M2 #733).
//!
//! Hosts still ship XYTC/XYTA buffers and coerce style literals. Rust owns
//! figure-level attach orchestration and per-trace XYTC/XYTA pack dispatch
//! routing so Python ``_pack_xytc`` / ``_pack_xyta`` and Node ``packXyTc`` /
//! ``packXyTa`` cannot drift on kind-class gates or sidecar branches.

use crate::kernels::{
    scene_kind_class, SCENE_KIND_CLASS_BAND, SCENE_KIND_CLASS_HEXBIN,
    SCENE_KIND_CLASS_HEATMAP, SCENE_KIND_CLASS_LINE, SCENE_KIND_CLASS_POLYFILL,
    SCENE_KIND_CLASS_RECT, SCENE_KIND_CLASS_RIBBON, SCENE_KIND_CLASS_SCATTER,
    SCENE_RIBBON_COLOR2_ENDS,
};

const SCENE_KIND_CLASS_OPACITY: i32 = SCENE_KIND_CLASS_BAND
    | SCENE_KIND_CLASS_RIBBON
    | SCENE_KIND_CLASS_RECT
    | SCENE_KIND_CLASS_HEATMAP
    | SCENE_KIND_CLASS_SCATTER
    | SCENE_KIND_CLASS_HEXBIN
    | SCENE_KIND_CLASS_POLYFILL;

fn scene_rect_kind_admits_radius(kind: &str) -> bool {
    matches!(
        kind,
        "bar" | "column" | "histogram" | "heatmap" | "violin" | "box"
    )
}

fn scene_rect_kind_admits_polar_wedge(kind: &str) -> bool {
    matches!(kind, "bar" | "column" | "histogram")
}

/// Resolved per-trace XYTC pack dispatch from product kind and host facts.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct XytcTraceDispatchPlan {
    pub kind_class: i32,
    pub pack_opacity: i32,
    pub pack_hex_pitch: i32,
    pub pack_stroke_perimeter: i32,
    pub pack_color2: i32,
    pub pack_radius: i32,
    pub marker_path_branch: i32,
    pub marker_glyph_branch: i32,
    pub meta_use_density: i32,
    pub meta_joined_fill: i32,
}

/// Figure-level XYTC orchestration from ``figure_scene`` / ``packXyTc``.
///
/// Hosts coerce ``show_legend`` (default ``true`` when absent). Returns ``1``
/// on success, ``0`` when ``show_legend`` is not ``0`` or ``1``.
pub fn scene_xytc_figure_plan(show_legend: i32, out_show_legend: &mut i32) -> i32 {
    if !matches!(show_legend, 0 | 1) {
        return 0;
    }
    *out_show_legend = show_legend;
    1
}

/// Per-trace XYTC pack dispatch from ``_pack_xytc`` / ``packXyTc``.
///
/// ``marker_path_present``, ``use_density``, and ``joined_fill`` are host
/// observations (``0``/``1``). Rust resolves ``kind_class`` and which pack
/// subroutines may run before hosts ship style bytes.
pub fn scene_xytc_trace_dispatch_plan(
    kind: &str,
    marker_path_present: i32,
    use_density: i32,
    joined_fill: i32,
    out: &mut XytcTraceDispatchPlan,
) -> i32 {
    for bit in [marker_path_present, use_density, joined_fill] {
        if !matches!(bit, 0 | 1) {
            return 0;
        }
    }
    let kind_class = scene_kind_class(kind);
    let scatter = kind == "scatter";
    let triangle_mesh = kind == "triangle_mesh";
    *out = XytcTraceDispatchPlan {
        kind_class,
        pack_opacity: i32::from(kind_class & SCENE_KIND_CLASS_OPACITY != 0),
        pack_hex_pitch: i32::from(kind_class & SCENE_KIND_CLASS_HEXBIN != 0),
        pack_stroke_perimeter: i32::from(kind_class & SCENE_KIND_CLASS_BAND != 0),
        pack_color2: i32::from(kind == "ribbon"),
        pack_radius: i32::from(
            scene_rect_kind_admits_radius(kind) || scene_rect_kind_admits_polar_wedge(kind),
        ),
        marker_path_branch: i32::from(scatter && marker_path_present != 0),
        marker_glyph_branch: i32::from(scatter && marker_path_present == 0),
        meta_use_density: i32::from(scatter && use_density != 0),
        meta_joined_fill: i32::from(triangle_mesh && joined_fill != 0),
    };
    1
}

/// Resolved per-trace XYTA attach dispatch from product kind and host facts.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct XytaTraceDispatchPlan {
    pub kind_class: i32,
    pub pack_heatmap: i32,
    pub pack_hexbin_colormap: i32,
    pub pack_hexbin_rgba: i32,
    pub pack_ribbon_ends: i32,
    pub pack_mesh_faces: i32,
    pub pack_scatter_paint: i32,
    pub pack_density: i32,
}

/// Figure-level XYTA orchestration from ``figure_scene`` / ``packXyTa``.
///
/// Hosts coerce ``polar`` from figure coords. Returns ``1`` on success, ``0``
/// when ``polar`` is not ``0`` or ``1``.
pub fn scene_xyta_figure_plan(polar: i32, out_polar: &mut i32) -> i32 {
    if !matches!(polar, 0 | 1) {
        return 0;
    }
    *out_polar = polar;
    1
}

fn scene_xyta_host_bit(value: i32) -> bool {
    matches!(value, 0 | 1)
}

/// Per-trace XYTA attach dispatch from ``_pack_xyta`` / ``packXyTa``.
///
/// Host observations are ``0``/``1`` except ``ribbon_color2_class`` (0–4 from
/// [`scene_ribbon_color2_classify`]). Rust resolves ``kind_class`` and which
/// attach branch may run before hosts ship grid/RGBA/density planes.
pub fn scene_xyta_trace_dispatch_plan(
    kind: &str,
    polar: i32,
    use_density: i32,
    hexbin_colormap_plane: i32,
    hexbin_rgba_plane_ready: i32,
    ribbon_color2_class: i32,
    mesh_paint_plane: i32,
    scatter_paint_plane: i32,
    out: &mut XytaTraceDispatchPlan,
) -> i32 {
    for bit in [
        polar,
        use_density,
        hexbin_colormap_plane,
        hexbin_rgba_plane_ready,
        mesh_paint_plane,
        scatter_paint_plane,
    ] {
        if !scene_xyta_host_bit(bit) {
            return 0;
        }
    }
    if !matches!(ribbon_color2_class, 0..=4) {
        return 0;
    }
    let kind_class = scene_kind_class(kind);
    let mut plan = XytaTraceDispatchPlan {
        kind_class,
        pack_heatmap: 0,
        pack_hexbin_colormap: 0,
        pack_hexbin_rgba: 0,
        pack_ribbon_ends: 0,
        pack_mesh_faces: 0,
        pack_scatter_paint: 0,
        pack_density: 0,
    };
    if kind_class & SCENE_KIND_CLASS_HEATMAP != 0 {
        plan.pack_heatmap = 1;
    } else if kind_class & SCENE_KIND_CLASS_HEXBIN != 0 && hexbin_colormap_plane != 0 {
        plan.pack_hexbin_colormap = 1;
    } else if kind_class & SCENE_KIND_CLASS_HEXBIN != 0 && hexbin_rgba_plane_ready != 0 {
        plan.pack_hexbin_rgba = 1;
    } else if kind_class & SCENE_KIND_CLASS_RIBBON != 0
        && polar == 0
        && ribbon_color2_class == SCENE_RIBBON_COLOR2_ENDS
    {
        plan.pack_ribbon_ends = 1;
    } else if mesh_paint_plane != 0 {
        plan.pack_mesh_faces = 1;
    } else if scatter_paint_plane != 0 {
        plan.pack_scatter_paint = 1;
    } else if kind == "scatter" && use_density != 0 {
        plan.pack_density = 1;
    }
    *out = plan;
    1
}

/// Resolved per-trace XYFS support-probe dispatch from product kind and host facts.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct FigureSupportTraceDispatchPlan {
    pub kind_class: i32,
    pub probe_marker_glyph: i32,
    pub probe_marker_path: i32,
    pub probe_curve_smooth: i32,
    pub probe_rect_extra: i32,
    pub probe_hexbin_reduce: i32,
    pub probe_heatmap_colormap: i32,
    pub probe_non_css_fill: i32,
}

fn scene_figure_support_host_bit(value: i32) -> bool {
    matches!(value, 0 | 1)
}

/// Figure-level XYFS support orchestration from ``_pack_figure_support`` /
/// ``packFigureSupport``.
///
/// Hosts coerce ``polar`` from figure coords. Returns ``1`` on success, ``0``
/// when ``polar`` is not ``0`` or ``1``.
pub fn scene_figure_support_figure_plan(polar: i32, out_polar: &mut i32) -> i32 {
    scene_xyta_figure_plan(polar, out_polar)
}

/// Per-trace XYFS support dispatch from ``_figure_trace_support_flags`` /
/// ``figureTraceSupport``.
///
/// Host observations are ``0``/``1``. Rust resolves ``kind_class`` and which
/// kind-gated probe branches may run before hosts ship style observations.
pub fn scene_figure_support_trace_dispatch_plan(
    kind: &str,
    marker_glyph_present: i32,
    marker_path_present: i32,
    curve_present: i32,
    fill_present: i32,
    out: &mut FigureSupportTraceDispatchPlan,
) -> i32 {
    for bit in [
        marker_glyph_present,
        marker_path_present,
        curve_present,
        fill_present,
    ] {
        if !scene_figure_support_host_bit(bit) {
            return 0;
        }
    }
    let kind_class = scene_kind_class(kind);
    *out = FigureSupportTraceDispatchPlan {
        kind_class,
        probe_marker_glyph: i32::from(marker_glyph_present != 0),
        probe_marker_path: i32::from(marker_path_present != 0),
        probe_curve_smooth: i32::from(
            kind_class & (SCENE_KIND_CLASS_LINE | SCENE_KIND_CLASS_BAND) != 0,
        ),
        probe_rect_extra: i32::from(
            kind_class & (SCENE_KIND_CLASS_RECT | SCENE_KIND_CLASS_HEATMAP) != 0,
        ),
        probe_hexbin_reduce: i32::from(kind_class & SCENE_KIND_CLASS_HEXBIN != 0),
        probe_heatmap_colormap: i32::from(kind_class & SCENE_KIND_CLASS_HEATMAP != 0),
        probe_non_css_fill: i32::from(fill_present != 0),
    };
    1
}

/// Figure-level XYCL column attach orchestration from ``_pack_xycl`` /
/// ``packXyCl``.
pub fn scene_xycl_figure_plan(polar: i32, out_polar: &mut i32) -> i32 {
    scene_figure_support_figure_plan(polar, out_polar)
}

/// Figure-level XYNM name attach orchestration from ``_pack_xynm`` /
/// ``packXyNm``.
pub fn scene_xynm_figure_plan(show_legend: i32, out_show_legend: &mut i32) -> i32 {
    scene_xytc_figure_plan(show_legend, out_show_legend)
}

/// Resolved XYCF figure chrome attach plan from ``_pack_chrome_facts`` /
/// ``packChromeFacts``.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct XycfFigurePlan {
    pub show_legend: i32,
    pub attach_legend: i32,
    pub attach_colorbar: i32,
    pub polar: i32,
}

fn scene_orchestrate_host_bit(value: i32) -> bool {
    matches!(value, 0 | 1)
}

/// Figure-level XYCF chrome attach orchestration.
///
/// Hosts coerce ``show_legend`` (default ``true`` when absent). ``colorbar_ok``
/// is a host observation that colorbar options may attach. Returns ``1`` on
/// success, ``0`` when any input is not ``0`` or ``1``.
pub fn scene_xycf_figure_plan(
    show_legend: i32,
    colorbar_ok: i32,
    polar: i32,
    out: &mut XycfFigurePlan,
) -> i32 {
    for bit in [show_legend, colorbar_ok, polar] {
        if !scene_orchestrate_host_bit(bit) {
            return 0;
        }
    }
    *out = XycfFigurePlan {
        show_legend,
        attach_legend: show_legend,
        attach_colorbar: colorbar_ok,
        polar,
    };
    1
}

/// Resolved per-annotation XYAF pack dispatch from kind and host facts.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct XyafAnnotationDispatchPlan {
    pub wrapped: i32,
    pub pack_rule_dash: i32,
    pub pack_rule_linecap: i32,
    pub pack_axis: i32,
    pub pack_symbol: i32,
}

/// Per-annotation XYAF attach dispatch from ``_pack_xyaf`` / ``packXyAf``.
///
/// ``authored_wrap`` and ``layout_text`` are host observations (``0``/``1``).
/// Rust resolves the wrapped-text branch and which style subroutines may run
/// before hosts ship annotation bytes.
pub fn scene_xyaf_annotation_dispatch_plan(
    kind: &str,
    authored_wrap: i32,
    layout_text: i32,
    out: &mut XyafAnnotationDispatchPlan,
) -> i32 {
    for bit in [authored_wrap, layout_text] {
        if !scene_orchestrate_host_bit(bit) {
            return 0;
        }
    }
    let wrapped = if kind == "text" {
        i32::from(authored_wrap != 0 || layout_text != 0)
    } else if kind == "callout" {
        authored_wrap
    } else {
        0
    };
    *out = XyafAnnotationDispatchPlan {
        wrapped,
        pack_rule_dash: i32::from(kind == "rule" && wrapped == 0),
        pack_rule_linecap: i32::from(kind == "rule" && wrapped == 0),
        pack_axis: i32::from(matches!(kind, "rule" | "band")),
        pack_symbol: i32::from(kind == "marker"),
    };
    1
}

/// Resolved XYEF public-export figure attach plan from ``_pack_public_export_support``
/// / ``packPublicExportSupport``.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct PublicExportFigurePlan {
    pub polar: i32,
    pub has_chrome_styles: i32,
    pub has_title_options: i32,
}

/// Figure-level XYEF export orchestration.
///
/// Host observations are ``0``/``1``. Rust resolves polar gating passed into
/// per-trace export dispatch before hosts ship XYEF observations.
pub fn scene_public_export_figure_plan(
    polar: i32,
    has_chrome_styles: i32,
    has_title_options: i32,
    out: &mut PublicExportFigurePlan,
) -> i32 {
    for bit in [polar, has_chrome_styles, has_title_options] {
        if !scene_orchestrate_host_bit(bit) {
            return 0;
        }
    }
    *out = PublicExportFigurePlan {
        polar,
        has_chrome_styles,
        has_title_options,
    };
    1
}

/// Resolved per-trace XYEF export dispatch from product kind and host facts.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct PublicExportTraceDispatchPlan {
    pub kind_class: i32,
    pub pack_density_blit: i32,
    pub pack_hexbin_pitch: i32,
}

/// Per-trace XYEF export dispatch from ``_pack_public_export_support`` /
/// ``packPublicExportSupport``.
///
/// ``polar`` and ``use_density`` are host observations (``0``/``1``). Rust
/// resolves kind-class gates and density-blit attach routing before hosts ship
/// trace observation bytes.
pub fn scene_public_export_trace_dispatch_plan(
    kind: &str,
    polar: i32,
    use_density: i32,
    out: &mut PublicExportTraceDispatchPlan,
) -> i32 {
    for bit in [polar, use_density] {
        if !scene_orchestrate_host_bit(bit) {
            return 0;
        }
    }
    let kind_class = scene_kind_class(kind);
    *out = PublicExportTraceDispatchPlan {
        kind_class,
        pack_density_blit: i32::from(kind == "scatter" && polar == 0 && use_density != 0),
        pack_hexbin_pitch: i32::from(kind_class & SCENE_KIND_CLASS_HEXBIN != 0),
    };
    1
}

/// Fixed product-path pack step indices (1-based) before ``xyg_scene_encode_product``.
pub const ENCODE_PRODUCT_STEP_XYTC: i32 = 1;
pub const ENCODE_PRODUCT_STEP_XYTA: i32 = 2;
pub const ENCODE_PRODUCT_STEP_XYNM: i32 = 3;
pub const ENCODE_PRODUCT_STEP_XYCL: i32 = 4;
pub const ENCODE_PRODUCT_STEP_XYAF: i32 = 5;
pub const ENCODE_PRODUCT_STEP_XYCF: i32 = 6;
pub const ENCODE_PRODUCT_STEP_XYPL: i32 = 7;
pub const ENCODE_PRODUCT_STEP_XYFS: i32 = 8;

/// Resolved XYPL polar attach plan from ``_pack_polar_scene_input`` /
/// ``packPolarSceneInput``.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct PolarFigurePlan {
    pub polar: i32,
    pub attach_xypl: i32,
}

/// Figure-level XYPL polar attach orchestration.
///
/// Hosts coerce ``polar`` from figure coords. Returns ``1`` on success, ``0``
/// when ``polar`` is not ``0`` or ``1``.
pub fn scene_polar_figure_plan(polar: i32, out: &mut PolarFigurePlan) -> i32 {
    if !scene_orchestrate_host_bit(polar) {
        return 0;
    }
    *out = PolarFigurePlan {
        polar,
        attach_xypl: polar,
    };
    1
}

/// Resolved product-path attach plan from ``figure_scene`` / ``figureSceneV3``.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct EncodeProductAttachPlan {
    pub polar: i32,
    pub attach_xypl: i32,
    pub step_xytc: i32,
    pub step_xyta: i32,
    pub step_xynm: i32,
    pub step_xycl: i32,
    pub step_xyaf: i32,
    pub step_xycf: i32,
    pub step_xypl: i32,
    pub step_xyfs: i32,
}

/// Figure-level encode-product attach orchestration.
///
/// Hosts coerce ``polar`` from figure coords. Rust owns the fixed pack order
/// and XYPL attach gating before hosts call ``xyg_scene_encode_product``.
pub fn scene_encode_product_attach_plan(polar: i32, out: &mut EncodeProductAttachPlan) -> i32 {
    if !scene_orchestrate_host_bit(polar) {
        return 0;
    }
    *out = EncodeProductAttachPlan {
        polar,
        attach_xypl: polar,
        step_xytc: ENCODE_PRODUCT_STEP_XYTC,
        step_xyta: ENCODE_PRODUCT_STEP_XYTA,
        step_xynm: ENCODE_PRODUCT_STEP_XYNM,
        step_xycl: ENCODE_PRODUCT_STEP_XYCL,
        step_xyaf: ENCODE_PRODUCT_STEP_XYAF,
        step_xycf: ENCODE_PRODUCT_STEP_XYCF,
        step_xypl: ENCODE_PRODUCT_STEP_XYPL,
        step_xyfs: ENCODE_PRODUCT_STEP_XYFS,
    };
    1
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn figure_plan_passes_show_legend() {
        let mut show = 0;
        assert_eq!(scene_xytc_figure_plan(1, &mut show), 1);
        assert_eq!(show, 1);
        assert_eq!(scene_xytc_figure_plan(0, &mut show), 1);
        assert_eq!(show, 0);
        assert_eq!(scene_xytc_figure_plan(2, &mut show), 0);
    }

    #[test]
    fn scatter_dispatch_routes_opacity_and_marker_glyph() {
        let mut plan = XytcTraceDispatchPlan {
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
        assert_eq!(
            scene_xytc_trace_dispatch_plan("scatter", 0, 1, 0, &mut plan),
            1
        );
        assert_eq!(plan.kind_class, SCENE_KIND_CLASS_SCATTER);
        assert_eq!(plan.pack_opacity, 1);
        assert_eq!(plan.pack_hex_pitch, 0);
        assert_eq!(plan.pack_stroke_perimeter, 0);
        assert_eq!(plan.pack_color2, 0);
        assert_eq!(plan.pack_radius, 0);
        assert_eq!(plan.marker_path_branch, 0);
        assert_eq!(plan.marker_glyph_branch, 1);
        assert_eq!(plan.meta_use_density, 1);
        assert_eq!(plan.meta_joined_fill, 0);
    }

    #[test]
    fn scatter_marker_path_branch_wins_over_glyph() {
        let mut plan = XytcTraceDispatchPlan {
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
        assert_eq!(
            scene_xytc_trace_dispatch_plan("scatter", 1, 0, 0, &mut plan),
            1
        );
        assert_eq!(plan.marker_path_branch, 1);
        assert_eq!(plan.marker_glyph_branch, 0);
    }

    #[test]
    fn ribbon_and_area_dispatch_kind_gates() {
        let mut ribbon = XytcTraceDispatchPlan {
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
        assert_eq!(
            scene_xytc_trace_dispatch_plan("ribbon", 0, 0, 0, &mut ribbon),
            1
        );
        assert_eq!(ribbon.kind_class, SCENE_KIND_CLASS_RIBBON);
        assert_eq!(ribbon.pack_opacity, 1);
        assert_eq!(ribbon.pack_color2, 1);
        assert_eq!(ribbon.pack_stroke_perimeter, 0);

        let mut area = ribbon;
        assert_eq!(
            scene_xytc_trace_dispatch_plan("area", 0, 0, 0, &mut area),
            1
        );
        assert_eq!(area.kind_class, SCENE_KIND_CLASS_BAND);
        assert_eq!(area.pack_stroke_perimeter, 1);
        assert_eq!(area.pack_color2, 0);
    }

    #[test]
    fn bar_and_hexbin_radius_and_hex_routes() {
        let mut bar = XytcTraceDispatchPlan {
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
        assert_eq!(scene_xytc_trace_dispatch_plan("bar", 0, 0, 0, &mut bar), 1);
        assert_eq!(bar.pack_radius, 1);
        assert_eq!(bar.pack_opacity, 1);

        let mut hex = bar;
        assert_eq!(
            scene_xytc_trace_dispatch_plan("hexbin", 0, 0, 0, &mut hex),
            1
        );
        assert_eq!(hex.pack_hex_pitch, 1);
        assert_eq!(hex.pack_radius, 0);
    }

    #[test]
    fn triangle_mesh_joined_fill_meta_route() {
        let mut plan = XytcTraceDispatchPlan {
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
        assert_eq!(
            scene_xytc_trace_dispatch_plan("triangle_mesh", 0, 0, 1, &mut plan),
            1
        );
        assert_eq!(plan.kind_class, SCENE_KIND_CLASS_POLYFILL);
        assert_eq!(plan.meta_joined_fill, 1);
    }

    #[test]
    fn dispatch_rejects_invalid_bits() {
        let mut plan = XytcTraceDispatchPlan {
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
        assert_eq!(scene_xytc_trace_dispatch_plan("line", 2, 0, 0, &mut plan), 0);
    }

    #[test]
    fn xyta_figure_plan_passes_polar() {
        let mut polar = 0;
        assert_eq!(scene_xyta_figure_plan(1, &mut polar), 1);
        assert_eq!(polar, 1);
        assert_eq!(scene_xyta_figure_plan(0, &mut polar), 1);
        assert_eq!(polar, 0);
        assert_eq!(scene_xyta_figure_plan(2, &mut polar), 0);
    }

    #[test]
    fn xyta_dispatch_heatmap_wins_over_hexbin() {
        let mut plan = XytaTraceDispatchPlan {
            kind_class: 0,
            pack_heatmap: 0,
            pack_hexbin_colormap: 0,
            pack_hexbin_rgba: 0,
            pack_ribbon_ends: 0,
            pack_mesh_faces: 0,
            pack_scatter_paint: 0,
            pack_density: 0,
        };
        assert_eq!(
            scene_xyta_trace_dispatch_plan(
                "heatmap",
                0,
                0,
                1,
                1,
                SCENE_RIBBON_COLOR2_ENDS,
                1,
                1,
                &mut plan,
            ),
            1
        );
        assert_eq!(plan.kind_class, SCENE_KIND_CLASS_HEATMAP);
        assert_eq!(plan.pack_heatmap, 1);
        assert_eq!(plan.pack_hexbin_colormap, 0);
    }

    #[test]
    fn xyta_dispatch_hexbin_colormap_and_rgba_priority() {
        let mut cmap = XytaTraceDispatchPlan {
            kind_class: 0,
            pack_heatmap: 0,
            pack_hexbin_colormap: 0,
            pack_hexbin_rgba: 0,
            pack_ribbon_ends: 0,
            pack_mesh_faces: 0,
            pack_scatter_paint: 0,
            pack_density: 0,
        };
        assert_eq!(
            scene_xyta_trace_dispatch_plan(
                "hexbin",
                0,
                0,
                1,
                1,
                0,
                0,
                0,
                &mut cmap,
            ),
            1
        );
        assert_eq!(cmap.pack_hexbin_colormap, 1);
        assert_eq!(cmap.pack_hexbin_rgba, 0);

        let mut rgba = cmap;
        assert_eq!(
            scene_xyta_trace_dispatch_plan("hexbin", 0, 0, 0, 1, 0, 0, 0, &mut rgba),
            1
        );
        assert_eq!(rgba.pack_hexbin_colormap, 0);
        assert_eq!(rgba.pack_hexbin_rgba, 1);
    }

    #[test]
    fn xyta_dispatch_ribbon_mesh_scatter_and_density() {
        let mut ribbon = XytaTraceDispatchPlan {
            kind_class: 0,
            pack_heatmap: 0,
            pack_hexbin_colormap: 0,
            pack_hexbin_rgba: 0,
            pack_ribbon_ends: 0,
            pack_mesh_faces: 0,
            pack_scatter_paint: 0,
            pack_density: 0,
        };
        assert_eq!(
            scene_xyta_trace_dispatch_plan(
                "ribbon",
                0,
                0,
                0,
                0,
                SCENE_RIBBON_COLOR2_ENDS,
                0,
                0,
                &mut ribbon,
            ),
            1
        );
        assert_eq!(ribbon.pack_ribbon_ends, 1);

        let mut polar_ribbon = ribbon;
        assert_eq!(
            scene_xyta_trace_dispatch_plan(
                "ribbon",
                1,
                0,
                0,
                0,
                SCENE_RIBBON_COLOR2_ENDS,
                0,
                0,
                &mut polar_ribbon,
            ),
            1
        );
        assert_eq!(polar_ribbon.pack_ribbon_ends, 0);

        let mut mesh = polar_ribbon;
        assert_eq!(
            scene_xyta_trace_dispatch_plan("triangle_mesh", 0, 0, 0, 0, 0, 1, 0, &mut mesh),
            1
        );
        assert_eq!(mesh.pack_mesh_faces, 1);

        let mut scatter = mesh;
        assert_eq!(
            scene_xyta_trace_dispatch_plan("scatter", 0, 0, 0, 0, 0, 0, 1, &mut scatter),
            1
        );
        assert_eq!(scatter.pack_scatter_paint, 1);

        let mut density = scatter;
        assert_eq!(
            scene_xyta_trace_dispatch_plan("scatter", 0, 1, 0, 0, 0, 0, 0, &mut density),
            1
        );
        assert_eq!(density.pack_density, 1);
    }

    #[test]
    fn xyta_dispatch_rejects_invalid_observations() {
        let mut plan = XytaTraceDispatchPlan {
            kind_class: 0,
            pack_heatmap: 0,
            pack_hexbin_colormap: 0,
            pack_hexbin_rgba: 0,
            pack_ribbon_ends: 0,
            pack_mesh_faces: 0,
            pack_scatter_paint: 0,
            pack_density: 0,
        };
        assert_eq!(
            scene_xyta_trace_dispatch_plan("scatter", 2, 0, 0, 0, 0, 0, 0, &mut plan),
            0
        );
        assert_eq!(
            scene_xyta_trace_dispatch_plan("ribbon", 0, 0, 0, 0, 5, 0, 0, &mut plan),
            0
        );
    }

    #[test]
    fn figure_support_figure_plan_passes_polar() {
        let mut polar = 0;
        assert_eq!(scene_figure_support_figure_plan(1, &mut polar), 1);
        assert_eq!(polar, 1);
        assert_eq!(scene_figure_support_figure_plan(0, &mut polar), 1);
        assert_eq!(polar, 0);
        assert_eq!(scene_figure_support_figure_plan(2, &mut polar), 0);
    }

    #[test]
    fn figure_support_dispatch_scatter_markers_and_fill() {
        let mut plan = FigureSupportTraceDispatchPlan {
            kind_class: 0,
            probe_marker_glyph: 0,
            probe_marker_path: 0,
            probe_curve_smooth: 0,
            probe_rect_extra: 0,
            probe_hexbin_reduce: 0,
            probe_heatmap_colormap: 0,
            probe_non_css_fill: 0,
        };
        assert_eq!(
            scene_figure_support_trace_dispatch_plan("scatter", 1, 0, 0, 1, &mut plan),
            1
        );
        assert_eq!(plan.kind_class, SCENE_KIND_CLASS_SCATTER);
        assert_eq!(plan.probe_marker_glyph, 1);
        assert_eq!(plan.probe_marker_path, 0);
        assert_eq!(plan.probe_non_css_fill, 1);
        assert_eq!(plan.probe_curve_smooth, 0);

        let mut path = plan;
        assert_eq!(
            scene_figure_support_trace_dispatch_plan("scatter", 0, 1, 0, 0, &mut path),
            1
        );
        assert_eq!(path.probe_marker_glyph, 0);
        assert_eq!(path.probe_marker_path, 1);
    }

    #[test]
    fn figure_support_dispatch_kind_gates() {
        let mut area = FigureSupportTraceDispatchPlan {
            kind_class: 0,
            probe_marker_glyph: 0,
            probe_marker_path: 0,
            probe_curve_smooth: 0,
            probe_rect_extra: 0,
            probe_hexbin_reduce: 0,
            probe_heatmap_colormap: 0,
            probe_non_css_fill: 0,
        };
        assert_eq!(
            scene_figure_support_trace_dispatch_plan("area", 0, 0, 1, 0, &mut area),
            1
        );
        assert_eq!(area.probe_curve_smooth, 1);
        assert_eq!(area.probe_rect_extra, 0);

        let mut bar = area;
        assert_eq!(
            scene_figure_support_trace_dispatch_plan("bar", 0, 0, 0, 0, &mut bar),
            1
        );
        assert_eq!(bar.probe_rect_extra, 1);

        let mut hex = bar;
        assert_eq!(
            scene_figure_support_trace_dispatch_plan("hexbin", 0, 0, 0, 0, &mut hex),
            1
        );
        assert_eq!(hex.probe_hexbin_reduce, 1);

        let mut heatmap = hex;
        assert_eq!(
            scene_figure_support_trace_dispatch_plan("heatmap", 0, 0, 0, 0, &mut heatmap),
            1
        );
        assert_eq!(heatmap.probe_heatmap_colormap, 1);
    }

    #[test]
    fn xycl_and_xynm_figure_plans_delegate() {
        let mut polar = 0;
        assert_eq!(scene_xycl_figure_plan(1, &mut polar), 1);
        assert_eq!(polar, 1);
        let mut show = 0;
        assert_eq!(scene_xynm_figure_plan(1, &mut show), 1);
        assert_eq!(show, 1);
    }

    #[test]
    fn figure_support_dispatch_rejects_invalid_bits() {
        let mut plan = FigureSupportTraceDispatchPlan {
            kind_class: 0,
            probe_marker_glyph: 0,
            probe_marker_path: 0,
            probe_curve_smooth: 0,
            probe_rect_extra: 0,
            probe_hexbin_reduce: 0,
            probe_heatmap_colormap: 0,
            probe_non_css_fill: 0,
        };
        assert_eq!(
            scene_figure_support_trace_dispatch_plan("line", 2, 0, 0, 0, &mut plan),
            0
        );
    }

    #[test]
    fn xycf_figure_plan_attach_routes() {
        let mut plan = XycfFigurePlan {
            show_legend: 0,
            attach_legend: 0,
            attach_colorbar: 0,
            polar: 0,
        };
        assert_eq!(scene_xycf_figure_plan(1, 1, 0, &mut plan), 1);
        assert_eq!(plan.show_legend, 1);
        assert_eq!(plan.attach_legend, 1);
        assert_eq!(plan.attach_colorbar, 1);
        assert_eq!(plan.polar, 0);
        assert_eq!(scene_xycf_figure_plan(0, 0, 1, &mut plan), 1);
        assert_eq!(plan.attach_legend, 0);
        assert_eq!(plan.attach_colorbar, 0);
        assert_eq!(plan.polar, 1);
        assert_eq!(scene_xycf_figure_plan(2, 0, 0, &mut plan), 0);
    }

    #[test]
    fn xyaf_dispatch_wrapped_and_rule_branches() {
        let mut text = XyafAnnotationDispatchPlan {
            wrapped: 0,
            pack_rule_dash: 0,
            pack_rule_linecap: 0,
            pack_axis: 0,
            pack_symbol: 0,
        };
        assert_eq!(
            scene_xyaf_annotation_dispatch_plan("text", 0, 1, &mut text),
            1
        );
        assert_eq!(text.wrapped, 1);
        assert_eq!(text.pack_rule_dash, 0);

        let mut rule = text;
        assert_eq!(
            scene_xyaf_annotation_dispatch_plan("rule", 0, 0, &mut rule),
            1
        );
        assert_eq!(rule.wrapped, 0);
        assert_eq!(rule.pack_rule_dash, 1);
        assert_eq!(rule.pack_rule_linecap, 1);
        assert_eq!(rule.pack_axis, 1);

        let mut marker = rule;
        assert_eq!(
            scene_xyaf_annotation_dispatch_plan("marker", 0, 0, &mut marker),
            1
        );
        assert_eq!(marker.pack_symbol, 1);
        assert_eq!(marker.pack_axis, 0);
    }

    #[test]
    fn public_export_figure_and_trace_dispatch() {
        let mut figure = PublicExportFigurePlan {
            polar: 0,
            has_chrome_styles: 0,
            has_title_options: 0,
        };
        assert_eq!(scene_public_export_figure_plan(1, 1, 0, &mut figure), 1);
        assert_eq!(figure.polar, 1);
        assert_eq!(figure.has_chrome_styles, 1);

        let mut scatter = PublicExportTraceDispatchPlan {
            kind_class: 0,
            pack_density_blit: 0,
            pack_hexbin_pitch: 0,
        };
        assert_eq!(
            scene_public_export_trace_dispatch_plan("scatter", 0, 1, &mut scatter),
            1
        );
        assert_eq!(scatter.pack_density_blit, 1);

        let mut polar_scatter = scatter;
        assert_eq!(
            scene_public_export_trace_dispatch_plan("scatter", 1, 1, &mut polar_scatter),
            1
        );
        assert_eq!(polar_scatter.pack_density_blit, 0);

        let mut hex = polar_scatter;
        assert_eq!(
            scene_public_export_trace_dispatch_plan("hexbin", 0, 0, &mut hex),
            1
        );
        assert_eq!(hex.pack_hexbin_pitch, 1);
    }

    #[test]
    fn polar_figure_plan_attach_xypl() {
        let mut plan = PolarFigurePlan {
            polar: 0,
            attach_xypl: 0,
        };
        assert_eq!(scene_polar_figure_plan(1, &mut plan), 1);
        assert_eq!(plan.polar, 1);
        assert_eq!(plan.attach_xypl, 1);
        assert_eq!(scene_polar_figure_plan(0, &mut plan), 1);
        assert_eq!(plan.attach_xypl, 0);
        assert_eq!(scene_polar_figure_plan(2, &mut plan), 0);
    }

    #[test]
    fn encode_product_attach_plan_order_and_polar() {
        let mut plan = EncodeProductAttachPlan {
            polar: 0,
            attach_xypl: 0,
            step_xytc: 0,
            step_xyta: 0,
            step_xynm: 0,
            step_xycl: 0,
            step_xyaf: 0,
            step_xycf: 0,
            step_xypl: 0,
            step_xyfs: 0,
        };
        assert_eq!(scene_encode_product_attach_plan(1, &mut plan), 1);
        assert_eq!(plan.attach_xypl, 1);
        assert_eq!(plan.step_xytc, ENCODE_PRODUCT_STEP_XYTC);
        assert_eq!(plan.step_xyta, ENCODE_PRODUCT_STEP_XYTA);
        assert_eq!(plan.step_xynm, ENCODE_PRODUCT_STEP_XYNM);
        assert_eq!(plan.step_xycl, ENCODE_PRODUCT_STEP_XYCL);
        assert_eq!(plan.step_xyaf, ENCODE_PRODUCT_STEP_XYAF);
        assert_eq!(plan.step_xycf, ENCODE_PRODUCT_STEP_XYCF);
        assert_eq!(plan.step_xypl, ENCODE_PRODUCT_STEP_XYPL);
        assert_eq!(plan.step_xyfs, ENCODE_PRODUCT_STEP_XYFS);
        assert_eq!(scene_encode_product_attach_plan(0, &mut plan), 1);
        assert_eq!(plan.attach_xypl, 0);
        assert_eq!(scene_encode_product_attach_plan(2, &mut plan), 0);
    }
}
