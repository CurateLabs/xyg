/**
 * Box plot mark — packed Rust-owned grouped geometry, with host-only style packing.
 */

import { boxGeometry, DEFAULT_MARK_COLOR } from "../encode.js";
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
  const boxStyle = opts.style ?? {};
  const whiskerStyle = opts.whiskerStyle ?? opts.whisker_style ?? {};
  const medianStyle = opts.medianStyle ?? opts.median_style ?? {};
  const outlierStyle = opts.outlierStyle ?? opts.outlier_style ?? {};
  const width = Number(opts.width ?? 0.6);
  const orientation = opts.orientation ?? "vertical";
  const color = boxStyle.color ?? opts.color ?? DEFAULT_MARK_COLOR;
  const opacity = boxStyle.opacity ?? opts.opacity ?? 0.85;
  const showOutliers = opts.showOutliers ?? opts.show_outliers ?? true;
  const geometry = boxGeometry(groups, positions, width, orientation, showOutliers);
  const [bx0, by0, bx1, by1] = geometry.body;
  const [wx0, wy0, wx1, wy1] = geometry.whiskers;
  const [mx0, my0, mx1, my1] = geometry.medians;

  const traces = [
    {
      kind: "box_whisker",
      name: null,
      x0: Float64Array.from(wx0),
      x1: Float64Array.from(wx1),
      y0: Float64Array.from(wy0),
      y1: Float64Array.from(wy1),
      style: { color: whiskerStyle.color ?? color, opacity: whiskerStyle.opacity ?? opacity, role: "box-whisker", width: whiskerStyle.width ?? 1.0 },
      x_axis: opts.xAxis ?? "x",
      y_axis: opts.yAxis ?? "y",
    },
    {
      kind: "box",
      name: opts.name ?? null,
      x0: Float64Array.from(bx0),
      x1: Float64Array.from(bx1),
      y0: Float64Array.from(by0),
      y1: Float64Array.from(by1),
      style: { color, opacity, role: "box", box_orientation: orientation, stroke_width: boxStyle.stroke_width ?? 1.0, ...(boxStyle.stroke != null ? { stroke: boxStyle.stroke } : {}) },
      count: bx0.length,
      x_axis: opts.xAxis ?? "x",
      y_axis: opts.yAxis ?? "y",
    },
    {
      kind: "box_median",
      name: null,
      x0: Float64Array.from(mx0),
      x1: Float64Array.from(mx1),
      y0: Float64Array.from(my0),
      y1: Float64Array.from(my1),
      style: { color: medianStyle.color ?? color, opacity: medianStyle.opacity ?? opacity, role: "box-median", width: medianStyle.width ?? 1.4 },
      x_axis: opts.xAxis ?? "x",
      y_axis: opts.yAxis ?? "y",
    },
  ];
  if (showOutliers && geometry.outlierX.length > 0) {
    traces.push({
      kind: "scatter",
      name: null,
      x: geometry.outlierX,
      y: geometry.outlierY,
      style: { color: outlierStyle.color ?? color, opacity: outlierStyle.opacity ?? opacity, role: "box-outlier", size: opts.outlierSize ?? opts.outlier_size ?? 4.0, ...outlierStyle },
      x_axis: opts.xAxis ?? "x",
      y_axis: opts.yAxis ?? "y",
    });
  }
  return {
    traces,
    stats: geometry.groupStats.length === 1 ? geometry.groupStats[0] : geometry.groupStats,
    groupStats: geometry.groupStats,
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
    if (t.kind === "box_whisker" || t.kind === "box_median") {
      fig._pushSegmentTrace(t, { name: t.name, style: t.style });
    } else if (t.kind === "box") {
      fig._pushRectTrace("box", t, { name: t.name, style: t.style });
    } else if (t.kind === "scatter") {
      fig.scatter(t.x, t.y, { name: t.name, style: t.style, xAxis: t.x_axis, yAxis: t.y_axis, _composed: true });
    }
  }
  return fig;
}
