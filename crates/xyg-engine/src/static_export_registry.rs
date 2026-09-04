//! Checked fixture vocabulary for exhaustive public static-export parity (#875).
//!
//! This is test/evidence policy, not another renderer.  The public-export
//! predicate consumes `PUBLIC_EXPORT_KINDS`, while the cross-host corpus is
//! generated from `STATIC_EXPORT_SHAPES`.  Consequently a newly admitted kind
//! cannot land without naming at least one live Python/Node fixture that covers
//! it.  #873 may append shapes here without changing the corpus machinery.

/// One Rust-recognised product kind and its stable XYEP code.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct PublicExportKind {
    pub name: &'static str,
    pub code: u8,
}

pub const PUBLIC_EXPORT_KINDS: &[PublicExportKind] = &[
    PublicExportKind {
        name: "scatter",
        code: 0,
    },
    PublicExportKind {
        name: "line",
        code: 1,
    },
    PublicExportKind {
        name: "bar",
        code: 2,
    },
    PublicExportKind {
        name: "column",
        code: 3,
    },
    PublicExportKind {
        name: "histogram",
        code: 4,
    },
    PublicExportKind {
        name: "violin",
        code: 5,
    },
    PublicExportKind {
        name: "box",
        code: 6,
    },
    PublicExportKind {
        name: "box_whisker",
        code: 7,
    },
    PublicExportKind {
        name: "box_median",
        code: 8,
    },
    PublicExportKind {
        name: "segments",
        code: 9,
    },
    PublicExportKind {
        name: "errorbar",
        code: 10,
    },
    PublicExportKind {
        name: "stem",
        code: 11,
    },
    PublicExportKind {
        name: "area",
        code: 12,
    },
    PublicExportKind {
        name: "error_band",
        code: 13,
    },
    PublicExportKind {
        name: "ribbon",
        code: 14,
    },
    PublicExportKind {
        name: "triangle_mesh",
        code: 15,
    },
    PublicExportKind {
        name: "hexbin",
        code: 16,
    },
    PublicExportKind {
        name: "heatmap",
        code: 17,
    },
    PublicExportKind {
        name: "contour",
        code: 18,
    },
];

/// One public authoring shape in the exhaustive static-export corpus.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct StaticExportShape {
    pub name: &'static str,
    pub trace_kinds: &'static [&'static str],
    pub autorange: bool,
}

/// Current admitted public authoring shapes. Internal companion kinds are
/// listed on their owning shape (box and stem), so the coverage check below is
/// exact over `PUBLIC_EXPORT_KINDS` without inventing host-only fixtures.
pub const STATIC_EXPORT_SHAPES: &[StaticExportShape] = &[
    StaticExportShape {
        name: "scatter",
        trace_kinds: &["scatter"],
        autorange: true,
    },
    StaticExportShape {
        name: "line",
        trace_kinds: &["line"],
        autorange: true,
    },
    StaticExportShape {
        name: "step",
        trace_kinds: &["line"],
        autorange: true,
    },
    StaticExportShape {
        name: "stairs",
        trace_kinds: &["line"],
        autorange: true,
    },
    StaticExportShape {
        name: "ecdf",
        trace_kinds: &["line"],
        autorange: true,
    },
    StaticExportShape {
        name: "bar",
        trace_kinds: &["bar"],
        autorange: true,
    },
    // Node's public `bar` is the canonical horizontal/vertical Rect alias for
    // Python `column`; the corpus proves their Scene bytes are identical.
    StaticExportShape {
        name: "column_bar",
        trace_kinds: &["column"],
        autorange: true,
    },
    StaticExportShape {
        name: "histogram",
        trace_kinds: &["histogram"],
        autorange: true,
    },
    StaticExportShape {
        name: "area",
        trace_kinds: &["area"],
        autorange: true,
    },
    StaticExportShape {
        name: "errorbar",
        trace_kinds: &["errorbar"],
        autorange: true,
    },
    StaticExportShape {
        name: "box",
        trace_kinds: &["box_whisker", "box", "box_median"],
        autorange: true,
    },
    StaticExportShape {
        name: "violin",
        trace_kinds: &["violin"],
        autorange: true,
    },
    StaticExportShape {
        name: "violin_horizontal",
        trace_kinds: &["violin"],
        autorange: true,
    },
    StaticExportShape {
        name: "hexbin",
        trace_kinds: &["hexbin"],
        autorange: true,
    },
    StaticExportShape {
        name: "segments",
        trace_kinds: &["segments"],
        autorange: false,
    },
    StaticExportShape {
        name: "stem",
        trace_kinds: &["stem", "scatter"],
        autorange: false,
    },
    StaticExportShape {
        name: "error_band",
        trace_kinds: &["error_band"],
        autorange: false,
    },
    StaticExportShape {
        name: "ribbon",
        trace_kinds: &["ribbon"],
        autorange: false,
    },
    StaticExportShape {
        name: "triangle_mesh",
        trace_kinds: &["triangle_mesh"],
        autorange: false,
    },
    StaticExportShape {
        name: "heatmap",
        trace_kinds: &["heatmap"],
        autorange: false,
    },
    StaticExportShape {
        name: "contour",
        trace_kinds: &["contour"],
        autorange: false,
    },
];

