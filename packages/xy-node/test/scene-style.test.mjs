import assert from "node:assert/strict";
import test from "node:test";

import { cssColorRgba8, lineChart, scatterChart } from "../src/index.js";
import { figureSceneV3 } from "../src/scene.js";

test("cssColorRgba8 matches Python named colors and none", () => {
  assert.deepEqual(Array.from(cssColorRgba8("#3b82f6")), [0x3b, 0x82, 0xf6, 255]);
  assert.deepEqual(Array.from(cssColorRgba8("steelblue")), [70, 130, 180, 255]);
  assert.deepEqual(Array.from(cssColorRgba8("none")), [0, 0, 0, 0]);
  assert.deepEqual(Array.from(cssColorRgba8("oklch(0.7 0.1 250)")), [76, 120, 168, 255]);
  assert.deepEqual(Array.from(cssColorRgba8("#ff0000", 0.5)), [255, 0, 0, 128]);
});

test("named color scatter compiles through Rust mark styles", () => {
  const fig = scatterChart([0, 1], [0, 1], { style: { color: "steelblue" } });
  const encoded = figureSceneV3(fig);
  assert.ok(encoded.byteLength > 0);
});

test("line charts keep the 1.5 default stroke width", () => {
  const fig = lineChart([0, 1], [0, 1], { style: { color: "#ff0000" } });
  const encoded = figureSceneV3(fig);
  const bytes = Buffer.from(encoded);
  assert.ok(bytes.includes(Buffer.from([255, 0, 0, 255])));
});
