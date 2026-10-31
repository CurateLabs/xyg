// Inspect only the real producer's outputs: no diagnostic copy or budget waiver.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import crypto from 'node:crypto';
import { gzipSync } from 'node:zlib';
const receipt = new URL('./', import.meta.url);
const sha = b => crypto.createHash('sha256').update(b).digest('hex');
const files = {};
const assets = ['xyg-wasm.wasm', 'xyg-wasm-inline.js', 'xyg-wasm.manifest.json'];
for (const name of assets) {
  const browser = fs.readFileSync(`packages/xy-client/dist/${name}`);
  const python = fs.readFileSync(`python/xyg/static/${name}`);
  assert.deepEqual(browser, python, `${name} paired copies`);
  for (const location of ['packages/xy-client/dist', 'python/xyg/static'])
    files[`${location}/${name}`] = { bytes: browser.length, sha256: sha(browser) };
}
const bytes = fs.readFileSync('packages/xy-client/dist/xyg-wasm.wasm');
const gzip = gzipSync(bytes);
const module = await WebAssembly.compile(bytes);
assert.deepEqual(WebAssembly.Module.imports(module), []);
const manifest = JSON.parse(fs.readFileSync('spec/wasm/abi.json'));
const functions = WebAssembly.Module.exports(module).filter(e => e.kind === 'function');
assert.deepEqual(functions.map(e => e.name).sort(), manifest.exports.map(e => e.name).sort());
const instance = await WebAssembly.instantiate(module, {});
assert.equal(instance.exports.xyg_wasm_abi_version(), manifest.abi_version);
assert.equal(instance.exports.xyg_wasm_scene_version(), manifest.scene_version);
const metadata = JSON.parse(fs.readFileSync('packages/xy-client/dist/xyg-wasm.manifest.json'));
assert.equal(metadata.sha256, sha(bytes));
assert.equal(metadata.bytes, bytes.length);
const report = {
  node: process.version, source: 'target/wasm32-unknown-unknown/release/xyg_wasm.wasm',
  sourceSha256: sha(fs.readFileSync('target/wasm32-unknown-unknown/release/xyg_wasm.wasm')),
  rawBytes: bytes.length, gzip6Bytes: gzip.length, sha256: sha(bytes), gzip6Sha256: sha(gzip),
  rawGate: 1513 * 1024, gzipGate: 626 * 1024,
  rawHeadroom: 1513 * 1024 - bytes.length, gzipHeadroom: 626 * 1024 - gzip.length,
  imports: 0, functions: functions.length, exports: functions.map(e => e.name).sort(),
  wasmAbi: manifest.abi_version, scene: manifest.scene_version, painter: manifest.painter_version,
  artifactCommit: null, sourceManifest: 'source-final-build.json',
  sourceManifestSha256: sha(fs.readFileSync(new URL('source-final-build.json', receipt))),
  files, metadata,
};
assert(report.rawHeadroom >= 0 && report.gzipHeadroom >= 0);
fs.writeFileSync(new URL('artifact.json', receipt), JSON.stringify(report, null, 2) + '\n');
fs.writeFileSync(new URL('packaged-wasm.manifest.json', receipt), JSON.stringify(metadata, null, 2) + '\n');
console.log(JSON.stringify(report, null, 2));
