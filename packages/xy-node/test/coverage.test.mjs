/**
 * Full mark-family coverage + density LOD for the Node host.
 * Complements marks.test.mjs (parity goldens) with end-to-end buildPayload checks.
 */
import assert from "node:assert/strict";
import test from "node:test";

import {
  DENSITY_GRID,
  PROTOCOL_VERSION,
  SCATTER_DENSITY_THRESHOLD,
  contourChart,
  errorBandChart,
  errorbarChart,
  figure,
  lodPlan,
  radarChart,
  sankeyChart,
  payloadTier,
  payloadM4Indices,
  payloadEvenIndices,
  payloadErrorbarIndices,
  payloadSampleTargetIndices,
  payloadSegmentBudget,
  payloadVisibleIndices,
  rectFiniteSel,
  shouldUseDensity,
  validIndicesF64,
  stairsChart,
  stemChart,
  stepChart,
  triangleMeshChart,
} from "../src/index.js";

function fill(n, fn) {
  const out = new Float64Array(n);
  for (let i = 0; i < n; i += 1) out[i] = fn(i);
  return out;
}

test("shouldUseDensity mirrors Python threshold / force / polar rules", () => {
  assert.equal(shouldUseDensity(SCATTER_DENSITY_THRESHOLD - 1), false);
  assert.equal(shouldUseDensity(SCATTER_DENSITY_THRESHOLD), false);
  assert.equal(shouldUseDensity(SCATTER_DENSITY_THRESHOLD + 1), true);
  assert.equal(shouldUseDensity(SCATTER_DENSITY_THRESHOLD + 1, { perItemChannels: true }), false);
  assert.equal(shouldUseDensity(10, { forceDensity: true }), true);
  assert.equal(shouldUseDensity(SCATTER_DENSITY_THRESHOLD * 2, { forceDirect: true }), false);
  assert.equal(shouldUseDensity(SCATTER_DENSITY_THRESHOLD * 2, { coords: "polar" }), false);
});

test("shouldUseDensity Boolean false stays auto unlike Python payload_force_density False", () => {
  // Python payload_force_density False → 0 (forced off). Node false → -1 (auto).
  assert.equal(shouldUseDensity(SCATTER_DENSITY_THRESHOLD + 1, { forceDensity: false }), true);
});

test("payloadTier polar line stays direct over M4 threshold", () => {
  assert.equal(payloadTier({ kind: 0, nPoints: 10_000 }), 0);
  assert.equal(payloadTier({ kind: 0, nPoints: 10_001 }), 1);
  assert.equal(payloadTier({ kind: 0, nPoints: 10_001, polar: true }), 0);
});

test("payloadM4Indices polar stays direct and cartesian matches m4 plus eps", () => {
  const n = 10_001;
  const x = fill(n, (i) => i);
  const y = fill(n, () => 1);
  const polar = payloadM4Indices({
    nPoints: n,
    x,
    y,
    x0: 0,
    x1: n - 1,
    nBuckets: 64,
    polar: true,
  });
  assert.equal(polar.tier, 0);
  assert.equal(polar.indices.length, 0);
  const cartesian = payloadM4Indices({
    nPoints: n,
    x,
    y,
    x0: 0,
    x1: n - 1,
    nBuckets: 64,
  });
  assert.equal(cartesian.tier, 1);
  assert.ok(cartesian.indices.length > 0);
});

test("payloadVisibleIndices keep-all vs log drop", () => {
  const x = new Float64Array([1, -2, 3, 0, 5]);
  const y = new Float64Array([1, 2, 3, 4, 5]);
  const linear = payloadVisibleIndices(x, y, { prefiltered: true });
  assert.equal(linear.keepAll, true);
  const logX = payloadVisibleIndices(x, y, { xLog: true, prefiltered: true });
  assert.equal(logX.keepAll, false);
  assert.deepEqual([...logX.indices], [0, 2, 4]);
});

test("validIndicesF64 keep-all vs filtered rows like Python", () => {
  assert.equal(validIndicesF64([new Float64Array([1, 2]), new Float64Array([3, 4])]), null);
  assert.equal(validIndicesF64([new Float64Array(0), new Float64Array(0)]), null);
  const filtered = validIndicesF64([
    new Float64Array([1, Number.NaN, 3, 4]),
    new Float64Array([1, 2, 3, Number.NaN]),
  ]);
  assert.deepEqual([...filtered], [0, 2]);
  assert.throws(() => validIndicesF64([]), /1 and 64/);
  assert.throws(
    () => validIndicesF64([new Float64Array([1, 2]), new Float64Array([3])]),
    /equal length/,
  );
});

