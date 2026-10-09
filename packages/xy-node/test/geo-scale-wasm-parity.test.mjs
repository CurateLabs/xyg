// Actual packaged wasm32/native retained source and snapshot byte contracts.
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import test from 'node:test';
import {fixture,budget} from './geoscale-fixture.mjs';
import {encodeGeoSnapshotRequest,decodeGeoSnapshotReply,nativeGeoSnapshotBridge} from '../src/geo-snapshot.js';
const artifact=new URL('../../xy-client/dist/xyg-wasm.wasm',import.meta.url);
async function freeze(bridge,frame){
 const frozen=decodeGeoSnapshotReply(await bridge.execute(encodeGeoSnapshotRequest(1,frame.handle,{sequence:1n,budget:budget.processorBytes}))).handle;
 let packet;
 try{packet=await bridge.read(encodeGeoSnapshotRequest(20,frozen));assert.equal(new TextDecoder().decode(new Uint8Array(packet,0,4)),'XYGX');return Buffer.from(packet).toString('hex');}
 finally{packet=undefined;await bridge.execute(encodeGeoSnapshotRequest(3,frozen));}
}
test('packaged ABI33 retained source and frozen snapshot equal actual native bytes',async()=>{
 let expectedSnapshot;const expected=await fixture(undefined,async frame=>{expectedSnapshot=await freeze(nativeGeoSnapshotBridge(budget.processorBytes),frame);});
 const{instance}=await WebAssembly.instantiate(readFileSync(artifact),{}),x=instance.exports,h=x.xyg_wasm_instance_new(budget.processorBytes);let sequence=0;
 assert.ok(h);assert.equal(x.xyg_wasm_geo_transport_acquire(h),0);
 function call(namespace,read,request){
  assert.equal(x.xyg_wasm_arena_resize(h,request.byteLength),0);new Uint8Array(x.memory.buffer,x.xyg_wasm_arena_ptr(h)>>>0,request.byteLength).set(new Uint8Array(request));
  const status=x[`xyg_wasm_geo_${namespace}_${read?'read':'execute'}`](h,++sequence,0,request.byteLength);
  assert.equal(x.xyg_wasm_arena_len(h),0);
  if(status){const detail=new TextDecoder().decode(new Uint8Array(x.memory.buffer,x.xyg_wasm_last_error_ptr(h)>>>0,x.xyg_wasm_last_error_len(h)));const error=new Error(detail);error.nativeCode=detail.endsWith('_RESOURCE_LIMIT')?-9:status;throw error;}
  return new Uint8Array(x.memory.buffer,x.xyg_wasm_output_ptr(h)>>>0,x.xyg_wasm_output_len(h)).slice().buffer;
 }
 const bridge=ns=>({async execute(request){return call(ns,false,request);},async read(request){return call(ns,true,request);}});
 try{
 const actual=await fixture(bridge('scale'),async frame=>{
  assert.equal(await freeze(bridge('snapshot'),frame),expectedSnapshot);
  const snapshot=decodeGeoSnapshotReply(await bridge('snapshot').execute(encodeGeoSnapshotRequest(1,frame.handle,{sequence:1n,budget:budget.processorBytes}))).handle;
  try{await assert.rejects(bridge('snapshot').execute(encodeGeoSnapshotRequest(2,snapshot,{budget:budget.processorBytes,format:'png'})),error=>error.message==='XYG_GEO_SNAPSHOT_UNSUPPORTED_EXPORT');}
  finally{await bridge('snapshot').execute(encodeGeoSnapshotRequest(3,snapshot));}
  assert.equal(x.xyg_wasm_geo_frame_prepare(h,++sequence,frame.handle,1n),0);
  const p=new Uint8Array(x.memory.buffer,x.xyg_wasm_output_ptr(h)>>>0,x.xyg_wasm_output_len(h));assert.equal(new TextDecoder().decode(p.subarray(0,4)),'XYPB');assert.equal(new DataView(p.buffer,p.byteOffset).getUint32(4,true),15);
 });assert.deepEqual(actual,expected);
 }finally{assert.equal(x.xyg_wasm_instance_dispose(h),0);}
});
