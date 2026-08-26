/**
 * Offset-encoded f32 geometry (§4/§16) and shared encode helpers.
 * Bit-identical to python/xyg/lod.encode_f32_values when calling xyg_encode_f32.
 */
import { pointer, xyEncodeF32, xyIsSorted, xyMinMax, xyM4Points, xyM4Indices, xyHistogramUniform, xyNormalizeF32, xyHexbin, xyViolinDensity, xyViolinRects, xyHistogramEdges, xyBoxGeometry, xyBoxStats, xyQuantiles, xyWindRoseBins, xyContourfDensify, xyContourfBands, xyBarStack, xyBinnedEcdf, xyWeightedEcdf, xyHeatmapRgba, xyBin2d, xyDensityLogU8, xyMarchingSquares, xyLodPlan, xyDrillDecision, xyStreamNew, xyStreamAppend, xyStreamSeal, xyStreamFree, xyStreamLen, xyStreamCapacity, xyStreamCopy } from "./native.js";

export const PROTOCOL_VERSION = 12;
export const DECIMATION_THRESHOLD = 10_000;
export const SCATTER_DENSITY_THRESHOLD = 200_000;
export const DIRECT_SOFT_CEILING = 2_000_000;
/** Default density grid (w, h) matching Python `config.DENSITY_GRID`. */
export const DENSITY_GRID = Object.freeze([512, 384]);
export const DENSITY_TARGET_POINTS_PER_CELL = 16;
export const DRILL_EXIT_FACTOR = 1.15;
/** Tier-3 pyramid thresholds — lockstep with `python/xyg/config.py`. */
export const PYRAMID_MIN_POINTS = 2_000_000;
export const PYRAMID_BASE_DIM = 2048;
export const PYRAMID_NO_RESCAN_ROWS = 200_000_000;
export const PYRAMID_MAX_DIM = 16384;
/** Phase-4 resident-tile byte budget (roadmap D2); mirrored via xyTileBudgetSet. */
export const PYRAMID_RESIDENT_BYTES = 512 * (1 << 20);
export const F32_SAFE_MAG = 1e37;
export const LOG_FAMILY_SCALES = Object.freeze(["log", "symlog"]);

export const DEFAULT_PALETTE = Object.freeze([
  "#3987e5",
  "#008300",
  "#d55181",
  "#c48300",
  "#199e70",
  "#d95926",
  "#9085e9",
  "#e66767",
]);

export function pinsOffsetToZero(scale) {
  return LOG_FAMILY_SCALES.includes(scale);
}

export function geometryOffset(scale, lo, hi) {
  if (pinsOffsetToZero(scale) || !Number.isFinite(lo) || !Number.isFinite(hi)) {
    return 0.0;
  }
  return (lo + hi) / 2.0;
}

export function f32SafeScale(offset, lo, hi) {
  const half = Math.max(Math.abs(lo - offset), Math.abs(hi - offset));
  if (!Number.isFinite(half) || half <= F32_SAFE_MAG) {
    return 1.0;
  }
  return F32_SAFE_MAG / half;
}

export function asF64Array(value, name = "values") {
  if (value instanceof Float64Array) {
    return value;
  }
  if (value == null) {
    return new Float64Array(0);
  }
  if (ArrayBuffer.isView(value)) {
    return Float64Array.from(value, (item) => Number(item));
  }
  return Float64Array.from(value, (item) => {
    const number = Number(item);
    if (!Number.isFinite(number) && number !== number) {
      return Number.NaN;
    }
    return number;
  });
}

export function minMax(data) {
  const arr = asF64Array(data);
  if (arr.length === 0) {
    return null;
  }
  const lo = new Float64Array(1);
  const hi = new Float64Array(1);
  const ok = xyMinMax(f64Ptr(arr), BigInt(arr.length), f64Ptr(lo), f64Ptr(hi));
  if (ok !== 1) {
    return null;
  }
  return [lo[0], hi[0]];
}

export function isSorted(data) {
  const arr = asF64Array(data);
  if (arr.length <= 1) {
    return true;
  }
  return xyIsSorted(f64Ptr(arr), BigInt(arr.length)) === 1;
}

export function encodeF32(data, offset, scale = 1.0) {
  const arr = asF64Array(data);
  if (arr.length === 0) {
    return new Float32Array(0);
  }
  const out = new Float32Array(arr.length);
  const ok = xyEncodeF32(f64Ptr(arr), BigInt(arr.length), Number(offset), Number(scale), f32Ptr(out));
  if (ok !== 1) {
    throw new Error("xyg_encode_f32 failed");
  }
  return out;
}

export function encodeF32Values(values, offset, lo, hi, { kind = null } = {}) {
  const vals = asF64Array(values);
  const offsetF = Number(offset);
  const scale = f32SafeScale(offsetF, Number(lo), Number(hi));
  const encoded = vals.length === 0 ? new Float32Array(0) : encodeF32(vals, offsetF, scale);
  const meta = { offset: offsetF, scale };
  if (kind != null) {
    meta.kind = kind;
  }
  return { values: encoded, meta, length: encoded.length };
}

