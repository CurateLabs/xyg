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

test("_emitScatterDensity colormap stays style unlike Python color_ch", () => {
  // Python `_density_trace_spec` reads `color_ch.colormap`. Node scatter traces
  // keep `style.colormap` because authoring does not copy `color_ch`.
  const n = 10;
  const x = fill(n, (i) => i / n);
  const y = fill(n, (i) => ((i * 3) % n) / n);
  const fig = figure({ width: 320, height: 240 });
  fig.scatter(x, y, { forceDensity: true, style: { colormap: "plasma" } });
  fig.traces[0].color_ch = { mode: "continuous", colormap: "magma" };
  const { spec } = fig.buildPayload();
  assert.equal(spec.traces[0].tier, "density");
  assert.equal(spec.traces[0].density.colormap, "plasma");
});

test("_emitScatter omits animation unlike Python _base_entry", () => {
  // Python `_base_entry` ships t.animation. Node scatter encode omits that
  // field. Recorded emit-scatter-animation stay-host.
  const fig = figure({ width: 240, height: 160 });
  fig.scatter([0, 1], [0, 1]);
  fig.traces[0].animation = { duration: 100 };
  const { spec } = fig.buildPayload();
  assert.equal(spec.traces[0].kind, "scatter");
  assert.equal(spec.traces[0].animation, undefined);
});

test("_emitRibbon skips tooltip_rows length unlike Python _attach_tooltip_rows", () => {
  // Python `_attach_tooltip_rows` rejects a mismatch with n_points. Node
  // ribbon encode ships the short list. Recorded emit-ribbon-tooltip-len
  // stay-host.
  const fig = figure({ width: 240, height: 160 });
  fig.ribbon([0], [1], [0], [1], [0], [1]);
  fig.traces[0].tooltip_rows = [{ id: "a" }, { id: "b" }];
  const { spec } = fig.buildPayload();
  assert.equal(spec.traces[0].kind, "ribbon");
  assert.equal(spec.traces[0].tooltip_rows.length, 2);
});

test("_emitSegments skips tooltip_rows length unlike Python _attach_tooltip_rows", () => {
  // Python `_attach_tooltip_rows` rejects a mismatch with n_points. Node
  // segments encode ships the short list. Recorded emit-segments-tooltip-len
  // stay-host.
  const fig = figure({ width: 240, height: 160 });
  fig.segments([0, 1], [0, 1], [1, 2], [1, 2]);
  fig.traces[0].tooltip_rows = [{ id: "a" }];
  const { spec } = fig.buildPayload();
  assert.equal(spec.traces[0].kind, "segments");
  assert.equal(spec.traces[0].tooltip_rows.length, 1);
});

test("_emitScatter skips tooltip_rows length unlike Python _attach_tooltip_rows", () => {
  // Python `_attach_tooltip_rows` rejects a mismatch with n_points. Node
  // scatter encode ships the short list. Recorded emit-scatter-tooltip-len
  // stay-host.
  const fig = figure({ width: 240, height: 160 });
  fig.scatter([0, 1], [0, 1]);
  fig.traces[0].tooltip_rows = [{ id: "a" }];
  const { spec } = fig.buildPayload();
  assert.equal(spec.traces[0].kind, "scatter");
  assert.equal(spec.traces[0].tooltip_rows.length, 1);
});

test("_emitRibbon copies t.style unlike Python _default_styled", () => {
  // Python `_emit_ribbon` uses `_default_styled` to fill palette color when
  // style.color is missing. Node ribbon encode copies t.style. Recorded
  // emit-ribbon-default-styled stay-host.
  const fig = figure({ width: 240, height: 160 });
  fig.ribbon([0], [1], [0], [1], [0], [1]);
  fig.traces[0].style = { opacity: 0.9 };
  const { spec } = fig.buildPayload();
  assert.equal(spec.traces[0].kind, "ribbon");
  assert.equal(spec.traces[0].style.color, undefined);
});

test("_emitSegments copies t.style unlike Python _default_styled", () => {
  // Python `_emit_segments` uses `_default_styled` to fill palette color when
  // style.color is missing. Node segments encode copies t.style. Recorded
  // emit-segments-default-styled stay-host.
  const fig = figure({ width: 240, height: 160 });
  fig.segments([0, 1], [0, 1], [1, 2], [1, 2]);
  fig.traces[0].style = { opacity: 0.9 };
  const { spec } = fig.buildPayload();
  assert.equal(spec.traces[0].kind, "segments");
  assert.equal(spec.traces[0].style.color, undefined);
});

test("_emitTriangleMesh copies t.style unlike Python _default_styled", () => {
  // Python `_emit_triangle_mesh` uses `_default_styled` to fill palette color
  // when style.color is missing. Node mesh encode copies t.style. Recorded
  // emit-mesh-default-styled stay-host.
  const fig = figure({ width: 240, height: 160 });
  fig.triangleMesh([0], [0], [1], [0], [0.5], [1]);
  fig.traces[0].style = { opacity: 0.9 };
  const { spec } = fig.buildPayload();
  assert.equal(spec.traces[0].kind, "triangle_mesh");
  assert.equal(spec.traces[0].style.color, undefined);
});

test("_emitRect copies t.style unlike Python _default_styled", () => {
  // Python `_emit_rect` uses `_default_styled` to fill palette color when
  // style.color is missing. Node rect encode copies t.style. Recorded
  // emit-rect-default-styled stay-host.
  const fig = figure({ width: 240, height: 160 });
  fig.bar([0, 1], [1, 2]);
  fig.traces[0].style = { opacity: 0.9 };
  const { spec } = fig.buildPayload();
  assert.equal(spec.traces[0].kind, "bar");
  assert.equal(spec.traces[0].style.color, undefined);
});

test("_emitHistogram copies t.style unlike Python _default_styled", () => {
  // Python `_emit_histogram` calls `_emit_rect`, which uses `_default_styled`
  // to fill palette color when style.color is missing. Node histogram encode
  // copies t.style. Recorded emit-hist-default-styled stay-host.
  const fig = figure({ width: 240, height: 160 });
  fig.histogram([0, 1, 1, 2], { bins: 2, range: [0, 2] });
  fig.traces[0].style = { opacity: 0.9 };
  const { spec } = fig.buildPayload();
  assert.equal(spec.traces[0].kind, "histogram");
  assert.equal(spec.traces[0].style.color, undefined);
});

test("_emitHexbin copies t.style unlike Python _default_styled", () => {
  // Python `_emit_hexbin` uses `_default_styled` to fill palette color when
  // style.color is missing. Node hexbin encode copies t.style. Recorded
  // emit-hexbin-default-styled stay-host.
  const fig = figure({ width: 240, height: 160 });
  fig.hexbin([1, 2, 3, 4, 5], [1, 2, 1, 2, 1.5], { gridsize: 4 });
  fig.traces[0].style = { opacity: 0.9 };
  const { spec } = fig.buildPayload();
  assert.equal(spec.traces[0].kind, "hexbin");
  assert.equal(spec.traces[0].style.color, undefined);
});

test("_emitArea copies t.style unlike Python _default_styled", () => {
  // Python `_emit_area` uses `_default_styled` to fill palette color when
  // style.color is missing. Node area encode copies t.style. Recorded
  // emit-area-default-styled stay-host.
  const fig = figure({ width: 240, height: 160 });
  fig.area([0, 1], [0, 1]);
  fig.traces[0].style = { opacity: 0.9 };
  const { spec } = fig.buildPayload();
  assert.equal(spec.traces[0].kind, "area");
  assert.equal(spec.traces[0].style.color, undefined);
});

