// Deliberately held inspection, isolated from the normal unheld run/cadence.
// Reuses the same fixture without changing its automatic browser ACK policy:
// Playwright intercepts the HTTP ACK only for this diagnostic.
import assert from 'node:assert/strict';
import { spawn, execFileSync } from 'node:child_process';
import { mkdirSync, existsSync, writeFileSync, readFileSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { performance } from 'node:perf_hooks';
import { chromium } from 'playwright';
import { validateClick } from './protocol.mjs';
const root=new URL('../../../',import.meta.url);
const output=process.env.XYG_NODE_INSPECTION_OUTPUT??`target/task-tmp/node-first-paint-1k-held-${Date.now()}/`;
const out=new URL(output.endsWith('/')?output:output+'/',root);
assert.equal(existsSync(out),false);mkdirSync(out,{recursive:true});
const write=(name,v)=>writeFileSync(new URL(name,out),Buffer.isBuffer(v)?v:JSON.stringify(v,null,2)+'\n');
const sha=b=>createHash('sha256').update(b).digest('hex');
const child=spawn(process.execPath,['--import',new URL('worker-audit.mjs',import.meta.url).pathname,new URL('fixture.mjs',import.meta.url).pathname],{cwd:root,env:process.env,stdio:['ignore','pipe','pipe']});
let logs='',browser,report={status:'started'};child.stdout.on('data',b=>logs+=b);child.stderr.on('data',b=>logs+=b);
try{
 const url=await new Promise((resolve,reject)=>{const timer=setTimeout(()=>reject(Error('startup timeout')),15000);
 child.stdout.on('data',()=>{const hit=logs.match(/XYG_GRAPHFORGE_LIVE_URL=(\S+)/);if(hit){clearTimeout(timer);resolve(hit[1]);}});
 child.once('exit',code=>{clearTimeout(timer);reject(Error(`fixture exit ${code}: ${logs}`));});});
 browser=await chromium.launch({executablePath:process.env.XYG_CHROMIUM,headless:true,args:['--no-sandbox','--use-gl=angle','--use-angle=swiftshader','--enable-unsafe-swiftshader']});
 const page=await browser.newPage({viewport:{width:900,height:650}}),errors=[];
 page.on('pageerror',e=>errors.push(e.message));
 const pending=[];
 await page.route('**/accept',route=>new Promise((resolve,reject)=>pending.push({route,release:async()=>{try{await route.continue();resolve();}catch(e){reject(e);}}})));
 await page.goto(url,{waitUntil:'networkidle'});
 await page.evaluate(()=>{beginGraph().catch(e=>proof.errors.push(String(e)));});
 await page.waitForFunction(()=>proof.frames.length>0||proof.errors.length>0,null,{timeout:30000});
 assert.deepEqual(await page.evaluate(()=>proof.errors),[]);
 const initial=await page.evaluate(()=>proof.frames[0]);assert.equal(initial.phase,'initial');
 assert.equal(pending.length,1,'initial HTTP ACK must actually be held');
 const beforeBadAck=await(await fetch(url+'/evidence')).json();
 const badAck={jobId:initial.jobId,revision:initial.revision,step:initial.step+1};
 const rejected=(await fetch(url+'/accept',{method:'POST',body:JSON.stringify(badAck)})).status;
 assert.equal(rejected,409);
 async function interact(){
  const location=await page.evaluate(()=>findNode()),began=performance.now();
  await page.mouse.click(location.x,location.y);await page.waitForFunction(()=>proof.clicks.length>0);
  const click=await page.evaluate(()=>proof.clicks.at(-1));validateClick(location,click);
  const pointerToUuidParentMs=performance.now()-began;
  const before=await page.evaluate(()=>({...graphView.view})),box=await page.locator('#chart canvas').first().boundingBox();
  const panStart=performance.now();await page.mouse.move(box.x+box.width*.5,box.y+box.height*.6);await page.mouse.down();
  await page.mouse.move(box.x+box.width*.5+35,box.y+box.height*.6+20,{steps:5});await page.mouse.up();
  await page.waitForFunction(old=>graphView.view.x0!==old.x0||graphView.view.y0!==old.y0,before);
  return{location,click,pointerToUuidParentMs,before,after:await page.evaluate(()=>({...graphView.view})),panResponseParentMs:performance.now()-panStart};
 }
 const interaction=await interact();
 await page.screenshot({path:new URL('held-initial-panned.png',out).pathname});
 const stillHeld=await(await fetch(url+'/evidence')).json();
 assert.equal(stillHeld.events.filter(e=>e.type==='checkpoint').length,1,'bad ACK must not release the initial presentation');
 assert.equal(stillHeld.events.filter(e=>e.type==='accepted').length,0);
 await pending.shift().release();
 await page.waitForFunction(()=>proof.frames.some(f=>f.phase==='complete')||proof.errors.length>0,null,{timeout:30000});
 const final=await page.evaluate(()=>proof.frames.at(-1));
 assert.equal(final.phase,'complete');assert.deepEqual(final.previousView,interaction.after);
 assert.notDeepEqual(final.view,interaction.after,'replacement discarded panned viewport');
 const snapshots=await(await fetch(url+'/snapshot')).json();
 const finalSpec=snapshots.at(-1).spec,range=finalSpec.view.ranges;
 assert.deepEqual([final.view.x0,final.view.x1],range.x);assert.deepEqual([final.view.y0,final.view.y1],range.y);
 assert.equal(pending.length,1);await page.screenshot({path:new URL('held-final-reset.png',out).pathname});
 await pending.shift().release();await page.waitForFunction(()=>proof.done);
 for(const p of snapshots){
  const prefix='step-'+p.step;write(prefix+'-spec.json',p.spec);
  write(prefix+'-buffer.bin',Buffer.from(await(await fetch(url+'/buffer/'+p.step)).arrayBuffer()));
  write(prefix+'-x.f64',Buffer.from(p.xBase64,'base64'));write(prefix+'-y.f64',Buffer.from(p.yBase64,'base64'));
 }
 write('positions-uuid.json',snapshots[0].positionsUuid);
 const proof=await page.evaluate(()=>{const {initialPng,finalPng,...p}=proof;return p;});
 await page.evaluate(()=>disposeGraph());await fetch(url+'/dispose',{method:'POST'});
 assert.deepEqual(errors,[]);assert.deepEqual(proof.errors,[]);
 report={schema:'node-rendered-first-paint-1k-held/1',status:'passed',scope:'Deliberately held ACK inspection and mutation; NONE of these frame or pointer/pan intervals qualifies normal presentation cadence or unheld initial interaction.',
 sourceBase:execFileSync('git',['rev-parse','HEAD'],{cwd:root,encoding:'utf8'}).trim(),
 sourceHashes:Object.fromEntries(['inspection.mjs','fixture.mjs','protocol.mjs','worker-audit.mjs'].map(p=>[p,sha(readFileSync(new URL(p,import.meta.url)))])),
 environment:{node:process.version,chromium:await browser.version(),chromiumExecutable:process.env.XYG_CHROMIUM},
 artifacts:{native:sha(readFileSync(process.env.XYG_NATIVE_LIB)),client:sha(readFileSync(new URL('packages/xy-client/dist/standalone.js',root)))},
 ackMode:'Playwright HTTP interception holds each automatic /accept request until inspection completes.',
 badAck, rejected,checkpointsBeforeBadAck:beforeBadAck.events.filter(e=>e.type==='checkpoint').length,
 checkpointsAfterInspectionBeforeRelease:stillHeld.events.filter(e=>e.type==='checkpoint').length,
 initial,final,interaction,proof,finalSpecRanges:range,evidence:await(await fetch(url+'/evidence')).json(),errors};
 console.log(JSON.stringify({status:report.status,scope:report.scope,initialStep:initial.step,finalStep:final.step,badAckStatus:rejected,interaction,resetView:final.view}));
}catch(e){report={...report,status:'failed',error:{message:e.message,stack:e.stack}};throw e;
}finally{await browser?.close();child.kill('SIGTERM');await new Promise(r=>{if(child.exitCode!==null)r();else child.once('exit',r);});
 writeFileSync(new URL('fixture.log',out),logs);report.workerAudit=logs.split('\n').filter(l=>l.startsWith('{"audit"')).map(l=>JSON.parse(l));write('result.json',report);}
