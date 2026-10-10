/** Actual native mutation uncertainty; no recreated State or guessed Source cleanup. */
import test from 'node:test';
import assert from 'node:assert/strict';
import {AsyncResource} from 'node:async_hooks';
import {fixture,budget,U64} from './geoscale-fixture.mjs';
import {createGeoSelectedScope} from '../src/geo-selected.js';
import {nativeGeoScaleBridge,encodeGeoScaleRequest as encode} from '../src/geoscale.js';

test('lost selected19 publication recovers exact Data after lost receipt',async()=>{
 const {GeoSpatialIndex}=await import('../src/geo-spatial.js'),raw=nativeGeoScaleBridge(budget.processorBytes);let scope,index,dataHandle,state,frame,armed=true;const deleted=[];
 const bridge={read:r=>raw.read(r),async execute(r){const request=new DataView(r),command=request.getUint32(8,true);if(command===10)deleted.push(request.getBigUint64(16,true));const reply=await raw.execute(r);if(command===19&&armed){armed=false;dataHandle=new DataView(reply).getBigUint64(16,true);throw new Error('lost actual19 Data reply');}return reply;}};
 try{await fixture(bridge,async(original,f)=>{
  const pages=new Map();index=await GeoSpatialIndex._fromFrame(original,{bridge,budget,readChunk:f.readChunk},{grid:16,maxVertices:1000000n,readPage:async t=>pages.get(t.page),writePage:async(t,b)=>{pages.set(t.page,b.slice());}});
  scope=await createGeoSelectedScope(bridge,{frameHandle:original.handle,sequence:1n,namespace:U64,layerId:U64,budget});state=await scope.state({revision:U64,ids:new BigUint64Array([U64]),fill:new Uint8Array([0,255,0,255]),budget});const accepted=await state.begin({command:36,handle:index.handle,sequence:2n,query:f.query,budget});await accepted.operation.drive({readPage:async t=>pages.get(t.page)});
  await assert.rejects(accepted.operation.prepare(f.style),/lost actual19/);assert(accepted.operation.publicationPending);assert(!deleted.includes(dataHandle));frame=await accepted.operation.prepare(f.style);assert.equal(frame.handle,dataHandle);assert.equal(frame.data.record(0).featureId,U64);await state.pendingOperation.dispose();await index.dispose();index=undefined;assert.equal(frame.data.selection.visibleVertices,1n);await frame.dispose();frame=undefined;dataHandle=undefined;
 });}finally{if(frame)await frame.dispose();else if(dataHandle)await raw.execute(encode({command:10,handle:dataHandle}));if(index)await index.dispose();if(scope)await scope.dispose();}
});


for(const fault of ['confirm','read','lost10','forget','microtask'])test(`actual19 ${fault} settles its distinct Data lifetime`,async()=>{
 const {GeoSpatialIndex}=await import('../src/geo-spatial.js'),raw=nativeGeoScaleBridge(budget.processorBytes);let armed=true,scope,index,frame,op,dataHandle;const issued=[],deleted=[];
 const bridge={async read(r){const reply=await raw.read(r);if(armed&&fault==='read'&&new DataView(r).getUint32(8,true)===23&&new DataView(r).getBigUint64(16,true)===dataHandle){armed=false;throw Error('lost read');}return reply;},async execute(r){const request=r.slice(0),v=new DataView(request),command=v.getUint32(8,true);if(command===10)deleted.push(v.getBigUint64(16,true));const reply=await raw.execute(r);
  if(command===19){dataHandle=new DataView(reply).getBigUint64(16,true);issued.push(request);if(fault==='microtask'&&armed){armed=false;Promise.resolve().then(()=>queueMicrotask(()=>{const v=new DataView(reply);v.setBigUint64(16,999999n,true);v.setBigUint64(32,1n,true);}));}}
  if(armed&&(fault==='confirm'&&command===47&&v.getUint32(256,true)===19&&v.getUint32(260,true)===0||fault==='lost10'&&command===10&&v.getBigUint64(16,true)===dataHandle||fault==='forget'&&command===47&&v.getUint32(256,true)===19&&v.getUint32(260,true)===1)){armed=false;throw Error('lost '+fault);}return reply;
 }};
 try{await fixture(bridge,async(original,f)=>{const pages=new Map();index=await GeoSpatialIndex._fromFrame(original,{bridge,budget,readChunk:f.readChunk},{grid:16,maxVertices:1000000n,readPage:async t=>pages.get(t.page),writePage:async(t,b)=>pages.set(t.page,b.slice())});scope=await createGeoSelectedScope(bridge,{frameHandle:original.handle,sequence:1n,namespace:U64,layerId:U64,budget});const state=await scope.state({revision:U64,ids:BigUint64Array.of(U64),fill:Uint8Array.of(0,255,0,255),budget});op=(await state.begin({command:36,handle:index.handle,sequence:2n,query:f.query,budget})).operation;await op.drive({readPage:async t=>pages.get(t.page)});
  if(['confirm','read'].includes(fault)){await assert.rejects(op.prepare(f.style),/lost/);assert(op.publicationPending);assert(!deleted.includes(dataHandle));await assert.rejects(op.prepare(new Uint8Array(48)),/original style/);}
  frame=await op.prepare(f.style);assert.equal(frame.handle,dataHandle);assert.equal(frame.data.record(0).featureId,U64);const {geoSceneDataAuthority}=await import('../src/geoscale.js'),authority=geoSceneDataAuthority(frame);assert.equal(authority.bridge,bridge);assert.equal(authority.request.byteLength,304);assert.notEqual(new DataView(authority.request).getBigUint64(240,true),0n);await state.pendingOperation.dispose();await index.dispose();index=undefined;
  if(fault==='forget')await assert.rejects(frame.dispose(),/lost forget/);await frame.dispose();frame=undefined;assert.equal(original.data.record(0).featureId,U64);
 });}finally{if(frame)await frame.dispose();if(index)await index.dispose();if(scope)await scope.dispose();}
});

