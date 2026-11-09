#!/usr/bin/env node
// Actual JupyterLab/kernel/anywidget bridge. No external servers or data APIs.
import {spawn} from 'node:child_process';
import {mkdtemp,writeFile,cp,mkdir,readFile} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {fileURLToPath} from 'node:url';
import {createServer} from 'node:net';
import {createHash} from 'node:crypto';
import {chromium} from 'playwright';
const hierarchy=process.env.XYG_GEO_HIERARCHY==='1',serverUrl=process.env.XYG_GEO_JUPYTER_URL;
if(hierarchy&&process.env.XYG_GEO_INDEXED==='1')throw Error('select one explicit indexed or hierarchy producer');
const root=fileURLToPath(new URL('../',import.meta.url)),temp=await mkdtemp(join(tmpdir(),'xyg-notebook-host-'));
await cp(join(root,hierarchy?'tests/notebook_geo_mounted_hierarchy_temporal.ipynb':process.env.XYG_GEO_INDEXED==='1'?'tests/notebook_geo_mounted_indexed_temporal.ipynb':'tests/notebook_geo_mounted_temporal.ipynb'),join(temp,'geographic.ipynb'));
const inputNotebook=await readFile(join(temp,'geographic.ipynb'));
const notebookSha256=createHash('sha256').update(inputNotebook).digest('hex');
if(serverUrl){const url=new URL(serverUrl);if(url.protocol!=='http:'||!['127.0.0.1','localhost','[::1]'].includes(url.hostname)||url.username||url.password||url.search||url.hash)throw Error('prestarted Jupyter must be an unauthenticated private loopback server');}
const allocator=createServer();await new Promise(r=>allocator.listen(0,'127.0.0.1',r));const port=allocator.address().port;await new Promise(r=>allocator.close(r));
await mkdir(join(temp,'runtime'));await mkdir(join(temp,'config'));await mkdir(join(temp,'data'));
const executable=process.env.XYG_GEO_JUPYTER??join(root,'.venv/bin/jupyter-lab');
const server=serverUrl?null:spawn(executable,['--no-browser','--ServerApp.ip=127.0.0.1',`--ServerApp.port=${port}`,`--ServerApp.root_dir=${temp}`,'--IdentityProvider.token=','--ServerApp.password='],{cwd:root,env:{...process.env,JUPYTER_RUNTIME_DIR:join(temp,'runtime'),JUPYTER_CONFIG_DIR:join(temp,'config'),JUPYTER_DATA_DIR:join(temp,'data'),PYTHONPATH:`${root}/python:${root}/tests`},stdio:['ignore','pipe','pipe']});
let logs='';server?.stdout.on('data',b=>logs+=b);server?.stderr.on('data',b=>logs+=b);
let browser,page; const errors=[],warnings=[];
try{
 const origin=serverUrl?new URL(serverUrl).origin:`http://127.0.0.1:${port}`;
 for(let i=0;i<100;i++){try{const r=await fetch(origin+'/api/status');if(r.ok)break;}catch{}await new Promise(r=>setTimeout(r,100));}
 if(serverUrl){const response=await fetch(origin+'/api/contents/geographic.ipynb?content=1');if(!response.ok)throw Error('prestarted server must serve the exact input as geographic.ipynb');const served=await response.json(),expected=JSON.parse(inputNotebook);if(JSON.stringify(served.content.cells.map(c=>[c.cell_type,Array.isArray(c.source)?c.source.join(''):c.source]))!==JSON.stringify(expected.cells.map(c=>[c.cell_type,Array.isArray(c.source)?c.source.join(''):c.source])))throw Error('prestarted server notebook differs from the committed input');}
 browser=await chromium.launch({...(process.env.XYG_CHROMIUM?{executablePath:process.env.XYG_CHROMIUM}:{}),args:['--use-gl=swiftshader','--enable-unsafe-swiftshader','--ignore-gpu-blocklist']});
 page=await browser.newPage({viewport:{width:1200,height:900}});const external=[];
 await page.route('**/*',route=>{const u=new URL(route.request().url());if(!['http:','https:'].includes(u.protocol)||u.origin===origin)return route.continue();external.push(u.href);return route.abort();});
 page.on('pageerror',e=>errors.push(e.message));page.on('console',m=>{if(m.type()==='error'||m.type()==='warning')warnings.push(m.text());});
 await page.goto(origin+(hierarchy?'/lab/workspaces/hierarchy-'+crypto.randomUUID():'/lab')+'/tree/geographic.ipynb');
 await page.locator('.jp-Notebook .jp-Cell').first().waitFor({timeout:45000});
 const select=page.getByRole('button',{name:'Select'});if(await select.count())await select.click();
 await page.waitForFunction(()=>document.querySelector('.jp-Notebook .cm-content')&&document.body.innerText.includes('Idle'),{},{timeout:45000});
 await page.locator('.jp-Notebook .jp-Cell').first().locator('.cm-content').click();await page.keyboard.press('Shift+Enter');
 const painter=page.locator('.jp-OutputArea canvas[role="img"]').first();
 await painter.waitFor({timeout:45000});
 let red=0;
 for(let attempt=0;attempt<100&&!red;attempt++){
  red=await painter.evaluate((canvas,channel)=>{const ctx=canvas.getContext('2d');let p;if(ctx)p=ctx.getImageData(0,0,canvas.width,canvas.height).data;else{const gl=canvas.getContext('webgl2');if(!gl)return 0;p=new Uint8Array(gl.drawingBufferWidth*gl.drawingBufferHeight*4);gl.readPixels(0,0,gl.drawingBufferWidth,gl.drawingBufferHeight,gl.RGBA,gl.UNSIGNED_BYTE,p);}let count=0;for(let i=0;i<p.length;i+=4)if(p[i+channel]>150&&p[i+1-channel]<100&&p[i+2]<100)count++;return count;},hierarchy?1:0);
  if(!red)await new Promise(r=>setTimeout(r,100));
 }
 if(!red)throw Error('actual notebook painter contains no '+(hierarchy?'selected green':'red')+' points');
 const canvasCount=await page.locator('.jp-OutputArea canvas').count();
 const phasePixels=[],phasePixelHashes=[],trustedKeyboardEvents=[];let hierarchyReport;
 if(hierarchy){
  await painter.evaluate(canvas=>{canvas.ownerDocument.addEventListener('keydown',event=>{if(event.target===canvas&&event.key==='ArrowRight')window.__xygHierarchyKeys=(window.__xygHierarchyKeys||[]).concat([{key:event.key,trusted:event.isTrusted}]);},true);canvas.tabIndex=0;canvas.focus();});
  await page.keyboard.press('ArrowRight');
  trustedKeyboardEvents.push(...await page.evaluate(()=>window.__xygHierarchyKeys||[]));if(!trustedKeyboardEvents.length||trustedKeyboardEvents.some(e=>!e.trusted))throw Error('trusted canvas keyboard input missing');
  const execute=async i=>{await page.locator('.jp-Notebook .jp-Cell').nth(i).locator('.cm-content').click();await page.keyboard.press('Shift+Enter');};
  await execute(1);await page.getByText('XYG aborted hierarchy renderer released',{exact:true}).waitFor({timeout:30000});
  if(await page.locator('.jp-OutputArea canvas').count())throw Error('Output clear retained the old painter');
  await execute(2);await painter.waitFor({timeout:45000});
  for(const [i,marker] of [[3,'XYG hierarchy remount accepted above aborted sequence'],[4,'XYG remounted hierarchy empty range accepted'],[5,'XYG remounted hierarchy restored cursor accepted']]){
   await execute(i);await page.getByText(marker,{exact:true}).waitFor({timeout:30000});await page.waitForTimeout(100);
   const paint=await painter.evaluate(async canvas=>{const ctx=canvas.getContext('2d');let data;if(ctx)data=ctx.getImageData(0,0,canvas.width,canvas.height).data;else{const gl=canvas.getContext('webgl2');data=new Uint8Array(gl.drawingBufferWidth*gl.drawingBufferHeight*4);gl.readPixels(0,0,gl.drawingBufferWidth,gl.drawingBufferHeight,gl.RGBA,gl.UNSIGNED_BYTE,data);}let count=0;for(let at=0;at<data.length;at+=4)if(data[at+1]>150&&data[at]<100&&data[at+2]<100)count++;return {count,sha256:Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',data)),n=>n.toString(16).padStart(2,'0')).join('')};});
   if(i===4?paint.count!==0:paint.count===0)throw Error('unexpected remounted pixels phase '+i+': '+paint.count);
   phasePixels.push(paint.count);phasePixelHashes.push(paint.sha256);
   if(process.env.XYG_GEO_NOTEBOOK_CAPTURE)await page.screenshot({path:process.env.XYG_GEO_NOTEBOOK_CAPTURE.replace('.png','-'+i+'.png')});
  }
  if(phasePixelHashes[0]!==phasePixelHashes[2])throw Error('restored source/camera must restore complete canvas RGBA');
  await execute(6);await page.getByText('XYG remounted hierarchy native cleanup acknowledged',{exact:true}).waitFor({timeout:30000});
  await execute(7);await page.getByText(/^XYG hierarchy remount report /).waitFor({timeout:30000});
  hierarchyReport=JSON.parse((await page.locator('.jp-OutputArea').allTextContents()).join('\n').match(/XYG hierarchy remount report (\{[^\n]+\})/)[1]);
 }else{
 const markers=['XYG mounted time and camera accepted','XYG empty range accepted','XYG rebind and independent caller accepted','XYG geographic browser release acknowledged'];

 for(let i=1;i<=4;i++){
  await page.locator('.jp-Notebook .jp-Cell').nth(i).locator('.cm-content').click();await page.keyboard.press('Shift+Enter');
  await page.getByText(markers[i-1],{exact:true}).waitFor({timeout:30000});
  if(i<4){
   await page.waitForTimeout(100);
   const count=await painter.evaluate(canvas=>{const ctx=canvas.getContext('2d');let p;if(ctx)p=ctx.getImageData(0,0,canvas.width,canvas.height).data;else{const gl=canvas.getContext('webgl2');p=new Uint8Array(gl.drawingBufferWidth*gl.drawingBufferHeight*4);gl.readPixels(0,0,gl.drawingBufferWidth,gl.drawingBufferHeight,gl.RGBA,gl.UNSIGNED_BYTE,p);}let red=0;for(let at=0;at<p.length;at+=4)if(p[at]>150&&p[at+1]<100&&p[at+2]<100)red++;return red;});
   phasePixels.push(count);if(i===2?count!==0:count===0)throw Error('unexpected mounted pixels phase '+i+': '+count);
   if(process.env.XYG_GEO_NOTEBOOK_CAPTURE){await painter.scrollIntoViewIfNeeded();await page.screenshot({path:process.env.XYG_GEO_NOTEBOOK_CAPTURE.replace('.png','-'+i+'.png')});}
  }
 }
 }
 if(errors.length)throw Error('browser page errors '+errors.join(','));
 if(external.length)throw Error('external requests '+external.join(','));
 const kernelEnvironment=process.env.XYG_GEO_INDEXED==='1'?JSON.parse((await page.locator('.jp-OutputArea').allTextContents()).join('\n').match(/XYG indexed environment (\{[^\n]+\})/)[1]):undefined;
 const result={ok:true,notebookSha256,kernelEnvironment:hierarchy?hierarchyReport.kernelEnvironment:kernelEnvironment,hierarchy,hierarchyReport,separatelyStartedServer:!!serverUrl,trustedKeyboardEvents:hierarchy?trustedKeyboardEvents:undefined,phasePixelHashes:hierarchy?phasePixelHashes:undefined,completeRgbaRestored:hierarchy?true:undefined,indexed:process.env.XYG_GEO_INDEXED==='1',selected:hierarchy||process.env.XYG_GEO_INDEXED==='1'&&process.env.XYG_GEO_SELECTED!=='0',journey:'actual JupyterLab + live IPython loop + anywidget binary comm + Rust native painter',mountedTemporal:true,rangeAndCursor:true,cameraPreserved:true,foreignThread:!hierarchy,failureRetained:!hierarchy,preparedAbort:hierarchy,actualOutputClear:hierarchy,actualRedisplay:hierarchy,rebind:true,independentCaller:true,phasePixels,canvasCount,redPixels:hierarchy?undefined:red,selectedGreenPixels:hierarchy?red:undefined,browser:browser.version(),external,errors,warnings,releaseAcknowledged:true};
 if(process.env.XYG_GEO_NOTEBOOK_REPORT)await writeFile(process.env.XYG_GEO_NOTEBOOK_REPORT,JSON.stringify(result,null,2)+'\n');console.log(JSON.stringify(result));
}catch(error){throw Error(JSON.stringify({error:error.message,errors,body:await page?.locator('body').innerText().catch(()=>''),outputs:await page?.locator('.jp-OutputArea').evaluateAll(els=>els.map(el=>el.innerHTML.slice(-6000))).catch(()=>[]),logs:logs.slice(-6000)}));}
finally{await browser?.close();server?.kill('SIGTERM');}
