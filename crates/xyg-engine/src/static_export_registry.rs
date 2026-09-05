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

/// StaticDocument vocabulary extends this same registry; it is not a second
/// host-maintained support list. Runtime proof consumers must cover every row.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct StaticDocumentVocabulary {
    pub name: &'static str,
    pub family: &'static str,
    pub code: u32,
}

/// These masks are consumed by the XYST decoder after the #873 integration.
pub const STATIC_DOCUMENT_HEADER_FLAGS: u32 = 15;
pub const STATIC_DOCUMENT_PANEL_FLAGS: u32 = 0x7fff;
pub const STATIC_DOCUMENT_FORMATS: &[&str] = &["svg", "png", "pdf", "jpeg", "webp"];

pub const STATIC_DOCUMENT_VOCABULARY: &[StaticDocumentVocabulary] = &[
    StaticDocumentVocabulary {
        name: "panel.colorbar-log-scale",
        family: "panel-flag",
        code: 1024,
    },
    StaticDocumentVocabulary {
        name: "panel.colorbar-extend-min",
        family: "panel-flag",
        code: 2048,
    },
    StaticDocumentVocabulary {
        name: "panel.colorbar-extend-max",
        family: "panel-flag",
        code: 4096,
    },
    StaticDocumentVocabulary {
        name: "panel.colorbar-pyplot-label",
        family: "panel-flag",
        code: 8192,
    },
    StaticDocumentVocabulary {
        name: "panel.grid-dash",
        family: "panel-flag",
        code: 1 << 14,
    },
    StaticDocumentVocabulary {
        name: "annotation.baseline",
        family: "annotation-vertical-align",
        code: 0,
    },
    StaticDocumentVocabulary {
        name: "annotation.top",
        family: "annotation-vertical-align",
        code: 1,
    },
    StaticDocumentVocabulary {
        name: "annotation.bottom",
        family: "annotation-vertical-align",
        code: 2,
    },
    StaticDocumentVocabulary {
        name: "annotation.center",
        family: "annotation-vertical-align",
        code: 3,
    },
    StaticDocumentVocabulary {
        name: "axis-sides.none",
        family: "axis-sides",
        code: 0,
    },
    StaticDocumentVocabulary {
        name: "axis-sides.low",
        family: "axis-sides",
        code: 1,
    },
    StaticDocumentVocabulary {
        name: "axis-sides.high",
        family: "axis-sides",
        code: 2,
    },
    StaticDocumentVocabulary {
        name: "axis-sides.both",
        family: "axis-sides",
        code: 3,
    },
    StaticDocumentVocabulary {
        name: "document.background",
        family: "document-flag",
        code: 1,
    },
    StaticDocumentVocabulary {
        name: "document.optimize-png",
        family: "document-flag",
        code: 2,
    },
    StaticDocumentVocabulary {
        name: "document.tight-crop",
        family: "document-flag",
        code: 4,
    },
    StaticDocumentVocabulary {
        name: "document.title-x-center",
        family: "document-flag",
        code: 8,
    },
    StaticDocumentVocabulary {
        name: "panel.x-chrome-metrics",
        family: "panel-flag",
        code: 1,
    },
    StaticDocumentVocabulary {
        name: "panel.y-chrome-metrics",
        family: "panel-flag",
        code: 2,
    },
    StaticDocumentVocabulary {
        name: "panel.colorbar-layout",
        family: "panel-flag",
        code: 4,
    },
    StaticDocumentVocabulary {
        name: "panel.annotation-font-size",
        family: "panel-flag",
        code: 8,
    },
    StaticDocumentVocabulary {
        name: "panel.arrow-metrics",
        family: "panel-flag",
        code: 16,
    },
    StaticDocumentVocabulary {
        name: "panel.axis-sides",
        family: "panel-flag",
        code: 32,
    },
    StaticDocumentVocabulary {
        name: "panel.annotation-text-flags",
        family: "panel-flag",
        code: 64,
    },
    StaticDocumentVocabulary {
        name: "panel.annotation-padding",
        family: "panel-flag",
        code: 128,
    },
    StaticDocumentVocabulary {
        name: "panel.title-style",
        family: "panel-flag",
        code: 256,
    },
    StaticDocumentVocabulary {
        name: "panel.annotation-vertical-align",
        family: "panel-flag",
        code: 512,
    },
    StaticDocumentVocabulary {
        name: "title.anchor-start",
        family: "title-anchor",
        code: 0,
    },
    StaticDocumentVocabulary {
        name: "title.anchor-middle",
        family: "title-anchor",
        code: 1,
    },
    StaticDocumentVocabulary {
        name: "title.anchor-end",
        family: "title-anchor",
        code: 2,
    },
    StaticDocumentVocabulary {
        name: "text.regular",
        family: "text-flags",
        code: 0,
    },
    StaticDocumentVocabulary {
        name: "text.italic",
        family: "text-flags",
        code: 1,
    },
    StaticDocumentVocabulary {
        name: "text.bold",
        family: "text-flags",
        code: 2,
    },
    StaticDocumentVocabulary {
        name: "text.bold-italic",
        family: "text-flags",
        code: 3,
    },
    StaticDocumentVocabulary {
        name: "label.anchor-start",
        family: "label-anchor",
        code: 0,
    },
    StaticDocumentVocabulary {
        name: "label.anchor-middle",
        family: "label-anchor",
        code: 1,
    },
    StaticDocumentVocabulary {
        name: "label.anchor-end",
        family: "label-anchor",
        code: 2,
    },
    StaticDocumentVocabulary {
        name: "label.baseline",
        family: "label-vertical-align",
        code: 1,
    },
    StaticDocumentVocabulary {
        name: "label.top",
        family: "label-vertical-align",
        code: 0,
    },
    StaticDocumentVocabulary {
        name: "label.center",
        family: "label-vertical-align",
        code: 3,
    },
    StaticDocumentVocabulary {
        name: "label.bottom",
        family: "label-vertical-align",
        code: 2,
    },
    StaticDocumentVocabulary {
        name: "legend.line",
        family: "legend-item",
        code: 0,
    },
    StaticDocumentVocabulary {
        name: "legend.scatter",
        family: "legend-item",
        code: 1,
    },
    StaticDocumentVocabulary {
        name: "legend.patch",
        family: "legend-item",
        code: 2,
    },
    StaticDocumentVocabulary {
        name: "legend.anchored",
        family: "envelope",
        code: 0,
    },
    StaticDocumentVocabulary {
        name: "legend.multicolumn",
        family: "envelope",
        code: 1,
    },
    StaticDocumentVocabulary {
        name: "label.rotated-opacity",
        family: "envelope",
        code: 2,
    },
    StaticDocumentVocabulary {
        name: "panel.signed-placement",
        family: "envelope",
        code: 3,
    },
    StaticDocumentVocabulary {
        name: "panel.overlap",
        family: "envelope",
        code: 4,
    },
    StaticDocumentVocabulary {
        name: "panel.multiple",
        family: "envelope",
        code: 5,
    },
    StaticDocumentVocabulary {
        name: "colorbar.shared",
        family: "envelope",
        code: 6,
    },
    StaticDocumentVocabulary {
        name: "colorbar.vertical",
        family: "envelope",
        code: 7,
    },
    StaticDocumentVocabulary {
        name: "colorbar.horizontal",
        family: "envelope",
        code: 8,
    },
    StaticDocumentVocabulary {
        name: "document.title",
        family: "envelope",
        code: 9,
    },
];

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct StaticDocumentCase {
    pub name: &'static str,
    pub vocabulary: &'static [&'static str],
    pub formats: &'static [&'static str],
}

