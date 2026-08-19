import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

import { axisTicks, scaleMap, scatterSceneSvg, sceneBatchEncode, sceneVersion } from "../src/index.js";

const sceneFixture = JSON.parse(fs.readFileSync(new URL("../../../tests/fixtures/scene_v2.json", import.meta.url), "utf8"));

test("Node Scene v2 matches shared scatter, line, bar, and axis bytes", () => {
  const encoded = sceneBatchEncode({
    viewport: sceneFixture.viewport, margins: sceneFixture.margins,
    xAxis: { id: sceneFixture.x_axis[0], kind: "linear", domain: sceneFixture.x_axis.slice(2, 4), constant: sceneFixture.x_axis[4], nonpositive: "clip" },
    yAxis: { id: sceneFixture.y_axis[0], kind: "linear", domain: sceneFixture.y_axis.slice(2, 4), constant: sceneFixture.y_axis[4], nonpositive: "clip" },
    kinds: sceneFixture.kinds, stableIds: sceneFixture.stable_ids, styleRefs: sceneFixture.style_refs,
    styles: sceneFixture.styles.map((style) => ({ fillRgba: style.fill_rgba, strokeRgba: style.stroke_rgba, strokeWidth: style.stroke_width })),
    diameter: sceneFixture.diameter, symbols: sceneFixture.symbols,
    x0: sceneFixture.x0, y0: sceneFixture.y0, x1: sceneFixture.x1, y1: sceneFixture.y1,
  });
  assert.equal(Buffer.from(encoded).toString("hex"), sceneFixture.expected_hex);
  const records = 160 + sceneFixture.styles.length * 16;
  assert.equal(encoded[records + 1], 1); // center outside, full marker overlaps
  assert.equal(encoded[records + 2], 2); // diamond
  assert.equal(new DataView(encoded.buffer, encoded.byteOffset).getFloat64(records + 48, true), 16);
});

test("Node Scene v2 rejects malformed batches", () => {
  const base = {
    viewport: [100, 80], margins: [10, 10, 10, 10],
    xAxis: { id: 1, domain: [0, 1] }, yAxis: { id: 2, domain: [0, 1] },
    kinds: [0], stableIds: [1], styleRefs: [0], x0: [0.5], y0: [0.5], x1: [0.5], y1: [0.5],
    styles: [{ fillRgba: [0, 0, 0, 255], strokeRgba: [0, 0, 0, 255], strokeWidth: 1 }],
    diameter: [8], symbols: [0],
  };
  assert.throws(() => sceneBatchEncode({ ...base, stableIds: [] }), /stableIds must have length 1/);
  assert.throws(() => sceneBatchEncode({ ...base, kinds: [9] }), /invalid canonical scene batch/);
  assert.throws(() => sceneBatchEncode({ ...base, styleRefs: [1] }), /invalid canonical scene batch/);
  assert.throws(() => sceneBatchEncode({ ...base, margins: [60, 40, 10, 10] }), /invalid canonical scene batch/);
});

test("Node consumes canonical linear, log, and symlog scale records", () => {
  assert.deepEqual(Array.from(scaleMap({ values: [0, 5, 10], domain: [0, 10], range: [20, 120] })), [20, 70, 120]);
  assert.deepEqual(Array.from(scaleMap({ values: [0.1, 1, 100], kind: "log", domain: [0.1, 100], range: [0, 300] })), [0, 100, 300]);
  const coordinates = scaleMap({ values: [-4, 0, 4], kind: "symlog", operation: "coord", domain: [-10, 10], constant: 2 });
  const roundTrip = scaleMap({ values: coordinates, kind: "symlog", operation: "value", domain: [-10, 10], constant: 2 });
  assert.ok(roundTrip.every((value, index) => Math.abs(value - [-4, 0, 4][index]) < 1e-12));
  assert.ok(Number.isNaN(scaleMap({ values: [0], kind: "log", operation: "coord", domain: [0.1, 10], nonpositive: "mask" })[0]));
});

test("Node rejects malformed canonical scale options before the ABI call", () => {
  assert.throws(
    () => scaleMap({ values: [1], kind: "log", domain: [0.1, 10], nonpositive: "drop" }),
    /nonpositive must be clip or mask/,
  );
});

test("Node consumes Rust-owned canonical axis ticks", () => {
  assert.deepEqual(axisTicks({ kind: "linear", lo: -0.9, hi: 5.1, target: 6 }), {
    ticks: [0, 1, 2, 3, 4, 5], labeled: [0, 1, 2, 3, 4, 5], step: 1,
  });
  assert.deepEqual(axisTicks({ kind: "log", lo: 0.1, hi: 100, target: 6 }).labeled, [0.1, 1, 10, 100]);
});

test("Node consumes the versioned Rust scatter scene", () => {
  assert.equal(sceneVersion(), 2);
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
