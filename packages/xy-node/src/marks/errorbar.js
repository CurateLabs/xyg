/**
 * Error bars — vertical/horizontal segments with optional caps (Python parity).
 */

import { asF64Array, DEFAULT_MARK_COLOR } from "../encode.js";

/**
 * Auto cap half-width in data units: 0.25 × median adjacent spacing of distinct
 * finite positions, or 0.4 when fewer than two are distinct.
 * @param {Float64Array} positions
 */
export function autoCapSize(positions) {
  const finite = [];
  for (let i = 0; i < positions.length; i += 1) {
    if (Number.isFinite(positions[i])) finite.push(positions[i]);
  }
  if (finite.length >= 2) {
    let sorted = true;
    const gaps = [];
    for (let i = 1; i < finite.length; i += 1) {
      const g = finite[i] - finite[i - 1];
      if (g < 0) {
        sorted = false;
        break;
      }
      if (g !== 0) gaps.push(g);
    }
    if (sorted) {
      if (gaps.length === 0) return 0.4;
      gaps.sort((a, b) => a - b);
      const mid = Math.floor(gaps.length / 2);
      const med = gaps.length % 2 === 0 ? 0.5 * (gaps[mid - 1] + gaps[mid]) : gaps[mid];
      return 0.25 * med;
    }
  }
  const distinct = Array.from(new Set(finite)).sort((a, b) => a - b);
  if (distinct.length < 2) return 0.4;
  const gaps = [];
  for (let i = 1; i < distinct.length; i += 1) gaps.push(distinct[i] - distinct[i - 1]);
  gaps.sort((a, b) => a - b);
  const mid = Math.floor(gaps.length / 2);
  const med = gaps.length % 2 === 0 ? 0.5 * (gaps[mid - 1] + gaps[mid]) : gaps[mid];
  return 0.25 * med;
}

/**
 * Normalize scalar / symmetric array / (lower, upper) pair error input.
 * @returns {[Float64Array, Float64Array]}
 */
function errorExtent(value, n, center, label) {
  if (value == null) {
    throw new TypeError(`${label} must not be null`);
  }
  if (typeof value === "number") {
    if (!Number.isFinite(value) || value < 0) {
      throw new RangeError(`${label} must be a non-negative finite number`);
    }
    const low = new Float64Array(n);
    const high = new Float64Array(n);
    for (let i = 0; i < n; i += 1) {
      low[i] = center[i] - value;
      high[i] = center[i] + value;
    }
    return [low, high];
  }
  if (Array.isArray(value) && value.length === 2 && (Array.isArray(value[0]) || ArrayBuffer.isView(value[0]))) {
    const lowerAmount = asF64Array(value[0], `${label}[0]`);
    const upperAmount = asF64Array(value[1], `${label}[1]`);
    if (lowerAmount.length !== n || upperAmount.length !== n) {
      throw new RangeError(`${label} pair columns must have length ${n}`);
    }
    const low = new Float64Array(n);
    const high = new Float64Array(n);
    for (let i = 0; i < n; i += 1) {
      if (!Number.isFinite(lowerAmount[i]) || !Number.isFinite(upperAmount[i])) {
        throw new RangeError(`${label} must be finite`);
      }
      if (lowerAmount[i] < 0 || upperAmount[i] < 0) {
        throw new RangeError(`${label} must be non-negative`);
      }
      low[i] = center[i] - lowerAmount[i];
      high[i] = center[i] + upperAmount[i];
    }
    return [low, high];
  }
  const arr = asF64Array(value, label);
  if (arr.length === n) {
    const low = new Float64Array(n);
    const high = new Float64Array(n);
    for (let i = 0; i < n; i += 1) {
      if (!Number.isFinite(arr[i])) {
        throw new RangeError(`${label} must be finite`);
      }
      if (arr[i] < 0) {
        throw new RangeError(`${label} must be non-negative`);
      }
      low[i] = center[i] - arr[i];
      high[i] = center[i] + arr[i];
    }
    return [low, high];
  }
  if (arr.length === 2 * n) {
    // Row-major (n, 2) flattened: [lo0, hi0, lo1, hi1, ...]
    const low = new Float64Array(n);
    const high = new Float64Array(n);
    for (let i = 0; i < n; i += 1) {
      const lo = arr[i * 2];
      const hi = arr[i * 2 + 1];
      if (!Number.isFinite(lo) || !Number.isFinite(hi)) {
        throw new RangeError(`${label} must be finite`);
      }
      if (lo < 0 || hi < 0) {
        throw new RangeError(`${label} must be non-negative`);
      }
      low[i] = center[i] - lo;
      high[i] = center[i] + hi;
    }
    return [low, high];
  }
  throw new RangeError(`${label} must be a scalar, length-${n} array, or a 2×${n} array`);
}