export function m4Points(x, y, x0, x1, nBuckets) {
  const xa = asF64Array(x);
  const ya = asF64Array(y);
  if (xa.length !== ya.length) {
    throw new RangeError("m4Points x/y length mismatch");
  }
  const cap = nBuckets * 4;
  const outX = new Float64Array(cap);
  const outY = new Float64Array(cap);
  const written = Number(
    xyM4Points(
      f64Ptr(xa),
      f64Ptr(ya),
      BigInt(xa.length),
      Number(x0),
      Number(x1),
      BigInt(nBuckets),
      f64Ptr(outX),
      f64Ptr(outY),
    ),
  );
  if (written === Number.MAX_SAFE_INTEGER || !Number.isFinite(written) || written < 0) {
    // usize::MAX from Rust — invalid args
    throw new Error("xyg_m4_points failed");
  }
  return [outX.subarray(0, written), outY.subarray(0, written)];
}

export function m4Indices(x, y, x0, x1, nBuckets) {
  const xa = asF64Array(x);
  const ya = asF64Array(y);
  const cap = nBuckets * 4;
  const out = new Uint32Array(cap);
  const written = Number(
    xyM4Indices(
      f64Ptr(xa),
      f64Ptr(ya),
      BigInt(xa.length),
      Number(x0),
      Number(x1),
      BigInt(nBuckets),
      u32Ptr(out),
    ),
  );
  if (!Number.isFinite(written) || written < 0) {
    throw new Error("xyg_m4_indices failed");
  }
  return out.subarray(0, written);
}

export function histogramUniform(data, lo, hi, nBins, { density = false } = {}) {
  const arr = asF64Array(data);
  const counts = new Float64Array(nBins);
  const total = Number(
    xyHistogramUniform(
      f64Ptr(arr),
      BigInt(arr.length),
      Number(lo),
      Number(hi),
      BigInt(nBins),
      density ? 1 : 0,
      f64Ptr(counts),
    ),
  );
  if (!Number.isFinite(total) || total < 0) {
    throw new Error("xyg_histogram_uniform failed");
  }
  const edges = new Float64Array(nBins + 1);
  const width = (hi - lo) / nBins;
  for (let i = 0; i <= nBins; i += 1) {
    edges[i] = lo + i * width;
  }
  return { counts, edges, total };
}

/** NumPy-compatible auto/sturges edges (`method`: `"auto"` | `"sturges"`). */
export function histogramEdges(data, { range = null, method = "auto" } = {}) {
  const arr = asF64Array(data);
  const methodId = method === "sturges" ? 1 : method === "auto" ? 0 : -1;
  if (methodId < 0) {
    throw new Error("histogramEdges method must be 'auto' or 'sturges'");
  }
  const useRange = range == null ? 0 : 1;
  const lo = range == null ? 0 : Number(range[0]);
  const hi = range == null ? 0 : Number(range[1]);
  // ABI 98 caps Rust auto resolution at 10,000 bins (10,001 edges).
  const capacity = 10_001;
  const out = new Float64Array(capacity);
  const written = Number(
    xyHistogramEdges(
      f64Ptr(arr),
      BigInt(arr.length),
      lo,
      hi,
      useRange,
      methodId,
      f64Ptr(out),
      BigInt(capacity),
    ),
  );
  if (!Number.isFinite(written) || written < 0 || written > capacity) {
    throw new Error("xyg_histogram_edges failed");
  }
  return out.subarray(0, written);
}

const HEX_REDUCE = Object.freeze({ count: 0, mean: 1, sum: 2 });

/** Matplotlib-compatible hexbin; `reduce` is count|mean|sum. */
export function hexbin(x, y, { gridsize, range, mincnt = 0, C = null, reduce = "count" } = {}) {
  const xa = asF64Array(x);
  const ya = asF64Array(y);
  if (xa.length !== ya.length) {
    throw new RangeError("hexbin x/y length mismatch");
  }
  const [w, h] = Array.isArray(gridsize) ? gridsize : [gridsize, gridsize];
  const [[x0, x1], [y0, y1]] = range;
  const reduceId = HEX_REDUCE[reduce];
  if (reduceId == null) {
    throw new Error("hexbin reduce must be count, mean, or sum");
  }
  const ca = C == null ? null : asF64Array(C);
  if (ca != null && ca.length !== xa.length) {
    throw new RangeError("hexbin C length mismatch");
  }
  const capacity = (w + 1) * (h + 1) + w * h;
  const outCx = new Float64Array(capacity);
  const outCy = new Float64Array(capacity);
  const outMetric = new Float64Array(capacity);
  const outCounts = new Float64Array(capacity);
  const dx = new Float64Array(1);
  const dy = new Float64Array(1);
  const written = Number(
    xyHexbin(
      f64Ptr(xa),
      f64Ptr(ya),
      ca == null ? null : f64Ptr(ca),
      BigInt(xa.length),
      BigInt(w),
      BigInt(h),
      Number(x0),
      Number(x1),
      Number(y0),
      Number(y1),
      BigInt(mincnt),
      reduceId,
      f64Ptr(outCx),
      f64Ptr(outCy),
      f64Ptr(outMetric),
      f64Ptr(outCounts),
      BigInt(capacity),
      f64Ptr(dx),
      f64Ptr(dy),
    ),
  );
  if (!Number.isFinite(written) || written < 0 || written > capacity) {
    throw new Error("xy_hexbin failed");
  }
  return {
    centersX: outCx.subarray(0, written),
    centersY: outCy.subarray(0, written),
    metrics: outMetric.subarray(0, written),
    counts: outCounts.subarray(0, written),
    dx: dx[0],
    dy: dy[0],
  };
}

