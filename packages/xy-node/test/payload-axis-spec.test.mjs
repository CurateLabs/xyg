import assert from "node:assert/strict";
import test from "node:test";

import { figure } from "../src/index.js";
import { payloadAxisSpecAttachPlan } from "../src/encode.js";

test("payloadAxisSpecAttachPlan cartesian core without polar fields", () => {
  const plan = payloadAxisSpecAttachPlan({ coordsCartesian: true, axisIsX: true });
  assert.equal(plan.attachId, true);
  assert.equal(plan.attachKind, true);
  assert.equal(plan.attachSide, true);
  assert.equal(plan.attachLabel, true);
  assert.equal(plan.attachRange, true);
  assert.equal(plan.attachScale, true);
  assert.equal(plan.attachTicks, true);
  assert.equal(plan.attachDomain, true);
  assert.equal(plan.attachFormat, true);
  assert.equal(plan.attachBounds, true);
  assert.equal(plan.attachThetaUnit, false);
  assert.equal(plan.attachHole, false);
});

test("payloadAxisSpecAttachPlan polar theta on x and radial on y", () => {
  const x = payloadAxisSpecAttachPlan({ coordsCartesian: false, axisIsX: true });
  assert.equal(x.attachThetaUnit, true);
  assert.equal(x.attachThetaZero, true);
  assert.equal(x.attachSector, true);
  assert.equal(x.attachHole, false);
  const y = payloadAxisSpecAttachPlan({ coordsCartesian: false, axisIsX: false });
  assert.equal(y.attachThetaUnit, false);
  assert.equal(y.attachHole, true);
  assert.equal(y.attachROrigin, true);
});

function axisMeta(spec) {
  return {
    id: spec.id,
    kind: spec.kind,
    side: spec.side,
    label: spec.label,
  };
}

test("buildPayload cartesian axis meta matches Python _axis_spec core fields", () => {
  const fig = figure({ width: 240, height: 160 });
  fig.scatter([0, 1, 2], [0, 1, 0.5]);
  fig.traces[0].id = 7;
  const { spec } = fig.buildPayload();
  assert.deepEqual(axisMeta(spec.x_axis), {
    id: "x",
    kind: "linear",
    side: "bottom",
    label: null,
  });
  assert.deepEqual(axisMeta(spec.y_axis), {
    id: "y",
    kind: "linear",
    side: "left",
    label: null,
  });
});

test("buildPayload polar axis meta matches Python _axis_spec core fields", () => {
  const fig = figure({ coords: "polar", width: 240, height: 160 });
  fig.scatter([0, Math.PI / 2], [0, 1]);
  const { spec } = fig.buildPayload();
  assert.equal(spec.x_axis.id, "x");
  assert.equal(spec.x_axis.kind, "linear");
  assert.equal(spec.x_axis.side, "bottom");
  assert.equal(spec.x_axis.label, null);
  assert.equal(spec.x_axis.scale, undefined);
  assert.equal(spec.y_axis.id, "y");
  assert.equal(spec.y_axis.kind, "linear");
  assert.equal(spec.y_axis.side, "left");
  assert.equal(spec.y_axis.label, null);
  assert.equal(spec.y_axis.scale, undefined);
});

test("buildPayload omits linear axis scale like Python _axis_spec", () => {
  const fig = figure({ width: 240, height: 160 });
  fig.scatter([0, 1, 2], [0, 1, 0.5]);
  const { spec } = fig.buildPayload();
  assert.equal(spec.x_axis.scale, undefined);
  assert.equal(spec.y_axis.scale, undefined);
});

test("buildPayload ships log axis scale like Python _axis_spec", () => {
  const fig = figure({ width: 240, height: 160 });
  fig.setAxis("x", { type: "log" });
  fig.scatter([1, 10], [1, 10]);
  const { spec } = fig.buildPayload();
  assert.equal(spec.x_axis.scale, "log");
  assert.equal(spec.y_axis.scale, undefined);
});

test("buildPayload ships cartesian axis tick_values like Python _axis_spec", () => {
  const fig = figure({ width: 240, height: 160 });
  fig.scatter([0, 1], [0, 1]);
  fig.setAxis("x", { tick_values: [0, 0.5, 1], domain: [0, 1], format: ".2f" });
  const { spec } = fig.buildPayload();
  assert.deepEqual(spec.x_axis.tick_values, [0, 0.5, 1]);
  assert.deepEqual(spec.x_axis.domain, [0, 1]);
  assert.equal(spec.x_axis.format, ".2f");
});

