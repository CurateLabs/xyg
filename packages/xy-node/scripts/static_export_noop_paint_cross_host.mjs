#!/usr/bin/env node
/**
 * Cross-host proof for Rust-owned no-op traces and per-segment colormapped
 * strokes (#1006): the same charts export through Node so Python can compare
 * bytes.
 */

import { Figure, sceneExportSupportReason, sceneStaticExport } from "../src/index.js";

function fixedDomains(figure) {
  figure.setAxisDomain("x", [0, 3]);
  figure.setAxisDomain("y", [0, 3]);
  return figure;
}

function normalizeIds(figure) {
  figure.traces.forEach((trace, index) => { trace.id = index; });
  return figure;
}

function figureFor(name) {
  const f = fixedDomains(new Figure({ width: 320, height: 240 }));
  if (name === "empty_traces") {
    f.line([0, 1, 2], [0, 2, 1], { color: "#ef4444" });
    f.line([], [], { color: "#22c55e", name: "proxy" });
    f.scatter([], [], { style: { color: "#3987e5", size: 6 } });
  } else if (name === "colormapped_segments") {
    f.segments([0, 1, 2, 0], [0, 1, 2, 2], [1, 2, 3, 1], [1, 0, 3, 3], { color: [0, 0, 1, 1] });
  } else {
    throw new Error(`unknown case ${name}`);
  }
  return normalizeIds(f);
}

const out = {};
for (const name of ["empty_traces", "colormapped_segments"]) {
  const figure = figureFor(name);
  const reason = sceneExportSupportReason(figure);
  if (reason !== null) throw new Error(`${name} failed public preflight: ${reason}`);
  const scene = figure.toScene();
  out[name] = {
    scene_b64: Buffer.from(scene).toString("base64"),
    svg_b64: Buffer.from(figure.toSceneSvg(), "utf8").toString("base64"),
    png_b64: Buffer.from(sceneStaticExport(scene, "png", { width: 320, height: 240, scale: 1 })).toString("base64"),
  };
}
process.stdout.write(`${JSON.stringify(out)}\n`);
