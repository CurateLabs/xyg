import {runDesktopGraphRegions} from './regions.mjs';
import {installGraphRegionHooks} from '../../scripts/graph_notebook_region_journey.mjs';
import {chromium} from 'playwright';
import {readFile,writeFile,rename} from 'node:fs/promises';
import {join} from 'node:path';
import {createHash} from 'node:crypto';
import {spawnSync} from 'node:child_process';
const regionsMode=process.env.XYG_VSCODE_GRAPH_REGIONS==='1';
const root=process.cwd(),dir=process.env.XYG_NOTEBOOK_PROBE,temp=dir;let browser,ui,graphFrame,selected=false;
const errors=[],pageErrors=[],external=[],network=[],hostAssets=[],outputs=new Map();let serial=0;
const remoteHostPaths=new Map([
 ['https://unpkg.com',['/']],
 ['https://cdn.jsdelivr.net',['/npm/requirejs@2.3.6/bin/r.min.js']],
 ['https://main.vscode-cdn.net',['/extensions/chat.json']],
 ['https://marketplace.visualstudio.com',['/_apis/public/gallery/vscode/xyg-local-test/xyg-graph-notebook-proof/latest']],
]);
const localOrigin=new URL(process.env.XYG_NOTEBOOK_SERVER).origin;
const approvedRequest=request=>{
 const url=new URL(request.url());
 if(!['http:','https:'].includes(url.protocol))return true;
 if(url.origin===localOrigin||url.origin==='https://file+.vscode-resource.vscode-cdn.net')return true;
 return remoteHostPaths.get(url.origin)?.includes(url.pathname)===true
   &&request.method()==='GET'&&!url.search&&!request.postData();
};
const writeRequest=async request=>{const path=join(dir,'request.json');await writeFile(path+'.next',JSON.stringify(request));await rename(path+'.next',path);};
const executeCell=async index=>{const id=++serial;await writeRequest({id,index});const deadline=Date.now()+45000;let result;while(Date.now()<deadline){try{result=JSON.parse(await readFile(join(dir,'response-'+id+'.json'),'utf8'));break;}catch(e){if(e.code!=='ENOENT')throw e;}await new Promise(r=>setTimeout(r,20));}if(!result)throw Error('missing actual execution '+index);if(result.execution.success!==true)throw Error('actual Python cell '+index+' failed: '+JSON.stringify(result.outputs));if(process.env.XYG_VSCODE_FAIL_AFTER_CELL===String(index))throw Error('intentional notebook failure after cell '+index);outputs.set(index,result.outputs.flat().filter(i=>i.mime.startsWith('text/')||i.mime.includes('stdout')).map(i=>i.data).join(''));return result;};
const outputText=index=>outputs.get(index)??'';
const output=prefix=>({async waitFor(){if(![...outputs.values()].some(s=>s.includes(prefix)))throw Error('missing kernel output '+prefix);},async innerText(){const s=[...outputs.values()].findLast(s=>s.includes(prefix));if(!s)throw Error('missing kernel output '+prefix);return s;}});
let inspector;const parsedScripts=new Map(),inspectedSources=[];
const expectedClient=await readFile(join(root,'python/xyg/static/index.js'),'utf8');
const captureActualViews=async()=>{
 if(!inspector){let frame=graphFrame;while(!inspector){try{inspector=await browser.contexts()[0].newCDPSession(frame.parentFrame()?frame:ui);}catch(error){if(!String(error).includes('This frame does not have a separate CDP session'))throw error;frame=frame.parentFrame();if(!frame)throw error;}}inspector.on('Debugger.scriptParsed',info=>parsedScripts.set(info.scriptId,info));await inspector.send('Debugger.enable');}
 let matched=0;
 for(const info of parsedScripts.values()){
  if(!info.url.startsWith('blob:'))continue;
  const {scriptSource}=await inspector.send('Debugger.getScriptSource',{scriptId:info.scriptId});
  if(!scriptSource.includes('_a11yClientPoint')||!scriptSource.includes('graph_mount'))continue;
  const exact=scriptSource.trimEnd()===expectedClient.trimEnd();
  const pin={url:info.url,bytes:Buffer.byteLength(scriptSource),sha256:createHash('sha256').update(scriptSource).digest('hex'),exactClientSource:exact};inspectedSources.push(pin);
  if(!exact){await writeFile(join(dir,'inspector-sources.json'),JSON.stringify(inspectedSources,null,2));throw Error('actual widget module differs from pinned client bytes');}
  const group='xyg-notebook-read-only-inspection';
  try{
   const evaluated=await inspector.send('Runtime.evaluate',{expression:'import('+JSON.stringify(info.url)+').then(module=>module.ChartView.prototype)',contextId:info.executionContextId,awaitPromise:true,objectGroup:group});
   if(evaluated.exceptionDetails||!evaluated.result.objectId)throw Error('cannot inspect actual cached ChartView module');
   const objects=await inspector.send('Runtime.queryObjects',{prototypeObjectId:evaluated.result.objectId,objectGroup:group});
   const found=await inspector.send('Runtime.callFunctionOn',{objectId:objects.objects.objectId,functionDeclaration:`function(source){let count=0;for(const view of this){if(!view.canvas)continue;const scope=view.canvas.ownerDocument.defaultView;scope.__xygInspectedViewSources??=new WeakMap();scope.__xygInspectedViewSources.set(view.canvas,source);scope.__xygInspectedViewRefs??=[];if(!scope.__xygInspectedViewRefs.some(ref=>ref.deref()===view))scope.__xygInspectedViewRefs.push(new WeakRef(view));scope.__xygActualViewForCanvas=canvas=>scope.__xygInspectedViewRefs.map(ref=>ref.deref()).find(view=>view?.canvas===canvas);count++;}return count;}`,arguments:[{value:pin}],returnByValue:true});
   matched+=found.result.value??0;
  }finally{await inspector.send('Runtime.releaseObjectGroup',{objectGroup:group});}
 }
 await writeFile(join(dir,'inspector-sources.json'),JSON.stringify(inspectedSources,null,2));
 if(!matched)throw Error('no actual ChartView objects found for the loaded client');
};
const geometrySnapshot=async canvas=>canvas.evaluate(canvas=>{
 const view=globalThis.__xygActualViewForCanvas(canvas),meta=view._graphs[0];
 const trace=view.gpuTraces.find(g=>g.trace.id===meta.node_trace);
 return {ranges:view.root.xy.state().ranges,width:canvas.getBoundingClientRect().width,height:canvas.getBoundingClientRect().height,
  positions:{x:Array.from(trace._cpu.x,(_,i)=>view._decodeValue(trace._cpu.x,trace._cpu.xMeta||trace.xMeta,i)),y:Array.from(trace._cpu.y,(_,i)=>view._decodeValue(trace._cpu.y,trace._cpu.yMeta||trace.yMeta,i))}};
});
const viewportRect=async canvas=>{
 const box=await canvas.evaluate(el=>{const r=el.getBoundingClientRect();return {x:r.left,y:r.top,width:r.width,height:r.height};});
 let frame=graphFrame;const chain=[];
 while(frame.parentFrame()){
  const owner=await frame.frameElement();const child=await frame.evaluate(()=>({width:innerWidth,height:innerHeight}));
  const info=await owner.evaluate(el=>{const r=el.getBoundingClientRect();return {x:r.left,y:r.top,width:r.width,height:r.height,clientWidth:el.clientWidth,clientHeight:el.clientHeight,offsetWidth:el.offsetWidth,offsetHeight:el.offsetHeight,left:el.clientLeft,top:el.clientTop};});
  if(Math.abs(info.width-info.offsetWidth)>.01||Math.abs(info.height-info.offsetHeight)>.01||Math.abs(info.clientWidth-child.width)>.01||Math.abs(info.clientHeight-child.height)>.01)throw Error('unsupported scaled notebook frame: '+JSON.stringify({info,child}));
  box.x+=info.x+info.left;box.y+=info.y+info.top;chain.push(info);frame=frame.parentFrame();
 }
 const viewport=await ui.evaluate(()=>({width:innerWidth,height:innerHeight}));
 if(box.x<0||box.y<0||box.x+box.width>viewport.width+.01||box.y+box.height>viewport.height+.01)throw Error('actual notebook canvas not fully visible: '+JSON.stringify({box,viewport,chain}));
 return box;
};
const physicalPoint=async(canvas,position)=>{
 const inside=await canvas.evaluate((el,p)=>{const r=el.getBoundingClientRect();return document.elementFromPoint(r.left+p.x,r.top+p.y)===el;},position);
 if(!inside){const diagnostic=await canvas.evaluate((el,p)=>{const r=el.getBoundingClientRect(),root=el.closest('[role=region]').getBoundingClientRect(),hit=document.elementFromPoint(r.left+p.x,r.top+p.y);return {position:p,rect:r.toJSON(),root:root.toJSON(),hit:hit?.outerHTML.slice(0,300)};},position);await ui.screenshot({path:join(dir,'obscured-workbench.png')});throw Error('notebook canvas point is obscured inside its output document: '+JSON.stringify(diagnostic));}
 const box=await viewportRect(canvas);return {x:box.x+position.x,y:box.y+position.y};
};
const nativeHover=async(canvas,position)=>{const p=await physicalPoint(canvas,position);await ui.mouse.move(p.x,p.y);};
const trustedClick=async(canvas,point)=>{
 const offset=await canvas.evaluate(el=>{const c=el.getBoundingClientRect(),r=el.closest('[role=region]').getBoundingClientRect();return{x:c.left-r.left,y:c.top-r.top};});
 const p=await physicalPoint(canvas,{x:point[0]-offset.x,y:point[1]-offset.y});await ui.mouse.click(p.x,p.y);
};
const canvasClick=async(canvas,position)=>{const p=await physicalPoint(canvas,position);await ui.mouse.click(p.x,p.y);};
const revealCell=async index=>{const id=++serial;await writeRequest({id,index,action:'reveal'});const deadline=Date.now()+10000;while(Date.now()<deadline){try{const d=JSON.parse(await readFile(join(dir,'response-'+id+'.json'),'utf8'));if(d.revealed!==index)throw Error('wrong notebook reveal response');await ui.evaluate(()=>new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r))));return;}catch(e){if(e.code!=='ENOENT')throw e;}await new Promise(r=>setTimeout(r,20));}throw Error('notebook output reveal did not settle');};

