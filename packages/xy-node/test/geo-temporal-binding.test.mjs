import assert from 'node:assert/strict';
import test from 'node:test';
import { fixture, budget, U64 } from './geoscale-fixture.mjs';
import { RetainedGeoSource, geoChart, geoLayer, temporalControllerCreate, temporalControllerSetCursor, temporalControllerSetSelection, temporalControllerDestroy, temporalControllerSubscribeState, temporalControllerState } from '../src/index.js';

for(const mode of ['cursor','range'])test(`public native ${mode} binding leases, races, failure and export`,async()=>{
 let q,style;
 const packets=await fixture(undefined,async(_,f)=>{q=f.query;style=f.style;});
 const bytes=h=>Uint8Array.from(Buffer.from(h,'hex')).buffer;
 const chunk=bytes(packets.chunk);let reads=0,fail=false,gate,entered,unblock;
 const source=await RetainedGeoSource.create(bytes(packets.manifest),async()=>{reads++;if(gate){entered();await gate;}if(fail)throw Error('storage unavailable');return chunk;},{budget});
 q={...q,timeRevision:0n,cameraRevision:0n};
 const chart=geoChart(geoLayer('points',{source,layerId:U64,query:q,sequence:1n,style}),{camera:q.camera});
 const handle=temporalControllerCreate({instanceId:U64,domainStart:-(1n<<63n),domainEnd:(1n<<63n)-1n,cursor:-(1n<<63n),window:0n,step:1n});
 const binding=chart.bindTemporal(handle,mode),leases=[];
 try {
  await binding.whenIdle();assert.equal(binding.error,undefined);
  const first=await binding.snapshot();leases.push(first.frame);
  assert.equal(first.frame.data.record(0).featureId,U64);
  console.log(JSON.stringify({rows:2,processMemory:process.memoryUsage(),packetBytes:first.frame.data.packet.byteLength,chunkBytes:chunk.byteLength}));
  const baseline=reads;temporalControllerSetSelection(handle,[U64,1n<<63n]);await binding.whenIdle();assert.equal(reads,baseline);
  let reached;const ready=new Promise(r=>reached=r);entered=reached;gate=new Promise(r=>unblock=r);
  temporalControllerSetCursor(handle,0n);await ready;
  temporalControllerSetCursor(handle,1n);binding.setCamera({...q.camera,zoom:1});temporalControllerSetCursor(handle,2n);unblock();gate=undefined;
  await binding.whenIdle();assert.equal(binding.error,undefined);
  const next=await binding.snapshot();leases.push(next.frame);
  assert.deepEqual(next.frame.data.identity.time,mode==='cursor'?{kind:1,instant:2n}:{kind:2,start:temporalControllerState(handle).rangeStart,end:temporalControllerState(handle).rangeEnd});
  assert.equal(next.frame.data.identity.camera.zoom,1);
  fail=true;temporalControllerSetCursor(handle,3n);await binding.whenIdle();assert.match(binding.error.message,/storage/);
  const retained=await binding.snapshot();leases.push(retained.frame);assert.deepEqual(retained.frame.data.identity,next.frame.data.identity);
  fail=false;temporalControllerSetCursor(handle,(1n<<63n)-2n);await binding.whenIdle();assert.equal(binding.error,undefined);
  const last=await binding.snapshot();leases.push(last.frame);
  const artifact=await last.chart.toImage('svg',{frame:last.frame});assert.match(Buffer.from(artifact.bytes).toString(),/<svg/);await artifact.dispose();
  let reachedDispose;const disposeReady=new Promise(r=>reachedDispose=r);entered=reachedDispose;gate=new Promise(r=>unblock=r);
  temporalControllerSetCursor(handle,4n);await disposeReady;temporalControllerDestroy(handle);
  let settled=false;const closing=binding.dispose().then(()=>settled=true);await Promise.resolve();assert.equal(settled,false);unblock();gate=undefined;await closing;assert.equal(last.frame.data.record(0).featureId,U64);
 } finally {unblock?.();await binding.dispose();for(const frame of leases)await frame.dispose();await source.dispose();try{temporalControllerDestroy(handle);}catch{}}
});
test('native observer reentrancy and rejected promises never fail commands',async()=>{
 const h=temporalControllerCreate({instanceId:4n,domainStart:-100n,domainEnd:100n,cursor:0n,window:0n,step:1n});
 const seen=[];const stop=temporalControllerSubscribeState(h,s=>{seen.push(s.cursor);if(s.cursor===1n)temporalControllerSetCursor(h,2n);});
 temporalControllerSubscribeState(h,async()=>{throw Error('async observer');});temporalControllerSubscribeState(h,()=>{throw Error('observer');});
 try{temporalControllerSetCursor(h,1n);await Promise.resolve();assert.deepEqual(seen,[1n,2n]);stop();temporalControllerSetCursor(h,3n);assert.deepEqual(seen,[1n,2n]);}finally{temporalControllerDestroy(h);}
});

