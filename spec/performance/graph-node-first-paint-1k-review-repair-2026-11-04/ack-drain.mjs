// Evidence-only ACK protocol. Synthetic sequences belong only in labelled tests.
import assert from 'node:assert/strict';
import { performance } from 'node:perf_hooks';
import { same } from './protocol.mjs';
export function validateNext(previous,next,maxStep=401){
 assert.equal(next.jobId,previous.jobId,'replacement must belong to the same job');
 assert.equal(next.revision,previous.revision,'replacement must belong to the same revision');
 assert.ok(Number.isSafeInteger(next.step)&&next.step>previous.step&&next.step<=maxStep,'replacement step must advance within the requested cap');
 assert.ok(['update','complete'].includes(next.phase),'replacement must be update or complete');
}
export function validateFirstReplacement(first,panned,ranges){
 assert.deepEqual(first.previousView,panned,'first replacement must follow the inspected panned frame');
 assert.notDeepEqual(first.view,panned,'replacement discarded panned viewport');
 assert.deepEqual([first.view.x0,first.view.x1],ranges.x);
 assert.deepEqual([first.view.y0,first.view.y1],ranges.y);
}
export async function drainToComplete({initial,release,waitNext,onFirstReplacement,timeoutMs=30000}){
 assert.equal(initial.phase,'initial');
 const deadline=performance.now()+timeoutMs,frames=[];
 async function bounded(operation){
  const remaining=deadline-performance.now();assert.ok(remaining>0,'held ACK drain deadline exceeded');
  let timer;try{return await Promise.race([Promise.resolve().then(operation),new Promise((_,reject)=>{timer=setTimeout(()=>reject(Error('held ACK drain deadline exceeded')),remaining);})]);}finally{clearTimeout(timer);}
 }
 let previous=initial;
 while(true){
  await bounded(()=>release(previous));
  const next=await bounded(()=>waitNext(previous));validateNext(previous,next);
  if(!frames.length)await bounded(()=>onFirstReplacement(next));
  frames.push(next);
  if(next.phase==='complete')return {firstReplacement:frames[0],final:next,replacementFrames:frames};
  previous=next;
 }
}
export function validateHeldAck(ack,frame){assert.ok(same(ack,frame),'intercepted ACK must match the exact held frame');}
export function createHeldAckQueue({timeoutMs=30000}={}){
 const pending=[],waiters=[];
 async function available(){
  if(pending.length)return pending[0];
  let notify,timer;
  try{
   await new Promise((resolve,reject)=>{
    notify=resolve;waiters.push(notify);
    timer=setTimeout(()=>reject(Error('intercepted ACK arrival deadline exceeded')),timeoutMs);
   });
  }finally{clearTimeout(timer);const i=waiters.indexOf(notify);if(i>=0)waiters.splice(i,1);}
  assert.ok(pending.length);return pending[0];
 }
 return {
  intercept:route=>new Promise((resolve,reject)=>{pending.push({route,resolve,reject});for(const notify of waiters.splice(0))notify();}),
  count:()=>pending.length,
  peek:async frame=>{const held=await available();validateHeldAck(held.route.request().postDataJSON(),frame);return held;},
  release:async frame=>{
   const held=await available();validateHeldAck(held.route.request().postDataJSON(),frame);
   pending.shift();try{await held.route.continue();held.resolve();}catch(error){held.reject(error);throw error;}
  }
 };
}
