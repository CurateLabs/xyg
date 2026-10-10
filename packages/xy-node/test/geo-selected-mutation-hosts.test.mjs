/** Actual native mutation uncertainty; no recreated State or guessed Source cleanup. */
import test from 'node:test';
import assert from 'node:assert/strict';
import {AsyncResource} from 'node:async_hooks';
import {fixture,budget,U64} from './geoscale-fixture.mjs';
import {createGeoSelectedScope} from '../src/geo-selected.js';
import {nativeGeoScaleBridge,encodeGeoScaleRequest as encode} from '../src/geoscale.js';

for(const fault of ['lost','forged-error','forged-confirm'])test(`actual selected35 ${fault} remains claimed until exact recovery`,async()=>{
 const raw=nativeGeoScaleBridge(budget.processorBytes);let armed=true,scope;const requests=[],deleted=[];
 const bridge={read:r=>raw.read(r),async execute(r){const v=new DataView(r),command=v.getUint32(8,true);if(command===10)deleted.push(v.getBigUint64(16,true));
  if(armed&&fault==='forged-error'&&command===35){armed=false;throw Object.assign(new Error('synthetic rejection'),{nativeCode:-9,name:'XygWasmError',status:3,wasmStatus:3});}
  if(command===35)requests.push(r.slice(0));const reply=await raw.execute(r);
  if(armed&&(fault==='lost'&&command===35||fault==='forged-confirm'&&command===47)){armed=false;if(fault==='lost')throw new Error('lost after actual35');return reply.slice(0);}
  return reply;
 }};
 try{await fixture(bridge,async(original,f)=>{
  const source=original.data.identity.sessionHandle;
  scope=await createGeoSelectedScope(bridge,{frameHandle:original.handle,sequence:1n,namespace:U64,layerId:U64,budget});
  const state=await scope.state({revision:U64,ids:new BigUint64Array([U64]),fill:new Uint8Array([0,255,0,255]),budget});
  await assert.rejects(state.begin({command:35,handle:source,sequence:2n,query:f.query,budget}));assert.throws(()=>state.check(),/active/);
  const recovered=await state.pendingOperation.recover();assert.equal(recovered.fallback,false);
  if(fault==='lost'){assert.equal(requests.length,2);assert.deepEqual(requests[0],requests[1]);}
  const operation=recovered.operation;await operation.drive({readChunk:f.readChunk});await operation.cancel();await state.pendingOperation.dispose();
  assert(!deleted.includes(source));assert.equal(original.data.record(0).featureId,U64);
 });}finally{if(scope)await scope.dispose();}
});

test('numeric legacy repeated Scopes reclaim journal bank only after original Source disposal',async()=>{
 const bridge=nativeGeoScaleBridge(budget.processorBytes);
 for(let i=0;i<20;i++){let scope;try{await fixture(bridge,async(original,f)=>{
  scope=await createGeoSelectedScope(bridge,{frameHandle:original.handle,sequence:1n,namespace:U64,layerId:U64,budget});
  const state=await scope.state({revision:U64,ids:new BigUint64Array(),fill:new Uint8Array([0,255,0,255]),budget});
  const accepted=await state.begin({command:35,handle:original.data.identity.sessionHandle,sequence:2n,query:f.query,budget});await accepted.operation.cancel();
 });}finally{if(scope)await scope.dispose();}}
});

