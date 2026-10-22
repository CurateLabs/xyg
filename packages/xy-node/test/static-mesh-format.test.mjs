import assert from "node:assert/strict";
import test from "node:test";

import { Figure, sceneExportSupportReason, staticDocumentExport } from "../src/index.js";

const LOD = "XYG_SCENE_UNSUPPORTED_PUBLIC_LOD";

function mesh(faces, overlap = false) {
  const zeros = new Float64Array(faces);
  const x1 = Float64Array.from({ length: faces }, (_, i) => overlap ? 1 : Math.cos(i * 2 * Math.PI / faces));
  const y1 = Float64Array.from({ length: faces }, (_, i) => overlap ? 0 : Math.sin(i * 2 * Math.PI / faces));
  const x2 = Float64Array.from({ length: faces }, (_, i) => overlap ? 0 : Math.cos((i + 1) * 2 * Math.PI / faces));
  const y2 = Float64Array.from({ length: faces }, (_, i) => overlap ? 1 : Math.sin((i + 1) * 2 * Math.PI / faces));
  const figure = new Figure({ width: 640, height: 420 });
  figure.setAxisDomain("x", [-1, 1]);
  figure.setAxisDomain("y", [-1, 1]);
  figure.triangleMesh(zeros, zeros, x1, y1, x2, y2);
  return figure;
}

for (const faces of [5_000, 50_000]) {
  test(`vector fan with ${faces} faces bypasses only raster work admission (#1042)`, () => {
    const figure = mesh(faces);
    for (const format of ["svg", "pdf"]) assert.equal(sceneExportSupportReason(figure, { format }), null);
    const svg = new TextDecoder().decode(figure.toSvg());
    assert.ok(!svg.includes("<image"));
    assert.ok((svg.match(/ Z/g) ?? []).length >= faces);
    const pdf = figure.toImage("pdf");
    assert.equal(Buffer.from(pdf.subarray(0, 4)).toString(), "%PDF");
    assert.ok(!Buffer.from(pdf).includes(Buffer.from("/Subtype /Image")));
    for (const format of ["png", "jpeg", "webp"]) {
      assert.equal(sceneExportSupportReason(figure, { format }), LOD);
      assert.throws(() => figure.toImage(format), new RegExp(LOD));
    }
    // Compiled XYST has no output format. Its consumer independently enforces
    // the bound, even when no host support predicate was called.
    assert.throws(() => staticDocumentExport(figure.toStaticDocument(), "png"), new RegExp(LOD));
  });
}

test("overlap and above-ceiling dense fan keep the shared stable LOD reason", () => {
  const overlap = mesh(1_100, true);
  assert.equal(sceneExportSupportReason(overlap, { format: "svg" }), null);
  assert.equal(sceneExportSupportReason(overlap, { format: "png" }), LOD);
  assert.throws(() => overlap.toImage("png"), new RegExp(LOD));
  const dense = mesh(50_001);
  for (const format of ["svg", "pdf", "png"]) {
    assert.equal(sceneExportSupportReason(dense, { format }), LOD);
    assert.throws(() => dense.toImage(format), new RegExp(LOD));
  }
});