test('20 sequential19 publications reclaim bounded16 host and engine banks',async()=>{
 const {GeoSpatialIndex}=await import('../src/geo-spatial.js'),bridge=nativeGeoScaleBridge(budget.processorBytes);let index,scope;
 try{await fixture(bridge,async(original,f)=>{const pages=new Map();index=await GeoSpatialIndex._fromFrame(original,{bridge,budget,readChunk:f.readChunk},{grid:16,maxVertices:1000000n,readPage:async t=>pages.get(t.page),writePage:async(t,b)=>pages.set(t.page,b.slice())});scope=await createGeoSelectedScope(bridge,{frameHandle:original.handle,sequence:1n,namespace:U64,layerId:U64,budget});
  for(let i=0;i<20;i++){const state=await scope.state({revision:U64,ids:BigUint64Array.of(U64),fill:Uint8Array.of(0,255,0,255),budget}),op=(await state.begin({command:36,handle:index.handle,sequence:BigInt(i+2),query:f.query,budget})).operation;await op.drive({readPage:async t=>pages.get(t.page)});const frame=await op.prepare(f.style);assert.equal(frame.data.selection.visibleVertices,1n);await frame.dispose();await state.pendingOperation.dispose();}
 });}finally{if(index)await index.dispose();if(scope)await scope.dispose();}
});

test('knownData two failed reads remain owned until exact cleanup, never recreated19',async()=>{
 const {GeoSpatialIndex}=await import('../src/geo-spatial.js'),raw=nativeGeoScaleBridge(budget.processorBytes);let scope,index,op,handle,reads=0,publications=0;
 const bridge={async execute(r){const reply=await raw.execute(r);if(new DataView(r).getUint32(8,true)===19){publications++;handle=new DataView(reply).getBigUint64(16,true);}return reply;},async read(r){const reply=await raw.read(r);if(new DataView(r).getUint32(8,true)===23&&new DataView(r).getBigUint64(16,true)===handle){reads++;throw Error('lost read'+reads);}return reply;}};
 try{await fixture(bridge,async(original,f)=>{const pages=new Map();index=await GeoSpatialIndex._fromFrame(original,{bridge,budget,readChunk:f.readChunk},{grid:16,maxVertices:1000000n,readPage:async t=>pages.get(t.page),writePage:async(t,b)=>pages.set(t.page,b.slice())});scope=await createGeoSelectedScope(bridge,{frameHandle:original.handle,sequence:1n,namespace:U64,layerId:U64,budget});const state=await scope.state({revision:U64,ids:BigUint64Array.of(U64),fill:Uint8Array.of(0,255,0,255),budget});op=(await state.begin({command:36,handle:index.handle,sequence:2n,query:f.query,budget})).operation;await op.drive({readPage:async t=>pages.get(t.page)});await assert.rejects(op.prepare(f.style),/lost read1/);await assert.rejects(op.prepare(f.style),/lost read2/);await assert.rejects(op.prepare(f.style),e=>e.nativeCode===-9);assert.equal(reads,2);assert.equal(publications,1);assert(op.publicationPending);await op.dispose();assert.equal(op.publicationPending,false);await state.pendingOperation.dispose();assert.equal(original.data.record(0).featureId,U64);
 });}finally{if(index)await index.dispose();if(scope)await scope.dispose();}
});

