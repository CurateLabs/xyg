/**
 * Chart convenience constructors — scatter / line / histogram / graph + batch-2 marks.
 * Thin wrappers over mark composers + the minimal Node Figure.
 */

import { figure } from "./figure.js";
import { attachScatter } from "./marks/scatter.js";
import { attachLine } from "./marks/line.js";
import { attachHistogram } from "./marks/histogram.js";
import { attachArea } from "./marks/area.js";
import { attachBar, attachColumn } from "./marks/bar.js";
import { attachBox } from "./marks/box.js";
import { attachEcdf } from "./marks/ecdf.js";
import { attachSegments } from "./marks/segments.js";
import { attachHeatmap } from "./marks/heatmap.js";
import { attachHexbin } from "./marks/hexbin.js";
import { attachViolin } from "./marks/violin.js";
import {
  pieChart,
  windRoseChart,
  polarChart,
  facetChart,
} from "./marks/polar.js";

function chartWith(figOpts, attachFn, ...args) {
  const { width, height, title, ...markOpts } = figOpts;
  const fig = figure({ width, height, title });
  attachFn(fig, ...args, markOpts);
  return fig;
}

/**
 * @param {ArrayLike|TypedArray} x
 * @param {ArrayLike|TypedArray} y
 * @param {{width?: number, height?: number, title?: string|null, name?: string|null, style?: object}} [opts]
 */
export function scatterChart(x, y, opts = {}) {
  return chartWith(opts, attachScatter, x, y);
}

/**
 * @param {ArrayLike|TypedArray} x
 * @param {ArrayLike|TypedArray} y
 * @param {object} [opts]
 */
export function lineChart(x, y, opts = {}) {
  return chartWith(opts, attachLine, x, y);
}

/**
 * @param {ArrayLike|TypedArray} values
 * @param {object} [opts]
 */
export function histogramChart(values, opts = {}) {
  return chartWith(opts, attachHistogram, values);
}

/**
 * @param {ArrayLike|TypedArray} x
 * @param {ArrayLike|TypedArray} y
 * @param {object} [opts]
 */
export function areaChart(x, y, opts = {}) {
  return chartWith(opts, attachArea, x, y);
}

/**
 * @param {ArrayLike|TypedArray} x
 * @param {ArrayLike|TypedArray} y
 * @param {object} [opts]
 */
export function barChart(x, y, opts = {}) {
  return chartWith(opts, attachBar, x, y);
}

/** Column charts share the bar rect renderer. */
export function columnChart(x, y, opts = {}) {
  return chartWith(opts, attachColumn, x, y);
}

/**
 * @param {ArrayLike|TypedArray} values
 * @param {object} [opts]
 */
export function boxChart(values, opts = {}) {
  return chartWith(opts, attachBox, values);
}

/**
 * @param {ArrayLike|TypedArray} values
 * @param {object} [opts]
 */
export function ecdfChart(values, opts = {}) {
  return chartWith(opts, attachEcdf, values);
}

/**
 * @param {ArrayLike|TypedArray} x0
 * @param {ArrayLike|TypedArray} y0
 * @param {ArrayLike|TypedArray} x1
 * @param {ArrayLike|TypedArray} y1
 * @param {object} [opts]
 */
export function segmentsChart(x0, y0, x1, y1, opts = {}) {
  return chartWith(opts, attachSegments, x0, y0, x1, y1);
}

/**
 * @param {ArrayLike|TypedArray|number[][]} z
 * @param {object} [opts]
 */
export function heatmapChart(z, opts = {}) {
  return chartWith(opts, attachHeatmap, z);
}

/**
 * @param {ArrayLike|TypedArray} x
 * @param {ArrayLike|TypedArray} y
 * @param {object} [opts]
 */
export function hexbinChart(x, y, opts = {}) {
  return chartWith(opts, attachHexbin, x, y);
}

/**
 * @param {ArrayLike|TypedArray} values
 * @param {object} [opts]
 */
export function violinChart(values, opts = {}) {
  return chartWith(opts, attachViolin, values);
}

/**
 * @param {Iterable|object} nodes
 * @param {Iterable|object} edges
 * @param {object} [opts]
 */
export function graphChart(nodes, edges, opts = {}) {
  const { width, height, title, ...graphOpts } = opts;
  const fig = figure({ width, height, title });
  fig.graph(nodes, edges, graphOpts);
  return fig;
}

export { pieChart, windRoseChart, polarChart, facetChart };
