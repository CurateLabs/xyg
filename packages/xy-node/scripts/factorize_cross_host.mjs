/**
 * Cross-host categorical factorization parity probe for Python vs Node.
 *
 * Reads tests/fixtures/factorize_cross_host.json and prints sorted categories,
 * codes, and counts for each case.
 */
import { readFileSync } from "node:fs";
import { createHash } from "node:crypto";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

import {
  factorizeCategories,
  objectColumnIsStringlike,
  objectColumnIsRealNumeric,
  useNativeFixedFactorizer,
} from "../src/factorize.js";
import { xyFactorizeUseNativeProbe, xyFoldCodesU8 } from "../src/native.js";
import { u32Ptr, u8Ptr } from "../src/encode.js";
import { quantizeUnitU8, paletteRowsRgba8, literalColorRgbaF64, categoricalPalette, categoricalPaletteMapResolve, colorChannelDirectRgbaF64Continuous, colorChannelDirectRgbaF64Categorical, colormapIsBuiltin, colormapCustomStopsResolveGradient, colormapCustomStopsResolveList, sizeRangeAdmit, arrayIsCategorical, realNumericDtypeAdmit } from "../src/color.js";
import { objectRowStringlikeTagFromProbe, objectRowRealNumericTagFromProbe, categoryLabelKindFromProbe, categoryCodeWidth, categoryPaletteRows } from "../src/factorize.js";
import { stratifiedSampleRangePlan } from "../src/encode.js";
import { colormapLutRgba8 } from "../src/encode.js";

const ROOT = join(dirname(fileURLToPath(import.meta.url)), "..", "..", "..");
const FIXTURE = join(ROOT, "tests", "fixtures", "factorize_cross_host.json");

function mulberry32(seed) {
  let t = seed >>> 0;
  return () => {
    t += 0x6d2b79f5;
    let r = Math.imul(t ^ (t >>> 15), 1 | t);
    r ^= r + Math.imul(r ^ (r >>> 7), 61 | r);
    return ((r ^ (r >>> 14)) >>> 0) / 4294967296;
  };
}

function buildFixedProbeValues(spec) {
  const rowCount = spec.row_count;
  if (rowCount === 0) {
    return new Uint32Array(0);
  }
  if (spec.modulo != null) {
    const out = new Uint32Array(rowCount);
    for (let i = 0; i < rowCount; i += 1) {
      out[i] = i % spec.modulo;
    }
    return out;
  }
  const out = new Uint32Array(rowCount);
  for (let i = 0; i < rowCount; i += 1) {
    out[i] = i;
  }
  return out;
}

function buildValues(spec) {
  if (spec.kind === "uint8") {
    return Uint8Array.from(spec.values);
  }
  if (spec.kind === "object") {
    return spec.values.map((value) => (value === null ? null : value));
  }
  if (spec.kind === "unicode" && spec.seed != null) {
    const rng = mulberry32(spec.seed);
    const categories = Array.from(
      { length: spec.category_count },
      (_, i) => `group-${String(i).padStart(3, "0")}`,
    );
    const rows = [];
    for (let i = 0; i < spec.row_count; i += 1) {
      rows.push(categories[Math.floor(rng() * categories.length)]);
    }
    return rows;
  }
  return spec.values;
}

function digestFactored(name, factored) {
  const codes = [...factored.codes].map((v) => Number(v));
  const counts =
    factored.counts == null
      ? null
      : [...factored.counts].map((v) => Number(v));
  const payload = JSON.stringify({
    categories: factored.categories,
    codes,
    counts,
  });
  return {
    name,
    categories: factored.categories,
    codes,
    counts,
    sha256: createHash("sha256").update(payload).digest("hex"),
  };
}

