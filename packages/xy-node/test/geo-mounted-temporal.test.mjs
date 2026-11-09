import {readFile} from 'node:fs/promises';
import assert from 'node:assert/strict';
import test from 'node:test';
import {liveFixture,request,release} from './geo-live-host-fixture.mjs';
import {attachGeoWebview} from '../src/geo-webview.js';
import {temporalControllerCreate,temporalControllerSetCursor,temporalControllerSetRange,temporalControllerDestroy} from '../src/index.js';
const turn=()=>new Promise(resolve=>setImmediate(resolve));
function panelFixture(){let receive,disposed;const sent=[];return {sent,receive:message=>receive({message,buffers:[]}),panel:{webview:{onDidReceiveMessage(callback){receive=callback;return {dispose(){}};},async postMessage(envelope){sent.push(envelope);return true;}},onDidDispose(callback){disposed=callback;return {dispose(){}};},dispose(){disposed();}}};}
test('mounted bounds, stale mount completion, shared claim, drain failure and retry',{timeout:10000},async()=>{
 const f=await liveFixture(),p=panelFixture(),host=attachGeoWebview(p.panel,f.adapter);
 const h=temporalControllerCreate({instanceId:23n,domainStart:-(1n<<63n),domainEnd:(1n<<63n)-1n,cursor:0n,window:0n,step:1n});
 const binding=host.bindTemporal(h);
 try{
  assert.throws(()=>f.chart.bindTemporal(h),/already/);await turn();assert.equal(p.sent.length,0);
  await request(f.adapter,1,{mount:'real'});
  p.receive({type:'geo_host_ready',mount:'foreign'});await turn();assert.equal(p.sent.length,0);
  p.receive({type:'geo_host_ready',mount:'real'});await turn();const first=p.sent[0].message;const framing=JSON.parse(await readFile(new URL('../../../tests/fixtures/geo_mounted_temporal.json',import.meta.url)));assert.equal(Buffer.from(p.sent[0].buffers[0]).toString('hex'),framing.instantZero);
  for(let i=0;i<1000;i++)temporalControllerSetCursor(h,BigInt(i));await turn();assert.equal(p.sent.length,2);
  p.receive({...first,type:'geo_host_temporal_done',mount:'old',status:'accepted',drained:true});await turn();assert.equal(p.sent.length,2);
  p.receive({...first,type:'geo_host_temporal_done',status:'superseded',drained:true});await turn();const last=p.sent.at(-1);assert.equal(new DataView(last.buffers[0]).getBigInt64(16,true),999n);
  const closing=binding.dispose();await turn();assert.throws(()=>f.chart.bindTemporal(h),/already/);
  p.receive({...last.message,type:'geo_host_temporal_done',status:'failed',drained:false,error:'lost abort ACK'});await assert.rejects(closing,/lost abort/);
  const retry=binding.dispose();await turn();assert.equal(new DataView(p.sent.at(-1).buffers[0]).getUint32(8,true),4);
  p.receive({...last.message,type:'geo_host_temporal_done',status:'superseded',drained:true});await retry;
  const other=f.chart.bindTemporal(h);await other.dispose();assert.equal(f.adapter.frame.data.record(0).featureId,(1n<<64n)-1n);
 }finally{await release(f);temporalControllerDestroy(h);}
});
test('premount disposal and real realm destruction settle idle and source claim',{timeout:10000},async()=>{
 const f=await liveFixture(),p=panelFixture(),host=attachGeoWebview(p.panel,f.adapter);
 const h=temporalControllerCreate({instanceId:24n,domainStart:-100n,domainEnd:100n,cursor:0n,window:0n,step:1n});
 try{const b=host.bindTemporal(h),idle=b.whenIdle();await b.dispose();await idle;assert.equal(p.sent.length,0);
  const next=host.bindTemporal(h);p.panel.dispose();await next.whenIdle();await next.dispose();assert.equal(f.adapter.mounted,false);
 }finally{await release(f);temporalControllerDestroy(h);}
});

test('selected mounted replacements retire each canonical query birth without raising caps',async()=>{
 const {mountedFixture}=await import('./geo-mounted-temporal-fixture.mjs');
 const {prepare,acknowledge}=await import('./geo-live-host-fixture.mjs');
 const f=await mountedFixture();let caller;
 try{await request(f.adapter,1);caller=await f.adapter.frame.retain();
  for(let n=3n;n<28n;n++){const old=f.adapter.frame,sequence=f.adapter.sequence;
   const [reply,packets]=await prepare(f.adapter,{nonce:n,sequence:n});assert.equal(reply.error,undefined);
   assert.equal((await acknowledge(f.adapter,7,old.handle,sequence,packets[0]))[0].error,undefined);
   assert.equal((await acknowledge(f.adapter,8,old.handle,sequence,packets[0]))[0].error,undefined);
   assert.equal(f.adapter.frame.data.selection.id(0),0xffffffffffffffffn);
  }
  assert.equal(caller.data.record(0).featureId,0xffffffffffffffffn);
 }finally{await caller?.dispose();await release(f);await f.scope.dispose();}
});

