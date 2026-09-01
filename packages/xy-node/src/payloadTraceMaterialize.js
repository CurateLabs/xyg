/** ABI 321 trace emit materialize: marshal Trace -> Rust -> PayloadWriter. */

import {
  pointer,
  xyPayloadTraceEmitMaterialize,
} from "./native.js";
import { Column, DEFAULT_PALETTE, f64Ptr, payloadTransitionEntryAttach, payloadVisibleIndices, u8Ptr, u32Ptr } from "./encode.js";
import { clipQuantizeU8, directRgbaAdmit } from "./color.js";

export const PAYLOAD_TRACE_EMIT_MAX_BYTES = 1 << 28;
export const PAYLOAD_TRACE_EMIT_MAX_GEOM = 8;
export const PAYLOAD_TRACE_EMIT_MAX_CHANNELS = 5;
export const PAYLOAD_TRACE_EMIT_PATH_ENTRY = 0;
export const PAYLOAD_TRACE_EMIT_PATH_DENSITY = 1;
export const PAYLOAD_TRACE_EMIT_PATH_RECT_FALLBACK = 2;
export const PAYLOAD_TRACE_EMIT_PATH_HEATMAP_RGBA = 3;
export const PAYLOAD_TRACE_EMIT_PATH_HEATMAP_GRID = 4;

const COL_ATTRS = ["x", "y", "x0", "x1", "y0", "y1", "base"];
const COL_SLOT_BY_REGISTRY = {
  x: "x",
  y: "y",
  x0: "x0",
  x1: "x1",
  y0: "y0",
  y1: "y1",
  x2: "x",
  y2: "y",
  base: "base",
  target_y0: "x",
  target_y1: "y",
  pos: "x",
  value0: "y0",
  value1: "y",
};
const COL_REGISTRY = ["x", "y", "x0", "x1", "y0", "y1", "x2", "y2", "base", "target_y0", "target_y1", "pos", "value0", "value1"];
const CHAN_REGISTRY = ["color", "size", "stroke", "channels", "color_target"];
const COL_DESC_SIZE = 56;
const CHAN_DESC_SIZE = 64;
const EMIT_IN_SIZE = 224;
const EMIT_OUT_SIZE = 200;
const GEOM_OUT_SIZE = 56;
const CHAN_OUT_SIZE = 40;

const TRANSITION_FALLBACK_BY_CODE = [
  null,
  "snap:aggregate",
  "snap:key-limit",
  "index:key-count-mismatch",
];
const AXIS_TYPE = { linear: 0, log: 1, symlog: 2 };
const CHAN_MODE = { constant: 0, continuous: 1, categorical: 2, direct_rgba: 3, match_fill: 4, direct: 5 };

function payloadAxisTypeCode(scale) {
  return AXIS_TYPE[scale] ?? 0;
}

function traceNPoints(t) {
  return t.n_points ?? t.count ?? t.x?.length ?? t.x0?.length ?? 0;
}

/** Mirror Python ColorChannel/SizeChannel/StyleChannel `.spec()` for plain Node objects. */
function traceChannelSpec(ch, role = "color") {
  if (ch == null) {
    return role === "size" ? { mode: "constant" } : { mode: "constant" };
  }
  if (typeof ch.spec === "function") return ch.spec();
  if (ch.mode === "constant") {
    if (role === "color") {
      return { mode: "constant", color: ch.constant ?? ch.color ?? "#3987e5" };
    }
    if (role === "size") {
      return { mode: "constant", size: ch.constant ?? ch.size ?? 4.0 };
    }
    return { mode: "constant" };
  }
  if (ch.mode === "continuous") {
    const out = {
      mode: "continuous",
      domain: ch.domain ? [...ch.domain] : null,
    };
    if (role === "color") {
      out.colormap = ch.colormap ?? "viridis";
      if (ch.label != null) out.label = ch.label;
    }
    if (role === "size" && ch.range_px) out.range_px = [...ch.range_px];
    return out;
  }
  if (ch.mode === "direct_rgba") {
    return { mode: "direct_rgba", components: 4, dtype: "u8" };
  }
  if (ch.mode === "categorical") {
    return { mode: "categorical", categories: ch.categories };
  }
  if (ch.mode === "match_fill") return { mode: "match_fill" };
  if (ch.mode === "direct") {
    return {
      mode: "direct",
      components: ch.components ?? 1,
      dtype: ch.dtype ?? "f32",
    };
  }
  return { mode: ch.mode ?? "constant" };
}

