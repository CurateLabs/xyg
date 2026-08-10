/**
 * Radar (spider) chart — closed polar polygons from category spokes + series.
 */

import { asF64Array, DEFAULT_PALETTE } from "../encode.js";
import { composeArea } from "./area.js";
import { composeLine } from "./line.js";
import { polarChart } from "./polar.js";

/**
 * @param {ArrayLike} categoriesOrAngles string labels or numeric angles (degrees)
 * @param {ArrayLike|TypedArray|ArrayLike[]} seriesValues one series or many
 * @param {{
 *   fill?: boolean,
 *   names?: string[],
 *   colors?: string[],
 *   name?: string|null,
 *   color?: string,
 *   opacity?: number,
 *   width?: number,
 *   style?: object,
 * }} [opts]
 */
export function composeRadar(categoriesOrAngles, seriesValues, opts = {}) {
  const raw = [...categoriesOrAngles];
  if (raw.length < 3) {
    throw new RangeError("radar needs at least 3 categories/angles");
  }
  const count = raw.length;
  const labels = [];
  let angles;
  if (typeof raw[0] === "string") {
    for (let i = 0; i < count; i += 1) labels.push(String(raw[i]));
    const step = 360.0 / count;
    angles = new Float64Array(count);
    for (let i = 0; i < count; i += 1) angles[i] = i * step;
  } else {
    angles = asF64Array(raw, "angles");
    if (angles.length !== count) {
      throw new RangeError("radar angles length mismatch");
    }
  }
  const closedAngles = new Float64Array(count + 1);
  closedAngles.set(angles, 0);
  closedAngles[count] = 360.0;

  const seriesList = normalizeSeries(seriesValues, count);
  const fill = opts.fill !== false;
  const colors = opts.colors ?? DEFAULT_PALETTE;
  const names = opts.names ?? null;
  const traces = [];
  for (let s = 0; s < seriesList.length; s += 1) {
    const values = seriesList[s];
    const closed = new Float64Array(count + 1);
    closed.set(values, 0);
    closed[count] = values[0];
    const color = opts.color ?? colors[s % colors.length];
    const name = names != null ? (names[s] ?? null) : s === 0 ? (opts.name ?? null) : null;
    if (fill) {
      const composed = composeArea(closedAngles, closed, {
        base: 0,
        name,
        color,
        opacity: opts.opacity ?? 0.35,
        style: { role: "radar", ...(opts.style ?? {}) },
        xAxis: opts.xAxis,
        yAxis: opts.yAxis,
      });
      traces.push(...composed.traces);
    } else {
      const composed = composeLine(closedAngles, closed, {
        name,
        color,
        width: opts.width ?? 2.0,
        style: { opacity: opts.opacity ?? 1.0, role: "radar", ...(opts.style ?? {}) },
        xAxis: opts.xAxis,
        yAxis: opts.yAxis,
      });
      traces.push(...composed.traces);
    }
  }
  return {
    traces,
    angles,
    labels: labels.length ? labels : null,
    coords: "polar",
    thetaUnit: "degrees",
  };
}

function normalizeSeries(seriesValues, count) {
  if (
    Array.isArray(seriesValues) &&
    seriesValues.length > 0 &&
    (Array.isArray(seriesValues[0]) || ArrayBuffer.isView(seriesValues[0]))
  ) {
    return seriesValues.map((row, i) => {
      const arr = asF64Array(row, `series[${i}]`);
      if (arr.length !== count) {
        throw new RangeError(
          `radar series[${i}] has ${arr.length} values but there are ${count} categories`,
        );
      }
      return arr;
    });
  }
  const arr = asF64Array(seriesValues, "series");
  if (arr.length !== count) {
    throw new RangeError(`radar series has ${arr.length} values but there are ${count} categories`);
  }
  return [arr];
}

/**
 * @param {import("../figure.js").Figure} fig
 * @param {ArrayLike} categoriesOrAngles
 * @param {ArrayLike|TypedArray|ArrayLike[]} seriesValues
 * @param {object} [opts]
 */
export function attachRadar(fig, categoriesOrAngles, seriesValues, opts = {}) {
  const composed = composeRadar(categoriesOrAngles, seriesValues, opts);
  if (typeof fig.setPolarMeta === "function") {
    fig.setPolarMeta({
      thetaUnit: "degrees",
      thetaZero: opts.thetaZero ?? "E",
      thetaDirection: opts.thetaDirection ?? "counterclockwise",
      hole: opts.hole ?? 0.0,
      sector: opts.sector ?? null,
      gridShape: opts.gridShape ?? "circular",
    });
  }
  if (fig.coords == null) {
    fig.coords = "polar";
  }
  for (const t of composed.traces) {
    if (t.kind === "area") {
      fig.area(t.x, t.y, {
        base: t.base,
        name: t.name,
        style: t.style,
        xAxis: t.x_axis,
        yAxis: t.y_axis,
      });
    } else {
      fig.line(t.x, t.y, {
        name: t.name,
        style: t.style,
        xAxis: t.x_axis,
        yAxis: t.y_axis,
      });
    }
  }
  return fig;
}

/**
 * Convenience: polar figure with closed radar polygons.
 *
 * @param {ArrayLike} categoriesOrAngles
 * @param {ArrayLike|TypedArray|ArrayLike[]} seriesValues
 * @param {object} [opts]
 */
export function radarChart(categoriesOrAngles, seriesValues, opts = {}) {
  const fig = polarChart({
    width: opts.width,
    height: opts.height,
    title: opts.title,
    thetaUnit: "degrees",
    thetaZero: opts.thetaZero,
    thetaDirection: opts.thetaDirection,
    hole: opts.hole,
    sector: opts.sector,
    gridShape: opts.gridShape,
  });
  return attachRadar(fig, categoriesOrAngles, seriesValues, opts);
}
