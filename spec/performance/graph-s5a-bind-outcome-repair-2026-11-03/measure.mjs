// Measure actual production output after the unchanged packaging gate succeeds.
import assert from "node:assert/strict";
import { readFileSync, writeFileSync } from "node:fs";
import { createHash } from "node:crypto";
import { gzipSync } from "node:zlib";

const bytes = readFileSync("packages/xy-client/dist/xyg-wasm.wasm");
assert.deepEqual(bytes, readFileSync("python/xyg/static/xyg-wasm.wasm"));
const compressed = gzipSync(bytes);
const sha = data => createHash("sha256").update(data).digest("hex");
const manifest = JSON.parse(readFileSync("spec/wasm/abi.json", "utf8"));
const module = await WebAssembly.compile(bytes);
const instance = await WebAssembly.instantiate(module, {});
assert.deepEqual(WebAssembly.Module.imports(module), []);
assert.equal(instance.exports.xyg_wasm_abi_version(), manifest.abi_version);
assert.equal(instance.exports.xyg_wasm_scene_version(), manifest.scene_version);
assert.ok(bytes.length <= 1829 * 1024);
assert.ok(compressed.length <= 747 * 1024);
const result = {
  source: "production-dist", diagnosticModule: false, artifactCommit: null,
  node: process.version, bytes: bytes.length, gzip6Bytes: compressed.length,
  sha256: sha(bytes), gzip6Sha256: sha(compressed),
  rawLimit: 1829 * 1024, gzip6Limit: 747 * 1024,
  rawHeadroom: 1829 * 1024 - bytes.length,
  gzip6Headroom: 747 * 1024 - compressed.length,
  wasmAbi: manifest.abi_version, sceneVersion: manifest.scene_version,
  painterVersion: manifest.painter_version,
  functionExports: WebAssembly.Module.exports(module).filter(v => v.kind === "function").length,
};
writeFileSync(new URL("module.json", import.meta.url), JSON.stringify(result, null, 2) + "\n");
console.log(JSON.stringify(result));
