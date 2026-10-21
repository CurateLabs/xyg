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

const CONTOUR_Z = [[0, 1, 0], [1, 2, 1], [0, 1, 0]];
// Same authored facts as tests/test_static_export_noop_paint_cross_host.py (#1025).
const CONTOURS = {
  contour_default_colormap: {},
  contour_named_colormap: { colormap: "magma" },
  contour_constant_color: { color: "#ef4444" },
  contour_level_colors: { color: [[1, 0, 0], [1, 1, 0], [0, 0, 1]] },
};

// Custom colormaps are refused by Scene export on both hosts (#1025).
const REJECTED_CONTOURS = {
  contour_gradient_colormap: { colormap: "linear-gradient(#ff0000, #0000ff)" },
  contour_listed_colormap: { colormap: ["#ff0000", "#00ff00", "#0000ff"] },
  contour_stops_colormap: { colormap: [[255, 0, 0], [0, 0, 255]] },
};

function figureFor(name) {
  const f = fixedDomains(new Figure({ width: 320, height: 240 }));
  if (name === "empty_traces") {
    f.line([0, 1, 2], [0, 2, 1], { color: "#ef4444" });
    f.line([], [], { color: "#22c55e", name: "proxy" });
    f.scatter([], [], { style: { color: "#3987e5", size: 6 } });
  } else if (name === "colormapped_segments") {
    f.segments([0, 1, 2, 0], [0, 1, 2, 2], [1, 2, 3, 1], [1, 0, 3, 3], { color: [0, 0, 1, 1] });
  } else if (name in CONTOURS || name in REJECTED_CONTOURS) {
    f.contour(CONTOUR_Z, { levels: [0.25, 1.0, 1.75], cornerMask: false, ...CONTOURS[name], ...REJECTED_CONTOURS[name] });
  } else {
    throw new Error(`unknown case ${name}`);
  }
  return normalizeIds(f);
}

const out = {};
for (const name of Object.keys(REJECTED_CONTOURS)) {
  out[name] = { reason: sceneExportSupportReason(figureFor(name)) };
}
for (const name of ["empty_traces", "colormapped_segments", ...Object.keys(CONTOURS)]) {
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
