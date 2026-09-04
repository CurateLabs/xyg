/**
 * Thin histogram mark builder — TypedArray values → Rust `xyg_histogram_bins`
 * → rectangle columns attached as a histogram trace (Python common path).
 */

import { asF64Array, DEFAULT_MARK_COLOR, histogramBins, histogramMarkEdges } from "../encode.js";

function isAuthoredEdges(bins) {
  return Array.isArray(bins) || ArrayBuffer.isView(bins);
}

/**
 * @param {ArrayLike|TypedArray} values
 * @param {{
 *   bins?: number|ArrayLike,
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
  const density = Boolean(opts.density);
  const cumulative = Boolean(opts.cumulative);
  if (opts.range != null) {
    const lo = Number(opts.range[0]);
    const hi = Number(opts.range[1]);
    if (!(Number.isFinite(lo) && Number.isFinite(hi) && hi > lo)) {
      throw new RangeError("histogram range must be a finite increasing pair");
    }
  }
  let edges;
  if (isAuthoredEdges(opts.bins)) {
    edges = asF64Array(opts.bins, "bins");
    if (edges.length < 2) {
      throw new RangeError("histogram bins must contain at least two edges");
    }
  } else if (opts.bins == null || typeof opts.bins === "string") {
    const method = opts.bins == null ? "auto" : String(opts.bins).toLowerCase();
    if (method !== "auto" && method !== "sturges") {
      throw new RangeError("histogram bins must be a positive integer");
    }
    edges = Float64Array.from(histogramMarkEdges(vals, { range: opts.range, method }));
  } else {
    const nBins = opts.bins;
    if (!Number.isInteger(nBins) || nBins <= 0) {
      throw new RangeError("histogram bins must be a positive integer");
    }
    edges = Float64Array.from(
      histogramMarkEdges(vals, { range: opts.range, method: "uniform", nBins }),
    );
  }
  const counts = histogramBins(vals, edges, { density, cumulative });
  const nBins = counts.length;
  const total = density
    ? Number.NaN
    : Number(cumulative ? (counts[nBins - 1] ?? 0) : counts.reduce((sum, value) => sum + value, 0));
  const x0 = edges.subarray(0, nBins);
  const x1 = edges.subarray(1, nBins + 1);
  const y0 = new Float64Array(nBins);
  const y1 = Float64Array.from(counts);
  const style = {
    color: opts.color ?? DEFAULT_MARK_COLOR,
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
