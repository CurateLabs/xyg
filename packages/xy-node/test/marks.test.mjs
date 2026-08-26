import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

import {
  DECIMATION_THRESHOLD,
  PROTOCOL_VERSION,
  composeArea,
  composeBar,
  composeBox,
  composeEcdf,
  composeHeatmap,
  composeHexbin,
  composeHistogram,
  composeLine,
  composeSegments,
  composeViolin,
  computeEcdf,
  encodeScatterPositions,
  figure,
  graphChart,
  histogramChart,
  areaChart,
  barChart,
  binnedEcdf,
  boxChart,
  ecdfChart,
  heatmapChart,
  hexbinChart,
  violinChart,
  lineChart,
  m4DecimateLine,
  prepareLineSeries,
  scatterChart,
  weightedEcdf,
} from "../src/index.js";

const here = path.dirname(fileURLToPath(import.meta.url));
const fixturePath = path.join(here, "fixtures", "mark_parity.json");

function loadFixture() {
  if (!fs.existsSync(fixturePath)) {
    return null;
  }
  return JSON.parse(fs.readFileSync(fixturePath, "utf8"));
}

function fromF64Hex(hex) {
  const buf = Buffer.from(hex, "hex");
  return new Float64Array(buf.buffer, buf.byteOffset, buf.byteLength / 8);
}

function f32Hex(arr) {
  return Buffer.from(arr.buffer, arr.byteOffset, arr.byteLength).toString("hex");
}

function u8Hex(arr) {
  return Buffer.from(arr.buffer, arr.byteOffset, arr.byteLength).toString("hex");
}

test("scatterChart + encode matches Python fixture when present", () => {
  const fixture = loadFixture();
  if (fixture == null) {
    // Fixtures are produced by write_mark_fixtures.py; still exercise the API.
    const x = new Float64Array([0, 1, 2]);
    const y = new Float64Array([1, 2, 3]);
    const fig = scatterChart(x, y, { width: 200, height: 100 });
    const { spec } = fig.buildPayload();
    assert.equal(spec.protocol, PROTOCOL_VERSION);
    assert.equal(spec.traces[0].kind, "scatter");
    return;
  }
  const x = fromF64Hex(fixture.scatter.x_f64_hex);
  const y = fromF64Hex(fixture.scatter.y_f64_hex);
  const enc = encodeScatterPositions(x, y);
  assert.equal(f32Hex(enc.x), fixture.scatter.x_f32_hex);
  assert.equal(f32Hex(enc.y), fixture.scatter.y_f32_hex);
  assert.equal(enc.xMeta.offset, fixture.scatter.x_meta.offset);
  assert.equal(enc.yMeta.offset, fixture.scatter.y_meta.offset);
  assert.equal(enc.xMeta.scale, fixture.scatter.x_meta.scale);
  assert.equal(enc.yMeta.scale, fixture.scatter.y_meta.scale);

  const fig = scatterChart(x, y);
  const { spec, buffers } = fig.buildPayload({ split: true });
  assert.equal(spec.traces[0].kind, "scatter");
  assert.ok(buffers[0] instanceof Float32Array);
  assert.equal(f32Hex(buffers[0]), fixture.scatter.x_f32_hex);
  assert.equal(f32Hex(buffers[1]), fixture.scatter.y_f32_hex);
});

