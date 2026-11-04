// Validate the NEW archived real-browser receipts independently of scripted ACK cases.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {validateUnheld,validateClick,same} from './protocol.mjs';
import {validateFirstReplacement} from './ack-drain.mjs';
const read=p=>JSON.parse(readFileSync(new URL(p,import.meta.url)));
const hash=b=>createHash('sha256').update(b).digest('hex');
const unheld=read('raw/unheld/result.json'),held=read('raw/held/result.json');
test('fresh real unheld frames retain geometry/source hashes with distinct timing bases',()=>{
 assert.equal(unheld.status,'passed');
 const checkpoints=unheld.evidence.events.filter(e=>e.type==='checkpoint');
 validateUnheld(unheld.proof,checkpoints);assert.equal(checkpoints.length,unheld.proof.frames.length);
 for(const p of checkpoints){
  const prefix=`raw/unheld/step-${p.step}`;
  assert.equal(hash(readFileSync(new URL(prefix+'-buffer.bin',import.meta.url))),p.bufferSha256);
  assert.equal(hash(Buffer.concat(['x','y'].map(axis=>readFileSync(new URL(prefix+'-'+axis+'.f64',import.meta.url))))),p.positionSha256);
  assert.ok(unheld.evidence.events.some(e=>e.type==='accepted'&&same(e,p)));
 }
 validateClick(unheld.settledInspection.location,unheld.settledInspection.click);
 assert.equal(unheld.settledInspection.syntheticClick.trusted,false);
});
test('fresh held inspection ACKs every actual replacement and checks first replacement, irrespective of phase',()=>{
 assert.equal(held.status,'passed');
 assert.equal(held.rejected,409);assert.equal(held.checkpointsAfterInspectionBeforeRelease,1);
 validateClick(held.interaction.location,held.interaction.click);
 validateFirstReplacement(held.firstReplacement,held.interaction.after,held.firstReplacementSpecRanges);
 const identities=frames=>frames.map(f=>[f.jobId,f.revision,f.step,f.phase]);
 assert.deepEqual(identities(held.drain.replacementFrames),identities(held.proof.frames.slice(1))); // ACK completion timestamps are added after the held snapshot.
 for(const p of held.proof.frames)assert.ok(held.evidence.events.some(e=>e.type==='accepted'&&same(e,p)));
 assert.equal(held.final.phase,'complete');assert.equal(held.final.step,held.proof.frames.at(-1).step);
});
test('fresh real fixture, bridge and force Workers directly attest the independently checked selected file',()=>{
 for(const report of [unheld,held]){
  const p=report.artifactProvenance??report.artifacts;
  const native=p.native;
  assert.equal(native.abi,399);assert.equal(native.origin.declaredKind,'unknown');assert.equal(native.matchesKnownParentArtifact,true);
  assert.equal(p.independentNativeBinding.sha256,native.sha256);assert.equal(p.independentNativeBinding.resolvedSelectedPath,native.resolvedSelectedPath);
  for(const role of ['fixture-main','bridge-worker','force-worker'])assert.ok(p.nativeProducerObservations.records.some(r=>r.role===role));
  for(const r of p.nativeProducerObservations.records){assert.equal(r.native.resolvedSelectedPath,native.resolvedSelectedPath);assert.equal(r.native.sha256,native.sha256);assert.equal(r.native.abi,native.abi);}
  assert.deepEqual(report.evidence.selectedNative,native);assert.deepEqual(report.evidence.selectedNativeRecheck,native);
 }
});
