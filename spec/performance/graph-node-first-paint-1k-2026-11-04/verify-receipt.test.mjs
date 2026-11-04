// Inspect actual archived browser/host evidence, not reconstructed implementation output.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { validateUnheld, validateClick, same } from './protocol.mjs';
const read=p=>JSON.parse(readFileSync(new URL(p,import.meta.url)));
const unheld=read('raw/unheld/result.json'),held=read('raw/held/result.json');
const hash=b=>createHash('sha256').update(b).digest('hex');
test('actual default browser flow ACKs every matching painted checkpoint without a deliberate hold',()=>{
 assert.equal(unheld.status,'passed');
 const events=unheld.evidence.events,checkpoints=events.filter(e=>e.type==='checkpoint');
 validateUnheld(unheld.proof,checkpoints);
 assert.equal(checkpoints.length,unheld.proof.frames.length);
 for(const checkpoint of checkpoints){
  const arrival=events.indexOf(checkpoint),accepted=events.findIndex(e=>e.type==='accepted'&&same(e,checkpoint));
  assert.ok(accepted>arrival);
  assert.equal(events.slice(arrival+1,accepted).some(e=>e.type==='checkpoint'),false);
  const f=unheld.proof.frames.find(f=>same(f,checkpoint));
  assert.ok(f.ackCompletedMs>=f.ackStartedMs);
 }
 assert.equal(events.at(-1).type,'disposed');
 assert.deepEqual(unheld.errors,[]);
});
test('retained geometry and full f64 snapshots bind each actual frame to native payload identities',()=>{
 const checkpoints=unheld.evidence.events.filter(e=>e.type==='checkpoint');
 for(const p of checkpoints){
  const prefix=`raw/unheld/step-${p.step}`;
  const buffer=readFileSync(new URL(prefix+'-buffer.bin',import.meta.url));
  assert.equal(hash(buffer),p.bufferSha256);assert.equal(buffer.length,p.bufferBytes);
  const x=readFileSync(new URL(prefix+'-x.f64',import.meta.url)),y=readFileSync(new URL(prefix+'-y.f64',import.meta.url));
  assert.equal(x.length,1000*8);assert.equal(y.length,1000*8);
  assert.equal(hash(Buffer.concat([x,y])),p.positionSha256);
  const graph=read(prefix+'-spec.json').graph[0];
  assert.equal(graph.source_n_nodes,1000);assert.equal(graph.source_n_edges,2000);assert.equal(graph.tier_name,'direct');
 }
 assert.notEqual(checkpoints[0].positionSha256,checkpoints.at(-1).positionSha256);
});
test('held invalid ACK cannot advance presentation; trusted initial pick and camera reset are separate facts',()=>{
 assert.equal(held.status,'passed');assert.equal(held.rejected,409);
 assert.equal(held.checkpointsBeforeBadAck,1);assert.equal(held.checkpointsAfterInspectionBeforeRelease,1);
 const events=held.evidence.events;
 const rejection=events.findIndex(e=>e.type==='rejected-ack'),accepted=events.findIndex(e=>e.type==='accepted');
 assert.ok(rejection>=0&&accepted>rejection);
 assert.equal(events.slice(rejection+1,accepted).some(e=>e.type==='checkpoint'),false);
 validateClick(held.interaction.location,held.interaction.click);
 assert.deepEqual(held.final.previousView,held.interaction.after);
 assert.notDeepEqual(held.final.view,held.interaction.after);
 assert.deepEqual([held.final.view.x0,held.final.view.x1],held.finalSpecRanges.x);
 assert.deepEqual([held.final.view.y0,held.final.view.y1],held.finalSpecRanges.y);
});
test('actual synthetic custom click after a real pointer cannot inherit its trust',()=>{
 const {location,click,syntheticClick}=unheld.settledInspection;
 validateClick(location,click);
 assert.equal(click.pointer.downTrusted,true);assert.equal(click.pointer.upTrusted,true);
 assert.equal(syntheticClick.pointer,null);assert.equal(syntheticClick.trusted,false);
 assert.throws(()=>validateClick(location,syntheticClick));
});
test('observed worker resources balance; cancellation/disposal are terminal in the separate native job',()=>{
 for(const r of [unheld,held]){
  const active=new Set();
  for(const e of r.workerAudit){const key=e.threadId+':'+e.id;
   if(e.event==='init'){assert.equal(active.has(key),false);active.add(key);}else assert.equal(active.delete(key),true);
  }
  assert.ok(r.workerAudit.length>=4);assert.equal(active.size,0);
 }
 assert.equal(unheld.cancellation.code,'GF_LAYOUT_ABORTED');
 assert.equal(unheld.cancellation.terminal,'GF_LAYOUT_DISPOSED');
 assert.equal(unheld.cancellation.calls,unheld.cancellation.atSettlement);
});