test("line M4 index count matches Python fixture when present", () => {
  const fixture = loadFixture();
  const n = fixture?.line_m4?.n ?? 20_000;
  const x = new Float64Array(n);
  const y = new Float64Array(n);
  for (let i = 0; i < n; i += 1) {
    x[i] = i;
    y[i] = Math.sin(i / 100.0) + i / n;
  }
  const nBuckets = fixture?.line_m4?.n_buckets ?? 640;
  const m4 = m4DecimateLine(x, y, {
    x0: 0,
    x1: n - 1,
    nBuckets,
    threshold: DECIMATION_THRESHOLD,
  });
  assert.equal(m4.tier, "decimated");
  if (fixture != null) {
    assert.equal(m4.indices.length, fixture.line_m4.index_count);
  } else {
    assert.ok(m4.indices.length > 0);
    assert.ok(m4.indices.length <= nBuckets * 4);
  }

  const composed = composeLine(x, y);
  assert.equal(composed.traces[0].kind, "line");
  const fig = lineChart(x, y, { width: 640 });
  const { spec } = fig.buildPayload({ pxWidth: nBuckets });
  assert.equal(spec.traces[0].kind, "line");
  assert.equal(spec.traces[0].tier, "decimated");
  assert.equal(spec.traces[0].decimation_px, nBuckets);
});

test("histogram_uniform counts match Python fixture when present", () => {
  const fixture = loadFixture();
  const values =
    fixture == null
      ? new Float64Array([0.1, 0.2, 0.5, 0.9, 1.1, 1.4, 1.9, 2.0, 2.5, 3.0, 3.5, 4.0, 4.5, 5.0, -0.5, 5.5])
      : fromF64Hex(fixture.histogram.values_f64_hex);
  const lo = fixture?.histogram?.lo ?? 0;
  const hi = fixture?.histogram?.hi ?? 5;
  const bins = fixture?.histogram?.n_bins ?? 5;
  const hist = composeHistogram(values, { bins, range: [lo, hi] });
  if (fixture != null) {
    assert.deepEqual([...hist.counts], fixture.histogram.counts);
    assert.deepEqual([...hist.edges], fixture.histogram.edges);
  }
  const fig = histogramChart(values, { bins, range: [lo, hi] });
  const { spec } = fig.buildPayload();
  assert.equal(spec.traces[0].kind, "histogram");
  assert.equal(spec.traces[0].n_marks, bins);
});

test("histogram auto edges support wide ranges and enforce the Rust cap", () => {
  const wide = composeHistogram(new Float64Array([0, 1]), { range: [-10, 10] });
  assert.equal(wide.edges.length, 41);
  assert.equal(wide.edges[0], -10);
  assert.equal(wide.edges[40], 10);
  const boundary = composeHistogram(new Float64Array([0, 1]), { range: [0, 5_000] });
  assert.equal(boundary.edges.length, 10_001);
  assert.throws(
    () => composeHistogram(new Float64Array([0, 1]), { range: [0, 5_000.5] }),
    /xyg_histogram_edges failed/,
  );
});

test("graphChart convenience wraps figure.graph", () => {
  const fig = graphChart(
    ["a", "b", "c"],
    [
      ["a", "b"],
      ["b", "c"],
    ],
    { layout: "circle", seed: 1, width: 300, height: 200 },
  );
  const { spec } = fig.buildPayload();
  assert.equal(spec.protocol, PROTOCOL_VERSION);
  assert.deepEqual(
    spec.traces.map((t) => t.kind),
    ["segments", "scatter"],
  );
});

test("figure.line and figure.histogram attach traces", () => {
  const fig = figure({ width: 100, height: 80 });
  fig.line([0, 1, 2], [0, 1, 0], { name: "l" });
  fig.histogram([1, 2, 2, 3], { bins: 3, range: [0, 3] });
  assert.equal(fig.traces.length, 2);
  assert.equal(fig.traces[0].kind, "line");
  assert.equal(fig.traces[1].kind, "histogram");
});

test("area stable sort matches Python fixture when present", () => {
  const fixture = loadFixture();
  const areaX = fixture == null ? new Float64Array([2, 0, 1]) : fromF64Hex(fixture.area.x_f64_hex);
  const areaY = fixture == null ? new Float64Array([3, 1, 2]) : fromF64Hex(fixture.area.y_f64_hex);
  const prepared = prepareLineSeries(areaX, areaY);
  const composed = composeArea(areaX, areaY, { base: fixture?.area?.base ?? 0.5 });
  if (fixture != null) {
    assert.equal(f64Hex(prepared.x), fixture.area.x_sorted_f64_hex);
    assert.equal(f64Hex(prepared.y), fixture.area.y_sorted_f64_hex);
    assert.equal(composed.traces[0].base.length, areaX.length);
  }
  const fig = areaChart(areaX, areaY, { base: fixture?.area?.base ?? 0.5 });
  assert.equal(fig.buildPayload().spec.traces[0].kind, "area");
});

