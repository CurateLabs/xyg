// XYPB v17 wire test: Rust resolves each axis's tick-label layout and the
// decoded painter spec must carry exactly what the static SVG draws (#1036).
//
// Byte 5 of the x/y/y2 axis blocks is the layout mode Rust applied, bytes 6-7 an
// i16 label angle in 1/100 degree, and dropped labels arrive blank. This bundles
// the real hydrator (`js/src/48_wasm_scene.ts`) in memory and compares its
// `compilePainter` output with `sceneSvg` for crowded axes (x, y, y2) under every
// strategy. The browser-side drawing is covered by tests/browser.
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

const ab = (bytes) => bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength);
const STRATEGIES = ["auto", "hide", "rotate", "stagger", "preserve", "none", "off"];

// Every axis is crowded (narrow plot, short plot height) so thinning really bites.
function figure(axis, strategy, extra = {}) {
  const fig = new Figure({ width: 110, height: 80, showLegend: false, xAxis: { domain: [0, 3_000_000] }, yAxis: { domain: [0, 4] } });
  fig.setAxis("y2", { side: "right", domain: [0, 400] });
  fig.line([0, 1_000_000, 3_000_000], [1, 3, 2]);
  fig.line([0, 1_000_000, 3_000_000], [100, 300, 200], { yAxis: "y2" });
  if (strategy) fig.setAxis(axis, { tick_label_strategy: strategy, ...extra });
  return fig.toScene();
}

// Tick-label texts of the static SVG, per axis: x labels are middle-anchored or
// rotated, y labels end-anchored and upright, y2 labels start-anchored.
function svgAxes(scene) {
  const svg = Buffer.from(sceneSvg(scene)).toString("utf8");
  const out = { x: [], y: [], y2: [] };
  for (const match of svg.matchAll(/<text x="([^"]+)" y="([^"]+)"[^>]*text-anchor="(\w+)"( transform="rotate\(([-\d.]+) )?[^>]*>([^<]*)<\/text>/g)) {
    const [, x, y, anchor, , angle, text] = match;
    const label = { text, angle: Number(angle ?? 0), y: Number(y) };
    if (anchor === "start") out.y2.push(label);
    else if (anchor === "middle" || angle !== undefined) out.x.push(label);
    else out.y.push(label);
    void x;
  }
  return out;
}

for (const axis of ["x", "y", "y2"]) {
  for (const strategy of STRATEGIES) {
    test(`${axis} ${strategy}: decoded labels, angle and rows match the SVG`, { skip }, async () => {
      const { compilePainter } = await hydrator();
      const scene = figure(axis, strategy);
      const { spec } = compilePainter(ab(sceneBrowserPainter(scene)));
      const svg = svgAxes(scene);
      for (const id of ["x", "y", "y2"]) {
        const resolved = spec.axes[id];
        const hidden = id === axis && ["none", "off"].includes(strategy);
        assert.equal(resolved.tick_label_strategy, hidden ? strategy : "preserve", id);
        const shown = hidden ? [] : resolved.tick_labels.filter(Boolean);
        assert.deepEqual(shown, svg[id].map((label) => label.text), `${id} label set`);
        if (!shown.length) continue;
        const angle = resolved.tick_label_angle ?? 0;
        assert.ok(svg[id].every((label) => label.angle === angle), `${id} angle ${angle}`);
        // Stagger puts alternate labels on a second row (a distinct SVG y).
        if (id === "x") assert.equal(Boolean(resolved.tick_stagger), new Set(svg.x.map((label) => label.y)).size > 1, "x rows");
        else assert.ok(!resolved.tick_stagger, `${id} never staggers`);
      }
    });
  }
}

test("crowded axes really thin, rotate and stagger", { skip }, async () => {
  const { compilePainter } = await hydrator();
  const spec = (strategy) => compilePainter(ab(sceneBrowserPainter(figure("x", strategy)))).spec.axes.x;
  assert.equal(spec("hide").tick_labels.filter(Boolean).length < spec("preserve").tick_labels.filter(Boolean).length, true);
  assert.equal(spec("rotate").tick_label_angle, -35);
  assert.equal(spec("stagger").tick_stagger, true);
});

test("an explicit label angle round-trips", { skip }, async () => {
  const { compilePainter } = await hydrator();
  const scene = figure("x", "rotate", { tick_label_angle: 20 });
  const { spec } = compilePainter(ab(sceneBrowserPainter(scene)));
  assert.equal(spec.axes.x.tick_label_angle, 20);
  assert.ok(svgAxes(scene).x.every((label) => label.angle === -20 || label.angle === 20));
});

test("a painter from an older XYPB version is rejected", { skip }, async () => {
  const { compilePainter } = await hydrator();
  const painter = Buffer.from(sceneBrowserPainter(figure("x", "none")));
  assert.equal(painter.readUInt32LE(4), 17);
  painter.writeUInt32LE(16, 4);
  assert.throws(() => compilePainter(ab(painter)), /incompatible/);
});

test("an unknown axis layout mode is rejected", { skip }, async () => {
  const { compilePainter } = await hydrator();
  for (const mode of [0, 1, 7]) {
    const painter = Buffer.from(sceneBrowserPainter(figure("x", "none")));
    painter[64 + 24 + 5] = mode;
    assert.throws(() => compilePainter(ab(painter)), /axis style is invalid/);
  }
});
