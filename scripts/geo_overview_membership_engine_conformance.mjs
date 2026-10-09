#!/usr/bin/env node
// Actual legacy projected-membership packets before/after the shared driver extraction.
// New overview membership remains engine-only; this script grants no domain/painter authority.
import assert from 'node:assert/strict';
import {readFile,writeFile} from 'node:fs/promises';
import {createHash} from 'node:crypto';
import {gzipSync} from 'node:zlib';
import {encodeGeoScaleRequest as encode,decodeGeoScaleReply as decode,encodeGeoChunkRequest,
 encodeGeoScaleStyle,driveGeoSession,prepareGeoSceneData,nativeGeoScaleBridge,parseGeoMembershipData}
 from '../packages/xy-node/src/geoscale.js';
const sha=b=>createHash('sha256').update(b).digest('hex');
const wasmPath=process.env.XYG_MEMBERSHIP_WASM??new URL('../packages/xy-client/dist/xyg-wasm.wasm',import.meta.url);
const wasmBytes=await readFile(wasmPath),nativePath=process.env.XYG_NATIVE_LIB;
assert.ok(nativePath,'XYG_NATIVE_LIB must pin the actual native artifact');
const nativeBytes=await readFile(nativePath);
const {instance}=await WebAssembly.instantiate(wasmBytes,{}),x=instance.exports;
assert.equal(x.xyg_wasm_abi_version(),33);
const budget={processorBytes:128<<20,maxRowsExamined:1000000n,maxReadBytes:128n<<20n,maxChunks:65536,pageRows:4};
const h=x.xyg_wasm_instance_new(budget.processorBytes);assert.ok(h);let transport=0;
const wasm={async execute(request){return call(request,false);},async read(request){return call(request,true);}};
function call(request,read){
 assert.equal(x.xyg_wasm_arena_resize(h,request.byteLength),0);
 new Uint8Array(x.memory.buffer,x.xyg_wasm_arena_ptr(h)>>>0,request.byteLength).set(new Uint8Array(request));
 const status=x[`xyg_wasm_geo_scale_${read?'read':'execute'}`](h,++transport,0,request.byteLength);
 if(status!==0){const error=new TextDecoder().decode(new Uint8Array(x.memory.buffer,x.xyg_wasm_last_error_ptr(h)>>>0,x.xyg_wasm_last_error_len(h)));throw Error(`WASM geographic status${status}: ${error}`);}
 return new Uint8Array(x.memory.buffer,x.xyg_wasm_output_ptr(h)>>>0,x.xyg_wasm_output_len(h)).slice().buffer;
}
const MAX=0xffffffffffffffffn,MIN=-0x8000000000000000n,END=0x7fffffffffffffffn;
const ids=[MAX,MAX,0n,1n<<63n,9007199254740993n,7n,8n];
function descriptor(){
 const vertices=45000,validAt=64+vertices*16,idAt=(validAt+7+7)&~7,offsetAt=idAt+7*8;
 const b=new Uint8Array(offsetAt+8*4),v=new DataView(b.buffer);b.set([88,89,71,68]);
 [1,4,4326,1,0].forEach((n,i)=>v.setUint32(4+4*i,n,true));
 [7n,BigInt(vertices),8n,0n,0n].forEach((n,i)=>v.setBigUint64(24+8*i,n,true));
 b.set([1,1,0,1,1,1,1],validAt);ids.forEach((id,i)=>v.setBigUint64(idAt+i*8,id,true));
 [0,9000,18000,18000,27000,36000,36000,45000].forEach((n,i)=>v.setUint32(offsetAt+4*i,n,true));return b;
}
const profiles=[
 {name:'All',time:{kind:0},rows:[0,1,3,4,6,7,8,10,11,13]},
 {name:'InstantMIN',time:{kind:1,instant:MIN},rows:[0,4,7,11]},
 {name:'Instant0',time:{kind:1,instant:0n},rows:[1,4,8,11]},
 {name:'Instant10',time:{kind:1,instant:10n},rows:[3,4,10,11]},
 {name:'WindowHalfOpen',time:{kind:2,start:-1n,end:11n},rows:[0,1,3,4,7,8,10,11]},
];
async function run(bridge,profile){
 const chunk=await bridge.read(encodeGeoChunkRequest({descriptor:descriptor(),rows:7,intervals:{
  starts:new BigInt64Array([MIN,0n,0n,10n,0n,0n,END-1n]),ends:new BigInt64Array([0n,10n,0n,END,0n,0n,END]),
  startValidity:Uint8Array.of(1,1,0,1,0,0,1),endValidity:Uint8Array.of(1,1,0,1,0,0,1)}},budget.processorBytes));
 const builder=decode(await bridge.execute(encode({command:1}))).handle;let source,frame;
 const packets=[],rawHashes=[],all=[];
 try{
  for(let i=0;i<2;i++)await bridge.execute(encode({command:2,handle:builder,payload:chunk}));
  await bridge.execute(encode({command:3,handle:builder,generation:77n}));const manifest=await bridge.read(encode({command:21,handle:builder}));
  source=decode(await bridge.execute(encode({command:4,payload:manifest,budget}))).handle;
  const readChunk=async ticket=>{assert.equal(ticket.encodedBytes,chunk.byteLength);assert.equal(ticket.generation,77n);assert.ok(ticket.chunkIndex===0||ticket.chunkIndex===1);return chunk;};
  const info=(await driveGeoSession(bridge,{handle:source,sequence:0n,budget,readChunk})).source;
  const query={camera:{crs:4326,worldWrap:true,centerX:0,centerY:0,zoom:0,width:800,height:600,bearing:0,pitch:0},
   reducedKind:0,maxCells:1,previousDirect:true,sourceDigest:info.digest,generation:info.generation,layerId:MAX,
   cameraRevision:5n,timeRevision:6n,layerRevision:7n,styleRevision:8n,stateRevision:9n,time:profile.time,maxProjectedVertices:1000000n};
  await bridge.execute(encode({command:5,handle:source,sequence:1n,budget,query}));await driveGeoSession(bridge,{handle:source,sequence:1n,budget,readChunk});
  frame=await prepareGeoSceneData(bridge,{handle:source,sequence:1n,budget,style:encodeGeoScaleStyle({fill:Uint8Array.of(255,0,0,255),stroke:new Uint8Array(4),strokeWidth:0,diameter:6,opacity:1,symbol:0})});
  await bridge.execute(encode({command:10,handle:source}));source=undefined;
  let cursor=null;
  do{
   const payload=new Uint8Array(16+(cursor?.length??0)),v=new DataView(payload.buffer);v.setUint32(4,cursor?1:0,true);v.setBigUint64(8,1000000n,true);if(cursor)payload.set(cursor,16);
   const member=decode(await bridge.execute(encode({command:12,handle:frame.handle,sequence:1n,budget,payload}))).handle;let data,packet,page,normalized,nv;
   try{
    await driveGeoSession(bridge,{handle:member,sequence:1n,budget,readChunk});
    const reply=decode(await bridge.execute(encode({command:13,handle:member,sequence:1n,budget})));data=reply.handle;
    assert.equal(reply.sourceHandle,member);assert.equal(reply.sequence,1n);
    packet=await bridge.read(encode({command:23,handle:data}));assert.equal(BigInt(packet.byteLength),reply.dataLength);
    page=parseGeoMembershipData(packet);assert.equal(page.owner,member);assert.equal(page.sequence,1n);assert.equal(page.cell,0);
    assert.ok(page.length<=4);for(let i=0;i<page.length;i++)all.push(page.record(i));
    cursor=page.cursor?.slice()??null;
    rawHashes.push(sha(new Uint8Array(packet)));
    normalized=new Uint8Array(packet.slice(0));nv=new DataView(normalized.buffer);
    // Both fields are the independently validated per-process membership-session owner, never source/camera/time/key.
    assert.equal(nv.getBigUint64(16,true),member);assert.equal(nv.getBigUint64(80,true),member);
    nv.setBigUint64(16,0n,true);nv.setBigUint64(80,0n,true);
    packets.push(Buffer.from(normalized).toString('base64'));
   }finally{nv=undefined;normalized=undefined;page=undefined;packet=undefined;if(data!==undefined)await bridge.execute(encode({command:10,handle:data}));await bridge.execute(encode({command:10,handle:member}));}
  }while(cursor);
  assert.deepEqual(all.map(f=>Number(f.sourceRow)),profile.rows);
  for(const f of all){assert.equal(f.chunkIndex,Number(f.sourceRow/7n));assert.equal(f.chunkRow,Number(f.sourceRow%7n));assert.equal(f.featureId,ids[f.chunkRow]);}
  if(profile.name==='All')assert.equal(packets.length,3);
  return {name:profile.name,rows:all.map(f=>({featureId:f.featureId.toString(),sourceRow:f.sourceRow.toString(),chunkIndex:f.chunkIndex,chunkRow:f.chunkRow})),packets,rawHashes};
 }finally{if(frame)await frame.dispose();if(source!==undefined)await bridge.execute(encode({command:10,handle:source}));await bridge.execute(encode({command:10,handle:builder}));}
}
const pairs=[];
try{for(const p of profiles){const native=await run(nativeGeoScaleBridge(budget.processorBytes),p),actualWasm=await run(wasm,p);assert.deepEqual({...native,rawHashes:[]},{...actualWasm,rawHashes:[]});pairs.push({name:p.name,rows:native.rows,normalizedPackets:native.packets,nativeRawSha256:native.rawHashes,wasmRawSha256:actualWasm.rawHashes});}}
finally{assert.equal(x.xyg_wasm_instance_dispose(h),0);}
const evidence={scope:'Actual legacy projected membership packets; new overview membership remains engine-only. No latency/paint/massive claim.',
 native:{path:nativePath,sha256:sha(nativeBytes)},wasm:{path:String(wasmPath),sha256:sha(wasmBytes),rawBytes:wasmBytes.length,gzipLevel6Bytes:gzipSync(wasmBytes,{level:6}).length},
 normalization:'Only validated process-local membership-session owner fields16..24 and80..88; every other byte remains exact.',pairs};
if(process.env.XYG_MEMBERSHIP_REPORT)await writeFile(process.env.XYG_MEMBERSHIP_REPORT,JSON.stringify(evidence,null,2)+'\n');
console.log(`actual native/WASM legacy membership: ${pairs.length} temporal profiles, ${pairs.reduce((n,p)=>n+p.normalizedPackets.length,0)} exact paged packets, full-u64 duplicate IDs/MultiPoint/source disposal PASS`);
