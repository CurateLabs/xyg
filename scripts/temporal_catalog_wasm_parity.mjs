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
console.log('6 native/raw-WASM exact Scene byte oracles including LF/CRLF and extreme i64/u64 passed');
