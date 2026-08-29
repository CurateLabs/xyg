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
colormap_rgba = _impl.colormap_rgba
colormap_rgba_canonical = _impl.colormap_rgba_canonical
colormap_lut = _impl.colormap_lut
correlation = _impl.correlation
density_rgba = _impl.density_rgba
density_rgba_linear = _impl.density_rgba_linear
density_log_u8 = _impl.density_log_u8
density_bin_window = _impl.density_bin_window
density_emit_plan = _impl.density_emit_plan
density_format_binning = _impl.density_format_binning
density_full_identity = _impl.density_full_identity
density_grid_path = _impl.density_grid_path
density_pyramid_preflight = _impl.density_pyramid_preflight
density_wasm_eligible = _impl.density_wasm_eligible
delaunay_triangles = _impl.delaunay_triangles
zone_maps = _impl.zone_maps
zone_maps_pair = _impl.zone_maps_pair
encode_f32 = _impl.encode_f32
f32_safe_scale = _impl.f32_safe_scale
geometry_offset = _impl.geometry_offset
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
    "argsort_stable",
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
    "density_bin_window",
    "density_emit_plan",
    "density_format_binning",
    "density_full_identity",
    "density_grid_path",
    "density_log_u8",
    "density_pyramid_preflight",
    "density_rgba",
    "density_rgba_linear",
    "density_wasm_eligible",
    "direct_rgba_admit",
    "drill_decision",
    "encode_f32",
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
    "payload_even_indices",
    "payload_m4_indices",
    "payload_sample_target_indices",
    "payload_segment_budget",
    "payload_tier",
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