/// Exhaustive sidecar witnesses; the runtime test must implement these exact
/// case names and run every declared format. These are explicit XYST authoring,
/// not a claim that Node automatically projects Figure/facet objects to XYST.
pub const STATIC_DOCUMENT_CASES: &[StaticDocumentCase] = &[
    StaticDocumentCase {
        name: "document_title_x_center",
        vocabulary: &[
            "document.title-x-center",
            "document.title",
            "title.anchor-middle",
        ],
        formats: STATIC_DOCUMENT_FORMATS,
    },
    StaticDocumentCase {
        name: "document_panel_colorbar_log_scale",
        vocabulary: &["panel.colorbar-log-scale"],
        formats: STATIC_DOCUMENT_FORMATS,
    },
    StaticDocumentCase {
        name: "document_panel_colorbar_extend_min",
        vocabulary: &["panel.colorbar-extend-min"],
        formats: STATIC_DOCUMENT_FORMATS,
    },
    StaticDocumentCase {
        name: "document_panel_colorbar_extend_max",
        vocabulary: &["panel.colorbar-extend-max"],
        formats: STATIC_DOCUMENT_FORMATS,
    },
    StaticDocumentCase {
        name: "document_panel_colorbar_pyplot_label",
        vocabulary: &["panel.colorbar-pyplot-label"],
        formats: STATIC_DOCUMENT_FORMATS,
    },
    StaticDocumentCase {
        name: "document_colorbar_extend_both",
        vocabulary: &["panel.colorbar-extend-min", "panel.colorbar-extend-max"],
        formats: STATIC_DOCUMENT_FORMATS,
    },
    StaticDocumentCase {
        name: "document_annotation_baseline",
        vocabulary: &["annotation.baseline"],
        formats: STATIC_DOCUMENT_FORMATS,
    },
    StaticDocumentCase {
        name: "document_annotation_top",
        vocabulary: &["annotation.top"],
        formats: STATIC_DOCUMENT_FORMATS,
    },
    StaticDocumentCase {
        name: "document_annotation_bottom",
        vocabulary: &["annotation.bottom"],
        formats: STATIC_DOCUMENT_FORMATS,
    },
    StaticDocumentCase {
        name: "document_annotation_center",
        vocabulary: &["annotation.center"],
        formats: STATIC_DOCUMENT_FORMATS,
    },
    StaticDocumentCase {
        name: "document_axis_sides_none",
        vocabulary: &["axis-sides.none"],
        formats: STATIC_DOCUMENT_FORMATS,
    },
    StaticDocumentCase {
        name: "document_axis_sides_low",
        vocabulary: &["axis-sides.low"],
        formats: STATIC_DOCUMENT_FORMATS,
    },
    StaticDocumentCase {
        name: "document_axis_sides_high",
        vocabulary: &["axis-sides.high"],
        formats: STATIC_DOCUMENT_FORMATS,
    },
    StaticDocumentCase {
        name: "document_axis_sides_both",
        vocabulary: &["axis-sides.both"],
        formats: STATIC_DOCUMENT_FORMATS,
    },
    StaticDocumentCase {
        name: "document_grid_dash",
        vocabulary: &["panel.grid-dash"],
        formats: STATIC_DOCUMENT_FORMATS,
    },
    StaticDocumentCase {
        name: "document_defaults",
        vocabulary: &[],
        formats: STATIC_DOCUMENT_FORMATS,
    },
    StaticDocumentCase {
        name: "document_background",
        vocabulary: &["document.background"],
        formats: STATIC_DOCUMENT_FORMATS,
    },
    StaticDocumentCase {
        name: "document_optimized_png",
        vocabulary: &["document.optimize-png"],
        formats: STATIC_DOCUMENT_FORMATS,
    },
    StaticDocumentCase {
        name: "document_tight_crop",
        vocabulary: &["document.tight-crop"],
        formats: STATIC_DOCUMENT_FORMATS,
    },
    StaticDocumentCase {
        name: "document_panel_chrome",
        vocabulary: &[
            "panel.x-chrome-metrics",
            "panel.y-chrome-metrics",
            "panel.axis-sides",
        ],
        formats: STATIC_DOCUMENT_FORMATS,
    },
    StaticDocumentCase {
        name: "document_annotation_style",
        vocabulary: &[
            "panel.annotation-font-size",
            "panel.annotation-text-flags",
            "panel.annotation-padding",
            "panel.annotation-vertical-align",
            "panel.arrow-metrics",
        ],
        formats: STATIC_DOCUMENT_FORMATS,
    },
    StaticDocumentCase {
        name: "document_panel_title",
        vocabulary: &["panel.title-style"],
        formats: STATIC_DOCUMENT_FORMATS,
    },
    StaticDocumentCase {
        name: "document_title_start",
        vocabulary: &["document.title", "title.anchor-start", "text.regular"],
        formats: STATIC_DOCUMENT_FORMATS,
    },
    StaticDocumentCase {
        name: "document_title_middle",
        vocabulary: &["title.anchor-middle", "text.italic"],
        formats: STATIC_DOCUMENT_FORMATS,
    },
    StaticDocumentCase {
        name: "document_title_end",
        vocabulary: &["title.anchor-end", "text.bold"],
        formats: STATIC_DOCUMENT_FORMATS,
    },
    StaticDocumentCase {
        name: "document_title_bold_italic",
        vocabulary: &["text.bold-italic"],
        formats: STATIC_DOCUMENT_FORMATS,
    },
    StaticDocumentCase {
        name: "document_labels_start_top",
        vocabulary: &["label.anchor-start", "label.top"],
        formats: STATIC_DOCUMENT_FORMATS,
    },
    StaticDocumentCase {
        name: "document_labels_middle_center",
        vocabulary: &["label.anchor-middle", "label.center"],
        formats: STATIC_DOCUMENT_FORMATS,
    },
    StaticDocumentCase {
        name: "document_labels_end_bottom",
        vocabulary: &["label.anchor-end", "label.bottom"],
        formats: STATIC_DOCUMENT_FORMATS,
    },
    StaticDocumentCase {
        name: "document_labels_baseline_rotated",
        vocabulary: &["label.baseline", "label.rotated-opacity"],
        formats: STATIC_DOCUMENT_FORMATS,
    },
    StaticDocumentCase {
        name: "document_legend",
        vocabulary: &[
            "legend.line",
            "legend.scatter",
            "legend.patch",
            "legend.anchored",
            "legend.multicolumn",
        ],
        formats: STATIC_DOCUMENT_FORMATS,
    },
    StaticDocumentCase {
        name: "document_signed_panels",
        vocabulary: &["panel.signed-placement", "panel.multiple"],
        formats: STATIC_DOCUMENT_FORMATS,
    },
    StaticDocumentCase {
        name: "document_overlap",
        vocabulary: &["panel.overlap"],
        formats: STATIC_DOCUMENT_FORMATS,
    },
    StaticDocumentCase {
        name: "document_colorbar_vertical",
        vocabulary: &["panel.colorbar-layout", "colorbar.vertical"],
        formats: STATIC_DOCUMENT_FORMATS,
    },
    StaticDocumentCase {
        name: "document_colorbar_horizontal",
        vocabulary: &["colorbar.horizontal"],
        formats: STATIC_DOCUMENT_FORMATS,
    },
    StaticDocumentCase {
        name: "document_shared_colorbar",
        vocabulary: &["colorbar.shared"],
        formats: STATIC_DOCUMENT_FORMATS,
    },
    StaticDocumentCase {
        name: "document_half_scale",
        vocabulary: &[],
        formats: STATIC_DOCUMENT_FORMATS,
    },
    StaticDocumentCase {
        name: "document_double_scale",
        vocabulary: &[],
        formats: STATIC_DOCUMENT_FORMATS,
    },
    StaticDocumentCase {
        name: "document_jpeg_quality_low",
        vocabulary: &[],
        formats: STATIC_DOCUMENT_FORMATS,
    },
    StaticDocumentCase {
        name: "document_jpeg_quality_high",
        vocabulary: &[],
        formats: STATIC_DOCUMENT_FORMATS,
    },
];

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct StaticDocumentAuthoredWitness {
    pub name: &'static str,
    pub vocabulary: &'static [&'static str],
}