const fixture = JSON.parse(readFileSync(FIXTURE, "utf8"));
const out = [];
for (const spec of fixture.cases) {
  if (spec.kind === "probe") {
    const ok = Number(
      xyFactorizeUseNativeProbe(
        BigInt(spec.distinct),
        BigInt(spec.probe_len),
        BigInt(spec.record_width),
      ),
    );
    out.push({
      name: spec.name,
      use_native: ok === 1,
    });
    continue;
  }
  if (spec.kind === "fixed_probe") {
    const values = buildFixedProbeValues(spec);
    out.push({
      name: spec.name,
      use_native: useNativeFixedFactorizer(values, 4),
    });
    continue;
  }
  if (spec.kind === "fold_codes_u8") {
    const codes = Uint32Array.from(spec.codes ?? []);
    const n = codes.length;
    const folded = new Uint8Array(n);
    if (n > 0) {
      const ok = xyFoldCodesU8(u32Ptr(codes), BigInt(n), BigInt(spec.n_palette), u8Ptr(folded));
      if (!ok) {
        throw new Error(`fold_codes_u8 rejected ${spec.name}`);
      }
    }
    out.push({
      name: spec.name,
      folded: [...folded],
    });
    continue;
  }
  if (spec.kind === "quantize_unit_u8") {
    const values = Float64Array.from(
      (spec.values ?? []).map((value) => (value == null ? Number.NaN : Number(value))),
    );
    const domain = spec.domain ?? [0, 1];
    const quantized = quantizeUnitU8(values, Number(domain[0]), Number(domain[1]));
    out.push({
      name: spec.name,
      quantized: [...quantized],
    });
    continue;
  }
  if (spec.kind === "palette_rows_rgba8") {
    if (spec.expect_error) {
      try {
        paletteRowsRgba8(spec.palette ?? [], spec.rows ?? 1);
        throw new Error(`expected palette_rows_rgba8 error for ${spec.name}`);
      } catch {
        out.push({ name: spec.name, error: true });
      }
      continue;
    }
    const lut = paletteRowsRgba8(spec.palette, spec.rows);
    const n = Math.max(1, Math.floor(Number(spec.rows)));
    const rows = [];
    for (let i = 0; i < n; i += 1) {
      rows.push([...lut.slice(i * 4, i * 4 + 4)]);
    }
    out.push({ name: spec.name, rows });
    continue;
  }
  if (spec.kind === "colormap_lut_rgba8") {
    const lut = spec.colormap != null
      ? colormapLutRgba8(spec.colormap)
      : colormapLutRgba8(Uint8Array.from(spec.stops.flat()));
    const rows = [];
    for (let i = 0; i < 256; i += 1) {
      rows.push([...lut.slice(i * 4, i * 4 + 4)]);
    }
    out.push({ name: spec.name, rows });
    continue;
  }
  if (spec.kind === "literal_color_rgba_f64") {
    const packed = literalColorRgbaF64(spec.values ?? []);
    if (spec.expect_null) {
      out.push({ name: spec.name, rgba: null });
      continue;
    }
    const n = (spec.values ?? []).length;
    const rows = [];
    for (let i = 0; i < n; i += 1) {
      rows.push([...packed.slice(i * 4, i * 4 + 4)]);
    }
    out.push({ name: spec.name, rgba: rows });
    continue;
  }
  if (spec.kind === "stratified_sample_range_plan") {
    const plan = stratifiedSampleRangePlan(
      spec.n_rows,
      spec.n_groups,
      spec.target,
      spec.level,
      spec.growth,
      spec.seed,
      spec.min_per_category,
    );
    out.push({
      name: spec.name,
      fraction: plan.fraction,
      seed: Number(plan.seed),
      min_count: plan.minCount,
      capacity: plan.capacity,
      keep_all: plan.keepAll,
    });
    continue;
  }
  if (spec.kind === "categorical_palette") {
    const colors = categoricalPalette(spec.palette, spec.n_categories);
    out.push({ name: spec.name, colors });
    continue;
  }
  if (spec.kind === "categorical_palette_map_resolve") {
    const resolved = categoricalPaletteMapResolve(
      spec.categories,
      spec.palette_map ?? {},
      spec.default_palette ?? [],
    );
    out.push({
      name: spec.name,
      colors: resolved.colors,
      unmapped_count: resolved.unmappedCount,
      map_exhausted: resolved.mapExhausted,
    });
    continue;
  }
  if (spec.kind === "color_channel_direct_rgba_f64_continuous") {
    const rgba = colorChannelDirectRgbaF64Continuous(
      spec.values,
      spec.domain,
      Uint8Array.from(spec.stops.flat()),
    );
    const rows = [];
    for (let i = 0; i < spec.values.length; i += 1) {
      rows.push([...rgba.slice(i * 4, i * 4 + 4)]);
    }
    out.push({ name: spec.name, rgba: rows });
    continue;
  }
  if (spec.kind === "color_channel_direct_rgba_f64_categorical") {
    const rgba = colorChannelDirectRgbaF64Categorical(spec.codes, spec.palette);
    const rows = [];
    for (let i = 0; i < spec.codes.length; i += 1) {
      rows.push([...rgba.slice(i * 4, i * 4 + 4)]);
    }
    out.push({ name: spec.name, rgba: rows });
    continue;
  }
  if (spec.kind === "colormap_is_builtin") {
    out.push({
      name: spec.name,
      builtin: colormapIsBuiltin(spec.colormap_name),
    });
    continue;
  }
  if (spec.kind === "colormap_custom_stops_resolve_list") {
    const positions =
      spec.positions == null
        ? spec.colors.map(() => null)
        : spec.positions.map((value) => (value == null ? null : Number(value)));
    out.push({
      name: spec.name,
      stops: colormapCustomStopsResolveList(spec.colors, positions),
    });
    continue;
  }
  if (spec.kind === "colormap_custom_stops_resolve_gradient") {
    out.push({
      name: spec.name,
      stops: colormapCustomStopsResolveGradient(spec.gradient),
    });
    continue;
  }
  if (spec.kind === "size_range_admit") {
    out.push({
      name: spec.name,
      range_px: sizeRangeAdmit(spec.lo, spec.hi),
    });
    continue;
  }
  if (spec.kind === "array_is_categorical") {
    out.push({
      name: spec.name,
      categorical: arrayIsCategorical(
        spec.dtype_kind.codePointAt(0),
        spec.object_real_numeric,
      ),
    });
    continue;
  }
  if (spec.kind === "real_numeric_dtype_admit") {
    try {
      realNumericDtypeAdmit(spec.dtype_kind.codePointAt(0));
      out.push({ name: spec.name, ok: true });
    } catch (err) {
      const msg = String(err?.message ?? err);
      out.push({
        name: spec.name,
        ok: false,
        error: msg.includes("boolean") ? "boolean" : "complex",
      });
    }
    continue;
  }
  if (spec.kind === "object_row_stringlike_tag") {
    out.push({
      name: spec.name,
      tag: objectRowStringlikeTagFromProbe(spec.probe),
    });
    continue;
  }
  if (spec.kind === "object_row_real_numeric_tag") {
    out.push({
      name: spec.name,
      tag: objectRowRealNumericTagFromProbe(spec.probe),
    });
    continue;
  }
  if (spec.kind === "category_label_kind") {
    out.push({
      name: spec.name,
      label_kind: categoryLabelKindFromProbe(spec.probe),
    });
    continue;
  }
  if (spec.kind === "category_code_width") {
    out.push({
      name: spec.name,
      code_width: categoryCodeWidth(spec.n_categories),
    });
    continue;
  }
  if (spec.kind === "category_palette_rows") {
    out.push({
      name: spec.name,
      palette_rows: categoryPaletteRows(spec.n_categories),
    });
    continue;
  }
  if (spec.kind === "stringlike") {
    const raw = spec.values.map((value) => (value === null ? null : value));
    out.push({
      name: spec.name,
      stringlike: objectColumnIsStringlike(raw),
    });
    continue;
  }
  if (spec.kind === "real_numeric") {
    const raw = spec.values.map((value) => (value === null ? null : value));
    out.push({
      name: spec.name,
      real_numeric: objectColumnIsRealNumeric(raw),
    });
    continue;
  }
  const raw = buildValues(spec);
  out.push(digestFactored(spec.name, factorizeCategories(raw)));
}
process.stdout.write(`${JSON.stringify({ cases: out })}\n`);
