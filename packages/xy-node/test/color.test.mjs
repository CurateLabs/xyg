import assert from "node:assert/strict";
import test from "node:test";

import {
  continuousDomain,
  cssIsFunctional,
  directRgbaAdmit,
  resolveColorChannel,
} from "../src/index.js";
import { factorizeCategories } from "../src/factorize.js";

test("cssIsFunctional admits hash and rgb and rejects named colors", () => {
  assert.equal(cssIsFunctional("#ff0000"), true);
  assert.equal(cssIsFunctional(" rgb(1, 2, 3)"), true);
  assert.equal(cssIsFunctional("red"), false);
});

test("continuousDomain pads equal zero bounds", () => {
  assert.deepEqual(continuousDomain([0, 100]), [0, 100]);
  assert.deepEqual(continuousDomain([0, 0]), [-0.5, 0.5]);
  assert.deepEqual(continuousDomain([]), [0, 1]);
});

test("directRgbaAdmit expands rgb and rejects out of range", () => {
  const packed = directRgbaAdmit([0.1, 0.2, 0.3, 0.4, 0.5, 0.6], 3);
  assert.deepEqual([...packed], [0.1, 0.2, 0.3, 1, 0.4, 0.5, 0.6, 1]);
  assert.throws(() => directRgbaAdmit([0, 0, 1.1], 3), /finite values/);
});

test("factorizeCategories uses native kernel for Uint8Array columns", () => {
  const raw = Uint8Array.from([1, 0, 1]);
  const factored = factorizeCategories(raw);
  assert.equal(factored.mode, "categorical");
  assert.deepEqual(factored.categories, ["0", "1"]);
  assert.deepEqual([...factored.codes], [1, 0, 1]);
  assert.equal(factored.counts[0], 1n);
  assert.equal(factored.counts[1], 2n);
});

test("resolveColorChannel splits css numeric categorical and direct rgba", () => {
  const constant = resolveColorChannel("#3987e5", 3);
  assert.equal(constant.mode, "constant");
  assert.equal(constant.constant, "#3987e5");
  assert.equal(constant.color, undefined);
  const continuous = resolveColorChannel([0, 0], 2);
  assert.equal(continuous.mode, "continuous");
  assert.deepEqual([...continuous.domain], [-0.5, 0.5]);
  const literal = resolveColorChannel(["#ff0000", "#00ff00"], 2);
  assert.equal(literal.mode, "direct_rgba");
  const cats = resolveColorChannel(["b", "a", "b"], 3);
  assert.equal(cats.mode, "categorical");
  assert.deepEqual(cats.categories, ["a", "b"]);
  assert.deepEqual([...cats.codes], [1, 0, 1]);
  const rgb = resolveColorChannel(
    [
      [0.1, 0.2, 0.3],
      [0.4, 0.5, 0.6],
    ],
    2,
  );
  assert.equal(rgb.mode, "direct_rgba");
  assert.equal(rgb.rgba.length, 8);
  assert.equal(rgb.rgba[3], 255);
});
