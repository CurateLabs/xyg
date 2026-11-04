// TEST-ONLY scripted presentation protocol. No synthetic frame is native/cadence evidence.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { drainToComplete,validateFirstReplacement,createHeldAckQueue } from './ack-drain.mjs';
const base={jobId:'test-only-scripted:1',revision:1};
const panned={x0:5,x1:15,y0:10,y1:20};
const reset={x0:0,x1:10,y0:0,y1:10};
const ranges={x:[0,10],y:[0,10]};
const initial={...base,step:1,phase:'initial',view:panned};
function sequence(){
 const frames=[initial,{...base,step:11,phase:'update',previousView:panned,view:reset},
  {...base,step:21,phase:'update',previousView:reset,view:reset},
  {...base,step:31,phase:'complete',previousView:reset,view:reset}];
 let at=0;const accepted=[],completeWaiters=[];
 return {frames,accepted,release:async frame=>{assert.deepEqual(frame,frames[at]);accepted.push(frame.step);at++;if(frames[at]?.phase==='complete')for(const resolve of completeWaiters.splice(0))resolve(frames[at]);},waitNext:async()=>frames[at],waitForComplete:()=>new Promise(resolve=>{if(frames[at]?.phase==='complete')resolve(frames[at]);else completeWaiters.push(resolve);})};
}
test('scripted initial -> update -> update -> complete drains genuine ACKs and inspects FIRST replacement',async()=>{
 const s=sequence(),inspected=[];
 const result=await drainToComplete({...s,initial,onFirstReplacement:async first=>{inspected.push(first.step);validateFirstReplacement(first,panned,ranges);}});
 assert.deepEqual(s.accepted,[1,11,21]);assert.deepEqual(inspected,[11]);assert.equal(result.final.step,31);
 assert.deepEqual(result.replacementFrames.map(f=>f.phase),['update','update','complete']);
 assert.throws(()=>validateFirstReplacement(result.final,panned,ranges),'the historical final-only camera assertion must fail this valid sequence');
 await s.release(result.final);assert.deepEqual(s.accepted,[1,11,21,31]);
});
test('historical wait-for-complete path stalls on the same valid ACK-gated UPDATE',async()=>{
 const old=readFileSync(new URL('../graph-node-first-paint-1k-2026-11-04/inspection.mjs',import.meta.url),'utf8');
 assert.ok(old.includes("await pending.shift().release();\n await page.waitForFunction(()=>proof.frames.some(f=>f.phase==='complete')"));
 const s=sequence();await s.release(initial);
 const completion=s.waitForComplete();
 const result=await Promise.race([completion.then(()=> 'complete'),new Promise(r=>setTimeout(()=>r('bounded-test-timeout'),20))]);
 assert.equal(result,'bounded-test-timeout');assert.deepEqual(s.accepted,[1]);
 // The same observer does receive completion once the missing genuine ACKs arrive.
 await s.release(s.frames[1]);await s.release(s.frames[2]);assert.equal((await completion).phase,'complete');
});
test('drain rejects stale jobs, revisions, nonadvancing steps, phases and out-of-budget waits',async()=>{
 for(const patch of [{jobId:'stale'},{revision:2},{step:1},{step:402},{phase:'initial'}]){
  const s=sequence();await assert.rejects(drainToComplete({initial,release:s.release,waitNext:async()=>({...s.frames[1],...patch}),onFirstReplacement:()=>{}}));
 }
 await assert.rejects(drainToComplete({initial,release:()=>new Promise(()=>{}),waitNext:()=>{},onFirstReplacement:()=>{},timeoutMs:10}),/deadline/);
});
test('actual interception queue validates exact job/step without consuming a wrong ACK',async()=>{
 const held=createHeldAckQueue({timeoutMs:100}),continued=[];
 const route={request:()=>({postDataJSON:()=>({...base,step:1})}),continue:async()=>continued.push(1)};
 const intercepted=held.intercept(route);
 await assert.rejects(held.release({...initial,step:11}),/exact held frame/);
 assert.equal(held.count(),1);assert.deepEqual(continued,[]);
 await held.peek(initial);await held.release(initial);await intercepted;
 assert.equal(held.count(),0);assert.deepEqual(continued,[1]);
 await assert.rejects(held.peek(initial),/arrival deadline/);
});
