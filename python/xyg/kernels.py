"""Kernel dispatch: the native Rust core is required.

xyg computes through a compiled Rust C-ABI core. There is no pure-Python
fallback: if the native core cannot be loaded — an unsupported platform with no
published wheel and no local Rust build — importing this module raises
ImportError with remediation, rather than silently degrading (§33: no-wheel
behavior is defined, and it is a loud failure).

`BACKEND` stays inspectable (always ``"native"``) so tooling can keep asserting
which path served a figure (§28: every tier decision is observable).
"""

from __future__ import annotations

try:
    from . import _native as _impl
except ImportError as err:  # pragma: no cover - platform-dependent
    raise ImportError(
        "xyg requires its native Rust core, which could not be loaded "
        f"({err}). Prebuilt wheels cover Linux glibc and musl (x86-64, aarch64, "
        "armv7), macOS (x86-64, Apple Silicon), and Windows (x86, x64, arm64); "
        "on those platforms `pip install xyg` needs no toolchain. On any "
        "other platform, install a Rust toolchain (https://rustup.rs) and "
        "reinstall from source (or run `cargo build --release`)."
    ) from err

BACKEND = "native"

CSS_DECLARATION = _impl.CSS_DECLARATION
CSS_COLOR = _impl.CSS_COLOR
CSS_LENGTH = _impl.CSS_LENGTH
CSS_NUMBER = _impl.CSS_NUMBER