test("rectFiniteSel drops nonfinite rows like Python _rect_finite_sel", () => {
  const geom = {
    kind: "bar",
    x0: [0, 1, 2],
    x1: [1, 2, 3],
    y0: [0, 0, 0],
    y1: [1, 2, 3],
  };
  assert.equal(rectFiniteSel(geom, geom.x0, geom.x1, geom.y0, geom.y1), null);
  const withNan = { ...geom, y1: [1, Number.NaN, 3] };
  assert.deepEqual(
    [...rectFiniteSel(withNan, withNan.x0, withNan.x1, withNan.y0, withNan.y1)],
    [0, 2],
  );
  const colorNan = {
    ...geom,
    color_ch: { mode: "continuous", values: [0.1, Number.NaN, 0.9] },
  };
  assert.deepEqual(
    [...rectFiniteSel(colorNan, colorNan.x0, colorNan.x1, colorNan.y0, colorNan.y1)],
    [0, 2],
  );
  const camel = {
    ...withNan,
    colorChannel: { mode: "continuous", values: [Number.NaN, Number.NaN, Number.NaN] },
  };
  assert.deepEqual(
    [...rectFiniteSel(camel, camel.x0, camel.x1, camel.y0, camel.y1)],
    [0, 2],
  );
  assert.throws(
    () => rectFiniteSel({ kind: "bar" }, [0], [1], [0], [1]),
    /missing rectangle columns/,
  );
  assert.throws(
    () => rectFiniteSel(
      { ...geom, color_ch: { mode: "continuous" } },
      geom.x0, geom.x1, geom.y0, geom.y1,
    ),
    /missing values/,
  );
  assert.throws(
    () => rectFiniteSel(
      { ...geom, color_ch: { mode: "categorical" } },
      geom.x0, geom.x1, geom.y0, geom.y1,
    ),
    /missing codes/,
  );
});

test("segments and bars drop nonfinite rows at emit", () => {
  const segments = figure({ width: 320, height: 240 });
  segments.segments([0, 1, 2], [0, 1, 2], [1, 2, 3], [1, Number.NaN, 3]);
  const seg = segments.buildPayload().spec.traces[0];
  assert.equal(seg.n_points, 3);
  assert.equal(seg.n_marks, 2);

  const bars = figure({ width: 320, height: 240 });
  bars.bar([0, 1, 2], [1, Number.NaN, 3]);
  const bar = bars.buildPayload().spec.traces[0];
  assert.equal(bar.kind, "bar");
  assert.equal(bar.n_marks, 2);
});

test("payloadEvenIndices matches numpy int64 linspace", () => {
  const keep = payloadEvenIndices(4, 10);
  assert.equal(keep.keepAll, true);
  const even = payloadEvenIndices(11, 4);
  assert.equal(even.keepAll, false);
  assert.deepEqual([...even.indices], [0, 3, 6, 10]);
});

test("payloadSegmentBudget matches host max(1024, floor(px)*4)", () => {
  assert.equal(payloadSegmentBudget(100), Math.max(1024, 100 * 4));
  assert.equal(payloadSegmentBudget(256), 1024);
  assert.equal(payloadSegmentBudget(257), 1028);
  assert.equal(payloadSegmentBudget(256.9), 1024);
  assert.equal(payloadSegmentBudget(0), 1024);
  assert.equal(payloadSegmentBudget(-10.7), 1024);
  assert.throws(() => payloadSegmentBudget(Number.NaN), /finite/);
});

test("payloadErrorbarIndices expands even keep across role groups", () => {
  const keep = payloadErrorbarIndices(33, 11, 20);
  assert.equal(keep.keepAll, true);
  const remainder = payloadErrorbarIndices(10, 3, 2);
  assert.equal(remainder.keepAll, true);
  const expanded = payloadErrorbarIndices(33, 11, 4);
  assert.equal(expanded.keepAll, false);
  assert.deepEqual([...expanded.indices], [0, 3, 6, 10, 11, 14, 17, 21, 22, 25, 28, 32]);
});

