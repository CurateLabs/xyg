import test from 'node:test';
import assert from 'node:assert/strict';
import {hierarchyFixture,releaseHierarchy,request,prepare,acknowledge} from './geo-live-hierarchy-fixture.mjs';
test('actual selected hierarchy live43/44 survives original source disposal',async()=>{
 const f=await hierarchyFixture(),a=f.adapter,bridge=f.source.bridge,execute=f.control.execute,calls=[];
 f.control.execute=raw=>{const op=new DataView(raw).getUint32(8,true);calls.push(op);assert.ok(![5,18,35,36,38,39].includes(op),'implicit query fallback');return execute(raw);};
 try{assert.equal((await request(a,1))[0].error,undefined);for(const seq of [4n,5n]){
  const old=a.frame,oldSeq=a.sequence,[reply,out]=await prepare(a,{nonce:seq,sequence:seq});assert.equal(reply.error,undefined);assert.equal(a.frame,old);
  assert.equal((await acknowledge(a,7,old.handle,oldSeq,out[0]))[0].error,undefined);assert.equal(a.frame.data.selection.id(0),0xffffffffffffffffn);
  assert.equal((await acknowledge(a,8,old.handle,oldSeq,out[0]))[0].error,undefined);const rows=await a.frame.rows();assert.equal(rows.data.record(0).featureId,0xffffffffffffffffn);await rows.dispose();
 }assert.equal(calls.filter(x=>x===43).length,2);assert.equal(calls.filter(x=>x===44).length,2);}
 finally{f.control.execute=execute;await releaseHierarchy(f);}
});
test('exclusive lane and closed lane fail before losing accepted paint',async()=>{
 const f=await hierarchyFixture(),a=f.adapter;
 try{assert.throws(()=>f.chart.host({frame:a.anchor,selectedScope:f.scope,hierarchyLane:f.lane}),/another live adapter/);await request(a,1);const accepted=a.frame;await f.lane.dispose();const [reply,out]=await prepare(a,{sequence:4n});assert.equal(reply.prepareAbsent,true);assert.equal(out.length,0);assert.equal(a.frame,accepted);assert.equal(accepted.data.selection.id(0),0xffffffffffffffffn);}
 finally{await releaseHierarchy(f);}
});
test('five independent hierarchy lanes keep15→16 replacement within fixed caps',async()=>{
 const {hierarchyFiveFixtures,releaseFive}=await import('./geo-live-hierarchy-fixture.mjs');
 const {encodeGeoScaleRequest,decodeGeoScaleReply}=await import('../src/geoscale.js');
 const fs=await hierarchyFiveFixtures(),bridge=fs[0].source.bridge,pressure=[];
 const execute=async fields=>decodeGeoScaleReply(await bridge.execute(encodeGeoScaleRequest(fields)));
 try{
  for(const f of fs)assert.equal((await request(f.adapter,1))[0].error,undefined);
  // Scope1 + five Lane + five Data =11. Five additional issued small
  // Scopes fill16 without adding canonical builder scratch reservations.
  for(let i=0;i<5;i++){const payload=new Uint8Array(16),v=new DataView(payload.buffer);v.setBigUint64(0,900n+BigInt(i),true);v.setBigUint64(8,fs[0].query.layerId,true);pressure.push((await execute({command:32,handle:fs[0].adapter.frame.handle,sequence:3n,budget:fs[0].source.budget,payload})).handle);}
  const [blocked]=await prepare(fs[0].adapter,{sequence:4n});assert.equal(blocked.prepareAbsent,true);
  for(const f of fs)assert.equal(f.adapter.frame.data.selection.id(0),0xffffffffffffffffn);
  await execute({command:10,handle:pressure.pop()});
  const first=fs[0].adapter,old=first.frame,[reply,out]=await prepare(first,{sequence:5n});assert.equal(reply.error,undefined);
  assert.ok((await prepare(fs[1].adapter,{sequence:4n}))[0].error,'one process staging slot');
  assert.equal((await acknowledge(first,7,old.handle,3n,out[0]))[0].error,undefined);
  assert.equal((await acknowledge(first,8,old.handle,3n,out[0]))[0].error,undefined);
  for(const handle of pressure.splice(0))await execute({command:10,handle});
  const other=fs[1].adapter,prior=other.frame,[second,b]=await prepare(other,{sequence:4n});assert.equal(second.error,undefined);
  assert.equal((await acknowledge(other,7,prior.handle,3n,b[0]))[0].error,undefined);assert.equal((await acknowledge(other,8,prior.handle,3n,b[0]))[0].error,undefined);
 }finally{for(const handle of pressure)await execute({command:10,handle});await releaseFive(fs);}
});
for(const mutation of [33,43,44])test(`lost actual${mutation} preserves paint and settles typed replacement before retry`,async()=>{
 const f=await hierarchyFixture(),a=f.adapter,bridge=f.source.bridge,execute=f.control.execute;let lose=true;
 f.control.execute=async raw=>{const op=new DataView(raw).getUint32(8,true),reply=await execute(raw);if(op===mutation&&lose){lose=false;throw Error(`lost${mutation}confirmation`);}return reply;};
 try{await request(a,1);const old=a.frame,[error]=await prepare(a,{sequence:4n});assert.equal(lose,false,'the real mutation reply must reach the injector');assert.match(error.error,/lost|uncertain|ownership/i);assert.equal(error.prepareAbsent,true);assert.equal(a.frame,old);assert.equal(f.lane.pendingOperation,undefined);assert.equal(a.liveCandidate.cleanupOperation,undefined);
  f.control.execute=execute;const [ok,out]=await prepare(a,{sequence:5n});assert.equal(ok.error,undefined);assert.equal((await acknowledge(a,9,old.handle,3n,out[0]))[0].error,undefined);
 }finally{f.control.execute=execute;await releaseHierarchy(f);}
});
for(const mutation of[33,43])test(`uncertain${mutation} cleanup failure holds global slot until exact retry confirmation`,async()=>{
 const f=await hierarchyFixture(),a=f.adapter,bridge=f.source.bridge,execute=f.control.execute;let lose=true,failures=3;
 f.control.execute=async raw=>{const op=new DataView(raw).getUint32(8,true);if(op===10&&failures-->0)throw Error('injected operation cleanup rejection');const reply=await execute(raw);if(op===mutation&&lose){lose=false;throw Error(`lost${mutation}confirmation`);}return reply;};
 try{await request(a,1);const old=a.frame,[error]=await prepare(a,{sequence:4n});assert.equal(lose,false,'the real mutation reply must reach the injector');assert.equal(error.prepareAbsent,undefined);assert.ok(a.liveCandidate.cleanupOperation||a.liveCandidate.cleanupAllocation);assert.equal(a.frame,old);assert.ok((await request(a,4,{owner:old.handle,sequence:3n}))[0].error);
  f.control.execute=execute;const [resolved]=await prepare(a,{sequence:4n});assert.equal(resolved.prepareAbsent,true);assert.equal(a.liveCandidate.cleanupOperation,undefined);assert.equal(f.lane.pendingOperation,undefined);assert.equal((await prepare(a,{sequence:5n}))[0].error,undefined);
 }finally{f.control.execute=execute;await releaseHierarchy(f);}
});
test('cancel after real44 publication cleans candidate before accepted paint changes',async()=>{
 const f=await hierarchyFixture(),a=f.adapter,bridge=f.source.bridge,execute=f.control.execute;
 let arrived,release;const published=new Promise(r=>arrived=r),gate=new Promise(r=>release=r);
 f.control.execute=async raw=>{const reply=await execute(raw);if(new DataView(raw).getUint32(8,true)===44){arrived();await gate;}return reply;};
 try{await request(a,1);const old=a.frame,pending=prepare(a,{sequence:4n});await published;const cancelling=f.lane.cancel();release();const [reply,out]=await pending;await cancelling;
  assert.equal(reply.prepareAbsent,true);assert.equal(out.length,0);assert.equal(a.frame,old);assert.equal(f.lane.pendingOperation,undefined);assert.equal(a.liveCandidate.cleanupOperation,undefined);assert.equal(a.liveCandidate.cleanupFrame,undefined);
  f.control.execute=execute;assert.equal((await prepare(a,{sequence:5n}))[0].error,undefined);
 }finally{release();f.control.execute=execute;await releaseHierarchy(f);}
});
test('close during actual26 retains failed disposal owner and retries before releasing lane',async()=>{
 const f=await hierarchyFixture(),bridge=f.source.bridge,execute=f.control.execute,read=f.control.read;
 const caller=await f.adapter.anchor.retain();await f.adapter.realmDestroyed();await f.adapter.cleanup;
 let arrived,release,fail=true;const copied=new Promise(r=>arrived=r),gate=new Promise(r=>release=r);
 f.control.read=async raw=>{const reply=await read(raw);if(new DataView(raw).getUint32(8,true)===23){arrived();await gate;}return reply;};
 const retain=caller.retain.bind(caller);let owned,disposals=0;
 // Retention captures the native transport before yielding its read. Inject
 // cleanup refusal at the genuinely issued owner's disposal boundary instead
 // of replacing a bridge callable that this owner no longer consults.
 caller.retain=async()=>{owned=await retain();const dispose=owned.dispose.bind(owned);owned.dispose=async()=>{disposals++;if(fail){fail=false;throw Error('injected anchor disposal rejection');}await dispose();};return owned;};
 let adapter,replacement;
 try{
  adapter=f.chart.host({frame:caller,selectedScope:f.scope,hierarchyLane:f.lane});await copied;adapter.close();release();await adapter.anchorReady;
  await assert.rejects(adapter.cleanup,/anchor disposal rejection/);assert.equal(disposals,1);assert.equal(adapter.anchor,owned,'failed disposal owner remains privately reachable');assert.notEqual(owned.handle,caller.handle);assert.throws(()=>f.chart.host({frame:caller,selectedScope:f.scope,hierarchyLane:f.lane}),/another live adapter/);
  await adapter.realmDestroyed();await adapter.cleanup;assert.ok(disposals>=2,'the retained owner must be retried');assert.throws(()=>owned.data,/disposed/);assert.equal(adapter.anchor,undefined);caller.retain=retain;
  replacement=f.chart.host({frame:caller,selectedScope:f.scope,hierarchyLane:f.lane});await replacement.anchorReady;assert.equal((await request(replacement,1))[0].error,undefined);assert.equal(replacement.frame.data.selection.id(0),0xffffffffffffffffn);
 }finally{release();fail=false;caller.retain=retain;f.control.execute=execute;f.control.read=read;if(replacement)await replacement.realmDestroyed();if(adapter)await adapter.realmDestroyed();await caller.dispose();await releaseHierarchy(f);}
});

