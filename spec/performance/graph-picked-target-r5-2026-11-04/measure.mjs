import fs from 'node:fs';
import {createHash} from 'node:crypto';
import {gzipSync} from 'node:zlib';
import assert from 'node:assert/strict';
const sha=b=>createHash('sha256').update(b).digest('hex');
const module=fs.readFileSync('packages/xy-client/dist/xyg-wasm.wasm');
const native=fs.readFileSync('target/release/libxyg_core.so');
const gzip=gzipSync(module,{level:6});
const artifacts={};
for(const dir of ['packages/xy-client/dist','python/xyg/static'])for(const file of ['index.js','standalone.js','wasm-worker.js','wasm-inline-worker.js','xyg-wasm.wasm','xyg-wasm-inline.js','xyg-wasm.manifest.json']){const p=dir+'/'+file; const b=fs.readFileSync(p);artifacts[p]={bytes:b.length,sha256:sha(b)};}
const record={node:process.version,productionProducers:true,native:{bytes:native.length,sha256:sha(native)},rawSource:{sha256:sha(fs.readFileSync('target/wasm32-unknown-unknown/release/xyg_wasm.wasm'))},module:{bytes:module.length,gzip6:gzip.length,sha256:sha(module)},limits:{raw:1882*1024,gzip6:768*1024},headroom:{raw:1882*1024-module.length,gzip6:768*1024-gzip.length},artifacts};
const r='spec/performance/graph-picked-target-r5-2026-11-04/';
fs.writeFileSync(r+'actual-production-artifacts.json',JSON.stringify(record,null,2)+'\n',{flag:'wx'});
fs.writeFileSync(r+'shipping-module.wasm.gz',gzip,{flag:'wx'});
console.log(JSON.stringify(record,null,2));
assert.equal(sha(native),'0deea9029e4a328dc15aa2d86873a203f12b8911e1c89c274f14270b31a3f880');
assert.equal(sha(module),'e3ef33b58820675f4c201a2b81ad23b3665090442210aa22fcee28a269884a96');
assert.ok(record.headroom.raw>=0&&record.headroom.gzip6>=0);
