/**
 * Bar/column mark — grouped / stacked / normalized rects via xy_bar_stack.
 */

import { asF64Array, barStack } from "../encode.js";

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
 * Resolve y into a row-major Float64Array of shape (nSeries, nItems).
 * Accepts 1-D heights or an array-of-series / nested matrix.
 */
function resolveValueMatrix(y, nItems) {
  if (y == null) {
    throw new TypeError("bar y is required");
  }
  if (Array.isArray(y) && y.length > 0 && (Array.isArray(y[0]) || ArrayBuffer.isView(y[0]))) {
    const nSeries = y.length;
    const out = new Float64Array(nSeries * nItems);
    for (let s = 0; s < nSeries; s += 1) {
      const row = asF64Array(y[s], `y[${s}]`);
      if (row.length === nItems) {
        out.set(row, s * nItems);
      } else if (nSeries === nItems && y.every((r) => asF64Array(r).length === y.length)) {
        // category-major matrix: transpose into series-major
        throw new RangeError("ambiguous bar y matrix; pass series-major rows");
      } else {
        throw new RangeError(`bar y[${s}] length ${row.length} != ${nItems}`);
      }
    }
    return { values: out, nSeries };
  }
  // Flat TypedArray that is a matrix: treat as single series unless opts.nSeries set.
  const flat = asF64Array(y, "y");
  if (flat.length === nItems) {
    return { values: flat, nSeries: 1 };
  }
  if (flat.length % nItems === 0) {
    return { values: flat, nSeries: flat.length / nItems };
  }
  throw new RangeError(`bar y length ${flat.length} does not match x length ${nItems}`);
}

/**
 * @param {ArrayLike|TypedArray} x category positions or labels
 * @param {ArrayLike|TypedArray|ArrayLike[]} y bar heights or series matrix
 * @param {{
 *   base?: number|ArrayLike,
 *   width?: number|ArrayLike,
 *   orientation?: "vertical"|"horizontal",
 *   mode?: "grouped"|"stacked"|"normalized",
 *   name?: string|null,
 *   series?: string[],
 *   style?: object,
 *   color?: string|string[],
 *   kind?: string,
 * }} [opts]
 */
export function composeBar(x, y, opts = {}) {
  const pos = resolvePositions(x);
  const { values, nSeries } = resolveValueMatrix(y, pos.length);
  const mode = opts.mode ?? (nSeries > 1 ? "grouped" : "grouped");
  const orientation = opts.orientation ?? "vertical";
  const width = opts.width ?? 0.8;
  const base = opts.base ?? 0;
  const { x0, x1, y0, y1 } = barStack(pos, values, nSeries, width, base, mode, orientation);
  const nItems = pos.length;
  const seriesNames =
    opts.series ??
    (nSeries === 1
      ? [opts.name ?? null]
      : Array.from({ length: nSeries }, (_, i) =>
          opts.name ? `${opts.name} ${i + 1}` : `series ${i + 1}`,
        ));
  const colors = Array.isArray(opts.color)
    ? opts.color
    : Array.from({ length: nSeries }, () => opts.color ?? "#3987e5");
  const kind = opts.kind ?? "bar";
  const traces = [];
  for (let s = 0; s < nSeries; s += 1) {
    const off = s * nItems;
    let role = kind;
    if (nSeries === 1) {
      role = mode === "normalized" ? `${kind}-normalized` : kind;
    } else if (mode === "grouped") {
      role = `${kind}-grouped`;
    } else {
      role = `${kind}-${mode}`;
    }
    const style = {
      color: colors[s] ?? "#3987e5",
      opacity: opts.opacity ?? 0.85,
      role,
      orientation,
      ...(opts.style ?? {}),
    };
    traces.push({
      kind,
      name: seriesNames[s] ?? null,
      x0: x0.subarray(off, off + nItems),
      x1: x1.subarray(off, off + nItems),
      y0: y0.subarray(off, off + nItems),
      y1: y1.subarray(off, off + nItems),
      style,
      count: nItems,
      x_axis: opts.xAxis ?? "x",
      y_axis: opts.yAxis ?? "y",
      ...(opts.id != null && s === 0 ? { id: opts.id } : {}),
    });
  }
  return { traces };
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
