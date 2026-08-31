import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

import { PROTOCOL_VERSION, abiVersion, figure } from "../src/index.js";

const fixture = JSON.parse(
  fs.readFileSync(
    new URL("../../../tests/fixtures/animation_emit_cross_host.json", import.meta.url),
    "utf8",
  ),
);

const ANIM = { duration: 250, easing: "linear" };

function buildCase(name) {
  const entry = fixture.cases.find((c) => c.name === name);
  if (entry == null) throw new Error(`unknown case ${name}`);
  const fig = figure({ width: 240, height: 160 });
  if (name === "scatter_animation") {
    fig.scatter([1, 2, 3], [1, 2, 3]);
    fig.traces[0].id = entry.trace_id;
    fig.traces[0].animation = { ...ANIM };
  } else if (name === "line_animation") {
    fig.line([0, 1, 2], [0, 1, 2]);
    fig.traces[0].id = entry.trace_id;
    fig.traces[0].animation = { ...ANIM };
  } else if (name === "scatter_no_animation") {
    fig.scatter([1, 2], [1, 2]);
    fig.traces[0].id = entry.trace_id;
  } else if (name === "line_no_animation") {
    fig.line([0, 1], [0, 1]);
    fig.traces[0].id = entry.trace_id;
  } else if (name === "scatter_log_animation") {
    fig.setAxis("x", { type: "log" });
    fig.scatter([1, 10, 100], [1, 10, 100]);
    fig.traces[0].id = entry.trace_id;
    fig.traces[0].animation = { ...ANIM };
  } else if (name === "line_decimated_animation") {
    const n = 10001;
    const xs = Array.from({ length: n }, (_, i) => i);
    const ys = Array.from({ length: n }, (_, i) => i % 7);
    fig.line(xs, ys);
    fig.traces[0].id = entry.trace_id;
    fig.traces[0].animation = { ...ANIM };
  } else if (name === "area_animation") {
    fig.area([0, 1, 2], [0, 1, 2]);
    fig.traces[0].id = entry.trace_id;
    fig.traces[0].animation = { ...ANIM };
  } else if (name === "area_no_animation") {
    fig.area([0, 1], [0, 1]);
    fig.traces[0].id = entry.trace_id;
  } else if (name === "area_decimated_animation") {
    const n = 10001;
    const xs = Array.from({ length: n }, (_, i) => i);
    const ys = Array.from({ length: n }, (_, i) => i % 7);
    fig.area(xs, ys);
    fig.traces[0].id = entry.trace_id;
    fig.traces[0].animation = { ...ANIM };
  } else if (name === "density_animation") {
    fig.scatter([1, 2, 3], [1, 2, 3], { forceDensity: true });
    fig.traces[0].id = entry.trace_id;
    fig.traces[0].animation = { ...ANIM };
  } else if (name === "density_no_animation") {
    fig.scatter([1, 2], [1, 2], { forceDensity: true });
    fig.traces[0].id = entry.trace_id;
  } else {
    throw new Error(`unknown case ${name}`);
  }
  return { fig, entry };
}

test("animation emit cross-host fixture contract", () => {
  assert.equal(fixture.schema, "xyg.animation-emit-cross-host/v1");
  assert.equal(fixture.protocol, PROTOCOL_VERSION);
  assert.equal(Number(fixture.abi_version), abiVersion());
  assert.equal(fixture.cases.length, 11);
});

for (const entry of fixture.cases) {
  test(`Node animation emit matches fixture for ${entry.name}`, () => {
    const { fig } = buildCase(entry.name);
    const { spec } = fig.buildPayload();
    const trace = spec.traces[0];
    assert.equal(trace.id, entry.trace_id);
    assert.equal(trace.kind, entry.kind);
    assert.equal(trace.n_points, entry.n_points);
    assert.equal(trace.tier, entry.tier);
    if (entry.animation == null) {
      assert.equal(trace.animation, undefined);
    } else {
      assert.deepEqual(trace.animation, entry.animation);
    }
  });
}
