import assert from "node:assert/strict";
import test from "node:test";

import { autoDomain, barChart, scatterChart } from "../src/index.js";

test("autoDomain matches Python Figure._auto_domain", () => {
  assert.deepEqual(autoDomain(null), [0, 1]);
  assert.deepEqual(autoDomain([2, 5]), [2, 5]);
  const constant = autoDomain([10, 10]);
  assert.ok(Math.abs(constant[0] - 9.5) < 1e-12);
  assert.ok(Math.abs(constant[1] - 10.5) < 1e-12);
  assert.deepEqual(autoDomain([0, 0]), [-0.5, 0.5]);
});

test("cartesian scatter uses the Rust 3% margin, not the old 5% pad", () => {
  const fig = scatterChart([-5, 5], [-5, 5]);
  const [lo, hi] = fig._range("x");
  assert.ok(Math.abs(lo - (-5.3)) < 1e-12);
  assert.ok(Math.abs(hi - 5.3) < 1e-12);
  const [ylo, yhi] = fig._range("y");
  assert.ok(Math.abs(ylo - (-5.3)) < 1e-12);
  assert.ok(Math.abs(yhi - 5.3) < 1e-12);
});

test("authored domain short-circuits autorange", () => {
  const fig = scatterChart([0, 1], [0, 1]);
  fig.setAxis("x", { domain: [2, 8] });
  fig.setAxis("y", { domain: [2, 8], reverse: true });
  assert.deepEqual(fig._range("x"), [2, 8]);
  assert.deepEqual(fig._range("y"), [8, 2]);
});

test("positive bars pin the zero baseline", () => {
  const fig = barChart(["A", "B"], [2, 4]);
  const [lo, hi] = fig._range("y");
  assert.equal(lo, 0);
  assert.ok(Math.abs(hi - 4.0 * 1.03) < 1e-12);
});
