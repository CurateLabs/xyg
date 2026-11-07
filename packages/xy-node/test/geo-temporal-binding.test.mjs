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

for(const numericSubscription of [false,true])test(`native observers normalize Number and BigInt handles ${numericSubscription}`,()=>{
 const h=temporalControllerCreate({instanceId:41n,domainStart:-10n,domainEnd:10n,cursor:0n,window:0n,step:1n});
 const n=Number(h);assert.ok(Number.isSafeInteger(n));const seen=[];
 const stop=temporalControllerSubscribeState(numericSubscription?n:h,s=>seen.push({cursor:s.cursor,disposed:s.disposed}));
 try{
  temporalControllerSetCursor(numericSubscription?h:n,3n);
  assert.deepEqual(seen,[{cursor:3n,disposed:false}]);
  temporalControllerDestroy(numericSubscription?h:n);
  assert.deepEqual(seen,[{cursor:3n,disposed:false},{cursor:3n,disposed:true}]);
 }finally{stop();try{temporalControllerDestroy(h);}catch{}}
});

test('reentrant destroy notifies retained binding and releases its source registration',async()=>{
 let q,style;const packets=await fixture(undefined,async(_,f)=>{q=f.query;style=f.style;});
 const bytes=h=>Uint8Array.from(Buffer.from(h,'hex')).buffer;
 const source=await RetainedGeoSource.create(bytes(packets.manifest),async()=>bytes(packets.chunk),{budget});
 q={...q,timeRevision:0n,cameraRevision:0n};
 const chart=geoChart(geoLayer('points',{source,layerId:U64,query:q,sequence:1n,style}),{camera:q.camera});
 const create=id=>temporalControllerCreate({instanceId:id,domainStart:-10n,domainEnd:10n,cursor:0n,window:0n,step:1n});
 const h=create(42n);const stop=temporalControllerSubscribeState(h,s=>{if(!s.disposed)temporalControllerDestroy(h);});
 let binding,replacement,lease,h2;
 try{
  binding=chart.bindTemporal(h);await binding.whenIdle();({frame:lease}=await binding.snapshot());
  temporalControllerSetCursor(h,3n);
  assert.equal(binding.closed,true);
  assert.ok(binding.disposing);await binding.disposing;
  h2=create(43n);const nextChart=geoChart(geoLayer('points',{source,layerId:U64,query:q,sequence:binding.sequence,style}),{camera:q.camera});replacement=nextChart.bindTemporal(h2);await replacement.whenIdle();assert.equal(replacement.error,undefined);
  assert.equal(lease.data.record(0).featureId,U64);
 }finally{
  stop();await replacement?.dispose();await binding?.dispose();await lease?.dispose();await source.dispose();
  for(const handle of [h,h2])if(handle!==undefined)try{temporalControllerDestroy(handle);}catch{}
 }
});

test('destroy remains safe when a terminal observer also requests destruction',()=>{
 const h=temporalControllerCreate({instanceId:44n,domainStart:-10n,domainEnd:10n,cursor:0n,window:0n,step:1n});let calls=0;
 const stop=temporalControllerSubscribeState(h,s=>{assert.equal(s.disposed,true);calls++;temporalControllerDestroy(h);});
 try{temporalControllerDestroy(h);assert.equal(calls,1);}finally{stop();try{temporalControllerDestroy(h);}catch{}}
});

