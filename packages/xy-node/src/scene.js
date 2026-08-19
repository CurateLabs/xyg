/** Thin Node adapter for the versioned Rust-owned canonical scene IR. */
import {
  pointer,
  xySceneAxisTicks,
  xySceneBatchEncode,
  xySceneScaleMap,
  xySceneScatterSvg,
  xySceneVersion,
} from "./native.js";
import { asF64Array, f64Ptr, u32Ptr, u8Ptr } from "./encode.js";

const USIZE_MAX_64 = (1n << 64n) - 1n;

function asU8Array(value, name) {
  if (value instanceof Uint8Array) return value;
  if (value == null) return new Uint8Array(0);
  try {
    return Uint8Array.from(value, (item) => Number(item));
  } catch (error) {
    throw new TypeError(`${name} must be an array-like byte sequence`, { cause: error });
  }
}

function requireLength(value, length, name) {
  if (value.length !== length) {
    throw new RangeError(`${name} must have length ${length}, got ${value.length}`);
  }
}

export function sceneVersion() {
  return xySceneVersion();
}

export function axisTicks({ kind = "linear", lo, hi, target = 6 }) {
  const kindCode = kind === "linear" ? 0 : kind === "log" ? 1 : -1;
  if (kindCode < 0) throw new RangeError("kind must be linear or log");
  const capacity = 200;
  const ticks = new Float64Array(capacity);
  const labeled = new Float64Array(capacity);
  const labeledLength = new BigUint64Array(1);
  const step = new Float64Array(1);
  const rawWritten = xySceneAxisTicks(
    kindCode, Number(lo), Number(hi), BigInt(target),
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
  return [BigInt(id), kindCode, Number(domain[0]), Number(domain[1]), Number(constant), nonpositive === "mask" ? 1 : 0];
}

/** Encode the shared backend-neutral Scene v2 typed batch. */
export function sceneBatchEncode({ viewport, margins, xAxis, yAxis, kinds, stableIds, styleRefs, styles, diameter, symbols, x0, y0, x1, y1 }) {
  if (!Array.isArray(viewport) || viewport.length !== 2 || !Array.isArray(margins) || margins.length !== 4) {
    throw new RangeError("viewport and margins must contain two and four values");
  }
  const kindArray = kinds instanceof Uint8Array ? kinds : Uint8Array.from(kinds);
  const ids = stableIds instanceof BigUint64Array ? stableIds : BigUint64Array.from(stableIds, BigInt);
  const styleRefArray = styleRefs instanceof Uint32Array ? styleRefs : Uint32Array.from(styleRefs, Number);
  const diameters = asF64Array(diameter, "diameter");
  const symbolCodes = symbols instanceof Uint8Array ? symbols : Uint8Array.from(symbols);
  const fills = new Uint8Array(styles.length * 4);
  const strokes = new Uint8Array(styles.length * 4);
  const widths = new Float64Array(styles.length);
  for (const [index, style] of styles.entries()) {
    const fill = asU8Array(style.fillRgba, `styles[${index}].fillRgba`);
    const stroke = asU8Array(style.strokeRgba, `styles[${index}].strokeRgba`);
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
  let capacity = 160 + widths.length * 16 + length * 56;
  for (;;) {
    const output = new Uint8Array(capacity);
    const rawWritten = xySceneBatchEncode(
      Number(viewport[0]), Number(viewport[1]), ...margins.map(Number), ...xd, ...yd,
      u8Ptr(kindArray), pointer(ids, "uint64_t *"), u32Ptr(styleRefArray),
      u8Ptr(fills), u8Ptr(strokes), f64Ptr(widths), BigInt(widths.length),
      f64Ptr(diameters), u8Ptr(symbolCodes),
      ...coordinates.map(f64Ptr), BigInt(length), u8Ptr(output), BigInt(capacity),
    );
    if (rawWritten === USIZE_MAX_64) throw new RangeError("invalid canonical scene batch");
    const written = Number(rawWritten);
    if (!Number.isSafeInteger(written) || written < 0) throw new RangeError("canonical scene batch exceeded host output limits");
    if (written <= capacity) return output.slice(0, written);
    capacity = written;
  }
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
