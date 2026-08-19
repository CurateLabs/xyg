/**
 * Minimal Node figure — holds scatter/line/histogram/segments traces and builds
 * a §29-ish payload subset (PROTOCOL_VERSION matches Python).
 *
 * Documented subset vs full Python `Figure.build_payload`:
 * - Emits `protocol`, width/height, axes ranges, traces, columns, graph meta.
 * - Geometry columns are offset-encoded f32 via `xyg_encode_f32` (§29).
 * - Line traces apply Rust M4 when over DECIMATION_THRESHOLD (§28).
 * - Histogram traces ship as rectangle columns from `xyg_histogram_uniform`.
 * - Polar charts emit `coords: "polar"` + theta/r axis descriptors.
 * - Ribbon / sankey ship flow-band geometry (`target_y0`/`target_y1`).
 * - Scatter uses density tier when n ≥ SCATTER_DENSITY_THRESHOLD (Rust bin_2d).
 * - At/above PYRAMID_MIN_POINTS, density prefers Tier-3 pyramid compose (§28).
 * - Contour / errorbar / stem / mesh / step / stairs / error_band / radar covered.
 * - Enough for mark encode / M4 / hist + graph layout goldens across hosts.
 */

import {
  Column,
  DECIMATION_THRESHOLD,
  DENSITY_GRID,
  PROTOCOL_VERSION,
  PYRAMID_MIN_POINTS,
  bin2d,
  densityLogU8,
  encodeF32Values,
  geometryOffset,
  m4Points,
  minMax,
  pinsOffsetToZero,
  shouldUseDensity,
} from "./encode.js";
import {
  PyramidCache,
  densityViewFromPyramid,
  pyramidAppendFromStream,
  shouldUsePyramid,
} from "./pyramid.js";
import { composeGraph } from "./graph.js";
import { composeSankey } from "./sankey.js";
import { composeScatter } from "./marks/scatter.js";
import { composeLine, F64_EPS } from "./marks/line.js";
import { composeHistogram } from "./marks/histogram.js";
import { composeArea } from "./marks/area.js";
import { composeBar } from "./marks/bar.js";
import { composeBox } from "./marks/box.js";
import { composeEcdf } from "./marks/ecdf.js";
import { composeSegments } from "./marks/segments.js";
import { composeHeatmap } from "./marks/heatmap.js";
import { composeHexbin } from "./marks/hexbin.js";
import { composeViolin } from "./marks/violin.js";
import { composeRibbon } from "./marks/ribbon.js";
import { composeContour } from "./marks/contour.js";
import { composeErrorbar } from "./marks/errorbar.js";
import { composeErrorBand } from "./marks/error_band.js";
import { composeStem } from "./marks/stem.js";
import { composeStep, composeStairs } from "./marks/step.js";
import { composeTriangleMesh } from "./marks/triangle_mesh.js";
import { composeRadar } from "./marks/radar.js";
import { toHtml } from "./html.js";
import { figureSceneV3, sceneRasterCommands, sceneSvg } from "./scene.js";

export { PROTOCOL_VERSION };

let nextTraceId = 1;

function asF64(value) {
  if (value instanceof Float64Array) return value;
  if (value == null) return new Float64Array(0);
  return Float64Array.from(value, Number);
}

function finiteBounds(arr) {
  const mm = minMax(arr);
  return mm == null ? [0.0, 0.0] : mm;
}

export class PayloadWriter {
  constructor({ split = false } = {}) {
    this.split = split;
    this.columns = [];
    this._chunks = [];
    this._pos = 0;
  }

  shipValues(values, { kind = "float", scale = null } = {}) {
    const vals = asF64(values);
    const [lo, hi] = finiteBounds(vals);
    const offset = pinsOffsetToZero(scale) ? geometryOffset(scale, lo, hi) : (lo + hi) / 2.0;
    const { values: encoded, meta } = encodeF32Values(vals, offset, lo, hi, { kind });
    return this._append(encoded, meta);
  }

  ship(values, column, { scale = null } = {}) {
    const vals = asF64(values);
    const col = column instanceof Column ? column : new Column(vals);
    const [lo, hi] = col.bounds();
    const offset = pinsOffsetToZero(scale)
      ? geometryOffset(scale, lo, hi)
      : col.suggestOffset();
    const { values: encoded, meta } = encodeF32Values(vals, offset, lo, hi, {
      kind: col.kind,
    });
    return this._append(encoded, meta);
  }

  /**
   * Raw u8 column (RGBA8 / categorical codes), 4-byte padded like Python.
   * @param {Uint8Array|ArrayLike} values
   */
  shipU8(values) {
    const enc =
      values instanceof Uint8Array ? values : Uint8Array.from(values, (v) => Number(v) & 0xff);
    const idx = this.columns.length;
    if (this.split) {
      const padding = (-enc.length) % 4;
      const padded =
        padding === 0 ? enc : (() => {
          const out = new Uint8Array(enc.length + padding);
          out.set(enc);
          return out;
        })();
      this.columns.push({
        buf: this._chunks.length,
        byte_offset: 0,
        len: enc.length,
        dtype: "u8",
      });
      this._chunks.push(padded);
      this._pos += padded.byteLength;
      return idx;
    }
    this.columns.push({ byte_offset: this._pos, len: enc.length, dtype: "u8" });
    this._chunks.push(enc);
    this._pos += enc.byteLength;
    const padding = (-this._pos) % 4;
    if (padding) {
      this._chunks.push(new Uint8Array(padding));
      this._pos += padding;
    }
    return idx;
  }