/** Violin density: edges (n_bins+1) + smoothed density (n_bins). */
export function violinDensity(data, nBins) {
  const arr = asF64Array(data);
  if (!Number.isInteger(nBins) || nBins < 4 || nBins > 1024) {
    throw new RangeError("violinDensity nBins must be in 4..=1024");
  }
  const edges = new Float64Array(nBins + 1);
  const density = new Float64Array(nBins);
  const ok = xyViolinDensity(
    f64Ptr(arr),
    BigInt(arr.length),
    BigInt(nBins),
    f64Ptr(edges),
    f64Ptr(density),
  );
  if (ok !== 1) {
    throw new Error("xy_violin_density failed");
  }
  return { edges, density };
}

export function violinRects(groups, positions, nBins, width, orientation) {
  const offsets = new BigUint64Array(groups.length + 1);
  let total = 0;
  for (let i = 0; i < groups.length; i += 1) { total += groups[i].length; offsets[i + 1] = BigInt(total); }
  const values = new Float64Array(total); let at = 0;
  for (const group of groups) { values.set(group, at); at += group.length; }
  const centers = Float64Array.from(positions);
  const call = (x0,y0,x1,y1,active,edges,density,cap) => Number(xyViolinRects(
    f64Ptr(values), BigInt(values.length), pointer(offsets, "size_t *"), BigInt(offsets.length),
    f64Ptr(centers), BigInt(centers.length), BigInt(nBins), Number(width), orientation === "vertical" ? 0 : orientation === "horizontal" ? 1 : 2,
    f64Ptr(x0), f64Ptr(y0), f64Ptr(x1), f64Ptr(y1), u32Ptr(active), f64Ptr(edges), f64Ptr(density), BigInt(cap),
  ));
  const required = call(null,null,null,null,null,null,null,0);
  if (!Number.isSafeInteger(required) || required <= 0 || required > 10_000) throw new RangeError("invalid bounded violin geometry");
  const activeCount = required / nBins;
  const x0=new Float64Array(required), y0=new Float64Array(required), x1=new Float64Array(required), y1=new Float64Array(required);
  const active=new Uint32Array(activeCount), edges=new Float64Array(activeCount*(nBins+1)), density=new Float64Array(required);
  if (call(x0,y0,x1,y1,active,edges,density,required) !== required) throw new Error("xy_violin_rects failed");
  return { x0,y0,x1,y1,activeGroups:active,
    groupEdges:Array.from({length:activeCount},(_,i)=>edges.slice(i*(nBins+1),(i+1)*(nBins+1))),
    groupDensity:Array.from({length:activeCount},(_,i)=>density.slice(i*nBins,(i+1)*nBins)) };
}

/** Weighted ECDF: sorted unique values + cumulative mass in [0, 1]. */
export function weightedEcdf(values, weights) {
  const vals = asF64Array(values);
  const wts = asF64Array(weights);
  if (vals.length !== wts.length || vals.length === 0) {
    throw new RangeError("weightedEcdf values/weights must have equal non-zero length");
  }
  const outValues = new Float64Array(vals.length);
  const cumulative = new Float64Array(vals.length);
  const written = Number(
    xyWeightedEcdf(
      f64Ptr(vals),
      f64Ptr(wts),
      BigInt(vals.length),
      f64Ptr(outValues),
      f64Ptr(cumulative),
    ),
  );
  if (!Number.isFinite(written) || written < 0 || written > vals.length) {
    throw new Error("xy_weighted_ecdf failed");
  }
  return {
    values: outValues.subarray(0, written),
    cumulative: cumulative.subarray(0, written),
  };
}

