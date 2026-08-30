/**
 * Thin scatter mark builder — TypedArray ingest → figure scatter trace.
 * Encode stays in Rust (`xyg_encode_f32`); host only coerces and attaches.
 */

import { asF64Array, encodeF32Values, minMax } from "../encode.js";

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

/**
 * @param {ArrayLike|TypedArray} x
 * @param {ArrayLike|TypedArray} y
 * @param {{name?: string|null, style?: object, id?: number}} [opts]
 * @returns {{traces: object[]}}
 */
export function composeScatter(x, y, opts = {}) {
  const xa = asF64Array(x, "x");
  const ya = asF64Array(y, "y");
  if (xa.length !== ya.length) {
    throw new RangeError("scatter x/y length mismatch");
  }
  const forceDensity = opts.forceDensity ?? opts.force_density;
  const forceDirect = opts.forceDirect ?? opts.force_direct;
  const forcePyramid = opts.forcePyramid ?? opts.force_pyramid;
  const pyramidSpill = optionalBoolean(
    opts.pyramidSpill ?? opts.pyramid_spill,
    "scatter pyramidSpill",
  );
  return {
    traces: [
      {
        kind: "scatter",
        name: opts.name ?? null,
        x: xa,
        y: ya,
        style: normalizeScatterStyle({ opacity: 0.8, ...(opts.style ?? {}) }),
        x_axis: opts.xAxis ?? "x",
        y_axis: opts.yAxis ?? "y",
        ...(forceDensity != null ? { force_density: Boolean(forceDensity) } : {}),        // Recorded scene-scatter-color-ch stay-host.

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