function styleChannelMarkCount(t) {
  if (t.x0 != null) return t.x0.length;
  if (t.x != null) return t.x.length;
  return traceNPoints(t);
}

function styleChannelEntryName(styleChannels) {
  if (styleChannels == null || typeof styleChannels !== "object") return null;
  const keys = Object.keys(styleChannels);
  return keys.length ? keys[0] : null;
}

function styleWireSpec(ch) {
  if (ch == null) return { mode: "direct", components: 1, dtype: "f32" };
  if (typeof ch.spec === "function") return ch.spec();
  if (ch.mode === "direct" || ch.values != null) {
    return {
      mode: "direct",
      components: ch.components ?? 1,
      dtype: ch.dtype ?? "f32",
    };
  }
  if (ch.mode === "constant" || ch.constant != null) {
    return {
      mode: "direct",
      components: ch.components ?? 1,
      dtype: ch.dtype ?? "f32",
    };
  }
  return traceChannelSpec(ch, "color");
}

function rgbaChannelF64(rgba) {
  if (rgba == null) return new Float64Array(0);
  if (rgba instanceof Uint8Array) {
    const out = new Float64Array(rgba.length);
    for (let i = 0; i < rgba.length; i += 1) out[i] = rgba[i] / 255;
    return out;
  }
  if (rgba instanceof Float64Array) return rgba;
  return Float64Array.from(rgba, Number);
}

/** Resolve trace column attrs: raw Float64Array, Column, or column-like object. */
function traceColumnForEmit(raw) {
  if (raw == null) return null;
  if (raw instanceof Column) return raw;
  const values = raw.values;
  if (values instanceof Float64Array
    || (ArrayBuffer.isView(values) && !(values instanceof DataView))) {
    return raw;
  }
  if (ArrayBuffer.isView(raw) && !(raw instanceof DataView)) {
    return new Column(raw);
  }
  if (Array.isArray(raw)) {
    return new Column(raw);
  }
  return null;
}

function traceColumnForEmitAttr(trace, attr) {
  if (attr === "x" && trace._xCol instanceof Column) return trace._xCol;
  if (attr === "y" && trace._yCol instanceof Column) return trace._yCol;
  return traceColumnForEmit(trace[attr]);
}

function traceColumnValues(raw) {
  return traceColumnForEmit(raw)?.values ?? null;
}

function columnDesc(col) {
  if (col == null) {
    return { desc: Buffer.alloc(COL_DESC_SIZE), arr: new Float64Array(0), kind: new Uint8Array(0) };
  }
  const arr = col.values instanceof Float64Array
    ? col.values
    : Float64Array.from(col.values ?? col, Number);
  const kind = new TextEncoder().encode(String(col.kind ?? "float"));
  const desc = Buffer.alloc(COL_DESC_SIZE);
  desc.writeInt32LE(1, 0);
  desc.writeBigUInt64LE(BigInt(arr.length), 8);
  desc.writeDoubleLE(Number(col.min ?? 0), 16);
  desc.writeDoubleLE(Number(col.max ?? 0), 24);
  desc.writeBigUInt64LE(BigInt(col.zone?.nullCount ?? col.nullCount ?? 0), 32);
  desc.writeDoubleLE(Number(col.suggestOffset?.() ?? col.suggest_offset?.() ?? 0), 40);
  desc.writeBigUInt64LE(BigInt(kind.length), 48);
  return { desc, arr, kind };
}

function styleWireChannel(ch) {
  if (ch == null) return null;
  if (typeof ch === "object" && !Object.hasOwn(ch, "mode")) {
    const keys = Object.keys(ch);
    if (keys.length === 0) return null;
    return ch[keys[0]];
  }
  return ch;
}

