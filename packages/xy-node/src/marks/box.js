/**
 * Box plot mark — Tukey stats via `xy_box_stats`, single-group MVP.
 */

import { asF64Array, boxStats } from "../encode.js";

/**
 * @param {ArrayLike|TypedArray} values
 * @param {{
 *   x?: number,
 *   width?: number,
 *   orientation?: "vertical"|"horizontal",
 *   showOutliers?: boolean,
 *   name?: string|null,
 *   style?: object,
 *   color?: string,
 * }} [opts]
 */
export function composeBox(values, opts = {}) {
  const arr = asF64Array(values, "values");
  const finite = arr.filter((v) => Number.isFinite(v));
  if (finite.length === 0) {
    throw new RangeError("box values must contain at least one finite value");
  }
  const stats = boxStats(Float64Array.from(finite));
  const center = Number(opts.x ?? 0);
  const width = Number(opts.width ?? 0.6);
  const orientation = opts.orientation ?? "vertical";
  const half = width / 2.0;
  const { q1, median, q3, low, high } = stats;
  const color = opts.color ?? "#3987e5";
  const opacity = opts.opacity ?? 0.85;
  const traces = [];
  let wx0;
  let wx1;
  let wy0;
  let wy1;
  let bx0;
  let bx1;
  let by0;
  let by1;
  let mx0;
  let mx1;
  let my0;
  let my1;
  if (orientation === "vertical") {
    bx0 = center - half;
    bx1 = center + half;
    by0 = q1;
    by1 = q3;
    wx0 = [center, center - width * 0.3, center - width * 0.3];
    wx1 = [center, center + width * 0.3, center + width * 0.3];
    wy0 = [low, low, high];
    wy1 = [high, low, high];
    mx0 = center - half;
    mx1 = center + half;
    my0 = median;
    my1 = median;
  } else {
    bx0 = q1;
    bx1 = q3;
    by0 = center - half;
    by1 = center + half;
    wx0 = [low, low, high];
    wx1 = [high, low, high];
    wy0 = [center, center - width * 0.3, center - width * 0.3];
    wy1 = [center, center + width * 0.3, center + width * 0.3];
    mx0 = median;
    mx1 = median;
    my0 = center - half;
    my1 = center + half;
  }
  traces.push({
    kind: "segments",
    name: null,
    x0: Float64Array.from(wx0),
    x1: Float64Array.from(wx1),
    y0: Float64Array.from(wy0),
    y1: Float64Array.from(wy1),
    style: { color, opacity, role: "box-whisker", width: 1.0 },
    x_axis: opts.xAxis ?? "x",
    y_axis: opts.yAxis ?? "y",
  });
  traces.push({
    kind: "bar",
    name: opts.name ?? null,
    x0: Float64Array.from([bx0]),
    x1: Float64Array.from([bx1]),
    y0: Float64Array.from([by0]),
    y1: Float64Array.from([by1]),
    style: { color, opacity, role: "box", box_orientation: orientation },
    count: 1,
    x_axis: opts.xAxis ?? "x",
    y_axis: opts.yAxis ?? "y",
  });
  traces.push({
    kind: "segments",
    name: null,
    x0: Float64Array.from([mx0]),
    x1: Float64Array.from([mx1]),
    y0: Float64Array.from([my0]),
    y1: Float64Array.from([my1]),
    style: { color, opacity, role: "box-median", width: 2.0 },
    x_axis: opts.xAxis ?? "x",
    y_axis: opts.yAxis ?? "y",
  });
  if (opts.showOutliers !== false && stats.outliers.length > 0) {
    const ox = new Float64Array(stats.outliers.length);
    const oy = new Float64Array(stats.outliers.length);
    for (let i = 0; i < stats.outliers.length; i += 1) {
      if (orientation === "vertical") {
        ox[i] = center;
        oy[i] = stats.outliers[i];
      } else {
        ox[i] = stats.outliers[i];
        oy[i] = center;
      }
    }
    traces.push({
      kind: "scatter",
      name: null,
      x: ox,
      y: oy,
      style: { color, opacity: 1.0, role: "box-outlier", size: 4.0 },
      x_axis: opts.xAxis ?? "x",
      y_axis: opts.yAxis ?? "y",
    });
  }
  return { traces, stats };
}

/**
 * @param {import("../figure.js").Figure} fig
 * @param {ArrayLike|TypedArray} values
 * @param {object} [opts]
 */
export function attachBox(fig, values, opts = {}) {
  const { traces } = composeBox(values, opts);
  for (const t of traces) {
    if (t.kind === "segments") {
      fig.segments(t.x0, t.y0, t.x1, t.y1, { name: t.name, style: t.style });
    } else if (t.kind === "bar") {
      fig._pushRectTrace("bar", t, { name: t.name, style: t.style });
    } else if (t.kind === "scatter") {
      fig.scatter(t.x, t.y, { name: t.name, style: t.style, _composed: true });
    }
  }
  return fig;
}
