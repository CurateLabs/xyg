/**
 * Box plot mark — Tukey stats via `xy_box_stats`, multi-group parity with Python.
 */

import { boxStats } from "../encode.js";
import { distributionGroups } from "./distribution.js";

/**
 * @param {ArrayLike|TypedArray|ArrayLike[]} values
 * @param {{
 *   x?: ArrayLike|number|null,
 *   group?: ArrayLike|null,
 *   width?: number,
 *   orientation?: "vertical"|"horizontal",
 *   showOutliers?: boolean,
 *   name?: string|null,
 *   style?: object,
 *   color?: string,
 *   opacity?: number,
 * }} [opts]
 */
export function composeBox(values, opts = {}) {
  const { groups, positions } = distributionGroups(values, {
    x: opts.x,
    group: opts.group,
    kind: "box",
  });
  if (groups.length !== positions.length) {
    throw new RangeError("box groups and positions must have equal length");
  }
  const width = Number(opts.width ?? 0.6);
  const orientation = opts.orientation ?? "vertical";
  const color = opts.color ?? "#3987e5";
  const opacity = opts.opacity ?? 0.85;
  const half = width / 2.0;

  const statsList = groups.map((g) => {
    const finite = g.filter((v) => Number.isFinite(v));
    if (finite.length === 0) {
      return null;
    }
    return boxStats(Float64Array.from(finite));
  });
  const finiteStats = statsList.filter((s) => s != null);
  if (finiteStats.length === 0) {
    throw new RangeError("box values must contain at least one finite group");
  }

  const bx0 = [];
  const bx1 = [];
  const by0 = [];
  const by1 = [];
  const wx0 = [];
  const wx1 = [];
  const wy0 = [];
  const wy1 = [];
  const mx0 = [];
  const mx1 = [];
  const my0 = [];
  const my1 = [];
  const ox = [];
  const oy = [];

  for (let i = 0; i < statsList.length; i += 1) {
    const stats = statsList[i];
    if (stats == null) continue;
    const center = positions[i];
    const { q1, median, q3, low, high } = stats;
    if (orientation === "vertical") {
      bx0.push(center - half);
      bx1.push(center + half);
      by0.push(q1);
      by1.push(q3);
      wx0.push(center, center - width * 0.3, center - width * 0.3);
      wx1.push(center, center + width * 0.3, center + width * 0.3);
      wy0.push(low, low, high);
      wy1.push(high, low, high);
      mx0.push(center - half);
      mx1.push(center + half);
      my0.push(median);
      my1.push(median);
      for (const o of stats.outliers) {
        ox.push(center);
        oy.push(o);
      }
    } else {
      bx0.push(q1);
      bx1.push(q3);
      by0.push(center - half);
      by1.push(center + half);
      wx0.push(low, low, high);
      wx1.push(high, low, high);
      wy0.push(center, center - width * 0.3, center - width * 0.3);
      wy1.push(center, center + width * 0.3, center + width * 0.3);
      mx0.push(median);
      mx1.push(median);
      my0.push(center - half);
      my1.push(center + half);
      for (const o of stats.outliers) {
        ox.push(o);
        oy.push(center);
      }
    }
  }

  const traces = [
    {
      kind: "segments",
      name: null,
      x0: Float64Array.from(wx0),
      x1: Float64Array.from(wx1),
      y0: Float64Array.from(wy0),
      y1: Float64Array.from(wy1),
      style: { color, opacity, role: "box-whisker", width: 1.0 },
      x_axis: opts.xAxis ?? "x",
      y_axis: opts.yAxis ?? "y",
    },
    {
      kind: "bar",
      name: opts.name ?? null,
      x0: Float64Array.from(bx0),
      x1: Float64Array.from(bx1),
      y0: Float64Array.from(by0),
      y1: Float64Array.from(by1),
      style: { color, opacity, role: "box", box_orientation: orientation },
      count: bx0.length,
      x_axis: opts.xAxis ?? "x",
      y_axis: opts.yAxis ?? "y",
    },
    {
      kind: "segments",
      name: null,
      x0: Float64Array.from(mx0),
      x1: Float64Array.from(mx1),
      y0: Float64Array.from(my0),
      y1: Float64Array.from(my1),
      style: { color, opacity, role: "box-median", width: 2.0 },
      x_axis: opts.xAxis ?? "x",
      y_axis: opts.yAxis ?? "y",
    },
  ];
  if (opts.showOutliers !== false && ox.length > 0) {
    traces.push({
      kind: "scatter",
      name: null,
      x: Float64Array.from(ox),
      y: Float64Array.from(oy),
      style: { color, opacity: 1.0, role: "box-outlier", size: 4.0 },
      x_axis: opts.xAxis ?? "x",
      y_axis: opts.yAxis ?? "y",
    });
  }
  return {
    traces,
    stats: finiteStats.length === 1 ? finiteStats[0] : finiteStats,
    groupStats: finiteStats,
    positions,
    groups: groups.length,
  };
}

/**
 * @param {import("../figure.js").Figure} fig
 * @param {ArrayLike|TypedArray|ArrayLike[]} values
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
