#!/usr/bin/env node
/**
 * Cross-host proof for the Rust-owned per-point scatter size plane (#1006): the
 * same size-array scatters export through Node so Python can compare bytes.
 */

import { Figure, sceneExportSupportReason, sceneStaticExport, staticDocumentEncode } from "../src/index.js";

const X = [0.5, 1, 1.5, 2, 2.5];
const Y = [1, 2, 1, 2, 1];
const SIZE = [10, 20, 30, 40, 50];

function figureFor(name) {
  const f = new Figure({ width: 320, height: 240 });
  f.setAxisDomain("x", [0, 3]);
  f.setAxisDomain("y", [0, 3]);
  if (name === "size_array_constant_color") {
    f.scatter(X, Y, { color: "#9467bd", size: SIZE, sizeRange: [4, 14] });
  } else if (name === "size_array_continuous_color") {
    f.scatter(X, Y, { color: [0, 1, 2, 3, 4], size: SIZE, sizeRange: [4, 14] });
  } else {
    throw new Error(`unknown case ${name}`);
  }
  f.traces.forEach((trace, index) => { trace.id = index; });
  return f;
}

const out = {};
for (const name of ["size_array_constant_color", "size_array_continuous_color"]) {
  const figure = figureFor(name);
  const reason = sceneExportSupportReason(figure);
  if (reason !== null) throw new Error(`${name} failed public preflight: ${reason}`);
  const scene = figure.toScene();
  out[name] = {
    scene_b64: Buffer.from(scene).toString("base64"),
    xyst_b64: Buffer.from(staticDocumentEncode({ panels: [{ scene, x: 0, y: 0, width: 320, height: 240 }], width: 320, height: 240 })).toString("base64"),
    svg_b64: Buffer.from(figure.toSceneSvg(), "utf8").toString("base64"),
    png_b64: Buffer.from(sceneStaticExport(scene, "png", { width: 320, height: 240, scale: 1 })).toString("base64"),
  };
}
process.stdout.write(`${JSON.stringify(out)}\n`);
