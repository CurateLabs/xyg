/**
 * Contour isolines — marching-squares segments matching Python `marks.contour`.
 */

import { asF64Array, contourLevels, DEFAULT_MARK_COLOR, marchingSquares } from "../encode.js";

const MAX_CONTOUR_WORK = 4_000_000;

/**
 * Coerce a row-major 2-D grid from nested arrays or a flat Float64Array.
 * @returns {{z: Float64Array, rows: number, cols: number}}
 */
function coerceGrid(z, opts) {
  if (Array.isArray(z) && Array.isArray(z[0])) {
    const rows = z.length;
    const cols = z[0].length;
    const flat = new Float64Array(rows * cols);
    let k = 0;
    for (let r = 0; r < rows; r += 1) {
      if (z[r].length !== cols) {
        throw new RangeError("contour z rows must have equal length");
      }
      for (let c = 0; c < cols; c += 1) {
        flat[k] = Number(z[r][c]);
        k += 1;
      }
    }
    return { z: flat, rows, cols };
  }
  const flat = asF64Array(z, "z");
  let rows = opts.rows;
  let cols = opts.cols;
  if ((rows == null || cols == null) && opts.x != null && opts.y != null) {
    cols = asF64Array(opts.x, "x").length;
    rows = asF64Array(opts.y, "y").length;
  }
  if (rows == null || cols == null) {
    throw new RangeError("contour rows/cols required for flat z input");
  }
  if (flat.length !== rows * cols) {
    throw new RangeError("contour z length must equal rows * cols");
  }
  return { z: flat, rows, cols };
}

function axisPositions(values, n, label) {
  if (values == null) {
    const out = new Float64Array(n);
    for (let i = 0; i < n; i += 1) out[i] = i;
    return out;
  }
  const pos = asF64Array(values, label);
  if (pos.length !== n) {
    throw new RangeError(`contour ${label} must have length ${n}, got ${pos.length}`);
  }
  return pos;
}

function resolveLevels(levels, finiteZ) {
  if (typeof levels === "number" && Number.isFinite(levels)) {
    const nLevels = Math.trunc(levels);
    if (nLevels <= 0 || nLevels > 256) {
      throw new RangeError("contour levels must be between 1 and 256");
    }
    return Float64Array.from(contourLevels(finiteZ, nLevels));
  }
  const arr = asF64Array(levels, "levels");
  try {
    return Float64Array.from(contourLevels(arr, 0));
  } catch {
    throw new RangeError("contour levels must contain 1 to 256 finite values");
  }
}

/**
 * @param {Float64Array|number[][]} z
 * @param {{
 *   levels?: number|ArrayLike,
 *   x?: ArrayLike|null,
 *   y?: ArrayLike|null,
 *   rows?: number,
 *   cols?: number,
 *   name?: string|null,
 *   color?: string,
 *   width?: number,
 *   opacity?: number,
 *   cornerMask?: boolean,
 *   style?: object,
 * }} [opts]
 */
export function composeContour(z, opts = {}) {
  const { z: flat, rows, cols } = coerceGrid(z, opts);
  if (rows < 2 || cols < 2) {
    throw new RangeError(
      `contour z must be a 2-D matrix with at least 2 rows/columns, got (${rows}, ${cols})`,
    );
  }
  const finite = [];
  for (let i = 0; i < flat.length; i += 1) {
    if (Number.isFinite(flat[i])) finite.push(flat[i]);
  }
  if (finite.length === 0) {
    throw new RangeError("contour z must contain at least one finite value");
  }
  const xpos = axisPositions(opts.x, cols, "x");
  const ypos = axisPositions(opts.y, rows, "y");
  const levelValues = resolveLevels(opts.levels ?? 10, Float64Array.from(finite));
  const work = (rows - 1) * (cols - 1) * levelValues.length;
  if (work > MAX_CONTOUR_WORK) {
    throw new RangeError(
      `contour grid x levels exceeds the bounded work budget (${MAX_CONTOUR_WORK.toLocaleString()})`,
    );
  }
  const cornerMask = Boolean(opts.cornerMask ?? false);
  const segs = marchingSquares(flat, rows, cols, xpos, ypos, levelValues, { cornerMask });
  if (segs.x0.length === 0) {
    throw new RangeError("contour levels do not intersect the finite grid");
  }
  const style = {
    color: opts.color ?? DEFAULT_MARK_COLOR,
    width: opts.width ?? 1.1,
    opacity: opts.opacity ?? 0.9,
    role: "contour",
    ...(opts.style ?? {}),
  };
  return {
    traces: [
      {
        kind: "contour",
        name: opts.name ?? null,
        x: segs.x0,
        y: segs.y0,
        x0: segs.x0,
        x1: segs.x1,
        y0: segs.y0,
        y1: segs.y1,
        levels: segs.levels,
        style,
        count: segs.x0.length,
        x_axis: opts.xAxis ?? "x",
        y_axis: opts.yAxis ?? "y",
        ...(opts.id != null ? { id: opts.id } : {}),
      },
    ],
    levelValues,
  };
}

/**
 * @param {import("../figure.js").Figure} fig
 * @param {Float64Array|number[][]} z
 * @param {object} [opts]
 */
export function attachContour(fig, z, opts = {}) {
  const { traces } = composeContour(z, opts);
  for (const t of traces) {
    fig.traces.push({
      id: t.id ?? fig.traces.length,
      ...t,
    });
  }
  return fig;
}
