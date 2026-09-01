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
  xyCategoryLabelsPacked,
  xyFactorizeDisplayLabels,
  xyLabelCodesFirstSeen,
  xySortedDisplayLabelRemap,
  xyFactorizeUseNativeFixed,
  xyObjectRowsAllStringlike,
  xyObjectRowsAllRealNumeric,
  xyObjectRowStringlikeTagFromProbe,
  xyObjectRowRealNumericTagFromProbe,
  xyCategoryLabelKindFromProbe,
  xyFactorizeFixed,
  xyFactorizeFixedU8Counts,
  xyFactorizeUnicode1U8Counts,
  xyRemapU8,
} from "./native.js";

export const MAX_CATEGORIES = 256;
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

function categoryLabelKindAndBytes(value) {
  const probe = valueProbe(value);
  const kind = categoryLabelKindFromProbe(probe);
  if (kind === 0) return { kind: 0, payload: new Uint8Array() };
  if (probe === 3) {
    if (value instanceof Uint8Array) return { kind, payload: value };
    if (ArrayBuffer.isView(value)) {
      return {
        kind,
        payload: new Uint8Array(value.buffer, value.byteOffset, value.byteLength),
      };
    }
  }
  if (probe === 2 && typeof value === "string") {
    return { kind, payload: new TextEncoder().encode(value) };
  }
  return { kind, payload: new TextEncoder().encode(String(value)) };
}

function categoryLabelsFromEncodings(encodings) {
  const n = encodings.length;
  if (n === 0) return [];
  const kinds = new Uint8Array(n);
  const inLens = new Uint32Array(n);
  let textLen = 0;
  for (let i = 0; i < n; i += 1) {
    kinds[i] = encodings[i].kind;
    inLens[i] = encodings[i].payload.length;
    textLen += encodings[i].payload.length;
  }
  const inTexts = new Uint8Array(textLen);
  let offset = 0;
  for (const { payload } of encodings) {
    inTexts.set(payload, offset);
    offset += payload.length;
  }
  const outLens = new Uint32Array(n);
  const outTextsCap = Math.max(256, textLen * 2 + n * 16);
  const outTexts = new Uint8Array(outTextsCap);
  const written = Number(
    xyCategoryLabelsPacked(
      pointer(kinds, "uint8_t *"),
      pointer(inLens, "uint32_t *"),
      pointer(inTexts, "uint8_t *"),
      BigInt(inTexts.length),
      BigInt(n),
      pointer(outLens, "uint32_t *"),
      pointer(outTexts, "uint8_t *"),
      BigInt(outTextsCap),
    ),
  );
  if (written === Number(FACTORIZE_CAPACITY_EXCEEDED)) {
    throw new Error("native category_labels rejected the packed encodings");
  }
  if (written !== n) {
    throw new Error("native category_labels returned an unexpected label count");
  }
  const labels = [];
  offset = 0;
  for (let i = 0; i < n; i += 1) {
    const end = offset + outLens[i];
    labels.push(new TextDecoder("utf-8").decode(outTexts.subarray(offset, end)));
    offset = end;
  }
  return labels;
}

/** Canonical display label — lockstep with Python `category_label`. */
export function categoryLabel(value) {
  return categoryLabelsFromEncodings([categoryLabelKindAndBytes(value)])[0];
}

function categoryLabels(values) {
  return categoryLabelsFromEncodings(values.map(categoryLabelKindAndBytes));
}

function categoryLabelFromFloat(value) {
  if (Number.isNaN(value)) {
    return categoryLabel(Number.NaN);
  }
  const text = Number.isInteger(value) ? `${value}.0` : String(value);
  return categoryLabelsFromEncodings([{ kind: 1, payload: new TextEncoder().encode(text) }])[0];
}

function facetTypedCategoryLabel(view, index) {
  const value = view[index];
  if (view instanceof Float64Array || view instanceof Float32Array) {
    return categoryLabelFromFloat(value);
  }
  return categoryLabel(value);
}

function recordCount(data, width) {
  if (data instanceof Uint8Array && width > 1 && data.length % width === 0) {
    return data.length / width;
  }
  return data.length;
}

function decodeRecord(view, index, width) {
  if (width === 1) return view[index];
  const byteOffset = index * width;
  return new Uint8Array(view.buffer, view.byteOffset + byteOffset, width);
}

