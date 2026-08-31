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
const { PROTOCOL_VERSION, abiVersion, figure } = await import(
  path.join(root, "packages/xy-node/src/index.js"),
);

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

function caseEntry(name, build, { split = false } = {}) {
  const fig = figure({ width: 240, height: 160 });
  build(fig);
  const { spec } = fig.buildPayload(split ? { split: true } : {});
  const trace = spec.traces[0];
  const density = trace.density ?? {};
  return {
    name,
    trace_id: trace.id,
    tier: trace.tier ?? null,
    density_colormap: density.colormap ?? null,
    density_dropped_channels: density.dropped_channels ?? [],
    density_channels_dropped: density.channels_dropped ?? false,
    density_color_agg: density.color_agg ?? null,
    density_has_rgba: density.rgba != null,
    ...sampleMeta(spec),
    ...(split ? wasmSourceMeta(spec) : {}),
  };
}

const cases = [
  caseEntry("scatter_density_colormap", (fig) => {
    fig.scatter([0, 1, 2], [0, 1, 0.5], { forceDensity: true, colormap: "plasma" });
    fig.traces[0].id = 21;
    fig.traces[0].color_ch = { ...fig.traces[0].color_ch, colormap: "magma" };
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
    { split: true },
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
];

const out = {
  schema: "xyg.density-emit-cross-host/v1",
  authority: "packages/xy-node/src/figure.js buildPayload density wire metadata",
  protocol: PROTOCOL_VERSION,
  abi_version: abiVersion(),
  cases,
};

process.stdout.write(`${JSON.stringify(out, null, 2)}\n`);
