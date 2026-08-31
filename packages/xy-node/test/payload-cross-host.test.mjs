import assert from "node:assert/strict";
import crypto from "node:crypto";
import fs from "node:fs";
import test from "node:test";

import { PROTOCOL_VERSION, abiVersion, figure } from "../src/index.js";

const fixture = JSON.parse(
  fs.readFileSync(new URL("../../../tests/fixtures/payload_cross_host.json", import.meta.url), "utf8"),
);

function sha256(buf) {
  return crypto.createHash("sha256").update(Buffer.from(buf)).digest("hex");
}

function buildCase(name) {
  const fig = figure({ width: 240, height: 160 });
  if (name === "scatter_direct") {
    fig.scatter([0, 1, 2], [0, 1, 0.5]);
    fig.traces[0].id = 7;
  } else if (name === "scatter_categorical_color") {
    fig.scatter([0, 1, 2], [0, 1, 0.5], { color: ["a", "b", "a"] });
    fig.traces[0].id = 15;
  } else if (name === "line_transition_keys") {
    fig.line([0, 1, 2], [0, 1, 0.5]);
    fig.traces[0].id = 8;
    fig.traces[0].transition_keys = [
      [1, 2],
      [3, 4],
      [5, 6],
    ];
  } else if (name === "histogram_fixed_bins") {
    fig.histogram([0, 1, 1, 2, 3], { bins: 3, range: [0, 3] });
    fig.traces[0].id = 10;
  } else if (name === "histogram_finite_sel") {
    fig.traces.push({
      kind: "histogram",
      id: 17,
      name: null,
      x0: new Float64Array([0, 1]),
      x1: new Float64Array([1, 2]),
      y0: new Float64Array([0, 0]),
      y1: new Float64Array([1, Number.NaN]),
      style: { color: "#3987e5", opacity: 0.85, role: "histogram" },
      count: 4,
    });
  } else if (name === "histogram_style_channels") {
    fig.histogram([0, 1, 1, 2], { bins: 2, range: [0, 2] });
    fig.traces[0].style_channels = { stroke_width: { mode: "constant", constant: 2 } };
    fig.traces[0].id = 21;
  } else if (name === "segments_pass_through") {
    fig.segments([0, 1], [0, 1], [1, 2], [1, 0]);
    fig.traces[0].id = 12;
  } else if (name === "segments_color_ch") {
    fig.segments([0], [0], [1], [1], { color: "#112233" });
    fig.traces[0].color_ch = { mode: "constant", constant: "#445566" };
    fig.traces[0].id = 22;
  } else if (name === "rect_color_ch") {
    fig.bar([0, 1], [1, 2], { color: "#112233" });
    fig.traces[0].color_ch = { mode: "constant", constant: "#445566" };
    fig.traces[0].id = 23;
  } else if (name === "mesh_style_channels") {
    fig.triangleMesh([0], [0], [1], [0], [0.5], [1]);
    fig.traces[0].style_channels = { stroke_width: { mode: "constant", constant: 2 } };
    fig.traces[0].id = 24;
  } else if (name === "ribbon_style_channels") {
    fig.ribbon([0], [1], [0], [1], [0], [1], { color: "#112233" });
    fig.traces[0].style_channels = { stroke_width: { mode: "constant", constant: 2 } };
    fig.traces[0].id = 25;
  } else if (name === "hexbin_colormap") {
    fig.axis_options = { x: { domain: [0, 4] }, y: { domain: [0, 5] } };
    fig.hexbin(
      [0.5, 1.5, 2.5, 3.5, 1.0, 2.0, 3.0],
      [0.5, 0.5, 0.5, 0.5, 2.0, 2.0, 2.0],
      { gridsize: [4, 4], range: [[0, 4], [0, 5]], name: "hex" },
    );
    fig.traces[0].id = 14;
  } else if (name === "bar_compact") {
    fig.bar([0, 1], [1, 2]);
    fig.traces[0].id = 9;
  } else if (name === "heatmap_colormap") {
    fig.heatmap([[0, 1], [1, 0]], { colormap: "viridis" });
    fig.traces[0].id = 11;
  } else if (name === "triangle_mesh_single") {
    fig.triangleMesh([0], [0], [1], [0], [0.5], [1]);
    fig.traces[0].id = 20;
  } else {
    throw new Error(`unknown case ${name}`);
  }
  return fig.buildPayload();
}

test("payload cross-host fixture contract", () => {
  assert.equal(fixture.schema, "xyg.payload-cross-host/v1");
  assert.equal(fixture.protocol, PROTOCOL_VERSION);
  assert.equal(Number(fixture.abi_version), abiVersion());
  assert.equal(fixture.cases.length, 15);
});

for (const entry of fixture.cases) {
  test(`Node payload blob matches Python fixture for ${entry.name}`, () => {
    const { spec, buffers } = buildCase(entry.name);
    const trace = spec.traces[0];
    assert.equal(trace.id, entry.trace_id);
    assert.equal(trace.kind, entry.kind);
    assert.equal(buffers.length, entry.payload_blob_len);
    assert.equal(sha256(buffers), entry.payload_blob_sha256);
    assert.equal(Buffer.from(buffers).toString("hex"), entry.payload_blob_hex);
    if (entry.name === "triangle_mesh_single") {
      assert.ok(trace.x2 != null);
      assert.ok(trace.y2 != null);
      assert.equal(trace.x, undefined);
      assert.equal(trace.y, undefined);
    }
    if (entry.trace_keys != null) {
      assert.deepEqual(trace.keys, entry.trace_keys);
      const lo = spec.columns[trace.keys.lo];
      const hi = spec.columns[trace.keys.hi];
      assert.equal(
        Buffer.from(buffers).subarray(lo.byte_offset, lo.byte_offset + lo.len * 4).toString("hex"),
        entry.keys_lo_hex,
      );
      assert.equal(
        Buffer.from(buffers).subarray(hi.byte_offset, hi.byte_offset + hi.len * 4).toString("hex"),
        entry.keys_hi_hex,
      );
    }
  });
}
