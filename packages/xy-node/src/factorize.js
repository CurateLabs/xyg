/**
 * Categorical label factorization for Node host color channels.
 *
 * Mirrors `python/xyg/channels._factorize_categories`: fixed-width and
 * one-codepoint Unicode columns factorize in Rust; JS arrays fall back to the
 * label-policy path that sorts display labels deterministically.
 */
import { DEFAULT_PALETTE } from "./encode.js";
import {
  pointer,
  xyFactorizeFixed,
  xyFactorizeFixedU8Counts,
  xyFactorizeUnicode1U8Counts,
  xyRemapU8,
} from "./native.js";

export const MAX_CATEGORIES = 256;
const FACTORIZE_PROBE_ROWS = 4096;
const FACTORIZE_NATIVE_MAX_PROBE_CATEGORIES = 512;
const FACTORIZE_NEAR_UNIQUE_RATIO = 0.95;
const FACTORIZE_NARROW_ITEMSIZE = 32;
const USIZE_MAX_64 = (1n << 64n) - 1n;
const FACTORIZE_CAPACITY_EXCEEDED = USIZE_MAX_64 - 1n;

function u8Ptr(view) {
  return pointer(view, "uint8_t *");
}

function u32Ptr(view) {
  return pointer(view, "uint32_t *");
}

function u64Ptr(view) {
  return pointer(view, "uint64_t *");
}

function isMissingCategory(value) {
  return value == null || (typeof value === "number" && Number.isNaN(value));
}

/** Canonical display label — lockstep with Python `category_label`. */
export function categoryLabel(value) {
  if (isMissingCategory(value)) return "(missing)";
  if (typeof value === "string") return value;
  if (value instanceof Uint8Array) {
    return new TextDecoder("utf-8", { fatal: false }).decode(value);
  }
  if (ArrayBuffer.isView(value)) {
    const bytes = new Uint8Array(value.buffer, value.byteOffset, value.byteLength);
    return new TextDecoder("utf-8", { fatal: false }).decode(bytes);
  }
  return String(value);
}

function recordCount(data, width) {
  if (data instanceof Uint8Array && width > 1 && data.length % width === 0) {
    return data.length / width;
  }
  return data.length;
}

function recordKey(data, index, width) {
  const byteOffset = index * width;
  if (data instanceof Uint8Array && width > 1) {
    const slice = new Uint8Array(data.buffer, data.byteOffset + byteOffset, width);
    let key = "";
    for (let i = 0; i < slice.length; i += 1) key += `\0${slice[i]}`;
    return key;
  }
  if (width === 1) return data[index];
  const slice = new Uint8Array(data.buffer, data.byteOffset + byteOffset, width);
  let key = "";
  for (let i = 0; i < slice.length; i += 1) key += `\0${slice[i]}`;
  return key;
}

function decodeRecord(view, index, width) {
  if (width === 1) return view[index];
  const byteOffset = index * width;
  return new Uint8Array(view.buffer, view.byteOffset + byteOffset, width);
}

function distinctProbeCount(data, width) {
  const n = recordCount(data, width);
  const probeLen = Math.min(n, FACTORIZE_PROBE_ROWS);
  const seen = new Set();
  for (let i = 0; i < probeLen; i += 1) {
    const idx =
      n <= FACTORIZE_PROBE_ROWS ? i : Math.floor((i * (n - 1)) / (probeLen - 1));
    seen.add(recordKey(data, idx, width));
  }
  return seen.size;
}

function useNativeFixedFactorizer(data, width) {
  const n = recordCount(data, width);
  const distinct = distinctProbeCount(data, width);
  if (distinct <= FACTORIZE_NATIVE_MAX_PROBE_CATEGORIES) return true;
  const nearUnique =
    width <= FACTORIZE_NARROW_ITEMSIZE ? 1.0 : FACTORIZE_NEAR_UNIQUE_RATIO;
  return distinct < nearUnique * Math.min(n, FACTORIZE_PROBE_ROWS);
}

function sortedCategoryRemap(uniqueLabels) {
  const categories = [...new Set(uniqueLabels)].sort();
  const index = new Map(categories.map((label, i) => [label, i]));
  const remap = uniqueLabels.map((label) => index.get(label));
  return { categories, remap };
}

function remapIsIdentity(remap) {
  for (let i = 0; i < remap.length; i += 1) {
    if (remap[i] !== i) return false;
  }
  return true;
}

function aggregateCounts(uniqueLabels, rawCounts, categories) {
  const index = new Map(categories.map((label, i) => [label, i]));
  const counts = new BigUint64Array(categories.length);
  for (let i = 0; i < uniqueLabels.length; i += 1) {
    counts[index.get(uniqueLabels[i])] += BigInt(rawCounts[i]);
  }
  return counts;
}