  _append(enc, meta) {
    const idx = this.columns.length;
    if (this.split) {
      this.columns.push({
        buf: this._chunks.length,
        byte_offset: 0,
        len: enc.length,
        ...meta,
      });
    } else {
      this.columns.push({ byte_offset: this._pos, len: enc.length, ...meta });
    }
    this._chunks.push(enc);
    this._pos += enc.byteLength;
    return idx;
  }

  blob() {
    return Buffer.concat(this._chunks.map((c) => Buffer.from(c.buffer, c.byteOffset, c.byteLength)));
  }

  buffers() {
    return this._chunks.map((c) => c);
  }
}

export class Figure {
  constructor(opts = {}) {
    this.width = opts.width ?? 640;
    this.height = opts.height ?? 400;
    this.title = opts.title ?? null;
    this.coords = opts.coords ?? "cartesian";
    this.traces = [];
    this._graphMeta = null;
    this._axisRange = { x: null, y: null };
    this._polarMeta = null;
    /** @type {Map<number|string, PyramidCache>} */
    this._pyramids = new Map();
    this._appendSeq = 0;
  }

  /**
   * @param {{
   *   thetaUnit?: string,
   *   thetaZero?: string|number,
   *   thetaDirection?: string,
   *   hole?: number,
   *   sector?: [number, number]|null,
   *   gridShape?: string,
   * }} meta
   */
  setPolarMeta(meta = {}) {
    this.coords = "polar";
    this._polarMeta = {
      thetaUnit: meta.thetaUnit ?? "radians",
      thetaZero: meta.thetaZero ?? "E",
      thetaDirection: meta.thetaDirection ?? "counterclockwise",
      hole: meta.hole ?? 0.0,
      sector: meta.sector ?? null,
      gridShape: meta.gridShape ?? "circular",
      ...(meta ?? {}),
    };
    return this;
  }

  /** Pin an axis domain (used by facet shared-axis + polar pie domains). */
  setAxisDomain(axisId, range) {
    const [a, b] = range;
    this._axisRange[axisId] = [Math.min(a, b), Math.max(a, b)];
    return this;
  }

  scatter(x, y, opts = {}) {
    const forceDensity = opts.forceDensity ?? opts.force_density;
    const forceDirect = opts.forceDirect ?? opts.force_direct;
    const forcePyramid = opts.forcePyramid ?? opts.force_pyramid;
    if (opts._composed) {
      this.traces.push({
        id: opts.id ?? nextTraceId++,
        kind: "scatter",
        name: opts.name ?? null,
        x: asF64(x),
        y: asF64(y),
        style: { ...(opts.style ?? {}) },
        x_axis: opts.xAxis ?? "x",
        y_axis: opts.yAxis ?? "y",
        ...(forceDensity != null ? { force_density: Boolean(forceDensity) } : {}),
        ...(forceDirect != null ? { force_direct: Boolean(forceDirect) } : {}),
        ...(forcePyramid != null ? { force_pyramid: Boolean(forcePyramid) } : {}),
      });
      return this;
    }
    const composed = composeScatter(x, y, opts);
    const t = composed.traces[0];
    const fd = forceDensity ?? t.force_density;
    const fx = forceDirect ?? t.force_direct;
    const fp = forcePyramid ?? t.force_pyramid;
    this.traces.push({
      id: opts.id ?? nextTraceId++,
      kind: "scatter",
      name: t.name,
      x: t.x,
      y: t.y,
      style: { ...t.style },
      x_axis: t.x_axis,
      y_axis: t.y_axis,
      ...(fd != null ? { force_density: Boolean(fd) } : {}),
      ...(fx != null ? { force_direct: Boolean(fx) } : {}),
      ...(fp != null ? { force_pyramid: Boolean(fp) } : {}),
    });
    return this;
  }

  line(x, y, opts = {}) {
    const composed = composeLine(x, y, opts);
    const t = composed.traces[0];
    this.traces.push({
      id: opts.id ?? nextTraceId++,
      kind: "line",
      name: t.name,
      x: t.x,
      y: t.y,
      style: { ...t.style },
      x_axis: t.x_axis,
      y_axis: t.y_axis,
    });
    return this;
  }

  histogram(values, opts = {}) {
    const composed = composeHistogram(values, opts);
    const t = composed.traces[0];
    this.traces.push({
      id: opts.id ?? nextTraceId++,
      kind: "histogram",
      name: t.name,
      x0: t.x0,
      x1: t.x1,
      y0: t.y0,
      y1: t.y1,
      style: { ...t.style },
      count: t.count,
      x_axis: t.x_axis,
      y_axis: t.y_axis,
    });
    return this;
  }