css_check = _impl.css_check
css_color_rgba = _impl.css_color_rgba
css_is_functional = _impl.css_is_functional
clip_quantize_u8 = _impl.clip_quantize_u8
colormap_rgba = _impl.colormap_rgba
colormap_rgba_canonical = _impl.colormap_rgba_canonical
colormap_lut = _impl.colormap_lut
correlation = _impl.correlation
density_rgba = _impl.density_rgba
density_rgba_linear = _impl.density_rgba_linear
density_log_u8 = _impl.density_log_u8
density_overlay_opacity = _impl.density_overlay_opacity
DENSITY_OVERLAY_NONE = _impl.DENSITY_OVERLAY_NONE
DENSITY_OVERLAY_ROWS_EXCEED_U32 = _impl.DENSITY_OVERLAY_ROWS_EXCEED_U32
DENSITY_OVERLAY_STATIC_RASTER = _impl.DENSITY_OVERLAY_STATIC_RASTER
density_overlay_omitted_wire = _impl.density_overlay_omitted_wire
density_bin_window = _impl.density_bin_window
density_bin_coord_endpoints = _impl.density_bin_coord_endpoints
density_emit_plan = _impl.density_emit_plan
density_color_classify = _impl.density_color_classify
density_trace_color_classify = _impl.density_trace_color_classify
density_uses_channel_colormap = _impl.density_uses_channel_colormap
density_constant_color_wire_admit = _impl.density_constant_color_wire_admit
density_categorical_color_wire_admit = _impl.density_categorical_color_wire_admit
density_mean_color_wire_admit = _impl.density_mean_color_wire_admit
density_channels_dropped_compat = _impl.density_channels_dropped_compat
density_dropped_channel_wire_admit = _impl.density_dropped_channel_wire_admit
density_mean_color_rgba_wire_admit = _impl.density_mean_color_rgba_wire_admit
density_wasm_source_admit = _impl.density_wasm_source_admit
DENSITY_WASM_DENSITY_NONE = _impl.DENSITY_WASM_DENSITY_NONE
DENSITY_WASM_DENSITY_AUTOMATIC = _impl.DENSITY_WASM_DENSITY_AUTOMATIC
DENSITY_WASM_DENSITY_UNSUPPORTED = _impl.DENSITY_WASM_DENSITY_UNSUPPORTED
density_wasm_density_wire_kind = _impl.density_wasm_density_wire_kind
DENSITY_REDUCTION_BIN2D = _impl.DENSITY_REDUCTION_BIN2D
DENSITY_REDUCTION_PYRAMID_COUNT = _impl.DENSITY_REDUCTION_PYRAMID_COUNT
density_reduction_kind = _impl.density_reduction_kind
density_format_binning = _impl.density_format_binning
density_full_identity = _impl.density_full_identity
density_grid_path = _impl.density_grid_path
density_grid_path_identity_state = _impl.density_grid_path_identity_state
density_pyramid_preflight = _impl.density_pyramid_preflight
density_wasm_eligible = _impl.density_wasm_eligible
delaunay_triangles = _impl.delaunay_triangles
zone_maps = _impl.zone_maps
zone_maps_pair = _impl.zone_maps_pair
encode_f32 = _impl.encode_f32
encoded_column_meta = _impl.encoded_column_meta
f32_safe_scale = _impl.f32_safe_scale
geometry_offset = _impl.geometry_offset
scale_pins_offset = _impl.scale_pins_offset
scene_annotation_style_admit = _impl.scene_annotation_style_admit
scene_arrays_equal = _impl.scene_arrays_equal
scene_channel_constant_css = _impl.scene_channel_constant_css
scene_constant_color_admit = _impl.scene_constant_color_admit
scene_curve_classify = _impl.scene_curve_classify
scene_dash_admit = _impl.scene_dash_admit
scene_fill_gradient_admit = _impl.scene_fill_gradient_admit
scene_finite_all = _impl.scene_finite_all
scene_gradient_dir = _impl.scene_gradient_dir
scene_gradient_solid_css = _impl.scene_gradient_solid_css
scene_gradient_spec_pack = _impl.scene_gradient_spec_pack
scene_marker_blob_pack = _impl.scene_marker_blob_pack
scene_xytc_symbol_int_pack = _impl.scene_xytc_symbol_int_pack
scene_xytc_color2_flags_pack = _impl.scene_xytc_color2_flags_pack
scene_xytc_meta_flags_pack = _impl.scene_xytc_meta_flags_pack
scene_xytc_paint_presence_pack = _impl.scene_xytc_paint_presence_pack
scene_xytc_dash_pattern_pack = _impl.scene_xytc_dash_pattern_pack
scene_xytc_opacity_pack = _impl.scene_xytc_opacity_pack
scene_xytc_hex_pitch_pack = _impl.scene_xytc_hex_pitch_pack
scene_xytc_stroke_perimeter_pack = _impl.scene_xytc_stroke_perimeter_pack
scene_xytc_numeric_style_pack = _impl.scene_xytc_numeric_style_pack
scene_xytc_color_channel_pack = _impl.scene_xytc_color_channel_pack
scene_xytc_radius_pack = _impl.scene_xytc_radius_pack
scene_gradient_space = _impl.scene_gradient_space
scene_heatmap_colormap_admit = _impl.scene_heatmap_colormap_admit
scene_xyta_colormap_pack = _impl.scene_xyta_colormap_pack
scene_xyhf_colormap_pack = _impl.scene_xyhf_colormap_pack
scene_heatmap_extent_admit = _impl.scene_heatmap_extent_admit
scene_heatmap_shape_admit = _impl.scene_heatmap_shape_admit
scene_hidden_or_per_item_admit = _impl.scene_hidden_or_per_item_admit
scene_hexbin_colormap_plane_admit = _impl.scene_hexbin_colormap_plane_admit
scene_hexbin_pitch_admit = _impl.scene_hexbin_pitch_admit
scene_hexbin_reduce_admit = _impl.scene_hexbin_reduce_admit
scene_hexbin_rgba_plane_admit = _impl.scene_hexbin_rgba_plane_admit
scene_item_apply_opacity = _impl.scene_item_apply_opacity
scene_item_fill_t = _impl.scene_item_fill_t
scene_item_widths_admit = _impl.scene_item_widths_admit
scene_kind_admit = _impl.scene_kind_admit
scene_kind_class = _impl.scene_kind_class
scene_linear_gradient_prefix = _impl.scene_linear_gradient_prefix
scene_linecap_admit = _impl.scene_linecap_admit
scene_marker_glyph_admit = _impl.scene_marker_glyph_admit
scene_marker_path_admit = _impl.scene_marker_path_admit
scene_mesh_paint_plane_admit = _impl.scene_mesh_paint_plane_admit
scene_parse_linear_gradient = _impl.scene_parse_linear_gradient
scene_rect_extra_flags = _impl.scene_rect_extra_flags
scene_ribbon_color2_classify = _impl.scene_ribbon_color2_classify
scene_scatter_paint_channel_admit = _impl.scene_scatter_paint_channel_admit
scene_tick_anchor = _impl.scene_tick_anchor
scene_tick_label_strategy = _impl.scene_tick_label_strategy
factorize_fixed = _impl.factorize_fixed
factorize_fixed_u8 = _impl.factorize_fixed_u8
factorize_fixed_u8_counts = _impl.factorize_fixed_u8_counts
factorize_unicode1_u8_counts = _impl.factorize_unicode1_u8_counts
transition_keys_fixed = _impl.transition_keys_fixed
m4_indices = _impl.m4_indices
marching_squares = _impl.marching_squares
marching_triangles = _impl.marching_triangles
is_sorted = _impl.is_sorted
argsort_stable = _impl.argsort_stable
arrow_end_decoration = _impl.arrow_end_decoration
arrow_geometry = _impl.arrow_geometry
arrow_shaft_points = _impl.arrow_shaft_points
arrow_style_pack = _impl.arrow_style_pack
arrow_shapes = _impl.arrow_shapes
arrow_taper_polygon = _impl.arrow_taper_polygon
arrow_trim_polyline_end = _impl.arrow_trim_polyline_end
min_max = _impl.min_max
continuous_domain = _impl.continuous_domain
direct_rgba_admit = _impl.direct_rgba_admit
bin_2d = _impl.bin_2d
binned_ecdf = _impl.binned_ecdf
bin_2d_f32 = _impl.bin_2d_f32
bin_2d_indices = _impl.bin_2d_indices
bin_2d_mean_color = _impl.bin_2d_mean_color
bin_2d_sample_range = _impl.bin_2d_sample_range
bin_2d_stratified_sample_range_u8_counted = _impl.bin_2d_stratified_sample_range_u8_counted
histogram_uniform = _impl.histogram_uniform
histogram_bins = _impl.histogram_bins
heatmap_rgba = _impl.heatmap_rgba
histogram2d = _impl.histogram2d
indexed_triangles = _impl.indexed_triangles
normalize_f32 = _impl.normalize_f32
valid_indices_f64 = _impl.valid_indices_f64
remap_u8 = _impl.remap_u8
range_indices = _impl.range_indices
range_indices_rows = _impl.range_indices_rows
polygon_select = _impl.polygon_select
sample_mask = _impl.sample_mask
sample_range_indices = _impl.sample_range_indices
stratified_sample_range_u8 = _impl.stratified_sample_range_u8
sector_triangles = _impl.sector_triangles
stacked_bounds = _impl.stacked_bounds
bar_stack = _impl.bar_stack
streamlines = _impl.streamlines
triangle_edges = _impl.triangle_edges
local_log_density = _impl.local_log_density
pyramid_build = _impl.pyramid_build
pyramid_build_color = _impl.pyramid_build_color
pyramid_build_from_stream = _impl.pyramid_build_from_stream
pyramid_append = _impl.pyramid_append
pyramid_append_from_stream = _impl.pyramid_append_from_stream
pyramid_count = _impl.pyramid_count
pyramid_compose = _impl.pyramid_compose
pyramid_compose_color = _impl.pyramid_compose_color
pyramid_free = _impl.pyramid_free
pyramid_spill = _impl.pyramid_spill
tile_store_compose = _impl.tile_store_compose
tile_store_compose_color = _impl.tile_store_compose_color
tile_store_append = _impl.tile_store_append
tile_store_stats = _impl.tile_store_stats
tile_store_free = _impl.tile_store_free
tile_budget_set = _impl.tile_budget_set
stream_new = _impl.stream_new
stream_append = _impl.stream_append
stream_seal = _impl.stream_seal
stream_free = _impl.stream_free
stream_len = _impl.stream_len
stream_capacity = _impl.stream_capacity
stream_view = _impl.stream_view
stream_copy = _impl.stream_copy
stream_zone_maps = _impl.stream_zone_maps
polygon_triangles = _impl.polygon_triangles
quad_mesh_triangles = _impl.quad_mesh_triangles
rasterize = _impl.rasterize
rasterize_png = _impl.rasterize_png
rfft = _impl.rfft
spectrogram = _impl.spectrogram
stratified_sample_mask = _impl.stratified_sample_mask
vector_segments = _impl.vector_segments
welch_spectra = _impl.welch_spectra
weighted_ecdf = _impl.weighted_ecdf
drill_decision = _impl.drill_decision
lod_grid_shape = _impl.lod_grid_shape
lod_plan = _impl.lod_plan
payload_tier = _impl.payload_tier
payload_m4_indices = _impl.payload_m4_indices
payload_visible_mask = _impl.payload_visible_mask
payload_visible_needed = _impl.payload_visible_needed
payload_visible_indices = _impl.payload_visible_indices
payload_even_indices = _impl.payload_even_indices
payload_errorbar_role_keys = _impl.payload_errorbar_role_keys
payload_errorbar_role_maps = _impl.payload_errorbar_role_maps
payload_segments_emit_gather = _impl.payload_segments_emit_gather
payload_trace_channels_ship_attach = _impl.payload_trace_channels_ship_attach
payload_transition_entry_attach = _impl.payload_transition_entry_attach
payload_base_entry_plan = _impl.payload_base_entry_plan
payload_nonxy_emit_plan = _impl.payload_nonxy_emit_plan
PAYLOAD_NONXY_KIND_RECT = _impl.PAYLOAD_NONXY_KIND_RECT
PAYLOAD_NONXY_KIND_HEXBIN = _impl.PAYLOAD_NONXY_KIND_HEXBIN
PAYLOAD_NONXY_KIND_DENSITY_SAMPLE = _impl.PAYLOAD_NONXY_KIND_DENSITY_SAMPLE
PAYLOAD_SHIP_CHANNELS_ALWAYS = 0
PAYLOAD_SHIP_CHANNELS_IF_COLOR = 1
payload_bar_compact_admit = _impl.payload_bar_compact_admit
payload_transition_keys_admit = _impl.payload_transition_keys_admit
payload_errorbar_indices = _impl.payload_errorbar_indices
payload_segment_budget = _impl.payload_segment_budget
payload_sample_target_indices = _impl.payload_sample_target_indices
paint_effective_rgba = _impl.paint_effective_rgba
quantiles = _impl.quantiles
box_stats = _impl.box_stats
box_geometry = _impl.box_geometry
hexbin = _impl.hexbin
hexbin_ingress = _impl.hexbin_ingress
hexbin_groups = _impl.hexbin_groups
legend_best_loc = _impl.legend_best_loc
legend_normalize = _impl.legend_normalize
monotone_tangents = _impl.monotone_tangents
ribbon_edge = _impl.ribbon_edge
ribbon_polygon = _impl.ribbon_polygon
curve_flatten = _impl.curve_flatten
rounded_rect_poly = _impl.rounded_rect_poly
violin_density = _impl.violin_density
violin_rects = _impl.violin_rects
histogram_edges = _impl.histogram_edges
histogram_mark_edges = _impl.histogram_mark_edges
contour_levels = _impl.contour_levels
wind_rose_bins = _impl.wind_rose_bins
contourf_densify = _impl.contourf_densify
contourf_bands = _impl.contourf_bands

