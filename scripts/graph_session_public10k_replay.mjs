// Exact full-result replay of browser commands; test-only, no product policy.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import {createHash} from 'node:crypto';
import * as native from '../packages/xy-node/src/native.js';
import {decodeContainer} from '../packages/xy-node/src/graphforge-container.js';
import {ptr,nativeComplete,wasmCall} from '../packages/xy-node/test/graph-session-replay-helpers.mjs';
const report=JSON.parse(fs.readFileSync(process.argv[2],'utf8'));
const {instance}=await WebAssembly.instantiate(fs.readFileSync('packages/xy-client/dist/xyg-wasm.wasm'),{}),x=instance.exports;
for(const view of report.views){
 const handle=new BigUint64Array(1),wasm=x.xyg_wasm_instance_new(384*1024*1024);
 try {
  for(const record of view.replay){
   const bytes=Buffer.from(record.request,'base64'),parts=decodeContainer(bytes,'XYGI'),h=parts.get('header.u64#0').value;
   const op=record.operation;
   if(op===19){const d=parts.get('document.bytes#0').value;assert.equal(native.xyGraphforgeSessionCreate(ptr(d),BigInt(d.length),ptr(bytes),BigInt(bytes.length),h[0],h[1],native.pointer(handle,'uint64_t *')),0);}
   const compare=b=>{assert.equal(b.length,record.replyBytes);assert.equal(createHash('sha256').update(b).digest('hex'),record.replySha256);};
   if(op!==19)compare(nativeComplete(op===21?native.xyGraphforgeSessionRender:native.xyGraphforgeSessionInteract,handle[0],bytes));
   const reply=wasmCall(x,wasm,op===19?'xyg_wasm_graphforge_session_open':op===21?'xyg_wasm_graphforge_session_render':'xyg_wasm_graphforge_session_interact',bytes);assert.equal(reply.status,0);compare(reply.output);
   const gpu=decodeContainer(reply.output,'XYGR').get('gpu.header.u32#0')?.value;
   if(gpu&&view.sourceNodes===10000){assert.equal(gpu[2],10000,'every primary publication keeps all 10k nodes');assert.equal(gpu[3],10000,'every primary publication keeps all 10k edges');}
  }
  console.log(JSON.stringify({id:view.id,commands:view.replay.length,linearPeak:x.memory.buffer.byteLength,comparison:'full XYGR SHA256: browser/native/WASM'}));
 }finally{assert.equal(native.xyGraphforgeSessionDestroy(handle[0]),0);assert.equal(x.xyg_wasm_graphforge_session_close(wasm),0);assert.equal(x.xyg_wasm_instance_dispose(wasm),0);}
}
