/**
 * Violin mark — `xy_violin_density` → instanced rectangle bands (multi-group).
 */

import { violinRects } from "../encode.js";
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
  if (!Number.isFinite(width) || width <= 0) throw new RangeError("violin width must be positive and finite");
  if (orientation !== "vertical" && orientation !== "horizontal") throw new RangeError("violin orientation must be 'vertical' or 'horizontal'");
  const color = opts.color ?? "#3987e5";
  const opacity = opts.opacity ?? 0.55;

  const compiled = violinRects(groups.map((group) => Float64Array.from(group)), positions, nBins, width, orientation);
  const { x0, x1, y0, y1 } = compiled;
  const allEdges = compiled.groupEdges, allDensity = compiled.groupDensity;

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
        x0, x1, y0, y1,
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
