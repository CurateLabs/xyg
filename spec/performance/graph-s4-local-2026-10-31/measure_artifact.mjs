// Exact Node22 measurements; failed gates are evidence, never an allowance.
import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {createHash} from 'node:crypto';
import {gzipSync} from 'node:zlib';
import assert from 'node:assert/strict';
const receipt=path.dirname(fileURLToPath(import.meta.url)),root=path.resolve(receipt,'../../..');
const file=path.join(root,'target/task-tmp/s4-diagnostic-assets/packages/xy-client/dist/xyg-wasm.wasm');
const bytes=fs.readFileSync(file),packed=gzipSync(bytes),manifest=JSON.parse(fs.readFileSync(path.join(root,'spec/wasm/abi.json')));
const module=new WebAssembly.Module(bytes),imports=WebAssembly.Module.imports(module),exports=WebAssembly.Module.exports(module);
assert.equal(imports.length,0);assert.deepEqual(exports.filter(x=>x.kind==='function').map(x=>x.name).sort(),manifest.exports.map(x=>x.name).sort());
const instance=await WebAssembly.instantiate(module,{});assert.equal(instance.exports.xyg_wasm_abi_version(),35);assert.equal(instance.exports.xyg_wasm_scene_version(),34);
const rawGate=1513*1024,gzipGate=626*1024;
const record={artifactCommit:null,scope:'diagnostic optimized module; shipping producer FAIL',file,node:process.version,rawBytes:bytes.length,gzip6Bytes:packed.length,sha256:createHash('sha256').update(bytes).digest('hex'),gzip6Sha256:createHash('sha256').update(packed).digest('hex'),gates:{raw:rawGate,gzip6:gzipGate},overGate:{raw:bytes.length-rawGate,gzip6:packed.length-gzipGate},deltaFromAcceptedS3:{raw:bytes.length-1548390,gzip6:packed.length-640709},imports,exports,abi:35,scene:34,painter:17};
fs.writeFileSync(path.join(receipt,'artifact.json'),JSON.stringify(record,null,2)+'\n');console.log(JSON.stringify(record,null,2));
