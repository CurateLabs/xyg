import assert from 'node:assert/strict';
import test from 'node:test';
import {driveGeoSession,encodeGeoScaleRequest,parseGeoSceneData,encodeGeoChunkRequest,prepareGeoSceneData} from '../src/geoscale.js';
import {fixture,budget} from './geoscale-fixture.mjs';

function reply(code=1){const b=new ArrayBuffer(256),v=new DataView(b);new Uint8Array(b).set([88,89,71,90]);v.setUint32(4,1,true);v.setUint32(8,code,true);v.setBigUint64(16,1n,true);if(code===1){v.setBigUint64(64,9n,true);v.setBigUint64(72,1n,true);v.setBigUint64(120,4n,true);}return b;}
test('real ABI382 full IDs/time, Data read quota, explicit lifecycle',async()=>{const data=await fixture();assert.equal(parseGeoSceneData(Uint8Array.from(Buffer.from(data.packet,'hex')).buffer).identity.sourceCrs,4326);});
for(const mode of ['abort','giant','failure','success'])test(`read lease ${mode}: settle before acknowledgment`,async()=>{
 const abort=new AbortController(),calls=[];let resolveRead,enteredResolve,settled=false;const entered=new Promise(resolve=>enteredResolve=resolve),pending=new Promise(resolve=>resolveRead=resolve);
 const bridge={async execute(request){const command=new DataView(request).getUint32(8,true);calls.push(command);if(command===8)assert.equal(settled,true);return reply(calls.filter(c=>c===6).length===1?1:3);},async read(){throw new Error('unused');}};
 const readChunk=async()=>{enteredResolve();await pending;settled=true;if(mode==='failure')throw new Error('read failed');return mode==='giant'?new Uint8Array(new ArrayBuffer(8),0,4):new Uint8Array([1,2,3,4]);};
 const driven=driveGeoSession(bridge,{handle:1n,sequence:0n,budget,readChunk,signal:abort.signal});const observed=driven.then(value=>({value}),error=>({error}));await entered;
 if(mode==='abort'){abort.abort();await Promise.resolve();assert.ok(calls.includes(9));assert.ok(!calls.includes(8));}resolveRead();const result=await observed;
 if(mode==='abort')assert.equal(result.error.name,'AbortError');else if(mode==='giant')assert.match(result.error.message,/exact bounded/);else if(mode==='failure')assert.match(result.error.message,/read failed/);else assert.equal(result.value.code,3);
 assert.equal(calls.filter(c=>c===8).length,1);assert.equal(calls.includes(7),mode==='success');
});
test('malformed provenance and exact scalar widths rejected',async()=>{
 const {packet}=await fixture(),b=Uint8Array.from(Buffer.from(packet,'hex')),v=new DataView(b.buffer);b[256+Number(v.getBigUint64(32,true))+28]=1;assert.throws(()=>parseGeoSceneData(b.buffer),/reserved/);
 assert.throws(()=>encodeGeoScaleRequest({command:6,handle:9007199254740993,sequence:1n}),/u64 bigint/);
 assert.throws(()=>encodeGeoChunkRequest({descriptor:new Uint8Array(),rows:1,values:new Float32Array([1])},1<<20),/exact typed/);
 assert.throws(()=>encodeGeoChunkRequest({descriptor:new Uint8Array(1024),rows:0},1024),/peak/);
});
test('parsed identity failure drops packet storage before Data disposal',{skip:typeof global.gc!=='function'},async()=>{
 const {packet:hex}=await fixture();let storage,disposals=0;
 const bridge={async execute(request){const command=new DataView(request).getUint32(8,true);if(command===10){disposals++;await new Promise(resolve=>setImmediate(resolve));global.gc();assert.equal(storage.deref(),undefined);return reply(0);}const b=reply(0),v=new DataView(b);v.setBigUint64(16,99n,true);v.setBigUint64(24,1n,true);v.setBigUint64(32,BigInt(hex.length/2),true);v.setBigUint64(40,1n,true);return b;},async read(){const packet=Uint8Array.from(Buffer.from(hex,'hex')).buffer;storage=new WeakRef(packet);return packet;}};
 await assert.rejects(prepareGeoSceneData(bridge,{handle:1n,sequence:1n,budget,style:new Uint8Array(48)}),/identity/);assert.equal(disposals,1);
});
