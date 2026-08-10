/**
 * Chart convenience constructors — all dual-host mark families.
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
import { attachContour } from "./marks/contour.js";
import { attachErrorbar } from "./marks/errorbar.js";
import { attachErrorBand } from "./marks/error_band.js";
import { attachStem } from "./marks/stem.js";
import { attachStep, attachStairs } from "./marks/step.js";
import { attachTriangleMesh } from "./marks/triangle_mesh.js";
import { attachRadar } from "./marks/radar.js";
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
 * @param {ArrayLike|TypedArray|number[][]} z
 * @param {object} [opts]
 */
export function contourChart(z, opts = {}) {
  return chartWith(opts, attachContour, z);
}

/**
 * @param {ArrayLike|TypedArray} x
 * @param {ArrayLike|TypedArray} y
 * @param {object} [opts]
 */
export function errorbarChart(x, y, opts = {}) {
  return chartWith(opts, attachErrorbar, x, y);
}

/**
 * @param {ArrayLike|TypedArray} x
 * @param {ArrayLike|TypedArray} lower
 * @param {ArrayLike|TypedArray} upper
 * @param {object} [opts]
 */
export function errorBandChart(x, lower, upper, opts = {}) {
  return chartWith(opts, attachErrorBand, x, lower, upper);
}

/**
 * @param {ArrayLike|TypedArray} x
 * @param {ArrayLike|TypedArray} y
 * @param {object} [opts]
 */
export function stemChart(x, y, opts = {}) {
  return chartWith(opts, attachStem, x, y);
}

/**
 * @param {ArrayLike|TypedArray} x
 * @param {ArrayLike|TypedArray} y
 * @param {object} [opts]
 */
export function stepChart(x, y, opts = {}) {
  return chartWith(opts, attachStep, x, y);
}

/**
 * @param {ArrayLike|TypedArray} edges
 * @param {ArrayLike|TypedArray} values
 * @param {object} [opts]
 */
export function stairsChart(edges, values, opts = {}) {
  return chartWith(opts, attachStairs, edges, values);
}

/**
 * @param {ArrayLike|TypedArray} x0
 * @param {ArrayLike|TypedArray} y0
 * @param {ArrayLike|TypedArray} x1
 * @param {ArrayLike|TypedArray} y1
 * @param {ArrayLike|TypedArray} x2
 * @param {ArrayLike|TypedArray} y2
 * @param {object} [opts]
 */
export function triangleMeshChart(x0, y0, x1, y1, x2, y2, opts = {}) {
  return chartWith(opts, attachTriangleMesh, x0, y0, x1, y1, x2, y2);
}

/**
 * @param {ArrayLike|TypedArray} categoriesOrAngles
 * @param {ArrayLike|TypedArray|ArrayLike[]} seriesValues
 * @param {object} [opts]
 */
export function radarChart(categoriesOrAngles, seriesValues, opts = {}) {
  return chartWith(opts, attachRadar, categoriesOrAngles, seriesValues);
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

/**
 * @param {Iterable|object} nodes
 * @param {Iterable|object} links
 * @param {object} [opts]
 */
export function sankeyChart(nodes, links, opts = {}) {
  const { width, height, title, ...sankeyOpts } = opts;
  const fig = figure({ width, height, title });
  fig.sankey(nodes, links, sankeyOpts);
  return fig;
}

export { pieChart, windRoseChart, polarChart, facetChart };