export function useNativeFixedFactorizer(data, width) {
  const n = recordCount(data, width);
  if (n === 0) {
    const ok = xyFactorizeUseNativeFixed(null, 0n, BigInt(width));
    if (ok < 0) {
      throw new RangeError("native factorize_use_native_fixed rejected the record array");
    }
    return ok === 1;
  }
  const bytes = data instanceof Uint8Array && width > 1 ? data : bytesView(data);
  const ok = xyFactorizeUseNativeFixed(u8Ptr(bytes), BigInt(n), BigInt(width));
  if (ok < 0) {
    throw new RangeError("native factorize_use_native_fixed rejected the record array");
  }
  return ok === 1;
}

function sortedDisplayLabelRemapJs(uniqueLabels, rawCounts = null) {
  const n = uniqueLabels.length;
  if (n === 0) {
    return {
      categories: [],
      remap: new Uint8Array(0),
      counts: rawCounts == null ? null : new BigUint64Array(0),
      width: 1,
    };
  }
  const enc = new TextEncoder();
  const encoded = uniqueLabels.map((label) => enc.encode(label));
  const lens = Uint32Array.from(encoded, (bytes) => bytes.length);
  const texts = new Uint8Array(lens.reduce((sum, len) => sum + len, 0));
  let offset = 0;
  for (const bytes of encoded) {
    texts.set(bytes, offset);
    offset += bytes.length;
  }
  const outRemapRaw = new Uint8Array(n * 4);
  const codeWidth = new Uint32Array(1);
  const categoryLensCap = Math.max(n, 256);
  const categoryLens = new Uint32Array(categoryLensCap);
  const categoryTextsCap = Math.max(256, texts.length * 2);
  const categoryTexts = new Uint8Array(categoryTextsCap);
  const categoryCounts = new BigUint64Array(categoryLensCap);
  const inCountsPtr =
    rawCounts == null ? null : u64Ptr(rawCounts.subarray(0, n));
  const written = xySortedDisplayLabelRemap(
    u32Ptr(lens),
    u8Ptr(texts),
    BigInt(texts.length),
    BigInt(n),
    inCountsPtr,
    u8Ptr(outRemapRaw),
    BigInt(outRemapRaw.length),
    u32Ptr(codeWidth),
    u32Ptr(categoryLens),
    u8Ptr(categoryTexts),
    BigInt(categoryTexts.length),
    BigInt(categoryLensCap),
    rawCounts == null ? null : u64Ptr(categoryCounts),
    rawCounts == null ? 0n : BigInt(categoryCounts.length),
  );
  if (written === USIZE_MAX_64) {
    throw new RangeError("native sorted_display_label_remap rejected the label array");
  }
  const nCategories = Number(written);
  const categories = [];
  let textOffset = 0;
  const dec = new TextDecoder();
  for (let i = 0; i < nCategories; i += 1) {
    const len = categoryLens[i];
    categories.push(dec.decode(categoryTexts.subarray(textOffset, textOffset + len)));
    textOffset += len;
  }
  const width = Number(codeWidth[0]);
  let remap;
  if (width === 1) {
    remap = outRemapRaw.slice(0, n);
  } else if (width === 4) {
    remap = new Uint32Array(outRemapRaw.buffer, outRemapRaw.byteOffset, n);
  } else {
    throw new RangeError("native sorted_display_label_remap returned an unknown code width");
  }
  const counts =
    rawCounts == null ? null : categoryCounts.subarray(0, nCategories);
  return { categories, remap, counts, width };
}

function sortedCategoryRemap(uniqueLabels) {
  return sortedDisplayLabelRemapJs(uniqueLabels);
}

