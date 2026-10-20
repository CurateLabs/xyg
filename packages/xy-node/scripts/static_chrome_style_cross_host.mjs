/**
 * Independent Node public authoring for the #1004 chrome-style corpus.
 *
 * Each case authors the same chart literals as
 * tests/test_static_chrome_style_cross_host.py through the public Figure API
 * and exports every admitted format; the Rust projection decides every size,
 * paint and weight. With `--frames`, stdin carries only raw XYCS frames (base64) for the
 * framing parity probe; no Python Scene or authoring bytes are read.
 */
import { createHash } from "node:crypto";

import { Figure, staticChromeStyle } from "../src/index.js";

const formats = ["svg", "png", "pdf", "jpeg", "webp"];

function figure({ styles = {}, root = {}, xStyle = {}, yStyle = {} } = {}) {
  const fig = new Figure({
    width: 320,
    height: 240,
    title: "Title",
    showLegend: false,
    style: root,
    chromeStyles: styles,
    xAxis: { domain: [0, 1], label: "X", style: xStyle },
    yAxis: { domain: [0, 1], label: "Y", style: yStyle },
  });
  fig.line([0, 1], [0, 1], { color: "#ef4444", width: 2 });
  return fig;
}

const cases = {
  default: figure(),
  tick_30: figure({ styles: { tick_label: { "font-size": "30px" } } }),
  typography: figure({
    styles: {
      title: { "font-weight": "bold", color: "#102030" },
      axis_title: { color: "#ff0000", "font-style": "italic", "font-size": "16px" },
      tick_label: { color: "#00ff00", "font-weight": "bold", "font-size": "10px" },
    },
  }),
  precedence: figure({
    root: { "--chart-text": "#0000ff" },
    styles: { tick_label: { "font-size": "20px", color: "#00ff00" } },
    xStyle: { tick_label_size: 9, label_color: "#ff0000" },
  }),
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
  bad_size: { tick_label: { "font-size": "2em" } },
  bad_weight: { title: { "font-weight": "600" } },
  bad_color: { title: { color: "var(--x)" } },
  bad_slot: { legend: { "font-size": "12px" } },
  bad_font: { title: { "font-family": "Comic Sans" } },
};
for (const [name, styles] of Object.entries(attempts)) {
  try {
    figure({ styles }).toSvg();
    failures[name] = null;
  } catch (error) {
    failures[name] = String(error.message ?? error);
  }
}
let input = "";
if (process.argv.includes("--frames")) {
  for await (const chunk of process.stdin) input += chunk;
}
const frames = {};
for (const [name, value] of Object.entries(JSON.parse(input || "{}"))) {
  try {
    frames[name] = { output: Buffer.from(staticChromeStyle(Buffer.from(value, "base64"))).toString("base64") };
  } catch (error) {
    frames[name] = { error: String(error.message ?? error) };
  }
}
process.stdout.write(JSON.stringify({ cases: out, failures, frames }));
