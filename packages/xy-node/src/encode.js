/**
 * Offset-encoded f32 geometry (§4/§16) and shared encode helpers.
 * Bit-identical to python/xyg/lod.encode_f32_values when calling xyg_encode_f32.
 */
import { pointer, xyEncodeF32, xyF32SafeScale, xyGeometryOffset, xyScalePinsOffset, xySceneDashAdmit, xySceneLinecapAdmit, xyDensityOverlayOpacity, xyArrowGeometry, xyArrowShaftPoints, xyArrowEndDecoration, xyArrowTaperPolygon, xyArrowTrimPolylineEnd, xyIsSorted, xyArgsortStable, xyMinMax, xyM4Points, xyM4Indices, xyHistogramUniform, xyHistogramBins, xyNormalizeF32, xyHexbin, xyHexbinIngress, xyHexbinGroups, xyHexbinRing, xyViolinDensity, xyViolinRects, xyHistogramEdges, xyHistogramMarkEdges, xyContourLevels, xyLegendNormalize, xyLegendBestLoc, xyRibbonEdge, xyRibbonPolygon, xyMonotoneTangents, xyCurveFlatten, xyStepArrays, xyMarkerPathScale, xyRoundedRectPoly, xyBoxGeometry, xyBoxStats, xyQuantiles, xyWindRoseBins, xyContourfDensify, xyContourfBands, xyBarStack, xyBinnedEcdf, xyWeightedEcdf, xyHeatmapRgba, xyColormapRgba, xyColormapRgbaCanonical, xyColormapLut, xyColormapStops, xyBin2d, xyBin2dMeanColor, xyDensityBinWindow, xyDensityEmitMeta, xyDensityFormatBinning, xyDensityFullIdentity, xyDensityGridPath, xyDensityLogU8, xyDensityRgbaLinear, xyDensityPyramidPreflight, xyDensityWasmEligible, xyMarchingSquares, xyLodPlan, xyPayloadTier, xyPayloadM4Indices, xyPayloadVisibleNeeded, xyPayloadVisibleMask, xyPayloadVisibleIndices, xyPayloadEvenIndices, xyPayloadErrorbarIndices, xyPayloadSegmentBudget, xyPayloadSampleTargetIndices, xyPaintEffectiveRgba, xyDrillDecision, xyStreamNew, xyStreamAppend, xyStreamSeal, xyStreamFree, xyStreamLen, xyStreamCapacity, xyStreamCopy } from "./native.js";

export const PROTOCOL_VERSION = 12;
export const DECIMATION_THRESHOLD = 10_000;
export const SCATTER_DENSITY_THRESHOLD = 200_000;
export const DIRECT_SOFT_CEILING = 2_000_000;
/** Default density grid (w, h) matching Python `config.DENSITY_GRID`. */
export const DENSITY_GRID = Object.freeze([512, 384]);
/** Default density overlay sample size matching Python `DENSITY_SAMPLE_TARGET`. */
export const DENSITY_SAMPLE_TARGET = 8_192;
/** Default density overlay seed matching Python `DENSITY_SAMPLE_SEED`. */
export const DENSITY_SAMPLE_SEED = 0;
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
/** Documented log-family names. Admission is ABI 216 `xyg_scale_pins_offset`. */
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
  if (scale == null) return false;
  const encoded = new TextEncoder().encode(String(scale));
  const code = Number(
    xyScalePinsOffset(encoded.length ? u8Ptr(encoded) : 0, BigInt(encoded.length)),
  );
  if (code < 0) throw new RangeError("invalid scale-pins-offset request");
  return code === 1;
}

/** Scene dash admit (ABI 218). None/omitted → null, unusable → false, else 2–8 lengths. */
export function sceneDashAdmit(value) {
  if (value == null) return null;
  const out = new Float64Array(8);
  const outN = new BigUint64Array(1);
  let encoded = new Uint8Array(0);
  let lengths = new Float64Array(0);
  let useLengths = 0;
  if (typeof value === "string") {
    if (value.length === 0) return false;
    encoded = new TextEncoder().encode(value);
  } else if (Array.isArray(value)) {
    lengths = asF64Array(value, "dash");
    useLengths = 1;
  } else {
    return false;
  }
  const code = Number(
    xySceneDashAdmit(
      encoded.length ? u8Ptr(encoded) : 0,
      BigInt(encoded.length),
      lengths.length ? f64Ptr(lengths) : 0,
      BigInt(lengths.length),
      useLengths,
      f64Ptr(out),
      8n,
      pointer(outN, "size_t *"),
    ),
  );
  if (code === -2) throw new RangeError("invalid scene-dash-admit request");
  if (code < 0) return false;
  if (code === 0) return null;
  return Array.from(out.subarray(0, Number(outN[0])));
}

/** Scene linecap admit (ABI 219). None/omitted/round → null, unusable → false, butt → 0, square → 2. */
export function sceneLinecapAdmit(value) {
  if (value == null) return null;
  const text = String(value);
  if (!text.trim()) return false;
  const encoded = new TextEncoder().encode(text);
  const code = Number(
    xySceneLinecapAdmit(encoded.length ? u8Ptr(encoded) : 0, BigInt(encoded.length)),
  );
  if (code === -2) throw new RangeError("invalid scene-linecap-admit request");
  if (code < 0) return false;
  if (code === 255) return null;
  return code;
}

/** Density overlay sample opacity (ABI 220). Finite values cap at 0.55; non-finite → 0.55. */
export function densityOverlayOpacity(authored) {
  const out = new Float64Array(1);
  const ok = xyDensityOverlayOpacity(Number(authored), f64Ptr(out));
  if (ok !== 1) {
    throw new RangeError("invalid density-overlay-opacity request");
  }
  return out[0];
}

export function geometryOffset(scale, lo, hi) {
  const out = new Float64Array(1);
  const ok = xyGeometryOffset(pinsOffsetToZero(scale) ? 1 : 0, Number(lo), Number(hi), f64Ptr(out));
  if (ok !== 1) {
    throw new Error("xyg_geometry_offset failed");
  }
  return out[0];
}

