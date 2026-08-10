/**
 * Shared multi-group helpers for box / violin (Python `_distribution_groups`).
 */

import { asF64Array } from "../encode.js";

/**
 * Split values into groups + category/position centers.
 *
 * Accepts:
 * - 1-D values (+ optional `group` / `x` per-row labels)
 * - sequence-of-datasets (array of arrays) — one group per item
 * - column-oriented 2-D TypedArray via `{columns: true, rows, cols}` is not
 *   required; pass an array of column arrays instead.
 *
 * @param {ArrayLike|TypedArray|ArrayLike[]} values
 * @param {{
 *   x?: ArrayLike|number|null,
 *   group?: ArrayLike|null,
 *   kind?: string,
 * }} [opts]
 * @returns {{groups: Float64Array[], positions: Float64Array}}
 */
export function distributionGroups(values, opts = {}) {
  const kind = opts.kind ?? "distribution";
  if (opts.x != null && opts.group != null) {
    throw new Error(`${kind} accepts either x or group, not both`);
  }

  // Sequence-of-datasets (ragged lengths allowed).
  if (
    Array.isArray(values) &&
    values.length > 0 &&
    values.every((v) => v != null && typeof v !== "string" && (Array.isArray(v) || ArrayBuffer.isView(v)))
  ) {
    if (opts.group != null) {
      throw new Error(`${kind} group is only valid with 1-D values`);
    }
    const groups = values.map((v, i) => asF64Array(v, `${kind} values[${i}]`));
    if (opts.x == null) {
      return { groups, positions: Float64Array.from(groups, (_, i) => i) };
    }
    if (typeof opts.x === "number" || (typeof opts.x !== "object" && opts.x != null && !Array.isArray(opts.x) && !ArrayBuffer.isView(opts.x))) {
      throw new RangeError(`${kind} x must be 1-D with one label per group`);
    }
    const positions = categoryPositions(opts.x);
    if (positions.length !== groups.length) {
      throw new RangeError(`${kind} x must have one label per group`);
    }
    return { groups, positions };
  }

  const vals = asF64Array(values, `${kind} values`);
  const key = opts.group ?? opts.x;
  const keyName = opts.group != null ? "group" : "x";
  if (key == null) {
    return { groups: [vals], positions: Float64Array.of(0) };
  }
  const positions = categoryPositions(key);
  if (positions.length !== vals.length) {
    throw new RangeError(`${kind} ${keyName} must have length ${vals.length}`);
  }
  return splitByPositions(vals, positions);
}

/**
 * Map labels / numeric keys to dense category positions (first-seen order).
 *
 * @param {ArrayLike} key
 * @returns {Float64Array}
 */
export function categoryPositions(key) {
  const items = [...key];
  const index = new Map();
  const out = new Float64Array(items.length);
  let next = 0;
  for (let i = 0; i < items.length; i += 1) {
    const k = items[i];
    if (!index.has(k)) {
      index.set(k, next);
      next += 1;
    }
    out[i] = index.get(k);
  }
  return out;
}

/**
 * @param {Float64Array} vals
 * @param {Float64Array} positions
 */
export function splitByPositions(vals, positions) {
  const order = new Map();
  for (const p of positions) {
    if (!order.has(p)) order.set(p, []);
  }
  for (let i = 0; i < vals.length; i += 1) {
    order.get(positions[i]).push(vals[i]);
  }
  const groups = [];
  const centers = [];
  for (const [pos, items] of order) {
    groups.push(Float64Array.from(items));
    centers.push(pos);
  }
  return { groups, positions: Float64Array.from(centers) };
}
