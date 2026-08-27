/** Thin Node adapter for the versioned Rust-owned canonical scene IR. */
import {
  pointer,
  xySceneAxisTicks,
  xySceneBatchEncode,
  xySceneBrowserPainter,
  xyScenePlotLayout,
  xySceneRasterCommands,
  xySceneScaleMap,
  xySceneScatterSvg,
  xySceneSupportReason,
  xySceneSvg,
  xySceneVersion,
} from "./native.js";
import { asF64Array, f64Ptr, shouldUseDensity, u32Ptr, u8Ptr } from "./encode.js";
import { parseCssColor } from "./color.js";

const USIZE_MAX_64 = (1n << 64n) - 1n;
const MAX_SCENE_MARKS = 2_000_000;
const MAX_SCENE_STYLES = 65_536;
const MAX_SCENE_TEXT_BYTES = 4_096;
const SYMBOL_CODES = new Map([
  "circle", "square", "diamond", "triangle", "cross", "hexagon", "pentagon", "star",
  "triangle_down", "triangle_left", "triangle_right", "x", "point", "pixel",
  "thin_diamond", "plus_line", "x_line", "horizontal_line", "vertical_line",
].map((name, code) => [name, code]));

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

function defaultChromeStyle() {
  const bytes = new Uint8Array(200);
  const view = new DataView(bytes.buffer);
  bytes.set([32, 32, 32, 217], 8);
  view.setFloat64(16, 12, true);
  for (const offset of [24, 112]) {
    bytes[offset + 1] = 1; bytes[offset + 2] = 1;
    bytes.set([32, 32, 32, 140], offset + 8);
    bytes.set([32, 32, 32, 36], offset + 12);
    bytes.set([32, 32, 32, 140], offset + 16);
    bytes.set([32, 32, 32, 140], offset + 24);
    bytes.set([32, 32, 32, 217], offset + 28);
    [1, 1, 1, 4, 1, 1, 0].forEach((value, index) => view.setFloat64(offset + 32 + index * 8, value, true));
  }
  return bytes;
}