test("bar rects match Python fixture when present", () => {
  const fixture = loadFixture();
  const barX = fixture == null ? new Float64Array([0, 1, 2]) : fromF64Hex(fixture.bar.x_f64_hex);
  const barY = fixture == null ? new Float64Array([1, 3, 2]) : fromF64Hex(fixture.bar.y_f64_hex);
  const width = fixture?.bar?.width ?? 0.8;
  const bar = composeBar(barX, barY, { width });
  if (fixture != null) {
    assert.equal(f64Hex(bar.traces[0].x0), fixture.bar.x0_f64_hex);
    assert.equal(f64Hex(bar.traces[0].x1), fixture.bar.x1_f64_hex);
    assert.equal(f64Hex(bar.traces[0].y0), fixture.bar.y0_f64_hex);
    assert.equal(f64Hex(bar.traces[0].y1), fixture.bar.y1_f64_hex);
  }
  const fig = barChart(barX, barY, { width });
  assert.equal(fig.buildPayload().spec.traces[0].kind, "bar");
});

test("bar stacked/grouped offsets via xyg_bar_stack", () => {
  const x = ["A", "B"];
  const y = [
    [2.0, -1.0],
    [3.0, -4.0],
    [-1.0, 2.0],
  ];
  const stacked = composeBar(x, y, { mode: "stacked", series: ["one", "two", "three"] });
  assert.equal(stacked.traces.length, 3);
  assert.equal(stacked.traces[1].style.role, "bar-stacked");
  assert.deepEqual(Array.from(stacked.traces[1].y0), [2.0, -1.0]);
  assert.deepEqual(Array.from(stacked.traces[1].y1), [5.0, -5.0]);

  const grouped = composeBar(x, [[1, 2], [3, 4]], { mode: "grouped", width: 0.8 });
  assert.equal(grouped.traces.length, 2);
  assert.equal(grouped.traces[0].style.role, "bar-grouped");
  assert.ok(Math.abs(grouped.traces[0].x0[0] - -0.4) < 1e-12);
});

test("pie / wind_rose / facet composers", async () => {
  const { pieChart, windRoseChart, facetChart, composePie, scatterChart } = await import(
    "../src/index.js"
  );
  const pie = composePie(["a", "b", "c"], [1, 2, 3], { hole: 0.4 });
  assert.ok(pie.traces.length >= 2);
  assert.equal(pie.coords, "polar");
  const pieFig = pieChart(["a", "b"], [10, 20], { width: 200, height: 200 });
  assert.equal(pieFig.coords, "polar");
  assert.ok(pieFig.traces.length >= 1);
  const piePayload = pieFig.buildPayload();
  assert.equal(piePayload.spec.coords, "polar");
  assert.equal(piePayload.spec.x_axis.theta_unit, "degrees");
  assert.equal(piePayload.spec.x_axis.theta_zero, "N");
  assert.equal(piePayload.spec.x_axis.theta_direction, "clockwise");
  assert.equal(piePayload.spec.y_axis.hole, 0.55);
  assert.deepEqual(piePayload.spec.x_axis.sector, [0, 360]);

  const rose = windRoseChart(
    new Float64Array([0, 0, 90]),
    new Float64Array([1, 1, 1]),
    { sectors: 4, speedBins: [2] },
  );
  assert.equal(rose.coords, "polar");
  assert.ok(rose.traces.length >= 1);
  assert.equal(rose._windRose.sectors, 4);
  const rosePayload = rose.buildPayload();
  assert.equal(rosePayload.spec.coords, "polar");
  assert.equal(rosePayload.spec.x_axis.theta_unit, "degrees");

  const stub = facetChart({ cols: 2 });
  assert.equal(stub.kind, "facet");
  assert.ok(stub.panels.length === 0);

  const left = scatterChart([0, 1], [0, 1]);
  const right = scatterChart([10, 11], [-5, 5]);
  const shared = facetChart({
    panels: [left, right],
    shareX: true,
    shareY: true,
  });
  assert.equal(shared.kind, "facet");
  assert.equal(shared.shareX, true);
  const [lx0, lx1] = left._range("x");
  const [rx0, rx1] = right._range("x");
  assert.equal(lx0, rx0);
  assert.equal(lx1, rx1);
  const [ly0, ly1] = left._range("y");
  const [ry0, ry1] = right._range("y");
  assert.equal(ly0, ry0);
  assert.equal(ly1, ry1);
  const payloads = shared.buildPayloads();
  assert.equal(payloads.length, 2);
  assert.ok(payloads[0].spec.traces.length >= 1);

  const panels = facetChart({
    by: ["x", "y", "x"],
    composePanel: (key) => ({ key, traces: [] }),
    shareX: false,
    shareY: false,
  });
  assert.deepEqual(panels.keys, ["x", "y"]);
  assert.equal(panels.panels.length, 2);
});

