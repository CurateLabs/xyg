/**
 * Error / confidence band — filled strip between lower and upper (area geometry).
 */

import { asF64Array, isSorted } from "../encode.js";

function stableArgsort(arr) {
  const idx = new Uint32Array(arr.length);
  for (let i = 0; i < arr.length; i += 1) idx[i] = i;
  idx.sort((a, b) => {
    const va = arr[a];
    const vb = arr[b];
    const aNan = !(va === va);
    const bNan = !(vb === vb);
    if (aNan && bNan) return a - b;
    if (aNan) return 1;
    if (bNan) return -1;
    if (va < vb) return -1;
    if (va > vb) return 1;
    return a - b;
  });
  return idx;
}

function gather(arr, idx) {
  const out = new Float64Array(idx.length);
  for (let i = 0; i < idx.length; i += 1) out[i] = arr[idx[i]];
  return out;
}

/**
 * @param {ArrayLike|TypedArray} x
 * @param {ArrayLike|TypedArray} lower
 * @param {ArrayLike|TypedArray} upper
 * @param {{
 *   name?: string|null,
 *   color?: string,
 *   opacity?: number,
 *   lineWidth?: number,
 *   lineOpacity?: number,
 *   style?: object,
 * }} [opts]
 */
export function composeErrorBand(x, lower, upper, opts = {}) {
  let xa = asF64Array(x, "x");
  let lo = asF64Array(lower, "lower");
  let hi = asF64Array(upper, "upper");
  if (xa.length !== lo.length) {
    throw new RangeError(`error_band lower must have length ${xa.length}, got ${lo.length}`);
  }
  if (hi.length !== xa.length) {
    throw new RangeError(`error_band upper must have length ${xa.length}, got ${hi.length}`);
  }
  if (xa.length > 1 && !isSorted(xa)) {
    const order = stableArgsort(xa);
    xa = gather(xa, order);
    lo = gather(lo, order);
    hi = gather(hi, order);
  }
  const style = {
    color: opts.color ?? "#3987e5",
    opacity: opts.opacity ?? 0.22,
    line_width: opts.lineWidth ?? 0.0,
    line_opacity: opts.lineOpacity ?? 0.0,
    role: "error-band",
    ...(opts.style ?? {}),
  };
  return {
    traces: [
      {
        kind: "error_band",
        name: opts.name ?? null,
        x: xa,
        y: hi,
        base: lo,
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
 * @param {ArrayLike|TypedArray} lower
 * @param {ArrayLike|TypedArray} upper
 * @param {object} [opts]
 */
export function attachErrorBand(fig, x, lower, upper, opts = {}) {
  const { traces } = composeErrorBand(x, lower, upper, opts);
  const t = traces[0];
  fig.traces.push({
    id: t.id ?? fig.traces.length,
    ...t,
  });
  return fig;
}