function channelDesc(ch, nPoints = 0) {
  ch = styleWireChannel(ch);
  const empty = {
    desc: Buffer.alloc(CHAN_DESC_SIZE),
    f64: new Float64Array(0),
    u8: new Uint8Array(0),
  };
  if (ch == null || (typeof ch === "object" && Object.keys(ch).length === 0)) {
    return empty;
  }
  let mode;
  let f64 = new Float64Array(0);
  let u8 = new Uint8Array(0);
  if (ch.mode == null && ch.values != null) {
    mode = CHAN_MODE.direct;
    f64 = ch.values instanceof Float64Array ? ch.values : Float64Array.from(ch.values, Number);
  } else if (ch.mode === "constant" && ch.constant != null && nPoints > 0) {
    mode = CHAN_MODE.direct;
    f64 = new Float64Array(nPoints).fill(Number(ch.constant));
  } else if (ch.mode === "direct_rgba" && (ch.rgba != null || ch.values != null)) {
    mode = CHAN_MODE.direct_rgba;
    const source = ch.rgba ?? ch.values;
    const packed = source instanceof Uint8Array
      ? source
      : clipQuantizeU8(directRgbaAdmit(rgbaChannelF64(source), 4));
    f64 = rgbaChannelF64(packed);
  } else if (ch.mode === "direct_rgba") {
    mode = CHAN_MODE.direct_rgba;
  } else {
    mode = CHAN_MODE[ch.mode] ?? 0;
    if (ch.mode === "continuous" && ch.values != null) {
      f64 = ch.values instanceof Float64Array ? ch.values : Float64Array.from(ch.values, Number);
    } else if (ch.mode === "categorical" && ch.codes != null) {
      u8 = ch.codes instanceof Uint8Array ? ch.codes : Uint8Array.from(ch.codes, (v) => Number(v) & 0xff);
    } else if ((ch.mode === "direct_rgba" || ch.mode === "direct") && ch.values != null) {
      f64 = ch.values instanceof Float64Array ? ch.values : Float64Array.from(ch.values, Number);
    }
  }
  const desc = Buffer.alloc(CHAN_DESC_SIZE);
  const dom = ch.domain ?? [0, 1];
  desc.writeInt32LE(1, 0);
  desc.writeInt32LE(mode, 4);
  desc.writeBigUInt64LE(BigInt((ch.categories ?? []).length), 8);
  desc.writeDoubleLE(Number(dom[0]), 16);
  desc.writeDoubleLE(Number(dom[1]), 24);
  desc.writeBigUInt64LE(BigInt(f64.length), 32);
  desc.writeBigUInt64LE(BigInt(u8.length), 40);
  desc.writeInt32LE(ch.dtype === "u8" ? 1 : 0, 48);
  desc.writeBigUInt64LE(0n, 56);
  return { desc, f64, u8 };
}

function traceGridValues(grid) {
  if (grid == null) return null;
  if (grid instanceof Column) {
    return grid.values;
  }
  const values = grid.values;
  if (values instanceof Float64Array
    || (ArrayBuffer.isView(values) && !(values instanceof DataView))) {
    return values instanceof Float64Array ? values : Float64Array.from(values, Number);
  }
  if (ArrayBuffer.isView(grid) && !(grid instanceof DataView)) {
    return grid;
  }
  return Float64Array.from(grid, Number);
}

/** Pack `XygPayloadTraceEmitIn` (repr(C), 224 bytes) — offsets match Rust/Python ctypes. */
function writeEmitIn(view, fields) {
  view.setBigUint64(0, BigInt(fields.kindLen), true);
  view.setBigUint64(8, BigInt(fields.nPoints), true);
  view.setBigUint64(16, BigInt(fields.segmentCount), true);
  view.setInt32(24, fields.polar, true);
  view.setInt32(28, fields.forceDensity, true);
  view.setInt32(32, fields.perItem, true);
  view.setInt32(36, fields.xAxisType, true);
  view.setInt32(40, fields.yAxisType, true);
  view.setBigUint64(48, BigInt(fields.xAxisScaleLen), true);
  view.setBigUint64(56, BigInt(fields.yAxisScaleLen), true);
  view.setFloat64(64, fields.xr0, true);
  view.setFloat64(72, fields.xr1, true);
  view.setUint32(80, fields.pxWidth, true);
  view.setInt32(84, fields.styleColorIsNone, true);
  view.setInt32(88, fields.hasTraceAnimation, true);
  view.setInt32(92, fields.hasTransitionKeys, true);
  view.setInt32(96, fields.hasTooltipRows, true);
  view.setBigUint64(104, BigInt(fields.nTooltipRows), true);
  view.setBigUint64(112, BigInt(fields.orientationLen), true);
  view.setInt32(120, fields.hasColor2Ch, true);
  view.setInt32(124, fields.hasColorCh, true);
  view.setInt32(128, fields.hasStrokeCh, true);
  view.setInt32(132, fields.hasStyleChannels, true);
  view.setUint32(136, fields.heatmapRows, true);
  view.setUint32(140, fields.heatmapCols, true);
  view.setInt32(144, fields.hasRgbaGrid, true);
  view.setInt32(148, fields.borrowHeatmaps, true);
  view.setInt32(152, fields.styleColormapIsNone, true);
  view.setBigUint64(160, BigInt(fields.gridValuesLen), true);
  view.setFloat64(168, fields.gridDomainLo, true);
  view.setFloat64(176, fields.gridDomainHi, true);
  view.setBigUint64(184, BigInt(fields.maxRows), true);
  view.setBigUint64(192, BigInt(fields.binXLen), true);
  view.setFloat64(200, fields.binX0, true);
  view.setFloat64(208, fields.binX1, true);
  view.setBigUint64(216, BigInt(fields.transitionKeysLen), true);
}