test("_emitLine copies t.style unlike Python _default_styled", () => {
  // Python `_emit_line` uses `_default_styled` to fill palette color when
  // style.color is missing. Node line encode copies t.style. Recorded
  // emit-line-default-styled stay-host.
  const fig = figure({ width: 240, height: 160 });
  fig.line([0, 1], [0, 1]);
  fig.traces[0].style = { opacity: 0.9 };
  const { spec } = fig.buildPayload();
  assert.equal(spec.traces[0].kind, "line");
  assert.equal(spec.traces[0].style.color, undefined);
});

test("buildPayload omits cartesian axis label unlike Python _axis_spec", () => {
  // Python `_axis_spec` ships `label`. Node cartesian payload axes omit that
  // field. Recorded emit-payload-axis-label stay-host.
  const fig = figure({ width: 240, height: 160 });
  fig.scatter([0, 1], [0, 1]);
  const { spec } = fig.buildPayload();
  assert.equal(spec.x_axis.label, undefined);
});

test("buildPayload omits cartesian axis side unlike Python _axis_spec", () => {
  // Python `_axis_spec` ships `side`. Node cartesian payload axes omit that
  // field. Recorded emit-payload-axis-side stay-host.
  const fig = figure({ width: 240, height: 160 });
  fig.scatter([0, 1], [0, 1]);
  const { spec } = fig.buildPayload();
  assert.equal(spec.x_axis.side, undefined);
});

test("buildPayload omits cartesian axis kind unlike Python _axis_spec", () => {
  // Python `_axis_spec` ships `_axis_kind`. Node cartesian payload axes omit
  // that field. Recorded emit-payload-axis-kind stay-host.
  const fig = figure({ width: 240, height: 160 });
  fig.scatter([0, 1], [0, 1]);
  const { spec } = fig.buildPayload();
  assert.equal(spec.x_axis.kind, undefined);
});

test("buildPayload omits cartesian axis id unlike Python _axis_spec", () => {
  // Python `_axis_spec` ships `id`. Node cartesian payload axes omit that
  // field. Recorded emit-payload-axis-id stay-host.
  const fig = figure({ width: 240, height: 160 });
  fig.scatter([0, 1], [0, 1]);
  const { spec } = fig.buildPayload();
  assert.equal(spec.x_axis.id, undefined);
});

test("buildPayload omits show_legend unlike Python build_payload", () => {
  // Python `build_payload` ships `show_legend`. Node payload omits that
  // field even when `show_legend` is false. Recorded
  // emit-payload-show-legend stay-host.
  const fig = figure({ width: 240, height: 160, showLegend: false });
  fig.scatter([0, 1], [0, 1]);
  const { spec } = fig.buildPayload();
  assert.equal(fig.show_legend, false);
  assert.equal(spec.show_legend, undefined);
});

test("buildPayload omits wasm_density unlike Python build_payload", () => {
  // Python `build_payload` attaches wasm_density from split
  // density.wasm_source. Node split payloads omit that field. Recorded
  // emit-payload-wasm-density stay-host.
  const fig = figure({ width: 240, height: 160 });
  fig.scatter([1, 10], [1, 10], { forceDensity: true });
  const { spec } = fig.buildPayload({ split: true });
  assert.equal(spec.traces[0].tier, "density");
  assert.equal(spec.wasm_density, undefined);
});

test("buildPayload cartesian axes stay linear unlike Python _axis_spec", () => {
  // Python `_axis_spec` ships `_axis_scale` when it is not linear. Node
  // cartesian payload axes keep scale linear. Recorded
  // emit-payload-axis-scale stay-host.
  const fig = figure({ width: 240, height: 160 });
  fig.setAxis("x", { type: "log" });
  fig.scatter([1, 10], [1, 10]);
  const { spec } = fig.buildPayload();
  assert.equal(spec.x_axis.scale, "linear");
});

test("_emitScatterDensity omits wasm_source unlike Python _density_trace_spec", () => {
  // Python `_density_trace_spec` ships density.wasm_source on split payloads.
  // Node density encode omits that replay source. Recorded
  // emit-density-wasm-source stay-host.
  const fig = figure({ width: 240, height: 160 });
  fig.scatter([1, 10], [1, 10], { forceDensity: true });
  const { spec } = fig.buildPayload({ split: true });
  assert.equal(spec.traces[0].tier, "density");
  assert.equal(spec.traces[0].density.wasm_source, undefined);
});

test("_emitScatterDensity sample omits ship scale unlike Python _axis_scale", () => {
  // Python `_density_sample_spec` passes `_axis_scale` into `pw.ship_values`,
  // pinning log offset to 0. Node density sample encode keeps the column
  // midpoint. Recorded emit-density-sample-ship-scale stay-host.
  const fig = figure({ width: 240, height: 160 });
  fig.setAxis("x", { type: "log" });
  fig.scatter([1, 10], [1, 10], { forceDensity: true });
  const { spec } = fig.buildPayload();
  assert.equal(spec.traces[0].tier, "density");
  assert.notEqual(spec.traces[0].density.sample.x.offset, 0);
});

test("_emitHistogram omits ship scale unlike Python _axis_scale", () => {
  // Python `_emit_histogram` calls `_emit_rect`, which passes `_axis_scale`
  // into `pw.ship`, pinning log offset to 0. Node histogram encode keeps the
  // column midpoint. Recorded emit-hist-ship-scale stay-host.
  const fig = figure({ width: 240, height: 160 });
  fig.setAxis("x", { type: "log" });
  fig.histogram([1, 2, 10], { bins: 2, range: [1, 10] });
  const { spec } = fig.buildPayload();
  assert.equal(spec.traces[0].kind, "histogram");
  const x0Col = spec.columns[spec.traces[0].x0];
  assert.notEqual(x0Col.offset, 0);
});

test("_emitTriangleMesh omits ship scale unlike Python _axis_scale", () => {
  // Python `_emit_triangle_mesh` passes `_axis_scale` into `pw.ship`, pinning
  // log offset to 0. Node mesh encode keeps the column midpoint. Recorded
  // emit-mesh-ship-scale stay-host.
  const fig = figure({ width: 240, height: 160 });
  fig.setAxis("x", { type: "log" });
  fig.triangleMesh([1], [1], [10], [1], [5], [10]);
  const { spec } = fig.buildPayload();
  assert.equal(spec.traces[0].kind, "triangle_mesh");
  const x0Col = spec.columns[spec.traces[0].x0];
  assert.notEqual(x0Col.offset, 0);
});

test("_emitRibbon omits ship scale unlike Python _axis_scale", () => {
  // Python `_emit_ribbon` passes `_axis_scale` into `pw.ship`, pinning log
  // offset to 0. Node ribbon encode keeps the column midpoint. Recorded
  // emit-ribbon-ship-scale stay-host.
  const fig = figure({ width: 240, height: 160 });
  fig.setAxis("x", { type: "log" });
  fig.ribbon([1], [10], [1], [10], [1], [10]);
  const { spec } = fig.buildPayload();
  assert.equal(spec.traces[0].kind, "ribbon");
  const x0Col = spec.columns[spec.traces[0].x0];
  assert.notEqual(x0Col.offset, 0);
});

test("_emitSegments omits ship scale unlike Python _axis_scale", () => {
  // Python `_emit_segments` passes `_axis_scale` into `pw.ship`, pinning log
  // offset to 0. Node segments encode keeps the column midpoint. Recorded
  // emit-segments-ship-scale stay-host.
  const fig = figure({ width: 240, height: 160 });
  fig.setAxis("x", { type: "log" });
  fig.segments([1, 10], [1, 10], [2, 20], [2, 20]);
  const { spec } = fig.buildPayload();
  assert.equal(spec.traces[0].kind, "segments");
  const x0Col = spec.columns[spec.traces[0].x0];
  assert.notEqual(x0Col.offset, 0);
});

