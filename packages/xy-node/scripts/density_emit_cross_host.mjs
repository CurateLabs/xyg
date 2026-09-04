#!/usr/bin/env node
/**
 * Emit density wire-metadata cross-host goldens — consumed by tests/test_density_emit_cross_host.py.
 *
 * Usage (from repo root):
 *   node packages/xy-node/scripts/density_emit_cross_host.mjs
 */
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../..");
const { PROTOCOL_VERSION, abiVersion, figure, payloadTier } = await import(
  path.join(root, "packages/xy-node/src/index.js"),
);
const { DENSITY_SAMPLE_TARGET, payloadDensityTraceEmitPlan } = await import(
  path.join(root, "packages/xy-node/src/encode.js"),
);

const MASSIVE_GRID_W = 512;
const MASSIVE_GRID_H = 384;

function massivePolicyEntry(pointCount) {
  const plan = payloadDensityTraceEmitPlan({
    pointOverlay: true,
    splitPayload: false,
    gridW: MASSIVE_GRID_W,
    gridH: MASSIVE_GRID_H,
    nPoints: pointCount,
  });
  const tierCode = payloadTier({ kind: 1, nPoints: pointCount });
  const densityGridBytesMax = plan.nMarks;
  const sampleGeometryBytesMax = 2 * 4 * (DENSITY_SAMPLE_TARGET + MASSIVE_GRID_W);
  const canonicalF64Bytes = plan.shipWasmSource ? pointCount * 16 : 0;
  return {
    point_count: pointCount,
    tier: ["direct", "decimated", "density"][tierCode] ?? "invalid",
    n_marks: plan.nMarks,
    pyramid_eligible: plan.pyramidEligible,
    wasm_eligible: plan.wasmEligible,
    attach_sample: plan.attachSample,
    ship_wasm_source: plan.shipWasmSource,
    density_grid_bytes_max: densityGridBytesMax,
    sample_geometry_bytes_max: sampleGeometryBytesMax,
    canonical_f64_bytes: canonicalF64Bytes,
    other_bytes: 0,
    total_bytes_max: densityGridBytesMax + sampleGeometryBytesMax + canonicalF64Bytes,
  };
}

function stripWireBuffers(obj) {
  if (obj == null || typeof obj !== "object") return obj;
  if (Array.isArray(obj)) return obj.map(stripWireBuffers);
  const out = {};
  for (const [key, value] of Object.entries(obj)) {
    if (key === "buf" || key === "byte_offset" || key === "col") continue;
    out[key] = stripWireBuffers(value);
  }
  return out;
}

function sampleMeta(spec) {
  const trace = spec.traces[0];
  const sample = trace.density?.sample ?? {};
  return {
    has_sample: Object.keys(sample).length > 0,
    sample_n: sample.n ?? null,
    sample_visible: sample.visible ?? null,
    sample_color: stripWireBuffers(sample.color ?? null),
    sample_size: stripWireBuffers(sample.size ?? null),
    sample_stroke: stripWireBuffers(sample.stroke ?? null),
    sample_channels: stripWireBuffers(sample.channels ?? null),
    sample_x_offset: sample.x?.offset ?? null,
    sample_y_offset: sample.y?.offset ?? null,
    animation_fallback: trace.animation_fallback ?? null,
  };
}

function columnDtype(columns, colRef) {
  if (typeof colRef !== "number") return null;
  if (Array.isArray(columns)) {
    return columns[colRef]?.dtype ?? null;
  }
  return columns?.[colRef]?.dtype ?? null;
}

function wasmSourceMeta(spec) {
  const wasmSource = spec.traces[0].density?.wasm_source ?? {};
  const columns = spec.columns ?? {};
  return {
    has_wasm_source: Object.keys(wasmSource).length > 0,
    wasm_source_kind: wasmSource.kind ?? null,
    wasm_source_point_count: wasmSource.point_count ?? null,
    wasm_source_trace_id: wasmSource.trace_id ?? null,
    wasm_source_capacity: wasmSource.capacity ?? null,
    wasm_source_ownership: wasmSource.ownership ?? null,
    wasm_source_x_dtype: columnDtype(columns, wasmSource.x),
    wasm_source_y_dtype: columnDtype(columns, wasmSource.y),
    wasm_density_automatic: spec.wasm_density?.automatic ?? null,
    buffer_layout: spec.buffer_layout ?? null,
  };
}

function caseEntry(name, build, { split = false, wasmSource = false, gridMeta = false } = {}) {
  const fig = figure({ width: 240, height: 160 });
  build(fig);
  const { spec } = fig.buildPayload(split ? { split: true, wasmSource } : {});
  const trace = spec.traces[0];
  const density = trace.density ?? {};
  const entry = {
    name,
    trace_id: trace.id,
    tier: trace.tier ?? null,
    visible: trace.visible ?? null,
    density_colormap: density.colormap ?? null,
    density_color: density.color ?? null,
    density_dropped_channels: density.dropped_channels ?? [],
    density_channels_dropped: density.channels_dropped ?? false,
    density_color_agg: density.color_agg ?? null,
    density_has_rgba: density.rgba != null,
    entry_color: stripWireBuffers(trace.color ?? null),
    ...sampleMeta(spec),
    ...(split ? wasmSourceMeta(spec) : {}),
  };
  if (gridMeta) {
    entry.density_max = density.max ?? null;
    entry.density_binning = density.binning ?? null;
    entry.density_reduction = density.reduction ?? null;
  }
  return entry;
}

