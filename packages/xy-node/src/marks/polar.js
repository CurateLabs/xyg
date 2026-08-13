/**
 * Polar / pie / wind_rose / facet composers for the Node host.
 *
 * Polar geometry and wind-rose binning live in Rust (`xy_wind_rose_bins`,
 * `xyg_bar_stack`, `xy_sector_triangles`). These helpers assemble marks the same
 * way Python `components.pie_chart` / `wind_rose` / `facet_chart` do, and the
 * Node figure emits a real `coords: "polar"` payload with theta/r axis meta.
 */

import { asF64Array, windRoseBins, DEFAULT_PALETTE } from "../encode.js";
import { composeBar } from "./bar.js";
import { figure } from "../figure.js";

/**
 * Polar chart shell — marks use angle as x and radius as y.
 *
 * Emits `coords: "polar"` plus resolved theta/r axis descriptors on
 * {@link Figure.buildPayload} (Python polar-axes.md defaults).
 *
 * @param {object} [opts]
 */
export function polarChart(opts = {}) {
  const fig = figure({
    width: opts.width,
    height: opts.height,
    title: opts.title,
    coords: "polar",
  });
  const meta = {
    thetaUnit: opts.thetaUnit ?? opts.theta_unit ?? "radians",
    thetaZero: opts.thetaZero ?? opts.theta_zero ?? "E",
    thetaDirection: opts.thetaDirection ?? opts.theta_direction ?? "counterclockwise",
    hole: opts.hole ?? 0.0,
    sector: opts.sector ?? null,
    gridShape: opts.gridShape ?? opts.grid_shape ?? "circular",
  };
  fig.setPolarMeta(meta);
  if (typeof opts.thetaAxis === "function") {
    // no-op hook for API familiarity
  }
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
    hole,
  };
}

/**
 * @param {ArrayLike} labels
 * @param {ArrayLike|TypedArray} values
 * @param {object} [opts]
 */
export function pieChart(labels, values, opts = {}) {
  const { width, height, title, ...pieOpts } = opts;
  const composed = composePie(labels, values, pieOpts);
  const fig = polarChart({
    width,
    height,
    title,
    thetaUnit: composed.thetaUnit,
    thetaZero: composed.thetaZero,
    thetaDirection: composed.thetaDirection,
    hole: composed.hole,
  });
  for (const t of composed.traces) {
    fig._pushRectTrace("bar", t, {});
  }
  // Pie spans the full turn in degrees; pin domains so chrome matches Python.
  fig.setAxisDomain("x", [0, 360]);
  fig.setAxisDomain("y", [0, 1]);
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
    thetaUnit: "degrees",
    thetaZero: "N",
    thetaDirection: "clockwise",
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
  const composed = composeWindRose(directions, speeds, roseOpts);
  const fig = polarChart({
    width,
    height,
    title,
    thetaUnit: composed.thetaUnit,
    thetaZero: composed.thetaZero,
    thetaDirection: composed.thetaDirection,
  });
  for (const t of composed.traces) {
    fig._pushRectTrace("bar", t, {});
  }
  fig._windRose = {
    edges: composed.edges,
    centres: composed.centres,
    nObs: composed.nObs,
    sectors: composed.sectors,
  };
  fig.setAxisDomain("x", [0, 360]);
  return fig;
}

/**
 * Merge shared axis domains across panel figures (Python facet_chart share_x/y).
 *
 * @param {import("../figure.js").Figure[]} panels
 * @param {{shareX?: boolean, shareY?: boolean}} [opts]
 */
export function shareFacetAxes(panels, opts = {}) {
  const shareX = opts.shareX !== false;
  const shareY = opts.shareY !== false;
  if (!Array.isArray(panels) || panels.length === 0) {
    return panels;
  }
  if (shareX) {
    let lo = Number.POSITIVE_INFINITY;
    let hi = Number.NEGATIVE_INFINITY;
    for (const fig of panels) {
      if (fig == null || typeof fig._range !== "function") continue;
      const [a, b] = fig._range("x");
      lo = Math.min(lo, a, b);
      hi = Math.max(hi, a, b);
    }
    if (Number.isFinite(lo) && Number.isFinite(hi)) {
      for (const fig of panels) {
        if (fig != null && typeof fig.setAxisDomain === "function") {
          fig.setAxisDomain("x", [lo, hi]);
        }
      }
    }
  }
  if (shareY) {
    let lo = Number.POSITIVE_INFINITY;
    let hi = Number.NEGATIVE_INFINITY;
    for (const fig of panels) {
      if (fig == null || typeof fig._range !== "function") continue;
      const [a, b] = fig._range("y");
      lo = Math.min(lo, a, b);
      hi = Math.max(hi, a, b);
    }
    if (Number.isFinite(lo) && Number.isFinite(hi)) {
      for (const fig of panels) {
        if (fig != null && typeof fig.setAxisDomain === "function") {
          fig.setAxisDomain("y", [lo, hi]);
        }
      }
    }
  }
  return panels;
}

/**
 * Facet composition with shared-axis domain merging.
 *
 * Full Python `facet_chart` repeats a child composition per `by` value. The
 * Node host:
 *   1. accepts `panels:[figure, ...]` and optionally shares x/y domains, or
 *   2. runs `composePanel(key, index)` once per facet key, then shares axes.
 *
 * @param {{
 *   by?: ArrayLike,
 *   cols?: number,
 *   panels?: object[],
 *   composePanel?: (key: any, index: number) => object,
 *   width?: number,
 *   height?: number,
 *   gap?: number,
 *   shareX?: boolean,
 *   shareY?: boolean,
 *   title?: string|null,
 * }} [opts]
 */
export function facetChart(opts = {}) {
  const cols = opts.cols ?? 3;
  const gap = opts.gap ?? 12;
  const shareX = opts.shareX !== false;
  const shareY = opts.shareY !== false;

  let panels;
  let keys = null;
  if (Array.isArray(opts.panels)) {
    panels = [...opts.panels];
  } else if (typeof opts.composePanel === "function") {
    keys = opts.by == null ? [0] : [...new Set([...opts.by])];
    panels = keys.map((key, index) => opts.composePanel(key, index));
  } else {
    return {
      kind: "facet",
      cols,
      gap,
      shareX,
      shareY,
      panels: [],
      note:
        "Node facet: pass panels:[figure, ...] or composePanel(key) to run child marks.",
    };
  }

  shareFacetAxes(panels, { shareX, shareY });

  const result = {
    kind: "facet",
    cols,
    gap,
    shareX,
    shareY,
    keys,
    panels,
    width: opts.width,
    height: opts.height,
    title: opts.title ?? null,
    /**
     * Build §29 payloads for every panel (shared domains already applied).
     * @param {object} [payloadOpts]
     */
    buildPayloads(payloadOpts = {}) {
      return panels.map((p) =>
        p != null && typeof p.buildPayload === "function"
          ? p.buildPayload(payloadOpts)
          : null,
      );
    },
  };
  return result;
}

/** @deprecated alias documenting the compose-N-figures path */
export function composeFacet(opts = {}) {
  return facetChart(opts);
}
