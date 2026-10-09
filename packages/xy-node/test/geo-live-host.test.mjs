import test from 'node:test';
import assert from 'node:assert/strict';
import {liveFixture,request,prepare,acknowledge,release} from './geo-live-host-fixture.mjs';
test('actual native staged camera/time keeps accepted paint until CAS and exact retired ACK',async()=>{
 const f=await liveFixture(),a=f.adapter;await request(a,1);const old=a.frame;
 try{const [message,buffers]=await prepare(a);assert.equal(message.error,undefined);assert.equal(a.frame,old);assert.equal(f.source.current,old);const tag=buffers[0];
  assert.equal((await acknowledge(a,7,old.handle,1n,tag))[0].error,undefined);const current=a.frame;assert.notEqual(current,old);assert.equal(current.data.identity.time.kind,0);assert.equal(old.data.record(0).featureId,0xffffffffffffffffn);
  assert.ok((await acknowledge(a,8,old.handle+1n,1n,tag))[0].error);assert.equal((await acknowledge(a,8,old.handle,1n,tag))[0].error,undefined);assert.throws(()=>old.data,/disposed/);assert.equal((await acknowledge(a,8,old.handle,1n,tag))[0].error,undefined);assert.equal(a.frame,current);
 }finally{await release(f);}
});
test('one process stage slot preserves five mounted frames and recovers after abort ACK',async()=>{
 const fs=[];try{for(let i=0;i<5;i++){const f=await liveFixture();fs.push(f);assert.equal((await request(f.adapter,1))[0].error,undefined);}
  const [,buffers]=await prepare(fs[0].adapter);assert.ok(buffers.length===3);assert.ok((await prepare(fs[1].adapter))[0].error);for(const f of fs)assert.equal(f.adapter.frame.data.record(0).featureId,0xffffffffffffffffn);
  assert.equal((await acknowledge(fs[0].adapter,9,fs[0].adapter.frame.handle,1n,buffers[0]))[0].error,undefined);assert.equal((await prepare(fs[1].adapter))[0].error,undefined);
 }finally{for(const f of fs)await release(f);}
});
test('lost stage and commit confirmations recover same candidate while closing',async()=>{
 const f=await liveFixture(),a=f.adapter;await request(a,1);const old=a.frame;
 try{
  const [,buffers]=await prepare(a);const tag=buffers[0],candidate=a.liveCandidate.frame;
  const [,retry]=await prepare(a);assert.equal(a.liveCandidate.frame,candidate);assert.deepEqual(new Uint8Array(retry[0]),new Uint8Array(tag));
  assert.equal((await acknowledge(a,7,old.handle,1n,tag))[0].error,undefined);a.close();
  assert.equal((await acknowledge(a,7,old.handle,1n,tag))[0].error,undefined);
  assert.equal((await acknowledge(a,8,old.handle,1n,tag))[0].error,undefined);
 }finally{await release(f);}
});
test('cancellation after actual Data creation drops candidate and preserves accepted paint',async()=>{
 const f=await liveFixture(),a=f.adapter;await request(a,1);const old=a.frame,bridge=f.source.bridge,execute=bridge.execute.bind(bridge);let unblock,entered;
 const gate=new Promise(r=>entered=r);bridge.execute=async raw=>{const result=await execute(raw);if(new DataView(raw).getUint32(8,true)===11){entered();await new Promise(r=>unblock=r);}return result;};
 try{const pending=prepare(a);await gate;f.source.cancel();unblock();const [reply]=await pending;assert.match(reply.error,/cancel/i);assert.equal(a.liveCandidate.frame,undefined);assert.equal(a.frame,old);assert.equal(old.data.record(0).featureId,0xffffffffffffffffn);
  bridge.execute=execute;assert.equal((await prepare(a,{sequence:3n}))[0].error,undefined);
 }finally{unblock?.();bridge.execute=execute;await release(f);}
});
test('accepted private anchor remounts and old realm ACK cannot change new realm',async()=>{
 const f=await liveFixture(),a=f.adapter;await request(a,1);const old=a.frame;
 try{const [,out]=await prepare(a);const tag=out[0];await acknowledge(a,7,old.handle,1n,tag);await acknowledge(a,8,old.handle,1n,tag);const accepted=a.frame;
  assert.equal((await request(a,4,{owner:accepted.handle,sequence:2n}))[0].error,undefined);
  assert.equal((await request(a,1,{mount:'newrealm'}))[0].error,undefined);assert.equal(a.frame,accepted);
  assert.match((await acknowledge(a,8,old.handle,1n,tag))[0].error,/mount/);
  const payload=new ArrayBuffer(224),v=new DataView(payload);[1n,3n,3n,3n,1n].forEach((n,i)=>v.setBigUint64(i*8,n,true));const {encodeGeoViewportRequest}=await import('../src/geoviewport.js');new Uint8Array(payload).set(new Uint8Array(encodeGeoViewportRequest(a.frame.data.identity.camera,3,[1,0])),64);
  assert.equal((await request(a,6,{version:2,owner:a.frame.handle,sequence:2n,mount:'newrealm',payload}))[0].error,undefined);
 }finally{await a.realmDestroyed();a.close();await a.cleanup;await f.source.dispose();}
});
for(const selected of [false,true])test(`actual indexed live updates preserve ${selected?'selected':'ordinary'} authority`,async()=>{
 const f=await liveFixture(),source=f.source,q=f.adapter.query,style=f.adapter.style;f.adapter.close();await f.adapter.cleanup;
 const {geoChart,geoLayer}=await import('../src/charts.js'),{createGeoSelectedScope}=await import('../src/geo-selected.js'),{attachRetainedFrame}=await import('../src/geo-retained.js'),{encodeGeoScaleRequest}=await import('../src/geoscale.js');
 let canonical,index,frame,adapter,scope;
 try{canonical=await source.update(q,{sequence:1n,style});const pages=new Map();index=await canonical.spatialIndex({grid:16,maxVertices:1000000n,readPage:async t=>pages.get(t.page),writePage:async(t,b)=>pages.set(t.page,b.slice())});
  if(selected){scope=await createGeoSelectedScope(source.bridge,{frameHandle:canonical.handle,sequence:1n,namespace:0xffffffffffffffffn,layerId:q.layerId,budget:source.budget});const state=await scope.state({revision:1n,ids:new BigUint64Array([0xffffffffffffffffn]),fill:new Uint8Array([0,255,0,255]),budget:source.budget});const accepted=await state.begin({command:36,handle:index.handle,sequence:2n,query:q,budget:source.budget});await accepted.operation.drive({readChunk:index.readChunk,readPage:index.readPage});frame=await accepted.operation.prepare(style);attachRetainedFrame(index,frame,2n,encodeGeoScaleRequest({command:36,handle:index.handle,sequence:2n,query:q,budget:source.budget,payload:new Uint8Array(8)}),style);await accepted.operation.dispose();await state.dispose();}
  else frame=await index.update(q,{sequence:2n,style});
  const chart=geoChart(geoLayer('points',{source:index,layerId:q.layerId,query:q,sequence:2n,style}),{camera:q.camera});if(selected){const original=frame._queryPacket;const badLength=original.slice(0);new DataView(badLength).setBigUint64(232,0n,true);const badCamera=original.slice(0);new Uint8Array(badCamera)[80]^=1;for(const invalid of [original.slice(0,256),badLength,badCamera]){frame._queryPacket=invalid;assert.throws(()=>chart.host({frame,selectedScope:scope}));}frame._queryPacket=original;}else{const original=frame._queryPacket;frame._queryPacket=new Uint8Array(264).buffer;new Uint8Array(frame._queryPacket).set(new Uint8Array(original));assert.throws(()=>chart.host({frame}));frame._queryPacket=original;}adapter=chart.host({frame,selectedScope:scope});await adapter.anchorReady;await frame.dispose();await request(adapter,1);
  for(const sequence of [3n,4n]){const old=adapter.frame,[message,out]=await prepare(adapter,{nonce:sequence,sequence});assert.equal(message.error,undefined);assert.equal((await acknowledge(adapter,7,old.handle,sequence-1n,out[0]))[0].error,undefined);assert.equal((await acknowledge(adapter,8,old.handle,sequence-1n,out[0]))[0].error,undefined);assert.equal(adapter.frame.data.record(0).featureId,0xffffffffffffffffn);if(selected)assert.equal(adapter.frame.data.selection.id(0),0xffffffffffffffffn);}
 }finally{if(adapter){await adapter.realmDestroyed();adapter.close();await adapter.cleanup;}await frame?.dispose();await index?.dispose();await canonical?.dispose();await source.dispose();await scope?.dispose();}
});
test('failed unpublished Data cleanup retains global stage credit until exact retry',async()=>{
 const f=await liveFixture(),a=f.adapter;await request(a,1);const old=a.frame,bridge=f.source.bridge,execute=bridge.execute.bind(bridge);let unblock,entered,failures=2;
 const gate=new Promise(r=>entered=r);bridge.execute=async raw=>{const op=new DataView(raw).getUint32(8,true);if(op===10&&failures-->0)throw Error('injected cleanup rejection');const result=await execute(raw);if(op===11){entered();await new Promise(r=>unblock=r);}return result;};
 try{const pending=prepare(a);await gate;f.source.cancel();unblock();const [reply]=await pending;assert.equal(reply.prepareAbsent,undefined);assert.ok(a.liveCandidate.cleanupFrame);assert.equal(a.frame,old);assert.ok((await request(a,4,{owner:old.handle,sequence:1n}))[0].error);bridge.execute=execute;
  const [settled]=await prepare(a);assert.equal(settled.prepareAbsent,true);assert.equal(a.liveCandidate.cleanupFrame,undefined);assert.equal(a.frame,old);assert.equal((await prepare(a,{sequence:3n}))[0].error,undefined);
 }finally{unblock?.();bridge.execute=execute;await release(f);}
});
