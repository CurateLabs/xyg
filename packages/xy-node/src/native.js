import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import koffi from "koffi";

const packageDir = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const libraryName = "libxy_core.so";

function candidateLibraries() {
  const candidates = [];
  if (process.env.XY_NATIVE_LIB) {
    candidates.push(process.env.XY_NATIVE_LIB);
  }
  candidates.push(path.resolve(packageDir, "..", "..", "target", "release", libraryName));
  candidates.push(path.resolve(process.cwd(), "target", "release", libraryName));
  return candidates;
}

export function resolveNativeLibrary() {
  const candidates = candidateLibraries();
  for (const candidate of candidates) {
    if (candidate && fs.existsSync(candidate)) {
      return candidate;
    }
  }
  throw new Error(
    [
      "Unable to find xy native library.",
      "Set XY_NATIVE_LIB to libxy_core.so or run `cargo build --release` from the repository root.",
      `Searched: ${candidates.join(", ")}`,
    ].join(" "),
  );
}

const libraryPath = resolveNativeLibrary();
const lib = koffi.load(libraryPath);

export const nativeLibraryPath = libraryPath;

// C ABI signatures from src/lib.rs / python/xy/_native.py. Keep in lockstep with ABI_VERSION.
export const xyAbiVersion = lib.func("uint32_t xy_abi_version()");

// --- Encode / LOD / stats (chart wire path) ---
export const xyEncodeF32 = lib.func(
  "int32_t xy_encode_f32(const double *data, size_t len, double offset, double scale, float *out)",
);
export const xyM4Indices = lib.func(
  "size_t xy_m4_indices(const double *x, const double *y, size_t len, double x0, double x1, size_t n_buckets, uint32_t *out)",
);
export const xyM4Points = lib.func(
  "size_t xy_m4_points(const double *x, const double *y, size_t len, double x0, double x1, size_t n_buckets, double *out_x, double *out_y)",
);
export const xyMinMax = lib.func(
  "int32_t xy_min_max(const double *data, size_t len, double *out_min, double *out_max)",
);
export const xyIsSorted = lib.func("int32_t xy_is_sorted(const double *data, size_t len)");
export const xyHistogramUniform = lib.func(
  "size_t xy_histogram_uniform(const double *data, size_t len, double lo, double hi, size_t n_bins, int32_t density, double *out_counts)",
);
export const xyNormalizeF32 = lib.func(
  "int32_t xy_normalize_f32(const double *data, size_t len, double lo, double hi, int32_t nan_mode, float *out)",
);
export const xyValidIndicesF64 = lib.func(
  "size_t xy_valid_indices_f64(const double *const *columns, size_t n_columns, size_t len, uint64_t positive_mask, uint32_t *out, size_t capacity)",
);
export const xyBin2d = lib.func(
  "int32_t xy_bin_2d(const double *x, const double *y, size_t len, double x0, double x1, double y0, double y1, size_t w, size_t h, float *out)",
);
export const xyBin2dF32 = lib.func(
  "int32_t xy_bin_2d_f32(const float *x, const float *y, size_t len, float x0, float x1, float y0, float y1, size_t w, size_t h, float *out)",
);
export const xyHeatmapRgba = lib.func(
  "int32_t xy_heatmap_rgba(const double *raw, size_t w, size_t h, const uint8_t *stops, size_t stop_count, uint8_t alpha, uint8_t *out)",
);
export const xyLocalLogDensity = lib.func(
  "int32_t xy_local_log_density(const double *x, const double *y, size_t len, double lo_x, double hi_x, double lo_y, double hi_y, size_t w, size_t h, float *out)",
);
export const xyDensityLogU8 = lib.func(
  "int32_t xy_density_log_u8(const float *grid, size_t len, uint8_t *out, double *out_max)",
);
export const xyWeightedEcdf = lib.func(
  "size_t xy_weighted_ecdf(const double *values, const double *weights, size_t len, double *out_values, double *out_cumulative)",
);
export const xyStackedBounds = lib.func(
  "int32_t xy_stacked_bounds(const double *values, size_t n_series, size_t n_points, uint32_t mode, double *lower, double *upper)",
);
export const xyMarchingSquares = lib.func(
  "size_t xy_marching_squares(const double *z, size_t rows, size_t cols, const double *x_coords, const double *y_coords, const double *levels, size_t n_levels, uint8_t corner_mask, double *out_x0, double *out_x1, double *out_y0, double *out_y1, double *out_levels, size_t capacity)",
);
export const xyDelaunayTriangles = lib.func(
  "size_t xy_delaunay_triangles(const double *x, const double *y, size_t len, int64_t *out, size_t capacity)",
);
export const xyPolygonTriangles = lib.func(
  "size_t xy_polygon_triangles(const double *x, const double *y, size_t len, int64_t *out, size_t capacity)",
);
export const xyVectorSegments = lib.func(
  "size_t xy_vector_segments(const double *x, const double *y, const double *u, const double *v, size_t len, double scale, uint32_t pivot, double head_ratio, double *out_x0, double *out_x1, double *out_y0, double *out_y1)",
);
export const xyQuadMeshTriangles = lib.func(
  "size_t xy_quad_mesh_triangles(const double *x, size_t x_len, const double *y, size_t y_len, const double *values, size_t cell_rows, size_t cell_cols, uint32_t layout, double *out_x0, double *out_y0, double *out_x1, double *out_y1, double *out_x2, double *out_y2, double *out_values)",
);
export const xyHistogram2d = lib.func(
  "int32_t xy_histogram2d(const double *x, const double *y, const double *weights, size_t len, const double *x_edges, size_t x_edge_len, const double *y_edges, size_t y_edge_len, double *out)",
);