/** @param {import("./figure.js").Figure} figure */
export function emitTraceMaterialized(figure, t, pw, xr, yr, pxWidth) {
  const kindB = new TextEncoder().encode(String(t.kind));
  const xScaleB = new TextEncoder().encode(figureAxisScale(figure, t.x_axis ?? "x"));
  const yScaleB = new TextEncoder().encode(figureAxisScale(figure, t.y_axis ?? "y"));
  const orientB = new TextEncoder().encode(String(t.style?.orientation ?? "vertical"));
  const nPoints = traceNPoints(t);
  const colDescs = Buffer.alloc(COL_DESC_SIZE * 7);
  const colValuePtrs = [];
  const colKindPtrs = [];
  const colKinds = [];
  const colKindBySlot = {};
  for (let i = 0; i < COL_ATTRS.length; i += 1) {
    const attr = COL_ATTRS[i];
    const col = traceColumnForEmitAttr(t, attr);
    const { desc, arr, kind } = columnDesc(col);
    desc.copy(colDescs, i * COL_DESC_SIZE);
    colValuePtrs.push(arr.length ? arr : null);
    colKindPtrs.push(kind.length ? kind : null);
    colKinds.push(kind);
    colKindBySlot[attr] = kind;
  }
  const chMap = {
    color: channelDesc(t.color_ch),
    stroke: channelDesc(t.stroke_ch),
    color2: channelDesc(t.color2_ch),
    size: channelDesc(t.size_ch),
    style: channelDesc(t.style_channels, styleChannelMarkCount(t)),
  };
  let transitionLo = null;
  let transitionHi = null;
  if (t.transition_keys != null) {
    transitionLo = new Uint32Array(t.transition_keys.length);
    transitionHi = new Uint32Array(t.transition_keys.length);
    for (let i = 0; i < t.transition_keys.length; i += 1) {
      transitionLo[i] = Number(t.transition_keys[i][0]) >>> 0;
      transitionHi[i] = Number(t.transition_keys[i][1]) >>> 0;
    }
  }
  let binXArr = null;
  let binX0 = 0;
  let binX1 = 0;
  if (t.kind === "line" || t.kind === "area" || t.kind === "error_band") {
    const xValues = traceColumnValues(t.x);
    const bx = figure._binningCoords(t.x_axis ?? "x", xValues, xr);
    binX0 = bx.b0;
    binX1 = bx.b1;
    if (bx.values !== xValues) {
      binXArr = bx.values instanceof Float64Array ? bx.values : Float64Array.from(bx.values, Number);
    }
  }
  let gridArr = null;
  let domain = [0, 1];
  if (t.kind === "heatmap" && t.grid != null) {
    gridArr = traceGridValues(t.grid);
    domain = t.style?.domain ?? [0, 1];
  }
  const emitIn = Buffer.alloc(EMIT_IN_SIZE);
  writeEmitIn(new DataView(emitIn.buffer, emitIn.byteOffset, emitIn.byteLength), {
    kindLen: kindB.length,
    nPoints,
    segmentCount: t.count ?? 0,
    polar: figure.coords === "polar" ? 1 : 0,
    forceDensity: scatterPayloadForceDensity(t),
    perItem: t.has_per_item_channels?.() ? 1 : 0,
    xAxisType: payloadAxisTypeCode(xScaleB.length ? new TextDecoder().decode(xScaleB) : "linear"),
    yAxisType: payloadAxisTypeCode(yScaleB.length ? new TextDecoder().decode(yScaleB) : "linear"),
    xAxisScaleLen: xScaleB.length,
    yAxisScaleLen: yScaleB.length,
    xr0: xr[0],
    xr1: xr[1],
    pxWidth,
    styleColorIsNone: t.style?.color == null ? 1 : 0,
    hasTraceAnimation: t.animation != null ? 1 : 0,
    hasTransitionKeys: t.transition_keys != null ? 1 : 0,
    hasTooltipRows: t.tooltip_rows != null ? 1 : 0,
    nTooltipRows: t.tooltip_rows?.length ?? 0,
    orientationLen: orientB.length,
    hasColor2Ch: t.color2_ch != null ? 1 : 0,
    hasColorCh: t.color_ch != null ? 1 : 0,
    hasStrokeCh: t.stroke_ch != null ? 1 : 0,
    hasStyleChannels: t.style_channels && Object.keys(t.style_channels).length ? 1 : 0,
    heatmapRows: t.grid_shape?.[0] ?? 0,
    heatmapCols: t.grid_shape?.[1] ?? 0,
    hasRgbaGrid: t.rgba_grid != null ? 1 : 0,
    borrowHeatmaps: pw.borrowHeatmaps ? 1 : 0,
    styleColormapIsNone: t.style?.colormap == null ? 1 : 0,
    gridValuesLen: gridArr?.length ?? 0,
    gridDomainLo: domain[0],
    gridDomainHi: domain[1],
    maxRows: 200_000,
    binXLen: binXArr?.length ?? 0,
    binX0,
    binX1,
    transitionKeysLen: transitionLo?.length ?? 0,
  });
  const summary = Buffer.alloc(EMIT_OUT_SIZE);
  const geomOut = Buffer.alloc(GEOM_OUT_SIZE * PAYLOAD_TRACE_EMIT_MAX_GEOM);
  const chanOut = Buffer.alloc(CHAN_OUT_SIZE * PAYLOAD_TRACE_EMIT_MAX_CHANNELS);
  const outBytes = new Uint8Array(PAYLOAD_TRACE_EMIT_MAX_BYTES);
  const outLen = new BigUint64Array(1);
  const code = Number(xyPayloadTraceEmitMaterialize(
    u8Ptr(emitIn),
    kindB.length ? u8Ptr(kindB) : 0,
    xScaleB.length ? u8Ptr(xScaleB) : 0,
    yScaleB.length ? u8Ptr(yScaleB) : 0,
    orientB.length ? u8Ptr(orientB) : 0,
    u8Ptr(colDescs),
    colValuePtrs,
    colKindPtrs,
    u8Ptr(chMap.color.desc),
    u8Ptr(chMap.stroke.desc),
    u8Ptr(chMap.color2.desc),
    u8Ptr(chMap.size.desc),
    u8Ptr(chMap.style.desc),
    chMap.color.f64.length ? f64Ptr(chMap.color.f64) : 0,
    chMap.stroke.f64.length ? f64Ptr(chMap.stroke.f64) : 0,
    chMap.color2.f64.length ? f64Ptr(chMap.color2.f64) : 0,
    chMap.size.f64.length ? f64Ptr(chMap.size.f64) : 0,
    chMap.style.f64.length ? f64Ptr(chMap.style.f64) : 0,
    chMap.color.u8.length ? u8Ptr(chMap.color.u8) : 0,
    chMap.stroke.u8.length ? u8Ptr(chMap.stroke.u8) : 0,
    chMap.color2.u8.length ? u8Ptr(chMap.color2.u8) : 0,
    chMap.size.u8.length ? u8Ptr(chMap.size.u8) : 0,
    chMap.style.u8.length ? u8Ptr(chMap.style.u8) : 0,
    transitionLo?.length ? u32Ptr(transitionLo) : 0,
    transitionHi?.length ? u32Ptr(transitionHi) : 0,
    binXArr?.length ? f64Ptr(binXArr) : 0,
    gridArr?.length ? f64Ptr(gridArr) : 0,
    u8Ptr(summary),
    u8Ptr(geomOut),
    BigInt(PAYLOAD_TRACE_EMIT_MAX_GEOM),
    u8Ptr(chanOut),
    BigInt(PAYLOAD_TRACE_EMIT_MAX_CHANNELS),
    u8Ptr(outBytes),
    BigInt(outBytes.length),
    pointer(outLen, "size_t *"),
  ));
  if (code !== 0) {
    throw new RangeError(`payload_trace_emit_materialize failed (${code}) for kind ${t.kind}`);
  }
  const blob = outBytes.subarray(0, Number(outLen[0]));
  const sv = new DataView(summary.buffer, summary.byteOffset, summary.byteLength);
  const path = sv.getInt32(0, true);
  if (path === PAYLOAD_TRACE_EMIT_PATH_DENSITY) {
    if (sv.getInt32(44, true)) t.shipped_sel = null;
    if (sv.getInt32(52, true)) t.drill_mode = false;
    let entry = figure._emitScatterDensity(t, pw, xr, yr);
    if (sv.getInt32(28, true)) {
      entry = attachTransitionEntry(entry, t, pw);
    }
    return entry;
  }
  if (path === PAYLOAD_TRACE_EMIT_PATH_RECT_FALLBACK) {
    const saved = t.kind;
    t.kind = "rect";
    try {
      return emitTraceMaterialized(figure, t, pw, xr, yr, pxWidth);
    } finally {
      t.kind = saved;
    }
  }
  const tier = sv.getInt32(4, true) === 0 ? "direct" : "decimated";
  const style = { ...(t.style ?? {}) };
  if (sv.getInt32(20, true)) {
    style.color = DEFAULT_PALETTE[t.id % DEFAULT_PALETTE.length];
  }
  const entry = {
    id: t.id,
    kind: t.kind,
    name: t.name,
    style,
    tier,
    n_points: nPoints,
    n_marks: Number(sv.getBigUint64(8, true)),
    x_axis: t.x_axis ?? "x",
    y_axis: t.y_axis ?? "y",
  };
  const decPx = sv.getUint32(16, true);
  if (decPx) entry.decimation_px = decPx;
  if (sv.getInt32(24, true) && t.animation != null) entry.animation = { ...t.animation };
  let target = entry;
  if (sv.getInt32(112, true)) {
    const barSpec = {
      orientation: sv.getInt32(116, true) === 0 ? "vertical" : "horizontal",
      value_axis: sv.getInt32(120, true) === 0 ? "y" : "x",
      width: sv.getFloat64(128, true),
    };
    if (sv.getInt32(136, true)) barSpec.value0_const = sv.getFloat64(144, true);
    entry.bar = barSpec;
    target = barSpec;
  }
  const nGeom = Number(sv.getBigUint64(64, true));
  for (let i = 0; i < nGeom; i += 1) {
    const base = i * GEOM_OUT_SIZE;
    const gv = new DataView(geomOut.buffer, geomOut.byteOffset + base, GEOM_OUT_SIZE);
    const key = COL_REGISTRY[gv.getInt32(0, true)];
    const dtypeCode = gv.getInt32(8, true);
    const bytesOffset = Number(gv.getBigUint64(40, true));
    const bytesLen = Number(gv.getBigUint64(48, true));
    const raw = blob.subarray(bytesOffset, bytesOffset + bytesLen);
    const enc = dtypeCode === 1
      ? new Float64Array(raw.buffer, raw.byteOffset, raw.byteLength / 8)
      : new Float32Array(raw.buffer, raw.byteOffset, raw.byteLength / 4);
    const meta = { len: gv.getUint32(36, true) };
    if (dtypeCode === 1) meta.dtype = "f64";
    else {
      meta.offset = gv.getFloat64(16, true);
      meta.scale = gv.getFloat64(24, true);
      if (gv.getInt32(32, true)) {
        const slot = COL_SLOT_BY_REGISTRY[key] ?? "x";
        meta.kind = new TextDecoder().decode(colKindBySlot[slot] ?? new Uint8Array(0));
      }
    }
    const colIdx = pw._appendFromMaterialized(enc, meta);
    target[key] = gv.getInt32(4, true)
      ? { col: colIdx, ...pw.columns[colIdx] }
      : colIdx;
  }
  const nChan = Number(sv.getBigUint64(72, true));
  for (let i = 0; i < nChan; i += 1) {
    const base = i * CHAN_OUT_SIZE;
    const cv = new DataView(chanOut.buffer, chanOut.byteOffset + base, CHAN_OUT_SIZE);
    const key = CHAN_REGISTRY[cv.getInt32(0, true)];
    const bufKind = cv.getInt32(4, true);
    if (bufKind === 0) {
      if (key === "color") entry.color = traceChannelSpec(t.color_ch, "color");
      else if (key === "size") entry.size = traceChannelSpec(t.size_ch, "size");
      else if (key === "stroke") entry.stroke = traceChannelSpec(t.stroke_ch, "color");
      else if (key === "channels") {
        const styleName = styleChannelEntryName(t.style_channels);
        const wire = styleWireChannel(t.style_channels);
        if (styleName != null && wire != null) {
          entry.channels = { [styleName]: styleWireSpec(wire) };
        }
      } else if (key === "color_target") {
        entry.color_target = traceChannelSpec(t.color2_ch, "color");
      }
      continue;
    }
    const bytesOffset = Number(cv.getBigUint64(24, true));
    const bytesLen = Number(cv.getBigUint64(32, true));
    const raw = blob.subarray(bytesOffset, bytesOffset + bytesLen);
    const buf = bufKind === 1
      ? pw.shipU8(new Uint8Array(raw))
      : pw.shipScalar(new Float32Array(raw.buffer, raw.byteOffset, raw.byteLength / 4));
    const spec = { buf };
    if (cv.getInt32(8, true)) spec.dtype = "u8";
    if (cv.getInt32(12, true)) {
      const cc = t.color_ch;
      const cats = cc?.categories ?? [];
      const palette = cc?.palette ?? cc?.colors;
      spec.palette = cc && Array.isArray(cats) && palette
        ? Array.from({ length: cats.length }, (_, i) => palette[i % palette.length])
        : true;
    }
    if (cv.getInt32(16, true)) spec.n = cv.getUint32(20, true);
    if (key === "color") {
      entry.color = { ...traceChannelSpec(t.color_ch, "color"), ...spec };
    } else if (key === "size") {
      entry.size = { ...traceChannelSpec(t.size_ch, "size"), ...spec };
    } else if (key === "stroke") {
      entry.stroke = { ...traceChannelSpec(t.stroke_ch, "color"), ...spec };
    } else if (key === "channels") {
      const styleName = styleChannelEntryName(t.style_channels);
      const wire = styleWireChannel(t.style_channels);
      const channelSpec = wire != null ? { ...styleWireSpec(wire), ...spec } : spec;
      if (styleName != null) entry.channels = { [styleName]: channelSpec };
      else entry.channels = channelSpec;
    } else if (key === "color_target") {
      entry.color_target = { ...traceChannelSpec(t.color2_ch, "color"), ...spec };
    }
  }
  const loLen = Number(sv.getBigUint64(88, true));
  if (sv.getInt32(28, true) && loLen) {
    const loOff = Number(sv.getBigUint64(80, true));
    const hiOff = Number(sv.getBigUint64(96, true));
    const hiLen = Number(sv.getBigUint64(104, true));
    const lo = new Uint32Array(blob.buffer, blob.byteOffset + loOff, loLen / 4);
    const hi = new Uint32Array(blob.buffer, blob.byteOffset + hiOff, hiLen / 4);
    if (!sv.getInt32(24, true)) {
      entry.keys = { lo: pw.shipU32(lo), hi: pw.shipU32(hi) };
    } else {
      entry.keys = entry.keys ?? {};
      entry.keys.lo = pw.shipU32(lo);
      entry.keys.hi = pw.shipU32(hi);
    }
  } else if (sv.getInt32(28, true) && sv.getInt32(60, true)) {
    entry.animation_fallback = TRANSITION_FALLBACK_BY_CODE[sv.getInt32(60, true)] ?? null;
  }
  let sel = null;
  if (sv.getInt32(48, true) || sv.getInt32(36, true)) {
    const xv = traceColumnValues(t.x);
    const yv = traceColumnValues(t.y);
    const baseCol = traceColumnForEmit(t.base);
    sel = visibleSel(figure, t, xv, yv, {
      base: baseCol?.values ?? null,
      prefiltered: sv.getInt32(4, true) !== 0,
      baseCol,
    });
  }
  if (sv.getInt32(32, true)) {
    entry.tooltip_rows = sv.getInt32(36, true)
      ? (sel ?? []).map((i) => ({ ...t.tooltip_rows[i] }))
      : t.tooltip_rows.map((row) => ({ ...row }));
  } else if (t.tooltip_rows != null && !sv.getInt32(40, true)) {
    throw new RangeError(`${t.kind} tooltip rows must match geometry`);
  }
  if (path === PAYLOAD_TRACE_EMIT_PATH_HEATMAP_RGBA) {
    entry.heatmap = {
      rgba_bufs: t.rgba_grid.map((column) => pw.shipScalar(column.values ?? column)),
      w: t.grid_shape[1],
      h: t.grid_shape[0],
      x_range: [...t.style.x_range],
      y_range: [...t.style.y_range],
    };
    return entry;
  }
  if (path === PAYLOAD_TRACE_EMIT_PATH_HEATMAP_GRID && sv.getInt32(160, true)) {
    const rows = t.grid_shape[0];
    const cols = t.grid_shape[1];
    const gridOff = Number(sv.getBigUint64(184, true));
    const gridLen = Number(sv.getBigUint64(192, true));
    let bufIdx;
    let encoding;
    if (sv.getInt32(180, true)) {
      bufIdx = pw.borrowF64(t.grid.values ?? t.grid);
      encoding = "canonical-f64";
    } else {
      const raw = blob.subarray(gridOff, gridOff + gridLen);
      bufIdx = pw.shipScalar(new Float32Array(raw.buffer, raw.byteOffset, raw.byteLength / 4));
      encoding = null;
    }
    let cmap = t.style?.colormap;
    if (sv.getInt32(172, true) && cmap == null) {
      cmap = [[0.22, 0.53, 0.9], [0.22, 0.53, 0.9]];
    }
    entry.heatmap = {
      buf: bufIdx,
      w: cols,
      h: rows,
      x_range: [...t.style.x_range],
      y_range: [...t.style.y_range],
      colormap: cmap,
      domain: [...domain],
      ...(sv.getInt32(176, true) && encoding ? { enc: encoding } : {}),
    };
    if (sv.getInt32(172, true)) {
      entry.color = { mode: "continuous", colormap: cmap, domain: [...domain] };
    }
    return entry;
  }
  if (sv.getInt32(48, true)) t.shipped_sel = sel;
  return entry;
}

