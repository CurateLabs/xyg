/**
 * Independent Node public authoring for the #1024 default-offset corpus.
 *
 * The text annotations omit `dx`/`dy`; the Rust-owned default (ABI 392) is the
 * only source of the offset, so the Python twin in
 * tests/test_text_annotation_default_offset_cross_host.py must match byte for byte.
 */
import { createHash } from "node:crypto";

import { Figure } from "../src/index.js";

const formats = ["svg", "png", "pdf", "jpeg", "webp"];

function figure(annotation = { kind: "text", x: 1, y: 2, text: "default offset" }, annotate = true) {
  const fig = new Figure({
    width: 320,
    height: 240,
    showLegend: false,
    xAxis: { domain: [0, 2], label: "X" },
    yAxis: { domain: [0, 4], label: "Y" },
  });
  fig.line([0, 1, 2], [1, 3, 2], { color: "#ef4444", width: 2 });
  if (annotate) fig.annotate(annotation);
  else fig.annotations = [annotation];
  return fig;
}

const fig = figure();
const out = {};
for (const format of formats) {
  const bytes = Buffer.from(fig.toImage(format, { scale: 1, quality: 90 }));
  out[format] = format === "svg"
    ? { text: bytes.toString("utf8") }
    : { sha256: createHash("sha256").update(bytes).digest("hex") };
}

// Raw annotations (no `annotate()`), anchor-only, and an explicit zero offset:
// static output and the live payload must agree on what "unset" means.
const text = { kind: "text", x: 1, y: 2, text: "default offset" };
const raw = {};
for (const [name, annotation, annotate] of [
  ["bare", text, false],
  ["anchor_only", { ...text, anchor: "start" }, false],
  ["zero", { ...text, dx: 0, dy: 0 }, true],
]) {
  const fig = figure(annotation, annotate);
  const spec = fig.buildPayload().spec.annotations[0];
  raw[name] = { svg: Buffer.from(fig.toSvg()).toString("utf8"), payload: [spec.dx, spec.dy] };
}
process.stdout.write(JSON.stringify({ cases: { default_offset: out }, raw }));
