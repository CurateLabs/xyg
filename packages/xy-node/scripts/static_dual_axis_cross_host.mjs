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
  symlog: () => dualFigure({
    y2: { type: "symlog", constant: 2, domain: [-100, 100] },
    y2Values: [-50, 0, 50],
  }),
  // Authored tick-collision options reach Rust through the same code as y.
  gap: () => dualFigure({ y2: { tick_label_min_gap: 200 } }),
  preserve: () => dualFigure({ y2: { tick_label_min_gap: 200, tick_label_strategy: "preserve" } }),
  collision_key: () => dualFigure({ y2: { tick_label_min_gap: 200, collision: "preserve" } }),
  strategy_wins: () => dualFigure({
    y2: { tick_label_min_gap: 200, tick_label_strategy: "preserve", collision: "hide" },
  }),
  // An authored empty tick list means automatic ticks, for y2 as for y.
  empty_y2_ticks: () => dualFigure({ y2: { tick_values: [] } }),
  empty_y_ticks: () => dualFigure({ y: { tick_values: [] } }),
};

// Authored values the Scene rejects: both hosts must pass them through untouched
// and surface Rust's rejection, never a host default.
const INVALID = {
  constant_zero: { type: "symlog", constant: 0 },
  constant_negative: { type: "symlog", constant: -2 },
  domain_infinite: { domain: [0, Number.POSITIVE_INFINITY] },
  angle_infinite: { tick_label_angle: Number.POSITIVE_INFINITY },
  angle_negative_infinite: { tick_label_angle: Number.NEGATIVE_INFINITY },
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
  y2_category: () => dualFigure({ y2: { type: "category" } }),
  // Annotations read on the secondary y scale are refused, never projected
  // through the primary scale.
  y2_annotation_data: () => y2Annotation({}),
  y2_annotation_yaxis_transform: () => y2Annotation({ style: { coordinate_space: "yaxis_transform" } }),
  y2_annotation_hline: () => {
    const figure = dualFigure();
    figure.annotate({ kind: "rule", axis: "y", value: 200, y_axis: "y2" });
    return figure;
  },
  // Spaces that never read the y scale project identically on y2: admitted.
  y2_annotation_axes_fraction: () => y2Annotation({ y: 0.5, style: { coordinate_space: "axes_fraction" } }),
  y2_annotation_primary: () => y2Annotation({ y: 2, y_axis: undefined }),
};

function y2Annotation(extra) {
  const figure = dualFigure();
  figure.annotate({ kind: "text", x: 2, y: 200, text: "secondary", y_axis: "y2", ...extra });
  return figure;
}

const b64 = (bytes) => Buffer.from(bytes).toString("base64");
const out = { cases: {}, reasons: {}, invalid: {} };
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
for (const [name, y2] of Object.entries(INVALID)) {
  try {
    out.invalid[name] = sceneExportSupportReason(dualFigure({ y2 }));
  } catch (error) {
    out.invalid[name] = error.message;
  }
}
process.stdout.write(`${JSON.stringify(out)}\n`);
