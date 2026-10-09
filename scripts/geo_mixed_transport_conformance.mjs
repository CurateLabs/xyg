#!/usr/bin/env node
// Actual native/WASM shared binary fixture. No private registry insertion.
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {nativeGeoScaleBridge,encodeGeoScaleRequest,decodeGeoScaleReply} from '../packages/xy-node/src/geoscale.js';
import {nativeGeoTileBridge} from '../packages/xy-node/src/geo-tiles.js';
import {nativeGeoSnapshotBridge,encodeGeoSnapshotRequest,decodeGeoSnapshotReply} from '../packages/xy-node/src/geo-snapshot.js';
import {prepareGeoMixedCandidate} from '../packages/xy-node/src/geo-mixed.js';
import {prepareGeoMixedData,encodeGeoMixedRequest,decodeGeoMixedReply} from '../packages/xy-node/src/geo-mixed-wire.js';
import {buildMixedFixture,MIXED_BUDGET} from '../tests/browser/geo_mixed_fixture.mjs';
const {instance}=await WebAssembly.instantiate(await readFile(process.env.XYG_MIXED_WASM??'target/wasm32-unknown-unknown/release/xyg_wasm.wasm'),{}),x=instance.exports,h=x.xyg_wasm_instance_new(MIXED_BUDGET);assert.ok(h);
let sequence=0;
async function call(request,read,family){
 assert.equal(x.xyg_wasm_arena_resize(h,request.byteLength),0);new Uint8Array(x.memory.buffer,x.xyg_wasm_arena_ptr(h)>>>0,request.byteLength).set(new Uint8Array(request));
 const status=x[`xyg_wasm_geo_${family}_${read?'read':'execute'}`](h,++sequence,0,request.byteLength);
 if(status){const detail=new TextDecoder().decode(new Uint8Array(x.memory.buffer,x.xyg_wasm_last_error_ptr(h)>>>0,x.xyg_wasm_last_error_len(h)));throw Error(`WASM ${status}: ${detail}`);}
 return new Uint8Array(x.memory.buffer,x.xyg_wasm_output_ptr(h)>>>0,x.xyg_wasm_output_len(h)).slice().buffer;
}
const wasm={};for(const family of ['scale','tile','snapshot'])wasm[family==='scale'?'source':family]={execute:r=>call(r,false,family),read:r=>call(r,true,family)};
const native={source:nativeGeoScaleBridge(MIXED_BUDGET),tile:nativeGeoTileBridge(MIXED_BUDGET),snapshot:nativeGeoSnapshotBridge(384<<20)};
native.prepareMixed=input=>prepareGeoMixedCandidate(input,{bridge:native.tile});
wasm.prepareMixed=input=>prepareGeoMixedCandidate(input,{bridge:wasm.tile});
let nativeFrame,wasmFrame;
try{
 nativeFrame=await buildMixedFixture(native);wasmFrame=await buildMixedFixture(wasm);
 assert.deepEqual(nativeFrame.scene,wasmFrame.scene);
 assert.throws(()=>wasmFrame.frame.export('html'),/matching snapshot bridge/);
 const hostArtifact=await nativeFrame.frame.export('html');try{assert.ok(new TextDecoder().decode(hostArtifact.bytes).includes('Tiles'));}finally{await hostArtifact.dispose();}
 const a=await nativeFrame.freeze(),b=await wasmFrame.freeze();try{
  assert.deepEqual(new Uint8Array(a.bytes),new Uint8Array(b.bytes));
  for(const format of ['svg','png','pdf','jpeg','webp','html']){
   const artifact=decodeGeoSnapshotReply(await native.snapshot.execute(encodeGeoSnapshotRequest(2,a.handle,{budget:384<<20,format,scale:1,quality:90}))).handle;
   try{const bytes=new Uint8Array(await native.snapshot.read(encodeGeoSnapshotRequest(22,artifact)));assert.ok(bytes.length>32);if(format==='svg'||format==='html'){const text=new TextDecoder().decode(bytes);assert.ok(text.includes('Tiles'));if(format==='html')assert.ok(text.includes("default-src 'none'"));}if(format==='png')assert.deepEqual([...bytes.subarray(0,8)],[137,80,78,71,13,10,26,10]);}
   finally{await native.snapshot.execute(encodeGeoSnapshotRequest(3,artifact));}
  }
  await assert.rejects(wasm.snapshot.execute(encodeGeoSnapshotRequest(2,b.handle,{budget:MIXED_BUDGET,format:'png',scale:1,quality:90})),/UNSUPPORTED/);
 }finally{await a.dispose();await b.dispose();}
 nativeFrame.scene=nativeFrame.descriptorBytes=undefined;await nativeFrame.frame.dispose();nativeFrame=undefined;
 let armed=false,attempts=0;
 const interrupted={read:native.tile.read,execute:request=>{const v=new DataView(request);if(armed&&v.getUint32(8,true)===5){attempts++;if(attempts===1)return Promise.reject(Error('injected pre-Rust disposal failure'));}return native.tile.execute(request);}};
 const retry=await buildMixedFixture({...native,prepareMixed:input=>prepareGeoMixedData(interrupted,input)}),held=[];
 try{
  while(true){try{held.push(decodeGeoMixedReply(await native.tile.execute(encodeGeoMixedRequest({command:6,handle:retry.frame.handle,nonce:retry.frame.nonce,budget:MIXED_BUDGET}))).handle);}catch(error){assert.equal(error.nativeCode,-9);break;}}
  assert.equal(held.length,7);
  const duplicate=()=>native.source.execute(encodeGeoScaleRequest({command:26,handle:held[0],sequence:1n,budget:{processorBytes:MIXED_BUDGET,maxRowsExamined:1000000n,maxReadBytes:128n<<20n,maxChunks:65536,pageRows:4096}}));
  retry.scene=retry.descriptorBytes=undefined;armed=true;const first=retry.frame.dispose(),coalesced=retry.frame.dispose();assert.strictEqual(first,coalesced);await assert.rejects(first,/injected/);assert.equal(attempts,1);assert.throws(()=>retry.frame.data,/disposed/);await assert.rejects(duplicate(),error=>error.nativeCode===-9);
  await retry.frame.dispose();assert.equal(attempts,2);held.push(decodeGeoScaleReply(await duplicate()).handle);assert.equal(held.length,8);await retry.frame.dispose();assert.equal(attempts,2);
 }finally{for(const handle of held)await native.source.execute(encodeGeoScaleRequest({command:10,handle}));await retry.frame.dispose();}
 console.log('mixed transport: native/WASM exact Scene+whole frozen bytes, public Rust provenance, fullu64/i64/stateRevision, disposal-independent source/tile/coord authority, stale/cancel/resource rejection, copy quotas, literal footer, six native exports, WASM unsupported raster and retryable coalesced disposal/exact SourceData quota recovery PASS');
}finally{if(wasmFrame)await wasmFrame.frame.dispose();if(nativeFrame)await nativeFrame.frame.dispose();assert.equal(x.xyg_wasm_instance_dispose(h),0);}
