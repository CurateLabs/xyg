/** Thin Node adapter for the versioned Rust-owned canonical scene IR. */
import {
  pointer,
  xySceneAxisTicks,
  xySceneTickLabelLayout,
  xyTickWindow,
  xyTickWindowFilter,
  xyTickFormat,
  xyLegendBoxLayout,
  xyTextBlockMeasure,
  xyTextBlockRotatedExtent,
  xyYTickLabelExtent,
  xyYAxisLeftRoom,
  xyXAxisTitleRoom,
  xyXTickLabelRoom,
  xyXTickLabelEdgeRooms,
  xyCompatIsCompact,
  xyCompatDefaultPadding,
  xyCompatTitleWrapWidth,
  xyCompatTitleRoom,
  xyCompatXAxisSideRoom,
  xyCompatColorbarExtra,
  xyCompatRightYRoom,
  xyPolarLegendRoom,
  xyPolarLegendReserve,
  xyPolarLabelRoom,
  xyPolarLayout,
  xyPolarProject,
  xyRecutPolarPlot,
  xyTightLayoutSolve,
  xySceneBatchEncode,
  xySceneBrowserPainter,
  xyScenePackAnnotations,
  xyScenePackColorbar,
  xyScenePackLegend,
  xyScenePlotLayout,
  xyScenePublicExportReason,
  xySceneFigureSupportReason,
  xyScenePackTrace,
  xyScenePackAnnotationMarks,
  xySceneRasterCommands,
  xySceneResolveChromeStyle,
  xySceneResolveMarkStyles,
  xySceneScaleMap,
  xySceneScatterSvg,
  xySceneSupportReason,
  xySceneSvg,
  xySvgToPdf,
  xyEncodeJpeg,
  xyEncodePng,
  xyEncodeWebp,
  xySceneVersion,
  polarAbiInputPointer,
} from "./native.js";
import { asF64Array, f64Ptr, legendBestLoc, legendNormalize, shouldUseDensity, u32Ptr, u8Ptr } from "./encode.js";
import { cssColorRgba8 } from "./color.js";

const USIZE_MAX_64 = (1n << 64n) - 1n;
const MAX_SCENE_MARKS = 2_000_000;
const MAX_SCENE_STYLES = 65_536;
const MAX_SCENE_TEXT_BYTES = 4_096;
const SYMBOL_CODES = new Map([
  "circle", "square", "diamond", "triangle", "cross", "hexagon", "pentagon", "star",
  "triangle_down", "triangle_left", "triangle_right", "x", "point", "pixel",
  "thin_diamond", "plus_line", "x_line", "horizontal_line", "vertical_line",
].map((name, code) => [name, code]));

function columnArg(column) {
  if (column == null || column.length === 0) return { ptr: 0, n: 0, keep: null };
  const arr = asF64Array(column, "trace column");
  return { ptr: f64Ptr(arr), n: arr.length, keep: arr };
}

function packTrace({
  packKind, flags = 0, stepMode = 0, symbol = 0, styleRef = 0, traceId = 0,
  diameter = 0, extra0 = 0, extra1 = 0, columns = [],
}) {
  const packedCols = [...columns];
  while (packedCols.length < 6) packedCols.push(null);
  const args = packedCols.slice(0, 6).map(columnArg);
  const packedId = asU64(traceId, "stableIds value");
  const n0 = args[0].n;
  const nRows = packKind === 4 || packKind === 5 ? n0 * 2 : packKind === 7 ? 2 : n0;
  const out = new Uint8Array(Math.max(nRows, 1) * 56);
  const code = xyScenePackTrace(
    packKind, flags, stepMode, symbol, styleRef, packedId,
    Number(diameter), Number(extra0), Number(extra1),
    args[0].ptr, BigInt(args[0].n),
    args[1].ptr, BigInt(args[1].n),
    args[2].ptr, BigInt(args[2].n),
    args[3].ptr, BigInt(args[3].n),
    args[4].ptr, BigInt(args[4].n),
    args[5].ptr, BigInt(args[5].n),
    u8Ptr(out), BigInt(out.length),
  );
  if (code === -5) throw new RangeError("Scene v12 does not yet encode missing-data breaks or nonfinite coordinates");
  if (code < 0) throw new RangeError("invalid scene trace packing");
  const view = new DataView(out.buffer, out.byteOffset, Math.max(code, 0) * 56);
  const rows = { kinds: [], stableIds: [], styleRefs: [], diameter: [], symbols: [], expansion: [], x0: [], y0: [], x1: [], y1: [] };
  for (let index = 0; index < code; index += 1) {
    const at = index * 56;
    rows.kinds.push(out[at]);
    rows.symbols.push(out[at + 1]);
    rows.expansion.push(out[at + 2]);
    rows.styleRefs.push(view.getUint32(at + 4, true));
    rows.stableIds.push(view.getBigUint64(at + 8, true));
    rows.diameter.push(view.getFloat64(at + 16, true));
    rows.x0.push(view.getFloat64(at + 24, true));
    rows.y0.push(view.getFloat64(at + 32, true));
    rows.x1.push(view.getFloat64(at + 40, true));
    rows.y1.push(view.getFloat64(at + 48, true));
  }
  return rows;
}

function packAnnotationMarks(rowBytes, xDomain, yDomain) {
  const source = rowBytes instanceof Uint8Array ? rowBytes : new Uint8Array(rowBytes ?? []);
  const nIn = Math.floor(source.length / 40);
  const out = new Uint8Array(Math.max(nIn * 2, 1) * 56);
  const code = xyScenePackAnnotationMarks(
    source.length ? u8Ptr(source) : 0,
    BigInt(source.length),
    Number(xDomain[0]),
    Number(xDomain[1]),
    Number(yDomain[0]),
    Number(yDomain[1]),
    u8Ptr(out),
    BigInt(out.length),
  );
  if (code === -5) throw new RangeError("Scene v12 annotation geometry must be finite");
  if (code < 0) throw new RangeError("invalid scene annotation packing");
  const view = new DataView(out.buffer, out.byteOffset, Math.max(code, 0) * 56);
  const rows = { kinds: [], stableIds: [], styleRefs: [], diameter: [], symbols: [], expansion: [], x0: [], y0: [], x1: [], y1: [] };
  for (let index = 0; index < code; index += 1) {
    const at = index * 56;
    rows.kinds.push(out[at]);
    rows.symbols.push(out[at + 1]);
    rows.expansion.push(out[at + 2]);
    rows.styleRefs.push(view.getUint32(at + 4, true));
    rows.stableIds.push(view.getBigUint64(at + 8, true));
    rows.diameter.push(view.getFloat64(at + 16, true));
    rows.x0.push(view.getFloat64(at + 24, true));
    rows.y0.push(view.getFloat64(at + 32, true));
    rows.x1.push(view.getFloat64(at + 40, true));
    rows.y1.push(view.getFloat64(at + 48, true));
  }
  return rows;
}

function annotationMarkRow(kind, axis, symbol, styleRef, index, value0, value1, size) {
  const row = new Uint8Array(40);
  const view = new DataView(row.buffer);
  row[0] = kind;
  row[1] = axis;
  row[2] = symbol;
  view.setUint32(4, styleRef >>> 0, true);
  view.setUint32(8, index >>> 0, true);
  view.setFloat64(16, Number(value0), true);
  view.setFloat64(24, Number(value1), true);
  view.setFloat64(32, Number(size), true);
  return row;
}

function appendPacked(kinds, stableIds, styleRefs, diameter, symbols, expansionModes, x0, y0, x1, y1, packed) {
  kinds.push(...packed.kinds);
  stableIds.push(...packed.stableIds);
  styleRefs.push(...packed.styleRefs);
  diameter.push(...packed.diameter);
  symbols.push(...packed.symbols);
  expansionModes.push(...packed.expansion);
  x0.push(...packed.x0);
  y0.push(...packed.y0);
  x1.push(...packed.x1);
  y1.push(...packed.y1);
}

function sceneSymbolCode(value) {
  if (typeof value === "string") {
    const code = SYMBOL_CODES.get(value);
    if (code == null) throw new RangeError(`Scene v12 does not support scatter symbol ${JSON.stringify(value)}`);
    return code;
  }
  if (!Number.isInteger(value) || value < 0 || value >= SYMBOL_CODES.size) {
    throw new RangeError("Scene v12 scatter symbol code must be an integer from 0 through 18");
  }
  return value;
}

function annotationSymbolCode(value) {
  if (typeof value !== "string") {
    throw new RangeError("Scene v12 annotation marker symbol must be a supported string name");
  }
  return sceneSymbolCode(value);
}

function asU8Array(value, name) {
  if (value instanceof Uint8Array) return value;
  if (value == null) return new Uint8Array(0);
  try {
    return Uint8Array.from(value, (item) => Number(item));
  } catch (error) {
    throw new TypeError(`${name} must be an array-like byte sequence`, { cause: error });
  }
}

function asUnsignedArray(value, name, max, TypedArray) {
  if (value instanceof TypedArray) return value;
  let items;
  try {
    items = Array.from(value);
  } catch (error) {
    throw new TypeError(`${name} must be an array-like unsigned integer sequence`, { cause: error });
  }
  for (const item of items) {
    if (typeof item !== "number" || !Number.isInteger(item) || item < 0 || item > max) {
      throw new RangeError(`${name} values must be integers from 0 through ${max}`);
    }
  }
  return TypedArray.from(items);
}

function asU64(value, name) {
  if (typeof value === "bigint") {
    if (value < 0n || value > USIZE_MAX_64) throw new RangeError(`${name} must be an unsigned 64-bit integer`);
    return value;
  }
  if (typeof value !== "number" || !Number.isSafeInteger(value) || value < 0) {
    throw new RangeError(`${name} number must be a non-negative safe integer; use BigInt above 2^53 - 1`);
  }
  return BigInt(value);
}

function asStableIds(value) {
  if (value instanceof BigUint64Array) return value;
  let items;
  try {
    items = Array.from(value);
  } catch (error) {
    throw new TypeError("stableIds must be an array-like unsigned 64-bit integer sequence", { cause: error });
  }
  const converted = items.map((item) => asU64(item, "stableIds value"));
  return BigUint64Array.from(converted);
}

function requireLength(value, length, name) {
  if (value.length !== length) {
    throw new RangeError(`${name} must have length ${length}, got ${value.length}`);
  }
}

export function sceneVersion() {
  return xySceneVersion();
}

export function axisTicks({
  kind = "linear",
  lo,
  hi,
  target = 6,
  categories,
  unit,
  constant = 1,
}) {
  let kindCode = -1;
  let aux = 0;
  if (kind === "linear") kindCode = 0;
  else if (kind === "log") kindCode = 1;
  else if (kind === "category") {
    kindCode = 2;
    const count = Array.isArray(categories) ? categories.length : Number(categories);
    if (!Number.isFinite(count) || count < 1) {
      throw new RangeError("category ticks require a positive categories length");
    }
    aux = count;
  } else if (kind === "angular") {
    kindCode = unit === "degrees" ? 3 : unit === "radians" ? 4 : -1;
    if (kindCode < 0) throw new RangeError('angular unit must be "degrees" or "radians"');
  } else if (kind === "time") {
    kindCode = 5;
  } else if (kind === "symlog") {
    kindCode = 6;
    aux = Number(constant);
  }
  if (kindCode < 0) {
    throw new RangeError("kind must be linear, log, category, angular, time, or symlog");
  }
  // Calendar time ladders can emit up to ~1000 first-of-month ticks.
  const capacity = kindCode === 5 ? 1000 : 200;
  const ticks = new Float64Array(capacity);
  const labeled = new Float64Array(capacity);
  const labeledLength = new BigUint64Array(1);
  const step = new Float64Array(1);
  const rawWritten = xySceneAxisTicks(
    kindCode, Number(lo), Number(hi), BigInt(target), Number(aux),
    pointer(ticks, "double *"), pointer(labeled, "double *"),
    pointer(labeledLength, "size_t *"), pointer(step, "double *"), BigInt(capacity),
  );
  if (rawWritten === USIZE_MAX_64) throw new RangeError("invalid canonical axis tick request");
  const written = Number(rawWritten);
  const labels = Number(labeledLength[0]);
  if (!Number.isSafeInteger(written) || written > capacity || labels > written) {
    throw new RangeError("canonical axis ticks exceeded host output limits");
  }
  return { ticks: Array.from(ticks.subarray(0, written)), labeled: Array.from(labeled.subarray(0, labels)), step: step[0] };
}

const TICK_LAYOUT_KIND = new Map([
  ["auto", 0], ["hide", 1], ["rotate", 2], ["stagger", 3],
  ["preserve", 4], ["none", 5], ["off", 6],
]);
const TICK_LAYOUT_SIDE = new Map([["bottom", 0], ["top", 1], ["left", 2], ["right", 3]]);
const TICK_LAYOUT_ANCHOR = new Map([["start", 0], ["center", 1], ["end", 2]]);

function tickLayoutEnum(value, mapping, name) {
  if (typeof value === "string") {
    const key = value.trim().toLowerCase().replaceAll("-", "_");
    if (!mapping.has(key)) {
      throw new RangeError(`${name} must be one of ${[...mapping.keys()].join(", ")}`);
    }
    return mapping.get(key);
  }
  const code = Number(value);
  if (!Number.isInteger(code)) {
    throw new RangeError(`${name} must be a string or integer code`);
  }
  return code;
}

export function tickLabelLayout({
  positions,
  labels,
  kind = "auto",
  side = "bottom",
  anchor = "center",
  isX = true,
  category = false,
  fontSize = 11,
  minGap = 8,
  explicitAngle,
} = {}) {
  const pos = asF64Array(positions ?? [], "positions");
  const texts = Array.from(labels ?? [], (label) => String(label));
  if (pos.length !== texts.length) {
    throw new RangeError("positions and labels must have the same length");
  }
  const encoder = new TextEncoder();
  const encoded = texts.map((text) => encoder.encode(text));
  const packedLen = encoded.reduce((sum, bytes) => sum + bytes.length, 0);
  const packed = new Uint8Array(packedLen);
  const lens = new Uint32Array(texts.length);
  let at = 0;
  for (const [index, bytes] of encoded.entries()) {
    lens[index] = bytes.length;
    packed.set(bytes, at);
    at += bytes.length;
  }
  const n = pos.length;
  const outIndex = new Uint32Array(n);
  const outAngle = new Float64Array(n);
  const outRow = new Uint32Array(n);
  const angle = explicitAngle == null ? Number.NaN : Number(explicitAngle);
  const flags = (isX ? 1 : 0) | (category ? 2 : 0);
  const rawWritten = xySceneTickLabelLayout(
    f64Ptr(pos),
    BigInt(n),
    u32Ptr(lens),
    packedLen ? u8Ptr(packed) : 0,
    BigInt(packedLen),
    tickLayoutEnum(kind, TICK_LAYOUT_KIND, "kind"),
    tickLayoutEnum(side, TICK_LAYOUT_SIDE, "side"),
    tickLayoutEnum(anchor, TICK_LAYOUT_ANCHOR, "anchor"),
    flags,
    Number(fontSize),
    Number(minGap),
    angle,
    n ? u32Ptr(outIndex) : 0,
    n ? f64Ptr(outAngle) : 0,
    n ? u32Ptr(outRow) : 0,
    BigInt(n),
  );
  if (rawWritten === USIZE_MAX_64) throw new RangeError("invalid tick-label layout request");
  const written = Number(rawWritten);
  if (!Number.isSafeInteger(written) || written > n) {
    throw new RangeError("tick-label layout exceeded host output limits");
  }
  return Array.from({ length: written }, (_, index) => ({
    index: outIndex[index],
    angle: outAngle[index],
    row: outRow[index],
  }));
}

function thetaUnitCode(thetaUnit) {
  if (thetaUnit == null) return 0;
  return thetaUnit === "degrees" ? 1 : 2;
}

export function tickWindow({
  rangeLo,
  rangeHi,
  thetaUnit = null,
  kind = "linear",
  nCategories = 0,
  sectorLo = Number.NaN,
  sectorHi = Number.NaN,
} = {}) {
  const outLo = new Float64Array(1);
  const outHi = new Float64Array(1);
  const written = xyTickWindow(
    Number(rangeLo),
    Number(rangeHi),
    thetaUnitCode(thetaUnit),
    kind === "category" ? 1 : 0,
    Number(nCategories) >>> 0,
    Number(sectorLo),
    Number(sectorHi),
    f64Ptr(outLo),
    f64Ptr(outHi),
  );
  if (written === USIZE_MAX_64) throw new RangeError("invalid tick-window request");
  return [outLo[0], outHi[0]];
}

export function tickWindowFilter({
  values,
  lo,
  hi,
  thetaUnit = null,
  kind = "linear",
  requireFinite = false,
} = {}) {
  const arr = asF64Array(values ?? [], "values");
  const n = arr.length;
  const out = new Float64Array(n);
  const written = xyTickWindowFilter(
    n ? f64Ptr(arr) : 0,
    BigInt(n),
    Number(lo),
    Number(hi),
    thetaUnitCode(thetaUnit),
    kind === "category" ? 1 : 0,
    requireFinite ? 1 : 0,
    n ? f64Ptr(out) : 0,
    BigInt(n),
  );
  if (written === USIZE_MAX_64) throw new RangeError("invalid tick-window filter request");
  const kept = Number(written);
  if (!Number.isSafeInteger(kept) || kept > n) {
    throw new RangeError("tick-window filter exceeded host output limits");
  }
  return Array.from(out.subarray(0, kept));
}

function tickFormatKind(kind) {
  if (kind === "category") return 2;
  if (kind === "time") return 1;
  return 0;
}

export function tickFormat({
  value,
  step,
  kind = "linear",
  scale = null,
  thetaUnit = null,
  format = null,
  categories = [],
} = {}) {
  const cats = Array.from(categories ?? [], (item) => String(item));
  const encoder = new TextEncoder();
  const encoded = cats.map((item) => encoder.encode(item));
  const packed = new Uint8Array(encoded.reduce((sum, item) => sum + item.length, 0));
  let packedOffset = 0;
  for (const item of encoded) {
    packed.set(item, packedOffset);
    packedOffset += item.length;
  }
  const lens = new Uint32Array(encoded.map((item) => item.length));
  const formatBytes = format == null ? new Uint8Array() : encoder.encode(String(format));
  let out = new Uint8Array(256);
  let written = xyTickFormat(
    Number(value),
    Number(step),
    tickFormatKind(kind),
    scale === "log" ? 1 : 0,
    thetaUnitCode(thetaUnit),
    formatBytes.length ? u8Ptr(formatBytes) : 0,
    BigInt(formatBytes.length),
    BigInt(cats.length),
    cats.length ? u32Ptr(lens) : 0,
    packed.length ? u8Ptr(packed) : 0,
    BigInt(packed.length),
    u8Ptr(out),
    BigInt(out.length),
  );
  if (written === USIZE_MAX_64) throw new RangeError("invalid tick-format request");
  let size = Number(written);
  if (!Number.isSafeInteger(size)) throw new RangeError("tick-format exceeded host output limits");
  if (size > out.length) {
    out = new Uint8Array(size);
    written = xyTickFormat(
      Number(value),
      Number(step),
      tickFormatKind(kind),
      scale === "log" ? 1 : 0,
      thetaUnitCode(thetaUnit),
      formatBytes.length ? u8Ptr(formatBytes) : 0,
      BigInt(formatBytes.length),
      BigInt(cats.length),
      cats.length ? u32Ptr(lens) : 0,
      packed.length ? u8Ptr(packed) : 0,
      BigInt(packed.length),
      u8Ptr(out),
      BigInt(out.length),
    );
    if (written === USIZE_MAX_64) throw new RangeError("invalid tick-format request");
    size = Number(written);
    if (!Number.isSafeInteger(size) || size > out.length) {
      throw new RangeError("tick-format exceeded host output limits");
    }
  }
  return new TextDecoder().decode(out.subarray(0, size));
}

