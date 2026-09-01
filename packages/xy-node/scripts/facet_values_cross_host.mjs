/**
 * Cross-host facet_values parity probe for Python vs Node.
 */
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

import { facetValues } from "../src/factorize.js";

const ROOT = join(dirname(fileURLToPath(import.meta.url)), "..", "..", "..");
const FIXTURE = join(ROOT, "tests", "fixtures", "facet_values_cross_host.json");

function buildValues(spec) {
  if (spec.kind === "object") {
    return spec.values.map((value) => (value === null ? null : value));
  }
  if (spec.kind === "float64") {
    return Float64Array.from(
      spec.values.map((value) => (value === null ? Number.NaN : value)),
    );
  }
  return spec.values;
}

const fixture = JSON.parse(readFileSync(FIXTURE, "utf8"));
const out = fixture.cases.map((spec) => {
  const factored = facetValues(buildValues(spec));
  return {
    name: spec.name,
    categories: factored.categories,
    codes: [...factored.codes].map((value) => Number(value)),
  };
});
process.stdout.write(JSON.stringify(out));
