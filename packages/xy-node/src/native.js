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

// C ABI signatures from src/lib.rs. Keep these in lockstep with ABI_VERSION.
export const xyAbiVersion = lib.func("uint32_t xy_abi_version()");

export const xyGraphLayout = lib.func(
  "int32_t xy_graph_layout(uint32_t layout, uint64_t n_nodes, uint64_t n_edges, const uint64_t *sources, const uint64_t *targets, const double *in_x, const double *in_y, const uint64_t *roots, uint64_t n_roots, uint64_t seed, double *out_x, double *out_y)",
);

export const xyGraphForceCreate = lib.func(
  "int32_t xy_graph_force_create(uint64_t n_nodes, uint64_t n_edges, const uint64_t *sources, const uint64_t *targets, const double *in_x, const double *in_y, uint64_t seed, uint64_t *out_handle)",
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

export const xyGraphClusterPositions = lib.func(
  "int32_t xy_graph_cluster_positions(uint64_t n_nodes, const double *x, const double *y, uint64_t budget, double *out_x, double *out_y, uint64_t *out_count, uint64_t *out_member_of)",
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