// --- View LOD plan + distribution stats ---
export const xyDrillDecision = lib.func(
  "int32_t xy_drill_decision(uint64_t visible, double budget, int32_t in_drill, double exit_factor, int32_t *out_exact)",
);
export const xyLodGridShape = lib.func(
  "int32_t xy_lod_grid_shape(int32_t px_w, int32_t px_h, uint64_t visible, double target_per_cell, int32_t *out_w, int32_t *out_h)",
);
export const xyLodPlan = lib.func(
  "int32_t xy_lod_plan(uint64_t visible, double budget, int32_t in_drill, double exit_factor, int32_t px_w, int32_t px_h, double target_per_cell, int32_t *out_exact, uint32_t *out_mode, int32_t *out_grid_w, int32_t *out_grid_h)",
);
export const xyQuantiles = lib.func(
  "size_t xy_quantiles(const double *data, size_t len, const double *probs, size_t n_probs, double *out)",
);
export const xyBoxStats = lib.func(
  "int32_t xy_box_stats(const double *data, size_t len, double *out_stats, double *out_outliers, size_t outliers_cap, size_t *out_n_outliers)",
);
export const xyHexbin = lib.func(
  "size_t xy_hexbin(const double *x, const double *y, const double *c, size_t len, size_t grid_w, size_t grid_h, double x0, double x1, double y0, double y1, size_t mincnt, int32_t reduce, double *out_cx, double *out_cy, double *out_metric, double *out_counts, size_t capacity, double *out_dx, double *out_dy)",
);
export const xyViolinDensity = lib.func(
  "int32_t xy_violin_density(const double *data, size_t len, size_t n_bins, double *out_edges, double *out_density)",
);
export const xyHistogramEdges = lib.func(
  "size_t xy_histogram_edges(const double *data, size_t len, double lo, double hi, int32_t use_range, int32_t method, double *out_edges, size_t capacity)",
);
export const xyWindRoseBins = lib.func(
  "size_t xy_wind_rose_bins(const double *directions, const double *speeds, size_t len, size_t sectors, const double *speed_edges, size_t n_speed_edges, double *out_edges, size_t capacity_edges, double *out_centres, double *out_counts, size_t capacity_counts, size_t *out_n_obs)",
);
export const xyContourfDensify = lib.func(
  "int32_t xy_contourf_densify(const double *z, size_t rows, size_t cols, const double *xpos, const double *ypos, double *out_z, double *out_x, double *out_y, size_t out_z_cap, size_t out_x_cap, size_t out_y_cap, size_t *out_rows, size_t *out_cols)",
);
export const xyBarStack = lib.func(
  "int32_t xy_bar_stack(const double *pos, size_t n_items, const double *values, size_t n_series, const double *width, size_t width_len, const double *base, size_t base_len, uint32_t mode, uint32_t orientation, double *out_x0, double *out_x1, double *out_y0, double *out_y1)",
);
export const xyContourfBands = lib.func(
  "size_t xy_contourf_bands(const double *z, size_t rows, size_t cols, const double *xpos, const double *ypos, const double *edges, size_t n_edges, uint8_t extend_min, uint8_t extend_max, double *out_x0, double *out_y0, double *out_x1, double *out_y1, double *out_x2, double *out_y2, int64_t *out_slots, size_t capacity)",
);

