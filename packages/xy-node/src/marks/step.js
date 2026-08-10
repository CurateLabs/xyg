/**
 * Step / stairs marks — ship as `line` + `style.step` (browser draws steps).
 */

import { asF64Array } from "../encode.js";
import { prepareLineSeries } from "./line.js";

/**
 * @param {ArrayLike|TypedArray} x
 * @param {ArrayLike|TypedArray} y
 * @param {{
 *   where?: "pre"|"mid"|"post",
 *   name?: string|null,
 *   color?: string,
 *   width?: number,
 *   opacity?: number,
 *   dash?: string|number[]|null,
 *   style?: object,
 * }} [opts]
 */
export function composeStep(x, y, opts = {}) {
  const where = opts.where ?? "post";
  if (where !== "pre" && where !== "mid" && where !== "post") {
    throw new RangeError("step where must be 'pre', 'post', or 'mid'");
  }
  const { x: xa, y: ya } = prepareLineSeries(x, y);
  const style = {
    color: opts.color ?? "#3987e5",
    width: opts.width ?? 1.5,
    opacity: opts.opacity ?? 1.0,
    step: where,
    role: "step",
    ...(opts.dash != null ? { dash: opts.dash } : {}),
    ...(opts.style ?? {}),
  };
  return {
    traces: [
      {
        kind: "line",
        name: opts.name ?? null,
        x: xa,
        y: ya,
        style,
        x_axis: opts.xAxis ?? "x",
        y_axis: opts.yAxis ?? "y",
        ...(opts.id != null ? { id: opts.id } : {}),
      },
    ],
  };
}

/**
 * Matplotlib-style stairs: k values + k+1 edges → compact step series.
 *
 * @param {ArrayLike|TypedArray} edges
 * @param {ArrayLike|TypedArray} values
 * @param {{
 *   where?: "pre"|"mid"|"post",
 *   baseline?: number,
 *   name?: string|null,
 *   color?: string,
 *   width?: number,
 *   opacity?: number,
 *   style?: object,
 * }} [opts]
 */
export function composeStairs(edges, values, opts = {}) {
  const where = opts.where ?? "post";
  if (where !== "pre" && where !== "mid" && where !== "post") {
    throw new RangeError("stairs where must be 'pre', 'post', or 'mid'");
  }
  const vals = asF64Array(values, "values");
  if (vals.length === 0) {
    throw new RangeError("stairs values must contain at least one value");
  }
  const edgeValues = asF64Array(edges, "edges");
  if (edgeValues.length !== vals.length + 1) {
    throw new RangeError(
      `stairs edges must have length ${vals.length + 1}, got ${edgeValues.length}`,
    );
  }
  for (let i = 0; i < edgeValues.length; i += 1) {
    if (!Number.isFinite(edgeValues[i])) {
      throw new RangeError("stairs edges must be finite and strictly increasing");
    }
    if (i > 0 && !(edgeValues[i] > edgeValues[i - 1])) {
      throw new RangeError("stairs edges must be finite and strictly increasing");
    }
  }
  // Step expansion holds each y from its riser onward: "pre" repeats the first
  // value; "post"/"mid" repeat the last (Python marks.stairs).
  const sy = new Float64Array(vals.length + 1);
  if (where === "pre") {
    sy[0] = vals[0];
    for (let i = 0; i < vals.length; i += 1) sy[i + 1] = vals[i];
  } else {
    for (let i = 0; i < vals.length; i += 1) sy[i] = vals[i];
    sy[vals.length] = vals[vals.length - 1];
  }
  // baseline is accepted for API familiarity with filled stairs; the wire
  // path is the step line (browser expands style.step).
  void opts.baseline;
  return composeStep(edgeValues, sy, {
    where,
    name: opts.name,
    color: opts.color,
    width: opts.width,
    opacity: opts.opacity,
    dash: opts.dash,
    style: { role: "stairs", ...(opts.style ?? {}) },
    xAxis: opts.xAxis,
    yAxis: opts.yAxis,
    id: opts.id,
  });
}

/**
 * @param {import("../figure.js").Figure} fig
 * @param {ArrayLike|TypedArray} x
 * @param {ArrayLike|TypedArray} y
 * @param {object} [opts]
 */
export function attachStep(fig, x, y, opts = {}) {
  const { traces } = composeStep(x, y, opts);
  const t = traces[0];
  fig.line(t.x, t.y, {
    name: t.name,
    style: t.style,
    xAxis: t.x_axis,
    yAxis: t.y_axis,
    id: t.id,
  });
  return fig;
}

/**
 * @param {import("../figure.js").Figure} fig
 * @param {ArrayLike|TypedArray} edges
 * @param {ArrayLike|TypedArray} values
 * @param {object} [opts]
 */
export function attachStairs(fig, edges, values, opts = {}) {
  const { traces } = composeStairs(edges, values, opts);
  const t = traces[0];
  fig.line(t.x, t.y, {
    name: t.name,
    style: t.style,
    xAxis: t.x_axis,
    yAxis: t.y_axis,
    id: t.id,
  });
  return fig;
}
