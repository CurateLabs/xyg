import assert from "node:assert/strict";
import test from "node:test";

import { Figure } from "../src/index.js";

test("Figure static aliases use the shared XYST product boundary", () => {
  const figure = new Figure({ width: 240, height: 180, showLegend: false });
  figure.line([0, 1, 2], [1, 3, 2], { color: "#2563eb", width: 2 });

  const document = figure.toStaticDocument({ background: "white", optimizePng: true });
  assert.equal(new TextDecoder().decode(document.subarray(0, 4)), "XYST");

  const svg = figure.toSvg();
  assert.equal(new TextDecoder().decode(svg.subarray(0, 4)), "<svg");
  assert.deepEqual(Array.from(figure.toPng().subarray(0, 8)), [137, 80, 78, 71, 13, 10, 26, 10]);
  assert.equal(new TextDecoder().decode(figure.toPdf().subarray(0, 5)), "%PDF-");
  assert.deepEqual(Array.from(figure.toJpeg().subarray(0, 3)), [255, 216, 255]);
  assert.equal(new TextDecoder().decode(figure.toWebp().subarray(0, 4)), "RIFF");
});

test("Figure toImage preserves shared format validation", () => {
  const figure = new Figure({ width: 120, height: 90, showLegend: false });
  figure.line([0, 1], [0, 1]);
  assert.throws(() => figure.toImage("gif"), /StaticDocument format/);
});