// --- Tier-3 tile pyramid (lod-architecture §4 / Phase 3) ---
export const xyPyramidBuild = lib.func(
  "uint64_t xy_pyramid_build(const double *x, const double *y, size_t len, double x0, double x1, double y0, double y1, uint32_t base_dim)",
);
export const xyPyramidBuildColor = lib.func(
  "uint64_t xy_pyramid_build_color(const double *x, const double *y, size_t len, const uint8_t *idx, const uint8_t *rgba, const uint8_t *lut, size_t lut_len, double x0, double x1, double y0, double y1, uint32_t base_dim)",
);
export const xyPyramidAppend = lib.func(
  "int32_t xy_pyramid_append(uint64_t handle, const double *x, const double *y, size_t len)",
);
export const xyPyramidCount = lib.func(
  "int32_t xy_pyramid_count(uint64_t handle, double lo_x, double hi_x, double lo_y, double hi_y, double *out_count)",
);
export const xyPyramidCompose = lib.func(
  "int32_t xy_pyramid_compose(uint64_t handle, double lo_x, double hi_x, double lo_y, double hi_y, size_t w, size_t h, size_t max_upsample, float *out)",
);
export const xyPyramidComposeColor = lib.func(
  "int32_t xy_pyramid_compose_color(uint64_t handle, double lo_x, double hi_x, double lo_y, double hi_y, size_t w, size_t h, size_t max_upsample, float *out, uint8_t *out_rgba)",
);
export const xyPyramidFree = lib.func("int32_t xy_pyramid_free(uint64_t handle)");

// --- Phase-4 tile store (lod-architecture §4 items 10-12, roadmap D1-D7).
// Signature stubs only (ABI 58): host engagement — spill gating, §28
// residency recording, PYRAMID_RESIDENT_BYTES plumbing — is WP2 (#9).
export const xyPyramidSpill = lib.func("uint64_t xy_pyramid_spill(uint64_t handle)");
export const xyTileStoreFetch = lib.func(
  "int32_t xy_tile_store_fetch(uint64_t store, uint32_t level, uint32_t tx, uint32_t ty, uint32_t *out_counts, uint16_t *out_color)",
);
export const xyTileStoreCompose = lib.func(
  "int32_t xy_tile_store_compose(uint64_t store, double lo_x, double hi_x, double lo_y, double hi_y, size_t w, size_t h, size_t max_upsample, float *out)",
);
export const xyTileStoreComposeColor = lib.func(
  "int32_t xy_tile_store_compose_color(uint64_t store, double lo_x, double hi_x, double lo_y, double hi_y, size_t w, size_t h, size_t max_upsample, float *out, uint8_t *out_rgba)",
);
export const xyTileStoreAppend = lib.func(
  "int32_t xy_tile_store_append(uint64_t store, const double *x, const double *y, size_t len)",
);
export const xyTileStoreStats = lib.func(
  "int32_t xy_tile_store_stats(uint64_t store, uint64_t *out)",
);
export const xyTileBudgetSet = lib.func("int32_t xy_tile_budget_set(uint64_t bytes)");
export const xyTileStoreFree = lib.func("int32_t xy_tile_store_free(uint64_t store)");

