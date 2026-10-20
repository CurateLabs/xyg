/**
 * Independent Node public authoring for the #1006 per-annotation label corpus.
 *
 * Each case authors the same chart literals as
 * tests/test_static_annotation_labels_cross_host.py through the public Figure
 * API and exports every admitted format; the Rust annotation-style projection
 * decides every size, weight, style, alignment and box, and Rust projects
 * axes-fraction anchors and lays out explicit cell boxes (host marshals facts).
 */
import { createHash } from "node:crypto";

import { Figure } from "../src/index.js";

const formats = ["svg", "png", "pdf", "jpeg", "webp"];

function text(x, y, value, style = {}) {
  return { kind: "text", x, y, text: value, dx: 0, dy: -6, anchor: "start", style };
}

/** One table-style cell: an axes-fraction anchor and an explicit box. */
function cell(x, y, value, anchor, { dx = 0, dy = 0, ...style } = {}) {
  return {
    kind: "text", x, y, text: value, dx, dy, anchor,
    style: {
      coordinate_space: "axes_fraction",
      vertical_align: "center",
      background: "#dbeafe",
      border: "1.5px solid #000000",
      ...style,
    },
  };
}

function figure(...annotations) {
  const fig = new Figure({
    width: 320,
    height: 240,
    showLegend: false,
    xAxis: { domain: [0, 2], label: "X" },
    yAxis: { domain: [0, 4], label: "Y" },
  });
  fig.line([0, 1, 2], [1, 3, 2], { color: "#ef4444", width: 2 });
  for (const annotation of annotations) fig.annotate(annotation);
  return fig;
}

const cases = {
  mixed_typography: figure(
    text(0.2, 1, "Default"),
    text(0.7, 2, "Large bold", { font_size: 18, font_weight: "bold", label_color: "#336699" }),
    text(1.2, 3, "Slanted", { font_style: "italic", font_size: 9, vertical_align: "center" }),
    text(1.5, 1.5, "Top", { font_weight: 700, vertical_align: "top", label_color: "#aa0000" }),
  ),
  boxes: figure(
    text(0.2, 1, "Wide pad", {
      background: "#ffffff", border: "1px solid #102030", padding: "6px",
    }),
    text(0.2, 2, "Tall pad", {
      background: "#fff3cd", border: "2px solid #664d03", padding: "2px 9px",
    }),
    text(0.2, 3, "Default pad", { background: "#e0f2fe", font_size: 15 }),
    text(1.2, 2, "Unboxed", { font_size: 14 }),
  ),
  table_cells: figure(
    cell(0.25, 0, "region", "middle", {
      box_width: "50%", box_height: 16, dy: 8, padding: "0px 5%", font_size: 13,
    }),
    cell(0.95, 0, "value", "end", {
      box_width: "50%", box_height: 16, dy: 8, padding: "0px 5%", background: "#dcfce7",
    }),
    cell(0, 0.5, "row", "start", { box_width: 40, box_height: "20%", dx: -36, padding: "0px 4px" }),
    cell(0.55, 0.5, " ", "start", {
      box_width: "40%", box_height: "20%", padding: "0px 4%", background: "#fee2e2",
    }),
  ),
  axes_fraction_text: figure(
    {
      kind: "text", x: 0.02, y: 0.95, text: "(a)", dx: 0, dy: 0, anchor: "start",
      style: { coordinate_space: "axes_fraction" },
    },
    {
      kind: "text", x: 1, y: 0, text: "corner", dx: -4, dy: -4, anchor: "end",
      style: { coordinate_space: "axes_fraction", font_weight: "bold" },
    },
    text(1, 2, "data"),
  ),
  mixed_kinds: figure(
    text(0.2, 1, "Default"),
    { kind: "rule", axis: "y", value: 3, text: "limit", style: { font_size: 9 } },
    {
      kind: "callout", x: 1, y: 2, text: "peak", dx: 36, dy: -30, anchor: "start",
      style: { font_size: 15, font_weight: "bold" },
    },
    text(1.4, 3.5, "Large", { font_size: 20, background: "#ffffff", padding: "4px 8px" }),
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

const failures = {};
const attempts = {
  round_box: [text(1, 2, "Round", { background: "#ffffff", border_radius: 5 })],
  padding_values: [text(1, 2, "Pad", { background: "#ffffff", padding: "1px 2px 3px" })],
  custom_font: [text(1, 2, "Font", { font_family: "Papyrus" })],
  one_sided_box: [cell(0.5, 0.5, "cell", "middle", { box_width: 40 })],
  uncentered_box: [cell(0.5, 0.5, "cell", "middle", { box_width: 40, box_height: 16, vertical_align: "top" })],
  percent_box_in_data_space: [text(1, 2, "cell", {
    background: "#ffffff", vertical_align: "center", box_width: "10%", box_height: 16,
  })],
  figure_fraction_text: [
    { kind: "text", x: 0.5, y: 0.5, text: "fig", style: { coordinate_space: "figure_fraction" } },
  ],
  cell_off_canvas: [cell(0.5, 0, "cell", "middle", { box_width: 40, box_height: 160, dy: 20 })],
  cell_text_overflow: [cell(0.5, 0.5, "far too long for its cell", "start", { box_width: 60, box_height: 16 })],
};
for (const [name, annotations] of Object.entries(attempts)) {
  try {
    figure(...annotations).toSvg();
    failures[name] = null;
  } catch (error) {
    failures[name] = String(error.message ?? error);
  }
}
process.stdout.write(JSON.stringify({ cases: out, failures }));
