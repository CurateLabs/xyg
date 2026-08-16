#!/usr/bin/env node
/**
 * Node twin of benchmarks/bench_scale_all_charts.py (chart families + density).
 *
 * Exercises every major mark family through `@curatelabs/xyg-node` buildPayload and records
 * wall ms + wire bytes. Scatter density (Tier-2) is forced for LOD evidence.
 * Graph 10M/100M/1B LOD decisions live in bench_graph_scale_classes_node.mjs.
 *
 * Usage:
 *   node benchmarks/bench_scale_all_charts_node.mjs
 *   node benchmarks/bench_scale_all_charts_node.mjs --profile smoke
 */
import { performance } from "node:perf_hooks";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { nativeLibraryFileName } from "../packages/xy-node/src/native-path.js";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
process.chdir(root);
if (!process.env.XYG_NATIVE_LIB) {
  process.env.XYG_NATIVE_LIB = path.join(root, "target/release", nativeLibraryFileName());
}

const {
  SCATTER_DENSITY_THRESHOLD,
  areaChart,
  boxChart,
  contourChart,
  ecdfChart,
  errorbarChart,
  heatmapChart,
  hexbinChart,
  histogramChart,
  lineChart,
  lodPlan,
  scatterChart,
  stemChart,
  violinChart,
} = await import("../packages/xy-node/src/index.js");

const PROFILES = {
  smoke: { chartSizes: [10_000] },
  standard: { chartSizes: [10_000, 100_000] },
};

function best(fn, repeat = 3) {
  let b = Infinity;
  for (let i = 0; i < repeat; i += 1) {
    const t0 = performance.now();
    fn();
    b = Math.min(b, performance.now() - t0);
  }
  return b;
}

function fill(n, fn) {
  const out = new Float64Array(n);
  for (let i = 0; i < n; i += 1) out[i] = fn(i);
  return out;
}

function wireBytes(fig) {
  const { buffers } = fig.buildPayload();
  return buffers.byteLength ?? Buffer.byteLength(buffers);
}

function row(family, n, fig, extra = {}) {
  const tBuild = best(() => {
    /* rebuild cost measured by callers */
  }, 1);
  void tBuild;
  const tPayload = best(() => fig.buildPayload());
  return {
    family,
    n,
    payload_ms: tPayload,
    wire_bytes: wireBytes(fig),
    ...extra,
  };
}

function benchScatter(n) {
  const x = fill(n, (i) => Math.sin(i * 0.001));
  const y = fill(n, (i) => Math.cos(i * 0.001));
  const tBuild = best(() => scatterChart(x, y));
  const fig = scatterChart(x, y);
  const { spec } = fig.buildPayload();
  return {
    family: "scatter",
    n,
    build_ms: tBuild,
    payload_ms: best(() => fig.buildPayload()),
    wire_bytes: wireBytes(fig),
    tier: spec.traces[0].tier,
  };
}

function benchScatterDensity(n) {
  const x = fill(n, (i) => (i % 256) / 255);
  const y = fill(n, (i) => Math.floor(i / 256) / 255);
  const fig = scatterChart(x, y, { forceDensity: true });
  const { spec } = fig.buildPayload();
  return {
    family: "scatter_density",
    n,
    payload_ms: best(() => fig.buildPayload()),
    wire_bytes: wireBytes(fig),
    tier: spec.traces[0].tier,
    budget_ok: spec.traces[0].tier === "density",
  };
}

function benchLine(n) {
  const x = fill(n, (i) => i);
  const y = fill(n, (i) => Math.sin(i * 1e-3));
  const fig = lineChart(x, y);
  return row("line", n, fig, { build_ms: best(() => lineChart(x, y)) });
}

function benchHist(n) {
  const values = fill(n, (i) => Math.sin(i) + Math.cos(i * 0.3));
  const fig = histogramChart(values, { bins: 64 });
  return row("hist", n, fig, { build_ms: best(() => histogramChart(values, { bins: 64 })) });
}

function benchArea(n) {
  const x = fill(n, (i) => i);
  const y = fill(n, (i) => Math.sin(i * 1e-3) + 1);
  const fig = areaChart(x, y);
  return row("area", n, fig, { build_ms: best(() => areaChart(x, y)) });
}

