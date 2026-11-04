// Read-only async resource observation, inherited by real Node Workers.
import { createHook } from 'node:async_hooks';
import { writeSync } from 'node:fs';
import { threadId } from 'node:worker_threads';
const workers=new Set();
const record=(event,id)=>writeSync(1,JSON.stringify({audit:'WORKER',threadId,event,id,hrtimeNs:process.hrtime.bigint().toString()})+'\n');
createHook({init(id,type){if(type==='WORKER'){workers.add(id);record('init',id);}},destroy(id){if(workers.delete(id))record('destroy',id);}}).enable();
// Observe the exact native module singleton subsequently used by each entrypoint.
const { nativeLibraryPath }=await import('../../../packages/xy-node/src/native.js');
const { abiVersion }=await import('../../../packages/xy-node/src/abi.js');
const { workerData,isMainThread }=await import('node:worker_threads');
const { attestNative }=await import('./native-provenance.mjs');
const role=isMainThread?'fixture-main':workerData?.type==='force_ticks'?'force-worker':workerData?.jobId?'bridge-worker':'unclassified-worker';
writeSync(1,JSON.stringify({audit:'NATIVE',threadId,role,jobId:workerData?.jobId??workerData?.args?.jobId??null,native:attestNative(nativeLibraryPath,abiVersion())})+'\n');
