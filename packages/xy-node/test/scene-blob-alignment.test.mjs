import assert from "node:assert/strict";
import test from "node:test";

import { Figure } from "../src/index.js";
import { sceneXyTcTraceObservationsMaterialize } from "../src/sceneBulkNative.js";

test("native trace f64 tails support every preceding UTF-8 byte alignment", () => {
  for (let length = 0; length < 8; length += 1) {
    const materialized = sceneXyTcTraceObservationsMaterialize({
      kind: "line", name: "x".repeat(length), has_name: length > 0,
      dash_is_array: true, dash_values: [5, 3],
    });
    assert.deepEqual(materialized.dashPattern, [5, 3], `name byte length ${length}`);
  }
});

test("public dashed line exports retain native dash facts with UTF-8 names", () => {
  for (const name of ["", "x", "Series", "é", "λ line"]) {
    const figure = new Figure({ width: 240, height: 180 });
    figure.line([0, 1, 2], [1, 3, 2], { name, style: { opacity: 0.75, dash: [5, 3] } });
    const svg = figure.toSceneSvg();
    assert.match(svg, /stroke-dasharray="5[ ,]3"/);
    assert.match(svg, /stroke-opacity="0\.75"/);
  }
});