  area(x, y, opts = {}) {
    const composed = composeArea(x, y, opts);
    const t = composed.traces[0];
    this.traces.push({
      id: opts.id ?? nextTraceId++,
      kind: "area",
      name: t.name,
      x: t.x,
      y: t.y,
      base: t.base,
      style: { ...t.style },
      x_axis: t.x_axis,
      y_axis: t.y_axis,
    });
    return this;
  }

  bar(x, y, opts = {}) {
    const composed = composeBar(x, y, opts);
    for (const t of composed.traces) {
      this._pushRectTrace(t.kind ?? "bar", t, opts);
    }
    return this;
  }

  _pushRectTrace(kind, t, opts = {}) {
    this.traces.push({
      id: opts.id ?? nextTraceId++,
      kind,
      name: t.name ?? opts.name ?? null,
      x0: t.x0,
      x1: t.x1,
      y0: t.y0,
      y1: t.y1,
      style: { ...(t.style ?? opts.style ?? {}) },
      count: t.count,
      edges: t.edges,
      density: t.density,
      x_axis: t.x_axis ?? opts.xAxis ?? "x",
      y_axis: t.y_axis ?? opts.yAxis ?? "y",
    });
  }

  box(values, opts = {}) {
    const composed = composeBox(values, opts);
    for (const t of composed.traces) {
      if (t.kind === "segments") {
        this.segments(t.x0, t.y0, t.x1, t.y1, { name: t.name, style: t.style });
      } else if (t.kind === "bar") {
        this._pushRectTrace("bar", t, { name: t.name, style: t.style });
      } else if (t.kind === "scatter") {
        this.scatter(t.x, t.y, { name: t.name, style: t.style, _composed: true });
      }
    }
    return this;
  }

  ecdf(values, opts = {}) {
    const composed = composeEcdf(values, opts);
    const t = composed.traces[0];
    // Browser paints ecdf as line + style.step (Python parity).
    this.traces.push({
      id: opts.id ?? t.id ?? nextTraceId++,
      kind: "line",
      name: t.name,
      x: t.x,
      y: t.y,
      style: { ...t.style },
      mode: t.mode,
      x_axis: t.x_axis,
      y_axis: t.y_axis,
    });
    return this;
  }

  contour(z, opts = {}) {
    const composed = composeContour(z, opts);
    for (const t of composed.traces) {
      this._pushSegmentTrace(t);
    }
    return this;
  }

  errorbar(x, y, opts = {}) {
    const composed = composeErrorbar(x, y, opts);
    for (const t of composed.traces) {
      this._pushSegmentTrace(t);
    }
    return this;
  }

  errorBand(x, lower, upper, opts = {}) {
    const composed = composeErrorBand(x, lower, upper, opts);
    const t = composed.traces[0];
    this.traces.push({
      id: opts.id ?? nextTraceId++,
      kind: "error_band",
      name: t.name,
      x: t.x,
      y: t.y,
      base: t.base,
      style: { ...t.style },
      x_axis: t.x_axis,
      y_axis: t.y_axis,
    });
    return this;
  }

  stem(x, y, opts = {}) {
    const composed = composeStem(x, y, opts);
    for (const t of composed.traces) {
      if (t.kind === "scatter") {
        this.scatter(t.x, t.y, { name: t.name, style: t.style, _composed: true });
      } else {
        this._pushSegmentTrace(t);
      }
    }
    return this;
  }

  step(x, y, opts = {}) {
    const composed = composeStep(x, y, opts);
    const t = composed.traces[0];
    this.traces.push({
      id: opts.id ?? nextTraceId++,
      kind: "line",
      name: t.name,
      x: t.x,
      y: t.y,
      style: { ...t.style },
      x_axis: t.x_axis,
      y_axis: t.y_axis,
    });
    return this;
  }

  stairs(edges, values, opts = {}) {
    const composed = composeStairs(edges, values, opts);
    const t = composed.traces[0];
    this.traces.push({
      id: opts.id ?? nextTraceId++,
      kind: "line",
      name: t.name,
      x: t.x,
      y: t.y,
      style: { ...t.style },
      x_axis: t.x_axis,
      y_axis: t.y_axis,
    });
    return this;
  }

  triangleMesh(x0, y0, x1, y1, x2, y2, opts = {}) {
    const composed = composeTriangleMesh(x0, y0, x1, y1, x2, y2, opts);
    const t = composed.traces[0];
    this.traces.push({
      id: opts.id ?? nextTraceId++,
      ...t,
    });
    return this;
  }

