import assert from "node:assert/strict";
import test from "node:test";

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
