// Reproduce the diagnostic bytes without waiving the real package gate.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import crypto from 'node:crypto';
import { gzipSync } from 'node:zlib';
import { optimizeWasm } from '../../../js/optimize-wasm.mjs';
const source='target/wasm32-unknown-unknown/release/xyg_wasm.wasm';
const label=process.argv[2];
const output=`target/task-tmp/${label}-optimized.wasm`;
const bytes=optimizeWasm(fs.readFileSync(source));
fs.writeFileSync(output,bytes);
const sha=b=>crypto.createHash('sha256').update(b).digest('hex');
const manifest=JSON.parse(fs.readFileSync('spec/wasm/abi.json','utf8'));
const module=await WebAssembly.compile(bytes);
assert.deepEqual(WebAssembly.Module.imports(module),[]);
const functions=WebAssembly.Module.exports(module).filter(e=>e.kind==='function');
assert.deepEqual(functions.map(e=>e.name).sort(),manifest.exports.map(e=>e.name).sort());
const instance=await WebAssembly.instantiate(module,{});
assert.equal(instance.exports.xyg_wasm_abi_version(),manifest.abi_version);
const gzip=gzipSync(bytes);
const report={node:process.version,source,output,rawBytes:bytes.length,gzip6Bytes:gzip.length,
 sha256:sha(bytes),gzip6Sha256:sha(gzip),rawGate:1512*1024,gzipGate:626*1024,
 rawHeadroom:1512*1024-bytes.length,gzipHeadroom:626*1024-gzip.length,
 imports:0,functions:functions.length,wasmAbi:manifest.abi_version,scene:instance.exports.xyg_wasm_scene_version()};
fs.writeFileSync(`spec/performance/graph-s3-review-repair-2026-10-31/${label}-artifact.json`,JSON.stringify(report,null,2)+'\n');
console.log(JSON.stringify(report,null,2));
