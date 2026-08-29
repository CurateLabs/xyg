/**
 * Heatmap mark — 2-D scalar grid + optional `xy_heatmap_rgba` colormap.
 */

import { asF64Array, heatmapRgba, minMax } from "../encode.js";

function cellEdges(pos, n) {
  if (pos != null) {
    const p = asF64Array(pos);
    if (p.length !== n) {
      throw new RangeError(`heatmap axis positions must have length ${n}`);
    }
    if (n === 1) {
      const c = p[0];
      return Float64Array.from([c - 0.5, c + 0.5]);
    }
    const edges = new Float64Array(n + 1);
    edges[0] = p[0] - (p[1] - p[0]) / 2.0;
    for (let i = 1; i < n; i += 1) {
      edges[i] = (p[i - 1] + p[i]) / 2.0;
    }
    edges[n] = p[n - 1] + (p[n - 1] - p[n - 2]) / 2.0;
    return edges;
  }
  const edges = new Float64Array(n + 1);
  for (let i = 0; i <= n; i += 1) edges[i] = i - 0.5;
  return edges;
}

/**
 * @param {ArrayLike|TypedArray|number[][]} z rows×cols or flat length rows*cols
 * @param {{
 *   rows?: number,
 *   cols?: number,
 *   x?: ArrayLike|null,
 *   y?: ArrayLike|null,
 *   domain?: [number, number]|null,
 *   colormapStops?: Uint8Array|number[],
 *   name?: string|null,
 *   style?: object,
 * }} [opts]
 */
export function composeHeatmap(z, opts = {}) {
  let rows = opts.rows;
  let cols = opts.cols;
  let flat;
  if (Array.isArray(z) && Array.isArray(z[0])) {
    rows = z.length;
    cols = z[0].length;
    flat = new Float64Array(rows * cols);
    let k = 0;
    for (let r = 0; r < rows; r += 1) {
      for (let c = 0; c < cols; c += 1) {
        flat[k] = Number(z[r][c]);
        k += 1;
      }
    }
  } else {
    flat = asF64Array(z, "z");
    if (rows == null || cols == null) {
      throw new RangeError("heatmap rows/cols required for flat z input");
    }
    if (flat.length !== rows * cols) {
      throw new RangeError("heatmap z length must equal rows * cols");
    }
  }
  const xEdges = cellEdges(opts.x, cols);
  const yEdges = cellEdges(opts.y, rows);
  const mm = minMax(flat) ?? [0, 1];
  let lo;
  let hi;
  if (opts.domain != null) {
    lo = Number(opts.domain[0]);
    hi = Number(opts.domain[1]);
  } else if (mm[0] === mm[1]) {
    lo = mm[0] - 0.5;
    hi = mm[1] + 0.5;
  } else {
    [lo, hi] = mm;
  }
  const style = {
    color: opts.color ?? "#3987e5",
    opacity: opts.opacity ?? 0.95,
    role: "heatmap",
    domain: [lo, hi],
    x_range: [xEdges[0], xEdges[xEdges.length - 1]],
    y_range: [yEdges[0], yEdges[yEdges.length - 1]],
    ...(opts.colormap != null ? { colormap: opts.colormap } : {}),
    ...(opts.style ?? {}),
  };
  let rgba = null;
  if (opts.colormapStops != null) {
    rgba = heatmapRgba(flat, cols, rows, opts.colormapStops, opts.alpha ?? 255).rgba;
  }
  return {
    traces: [
      {
        kind: "heatmap",
        name: opts.name ?? null,
        x: Float64Array.from([xEdges[0], xEdges[xEdges.length - 1]]),
        y: Float64Array.from([yEdges[0], yEdges[yEdges.length - 1]]),
        grid: flat,
        grid_shape: [rows, cols],
        rgba,
        colormapStops: opts.colormapStops ?? null,
        style,
        count: flat.length,
        x_axis: opts.xAxis ?? "x",
        y_axis: opts.yAxis ?? "y",
        ...(opts.id != null ? { id: opts.id } : {}),
      },
    ],
    domain: [lo, hi],
  };
}

/**
 * @param {import("../figure.js").Figure} fig
 * @param {ArrayLike|TypedArray|number[][]} z
 * @param {object} [opts]
 */
export function attachHeatmap(fig, z, opts = {}) {
  const { traces } = composeHeatmap(z, opts);
  const t = traces[0];
  fig.heatmap(t.grid, {
    rows: t.grid_shape[0],
    cols: t.grid_shape[1],
    x: opts.x,
    y: opts.y,
    name: t.name,
    style: t.style,
    domain: t.style.domain,
    colormapStops: opts.colormapStops,
    xAxis: t.x_axis,
    yAxis: t.y_axis,
    id: t.id,
  });
  return fig;
}