for(const mapping of [false,true])for(const bytesKind of ['plain','shared','buffer'])test(`snapshot charts and authored styles are isolated mapping=${mapping} bytes=${bytesKind}`,async()=>{
 let q,rawStyle;const packets=await fixture(undefined,async(_,f)=>{q=f.query;rawStyle=f.style;});
 const bytes=h=>Uint8Array.from(Buffer.from(h,'hex')).buffer;
 const source=await RetainedGeoSource.create(bytes(packets.manifest),async()=>bytes(packets.chunk),{budget});
 q={...q,timeRevision:0n,cameraRevision:0n};
 let authored=mapping?{fill:new Uint8Array([255,0,0,255]),stroke:new Uint8Array(4),strokeWidth:0,diameter:6,opacity:1,symbol:0}:rawStyle.slice();
 if(bytesKind==='shared'){
  const copy=bytes=>{const value=new Uint8Array(new SharedArrayBuffer(bytes.length));value.set(bytes);return value;};
  q.sourceDigest=copy(q.sourceDigest);
  if(mapping){authored.fill=copy(authored.fill);authored.stroke=copy(authored.stroke);}
  else authored=copy(authored);
 }
 if(bytesKind==='buffer'){
  q.sourceDigest=Buffer.from(q.sourceDigest);
  if(mapping){authored.fill=Buffer.from(authored.fill);authored.stroke=Buffer.from(authored.stroke);}else authored=Buffer.from(authored);
 }
 const expected=mapping?{...authored,fill:new Uint8Array(authored.fill),stroke:new Uint8Array(authored.stroke)}:new Uint8Array(authored);
 const chart=geoChart(geoLayer('points',{source,layerId:U64,query:q,sequence:1n,style:authored}),{camera:q.camera});
 const h=temporalControllerCreate({instanceId:45n,domainStart:-10n,domainEnd:10n,cursor:0n,window:0n,step:1n}),binding=chart.bindTemporal(h),leases=[];
 try{
  if(mapping){authored.diameter=100;authored.fill[0]=0;}else authored[0]^=255;
  if(bytesKind!=='plain')q.sourceDigest.fill(0);
  const a=await binding.snapshot();leases.push(a.frame);
  assert.deepEqual(a.chart.layers[0].properties.style,expected);
  a.chart.layers[0].properties.query.time.instant=5n;a.chart.camera.zoom=99;
  if(mapping)a.chart.layers[0].properties.style.opacity=0;else a.chart.layers[0].properties.style[0]^=255;
  const b=await binding.snapshot();leases.push(b.frame);
  assert.notEqual(a.chart,b.chart);assert.equal(b.chart.layers[0].source,source);
  assert.deepEqual(b.chart.layers[0].properties.query.time,b.frame.data.identity.time);
  assert.deepEqual(b.chart.layers[0].properties.style,expected);
  const artifact=await b.chart.toImage('svg',{frame:b.frame});await artifact.dispose();
  temporalControllerSetCursor(h,2n);const c=await binding.snapshot();leases.push(c.frame);
  assert.deepEqual(c.chart.layers[0].properties.style,expected);assert.equal(c.frame.data.identity.time.instant,2n);
 }finally{await binding.dispose();for(const f of leases)await f.dispose();await source.dispose();temporalControllerDestroy(h);}
});

test('binding refused during terminal notification leaves no source registration',async()=>{
 let q,style;const packets=await fixture(undefined,async(_,f)=>{q=f.query;style=f.style;});
 const bytes=h=>Uint8Array.from(Buffer.from(h,'hex')).buffer;
 const source=await RetainedGeoSource.create(bytes(packets.manifest),async()=>bytes(packets.chunk),{budget});
 q={...q,timeRevision:0n,cameraRevision:0n};const chart=geoChart(geoLayer('points',{source,layerId:U64,query:q,sequence:1n,style}),{camera:q.camera});
 const create=id=>temporalControllerCreate({instanceId:id,domainStart:-10n,domainEnd:10n,cursor:0n,window:0n,step:1n});
 const h=create(46n);let refusal,other,binding;
 const stop=temporalControllerSubscribeState(h,()=>{try{chart.bindTemporal(h);}catch(error){refusal=error;}});
 try{
  temporalControllerDestroy(h);assert.match(refusal?.message??'',/being destroyed/);
  other=create(47n);binding=chart.bindTemporal(other);await binding.whenIdle();assert.equal(binding.error,undefined);
 }finally{stop();await binding?.dispose();await source.dispose();for(const handle of [h,other])if(handle!==undefined)try{temporalControllerDestroy(handle);}catch{}}
});

test('latest controller intent at the pump completion boundary is not lost',async()=>{
 let q,style;const packets=await fixture(undefined,async(_,f)=>{q=f.query;style=f.style;});
 const bytes=h=>Uint8Array.from(Buffer.from(h,'hex')).buffer;
 const source=await RetainedGeoSource.create(bytes(packets.manifest),async()=>bytes(packets.chunk),{budget});
 q={...q,timeRevision:0n,cameraRevision:0n};const chart=geoChart(geoLayer('points',{source,layerId:U64,query:q,sequence:1n,style}),{camera:q.camera});
 const h=temporalControllerCreate({instanceId:48n,domainStart:-10n,domainEnd:10n,cursor:0n,window:0n,step:1n}),binding=chart.bindTemporal(h);let frame;
 try{
  await binding.whenIdle();temporalControllerSetCursor(h,1n);
  // Arrange a real controller mutation when the admitted operation settles,
  // before the pump's completion reaction. All computation remains native.
  const changed=binding.lock.then(()=>temporalControllerSetCursor(h,2n));
  await changed;await binding.whenIdle();({frame}=await binding.snapshot());
  assert.equal(temporalControllerState(h).cursor,2n);assert.equal(frame.data.identity.time.instant,2n);
 }finally{await binding.dispose();await frame?.dispose();await source.dispose();temporalControllerDestroy(h);}
});
