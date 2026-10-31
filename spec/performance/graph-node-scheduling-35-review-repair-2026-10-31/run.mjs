// Local native/painter functional render proof; no shipping WASM qualification.
// Run from repository root; see README.md for the exact environment command.
import assert from 'node:assert/strict';
import { spawn, execFileSync } from 'node:child_process';
import { readFileSync, writeFileSync, mkdirSync, existsSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { performance } from 'node:perf_hooks';
import { chromium } from 'playwright';
const root = new URL('../../../', import.meta.url);
const outputName = process.env.XYG_GRAPH_NODE_RECEIPT_OUTPUT ?? `target/task-tmp/graph-node-scheduling-35-review-repair-${Date.now()}/`;
const out = new URL(outputName.endsWith('/') ? outputName : `${outputName}/`, root);
mkdirSync(out, { recursive: true });
assert.equal(existsSync(new URL('result.json', out)), false, 'receipt already exists; choose a new output directory');
const chrome = process.env.XYG_CHROMIUM;
assert.ok(chrome, 'XYG_CHROMIUM must name the local Chromium executable');
const sha256 = path => createHash('sha256').update(readFileSync(new URL(path, root))).digest('hex');
const started = performance.now();
const child = spawn(process.execPath, ['examples/vanilla-ts/graphforge-live.mjs'], { cwd: root, env: process.env, stdio: ['ignore', 'pipe', 'pipe'] });
let logs = '';
child.stdout.on('data', b => { logs += b; }); child.stderr.on('data', b => { logs += b; });
let browser;
try {
 const url = await new Promise((resolve,reject) => {
  const timeout=setTimeout(()=>reject(Error('fixture startup timed out')),15000);
  child.stdout.on('data',()=>{const hit=logs.match(/XYG_GRAPHFORGE_LIVE_URL=(\S+)/);if(hit){clearTimeout(timeout);resolve(hit[1]);}});
  child.once('exit',code=>{clearTimeout(timeout);reject(Error(`fixture exited ${code}: ${logs}`));});
 });
 const nodeColdStartupMs = performance.now()-started;
 const browserStarted=performance.now();
 browser=await chromium.launch({executablePath:chrome,headless:true,args:['--no-sandbox','--use-gl=angle','--use-angle=swiftshader','--enable-unsafe-swiftshader']});
 const browserColdStartupMs=performance.now()-browserStarted;
 const context=await browser.newContext({viewport:{width:900,height:650}});
 const page=await context.newPage(); const errors=[], requests=[];
 page.on('pageerror',e=>errors.push(e.message));
 page.on('request',r=>requests.push(r.url()));
 await page.goto(url,{waitUntil:'networkidle',timeout:15000});
 const navigationMs=await page.evaluate(()=>performance.now());
 await page.evaluate(()=>{ window.beginGraph().catch(e=>proof.errors.push(String(e))); });
 await page.waitForFunction(()=>proof.checkpoints.length>=1,{},{timeout:15000});
 const initial=await page.evaluate(()=>proof.checkpoints[0]);
 assert.equal(initial.phase,'initial');assert.ok(initial.coloredPixels>0,JSON.stringify(initial));
 async function retainPayload(label, checkpoint) {
  const current=await page.evaluate(()=>proof.current);
  assert.equal(current.step,checkpoint.step);assert.equal(current.jobId,checkpoint.jobId);
  const buffer=Buffer.from(await (await fetch(`${url}/buffer`)).arrayBuffer());
  assert.equal(buffer.byteLength,checkpoint.bufferBytes);
  writeFileSync(new URL(`${label}-spec.json`,out),JSON.stringify(current.spec,null,2)+'\n');
  writeFileSync(new URL(`${label}-buffer.bin`,out),buffer);
 }
 await retainPayload('initial',initial);
 await page.screenshot({path:new URL('initial.png',out).pathname});
 async function interact(label) {
  const location=await page.evaluate(()=>{
   const v=graphView, wanted=proof.current.nodeTrace;
   // Probe the actual GPU pick pass to locate a rendered node. The subsequent
   // Playwright click is a real pointer event through the consumer's xy:click.
   for(let y=16;y<v.plot.h;y+=4) for(let x=16;x<v.plot.w;x+=4) {
    const hit=v._pickAt(x,y); if(hit?.trace===wanted) {
     const r=v.canvas.getBoundingClientRect();return {x:r.x+x,y:r.y+y,hit:{trace:hit.trace,index:hit.index}};
    }
   }
   throw Error('no GPU-picked node found');
  });
  const began=performance.now(); const count=await page.evaluate(()=>proof.clicks.length);
  await page.mouse.click(location.x,location.y);
  await page.waitForFunction(n=>proof.clicks.length>n,count,{timeout:5000});
  const click=await page.evaluate(()=>proof.clicks.at(-1));
  const pointerToIdentityMs=performance.now()-began;
  assert.ok(click.identity.uuid,'real click must resolve a source UUID');
  assert.equal(click.detail.trace,location.hit.trace,'pointer click must agree with the GPU-probed trace');
  assert.equal(click.detail.index,location.hit.index,'pointer click must agree with the GPU-probed render row');
  assert.equal(click.identity.uuid,click.detail.row.id,'host UUID must equal the actual clicked tooltip UUID');
  const before=await page.evaluate(()=>({...graphView.view}));
  const box=await page.locator('#chart canvas').first().boundingBox();
  const panStarted=performance.now();
  await page.mouse.move(box.x+box.width*0.5,box.y+box.height*0.6);
  await page.mouse.down();await page.mouse.move(box.x+box.width*0.5+35,box.y+box.height*0.6+20,{steps:5});await page.mouse.up();
  await page.waitForFunction(old=>graphView.view.x0!==old.x0 || graphView.view.y0!==old.y0,before,{timeout:5000});
  const after=await page.evaluate(()=>({...graphView.view}));
  return {label,probedHit:location.hit,click,pointerToIdentityMs,panBefore:before,panAfter:after,panResponseMs:performance.now()-panStarted,totalJourneyMs:performance.now()-began};
 }
 const initialInteraction=await interact('initial');
 await page.evaluate(()=>acceptGraph());
 await page.waitForFunction(()=>proof.checkpoints.some(p=>p.phase==='complete'),{},{timeout:15000});
 const final=await page.evaluate(()=>proof.checkpoints.at(-1));
 assert.ok(final.step>initial.step && final.coloredPixels>0);assert.equal(final.jobId,initial.jobId);assert.equal(final.revision,initial.revision);
 await retainPayload('final',final);
 await page.screenshot({path:new URL('final.png',out).pathname});
 const finalInteraction=await interact('complete');
 await page.evaluate(()=>acceptGraph());await page.waitForFunction(()=>proof.done,{},{timeout:5000});
 const proof=await page.evaluate(()=>window.proof);
 assert.deepEqual(proof.errors,[]);assert.deepEqual(errors,[]);
 assert.ok(requests.every(r=>new URL(r).origin===url),'only local assets/transport');
 const evidence=await (await fetch(`${url}/evidence`)).json();
 const checkpoints=evidence.events.filter(e=>e.type==='checkpoint');
 assert.notEqual(checkpoints[0].positionSha256,checkpoints.at(-1).positionSha256,'later paint uses changed source positions');
 await page.evaluate(()=>disposeGraph());
 assert.equal(await page.locator('#chart canvas').count(),0);
 const sourcePaths=['packages/xy-node/src/graphforge.js','packages/xy-node/src/index.js','packages/xy-node/src/vscode.js','packages/xy-node/src/graph.js','packages/xy-node/src/figure.js','packages/xy-node/src/native.js','packages/xy-node/src/_abi_generated.js','packages/xy-node/test/graphforge-layout.test.mjs','tests/fixtures/graphforge/results/manifest.json',`tests/fixtures/graphforge/results/${JSON.parse(readFileSync(new URL('tests/fixtures/graphforge/results/manifest.json',root))).bases.cyclic.nodes}.arrow`,`tests/fixtures/graphforge/results/${JSON.parse(readFileSync(new URL('tests/fixtures/graphforge/results/manifest.json',root))).bases.cyclic.edges}.arrow`];
 sourcePaths.push('packages/xy-node/src/graphforge_layout.js','packages/xy-node/src/graphforge_layout_worker.js',
  'packages/xy-node/src/force_scheduler.js','packages/xy-node/src/abi.js',
  'scripts/graphforge_webview_smoke.mjs','scripts/node_release_smoke.mjs','benchmarks/bench_graphforge_compose.mjs');
 const sourceHashes=Object.fromEntries(sourcePaths.map(p=>[p,sha256(p)]));
 const report={scope:'bounded local native Node/painter functional proof; full view replacement, no S5 retained controller, no scale/competitor/release gate',
  sourceBase:execFileSync('git',['rev-parse','HEAD'],{cwd:root,encoding:'utf8'}).trim(),
  environment:{node:process.version,nodeExecutable:process.execPath,chromium:await browser.version(),chromiumExecutable:chrome,
   platform:process.platform,arch:process.arch,os:execFileSync('uname',['-a'],{encoding:'utf8'}).trim(),
   nativeAbi:(await import('../../../packages/xy-node/src/abi.js')).abiVersion(),rust:execFileSync('/home/ubuntu/.cargo/bin/rustc',['--version'],{cwd:root,encoding:'utf8'}).trim(),
   graphics:'ANGLE SwiftShader; software rendering; shared local environment'},
  presentationCadenceMs:checkpoints.slice(1).map((e,i)=>e.ms-checkpoints[i].ms),
  cadenceMeaning:'Consumer ACK deliberately holds frames; presentation cadence is not native chunk cadence. Historical ladder measures scheduler-only cadence.',
  executables:{node:sha256(process.execPath),chromium:sha256(chrome),rustupShim:sha256('/home/ubuntu/.cargo/bin/rustc')},
  retainedObjects:'Initial/final raw painter buffers and JSON specs, screenshots, exact pick details/identities/probed hits, checkpoint position digests and byte counts; full source position arrays and intermediate payloads are not retained.',
  retainedPayloadHashes:Object.fromEntries(['initial-spec.json','initial-buffer.bin','final-spec.json','final-buffer.bin'].map(p=>[p,createHash('sha256').update(readFileSync(new URL(p,out))).digest('hex')])),
  sourceHashes,firstPaintedMs:initial.paintedMs,firstIdentityAcceptedMs:proof.clicks[0].atMs,
  nodeColdStartupMs,browserColdStartupMs,navigationMs,proof,initialInteraction,finalInteraction,evidence,errors,requests,
  assets:{native:sha256('target/release/libxyg_core.so'),client:sha256('packages/xy-client/dist/standalone.js'),clientEsm:sha256('packages/xy-client/dist/index.js'),
   fixture:sha256('examples/vanilla-ts/graphforge-live.mjs'),runner:sha256('spec/performance/graph-node-scheduling-35-review-repair-2026-10-31/run.mjs'),
   controller:sha256('packages/xy-node/src/graphforge_layout.js'),bridge:sha256('packages/xy-node/src/graphforge_layout_worker.js'),scheduler:sha256('packages/xy-node/src/force_scheduler.js'),
   initial:createHash('sha256').update(readFileSync(new URL('initial.png',out))).digest('hex'),final:createHash('sha256').update(readFileSync(new URL('final.png',out))).digest('hex')}};
 writeFileSync(new URL('result.json',out),JSON.stringify(report,null,2)+'\n');
 console.log(JSON.stringify({passed:true,receipt:out.pathname,initial,final,nodeColdStartupMs,browserColdStartupMs,initialInteraction,finalInteraction,evidence}));
} finally {
 await browser?.close();
 child.kill('SIGTERM');await new Promise(resolve=>{if(child.exitCode!==null)resolve();else child.once('exit',resolve);});
 writeFileSync(new URL('fixture.log',out),logs);
}