test("_emitRect omits ship scale unlike Python _axis_scale", () => {
  // Python `_emit_rect` passes `_axis_scale` into `pw.ship`, pinning log
  // offset to 0. Node rect encode keeps the column midpoint. Recorded
  // emit-rect-ship-scale stay-host.
  const fig = figure({ width: 240, height: 160 });
  fig.setAxis("x", { type: "log" });
  fig.bar([1, 10], [1, 2]);
  const { spec } = fig.buildPayload();
  assert.equal(spec.traces[0].kind, "bar");
  const x0Col = spec.columns[spec.traces[0].x0];
  assert.notEqual(x0Col.offset, 0);
});

test("_emitHexbin omits ship scale unlike Python _axis_scale", () => {
  // Python `_emit_hexbin` passes `_axis_scale` into `ship_values`, pinning
  // log offset to 0. Node hexbin encode keeps the column midpoint. Recorded
  // emit-hexbin-ship-scale stay-host.
  const fig = figure({ width: 240, height: 160 });
  fig.setAxis("x", { type: "log" });
  fig.hexbin([1, 2, 3, 4, 5], [1, 2, 1, 2, 1.5], { gridsize: 4 });
  const { spec } = fig.buildPayload();
  assert.equal(spec.traces[0].kind, "hexbin");
  const xCol = spec.columns[spec.traces[0].x];
  assert.notEqual(xCol.offset, 0);
});

test("_emitArea omits ship scale unlike Python _axis_scale", () => {
  // Python `_base_entry` passes `_axis_scale` into `pw.ship`, pinning log
  // offset to 0. Node area encode keeps the column midpoint. Recorded
  // emit-area-ship-scale stay-host.
  const fig = figure({ width: 240, height: 160 });
  fig.setAxis("x", { type: "log" });
  fig.area([1, 10], [1, 10]);
  const { spec } = fig.buildPayload();
  assert.equal(spec.traces[0].kind, "area");
  const xCol = spec.columns[spec.traces[0].x];
  assert.notEqual(xCol.offset, 0);
});

test("_emitLine omits ship scale unlike Python _axis_scale", () => {
  // Python `_base_entry` passes `_axis_scale` into `pw.ship`, pinning log
  // offset to 0. Node line encode keeps the column midpoint. Recorded
  // emit-line-ship-scale stay-host.
  const fig = figure({ width: 240, height: 160 });
  fig.setAxis("x", { type: "log" });
  fig.line([1, 10], [1, 10]);
  const { spec } = fig.buildPayload();
  assert.equal(spec.traces[0].kind, "line");
  const xCol = spec.columns[spec.traces[0].x];
  assert.notEqual(xCol.offset, 0);
});

test("_emitScatter omits ship scale unlike Python _axis_scale", () => {
  // Python `_base_entry` passes `_axis_scale` into `pw.ship`, pinning log
  // offset to 0. Node scatter encode keeps the column midpoint. Recorded
  // emit-scatter-ship-scale stay-host.
  const fig = figure({ width: 240, height: 160 });
  fig.setAxis("x", { type: "log" });
  fig.scatter([1, 10], [1, 10]);
  const { spec } = fig.buildPayload();
  assert.equal(spec.traces[0].tier, "direct");
  const xCol = spec.columns[spec.traces[0].x];
  assert.notEqual(xCol.offset, 0);
});

test("_emitScatterDensity omits mean-color rgba unlike Python trace_bin_colors", () => {
  // Python `_density_trace_spec` ships density.rgba from trace_bin_colors.
  // Node density keeps no rgba/color_agg even when color_ch is continuous.
  // Recorded emit-density-rgba stay-host.
  const fig = figure({ width: 320, height: 240 });
  fig.scatter([0, 1], [0, 1], { forceDensity: true });
  fig.traces[0].color_ch = {
    mode: "continuous",
    values: [0, 1],
    domain: [0, 1],
    colormap: "viridis",
  };
  const { spec } = fig.buildPayload();
  assert.equal(spec.traces[0].tier, "density");
  assert.equal(spec.traces[0].density.rgba, undefined);
  assert.equal(spec.traces[0].density.color_agg, undefined);
});

test("_emitScatterDensity dropped_channels stays empty unlike Python per_item_channel_names", () => {
  // Python `_density_trace_spec` lists per_item_channel_names as dropped_channels.
  // Node density keeps an empty list even when style_channels is present.
  // Recorded emit-density-dropped-channels stay-host.
  const fig = figure({ width: 320, height: 240 });
  fig.scatter([0, 1], [0, 1], { forceDensity: true });
  fig.traces[0].style_channels = { stroke_width: { mode: "constant", constant: 2 } };
  const { spec } = fig.buildPayload();
  assert.equal(spec.traces[0].tier, "density");
  assert.equal(spec.traces[0].density.channels_dropped, false);
  assert.deepEqual(spec.traces[0].density.dropped_channels, []);
});

test("_emitHeatmap ships rgba_len unlike Python nested rgba_bufs", () => {
  // Python `_emit_heatmap` ships nested heatmap.rgba_bufs from rgba_grid.
  // Node keeps rgba_len from t.rgba. Recorded emit-heatmap-rgba stay-host.
  const fig = figure({ width: 240, height: 160 });
  fig.heatmap([[0, 1], [1, 0]], {
    colormapStops: Uint8Array.from([0, 0, 255, 255, 255, 255, 255, 0, 0]),
  });
  fig.traces[0].rgba_grid = [{ values: [1, 0, 0, 1] }];
  const { spec } = fig.buildPayload();
  assert.equal(spec.traces[0].kind, "heatmap");
  assert.notEqual(spec.traces[0].rgba_len, undefined);
  assert.equal(spec.traces[0].heatmap, undefined);
});

test("_emitHeatmap omits color unlike Python _emit_heatmap", () => {
  // Python `_emit_heatmap` ships a continuous color spec. Node keeps no
  // color field on the grid-column payload. Recorded emit-heatmap-color stay-host.
  const fig = figure({ width: 240, height: 160 });
  fig.heatmap([[0, 1], [1, 0]], { colormap: "viridis" });
  const { spec } = fig.buildPayload();
  assert.equal(spec.traces[0].kind, "heatmap");
  assert.equal(spec.traces[0].color, undefined);
});

test("_emitScatter ships sizeValues unlike Python size_ch", () => {
  // Python `_emit_scatter` ships size_ch. Node keeps t.sizeValues even when
  // size_ch is also present. Recorded emit-scatter-size stay-host.
  const fig = figure({ width: 240, height: 160 });
  fig.scatter([0, 1], [0, 1], {
    _composed: true,
    sizeValues: [4, 8],
  });
  fig.traces[0].size_ch = { mode: "constant", constant: 12 };
  const { spec } = fig.buildPayload();
  assert.equal(spec.traces[0].tier, "direct");
  assert.equal(spec.traces[0].size.mode, "continuous");
  assert.deepEqual([...spec.traces[0].size.domain], [4, 8]);
});

test("_emitScatterDensity sample omits style_channels unlike Python _ship_trace_styles", () => {
  // Python `_density_sample_spec` ships style_channels as sample.channels.
  // Node density overlay keeps no channels field even when style_channels is
  // present. Recorded emit-density-sample-channels stay-host.
  const fig = figure({ width: 320, height: 240 });
  fig.scatter([0, 1], [0, 1], { forceDensity: true });
  fig.traces[0].style_channels = { stroke_width: { mode: "constant", constant: 2 } };
  const { spec } = fig.buildPayload();
  assert.equal(spec.traces[0].tier, "density");
  assert.notEqual(spec.traces[0].density.sample, undefined);
  assert.equal(spec.traces[0].density.sample.channels, undefined);
});

