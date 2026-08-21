"""Generated ctypes declarations. Do not edit; run scripts/gen_abi_manifest.py --write."""

from __future__ import annotations

import ctypes

# fmt: off

ABI_VERSION = 77
SIGNATURE_SHA256 = "ffe0b75c1cb2c4ccf5fc5e0c353621880575f3b192d4ac6409f179430218c60a"


def bind_abi_version(lib: ctypes.CDLL):
    function = lib.xyg_abi_version
    function.restype = ctypes.c_uint32
    function.argtypes = []
    return function


def bind_generated_abi(lib: ctypes.CDLL) -> None:
    # int32_t xyg_bar_stack(const double * pos, size_t n_items, const double * values, size_t n_series, const double * width, size_t width_len, const double * base, size_t base_len, uint32_t mode, uint32_t orientation, double * out_x0, double * out_x1, double * out_y0, double * out_y1)
    function = lib.xyg_bar_stack
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p]
    # int32_t xyg_bin_2d(const double * x, const double * y, size_t len, double x0, double x1, double y0, double y1, size_t w, size_t h, float * out)
    function = lib.xyg_bin_2d
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_size_t, ctypes.c_size_t, ctypes.c_void_p]
    # int32_t xyg_bin_2d_f32(const float * x, const float * y, size_t len, double x0, double x1, double y0, double y1, size_t w, size_t h, float * out)
    function = lib.xyg_bin_2d_f32
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_size_t, ctypes.c_size_t, ctypes.c_void_p]
    # size_t xyg_bin_2d_indices(const double * x, const double * y, size_t len, double x0, double x1, double y0, double y1, size_t w, size_t h, float * grid, uint32_t * idx)
    function = lib.xyg_bin_2d_indices
    function.restype = ctypes.c_size_t
    function.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_size_t, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_void_p]
    # int32_t xyg_bin_2d_mean_color(const double * x, const double * y, size_t len, const uint8_t * idx, const uint8_t * rgba, const uint8_t * lut, size_t lut_len, double x0, double x1, double y0, double y1, size_t w, size_t h, uint8_t * out)
    function = lib.xyg_bin_2d_mean_color
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_size_t, ctypes.c_size_t, ctypes.c_void_p]
    # size_t xyg_bin_2d_sample_range(const double * x, const double * y, size_t len, double x0, double x1, double y0, double y1, size_t w, size_t h, uint64_t seed, uint64_t threshold, float * grid, uint32_t * out, size_t capacity)
    function = lib.xyg_bin_2d_sample_range
    function.restype = ctypes.c_size_t
    function.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_size_t, ctypes.c_size_t, ctypes.c_uint64, ctypes.c_uint64, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t]
    # size_t xyg_bin_2d_stratified_sample_range_u8_counted(const double * x, const double * y, const uint8_t * groups, size_t len, const uint64_t * counts, size_t n_groups, double x0, double x1, double y0, double y1, size_t w, size_t h, uint64_t seed, double fraction, uint64_t min_count, float * grid, uint32_t * out, size_t capacity)
    function = lib.xyg_bin_2d_stratified_sample_range_u8_counted
    function.restype = ctypes.c_size_t
    function.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_size_t, ctypes.c_size_t, ctypes.c_uint64, ctypes.c_double, ctypes.c_uint64, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t]
    # int32_t xyg_box_stats(const double * data, size_t len, double * out_stats, double * out_outliers, size_t outliers_cap, size_t * out_n_outliers)
    function = lib.xyg_box_stats
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p]
    # size_t xyg_contourf_bands(const double * z, size_t rows, size_t cols, const double * xpos, const double * ypos, const double * edges, size_t n_edges, uint8_t extend_min, uint8_t extend_max, double * out_x0, double * out_y0, double * out_x1, double * out_y1, double * out_x2, double * out_y2, int64_t * out_slots, size_t capacity)
    function = lib.xyg_contourf_bands
    function.restype = ctypes.c_size_t
    function.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_uint8, ctypes.c_uint8, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t]
    # int32_t xyg_contourf_densify(const double * z, size_t rows, size_t cols, const double * xpos, const double * ypos, double * out_z, double * out_x, double * out_y, size_t out_z_cap, size_t out_x_cap, size_t out_y_cap, size_t * out_rows, size_t * out_cols)
    function = lib.xyg_contourf_densify
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_size_t, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_void_p]
    # int32_t xyg_correlation(const double * x, const double * y, size_t len, size_t max_lag, int32_t normalize, double * out_lag, double * out_correlation)
    function = lib.xyg_correlation
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_size_t, ctypes.c_int32, ctypes.c_void_p, ctypes.c_void_p]
    # int32_t xyg_css_check(uint32_t kind, const uint8_t * prop, size_t prop_len, const uint8_t * value, size_t value_len, float * out_rgba)
    function = lib.xyg_css_check
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_uint32, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p]
    # size_t xyg_delaunay_triangles(const double * x, const double * y, size_t len, int64_t * out, size_t capacity)
    function = lib.xyg_delaunay_triangles
    function.restype = ctypes.c_size_t
    function.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t]
    # int32_t xyg_density_log_u8(const float * grid, size_t len, uint8_t * out, double * out_max)
    function = lib.xyg_density_log_u8
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_void_p]
    # int32_t xyg_density_rgba(const uint8_t * encoded, size_t w, size_t h, double maximum, const uint8_t * stops, size_t stop_count, double opacity, uint8_t * out)
    function = lib.xyg_density_rgba
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_size_t, ctypes.c_double, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_double, ctypes.c_void_p]
    # int32_t xyg_drill_decision(uint64_t visible, double budget, int32_t in_drill, double exit_factor, int32_t * out_exact)
    function = lib.xyg_drill_decision
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_uint64, ctypes.c_double, ctypes.c_int32, ctypes.c_double, ctypes.c_void_p]
    # int32_t xyg_encode_f32(const double * data, size_t len, double offset, double scale, float * out)
    function = lib.xyg_encode_f32
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_double, ctypes.c_double, ctypes.c_void_p]
    # size_t xyg_factorize_fixed(const uint8_t * data, size_t len, size_t width, uint32_t * out_codes, uint32_t * out_unique_indices)
    function = lib.xyg_factorize_fixed
    function.restype = ctypes.c_size_t
    function.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_void_p]
    # size_t xyg_factorize_fixed_u8(const uint8_t * data, size_t len, size_t width, uint8_t * out_codes, uint32_t * out_unique_indices, size_t unique_capacity)
    function = lib.xyg_factorize_fixed_u8
    function.restype = ctypes.c_size_t
    function.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t]
    # size_t xyg_factorize_fixed_u8_counts(const uint8_t * data, size_t len, size_t width, uint8_t * out_codes, uint32_t * out_unique_indices, uint64_t * out_counts, size_t unique_capacity)
    function = lib.xyg_factorize_fixed_u8_counts
    function.restype = ctypes.c_size_t
    function.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t]
    # size_t xyg_factorize_unicode1_u8_counts(const uint32_t * data, size_t len, int32_t swap_endian, uint8_t * out_codes, uint32_t * out_unique_indices, uint64_t * out_counts, size_t unique_capacity)
    function = lib.xyg_factorize_unicode1_u8_counts
    function.restype = ctypes.c_size_t
    function.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_int32, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t]
    # uint32_t xyg_geo_column_crs(uint64_t handle)
    function = lib.xyg_geo_column_crs
    function.restype = ctypes.c_uint32
    function.argtypes = [ctypes.c_uint64]
    # int32_t xyg_geo_column_free(uint64_t handle)
    function = lib.xyg_geo_column_free
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_uint64]
    # uint32_t xyg_geo_column_geometry(uint64_t handle)
    function = lib.xyg_geo_column_geometry
    function.restype = ctypes.c_uint32
    function.argtypes = [ctypes.c_uint64]
    # size_t xyg_geo_column_len(uint64_t handle)
    function = lib.xyg_geo_column_len
    function.restype = ctypes.c_size_t
    function.argtypes = [ctypes.c_uint64]
    # uint64_t xyg_geo_column_new(uint32_t geometry, uint32_t crs, const double * xy, size_t xy_len, const uint8_t * validity, size_t validity_len, const uint64_t * feature_ids, const uint32_t * offsets0, size_t offsets0_len, const uint32_t * offsets1, size_t offsets1_len, const uint32_t * offsets2, size_t offsets2_len, int32_t * out_error)
    function = lib.xyg_geo_column_new
    function.restype = ctypes.c_uint64
    function.argtypes = [ctypes.c_uint32, ctypes.c_uint32, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p]
    # size_t xyg_geo_column_vertex_count(uint64_t handle)
    function = lib.xyg_geo_column_vertex_count
    function.restype = ctypes.c_size_t
    function.argtypes = [ctypes.c_uint64]
    # int32_t xyg_graph_build_csr(uint64_t n_nodes, uint64_t n_edges, const uint64_t * sources, const uint64_t * targets, int32_t directed, uint64_t * out_offsets, uint64_t * out_neighbors, uint64_t neighbors_cap, uint64_t * out_neighbor_len)
    function = lib.xyg_graph_build_csr
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_uint64, ctypes.c_uint64, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int32, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint64, ctypes.c_void_p]
    # int32_t xyg_graph_build_render(uint64_t n_nodes, uint64_t n_edges, const double * x, const double * y, const uint64_t * sources, const uint64_t * targets, uint64_t node_budget, uint64_t edge_budget, int32_t viewport_enabled, double vp_x0, double vp_y0, double vp_x1, double vp_y1, double * out_node_x, double * out_node_y, uint64_t * out_member_of, uint64_t * out_edge_sources, uint64_t * out_edge_targets, uint64_t * out_n_nodes, uint64_t * out_n_edges, uint32_t * out_tier, uint64_t * out_edges_kept)
    function = lib.xyg_graph_build_render
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_uint64, ctypes.c_uint64, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint64, ctypes.c_uint64, ctypes.c_int32, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p]
    # int32_t xyg_graph_cluster_aggregate(uint64_t n_nodes, uint64_t n_edges, const double * x, const double * y, uint64_t node_budget, uint64_t edge_budget, double * out_x, double * out_y, uint64_t * out_count, uint64_t * out_member_of, uint32_t * out_tier, uint64_t * out_edges_kept)
    function = lib.xyg_graph_cluster_aggregate
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_uint64, ctypes.c_uint64, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint64, ctypes.c_uint64, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p]
    # int32_t xyg_graph_edge_route_segments(uint64_t n_nodes, uint64_t n_edges, const double * x, const double * y, const uint64_t * sources, const uint64_t * targets, int32_t directed, double separation, double loop_radius, double arrow_size, double * out_x0, double * out_y0, double * out_x1, double * out_y1, uint64_t * out_edge_index, uint64_t * out_n_segments)
    function = lib.xyg_graph_edge_route_segments
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_uint64, ctypes.c_uint64, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int32, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p]
    # int32_t xyg_graph_force_create(uint64_t n_nodes, uint64_t n_edges, const uint64_t * sources, const uint64_t * targets, const double * in_x, const double * in_y, uint64_t seed, uint32_t algorithm, uint64_t * out_handle)
    function = lib.xyg_graph_force_create
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_uint64, ctypes.c_uint64, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint64, ctypes.c_uint32, ctypes.c_void_p]
    # int32_t xyg_graph_force_destroy(uint64_t handle)
    function = lib.xyg_graph_force_destroy
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_uint64]
    # int32_t xyg_graph_force_tick(uint64_t handle, uint64_t n_nodes, uint32_t steps, double * out_x, double * out_y, double * out_alpha)
    function = lib.xyg_graph_force_tick
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_uint64, ctypes.c_uint64, ctypes.c_uint32, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p]
    # int32_t xyg_graph_layout(uint32_t layout, uint64_t n_nodes, uint64_t n_edges, const uint64_t * sources, const uint64_t * targets, const double * in_x, const double * in_y, const uint64_t * roots, uint64_t n_roots, uint64_t seed, double * out_x, double * out_y)
    function = lib.xyg_graph_layout
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_uint32, ctypes.c_uint64, ctypes.c_uint64, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint64, ctypes.c_uint64, ctypes.c_void_p, ctypes.c_void_p]
    # int32_t xyg_graph_lod_decision(uint64_t n_nodes, uint64_t n_edges, uint64_t node_budget, uint64_t edge_budget, uint32_t * out_tier, uint64_t * out_edges_kept)
    function = lib.xyg_graph_lod_decision
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_uint64, ctypes.c_uint64, ctypes.c_uint64, ctypes.c_uint64, ctypes.c_void_p, ctypes.c_void_p]
    # int32_t xyg_graph_projection_copy_edge_ids(uint64_t handle, uint8_t * output, uint64_t capacity)
    function = lib.xyg_graph_projection_copy_edge_ids
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_uint64, ctypes.c_void_p, ctypes.c_uint64]
    # int32_t xyg_graph_projection_copy_endpoints(uint64_t handle, uint64_t * out_sources, uint64_t * out_targets, uint64_t capacity)
    function = lib.xyg_graph_projection_copy_endpoints
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_uint64, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint64]
    # int32_t xyg_graph_projection_copy_node_ids(uint64_t handle, uint8_t * output, uint64_t capacity)
    function = lib.xyg_graph_projection_copy_node_ids
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_uint64, ctypes.c_void_p, ctypes.c_uint64]
    # int32_t xyg_graph_projection_copy_parents(uint64_t handle, uint64_t * out_parents, uint8_t * out_validity, uint64_t capacity)
    function = lib.xyg_graph_projection_copy_parents
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_uint64, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint64]
    # int32_t xyg_graph_projection_counts(uint64_t handle, uint64_t * out_nodes, uint64_t * out_edges, uint32_t * out_directed)
    function = lib.xyg_graph_projection_counts
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_uint64, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p]
    # int32_t xyg_graph_projection_create(const void * descriptor, uint64_t * out_handle)
    function = lib.xyg_graph_projection_create
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    # int32_t xyg_graph_projection_destroy(uint64_t handle)
    function = lib.xyg_graph_projection_destroy
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_uint64]
    # uint64_t xyg_graph_sample_edges(uint64_t n_edges, uint64_t budget, uint64_t * out_indices)
    function = lib.xyg_graph_sample_edges
    function.restype = ctypes.c_uint64
    function.argtypes = [ctypes.c_uint64, ctypes.c_uint64, ctypes.c_void_p]
    # int32_t xyg_heatmap_rgba(const double * raw, size_t w, size_t h, const uint8_t * stops, size_t stop_count, uint8_t alpha, uint8_t * out)
    function = lib.xyg_heatmap_rgba
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_uint8, ctypes.c_void_p]
    # size_t xyg_hexbin(const double * x, const double * y, const double * c, size_t len, size_t grid_w, size_t grid_h, double x0, double x1, double y0, double y1, size_t mincnt, int32_t reduce, double * out_cx, double * out_cy, double * out_metric, double * out_counts, size_t capacity, double * out_dx, double * out_dy)
    function = lib.xyg_hexbin
    function.restype = ctypes.c_size_t
    function.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_size_t, ctypes.c_size_t, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_size_t, ctypes.c_int32, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_void_p]
    # int32_t xyg_histogram2d(const double * x, const double * y, const double * weights, size_t len, const double * x_edges, size_t x_edge_len, const double * y_edges, size_t y_edge_len, double * out)
    function = lib.xyg_histogram2d
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p]
    # size_t xyg_histogram_edges(const double * data, size_t len, double lo, double hi, int32_t use_range, int32_t method, double * out_edges, size_t capacity)
    function = lib.xyg_histogram_edges
    function.restype = ctypes.c_size_t
    function.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_double, ctypes.c_double, ctypes.c_int32, ctypes.c_int32, ctypes.c_void_p, ctypes.c_size_t]
    # size_t xyg_histogram_uniform(const double * data, size_t len, double lo, double hi, size_t n_bins, int32_t density, double * out_counts)
    function = lib.xyg_histogram_uniform
    function.restype = ctypes.c_size_t
    function.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_double, ctypes.c_double, ctypes.c_size_t, ctypes.c_int32, ctypes.c_void_p]
    # size_t xyg_indexed_triangles(const double * x, const double * y, size_t vertex_count, const int64_t * triangles, size_t face_count, const double * values, size_t value_len, uint32_t value_mode, double * out_x0, double * out_y0, double * out_x1, double * out_y1, double * out_x2, double * out_y2, double * out_values)
    function = lib.xyg_indexed_triangles
    function.restype = ctypes.c_size_t
    function.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_uint32, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p]
    # int32_t xyg_is_sorted(const double * data, size_t len)
    function = lib.xyg_is_sorted
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_void_p, ctypes.c_size_t]
    # int32_t xyg_local_log_density(const double * x, const double * y, size_t len, double lo_x, double hi_x, double lo_y, double hi_y, size_t w, size_t h, float * out)
    function = lib.xyg_local_log_density
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_size_t, ctypes.c_size_t, ctypes.c_void_p]
    # int32_t xyg_lod_grid_shape(int32_t px_w, int32_t px_h, uint64_t visible, double target_per_cell, int32_t * out_w, int32_t * out_h)
    function = lib.xyg_lod_grid_shape
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_int32, ctypes.c_int32, ctypes.c_uint64, ctypes.c_double, ctypes.c_void_p, ctypes.c_void_p]
    # int32_t xyg_lod_plan(uint64_t visible, double budget, int32_t in_drill, double exit_factor, int32_t px_w, int32_t px_h, double target_per_cell, int32_t * out_exact, uint32_t * out_mode, int32_t * out_grid_w, int32_t * out_grid_h)
    function = lib.xyg_lod_plan
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_uint64, ctypes.c_double, ctypes.c_int32, ctypes.c_double, ctypes.c_int32, ctypes.c_int32, ctypes.c_double, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p]
    # size_t xyg_m4_indices(const double * x, const double * y, size_t len, double x0, double x1, size_t n_buckets, uint32_t * out)
    function = lib.xyg_m4_indices
    function.restype = ctypes.c_size_t
    function.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_double, ctypes.c_double, ctypes.c_size_t, ctypes.c_void_p]
    # size_t xyg_m4_points(const double * x, const double * y, size_t len, double x0, double x1, size_t n_buckets, double * out_x, double * out_y)
    function = lib.xyg_m4_points
    function.restype = ctypes.c_size_t
    function.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_double, ctypes.c_double, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_void_p]
    # size_t xyg_marching_squares(const double * z, size_t rows, size_t cols, const double * x_coords, const double * y_coords, const double * levels, size_t n_levels, uint8_t corner_mask, double * out_x0, double * out_x1, double * out_y0, double * out_y1, double * out_levels, size_t capacity)
    function = lib.xyg_marching_squares
    function.restype = ctypes.c_size_t
    function.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_uint8, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t]
    # size_t xyg_marching_triangles(const double * x, const double * y, const double * z, size_t vertex_count, const int64_t * triangles, size_t face_count, const double * levels, size_t level_count, double * out_x0, double * out_x1, double * out_y0, double * out_y1, double * out_levels, size_t capacity)
    function = lib.xyg_marching_triangles
    function.restype = ctypes.c_size_t
    function.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t]
    # int32_t xyg_min_max(const double * data, size_t len, double * out_min, double * out_max)
    function = lib.xyg_min_max
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_void_p]
    # int32_t xyg_normalize_f32(const double * data, size_t len, double lo, double hi, int32_t nan_mode, float * out)
    function = lib.xyg_normalize_f32
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_double, ctypes.c_double, ctypes.c_int32, ctypes.c_void_p]
    # size_t xyg_polygon_select(const double * x, const double * y, size_t len, const uint32_t * rows, size_t n_rows, const double * poly_x, const double * poly_y, size_t n_poly, uint32_t * out)
    function = lib.xyg_polygon_select
    function.restype = ctypes.c_size_t
    function.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p]
    # size_t xyg_polygon_triangles(const double * x, const double * y, size_t len, int64_t * out, size_t capacity)
    function = lib.xyg_polygon_triangles
    function.restype = ctypes.c_size_t
    function.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t]
    # int32_t xyg_pyramid_append(uint64_t handle, const double * x, const double * y, size_t len)
    function = lib.xyg_pyramid_append
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_uint64, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t]
    # int32_t xyg_pyramid_append_from_stream(uint64_t handle, uint64_t x_handle, uint64_t y_handle, size_t tail_len)
    function = lib.xyg_pyramid_append_from_stream
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_uint64, ctypes.c_uint64, ctypes.c_uint64, ctypes.c_size_t]
    # uint64_t xyg_pyramid_build(const double * x, const double * y, size_t len, double x0, double x1, double y0, double y1, uint32_t base_dim)
    function = lib.xyg_pyramid_build
    function.restype = ctypes.c_uint64
    function.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_uint32]
    # uint64_t xyg_pyramid_build_color(const double * x, const double * y, size_t len, const uint8_t * idx, const uint8_t * rgba, const uint8_t * lut, size_t lut_len, double x0, double x1, double y0, double y1, uint32_t base_dim)
    function = lib.xyg_pyramid_build_color
    function.restype = ctypes.c_uint64
    function.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_uint32]
    # uint64_t xyg_pyramid_build_from_stream(uint64_t x_handle, uint64_t y_handle, double x0, double x1, double y0, double y1, uint32_t base_dim)
    function = lib.xyg_pyramid_build_from_stream
    function.restype = ctypes.c_uint64
    function.argtypes = [ctypes.c_uint64, ctypes.c_uint64, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_uint32]
    # int32_t xyg_pyramid_compose(uint64_t handle, double lo_x, double hi_x, double lo_y, double hi_y, size_t w, size_t h, size_t max_upsample, float * out)
    function = lib.xyg_pyramid_compose
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_uint64, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_size_t, ctypes.c_size_t, ctypes.c_size_t, ctypes.c_void_p]
    # int32_t xyg_pyramid_compose_color(uint64_t handle, double lo_x, double hi_x, double lo_y, double hi_y, size_t w, size_t h, size_t max_upsample, float * out, uint8_t * out_rgba)
    function = lib.xyg_pyramid_compose_color
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_uint64, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_size_t, ctypes.c_size_t, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_void_p]
    # int32_t xyg_pyramid_count(uint64_t handle, double lo_x, double hi_x, double lo_y, double hi_y, double * out_count)
    function = lib.xyg_pyramid_count
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_uint64, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_void_p]
    # int32_t xyg_pyramid_free(uint64_t handle)
    function = lib.xyg_pyramid_free
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_uint64]
    # uint64_t xyg_pyramid_spill(uint64_t handle)
    function = lib.xyg_pyramid_spill
    function.restype = ctypes.c_uint64
    function.argtypes = [ctypes.c_uint64]
    # size_t xyg_quad_mesh_triangles(const double * x, size_t x_len, const double * y, size_t y_len, const double * values, size_t cell_rows, size_t cell_cols, uint32_t layout, double * out_x0, double * out_y0, double * out_x1, double * out_y1, double * out_x2, double * out_y2, double * out_values)
    function = lib.xyg_quad_mesh_triangles
    function.restype = ctypes.c_size_t
    function.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_size_t, ctypes.c_uint32, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p]
    # size_t xyg_quantiles(const double * data, size_t len, const double * probs, size_t n_probs, double * out)
    function = lib.xyg_quantiles
    function.restype = ctypes.c_size_t
    function.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p]
    # size_t xyg_range_indices(const double * x, const double * y, size_t len, double lo_x, double hi_x, double lo_y, double hi_y, uint32_t * out)
    function = lib.xyg_range_indices
    function.restype = ctypes.c_size_t
    function.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_void_p]
    # size_t xyg_range_indices_rows(const double * x, const double * y, size_t len, const uint32_t * rows, size_t n_rows, double lo_x, double hi_x, double lo_y, double hi_y, uint32_t * out)
    function = lib.xyg_range_indices_rows
    function.restype = ctypes.c_size_t
    function.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_void_p]
    # int32_t xyg_rasterize(const uint8_t * cmd, size_t cmd_len, uint8_t * out, size_t w, size_t h)
    function = lib.xyg_rasterize
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_size_t]
    # int32_t xyg_rasterize_data(const uint8_t * cmd, size_t cmd_len, const uint8_t * data, size_t data_len, uint8_t * out, size_t w, size_t h)
    function = lib.xyg_rasterize_data
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_size_t]
    # size_t xyg_rasterize_png(const uint8_t * cmd, size_t cmd_len, uint8_t * out, size_t out_capacity, size_t w, size_t h)
    function = lib.xyg_rasterize_png
    function.restype = ctypes.c_size_t
    function.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_size_t, ctypes.c_size_t]
    # size_t xyg_rasterize_png_data(const uint8_t * cmd, size_t cmd_len, const uint8_t * data, size_t data_len, uint8_t * out, size_t out_capacity, size_t w, size_t h)
    function = lib.xyg_rasterize_png_data
    function.restype = ctypes.c_size_t
    function.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_size_t, ctypes.c_size_t]
    # size_t xyg_rasterize_png_spans(const uint8_t * cmd, size_t cmd_len, const uint8_t *const * span_ptrs, const size_t * span_lens, size_t span_count, uint8_t * out, size_t out_capacity, size_t w, size_t h)
    function = lib.xyg_rasterize_png_spans
    function.restype = ctypes.c_size_t
    function.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_size_t, ctypes.c_size_t]
    # int32_t xyg_rasterize_spans(const uint8_t * cmd, size_t cmd_len, const uint8_t *const * span_ptrs, const size_t * span_lens, size_t span_count, uint8_t * out, size_t w, size_t h)
    function = lib.xyg_rasterize_spans
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_size_t]
    # int32_t xyg_remap_u8(uint8_t * values, size_t len, const uint8_t * mapping, size_t mapping_len)
    function = lib.xyg_remap_u8
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t]
    # int32_t xyg_rfft(const double * data, size_t len, size_t nfft, double sample_rate, double * out_frequency, double * out_real, double * out_imag)
    function = lib.xyg_rfft
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_size_t, ctypes.c_double, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p]
    # int32_t xyg_sample_mask(const uint64_t * ids, size_t len, uint64_t seed, uint64_t threshold, uint8_t * out)
    function = lib.xyg_sample_mask
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_uint64, ctypes.c_uint64, ctypes.c_void_p]
    # int32_t xyg_sample_mask_u32(const uint32_t * ids, size_t len, uint64_t seed, uint64_t threshold, uint8_t * out)
    function = lib.xyg_sample_mask_u32
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_uint64, ctypes.c_uint64, ctypes.c_void_p]
    # size_t xyg_sample_range_indices(size_t size, uint64_t seed, uint64_t threshold, uint32_t * out, size_t capacity)
    function = lib.xyg_sample_range_indices
    function.restype = ctypes.c_size_t
    function.argtypes = [ctypes.c_size_t, ctypes.c_uint64, ctypes.c_uint64, ctypes.c_void_p, ctypes.c_size_t]
    # int32_t xyg_sankey_layout(uint64_t n_nodes, uint64_t n_links, const uint64_t * sources, const uint64_t * targets, const double * values, double node_width, double node_padding, uint32_t align, uint32_t iterations, double * out_x0, double * out_y0, double * out_x1, double * out_y1, uint32_t * out_layer, double * out_value, double * out_source_y0, double * out_source_y1, double * out_target_y0, double * out_target_y1, uint32_t * out_layers, uint64_t * out_err_nodes, uint64_t * out_err_n)
    function = lib.xyg_sankey_layout
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_uint64, ctypes.c_uint64, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_double, ctypes.c_double, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p]
    # size_t xyg_scene_axis_ticks(uint32_t kind, double lo, double hi, size_t target, double aux, double * out_ticks, double * out_labeled, size_t * out_labeled_len, double * out_step, size_t out_cap)
    function = lib.xyg_scene_axis_ticks
    function.restype = ctypes.c_size_t
    function.argtypes = [ctypes.c_uint32, ctypes.c_double, ctypes.c_double, ctypes.c_size_t, ctypes.c_double, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t]
    # size_t xyg_scene_batch_encode(double viewport_width, double viewport_height, double margin_left, double margin_right, double margin_top, double margin_bottom, uint64_t x_axis_id, uint32_t x_kind, double x_lo, double x_hi, double x_constant, int32_t x_mask_nonpositive, uint64_t y_axis_id, uint32_t y_kind, double y_lo, double y_hi, double y_constant, int32_t y_mask_nonpositive, const uint8_t * chrome_style, size_t chrome_style_len, const double * x_major_ticks, size_t x_major_count, int32_t x_major_auto, const double * x_minor_ticks, size_t x_minor_count, const double * y_major_ticks, size_t y_major_count, int32_t y_major_auto, const double * y_minor_ticks, size_t y_minor_count, const uint8_t * kinds, const uint64_t * stable_ids, const uint32_t * style_refs, const uint8_t * fill_rgba, const uint8_t * stroke_rgba, const double * stroke_width, size_t style_count, const double * diameter, const uint8_t * symbols, const double * x0, const double * y0, const double * x1, const double * y1, size_t len, const uint8_t * title, size_t title_len, const uint8_t * x_label, size_t x_label_len, const uint8_t * y_label, size_t y_label_len, const uint8_t * legend_input, size_t legend_input_len, uint8_t * out, size_t out_cap)
    function = lib.xyg_scene_batch_encode
    function.restype = ctypes.c_size_t
    function.argtypes = [ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_uint64, ctypes.c_uint32, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_int32, ctypes.c_uint64, ctypes.c_uint32, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_int32, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_int32, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_int32, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t]
    # size_t xyg_scene_plot_layout(double viewport_width, double viewport_height, const double * authored_padding, uint32_t x_kind, double x_lo, double x_hi, double x_constant, int32_t x_mask_nonpositive, uint32_t y_kind, double y_lo, double y_hi, double y_constant, int32_t y_mask_nonpositive, const uint8_t * title, size_t title_len, const uint8_t * x_label, size_t x_label_len, const uint8_t * y_label, size_t y_label_len, double * out_margins)
    function = lib.xyg_scene_plot_layout
    function.restype = ctypes.c_size_t
    function.argtypes = [ctypes.c_double, ctypes.c_double, ctypes.c_void_p, ctypes.c_uint32, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_int32, ctypes.c_uint32, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_int32, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p]
    # size_t xyg_scene_raster_commands(const uint8_t * encoded, size_t encoded_len, double scale, uint8_t * out, size_t out_cap)
    function = lib.xyg_scene_raster_commands
    function.restype = ctypes.c_size_t
    function.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_double, ctypes.c_void_p, ctypes.c_size_t]
    # int32_t xyg_scene_scale_map(const double * values, size_t len, uint32_t kind, uint32_t operation, double lo, double hi, double px0, double px1, double constant, int32_t mask_nonpositive, double * out)
    function = lib.xyg_scene_scale_map
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_int32, ctypes.c_void_p]
    # size_t xyg_scene_scatter_svg(const double * x, const double * y, const double * diameter, const uint8_t * fill_rgba, const uint8_t * stroke_rgba, const double * stroke_width, const uint8_t * symbols, const uint8_t * visible, const uint8_t * fill_css, size_t fill_css_len, const uint8_t * stroke_css, size_t stroke_css_len, size_t len, uint8_t * out, size_t out_cap)
    function = lib.xyg_scene_scatter_svg
    function.restype = ctypes.c_size_t
    function.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t]
    # size_t xyg_scene_svg(const uint8_t * encoded, size_t encoded_len, uint8_t * out, size_t out_cap)
    function = lib.xyg_scene_svg
    function.restype = ctypes.c_size_t
    function.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t]
    # uint32_t xyg_scene_version()
    function = lib.xyg_scene_version
    function.restype = ctypes.c_uint32
    function.argtypes = []
    # size_t xyg_sector_triangles(const double * values, size_t len, const double * explode, double center_x, double center_y, double radius, double inner_radius, double start_degrees, int32_t counterclockwise, int32_t normalize, double * out_x0, double * out_y0, double * out_x1, double * out_y1, double * out_x2, double * out_y2, double * out_sector, size_t capacity)
    function = lib.xyg_sector_triangles
    function.restype = ctypes.c_size_t
    function.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_int32, ctypes.c_int32, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t]
    # int32_t xyg_spectrogram(const double * data, size_t len, size_t nfft, size_t noverlap, double sample_rate, double * out_frequency, double * out_time, double * out_power)
    function = lib.xyg_spectrogram
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_size_t, ctypes.c_size_t, ctypes.c_double, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p]
    # int32_t xyg_stacked_bounds(const double * values, size_t rows, size_t cols, uint32_t baseline, double * out_lower, double * out_upper)
    function = lib.xyg_stacked_bounds
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_size_t, ctypes.c_uint32, ctypes.c_void_p, ctypes.c_void_p]
    # int32_t xyg_stratified_sample_mask(const uint64_t * ids, const uint32_t * groups, size_t len, size_t n_groups, uint64_t seed, double fraction, uint64_t min_count, uint8_t * out)
    function = lib.xyg_stratified_sample_mask
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_size_t, ctypes.c_uint64, ctypes.c_double, ctypes.c_uint64, ctypes.c_void_p]
    # int32_t xyg_stratified_sample_mask_u32(const uint32_t * ids, const uint32_t * groups, size_t len, size_t n_groups, uint64_t seed, double fraction, uint64_t min_count, uint8_t * out)
    function = lib.xyg_stratified_sample_mask_u32
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_size_t, ctypes.c_uint64, ctypes.c_double, ctypes.c_uint64, ctypes.c_void_p]
    # size_t xyg_stratified_sample_range_u8(const uint8_t * groups, size_t len, size_t n_groups, uint64_t seed, double fraction, uint64_t min_count, uint32_t * out, size_t capacity)
    function = lib.xyg_stratified_sample_range_u8
    function.restype = ctypes.c_size_t
    function.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_size_t, ctypes.c_uint64, ctypes.c_double, ctypes.c_uint64, ctypes.c_void_p, ctypes.c_size_t]
    # size_t xyg_stratified_sample_range_u8_counted(const uint8_t * groups, size_t len, const uint64_t * counts, size_t n_groups, uint64_t seed, double fraction, uint64_t min_count, uint32_t * out, size_t capacity)
    function = lib.xyg_stratified_sample_range_u8_counted
    function.restype = ctypes.c_size_t
    function.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_uint64, ctypes.c_double, ctypes.c_uint64, ctypes.c_void_p, ctypes.c_size_t]
    # int32_t xyg_stream_append(uint64_t handle, const double * data, size_t len)
    function = lib.xyg_stream_append
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_uint64, ctypes.c_void_p, ctypes.c_size_t]
    # size_t xyg_stream_capacity(uint64_t handle)
    function = lib.xyg_stream_capacity
    function.restype = ctypes.c_size_t
    function.argtypes = [ctypes.c_uint64]
    # int32_t xyg_stream_copy(uint64_t handle, double * out, size_t len)
    function = lib.xyg_stream_copy
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_uint64, ctypes.c_void_p, ctypes.c_size_t]
    # int32_t xyg_stream_data(uint64_t handle, const double ** out_ptr, size_t * out_len)
    function = lib.xyg_stream_data
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_uint64, ctypes.c_void_p, ctypes.c_void_p]
    # int32_t xyg_stream_free(uint64_t handle)
    function = lib.xyg_stream_free
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_uint64]
    # size_t xyg_stream_len(uint64_t handle)
    function = lib.xyg_stream_len
    function.restype = ctypes.c_size_t
    function.argtypes = [ctypes.c_uint64]
    # uint64_t xyg_stream_new(const double * data, size_t len)
    function = lib.xyg_stream_new
    function.restype = ctypes.c_uint64
    function.argtypes = [ctypes.c_void_p, ctypes.c_size_t]
    # int32_t xyg_stream_seal(uint64_t handle)
    function = lib.xyg_stream_seal
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_uint64]
    # size_t xyg_stream_zone_maps(uint64_t handle, double * out_min, double * out_max, uint64_t * out_count, uint64_t * out_null_count, double * out_sum, double * out_sum_sq, double * out_positive_min, double * out_positive_max)
    function = lib.xyg_stream_zone_maps
    function.restype = ctypes.c_size_t
    function.argtypes = [ctypes.c_uint64, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p]
    # size_t xyg_streamlines(const double * x_coords, size_t cols, const double * y_coords, size_t rows, const double * u, const double * v, double density, size_t max_steps, double * out_x0, double * out_x1, double * out_y0, double * out_y1, size_t capacity)
    function = lib.xyg_streamlines
    function.restype = ctypes.c_size_t
    function.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_double, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t]
    # size_t xyg_svg_poly_path(const double * x, const double * y, size_t len, uint8_t * out, size_t out_cap)
    function = lib.xyg_svg_poly_path
    function.restype = ctypes.c_size_t
    function.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t]
    # int32_t xyg_temporal_column_copy(uint64_t handle, int64_t * out_values, uint8_t * out_validity, uint64_t capacity)
    function = lib.xyg_temporal_column_copy
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_uint64, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint64]
    # int32_t xyg_temporal_column_create(const void * descriptor, uint64_t * out_handle)
    function = lib.xyg_temporal_column_create
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    # int32_t xyg_temporal_column_destroy(uint64_t handle)
    function = lib.xyg_temporal_column_destroy
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_uint64]
    # int32_t xyg_temporal_column_meta(uint64_t handle, uint64_t * out_len, uint32_t * out_precision, uint32_t * out_timezone_len)
    function = lib.xyg_temporal_column_meta
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_uint64, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p]
    # int32_t xyg_temporal_column_timezone(uint64_t handle, uint8_t * out_timezone, uint32_t capacity)
    function = lib.xyg_temporal_column_timezone
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_uint64, ctypes.c_void_p, ctypes.c_uint32]
    # int32_t xyg_temporal_controller_apply_event(uint64_t handle, uint64_t group_id, uint64_t source_instance, uint64_t revision, int64_t range_start, int64_t range_end, int64_t cursor, int64_t window, uint32_t * out_applied)
    function = lib.xyg_temporal_controller_apply_event
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_uint64, ctypes.c_uint64, ctypes.c_uint64, ctypes.c_uint64, ctypes.c_int64, ctypes.c_int64, ctypes.c_int64, ctypes.c_int64, ctypes.c_void_p]
    # int32_t xyg_temporal_controller_create(const void * descriptor, uint64_t * out_handle)
    function = lib.xyg_temporal_controller_create
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    # int32_t xyg_temporal_controller_destroy(uint64_t handle)
    function = lib.xyg_temporal_controller_destroy
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_uint64]
    # int32_t xyg_temporal_controller_dispose(uint64_t handle)
    function = lib.xyg_temporal_controller_dispose
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_uint64]
    # int32_t xyg_temporal_controller_pause(uint64_t handle)
    function = lib.xyg_temporal_controller_pause
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_uint64]
    # int32_t xyg_temporal_controller_play(uint64_t handle)
    function = lib.xyg_temporal_controller_play
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_uint64]
    # int32_t xyg_temporal_controller_poll_event(uint64_t handle, uint32_t * out_has_event, uint64_t * out_group_id, uint64_t * out_source_instance, uint64_t * out_revision, int64_t * out_range_start, int64_t * out_range_end, int64_t * out_cursor, int64_t * out_window)
    function = lib.xyg_temporal_controller_poll_event
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_uint64, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p]
    # int32_t xyg_temporal_controller_set_cursor(uint64_t handle, int64_t cursor)
    function = lib.xyg_temporal_controller_set_cursor
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_uint64, ctypes.c_int64]
    # int32_t xyg_temporal_controller_set_direction(uint64_t handle, int32_t direction)
    function = lib.xyg_temporal_controller_set_direction
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_uint64, ctypes.c_int32]
    # int32_t xyg_temporal_controller_set_loop(uint64_t handle, uint32_t enabled)
    function = lib.xyg_temporal_controller_set_loop
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_uint64, ctypes.c_uint32]
    # int32_t xyg_temporal_controller_set_range(uint64_t handle, int64_t start, int64_t end)
    function = lib.xyg_temporal_controller_set_range
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_uint64, ctypes.c_int64, ctypes.c_int64]
    # int32_t xyg_temporal_controller_set_rate_milli(uint64_t handle, uint32_t rate_milli)
    function = lib.xyg_temporal_controller_set_rate_milli
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_uint64, ctypes.c_uint32]
    # int32_t xyg_temporal_controller_set_reduced_motion(uint64_t handle, uint32_t enabled)
    function = lib.xyg_temporal_controller_set_reduced_motion
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_uint64, ctypes.c_uint32]
    # int32_t xyg_temporal_controller_state(uint64_t handle, uint64_t * out_instance_id, uint64_t * out_group_id, int64_t * out_domain_start, int64_t * out_domain_end, int64_t * out_range_start, int64_t * out_range_end, int64_t * out_cursor, int64_t * out_window, int64_t * out_step, int32_t * out_direction, uint32_t * out_rate_milli, uint32_t * out_loop_enabled, uint32_t * out_playing, uint32_t * out_reduced_motion, uint64_t * out_revision, uint32_t * out_disposed)
    function = lib.xyg_temporal_controller_state
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_uint64, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p]
    # int32_t xyg_temporal_controller_step(uint64_t handle)
    function = lib.xyg_temporal_controller_step
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_uint64]
    # int32_t xyg_temporal_controller_tick(uint64_t handle, int64_t dt_micros, uint32_t * out_advanced)
    function = lib.xyg_temporal_controller_tick
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_uint64, ctypes.c_int64, ctypes.c_void_p]
    # int32_t xyg_temporal_coordinate_deliver(uint64_t group_id, uint64_t source_instance, uint64_t revision, int64_t range_start, int64_t range_end, int64_t cursor, int64_t window, uint32_t * out_applied)
    function = lib.xyg_temporal_coordinate_deliver
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_uint64, ctypes.c_uint64, ctypes.c_uint64, ctypes.c_int64, ctypes.c_int64, ctypes.c_int64, ctypes.c_int64, ctypes.c_void_p]
    # int32_t xyg_temporal_events_in_range(const int64_t * event_micros, const uint8_t * event_valid, uint64_t event_len, int64_t range_start, uint32_t range_start_valid, int64_t range_end, uint32_t range_end_valid, uint8_t * out_visibility, uint64_t capacity, uint64_t budget, const uint32_t * cancel_flag)
    function = lib.xyg_temporal_events_in_range
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint64, ctypes.c_int64, ctypes.c_uint32, ctypes.c_int64, ctypes.c_uint32, ctypes.c_void_p, ctypes.c_uint64, ctypes.c_uint64, ctypes.c_void_p]
    # int32_t xyg_temporal_interval_index_create(const void * descriptor, uint64_t * out_handle)
    function = lib.xyg_temporal_interval_index_create
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    # int32_t xyg_temporal_interval_index_destroy(uint64_t handle)
    function = lib.xyg_temporal_interval_index_destroy
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_uint64]
    # int32_t xyg_temporal_interval_index_len(uint64_t handle, uint64_t * out_len)
    function = lib.xyg_temporal_interval_index_len
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_uint64, ctypes.c_void_p]
    # int32_t xyg_temporal_interval_visibility_at(uint64_t handle, int64_t instant_micros, uint8_t * out_visibility, uint64_t capacity, uint64_t budget, const uint32_t * cancel_flag)
    function = lib.xyg_temporal_interval_visibility_at
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_uint64, ctypes.c_int64, ctypes.c_void_p, ctypes.c_uint64, ctypes.c_uint64, ctypes.c_void_p]
    # int32_t xyg_tile_budget_set(uint64_t bytes)
    function = lib.xyg_tile_budget_set
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_uint64]
    # int32_t xyg_tile_store_append(uint64_t store, const double * x, const double * y, size_t len)
    function = lib.xyg_tile_store_append
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_uint64, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t]
    # int32_t xyg_tile_store_compose(uint64_t store, double lo_x, double hi_x, double lo_y, double hi_y, size_t w, size_t h, size_t max_upsample, float * out)
    function = lib.xyg_tile_store_compose
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_uint64, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_size_t, ctypes.c_size_t, ctypes.c_size_t, ctypes.c_void_p]
    # int32_t xyg_tile_store_compose_color(uint64_t store, double lo_x, double hi_x, double lo_y, double hi_y, size_t w, size_t h, size_t max_upsample, float * out, uint8_t * out_rgba)
    function = lib.xyg_tile_store_compose_color
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_uint64, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_size_t, ctypes.c_size_t, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_void_p]
    # int32_t xyg_tile_store_fetch(uint64_t store, uint32_t level, uint32_t tx, uint32_t ty, uint32_t * out_counts, uint16_t * out_color)
    function = lib.xyg_tile_store_fetch
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_uint64, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_void_p, ctypes.c_void_p]
    # int32_t xyg_tile_store_free(uint64_t store)
    function = lib.xyg_tile_store_free
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_uint64]
    # int32_t xyg_tile_store_stats(uint64_t store, uint64_t * out)
    function = lib.xyg_tile_store_stats
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_uint64, ctypes.c_void_p]
    # int32_t xyg_transition_keys_fixed(const uint8_t * data, size_t len, size_t width, uint32_t kind, int32_t swap_endian, uint32_t * out_lo, uint32_t * out_hi, size_t * out_error_first, size_t * out_error_index)
    function = lib.xyg_transition_keys_fixed
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_size_t, ctypes.c_uint32, ctypes.c_int32, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p]
    # size_t xyg_triangle_edges(const double * x, const double * y, size_t vertex_count, const int64_t * triangles, size_t face_count, double * out_x0, double * out_x1, double * out_y0, double * out_y1)
    function = lib.xyg_triangle_edges
    function.restype = ctypes.c_size_t
    function.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p]
    # size_t xyg_valid_indices_f64(const double *const * columns, size_t n_columns, size_t len, uint64_t positive_mask, uint32_t * out, size_t capacity)
    function = lib.xyg_valid_indices_f64
    function.restype = ctypes.c_size_t
    function.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_size_t, ctypes.c_uint64, ctypes.c_void_p, ctypes.c_size_t]
    # size_t xyg_vector_segments(const double * x, const double * y, const double * u, const double * v, size_t len, double scale, uint32_t pivot, double head_ratio, double * out_x0, double * out_x1, double * out_y0, double * out_y1)
    function = lib.xyg_vector_segments
    function.restype = ctypes.c_size_t
    function.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_double, ctypes.c_uint32, ctypes.c_double, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p]
    # int32_t xyg_violin_density(const double * data, size_t len, size_t n_bins, double * out_edges, double * out_density)
    function = lib.xyg_violin_density
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_void_p]
    # size_t xyg_weighted_ecdf(const double * values, const double * weights, size_t len, double * out_values, double * out_cumulative)
    function = lib.xyg_weighted_ecdf
    function.restype = ctypes.c_size_t
    function.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_void_p]
    # int32_t xyg_welch_spectra(const double * x, const double * y, size_t len, size_t nfft, size_t noverlap, double sample_rate, double * out_frequency, double * out_pxx, double * out_pyy, double * out_pxy_real, double * out_pxy_imag)
    function = lib.xyg_welch_spectra
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_size_t, ctypes.c_size_t, ctypes.c_double, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p]
    # size_t xyg_wind_rose_bins(const double * directions, const double * speeds, size_t len, size_t sectors, const double * speed_edges, size_t n_speed_edges, double * out_edges, size_t capacity_edges, double * out_centres, double * out_counts, size_t capacity_counts, size_t * out_n_obs)
    function = lib.xyg_wind_rose_bins
    function.restype = ctypes.c_size_t
    function.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p]
    # size_t xyg_zone_maps(const double * data, size_t len, size_t chunk_size, double * out_min, double * out_max, uint64_t * out_count, uint64_t * out_null_count, double * out_sum, double * out_sum_sq, double * out_positive_min, double * out_positive_max)
    function = lib.xyg_zone_maps
    function.restype = ctypes.c_size_t
    function.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p]
    # size_t xyg_zone_maps_pair(const double * x, const double * y, size_t len, size_t chunk_size, void * out_x, void * out_y)
    function = lib.xyg_zone_maps_pair
    function.restype = ctypes.c_size_t
    function.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_void_p]
