import assert from "node:assert/strict";
import test from "node:test";

import { payloadColumnShipPlan } from "../src/encode.js";

test("payloadColumnShipPlan rect registry uses rect_finite gather", () => {
  const plan = payloadColumnShipPlan({
    kind: "rect",
    xAxisScale: "log",
    yAxisScale: "symlog",
  });
  assert.equal(plan.gatherPolicy, "rect_finite");
  assert.equal(plan.nColumns, 4);
  assert.equal(plan.xShipScale, "log");
  assert.equal(plan.yShipScale, "symlog");
  assert.deepEqual(plan.columns.map((col) => col.registryKey), ["x0", "x1", "y0", "y1"]);
  assert.ok(plan.columns.every((col) => col.shipMethod === "offset"));
});

test("payloadColumnShipPlan ribbon ships six columns with y-scaled targets", () => {
  const plan = payloadColumnShipPlan({
    kind: "ribbon",
    xAxisScale: "log",
    yAxisScale: "symlog",
  });
  assert.equal(plan.gatherPolicy, "valid_indices");
  assert.equal(plan.nColumns, 6);
  assert.equal(plan.columns[4].registryKey, "target_y0");
  assert.equal(plan.columns[4].traceSlot, "x");
  assert.equal(plan.columns[4].shipScale, "symlog");
  assert.equal(plan.columns[5].registryKey, "target_y1");
});

test("payloadColumnShipPlan rejects unknown kinds", () => {
  assert.throws(
    () => payloadColumnShipPlan({ kind: "sankey" }),
    /invalid payload-column-ship-plan kind/,
  );
});

test("payloadColumnShipPlan density_sample uses values without gather", () => {
  const plan = payloadColumnShipPlan({
    kind: "density_sample",
    xAxisScale: "linear",
    yAxisScale: "log",
  });
  assert.equal(plan.gatherPolicy, "none");
  assert.equal(plan.nColumns, 2);
  assert.equal(plan.columns[0].shipMethod, "values");
  assert.equal(plan.columns[0].gather, false);
  assert.equal(plan.columns[1].shipScale, "log");
});

test("payloadColumnShipPlan density_wasm_source uses f64 without gather", () => {
  const plan = payloadColumnShipPlan({
    kind: "density_wasm_source",
    xAxisScale: "log",
    yAxisScale: "symlog",
  });
  assert.equal(plan.gatherPolicy, "none");
  assert.equal(plan.nColumns, 2);
  assert.equal(plan.columns[0].shipMethod, "f64");
  assert.equal(plan.columns[0].gather, false);
  assert.equal(plan.columns[1].shipMethod, "f64");
});
