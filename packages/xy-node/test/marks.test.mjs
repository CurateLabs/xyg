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
  assert.equal(composed.traces[0].kind, "ecdf");
  assert.equal(composed.traces[0].x.length, step.x.length);
  const fig = ecdfChart(values);
  assert.equal(fig.buildPayload().spec.traces[0].kind, "ecdf");
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