test('postMessage rejection and failed realm cleanup retain retryable source exclusion',{timeout:10000},async()=>{
 const f=await liveFixture(),p=panelFixture(),host=attachGeoWebview(p.panel,f.adapter);
 const h=temporalControllerCreate({instanceId:25n,domainStart:-100n,domainEnd:100n,cursor:0n,window:0n,step:1n});
 const original=p.panel.webview.postMessage;let fail=true;
 p.panel.webview.postMessage=async envelope=>{if(fail&&envelope.message.type==='geo_host_temporal')return false;return original(envelope);};
 const b=host.bindTemporal(h);
 try{await request(f.adapter,1,{mount:'real'});p.receive({type:'geo_host_ready',mount:'real'});await b.whenIdle();assert.match(b.error.message,/rejected/);
  await assert.rejects(b.dispose(),/rejected/);assert.throws(()=>f.chart.bindTemporal(h),/already/);
  fail=false;const retry=b.dispose();await turn();const drain=p.sent.at(-1).message;
  p.receive({...drain,type:'geo_host_temporal_done',status:'superseded',drained:true});await retry;
  const next=host.bindTemporal(h);await turn();const destroy=f.adapter.realmDestroyed.bind(f.adapter);let rejectCleanup=true;
  f.adapter.realmDestroyed=async()=>{if(rejectCleanup)throw Error('native teardown rejected');return destroy();};
  p.panel.dispose();await turn();assert.throws(()=>f.chart.bindTemporal(h),/already/);rejectCleanup=false;await host.dispose();await next.dispose();assert.equal(f.adapter.mounted,false);
 }finally{await release(f);temporalControllerDestroy(h);}
});

for(const selected of [false,true])test(`indexed mounted ${selected?'selected':'ordinary'} native replacement, fallback and disposal`,{timeout:15000},async()=>{
 const {mountedIndexedFixture}=await import('./geo-mounted-indexed-temporal-fixture.mjs');
 const {prepare,acknowledge}=await import('./geo-live-host-fixture.mjs');
 const f=await mountedIndexedFixture({selected}),p=panelFixture(),host=attachGeoWebview(p.panel,f.adapter);
 const h=temporalControllerCreate({instanceId:selected?63n:62n,domainStart:-(1n<<63n),domainEnd:(1n<<63n)-1n,cursor:0n,window:0n,step:1n});
 const prototype=Object.getPrototypeOf(f.source);class UnissuedSubclass extends f.source.constructor{}
 try{Object.setPrototypeOf(f.source,UnissuedSubclass.prototype);assert.throws(()=>host.bindTemporal(h),/spatial index required/);}finally{Object.setPrototypeOf(f.source,prototype);}
 const binding=host.bindTemporal(h);let caller,unblock;
 try{
  assert.throws(()=>host.bindTemporal(h),/already/);
  // Snapshot binding remains outside this indexed mounted slice.
  assert.throws(()=>f.chart.bindTemporal(h),/canonical retained/);
  await request(f.adapter,1,{mount:'native'});caller=await f.adapter.frame.retain();const originalCurrent=f.source.current;
  p.receive({type:'geo_host_ready',mount:'native'});await turn();const active=p.sent.at(-1).message;
  for(let n=0;n<1000;n++)temporalControllerSetCursor(h,BigInt(n));await turn();assert.equal(p.sent.length,2);
  p.receive({...active,type:'geo_host_temporal_done',status:'superseded',drained:true});await turn();const last=p.sent.at(-1);
  assert.equal(new DataView(last.buffers[0]).getBigInt64(16,true),999n);
  p.receive({...last.message,type:'geo_host_temporal_done',status:'failed',drained:false,error:'lost indexed ACK'});await binding.whenIdle();assert.match(binding.error.message,/lost indexed/);
  const draining=binding.dispose();await turn();const retry=p.sent.findLast(e=>new DataView(e.buffers[0]).getUint32(8,true)===4);assert.ok(retry);assert.deepEqual(retry.message,last.message);
  p.receive({...last.message,type:'geo_host_temporal_done',status:'superseded',drained:true});await draining;
  // Real native replacements cross the fixed selected birth-bank capacity.
  for(let n=3n;n<28n;n++){
   const old=f.adapter.frame,sequence=f.adapter.sequence,[reply,packets]=await prepare(f.adapter,{nonce:n,sequence:n});assert.equal(reply.error,undefined);
   assert.equal((await acknowledge(f.adapter,7,old.handle,sequence,packets[0]))[0].error,undefined);
   assert.equal((await acknowledge(f.adapter,8,old.handle,sequence,packets[0]))[0].error,undefined);
   assert.equal(f.adapter.frame.data.length,2);assert.equal(f.adapter.frame.data.record(0).featureId,0xffffffffffffffffn);
   if(selected)assert.equal(f.adapter.frame.data.selection.id(0),0xffffffffffffffffn);
  }
  const good=f.adapter.frame,cap=f.source.budget.maxChunks;f.source.budget.maxChunks=1;
  assert.match((await prepare(f.adapter,{nonce:28n,sequence:28n}))[0].error,/explicit canonical full-source scan/);assert.equal(f.adapter.frame,good);f.source.budget.maxChunks=cap;
  const reader=f.source.readPage;let enter;const entered=new Promise(r=>enter=r),gate=new Promise(r=>unblock=r);
  f.source.readPage=async ticket=>{enter();await gate;return reader(ticket);};
  const pending=prepare(f.adapter,{nonce:29n,sequence:29n});await entered;let closed=false;const closing=f.source.dispose().then(()=>closed=true);await turn();assert.equal(closed,false);unblock();assert.match((await pending)[0].error,/abort|cancel|closing|disposed/i);await closing;
  assert.equal(f.adapter.frame,good);assert.equal(caller.data.record(0).featureId,0xffffffffffffffffn);assert.equal(f.source.current,originalCurrent);assert.equal(f.canonicalReads(),0);assert.ok(f.pageReads()>0);
 }finally{unblock?.();p.panel.dispose();await host.dispose();await binding.dispose();await caller?.dispose();await release(f);await f.scope?.dispose();temporalControllerDestroy(h);}
});

