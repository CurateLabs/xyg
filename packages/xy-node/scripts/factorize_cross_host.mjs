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

import { factorizeCategories } from "../src/factorize.js";
import { xyFactorizeUseNativeProbe } from "../src/native.js";

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
  const raw = buildValues(spec);
  out.push(digestFactored(spec.name, factorizeCategories(raw)));
}
process.stdout.write(`${JSON.stringify({ cases: out })}\n`);