  radar(categoriesOrAngles, seriesValues, opts = {}) {
    const composed = composeRadar(categoriesOrAngles, seriesValues, opts);
    if (composed.coords === "polar") {
      this.setPolarMeta({
        thetaUnit: composed.thetaUnit ?? "degrees",
        thetaZero: composed.thetaZero ?? "N",
        thetaDirection: composed.thetaDirection ?? "clockwise",
      });
    }
    for (const t of composed.traces) {
      if (t.kind === "area") {
        this.traces.push({
          id: nextTraceId++,
          kind: "area",
          name: t.name,
          x: t.x,
          y: t.y,
          base: t.base,
          style: { ...t.style },
          x_axis: t.x_axis ?? "x",
          y_axis: t.y_axis ?? "y",
        });
      } else if (t.kind === "line") {
        this.traces.push({
          id: nextTraceId++,
          kind: "line",
          name: t.name,
          x: t.x,
          y: t.y,
          style: { ...t.style },
          x_axis: t.x_axis ?? "x",
          y_axis: t.y_axis ?? "y",
        });
      }
    }
    return this;
  }

  _pushSegmentTrace(t, opts = {}) {
    this.traces.push({
      id: opts.id ?? nextTraceId++,
      kind: t.kind ?? "segments",
      name: t.name ?? null,
      x0: t.x0,
      y0: t.y0,
      x1: t.x1,
      y1: t.y1,
      style: { ...(t.style ?? {}) },
      count: t.count,
      x_axis: t.x_axis ?? "x",
      y_axis: t.y_axis ?? "y",
    });
  }

  heatmap(z, opts = {}) {
    const composed = composeHeatmap(z, opts);
    const t = composed.traces[0];
    this.traces.push({
      id: opts.id ?? nextTraceId++,
      kind: "heatmap",
      name: t.name,
      x: t.x,
      y: t.y,
      grid: t.grid,
      grid_shape: t.grid_shape,
      rgba: t.rgba,
      style: { ...t.style },
      count: t.count,
      x_axis: t.x_axis,
      y_axis: t.y_axis,
    });
    return this;
  }

  hexbin(x, y, opts = {}) {
    const composed = composeHexbin(x, y, opts);
    const t = composed.traces[0];
    this.traces.push({
      id: opts.id ?? nextTraceId++,
      kind: "hexbin",
      name: t.name,
      x: t.x,
      y: t.y,
      metric: t.metric,
      counts: t.counts,
      style: { ...t.style },
      n_points: t.n_points,
      x_axis: t.x_axis,
      y_axis: t.y_axis,
    });
    return this;
  }

  violin(values, opts = {}) {
    const composed = composeViolin(values, opts);
    const t = composed.traces[0];
    this._pushRectTrace("violin", t, opts);
    return this;
  }

  segments(x0, y0, x1, y1, opts = {}) {
    this.traces.push({
      id: opts.id ?? nextTraceId++,
      kind: "segments",
      name: opts.name ?? null,
      x0: asF64(x0),
      y0: asF64(y0),
      x1: asF64(x1),
      y1: asF64(y1),
      style: { ...(opts.style ?? {}) },
      x_axis: opts.xAxis ?? "x",
      y_axis: opts.yAxis ?? "y",
    });
    return this;
  }

  /**
   * Compose a graph mark (normalize → layout → render-graph → traces + meta).
   */
  graph(nodes, edges, opts = {}) {
    const composed = composeGraph(nodes, edges, opts);
    for (const t of composed.traces) {
      if (t.kind === "segments") {
        this.segments(t.x0, t.y0, t.x1, t.y1, { name: t.name, style: t.style });
      } else if (t.kind === "scatter") {
        this.scatter(t.x, t.y, { name: t.name, style: t.style, _composed: true });
      }
    }
    const meta = {
      ...composed.graphMeta,
      node_trace: this.traces.length - 1,
      edge_trace: this.traces.length - 2,
    };
    if (this._graphMeta == null) {
      this._graphMeta = [meta];
    } else {
      this._graphMeta.push(meta);
    }
    return this;
  }

  /**
   * Compose a sankey mark as ribbon bands (Python parity).
   */
  sankey(nodes, links, opts = {}) {
    const composed = composeSankey(nodes, links, opts);
    for (const t of composed.traces) {
      if (t.kind === "ribbon") {
        this.traces.push({
          id: nextTraceId++,
          ...t,
        });
      } else if (t.kind === "segments") {
        this.segments(t.x0, t.y0, t.x1, t.y1, { name: t.name, style: t.style });
      } else if (t.kind === "scatter") {
        this.scatter(t.x, t.y, { name: t.name, style: t.style, _composed: true });
      }
    }
    return this;
  }

  /**
   * Flow band primitive (Sankey / alluvial).
   */
  ribbon(x0, x1, sourceLo, sourceHi, targetLo, targetHi, opts = {}) {
    const composed = composeRibbon(x0, x1, sourceLo, sourceHi, targetLo, targetHi, opts);
    const t = composed.traces[0];
    this.traces.push({
      id: opts.id ?? nextTraceId++,
      ...t,
    });
    return this;
  }

