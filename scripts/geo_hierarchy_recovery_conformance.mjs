#!/usr/bin/env node
// Test-only journal instrumentation over the canonical raw hierarchy fixtures.
// No product policy: Rust still owns selection, hierarchy traversal, LOD and Scene.
import assert from 'node:assert/strict';
import {readFile,writeFile} from 'node:fs/promises';
import {pathToFileURL} from 'node:url';
const original=new URL('./geo_selected_hierarchy_conformance.mjs',import.meta.url);
let text=await readFile(original,'utf8');
const packets=[],controls=[];
globalThis.__hierarchyRecoveryPackets=packets;
globalThis.__hierarchyRecoveryControls=controls;
globalThis.__hierarchyRecoveryLegacy=process.env.XYG_HIERARCHY_RECOVERY_LEGACY_ONLY==='1';
const instrumentation=`
function recoveryBridge(base,native=false){
 const births=[],alive=new Map(),latest=new Map(),nonces=new Map(),issued=new Map();
 function ack(b,target,action){const v=new DataView(b),p=new Uint8Array(16),pv=new DataView(p.buffer);pv.setUint32(0,v.getUint32(8,true),true);pv.setUint32(4,action,true);pv.setBigUint64(8,target,true);const q=request(47,v.getBigUint64(16,true),v.getBigUint64(24,true),p);new DataView(q).setBigUint64(240,v.getBigUint64(240,true),true);return q;}
 function targetLive(b){const a=alive.get(b.target);return a?.kind===b.command&&a.sequence===b.sequence&&(b.command!==43||latest.get(b.issuer)===b.sequence);}
 function issuerLive(b){return b.command===43?alive.has(b.issuer):alive.get(b.issuer)?.kind===43;}
 async function settle(){for(const b of births){if(!b.released&&!targetLive(b)){const retired=reply(await base.execute(ack(b.raw,b.target,0)));assert.equal(retired.code,22);assert.equal(retired.handle,0n);assert.equal(reply(await base.execute(ack(b.raw,b.target,2))).code,0);b.released=true;}if(b.released&&!b.forgotten&&!issuerLive(b)){assert.equal(reply(await base.execute(ack(b.raw,b.target,1))).code,0);b.forgotten=true;}}}
 return {async execute(input){let b=input;const iv=new DataView(input),cmd=iv.getUint32(8,true),h=iv.getBigUint64(16,true),seq=iv.getBigUint64(24,true);const opt=!globalThis.__hierarchyRecoveryLegacy&&[43,44].includes(cmd);
  if(opt){b=input.slice(0);const key=String(h)+':'+cmd,n=(nonces.get(key)??0n)+1n;nonces.set(key,n);new DataView(b).setBigUint64(240,n,true);}
  const out=await base.execute(b),r=reply(out);
  if(r.code===0&&[1,4,11,13,14,16,17,19,26,32,33,34,37,42,43,44].includes(cmd))alive.set(r.handle,{kind:cmd===43?43:cmd===44?44:0,sequence:new DataView(out).getBigUint64(24,true)});
  if(r.code===0&&[11,13,14,16,19,26,44].includes(cmd))issued.set(r.handle,{issuer:h,sequence:new DataView(out).getBigUint64(24,true)});
  if(cmd===43&&r.code===0)latest.set(h,seq);
  if(cmd===9||(cmd===6&&[9,10].includes(r.code))){const a=alive.get(h);if(a?.kind===43)a.kind=-1;}
  if(cmd===10&&r.code===0)alive.delete(h);
  if(opt&&r.code===0){assert.deepEqual(await base.execute(b),out);const changed=b.slice(0);new Uint8Array(changed)[cmd===44?256:40]^=1;await assert.rejects(base.execute(changed));const confirmed=await base.execute(ack(b,r.handle,0));assert.equal(reply(confirmed).code,0);assert.equal(reply(confirmed).handle,r.handle);assert.deepEqual(await base.execute(ack(b,r.handle,0)),confirmed);births.push({raw:b,target:r.handle,issuer:h,sequence:seq,command:cmd,released:false,forgotten:false});globalThis.__hierarchyRecoveryControls.push({native,command:cmd,sequence:String(seq),exactReplay:true,changedBytesRejected:true,confirmReplay:true});}
  await settle();return out;},async read(b){const out=await base.read(b),v=new DataView(b);if(native&&v.getUint32(8,true)===23){const h=v.getBigUint64(16,true),record=issued.get(h),p=new DataView(out);assert.ok(record);assert.equal(p.getBigUint64(16,true),record.issuer);assert.equal(p.getBigUint64(24,true),record.sequence);globalThis.__hierarchyRecoveryPackets.push({magic:Buffer.from(out,0,4).toString(),owner:String(h),issuer:String(record.issuer),publication:String(record.sequence),bytes:out.byteLength,base64:Buffer.from(out).toString('base64')});}return out;}};
}
`;
assert.equal((text.match(/nativeGeoScaleBridge\(budget\.processorBytes\)/g)??[]).length,2);
text=text.replaceAll('nativeGeoScaleBridge(budget.processorBytes)','recoveryBridge(nativeGeoScaleBridge(budget.processorBytes),true)');
text=text.replace('const wasm={execute:', 'const wasmBase={execute:');
text=text.replace('function snapshotRequest(', 'const wasm=recoveryBridge(wasmBase);\nfunction snapshotRequest(');
text=text.replace('try{const cases=[];',instrumentation+'\ntry{const cases=[];');
text=text.replaceAll("'../packages/", "'"+pathToFileURL(new URL('../packages/',import.meta.url).pathname).href);
text=text.replaceAll('new URL(import.meta.url)','new URL('+JSON.stringify(original.href)+')');
await import('data:text/javascript;base64,'+Buffer.from(text).toString('base64'));
assert.ok(packets.length>=12);
if(!globalThis.__hierarchyRecoveryLegacy)assert.ok(controls.length>=20);
if(process.env.XYG_HIERARCHY_RECOVERY_PACKETS)await writeFile(process.env.XYG_HIERARCHY_RECOVERY_PACKETS,JSON.stringify({normalization:'none: full native packets after exact creation owner/publication validation',legacy:globalThis.__hierarchyRecoveryLegacy,controls,packets},null,2)+'\n');
delete globalThis.__hierarchyRecoveryPackets;
delete globalThis.__hierarchyRecoveryControls;
delete globalThis.__hierarchyRecoveryLegacy;
