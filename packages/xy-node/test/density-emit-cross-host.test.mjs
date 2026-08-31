import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

import { PROTOCOL_VERSION, abiVersion, figure } from "../src/index.js";

const fixture = JSON.parse(
  fs.readFileSync(new URL("../../../tests/fixtures/density_emit_cross_host.json", import.meta.url), "utf8"),
);

const CASE_NAMES = [
  "scatter_density_colormap",
  "scatter_density_dropped_channels",
  "scatter_density_mean_color_categorical",
  "scatter_density_wasm_source_split",
  "density_sample_color_size",
  "density_sample_stroke",
  "density_sample_style_channels",
  "density_sample_log_x_ship",
  "density_sample_transition_fallback",
  "density_sample_nan_oov_filter",
  "scatter_density_log_y_grid",
];

const GRID_META_CASE_KEYS = new Set([
  "trace_id",
  "tier",
  "visible",
  "density_max",
  "density_binning",
  "density_reduction",
  "density_colormap",
  "density_dropped_channels",
  "density_channels_dropped",
  "density_color_agg",
  "density_has_rgba",
  "entry_color",
  "has_sample",
  "sample_n",
  "sample_visible",
  "sample_color",
  "sample_size",
  "sample_stroke",
  "sample_channels",
  "sample_x_offset",
  "sample_y_offset",
  "animation_fallback",
]);

const SAMPLE_CASE_KEYS = new Set([
  "trace_id",
  "tier",
  "has_sample",
  "sample_n",
  "sample_visible",
  "visible",
  "sample_color",
  "sample_size",
  "sample_stroke",
  "sample_channels",
  "sample_x_offset",
  "sample_y_offset",
  "animation_fallback",
  "entry_color",
]);

const WASM_SOURCE_CASE_KEYS = new Set([
  "trace_id",
  "tier",
  "has_wasm_source",
  "wasm_source_kind",
  "wasm_source_point_count",
  "wasm_source_trace_id",
  "wasm_source_capacity",
  "wasm_source_ownership",
  "wasm_source_x_dtype",
  "wasm_source_y_dtype",
  "wasm_density_automatic",
  "buffer_layout",
]);

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

function columnDtype(columns, colRef) {
  if (typeof colRef !== "number") return null;
  if (Array.isArray(columns)) {
    return columns[colRef]?.dtype ?? null;
  }
  return columns?.[colRef]?.dtype ?? null;
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

function densityMeta(spec, { caseName = "", split = false } = {}) {
  const trace = spec.traces[0];
  const density = trace.density ?? {};
  const meta = {
    trace_id: trace.id,
    tier: trace.tier ?? null,
    visible: trace.visible ?? null,
    density_colormap: density.colormap ?? null,
    density_dropped_channels: density.dropped_channels ?? [],
    density_channels_dropped: density.channels_dropped ?? false,
    density_color_agg: density.color_agg ?? null,
    density_has_rgba: density.rgba != null,
    entry_color: stripWireBuffers(trace.color ?? null),
    ...sampleMeta(spec),
    ...(split ? wasmSourceMeta(spec) : {}),
  };
  if (caseName === "scatter_density_log_y_grid") {
    meta.density_max = density.max ?? null;
    meta.density_binning = density.binning ?? null;
    meta.density_reduction = density.reduction ?? null;
  }
  return meta;
}

function caseKeys(caseName, entry) {
  if (caseName.startsWith("density_sample_")) {
    return Object.keys(entry).filter((key) => SAMPLE_CASE_KEYS.has(key));
  }
  if (caseName.startsWith("scatter_density_wasm_source")) {
    return Object.keys(entry).filter((key) => WASM_SOURCE_CASE_KEYS.has(key));
  }
  if (caseName === "scatter_density_log_y_grid") {
    return Object.keys(entry).filter((key) => GRID_META_CASE_KEYS.has(key));
  }
  return Object.keys(entry).filter((key) => key !== "name");
}

function buildCase(name) {
  const fig = figure({ width: 240, height: 160 });
  let split = false;
  if (name === "scatter_density_colormap") {
    fig.scatter([0, 1, 2], [0, 1, 0.5], { forceDensity: true, colormap: "plasma" });
    fig.traces[0].id = 21;
    fig.traces[0].color_ch = { ...fig.traces[0].color_ch, colormap: "magma" };
  } else if (name === "scatter_density_dropped_channels") {
    fig.scatter([0, 1, 2], [0, 1, 0.5], { forceDensity: true, size: [1, 2, 3] });
    fig.traces[0].id = 22;
  } else if (name === "scatter_density_mean_color_categorical") {
    fig.scatter([0, 1, 2, 3, 4], [0, 1, 0.5, 0.2, 0.8], {
      forceDensity: true,
      color: ["a", "b", "a", "c", "b"],
      size: [1, 2, 3, 4, 5],
    });
    fig.traces[0].id = 23;
  } else if (name === "scatter_density_wasm_source_split") {
    fig.scatter([1, 10], [1, 10], { forceDensity: true });
    fig.traces[0].id = 41;
    split = true;
  } else if (name === "density_sample_color_size") {
    fig.scatter([0, 1, 2, 3, 4], [0, 1, 0.5, 0.2, 0.8], {
      forceDensity: true,
      color: ["a", "b", "a", "c", "b"],
      size: [1, 2, 3, 4, 5],
    });
    fig.traces[0].id = 31;
  } else if (name === "density_sample_stroke") {
    fig.scatter([0, 1, 2], [0, 1, 0.5], {
      forceDensity: true,
      stroke: ["#f00", "#0f0", "#00f"],
    });
    fig.traces[0].id = 32;
  } else if (name === "density_sample_style_channels") {
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
  } else if (name === "density_sample_log_x_ship") {
    fig.setAxis("x", { type: "log" });
    fig.scatter([1, 10, 100], [1, 10, 100], { forceDensity: true });
    fig.traces[0].id = 34;
  } else if (name === "density_sample_transition_fallback") {
    fig.scatter([0, 1], [0, 1], { forceDensity: true });
    fig.traces[0].id = 35;
    fig.traces[0].transition_keys = [
      [1, 2],
      [3, 4],
    ];
  } else if (name === "density_sample_nan_oov_filter") {
    fig.setAxisDomain("x", [0, 1.5]);
    fig.setAxisDomain("y", [0, 2.5]);
    fig.scatter([0, 1, NaN, 5], [1, 2, 3, 4], { forceDensity: true });
    fig.traces[0].id = 36;
  } else if (name === "scatter_density_log_y_grid") {
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
  } else {
    throw new Error(`unknown case ${name}`);
  }
  return { spec: fig.buildPayload(split ? { split: true } : {}).spec, split };
}

test("density emit cross-host fixture contract", () => {
  assert.equal(fixture.schema, "xyg.density-emit-cross-host/v1");
  assert.equal(fixture.protocol, PROTOCOL_VERSION);
  assert.equal(Number(fixture.abi_version), abiVersion());
  assert.equal(fixture.cases.length, CASE_NAMES.length);
  assert.deepEqual(fixture.cases.map((entry) => entry.name), CASE_NAMES);
});

for (const entry of fixture.cases) {
  test(`Node density wire metadata matches fixture for ${entry.name}`, () => {
    const { spec, split } = buildCase(entry.name);
    const meta = densityMeta(spec, { caseName: entry.name, split });
    for (const key of caseKeys(entry.name, entry)) {
      assert.deepEqual(meta[key], entry[key], key);
    }
  });
}
