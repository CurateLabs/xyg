/**
 * Cross-host sorted_display_label_remap parity probe for Python vs Node.
 */
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

import { sortedDisplayLabelRemap } from "../src/factorize.js";

const ROOT = join(dirname(fileURLToPath(import.meta.url)), "..", "..", "..");
const FIXTURE = join(
  ROOT,
  "tests",
  "fixtures",
  "sorted_display_label_remap_cross_host.json",
);

const fixture = JSON.parse(readFileSync(FIXTURE, "utf8"));
const out = fixture.cases.map((spec) => {
  const counts =
    spec.counts == null ? null : BigUint64Array.from(spec.counts.map((value) => BigInt(value)));
  const factored = sortedDisplayLabelRemap(spec.labels, counts);
  return {
    name: spec.name,
    categories: factored.categories,
    remap: [...factored.remap].map((value) => Number(value)),
    counts:
      factored.counts == null ? null : [...factored.counts].map((value) => Number(value)),
  };
});
process.stdout.write(JSON.stringify(out));
