/**
 * ECDF mark — exact and binned paths via `xyg_weighted_ecdf` and
 * `xyg_binned_ecdf`.
 */

import { asF64Array, binnedEcdf, DEFAULT_MARK_COLOR, weightedEcdf } from "../encode.js";

function finiteValues(values) {
  const arr = asF64Array(values, "values");
  const out = [];
  for (let i = 0; i < arr.length; i += 1) {
    if (Number.isFinite(arr[i])) out.push(arr[i]);
  }
  if (out.length === 0) {
    throw new RangeError("ecdf values must contain at least one finite value");
  }
  return Float64Array.from(out);
}

/**
 * Build step-function ECDF coordinates (right-continuous, anchored at 0).
 * @param {ArrayLike|TypedArray} values
 * @param {{ bins?: number|null, range?: [number, number]|null }} [opts]
 */
export function computeEcdf(values, opts = {}) {
  const rawValues = asF64Array(values, "values");
  if (opts.bins != null) {
    const nBins = Number(opts.bins);
    if (!Number.isInteger(nBins) || nBins <= 0) {
      throw new RangeError("ecdf bins must be a positive integer");
    }
    let result;
    try {
      result = binnedEcdf(rawValues, nBins, { range: opts.range ?? null });
    } catch (error) {
      if (!rawValues.some(Number.isFinite)) {
        throw new RangeError("ecdf values must contain at least one finite value");
      }
      throw error;
    }
    const { x, cumulative } = result;
    return { x, y: cumulative, mode: "binned" };
  }
  const vals = finiteValues(rawValues);
  const weights = new Float64Array(vals.length).fill(1.0);
  const { values: unique, cumulative } = weightedEcdf(vals, weights);
  const sx = new Float64Array(unique.length + 1);
  const sy = new Float64Array(unique.length + 1);
  sx[0] = unique[0];
  sy[0] = 0.0;
  for (let i = 0; i < unique.length; i += 1) {
    sx[i + 1] = unique[i];
    sy[i + 1] = cumulative[i];
  }
  return { x: sx, y: sy, mode: "exact" };
}

/**
 * @param {ArrayLike|TypedArray} values
 * @param {object} [opts]
 */
export function composeEcdf(values, opts = {}) {
  const { x, y, mode } = computeEcdf(values, opts);
  const style = {
    color: opts.color ?? DEFAULT_MARK_COLOR,
    width: opts.width ?? 1.5,
    opacity: opts.opacity ?? 1.0,
    step: "post",
    ...(opts.style ?? {}),
  };
  return {
    traces: [
      {
        // Browser MARK_KINDS: ecdf ships as line + style.step (not a wire kind).
        kind: "line",
        name: opts.name ?? null,
        x,
        y,
        style,
        mode,
        x_axis: opts.xAxis ?? "x",
        y_axis: opts.yAxis ?? "y",
        ...(opts.id != null ? { id: opts.id } : {}),
      },
    ],
  };
}

/**
 * @param {import("../figure.js").Figure} fig
 * @param {ArrayLike|TypedArray} values
 * @param {object} [opts]
 */
export function attachEcdf(fig, values, opts = {}) {
  // Reuse the Figure method so the public constructor and fluent API keep
  // identical top-level diagnostic metadata instead of leaking mode into style.
  return fig.ecdf(values, opts);
}