/// A bounded pairwise edge-case row. Each concern appears in at least two rows
/// and is crossed with a different shape/axis mode; this is deliberately not a
/// combinatorial product.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct StaticExportEdgeCase {
    pub name: &'static str,
    pub shape: &'static str,
    pub axis_mode: &'static str,
    pub concerns: &'static [&'static str],
    pub reason_prefix: &'static str,
}

/// The exact concern vocabulary required by #875. Registry tests pin both the
/// set and the two-row bounded-pairwise coverage for every concern.
pub const REQUIRED_EDGE_CONCERNS: &[&str] = &[
    "authored-domain",
    "style",
    "single",
    "log-scale",
    "nonfinite",
    "categorical-axis",
    "temporal-axis",
    "empty",
    "linear-scale",
];

pub const STATIC_EXPORT_EDGE_CASES: &[StaticExportEdgeCase] = &[
    StaticExportEdgeCase {
        name: "line_authored_style",
        shape: "line",
        axis_mode: "authored-linear-xy",
        concerns: &["authored-domain", "style"],
        reason_prefix: "",
    },
    StaticExportEdgeCase {
        name: "scatter_single_log",
        shape: "scatter",
        axis_mode: "log-x-linear-y",
        concerns: &["single", "log-scale"],
        reason_prefix: "",
    },
    StaticExportEdgeCase {
        name: "step_nonfinite_authored",
        shape: "step",
        axis_mode: "authored-linear-x-log-y",
        concerns: &["nonfinite", "authored-domain"],
        reason_prefix: "Scene v12 does not yet encode missing-data breaks or nonfinite coordinates",
    },
    StaticExportEdgeCase {
        name: "bar_categorical_style",
        shape: "bar",
        axis_mode: "categorical-x-linear-y",
        concerns: &["categorical-axis", "style"],
        reason_prefix: "XYG_SCENE_UNSUPPORTED_PUBLIC_AXIS",
    },
    StaticExportEdgeCase {
        name: "line_temporal_single",
        shape: "line",
        axis_mode: "temporal-x-linear-y",
        concerns: &["temporal-axis", "single"],
        reason_prefix: "XYG_SCENE_UNSUPPORTED_PUBLIC_AXIS",
    },
    StaticExportEdgeCase {
        name: "scatter_empty_linear",
        shape: "scatter",
        axis_mode: "linear-x-linear-y",
        concerns: &["empty", "linear-scale"],
        reason_prefix: "invalid scene trace packing",
    },
    StaticExportEdgeCase {
        name: "area_nonfinite_linear",
        shape: "area",
        axis_mode: "authored-linear-xy",
        concerns: &["nonfinite", "linear-scale"],
        reason_prefix: "Scene v12 does not yet encode missing-data breaks or nonfinite coordinates",
    },
    StaticExportEdgeCase {
        name: "histogram_empty_categorical",
        shape: "histogram",
        axis_mode: "linear-x-categorical-y",
        concerns: &["empty", "categorical-axis"],
        reason_prefix: "XYG_SCENE_UNSUPPORTED_PUBLIC_AXIS",
    },
    StaticExportEdgeCase {
        name: "step_temporal_log",
        shape: "step",
        axis_mode: "temporal-x-log-y",
        concerns: &["temporal-axis", "log-scale"],
        reason_prefix: "XYG_SCENE_UNSUPPORTED_PUBLIC_AXIS",
    },
];

/// Fail-closed feature families deliberately outside the current shared Scene
/// contract. Reasons are prefixes because some diagnostics carry detail.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct StaticExportFailClose {
    pub name: &'static str,
    pub reason_prefix: &'static str,
}

