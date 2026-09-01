/**
 * Minimal CSS / numeric color helpers for Node host composition.
 * Ships constant CSS strings, packed RGBA8 for direct_rgba, or continuous
 * unit-f32 channels for numeric encodings (Python `_ship_channels` parity).
 */
import { pointer, xyCssColorRgba, xyCssIsFunctional, xyContinuousDomain, xyDirectRgbaAdmit, xyClipQuantizeU8, xyQuantizeUnitU8, xyPaletteRowsRgba8, xyLiteralColorRgbaF64 } from "./native.js";
import { DEFAULT_PALETTE } from "./encode.js";
import { factorizeCategories } from "./factorize.js";

function u8Ptr(view) {
  return pointer(view, "uint8_t *");
}

function f64Ptr(view) {
  return pointer(view, "double *");
}

/**
 * Resolve a CSS color to RGBA8 via `xyg_css_color_rgba`. Named colors,
 * `hsl()`, `none`, and the never-invisible fallback match Python Scene/raster.
 *
 * @param {string} css
 * @param {number} [opacity]
 * @returns {Uint8Array}
 */
export function cssColorRgba8(css, opacity = 1) {
  const encoded = new TextEncoder().encode(String(css ?? ""));
  const out = new Uint8Array(4);
  const code = xyCssColorRgba(
    encoded.length ? u8Ptr(encoded) : null,
    BigInt(encoded.length),
    Number(opacity),
    u8Ptr(out),
  );
  if (code !== 0) throw new RangeError("native css color resolver rejected the color");
  return out;
}

/**
 * Parse `#rgb`, `#rgba`, `#rrggbb`, `#rrggbbaa`, or `rgb(a)(...)` into
 * `[r,g,b,a]` in 0..1. Returns null when unrecognized. Named colors, `hsl()`,
 * and `none` go through `cssColorRgba8` / `xyg_css_color_rgba`.
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
    out.set(cssColorRgba8(colors[i]), i * 4);
  }
  return out;
}

/** Unambiguous `#` / `rgb()` / `hsl()` paint syntax (ABI 213). */
export function cssIsFunctional(css) {
  const encoded = new TextEncoder().encode(String(css ?? ""));
  const code = Number(
    xyCssIsFunctional(encoded.length ? u8Ptr(encoded) : 0, BigInt(encoded.length)),
  );
  if (code < 0) throw new RangeError("invalid css-is-functional request");
  return code === 1;
}

/** Continuous color/size domain (ABI 213). */
export function continuousDomain(values) {
  const xv = values instanceof Float64Array ? values : Float64Array.from(values, Number);
  const lo = new Float64Array(1);
  const hi = new Float64Array(1);
  const code = Number(
    xyContinuousDomain(
      xv.length ? f64Ptr(xv) : 0,
      BigInt(xv.length),
      f64Ptr(lo),
      f64Ptr(hi),
    ),
  );
  if (code !== 0) throw new RangeError("invalid continuous-domain request");
  return [lo[0], hi[0]];
}

/** Admit per-point RGB/RGBA in `[0, 1]` as contiguous Nx4 (ABI 213). */
export function directRgbaAdmit(values, components) {
  const xv = values instanceof Float64Array ? values : Float64Array.from(values, Number);
  const nComp = Number(components);
  if (nComp !== 3 && nComp !== 4) {
    throw new RangeError("direct RGB/RGBA colors must be 3 or 4 components");
  }
  if (xv.length % nComp !== 0) {
    throw new RangeError("direct RGB/RGBA colors must be a multiple of the component count");
  }
  const n = xv.length / nComp;
  const probed = xyDirectRgbaAdmit(n ? f64Ptr(xv) : 0, BigInt(n), BigInt(nComp), 0, 0);
  const USIZE_MAX_64 = (1n << 64n) - 1n;
  if (probed === USIZE_MAX_64) {
    throw new RangeError("direct RGB/RGBA colors must contain finite values between 0 and 1");
  }
  const count = Number(probed);
  if (count === 0) return new Float64Array(0);
  const out = new Float64Array(count);
  const written = xyDirectRgbaAdmit(
    n ? f64Ptr(xv) : 0,
    BigInt(n),
    BigInt(nComp),
    f64Ptr(out),
    count,
  );
  if (written === USIZE_MAX_64 || Number(written) !== count) {
    throw new RangeError("direct RGB/RGBA colors must contain finite values between 0 and 1");
  }
  return out;
}

/** Clip unit f64 to `[0, 1]`, scale by 255, and quantize to u8 (ABI 251). */
export function clipQuantizeU8(values) {
  const xv = values instanceof Float64Array ? values : Float64Array.from(values ?? [], Number);
  const out = new Uint8Array(xv.length);
  const code = Number(
    xyClipQuantizeU8(
      xv.length ? f64Ptr(xv) : 0,
      BigInt(xv.length),
      out.length ? u8Ptr(out) : 0,
      BigInt(out.length),
    ),
  );
  if (code === -2) throw new RangeError("invalid clip-quantize-u8 request");
  if (code !== 1) return null;
  return out;
}

