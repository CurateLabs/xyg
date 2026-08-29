#!/usr/bin/env node
/**
 * Emit JSON for scatter / line-M4 / histogram + batch-2 mark goldens — consumed by
 * tests/test_node_mark_parity.py and optionally compared to fixtures.
 *
 * Usage (from repo root):
 *   node packages/xy-node/scripts/mark_parity_golden.mjs
 */
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../..");
const xyNode = await import(path.join(root, "packages/xy-node/src/index.js"));
const {
  PROTOCOL_VERSION,
  abiVersion,
  encodeScatterPositions,
  m4DecimateLine,
  composeHistogram,
  prepareLineSeries,
  composeArea,
  composeBar,
  composeBox,
  computeEcdf,
  composeSegments,
  composeHeatmap,
  composeHexbin,
  composeViolin,
  weightedEcdf,
  DECIMATION_THRESHOLD,
  F64_EPS,
} = xyNode;

function f32Hex(arr) {
  const buf = Buffer.from(arr.buffer, arr.byteOffset, arr.byteLength);
  return buf.toString("hex");
}

function f64Hex(arr) {
  const buf = Buffer.from(arr.buffer, arr.byteOffset, arr.byteLength);
  return buf.toString("hex");
}

function u8Hex(arr) {
  const buf = Buffer.from(arr.buffer, arr.byteOffset, arr.byteLength);
  return buf.toString("hex");
}

// --- Small scatter encode (bit-identical offset-encoded f32) ---
const scatterX = new Float64Array([0.0, 1.0, 2.0, 3.0, 4.0, -1.5, 10.25]);
const scatterY = new Float64Array([0.0, 0.5, 1.0, 1.5, 2.0, 3.25, -4.0]);
const scatterEnc = encodeScatterPositions(scatterX, scatterY);

// --- M4 line decimation index count for a monotone series ---
const nLine = 20_000;
const lineX = new Float64Array(nLine);
const lineY = new Float64Array(nLine);
for (let i = 0; i < nLine; i += 1) {
  lineX[i] = i;
  lineY[i] = Math.sin(i / 100.0) + i / nLine;
}
const nBuckets = 640;
const x0 = 0.0;
const x1 = nLine - 1;
const m4 = m4DecimateLine(lineX, lineY, {
  x0,
  x1,
  nBuckets,
  threshold: DECIMATION_THRESHOLD,
});

// --- histogram_uniform counts for fixed edges ---
const histValues = new Float64Array([
  0.1, 0.2, 0.5, 0.9, 1.1, 1.4, 1.9, 2.0, 2.5, 3.0, 3.5, 4.0, 4.5, 5.0, -0.5, 5.5,
]);
const histLo = 0.0;
const histHi = 5.0;
const histBins = 5;
const hist = composeHistogram(histValues, {
  bins: histBins,
  range: [histLo, histHi],
  density: false,
});

// --- area stable sort ---
const areaX = new Float64Array([2.0, 0.0, 1.0]);
const areaY = new Float64Array([3.0, 1.0, 2.0]);
const areaBase = 0.5;
const areaPrepared = prepareLineSeries(areaX, areaY);
const areaComposed = composeArea(areaX, areaY, { base: areaBase });

// --- bar rects ---
const barX = new Float64Array([0.0, 1.0, 2.0]);
const barY = new Float64Array([1.0, 3.0, 2.0]);
const barWidth = 0.8;
const barComposed = composeBar(barX, barY, { width: barWidth });

// --- box stats ---
const boxValues = new Float64Array([1, 2, 2, 3, 4, 5, 6, 7, 8, 100]);
const boxComposed = composeBox(boxValues);

// --- ecdf exact ---
const ecdfValues = new Float64Array([3.0, 1.0, 2.0, 1.0, 3.0]);
const ecdf = computeEcdf(ecdfValues);
const ecdfNative = weightedEcdf(
  ecdfValues,
  new Float64Array(ecdfValues.length).fill(1.0),
);

// --- segments ---
const segX0 = new Float64Array([0.0, 1.0]);
const segY0 = new Float64Array([0.0, 1.0]);
const segX1 = new Float64Array([1.0, 2.0]);
const segY1 = new Float64Array([1.0, 0.0]);
const segComposed = composeSegments(segX0, segY0, segX1, segY1);

// --- heatmap rgba ---
const heatRows = 3;
const heatCols = 3;
const heatZ = new Float64Array([0.0, 0.5, 1.0, 0.25, 0.75, 0.5, 1.0, 0.0, 0.5]);
const heatStops = Uint8Array.from([0, 0, 255, 255, 255, 255, 255, 0, 0]);
const heatComposed = composeHeatmap(heatZ, {
  rows: heatRows,
  cols: heatCols,
  colormapStops: heatStops,
});

