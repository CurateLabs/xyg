/**
 * ECDF mark — exact path via `xy_weighted_ecdf`, binned path via histogram.
 */

import { asF64Array, histogramUniform, weightedEcdf } from "../encode.js";

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
  const vals = finiteValues(values);
  if (opts.bins != null) {
    const nBins = Number(opts.bins);
    if (!Number.isInteger(nBins) || nBins <= 0) {
      throw new RangeError("ecdf bins must be a positive integer");
    }
    let lo;
    let hi;
    if (opts.range != null) {
      lo = Number(opts.range[0]);
      hi = Number(opts.range[1]);
    } else {
      lo = vals[0];
      hi = vals[0];
      for (let i = 1; i < vals.length; i += 1) {
        if (vals[i] < lo) lo = vals[i];
        if (vals[i] > hi) hi = vals[i];
      }
      if (lo === hi) {
        lo -= 0.5;
        hi += 0.5;
      }
    }
    const { counts, edges } = histogramUniform(vals, lo, hi, nBins, { density: false });
    const sx = [edges[0]];
    const sy = [0.0];
    let acc = 0;
    for (let i = 0; i < counts.length; i += 1) {
      if (counts[i] > 0) {
        acc += counts[i];
        sx.push(edges[i + 1]);
        sy.push(acc / vals.length);
      }
    }
    return { x: Float64Array.from(sx), y: Float64Array.from(sy), mode: "binned" };
  }
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
    color: opts.color ?? "#3987e5",
    width: opts.width ?? 1.5,
    opacity: opts.opacity ?? 1.0,
    role: "ecdf",
    step: "post",
    ...(opts.style ?? {}),
  };
  return {
    traces: [
      {
        // Browser MARK_KINDS: ecdf ships as line + style.step/role (not a wire kind).
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
  const { traces } = composeEcdf(values, opts);
  const t = traces[0];
  // Wire kind is `line` + style.step/role (MARK_KINDS); keep mode on the style.
  fig.line(t.x, t.y, {
    name: t.name,
    style: { ...t.style, mode: t.mode },
    xAxis: t.x_axis,
    yAxis: t.y_axis,
    id: t.id,
  });
  return fig;
}
