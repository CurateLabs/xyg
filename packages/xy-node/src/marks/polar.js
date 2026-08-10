/**
 * Thin polar / pie / wind_rose / facet composers for the Node host.
 *
 * Polar geometry and wind-rose binning live in Rust (`xy_wind_rose_bins`,
 * `xy_bar_stack`, `xy_sector_triangles`). These helpers only assemble marks
 * the same way Python `components.pie_chart` / `wind_rose` do.
 */

import { asF64Array, windRoseBins, DEFAULT_PALETTE } from "../encode.js";
import { composeBar } from "./bar.js";
import { figure } from "../figure.js";

/**
 * Polar chart shell — marks use angle as x and radius as y.
 * The Node figure MVP does not yet emit a full polar payload; this documents
 * `coords: "polar"` on the returned figure for host consumers.
 *
 * @param {object} [opts]
 */
export function polarChart(opts = {}) {
  const fig = figure({
    width: opts.width,
    height: opts.height,
    title: opts.title,
  });
  fig.coords = "polar";
  return fig;
}

/**
 * Pie / donut as unequal-width polar bars (value → angular span).
 *
 * @param {ArrayLike} labels
 * @param {ArrayLike|TypedArray} values
 * @param {{
 *   hole?: number,
 *   pad?: number,
 *   colors?: string[],
 *   width?: number,
 *   height?: number,
 *   title?: string|null,
 * }} [opts]
 */
export function composePie(labels, values, opts = {}) {
  const names = [...labels].map(String);
  const amounts = asF64Array(values, "values");
  if (names.length !== amounts.length) {
    throw new RangeError("pie labels/values length mismatch");
  }
  if (names.length === 0) {
    throw new RangeError("pie needs at least one slice");
  }
  let total = 0;
  for (const v of amounts) {
    if (!Number.isFinite(v) || v < 0) {
      throw new RangeError("pie values must be finite and non-negative");
    }
    total += v;
  }
  if (!(total > 0)) {
    throw new RangeError("pie values must sum to a positive total");
  }
  const hole = opts.hole ?? 0.55;
  if (!(hole >= 0 && hole < 1)) {
    throw new RangeError("pie hole must be in [0, 1)");
  }
  const colors = opts.colors ?? DEFAULT_PALETTE;
  const traces = [];
  let cursor = 0;
  for (let i = 0; i < amounts.length; i += 1) {
    const span = (amounts[i] / total) * 360.0;
    if (span <= 0) continue;
    const composed = composeBar(
      [cursor + span / 2.0],
      [1.0 - hole],
      {
        base: hole,
        width: span,
        kind: "bar",
        name: names[i],
        color: colors[i % colors.length],
        orientation: "vertical",
        style: {
          role: "bar",
          wedge_gap: opts.pad ?? 4.0,
          corner_radius: opts.cornerRadius ?? 6.0,
        },
      },
    );
    traces.push(...composed.traces);
    cursor += span;
  }
  return {
    traces,
    coords: "polar",
    thetaUnit: "degrees",
    thetaZero: "N",
    thetaDirection: "clockwise",
  };
}

/**
 * @param {ArrayLike} labels
 * @param {ArrayLike|TypedArray} values
 * @param {object} [opts]
 */
export function pieChart(labels, values, opts = {}) {
  const { width, height, title, ...pieOpts } = opts;
  const fig = polarChart({ width, height, title });
  const composed = composePie(labels, values, pieOpts);
  for (const t of composed.traces) {
    fig._pushRectTrace("bar", t, {});
  }
  fig._polarMeta = {
    thetaUnit: composed.thetaUnit,
    thetaZero: composed.thetaZero,
    thetaDirection: composed.thetaDirection,
  };
  return fig;
}