test("_emitScatterDensity sample omits stroke_ch unlike Python _ship_trace_styles", () => {
  // Python `_density_sample_spec` ships stroke_ch as sample.stroke. Node
  // density overlay keeps no stroke field even when stroke_ch is present.
  // Recorded emit-density-sample-stroke stay-host.
  const fig = figure({ width: 320, height: 240 });
  fig.scatter([0, 1], [0, 1], { forceDensity: true });
  fig.traces[0].stroke_ch = { mode: "constant", constant: "#112233" };
  const { spec } = fig.buildPayload();
  assert.equal(spec.traces[0].tier, "density");
  assert.notEqual(spec.traces[0].density.sample, undefined);
  assert.equal(spec.traces[0].density.sample.stroke, undefined);
});

test("_emitScatterDensity sample omits size_ch unlike Python _ship_channels", () => {
  // Python `_density_sample_spec` ships size_ch as sample.size. Node density
  // overlay keeps no size field even when size_ch is present.
  // Recorded emit-density-sample-size stay-host.
  const fig = figure({ width: 320, height: 240 });
  fig.scatter([0, 1], [0, 1], { forceDensity: true });
  fig.traces[0].size_ch = { mode: "constant", constant: 8 };
  const { spec } = fig.buildPayload();
  assert.equal(spec.traces[0].tier, "density");
  assert.notEqual(spec.traces[0].density.sample, undefined);
  assert.equal(spec.traces[0].density.sample.size, undefined);
});

test("_emitScatterDensity sample omits color_ch unlike Python _ship_channels", () => {
  // Python `_density_sample_spec` ships color_ch as sample.color. Node density
  // overlay keeps no color field even when color_ch is present.
  // Recorded emit-density-sample-color stay-host.
  const fig = figure({ width: 320, height: 240 });
  fig.scatter([0, 1], [0, 1], { forceDensity: true });
  fig.traces[0].color_ch = { mode: "constant", constant: "#112233" };
  const { spec } = fig.buildPayload();
  assert.equal(spec.traces[0].tier, "density");
  assert.notEqual(spec.traces[0].density.sample, undefined);
  assert.equal(spec.traces[0].density.sample.color, undefined);
});

test("_emitScatterDensity omits transition_keys unlike Python _transition_entry", () => {
  // Python `_emit_scatter` ships transition_keys via `_transition_entry` on the
  // density path. Node density payload keeps no keys field even when
  // transition_keys is present. Recorded emit-density-transition stay-host.
  const fig = figure({ width: 320, height: 240 });
  fig.scatter([0, 1], [0, 1], { forceDensity: true });
  fig.traces[0].transition_keys = [
    [1, 2],
    [3, 4],
  ];
  const { spec } = fig.buildPayload();
  assert.equal(spec.traces[0].tier, "density");
  assert.equal(spec.traces[0].keys, undefined);
});

test("_emitHistogram omits transition_keys unlike Python _transition_entry", () => {
  // Python `_emit_histogram` ships transition_keys via `_emit_rect` /
  // `_transition_entry`. Node histogram payload keeps no keys field even when
  // transition_keys is present. Recorded emit-hist-transition stay-host.
  const fig = figure({ width: 240, height: 160 });
  fig.histogram([0, 1, 1, 2], { bins: 2, range: [0, 2] });
  fig.traces[0].transition_keys = [
    [1, 2],
    [3, 4],
  ];
  const { spec } = fig.buildPayload();
  assert.equal(spec.traces[0].kind, "histogram");
  assert.equal(spec.traces[0].keys, undefined);
});

test("_emitSegments omits transition_keys unlike Python _transition_entry", () => {
  // Python `_emit_segments` ships transition_keys as `keys`. Node segments
  // payload keeps no keys field even when transition_keys is present.
  // Recorded emit-segments-transition stay-host.
  const fig = figure({ width: 240, height: 160 });
  fig.segments([0], [0], [1], [1]);
  fig.traces[0].transition_keys = [[1, 2]];
  const { spec } = fig.buildPayload();
  assert.equal(spec.traces[0].kind, "segments");
  assert.equal(spec.traces[0].keys, undefined);
});

test("_emitTriangleMesh omits transition_keys unlike Python _transition_entry", () => {
  // Python `_emit_triangle_mesh` ships transition_keys as `keys`. Node mesh
  // payload keeps no keys field even when transition_keys is present.
  // Recorded emit-mesh-transition stay-host.
  const fig = figure({ width: 240, height: 160 });
  fig.triangleMesh([0], [0], [1], [0], [0.5], [1]);
  fig.traces[0].transition_keys = [[1, 2]];
  const { spec } = fig.buildPayload();
  assert.equal(spec.traces[0].kind, "triangle_mesh");
  assert.equal(spec.traces[0].keys, undefined);
});

test("_emitRibbon omits transition_keys unlike Python _transition_entry", () => {
  // Python `_emit_ribbon` ships transition_keys as `keys`. Node ribbon
  // payload keeps no keys field even when transition_keys is present.
  // Recorded emit-ribbon-transition stay-host.
  const fig = figure({ width: 240, height: 160 });
  fig.ribbon([0], [1], [0], [1], [0], [1], { color: "#112233" });
  fig.traces[0].transition_keys = [[1, 2]];
  const { spec } = fig.buildPayload();
  assert.equal(spec.traces[0].kind, "ribbon");
  assert.equal(spec.traces[0].keys, undefined);
});

test("_emitRect omits transition_keys unlike Python _transition_entry", () => {
  // Python `_emit_rect` / `_emit_bar_compact` ship transition_keys as `keys`.
  // Node bar/rect payload keeps no keys field even when transition_keys is
  // present. Recorded emit-rect-transition stay-host.
  const fig = figure({ width: 240, height: 160 });
  fig.bar([0, 1], [1, 2]);
  fig.traces[0].transition_keys = [
    [1, 2],
    [3, 4],
  ];
  const { spec } = fig.buildPayload();
  assert.equal(spec.traces[0].kind, "bar");
  assert.equal(spec.traces[0].keys, undefined);
});

test("_emitTriangleMesh skips valid_indices_f64 unlike Python _emit_triangle_mesh", () => {
  // Python `_emit_triangle_mesh` gathers null geometry rows via
  // `valid_indices_f64`. Node mesh payload keeps every triangle even when a
  // geometry column has NaN. Recorded emit-mesh-gather stay-host.
  const fig = figure({ width: 240, height: 160 });
  fig.triangleMesh([0, 1], [0, 0], [1, 2], [0, 0], [0.5, 1.5], [1, 1]);
  const n = fig.traces[0].x0.length;
  fig.traces[0].x0[0] = Number.NaN;
  const { spec } = fig.buildPayload();
  assert.equal(spec.traces[0].kind, "triangle_mesh");
  assert.equal(spec.traces[0].n_marks, n);
});

test("_emitRibbon skips valid_indices_f64 unlike Python _emit_ribbon", () => {
  // Python `_emit_ribbon` gathers null geometry rows via `valid_indices_f64`.
  // Node ribbon payload keeps every band even when a geometry column has NaN.
  // Recorded emit-ribbon-gather stay-host.
  const fig = figure({ width: 240, height: 160 });
  fig.ribbon([0, 1], [1, 2], [0, 0], [1, 1], [0, 0], [1, 1], { color: "#112233" });
  const n = fig.traces[0].x0.length;
  fig.traces[0].x0[0] = Number.NaN;
  const { spec } = fig.buildPayload();
  assert.equal(spec.traces[0].kind, "ribbon");
  assert.equal(spec.traces[0].n_marks, n);
});

