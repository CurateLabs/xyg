// The browser painter must show the axis chrome Rust resolved from each axis's
// tick-label strategy, matching the static SVG (#1036).
//
// XYPB v17 carries the resolved strategy in byte 5 of the x/y/y2 axis blocks
// and blanks labels the strategy layout drops. This bundles the real hydrator
// (`js/src/48_wasm_scene.ts`) in memory and compares its output with the SVG.
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

// Crowded x ticks (narrow plot, long labels) so the layout really drops some.
function figure(axis, strategy) {
  const fig = new Figure({ width: 110, height: 200, showLegend: false, xAxis: { domain: [0, 3_000_000] }, yAxis: { domain: [0, 4] } });
  fig.setAxis("y2", { side: "right", domain: [0, 400] });
  fig.line([0, 1_000_000, 3_000_000], [1, 3, 2]);
  fig.line([0, 1_000_000, 3_000_000], [100, 300, 200], { yAxis: "y2" });
  if (strategy) fig.setAxis(axis, { tick_label_strategy: strategy });
  return fig.toScene();
}

const svgLabels = (scene) => (Buffer.from(sceneSvg(scene)).toString("utf8").match(/<text /g) ?? []).length;

for (const axis of ["x", "y", "y2"]) {
  for (const strategy of STRATEGIES) {
    test(`${axis} ${strategy}: painter label and chrome visibility match the SVG`, { skip }, async () => {
      const { compilePainter } = await hydrator();
      const scene = figure(axis, strategy);
      const { spec } = compilePainter(ab(sceneBrowserPainter(scene)));
      const resolved = spec.axes[axis];
      // `hide` is thinned by Rust, so the browser keeps exactly what it is given.
      assert.equal(resolved.tick_label_strategy, strategy === "hide" ? "preserve" : strategy);
      const shown = Object.values(spec.axes).reduce((sum, entry) => sum + (["none", "off"].includes(entry.tick_label_strategy) ? 0 : entry.tick_labels.filter(Boolean).length), 0);
      const titles = (Buffer.from(sceneSvg(scene)).toString("utf8").match(/<text [^>]*font-size="1[3-9]/g) ?? []).length;
      assert.equal(shown, svgLabels(scene) - titles);
    });
  }
}

test("a painter from an older XYPB version is rejected", { skip }, async () => {
  const { compilePainter } = await hydrator();
  const painter = Buffer.from(sceneBrowserPainter(figure("x", "none")));
  assert.equal(painter.readUInt32LE(4), 17);
  painter.writeUInt32LE(16, 4);
  assert.throws(() => compilePainter(ab(painter)), /incompatible/);
});

test("an unknown axis strategy code is rejected", { skip }, async () => {
  const { compilePainter } = await hydrator();
  const painter = Buffer.from(sceneBrowserPainter(figure("x", "none")));
  painter[64 + 24 + 5] = 7;
  assert.throws(() => compilePainter(ab(painter)), /axis style is invalid/);
});
