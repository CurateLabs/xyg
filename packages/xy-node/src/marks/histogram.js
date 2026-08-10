/**
 * Thin histogram mark builder — TypedArray values → Rust `xy_histogram_uniform`
 * → rectangle columns attached as a histogram trace (Python common path).
 */

import { asF64Array, histogramUniform, minMax } from "../encode.js";

/**
 * @param {ArrayLike|TypedArray} values
 * @param {{
 *   bins?: number,
 *   range?: [number, number]|null,
 *   density?: boolean,
 *   cumulative?: boolean,
 *   name?: string|null,
 *   style?: object,
 *   color?: string,
 * }} [opts]
 * @returns {{
 *   traces: object[],
 *   counts: Float64Array,
 *   edges: Float64Array,
 *   total: number,
 * }}
 */
export function composeHistogram(values, opts = {}) {
  const vals = asF64Array(values, "values");
  const nBins = opts.bins ?? 10;
  if (!Number.isInteger(nBins) || nBins <= 0) {
    throw new RangeError("histogram bins must be a positive integer");
  }
  const density = Boolean(opts.density);
  const cumulative = Boolean(opts.cumulative);
  let lo;
  let hi;
  if (opts.range != null) {
    lo = Number(opts.range[0]);
    hi = Number(opts.range[1]);
    if (!(Number.isFinite(lo) && Number.isFinite(hi) && hi > lo)) {
      throw new RangeError("histogram range must be a finite increasing pair");
    }
  } else {
    const mm = minMax(vals);
    if (mm == null) {
      lo = 0;
      hi = 1;
    } else if (mm[0] === mm[1]) {
      lo = mm[0] - 0.5;
      hi = mm[1] + 0.5;
    } else {
      [lo, hi] = mm;
    }
  }
  const { counts: rawCounts, edges, total } = histogramUniform(vals, lo, hi, nBins, {
    density,
  });
  let counts = rawCounts;
  if (cumulative) {
    const out = new Float64Array(counts.length);
    if (density) {
      let acc = 0;
      for (let i = 0; i < counts.length; i += 1) {
        const width = edges[i + 1] - edges[i];
        acc += counts[i] * width;
        out[i] = acc;
      }
    } else {
      let acc = 0;
      for (let i = 0; i < counts.length; i += 1) {
        acc += counts[i];
        out[i] = acc;
      }
    }
    counts = out;
  }
  const x0 = edges.subarray(0, nBins);
  const x1 = edges.subarray(1, nBins + 1);
  const y0 = new Float64Array(nBins);
  const y1 = Float64Array.from(counts);
  const style = {
    color: opts.color ?? "#3987e5",
    opacity: 0.85,
    role: "histogram",
    cumulative,
    density,
    ...(opts.style ?? {}),
  };
  return {
    traces: [
      {
        kind: "histogram",
        name: opts.name ?? null,
        x0: Float64Array.from(x0),
        x1: Float64Array.from(x1),
        y0,
        y1,
        style,
        count: vals.length,
        x_axis: opts.xAxis ?? "x",
        y_axis: opts.yAxis ?? "y",
        ...(opts.id != null ? { id: opts.id } : {}),
      },
    ],
    counts,
    edges,
    total,
  };
}

/**
 * @param {import("../figure.js").Figure} fig
 * @param {ArrayLike|TypedArray} values
 * @param {object} [opts]
 */
export function attachHistogram(fig, values, opts = {}) {
  fig.histogram(values, opts);
  return fig;
}
