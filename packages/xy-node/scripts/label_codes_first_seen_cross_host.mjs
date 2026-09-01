/**
 * Cross-host label_codes_first_seen parity probe for Python vs Node.
 */
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

import { labelCodesFirstSeen } from "../src/factorize.js";

const ROOT = join(dirname(fileURLToPath(import.meta.url)), "..", "..", "..");
const FIXTURE = join(ROOT, "tests", "fixtures", "label_codes_first_seen_cross_host.json");

const fixture = JSON.parse(readFileSync(FIXTURE, "utf8"));
const out = fixture.cases.map((spec) => {
  const factored = labelCodesFirstSeen(spec.labels);
  return {
    name: spec.name,
    categories: factored.categories,
    codes: [...factored.codes].map((value) => Number(value)),
  };
});
process.stdout.write(JSON.stringify(out));