/** Normalize over `[lo, hi]` then ABI 341 clip-quantize (Python `quantize_unit_u8`). */
export function quantizeUnitU8(values, lo, hi) {
  const n = values == null ? 0 : values.length;
  const out = new Uint8Array(n);
  if (n === 0) {
    return out;
  }
  const src = values instanceof Float64Array ? values : Float64Array.from(values);
  const code = xyQuantizeUnitU8(f64Ptr(src), BigInt(n), lo, hi, u8Ptr(out));
  if (code === -2) throw new RangeError("invalid quantize-unit-u8 request");
  if (code !== 1) throw new RangeError("invalid quantize-unit-u8 request");
  return out;
}

function packUtf8Strings(texts) {
  const encoded = texts.map((text) => new TextEncoder().encode(String(text)));
  const lens = Uint32Array.from(encoded.map((item) => item.length));
  const total = lens.reduce((sum, len) => sum + len, 0);
  const packed = new Uint8Array(total);
  let at = 0;
  for (const item of encoded) {
    packed.set(item, at);
    at += item.length;
  }
  return { lens, packed };
}

function u32Ptr(view) {
  return pointer(view, "uint32_t *");
}

/** Indexed palette rows as straight-alpha RGBA8 (ABI 342). */
export function paletteRowsRgba8(palette, rows) {
  const src = palette?.length ? palette.map((entry) => String(entry)) : [];
  if (!src.length) {
    throw new RangeError("paletteRowsRgba8 requires at least one entry");
  }
  const n = Math.max(1, Math.floor(Number(rows)));
  const { lens, packed } = packUtf8Strings(src);
  const out = new Uint8Array(n * 4);
  const unresolved = new Uint32Array(1);
  const USIZE_MAX_64 = (1n << 64n) - 1n;
  const written = xyPaletteRowsRgba8(
    lens.length ? u32Ptr(lens) : 0,
    packed.length ? u8Ptr(packed) : 0,
    BigInt(packed.length),
    BigInt(src.length),
    BigInt(n),
    u8Ptr(out),
    BigInt(out.length),
    u32Ptr(unresolved),
  );
  if (written === USIZE_MAX_64) {
    throw new RangeError("invalid palette-rows-rgba8 request");
  }
  return out;
}

/** Functional CSS color column to canonical f64 RGBA rows (ABI 344). */
export function literalColorRgbaF64(colors) {
  const src = colors?.length ? colors.map((entry) => String(entry)) : [];
  if (!src.length) {
    return null;
  }
  const { lens, packed } = packUtf8Strings(src);
  const out = new Float64Array(src.length * 4);
  const USIZE_MAX_64 = (1n << 64n) - 1n;
  const written = xyLiteralColorRgbaF64(
    lens.length ? u32Ptr(lens) : 0,
    packed.length ? u8Ptr(packed) : 0,
    BigInt(packed.length),
    BigInt(src.length),
    f64Ptr(out),
    BigInt(out.length),
  );
  if (written === USIZE_MAX_64) {
    return null;
  }
  return out;
}

function flattenRgbRows(raw, n) {
  if (raw.length !== n) return null;
  const first = raw[0];
  if (!Array.isArray(first) && !ArrayBuffer.isView(first)) return null;
  const components = first.length;
  if (components !== 3 && components !== 4) return null;
  const flat = new Float64Array(n * components);
  for (let i = 0; i < n; i += 1) {
    const row = raw[i];
    if (row == null || row.length !== components) return null;
    for (let c = 0; c < components; c += 1) flat[i * components + c] = Number(row[c]);
  }
  return { flat, components };
}

/**
 * Resolve a color encoding to a wire color channel for the Node figure MVP.
 *
 * @param {string|string[]|number[]|TypedArray|null|undefined} color
 * @param {number} n
 * @param {string} [fallback]
 * @returns {{mode: string, constant?: string, rgba?: Uint8Array, values?: Float64Array, domain?: number[], colormap?: string, codes?: Uint8Array|Uint32Array, categories?: string[], palette?: string[]}|null}
 */
export function resolveColorChannel(color, n, fallback = "#3987e5") {
  if (color == null) {
    return { mode: "constant", constant: fallback };
  }
  if (typeof color === "string") {
    return { mode: "constant", constant: color };
  }
  if (typeof color === "number") {
    if (!Number.isFinite(color)) {
      throw new RangeError("color scalar must be finite");
    }
    const values = Float64Array.from({ length: n }, () => color);
    return {
      mode: "continuous",
      values,
      domain: continuousDomain(new Float64Array([color])),
      colormap: "viridis",
    };
  }
  if (Array.isArray(color) || ArrayBuffer.isView(color)) {
    const raw = Array.isArray(color) ? color : [...color];
    const rgb = flattenRgbRows(raw, n);
    if (rgb) {
      const packed = directRgbaAdmit(rgb.flat, rgb.components);
      return { mode: "direct_rgba", rgba: clipQuantizeU8(packed) };
    }
    if (raw.length !== n) {
      throw new RangeError(`color length ${raw.length} != n=${n}`);
    }
    const numeric = raw.every((v) => typeof v !== "string" && Number.isFinite(Number(v)));
    if (numeric) {
      const values = Float64Array.from(raw, Number);
      return {
        mode: "continuous",
        values,
        domain: continuousDomain(values),
        colormap: "viridis",
      };
    }
    if (raw.every((v) => typeof v === "string" && cssIsFunctional(v))) {
      const packed = literalColorRgbaF64(raw);
      if (packed) {
        return { mode: "direct_rgba", rgba: clipQuantizeU8(packed) };
      }
    }
    return factorizeCategories(raw);
  }
  return { mode: "constant", constant: String(color) };
}
