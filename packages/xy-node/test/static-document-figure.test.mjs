import assert from "node:assert/strict";
import test from "node:test";

import { Figure } from "../src/index.js";

test("Figure static aliases use the shared XYST product boundary", () => {
  const figure = new Figure({ width: 240, height: 180, showLegend: false });
  figure.line([0, 1, 2], [1, 3, 2], { color: "#2563eb", width: 2 });

  const document = figure.toStaticDocument({ background: "white", optimizePng: true });
  assert.equal(new TextDecoder().decode(document.subarray(0, 4)), "XYST");

  const svg = figure.toSvg();
  assert.equal(new TextDecoder().decode(svg.subarray(0, 4)), "<svg");
  assert.deepEqual(Array.from(figure.toPng().subarray(0, 8)), [137, 80, 78, 71, 13, 10, 26, 10]);
  assert.equal(new TextDecoder().decode(figure.toPdf().subarray(0, 5)), "%PDF-");
  assert.deepEqual(Array.from(figure.toJpeg().subarray(0, 3)), [255, 216, 255]);
  assert.equal(new TextDecoder().decode(figure.toWebp().subarray(0, 4)), "RIFF");
});

test("Figure toImage preserves shared format validation", () => {
  const figure = new Figure({ width: 120, height: 90, showLegend: false });
  figure.line([0, 1], [0, 1]);
  assert.throws(() => figure.toImage("gif"), /StaticDocument format/);
});

function tableFigure(cellStyle = {}) {
  const figure = new Figure({
    width: 320, height: 240, showLegend: false,
    xAxis: { domain: [0, 2] }, yAxis: { domain: [0, 4] },
  });
  figure.line([0, 1, 2], [1, 3, 2]);
  figure.annotate({
    kind: "text", x: 0.5, y: 0, text: "cell", dx: 0, dy: 10, anchor: "end",
    style: {
      coordinate_space: "axes_fraction", background: "#dbeafe", border: "1px solid #000000",
      padding: "6px", vertical_align: "center", box_width: 90, box_height: 16, ...cellStyle,
    },
  });
  return figure;
}

function plotAndCell(svg) {
  const plot = svg.match(/<clipPath[^>]*><rect x="([\d.]+)" y="([\d.]+)" width="([\d.]+)" height="([\d.]+)"/);
  const cell = svg.match(/data-xy-slot="annotation_label_box"[^>]*x="([\d.]+)" y="([\d.]+)" width="([\d.]+)" height="([\d.]+)"/);
  assert.ok(plot && cell, svg);
  return [plot.slice(1).map(Number), cell.slice(1).map(Number)];
}

test("axes-fraction boxed text exports as a Rust-placed table cell (#1006)", () => {
  const svg = new TextDecoder().decode(tableFigure().toSvg());
  const [[left, top, width, height], [x, y, w, h]] = plotAndCell(svg);
  // End-anchored at the plot's horizontal center with a 6px inset; centered
  // 10px below the axes bottom (box top = bottom + 10 - 8).
  assert.deepEqual([w, h], [90, 16]);
  assert.ok(Math.abs(x - (left + width / 2 + 6 - 90)) < 0.02);
  assert.ok(Math.abs(y - (top + height + 2)) < 0.02);
  assert.match(svg, />cell<\/text>/);
  // Percentages resolve in Rust against the final plot rectangle.
  const percent = new TextDecoder().decode(
    tableFigure({ box_width: "50%", padding: "0px 5%" }).toSvg(),
  );
  const [[pLeft, , pWidth], [px, , pw]] = plotAndCell(percent);
  assert.ok(Math.abs(pw - pWidth / 2) < 0.02);
  assert.ok(Math.abs(px - (pLeft + pWidth / 2 + 0.05 * pWidth - pWidth / 2)) < 0.02);
});

test("axes-fraction coordinates and explicit boxes fail closed with stable reasons (#1006)", () => {
  assert.throws(
    () => tableFigure({ coordinate_space: "figure_fraction" }).toSvg(),
    /coordinate_space 'data' or 'axes_fraction' only/,
  );
  assert.throws(() => tableFigure({ box_height: null }).toSvg(), /XYG_STATIC_UNSUPPORTED_ANNOTATION_BBOX/);
  assert.throws(() => tableFigure({ vertical_align: "top" }).toSvg(), /XYG_STATIC_UNSUPPORTED_ANNOTATION_BBOX/);
  assert.throws(
    () => tableFigure({ coordinate_space: "data", box_width: "50%" }).toSvg(),
    /XYG_STATIC_UNSUPPORTED_ANNOTATION_BBOX/,
  );
});