test("_emitRect ships bar columns unlike Python nested bar", () => {
  // Python `_emit_bar` ships a nested `bar` spec via `_emit_bar_compact`.
  // Node bar payload keeps x0/x1/y0/y1 rect columns and no `bar` field.
  // Recorded emit-bar-compact stay-host.
  const fig = figure({ width: 240, height: 160 });
  fig.bar([0, 1], [1, 2]);
  const { spec } = fig.buildPayload();
  assert.equal(spec.traces[0].kind, "bar");
  assert.equal(spec.traces[0].bar, undefined);
  assert.notEqual(spec.traces[0].x0, undefined);
});

test("_emitHistogram skips rectFiniteSel unlike Python _emit_rect", () => {
  // Python `_emit_histogram` calls `_emit_rect`, which drops non-finite rows
  // via `_rect_finite_sel`. Node histogram payload keeps every bin even when
  // a geometry column has NaN. Recorded emit-hist-finite-sel stay-host.
  const fig = figure({ width: 240, height: 160 });
  fig.histogram([0, 1, 1, 2], { bins: 2, range: [0, 2] });
  const nBins = fig.traces[0].x0.length;
  fig.traces[0].x0[0] = Number.NaN;
  const { spec } = fig.buildPayload();
  assert.equal(spec.traces[0].kind, "histogram");
  assert.equal(spec.traces[0].n_marks, nBins);
});

test("_emitArea omits transition_keys unlike Python _transition_entry", () => {
  // Python `_emit_area` ships transition_keys as `keys`. Node area payload
  // keeps no keys field even when transition_keys is present.
  // Recorded emit-area-transition stay-host.
  const fig = figure({ width: 240, height: 160 });
  fig.area([0, 1], [0, 1]);
  fig.traces[0].transition_keys = [
    [1, 2],
    [3, 4],
  ];
  const { spec } = fig.buildPayload();
  assert.equal(spec.traces[0].kind, "area");
  assert.equal(spec.traces[0].keys, undefined);
});

test("_emitLine omits transition_keys unlike Python _transition_entry", () => {
  // Python `_emit_line` ships transition_keys as `keys`. Node line payload
  // keeps no keys field even when transition_keys is present.
  // Recorded emit-line-transition stay-host.
  const fig = figure({ width: 240, height: 160 });
  fig.line([0, 1], [0, 1]);
  fig.traces[0].transition_keys = [
    [1, 2],
    [3, 4],
  ];
  const { spec } = fig.buildPayload();
  assert.equal(spec.traces[0].kind, "line");
  assert.equal(spec.traces[0].keys, undefined);
});

test("_emitScatter omits transition_keys unlike Python _transition_entry", () => {
  // Python `_emit_scatter` ships transition_keys as `keys`. Node scatter
  // payload keeps no keys field even when transition_keys is present.
  // Recorded emit-scatter-transition stay-host.
  const fig = figure({ width: 240, height: 160 });
  fig.scatter([0, 1], [0, 1]);
  fig.traces[0].transition_keys = [
    [1, 2],
    [3, 4],
  ];
  const { spec } = fig.buildPayload();
  assert.equal(spec.traces[0].tier, "direct");
  assert.equal(spec.traces[0].keys, undefined);
});

test("_emitHistogram omits style_channels unlike Python _ship_trace_styles", () => {
  // Python `_emit_histogram` ships style_channels via `_emit_rect` /
  // `_ship_trace_styles` as `channels`. Node histogram payload keeps no
  // channels field even when style_channels is present.
  // Recorded emit-hist-channels stay-host.
  const fig = figure({ width: 240, height: 160 });
  fig.histogram([0, 1, 1, 2], { bins: 2, range: [0, 2] });
  fig.traces[0].style_channels = { stroke_width: { mode: "constant", constant: 2 } };
  const { spec } = fig.buildPayload();
  assert.equal(spec.traces[0].kind, "histogram");
  assert.equal(spec.traces[0].channels, undefined);
});

test("_emitSegments omits style_channels unlike Python _ship_trace_styles", () => {
  // Python `_emit_segments` ships style_channels as `channels`. Node
  // segments payload keeps no channels field even when style_channels is present.
  // Recorded emit-segments-channels stay-host.
  const fig = figure({ width: 240, height: 160 });
  fig.segments([0], [0], [1], [1]);
  fig.traces[0].style_channels = { stroke_width: { mode: "constant", constant: 2 } };
  const { spec } = fig.buildPayload();
  assert.equal(spec.traces[0].kind, "segments");
  assert.equal(spec.traces[0].channels, undefined);
});

test("_emitTriangleMesh omits style_channels unlike Python _ship_trace_styles", () => {
  // Python `_emit_triangle_mesh` ships style_channels as `channels`. Node
  // mesh payload keeps no channels field even when style_channels is present.
  // Recorded emit-mesh-channels stay-host.
  const fig = figure({ width: 240, height: 160 });
  fig.triangleMesh([0], [0], [1], [0], [0.5], [1]);
  fig.traces[0].style_channels = { stroke_width: { mode: "constant", constant: 2 } };
  const { spec } = fig.buildPayload();
  assert.equal(spec.traces[0].kind, "triangle_mesh");
  assert.equal(spec.traces[0].channels, undefined);
});

test("_emitRect omits style_channels unlike Python _ship_trace_styles", () => {
  // Python `_emit_rect` ships style_channels as `channels`. Node bar/rect
  // payload keeps no channels field even when style_channels is present.
  // Recorded emit-rect-channels stay-host.
  const fig = figure({ width: 240, height: 160 });
  fig.bar([0, 1], [1, 2]);
  fig.traces[0].style_channels = { stroke_width: { mode: "constant", constant: 2 } };
  const { spec } = fig.buildPayload();
  assert.equal(spec.traces[0].kind, "bar");
  assert.equal(spec.traces[0].channels, undefined);
});

test("_emitRibbon omits style_channels unlike Python _ship_trace_styles", () => {
  // Python `_emit_ribbon` ships style_channels as `channels`. Node ribbon
  // payload keeps no channels field even when style_channels is present.
  // Recorded emit-ribbon-channels stay-host.
  const fig = figure({ width: 240, height: 160 });
  fig.ribbon([0], [1], [0], [1], [0], [1], { color: "#112233" });
  fig.traces[0].style_channels = { stroke_width: { mode: "constant", constant: 2 } };
  const { spec } = fig.buildPayload();
  assert.equal(spec.traces[0].kind, "ribbon");
  assert.equal(spec.traces[0].channels, undefined);
});

test("_emitScatter omits style_channels unlike Python _ship_trace_styles", () => {
  // Python `_emit_scatter` ships style_channels as `channels`. Node scatter
  // payload keeps no channels field even when style_channels is present.
  // Recorded emit-scatter-channels stay-host.
  const fig = figure({ width: 240, height: 160 });
  fig.scatter([0, 1], [0, 1]);
  fig.traces[0].style_channels = { stroke_width: { mode: "constant", constant: 2 } };
  const { spec } = fig.buildPayload();
  assert.equal(spec.traces[0].tier, "direct");
  assert.equal(spec.traces[0].channels, undefined);
});

test("_emitHistogram omits stroke_ch unlike Python _ship_trace_styles", () => {
  // Python `_emit_histogram` ships stroke_ch via `_emit_rect` /
  // `_ship_trace_styles`. Node histogram payload keeps no stroke field even
  // when stroke_ch is present. Recorded emit-hist-stroke stay-host.
  const fig = figure({ width: 240, height: 160 });
  fig.histogram([0, 1, 1, 2], { bins: 2, range: [0, 2] });
  fig.traces[0].stroke_ch = { mode: "constant", constant: "#112233" };
  const { spec } = fig.buildPayload();
  assert.equal(spec.traces[0].kind, "histogram");
  assert.equal(spec.traces[0].stroke, undefined);
});

