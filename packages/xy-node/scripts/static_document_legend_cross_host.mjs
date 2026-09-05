/** Raw ABI parity inputs are separate from independently authored public documents. */
import { Figure, staticDocumentEncode, staticDocumentExport, staticDocumentLegend } from "../src/index.js";

let input = "";
for await (const chunk of process.stdin) input += chunk;
const queries = {};
for (const [name, value] of Object.entries(JSON.parse(input))) {
  try { queries[name] = { output: Buffer.from(staticDocumentLegend(Buffer.from(value, "base64"))).toString("base64") }; }
  catch (error) { queries[name] = { error: String(error.message ?? error) }; }
}
// These literals are authored here, not received from Python.
const legends = {
  default: { items: [{ name: "Line" }] },
  styled: { title: "Kinds < & >", ncols: 2, anchor: [0.9, 0.9], handlelength: 3,
    handletextpad: 1, border_pad: 2,
    style: { fontSize: "13px", padding: "0.6em", rowGap: "0.7em", color: "#123456",
      background: "#ffffff", borderColor: "#222222", "--xy-legend-frame-alpha": String(1.5 / 255) },
    items: [{ kind: "line", name: "Line", style: { width: 4, stroke_width: 9, dash: true, color: "#123456" } },
      { kind: "scatter", name: "Point", style: { size: 7, opacity: 2, color: "#654321" } },
      { kind: "bar", name: "Patch", style: { color: "#22aa44" } }] },
};
const authored = {};
for (const [name, legend] of Object.entries(legends)) {
  const figure = new Figure({ width: 320, height: 240, showLegend: false,
    xAxis: { domain: [0, 2] }, yAxis: { domain: [0, 4] } });
  figure.line([0, 1, 2], [1, 3, 2], { color: "#ef4444", width: 2 });
  const scene = figure.toScene();
  const document = Buffer.from(staticDocumentEncode({ panels: [{ scene, x: 0, y: 0, width: 320, height: 240 }], width: 320, height: 240, legend }));
  const at = 64 + document.readUInt32LE(20) * 108 + document.readUInt32LE(24);
  const length = document.readUInt32LE(at + 12);
  authored[name] = { scene: Buffer.from(scene).toString("base64"), document: document.toString("base64"),
    legend: document.subarray(at + 32, at + 32 + length).toString("base64"),
    svg: Buffer.from(staticDocumentExport(document, "svg")).toString("base64") };
}
process.stdout.write(JSON.stringify({ queries, public: authored }));
