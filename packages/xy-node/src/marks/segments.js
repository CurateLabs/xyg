/**
 * Segments mark — independent line segments (x0,y0)→(x1,y1).
 */

import { asF64Array, DEFAULT_MARK_COLOR } from "../encode.js";
import { resolveColorChannel } from "../color.js";

/**
 * @param {ArrayLike|TypedArray} x0
 * @param {ArrayLike|TypedArray} y0
 * @param {ArrayLike|TypedArray} x1
 * @param {ArrayLike|TypedArray} y1
 * @param {{name?: string|null, style?: object, color?: string, width?: number}} [opts]
 */
export function composeSegments(x0, y0, x1, y1, opts = {}) {
  const xa0 = asF64Array(x0, "x0");
  const ya0 = asF64Array(y0, "y0");
  const xa1 = asF64Array(x1, "x1");
  const ya1 = asF64Array(y1, "y1");
  const n = xa0.length;
  if (ya0.length !== n || xa1.length !== n || ya1.length !== n) {
    throw new RangeError("segments coordinate columns must have equal length");
  }
  const color = resolveColorChannel(opts.color ?? opts.style?.color ?? DEFAULT_MARK_COLOR, n);
  const style = {
    color: color.mode === "constant" ? color.constant : opts.color ?? DEFAULT_MARK_COLOR,
    width: opts.width ?? 1.2,
    opacity: opts.opacity ?? 1.0,
    role: "segments",
    ...(opts.style ?? {}),
  };
  return {
    traces: [
      {
        kind: "segments",
        name: opts.name ?? null,
        x0: xa0,
        y0: ya0,
        x1: xa1,
        y1: ya1,
        ...(color.mode !== "constant" ? { color_ch: color } : {}),
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
 * @param {ArrayLike|TypedArray} x0
 * @param {ArrayLike|TypedArray} y0
 * @param {ArrayLike|TypedArray} x1
 * @param {ArrayLike|TypedArray} y1
 * @param {object} [opts]
 */
export function attachSegments(fig, x0, y0, x1, y1, opts = {}) {
  const { traces } = composeSegments(x0, y0, x1, y1, opts);
  const t = traces[0];
  fig.segments(t.x0, t.y0, t.x1, t.y1, {
    name: t.name,
    style: t.style,
    xAxis: t.x_axis,
    yAxis: t.y_axis,
    id: t.id,
  });
  return fig;
}
