/**
 * Tier-3 count pyramid — thin Node bindings over `xyg_pyramid_*`.
 *
 * Productized Phase-3 contract (lod-architecture.md §4 / Phase 3 items 6–7):
 * build once over the full data bounds, then compose any viewport in
 * O(grid cells). Records §28 `binning: "pyramid-L<l>[-upsampled]"`.
 *
 * Phase-4 disk-resident 256² tile spill remains a separate residency layer;
 * this module is the shippable serve path on both hosts.
 */

import {
  PYRAMID_BASE_DIM,
  PYRAMID_MAX_DIM,
  PYRAMID_MIN_POINTS,
  PYRAMID_NO_RESCAN_ROWS,
  asF64Array,
  f64Ptr,
  f32Ptr,
  minMax,
  u8Ptr,
} from "./encode.js";
import {
  xyPyramidAppend,
  xyPyramidAppendFromStream,
  xyPyramidBuild,
  xyPyramidBuildColor,
  xyPyramidBuildFromStream,
  xyPyramidCompose,
  xyPyramidComposeColor,
  xyPyramidCount,
  xyPyramidFree,
} from "./native.js";

function pyramidBaseDim(baseDim) {
  let d = Math.floor(Number(baseDim));
  if (!Number.isFinite(d) || d < 2) {
    throw new RangeError("pyramid base_dim must be ≥ 2");
  }
  // Next power of two, clamped.
  let p = 2;
  while (p < d) p <<= 1;
  return Math.min(p, PYRAMID_MAX_DIM);
}

function finiteIncreasing(a, b, label) {
  const lo = Number(a);
  const hi = Number(b);
  if (!(Number.isFinite(lo) && Number.isFinite(hi) && hi > lo)) {
    throw new RangeError(`pyramid ${label} must be a finite increasing pair`);
  }
  return [lo, hi];
}

/**
 * Adaptive base dim for huge / no-rescan traces (~sqrt(N/target), capped).
 */
export function pyramidBaseDimFor(nPoints, { noRescan = false, targetPerCell = 16 } = {}) {
  if (!noRescan) return PYRAMID_BASE_DIM;
  const n = Math.max(1, Number(nPoints));
  const ideal = Math.ceil(Math.sqrt(n / Math.max(1, targetPerCell)));
  return pyramidBaseDim(Math.max(PYRAMID_BASE_DIM, ideal));
}

export function shouldUsePyramid(nPoints, { forcePyramid = false, forceBin2d = false } = {}) {
  if (forceBin2d) return false;
  if (forcePyramid) return true;
  return Number(nPoints) >= PYRAMID_MIN_POINTS;
}

/**
 * @returns {bigint} nonzero handle, or 0n on failure
 */
export function pyramidBuild(x, y, x0, x1, y0, y1, baseDim = PYRAMID_BASE_DIM) {
  const xa = asF64Array(x, "x");
  const ya = asF64Array(y, "y");
  if (xa.length !== ya.length) throw new RangeError("pyramid x/y length mismatch");
  if (xa.length === 0) return 0n;
  const [a0, a1] = finiteIncreasing(x0, x1, "x range");
  const [b0, b1] = finiteIncreasing(y0, y1, "y range");
  const dim = pyramidBaseDim(baseDim);
  return BigInt(
    xyPyramidBuild(f64Ptr(xa), f64Ptr(ya), BigInt(xa.length), a0, a1, b0, b1, dim),
  );
}

/**
 * Colored pyramid (mean-color planes). `rgba` is length 4*n uint8 straight alpha.
 */
