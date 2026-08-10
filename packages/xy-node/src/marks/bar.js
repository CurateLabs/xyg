/**
 * Bar/column mark — simple non-stacked rects (numeric x or category indices).
 */

import { asF64Array } from "../encode.js";

function categoryPositions(x) {
  const out = new Float64Array(x.length);
  for (let i = 0; i < x.length; i += 1) out[i] = i;
  return out;
}

function resolvePositions(x) {
  if (x == null) {
    throw new TypeError("bar x is required");
  }
  if (ArrayBuffer.isView(x) || Array.isArray(x)) {
    const first = x.length > 0 ? x[0] : 0;
    if (typeof first === "string") {
      return categoryPositions(x);
    }
    return asF64Array(x, "x");
  }
  if (typeof x[Symbol.iterator] === "function") {
    const items = [...x];
    if (items.length > 0 && typeof items[0] === "string") {
      return categoryPositions(items);
    }
    return Float64Array.from(items, Number);
  }
  return asF64Array(x, "x");
}

/**
 * @param {ArrayLike|TypedArray} x category positions or labels
 * @param {ArrayLike|TypedArray} y bar heights/lengths
 * @param {{
 *   base?: number,
 *   width?: number,
 *   orientation?: "vertical"|"horizontal",
 *   name?: string|null,
 *   style?: object,
 *   color?: string,
 * }} [opts]
 */
export function composeBar(x, y, opts = {}) {
  const pos = resolvePositions(x);
  const vals = asF64Array(y, "y");
  if (pos.length !== vals.length) {
    throw new RangeError("bar x/y length mismatch");
  }
  const width = Number(opts.width ?? 0.8);
  const base = Number(opts.base ?? 0);
  const orientation = opts.orientation ?? "vertical";
  const half = width / 2.0;
  const x0 = new Float64Array(pos.length);
  const x1 = new Float64Array(pos.length);
  const y0 = new Float64Array(pos.length);
  const y1 = new Float64Array(pos.length);
  if (orientation === "horizontal") {
    for (let i = 0; i < pos.length; i += 1) {
      x0[i] = base;
      x1[i] = vals[i];
      y0[i] = pos[i] - half;
      y1[i] = pos[i] + half;
    }
  } else {
    for (let i = 0; i < pos.length; i += 1) {
      x0[i] = pos[i] - half;
      x1[i] = pos[i] + half;
      y0[i] = base;
      y1[i] = vals[i];
    }
  }
  const style = {
    color: opts.color ?? "#3987e5",
    opacity: opts.opacity ?? 0.85,
    role: opts.kind ?? "bar",
    orientation,
    ...(opts.style ?? {}),
  };
  return {
    traces: [
      {
        kind: opts.kind ?? "bar",
        name: opts.name ?? null,
        x0,
        x1,
        y0,
        y1,
        style,
        count: pos.length,
        x_axis: opts.xAxis ?? "x",
        y_axis: opts.yAxis ?? "y",
        ...(opts.id != null ? { id: opts.id } : {}),
      },
    ],
  };
}

/**
 * @param {import("../figure.js").Figure} fig
 * @param {ArrayLike|TypedArray} x
 * @param {ArrayLike|TypedArray} y
 * @param {object} [opts]
 */
export function attachBar(fig, x, y, opts = {}) {
  fig.bar(x, y, opts);
  return fig;
}

/** Column charts share the bar rect renderer. */
export function composeColumn(x, y, opts = {}) {
  return composeBar(x, y, { ...opts, kind: "column" });
}

export function attachColumn(fig, x, y, opts = {}) {
  return attachBar(fig, x, y, { ...opts, kind: "column" });
}
