import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {FrozenTemporalGraph} from '../src/index.js';
const raw=readFileSync(new URL('../../../spec/performance/temporal-native-render-2026-11-07/artifacts/retained-later.xyfg',import.meta.url));
const edge=readFileSync(new URL('../../../spec/performance/temporal-worker-export-2026-11-07/artifacts/edge-focus-dpr2.xyfg',import.meta.url));
const bundle=readFileSync(new URL('../../xy-client/dist/standalone.js',import.meta.url));
function packet(data,format,{client=new Uint8Array(),operation=1,scale=1}={}) {
 const out=new Uint8Array(64+data.length+client.length),v=new DataView(out.buffer);
 out.set([88,89,70,88]);v.setUint32(4,1,true);v.setUint32(8,operation,true);v.setUint32(12,format,true);v.setFloat64(24,scale,true);v.setBigUint64(32,BigInt(data.length),true);v.setBigUint64(40,BigInt(client.length),true);v.setBigUint64(48,384n*1024n*1024n,true);out.set(data,64);out.set(client,64+data.length);return out;
}
async function wasm() {
 const {instance}=await WebAssembly.instantiate(readFileSync(new URL('../../xy-client/dist/xyg-wasm.wasm',import.meta.url)),{});
 const x=instance.exports;
 return {x,run(h,p){assert.equal(x.xyg_wasm_arena_resize(h,p.length),0);new Uint8Array(x.memory.buffer,x.xyg_wasm_arena_ptr(h),p.length).set(p);const status=x.xyg_wasm_frozen_graph_execute(h,0,p.length);const bytes=Buffer.from(new Uint8Array(x.memory.buffer,x.xyg_wasm_output_ptr(h),x.xyg_wasm_output_len(h)));return {status,bytes};}};
}
test('actual wasm32 frozen Scene/XYPB/SVG/HTML/PNG match public native import at scales1/2',async()=>{
 const {x,run}=await wasm(),h=x.xyg_wasm_instance_new(384*1024*1024);assert.ok(h);
 try {for(const input of [raw,edge]) {
  const source=FrozenTemporalGraph.fromBytes(input),f=source.captureFocus([77,110,159,191]);source.close();
  try {for(const scale of [1,2])for(const [format,code] of [['scene',3],['painter',4],['svg',0],['html',2],['png',1]]) {
   const {status,bytes}=run(h,packet(f.toBytes(),code,{client:code===2?bundle:undefined,scale}));assert.equal(status,0,`${format} scale${scale}`);assert.deepEqual(bytes,Buffer.from(f.export(format,{scale})));
   if(format==='png') {const recovered=run(h,packet(bytes,0,{operation:2}));assert.equal(recovered.status,0);assert.deepEqual(recovered.bytes,Buffer.from(f.toBytes()));}
  }} finally {f.close();}
 }} finally {assert.equal(x.xyg_wasm_instance_dispose(h),0);}
});
test('real PNG malformed carriers and output reservations refuse without poisoning later exports',async()=>{
 const {x,run}=await wasm(),h=x.xyg_wasm_instance_new(368*1024*1024),bounded=x.xyg_wasm_instance_new(16*1024*1024);assert.ok(h);assert.ok(bounded);assert.equal(x.xyg_wasm_instance_new(1),0);
 const source=FrozenTemporalGraph.fromBytes(raw),f=source.captureFocus([77,110,159,191]);source.close();
 try {
  const png=run(h,packet(f.toBytes(),1));assert.equal(png.status,0);assert.ok(png.bytes.length>100);
  const metadata=[];for(let i=8;i<png.bytes.length;){const end=i+png.bytes.readUInt32BE(i)+12;if(png.bytes.toString('ascii',i+4,i+8)==='iTXt')metadata.push(png.bytes.subarray(i,end));i=end;}assert.equal(metadata.length,1);
  const duplicate=Buffer.concat([png.bytes.subarray(0,-12),metadata[0],png.bytes.subarray(-12)]);
  const corrupt=Buffer.from(png.bytes);corrupt[40]^=1;
  for(const data of [new Uint8Array(),png.bytes.subarray(0,-1),duplicate,corrupt]) {
   const bad=run(h,packet(data,0,{operation:2}));assert.equal(bad.status,2);assert.equal(bad.bytes.length,0);
   const good=run(h,packet(f.toBytes(),0));assert.equal(good.status,0);assert.deepEqual(good.bytes,Buffer.from(f.export('svg')));
  }
  const refused=run(bounded,packet(f.toBytes(),1,{scale:8}));assert.equal(refused.status,3);assert.equal(refused.bytes.length,0);
  const good=run(bounded,packet(f.toBytes(),1));assert.equal(good.status,0);assert.deepEqual(good.bytes,png.bytes);
  assert.deepEqual(Buffer.from(f.toBytes()),run(h,packet(png.bytes,0,{operation:2})).bytes);
 } finally {f.close();assert.equal(x.xyg_wasm_instance_dispose(h),0);assert.equal(x.xyg_wasm_instance_dispose(bounded),0);}
});
