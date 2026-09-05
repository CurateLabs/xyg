/** Query bytes are supplied only for ABI tests; public authoring below is independent. */
import { Figure, staticDocumentEncode, staticDocumentExport, staticDocumentLabels } from "../src/index.js";

let input = "";
for await (const chunk of process.stdin) input += chunk;
const queries = {};
for (const [name, value] of Object.entries(JSON.parse(input))) {
  try { queries[name] = { output: Buffer.from(staticDocumentLabels(Buffer.from(value, "base64"))).toString("base64") }; }
  catch (error) { queries[name] = { error: String(error.message ?? error) }; }
}
const labelsByCase = {
  default: [{ text: "Default < & >" }],
  styled: [{ text: "Italic < & >", x: 0.4, y: 0.6, size: 14, rotation: 90, opacity: 0.5,
    family: "DejaVu Sans", anchor: "end", vertical_align: "top", font_style: "Oblique", weight: "SEMIBOLD", color: "#654321" },
  { text: "Normal", x: 0.7, y: 0.3, anchor: "start", vertical_align: "baseline", family: "sans-serif" }],
};
const authored = {};
for (const [name, labels] of Object.entries(labelsByCase)) {
  const figure = new Figure({ width: 320, height: 240, showLegend: false,
    xAxis: { domain: [0, 2] }, yAxis: { domain: [0, 4] } });
  figure.line([0, 1, 2], [1, 3, 2], { color: "#ef4444", width: 2 });
  const scene = figure.toScene();
  const document = Buffer.from(staticDocumentEncode({ panels: [{ scene, x: 0, y: 0, width: 320, height: 240 }], width: 320, height: 240, labels }));
  const at = 64 + document.readUInt32LE(20) * 108 + document.readUInt32LE(24);
  const count = document.readUInt32LE(at + 8), start = at + 32;
  let end = start;
  for (let i = 0; i < count; i += 1) end += 40 + document.readUInt32LE(end + 28);
  authored[name] = { scene: Buffer.from(scene).toString("base64"), document: document.toString("base64"),
    labels: document.subarray(start, end).toString("base64"), svg: Buffer.from(staticDocumentExport(document, "svg")).toString("base64") };
}
process.stdout.write(JSON.stringify({ queries, public: authored }));
