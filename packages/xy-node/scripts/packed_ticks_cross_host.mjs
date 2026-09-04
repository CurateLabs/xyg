import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { tickResolvePacked } from "../src/index.js";

const here = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(here, "../../..");
const fixture = JSON.parse(fs.readFileSync(
  path.join(root, "tests/fixtures/packed_ticks_cross_host.json"),
  "utf8",
));
const request = Uint8Array.from(Buffer.from(fixture.request_hex, "hex"));
const output = tickResolvePacked(request);
const outputHex = Buffer.from(output).toString("hex");
if (outputHex !== fixture.output_hex) {
  throw new Error("Node/native packed tick output differs from the exact fixture");
}
const malformed = new Map();
const embeddedNul = request.slice();
const embeddedNulView = new DataView(embeddedNul.buffer, embeddedNul.byteOffset, embeddedNul.byteLength);
embeddedNul[embeddedNulView.getUint32(32 + 92, true)] = 0;
malformed.set("embedded-nul", embeddedNul);
const irrelevantCategory = request.slice();
new DataView(irrelevantCategory.buffer, irrelevantCategory.byteOffset, irrelevantCategory.byteLength)
  .setUint32(32 + 4 * 96 + 8, 0, true);
malformed.set("category-plane-on-linear", irrelevantCategory);
const irrelevantLabels = request.slice();
new DataView(irrelevantLabels.buffer, irrelevantLabels.byteOffset, irrelevantLabels.byteLength)
  .setUint32(32 + 96 + 12, 2, true);
malformed.set("label-plane-on-minor", irrelevantLabels);
const irrelevantFormat = request.slice();
new DataView(irrelevantFormat.buffer, irrelevantFormat.byteOffset, irrelevantFormat.byteLength)
  .setUint32(32 + 12, 2, true);
malformed.set("format-plane-on-minor", irrelevantFormat);
for (const [name, bytes] of malformed) {
  try {
    tickResolvePacked(bytes);
    throw new Error(`${name}: native packed tick resolver unexpectedly accepted malformed bytes`);
  } catch (error) {
    if (!(error instanceof RangeError) || !String(error.message).includes("rejected")) throw error;
  }
}
process.stdout.write(`${outputHex}\n`);
