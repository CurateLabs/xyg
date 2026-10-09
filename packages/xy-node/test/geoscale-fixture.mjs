// Real Rust ABI382 fixture shared with the independent Python byte comparison.
import assert from 'node:assert/strict';
import {pathToFileURL} from 'node:url';
import {encodeGeoChunkRequest,encodeGeoScaleRequest,decodeGeoScaleReply,encodeGeoScaleStyle,driveGeoSession,prepareGeoSceneData,nativeGeoScaleBridge} from '../src/geoscale.js';

export const budget={processorBytes:128*1024*1024,maxRowsExamined:1000000n,maxReadBytes:128n*1024n*1024n,maxChunks:65536,pageRows:4096};
export const U64=0xffffffffffffffffn,I64= -0x8000000000000000n;
export async function fixture(inputBridge,onFrame){
 const bridge=inputBridge??nativeGeoScaleBridge(budget.processorBytes),descriptor=new Uint8Array(120),v=new DataView(descriptor.buffer);
 descriptor.set([88,89,71,68]);[1,1,4326,1,0].forEach((n,i)=>v.setUint32(4+i*4,n,true));[2n,2n,0n,0n,0n].forEach((n,i)=>v.setBigUint64(24+i*8,n,true));[0,0,1,1].forEach((n,i)=>v.setFloat64(64+i*8,n,true));descriptor.set([1,1],96);v.setBigUint64(104,U64,true);v.setBigUint64(112,9007199254740993n,true);
 const request=encodeGeoChunkRequest({descriptor,rows:2,intervals:{starts:new BigInt64Array([I64,I64]),ends:new BigInt64Array([0x7fffffffffffffffn,0x7fffffffffffffffn]),startValidity:new Uint8Array([1,1]),endValidity:new Uint8Array([1,1])},values:new Float64Array([0,1])},budget.processorBytes),chunk=await bridge.read(request);
 const builder=decodeGeoScaleReply(await bridge.execute(encodeGeoScaleRequest({command:1}))).handle;let session,lease;
 try{
  await bridge.execute(encodeGeoScaleRequest({command:2,handle:builder,payload:chunk}));await bridge.execute(encodeGeoScaleRequest({command:3,handle:builder,generation:U64}));const manifest=await bridge.read(encodeGeoScaleRequest({command:21,handle:builder}));session=decodeGeoScaleReply(await bridge.execute(encodeGeoScaleRequest({command:4,payload:manifest,budget}))).handle;
  const readChunk=async ticket=>{assert.equal(ticket.encodedBytes,chunk.byteLength);return chunk;};const source=(await driveGeoSession(bridge,{handle:session,sequence:0n,budget,readChunk})).source;
  const query={camera:{crs:4326,worldWrap:true,centerX:0,centerY:0,zoom:0,width:800,height:600,bearing:0,pitch:0},reducedKind:0,maxCells:32768,previousDirect:true,sourceDigest:source.digest,generation:source.generation,layerId:U64,cameraRevision:U64,timeRevision:U64,layerRevision:U64,styleRevision:U64,stateRevision:U64,time:{kind:1,instant:I64},maxProjectedVertices:1000000n};
  const begin=encodeGeoScaleRequest({command:5,handle:session,sequence:1n,budget,query});await bridge.execute(begin);assert.equal((await driveGeoSession(bridge,{handle:session,sequence:1n,budget,readChunk})).code,4);
  lease=await prepareGeoSceneData(bridge,{handle:session,sequence:1n,budget,style:encodeGeoScaleStyle({fill:new Uint8Array([255,0,0,255]),stroke:new Uint8Array(4),strokeWidth:0,diameter:6,opacity:1,symbol:0})});assert.equal(lease.data.record(0).featureId,U64);assert.equal(lease.data.record(1).featureId,9007199254740993n);assert.equal(lease.data.identity.time.instant,I64);
  if(onFrame)await onFrame(lease,{bridge,readChunk,query,style:encodeGeoScaleStyle({fill:new Uint8Array([255,0,0,255]),stroke:new Uint8Array(4),strokeWidth:0,diameter:6,opacity:1,symbol:0})});
  await bridge.read(encodeGeoScaleRequest({command:23,handle:lease.handle}));await assert.rejects(bridge.read(encodeGeoScaleRequest({command:23,handle:lease.handle})),error=>error.nativeCode=== -9);
  const packet=lease.data.packet.slice(0);new Uint8Array(packet).fill(0,16,24);new Uint8Array(begin).fill(0,16,24);const hex=b=>Buffer.from(b).toString('hex');return {chunk_request:hex(request),chunk:hex(chunk),manifest:hex(manifest),begin:hex(begin),packet:hex(packet)};
 }finally{if(lease){await lease.dispose();assert.throws(()=>lease.data,/disposed/);}if(session!==undefined)await bridge.execute(encodeGeoScaleRequest({command:10,handle:session}));await bridge.execute(encodeGeoScaleRequest({command:10,handle:builder}));}
}
if(process.argv[1]&&import.meta.url===pathToFileURL(process.argv[1]).href)console.log(JSON.stringify(await fixture()));
