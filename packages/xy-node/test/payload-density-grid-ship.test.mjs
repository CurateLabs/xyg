import assert from "node:assert/strict";
import test from "node:test";

import { payloadDensityGridShipPlan } from "../src/encode.js";

test("payloadDensityGridShipPlan count-only ships buf then dropped metadata", () => {
  const plan = payloadDensityGridShipPlan();
  assert.equal(plan.nBuffers, 1);
  assert.deepEqual(plan.buffers[0], {
    registryKey: "buf",
    bufferSlot: "count",
    shipMethod: "u8",
  });
  assert.equal(plan.nAttach, 2);
  assert.deepEqual(plan.attach.map((step) => step.attachKind), [
    "channels_dropped",
    "dropped_channels",
  ]);
});

test("payloadDensityGridShipPlan full overlay attach order", () => {
  const plan = payloadDensityGridShipPlan({
    shipMeanColorRgba: true,
    shipWasmSource: true,
    attachSample: true,
    hasTiles: true,
    shipConstantColor: true,
    shipCategoricalEntryColor: true,
  });
  assert.equal(plan.nBuffers, 2);
  assert.equal(plan.buffers[1].registryKey, "rgba");
  assert.deepEqual(plan.attach.map((step) => step.attachKind), [
    "wasm_source",
    "tiles",
    "rgba",
    "channels_dropped",
    "dropped_channels",
    "constant_color",
    "sample",
    "entry_color",
  ]);
});

test("payloadDensityGridShipPlan static raster when sample off", () => {
  const plan = payloadDensityGridShipPlan({
    overlayWireStaticRaster: true,
  });
  assert.deepEqual(plan.attach.map((step) => step.attachKind), [
    "channels_dropped",
    "dropped_channels",
    "overlay_static_raster",
  ]);
});
