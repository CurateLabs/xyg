// Scene-sourced straight arrows must hydrate in the browser painter (#1006).
//
// `to_browser_painter` serializes Rust's arrow run (2/5/8-vertex shaft plus an
// optional filled head). The browser hydrator once accepted only 2-vertex
// shafts, so every open-head arrow threw XYG_WASM_MALFORMED_OUTPUT. This test
// bundles the real hydrator (`js/src/48_wasm_scene.ts`) in memory and feeds it
// the painter bytes of every admitted style, then checks the traces carry
// Rust's exact vertices (the browser has no second arrow renderer for them).
import assert from "node:assert/strict";
import { existsSync } from "node:fs";
import { fileURLToPath, pathToFileURL } from "node:url";
import test from "node:test";

import { Figure, sceneBrowserPainter, sceneSvg } from "../src/index.js";

const root = fileURLToPath(new URL("../../../", import.meta.url));
const vite = `${root}node_modules/vite/dist/node/index.js`;
const skip = existsSync(vite) ? false : "root node_modules (npm ci) required to bundle the hydrator";

async function hydrator() {
  const { build } = await import(pathToFileURL(vite).href);
  const out = await build({
    configFile: false,
    logLevel: "error",
    build: { write: false, minify: false, lib: { entry: `${root}js/src/48_wasm_scene.ts`, formats: ["es"], fileName: "hydrator" } },
  });
  const code = (Array.isArray(out) ? out[0] : out).output[0].code;
  return import(`data:text/javascript;base64,${Buffer.from(code).toString("base64")}`);
}

// admitted style -> [shaft vertices, filled head traces]
const STYLES = {
  "-|>": [{}, 2, 1],
  "->": [{ head_style: "v" }, 5, 0],
  "<-": [{ head_style: "none", tail_style: "v" }, 5, 0],
  "<->": [{ head_style: "v", tail_style: "v" }, 8, 0],
  "-": [{ head_style: "none" }, 2, 0],
  "label-attach": [{ head_style: "v", start_offset: "6,-4", label_clear: "20,20,8,8", gap_end: 3 }, 5, 0],
};

function figure(style) {
  const fig = new Figure({ width: 320, height: 240, showLegend: false, xAxis: { domain: [0, 2] }, yAxis: { domain: [0, 4] } });
  fig.line([0, 1, 2], [1, 3, 2]);
  fig.annotate({ kind: "arrow", x0: 0.4, y0: 3.4, x1: 1.5, y1: 1.2, style });
  return fig;
}

for (const [name, [style, vertices, heads]] of Object.entries(STYLES)) {
  test(`painter hydration draws the Rust arrow vertices for ${name}`, { skip }, async () => {
    const { compilePainter } = await hydrator();
    const scene = figure(style).toScene();
    const painter = sceneBrowserPainter(scene);
    const { spec } = compilePainter(painter.buffer.slice(painter.byteOffset, painter.byteOffset + painter.byteLength));
    assert.deepEqual(spec.annotations.map((a) => a.kind), ["straight_arrow"]);
    // trace 0 is the data line; the arrow's shaft follows, then its optional head.
    const shaft = spec.traces[1];
    assert.equal(shaft.n_points, vertices);
    assert.equal(spec.traces.length, 2 + heads);
    const view = new DataView(painter.buffer, painter.byteOffset, painter.byteLength);
    const column = (index) => Array.from({ length: spec.columns[index].len }, (_, i) =>
      view.getFloat32(spec.columns[index].byte_offset + i * 4, true));
    const xs = column(shaft.x), ys = column(shaft.y);
    // Same vertices as the Rust SVG of the same Scene (the last polyline).
    const svg = [...sceneSvg(scene).matchAll(/<polyline points="([^"]*)"/g)].at(-1)[1].trim().split(/\s+/);
    assert.equal(svg.length, vertices);
    svg.forEach((pair, i) => {
      const [sx, sy] = pair.split(",").map(Number);
      assert.ok(Math.abs(xs[i] - sx) < 0.02 && Math.abs(ys[i] - sy) < 0.02, `${name} vertex ${i}: ${xs[i]},${ys[i]} vs ${pair}`);
    });
  });
}

test("painter hydration of an arrow beside a styled annotation label stays below XYLB v7", { skip }, async () => {
  const { compilePainter } = await hydrator();
  const fig = figure({ head_style: "v", tail_style: "v" });
  fig.annotate({ kind: "text", x: 1, y: 3, text: "styled note", dx: 0, dy: -6, style: { label_background: "#ffffff" } });
  const painter = sceneBrowserPainter(fig.toScene());
  const at = Buffer.from(painter).indexOf("XYLB");
  assert.ok(at >= 0);
  assert.ok(new DataView(painter.buffer, painter.byteOffset).getUint32(at + 4, true) <= 5);
  const { spec } = compilePainter(painter.buffer.slice(painter.byteOffset, painter.byteOffset + painter.byteLength));
  assert.ok(spec.annotations.some((a) => a.kind === "straight_arrow"));
});