/**
 * Wind rose: `xy_wind_rose_bins` + stacked polar bars.
 *
 * @param {ArrayLike|TypedArray} directions degrees (0 = N, clockwise)
 * @param {ArrayLike|TypedArray} speeds
 * @param {{
 *   sectors?: number,
 *   speedBins?: ArrayLike|null,
 *   width?: number,
 *   height?: number,
 *   title?: string|null,
 * }} [opts]
 */
export function composeWindRose(directions, speeds, opts = {}) {
  const sectors = opts.sectors ?? 16;
  const binned = windRoseBins(directions, speeds, sectors, opts.speedBins ?? null);
  const width = 360.0 / sectors;
  const centres = binned.centres;
  const nBands = binned.edges.length;
  const traces = [];
  const base = new Float64Array(sectors);
  for (let band = 0; band < nBands; band += 1) {
    const bandCounts = binned.counts.subarray(band * sectors, (band + 1) * sectors);
    const heights = new Float64Array(bandCounts);
    const composed = composeBar(centres, heights, {
      base: new Float64Array(base),
      width,
      mode: "grouped",
      kind: "bar",
      name: `≤ ${binned.edges[band]}`,
      color: DEFAULT_PALETTE[band % DEFAULT_PALETTE.length],
      orientation: "vertical",
    });
    traces.push(...composed.traces);
    for (let i = 0; i < sectors; i += 1) {
      base[i] += heights[i];
    }
  }
  return {
    traces,
    coords: "polar",
    edges: binned.edges,
    centres,
    counts: binned.counts,
    nObs: binned.nObs,
    sectors,
  };
}

/**
 * @param {ArrayLike|TypedArray} directions
 * @param {ArrayLike|TypedArray} speeds
 * @param {object} [opts]
 */
export function windRoseChart(directions, speeds, opts = {}) {
  const { width, height, title, ...roseOpts } = opts;
  const fig = polarChart({ width, height, title });
  const composed = composeWindRose(directions, speeds, roseOpts);
  for (const t of composed.traces) {
    fig._pushRectTrace("bar", t, {});
  }
  fig._polarMeta = { thetaUnit: "degrees", thetaZero: "N", thetaDirection: "clockwise" };
  fig._windRose = {
    edges: composed.edges,
    centres: composed.centres,
    nObs: composed.nObs,
    sectors: composed.sectors,
  };
  return fig;
}

/**
 * Minimal facet stub.
 *
 * Full Python `facet_chart` repeats a child composition per `by` value with
 * shared axes. The Node MVP either:
 *   1. documents "compose N figures" via {@link facetChart} when `panels` is
 *      an array of already-built figures, or
 *   2. runs a `composePanel(key, values)` callback once per facet key.
 *
 * @param {{
 *   by?: ArrayLike,
 *   cols?: number,
 *   panels?: object[],
 *   composePanel?: (key: any, index: number) => object,
 *   width?: number,
 *   height?: number,
 *   gap?: number,
 * }} [opts]
 */
export function facetChart(opts = {}) {
  const cols = opts.cols ?? 3;
  const gap = opts.gap ?? 12;
  if (Array.isArray(opts.panels)) {
    return {
      kind: "facet",
      cols,
      gap,
      panels: opts.panels,
      note: "compose N figures — attach each panel's buildPayload() independently",
    };
  }
  if (typeof opts.composePanel === "function") {
    const keys = opts.by == null ? [0] : [...new Set([...opts.by])];
    const panels = keys.map((key, index) => opts.composePanel(key, index));
    return {
      kind: "facet",
      cols,
      gap,
      keys,
      panels,
      width: opts.width,
      height: opts.height,
    };
  }
  return {
    kind: "facet",
    cols,
    gap,
    panels: [],
    note:
      "Node facet is a thin stub: pass panels:[figure, ...] or composePanel(key) " +
      "to run child marks. Full shared-axis FacetChart remains Python-side.",
  };
}

/** @deprecated alias documenting the compose-N-figures path */
export function composeFacet(opts = {}) {
  return facetChart(opts);
}
