// Actual native immutable Data duplication, lifetime and failure atomicity.
import test from 'node:test';
import assert from 'node:assert/strict';
import {RetainedGeoSource} from '../src/geo-retained.js';
import {nativeGeoScaleBridge,encodeGeoScaleStyle} from '../src/geoscale.js';
import {fixture,budget,U64,I64} from './geoscale-fixture.mjs';
const style=()=>encodeGeoScaleStyle({fill:new Uint8Array([255,0,0,255]),stroke:new Uint8Array(4),strokeWidth:0,diameter:6,opacity:1,symbol:0});
function query(info){return {camera:{crs:4326,worldWrap:true,centerX:0,centerY:0,zoom:0,width:800,height:600,bearing:0,pitch:0},reducedKind:0,maxCells:32768,previousDirect:true,sourceDigest:info.digest,generation:info.generation,layerId:U64,cameraRevision:U64,timeRevision:U64,layerRevision:U64,styleRevision:U64,stateRevision:U64,time:{kind:1,instant:I64},maxProjectedVertices:1000000n};}
async function setup(){const f=await fixture(),bridge=nativeGeoScaleBridge(budget.processorBytes),source=await RetainedGeoSource.create(Uint8Array.from(Buffer.from(f.manifest,'hex')),async()=>Uint8Array.from(Buffer.from(f.chunk,'hex')),{budget,bridge});return {source,frame:await source.update(query(source.info),{sequence:1n,style:style()})};}
function canonical(packet){const b=new Uint8Array(packet.slice(0));b.fill(0,16,24);return b;}
test('retained frame is independent after original and source disposal',async()=>{
 const {source,frame}=await setup(),owned=await frame.retain();
 try{
 assert.notEqual(owned.handle,frame.handle);assert.equal(source.current,frame);assert.equal(owned.data.identity.sessionHandle,frame.handle);assert.deepEqual(canonical(owned.data.packet),canonical(frame.data.packet));
 await source.dispose();await frame.dispose();assert.equal(owned.data.record(0).featureId,U64);
 const rows=await owned.rows();assert.equal(rows.data.record(0).featureId,U64);await rows.dispose();
 const hit=await owned.pick({style:style(),x:400,y:300,tolerance:0,mode:0,maxHits:4});assert.equal(hit.data.count,1n);await hit.dispose();
 const artifact=await owned.export('svg');assert.match(Buffer.from(artifact.bytes).toString(),/<svg/);await artifact.dispose();
 const second=await owned.retain();await owned.dispose();assert.equal(second.data.record(0).featureId,U64);await second.dispose();await assert.rejects(frame.retain(),/disposed/);
 }finally{await owned.dispose();await frame.dispose();await source.dispose();}
});
test('indexed retained frame never depends on disposed query/index handles',async()=>{
 const {source,frame}=await setup(),pages=new Map();let indexed,owned,index;
 try{
 index=await frame.spatialIndex({grid:16,maxVertices:1000000n,readPage:async t=>pages.get(t.page),writePage:async(t,b)=>pages.set(t.page,b.slice())});
 indexed=await index.update(query(index.info),{sequence:2n,style:style()});owned=await indexed.retain();assert.equal(index.current,indexed);assert.deepEqual(owned.indexStats,indexed.indexStats);assert.deepEqual(canonical(owned.data.packet),canonical(indexed.data.packet));
 await indexed.dispose();await index.dispose();await frame.dispose();await source.dispose();
 const rows=await owned.rows();assert.equal(rows.data.record(0).featureId,U64);await rows.dispose();
 const hit=await owned.pick({style:style(),x:400,y:300,tolerance:0,mode:0,maxHits:4});assert.equal(hit.data.count,1n);await hit.dispose();
 const artifact=await owned.export('svg');assert.match(Buffer.from(artifact.bytes).toString(),/<svg/);await artifact.dispose();
 }finally{if(owned)await owned.dispose();if(indexed)await indexed.dispose();if(index)await index.dispose();await frame.dispose();await source.dispose();}
});
test('duplicate pressure drains without altering source current',async()=>{
 const {source,frame}=await setup(),owned=[];
 try{for(let i=0;i<7;i++)owned.push(await frame.retain());await assert.rejects(frame.retain());assert.equal(source.current,frame);for(const f of owned)await f.dispose();owned.length=0;for(let i=0;i<20;i++)await(await frame.retain()).dispose();assert.equal(frame.data.record(0).featureId,U64);}
 finally{for(const f of owned)await f.dispose();await frame.dispose();await source.dispose();}
});
test('failed duplicate read disposes unreturned owner and preserves old paint',async()=>{
 const {source,frame}=await setup(),native=source.bridge;let duplicate;
 source.bridge={async execute(request){const reply=await native.execute(request);if(new DataView(request).getUint32(8,true)===26)duplicate=new DataView(reply).getBigUint64(16,true);return reply;},async read(request){if(new DataView(request).getBigUint64(16,true)===duplicate)throw new Error('duplicate transport failed');return native.read(request);}};
 try{
 await assert.rejects(frame.retain(),/duplicate transport failed/);const {encodeGeoScaleRequest}=await import('../src/geoscale.js');await assert.rejects(native.read(encodeGeoScaleRequest({command:23,handle:duplicate})));assert.equal(source.current,frame);assert.equal(frame.data.record(0).featureId,U64);
 source.bridge=native;const recovery=await frame.retain();await recovery.dispose();
 }finally{source.bridge=native;await frame.dispose();await source.dispose();}
});
