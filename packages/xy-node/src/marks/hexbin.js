/**
 * Hexbin mark — native `xy_hexbin` lattice → center points + metric channel.
 */

import { asF64Array, hexbin, minMax } from "../encode.js";

function autoDomain(arr) {
  const mm = minMax(arr);
  if (mm == null) return [0, 1];
  if (mm[0] === mm[1]) return [mm[0] - 0.5, mm[1] + 0.5];
  return mm;
}

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
  const finiteX = [];
  const finiteY = [];
  const finiteC = opts.C == null ? null : [];
  const ca = opts.C == null ? null : asF64Array(opts.C, "C");
  for (let i = 0; i < xa.length; i += 1) {
    if (!Number.isFinite(xa[i]) || !Number.isFinite(ya[i])) continue;
    if (ca != null && !Number.isFinite(ca[i])) continue;
    finiteX.push(xa[i]);
    finiteY.push(ya[i]);
    if (finiteC != null) finiteC.push(ca[i]);
  }
  if (finiteX.length === 0) {
    throw new RangeError("hexbin x and y must contain at least one finite pair");
  }
  const xv = Float64Array.from(finiteX);
  const yv = Float64Array.from(finiteY);
  const cv = finiteC == null ? null : Float64Array.from(finiteC);
  const gridsize = opts.gridsize ?? 16;
  const [w, h] = Array.isArray(gridsize) ? gridsize : [gridsize, Math.max(2, Math.round(gridsize / Math.sqrt(3)))];
  const range = opts.range ?? [autoDomain(xv), autoDomain(yv)];
  const mincnt = opts.mincnt ?? (cv == null ? 0 : 1);
  const reduce = opts.reduce ?? "count";
  const result = hexbin(xv, yv, { gridsize: [w, h], range, mincnt, C: cv, reduce });
  if (result.centersX.length === 0) {
    throw new RangeError("hexbin range contains no finite points");
  }
  const style = {
    color: opts.color ?? "#3987e5",
    opacity: opts.opacity ?? 0.9,
    role: "hexbin",
    dx: result.dx,
    dy: result.dy,
    reduce,
    ...(opts.style ?? {}),
  };
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