  _range(axisId) {
    if (this._axisRange[axisId] != null) {
      return this._axisRange[axisId];
    }
    let lo = Number.POSITIVE_INFINITY;
    let hi = Number.NEGATIVE_INFINITY;
    for (const t of this.traces) {
      let cols;
      if (t.kind === "ribbon") {
        // x: faces; y: all four span edges (incl. target y in x/y slots).
        cols =
          axisId === "x" || axisId === (t.x_axis ?? "x")
            ? [t.x0, t.x1]
            : [t.y0, t.y1, t.x, t.y];
      } else if (t.kind === "triangle_mesh") {
        cols =
          axisId === "x" || axisId === (t.x_axis ?? "x")
            ? [t.x0, t.x1, t.x]
            : [t.y0, t.y1, t.y];
      } else if (
        t.kind === "segments" ||
        t.kind === "histogram" ||
        t.kind === "bar" ||
        t.kind === "violin" ||
        t.kind === "contour" ||
        t.kind === "errorbar" ||
        t.kind === "stem" ||
        t.kind === "box_whisker" ||
        t.kind === "box_median"
      ) {
        cols =
          axisId === "x" || axisId === (t.x_axis ?? "x") ? [t.x0, t.x1] : [t.y0, t.y1];
      } else if (t.kind === "area" || t.kind === "error_band") {
        cols =
          axisId === "x" || axisId === (t.x_axis ?? "x")
            ? [t.x]
            : [t.y, t.base];
      } else {
        cols = axisId === "x" || axisId === (t.x_axis ?? "x") ? [t.x] : [t.y];
      }
      for (const col of cols) {
        if (col == null) continue;
        const mm = minMax(col);
        if (mm == null) continue;
        lo = Math.min(lo, mm[0]);
        hi = Math.max(hi, mm[1]);
      }
    }
    if (!Number.isFinite(lo) || !Number.isFinite(hi)) {
      lo = 0;
      hi = 1;
    }
    if (lo === hi) {
      hi = lo + 1;
    }
    const pad = (hi - lo) * 0.05;
    const range = [lo - pad, hi + pad];
    this._axisRange[axisId] = range;
    return range;
  }

  _emitScatter(t, pw, xr, yr) {
    const forceDensity = Boolean(t.force_density ?? t.style?.force_density);
    const forceDirect = Boolean(t.force_direct ?? t.style?.force_direct);
    const forcePyramid = Boolean(t.force_pyramid ?? t.style?.force_pyramid);
    if (
      shouldUseDensity(t.x.length, {
        forceDensity: forceDensity || forcePyramid,
        forceDirect,
        coords: this.coords,
      })
    ) {
      return this._emitScatterDensity(t, pw, xr, yr);
    }
    const xCol = t._xCol instanceof Column ? t._xCol : new Column(t.x);
    const yCol = t._yCol instanceof Column ? t._yCol : new Column(t.y);
    t._xCol = xCol;
    t._yCol = yCol;
    return {
      id: t.id,
      kind: "scatter",
      name: t.name,
      style: { ...t.style },
      tier: "direct",
      n_points: t.x.length,
      n_marks: t.x.length,
      x: pw.ship(t.x, xCol),
      y: pw.ship(t.y, yCol),
      x_axis: t.x_axis ?? "x",
      y_axis: t.y_axis ?? "y",
    };
  }

  /**
   * Tier-2/3 density scatter — `bin_2d` below pyramid floor; Tier-3 pyramid
   * compose at/above `PYRAMID_MIN_POINTS` (§28 `binning: pyramid-L*`).
   */
  _emitScatterDensity(t, pw, xr, yr) {
    const [w, h] = DENSITY_GRID;
    let grid;
    let binning = "exact";
    let reduction = "bin2d";
    const forceBin2d = Boolean(t.force_bin2d ?? t.style?.force_bin2d);
    const forcePyramid = Boolean(t.force_pyramid ?? t.style?.force_pyramid);
    const noRescan = Boolean(t.no_rescan ?? t.style?.no_rescan);
    if (
      this.coords !== "polar" &&
      !this._deferPyramidRebuild?.has(t.id) &&
      shouldUsePyramid(t.x.length, { forcePyramid, forceBin2d })
    ) {
      let cache = this._pyramids.get(t.id);
      if (cache == null) {
        cache = new PyramidCache();
        this._pyramids.set(t.id, cache);
      }
      const served = densityViewFromPyramid(cache, t.x, t.y, xr[0], xr[1], yr[0], yr[1], w, h, {
        force: forcePyramid,
        noRescan,
      });
      if (served != null) {
        grid = served.grid;
        binning = served.binning;
        reduction = served.reduction;
      }
    }
    if (grid == null) {
      grid = bin2d(t.x, t.y, xr[0], xr[1], yr[0], yr[1], w, h);
      binning = "exact";
      reduction = "bin2d";
    }
    const { encoded, max } = densityLogU8(grid);
    const density = {
      buf: pw.shipU8(encoded),
      w,
      h,
      max,
      enc: "log-u8",
      colormap: t.style?.colormap ?? "viridis",
      x_range: [...xr],
      y_range: [...yr],
      binning,
      reduction,
      channels_dropped: false,
      dropped_channels: [],
      overlay_omitted: "node_host_mvp",
    };
    if (t.style?.color) {
      density.color = t.style.color;
    }
    return {
      id: t.id,
      kind: "scatter",
      name: t.name,
      style: { ...t.style },
      tier: "density",
      n_points: t.x.length,
      n_marks: w * h,
      visible: t.x.length,
      x_axis: t.x_axis ?? "x",
      y_axis: t.y_axis ?? "y",
      density,
    };
  }