export function pyramidBuildColor(x, y, x0, x1, y0, y1, baseDim = PYRAMID_BASE_DIM, { rgba = null, idx = null, lut = null } = {}) {
  const xa = asF64Array(x, "x");
  const ya = asF64Array(y, "y");
  if (xa.length !== ya.length) throw new RangeError("pyramid x/y length mismatch");
  if (xa.length === 0) return 0n;
  const [a0, a1] = finiteIncreasing(x0, x1, "x range");
  const [b0, b1] = finiteIncreasing(y0, y1, "y range");
  const dim = pyramidBaseDim(baseDim);
  const rgbaArr = rgba == null ? null : rgba instanceof Uint8Array ? rgba : Uint8Array.from(rgba);
  const idxArr = idx == null ? null : idx instanceof Uint8Array ? idx : Uint8Array.from(idx);
  const lutArr = lut == null ? null : lut instanceof Uint8Array ? lut : Uint8Array.from(lut);
  return BigInt(
    xyPyramidBuildColor(
      f64Ptr(xa),
      f64Ptr(ya),
      BigInt(xa.length),
      idxArr == null ? null : u8Ptr(idxArr),
      rgbaArr == null ? null : u8Ptr(rgbaArr),
      lutArr == null ? null : u8Ptr(lutArr),
      BigInt(lutArr == null ? 0 : lutArr.length),
      a0,
      a1,
      b0,
      b1,
      dim,
    ),
  );
}

export function pyramidAppend(handle, x, y) {
  const xa = asF64Array(x, "x");
  const ya = asF64Array(y, "y");
  if (xa.length !== ya.length) throw new RangeError("pyramid append x/y length mismatch");
  return xyPyramidAppend(BigInt(handle), f64Ptr(xa), f64Ptr(ya), BigInt(xa.length)) === 1;
}

export function pyramidBuildFromStream(xHandle, yHandle, x0, x1, y0, y1, baseDim) {
  const [a0, a1] = finiteIncreasing(x0, x1, "x range");
  const [b0, b1] = finiteIncreasing(y0, y1, "y range");
  const dim = pyramidBaseDim(baseDim);
  return BigInt(
    xyPyramidBuildFromStream(BigInt(xHandle), BigInt(yHandle), a0, a1, b0, b1, dim),
  );
}

export function pyramidAppendFromStream(handle, xHandle, yHandle, tailLen) {
  const n = Number(tailLen);
  if (!Number.isInteger(n) || n < 0) {
    throw new RangeError("pyramid append-from-stream tail_len must be a non-negative integer");
  }
  return (
    xyPyramidAppendFromStream(BigInt(handle), BigInt(xHandle), BigInt(yHandle), BigInt(n)) === 1
  );
}

export function pyramidCount(handle, loX, hiX, loY, hiY) {
  const out = new Float64Array(1);
  const ok = xyPyramidCount(
    BigInt(handle),
    Number(loX),
    Number(hiX),
    Number(loY),
    Number(hiY),
    f64Ptr(out),
  );
  if (ok !== 1) return null;
  return out[0];
}

/**
 * @returns {{grid: Float32Array, level: number, binning: string}|null}
 */
export function pyramidCompose(
  handle,
  loX,
  hiX,
  loY,
  hiY,
  w,
  h,
  { maxUpsample = 2, noRescan = false } = {},
) {
  const ww = Math.max(1, Math.floor(Number(w)));
  const hh = Math.max(1, Math.floor(Number(h)));
  const up = Math.max(1, Math.floor(Number(maxUpsample)));
  const out = new Float32Array(ww * hh);
  const level = xyPyramidCompose(
    BigInt(handle),
    Number(loX),
    Number(hiX),
    Number(loY),
    Number(hiY),
    BigInt(ww),
    BigInt(hh),
    BigInt(up),
    f32Ptr(out),
  );
  if (level < 0) return null;
  const upsampled = Boolean(noRescan && level === 0);
  return {
    grid: out,
    level,
    binning: `pyramid-L${level}${upsampled ? "-upsampled" : ""}`,
  };
}

/**
 * @returns {{grid: Float32Array, rgba: Uint8Array, level: number, binning: string}|null}
 */
export function pyramidComposeColor(
  handle,
  loX,
  hiX,
  loY,
  hiY,
  w,
  h,
  { maxUpsample = 2, noRescan = false } = {},
) {
  const ww = Math.max(1, Math.floor(Number(w)));
  const hh = Math.max(1, Math.floor(Number(h)));
  const up = Math.max(1, Math.floor(Number(maxUpsample)));
  const out = new Float32Array(ww * hh);
  const rgba = new Uint8Array(ww * hh * 4);
  const level = xyPyramidComposeColor(
    BigInt(handle),
    Number(loX),
    Number(hiX),
    Number(loY),
    Number(hiY),
    BigInt(ww),
    BigInt(hh),
    BigInt(up),
    f32Ptr(out),
    u8Ptr(rgba),
  );
  if (level < 0) return null;
  const upsampled = Boolean(noRescan && level === 0);
  return {
    grid: out,
    rgba,
    level,
    binning: `pyramid-L${level}${upsampled ? "-upsampled" : ""}`,
  };
}

