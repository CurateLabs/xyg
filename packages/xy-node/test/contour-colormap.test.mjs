// Node contour colormap authoring (#1025): admission errors mirror Python.

import assert from "node:assert/strict";
import test from "node:test";

import { Figure, resolveColormap, sceneExportSupportReason } from "../src/index.js";

const Z = [[0, 1, 0], [1, 2, 1], [0, 1, 0]];
const LEVELS = [0.25, 1.0, 1.75];

function contour(opts) {
  return new Figure({ width: 320, height: 240 }).contour(Z, { levels: LEVELS, ...opts });
}

test("default contour carries a continuous viridis channel over the levels", () => {
  const trace = contour({}).traces[0];
  assert.equal(trace.color_ch.mode, "continuous");
  assert.equal(trace.color_ch.colormap, "viridis");
  assert.equal(trace.style.color, null);
});

test("a string color is one validated constant stroke", () => {
  const trace = contour({ color: "#ef4444" }).traces[0];
  assert.equal(trace.color_ch, undefined);
  assert.equal(trace.style.color, "#ef4444");
  assert.throws(() => contour({ color: "notacolor" }), /contour color 'notacolor' is not a recognized CSS color name/);
});

test("contour input errors", () => {
  assert.throws(() => contour({ colormap: "nope" }), /unknown colormap "nope"/);
  assert.throws(() => contour({ colormap: 5 }), /colormap must be a built-in name/);
  assert.throws(() => contour({ color: [[1, 0, 0], [0, 1, 0]] }), /length|!= n/);
  assert.throws(() => contour({ color: ["red", "green", "blue"] }), /direct RGB\/RGBA rows/);
  assert.throws(() => contour({ color: [[2, 0, 0], [0, 1, 0], [0, 0, 1]] }), RangeError);
  assert.throws(() => contour({ style: { color: [1, 2, 3] } }), /contour style color must be a CSS color string/);
});

test("colormap stops reject wrapping values", () => {
  assert.throws(() => resolveColormap([[256, 0, 0], [0, 0, 1]]), /integers in 0\.\.255/);
  assert.throws(() => resolveColormap([[1.5, 0, 0], [0, 0, 1]]), /integers in 0\.\.255/);
  assert.throws(() => resolveColormap([[-1, 0, 0], [0, 0, 1]]), /integers in 0\.\.255/);
  assert.deepEqual(resolveColormap([[255, 0, 0], [0, 0, 255]]), [[255, 0, 0], [0, 0, 255]]);
});

test("custom colormaps stay live but fail closed in Scene export", () => {
  const fig = contour({ colormap: ["#ff0000", "#0000ff"] });
  fig.setAxisDomain("x", [0, 3]);
  fig.setAxisDomain("y", [0, 3]);
  assert.equal(sceneExportSupportReason(fig), "XYG_SCENE_UNSUPPORTED_CONTOUR_CUSTOM_COLORMAP");
  const named = contour({ colormap: "magma" });
  assert.equal(sceneExportSupportReason(named), null);
});