export function legendBoxLayout({
  plot,
  names = [],
  title = null,
  loc = "upper right",
  fontSize = 11,
  handleLength,
  handleTextPad,
  handleHeight,
  ncols = 1,
  paddingEm = 0.4,
  rowGapEm = 0.5,
  anchor,
  borderAxesPad = 0,
} = {}) {
  if (plot == null || typeof plot !== "object") {
    throw new TypeError("plot must be an object with x, y, w, and h");
  }
  const texts = Array.from(names ?? [], (name) => String(name));
  const encoder = new TextEncoder();
  const encoded = texts.map((text) => encoder.encode(text));
  const packedLen = encoded.reduce((sum, bytes) => sum + bytes.length, 0);
  const packed = new Uint8Array(packedLen);
  const lens = new Uint32Array(texts.length);
  let at = 0;
  for (const [index, bytes] of encoded.entries()) {
    lens[index] = bytes.length;
    packed.set(bytes, at);
    at += bytes.length;
  }
  const titleBytes = encoder.encode(title == null ? "" : String(title));
  const locBytes = encoder.encode(loc == null || loc === "" ? "upper right" : String(loc));
  const n = texts.length;
  const colCap = Math.max(n, 1);
  const metrics = new Float64Array(17);
  const widths = new Float64Array(colCap);
  const offsets = new Float64Array(colCap);
  const nameLens = new Uint32Array(colCap);
  const namesCap = packedLen + 3 * n;
  const namesOut = new Uint8Array(Math.max(namesCap, 1));
  const titleCap = Math.max(titleBytes.length + 8, 1);
  const titleOut = new Uint8Array(titleCap);
  const titleLen = new BigUint64Array(1);
  let anchorArr = null;
  let anchorLen = 0;
  if (anchor != null) {
    const vals = Array.from(anchor, (value) => Number(value));
    if (vals.length !== 2 && vals.length !== 4) {
      throw new RangeError("legend anchor must have length 2 or 4");
    }
    anchorArr = Float64Array.from(vals);
    anchorLen = vals.length;
  }
  const nan = Number.NaN;
  const rawWritten = xyLegendBoxLayout(
    Number(plot.x),
    Number(plot.y),
    Number(plot.w),
    Number(plot.h),
    n ? u32Ptr(lens) : 0,
    packedLen ? u8Ptr(packed) : 0,
    BigInt(packedLen),
    BigInt(n),
    titleBytes.length ? u8Ptr(titleBytes) : 0,
    BigInt(titleBytes.length),
    locBytes.length ? u8Ptr(locBytes) : 0,
    BigInt(locBytes.length),
    Number(fontSize),
    handleLength == null ? nan : Number(handleLength),
    handleTextPad == null ? nan : Number(handleTextPad),
    handleHeight == null ? nan : Number(handleHeight),
    Math.max(1, Number(ncols) | 0),
    Number(paddingEm),
    Number(rowGapEm),
    anchorArr ? f64Ptr(anchorArr) : 0,
    BigInt(anchorLen),
    Number(borderAxesPad),
    f64Ptr(metrics),
    f64Ptr(widths),
    f64Ptr(offsets),
    BigInt(colCap),
    u32Ptr(nameLens),
    u8Ptr(namesOut),
    BigInt(namesOut.length),
    u8Ptr(titleOut),
    BigInt(titleOut.length),
    pointer(titleLen, "size_t *"),
  );
  if (rawWritten === USIZE_MAX_64) throw new RangeError("invalid legend box layout request");
  const visible = Number(rawWritten);
  if (!Number.isSafeInteger(visible) || visible < 0) {
    throw new RangeError("legend box layout exceeded host output limits");
  }
  const decoder = new TextDecoder();
  const outNames = [];
  let nameAt = 0;
  for (let index = 0; index < visible; index += 1) {
    const length = nameLens[index];
    outNames.push(decoder.decode(namesOut.subarray(nameAt, nameAt + length)));
    nameAt += length;
  }
  const titleText = decoder.decode(titleOut.subarray(0, Number(titleLen[0])));
  const ncolsOut = metrics[9] | 0;
  return {
    pad: metrics[0],
    handle: metrics[1],
    gap: metrics[2],
    columnGap: metrics[3],
    rowGap: metrics[4],
    fontSize: metrics[5],
    textH: metrics[6],
    lineH: metrics[7],
    swatchH: metrics[8],
    ncols: ncolsOut,
    title: titleText || null,
    titleH: metrics[10],
    cellW: metrics[11],
    columnWidths: Array.from(widths.subarray(0, ncolsOut)),
    columnOffsets: Array.from(offsets.subarray(0, ncolsOut)),
    boxW: metrics[12],
    boxH: metrics[13],
    x: metrics[14],
    y: metrics[15],
    visibleCount: visible,
    names: outNames,
  };
}

function packUtf8Strings(values) {
  const encoder = new TextEncoder();
  const encoded = Array.from(values ?? [], (value) => encoder.encode(String(value)));
  const packedLen = encoded.reduce((sum, bytes) => sum + bytes.length, 0);
  const packed = new Uint8Array(packedLen);
  const lens = new Uint32Array(encoded.length);
  let at = 0;
  for (const [index, bytes] of encoded.entries()) {
    lens[index] = bytes.length;
    packed.set(bytes, at);
    at += bytes.length;
  }
  return { lens, packed, n: encoded.length };
}

function unpackUtf8Strings(lens, packed, count) {
  const decoder = new TextDecoder();
  const out = [];
  let at = 0;
  for (let index = 0; index < count; index += 1) {
    const length = lens[index];
    out.push(decoder.decode(packed.subarray(at, at + length)));
    at += length;
  }
  return out;
}

const ANCHOR_CODES = { start: 0, center: 1, end: 2 };

export function textBlockMeasure(text, fontSize, lineHeight = 1.2, maxWidth = null) {
  const encoder = new TextEncoder();
  const textBytes = encoder.encode(String(text ?? ""));
  let lineCap = Math.max(textBytes.length + 8, 8);
  let packedCap = Math.max(textBytes.length + 8, 8);
  const metrics = new Float64Array(6);
  let written = USIZE_MAX_64;
  let lineLens = new Uint32Array(lineCap);
  let packed = new Uint8Array(packedCap);
  for (let attempt = 0; attempt < 4; attempt += 1) {
    lineLens = new Uint32Array(lineCap);
    packed = new Uint8Array(packedCap);
    written = xyTextBlockMeasure(
      textBytes.length ? u8Ptr(textBytes) : 0,
      BigInt(textBytes.length),
      Number(fontSize),
      Number(lineHeight),
      maxWidth == null ? Number.NaN : Number(maxWidth),
      f64Ptr(metrics),
      u32Ptr(lineLens),
      BigInt(lineCap),
      u8Ptr(packed),
      BigInt(packedCap),
    );
    if (written !== USIZE_MAX_64) break;
    lineCap *= 4;
    packedCap *= 4;
  }
  if (written === USIZE_MAX_64) throw new RangeError("invalid text-block measure request");
  const n = Number(written);
  if (!Number.isSafeInteger(n) || n < 0) {
    throw new RangeError("text-block measure exceeded host output limits");
  }
  return {
    lines: unpackUtf8Strings(lineLens, packed, n),
    width: metrics[0],
    height: metrics[1],
    lineStep: metrics[2],
    ascent: metrics[3],
    descent: metrics[4],
    lineCount: n,
  };
}

export function textBlockRotatedExtent(width, height, angleDegrees) {
  const outX = new Float64Array(1);
  const outY = new Float64Array(1);
  const written = xyTextBlockRotatedExtent(
    Number(width),
    Number(height),
    Number(angleDegrees),
    f64Ptr(outX),
    f64Ptr(outY),
  );
  if (written === USIZE_MAX_64) throw new RangeError("invalid text-block rotation request");
  return [outX[0], outY[0]];
}

export function yTickLabelExtent(labels, fontSize, angle) {
  const { lens, packed, n } = packUtf8Strings(labels);
  const out = new Float64Array(1);
  const written = xyYTickLabelExtent(
    n ? u32Ptr(lens) : 0,
    packed.length ? u8Ptr(packed) : 0,
    BigInt(packed.length),
    BigInt(n),
    Number(fontSize),
    Number(angle),
    f64Ptr(out),
  );
  if (written === USIZE_MAX_64) throw new RangeError("invalid y tick-label extent request");
  return out[0];
}

export function yAxisLeftRoom(tickOffset, tickRoom, title, titleFontSize, titleGap) {
  const titleBytes = new TextEncoder().encode(title == null ? "" : String(title));
  const out = new Float64Array(1);
  const written = xyYAxisLeftRoom(
    Number(tickOffset),
    Number(tickRoom),
    titleBytes.length ? u8Ptr(titleBytes) : 0,
    BigInt(titleBytes.length),
    Number(titleFontSize),
    Number(titleGap),
    f64Ptr(out),
  );
  if (written === USIZE_MAX_64) throw new RangeError("invalid y-axis left-room request");
  return out[0];
}

export function xAxisTitleRoom(title, fontSize, offset, top) {
  const titleBytes = new TextEncoder().encode(title == null ? "" : String(title));
  const out = new Float64Array(1);
  const written = xyXAxisTitleRoom(
    titleBytes.length ? u8Ptr(titleBytes) : 0,
    BigInt(titleBytes.length),
    Number(fontSize),
    Number(offset),
    top ? 1 : 0,
    f64Ptr(out),
  );
  if (written === USIZE_MAX_64) throw new RangeError("invalid x-axis title-room request");
  return out[0];
}

export function xTickLabelRoom(labels, angles, rows, fontSize, labelOffset, titleRoom) {
  const texts = Array.from(labels ?? [], (label) => String(label));
  const n = texts.length;
  if (n !== (angles?.length ?? 0) || n !== (rows?.length ?? 0)) {
    throw new RangeError("x tick-label room arrays must have equal length");
  }
  const { lens, packed } = packUtf8Strings(texts);
  const angleArr = Float64Array.from(angles ?? [], (angle) => Number(angle));
  const rowArr = Uint32Array.from(rows ?? [], (row) => Number(row) >>> 0);
  const out = new Float64Array(1);
  const written = xyXTickLabelRoom(
    n ? u32Ptr(lens) : 0,
    packed.length ? u8Ptr(packed) : 0,
    BigInt(packed.length),
    BigInt(n),
    n ? f64Ptr(angleArr) : 0,
    n ? u32Ptr(rowArr) : 0,
    Number(fontSize),
    Number(labelOffset),
    Number(titleRoom),
    f64Ptr(out),
  );
  if (written === USIZE_MAX_64) throw new RangeError("invalid x tick-label room request");
  return out[0];
}

export function xTickLabelEdgeRooms(plotW, positions, labels, angles, anchors, fontSize) {
  const texts = Array.from(labels ?? [], (label) => String(label));
  const n = texts.length;
  if (n !== (positions?.length ?? 0) || n !== (angles?.length ?? 0) || n !== (anchors?.length ?? 0)) {
    throw new RangeError("x tick-label edge-room arrays must have equal length");
  }
  const { lens, packed } = packUtf8Strings(texts);
  const posArr = Float64Array.from(positions ?? [], (pos) => Number(pos));
  const angleArr = Float64Array.from(angles ?? [], (angle) => Number(angle));
  const anchorArr = new Uint32Array(n);
  for (let index = 0; index < n; index += 1) {
    const code = ANCHOR_CODES[String(anchors[index])];
    if (code === undefined) throw new RangeError("anchor must be start, center, or end");
    anchorArr[index] = code;
  }
  const outLeft = new Float64Array(1);
  const outRight = new Float64Array(1);
  const written = xyXTickLabelEdgeRooms(
    Number(plotW),
    n ? f64Ptr(posArr) : 0,
    BigInt(n),
    n ? u32Ptr(lens) : 0,
    packed.length ? u8Ptr(packed) : 0,
    BigInt(packed.length),
    n ? f64Ptr(angleArr) : 0,
    n ? u32Ptr(anchorArr) : 0,
    Number(fontSize),
    f64Ptr(outLeft),
    f64Ptr(outRight),
  );
  if (written === USIZE_MAX_64) throw new RangeError("invalid x tick-label edge-room request");
  return [outLeft[0], outRight[0]];
}

const COLORBAR_KINDS = {
  none: 0,
  axes_horizontal: 1,
  axes_vertical: 2,
  figure_horizontal: 3,
  figure_vertical: 4,
};
const POLAR_LEGEND_SIDES = { 0: "", 1: "left", 2: "right", 3: "bottom" };
const POLAR_LEGEND_SIDE_CODES = { "": 0, left: 1, right: 2, bottom: 3 };

export function compatIsCompact(width) {
  const status = xyCompatIsCompact(Number(width));
  if (status === 1) return true;
  if (status === 0) return false;
  throw new RangeError("invalid compact-width request");
}

export function compatDefaultPadding(compact) {
  const out = new Float64Array(4);
  const written = xyCompatDefaultPadding(compact ? 1 : 0, f64Ptr(out));
  if (written === USIZE_MAX_64) throw new RangeError("invalid default-padding request");
  return [out[0], out[1], out[2], out[3]];
}

export function compatTitleWrapWidth(width, left, right) {
  const out = new Float64Array(1);
  const written = xyCompatTitleWrapWidth(Number(width), Number(left), Number(right), f64Ptr(out));
  if (written === USIZE_MAX_64) throw new RangeError("invalid title-wrap-width request");
  return out[0];
}

export function compatTitleRoom(compact, blockHeight, pad, automaticY, y) {
  const out = new Float64Array(1);
  const written = xyCompatTitleRoom(
    compact ? 1 : 0,
    Number(blockHeight),
    Number(pad),
    automaticY ? 1 : 0,
    Number(y),
    f64Ptr(out),
  );
  if (written === USIZE_MAX_64) throw new RangeError("invalid title-room request");
  return out[0];
}

export function compatXAxisSideRoom(compact, top, measured) {
  const outRoom = new Float64Array(1);
  const outMeasured = new Float64Array(1);
  const written = xyCompatXAxisSideRoom(
    compact ? 1 : 0,
    top ? 1 : 0,
    Number(measured),
    f64Ptr(outRoom),
    f64Ptr(outMeasured),
  );
  if (written === USIZE_MAX_64) throw new RangeError("invalid x-axis side-room request");
  return [outRoom[0], outMeasured[0]];
}

export function compatColorbarExtra(kind, hasLabel, padZero) {
  const code = COLORBAR_KINDS[kind];
  if (code === undefined) throw new RangeError("unknown colorbar layout kind");
  const outRight = new Float64Array(1);
  const outBottom = new Float64Array(1);
  const written = xyCompatColorbarExtra(
    code,
    hasLabel ? 1 : 0,
    padZero ? 1 : 0,
    f64Ptr(outRight),
    f64Ptr(outBottom),
  );
  if (written === USIZE_MAX_64) throw new RangeError("invalid colorbar-extra request");
  return [outRight[0], outBottom[0]];
}

export function compatRightYRoom(compact) {
  const out = new Float64Array(1);
  const written = xyCompatRightYRoom(compact ? 1 : 0, f64Ptr(out));
  if (written === USIZE_MAX_64) throw new RangeError("invalid right-y-room request");
  return out[0];
}

export const POLAR_METRICS_LEN = 23;

const THETA_ZERO = {
  E: 0,
  N: Math.PI / 2,
  W: Math.PI,
  S: -Math.PI / 2,
};

function polarThetaUnit(unit = "radians") {
  return unit === "degrees" ? 1 : 0;
}

function polarThetaDirection(direction = "counterclockwise") {
  return direction === "clockwise" ? 1 : 0;
}

function polarThetaZero(zero = "E") {
  if (typeof zero === "string") return THETA_ZERO[zero] ?? 0;
  return Number(zero);
}

function polarRScale(axis = {}) {
  const scale = axis.scale ?? "";
  const kind = axis.kind ?? "linear";
  let code = 0;
  if (scale === "log" || kind === "log") code = 1;
  else if (scale === "symlog") code = 2;
  return {
    kind: code,
    constant: Number(axis.constant ?? 1),
    maskNonpositive: (axis.nonpositive ?? "clip") === "mask",
  };
}

export function packPolarSceneInput(figure) {
  if ((figure.coords ?? "cartesian") !== "polar") return new Uint8Array();
  const thetaAxis = figure.xAxis ?? figure.x_axis ?? figure.axis_options?.x ?? {};
  const rAxis = figure.yAxis ?? figure.y_axis ?? figure.axis_options?.y ?? {};
  const unit = thetaAxis.theta_unit ?? thetaAxis.thetaUnit ?? "radians";
  const turn = unit === "degrees" ? 360 : Math.PI * 2;
  const sector = thetaAxis.sector ?? [0, turn];
  const categories = thetaAxis.categories ?? [];
  const range = typeof figure._range === "function" ? figure._range("y") : (rAxis.range ?? [0, 1]);
  const [rLo, rHi] = range;
  const origin = rAxis.r_origin ?? rAxis.rOrigin;
  const scale = polarRScale(rAxis);
  const grid = thetaAxis.grid_shape ?? thetaAxis.gridShape ?? "circular";
  const out = new Uint8Array(92);
  const view = new DataView(out.buffer);
  out.set(encodeUtf8("XYPL").slice(0, 4), 0);
  view.setUint32(4, 1, true);
  view.setUint32(8, polarThetaUnit(unit), true);
  view.setUint32(12, polarThetaDirection(thetaAxis.theta_direction ?? thetaAxis.thetaDirection), true);
  view.setUint32(16, categories.length, true);
  view.setUint32(20, scale.kind, true);
  out[24] = grid === "linear" ? 1 : 0;
  out[25] = scale.maskNonpositive ? 1 : 0;
  view.setUint16(26, 0, true);
  view.setFloat64(28, polarThetaZero(thetaAxis.theta_zero ?? thetaAxis.thetaZero ?? "E"), true);
  view.setFloat64(36, Number(sector[0]), true);
  view.setFloat64(44, Number(sector[1]), true);
  view.setFloat64(52, Number(rLo), true);
  view.setFloat64(60, Number(rHi), true);
  view.setFloat64(68, origin == null ? Number.NaN : Number(origin), true);
  view.setFloat64(76, Number(rAxis.hole ?? 0), true);
  view.setFloat64(84, scale.constant, true);
  return out;
}

