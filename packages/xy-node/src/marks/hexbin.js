/**
 * Thin hexbin mark builder — TypedArrays → Rust `xyg_hexbin`
 * (finite-pair filter, automatic domain, default grid aspect, lattice).
 */

import { asF64Array, hexbin } from "../encode.js";

/**
 * @param {ArrayLike|TypedArray} x
 * @param {ArrayLike|TypedArray} y
 * @param {{
 *   gridsize?: number|[number, number],
 *   range?: [[number, number], [number, number]]|null,
 *   mincnt?: number,
 *   C?: ArrayLike|null,
 *   reduce?: "count"|"mean"|"sum",
 *   name?: string|null,
 *   style?: object,
 * }} [opts]
 */
export function composeHexbin(x, y, opts = {}) {
  const xa = asF64Array(x, "x");
  const ya = asF64Array(y, "y");
  if (xa.length !== ya.length) {
    throw new RangeError("hexbin x/y length mismatch");
  }
  const ca = opts.C == null ? null : asF64Array(opts.C, "C");
  if (ca != null && ca.length !== xa.length) {
    throw new RangeError("hexbin C length mismatch");
  }
  const gridsize = opts.gridsize ?? 16;
  const mincnt = opts.mincnt ?? (ca == null ? 0 : 1);
  const reduce = opts.reduce ?? "count";
  const result = hexbin(xa, ya, { gridsize, range: opts.range ?? null, mincnt, C: ca, reduce });
  if (result.centersX.length === 0) {
    throw new RangeError("hexbin range contains no finite points");
  }
  const constantColor = opts.color;
  const colormap = opts.colormap ?? "viridis";
  const style = {
    color: constantColor ?? "#3987e5",
    opacity: opts.opacity ?? 0.9,
    role: "hexbin",
    dx: result.dx,
    dy: result.dy,
    hex_dx: result.dx,
    hex_dy: result.dy,
    reduce,
    ...(opts.style ?? {}),
  };
  let color_ch;
  if (constantColor == null) {
    const metrics = result.metrics;
    let lo = Infinity;
    let hi = -Infinity;
    for (const value of metrics) {
      if (Number.isFinite(value)) {
        if (value < lo) lo = value;
        if (value > hi) hi = value;
      }
    }
    color_ch = {
      mode: "continuous",
      values: metrics,
      colormap: style.colormap ?? colormap,
      domain: Number.isFinite(lo) && Number.isFinite(hi) ? [lo, hi] : undefined,
    };
    delete style.colormap;
  }
  return {
    traces: [
      {
        kind: "hexbin",
        name: opts.name ?? null,
        x: result.centersX,
        y: result.centersY,
        metric: result.metrics,
        counts: result.counts,
        style,
        ...(color_ch != null ? { color_ch } : {}),
        n_points: xa.length,
        x_axis: opts.xAxis ?? "x",
        y_axis: opts.yAxis ?? "y",
        ...(opts.id != null ? { id: opts.id } : {}),
      },
    ],
    ...result,
  };
}

/**
 * @param {import("../figure.js").Figure} fig
 * @param {ArrayLike|TypedArray} x
 * @param {ArrayLike|TypedArray} y
 * @param {object} [opts]
 */
export function attachHexbin(fig, x, y, opts = {}) {
  const { traces } = composeHexbin(x, y, opts);
  const t = traces[0];
  fig.hexbin(t.x, t.y, {
    metric: t.metric,
    counts: t.counts,
    name: t.name,
    style: t.style,
    xAxis: t.x_axis,
    yAxis: t.y_axis,
    id: t.id,
  });
  return fig;
}