  /** Release all Tier-3 pyramid handles owned by this figure. */
  dispose() {
    for (const cache of this._pyramids.values()) {
      cache.free();
    }
    this._pyramids.clear();
  }

  _emitLine(t, pw, xr, pxWidth) {
    let xv = t.x;
    let yv = t.y;
    let tier = "direct";
    const decimated = xv.length > DECIMATION_THRESHOLD;
    if (decimated) {
      const [outX, outY] = m4Points(xv, yv, xr[0], xr[1] + F64_EPS, pxWidth);
      xv = outX;
      yv = outY;
      tier = "decimated";
    }
    const xCol = !decimated && t._xCol instanceof Column ? t._xCol : new Column(xv);
    const yCol = !decimated && t._yCol instanceof Column ? t._yCol : new Column(yv);
    if (!decimated) {
      t._xCol = xCol;
      t._yCol = yCol;
    }
    const entry = {
      id: t.id,
      kind: "line",
      name: t.name,
      style: { ...t.style },
      tier,
      n_points: t.x.length,
      n_marks: xv.length,
      x: pw.ship(xv, xCol),
      y: pw.ship(yv, yCol),
      x_axis: t.x_axis ?? "x",
      y_axis: t.y_axis ?? "y",
    };
    if (tier === "decimated") {
      entry.decimation_px = pxWidth;
    }
    return entry;
  }

  _emitHistogram(t, pw) {
    const x0 = new Column(t.x0);
    const x1 = new Column(t.x1);
    const y0 = new Column(t.y0);
    const y1 = new Column(t.y1);
    return {
      id: t.id,
      kind: "histogram",
      name: t.name,
      style: { ...t.style },
      tier: "direct",
      n_points: t.count ?? t.x0.length,
      n_marks: t.x0.length,
      x0: pw.ship(t.x0, x0),
      x1: pw.ship(t.x1, x1),
      y0: pw.ship(t.y0, y0),
      y1: pw.ship(t.y1, y1),
      x_axis: t.x_axis ?? "x",
      y_axis: t.y_axis ?? "y",
    };
  }

  _emitSegments(t, pw) {
    const x0 = new Column(t.x0);
    const x1 = new Column(t.x1);
    const y0 = new Column(t.y0);
    const y1 = new Column(t.y1);
    return {
      id: t.id,
      kind: t.kind ?? "segments",
      name: t.name,
      style: { ...t.style },
      tier: "direct",
      n_points: t.count ?? t.x0.length,
      n_marks: t.x0.length,
      x0: pw.ship(t.x0, x0),
      x1: pw.ship(t.x1, x1),
      y0: pw.ship(t.y0, y0),
      y1: pw.ship(t.y1, y1),
      x_axis: t.x_axis ?? "x",
      y_axis: t.y_axis ?? "y",
    };
  }

  _emitTriangleMesh(t, pw) {
    const x0 = new Column(t.x0);
    const y0 = new Column(t.y0);
    const x1 = new Column(t.x1);
    const y1 = new Column(t.y1);
    const x2 = new Column(t.x);
    const y2 = new Column(t.y);
    return {
      id: t.id,
      kind: "triangle_mesh",
      name: t.name,
      style: { ...t.style },
      tier: "direct",
      n_points: t.count ?? t.x0.length,
      n_marks: t.x0.length,
      x0: pw.ship(t.x0, x0),
      y0: pw.ship(t.y0, y0),
      x1: pw.ship(t.x1, x1),
      y1: pw.ship(t.y1, y1),
      x: pw.ship(t.x, x2),
      y: pw.ship(t.y, y2),
      x_axis: t.x_axis ?? "x",
      y_axis: t.y_axis ?? "y",
    };
  }

  _emitRect(t, pw, kind) {
    const x0 = new Column(t.x0);
    const x1 = new Column(t.x1);
    const y0 = new Column(t.y0);
    const y1 = new Column(t.y1);
    return {
      id: t.id,
      kind,
      name: t.name,
      style: { ...t.style },
      tier: "direct",
      n_points: t.count ?? t.x0.length,
      n_marks: t.x0.length,
      x0: pw.ship(t.x0, x0),
      x1: pw.ship(t.x1, x1),
      y0: pw.ship(t.y0, y0),
      y1: pw.ship(t.y1, y1),
      x_axis: t.x_axis ?? "x",
      y_axis: t.y_axis ?? "y",
    };
  }

  _emitArea(t, pw, xr, pxWidth) {
    const line = this._emitLine(
      { ...t, kind: "line" },
      pw,
      xr,
      pxWidth,
    );
    const baseCol = new Column(t.base);
    return {
      ...line,
      kind: t.kind === "error_band" ? "error_band" : "area",
      base: pw.ship(t.base, baseCol),
    };
  }