test("multi-group box / violin", () => {
  const groups = [
    new Float64Array([1, 2, 2, 3, 4]),
    new Float64Array([10, 11, 12, 13, 50]),
  ];
  const box = composeBox(groups);
  assert.equal(box.groups, 2);
  assert.equal(box.groupStats.length, 2);
  assert.ok(box.traces.find((t) => t.kind === "box").x0.length === 2);
  const boxPayload = boxChart(groups).buildPayload().spec;
  assert.deepEqual(
    boxPayload.traces.slice(0, 3).map((trace) => trace.kind),
    ["box_whisker", "box", "box_median"],
  );

  const grouped = composeBox(new Float64Array([1, 2, 10, 11, 12]), {
    group: ["a", "a", "b", "b", "b"],
  });
  assert.equal(grouped.groups, 2);
  for (const badCenter of [Number.NaN, Number.POSITIVE_INFINITY]) {
    assert.throws(
      () => composeBox([[1], [2]], { x: [10, badCenter], showOutliers: false }),
      /invalid bounded box geometry/,
    );
  }

  const violin = composeViolin(groups, { bins: 8 });
  assert.equal(violin.groups, 2);
  assert.equal(violin.traces[0].x0.length, 16);
  const fig = violinChart(groups, { bins: 8 });
  assert.equal(fig.buildPayload().spec.traces[0].kind, "violin");
});

test("sankey emits ribbon band polygons", async () => {
  const { composeSankey, figure } = await import("../src/index.js");
  const composed = composeSankey(["A", "B"], [["A", "B", 1]], { linkOpacity: 0.4 });
  assert.equal(composed.traces.length, 2);
  assert.ok(composed.traces.every((t) => t.kind === "ribbon"));
  // One link → constant source/target paints; two nodes → direct_rgba node ribbon.
  assert.equal(composed.traces[0].kind, "ribbon");
  assert.equal(composed.traces[1].color.mode, "direct_rgba");
  const multi = composeSankey(
    ["A", "B", "C"],
    [
      ["A", "B", 2],
      ["A", "C", 1],
    ],
  );
  assert.equal(multi.traces[0].color.mode, "direct_rgba");
  assert.equal(multi.traces[0].color_target.mode, "direct_rgba");
  const fig = figure();
  fig.sankey(["A", "B", "C"], [
    ["A", "B", 2],
    ["A", "C", 1],
  ]);
  const payload = fig.buildPayload();
  assert.ok(payload.spec.traces.every((t) => t.kind === "ribbon"));
  assert.ok(payload.spec.traces[0].target_y0 != null);
  assert.ok(payload.spec.traces[0].target_y1 != null);
  assert.equal(payload.spec.traces[0].color.mode, "direct_rgba");
});

