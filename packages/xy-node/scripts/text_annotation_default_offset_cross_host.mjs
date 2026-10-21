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

function figure() {
  const fig = new Figure({
    width: 320,
    height: 240,
    showLegend: false,
    xAxis: { domain: [0, 2], label: "X" },
    yAxis: { domain: [0, 4], label: "Y" },
  });
  fig.line([0, 1, 2], [1, 3, 2], { color: "#ef4444", width: 2 });
  fig.annotate({ kind: "text", x: 1, y: 2, text: "default offset" });
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
process.stdout.write(JSON.stringify({ cases: { default_offset: out } }));