/** Uniformly binned ECDF with Rust-owned finite filtering and compaction. */
export function binnedEcdf(values, nBins, { range = null } = {}) {
  const vals = asF64Array(values);
  const bins = Number(nBins);
  if (!Number.isInteger(bins) || bins <= 0) {
    throw new RangeError("ecdf bins must be a positive integer");
  }
  if (bins > 10_000) {
    throw new RangeError("ecdf bins must be <= 10000");
  }
  const useRange = range == null ? 0 : 1;
  const lo = range == null ? 0 : Number(range[0]);
  const hi = range == null ? 0 : Number(range[1]);
  const capacity = bins + 1;
  const x = new Float64Array(capacity);
  const cumulative = new Float64Array(capacity);
  const written = Number(
    xyBinnedEcdf(
      f64Ptr(vals),
      BigInt(vals.length),
      BigInt(bins),
      lo,
      hi,
      useRange,
      f64Ptr(x),
      f64Ptr(cumulative),
      BigInt(capacity),
    ),
  );
  if (!Number.isSafeInteger(written) || written <= 0 || written > capacity) {
    throw new RangeError("ecdf values must contain a finite representable distribution");
  }
  return { x: x.slice(0, written), cumulative: cumulative.slice(0, written) };
}

/** Map scalar heatmap grid to vertically flipped RGBA bytes (h, w, 4). */
export function heatmapRgba(raw, w, h, stops, alpha = 255) {
  const ww = Number(w);
  const hh = Number(h);
  const values = asF64Array(raw);
  if (values.length !== ww * hh) {
    throw new RangeError("heatmapRgba scalar count must match width * height");
  }
  const stopArr = stops instanceof Uint8Array ? stops : Uint8Array.from(stops);
  if (stopArr.length % 3 !== 0 || stopArr.length < 3) {
    throw new RangeError("heatmapRgba stops must be a non-empty multiple of 3");
  }
  const stopCount = stopArr.length / 3;
  const out = new Uint8Array(hh * ww * 4);
  const ok = xyHeatmapRgba(
    f64Ptr(values),
    BigInt(ww),
    BigInt(hh),
    u8Ptr(stopArr),
    BigInt(stopCount),
    Number(alpha),
    u8Ptr(out),
  );
  if (ok !== 1) {
    throw new Error("xy_heatmap_rgba failed");
  }
  return { rgba: out, width: ww, height: hh };
}

export function boxStats(data) {
  const arr = asF64Array(data);
  const stats = new Float64Array(5);
  const outliers = new Float64Array(arr.length);
  const nOut = new BigUint64Array(1);
  const ok = xyBoxStats(
    f64Ptr(arr),
    BigInt(arr.length),
    f64Ptr(stats),
    arr.length ? f64Ptr(outliers) : null,
    BigInt(arr.length),
    pointer(nOut, "size_t *"),
  );
  if (ok !== 1) {
    throw new Error("xy_box_stats failed");
  }
  return {
    q1: stats[0],
    median: stats[1],
    q3: stats[2],
    low: stats[3],
    high: stats[4],
    outliers: outliers.subarray(0, Number(nOut[0])),
  };
}

export function boxGeometry(groups, positions, width, orientation, showOutliers = true) {
  const offsets = new BigUint64Array(groups.length + 1);
  let total = 0;
  for (let index = 0; index < groups.length; index += 1) {
    total += groups[index].length;
    offsets[index + 1] = BigInt(total);
  }
  const values = new Float64Array(total);
  let at = 0;
  for (const group of groups) { values.set(group, at); at += group.length; }
  const centers = Float64Array.from(positions);
  const nOutliers = new BigUint64Array(1);
  const call = (active, records, outlierOffsets, outlierRecords, groupCap, outlierCap) => Number(xyBoxGeometry(
    f64Ptr(values), BigInt(values.length), pointer(offsets, "size_t *"), BigInt(offsets.length),
    f64Ptr(centers), BigInt(centers.length), Number(width),
    orientation === "vertical" ? 0 : orientation === "horizontal" ? 1 : 2,
    showOutliers ? 1 : 0, pointer(nOutliers, "size_t *"), u32Ptr(active), f64Ptr(records),
    pointer(outlierOffsets, "size_t *"), f64Ptr(outlierRecords), BigInt(groupCap), BigInt(outlierCap),
  ));
  const required = call(null, null, null, null, 0, 0);
  const outliers = Number(nOutliers[0]);
  if (!Number.isSafeInteger(required) || required <= 0 || required > 2_000 ||
      !Number.isSafeInteger(outliers) || outliers < 0 || required * 5 + outliers > 10_000) {
    throw new RangeError("invalid bounded box geometry");
  }
  const active = new Uint32Array(required);
  const records = new Float64Array(required * 25);
  const outlierOffsets = new BigUint64Array(required + 1);
  const outlierRecords = new Float64Array(outliers * 3);
  if (call(active, records, outlierOffsets, outlierRecords, required, outliers) !== required) {
    throw new Error("xy_box_geometry failed");
  }
  const body = [0, 1, 2, 3].map(() => new Float64Array(required));
  const whiskers = [0, 1, 2, 3].map(() => new Float64Array(required * 3));
  const medians = [0, 1, 2, 3].map(() => new Float64Array(required));
  const groupStats = [];
  for (let group = 0; group < required; group += 1) {
    const base = group * 25;
    for (let coordinate = 0; coordinate < 4; coordinate += 1) {
      body[coordinate][group] = records[base + 5 + coordinate];
      medians[coordinate][group] = records[base + 21 + coordinate];
      for (let segment = 0; segment < 3; segment += 1) {
        whiskers[coordinate][group * 3 + segment] = records[base + 9 + segment * 4 + coordinate];
      }
    }
    const start = Number(outlierOffsets[group]);
    const end = Number(outlierOffsets[group + 1]);
    groupStats.push({
      q1: records[base], median: records[base + 1], q3: records[base + 2],
      low: records[base + 3], high: records[base + 4],
      outliers: Float64Array.from({ length: end - start }, (_, index) => outlierRecords[(start + index) * 3]),
    });
  }
  return {
    activeGroups: active, groupStats, body, whiskers, medians,
    outlierX: showOutliers ? Float64Array.from({ length: outliers }, (_, index) => outlierRecords[index * 3 + 1]) : new Float64Array(),
    outlierY: showOutliers ? Float64Array.from({ length: outliers }, (_, index) => outlierRecords[index * 3 + 2]) : new Float64Array(),
  };
}