test('actual36 forged fallback remains uncertain; exact replay owns Query and never replacement Data',async()=>{
 const {GeoSpatialIndex}=await import('../src/geo-spatial.js');const raw=nativeGeoScaleBridge(budget.processorBytes);let armed=false,scope,index,frame;const requests=[];
 const bridge={read:r=>raw.read(r),async execute(r){const reply=await raw.execute(r),v=new DataView(r);if(v.getUint32(8,true)===36){requests.push(r.slice(0));if(armed){armed=false;const forged=reply.slice(0),f=new DataView(forged);f.setUint32(8,10,true);f.setBigUint64(16,v.getBigUint64(16,true),true);f.setUint32(48,2,true);return forged;}}return reply;}};
 try{await fixture(bridge,async(original,f)=>{
  const pages=new Map();index=await GeoSpatialIndex._fromFrame(original,{bridge,budget,readChunk:f.readChunk},{grid:16,maxVertices:1000000n,readPage:async t=>pages.get(t.page),writePage:async(t,b)=>{pages.set(t.page,b.slice());}});
  scope=await createGeoSelectedScope(bridge,{frameHandle:original.handle,sequence:1n,namespace:U64,layerId:U64,budget});
  const state=await scope.state({revision:U64,ids:new BigUint64Array([U64]),fill:new Uint8Array([0,255,0,255]),budget});armed=true;
  await assert.rejects(state.begin({command:36,handle:index.handle,sequence:2n,query:f.query,budget}),/genuine producer/);assert.throws(()=>state.check(),/active/);
  const accepted=await state.pendingOperation.recover();assert.equal(accepted.fallback,false);assert.deepEqual(requests[0],requests[1]);
  await accepted.operation.drive({readPage:async t=>pages.get(t.page)});frame=await accepted.operation.prepare(f.style);assert.equal(frame.handle,state.handle);
  await state.pendingOperation.dispose();assert.equal(frame.data.record(0).featureId,U64);await index.dispose();await frame.dispose();frame=undefined;
 });}finally{if(frame)await frame.dispose();if(index)await index.dispose();if(scope)await scope.dispose();}
});

test('genuine nonjournaled36 fallback preserves State and sequence for corrected admission',async()=>{
 const {GeoSpatialIndex}=await import('../src/geo-spatial.js'),raw=nativeGeoScaleBridge(budget.processorBytes);let scope,index,frame,state;
 const bridge={read:r=>{if(new DataView(r).getUint32(8,true)===20){r=r.slice(0);new DataView(r).setFloat64(256+32+80,90,true);}return raw.read(r);},async execute(r){const command=new DataView(r).getUint32(8,true),reply=await raw.execute(r);if(command===2)await raw.execute(r.slice(0));return reply;}};
 try{await fixture(bridge,async(original,f)=>{
  const pages=new Map();index=await GeoSpatialIndex._fromFrame(original,{bridge,budget,readChunk:f.readChunk},{grid:16,maxVertices:1000000n,readPage:async t=>pages.get(t.page),writePage:async(t,b)=>{pages.set(t.page,b.slice());}});
  scope=await createGeoSelectedScope(bridge,{frameHandle:original.handle,sequence:1n,namespace:U64,layerId:U64,budget});state=await scope.state({revision:U64,ids:new BigUint64Array([U64]),fill:new Uint8Array([0,255,0,255]),budget});
  const fallback=await state.begin({command:36,handle:index.handle,sequence:2n,query:f.query,budget:{...budget,maxChunks:1}});assert.equal(fallback.fallback,true);assert.equal(fallback.reason,2);state.check();
  const accepted=await state.begin({command:36,handle:index.handle,sequence:2n,query:f.query,budget});assert.equal(accepted.fallback,false);await accepted.operation.drive({readPage:async t=>pages.get(t.page)});frame=await accepted.operation.prepare(f.style);assert.equal(frame.data.selection.visibleVertices,2n);await state.pendingOperation.dispose();await frame.dispose();frame=undefined;
 });}finally{if(state?.pendingOperation)await state.pendingOperation.dispose();if(state)await state.dispose();if(frame)await frame.dispose();if(index)await index.dispose();if(scope)await scope.dispose();}
});

