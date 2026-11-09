import {test} from 'node:test';
import assert from 'node:assert/strict';
import {mkdtempSync, writeFileSync, readFileSync, rmSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {fileURLToPath} from 'node:url';
import {chromium} from '../../../node_modules/playwright/index.mjs';
import {createChunkedNativeApp, frame} from '../../../examples/vanilla-ts/chunked-native-host.mjs';
import {scatterChart} from '../src/charts.js';
import {spawnSync} from 'node:child_process';

// Same deterministic paired source as the installed notebook, physically backed.
const yValue=i=>((i*53)%997)/997;
function artifact(path) {
 const rows=16384,chunks=128,offset=64+chunks*48,b=Buffer.alloc(offset+rows*16+2048*24);
 b.write('XYGC');b.writeUInt32LE(2,4);b.writeBigUInt64LE(BigInt(rows),8);b.writeUInt32LE(128,16);b.writeUInt32LE(chunks,20);b.writeBigUInt64LE(BigInt(offset),24);b.writeBigUInt64LE(BigInt(offset+rows*16),32);b.writeUInt32LE(2048,40);
 for(let i=0;i<chunks;i++){const p=64+i*48;b.writeBigUInt64LE(BigInt(i*128),p);b.writeUInt32LE(128,p+8);[i*128,i*128+127,Math.min(...Array.from({length:128},(_,j)=>yValue(i*128+j))),Math.max(...Array.from({length:128},(_,j)=>yValue(i*128+j)))].forEach((v,j)=>b.writeDoubleLE(v,p+16+8*j));}
 for(let i=0;i<rows;i++){b.writeDoubleLE(i,offset+i*16);b.writeDoubleLE(yValue(i),offset+i*16+8);}
 for(let j=0;j<2048;j++){const i=j===2047?16383:j*8,p=offset+rows*16+j*24;b.writeBigUInt64LE(BigInt(i),p);b.writeDoubleLE(i,p+8);b.writeDoubleLE(yValue(i),p+16);}
 writeFileSync(path,b);
}

test('public native HTTP consumer: gesture, fullscan pixels, pointer IDs, failure and remount',async()=>{
 const chrome=process.env.XYG_CHROMIUM??process.env.XYG_TEST_CHROMIUM;
 // Normal Node CI provisions Playwright's Chromium; absence fails, never skips.
 const directory=mkdtempSync(join(tmpdir(),'xyg-native-http-')),path=join(directory,'source.xygc');artifact(path);writeFileSync(join(directory,'original-source.xygc'),readFileSync(path));
 const clicks=[],selections=[],app=await createChunkedNativeApp({path,assets:fileURLToPath(new URL('../../../packages/xy-client/dist',import.meta.url)),staticDirectory:directory,callbacks:{onHover:()=>{},onClick:row=>clicks.push(row),onSelect:selection=>selections.push([...selection.sourceRowIds].map(String))}});
 const incoming=[];const originalMessage=app.hosts[0].message.bind(app.hosts[0]);app.hosts[0].message=msg=>{incoming.push(msg);return originalMessage(msg)};
 const authoredPaint={color:'#ff0000',size:13,symbol:'square',opacity:.35,stroke:'#000000',stroke_width:2};
 const authored=app.hosts[0].initial.traces[0];
 authored.style={...authored.style,symbol:authoredPaint.symbol,opacity:authoredPaint.opacity,stroke:authoredPaint.stroke,stroke_width:authoredPaint.stroke_width};
 authored.color_ch={mode:'constant',constant:authoredPaint.color};authored.size_ch={mode:'constant',constant:authoredPaint.size,range_px:[2,18]};
 let browser;
 const errors=[],external=[];
 try {
  browser=await chromium.launch({...(chrome?{executablePath:chrome}:{}),args:['--no-sandbox','--use-gl=angle','--use-angle=swiftshader','--enable-unsafe-swiftshader']});
  const page=await browser.newPage({viewport:{width:1200,height:1000}});page.on('pageerror',e=>errors.push(e.message));
  await page.exposeFunction('nativeCurrent',ranges=>{const host=app.hosts[0],last=incoming.filter(message=>message.type==='view_change').at(-1);return last?.phase==='end'&&JSON.stringify(last.ranges)===JSON.stringify(ranges)&&host.frame===String(host.generation)&&!host.pending&&!host.staged&&!host.ready;});
  await page.route('**/*',route=>{if(route.request().url().startsWith(app.origin))return route.continue();external.push(route.request().url());return route.abort();});
  await page.addInitScript(()=>{const create=WebGL2RenderingContext.prototype.createBuffer;WebGL2RenderingContext.prototype.createBuffer=function(...args){return globalThis.__rejectNativeStage?null:create.apply(this,args)};globalThis.__chunkedFrames=[];globalThis.__chunkedViews=[];globalThis.exact=[];globalThis.failures=[];globalThis.selections=[];globalThis.clickEvents=[];document.addEventListener('xy:click',e=>globalThis.clickEvents.push(e.detail));
   document.addEventListener('xy:chunked_frame',e=>globalThis.__chunkedFrames.push(e.detail));
   document.addEventListener('xy:view_change',e=>{if(e.target.closest('#chart'))globalThis.__chunkedViews.push(e.detail)});
   document.addEventListener('xy:chunked_error',e=>globalThis.failures.push(e.detail));
   document.addEventListener('xy:hover',e=>{if(e.detail.exact){const r=e.target.getBoundingClientRect();globalThis.exact.push({row:e.detail.row,point:[r.left+e.detail.cursor.px[0],r.top+e.detail.cursor.px[1]]})}});
   document.addEventListener('xy:select',e=>globalThis.selections.push({total:e.detail.total,ids:(e.detail.source_row_ids??[]).flatMap(s=>[...s.ids].map(String))}));
  });
  await page.goto(app.origin);const canvas=page.locator('#chart canvas[data-xy-slot=canvas]');await canvas.waitFor();
  const home=app.hosts[0].payload().spec;
  assert.equal(app.hosts[0].initial.sourceProvenance.detailRowsRead,0n);
  assert.equal(app.hosts[1].initial.sourceProvenance.detailRowsRead,0n);
  await page.evaluate(()=>globalThis.__rejectNativeStage=true);
  const box=await canvas.boundingBox();await page.mouse.move(box.x+box.width/2,box.y+box.height/2);await page.mouse.wheel(0,-1200);
  await page.waitForFunction(()=>globalThis.failures.length>0);
  await assert.rejects(app.hosts[0].whenPainted(),/rejected/);
  assert.equal(app.hosts[0].chart,app.hosts[0].initial);
  assert.equal(await page.evaluate(()=>globalThis.__chunkedFrames.length),0);
  await page.evaluate(()=>{globalThis.__rejectNativeStage=false;globalThis.__chunkedViews=[];globalThis.__chunkedFrames=[]});
  await page.mouse.wheel(0,-60);
  await page.waitForFunction(()=>globalThis.__chunkedViews.at(-1)?.phase==='end');
  const ranges=await canvas.evaluate(c=>c.closest('.xy').xy.state().ranges);
  await page.waitForFunction(async ranges=>await globalThis.nativeCurrent(ranges),ranges);await app.hosts[0].whenPainted();
  const expected=Array.from({length:16384},(_,i)=>i).filter(i=>i>=ranges.x[0]&&i<=ranges.x[1]&&yValue(i)>=ranges.y[0]&&yValue(i)<=ranges.y[1]);
  assert.deepEqual([...app.hosts[0].chart.sourceRowIds].map(Number),expected);
  const oracle=scatterChart(expected,expected.map(yValue),{density:false,...authoredPaint});
  oracle.setAxis('x',{domain:home.x_axis.range,margin:0});oracle.setAxis('y',{domain:home.y_axis.range,margin:0});
  const {spec,buffers}=oracle.buildPayload({split:true});writeFileSync(join(directory,'oracle.xybf'),frame({spec},buffers));
  await page.evaluate(async ranges=>{const {render,decodeFrame}=await import('/assets/index.js');const packet=decodeFrame(await(await fetch('/oracle.xybf')).arrayBuffer());render({el:document.querySelector('#oracle'),model:{get:k=>k==='spec'?packet.message.spec:packet.buffers,on(){},off(){},send(){}}});document.querySelector('#oracle .xy').xy.applyState({ranges},{animate:false,history:false});},ranges);
  const oracleCanvas=page.locator('#oracle canvas[data-xy-slot=canvas]');await page.mouse.move(1,1);await canvas.screenshot({path:join(directory,'refined.png')});await oracleCanvas.screenshot({path:join(directory,'oracle.png')});
  const paint=async(c,name)=>{await page.evaluate(()=>new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r))));writeFileSync(join(directory,name),Buffer.from(await c.evaluate(c=>c.toDataURL('image/png').split(',')[1]),'base64'));};
  await paint(canvas,'refined-paint.png');await paint(oracleCanvas,'oracle-paint.png');
  const compare=(a,b,equal=true)=>{const r=spawnSync(process.env.XYG_PYTHON??fileURLToPath(new URL('../../../.venv/bin/python',import.meta.url)),['-c','from PIL import Image;import sys; a,b=[Image.open(p).convert("RGBA") for p in sys.argv[1:3]];assert (a.size==b.size and a.tobytes()==b.tobytes()) == (sys.argv[3]=="equal")',join(directory,a),join(directory,b),equal?'equal':'different'],{encoding:'utf8'});assert.equal(r.status,0,r.stderr);};compare('refined-paint.png','oracle-paint.png');
  const control=app.hosts[0].initial.buildPayload({split:true});writeFileSync(join(directory,'overview-control.xybf'),frame({spec:control.spec},control.buffers));
  await page.evaluate(async ranges=>{const {render,decodeFrame}=await import('/assets/index.js');const packet=decodeFrame(await(await fetch('/overview-control.xybf')).arrayBuffer());const el=document.createElement('div');el.id='overview-control';document.body.append(el);globalThis.controlCleanup=render({el,model:{get:k=>k==='spec'?packet.message.spec:packet.buffers,on(){},off(){},send(){}}});el.querySelector('.xy').xy.applyState({ranges},{animate:false,history:false});},ranges);
  await paint(page.locator('#overview-control canvas[data-xy-slot=canvas]'),'overview-control-paint.png');compare('refined-paint.png','overview-control-paint.png',false);
  await page.evaluate(()=>{globalThis.controlCleanup();document.querySelector('#overview-control').remove()});
  // Real committed public view changes revisit a working set below the Rust cache cap.
  const navigatePaint=async ranges=>{const previous=app.hosts[0].frame;await canvas.evaluate((c,ranges)=>c.closest('.xy').xy.applyState({ranges},{animate:false,history:false}),ranges);await page.waitForFunction(previous=>globalThis.__chunkedFrames.some(f=>BigInt(f.frame)>BigInt(previous)),previous);await page.waitForFunction(async ranges=>await globalThis.nativeCurrent(ranges),ranges);await app.hosts[0].whenPainted();};
  const cacheRevisit=[];
  for(const x of [[8000,8090],[8001,8089],[8000,8090]]) {
    await navigatePaint({x,y:[0,1]});const provenance=app.hosts[0].chart.sourceProvenance;
    cacheRevisit.push({bytesRead:String(provenance.bytesRead),chunksRead:String(provenance.chunksRead)});
    assert.deepEqual([...app.hosts[0].chart.sourceRowIds],Array.from({length:x[1]-x[0]+1},(_,i)=>BigInt(i+x[0])));
  }
  assert.equal(cacheRevisit[1].bytesRead,'0');assert.equal(cacheRevisit[2].bytesRead,'0');
  await navigatePaint(ranges);
  await canvas.scrollIntoViewIfNeeded();await page.evaluate(()=>globalThis.exact=[]);await canvas.focus();await page.keyboard.press('Home');for(let i=0;i<20;i++)await page.keyboard.press('ArrowRight');await page.waitForFunction(()=>globalThis.exact.some(h=>h.row.index===20));const hit=await page.evaluate(()=>globalThis.exact.at(-1));const pointTarget=await page.evaluate(([x,y])=>{const el=document.elementFromPoint(x,y);return {html:el?.outerHTML.slice(0,1500),box:document.querySelector('#chart canvas[data-xy-slot=canvas]').getBoundingClientRect().toJSON()}},hit.point);await page.mouse.click(...hit.point);
  const root=page.locator('#chart .xy');await root.locator('[data-xy-modebar-select-trigger]').click();await root.locator('[data-xy-modebar-select-item=select]').click();
  const b=await canvas.boundingBox();await page.mouse.move(b.x+b.width*.2,b.y+b.height*.2);await page.mouse.down();await page.mouse.move(b.x+b.width*.8,b.y+b.height*.8,{steps:8});await page.mouse.up();
  await page.waitForFunction(()=>globalThis.selections.some(s=>s.total>0&&s.ids.length===s.total));
  writeFileSync(join(directory,'pointer-debug.json'),JSON.stringify({clicks,selections,incoming,hit,pointTarget,events:await page.evaluate(()=>globalThis.clickEvents)},null,2));
  assert.ok(clicks.length&&selections.length);assert.ok(expected.includes(Number(clicks.at(-1).source_row_id)));const boxSelection=await canvas.evaluate(c=>c.closest('.xy').xy.state().selection.range);
  assert.deepEqual(selections.at(-1),expected.filter(i=>i>=boxSelection.x0&&i<=boxSelection.x1&&yValue(i)>=boxSelection.y0&&yValue(i)<=boxSelection.y1).map(String));
  await root.locator('[data-xy-modebar-select-trigger]').click();await root.locator('[data-xy-modebar-select-item=select-lasso]').click();
  const selectedBefore=selections.length,lasso=await canvas.boundingBox();
  await page.mouse.move(lasso.x+lasso.width*.25,lasso.y+lasso.height*.25);await page.mouse.down();
  for(const [x,y]of [[.75,.25],[.75,.75],[.25,.75],[.25,.25]])await page.mouse.move(lasso.x+lasso.width*x,lasso.y+lasso.height*y,{steps:4});await page.mouse.up();
  await page.waitForFunction(n=>globalThis.selections.length>n,selectedBefore);
  const polygon=await canvas.evaluate(c=>c.closest('.xy').xy.state().selection.polygon);
  const inside=(x,y)=>{let keep=false;for(let i=0,j=polygon.length-1;i<polygon.length;j=i++){const a=polygon[i],b=polygon[j];if((a[1]>y)!==(b[1]>y)&&x<(b[0]-a[0])*(y-a[1])/(b[1]-a[1])+a[0])keep=!keep;}return keep;};
  assert.deepEqual(selections.at(-1),expected.filter(i=>inside(i,yValue(i))).map(String));
  const before=await canvas.evaluate(c=>c.closest('.xy').xy.state()),previousFrame=app.hosts[0].frame;await page.locator('#chart').evaluate(el=>el.remount());await page.waitForFunction(previous=>globalThis.__chunkedFrames.some(f=>BigInt(f.frame)>BigInt(previous)),previousFrame);await app.hosts[0].whenPainted();
  const remounted=page.locator('#chart canvas[data-xy-slot=canvas]');assert.deepEqual(await remounted.evaluate(c=>c.closest('.xy').xy.state().ranges),before.ranges);
  await remounted.evaluate(c=>c.closest('.xy').xy.back());
  await remounted.evaluate(c=>c.closest('.xy').xy.forward());
  assert.deepEqual(await remounted.evaluate(c=>c.closest('.xy').xy.state()),before);
  const last=[...app.hosts[0].chart.sourceRowIds].map(Number);
  const beforeBudget=await page.evaluate(()=>globalThis.failures.length);
  await remounted.evaluate(c=>c.closest('.xy').xy.applyState({ranges:{x:[0,16383],y:[0,1]},selection:null},{animate:false,history:false}));await page.waitForFunction(n=>globalThis.failures.length>n,beforeBudget);
  await assert.rejects(app.hosts[0].whenPainted(),/code 4/);
  assert.deepEqual([...app.hosts[0].chart.sourceRowIds].map(Number),last);
  await oracleCanvas.evaluate(c=>c.closest('.xy').xy.applyState({ranges:{x:[0,16383],y:[0,1]},selection:null},{animate:false,history:false}));
  await paint(remounted,'failure-retained-paint.png');await paint(oracleCanvas,'failure-oracle-paint.png');compare('failure-retained-paint.png','failure-oracle-paint.png');
  const failures=[{kind:'budget',error:String(app.hosts[0].lastError)}];
  const {openSync,closeSync,writeSync,ftruncateSync,unlinkSync}=await import('node:fs');
  for(const [kind,range] of [['corrupt',[0,20]],['partial',[0,21]]]) {
    const fd=openSync(path,'r+'),dataOffset=64+128*48;
    try {if(kind==='corrupt'){const bytes=Buffer.alloc(8);bytes.writeDoubleLE(99);writeSync(fd,bytes,0,8,dataOffset);}else ftruncateSync(fd,dataOffset+3);}finally{closeSync(fd);}
    writeFileSync(join(directory,kind+'-source.xygc'),readFileSync(path));
    const count=await page.evaluate(()=>globalThis.failures.length);
    await remounted.evaluate((c,x)=>c.closest('.xy').xy.applyState({ranges:{x,y:[0,1]}},{animate:false,history:false}),range);
    await page.waitForFunction(n=>globalThis.failures.length>n,count);
    assert.deepEqual([...app.hosts[0].chart.sourceRowIds].map(Number),last);
    await oracleCanvas.evaluate((c,x)=>c.closest('.xy').xy.applyState({ranges:{x,y:[0,1]}},{animate:false,history:false}),range);
    await paint(remounted,kind+'-retained-paint.png');await paint(oracleCanvas,kind+'-oracle-paint.png');compare(kind+'-retained-paint.png',kind+'-oracle-paint.png');
    failures.push({kind,error:String(app.hosts[0].lastError)});
  }
  assert.match(failures[1].error,/code 2/);assert.match(failures[2].error,/code 1/);
  // A delayed old mask reaches the real HTTP/renderer route and must not dim this frame.
  await paint(remounted,'before-stale-paint.png');
  const packetCount=await page.locator('#chart').getAttribute('data-packets');
  app.hosts[0].send({type:'selection',chunked_frame:'0',traces:[{id:0,count:1,buf:0}],total:1},[new Uint32Array([0])]);
  await page.waitForFunction(n=>Number(document.querySelector('#chart').dataset.packets)>Number(n),packetCount);
  await paint(remounted,'after-stale-paint.png');compare('before-stale-paint.png','after-stale-paint.png');
  unlinkSync(path);const {ChunkedColumns}=await import('../src/index.js');assert.throws(()=>new ChunkedColumns(path),/cannot open/);
  assert.deepEqual([...app.hosts[0].chart.sourceRowIds].map(Number),last);
  assert.deepEqual(errors,[]);assert.deepEqual(external,[]);
  const report={ok:true,journey:'public Node liveHost over binary HTTP with native async reads',ranges,expected,clicks,selections,frames:await page.evaluate(()=>globalThis.__chunkedFrames),failures:await page.evaluate(()=>globalThis.failures),memory:app.hosts[0].memoryReport(),serialization:app.lanes.map(l=>({peak:l.serializedPeak,queued:l.queue.length,queuedHighWater:l.queuedPeak,replyQueueLimit:16,frameByteLimit:8<<20})),oldOverviewControlDiffers:true,zeroDetailOverview:true,cacheRevisit,pixelOracle:true,failedStageRejected:true,lassoSourceOracle:true,boxSourceOracle:true,failurePixelOracles:failures,staleMaskRejected:true,missingArtifactRejected:true,historyRestored:true,remount:true,errors,external,browser:browser.version()};
  writeFileSync(join(directory,'report.json'),JSON.stringify(report,null,2));
  if(process.env.XYG_CHUNKED_HTTP_REPORT){const {cpSync}=await import('node:fs');cpSync(directory,process.env.XYG_CHUNKED_HTTP_REPORT,{recursive:true});}
 }finally{await browser?.close();await app.close();if(!process.env.XYG_CHUNKED_HTTP_REPORT)rmSync(directory,{recursive:true,force:true});}
});
