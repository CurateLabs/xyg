        // Recorded emit-payload-axis-tick-labels stay-host.
    // Node payload ribbon omits animation. Python `_emit_ribbon` ships
    // t.animation via `_transition_entry`. Matching Python would add
    // entry.animation. Recorded emit-ribbon-animation stay-host.
    // Node payload segments omits animation. Python `_emit_segments` ships
    // t.animation via `_transition_entry`. Matching Python would add
    // entry.animation. Recorded emit-segments-animation stay-host.
    // emit-area-animation stay-host.
    // emit-line-animation stay-host.
/**
 * Minimal Node figure — holds scatter/line/histogram/segments traces and builds
 * a §29-ish payload subset (PROTOCOL_VERSION matches Python).
 *
 * Documented subset vs full Python `Figure.build_payload`:
 * - Emits `protocol`, width/height, axes ranges, traces, columns, graph meta.
 * - Geometry columns are offset-encoded f32 via `xyg_encode_f32` (§29).
 * - Line traces apply Rust M4 when `xyg_payload_m4_indices` says decimated (§28).
 * - Histogram traces ship as rectangle columns from `xyg_histogram_bins`.
 * - Polar charts emit `coords: "polar"` + theta/r axis descriptors.
 * - Ribbon / sankey ship flow-band geometry (`target_y0`/`target_y1`).
 * - Scatter uses density tier when n > SCATTER_DENSITY_THRESHOLD (Rust payload_tier).
 * - At/above PYRAMID_MIN_POINTS, density prefers Tier-3 pyramid compose (§28).
 * - Contour / errorbar / stem / mesh / step / stairs / error_band / radar covered.
 * - Enough for mark encode / M4 / hist + graph layout goldens across hosts.
 */

import {
  Column,
  DENSITY_GRID,
  DENSITY_OVERLAY_STATIC_RASTER,
  DENSITY_OVERLAY_ROWS_EXCEED_U32,
  DENSITY_SAMPLE_SEED,
  DENSITY_SAMPLE_TARGET,
  PROTOCOL_VERSION,
  bin2d,
  densityEmitPlan,
  densityFormatBinning,
  densityLogU8,
  densityOverlayOpacity,
  encodeF32Values,
  geometryOffset,
  payloadEvenIndices,
  payloadErrorbarIndices,
  payloadM4Indices,
  payloadSegmentBudget,
  payloadSampleTargetIndices,
  payloadVisibleIndices,
  rectFiniteSel,
  minMax,
  normalizeF32,
  payloadTier,
  pinsOffsetToZero,
  shouldUseDensity,
  f64Ptr,
  u8Ptr,
} from "./encode.js";
import {
  xyAutoDomain,
  xyFigureAutorange,
  xyRectZeroBaselineFlags,
} from "./native.js";
import {
  PyramidCache,
  densityViewFromPyramid,
  pyramidAppendFromStream,
  shouldUsePyramid,
  tileStoreAppend,
} from "./pyramid.js";
import { composeGraph } from "./graph.js";
import { composeSankey } from "./sankey.js";
import { composeScatter, normalizeScatterStyle } from "./marks/scatter.js";
import { composeLine } from "./marks/line.js";
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
import { figureSceneV3, scatterPaintChannelNames, sceneRasterCommands, sceneSvg, svgToPdf } from "./scene.js";

export { PROTOCOL_VERSION };

let nextTraceId = 1;

function asF64(value) {
  if (value instanceof Float64Array) return value;// next-trace-id-base stay-host.

  if (value == null) return new Float64Array(0);
  return Float64Array.from(value, Number);
}

function gatherF64(arr, idx) {
  const src = asF64(arr);
  const out = new Float64Array(idx.length);
  for (let i = 0; i < idx.length; i += 1) out[i] = src[idx[i]];
  return out;
}

function gatherItems(arr, idx) {
  if (arr == null) return arr;
  const out = new Array(idx.length);
  for (let i = 0; i < idx.length; i += 1) out[i] = arr[idx[i]];
  return out;
}

export function scatterPerItemChannels(t) {
  return scatterPaintChannelNames(t).length > 0;
}

const AUTORANGE_KIND = {
  scatter: 0,
  line: 1,
  bar: 2,
  column: 3,
  histogram: 4,
  violin: 5,
  box: 6,
  box_whisker: 7,
  box_median: 8,
  segments: 9,
  errorbar: 10,
  stem: 11,
  area: 12,
  error_band: 13,
  ribbon: 14,
  triangle_mesh: 15,
  hexbin: 16,
  heatmap: 17,
};
const AUTORANGE_ROLES = [
  ["x", 0],
  ["y", 1],
  ["x0", 2],
  ["x1", 3],
  ["y0", 4],
  ["y1", 5],
  ["base", 6],
];

/** Payload density override. Python `payload_force_density` reads `force_density` only. */
export function scatterPayloadForceDensity(trace) {
  return (trace ?? {}).force_density;
}

/** Payload bin2d override. Python `_density_trace_spec` does not read `style.force_bin2d`. */
export function scatterPayloadForceBin2d(trace) {
  return (trace ?? {}).force_bin2d;
}

/** Payload direct override. Python `_emit_scatter` does not read `style.force_direct`. */
export function scatterPayloadForceDirect(trace) {
  return (trace ?? {}).force_direct;
}

/** Payload pyramid override. Python `_emit_scatter` does not read `style.force_pyramid`. */
export function scatterPayloadForcePyramid(trace) {
  return (trace ?? {}).force_pyramid;
}

/** Payload no-rescan override. Python `_density_trace_spec` does not read `style.no_rescan`. */
export function scatterPayloadNoRescan(trace) {
  return (trace ?? {}).no_rescan;
}

/** Autorange axis record. Python `_axis_scale` / `_range` read `axis_options` only. */
export function figureAutorangeAxisOptions(figure, axisId) {
  return (figure ?? {}).axis_options?.[axisId] ?? {};
}

/** Autorange axis scale. Python `_axis_scale` reads axis `type` only. */
export function figureAutorangeAxisScale(options) {
  const scale = (options ?? {}).type;
  return scale === "log" || scale === "symlog" ? scale : "linear";
}

/** Payload log-axis flag. Python `_axis_scale(...) == "log"` reads axis `type` only. */
export function figureAxisIsLog(figure, axisId) {
  return figureAutorangeAxisScale(figureAutorangeAxisOptions(figure, axisId)) === "log";
}

/** Polar autorange category labels. Python `_pack_autorange` reads `_axis_categories` only. */
export function figureAutorangeCategories(figure, axisId) {
  if ((figure ?? {}).coords !== "polar") return undefined;
  return figure._axis_categories?.[axisId];
}

/** Autorange axis domain. Python `_pack_autorange` / `_pack_public_export_support` read `axis_options.domain` only. */
export function figureAutorangeDomain(options) {
  return (options ?? {}).domain;
}

/** Axis kind. Python `_axis_kind` uses forced `type` time, then category labels, then `time_ms` columns. */
export function figureAxisKind(figure, axisId) {
  const options = figureAutorangeAxisOptions(figure, axisId);
  if (options.type === "time") return "time";
  const categories = figure?._axis_categories;
  if (categories != null && Object.prototype.hasOwnProperty.call(categories, axisId)) return "category";
  const axis = typeof axisId === "string" && axisId.startsWith("x") ? "x" : "y";
  for (const trace of figure?.traces ?? []) {
    if (axis === "x" && trace.x_axis !== axisId) continue;
    if (axis === "y" && trace.y_axis !== axisId) continue;
    const col = axis === "x" ? trace.x : trace.y;
    // Node scatter stores f64, so this time_ms scan is a no-op on typical
    // Node traces. Python Column.kind can be time_ms. Recorded
    // scatter-f64-kind stay-host.
    if (col?.kind === "time_ms") return "time";
  }
  return "linear";
}

/** Autorange theta unit. Python `_pack_autorange` reads `opts.get("theta_unit")` only. */
export function figureAutorangeThetaUnit(options) {
  return (options ?? {}).theta_unit;
}

function columnValues(col) {
  if (col == null) return null;
  if (col instanceof Column) return col.values;
  if (col instanceof Float64Array) return col;
  if (ArrayBuffer.isView(col) || Array.isArray(col)) return asF64(col);
  if (col.values != null) return asF64(col.values);
  return asF64(col);
}