try{
for(let i=0;i<200;i++){try{browser=await chromium.connectOverCDP('http://127.0.0.1:'+process.env.XYG_NOTEBOOK_DEBUG_PORT,{timeout:1000});break;}catch{await new Promise(r=>setTimeout(r,100));}}
if(!browser)throw Error('VSCode debug endpoint absent');
let pages=[];for(let i=0;i<200;i++){pages=browser.contexts().flatMap(c=>c.pages());if(pages.length)break;await new Promise(r=>setTimeout(r,100));}
ui=pages.find(p=>p.url().includes('workbench.html'))??pages[0];if(!ui)throw Error('actual workbench missing');
await ui.route('**/*',route=>{
 const request=route.request(),url=new URL(request.url());
 if(['http:','https:'].includes(url.protocol))network.push({origin:url.origin,path:url.pathname,type:request.resourceType(),method:request.method(),hasQuery:!!url.search,bodyBytes:Buffer.byteLength(request.postData()??''),approved:approvedRequest(request)});
 if(!approvedRequest(request)){external.push({origin:url.origin,path:url.pathname,method:request.method()});return route.abort();}
 return route.continue();
});
const pendingAssets=new Set();
ui.on('response',response=>{
 const url=new URL(response.url());
 if(url.origin!=='https://cdn.jsdelivr.net'||url.pathname!=='/npm/requirejs@2.3.6/bin/r.min.js')return;
 const pending=response.body().then(bytes=>hostAssets.push({origin:url.origin,path:url.pathname,status:response.status(),bytes:bytes.length,sha256:createHash('sha256').update(bytes).digest('hex')})).catch(error=>hostAssets.push({origin:url.origin,path:url.pathname,status:response.status(),unavailable:error.message}));
 pendingAssets.add(pending);pending.finally(()=>pendingAssets.delete(pending));
});
ui.on('pageerror',e=>pageErrors.push(e.message));ui.on('console',m=>{if(m.type()==='error'||m.type()==='warning')errors.push(m.text());});
const installHooks=()=>{
 globalThis.__graphHookCleanup?.();
 globalThis.__graphFrames??=[];globalThis.__graphActions??=[];globalThis.__graphEvents??=[];
 const cleanup=[];let primarySurface=document.querySelector('[data-graph-steps]');
 const record=()=>{
  primarySurface??=document.querySelector('[data-graph-steps]');
  if(!primarySurface?.isConnected)return;
  const canvas=primarySurface.querySelector('canvas[role="img"]'),step=primarySurface.getAttribute('data-graph-steps');
  if(!canvas?.width||!canvas?.height||globalThis.__graphFrames.at(-1)?.step===step)return;
  globalThis.__graphFrames.push({step,time:performance.now(),width:canvas.width,height:canvas.height});
 };
 for(const kind of ['click','hover','view_change','select']){
  const listener=event=>{const rect=event.target.closest('[role=region]').getBoundingClientRect(),px=event.detail.cursor?.px;globalThis.__graphEvents.push({kind,detail:event.detail,client:px?[rect.left+px[0],rect.top+px[1]]:null,step:event.target.closest('[data-graph-steps]')?.dataset.graphSteps});};
  document.addEventListener('xy:'+kind,listener);cleanup.push(()=>document.removeEventListener('xy:'+kind,listener));
 }
 for(const kind of ['keydown','pointerdown','wheel']){
  const listener=event=>{if(event.target instanceof HTMLCanvasElement&&event.isTrusted)globalThis.__graphActions.push({kind,key:event.key,step:event.target.closest('[data-graph-steps]')?.dataset.graphSteps});};
  document.addEventListener(kind,listener,true);cleanup.push(()=>document.removeEventListener(kind,listener,true));
 }
 const observer=new MutationObserver(record);observer.observe(document,{subtree:true,attributes:true,attributeFilter:['data-graph-steps'],childList:true});cleanup.push(()=>observer.disconnect());
 globalThis.__graphHookCleanup=()=>cleanup.forEach(f=>f());record();
};await ui.addInitScript(installHooks);for(const frame of ui.frames())await frame.evaluate(installHooks).catch(()=>{});
if(regionsMode){await ui.addInitScript(installGraphRegionHooks);for(const frame of ui.frames())await frame.evaluate(installGraphRegionHooks).catch(()=>{});}
await ui.getByText('XYG local notebook server',{exact:true}).click({timeout:30000});
await ui.locator('.quick-input-widget .monaco-list-row').filter({hasText:'Python 3 (ipykernel)'}).click({timeout:30000});selected=true;
const deadline=Date.now()+45000;while(Date.now()<deadline){const dialog=ui.getByRole('dialog').filter({hasText:'Widgets require us to download supporting files from a 3rd party website.'});if(await dialog.count()){await writeFile(join(dir,'first-use-dialog.txt'),await dialog.innerText());const local=dialog.getByRole('button',{name:/do(n.t| not) show again/i});await local.click();}for(const f of ui.frames()){await f.evaluate(installHooks).catch(()=>{});if(await f.locator('[data-graph-steps]').count().catch(()=>0)){graphFrame=f;break;}}if(graphFrame)break;await new Promise(r=>setTimeout(r,20));}
if(!graphFrame)throw Error('real notebook graph output did not paint');
await graphFrame.evaluate(installHooks);const surface=graphFrame.locator('[data-graph-steps]').first();await surface.locator('canvas[role=img]').waitFor({timeout:5000});await writeFile(join(dir,'first-state.json'),JSON.stringify(await graphFrame.evaluate(()=>({frames:globalThis.__graphFrames,step:document.querySelector('[data-graph-steps]')?.dataset.graphSteps})),null,2));
if(regionsMode){
 await graphFrame.evaluate(installGraphRegionHooks);
 await runDesktopGraphRegions({root,dir,graphFrame,ui,browser,executeCell,outputText,revealCell,captureActualViews,viewportRect,nativeHover,pendingAssets,network,hostAssets,expectedClient,inspectedSources,pageErrors,external});
}else{
const picture=async name=>{await revealCell(0);const path=join(temp,name+'.png');const clip=await viewportRect(canvas);const bytes=await ui.screenshot({path,clip});await ui.screenshot({path:join(temp,name+'-workbench.png')});const probe=spawnSync(join(root,'.venv/bin/python'),['-c','from PIL import Image; import sys,json; im=Image.open(sys.argv[1]).convert("RGB"); print(json.dumps({"colors":len(im.getcolors(im.width*im.height)),"width":im.width,"height":im.height}))',path],{encoding:'utf8'});if(probe.status!==0)throw Error(probe.stderr);const result={...JSON.parse(probe.stdout),sha256:createHash('sha256').update(bytes).digest('hex'),step:await surface.getAttribute('data-graph-steps')};if(result.colors<=2)throw Error('empty graph canvas');return result;};
const firstSteps=await surface.getAttribute('data-graph-steps');
 const canvas=surface.locator('canvas[role="img"]');
 const initialPicture=await picture('initial');
 if(Number(initialPicture.step)>=300)throw Error('initial picture was terminal');
 await canvas.evaluate(el=>el.focus({preventScroll:true})); await ui.keyboard.press('Home'); await ui.keyboard.press('Enter');
 await graphFrame.waitForFunction(()=>globalThis.__graphEvents.some(e=>e.kind==='hover'&&e.detail.exact),{},{timeout:5000});
 const point=await graphFrame.evaluate(()=>globalThis.__graphEvents.findLast(e=>e.kind==='hover'&&e.detail.exact)?.detail.cursor.px);
 if(!point)throw Error('missing exact readout coordinates');await trustedClick(canvas,point);
 // Wheel/pan and keyboard activation are trusted input against the real view.
 const box=await canvas.boundingBox(); await nativeHover(canvas,{x:box.width/2,y:box.height/2});const viewBefore=await graphFrame.evaluate(()=>globalThis.__graphEvents.length);await ui.mouse.wheel(0,-60);await graphFrame.waitForFunction(start=>globalThis.__graphEvents.slice(start).some(e=>e.kind==='view_change'&&e.detail.phase==='end'),viewBefore,{timeout:5000});
 await executeCell(1);
 await output('XYG graph kernel responsive').waitFor({timeout:20000});
 const kernelOutput=await output('XYG graph kernel responsive').innerText();
 const kernel=JSON.parse(kernelOutput.slice(kernelOutput.indexOf('XYG graph kernel responsive')+'XYG graph kernel responsive'.length).trim());
 const expectedNativeHash=createHash('sha256').update(await readFile(join(root,'target/release/libxyg_core.so'))).digest('hex');
 if(kernel.native.sha256!==expectedNativeHash||kernel.otherClicks!==0)throw Error('native provenance or widget isolation mismatch');
 await executeCell(2);
 const selectionOutput=output('XYG graph Python rows selected');await selectionOutput.waitFor({timeout:20000});
 const selectionText=await selectionOutput.innerText();
 const uuidSelection=JSON.parse(selectionText.slice(selectionText.indexOf('XYG graph Python rows selected')+'XYG graph Python rows selected'.length).trim());
 await graphFrame.waitForFunction(()=>globalThis.__graphEvents.some(e=>e.kind==='select'&&e.detail.total===2),{},{timeout:20000});
 await captureActualViews();
 const initialClientSources=await graphFrame.locator('[data-graph-steps] canvas[role=img]').evaluateAll(canvases=>canvases.map(canvas=>globalThis.__xygInspectedViewSources.get(canvas)));
 const primaryClientSource=await canvas.evaluate(canvas=>globalThis.__xygInspectedViewSources.get(canvas));
 const uuidMasks=await canvas.evaluate(canvas=>{
 const view=globalThis.__xygActualViewForCanvas(canvas),gl=view.gl;
 const previous=gl.getParameter(gl.ARRAY_BUFFER_BINDING);
 try{return view.gpuTraces.map(g=>{const values=new Float32Array(g.n);if(g.selBuf){gl.bindBuffer(gl.ARRAY_BUFFER,g.selBuf);gl.getBufferSubData(gl.ARRAY_BUFFER,0,values);}return {trace:g.trace.id,active:g.selActive===true,count:g.n,selected:Array.from(values).flatMap((v,i)=>v===1?[i]:[]),values:Array.from(values)};});}
 finally{gl.bindBuffer(gl.ARRAY_BUFFER,previous);}
 });
 await revealCell(0);
 await surface.getByText('Layout complete',{exact:true}).waitFor({timeout:45000});
 const finalSteps=await surface.getAttribute('data-graph-steps');
 const beforeResetGeometry=await geometrySnapshot(canvas);
 const dimensions=await picture('final');
 const widgetCount=await graphFrame.locator('[data-graph-steps]').count();if(widgetCount!==2)throw Error('missing independent second widget');
 const title=await surface.innerText();if(!title.includes('Progressive property graph')||!title.includes('GraphForge result')||!title.includes('Company')||!title.includes('Person'))throw Error('default title/legend presentation missing');
 await executeCell(3);
 if(!outputText(3).includes('XYG graph reset'))throw Error('missing reset output');
 await revealCell(0);
 await graphFrame.waitForFunction(()=>globalThis.__graphEvents.some(e=>e.kind==='view_change'&&e.detail.source==='reset'&&e.detail.phase==='end'),{},{timeout:5000});

 await executeCell(6);
 const fixtureOutput=output('XYG identity fixture');await fixtureOutput.waitFor({timeout:10000});
 const identityFixture=JSON.parse((await fixtureOutput.innerText()).split('XYG identity fixture')[1].trim());
 await graphFrame.waitForFunction(()=>globalThis.__graphEvents.some(e=>e.kind==='view_change'&&e.detail.source==='api'&&e.detail.phase==='end'),{},{timeout:5000});
 const connectedGeometry=await geometrySnapshot(canvas);
 const connectedPicture=await picture('connected');
 const pixels=spawnSync(join(root,'.venv/bin/python'),['-c','import json,sys;from pathlib import Path;from scripts.graph_notebook_pixels import mark_witness;x=json.load(sys.stdin);print(json.dumps(mark_witness(Path(x["path"]).read_bytes(),x["positions"],x["ranges"])))'],{cwd:root,input:JSON.stringify({path:join(dir,'connected.png'),positions:identityFixture.positions,ranges:connectedGeometry.ranges}),encoding:'utf8'});
 await writeFile(join(dir,'mark-pixels.log'),pixels.stdout+pixels.stderr);
 await writeFile(join(dir,'geometry-diagnostic.json'),JSON.stringify({beforeResetGeometry,connectedGeometry},null,2));
 if(pixels.status!==0)throw Error('canonical mark pixel oracle failed: '+pixels.stderr);
 const markPixels=JSON.parse(pixels.stdout);
 const routed=[];
 for(const source of [0,1,2,3,4]){
   await revealCell(0);
   // A trusted hover settles Jupyter's virtualized output and reveals controls.
   const box=await canvas.boundingBox();
   await nativeHover(canvas,{x:box.width/2,y:box.height/2});
   await canvas.evaluate(()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve))));
   const target=await canvas.evaluate((canvas,{source,edgeSources})=>{
    const view=globalThis.__xygActualViewForCanvas(canvas),meta=view._graphs[0];
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
   const before=await graphFrame.evaluate(()=>globalThis.__graphEvents.length), actionBefore=await graphFrame.evaluate(()=>globalThis.__graphActions.length);
   await canvasClick(canvas,{x:target.x,y:target.y});
   await graphFrame.waitForFunction(({before,index,trace})=>globalThis.__graphEvents.slice(before).some(e=>e.kind==='click'&&e.detail.trace===trace&&e.detail.index===index),{before,index:target.index,trace:identityFixture.edgeTrace},{timeout:5000});
   const pointer=await graphFrame.evaluate(start=>globalThis.__graphActions.slice(start).find(e=>e.kind==='pointerdown'),actionBefore);
   if(pointer?.step!=='300')throw Error('missing terminal trusted edge pointer');
   routed.push({...target,pointer});
 }
 await executeCell(4);
 const baselineOutput=output('XYG graph pointer baseline');await baselineOutput.waitFor({timeout:10000});
 const pointerBaseline=Number((await baselineOutput.innerText()).split('XYG graph pointer baseline')[1].trim());
 if(!Number.isSafeInteger(pointerBaseline))throw Error('missing pointer callback baseline');
 await revealCell(0);
 const finalHoverBefore=await graphFrame.evaluate(()=>globalThis.__graphEvents.length);
 await canvas.evaluate(el=>el.focus({preventScroll:true}));await ui.keyboard.press('Home');
 await graphFrame.waitForFunction(start=>globalThis.__graphEvents.slice(start).some(e=>e.kind==='hover'&&e.detail.exact&&e.step==='300'),finalHoverBefore,{timeout:5000});
 const finalPoint=await graphFrame.evaluate(()=>globalThis.__graphEvents.findLast(e=>e.kind==='hover'&&e.detail.exact)?.detail.cursor.px);
 await trustedClick(canvas,finalPoint);
 const events=await graphFrame.evaluate(()=>({actions:globalThis.__graphActions,events:globalThis.__graphEvents}));
 if(!events.actions.some(e=>e.kind==='keydown'&&Number(e.step)<Number(finalSteps)))throw Error('no trusted interaction during unfinished layout');
 if(!events.events.some(e=>e.kind==='select'))throw Error('Python selection failed to reach view');
 await executeCell(5);
 const disposedOutput=output('XYG graph disposed');await disposedOutput.waitFor({timeout:20000});
 const finalPointer=JSON.parse((await disposedOutput.innerText()).split('XYG graph disposed')[1].trim());
 if(finalPointer.before!==pointerBaseline||finalPointer.after<=finalPointer.before||finalPointer.id!==finalPointer.expectedId)throw Error('final pointer produced no new exact kernel callback');
 if(external.length)throw Error('unapproved renderer requests '+JSON.stringify(external));
 await executeCell(7);
 const routedOutput=output('XYG routed identity');await routedOutput.waitFor({timeout:10000});
 const routedIdentity=JSON.parse((await routedOutput.innerText()).split('XYG routed identity')[1].trim());
 await writeFile(join(temp,'routed.json'),JSON.stringify({routedIdentity,routed},null,2));
 const previousInstances=await graphFrame.locator('[data-graph-instance]').evaluateAll(els=>els.map(e=>e.dataset.graphInstance));
 await executeCell(8);
 await graphFrame.waitForFunction(old=>[...document.querySelectorAll('[data-graph-instance]')].some(el=>!old.includes(el.dataset.graphInstance)),previousInstances,{timeout:30000});
 const layeredInstance=await graphFrame.evaluate(old=>[...document.querySelectorAll('[data-graph-instance]')].find(el=>!old.includes(el.dataset.graphInstance)).dataset.graphInstance,previousInstances);
 if(!/^[a-f0-9-]+$/.test(layeredInstance))throw Error('invalid actual layered instance');
 const layeredSurface=graphFrame.locator('[data-graph-instance='+JSON.stringify(layeredInstance)+']');await layeredSurface.waitFor({timeout:30000});
 await layeredSurface.getByText('Layout complete',{exact:true}).waitFor({timeout:45000});
 const layeredCanvas=layeredSurface.locator('canvas[role="img"]');await captureActualViews();
 const layeredClientSource=await layeredCanvas.evaluate(canvas=>globalThis.__xygInspectedViewSources.get(canvas));
 await revealCell(8);await layeredCanvas.evaluate(el=>el.focus({preventScroll:true}));
 const layeredActionStart=await graphFrame.evaluate(()=>globalThis.__graphActions.length);
 const layeredStart=await graphFrame.evaluate(()=>globalThis.__graphEvents.length);await ui.keyboard.press('Home');
 await graphFrame.waitForFunction(start=>globalThis.__graphEvents.slice(start).some(e=>e.kind==='hover'&&e.detail.exact),layeredStart,{timeout:5000});
 const layeredPoint=await graphFrame.evaluate(()=>globalThis.__graphEvents.findLast(e=>e.kind==='hover'&&e.detail.exact).detail.cursor.px);
 await trustedClick(layeredCanvas,layeredPoint);
 await executeCell(9);
 const layeredOutput=output('XYG layered identity');await layeredOutput.waitFor({timeout:10000});
 const layeredIdentity=JSON.parse((await layeredOutput.innerText()).split('XYG layered identity')[1].trim());
 const layeredPointer=await graphFrame.evaluate(start=>globalThis.__graphActions.slice(start).find(e=>e.kind==='pointerdown'),layeredActionStart);
 if(layeredPointer?.step!=='300')throw Error('missing trusted layered pointer');
 const parityInput=join(temp,'identity-parity-input.json');
 await writeFile(parityInput,JSON.stringify({routedIdentity,layeredIdentity,uuidMasks})+'\n');
 const parity=spawnSync(process.execPath,[join(root,'scripts/graph_notebook_identity_parity.mjs'),parityInput],{cwd:root,env:{...process.env,XYG_NATIVE_LIB:join(root,'target/release/libxyg_core.so')},encoding:'utf8'});
 await writeFile(join(temp,'identity-parity.log'),parity.stdout+parity.stderr);
 if(parity.status!==0)throw Error('Node notebook identity parity failed: '+parity.stderr);
 const nodeParity=JSON.parse(parity.stdout);
 if(nodeParity.nativeSha256!==expectedNativeHash)throw Error('Node notebook identity used a different native library');


 const frameTimeOrigin=await graphFrame.evaluate(()=>performance.timeOrigin);
 const frames=await graphFrame.evaluate(()=>globalThis.__graphFrames);
 if(frames[0]?.step!=='1'||!frames[0]?.width)throw Error('missing initial one-tick native paint');
await Promise.all([...pendingAssets]);
const host=JSON.parse(await readFile(join(dir,'extension-state.json'),'utf8'));
const inspectedClientSources=JSON.parse(await readFile(join(dir,'inspector-sources.json'),'utf8'));
const clientSha256=createHash('sha256').update(expectedClient).digest('hex');
const result={artifactDir:dir,host,frontend:{kind:'vscode-jupyter',appName:host.appName,appHost:host.appHost,version:host.vscode,extensionId:host.extension.id,jupyterExtension:host.extension.version,node:host.node,notebookType:host.notebook.type,cellCount:host.notebook.cellCount,normalGuiMode:host.normalGuiMode},clientSha256,inspectedClientSources,usedClientSources:{primary:primaryClientSource,initial:initialClientSources,layered:layeredClientSource},hostAssets,networkScope:'Renderer requests only; allowlisted host bootstrap traffic; not offline or extension-host Node network audit',routedIdentity,routed,connectedPicture,connectedGeometry,markPixels,beforeResetGeometry,layeredIdentity,layeredPointer,uuidMasks,nodeParity,presentation:title,kernel,uuidSelection,finalPointer,finalPointerVerified:finalPointer.after>finalPointer.before,expectedNativeHash,initialPicture,widgetCount,events,frames,frameTimeOrigin,kernelVerified:true,disposed:true,pageErrors,ok:true,journey:'actual VSCode Jupyter/IPython/anywidget/native retained graph',firstSteps,finalSteps,dimensions,browser:browser.version(),external,network,errors};
if(pageErrors.length)throw Error('actual application runtime errors '+pageErrors.join(';'));
if(external.length)throw Error('unapproved late renderer requests '+JSON.stringify(external));
if(initialClientSources.length!==2||initialClientSources.some(pin=>!pin?.exactClientSource||pin.sha256!==clientSha256))throw Error('initial widget source identity mismatch');
if(!primaryClientSource?.exactClientSource||!layeredClientSource?.exactClientSource||primaryClientSource.sha256!==clientSha256||layeredClientSource.sha256!==clientSha256)throw Error('used canvas source identity mismatch');
await inspector?.detach();inspector=null;await writeFile(join(dir,'report.json'),JSON.stringify(result,null,2)+'\n');console.log('actual VSCode notebook complete');
}
}catch(error){await writeFile(join(dir,'failure.json'),JSON.stringify({error:error.message,stack:error.stack,errors,pageErrors,network,regionEvents:regionsMode?await graphFrame?.evaluate(()=>globalThis.__regionEvents).catch(()=>[]):undefined,actions:await graphFrame?.evaluate(()=>globalThis.__graphActions).catch(()=>[]),frames:await graphFrame?.evaluate(()=>globalThis.__graphFrames).catch(e=>({diagnosticUnavailable:e.message})),events:await graphFrame?.evaluate(()=>globalThis.__graphEvents).catch(e=>({diagnosticUnavailable:e.message})),body:await ui?.locator('body').innerText().catch(()=>''),graphBody:await graphFrame?.locator('body').innerText().catch(()=>'' )},null,2));throw error;}
finally{if(regionsMode&&selected&&graphFrame&&!outputs.get(3)){try{await executeCell(3);await writeFile(join(dir,'failure-owner-cleanup.json'),JSON.stringify({output:outputText(3)})+'\n');}catch(error){await writeFile(join(dir,'failure-owner-cleanup.json'),JSON.stringify({error:error.message})+'\n');}}await inspector?.detach().catch(()=>{});if(!selected)await ui?.keyboard.press('Escape').catch(()=>{});await writeFile(join(dir,'done'),'done\n');await browser?.close();}