test("_emitSegments omits stroke_ch unlike Python _ship_trace_styles", () => {
  // Python `_emit_segments` ships stroke_ch via `_ship_trace_styles`. Node
  // segments payload keeps no stroke field even when stroke_ch is present.
  // Recorded emit-segments-stroke stay-host.
  const fig = figure({ width: 240, height: 160 });
  fig.segments([0], [0], [1], [1]);
  fig.traces[0].stroke_ch = { mode: "constant", constant: "#112233" };
  const { spec } = fig.buildPayload();
  assert.equal(spec.traces[0].kind, "segments");
  assert.equal(spec.traces[0].stroke, undefined);
});

test("_emitTriangleMesh omits stroke_ch unlike Python _ship_trace_styles", () => {
  // Python `_emit_triangle_mesh` ships stroke_ch via `_ship_trace_styles`.
  // Node mesh payload keeps no stroke field even when stroke_ch is present.
  // Recorded emit-mesh-stroke stay-host.
  const fig = figure({ width: 240, height: 160 });
  fig.triangleMesh([0], [0], [1], [0], [0.5], [1]);
  fig.traces[0].stroke_ch = { mode: "constant", constant: "#112233" };
  const { spec } = fig.buildPayload();
  assert.equal(spec.traces[0].kind, "triangle_mesh");
  assert.equal(spec.traces[0].stroke, undefined);
});

test("_emitRect omits stroke_ch unlike Python _ship_trace_styles", () => {
  // Python `_emit_rect` ships stroke_ch via `_ship_trace_styles`. Node
  // bar/rect payload keeps no stroke field even when stroke_ch is present.
  // Recorded emit-rect-stroke stay-host.
  const fig = figure({ width: 240, height: 160 });
  fig.bar([0, 1], [1, 2]);
  fig.traces[0].stroke_ch = { mode: "constant", constant: "#112233" };
  const { spec } = fig.buildPayload();
  assert.equal(spec.traces[0].kind, "bar");
  assert.equal(spec.traces[0].stroke, undefined);
});

test("_emitRibbon omits stroke_ch unlike Python _ship_trace_styles", () => {
  // Python `_emit_ribbon` ships stroke_ch via `_ship_trace_styles`. Node
  // ribbon payload keeps no stroke field even when stroke_ch is present.
  // Recorded emit-ribbon-stroke stay-host.
  const fig = figure({ width: 240, height: 160 });
  fig.ribbon([0], [1], [0], [1], [0], [1], { color: "#112233" });
  fig.traces[0].stroke_ch = { mode: "constant", constant: "#445566" };
  const { spec } = fig.buildPayload();
  assert.equal(spec.traces[0].kind, "ribbon");
  assert.equal(spec.traces[0].stroke, undefined);
});

test("_emitScatter omits stroke_ch unlike Python _ship_trace_styles", () => {
  // Python `_emit_scatter` ships stroke_ch via `_ship_trace_styles`. Node
  // scatter payload keeps no stroke field even when stroke_ch is present.
  // Recorded emit-scatter-stroke stay-host.
  const fig = figure({ width: 240, height: 160 });
  fig.scatter([0, 1], [0, 1]);
  fig.traces[0].stroke_ch = { mode: "constant", constant: "#112233" };
  const { spec } = fig.buildPayload();
  assert.equal(spec.traces[0].tier, "direct");
  assert.equal(spec.traces[0].stroke, undefined);
});

test("_emitTriangleMesh ships x/y unlike Python x2/y2", () => {
  // Python `_emit_triangle_mesh` ships x2/y2. Node keeps x/y for the third
  // vertex. Recorded emit-mesh-xy stay-host.
  const fig = figure({ width: 240, height: 160 });
  fig.triangleMesh([0], [0], [1], [0], [0.5], [1]);
  const { spec } = fig.buildPayload();
  assert.equal(spec.traces[0].kind, "triangle_mesh");
  assert.ok(spec.traces[0].x != null);
  assert.ok(spec.traces[0].y != null);
  assert.equal(spec.traces[0].x2, undefined);
  assert.equal(spec.traces[0].y2, undefined);
});

test("_emitHistogram omits color_ch unlike Python _emit_histogram", () => {
  // Python `_emit_histogram` ships color_ch via `_emit_rect`. Node histogram
  // payload keeps no color field even when color_ch is present. Recorded
  // emit-hist-color stay-host.
  const fig = figure({ width: 240, height: 160 });
  fig.histogram([0, 1, 1, 2], { bins: 2, range: [0, 2] });
  fig.traces[0].color_ch = { mode: "constant", constant: "#112233" };
  const { spec } = fig.buildPayload();
  assert.equal(spec.traces[0].kind, "histogram");
  assert.equal(spec.traces[0].color, undefined);
});

test("_emitTriangleMesh omits color_ch unlike Python _emit_triangle_mesh", () => {
  // Python `_emit_triangle_mesh` ships color_ch. Node mesh payload keeps no
  // color field even when color_ch is present. Recorded emit-mesh-color stay-host.
  const fig = figure({ width: 240, height: 160 });
  fig.triangleMesh([0], [0], [1], [0], [0.5], [1]);
  fig.traces[0].color_ch = { mode: "constant", constant: "#112233" };
  const { spec } = fig.buildPayload();
  assert.equal(spec.traces[0].kind, "triangle_mesh");
  assert.equal(spec.traces[0].color, undefined);
});

test("_emitSegments ships t.color unlike Python color_ch", () => {
  // Python `_emit_segments` ships color_ch. Node keeps t.color even when
  // color_ch is also present. Recorded emit-segments-color stay-host.
  const fig = figure({ width: 240, height: 160 });
  fig.segments([0], [0], [1], [1], {
    color: { mode: "constant", constant: "#112233" },
  });
  fig.traces[0].color_ch = { mode: "constant", constant: "#445566" };
  const { spec } = fig.buildPayload();
  assert.equal(spec.traces[0].kind, "segments");
  assert.equal(spec.traces[0].color.color, "#112233");
});

test("_emitRect omits color_ch unlike Python _emit_rect", () => {
  // Python `_emit_rect` ships color_ch. Node bar/rect payload keeps no color
  // field even when color_ch is present. Recorded emit-rect-color stay-host.
  const fig = figure({ width: 240, height: 160 });
  fig.bar([0, 1], [1, 2]);
  fig.traces[0].color_ch = { mode: "constant", constant: "#112233" };
  const { spec } = fig.buildPayload();
  assert.equal(spec.traces[0].kind, "bar");
  assert.equal(spec.traces[0].color, undefined);
});

