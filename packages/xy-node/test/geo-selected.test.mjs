import test from 'node:test';
import assert from 'node:assert/strict';
import {fixture,budget,U64} from './geoscale-fixture.mjs';
import {createGeoSelectedScope} from '../src/geo-selected.js';
import {encodeGeoScaleRequest as encode,parseGeoSceneData,prepareGeoSceneData,nativeGeoScaleBridge} from '../src/geoscale.js';

const sharedNative=nativeGeoScaleBridge(budget.processorBytes);

test('actual native selected scope consumes only success and binds exact u64 intent',async()=>{
 let scope;
 try{await fixture(sharedNative,async(original,f)=>{
  scope=await createGeoSelectedScope(f.bridge,{frameHandle:original.handle,sequence:1n,namespace:U64,layerId:U64,budget});
  const state=await scope.state({revision:U64,ids:new BigUint64Array([U64,U64]),fill:new Uint8Array([0,255,0,255]),budget});
  await assert.rejects(state.begin({command:35,handle:original.data.identity.sessionHandle,sequence:1n,query:f.query,budget}));
  const accepted=await state.begin({command:35,handle:original.data.identity.sessionHandle,sequence:2n,query:f.query,budget});assert.equal(accepted.fallback,false);
  await accepted.operation.drive({readChunk:f.readChunk});const frame=await accepted.operation.prepare(f.style);
  try{assert.equal(frame.data.selection.idCount,1);assert.equal(frame.data.selection.id(0),U64);assert.equal(frame.data.selection.namespace,U64);assert.equal(frame.data.selection.visibleVertices,1n);assert.equal(frame.data.selection.raw.buffer,frame.data.packet);
   await assert.rejects(scope.dispose());
   const bad=frame.data.packet.slice(0);new Uint8Array(bad)[bad.byteLength-72]^=1;assert.throws(()=>parseGeoSceneData(bad),/binding/);
  }finally{await frame.dispose();}
 });}finally{if(scope)await scope.dispose();}
});

test('ordinary native Scene owner retries failed cleanup without resurrecting views',async()=>{
 let attempt=0,active=false;
 const raw=sharedNative,bridge={read:r=>raw.read(r),async execute(r){if(active&&new DataView(r).getUint32(8,true)===10&&++attempt===1)throw new Error('transient release failure');return raw.execute(r);}};
 await fixture(bridge,async(original,f)=>{
  const duplicate=await prepareGeoSceneData(bridge,{command:26,handle:original.handle,sequence:1n,budget});active=true;
  await assert.rejects(duplicate.dispose(),/transient/);assert.throws(()=>duplicate.data,/disposed/);
  await duplicate.dispose();assert.equal(attempt,2);active=false;
  await assert.rejects(raw.read(encode({command:23,handle:duplicate.handle})));
 });
});


test('selected native Scene cleanup retries the same independent owner',async()=>{
 let scope,attempt=0,target;
 const raw=sharedNative,bridge={read:r=>raw.read(r),async execute(r){const v=new DataView(r);if(v.getUint32(8,true)===10&&v.getBigUint64(16,true)===target&&++attempt===1)throw new Error('transient selected release');return raw.execute(r);}};
 try{await fixture(bridge,async(original,f)=>{
  scope=await createGeoSelectedScope(bridge,{frameHandle:original.handle,sequence:1n,namespace:U64,layerId:U64,budget});
  const state=await scope.state({revision:U64,ids:new BigUint64Array([U64]),fill:new Uint8Array([0,255,0,255]),budget});
  const accepted=await state.begin({command:35,handle:original.data.identity.sessionHandle,sequence:2n,query:f.query,budget});
  await accepted.operation.drive({readChunk:f.readChunk});const frame=await accepted.operation.prepare(f.style);target=frame.handle;
  await assert.rejects(frame.dispose(),/transient selected/);assert.throws(()=>frame.data,/disposed/);
  assert.equal(original.data.record(0).featureId,U64);await frame.dispose();await frame.dispose();assert.equal(attempt,2);
  await assert.rejects(raw.read(encode({command:23,handle:target})));target=undefined;
 });}finally{if(scope)await scope.dispose();}
});
