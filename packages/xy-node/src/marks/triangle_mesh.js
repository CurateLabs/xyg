/**
 * Triangle mesh — independently colored filled triangles (six equal columns).
 */

import { asF64Array } from "../encode.js";

/**
 * @param {ArrayLike|TypedArray} x0
 * @param {ArrayLike|TypedArray} y0
 * @param {ArrayLike|TypedArray} x1
 * @param {ArrayLike|TypedArray} y1
 * @param {ArrayLike|TypedArray} x2
 * @param {ArrayLike|TypedArray} y2
 * @param {{
 *   name?: string|null,
 *   color?: string,
 *   opacity?: number,
 *   stroke?: string|null,
 *   strokeWidth?: number,
 *   style?: object,
 * }} [opts]
 */
export function composeTriangleMesh(x0, y0, x1, y1, x2, y2, opts = {}) {
  const cols = [
    asF64Array(x0, "x0"),
    asF64Array(y0, "y0"),
    asF64Array(x1, "x1"),
    asF64Array(y1, "y1"),
    asF64Array(x2, "x2"),
    asF64Array(y2, "y2"),
  ];
  const n = cols[0].length;
  if (cols.some((c) => c.length !== n)) {
    throw new RangeError("triangle_mesh coordinate columns must have equal length");
  }
  const opacity = opts.opacity ?? 1.0;
  if (!(opacity >= 0 && opacity <= 1)) {
    throw new RangeError("triangle_mesh opacity must be in [0, 1]");
  }
  let strokeWidth = opts.strokeWidth ?? 0.0;
  if (opts.stroke != null && !strokeWidth) {
    strokeWidth = 1.0;
  }
  const style = {
    opacity,
    role: "triangle-mesh",
    ...(opts.color != null ? { color: opts.color } : {}),
    ...(opts.stroke != null ? { stroke: opts.stroke } : {}),
    ...(strokeWidth ? { stroke_width: Number(strokeWidth) } : {}),
    ...(opts.style ?? {}),
  };
  return {
    traces: [
      {
        kind: "triangle_mesh",
        name: opts.name ?? null,
        // Third vertex occupies x/y slots (Python triangle_mesh geometry).
        x: cols[4],
        y: cols[5],
        x0: cols[0],
        y0: cols[1],
        x1: cols[2],
        y1: cols[3],
        style,
        count: n,
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
 * @param {ArrayLike|TypedArray} x2
 * @param {ArrayLike|TypedArray} y2
 * @param {object} [opts]
 */
export function attachTriangleMesh(fig, x0, y0, x1, y1, x2, y2, opts = {}) {
  const { traces } = composeTriangleMesh(x0, y0, x1, y1, x2, y2, opts);
  const t = traces[0];
  fig.traces.push({
    id: t.id ?? fig.traces.length,
    ...t,
  });
  return fig;
}
