#!/usr/bin/env node
// Cold-process compile/instantiate evidence. This does not measure browser painting.
import {readFileSync,writeFileSync} from 'node:fs';
import {execFileSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';
import {performance} from 'node:perf_hooks';
import os from 'node:os';
const [a,b,out]=process.argv.slice(2);
if(a==='--child'){
 const start=performance.now(),bytes=readFileSync(b),readMs=performance.now()-start;
 const compileStart=performance.now(),module=await WebAssembly.compile(bytes),compileMs=performance.now()-compileStart;
 const instanceStart=performance.now(),instance=await WebAssembly.instantiate(module,{}),handle=instance.exports.xyg_wasm_instance_new(384<<20),instantiateMs=performance.now()-instanceStart;
 if(!handle)throw Error('instance admission failed');
 const memoryBytes=instance.exports.memory.buffer.byteLength;instance.exports.xyg_wasm_instance_dispose(handle);
 console.log(JSON.stringify({readMs,compileMs,instantiateMs,memoryBytes,maxRssBytes:process.resourceUsage().maxRSS*1024}));
}else{
 if(!out)throw Error('usage: bench_wasm_startup.mjs A.wasm B.wasm OUTPUT.json');
 const samples=[];
 for(let pair=0;pair<4;pair++)for(const label of ['A','B','B','A']){
  const start=performance.now(),result=JSON.parse(execFileSync(process.execPath,[fileURLToPath(import.meta.url),'--child',label==='A'?a:b],{encoding:'utf8'}));
  samples.push({pair,label,...result,childWallMs:performance.now()-start});
 }
 writeFileSync(out,JSON.stringify({schema:'xyg-wasm-cold-start-abba-v1',environment:{node:process.version,platform:process.platform,arch:process.arch,cpu:os.cpus()[0].model},artifacts:{A:a,B:b},samples},null,2)+'\n');
 console.log(out);
}
