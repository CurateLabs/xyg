/**
 * Chart convenience constructors — scatter / line / histogram / graph.
 * Thin wrappers over mark composers + the minimal Node Figure.
 */

import { figure } from "./figure.js";
import { attachScatter } from "./marks/scatter.js";
import { attachLine } from "./marks/line.js";
import { attachHistogram } from "./marks/histogram.js";

/**
 * @param {ArrayLike|TypedArray} x
 * @param {ArrayLike|TypedArray} y
 * @param {{width?: number, height?: number, title?: string|null, name?: string|null, style?: object}} [opts]
 */
export function scatterChart(x, y, opts = {}) {
  const { width, height, title, ...markOpts } = opts;
  const fig = figure({ width, height, title });
  attachScatter(fig, x, y, markOpts);
  return fig;
}

/**
 * @param {ArrayLike|TypedArray} x
 * @param {ArrayLike|TypedArray} y
 * @param {object} [opts]
 */
export function lineChart(x, y, opts = {}) {
  const { width, height, title, ...markOpts } = opts;
  const fig = figure({ width, height, title });
  attachLine(fig, x, y, markOpts);
  return fig;
}

/**
 * @param {ArrayLike|TypedArray} values
 * @param {object} [opts]
 */
export function histogramChart(values, opts = {}) {
  const { width, height, title, ...markOpts } = opts;
  const fig = figure({ width, height, title });
  attachHistogram(fig, values, markOpts);
  return fig;
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