function scatterPayloadForceDensity(trace) {
  const v = (trace ?? {}).force_density;
  if (v === true) return 1;
  if (v === false) return 0;
  return -1;
}

function figureAxisScale(figure, axisId) {
  const scale = figure.axis_options?.[axisId]?.type;
  return scale === "log" || scale === "symlog" ? scale : "linear";
}

function axisIsLog(figure, axisId) {
  if (typeof figure._axisIsLog === "function") {
    return figure._axisIsLog(axisId);
  }
  return figureAxisScale(figure, axisId) === "log";
}

function visibleSel(figure, t, xv, yv, { base = null, prefiltered = false, baseCol = null } = {}) {
  const xCol = traceColumnForEmit(t.x);
  const yCol = traceColumnForEmit(t.y);
  const { keepAll, indices } = payloadVisibleIndices(xv, yv, {
    xLog: axisIsLog(figure, t.x_axis ?? "x"),
    yLog: axisIsLog(figure, t.y_axis ?? "y"),
    base,
    prefiltered,
    xHasNulls: (xCol?.zone?.nullCount ?? xCol?.nullCount ?? 0) > 0,
    yHasNulls: (yCol?.zone?.nullCount ?? yCol?.nullCount ?? 0) > 0,
    hasBase: base != null || baseCol != null,
    baseHasNulls: baseCol != null ? (baseCol.zone?.nullCount ?? baseCol.nullCount ?? 0) > 0 : false,
  });
  return keepAll ? null : indices;
}

