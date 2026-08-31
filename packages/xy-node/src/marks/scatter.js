/**
 * Thin scatter mark builder — TypedArray ingest → figure scatter trace.
 * Encode stays in Rust (`xyg_encode_f32`); host only coerces and attaches.
 */

import { cssIsFunctional, resolveColorChannel } from "../color.js";
import { asF64Array, canonicalScatterColumn, encodeF32Values, minMax } from "../encode.js";

const BUILTIN_SYMBOLS = [
  "circle",
  "square",
  "diamond",
  "triangle",
  "cross",
  "hexagon",
  "pentagon",
  "star",
  "triangle_down",
  "triangle_left",
  "triangle_right",
  "x",
  "point",
  "pixel",
  "thin_diamond",
  "plus_line",
  "x_line",
  "horizontal_line",
  "vertical_line",
];
const SYMBOL_CODES = new Map(BUILTIN_SYMBOLS.map((name, code) => [name, code]));

/** Match Python `_validate.point_symbol` for scatter marker shapes. */
export function validatePointSymbol(symbol, label = "scatter symbol") {
  if (typeof symbol !== "string" || !SYMBOL_CODES.has(symbol)) {
    throw new RangeError(`${label} must be one of ${[...BUILTIN_SYMBOLS].sort().join(", ")}`);
  }
  return symbol;
}

/** Match Python `marks._direct_symbols` for scatter symbol authoring. */
export function resolveSymbolChannel(symbol, n) {
  if (symbol == null) {
    return { symbolValue: "circle", styleChannels: null };
  }
  if (typeof symbol === "string") {
    return { symbolValue: validatePointSymbol(symbol), styleChannels: null };
  }
  const values = Array.from(symbol);
  if (values.length !== n) {
    throw new RangeError(`scatter symbol array must be 1-D length ${n}, got length ${values.length}`);
  }
  const codes = new Uint8Array(n);
  for (let index = 0; index < n; index += 1) {
    codes[index] = SYMBOL_CODES.get(validatePointSymbol(values[index], `scatter symbol[${index}]`));
  }
  return {
    symbolValue: "circle",
    styleChannels: { symbol: { values: codes, dtype: "u8" } },
  };
}

/** Match Python `marks._stroke_channel` for scatter stroke authoring. */
export function resolveStrokeChannel(stroke, n) {
  if (stroke == null) {
    return { strokeValue: null, strokeCh: null };
  }
  if (typeof stroke === "string") {
    if (!cssIsFunctional(stroke)) {
      throw new RangeError("scatter stroke must be a CSS color");
    }
    return { strokeValue: stroke, strokeCh: null };
  }
  const resolved = resolveColorChannel(stroke, n, "transparent");
  if (resolved.mode !== "direct_rgba") {
    throw new RangeError(
      `scatter stroke arrays must be numeric RGB/RGBA or CSS colors with length ${n}`,
    );
  }
  return { strokeValue: null, strokeCh: resolved };
}

export function normalizeScatterStyle(style = {}) {
  const normalized = { ...style };
  if (normalized.stroke != null && normalized.stroke_width == null) {
    normalized.stroke_width = 1;
  }
  return normalized;
}

function optionalBoolean(value, name) {
  if (value == null) return undefined;
  if (typeof value !== "boolean") {
    throw new TypeError(`${name} must be a boolean`);
  }
  return value;
}

/** Match Python `channels.resolve_size` for Scene XYTC diameter packing. */
export function resolveSizeChannel(size, n, rangePx = [2, 18]) {
  const range_px = rangePx;
  if (size == null) {
    return { mode: "constant", constant: 4.0, range_px };
  }
  if (typeof size === "number" && Number.isFinite(size)) {
    if (size < 0) throw new RangeError("size must be non-negative");
    return { mode: "constant", constant: size, range_px };
  }
  const values = asF64Array(size, "size");
  if (values.length !== n) {
    throw new RangeError(`size array must be 1-D length ${n}, got length ${values.length}`);
  }
  const mm = minMax(values) ?? [0, 1];
  const lo = mm[0];
  const hi = mm[0] === mm[1] ? mm[0] + 1 : mm[1];
  return { mode: "continuous", values, domain: [lo, hi], range_px };
}

/**
 * @param {ArrayLike|TypedArray} x
 * @param {ArrayLike|TypedArray} y
 * @param {{name?: string|null, style?: object, id?: number}} [opts]
 * @returns {{traces: object[]}}
 */