function figureChromeStyle(figure) {
  const out = defaultChromeStyle(), view = new DataView(out.buffer);
  const figureStyle = figure.style ?? {};
  if (figureStyle.background != null) out.set(rgba8(figureStyle.background, 1, "chart background"), 0);
  if (figureStyle["--chart-bg"] != null) out.set(rgba8(figureStyle["--chart-bg"], 1, "plot background"), 4);
  for (const [axis, offset, sides] of [["x", 24, ["bottom", "top"]], ["y", 112, ["left", "right"]]]) {
    const options = figure[`${axis}Axis`] ?? figure[`${axis}_axis`] ?? {}, style = options.style ?? {}, minor = options.minorStyle ?? options.minor_style ?? {};
    const side = options.side ?? sides[0]; if (!sides.includes(side)) throw new RangeError(`Scene ${axis} axis side is invalid`);
    const mask = (values, fallback) => values == null ? 1 << fallback : values.reduce((sum, value) => { const i = sides.indexOf(value); if (i < 0) throw new RangeError(`Scene ${axis} axis sides are invalid`); return sum | (1 << i); }, 0);
    const direction = {out:0, in:1, inout:2};
    out[offset] = sides.indexOf(side); out[offset + 1] = mask(options.tickSides ?? options.tick_sides, out[offset]); out[offset + 2] = mask(options.tickLabelSides ?? options.tick_label_sides, out[offset]);
    out[offset + 3] = direction[style.tick_direction ?? style.tickDirection ?? "out"] ?? 255; out[offset + 4] = direction[minor.tick_direction ?? minor.tickDirection ?? "out"] ?? 255;
    const paints = [[style.axis_color, .55], [style.grid_color, .14], [style.tick_color, .55], [minor.grid_color, 1], [minor.tick_color, .55], [style.tick_label_color ?? style.label_color, .85]];
    paints.forEach(([paint], i) => { if (paint != null) out.set(rgba8(paint, 1, "axis paint"), offset + 8 + i * 4); });
    const nums = [style.axis_width, style.grid_width, style.tick_width, style.tick_length, minor.grid_width, minor.tick_width, minor.tick_length]; nums.forEach((value, i) => { if (value != null) view.setFloat64(offset + 32 + i * 8, Number(value), true); });
  }
  return out;
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
    : asUnsignedArray(expansionModes, "expansionModes", 4, Uint8Array);
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

function rgba8(css, opacity, name) {
  const parsed = parseCssColor(css);
  if (parsed == null) throw new RangeError(`${name} must be a supported constant CSS color`);
  return parsed.map((value, index) => Math.round(value * (index === 3 ? opacity : 1) * 255));
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
// Pointy-top hexagon ring as fractions of hex_dx/hex_dy. Same contract as
// python/xyg/_svg.py HEX_RING and js/src/50_chartview.ts _buildHexbinMark.
const HEXBIN_RING = [
  [0, -1 / 3],
  [0.5, -1 / 6],
  [0.5, 1 / 6],
  [0, 1 / 3],
  [-0.5, 1 / 6],
  [-0.5, -1 / 6],
];
const STROKE_KINDS = new Set(["line", "segments", "errorbar", "stem", "contour", "box_whisker", "box_median"]);
const SUPPORTED_KINDS = new Set([
  "scatter", "line", "bar", "column", "histogram", "violin", "box",
  "segments", "errorbar", "stem", "contour", "box_whisker", "box_median",
  "area", "error_band", "ribbon", "triangle_mesh", "hexbin",
]);

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
const LEGEND_LOCATIONS = new Map([["upper right", 0], ["upper left", 1], ["lower left", 2], ["lower right", 3], ["center right", 4], ["center left", 5], ["upper center", 6], ["lower center", 7], ["center", 8]]);

function legendInput(figure, entries, styles) {
  if (figure.showLegend === false || entries.length === 0) return new Uint8Array();
  const options = figure.legend ?? {};
  const allowed = new Set(["loc", "title", "ncols", "style", "highlight", "toggle"]);
  if (Object.keys(options).some((key) => !allowed.has(key)) || Number(options.ncols ?? 1) !== 1) throw new RangeError("Scene v12 primary legends do not yet encode anchors, multiple columns, or custom content");
  if (["toggle", "highlight"].some((key) => Object.hasOwn(options, key) && options[key] !== false)) throw new RangeError("Scene v12 primary legends are static; toggle and highlight must be false");
  const authoredLoc = options.loc;
  const loc = authoredLoc ?? "upper right";
  if (!LEGEND_LOCATIONS.has(loc) || loc === "best") throw new RangeError(`Scene v12 does not support legend location ${JSON.stringify(loc)}`);
  const style = options.style ?? {};
  const allowedStyle = new Set(["background", "color", "font_size", "fontSize", "title_font_size", "titleFontSize"]);
  if (Object.keys(style).some((key) => !allowedStyle.has(key))) throw new RangeError("Scene v12 legends support only background, color, font_size, and title_font_size");
  const authoredFontSize = style.font_size ?? style.fontSize, authoredTitleFontSize = style.title_font_size ?? style.titleFontSize;
  const fontSize = authoredFontSize == null ? 0 : Number(authoredFontSize), titleFontSize = authoredTitleFontSize == null ? 0 : Number(authoredTitleFontSize);
  if (!((authoredFontSize == null || (fontSize >= 1 && fontSize <= 1000)) && (authoredTitleFontSize == null || (titleFontSize >= 1 && titleFontSize <= 1000)))) throw new RangeError("legend font sizes must be finite and in [1, 1000]");
  const encoder = new TextEncoder(), title = encoder.encode(String(options.title ?? "")), labels = entries.map((entry) => encoder.encode(entry.label));
  const textLength = title.length + labels.reduce((sum, label) => sum + label.length, 0);
  if (entries.length > 128 || title.length > 4096 || textLength > 16384 || labels.some((label) => label.length === 0 || label.length > 4096)) throw new RangeError("Scene v12 legend text exceeds its bounded UTF-8 limits");
  const out = new Uint8Array(48 + entries.length * 24 + textLength), view = new DataView(out.buffer);
  out.set([88, 89, 76, 71]); out[4] = LEGEND_LOCATIONS.get(loc); out[5] = Number(authoredLoc != null) | (Number(authoredFontSize != null) << 1) | (Number(authoredTitleFontSize != null) << 2) | (Number(Object.hasOwn(style, "color")) << 3) | (Number(Object.hasOwn(style, "background")) << 4); view.setUint32(8, entries.length, true); view.setUint32(12, title.length, true); view.setFloat64(16, fontSize, true); view.setFloat64(24, titleFontSize, true);
  if (Object.hasOwn(style, "color")) out.set(rgba8(style.color, 1, "legend color"), 32); if (Object.hasOwn(style, "background")) out.set(rgba8(style.background, 1, "legend background"), 36);
  let textOffset = title.length; out.set(title, 48 + entries.length * 24);
  for (const [index, entry] of entries.entries()) {
    const offset = 48 + index * 24, label = labels[index], paint = styles[entry.styleRef];
    view.setUint32(offset, entry.styleRef, true); out[offset + 4] = entry.kind; out[offset + 5] = entry.symbol; view.setUint32(offset + 8, textOffset, true); view.setUint32(offset + 12, label.length, true); out.set(paint.fillRgba, offset + 16); out.set(paint.strokeRgba, offset + 20); out.set(label, 48 + entries.length * 24 + textOffset); textOffset += label.length;
  }
  return out;
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
  if (!Number.isFinite(lo) || !Number.isFinite(hi) || lo >= hi) throw new RangeError("Scene v19 colorbar domain must be finite and ordered");
  const title = options.title ?? "";
  if (typeof title !== "string") throw new TypeError("Scene v19 colorbar title must be a string");
  const titleBytes = new TextEncoder().encode(title), text = asUnsignedArray(options.text_rgba ?? [32, 32, 32, 255], "colorbar text_rgba", 255, Uint8Array);
  requireLength(text, 4, "colorbar text_rgba"); if (titleBytes.length > 4096) throw new RangeError("Scene v19 colorbar title is limited to 4,096 UTF-8 bytes");
  const rawTicks = options.ticks;
  if (rawTicks != null && (!Array.isArray(rawTicks) || rawTicks.length > 32)) throw new RangeError("Scene v19 colorbar ticks are limited to 32 finite ordered values");
  const ticks = rawTicks == null ? [] : rawTicks.map(Number);
  if (ticks.some((value, index) => !Number.isFinite(value) || value < lo || value > hi || (index && value <= ticks[index - 1]))) throw new RangeError("Scene v19 colorbar ticks are limited to 32 finite ordered values");
  const authoredTicks = ticks.length > 0;
  const minorTicks = options.minor_ticks ?? false;
  if (typeof minorTicks !== "boolean") throw new TypeError("Scene v19 colorbar minor_ticks must be a boolean");
  const out = new Uint8Array(56 + stops.length * 12 + ticks.length * 8 + titleBytes.length), view = new DataView(out.buffer);
  out.set([88, 89, 67, 66]); view.setUint32(4, 2, true);
  const side = options.side ?? "right"; if (side !== "right" && side !== "bottom") throw new RangeError("Scene v19 colorbar side is right or bottom");
  out[8] = Number(side === "bottom") | 2 | (Number(minorTicks) << 2) | (Number(authoredTicks) << 3);
  view.setUint32(12, stops.length, true); view.setUint32(16, ticks.length, true); view.setUint32(20, titleBytes.length, true); view.setFloat64(24, lo, true); view.setFloat64(32, hi, true); out.set(text, 40);
  let previous = -Infinity;
  for (const [index, stop] of stops.entries()) { if (!Array.isArray(stop) || stop.length !== 2) throw new TypeError("colorbar stops are [value, RGBA]"); const value = Number(stop[0]), rgba = asUnsignedArray(stop[1], `colorbar stops[${index}]`, 255, Uint8Array); requireLength(rgba, 4, `colorbar stops[${index}]`); if (!Number.isFinite(value) || value < lo || value > hi || value <= previous) throw new RangeError("colorbar stops must be ordered within the domain"); previous = value; view.setFloat64(56 + index * 12, value, true); out.set(rgba, 64 + index * 12); }
  if (view.getFloat64(56, true) !== lo || view.getFloat64(56 + (stops.length - 1) * 12, true) !== hi) throw new RangeError("colorbar stops must span the domain");
  const ticksStart = 56 + stops.length * 12;
  for (const [index, value] of ticks.entries()) view.setFloat64(ticksStart + index * 8, value, true);
  out.set(titleBytes, ticksStart + ticks.length * 8); return out;
}

function rejectRectExtras(style, kind) {
  if (style.fill != null && typeof style.fill === "object") {
    throw new RangeError(`Scene v12 does not yet encode ${kind} gradient fills`);
  }
  const radius = style.corner_radius ?? 0;
  if (Array.isArray(radius)) {
    if (radius.some((value) => Number(value) !== 0)) {
      throw new RangeError(`Scene v12 does not yet encode ${kind} corner_radius`);
    }
  } else if (Number(radius) !== 0) {
    throw new RangeError(`Scene v12 does not yet encode ${kind} corner_radius`);
  }
  if (Number(style.wedge_gap ?? 0) !== 0) {
    throw new RangeError(`Scene v12 does not yet encode ${kind} wedge_gap`);
  }
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
  const chromeStyles = figure.chromeStyles ?? figure.chrome_styles ?? {};
  let encodedColorbar = new Uint8Array(), colorbarUnsupported = false;
  try { encodedColorbar = colorbarInput(figure); } catch { colorbarUnsupported = Boolean(figure.colorbarOptions ?? figure.colorbar_options); }
  let features = 0n;
  if (figure.coords !== "cartesian") features |= 1n << 0n;
  if (Object.values(chromeStyles).some((style) => style?.fontFamily != null || style?.["font-family"] != null)) features |= 1n << 1n;
  if (
    figure.className
    || figure.class_name
    || Object.keys(figure.classNames ?? figure.class_names ?? {}).length
    || Object.keys(chromeStyles).length
    || Object.keys(figure.style ?? {}).some((key) => !["background", "--chart-bg"].includes(key))
    || (figure.annotations ?? []).some((annotation) => annotation.className || annotation.class_name)
  ) features |= 1n << 2n;
  if ((figure.traces ?? []).some((trace) => (
    trace.color_target != null
    || (trace.style?.fill != null && typeof trace.style.fill === "object")
    || (
      trace.color != null
      && typeof trace.color === "object"
      && (trace.color.mode !== "constant" || trace.color.color == null)
    )
  ))) features |= 1n << 3n;
  if (colorbarUnsupported) features |= 1n << 4n;
  if ((figure.extraLegends ?? figure.extra_legends ?? []).length) features |= 1n << 5n;
  if ((figure.annotations ?? []).some((annotation) => !["callout", "arrow", "text"].includes(annotation.kind) && annotation.text != null && annotation.text !== "")) features |= 1n << 7n;
  const reason = sceneSupportReason(features);
  if (reason) throw new RangeError(reason);
  const unsupported = figure.traces.find((trace) => !SUPPORTED_KINDS.has(trace.kind));
  if (unsupported) throw new RangeError(`Scene v12 figure compilation does not yet support ${unsupported.kind}`);
  const kinds = [], stableIds = [], styleRefs = [], diameter = [], symbols = [], x0 = [], y0 = [], x1 = [], y1 = [], styles = [], legendEntries = [], expansionRuns = [];
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
    if (trace.x_axis !== "x" || trace.y_axis !== "y") throw new RangeError("Scene v12 currently supports only the primary x/y axes");
    if (
      trace.kind === "scatter" &&
      shouldUseDensity(trace.x?.length ?? 0, {
        forceDensity: Boolean(trace.force_density ?? trace.forceDensity),
        forceDirect: Boolean(trace.force_direct ?? trace.forceDirect),
        coords: figure.coords ?? "cartesian",
      })
    ) {
      throw new RangeError("Scene v12 does not yet encode density-tier scatter");
    }
    const style = trace.style ?? {};
    for (const key of ["color_channel", "size_channel", "stroke_channel", "dash", "curve", "smooth", "linecap", "marker_path", "marker_glyph"]) {
      if (style[key] != null) throw new RangeError(`Scene v12 figure compilation does not yet support ${key}`);
    }
    if (RECT_KINDS.has(trace.kind)) rejectRectExtras(style, trace.kind);
    const opacity = Number(style.opacity ?? 1);
    if (!Number.isFinite(opacity) || opacity < 0 || opacity > 1) throw new RangeError("trace opacity must be in [0, 1]");
    const fillOpacity = BAND_KINDS.has(trace.kind) || RIBBON_KINDS.has(trace.kind) ? Number(style.fill_opacity ?? 1) : 1;
    const strokeOpacity = BAND_KINDS.has(trace.kind) || RIBBON_KINDS.has(trace.kind) ? Number(style.stroke_opacity ?? 1) : 1;
    const lineOpacity = BAND_KINDS.has(trace.kind) ? Number(style.line_opacity ?? 1) : 1;
    if ((BAND_KINDS.has(trace.kind) || RIBBON_KINDS.has(trace.kind)) && [fillOpacity, strokeOpacity, lineOpacity].some((value) => !Number.isFinite(value) || value < 0 || value > 1)) {
      throw new RangeError("trace opacity channels must be in [0, 1]");
    }
    const color = style.color
      ?? (typeof trace.color === "string" ? trace.color : trace.color?.color)
      ?? "#3987e5";
    const fillDefault = SEGMENT_KINDS.has(trace.kind) ? "#00000000" : color;
    const fillCss = style.fill ?? fillDefault;
    if (typeof fillCss !== "string") throw new RangeError(`Scene v12 does not yet encode ${trace.kind} non-CSS fills`);
    const symbolCode = sceneSymbolCode(style.symbol ?? 0);
    const strokeCss = BAND_KINDS.has(trace.kind)
      ? (style.line_color ?? color)
      : RIBBON_KINDS.has(trace.kind)
        ? (style.stroke ?? color)
        : (style.stroke ?? (
            STROKE_KINDS.has(trace.kind)
            || (
              trace.kind === "scatter"
              && symbolCode >= SYMBOL_CODES.get("plus_line")
            )
              ? color
              : "#00000000"
          ));
    const width = Number(
      style.stroke_width
      ?? style.width
      ?? style.line_width
      ?? (STROKE_KINDS.has(trace.kind) ? 1.5 : 0),
    );
    styles.push({
      fillRgba: rgba8(fillCss, opacity * fillOpacity, "fill"),
      strokeRgba: rgba8(strokeCss, opacity * strokeOpacity * (BAND_KINDS.has(trace.kind) ? lineOpacity : 1), "stroke"),
      strokeWidth: width,
    });
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
      if (cols.some((column) => Array.from(column).some((value) => !Number.isFinite(value)))) {
        throw new RangeError("Scene v12 does not yet encode missing-data breaks or nonfinite coordinates");
      }
      for (let bandIndex = 0; bandIndex < count; bandIndex += 1) {
        const stableId = (BigInt(id) << 32n) | BigInt(bandIndex);
        const runStart = kinds.length;
        for (const [startY, endY] of [
          [trace.y1[bandIndex], trace.y[bandIndex]],
          [trace.y0[bandIndex], trace.x[bandIndex]],
        ]) {
          kinds.push(3); stableIds.push(stableId); styleRefs.push(styleRef);
          diameter.push(0); symbols.push(2);
          x0.push(Number(trace.x0[bandIndex])); y0.push(Number(startY));
          x1.push(Number(trace.x1[bandIndex])); y1.push(Number(endY));
        }
        expansionRuns.push([runStart, kinds.length, 4]);
      }
      continue;
    }

    if (POLYFILL_KINDS.has(trace.kind)) {
      if (style.joined_fill) throw new RangeError("Scene v12 does not yet encode joined triangle-mesh fills");
      const cols = [trace.x0, trace.y0, trace.x1, trace.y1, trace.x, trace.y];
      if (cols.some((column) => column == null)) {
        throw new RangeError("triangle_mesh Scene v12 compilation requires six vertex columns");
      }
      const count = cols[0].length;
      if (cols.some((column) => column.length !== count)) {
        throw new RangeError("Scene v12 triangle_mesh columns must have equal length");
      }
      if (cols.some((column) => Array.from(column).some((value) => !Number.isFinite(value)))) {
        throw new RangeError("Scene v12 does not yet encode missing-data breaks or nonfinite coordinates");
      }
      for (let triIndex = 0; triIndex < count; triIndex += 1) {
        const stableId = (BigInt(id) << 32n) | BigInt(triIndex);
        for (const [px, py] of [
          [trace.x0[triIndex], trace.y0[triIndex]],
          [trace.x1[triIndex], trace.y1[triIndex]],
          [trace.x[triIndex], trace.y[triIndex]],
        ]) {
          kinds.push(4); stableIds.push(stableId); styleRefs.push(styleRef);
          diameter.push(0); symbols.push(0);
          x0.push(px); y0.push(py); x1.push(0); y1.push(0);
        }
      }
      continue;
    }

    if (HEXBIN_KINDS.has(trace.kind)) {
      if (!HEXBIN_REDUCES.has(style.reduce)) {
        throw new RangeError("Scene v12 does not yet encode custom hexbin reducers");
      }
      const xv = trace.x;
      const yv = trace.y;
      if (xv == null || yv == null || xv.length !== yv.length) {
        throw new RangeError("Scene v12 hexbin columns must have equal length");
      }
      if (
        Array.from(xv).some((value) => !Number.isFinite(value))
        || Array.from(yv).some((value) => !Number.isFinite(value))
      ) {
        throw new RangeError("Scene v12 does not yet encode missing-data breaks or nonfinite coordinates");
      }
      const dx = Number(style.hex_dx ?? style.dx);
      const dy = Number(style.hex_dy ?? style.dy);
      if (!Number.isFinite(dx) || !Number.isFinite(dy) || dx <= 0 || dy <= 0) {
        throw new RangeError("Scene v12 hexbin requires finite hex_dx/hex_dy cell pitch");
      }
      for (let cellIndex = 0; cellIndex < xv.length; cellIndex += 1) {
        const stableId = (BigInt(id) << 32n) | BigInt(cellIndex);
        const cx = Number(xv[cellIndex]);
        const cy = Number(yv[cellIndex]);
        for (const [rx, ry] of HEXBIN_RING) {
          kinds.push(4); stableIds.push(stableId); styleRefs.push(styleRef);
          diameter.push(0); symbols.push(0);
          x0.push(cx + rx * dx); y0.push(cy + ry * dy); x1.push(0); y1.push(0);
        }
      }
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
      if (
        Array.from(xv).some((value) => !Number.isFinite(value))
        || Array.from(yv).some((value) => !Number.isFinite(value))
        || Array.from(base).some((value) => !Number.isFinite(value))
      ) {
        throw new RangeError("Scene v12 does not yet encode missing-data breaks or nonfinite coordinates");
      }
      const strokePerimeter = style.stroke_perimeter === undefined ? false : style.stroke_perimeter;
      if (typeof strokePerimeter !== "boolean") {
        throw new RangeError("Scene v25 area stroke_perimeter must be a boolean");
      }
      const outline = strokePerimeter ? 2 : 1;
      for (let index = 0; index < xv.length; index += 1) {
        kinds.push(3); stableIds.push(id); styleRefs.push(styleRef);
        diameter.push(0); symbols.push(outline);
        x0.push(xv[index]); y0.push(yv[index]); x1.push(xv[index]); y1.push(base[index]);
      }
      continue;
    }

    if (RECT_KINDS.has(trace.kind)) {
      const count = requireEqualColumns([trace.x0, trace.y0, trace.x1, trace.y1], trace.kind, "rectangle");
      for (let index = 0; index < count; index += 1) {
        kinds.push(2); stableIds.push(id); styleRefs.push(styleRef);
        diameter.push(0); symbols.push(0);
        x0.push(trace.x0[index]); y0.push(trace.y0[index]); x1.push(trace.x1[index]); y1.push(trace.y1[index]);
      }
      continue;
    }

    if (SEGMENT_KINDS.has(trace.kind)) {
      const count = requireEqualColumns([trace.x0, trace.y0, trace.x1, trace.y1], trace.kind, "endpoint");
      for (let index = 0; index < count; index += 1) {
        const stableId = (BigInt(id) << 32n) | BigInt(index);
        for (const [px, py] of [[trace.x0[index], trace.y0[index]], [trace.x1[index], trace.y1[index]]]) {
          kinds.push(1); stableIds.push(stableId); styleRefs.push(styleRef);
          diameter.push(0); symbols.push(0);
          x0.push(px); y0.push(py); x1.push(0); y1.push(0);
        }
      }
      continue;
    }

    let xv = trace.x;
    let yv = trace.y;
    const where = style.step;
    if (where != null) {
      if (trace.kind !== "line") throw new RangeError("Scene v12 step expansion applies only to line traces");
      if (!["pre", "post", "mid"].includes(where)) {
        throw new RangeError(`Scene v12 does not support step mode ${JSON.stringify(where)}`);
      }
    }
    if (xv == null || yv == null || xv.length !== yv.length) {
      throw new RangeError("Scene v12 does not yet encode missing-data breaks or nonfinite coordinates");
    }
    if (Array.from(xv).some((value) => !Number.isFinite(value)) || Array.from(yv).some((value) => !Number.isFinite(value))) {
      throw new RangeError("Scene v12 does not yet encode missing-data breaks or nonfinite coordinates");
    }
    const kindCode = trace.kind === "scatter" ? 0 : 1;
    const runStart = kinds.length;
    for (let index = 0; index < xv.length; index += 1) {
      kinds.push(kindCode); stableIds.push(id); styleRefs.push(styleRef);
      diameter.push(trace.kind === "scatter" ? Number(style.size ?? style.diameter ?? 4) : 0);
      symbols.push(trace.kind === "scatter" ? sceneSymbolCode(style.symbol ?? 0) : 0);
      x0.push(xv[index]); y0.push(yv[index]); x1.push(0); y1.push(0);
    }
    if (where != null) expansionRuns.push([runStart, kinds.length, { pre: 1, mid: 2, post: 3 }[where]]);
  }
  const annotationPrefix = 0x5859000000000000n, attachedLabels = [], straightArrows = [], cartesianCallouts = [], wrappedAnnotations = [];
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
    const append = (recordKind, a, b, c = 0, d = 0, size = 0, symbol = 0) => {
      if (![a, b, c, d, size].every(Number.isFinite)) throw new RangeError(`Scene v12 ${kind} annotation geometry must be finite`);
      kinds.push(recordKind); stableIds.push(stableId); styleRefs.push(styleRef); diameter.push(size); symbols.push(symbol); x0.push(a); y0.push(b); x1.push(c); y1.push(d);
    };
    if (kind === "rule") {
      const value = annotationNumber(annotation, "value", undefined, `${kind} value`);
      if (annotation.axis === "x") { append(1, value, Number(yDomain[0])); append(1, value, Number(yDomain[1])); }
      else if (annotation.axis === "y") { append(1, Number(xDomain[0]), value); append(1, Number(xDomain[1]), value); }
      else throw new RangeError("Scene v12 rule annotation axis must be 'x' or 'y'");
    } else if (kind === "band") {
      const start = annotationNumber(annotation, "start", undefined, `${kind} start`);
      const end = annotationNumber(annotation, "end", undefined, `${kind} end`);
      if (annotation.axis === "x") append(2, start, Number(yDomain[0]), end, Number(yDomain[1]));
      else if (annotation.axis === "y") append(2, Number(xDomain[0]), start, Number(xDomain[1]), end);
      else throw new RangeError("Scene v12 band annotation axis must be 'x' or 'y'");
    } else {
      const size = annotationNumber(annotation, "size", 8, `${kind} size`);
      if (!Number.isFinite(size) || size <= 0) throw new RangeError("Scene v12 marker annotation size must be finite and positive");
      append(0, annotationNumber(annotation, "x", undefined, `${kind} x`), annotationNumber(annotation, "y", undefined, `${kind} y`), 0, 0, size, annotationSymbolCode(annotation.symbol ?? "circle"));
    }
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
    const xyatV3 = rows.some((row) => row.labelBorder != null), xyatV2 = rows.some((row) => row.labelFill != null), xyatFixedBytes = xyatV3 ? 40 : xyatV2 ? 28 : 24;
    const xyat = new Uint8Array(12 + rows.reduce((n, row) => n + xyatFixedBytes + row.text.length, 0)); const xyatView = new DataView(xyat.buffer); xyat.set(textEncoder.encode("XYAT")); xyatView.setUint32(4, xyatV3 ? 3 : xyatV2 ? 2 : 1, true); xyatView.setUint32(8, rows.length, true); let at = 12;
    for (const row of rows) { xyatView.setFloat64(at, row.x, true); xyatView.setFloat64(at + 8, row.y, true); xyat.set(row.rgba, at + 16); if (xyatV3 || xyatV2) xyat.set(row.labelFill ?? [0, 0, 0, 0], at + 20); if (xyatV3) { xyat.set(row.labelBorder?.rgba ?? [0, 0, 0, 0], at + 24); xyatView.setFloat64(at + 28, row.labelBorder?.width ?? 0, true); } xyatView.setUint32(at + xyatFixedBytes - 4, row.text.length, true); xyat.set(row.text, at + xyatFixedBytes); at += xyatFixedBytes + row.text.length; }
    const xyalV4 = attachedLabels.some((row) => row.labelBorder != null), xyalV3 = attachedLabels.some((row) => row.labelFill != null), xyalFixedBytes = xyalV4 ? 32 : xyalV3 ? 20 : 16;
    const xyal = new Uint8Array(12 + attachedLabels.reduce((n, row) => n + xyalFixedBytes + row.text.length, 0)); const xyalView = new DataView(xyal.buffer); xyal.set(textEncoder.encode("XYAL")); xyalView.setUint32(4, xyalV4 ? 4 : xyalV3 ? 3 : 2, true); xyalView.setUint32(8, attachedLabels.length, true); at = 12;
    for (const row of attachedLabels) { xyalView.setBigUint64(at, row.stableId, true); xyal.set(row.rgba, at + 8); if (xyalV4 || xyalV3) xyal.set(row.labelFill ?? [0, 0, 0, 0], at + 12); if (xyalV4) { xyal.set(row.labelBorder?.rgba ?? [0, 0, 0, 0], at + 16); xyalView.setFloat64(at + 20, row.labelBorder?.width ?? 0, true); } xyalView.setUint32(at + xyalFixedBytes - 4, row.text.length, true); xyal.set(row.text, at + xyalFixedBytes); at += xyalFixedBytes + row.text.length; }
    const xyar = new Uint8Array(12 + straightArrows.length * 60), xyarView = new DataView(xyar.buffer); xyar.set(textEncoder.encode("XYAR")); xyarView.setUint32(4, 1, true); xyarView.setUint32(8, straightArrows.length, true); at = 12;
    for (const row of straightArrows) { xyarView.setBigUint64(at, row.stableId, true); xyarView.setFloat64(at + 8, row.x0, true); xyarView.setFloat64(at + 16, row.y0, true); xyarView.setFloat64(at + 24, row.x1, true); xyarView.setFloat64(at + 32, row.y1, true); xyar.set(row.rgba, at + 40); xyarView.setFloat64(at + 44, row.opacity, true); xyarView.setFloat64(at + 52, row.width, true); at += 60; }
    const xyacV3 = cartesianCallouts.some((row) => row.labelBorder != null), xyacV2 = cartesianCallouts.some((row) => row.labelFill != null), xyacFixedBytes = xyacV3 ? 76 : xyacV2 ? 64 : 60;
    const xyac = new Uint8Array(12 + cartesianCallouts.reduce((n, row) => n + xyacFixedBytes + row.text.length, 0)), xyacView = new DataView(xyac.buffer); xyac.set(textEncoder.encode("XYAC")); xyacView.setUint32(4, xyacV3 ? 3 : xyacV2 ? 2 : 1, true); xyacView.setUint32(8, cartesianCallouts.length, true); at = 12;
    for (const row of cartesianCallouts) { xyacView.setFloat64(at, row.x, true); xyacView.setFloat64(at + 8, row.y, true); xyacView.setFloat64(at + 16, row.dx, true); xyacView.setFloat64(at + 24, row.dy, true); xyac.set(row.rgba, at + 32); xyacView.setFloat64(at + 36, row.opacity, true); xyacView.setFloat64(at + 44, row.width, true); xyacView.setUint8(at + 52, row.anchorCode); xyacView.setUint32(at + 56, row.text.length, true); if (xyacV3 || xyacV2) xyac.set(row.labelFill ?? [0, 0, 0, 0], at + 60); if (xyacV3) { xyac.set(row.labelBorder?.rgba ?? [0, 0, 0, 0], at + 64); xyacView.setFloat64(at + 68, row.labelBorder?.width ?? 0, true); } xyac.set(row.text, at + xyacFixedBytes); at += xyacFixedBytes + row.text.length; }
    const wrapped = wrappedAnnotations.map((a) => { const s = { ...(a.style ?? {}) }, allowed = ["color","opacity","label_background","label_border_color","label_border_width"]; if (a.class_name != null && a.class_name !== "" || typeof a.text !== "string" || !a.text || a.text.includes("\\0") || a.text.includes("\\r") || Object.keys(s).some((k) => !allowed.includes(k) && s[k] != null)) throw new RangeError("Scene wrapped annotations do not encode class_name, custom fonts, CSS, markup, collision, or leader style"); const text=textEncoder.encode(a.text), x=annotationNumber(a,"x",undefined,"wrapped x"), y=annotationNumber(a,"y",undefined,"wrapped y"), dx=annotationNumber(a,"dx",a.kind === "callout" ? 36 : 6,"wrapped dx"), dy=annotationNumber(a,"dy",a.kind === "callout" ? -30 : -6,"wrapped dy"), wrap=annotationNumber(a,"wrap",undefined,"wrapped width"), anchor={start:0,middle:1,end:2}[a.anchor ?? "start"], opacity=annotationNumber(s,"opacity",1,"wrapped opacity"); if (text.length > 4096 || ![x,y,dx,dy,wrap,opacity].every(Number.isFinite) || wrap < 0 || opacity < 0 || opacity > 1 || anchor == null) throw new RangeError("Scene wrapped annotation values are invalid"); const fill=s.label_background == null ? [0,0,0,0] : rgba8(annotationColor(s,"label_background","","wrapped background"),1,"wrapped background"); if ((s.label_border_color == null) !== (s.label_border_width == null)) throw new RangeError("Scene wrapped label border requires color and width"); const border=s.label_border_color == null ? null : { rgba:rgba8(annotationColor(s,"label_border_color","","wrapped border"),1,"wrapped border"), width:annotationNumber(s,"label_border_width",undefined,"wrapped border width") }; if (border && (!Number.isFinite(border.width) || border.width <= 0 || fill[3] === 0)) throw new RangeError("Scene wrapped label border requires a positive width and background"); return {a,text,x,y,dx,dy,wrap,anchor,opacity,fill,border}; });
    const xyaw = new Uint8Array(12 + wrapped.reduce((n,r)=>n+68+r.text.length,0)), xyawView = new DataView(xyaw.buffer); xyaw.set(textEncoder.encode("XYAW")); xyawView.setUint32(4,1,true); xyawView.setUint32(8,wrapped.length,true); at=12; for(const r of wrapped) { xyawView.setFloat64(at,r.x,true); xyawView.setFloat64(at+8,r.y,true); xyawView.setFloat64(at+16,r.dx,true); xyawView.setFloat64(at+24,r.dy,true); xyawView.setFloat64(at+32,r.wrap,true); xyaw.set(rgba8(annotationColor(r.a.style ?? {},"color",r.a.kind === "callout" ? "#344054":"#667085","wrapped color"),r.opacity,"wrapped"),at+40); xyaw.set(r.fill,at+44); xyaw.set(r.border?.rgba ?? [0,0,0,0],at+48); xyawView.setFloat64(at+52,r.border?.width ?? 0,true); xyawView.setUint8(at+60,r.a.kind === "callout" ? 1:0); xyawView.setUint8(at+61,r.anchor); xyawView.setUint32(at+64,r.text.length,true); xyaw.set(r.text,at+68); at+=68+r.text.length; }
    const xyadV3 = wrapped.length > 0, header = xyadV3 ? 28 : 24, out = new Uint8Array(header + xyat.length + xyal.length + xyar.length + xyac.length + (xyadV3 ? xyaw.length : 0)), view = new DataView(out.buffer); out.set(textEncoder.encode("XYAD")); view.setUint32(4,xyadV3 ? 3 : 2,true); view.setUint32(8,xyat.length,true); view.setUint32(12,xyal.length,true); view.setUint32(16,xyar.length,true); view.setUint32(20,xyac.length,true); if (xyadV3) view.setUint32(24,xyaw.length,true); out.set(xyat,header); out.set(xyal,header+xyat.length); out.set(xyar,header+xyat.length+xyal.length); out.set(xyac,header+xyat.length+xyal.length+xyar.length); if (xyadV3) out.set(xyaw,header+xyat.length+xyal.length+xyar.length+xyac.length); return out;
  })();
  const title = figure.title ?? "";
  const expansionModes = new Uint8Array(kinds.length);
  for (const [start, end, mode] of expansionRuns) expansionModes.fill(mode, start, end);
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
    title, xLabel, yLabel, chromeStyle: figureChromeStyle(figure), xMajorTicks: (figure.xAxis ?? figure.x_axis)?.tickValues ?? (figure.xAxis ?? figure.x_axis)?.tick_values ?? null, xMinorTicks: (figure.xAxis ?? figure.x_axis)?.minorTickValues ?? (figure.xAxis ?? figure.x_axis)?.minor_tick_values ?? [], yMajorTicks: (figure.yAxis ?? figure.y_axis)?.tickValues ?? (figure.yAxis ?? figure.y_axis)?.tick_values ?? null, yMinorTicks: (figure.yAxis ?? figure.y_axis)?.minorTickValues ?? (figure.yAxis ?? figure.y_axis)?.minor_tick_values ?? [], xTickLabels: (figure.xAxis ?? figure.x_axis)?.tickLabels ?? (figure.xAxis ?? figure.x_axis)?.tick_labels ?? null, yTickLabels: (figure.yAxis ?? figure.y_axis)?.tickLabels ?? (figure.yAxis ?? figure.y_axis)?.tick_labels ?? null, xFormat: xSceneAxis.format, yFormat: ySceneAxis.format, legendInput: legendInput(figure, legendEntries, styles), colorbarInput: encodedColorbar, authoredTextAnnotations: authoredText,
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