test("buildPayload ships cartesian axis minor_tick_values like Python _axis_spec", () => {
  const fig = figure({ width: 240, height: 160 });
  fig.scatter([0, 1], [0, 1]);
  fig.setAxis("x", { minor_tick_values: [0.25, 0.75] });
  const { spec } = fig.buildPayload();
  assert.deepEqual(spec.x_axis.minor_tick_values, [0.25, 0.75]);
  assert.equal(spec.y_axis.minor_tick_values, undefined);
});

test("buildPayload ships cartesian axis tick_labels like Python _axis_spec", () => {
  const fig = figure({ width: 240, height: 160 });
  fig.scatter([0, 1], [0, 1]);
  fig.setAxis("x", { tick_values: [0, 1], tick_labels: ["a", "b"] });
  const { spec } = fig.buildPayload();
  assert.deepEqual(spec.x_axis.tick_labels, ["a", "b"]);
  assert.equal(spec.y_axis.tick_labels, undefined);
});

test("buildPayload ships cartesian axis tick_count like Python _axis_spec", () => {
  const fig = figure({ width: 240, height: 160 });
  fig.scatter([0, 1], [0, 1]);
  fig.setAxis("x", { tick_count: 4 });
  const { spec } = fig.buildPayload();
  assert.equal(spec.x_axis.tick_count, 4);
  assert.equal(spec.y_axis.tick_count, undefined);
});

test("buildPayload ships cartesian axis reverse like Python _axis_spec", () => {
  const fig = figure({ width: 240, height: 160 });
  fig.scatter([0, 1], [0, 1]);
  fig.setAxis("x", { reverse: true });
  const { spec } = fig.buildPayload();
  assert.equal(spec.x_axis.reverse, true);
  assert.equal(spec.y_axis.reverse, undefined);
});

test("buildPayload ships cartesian axis domain like Python _axis_spec", () => {
  const fig = figure({ width: 240, height: 160 });
  fig.scatter([1, 2], [1, 2]);
  fig.setAxis("x", { domain: [0, 3] });
  const { spec } = fig.buildPayload();
  assert.deepEqual(spec.x_axis.domain, [0, 3]);
  assert.equal(spec.y_axis.domain, undefined);
});

test("buildPayload ships cartesian axis format like Python _axis_spec", () => {
  const fig = figure({ width: 240, height: 160 });
  fig.scatter([0, 1], [0, 1]);
  fig.setAxis("x", { format: ".2f" });
  const { spec } = fig.buildPayload();
  assert.equal(spec.x_axis.format, ".2f");
  assert.equal(spec.y_axis.format, undefined);
});

test("buildPayload ships cartesian axis bounds like Python _axis_spec", () => {
  const fig = figure({ width: 240, height: 160 });
  fig.scatter([0, 1], [0, 1]);
  fig.setAxis("x", { bounds: [0, 2] });
  const { spec } = fig.buildPayload();
  assert.deepEqual(spec.x_axis.bounds, [0, 2]);
  assert.equal(spec.y_axis.bounds, undefined);
});

test("buildPayload ships cartesian axis tick_sides like Python _axis_spec", () => {
  const fig = figure({ width: 240, height: 160 });
  fig.scatter([0, 1], [0, 1]);
  fig.setAxis("x", { tick_sides: ["bottom"] });
  const { spec } = fig.buildPayload();
  assert.deepEqual(spec.x_axis.tick_sides, ["bottom"]);
  assert.equal(spec.y_axis.tick_sides, undefined);
});

test("buildPayload ships polar axis tick_sides like Python _axis_spec", () => {
  const fig = figure({ coords: "polar", width: 240, height: 160 });
  fig.setAxis("x", { tick_sides: ["bottom"] });
  fig.scatter([0, 1], [1, 2]);
  const { spec } = fig.buildPayload();
  assert.deepEqual(spec.x_axis.tick_sides, ["bottom"]);
});

test("buildPayload ships cartesian axis tick_label_sides like Python _axis_spec", () => {
  const fig = figure({ width: 240, height: 160 });
  fig.scatter([0, 1], [0, 1]);
  fig.setAxis("x", { tick_label_sides: ["bottom"] });
  const { spec } = fig.buildPayload();
  assert.deepEqual(spec.x_axis.tick_label_sides, ["bottom"]);
  assert.equal(spec.y_axis.tick_label_sides, undefined);
});

test("buildPayload ships polar axis tick_label_sides like Python _axis_spec", () => {
  const fig = figure({ coords: "polar", width: 240, height: 160 });
  fig.setAxis("x", { tick_label_sides: ["bottom"] });
  fig.scatter([0, 1], [1, 2]);
  const { spec } = fig.buildPayload();
  assert.deepEqual(spec.x_axis.tick_label_sides, ["bottom"]);
});
