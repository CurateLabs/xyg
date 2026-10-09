// Actual packaged wasm32/native retained source and snapshot byte contracts.
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import test from 'node:test';
import {fixture,budget} from './geoscale-fixture.mjs';
import {encodeGeoScaleRequest,decodeGeoScaleReply,driveGeoSession,driveGeoIndexSession,prepareGeoSceneData,prepareGeoAuxData,parseGeoRowsData} from '../src/geoscale.js';
import {encodeGeoSnapshotRequest,decodeGeoSnapshotReply,nativeGeoSnapshotBridge} from '../src/geo-snapshot.js';
const artifact=new URL('../../xy-client/dist/xyg-wasm.wasm',import.meta.url);
async function freeze(bridge,frame){
 const frozen=decodeGeoSnapshotReply(await bridge.execute(encodeGeoSnapshotRequest(1,frame.handle,{sequence:frame.data.identity.sequence,budget:budget.processorBytes}))).handle;
 let packet;
 try{packet=await bridge.read(encodeGeoSnapshotRequest(20,frozen));assert.equal(new TextDecoder().decode(new Uint8Array(packet,0,4)),'XYGX');return Buffer.from(packet).toString('hex');}
 finally{packet=undefined;await bridge.execute(encodeGeoSnapshotRequest(3,frozen));}
}
async function rows(frame,{bridge,readChunk}){
 const b={...budget,pageRows:1},packets=[];let owner=frame.handle,prior=null;
 try{for(;;){
  const session=decodeGeoScaleReply(await bridge.execute(encodeGeoScaleRequest({command:15,handle:owner,sequence:frame.data.identity.sequence,budget:b}))).handle;
  if(prior){await prior.dispose();prior=null;}
  try{
   await driveGeoSession(bridge,{handle:session,sequence:frame.data.identity.sequence,budget:b,readChunk});
   prior=await prepareGeoAuxData(bridge,{command:16,handle:session,sequence:frame.data.identity.sequence,budget:b},parseGeoRowsData);
  }finally{await bridge.execute(encodeGeoScaleRequest({command:10,handle:session}));}
  const packet=prior.data.packet.slice(),v=new DataView(packet);
  assert.equal(prior.data.length,1);assert.equal(v.getBigUint64(144,true),0xffffffffffffffffn);
  // Only process-local owner handles differ; every semantic byte is exact.
  v.setBigUint64(16,0n,true);v.setBigUint64(80,0n,true);
  packets.push(Buffer.from(packet).toString('hex'));
  if(!prior.data.hasNext)break;owner=prior.handle;
 }}finally{if(prior)await prior.dispose();}
 assert.equal(packets.length,2);return packets;
}
async function indexed(frame,{bridge,readChunk,query,style},snapshotBridge){
 const pages=new Map(),payload=new Uint8Array(16),v=new DataView(payload.buffer);v.setUint32(0,16,true);v.setBigUint64(8,1000000n,true);
 const h=decodeGeoScaleReply(await bridge.execute(encodeGeoScaleRequest({command:17,handle:frame.handle,sequence:1n,budget,payload}))).handle;let session,owned;
 try{
  const built=await driveGeoIndexSession(bridge,{handle:h,sequence:1n,budget,readChunk,writePage:async(t,b)=>pages.set(t.page,b.slice())});assert.equal(built.code,11);
  session=decodeGeoScaleReply(await bridge.execute(encodeGeoScaleRequest({command:18,handle:h,sequence:2n,budget,query}))).handle;
  const completed=await driveGeoIndexSession(bridge,{handle:session,sequence:2n,budget,readPage:async t=>pages.get(t.page)});assert.equal(completed.code,12);
  owned=await prepareGeoSceneData(bridge,{command:19,handle:session,sequence:2n,budget,style});
  const packet=owned.data.packet.slice(),pv=new DataView(packet);pv.setBigUint64(16,0n,true);pv.setBigUint64(24,0n,true);
  const canonical=frame.data.packet.slice(),cv=new DataView(canonical);cv.setBigUint64(16,0n,true);cv.setBigUint64(24,0n,true);assert.deepEqual(new Uint8Array(packet),new Uint8Array(canonical));
  return {packet:Buffer.from(packet).toString('hex'),stats:completed.indexStats,rows:await rows(owned,{bridge,readChunk}),frozen:await freeze(snapshotBridge,owned)};
 }finally{if(owned)await owned.dispose();if(session)await bridge.execute(encodeGeoScaleRequest({command:10,handle:session}));await bridge.execute(encodeGeoScaleRequest({command:10,handle:h}));}
}
test('packaged ABI33 retained source and frozen snapshot equal actual native bytes',async()=>{
 let expectedSnapshot,expectedRows,expectedIndex;const expected=await fixture(undefined,async(frame,source)=>{expectedSnapshot=await freeze(nativeGeoSnapshotBridge(budget.processorBytes),frame);expectedRows=await rows(frame,source);expectedIndex=await indexed(frame,source,nativeGeoSnapshotBridge(budget.processorBytes));});
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
 const actual=await fixture(bridge('scale'),async(frame,source)=>{
  assert.equal(await freeze(bridge('snapshot'),frame),expectedSnapshot);
  assert.deepEqual(await rows(frame,source),expectedRows);
  assert.deepEqual(await indexed(frame,source,bridge('snapshot')),expectedIndex);
  const snapshot=decodeGeoSnapshotReply(await bridge('snapshot').execute(encodeGeoSnapshotRequest(1,frame.handle,{sequence:frame.data.identity.sequence,budget:budget.processorBytes}))).handle;
  try{await assert.rejects(bridge('snapshot').execute(encodeGeoSnapshotRequest(2,snapshot,{budget:budget.processorBytes,format:'png'})),error=>error.message==='XYG_GEO_SNAPSHOT_UNSUPPORTED_EXPORT');}
  finally{await bridge('snapshot').execute(encodeGeoSnapshotRequest(3,snapshot));}
  assert.equal(x.xyg_wasm_geo_frame_prepare(h,++sequence,frame.handle,1n),0);
  const p=new Uint8Array(x.memory.buffer,x.xyg_wasm_output_ptr(h)>>>0,x.xyg_wasm_output_len(h));assert.equal(new TextDecoder().decode(p.subarray(0,4)),'XYPB');assert.equal(new DataView(p.buffer,p.byteOffset).getUint32(4,true),15);
 });assert.deepEqual(actual,expected);
 }finally{assert.equal(x.xyg_wasm_instance_dispose(h),0);}
});