pub const STATIC_EXPORT_FAIL_CLOSES: &[StaticExportFailClose] = &[
    StaticExportFailClose {
        name: "fluid_viewport",
        reason_prefix: "XYG_SCENE_UNSUPPORTED_FLUID_VIEWPORT",
    },
    StaticExportFailClose {
        name: "browser_css",
        reason_prefix: "XYG_SCENE_UNSUPPORTED_BROWSER_CSS",
    },
    StaticExportFailClose {
        name: "custom_font",
        reason_prefix: "XYG_SCENE_UNSUPPORTED_PUBLIC_STYLE",
    },
    StaticExportFailClose {
        name: "title_options",
        reason_prefix: "XYG_SCENE_UNSUPPORTED_PUBLIC_TEXT",
    },
    StaticExportFailClose {
        name: "extra_legend",
        reason_prefix: "XYG_SCENE_UNSUPPORTED_PUBLIC_LEGEND",
    },
    StaticExportFailClose {
        name: "alternate_axis",
        reason_prefix: "Scene v12 currently supports only the primary x/y axes",
    },
    StaticExportFailClose {
        name: "unsupported_symbol",
        reason_prefix: "XYG_SCENE_UNSUPPORTED_PUBLIC_SYMBOL",
    },
    StaticExportFailClose {
        name: "unsupported_mark",
        reason_prefix: "XYG_SCENE_UNSUPPORTED_PUBLIC_MARK",
    },
    StaticExportFailClose {
        name: "violin_orientation_metadata",
        reason_prefix: "XYG_SCENE_UNSUPPORTED_PUBLIC_STYLE",
    },
    StaticExportFailClose {
        name: "layered_autorange",
        reason_prefix: "XYG_SCENE_UNSUPPORTED_PUBLIC_AXIS",
    },
    StaticExportFailClose {
        name: "annotation_html",
        reason_prefix: "XYG_SCENE_UNSUPPORTED_ANNOTATION_HTML",
    },
    StaticExportFailClose {
        name: "annotation_collision",
        reason_prefix: "XYG_SCENE_UNSUPPORTED_ANNOTATION_COLLISION",
    },
    StaticExportFailClose {
        name: "annotation_markup",
        reason_prefix: "XYG_SCENE_UNSUPPORTED_ANNOTATION_MARKUP",
    },
    StaticExportFailClose {
        name: "invalid_annotation",
        reason_prefix: "XYG_SCENE_UNSUPPORTED_PUBLIC_ANNOTATION",
    },
    StaticExportFailClose {
        name: "colorbar_option",
        reason_prefix: "XYG_SCENE_UNSUPPORTED_PUBLIC_COLORBAR",
    },
    StaticExportFailClose {
        name: "lod_limit",
        reason_prefix: "XYG_SCENE_UNSUPPORTED_PUBLIC_LOD",
    },
    StaticExportFailClose {
        name: "band_shape",
        reason_prefix: "XYG_SCENE_UNSUPPORTED_PUBLIC_BAND",
    },
    StaticExportFailClose {
        name: "segment_shape",
        reason_prefix: "XYG_SCENE_UNSUPPORTED_PUBLIC_SEGMENTS",
    },
    StaticExportFailClose {
        name: "triangle_mesh_limit",
        reason_prefix: "XYG_SCENE_UNSUPPORTED_PUBLIC_TRIANGLE_MESH",
    },
];