/// Independently public-authored Python/Node fixtures in
/// test_static_document_authored_cross_host.py. The Node side authors explicit
/// envelope facts using public staticDocumentEncode; no Python bytes are sent.
pub const STATIC_DOCUMENT_AUTHORED_WITNESSES: &[StaticDocumentAuthoredWitness] = &[
    StaticDocumentAuthoredWitness {
        name: "styled_line",
        vocabulary: &[
            "panel.x-chrome-metrics",
            "panel.y-chrome-metrics",
            "panel.axis-sides",
        ],
    },
    StaticDocumentAuthoredWitness {
        name: "styled_scatter",
        vocabulary: &[
            "panel.x-chrome-metrics",
            "panel.y-chrome-metrics",
            "panel.axis-sides",
        ],
    },
    StaticDocumentAuthoredWitness {
        name: "text_annotation",
        vocabulary: &[
            "panel.annotation-font-size",
            "panel.annotation-text-flags",
            "panel.annotation-vertical-align",
        ],
    },
    StaticDocumentAuthoredWitness {
        name: "anchored_legend",
        vocabulary: &["legend.line", "legend.scatter", "legend.anchored"],
    },
    StaticDocumentAuthoredWitness {
        name: "continuous_colorbar",
        vocabulary: &["colorbar.vertical"],
    },
    StaticDocumentAuthoredWitness {
        name: "facet_panels",
        vocabulary: &["panel.multiple", "document.title", "title.anchor-middle"],
    },
];