test("_emitRibbon ships t.color unlike Python color_ch", () => {
  // Python `_emit_ribbon` ships color_ch. Node keeps t.color even when
  // color_ch differs. Recorded ribbon-ship-color stay-host.
  const fig = figure({ width: 240, height: 160 });
  fig.ribbon([0], [1], [0], [1], [0], [1], { color: "#112233" });
  fig.traces[0].color_ch = { mode: "constant", constant: "#445566" };
  const { spec } = fig.buildPayload();
  assert.equal(spec.traces[0].kind, "ribbon");
  assert.equal(spec.traces[0].color.color, "#112233");
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

test("_emitScatter ships t.color unlike Python color_ch", () => {
  // Python `_emit_scatter` ships color_ch. Node keeps t.color even when
  // color_ch is also present. Recorded scatter-ship-color stay-host.
  const fig = figure({ width: 240, height: 160 });
  fig.scatter([0, 1], [0, 1], {
    _composed: true,
    color: { mode: "constant", constant: "#112233" },
  });
  fig.traces[0].color_ch = { mode: "constant", constant: "#445566" };
  const { spec } = fig.buildPayload();
  assert.equal(spec.traces[0].tier, "direct");
  assert.equal(spec.traces[0].color.color, "#112233");
});

test("_emitHeatmap ships grid columns unlike Python nested heatmap", () => {
  // Python `_emit_heatmap` ships a nested heatmap object. Node keeps grid
  // columns. Recorded heatmap-grid stay-host.
  const fig = figure({ width: 240, height: 160 });
  fig.heatmap([[0, 1], [1, 0]], { colormap: "viridis" });
  const { spec } = fig.buildPayload();
  assert.equal(spec.traces[0].kind, "heatmap");
  assert.ok(spec.traces[0].grid != null);
  assert.equal(spec.traces[0].heatmap, undefined);
});

test("_emitHexbin ships metric unlike Python color_ch", () => {
  // Python `_emit_hexbin` ships color from color_ch. Node hexbin() stores
  // both metric and color_ch, but payload keeps metric. Recorded hexbin-metric stay-host.
  const fig = figure({ width: 240, height: 160 });
  fig.hexbin([0, 1, 0, 1, 0.5], [0, 0, 1, 1, 0.5], { gridsize: 4 });
  const { spec } = fig.buildPayload();
  assert.equal(spec.traces[0].kind, "hexbin");
  assert.ok(spec.traces[0].metric != null);
  assert.equal(spec.traces[0].color, undefined);
  assert.ok(fig.traces[0].color_ch != null);
});

test("_emitScatterDensity colorMode stays style unlike Python color_ch", () => {
  // Python color_mode follows color_ch. Node uses style.color ? 1 : 0, so
  // density.color ships from style even when color_ch is continuous.
  const n = 10;
  const x = fill(n, (i) => i / n);
  const y = fill(n, (i) => ((i * 3) % n) / n);
  const fig = figure({ width: 320, height: 240 });
  fig.scatter(x, y, { forceDensity: true, style: { color: "#112233" } });
  fig.traces[0].color_ch = { mode: "continuous", colormap: "magma" };
  const { spec } = fig.buildPayload();
  assert.equal(spec.traces[0].tier, "density");
  assert.equal(spec.traces[0].density.color, "#112233");
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

test("_emitLine omits animation unlike Python _base_entry", () => {
  // Python `_base_entry` ships t.animation. Node line encode omits that
  // field. Recorded emit-line-animation stay-host.
  const fig = figure({ width: 240, height: 160 });
  fig.line([0, 1], [0, 1]);
  fig.traces[0].animation = { duration: 100 };
  const { spec } = fig.buildPayload();
  assert.equal(spec.traces[0].kind, "line");
  assert.equal(spec.traces[0].animation, undefined);
});

test("_emitArea omits animation unlike Python _base_entry", () => {
  // Python `_base_entry` ships t.animation. Node area encode omits that
  // field. Recorded emit-area-animation stay-host.
  const fig = figure({ width: 240, height: 160 });
  fig.area([0, 1], [0, 1]);
  fig.traces[0].animation = { duration: 100 };
  const { spec } = fig.buildPayload();
  assert.equal(spec.traces[0].kind, "area");
  assert.equal(spec.traces[0].animation, undefined);
});

test("_emitHistogram omits animation unlike Python _transition_entry", () => {
  // Python `_emit_histogram` calls `_emit_rect`, which ships t.animation via
  // `_transition_entry`. Node histogram encode omits that field. Recorded
  // emit-hist-animation stay-host.
  const fig = figure({ width: 240, height: 160 });
  fig.histogram([0, 1, 1, 2], { bins: 2, range: [0, 2] });
  fig.traces[0].animation = { duration: 100 };
  const { spec } = fig.buildPayload();
  assert.equal(spec.traces[0].kind, "histogram");
  assert.equal(spec.traces[0].animation, undefined);
});

test("_emitRect omits animation unlike Python _transition_entry", () => {
  // Python `_emit_rect` ships t.animation via `_transition_entry`. Node bar
  // encode omits that field. Recorded emit-rect-animation stay-host.
  const fig = figure({ width: 240, height: 160 });
  fig.bar([0, 1], [1, 2]);
  fig.traces[0].animation = { duration: 100 };
  const { spec } = fig.buildPayload();
  assert.equal(spec.traces[0].kind, "bar");
  assert.equal(spec.traces[0].animation, undefined);
});

test("_emitTriangleMesh omits animation unlike Python _transition_entry", () => {
  // Python `_emit_triangle_mesh` ships t.animation via `_transition_entry`.
  // Node mesh encode omits that field. Recorded emit-mesh-animation stay-host.
  const fig = figure({ width: 240, height: 160 });
  fig.triangleMesh([0], [0], [1], [0], [0.5], [1]);
  fig.traces[0].animation = { duration: 100 };
  const { spec } = fig.buildPayload();
  assert.equal(spec.traces[0].kind, "triangle_mesh");
  assert.equal(spec.traces[0].animation, undefined);
});


test("_emitRibbon omits animation unlike Python _transition_entry", () => {
  // Python `_emit_ribbon` ships t.animation via `_transition_entry`. Node
  // ribbon encode omits that field. Recorded emit-ribbon-animation stay-host.
  const fig = figure({ width: 240, height: 160 });
  fig.ribbon([0], [1], [0], [1], [0], [1]);
  fig.traces[0].animation = { duration: 100 };
  const { spec } = fig.buildPayload();
  assert.equal(spec.traces[0].kind, "ribbon");
  assert.equal(spec.traces[0].animation, undefined);
});


test("_emitSegments omits animation unlike Python _transition_entry", () => {
  // Python `_emit_segments` ships t.animation via `_transition_entry`. Node
  // segments encode omits that field. Recorded emit-segments-animation stay-host.
  const fig = figure({ width: 240, height: 160 });
  fig.segments([0], [0], [1], [1]);
  fig.traces[0].animation = { duration: 100 };
  const { spec } = fig.buildPayload();
  assert.equal(spec.traces[0].kind, "segments");
  assert.equal(spec.traces[0].animation, undefined);
});

test("_emitScatterDensity omits animation unlike Python _transition_entry", () => {
  // Python `_transition_entry` ships t.animation on the density path. Node
  // density encode omits that field. Recorded emit-density-animation stay-host.
  const fig = figure({ width: 240, height: 160 });
  fig.scatter([0, 1], [0, 1], { forceDensity: true });
  fig.traces[0].animation = { duration: 100 };
  const { spec } = fig.buildPayload();
  assert.equal(spec.traces[0].tier, "density");
  assert.equal(spec.traces[0].animation, undefined);
});

test("buildPayload omits cartesian axis tick_values unlike Python _axis_spec", () => {
  // Python `_axis_spec` ships `tick_values`. Node cartesian payload axes omit
  // that field even when axis tick_values is set. Recorded
  // emit-payload-axis-tick-values stay-host.
  const fig = figure({ width: 240, height: 160 });
  fig.scatter([0, 1], [0, 1]);
  fig.setAxis("x", { tick_values: [0, 0.5, 1] });
  const { spec } = fig.buildPayload();
  assert.deepEqual(fig.axis_options.x.tick_values, [0, 0.5, 1]);
  assert.equal(spec.x_axis.tick_values, undefined);
});


test("buildPayload omits dom unlike Python _dom_spec", () => {
  // Python `_dom_spec` ships class_name / class_names / style / styles.
  // Node payload omits spec.dom even when class_name is set. Recorded
  // emit-payload-dom stay-host.
  const fig = figure({ width: 240, height: 160 });
  fig.scatter([0, 1], [0, 1]);
  fig.class_name = "root-node";
  const { spec } = fig.buildPayload();
  assert.equal(fig.class_name, "root-node");
  assert.equal(spec.dom, undefined);
});


test("_emitScatterDensity omits categorical color unlike Python _density_trace_spec", () => {
  // Python `_density_trace_spec` ships a slim categorical color spec for
  // legend chrome. Node density encode omits that field. Recorded
  // emit-density-cat-color stay-host.
  const fig = figure({ width: 240, height: 160 });
  fig.scatter([0, 1], [0, 1], { forceDensity: true });
  fig.traces[0].color_ch = { mode: "categorical", categories: ["a", "b"] };
  const { spec } = fig.buildPayload();
  assert.equal(spec.traces[0].tier, "density");
  assert.equal(spec.traces[0].color, undefined);
});


test("buildPayload omits padding unlike Python build_payload", () => {
  // Python `build_payload` ships `padding`. Node payload omits that field
  // even when Scene pack would read figure.padding. Recorded
  // emit-payload-padding stay-host.
  const fig = figure({ width: 240, height: 160 });
  fig.scatter([0, 1], [0, 1]);
  fig.padding = [8, 8, 8, 8];
  const { spec } = fig.buildPayload();
  assert.deepEqual(fig.padding, [8, 8, 8, 8]);
  assert.equal(spec.padding, undefined);
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

test("buildPayload omits cartesian axis minor_tick_values unlike Python _axis_spec", () => {
  // Python `_axis_spec` ships `minor_tick_values`. Node cartesian payload axes
  // omit that field even when axis minor_tick_values is set. Recorded
  // emit-payload-axis-minor-ticks stay-host.
  const fig = figure({ width: 240, height: 160 });
  fig.scatter([0, 1], [0, 1]);
  fig.setAxis("x", { minor_tick_values: [0.25, 0.75] });
  const { spec } = fig.buildPayload();
  assert.deepEqual(fig.axis_options.x.minor_tick_values, [0.25, 0.75]);
  assert.equal(spec.x_axis.minor_tick_values, undefined);
});

test("buildPayload omits cartesian axis tick_labels unlike Python _axis_spec", () => {
  // Python `_axis_spec` ships `tick_labels`. Node cartesian payload axes omit
  // that field even when axis tick_labels is set. Recorded
  // emit-payload-axis-tick-labels stay-host.
  const fig = figure({ width: 240, height: 160 });
  fig.scatter([0, 1], [0, 1]);
  fig.setAxis("x", { tick_labels: ["a", "b"] });
  const { spec } = fig.buildPayload();
  assert.deepEqual(fig.axis_options.x.tick_labels, ["a", "b"]);
  assert.equal(spec.x_axis.tick_labels, undefined);
});

test("buildPayload omits cartesian axis tick_count unlike Python _axis_spec", () => {
  // Python `_axis_spec` ships `tick_count`. Node cartesian payload axes omit
  // that field even when axis tick_count is set. Recorded
  // emit-payload-axis-tick-count stay-host.
  const fig = figure({ width: 240, height: 160 });
  fig.scatter([0, 1], [0, 1]);
  fig.setAxis("x", { tick_count: 4 });
  const { spec } = fig.buildPayload();
  assert.equal(fig.axis_options.x.tick_count, 4);
  assert.equal(spec.x_axis.tick_count, undefined);
});

test("buildPayload omits cartesian axis reverse unlike Python _axis_spec", () => {
  // Python `_axis_spec` ships `reverse`. Node cartesian payload axes omit
  // that field even when axis reverse is set. Recorded
  // emit-payload-axis-reverse stay-host.
  const fig = figure({ width: 240, height: 160 });
  fig.scatter([0, 1], [0, 1]);
  fig.setAxis("x", { reverse: true });
  const { spec } = fig.buildPayload();
  assert.equal(fig.axis_options.x.reverse, true);
  assert.equal(spec.x_axis.reverse, undefined);
});

test("buildPayload omits cartesian axis domain unlike Python _axis_spec", () => {
  // Python `_axis_spec` ships `domain`. Node cartesian payload axes omit that
  // field even when axis domain is set. Recorded emit-payload-axis-domain
  // stay-host.
  const fig = figure({ width: 240, height: 160 });
  fig.scatter([1, 2], [1, 2]);
  fig.setAxis("x", { domain: [0, 3] });
  const { spec } = fig.buildPayload();
  assert.deepEqual(fig.axis_options.x.domain, [0, 3]);
  assert.equal(spec.x_axis.domain, undefined);
});

test("buildPayload omits cartesian axis format unlike Python _axis_spec", () => {
  // Python `_axis_spec` ships `format`. Node cartesian payload axes omit that
  // field even when axis format is set. Recorded emit-payload-axis-format
  // stay-host.
  const fig = figure({ width: 240, height: 160 });
  fig.scatter([0, 1], [0, 1]);
  fig.setAxis("x", { format: ".2f" });
  const { spec } = fig.buildPayload();
  assert.equal(fig.axis_options.x.format, ".2f");
  assert.equal(spec.x_axis.format, undefined);
});

test("buildPayload omits cartesian axis bounds unlike Python _axis_spec", () => {
  // Python `_axis_spec` ships `bounds`. Node cartesian payload axes omit that
  // field even when axis bounds is set. Recorded emit-payload-axis-bounds
  // stay-host.
  const fig = figure({ width: 240, height: 160 });
  fig.scatter([0, 1], [0, 1]);
  fig.setAxis("x", { bounds: [0, 2] });
  const { spec } = fig.buildPayload();
  assert.deepEqual(fig.axis_options.x.bounds, [0, 2]);
  assert.equal(spec.x_axis.bounds, undefined);
});

test("buildPayload omits cartesian axis tick_sides unlike Python _axis_spec", () => {
  // Python `_axis_spec` ships `tick_sides`. Node cartesian payload axes omit
  // that field even when axis tick_sides is set. Recorded
  // emit-payload-axis-tick-sides stay-host.
  const fig = figure({ width: 240, height: 160 });
  fig.scatter([0, 1], [0, 1]);
  fig.setAxis("x", { tick_sides: ["bottom"] });
  const { spec } = fig.buildPayload();
  assert.deepEqual(fig.axis_options.x.tick_sides, ["bottom"]);
  assert.equal(spec.x_axis.tick_sides, undefined);
});

test("buildPayload omits cartesian axis tick_label_sides unlike Python _axis_spec", () => {
  // Python `_axis_spec` ships `tick_label_sides`. Node cartesian payload axes
  // omit that field even when axis tick_label_sides is set. Recorded
  // emit-payload-axis-tick-label-sides stay-host.
  const fig = figure({ width: 240, height: 160 });
  fig.scatter([0, 1], [0, 1]);
  fig.setAxis("x", { tick_label_sides: ["bottom"] });
  const { spec } = fig.buildPayload();
  assert.deepEqual(fig.axis_options.x.tick_label_sides, ["bottom"]);
  assert.equal(spec.x_axis.tick_label_sides, undefined);
});

test("buildPayload omits cartesian axis label_position unlike Python _axis_spec", () => {
  // Python `_axis_spec` ships `label_position`. Node cartesian payload axes
  // omit that field even when axis label_position is set. Recorded
  // emit-payload-axis-label-position stay-host.
  const fig = figure({ width: 240, height: 160 });
  fig.scatter([0, 1], [0, 1]);
  fig.setAxis("x", { label_position: "end" });
  const { spec } = fig.buildPayload();
  assert.equal(fig.axis_options.x.label_position, "end");
  assert.equal(spec.x_axis.label_position, undefined);
});

