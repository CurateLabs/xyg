import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

import {
  DECIMATION_THRESHOLD,
  PROTOCOL_VERSION,
  composeHistogram,
  composeLine,
  encodeScatterPositions,
  figure,
  graphChart,
  histogramChart,
  lineChart,
  m4DecimateLine,
  scatterChart,
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
