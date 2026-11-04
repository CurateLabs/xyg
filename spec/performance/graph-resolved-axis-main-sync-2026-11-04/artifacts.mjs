// Re-measure qualified existing artifacts; no build, browser or runtime run.
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import fs from 'node:fs';
import { gzipSync } from 'node:zlib';
const out = new URL('./', import.meta.url);
const historicalPath = 'spec/performance/graph-resolved-axis-live-css-2026-11-03/evidence-final.json';
const historical = JSON.parse(fs.readFileSync(historicalPath));
const sha = data => createHash('sha256').update(data).digest('hex');
const artifacts = {};
for (const [name, expected] of Object.entries(historical.artifacts)) {
  if (name.startsWith('target/task-tmp/')) continue;
  const data = fs.readFileSync(name);
  assert.equal(data.length, expected.bytes, name); assert.equal(sha(data), expected.sha256, name);
  artifacts[name] = { bytes: data.length, sha256: sha(data), qualification: 'reused qualified78/8a artifact; no build or fresh runtime/browser qualification' };
}
for (const name of ['index.js', 'standalone.js', 'wasm-worker.js', 'xyg-wasm.wasm', 'xyg-wasm-inline.js', 'xyg-wasm.manifest.json']) {
  assert.deepEqual(fs.readFileSync(`packages/xy-client/dist/${name}`), fs.readFileSync(`python/xyg/static/${name}`));
}
const wasm = fs.readFileSync('packages/xy-client/dist/xyg-wasm.wasm'), compressed = gzipSync(wasm, { level: 6 });
const previous = JSON.parse(fs.readFileSync('spec/performance/graph-resolved-axis-live-css-2026-11-03/module.json'));
assert.equal(wasm.length, previous.bytes); assert.equal(compressed.length, previous.gzip6Bytes);
assert.equal(sha(compressed), previous.gzip6Sha256);
const native = JSON.parse(fs.readFileSync('spec/abi/xyg-abi.json'));
const manifest = JSON.parse(fs.readFileSync('spec/wasm/abi.json'));
assert.equal(native.abi_version, 398);
assert.equal(manifest.abi_version, 35); assert.equal(manifest.scene_version, 34); assert.equal(manifest.painter_version, 17);
assert.equal(previous.rawLimit, 1838 * 1024); assert.equal(previous.gzip6Limit, 751 * 1024);
const result = { reuse: true, freshBuild: false, freshBrowserRuntimeQualification: false, artifactCommit: null,
  qualificationReceipt: { path: historicalPath, sha256: sha(fs.readFileSync(historicalPath)) },
  artifacts, module: { ...previous, node: process.version, bytes: wasm.length, gzip6Bytes: compressed.length, sha256: sha(wasm), gzip6Sha256: sha(compressed), nativeAbi: native.abi_version },
};
const destination = new URL('artifact-manifest.json', out); assert.ok(!fs.existsSync(destination));
fs.writeFileSync(destination, JSON.stringify(result, null, 2) + '\n');
console.log(JSON.stringify({ artifactCount: Object.keys(artifacts).length, reuse: true, module: result.module }, null, 2));