function attachTransitionEntry(entry, t, pw) {
  const plan = payloadTransitionEntryAttach({
    hasTraceAnimation: t.animation != null,
    entryHasAnimation: Object.prototype.hasOwnProperty.call(entry, "animation"),
    hasTraceKeys: t.transition_keys != null,
    hasKeyValues: false,
    hasSel: false,
    tierDirect: entry.tier === "direct",
    nMarks: entry.n_marks ?? 0,
    nTraceKeyRows: t.transition_keys?.length ?? 0,
    nKeyValueRows: 0,
    nSelRows: 0,
    maxRows: 200_000,
    hasTooltipRows: false,
    nTooltipRows: 0,
    nPoints: entry.n_points ?? 0,
  });
  if (plan.attachAnimation && t.animation != null) {
    entry.animation = { ...t.animation };
  }
  if (!plan.attemptKeys) return entry;
  const keys = t.transition_keys;
  if (!plan.shipKeys) {
    entry.animation_fallback = plan.animationFallback;
    return entry;
  }
  const lo = new Uint32Array(keys.length);
  const hi = new Uint32Array(keys.length);
  for (let i = 0; i < keys.length; i += 1) {
    lo[i] = Number(keys[i][0]) >>> 0;
    hi[i] = Number(keys[i][1]) >>> 0;
  }
  entry.keys = { lo: pw.shipU32(lo), hi: pw.shipU32(hi) };
  return entry;
}
