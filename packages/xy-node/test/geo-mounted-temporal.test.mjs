import {readFile} from 'node:fs/promises';
import assert from 'node:assert/strict';
import test from 'node:test';
import {liveFixture,request,release} from './geo-live-host-fixture.mjs';
import {attachGeoWebview} from '../src/geo-webview.js';
import {temporalControllerCreate,temporalControllerSetCursor,temporalControllerDestroy} from '../src/index.js';
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
