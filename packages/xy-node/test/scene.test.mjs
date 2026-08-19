import assert from "node:assert/strict";
import test from "node:test";

import { axisTicks, scaleMap, scatterSceneSvg, sceneVersion } from "../src/index.js";

test("Node consumes canonical linear, log, and symlog scale records", () => {
  assert.deepEqual(Array.from(scaleMap({ values: [0, 5, 10], domain: [0, 10], range: [20, 120] })), [20, 70, 120]);
  assert.deepEqual(Array.from(scaleMap({ values: [0.1, 1, 100], kind: "log", domain: [0.1, 100], range: [0, 300] })), [0, 100, 300]);
  const coordinates = scaleMap({ values: [-4, 0, 4], kind: "symlog", operation: "coord", domain: [-10, 10], constant: 2 });
  const roundTrip = scaleMap({ values: coordinates, kind: "symlog", operation: "value", domain: [-10, 10], constant: 2 });
  assert.ok(roundTrip.every((value, index) => Math.abs(value - [-4, 0, 4][index]) < 1e-12));
  assert.ok(Number.isNaN(scaleMap({ values: [0], kind: "log", operation: "coord", domain: [0.1, 10], nonpositive: "mask" })[0]));
});

test("Node consumes Rust-owned canonical axis ticks", () => {
  assert.deepEqual(axisTicks({ kind: "linear", lo: -0.9, hi: 5.1, target: 6 }), {
    ticks: [0, 1, 2, 3, 4, 5], labeled: [0, 1, 2, 3, 4, 5], step: 1,
  });
  assert.deepEqual(axisTicks({ kind: "log", lo: 0.1, hi: 100, target: 6 }).labeled, [0.1, 1, 10, 100]);
});

test("Node consumes the versioned Rust scatter scene", () => {
  assert.equal(sceneVersion(), 1);
  assert.equal(
    scatterSceneSvg({
      x: [10, 20],
      y: [11, 21],
      diameter: [8, 10],
      fillRgba: [37, 99, 235, 255, 239, 68, 68, 128],
      strokeRgba: [0, 0, 0, 255, 17, 24, 39, 64],
      strokeWidth: [2, 0],
      symbols: [0, 14],
    }),
    '<g><circle cx="10" cy="11" r="3" fill="rgb(37,99,235)" stroke="rgb(0,0,0)" stroke-width="2"/><path d="M 15.5 21 H 24.5 M 20 16.5 V 25.5" fill="none" stroke="rgb(17,24,39)" stroke-opacity="0.25" stroke-width="1"/></g>',
  );
});

test("Node rejects malformed scene array lengths before the ABI call", () => {
  assert.throws(
    () => scatterSceneSvg({
      x: [1], y: [], diameter: [4], fillRgba: [0, 0, 0, 255],
      strokeRgba: [0, 0, 0, 0], strokeWidth: [0], symbols: [0],
    }),
    /y must have length 1/,
  );
});

test("Node maps Rust scene validation failures to a stable host error", () => {
  assert.throws(
    () => scatterSceneSvg({
      x: [Number.NaN], y: [1], diameter: [4], fillRgba: [0, 0, 0, 255],
      strokeRgba: [0, 0, 0, 0], strokeWidth: [0], symbols: [0],
    }),
    /invalid canonical scatter scene/,
  );
});
