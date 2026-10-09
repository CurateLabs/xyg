import test from 'node:test';
import assert from 'node:assert/strict';
import {RetainedGeoSource} from '../src/geo-retained.js';
import {geoChart,geoLayer} from '../src/charts.js';
import {encodeGeoScaleStyle} from '../src/geoscale.js';
import {fixture,budget,U64,I64} from './geoscale-fixture.mjs';
const style=()=>encodeGeoScaleStyle({fill:new Uint8Array([255,0,0,255]),stroke:new Uint8Array(4),strokeWidth:0,diameter:6,opacity:1,symbol:0});
const query=info=>({camera:{crs:4326,worldWrap:true,centerX:0,centerY:0,zoom:0,width:800,height:600,bearing:0,pitch:0},reducedKind:0,maxCells:32768,previousDirect:true,sourceDigest:info.digest,generation:info.generation,layerId:U64,cameraRevision:U64,timeRevision:U64,layerRevision:U64,styleRevision:U64,stateRevision:U64,time:{kind:1,instant:I64},maxProjectedVertices:1000000n});
async function setup(){
 const f=await fixture(),bytes=x=>Uint8Array.from(Buffer.from(x,'hex'));
 const source=await RetainedGeoSource.create(bytes(f.manifest),async()=>bytes(f.chunk),{budget});
 const first=await source.update(query(source.info),{sequence:1n,style:style()}),pages=new Map();
 const index=await first.spatialIndex({grid:16,maxVertices:1000000n,readPage:async t=>pages.get(t.page),writePage:async(t,b)=>pages.set(t.page,b.slice())});
 const q=query(index.info),frame=await index.update(q,{sequence:2n,style:style()});
 const chart=geoChart(geoLayer('points',{source:index,layerId:U64,query:q,sequence:2n,style:style()}),{camera:q.camera});
 await index.dispose();await first.dispose();await source.dispose();return {index,chart,frame,q};
}
function request(adapter,op,{mount='first',owner=0n,sequence=0n}={}){const b=new ArrayBuffer(32),v=new DataView(b);new Uint8Array(b).set([88,89,71,72]);v.setUint32(4,1,true);v.setUint32(8,op,true);v.setBigUint64(16,owner,true);v.setBigUint64(24,sequence,true);return adapter.handle({type:'geo_host',request:'test',mount},[b]);}
test('indexed explicit mount retains anchor before caller disposal and remounts after ACK',async()=>{
 const {index,chart,frame}=await setup(),adapter=chart.host({frame});
 try{
 assert.equal(index.current,frame);await frame.dispose();
 await adapter.anchorReady;const anchor=adapter.anchor;assert.notEqual(anchor.handle,frame.handle);
 for(const mount of ['first','second']){
  let [reply,packets]=await request(adapter,1,{mount});assert.equal(reply.error,undefined);const owner=adapter.frame.handle;assert.equal(owner,anchor.handle);if(mount==='second'){const [stale]=await request(adapter,4,{mount:'first',owner,sequence:2n});assert.ok(stale.error);assert.equal(adapter.mounted,true);}assert.equal(adapter.frame.data.record(0).featureId,U64);
  const rows=await adapter.frame.rows();assert.equal(rows.data.record(0).featureId,U64);await rows.dispose();
  packets=undefined;
  if(mount==='second'){adapter.close();assert.equal(anchor.data.record(0).featureId,U64);}
  [reply]=await request(adapter,4,{mount,owner,sequence:2n});assert.equal(reply.error,undefined);
 }
 assert.throws(()=>anchor.data,/disposed/);
 }finally{await adapter.realmDestroyed();await frame.dispose();}
});
test('query/style/sequence mismatch rejects before retain and preserves caller',async()=>{
 const {index,chart,frame,q}=await setup();
 try{
 assert.throws(()=>chart.host(),/indexed hosts are pending/);
 for(const field of ['cameraRevision','timeRevision','styleRevision','stateRevision']){
 const changed={...q,[field]:q[field]-1n};const wrong=geoChart(geoLayer('points',{source:index,layerId:U64,query:changed,sequence:2n,style:style()}),{camera:q.camera});assert.throws(()=>wrong.host({frame}),/explicit frame/);
 }
 const differentStyle=style();differentStyle[0]=127;
 const wrongStyle=geoChart(geoLayer('points',{source:index,layerId:U64,query:q,sequence:2n,style:differentStyle}),{camera:q.camera});assert.throws(()=>wrongStyle.host({frame}),/explicit frame/);
 const wrongSequence=geoChart(geoLayer('points',{source:index,layerId:U64,query:q,sequence:3n,style:style()}),{camera:q.camera});assert.throws(()=>wrongSequence.host({frame}),/explicit frame/);
 const camera={...q.camera,centerX:1};const wrongCamera=geoChart(geoLayer('points',{source:index,layerId:U64,query:{...q,camera},sequence:2n,style:style()}),{camera});assert.throws(()=>wrongCamera.host({frame}),/explicit frame/);
 const originalRows=index.info.rows;index.info.rows+=1n;assert.throws(()=>chart.host({frame}),/explicit frame/);index.info.rows=originalRows;
 frame.data.identity.sequence=100n;
 assert.equal(frame.data.record(0).featureId,U64);
 const adapter=chart.host({frame});adapter.close();await adapter.cleanup;assert.equal(frame.data.record(0).featureId,U64);
 }finally{await frame.dispose();}
});
test('anchor admission pressure preserves caller and unmounted close drains leases',async()=>{
 const {chart,frame}=await setup(),copies=[];
 try{
  for(let i=0;i<7;i++)copies.push(await frame.retain());
  const rejected=chart.host({frame});await assert.rejects(rejected.anchorReady);rejected.close();await assert.rejects(rejected.cleanup);
  assert.equal(frame.data.record(0).featureId,U64);
  for(const copy of copies)await copy.dispose();copies.length=0;
  for(let i=0;i<12;i++){const adapter=chart.host({frame});adapter.close();await adapter.cleanup;}
  assert.equal(frame.data.record(0).featureId,U64);
 }finally{for(const copy of copies)await copy.dispose();await frame.dispose();}
});
test('five mounted native views fit unchanged quota and auxiliary pressure preserves paint',async()=>{
 const {chart,frame}=await setup(),adapters=[];
 try{
  for(let i=0;i<5;i++){const a=chart.host({frame});adapters.push(a);await a.anchorReady;const [reply]=await request(a,1,{mount:String(i)});assert.equal(reply.error,undefined);assert.equal(a.frame,a.anchor);}
  const pages=[];
  for(let i=0;i<2;i++)pages.push(await adapters[i].frame.rows());
  await assert.rejects(adapters[2].frame.rows());
  for(const a of adapters)assert.equal(a.frame.data.record(0).featureId,U64);
  for(const page of pages)await page.dispose();
  const recovery=await adapters[2].frame.rows();assert.equal(recovery.data.record(0).featureId,U64);await recovery.dispose();
 }finally{
  for(let i=0;i<adapters.length;i++){const a=adapters[i];a.close();if(a.mounted){const [reply]=await request(a,4,{mount:String(i),owner:a.frame.handle,sequence:2n});assert.equal(reply.error,undefined);}await a.cleanup;assert.equal(a.anchor,undefined);}
  await frame.dispose();
 }
});