export function polarLayout(thetaAxis = {}, rAxis = {}, plot = {}) {
  const unit = thetaAxis.theta_unit ?? thetaAxis.thetaUnit ?? "radians";
  const turn = unit === "degrees" ? 360 : Math.PI * 2;
  const sector = thetaAxis.sector ?? [0, turn];
  const categories = thetaAxis.categories ?? [];
  const [rLo, rHi] = rAxis.range ?? [0, 1];
  const origin = rAxis.r_origin ?? rAxis.rOrigin;
  const scale = polarRScale(rAxis);
  const metrics = new Float64Array(POLAR_METRICS_LEN);
  const written = xyPolarLayout(
    Number(plot.x ?? 0),
    Number(plot.y ?? 0),
    Number(plot.w ?? 0),
    Number(plot.h ?? 0),
    polarThetaUnit(unit),
    polarThetaZero(thetaAxis.theta_zero ?? thetaAxis.thetaZero ?? "E"),
    polarThetaDirection(thetaAxis.theta_direction ?? thetaAxis.thetaDirection),
    Number(sector[0]),
    Number(sector[1]),
    categories.length,
    Number(rLo),
    Number(rHi),
    origin == null ? Number.NaN : Number(origin),
    Number(rAxis.hole ?? 0),
    scale.kind,
    scale.constant,
    scale.maskNonpositive ? 1 : 0,
    f64Ptr(metrics),
    POLAR_METRICS_LEN,
  );
  if (written !== POLAR_METRICS_LEN) throw new RangeError("invalid polar-layout request");
  return metrics;
}

export function polarProject(metrics, theta, r) {
  const packed = metrics instanceof Float64Array ? metrics : Float64Array.from(metrics);
  const th = Float64Array.from(Array.isArray(theta) ? theta : [theta]);
  const rv = Float64Array.from(Array.isArray(r) ? r : [r]);
  if (th.length !== rv.length) throw new RangeError("theta and r must have the same length");
  const outX = new Float64Array(th.length);
  const outY = new Float64Array(th.length);
  const written = xyPolarProject(
    f64Ptr(packed),
    packed.length,
    f64Ptr(th),
    f64Ptr(rv),
    th.length,
    f64Ptr(outX),
    f64Ptr(outY),
  );
  if (written === USIZE_MAX_64 || written !== th.length) {
    throw new RangeError("invalid polar-project request");
  }
  if (!Array.isArray(theta)) return [outX[0], outY[0]];
  return [outX, outY];
}

export function polarLegendRoom(width) {
  const out = new Float64Array(1);
  const written = xyPolarLegendRoom(Number(width), f64Ptr(out));
  if (written === USIZE_MAX_64) throw new RangeError("invalid polar-legend-room request");
  return out[0];
}

export function polarLegendReserve(compact, locHasLeft, width) {
  const side = new Uint32Array(1);
  const room = new Float64Array(1);
  const written = xyPolarLegendReserve(
    compact ? 1 : 0,
    locHasLeft ? 1 : 0,
    Number(width),
    u32Ptr(side),
    f64Ptr(room),
  );
  if (written === USIZE_MAX_64) throw new RangeError("invalid polar-legend-reserve request");
  return [POLAR_LEGEND_SIDES[side[0]], room[0]];
}

export function polarLabelRoom(widest = null) {
  const out = new Float64Array(1);
  const written = xyPolarLabelRoom(widest == null ? Number.NaN : Number(widest), f64Ptr(out));
  if (written === USIZE_MAX_64) throw new RangeError("invalid polar-label-room request");
  return out[0];
}

export function recutPolarPlot(plot, width, height, {
  legendSide = "",
  legendRoom = 0,
  polarLabelRoom: labelRoom = 0,
  authoredPadding = false,
  yTitled = false,
  keepsBottom = false,
} = {}) {
  const side = POLAR_LEGEND_SIDE_CODES[legendSide];
  if (side === undefined) throw new RangeError("legendSide must be '', left, right, or bottom");
  const incoming = Float64Array.from([
    Number(plot.x),
    Number(plot.y),
    Number(plot.w),
    Number(plot.h),
    Number(plot.top_axis_room ?? plot.topAxisRoom ?? 0),
  ]);
  const out = new Float64Array(9);
  const written = xyRecutPolarPlot(
    f64Ptr(incoming),
    Number(width),
    Number(height),
    side,
    Number(legendRoom),
    Number(labelRoom),
    authoredPadding ? 1 : 0,
    yTitled ? 1 : 0,
    keepsBottom ? 1 : 0,
    f64Ptr(out),
  );
  if (written === USIZE_MAX_64) throw new RangeError("invalid polar-recut request");
  const result = { x: out[0], y: out[1], w: out[2], h: out[3], topAxisRoom: out[4] };
  if (Number.isFinite(out[5])) {
    result.legendBoxX = out[5];
    result.legendBoxY = out[6];
    result.legendBoxW = out[7];
    result.legendBoxH = out[8];
  }
  return result;
}

export function tightLayoutSolve({
  canvasW,
  canvasH,
  nrows,
  ncols,
  compact = false,
  panels = [],
  extra = [0, 0, 0, 0],
  pad = null,
  wPad = null,
  hPad = null,
  pointPx = 1,
  rect = [0, 0, 1, 1],
} = {}) {
  if (!Array.isArray(extra) || extra.length !== 4) {
    throw new RangeError("extra must be left, right, bottom, top");
  }
  if (!Array.isArray(rect) || rect.length !== 4) {
    throw new RangeError("rect must be left, bottom, right, top");
  }
  const packed = new Float64Array(panels.length * 8);
  for (let index = 0; index < panels.length; index += 1) {
    const panel = panels[index];
    const at = index * 8;
    packed[at] = Number(panel.row0);
    packed[at + 1] = Number(panel.row1);
    packed[at + 2] = Number(panel.col0);
    packed[at + 3] = Number(panel.col1);
    packed[at + 4] = Number(panel.left);
    packed[at + 5] = Number(panel.top);
    packed[at + 6] = Number(panel.right);
    packed[at + 7] = Number(panel.bottom);
  }
  const extraArr = Float64Array.from(extra, (value) => Number(value));
  const rectArr = Float64Array.from(rect, (value) => Number(value));
  const out = new Float64Array(6);
  const written = xyTightLayoutSolve(
    Number(canvasW),
    Number(canvasH),
    Number(nrows) >>> 0,
    Number(ncols) >>> 0,
    compact ? 1 : 0,
    packed.length ? f64Ptr(packed) : 0,
    BigInt(panels.length),
    f64Ptr(extraArr),
    pad == null ? Number.NaN : Number(pad),
    wPad == null ? Number.NaN : Number(wPad),
    hPad == null ? Number.NaN : Number(hPad),
    Number(pointPx),
    f64Ptr(rectArr),
    f64Ptr(out),
  );
  if (written === USIZE_MAX_64) throw new RangeError("invalid tight-layout request");
  return { left: out[0], right: out[1], bottom: out[2], top: out[3], wspace: out[4], hspace: out[5] };
}

export function scaleMap({ values, kind = "linear", operation = "pixel", domain, range = [0, 1], constant = 1, nonpositive = "clip" }) {
  const kindCode = kind === "linear" ? 0 : kind === "log" ? 1 : kind === "symlog" ? 2 : -1;
  const operationCode = operation === "coord" ? 0 : operation === "pixel" ? 1 : operation === "value" ? 2 : -1;
  if (kindCode < 0) throw new RangeError("kind must be linear, log, or symlog");
  if (operationCode < 0) throw new RangeError("operation must be coord, pixel, or value");
  if (nonpositive !== "clip" && nonpositive !== "mask") {
    throw new RangeError("nonpositive must be clip or mask");
  }
  if (!Array.isArray(domain) || domain.length !== 2 || !Array.isArray(range) || range.length !== 2) {
    throw new RangeError("domain and range must each contain two values");
  }
  const source = asF64Array(values, "values");
  const output = new Float64Array(source.length);
  const status = xySceneScaleMap(
    f64Ptr(source), BigInt(source.length), kindCode, operationCode,
    Number(domain[0]), Number(domain[1]), Number(range[0]), Number(range[1]),
    Number(constant), nonpositive === "mask" ? 1 : 0, f64Ptr(output),
  );
  if (status !== 0) throw new RangeError("invalid canonical scene scale");
  return output;
}

function axisDescriptor(axis, name) {
  const { id, kind = "linear", domain, constant = 1, nonpositive = "clip" } = axis;
  const kindCode = kind === "linear" ? 0 : kind === "log" ? 1 : kind === "symlog" ? 2 : -1;
  if (kindCode < 0) throw new RangeError(`${name}.kind must be linear, log, or symlog`);
  if (nonpositive !== "clip" && nonpositive !== "mask") throw new RangeError(`${name}.nonpositive must be clip or mask`);
  if (!Array.isArray(domain) || domain.length !== 2) throw new RangeError(`${name}.domain must contain two values`);
  return [asU64(id, `${name}.id`), kindCode, Number(domain[0]), Number(domain[1]), Number(constant), nonpositive === "mask" ? 1 : 0];
}

const AXIS_STYLE_KEYS = new Set([
  "grid_color", "grid_width", "grid_opacity", "axis_color", "axis_width",
  "tick_color", "tick_width", "tick_length", "tick_direction", "tick_label_color", "label_color",
  "gridColor", "gridWidth", "gridOpacity", "axisColor", "axisWidth",
  "tickColor", "tickWidth", "tickLength", "tickDirection", "tickLabelColor", "labelColor",
]);

function styleHas(style, snake, camel) {
  return Object.hasOwn(style, snake) || (camel != null && Object.hasOwn(style, camel));
}

function styleValue(style, snake, camel, fallback) {
  if (Object.hasOwn(style, snake)) return style[snake];
  if (camel != null && Object.hasOwn(style, camel)) return style[camel];
  return fallback;
}

function packChromeAxis(axis, options, sides) {
  const style = options.style ?? {};
  const minor = options.minorStyle ?? options.minor_style ?? {};
  for (const [label, authored] of [["style", style], ["minor_style", minor]]) {
    const unsupported = Object.keys(authored).filter((key) => authored[key] != null && !AXIS_STYLE_KEYS.has(key));
    if (unsupported.length) {
      throw new RangeError(`Scene v12 does not yet encode ${axis} axis ${label} keys`);
    }
  }
  const side = options.side ?? sides[0];
  if (!sides.includes(side)) throw new RangeError(`Scene ${axis} axis side is invalid`);
  const sideCode = sides.indexOf(side);
  const mask = (values, name) => {
    if (values == null) return 1 << sideCode;
    return values.reduce((sum, value) => {
      const index = sides.indexOf(value);
      if (index < 0) throw new RangeError(`Scene ${axis} axis ${name} are invalid`);
      return sum | (1 << index);
    }, 0);
  };
  const direction = { out: 0, in: 1, inout: 2 };
  let paintFlags = 0;
  if (styleHas(style, "axis_color", "axisColor")) paintFlags |= 1 << 0;
  if (styleHas(style, "grid_color", "gridColor")) paintFlags |= 1 << 1;
  if (styleHas(style, "tick_color", "tickColor")) paintFlags |= 1 << 2;
  if (styleHas(minor, "grid_color", "gridColor")) paintFlags |= 1 << 3;
  if (styleHas(minor, "tick_color", "tickColor")) paintFlags |= 1 << 4;
  if (styleHas(style, "tick_label_color", "tickLabelColor") || styleHas(style, "label_color", "labelColor")) paintFlags |= 1 << 5;
  const widthSpecs = [
    [style, "axis_width", "axisWidth", 1],
    [style, "grid_width", "gridWidth", 1],
    [style, "tick_width", "tickWidth", 1],
    [style, "tick_length", "tickLength", 4],
    [minor, "grid_width", "gridWidth", 1],
    [minor, "tick_width", "tickWidth", 1],
    [minor, "tick_length", "tickLength", 0],
  ];
  let widthFlags = 0;
  const widths = widthSpecs.map(([source, snake, camel, fallback], index) => {
    if (styleHas(source, snake, camel)) {
      widthFlags |= 1 << index;
      return Number(styleValue(source, snake, camel, fallback));
    }
    return fallback;
  });
  const paints = [
    String(styleValue(style, "axis_color", "axisColor", "#202020")),
    String(styleValue(style, "grid_color", "gridColor", "#202020")),
    String(styleValue(style, "tick_color", "tickColor", "#202020")),
    String(styleValue(minor, "grid_color", "gridColor", "transparent")),
    String(styleValue(minor, "tick_color", "tickColor", "#202020")),
    String(styleValue(style, "tick_label_color", "tickLabelColor", styleValue(style, "label_color", "labelColor", "#202020"))),
  ].map(encodeUtf8);
  const prefix = new Uint8Array(84);
  const view = new DataView(prefix.buffer);
  prefix[0] = sideCode;
  prefix[1] = mask(options.tickSides ?? options.tick_sides, "tick_sides");
  prefix[2] = mask(options.tickLabelSides ?? options.tick_label_sides, "tick_label_sides");
  prefix[3] = direction[String(styleValue(style, "tick_direction", "tickDirection", "out"))] ?? 255;
  prefix[4] = direction[String(styleValue(minor, "tick_direction", "tickDirection", "out"))] ?? 255;
  prefix[5] = paintFlags;
  prefix[6] = widthFlags;
  view.setFloat32(8, Number(styleValue(style, "grid_opacity", "gridOpacity", 1)), true);
  view.setFloat32(12, Number(styleValue(minor, "grid_opacity", "gridOpacity", 1)), true);
  widths.forEach((value, index) => view.setFloat64(16 + index * 8, value, true));
  paints.forEach((bytes, index) => view.setUint16(72 + index * 2, bytes.length, true));
  return concatBytes([prefix, ...paints]);
}

function resolveChromeStyle(envelope) {
  const out = new Uint8Array(200);
  const code = xySceneResolveChromeStyle(u8Ptr(envelope), BigInt(envelope.length), u8Ptr(out), BigInt(out.length));
  if (code !== 200) throw new RangeError("invalid chrome style envelope");
  return out;
}

function defaultChromeStyle() {
  const envelope = new Uint8Array(16);
  envelope.set(encodeUtf8("XYCH").slice(0, 4), 0);
  new DataView(envelope.buffer).setUint32(4, 1, true);
  return resolveChromeStyle(envelope);
}

function figureChromeStyle(figure) {
  const figureStyle = figure.style ?? {};
  let flags = 2 << 8;
  let chart = new Uint8Array(0);
  let plot = new Uint8Array(0);
  if (figureStyle.background != null) {
    flags |= 1;
    chart = encodeUtf8(figureStyle.background || "transparent");
  }
  if (figureStyle["--chart-bg"] != null) {
    flags |= 2;
    plot = encodeUtf8(figureStyle["--chart-bg"] || "transparent");
  }
  const x = packChromeAxis("x", figure.xAxis ?? figure.x_axis ?? {}, ["bottom", "top"]);
  const y = packChromeAxis("y", figure.yAxis ?? figure.y_axis ?? {}, ["left", "right"]);
  const header = new Uint8Array(16);
  const view = new DataView(header.buffer);
  header.set(encodeUtf8("XYCH").slice(0, 4), 0);
  view.setUint32(4, 1, true);
  view.setUint32(8, flags >>> 0, true);
  view.setUint16(12, chart.length, true);
  view.setUint16(14, plot.length, true);
  return resolveChromeStyle(concatBytes([header, chart, plot, x, y]));
}

