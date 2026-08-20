/** Thin Node adapter for the versioned Rust-owned canonical scene IR. */
import {
  pointer,
  xySceneAxisTicks,
  xySceneBatchEncode,
  xyScenePlotLayout,
  xySceneRasterCommands,
  xySceneScaleMap,
  xySceneScatterSvg,
  xySceneSvg,
  xySceneVersion,
} from "./native.js";
import { asF64Array, f64Ptr, shouldUseDensity, u32Ptr, u8Ptr } from "./encode.js";
import { parseCssColor } from "./color.js";

const USIZE_MAX_64 = (1n << 64n) - 1n;
const SYMBOL_CODES = new Map([
  "circle", "square", "diamond", "triangle", "cross", "hexagon", "pentagon", "star",
  "triangle_down", "triangle_left", "triangle_right", "x", "point", "pixel",
  "thin_diamond", "plus_line", "x_line", "horizontal_line", "vertical_line",
].map((name, code) => [name, code]));

function sceneSymbolCode(value) {
  if (typeof value === "string") {
    const code = SYMBOL_CODES.get(value);
    if (code == null) throw new RangeError(`Scene v6 does not support scatter symbol ${JSON.stringify(value)}`);
    return code;
  }
  if (!Number.isInteger(value) || value < 0 || value >= SYMBOL_CODES.size) {
    throw new RangeError("Scene v6 scatter symbol code must be an integer from 0 through 18");
  }
  return value;
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
  }
  if (kindCode < 0) {
    throw new RangeError("kind must be linear, log, category, angular, or time");
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

/** Encode the shared backend-neutral Scene v6 typed batch. */
export function sceneBatchEncode({
  viewport, margins, xAxis, yAxis, kinds, stableIds, styleRefs, styles, diameter, symbols, x0, y0, x1, y1,
  title = "", xLabel = "", yLabel = "",
}) {
  if (!Array.isArray(viewport) || viewport.length !== 2 || !Array.isArray(margins) || margins.length !== 4) {
    throw new RangeError("viewport and margins must contain two and four values");
  }
  const kindArray = asUnsignedArray(kinds, "kinds", 255, Uint8Array);
  const ids = asStableIds(stableIds);
  const styleRefArray = asUnsignedArray(styleRefs, "styleRefs", 0xffff_ffff, Uint32Array);
  const diameters = asF64Array(diameter, "diameter");
  const symbolCodes = asUnsignedArray(symbols, "symbols", 255, Uint8Array);
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
  for (const [value, name] of [[ids, "stableIds"], [styleRefArray, "styleRefs"], [diameters, "diameter"], [symbolCodes, "symbols"], ...coordinates.map((value, index) => [value, ["x0", "y0", "x1", "y1"][index]])]) requireLength(value, length, name);
  const xd = axisDescriptor(xAxis, "xAxis");
  const yd = axisDescriptor(yAxis, "yAxis");
  const titleBytes = new TextEncoder().encode(String(title ?? ""));
  const xLabelBytes = new TextEncoder().encode(String(xLabel ?? ""));
  const yLabelBytes = new TextEncoder().encode(String(yLabel ?? ""));
  let capacity = 160 + widths.length * 16 + length * 56 + 40 + titleBytes.length + xLabelBytes.length + yLabelBytes.length;
  for (;;) {
    const output = new Uint8Array(capacity);
    const rawWritten = xySceneBatchEncode(
      Number(viewport[0]), Number(viewport[1]), ...margins.map(Number), ...xd, ...yd,
      u8Ptr(kindArray), pointer(ids, "uint64_t *"), u32Ptr(styleRefArray),
      u8Ptr(fills), u8Ptr(strokes), f64Ptr(widths), BigInt(widths.length),
      f64Ptr(diameters), u8Ptr(symbolCodes),
      ...coordinates.map(f64Ptr), BigInt(length),
      titleBytes.length ? u8Ptr(titleBytes) : 0, BigInt(titleBytes.length),
      xLabelBytes.length ? u8Ptr(xLabelBytes) : 0, BigInt(xLabelBytes.length),
      yLabelBytes.length ? u8Ptr(yLabelBytes) : 0, BigInt(yLabelBytes.length),
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

function rgba8(css, opacity, name) {
  const parsed = parseCssColor(css);
  if (parsed == null) throw new RangeError(`${name} must be a supported constant CSS color`);
  return parsed.map((value, index) => Math.round(value * (index === 3 ? opacity : 1) * 255));
}

const RECT_KINDS = new Set(["bar", "column", "histogram", "violin", "box"]);
const SEGMENT_KINDS = new Set(["segments", "errorbar", "stem", "contour", "box_whisker", "box_median"]);
const BAND_KINDS = new Set(["area", "error_band"]);
const STROKE_KINDS = new Set(["line", "segments", "errorbar", "stem", "contour", "box_whisker", "box_median"]);
const SUPPORTED_KINDS = new Set([
  "scatter", "line", "bar", "column", "histogram", "violin", "box",
  "segments", "errorbar", "stem", "contour", "box_whisker", "box_median",
  "area", "error_band",
]);

function rejectRectExtras(style, kind) {
  if (style.fill != null && typeof style.fill === "object") {
    throw new RangeError(`Scene v6 does not yet encode ${kind} gradient fills`);
  }
  const radius = style.corner_radius ?? 0;
  if (Array.isArray(radius)) {
    if (radius.some((value) => Number(value) !== 0)) {
      throw new RangeError(`Scene v6 does not yet encode ${kind} corner_radius`);
    }
  } else if (Number(radius) !== 0) {
    throw new RangeError(`Scene v6 does not yet encode ${kind} corner_radius`);
  }
  if (Number(style.wedge_gap ?? 0) !== 0) {
    throw new RangeError(`Scene v6 does not yet encode ${kind} wedge_gap`);
  }
}

function stepArrays(xv, yv, where) {
  if (xv.length < 2) return { x: xv, y: yv };
  const xs = [Number(xv[0])];
  const ys = [Number(yv[0])];
  for (let index = 1; index < xv.length; index += 1) {
    if (where === "pre") {
      xs.push(Number(xv[index - 1]), Number(xv[index]));
      ys.push(Number(yv[index]), Number(yv[index]));
    } else if (where === "mid") {
      const mid = (Number(xv[index - 1]) + Number(xv[index])) * 0.5;
      xs.push(mid, mid, Number(xv[index]));
      ys.push(Number(yv[index - 1]), Number(yv[index]), Number(yv[index]));
    } else {
      xs.push(Number(xv[index]), Number(xv[index]));
      ys.push(Number(yv[index - 1]), Number(yv[index]));
    }
  }
  return { x: xs, y: ys };
}

function requireEqualColumns(columns, kind, label) {
  if (columns.some((column) => column == null)) {
    throw new RangeError(`${kind} Scene v6 compilation requires four ${label} columns`);
  }
  const count = columns[0].length;
  if (columns.some((column) => column.length !== count)) {
    throw new RangeError(`Scene v6 ${kind} ${label} columns must have equal length`);
  }
  if (columns.some((column) => Array.from(column).some((value) => !Number.isFinite(value)))) {
    throw new RangeError("Scene v6 does not yet encode missing-data breaks or nonfinite coordinates");
  }
  return count;
}

/** Compile migrated cartesian marks to Scene v6. */
export function figureSceneV3(figure, { margins = null } = {}) {
  if (figure.coords !== "cartesian") throw new RangeError("Scene v6 figure compilation currently supports cartesian coordinates only");
  if (figure.annotations?.length) throw new RangeError("Scene v6 does not yet encode annotations");
  const unsupported = figure.traces.find((trace) => !SUPPORTED_KINDS.has(trace.kind));
  if (unsupported) throw new RangeError(`Scene v6 figure compilation does not yet support ${unsupported.kind}`);
  const kinds = [], stableIds = [], styleRefs = [], diameter = [], symbols = [], x0 = [], y0 = [], x1 = [], y1 = [], styles = [];
  for (const trace of figure.traces) {
    if (trace.name != null) throw new RangeError("Scene v6 does not yet encode legends");
    if (trace.x_axis !== "x" || trace.y_axis !== "y") throw new RangeError("Scene v6 currently supports only the primary x/y axes");
    if (
      trace.kind === "scatter" &&
      shouldUseDensity(trace.x?.length ?? 0, {
        forceDensity: Boolean(trace.force_density ?? trace.forceDensity),
        forceDirect: Boolean(trace.force_direct ?? trace.forceDirect),
        coords: figure.coords ?? "cartesian",
      })
    ) {
      throw new RangeError("Scene v6 does not yet encode density-tier scatter");
    }
    const style = trace.style ?? {};
    for (const key of ["color_channel", "size_channel", "stroke_channel", "dash", "curve", "smooth", "linecap", "marker_path", "marker_glyph"]) {
      if (style[key] != null) throw new RangeError(`Scene v6 figure compilation does not yet support ${key}`);
    }
    if (RECT_KINDS.has(trace.kind)) rejectRectExtras(style, trace.kind);
    const opacity = Number(style.opacity ?? 1);
    if (!Number.isFinite(opacity) || opacity < 0 || opacity > 1) throw new RangeError("trace opacity must be in [0, 1]");
    const color = style.color ?? "#3987e5";
    const fillDefault = SEGMENT_KINDS.has(trace.kind) ? "#00000000" : color;
    const fillCss = style.fill ?? fillDefault;
    if (typeof fillCss !== "string") throw new RangeError(`Scene v6 does not yet encode ${trace.kind} non-CSS fills`);
    const strokeCss = style.stroke ?? (STROKE_KINDS.has(trace.kind) ? color : "#00000000");
    const width = Number(
      style.stroke_width ?? style.width ?? style.line_width ?? (STROKE_KINDS.has(trace.kind) ? 1.5 : 0),
    );
    styles.push({ fillRgba: rgba8(fillCss, opacity, "fill"), strokeRgba: rgba8(strokeCss, opacity, "stroke"), strokeWidth: width });
    const styleRef = styles.length - 1;
    const id = Number(trace.id);

    if (BAND_KINDS.has(trace.kind)) {
      const xv = trace.x, yv = trace.y, base = trace.base;
      if (xv == null || yv == null || base == null) {
        throw new RangeError(`${trace.kind} Scene v6 compilation requires x, y, and base columns`);
      }
      if (!(xv.length === yv.length && yv.length === base.length)) {
        throw new RangeError(`Scene v6 ${trace.kind} band columns must have equal length`);
      }
      if (
        Array.from(xv).some((value) => !Number.isFinite(value))
        || Array.from(yv).some((value) => !Number.isFinite(value))
        || Array.from(base).some((value) => !Number.isFinite(value))
      ) {
        throw new RangeError("Scene v6 does not yet encode missing-data breaks or nonfinite coordinates");
      }
      for (let index = 0; index < xv.length; index += 1) {
        kinds.push(3); stableIds.push(id); styleRefs.push(styleRef);
        diameter.push(0); symbols.push(0);
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
      if (trace.kind !== "line") throw new RangeError("Scene v6 step expansion applies only to line traces");
      if (!["pre", "post", "mid"].includes(where)) {
        throw new RangeError(`Scene v6 does not support step mode ${JSON.stringify(where)}`);
      }
      const stepped = stepArrays(xv, yv, where);
      xv = stepped.x; yv = stepped.y;
    }
    if (xv == null || yv == null || xv.length !== yv.length) {
      throw new RangeError("Scene v6 does not yet encode missing-data breaks or nonfinite coordinates");
    }
    if (Array.from(xv).some((value) => !Number.isFinite(value)) || Array.from(yv).some((value) => !Number.isFinite(value))) {
      throw new RangeError("Scene v6 does not yet encode missing-data breaks or nonfinite coordinates");
    }
    const kindCode = trace.kind === "scatter" ? 0 : 1;
    for (let index = 0; index < xv.length; index += 1) {
      kinds.push(kindCode); stableIds.push(id); styleRefs.push(styleRef);
      diameter.push(trace.kind === "scatter" ? Number(style.size ?? style.diameter ?? 4) : 0);
      symbols.push(trace.kind === "scatter" ? sceneSymbolCode(style.symbol ?? 0) : 0);
      x0.push(xv[index]); y0.push(yv[index]); x1.push(0); y1.push(0);
    }
  }
  const title = figure.title ?? "";
  const xLabel = figure.xLabel ?? figure.x_label ?? "";
  const yLabel = figure.yLabel ?? figure.y_label ?? "";
  const xDomain = figure._range("x");
  const yDomain = figure._range("y");
  let resolvedMargins = margins;
  if (resolvedMargins == null) {
    const out = new Float64Array(4);
    const titleBytes = new TextEncoder().encode(String(title));
    const xLabelBytes = new TextEncoder().encode(String(xLabel));
    const yLabelBytes = new TextEncoder().encode(String(yLabel));
    const written = xyScenePlotLayout(
      Number(figure.width), Number(figure.height), 0,
      0, Number(xDomain[0]), Number(xDomain[1]), 1, 0,
      0, Number(yDomain[0]), Number(yDomain[1]), 1, 0,
      titleBytes.length ? u8Ptr(titleBytes) : 0, BigInt(titleBytes.length),
      xLabelBytes.length ? u8Ptr(xLabelBytes) : 0, BigInt(xLabelBytes.length),
      yLabelBytes.length ? u8Ptr(yLabelBytes) : 0, BigInt(yLabelBytes.length),
      f64Ptr(out),
    );
    if (written !== 4n && written !== 4) throw new RangeError("invalid canonical scene plot layout");
    resolvedMargins = [out[0], out[1], out[2], out[3]];
  }
  return sceneBatchEncode({ viewport: [figure.width, figure.height], margins: resolvedMargins,
    xAxis: { id: 1, domain: xDomain }, yAxis: { id: 2, domain: yDomain },
    kinds, stableIds, styleRefs, styles, diameter, symbols, x0, y0, x1, y1,
    title, xLabel, yLabel,
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
