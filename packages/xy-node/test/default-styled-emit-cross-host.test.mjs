import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

import { DEFAULT_PALETTE, PROTOCOL_VERSION, abiVersion, figure } from "../src/index.js";

const fixture = JSON.parse(
  fs.readFileSync(
    new URL("../../../tests/fixtures/default_styled_emit_cross_host.json", import.meta.url),
    "utf8",
  ),
);

function buildCase(name) {
  const entry = fixture.cases.find((c) => c.name === name);
  if (entry == null) throw new Error(`unknown case ${name}`);
  const fig = figure({ width: 240, height: 160 });
  if (name === "line_default_styled") {
    fig.line([0, 1], [0, 1]);
    fig.traces[0].id = entry.trace_id;
    fig.traces[0].style = { opacity: 0.9 };
  } else if (name === "area_default_styled") {
    fig.area([0, 1], [0, 1]);
    fig.traces[0].id = entry.trace_id;
    fig.traces[0].style = { opacity: 0.9 };
  } else if (name === "hist_default_styled") {
    fig.histogram([0, 1, 1, 2], { bins: 2, range: [0, 2] });
    fig.traces[0].id = entry.trace_id;
    fig.traces[0].style = { opacity: 0.9 };
  } else if (name === "mesh_default_styled") {
    fig.triangleMesh([0], [0], [1], [0], [0.5], [1]);
    fig.traces[0].id = entry.trace_id;
    fig.traces[0].style = { opacity: 0.9 };
  } else if (name === "segments_default_styled") {
    fig.segments([0, 1], [0, 1], [1, 2], [1, 2]);
    fig.traces[0].id = entry.trace_id;
    fig.traces[0].style = { opacity: 0.9 };
  } else if (name === "ribbon_default_styled") {
    fig.ribbon([0], [1], [0], [1], [0], [1]);
    fig.traces[0].id = entry.trace_id;
    fig.traces[0].style = { opacity: 0.9 };
  } else if (name === "rect_default_styled") {
    fig.box([1, 2, 3, 4, 5]);
    const whiskerIdx = fig.traces.findIndex((t) => t.kind === "box_whisker");
    fig.traces[whiskerIdx].id = entry.trace_id;
    fig.traces[whiskerIdx].style = { opacity: 0.9 };
  } else if (name === "hexbin_default_styled") {
    fig.hexbin([1, 2, 3, 4, 5], [1, 2, 1, 2, 1.5], { gridsize: 4 });
    fig.traces[0].id = entry.trace_id;
    fig.traces[0].style = { opacity: 0.9 };
  } else {
    throw new Error(`unknown case ${name}`);
  }
  const { spec } = fig.buildPayload();
  const trace =
    name === "rect_default_styled"
      ? spec.traces.find((t) => t.kind === "box_whisker")
      : spec.traces[0];
  return { spec, trace };
}

test("default-styled emit cross-host fixture contract", () => {
  assert.equal(fixture.schema, "xyg.default-styled-emit-cross-host/v1");
  assert.equal(fixture.protocol, PROTOCOL_VERSION);
  assert.equal(Number(fixture.abi_version), abiVersion());
  assert.equal(fixture.cases.length, 8);
});

for (const entry of fixture.cases) {
  test(`Node default-styled emit matches fixture for ${entry.name}`, () => {
    const { trace } = buildCase(entry.name);
    assert.equal(trace.id, entry.trace_id);
    assert.equal(trace.kind, entry.kind);
    assert.deepEqual(trace.style, entry.style);
    assert.equal(DEFAULT_PALETTE[trace.id % DEFAULT_PALETTE.length], entry.palette_color);
  });
}