export function quantiles(data, probs) {
  const arr = asF64Array(data);
  const p = asF64Array(probs);
  const out = new Float64Array(p.length);
  const written = Number(xyQuantiles(f64Ptr(arr), BigInt(arr.length), f64Ptr(p), BigInt(p.length), f64Ptr(out)));
  if (!Number.isFinite(written) || written < 0) {
    throw new Error("xy_quantiles failed");
  }
  return out;
}


/** Wind-rose directional/speed binning; `speedEdges` omitted → auto quartiles. */
export function windRoseBins(directions, speeds, sectors, speedEdges = null) {
  const dirs = asF64Array(directions);
  const mags = asF64Array(speeds);
  if (dirs.length !== mags.length) {
    throw new RangeError("windRoseBins directions/speeds length mismatch");
  }
  if (!Number.isInteger(sectors) || sectors < 3 || sectors > 3600) {
    throw new RangeError("windRoseBins sectors must be in 3..=3600");
  }
  const edgesIn = speedEdges == null ? null : asF64Array(speedEdges);
  const nEdges = edgesIn == null ? 0 : edgesIn.length;
  const capacityEdges = edgesIn == null ? 4 : Math.max(nEdges, 1);
  const outEdges = new Float64Array(capacityEdges);
  const outCentres = new Float64Array(sectors);
  const capacityCounts = capacityEdges * sectors;
  const outCounts = new Float64Array(capacityCounts);
  const nObs = new BigUint64Array(1);
  const written = Number(
    xyWindRoseBins(
      f64Ptr(dirs),
      f64Ptr(mags),
      BigInt(dirs.length),
      BigInt(sectors),
      edgesIn == null ? null : f64Ptr(edgesIn),
      BigInt(nEdges),
      f64Ptr(outEdges),
      BigInt(capacityEdges),
      f64Ptr(outCentres),
      f64Ptr(outCounts),
      BigInt(capacityCounts),
      pointer(nObs, "size_t *"),
    ),
  );
  if (!Number.isFinite(written) || written < 0 || written > capacityEdges) {
    throw new Error("xy_wind_rose_bins failed");
  }
  return {
    edges: outEdges.subarray(0, written),
    centres: outCentres,
    counts: outCounts.subarray(0, written * sectors),
    nObs: Number(nObs[0]),
    sectors,
  };
}

/** Bilinear contourf densify (paired with contourfBands for corner-mask). */
export function contourfDensify(z, rows, cols, xpos, ypos) {
  const zz = asF64Array(z);
  const xx = asF64Array(xpos);
  const yy = asF64Array(ypos);
  if (zz.length !== rows * cols || xx.length !== cols || yy.length !== rows) {
    throw new RangeError("contourfDensify shape mismatch");
  }
  const sampleCount = (size) => {
    if (size > 512) return size;
    return Math.min(512, Math.max(256, (size - 1) * 8 + 1));
  };
  const outRows = sampleCount(rows);
  const outCols = sampleCount(cols);
  const outZ = new Float64Array(outRows * outCols);
  const outX = new Float64Array(outCols);
  const outY = new Float64Array(outRows);
  const gotRows = new BigUint64Array(1);
  const gotCols = new BigUint64Array(1);
  const ok = xyContourfDensify(
    f64Ptr(zz),
    BigInt(rows),
    BigInt(cols),
    f64Ptr(xx),
    f64Ptr(yy),
    f64Ptr(outZ),
    f64Ptr(outX),
    f64Ptr(outY),
    BigInt(outZ.length),
    BigInt(outX.length),
    BigInt(outY.length),
    pointer(gotRows, "size_t *"),
    pointer(gotCols, "size_t *"),
  );
  if (ok !== 1) {
    throw new Error("xy_contourf_densify failed");
  }
  const r = Number(gotRows[0]);
  const c = Number(gotCols[0]);
  return {
    z: outZ.subarray(0, r * c),
    x: outX.subarray(0, c),
    y: outY.subarray(0, r),
    rows: r,
    cols: c,
  };
}

