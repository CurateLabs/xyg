// Actual native/WASM selected authority; raw27 deliberately bypasses the host gate.
import test,{after} from 'node:test';
import assert from 'node:assert/strict';
import {readFile,writeFile} from 'node:fs/promises';
import {createHash} from 'node:crypto';
import {encodeGeoOverviewBuild,GeoOverviewUnsupportedSelected,encodeGeoOverviewRequest,decodeGeoOverviewReply} from '../src/geo-overview.js';
import {nativeGeoScaleBridge,encodeGeoScaleRequest as encode,decodeGeoScaleReply as decode,driveGeoSession,prepareGeoSceneData,encodeGeoScaleStyle} from '../src/geoscale.js';
import {fixture,budget,U64,I64} from './geoscale-fixture.mjs';

const wasmPath=process.env.XYG_GEO_OVERVIEW_WASM,hosts=wasmPath?['native','wasm']:['native'];
async function transport(host){
 if(host==='native')return {bridge:nativeGeoScaleBridge(budget.processorBytes),dispose(){}};
 const {instance}=await WebAssembly.instantiate(await readFile(wasmPath),{}),x=instance.exports,id=x.xyg_wasm_instance_new(budget.processorBytes);assert.ok(id);let seq=0;
 async function call(request,read){assert.equal(x.xyg_wasm_arena_resize(id,request.byteLength),0);new Uint8Array(x.memory.buffer,x.xyg_wasm_arena_ptr(id)>>>0,request.byteLength).set(new Uint8Array(request));const status=x[read?'xyg_wasm_geo_scale_read':'xyg_wasm_geo_scale_execute'](id,++seq,0,request.byteLength);if(status){const error=new Error(new TextDecoder().decode(new Uint8Array(x.memory.buffer,x.xyg_wasm_last_error_ptr(id)>>>0,x.xyg_wasm_last_error_len(id))));error.nativeCode=status===3?-9:status;throw error;}return new Uint8Array(x.memory.buffer,x.xyg_wasm_output_ptr(id)>>>0,x.xyg_wasm_output_len(id)).slice().buffer;}
 return {bridge:{execute:b=>call(b,false),read:b=>call(b,true)},dispose(){assert.equal(x.xyg_wasm_instance_dispose(id),0);}};
}
function extension(command,handle,sequence,payload,query){const b=encode({command:query?5:6,handle,sequence,budget,payload,query});new DataView(b).setUint32(8,command,true);return b;}
const style=()=>encodeGeoScaleStyle({fill:Uint8Array.of(255,0,0,255),stroke:new Uint8Array(4),strokeWidth:0,diameter:6,opacity:1,symbol:0});
const receipts=[];
for(const host of hosts)for(const empty of [false,true])test(`${host} overview rejects ${empty?'empty':'full'} selected authority atomically and before typed dispatch`,async()=>{
 const holder=await transport(host),bridge=holder.bridge,raw=await fixture(bridge),chunk=Uint8Array.from(Buffer.from(raw.chunk,'hex')),manifest=Uint8Array.from(Buffer.from(raw.manifest,'hex')),handles=new Map();let ordinary,selected,source;
 const track=(h,s=0n)=>{handles.set(h,s);return h;},close=async h=>{await bridge.execute(extension(10,h,handles.get(h)));handles.delete(h);};
 try{
  source=track(decode(await bridge.execute(encode({command:4,payload:manifest,budget}))).handle);const readChunk=async()=>chunk,info=(await driveGeoSession(bridge,{handle:source,sequence:0n,budget,readChunk})).source;
  const q={camera:{crs:4326,worldWrap:true,centerX:0,centerY:0,zoom:0,width:800,height:600,bearing:0,pitch:0},reducedKind:0,maxCells:32768,previousDirect:true,sourceDigest:info.digest,generation:info.generation,layerId:U64,cameraRevision:1n,timeRevision:1n,layerRevision:1n,styleRevision:1n,stateRevision:1n,time:{kind:1,instant:I64},maxProjectedVertices:1000000n};
  await bridge.execute(encode({command:5,handle:source,sequence:1n,budget,query:q}));await driveGeoSession(bridge,{handle:source,sequence:1n,budget,readChunk});ordinary=await prepareGeoSceneData(bridge,{handle:source,sequence:1n,budget,style:style()});
  const binding=new Uint8Array(16),bv=new DataView(binding.buffer);bv.setBigUint64(0,U64,true);bv.setBigUint64(8,U64,true);const scope=track(decode(await bridge.execute(extension(32,ordinary.handle,1n,binding))).handle);
  async function issue(){const p=new Uint8Array(empty?24:40),v=new DataView(p.buffer);v.setBigUint64(0,2n,true);p.set([0,255,0,255],8);v.setBigUint64(16,empty?0n:2n,true);if(!empty){v.setBigUint64(24,U64,true);v.setBigUint64(32,U64,true);}return track(decode(await bridge.execute(extension(33,scope,0n,p))).handle);}
  async function begin(state,sequence){const p=new Uint8Array(8);new DataView(p.buffer).setBigUint64(0,state,true);await bridge.execute(extension(35,source,sequence,p,{...q,cameraRevision:sequence,timeRevision:sequence,layerRevision:sequence,styleRevision:sequence,stateRevision:2n}));handles.delete(state);await driveGeoSession(bridge,{handle:source,sequence,budget,readChunk});}
  await begin(await issue(),2n);selected=await prepareGeoSceneData(bridge,{handle:source,sequence:2n,budget,style:style()});assert.notEqual(selected.data.selection,null);assert.equal(selected.data.selection.idCount,empty?0:1);
  const issued=await issue(),old=selected.data.packet.slice(0),payload=new Uint8Array(8);new DataView(payload.buffer).setBigUint64(0,1000000n,true);const request=encodeGeoOverviewRequest({command:27,handle:selected.handle,sequence:2n,budget,payload});
  const rejection=await bridge.execute(request);const receipt=decodeGeoOverviewReply(rejection);assert.equal(receipt.code,17);assert.equal(receipt.handle,selected.handle);assert.equal(receipt.sequence,2n);assert.equal(receipt.ticket,null);assert.deepEqual(await bridge.execute(request),rejection);assert.deepEqual(await bridge.read(encode({command:23,handle:selected.handle})),old);
  assert.deepEqual(await bridge.execute(encodeGeoOverviewRequest({command:27,handle:selected.handle,sequence:2n,budget:{...budget,processorBytes:4096},payload})),rejection);
  // A forged host-side None annotation cannot erase the private Rust owner.
  assert.deepEqual(await bridge.execute(encodeGeoOverviewBuild({handle:selected.handle,data:{selection:null,identity:{sequence:2n}}},{budget,maxVertices:1000000n})),rejection);
  let dispatched=0;const guarded={execute:b=>{dispatched++;return bridge.execute(b);}};assert.throws(()=>guarded.execute(encodeGeoOverviewBuild(selected,{budget,maxVertices:1000000n})),e=>e instanceof GeoOverviewUnsupportedSelected);assert.equal(dispatched,0);
  await begin(issued,3n);assert.equal(selected.data.selection.idCount,empty?0:1);assert.equal(ordinary.data.record(0).featureId,U64);
  const encoded=encodeGeoOverviewBuild(ordinary,{budget,maxVertices:1000000n});assert.deepEqual(encoded,encodeGeoOverviewRequest({command:27,handle:ordinary.handle,sequence:1n,budget,payload}));const build=decodeGeoOverviewReply(await bridge.execute(encoded));track(build.handle,1n);assert.equal(build.code,0);await close(build.handle);
  receipts.push({host,empty,replyHex:Buffer.from(rejection).toString('hex'),priorPacketSha256:createHash('sha256').update(new Uint8Array(old)).digest('hex'),selectedIdCount:selected.data.selection.idCount,typedDispatches:dispatched,lowBudget:4096,issuedStateReused:true,ordinaryFramingIdentical:true});
 }finally{if(selected)await selected.dispose();if(ordinary)await ordinary.dispose();if(handles.has(source))await close(source);for(const [h] of [...handles].reverse())await close(h);holder.dispose();}
});
after(async()=>{if(process.env.XYG_OVERVIEW_SELECTED_REPORT){assert.equal(receipts.length,hosts.length*2);const wasm=wasmPath?await readFile(wasmPath):null,native=await readFile(process.env.XYG_NATIVE_LIB),script=await readFile(new URL(import.meta.url));await writeFile(process.env.XYG_OVERVIEW_SELECTED_REPORT,JSON.stringify({status:'passed',recordedAt:new Date().toISOString(),node:process.version,platform:process.platform,architecture:process.arch,nativeSha256:createHash('sha256').update(native).digest('hex'),wasmSha256:wasm?createHash('sha256').update(wasm).digest('hex'):null,scriptSha256:createHash('sha256').update(script).digest('hex'),cases:receipts,claims:['private Rust selected/Scope rejection, full and empty intent','low-budget rejection before builder credit or source clone','typed pre-dispatch rejection and forged host None cannot bypass Rust','old frame and independent issued State unchanged','ordinary None framing unchanged'],limitations:['counts remain data-space/nonfinal','no overview paint/export/domain-cell membership or massive latency claim']},null,2)+'\n');}});