for(const route of['canonical','indexed','hierarchy'])for(const mode of['lost','corrupt'])test(`${route} ${mode}33 reply resolves one allocation and keeps accepted paint`,async()=>{
 const {selectedLiveFixture,releaseSelectedLive}=await import('./geo-live-hierarchy-fixture.mjs');
 const f=route==='hierarchy'?await hierarchyFixture():await selectedLiveFixture(route==='indexed'),a=f.adapter,b=f.source.bridge,execute=f.control.execute;
 const {decodeGeoScaleReply}=await import('../src/geoscale.js');let fail=true;const receipts=[];
 f.control.execute=async raw=>{const reply=await execute(raw);if(new DataView(raw).getUint32(8,true)===33){receipts.push({handle:decodeGeoScaleReply(reply).handle,nonce:new DataView(raw).getBigUint64(24,true)});if(fail){fail=false;if(mode==='lost')throw Error('lost allocation confirmation');const corrupt=reply.slice(0);new Uint8Array(corrupt)[0]^=1;return corrupt;}}return reply;};
 try{await request(a,1);const old=a.frame,sequence=a.sequence+1n,[error,out]=await prepare(a,{sequence});assert.ok(error.error);assert.equal(error.prepareAbsent,true);assert.equal(out.length,0);assert.equal(a.frame,old);assert.equal(a.liveCandidate.cleanupAllocation,undefined);assert.equal(receipts.length,2);assert.deepEqual(receipts[0],receipts[1]);assert.ok(receipts[0].nonce>0n);
  f.control.execute=execute;const [ok,next]=await prepare(a,{sequence:sequence+1n});assert.equal(ok.error,undefined);assert.equal((await acknowledge(a,9,old.handle,a.sequence,next[0]))[0].error,undefined);assert.equal(old.data.selection.id(0),0xffffffffffffffffn);
 }finally{f.control.execute=execute;await(route==='hierarchy'?releaseHierarchy(f):releaseSelectedLive(f));}
});

