#!/usr/bin/env node
// Actual JupyterLab/kernel/anywidget bridge. No external servers or data APIs.
import {spawn} from 'node:child_process';
import {mkdtemp,writeFile,cp,mkdir} from 'node:fs/promises';
import {join} from 'node:path';
import {fileURLToPath} from 'node:url';
import {createServer} from 'node:net';
import {chromium} from 'playwright';
const root=fileURLToPath(new URL('../',import.meta.url)),temp=await mkdtemp(join(root,'target/xyg-graph-notebook-'));
await cp(join(root,'tests/notebook_graph_progressive.ipynb'),join(temp,'graph.ipynb'));
const allocator=createServer();await new Promise(r=>allocator.listen(0,'127.0.0.1',r));const port=allocator.address().port;await new Promise(r=>allocator.close(r));
await mkdir(join(temp,'runtime'));await mkdir(join(temp,'config'));await mkdir(join(temp,'data'));
const executable=process.env.XYG_GRAPH_JUPYTER??join(root,'.venv/bin/jupyter-lab');
const server=spawn(executable,['--no-browser','--ServerApp.ip=127.0.0.1',`--ServerApp.port=${port}`,`--ServerApp.root_dir=${temp}`,'--IdentityProvider.token=','--ServerApp.password='],{cwd:root,env:{...process.env,JUPYTER_RUNTIME_DIR:join(temp,'runtime'),JUPYTER_CONFIG_DIR:join(temp,'config'),JUPYTER_DATA_DIR:join(temp,'data'),PYTHONPATH:`${root}/python:${root}/tests`},stdio:['ignore','pipe','pipe']});
let logs='';server.stdout.on('data',b=>logs+=b);server.stderr.on('data',b=>logs+=b);
let browser,page; const errors=[];
try{
 const origin=`http://127.0.0.1:${port}`;
 for(let i=0;i<100;i++){try{const r=await fetch(origin+'/api/status');if(r.ok)break;}catch{}await new Promise(r=>setTimeout(r,100));}
 browser=await chromium.launch({...(process.env.XYG_CHROMIUM?{executablePath:process.env.XYG_CHROMIUM}:{}),args:['--use-gl=swiftshader','--enable-unsafe-swiftshader','--ignore-gpu-blocklist']});
 page=await browser.newPage({viewport:{width:1200,height:900}});const external=[];
 await page.route('**/*',route=>{const u=new URL(route.request().url());if(!['http:','https:'].includes(u.protocol)||u.origin===origin)return route.continue();external.push(u.href);return route.abort();});
 page.on('pageerror',e=>errors.push(e.message));page.on('console',m=>{if(m.type()==='error'||m.type()==='warning')errors.push(m.text());});
 await page.addInitScript(()=>{
  globalThis.__graphFrames=[];
  new MutationObserver(records=>{for(const record of records){
   const el=record.target;if(!(el instanceof HTMLElement)||!el.hasAttribute('data-graph-steps'))continue;
   const canvas=el.querySelector('canvas'),step=el.getAttribute('data-graph-steps');
   if(globalThis.__graphFrames.at(-1)?.step===step)continue;
   const p=canvas?.getContext('2d')?.getImageData(0,0,canvas.width,canvas.height).data;
   let painted=0;if(p)for(let i=0;i<p.length;i+=4)if(p[i+3])painted++;
   globalThis.__graphFrames.push({step,painted,time:performance.now()});
  }}).observe(document,{subtree:true,attributes:true,attributeFilter:['data-graph-steps']});
 });
 await page.goto(origin+'/lab/tree/graph.ipynb');
 await page.locator('.jp-Notebook .jp-Cell').first().waitFor({timeout:45000});
 const select=page.getByRole('button',{name:'Select'});if(await select.count())await select.click();
 await page.waitForFunction(()=>document.querySelector('.jp-Notebook .cm-content')&&document.body.innerText.includes('Idle'),{},{timeout:45000});
 await page.locator('.jp-Notebook .jp-Cell').first().locator('.cm-content').click();await page.keyboard.press('Shift+Enter');
 const surface=page.locator('.jp-OutputArea [data-graph-steps]').first();
 await surface.waitFor({timeout:45000});
 const firstSteps=await surface.getAttribute('data-graph-steps');
 await page.locator('.jp-Notebook .jp-Cell').nth(1).locator('.cm-content').click();await page.keyboard.press('Shift+Enter');
 await page.getByText('XYG graph kernel responsive',{exact:true}).waitFor({timeout:20000});
 await page.getByText('Layout complete',{exact:true}).waitFor({timeout:45000});
 const finalSteps=await surface.getAttribute('data-graph-steps');
 const canvas=surface.locator('canvas');
 const dimensions=await canvas.evaluate(c=>{const p=c.getContext('2d').getImageData(0,0,c.width,c.height).data;let painted=0;for(let i=0;i<p.length;i+=4)if(p[i+3]>0)painted++;return {width:c.width,height:c.height,painted};});
 if(!dimensions.width||!dimensions.height||!dimensions.painted||Number(finalSteps)<=1)throw Error('no progressive native paint');
 await page.locator('.jp-Notebook .jp-Cell').nth(2).locator('.cm-content').click();await page.keyboard.press('Shift+Enter');
 await page.getByText('XYG graph disposed',{exact:true}).waitFor({timeout:20000});
 if(external.length)throw Error('external requests '+external.join(','));
 const frames=await page.evaluate(()=>globalThis.__graphFrames);
 if(frames[0]?.step!=='1'||!frames[0]?.painted)throw Error('missing initial one-tick native paint');
 const result={frames,ok:true,journey:'actual JupyterLab/IPython/anywidget/native retained graph',firstSteps,finalSteps,dimensions,browser:browser.version(),external,errors};
 if(process.env.XYG_GRAPH_NOTEBOOK_REPORT)await writeFile(process.env.XYG_GRAPH_NOTEBOOK_REPORT,JSON.stringify(result,null,2)+'\n');console.log(JSON.stringify(result));
}catch(error){throw Error(JSON.stringify({error:error.message,errors,body:await page?.locator('body').innerText().catch(()=>''),outputs:await page?.locator('.jp-OutputArea').evaluateAll(els=>els.map(el=>el.innerHTML.slice(-6000))).catch(()=>[]),logs:logs.slice(-6000)}));}
finally{await browser?.close();server.kill('SIGTERM');}