export function composeScatter(x, y, opts = {}) {
  const xCol = canonicalScatterColumn(x, "x");
  const yCol = canonicalScatterColumn(y, "y");
  const xa = xCol.values;
  const ya = yCol.values;
  if (xa.length !== ya.length) {
    throw new RangeError("scatter x/y length mismatch");
  }
  const forceDensity = opts.forceDensity ?? opts.force_density ?? opts.density;
  const forceDirect = opts.forceDirect ?? opts.force_direct;
  const forcePyramid = opts.forcePyramid ?? opts.force_pyramid;
  const pyramidSpill = optionalBoolean(
    opts.pyramidSpill ?? opts.pyramid_spill,
    "scatter pyramidSpill",
  );
  const n = xa.length;
  const opacity = opts.opacity ?? opts.style?.opacity ?? 0.8;
  const color = opts.color ?? opts.style?.color;
  const color_ch = resolveColorChannel(color, n);
  const sizeRange = opts.sizeRange ?? opts.size_range ?? [2, 18];
  const rawStyle = { ...(opts.style ?? {}) };
  const sizeInput = opts.size ?? rawStyle.size ?? opts.size_ch?.constant ?? null;
  if (rawStyle.size != null) delete rawStyle.size;
  const strokeInput = opts.stroke ?? rawStyle.stroke ?? null;
  if (rawStyle.stroke != null) delete rawStyle.stroke;
  const symbolInput = opts.symbol ?? rawStyle.symbol ?? "circle";
  if (rawStyle.symbol != null) delete rawStyle.symbol;
  const strokeWidthInput = opts.stroke_width ?? opts.strokeWidth ?? rawStyle.stroke_width ?? null;
  if (rawStyle.stroke_width != null) delete rawStyle.stroke_width;
  const size_ch = opts.size_ch ?? resolveSizeChannel(sizeInput, n, sizeRange);
  const { strokeValue, strokeCh } = resolveStrokeChannel(strokeInput, n);
  const { symbolValue, styleChannels: symbolStyleChannels } = resolveSymbolChannel(symbolInput, n);
  let strokeWidth = strokeWidthInput == null ? 0.0 : Number(strokeWidthInput);
  if ((strokeValue != null || strokeCh != null) && strokeWidthInput == null) {
    strokeWidth = 1.0;
  }
  let resolvedStrokeCh = strokeCh;
  if (
    strokeValue == null
    && resolvedStrokeCh == null
    && strokeWidthInput != null
    && strokeWidth !== 0
  ) {
    resolvedStrokeCh = { mode: "match_fill" };
  }
  const style_channels = {
    ...(opts.style_channels ?? {}),
    ...(symbolStyleChannels ?? {}),
  };
  return {
    traces: [
      {
        kind: "scatter",
        name: opts.name ?? null,
        x: xa,
        y: ya,
        _xCol: xCol,
        _yCol: yCol,
        color_ch,
        size_ch,
        ...(resolvedStrokeCh != null ? { stroke_ch: resolvedStrokeCh } : {}),
        ...(Object.keys(style_channels).length ? { style_channels } : {}),
        style: normalizeScatterStyle({
          opacity,
          ...rawStyle,
          ...(symbolValue !== "circle" ? { symbol: symbolValue } : {}),
          ...(strokeValue != null ? { stroke: strokeValue } : {}),
          ...(strokeWidthInput != null || strokeWidth !== 0 ? { stroke_width: strokeWidth } : {}),
        }),
        x_axis: opts.xAxis ?? "x",
        y_axis: opts.yAxis ?? "y",
        ...(forceDensity != null ? { force_density: Boolean(forceDensity) } : {}),

        ...(forceDirect != null ? { force_direct: Boolean(forceDirect) } : {}),
        ...(forcePyramid != null ? { force_pyramid: Boolean(forcePyramid) } : {}),
        ...(pyramidSpill != null ? { pyramid_spill: pyramidSpill } : {}),
        ...(opts.id != null ? { id: opts.id } : {}),
      },
    ],
  };
}

/**
 * Attach a scatter mark to a minimal Node Figure.
 * @param {import("../figure.js").Figure} fig
 * @param {ArrayLike|TypedArray} x
 * @param {ArrayLike|TypedArray} y
 * @param {object} [opts]
 */
export function attachScatter(fig, x, y, opts = {}) {
  const { traces } = composeScatter(x, y, opts);
  const t = traces[0];
  fig.scatter(t.x, t.y, {
    name: t.name,
    style: t.style,
    xAxis: t.x_axis,
    yAxis: t.y_axis,
    id: t.id,
    color_ch: t.color_ch,
    size_ch: t.size_ch,
    ...(t.stroke_ch != null ? { stroke_ch: t.stroke_ch } : {}),
    ...(t.style_channels != null ? { style_channels: t.style_channels } : {}),
    forceDensity: t.force_density,
    forceDirect: t.force_direct,
    forcePyramid: t.force_pyramid,
    pyramidSpill: t.pyramid_spill,
    _composed: true,
  });
  return fig;
}

/**
 * Offset-encode scatter positions the same way Figure.buildPayload ships them
 * (mid-range offset, f32-safe scale) — for Python↔Node bit goldens.
 *
 * @param {ArrayLike|TypedArray} x
 * @param {ArrayLike|TypedArray} y
 */
export function encodeScatterPositions(x, y) {
  const xa = asF64Array(x, "x");
  const ya = asF64Array(y, "y");
  if (xa.length !== ya.length) {
    throw new RangeError("scatter x/y length mismatch");
  }
  const xmm = minMax(xa) ?? [0, 0];
  const ymm = minMax(ya) ?? [0, 0];
  const xOff = (xmm[0] + xmm[1]) / 2.0;
  const yOff = (ymm[0] + ymm[1]) / 2.0;
  const xEnc = encodeF32Values(xa, xOff, xmm[0], xmm[1], { kind: "float" });
  const yEnc = encodeF32Values(ya, yOff, ymm[0], ymm[1], { kind: "float" });
  return {
    x: xEnc.values,
    y: yEnc.values,
    xMeta: xEnc.meta,
    yMeta: yEnc.meta,
    xBounds: xmm,
    yBounds: ymm,
  };
}