export function pyramidFree(handle) {
  return xyPyramidFree(BigInt(handle)) === 1;
}

/**
 * Estimate resident pyramid bytes (u32 counts + optional color planes).
 */
export function pyramidReportBytes(baseDim = PYRAMID_BASE_DIM, { colored = false } = {}) {
  const perCell = 4 + (colored ? 8 : 0);
  let total = 0;
  let dim = pyramidBaseDim(baseDim);
  while (true) {
    total += dim * dim * perCell;
    if (dim === 1) return total;
    dim >>= 1;
  }
}

/**
 * Lazy per-trace pyramid cache for Node figure / densityView.
 */
export class PyramidCache {
  constructor() {
    this.handle = 0n;
    this.baseDim = PYRAMID_BASE_DIM;
    this.colored = false;
    this.tried = false;
  }

  ensure(x, y, { force = false, noRescan = false, coloredRgba = null } = {}) {
    if (this.handle !== 0n) return this.handle;
    if (this.tried && !force) return 0n;
    const xa = asF64Array(x, "x");
    const ya = asF64Array(y, "y");
    if (!shouldUsePyramid(xa.length, { forcePyramid: force })) {
      this.tried = true;
      return 0n;
    }
    const xmm = minMax(xa);
    const ymm = minMax(ya);
    if (xmm == null || ymm == null || !(xmm[1] > xmm[0] && ymm[1] > ymm[0])) {
      this.tried = true;
      return 0n;
    }
    const x1 = xmm[1] + (xmm[1] - xmm[0]) * 1e-9;
    const y1 = ymm[1] + (ymm[1] - ymm[0]) * 1e-9;
    const dim = pyramidBaseDimFor(xa.length, {
      noRescan: noRescan || xa.length > PYRAMID_NO_RESCAN_ROWS,
    });
    let handle;
    if (coloredRgba != null) {
      handle = pyramidBuildColor(xa, ya, xmm[0], x1, ymm[0], y1, dim, { rgba: coloredRgba });
      this.colored = handle !== 0n;
    } else {
      handle = pyramidBuild(xa, ya, xmm[0], x1, ymm[0], y1, dim);
      this.colored = false;
    }
    this.handle = handle;
    this.baseDim = dim;
    this.tried = true;
    return handle;
  }

  free() {
    if (this.handle !== 0n) {
      pyramidFree(this.handle);
      this.handle = 0n;
    }
    this.tried = false;
  }
}

/**
 * Serve a density viewport from a pyramid when eligible; else null (caller bin2d).
 */
export function densityViewFromPyramid(
  cache,
  x,
  y,
  loX,
  hiX,
  loY,
  hiY,
  w,
  h,
  { force = false, noRescan = false } = {},
) {
  const n = asF64Array(x).length;
  const autoNoRescan = noRescan || n > PYRAMID_NO_RESCAN_ROWS;
  const handle = cache.ensure(x, y, { force, noRescan: autoNoRescan });
  if (handle === 0n) return null;
  const maxUpsample = autoNoRescan ? 1_000_000 : 2;
  const composed = pyramidCompose(handle, loX, hiX, loY, hiY, w, h, {
    maxUpsample,
    noRescan: autoNoRescan,
  });
  if (composed == null) return null;
  return {
    ...composed,
    reduction: "pyramid-count",
    tier: "density",
    handle,
    residentBytes: pyramidReportBytes(cache.baseDim, { colored: cache.colored }),
  };
}

export {
  PYRAMID_BASE_DIM,
  PYRAMID_MAX_DIM,
  PYRAMID_MIN_POINTS,
  PYRAMID_NO_RESCAN_ROWS,
};
