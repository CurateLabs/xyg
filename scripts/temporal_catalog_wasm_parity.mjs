// Actual raw-WASM/native same-packet Scene oracle. Packaging is a separate gate.
import {readFileSync} from 'node:fs';
import assert from 'node:assert/strict';
import {encodeTemporalScene,temporalSceneCompile} from '../packages/xy-node/src/temporal-scene.js';
const {instance}=await WebAssembly.instantiate(readFileSync(process.argv[2]),{}), e=instance.exports;
const windowFixture=JSON.parse(readFileSync(new URL('../tests/fixtures/temporal/line-window-edges.json',import.meta.url)));
for(const fixture of windowFixture.cases){
 const packet=encodeTemporalScene({kind:'line',rows:fixture.times.map((t,i)=>[t===null?null:BigInt(t),null,fixture.values[i],BigInt(i+42)]),domain:fixture.domain.map(BigInt),timezone:'UTC',width:windowFixture.width,height:windowFixture.height,strokeWidth:4});
 const expected=temporalSceneCompile(packet),h=e.xyg_wasm_instance_new(64*1024*1024);
 try{assert.notEqual(h,0);assert.equal(e.xyg_wasm_arena_resize(h,packet.byteLength),0);new Uint8Array(e.memory.buffer,e.xyg_wasm_arena_ptr(h),packet.byteLength).set(new Uint8Array(packet));assert.equal(e.xyg_wasm_temporal_scene_compile(h,1,0,packet.byteLength),0);assert.deepEqual(new Uint8Array(e.memory.buffer,e.xyg_wasm_output_ptr(h),e.xyg_wasm_output_len(h)).slice(),expected,fixture.name);}finally{assert.equal(e.xyg_wasm_instance_dispose(h),0);}
}
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
console.log('16 native/WASM exact Scene byte oracles including line-window clipping, null gaps, LF/CRLF, extreme i64/u64 and opposite finite f64 extremes passed');

// Opaque owner handles are runtime-local; every other control/output byte agrees.
for(const kind of ['event','interval','gantt','line','bar','scatter']){
 const {instance}=await WebAssembly.instantiate(readFileSync(process.argv[2]),{}), w=instance.exports;
 const h=w.xyg_wasm_instance_new(64*1024*1024);let sequence=1;
 const command=(op,owner,revision,source)=>{const b=new ArrayBuffer(64+(source?.byteLength??0)),v=new DataView(b);new Uint8Array(b).set([88,89,84,74]);v.setUint32(4,1,true);v.setUint32(8,op,true);v.setBigUint64(16,owner,true);v.setBigUint64(24,revision,true);if(source)new Uint8Array(b,64).set(new Uint8Array(source));return b;};
 const wasm=packet=>{assert.equal(w.xyg_wasm_arena_resize(h,packet.byteLength),0);new Uint8Array(w.memory.buffer,w.xyg_wasm_arena_ptr(h),packet.byteLength).set(new Uint8Array(packet));const status=w.xyg_wasm_temporal_scene_compile(h,sequence++,0,packet.byteLength);if(status)return {status};return new Uint8Array(w.memory.buffer,w.xyg_wasm_output_ptr(h),w.xyg_wasm_output_len(h)).slice();};
 const opened=command(0,0n,0n),na=temporalSceneCompile(opened),wa=wasm(opened),nh=new DataView(na.buffer).getBigUint64(16,true),wh=new DataView(wa.buffer).getBigUint64(16,true);
 const compare=(op,revision,source)=>{const n=temporalSceneCompile(command(op,nh,revision,source)),a=wasm(command(op,wh,revision,source));assert.ok(a instanceof Uint8Array);if(op!==3){n.fill(0,16,24);a.fill(0,16,24);}assert.deepEqual(a,n,`${kind}:command${op}`);return n;};
 const source=encodeTemporalScene({kind,rows:Array.from({length:10000},(_,i)=>[BigInt(i),BigInt(i+7),i%5,2n**63n+BigInt(i)]),domain:[0n,10000n],timezone:'UTC',dense:true});
 compare(1,1n,source);let ack;do{ack=compare(2,1n);}while(new DataView(ack.buffer).getUint32(8,true)===0);
 const accepted=compare(3,1n);assert.deepEqual(accepted,temporalSceneCompile(source));
 compare(1,2n,source);compare(2,2n);compare(4,2n);assert.deepEqual(compare(3,1n),accepted);
 compare(5,2n);assert.equal(w.xyg_wasm_instance_dispose(h),0);
}
console.log('six stepped native/WASM control, scan, atomic read, cancellation and accepted-state packet oracles passed (owner handles normalized)');

// Every occupied cell in all eight authored clipping counterexamples: observations
// and supports remain separate exact packets under the public binary compiler.
let supportPages=0;
for(const fixture of windowFixture.cases){
 const input={kind:'line',rows:fixture.times.map((t,i)=>[t===null?null:BigInt(t),null,fixture.values[i],BigInt(i+42)]),domain:fixture.domain.map(BigInt),timezone:'UTC',width:windowFixture.width,height:windowFixture.height,dense:true};
 const h=e.xyg_wasm_instance_new(64*1024*1024);let sequence=1;
 const compare=packet=>{const expected=temporalSceneCompile(packet);assert.equal(e.xyg_wasm_arena_resize(h,packet.byteLength),0);new Uint8Array(e.memory.buffer,e.xyg_wasm_arena_ptr(h),packet.byteLength).set(new Uint8Array(packet));assert.equal(e.xyg_wasm_temporal_scene_compile(h,sequence++,0,packet.byteLength),0);const actual=new Uint8Array(e.memory.buffer,e.xyg_wasm_output_ptr(h),e.xyg_wasm_output_len(h)).slice();assert.deepEqual(actual,expected,fixture.name);return actual;};
 try{const metadata=compare(encodeTemporalScene({...input,operation:2})),v=new DataView(metadata.buffer);for(let at=64;at<metadata.length;at+=72){const cell=Number(v.getBigUint64(at,true));for(const operation of [1,3]){compare(encodeTemporalScene({...input,operation,cell,limit:256,publication:metadata.buffer}));supportPages++;}}}finally{assert.equal(e.xyg_wasm_instance_dispose(h),0);}
}
console.log(`${supportPages} exact clipped observation/support native/WASM page comparisons passed across eight authored counterexamples`);