for(const route of['canonical','indexed'])test(`${route} uncertain33 cleanup keeps owner and slot until exact retry`,async()=>{
 const {selectedLiveFixture,releaseSelectedLive}=await import('./geo-live-hierarchy-fixture.mjs');
 const f=await selectedLiveFixture(route==='indexed'),a=f.adapter,b=f.source.bridge,execute=f.control.execute;let lose=true,failures=3;
 f.control.execute=async raw=>{const op=new DataView(raw).getUint32(8,true);if(op===10&&failures-->0)throw Error('injected allocation cleanup rejection');const reply=await execute(raw);if(op===33&&lose){lose=false;throw Error('lost allocation reply');}return reply;};
 try{await request(a,1);const old=a.frame,seq=a.sequence+1n,[failed,out]=await prepare(a,{sequence:seq});assert.ok(failed.error);assert.equal(failed.prepareAbsent,undefined);assert.equal(out.length,0);assert.equal(a.frame,old);assert.ok(a.liveCandidate.cleanupAllocation);assert.ok((await request(a,4,{owner:old.handle,sequence:a.sequence}))[0].error);
  f.control.execute=execute;const [settled]=await prepare(a,{sequence:seq});assert.equal(settled.prepareAbsent,true);assert.equal(a.liveCandidate.cleanupAllocation,undefined);const [ok,next]=await prepare(a,{sequence:seq+1n});assert.equal(ok.error,undefined);assert.equal((await acknowledge(a,9,old.handle,a.sequence,next[0]))[0].error,undefined);
 }finally{f.control.execute=execute;await releaseSelectedLive(f);}
});
