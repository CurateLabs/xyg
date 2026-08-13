// JavaScript demo: compose a chart with the Node host bindings (same Rust
// core as Python, loaded via koffi) and emit a standalone HTML page via
// `toHtml`, which inlines the host-neutral `@curatelabs/xyg` paint client.
//
// Run from the repo root:
//
//   XY_NATIVE_LIB=$PWD/target/release/libxy_core.dylib node demo/js_demo.mjs
//
// Writes demo/js_demo.html.

import path from "node:path";
import { fileURLToPath } from "node:url";

import { createEngine } from "../packages/xy-node/src/index.js";

const here = path.dirname(fileURLToPath(import.meta.url));

// --- Data: a 200k-sample damped chirp (line, M4-decimated in Rust) plus the
// --- envelope as an area band and peak markers as a scatter overlay.
const n = 200_000;
const x = new Float64Array(n);
const signal = new Float64Array(n);
const envelope = new Float64Array(n);
for (let i = 0; i < n; i++) {
  const t = (i / (n - 1)) * 12.0;
  const env = Math.exp(-t / 5.0) * (1.4 + 0.3 * Math.sin(t * 0.9));
  const phase = 2 * Math.PI * (2.0 * t + 0.35 * t * t);
  x[i] = t;
  envelope[i] = env;
  signal[i] = env * Math.sin(phase) + 0.01 * Math.sin(t * 97.0);
}

// Local maxima of the signal, sampled sparsely for the marker overlay.
const peakX = [];
const peakY = [];
for (let i = 1; i < n - 1; i++) {
  if (signal[i] > signal[i - 1] && signal[i] > signal[i + 1] && signal[i] > 0.12) {
    peakX.push(x[i]);
    peakY.push(signal[i]);
  }
}

const fig = createEngine({
  width: 960,
  height: 520,
  title: "XY JavaScript demo — 200k-sample damped chirp (Node host, Rust core)",
});
fig.area(x, envelope, {
  name: "envelope",
  style: { color: "#0891b2", opacity: 0.14, line_width: 1.0 },
});
fig.line(x, signal, { name: "signal", style: { color: "#3267c8", width: 1.2 } });
fig.scatter(Float64Array.from(peakX), Float64Array.from(peakY), {
  name: "peaks",
  style: { color: "#dc2626", size: 5.0, opacity: 0.9 },
});

const out = path.join(here, "js_demo.html");
const html = fig.toHtml(out);
console.log(`wrote ${out} (${(html.length / 2 ** 20).toFixed(1)} MB, ${peakX.length} peaks)`);
