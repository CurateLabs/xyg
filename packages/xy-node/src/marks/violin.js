/**
 * Violin mark — `xy_violin_density` → instanced rectangle bands.
 */

import { asF64Array, violinDensity } from "../encode.js";

/**
 * @param {ArrayLike|TypedArray} values
 * @param {{
 *   x?: number,
 *   width?: number,
 *   bins?: number,
 *   orientation?: "vertical"|"horizontal",
 *   name?: string|null,
 *   style?: object,
 *   color?: string,
 * }} [opts]
 */
export function composeViolin(values, opts = {}) {
  const arr = asF64Array(values, "values");
  const finite = arr.filter((v) => Number.isFinite(v));
  if (finite.length === 0) {
    throw new RangeError("violin values must contain at least one finite value");
  }
  const nBins = opts.bins ?? 64;
  const { edges, density } = violinDensity(Float64Array.from(finite), nBins);
  const center = Number(opts.x ?? 0);
  const width = Number(opts.width ?? 0.8);
  const orientation = opts.orientation ?? "vertical";
  let peak = 0;
  for (let i = 0; i < density.length; i += 1) {
    if (density[i] > peak) peak = density[i];
  }
  if (peak === 0) peak = 1;
  const x0 = new Float64Array(nBins);
  const x1 = new Float64Array(nBins);
  const y0 = new Float64Array(nBins);
  const y1 = new Float64Array(nBins);
  for (let i = 0; i < nBins; i += 1) {
    const half = (width * 0.5 * density[i]) / peak;
    if (orientation === "vertical") {
      x0[i] = center - half;
      x1[i] = center + half;
      y0[i] = edges[i];
      y1[i] = edges[i + 1];
    } else {
      x0[i] = edges[i];
      x1[i] = edges[i + 1];
      y0[i] = center - half;
      y1[i] = center + half;
    }
  }
  const style = {
    color: opts.color ?? "#3987e5",
    opacity: opts.opacity ?? 0.55,
    role: "violin",
    orientation,
    ...(opts.style ?? {}),
  };
  return {
    traces: [
      {
        kind: "violin",
        name: opts.name ?? null,
        x0,
        x1,
        y0,
        y1,
        style,
        edges,
        density,
        x_axis: opts.xAxis ?? "x",
        y_axis: opts.yAxis ?? "y",
        ...(opts.id != null ? { id: opts.id } : {}),
      },
    ],
    edges,
    density,
  };
}

/**
 * @param {import("../figure.js").Figure} fig
 * @param {ArrayLike|TypedArray} values
 * @param {object} [opts]
 */
export function attachViolin(fig, values, opts = {}) {
  fig.violin(values, opts);
  return fig;
}