/** Encode the shared backend-neutral Scene v12 typed batch. */
export function sceneBatchEncode({
  viewport, margins, xAxis, yAxis, kinds, stableIds, styleRefs, styles, diameter, symbols, x0, y0, x1, y1,
  expansionModes = null,
  title = "", xLabel = "", yLabel = "", chromeStyle = null,
  xMajorTicks = null, xMinorTicks = [], yMajorTicks = null, yMinorTicks = [],
  xTickLabels = null, yTickLabels = null,
  xFormat = null, yFormat = null,
  legendInput = null, colorbarInput = null, authoredTextAnnotations = null,
  polarInput = null,
}) {
  if (!Array.isArray(viewport) || viewport.length !== 2 || !Array.isArray(margins) || margins.length !== 4) {
    throw new RangeError("viewport and margins must contain two and four values");
  }
  if (styles.length > MAX_SCENE_STYLES) {
    throw new RangeError(`scene style tables are limited to ${MAX_SCENE_STYLES} entries`);
  }
  const kindArray = asUnsignedArray(kinds, "kinds", 255, Uint8Array);
  if (kindArray.length > MAX_SCENE_MARKS) {
    throw new RangeError(`scene batches are limited to ${MAX_SCENE_MARKS} records`);
  }
  const ids = asStableIds(stableIds);
  const styleRefArray = asUnsignedArray(styleRefs, "styleRefs", 0xffff_ffff, Uint32Array);
  const diameters = asF64Array(diameter, "diameter");
  const symbolCodes = asUnsignedArray(symbols, "symbols", 255, Uint8Array);
  const expansionModeCodes = expansionModes == null
    ? new Uint8Array(kindArray.length)
    : asUnsignedArray(expansionModes, "expansionModes", 8, Uint8Array);
  const fills = new Uint8Array(styles.length * 4);
  const strokes = new Uint8Array(styles.length * 4);
  const widths = new Float64Array(styles.length);
  for (const [index, style] of styles.entries()) {
    const fill = asUnsignedArray(style.fillRgba, `styles[${index}].fillRgba`, 255, Uint8Array);
    const stroke = asUnsignedArray(style.strokeRgba, `styles[${index}].strokeRgba`, 255, Uint8Array);
    requireLength(fill, 4, `styles[${index}].fillRgba`);
    requireLength(stroke, 4, `styles[${index}].strokeRgba`);
    fills.set(fill, index * 4);
    strokes.set(stroke, index * 4);
    widths[index] = Number(style.strokeWidth ?? 0);
  }
  const coordinates = [x0, y0, x1, y1].map((value, index) => asF64Array(value, ["x0", "y0", "x1", "y1"][index]));
  const length = kindArray.length;
  for (const [value, name] of [[ids, "stableIds"], [styleRefArray, "styleRefs"], [diameters, "diameter"], [symbolCodes, "symbols"], [expansionModeCodes, "expansionModes"], ...coordinates.map((value, index) => [value, ["x0", "y0", "x1", "y1"][index]])]) requireLength(value, length, name);
  const xd = axisDescriptor(xAxis, "xAxis");
  const yd = axisDescriptor(yAxis, "yAxis");
  const titleBytes = new TextEncoder().encode(String(title ?? ""));
  const xLabelBytes = new TextEncoder().encode(String(xLabel ?? ""));
  const yLabelBytes = new TextEncoder().encode(String(yLabel ?? ""));
  if ([titleBytes, xLabelBytes, yLabelBytes].some((value) => value.length > MAX_SCENE_TEXT_BYTES)) {
    throw new RangeError(`scene title and axis labels are limited to ${MAX_SCENE_TEXT_BYTES} UTF-8 bytes each`);
  }
  const chrome = chromeStyle == null
    ? defaultChromeStyle()
    : asUnsignedArray(chromeStyle, "chromeStyle", 255, Uint8Array);
  requireLength(chrome, 200, "chromeStyle");
  const tickArrays = [xMajorTicks, xMinorTicks, yMajorTicks, yMinorTicks].map((value, index) => value == null ? null : asF64Array(value, ["xMajorTicks", "xMinorTicks", "yMajorTicks", "yMinorTicks"][index]));
  const frameTickLabels = (labels, name) => {
    if (labels == null) return new Uint8Array();
    if (!Array.isArray(labels) || labels.length > 200) throw new RangeError(`${name} must contain at most 200 strings`);
    const texts = labels.map((value) => new TextEncoder().encode(String(value)));
    if (texts.some((value) => value.length === 0 || value.includes(0)) || texts.reduce((sum, value) => sum + value.length, 0) > MAX_SCENE_TEXT_BYTES) throw new RangeError(`${name} must contain nonempty bounded UTF-8 strings`);
    const out = new Uint8Array(12 + texts.reduce((sum, value) => sum + 4 + value.length, 0)); const view = new DataView(out.buffer);
    out.set(new TextEncoder().encode("XYTL")); view.setUint32(4, 1, true); view.setUint32(8, texts.length, true); let at = 12;
    for (const text of texts) { view.setUint32(at, text.length, true); at += 4; out.set(text, at); at += text.length; }
    return out;
  };
  const xTickLabelBytes = frameTickLabels(xTickLabels, "xTickLabels");
  const yTickLabelBytes = frameTickLabels(yTickLabels, "yTickLabels");
  const frameAxisFormat = (value, name) => {
    if (value == null) return new Uint8Array();
    if (typeof value !== "string") throw new TypeError(`${name} must be a string or null`);
    const encoded = new TextEncoder().encode(value);
    if (encoded.length > 256 || encoded.includes(0)) throw new RangeError(`${name} must be NUL-free and at most 256 UTF-8 bytes`);
    return encoded;
  };
  const xFormatBytes = frameAxisFormat(xFormat, "xFormat");
  const yFormatBytes = frameAxisFormat(yFormat, "yFormat");
  const legend = legendInput == null ? new Uint8Array() : asUnsignedArray(legendInput, "legendInput", 255, Uint8Array);
  const colorbar = colorbarInput == null ? new Uint8Array() : asUnsignedArray(colorbarInput, "colorbarInput", 255, Uint8Array);
  const polar = polarInput == null || polarInput.length === 0
    ? new Uint8Array()
    : asUnsignedArray(polarInput, "polarInput", 255, Uint8Array);
  if (polar.length && polar.length !== 92) {
    throw new RangeError("polarInput must be empty or a 92-byte XYPL v1 envelope");
  }
  const authoredText = authoredTextAnnotations == null ? new Uint8Array() : asUnsignedArray(authoredTextAnnotations, "authoredTextAnnotations", 255, Uint8Array);
  const authoredInput = xFormatBytes.length || yFormatBytes.length ? (() => {
    const out = new Uint8Array(20 + xFormatBytes.length + yFormatBytes.length + authoredText.length);
    const view = new DataView(out.buffer);
    out.set(new TextEncoder().encode("XYAF"));
    view.setUint32(4, 1, true);
    view.setUint32(8, xFormatBytes.length, true);
    view.setUint32(12, yFormatBytes.length, true);
    view.setUint32(16, authoredText.length, true);
    out.set(xFormatBytes, 20);
    out.set(yFormatBytes, 20 + xFormatBytes.length);
    out.set(authoredText, 20 + xFormatBytes.length + yFormatBytes.length);
    return out;
  })() : authoredText;
  if (colorbar.length > 4_600) throw new RangeError("scene colorbar input is limited to 4,600 bytes");
  if (tickArrays.some((value) => value != null && value.length > 200)) throw new RangeError("scene axis tick lists are limited to 200 values");
  const polarView = polarAbiInputPointer(polar);
  let capacity = 160 + widths.length * 16 + length * 56 + 248 + titleBytes.length + xLabelBytes.length + yLabelBytes.length + xTickLabelBytes.length + yTickLabelBytes.length + authoredInput.length + legend.length + colorbar.length + tickArrays.reduce((sum, value) => sum + (value?.byteLength ?? 0), 0);
  for (;;) {
    const output = new Uint8Array(capacity);
    const rawWritten = xySceneBatchEncode(
      Number(viewport[0]), Number(viewport[1]), ...margins.map(Number), ...xd, ...yd,
      u8Ptr(chrome), BigInt(chrome.length),
      f64Ptr(tickArrays[0]), BigInt(tickArrays[0]?.length ?? 0), tickArrays[0] == null ? 1 : 0,
      f64Ptr(tickArrays[1]), BigInt(tickArrays[1]?.length ?? 0),
      f64Ptr(tickArrays[2]), BigInt(tickArrays[2]?.length ?? 0), tickArrays[2] == null ? 1 : 0,
      f64Ptr(tickArrays[3]), BigInt(tickArrays[3]?.length ?? 0),
      xTickLabelBytes.length ? u8Ptr(xTickLabelBytes) : 0, BigInt(xTickLabelBytes.length),
      yTickLabelBytes.length ? u8Ptr(yTickLabelBytes) : 0, BigInt(yTickLabelBytes.length),
      authoredInput.length ? u8Ptr(authoredInput) : 0, BigInt(authoredInput.length),
      u8Ptr(kindArray), pointer(ids, "uint64_t *"), u32Ptr(styleRefArray),
      u8Ptr(fills), u8Ptr(strokes), f64Ptr(widths), BigInt(widths.length),
      f64Ptr(diameters), u8Ptr(symbolCodes), u8Ptr(expansionModeCodes),
      ...coordinates.map(f64Ptr), BigInt(length),
      titleBytes.length ? u8Ptr(titleBytes) : 0, BigInt(titleBytes.length),
      xLabelBytes.length ? u8Ptr(xLabelBytes) : 0, BigInt(xLabelBytes.length),
      yLabelBytes.length ? u8Ptr(yLabelBytes) : 0, BigInt(yLabelBytes.length),
      legend.length ? u8Ptr(legend) : 0, BigInt(legend.length),
      colorbar.length ? u8Ptr(colorbar) : 0, BigInt(colorbar.length),
      polarView.ptr,
      u8Ptr(output), BigInt(capacity),
    );
    if (rawWritten === USIZE_MAX_64) throw new RangeError("invalid canonical scene batch");
    const written = Number(rawWritten);
    if (!Number.isSafeInteger(written) || written < 0) throw new RangeError("canonical scene batch exceeded host output limits");
    if (written <= capacity) return output.slice(0, written);
    capacity = written;
  }
}

function sceneOutput(encoded, call, name, extra = []) {
  const source = asU8Array(encoded, "encoded scene");
  if (source.length === 0) throw new RangeError("encoded scene must not be empty");
  let capacity = Math.max(256, source.length * 3);
  for (;;) {
    const output = new Uint8Array(capacity);
    const rawWritten = call(u8Ptr(source), BigInt(source.length), ...extra, u8Ptr(output), BigInt(capacity));
    if (rawWritten === USIZE_MAX_64) throw new RangeError(`invalid canonical scene for ${name}`);
    const written = Number(rawWritten);
    if (!Number.isSafeInteger(written) || written < 0) throw new RangeError(`${name} output exceeded host limits`);
    if (written <= capacity) return output.slice(0, written);
    capacity = written;
  }
}

export function sceneSvg(encoded) {
  return new TextDecoder().decode(sceneOutput(encoded, xySceneSvg, "SVG"));
}

export function svgToPdf(svg) {
  const text = String(svg);
  const source = new TextEncoder().encode(text);
  let capacity = Math.max(256, source.length * 2);
  for (;;) {
    const output = new Uint8Array(capacity);
    const rawWritten = xySvgToPdf(
      source.length ? u8Ptr(source) : 0,
      BigInt(source.length),
      u8Ptr(output),
      BigInt(capacity),
    );
    if (rawWritten === USIZE_MAX_64) {
      const end = output.indexOf(0);
      const message = new TextDecoder().decode(end >= 0 ? output.subarray(0, end) : output).trim()
        || "unsupported SVG feature";
      throw new RangeError(message);
    }
    const written = Number(rawWritten);
    if (!Number.isSafeInteger(written) || written < 0) {
      throw new RangeError("svgToPdf output exceeded host limits");
    }
    if (written <= capacity) return output.slice(0, written);
    capacity = written;
  }
}

function encodePixels(fn, pixels, width, height, channels, extra = [], label = "image") {
  const source = pixels instanceof Uint8Array ? pixels : new Uint8Array(pixels);
  const w = Number(width);
  const h = Number(height);
  const c = Number(channels);
  if (!Number.isInteger(w) || !Number.isInteger(h) || !Number.isInteger(c)) {
    throw new RangeError(`${label} dimensions must be integers`);
  }
  let capacity = Math.max(256, source.length);
  for (;;) {
    const output = new Uint8Array(capacity);
    const rawWritten = fn(
      source.length ? u8Ptr(source) : 0,
      BigInt(source.length),
      BigInt(w),
      BigInt(h),
      BigInt(c),
      ...extra,
      u8Ptr(output),
      BigInt(capacity),
    );
    if (rawWritten === USIZE_MAX_64) {
      const end = output.indexOf(0);
      const message = new TextDecoder().decode(end >= 0 ? output.subarray(0, end) : output).trim()
        || `invalid ${label} input`;
      throw new RangeError(message);
    }
    const written = Number(rawWritten);
    if (!Number.isSafeInteger(written) || written < 0) {
      throw new RangeError(`${label} output exceeded host limits`);
    }
    if (written <= capacity) return output.slice(0, written);
    capacity = written;
  }
}

export function encodeJpeg(pixels, width, height, channels, quality = 90) {
  const q = Number(quality);
  if (!Number.isInteger(q)) throw new RangeError("quality must be an int in 1..100");
  return encodePixels(xyEncodeJpeg, pixels, width, height, channels, [q], "JPEG");
}

export function encodeWebp(pixels, width, height, channels) {
  return encodePixels(xyEncodeWebp, pixels, width, height, channels, [], "WebP");
}

export function encodePng(pixels, width, height, channels, mode = 0, compression = 6) {
  const m = Number(mode);
  const c = Number(compression);
  if (!Number.isInteger(m) || (m !== 0 && m !== 1)) {
    throw new RangeError("PNG mode must be 0 (auto) or 1 (truecolor)");
  }
  if (!Number.isInteger(c) || c < 0 || c > 9) {
    throw new RangeError("PNG compression must be an int in 0..9");
  }
  return encodePixels(xyEncodePng, pixels, width, height, channels, [m, c], "PNG");
}

export function sceneRasterCommands(encoded, scale = 1) {
  const factor = Number(scale);
  if (!Number.isFinite(factor) || factor <= 0) throw new RangeError("scene raster scale must be positive and finite");
  return sceneOutput(encoded, xySceneRasterCommands, "raster commands", [factor]);
}

export function sceneBrowserPainter(encoded, maxBytes = 64 * 1024 * 1024) {
  const limit = Number(maxBytes);
  if (!Number.isSafeInteger(limit) || limit <= 0) throw new RangeError("scene painter byte limit must be a positive safe integer");
  return sceneOutput(encoded, xySceneBrowserPainter, "browser painter", [BigInt(limit)]);
}

function rgba8(css, opacity = 1) {
  return cssColorRgba8(css, opacity);
}

function annotationNumber(style, key, fallback, label) {
  const raw = Object.hasOwn(style, key) ? style[key] : fallback;
  if (raw == null || typeof raw === "boolean" || (typeof raw === "string" && raw.trim() === "")) throw new RangeError(`Scene v12 annotation ${label} must be numeric`);
  const value = Number(raw);
  if (!Number.isFinite(value)) throw new RangeError(`Scene v12 annotation ${label} must be numeric`);
  return value;
}

function annotationColor(style, key, fallback, label) {
  const raw = Object.hasOwn(style, key) ? style[key] : fallback;
  if (typeof raw !== "string" || raw.trim() === "") throw new RangeError(`Scene v12 annotation ${label} must be a nonempty CSS color`);
  return raw;
}

const RECT_KINDS = new Set(["bar", "column", "histogram", "violin", "box"]);
const SEGMENT_KINDS = new Set(["segments", "errorbar", "stem", "contour", "box_whisker", "box_median"]);
const BAND_KINDS = new Set(["area", "error_band"]);
const RIBBON_KINDS = new Set(["ribbon"]);
const POLYFILL_KINDS = new Set(["triangle_mesh"]);
const HEXBIN_KINDS = new Set(["hexbin"]);
const HEXBIN_REDUCES = new Set(["count", "mean", "sum"]);
const HEATMAP_KINDS = new Set(["heatmap"]);
const STROKE_KINDS = new Set(["line", "segments", "errorbar", "stem", "contour", "box_whisker", "box_median"]);
const SUPPORTED_KINDS = new Set([
  "scatter", "line", "bar", "column", "histogram", "violin", "box",
  "segments", "errorbar", "stem", "contour", "box_whisker", "box_median",
  "area", "error_band", "ribbon", "triangle_mesh", "hexbin", "heatmap",
]);
const XYFS_TRACE_UNSUPPORTED_KIND = 1 << 0;
const XYFS_TRACE_NON_PRIMARY_AXIS = 1 << 1;
const XYFS_TRACE_HIDDEN_OR_PER_ITEM = 1 << 2;
const XYFS_TRACE_DENSITY = 1 << 3;
const XYFS_TRACE_DASHED_MARKERS = 1 << 4;
const XYFS_TRACE_RECT_GRADIENT = 1 << 5;
const XYFS_TRACE_CORNER_RADIUS = 1 << 6;
const XYFS_TRACE_WEDGE_GAP = 1 << 7;
const XYFS_TRACE_JOINED_FILL = 1 << 8;
const XYFS_TRACE_CUSTOM_HEX_REDUCE = 1 << 9;
const XYFS_TRACE_HEATMAP_COLORMAP = 1 << 10;
const XYFS_TRACE_NON_CSS_FILL = 1 << 11;
const XYFS_DASH_KEYS = ["dash", "curve", "linecap", "marker_path", "marker_glyph", "smooth"];

/** Return Rust's stable diagnostic for authored Scene feature bits. */
export function sceneSupportReason(features, requestVersion = 1) {
  if (
    typeof requestVersion !== "number"
    || !Number.isInteger(requestVersion)
    || requestVersion < 0
    || requestVersion >= 0x1_0000_0000
  ) throw new TypeError("scene support requestVersion must be a u32 integer");
  if (
    typeof features !== "bigint"
    && (typeof features !== "number" || !Number.isSafeInteger(features) || features < 0)
  ) throw new TypeError("scene support features must be an exact nonnegative u64 integer");
  const mask = BigInt(features);
  if (mask < 0n || mask > 0xffff_ffff_ffff_ffffn) throw new RangeError("scene support features must be a u64 bit mask");
  const requiredRaw = xySceneSupportReason(Number(requestVersion), mask, 0, 0n);
  if (requiredRaw === USIZE_MAX_64) throw new RangeError("invalid Scene support request version or feature mask");
  const required = Number(requiredRaw);
  if (required === 0) return "";
  const output = new Uint8Array(required);
  const written = xySceneSupportReason(Number(requestVersion), mask, u8Ptr(output), BigInt(required));
  if (Number(written) !== required) throw new Error("native Scene support predicate returned an inconsistent length");
  return new TextDecoder("utf-8", { fatal: true }).decode(output);
}

function significantSceneAxisKeys(options) {
  return Object.entries(options ?? {})
    .filter(([, value]) => {
      if (value == null || value === false) return false;
      if (Array.isArray(value) && value.length === 0) return false;
      if (typeof value === "object" && !Array.isArray(value) && Object.keys(value).length === 0) return false;
      return true;
    })
    .map(([key]) => key);
}

function packFigureSupport(figure, { colorbarUnsupported = false } = {}) {
  const chromeStyles = figure.chromeStyles ?? figure.chrome_styles ?? {};
  const annotations = [...(figure.annotations ?? [])];
  let flags = 0;
  if (figure.coords !== "cartesian") flags |= 1 << 0;
  if (Object.values(chromeStyles).some((style) => style?.fontFamily != null || style?.["font-family"] != null)) flags |= 1 << 1;
  if (
    figure.className
    || figure.class_name
    || Object.keys(figure.classNames ?? figure.class_names ?? {}).length
    || Object.keys(chromeStyles).length
    || Object.keys(figure.style ?? {}).some((key) => !["background", "--chart-bg"].includes(key))
    || annotations.some((annotation) => annotation.className || annotation.class_name)
  ) flags |= 1 << 2;
  if ((figure.traces ?? []).some((trace) => (
    trace.color_target != null
    || (trace.style?.fill != null && typeof trace.style.fill === "object")
    || (
      trace.color != null
      && typeof trace.color === "object"
      && (trace.color.mode !== "constant" || trace.color.color == null)
    )
  ))) flags |= 1 << 3;
  if (colorbarUnsupported) flags |= 1 << 4;
  if ((figure.extraLegends ?? figure.extra_legends ?? []).length) flags |= 1 << 5;
  if (annotations.some((annotation) => !["callout", "arrow", "text"].includes(annotation.kind) && annotation.text != null && annotation.text !== "")) flags |= 1 << 7;
  const traces = [...(figure.traces ?? [])];
  const axisEntries = [];
  const seenAxes = new Set();
  const addAxis = (axisId, options) => {
    if (seenAxes.has(axisId)) return;
    seenAxes.add(axisId);
    axisEntries.push([axisId, options ?? {}]);
  };
  if (figure.axis_options && typeof figure.axis_options === "object") {
    for (const [axisId, options] of Object.entries(figure.axis_options)) addAxis(axisId, options);
  }
  addAxis("x", figure.xAxis ?? figure.x_axis ?? figure.axis_options?.x ?? {});
  addAxis("y", figure.yAxis ?? figure.y_axis ?? figure.axis_options?.y ?? {});
  const parts = [new Uint8Array(20)];
  const header = new DataView(parts[0].buffer);
  parts[0].set([88, 89, 70, 83]); // XYFS
  header.setUint32(4, 2, true);
  header.setUint32(8, flags, true);
  header.setUint32(12, axisEntries.length, true);
  header.setUint32(16, traces.length, true);
  for (const [axisId, options] of axisEntries) {
    const axisCode = axisId === "x" ? 0 : axisId === "y" ? 1 : 255;
    const keys = significantSceneAxisKeys(options);
    const axis = new Uint8Array(8);
    axis[0] = axisCode;
    new DataView(axis.buffer).setUint32(4, keys.length, true);
    parts.push(axis);
    for (const key of keys) parts.push(encodeExportKey(key));
  }
  for (const trace of traces) {
    const { flags: traceFlags, kind } = figureTraceSupport(figure, trace);
    const kindBytes = new TextEncoder().encode(kind.slice(0, 32));
    const row = new Uint8Array(8 + kindBytes.length);
    const view = new DataView(row.buffer);
    view.setUint16(0, traceFlags, true);
    row[2] = kindBytes.length;
    row.set(kindBytes, 8);
    parts.push(row);
  }
  return concatBytes(parts);
}

