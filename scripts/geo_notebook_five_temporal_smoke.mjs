#!/usr/bin/env node
// Installed JupyterLab + real anywidget binary comms. Source-checkout qualification.
import assert from 'node:assert/strict';
import {spawn} from 'node:child_process';
import {mkdtemp,writeFile,cp,mkdir,readFile} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {fileURLToPath} from 'node:url';
import {createServer} from 'node:net';
import {createHash} from 'node:crypto';
import {chromium} from 'playwright';
const root=fileURLToPath(new URL('../',import.meta.url)),temp=await mkdtemp(join(tmpdir(),'xyg-five-notebook-')),artifacts=process.env.XYG_GEO_ARTIFACT_DIR??join(root,'target/task-tmp/five-temporal-successor');
await cp(join(root,'tests/notebook_geo_five_temporal.ipynb'),join(temp,'geographic.ipynb'));
for(const name of ['runtime','config','data','ipython'])await mkdir(join(temp,name));
const kernelDir=join(temp,'data/kernels/python3');await mkdir(kernelDir,{recursive:true});
const python=process.env.XYG_GEO_JUPYTER_PYTHON;if(!python)throw Error('set explicit verified Jupyter Python interpreter');
await writeFile(join(kernelDir,'kernel.json'),JSON.stringify({argv:[python,'-m','ipykernel_launcher','-f','{connection_file}'],display_name:'Python 3 (ipykernel)',language:'python'}));
const allocator=createServer();await new Promise(r=>allocator.listen(0,'127.0.0.1',r));const port=allocator.address().port;await new Promise(r=>allocator.close(r));
const server=spawn(python,['-m','jupyterlab','--no-browser','--ServerApp.ip=127.0.0.1',`--ServerApp.port=${port}`,`--ServerApp.root_dir=${temp}`,'--IdentityProvider.token=','--ServerApp.password='],{cwd:root,env:{...process.env,PYTHONDONTWRITEBYTECODE:'1',JUPYTER_RUNTIME_DIR:join(temp,'runtime'),JUPYTER_CONFIG_DIR:join(temp,'config'),JUPYTER_DATA_DIR:join(temp,'data'),JUPYTER_PATH:join(temp,'data'),IPYTHONDIR:join(temp,'ipython'),PYTHONPATH:`${root}/python:${root}/tests`},stdio:['ignore','pipe','pipe']});
let logs='',browser,page;server.stdout.on('data',b=>logs+=b);server.stderr.on('data',b=>logs+=b);const errors=[];
try{
 const origin=`http://127.0.0.1:${port}`;for(let i=0;i<100;i++){try{if((await fetch(origin+'/api/status')).ok)break;}catch{}await new Promise(r=>setTimeout(r,100));}
 browser=await chromium.launch({executablePath:process.env.XYG_CHROMIUM,args:['--use-angle=swiftshader','--enable-unsafe-swiftshader','--ignore-gpu-blocklist']});page=await browser.newPage({viewport:{width:1200,height:1000}});page.on('pageerror',e=>errors.push(e.message));
 await page.goto(origin+'/lab/tree/geographic.ipynb');await page.locator('.jp-Notebook .jp-Cell').first().waitFor({timeout:45000});const select=page.getByRole('button',{name:'Select'});if(await select.count())await select.click();await page.waitForFunction(()=>document.querySelector('.jp-Notebook .cm-content')&&document.body.innerText.includes('Idle'),{},{timeout:45000});
 const execute=async i=>{await page.locator('.jp-Notebook .jp-Cell').nth(i).locator('.cm-content').click();await page.keyboard.press('Shift+Enter');};
 const marker=async text=>{await page.waitForFunction(text=>Array.from(document.querySelectorAll('.jp-OutputArea'),e=>e.innerText).some(t=>t.includes(text)||t.includes('ERROR ')),text,{timeout:45000});const body=(await page.locator('.jp-OutputArea').allTextContents()).join('\n');assert.ok(!body.includes('ERROR '),body);assert.ok(body.includes(text));};
 const painters=()=>page.locator('.jp-OutputArea canvas[role="img"]');
 const pixels=async()=>{assert.equal(await painters().count(),5);const result=[];for(let i=0;i<5;i++)result.push(await painters().nth(i).evaluate(async canvas=>{await new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)));const ctx=canvas.getContext('2d'),bytes=ctx.getImageData(0,0,canvas.width,canvas.height).data;return {sha256:Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',bytes)),n=>n.toString(16).padStart(2,'0')).join(''),colored:[...bytes].filter((_,i)=>i%4===0&&bytes[i+1]>150&&bytes[i]<100&&bytes[i+2]<100).length};}));return result;};
 await execute(0);await marker('XYG five ready');const initial=await pixels();assert.ok(initial.every(p=>p.colored>0));assert.deepEqual(await pixels(),initial);
 await execute(1);await marker('XYG five prepared held');assert.deepEqual(await pixels(),initial);await execute(2);await marker('XYG five latest');assert.deepEqual(await pixels(),initial);
 let cameraStep=0;for(let i=0;i<5;i++){
  for(let n=0;n<=i;n++){await painters().nth(i).scrollIntoViewIfNeeded();await painters().nth(i).evaluate(canvas=>{canvas.tabIndex=0;canvas.focus();});await page.keyboard.press('ArrowRight');await execute(3);await marker('XYG five camera '+(++cameraStep));}
 }
 const cameras=await pixels();await page.screenshot({path:join(artifacts,'jupyter-five-cameras.png'),fullPage:true});
 await execute(4);await marker('XYG five released');assert.equal(await painters().count(),0);
 await execute(5);await marker('XYG five remounted');assert.deepEqual(await pixels(),cameras);
 await execute(6);await marker('XYG five native cleanup acknowledged');assert.equal(await painters().count(),0);await execute(7);await page.getByText(/^XYG five report /).waitFor({timeout:30000});
 const outputs=(await page.locator('.jp-OutputArea').allTextContents()).join('\n'),report=JSON.parse(outputs.match(/XYG five report (\{[^\n]+\})/)[1]);assert.equal(errors.length,0);report.initial=initial;report.remount=cameras;report.errors=errors;report.browser=browser.version();report.notebookSha256=createHash('sha256').update(await readFile(join(temp,'geographic.ipynb'))).digest('hex');report.temp=temp;
 await writeFile(join(artifacts,'jupyter-five-report.json'),JSON.stringify(report,null,2)+'\n');console.log(JSON.stringify(report));
}catch(error){await page?.screenshot({path:join(artifacts,'jupyter-five-failure.png'),fullPage:true}).catch(()=>{});console.error(JSON.stringify({error:error.stack,errors,temp,body:await page?.locator('body').innerText().catch(()=>''),logs:logs.slice(-12000)}));process.exitCode=1;}
finally{await browser?.close();server.kill('SIGTERM');await writeFile(join(artifacts,'jupyter-server.log'),logs);}
