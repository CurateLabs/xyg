/**
 * Violin mark — `xy_violin_density` → instanced rectangle bands (multi-group).
 */

import { violinDensity } from "../encode.js";
import { distributionGroups } from "./distribution.js";

/**
 * @param {ArrayLike|TypedArray|ArrayLike[]} values
 * @param {{
 *   x?: ArrayLike|number|null,
 *   group?: ArrayLike|null,
 *   width?: number,
 *   bins?: number,
 *   orientation?: "vertical"|"horizontal",
 *   name?: string|null,
 *   style?: object,
 *   color?: string,
 *   opacity?: number,
 * }} [opts]
 */
export function composeViolin(values, opts = {}) {
  const { groups, positions } = distributionGroups(values, {
    x: opts.x,
    group: opts.group,
    kind: "violin",
  });
  const nBins = opts.bins ?? 64;
  if (!Number.isInteger(nBins) || nBins < 4 || nBins > 1024) {
    throw new RangeError("violin bins must be an integer between 4 and 1024");
  }
  const width = Number(opts.width ?? 0.8);
  const orientation = opts.orientation ?? "vertical";
  const color = opts.color ?? "#3987e5";
  const opacity = opts.opacity ?? 0.55;

  const x0 = [];
  const x1 = [];
  const y0 = [];
  const y1 = [];
  const allEdges = [];
  const allDensity = [];

  for (let gi = 0; gi < groups.length; gi += 1) {
    const finite = groups[gi].filter((v) => Number.isFinite(v));
    if (finite.length === 0) continue;
    const { edges, density } = violinDensity(Float64Array.from(finite), nBins);
    let peak = 0;
    for (let i = 0; i < density.length; i += 1) {
      if (density[i] > peak) peak = density[i];
    }
    if (peak === 0) peak = 1;
    const center = positions[gi];
    for (let i = 0; i < nBins; i += 1) {
      const half = (width * 0.5 * density[i]) / peak;
      if (orientation === "vertical") {
        x0.push(center - half);
        x1.push(center + half);
        y0.push(edges[i]);
        y1.push(edges[i + 1]);
      } else {
        x0.push(edges[i]);
        x1.push(edges[i + 1]);
        y0.push(center - half);
        y1.push(center + half);
      }
    }
    allEdges.push(edges);
    allDensity.push(density);
  }
  if (x0.length === 0) {
    throw new RangeError("violin values must contain at least one finite group");
  }

  const style = {
    color,
    opacity,
    role: "violin",
    orientation,
    ...(opts.style ?? {}),
  };
  return {
    traces: [
      {
        kind: "violin",
        name: opts.name ?? null,
        x0: Float64Array.from(x0),
        x1: Float64Array.from(x1),
        y0: Float64Array.from(y0),
        y1: Float64Array.from(y1),
        style,
        edges: allEdges[0],
        density: allDensity[0],
        x_axis: opts.xAxis ?? "x",
        y_axis: opts.yAxis ?? "y",
        ...(opts.id != null ? { id: opts.id } : {}),
      },
    ],
    // Single-group goldens read `.edges` / `.density` as TypedArrays.
    edges: allEdges.length === 1 ? allEdges[0] : allEdges,
    density: allDensity.length === 1 ? allDensity[0] : allDensity,
    groupEdges: allEdges,
    groupDensity: allDensity,
    positions,
    groups: groups.length,
  };
}

/**
 * @param {import("../figure.js").Figure} fig
 * @param {ArrayLike|TypedArray|ArrayLike[]} values
 * @param {object} [opts]
 */
export function attachViolin(fig, values, opts = {}) {
  fig.violin(values, opts);
  return fig;
}
