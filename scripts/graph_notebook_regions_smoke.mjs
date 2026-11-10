#!/usr/bin/env node
// Actual notebook/anywidget transport; all gestures below are trusted input.
import assert from 'node:assert/strict';
import {spawn, spawnSync} from 'node:child_process';
import {createHash} from 'node:crypto';
import {cp, mkdir, mkdtemp, readFile, writeFile} from 'node:fs/promises';
import {createServer} from 'node:net';
import {join} from 'node:path';
import {fileURLToPath} from 'node:url';
import {chromium} from 'playwright';
import {namedIdleKernel} from './graph_notebook_kernel_witness.mjs';

const args=process.argv.slice(2);
if(args.length!==0&&(args.length!==2||args[0]!=='--frontend'||!['jupyterlab','notebook7'].includes(args[1])))
 throw Error('usage: graph_notebook_regions_smoke.mjs [--frontend jupyterlab|notebook7]');
const frontendKind=args[1]??'jupyterlab';
const root=fileURLToPath(new URL('../',import.meta.url));
const temp=await mkdtemp(join(root,'target/xyg-graph-regions-'));
await cp(join(root,'tests/notebook_graph_regions.ipynb'),join(temp,'regions.ipynb'));
for(const name of ['runtime','config','data'])await mkdir(join(temp,name));
const allocator=createServer();await new Promise(r=>allocator.listen(0,'127.0.0.1',r));
const port=allocator.address().port;await new Promise(r=>allocator.close(r));
const origin=`http://127.0.0.1:${port}`;
const server=spawn(process.env.XYG_GRAPH_JUPYTER??join(root,frontendKind==='notebook7'?'.venv/bin/jupyter-notebook':'.venv/bin/jupyter-lab'),[
 '--no-browser','--ServerApp.ip=127.0.0.1',`--ServerApp.port=${port}`,`--ServerApp.root_dir=${temp}`,
 '--IdentityProvider.token=','--ServerApp.password=',
],{cwd:root,env:{...process.env,XYG_NATIVE_LIB:join(root,'target/release/libxyg_core.so'),
 PYTHONPATH:`${root}/python:${root}/tests`,JUPYTER_RUNTIME_DIR:join(temp,'runtime'),
 JUPYTER_CONFIG_DIR:join(temp,'config'),JUPYTER_DATA_DIR:join(temp,'data')},stdio:['ignore','pipe','pipe']});