__all__ = [
    "BACKEND",
    "CSS_COLOR",
    "CSS_DECLARATION",
    "CSS_LENGTH",
    "CSS_NUMBER",
    "DENSITY_OVERLAY_NONE",
    "DENSITY_OVERLAY_ROWS_EXCEED_U32",
    "DENSITY_OVERLAY_STATIC_RASTER",
    "DENSITY_REDUCTION_BIN2D",
    "DENSITY_REDUCTION_PYRAMID_COUNT",
    "DENSITY_WASM_DENSITY_AUTOMATIC",
    "DENSITY_WASM_DENSITY_NONE",
    "DENSITY_WASM_DENSITY_UNSUPPORTED",
    "PAYLOAD_NONXY_KIND_DENSITY_SAMPLE",
    "PAYLOAD_NONXY_KIND_HEXBIN",
    "PAYLOAD_NONXY_KIND_RECT",
    "PAYLOAD_SHIP_CHANNELS_ALWAYS",
    "PAYLOAD_SHIP_CHANNELS_IF_COLOR",
    "argsort_stable",
    "arrow_end_decoration",
    "arrow_geometry",
    "arrow_shaft_points",
    "arrow_shapes",
    "arrow_style_pack",
    "arrow_taper_polygon",
    "arrow_trim_polyline_end",
    "bar_stack",
    "bin_2d",
    "bin_2d_f32",
    "bin_2d_indices",
    "bin_2d_mean_color",
    "bin_2d_sample_range",
    "bin_2d_stratified_sample_range_u8_counted",
    "binned_ecdf",
    "box_geometry",
    "box_stats",
    "clip_quantize_u8",
    "colormap_lut",
    "colormap_rgba",
    "colormap_rgba_canonical",
    "continuous_domain",
    "contour_levels",
    "contourf_bands",
    "contourf_densify",
    "correlation",
    "css_check",
    "css_color_rgba",
    "css_is_functional",
    "curve_flatten",
    "delaunay_triangles",
    "density_bin_coord_endpoints",
    "density_bin_window",
    "density_categorical_color_wire_admit",
    "density_channels_dropped_compat",
    "density_color_classify",
    "density_constant_color_wire_admit",
    "density_dropped_channel_wire_admit",
    "density_emit_plan",
    "density_format_binning",
    "density_full_identity",
    "density_grid_path",
    "density_grid_path_identity_state",
    "density_log_u8",
    "density_mean_color_rgba_wire_admit",
    "density_mean_color_wire_admit",
    "density_overlay_omitted_wire",
    "density_overlay_opacity",
    "density_pyramid_preflight",
    "density_reduction_kind",
    "density_rgba",
    "density_rgba_linear",
    "density_trace_color_classify",
    "density_uses_channel_colormap",
    "density_wasm_density_wire_kind",
    "density_wasm_eligible",
    "density_wasm_source_admit",
    "direct_rgba_admit",
    "drill_decision",
    "encode_f32",
    "encoded_column_meta",
    "f32_safe_scale",
    "factorize_fixed",
    "factorize_fixed_u8",
    "factorize_fixed_u8_counts",
    "factorize_unicode1_u8_counts",
    "geometry_offset",
    "heatmap_rgba",
    "hexbin",
    "hexbin_groups",
    "hexbin_ingress",
    "histogram2d",
    "histogram_bins",
    "histogram_edges",
    "histogram_mark_edges",
    "histogram_uniform",
    "indexed_triangles",
    "is_sorted",
    "legend_best_loc",
    "legend_normalize",
    "local_log_density",
    "lod_grid_shape",
    "lod_plan",
    "m4_indices",
    "marching_squares",
    "marching_triangles",
    "min_max",
    "monotone_tangents",
    "normalize_f32",
    "paint_effective_rgba",
    "payload_bar_compact_admit",
    "payload_base_entry_plan",
    "payload_errorbar_indices",
    "payload_errorbar_role_keys",
    "payload_errorbar_role_maps",
    "payload_even_indices",
    "payload_m4_indices",
    "payload_nonxy_emit_plan",
    "payload_sample_target_indices",
    "payload_segment_budget",
    "payload_segments_emit_gather",
    "payload_tier",
    "payload_trace_channels_ship_attach",
    "payload_transition_entry_attach",
    "payload_transition_keys_admit",
    "payload_visible_indices",
    "payload_visible_mask",
    "payload_visible_needed",
    "polygon_select",
    "polygon_triangles",
    "pyramid_append",
    "pyramid_append_from_stream",
    "pyramid_build",
    "pyramid_build_color",
    "pyramid_build_from_stream",
    "pyramid_compose",
    "pyramid_compose_color",
    "pyramid_count",
    "pyramid_free",
    "pyramid_spill",
    "quad_mesh_triangles",
    "quantiles",
    "range_indices",
    "range_indices_rows",
    "rasterize",
    "rasterize_png",
    "remap_u8",
    "rfft",
    "ribbon_edge",
    "ribbon_polygon",
    "rounded_rect_poly",
    "sample_mask",
    "sample_range_indices",
    "scale_pins_offset",
    "scene_annotation_style_admit",
    "scene_arrays_equal",
    "scene_channel_constant_css",
    "scene_constant_color_admit",
    "scene_curve_classify",
    "scene_dash_admit",
    "scene_fill_gradient_admit",
    "scene_finite_all",
    "scene_gradient_dir",
    "scene_gradient_solid_css",
    "scene_gradient_space",
    "scene_gradient_spec_pack",
    "scene_heatmap_colormap_admit",
    "scene_heatmap_extent_admit",
    "scene_heatmap_shape_admit",
    "scene_hexbin_colormap_plane_admit",
    "scene_hexbin_pitch_admit",
    "scene_hexbin_reduce_admit",
    "scene_hexbin_rgba_plane_admit",
    "scene_hidden_or_per_item_admit",
    "scene_item_apply_opacity",
    "scene_item_fill_t",
    "scene_item_widths_admit",
    "scene_kind_admit",
    "scene_kind_class",
    "scene_linear_gradient_prefix",
    "scene_linecap_admit",
    "scene_marker_blob_pack",
    "scene_marker_glyph_admit",
    "scene_marker_path_admit",
    "scene_mesh_paint_plane_admit",
    "scene_parse_linear_gradient",
    "scene_rect_extra_flags",
    "scene_ribbon_color2_classify",
    "scene_scatter_paint_channel_admit",
    "scene_tick_anchor",
    "scene_tick_label_strategy",
    "scene_xyhf_colormap_pack",
    "scene_xyta_colormap_pack",
    "scene_xytc_color2_flags_pack",
    "scene_xytc_color_channel_pack",
    "scene_xytc_dash_pattern_pack",
    "scene_xytc_hex_pitch_pack",
    "scene_xytc_meta_flags_pack",
    "scene_xytc_numeric_style_pack",
    "scene_xytc_opacity_pack",
    "scene_xytc_paint_presence_pack",
    "scene_xytc_radius_pack",
    "scene_xytc_stroke_perimeter_pack",
    "scene_xytc_symbol_int_pack",
    "sector_triangles",
    "spectrogram",
    "stacked_bounds",
    "stratified_sample_mask",
    "stratified_sample_range_u8",
    "stream_append",
    "stream_capacity",
    "stream_copy",
    "stream_free",
    "stream_len",
    "stream_new",
    "stream_seal",
    "stream_view",
    "stream_zone_maps",
    "streamlines",
    "tile_budget_set",
    "tile_store_append",
    "tile_store_compose",
    "tile_store_compose_color",
    "tile_store_free",
    "tile_store_stats",
    "transition_keys_fixed",
    "triangle_edges",
    "valid_indices_f64",
    "vector_segments",
    "violin_density",
    "violin_rects",
    "weighted_ecdf",
    "welch_spectra",
    "wind_rose_bins",
    "zone_maps",
    "zone_maps_pair",
]
