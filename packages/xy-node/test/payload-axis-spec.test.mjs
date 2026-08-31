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