test('public aggregate binding returns exact native paged membership',async()=>{
 const {nativeGeoScaleBridge,encodeGeoScaleRequest:enc,decodeGeoScaleReply:dec,encodeGeoChunkRequest:chunkRequest}=await import('../src/geoscale.js');
 const b=nativeGeoScaleBridge(budget.processorBytes);
 const start=performance.now(),n=32769,idsAt=64+n*16+Math.ceil(n/8)*8;
 const d=new Uint8Array(idsAt+n*8),v=new DataView(d.buffer);d.set([88,89,71,68]);
 [1,1,4326,1,0].forEach((x,i)=>v.setUint32(4+4*i,x,true));[BigInt(n),BigInt(n),0n,0n,0n].forEach((x,i)=>v.setBigUint64(24+8*i,x,true));
 d.fill(1,64+n*16,64+n*17);for(let i=0;i<n;i++)v.setBigUint64(idsAt+8*i,i?BigInt(i):U64,true);
 const chunk=await b.read(chunkRequest({descriptor:d,rows:n},budget.processorBytes));
 const builder=dec(await b.execute(enc({command:1}))).handle;let manifest;
 try{await b.execute(enc({command:2,handle:builder,payload:chunk}));await b.execute(enc({command:3,handle:builder,generation:U64}));manifest=await b.read(enc({command:21,handle:builder}));}finally{await b.execute(enc({command:10,handle:builder}));}
 let q,style;await fixture(undefined,async(_,f)=>{q=f.query;style=f.style;});
 const source=await RetainedGeoSource.create(manifest,async()=>chunk,{budget:{...budget,pageRows:1}});
 q={...q,sourceDigest:source.info.digest,generation:source.info.generation,timeRevision:0n,cameraRevision:0n,maxCells:1,previousDirect:false};
 const chart=geoChart(geoLayer('points',{source,layerId:U64,query:q,sequence:1n,style}),{camera:q.camera});
 const h=temporalControllerCreate({instanceId:8n,domainStart:-10n,domainEnd:10n,cursor:0n,window:0n,step:1n}),binding=chart.bindTemporal(h);let frame,page;
 try{await binding.whenIdle();assert.equal(binding.error,undefined);({frame}=await binding.snapshot());assert.equal(frame.data.aggregate,true);
  page=await frame.membership(0,{maxProjectedVertices:1000000n});assert.equal(new DataView(page.data.records.buffer,page.data.records.byteOffset).getBigUint64(0,true),U64);
  console.log(JSON.stringify({rows:n,elapsedMs:performance.now()-start,processMemory:process.memoryUsage(),chunkBytes:chunk.byteLength,packetBytes:frame.data.packet.byteLength}));
 }finally{await page?.dispose();await frame?.dispose();await binding.dispose();temporalControllerDestroy(h);await source.dispose();}
});

test('old unsubscribe cannot remove a resubscribed observer set',()=>{
 const h=temporalControllerCreate({instanceId:23n,domainStart:-10n,domainEnd:10n,cursor:0n,window:0n,step:1n});
 try{
  const seen=[];
  const old=temporalControllerSubscribeState(h,()=>assert.fail('old observer invoked'));
  old();
  const current=temporalControllerSubscribeState(h,s=>seen.push(s.cursor));
  old();
  temporalControllerSetCursor(h,3n);
  assert.deepEqual(seen,[3n]);
  current();current();temporalControllerSetCursor(h,4n);
  assert.deepEqual(seen,[3n]);
 }finally{temporalControllerDestroy(h);}
});
