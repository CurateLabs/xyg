#!/usr/bin/env node
/**
 * Cross-host proof for the native secondary right-hand y axis (`y2`, twinx;
 * #1006): the same public dual-axis charts export through Node so Python can
 * compare XYST/SVG/PNG/PDF bytes, plus the stable Rust rejection reasons.
 */

import { Figure, sceneExportSupportReason } from "../src/index.js";

const WIDTH = 480;
const HEIGHT = 320;

function dualFigure({ y = {}, y2 = {}, y2Side = "right", y2Values = [100, 200, 300] } = {}) {
  const figure = new Figure({ width: WIDTH, height: HEIGHT });
  figure.setAxis("x", { domain: [0, 4] });
  figure.setAxis("y", { domain: [0, 4], label: "L", ...y });
  figure.setAxis("y2", { side: y2Side, label: "R", domain: [0, 400], ...y2 });
  figure.line([1, 2, 3], [1, 2, 3]);
  figure.line([1, 2, 3], y2Values, { yAxis: "y2" });
  figure.traces.forEach((trace, index) => { trace.id = index; });
  return figure;
}

const CASES = {
  dual: () => dualFigure(),
  styled: () => dualFigure({
    y: { style: { label_color: "#1f77b4" } },
    y2: {
      style: { label_color: "#d62728", tick_label_size: 20, tick_padding: 12 },
      tick_values: [0, 200, 400],
      tick_labels: ["zero", "two hundred", "four hundred"],
    },
  }),
  log: () => dualFigure({ y2: { type: "log", domain: [10, 1000] }, y2Values: [10, 100, 1000] }),
};

const REJECTIONS = {
  left_y2: () => dualFigure({ y2Side: "left" }),
  x2: () => {
    const figure = new Figure({ width: WIDTH, height: HEIGHT });
    figure.setAxis("x", { domain: [0, 4] });
    figure.setAxis("y", { domain: [0, 4] });
    figure.axis_options.x2 = { side: "top" };
    figure.line([1, 2, 3], [1, 2, 3]);
    return figure;
  },
  y2_colorbar: () => {
    const figure = dualFigure();
    figure.colorbar_options = { title: "c" };
    return figure;
  },
  y2_polar: () => {
    const figure = dualFigure();
    figure.coords = "polar";
    return figure;
  },
};

const b64 = (bytes) => Buffer.from(bytes).toString("base64");
const out = { cases: {}, reasons: {} };
for (const [name, build] of Object.entries(CASES)) {
  const figure = build();
  out.cases[name] = {
    xyst_b64: b64(figure.toStaticDocument()),
    svg_b64: b64(figure.toSvg()),
    png_b64: b64(figure.toPng({ scale: 1 })),
    pdf_b64: b64(figure.toPdf()),
  };
}
for (const [name, build] of Object.entries(REJECTIONS)) {
  out.reasons[name] = sceneExportSupportReason(build());
}
process.stdout.write(`${JSON.stringify(out)}\n`);
