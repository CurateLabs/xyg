/**
 * Stem mark — vertical segments from base to y, optional scatter markers.
 */

import { asF64Array } from "../encode.js";

/**
 * @param {ArrayLike|TypedArray} x
 * @param {ArrayLike|TypedArray} y
 * @param {{
 *   base?: number|ArrayLike,
 *   name?: string|null,
 *   color?: string,
 *   width?: number,
 *   opacity?: number,
 *   marker?: boolean,
 *   markerSize?: number,
 *   symbol?: string,
 *   style?: object,
 * }} [opts]
 */
export function composeStem(x, y, opts = {}) {
  const xa = asF64Array(x, "x");
  const ya = asF64Array(y, "y");
  if (xa.length !== ya.length) {
    throw new RangeError("stem x/y length mismatch");
  }
  const n = xa.length;
  let base;
  if (opts.base == null || typeof opts.base === "number") {
    base = new Float64Array(n).fill(Number(opts.base ?? 0));
  } else {
    base = asF64Array(opts.base, "base");
    if (base.length !== n) {
      throw new RangeError(`stem base must have length ${n}, got ${base.length}`);
    }
  }
  const color = opts.color ?? "#3987e5";
  const opacity = opts.opacity ?? 1.0;
  const width = opts.width ?? 1.2;
  const marker = opts.marker !== false;
  const markerSize = opts.markerSize ?? 5.0;
  const traces = [
    {
      kind: "stem",
      name: opts.name ?? null,
      x: xa,
      y: base,
      x0: xa,
      x1: xa,
      y0: base,
      y1: ya,
      style: {
        color,
        width,
        opacity,
        role: "stem",
        ...(opts.style ?? {}),
      },
      count: n,
      x_axis: opts.xAxis ?? "x",
      y_axis: opts.yAxis ?? "y",
      ...(opts.id != null ? { id: opts.id } : {}),
    },
  ];
  if (marker) {
    traces.push({
      kind: "scatter",
      name: null,
      x: xa,
      y: ya,
      style: {
        color,
        opacity,
        size: markerSize,
        symbol: opts.symbol ?? "circle",
        role: "stem-marker",
      },
      x_axis: opts.xAxis ?? "x",
      y_axis: opts.yAxis ?? "y",
    });
  }
  return { traces };
}

/**
 * @param {import("../figure.js").Figure} fig
 * @param {ArrayLike|TypedArray} x
 * @param {ArrayLike|TypedArray} y
 * @param {object} [opts]
 */
export function attachStem(fig, x, y, opts = {}) {
  const { traces } = composeStem(x, y, opts);
  for (const t of traces) {
    if (t.kind === "scatter") {
      fig.scatter(t.x, t.y, { name: t.name, style: t.style, _composed: true });
    } else {
      fig.traces.push({
        id: t.id ?? fig.traces.length,
        ...t,
      });
    }
  }
  return fig;
}