test('dispose waits complete in-flight19 read then drops private views before Data10',async()=>{
 const {GeoSpatialIndex}=await import('../src/geo-spatial.js'),raw=nativeGeoScaleBridge(budget.processorBytes);let scope,index,handle,entered,release;const gate=new Promise(r=>release=r),started=new Promise(r=>entered=r);let drop=false,deleted=false;
 const bridge={async execute(r){const v=new DataView(r),reply=await raw.execute(r);if(v.getUint32(8,true)===19)handle=new DataView(reply).getBigUint64(16,true);if(v.getUint32(8,true)===10&&v.getBigUint64(16,true)===handle)deleted=true;return reply;},async read(r){const reply=await raw.read(r);if(new DataView(r).getUint32(8,true)===23&&new DataView(r).getBigUint64(16,true)===handle){entered();await gate;drop=true;}return reply;}};
 try{await fixture(bridge,async(original,f)=>{const pages=new Map();index=await GeoSpatialIndex._fromFrame(original,{bridge,budget,readChunk:f.readChunk},{grid:16,maxVertices:1000000n,readPage:async t=>pages.get(t.page),writePage:async(t,b)=>pages.set(t.page,b.slice())});scope=await createGeoSelectedScope(bridge,{frameHandle:original.handle,sequence:1n,namespace:U64,layerId:U64,budget});const state=await scope.state({revision:U64,ids:BigUint64Array.of(U64),fill:Uint8Array.of(0,255,0,255),budget}),op=(await state.begin({command:36,handle:index.handle,sequence:2n,query:f.query,budget})).operation;await op.drive({readPage:async t=>pages.get(t.page)});const preparing=op.prepare(f.style),failed=assert.rejects(preparing,/closing/);await started;const closing=op.dispose();await new Promise(r=>setTimeout(r,10));assert(!deleted&&!drop);release();await Promise.all([failed,closing]);assert(deleted&&drop);await state.pendingOperation.dispose();assert.equal(original.data.record(0).featureId,U64);
 });}finally{release();if(index)await index.dispose();if(scope)await scope.dispose();}
});

test('genuine19 nonadmission preserves completeQuery and private capability cannot be cloned',async()=>{
 const {GeoSpatialIndex}=await import('../src/geo-spatial.js'),bridge=nativeGeoScaleBridge(budget.processorBytes);let scope,index,operation;
 try{await fixture(bridge,async(original,f)=>{const pages=new Map();index=await GeoSpatialIndex._fromFrame(original,{bridge,budget,readChunk:f.readChunk},{grid:16,maxVertices:1000000n,readPage:async t=>pages.get(t.page),writePage:async(t,b)=>pages.set(t.page,b.slice())});scope=await createGeoSelectedScope(bridge,{frameHandle:original.handle,sequence:1n,namespace:U64,layerId:U64,budget});const state=await scope.state({revision:U64,ids:BigUint64Array.of(U64),fill:Uint8Array.of(0,255,0,255),budget}),op=operation=(await state.begin({command:36,handle:index.handle,sequence:2n,query:f.query,budget})).operation;
  await op.drive({readPage:async t=>pages.get(t.page)});
  const {captureGeoSceneDataIssuer,createGeoSceneDataPublication}=await import('../src/geoscale.js'),context=captureGeoSceneDataIssuer(bridge);assert.throws(()=>createGeoSceneDataPublication({...context},{handle:op.handle,sequence:op.sequence,budget,style:f.style}),/Captured issuing/);
  const invalid=f.style.slice();new DataView(invalid.buffer).setFloat64(8,NaN,true);await assert.rejects(op.prepare(invalid),e=>e.nativeCode===-10);assert.equal(op.publicationPending,false);const frame=await op.prepare(f.style);assert.equal(frame.data.selection.visibleVertices,1n);await frame.dispose();await state.pendingOperation.dispose();assert.equal(original.data.record(0).featureId,U64);
 });}finally{if(operation)await operation.dispose();if(index)await index.dispose();if(scope)await scope.dispose();}
});