function columnExtent(col) {
  const values = columnValues(col);
  if (values == null) return null;
  let min = Number.POSITIVE_INFINITY;
  let max = Number.NEGATIVE_INFINITY;
  let posMin = Number.POSITIVE_INFINITY;
  let posMax = Number.NEGATIVE_INFINITY;
  for (let i = 0; i < values.length; i += 1) {
    const value = values[i];
    if (!Number.isFinite(value)) continue;
    if (value < min) min = value;
    if (value > max) max = value;
    if (value > 0) {
      if (value < posMin) posMin = value;
      if (value > posMax) posMax = value;
    }
  }
  return {
    min: Number.isFinite(min) ? min : Number.NaN,
    max: Number.isFinite(max) ? max : Number.NaN,
    posMin: Number.isFinite(posMin) ? posMin : Number.NaN,
    posMax: Number.isFinite(posMax) ? posMax : Number.NaN,
  };
}

function packColumnExtent(role, extent) {
  const row = new Uint8Array(40);
  const view = new DataView(row.buffer);
  row[0] = role;
  view.setFloat64(8, extent.min, true);
  view.setFloat64(16, extent.max, true);
  view.setFloat64(24, extent.posMin, true);
  view.setFloat64(32, extent.posMax, true);
  return row;
}

function rectZeroBaselineFlags(base, value) {
  const baseArr = columnValues(base);
  const valueArr = columnValues(value);
  if (baseArr == null || valueArr == null || baseArr.length !== valueArr.length) return 0xff;
  return xyRectZeroBaselineFlags(f64Ptr(baseArr), f64Ptr(valueArr), BigInt(baseArr.length));
}

/** Expand a possibly-degenerate scalar domain in Rust (`Figure._auto_domain`). */
export function autoDomain(bounds) {
  const lo = new Float64Array(1);
  const hi = new Float64Array(1);
  const code = bounds == null
    ? xyAutoDomain(0, 0, 0, f64Ptr(lo), f64Ptr(hi))
    : xyAutoDomain(1, Number(bounds[0]), Number(bounds[1]), f64Ptr(lo), f64Ptr(hi));
  if (code !== 0) throw new RangeError("native auto_domain rejected the bounds");
  return [lo[0], hi[0]];
}

function packFigureAutorange(figure, axisId, { useDomain = true } = {}) {
  const options = figureAutorangeAxisOptions(figure, axisId);
  const domain = figureAutorangeDomain(options);
  let flags = 0;
  if (useDomain) flags |= 1 << 0;
  if (options.reverse) flags |= 1 << 1;
  if (domain != null) flags |= 1 << 2;
  if (options.margin != null) flags |= 1 << 3;
  if (figure.coords === "polar") flags |= 1 << 4;
  const axisDimX = typeof axisId === "string" ? axisId.startsWith("x") : axisId === "x";
  if (axisDimX) flags |= 1 << 5;
  const scale = figureAutorangeAxisScale(options);
  const scaleCode = scale === "log" ? 1 : scale === "symlog" ? 2 : 0;
  const categories = figureAutorangeCategories(figure, axisId);
  const kind = figureAxisKind(figure, axisId);
  const kindCode = kind === "time" ? 1 : kind === "category" ? 2 : 0;
  const thetaUnit = (figureAutorangeThetaUnit(options) ?? "radians") === "degrees" ? 1 : 0;
  const nCategories = categories?.length ? categories.length : 0;
  const traces = figure.traces ?? [];
  if (traces.length > 0xffff) throw new RangeError("figure autorange trace budget exceeded");
  const header = new Uint8Array(48);
  const view = new DataView(header.buffer);
  header.set([88, 89, 65, 82]);
  view.setUint32(4, 1, true);
  view.setUint32(8, flags, true);
  header[12] = scaleCode;
  header[13] = kindCode;
  header[14] = thetaUnit;
  header[15] = 0;
  view.setUint16(16, traces.length, true);
  view.setUint16(18, nCategories, true);
  view.setUint32(20, 0, true);
  view.setFloat64(24, domain != null ? Number(domain[0]) : 0, true);
  view.setFloat64(32, domain != null ? Number(domain[1]) : 0, true);
  view.setFloat64(40, options.margin == null ? 0 : Number(options.margin), true);
  const parts = [header];
  for (const trace of traces) {
    if (
      trace.kind === "ribbon"
      && (trace.x0 == null || trace.x1 == null || trace.y0 == null || trace.y1 == null)
    ) {
      throw new RangeError("ribbon trace missing geometry columns");
    }
    let traceFlags = 0;
    if ((trace.x_axis ?? "x") === axisId) traceFlags |= 1 << 0;
    if ((trace.y_axis ?? "y") === axisId) traceFlags |= 1 << 1;
    const hasEndpoints = trace.x0 != null && trace.x1 != null && trace.y0 != null && trace.y1 != null;
    if (hasEndpoints) traceFlags |= 1 << 2;
    if (trace.base != null) traceFlags |= 1 << 3;
    const columns = [];
    for (const [name, role] of AUTORANGE_ROLES) {
      const extent = columnExtent(trace[name]);
      if (extent == null) continue;
      columns.push(packColumnExtent(role, extent));
    }
    let zb = 0xff;
    if ((trace.kind === "bar" || trace.kind === "column" || trace.kind === "histogram") && hasEndpoints) {
      zb = rectZeroBaselineFlags(axisDimX ? trace.x0 : trace.y0, axisDimX ? trace.x1 : trace.y1);
    }
    const row = new Uint8Array(4);
    row[0] = AUTORANGE_KIND[trace.kind] ?? 255;
    row[1] = traceFlags;
    row[2] = columns.length;
    row[3] = zb;
    parts.push(row, ...columns);
  }
  const out = new Uint8Array(parts.reduce((n, part) => n + part.length, 0));
  let offset = 0;
  for (const part of parts) {
    out.set(part, offset);
    offset += part.length;
  }
  return out;
}

function optionalBoolean(value, name) {
  if (value == null) return undefined;
  if (typeof value !== "boolean") {
    throw new TypeError(`${name} must be a boolean`);
  }
  return value;
}

function copyAnnotation(annotation) {
  return {
    ...annotation,
    ...(annotation.style != null && typeof annotation.style === "object" && !Array.isArray(annotation.style)
      ? { style: { ...annotation.style } }
      : {}),
  };
}

function requireAnnotationObject(annotation) {
  if (annotation == null || typeof annotation !== "object" || Array.isArray(annotation)) {
    throw new TypeError("annotation must be an object");
  }
  return annotation;
}

function requirePlainObject(value, name) {
  if (value == null || typeof value !== "object" || Array.isArray(value)) {
    throw new TypeError(`${name} must be an object`);
  }
  return value;
}