const BAR_MODES = { grouped: 0, stacked: 1, normalized: 2 };
const BAR_ORIENT = { vertical: 0, horizontal: 1 };

/** Grouped / stacked / normalized bar rect corners via xyg_bar_stack. */
export function barStack(pos, values, nSeries, width = 0.8, base = 0, mode = "grouped", orientation = "vertical") {
  const p = asF64Array(pos);
  const vals = asF64Array(values);
  const nItems = p.length;
  if (!Number.isInteger(nSeries) || nSeries < 1 || vals.length !== nSeries * nItems) {
    throw new RangeError("barStack values must be row-major nSeries * nItems");
  }
  if (!(mode in BAR_MODES) || !(orientation in BAR_ORIENT)) {
    throw new RangeError("barStack mode/orientation invalid");
  }
  const widthArr = typeof width === "number" ? new Float64Array([width]) : asF64Array(width);
  const baseArr = typeof base === "number" ? new Float64Array([base]) : asF64Array(base);
  const outX0 = new Float64Array(nSeries * nItems);
  const outX1 = new Float64Array(nSeries * nItems);
  const outY0 = new Float64Array(nSeries * nItems);
  const outY1 = new Float64Array(nSeries * nItems);
  const ok = xyBarStack(
    f64Ptr(p),
    BigInt(nItems),
    f64Ptr(vals),
    BigInt(nSeries),
    f64Ptr(widthArr),
    BigInt(widthArr.length),
    f64Ptr(baseArr),
    BigInt(baseArr.length),
    BAR_MODES[mode],
    BAR_ORIENT[orientation],
    f64Ptr(outX0),
    f64Ptr(outX1),
    f64Ptr(outY0),
    f64Ptr(outY1),
  );
  if (ok !== 1) {
    throw new Error("xyg_bar_stack failed");
  }
  return { x0: outX0, x1: outX1, y0: outY0, y1: outY1, nSeries, nItems };
}

/** Corner-mask contourf band triangles via xy_contourf_bands. */
export function contourfBands(z, rows, cols, xpos, ypos, edges, { extendMin = false, extendMax = false } = {}) {
  const zz = asF64Array(z);
  const xx = asF64Array(xpos);
  const yy = asF64Array(ypos);
  const ee = asF64Array(edges);
  if (zz.length !== rows * cols || xx.length !== cols || yy.length !== rows || ee.length < 2) {
    throw new RangeError("contourfBands shape mismatch");
  }
  const needed = Number(
    xyContourfBands(
      f64Ptr(zz),
      BigInt(rows),
      BigInt(cols),
      f64Ptr(xx),
      f64Ptr(yy),
      f64Ptr(ee),
      BigInt(ee.length),
      extendMin ? 1 : 0,
      extendMax ? 1 : 0,
      null,
      null,
      null,
      null,
      null,
      null,
      null,
      0n,
    ),
  );
  if (!Number.isFinite(needed) || needed < 0) {
    throw new Error("xy_contourf_bands failed");
  }
  if (needed === 0) {
    return {
      x0: new Float64Array(0),
      y0: new Float64Array(0),
      x1: new Float64Array(0),
      y1: new Float64Array(0),
      x2: new Float64Array(0),
      y2: new Float64Array(0),
      slots: new BigInt64Array(0),
    };
  }
  const x0 = new Float64Array(needed);
  const y0 = new Float64Array(needed);
  const x1 = new Float64Array(needed);
  const y1 = new Float64Array(needed);
  const x2 = new Float64Array(needed);
  const y2 = new Float64Array(needed);
  const slots = new BigInt64Array(needed);
  const written = Number(
    xyContourfBands(
      f64Ptr(zz),
      BigInt(rows),
      BigInt(cols),
      f64Ptr(xx),
      f64Ptr(yy),
      f64Ptr(ee),
      BigInt(ee.length),
      extendMin ? 1 : 0,
      extendMax ? 1 : 0,
      f64Ptr(x0),
      f64Ptr(y0),
      f64Ptr(x1),
      f64Ptr(y1),
      f64Ptr(x2),
      f64Ptr(y2),
      pointer(slots, "int64_t *"),
      BigInt(needed),
    ),
  );
  if (written !== needed) {
    throw new Error("xy_contourf_bands inconsistent count");
  }
  return { x0, y0, x1, y1, x2, y2, slots };
}

/**
 * Axis-aligned 2-D density counts via `xyg_bin_2d` (row-major float grid).
 * @returns {Float32Array} length w*h
 */