export function f32SafeScale(offset, lo, hi) {
  const out = new Float64Array(1);
  const ok = xyF32SafeScale(Number(offset), Number(lo), Number(hi), f64Ptr(out));
  if (ok !== 1) {
    throw new Error("xyg_f32_safe_scale failed");
  }
  return out[0];
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

/** NumPy `argsort(..., kind="stable")` for f64 (NaNs last). */
export function argsortStable(data) {
  const arr = asF64Array(data);
  if (arr.length === 0) {
    return new Uint32Array(0);
  }
  const out = new Uint32Array(arr.length);
  const written = Number(xyArgsortStable(f64Ptr(arr), BigInt(arr.length), u32Ptr(out), BigInt(out.length)));
  if (written !== arr.length) {
    throw new Error("xyg_argsort_stable failed");
  }
  return out;
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

export function histogramBins(data, edges, { density = false, cumulative = false } = {}) {
  const values = asF64Array(data);
  const binEdges = asF64Array(edges, "edges");
  if (binEdges.length < 2 || binEdges.length > 10_001) {
    throw new RangeError("histogram edges must contain 2 through 10,001 values");
  }
  const counts = new Float64Array(binEdges.length - 1);
  const written = Number(
    xyHistogramBins(
      f64Ptr(values),
      BigInt(values.length),
      f64Ptr(binEdges),
      BigInt(binEdges.length),
      density ? 1 : 0,
      cumulative ? 1 : 0,
      f64Ptr(counts),
    ),
  );
  if (!Number.isFinite(written) || written !== counts.length) {
    throw new Error("xyg_histogram_bins failed");
  }
  return counts;
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

const HISTOGRAM_MARK_METHOD = Object.freeze({ auto: 0, sturges: 1, uniform: 2 });

/** Composition histogram edges (empty auto/sturges → 10 bins; uniform uses auto_domain). */
export function histogramMarkEdges(data, { range = null, method = "auto", nBins = 0 } = {}) {
  const arr = asF64Array(data);
  const methodId = HISTOGRAM_MARK_METHOD[method];
  if (methodId == null) {
    throw new Error("histogramMarkEdges method must be 'auto', 'sturges', or 'uniform'");
  }
  const useRange = range == null ? 0 : 1;
  const lo = range == null ? 0 : Number(range[0]);
  const hi = range == null ? 0 : Number(range[1]);
  const capacity = 10_001;
  const out = new Float64Array(capacity);
  const written = Number(
    xyHistogramMarkEdges(
      f64Ptr(arr),
      BigInt(arr.length),
      lo,
      hi,
      useRange,
      methodId,
      BigInt(nBins),
      f64Ptr(out),
      BigInt(capacity),
    ),
  );
  if (!Number.isFinite(written) || written < 0 || written > capacity) {
    throw new Error("xyg_histogram_mark_edges failed");
  }
  return out.subarray(0, written);
}

/** Composition contour isolines. `nLevels > 0` auto-spaces; `nLevels === 0` sorts authored levels. */
export function contourLevels(data, nLevels = 0) {
  const arr = asF64Array(data);
  const capacity = 256;
  const out = new Float64Array(capacity);
  const written = Number(
    xyContourLevels(f64Ptr(arr), BigInt(arr.length), BigInt(nLevels), f64Ptr(out), BigInt(capacity)),
  );
  if (!Number.isFinite(written) || written < 0 || written > capacity) {
    throw new Error("xyg_contour_levels failed");
  }
  return out.subarray(0, written);
}

const LEGEND_SCALE = Object.freeze({ linear: 0, log: 1, symlog: 2 });

/** Matplotlib `loc="best"` candidates in preference order (ABI 120). */
export const LEGEND_CANDIDATE_ORDER = Object.freeze([
  "upper right",
  "upper left",
  "lower left",
  "lower right",
  "center right",
  "center left",
  "lower center",
  "upper center",
  "center",
]);

function legendScaleCode(scale) {
  if (scale == null || scale === "linear") return 0;
  const code = LEGEND_SCALE[scale];
  return code == null ? 0 : code;
}

/** Display-space occupancy sample. Returns null when nothing is scorable. */
export function legendNormalize(x, y, {
  xDomain, yDomain,
  xReverse = false, yReverse = false,
  xScale = "linear", yScale = "linear",
  xConstant = 1, yConstant = 1,
} = {}) {
  const xv = asF64Array(x);
  const yv = asF64Array(y);
  if (xv.length !== yv.length) {
    throw new Error("legendNormalize x and y must have equal length");
  }
  const capacity = Math.min(xv.length, 512);
  const outX = new Float64Array(capacity);
  const outY = new Float64Array(capacity);
  const written = Number(
    xyLegendNormalize(
      f64Ptr(xv),
      f64Ptr(yv),
      BigInt(xv.length),
      Number(xDomain[0]),
      Number(xDomain[1]),
      Number(yDomain[0]),
      Number(yDomain[1]),
      xReverse ? 1 : 0,
      yReverse ? 1 : 0,
      legendScaleCode(xScale),
      legendScaleCode(yScale),
      Number(xConstant),
      Number(yConstant),
      capacity ? f64Ptr(outX) : null,
      capacity ? f64Ptr(outY) : null,
      BigInt(capacity),
    ),
  );
  if (!Number.isFinite(written) || written < 0 || written > capacity) {
    throw new Error("xyg_legend_normalize failed");
  }
  if (written === 0) return null;
  return { x: outX.subarray(0, written), y: outY.subarray(0, written) };
}

/** Least-occupied candidate name for concatenated normalized series. */
export function legendBestLoc(series, labelLens = []) {
  const rows = Array.isArray(series) ? series : [];
  const starts = new BigUint64Array(rows.length);
  let total = 0;
  for (let i = 0; i < rows.length; i += 1) {
    starts[i] = BigInt(total);
    const row = rows[i];
    const xv = row.x ?? row[0];
    total += xv.length;
  }
  const xs = new Float64Array(total);
  const ys = new Float64Array(total);
  let at = 0;
  for (const row of rows) {
    const xv = row.x ?? row[0];
    const yv = row.y ?? row[1];
    if (xv.length !== yv.length) {
      throw new Error("legendBestLoc series x and y must have equal length");
    }
    xs.set(xv, at);
    ys.set(yv, at);
    at += xv.length;
  }
  const labels = Uint32Array.from(labelLens, (value) => Number(value) >>> 0);
  const code = xyLegendBestLoc(
    total ? f64Ptr(xs) : null,
    total ? f64Ptr(ys) : null,
    BigInt(total),
    rows.length ? pointer(starts, "size_t *") : null,
    BigInt(rows.length),
    labels.length ? u32Ptr(labels) : null,
    BigInt(labels.length),
  );
  if (!Number.isInteger(code) || code < 0 || code >= LEGEND_CANDIDATE_ORDER.length) {
    throw new Error("xyg_legend_best_loc failed");
  }
  return LEGEND_CANDIDATE_ORDER[code];
}

function requireWritten(written, capacity, name) {
  if (!Number.isFinite(written) || written < 0 || written > capacity) {
    throw new Error(`${name} failed`);
  }
  return written;
}

/** Flatten one d3 curveBumpX edge. Returns `{ x, y }` of length `steps + 1`. */
export function ribbonEdge(x0, x1, ya, yb, steps = 96) {
  const nSteps = Number(steps);
  if (!Number.isInteger(nSteps) || nSteps <= 0) {
    throw new Error("ribbonEdge steps must be a positive integer");
  }
  const capacity = nSteps + 1;
  const outX = new Float64Array(capacity);
  const outY = new Float64Array(capacity);
  const written = requireWritten(
    Number(xyRibbonEdge(Number(x0), Number(x1), Number(ya), Number(yb), BigInt(nSteps), f64Ptr(outX), f64Ptr(outY), BigInt(capacity))),
    capacity,
    "xyg_ribbon_edge",
  );
  return { x: outX.subarray(0, written), y: outY.subarray(0, written) };
}

/** Closed flow-band polygon: upper edge then reversed lower. */
export function ribbonPolygon(x0, x1, srcLo, srcHi, dstLo, dstHi, steps = 96) {
  const nSteps = Number(steps);
  if (!Number.isInteger(nSteps) || nSteps <= 0) {
    throw new Error("ribbonPolygon steps must be a positive integer");
  }
  const capacity = 2 * (nSteps + 1);
  const outX = new Float64Array(capacity);
  const outY = new Float64Array(capacity);
  const written = requireWritten(
    Number(xyRibbonPolygon(
      Number(x0),
      Number(x1),
      Number(srcLo),
      Number(srcHi),
      Number(dstLo),
      Number(dstHi),
      BigInt(nSteps),
      f64Ptr(outX),
      f64Ptr(outY),
      BigInt(capacity),
    )),
    capacity,
    "xyg_ribbon_polygon",
  );
  return { x: outX.subarray(0, written), y: outY.subarray(0, written) };
}

/** Fritsch–Carlson monotone-cubic tangents. */
export function monotoneTangents(x, y) {
  const xv = asF64Array(x);
  const yv = asF64Array(y);
  if (xv.length !== yv.length) {
    throw new Error("monotoneTangents x and y must have equal length");
  }
  const out = new Float64Array(xv.length);
  const written = requireWritten(
    Number(xyMonotoneTangents(
      xv.length ? f64Ptr(xv) : null,
      yv.length ? f64Ptr(yv) : null,
      BigInt(xv.length),
      xv.length ? f64Ptr(out) : null,
      BigInt(out.length),
    )),
    out.length,
    "xyg_monotone_tangents",
  );
  return out.subarray(0, written);
}

/** Data-space monotone-cubic Hermite flatten. */
export function curveFlatten(x, y, bezierSteps = 16) {
  const xv = asF64Array(x);
  const yv = asF64Array(y);
  if (xv.length !== yv.length) {
    throw new Error("curveFlatten x and y must have equal length");
  }
  const steps = Number(bezierSteps);
  if (!Number.isInteger(steps) || steps < 2) {
    throw new Error("curveFlatten bezierSteps must be an integer >= 2");
  }
  const n = xv.length;
  const capacity = n === 0 ? 0 : n === 1 ? 1 : 1 + (n - 1) * steps;
  const outX = new Float64Array(capacity);
  const outY = new Float64Array(capacity);
  const written = requireWritten(
    Number(xyCurveFlatten(
      n ? f64Ptr(xv) : null,
      n ? f64Ptr(yv) : null,
      BigInt(n),
      BigInt(steps),
      capacity ? f64Ptr(outX) : null,
      capacity ? f64Ptr(outY) : null,
      BigInt(capacity),
    )),
    capacity,
    "xyg_curve_flatten",
  );
  return { x: outX.subarray(0, written), y: outY.subarray(0, written) };
}

const USIZE_MAX_64 = (1n << 64n) - 1n;

function stepMode(where) {
  if (where === "pre" || where === 1) return 1;
  if (where === "mid" || where === 2) return 2;
  if (where === "post" || where === 3) return 3;
  if (typeof where === "string") return 3;
  throw new RangeError("stepArrays where must be pre, mid, or post");
}

/** Expand compact vertices into a step polyline (ABI 211). */
export function stepArrays(x, y, where = "post") {
  const xv = asF64Array(x);
  const yv = asF64Array(y);
  if (xv.length !== yv.length) {
    throw new Error("stepArrays x and y must have equal length");
  }
  const mode = stepMode(where);
  const n = xv.length;
  const probed = xyStepArrays(
    n ? f64Ptr(xv) : 0,
    n ? f64Ptr(yv) : 0,
    BigInt(n),
    mode,
    0,
    0,
    0,
  );
  if (probed === USIZE_MAX_64) throw new RangeError("invalid step-arrays request");
  const count = Number(probed);
  if (count === 0) return { x: new Float64Array(0), y: new Float64Array(0) };
  const outX = new Float64Array(count);
  const outY = new Float64Array(count);
  const written = xyStepArrays(
    n ? f64Ptr(xv) : 0,
    n ? f64Ptr(yv) : 0,
    BigInt(n),
    mode,
    f64Ptr(outX),
    f64Ptr(outY),
    count,
  );
  if (written === USIZE_MAX_64 || Number(written) !== count) {
    throw new RangeError("invalid step-arrays request");
  }
  return { x: outX, y: outY };
}

/** Pixel-space authored marker vertices (ABI 212). */
export function markerPathScale(cx, cy, scale, x, y) {
  const xv = asF64Array(x);
  const yv = asF64Array(y);
  if (xv.length !== yv.length) {
    throw new Error("markerPathScale x and y must have equal length");
  }
  const n = xv.length;
  const probed = xyMarkerPathScale(
    Number(cx),
    Number(cy),
    Number(scale),
    n ? f64Ptr(xv) : 0,
    n ? f64Ptr(yv) : 0,
    BigInt(n),
    0,
    0,
    0,
  );
  if (probed === USIZE_MAX_64) throw new RangeError("invalid marker-path-scale request");
  const count = Number(probed);
  if (count === 0) return { x: new Float64Array(0), y: new Float64Array(0) };
  const outX = new Float64Array(count);
  const outY = new Float64Array(count);
  const written = xyMarkerPathScale(
    Number(cx),
    Number(cy),
    Number(scale),
    n ? f64Ptr(xv) : 0,
    n ? f64Ptr(yv) : 0,
    BigInt(n),
    f64Ptr(outX),
    f64Ptr(outY),
    count,
  );
  if (written === USIZE_MAX_64 || Number(written) !== count) {
    throw new RangeError("invalid marker-path-scale request");
  }
  return { x: outX, y: outY };
}

function packArrowStyle(style = {}) {
  const packed = new Float64Array(12);
  packed.fill(Number.NaN);
  if (typeof style.start_offset === "string") {
    const offset = style.start_offset.split(",").map(Number);
    if (offset.length === 2 && offset.every(Number.isFinite)) {
      packed[0] = offset[0];
      packed[1] = offset[1];
    }
  }
  const num = (v) => (Number.isFinite(Number(v)) ? Number(v) : null);
  const angleA = num(style.angle_a);
  const angleB = num(style.angle_b);
  if (angleA !== null) packed[2] = angleA;
  if (angleB !== null) packed[3] = angleB;
  const curve = num(style.curve);
  if (curve !== null) packed[4] = curve;
  const gapStart = num(style.gap_start);
  const gapEnd = num(style.gap_end);
  if (gapStart !== null) packed[5] = gapStart;
  if (gapEnd !== null) packed[6] = gapEnd;
  if (typeof style.label_clear === "string") {
    const parts = style.label_clear.split(",").map(Number);
    if (parts.length === 4 && parts.every((p) => Number.isFinite(p) && p >= 0)) {
      packed[7] = parts[0];
      packed[8] = parts[1];
      packed[9] = parts[2];
      packed[10] = parts[3];
    }
  }
  if (style.elbow) packed[11] = 1;
  return packed;
}

/** Annotation arrow connectionstyle geometry (ABI 217). */
export function arrowGeometry(x0, y0, x1, y1, style = {}) {
  const packed = packArrowStyle(style);
  const out = new Float64Array(11);
  const ok = xyArrowGeometry(
    Number(x0),
    Number(y0),
    Number(x1),
    Number(y1),
    f64Ptr(packed),
    12n,
    f64Ptr(out),
    11n,
  );
  if (ok !== 1) throw new Error("xyg_arrow_geometry failed");
  const hasControl = out[6] !== 0;
  return {
    p0: [out[0], out[1]],
    p1: [out[2], out[3]],
    control: hasControl ? [out[4], out[5]] : null,
    elbow: Boolean(style.elbow),
    dir0: [out[7], out[8]],
    dir1: [out[9], out[10]],
  };
}

/** Quadratic / elbow / linear shaft samples (ABI 217). */
export function arrowShaftPoints(geom, samples = 24) {
  const [p0x, p0y] = geom.p0;
  const [p1x, p1y] = geom.p1;
  const hasControl = geom.control != null;
  const [cx, cy] = hasControl ? geom.control : [0, 0];
  const probed = xyArrowShaftPoints(
    Number(p0x),
    Number(p0y),
    Number(p1x),
    Number(p1y),
    Number(cx),
    Number(cy),
    hasControl ? 1 : 0,
    geom.elbow ? 1 : 0,
    BigInt(samples),
    0,
    0,
    0,
  );
  if (probed === USIZE_MAX_64) throw new RangeError("invalid arrow-shaft-points request");
  const count = Number(probed);
  if (count === 0) return [];
  const outX = new Float64Array(count);
  const outY = new Float64Array(count);
  const written = xyArrowShaftPoints(
    Number(p0x),
    Number(p0y),
    Number(p1x),
    Number(p1y),
    Number(cx),
    Number(cy),
    hasControl ? 1 : 0,
    geom.elbow ? 1 : 0,
    BigInt(samples),
    f64Ptr(outX),
    f64Ptr(outY),
    count,
  );
  if (written === USIZE_MAX_64 || Number(written) !== count) {
    throw new RangeError("invalid arrow-shaft-points request");
  }
  return Array.from({ length: count }, (_, i) => [outX[i], outY[i]]);
}

/** Endpoint decoration vertices (ABI 217). kind 0 none / 1 fill / 2 stroke. */
export function arrowEndDecoration(point, direction, style, head) {
  const encoded = new TextEncoder().encode(String(style));
  const kind = new Int32Array([-1]);
  const probed = xyArrowEndDecoration(
    Number(point[0]),
    Number(point[1]),
    Number(direction[0]),
    Number(direction[1]),
    encoded.length ? u8Ptr(encoded) : 0,
    BigInt(encoded.length),
    Number(head),
    0,
    0,
    0,
    pointer(kind, "int32_t *"),
  );
  if (probed === USIZE_MAX_64 || kind[0] < 0) {
    throw new RangeError("invalid arrow-end-decoration request");
  }
  const count = Number(probed);
  if (count === 0) return { kind: kind[0], points: [] };
  const outX = new Float64Array(count);
  const outY = new Float64Array(count);
  kind[0] = -1;
  const written = xyArrowEndDecoration(
    Number(point[0]),
    Number(point[1]),
    Number(direction[0]),
    Number(direction[1]),
    encoded.length ? u8Ptr(encoded) : 0,
    BigInt(encoded.length),
    Number(head),
    f64Ptr(outX),
    f64Ptr(outY),
    count,
    pointer(kind, "int32_t *"),
  );
  if (written === USIZE_MAX_64 || Number(written) !== count || kind[0] < 0) {
    throw new RangeError("invalid arrow-end-decoration request");
  }
  return {
    kind: kind[0],
    points: Array.from({ length: count }, (_, i) => [outX[i], outY[i]]),
  };
}

/** Tapered shaft polygon (ABI 217). */
export function arrowTaperPolygon(points, widthStart, widthEnd) {
  const xv = new Float64Array(points.map((p) => p[0]));
  const yv = new Float64Array(points.map((p) => p[1]));
  const n = xv.length;
  const probed = xyArrowTaperPolygon(
    n ? f64Ptr(xv) : 0,
    n ? f64Ptr(yv) : 0,
    BigInt(n),
    Number(widthStart),
    Number(widthEnd),
    0,
    0,
    0,
  );
  if (probed === USIZE_MAX_64) throw new RangeError("invalid arrow-taper-polygon request");
  const count = Number(probed);
  if (count === 0) return [];
  const outX = new Float64Array(count);
  const outY = new Float64Array(count);
  const written = xyArrowTaperPolygon(
    n ? f64Ptr(xv) : 0,
    n ? f64Ptr(yv) : 0,
    BigInt(n),
    Number(widthStart),
    Number(widthEnd),
    f64Ptr(outX),
    f64Ptr(outY),
    count,
  );
  if (written === USIZE_MAX_64 || Number(written) !== count) {
    throw new RangeError("invalid arrow-taper-polygon request");
  }
  return Array.from({ length: count }, (_, i) => [outX[i], outY[i]]);
}

/** Trim arclength from a polyline end (ABI 217). */
export function arrowTrimPolylineEnd(points, trim) {
  const xv = new Float64Array(points.map((p) => p[0]));
  const yv = new Float64Array(points.map((p) => p[1]));
  const n = xv.length;
  const probed = xyArrowTrimPolylineEnd(
    n ? f64Ptr(xv) : 0,
    n ? f64Ptr(yv) : 0,
    BigInt(n),
    Number(trim),
    0,
    0,
    0,
  );
  if (probed === USIZE_MAX_64) throw new RangeError("invalid arrow-trim-polyline-end request");
  const count = Number(probed);
  if (count === 0) return [];
  const outX = new Float64Array(count);
  const outY = new Float64Array(count);
  const written = xyArrowTrimPolylineEnd(
    n ? f64Ptr(xv) : 0,
    n ? f64Ptr(yv) : 0,
    BigInt(n),
    Number(trim),
    f64Ptr(outX),
    f64Ptr(outY),
    count,
  );
  if (written === USIZE_MAX_64 || Number(written) !== count) {
    throw new RangeError("invalid arrow-trim-polyline-end request");
  }
  return Array.from({ length: count }, (_, i) => [outX[i], outY[i]]);
}

/** CW rounded-rect outline with independent tip/base radii. */
export function roundedRectPoly(x, y, w, h, rTip, rBase, tipTop = true) {
  const outX = new Float64Array(20);
  const outY = new Float64Array(20);
  const written = requireWritten(
    Number(xyRoundedRectPoly(
      Number(x),
      Number(y),
      Number(w),
      Number(h),
      Number(rTip),
      Number(rBase),
      tipTop ? 1 : 0,
      f64Ptr(outX),
      f64Ptr(outY),
      20n,
    )),
    20,
    "xyg_rounded_rect_poly",
  );
  return { x: outX.subarray(0, written), y: outY.subarray(0, written) };
}

const HEX_REDUCE = Object.freeze({ count: 0, mean: 1, sum: 2 });

function hexbinGridAndRange(gridsize, range) {
  const [w, h] = Array.isArray(gridsize) ? gridsize : [gridsize, 0];
  const width = Number(w);
  const height = Number(h);
  if (!Number.isInteger(width) || width < 2 || width > 2048) {
    throw new RangeError("hexbin gridsize dimensions must be in 2..=2048");
  }
  if (height !== 0 && (!Number.isInteger(height) || height < 2 || height > 2048)) {
    throw new RangeError("hexbin gridsize dimensions must be in 2..=2048");
  }
  if (range == null) {
    return { w: width, h: height, x0: 0, x1: 0, y0: 0, y1: 0, useRange: 0 };
  }
  const x0 = Number(range[0][0]);
  const x1 = Number(range[0][1]);
  const y0 = Number(range[1][0]);
  const y1 = Number(range[1][1]);
  if (!(Number.isFinite(x0) && Number.isFinite(x1) && x1 > x0 && Number.isFinite(y0) && Number.isFinite(y1) && y1 > y0)) {
    throw new RangeError("hexbin range must be a finite increasing rectangle");
  }
  return { w: width, h: height, x0, x1, y0, y1, useRange: 1 };
}

/** Pointy-top hexagon vertex offsets scaled by cell pitch (ABI 210). */
export function hexbinRing(hexDx, hexDy) {
  const probed = xyHexbinRing(Number(hexDx), Number(hexDy), 0, 0, 0);
  if (probed === USIZE_MAX_64) throw new RangeError("invalid hexbin-ring request");
  const n = Number(probed);
  const outX = new Float64Array(n);
  const outY = new Float64Array(n);
  const written = xyHexbinRing(
    Number(hexDx),
    Number(hexDy),
    f64Ptr(outX),
    f64Ptr(outY),
    n,
  );
  if (written === USIZE_MAX_64 || Number(written) !== n) {
    throw new RangeError("invalid hexbin-ring request");
  }
  return { x: outX, y: outY };
}

/** Rust-owned hexbin finite-pair domain and default grid aspect. */
export function hexbinIngress(x, y, { gridsize, range = null, C = null } = {}) {
  const xa = asF64Array(x);
  const ya = asF64Array(y);
  if (xa.length !== ya.length) {
    throw new RangeError("hexbin x/y length mismatch");
  }
  const { w, h, x0, x1, y0, y1, useRange } = hexbinGridAndRange(gridsize, range);
  const ca = C == null ? null : asF64Array(C);
  if (ca != null && ca.length !== xa.length) {
    throw new RangeError("hexbin C length mismatch");
  }
  const outX0 = new Float64Array(1);
  const outX1 = new Float64Array(1);
  const outY0 = new Float64Array(1);
  const outY1 = new Float64Array(1);
  const outW = new BigUint64Array(1);
  const outH = new BigUint64Array(1);
  const ok = Number(
    xyHexbinIngress(
      f64Ptr(xa),
      f64Ptr(ya),
      ca == null ? null : f64Ptr(ca),
      BigInt(xa.length),
      BigInt(w),
      BigInt(h),
      x0,
      x1,
      y0,
      y1,
      useRange,
      f64Ptr(outX0),
      f64Ptr(outX1),
      f64Ptr(outY0),
      f64Ptr(outY1),
      pointer(outW, "size_t *"),
      pointer(outH, "size_t *"),
    ),
  );
  if (ok !== 1) {
    throw new RangeError("hexbin x and y must contain at least one finite pair");
  }
  return {
    range: [
      [outX0[0], outX1[0]],
      [outY0[0], outY1[0]],
    ],
    gridsize: [Number(outW[0]), Number(outH[0])],
  };
}

/** Matplotlib-compatible hexbin; `reduce` is count|mean|sum. */
export function hexbin(x, y, { gridsize, range = null, mincnt = 0, C = null, reduce = "count" } = {}) {
  const xa = asF64Array(x);
  const ya = asF64Array(y);
  if (xa.length !== ya.length) {
    throw new RangeError("hexbin x/y length mismatch");
  }
  const { w, h, x0, x1, y0, y1, useRange } = hexbinGridAndRange(gridsize, range);
  const reduceId = HEX_REDUCE[reduce];
  if (reduceId == null) {
    throw new Error("hexbin reduce must be count, mean, or sum");
  }
  const ca = C == null ? null : asF64Array(C);
  if (ca != null && ca.length !== xa.length) {
    throw new RangeError("hexbin C length mismatch");
  }
  const hCap = h === 0 ? w : h;
  const capacity = (w + 1) * (hCap + 1) + w * hCap;
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
      x0,
      x1,
      y0,
      y1,
      useRange,
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
    throw new RangeError("hexbin x and y must contain at least one finite pair");
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

/** Occupied hex-cell memberships for a host custom reducer. */
export function hexbinGroups(x, y, { gridsize, range = null, mincnt = 0, C = null } = {}) {
  const xa = asF64Array(x);
  const ya = asF64Array(y);
  if (xa.length !== ya.length) {
    throw new RangeError("hexbin x/y length mismatch");
  }
  const { w, h, x0, x1, y0, y1, useRange } = hexbinGridAndRange(gridsize, range);
  const ca = C == null ? null : asF64Array(C);
  if (ca != null && ca.length !== xa.length) {
    throw new RangeError("hexbin C length mismatch");
  }
  const hCap = h === 0 ? w : h;
  const cellCapacity = (w + 1) * (hCap + 1) + w * hCap;
  const outCx = new Float64Array(cellCapacity);
  const outCy = new Float64Array(cellCapacity);
  const outCounts = new Float64Array(cellCapacity);
  const outStarts = new Uint32Array(cellCapacity);
  const outLens = new Uint32Array(cellCapacity);
  const outIndices = new Uint32Array(xa.length);
  const nIndices = new BigUint64Array(1);
  const dx = new Float64Array(1);
  const dy = new Float64Array(1);
  const written = Number(
    xyHexbinGroups(
      f64Ptr(xa),
      f64Ptr(ya),
      ca == null ? null : f64Ptr(ca),
      BigInt(xa.length),
      BigInt(w),
      BigInt(h),
      x0,
      x1,
      y0,
      y1,
      useRange,
      BigInt(mincnt),
      f64Ptr(outCx),
      f64Ptr(outCy),
      f64Ptr(outCounts),
      u32Ptr(outStarts),
      u32Ptr(outLens),
      BigInt(cellCapacity),
      u32Ptr(outIndices),
      BigInt(outIndices.length),
      pointer(nIndices, "size_t *"),
      f64Ptr(dx),
      f64Ptr(dy),
    ),
  );
  if (!Number.isFinite(written) || written < 0 || written > cellCapacity) {
    throw new RangeError("hexbin x and y must contain at least one finite pair");
  }
  const nIdx = Number(nIndices[0]);
  return {
    centersX: outCx.subarray(0, written),
    centersY: outCy.subarray(0, written),
    counts: outCounts.subarray(0, written),
    starts: outStarts.subarray(0, written),
    lengths: outLens.subarray(0, written),
    indices: outIndices.subarray(0, nIdx),
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

/** Map normalized scalars t ∈ [0, 1] to vertically flipped RGBA bytes (h, w, 4). */
export function colormapRgba(raw, w, h, stops, alpha = 255) {
  const ww = Number(w);
  const hh = Number(h);
  const values = asF64Array(raw);
  if (values.length !== ww * hh) {
    throw new RangeError("colormapRgba scalar count must match width * height");
  }
  const stopArr = stops instanceof Uint8Array ? stops : Uint8Array.from(stops);
  if (stopArr.length % 3 !== 0 || stopArr.length < 3) {
    throw new RangeError("colormapRgba stops must be a non-empty multiple of 3");
  }
  const stopCount = stopArr.length / 3;
  const out = new Uint8Array(hh * ww * 4);
  const ok = xyColormapRgba(
    f64Ptr(values),
    BigInt(ww),
    BigInt(hh),
    u8Ptr(stopArr),
    BigInt(stopCount),
    Number(alpha),
    u8Ptr(out),
  );
  if (ok !== 1) {
    throw new Error("xy_colormap_rgba failed");
  }
  return { rgba: out, width: ww, height: hh };
}

/** Map canonical f64 scalars through domain normalization to RGBA bytes. */
export function colormapRgbaCanonical(raw, w, h, domain, stops, alpha = 255) {
  const ww = Number(w);
  const hh = Number(h);
  const values = asF64Array(raw);
  if (values.length !== ww * hh) {
    throw new RangeError("colormapRgbaCanonical scalar count must match width * height");
  }
  const stopArr = stops instanceof Uint8Array ? stops : Uint8Array.from(stops);
  if (stopArr.length % 3 !== 0 || stopArr.length < 3) {
    throw new RangeError("colormapRgbaCanonical stops must be a non-empty multiple of 3");
  }
  const stopCount = stopArr.length / 3;
  const out = new Uint8Array(hh * ww * 4);
  const ok = xyColormapRgbaCanonical(
    f64Ptr(values),
    BigInt(ww),
    BigInt(hh),
    Number(domain[0]),
    Number(domain[1]),
    u8Ptr(stopArr),
    BigInt(stopCount),
    Number(alpha),
    u8Ptr(out),
  );
  if (ok !== 1) {
    throw new Error("xy_colormap_rgba_canonical failed");
  }
  return { rgba: out, width: ww, height: hh };
}

/** 1D colormap sample matching `_svg._lut` (ABI 206). */
export function colormapLut(t, stops) {
  const values = asF64Array(t);
  const stopArr = stops instanceof Uint8Array ? stops : Uint8Array.from(stops);
  if (stopArr.length % 3 !== 0 || stopArr.length < 3) {
    throw new RangeError("colormapLut stops must be a non-empty multiple of 3");
  }
  const n = values.length;
  const out = new Uint8Array(n * 3);
  const ok = xyColormapLut(
    n ? f64Ptr(values) : 0,
    BigInt(n),
    u8Ptr(stopArr),
    BigInt(stopArr.length / 3),
    n ? u8Ptr(out) : 0,
  );
  if (ok !== 1) {
    throw new Error("xy_colormap_lut failed");
  }
  return out;
}

/** Legacy f64 count-grid density colormap (ABI 206). */
export function densityRgbaLinear(counts, w, h, maximum, stops, opacity) {
  const ww = Number(w);
  const hh = Number(h);
  const values = asF64Array(counts);
  if (values.length !== ww * hh) {
    throw new RangeError("densityRgbaLinear scalar count must match width * height");
  }
  const stopArr = stops instanceof Uint8Array ? stops : Uint8Array.from(stops);
  if (stopArr.length % 3 !== 0 || stopArr.length < 3) {
    throw new RangeError("densityRgbaLinear stops must be a non-empty multiple of 3");
  }
  const out = new Uint8Array(hh * ww * 4);
  const ok = xyDensityRgbaLinear(
    f64Ptr(values),
    BigInt(ww),
    BigInt(hh),
    Number(maximum),
    u8Ptr(stopArr),
    BigInt(stopArr.length / 3),
    Number(opacity),
    u8Ptr(out),
  );
  if (ok !== 1) {
    throw new Error("xy_density_rgba_linear failed");
  }
  return { rgba: out, width: ww, height: hh };
}

/** Matplotlib artist-alpha replace then xy opacity multiply (ABI 206). */
export function paintEffectiveRgba(intrinsic, artistAlpha, opacity, componentOpacity) {
  const rgba = asF64Array(intrinsic);
  if (rgba.length % 4 !== 0) {
    throw new RangeError("paintEffectiveRgba intrinsic must be N*4 f64s");
  }
  const n = rgba.length / 4;
  const artist = asF64Array(artistAlpha);
  const opac = asF64Array(opacity);
  if (artist.length !== n || opac.length !== n) {
    throw new RangeError("paintEffectiveRgba artist/opacity length must match N");
  }
  const out = new Float64Array(rgba.length);
  const ok = xyPaintEffectiveRgba(
    n ? f64Ptr(rgba) : 0,
    BigInt(n),
    n ? f64Ptr(artist) : 0,
    n ? f64Ptr(opac) : 0,
    Number(componentOpacity),
    n ? f64Ptr(out) : 0,
  );
  if (ok !== 1) {
    throw new Error("xy_paint_effective_rgba failed");
  }
  return out;
}

/** Resolve a named colormap to packed RGB triples (`n * 3` bytes). */
export function colormapNamedStops(name) {
  const encoded = new TextEncoder().encode(String(name ?? ""));
  const out = new Uint8Array(256 * 3);
  const count = Number(xyColormapStops(
    encoded.length ? u8Ptr(encoded) : null,
    BigInt(encoded.length),
    u8Ptr(out),
    BigInt(out.length),
  ));
  if (count <= 0) {
    throw new Error("xy_colormap_stops failed");
  }
  return out.subarray(0, count * 3);
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
 * Mean-color companion grid to `bin2d` (LOD doc §2): (h*w*4) straight-alpha
 * RGBA8, row 0 = bottom. `source` is either `{ rgba: Uint8Array }` or
 * `{ idx: Uint8Array, lut: Uint8Array }` with lut length a multiple of 4.
 */
export function bin2dMeanColor(x, y, x0, x1, y0, y1, w, h, source) {
  const xa = asF64Array(x, "x");
  const ya = asF64Array(y, "y");
  if (xa.length !== ya.length) {
    throw new RangeError("bin2dMeanColor x/y length mismatch");
  }
  const ww = Math.max(1, Math.floor(Number(w)));
  const hh = Math.max(1, Math.floor(Number(h)));
  const out = new Uint8Array(ww * hh * 4);
  let idxPtr = 0;
  let rgbaPtr = 0;
  let lutPtr = 0;
  let lutLen = 0n;
  if (source?.rgba != null) {
    const rgba = source.rgba instanceof Uint8Array ? source.rgba : Uint8Array.from(source.rgba);
    if (rgba.length !== xa.length * 4) {
      throw new RangeError("bin2dMeanColor rgba length must be 4 * n");
    }
    rgbaPtr = xa.length ? u8Ptr(rgba) : 0;
  } else if (source?.idx != null && source?.lut != null) {
    const idx = source.idx instanceof Uint8Array ? source.idx : Uint8Array.from(source.idx);
    const lut = source.lut instanceof Uint8Array ? source.lut : Uint8Array.from(source.lut);
    if (idx.length !== xa.length) {
      throw new RangeError("bin2dMeanColor idx length must match x/y");
    }
    if (lut.length < 4 || lut.length % 4 !== 0 || lut.length / 4 > 256) {
      throw new RangeError("bin2dMeanColor lut must be 1..256 RGBA8 entries");
    }
    idxPtr = xa.length ? u8Ptr(idx) : 0;
    lutPtr = u8Ptr(lut);
    lutLen = BigInt(lut.length / 4);
  } else {
    throw new RangeError("bin2dMeanColor requires rgba or idx+lut");
  }
  const ok = xyBin2dMeanColor(
    f64Ptr(xa),
    f64Ptr(ya),
    BigInt(xa.length),
    idxPtr,
    rgbaPtr,
    lutPtr,
    lutLen,
    Number(x0),
    Number(x1),
    Number(y0),
    Number(y1),
    BigInt(ww),
    BigInt(hh),
    u8Ptr(out),
  );
  if (ok !== 1) {
    throw new Error("xyg_bin_2d_mean_color failed");
  }
  return out;
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
 * Compile-time payload tier via `xyg_payload_tier` (ABI 122).
 * `kind` 0=line/area, 1=scatter. Returns 0=direct, 1=decimated, 2=density.
 */
export function payloadTier({
  kind,
  nPoints,
  polar = false,
  forceDensity = -1,
  forceDirect = false,
  perItem = false,
} = {}) {
  const code = xyPayloadTier(
    Number(kind),
    BigInt(nPoints),
    polar ? 1 : 0,
    Number(forceDensity),
    forceDirect ? 1 : 0,
    perItem ? 1 : 0,
  );
  if (code < 0) {
    throw new Error("xyg_payload_tier failed");
  }
  return code;
}

/**
 * Whether the payload visible-row mask can drop rows (ABI 122).
 */
export function payloadVisibleNeeded({
  xLog = false,
  yLog = false,
  prefiltered = false,
  xHasNulls = false,
  yHasNulls = false,
  hasBase = false,
  baseHasNulls = false,
} = {}) {
  const code = xyPayloadVisibleNeeded(
    xLog ? 1 : 0,
    yLog ? 1 : 0,
    prefiltered ? 1 : 0,
    xHasNulls ? 1 : 0,
    yHasNulls ? 1 : 0,
    hasBase ? 1 : 0,
    baseHasNulls ? 1 : 0,
  );
  if (code < 0) {
    throw new Error("xyg_payload_visible_needed failed");
  }
  return code === 1;
}

/**
 * Finite + log-positive keep mask via `xyg_payload_visible_mask`.
 */
export function payloadVisibleMask(x, y, { xLog = false, yLog = false, base = null } = {}) {
  const xa = asF64Array(x);
  const ya = asF64Array(y);
  if (xa.length !== ya.length) {
    throw new RangeError("payloadVisibleMask x/y length mismatch");
  }
  const n = xa.length;
  const out = new Uint8Array(n);
  const hasBase = base != null;
  const ba = hasBase ? asF64Array(base) : null;
  if (hasBase && ba.length !== n) {
    throw new RangeError("payloadVisibleMask base length mismatch");
  }
  const written = requireWritten(
    Number(xyPayloadVisibleMask(
      n ? f64Ptr(xa) : null,
      n ? f64Ptr(ya) : null,
      BigInt(n),
      xLog ? 1 : 0,
      yLog ? 1 : 0,
      hasBase && n ? f64Ptr(ba) : null,
      hasBase ? 1 : 0,
      n ? u8Ptr(out) : null,
      BigInt(n),
    )),
    n,
    "xyg_payload_visible_mask",
  );
  return { mask: out, kept: written };
}

/**
 * Line M4 indices via `xyg_payload_m4_indices` (ABI 204).
 * Returns `{ tier, indices }`. `tier` is 0=direct (empty indices) or 1=decimated.
 * Rust owns the threshold, polar skip, and closed-window ulp.
 */
export function payloadM4Indices({
  nPoints,
  x,
  y,
  x0,
  x1,
  nBuckets,
  polar = false,
  binX = null,
  binX0 = 0,
  binX1 = 0,
} = {}) {
  const xa = asF64Array(x);
  const ya = asF64Array(y);
  if (xa.length !== ya.length) {
    throw new RangeError("payloadM4Indices x/y length mismatch");
  }
  const n = xa.length;
  const ba = binX == null ? null : asF64Array(binX);
  if (ba != null && ba.length !== n) {
    throw new RangeError("payloadM4Indices binX length mismatch");
  }
  const cap = Math.max(0, Math.floor(Number(nBuckets))) * 4;
  const out = new Uint32Array(cap);
  const tier = new Int32Array([-1]);
  const written = requireWritten(
    Number(xyPayloadM4Indices(
      BigInt(nPoints),
      polar ? 1 : 0,
      n ? f64Ptr(xa) : 0,
      n ? f64Ptr(ya) : 0,
      BigInt(n),
      Number(x0),
      Number(x1),
      BigInt(Math.max(0, Math.floor(Number(nBuckets)))),
      ba != null && n ? f64Ptr(ba) : 0,
      Number(binX0),
      Number(binX1),
      pointer(tier, "int32_t *"),
      cap ? u32Ptr(out) : 0,
      BigInt(cap),
    )),
    cap,
    "xyg_payload_m4_indices",
  );
  return { tier: tier[0], indices: out.subarray(0, written) };
}

function readKeepAllIndices(written, keepAll, out, name) {
  if (!Number.isFinite(written) || written < 0 || written === Number.MAX_SAFE_INTEGER) {
    throw new Error(`${name} failed`);
  }
  if (keepAll[0] === 1) {
    return { keepAll: true, indices: new Uint32Array(0) };
  }
  if (written > out.length) {
    return { keepAll: false, required: written, indices: out };
  }
  return { keepAll: false, indices: out.subarray(0, written) };
}

/**
 * Fused keep-all vs keep-indices via `xyg_payload_visible_indices` (ABI 205).
 * `keepAll` means ship every row without an N-index allocation.
 */
export function payloadVisibleIndices(x, y, {
  xLog = false,
  yLog = false,
  base = null,
  prefiltered = false,
  xHasNulls = false,
  yHasNulls = false,
  hasBase = false,
  baseHasNulls = false,
} = {}) {
  const xa = asF64Array(x);
  const ya = asF64Array(y);
  if (xa.length !== ya.length) {
    throw new RangeError("payloadVisibleIndices x/y length mismatch");
  }
  const n = xa.length;
  const hasBaseFlag = Boolean(hasBase) || base != null;
  const ba = hasBaseFlag ? asF64Array(base) : null;
  if (hasBaseFlag && ba != null && ba.length !== n) {
    throw new RangeError("payloadVisibleIndices base length mismatch");
  }
  const cap = n;
  const out = new Uint32Array(cap);
  const keepAll = new Int32Array([-1]);
  const written = Number(xyPayloadVisibleIndices(
    n ? f64Ptr(xa) : 0,
    n ? f64Ptr(ya) : 0,
    BigInt(n),
    xLog ? 1 : 0,
    yLog ? 1 : 0,
    hasBaseFlag && n ? f64Ptr(ba) : 0,
    hasBaseFlag ? 1 : 0,
    prefiltered ? 1 : 0,
    xHasNulls ? 1 : 0,
    yHasNulls ? 1 : 0,
    baseHasNulls ? 1 : 0,
    pointer(keepAll, "int32_t *"),
    cap ? u32Ptr(out) : 0,
    BigInt(cap),
  ));
  const result = readKeepAllIndices(written, keepAll, out, "xyg_payload_visible_indices");
  if (result.required != null) {
    throw new Error("xyg_payload_visible_indices failed");
  }
  return result;
}

/**
 * Even keep indices via `xyg_payload_even_indices` (ABI 205).
 * Matches NumPy `linspace(0, n-1, count, dtype=np.int64)`.
 */
export function payloadEvenIndices(n, count) {
  const nI = Math.floor(Number(n));
  const countI = Math.floor(Number(count));
  if (!Number.isFinite(nI) || nI < 0 || !Number.isFinite(countI) || countI <= 0) {
    throw new RangeError("payloadEvenIndices n/count must be n>=0 and count>=1");
  }
  const out = new Uint32Array(countI);
  const keepAll = new Int32Array([-1]);
  const written = Number(xyPayloadEvenIndices(
    BigInt(nI),
    BigInt(countI),
    pointer(keepAll, "int32_t *"),
    u32Ptr(out),
    BigInt(countI),
  ));
  const result = readKeepAllIndices(written, keepAll, out, "xyg_payload_even_indices");
  if (result.required != null) {
    throw new Error("xyg_payload_even_indices failed");
  }
  return result;
}

/**
 * Errorbar role-block keep indices via `xyg_payload_errorbar_indices` (ABI 215).
 * Even-samples `nPoints` at `budget` then expands `chosen[i] + k * nPoints`.
 */
export function payloadErrorbarIndices(nSegments, nPoints, budget) {
  const nSeg = Math.floor(Number(nSegments));
  const nPts = Math.floor(Number(nPoints));
  const budgetI = Math.floor(Number(budget));
  if (
    !Number.isFinite(nSeg) || nSeg < 0
    || !Number.isFinite(nPts) || nPts <= 0
    || !Number.isFinite(budgetI) || budgetI <= 0
  ) {
    throw new RangeError("payloadErrorbarIndices nSegments>=0, nPoints>=1, budget>=1");
  }
  const out = new Uint32Array(nSeg);
  const keepAll = new Int32Array([-1]);
  const written = Number(xyPayloadErrorbarIndices(
    BigInt(nSeg),
    BigInt(nPts),
    BigInt(budgetI),
    pointer(keepAll, "int32_t *"),
    nSeg ? u32Ptr(out) : 0,
    BigInt(nSeg),
  ));
  const result = readKeepAllIndices(written, keepAll, out, "xyg_payload_errorbar_indices");
  if (result.required != null) {
    throw new Error("xyg_payload_errorbar_indices failed");
  }
  return result;
}

/**
 * Stem/errorbar emit count budget via `xyg_payload_segment_budget` (ABI 214).
 * `max(1024, floor(pxWidth) * 4)`.
 */
export function payloadSegmentBudget(pxWidth) {
  const width = Number(pxWidth);
  if (!Number.isFinite(width)) {
    throw new RangeError("payloadSegmentBudget pxWidth must be finite");
  }
  const raw = xyPayloadSegmentBudget(width);
  if (raw === USIZE_MAX_64) {
    throw new RangeError("invalid payload-segment-budget request");
  }
  return Number(raw);
}

/**
 * Density-overlay sample of implicit ids via `xyg_payload_sample_target_indices`.
 */
export function payloadSampleTargetIndices({
  n,
  target,
  seed = 0,
  level = 0,
  growth = 2.0,
} = {}) {
  const nI = Math.floor(Number(n));
  const targetI = Math.floor(Number(target));
  const seedI = Math.floor(Number(seed));
  const levelI = Math.floor(Number(level));
  const growthF = Number(growth);
  if (!Number.isFinite(nI) || nI < 0 || !Number.isFinite(targetI) || targetI <= 0) {
    throw new RangeError("payloadSampleTargetIndices n>=0 and target>=1");
  }
  if (!Number.isFinite(growthF) || growthF < 1) {
    throw new RangeError("payloadSampleTargetIndices growth must be >= 1");
  }
  const cap = nI ? Math.min(nI, Math.max(64, targetI * 2)) : 0;
  let out = new Uint32Array(cap);
  const keepAll = new Int32Array([-1]);
  let written = Number(xyPayloadSampleTargetIndices(
    BigInt(nI),
    BigInt(targetI),
    BigInt(seedI),
    levelI >>> 0,
    growthF,
    pointer(keepAll, "int32_t *"),
    cap ? u32Ptr(out) : 0,
    BigInt(cap),
  ));
  let result = readKeepAllIndices(written, keepAll, out, "xyg_payload_sample_target_indices");
  if (result.required != null) {
    out = new Uint32Array(result.required);
    keepAll[0] = -1;
    written = Number(xyPayloadSampleTargetIndices(
      BigInt(nI),
      BigInt(targetI),
      BigInt(seedI),
      levelI >>> 0,
      growthF,
      pointer(keepAll, "int32_t *"),
      u32Ptr(out),
      BigInt(result.required),
    ));
    result = readKeepAllIndices(written, keepAll, out, "xyg_payload_sample_target_indices");
    if (result.required != null || result.keepAll) {
      throw new Error("xyg_payload_sample_target_indices returned an inconsistent count");
    }
  }
  return result;
}

export const DENSITY_GRID_PATH_OVERSIZED_BIN2D = 0;
export const DENSITY_GRID_PATH_IDENTITY_GRID_ONLY = 1;
export const DENSITY_GRID_PATH_IDENTITY_STRATIFIED_FUSED = 2;
export const DENSITY_GRID_PATH_IDENTITY_STRATIFIED_SPLIT = 3;
export const DENSITY_GRID_PATH_IDENTITY_SAMPLE_FUSED = 4;
export const DENSITY_GRID_PATH_RANGE_INDICES = 5;

export const DENSITY_COLOR_MODE_NONE = 0;
export const DENSITY_COLOR_MODE_CONSTANT = 1;
export const DENSITY_COLOR_MODE_OTHER = 2;

export const DENSITY_OVERLAY_NONE = 0;
export const DENSITY_OVERLAY_ROWS_EXCEED_U32 = 1;
export const DENSITY_OVERLAY_STATIC_RASTER = 2;

const DENSITY_EMIT_META_BYTES = 96;

function readDensityEmitMeta(buf) {
  const view = new DataView(buf.buffer, buf.byteOffset, buf.byteLength);
  return {
    grid_path: view.getInt32(0, true),
    bin_window_x0: view.getFloat64(8, true),
    bin_window_x1: view.getFloat64(16, true),
    bin_window_y0: view.getFloat64(24, true),
    bin_window_y1: view.getFloat64(32, true),
    full_identity: view.getUint32(40, true) === 1,
    oversized: view.getUint32(44, true) === 1,
    pyramid_eligible: view.getUint32(48, true) === 1,
    pyramid_attempt: view.getUint32(52, true) === 1,
    pyramid_no_rescan: view.getUint32(56, true) === 1,
    pyramid_max_upsample: view.getUint32(60, true),
    pyramid_tile_upsample: view.getUint32(64, true),
    wasm_eligible: view.getUint32(68, true) === 1,
    needs_pyramid_sample: view.getUint32(72, true) === 1,
    overlay_omitted: view.getUint32(76, true),
    visible_is_n_points: view.getUint32(80, true) === 1,
    use_raw_range_bin2d: view.getUint32(84, true) === 1,
  };
}

export function densityFormatBinning({
  exact = false,
  level = 0,
  tiles = false,
  upsampled = false,
} = {}) {
  const out = new Uint8Array(64);
  const written = Number(xyDensityFormatBinning(
    exact ? 1 : 0,
    Number(level),
    tiles ? 1 : 0,
    upsampled ? 1 : 0,
    u8Ptr(out),
    BigInt(out.length),
  ));
  if (!Number.isFinite(written) || written === Number.MAX_SAFE_INTEGER) {
    throw new Error("xyg_density_format_binning failed");
  }
  return new TextDecoder().decode(out.subarray(0, written));
}

export function densityEmitPlan({
  cartesian = true,
  xLinear = true,
  yLinear = true,
  categorical = false,
  compactCategorical = false,
  stratifiedCounts = false,
  xHasNulls = false,
  yHasNulls = false,
  pointOverlay = true,
  gridFromPyramid = false,
  xMemmapped = false,
  yMemmapped = false,
  hasPyramidResource = false,
  forceBin2d = false,
  forcePyramid = false,
  colorMode = DENSITY_COLOR_MODE_NONE,
  xMin = 0,
  xMax = 1,
  yMin = 0,
  yMax = 1,
  xr0 = 0,
  xr1 = 1,
  yr0 = 0,
  yr1 = 1,
  xC0 = 0,
  xC1 = 1,
  yC0 = 0,
  yC1 = 1,
  nPoints = 0,
} = {}) {
  const out = new Uint8Array(DENSITY_EMIT_META_BYTES);
  const code = Number(xyDensityEmitMeta(
    cartesian ? 1 : 0,
    xLinear ? 1 : 0,
    yLinear ? 1 : 0,
    categorical ? 1 : 0,
    compactCategorical ? 1 : 0,
    stratifiedCounts ? 1 : 0,
    xHasNulls ? 1 : 0,
    yHasNulls ? 1 : 0,
    pointOverlay ? 1 : 0,
    gridFromPyramid ? 1 : 0,
    xMemmapped ? 1 : 0,
    yMemmapped ? 1 : 0,
    hasPyramidResource ? 1 : 0,
    forceBin2d ? 1 : 0,
    forcePyramid ? 1 : 0,
    Number(colorMode),
    Number(xMin),
    Number(xMax),
    Number(yMin),
    Number(yMax),
    Number(xr0),
    Number(xr1),
    Number(yr0),
    Number(yr1),
    Number(xC0),
    Number(xC1),
    Number(yC0),
    Number(yC1),
    BigInt(nPoints),
    u8Ptr(out),
  ));
  if (code !== 0) {
    throw new Error("xyg_density_emit_meta failed");
  }
  return readDensityEmitMeta(out);
}

export function densityWasmEligible({
  cartesian = true,
  xLinear = true,
  yLinear = true,
  colorMode = DENSITY_COLOR_MODE_NONE,
  xHasNulls = false,
  yHasNulls = false,
  nPoints = 0,
} = {}) {
  const code = Number(xyDensityWasmEligible(
    cartesian ? 1 : 0,
    xLinear ? 1 : 0,
    yLinear ? 1 : 0,
    Number(colorMode),
    xHasNulls ? 1 : 0,
    yHasNulls ? 1 : 0,
    BigInt(nPoints),
  ));
  if (code < 0) {
    throw new Error("xyg_density_wasm_eligible failed");
  }
  return code === 1;
}

/**
 * Whether a scatter should use the density tier (Python Trace.use_density).
 * Polar / forceDirect always ship direct; threshold is strict `>` (ABI 122).
 */
export function shouldUseDensity(nPoints, {
  forceDensity = false,
  forceDirect = false,
  coords = "cartesian",
  perItemChannels = false,
} = {}) {
  return payloadTier({
    kind: 1,
    nPoints,
    polar: coords === "polar",
    forceDensity: forceDensity ? 1 : -1,
    forceDirect,
    perItem: perItemChannels,
  }) === 2;
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
