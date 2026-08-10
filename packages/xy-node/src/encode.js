/**
 * Offset-encoded f32 geometry (§4/§16) and shared encode helpers.
 * Bit-identical to python/xy/lod.encode_f32_values when calling xy_encode_f32.
 */
import { pointer, xyEncodeF32, xyIsSorted, xyMinMax, xyM4Points, xyM4Indices, xyHistogramUniform, xyNormalizeF32 } from "./native.js";

export const PROTOCOL_VERSION = 12;
export const DECIMATION_THRESHOLD = 10_000;
export const SCATTER_DENSITY_THRESHOLD = 200_000;
export const DIRECT_SOFT_CEILING = 2_000_000;
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
    throw new Error("xy_encode_f32 failed");
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
    throw new Error("xy_m4_points failed");
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
    throw new Error("xy_m4_indices failed");
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
    throw new Error("xy_histogram_uniform failed");
  }
  const edges = new Float64Array(nBins + 1);
  const width = (hi - lo) / nBins;
  for (let i = 0; i <= nBins; i += 1) {
    edges[i] = lo + i * width;
  }
  return { counts, edges, total };
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
    throw new Error("xy_normalize_f32 failed");
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
}

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
