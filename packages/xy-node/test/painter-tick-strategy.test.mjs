// XYPB v17 wire test: Rust resolves each axis's tick-label layout and the
// decoded painter spec must carry exactly what the static SVG draws (#1036).
//
// Byte 5 packs the Rust layout mode (low 3 bits) and per-side anchors (bits 3-6);
// bytes 6-7 carry an
// i16 bottom/left angle in 1/100 degree; top/right angles use header 416/418/378
// (x/y/y2). Dropped labels arrive blank. This bundles
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

// Classify these fixtures by label anchor position relative to the plot, so
// top/bottom rotated labels keep their axis even when their text anchor changes.
function svgAxes(scene) {
  const svg = Buffer.from(sceneSvg(scene)).toString("utf8");
  const out = { x: [], y: [], y2: [] };
  const [, left, top, width] = /data-xy-chrome="plot-background" x="([^"]+)" y="([^"]+)" width="([^"]+)"/.exec(svg).map((v, i) => i ? Number(v) : v);
  const right = left + width;
  for (const match of svg.matchAll(/<text x="([^"]+)" y="([^"]+)"[^>]*text-anchor="(\w+)"( transform="rotate\(([-\d.]+) )?[^>]*>([^<]*)<\/text>/g)) {
    const [, x, y, anchor, , angle, text] = match;
    const axis = Number(x) >= left && Number(x) <= right ? "x" : Number(x) < left ? "y" : "y2";
    out[axis].push({ text, anchor, angle: Number(angle ?? 0), y: Number(y), side: axis === "x" ? Number(y) < top ? "top" : "bottom" : axis === "y" ? "left" : "right" });
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

for (const explicit of [false, true]) {
  test(`two-sided x rotation ${explicit ? "explicit" : "default"} matches each SVG side`, { skip }, async () => {
    const { compilePainter } = await hydrator();
    const scene = figure("x", "rotate", { tick_label_sides: ["bottom", "top"], ...(explicit ? { tick_label_angle: 20 } : {}) });
    const { spec } = compilePainter(ab(sceneBrowserPainter(scene)));
    const labels = svgAxes(scene).x;
    const shown = spec.axes.x.tick_labels.filter(Boolean);
    for (const [side, angle] of Object.entries(spec.axes.x.tick_label_angles)) {
      assert.equal(angle, explicit ? 20 : side === "bottom" ? -35 : 35);
      const svgSide = labels.filter((label) => label.side === side);
      assert.deepEqual(svgSide.map((label) => label.text), shown, side);
      assert.ok(svgSide.every((label) => label.angle === angle), `${side} rotation`);
    }
  });
}

for (const angle of [350, -350]) {
  for (const anchor of [null, angle > 0 ? "end" : "start"]) {
    test(`two-sided ${angle}deg preserves SVG anchors ${anchor ?? "default"}`, { skip }, async () => {
      const { compilePainter } = await hydrator();
      const scene = figure("x", "preserve", { tick_label_sides: ["bottom", "top"], tick_label_angle: angle, ...(anchor ? { tick_label_anchor: anchor } : {}) });
      const { spec } = compilePainter(ab(sceneBrowserPainter(scene)));
      const labels = svgAxes(scene).x;
      for (const side of ["bottom", "top"]) {
        assert.equal(spec.axes.x.tick_label_angles[side], angle > 0 ? -10 : 10);
        const resolvedAnchor = spec.axes.x.tick_label_anchors[side];
        const svgSide = labels.filter((label) => label.side === side);
        assert.ok(svgSide.length);
        assert.ok(svgSide.every((label) => label.angle === angle && label.anchor === (resolvedAnchor === "center" ? "middle" : resolvedAnchor)), `${side} anchor from original angle`);
      }
    });
  }
}

test("a large finite rotation normalizes before adding any offset", { skip }, async () => {
  const { compilePainter } = await hydrator();
  const scene = figure("x", "preserve", { tick_label_sides: ["bottom", "top"], tick_label_angle: 1e18 });
  const { spec } = compilePainter(ab(sceneBrowserPainter(scene)));
  assert.deepEqual(spec.axes.x.tick_label_angles, { bottom: -80, top: -80 });
  assert.deepEqual(spec.axes.x.tick_label_anchors, { bottom: "start", top: "end" });
});

test("upright resolved labels retain the no-angle room fast path", { skip }, async () => {
  const { compilePainter } = await hydrator();
  const { spec } = compilePainter(ab(sceneBrowserPainter(figure("x", "preserve"))));
  assert.equal(spec.axes.x.tick_label_angle, undefined);
});

test("a painter from an older XYPB version is rejected", { skip }, async () => {
  const { compilePainter } = await hydrator();
  const painter = Buffer.from(sceneBrowserPainter(figure("x", "none")));
  assert.equal(painter.readUInt32LE(4), 17);
  painter.writeUInt32LE(16, 4);
  assert.throws(() => compilePainter(ab(painter)), /incompatible/);
});

test("unknown axis layout modes, anchors and reserved bits are rejected", { skip }, async () => {
  const { compilePainter } = await hydrator();
  for (const mode of [0, 1, 7, 4 | (3 << 3), 4 | (3 << 5), 128 | 4]) {
    const painter = Buffer.from(sceneBrowserPainter(figure("x", "none")));
    painter[64 + 24 + 5] = mode;
    assert.throws(() => compilePainter(ab(painter)), /axis style is invalid/);
  }
});
