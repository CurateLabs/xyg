// Real native index storage, ordinary immutable frame APIs and release ordering.
import test from 'node:test';
import assert from 'node:assert/strict';
import {RetainedGeoSource} from '../src/geo-retained.js';
import {GeoSpatialFullScanRequired} from '../src/geo-spatial.js';
import {nativeGeoScaleBridge,encodeGeoScaleStyle,encodeGeoScaleRequest as encode,decodeGeoScaleReply as decode} from '../src/geoscale.js';
import {fixture,budget,U64,I64} from './geoscale-fixture.mjs';
const style=()=>encodeGeoScaleStyle({fill:new Uint8Array([255,0,0,255]),stroke:new Uint8Array(4),strokeWidth:0,diameter:6,opacity:1,symbol:0});
function query(info){return {camera:{crs:4326,worldWrap:true,centerX:0,centerY:0,zoom:0,width:800,height:600,bearing:0,pitch:0},reducedKind:0,maxCells:32768,previousDirect:true,sourceDigest:info.digest,generation:info.generation,layerId:U64,cameraRevision:U64,timeRevision:U64,layerRevision:U64,styleRevision:U64,stateRevision:U64,time:{kind:1,instant:I64},maxProjectedVertices:1000000n};}
async function setup(spread=false){
 const raw=await fixture(),bridge=nativeGeoScaleBridge(budget.processorBytes);
 let chunk=Uint8Array.from(Buffer.from(raw.chunk,'hex')),manifest=Uint8Array.from(Buffer.from(raw.manifest,'hex'));
 if(spread){const request=Uint8Array.from(Buffer.from(raw.chunk_request,'hex'));new DataView(request.buffer).setFloat64(256+32+64+16,45,true);chunk=await bridge.read(request.buffer);const h=decode(await bridge.execute(encode({command:1}))).handle;try{await bridge.execute(encode({command:2,handle:h,payload:chunk}));await bridge.execute(encode({command:3,handle:h,generation:U64}));manifest=await bridge.read(encode({command:21,handle:h}));}finally{await bridge.execute(encode({command:10,handle:h}));}}
 const source=await RetainedGeoSource.create(manifest,async()=>chunk,{budget,bridge});
 return {source,frame:await source.update(query(source.info),{sequence:1n,style:style()}),chunk};
}
function storage(pages){return {grid:16,maxVertices:1000000n,readPage:async t=>pages.get(t.page),writePage:async(t,b)=>pages.set(t.page,b.slice())};}
test('indexed frames retain full IDs, rows, picking and export after source/index disposal',async()=>{
 const {source,frame:old}=await setup(),pages=new Map();let index,frame;
 try{
 index=await old.spatialIndex(storage(pages));const canonical=new Uint8Array(old.data.packet.slice(0));canonical.fill(0,16,32);await source.dispose();await old.dispose();
 frame=await index.update(query(index.info),{sequence:2n,style:style()});
 const indexed=new Uint8Array(frame.data.packet.slice(0));indexed.fill(0,16,32);assert.deepEqual(indexed,canonical);
 assert.equal(frame.data.record(0).featureId,U64);assert.equal(frame.data.record(1).featureId,9007199254740993n);
 assert.equal(frame.indexStats.pagesRead,BigInt(pages.size));assert.equal(frame.indexStats.passes,1);
 await index.dispose();
 const rows=await frame.rows();assert.equal(rows.data.record(0).featureId,U64);await rows.dispose();
 const hits=await frame.pick({style:style(),x:400,y:300,tolerance:0,mode:0,maxHits:4});assert.equal(hits.data.count,1n);await hits.dispose();
 const artifact=await frame.export('svg');assert.match(Buffer.from(artifact.bytes).toString(),/<svg/);await artifact.dispose();
 }finally{if(frame)await frame.dispose();if(index)await index.dispose();await old.dispose();await source.dispose();}
});
test('failed writes and authenticated reads preserve old frame and recover',async()=>{
 const {source,frame}=await setup();let index,newer;
 try{
 for(let i=0;i<10;i++)await assert.rejects(frame.spatialIndex({...storage(new Map()),writePage:async(t,b)=>{assert.equal(b.byteLength,t.encodedBytes);throw new Error('durable storage failed');}}),/durable/);
 assert.equal(source.current,frame);
 const pages=new Map();index=await frame.spatialIndex(storage(pages));newer=await index.update(query(index.info),{sequence:2n,style:style()});
 index.readPage=async t=>new Uint8Array(pages.get(t.page).byteLength);
 await assert.rejects(index.update(query(index.info),{sequence:3n,style:style()}));assert.equal(index.current,newer);
 index.readPage=async t=>pages.get(t.page);const recovery=await index.update(query(index.info),{sequence:4n,style:style()});await recovery.dispose();
 }finally{if(newer)await newer.dispose();if(index)await index.dispose();await frame.dispose();await source.dispose();}
});
test('pending durable write cancellation waits for storage settlement before ACK',async()=>{
 const {source,frame}=await setup();const controller=new AbortController();let enter,release;
 const started=new Promise(r=>enter=r),gate=new Promise(r=>release=r);
 const pending=frame.spatialIndex({...storage(new Map()),signal:controller.signal,writePage:async(t,b)=>{assert.equal(t.encodedBytes,b.byteLength);enter();await gate;}});
 await Promise.race([started,pending.then(()=>{throw new Error('write not entered');})]);controller.abort();
 let settled=false;pending.then(()=>settled=true,()=>settled=true);await new Promise(r=>setTimeout(r,10));assert.equal(settled,false);
 release();await assert.rejects(pending,/abort|cancel/i);assert.equal(source.current,frame);
 const index=await frame.spatialIndex(storage(new Map()));await index.dispose();await frame.dispose();await source.dispose();
});
test('callback mutation cannot authorize larger leaf storage',async()=>{
 const {source,frame}=await setup(),pages=new Map();const index=await frame.spatialIndex({...storage(pages),readPage:async t=>{const b=pages.get(t.page);t.encodedBytes*=2;const result=new Uint8Array(b.length*2);result.set(b);return result;}});
 try{await assert.rejects(index.update(query(index.info),{sequence:2n,style:style()}));assert.equal(index.current,undefined);}
 finally{await index.dispose();await frame.dispose();await source.dispose();}
});
test('public composition compiles indexed source and exports exact owned frame',async()=>{
 const {geoChart,geoLayer}=await import('../src/charts.js');
 const {source,frame:initial}=await setup(),index=await initial.spatialIndex(storage(new Map()));
 const q=query(index.info),chart=geoChart(geoLayer('points',{source:index,layerId:U64,query:q,sequence:2n,style:style()}),{camera:q.camera});
 let frame;
 try{frame=await chart.compileRetained();assert.equal(index.current,frame);assert.equal(frame.data.record(0).featureId,U64);const artifact=await chart.toImage('svg',{frame});assert.match(Buffer.from(artifact.bytes).toString(),/<svg/);await artifact.dispose();}
 finally{if(frame)await frame.dispose();await index.dispose();await initial.dispose();await source.dispose();}
});
test('leaf work fallback reports explicit reason and does not advance query sequence',async()=>{
 const {source,frame:initial}=await setup(true),index=await initial.spatialIndex(storage(new Map()));
 try{index.budget.maxChunks=1;await assert.rejects(index.update(query(index.info),{sequence:2n,style:style()}),e=>e instanceof GeoSpatialFullScanRequired&&e.reasonCode===2);assert.equal(index.current,undefined);index.budget.maxChunks=budget.maxChunks;const frame=await index.update(query(index.info),{sequence:2n,style:style()});assert.equal(frame.data.record(0).featureId,U64);await frame.dispose();}
 finally{await index.dispose();await initial.dispose();await source.dispose();}
});