test("box stats match Python fixture when present", () => {
  const fixture = loadFixture();
  const values =
    fixture == null
      ? new Float64Array([1, 2, 2, 3, 4, 5, 6, 7, 8, 100])
      : fromF64Hex(fixture.box.values_f64_hex);
  const box = composeBox(values);
  if (fixture != null) {
    assert.equal(box.stats.q1, fixture.box.q1);
    assert.equal(box.stats.median, fixture.box.median);
    assert.equal(box.stats.q3, fixture.box.q3);
    assert.equal(box.stats.low, fixture.box.low);
    assert.equal(box.stats.high, fixture.box.high);
    assert.equal(f64Hex(box.stats.outliers), fixture.box.outliers_f64_hex);
  }
  const fig = boxChart(values);
  assert.ok(fig.traces.length >= 3);
});

test("ecdf weighted kernel matches Python fixture when present", () => {
  const fixture = loadFixture();
  const values =
    fixture == null
      ? new Float64Array([3, 1, 2, 1, 3])
      : fromF64Hex(fixture.ecdf.values_f64_hex);
  const weights = new Float64Array(values.length).fill(1.0);
  const native = weightedEcdf(values, weights);
  const step = computeEcdf(values);
  if (fixture != null) {
    assert.equal(f64Hex(native.values), fixture.ecdf.x_f64_hex);
    assert.equal(f64Hex(native.cumulative), fixture.ecdf.y_f64_hex);
    assert.equal(native.values.length, fixture.ecdf.n_points);
  }
  const composed = composeEcdf(values);
  assert.equal(composed.traces[0].kind, "line");
  assert.equal(composed.traces[0].style.step, "post");
  assert.equal(composed.traces[0].style.role, "ecdf");
  assert.equal(composed.traces[0].x.length, step.x.length);
  const fig = ecdfChart(values);
  const trace = fig.buildPayload().spec.traces[0];
  assert.equal(trace.kind, "line");
  assert.equal(trace.style.step, "post");
  assert.equal(trace.style.role, "ecdf");
});

test("binned ecdf is Rust-owned, compact, bounded, and range-stable", () => {
  const compact = binnedEcdf(new Float64Array([0, 0.2, NaN, 0.2, 0.9]), 4);
  assert.deepEqual(Array.from(compact.x), [0, 0.225, 0.9]);
  assert.deepEqual(Array.from(compact.cumulative), [0, 0.75, 1]);

  const ranged = computeEcdf([-1, 0.25, 0.75, 2, Infinity], { bins: 2, range: [0, 1] });
  assert.deepEqual(Array.from(ranged.x), [0, 0.5, 1]);
  assert.deepEqual(Array.from(ranged.y), [0, 0.25, 0.5]);
  assert.equal(ranged.mode, "binned");

  const outside = computeEcdf([-2, 2], { bins: 4, range: [0, 1] });
  assert.deepEqual(Array.from(outside.x), [0]);
  assert.deepEqual(Array.from(outside.y), [0]);
  assert.throws(() => computeEcdf([NaN, Infinity], { bins: 4 }), /at least one finite value/);
  assert.throws(() => computeEcdf([0], { bins: 10_001 }), /<= 10000/);
});

test("segments compose matches Python fixture when present", () => {
  const fixture = loadFixture();
  const x0 = fixture == null ? new Float64Array([0, 1]) : fromF64Hex(fixture.segments.x0_f64_hex);
  const y0 = fixture == null ? new Float64Array([0, 1]) : fromF64Hex(fixture.segments.y0_f64_hex);
  const x1 = fixture == null ? new Float64Array([1, 2]) : fromF64Hex(fixture.segments.x1_f64_hex);
  const y1 = fixture == null ? new Float64Array([1, 0]) : fromF64Hex(fixture.segments.y1_f64_hex);
  const seg = composeSegments(x0, y0, x1, y1);
  if (fixture != null) {
    assert.equal(seg.traces[0].x0.length, fixture.segments.n);
  }
  const fig = figure();
  fig.segments(x0, y0, x1, y1);
  assert.equal(fig.buildPayload().spec.traces[0].kind, "segments");
});