test("payloadSampleTargetIndices keep-all under target", () => {
  const small = payloadSampleTargetIndices({ n: 100, target: 8192 });
  assert.equal(small.keepAll, true);
  const sampled = payloadSampleTargetIndices({ n: 10_000, target: 8192 });
  assert.equal(sampled.keepAll, false);
  assert.ok(sampled.indices.length > 0 && sampled.indices.length < 10_000);
});

test("log scatter drops non-positive rows at emit", () => {
  const fig = figure({ width: 320, height: 240 });
  fig.setAxis("x", { type: "log" });
  fig.scatter([1, -2, 3, 0, 5], [1, 2, 3, 4, 5]);
  const { spec } = fig.buildPayload();
  assert.equal(spec.traces[0].tier, "direct");
  assert.equal(spec.traces[0].n_marks, 3);
});

test("polar line over DECIMATION_THRESHOLD stays direct at emit", () => {
  const n = 10_001;
  const x = fill(n, (i) => i);
  const y = fill(n, () => 1);
  const fig = figure({ coords: "polar", width: 640, height: 360 });
  fig.line(x, y);
  const { spec } = fig.buildPayload();
  assert.equal(spec.traces[0].tier, "direct");
  assert.equal(spec.traces[0].n_marks, n);
});

test("scatter force_density emits tier=density log-u8 grid", () => {
  const n = 2_048;
  const x = fill(n, (i) => (i % 64) / 63);
  const y = fill(n, (i) => Math.floor(i / 64) / 31);
  const fig = figure({ width: 320, height: 240 });
  fig.scatter(x, y, { forceDensity: true });
  const { spec, buffers } = fig.buildPayload();
  assert.equal(spec.protocol, PROTOCOL_VERSION);
  const t = spec.traces[0];
  assert.equal(t.kind, "scatter");
  assert.equal(t.tier, "density");
  assert.equal(t.n_points, n);
  assert.equal(t.n_marks, DENSITY_GRID[0] * DENSITY_GRID[1]);
  assert.ok(t.density);
  assert.equal(t.density.w, DENSITY_GRID[0]);
  assert.equal(t.density.h, DENSITY_GRID[1]);
  assert.equal(t.density.enc, "log-u8");
  assert.equal(typeof t.density.buf, "number");
  assert.ok(buffers.byteLength > 0);
});

test("scatter above SCATTER_DENSITY_THRESHOLD auto-selects density", () => {
  const n = SCATTER_DENSITY_THRESHOLD + 1;
  const x = fill(n, (i) => i / n);
  const y = fill(n, (i) => ((i * 7) % n) / n);
  const { spec } = scatterPayload(x, y);
  assert.equal(spec.traces[0].tier, "density");
  assert.equal(spec.traces[0].density.enc, "log-u8");
});

function scatterPayload(x, y) {
  const fig = figure({ width: 640, height: 360 });
  fig.scatter(x, y);
  return fig.buildPayload();
}

test("scatter force_direct stays direct even above threshold", () => {
  const n = SCATTER_DENSITY_THRESHOLD;
  const x = fill(n, (i) => i / n);
  const y = fill(n, (i) => ((i * 3) % n) / n);
  const fig = figure();
  fig.scatter(x, y, { forceDirect: true });
  const { spec } = fig.buildPayload();
  assert.equal(spec.traces[0].tier, "direct");
  assert.equal(spec.traces[0].n_marks, n);
});

test("_emitScatter still passes forceDirect unlike Python _emit_scatter", () => {
  // Python payload_tier omits force_direct (defaults false → density here).
  // Node still passes forceDirect so large forceDirect scatters stay direct.
  const n = SCATTER_DENSITY_THRESHOLD + 1;
  const x = fill(n, (i) => i / n);
  const y = fill(n, (i) => ((i * 3) % n) / n);
  const fig = figure();
  fig.scatter(x, y, { forceDirect: true });
  const { spec } = fig.buildPayload();
  assert.equal(spec.traces[0].tier, "direct");
  assert.equal(spec.traces[0].n_marks, n);
});

test("_emitScatter still ORs forcePyramid into density unlike Python _emit_scatter", () => {
  // Python Trace has no force_pyramid; `_emit_scatter` never densifies from it.
  // Node ORs forcePyramid into shouldUseDensity so small forcePyramid scatters densify.
  const n = 10_000;
  const x = fill(n, (i) => i / n);
  const y = fill(n, (i) => ((i * 3) % n) / n);
  const fig = figure({ width: 320, height: 240 });
  fig.scatter(x, y, { forcePyramid: true });
  const { spec } = fig.buildPayload();
  assert.equal(spec.traces[0].tier, "density");
  fig.dispose();
});

