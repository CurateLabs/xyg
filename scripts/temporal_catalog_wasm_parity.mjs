// Actual raw-WASM/native same-packet Scene oracle. Packaging is a separate gate.
import {readFileSync} from 'node:fs';
import assert from 'node:assert/strict';
import {encodeTemporalScene,temporalSceneCompile} from '../packages/xy-node/src/temporal-scene.js';
const {instance}=await WebAssembly.instantiate(readFileSync(process.argv[2]),{}), e=instance.exports;
for(const kind of ['event','interval','gantt','line','bar','scatter']){
 const lo=9223372036854775707n;
 const packet=encodeTemporalScene({kind,rows:[[lo+1n,lo+4n,1,18446744073709551615n],[lo+5n,null,2,42n]],domain:[lo,lo+10n],timezone:'UTC',title:'LF\nCRLF\r\n'});
 const expected=temporalSceneCompile(packet), h=e.xyg_wasm_instance_new(64*1024*1024);
 assert.notEqual(h,0);assert.equal(e.xyg_wasm_arena_resize(h,packet.byteLength),0);
 new Uint8Array(e.memory.buffer,e.xyg_wasm_arena_ptr(h),packet.byteLength).set(new Uint8Array(packet));
 assert.equal(e.xyg_wasm_temporal_scene_compile(h,1,0,packet.byteLength),0);
 const actual=new Uint8Array(e.memory.buffer,e.xyg_wasm_output_ptr(h),e.xyg_wasm_output_len(h)).slice();
 assert.deepEqual(actual,expected,kind);assert.equal(e.xyg_wasm_instance_dispose(h),0);
}
for(const extent of [1e308,Number.MAX_VALUE]){
 const packet=encodeTemporalScene({kind:'scatter',rows:[[-1n,null,-extent,1n],[0n,null,0,2n],[1n,null,extent,3n]],domain:[-2n,8n],timezone:'UTC'});
 const expected=temporalSceneCompile(packet),h=e.xyg_wasm_instance_new(64*1024*1024);
 assert.notEqual(h,0);assert.equal(e.xyg_wasm_arena_resize(h,packet.byteLength),0);
 new Uint8Array(e.memory.buffer,e.xyg_wasm_arena_ptr(h),packet.byteLength).set(new Uint8Array(packet));
 assert.equal(e.xyg_wasm_temporal_scene_compile(h,1,0,packet.byteLength),0);
 const actual=new Uint8Array(e.memory.buffer,e.xyg_wasm_output_ptr(h),e.xyg_wasm_output_len(h)).slice();
 assert.deepEqual(actual,expected);assert.equal(e.xyg_wasm_instance_dispose(h),0);
}
console.log('8 native/WASM exact Scene byte oracles including LF/CRLF, extreme i64/u64 and opposite finite f64 extremes passed');
for(const kind of ['event','interval','gantt','line','bar','scatter']){
 const rows=Array.from({length:10000},(_,i)=>[BigInt(i),BigInt(i+7),i%5,2n**63n+BigInt(i)]);
 let publication;
 for(const operation of [2,0,1]){
  const packet=encodeTemporalScene({kind,rows,domain:[0n,10000n],timezone:'UTC',dense:true,operation,cell:0,limit:operation===1?256:0,publication});
  const expected=temporalSceneCompile(packet),h=e.xyg_wasm_instance_new(64*1024*1024);
  assert.notEqual(h,0);assert.equal(e.xyg_wasm_arena_resize(h,packet.byteLength),0);
  new Uint8Array(e.memory.buffer,e.xyg_wasm_arena_ptr(h),packet.byteLength).set(new Uint8Array(packet));
  assert.equal(e.xyg_wasm_temporal_scene_compile(h,1,0,packet.byteLength),0);
  const actual=new Uint8Array(e.memory.buffer,e.xyg_wasm_output_ptr(h),e.xyg_wasm_output_len(h)).slice();
  assert.deepEqual(actual,expected,`${kind}:${operation}`);
  if(operation===2)publication=actual.buffer;
  assert.equal(e.xyg_wasm_instance_dispose(h),0);
 }
}
console.log('18 dense native/WASM metadata, Scene and exact member page byte comparisons passed');