test('packet mutation after scoped validation cannot turn accepted36 into fallback',async()=>{
 const {GeoSpatialIndex}=await import('../src/geo-spatial.js'),raw=nativeGeoScaleBridge(budget.processorBytes);let scope,index,frame,mutated=false,state;
 const bridge={read:r=>raw.read(r),async execute(r){const reply=await raw.execute(r),request=new DataView(r);if(request.getUint32(8,true)===36){const issuer=request.getBigUint64(16,true);Promise.resolve().then(()=>queueMicrotask(()=>{const v=new DataView(reply);v.setUint32(8,10,true);v.setBigUint64(16,issuer,true);v.setUint32(48,2,true);mutated=true;}));}return reply;}};
 try{await fixture(bridge,async(original,f)=>{
  const pages=new Map();index=await GeoSpatialIndex._fromFrame(original,{bridge,budget,readChunk:f.readChunk},{grid:16,maxVertices:1000000n,readPage:async t=>pages.get(t.page),writePage:async(t,b)=>{pages.set(t.page,b.slice());}});
  scope=await createGeoSelectedScope(bridge,{frameHandle:original.handle,sequence:1n,namespace:U64,layerId:U64,budget});state=await scope.state({revision:U64,ids:new BigUint64Array([U64]),fill:new Uint8Array([0,255,0,255]),budget});
  const accepted=await state.begin({command:36,handle:index.handle,sequence:2n,query:f.query,budget});assert.equal(mutated,true);assert.equal(accepted.fallback,false);assert.throws(()=>state.check(),/unavailable/);await accepted.operation.drive({readPage:async t=>pages.get(t.page)});frame=await accepted.operation.prepare(f.style);assert.equal(frame.data.selection.visibleVertices,1n);await state.pendingOperation.dispose();await frame.dispose();frame=undefined;
 });}finally{if(state?.pendingOperation)await state.pendingOperation.dispose();if(frame)await frame.dispose();if(state)try{await raw.execute(encode({command:10,handle:state.handle}));}catch{/*Exact test-owned Query may already have retired.*/}if(index)await index.dispose();if(scope)await scope.dispose();}
});

test('lost selected19 publication retains guard and never guesses replacement Data cleanup',async()=>{
 const {GeoSpatialIndex}=await import('../src/geo-spatial.js'),raw=nativeGeoScaleBridge(budget.processorBytes);let scope,index,dataHandle,state;const deleted=[];
 const bridge={read:r=>raw.read(r),async execute(r){const request=new DataView(r),command=request.getUint32(8,true);if(command===10)deleted.push(request.getBigUint64(16,true));const reply=await raw.execute(r);if(command===19){dataHandle=new DataView(reply).getBigUint64(16,true);throw new Error('lost actual19 Data reply');}return reply;}};
 try{await fixture(bridge,async(original,f)=>{
  const pages=new Map();index=await GeoSpatialIndex._fromFrame(original,{bridge,budget,readChunk:f.readChunk},{grid:16,maxVertices:1000000n,readPage:async t=>pages.get(t.page),writePage:async(t,b)=>{pages.set(t.page,b.slice());}});
  scope=await createGeoSelectedScope(bridge,{frameHandle:original.handle,sequence:1n,namespace:U64,layerId:U64,budget});state=await scope.state({revision:U64,ids:new BigUint64Array([U64]),fill:new Uint8Array([0,255,0,255]),budget});const accepted=await state.begin({command:36,handle:index.handle,sequence:2n,query:f.query,budget});await accepted.operation.drive({readPage:async t=>pages.get(t.page)});
  await assert.rejects(accepted.operation.prepare(f.style),/lost actual19/);await assert.rejects(state.pendingOperation.dispose(),/publication remains uncertain/);await assert.rejects(accepted.operation.dispose(),/publication remains uncertain/);await assert.rejects(accepted.operation.cancel(),/publication remains uncertain/);assert(!deleted.includes(dataHandle));assert.equal(original.data.record(0).featureId,U64);const packet=await raw.read(encode({command:23,handle:dataHandle}));assert.equal(new DataView(packet).getBigUint64(24,true),2n);
 });}finally{if(dataHandle)await raw.execute(encode({command:10,handle:dataHandle}));if(index)await index.dispose();if(scope)await scope.dispose();}
});