function finalizeCompactFactorization(
  view,
  width,
  rawCodes,
  uniqueIndices,
  rawCounts,
  labelAt,
) {
  const uniqueLabels = [];
  for (let i = 0; i < uniqueIndices.length; i += 1) {
    const idx = uniqueIndices[i];
    uniqueLabels.push(
      labelAt != null ? labelAt(idx) : categoryLabel(decodeRecord(view, idx, width)),
    );
  }
  const { categories, remap } = sortedCategoryRemap(uniqueLabels);
  if (!remapIsIdentity(remap)) {
    const mapping = Uint8Array.from(remap);
    const ok = Number(
      xyRemapU8(u8Ptr(rawCodes), BigInt(rawCodes.length), u8Ptr(mapping), BigInt(mapping.length)),
    );
    if (ok !== 1) throw new RangeError("native remap_u8 rejected categorical remap");
  }
  const counts = aggregateCounts(uniqueLabels, rawCounts, categories);
  return {
    mode: "categorical",
    codes: rawCodes,
    categories,
    counts,
    palette: [...DEFAULT_PALETTE],
  };
}

function bytesView(view) {
  return new Uint8Array(view.buffer, view.byteOffset, view.byteLength);
}

function factorizeFixedRecords(data, width, labelAt) {
  const n = recordCount(data, width);
  if (n === 0) {
    return {
      mode: "categorical",
      codes: new Uint8Array(0),
      categories: [],
      counts: new BigUint64Array(0),
      palette: [...DEFAULT_PALETTE],
    };
  }
  const codes = new Uint8Array(n);
  const capacity = Math.min(n, MAX_CATEGORIES);
  const uniqueIndices = new Uint32Array(capacity);
  const countsBuf = new BigUint64Array(capacity);
  const bytes =
    data instanceof Uint8Array && width > 1 ? data : bytesView(data);
  const written = xyFactorizeFixedU8Counts(
    u8Ptr(bytes),
    BigInt(n),
    BigInt(width),
    u8Ptr(codes),
    u32Ptr(uniqueIndices),
    u64Ptr(countsBuf),
    BigInt(capacity),
  );
  if (written === FACTORIZE_CAPACITY_EXCEEDED) return null;
  if (written === USIZE_MAX_64 || written > BigInt(capacity)) {
    throw new RangeError("native factorize_fixed_u8_counts rejected the record array");
  }
  const uniq = Number(written);
  return finalizeCompactFactorization(
    data,
    width,
    codes,
    uniqueIndices.subarray(0, uniq),
    countsBuf.subarray(0, uniq),
    labelAt,
  );
}

function factorizeUnicode1Records(view, labelAt) {
  const n = view.length;
  if (n === 0) {
    return {
      mode: "categorical",
      codes: new Uint8Array(0),
      categories: [],
      counts: new BigUint64Array(0),
      palette: [...DEFAULT_PALETTE],
    };
  }
  const codes = new Uint8Array(n);
  const capacity = Math.min(n, MAX_CATEGORIES);
  const uniqueIndices = new Uint32Array(capacity);
  const countsBuf = new BigUint64Array(capacity);
  const written = xyFactorizeUnicode1U8Counts(
    u32Ptr(view),
    BigInt(n),
    0,
    u8Ptr(codes),
    u32Ptr(uniqueIndices),
    u64Ptr(countsBuf),
    BigInt(capacity),
  );
  if (written === FACTORIZE_CAPACITY_EXCEEDED) return null;
  if (written === USIZE_MAX_64 || written > BigInt(capacity)) {
    throw new RangeError("native factorize_unicode1_u8_counts rejected the array");
  }
  const uniq = Number(written);
  return finalizeCompactFactorization(
    view,
    4,
    codes,
    uniqueIndices.subarray(0, uniq),
    countsBuf.subarray(0, uniq),
    labelAt,
  );
}

function factorizeFixedWide(data, width, labelAt) {
  const n = recordCount(data, width);
  const codes = new Uint32Array(n);
  const uniqueIndices = new Uint32Array(n);
  const bytes =
    data instanceof Uint8Array && width > 1 ? data : bytesView(data);
  const written = xyFactorizeFixed(
    u8Ptr(bytes),
    BigInt(n),
    BigInt(width),
    u32Ptr(codes),
    u32Ptr(uniqueIndices),
  );
  if (written === USIZE_MAX_64 || written > BigInt(n)) {
    throw new RangeError("native factorize_fixed rejected the record array");
  }
  const uniq = Number(written);
  const uniqueLabels = [];
  for (let i = 0; i < uniq; i += 1) {
    const idx = uniqueIndices[i];
    uniqueLabels.push(
      labelAt != null ? labelAt(idx) : categoryLabel(decodeRecord(data, idx, width)),
    );
  }
  const { categories, remap } = sortedCategoryRemap(uniqueLabels);
  const outCodes =
    categories.length <= MAX_CATEGORIES ? new Uint8Array(n) : new Uint32Array(n);
  for (let i = 0; i < n; i += 1) {
    outCodes[i] = remap[codes[i]];
  }
  return {
    mode: "categorical",
    codes: outCodes,
    categories,
    counts: null,
    palette: [...DEFAULT_PALETTE],
  };
}