function copySceneOptions(value, name) {
  // Preserve the user's literal values without interpreting them, while
  // preventing later caller mutation from changing the eventual ABI input.
  // Node 20+ supplies structuredClone for the public runtime contract.
  return structuredClone(requirePlainObject(value, name));
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
   * Raw f32 column already in final units (no offset) — size/color channels.
   * @param {Float32Array|ArrayLike<number>} values
   */
  shipScalar(values) {
    const enc =
      values instanceof Float32Array
        ? values
        : Float32Array.from(values, (v) => Number(v));
    return this._append(enc, {});
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
    this.showLegend = opts.showLegend ?? true;
    this.show_legend = this.showLegend;
    // These are deliberately inert host snapshots. `figureSceneV3` is the
    // only validation/packing seam, so Node cannot grow a competing chrome
    // layout or default-resolution policy.
    this.style = opts.style == null ? {} : copySceneOptions(opts.style, "style");
    this.legend = opts.legend == null ? {} : copySceneOptions(opts.legend, "legend");
    this.legend_options = this.legend;
    this.colorbarOptions = opts.colorbar == null ? null : copySceneOptions(opts.colorbar, "colorbar");
    this.colorbar_options = this.colorbarOptions;
    if (opts.annotations != null && !Array.isArray(opts.annotations)) {
      throw new TypeError("annotations must be an array");
    }
    // Keep this as a host-side collection only.  `figureSceneV3` remains the
    // single validation/packing seam for the bounded Rust-owned annotation
    // contract, so Node cannot acquire a second annotation policy.
    this.annotations = (opts.annotations ?? []).map((annotation) => copyAnnotation(requireAnnotationObject(annotation)));
    this.traces = [];
    this.axis_options = { x: {}, y: {} };
    this._graphMeta = null;
    this._axisRange = { x: null, y: null };
    this._polarMeta = null;
    /** @type {Map<number|string, PyramidCache>} */
    this._pyramids = new Map();
    this._appendSeq = 0;
    if (opts.xAxis != null || opts.x_axis != null) this.setAxis("x", opts.xAxis ?? opts.x_axis);
    if (opts.yAxis != null || opts.y_axis != null) this.setAxis("y", opts.yAxis ?? opts.y_axis);
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
    this.axis_options = this.axis_options ?? { x: {}, y: {} };
    this.axis_options.x = {
      ...(this.axis_options.x ?? {}),
      theta_unit: this._polarMeta.thetaUnit,
      theta_zero: this._polarMeta.thetaZero,
      theta_direction: this._polarMeta.thetaDirection,
      grid_shape: this._polarMeta.gridShape,
      sector: this._polarMeta.sector,
    };
    this.xAxis = this.axis_options.x;
    this.axis_options.y = {
      ...(this.axis_options.y ?? {}),
      hole: this._polarMeta.hole,
    };
    this.yAxis = this.axis_options.y;
    return this;
  }

  /** Pin an axis domain (used by facet shared-axis + polar pie domains). */
  setAxisDomain(axisId, range) {
    const [a, b] = range;
    const domain = [Math.min(a, b), Math.max(a, b)];
    this._axisRange[axisId] = domain;
    this.axis_options = this.axis_options ?? { x: {}, y: {} };
    this.axis_options[axisId] = { ...(this.axis_options[axisId] ?? {}), domain };
    this[`${axisId}Axis`] = this.axis_options[axisId];
    return this;
  }

  /** Bounded Cartesian Scene axis authoring; Rust resolves layout and chrome. */
  setAxis(axisId, options = {}) {
    if (axisId !== "x" && axisId !== "y") throw new RangeError("axisId must be x or y");
    options = copySceneOptions(options, `Scene ${axisId} axis options`);
    this.axis_options = this.axis_options ?? { x: {}, y: {} };
    this.axis_options[axisId] = { ...(this.axis_options[axisId] ?? {}), ...options };
    this[`${axisId}Axis`] = this.axis_options[axisId];
    if (options.domain != null) this.setAxisDomain(axisId, options.domain);
    return this;
  }

  /**
   * Set literal chart/plot paint for the bounded Scene subset.
   *
   * This does not resolve CSS, defaults, or geometry: Rust validates the
   * resulting Scene frame when a consumer asks for `toScene()`.
   */
  setStyle(style = {}) {
    this.style = copySceneOptions(style, "Scene style");
    return this;
  }

  /** Set one bounded static legend request for the Rust Scene compiler. */
  setLegend(legend = {}) {
    this.legend = copySceneOptions(legend, "Scene legend");
    this.legend_options = this.legend;
    return this;
  }

  /** Set (or clear with `null`) one literal-banded Scene colorbar request. */
  setColorbar(colorbar = null) {
    this.colorbarOptions = colorbar == null ? null : copySceneOptions(colorbar, "Scene colorbar");
    this.colorbar_options = this.colorbarOptions;
    return this;
  }

  /**
   * Add one authored Cartesian annotation to the canonical Scene input.
   *
   * The Scene compiler validates the bounded record kinds, style vocabulary,
   * resource limits, and coordinates when `toScene()` is requested.  Keeping
   * those decisions there makes this a thin public authoring seam rather than
   * a parallel Node implementation of Scene policy.
  */
  annotate(annotation) {
    this.annotations.push(copyAnnotation(requireAnnotationObject(annotation)));
    return this;
  }

  scatter(x, y, opts = {}) {
    const forceDensity = opts.forceDensity ?? opts.force_density;
    const forceDirect = opts.forceDirect ?? opts.force_direct;
    const forcePyramid = opts.forcePyramid ?? opts.force_pyramid;
    const pyramidSpill = optionalBoolean(
      opts.pyramidSpill ?? opts.pyramid_spill,
      "scatter pyramidSpill",
    );
    if (opts._composed) {
      this.traces.push({
        id: opts.id ?? nextTraceId++,
        kind: "scatter",    // Node payload density scatter omits animation. Python `_transition_entry`
    // ships t.animation on the density path. Matching Python would add
    // entry.animation. Recorded emit-density-animation stay-host.

        name: opts.name ?? null,
        // Node scatter stores f64, not Column.kind. Python Column infers
        // time_ms. Recorded scatter-f64-kind stay-host.
        x: asF64(x),
        y: asF64(y),
        style: normalizeScatterStyle(opts.style),
        x_axis: opts.xAxis ?? "x",
        y_axis: opts.yAxis ?? "y",
        ...(opts.color != null ? { color: opts.color } : {}),
        ...(opts.sizeValues != null ? { sizeValues: opts.sizeValues } : {}),
        ...(opts.sizeRange != null ? { sizeRange: opts.sizeRange } : {}),
        ...(opts.tooltip_rows != null ? { tooltip_rows: opts.tooltip_rows } : {}),
        ...(forceDensity != null ? { force_density: Boolean(forceDensity) } : {}),
        ...(forceDirect != null ? { force_direct: Boolean(forceDirect) } : {}),
        ...(forcePyramid != null ? { force_pyramid: Boolean(forcePyramid) } : {}),
        ...(pyramidSpill != null ? { pyramid_spill: pyramidSpill } : {}),
      });
      return this;
    }
    const composed = composeScatter(x, y, opts);
    const t = composed.traces[0];
    const fd = forceDensity ?? t.force_density;
    const fx = forceDirect ?? t.force_direct;
    const fp = forcePyramid ?? t.force_pyramid;
    const ps = pyramidSpill ?? t.pyramid_spill;
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
      ...(ps != null ? { pyramid_spill: ps } : {}),
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
      kind: "histogram",    // Python would add entry.animation. Recorded emit-hist-animation stay-host.

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
      kind,    // Node payload rect omits animation. Python `_emit_rect` ships t.animation
    // via `_transition_entry`. Matching Python would add entry.animation.
    // Recorded emit-rect-animation stay-host.

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
      if (t.kind === "box_whisker" || t.kind === "box_median") {
        this._pushSegmentTrace(t, { name: t.name, style: t.style });
      } else if (t.kind === "box") {
        this._pushRectTrace("box", t, { name: t.name, style: t.style });
      } else if (t.kind === "scatter") {
        this.scatter(t.x, t.y, { name: t.name, style: t.style, xAxis: t.x_axis, yAxis: t.y_axis, _composed: true });
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
      ...(opts.color ?? t.color) != null ? { color: opts.color ?? t.color } : {},
      ...(opts.tooltip_rows ?? t.tooltip_rows) != null
        ? { tooltip_rows: opts.tooltip_rows ?? t.tooltip_rows }
        : {},
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
      colormapStops: opts.colormapStops ?? t.colormapStops ?? null,
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
      color_ch: t.color_ch,
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
    const t = composeSegments(x0, y0, x1, y1, opts).traces[0];
    this._pushSegmentTrace(t, opts);
    return this;
  }

  /**
   * Compose a graph mark (normalize → layout → render-graph → traces + meta).
   */
  graph(nodes, edges, opts = {}) {
    const composed = composeGraph(nodes, edges, opts);
    for (const t of composed.traces) {
      if (t.kind === "segments") {
        this.segments(t.x0, t.y0, t.x1, t.y1, {
          name: t.name,
          style: t.style,
          color: t.color,
          tooltip_rows: t.tooltip_rows,
        });
      } else if (t.kind === "scatter") {
        this.scatter(t.x, t.y, {
          name: t.name,
          style: t.style,
          color: t.color,
          sizeValues: t.sizeValues,
          tooltip_rows: t.tooltip_rows,
          _composed: true,
        });
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

  _range(axisId, { useDomain = true } = {}) {
    const packed = packFigureAutorange(this, axisId, { useDomain });
    const lo = new Float64Array(1);
    const hi = new Float64Array(1);
    const code = xyFigureAutorange(u8Ptr(packed), BigInt(packed.length), f64Ptr(lo), f64Ptr(hi));
    if (code === -4) {
      throw new RangeError(`${axisId} log axis requires at least one positive value`);
    }
    if (code !== 0) throw new RangeError("invalid figure autorange envelope");
    return [lo[0], hi[0]];
  }

  _axisKind(axisId) {
    return figureAxisKind(this, axisId);
  }

  _axisIsLog(axisId) {
    return figureAxisIsLog(this, axisId);
  }

  _axisDomain(axisId) {
    return figureAutorangeDomain(figureAutorangeAxisOptions(this, axisId));
  }

  _visibleSel(t, x, y, {
    base = null,
    prefiltered = false,
    xCol = null,
    yCol = null,
    baseCol = null,
  } = {}) {
    const xc = xCol ?? (t._xCol instanceof Column ? t._xCol : new Column(x));
    const yc = yCol ?? (t._yCol instanceof Column ? t._yCol : new Column(y));
    const { keepAll, indices } = payloadVisibleIndices(x, y, {
      xLog: this._axisIsLog(t.x_axis ?? "x"),
      yLog: this._axisIsLog(t.y_axis ?? "y"),
      base,
      prefiltered,
      xHasNulls: xc.nullCount > 0,
      yHasNulls: yc.nullCount > 0,
      hasBase: base != null,
      baseHasNulls: baseCol != null ? baseCol.nullCount > 0 : false,
    });
    return keepAll ? null : indices;
  }

  _emitScatter(t, pw, xr, yr) {
    const forceDensity = Boolean(scatterPayloadForceDensity(t));
    const forceDirect = Boolean(scatterPayloadForceDirect(t));
    const forcePyramid = Boolean(scatterPayloadForcePyramid(t));
    // Node still passes forceDirect into shouldUseDensity. Python
    // `_emit_scatter` never passes force_direct (ABI defaults false).
    // Dropping it would ship density for Node `forceDirect: true` on
    // large scatters. Recorded emit-force-direct stay-host.
    // Node also ORs forcePyramid into forceDensity. Python Trace has no
    // force_pyramid and `_emit_scatter` never densifies from it. Dropping
    // the OR would ship direct for Node `forcePyramid: true` below the
    // density threshold. Recorded emit-force-pyramid stay-host.
    if (
      shouldUseDensity(t.x.length, {
        forceDensity: forceDensity || forcePyramid,
        forceDirect,
        coords: this.coords,
        perItemChannels: scatterPerItemChannels(t),
      })
    ) {
      return this._emitScatterDensity(t, pw, xr, yr);
    }
    const xCol = t._xCol instanceof Column ? t._xCol : new Column(t.x);
    const yCol = t._yCol instanceof Column ? t._yCol : new Column(t.y);
    t._xCol = xCol;
    t._yCol = yCol;
    let xv = t.x;
    let yv = t.y;
    const sel = this._visibleSel(t, xv, yv, { xCol, yCol });
    if (sel != null) {
      xv = gatherF64(xv, sel);
      yv = gatherF64(yv, sel);
    }
    const entry = {
      id: t.id,
      kind: "scatter",
      name: t.name,
      style: { ...t.style },
      tier: "direct",
      n_points: t.x.length,
      n_marks: xv.length,
      // Node payload scatter omits ship scale. Python `_base_entry` passes
      // `_axis_scale`. Matching Python would pin log-axis offset to 0.
      // Recorded emit-scatter-ship-scale stay-host.
      x: pw.ship(xv, sel == null ? xCol : new Column(xv)),
      y: pw.ship(yv, sel == null ? yCol : new Column(yv)),
      x_axis: t.x_axis ?? "x",
      y_axis: t.y_axis ?? "y",
    };
    // Node payload scatter ships t.color. Python `_emit_scatter` ships
    // color_ch via `_ship_channels`. Matching Python would ignore t.color.
    // Recorded scatter-ship-color stay-host.
    const color = this._shipColor(t.color, pw, sel);
    if (color != null) entry.color = color;
    // Node payload scatter ships t.sizeValues. Python `_emit_scatter` ships
    // size_ch via `_ship_channels`. Matching Python would ignore t.sizeValues.
    // Recorded emit-scatter-size stay-host.
    if (t.sizeValues != null) {
      let values = t.sizeValues instanceof Float64Array
        ? t.sizeValues
        : Float64Array.from(t.sizeValues, Number);
      if (sel != null) values = gatherF64(values, sel);
      const mm = minMax(values) ?? [0, 1];
      const lo = mm[0];
      const hi = mm[0] === mm[1] ? mm[0] + 1 : mm[1];
      const norm = normalizeF32(values, lo, hi);
      entry.size = {
        mode: "continuous",
        range_px: t.sizeRange ?? [8, 22],
        domain: [lo, hi],
        buf: pw.shipScalar(norm),
      };        // Recorded emit-payload-axis-minor-style stay-host.
        // x_axis.tick_label_anchor. Recorded emit-payload-axis-tick-label-anchor
        // x_axis.tick_label_angle. Recorded emit-payload-axis-tick-label-angle
        // Recorded emit-payload-axis-label-offset stay-host.
        // x_axis.tick_label_sides. Recorded emit-payload-axis-tick-label-sides
        // emit-payload-axis-bounds stay-host.
        // emit-payload-axis-domain stay-host.
        // Recorded emit-payload-axis-tick-count stay-host.
        // x_axis.minor_tick_values. Recorded emit-payload-axis-minor-ticks

    }
    if (t.tooltip_rows != null) {
      // Node payload scatter skips tooltip_rows length. Python        // Recorded emit-payload-axis-tick-values stay-host.

      // `_attach_tooltip_rows` rejects a mismatch with n_points. Matching
      // Python would throw. Recorded emit-scatter-tooltip-len stay-host.
      entry.tooltip_rows = sel == null ? t.tooltip_rows : gatherItems(t.tooltip_rows, sel);
    }
    // Node payload scatter omits stroke_ch. Python `_emit_scatter` ships
    // stroke_ch via `_ship_trace_styles`. Matching Python would add
    // entry.stroke. Recorded emit-scatter-stroke stay-host.
    // Node payload scatter omits style_channels. Python `_emit_scatter` ships
    // them as `channels` via `_ship_trace_styles`. Matching Python would add
    // entry.channels. Recorded emit-scatter-channels stay-host.
    // Node payload scatter omits transition_keys. Python `_emit_scatter` ships
    // them via `_transition_entry`. Matching Python would add entry.keys.
    // Recorded emit-scatter-transition stay-host.
    // Node payload scatter omits animation. Python `_base_entry` ships
    // t.animation. Matching Python would add entry.animation. Recorded
    // emit-scatter-animation stay-host.
    return entry;
  }

  /**
   * Tier-2/3 density scatter — `bin_2d` below pyramid floor; Tier-3 pyramid
   * compose at/above `PYRAMID_MIN_POINTS` (§28 `binning: pyramid-L*`).
   */
  _emitScatterDensity(t, pw, xr, yr) {
    const [w, h] = DENSITY_GRID;
    let grid;
    let binning = densityFormatBinning({ exact: true });
    let reduction = "bin2d";
    let tiles = null;
    const forceBin2d = Boolean(scatterPayloadForceBin2d(t));
    const forcePyramid = Boolean(scatterPayloadForcePyramid(t));
    const noRescan = Boolean(scatterPayloadNoRescan(t));
    const forceSpill = Boolean(t.pyramid_spill ?? t.style?.pyramid_spill);
    let hasPyramidResource = false;
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
      hasPyramidResource = true;
      const served = densityViewFromPyramid(cache, t.x, t.y, xr[0], xr[1], yr[0], yr[1], w, h, {
        force: forcePyramid,
        noRescan,
        forceSpill,
      });
      if (served != null) {
        grid = served.grid;
        binning = served.binning;
        reduction = served.reduction;
        if (served.tiles != null) {
          tiles = served.tiles;
        }
      }
    }
    if (grid == null) {
      grid = bin2d(t.x, t.y, xr[0], xr[1], yr[0], yr[1], w, h);
      binning = densityFormatBinning({ exact: true });
      reduction = "bin2d";
    }
    const xmm = minMax(t.x) ?? xr;
    const ymm = minMax(t.y) ?? yr;
    const plan = densityEmitPlan({
      cartesian: this.coords === "cartesian",
      xLinear: true,
      yLinear: true,
      pointOverlay: true,
      gridFromPyramid: reduction === "pyramid-count",
      hasPyramidResource,
      forceBin2d,
      forcePyramid,
      // Node colorMode is style.color ? 1 : 0. Python `_density_trace_spec`
      // uses color_ch (none/constant/other). Node scatter() does not copy
      // color_ch onto traces. Recorded density-colormode stay-host.
      colorMode: t.style?.color ? 1 : 0,
      xMin: xmm[0],
      xMax: xmm[1],
      yMin: ymm[0],
      yMax: ymm[1],
      xr0: xr[0],
      xr1: xr[1],
      yr0: yr[0],
      yr1: yr[1],
      nPoints: t.x.length,
    });
    const { encoded, max } = densityLogU8(grid);
    const density = {
      buf: pw.shipU8(encoded),
      w,
      h,
      max,
      enc: "log-u8",
      // Node payload density colormap stays `style.colormap`. Python
      // `_density_trace_spec` uses `color_ch.colormap`. Node `scatter()`
      // does not copy `color_ch` onto traces. Recorded density-colormap stay-host.
      colormap: t.style?.colormap ?? "viridis",
      x_range: [...xr],
      y_range: [...yr],
      binning,
      reduction,
      // Node payload density dropped_channels stays empty. Python
      // `_density_trace_spec` uses `per_item_channel_names`. Matching Python
      // would list per-item extras. Recorded emit-density-dropped-channels stay-host.
      // Node payload density omits mean-color rgba. Python `_density_trace_spec`
      // ships rgba from `trace_bin_colors`. Matching Python would add
      // density.rgba. Recorded emit-density-rgba stay-host.
      // Node payload density omits wasm_source. Python `_density_trace_spec`
      // ships a split f64 replay source. Matching Python would add
      // density.wasm_source. Recorded emit-density-wasm-source stay-host.
      channels_dropped: false,
      dropped_channels: [],
    };
    if (plan.overlay_omitted === DENSITY_OVERLAY_STATIC_RASTER) {
      density.overlay_omitted = "static_raster";
    } else if (plan.overlay_omitted === DENSITY_OVERLAY_ROWS_EXCEED_U32) {
      density.overlay_omitted = "rows_exceed_u32";
    } else {
      const n = t.x.length;
      const { keepAll, indices } = payloadSampleTargetIndices({
        n,
        target: DENSITY_SAMPLE_TARGET,      // NaN rows from sample.n. Recorded emit-density-sample-sel stay-host.

        seed: DENSITY_SAMPLE_SEED,
      });
      const sx = keepAll ? t.x : gatherF64(t.x, indices);
      const sy = keepAll ? t.y : gatherF64(t.y, indices);
      if (sx.length > 0) {
        const sampleX = new Column(sx);
        const sampleY = new Column(sy);
        // Node density sample omits ship scale. Python `_density_sample_spec`
        // passes `_axis_scale` into `pw.ship_values`. Matching Python would
        // pin log-axis offset to 0. Recorded emit-density-sample-ship-scale stay-host.
        const xCol = pw.ship(sx, sampleX);
        const yCol = pw.ship(sy, sampleY);
        const opacityRaw = Number(t.style?.opacity ?? 0.8);
        density.sample = {
          mode: "sampled",
          n: sx.length,
          visible: n,
          target: DENSITY_SAMPLE_TARGET,
          level: 0,
          seed: DENSITY_SAMPLE_SEED,
          x: { col: xCol, ...pw.columns[xCol] },
          y: { col: yCol, ...pw.columns[yCol] },
          x_range: [...xr],
          y_range: [...yr],
          style: {
            ...t.style,
            opacity: densityOverlayOpacity(opacityRaw),
          },
        };
        // Node density sample omits color_ch. Python `_density_sample_spec`
        // ships color/size via `_ship_channels`. Matching Python would add
        // sample.color. Recorded emit-density-sample-color stay-host.
        // Node density sample omits size_ch. Python `_density_sample_spec`
        // ships size via `_ship_channels`. Matching Python would add
        // sample.size. Recorded emit-density-sample-size stay-host.
        // Node density sample omits stroke_ch. Python `_density_sample_spec`
        // ships stroke via `_ship_trace_styles`. Matching Python would add
        // sample.stroke. Recorded emit-density-sample-stroke stay-host.
        // Node density sample omits style_channels. Python `_density_sample_spec`
        // ships them as `channels` via `_ship_trace_styles`. Matching Python
        // would add sample.channels. Recorded emit-density-sample-channels stay-host.
      }
    }
    if (tiles != null) {
      density.tiles = tiles;
    }
    if (t.style?.color) {
      density.color = t.style.color;
    }
    // Node payload density scatter omits transition_keys. Python `_emit_scatter`
    // ships them via `_transition_entry` on the density path. Matching Python
    // would add entry.keys. Recorded emit-density-transition stay-host.
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
      density,      // rows from entry.visible. Recorded emit-density-visible stay-host.

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
    const { tier: tierCode, indices } = payloadM4Indices({
      nPoints: xv.length,
      x: xv,
      y: yv,
      x0: xr[0],
      x1: xr[1],
      nBuckets: pxWidth,
      polar: this.coords === "polar",
    });
    const decimated = tierCode === 1;
    let tier = "direct";
    if (decimated) {
      xv = gatherF64(xv, indices);
      yv = gatherF64(yv, indices);
      tier = "decimated";
    }
    const xCol = !decimated && t._xCol instanceof Column ? t._xCol : new Column(xv);
    const yCol = !decimated && t._yCol instanceof Column ? t._yCol : new Column(yv);
    if (!decimated) {
      t._xCol = xCol;
      t._yCol = yCol;
    }
    const vis = this._visibleSel(t, xv, yv, {
      prefiltered: decimated,
    });
    if (vis != null) {
      xv = gatherF64(xv, vis);
      yv = gatherF64(yv, vis);
    }
    const shipX = vis == null ? xCol : new Column(xv);
    const shipY = vis == null ? yCol : new Column(yv);
    const entry = {
      id: t.id,
      kind: "line",
      name: t.name,
      // Node payload line copies t.style. Python `_emit_line` uses
      // `_default_styled` to fill palette color when style.color is missing.
      // Matching Python would add style.color. Recorded
      // emit-line-default-styled stay-host.
      style: { ...t.style },
      tier,
      n_points: t.x.length,
      n_marks: xv.length,
      // Node payload line omits ship scale. Python `_base_entry` passes
      // `_axis_scale`. Matching Python would pin log-axis offset to 0.
      // Recorded emit-line-ship-scale stay-host.
      x: pw.ship(xv, shipX),
      y: pw.ship(yv, shipY),
      x_axis: t.x_axis ?? "x",
      y_axis: t.y_axis ?? "y",
    };
    if (tier === "decimated") {
      entry.decimation_px = pxWidth;
    }
    // Node payload line omits transition_keys. Python `_emit_line` ships them
    // via `_transition_entry`. Matching Python would add entry.keys.
    // Recorded emit-line-transition stay-host.
    return entry;
  }

  _emitHistogram(t, pw) {
    const x0 = new Column(t.x0);
    const x1 = new Column(t.x1);
    const y0 = new Column(t.y0);
    const y1 = new Column(t.y1);
    // Node payload histogram omits color_ch. Python `_emit_histogram` calls
    // `_emit_rect`, which ships color_ch. Matching Python would add
    // entry.color. Recorded emit-hist-color stay-host.
    // Node payload histogram omits stroke_ch. Python `_emit_histogram` calls
    // `_emit_rect`, which ships stroke_ch via `_ship_trace_styles`. Matching
    // Python would add entry.stroke. Recorded emit-hist-stroke stay-host.
    // Node payload histogram omits style_channels. Python `_emit_histogram`
    // calls `_emit_rect`, which ships them as `channels` via `_ship_trace_styles`.
    // Matching Python would add entry.channels. Recorded emit-hist-channels stay-host.
    // Node payload histogram skips rectFiniteSel. Python `_emit_histogram` calls
    // `_emit_rect`, which drops non-finite rows. Matching Python would gather.
    // Recorded emit-hist-finite-sel stay-host.
    // Node payload histogram omits transition_keys. Python `_emit_histogram`
    // calls `_emit_rect`, which ships them via `_transition_entry`. Matching
    // Python would add entry.keys. Recorded emit-hist-transition stay-host.
    return {
      id: t.id,
      kind: "histogram",
      name: t.name,
      // Node payload histogram copies t.style. Python `_emit_histogram`
      // calls `_emit_rect`, which uses `_default_styled`. Matching Python
      // would add style.color. Recorded emit-hist-default-styled stay-host.
      style: { ...t.style },
      tier: "direct",
      n_points: t.count ?? t.x0.length,
      n_marks: t.x0.length,
      // Node payload histogram omits ship scale. Python `_emit_histogram`
      // calls `_emit_rect`, which passes `_axis_scale` into `pw.ship`.
      // Matching Python would pin log-axis offset to 0. Recorded
      // emit-hist-ship-scale stay-host.
      x0: pw.ship(t.x0, x0),
      x1: pw.ship(t.x1, x1),
      y0: pw.ship(t.y0, y0),
      y1: pw.ship(t.y1, y1),
      x_axis: t.x_axis ?? "x",
      y_axis: t.y_axis ?? "y",
    };
  }

  _emitSegments(t, pw, pxWidth) {
    if (t.x0 == null || t.x1 == null || t.y0 == null || t.y1 == null) {
      throw new Error(`${t.kind} trace missing segment columns`);
    }
    let x0v = t.x0;
    let x1v = t.x1;
    let y0v = t.y0;
    let y1v = t.y1;
    let tier = "direct";
    const maxGroups = payloadSegmentBudget(pxWidth);
    if (t.kind === "errorbar" && t.count) {
      const { keepAll, indices } = payloadErrorbarIndices(x0v.length, t.count, maxGroups);
      if (!keepAll) {
        x0v = gatherF64(x0v, indices);
        x1v = gatherF64(x1v, indices);
        y0v = gatherF64(y0v, indices);
        y1v = gatherF64(y1v, indices);
        tier = "decimated";
      }
    } else if (t.kind === "stem" && x0v.length > maxGroups) {
      const { keepAll, indices } = payloadEvenIndices(x0v.length, maxGroups);
      if (!keepAll) {
        x0v = gatherF64(x0v, indices);
        x1v = gatherF64(x1v, indices);
        y0v = gatherF64(y0v, indices);
        y1v = gatherF64(y1v, indices);
        tier = "decimated";
      }
    }
    const finiteSel = rectFiniteSel(t, x0v, x1v, y0v, y1v);
    if (finiteSel != null) {
      x0v = gatherF64(x0v, finiteSel);
      x1v = gatherF64(x1v, finiteSel);
      y0v = gatherF64(y0v, finiteSel);
      y1v = gatherF64(y1v, finiteSel);
    }
    const x0 = new Column(x0v);
    const x1 = new Column(x1v);
    const y0 = new Column(y0v);
    const y1 = new Column(y1v);
    const entry = {
      id: t.id,
      kind: t.kind ?? "segments",
      name: t.name,
      // Node payload segments copies t.style. Python `_emit_segments` uses
      // `_default_styled` to fill palette color when style.color is missing.
      // Matching Python would add style.color. Recorded
      // emit-segments-default-styled stay-host.
      style: { ...t.style },
      tier,
      n_points: t.count ?? t.x0.length,
      n_marks: x0v.length,
      // Node payload segments omits ship scale. Python `_emit_segments`
      // passes `_axis_scale` into `pw.ship`. Matching Python would pin
      // log-axis offset to 0. Recorded emit-segments-ship-scale stay-host.
      x0: pw.ship(x0v, x0),
      x1: pw.ship(x1v, x1),
      y0: pw.ship(y0v, y0),
      y1: pw.ship(y1v, y1),
      x_axis: t.x_axis ?? "x",
      y_axis: t.y_axis ?? "y",
    };
    // Node payload segments ships t.color. Python `_emit_segments` ships
    // color_ch via `_ship_channels`. Matching Python would ignore t.color.
    // Recorded emit-segments-color stay-host.
    const color = this._shipColor(t.color, pw);
    if (color != null) entry.color = color;
    if (t.tooltip_rows != null) {
      // Node payload segments skips tooltip_rows length. Python
      // `_attach_tooltip_rows` rejects a mismatch with n_points. Matching
      // Python would throw. Recorded emit-segments-tooltip-len stay-host.
      entry.tooltip_rows = t.tooltip_rows;
    }
    // Node payload segments omits stroke_ch. Python `_emit_segments` ships
    // stroke_ch via `_ship_trace_styles`. Matching Python would add
    // entry.stroke. Recorded emit-segments-stroke stay-host.
    // Node payload segments omits style_channels. Python `_emit_segments`
    // ships them as `channels` via `_ship_trace_styles`. Matching Python
    // would add entry.channels. Recorded emit-segments-channels stay-host.
    // Node payload segments omits transition_keys. Python `_emit_segments`
    // ships them via `_transition_entry`. Matching Python would add entry.keys.
    // Recorded emit-segments-transition stay-host.
    return entry;
  }

  _emitTriangleMesh(t, pw) {
    const x0 = new Column(t.x0);
    const y0 = new Column(t.y0);
    const x1 = new Column(t.x1);
    const y1 = new Column(t.y1);
    const x2 = new Column(t.x);
    const y2 = new Column(t.y);
    // Node payload mesh omits color_ch. Python `_emit_triangle_mesh` ships
    // color_ch via `_ship_channels`. Matching Python would add entry.color.
    // Recorded emit-mesh-color stay-host.
    // Node payload mesh omits stroke_ch. Python `_emit_triangle_mesh` ships
    // stroke_ch via `_ship_trace_styles`. Matching Python would add
    // entry.stroke. Recorded emit-mesh-stroke stay-host.
    // Node payload mesh omits style_channels. Python `_emit_triangle_mesh`
    // ships them as `channels` via `_ship_trace_styles`. Matching Python
    // would add entry.channels. Recorded emit-mesh-channels stay-host.
    // Node payload mesh skips valid_indices_f64 gather. Python
    // `_emit_triangle_mesh` drops null geometry rows. Matching Python would
    // gather. Recorded emit-mesh-gather stay-host.
    // Node payload mesh omits transition_keys. Python `_emit_triangle_mesh`
    // ships them via `_transition_entry`. Matching Python would add entry.keys.
    // Recorded emit-mesh-transition stay-host.
    return {
      id: t.id,
      kind: "triangle_mesh",    // Node payload mesh omits animation. Python `_emit_triangle_mesh` ships
    // t.animation via `_transition_entry`. Matching Python would add
    // entry.animation. Recorded emit-mesh-animation stay-host.

      name: t.name,
      // Node payload mesh copies t.style. Python `_emit_triangle_mesh` uses
      // `_default_styled` to fill palette color when style.color is missing.
      // Matching Python would add style.color. Recorded
      // emit-mesh-default-styled stay-host.
      style: { ...t.style },
      tier: "direct",
      n_points: t.count ?? t.x0.length,
      n_marks: t.x0.length,
      // Node payload mesh omits ship scale. Python `_emit_triangle_mesh`
      // passes `_axis_scale` into `pw.ship`. Matching Python would pin
      // log-axis offset to 0. Recorded emit-mesh-ship-scale stay-host.
      x0: pw.ship(t.x0, x0),
      y0: pw.ship(t.y0, y0),
      x1: pw.ship(t.x1, x1),
      y1: pw.ship(t.y1, y1),
      // Node payload mesh ships x/y for the third vertex. Python
      // `_emit_triangle_mesh` ships x2/y2. Matching Python would rename these
      // keys. Recorded emit-mesh-xy stay-host.
      x: pw.ship(t.x, x2),
      y: pw.ship(t.y, y2),
      x_axis: t.x_axis ?? "x",
      y_axis: t.y_axis ?? "y",
    };
  }

  _emitRect(t, pw, kind) {
    if (t.x0 == null || t.x1 == null || t.y0 == null || t.y1 == null) {
      throw new Error(`${t.kind} trace missing rectangle columns`);
    }
    let x0v = t.x0;
    let x1v = t.x1;
    let y0v = t.y0;
    let y1v = t.y1;
    const finiteSel = rectFiniteSel(t, x0v, x1v, y0v, y1v);
    if (finiteSel != null) {
      x0v = gatherF64(x0v, finiteSel);
      x1v = gatherF64(x1v, finiteSel);
      y0v = gatherF64(y0v, finiteSel);
      y1v = gatherF64(y1v, finiteSel);
    }
    const x0 = new Column(x0v);
    const x1 = new Column(x1v);
    const y0 = new Column(y0v);
    const y1 = new Column(y1v);
    // Node payload rect omits color_ch. Python `_emit_rect` ships color_ch
    // via `_ship_channels`. Matching Python would add entry.color. Recorded
    // emit-rect-color stay-host.
    // Node payload rect omits stroke_ch. Python `_emit_rect` ships stroke_ch
    // via `_ship_trace_styles`. Matching Python would add entry.stroke.
    // Recorded emit-rect-stroke stay-host.
    // Node payload rect omits style_channels. Python `_emit_rect` ships them
    // as `channels` via `_ship_trace_styles`. Matching Python would add
    // entry.channels. Recorded emit-rect-channels stay-host.
    // Node payload bar/column ships rect columns. Python `_emit_bar` ships a
    // nested `bar` spec via `_emit_bar_compact`. Matching Python would nest
    // bar. Recorded emit-bar-compact stay-host.
    // Node payload rect omits transition_keys. Python `_emit_rect` ships them
    // via `_transition_entry`. Matching Python would add entry.keys.
    // Recorded emit-rect-transition stay-host.
    return {
      id: t.id,
      kind,
      name: t.name,
      // Node payload rect copies t.style. Python `_emit_rect` uses
      // `_default_styled` to fill palette color when style.color is missing.
      // Matching Python would add style.color. Recorded
      // emit-rect-default-styled stay-host.
      style: { ...t.style },
      tier: "direct",
      n_points: t.count ?? t.x0.length,
      n_marks: x0v.length,
      // Node payload rect omits ship scale. Python `_emit_rect` passes
      // `_axis_scale` into `pw.ship`. Matching Python would pin log-axis
      // offset to 0. Recorded emit-rect-ship-scale stay-host.
      x0: pw.ship(x0v, x0),
      x1: pw.ship(x1v, x1),
      y0: pw.ship(y0v, y0),
      y1: pw.ship(y1v, y1),
      x_axis: t.x_axis ?? "x",
      y_axis: t.y_axis ?? "y",
    };
  }

  _emitArea(t, pw, xr, pxWidth) {
    const { tier: tierCode, indices } = payloadM4Indices({
      nPoints: t.x.length,
      x: t.x,
      y: t.y,
      x0: xr[0],
      x1: xr[1],
      nBuckets: pxWidth,
      polar: this.coords === "polar",
    });
    let xv = t.x;
    let yv = t.y;
    let bv = t.base;
    let tier = "direct";
    if (tierCode === 1) {
      xv = gatherF64(xv, indices);
      yv = gatherF64(yv, indices);
      bv = gatherF64(bv, indices);
      tier = "decimated";
    }
    const xCol = tier === "direct" && t._xCol instanceof Column ? t._xCol : new Column(xv);
    const yCol = tier === "direct" && t._yCol instanceof Column ? t._yCol : new Column(yv);
    if (tier === "direct") {
      t._xCol = xCol;
      t._yCol = yCol;
    }
    const baseCol = new Column(bv);
    const vis = this._visibleSel(t, xv, yv, {
      base: bv,
      baseCol: new Column(t.base),
    });
    if (vis != null) {
      xv = gatherF64(xv, vis);
      yv = gatherF64(yv, vis);
      bv = gatherF64(bv, vis);
    }
    const shipX = vis == null ? xCol : new Column(xv);
    const shipY = vis == null ? yCol : new Column(yv);
    const shipB = vis == null ? baseCol : new Column(bv);
    const entry = {
      id: t.id,
      kind: t.kind === "error_band" ? "error_band" : "area",
      name: t.name,
      // Node payload area copies t.style. Python `_emit_area` uses
      // `_default_styled` to fill palette color when style.color is missing.
      // Matching Python would add style.color. Recorded
      // emit-area-default-styled stay-host.
      style: { ...t.style },
      tier,
      n_points: t.x.length,
      n_marks: xv.length,
      // Node payload area omits ship scale. Python `_base_entry` passes
      // `_axis_scale`. Matching Python would pin log-axis offset to 0.
      // Recorded emit-area-ship-scale stay-host.
      x: pw.ship(xv, shipX),
      y: pw.ship(yv, shipY),
      base: pw.ship(bv, shipB),
      x_axis: t.x_axis ?? "x",
      y_axis: t.y_axis ?? "y",
    };
    if (tier === "decimated") {
      entry.decimation_px = pxWidth;
    }
    // Node payload area omits transition_keys. Python `_emit_area` ships them
    // via `_transition_entry`. Matching Python would add entry.keys.
    // Recorded emit-area-transition stay-host.
    return entry;
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
      // Node payload heatmap ships grid columns. Python `_emit_heatmap` ships
      // a nested heatmap object. Matching Python would nest buf/w/h/colormap.
      // Recorded heatmap-grid stay-host.
      // Node payload heatmap omits color. Python `_emit_heatmap` ships a
      // continuous color spec from the nested colormap/domain. Matching
      // Python would add entry.color. Recorded emit-heatmap-color stay-host.
      x: pw.ship(t.x, xCol),
      y: pw.ship(t.y, yCol),
      grid: pw.ship(t.grid, gridCol),
      grid_shape: t.grid_shape,
      x_axis: t.x_axis ?? "x",
      y_axis: t.y_axis ?? "y",
    };
    if (t.rgba != null) {
      // Node payload heatmap ships rgba_len. Python `_emit_heatmap` ships
      // nested heatmap.rgba_bufs from rgba_grid. Matching Python would nest
      // buffers. Recorded emit-heatmap-rgba stay-host.
      entry.rgba_len = t.rgba.length;
    }
    return entry;
  }

  _emitHexbin(t, pw) {
    const xCol = new Column(t.x);
    const yCol = new Column(t.y);
    let xv = t.x;
    let yv = t.y;
    let mv = t.metric;
    const sel = this._visibleSel(t, xv, yv, { xCol, yCol });
    if (sel != null) {
      xv = gatherF64(xv, sel);
      yv = gatherF64(yv, sel);
      if (mv != null) mv = gatherF64(mv, sel);
    }
    const shipX = sel == null ? xCol : new Column(xv);
    const shipY = sel == null ? yCol : new Column(yv);
    const mCol = new Column(mv);
    return {
      id: t.id,
      kind: "hexbin",
      name: t.name,
      // Node payload hexbin copies t.style. Python `_emit_hexbin` uses
      // `_default_styled` to fill palette color when style.color is missing.
      // Matching Python would add style.color. Recorded
      // emit-hexbin-default-styled stay-host.
      style: { ...t.style },
      tier: "direct",
      n_points: t.n_points ?? t.x.length,
      n_marks: xv.length,
      // Node payload hexbin omits ship scale. Python `_emit_hexbin` passes
      // `_axis_scale` into `ship_values`. Matching Python would pin log-axis
      // offset to 0. Recorded emit-hexbin-ship-scale stay-host.
      x: pw.ship(xv, shipX),
      y: pw.ship(yv, shipY),
      // Node payload hexbin ships metric. Python `_emit_hexbin` ships color
      // from color_ch. Matching Python would call `_shipColor`. Recorded
      // hexbin-metric stay-host.
      metric: pw.ship(mv, mCol),
      x_axis: t.x_axis ?? "x",
      y_axis: t.y_axis ?? "y",
    };
  }

  _shipColor(channel, pw, sel = null) {
    if (channel == null) return undefined;
    if (channel.mode === "direct_rgba" && channel.rgba != null) {
      let rgba = channel.rgba;
      if (sel != null) {
        const out = new Uint8Array(sel.length * 4);
        for (let i = 0; i < sel.length; i += 1) {
          const src = sel[i] * 4;
          const dst = i * 4;
          out[dst] = rgba[src];
          out[dst + 1] = rgba[src + 1];
          out[dst + 2] = rgba[src + 2];
          out[dst + 3] = rgba[src + 3];
        }
        rgba = out;
      }
      return {
        mode: "direct_rgba",
        buf: pw.shipU8(rgba),
        n: Math.floor(rgba.length / 4),
      };
    }
    if (channel.mode === "continuous" && channel.values != null) {
      const values = sel == null ? channel.values : gatherF64(channel.values, sel);
      const domain = channel.domain ?? minMax(values) ?? [0, 1];
      const lo = domain[0];
      const hi = domain[0] === domain[1] ? domain[0] + 1 : domain[1];
      return {
        mode: "continuous",
        colormap: channel.colormap ?? "viridis",
        domain: [lo, hi],
        buf: pw.shipScalar(normalizeF32(values, lo, hi)),
      };
    }
    if (channel.mode === "constant") {
      return { mode: "constant", color: channel.constant };
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
      // Node payload ribbon copies t.style. Python `_emit_ribbon` uses
      // `_default_styled` to fill palette color when style.color is missing.
      // Matching Python would add style.color. Recorded
      // emit-ribbon-default-styled stay-host.
      style: { ...t.style },
      tier: "direct",
      n_points: t.count ?? t.x0.length,
      n_marks: t.x0.length,
      // Node payload ribbon omits ship scale. Python `_emit_ribbon` passes
      // `_axis_scale` into `pw.ship`. Matching Python would pin log-axis
      // offset to 0. Recorded emit-ribbon-ship-scale stay-host.
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
    // Node payload ribbon ships t.color. Python `_emit_ribbon` ships color_ch.
    // Matching Python would ignore t.color. Recorded ribbon-ship-color stay-host.
    const color = this._shipColor(t.color, pw);
    if (color != null) entry.color = color;
    // Node payload ribbon ships t.color_target. Python `_emit_ribbon` ships
    // color2_ch. Matching Python would ignore t.color_target. Recorded
    // ribbon-color-target stay-host.
    const colorTarget = this._shipColor(t.color_target, pw);
    if (colorTarget != null) entry.color_target = colorTarget;
    if (t.tooltip_rows != null) {
      // Node payload ribbon skips tooltip_rows length. Python
      // `_attach_tooltip_rows` rejects a mismatch with n_points. Matching
      // Python would throw. Recorded emit-ribbon-tooltip-len stay-host.
      entry.tooltip_rows = t.tooltip_rows;
    }
    // Node payload ribbon omits stroke_ch. Python `_emit_ribbon` ships
    // stroke_ch via `_ship_trace_styles`. Matching Python would add
    // entry.stroke. Recorded emit-ribbon-stroke stay-host.
    // Node payload ribbon omits style_channels. Python `_emit_ribbon` ships
    // them as `channels` via `_ship_trace_styles`. Matching Python would add
    // entry.channels. Recorded emit-ribbon-channels stay-host.
    // Node payload ribbon skips valid_indices_f64 gather. Python `_emit_ribbon`
    // drops null geometry rows. Matching Python would gather. Recorded
    // emit-ribbon-gather stay-host.
    // Node payload ribbon omits transition_keys. Python `_emit_ribbon` ships
    // them via `_transition_entry`. Matching Python would add entry.keys.
    // Recorded emit-ribbon-transition stay-host.
    return entry;
  }

  _polarAxisSpecs(xr, yr) {
    // Node `??` keeps empty `theta_unit`. Python `_axis_spec` uses
    // `opts.get("theta_unit") or "radians"`. Recorded polar-payload-unit-empty stay-host.
    const unit = figureAutorangeThetaUnit(this.axis_options?.x) ?? "radians";
    const turn = unit === "degrees" ? 360.0 : 2.0 * Math.PI;
    const authoredSector = (this.axis_options?.x ?? {}).sector;
    // Node keeps an empty sector list. Python `_axis_spec` uses
    // `opts.get("sector") or (0.0, turn)`. Recorded polar-payload-sector-empty stay-host.
    const sector = authoredSector != null ? [...authoredSector] : [0.0, turn];
    const yOpts = this.axis_options?.y ?? {};
    const y = {
      range: yr,
      scale: "linear",
      // Node `??` keeps empty `hole`. Python `_axis_spec` uses
      // `opts.get("hole") or 0.0`. Recorded polar-payload-hole-empty stay-host.
      hole: yOpts.hole ?? 0.0,
    };
    if (yOpts.r_origin != null) y.r_origin = yOpts.r_origin;
    return {
      x: {
        range: xr,
        scale: "linear",
        theta_unit: unit,
        theta_zero: (this.axis_options?.x ?? {}).theta_zero ?? "E",
        // Node `??` keeps empty `theta_direction`. Python `_axis_spec` uses
        // `opts.get("theta_direction") or "counterclockwise"`. Recorded
        // polar-payload-dir-empty stay-host.
        theta_direction: (this.axis_options?.x ?? {}).theta_direction ?? "counterclockwise",
        sector,
        // Node `??` keeps empty `grid_shape`. Python `_axis_spec` uses
        // `opts.get("grid_shape") or "circular"`. Recorded
        // polar-payload-grid-empty stay-host.
        grid_shape: (this.axis_options?.x ?? {}).grid_shape ?? "circular",
      },
      y,
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
    if (t.kind === "scatter" && cache?.store) {
      const applied = tileStoreAppend(cache.store, ax, ay);
      if (applied) {
        pyramidUpdate = "dirty-tiles";
      } else {
        cache.free();
        this._pyramids.delete(t.id);
        pyramidUpdate = "invalidate";
      }
    } else if (t.kind === "scatter" && cache?.handle) {
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
        specTraces.push(this._emitSegments(t, pw, widthPx));
      } else if (t.kind === "area" || t.kind === "error_band") {
        specTraces.push(this._emitArea(t, pw, xr, widthPx));
      } else if (t.kind === "bar" || t.kind === "violin" || t.kind === "box") {
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
        // Node cartesian payload axes stay linear. Python `_axis_spec` ships
        // `_axis_scale` when it is not linear. Matching Python would set
        // scale to log. Recorded emit-payload-axis-scale stay-host.
        // Node cartesian payload axes omit id. Python `_axis_spec` ships
        // `id`. Matching Python would add x_axis.id. Recorded
        // emit-payload-axis-id stay-host.
        // Node cartesian payload axes omit kind. Python `_axis_spec` ships
        // `_axis_kind`. Matching Python would add x_axis.kind. Recorded
        // emit-payload-axis-kind stay-host.
        // Node cartesian payload axes omit side. Python `_axis_spec` ships
        // `side`. Matching Python would add x_axis.side. Recorded
        // emit-payload-axis-side stay-host.
        // Node cartesian payload axes omit label. Python `_axis_spec` ships
        // `label`. Matching Python would add x_axis.label. Recorded
        // emit-payload-axis-label stay-host.
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
      // Node payload omits show_legend. Python `build_payload` ships
      // `show_legend`. Matching Python would add spec.show_legend. Recorded
      // emit-payload-show-legend stay-host.
      view: { ranges: { x: [...xr], y: [...yr] } },
    };
    if (this.coords === "polar") {
      spec.coords = "polar";
    }
    if (split) {
      spec.buffer_layout = "split";
    }
    // Node payload omits wasm_density. Python `build_payload` attaches
    // wasm_density from split density.wasm_source. Matching Python would add
    // spec.wasm_density. Recorded emit-payload-wasm-density stay-host.
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

  /** Canonical Rust-owned Scene v5 for the migrated mark subset. */
  toScene(opts = {}) {
    return figureSceneV3(this, opts);
  }

  /** Whole-scene SVG rendered from the canonical Scene v5 document. */
  toSceneSvg(opts = {}) {
    return sceneSvg(this.toScene(opts));
  }

  /** Whole-scene vector PDF from the canonical Scene SVG (Rust `xyg_svg_to_pdf`). */
  toScenePdf(opts = {}) {
    return svgToPdf(this.toSceneSvg(opts));
  }

  /** Existing native-raster display list compiled from Scene v5. */
  toSceneRasterCommands(opts = {}) {
    return sceneRasterCommands(this.toScene(opts), opts.scale ?? 1);
  }
}

export function figure(opts) {
  return new Figure(opts);
}