function remapIsIdentity(remap) {
  for (let i = 0; i < remap.length; i += 1) {
    if (remap[i] !== i) return false;
  }
  return true;
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
  const { categories, remap, counts } = sortedDisplayLabelRemapJs(uniqueLabels, rawCounts);
  if (!remapIsIdentity(remap)) {
    const mapping = remap instanceof Uint8Array ? remap : Uint8Array.from(remap);
    const ok = Number(
      xyRemapU8(u8Ptr(rawCodes), BigInt(rawCodes.length), u8Ptr(mapping), BigInt(mapping.length)),
    );
    if (ok !== 1) throw new RangeError("native remap_u8 rejected categorical remap");
  }
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
  const { categories, remap } = sortedDisplayLabelRemapJs(uniqueLabels);
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
function valueProbe(value) {
  if (isMissingCategory(value)) return 0;
  if (typeof value === "boolean") return 1;
  if (typeof value === "string") return 2;
  if (value instanceof Uint8Array) return 3;
  if (ArrayBuffer.isView(value)) return 3;
  if (typeof value === "number" && Number.isFinite(value)) return 4;
  try {
    const coerced = Number(value);
    if (Number.isFinite(coerced)) return 5;
  } catch {
    return 6;
  }
  return 6;
}

export function objectRowStringlikeTagFromProbe(probe) {
  const code = Number(xyObjectRowStringlikeTagFromProbe(Number(probe) & 0xff));
  if (code < 0) throw new RangeError("invalid object-row-stringlike-tag request");
  return code;
}

export function objectRowRealNumericTagFromProbe(probe) {
  const code = Number(xyObjectRowRealNumericTagFromProbe(Number(probe) & 0xff));
  if (code < 0) throw new RangeError("invalid object-row-real-numeric-tag request");
  return code;
}

export function categoryLabelKindFromProbe(probe) {
  const code = Number(xyCategoryLabelKindFromProbe(Number(probe) & 0xff));
  if (code < 0) throw new RangeError("invalid category-label-kind request");
  return code;
}

function objectRowRealNumericTag(value) {
  return objectRowRealNumericTagFromProbe(valueProbe(value));
}

export function objectColumnIsRealNumeric(raw) {
  if (!Array.isArray(raw)) return false;
  const tags = Uint8Array.from(raw, objectRowRealNumericTag);
  const ok = Number(xyObjectRowsAllRealNumeric(pointer(tags, "uint8_t *"), BigInt(tags.length)));
  if (ok < 0) {
    throw new Error("native object_rows_all_real_numeric rejected the row tags");
  }
  return ok === 1;
}

function objectRowStringlikeTag(value) {
  return objectRowStringlikeTagFromProbe(valueProbe(value));
}

export function objectColumnIsStringlike(raw) {
  if (!Array.isArray(raw)) return false;
  const tags = Uint8Array.from(raw, objectRowStringlikeTag);
  const ok = Number(xyObjectRowsAllStringlike(pointer(tags, "uint8_t *"), BigInt(tags.length)));
  if (ok < 0) {
    throw new Error("native object_rows_all_stringlike rejected the row tags");
  }
  return ok === 1;
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

function labelCodesFirstSeenJs(labels) {
  const n = labels.length;
  if (n === 0) {
    return { categories: [], codes: new Uint8Array(0) };
  }
  const enc = new TextEncoder();
  const encoded = labels.map((label) => enc.encode(label));
  const lens = Uint32Array.from(encoded, (bytes) => bytes.length);
  const texts = new Uint8Array(lens.reduce((sum, len) => sum + len, 0));
  let offset = 0;
  for (const bytes of encoded) {
    texts.set(bytes, offset);
    offset += bytes.length;
  }
  const outCodesRaw = new Uint8Array(n * 4);
  const codeWidth = new Uint32Array(1);
  const categoryLensCap = Math.max(n, 256);
  const categoryLens = new Uint32Array(categoryLensCap);
  const categoryTextsCap = Math.max(256, texts.length * 2);
  const categoryTexts = new Uint8Array(categoryTextsCap);
  const written = xyLabelCodesFirstSeen(
    u32Ptr(lens),
    u8Ptr(texts),
    BigInt(texts.length),
    BigInt(n),
    u8Ptr(outCodesRaw),
    BigInt(outCodesRaw.length),
    u32Ptr(codeWidth),
    u32Ptr(categoryLens),
    u8Ptr(categoryTexts),
    BigInt(categoryTexts.length),
    BigInt(categoryLensCap),
  );
  if (written === USIZE_MAX_64) {
    throw new RangeError("native label_codes_first_seen rejected the label array");
  }
  const nCategories = Number(written);
  const categories = [];
  let textOffset = 0;
  const dec = new TextDecoder();
  for (let i = 0; i < nCategories; i += 1) {
    const len = categoryLens[i];
    categories.push(dec.decode(categoryTexts.subarray(textOffset, textOffset + len)));
    textOffset += len;
  }
  const width = Number(codeWidth[0]);
  let codes;
  if (width === 1) {
    codes = outCodesRaw.slice(0, n);
  } else if (width === 4) {
    codes = new Uint32Array(outCodesRaw.buffer, outCodesRaw.byteOffset, n);
  } else {
    throw new RangeError("native label_codes_first_seen returned an unknown code width");
  }
  return { categories, codes };
}

export function sortedDisplayLabelRemap(uniqueLabels, rawCounts = null) {
  const { categories, remap, counts } = sortedDisplayLabelRemapJs(uniqueLabels, rawCounts);
  return { categories, remap, counts };
}

/**
 * Dedupe display labels in first-seen order for facet panels.
 *
 * @param {string[]} labels
 * @returns {{categories: string[], codes: Uint8Array|Uint32Array}}
 */
export function labelCodesFirstSeen(labels) {
  return labelCodesFirstSeenJs(labels.map((value) => String(value)));
}

function factorizeFixedFirstSeen(view) {
  const width = view.BYTES_PER_ELEMENT;
  const n = view.length;
  if (n === 0) {
    return {
      rawCodes: new Uint32Array(0),
      uniqueIndices: new Uint32Array(0),
      uniq: 0,
    };
  }
  const codes = new Uint32Array(n);
  const uniqueIndices = new Uint32Array(n);
  const bytes = bytesView(view);
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
  return { rawCodes: codes, uniqueIndices, uniq: Number(written) };
}

/**
 * Factorize a facet column into first-seen panel codes + labels.
 *
 * Mirrors Python `facets._facet_values` for typed columns (native
 * `factorize_fixed` + display-label dedupe) and object columns (batch
 * `category_label` + first-seen dedupe).
 *
 * @param {Array|TypedArray} raw
 * @returns {{categories: string[], codes: Uint8Array|Uint32Array}}
 */
export function facetValues(raw) {
  if (ArrayBuffer.isView(raw) && !(raw instanceof DataView)) {
    const view = /** @type {ArrayBufferView & {length: number}} */ (raw);
    const { rawCodes, uniqueIndices, uniq } = factorizeFixedFirstSeen(view);
    const displayLabels = [];
    for (let i = 0; i < uniq; i += 1) {
      displayLabels.push(facetTypedCategoryLabel(view, uniqueIndices[i]));
    }
    const { categories, codes: labelCodes } = labelCodesFirstSeenJs(displayLabels);
    const out = new Uint32Array(view.length);
    for (let i = 0; i < view.length; i += 1) {
      out[i] = labelCodes[rawCodes[i]];
    }
    return { categories, codes: out };
  }
  const rows = Array.isArray(raw) ? raw : [...raw];
  return labelCodesFirstSeenJs(categoryLabels(rows));
}

function factorizeDisplayLabelsJs(labels) {
  const n = labels.length;
  if (n === 0) {
    return {
      mode: "categorical",
      codes: new Uint8Array(0),
      categories: [],
      counts: null,
      palette: [...DEFAULT_PALETTE],
    };
  }
  const enc = new TextEncoder();
  const encoded = labels.map((label) => enc.encode(label));
  const lens = Uint32Array.from(encoded, (bytes) => bytes.length);
  const texts = new Uint8Array(lens.reduce((sum, len) => sum + len, 0));
  let offset = 0;
  for (const bytes of encoded) {
    texts.set(bytes, offset);
    offset += bytes.length;
  }
  const outCodesRaw = new Uint8Array(n * 4);
  const codeWidth = new Uint32Array(1);
  const categoryLensCap = Math.max(n, 256);
  const categoryLens = new Uint32Array(categoryLensCap);
  const categoryTextsCap = Math.max(256, texts.length * 2);
  const categoryTexts = new Uint8Array(categoryTextsCap);
  const written = xyFactorizeDisplayLabels(
    u32Ptr(lens),
    u8Ptr(texts),
    BigInt(texts.length),
    BigInt(n),
    u8Ptr(outCodesRaw),
    BigInt(outCodesRaw.length),
    u32Ptr(codeWidth),
    u32Ptr(categoryLens),
    u8Ptr(categoryTexts),
    BigInt(categoryTexts.length),
    BigInt(categoryLensCap),
  );
  if (written === USIZE_MAX_64) {
    throw new RangeError("native factorize_display_labels rejected the label array");
  }
  const nCategories = Number(written);
  const categories = [];
  let textOffset = 0;
  const dec = new TextDecoder();
  for (let i = 0; i < nCategories; i += 1) {
    const len = categoryLens[i];
    categories.push(dec.decode(categoryTexts.subarray(textOffset, textOffset + len)));
    textOffset += len;
  }
  const width = Number(codeWidth[0]);
  let codes;
  if (width === 1) {
    codes = outCodesRaw.slice(0, n);
  } else if (width === 4) {
    codes = new Uint32Array(outCodesRaw.buffer, outCodesRaw.byteOffset, n);
  } else {
    throw new RangeError("native factorize_display_labels returned an unknown code width");
  }
  return {
    mode: "categorical",
    codes,
    categories,
    counts: null,
    palette: [...DEFAULT_PALETTE],
  };
}

function factorizeJsArray(raw) {
  const labels = raw.map(categoryLabel);
  return factorizeDisplayLabelsJs(labels);
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
