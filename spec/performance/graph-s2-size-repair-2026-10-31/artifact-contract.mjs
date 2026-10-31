// Diagnostic module contract only; this does not waive the real package gate.
import assert from 'node:assert/strict';
import fs from 'node:fs';
const bytes = fs.readFileSync(process.argv[2] ?? 'target/task-tmp/s2-size-repair/final/optimized.wasm');
const manifest = JSON.parse(fs.readFileSync('spec/wasm/abi.json', 'utf8'));
const module = await WebAssembly.compile(bytes);
assert.deepEqual(WebAssembly.Module.imports(module), []);
const exports = WebAssembly.Module.exports(module).filter(x => x.kind === 'function');
assert.deepEqual(exports.map(x => x.name).sort(), manifest.exports.map(x => x.name).sort());
const instance = await WebAssembly.instantiate(module, {});
assert.equal(instance.exports.xyg_wasm_abi_version(), manifest.abi_version);
assert.equal(instance.exports.xyg_wasm_scene_version(), manifest.scene_version);
console.log(JSON.stringify({imports: 0, functions: exports.length,
  wasmAbi: manifest.abi_version, scene: manifest.scene_version}));
