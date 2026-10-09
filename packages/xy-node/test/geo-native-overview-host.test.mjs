import test from 'node:test';
import assert from 'node:assert/strict';
import {overviewHostFixture} from './geo-native-overview-host-fixture.mjs';
import {request,prepare,acknowledge} from './geo-live-host-fixture.mjs';
import {_testConfigureGeneratedAbiTrace} from '../src/native.js';
import {encodeGeoViewportRequest} from '../src/geoviewport.js';
let loseNativeReceipt=false,nativeReceiptCalls=0;
_testConfigureGeneratedAbiTrace(event=>{if(loseNativeReceipt&&event.symbol==='xyg_geo_scale_execute'&&event.outcome==='ok'){nativeReceiptCalls++;throw Error('lost after actual native allocation');}});
const total=frame=>Array.from({length:256},(_,i)=>frame.data.count(i)).reduce((a,b)=>a+b,0n);
test('native overview stage/CAS/retire has exclusive owners and never updates caller current',async()=>{
 const f=await overviewHostFixture(),a=f.adapter;let caller;
 try{
  caller=await f.chart.compileRetained();let [message,buffers]=await request(a,1);assert.ok(!message.error);assert.equal(Buffer.from(buffers[1]).subarray(0,4).toString(),'XYOV');const old=a.frame;assert.notEqual(old,caller);assert.equal(f.index.current,caller);
  let [prepared,candidate]=await prepare(a,{sequence:3n});assert.ok(!prepared.error);assert.equal(a.frame,old);const count=total(caller),tag=candidate[0];buffers=candidate=undefined;assert.ok(!(await acknowledge(a,7,old.handle,2n,tag))[0].error);assert.equal(f.index.current,caller);assert.equal(a.frame.data.final,false);assert.ok((await acknowledge(a,8,old.handle+1n,2n,tag))[0].error);assert.ok(!(await acknowledge(a,8,old.handle,2n,tag))[0].error);assert.throws(()=>old.data,/disposed/);assert.equal(total(caller),count);await caller.dispose();assert.equal(a.frame.sequence,3n);
 }finally{await caller?.dispose();await f.dispose();}
});
test('native overview accepted anchor survives caller/index/source disposal and exact remount',async()=>{
 const f=await overviewHostFixture(),caller=await f.chart.compileRetained();const adapter=f.chart.host({frame:caller});f.adapter.close();await f.adapter.cleanup;f.adapter=adapter;
 try{await adapter.anchorReady;await caller.dispose();await f.index.dispose();await f.seed.dispose();await f.source.dispose();assert.ok(!(await request(adapter,1))[0].error);const old=adapter.frame;assert.equal(old.data.final,false);const [closedQuery]=await prepare(adapter,{sequence:3n});assert.ok(closedQuery.error);assert.equal(closedQuery.prepareAbsent,true);assert.equal(adapter.frame,old);assert.ok((await request(adapter,2,{owner:old.handle,sequence:old.sequence,payload:new ArrayBuffer(32)}))[0].error);assert.equal(adapter.aux,undefined);assert.ok(!(await request(adapter,4,{owner:old.handle,sequence:old.sequence}))[0].error);assert.ok(!(await request(adapter,1,{mount:'replacement'}))[0].error);assert.equal(adapter.frame,old);}finally{await adapter.realmDestroyed();await f.dispose();}
});
test('close during an admitted native page read drains exact cleanup and keeps old mount until release',async()=>{
 const f=await overviewHostFixture({splitTime:true}),a=f.adapter;let release;const gate=new Promise(r=>release=r);let entered;const started=new Promise(r=>entered=r),read=f.control.readPage;
 try{assert.ok(!(await request(a,1))[0].error);const old=a.frame;f.control.readPage=async t=>{entered();await gate;return read(t);};const body=new ArrayBuffer(224),v=new DataView(body);[1n,3n,3n,3n,1n].forEach((n,i)=>v.setBigUint64(i*8,n,true));v.setUint32(40,1,true);v.setBigInt64(48,-1n,true);new Uint8Array(body).set(new Uint8Array(encodeGeoViewportRequest(old.data.identity.camera,3,[1,0])),64);const pending=request(a,6,{version:2,owner:old.handle,sequence:old.sequence,payload:body});await Promise.race([started,new Promise((_,j)=>setTimeout(()=>j(Error('query did not request external page')),5000))]);a.close();assert.equal(a.mounted,true);assert.equal(old.data.final,false);release();const [message]=await pending;assert.ok(message.error);assert.equal(message.prepareAbsent,true);assert.equal(a.liveCandidate.cleanupOperation,undefined);assert.equal(a.liveCandidate.frame,undefined);assert.equal(a.frame,old);assert.ok(!(await request(a,4,{owner:old.handle,sequence:old.sequence}))[0].error);await a.cleanup;assert.throws(()=>old.data,/disposed/);}finally{release();f.control.readPage=read;await f.dispose();}
});

