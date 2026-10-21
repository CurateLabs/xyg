// Rotated Scene labels must hydrate in the browser painter (#1040).
//
// Rust emits XYLB v6 (112-byte record, f64 rotation at +104) when any label is
// rotated. The hydrator once accepted v1-v5 only and rejected the whole frame.
// This bundles the real hydrator (`js/src/48_wasm_scene.ts`) in memory, feeds
// it Rust painter bytes, and pins the accepted XYLB versions against the
// Rust-side ceiling (`BROWSER_PAINTER_XYLB_MAX_VERSION` in scene.rs).
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

function figure(rotation, extra = {}) {
  const fig = new Figure({ width: 320, height: 240, showLegend: false, xAxis: { domain: [0, 2] }, yAxis: { domain: [0, 4] } });
  fig.line([0, 1, 2], [1, 3, 2]);
  fig.annotate({ kind: "text", x: 1, y: 3, text: "tilted", style: { rotation }, ...extra });
  return fig;
}

const ab = (bytes) => bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength);

const FEATURES = { rotation: 30, label_background: "#ffff00", label_border_color: "#ff0000", label_border_width: 2 };
const xylbVersion = (painter) => new DataView(painter.buffer, painter.byteOffset).getUint32(Buffer.from(painter).indexOf("XYLB") + 4, true);

test("client accepts the XYLB version of a painter payload carrying every label feature", { skip }, async () => {
  const { XYLB_PAINTER_VERSIONS, compilePainter } = await hydrator();
  const fig = figure(30);
  fig.annotate({ kind: "text", x: 0.5, y: 1, text: "boxed", style: FEATURES });
  const painter = sceneBrowserPainter(fig.toScene());
  const version = xylbVersion(painter);
  assert.ok(XYLB_PAINTER_VERSIONS.includes(version), `client rejects emitted XYLB v${version}`);
  assert.equal(version, Math.max(...XYLB_PAINTER_VERSIONS), "client ceiling is exactly what Rust emits");
  assert.ok(compilePainter(ab(painter)).sceneLabels.length >= 2);
});

test("rotated bordered callout box keeps its border (v6) and matches the SVG stroke", { skip }, async () => {
  const { compilePainter } = await hydrator();
  for (const rotation of [0, 30]) {
    const fig = figure(0);
    fig.annotate({ kind: "text", x: 0.5, y: 1, text: "boxed", style: { ...FEATURES, rotation } });
    const scene = fig.toScene();
    const painter = sceneBrowserPainter(scene);
    assert.equal(xylbVersion(painter), rotation ? 6 : 4);
    const label = compilePainter(ab(painter)).sceneLabels.find((l) => l.text === "boxed");
    assert.equal(label.rotation, rotation);
    assert.deepEqual(label.box.border, { color: "rgba(255 0 0 / 1)", width: 2 });
    assert.match(Buffer.from(sceneSvg(scene)).toString("utf8"), /annotation_label_box[^>]*stroke=/);
  }
});

test("rotated wrapped bordered label decodes (v5 fields inside v6)", { skip }, async () => {
  const { compilePainter } = await hydrator();
  const fig = figure(0);
  fig.annotate({ kind: "text", x: 0.5, y: 1, text: "one\ntwo", style: FEATURES });
  const scene = fig.toScene();
  const painter = sceneBrowserPainter(scene);
  const label = compilePainter(ab(painter)).sceneLabels.find((l) => l.text === "one\ntwo");
  assert.equal(xylbVersion(painter), 6);
  assert.equal(label.rotation, 30);
  assert.equal(label.box.border.width, 2);
  assert.match(Buffer.from(sceneSvg(scene)).toString("utf8"), /annotation_label_box[^>]*stroke=/);
});

for (const rotation of [30, -45, 90]) {
  test(`painter hydration keeps the XYLB v6 rotation ${rotation} and matches the SVG`, { skip }, async () => {
    const { compilePainter } = await hydrator();
    const fig = figure(rotation);
    const scene = fig.toScene();
    const painter = sceneBrowserPainter(scene);
    const at = Buffer.from(painter).indexOf("XYLB");
    assert.ok(at >= 0);
    const view = new DataView(painter.buffer, painter.byteOffset, painter.byteLength);
    assert.equal(view.getUint32(at + 4, true), 6);
    const { sceneLabels } = compilePainter(ab(painter));
    const label = sceneLabels.find((entry) => entry.text === "tilted");
    assert.ok(label, "rotated label decoded");
    assert.equal(label.rotation, rotation);
    // The static SVG rotates by -rotation about the label anchor (x, y).
    const svg = Buffer.from(sceneSvg(scene)).toString("utf8");
    assert.match(svg, new RegExp(`rotate\\(${-rotation} ${label.x} ${label.y}\\)`));
  });
}

test("rotated and upright labels coexist and the CSS rotates about the anchor", { skip }, async () => {
  const { compilePainter, labelRotationStyle } = await hydrator();
  const fig = figure(30);
  fig.annotate({ kind: "text", x: 0.5, y: 1, text: "flat" });
  const { sceneLabels } = compilePainter(ab(sceneBrowserPainter(fig.toScene())));
  assert.deepEqual(sceneLabels.map((l) => [l.text, l.rotation]).sort(), [["flat", 0], ["tilted", 30]]);
  assert.deepEqual(labelRotationStyle({ anchor: 1, rotation: 0, fontSize: 12 }), { transform: "translateX(-50%)" });
  assert.deepEqual(labelRotationStyle({ anchor: 1, rotation: 30, fontSize: 12 }), { transform: "translateX(-50%) rotate(-30deg)", transformOrigin: "50% 12px" });
  assert.deepEqual(labelRotationStyle({ anchor: 0, rotation: -45, fontSize: 10 }), { transform: "translateX(0) rotate(45deg)", transformOrigin: "0 10px" });
});

test("a nonfinite v6 rotation is rejected", { skip }, async () => {
  const { compilePainter } = await hydrator();
  const painter = Buffer.from(sceneBrowserPainter(figure(30).toScene()));
  const at = painter.indexOf("XYLB");
  const first = at + 16;
  painter.writeDoubleLE(NaN, first + 104);
  assert.throws(() => compilePainter(ab(painter)), /nonfinite geometry/);
});