let logs='',browser,page,startupError;const errors=[],external=[];
server.on('error',error=>{startupError=error;});
server.stdout.on('data',b=>logs+=b);server.stderr.on('data',b=>logs+=b);
const dpr=Number(process.env.XYG_GRAPH_REGION_DPR??1);
assert.ok(dpr===1||dpr===2,'DPR must be 1 or 2');
const inside=(p,polygon)=>{
 let hit=false;
 for(let i=0,j=polygon.length-1;i<polygon.length;j=i++){
  const a=polygon[i],b=polygon[j];
  if((a[1]>p[1])!==(b[1]>p[1])&&p[0]<(b[0]-a[0])*(p[1]-a[1])/(b[1]-a[1])+a[0])hit=!hit;
 }
 return hit;
};
try{
 for(let i=0;i<100;i++){if(startupError)throw startupError;try{if((await fetch(origin+'/api/status')).ok)break;}catch{}await new Promise(r=>setTimeout(r,100));}
 browser=await chromium.launch({...(process.env.XYG_CHROMIUM?{executablePath:process.env.XYG_CHROMIUM}:{}),
  args:['--use-gl=swiftshader','--enable-unsafe-swiftshader','--ignore-gpu-blocklist']});
 page=await browser.newPage({viewport:{width:1200,height:1000},deviceScaleFactor:dpr});
 page.on('pageerror',e=>errors.push(e.message));
 await page.route('**/*',route=>{const u=new URL(route.request().url());
  if(!['http:','https:'].includes(u.protocol)||u.origin===origin)return route.continue();
  external.push(u.href);return route.abort();});
 await page.addInitScript(()=>{
  globalThis.__regionEvents=[];globalThis.__regionTrusted=[];
  for(const kind of ['brush','select','view_change'])document.addEventListener('xy:'+kind,e=>{
   globalThis.__regionEvents.push({kind,detail:e.detail});
  });
  document.addEventListener('pointerdown',e=>{if(e.target instanceof HTMLCanvasElement)
   globalThis.__regionTrusted.push({kind:'pointerdown',trusted:e.isTrusted,shift:e.shiftKey});},true);
  document.addEventListener('wheel',e=>{if(e.target instanceof HTMLCanvasElement)
   globalThis.__regionTrusted.push({kind:'wheel',trusted:e.isTrusted});},true);
 });
 await page.goto(origin+(frontendKind==='notebook7'?'/notebooks/regions.ipynb':'/lab/tree/regions.ipynb'));
 const frontend=await page.evaluate(kind=>{
  const config=JSON.parse(document.getElementById('jupyter-config-data')?.textContent||'{}');
  return {kind,name:config.appName,version:config.appVersion,namespace:config.appNamespace,
   staticUrl:config.fullStaticUrl,route:location.pathname,
   staticRequests:[...new Set(performance.getEntriesByType('resource').map(r=>new URL(r.name).pathname).filter(path=>path.startsWith('/static/')))].sort()};
 },frontendKind);
 const expectedApp=frontendKind==='notebook7'?['Jupyter Notebook','notebook','7','/static/notebook']:['JupyterLab','lab','4','/static/lab'];
 assert.equal(frontend.name,expectedApp[0]);assert.equal(frontend.namespace,expectedApp[1]);
 assert.equal(frontend.version?.split('.')[0],expectedApp[2]);assert.equal(frontend.staticUrl,expectedApp[3]);
 assert.equal(frontend.route,frontendKind==='notebook7'?'/notebooks/regions.ipynb':'/lab/tree/regions.ipynb');
 assert.ok(frontend.staticRequests.some(path=>path.startsWith(expectedApp[3]+'/')),'actual frontend assets must be loaded');
 await page.locator('.jp-Notebook .jp-Cell').first().waitFor({timeout:45000});
 const select=page.getByRole('button',{name:'Select'});if(await select.count())await select.click();
 const kernel=await namedIdleKernel(page,frontendKind);
 const cell=async(index)=>{await page.locator('.jp-Notebook .jp-Cell').nth(index).locator('.cm-content').click();await page.keyboard.press('Shift+Enter');};
 await cell(0);
 const surfaces=page.locator('.jp-OutputArea [data-graph-steps]'),surface=surfaces.first();
 await surface.waitFor({timeout:45000});
 await surface.getByText('Layout complete',{exact:true}).waitFor({timeout:45000});
 assert.equal(await surfaces.count(),2);
 await surfaces.nth(1).getByText('Layout complete',{exact:true}).waitFor({timeout:45000});
 const canvas=surface.locator('canvas[role="img"]');
 let reportSequence=0;
 const report=async()=>{
  const expected=++reportSequence;
  await cell(1);
  const output=page.locator('.jp-Notebook .jp-Cell').nth(1).locator('.jp-OutputArea');
  await output.getByText('XYG graph region report',{exact:false}).waitFor({timeout:15000});
  await page.waitForFunction(expected=>document.querySelectorAll('.jp-Notebook .jp-Cell')[1]?.textContent.includes(`"report_sequence": ${expected},`),expected,{timeout:15000});
  const text=await output.innerText();assert.ok(!text.includes('Traceback'),text);
  return JSON.parse(text.split('XYG graph region report')[1].trim());
 };
 const initial=await report(),fixture=initial.fixture;
 assert.equal(initial.native_sha256,createHash('sha256').update(await readFile(join(root,'target/release/libxyg_core.so'))).digest('hex'));
 await page.waitForFunction(()=>globalThis.__regionEvents.some(e=>e.kind==='view_change'&&e.detail.source==='api'&&e.detail.phase==='end'),null,{timeout:10000});
 const geometry=async()=>{
  await canvas.scrollIntoViewIfNeeded();
  return canvas.evaluate(canvas=>{
   const view=globalThis[Symbol.for('reflex-dev.xy.shared-webgl-host.v2')].get(document).dashboardResourceSnapshot().clients.find(v=>v.canvas===canvas);
   const meta=view._graphs[0],gpu=view.gpuTraces.find(g=>g.trace.id===meta.node_trace),box=canvas.getBoundingClientRect();
   const edge=view.gpuTraces.find(g=>g.trace.id===meta.edge_trace);
   return {points:Array.from({length:gpu.n},(_,i)=>{
    const cpu=gpu._cpu,p=view._projectDataPoint(gpu.xAxis,gpu.yAxis,view._decodeValue(cpu.x,cpu.xMeta||gpu.xMeta,i),view._decodeValue(cpu.y,cpu.yMeta||gpu.yMeta,i));
    return [p[0]-view.plot.x,p[1]-view.plot.y];}),
    edgePoints:Array.from({length:edge.n},(_,i)=>{const [a,b]=view._projectSegmentEndpoints(edge,edge._segmentCpu,i);return [(a[0]+b[0])/2-view.plot.x,(a[1]+b[1])/2-view.plot.y];}),
    origin:[box.left,box.top],width:box.width,height:box.height,state:view._stateSelection,
    history:{past:view._historyPast.length,future:view._historyFuture.length}};
  });
 };
 const masks=()=>canvas.evaluate(canvas=>{
  const view=globalThis[Symbol.for('reflex-dev.xy.shared-webgl-host.v2')].get(document).dashboardResourceSnapshot().clients.find(v=>v.canvas===canvas),gl=view.gl,previous=gl.getParameter(gl.ARRAY_BUFFER_BINDING);
  try{return view.gpuTraces.map(g=>{const data=new Float32Array(g.n);if(g.selBuf){gl.bindBuffer(gl.ARRAY_BUFFER,g.selBuf);gl.getBufferSubData(gl.ARRAY_BUFFER,0,data);}
   return {trace:g.trace.id,active:g.selActive===true,values:Array.from(data)};});}finally{gl.bindBuffer(gl.ARRAY_BUFFER,previous);}
 });
 const picture=async(name,points)=>{
  const path=join(temp,name+'.png'),bytes=await canvas.screenshot({path});
  const paintPath=join(temp,name+'-paint.png');
  const paint=Buffer.from(await canvas.evaluate(canvas=>canvas.toDataURL('image/png').split(',')[1]),'base64');
  await writeFile(paintPath,paint);
  const probe=spawnSync(join(root,'.venv/bin/python'),['-c',
   'from PIL import Image; import json,sys; im=Image.open(sys.argv[1]).convert("RGBA"); points=json.loads(sys.argv[2]); print(json.dumps({"size":im.size,"samples":[[im.getpixel((round(x)+dx,round(y)+dy)) for dx,dy in [(0,0),(1,0),(0,1),(-1,0),(0,-1)]] if 2<=x<im.width-2 and 2<=y<im.height-2 else None for x,y in points]}))',
   paintPath,JSON.stringify(points.map(p=>p.map(v=>v*dpr)))],{encoding:'utf8'});
  assert.equal(probe.status,0,probe.stderr);
  const result={sha256:createHash('sha256').update(bytes).digest('hex'),paintSha256:createHash('sha256').update(paint).digest('hex'),...JSON.parse(probe.stdout)};
  await writeFile(join(temp,name+'-pixels.json'),JSON.stringify({points,result},null,2)+'\n');
  return result;
 };
 const waitSelect=async(start)=>page.waitForFunction(start=>globalThis.__regionEvents.slice(start).some(e=>e.kind==='select'),start,{timeout:10000});
 const oracle=(data)=>{
  const brush=data.brushes.at(-1),selection=data.selections.at(-1);
  const nodes=fixture.x.flatMap((x,i)=>{
   const y=fixture.y[i],hit=brush.polygon?inside([x,y],brush.polygon):x>=brush.x0&&x<=brush.x1&&y>=brush.y0&&y<=brush.y1;
   return hit?[i]:[];
  });
  const set=new Set(nodes),edges=fixture.edge_source.flatMap((s,i)=>set.has(s)&&set.has(fixture.edge_target[i])?[i]:[]);
  const expected=[...nodes.map(i=>['node',fixture.node_ids[i],i]),...edges.map(i=>['edge',fixture.edge_ids[i],i])].sort();
  assert.deepEqual(selection.identities.map(v=>[v.kind,v.uuid,v.index]).sort(),expected);
  assert.ok(selection.identities.every(v=>Array.isArray(v.layers)));
  assert.equal(data.other_selections.length,0);
  const nodeRows=[...new Set(nodes.map(i=>fixture.member_of[i]))].sort((a,b)=>a-b);
  const edgeRows=fixture.edge_rows.flatMap((members,i)=>members.length&&members.every(m=>edges.includes(m))?[i]:[]);
  assert.deepEqual(selection.per_trace[String(fixture.node_trace)]??[],nodeRows);
  assert.deepEqual(selection.per_trace[String(fixture.edge_trace)]??[],edgeRows);
  return {nodes,edges,nodeRows,edgeRows,brush};
 };
 const checkMasks=async(expected)=>{
  const value=await masks();
  for(const [trace,rows] of [[fixture.node_trace,expected.nodeRows],[fixture.edge_trace,expected.edgeRows]]){
   const mask=value.find(g=>g.trace===trace);assert.equal(mask.active,true);
   assert.ok(mask.values.every(v=>v===0||v===1));
   assert.deepEqual(mask.values.flatMap((v,i)=>v===1?[i]:[]),rows);
  }
  return value;
 };
 // Exhaustion is real native owner admission, not a forged reply. Ordinary
 // public row highlights and the last accepted picture must remain usable.
 await page.waitForFunction(()=>globalThis.__regionEvents.some(e=>e.kind==='select'&&e.detail.total===2),null,{timeout:10000});
 let capacityGeometry=await geometry();const capacityMasks=await masks();
 assert.deepEqual(capacityGeometry.state,{rows:true});assert.ok(initial.capacity_owners>0);
 const capacityBefore=await picture('capacity-before',capacityGeometry.points);
 const cp=capacityGeometry.points[1],cr=8;
 await page.keyboard.down('Shift');await page.mouse.move(capacityGeometry.origin[0]+cp[0]-cr,capacityGeometry.origin[1]+cp[1]-cr);
 await page.mouse.down();await page.mouse.move(capacityGeometry.origin[0]+cp[0]+cr,capacityGeometry.origin[1]+cp[1]+cr,{steps:6});await page.mouse.up();await page.keyboard.up('Shift');
 await surface.getByText('Graph selection exceeds the resource limit',{exact:true}).waitFor({timeout:10000});
 await page.mouse.move(1195,995);
 await canvas.evaluate(()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve))));
 const capacityAfter=await picture('capacity-refused',capacityGeometry.points),refused=await report();
 assert.equal(refused.selections.length,0);assert.equal(refused.brushes.length,0);
 assert.deepEqual(refused.state.selection,{rows:true});assert.deepEqual(await masks(),capacityMasks);
 assert.deepEqual((await geometry()).history,capacityGeometry.history);
 assert.equal(capacityAfter.paintSha256,capacityBefore.paintSha256,'capacity refusal preserves complete accepted RGBA');
 // Seed one explicit prior snapshot to exercise Back while the real native
 // owner table is full. The subsequent ordinary gestures keep their history.
 const capacityHistory=await canvas.evaluate(canvas=>{
  const view=globalThis[Symbol.for('reflex-dev.xy.shared-webgl-host.v2')].get(document).dashboardResourceSnapshot().clients.find(v=>v.canvas===canvas);
  const before=view._durableState(),target=structuredClone(before);
  target.ranges.x=target.ranges.x.map(v=>v+0.25);
  target.selection={range:{x0:-1000,x1:1000,y0:-1000,y1:1000}};
  view.__regionHistorySaved={past:[...view._historyPast],future:[...view._historyFuture],last:view._historyLastInteractionId};
  view._historyPast.length=0;view._historyFuture.length=0;view._historyPast.push(target);
  const status=[...canvas.closest('[data-graph-steps]').querySelectorAll('[aria-live]')].find(el=>el.textContent==='Graph selection exceeds the resource limit');
  if(!status)throw Error('capacity history control requires the real refusal status');
  globalThis.__regionHistoryRefused=false;
  const observer=new MutationObserver(()=>{if(status.textContent==='Graph selection exceeds the resource limit'){
   globalThis.__regionHistoryRefused=true;observer.disconnect();
  }});observer.observe(status,{childList:true,characterData:true,subtree:true});
  return {before,target,admitted:view.root.xy.back(),seededTarget:true};
 });
 assert.equal(capacityHistory.admitted,true);
 await page.waitForFunction(()=>globalThis.__regionHistoryRefused,null,{timeout:10000});
 await canvas.evaluate(canvas=>new Promise(resolve=>{
  const view=globalThis[Symbol.for('reflex-dev.xy.shared-webgl-host.v2')].get(document).dashboardResourceSnapshot().clients.find(v=>v.canvas===canvas);
  const check=()=>{if(!view._viewAnim)resolve();else requestAnimationFrame(check);};check();
 }));
 capacityHistory.after=await canvas.evaluate(canvas=>{
  const view=globalThis[Symbol.for('reflex-dev.xy.shared-webgl-host.v2')].get(document).dashboardResourceSnapshot().clients.find(v=>v.canvas===canvas);
  const result={state:view._durableState(),past:structuredClone(view._historyPast),future:structuredClone(view._historyFuture)};
  const saved=view.__regionHistorySaved;view._historyPast.splice(0,view._historyPast.length,...saved.past);
  view._historyFuture.splice(0,view._historyFuture.length,...saved.future);view._historyLastInteractionId=saved.last;delete view.__regionHistorySaved;
  return result;
 });
 assert.deepEqual(capacityHistory.after.state,capacityHistory.before,'refused Back preserves the complete accepted camera and selection');
 assert.deepEqual(capacityHistory.after.past,[capacityHistory.target]);assert.deepEqual(capacityHistory.after.future,[]);
 assert.deepEqual(await masks(),capacityMasks);
 const capacityHistoryPaint=await picture('capacity-history-refused',capacityGeometry.points);
 assert.equal(capacityHistoryPaint.paintSha256,capacityBefore.paintSha256,'refused Back preserves the entire accepted RGBA');
 const clearStart=await page.evaluate(()=>globalThis.__regionEvents.length);
 await cell(2);await waitSelect(clearStart);
 let g=await geometry();const before=await picture('before',g.points),beforeEdges=await picture('before-edges',g.edgePoints);
 const p=g.points[1],nearest=Math.min(...g.points.filter((_,i)=>i!==1).map(q=>Math.hypot(q[0]-p[0],q[1]-p[1])));
 const radius=Math.min(12,nearest/4);assert.ok(radius>3,'fixture must resolve a separate node');
 let start=await page.evaluate(()=>globalThis.__regionEvents.length);
 await page.keyboard.down('Shift');await page.mouse.move(g.origin[0]+p[0]-radius,g.origin[1]+p[1]-radius);
 await page.mouse.down();await page.mouse.move(g.origin[0]+p[0]+radius,g.origin[1]+p[1]+radius,{steps:6});await page.mouse.up();await page.keyboard.up('Shift');
 await waitSelect(start);const box=await report(),boxExpected=oracle(box);
 assert.deepEqual(boxExpected.nodes,[1]);assert.ok(boxExpected.edges.length>0,'self-loop is induced');
 const boxMasks=await checkMasks(boxExpected);g=await geometry();const afterBox=await picture('box',g.points);
 assert.notEqual(before.sha256,afterBox.sha256);
 const distance=(a,b)=>a.reduce((sum,v,i)=>sum+Math.abs(v-b[i]),0);
 assert.ok(distance(before.samples[1][0],afterBox.samples[1][0])<=9,'selected flat center retains color');
 assert.ok(before.samples.some((samples,i)=>i!==1&&samples&&afterBox.samples[i]&&samples[0][3]-afterBox.samples[i][0][3]>128),'unselected flat center alpha dims against the host backdrop');
 const afterBoxEdges=await picture('box-edges',g.edgePoints);
 const alpha=samples=>Math.max(...samples.map(p=>p[3]));
 const unselectedEdge=fixture.edge_rows.findIndex(m=>m.length===1&&m[0]===3);
 assert.ok(alpha(beforeEdges.samples[unselectedEdge])-alpha(afterBoxEdges.samples[unselectedEdge])>80,'unselected edge shaft alpha dims');
 const selectedEdge=fixture.edge_rows.findIndex(m=>m.length===1&&m[0]===2);
 assert.ok(Math.abs(alpha(beforeEdges.samples[selectedEdge])-alpha(afterBoxEdges.samples[selectedEdge]))<=3,'selected self-loop shaft retains alpha');
 // Clear via the public selection toolbar, then create a genuinely concave
 // polygon from current screen coordinates; kernel geometry is the oracle.
 await canvas.hover();await surface.getByRole('button',{name:/^Selection controls/}).click();
 await surface.getByRole('menuitem',{name:'Lasso Select',exact:true}).click();
 g=await geometry();const visible=g.points.filter(p=>p[0]>2&&p[0]<g.width-2&&p[1]>2&&p[1]<g.height-2),xs=visible.map(p=>p[0]),ys=visible.map(p=>p[1]);
 let polygon;
 for(const sx of [...new Set(xs)].sort((a,b)=>a-b).slice(0,-1).map((v,i,a)=>(v+[...new Set(xs)].sort((a,b)=>a-b)[i+1])/2)){
  for(const sy of [...new Set(ys)].sort((a,b)=>a-b).slice(0,-1).map((v,i)=>(v+[...new Set(ys)].sort((a,b)=>a-b)[i+1])/2)){
   const l=Math.max(2,Math.min(...xs)-15),r=Math.min(g.width-2,Math.max(...xs)+15),t=Math.max(2,Math.min(...ys)-15),b=Math.min(g.height-2,Math.max(...ys)+15);
   const candidates=[[[l,t],[r,t],[r,sy],[sx,sy],[sx,b],[l,b]],[[l,t],[sx,t],[sx,sy],[r,sy],[r,b],[l,b]],
    [[sx,t],[r,t],[r,b],[l,b],[l,sy],[sx,sy]],[[l,t],[r,t],[r,b],[sx,b],[sx,sy],[l,sy]]];
   for(const candidate of candidates){const selected=g.points.map(p=>inside(p,candidate));
    if(selected[0]&&selected[1]&&!selected[2]&&!selected[3]&&candidate.every((p,i)=>Math.hypot(p[0]-candidate[(i+1)%6][0],p[1]-candidate[(i+1)%6][1])>10))polygon??=candidate;}
  }
 }
 assert.ok(polygon,'fixture must admit a nontrivial concave polygon');
 start=await page.evaluate(()=>globalThis.__regionEvents.length);
 await page.mouse.move(g.origin[0]+polygon[0][0],g.origin[1]+polygon[0][1]);await page.mouse.down();
 for(const p of [...polygon.slice(1),polygon[0]])await page.mouse.move(g.origin[0]+p[0],g.origin[1]+p[1],{steps:8});
 await page.mouse.up();await waitSelect(start);
 const lasso=await report(),lassoExpected=oracle(lasso);assert.ok(lassoExpected.brush.polygon.length>=6);
 assert.deepEqual(lassoExpected.nodes,[0,1]);
 assert.deepEqual(lassoExpected.edges,[0,1,2],'parallel edges and self-loop survive; crossing edges are excluded');
 const lassoMasks=await checkMasks(lassoExpected),afterLasso=await picture('lasso',(await geometry()).points);
 // A real camera change must not turn the next predicate into source-row or
 // screen-space guesses: compare its new emitted f64 geometry independently.
 await canvas.hover();await surface.getByRole('button',{name:'Pan',exact:true}).click();
 g=await geometry();start=await page.evaluate(()=>globalThis.__regionEvents.length);
 await page.mouse.move(g.origin[0]+g.width*0.75,g.origin[1]+g.height*0.75);await page.mouse.down();
 await page.mouse.move(g.origin[0]+g.width*0.75+20,g.origin[1]+g.height*0.75-12,{steps:6});await page.mouse.up();
 await page.waitForFunction(start=>globalThis.__regionEvents.slice(start).some(e=>e.kind==='view_change'&&e.detail.phase==='end'),start,{timeout:10000});
 start=await page.evaluate(()=>globalThis.__regionEvents.length);await page.mouse.wheel(0,-45);
 await page.waitForFunction(start=>globalThis.__regionEvents.slice(start).some(e=>e.kind==='view_change'&&e.detail.phase==='end'),start,{timeout:10000});
 g=await geometry();const moved=g.points[0];start=await page.evaluate(()=>globalThis.__regionEvents.length);
 await page.keyboard.down('Shift');await page.mouse.move(g.origin[0]+moved[0]-8,g.origin[1]+moved[1]-8);await page.mouse.down();
 await page.mouse.move(g.origin[0]+moved[0]+8,g.origin[1]+moved[1]+8,{steps:6});await page.mouse.up();await page.keyboard.up('Shift');
 await waitSelect(start);const cameraBox=await report(),cameraExpected=oracle(cameraBox),cameraMasks=await checkMasks(cameraExpected);
 assert.deepEqual(cameraExpected.nodes,[0]);assert.deepEqual(cameraExpected.edges,[]);
 const combinedHistory=await canvas.evaluate(async canvas=>{
  const view=globalThis[Symbol.for('reflex-dev.xy.shared-webgl-host.v2')].get(document).dashboardResourceSnapshot().clients.find(v=>v.canvas===canvas);
  const wait=()=>new Promise((resolve,reject)=>{
   const timer=setTimeout(()=>{stop();reject(Error('history selection reply timed out'));},10000);
   const stop=view.comm.onMessage(msg=>{if(msg.type==='selection'){clearTimeout(timer);stop();resolve(msg);}});
  });
  const before=view._durableState(),past=view._historyPast.length;
  const ranges=structuredClone(before.ranges);ranges.x=ranges.x.map(v=>v+0.25);
  let done=wait();view.root.xy.applyState({ranges,selection:{range:{x0:-1000,x1:1000,y0:-1000,y1:1000}}});await done;
  const after=view._durableState(),entries=structuredClone(view._historyPast);
  done=wait();const back=view.root.xy.back();await done;
  while(view._viewAnim)await new Promise(requestAnimationFrame);
  const restored=view._durableState();
  done=wait();const forward=view.root.xy.forward();await done;
  while(view._viewAnim)await new Promise(requestAnimationFrame);
  return {before,after,past,entries,back,restored,forward,reapplied:view._durableState()};
 });
 assert.equal(combinedHistory.entries.length,combinedHistory.past+1,'one mixed API update makes one undo entry');
 assert.deepEqual(combinedHistory.entries.at(-1),combinedHistory.before);
 assert.equal(combinedHistory.back,true);assert.deepEqual(combinedHistory.restored,combinedHistory.before);
 assert.equal(combinedHistory.forward,true);assert.deepEqual(combinedHistory.reapplied,combinedHistory.after);
 const trusted=await page.evaluate(()=>globalThis.__regionTrusted);
 assert.ok(trusted.length>=2&&trusted.every(v=>v.trusted));assert.ok(trusted.some(v=>v.shift));assert.ok(trusted.some(v=>v.kind==='wheel'));
 await cell(3);await page.locator('.jp-Notebook .jp-Cell').nth(3).locator('.jp-OutputArea').getByText('XYG graph region cleanup',{exact:false}).waitFor({timeout:10000});
 assert.equal(errors.length,0,JSON.stringify(errors));assert.equal(external.length,0);
 const result={ok:true,artifactDir:temp,frontend,kernel,dpr,browser:browser.version(),initial,capacity:{before:capacityBefore,after:capacityAfter,refused,masks:capacityMasks,history:capacityHistory,historyPaint:capacityHistoryPaint},combinedHistory,box,boxExpected,boxMasks,lasso,lassoExpected,lassoMasks,cameraBox,cameraExpected,cameraMasks,before,beforeEdges,afterBox,afterBoxEdges,afterLasso,trusted,disposed:true};
 await writeFile(join(temp,'report.json'),JSON.stringify(result,null,2)+'\n');
 if(process.env.XYG_GRAPH_REGION_REPORT)await writeFile(process.env.XYG_GRAPH_REGION_REPORT,JSON.stringify(result,null,2)+'\n');
 console.log(JSON.stringify({ok:true,artifactDir:temp,nodes:lassoExpected.nodes,edges:lassoExpected.edges,dpr}));
}catch(error){await writeFile(join(temp,'failure.json'),JSON.stringify({error:error.stack,logs,errors,body:await page?.locator('body').innerText().catch(()=>''),events:await page?.evaluate(()=>globalThis.__regionEvents).catch(()=>[])},null,2));throw error;}
finally{await browser?.close();server.kill('SIGTERM');}
