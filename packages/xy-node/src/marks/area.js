/**
 * Area mark — line ingest + optional base; M4 at emit (same path as line).
 */

import { asF64Array, DEFAULT_MARK_COLOR } from "../encode.js";
import { composeLine, prepareLineSeries } from "./line.js";

/**
 * @param {ArrayLike|TypedArray} x
 * @param {ArrayLike|TypedArray} y
 * @param {{
 *   base?: number|ArrayLike|TypedArray,
 *   name?: string|null,
 *   style?: object,
 *   color?: string,
 *   opacity?: number,
 *   lineColor?: string,
 *   lineWidth?: number,
 *   lineOpacity?: number,
 *   strokePerimeter?: boolean,
 * }} [opts]
 */
export function composeArea(x, y, opts = {}) {
  const { x: xa, y: ya } = prepareLineSeries(x, y);
  const n = xa.length;
  let base;
  if (opts.base == null || typeof opts.base === "number") {
    const b = Number(opts.base ?? 0);
    base = new Float64Array(n).fill(b);
  } else {
    base = asF64Array(opts.base, "base");
    if (base.length !== n) {
      throw new RangeError(`area base must have length ${n}, got ${base.length}`);
    }
  }
  const style = {
    color: opts.color ?? DEFAULT_MARK_COLOR,
    opacity: opts.opacity ?? 0.35,
    line_width: opts.lineWidth ?? 1.2,
    line_opacity: opts.lineOpacity ?? 1.0,
    stroke_perimeter: opts.strokePerimeter ?? false,
    ...(opts.style ?? {}),
  };
  if (opts.lineColor != null && !("line_color" in (opts.style ?? {}))) {
    style.line_color = opts.lineColor;
  }
  return {
    traces: [
      {
        kind: "area",
        name: opts.name ?? null,
        x: xa,
        y: ya,
        base,
        style,
        x_axis: opts.xAxis ?? "x",
        y_axis: opts.yAxis ?? "y",
        ...(opts.id != null ? { id: opts.id } : {}),
      },
    ],
  };
}

/**
 * @param {import("../figure.js").Figure} fig
 * @param {ArrayLike|TypedArray} x
 * @param {ArrayLike|TypedArray} y
 * @param {object} [opts]
 */
export function attachArea(fig, x, y, opts = {}) {
  const { traces } = composeArea(x, y, opts);
  const t = traces[0];
  fig.area(t.x, t.y, {
    base: t.base,
    name: t.name,
    style: t.style,
    xAxis: t.x_axis,
    yAxis: t.y_axis,
    id: t.id,
  });
  return fig;
}

/** Re-export line M4 helpers for area parity goldens. */
export { prepareLineSeries, composeLine };
