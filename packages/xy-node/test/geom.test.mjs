import assert from "node:assert/strict";
import test from "node:test";

import {
  curveFlatten,
  monotoneTangents,
  ribbonEdge,
  ribbonPolygon,
  roundedRectPoly,
} from "../src/index.js";

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

test("roundedRectPoly zero radii is four corners", () => {
  const { x, y } = roundedRectPoly(0, 0, 4, 3, 0, 0, true);
  assert.deepEqual([...x], [0, 4, 4, 0]);
  assert.deepEqual([...y], [0, 0, 3, 3]);
});