function selectedAck(issuer,action){const payload=new Uint8Array(16),v=new DataView(payload.buffer);v.setUint32(0,35,true);v.setUint32(4,action,true);v.setBigUint64(8,issuer,true);const r=encode({command:6,handle:issuer,sequence:2n,payload}),h=new DataView(r);h.setUint32(8,47,true);h.setBigUint64(240,1n,true);return r;}
async function fullReceiptBank(raw){const issuers=[];for(let i=0;i<16;i++){let scope;try{await fixture(raw,async(original,f)=>{
 scope=await createGeoSelectedScope(raw,{frameHandle:original.handle,sequence:1n,namespace:U64,layerId:U64,budget});const state=await scope.state({revision:U64,ids:new BigUint64Array([U64]),fill:new Uint8Array([0,255,0,255]),budget}),issuer=original.data.identity.sessionHandle;
 const payload=new Uint8Array(8);new DataView(payload.buffer).setBigUint64(0,state.handle,true);const r=encode({command:35,handle:issuer,sequence:2n,query:f.query,budget,payload});new DataView(r).setBigUint64(240,1n,true);await raw.execute(r);await raw.execute(selectedAck(issuer,0));await raw.execute(encode({command:9,handle:issuer,sequence:2n}));await raw.execute(selectedAck(issuer,2));issuers.push(issuer);
 });}finally{if(scope)await scope.dispose();}}return issuers;}
for(const older of ['prior-call','same-call-clone','escaped-context','nested-capture'])test(`older genuine rejection from ${older} cannot clear accepted35 ownership`,async()=>{
 const raw=nativeGeoScaleBridge(budget.processorBytes),held=await fullReceiptBank(raw);let scope,saved,armed=true;
 const bridge={read:r=>raw.read(r),async execute(r){if(new DataView(r).getUint32(8,true)===35&&armed){armed=false;
  if(older!=='prior-call'){try{await raw.execute(r);}catch(error){assert.equal(error.nativeCode,-9);saved=error;}assert(saved);await raw.execute(selectedAck(held.pop(),1));}
  if(older==='escaped-context'){const resource=new AsyncResource('selected-external',{triggerAsyncId:0});try{await resource.runInAsyncScope(()=>raw.execute(r.slice(0)));}finally{resource.emitDestroy();}}else if(older==='nested-capture'){const {withGeoNativeMutationOutcome}=await import('../src/geoscale.js');await withGeoNativeMutationOutcome(raw,r,()=>raw.execute(r.slice(0)));}else await raw.execute(r.slice(0));throw saved;
 }return raw.execute(r);}};
 try{await fixture(bridge,async(original,f)=>{
  scope=await createGeoSelectedScope(bridge,{frameHandle:original.handle,sequence:1n,namespace:U64,layerId:U64,budget});const state=await scope.state({revision:U64,ids:new BigUint64Array([U64]),fill:new Uint8Array([0,255,0,255]),budget});
  if(older==='prior-call'){const payload=new Uint8Array(8);new DataView(payload.buffer).setBigUint64(0,state.handle,true);const r=encode({command:35,handle:original.data.identity.sessionHandle,sequence:2n,query:f.query,budget,payload});new DataView(r).setBigUint64(240,1n,true);try{await raw.execute(r);}catch(error){assert.equal(error.nativeCode,-9);saved=error;}assert(saved);await raw.execute(selectedAck(held.pop(),1));}
  await assert.rejects(state.begin({command:35,handle:original.data.identity.sessionHandle,sequence:2n,query:f.query,budget}));assert.throws(()=>state.check(),/active/);const accepted=await state.pendingOperation.recover();assert.equal(accepted.fallback,false);await accepted.operation.cancel();await state.pendingOperation.dispose();assert.equal(original.data.record(0).featureId,U64);
 });}finally{if(scope)await scope.dispose();for(const issuer of held)await raw.execute(selectedAck(issuer,1));}
});
