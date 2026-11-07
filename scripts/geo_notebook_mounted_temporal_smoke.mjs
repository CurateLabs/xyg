#!/usr/bin/env node
// Actual JupyterLab/kernel/anywidget bridge. No external servers or data APIs.
import {spawn} from 'node:child_process';
import {mkdtemp,writeFile,cp,mkdir} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {fileURLToPath} from 'node:url';
import {createServer} from 'node:net';
import {chromium} from 'playwright';
const root=fileURLToPath(new URL('../',import.meta.url)),temp=await mkdtemp(join(tmpdir(),'xyg-notebook-host-'));
await cp(join(root,'tests/notebook_geo_mounted_temporal.ipynb'),join(temp,'geographic.ipynb'));
const allocator=createServer();await new Promise(r=>allocator.listen(0,'127.0.0.1',r));const port=allocator.address().port;await new Promise(r=>allocator.close(r));
await mkdir(join(temp,'runtime'));await mkdir(join(temp,'config'));await mkdir(join(temp,'data'));
const executable=process.env.XYG_GEO_JUPYTER??join(root,'.venv/bin/jupyter-lab');
const server=spawn(executable,['--no-browser','--ServerApp.ip=127.0.0.1',`--ServerApp.port=${port}`,`--ServerApp.root_dir=${temp}`,'--IdentityProvider.token=','--ServerApp.password='],{cwd:root,env:{...process.env,JUPYTER_RUNTIME_DIR:join(temp,'runtime'),JUPYTER_CONFIG_DIR:join(temp,'config'),JUPYTER_DATA_DIR:join(temp,'data'),PYTHONPATH:`${root}/python:${root}/tests`},stdio:['ignore','pipe','pipe']});
let logs='';server.stdout.on('data',b=>logs+=b);server.stderr.on('data',b=>logs+=b);
let browser,page; const errors=[],warnings=[];
try{
 const origin=`http://127.0.0.1:${port}`;
 for(let i=0;i<100;i++){try{const r=await fetch(origin+'/api/status');if(r.ok)break;}catch{}await new Promise(r=>setTimeout(r,100));}
 browser=await chromium.launch({...(process.env.XYG_CHROMIUM?{executablePath:process.env.XYG_CHROMIUM}:{}),args:['--use-gl=swiftshader','--enable-unsafe-swiftshader','--ignore-gpu-blocklist']});
 page=await browser.newPage({viewport:{width:1200,height:900}});const external=[];
 await page.route('**/*',route=>{const u=new URL(route.request().url());if(!['http:','https:'].includes(u.protocol)||u.origin===origin)return route.continue();external.push(u.href);return route.abort();});
 page.on('pageerror',e=>errors.push(e.message));page.on('console',m=>{if(m.type()==='error'||m.type()==='warning')warnings.push(m.text());});
 await page.goto(origin+'/lab/tree/geographic.ipynb');
 await page.locator('.jp-Notebook .jp-Cell').first().waitFor({timeout:45000});
 const select=page.getByRole('button',{name:'Select'});if(await select.count())await select.click();
 await page.waitForFunction(()=>document.querySelector('.jp-Notebook .cm-content')&&document.body.innerText.includes('Idle'),{},{timeout:45000});
 await page.locator('.jp-Notebook .jp-Cell').first().locator('.cm-content').click();await page.keyboard.press('Shift+Enter');
 const painter=page.locator('.jp-OutputArea canvas[role="img"]').first();
 await painter.waitFor({timeout:45000});
 let red=0;
 for(let attempt=0;attempt<100&&!red;attempt++){
  red=await painter.evaluate(canvas=>{const ctx=canvas.getContext('2d');let p;if(ctx)p=ctx.getImageData(0,0,canvas.width,canvas.height).data;else{const gl=canvas.getContext('webgl2');if(!gl)return 0;p=new Uint8Array(gl.drawingBufferWidth*gl.drawingBufferHeight*4);gl.readPixels(0,0,gl.drawingBufferWidth,gl.drawingBufferHeight,gl.RGBA,gl.UNSIGNED_BYTE,p);}let count=0;for(let i=0;i<p.length;i+=4)if(p[i]>150&&p[i+1]<100&&p[i+2]<100)count++;return count;});
  if(!red)await new Promise(r=>setTimeout(r,100));
 }
 if(!red)throw Error('actual notebook painter contains no red points');
 const canvasCount=await page.locator('.jp-OutputArea canvas').count();
 const markers=['XYG mounted time and camera accepted','XYG empty range accepted','XYG rebind and independent caller accepted','XYG geographic browser release acknowledged'];
 const phasePixels=[];
 for(let i=1;i<=4;i++){
  await page.locator('.jp-Notebook .jp-Cell').nth(i).locator('.cm-content').click();await page.keyboard.press('Shift+Enter');
  await page.getByText(markers[i-1],{exact:true}).waitFor({timeout:30000});
  if(i<4){
   await page.waitForTimeout(100);
   const count=await painter.evaluate(canvas=>{const ctx=canvas.getContext('2d');let p;if(ctx)p=ctx.getImageData(0,0,canvas.width,canvas.height).data;else{const gl=canvas.getContext('webgl2');p=new Uint8Array(gl.drawingBufferWidth*gl.drawingBufferHeight*4);gl.readPixels(0,0,gl.drawingBufferWidth,gl.drawingBufferHeight,gl.RGBA,gl.UNSIGNED_BYTE,p);}let red=0;for(let at=0;at<p.length;at+=4)if(p[at]>150&&p[at+1]<100&&p[at+2]<100)red++;return red;});
   phasePixels.push(count);if(i===2?count!==0:count===0)throw Error('unexpected mounted pixels phase '+i+': '+count);
   if(process.env.XYG_GEO_NOTEBOOK_CAPTURE)await page.screenshot({path:process.env.XYG_GEO_NOTEBOOK_CAPTURE.replace('.png','-'+i+'.png')});
  }
 }
 if(errors.length)throw Error('browser page errors '+errors.join(','));
 if(external.length)throw Error('external requests '+external.join(','));
 const result={ok:true,journey:'actual JupyterLab + live IPython loop + anywidget binary comm + Rust native painter',mountedTemporal:true,rangeAndCursor:true,cameraPreserved:true,foreignThread:true,failureRetained:true,rebind:true,independentCaller:true,phasePixels,canvasCount,redPixels:red,browser:browser.version(),external,errors,warnings,releaseAcknowledged:true};
 if(process.env.XYG_GEO_NOTEBOOK_REPORT)await writeFile(process.env.XYG_GEO_NOTEBOOK_REPORT,JSON.stringify(result,null,2)+'\n');console.log(JSON.stringify(result));
}catch(error){throw Error(JSON.stringify({error:error.message,errors,body:await page?.locator('body').innerText().catch(()=>''),outputs:await page?.locator('.jp-OutputArea').evaluateAll(els=>els.map(el=>el.innerHTML.slice(-6000))).catch(()=>[]),logs:logs.slice(-6000)}));}
finally{await browser?.close();server.kill('SIGTERM');}
