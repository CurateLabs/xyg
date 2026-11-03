import assert from 'node:assert/strict';
import test from 'node:test';
import {createHostTickEngine,encodeWasmTickBatch,decodeWasmTickBatch} from '../../xy-client/dist/index.js';
import {tickResolvePacked} from '../src/index.js';

const packet=sequence=>{const value=new ArrayBuffer(32);new DataView(value).setUint32(12,sequence,true);return value;};

test('native tick transport uses the byte-exact canonical Rust contract',async()=>{
 const engine=createHostTickEngine({resolve:async packet=>tickResolvePacked(packet).buffer});
 try{
  const sequence=engine.allocateTickSequence();
  const packet=encodeWasmTickBatch({sequence,axes:[{axisId:1,revision:1,family:'linear',provenance:'automatic',lo:0,hi:10,target:5}]});
  const expected=tickResolvePacked(packet);
  const actual=await engine.resolveTicks(packet,{sequence}).result;
  assert.deepEqual(new Uint8Array(actual),expected);
  assert.equal(decodeWasmTickBatch(actual).axes[0].revision,1);
 }finally{await engine.dispose();}
});
test('cancellation and disposal reject late transport responses',async()=>{
 let finish;const engine=createHostTickEngine({resolve:()=>new Promise(resolve=>{finish=resolve;})});
 const sequence=engine.allocateTickSequence(),task=engine.resolveTicks(packet(sequence),{sequence});
 await Promise.resolve();task.cancel();await assert.rejects(task.result,/cancelled/i);finish(new ArrayBuffer(32));
 const next=engine.resolveTicks(packet(2),{sequence:engine.allocateTickSequence()});
 await Promise.resolve();await engine.dispose();await assert.rejects(next.result,/cancelled/i);
 assert.throws(()=>engine.allocateTickSequence(),/disposed/i);
});

test('pre-dispatch cancellation and disposal never start transport work',async()=>{
 for(const dispose of [false,true]){
  let calls=0;const engine=createHostTickEngine({resolve:async()=>{calls++;return new ArrayBuffer(32);}});
  const sequence=engine.allocateTickSequence(),task=engine.resolveTicks(packet(sequence),{sequence});
  if(dispose)await engine.dispose();else task.cancel();
  await assert.rejects(task.result,/cancelled/i);assert.equal(calls,0);await engine.dispose();
 }
});
test('packed header identity and explicit allocation stay monotonic',async()=>{
 const engine=createHostTickEngine({resolve:async request=>request});
 assert.throws(()=>engine.resolveTicks(new ArrayBuffer(31),{sequence:1}),/invalid/);
 assert.throws(()=>engine.resolveTicks(packet(100),{sequence:7}),/header sequence/);
 await engine.resolveTicks(packet(100),{sequence:100}).result;
 assert.equal(engine.allocateTickSequence(),101);await engine.dispose();
});
