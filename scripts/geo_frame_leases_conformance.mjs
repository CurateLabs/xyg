#!/usr/bin/env node
// Actual native383 / real wasm32 immutable-frame duplicate conformance.
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {encodeGeoScaleRequest as encode,decodeGeoScaleReply as decode,encodeGeoChunkRequest,encodeGeoScaleStyle,driveGeoSession,prepareGeoSceneData,nativeGeoScaleBridge,parseGeoHitData,parseGeoMembershipData,parseGeoRowsData} from '../packages/xy-node/src/geoscale.js';
import {encodeGeoSnapshotRequest as rawSnapshotRequest,decodeGeoSnapshotReply as snapshotReply,nativeGeoSnapshotBridge} from '../packages/xy-node/src/geo-snapshot.js';
const snapshotRequest=({command,handle,...options})=>rawSnapshotRequest(command,handle,options);
const budget={processorBytes:128<<20,maxRowsExamined:1000000n,maxReadBytes:128n<<20n,maxChunks:65536,pageRows:4096};
const style=encodeGeoScaleStyle({fill:Uint8Array.of(255,0,0,255),stroke:new Uint8Array(4),strokeWidth:0,diameter:6,opacity:1,symbol:0});
const MAX=0xffffffffffffffffn;
const {instance}=await WebAssembly.instantiate(await readFile(process.env.XYG_FRAME_LEASE_WASM??'target/wasm32-unknown-unknown/release/xyg_wasm.wasm'),{});
const x=instance.exports,h=x.xyg_wasm_instance_new(budget.processorBytes);assert.ok(h);assert.equal(x.xyg_wasm_abi_version(),33);
let sequence=0;
async function call(request,read,family='scale'){
 assert.equal(x.xyg_wasm_arena_resize(h,request.byteLength),0);
 new Uint8Array(x.memory.buffer,x.xyg_wasm_arena_ptr(h)>>>0,request.byteLength).set(new Uint8Array(request));
 const status=x[`xyg_wasm_geo_${family}_${read?'read':'execute'}`](h,++sequence,0,request.byteLength);
 if(status!==0){const detail=new TextDecoder().decode(new Uint8Array(x.memory.buffer,x.xyg_wasm_last_error_ptr(h)>>>0,x.xyg_wasm_last_error_len(h)));throw Error(`WASM geographic status ${status}: ${detail}`);}
 return new Uint8Array(x.memory.buffer,x.xyg_wasm_output_ptr(h)>>>0,x.xyg_wasm_output_len(h)).slice().buffer;
}
const wasm={execute:request=>call(request,false),read:request=>call(request,true)};
const wasmSnapshot={execute:request=>call(request,false,'snapshot'),read:request=>call(request,true,'snapshot')};
function canonical(packet){const b=new Uint8Array(packet.slice(0));b.fill(0,16,24);return b;}
async function run(bridge,snapshots,vertices,isWasm){
 const xyBytes=16*vertices,validAt=64+xyBytes,idAt=(validAt+2+7)&~7,offsetAt=idAt+16;
 const d=new Uint8Array(offsetAt+16),v=new DataView(d.buffer);d.set([88,89,71,68]);
 [1,4,4326,1,0].forEach((n,i)=>v.setUint32(4+4*i,n,true));[2n,BigInt(vertices),3n,0n,0n].forEach((n,i)=>v.setBigUint64(24+8*i,n,true));
 d.set([1,1],validAt);v.setBigUint64(idAt,MAX,true);v.setBigUint64(idAt+8,9007199254740993n,true);[0,vertices/2,vertices].forEach((n,i)=>v.setUint32(offsetAt+4*i,n,true));
 const chunk=await bridge.read(encodeGeoChunkRequest({descriptor:d,rows:2},budget.processorBytes));
 const builder=decode(await bridge.execute(encode({command:1}))).handle;let source,original,retained,rows,rowsData,hit,member,members,frozen;
 try{
 await bridge.execute(encode({command:2,handle:builder,payload:new Uint8Array(chunk)}));await bridge.execute(encode({command:3,handle:builder,generation:MAX}));
 const manifest=await bridge.read(encode({command:21,handle:builder}));source=decode(await bridge.execute(encode({command:4,payload:new Uint8Array(manifest),budget}))).handle;
 const readChunk=async()=>chunk;
 const info=(await driveGeoSession(bridge,{handle:source,sequence:0n,budget,readChunk})).source;
 const query={camera:{crs:4326,worldWrap:true,centerX:0,centerY:0,zoom:0,width:800,height:600,bearing:0,pitch:0},reducedKind:0,maxCells:1,previousDirect:true,sourceDigest:info.digest,generation:info.generation,layerId:MAX,cameraRevision:MAX,timeRevision:MAX,layerRevision:MAX,styleRevision:MAX,stateRevision:MAX,time:{kind:0},maxProjectedVertices:1000000n};
 await bridge.execute(encode({command:5,handle:source,sequence:1n,budget,query}));await driveGeoSession(bridge,{handle:source,sequence:1n,budget,readChunk});
 original=await prepareGeoSceneData(bridge,{handle:source,sequence:1n,budget,style});
 retained=await prepareGeoSceneData(bridge,{command:26,handle:original.handle,sequence:1n,budget});
 assert.deepEqual(canonical(retained.data.packet),canonical(original.data.packet));assert.equal(retained.data.identity.sessionHandle,original.handle);
 const expected=canonical(original.data.packet);await original.dispose();original=undefined;await bridge.execute(encode({command:10,handle:source}));source=undefined;
 assert.equal(retained.data.identity.layerId,MAX);
 const p=new Uint8Array(80);p.set(style);const pv=new DataView(p.buffer);pv.setFloat64(48,400,true);pv.setFloat64(56,300,true);pv.setUint32(76,1,true);
 hit=decode(await bridge.execute(encode({command:14,handle:retained.handle,sequence:1n,budget,payload:p}))).handle;
 const hits=parseGeoHitData(await bridge.read(encode({command:23,handle:hit})));assert.equal(hits.length,1);
 if(vertices>32768){
 assert.equal(hits.record(0).count,BigInt(vertices));const p=new Uint8Array(16),v=new DataView(p.buffer);v.setUint32(0,hits.record(0).cell,true);v.setBigUint64(8,1000000n,true);
 member=decode(await bridge.execute(encode({command:12,handle:retained.handle,sequence:1n,budget,payload:p}))).handle;await driveGeoSession(bridge,{handle:member,sequence:1n,budget,readChunk});
 members=decode(await bridge.execute(encode({command:13,handle:member,sequence:1n,budget}))).handle;
 const page=parseGeoMembershipData(await bridge.read(encode({command:23,handle:members})));assert.equal(page.length,2);assert.equal(page.record(0).featureId,MAX);
 }
 rows=decode(await bridge.execute(encode({command:15,handle:retained.handle,sequence:1n,budget}))).handle;await driveGeoSession(bridge,{handle:rows,sequence:1n,budget,readChunk});
 rowsData=decode(await bridge.execute(encode({command:16,handle:rows,sequence:1n,budget}))).handle;
 const page=parseGeoRowsData(await bridge.read(encode({command:23,handle:rowsData})));assert.equal(page.length,2);assert.equal(page.record(0).featureId,MAX);
 // Freeze and export from retained trusted authority after original/source disposal.
 frozen=snapshotReply(await snapshots.execute(snapshotRequest({command:1,handle:retained.handle,sequence:1n,budget:128<<20}))).handle;
 const frozenBytes=await snapshots.read(snapshotRequest({command:20,handle:frozen}));
 if(isWasm){await assert.rejects(snapshots.execute(snapshotRequest({command:2,handle:frozen,budget:128<<20,format:'png',quality:90,scale:1})),/XYG_GEO_SNAPSHOT_UNSUPPORTED_EXPORT/);}
 else for(const format of ['svg','png','pdf','jpeg','webp','html']){
  const artifact=snapshotReply(await snapshots.execute(snapshotRequest({command:2,handle:frozen,budget:384<<20,format,quality:90,scale:1}))).handle;
  try{const b=new Uint8Array(await snapshots.read(snapshotRequest({command:22,handle:artifact})));assert.ok(b.length>32);if(format==='svg')assert.ok(Buffer.from(b).includes(Buffer.from('<svg')));if(format==='png')assert.deepEqual([...b.slice(0,8)],[137,80,78,71,13,10,26,10]);if(format==='pdf')assert.equal(Buffer.from(b.slice(0,4)).toString(),'%PDF');if(format==='html')assert.ok(Buffer.from(b).toString().toLowerCase().includes('<!doctype html>'));}
  finally{await snapshots.execute(snapshotRequest({command:3,handle:artifact}));}
 }
 // A duplicate has exactly its own two-copy allowance, independent of original.
 await bridge.read(encode({command:23,handle:retained.handle}));await assert.rejects(bridge.read(encode({command:23,handle:retained.handle})));
 return {packet:expected,snapshot:new Uint8Array(frozenBytes)};
 }finally{
 if(frozen!==undefined)await snapshots.execute(snapshotRequest({command:3,handle:frozen}));
 for(const id of [rowsData,rows,members,member,hit])if(id!==undefined)await bridge.execute(encode({command:10,handle:id}));
 if(retained)await retained.dispose();if(original)await original.dispose();if(source!==undefined)await bridge.execute(encode({command:10,handle:source}));await bridge.execute(encode({command:10,handle:builder}));
 }
}
try{for(const vertices of [2,40000])assert.deepEqual(await run(nativeGeoScaleBridge(budget.processorBytes),nativeGeoSnapshotBridge(384<<20),vertices,false),await run(wasm,wasmSnapshot,vertices,true));console.log('frame leases: native383/WASM33 direct+reduced exact bytes, full-u64, source/original disposal, picking, exact membership, full-source rows independent copy quotas, exact frozen snapshots, native six-format exports/WASM unsupported export PASS');}
finally{assert.equal(x.xyg_wasm_instance_dispose(h),0);}
