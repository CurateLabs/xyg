/**
 * Thin line mark builder — TypedArray ingest, optional sort, M4 at emit.
 * Decimation decisions stay in Rust (`xyg_m4_indices` / `xyg_m4_points`).
 */

import {
  DECIMATION_THRESHOLD,
  asF64Array,
  argsortStable,
  isSorted,
  m4Indices,
  m4Points,
  minMax,
} from "../encode.js";

/** Same as `np.finfo(np.float64).eps` / Python `_payload._m4_decimate`. */
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
 * `_payload._m4_decimate` for the linear-axis common path.
 *
 * @param {ArrayLike|TypedArray} x
 * @param {ArrayLike|TypedArray} y
 * @param {{x0?: number, x1?: number, nBuckets?: number, threshold?: number}} [opts]
 * @returns {{tier: string, x: Float64Array, y: Float64Array, indices?: Uint32Array, nBuckets: number}}
 */
export function m4DecimateLine(x, y, opts = {}) {
  const prepared = prepareLineSeries(x, y);
  const xa = prepared.x;
  const ya = prepared.y;
  const threshold = opts.threshold ?? DECIMATION_THRESHOLD;
  const nBuckets = opts.nBuckets ?? 640;
  if (xa.length <= threshold) {
    return { tier: "direct", x: xa, y: ya, nBuckets };
  }
  const mm = minMax(xa) ?? [0, 1];
  const x0 = opts.x0 ?? mm[0];
  const x1 = (opts.x1 ?? mm[1]) + F64_EPS;
  const indices = m4Indices(xa, ya, x0, x1, nBuckets);
  if (indices.length === 0) {
    return {
      tier: "decimated",
      x: new Float64Array(0),
      y: new Float64Array(0),
      indices,
      nBuckets,
    };
  }
  const [outX, outY] = m4Points(xa, ya, x0, x1, nBuckets);
  return { tier: "decimated", x: outX, y: outY, indices, nBuckets };
}

/**
 * @param {ArrayLike|TypedArray} x
 * @param {ArrayLike|TypedArray} y
 * @param {{name?: string|null, style?: object, color?: string, width?: number}} [opts]
 */
export function composeLine(x, y, opts = {}) {
  const { x: xa, y: ya } = prepareLineSeries(x, y);
  const style = {
    color: opts.color ?? "#3987e5",
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