test("lodPlan returns exact vs density for Rust budgets", () => {
  const exact = lodPlan(1_000, SCATTER_DENSITY_THRESHOLD);
  assert.equal(exact.exact, true);
  const dense = lodPlan(SCATTER_DENSITY_THRESHOLD * 2, SCATTER_DENSITY_THRESHOLD);
  assert.equal(dense.exact, false);
  assert.ok(dense.gridW > 0 && dense.gridH > 0);
});

test("contourChart emits contour segments", () => {
  const z = [
    [0, 1, 2],
    [1, 2, 3],
    [2, 3, 4],
  ];
  const fig = contourChart(z, { levels: 3, width: 200, height: 160 });
  const { spec } = fig.buildPayload();
  assert.equal(spec.traces[0].kind, "contour");
  assert.ok(spec.traces[0].n_marks > 0);
});

test("errorbarChart emits errorbar segments", () => {
  const x = new Float64Array([0, 1, 2]);
  const y = new Float64Array([1, 2, 1.5]);
  const fig = errorbarChart(x, y, { yerr: 0.2 });
  const { spec } = fig.buildPayload();
  assert.ok(spec.traces.every((t) => t.kind === "errorbar"));
  assert.ok(spec.traces[0].n_marks >= 3);
});

test("errorBandChart emits error_band area geometry", () => {
  const x = new Float64Array([0, 1, 2, 3]);
  const lo = new Float64Array([0, 0.5, 0.2, 0.8]);
  const hi = new Float64Array([1, 1.5, 1.2, 1.8]);
  const fig = errorBandChart(x, lo, hi);
  const { spec } = fig.buildPayload();
  assert.equal(spec.traces[0].kind, "error_band");
  assert.ok(spec.traces[0].base != null);
});

test("stemChart emits stem segments + scatter heads", () => {
  const x = new Float64Array([0, 1, 2]);
  const y = new Float64Array([1, -0.5, 2]);
  const fig = stemChart(x, y);
  const { spec } = fig.buildPayload();
  const kinds = new Set(spec.traces.map((t) => t.kind));
  assert.ok(kinds.has("stem") || kinds.has("segments"));
  assert.ok(kinds.has("scatter"));
});

test("stepChart / stairsChart emit line with step style", () => {
  const x = new Float64Array([0, 1, 2, 3]);
  const y = new Float64Array([0, 1, 0, 1]);
  const step = stepChart(x, y).buildPayload().spec.traces[0];
  assert.equal(step.kind, "line");
  assert.ok(step.style.step);

  const edges = new Float64Array([0, 1, 2, 3, 4]);
  const vals = new Float64Array([1, 2, 1, 3]);
  const stairs = stairsChart(edges, vals).buildPayload().spec.traces[0];
  assert.equal(stairs.kind, "line");
  assert.ok(stairs.style.step);
});

test("triangleMeshChart emits triangle_mesh columns", () => {
  const x0 = new Float64Array([0, 1]);
  const y0 = new Float64Array([0, 0]);
  const x1 = new Float64Array([1, 2]);
  const y1 = new Float64Array([0, 0]);
  const x2 = new Float64Array([0.5, 1.5]);
  const y2 = new Float64Array([1, 1]);
  const { spec } = triangleMeshChart(x0, y0, x1, y1, x2, y2).buildPayload();
  assert.equal(spec.traces[0].kind, "triangle_mesh");
  assert.equal(spec.traces[0].n_marks, 2);
});

test("radarChart sets polar coords and area/line traces", () => {
  const cats = ["a", "b", "c", "d"];
  const series = [new Float64Array([1, 2, 1.5, 2.5])];
  const { spec } = radarChart(cats, series, { fill: true }).buildPayload();
  assert.equal(spec.coords, "polar");
  assert.ok(spec.traces.length >= 1);
  assert.ok(["area", "line"].includes(spec.traces[0].kind));
});

test("sankeyChart emits ribbon bands", () => {
  const nodes = ["A", "B", "C"];
  const links = [
    { source: "A", target: "B", value: 4 },
    { source: "B", target: "C", value: 2 },
  ];
  const { spec } = sankeyChart(nodes, links).buildPayload();
  assert.ok(spec.traces.some((t) => t.kind === "ribbon"));
});
