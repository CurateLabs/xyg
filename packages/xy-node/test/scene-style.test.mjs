import assert from "node:assert/strict";
import test from "node:test";

import { cssColorRgba8, lineChart, scatterChart } from "../src/index.js";
import { figureSceneV3 } from "../src/scene.js";
import { xySceneResolveChromeStyle } from "../src/native.js";
import { u8Ptr } from "../src/encode.js";

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

function resolveChrome(envelope) {
  const out = new Uint8Array(200);
  const code = xySceneResolveChromeStyle(
    u8Ptr(envelope),
    BigInt(envelope.length),
    u8Ptr(out),
    BigInt(out.length),
  );
  assert.equal(code, 200);
  return out;
}

function chromeAxis(gridOpacity = 1) {
  const prefix = new Uint8Array(84);
  const view = new DataView(prefix.buffer);
  prefix[1] = 1;
  prefix[2] = 1;
  view.setFloat32(8, gridOpacity, true);
  view.setFloat32(12, 1, true);
  [1, 1, 1, 4, 1, 1, 0].forEach((value, index) => view.setFloat64(16 + index * 8, value, true));
  return prefix;
}

test("empty XYCH envelope is the Scene chrome default", () => {
  const envelope = new Uint8Array(16);
  envelope.set(new TextEncoder().encode("XYCH"));
  new DataView(envelope.buffer).setUint32(4, 1, true);
  const chrome = resolveChrome(envelope);
  assert.deepEqual(Array.from(chrome.subarray(8, 12)), [32, 32, 32, 217]);
  assert.equal(new DataView(chrome.buffer).getFloat64(16, true), 12);
  assert.deepEqual(Array.from(chrome.subarray(36, 40)), [32, 32, 32, 36]);
});

test("grid_opacity scales the default grid color without authored grid_color", () => {
  const x = chromeAxis(0);
  const y = chromeAxis(1);
  const envelope = new Uint8Array(16 + x.length + y.length);
  const view = new DataView(envelope.buffer);
  envelope.set(new TextEncoder().encode("XYCH"));
  view.setUint32(4, 1, true);
  view.setUint32(8, 2 << 8, true);
  envelope.set(x, 16);
  envelope.set(y, 16 + x.length);
  const chrome = resolveChrome(envelope);
  assert.deepEqual(Array.from(chrome.subarray(24 + 12, 24 + 16)), [32, 32, 32, 0]);
  assert.deepEqual(Array.from(chrome.subarray(112 + 12, 112 + 16)), [32, 32, 32, 36]);
});