function sceneFigureSupportReason(figure, { colorbarUnsupported = false } = {}) {
  const envelope = packFigureSupport(figure, { colorbarUnsupported });
  const requiredRaw = xySceneFigureSupportReason(
    envelope.length ? u8Ptr(envelope) : 0,
    BigInt(envelope.length),
    0,
    0n,
  );
  if (requiredRaw === USIZE_MAX_64) throw new RangeError("invalid scene figure support envelope");
  const required = Number(requiredRaw);
  if (required === 0) return "";
  const output = new Uint8Array(required);
  const written = xySceneFigureSupportReason(
    envelope.length ? u8Ptr(envelope) : 0,
    BigInt(envelope.length),
    u8Ptr(output),
    BigInt(required),
  );
  if (Number(written) !== required) throw new Error("native Scene figure support predicate returned an inconsistent length");
  return new TextDecoder("utf-8", { fatal: true }).decode(output);
}

const PUBLIC_EXPORT_KIND_CODES = {
  scatter: 0, line: 1, bar: 2, column: 3, histogram: 4, violin: 5, box: 6,
  box_whisker: 7, box_median: 8, segments: 9, errorbar: 10, stem: 11, area: 12,
  error_band: 13, ribbon: 14, triangle_mesh: 15, hexbin: 16, heatmap: 17,
};
const STYLE_KIND_CODES = { ...PUBLIC_EXPORT_KIND_CODES, contour: 18 };
const MS_LINE_ONLY = 1 << 0;
const MS_HAS_FILL = 1 << 1;
const MS_HAS_STROKE = 1 << 2;
const MS_HAS_LINE_COLOR = 1 << 3;
const MS_HAS_STROKE_WIDTH = 1 << 5;
const MS_HAS_WIDTH = 1 << 6;
const MS_HAS_LINE_WIDTH = 1 << 7;

function encodeUtf8(value) {
  return new TextEncoder().encode(String(value ?? ""));
}

function packMarkStyleRecord(trace, opacity, fillOpacity, strokeOpacity, lineOpacity, symbolCode) {
  const style = trace.style ?? {};
  let flags = 0;
  if (trace.kind === "scatter" && symbolCode >= SYMBOL_CODES.get("plus_line")) flags |= MS_LINE_ONLY;
  const parts = [];
  let fill = new Uint8Array(0);
  if (Object.hasOwn(style, "fill")) {
    if (typeof style.fill !== "string") throw new RangeError(`Scene v12 does not yet encode ${trace.kind} non-CSS fills`);
    flags |= MS_HAS_FILL;
    fill = encodeUtf8(style.fill);
  }
  let stroke = new Uint8Array(0);
  if (Object.hasOwn(style, "stroke")) {
    flags |= MS_HAS_STROKE;
    stroke = encodeUtf8(style.stroke);
  }
  let lineColor = new Uint8Array(0);
  if (Object.hasOwn(style, "line_color") || Object.hasOwn(style, "lineColor")) {
    flags |= MS_HAS_LINE_COLOR;
    lineColor = encodeUtf8(style.line_color ?? style.lineColor);
  }
  const color = style.color
    ?? (typeof trace.color === "string" ? trace.color : trace.color?.color)
    ?? "#3987e5";
  const colorBytes = encodeUtf8(color);
  let strokeWidth = 0;
  let width = 0;
  let lineWidth = 0;
  if (Object.hasOwn(style, "stroke_width") || Object.hasOwn(style, "strokeWidth")) {
    flags |= MS_HAS_STROKE_WIDTH;
    strokeWidth = Number(style.stroke_width ?? style.strokeWidth);
  }
  if (Object.hasOwn(style, "width")) {
    flags |= MS_HAS_WIDTH;
    width = Number(style.width);
  }
  if (Object.hasOwn(style, "line_width") || Object.hasOwn(style, "lineWidth")) {
    flags |= MS_HAS_LINE_WIDTH;
    lineWidth = Number(style.line_width ?? style.lineWidth);
  }
  const prefix = new Uint8Array(52);
  const view = new DataView(prefix.buffer);
  prefix[0] = STYLE_KIND_CODES[trace.kind] ?? 255;
  prefix[1] = flags;
  view.setFloat32(4, Number(opacity), true);
  view.setFloat32(8, Number(fillOpacity), true);
  view.setFloat32(12, Number(strokeOpacity), true);
  view.setFloat32(16, Number(lineOpacity), true);
  view.setFloat64(20, strokeWidth, true);
  view.setFloat64(28, width, true);
  view.setFloat64(36, lineWidth, true);
  view.setUint16(44, fill.length, true);
  view.setUint16(46, stroke.length, true);
  view.setUint16(48, lineColor.length, true);
  view.setUint16(50, colorBytes.length, true);
  parts.push(prefix, fill, stroke, lineColor, colorBytes);
  return concatBytes(parts);
}

function resolveMarkStyle(trace, opacity, fillOpacity, strokeOpacity, lineOpacity, symbolCode) {
  const record = packMarkStyleRecord(trace, opacity, fillOpacity, strokeOpacity, lineOpacity, symbolCode);
  const envelope = new Uint8Array(16 + record.length);
  const view = new DataView(envelope.buffer);
  envelope.set(encodeUtf8("XYMS").slice(0, 4), 0);
  view.setUint32(4, 1, true);
  view.setUint32(8, 1, true);
  envelope.set(record, 16);
  const out = new Uint8Array(16);
  const code = xySceneResolveMarkStyles(u8Ptr(envelope), BigInt(envelope.length), u8Ptr(out), BigInt(out.length));
  if (code !== 1) throw new RangeError("invalid mark style envelope");
  return {
    fillRgba: Array.from(out.subarray(0, 4)),
    strokeRgba: Array.from(out.subarray(4, 8)),
    strokeWidth: new DataView(out.buffer, out.byteOffset + 8, 8).getFloat64(0, true),
  };
}

function canonicalExportKey(key) {
  return String(key).replace(/[A-Z]/g, (ch) => `_${ch.toLowerCase()}`);
}

function encodeExportKey(key) {
  const bytes = new TextEncoder().encode(canonicalExportKey(key).slice(0, 256));
  const out = new Uint8Array(2 + bytes.length);
  out[0] = bytes.length & 0xff;
  out[1] = (bytes.length >> 8) & 0xff;
  out.set(bytes, 2);
  return out;
}

function concatBytes(parts) {
  const total = parts.reduce((sum, part) => sum + part.length, 0);
  const out = new Uint8Array(total);
  let offset = 0;
  for (const part of parts) {
    out.set(part, offset);
    offset += part.length;
  }
  return out;
}

function exportColumn(trace, name) {
  const value = trace[name];
  if (value == null) return null;
  return value.values ?? value;
}

function exportColumnLen(column) {
  return column == null ? 0 : column.length;
}

function exportColumnFinite(column) {
  if (column == null) return false;
  for (let index = 0; index < column.length; index += 1) {
    if (!Number.isFinite(Number(column[index]))) return false;
  }
  return true;
}

function exportArraysEqual(left, right) {
  if (left == null || right == null || left.length !== right.length) return false;
  for (let index = 0; index < left.length; index += 1) {
    if (Number(left[index]) !== Number(right[index])) return false;
  }
  return true;
}

function significantExportKeys(record) {
  return Object.entries(record ?? {})
    .filter(([, value]) => value != null && value !== false)
    .map(([key]) => key);
}

function packPublicExportSupport(figure, { width = null, height = null } = {}) {
  let flags = 0;
  if (width == null && !Number.isInteger(figure.width)) flags |= 1 << 0;
  if (height == null && !Number.isInteger(figure.height)) flags |= 1 << 1;
  const chrome = figure.chromeStyles ?? figure.chrome_styles;
  if (chrome && Object.keys(chrome).length) flags |= 1 << 2;
  const titleOptions = figure.titleOptions ?? figure.title_options;
  if (Array.isArray(titleOptions) ? titleOptions.length : titleOptions) flags |= 1 << 3;
  const styleKeys = Object.keys(figure.style ?? {});
  const legend = figure.legend ?? figure.legend_options ?? {};
  const legendKeys = Object.keys(legend);
  const colorbar = figure.colorbarOptions ?? figure.colorbar_options ?? {};
  const colorbarKeys = Object.keys(colorbar ?? {});
  const annotations = [...(figure.annotations ?? [])];
  const traces = [...(figure.traces ?? [])];
  const axisEntries = [];
  const seenAxes = new Set();
  const addAxis = (axisId, options) => {
    if (seenAxes.has(axisId)) return;
    seenAxes.add(axisId);
    axisEntries.push([axisId, options ?? {}]);
  };
  if (figure.axis_options && typeof figure.axis_options === "object") {
    for (const [axisId, options] of Object.entries(figure.axis_options)) addAxis(axisId, options);
  }
  addAxis("x", figure.xAxis ?? figure.x_axis ?? figure.axis_options?.x ?? {});
  addAxis("y", figure.yAxis ?? figure.y_axis ?? figure.axis_options?.y ?? {});

  const parts = [new Uint8Array(36)];
  const header = new DataView(parts[0].buffer);
  parts[0].set([88, 89, 69, 80]);
  header.setUint32(4, 1, true);
  header.setUint32(8, flags, true);
  header.setUint32(12, styleKeys.length, true);
  header.setUint32(16, legendKeys.length, true);
  header.setUint32(20, colorbarKeys.length, true);
  header.setUint32(24, axisEntries.length, true);
  header.setUint32(28, annotations.length, true);
  header.setUint32(32, traces.length, true);
  for (const key of styleKeys) parts.push(encodeExportKey(key));
  for (const key of legendKeys) parts.push(encodeExportKey(key));
  for (const key of colorbarKeys) parts.push(encodeExportKey(key));

  for (const [axisId, options] of axisEntries) {
    const axisCode = axisId === "x" ? 0 : axisId === "y" ? 1 : 255;
    const authored = options.type;
    const authoredCode = authored == null ? 0 : authored === "linear" ? 1 : authored === "log" ? 2 : authored === "symlog" ? 3 : 255;
    const forced = options.type ?? options.kind;
    const resolvedCode = forced === "time" ? 1 : forced === "category" ? 2 : 0;
    const domain = options.domain ?? figure._axisRange?.[axisId];
    const side = options.side;
    const sideCode = side == null ? 0 : side === "bottom" ? 1 : side === "left" ? 2 : side === "top" ? 3 : side === "right" ? 4 : 255;
    const keys = significantExportKeys(options);
    const axis = new Uint8Array(8);
    axis[0] = axisCode;
    axis[1] = resolvedCode;
    axis[2] = authoredCode;
    axis[3] = Number(domain != null);
    axis[4] = sideCode;
    axis[5] = 0;
    axis[6] = keys.length & 0xff;
    axis[7] = (keys.length >> 8) & 0xff;
    parts.push(axis);
    for (const key of keys) parts.push(encodeExportKey(key));
  }

  const annotationKinds = { text: 1, rule: 2, band: 3, marker: 4, arrow: 5, callout: 6 };
  for (const annotation of annotations) {
    if (annotation == null || typeof annotation !== "object" || Array.isArray(annotation)) {
      const row = new Uint8Array(4);
      row[1] = 1 << 4;
      parts.push(row);
      continue;
    }
    const kindCode = annotationKinds[String(annotation.kind)] ?? 0;
    let flagsAnn = 0;
    if (Object.hasOwn(annotation, "wrap")) flagsAnn |= 1 << 0;
    if (Object.hasOwn(annotation, "dx")) flagsAnn |= 1 << 1;
    if (Object.hasOwn(annotation, "dy")) flagsAnn |= 1 << 2;
    if (Object.hasOwn(annotation, "anchor")) flagsAnn |= 1 << 3;
    const fields = Object.keys(annotation);
    const row = new Uint8Array(4);
    row[0] = kindCode;
    row[1] = flagsAnn;
    row[2] = fields.length & 0xff;
    row[3] = (fields.length >> 8) & 0xff;
    parts.push(row);
    for (const key of fields) parts.push(encodeExportKey(key));
  }

  for (const [traceIndex, trace] of traces.entries()) {
    const style = trace.style ?? {};
    const opacity = Number(style.opacity ?? 1);
    if (!Number.isFinite(opacity) || opacity < 0 || opacity > 1) {
      throw new RangeError("trace opacity must be finite and in [0, 1]");
    }
    const kindCode = PUBLIC_EXPORT_KIND_CODES[trace.kind] ?? 255;
    const step = { pre: 1, mid: 2, post: 3 }[style.step] ?? 0;
    const prev = traceIndex ? traces[traceIndex - 1] : null;
    const prev2 = traceIndex >= 2 ? traces[traceIndex - 2] : null;
    const prev3 = traceIndex >= 3 ? traces[traceIndex - 3] : null;
    const xv = exportColumn(trace, "x");
    const yv = exportColumn(trace, "y");
    const x0 = exportColumn(trace, "x0");
    const y0 = exportColumn(trace, "y0");
    const x1 = exportColumn(trace, "x1");
    const y1 = exportColumn(trace, "y1");
    const mesh = [x0, y0, x1, y1, xv, yv];
    let flagsTr = 0;
    if (xv != null) flagsTr |= 1 << 0;
    if (yv != null) flagsTr |= 1 << 1;
    if (xv != null && yv != null && exportColumnLen(xv) === exportColumnLen(yv)) flagsTr |= 1 << 2;
    if (exportColumnFinite(xv)) flagsTr |= 1 << 3;
    if (exportColumnFinite(yv)) flagsTr |= 1 << 4;
    if (x0 != null && y0 != null && x1 != null && y1 != null) {
      flagsTr |= 1 << 5;
      const lengths = new Set([exportColumnLen(x0), exportColumnLen(y0), exportColumnLen(x1), exportColumnLen(y1)]);
      if (lengths.size === 1) flagsTr |= 1 << 6;
    }
    if (mesh.every((column) => column != null)) {
      flagsTr |= 1 << 7;
      const meshLengths = new Set(mesh.map(exportColumnLen));
      if (meshLengths.size === 1) flagsTr |= 1 << 8;
      if (mesh.every(exportColumnFinite)) flagsTr |= 1 << 9;
    }
    if (style.joined_fill || style.joinedFill) flagsTr |= 1 << 10;
    let heatmapRows = 0, heatmapCols = 0, heatmapValues = 0;
    if (trace.kind === "heatmap") {
      if (style.truecolor || style.colormap != null || trace.rgba_grid != null || trace.rgba != null) flagsTr |= 1 << 11;
      const shape = trace.grid_shape ?? trace.gridShape;
      const grid = exportColumn(trace, "grid");
      const hx = xv, hy = yv;
      if (Array.isArray(shape) && shape.length === 2) {
        const rows = Number(shape[0]), cols = Number(shape[1]);
        if (Number.isInteger(rows) && Number.isInteger(cols) && rows >= 1 && cols >= 1) {
          heatmapRows = rows;
          heatmapCols = cols;
          flagsTr |= 1 << 12;
          if (grid != null) heatmapValues = grid.length;
          if (
            hx != null && hy != null && hx.length === 2 && hy.length === 2
            && [hx[0], hx[1], hy[0], hy[1]].every((value) => Number.isFinite(Number(value)))
            && Number(hx[0]) < Number(hx[1]) && Number(hy[0]) < Number(hy[1])
          ) flagsTr |= 1 << 13;
          if (grid != null && exportColumnFinite(grid)) flagsTr |= 1 << 14;
        }
      }
    }
    if (xv != null && yv != null && exportColumnLen(xv) === exportColumnLen(yv)) flagsTr |= 1 << 15;
    if (exportColumnFinite(xv) && exportColumnFinite(yv)) flagsTr |= 1 << 16;
    if ((style.stroke_width ?? style.strokeWidth) != null && style.stroke == null) flagsTr |= 1 << 17;
    const prevX1 = prev && exportColumn(prev, "x1");
    const prevY1 = prev && exportColumn(prev, "y1");
    if (prev != null && xv != null && yv != null && prevX1 != null && prevY1 != null && exportArraysEqual(xv, prevX1) && exportArraysEqual(yv, prevY1)) {
      flagsTr |= 1 << 18;
    }
    if (prev != null && (trace.x_axis ?? "x") === (prev.x_axis ?? "x") && (trace.y_axis ?? "y") === (prev.y_axis ?? "y")) {
      flagsTr |= 1 << 19;
    }
    if (exportColumnFinite(xv) && exportColumnFinite(yv)) flagsTr |= 1 << 20;
    let symbol = style.symbol ?? "circle";
    if (typeof symbol !== "string") {
      flagsTr |= 1 << 21;
      symbol = "";
    }
    const role = style.role == null ? "" : String(style.role);
    const reduce = style.reduce == null ? "" : String(style.reduce);
    let hexDx = Number.NaN, hexDy = Number.NaN;
    if (trace.kind === "hexbin") {
      hexDx = Number(style.hex_dx ?? style.hexDx ?? style.dx);
      hexDy = Number(style.hex_dy ?? style.hexDy ?? style.dy);
    }
    const styleKeysTrace = Object.entries(style).filter(([, value]) => value != null).map(([key]) => key);
    const roleBytes = new TextEncoder().encode(role);
    const symbolBytes = new TextEncoder().encode(symbol);
    const reduceBytes = new TextEncoder().encode(reduce);
    const nMesh = (flagsTr & (1 << 7)) ? exportColumnLen(xv) : 0;
    const row = new Uint8Array(72);
    const view = new DataView(row.buffer);
    row[0] = kindCode;
    row[1] = step;
    row[2] = prev == null ? 255 : (PUBLIC_EXPORT_KIND_CODES[prev.kind] ?? 255);
    row[3] = prev2 == null ? 255 : (PUBLIC_EXPORT_KIND_CODES[prev2.kind] ?? 255);
    row[4] = prev3 == null ? 255 : (PUBLIC_EXPORT_KIND_CODES[prev3.kind] ?? 255);
    view.setUint32(8, flagsTr, true);
    view.setUint32(12, xv != null ? exportColumnLen(xv) : nMesh, true);
    view.setUint32(16, exportColumnLen(yv), true);
    view.setUint32(20, exportColumnLen(x0), true);
    view.setUint32(24, exportColumnLen(y0), true);
    view.setUint32(28, exportColumnLen(x1), true);
    view.setUint32(32, exportColumnLen(y1), true);
    view.setUint32(36, heatmapRows, true);
    view.setUint32(40, heatmapCols, true);
    view.setUint32(44, heatmapValues, true);
    view.setUint16(48, styleKeysTrace.length, true);
    view.setUint16(50, roleBytes.length, true);
    view.setUint16(52, symbolBytes.length, true);
    view.setUint16(54, reduceBytes.length, true);
    view.setFloat64(56, hexDx, true);
    view.setFloat64(64, hexDy, true);
    parts.push(row, roleBytes, symbolBytes, reduceBytes);
    for (const key of styleKeysTrace) parts.push(encodeExportKey(key));
  }
  return concatBytes(parts);
}

