// Negative evidence-contract tests: prevent checkpoint/paint, ACK and identity misattribution.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { validateUnheld, validateClick, same } from './protocol.mjs';
const id={jobId:'a:1',revision:1,step:1};
const frame=(step,phase)=>({...id,step,phase,receivedMs:20+step,paintedMs:30+step,ackStartedMs:40+step,coloredPixels:10,gpuHit:{trace:0,index:0},gpuPickReadyMs:35+step});
const valid=()=>({mode:'automatic-after-frame',deliberateHolds:0,frames:[frame(1,'initial'),frame(11,'complete')]});
const host=[{...id,ms:5},{...id,step:11,ms:8}];
test('checkpoint arrival cannot substitute for painted geometry or matching frame identity',()=>{
 const result=validateUnheld(valid(),host);assert.equal(result.firstCheckpointHostMs,5);assert.equal(result.firstPaintedBrowserMs,31);
 for(const patch of [{coloredPixels:0},{jobId:'stale'},{paintedMs:1},{gpuHit:null}]){const b=valid();Object.assign(b.frames[0],patch);assert.throws(()=>validateUnheld(b,host));}
});
test('held consumer and acceptance before paint cannot qualify unheld cadence',()=>{
 for(const patch of [{mode:'held-inspection'},{deliberateHolds:1}])assert.throws(()=>validateUnheld({...valid(),...patch},host));
 const b=valid();b.frames[0].ackStartedMs=2;assert.throws(()=>validateUnheld(b,host));
 assert.equal(same(id,{...id,step:11}),false);assert.equal(same(id,{...id,jobId:'wrong'}),false);
});
test('trusted pointer must identify the exact probed render row and tooltip UUID',()=>{
 const location={...id,hit:{trace:0,index:7}},click={...id,trusted:true,detail:{trace:0,index:7,row:{id:'uuid'}},identity:{uuid:'uuid'}};
 validateClick(location,click);
 for(const patch of [{trusted:false},{step:11},{identity:{uuid:'wrong'}},{detail:{trace:0,index:8,row:{id:'uuid'}}}])assert.throws(()=>validateClick(location,{...click,...patch}));
});
