// Replay against an optional saved codec source; no native core is loaded.
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { pathToFileURL } from "node:url";

const source = process.argv[2]
  ? pathToFileURL(resolve(process.argv[2]))
  : new URL("../../../packages/xy-node/src/graphforge-container.js", import.meta.url);
const { encodeContainer, decodeContainer, DTYPE } = await import(source);
const expected = [7n, 9n, 1n];
const bytes = encodeContainer("XYGI", [{ name: "header.u64", dtype: DTYPE.u64, values: expected }]);
assert.equal(bytes.length, 112);
const backing = Buffer.alloc(113, 0xa5);
backing.set(bytes);
const buffer = backing.subarray(0, bytes.length);
assert.deepEqual([...buffer], [...bytes]);
assert.deepEqual([...decodeContainer(bytes, "XYGI").get("header.u64#0").value], expected);
let outcome;
try {
  const actual = decodeContainer(buffer, "XYGI").get("header.u64#0").value;
  assert.deepEqual([...actual], expected);
  outcome = { status: "pass", count: actual.length, values: [...actual].map(String) };
} catch (error) {
  outcome = { status: "fail", error: error.name, message: error.message };
  process.exitCode = 1;
}
console.log(JSON.stringify({
  node: process.version,
  platform: process.platform,
  arch: process.arch,
  codecSha256: createHash("sha256").update(readFileSync(source)).digest("hex"),
  inputSha256: createHash("sha256").update(bytes).digest("hex"),
  inputHex: Buffer.from(bytes).toString("hex"),
  inputBytes: bytes.length,
  backingBytes: buffer.buffer.byteLength,
  identicalInput: true,
  plainUint8Array: "pass",
  buffer: outcome,
}, null, 2));
