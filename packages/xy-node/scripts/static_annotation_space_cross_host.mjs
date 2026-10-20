/**
 * Independent Node public authoring for the #1006 annotation coordinate
 * spaces (`axes_fraction`, `xaxis_transform`, `yaxis_transform`).
 *
 * Mirrors tests/test_static_annotation_space_cross_host.py: the same chart
 * literals through the public Figure API, every static format, the packed
 * XYAF bulk bytes and the stable rejection reasons. The host marshals the
 * `coordinate_space` string; Rust owns the code and the projection.
 */
import { createHash } from "node:crypto";

import { Figure } from "../src/index.js";
import { sceneXyafBulkPack } from "../src/sceneBulkNative.js";

const formats = ["svg", "png", "pdf", "jpeg", "webp"];

function text(x, y, value, style = {}) {
  return { kind: "text", x, y, text: value, dx: 0, dy: 0, anchor: "middle", style };
}

function figure(...annotations) {
  const fig = new Figure({
    width: 320,
    height: 240,
    showLegend: false,
    xAxis: { type: "log", domain: [1, 1000], label: "X" },
    yAxis: { domain: [0, 4], label: "Y" },
  });
  fig.line([1, 10, 1000], [1, 3, 2], { color: "#ef4444", width: 2 });
  for (const annotation of annotations) fig.annotate(annotation);
  return fig;
}

const cases = {
  axes_fraction: figure(
    text(0.5, 0.5, "Center", { coordinate_space: "axes_fraction" }),
    text(0.02, 0.95, "Corner", { coordinate_space: "axes_fraction", font_size: 9 }),
    text(0.5, -0.1, "Below", {
      coordinate_space: "axes_fraction", background: "#dbeafe", padding: "4px 8px",
    }),
  ),
  mixed: figure(
    text(10, 0.5, "x data", { coordinate_space: "xaxis_transform" }),
    text(0.25, 3, "y data", { coordinate_space: "yaxis_transform" }),
  ),
  data_reference: figure(
    text(1000 ** 0.5, 2, "Center"),
    text(10, 2, "x data"),
    text(1000 ** 0.25, 3, "y data"),
  ),
};

const out = {};
for (const [name, fig] of Object.entries(cases)) {
  out[name] = {};
  for (const format of formats) {
    const bytes = Buffer.from(fig.toImage(format, { scale: 1, quality: 90 }));
    out[name][format] = format === "svg"
      ? { text: bytes.toString("utf8") }
      : { sha256: createHash("sha256").update(bytes).digest("hex") };
  }
}

const bulk = {};
for (const space of ["data", "axes_fraction", "xaxis_transform", "yaxis_transform"]) {
  bulk[space] = Buffer.from(
    sceneXyafBulkPack([text(0.25, 0.75, "Pack", { coordinate_space: space })]),
  ).toString("hex");
}

const failures = {};
const attempts = {
  figure_fraction: [text(0.5, 0.5, "Fig", { coordinate_space: "figure_fraction" })],
  unknown_space: [text(0.5, 0.5, "Odd", { coordinate_space: "polar" })],
  callout_space: [{
    kind: "callout", x: 0.5, y: 0.5, text: "No", dx: 10, dy: -10,
    style: { coordinate_space: "axes_fraction" },
  }],
};
for (const [name, annotations] of Object.entries(attempts)) {
  try {
    figure(...annotations).toSvg();
    failures[name] = null;
  } catch (error) {
    failures[name] = String(error.message ?? error);
  }
}
process.stdout.write(JSON.stringify({ cases: out, bulk, failures }));
