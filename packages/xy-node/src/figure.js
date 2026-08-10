/**
 * Minimal Node figure — holds scatter/line/histogram/segments traces and builds
 * a §29-ish payload subset (PROTOCOL_VERSION matches Python).
 *
 * Documented subset vs full Python `Figure.build_payload`:
 * - Emits `protocol`, width/height, axes ranges, traces, columns, graph meta.
 * - Geometry columns are offset-encoded f32 via `xy_encode_f32` (§29).
 * - Line traces apply Rust M4 when over DECIMATION_THRESHOLD (§28).
 * - Histogram traces ship as rectangle columns from `xy_histogram_uniform`.
 * - Omits density tiers, legend resolution, animation keys, polar, etc.
 * - Enough for mark encode / M4 / hist + graph layout goldens across hosts.
 */

import {
  Column,
  DECIMATION_THRESHOLD,
  PROTOCOL_VERSION,
  encodeF32Values,
  geometryOffset,
  m4Points,
  minMax,
  pinsOffsetToZero,
} from "./encode.js";
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
    this.traces = [];
    this._graphMeta = null;
    this._axisRange = { x: null, y: null };
  }

  scatter(x, y, opts = {}) {
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
      });
      return this;
    }
    const composed = composeScatter(x, y, opts);
    const t = composed.traces[0];
    this.traces.push({
      id: opts.id ?? nextTraceId++,
      kind: "scatter",
      name: t.name,
      x: t.x,
      y: t.y,
      style: { ...t.style },
      x_axis: t.x_axis,
      y_axis: t.y_axis,
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

  ecdf(x, y, opts = {}) {
    if (opts._composed) {
      this.traces.push({
        id: opts.id ?? nextTraceId++,
        kind: "ecdf",
        name: opts.name ?? null,
        x: asF64(x),
        y: asF64(y),
        style: { ...(opts.style ?? {}) },
        mode: opts.mode ?? "exact",
        x_axis: opts.xAxis ?? "x",
        y_axis: opts.yAxis ?? "y",
      });
      return this;
    }
    const composed = composeEcdf(x, opts);
    const t = composed.traces[0];
    this.ecdf(t.x, t.y, {
      name: t.name,
      style: t.style,
      mode: t.mode,
      xAxis: t.x_axis,
      yAxis: t.y_axis,
      id: t.id,
      _composed: true,
    });
    return this;
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
   * Compose a sankey mark when straightforward (rects + link bands as segments).
   */
  sankey(nodes, links, opts = {}) {
    const composed = composeSankey(nodes, links, opts);
    for (const t of composed.traces) {
      if (t.kind === "segments") {
        this.segments(t.x0, t.y0, t.x1, t.y1, { name: t.name, style: t.style });
      } else if (t.kind === "scatter") {
        this.scatter(t.x, t.y, { name: t.name, style: t.style, _composed: true });
      }
    }
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
      if (t.kind === "segments" || t.kind === "histogram" || t.kind === "bar" || t.kind === "violin") {
        cols =
          axisId === "x" || axisId === (t.x_axis ?? "x") ? [t.x0, t.x1] : [t.y0, t.y1];
      } else if (t.kind === "area") {
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

  _emitScatter(t, pw) {
    const xCol = new Column(t.x);
    const yCol = new Column(t.y);
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

  _emitLine(t, pw, xr, pxWidth) {
    let xv = t.x;
    let yv = t.y;
    let tier = "direct";
    if (xv.length > DECIMATION_THRESHOLD) {
      const [outX, outY] = m4Points(xv, yv, xr[0], xr[1] + F64_EPS, pxWidth);
      xv = outX;
      yv = outY;
      tier = "decimated";
    }
    const xCol = new Column(xv);
    const yCol = new Column(yv);
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
      kind: "segments",
      name: t.name,
      style: { ...t.style },
      tier: "direct",
      n_points: t.x0.length,
      n_marks: t.x0.length,
      x0: pw.ship(t.x0, x0),
      x1: pw.ship(t.x1, x1),
      y0: pw.ship(t.y0, y0),
      y1: pw.ship(t.y1, y1),
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
      kind: "area",
      base: pw.ship(t.base, baseCol),
    };
  }

  _emitEcdf(t, pw) {
    const xCol = new Column(t.x);
    const yCol = new Column(t.y);
    return {
      id: t.id,
      kind: "ecdf",
      name: t.name,
      style: { ...t.style },
      tier: "direct",
      mode: t.mode ?? "exact",
      n_points: t.x.length,
      n_marks: t.x.length,
      x: pw.ship(t.x, xCol),
      y: pw.ship(t.y, yCol),
      x_axis: t.x_axis ?? "x",
      y_axis: t.y_axis ?? "y",
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
        specTraces.push(this._emitScatter(t, pw));
      } else if (t.kind === "line") {
        specTraces.push(this._emitLine(t, pw, xr, widthPx));
      } else if (t.kind === "histogram") {
        specTraces.push(this._emitHistogram(t, pw));
      } else if (t.kind === "segments") {
        specTraces.push(this._emitSegments(t, pw));
      } else if (t.kind === "area") {
        specTraces.push(this._emitArea(t, pw, xr, widthPx));
      } else if (t.kind === "bar" || t.kind === "violin") {
        specTraces.push(this._emitRect(t, pw, t.kind));
      } else if (t.kind === "ecdf") {
        specTraces.push(this._emitEcdf(t, pw));
      } else if (t.kind === "heatmap") {
        specTraces.push(this._emitHeatmap(t, pw));
      } else if (t.kind === "hexbin") {
        specTraces.push(this._emitHexbin(t, pw));
      } else {
        throw new Error(`unsupported trace kind ${t.kind} in Node figure MVP`);
      }
    }
    const axisSpecs = {
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
}

export function figure(opts) {
  return new Figure(opts);
}
