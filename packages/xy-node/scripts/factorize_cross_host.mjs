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
import { quantizeUnitU8, paletteRowsRgba8 } from "../src/color.js";
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