/** Return Rust's public-export diagnostic, or null when the Scene route applies. */
export function sceneExportSupportReason(figure, { width = null, height = null } = {}) {
  const envelope = packPublicExportSupport(figure, { width, height });
  const requiredRaw = xyScenePublicExportReason(u8Ptr(envelope), BigInt(envelope.length), 0, 0n);
  if (requiredRaw === USIZE_MAX_64) throw new RangeError("invalid scene public export support envelope");
  const required = Number(requiredRaw);
  let reason = "";
  if (required !== 0) {
    const output = new Uint8Array(required);
    const written = xyScenePublicExportReason(u8Ptr(envelope), BigInt(envelope.length), u8Ptr(output), BigInt(required));
    if (Number(written) !== required) throw new Error("native Scene public export predicate returned an inconsistent length");
    reason = new TextDecoder("utf-8", { fatal: true }).decode(output);
  }
  if (reason) return reason;
  let publicTriangleMeshCount = 0;
  for (const trace of figure.traces ?? []) {
    if (POLYFILL_KINDS.has(trace.kind)) {
      const mesh = [trace.x0, trace.y0, trace.x1, trace.y1, trace.x, trace.y];
      if (mesh.every((column) => column != null)) publicTriangleMeshCount += mesh[0].length;
    } else if (HEXBIN_KINDS.has(trace.kind) && trace.x != null) {
      publicTriangleMeshCount += trace.x.length;
    }
  }
  let scene;
  try {
    scene = figureSceneV3(figure);
  } catch (err) {
    if (err instanceof RangeError) {
      if (err.message === "invalid canonical scene plot layout") return "XYG_SCENE_UNSUPPORTED_VIEWPORT";
      return err.message;
    }
    throw err;
  }
  if (publicTriangleMeshCount) {
    try {
      sceneBrowserPainter(scene);
    } catch (err) {
      if (err instanceof RangeError && err.message === "invalid canonical scene for browser painter") {
        return "XYG_SCENE_UNSUPPORTED_PUBLIC_TRIANGLE_MESH";
      }
      throw err;
    }
  }
  return null;
}

const LEGEND_LOCATIONS = new Map([["upper right", 0], ["upper left", 1], ["lower left", 2], ["lower right", 3], ["center right", 4], ["center left", 5], ["upper center", 6], ["lower center", 7], ["center", 8]]);

function legendColumnValues(column) {
  if (column == null) return null;
  if (ArrayBuffer.isView(column) || Array.isArray(column)) return asF64Array(column);
  if (column.values != null && typeof column.values !== "function") return asF64Array(column.values);
  return null;
}

function legendAxisSpec(figure, axisId) {
  const options = figure.axis_options?.[axisId] ?? figure[`${axisId}Axis`] ?? figure[`${axisId}_axis`] ?? {};
  let lo, hi;
  try {
    [lo, hi] = figure._range(axisId);
  } catch {
    return null;
  }
  const reverse = lo > hi;
  if (reverse) [lo, hi] = [hi, lo];
  if (!(Number.isFinite(lo) && Number.isFinite(hi)) || hi <= lo) return null;
  const scale = options.type ?? options.scale ?? options.kind ?? "linear";
  const constant = options.constant == null || Number(options.constant) === 0 ? 1 : Number(options.constant);
  return { domain: [lo, hi], reverse, scale, constant };
}

function resolveLegendBestLoc(figure) {
  const series = [];
  const labelLens = [];
  for (const trace of figure.traces ?? []) {
    if (trace.hidden) continue;
    if (trace.name != null && String(trace.name).length > 0) labelLens.push(String(trace.name).length);
    const xv = legendColumnValues(trace.x);
    const yv = legendColumnValues(trace.y);
    if (xv == null || yv == null || xv.length !== yv.length) continue;
    const xSpec = legendAxisSpec(figure, trace.x_axis ?? "x");
    const ySpec = legendAxisSpec(figure, trace.y_axis ?? "y");
    if (xSpec == null || ySpec == null) continue;
    const projected = legendNormalize(xv, yv, {
      xDomain: xSpec.domain,
      yDomain: ySpec.domain,
      xReverse: xSpec.reverse,
      yReverse: ySpec.reverse,
      xScale: xSpec.scale,
      yScale: ySpec.scale,
      xConstant: xSpec.constant,
      yConstant: ySpec.constant,
    });
    if (projected != null) series.push(projected);
  }
  return legendBestLoc(series, labelLens);
}

function legendInput(figure, entries, styles) {
  if (figure.showLegend === false || entries.length === 0) return new Uint8Array();
  const options = figure.legend ?? {};
  const allowed = new Set(["loc", "title", "ncols", "style", "highlight", "toggle"]);
  if (Object.keys(options).some((key) => !allowed.has(key)) || Number(options.ncols ?? 1) !== 1) throw new RangeError("Scene v12 primary legends do not yet encode anchors, multiple columns, or custom content");
  if (["toggle", "highlight"].some((key) => Object.hasOwn(options, key) && options[key] !== false)) throw new RangeError("Scene v12 primary legends are static; toggle and highlight must be false");
  const authoredLoc = options.loc;
  let loc = authoredLoc ?? "upper right";
  if (loc === "best") loc = resolveLegendBestLoc(figure);
  if (!LEGEND_LOCATIONS.has(loc)) throw new RangeError(`Scene v12 does not support legend location ${JSON.stringify(loc)}`);
  const style = options.style ?? {};
  const allowedStyle = new Set(["background", "color", "font_size", "fontSize", "title_font_size", "titleFontSize"]);
  if (Object.keys(style).some((key) => !allowedStyle.has(key))) throw new RangeError("Scene v12 legends support only background, color, font_size, and title_font_size");
  const authoredFontSize = style.font_size ?? style.fontSize, authoredTitleFontSize = style.title_font_size ?? style.titleFontSize;
  const fontSize = authoredFontSize == null ? 0 : Number(authoredFontSize), titleFontSize = authoredTitleFontSize == null ? 0 : Number(authoredTitleFontSize);
  if (!((authoredFontSize == null || (fontSize >= 1 && fontSize <= 1000)) && (authoredTitleFontSize == null || (titleFontSize >= 1 && titleFontSize <= 1000)))) throw new RangeError("legend font sizes must be finite and in [1, 1000]");
  const encoder = new TextEncoder(), title = encoder.encode(String(options.title ?? "")), labels = entries.map((entry) => encoder.encode(entry.label));
  const textLength = title.length + labels.reduce((sum, label) => sum + label.length, 0);
  if (entries.length > 128 || title.length > 4096 || textLength > 16384 || labels.some((label) => label.length === 0 || label.length > 4096)) throw new RangeError("Scene v12 legend text exceeds its bounded UTF-8 limits");
  const flags = Number(authoredLoc != null) | (Number(authoredFontSize != null) << 1) | (Number(authoredTitleFontSize != null) << 2) | (Number(Object.hasOwn(style, "color")) << 3) | (Number(Object.hasOwn(style, "background")) << 4);
  const textRgba = Object.hasOwn(style, "color") ? rgba8(style.color, 1, "legend color") : new Uint8Array(4);
  const frameFill = Object.hasOwn(style, "background") ? rgba8(style.background, 1, "legend background") : new Uint8Array(4);
  const meta = new Uint8Array(entries.length * 16);
  const metaView = new DataView(meta.buffer);
  const concatenated = new Uint8Array(textLength - title.length);
  const labelLens = new Uint32Array(entries.length);
  let labelAt = 0;
  for (const [index, entry] of entries.entries()) {
    const paint = styles[entry.styleRef];
    const offset = index * 16;
    metaView.setUint32(offset, entry.styleRef, true);
    meta[offset + 4] = entry.kind;
    meta[offset + 5] = entry.symbol;
    meta.set(paint.fillRgba, offset + 8);
    meta.set(paint.strokeRgba, offset + 12);
    const label = labels[index];
    labelLens[index] = label.length;
    concatenated.set(label, labelAt);
    labelAt += label.length;
  }
  const out = new Uint8Array(48 + entries.length * 24 + textLength);
  const code = xyScenePackLegend(
    LEGEND_LOCATIONS.get(loc),
    flags,
    fontSize,
    titleFontSize,
    u8Ptr(textRgba),
    u8Ptr(frameFill),
    title.length ? u8Ptr(title) : 0,
    BigInt(title.length),
    entries.length,
    meta.length ? u8Ptr(meta) : 0,
    BigInt(meta.length),
    u32Ptr(labelLens),
    concatenated.length ? u8Ptr(concatenated) : 0,
    BigInt(concatenated.length),
    u8Ptr(out),
    BigInt(out.length),
  );
  if (code === -5) throw new RangeError("legend font sizes must be finite and in [1, 1000]");
  if (code < 0) throw new RangeError("invalid scene legend packing");
  return out.subarray(0, code);
}

function colorbarInput(figure) {
  const options = figure.colorbarOptions ?? figure.colorbar_options;
  if (options == null) return new Uint8Array();
  if (typeof options !== "object" || Array.isArray(options)) throw new RangeError("Scene v19 colorbar requires literal RGBA stops");
  const allowed = new Set(["domain", "stops", "side", "title", "text_rgba", "ticks", "minor_ticks"]);
  if (Object.keys(options).some((key) => !allowed.has(key))) throw new RangeError("Scene v19 colorbar requires bounded literal RGBA stops");
  const domain = options.domain, stops = options.stops;
  if (!Array.isArray(domain) || domain.length !== 2 || !Array.isArray(stops) || stops.length < 2 || stops.length > 16) throw new RangeError("Scene v19 colorbar requires a domain and 2–16 stops");
  const lo = Number(domain[0]), hi = Number(domain[1]);
  const title = options.title ?? "";
  if (typeof title !== "string") throw new TypeError("Scene v19 colorbar title must be a string");
  const titleBytes = new TextEncoder().encode(title), text = asUnsignedArray(options.text_rgba ?? [32, 32, 32, 255], "colorbar text_rgba", 255, Uint8Array);
  requireLength(text, 4, "colorbar text_rgba"); if (titleBytes.length > 4096) throw new RangeError("Scene v19 colorbar title is limited to 4,096 UTF-8 bytes");
  const rawTicks = options.ticks;
  if (rawTicks != null && (!Array.isArray(rawTicks) || rawTicks.length > 32)) throw new RangeError("Scene v19 colorbar ticks are limited to 32 finite ordered values");
  const ticks = rawTicks == null ? [] : rawTicks.map(Number);
  const minorTicks = options.minor_ticks ?? false;
  if (typeof minorTicks !== "boolean") throw new TypeError("Scene v19 colorbar minor_ticks must be a boolean");
  const side = options.side ?? "right"; if (side !== "right" && side !== "bottom") throw new RangeError("Scene v19 colorbar side is right or bottom");
  const stopValues = new Float64Array(stops.length);
  const stopRgba = new Uint8Array(stops.length * 4);
  for (const [index, stop] of stops.entries()) {
    if (!Array.isArray(stop) || stop.length !== 2) throw new TypeError("colorbar stops are [value, RGBA]");
    stopValues[index] = Number(stop[0]);
    const rgba = asUnsignedArray(stop[1], `colorbar stops[${index}]`, 255, Uint8Array);
    requireLength(rgba, 4, `colorbar stops[${index}]`);
    stopRgba.set(rgba, index * 4);
  }
  const tickValues = Float64Array.from(ticks);
  const out = new Uint8Array(56 + stops.length * 12 + ticks.length * 8 + titleBytes.length);
  const code = xyScenePackColorbar(
    Number(side === "bottom") | (Number(minorTicks) << 2),
    lo,
    hi,
    u8Ptr(text),
    titleBytes.length ? u8Ptr(titleBytes) : 0,
    BigInt(titleBytes.length),
    stops.length,
    f64Ptr(stopValues),
    u8Ptr(stopRgba),
    BigInt(stopRgba.length),
    ticks.length,
    ticks.length ? f64Ptr(tickValues) : 0,
    u8Ptr(out),
    BigInt(out.length),
  );
  if (code === -5) throw new RangeError("Scene v19 colorbar domain must be finite and ordered");
  if (code === -6) throw new RangeError("colorbar stops must span the domain");
  if (code === -7) throw new RangeError("Scene v19 colorbar ticks are limited to 32 finite ordered values");
  if (code < 0) throw new RangeError("invalid scene colorbar packing");
  return out.subarray(0, code);
}

const MAX_SCENE_ANNOTATION_INPUT_BYTES = 28
  + 12 + 128 * 40 + 4096
  + 12 + 128 * 32 + 4096
  + 12 + 128 * 60
  + 12 + 128 * 76 + 8192
  + 12 + 128 * 68 + 8192;

function packAnnotationEnvelope({ texts, attached, arrows, callouts, wrapped }) {
  if (!texts.length && !attached.length && !arrows.length && !callouts.length && !wrapped.length) {
    return new Uint8Array();
  }
  const textMeta = new Uint8Array(texts.length * 40);
  const textView = new DataView(textMeta.buffer);
  const textLens = new Uint32Array(texts.length);
  texts.forEach((row, index) => {
    const at = index * 40;
    textView.setFloat64(at, row.x, true);
    textView.setFloat64(at + 8, row.y, true);
    textMeta.set(row.rgba, at + 16);
    textMeta.set(row.labelFill ?? [0, 0, 0, 0], at + 20);
    textMeta.set(row.labelBorder?.rgba ?? [0, 0, 0, 0], at + 24);
    textView.setFloat64(at + 28, row.labelBorder?.width ?? 0, true);
    textMeta[at + 36] = (row.labelFill ? 1 : 0) | (row.labelBorder ? 2 : 0);
    textLens[index] = row.text.length;
  });
  const textBytes = concatBytes(texts.map((row) => row.text));
  const attachedMeta = new Uint8Array(attached.length * 32);
  const attachedView = new DataView(attachedMeta.buffer);
  const attachedLens = new Uint32Array(attached.length);
  attached.forEach((row, index) => {
    const at = index * 32;
    attachedView.setBigUint64(at, row.stableId, true);
    attachedMeta.set(row.rgba, at + 8);
    attachedMeta.set(row.labelFill ?? [0, 0, 0, 0], at + 12);
    attachedMeta.set(row.labelBorder?.rgba ?? [0, 0, 0, 0], at + 16);
    attachedView.setFloat64(at + 20, row.labelBorder?.width ?? 0, true);
    attachedMeta[at + 28] = (row.labelFill ? 1 : 0) | (row.labelBorder ? 2 : 0);
    attachedLens[index] = row.text.length;
  });
  const attachedBytes = concatBytes(attached.map((row) => row.text));
  const arrowMeta = new Uint8Array(arrows.length * 60);
  const arrowView = new DataView(arrowMeta.buffer);
  arrows.forEach((row, index) => {
    const at = index * 60;
    arrowView.setBigUint64(at, row.stableId, true);
    arrowView.setFloat64(at + 8, row.x0, true);
    arrowView.setFloat64(at + 16, row.y0, true);
    arrowView.setFloat64(at + 24, row.x1, true);
    arrowView.setFloat64(at + 32, row.y1, true);
    arrowMeta.set(row.rgba, at + 40);
    arrowView.setFloat64(at + 44, row.opacity, true);
    arrowView.setFloat64(at + 52, row.width, true);
  });
  const calloutMeta = new Uint8Array(callouts.length * 76);
  const calloutView = new DataView(calloutMeta.buffer);
  const calloutLens = new Uint32Array(callouts.length);
  callouts.forEach((row, index) => {
    const at = index * 76;
    calloutView.setFloat64(at, row.x, true);
    calloutView.setFloat64(at + 8, row.y, true);
    calloutView.setFloat64(at + 16, row.dx, true);
    calloutView.setFloat64(at + 24, row.dy, true);
    calloutMeta.set(row.rgba, at + 32);
    calloutView.setFloat64(at + 36, row.opacity, true);
    calloutView.setFloat64(at + 44, row.width, true);
    calloutMeta[at + 52] = row.anchorCode;
    calloutMeta.set(row.labelFill ?? [0, 0, 0, 0], at + 56);
    calloutMeta.set(row.labelBorder?.rgba ?? [0, 0, 0, 0], at + 60);
    calloutView.setFloat64(at + 64, row.labelBorder?.width ?? 0, true);
    calloutMeta[at + 72] = (row.labelFill ? 1 : 0) | (row.labelBorder ? 2 : 0);
    calloutLens[index] = row.text.length;
  });
  const calloutBytes = concatBytes(callouts.map((row) => row.text));
  const wrappedMeta = new Uint8Array(wrapped.length * 64);
  const wrappedView = new DataView(wrappedMeta.buffer);
  const wrappedLens = new Uint32Array(wrapped.length);
  wrapped.forEach((row, index) => {
    const at = index * 64;
    wrappedView.setFloat64(at, row.x, true);
    wrappedView.setFloat64(at + 8, row.y, true);
    wrappedView.setFloat64(at + 16, row.dx, true);
    wrappedView.setFloat64(at + 24, row.dy, true);
    wrappedView.setFloat64(at + 32, row.wrap, true);
    wrappedMeta.set(rgba8(annotationColor(row.a.style ?? {}, "color", row.a.kind === "callout" ? "#344054" : "#667085", "wrapped color"), row.opacity, "wrapped"), at + 40);
    wrappedMeta.set(row.fill, at + 44);
    wrappedMeta.set(row.border?.rgba ?? [0, 0, 0, 0], at + 48);
    wrappedView.setFloat64(at + 52, row.border?.width ?? 0, true);
    wrappedMeta[at + 60] = row.a.kind === "callout" ? 1 : 0;
    wrappedMeta[at + 61] = row.anchor;
    wrappedLens[index] = row.text.length;
  });
  const wrappedBytes = concatBytes(wrapped.map((row) => row.text));
  const out = new Uint8Array(MAX_SCENE_ANNOTATION_INPUT_BYTES);
  const code = xyScenePackAnnotations(
    texts.length, textMeta.length ? u8Ptr(textMeta) : 0, BigInt(textMeta.length),
    texts.length ? u32Ptr(textLens) : 0, textBytes.length ? u8Ptr(textBytes) : 0, BigInt(textBytes.length),
    attached.length, attachedMeta.length ? u8Ptr(attachedMeta) : 0, BigInt(attachedMeta.length),
    attached.length ? u32Ptr(attachedLens) : 0, attachedBytes.length ? u8Ptr(attachedBytes) : 0, BigInt(attachedBytes.length),
    arrows.length, arrowMeta.length ? u8Ptr(arrowMeta) : 0, BigInt(arrowMeta.length),
    callouts.length, calloutMeta.length ? u8Ptr(calloutMeta) : 0, BigInt(calloutMeta.length),
    callouts.length ? u32Ptr(calloutLens) : 0, calloutBytes.length ? u8Ptr(calloutBytes) : 0, BigInt(calloutBytes.length),
    wrapped.length, wrappedMeta.length ? u8Ptr(wrappedMeta) : 0, BigInt(wrappedMeta.length),
    wrapped.length ? u32Ptr(wrappedLens) : 0, wrappedBytes.length ? u8Ptr(wrappedBytes) : 0, BigInt(wrappedBytes.length),
    u8Ptr(out), BigInt(out.length),
  );
  if (code === -5) throw new RangeError("Scene annotation geometry must be finite");
  if (code === -6) throw new RangeError("Scene annotations require nonempty NUL-free text");
  if (code === -7) throw new RangeError("Scene v23 label border requires label_background");
  if (code < 0) throw new RangeError("invalid scene annotation packing");
  return out.subarray(0, code);
}

