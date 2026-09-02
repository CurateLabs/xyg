/**
 * Cross-host category_label parity probe for Python vs Node.
 */
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

import { categoryLabel } from "../src/factorize.js";

const ROOT = join(dirname(fileURLToPath(import.meta.url)), "..", "..", "..");
const FIXTURE = join(ROOT, "tests", "fixtures", "category_label_cross_host.json");

function decodeCase(spec) {
  switch (spec.kind) {
    case "null":
      return null;
    case "nan":
      return Number.NaN;
    case "string":
      return spec.value;
    case "bytes":
      return Uint8Array.from(spec.hex.match(/.{1,2}/g).map((byte) => parseInt(byte, 16)));
    case "int":
      return spec.value;
    case "bool":
      return spec.value;
    default:
      throw new Error(`unknown case kind ${spec.kind}`);
  }
}

const fixture = JSON.parse(readFileSync(FIXTURE, "utf8"));
const out = fixture.cases.map((spec) => ({
  name: spec.name,
  label: categoryLabel(decodeCase(spec)),
}));
process.stdout.write(JSON.stringify(out));