export function bin2d(x, y, x0, x1, y0, y1, w, h) {
  const xa = asF64Array(x, "x");
  const ya = asF64Array(y, "y");
  if (xa.length !== ya.length) {
    throw new RangeError("bin2d x/y length mismatch");
  }
  const ww = Math.max(1, Math.floor(Number(w)));
  const hh = Math.max(1, Math.floor(Number(h)));
  const out = new Float32Array(ww * hh);
  const ok = xyBin2d(
    f64Ptr(xa),
    f64Ptr(ya),
    BigInt(xa.length),
    Number(x0),
    Number(x1),
    Number(y0),
    Number(y1),
    BigInt(ww),
    BigInt(hh),
    f32Ptr(out),
  );
  if (ok !== 1) {
    throw new Error("xyg_bin_2d failed");
  }
  return out;
}

/**
 * Encode a float density grid as log-u8 for the wire (§5 Tier 2).
 * @returns {{encoded: Uint8Array, max: number}}
 */
export function densityLogU8(grid) {
  const arr = grid instanceof Float32Array ? grid : Float32Array.from(grid, Number);
  const out = new Uint8Array(arr.length);
  const maxBuf = new Float64Array(1);
  const ok = xyDensityLogU8(f32Ptr(arr), BigInt(arr.length), u8Ptr(out), f64Ptr(maxBuf));
  if (ok !== 1) {
    throw new Error("xy_density_log_u8 failed");
  }
  return { encoded: out, max: maxBuf[0] };
}

/**
 * Regular-grid contour isolines via `xy_marching_squares`.
 * @returns {{x0: Float64Array, x1: Float64Array, y0: Float64Array, y1: Float64Array, levels: Float64Array}}
 */
export function marchingSquares(z, rows, cols, xCoords, yCoords, levels, { cornerMask = false } = {}) {
  const zz = asF64Array(z, "z");
  const xc = asF64Array(xCoords, "x_coords");
  const yc = asF64Array(yCoords, "y_coords");
  const lv = asF64Array(levels, "levels");
  const r = Math.floor(Number(rows));
  const c = Math.floor(Number(cols));
  if (zz.length !== r * c || r < 2 || c < 2) {
    throw new RangeError("marchingSquares z must be rows*cols with rows,cols ≥ 2");
  }
  if (xc.length !== c || yc.length !== r) {
    throw new RangeError("marchingSquares x/y coords must match cols/rows");
  }
  if (lv.length === 0 || lv.length > 256) {
    throw new RangeError("marchingSquares levels must contain 1..256 values");
  }
  let capacity = Math.max(64, (r - 1) * (c - 1) * lv.length);
  for (let attempt = 0; attempt < 2; attempt += 1) {
    const x0 = new Float64Array(capacity);
    const x1 = new Float64Array(capacity);
    const y0 = new Float64Array(capacity);
    const y1 = new Float64Array(capacity);
    const outLevels = new Float64Array(capacity);
    const written = Number(
      xyMarchingSquares(
        f64Ptr(zz),
        BigInt(r),
        BigInt(c),
        f64Ptr(xc),
        f64Ptr(yc),
        f64Ptr(lv),
        BigInt(lv.length),
        cornerMask ? 1 : 0,
        f64Ptr(x0),
        f64Ptr(x1),
        f64Ptr(y0),
        f64Ptr(y1),
        f64Ptr(outLevels),
        BigInt(capacity),
      ),
    );
    if (!Number.isFinite(written) || written < 0) {
      throw new Error("xy_marching_squares failed");
    }
    if (written <= capacity) {
      return {
        x0: x0.subarray(0, written),
        x1: x1.subarray(0, written),
        y0: y0.subarray(0, written),
        y1: y1.subarray(0, written),
        levels: outLevels.subarray(0, written),
      };
    }
    capacity = written;
  }
  throw new Error("xy_marching_squares inconsistent capacity");
}

/**
 * View LOD plan — Rust owns exact vs density mode + grid shape (§28).
 */
export function lodPlan(visible, budget, { inDrill = false, exitFactor = DRILL_EXIT_FACTOR, pxW = 640, pxH = 360, targetPerCell = DENSITY_TARGET_POINTS_PER_CELL } = {}) {
  const exact = new Int32Array(1);
  const mode = new Uint32Array(1);
  const gw = new Int32Array(1);
  const gh = new Int32Array(1);
  const ok = xyLodPlan(
    BigInt(visible),
    Number(budget),
    inDrill ? 1 : 0,
    Number(exitFactor),
    Math.floor(Number(pxW)),
    Math.floor(Number(pxH)),
    Number(targetPerCell),
    pointer(exact, "int32_t *"),
    u32Ptr(mode),
    pointer(gw, "int32_t *"),
    pointer(gh, "int32_t *"),
  );
  if (ok !== 1) {
    throw new Error("xy_lod_plan failed");
  }
  return {
    exact: exact[0] === 1,
    mode: mode[0],
    gridW: gw[0],
    gridH: gh[0],
  };
}

