// Node twin of tests/test_polar_legend_support_cross_host.py (#1041).
//
// A polar figure whose in-Scene legend cannot fit the recut polar viewport
// reports the one stable XYG_SCENE_UNSUPPORTED_POLAR_LEGEND reason from Rust on
// both hosts. The expected reason per case is pinned in
// tests/fixtures/polar_legend_support_cross_host.json.

import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

import { Figure, sceneExportSupportReason } from "../src/index.js";

const fixture = JSON.parse(fs.readFileSync(
  new URL("../../../tests/fixtures/polar_legend_support_cross_host.json", import.meta.url),
  "utf8",
));
const TAU = 6.283185307179586;

function polarBands(side, bands) {
  const figure = new Figure({ width: side, height: side, coords: "polar" });
  figure.setAxisDomain("x", [0, TAU]);
  figure.setAxisDomain("y", [0, 1]);
  for (let index = 0; index < bands; index += 1) {
    figure.bar([0, 1.57, 3.14], [0.5, 0.8, 0.6], { color: "#3987e5", name: `band ${index}`, id: index });
  }
  return figure;
}

for (const { side, bands, reason } of fixture.cases) {
  test(`polar legend support reason at ${side}px with ${bands} bands`, () => {
    assert.equal(sceneExportSupportReason(polarBands(side, bands), { width: side, height: side }), reason);
  });
}
