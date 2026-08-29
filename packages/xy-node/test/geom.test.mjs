import assert from "node:assert/strict";
import test from "node:test";

import {
  F32_SAFE_MAG,
  curveFlatten,
  f32SafeScale,
  geometryOffset,
  hexbinRing,
  markerPathScale,
  pinsOffsetToZero,
  monotoneTangents,
  ribbonEdge,
  ribbonPolygon,
  roundedRectPoly,
  stepArrays,
} from "../src/index.js";

test("geometryOffset pins log family and nonfinite to zero", () => {
  assert.equal(pinsOffsetToZero("log"), true);
  assert.equal(pinsOffsetToZero("symlog"), true);
  assert.equal(pinsOffsetToZero("linear"), false);
  assert.equal(pinsOffsetToZero("Log"), false);
  assert.equal(pinsOffsetToZero(""), false);
  assert.equal(pinsOffsetToZero(null), false);
  assert.equal(geometryOffset("log", 10, 20), 0);
  assert.equal(geometryOffset("symlog", 10, 20), 0);
  assert.equal(geometryOffset("linear", 10, 20), 15);
  assert.equal(geometryOffset("linear", Number.NaN, 20), 0);
  assert.equal(f32SafeScale(0, -1, 1), 1);
  const huge = F32_SAFE_MAG * 10;
  assert.ok(Math.abs(f32SafeScale(0, -huge, huge) - 0.1) < 1e-12);
});

test("hexbinRing scales the canonical pointy-top fractions", () => {
  const { x, y } = hexbinRing(6, 12);
  assert.equal(x.length, 6);
  assert.equal(y.length, 6);
  assert.equal(x[0], 0);
  assert.equal(y[0], -4);
  assert.equal(x[1], 3);
  assert.equal(y[1], -2);
  assert.throws(() => hexbinRing(Number.NaN, 1), /invalid hexbin-ring request/);
});

test("ribbonEdge midpoint matches Python golden", () => {
  const { x, y } = ribbonEdge(0, 10, 1, 3, 8);
  assert.equal(x.length, 9);
  assert.equal(x[0], 0);
  assert.equal(y[0], 1);
  assert.equal(x[4], 5);
  assert.equal(y[4], 2);
  assert.equal(x[8], 10);
  assert.equal(y[8], 3);
});

test("ribbonPolygon is upper then reversed lower", () => {
  const { x, y } = ribbonPolygon(0, 10, 0, 1, 2, 4, 4);
  assert.equal(x.length, 10);
  assert.equal(y[0], 1);
  assert.equal(y[4], 4);
  assert.equal(y[5], 2);
  assert.equal(y[9], 0);
});

test("monotoneTangents zero interiors on sign change", () => {
  const m = monotoneTangents([0, 1, 2, 3, 4], [0, 1, 0.5, 2, 1.5]);
  assert.deepEqual([...m], [1, 0, 0, 0, -0.5]);
});

test("curveFlatten keeps knots and 15 interiors per span", () => {
  const { x, y } = curveFlatten([0, 1, 2, 3, 4], [0, 1, 0.5, 2, 1.5]);
  assert.equal(x.length, 65);
  assert.equal(x[0], 0);
  assert.equal(y[16], 1);
  assert.equal(x[64], 4);
  assert.equal(y[64], 1.5);
});

test("stepArrays expands pre mid and post vertices", () => {
  const pre = stepArrays([0, 1, 2], [10, 20, 30], "pre");
  assert.deepEqual([...pre.x], [0, 0, 1, 1, 2]);
  assert.deepEqual([...pre.y], [10, 20, 20, 30, 30]);
  const mid = stepArrays([0, 1, 2], [10, 20, 30], "mid");
  assert.deepEqual([...mid.x], [0, 0.5, 0.5, 1, 1.5, 1.5, 2]);
  assert.deepEqual([...mid.y], [10, 10, 20, 20, 20, 30, 30]);
  const post = stepArrays([0, 1, 2], [10, 20, 30], "post");
  assert.deepEqual([...post.x], [0, 1, 1, 2, 2]);
  assert.deepEqual([...post.y], [10, 10, 20, 20, 30]);
  const identity = stepArrays([7], [9], "pre");
  assert.deepEqual([...identity.x], [7]);
  assert.deepEqual([...identity.y], [9]);
  assert.throws(() => stepArrays([0, 1], [10], "post"), /equal length/);
});

test("markerPathScale flips y and matches host vertices", () => {
  const scaled = markerPathScale(10, 20, 8, [0, 0.5, 0, -0.5], [0.5, 0, -0.5, 0]);
  assert.deepEqual([...scaled.x], [10, 14, 10, 6]);
  assert.deepEqual([...scaled.y], [16, 20, 24, 20]);
  const empty = markerPathScale(10, 20, 8, [], []);
  assert.deepEqual([...empty.x], []);
  assert.deepEqual([...empty.y], []);
  assert.throws(() => markerPathScale(10, 20, 8, [0, 1], [0]), /equal length/);
});

test("roundedRectPoly zero radii is four corners", () => {
  const { x, y } = roundedRectPoly(0, 0, 4, 3, 0, 0, true);
  assert.deepEqual([...x], [0, 4, 4, 0]);
  assert.deepEqual([...y], [0, 0, 3, 3]);
});
