#!/usr/bin/env node
// Actual JupyterLab/Notebook7/kernel/anywidget bridge. No external data APIs.
import {spawn,spawnSync} from 'node:child_process';
import {createHash} from 'node:crypto';
import {mkdtemp,writeFile,cp,mkdir,readFile} from 'node:fs/promises';
import {join} from 'node:path';
import {fileURLToPath} from 'node:url';
import {createServer} from 'node:net';
import {chromium} from 'playwright';
import {namedIdleKernel} from './graph_notebook_kernel_witness.mjs';
const args=process.argv.slice(2);
if(args.length!==0&&(args.length!==2||args[0]!=='--frontend'||!['jupyterlab','notebook7'].includes(args[1])))throw Error('usage: graph_notebook_progressive_smoke.mjs [--frontend jupyterlab|notebook7]');
const frontendKind=args[1]??'jupyterlab';
const root=fileURLToPath(new URL('../',import.meta.url)),temp=await mkdtemp(join(root,'target/xyg-graph-notebook-'));
await cp(join(root,'tests/notebook_graph_progressive.ipynb'),join(temp,'graph.ipynb'));
const allocator=createServer();await new Promise(r=>allocator.listen(0,'127.0.0.1',r));const port=allocator.address().port;await new Promise(r=>allocator.close(r));
await mkdir(join(temp,'runtime'));await mkdir(join(temp,'config'));await mkdir(join(temp,'data'));
const executable=process.env.XYG_GRAPH_JUPYTER??join(root,frontendKind==='notebook7'?'.venv/bin/jupyter-notebook':'.venv/bin/jupyter-lab');
const server=spawn(executable,['--no-browser','--ServerApp.ip=127.0.0.1',`--ServerApp.port=${port}`,`--ServerApp.root_dir=${temp}`,'--IdentityProvider.token=','--ServerApp.password='],{cwd:root,env:{...process.env,XYG_NATIVE_LIB:join(root,"target/release/libxyg_core.so"),JUPYTER_RUNTIME_DIR:join(temp,'runtime'),JUPYTER_CONFIG_DIR:join(temp,'config'),JUPYTER_DATA_DIR:join(temp,'data'),PYTHONPATH:`${root}/python:${root}/tests`},stdio:['ignore','pipe','pipe']});
let logs='';server.stdout.on('data',b=>logs+=b);server.stderr.on('data',b=>logs+=b);
let browser,page; const errors=[],pageErrors=[];
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
  let primarySurface=null;
  new MutationObserver(records=>{for(const record of records){
   const el=record.target;if(!(el instanceof HTMLElement)||!el.hasAttribute('data-graph-steps'))continue;
   const canvas=el.querySelector('canvas[role="img"]'),step=el.getAttribute('data-graph-steps');
   primarySurface??=document.querySelector('[data-graph-steps]');
   if(el!==primarySurface)continue;
   if(globalThis.__graphFrames.at(-1)?.step===step)continue;
   globalThis.__graphFrames.push({step,time:performance.now(),width:canvas?.width,height:canvas?.height});
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
 const surface=page.locator('.jp-OutputArea [data-graph-steps]').first();
 await surface.waitFor({timeout:45000});
 const firstSteps=await surface.getAttribute('data-graph-steps');
 const canvas=surface.locator('canvas[role="img"]');
 const picture=async(name)=>{
   const path=join(temp,name+'.png'),data=await canvas.screenshot({path});
   const probe=spawnSync(join(root,'.venv/bin/python'),['-c','from PIL import Image; import sys,json; im=Image.open(sys.argv[1]).convert("RGB"); print(json.dumps({"colors":len(im.getcolors(im.width*im.height)),"width":im.width,"height":im.height}))',path],{encoding:'utf8'});
   if(probe.status!==0)throw Error(probe.stderr);
   const result={...JSON.parse(probe.stdout),sha256:createHash('sha256').update(data).digest('hex'),step:await surface.getAttribute('data-graph-steps')};
   if(result.colors<=2)throw Error('empty graph picture');return result;
 };
 const initialPicture=await picture('initial');
 if(Number(initialPicture.step)>=300)throw Error('initial picture was terminal');
 await canvas.focus(); await page.keyboard.press('Home'); await page.keyboard.press('Enter');
 await page.waitForFunction(()=>globalThis.__graphEvents.some(e=>e.kind==='hover'&&e.detail.exact),{},{timeout:5000});
 const point=await page.evaluate(()=>globalThis.__graphEvents.findLast(e=>e.kind==='hover'&&e.detail.exact)?.client);
 if(!point)throw Error('missing exact readout coordinates');await page.mouse.click(point[0],point[1]);
 // Wheel/pan and keyboard activation are trusted input against the real view.
 const box=await canvas.boundingBox(); await page.mouse.move(box.x+box.width/2,box.y+box.height/2);await page.mouse.wheel(0,-60);
 await page.locator('.jp-Notebook .jp-Cell').nth(1).locator('.cm-content').click();await page.keyboard.press('Shift+Enter');
 await page.locator('.jp-OutputArea').getByText('XYG graph kernel responsive',{exact:false}).last().waitFor({timeout:20000});
 const kernelOutput=await page.locator('.jp-OutputArea').getByText('XYG graph kernel responsive',{exact:false}).last().innerText();
 const kernel=JSON.parse(kernelOutput.slice(kernelOutput.indexOf('XYG graph kernel responsive')+'XYG graph kernel responsive'.length).trim());
 const expectedNativeHash=createHash('sha256').update(await readFile(join(root,'target/release/libxyg_core.so'))).digest('hex');
 if(kernel.native.sha256!==expectedNativeHash||kernel.otherClicks!==0)throw Error('native provenance or widget isolation mismatch');
 await page.locator('.jp-Notebook .jp-Cell').nth(2).locator('.cm-content').click();await page.keyboard.press('Shift+Enter');
 const selectionOutput=page.locator('.jp-OutputArea').getByText('XYG graph Python rows selected',{exact:false}).last();await selectionOutput.waitFor({timeout:20000});
 const selectionText=await selectionOutput.innerText();
 const uuidSelection=JSON.parse(selectionText.slice(selectionText.indexOf('XYG graph Python rows selected')+'XYG graph Python rows selected'.length).trim());
 await page.waitForFunction(()=>globalThis.__graphEvents.some(e=>e.kind==='select'&&e.detail.total===2),{},{timeout:20000});
 const uuidMasks=await canvas.evaluate(canvas=>{
 const view=globalThis[Symbol.for('reflex-dev.xy.shared-webgl-host.v2')].get(document).dashboardResourceSnapshot().clients.find(v=>v.canvas===canvas),gl=view.gl;
 const previous=gl.getParameter(gl.ARRAY_BUFFER_BINDING);
 try{return view.gpuTraces.map(g=>{const values=new Float32Array(g.n);if(g.selBuf){gl.bindBuffer(gl.ARRAY_BUFFER,g.selBuf);gl.getBufferSubData(gl.ARRAY_BUFFER,0,values);}return {trace:g.trace.id,active:g.selActive===true,count:g.n,selected:Array.from(values).flatMap((v,i)=>v===1?[i]:[]),values:Array.from(values)};});}
 finally{gl.bindBuffer(gl.ARRAY_BUFFER,previous);}
 });
 await canvas.scrollIntoViewIfNeeded();
 await page.getByText('Layout complete',{exact:true}).first().waitFor({timeout:45000});
 const finalSteps=await surface.getAttribute('data-graph-steps');
 const dimensions=await picture('final');
 const widgetCount=await page.locator('.jp-OutputArea [data-graph-steps]').count();if(widgetCount!==2)throw Error('missing independent second widget');
 const title=await surface.innerText();if(!title.includes('Progressive property graph')||!title.includes('GraphForge result')||!title.includes('Company')||!title.includes('Person'))throw Error('default title/legend presentation missing');
 await page.locator('.jp-Notebook .jp-Cell').nth(3).locator('.cm-content').click();await page.keyboard.press('Shift+Enter');
 await page.getByText('XYG graph reset',{exact:true}).waitFor({timeout:10000});
 await canvas.scrollIntoViewIfNeeded();
 await page.waitForFunction(()=>globalThis.__graphEvents.some(e=>e.kind==='view_change'&&e.detail.source==='reset'&&e.detail.phase==='end'),{},{timeout:5000});

 await page.locator('.jp-Notebook .jp-Cell').nth(6).locator('.cm-content').click();await page.keyboard.press('Shift+Enter');
 const fixtureOutput=page.locator('.jp-OutputArea').getByText('XYG identity fixture',{exact:false}).last();await fixtureOutput.waitFor({timeout:10000});
 const identityFixture=JSON.parse((await fixtureOutput.innerText()).split('XYG identity fixture')[1].trim());
 await page.waitForFunction(()=>globalThis.__graphEvents.some(e=>e.kind==='view_change'&&e.detail.source==='api'&&e.detail.phase==='end'),{},{timeout:5000});
 const routed=[];
 for(const source of [0,1,2,3,4]){
   await canvas.scrollIntoViewIfNeeded();
   // A trusted hover settles Jupyter's virtualized output and reveals controls.
   const box=await canvas.boundingBox();
   await canvas.hover({position:{x:box.width/2,y:box.height/2}});
   await canvas.evaluate(()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve))));
   const target=await canvas.evaluate((canvas,{source,edgeSources})=>{
    const host=globalThis[Symbol.for('reflex-dev.xy.shared-webgl-host.v2')].get(document);
    const view=host.dashboardResourceSnapshot().clients.find(v=>v.canvas===canvas),meta=view._graphs[0];
    const g=view.gpuTraces.find(g=>g.trace.id===meta.edge_trace),rect=canvas.getBoundingClientRect();
    const indices=edgeSources.flatMap((members,i)=>members.length===1&&members[0]===source?[i]:[]);
    // The self-loop's middle segment is longest; its middle overlaps the node.
    if(source===2)indices.sort((a,b)=>{const length=i=>{const [p,q]=view._projectSegmentEndpoints(g,g._segmentCpu,i);return Math.hypot(q[0]-p[0],q[1]-p[1]);};return length(b)-length(a);});
    for(const index of indices){
      const [a,b]=view._projectSegmentEndpoints(g,g._segmentCpu,index);
      for(const fraction of source===2?[.8,.2,.65,.35]:[.35,.5,.65,.8,.2]){
       const x=a[0]*(1-fraction)+b[0]*fraction-view.plot.x,y=a[1]*(1-fraction)+b[1]*fraction-view.plot.y;
       if(x>=0&&x<rect.width&&y>=0&&y<rect.height&&document.elementFromPoint(rect.left+x,rect.top+y)===canvas)
         return {source,index,x,y,fraction};
      }
    }
    return null;
   },{source,edgeSources:identityFixture.edgeSources});
   if(!target)throw Error('no unobscured rendered edge point '+source);
   const before=await page.evaluate(()=>globalThis.__graphEvents.length), actionBefore=await page.evaluate(()=>globalThis.__graphActions.length);
   await canvas.click({position:{x:target.x,y:target.y}});
   await page.waitForFunction(({before,index,trace})=>globalThis.__graphEvents.slice(before).some(e=>e.kind==='click'&&e.detail.trace===trace&&e.detail.index===index),{before,index:target.index,trace:identityFixture.edgeTrace},{timeout:5000});
   const pointer=await page.evaluate(start=>globalThis.__graphActions.slice(start).find(e=>e.kind==='pointerdown'),actionBefore);
   if(pointer?.step!=='300')throw Error('missing terminal trusted edge pointer');
   routed.push({...target,pointer});
 }
 await page.locator('.jp-Notebook .jp-Cell').nth(4).locator('.cm-content').click();await page.keyboard.press('Shift+Enter');
 const baselineOutput=page.locator('.jp-OutputArea').getByText('XYG graph pointer baseline',{exact:false}).last();await baselineOutput.waitFor({timeout:10000});
 const pointerBaseline=Number((await baselineOutput.innerText()).split('XYG graph pointer baseline')[1].trim());
 if(!Number.isSafeInteger(pointerBaseline))throw Error('missing pointer callback baseline');
 await canvas.scrollIntoViewIfNeeded();
 const finalHoverBefore=await page.evaluate(()=>globalThis.__graphEvents.length);
 await canvas.focus();await page.keyboard.press('Home');
 await page.waitForFunction(start=>globalThis.__graphEvents.slice(start).some(e=>e.kind==='hover'&&e.detail.exact&&e.step==='300'),finalHoverBefore,{timeout:5000});
 const finalPoint=await page.evaluate(()=>globalThis.__graphEvents.findLast(e=>e.kind==='hover'&&e.detail.exact)?.client);
 await page.mouse.click(finalPoint[0],finalPoint[1]);
 const events=await page.evaluate(()=>({actions:globalThis.__graphActions,events:globalThis.__graphEvents}));
 if(!events.actions.some(e=>e.kind==='keydown'&&Number(e.step)<Number(finalSteps)))throw Error('no trusted interaction during unfinished layout');
 if(!events.events.some(e=>e.kind==='select'))throw Error('Python selection failed to reach view');
 await page.locator('.jp-Notebook .jp-Cell').nth(5).locator('.cm-content').click();await page.keyboard.press('Shift+Enter');
 const disposedOutput=page.locator('.jp-OutputArea').getByText('XYG graph disposed',{exact:false}).last();await disposedOutput.waitFor({timeout:20000});
 const finalPointer=JSON.parse((await disposedOutput.innerText()).split('XYG graph disposed')[1].trim());
 if(finalPointer.before!==pointerBaseline||finalPointer.after<=finalPointer.before||finalPointer.id!==finalPointer.expectedId)throw Error('final pointer produced no new exact kernel callback');
 if(external.length)throw Error('external requests '+external.join(','));
 await page.locator('.jp-Notebook .jp-Cell').nth(7).locator('.cm-content').click();await page.keyboard.press('Shift+Enter');
 const routedOutput=page.locator('.jp-OutputArea').getByText('XYG routed identity',{exact:false}).last();await routedOutput.waitFor({timeout:10000});
 const routedIdentity=JSON.parse((await routedOutput.innerText()).split('XYG routed identity')[1].trim());
 await writeFile(join(temp,'routed.json'),JSON.stringify({routedIdentity,routed},null,2));
 await page.locator('.jp-Notebook .jp-Cell').nth(8).locator('.cm-content').click();await page.keyboard.press('Shift+Enter');
 const layeredSurface=page.locator('.jp-Notebook .jp-Cell').nth(8).locator('[data-graph-steps]');await layeredSurface.waitFor({timeout:30000});
 await layeredSurface.getByText('Layout complete',{exact:true}).waitFor({timeout:45000});
 const layeredCanvas=layeredSurface.locator('canvas[role="img"]');await layeredCanvas.scrollIntoViewIfNeeded();await layeredCanvas.focus();
 const layeredActionStart=await page.evaluate(()=>globalThis.__graphActions.length);
 const layeredStart=await page.evaluate(()=>globalThis.__graphEvents.length);await page.keyboard.press('Home');
 await page.waitForFunction(start=>globalThis.__graphEvents.slice(start).some(e=>e.kind==='hover'&&e.detail.exact),layeredStart,{timeout:5000});
 const layeredPoint=await page.evaluate(()=>globalThis.__graphEvents.findLast(e=>e.kind==='hover'&&e.detail.exact).client);
 await page.mouse.click(...layeredPoint);
 await page.locator('.jp-Notebook .jp-Cell').nth(9).locator('.cm-content').click();await page.keyboard.press('Shift+Enter');
 const layeredOutput=page.locator('.jp-OutputArea').getByText('XYG layered identity',{exact:false}).last();await layeredOutput.waitFor({timeout:10000});
 const layeredIdentity=JSON.parse((await layeredOutput.innerText()).split('XYG layered identity')[1].trim());
 const layeredPointer=await page.evaluate(start=>globalThis.__graphActions.slice(start).find(e=>e.kind==='pointerdown'),layeredActionStart);
 if(layeredPointer?.step!=='300')throw Error('missing trusted layered pointer');
 const parityInput=join(temp,'identity-parity-input.json');
 await writeFile(parityInput,JSON.stringify({routedIdentity,layeredIdentity,uuidMasks})+'\n');
 const parity=spawnSync(process.execPath,[join(root,'scripts/graph_notebook_identity_parity.mjs'),parityInput],{cwd:root,env:{...process.env,XYG_NATIVE_LIB:join(root,'target/release/libxyg_core.so')},encoding:'utf8'});
 await writeFile(join(temp,'identity-parity.log'),parity.stdout+parity.stderr);
 if(parity.status!==0)throw Error('Node notebook identity parity failed: '+parity.stderr);
 const nodeParity=JSON.parse(parity.stdout);
 if(nodeParity.nativeSha256!==expectedNativeHash)throw Error('Node notebook identity used a different native library');


 const frames=await page.evaluate(()=>globalThis.__graphFrames);
 if(frames[0]?.step!=='1'||!frames[0]?.width)throw Error('missing initial one-tick native paint');
 const result={artifactDir:temp,frontend,routedIdentity,routed,layeredIdentity,layeredPointer,uuidMasks,nodeParity,presentation:title,kernel,uuidSelection,finalPointer,finalPointerVerified:finalPointer.after>finalPointer.before,expectedNativeHash,initialPicture,widgetCount,events,frames,kernelVerified:true,disposed:true,pageErrors,ok:true,journey:`actual ${frontendKind==='notebook7'?'Notebook 7':'JupyterLab'}/IPython/anywidget/native retained graph`,firstSteps,finalSteps,dimensions,browser:browser.version(),external,errors};
 if(process.env.XYG_GRAPH_NOTEBOOK_REPORT)await writeFile(process.env.XYG_GRAPH_NOTEBOOK_REPORT,JSON.stringify(result,null,2)+'\n');console.log(JSON.stringify(result));
}catch(error){throw Error(JSON.stringify({error:error.message,errors,frames:await page?.evaluate(()=>globalThis.__graphFrames).catch(e=>({diagnosticUnavailable:e.message})),events:await page?.evaluate(()=>globalThis.__graphEvents).catch(e=>({diagnosticUnavailable:e.message})),actions:await page?.evaluate(()=>globalThis.__graphActions).catch(e=>({diagnosticUnavailable:e.message})),body:await page?.locator('body').innerText().catch(()=>''),outputs:await page?.locator('.jp-OutputArea').evaluateAll(els=>els.map(el=>el.innerHTML.slice(-6000))).catch(()=>[]),logs:logs.slice(-6000)}));}
finally{await browser?.close();server.kill('SIGTERM');}
