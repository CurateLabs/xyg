/** Panel-owned legends and the line-handle marker, authored here (not received from Python). */
import { Figure, staticDocumentEncode, staticDocumentExport } from "../src/index.js";

const marker = { symbol: "square", color: "#cc00cc", size: 6, stroke_width: 1 };
const legends = [
  [0, { loc: "upper left", items: [
    { kind: "line", name: "marked", style: { color: "#cc00cc", width: 2, legend_marker: marker } },
    { kind: "line", name: "plain", style: { color: "#1f77b4", width: 2 } },
    { kind: "scatter", name: "points", style: { color: "#2ca02c", size: 8 } },
  ] }],
  [1, { loc: "lower right", items: [
    { kind: "line", name: "second", style: { color: "#d62728", width: 2, legend_marker: { symbol: "triangle", size: 9 } } },
  ] }],
];
const scenes = [0, 1].map(() => {
  const figure = new Figure({ width: 200, height: 160, showLegend: false,
    xAxis: { domain: [0, 2] }, yAxis: { domain: [0, 4] } });
  figure.line([0, 1, 2], [1, 3, 2], { color: "#ef4444", width: 2 });
  return figure.toScene();
});
const document = Buffer.from(staticDocumentEncode({
  panels: scenes.map((scene, index) => ({ scene, x: index * 200, y: 0, width: 200, height: 160 })),
  width: 400, height: 160, panelLegends: legends,
}));
// One single-panel document per legend location, plus empty/partial marker
// objects (presence semantics must match the Python packer byte for byte).
const single = (legend) => {
  const doc = Buffer.from(staticDocumentEncode({
    panels: [{ scene: scenes[0], x: 0, y: 0, width: 200, height: 160 }],
    width: 200, height: 160, panelLegends: [[0, legend]],
  }));
  return { document: doc.toString("base64"), svg: Buffer.from(staticDocumentExport(doc, "svg")).toString("base64") };
};
const matrix = {};
for (const loc of ["upper left", "upper right", "lower left", "lower right", "center"]) {
  matrix[loc] = single({ loc, items: [{ kind: "line", name: "series", style: { color: "#1f77b4", width: 2 } }] });
}
const markers = {
  empty: {},
  size_only: { size: 0.5 },
  stroke_only: { stroke_width: 2, color: "#00aa00" },
};
const markerDocs = {};
for (const [name, legend_marker] of Object.entries(markers)) {
  markerDocs[name] = single({ items: [{ kind: "line", name: name, style: { color: "#1f77b4", width: 2, legend_marker } }] });
}
process.stdout.write(JSON.stringify({
  matrix,
  markers: markerDocs,
  scenes: scenes.map((scene) => Buffer.from(scene).toString("base64")),
  document: document.toString("base64"),
  svg: Buffer.from(staticDocumentExport(document, "svg")).toString("base64"),
  png: Buffer.from(staticDocumentExport(document, "png", { scale: 1 })).toString("base64"),
}));
