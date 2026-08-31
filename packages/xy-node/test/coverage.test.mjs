/**
 * Full mark-family coverage + density LOD for the Node host.
 * Complements marks.test.mjs (parity goldens) with end-to-end buildPayload checks.
 */
import assert from "node:assert/strict";
import test from "node:test";

import {
  DENSITY_GRID,
  DEFAULT_PALETTE,
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
import { composeScatter } from "../src/marks/scatter.js";

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

test("scatter force_direct ignored above threshold like Python _emit_scatter", () => {
  const n = SCATTER_DENSITY_THRESHOLD + 1;
  const x = fill(n, (i) => i / n);
  const y = fill(n, (i) => ((i * 3) % n) / n);
  const fig = figure();
  fig.scatter(x, y, { forceDirect: true });
  const { spec } = fig.buildPayload();
  assert.equal(spec.traces[0].tier, "density");
  assert.ok(spec.traces[0].density != null);
});

test("_emitScatter passes forceDirect false like Python _emit_scatter", () => {
  const n = SCATTER_DENSITY_THRESHOLD;
  const x = fill(n, (i) => i / n);
  const y = fill(n, (i) => ((i * 3) % n) / n);
  const fig = figure();
  fig.scatter(x, y, { forceDirect: true });
  const { spec } = fig.buildPayload();
  assert.equal(spec.traces[0].tier, "direct");
  assert.equal(spec.traces[0].n_marks, n);
});

test("_emitScatter ignores forcePyramid below threshold like Python _emit_scatter", () => {
  const n = 10_000;
  const x = fill(n, (i) => i / n);
  const y = fill(n, (i) => ((i * 3) % n) / n);
  const fig = figure({ width: 320, height: 240 });
  fig.scatter(x, y, { forcePyramid: true });
  const { spec } = fig.buildPayload();
  assert.equal(spec.traces[0].tier, "direct");
  assert.equal(spec.traces[0].n_marks, n);
  fig.dispose();
});

test("_emitScatterDensity colormap uses color_ch like Python _density_trace_spec", () => {
  const n = 10;
  const x = fill(n, (i) => i / n);
  const y = fill(n, (i) => ((i * 3) % n) / n);
  const fig = figure({ width: 320, height: 240 });
  fig.scatter(x, y, { forceDensity: true, colormap: "plasma" });
  fig.traces[0].color_ch = { ...fig.traces[0].color_ch, colormap: "magma" };
  const { spec } = fig.buildPayload();
  assert.equal(spec.traces[0].tier, "density");
  assert.equal(spec.traces[0].density.colormap, "magma");
});

test("_emitScatter ships animation via payload base-entry plan", () => {
  const fig = figure({ width: 240, height: 160 });
  fig.scatter([0, 1], [0, 1]);
  fig.traces[0].animation = { duration: 100 };
  const { spec } = fig.buildPayload();
  assert.equal(spec.traces[0].kind, "scatter");
  assert.deepEqual(spec.traces[0].animation, { duration: 100 });
});

test("_emitRibbon rejects tooltip_rows length mismatch", () => {
  const fig = figure({ width: 240, height: 160 });
  fig.ribbon([0], [1], [0], [1], [0], [1]);
  fig.traces[0].tooltip_rows = [{ id: "a" }, { id: "b" }];
  assert.throws(() => fig.buildPayload(), /tooltip rows must match geometry/);
});

test("_emitSegments rejects tooltip_rows length mismatch", () => {
  const fig = figure({ width: 240, height: 160 });
  fig.segments([0, 1], [0, 1], [1, 2], [1, 2]);
  fig.traces[0].tooltip_rows = [{ id: "a" }];
  assert.throws(() => fig.buildPayload(), /tooltip rows must match geometry/);
});

test("_emitScatter rejects tooltip_rows length mismatch", () => {
  const fig = figure({ width: 240, height: 160 });
  fig.scatter([0, 1], [0, 1]);
  fig.traces[0].tooltip_rows = [{ id: "a" }];
  assert.throws(() => fig.buildPayload(), /tooltip rows must match geometry/);
});

test("_emitRibbon uses _defaultStyled when style.color is missing", () => {
  const fig = figure({ width: 240, height: 160 });
  fig.ribbon([0], [1], [0], [1], [0], [1]);
  fig.traces[0].style = { opacity: 0.9 };
  const { spec } = fig.buildPayload();
  assert.equal(spec.traces[0].kind, "ribbon");
  assert.equal(
    spec.traces[0].style.color,
    DEFAULT_PALETTE[fig.traces[0].id % DEFAULT_PALETTE.length],
  );
  assert.equal(spec.traces[0].style.opacity, 0.9);
});

test("_emitSegments uses _defaultStyled when style.color is missing", () => {
  const fig = figure({ width: 240, height: 160 });
  fig.segments([0, 1], [0, 1], [1, 2], [1, 2]);
  fig.traces[0].style = { opacity: 0.9 };
  const { spec } = fig.buildPayload();
  assert.equal(spec.traces[0].kind, "segments");
  assert.equal(
    spec.traces[0].style.color,
    DEFAULT_PALETTE[fig.traces[0].id % DEFAULT_PALETTE.length],
  );
  assert.equal(spec.traces[0].style.opacity, 0.9);
});

test("_emitTriangleMesh uses _defaultStyled when style.color is missing", () => {
  const fig = figure({ width: 240, height: 160 });
  fig.triangleMesh([0], [0], [1], [0], [0.5], [1]);
  fig.traces[0].style = { opacity: 0.9 };
  const { spec } = fig.buildPayload();
  assert.equal(spec.traces[0].kind, "triangle_mesh");
  assert.equal(
    spec.traces[0].style.color,
    DEFAULT_PALETTE[fig.traces[0].id % DEFAULT_PALETTE.length],
  );
  assert.equal(spec.traces[0].style.opacity, 0.9);
});

test("_emitRect uses _defaultStyled when style.color is missing", () => {
  const fig = figure({ width: 240, height: 160 });
  fig.box([1, 2, 3, 4, 5]);
  const whiskerIdx = fig.traces.findIndex((t) => t.kind === "box_whisker");
  fig.traces[whiskerIdx].style = { opacity: 0.9 };
  const { spec } = fig.buildPayload();
  const whiskerTrace = spec.traces.find((t) => t.kind === "box_whisker");
  assert.equal(whiskerTrace.kind, "box_whisker");
  assert.equal(
    whiskerTrace.style.color,
    DEFAULT_PALETTE[fig.traces[whiskerIdx].id % DEFAULT_PALETTE.length],
  );
  assert.equal(whiskerTrace.style.opacity, 0.9);
});

test("_emitHistogram uses _defaultStyled when style.color is missing", () => {
  const fig = figure({ width: 240, height: 160 });
  fig.histogram([0, 1, 1, 2], { bins: 2, range: [0, 2] });
  fig.traces[0].style = { opacity: 0.9 };
  const { spec } = fig.buildPayload();
  assert.equal(spec.traces[0].kind, "histogram");
  assert.equal(
    spec.traces[0].style.color,
    DEFAULT_PALETTE[fig.traces[0].id % DEFAULT_PALETTE.length],
  );
  assert.equal(spec.traces[0].style.opacity, 0.9);
});

test("_emitHexbin uses _defaultStyled when style.color is missing", () => {
  const fig = figure({ width: 240, height: 160 });
  fig.hexbin([1, 2, 3, 4, 5], [1, 2, 1, 2, 1.5], { gridsize: 4 });
  fig.traces[0].style = { opacity: 0.9 };
  const { spec } = fig.buildPayload();
  assert.equal(spec.traces[0].kind, "hexbin");
  assert.equal(spec.traces[0].style.color, DEFAULT_PALETTE[fig.traces[0].id % DEFAULT_PALETTE.length]);
});

test("_emitArea uses _defaultStyled when style.color is missing", () => {
  const fig = figure({ width: 240, height: 160 });
  fig.area([0, 1], [0, 1]);
  fig.traces[0].style = { opacity: 0.9 };
  const { spec } = fig.buildPayload();
  assert.equal(spec.traces[0].kind, "area");
  assert.equal(
    spec.traces[0].style.color,
    DEFAULT_PALETTE[fig.traces[0].id % DEFAULT_PALETTE.length],
  );
  assert.equal(spec.traces[0].style.opacity, 0.9);
});

test("_emitLine uses _defaultStyled when style.color is missing", () => {
  const fig = figure({ width: 240, height: 160 });
  fig.line([0, 1], [0, 1]);
  fig.traces[0].style = { opacity: 0.9 };
  const { spec } = fig.buildPayload();
  assert.equal(spec.traces[0].kind, "line");
  assert.equal(spec.traces[0].style.color, DEFAULT_PALETTE[fig.traces[0].id % DEFAULT_PALETTE.length]);
  assert.equal(spec.traces[0].style.opacity, 0.9);
});

test("buildPayload ships cartesian axis label like Python _axis_spec", () => {
  const fig = figure({ width: 240, height: 160 });
  fig.scatter([0, 1], [0, 1]);
  const { spec } = fig.buildPayload();
  assert.equal(spec.x_axis.label, null);
});

test("buildPayload ships cartesian axis side like Python _axis_spec", () => {
  const fig = figure({ width: 240, height: 160 });
  fig.scatter([0, 1], [0, 1]);
  const { spec } = fig.buildPayload();
  assert.equal(spec.x_axis.side, "bottom");
  assert.equal(spec.y_axis.side, "left");
});

test("buildPayload ships cartesian axis kind like Python _axis_spec", () => {
  const fig = figure({ width: 240, height: 160 });
  fig.scatter([0, 1], [0, 1]);
  const { spec } = fig.buildPayload();
  assert.equal(spec.x_axis.kind, "linear");
  assert.equal(spec.y_axis.kind, "linear");
});

test("buildPayload ships cartesian axis id like Python _axis_spec", () => {
  const fig = figure({ width: 240, height: 160 });
  fig.scatter([0, 1], [0, 1]);
  const { spec } = fig.buildPayload();
  assert.equal(spec.x_axis.id, "x");
  assert.equal(spec.y_axis.id, "y");
});

test("buildPayload ships show_legend via payload build plan", () => {
  const fig = figure({ width: 240, height: 160, showLegend: false });
  fig.scatter([0, 1], [0, 1]);
  const { spec } = fig.buildPayload();
  assert.equal(fig.show_legend, false);
  assert.equal(spec.show_legend, false);
});

test("buildPayload ships wasm_density automatic on split density with wasm_source", () => {
  const fig = figure({ width: 240, height: 160 });
  fig.scatter([1, 10], [1, 10], { forceDensity: true });
  const { spec } = fig.buildPayload({ split: true });
  assert.equal(spec.traces[0].tier, "density");
  assert.notEqual(spec.traces[0].density.wasm_source, undefined);
  assert.equal(spec.wasm_density.automatic, true);
  assert.equal(spec.wasm_density.source, spec.traces[0].density.wasm_source);
});

test("buildPayload omits linear axis scale like Python _axis_spec", () => {
  const fig = figure({ width: 240, height: 160 });
  fig.scatter([1, 10], [1, 10]);
  const { spec } = fig.buildPayload();
  assert.equal(spec.x_axis.scale, undefined);
  assert.equal(spec.y_axis.scale, undefined);
});

test("buildPayload ships non-linear axis scale like Python _axis_spec", () => {
  const fig = figure({ width: 240, height: 160 });
  fig.setAxis("x", { type: "log" });
  fig.scatter([1, 10], [1, 10]);
  const { spec } = fig.buildPayload();
  assert.equal(spec.x_axis.scale, "log");
  assert.equal(spec.y_axis.scale, undefined);
});

test("_emitScatterDensity ships wasm_source on split via registry plan", () => {
  const fig = figure({ width: 240, height: 160 });
  fig.scatter([1, 10], [1, 10], { forceDensity: true });
  const { spec } = fig.buildPayload({ split: true });
  assert.equal(spec.traces[0].tier, "density");
  const wasmSource = spec.traces[0].density.wasm_source;
  assert.notEqual(wasmSource, undefined);
  assert.equal(wasmSource.kind, "cartesian-count-f64-stream-v1");
  assert.equal(wasmSource.point_count, 2);
  assert.equal(wasmSource.trace_id, fig.traces[0].id);
  assert.equal(wasmSource.capacity, 8_000_000);
  assert.equal(wasmSource.ownership, "retain-host-replay");
  assert.equal(typeof wasmSource.x, "number");
  assert.equal(typeof wasmSource.y, "number");
  assert.equal(spec.columns[wasmSource.x].dtype, "f64");
  assert.equal(spec.columns[wasmSource.y].dtype, "f64");
});

test("_emitScatterDensity omits wasm_source on unsplit payloads", () => {
  const fig = figure({ width: 240, height: 160 });
  fig.scatter([1, 10], [1, 10], { forceDensity: true });
  const { spec } = fig.buildPayload();
  assert.equal(spec.traces[0].density.wasm_source, undefined);
});

test("_emitScatterDensity sample uses log ship scale via payload nonxy plan", () => {
  const fig = figure({ width: 240, height: 160 });
  fig.setAxis("x", { type: "log" });
  fig.scatter([1, 10], [1, 10], { forceDensity: true });
  const { spec } = fig.buildPayload();
  assert.equal(spec.traces[0].tier, "density");
  assert.equal(spec.traces[0].density.sample.x.offset, 0);
});

test("_emitHistogram uses log ship scale via payload bar-hist plan", () => {
  const fig = figure({ width: 240, height: 160 });
  fig.setAxis("x", { type: "log" });
  fig.histogram([1, 2, 10], { bins: 2, range: [1, 10] });
  const { spec } = fig.buildPayload();
  assert.equal(spec.traces[0].kind, "histogram");
  const x0Col = spec.columns[spec.traces[0].x0];
  assert.equal(x0Col.offset, 0);
});

test("_emitTriangleMesh uses log ship scale via payload mesh plan", () => {
  const fig = figure({ width: 240, height: 160 });
  fig.setAxis("x", { type: "log" });
  fig.triangleMesh([1], [1], [10], [1], [5], [10]);
  const { spec } = fig.buildPayload();
  assert.equal(spec.traces[0].kind, "triangle_mesh");
  const x0Col = spec.columns[spec.traces[0].x0];
  assert.equal(x0Col.offset, 0);
});

test("_emitRibbon uses log ship scale via payload ribbon plan", () => {
  const fig = figure({ width: 240, height: 160 });
  fig.setAxis("x", { type: "log" });
  fig.ribbon([1], [10], [1], [10], [1], [10]);
  const { spec } = fig.buildPayload();
  assert.equal(spec.traces[0].kind, "ribbon");
  const x0Col = spec.columns[spec.traces[0].x0];
  assert.equal(x0Col.offset, 0);
});

test("_emitSegments uses log ship scale via payload segments plan", () => {
  const fig = figure({ width: 240, height: 160 });
  fig.setAxis("x", { type: "log" });
  fig.segments([1, 10], [1, 10], [2, 20], [2, 20]);
  const { spec } = fig.buildPayload();
  assert.equal(spec.traces[0].kind, "segments");
  const x0Col = spec.columns[spec.traces[0].x0];
  assert.equal(x0Col.offset, 0);
});

test("_emitRect uses log ship scale via payload nonxy plan", () => {
  const fig = figure({ width: 240, height: 160 });
  fig.setAxis("x", { type: "log" });
  fig.box([1, 2, 3, 4, 5]);
  const { spec } = fig.buildPayload();
  const boxTrace = spec.traces.find((t) => t.kind === "box");
  assert.equal(boxTrace.kind, "box");
  const x0Col = spec.columns[boxTrace.x0];
  assert.equal(x0Col.offset, 0);
});

test("_emitHexbin uses log ship scale via payload nonxy plan", () => {
  const fig = figure({ width: 240, height: 160 });
  fig.setAxis("x", { type: "log" });
  fig.hexbin([1, 2, 3, 4, 5], [1, 2, 1, 2, 1.5], { gridsize: 4 });
  const { spec } = fig.buildPayload();
  assert.equal(spec.traces[0].kind, "hexbin");
  const xCol = spec.columns[spec.traces[0].x];
  assert.equal(xCol.offset, 0);
});

test("_emitArea uses log ship scale via payload base-entry plan", () => {
  const fig = figure({ width: 240, height: 160 });
  fig.setAxis("x", { type: "log" });
  fig.area([1, 10], [1, 10]);
  const { spec } = fig.buildPayload();
  assert.equal(spec.traces[0].kind, "area");
  const xCol = spec.columns[spec.traces[0].x];
  assert.equal(xCol.offset, 0);
});

test("_emitLine uses log ship scale via payload base-entry plan", () => {
  const fig = figure({ width: 240, height: 160 });
  fig.setAxis("x", { type: "log" });
  fig.line([1, 10], [1, 10]);
  const { spec } = fig.buildPayload();
  assert.equal(spec.traces[0].kind, "line");
  const xCol = spec.columns[spec.traces[0].x];
  assert.equal(xCol.offset, 0);
});

test("_emitScatter uses log ship scale via payload base-entry plan", () => {
  const fig = figure({ width: 240, height: 160 });
  fig.setAxis("x", { type: "log" });
  fig.scatter([1, 10], [1, 10]);
  const { spec } = fig.buildPayload();
  assert.equal(spec.traces[0].tier, "direct");
  const xCol = spec.columns[spec.traces[0].x];
  assert.equal(xCol.offset, 0);
});

test("_emitScatterDensity ships mean-color rgba for categorical color like Python", () => {
  const fig = figure({ width: 240, height: 160 });
  fig.scatter([0, 1, 2, 3, 4], [0, 1, 0.5, 0.2, 0.8], {
    forceDensity: true,
    color: ["a", "b", "a", "c", "b"],
    size: [1, 2, 3, 4, 5],
  });
  const { spec } = fig.buildPayload();
  const density = spec.traces[0].density;
  assert.equal(spec.traces[0].tier, "density");
  assert.equal(density.color_agg, "mean");
  assert.equal(density.channels_dropped, true);
  assert.deepEqual(density.dropped_channels, ["size"]);
  assert.ok(density.rgba != null);
});

test("_emitScatterDensity dropped_channels lists per_item extras like Python", () => {
  const fig = figure({ width: 320, height: 240 });
  fig.scatter([0, 1, 2], [0, 1, 0.5], { forceDensity: true, size: [1, 2, 3] });
  const { spec } = fig.buildPayload();
  assert.equal(spec.traces[0].tier, "density");
  assert.equal(spec.traces[0].density.channels_dropped, true);
  assert.deepEqual(spec.traces[0].density.dropped_channels, ["size"]);
});

test("_emitHeatmap ships nested rgba_bufs like Python _emit_heatmap", () => {
  const fig = figure({ width: 240, height: 160 });
  fig.heatmap([[0, 1], [1, 0]], {
    colormapStops: Uint8Array.from([0, 0, 255, 255, 255, 255, 255, 0, 0]),
  });
  fig.traces[0].rgba_grid = [{ values: [1, 0, 0, 1] }];
  const { spec } = fig.buildPayload();
  assert.equal(spec.traces[0].kind, "heatmap");
  assert.ok(Array.isArray(spec.traces[0].heatmap.rgba_bufs));
  assert.equal(spec.traces[0].heatmap.rgba_bufs.length, 1);
  assert.equal(spec.traces[0].rgba_len, undefined);
});

test("_emitHeatmap attaches color like Python _emit_heatmap", () => {
  const fig = figure({ width: 240, height: 160 });
  fig.heatmap([[0, 1], [1, 0]], { colormap: "viridis" });
  const { spec } = fig.buildPayload();
  assert.equal(spec.traces[0].kind, "heatmap");
  assert.equal(spec.traces[0].color.mode, "continuous");
  assert.equal(spec.traces[0].color.colormap, "viridis");
});

test("_emitScatter ships size_ch like Python _emit_scatter", () => {
  const fig = figure({ width: 240, height: 160 });
  fig.scatter([0, 1], [0, 1], {
    _composed: true,
    sizeValues: [4, 8],
  });
  fig.traces[0].size_ch = { mode: "constant", constant: 12 };
  const { spec } = fig.buildPayload();
  assert.equal(spec.traces[0].tier, "direct");
  assert.equal(spec.traces[0].size.mode, "constant");
  assert.equal(spec.traces[0].size.size, 12);
});

test("_emitScatterDensity sample ships style_channels via payload channel attach", () => {
  const fig = figure({ width: 320, height: 240 });
  fig.scatter([0, 1, 2], [0, 1, 0.5], { forceDensity: true });
  fig.traces[0].style_channels = {
    opacity: {
      mode: "direct",
      values: new Float64Array([0.5, 0.6, 0.7]),
      components: 1,
      dtype: "f32",
    },
  };
  const { spec } = fig.buildPayload();
  assert.equal(spec.traces[0].tier, "density");
  assert.notEqual(spec.traces[0].density.sample, undefined);
  assert.equal(spec.traces[0].density.sample.channels.opacity.mode, "direct");
  assert.equal(spec.traces[0].density.sample.channels.opacity.n, 3);
});

test("_emitScatterDensity sample ships stroke arrays via stroke_ch resolution", () => {
  const fig = figure({ width: 320, height: 240 });
  fig.scatter([0, 1, 2], [0, 1, 0.5], {
    forceDensity: true,
    stroke: ["#f00", "#0f0", "#00f"],
  });
  const { spec } = fig.buildPayload();
  assert.equal(spec.traces[0].tier, "density");
  assert.notEqual(spec.traces[0].density.sample, undefined);
  assert.equal(spec.traces[0].density.sample.stroke.mode, "direct_rgba");
  assert.equal(spec.traces[0].density.sample.stroke.n, 3);
});

test("_emitScatterDensity sample ships stroke_ch via payload channel attach", () => {
  const fig = figure({ width: 320, height: 240 });
  fig.scatter([0, 1], [0, 1], { forceDensity: true });
  fig.traces[0].stroke_ch = { mode: "constant", constant: "#112233" };
  const { spec } = fig.buildPayload();
  assert.equal(spec.traces[0].tier, "density");
  assert.notEqual(spec.traces[0].density.sample, undefined);
  assert.equal(spec.traces[0].density.sample.stroke.color, "#112233");
});

test("_emitScatterDensity sample ships size_ch via payload channel attach", () => {
  const fig = figure({ width: 320, height: 240 });
  fig.scatter([0, 1], [0, 1], { forceDensity: true });
  fig.traces[0].size_ch = { mode: "constant", constant: 8 };
  const { spec } = fig.buildPayload();
  assert.equal(spec.traces[0].tier, "density");
  assert.notEqual(spec.traces[0].density.sample, undefined);
  assert.equal(spec.traces[0].density.sample.size.size, 8);
});

test("_emitScatterDensity sample ships color_ch via payload channel attach", () => {
  const fig = figure({ width: 320, height: 240 });
  fig.scatter([0, 1], [0, 1], { forceDensity: true });
  fig.traces[0].color_ch = { mode: "constant", constant: "#112233" };
  const { spec } = fig.buildPayload();
  assert.equal(spec.traces[0].tier, "density");
  assert.notEqual(spec.traces[0].density.sample, undefined);
  assert.equal(spec.traces[0].density.sample.color.color, "#112233");
});

test("_emitScatterDensity ships animation_fallback via payload transition attach", () => {
  const fig = figure({ width: 320, height: 240 });
  fig.scatter([0, 1], [0, 1], { forceDensity: true });
  fig.traces[0].transition_keys = [
    [1, 2],
    [3, 4],
  ];
  const { spec } = fig.buildPayload();
  assert.equal(spec.traces[0].tier, "density");
  assert.equal(spec.traces[0].keys, undefined);
  assert.equal(spec.traces[0].animation_fallback, "snap:aggregate");
});

test("_emitHistogram ships transition_keys via payload bar-hist plan", () => {
  const fig = figure({ width: 240, height: 160 });
  fig.histogram([0, 1, 1, 2], { bins: 2, range: [0, 2] });
  fig.traces[0].transition_keys = [
    [1, 2],
    [3, 4],
  ];
  const { spec } = fig.buildPayload();
  assert.equal(spec.traces[0].kind, "histogram");
  assert.notEqual(spec.traces[0].keys, undefined);
});

test("_emitSegments ships transition_keys via payload segments plan", () => {
  const fig = figure({ width: 240, height: 160 });
  fig.segments([0], [0], [1], [1]);
  fig.traces[0].transition_keys = [[1, 2]];
  const { spec } = fig.buildPayload();
  assert.equal(spec.traces[0].kind, "segments");
  assert.notEqual(spec.traces[0].keys, undefined);
});

test("_emitTriangleMesh ships transition_keys via payload mesh plan", () => {
  const fig = figure({ width: 240, height: 160 });
  fig.triangleMesh([0], [0], [1], [0], [0.5], [1]);
  fig.traces[0].transition_keys = [[1, 2]];
  const { spec } = fig.buildPayload();
  assert.equal(spec.traces[0].kind, "triangle_mesh");
  assert.notEqual(spec.traces[0].keys, undefined);
});

test("_emitRibbon ships transition_keys via payload ribbon plan", () => {
  const fig = figure({ width: 240, height: 160 });
  fig.ribbon([0], [1], [0], [1], [0], [1], { color: "#112233" });
  fig.traces[0].transition_keys = [[1, 2]];
  const { spec } = fig.buildPayload();
  assert.equal(spec.traces[0].kind, "ribbon");
  assert.notEqual(spec.traces[0].keys, undefined);
});

test("_emitRect ships transition_keys via payload nonxy plan", () => {
  const fig = figure({ width: 240, height: 160 });
  fig.bar([0, 1], [1, 2]);
  fig.traces[0].transition_keys = [
    [1, 2],
    [3, 4],
  ];
  const { spec } = fig.buildPayload();
  assert.equal(spec.traces[0].kind, "bar");
  assert.notEqual(spec.traces[0].keys, undefined);
});

test("_emitTriangleMesh gathers null geometry rows via payload mesh plan", () => {
  const fig = figure({ width: 240, height: 160 });
  fig.triangleMesh([0, 1], [0, 0], [1, 2], [0, 0], [0.5, 1.5], [1, 1]);
  const n = fig.traces[0].x0.length;
  fig.traces[0].x0[0] = Number.NaN;
  const { spec } = fig.buildPayload();
  assert.equal(spec.traces[0].kind, "triangle_mesh");
  assert.equal(spec.traces[0].n_marks, n - 1);
});

test("_emitRibbon gathers null geometry rows via payload ribbon plan", () => {
  const fig = figure({ width: 240, height: 160 });
  fig.ribbon([0, 1], [1, 2], [0, 0], [1, 1], [0, 0], [1, 1], { color: "#112233" });
  const n = fig.traces[0].x0.length;
  fig.traces[0].x0[0] = Number.NaN;
  const { spec } = fig.buildPayload();
  assert.equal(spec.traces[0].kind, "ribbon");
  assert.equal(spec.traces[0].n_marks, n - 1);
});

test("_emitBarCompact ships nested bar spec like Python _emit_bar_compact", () => {
  const fig = figure({ width: 240, height: 160 });
  fig.bar([0, 1], [1, 2]);
  const { spec } = fig.buildPayload();
  assert.equal(spec.traces[0].kind, "bar");
  assert.notEqual(spec.traces[0].bar, undefined);
  assert.equal(spec.traces[0].bar.orientation, "vertical");
  assert.equal(spec.traces[0].bar.value_axis, "y");
  assert.equal(spec.traces[0].x0, undefined);
});

test("_emitHistogram drops non-finite bins via rectFiniteSel like Python _emit_rect", () => {
  const fig = figure({ width: 240, height: 160 });
  fig.traces.push({
    kind: "histogram",
    id: 17,
    name: null,
    x0: new Float64Array([0, 1]),
    x1: new Float64Array([1, 2]),
    y0: new Float64Array([0, 0]),
    y1: new Float64Array([1, Number.NaN]),
    style: { color: "#3987e5", opacity: 0.85, role: "histogram" },
    count: 4,
  });
  const { spec } = fig.buildPayload();
  assert.equal(spec.traces[0].kind, "histogram");
  assert.equal(spec.traces[0].n_marks, 1);
});

test("_emitArea ships transition_keys via payload transition attach", () => {
  const fig = figure({ width: 240, height: 160 });
  fig.area([0, 1], [0, 1]);
  fig.traces[0].transition_keys = [
    [1, 2],
    [3, 4],
  ];
  const { spec } = fig.buildPayload();
  assert.equal(spec.traces[0].kind, "area");
  assert.ok(spec.traces[0].keys);
  assert.equal(spec.columns[spec.traces[0].keys.lo].dtype, "u32");
});

test("_emitLine ships transition_keys via payload transition attach", () => {
  const fig = figure({ width: 240, height: 160 });
  fig.line([0, 1], [0, 1]);
  fig.traces[0].transition_keys = [
    [1, 2],
    [3, 4],
  ];
  const { spec } = fig.buildPayload();
  assert.equal(spec.traces[0].kind, "line");
  assert.ok(spec.traces[0].keys);
  assert.equal(spec.columns[spec.traces[0].keys.lo].dtype, "u32");
});

test("_emitScatter ships transition_keys via payload transition attach", () => {
  const fig = figure({ width: 240, height: 160 });
  fig.scatter([0, 1], [0, 1]);
  fig.traces[0].transition_keys = [
    [1, 2],
    [3, 4],
  ];
  const { spec } = fig.buildPayload();
  assert.equal(spec.traces[0].tier, "direct");
  assert.ok(spec.traces[0].keys);
  assert.equal(spec.columns[spec.traces[0].keys.lo].dtype, "u32");
});

test("_emitHistogram ships constant style_channels via shipStyleChannels", () => {
  const fig = figure({ width: 240, height: 160 });
  fig.histogram([0, 1, 1, 2], { bins: 2, range: [0, 2] });
  fig.traces[0].style_channels = { stroke_width: { mode: "constant", constant: 2 } };
  const { spec } = fig.buildPayload();
  assert.equal(spec.traces[0].kind, "histogram");
  assert.equal(spec.traces[0].channels.stroke_width.mode, "direct");
  assert.equal(spec.traces[0].channels.stroke_width.n, 2);
});

test("_emitSegments ships constant style_channels via shipStyleChannels", () => {
  const fig = figure({ width: 240, height: 160 });
  fig.segments([0], [0], [1], [1]);
  fig.traces[0].style_channels = { stroke_width: { mode: "constant", constant: 2 } };
  const { spec } = fig.buildPayload();
  assert.equal(spec.traces[0].kind, "segments");
  assert.equal(spec.traces[0].channels.stroke_width.mode, "direct");
  assert.equal(spec.traces[0].channels.stroke_width.n, 1);
});

test("_emitTriangleMesh ships constant style_channels via shipStyleChannels", () => {
  const fig = figure({ width: 240, height: 160 });
  fig.triangleMesh([0], [0], [1], [0], [0.5], [1]);
  fig.traces[0].style_channels = { stroke_width: { mode: "constant", constant: 2 } };
  const { spec } = fig.buildPayload();
  assert.equal(spec.traces[0].kind, "triangle_mesh");
  assert.equal(spec.traces[0].channels.stroke_width.mode, "direct");
  assert.equal(spec.traces[0].channels.stroke_width.n, 1);
});

test("_emitRect ships constant style_channels via shipStyleChannels", () => {
  const fig = figure({ width: 240, height: 160 });
  fig.bar([0, 1], [1, 2]);
  fig.traces[0].style_channels = { stroke_width: { mode: "constant", constant: 2 } };
  const { spec } = fig.buildPayload();
  assert.equal(spec.traces[0].kind, "bar");
  assert.equal(spec.traces[0].channels.stroke_width.mode, "direct");
  assert.equal(spec.traces[0].channels.stroke_width.n, 2);
});

test("_emitRibbon ships constant style_channels via shipStyleChannels", () => {
  const fig = figure({ width: 240, height: 160 });
  fig.ribbon([0], [1], [0], [1], [0], [1], { color: "#112233" });
  fig.traces[0].style_channels = { stroke_width: { mode: "constant", constant: 2 } };
  const { spec } = fig.buildPayload();
  assert.equal(spec.traces[0].kind, "ribbon");
  assert.equal(spec.traces[0].channels.stroke_width.mode, "direct");
  assert.equal(spec.traces[0].channels.stroke_width.n, 1);
});

test("_emitScatter ships style_channels like Python _ship_trace_styles", () => {
  const fig = figure({ width: 240, height: 160 });
  fig.scatter([0, 1], [0, 1]);
  fig.traces[0].style_channels = { stroke_width: { values: [2, 3] } };
  const { spec } = fig.buildPayload();
  assert.equal(spec.traces[0].tier, "direct");
  assert.equal(spec.traces[0].channels.stroke_width.mode, "direct");
  assert.equal(spec.traces[0].channels.stroke_width.n, 2);
});

test("_emitHistogram ships stroke_ch via payload channel attach", () => {
  const fig = figure({ width: 240, height: 160 });
  fig.histogram([0, 1, 1, 2], { bins: 2, range: [0, 2] });
  fig.traces[0].stroke_ch = { mode: "constant", constant: "#112233" };
  const { spec } = fig.buildPayload();
  assert.equal(spec.traces[0].kind, "histogram");
  assert.equal(spec.traces[0].stroke.color, "#112233");
});

test("_emitSegments ships stroke_ch via payload channel attach", () => {
  const fig = figure({ width: 240, height: 160 });
  fig.segments([0], [0], [1], [1]);
  fig.traces[0].stroke_ch = { mode: "constant", constant: "#112233" };
  const { spec } = fig.buildPayload();
  assert.equal(spec.traces[0].kind, "segments");
  assert.equal(spec.traces[0].stroke.color, "#112233");
});

test("_emitTriangleMesh ships stroke_ch via payload channel attach", () => {
  const fig = figure({ width: 240, height: 160 });
  fig.triangleMesh([0], [0], [1], [0], [0.5], [1]);
  fig.traces[0].stroke_ch = { mode: "constant", constant: "#112233" };
  const { spec } = fig.buildPayload();
  assert.equal(spec.traces[0].kind, "triangle_mesh");
  assert.equal(spec.traces[0].stroke.color, "#112233");
});

test("_emitRect ships stroke_ch via payload channel attach", () => {
  const fig = figure({ width: 240, height: 160 });
  fig.bar([0, 1], [1, 2]);
  fig.traces[0].stroke_ch = { mode: "constant", constant: "#112233" };
  const { spec } = fig.buildPayload();
  assert.equal(spec.traces[0].kind, "bar");
  assert.equal(spec.traces[0].stroke.color, "#112233");
});

test("_emitRibbon ships stroke_ch via payload channel attach", () => {
  const fig = figure({ width: 240, height: 160 });
  fig.ribbon([0], [1], [0], [1], [0], [1], { color: "#112233" });
  fig.traces[0].stroke_ch = { mode: "constant", constant: "#445566" };
  const { spec } = fig.buildPayload();
  assert.equal(spec.traces[0].kind, "ribbon");
  assert.equal(spec.traces[0].stroke.color, "#445566");
});

test("_emitScatter ships stroke_ch like Python _ship_trace_styles", () => {
  const fig = figure({ width: 240, height: 160 });
  fig.scatter([0, 1], [0, 1]);
  fig.traces[0].stroke_ch = { mode: "constant", constant: "#112233" };
  const { spec } = fig.buildPayload();
  assert.equal(spec.traces[0].tier, "direct");
  assert.equal(spec.traces[0].stroke.color, "#112233");
});

test("_emitTriangleMesh ships x2/y2 via payload column ship registry", () => {
  const fig = figure({ width: 240, height: 160 });
  fig.triangleMesh([0], [0], [1], [0], [0.5], [1]);
  const { spec } = fig.buildPayload();
  assert.equal(spec.traces[0].kind, "triangle_mesh");
  assert.ok(spec.traces[0].x2 != null);
  assert.ok(spec.traces[0].y2 != null);
  assert.equal(spec.traces[0].x, undefined);
  assert.equal(spec.traces[0].y, undefined);
});

test("_emitHistogram ships color_ch via payload channel attach", () => {
  const fig = figure({ width: 240, height: 160 });
  fig.histogram([0, 1, 1, 2], { bins: 2, range: [0, 2] });
  fig.traces[0].color_ch = { mode: "constant", constant: "#112233" };
  const { spec } = fig.buildPayload();
  assert.equal(spec.traces[0].kind, "histogram");
  assert.equal(spec.traces[0].color.color, "#112233");
});

test("_emitTriangleMesh ships color_ch via payload channel attach", () => {
  const fig = figure({ width: 240, height: 160 });
  fig.triangleMesh([0], [0], [1], [0], [0.5], [1]);
  fig.traces[0].color_ch = { mode: "constant", constant: "#112233" };
  const { spec } = fig.buildPayload();
  assert.equal(spec.traces[0].kind, "triangle_mesh");
  assert.equal(spec.traces[0].color.color, "#112233");
});

test("_emitSegments ships color_ch like Python _emit_segments", () => {
  const fig = figure({ width: 240, height: 160 });
  fig.segments([0], [0], [1], [1], {
    color: { mode: "constant", constant: "#112233" },
  });
  fig.traces[0].color_ch = { mode: "constant", constant: "#445566" };
  const { spec } = fig.buildPayload();
  assert.equal(spec.traces[0].kind, "segments");
  assert.equal(spec.traces[0].color.color, "#445566");
});

test("_emitRect ships color_ch like Python _emit_rect", () => {
  const fig = figure({ width: 240, height: 160 });
  fig.bar([0, 1], [1, 2], { color: "#112233" });
  fig.traces[0].color_ch = { mode: "constant", constant: "#445566" };
  const { spec } = fig.buildPayload();
  assert.equal(spec.traces[0].kind, "bar");
  assert.equal(spec.traces[0].color.color, "#445566");
});

test("_emitRibbon ships color_ch via payload channel attach", () => {
  // Node `_emitRibbon` ships color_ch like Python after gather/ship registry parity (#770).
  const fig = figure({ width: 240, height: 160 });
  fig.ribbon([0], [1], [0], [1], [0], [1], { color: "#112233" });
  fig.traces[0].color_ch = { mode: "constant", constant: "#445566" };
  const { spec } = fig.buildPayload();
  assert.equal(spec.traces[0].kind, "ribbon");
  assert.equal(spec.traces[0].color.color, "#445566");
});

test("_emitRibbon ships t.color_target unlike Python color2_ch", () => {
  // Python `_emit_ribbon` ships color2_ch. Node keeps t.color_target even when
  // color2_ch differs. Recorded ribbon-color-target stay-host.
  const fig = figure({ width: 240, height: 160 });
  fig.ribbon([0], [1], [0], [1], [0], [1], { color: "#112233", colorTarget: "#445566" });
  fig.traces[0].color2_ch = { mode: "constant", constant: "#778899" };
  const { spec } = fig.buildPayload();
  assert.equal(spec.traces[0].kind, "ribbon");
  assert.equal(spec.traces[0].color_target.color, "#445566");
});

test("_emitScatter ships color_ch like Python _emit_scatter", () => {
  const fig = figure({ width: 240, height: 160 });
  fig.scatter([0, 1], [0, 1], {
    _composed: true,
    color: { mode: "constant", constant: "#112233" },
  });
  fig.traces[0].color_ch = { mode: "constant", constant: "#445566" };
  const { spec } = fig.buildPayload();
  assert.equal(spec.traces[0].tier, "direct");
  assert.equal(spec.traces[0].color.color, "#445566");
});

test("_emitHeatmap ships nested heatmap spec like Python _emit_heatmap", () => {
  const fig = figure({ width: 240, height: 160 });
  fig.heatmap([[0, 1], [1, 0]], { colormap: "viridis" });
  const { spec } = fig.buildPayload();
  assert.equal(spec.traces[0].kind, "heatmap");
  assert.ok(spec.traces[0].heatmap != null);
  assert.equal(spec.traces[0].heatmap.w, 2);
  assert.equal(spec.traces[0].heatmap.h, 2);
  assert.equal(spec.traces[0].grid, undefined);
  assert.equal(spec.traces[0].x, undefined);
});

test("_emitHexbin ships color and size via payload channel attach", () => {
  const fig = figure({ width: 240, height: 160 });
  fig.hexbin([0, 1, 0, 1, 0.5], [0, 0, 1, 1, 0.5], { gridsize: 4 });
  const { spec } = fig.buildPayload();
  assert.equal(spec.traces[0].kind, "hexbin");
  assert.equal(spec.traces[0].metric, undefined);
  assert.notEqual(spec.traces[0].color, undefined);
  assert.deepEqual(spec.traces[0].size, { mode: "constant", size: 8 });
  assert.ok(fig.traces[0].color_ch != null);
});

test("_emitScatterDensity defers style color when color_ch is continuous without values", () => {
  // Python `_density_trace_spec` uses color_ch when values/domain are present.
  // Continuous color_ch without values stays off the density color path on both hosts.
  const n = 10;
  const x = fill(n, (i) => i / n);
  const y = fill(n, (i) => ((i * 3) % n) / n);
  const fig = figure({ width: 320, height: 240 });
  fig.scatter(x, y, { forceDensity: true, style: { color: "#112233" } });
  fig.traces[0].color_ch = { mode: "continuous", colormap: "magma" };
  const { spec } = fig.buildPayload();
  assert.equal(spec.traces[0].tier, "density");
  assert.equal(spec.traces[0].density.color, undefined);
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

test("_emitLine ships animation via payload base-entry plan", () => {
  const fig = figure({ width: 240, height: 160 });
  fig.line([0, 1], [0, 1]);
  fig.traces[0].animation = { duration: 100 };
  const { spec } = fig.buildPayload();
  assert.equal(spec.traces[0].kind, "line");
  assert.deepEqual(spec.traces[0].animation, { duration: 100 });
});

test("_emitArea ships animation via payload base-entry plan", () => {
  const fig = figure({ width: 240, height: 160 });
  fig.area([0, 1], [0, 1]);
  fig.traces[0].animation = { duration: 100 };
  const { spec } = fig.buildPayload();
  assert.equal(spec.traces[0].kind, "area");
  assert.deepEqual(spec.traces[0].animation, { duration: 100 });
});

test("_emitHistogram ships animation via payload bar-hist plan", () => {
  const fig = figure({ width: 240, height: 160 });
  fig.histogram([0, 1, 1, 2], { bins: 2, range: [0, 2] });
  fig.traces[0].animation = { duration: 100 };
  const { spec } = fig.buildPayload();
  assert.equal(spec.traces[0].kind, "histogram");
  assert.deepEqual(spec.traces[0].animation, { duration: 100 });
});

test("_emitRect ships animation via payload transition attach", () => {
  const fig = figure({ width: 240, height: 160 });
  fig.bar([0, 1], [1, 2]);
  fig.traces[0].animation = { duration: 100 };
  const { spec } = fig.buildPayload();
  assert.equal(spec.traces[0].kind, "bar");
  assert.deepEqual(spec.traces[0].animation, { duration: 100 });
});

test("_emitTriangleMesh ships animation via payload mesh plan", () => {
  const fig = figure({ width: 240, height: 160 });
  fig.triangleMesh([0], [0], [1], [0], [0.5], [1]);
  fig.traces[0].animation = { duration: 100 };
  const { spec } = fig.buildPayload();
  assert.equal(spec.traces[0].kind, "triangle_mesh");
  assert.deepEqual(spec.traces[0].animation, { duration: 100 });
});


test("_emitRibbon ships animation via payload ribbon plan", () => {
  const fig = figure({ width: 240, height: 160 });
  fig.ribbon([0], [1], [0], [1], [0], [1]);
  fig.traces[0].animation = { duration: 100 };
  const { spec } = fig.buildPayload();
  assert.equal(spec.traces[0].kind, "ribbon");
  assert.deepEqual(spec.traces[0].animation, { duration: 100 });
});


test("_emitSegments ships animation via payload segments plan", () => {
  const fig = figure({ width: 240, height: 160 });
  fig.segments([0], [0], [1], [1]);
  fig.traces[0].animation = { duration: 100 };
  const { spec } = fig.buildPayload();
  assert.equal(spec.traces[0].kind, "segments");
  assert.notEqual(spec.traces[0].animation, undefined);
});

test("_emitScatterDensity ships animation via payload transition attach", () => {
  const fig = figure({ width: 240, height: 160 });
  fig.scatter([0, 1], [0, 1], { forceDensity: true });
  fig.traces[0].animation = { duration: 100 };
  const { spec } = fig.buildPayload();
  assert.equal(spec.traces[0].tier, "density");
  assert.deepEqual(spec.traces[0].animation, { duration: 100 });
});

test("buildPayload ships cartesian axis tick_values like Python _axis_spec", () => {
  const fig = figure({ width: 240, height: 160 });
  fig.scatter([0, 1], [0, 1]);
  fig.setAxis("x", { tick_values: [0, 0.5, 1] });
  const { spec } = fig.buildPayload();
  assert.deepEqual(spec.x_axis.tick_values, [0, 0.5, 1]);
  assert.equal(spec.y_axis.tick_values, undefined);
});


test("buildPayload ships dom via payload build plan", () => {
  const fig = figure({ width: 240, height: 160 });
  fig.scatter([0, 1], [0, 1]);
  fig.class_name = "root-node";
  const { spec } = fig.buildPayload();
  assert.equal(fig.class_name, "root-node");
  assert.deepEqual(spec.dom, { class_name: "root-node" });
});


test("_emitScatterDensity ships slim categorical entry color like Python _density_trace_spec", () => {
  const fig = figure({ width: 240, height: 160 });
  fig.scatter([0, 1, 2, 3, 4], [0, 1, 0.5, 0.2, 0.8], {
    forceDensity: true,
    color: ["a", "b", "a", "c", "b"],
  });
  const { spec } = fig.buildPayload();
  assert.equal(spec.traces[0].tier, "density");
  assert.deepEqual(spec.traces[0].color, {
    mode: "categorical",
    categories: ["a", "b", "c"],
    palette: ["#3987e5", "#008300", "#d55181"],
  });
  assert.equal(spec.traces[0].color.buf, undefined);
});


test("buildPayload ships padding via payload build plan", () => {
  const fig = figure({ width: 240, height: 160 });
  fig.scatter([0, 1], [0, 1]);
  fig.padding = [8, 8, 8, 8];
  const { spec } = fig.buildPayload();
  assert.deepEqual(fig.padding, [8, 8, 8, 8]);
  assert.deepEqual(spec.padding, [8, 8, 8, 8]);
});


test("buildPayload omits title_options unlike Python build_payload", () => {
  // Python `build_payload` ships `title_options` with geometry columns. Node
  // payload omits that field. Recorded emit-payload-title-options stay-host.
  const fig = figure({ width: 240, height: 160 });
  fig.scatter([0, 1], [0, 1]);
  fig.title_options = [{ text: "T", y: 1.0, pad: 8.0 }];
  const { spec } = fig.buildPayload();
  assert.equal(fig.title_options.length, 1);
  assert.equal(spec.title_options, undefined);
});


test("buildPayload omits extra_legends unlike Python build_payload", () => {
  // Python `build_payload` ships `extra_legends`. Node payload omits that
  // field. Recorded emit-payload-extra-legends stay-host.
  const fig = figure({ width: 240, height: 160 });
  fig.scatter([0, 1], [0, 1]);
  fig.extra_legends = [{ loc: "lower left" }];
  const { spec } = fig.buildPayload();
  assert.equal(fig.extra_legends.length, 1);
  assert.equal(spec.extra_legends, undefined);
});


test("buildPayload omits annotations unlike Python build_payload", () => {
  // Python `build_payload` ships `_annotation_specs`. Node payload omits
  // that field. Recorded emit-payload-annotations stay-host.
  const fig = figure({
    width: 240,
    height: 160,
    annotations: [{ kind: "text", text: "hi", x: 0, y: 1 }],
  });
  fig.scatter([0, 1], [0, 1]);
  const { spec } = fig.buildPayload();
  assert.equal(fig.annotations.length, 1);
  assert.equal(spec.annotations, undefined);
});


test("buildPayload omits colorbar unlike Python build_payload", () => {
  // Python `build_payload` ships `colorbar` from `colorbar_options`. Node
  // payload omits that field. Recorded emit-payload-colorbar stay-host.
  const fig = figure({ width: 240, height: 160, colorbar: { title: "c" } });
  fig.scatter([0, 1], [0, 1]);
  const { spec } = fig.buildPayload();
  assert.equal(fig.colorbar_options.title, "c");
  assert.equal(spec.colorbar, undefined);
});


test("buildPayload omits legend unlike Python build_payload", () => {
  // Python `build_payload` ships `legend` from `legend_options`. Node
  // payload omits that field. Recorded emit-payload-legend stay-host.
  const fig = figure({ width: 240, height: 160, legend: { loc: "upper right" } });
  fig.scatter([0, 1], [0, 1]);
  const { spec } = fig.buildPayload();
  assert.equal(fig.legend_options.loc, "upper right");
  assert.equal(spec.legend, undefined);
});

test("buildPayload ships cartesian axis minor_tick_values like Python _axis_spec", () => {
  const fig = figure({ width: 240, height: 160 });
  fig.scatter([0, 1], [0, 1]);
  fig.setAxis("x", { minor_tick_values: [0.25, 0.75] });
  const { spec } = fig.buildPayload();
  assert.deepEqual(spec.x_axis.minor_tick_values, [0.25, 0.75]);
  assert.equal(spec.y_axis.minor_tick_values, undefined);
});

test("buildPayload ships cartesian axis tick_labels like Python _axis_spec", () => {
  const fig = figure({ width: 240, height: 160 });
  fig.scatter([0, 1], [0, 1]);
  fig.setAxis("x", { tick_values: [0, 1], tick_labels: ["a", "b"] });
  const { spec } = fig.buildPayload();
  assert.deepEqual(spec.x_axis.tick_labels, ["a", "b"]);
  assert.equal(spec.y_axis.tick_labels, undefined);
});

test("buildPayload ships cartesian axis tick_count like Python _axis_spec", () => {
  const fig = figure({ width: 240, height: 160 });
  fig.scatter([0, 1], [0, 1]);
  fig.setAxis("x", { tick_count: 4 });
  const { spec } = fig.buildPayload();
  assert.equal(spec.x_axis.tick_count, 4);
  assert.equal(spec.y_axis.tick_count, undefined);
});

test("buildPayload ships cartesian axis reverse like Python _axis_spec", () => {
  const fig = figure({ width: 240, height: 160 });
  fig.scatter([0, 1], [0, 1]);
  fig.setAxis("x", { reverse: true });
  const { spec } = fig.buildPayload();
  assert.equal(fig.axis_options.x.reverse, true);
  assert.equal(spec.x_axis.reverse, true);
  assert.equal(spec.y_axis.reverse, undefined);
});

test("buildPayload ships cartesian axis domain like Python _axis_spec", () => {
  const fig = figure({ width: 240, height: 160 });
  fig.scatter([1, 2], [1, 2]);
  fig.setAxis("x", { domain: [0, 3] });
  const { spec } = fig.buildPayload();
  assert.deepEqual(fig.axis_options.x.domain, [0, 3]);
  assert.deepEqual(spec.x_axis.domain, [0, 3]);
  assert.equal(spec.y_axis.domain, undefined);
});

test("buildPayload ships cartesian axis format like Python _axis_spec", () => {
  const fig = figure({ width: 240, height: 160 });
  fig.scatter([0, 1], [0, 1]);
  fig.setAxis("x", { format: ".2f" });
  const { spec } = fig.buildPayload();
  assert.equal(fig.axis_options.x.format, ".2f");
  assert.equal(spec.x_axis.format, ".2f");
  assert.equal(spec.y_axis.format, undefined);
});

test("buildPayload ships cartesian axis bounds like Python _axis_spec", () => {
  const fig = figure({ width: 240, height: 160 });
  fig.scatter([0, 1], [0, 1]);
  fig.setAxis("x", { bounds: [0, 2] });
  const { spec } = fig.buildPayload();
  assert.deepEqual(fig.axis_options.x.bounds, [0, 2]);
  assert.deepEqual(spec.x_axis.bounds, [0, 2]);
  assert.equal(spec.y_axis.bounds, undefined);
});

test("buildPayload ships cartesian axis tick_sides like Python _axis_spec", () => {
  const fig = figure({ width: 240, height: 160 });
  fig.scatter([0, 1], [0, 1]);
  fig.setAxis("x", { tick_sides: ["bottom"] });
  const { spec } = fig.buildPayload();
  assert.deepEqual(fig.axis_options.x.tick_sides, ["bottom"]);
  assert.deepEqual(spec.x_axis.tick_sides, ["bottom"]);
  assert.equal(spec.y_axis.tick_sides, undefined);
});

test("buildPayload ships cartesian axis tick_label_sides like Python _axis_spec", () => {
  const fig = figure({ width: 240, height: 160 });
  fig.scatter([0, 1], [0, 1]);
  fig.setAxis("x", { tick_label_sides: ["bottom"] });
  const { spec } = fig.buildPayload();
  assert.deepEqual(fig.axis_options.x.tick_label_sides, ["bottom"]);
  assert.deepEqual(spec.x_axis.tick_label_sides, ["bottom"]);
  assert.equal(spec.y_axis.tick_label_sides, undefined);
});

test("buildPayload ships cartesian axis label_position like Python _axis_spec", () => {
  const fig = figure({ width: 240, height: 160 });
  fig.scatter([0, 1], [0, 1]);
  fig.setAxis("x", { label_position: "end" });
  const { spec } = fig.buildPayload();
  assert.deepEqual(fig.axis_options.x.label_position, "end");
  assert.deepEqual(spec.x_axis.label_position, "end");
  assert.equal(spec.y_axis.label_position, undefined);
});

test("buildPayload ships cartesian axis label_offset like Python _axis_spec", () => {
  const fig = figure({ width: 240, height: 160 });
  fig.scatter([0, 1], [0, 1]);
  fig.setAxis("x", { label_offset: 8 });
  const { spec } = fig.buildPayload();
  assert.equal(fig.axis_options.x.label_offset, 8);
  assert.equal(spec.x_axis.label_offset, 8);
  assert.equal(spec.y_axis.label_offset, undefined);
});

test("buildPayload ships cartesian axis label_angle like Python _axis_spec", () => {
  const fig = figure({ width: 240, height: 160 });
  fig.scatter([0, 1], [0, 1]);
  fig.setAxis("x", { label_angle: 45 });
  const { spec } = fig.buildPayload();
  assert.equal(fig.axis_options.x.label_angle, 45);
  assert.equal(spec.x_axis.label_angle, 45);
  assert.equal(spec.y_axis.label_angle, undefined);
});

test("buildPayload ships cartesian axis tick_label_angle like Python _axis_spec", () => {
  const fig = figure({ width: 240, height: 160 });
  fig.scatter([0, 1], [0, 1]);
  fig.setAxis("x", { tick_label_angle: 30 });
  const { spec } = fig.buildPayload();
  assert.equal(fig.axis_options.x.tick_label_angle, 30);
  assert.equal(spec.x_axis.tick_label_angle, 30);
  assert.equal(spec.y_axis.tick_label_angle, undefined);
});

test("buildPayload ships cartesian axis tick_label_strategy like Python _axis_spec", () => {
  const fig = figure({ width: 240, height: 160 });
  fig.scatter([0, 1], [0, 1]);
  fig.setAxis("x", { tick_label_strategy: "hide" });
  const { spec } = fig.buildPayload();
  assert.equal(fig.axis_options.x.tick_label_strategy, "hide");
  assert.equal(spec.x_axis.tick_label_strategy, "hide");
  assert.equal(spec.y_axis.tick_label_strategy, undefined);
});

test("buildPayload ships cartesian axis tick_label_anchor like Python _axis_spec", () => {
  const fig = figure({ width: 240, height: 160 });
  fig.scatter([0, 1], [0, 1]);
  fig.setAxis("x", { tick_label_anchor: "start" });
  const { spec } = fig.buildPayload();
  assert.equal(fig.axis_options.x.tick_label_anchor, "start");
  assert.equal(spec.x_axis.tick_label_anchor, "start");
  assert.equal(spec.y_axis.tick_label_anchor, undefined);
});

test("buildPayload ships cartesian axis tick_label_min_gap like Python _axis_spec", () => {
  const fig = figure({ width: 240, height: 160 });
  fig.scatter([0, 1], [0, 1]);
  fig.setAxis("x", { tick_label_min_gap: 4 });
  const { spec } = fig.buildPayload();
  assert.equal(fig.axis_options.x.tick_label_min_gap, 4);
  assert.equal(spec.x_axis.tick_label_min_gap, 4);
  assert.equal(spec.y_axis.tick_label_min_gap, undefined);
});

test("buildPayload omits cartesian axis minor_style unlike Python _axis_spec", () => {
  // Python `_axis_spec` ships `minor_style`. Node cartesian payload axes omit
  // that field even when axis minor_style is set. Recorded
  // emit-payload-axis-minor-style stay-host.
  const fig = figure({ width: 240, height: 160 });
  fig.scatter([0, 1], [0, 1]);
  fig.setAxis("x", { minor_style: { color: "#888" } });
  const { spec } = fig.buildPayload();
  assert.equal(fig.axis_options.x.minor_style.color, "#888");
  assert.equal(spec.x_axis.minor_style, undefined);
});

test("buildPayload omits cartesian axis style unlike Python _axis_spec", () => {
  // Python `_axis_spec` ships compiled axis `style`. Node cartesian payload
  // axes omit that field even when axis style is set. Recorded
  // emit-payload-axis-style stay-host.
  const fig = figure({ width: 240, height: 160 });
  fig.scatter([0, 1], [0, 1]);
  fig.setAxis("x", { style: { color: "#111" } });
  const { spec } = fig.buildPayload();
  assert.equal(fig.axis_options.x.style.color, "#111");
  assert.equal(spec.x_axis.style, undefined);
});

test("buildPayload omits cartesian axis nonpositive unlike Python _axis_spec", () => {
  // Python `_axis_spec` ships `nonpositive` on log axes. Node cartesian payload
  // axes omit that field even when axis nonpositive is set. Recorded
  // emit-payload-axis-nonpositive stay-host.
  const fig = figure({ width: 240, height: 160 });
  fig.scatter([1, 2], [1, 2]);
  fig.setAxis("x", { type: "log", nonpositive: "clip" });
  const { spec } = fig.buildPayload();
  assert.equal(fig.axis_options.x.nonpositive, "clip");
  assert.equal(spec.x_axis.nonpositive, undefined);
});

test("buildPayload omits cartesian axis constant unlike Python _axis_spec", () => {
  // Python `_axis_spec` ships `constant` on symlog axes. Node cartesian payload
  // axes omit that field even when axis constant is set. Recorded
  // emit-payload-axis-constant stay-host.
  const fig = figure({ width: 240, height: 160 });
  fig.scatter([1, 2], [1, 2]);
  fig.setAxis("x", { type: "symlog", constant: 2 });
  const { spec } = fig.buildPayload();
  assert.equal(fig.axis_options.x.constant, 2);
  assert.equal(spec.x_axis.constant, undefined);
});

test("buildPayload omits cartesian axis categories unlike Python _axis_spec", () => {
  // Python `_axis_spec` ships `_axis_categories` for category axes. Node
  // cartesian payload axes omit that field even when categories are set.
  // Recorded emit-payload-axis-categories stay-host.
  const fig = figure({ width: 240, height: 160 });
  fig.scatter([0, 1], [0, 1]);
  fig._axis_categories = { x: ["a", "b"] };
  const { spec } = fig.buildPayload();
  assert.deepEqual(fig._axis_categories.x, ["a", "b"]);
  assert.equal(spec.x_axis.categories, undefined);
});

test("_emitLine skips M4 bin_x unlike Python _m4_decimate", () => {
  // Python `_m4_decimate` passes `_binning_coords` so log x buckets in
  // scale space. Node `_emitLine` omits bin_x, so log x keeps the same
  // n_marks as linear. Recorded emit-line-m4-bin-x stay-host.
  const n = 10001;
  const x = new Float64Array(n);
  const y = new Float64Array(n);
  for (let i = 0; i < n; i++) {
    x[i] = i < 9000 ? 1 + i * 0.001 : 10 + (i - 9000) * 0.09;
    y[i] = i;
  }
  const lin = figure({ width: 240, height: 160 });
  lin.setAxis("x", { domain: [1, 100] });
  lin.line(x, y);
  const log = figure({ width: 240, height: 160 });
  log.setAxis("x", { type: "log", domain: [1, 100] });
  log.line(x, y);
  const a = lin.buildPayload({ pxWidth: 64 }).spec.traces[0];
  const b = log.buildPayload({ pxWidth: 64 }).spec.traces[0];
  assert.equal(a.tier, "decimated");
  assert.equal(b.tier, "decimated");
  assert.equal(a.n_marks, b.n_marks);
});


test("_emitArea skips M4 bin_x unlike Python _m4_decimate", () => {
  // Python `_m4_decimate` passes `_binning_coords` so log x buckets in
  // scale space. Node `_emitArea` omits bin_x, so log x keeps the same
  // n_marks as linear. Recorded emit-area-m4-bin-x stay-host.
  const n = 10001;
  const x = new Float64Array(n);
  const y = new Float64Array(n);
  for (let i = 0; i < n; i++) {
    x[i] = i < 9000 ? 1 + i * 0.001 : 10 + (i - 9000) * 0.09;
    y[i] = i;
  }
  const lin = figure({ width: 240, height: 160 });
  lin.setAxis("x", { domain: [1, 100] });
  lin.area(x, y);
  const log = figure({ width: 240, height: 160 });
  log.setAxis("x", { type: "log", domain: [1, 100] });
  log.area(x, y);
  const a = lin.buildPayload({ pxWidth: 64 }).spec.traces[0];
  const b = log.buildPayload({ pxWidth: 64 }).spec.traces[0];
  assert.equal(a.tier, "decimated");
  assert.equal(b.tier, "decimated");
  assert.equal(a.n_marks, b.n_marks);
});


test("buildPayload ships polar axis id like Python _axis_spec", () => {
  const fig = figure({ coords: "polar", width: 240, height: 160 });
  fig.scatter([0, 1], [1, 2]);
  const { spec } = fig.buildPayload();
  assert.equal(spec.x_axis.id, "x");
  assert.equal(spec.y_axis.id, "y");
});


test("_emitScatterDensity yLinear follows axis scale like Python _density_trace_spec", () => {
  const n = 80;
  const x = new Float64Array(n);
  const y = new Float64Array(n);
  for (let i = 0; i < n; i++) {
    x[i] = 1;
    y[i] = i < 70 ? 1 + i * 0.01 : 10 + (i - 70);
  }
  const lin = figure({ width: 240, height: 160 });
  lin.setAxis("y", { domain: [1, 100] });
  lin.scatter(x, y, { forceDensity: true });
  const log = figure({ width: 240, height: 160 });
  log.setAxis("y", { type: "log", domain: [1, 100] });
  log.scatter(x, y, { forceDensity: true });
  const a = lin.buildPayload().spec.traces[0];
  const b = log.buildPayload().spec.traces[0];
  assert.equal(a.tier, "density");
  assert.equal(b.tier, "density");
  assert.notEqual(a.density.max, b.density.max);
});


test("_emitScatterDensity xLinear follows axis scale like Python _density_trace_spec", () => {
  const n = 80;
  const x = new Float64Array(n);
  const y = new Float64Array(n);
  for (let i = 0; i < n; i++) {
    x[i] = i < 70 ? 1 + i * 0.01 : 10 + (i - 70);
    y[i] = 1;
  }
  const lin = figure({ width: 240, height: 160 });
  lin.setAxis("x", { domain: [1, 100] });
  lin.scatter(x, y, { forceDensity: true });
  const log = figure({ width: 240, height: 160 });
  log.setAxis("x", { type: "log", domain: [1, 100] });
  log.scatter(x, y, { forceDensity: true });
  const a = lin.buildPayload().spec.traces[0];
  const b = log.buildPayload().spec.traces[0];
  assert.equal(a.tier, "density");
  assert.equal(b.tier, "density");
  assert.notEqual(a.density.max, b.density.max);
});

test("buildPayload ships polar axis kind like Python _axis_spec", () => {
  const fig = figure({ coords: "polar", width: 240, height: 160 });
  fig.scatter([0, 1], [1, 2]);
  const { spec } = fig.buildPayload();
  assert.equal(spec.x_axis.kind, "linear");
  assert.equal(spec.y_axis.kind, "linear");
});

test("buildPayload ships polar axis side like Python _axis_spec", () => {
  const fig = figure({ coords: "polar", width: 240, height: 160 });
  fig.scatter([0, 1], [1, 2]);
  const { spec } = fig.buildPayload();
  assert.equal(spec.x_axis.side, "bottom");
  assert.equal(spec.y_axis.side, "left");
});

test("buildPayload ships polar axis label like Python _axis_spec", () => {
  const fig = figure({ coords: "polar", width: 240, height: 160 });
  fig.scatter([0, 1], [1, 2]);
  const { spec } = fig.buildPayload();
  assert.equal(spec.x_axis.label, null);
  assert.equal(spec.y_axis.label, null);
});

test("buildPayload omits polar axis tick_values unlike Python _axis_spec", () => {
  // Python `_axis_spec` ships `tick_values` on polar axes. Node
  // `_polarAxisSpecs` omits that field. Recorded emit-polar-payload-axis-tick-values stay-host.
  const fig = figure({ coords: "polar", width: 240, height: 160 });
  fig.setAxis("x", { tick_values: [0, 1] });
  fig.scatter([0, 1], [1, 2]);
  const { spec } = fig.buildPayload();
  assert.equal(spec.x_axis.tick_values, undefined);
});

test("buildPayload omits polar axis minor_tick_values unlike Python _axis_spec", () => {
  // Python `_axis_spec` ships `minor_tick_values` on polar axes. Node
  // `_polarAxisSpecs` omits that field. Recorded emit-polar-payload-axis-minor-ticks stay-host.
  const fig = figure({ coords: "polar", width: 240, height: 160 });
  fig.setAxis("x", { minor_tick_values: [0.5] });
  fig.scatter([0, 1], [1, 2]);
  const { spec } = fig.buildPayload();
  assert.equal(spec.x_axis.minor_tick_values, undefined);
});

test("buildPayload omits polar axis tick_labels unlike Python _axis_spec", () => {
  // Python `_axis_spec` ships `tick_labels` on polar axes. Node
  // `_polarAxisSpecs` omits that field. Recorded emit-polar-payload-axis-tick-labels stay-host.
  const fig = figure({ coords: "polar", width: 240, height: 160 });
  fig.setAxis("x", { tick_labels: ["a", "b"] });
  fig.scatter([0, 1], [1, 2]);
  const { spec } = fig.buildPayload();
  assert.equal(spec.x_axis.tick_labels, undefined);
});

test("buildPayload omits polar axis tick_count unlike Python _axis_spec", () => {
  // Python `_axis_spec` ships `tick_count` on polar axes. Node
  // `_polarAxisSpecs` omits that field. Recorded emit-polar-payload-axis-tick-count stay-host.
  const fig = figure({ coords: "polar", width: 240, height: 160 });
  fig.setAxis("x", { tick_count: 4 });
  fig.scatter([0, 1], [1, 2]);
  const { spec } = fig.buildPayload();
  assert.equal(spec.x_axis.tick_count, undefined);
});

test("buildPayload ships polar axis reverse like Python _axis_spec", () => {
  const fig = figure({ coords: "polar", width: 240, height: 160 });
  fig.setAxis("x", { reverse: true });
  fig.scatter([0, 1], [1, 2]);
  const { spec } = fig.buildPayload();
  assert.equal(spec.x_axis.reverse, true);
});

test("buildPayload ships polar axis domain like Python _axis_spec", () => {
  const fig = figure({ coords: "polar", width: 240, height: 160 });
  fig.setAxis("x", { domain: [0, 1] });
  fig.scatter([0, 1], [1, 2]);
  const { spec } = fig.buildPayload();
  assert.deepEqual(spec.x_axis.domain, [0, 1]);
});

test("buildPayload ships polar axis format like Python _axis_spec", () => {
  const fig = figure({ coords: "polar", width: 240, height: 160 });
  fig.setAxis("x", { format: ".2f" });
  fig.scatter([0, 1], [1, 2]);
  const { spec } = fig.buildPayload();
  assert.equal(spec.x_axis.format, ".2f");
});

test("buildPayload ships polar axis bounds like Python _axis_spec", () => {
  const fig = figure({ coords: "polar", width: 240, height: 160 });
  fig.setAxis("x", { bounds: [0, 1] });
  fig.scatter([0, 1], [1, 2]);
  const { spec } = fig.buildPayload();
  assert.deepEqual(spec.x_axis.bounds, [0, 1]);
});

test("buildPayload ships polar axis tick_sides like Python _axis_spec", () => {
  const fig = figure({ coords: "polar", width: 240, height: 160 });
  fig.setAxis("x", { tick_sides: ["bottom"] });
  fig.scatter([0, 1], [1, 2]);
  const { spec } = fig.buildPayload();
  assert.deepEqual(spec.x_axis.tick_sides, ["bottom"]);
});

test("buildPayload ships polar axis tick_label_sides like Python _axis_spec", () => {
  const fig = figure({ coords: "polar", width: 240, height: 160 });
  fig.setAxis("x", { tick_label_sides: ["bottom"] });
  fig.scatter([0, 1], [1, 2]);
  const { spec } = fig.buildPayload();
  assert.deepEqual(spec.x_axis.tick_label_sides, ["bottom"]);
});

test("buildPayload ships polar axis label_position like Python _axis_spec", () => {
  const fig = figure({ coords: "polar", width: 240, height: 160 });
  fig.setAxis("x", { label_position: "end" });
  fig.scatter([0, 1], [1, 2]);
  const { spec } = fig.buildPayload();
  assert.deepEqual(spec.x_axis.label_position, "end");
});

test("buildPayload ships polar axis label_offset like Python _axis_spec", () => {
  const fig = figure({ coords: "polar", width: 240, height: 160 });
  fig.setAxis("x", { label_offset: 4 });
  fig.scatter([0, 1], [1, 2]);
  const { spec } = fig.buildPayload();
  assert.equal(spec.x_axis.label_offset, 4);
});

test("buildPayload ships polar axis label_angle like Python _axis_spec", () => {
  const fig = figure({ coords: "polar", width: 240, height: 160 });
  fig.setAxis("x", { label_angle: 15 });
  fig.scatter([0, 1], [1, 2]);
  const { spec } = fig.buildPayload();
  assert.equal(spec.x_axis.label_angle, 15);
});

test("buildPayload ships polar axis tick_label_angle like Python _axis_spec", () => {
  const fig = figure({ coords: "polar", width: 240, height: 160 });
  fig.setAxis("x", { tick_label_angle: 20 });
  fig.scatter([0, 1], [1, 2]);
  const { spec } = fig.buildPayload();
  assert.equal(spec.x_axis.tick_label_angle, 20);
});

test("buildPayload ships polar axis tick_label_strategy like Python _axis_spec", () => {
  const fig = figure({ coords: "polar", width: 240, height: 160 });
  fig.setAxis("x", { tick_label_strategy: "rotate" });
  fig.scatter([0, 1], [1, 2]);
  const { spec } = fig.buildPayload();
  assert.equal(spec.x_axis.tick_label_strategy, "rotate");
});

test("buildPayload ships polar axis tick_label_anchor like Python _axis_spec", () => {
  const fig = figure({ coords: "polar", width: 240, height: 160 });
  fig.setAxis("x", { tick_label_anchor: "start" });
  fig.scatter([0, 1], [1, 2]);
  const { spec } = fig.buildPayload();
  assert.equal(spec.x_axis.tick_label_anchor, "start");
});

test("buildPayload ships polar axis tick_label_min_gap like Python _axis_spec", () => {
  const fig = figure({ coords: "polar", width: 240, height: 160 });
  fig.setAxis("x", { tick_label_min_gap: 2 });
  fig.scatter([0, 1], [1, 2]);
  const { spec } = fig.buildPayload();
  assert.equal(spec.x_axis.tick_label_min_gap, 2);
});

test("buildPayload omits polar axis minor_style unlike Python _axis_spec", () => {
  // Python `_axis_spec` ships `minor_style` on polar axes. Node
  // `_polarAxisSpecs` omits that field. Recorded emit-polar-payload-axis-minor-style stay-host.
  const fig = figure({ coords: "polar", width: 240, height: 160 });
  fig.setAxis("x", { minor_style: { color: "#111" } });
  fig.scatter([0, 1], [1, 2]);
  const { spec } = fig.buildPayload();
  assert.equal(spec.x_axis.minor_style, undefined);
});

test("buildPayload omits polar axis style unlike Python _axis_spec", () => {
  // Python `_axis_spec` ships `compiled axis `style`` on polar axes. Node
  // `_polarAxisSpecs` omits that field. Recorded emit-polar-payload-axis-style stay-host.
  const fig = figure({ coords: "polar", width: 240, height: 160 });
  fig.setAxis("x", { style: { color: "#222" } });
  fig.scatter([0, 1], [1, 2]);
  const { spec } = fig.buildPayload();
  assert.equal(spec.x_axis.style, undefined);
});

test("buildPayload polar omits linear y scale like Python _axis_spec", () => {
  const fig = figure({ coords: "polar", width: 240, height: 160 });
  fig.scatter([0, 1], [1, 2]);
  const { spec } = fig.buildPayload();
  assert.equal(spec.y_axis.scale, undefined);
});

test("buildPayload polar ships non-linear y scale like Python _axis_spec", () => {
  const fig = figure({ coords: "polar", width: 240, height: 160 });
  fig.setAxis("y", { type: "log" });
  fig.scatter([0, 1], [1, 2]);
  const { spec } = fig.buildPayload();
  assert.equal(spec.y_axis.scale, "log");
});

test("buildPayload omits polar axis nonpositive unlike Python _axis_spec", () => {
  // Python `_axis_spec` ships `nonpositive` on log axes. Node `_polarAxisSpecs`
  // omits that field. Recorded emit-polar-payload-axis-nonpositive stay-host.
  const fig = figure({ coords: "polar", width: 240, height: 160 });
  fig.setAxis("y", { type: "log", nonpositive: "mask" });
  fig.scatter([0, 1], [1, 2]);
  const { spec } = fig.buildPayload();
  assert.equal(spec.y_axis.nonpositive, undefined);
});

test("buildPayload omits polar axis constant unlike Python _axis_spec", () => {
  // Python `_axis_spec` ships `constant` on symlog axes. Node `_polarAxisSpecs`
  // omits that field. Recorded emit-polar-payload-axis-constant stay-host.
  const fig = figure({ coords: "polar", width: 240, height: 160 });
  fig.setAxis("y", { type: "symlog", constant: 2 });
  fig.scatter([0, 1], [1, 2]);
  const { spec } = fig.buildPayload();
  assert.equal(spec.y_axis.constant, undefined);
});

test("buildPayload omits polar axis categories unlike Python _axis_spec", () => {
  // Python `_axis_spec` ships `_axis_categories` for category axes. Node
  // `_polarAxisSpecs` omits that field. Recorded emit-polar-payload-axis-categories stay-host.
  const fig = figure({ coords: "polar", width: 240, height: 160 });
  fig.setAxis("x", { type: "category", categories: ["a", "b"] });
  fig.scatter([0, 1], [1, 2]);
  const { spec } = fig.buildPayload();
  assert.equal(spec.x_axis.categories, undefined);
});

test("nextTraceId starts at 1 unlike Python len(traces)", () => {
  // Python first trace id is 0 (`id=len(self.traces)`). Node auto-ids start
  // at 1 and never assign 0. Recorded next-trace-id-base stay-host.
  const fig = figure({ width: 240, height: 160 });
  fig.scatter([0, 1], [1, 2]);
  const { spec } = fig.buildPayload();
  assert.notEqual(spec.traces[0].id, 0);
});


test("_emitScatterDensity visible uses range-index count like Python _density_trace_spec", () => {
  const fig = figure({ width: 240, height: 160 });
  fig.scatter([0, 1, NaN, 2], [1, 2, 3, 4], { forceDensity: true });
  const { spec } = fig.buildPayload();
  assert.equal(spec.traces[0].visible, 3);
});


test("_emitScatterDensity sample uses range-index sel like Python _density_sample_spec", () => {
  const fig = figure({ width: 240, height: 160 });
  fig.scatter([0, 1, NaN, 2], [1, 2, 3, 4], { forceDensity: true });
  const { spec } = fig.buildPayload();
  assert.equal(spec.traces[0].density.sample.n, 3);
});


test("_emitScatterDensity sample.visible uses range-index visible like Python _density_sample_spec", () => {
  const fig = figure({ width: 240, height: 160 });
  fig.scatter([0, 1, NaN, 2], [1, 2, 3, 4], { forceDensity: true });
  const { spec } = fig.buildPayload();
  assert.equal(spec.traces[0].density.sample.visible, 3);
});


test("_emitScatterDensity sample filters NaN and out-of-view rows like Python", () => {
  const fig = figure({ width: 240, height: 160 });
  fig.setAxisDomain("x", [0, 1.5]);
  fig.setAxisDomain("y", [0, 2.5]);
  fig.scatter([0, 1, NaN, 5], [1, 2, 3, 4], { forceDensity: true });
  const { spec } = fig.buildPayload();
  assert.equal(spec.traces[0].density.sample.n, 2);
  assert.equal(spec.traces[0].density.sample.visible, 2);
});


test("density Scene uses default color_ch palette like Python", () => {
  const fig = figure({ width: 240, height: 160 });
  fig.setAxisDomain("x", [0, 2]);
  fig.setAxisDomain("y", [0, 3]);
  fig.scatter([0, 1], [1, 2], { forceDensity: true, name: null });
  const scene = Buffer.from(fig.toScene());
  const viridis = Buffer.from([0x44, 0x01, 0x54, 0x00]);
  const palette = Buffer.from([0x39, 0x87, 0xe5, 0x00]);
  assert.equal(fig.traces[0].color_ch.mode, "constant");
  assert.equal(fig.traces[0].color_ch.constant, "#3987e5");
  assert.equal(scene.includes(palette), true);
  assert.equal(scene.includes(viridis), false);
});

test("composeScatter resolves color_ch like Python marks.scatter", () => {
  const fig = figure({ width: 240, height: 160 });
  fig.setAxisDomain("x", [0, 2]);
  fig.setAxisDomain("y", [0, 3]);
  fig.scatter([0, 1], [1, 2], { color: "#112233", name: null });
  const scene = Buffer.from(fig.toScene());
  const authored = Buffer.from([0x11, 0x22, 0x33]);
  const palette = Buffer.from([0x39, 0x87, 0xe5]);
  assert.equal(fig.traces[0].color_ch.mode, "constant");
  assert.equal(fig.traces[0].color_ch.constant, "#112233");
  assert.equal(scene.includes(authored), true);
  assert.equal(scene.includes(palette), false);
});

test("composeScatter always sets size_ch like Python marks.scatter", () => {
  const { traces } = composeScatter([0, 1], [1, 2]);
  assert.equal(traces[0].size_ch?.mode, "constant");
  assert.equal(traces[0].size_ch?.constant, 4);
});

test("composeScatter maps size to size_ch like Python marks.scatter", () => {
  const a = figure({ width: 240, height: 160 });
  a.scatter([0, 1], [1, 2], { id: 1 });
  const b = figure({ width: 240, height: 160 });
  b.scatter([0, 1], [1, 2], { id: 1, size: 8 });
  assert.notDeepEqual(Buffer.from(a.toScene()), Buffer.from(b.toScene()));
  assert.equal(b.traces[0].size_ch?.constant, 8);
});

test("composeScatter resolves stroke for payload channel attach", () => {
  const arrayStroke = composeScatter([0, 1, 2], [1, 2, 3], {
    stroke: ["#f00", "#0f0", "#00f"],
  }).traces[0];
  assert.equal(arrayStroke.stroke_ch.mode, "direct_rgba");
  assert.equal(arrayStroke.stroke_ch.rgba.length, 12);

  const constantStroke = composeScatter([0, 1], [1, 2], { stroke: "#ff0000" }).traces[0];
  assert.equal(constantStroke.style.stroke, "#ff0000");
  assert.equal(constantStroke.stroke_ch, undefined);
});

test("composeScatter omits symbol unlike Python style.symbol Scene", () => {
  // Python marks.scatter sets style.symbol from symbol=, so Scene paints square.
  // Node composeScatter ignores symbol, so Scene matches default circle marks.
  // Recorded scene-scatter-symbol-ch stay-host.
  const a = figure({ width: 240, height: 160 });
  a.scatter([0, 1], [1, 2], { id: 1 });
  const b = figure({ width: 240, height: 160 });
  b.scatter([0, 1], [1, 2], { id: 1, symbol: "square" });
  assert.deepEqual(Buffer.from(a.toScene()), Buffer.from(b.toScene()));
});

