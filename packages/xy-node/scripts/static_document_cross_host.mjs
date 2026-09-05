import fs from "node:fs";

import { staticDocumentEncode, staticDocumentExport } from "../src/index.js";

const request = JSON.parse(fs.readFileSync(0, "utf8"));
const scenes = request.scenes.map((value) => Uint8Array.from(Buffer.from(value, "base64")));
const document = staticDocumentEncode({
  panels: scenes.map((scene, index) => ({
    scene,
    x: index * request.panelWidth - 5,
    y: 0,
    width: request.panelWidth,
    height: request.panelHeight,
    chromeMetrics: [12, 13, 4, 12, 13, 4],
    annotationFontSize: request.annotationFontSize ?? null,
  })),
  width: request.panelWidth * scenes.length,
  height: request.panelHeight,
  title: request.title,
  titleColor: request.titleColor,
  titleSize: request.titleSize,
  titleX: request.titleX,
  titleY: request.titleY,
  titleAnchor: 1,
  titleFlags: request.titleFlags ?? 0,
  labels: request.labels,
  legend: request.legend,
});
if (request.encodeOnly) {
  process.stdout.write(JSON.stringify({ document: Buffer.from(document).toString("base64") }));
  process.exit(0);
}
const outputs = {};
for (const format of ["svg", "png", "pdf", "jpeg", "webp"]) {
  outputs[format] = Buffer.from(staticDocumentExport(document, format, { scale: 1, quality: 90 })).toString("base64");
}
process.stdout.write(JSON.stringify({
  document: Buffer.from(document).toString("base64"),
  outputs,
}));