function benchHeatmap(n) {
  const side = Math.max(8, Math.floor(Math.sqrt(n)));
  const z = [];
  for (let r = 0; r < side; r += 1) {
    const rowZ = [];
    for (let c = 0; c < side; c += 1) rowZ.push(r * side + c);
    z.push(rowZ);
  }
  const fig = heatmapChart(z);
  return row("heatmap", side * side, fig, { build_ms: best(() => heatmapChart(z)) });
}

function benchHexbin(n) {
  const x = fill(n, (i) => Math.sin(i * 0.01));
  const y = fill(n, (i) => Math.cos(i * 0.01));
  const fig = hexbinChart(x, y, { gridsize: 32 });
  return row("hexbin", n, fig, { build_ms: best(() => hexbinChart(x, y, { gridsize: 32 })) });
}

function benchBox(n) {
  const values = fill(n, (i) => Math.sin(i * 0.1));
  const fig = boxChart(values);
  return row("box", n, fig, { build_ms: best(() => boxChart(values)) });
}

function benchViolin(n) {
  const values = fill(n, (i) => Math.cos(i * 0.07));
  const fig = violinChart(values, { bins: 32 });
  return row("violin", n, fig, { build_ms: best(() => violinChart(values, { bins: 32 })) });
}

function benchContour(n) {
  const side = Math.max(8, Math.floor(Math.sqrt(n)));
  const z = [];
  for (let r = 0; r < side; r += 1) {
    const rowZ = [];
    for (let c = 0; c < side; c += 1) rowZ.push(Math.sin(c * 0.3) * Math.cos(r * 0.3));
    z.push(rowZ);
  }
  const fig = contourChart(z, { levels: 8 });
  return row("contour", side * side, fig, { build_ms: best(() => contourChart(z, { levels: 8 })) });
}

function benchErrorbar(n) {
  const k = Math.min(n, 4096);
  const x = fill(k, (i) => i);
  const y = fill(k, (i) => Math.sin(i * 0.01));
  const fig = errorbarChart(x, y, { yerr: 0.1 });
  return row("errorbar", k, fig, { build_ms: best(() => errorbarChart(x, y, { yerr: 0.1 })) });
}

function benchStem(n) {
  const k = Math.min(n, 4096);
  const x = fill(k, (i) => i);
  const y = fill(k, (i) => Math.cos(i * 0.02));
  const fig = stemChart(x, y);
  return row("stem", k, fig, { build_ms: best(() => stemChart(x, y)) });
}

function benchEcdf(n) {
  const values = fill(n, (i) => Math.sin(i * 0.05));
  const fig = ecdfChart(values);
  return row("ecdf", n, fig, { build_ms: best(() => ecdfChart(values)) });
}

function benchLodClasses() {
  const out = [];
  for (const n of [10_000_000, 100_000_000, 1_000_000_000]) {
    const plan = lodPlan(n, SCATTER_DENSITY_THRESHOLD);
    out.push({
      family: "scatter_lod_class",
      n,
      exact: plan.exact,
      gridW: plan.gridW,
      gridH: plan.gridH,
      budget_ok: plan.exact === false && plan.gridW > 0 && plan.gridH > 0,
    });
  }
  return out;
}

const args = process.argv.slice(2);
const profileName = args.includes("--profile")
  ? args[args.indexOf("--profile") + 1]
  : "smoke";
const profile = PROFILES[profileName] ?? PROFILES.smoke;

const results = [];
for (const n of profile.chartSizes) {
  results.push(benchScatter(n));
  results.push(benchScatterDensity(Math.min(n, 50_000)));
  results.push(benchLine(n));
  results.push(benchHist(n));
  results.push(benchArea(n));
  results.push(benchHeatmap(n));
  results.push(benchHexbin(n));
  results.push(benchBox(n));
  results.push(benchViolin(n));
  results.push(benchContour(n));
  results.push(benchErrorbar(n));
  results.push(benchStem(n));
  results.push(benchEcdf(n));
}
results.push(...benchLodClasses());

const hardOk = results.every((r) => r.budget_ok !== false);
const report = {
  host: "node",
  profile: profileName,
  ok: hardOk,
  results,
};
console.log(JSON.stringify(report, null, 2));
process.exit(hardOk ? 0 : 1);