// --- Graph / Sankey ---
export const xyGraphLayout = lib.func(
  "int32_t xy_graph_layout(uint32_t layout, uint64_t n_nodes, uint64_t n_edges, const uint64_t *sources, const uint64_t *targets, const double *in_x, const double *in_y, const uint64_t *roots, uint64_t n_roots, uint64_t seed, double *out_x, double *out_y)",
);
export const xyGraphForceCreate = lib.func(
  "int32_t xy_graph_force_create(uint64_t n_nodes, uint64_t n_edges, const uint64_t *sources, const uint64_t *targets, const double *in_x, const double *in_y, uint64_t seed, uint32_t algorithm, uint64_t *out_handle)",
);
export const xyGraphForceTick = lib.func(
  "int32_t xy_graph_force_tick(uint64_t handle, uint64_t n_nodes, uint32_t steps, double *out_x, double *out_y, double *out_alpha)",
);
export const xyGraphForceDestroy = lib.func(
  "int32_t xy_graph_force_destroy(uint64_t handle)",
);
export const xyGraphBuildCsr = lib.func(
  "int32_t xy_graph_build_csr(uint64_t n_nodes, uint64_t n_edges, const uint64_t *sources, const uint64_t *targets, int32_t directed, uint64_t *out_offsets, uint64_t *out_neighbors, uint64_t neighbors_cap, uint64_t *out_neighbor_len)",
);
export const xyGraphLodDecision = lib.func(
  "int32_t xy_graph_lod_decision(uint64_t n_nodes, uint64_t n_edges, uint64_t node_budget, uint64_t edge_budget, uint32_t *out_tier, uint64_t *out_edges_kept)",
);
export const xyGraphClusterAggregate = lib.func(
  "int32_t xy_graph_cluster_aggregate(uint64_t n_nodes, uint64_t n_edges, const double *x, const double *y, uint64_t node_budget, uint64_t edge_budget, double *out_x, double *out_y, uint64_t *out_count, uint64_t *out_member_of, uint32_t *out_tier, uint64_t *out_edges_kept)",
);
export const xyGraphBuildRender = lib.func(
  "int32_t xy_graph_build_render(uint64_t n_nodes, uint64_t n_edges, const double *x, const double *y, const uint64_t *sources, const uint64_t *targets, uint64_t node_budget, uint64_t edge_budget, int32_t viewport_enabled, double vp_x0, double vp_y0, double vp_x1, double vp_y1, double *out_node_x, double *out_node_y, uint64_t *out_member_of, uint64_t *out_edge_sources, uint64_t *out_edge_targets, uint64_t *out_n_nodes, uint64_t *out_n_edges, uint32_t *out_tier, uint64_t *out_edges_kept)",
);
export const xyGraphSampleEdges = lib.func(
  "uint64_t xy_graph_sample_edges(uint64_t n_edges, uint64_t budget, uint64_t *out_indices)",
);
export const xySankeyLayout = lib.func(
  "int32_t xy_sankey_layout(uint64_t n_nodes, uint64_t n_links, const uint64_t *sources, const uint64_t *targets, const double *values, double node_width, double node_padding, uint32_t align, uint32_t iterations, double *out_x0, double *out_y0, double *out_x1, double *out_y1, uint32_t *out_layer, double *out_value, double *out_source_y0, double *out_source_y1, double *out_target_y0, double *out_target_y1, uint32_t *out_layers, uint64_t *out_err_nodes, uint64_t *out_err_n)",
);

export function pointer(view, cType) {
  if (view == null) {
    return null;
  }
  if (!ArrayBuffer.isView(view)) {
    throw new TypeError("native pointer arguments must be TypedArrays or DataViews");
  }
  if (view.byteLength === 0) {
    return null;
  }
  const buffer = Buffer.from(view.buffer, view.byteOffset, view.byteLength);
  return koffi.as(buffer, cType);
}

/** Optional symbol probe — returns null when the cdylib lacks the export. */
export function tryFunc(signature) {
  try {
    return lib.func(signature);
  } catch {
    return null;
  }
}