// --- hexbin ---
const hexX = new Float64Array([0.5, 1.5, 2.5, 3.5, 1.0, 2.0, 3.0]);
const hexY = new Float64Array([0.5, 0.5, 0.5, 0.5, 2.0, 2.0, 2.0]);
const hexRange = [
  [0.0, 4.0],
  [0.0, 3.0],
];
const hexGridsize = [8, 6];
const hexComposed = composeHexbin(hexX, hexY, {
  gridsize: hexGridsize,
  range: hexRange,
  mincnt: 0,
  reduce: "count",
});

// --- violin ---
const violinValues = new Float64Array([1, 1.5, 2, 2, 2.5, 3, 3, 3.5, 4, 4.5, 5]);
const violinBins = 16;
const violinComposed = composeViolin(violinValues, { bins: violinBins });

const out = {
  protocol: PROTOCOL_VERSION,
  abi_version: abiVersion(),
  scatter: {
    x_f64_hex: f64Hex(scatterX),
    y_f64_hex: f64Hex(scatterY),
    x_f32_hex: f32Hex(scatterEnc.x),
    y_f32_hex: f32Hex(scatterEnc.y),
    x_meta: scatterEnc.xMeta,
    y_meta: scatterEnc.yMeta,
    x_bounds: scatterEnc.xBounds,
    y_bounds: scatterEnc.yBounds,
  },
  line_m4: {
    n: nLine,
    n_buckets: nBuckets,
    x0,
    x1,
    x1_plus_eps: x1 + F64_EPS,
    threshold: DECIMATION_THRESHOLD,
    tier: m4.tier,
    index_count: m4.indices?.length ?? m4.x.length,
    mark_count: m4.x.length,
  },
  histogram: {
    lo: histLo,
    hi: histHi,
    n_bins: histBins,
    density: false,
    values_f64_hex: f64Hex(histValues),
    counts: [...hist.counts],
    edges: [...hist.edges],
    total: hist.total,
    counts_f64_hex: f64Hex(hist.counts),
    edges_f64_hex: f64Hex(hist.edges),
  },
  area: {
    x_f64_hex: f64Hex(areaX),
    y_f64_hex: f64Hex(areaY),
    base: areaBase,
    x_sorted_f64_hex: f64Hex(areaPrepared.x),
    y_sorted_f64_hex: f64Hex(areaPrepared.y),
    composed_x_f64_hex: f64Hex(areaComposed.traces[0].x),
    composed_base_len: areaComposed.traces[0].base.length,
  },
  bar: {
    x_f64_hex: f64Hex(barX),
    y_f64_hex: f64Hex(barY),
    width: barWidth,
    x0_f64_hex: f64Hex(barComposed.traces[0].x0),
    x1_f64_hex: f64Hex(barComposed.traces[0].x1),
    y0_f64_hex: f64Hex(barComposed.traces[0].y0),
    y1_f64_hex: f64Hex(barComposed.traces[0].y1),
  },
  box: {
    values_f64_hex: f64Hex(boxValues),
    q1: boxComposed.stats.q1,
    median: boxComposed.stats.median,
    q3: boxComposed.stats.q3,
    low: boxComposed.stats.low,
    high: boxComposed.stats.high,
    outliers_f64_hex: f64Hex(boxComposed.stats.outliers),
    n_outliers: boxComposed.stats.outliers.length,
  },
  ecdf: {
    values_f64_hex: f64Hex(ecdfValues),
    x_f64_hex: f64Hex(ecdfNative.values),
    y_f64_hex: f64Hex(ecdfNative.cumulative),
    n_points: ecdfNative.values.length,
    step_x_f64_hex: f64Hex(ecdf.x),
    step_y_f64_hex: f64Hex(ecdf.y),
  },
  segments: {
    x0_f64_hex: f64Hex(segX0),
    y0_f64_hex: f64Hex(segY0),
    x1_f64_hex: f64Hex(segX1),
    y1_f64_hex: f64Hex(segY1),
    n: segComposed.traces[0].x0.length,
  },
  heatmap: {
    rows: heatRows,
    cols: heatCols,
    z_f64_hex: f64Hex(heatZ),
    stops_u8_hex: u8Hex(heatStops),
    rgba_u8_hex: u8Hex(heatComposed.traces[0].rgba),
  },
  hexbin: {
    x_f64_hex: f64Hex(hexX),
    y_f64_hex: f64Hex(hexY),
    gridsize: hexGridsize,
    range: hexRange,
    mincnt: 0,
    reduce: "count",
    n_bins: hexComposed.centersX.length,
    centers_x_f64_hex: f64Hex(hexComposed.centersX),
    centers_y_f64_hex: f64Hex(hexComposed.centersY),
    metrics_f64_hex: f64Hex(hexComposed.metrics),
    counts_f64_hex: f64Hex(hexComposed.counts),
    dx: hexComposed.dx,
    dy: hexComposed.dy,
  },
  violin: {
    values_f64_hex: f64Hex(violinValues),
    bins: violinBins,
    edges_f64_hex: f64Hex(violinComposed.edges),
    density_f64_hex: f64Hex(violinComposed.density),
    n_rects: violinComposed.traces[0].x0.length,
  },
};

process.stdout.write(`${JSON.stringify(out)}\n`);
