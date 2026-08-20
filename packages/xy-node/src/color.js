/**
 * Minimal CSS / numeric color helpers for Node host composition.
 * Ships constant CSS strings, packed RGBA8 for direct_rgba, or continuous
 * unit-f32 channels for numeric encodings (Python `_ship_channels` parity).
 */

/**
 * Parse `#rgb`, `#rgba`, `#rrggbb`, `#rrggbbaa`, or `rgb(a)(...)` into
 * `[r,g,b,a]` in 0..1. Returns null when unrecognized.
 *
 * @param {string} css
 * @returns {[number, number, number, number]|null}
 */
export function parseCssColor(css) {
  if (css == null) return null;
  const s = String(css).trim();
  if (s.startsWith("#")) {
    const hex = s.slice(1);
    let r;
    let g;
    let b;
    let a = 255;
    if (hex.length === 3 || hex.length === 4) {
      r = parseInt(hex[0] + hex[0], 16);
      g = parseInt(hex[1] + hex[1], 16);
      b = parseInt(hex[2] + hex[2], 16);
      if (hex.length === 4) a = parseInt(hex[3] + hex[3], 16);
    } else if (hex.length === 6 || hex.length === 8) {
      r = parseInt(hex.slice(0, 2), 16);
      g = parseInt(hex.slice(2, 4), 16);
      b = parseInt(hex.slice(4, 6), 16);
      if (hex.length === 8) a = parseInt(hex.slice(6, 8), 16);
    } else {
      return null;
    }
    if (![r, g, b, a].every((v) => Number.isFinite(v))) return null;
    return [r / 255, g / 255, b / 255, a / 255];
  }
  const m = /^rgba?\(\s*([0-9.]+)\s*,\s*([0-9.]+)\s*,\s*([0-9.]+)(?:\s*,\s*([0-9.]+))?\s*\)$/i.exec(
    s,
  );
  if (m) {
    const r = Number(m[1]);
    const g = Number(m[2]);
    const b = Number(m[3]);
    const a = m[4] == null ? 1 : Number(m[4]);
    if (![r, g, b, a].every((v) => Number.isFinite(v))) return null;
    return [
      Math.min(255, Math.max(0, r)) / 255,
      Math.min(255, Math.max(0, g)) / 255,
      Math.min(255, Math.max(0, b)) / 255,
      Math.min(1, Math.max(0, a)),
    ];
  }
  return null;
}

/**
 * Pack CSS colors into a contiguous RGBA8 buffer (one pixel per color).
 *
 * @param {string[]} colors
 * @returns {Uint8Array}
 */
export function cssColorsToRgba8(colors) {
  const out = new Uint8Array(colors.length * 4);
  for (let i = 0; i < colors.length; i += 1) {
    const rgba = parseCssColor(colors[i]) ?? [0.22, 0.53, 0.9, 1];
    const o = i * 4;
    out[o] = Math.round(rgba[0] * 255);
    out[o + 1] = Math.round(rgba[1] * 255);
    out[o + 2] = Math.round(rgba[2] * 255);
    out[o + 3] = Math.round(rgba[3] * 255);
  }
  return out;
}

function looksLikeCssColor(value) {
  if (typeof value !== "string") return false;
  const s = value.trim();
  return s.startsWith("#") || /^rgba?\(/i.test(s) || /^[a-zA-Z][a-zA-Z0-9-]*$/.test(s);
}

/**
 * Resolve a color encoding to a wire color channel for the Node figure MVP.
 *
 * @param {string|string[]|number[]|TypedArray|null|undefined} color
 * @param {number} n
 * @param {string} [fallback]
 * @returns {{mode: string, color?: string, rgba?: Uint8Array, values?: Float64Array, domain?: number[], colormap?: string}|null}
 */
export function resolveColorChannel(color, n, fallback = "#3987e5") {
  if (color == null) {
    return { mode: "constant", color: fallback };
  }
  if (typeof color === "string") {
    return { mode: "constant", color };
  }
  if (typeof color === "number") {
    if (!Number.isFinite(color)) {
      throw new RangeError("color scalar must be finite");
    }
    return {
      mode: "continuous",
      values: Float64Array.from({ length: n }, () => color),
      domain: [color, color === 0 ? 1 : color * 1.000001 || 1],
      colormap: "viridis",
    };
  }
  if (Array.isArray(color) || ArrayBuffer.isView(color)) {
    const raw = [...color];
    if (raw.length === 1) {
      const only = raw[0];
      if (looksLikeCssColor(only) || typeof only === "string") {
        return { mode: "constant", color: String(only) };
      }
    }
    if (raw.length !== n) {
      throw new RangeError(`color length ${raw.length} != n=${n}`);
    }
    const numeric = raw.every((v) => !looksLikeCssColor(v) && Number.isFinite(Number(v)));
    if (numeric) {
      const values = Float64Array.from(raw, Number);
      let lo = Number.POSITIVE_INFINITY;
      let hi = Number.NEGATIVE_INFINITY;
      for (const v of values) {
        if (v < lo) lo = v;
        if (v > hi) hi = v;
      }
      if (!Number.isFinite(lo) || !Number.isFinite(hi)) {
        lo = 0;
        hi = 1;
      }
      if (lo === hi) hi = lo + 1;
      return { mode: "continuous", values, domain: [lo, hi], colormap: "viridis" };
    }
    return { mode: "direct_rgba", rgba: cssColorsToRgba8(raw.map(String)) };
  }
  return { mode: "constant", color: String(color) };
}