/// Deterministic JSON consumed by the fixture generator; no serde dependency is
/// added to the minimal engine crate.
pub fn static_export_registry_json() -> String {
    fn strings(values: &[&str]) -> String {
        values
            .iter()
            .map(|value| format!("\"{value}\""))
            .collect::<Vec<_>>()
            .join(",")
    }
    let shapes = STATIC_EXPORT_SHAPES
        .iter()
        .map(|shape| {
            format!(
                "{{\"name\":\"{}\",\"trace_kinds\":[{}],\"autorange\":{}}}",
                shape.name,
                strings(shape.trace_kinds),
                shape.autorange
            )
        })
        .collect::<Vec<_>>()
        .join(",");
    let edges = STATIC_EXPORT_EDGE_CASES
        .iter()
        .map(|case| {
            format!(
                "{{\"name\":\"{}\",\"shape\":\"{}\",\"axis_mode\":\"{}\",\"concerns\":[{}],\"reason_prefix\":\"{}\"}}",
                case.name,
                case.shape,
                case.axis_mode,
                strings(case.concerns),
                case.reason_prefix,
            )
        })
        .collect::<Vec<_>>()
        .join(",");
    let misses = STATIC_EXPORT_FAIL_CLOSES
        .iter()
        .map(|case| {
            format!(
                "{{\"name\":\"{}\",\"reason_prefix\":\"{}\"}}",
                case.name, case.reason_prefix
            )
        })
        .collect::<Vec<_>>()
        .join(",");
    format!(
        "{{\"schema\":\"xyg.static-export-support-registry/v1\",\"required_edge_concerns\":[{}],\"shapes\":[{shapes}],\"edge_cases\":[{edges}],\"fail_close\":[{misses}]}}\n",
        strings(REQUIRED_EDGE_CONCERNS)
    )
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::collections::{BTreeMap, BTreeSet};

    #[test]
    fn every_admitted_kind_has_a_cross_host_shape() {
        let admitted: BTreeSet<&str> = PUBLIC_EXPORT_KINDS.iter().map(|kind| kind.name).collect();
        let covered: BTreeSet<&str> = STATIC_EXPORT_SHAPES
            .iter()
            .flat_map(|shape| shape.trace_kinds.iter().copied())
            .collect();
        assert_eq!(covered, admitted);
    }

    #[test]
    fn registry_names_and_kind_codes_are_unique() {
        let shape_names: BTreeSet<&str> = STATIC_EXPORT_SHAPES
            .iter()
            .map(|shape| shape.name)
            .collect();
        let edge_names: BTreeSet<&str> = STATIC_EXPORT_EDGE_CASES
            .iter()
            .map(|case| case.name)
            .collect();
        let miss_names: BTreeSet<&str> = STATIC_EXPORT_FAIL_CLOSES
            .iter()
            .map(|case| case.name)
            .collect();
        let kind_names: BTreeSet<&str> = PUBLIC_EXPORT_KINDS.iter().map(|kind| kind.name).collect();
        let kind_codes: BTreeSet<u8> = PUBLIC_EXPORT_KINDS.iter().map(|kind| kind.code).collect();
        assert_eq!(shape_names.len(), STATIC_EXPORT_SHAPES.len());
        assert_eq!(edge_names.len(), STATIC_EXPORT_EDGE_CASES.len());
        assert_eq!(miss_names.len(), STATIC_EXPORT_FAIL_CLOSES.len());
        assert_eq!(kind_names.len(), PUBLIC_EXPORT_KINDS.len());
        assert_eq!(kind_codes.len(), PUBLIC_EXPORT_KINDS.len());

        let all_case_names: BTreeSet<&str> = shape_names
            .iter()
            .chain(edge_names.iter())
            .chain(miss_names.iter())
            .copied()
            .collect();
        assert_eq!(
            all_case_names.len(),
            STATIC_EXPORT_SHAPES.len()
                + STATIC_EXPORT_EDGE_CASES.len()
                + STATIC_EXPORT_FAIL_CLOSES.len()
        );
        assert!(STATIC_EXPORT_SHAPES
            .iter()
            .all(|shape| !shape.trace_kinds.is_empty()));
        assert!(STATIC_EXPORT_EDGE_CASES
            .iter()
            .all(|case| shape_names.contains(case.shape)));
        assert!(STATIC_EXPORT_FAIL_CLOSES
            .iter()
            .all(|case| !case.reason_prefix.is_empty()));
    }

    #[test]
    fn pairwise_concerns_each_have_two_bounded_rows() {
        let mut rows = BTreeMap::<&str, Vec<&StaticExportEdgeCase>>::new();
        for case in STATIC_EXPORT_EDGE_CASES {
            assert_eq!(case.concerns.len(), 2);
            for concern in case.concerns {
                rows.entry(*concern).or_default().push(case);
            }
        }
        let actual: BTreeSet<&str> = rows.keys().copied().collect();
        let required: BTreeSet<&str> = REQUIRED_EDGE_CONCERNS.iter().copied().collect();
        assert_eq!(actual, required);
        for cases in rows.values() {
            assert_eq!(cases.len(), 2);
            assert_ne!(cases[0].shape, cases[1].shape);
            assert_ne!(cases[0].axis_mode, cases[1].axis_mode);
        }
    }
}