  _emitHeatmap(t, pw) {
    const xCol = new Column(t.x);
    const yCol = new Column(t.y);
    const gridCol = new Column(t.grid);
    const entry = {
      id: t.id,
      kind: "heatmap",
      name: t.name,
      style: { ...t.style },
      tier: "direct",
      n_points: t.count ?? t.grid.length,
      n_marks: t.grid.length,
      x: pw.ship(t.x, xCol),
      y: pw.ship(t.y, yCol),
      grid: pw.ship(t.grid, gridCol),
      grid_shape: t.grid_shape,
      x_axis: t.x_axis ?? "x",
      y_axis: t.y_axis ?? "y",
    };
    if (t.rgba != null) {
      entry.rgba_len = t.rgba.rgba.length;
    }
    return entry;
  }

  _emitHexbin(t, pw) {
    const xCol = new Column(t.x);
    const yCol = new Column(t.y);
    const mCol = new Column(t.metric);
    return {
      id: t.id,
      kind: "hexbin",
      name: t.name,
      style: { ...t.style },
      tier: "direct",
      n_points: t.n_points ?? t.x.length,
      n_marks: t.x.length,
      x: pw.ship(t.x, xCol),
      y: pw.ship(t.y, yCol),
      metric: pw.ship(t.metric, mCol),
      x_axis: t.x_axis ?? "x",
      y_axis: t.y_axis ?? "y",
    };
  }

  _shipColor(channel, pw) {
    if (channel == null) return undefined;
    if (channel.mode === "direct_rgba" && channel.rgba != null) {
      return {
        mode: "direct_rgba",
        buf: pw.shipU8(channel.rgba),
        n: Math.floor(channel.rgba.length / 4),
      };
    }
    if (channel.mode === "constant") {
      return { mode: "constant", color: channel.color };
    }
    return { ...channel };
  }

  _emitRibbon(t, pw) {
    const x0 = new Column(t.x0);
    const x1 = new Column(t.x1);
    const y0 = new Column(t.y0);
    const y1 = new Column(t.y1);
    const t0 = new Column(t.x);
    const t1 = new Column(t.y);
    const entry = {
      id: t.id,
      kind: "ribbon",
      name: t.name,
      style: { ...t.style },
      tier: "direct",
      n_points: t.count ?? t.x0.length,
      n_marks: t.x0.length,
      x0: pw.ship(t.x0, x0),
      x1: pw.ship(t.x1, x1),
      y0: pw.ship(t.y0, y0),
      y1: pw.ship(t.y1, y1),
      // Target span y values on the y scale (Python ribbon contract).
      target_y0: pw.ship(t.x, t0),
      target_y1: pw.ship(t.y, t1),
      x_axis: t.x_axis ?? "x",
      y_axis: t.y_axis ?? "y",
    };
    const color = this._shipColor(t.color, pw);
    if (color != null) entry.color = color;
    const colorTarget = this._shipColor(t.color_target, pw);
    if (colorTarget != null) entry.color_target = colorTarget;
    if (t.tooltip_rows != null) entry.tooltip_rows = t.tooltip_rows;
    return entry;
  }

  _polarAxisSpecs(xr, yr) {
    const meta = this._polarMeta ?? {
      thetaUnit: "radians",
      thetaZero: "E",
      thetaDirection: "counterclockwise",
      hole: 0.0,
      sector: null,
      gridShape: "circular",
    };
    const unit = meta.thetaUnit ?? "radians";
    const turn = unit === "degrees" ? 360.0 : 2.0 * Math.PI;
    const sector = meta.sector != null ? [...meta.sector] : [0.0, turn];
    return {
      x: {
        range: xr,
        scale: "linear",
        theta_unit: unit,
        theta_zero: meta.thetaZero ?? "E",
        theta_direction: meta.thetaDirection ?? "counterclockwise",
        sector,
        grid_shape: meta.gridShape ?? "circular",
      },
      y: {
        range: yr,
        scale: "linear",
        hole: meta.hole ?? 0.0,
      },
    };
  }