for(const mode of ['cursor','range'])test(`hierarchy temporal ${mode} remount advertises a cancelled native query sequence`, {timeout:15000}, async()=>{
 const {mountedHierarchyFixture,release:releaseHierarchy}=await import('./geo-mounted-hierarchy-temporal-fixture.mjs');
 const {prepare,acknowledge}=await import('./geo-live-host-fixture.mjs');
 const f=await mountedHierarchyFixture(),p=panelFixture(),host=attachGeoWebview(p.panel,f.adapter);
 const h=temporalControllerCreate({instanceId:62n,domainStart:-100n,domainEnd:100n,cursor:23n,window:0n,step:1n});
 let binding;
 try{
  await request(f.adapter,1);
  const accepted=f.adapter.frame,sequence=f.adapter.sequence,sourceSequence=f.source.sequence;
  const malformed=new ArrayBuffer(224),mv=new DataView(malformed);[1n,0xffffffffffffffffn,1n,1n,1n].forEach((n,i)=>mv.setBigUint64(i*8,n,true));
  assert.ok((await request(f.adapter,6,{version:2,owner:accepted.handle,sequence,payload:malformed}))[0].error);assert.equal(f.adapter.liveCandidate.sequenceFloor,sequence);
  const [message,packets]=await prepare(f.adapter,{nonce:1n,sequence:4n});assert.equal(message.error,undefined);
  assert.equal((await acknowledge(f.adapter,9,accepted.handle,sequence,packets[0]))[0].error,undefined);
  assert.equal(f.source.sequence,sourceSequence);assert.equal(f.lane.sequence,4n);
  assert.equal((await request(f.adapter,4,{owner:accepted.handle,sequence}))[0].error,undefined);
  assert.equal((await request(f.adapter,1))[0].error,undefined);
  assert.equal(f.adapter.frame,accepted);assert.equal(f.adapter.sequence,sequence);
  temporalControllerSetRange(h,23n,24n);binding=host.bindTemporal(h,mode);p.receive({type:'geo_host_ready',mount:'native'});await turn();
  const sent=p.sent.at(-1),v=new DataView(sent.buffers[0]);assert.equal(v.getBigUint64(32,true),4n);
  const framing=JSON.parse(await readFile(new URL('../../../tests/fixtures/geo_mounted_temporal.json',import.meta.url)));assert.equal(Buffer.from(sent.buffers[0]).toString('hex'),framing[mode==='cursor'?'hierarchyAfterAbortCursor':'hierarchyAfterAbortRange']);
  assert.ok(v.getBigUint64(32,true)>f.adapter.sequence);
  p.receive({...sent.message,type:'geo_host_temporal_done',status:'superseded',drained:true});await binding.dispose();
  const next=await prepare(f.adapter,{nonce:1n,sequence:v.getBigUint64(32,true)+1n});assert.equal(next[0].error,undefined);
  assert.equal((await acknowledge(f.adapter,7,accepted.handle,sequence,next[1][0]))[0].error,undefined);
  assert.equal((await acknowledge(f.adapter,8,accepted.handle,sequence,next[1][0]))[0].error,undefined);
  assert.equal(f.adapter.frame.data.selection.id(0),0xffffffffffffffffn);
 }finally{if(binding?.active)p.receive({...binding.active,type:'geo_host_temporal_done',status:'superseded',drained:true});await binding?.dispose();await releaseHierarchy(f);await f.scope.dispose();temporalControllerDestroy(h);}
});