function concat3(a, b, c) {
  const out = new Float64Array(a.length + b.length + c.length);
  out.set(a, 0);
  out.set(b, a.length);
  out.set(c, a.length + b.length);
  return out;
}

function segmentTrace(kind, x0, x1, y0, y1, { name, color, width, opacity, role, count, xAxis, yAxis, id, style }) {
  return {
    kind,
    name: name ?? null,
    x: x0,
    y: y0,
    x0,
    x1,
    y0,
    y1,
    style: {
      color: color ?? DEFAULT_MARK_COLOR,
      width: width ?? 1.2,
      opacity: opacity ?? 1.0,
      role,
      ...(style ?? {}),
    },
    count,
    x_axis: xAxis ?? "x",
    y_axis: yAxis ?? "y",
    ...(id != null ? { id } : {}),
  };
}

/**
 * @param {ArrayLike|TypedArray} x
 * @param {ArrayLike|TypedArray} y
 * @param {{
 *   yerr?: number|ArrayLike|null,
 *   xerr?: number|ArrayLike|null,
 *   capSize?: number|null,
 *   name?: string|null,
 *   color?: string,
 *   width?: number,
 *   opacity?: number,
 *   style?: object,
 * }} [opts]
 */
export function composeErrorbar(x, y, opts = {}) {
  const xa = asF64Array(x, "x");
  const ya = asF64Array(y, "y");
  if (xa.length !== ya.length) {
    throw new RangeError("errorbar x/y length mismatch");
  }
  const n = xa.length;
  if (opts.yerr == null && opts.xerr == null) {
    throw new RangeError("errorbar requires yerr, xerr, or both");
  }
  const capSize = opts.capSize;
  if (capSize != null && (!(Number.isFinite(capSize) && capSize >= 0))) {
    throw new RangeError("errorbar capSize must be a non-negative finite number");
  }
  const traces = [];
  let emitted = false;
  if (opts.yerr != null) {
    const [low, high] = errorExtent(opts.yerr, n, ya, "yerr");
    const cap = capSize == null ? autoCapSize(xa) : Number(capSize);
    let x0;
    let x1;
    let y0;
    let y1;
    if (cap > 0) {
      const left = new Float64Array(n);
      const right = new Float64Array(n);
      for (let i = 0; i < n; i += 1) {
        left[i] = xa[i] - cap;
        right[i] = xa[i] + cap;
      }
      x0 = concat3(xa, left, left);
      x1 = concat3(xa, right, right);
      y0 = concat3(low, low, high);
      y1 = concat3(high, low, high);
    } else {
      x0 = xa;
      x1 = xa;
      y0 = low;
      y1 = high;
    }
    traces.push(
      segmentTrace("errorbar", x0, x1, y0, y1, {
        name: opts.name,
        color: opts.color,
        width: opts.width,
        opacity: opts.opacity,
        role: "y-errorbar",
        count: n,
        xAxis: opts.xAxis,
        yAxis: opts.yAxis,
        id: opts.id,
        style: opts.style,
      }),
    );
    emitted = true;
  }
  if (opts.xerr != null) {
    const [low, high] = errorExtent(opts.xerr, n, xa, "xerr");
    const cap = capSize == null ? autoCapSize(ya) : Number(capSize);
    let x0;
    let x1;
    let y0;
    let y1;
    if (cap > 0) {
      const below = new Float64Array(n);
      const above = new Float64Array(n);
      for (let i = 0; i < n; i += 1) {
        below[i] = ya[i] - cap;
        above[i] = ya[i] + cap;
      }
      x0 = concat3(low, low, high);
      x1 = concat3(high, low, high);
      y0 = concat3(ya, below, below);
      y1 = concat3(ya, above, above);
    } else {
      x0 = low;
      x1 = high;
      y0 = ya;
      y1 = ya;
    }
    traces.push(
      segmentTrace("errorbar", x0, x1, y0, y1, {
        name: emitted ? null : opts.name,
        color: opts.color,
        width: opts.width,
        opacity: opts.opacity,
        role: "x-errorbar",
        count: n,
        xAxis: opts.xAxis,
        yAxis: opts.yAxis,
        id: opts.id != null && !emitted ? opts.id : undefined,
        style: opts.style,
      }),
    );
  }
  return { traces };
}

/**
 * @param {import("../figure.js").Figure} fig
 * @param {ArrayLike|TypedArray} x
 * @param {ArrayLike|TypedArray} y
 * @param {object} [opts]
 */
export function attachErrorbar(fig, x, y, opts = {}) {
  const { traces } = composeErrorbar(x, y, opts);
  for (const t of traces) {
    fig.traces.push({
      id: t.id ?? fig.traces.length,
      ...t,
    });
  }
  return fig;
}
