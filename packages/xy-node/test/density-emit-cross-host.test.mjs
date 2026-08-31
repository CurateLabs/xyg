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
  "density_sample_color_size",
  "density_sample_stroke",
  "density_sample_style_channels",
  "density_sample_log_x_ship",
  "density_sample_transition_fallback",
];

const SAMPLE_CASE_KEYS = new Set([
  "trace_id",
  "tier",
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

function densityMeta(spec) {
  const trace = spec.traces[0];
  const density = trace.density ?? {};
  return {
    trace_id: trace.id,
    tier: trace.tier ?? null,
    density_colormap: density.colormap ?? null,
    density_dropped_channels: density.dropped_channels ?? [],
    density_channels_dropped: density.channels_dropped ?? false,
    ...sampleMeta(spec),
  };
}

function caseKeys(caseName, entry) {
  if (caseName.startsWith("density_sample_")) {
    return Object.keys(entry).filter((key) => SAMPLE_CASE_KEYS.has(key));
  }
  return Object.keys(entry).filter((key) => key !== "name");
}

function buildCase(name) {
  const fig = figure({ width: 240, height: 160 });
  if (name === "scatter_density_colormap") {
    fig.scatter([0, 1, 2], [0, 1, 0.5], { forceDensity: true, colormap: "plasma" });
    fig.traces[0].id = 21;
    fig.traces[0].color_ch = { ...fig.traces[0].color_ch, colormap: "magma" };
  } else if (name === "scatter_density_dropped_channels") {
    fig.scatter([0, 1, 2], [0, 1, 0.5], { forceDensity: true, size: [1, 2, 3] });
    fig.traces[0].id = 22;
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
  } else {
    throw new Error(`unknown case ${name}`);
  }
  return fig.buildPayload();
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
    const { spec } = buildCase(entry.name);
    const meta = densityMeta(spec);
    for (const key of caseKeys(entry.name, entry)) {
      assert.deepEqual(meta[key], entry[key], key);
    }
  });
}
