// Run from repository root using the documented repository Playwright workflow.
import assert from 'node:assert/strict';
import { spawn, execFileSync } from 'node:child_process';
import { readFileSync, writeFileSync, mkdirSync, existsSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { performance } from 'node:perf_hooks';
import os from 'node:os';
import { chromium } from 'playwright';
import { validateUnheld, validateClick } from './protocol.mjs';
import { verifyNative,verifyNativeRecords,admitKnownParentCapture } from './native-provenance.mjs';
const root=new URL('../../../',import.meta.url);
const output=process.env.XYG_NODE_PAINT_OUTPUT??`target/task-tmp/node-first-paint-1k-review-repair-${Date.now()}/`;
const out=new URL(output.endsWith('/')?output:output+'/',root);
assert.equal(existsSync(out),false,'append-only: use a new output directory');mkdirSync(out,{recursive:true});
const write=(name,v)=>writeFileSync(new URL(name,out),typeof v==='string'||Buffer.isBuffer(v)?v:JSON.stringify(v,null,2)+'\n');
const sha=b=>createHash('sha256').update(b).digest('hex');
const hashFile=p=>sha(readFileSync(new URL(p,root)));
const chrome=process.env.XYG_CHROMIUM;assert.ok(chrome,'XYG_CHROMIUM required');
const started=performance.now();
const child=spawn(process.execPath,['--import',new URL('worker-audit.mjs',import.meta.url).pathname,new URL('fixture.mjs',import.meta.url).pathname],{cwd:root,env:process.env,stdio:['ignore','pipe','pipe']});
let logs='',browser,report={status:'started'},errors=[],requests=[];
child.stdout.on('data',b=>logs+=b);child.stderr.on('data',b=>logs+=b);
try{
 const url=await new Promise((resolve,reject)=>{
  const timeout=setTimeout(()=>reject(Error('fixture startup timeout')),15000);
  const inspect=()=>{const hit=logs.match(/XYG_GRAPHFORGE_LIVE_URL=(\S+)/);if(hit){clearTimeout(timeout);resolve(hit[1]);}};
  child.stdout.on('data',inspect);inspect();child.once('exit',code=>{clearTimeout(timeout);reject(Error(`fixture exited ${code}: ${logs}`));});
 });
 const nodeColdStartupMs=performance.now()-started;
 const identityStarted=performance.now();
 const fixtureIdentityBefore=await(await fetch(url+'/evidence')).json();
 report.selectedNativeBeforeCapture=fixtureIdentityBefore.selectedNative;
 const independentNativeBinding=admitKnownParentCapture(fixtureIdentityBefore.selectedNative);
 const identityVerificationParentMs=performance.now()-identityStarted;
 const browserStart=performance.now();
 browser=await chromium.launch({executablePath:chrome,headless:true,args:['--no-sandbox','--use-gl=angle','--use-angle=swiftshader','--enable-unsafe-swiftshader']});
 const browserColdStartupMs=performance.now()-browserStart;
 const contextStart=performance.now(),context=await browser.newContext({viewport:{width:900,height:650}}),page=await context.newPage();
 page.on('pageerror',e=>errors.push(e.message));page.on('request',r=>requests.push(r.url()));
 await page.goto(url,{waitUntil:'networkidle'});
 const contextAndNavigationMs=performance.now()-contextStart;
 await page.evaluate(()=>{beginGraph().catch(e=>proof.errors.push(String(e)));});
 await page.waitForFunction(()=>proof.frames.length>0||proof.errors.length>0,null,{timeout:30000});
 const firstFrameObservedFromParentStartMs=performance.now()-started;
 await page.waitForFunction(()=>proof.done||proof.errors.length>0,null,{timeout:30000});
 let proof=await page.evaluate(()=>window.proof);
 assert.deepEqual(proof.errors,[]);
 const evidence=await(await fetch(url+'/evidence')).json();
 const checkpoints=evidence.events.filter(e=>e.type==='checkpoint');
 const timings=validateUnheld(proof,checkpoints);
 assert.notEqual(checkpoints[0].positionSha256,checkpoints.at(-1).positionSha256);
 const retained=await(await fetch(url+'/snapshot')).json();
 for(const p of retained){
  const prefix=`step-${p.step}`;
  write(prefix+'-spec.json',p.spec);
  const buffer=Buffer.from(await(await fetch(url+'/buffer/'+p.step)).arrayBuffer());
  assert.equal(sha(buffer),checkpoints.find(c=>c.step===p.step).bufferSha256);
  write(prefix+'-buffer.bin',buffer);write(prefix+'-x.f64',Buffer.from(p.xBase64,'base64'));write(prefix+'-y.f64',Buffer.from(p.yBase64,'base64'));
 }
 write('positions-uuid.json',retained[0].positionsUuid);
 write('initial-canvas.png',Buffer.from(proof.initialPng.split(',')[1],'base64'));
 write('final-canvas.png',Buffer.from(proof.finalPng.split(',')[1],'base64'));
 await page.screenshot({path:new URL('final-page.png',out).pathname});
 // Separate settled-frame inspection; the unheld cadence above has already ended.
 const location=await page.evaluate(()=>findNode());
 const pointerStart=performance.now();await page.mouse.click(location.x,location.y);
 await page.waitForFunction(()=>proof.clicks.length>0,null,{timeout:5000});
 const click=await page.evaluate(()=>proof.clicks.at(-1));validateClick(location,click);
 const pointerToUuidParentMs=performance.now()-pointerStart;
 // A synthetic custom click after a real pointer must not inherit its trust.
 await page.evaluate(detail=>document.getElementById('chart').dispatchEvent(new CustomEvent('xy:click',{detail})),click.detail);
 await page.waitForFunction(()=>proof.clicks.length===2);
 const syntheticClick=await page.evaluate(()=>proof.clicks.at(-1));
 assert.equal(syntheticClick.trusted,false);assert.throws(()=>validateClick(location,syntheticClick));
 const panBefore=await page.evaluate(()=>({...graphView.view}));
 const box=await page.locator('#chart canvas').first().boundingBox(),panStart=performance.now();
 await page.mouse.move(box.x+box.width*.5,box.y+box.height*.6);await page.mouse.down();
 await page.mouse.move(box.x+box.width*.5+35,box.y+box.height*.6+20,{steps:5});await page.mouse.up();
 await page.waitForFunction(old=>graphView.view.x0!==old.x0||graphView.view.y0!==old.y0,panBefore,{timeout:5000});
 const panAfter=await page.evaluate(()=>({...graphView.view}));
 const panResponseParentMs=performance.now()-panStart;
 await page.screenshot({path:new URL('panned-page.png',out).pathname});
 // Bad ACK / wrong-job identity must not be accepted, even after completion.
 const badAckStatus=(await fetch(url+'/accept',{method:'POST',body:JSON.stringify({...location,jobId:'wrong-job'})})).status;
 const badPickStatus=(await fetch(url+'/pick',{method:'POST',body:JSON.stringify({...location,jobId:'wrong-job',hit:location.hit})})).status;
 assert.equal(badAckStatus,409);assert.equal(badPickStatus,409);
 const cancellation=await(await fetch(url+'/cancel-probe',{method:'POST'})).json();
 assert.equal(cancellation.code,'GF_LAYOUT_ABORTED');assert.equal(cancellation.terminal,'GF_LAYOUT_DISPOSED');assert.equal(cancellation.calls,cancellation.atSettlement);
 await page.evaluate(()=>disposeGraph());assert.equal(await page.locator('#chart canvas').count(),0);
 assert.equal((await(await fetch(url+'/dispose',{method:'POST'})).json()).disposed,true);
 const after=await(await fetch(url+'/evidence')).json();
 assert.deepEqual(after.selectedNative,fixtureIdentityBefore.selectedNative);
 assert.deepEqual(after.selectedNativeRecheck,fixtureIdentityBefore.selectedNative);
 verifyNative(after.selectedNative);
 const nativeProducerObservations=verifyNativeRecords(logs,after.selectedNative,[...new Set(after.events.filter(e=>e.type==='checkpoint').map(e=>e.jobId))]);
 proof=await page.evaluate(()=>{const {initialPng,finalPng,...p}=proof;return p;});
 assert.deepEqual(errors,[]);assert.deepEqual(proof.errors,[]);
 assert.ok(requests.every(r=>new URL(r).origin===url));
 const graphics=await page.evaluate(()=>{const canvas=document.createElement('canvas'),gl=canvas.getContext('webgl2'),ext=gl.getExtension('WEBGL_debug_renderer_info');return{vendor:gl.getParameter(ext.UNMASKED_VENDOR_WEBGL),renderer:gl.getParameter(ext.UNMASKED_RENDERER_WEBGL)};});
 const sourcePaths=['AGENTS.md','package-lock.json','packages/xy-node/package-lock.json','examples/vanilla-ts/graphforge-live.mjs',
 'scripts/bench_cose_progressive_node.mjs','scripts/bench_cose_progressive.py','packages/xy-node/src/graphforge.js',
 'packages/xy-node/src/graphforge_layout.js','packages/xy-node/src/graphforge_layout_worker.js','packages/xy-node/src/force_scheduler.js',
 'packages/xy-node/src/abi.js','packages/xy-node/src/graph.js','packages/xy-node/src/native.js','packages/xy-node/src/native-path.js','packages/xy-node/src/_abi_generated.js',
 'spec/performance/cose-progressive-ladder-2026-10-20/results.json',
 'spec/performance/graph-node-scheduling-35-review-repair-2026-10-31/run.mjs'];
 const thisFolder='spec/performance/graph-node-first-paint-1k-review-repair-2026-11-04/';
 sourcePaths.push(...['run.mjs','inspection.mjs','fixture.mjs','protocol.mjs','worker-audit.mjs','protocol.test.mjs','ack-drain.mjs','native-provenance.mjs','ack-drain.test.mjs','native-provenance.test.mjs','verify-repair.test.mjs'].map(p=>thisFolder+p));
 report={schema:'node-rendered-first-paint-1k/2',status:'passed',sourceBase:execFileSync('git',['rev-parse','HEAD'],{cwd:root,encoding:'utf8'}).trim(),
  gitStatus:execFileSync('git',['status','--short'],{cwd:root,encoding:'utf8'}),
  scope:'One instrumented local 1k Node live run; partial #35 evidence only. No timing gate, scale/competitor win, notebook/browser scheduler or release qualification.',
  protocol:{topology:'historical ring + deterministic chord (2 edges/node)',layout:'cose',seed:7,iterations:401,chunkSteps:'omitted: live default 10',maxWallMs:'omitted: live default 30000',
   options:'No authored positions, pins, masks, CoSE overrides, LOD or tolerance overrides. legend:false; width:720 height:480 as historical live fixture.',
   ack:'Automatically after two rAFs, visible canvas pixel readback, GPU node-hit probe and initial/final PNG encoding. No intentional delay or inspection hold; instrumentation costs are included.',
   camera:'Whole ChartView replaced on each payload. View snapshots recorded, with no continuity repair.',
   clocks:'Host checkpoint ms: Node performance.now minus server /start. Browser received/paint/GPU/ACK ms: page performance.now minus beginGraph. Parent startup/interaction observations use runner performance.now; no cross-clock subtraction. Painted time is an observation upper bound after two rAFs and pixel readback, not scanout timing.',
   interactivity:'Initial and subsequent GPU node-hit readiness is synchronous diagnostic evidence; trusted Playwright pointer UUID and pan response occur only on settled final frame, outside cadence. Initial trusted pointer response remains unmeasured.'},
  environment:{node:process.version,nodeExecutable:process.execPath,chromium:await browser.version(),chromiumExecutable:chrome,playwright:JSON.parse(readFileSync(new URL('node_modules/playwright/package.json',root))).version,
   os:os.release(),platform:process.platform,arch:process.arch,cpu:os.cpus()[0].model,cpuCount:os.cpus().length,totalMemoryBytes:os.totalmem(),loadavg:os.loadavg(),graphics,
   nativeAbi:after.selectedNative.abi},
  artifactProvenance:{native:after.selectedNative,independentNativeBinding,nativeProducerObservations,
   client:'Existing generated client observed by byte identity; no fresh client build invocation in this repair.',clientStandaloneSha256:hashFile('packages/xy-client/dist/standalone.js'),clientEsmSha256:hashFile('packages/xy-client/dist/index.js'),
   nodeSha256:hashFile(process.execPath),chromiumSha256:hashFile(chrome),wasm:'Unused; no module/package gate changes or claims.'},
  sourceHashes:Object.fromEntries(sourcePaths.map(p=>[p,hashFile(p)])),
  nodeColdStartupMs,browserColdStartupMs,contextAndNavigationMs,identityVerificationParentMs,firstFrameObservedFromParentStartMs,timings,proof,evidence:after,
  settledInspection:{location,click,syntheticClick,pointerToUuidParentMs,panBefore,panAfter,panResponseParentMs,badAckStatus,badPickStatus},cancellation,errors,requests,
  limitations:['single run on shared host with software GL','payload/source retention and pixel/GPU probes add measurement overhead','no native scheduler checkpoint instrumentation: callback steps expose actual coalesced presentations only','no complete memory/VRAM accounting or destructor instrumentation; worker resource logs are observational','unheld camera input during replacement not measured; prior whole-view replacement behavior remains','401 is historical rung cap; live default iteration cap is 300; convergence may finish earlier']};
 console.log(JSON.stringify({status:report.status,timings,nodeColdStartupMs,browserColdStartupMs,frames:proof.frames.map(f=>({step:f.step,phase:f.phase,coloredPixels:f.coloredPixels})),pointerToUuidParentMs,panResponseParentMs,cancellation}));
}catch(e){report={...report,status:'failed',error:{message:e.message,stack:e.stack},errors,requests};write('failure.json',report);throw e;
}finally{
 await browser?.close();child.kill('SIGTERM');await new Promise(resolve=>{if(child.exitCode!==null)resolve();else child.once('exit',resolve);});
 write('fixture.log',logs);report.workerAudit=logs.split('\n').filter(l=>l.startsWith('{"audit"')).map(l=>JSON.parse(l));
 write('result.json',report);
}
