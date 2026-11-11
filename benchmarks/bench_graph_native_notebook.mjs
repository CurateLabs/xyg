import assert from 'node:assert/strict';
// Actual Jupyter/kernel/anywidget bridge. Use CodSpeed for timing runs.
// Paint, keyboard, queued UUID selection and early cancellation; not convergence.
import {spawn,spawnSync} from 'node:child_process';
import {createHash} from 'node:crypto';
import {mkdtemp,writeFile,cp,mkdir,readFile} from 'node:fs/promises';
import {join} from 'node:path';
import {fileURLToPath} from 'node:url';
import {createServer} from 'node:net';
import {chromium} from 'playwright';
import {namedIdleKernel} from '../scripts/graph_notebook_kernel_witness.mjs';
const args=process.argv.slice(2);
if(args.length!==0&&(args.length!==2||args[0]!=='--frontend'||!['jupyterlab','notebook7'].includes(args[1])))throw Error('usage: bench_graph_native_notebook.mjs [--frontend jupyterlab|notebook7]');
const frontendKind=args[1]??'jupyterlab';
const root=fileURLToPath(new URL('../',import.meta.url)),temp=await mkdtemp(join(root,'target/xyg-graph-notebook-'));
const scale=Number(process.env.XYG_NOTEBOOK_SCALE??100000);assert.ok([1000,10000,100000].includes(scale));
const reportPath=process.env.XYG_SCALE_REPORT??join(temp,'report.json');
await cp(join(root,'tests/notebook_graph_native_scale.ipynb'),join(temp,'graph.ipynb'));
const allocator=createServer();await new Promise(r=>allocator.listen(0,'127.0.0.1',r));const port=allocator.address().port;await new Promise(r=>allocator.close(r));
await mkdir(join(temp,'runtime'));await mkdir(join(temp,'config'));await mkdir(join(temp,'data'));
const executable=process.env.XYG_GRAPH_JUPYTER??join(root,frontendKind==='notebook7'?'.venv/bin/jupyter-notebook':'.venv/bin/jupyter-lab');
const server=spawn(executable,['--no-browser','--ServerApp.ip=127.0.0.1',`--ServerApp.port=${port}`,`--ServerApp.root_dir=${temp}`,'--IdentityProvider.token=','--ServerApp.password='],{cwd:root,env:{...process.env,XYG_NATIVE_LIB:join(root,"target/release/libxyg_core.so"),JUPYTER_RUNTIME_DIR:join(temp,'runtime'),JUPYTER_CONFIG_DIR:join(temp,'config'),JUPYTER_DATA_DIR:join(temp,'data'),PYTHONPATH:`${root}/python:${root}/tests`,XYG_GRAPH_SOURCE_ROOT:root,XYG_NOTEBOOK_SCALE:String(scale)},stdio:['ignore','pipe','pipe']});
let logs='';server.stdout.on('data',b=>logs+=b);server.stderr.on('data',b=>logs+=b);
let browser,page,runCell,output,cleanupAttempted=false; const errors=[],pageErrors=[];
try{
 const origin=`http://127.0.0.1:${port}`;
 for(let i=0;i<100;i++){try{const r=await fetch(origin+'/api/status');if(r.ok)break;}catch{}await new Promise(r=>setTimeout(r,100));}
 browser=await chromium.launch({...(process.env.XYG_CHROMIUM?{executablePath:process.env.XYG_CHROMIUM}:{}),args:['--use-gl=swiftshader','--enable-unsafe-swiftshader','--ignore-gpu-blocklist']});
 page=await browser.newPage({viewport:{width:1200,height:900}});const external=[];
 await page.route('**/*',route=>{const u=new URL(route.request().url());if(!['http:','https:'].includes(u.protocol)||u.origin===origin)return route.continue();external.push(u.href);return route.abort();});
 page.on('pageerror',e=>pageErrors.push(e.message));page.on('console',m=>{if(m.type()==='error'||m.type()==='warning')errors.push(m.text());});
 await page.addInitScript(()=>{
  globalThis.__graphFrames=[]; globalThis.__graphActions=[]; globalThis.__graphEvents=[];
  for(const kind of ['click','hover','view_change','select'])document.addEventListener('xy:'+kind,event=>{
    const rect=event.target.getBoundingClientRect(),px=event.detail.cursor?.px;
    globalThis.__graphEvents.push({kind,detail:event.detail,client:px?[rect.left+px[0],rect.top+px[1]]:null,step:event.target.closest('[data-graph-steps]')?.dataset.graphSteps});
  });
  for(const kind of ['keydown','pointerdown','wheel'])document.addEventListener(kind,event=>{
    if(event.target instanceof HTMLCanvasElement&&event.isTrusted)globalThis.__graphActions.push({kind,key:event.key,step:event.target.closest('[data-graph-steps]')?.dataset.graphSteps});
  },true);
  const lastStepByInstance=new Map();
  new MutationObserver(records=>{for(const record of records){
   const el=record.target;if(!(el instanceof HTMLElement)||!el.hasAttribute('data-graph-steps'))continue;
   const canvas=el.querySelector('canvas[role="img"]'),step=el.getAttribute('data-graph-steps');
   const instance=el.dataset.graphInstance;
   if(lastStepByInstance.get(instance)===step)continue;lastStepByInstance.set(instance,step);
   globalThis.__graphFrames.push({instance,step,time:performance.now(),width:canvas?.width,height:canvas?.height});
  }}).observe(document,{subtree:true,attributes:true,attributeFilter:['data-graph-steps']});
 });
 await page.goto(origin+(frontendKind==='notebook7'?'/notebooks/graph.ipynb':'/lab/tree/graph.ipynb'));
 const frontend=await page.evaluate(kind=>{
  const config=JSON.parse(document.getElementById('jupyter-config-data')?.textContent||'{}');
  return {kind,appName:config.appName,version:config.appVersion,namespace:config.appNamespace,
   staticUrl:config.fullStaticUrl,route:location.pathname,
   staticRequests:[...new Set(performance.getEntriesByType('resource').map(r=>new URL(r.name).pathname).filter(path=>path.startsWith('/static/')))].sort()};
 },frontendKind);
 const expectedApp=frontendKind==='notebook7'?['Jupyter Notebook','notebook','7','/static/notebook']:['JupyterLab','lab','4','/static/lab'];
 if(frontend.appName!==expectedApp[0]||frontend.namespace!==expectedApp[1]||frontend.version?.split('.')[0]!==expectedApp[2]||frontend.staticUrl!==expectedApp[3]||!frontend.staticRequests.some(path=>path.startsWith(expectedApp[3]+'/')))throw Error('wrong actual notebook frontend: '+JSON.stringify(frontend));
 await page.locator('.jp-Notebook .jp-Cell').first().waitFor({timeout:45000});
 const select=page.getByRole('button',{name:'Select'});if(await select.count())await select.click();
 // Notebook7's initial execution indicator can say idle while No Kernel is
 // selected. Require both a named kernel and the idle execution indicator.
 frontend.kernel=await namedIdleKernel(page,frontendKind);
 await page.locator('.jp-Notebook .jp-Cell').first().locator('.cm-content').click();await page.keyboard.press('Shift+Enter');
 runCell=async index=>{const c=page.locator('.jp-Notebook .jp-Cell').nth(index);await c.locator('.cm-content').click();await page.keyboard.press('Shift+Enter');};
 output=async(index,prefix)=>{const el=page.locator('.jp-Notebook .jp-Cell').nth(index).locator('.jp-OutputArea');await el.getByText(prefix,{exact:false}).waitFor({timeout:20000});const text=await el.innerText();if(text.includes('Traceback'))throw Error(text);return JSON.parse(text.split(prefix)[1].trim());};
 const setup=await output(0,'XYG scale setup');
 assert.equal(setup.nodes,scale);assert.equal(setup.edges,2*scale);
 assert.notEqual(setup.primaryInstance,setup.peerInstance);
 assert.equal(setup.nativeSha256,createHash('sha256').update(await readFile(join(root,'target/release/libxyg_core.so'))).digest('hex'));
 assert.equal(setup.clientSha256,createHash('sha256').update(await readFile(join(root,'python/xyg/static/index.js'))).digest('hex'));
 const surface=page.locator(`[data-graph-instance="${setup.primaryInstance}"]`);
 await runCell(1);const responsive=await output(1,'XYG scale responsive');
 const canvas=surface.locator('canvas[role="img"]');await canvas.waitFor({timeout:45000});await canvas.scrollIntoViewIfNeeded();
 assert.equal(await surface.getAttribute('data-graph-instance'),setup.primaryInstance);
 const runtime=await canvas.evaluate(canvas=>{const view=globalThis[Symbol.for('reflex-dev.xy.shared-webgl-host.v2')].get(document).dashboardResourceSnapshot().clients.find(v=>v.canvas===canvas);return {themeSignature:typeof view._computedThemeSignature,onPainted:typeof view.comm?.onPainted,segmentPrograms:[...view._progCache.keys()].filter(k=>k.startsWith("segment"))};});
 assert.equal(runtime.themeSignature,'function');assert.equal(runtime.onPainted,'function');assert.ok(runtime.segmentPrograms.includes('segment-cartesian'));
 await canvas.focus();await page.keyboard.press('Home');await page.keyboard.press('Enter');
 await page.waitForFunction(()=>globalThis.__graphEvents.some(e=>e.kind==='click'),null,{timeout:10000});
 await runCell(2);const first=await output(2,'XYG scale report');
 await runCell(3);await page.locator('.jp-Notebook .jp-Cell').nth(3).locator('.jp-OutputArea').getByText('XYG scale selected UUID',{exact:false}).waitFor({timeout:10000});
 await runCell(4);const selected=await output(4,'XYG scale report');
 // Cell completion only queues public selection when a publication is pending.
 // Require the actual accepted client selection before inspecting its mask.
 await page.waitForFunction(instance=>{const host=globalThis[Symbol.for('reflex-dev.xy.shared-webgl-host.v2')]?.get(document);const view=host?.dashboardResourceSnapshot().clients.find(v=>v.canvas===document.querySelector(`[data-graph-instance="${instance}"] canvas[role="img"]`));return view?.root.xy.state().selection?.rows===true&&view.gpuTraces.find(g=>g.trace.id===view._graphs[0].node_trace)?.selActive===true;},setup.primaryInstance,{timeout:10000});

 await canvas.scrollIntoViewIfNeeded();await canvas.screenshot({path:join(temp,'paint.png')});
 const inspectCanvas=canvas=>{const owner=globalThis[Symbol.for('reflex-dev.xy.shared-webgl-host.v2')].get(document).dashboardResourceSnapshot().clients.find(v=>v.canvas===canvas);return {nodeRows:owner.gpuTraces.find(g=>g.trace.id===owner._graphs[0].node_trace).n,edgeRows:owner.gpuTraces.find(g=>g.trace.id===owner._graphs[0].edge_trace).n,state:owner.root.xy.state(),ranges:owner._durableState().ranges,masks:owner.gpuTraces.map(g=>{const gl=owner.gl,previous=gl.getParameter(gl.ARRAY_BUFFER_BINDING),data=new Float32Array(g.n);try{if(g.selBuf){gl.bindBuffer(gl.ARRAY_BUFFER,g.selBuf);gl.getBufferSubData(gl.ARRAY_BUFFER,0,data);}return {trace:g.trace.id,active:g.selActive===true,rows:Array.from(data).flatMap((v,i)=>v===1?[i]:[]),binary:Array.from(data).every(v=>v===0||v===1)};}finally{gl.bindBuffer(gl.ARRAY_BUFFER,previous);}}),nodeTrace:owner._graphs[0].node_trace,edgeTrace:owner._graphs[0].edge_trace};};
 const view=await canvas.evaluate(inspectCanvas);
 const peerView=await page.locator(`[data-graph-instance="${setup.peerInstance}"]`).locator('canvas[role="img"]').evaluate(inspectCanvas);
 const before=await page.evaluate(()=>({frames:globalThis.__graphFrames,events:globalThis.__graphEvents,actions:globalThis.__graphActions,timeOrigin:performance.timeOrigin}));
 await runCell(4);const accepted=await output(4,'XYG scale report');

 cleanupAttempted=true;await runCell(5);const cleanup=await output(5,'XYG scale cleanup');
 const result={scope:'Bounded native ordinary notebook paint, trusted keyboard, queued UUID selection and cancellation; no convergence or whole-issue qualification',runtime,frontend,setup,responsive,first,selected,accepted,view,peerView,before,cleanup,errors,pageErrors,external,artifactDir:temp,browser:browser.version()};
 await writeFile(reportPath,JSON.stringify(result,null,2)+'\n');console.log(JSON.stringify({report:reportPath,setup,responsive,primary:first.primary,clicks:first.clicks.length}));
 if(pageErrors.length||external.length)throw Error('page errors or unapproved traffic');
 if(!responsive.primaryLive)throw Error('concurrent cell did not execute during primary layout');
 if(first.primary.identityError!==null||first.clicks.some(c=>c.graphforge_error))throw Error('native notebook identity admission refused');
 assert.ok(first.clicks.length>0);assert.deepEqual(first.clicks[0].graphforge,[first.expected]);
 assert.ok(view.masks.every(m=>m.binary));
 assert.deepEqual(view.masks.find(m=>m.trace===view.nodeTrace).rows,[0]);
 assert.deepEqual(view.masks.find(m=>m.trace===view.edgeTrace).rows,[]);
 assert.equal(selected.primary.identityError,null);assert.equal(selected.primary.failed,false);
 assert.ok(peerView.masks.every(m=>!m.active&&m.rows.length===0),"peer selection remains empty");
 assert.equal(peerView.nodeRows,setup.peerNodes);assert.equal(peerView.edgeRows,setup.peerEdges);
 assert.equal(view.nodeRows,setup.nodes);assert.equal(view.edgeRows,setup.edges);
 assert.equal(cleanup.identityOwnersClosed,true);assert.equal(cleanup.threadsStopped,true);assert.equal(accepted.primary.failed,false);assert.equal(accepted.peer.failed,false);
 for(const owner of [accepted.primary,accepted.peer])assert.ok(owner.running||owner.step===setup.iterations,'unfinished layout must remain live');
 assert.deepEqual(accepted.primary.selection,{rows:true});
} catch(error){let cleanupFailure=null;if(page&&runCell&&output&&!cleanupAttempted){cleanupAttempted=true;try{await runCell(5);await output(5,'XYG scale cleanup');}catch(e){cleanupFailure=String(e.stack||e);}}await writeFile(reportPath+'.failure.json',JSON.stringify({error:error.stack,cleanupFailure,logs,errors,pageErrors,body:await page?.locator('body').innerText().catch(()=>''),events:await page?.evaluate(()=>globalThis.__graphEvents).catch(()=>[])},null,2));throw error;}
finally{try{await browser?.close();}finally{if(server.exitCode===null&&server.signalCode===null){const exited=new Promise(resolve=>server.once('exit',resolve));server.kill('SIGTERM');let timer;await Promise.race([exited,new Promise(resolve=>{timer=setTimeout(resolve,10000);})]);clearTimeout(timer);if(server.exitCode===null&&server.signalCode===null){server.kill('SIGKILL');await exited;}}}}