/// Existing Scene fail-close fixtures whose exact public admission changed
/// during #873. Keep the fixtures; resolve each against the integrated product
/// before reporting the combined registry green.
pub const STATIC_DOCUMENT_RECHECK_SCENE_CASES: &[&str] =
    &["title_options", "extra_legend", "colorbar_option"];

/// Corrupt envelopes must fail at both host boundaries without renderer retry.
/// Rows refer to exact mutation builders in the integrated runtime corpus.
pub const STATIC_DOCUMENT_REJECTIONS: &[&str] = &[
    "centered_title_x_nonzero",
    "header_truncated",
    "version_unknown",
    "header_flags_unknown",
    "header_reserved_nonzero",
    "panels_empty",
    "dimensions_zero",
    "panel_flags_unknown",
    "panel_inactive_nonzero",
    "panel_ranges_overlap",
    "panel_scene_corrupt",
    "title_invalid_utf8",
    "title_nul",
    "title_anchor_unknown",
    "text_flags_unknown",
    "label_alignment_unknown",
    "label_opacity_invalid",
    "legend_kind_unknown",
    "legend_reserved_nonzero",
    "decoration_trailing_bytes",
    "document_trailing_bytes",
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
    let vocabulary = STATIC_DOCUMENT_VOCABULARY
        .iter()
        .map(|row| {
            format!(
                "{{\"name\":\"{}\",\"family\":\"{}\",\"code\":{}}}",
                row.name, row.family, row.code
            )
        })
        .collect::<Vec<_>>()
        .join(",");
    let documents = STATIC_DOCUMENT_CASES
        .iter()
        .map(|row| {
            format!(
                "{{\"name\":\"{}\",\"vocabulary\":[{}],\"formats\":[{}]}}",
                row.name,
                strings(row.vocabulary),
                strings(row.formats)
            )
        })
        .collect::<Vec<_>>()
        .join(",");
    let witnesses = STATIC_DOCUMENT_AUTHORED_WITNESSES.iter().map(|row| format!(
        "{{\"name\":\"{}\",\"vocabulary\":[{}],\"formats\":[{}],\"python\":\"public-composition-export\",\"node\":\"public-figure-explicit-xyst\"}}",
        row.name, strings(row.vocabulary), strings(STATIC_DOCUMENT_FORMATS)
    )).collect::<Vec<_>>().join(",");
    format!(
        "{{\"schema\":\"xyg.static-export-support-registry/v1\",\"required_edge_concerns\":[{}],\"shapes\":[{shapes}],\"edge_cases\":[{edges}],\"fail_close\":[{misses}],\"document\":{{\"version\":1,\"formats\":[{}],\"vocabulary\":[{vocabulary}],\"cases\":[{documents}],\"authored_witnesses\":[{witnesses}],\"rejections\":[{}],\"scene_cases_requiring_recheck\":[{}]}}}}\n",
        strings(REQUIRED_EDGE_CONCERNS), strings(STATIC_DOCUMENT_FORMATS), strings(STATIC_DOCUMENT_REJECTIONS), strings(STATIC_DOCUMENT_RECHECK_SCENE_CASES)
    )
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::collections::{BTreeMap, BTreeSet};

    #[test]
    fn every_document_vocabulary_row_has_all_format_witnesses() {
        assert_eq!(
            STATIC_DOCUMENT_FORMATS,
            &["svg", "png", "pdf", "jpeg", "webp"]
        );
        let rejection_names: BTreeSet<_> = STATIC_DOCUMENT_REJECTIONS.iter().copied().collect();
        assert_eq!(rejection_names.len(), STATIC_DOCUMENT_REJECTIONS.len());
        let family_codes: BTreeSet<_> = STATIC_DOCUMENT_VOCABULARY
            .iter()
            .map(|row| (row.family, row.code))
            .collect();
        assert_eq!(family_codes.len(), STATIC_DOCUMENT_VOCABULARY.len());
        let vocabulary: BTreeSet<_> = STATIC_DOCUMENT_VOCABULARY
            .iter()
            .map(|row| row.name)
            .collect();
        assert_eq!(vocabulary.len(), STATIC_DOCUMENT_VOCABULARY.len());
        let covered: BTreeSet<_> = STATIC_DOCUMENT_CASES
            .iter()
            .flat_map(|row| row.vocabulary.iter().copied())
            .collect();
        assert_eq!(vocabulary, covered);
        let names: BTreeSet<_> = STATIC_DOCUMENT_CASES.iter().map(|row| row.name).collect();
        assert_eq!(names.len(), STATIC_DOCUMENT_CASES.len());
        for row in STATIC_DOCUMENT_CASES {
            assert_eq!(row.formats, STATIC_DOCUMENT_FORMATS, "{}", row.name);
        }
        for (family, mask) in [
            ("document-flag", STATIC_DOCUMENT_HEADER_FLAGS),
            ("panel-flag", STATIC_DOCUMENT_PANEL_FLAGS),
        ] {
            let mut actual = 0;
            for row in STATIC_DOCUMENT_VOCABULARY
                .iter()
                .filter(|row| row.family == family)
            {
                assert!(row.code.is_power_of_two());
                assert_eq!(actual & row.code, 0);
                actual |= row.code;
            }
            assert_eq!(actual, mask);
        }
        let witness_names: BTreeSet<_> = STATIC_DOCUMENT_AUTHORED_WITNESSES
            .iter()
            .map(|row| row.name)
            .collect();
        assert_eq!(
            witness_names.len(),
            STATIC_DOCUMENT_AUTHORED_WITNESSES.len()
        );
        for witness in STATIC_DOCUMENT_AUTHORED_WITNESSES {
            assert!(!witness.vocabulary.is_empty());
            assert!(witness
                .vocabulary
                .iter()
                .all(|name| vocabulary.contains(name)));
        }
    }

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
