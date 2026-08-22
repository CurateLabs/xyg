/* Generated C ABI header. Do not edit; run scripts/gen_abi_manifest.py --write. */
#ifndef XYG_ABI_H
#define XYG_ABI_H

#include <stddef.h>
#include <stdint.h>

#define XYG_ABI_VERSION 88
#define XYG_ABI_SIGNATURE_SHA256 "7eede87030812d3f6ab19fbdba3aa889a8b17c53d74fb4e39675dcd6bd0f9952"

#ifdef __cplusplus
extern "C" {
#endif

uint32_t xyg_abi_version();
int32_t xyg_bar_stack(const double * pos, size_t n_items, const double * values, size_t n_series, const double * width, size_t width_len, const double * base, size_t base_len, uint32_t mode, uint32_t orientation, double * out_x0, double * out_x1, double * out_y0, double * out_y1);
int32_t xyg_bin_2d(const double * x, const double * y, size_t len, double x0, double x1, double y0, double y1, size_t w, size_t h, float * out);
int32_t xyg_bin_2d_f32(const float * x, const float * y, size_t len, double x0, double x1, double y0, double y1, size_t w, size_t h, float * out);
size_t xyg_bin_2d_indices(const double * x, const double * y, size_t len, double x0, double x1, double y0, double y1, size_t w, size_t h, float * grid, uint32_t * idx);
int32_t xyg_bin_2d_mean_color(const double * x, const double * y, size_t len, const uint8_t * idx, const uint8_t * rgba, const uint8_t * lut, size_t lut_len, double x0, double x1, double y0, double y1, size_t w, size_t h, uint8_t * out);
size_t xyg_bin_2d_sample_range(const double * x, const double * y, size_t len, double x0, double x1, double y0, double y1, size_t w, size_t h, uint64_t seed, uint64_t threshold, float * grid, uint32_t * out, size_t capacity);
size_t xyg_bin_2d_stratified_sample_range_u8_counted(const double * x, const double * y, const uint8_t * groups, size_t len, const uint64_t * counts, size_t n_groups, double x0, double x1, double y0, double y1, size_t w, size_t h, uint64_t seed, double fraction, uint64_t min_count, float * grid, uint32_t * out, size_t capacity);
int32_t xyg_box_stats(const double * data, size_t len, double * out_stats, double * out_outliers, size_t outliers_cap, size_t * out_n_outliers);
int32_t xyg_chunked_columns_cancel_before(uint64_t store, uint64_t generation);
int32_t xyg_chunked_columns_free(uint64_t store);
uint64_t xyg_chunked_columns_open(const uint8_t * path, size_t path_len);
size_t xyg_chunked_columns_overview(uint64_t store, size_t max_points, uint64_t * out_rows, double * out_x, double * out_y, uint64_t * out_stats);
size_t xyg_chunked_columns_read(uint64_t store, double x0, double x1, double y0, double y1, int32_t use_y, uint64_t budget_bytes, uint64_t generation, double * out_x, double * out_y, size_t capacity, uint64_t * out_stats);
size_t xyg_chunked_columns_read_page(uint64_t store, double x0, double x1, double y0, double y1, int32_t use_y, uint64_t budget_bytes, uint64_t generation, uint32_t cursor, double * out_x, double * out_y, size_t capacity, uint64_t * out_stats);
uint64_t xyg_chunked_columns_rows(uint64_t store);
size_t xyg_contourf_bands(const double * z, size_t rows, size_t cols, const double * xpos, const double * ypos, const double * edges, size_t n_edges, uint8_t extend_min, uint8_t extend_max, double * out_x0, double * out_y0, double * out_x1, double * out_y1, double * out_x2, double * out_y2, int64_t * out_slots, size_t capacity);
int32_t xyg_contourf_densify(const double * z, size_t rows, size_t cols, const double * xpos, const double * ypos, double * out_z, double * out_x, double * out_y, size_t out_z_cap, size_t out_x_cap, size_t out_y_cap, size_t * out_rows, size_t * out_cols);
int32_t xyg_correlation(const double * x, const double * y, size_t len, size_t max_lag, int32_t normalize, double * out_lag, double * out_correlation);
int32_t xyg_css_check(uint32_t kind, const uint8_t * prop, size_t prop_len, const uint8_t * value, size_t value_len, float * out_rgba);
size_t xyg_delaunay_triangles(const double * x, const double * y, size_t len, int64_t * out, size_t capacity);
int32_t xyg_density_log_u8(const float * grid, size_t len, uint8_t * out, double * out_max);
int32_t xyg_density_rgba(const uint8_t * encoded, size_t w, size_t h, double maximum, const uint8_t * stops, size_t stop_count, double opacity, uint8_t * out);
int32_t xyg_drill_decision(uint64_t visible, double budget, int32_t in_drill, double exit_factor, int32_t * out_exact);
int32_t xyg_encode_f32(const double * data, size_t len, double offset, double scale, float * out);
size_t xyg_factorize_fixed(const uint8_t * data, size_t len, size_t width, uint32_t * out_codes, uint32_t * out_unique_indices);
size_t xyg_factorize_fixed_u8(const uint8_t * data, size_t len, size_t width, uint8_t * out_codes, uint32_t * out_unique_indices, size_t unique_capacity);
size_t xyg_factorize_fixed_u8_counts(const uint8_t * data, size_t len, size_t width, uint8_t * out_codes, uint32_t * out_unique_indices, uint64_t * out_counts, size_t unique_capacity);
size_t xyg_factorize_unicode1_u8_counts(const uint32_t * data, size_t len, int32_t swap_endian, uint8_t * out_codes, uint32_t * out_unique_indices, uint64_t * out_counts, size_t unique_capacity);
uint32_t xyg_geo_column_crs(uint64_t handle);
int32_t xyg_geo_column_free(uint64_t handle);
uint32_t xyg_geo_column_geometry(uint64_t handle);
size_t xyg_geo_column_len(uint64_t handle);
uint64_t xyg_geo_column_new(uint32_t geometry, uint32_t crs, const double * xy, size_t xy_len, const uint8_t * validity, size_t validity_len, const uint64_t * feature_ids, const uint32_t * offsets0, size_t offsets0_len, const uint32_t * offsets1, size_t offsets1_len, const uint32_t * offsets2, size_t offsets2_len, int32_t * out_error);
size_t xyg_geo_column_vertex_count(uint64_t handle);
int32_t xyg_graph_build_csr(uint64_t n_nodes, uint64_t n_edges, const uint64_t * sources, const uint64_t * targets, int32_t directed, uint64_t * out_offsets, uint64_t * out_neighbors, uint64_t neighbors_cap, uint64_t * out_neighbor_len);
int32_t xyg_graph_build_render(uint64_t n_nodes, uint64_t n_edges, const double * x, const double * y, const uint64_t * sources, const uint64_t * targets, uint64_t node_budget, uint64_t edge_budget, int32_t viewport_enabled, double vp_x0, double vp_y0, double vp_x1, double vp_y1, double * out_node_x, double * out_node_y, uint64_t * out_member_of, uint64_t * out_edge_sources, uint64_t * out_edge_targets, uint64_t * out_n_nodes, uint64_t * out_n_edges, uint32_t * out_tier, uint64_t * out_edges_kept);
int32_t xyg_graph_cluster_aggregate(uint64_t n_nodes, uint64_t n_edges, const double * x, const double * y, uint64_t node_budget, uint64_t edge_budget, double * out_x, double * out_y, uint64_t * out_count, uint64_t * out_member_of, uint32_t * out_tier, uint64_t * out_edges_kept);
int32_t xyg_graph_compound_bounds(uint64_t n, const double * x, const double * y, const uint64_t * parents, const uint8_t * validity, uint64_t * parent_of, uint8_t * is_compound, double * xmin, double * xmax, double * ymin, double * ymax);
int32_t xyg_graph_edge_route_segments(uint64_t n_nodes, uint64_t n_edges, const double * x, const double * y, const uint64_t * sources, const uint64_t * targets, int32_t directed, double separation, double loop_radius, double arrow_size, double * out_x0, double * out_y0, double * out_x1, double * out_y1, uint64_t * out_edge_index, uint64_t * out_n_segments);
int32_t xyg_graph_force_create(uint64_t n_nodes, uint64_t n_edges, const uint64_t * sources, const uint64_t * targets, const double * in_x, const double * in_y, uint64_t seed, uint32_t algorithm, uint64_t * out_handle);
int32_t xyg_graph_force_create_cose(const void * descriptor, uint64_t n_nodes, uint64_t n_edges, const uint64_t * sources, const uint64_t * targets, uint64_t seed, uint64_t * out_handle);
int32_t xyg_graph_force_destroy(uint64_t handle);
int32_t xyg_graph_force_tick(uint64_t handle, uint64_t n_nodes, uint32_t steps, double * out_x, double * out_y, double * out_alpha);
int32_t xyg_graph_label_accept(uint64_t n, const double * priorities, uint64_t budget, double floor, uint8_t * out, uint64_t * out_count);
int32_t xyg_graph_layout(uint32_t layout, uint64_t n_nodes, uint64_t n_edges, const uint64_t * sources, const uint64_t * targets, const double * in_x, const double * in_y, const uint64_t * roots, uint64_t n_roots, uint64_t seed, double * out_x, double * out_y);
int32_t xyg_graph_lod_decision(uint64_t n_nodes, uint64_t n_edges, uint64_t node_budget, uint64_t edge_budget, uint32_t * out_tier, uint64_t * out_edges_kept);
int32_t xyg_graph_projection_copy_edge_ids(uint64_t handle, uint8_t * output, uint64_t capacity);
int32_t xyg_graph_projection_copy_endpoints(uint64_t handle, uint64_t * out_sources, uint64_t * out_targets, uint64_t capacity);
int32_t xyg_graph_projection_copy_node_ids(uint64_t handle, uint8_t * output, uint64_t capacity);
int32_t xyg_graph_projection_copy_parents(uint64_t handle, uint64_t * out_parents, uint8_t * out_validity, uint64_t capacity);
int32_t xyg_graph_projection_counts(uint64_t handle, uint64_t * out_nodes, uint64_t * out_edges, uint32_t * out_directed);
int32_t xyg_graph_projection_create(const void * descriptor, uint64_t * out_handle);
int32_t xyg_graph_projection_destroy(uint64_t handle);
uint64_t xyg_graph_sample_edges(uint64_t n_edges, uint64_t budget, uint64_t * out_indices);
int32_t xyg_graph_semantic_legend(uint32_t version, uint32_t theme, uint64_t n, const uint8_t * classes, const uint8_t * epistemic, const uint8_t * statuses, uint64_t capacity, uint8_t * out_field, uint8_t * out_value, uint8_t * out_rgba, uint8_t * out_shape, uint64_t * out_count);
int32_t xyg_graph_semantic_style_resolve(uint32_t version, uint32_t theme, uint64_t n, const uint8_t * classes, const uint8_t * epistemic, const uint8_t * statuses, const double * metric, const uint32_t * flags, int32_t edge, uint8_t * fill_rgba, uint8_t * stroke_rgba, uint8_t * halo_rgba, float * size, float * width, float * opacity, uint8_t * shape, uint8_t * dash, uint8_t * arrow, uint8_t * state, double * out_domain_lo, double * out_domain_hi);
int32_t xyg_graph_visual_state_resolve(uint64_t n, const uint32_t * flags, uint8_t * out);
int32_t xyg_heatmap_rgba(const double * raw, size_t w, size_t h, const uint8_t * stops, size_t stop_count, uint8_t alpha, uint8_t * out);
size_t xyg_hexbin(const double * x, const double * y, const double * c, size_t len, size_t grid_w, size_t grid_h, double x0, double x1, double y0, double y1, size_t mincnt, int32_t reduce, double * out_cx, double * out_cy, double * out_metric, double * out_counts, size_t capacity, double * out_dx, double * out_dy);
int32_t xyg_histogram2d(const double * x, const double * y, const double * weights, size_t len, const double * x_edges, size_t x_edge_len, const double * y_edges, size_t y_edge_len, double * out);
size_t xyg_histogram_edges(const double * data, size_t len, double lo, double hi, int32_t use_range, int32_t method, double * out_edges, size_t capacity);
size_t xyg_histogram_uniform(const double * data, size_t len, double lo, double hi, size_t n_bins, int32_t density, double * out_counts);
size_t xyg_indexed_triangles(const double * x, const double * y, size_t vertex_count, const int64_t * triangles, size_t face_count, const double * values, size_t value_len, uint32_t value_mode, double * out_x0, double * out_y0, double * out_x1, double * out_y1, double * out_x2, double * out_y2, double * out_values);
int32_t xyg_is_sorted(const double * data, size_t len);
int32_t xyg_local_log_density(const double * x, const double * y, size_t len, double lo_x, double hi_x, double lo_y, double hi_y, size_t w, size_t h, float * out);
int32_t xyg_lod_grid_shape(int32_t px_w, int32_t px_h, uint64_t visible, double target_per_cell, int32_t * out_w, int32_t * out_h);
int32_t xyg_lod_plan(uint64_t visible, double budget, int32_t in_drill, double exit_factor, int32_t px_w, int32_t px_h, double target_per_cell, int32_t * out_exact, uint32_t * out_mode, int32_t * out_grid_w, int32_t * out_grid_h);
size_t xyg_m4_indices(const double * x, const double * y, size_t len, double x0, double x1, size_t n_buckets, uint32_t * out);
size_t xyg_m4_points(const double * x, const double * y, size_t len, double x0, double x1, size_t n_buckets, double * out_x, double * out_y);
size_t xyg_marching_squares(const double * z, size_t rows, size_t cols, const double * x_coords, const double * y_coords, const double * levels, size_t n_levels, uint8_t corner_mask, double * out_x0, double * out_x1, double * out_y0, double * out_y1, double * out_levels, size_t capacity);
size_t xyg_marching_triangles(const double * x, const double * y, const double * z, size_t vertex_count, const int64_t * triangles, size_t face_count, const double * levels, size_t level_count, double * out_x0, double * out_x1, double * out_y0, double * out_y1, double * out_levels, size_t capacity);
int32_t xyg_min_max(const double * data, size_t len, double * out_min, double * out_max);
int32_t xyg_normalize_f32(const double * data, size_t len, double lo, double hi, int32_t nan_mode, float * out);
size_t xyg_polygon_select(const double * x, const double * y, size_t len, const uint32_t * rows, size_t n_rows, const double * poly_x, const double * poly_y, size_t n_poly, uint32_t * out);
size_t xyg_polygon_triangles(const double * x, const double * y, size_t len, int64_t * out, size_t capacity);
int32_t xyg_pyramid_append(uint64_t handle, const double * x, const double * y, size_t len);
int32_t xyg_pyramid_append_from_stream(uint64_t handle, uint64_t x_handle, uint64_t y_handle, size_t tail_len);
uint64_t xyg_pyramid_build(const double * x, const double * y, size_t len, double x0, double x1, double y0, double y1, uint32_t base_dim);
uint64_t xyg_pyramid_build_color(const double * x, const double * y, size_t len, const uint8_t * idx, const uint8_t * rgba, const uint8_t * lut, size_t lut_len, double x0, double x1, double y0, double y1, uint32_t base_dim);
uint64_t xyg_pyramid_build_from_stream(uint64_t x_handle, uint64_t y_handle, double x0, double x1, double y0, double y1, uint32_t base_dim);
int32_t xyg_pyramid_compose(uint64_t handle, double lo_x, double hi_x, double lo_y, double hi_y, size_t w, size_t h, size_t max_upsample, float * out);
int32_t xyg_pyramid_compose_color(uint64_t handle, double lo_x, double hi_x, double lo_y, double hi_y, size_t w, size_t h, size_t max_upsample, float * out, uint8_t * out_rgba);
int32_t xyg_pyramid_count(uint64_t handle, double lo_x, double hi_x, double lo_y, double hi_y, double * out_count);
int32_t xyg_pyramid_free(uint64_t handle);
uint64_t xyg_pyramid_spill(uint64_t handle);
size_t xyg_quad_mesh_triangles(const double * x, size_t x_len, const double * y, size_t y_len, const double * values, size_t cell_rows, size_t cell_cols, uint32_t layout, double * out_x0, double * out_y0, double * out_x1, double * out_y1, double * out_x2, double * out_y2, double * out_values);
size_t xyg_quantiles(const double * data, size_t len, const double * probs, size_t n_probs, double * out);
size_t xyg_range_indices(const double * x, const double * y, size_t len, double lo_x, double hi_x, double lo_y, double hi_y, uint32_t * out);
size_t xyg_range_indices_rows(const double * x, const double * y, size_t len, const uint32_t * rows, size_t n_rows, double lo_x, double hi_x, double lo_y, double hi_y, uint32_t * out);
int32_t xyg_rasterize(const uint8_t * cmd, size_t cmd_len, uint8_t * out, size_t w, size_t h);
int32_t xyg_rasterize_data(const uint8_t * cmd, size_t cmd_len, const uint8_t * data, size_t data_len, uint8_t * out, size_t w, size_t h);
size_t xyg_rasterize_png(const uint8_t * cmd, size_t cmd_len, uint8_t * out, size_t out_capacity, size_t w, size_t h);
size_t xyg_rasterize_png_data(const uint8_t * cmd, size_t cmd_len, const uint8_t * data, size_t data_len, uint8_t * out, size_t out_capacity, size_t w, size_t h);
size_t xyg_rasterize_png_spans(const uint8_t * cmd, size_t cmd_len, const uint8_t *const * span_ptrs, const size_t * span_lens, size_t span_count, uint8_t * out, size_t out_capacity, size_t w, size_t h);
int32_t xyg_rasterize_spans(const uint8_t * cmd, size_t cmd_len, const uint8_t *const * span_ptrs, const size_t * span_lens, size_t span_count, uint8_t * out, size_t w, size_t h);
int32_t xyg_remap_u8(uint8_t * values, size_t len, const uint8_t * mapping, size_t mapping_len);
int32_t xyg_rfft(const double * data, size_t len, size_t nfft, double sample_rate, double * out_frequency, double * out_real, double * out_imag);
int32_t xyg_sample_mask(const uint64_t * ids, size_t len, uint64_t seed, uint64_t threshold, uint8_t * out);
int32_t xyg_sample_mask_u32(const uint32_t * ids, size_t len, uint64_t seed, uint64_t threshold, uint8_t * out);
size_t xyg_sample_range_indices(size_t size, uint64_t seed, uint64_t threshold, uint32_t * out, size_t capacity);
int32_t xyg_sankey_layout(uint64_t n_nodes, uint64_t n_links, const uint64_t * sources, const uint64_t * targets, const double * values, double node_width, double node_padding, uint32_t align, uint32_t iterations, double * out_x0, double * out_y0, double * out_x1, double * out_y1, uint32_t * out_layer, double * out_value, double * out_source_y0, double * out_source_y1, double * out_target_y0, double * out_target_y1, uint32_t * out_layers, uint64_t * out_err_nodes, uint64_t * out_err_n);
size_t xyg_scene_axis_ticks(uint32_t kind, double lo, double hi, size_t target, double aux, double * out_ticks, double * out_labeled, size_t * out_labeled_len, double * out_step, size_t out_cap);
size_t xyg_scene_batch_encode(double viewport_width, double viewport_height, double margin_left, double margin_right, double margin_top, double margin_bottom, uint64_t x_axis_id, uint32_t x_kind, double x_lo, double x_hi, double x_constant, int32_t x_mask_nonpositive, uint64_t y_axis_id, uint32_t y_kind, double y_lo, double y_hi, double y_constant, int32_t y_mask_nonpositive, const uint8_t * chrome_style, size_t chrome_style_len, const double * x_major_ticks, size_t x_major_count, int32_t x_major_auto, const double * x_minor_ticks, size_t x_minor_count, const double * y_major_ticks, size_t y_major_count, int32_t y_major_auto, const double * y_minor_ticks, size_t y_minor_count, const uint8_t * kinds, const uint64_t * stable_ids, const uint32_t * style_refs, const uint8_t * fill_rgba, const uint8_t * stroke_rgba, const double * stroke_width, size_t style_count, const double * diameter, const uint8_t * symbols, const double * x0, const double * y0, const double * x1, const double * y1, size_t len, const uint8_t * title, size_t title_len, const uint8_t * x_label, size_t x_label_len, const uint8_t * y_label, size_t y_label_len, const uint8_t * legend_input, size_t legend_input_len, uint8_t * out, size_t out_cap);
size_t xyg_scene_browser_painter(const uint8_t * encoded, size_t encoded_len, size_t max_bytes, uint8_t * out, size_t out_cap);
size_t xyg_scene_plot_layout(double viewport_width, double viewport_height, const double * authored_padding, uint32_t x_kind, double x_lo, double x_hi, double x_constant, int32_t x_mask_nonpositive, uint32_t y_kind, double y_lo, double y_hi, double y_constant, int32_t y_mask_nonpositive, const uint8_t * title, size_t title_len, const uint8_t * x_label, size_t x_label_len, const uint8_t * y_label, size_t y_label_len, double * out_margins);
size_t xyg_scene_raster_commands(const uint8_t * encoded, size_t encoded_len, double scale, uint8_t * out, size_t out_cap);
int32_t xyg_scene_scale_map(const double * values, size_t len, uint32_t kind, uint32_t operation, double lo, double hi, double px0, double px1, double constant, int32_t mask_nonpositive, double * out);
size_t xyg_scene_scatter_svg(const double * x, const double * y, const double * diameter, const uint8_t * fill_rgba, const uint8_t * stroke_rgba, const double * stroke_width, const uint8_t * symbols, const uint8_t * visible, const uint8_t * fill_css, size_t fill_css_len, const uint8_t * stroke_css, size_t stroke_css_len, size_t len, uint8_t * out, size_t out_cap);
size_t xyg_scene_support_reason(uint32_t request_version, uint64_t features, uint8_t * out, size_t out_cap);
size_t xyg_scene_svg(const uint8_t * encoded, size_t encoded_len, uint8_t * out, size_t out_cap);
uint32_t xyg_scene_version();
size_t xyg_sector_triangles(const double * values, size_t len, const double * explode, double center_x, double center_y, double radius, double inner_radius, double start_degrees, int32_t counterclockwise, int32_t normalize, double * out_x0, double * out_y0, double * out_x1, double * out_y1, double * out_x2, double * out_y2, double * out_sector, size_t capacity);
int32_t xyg_spectrogram(const double * data, size_t len, size_t nfft, size_t noverlap, double sample_rate, double * out_frequency, double * out_time, double * out_power);
int32_t xyg_stacked_bounds(const double * values, size_t rows, size_t cols, uint32_t baseline, double * out_lower, double * out_upper);
int32_t xyg_stratified_sample_mask(const uint64_t * ids, const uint32_t * groups, size_t len, size_t n_groups, uint64_t seed, double fraction, uint64_t min_count, uint8_t * out);
int32_t xyg_stratified_sample_mask_u32(const uint32_t * ids, const uint32_t * groups, size_t len, size_t n_groups, uint64_t seed, double fraction, uint64_t min_count, uint8_t * out);
size_t xyg_stratified_sample_range_u8(const uint8_t * groups, size_t len, size_t n_groups, uint64_t seed, double fraction, uint64_t min_count, uint32_t * out, size_t capacity);
size_t xyg_stratified_sample_range_u8_counted(const uint8_t * groups, size_t len, const uint64_t * counts, size_t n_groups, uint64_t seed, double fraction, uint64_t min_count, uint32_t * out, size_t capacity);
int32_t xyg_stream_append(uint64_t handle, const double * data, size_t len);
size_t xyg_stream_capacity(uint64_t handle);
int32_t xyg_stream_copy(uint64_t handle, double * out, size_t len);
int32_t xyg_stream_data(uint64_t handle, const double ** out_ptr, size_t * out_len);
int32_t xyg_stream_free(uint64_t handle);
size_t xyg_stream_len(uint64_t handle);
uint64_t xyg_stream_new(const double * data, size_t len);
int32_t xyg_stream_seal(uint64_t handle);
size_t xyg_stream_zone_maps(uint64_t handle, double * out_min, double * out_max, uint64_t * out_count, uint64_t * out_null_count, double * out_sum, double * out_sum_sq, double * out_positive_min, double * out_positive_max);
size_t xyg_streamlines(const double * x_coords, size_t cols, const double * y_coords, size_t rows, const double * u, const double * v, double density, size_t max_steps, double * out_x0, double * out_x1, double * out_y0, double * out_y1, size_t capacity);
size_t xyg_svg_poly_path(const double * x, const double * y, size_t len, uint8_t * out, size_t out_cap);
int32_t xyg_temporal_column_copy(uint64_t handle, int64_t * out_values, uint8_t * out_validity, uint64_t capacity);
int32_t xyg_temporal_column_create(const void * descriptor, uint64_t * out_handle);
int32_t xyg_temporal_column_destroy(uint64_t handle);
int32_t xyg_temporal_column_meta(uint64_t handle, uint64_t * out_len, uint32_t * out_precision, uint32_t * out_timezone_len);
int32_t xyg_temporal_column_timezone(uint64_t handle, uint8_t * out_timezone, uint32_t capacity);
int32_t xyg_temporal_controller_apply_event(uint64_t handle, uint64_t group_id, uint64_t source_instance, uint64_t revision, int64_t range_start, int64_t range_end, int64_t cursor, int64_t window, const uint64_t * selection, uint64_t selection_count, uint32_t * out_applied);
int32_t xyg_temporal_controller_create(const void * descriptor, uint64_t * out_handle);
int32_t xyg_temporal_controller_destroy(uint64_t handle);
int32_t xyg_temporal_controller_dispose(uint64_t handle);
int32_t xyg_temporal_controller_pause(uint64_t handle);
int32_t xyg_temporal_controller_play(uint64_t handle);
int32_t xyg_temporal_controller_poll_event(uint64_t handle, uint32_t * out_has_event, uint64_t * out_group_id, uint64_t * out_source_instance, uint64_t * out_revision, int64_t * out_range_start, int64_t * out_range_end, int64_t * out_cursor, int64_t * out_window, uint64_t * out_selection, uint64_t selection_capacity, uint64_t * out_selection_count);
int32_t xyg_temporal_controller_set_cursor(uint64_t handle, int64_t cursor);
int32_t xyg_temporal_controller_set_direction(uint64_t handle, int32_t direction);
int32_t xyg_temporal_controller_set_loop(uint64_t handle, uint32_t enabled);
int32_t xyg_temporal_controller_set_range(uint64_t handle, int64_t start, int64_t end);
int32_t xyg_temporal_controller_set_rate_milli(uint64_t handle, uint32_t rate_milli);
int32_t xyg_temporal_controller_set_reduced_motion(uint64_t handle, uint32_t enabled);
int32_t xyg_temporal_controller_set_selection(uint64_t handle, const uint64_t * ids, uint64_t count);
int32_t xyg_temporal_controller_state(uint64_t handle, uint64_t * out_instance_id, uint64_t * out_group_id, int64_t * out_domain_start, int64_t * out_domain_end, int64_t * out_range_start, int64_t * out_range_end, int64_t * out_cursor, int64_t * out_window, int64_t * out_step, int32_t * out_direction, uint32_t * out_rate_milli, uint32_t * out_loop_enabled, uint32_t * out_playing, uint32_t * out_reduced_motion, uint64_t * out_revision, uint32_t * out_disposed, uint64_t * out_selection, uint64_t selection_capacity, uint64_t * out_selection_count);
int32_t xyg_temporal_controller_step(uint64_t handle);
int32_t xyg_temporal_controller_tick(uint64_t handle, int64_t dt_micros, uint32_t * out_advanced);
int32_t xyg_temporal_coordinate_deliver(uint64_t group_id, uint64_t source_instance, uint64_t revision, int64_t range_start, int64_t range_end, int64_t cursor, int64_t window, const uint64_t * selection, uint64_t selection_count, uint32_t * out_applied);
int32_t xyg_temporal_events_in_range(const int64_t * event_micros, const uint8_t * event_valid, uint64_t event_len, int64_t range_start, uint32_t range_start_valid, int64_t range_end, uint32_t range_end_valid, uint8_t * out_visibility, uint64_t capacity, uint64_t budget, const uint32_t * cancel_flag);
int32_t xyg_temporal_graph_cancel(uint64_t handle);
int32_t xyg_temporal_graph_create(const void * descriptor, uint64_t * out_handle);
int32_t xyg_temporal_graph_destroy(uint64_t handle);
int32_t xyg_temporal_graph_frame(uint64_t handle, uint64_t revision, int64_t cursor_micros, int64_t range_start_micros, int64_t range_end_micros, uint64_t budget);
int32_t xyg_temporal_graph_required_budget(uint64_t handle, uint64_t * out_budget);
int32_t xyg_temporal_graph_set_focus(uint64_t handle, uint32_t kind, const uint8_t * id);
int32_t xyg_temporal_graph_set_pinned(uint64_t handle, const uint8_t * node_ids, uint64_t node_count);
int32_t xyg_temporal_graph_set_selection(uint64_t handle, const uint8_t * node_ids, uint64_t node_count, const uint8_t * edge_ids, uint64_t edge_count);
int32_t xyg_temporal_graph_snapshot_copy(uint64_t handle, uint64_t expected_revision, const void * buffers);
int32_t xyg_temporal_graph_snapshot_meta(uint64_t handle, void * out_meta);
int32_t xyg_temporal_interval_index_create(const void * descriptor, uint64_t * out_handle);
int32_t xyg_temporal_interval_index_destroy(uint64_t handle);
int32_t xyg_temporal_interval_index_len(uint64_t handle, uint64_t * out_len);
int32_t xyg_temporal_interval_visibility_at(uint64_t handle, int64_t instant_micros, uint8_t * out_visibility, uint64_t capacity, uint64_t budget, const uint32_t * cancel_flag);
uint64_t xyg_temporal_selection_limit();
int32_t xyg_tile_budget_set(uint64_t bytes);
int32_t xyg_tile_store_append(uint64_t store, const double * x, const double * y, size_t len);
int32_t xyg_tile_store_compose(uint64_t store, double lo_x, double hi_x, double lo_y, double hi_y, size_t w, size_t h, size_t max_upsample, float * out);
int32_t xyg_tile_store_compose_color(uint64_t store, double lo_x, double hi_x, double lo_y, double hi_y, size_t w, size_t h, size_t max_upsample, float * out, uint8_t * out_rgba);
int32_t xyg_tile_store_fetch(uint64_t store, uint32_t level, uint32_t tx, uint32_t ty, uint32_t * out_counts, uint16_t * out_color);
int32_t xyg_tile_store_free(uint64_t store);
int32_t xyg_tile_store_stats(uint64_t store, uint64_t * out);
int32_t xyg_transition_keys_fixed(const uint8_t * data, size_t len, size_t width, uint32_t kind, int32_t swap_endian, uint32_t * out_lo, uint32_t * out_hi, size_t * out_error_first, size_t * out_error_index);
size_t xyg_triangle_edges(const double * x, const double * y, size_t vertex_count, const int64_t * triangles, size_t face_count, double * out_x0, double * out_x1, double * out_y0, double * out_y1);
size_t xyg_valid_indices_f64(const double *const * columns, size_t n_columns, size_t len, uint64_t positive_mask, uint32_t * out, size_t capacity);
size_t xyg_vector_segments(const double * x, const double * y, const double * u, const double * v, size_t len, double scale, uint32_t pivot, double head_ratio, double * out_x0, double * out_x1, double * out_y0, double * out_y1);
int32_t xyg_violin_density(const double * data, size_t len, size_t n_bins, double * out_edges, double * out_density);
size_t xyg_weighted_ecdf(const double * values, const double * weights, size_t len, double * out_values, double * out_cumulative);
int32_t xyg_welch_spectra(const double * x, const double * y, size_t len, size_t nfft, size_t noverlap, double sample_rate, double * out_frequency, double * out_pxx, double * out_pyy, double * out_pxy_real, double * out_pxy_imag);
size_t xyg_wind_rose_bins(const double * directions, const double * speeds, size_t len, size_t sectors, const double * speed_edges, size_t n_speed_edges, double * out_edges, size_t capacity_edges, double * out_centres, double * out_counts, size_t capacity_counts, size_t * out_n_obs);
size_t xyg_zone_maps(const double * data, size_t len, size_t chunk_size, double * out_min, double * out_max, uint64_t * out_count, uint64_t * out_null_count, double * out_sum, double * out_sum_sq, double * out_positive_min, double * out_positive_max);
size_t xyg_zone_maps_pair(const double * x, const double * y, size_t len, size_t chunk_size, void * out_x, void * out_y);

#ifdef __cplusplus
}
#endif

#endif /* XYG_ABI_H */