/**
 * Drill hysteresis decision — Rust owns exact/density toggle (§28).
 */
export function drillDecision(visible, budget, { inDrill = false, exitFactor = DRILL_EXIT_FACTOR } = {}) {
  const exact = new Int32Array(1);
  const ok = xyDrillDecision(
    BigInt(visible),
    Number(budget),
    inDrill ? 1 : 0,
    Number(exitFactor),
    pointer(exact, "int32_t *"),
  );
  if (ok !== 1) {
    throw new Error("xy_drill_decision failed");
  }
  return { exact: exact[0] === 1 };
}

/**
 * Whether a scatter should use the density tier (Python Trace.use_density).
 */
export function shouldUseDensity(nPoints, { forceDensity = false, forceDirect = false, coords = "cartesian" } = {}) {
  if (forceDirect || coords === "polar") return false;
  if (forceDensity) return true;
  return Number(nPoints) >= SCATTER_DENSITY_THRESHOLD;
}

export function normalizeF32(data, lo, hi, { nanMode = "nan" } = {}) {
  const arr = asF64Array(data);
  const out = new Float32Array(arr.length);
  if (arr.length === 0) {
    return out;
  }
  const ok = xyNormalizeF32(
    f64Ptr(arr),
    BigInt(arr.length),
    Number(lo),
    Number(hi),
    nanMode === "nan" ? 1 : 0,
    f32Ptr(out),
  );
  if (ok !== 1) {
    throw new Error("xyg_normalize_f32 failed");
  }
  return out;
}

export class Column {
  constructor(values, { kind = "float" } = {}) {
    this.values = asF64Array(values);
    this.kind = kind;
    this._bounds = undefined;
    this._nullCount = undefined;
    this._shipOffset = null;
    this._stream = 0n;
  }

  get length() {
    return this.values.length;
  }

  get min() {
    return this.bounds()[0];
  }

  get max() {
    return this.bounds()[1];
  }

  get nullCount() {
    if (this._nullCount === undefined) {
      let n = 0;
      for (let i = 0; i < this.values.length; i += 1) {
        if (!Number.isFinite(this.values[i])) {
          n += 1;
        }
      }
      this._nullCount = n;
    }
    return this._nullCount;
  }

  bounds() {
    if (this._bounds === undefined) {
      const mm = minMax(this.values);
      this._bounds = mm == null ? [Number.NaN, Number.NaN] : mm;
    }
    return this._bounds;
  }

  suggestOffset() {
    const [lo, hi] = this.bounds();
    if (Number.isNaN(lo) || Number.isNaN(hi)) {
      return 0.0;
    }
    const mid = (lo + hi) / 2.0;
    const prev = this._shipOffset;
    if (prev != null && Number.isFinite(prev)) {
      const span = hi - lo;
      if (Math.max(Math.abs(lo - prev), Math.abs(hi - prev)) <= (span > 0 ? span : 0.0)) {
        return prev;
      }
    }
    this._shipOffset = mid;
    return mid;
  }

  /** Grow this column through `xyg_stream_*`. The TypedArray is a snapshot. */
  append(data) {
    const tail = asF64Array(data);
    if (tail.length === 0) {
      return;
    }
    if (this._stream === 0n) {
      this._stream = xyStreamNew(f64Ptr(this.values), BigInt(this.values.length));
      if (this._stream === 0n) {
        throw new Error("xyg_stream_new failed");
      }
    }
    const ok = xyStreamAppend(this._stream, f64Ptr(tail), BigInt(tail.length));
    if (ok !== 1) {
      throw new Error("stale or busy stream handle");
    }
    if (xyStreamSeal(this._stream) !== 1) {
      throw new Error("stale or busy stream handle");
    }
    const n = Number(xyStreamLen(this._stream));
    const out = new Float64Array(n);
    if (xyStreamCopy(this._stream, f64Ptr(out), BigInt(n)) !== 1) {
      throw new Error("stale stream handle");
    }
    this.values = out;
    this._bounds = undefined;
    this._nullCount = undefined;
  }

  get capacityValues() {
    if (this._stream === 0n) {
      return this.values.length;
    }
    return Number(xyStreamCapacity(this._stream));
  }

  freeStream() {
    if (this._stream !== 0n) {
      xyStreamFree(this._stream);
      this._stream = 0n;
    }
  }
}

export {
  xyStreamNew,
  xyStreamAppend,
  xyStreamSeal,
  xyStreamFree,
  xyStreamLen,
  xyStreamCapacity,
  xyStreamCopy,
};

export function f64Ptr(view) {
  return pointer(view, "double *");
}

export function f32Ptr(view) {
  return pointer(view, "float *");
}

export function u32Ptr(view) {
  return pointer(view, "uint32_t *");
}

export function u8Ptr(view) {
  return pointer(view, "uint8_t *");
}
