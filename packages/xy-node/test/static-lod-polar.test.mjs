// Node twin of tests/test_static_lod_polar_cross_host.py (#1006).
//
// Both hosts build the same figures and export native SVG/PNG through the one
// Rust static route; the digests pinned in
// tests/fixtures/static_lod_polar_cross_host.json prove byte identity for a
// 1,000,000-point line on the browser's M4 tier, a 100,000-point scatter on the
// direct tier, and polar bar wedges written as exact SVG arcs.

import assert from "node:assert/strict";
import crypto from "node:crypto";
import fs from "node:fs";
import test from "node:test";

import { Figure, sceneExportSupportReason } from "../src/index.js";

const fixture = JSON.parse(fs.readFileSync(
  new URL("../../../tests/fixtures/static_lod_polar_cross_host.json", import.meta.url),
  "utf8",
));
const LINE_N = 1_000_000;
const SCATTER_N = 100_000;
const TAU = 6.283185307179586;

function lineFigure() {
  const x = Float64Array.from({ length: LINE_N }, (_, i) => i * 0.25);
  const y = Float64Array.from({ length: LINE_N }, (_, i) => ((i * 7919) % 1009) / 10 - (i % 97));
  const figure = new Figure({ width: 720, height: 420 });
  figure.line(x, y, { color: "#ef4444", width: 1 });
  figure.traces[0].id = 0;
  return figure;
}

function scatterFigure() {
  const x = Float64Array.from({ length: SCATTER_N }, (_, i) => ((i * 7919) % 1009) / 1009 * 8 - 2);
  const y = Float64Array.from({ length: SCATTER_N }, (_, i) => ((i * 104729) % 997) / 997 * 8 - 2);
  const figure = new Figure({ width: 720, height: 420 });
  figure.setAxisDomain("x", [-2, 6]);
  figure.setAxisDomain("y", [-2, 6]);
  figure.scatter(x, y, { style: { color: "#3987e5", size: 3 } });
  figure.traces[0].id = 0;
  return figure;
}

function polarBarFigure() {
  const figure = new Figure({ width: 320, height: 240, coords: "polar" });
  figure.setAxisDomain("x", [0, TAU]);
  figure.setAxisDomain("y", [0, 1]);
  figure.bar([0, 1.57, 3.14], [0.5, 0.8, 0.6], { color: "#3987e5", name: "pbar", id: 0 });
  return figure;
}

const BUILDERS = {
  line_1m_m4: lineFigure,
  polar_bar_arcs: polarBarFigure,
  scatter_100k_direct: scatterFigure,
};

const sha256 = (bytes) => crypto.createHash("sha256").update(bytes).digest("hex");

test("Node static LOD and polar-arc exports match the Python cross-host digests", () => {
  assert.equal(fixture.schema, "xyg.static-lod-polar-cross-host/v1");
  assert.deepEqual(Object.keys(BUILDERS).sort(), Object.keys(fixture.cases).sort());
  for (const [name, build] of Object.entries(BUILDERS)) {
    const figure = build();
    assert.equal(sceneExportSupportReason(figure), null, name);
    const digests = {
      svg_sha256: sha256(figure.toSvg()),
      png_sha256: sha256(figure.toPng({ scale: 1 })),
    };
    assert.deepEqual(digests, fixture.cases[name], name);
  }
});

test("Node cross-host cases exercise the tiers they name", () => {
  const decode = (bytes) => new TextDecoder().decode(bytes);
  const line = decode(lineFigure().toSvg());
  const points = line.match(/<polyline points="([^"]*)"/)[1].split(" ");
  assert.ok(points.length > 720 && points.length <= 4 * 720, `${points.length} M4 rows`);
  const scatter = decode(scatterFigure().toSvg());
  assert.equal((scatter.match(/<circle/g) || []).length, SCATTER_N);
  const wedges = [...decode(polarBarFigure().toSvg()).matchAll(/<path d="([^"]*)"/g)]
    .map((match) => match[1])
    .filter((d) => d.includes(" A "));
  assert.equal(wedges.length, 3);
});
