#!/usr/bin/env node
// Small actual native/wasm snapshot namespace proof, no browser policy or timing claim.
import assert from 'node:assert/strict';
import {readFile,writeFile} from 'node:fs/promises';
import {createHash} from 'node:crypto';
import {nativeGeoScaleBridge} from '../packages/xy-node/src/geoscale.js';
import {nativeGeoSnapshotBridge} from '../packages/xy-node/src/geo-snapshot.js';
import {buildOverviewPainterFixture,BUDGET,snapshotRequest} from '../tests/browser/geo_overview_painter_fixture.mjs';
const artifact=await readFile(new URL('../packages/xy-client/dist/xyg-wasm.wasm',import.meta.url));
const {instance}=await WebAssembly.instantiate(artifact,{}),x=instance.exports,h=x.xyg_wasm_instance_new(BUDGET.processorBytes);assert.ok(h);let sequence=0;
function call(family,read,r){assert.equal(x.xyg_wasm_arena_resize(h,r.byteLength),0);new Uint8Array(x.memory.buffer,x.xyg_wasm_arena_ptr(h)>>>0,r.byteLength).set(new Uint8Array(r));const code=x[`xyg_wasm_geo_${family}_${read?'read':'execute'}`](h,++sequence,0,r.byteLength);if(code)throw Error(`WASM ${code}: `+new TextDecoder().decode(new Uint8Array(x.memory.buffer,x.xyg_wasm_last_error_ptr(h)>>>0,x.xyg_wasm_last_error_len(h))));return new Uint8Array(x.memory.buffer,x.xyg_wasm_output_ptr(h)>>>0,x.xyg_wasm_output_len(h)).slice().buffer;}
const wasm={source:{execute:async r=>call('scale',false,r),read:async r=>call('scale',true,r)},snapshot:{execute:async r=>call('snapshot',false,r),read:async r=>call('snapshot',true,r)}};
const native={source:nativeGeoScaleBridge(BUDGET.processorBytes),snapshot:nativeGeoSnapshotBridge(384<<20)};
function req(command,issuer,nonce=0n,target=0n,action=0){const b=snapshotRequest(command===7?6:command,issuer,{sequence:7n,budget:command===6?128<<20:0});const v=new DataView(b);v.setUint32(8,command,true);v.setBigUint64(240,nonce,true);if(command===7){v.setBigUint64(40,target,true);v.setUint32(48,action,true);}return b;}
function target(b,kind=0){assert.equal(b.byteLength,256);const v=new DataView(b);assert.equal(v.getUint32(0,true),0x57475958);assert.equal(v.getUint32(8,true),kind);return v.getBigUint64(16,true);}
const packetReports=[];
async function proof(bridge){
 let fixture=await buildOverviewPainterFixture(bridge),legacy,owner;const live=[];
 try{
  legacy=await fixture.freeze();const expected=new Uint8Array(legacy.bytes).slice();await legacy.dispose();legacy=undefined;
  const canonical=req(6,fixture.handle,1n),receipt=await bridge.snapshot.execute(canonical);owner=target(receipt);live.push(owner);assert.deepEqual(await bridge.snapshot.execute(canonical),receipt);
  await assert.rejects(bridge.snapshot.read(snapshotRequest(20,owner)));
  const mismatch=canonical.slice(0);new DataView(mismatch).setBigUint64(32,64n<<20n,true);await assert.rejects(bridge.snapshot.execute(mismatch));
  await assert.rejects(bridge.snapshot.execute(req(7,fixture.handle,1n,owner,2)));
  const confirm=await bridge.snapshot.execute(req(7,fixture.handle,1n,owner));assert.equal(target(confirm),owner);assert.equal(new DataView(confirm).getBigUint64(32,true),0n);
  const frozen=await bridge.snapshot.read(snapshotRequest(20,owner));assert.deepEqual(new Uint8Array(frozen),expected);await bridge.snapshot.read(snapshotRequest(20,owner));await assert.rejects(bridge.snapshot.read(snapshotRequest(20,owner)));
  for(let nonce=2n;nonce<=8n;nonce++){const r=await bridge.snapshot.execute(req(6,fixture.handle,nonce)),id=target(r);live.push(id);assert.equal(target(await bridge.snapshot.execute(req(7,fixture.handle,nonce,id))),id);}
  await assert.rejects(bridge.snapshot.execute(req(6,fixture.handle,9n)));
  await fixture.dispose();fixture=undefined;assert.deepEqual(await bridge.snapshot.execute(canonical),receipt);
  // Simulate lost successful disposal confirmation: discard result, recover from birth.
  for(let i=0;i<live.length;i++){
   const id=live[i],nonce=BigInt(i+1);await bridge.snapshot.execute(snapshotRequest(3,id));
   const retired=await bridge.snapshot.execute(req(7,new DataView(canonical).getBigUint64(16,true),nonce,0n));assert.equal(target(retired,2),0n);
   const release=req(7,new DataView(canonical).getBigUint64(16,true),nonce,0n,2);await bridge.snapshot.execute(release);assert.equal(target(await bridge.snapshot.execute(release)),0n);
  }
  live.length=0;
  const report={binaryBytes:frozen.byteLength,binarySha256:createHash('sha256').update(new Uint8Array(frozen)).digest('hex'),eightSnapshots:true,legacyBytesIdentical:true,replayAfterIssuerGone:true,strictRequest:true,confirmBeforeRead:true,twoReadQuota:true,lostDisposeAndRelease:true};packetReports.push(report);return report;
 }finally{if(legacy)await legacy.dispose();for(const id of live)try{await bridge.snapshot.execute(snapshotRequest(3,id));}catch{}if(fixture)await fixture.dispose();}
}
try{assert.deepEqual(await proof(native),await proof(wasm));const report={artifactSha256:createHash('sha256').update(artifact).digest('hex'),packets:packetReports,scope:'small actual native/WASM Snapshot-local6/7 proof; no performance or selected overview claim'};if(process.env.XYG_SNAPSHOT_RECOVERY_REPORT)await writeFile(process.env.XYG_SNAPSHOT_RECOVERY_REPORT,JSON.stringify(report,null,2)+'\n');console.log(JSON.stringify(report));}finally{x.xyg_wasm_instance_dispose(h);}