function factorizeTypedArray(view) {
  if (view instanceof Uint32Array) {
    if (!useNativeFixedFactorizer(view, 4)) return null;
    return factorizeUnicode1Records(view) ?? factorizeFixedWide(view, 4);
  }
  const width = view.BYTES_PER_ELEMENT;
  if (width <= 0) return null;
  if (!useNativeFixedFactorizer(view, width)) return null;
  return factorizeFixedRecords(view, width) ?? factorizeFixedWide(view, width);
}
export function objectColumnIsStringlike(raw) {
  if (!Array.isArray(raw)) return false;
  for (const value of raw) {
    if (isMissingCategory(value)) continue;
    if (typeof value === "string") continue;
    if (value instanceof Uint8Array) continue;
    if (ArrayBuffer.isView(value)) continue;
    return false;
  }
  return true;
}

function packUnicodeLabels(labels) {
  const n = labels.length;
  if (n === 0) {
    return { n: 0, width: 4, view: new Uint32Array(0), u1: true, labels };
  }
  const codePoints = labels.map((label) => [...label].map((ch) => ch.codePointAt(0)));
  const maxLen = Math.max(...codePoints.map((cps) => cps.length));
  if (maxLen === 1) {
    const view = new Uint32Array(n);
    for (let i = 0; i < n; i += 1) view[i] = codePoints[i][0] ?? 0;
    return { n, width: 4, view, u1: true, labels };
  }
  const width = maxLen * 4;
  const data = new Uint8Array(n * width);
  const u32 = new Uint32Array(data.buffer);
  for (let i = 0; i < n; i += 1) {
    const cps = codePoints[i];
    for (let j = 0; j < maxLen; j += 1) {
      u32[i * maxLen + j] = j < cps.length ? cps[j] : 0;
    }
  }
  return { n, width, data, u1: false, labels };
}

function factorizeStringlikeJsArray(raw) {
  const labels = raw.map(categoryLabel);
  const packed = packUnicodeLabels(labels);
  const labelAt = (idx) => labels[idx];
  if (packed.n === 0) return factorizeJsArray([]);
  if (packed.u1) {
    if (!useNativeFixedFactorizer(packed.view, 4)) return factorizeJsArray(labels);
    const native =
      factorizeUnicode1Records(packed.view, labelAt)
      ?? factorizeFixedWide(packed.view, 4, labelAt);
    if (native != null) return native;
    return factorizeJsArray(labels);
  }
  if (!useNativeFixedFactorizer(packed.data, packed.width)) return factorizeJsArray(labels);
  const native =
    factorizeFixedRecords(packed.data, packed.width, labelAt)
    ?? factorizeFixedWide(packed.data, packed.width, labelAt);
  if (native != null) return native;
  return factorizeJsArray(labels);
}

function factorizeJsArray(raw) {
  const labels = raw.map(categoryLabel);
  const categories = [...new Set(labels)].sort();
  const index = new Map(categories.map((label, i) => [label, i]));
  const codes =
    categories.length <= MAX_CATEGORIES
      ? new Uint8Array(labels.length)
      : new Uint32Array(labels.length);
  for (let i = 0; i < labels.length; i += 1) {
    codes[i] = index.get(labels[i]);
  }
  return {
    mode: "categorical",
    codes,
    categories,
    counts: null,
    palette: [...DEFAULT_PALETTE],
  };
}

function materializeTypedLabels(view) {
  const width = view.BYTES_PER_ELEMENT;
  const labels = [];
  for (let i = 0; i < view.length; i += 1) {
    labels.push(categoryLabel(decodeRecord(view, i, width)));
  }
  return factorizeJsArray(labels);
}

/**
 * Factorize categorical labels for color channels.
 *
 * @param {Array|TypedArray} raw
 * @returns {{mode: "categorical", codes: Uint8Array|Uint32Array, categories: string[], counts: BigUint64Array|null, palette: string[]}}
 */
export function factorizeCategories(raw) {
  if (ArrayBuffer.isView(raw) && !(raw instanceof Float32Array) && !(raw instanceof Float64Array)) {
    const native = factorizeTypedArray(raw);
    if (native != null) return native;
    return materializeTypedLabels(raw);
  }
  const rows = Array.isArray(raw) ? raw : [...raw];
  if (objectColumnIsStringlike(rows)) {
    return factorizeStringlikeJsArray(rows);
  }
  return factorizeJsArray(rows);
}