function rectExtraFlags(style) {
  let flags = 0;
  if (style.fill != null && typeof style.fill === "object") flags |= XYFS_TRACE_RECT_GRADIENT;
  const radius = style.corner_radius ?? 0;
  if (Array.isArray(radius)) {
    if (radius.some((value) => Number(value) !== 0)) flags |= XYFS_TRACE_CORNER_RADIUS;
  } else if (Number(radius) !== 0) {
    flags |= XYFS_TRACE_CORNER_RADIUS;
  }
  if (Number(style.wedge_gap ?? 0) !== 0) flags |= XYFS_TRACE_WEDGE_GAP;
  return flags;
}

function figureTraceSupport(figure, trace) {
  const style = trace.style ?? {};
  const kind = String(trace.kind ?? "mark");
  let flags = 0;
  if (!SUPPORTED_KINDS.has(kind)) flags |= XYFS_TRACE_UNSUPPORTED_KIND;
  if ((trace.x_axis ?? "x") !== "x" || (trace.y_axis ?? "y") !== "y") flags |= XYFS_TRACE_NON_PRIMARY_AXIS;
  if (
    trace.hidden
    || style.color_channel != null
    || style.size_channel != null
    || style.stroke_channel != null
  ) flags |= XYFS_TRACE_HIDDEN_OR_PER_ITEM;
  if (
    kind === "scatter"
    && shouldUseDensity(trace.x?.length ?? 0, {
      forceDensity: Boolean(trace.force_density ?? trace.forceDensity),
      forceDirect: Boolean(trace.force_direct ?? trace.forceDirect),
      coords: figure.coords ?? "cartesian",
      perItemChannels: style.color_channel != null
        || style.size_channel != null
        || style.stroke_channel != null,
    })
  ) flags |= XYFS_TRACE_DENSITY;
  if (XYFS_DASH_KEYS.some((key) => style[key] != null)) flags |= XYFS_TRACE_DASHED_MARKERS;
  if (RECT_KINDS.has(kind) || HEATMAP_KINDS.has(kind)) flags |= rectExtraFlags(style);
  if (POLYFILL_KINDS.has(kind) && style.joined_fill) flags |= XYFS_TRACE_JOINED_FILL;
  if (HEXBIN_KINDS.has(kind) && !HEXBIN_REDUCES.has(style.reduce)) flags |= XYFS_TRACE_CUSTOM_HEX_REDUCE;
  if (
    HEATMAP_KINDS.has(kind)
    && (style.truecolor || style.colormap != null || trace.rgba_grid != null || trace.rgba != null)
  ) flags |= XYFS_TRACE_HEATMAP_COLORMAP;
  if (Object.hasOwn(style, "fill") && typeof style.fill !== "string") flags |= XYFS_TRACE_NON_CSS_FILL;
  return { flags, kind };
}

function requireEqualColumns(columns, kind, label) {
  if (columns.some((column) => column == null)) {
    throw new RangeError(`${kind} Scene v12 compilation requires four ${label} columns`);
  }
  const count = columns[0].length;
  if (columns.some((column) => column.length !== count)) {
    throw new RangeError(`Scene v12 ${kind} ${label} columns must have equal length`);
  }
  if (columns.some((column) => Array.from(column).some((value) => !Number.isFinite(value)))) {
    throw new RangeError("Scene v12 does not yet encode missing-data breaks or nonfinite coordinates");
  }
  return count;
}

