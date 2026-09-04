/**
 * Thin line mark builder — TypedArray ingest, optional sort, M4 at emit.
 * Decimation decisions stay in Rust (`xyg_payload_m4_indices`).
 */

import {
  asF64Array,
  argsortStable,
  DEFAULT_MARK_COLOR,
  isSorted,
  minMax,
  payloadM4Indices,
} from "../encode.js";

/** Same as `np.finfo(np.float64).eps`; ABI 204 owns the closed-window ulp. */
export const F64_EPS = Number.EPSILON;

function gather(arr, idx) {
  const out = new Float64Array(idx.length);
  for (let i = 0; i < idx.length; i += 1) out[i] = arr[idx[i]];
  return out;
}

/**
 * Coerce + sort (when needed) like Python `marks.line` ingest.
 * @returns {{x: Float64Array, y: Float64Array, sorted: boolean}}
 */
export function prepareLineSeries(x, y) {
  let xa = asF64Array(x, "x");
  let ya = asF64Array(y, "y");
  if (xa.length !== ya.length) {
    throw new RangeError("line x/y length mismatch");
  }
  let sorted = false;
  if (xa.length > 1 && !isSorted(xa)) {
    const order = argsortStable(xa);
    xa = gather(xa, order);
    ya = gather(ya, order);
    sorted = true;
  }
  return { x: xa, y: ya, sorted };
}

/**
 * M4-decimate a monotone (or pre-sorted) series — mirrors Python
 * `_payload._m4_decimate`.
 *
 * @param {ArrayLike|TypedArray} x
 * @param {ArrayLike|TypedArray} y
 * @param {{x0?: number, x1?: number, nBuckets?: number, polar?: boolean, coords?: string, binX?: ArrayLike|TypedArray, binX0?: number, binX1?: number}} [opts]
 * @returns {{tier: string, x: Float64Array, y: Float64Array, indices?: Uint32Array, nBuckets: number}}
 */
export function m4DecimateLine(x, y, opts = {}) {
  const prepared = prepareLineSeries(x, y);
  const xa = prepared.x;
  const ya = prepared.y;
  const nBuckets = opts.nBuckets ?? 640;
  const polar = Boolean(opts.polar) || opts.coords === "polar";
  const mm = minMax(xa) ?? [0, 1];
  const x0 = opts.x0 ?? mm[0];
  const x1 = opts.x1 ?? mm[1];
  const { tier, indices } = payloadM4Indices({
    nPoints: xa.length,
    x: xa,
    y: ya,
    x0,
    x1,
    nBuckets,
    polar,
    binX: opts.binX ?? null,
    binX0: opts.binX0 ?? 0,
    binX1: opts.binX1 ?? 0,
  });
  if (tier === 0) {
    return { tier: "direct", x: xa, y: ya, nBuckets };
  }
  if (indices.length === 0) {
    return {
      tier: "decimated",
      x: new Float64Array(0),
      y: new Float64Array(0),
      indices,
      nBuckets,
    };
  }
  return {
    tier: "decimated",
    x: gather(xa, indices),
    y: gather(ya, indices),
    indices,
    nBuckets,
  };
}

/**
 * @param {ArrayLike|TypedArray} x
 * @param {ArrayLike|TypedArray} y
 * @param {{name?: string|null, style?: object, color?: string, width?: number}} [opts]
 */
export function composeLine(x, y, opts = {}) {
  const { x: xa, y: ya } = prepareLineSeries(x, y);
  const style = {
    color: opts.color ?? DEFAULT_MARK_COLOR,
    width: opts.width ?? 1.5,
    opacity: 1.0,
    ...(opts.style ?? {}),
  };
  return {
    traces: [
      {
        kind: "line",
        name: opts.name ?? null,
        x: xa,
        y: ya,
        style,
        x_axis: opts.xAxis ?? "x",
        y_axis: opts.yAxis ?? "y",
        ...(opts.id != null ? { id: opts.id } : {}),
      },
    ],
  };
}

/**
 * @param {import("../figure.js").Figure} fig
 * @param {ArrayLike|TypedArray} x
 * @param {ArrayLike|TypedArray} y
 * @param {object} [opts]
 */
export function attachLine(fig, x, y, opts = {}) {
  const { traces } = composeLine(x, y, opts);
  const t = traces[0];
  fig.line(t.x, t.y, {
    name: t.name,
    style: t.style,
    xAxis: t.x_axis,
    yAxis: t.y_axis,
    id: t.id,
  });
  return fig;
}
