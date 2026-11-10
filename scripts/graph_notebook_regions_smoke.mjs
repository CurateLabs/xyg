#!/usr/bin/env node
// Actual notebook/anywidget transport; all gestures below are trusted input.
import assert from 'node:assert/strict';
import {spawn} from 'node:child_process';
import {cp, mkdir, mkdtemp, writeFile} from 'node:fs/promises';
import {createServer} from 'node:net';
import {join} from 'node:path';
import {fileURLToPath} from 'node:url';
import {chromium} from 'playwright';
import {namedIdleKernel} from './graph_notebook_kernel_witness.mjs';
import {runGraphNotebookRegions,installGraphRegionHooks} from './graph_notebook_region_journey.mjs';

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

try{
 for(let i=0;i<100;i++){if(startupError)throw startupError;try{if((await fetch(origin+'/api/status')).ok)break;}catch{}await new Promise(r=>setTimeout(r,100));}
 browser=await chromium.launch({...(process.env.XYG_CHROMIUM?{executablePath:process.env.XYG_CHROMIUM}:{}),
  args:['--use-gl=swiftshader','--enable-unsafe-swiftshader','--ignore-gpu-blocklist']});
 page=await browser.newPage({viewport:{width:1200,height:1000},deviceScaleFactor:dpr});
 page.on('pageerror',e=>errors.push(e.message));
 await page.route('**/*',route=>{const u=new URL(route.request().url());
  if(!['http:','https:'].includes(u.protocol)||u.origin===origin)return route.continue();
  external.push(u.href);return route.abort();});
 await page.addInitScript(installGraphRegionHooks);
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
 const surfaces=page.locator('.jp-OutputArea [data-graph-steps]');
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
 const cleanup=()=>page.locator('.jp-Notebook .jp-Cell').nth(3).locator('.jp-OutputArea').getByText('XYG graph region cleanup',{exact:false}).waitFor({timeout:10000});
 const result=await runGraphNotebookRegions({root,temp,page,surfaces,cell,report,cleanup,frontend,kernel,dpr,browser,errors,external});
 await writeFile(join(temp,'report.json'),JSON.stringify(result,null,2)+'\n');
 if(process.env.XYG_GRAPH_REGION_REPORT)await writeFile(process.env.XYG_GRAPH_REGION_REPORT,JSON.stringify(result,null,2)+'\n');
 console.log(JSON.stringify({ok:true,artifactDir:temp,nodes:result.lassoExpected.nodes,edges:result.lassoExpected.edges,dpr}));
}catch(error){await writeFile(join(temp,'failure.json'),JSON.stringify({error:error.stack,logs,errors,body:await page?.locator('body').innerText().catch(()=>''),events:await page?.evaluate(()=>globalThis.__regionEvents).catch(()=>[])},null,2));throw error;}
finally{await browser?.close();server.kill('SIGTERM');}