const cases = [
  caseEntry("scatter_density_colormap", (fig) => {
    fig.scatter([0, 1, 2], [0, 1, 0.5], { forceDensity: true, colormap: "plasma" });
    fig.traces[0].id = 21;
    fig.traces[0].color_ch = { ...fig.traces[0].color_ch, colormap: "magma" };
  }),
  caseEntry("scatter_density_continuous_colormap", (fig) => {
    fig.scatter([0, 1, 2, 3], [0, 1, 0.5, 0.2], {
      forceDensity: true,
      colormap: "plasma",
      color: [1, 2, 3, 4],
    });
    fig.traces[0].id = 24;
    fig.traces[0].color_ch = { ...fig.traces[0].color_ch, colormap: "inferno" };
  }),
  caseEntry("scatter_density_constant_color", (fig) => {
    fig.scatter([0, 1, 2], [0, 1, 0.5], { forceDensity: true, style: { color: "#112233" } });
    fig.traces[0].id = 25;
    fig.traces[0].color_ch = { mode: "constant", constant: "#22c55e" };
  }),
  caseEntry("scatter_density_dropped_channels", (fig) => {
    fig.scatter([0, 1, 2], [0, 1, 0.5], { forceDensity: true, size: [1, 2, 3] });
    fig.traces[0].id = 22;
  }),
  caseEntry("scatter_density_mean_color_categorical", (fig) => {
    fig.scatter([0, 1, 2, 3, 4], [0, 1, 0.5, 0.2, 0.8], {
      forceDensity: true,
      color: ["a", "b", "a", "c", "b"],
      size: [1, 2, 3, 4, 5],
    });
    fig.traces[0].id = 23;
  }),
  caseEntry(
    "scatter_density_wasm_source_split",
    (fig) => {
      fig.scatter([1, 10], [1, 10], { forceDensity: true });
      fig.traces[0].id = 41;
    },
    { split: true, wasmSource: true },
  ),
  caseEntry("density_sample_color_size", (fig) => {
    fig.scatter([0, 1, 2, 3, 4], [0, 1, 0.5, 0.2, 0.8], {
      forceDensity: true,
      color: ["a", "b", "a", "c", "b"],
      size: [1, 2, 3, 4, 5],
    });
    fig.traces[0].id = 31;
  }),
  caseEntry("density_sample_stroke", (fig) => {
    fig.scatter([0, 1, 2], [0, 1, 0.5], {
      forceDensity: true,
      stroke: ["#f00", "#0f0", "#00f"],
    });
    fig.traces[0].id = 32;
  }),
  caseEntry("density_sample_style_channels", (fig) => {
    fig.scatter([0, 1, 2], [0, 1, 0.5], { forceDensity: true });
    fig.traces[0].id = 33;
    fig.traces[0].style_channels = {
      opacity: {
        mode: "direct",
        values: new Float64Array([0.5, 0.6, 0.7]),
        components: 1,
        dtype: "f32",
      },
    };
  }),
  caseEntry("density_sample_log_x_ship", (fig) => {
    fig.setAxis("x", { type: "log" });
    fig.scatter([1, 10, 100], [1, 10, 100], { forceDensity: true });
    fig.traces[0].id = 34;
  }),
  caseEntry("density_sample_transition_fallback", (fig) => {
    fig.scatter([0, 1], [0, 1], { forceDensity: true });
    fig.traces[0].id = 35;
    fig.traces[0].transition_keys = [
      [1, 2],
      [3, 4],
    ];
  }),
  caseEntry("density_sample_nan_oov_filter", (fig) => {
    fig.setAxisDomain("x", [0, 1.5]);
    fig.setAxisDomain("y", [0, 2.5]);
    fig.scatter([0, 1, NaN, 5], [1, 2, 3, 4], { forceDensity: true });
    fig.traces[0].id = 36;
  }),
  caseEntry(
    "scatter_density_log_y_grid",
    (fig) => {
      fig.setAxis("y", { type: "log", domain: [1, 100] });
      const n = 80;
      const x = new Float64Array(n);
      const y = new Float64Array(n);
      for (let i = 0; i < n; i++) {
        x[i] = 1;
        y[i] = i < 70 ? 1 + i * 0.01 : 10 + (i - 70);
      }
      fig.scatter(x, y, { forceDensity: true });
      fig.traces[0].id = 37;
    },
    { gridMeta: true },
  ),
];

const out = {
  schema: "xyg.density-emit-cross-host/v1",
  authority: "packages/xy-node/src/figure.js buildPayload density wire metadata",
  protocol: PROTOCOL_VERSION,
  abi_version: abiVersion(),
  cases,
  massive_policy: [1_000_000, 100_000_000].map(massivePolicyEntry),
};

process.stdout.write(`${JSON.stringify(out, null, 2)}\n`);
