import fs from 'node:fs';
import path from 'node:path';
import {createServer} from 'node:http';
import {chromium} from 'playwright';
const child='/home/ubuntu/.t3/worktrees/xyg/t3-42669f21';
const receipt=path.join(child,'spec/performance/graph-resolved-scene-consumer-repair-2026-11-03');
const dist=path.join(child,'packages/xy-client/dist');
const baseline=path.join(child,'target/task-tmp/resolved-spine-188f-baseline/packages/xy-client/dist');
const server=createServer((req,res)=>{try{if(req.url==='/'){res.setHeader('Content-Type','text/html');res.end('<!doctype html><style>body{margin:0}</style><div id="chart"></div>');return;}const name=path.basename(req.url);const source=name==='slot.scene'?path.join(receipt,name):path.join(req.url.startsWith('/before/')?baseline:dist,name);res.setHeader('Content-Type',name.endsWith('.js')?'text/javascript':name.endsWith('.wasm')?'application/wasm':'application/octet-stream');res.end(fs.readFileSync(source));}catch{res.writeHead(404);res.end();}});
await new Promise(r=>server.listen(0,'127.0.0.1',r));
const browser=await chromium.launch({executablePath:'/home/ubuntu/.cache/ms-playwright/chromium-1248/chrome-linux64/chrome',args:['--no-sandbox','--use-angle=swiftshader','--enable-unsafe-swiftshader']});
const results=[];
try{for(const lane of ['before','after']){
 const page=await browser.newPage({viewport:{width:320,height:240}});await page.goto(`http://127.0.0.1:${server.address().port}/`);
 const state=await page.evaluate(async lane=>{const client=await import(lane==='before'?'/before/index.js':'/index.js');window.worker=client.createXygWasmWorker({workerUrl:'/wasm-worker.js',wasm:'/xyg-wasm.wasm'});await worker.ready;const el=document.getElementById('chart');Object.assign(el.style,{width:'320px',height:'240px',position:'relative'});window.view=await client.renderWasmScene({el,worker,scene:await(await fetch('/slot.scene')).arrayBuffer()});const style=document.createElement('style');style.textContent='.pointer-probe[data-xy-axis^="y"]{display:none}.pointer-probe:hover{outline:2px solid blue}';document.head.appendChild(style);view.spec.dom={class_names:{axis_line:'pointer-probe'},styles:{axis_line:{left:17,top:19,width:80,height:8,background:'red','pointer-events':'auto','z-index':99}}};view.refreshTheme();await new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)));window.clicked=0;const slot=view.labels.querySelector('[data-xy-axis="x"][data-xy-slot="axis_line"]');slot.addEventListener('click',()=>window.clicked++);const hit=document.elementFromPoint(22,22);return {box:slot.getBoundingClientRect().toJSON(),hitTag:hit?.tagName,hitClass:hit?.className,hitHTML:hit?.outerHTML?.slice(0,250),stack:document.elementsFromPoint(22,22).map(e=>({tag:e.tagName,slot:e.dataset.xySlot,cls:String(e.className)})),paint:slot.dataset.xySpinePaint??'html',clip:getComputedStyle(slot).clipPath,pointerEvents:getComputedStyle(slot).pointerEvents,hitPublicSlot:hit===slot};},lane);
 await page.mouse.move(22,22);await page.mouse.click(22,22);
 const outcome=await page.evaluate(()=>({clicks:window.clicked,hover:!!view.labels.querySelector('[data-xy-slot="axis_line"]:hover')}));results.push({lane,...state,...outcome});await page.evaluate(()=>{view.destroy();worker.dispose();});await page.close();
}}finally{await browser.close();server.close();}
fs.writeFileSync('target/task-tmp/axis-pointer-review/observations-v3.json',JSON.stringify(results,null,2)+'\n');console.log(JSON.stringify(results));