test("heatmap rgba matches Python fixture when present", () => {
  const fixture = loadFixture();
  const rows = fixture?.heatmap?.rows ?? 3;
  const cols = fixture?.heatmap?.cols ?? 3;
  const z =
    fixture == null
      ? new Float64Array([0, 0.5, 1, 0.25, 0.75, 0.5, 1, 0, 0.5])
      : fromF64Hex(fixture.heatmap.z_f64_hex);
  const stops =
    fixture == null
      ? Uint8Array.from([0, 0, 255, 255, 255, 255, 255, 0, 0])
      : Buffer.from(fixture.heatmap.stops_u8_hex, "hex");
  const hm = composeHeatmap(z, { rows, cols, colormapStops: stops });
  if (fixture != null) {
    assert.equal(u8Hex(hm.traces[0].rgba.rgba), fixture.heatmap.rgba_u8_hex);
  }
  const fig = heatmapChart(z, { rows, cols, colormapStops: stops });
  assert.equal(fig.buildPayload().spec.traces[0].kind, "heatmap");
});

test("hexbin kernel matches Python fixture when present", () => {
  const fixture = loadFixture();
  const x = fixture == null ? new Float64Array([0.5, 1.5, 2.5, 3.5, 1, 2, 3]) : fromF64Hex(fixture.hexbin.x_f64_hex);
  const y = fixture == null ? new Float64Array([0.5, 0.5, 0.5, 0.5, 2, 2, 2]) : fromF64Hex(fixture.hexbin.y_f64_hex);
  const range = fixture?.hexbin?.range ?? [
    [0, 4],
    [0, 3],
  ];
  const gridsize = fixture?.hexbin?.gridsize ?? [8, 6];
  const hx = composeHexbin(x, y, { range, gridsize, mincnt: 0, reduce: "count" });
  if (fixture != null) {
    assert.equal(hx.centersX.length, fixture.hexbin.n_bins);
    assert.equal(f64Hex(hx.centersX), fixture.hexbin.centers_x_f64_hex);
    assert.equal(f64Hex(hx.centersY), fixture.hexbin.centers_y_f64_hex);
    assert.equal(f64Hex(hx.metrics), fixture.hexbin.metrics_f64_hex);
    assert.equal(f64Hex(hx.counts), fixture.hexbin.counts_f64_hex);
    assert.equal(hx.dx, fixture.hexbin.dx);
    assert.equal(hx.dy, fixture.hexbin.dy);
  }
  const fig = hexbinChart(x, y, { range, gridsize });
  assert.equal(fig.buildPayload().spec.traces[0].kind, "hexbin");
});

test("violin density matches Python fixture when present", () => {
  const fixture = loadFixture();
  const values =
    fixture == null
      ? new Float64Array([1, 1.5, 2, 2, 2.5, 3, 3, 3.5, 4, 4.5, 5])
      : fromF64Hex(fixture.violin.values_f64_hex);
  const bins = fixture?.violin?.bins ?? 16;
  const v = composeViolin(values, { bins });
  if (fixture != null) {
    assert.equal(f64Hex(v.edges), fixture.violin.edges_f64_hex);
    assert.equal(f64Hex(v.density), fixture.violin.density_f64_hex);
  }
  const fig = violinChart(values, { bins });
  assert.equal(fig.buildPayload().spec.traces[0].kind, "violin");
});

function f64Hex(arr) {
  return Buffer.from(arr.buffer, arr.byteOffset, arr.byteLength).toString("hex");
}
