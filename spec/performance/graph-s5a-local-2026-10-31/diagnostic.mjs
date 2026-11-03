// Functional replay only after a failed real shipping gate. This invokes the
// exact production optimizer; it changes no input, flags, exports or budgets.
import { readFileSync, writeFileSync, mkdirSync } from "node:fs";
import { createHash } from "node:crypto";
import { gzipSync } from "node:zlib";
import { optimizeWasm } from "../../../js/optimize-wasm.mjs";
import assert from "node:assert/strict";

const source = "target/wasm32-unknown-unknown/release/xyg_wasm.wasm";
const output = "target/task-tmp/s5a-diagnostic.wasm";
const raw = readFileSync(source);
const bytes = optimizeWasm(raw);
mkdirSync("target/task-tmp", { recursive: true });
writeFileSync(output, bytes);
const gzip = gzipSync(bytes);
const sha = (bytes) => createHash("sha256").update(bytes).digest("hex");
const module = await WebAssembly.compile(bytes);
const exports = WebAssembly.Module.exports(module).filter((v) => v.kind === "function");
const instance = await WebAssembly.instantiate(module, {});
const manifest = JSON.parse(readFileSync("spec/wasm/abi.json", "utf8"));
// Inspect actual compiled type/function/export sections without publishing or
// altering the failed production gate. WebAssembly.compile validated framing.
let at = 8;
const u32 = () => {
  let value = 0, shift = 0, byte;
  do { byte = bytes[at++]; value |= (byte & 127) << shift; shift += 7; } while (byte & 128);
  return value >>> 0;
};
const vector = (read) => Array.from({length: u32()}, read);
const name = () => { const count = u32(), start = at; at += count; return bytes.subarray(start, at).toString("utf8"); };
const types = [], functions = [], signatures = new Map();
while (at < bytes.length) {
  const id = bytes[at++], size = u32(), end = at + size;
  assert.notEqual(id, 8, "no start function");
  if (id === 1) types.push(...vector(() => { assert.equal(bytes[at++], 0x60); return {params: vector(() => bytes[at++]), results: vector(() => bytes[at++])}; }));
  if (id === 3) functions.push(...vector(u32));
  if (id === 7) vector(() => { const label = name(), kind = bytes[at++], index = u32(); if (kind === 0) signatures.set(label, types[functions[index]]); });
  at = end;
}
const wasmType = (value) => ["u64", "i64"].includes(value) ? 0x7e : 0x7f;
assert.deepEqual([...signatures.keys()].sort(), manifest.exports.map((v) => v.name).sort());
for (const expected of manifest.exports) assert.deepEqual(signatures.get(expected.name), {params: expected.params.map(wasmType), results: [wasmType(expected.result)]}, expected.name);
assert.deepEqual(WebAssembly.Module.imports(module), []);
assert.equal(instance.exports.xyg_wasm_abi_version(), manifest.abi_version);
assert.equal(instance.exports.xyg_wasm_scene_version(), manifest.scene_version);
const result = {
  diagnosticOnly: true, shippingGatePassed: false,
  source, output, node: process.version, rawBytes: bytes.length, gzip6Bytes: gzip.length,
  rawGate: 1817 * 1024, gzip6Gate: 742 * 1024,
  rawOver: Math.max(0, bytes.length - 1817 * 1024), gzip6Over: Math.max(0, gzip.length - 742 * 1024),
  unoptimizedSha256: sha(raw), optimizedSha256: sha(bytes), gzip6Sha256: sha(gzip),
  functions: exports.length, exactManifestSignatures: signatures.size, imports: WebAssembly.Module.imports(module),
  painterVersion: manifest.painter_version,
  wasmAbi: instance.exports.xyg_wasm_abi_version(), sceneVersion: instance.exports.xyg_wasm_scene_version(),
  exports: exports.map((v) => v.name).sort(),
};
writeFileSync("target/task-tmp/s5a-diagnostic.json", JSON.stringify(result, null, 2) + "\n");
console.log(JSON.stringify(result, null, 2));