  /**
   * Streaming append for scatter/line traces. Canonical growth lives in
   * `xyg_stream_*`; the trace TypedArrays are snapshots for encode.
   */
  append(traceId, x, y) {
    const t = this.traces.find((tr) => tr.id === traceId);
    if (t == null) {
      throw new RangeError(`unknown trace id ${traceId}`);
    }
    if (t.kind !== "scatter" && t.kind !== "line") {
      throw new RangeError(`append supports scatter/line traces, not ${t.kind}`);
    }
    const ax = asF64(x);
    const ay = asF64(y);
    if (ax.length !== ay.length) {
      throw new RangeError(`appended x and y must have equal length, got ${ax.length} and ${ay.length}`);
    }
    if (ax.length === 0) {
      throw new RangeError("append needs at least one row");
    }
    if (t.kind === "line") {
      for (let i = 0; i < ax.length; i += 1) {
        if (!Number.isFinite(ax[i])) {
          throw new RangeError("line append requires finite x values");
        }
        if (i > 0 && ax[i] < ax[i - 1]) {
          throw new RangeError("line append requires ascending x");
        }
      }
      const prev = t.x.length === 0 ? Number.NaN : t.x[t.x.length - 1];
      if (Number.isFinite(prev) && ax[0] < prev) {
        throw new RangeError(
          `line append must continue the series: new x starts at ${ax[0]}, before the current last x ${prev}`,
        );
      }
    }
    const xCol = t._xCol instanceof Column ? t._xCol : new Column(t.x);
    const yCol = t._yCol instanceof Column ? t._yCol : new Column(t.y);
    xCol.append(ax);
    yCol.append(ay);
    t._xCol = xCol;
    t._yCol = yCol;
    t.x = xCol.values;
    t.y = yCol.values;

    let pyramidUpdate = "none";
    const cache = this._pyramids.get(t.id);
    if (t.kind === "scatter" && cache?.handle) {
      const applied = pyramidAppendFromStream(
        cache.handle,
        xCol._stream,
        yCol._stream,
        ax.length,
      );
      if (applied) {
        pyramidUpdate = "dirty-tiles";
      } else {
        cache.free();
        this._pyramids.delete(t.id);
        pyramidUpdate = "invalidate";
      }
    }

    this._appendSeq += 1;
    if (pyramidUpdate === "invalidate") {
      this._deferPyramidRebuild = new Set([t.id]);
    }
    try {
      const { spec, buffers } = this.buildPayload({ split: true });
      spec.append = { seq: this._appendSeq, affected: [t.id], pyramid: pyramidUpdate };
      return { spec, buffers, type: "append", affected: [t.id] };
    } finally {
      this._deferPyramidRebuild = null;
    }
  }

  /**
   * @returns {{spec: object, buffers: Buffer|Float32Array[]}}
   */
  buildPayload({ split = false, pxWidth = null } = {}) {
    const pw = new PayloadWriter({ split });
    const xr = this._range("x");
    const yr = this._range("y");
    const widthPx = pxWidth ?? Math.max(16, Math.floor(this.width));
    const specTraces = [];
    for (const t of this.traces) {
      if (t.kind === "scatter") {
        specTraces.push(this._emitScatter(t, pw, xr, yr));
      } else if (t.kind === "line") {
        specTraces.push(this._emitLine(t, pw, xr, widthPx));
      } else if (t.kind === "histogram") {
        specTraces.push(this._emitHistogram(t, pw));
      } else if (
        t.kind === "segments" ||
        t.kind === "contour" ||
        t.kind === "errorbar" ||
        t.kind === "stem" ||
        t.kind === "box_whisker" ||
        t.kind === "box_median"
      ) {
        specTraces.push(this._emitSegments(t, pw));
      } else if (t.kind === "area" || t.kind === "error_band") {
        specTraces.push(this._emitArea(t, pw, xr, widthPx));
      } else if (t.kind === "bar" || t.kind === "violin") {
        specTraces.push(this._emitRect(t, pw, t.kind));
      } else if (t.kind === "heatmap") {
        specTraces.push(this._emitHeatmap(t, pw));
      } else if (t.kind === "hexbin") {
        specTraces.push(this._emitHexbin(t, pw));
      } else if (t.kind === "ribbon") {
        specTraces.push(this._emitRibbon(t, pw));
      } else if (t.kind === "triangle_mesh") {
        specTraces.push(this._emitTriangleMesh(t, pw));
      } else {
        throw new Error(`unsupported trace kind ${t.kind} in Node figure MVP`);
      }
    }
    const axisSpecs =
      this.coords === "polar" ? this._polarAxisSpecs(xr, yr) : {
        x: { range: xr, scale: "linear" },
        y: { range: yr, scale: "linear" },
      };
    const spec = {
      protocol: PROTOCOL_VERSION,
      width: this.width,
      height: this.height,
      title: this.title,
      x_axis: axisSpecs.x,
      y_axis: axisSpecs.y,
      axes: axisSpecs,
      traces: specTraces,
      columns: pw.columns,
      backend: "native",
      view: { ranges: { x: [...xr], y: [...yr] } },
    };
    if (this.coords === "polar") {
      spec.coords = "polar";
    }
    if (split) {
      spec.buffer_layout = "split";
    }
    if (this._graphMeta) {
      spec.graph = this._graphMeta;
    }
    return {
      spec,
      buffers: split ? pw.buffers() : pw.blob(),
    };
  }

  /**
   * Self-contained HTML document inlining the host-neutral `@curatelabs/xyg`
   * standalone client. See {@link toHtml}.
   */
  toHtml(path = null, opts = {}) {
    return toHtml(this, path, opts);
  }

  /** Canonical Rust-owned Scene v3 for the supported scatter/line/bar subset. */
  toScene(opts = {}) {
    return figureSceneV3(this, opts);
  }

  /** Whole-scene SVG rendered from the canonical Scene v3 document. */
  toSceneSvg(opts = {}) {
    return sceneSvg(this.toScene(opts));
  }

  /** Existing native-raster display list compiled from Scene v3. */
  toSceneRasterCommands(opts = {}) {
    return sceneRasterCommands(this.toScene(opts), opts.scale ?? 1);
  }
}

export function figure(opts) {
  return new Figure(opts);
}