test('native-looking closure producer cannot be retagged into native overview host authority',async()=>{
 const {geoScaleExecute,geoScaleRead}=await import('../src/geoscale.js'),{budget}=await import('./geoscale-fixture.mjs');
 const bridge={execute:b=>geoScaleExecute(b),read:b=>geoScaleRead(b,budget.processorBytes)},f=await overviewHostFixture({bridge,host:false});
 try{assert.throws(()=>f.chart.host(),/genuine native issuing producer/);bridge.execute=geoScaleExecute;bridge.read=geoScaleRead;assert.throws(()=>f.chart.host(),/genuine native issuing producer/);assert.equal(f.index.current,undefined);assert.ok(f.seed.data.record(0).featureId>0n);}finally{await f.dispose();}
});

for(const supplied of [false,true])test(`lost native26 ${supplied?'supplied':'current'} retain keeps genuine pre-dispatch guard`,async()=>{
 const f=await overviewHostFixture({host:false}),caller=await f.chart.compileRetained();let a;
 try{
  if(!supplied)a=f.chart.host();nativeReceiptCalls=0;loseNativeReceipt=true;
  if(supplied){a=f.chart.host({frame:caller});await assert.rejects(a.anchorReady,/uncertain/i);}else{const [reply,buffers]=await request(a,1);assert.ok(reply.error);assert.equal(buffers.length,0);assert.ok((await request(a,1))[0].error);}
  assert.equal(nativeReceiptCalls,1);assert.ok(a.liveCandidate.cleanupOperation);assert.equal(a.mounted,false);assert.equal(caller.data.final,false);
  loseNativeReceipt=false;a.close();await a.cleanup;assert.equal(a.liveCandidate.cleanupOperation,undefined);assert.equal(caller.data.final,false);
 }finally{loseNativeReceipt=false;if(a)await a.realmDestroyed();await caller.dispose();await f.dispose();}
});

test('public overview decorations and outgoing transfer never retag the private remount',async()=>{
 const f=await overviewHostFixture({host:false}),caller=await f.chart.compileRetained();let a,publicData;
 try{
  publicData=caller.data;new Uint8Array(publicData.packet).fill(0);publicData.scene=new Uint8Array(160);publicData.count=()=>0xffffffffffffffffn;
  a=f.chart.host({frame:caller});await a.anchorReady;let [reply,buffers]=await request(a,1);assert.ok(!reply.error);const expected=Buffer.from(buffers[1]).toString('hex'),old=a.frame;assert.equal(total(old),2n);
  structuredClone(buffers[1],{transfer:[buffers[1]]});assert.equal(buffers[1].byteLength,0);buffers=undefined;
  assert.ok(!(await request(a,4,{owner:old.handle,sequence:old.sequence}))[0].error);[reply,buffers]=await request(a,1,{mount:'remounted'});assert.ok(!reply.error);assert.equal(a.frame,old);assert.equal(Buffer.from(buffers[1]).toString('hex'),expected);assert.equal(total(old),2n);buffers=undefined;
 }finally{publicData=undefined;if(a)await a.realmDestroyed();await caller.dispose();await f.dispose();}
});

test('public route and budget shadows cannot redirect overview inspection, update or retirement',async()=>{
 const f=await overviewHostFixture(),a=f.adapter;const {GeoOverviewFrame,overviewFrameAuthority}=await import('../src/geo-overview-source.js'),originalDispose=GeoOverviewFrame.prototype.dispose;
 try{
  Object.defineProperty(a,'overviewMode',{value:false});Object.defineProperty(f.index,'budget',{value:{...f.index.budget,processorBytes:1}});
  let [message,buffers]=await request(a,1);assert.ok(!message.error);assert.equal(Buffer.from(buffers[1]).subarray(0,4).toString(),'XYOV');const old=a.frame;buffers=undefined;
  GeoOverviewFrame.prototype.dispose=()=>{throw Error('public disposal redirected private owner');};let [prepared,candidate]=await prepare(a,{sequence:3n});assert.ok(!prepared.error,prepared.error);const tag=candidate[0];candidate=undefined;
  assert.ok(!(await acknowledge(a,7,old.handle,2n,tag))[0].error);assert.ok(!(await acknowledge(a,8,old.handle,2n,tag))[0].error);assert.equal(overviewFrameAuthority(old),undefined);assert.equal(f.index.current,undefined);
  await a.realmDestroyed();assert.equal(a.mounted,false);
 }finally{GeoOverviewFrame.prototype.dispose=originalDispose;await f.dispose();}
});