/** Compile migrated cartesian marks to Scene v12. */
export function figureSceneV3(figure, { margins = null } = {}) {
  let encodedColorbar = new Uint8Array(), colorbarUnsupported = false;
  try { encodedColorbar = colorbarInput(figure); } catch { colorbarUnsupported = Boolean(figure.colorbarOptions ?? figure.colorbar_options); }
  const reason = sceneFigureSupportReason(figure, { colorbarUnsupported });
  if (reason) throw new RangeError(reason);
  const kinds = [], stableIds = [], styleRefs = [], diameter = [], symbols = [], expansionModes = [], x0 = [], y0 = [], x1 = [], y1 = [], styles = [], legendEntries = [];
  const xDomain = figure._range("x");
  const yDomain = figure._range("y");
  const sceneAxis = (axis, id, domain) => {
    const options = figure[`${axis}Axis`] ?? figure[`${axis}_axis`] ?? {};
    return {
      id,
      kind: options.kind ?? options.type ?? "linear",
      domain,
      constant: options.constant ?? 1,
      nonpositive: options.nonpositive ?? "clip",
      format: options.format ?? null,
    };
  };
  const xSceneAxis = sceneAxis("x", 1, xDomain);
  const ySceneAxis = sceneAxis("y", 2, yDomain);
  const xSceneDescriptor = axisDescriptor(xSceneAxis, "xAxis");
  const ySceneDescriptor = axisDescriptor(ySceneAxis, "yAxis");
  for (const trace of figure.traces) {
    const style = trace.style ?? {};
    const opacity = Number(style.opacity ?? 1);
    if (!Number.isFinite(opacity) || opacity < 0 || opacity > 1) throw new RangeError("trace opacity must be in [0, 1]");
    const fillOpacity = BAND_KINDS.has(trace.kind) || RIBBON_KINDS.has(trace.kind) ? Number(style.fill_opacity ?? 1) : 1;
    const strokeOpacity = BAND_KINDS.has(trace.kind) || RIBBON_KINDS.has(trace.kind) ? Number(style.stroke_opacity ?? 1) : 1;
    const lineOpacity = BAND_KINDS.has(trace.kind) ? Number(style.line_opacity ?? 1) : 1;
    if ((BAND_KINDS.has(trace.kind) || RIBBON_KINDS.has(trace.kind)) && [fillOpacity, strokeOpacity, lineOpacity].some((value) => !Number.isFinite(value) || value < 0 || value > 1)) {
      throw new RangeError("trace opacity channels must be in [0, 1]");
    }
    const symbolCode = sceneSymbolCode(style.symbol ?? 0);
    styles.push(resolveMarkStyle(trace, opacity, fillOpacity, strokeOpacity, lineOpacity, symbolCode));
    const styleRef = styles.length - 1;
    if (trace.name != null && String(trace.name).length > 0 && figure.showLegend !== false) {
      const legendKind = trace.kind === "scatter" ? 0 : STROKE_KINDS.has(trace.kind) ? 1 : 2;
      legendEntries.push({ styleRef, kind: legendKind, symbol: legendKind === 0 ? sceneSymbolCode(style.symbol ?? 0) : 0, label: String(trace.name) });
    }
    const id = Number(trace.id);

    if (RIBBON_KINDS.has(trace.kind)) {
      if (trace.color_target != null) {
        throw new RangeError("Scene v12 does not yet encode two-ended ribbon gradients");
      }
      const cols = [trace.x0, trace.x1, trace.y0, trace.y1, trace.x, trace.y];
      if (cols.some((column) => column == null)) {
        throw new RangeError("ribbon Scene v12 compilation requires six geometry columns");
      }
      const count = cols[0].length;
      if (cols.some((column) => column.length !== count)) {
        throw new RangeError("Scene v12 ribbon columns must have equal length");
      }
      appendPacked(kinds, stableIds, styleRefs, diameter, symbols, expansionModes, x0, y0, x1, y1, packTrace({
        packKind: 4, styleRef, traceId: id, columns: cols,
      }));
      continue;
    }

    if (POLYFILL_KINDS.has(trace.kind)) {
      const cols = [trace.x0, trace.y0, trace.x1, trace.y1, trace.x, trace.y];
      if (cols.some((column) => column == null)) {
        throw new RangeError("triangle_mesh Scene v12 compilation requires six vertex columns");
      }
      const count = cols[0].length;
      if (cols.some((column) => column.length !== count)) {
        throw new RangeError("Scene v12 triangle_mesh columns must have equal length");
      }
      appendPacked(kinds, stableIds, styleRefs, diameter, symbols, expansionModes, x0, y0, x1, y1, packTrace({
        packKind: 5, styleRef, traceId: id, columns: cols,
      }));
      continue;
    }

    if (HEXBIN_KINDS.has(trace.kind)) {
      const xv = trace.x;
      const yv = trace.y;
      if (xv == null || yv == null || xv.length !== yv.length) {
        throw new RangeError("Scene v12 hexbin columns must have equal length");
      }
      const dx = Number(style.hex_dx ?? style.dx);
      const dy = Number(style.hex_dy ?? style.dy);
      if (!Number.isFinite(dx) || !Number.isFinite(dy) || dx <= 0 || dy <= 0) {
        throw new RangeError("Scene v12 hexbin requires finite hex_dx/hex_dy cell pitch");
      }
      appendPacked(kinds, stableIds, styleRefs, diameter, symbols, expansionModes, x0, y0, x1, y1, packTrace({
        packKind: 6, styleRef, traceId: id, extra0: dx, extra1: dy, columns: [xv, yv],
      }));
      continue;
    }

    if (HEATMAP_KINDS.has(trace.kind)) {
      const shape = trace.grid_shape;
      if (shape == null || shape.length !== 2) {
        throw new RangeError("Scene v12 heatmap requires a rows x cols grid_shape");
      }
      const rows = Number(shape[0]);
      const cols = Number(shape[1]);
      if (!Number.isInteger(rows) || !Number.isInteger(cols) || rows < 1 || cols < 1) {
        throw new RangeError("Scene v12 heatmap requires a positive grid_shape");
      }
      const grid = trace.grid;
      if (grid == null) {
        throw new RangeError("heatmap Scene v12 compilation requires a scalar grid");
      }
      if (grid.length !== rows * cols) {
        throw new RangeError("Scene v12 heatmap grid must match rows x cols");
      }
      if (Array.from(grid).some((value) => !Number.isFinite(value))) {
        throw new RangeError("Scene v12 does not yet encode missing-data breaks or nonfinite coordinates");
      }
      const xv = trace.x;
      const yv = trace.y;
      if (xv == null || yv == null || xv.length !== 2 || yv.length !== 2) {
        throw new RangeError("Scene v12 heatmap range columns must be two endpoints");
      }
      const x0Extent = Number(xv[0]);
      const x1Extent = Number(xv[1]);
      const y0Extent = Number(yv[0]);
      const y1Extent = Number(yv[1]);
      if (
        ![x0Extent, x1Extent, y0Extent, y1Extent].every(Number.isFinite)
        || x0Extent >= x1Extent
        || y0Extent >= y1Extent
      ) {
        throw new RangeError("Scene v12 heatmap requires a finite increasing cell extent");
      }
      appendPacked(kinds, stableIds, styleRefs, diameter, symbols, expansionModes, x0, y0, x1, y1, packTrace({
        packKind: 7, styleRef, traceId: id, extra0: rows, extra1: cols,
        columns: [[x0Extent], [y0Extent], [x1Extent], [y1Extent]],
      }));
      continue;
    }

    if (BAND_KINDS.has(trace.kind)) {
      const xv = trace.x, yv = trace.y, base = trace.base;
      if (xv == null || yv == null || base == null) {
        throw new RangeError(`${trace.kind} Scene v12 compilation requires x, y, and base columns`);
      }
      if (!(xv.length === yv.length && yv.length === base.length)) {
        throw new RangeError(`Scene v12 ${trace.kind} band columns must have equal length`);
      }
      const strokePerimeter = style.stroke_perimeter === undefined ? false : style.stroke_perimeter;
      if (typeof strokePerimeter !== "boolean") {
        throw new RangeError("Scene v25 area stroke_perimeter must be a boolean");
      }
      appendPacked(kinds, stableIds, styleRefs, diameter, symbols, expansionModes, x0, y0, x1, y1, packTrace({
        packKind: 3, flags: strokePerimeter ? 1 : 0, styleRef, traceId: id, columns: [xv, yv, base],
      }));
      continue;
    }

    if (RECT_KINDS.has(trace.kind)) {
      requireEqualColumns([trace.x0, trace.y0, trace.x1, trace.y1], trace.kind, "rectangle");
      appendPacked(kinds, stableIds, styleRefs, diameter, symbols, expansionModes, x0, y0, x1, y1, packTrace({
        packKind: 2, styleRef, traceId: id, columns: [trace.x0, trace.y0, trace.x1, trace.y1],
      }));
      continue;
    }

    if (SEGMENT_KINDS.has(trace.kind)) {
      requireEqualColumns([trace.x0, trace.y0, trace.x1, trace.y1], trace.kind, "endpoint");
      appendPacked(kinds, stableIds, styleRefs, diameter, symbols, expansionModes, x0, y0, x1, y1, packTrace({
        packKind: 8, styleRef, traceId: id, columns: [trace.x0, trace.y0, trace.x1, trace.y1],
      }));
      continue;
    }

    let xv = trace.x;
    let yv = trace.y;
    const where = style.step;
    let stepMode = 0;
    if (where != null) {
      if (trace.kind !== "line") throw new RangeError("Scene v12 step expansion applies only to line traces");
      if (!["pre", "post", "mid"].includes(where)) {
        throw new RangeError(`Scene v12 does not support step mode ${JSON.stringify(where)}`);
      }
      stepMode = { pre: 1, mid: 2, post: 3 }[where];
    }
    if (xv == null || yv == null || xv.length !== yv.length) {
      throw new RangeError("Scene v12 does not yet encode missing-data breaks or nonfinite coordinates");
    }
    appendPacked(kinds, stableIds, styleRefs, diameter, symbols, expansionModes, x0, y0, x1, y1, packTrace({
      packKind: trace.kind === "scatter" ? 0 : 1,
      stepMode,
      symbol: trace.kind === "scatter" ? sceneSymbolCode(style.symbol ?? 0) : 0,
      styleRef,
      traceId: id,
      diameter: trace.kind === "scatter" ? Number(style.size ?? style.diameter ?? 4) : 0,
      columns: [xv, yv],
    }));
  }

  const annotationPrefix = 0x5859000000000000n, attachedLabels = [], straightArrows = [], cartesianCallouts = [], wrappedAnnotations = [];
  const annotationMarkRows = [];
  for (const [annotationIndex, annotation] of (figure.annotations ?? []).entries()) {
    const kind = annotation.kind;
    if (["text", "callout"].includes(kind) && Object.hasOwn(annotation, "wrap")) { wrappedAnnotations.push(annotation); continue; }
    if (kind === "text") continue;
    if (kind === "arrow") {
      if (annotation.text != null && annotation.text !== "") throw new RangeError("Scene arrows do not encode text");
      if (annotation.class_name != null && annotation.class_name !== "") throw new RangeError("Scene arrows do not encode class_name");
      const style = { ...(annotation.style ?? {}) }, bad = Object.keys(style).filter((key) => !["color", "opacity", "width"].includes(key) && style[key] != null).sort();
      if (bad.length) throw new RangeError(`Scene arrow style does not encode ${JSON.stringify(bad)}`);
      const opacity = annotationNumber(style, "opacity", 1, "arrow opacity"), width = annotationNumber(style, "width", 1.5, "arrow width");
      if (!Number.isFinite(opacity) || opacity < 0 || opacity > 1 || !Number.isFinite(width) || width <= 0) throw new RangeError("Scene arrow opacity must be in [0, 1] and width must be positive");
      straightArrows.push({ stableId: annotationPrefix | (5n << 40n) | BigInt(annotationIndex), x0: annotationNumber(annotation, "x0", undefined, "arrow x0"), y0: annotationNumber(annotation, "y0", undefined, "arrow y0"), x1: annotationNumber(annotation, "x1", undefined, "arrow x1"), y1: annotationNumber(annotation, "y1", undefined, "arrow y1"), rgba: rgba8(annotationColor(style, "color", "#667085", "arrow color"), 1, "arrow"), opacity, width });
      continue;
    }
    if (kind === "callout") {
      if (annotation.class_name != null && annotation.class_name !== "") throw new RangeError("Scene callouts do not encode class_name");
      if (typeof annotation.text !== "string" || !annotation.text || annotation.text.includes("\0")) throw new RangeError("Scene callouts require nonempty NUL-free text");
      const text = new TextEncoder().encode(annotation.text);
      if (text.length > 4096) throw new RangeError("Scene callouts are limited to 4,096 UTF-8 bytes");
      const style = { ...(annotation.style ?? {}) }, bad = Object.keys(style).filter((key) => !["color", "opacity", "width", "label_background", "label_border_color", "label_border_width"].includes(key) && style[key] != null).sort();
      if (bad.length) throw new RangeError(`Scene callout style does not encode ${JSON.stringify(bad)}`);
      const opacity = annotationNumber(style, "opacity", 1, "callout opacity"), width = annotationNumber(style, "width", 1.5, "callout width");
      if (!Number.isFinite(opacity) || opacity < 0 || opacity > 1 || !Number.isFinite(width) || width <= 0) throw new RangeError("Scene callout opacity must be in [0, 1] and width must be positive");
      const x = annotationNumber(annotation, "x", undefined, "callout x"), y = annotationNumber(annotation, "y", undefined, "callout y"), dx = annotationNumber(annotation, "dx", 36, "callout dx"), dy = annotationNumber(annotation, "dy", -30, "callout dy");
      const anchorCode = { start: 0, middle: 1, end: 2 }[annotation.anchor ?? "start"];
      if (anchorCode == null) throw new RangeError("Scene callout anchor must be start, middle, or end");
      // XYAC v1 rows are LE dddd4sddB3xI (60 fixed bytes), followed by UTF-8
      // text.  When any callout requests a label background, XYAC v2 retains
      // those bytes and appends one literal label-fill RGBA8 before each text.
      // Rust derives identity, layout, and label-box geometry from record order.
      const labelFill = style.label_background == null ? null : rgba8(annotationColor(style, "label_background", "", "callout label background"), 1, "callout label background");
      if ((style.label_border_color == null) !== (style.label_border_width == null)) throw new RangeError("Scene v23 label border requires color and width");
      const labelBorder = style.label_border_color == null ? null : { rgba: rgba8(annotationColor(style, "label_border_color", "", "callout label border"), 1, "callout label border"), width: annotationNumber(style, "label_border_width", undefined, "callout label border width") };
      if (labelBorder && (!Number.isFinite(labelBorder.width) || labelBorder.width <= 0)) throw new RangeError("Scene v23 label border width must be positive and finite");
      if (labelBorder && !labelFill) throw new RangeError("Scene v23 label border requires label_background");
      cartesianCallouts.push({ x, y, dx, dy, rgba: rgba8(annotationColor(style, "color", "#344054", "callout color"), 1, "callout"), opacity, width, anchorCode, text, labelFill, labelBorder });
      continue;
    }
    if (!["rule", "band", "marker"].includes(kind)) throw new RangeError(`Scene v12 annotations support rule, band, and unlabeled marker only; ${JSON.stringify(kind)} is deferred`);
    if (annotation.text != null && annotation.text !== "" && (typeof annotation.text !== "string" || annotation.text.includes("\0"))) throw new RangeError("Scene v16 annotation labels require nonempty NUL-free text");
    if (annotation.class_name != null && annotation.class_name !== "") throw new RangeError(sceneSupportReason(1n << 2n));
    const style = { ...(annotation.style ?? {}) };
    const hasAttachedLabel = annotation.text != null && annotation.text !== "";
    const allowed = new Set(kind === "rule" ? ["color", "opacity", "width"] : kind === "marker" ? ["color", "opacity", "stroke_color", "stroke_width"] : ["color", "opacity"]);
    if (hasAttachedLabel) { allowed.add("label_color"); allowed.add("label_opacity"); allowed.add("label_background"); allowed.add("label_border_color"); allowed.add("label_border_width"); }
    const unsupported = Object.keys(style).filter((key) => !allowed.has(key) && style[key] != null).sort();
    if (unsupported.length) throw new RangeError(`Scene v12 ${kind} annotation style does not encode ${JSON.stringify(unsupported)}`);
    const opacity = annotationNumber(style, "opacity", kind === "band" ? 0.14 : 1, `${kind} opacity`);
    if (!Number.isFinite(opacity) || opacity < 0 || opacity > 1) throw new RangeError(`Scene v12 ${kind} annotation opacity must be finite and in [0, 1]`);
    const color = annotationColor(style, "color", kind === "band" ? "#64748b" : "#667085", `${kind} color`);
    const strokeColor = annotationColor(style, "stroke_color", color, `${kind} stroke color`);
    const widthKey = kind === "rule" ? "width" : "stroke_width";
    const width = annotationNumber(style, widthKey, kind === "band" ? 0 : 1.5, `${kind} width`);
    if (!Number.isFinite(width) || width < 0 || (kind === "rule" && width === 0)) throw new RangeError(`Scene v12 ${kind} annotation width must be finite and nonnegative`);
    styles.push({ fillRgba: kind === "rule" ? [0, 0, 0, 0] : rgba8(color, opacity, "annotation fill"), strokeRgba: rgba8(strokeColor, opacity, "annotation stroke"), strokeWidth: width });
    const styleRef = styles.length - 1;
    const tag = kind === "band" && annotation.axis === "y" ? 4n : { rule: 1n, band: 2n, marker: 3n }[kind];
    const stableId = annotationPrefix | (tag << 40n) | BigInt(annotationIndex);
    if (hasAttachedLabel) {
      const text = new TextEncoder().encode(annotation.text);
      if (text.length > 4096) throw new RangeError("Scene v16 annotation labels are limited to 4,096 UTF-8 bytes");
      const labelOpacity = annotationNumber(style, "label_opacity", 1, "label opacity");
      if (!Number.isFinite(labelOpacity) || labelOpacity < 0 || labelOpacity > 1) throw new RangeError("Scene v16 annotation label opacity must be finite and in [0, 1]");
      const labelFill = style.label_background == null ? null : rgba8(annotationColor(style, "label_background", "", "annotation label background"), 1, "annotation label background");
      if ((style.label_border_color == null) !== (style.label_border_width == null)) throw new RangeError("Scene v23 label border requires color and width");
      const labelBorder = style.label_border_color == null ? null : { rgba: rgba8(annotationColor(style, "label_border_color", "", "annotation label border"), 1, "annotation label border"), width: annotationNumber(style, "label_border_width", undefined, "annotation label border width") };
      if (labelBorder && (!Number.isFinite(labelBorder.width) || labelBorder.width <= 0)) throw new RangeError("Scene v23 label border width must be positive and finite");
      if (labelBorder && !labelFill) throw new RangeError("Scene v23 label border requires label_background");
      attachedLabels.push({ stableId, rgba: rgba8(annotationColor(style, "label_color", "#667085", "label color"), labelOpacity, "annotation label"), labelFill, labelBorder, text });
    }
    const kindCode = { rule: 1, band: 2, marker: 3 }[kind];
    if (kind === "rule") {
      const value = annotationNumber(annotation, "value", undefined, `${kind} value`);
      if (annotation.axis !== "x" && annotation.axis !== "y") throw new RangeError("Scene v12 rule annotation axis must be 'x' or 'y'");
      annotationMarkRows.push(annotationMarkRow(kindCode, annotation.axis === "x" ? 0 : 1, 0, styleRef, annotationIndex, value, 0, 0));
    } else if (kind === "band") {
      const start = annotationNumber(annotation, "start", undefined, `${kind} start`);
      const end = annotationNumber(annotation, "end", undefined, `${kind} end`);
      if (annotation.axis !== "x" && annotation.axis !== "y") throw new RangeError("Scene v12 band annotation axis must be 'x' or 'y'");
      annotationMarkRows.push(annotationMarkRow(kindCode, annotation.axis === "x" ? 0 : 1, 0, styleRef, annotationIndex, start, end, 0));
    } else {
      const size = annotationNumber(annotation, "size", 8, `${kind} size`);
      if (!Number.isFinite(size) || size <= 0) throw new RangeError("Scene v12 marker annotation size must be finite and positive");
      annotationMarkRows.push(annotationMarkRow(
        kindCode, 0, annotationSymbolCode(annotation.symbol ?? "circle"), styleRef, annotationIndex,
        annotationNumber(annotation, "x", undefined, `${kind} x`),
        annotationNumber(annotation, "y", undefined, `${kind} y`),
        size,
      ));
    }
  }
  if (annotationMarkRows.length) {
    const packedMarks = new Uint8Array(annotationMarkRows.reduce((n, row) => n + row.length, 0));
    let offset = 0;
    for (const row of annotationMarkRows) { packedMarks.set(row, offset); offset += row.length; }
    appendPacked(kinds, stableIds, styleRefs, diameter, symbols, expansionModes, x0, y0, x1, y1, packAnnotationMarks(packedMarks, xDomain, yDomain));
  }
  const textAnnotations = (figure.annotations ?? []).filter((annotation) => annotation.kind === "text" && !Object.hasOwn(annotation, "wrap"));
  const textEncoder = new TextEncoder();
  const authoredText = (() => {
    if (!textAnnotations.length && !attachedLabels.length && !straightArrows.length && !cartesianCallouts.length && !wrappedAnnotations.length) return new Uint8Array();
    if (cartesianCallouts.length > 128) throw new RangeError("Scene callouts are limited to 128 entries");
    if (textAnnotations.length > 128) throw new RangeError("Scene v16 text annotations are limited to 128 entries");
    const rows = textAnnotations.map((annotation) => {
      if (typeof annotation.text !== "string" || !annotation.text || annotation.text.includes("\0")) throw new RangeError("Scene v16 text annotations require nonempty NUL-free text");
      const text = textEncoder.encode(annotation.text); if (text.length > 4096) throw new RangeError("Scene v16 text annotations are bounded");
      const x = annotationNumber(annotation, "x", undefined, "text x"), y = annotationNumber(annotation, "y", undefined, "text y");
      const style = { ...(annotation.style ?? {}) }; if (Object.keys(style).some((key) => !["color", "opacity", "label_background", "label_border_color", "label_border_width"].includes(key))) throw new RangeError("Scene v23 text annotations support only color, opacity, label_background, and label_border_*");
      const labelFill = style.label_background == null ? null : rgba8(annotationColor(style, "label_background", "", "text label background"), 1, "text label background");
      if ((style.label_border_color == null) !== (style.label_border_width == null)) throw new RangeError("Scene v23 label border requires color and width");
      const labelBorder = style.label_border_color == null ? null : { rgba: rgba8(annotationColor(style, "label_border_color", "", "text label border"), 1, "text label border"), width: annotationNumber(style, "label_border_width", undefined, "text label border width") };
      if (labelBorder && (!Number.isFinite(labelBorder.width) || labelBorder.width <= 0)) throw new RangeError("Scene v23 label border width must be positive and finite");
      if (labelBorder && !labelFill) throw new RangeError("Scene v23 label border requires label_background");
      return { x, y, rgba: rgba8(annotationColor(style, "color", "#667085", "text color"), annotationNumber(style, "opacity", 1, "text opacity"), "text"), labelFill, labelBorder, text };
    });
    const wrapped = wrappedAnnotations.map((a) => { const s = { ...(a.style ?? {}) }, allowed = ["color","opacity","label_background","label_border_color","label_border_width"]; if (a.class_name != null && a.class_name !== "" || typeof a.text !== "string" || !a.text || a.text.includes("\\0") || a.text.includes("\\r") || Object.keys(s).some((k) => !allowed.includes(k) && s[k] != null)) throw new RangeError("Scene wrapped annotations do not encode class_name, custom fonts, CSS, markup, collision, or leader style"); const text=textEncoder.encode(a.text), x=annotationNumber(a,"x",undefined,"wrapped x"), y=annotationNumber(a,"y",undefined,"wrapped y"), dx=annotationNumber(a,"dx",a.kind === "callout" ? 36 : 6,"wrapped dx"), dy=annotationNumber(a,"dy",a.kind === "callout" ? -30 : -6,"wrapped dy"), wrap=annotationNumber(a,"wrap",undefined,"wrapped width"), anchor={start:0,middle:1,end:2}[a.anchor ?? "start"], opacity=annotationNumber(s,"opacity",1,"wrapped opacity"); if (text.length > 4096 || ![x,y,dx,dy,wrap,opacity].every(Number.isFinite) || wrap < 0 || opacity < 0 || opacity > 1 || anchor == null) throw new RangeError("Scene wrapped annotation values are invalid"); const fill=s.label_background == null ? [0,0,0,0] : rgba8(annotationColor(s,"label_background","","wrapped background"),1,"wrapped background"); if ((s.label_border_color == null) !== (s.label_border_width == null)) throw new RangeError("Scene wrapped label border requires color and width"); const border=s.label_border_color == null ? null : { rgba:rgba8(annotationColor(s,"label_border_color","","wrapped border"),1,"wrapped border"), width:annotationNumber(s,"label_border_width",undefined,"wrapped border width") }; if (border && (!Number.isFinite(border.width) || border.width <= 0 || fill[3] === 0)) throw new RangeError("Scene wrapped label border requires a positive width and background"); return {a,text,x,y,dx,dy,wrap,anchor,opacity,fill,border}; });
    return packAnnotationEnvelope({ texts: rows, attached: attachedLabels, arrows: straightArrows, callouts: cartesianCallouts, wrapped });
  })();
  const title = figure.title ?? "";
  // `Figure.setAxis({ label })` is the public Node authoring form, matching
  // Python's `axis_options`; do not silently drop those bytes before the Rust
  // layout/Scene seam.
  const xLabel = figure.xLabel ?? figure.x_label ?? figure.xAxis?.label ?? figure.x_axis?.label ?? "";
  const yLabel = figure.yLabel ?? figure.y_label ?? figure.yAxis?.label ?? figure.y_axis?.label ?? "";
  let resolvedMargins = margins;
  if (resolvedMargins == null) {
    const out = new Float64Array(4);
    const titleBytes = new TextEncoder().encode(String(title));
    const xLabelBytes = new TextEncoder().encode(String(xLabel));
    const yLabelBytes = new TextEncoder().encode(String(yLabel));
    const xAxisOptions = figure.xAxis ?? figure.x_axis ?? {};
    const yAxisOptions = figure.yAxis ?? figure.y_axis ?? {};
    const xLayoutFormat = (xAxisOptions.tickLabels ?? xAxisOptions.tick_labels) == null ? xSceneAxis.format : null;
    const yLayoutFormat = (yAxisOptions.tickLabels ?? yAxisOptions.tick_labels) == null ? ySceneAxis.format : null;
    const xFormatBytes = xLayoutFormat == null ? new Uint8Array() : new TextEncoder().encode(String(xLayoutFormat));
    const yFormatBytes = yLayoutFormat == null ? new Uint8Array() : new TextEncoder().encode(String(yLayoutFormat));
    if ([xFormatBytes, yFormatBytes].some((value) => value.length > 256 || value.includes(0))) throw new RangeError("Scene axis format must be NUL-free and at most 256 UTF-8 bytes");
    const written = xyScenePlotLayout(
      Number(figure.width), Number(figure.height), 0,
      ...xSceneDescriptor.slice(1), ...ySceneDescriptor.slice(1),
      titleBytes.length ? u8Ptr(titleBytes) : 0, BigInt(titleBytes.length),
      xLabelBytes.length ? u8Ptr(xLabelBytes) : 0, BigInt(xLabelBytes.length),
      yLabelBytes.length ? u8Ptr(yLabelBytes) : 0, BigInt(yLabelBytes.length),
      xFormatBytes.length ? u8Ptr(xFormatBytes) : 0, BigInt(xFormatBytes.length),
      yFormatBytes.length ? u8Ptr(yFormatBytes) : 0, BigInt(yFormatBytes.length),
      encodedColorbar.length ? (encodedColorbar[8] & 1 ? 2 : 1) : 0,
      f64Ptr(out),
    );
    if (written !== 4n && written !== 4) throw new RangeError("invalid canonical scene plot layout");
    resolvedMargins = [out[0], out[1], out[2], out[3]];
  }
  return sceneBatchEncode({ viewport: [figure.width, figure.height], margins: resolvedMargins,
    xAxis: xSceneAxis, yAxis: ySceneAxis,
    kinds, stableIds, styleRefs, styles, diameter, symbols, expansionModes, x0, y0, x1, y1,
    title, xLabel, yLabel, chromeStyle: figureChromeStyle(figure), xMajorTicks: (figure.xAxis ?? figure.x_axis)?.tickValues ?? (figure.xAxis ?? figure.x_axis)?.tick_values ?? null, xMinorTicks: (figure.xAxis ?? figure.x_axis)?.minorTickValues ?? (figure.xAxis ?? figure.x_axis)?.minor_tick_values ?? [], yMajorTicks: (figure.yAxis ?? figure.y_axis)?.tickValues ?? (figure.yAxis ?? figure.y_axis)?.tick_values ?? null, yMinorTicks: (figure.yAxis ?? figure.y_axis)?.minorTickValues ?? (figure.yAxis ?? figure.y_axis)?.minor_tick_values ?? [], xTickLabels: (figure.xAxis ?? figure.x_axis)?.tickLabels ?? (figure.xAxis ?? figure.x_axis)?.tick_labels ?? null, yTickLabels: (figure.yAxis ?? figure.y_axis)?.tickLabels ?? (figure.yAxis ?? figure.y_axis)?.tick_labels ?? null, xFormat: xSceneAxis.format, yFormat: ySceneAxis.format, legendInput: legendInput(figure, legendEntries, styles), colorbarInput: encodedColorbar, authoredTextAnnotations: authoredText, polarInput: packPolarSceneInput(figure),
  });
}

/** Serialize built-in scatter marks through the shared Rust scene schema. */
export function scatterSceneSvg({
  x,
  y,
  diameter,
  fillRgba,
  strokeRgba,
  strokeWidth,
  symbols,
  visible = null,
  fillCss = null,
  strokeCss = null,
}) {
  const xa = asF64Array(x, "x");
  const ya = asF64Array(y, "y");
  const diameters = asF64Array(diameter, "diameter");
  const widths = asF64Array(strokeWidth, "strokeWidth");
  const fills = asU8Array(fillRgba, "fillRgba");
  const strokes = asU8Array(strokeRgba, "strokeRgba");
  const symbolCodes = asU8Array(symbols, "symbols");
  const visibility = visible == null ? null : asU8Array(visible, "visible");
  const fillCssBytes = fillCss == null ? null : new TextEncoder().encode(String(fillCss));
  const strokeCssBytes = strokeCss == null ? null : new TextEncoder().encode(String(strokeCss));
  const length = xa.length;
  requireLength(ya, length, "y");
  requireLength(diameters, length, "diameter");
  requireLength(widths, length, "strokeWidth");
  requireLength(symbolCodes, length, "symbols");
  requireLength(fills, length * 4, "fillRgba");
  requireLength(strokes, length * 4, "strokeRgba");
  if (visibility != null) requireLength(visibility, length, "visible");

  let capacity = Math.max(32, length * 160);
  for (;;) {
    const output = new Uint8Array(capacity);
    const rawWritten = xySceneScatterSvg(
      f64Ptr(xa),
      f64Ptr(ya),
      f64Ptr(diameters),
      u8Ptr(fills),
      u8Ptr(strokes),
      f64Ptr(widths),
      u8Ptr(symbolCodes),
      u8Ptr(visibility),
      u8Ptr(fillCssBytes),
      BigInt(fillCssBytes?.length ?? 0),
      u8Ptr(strokeCssBytes),
      BigInt(strokeCssBytes?.length ?? 0),
      BigInt(length),
      pointer(output, "uint8_t *"),
      BigInt(capacity),
    );
    if (rawWritten === USIZE_MAX_64) {
      throw new RangeError("invalid canonical scatter scene");
    }
    const written = Number(rawWritten);
    if (!Number.isSafeInteger(written) || written < 0) {
      throw new RangeError("canonical scatter scene exceeded host output limits");
    }
    if (written <= capacity) {
      return new TextDecoder().decode(output.subarray(0, written));
    }
    capacity = written;
  }
}
