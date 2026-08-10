/**
 * Ribbon mark — flow bands (Sankey / alluvial primitive).
 *
 * Geometry contract matches Python: x0/x1 faces, source_lo/hi + target_lo/hi
 * spans; target spans ride the `x`/`y` slots on the wire as `target_y0`/`target_y1`.
 */

import { asF64Array } from "../encode.js";
import { resolveColorChannel } from "../color.js";

/**
 * @param {ArrayLike|TypedArray} x0
 * @param {ArrayLike|TypedArray} x1
 * @param {ArrayLike|TypedArray} sourceLo
 * @param {ArrayLike|TypedArray} sourceHi
 * @param {ArrayLike|TypedArray} targetLo
 * @param {ArrayLike|TypedArray} targetHi
 * @param {{
 *   color?: string|string[],
 *   colorTarget?: string|string[]|null,
 *   name?: string|null,
 *   opacity?: number,
 *   stroke?: string|null,
 *   strokeWidth?: number,
 *   style?: object,
 * }} [opts]
 */
export function composeRibbon(x0, x1, sourceLo, sourceHi, targetLo, targetHi, opts = {}) {
  const cols = [
    asF64Array(x0, "x0"),
    asF64Array(x1, "x1"),
    asF64Array(sourceLo, "source_lo"),
    asF64Array(sourceHi, "source_hi"),
    asF64Array(targetLo, "target_lo"),
    asF64Array(targetHi, "target_hi"),
  ];
  const n = cols[0].length;
  if (cols.some((c) => c.length !== n)) {
    throw new RangeError("ribbon columns must be the same length");
  }
  const opacity = opts.opacity ?? 1.0;
  if (!(opacity >= 0 && opacity <= 1)) {
    throw new RangeError("ribbon opacity must be in [0, 1]");
  }
  const color = resolveColorChannel(opts.color, n);
  const colorTarget =
    opts.colorTarget == null ? null : resolveColorChannel(opts.colorTarget, n, color.color);
  const style = {
    opacity,
    role: "ribbon",
    ...(opts.stroke != null ? { stroke: opts.stroke } : {}),
    ...(opts.strokeWidth ? { stroke_width: Number(opts.strokeWidth) } : {}),
    ...(opts.style ?? {}),
  };
  return {
    traces: [
      {
        kind: "ribbon",
        name: opts.name ?? null,
        // Target span y values occupy x/y slots (Python ribbon geometry contract).
        x: cols[4],
        y: cols[5],
        x0: cols[0],
        x1: cols[1],
        y0: cols[2],
        y1: cols[3],
        color,
        color_target: colorTarget,
        style,
        count: n,
        x_axis: opts.xAxis ?? "x",
        y_axis: opts.yAxis ?? "y",
        ...(opts.tooltipRows != null ? { tooltip_rows: opts.tooltipRows } : {}),
      },
    ],
  };
}

/**
 * @param {import("../figure.js").Figure} fig
 * @param {ArrayLike|TypedArray} x0
 * @param {ArrayLike|TypedArray} x1
 * @param {ArrayLike|TypedArray} sourceLo
 * @param {ArrayLike|TypedArray} sourceHi
 * @param {ArrayLike|TypedArray} targetLo
 * @param {ArrayLike|TypedArray} targetHi
 * @param {object} [opts]
 */
export function attachRibbon(fig, x0, x1, sourceLo, sourceHi, targetLo, targetHi, opts = {}) {
  fig.ribbon(x0, x1, sourceLo, sourceHi, targetLo, targetHi, opts);
  return fig;
}
