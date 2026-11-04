// Read-only async resource observation, inherited by real Node Workers.
import { createHook } from 'node:async_hooks';
import { writeSync } from 'node:fs';
import { threadId } from 'node:worker_threads';
const workers=new Set();
const record=(event,id)=>writeSync(1,JSON.stringify({audit:'WORKER',threadId,event,id,hrtimeNs:process.hrtime.bigint().toString()})+'\n');
createHook({init(id,type){if(type==='WORKER'){workers.add(id);record('init',id);}},destroy(id){if(workers.delete(id))record('destroy',id);}}).enable();
