// Read-only capture of assets produced by the normal shipping packager.
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import fs from "node:fs";
import path from "node:path";
import vm from "node:vm";
import { fileURLToPath } from "node:url";
import { gzipSync, gunzipSync } from "node:zlib";
import { xyAbiVersion } from "../../../packages/xy-node/src/native.js";

const root = process.cwd();
const output = path.dirname(fileURLToPath(import.meta.url));
const names = ["index.js", "standalone.js", "wasm-worker.js", "xyg-wasm.wasm", "xyg-wasm-inline.js", "xyg-wasm.manifest.json"];
const sha = (data) => createHash("sha256").update(data).digest("hex");
const info = (file) => { const bytes = fs.readFileSync(file); return { bytes: bytes.length, sha256: sha(bytes) }; };
const artifacts = {};
for (const name of names) {
  const client = path.join(root, "packages/xy-client/dist", name);
  const python = path.join(root, "python/xyg/static", name);
  assert.deepEqual(fs.readFileSync(client), fs.readFileSync(python), `paired ${name}`);
  artifacts[`packages/xy-client/dist/${name}`] = info(client);
  artifacts[`python/xyg/static/${name}`] = info(python);
}
for (const name of ["target/release/libxyg_core.so", "target/wasm32-unknown-unknown/release/xyg_wasm.wasm", "packages/xy-client/dist/wasm-inline-worker.js"]) artifacts[name] = info(path.join(root, name));
const bytes = fs.readFileSync(path.join(root, "packages/xy-client/dist/xyg-wasm.wasm"));
const compressed = gzipSync(bytes, { level: 6 });
const policy = fs.readFileSync(path.join(root, "js/package-wasm.mjs"), "utf8");
const rawLimit = Number(policy.match(/const WASM_SIZE_BUDGET_BYTES = (\d+) \* 1024;/)[1]) * 1024;
const gzipLimit = Number(policy.match(/const WASM_GZIP_BUDGET_BYTES = (\d+) \* 1024;/)[1]) * 1024;
assert.ok(bytes.length <= rawLimit && compressed.length <= gzipLimit);
const context = {};
vm.runInNewContext(fs.readFileSync(path.join(root, "packages/xy-client/dist/xyg-wasm-inline.js"), "utf8"), context);
assert.equal(context.__xygInlineWasm.sha256, sha(bytes));
assert.deepEqual(Buffer.from(context.__xygInlineWasm.base64, "base64"), bytes);
assert.equal(context.__xygInlineWasm.classicWorkerSource, fs.readFileSync(path.join(root, "packages/xy-client/dist/wasm-inline-worker.js"), "utf8"));
const metadata = JSON.parse(fs.readFileSync(path.join(root, "packages/xy-client/dist/xyg-wasm.manifest.json")));
assert.equal(metadata.sha256, sha(bytes));
assert.equal(metadata.bytes, bytes.length);
assert.equal(metadata.abi_version, 35); assert.equal(metadata.scene_version, 34); assert.equal(metadata.painter_version, 17);
assert.equal(xyAbiVersion(), 399);
const module = await WebAssembly.compile(bytes);
const previous = await WebAssembly.compile(gunzipSync(fs.readFileSync(path.join(root, "spec/performance/graph-property-default-presentation-2026-11-03/corrected-production-candidate.wasm.gz"))));
assert.deepEqual(WebAssembly.Module.imports(module), []);
assert.deepEqual(WebAssembly.Module.exports(module), WebAssembly.Module.exports(previous));
const instance = await WebAssembly.instantiate(module, {});
assert.equal(instance.exports.xyg_wasm_abi_version(), 35);
assert.equal(instance.exports.xyg_wasm_scene_version(), 34);
const source = JSON.parse(fs.readFileSync(path.join(output, "build-inputs.json")));
for (const [name, expected] of Object.entries(source.files)) assert.equal(info(path.join(root, name)).sha256, expected, `build source ${name}`);
const packageRun = JSON.parse(fs.readFileSync(path.join(output, "shipping-package.command.json")));
assert.equal(packageRun.exit, 0);
const report = {
  provenance: "Actual production release targets and normal shipping packager, exit 0; no manually staged candidate assets",
  source_sha256: source.source_sha256,
  native_abi: xyAbiVersion(), wasm_abi: 35, scene: 34, painter: 17,
  optimized: { bytes: bytes.length, sha256: sha(bytes) },
  gzip6: { bytes: compressed.length, sha256: sha(compressed) },
  limits: { raw: rawLimit, gzip6: gzipLimit },
  headroom: { raw: rawLimit - bytes.length, gzip6: gzipLimit - compressed.length },
  growth_over_p1: { raw: bytes.length - 1881508, gzip6: compressed.length - 768134 },
  unchanged_reviewed_candidate: bytes.length === 1922561 && compressed.length === 783148,
  no_imports: true, export_set_exact_reviewed_candidate: true,
  export_count: WebAssembly.Module.exports(module).length,
  paired_assets_manifests_inline_payload_and_worker_exact: true,
  package_accepted: true, artifacts,
};
fs.writeFileSync(path.join(output, "shipping-artifacts.json"), JSON.stringify(report, null, 2) + "\n", { flag: "wx" });
fs.writeFileSync(path.join(output, "shipping-module.wasm.gz"), compressed, { flag: "wx" });
console.log(JSON.stringify(report, null, 2));
