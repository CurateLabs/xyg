//! Scene pack orchestration (M2 #733).
//!
//! Hosts still ship XYTC/XYTA buffers and coerce style literals. Rust owns
//! figure-level legend attach and per-trace XYTC pack dispatch routing so
//! Python ``_pack_xytc`` and Node ``packXyTc`` cannot drift on kind-class
//! gates or scatter marker branches.

use crate::kernels::{
    scene_kind_class, SCENE_KIND_CLASS_BAND, SCENE_KIND_CLASS_HEXBIN,
    SCENE_KIND_CLASS_HEATMAP, SCENE_KIND_CLASS_POLYFILL, SCENE_KIND_CLASS_RECT,
    SCENE_KIND_CLASS_RIBBON, SCENE_KIND_CLASS_SCATTER,
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
}
