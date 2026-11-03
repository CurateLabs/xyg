// DIAGNOSTIC ONLY: selected unchanged 25d captures, never substitute product proof.
// Actual-browser projection regression. Python producer supplies authored Rust
// Scenes and ordinary host payloads; no plot positions/layout are supplied here.
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import fs from 'node:fs';
import { createServer } from 'node:http';
import path from 'node:path';
import { chromium } from 'playwright';
const root=process.cwd(), inputs=path.resolve(process.argv[2]), output=path.resolve(process.argv[3]);
assert.ok(process.argv[2] && process.argv[3], 'supply inputs and fresh output directories');
fs.mkdirSync(output,{recursive:true});
const cases=JSON.parse(fs.readFileSync(path.join(inputs,'cases.json'))).filter(r=>['w1-top-right-opaque','w0-top-right-transparent','w1-top-right-alpha'].includes(r.name));
const server=createServer((req,res)=>{
 const url=new URL(req.url,'http://localhost').pathname;
 if(url==='/'){res.setHeader('Content-Type','text/html');res.end('<!doctype html><style>body{margin:0}</style><div id="chart"></div>');return;}
 const directory=url.startsWith('/inputs/')?inputs:path.join(root,'packages/xy-client/dist');
 const name=path.basename(url);
 try{const bytes=fs.readFileSync(name==='index.js'?path.resolve('target/task-tmp/axis-eligibility-25d-assets/index.js'):path.join(directory,name));res.setHeader('Content-Type',name.endsWith('.wasm')?'application/wasm':name.endsWith('.js')?'text/javascript':name.endsWith('.json')?'application/json':'application/octet-stream');res.end(bytes);}catch{res.writeHead(404);res.end();}
});
await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
const origin=`http://127.0.0.1:${server.address().port}`;
const browser=await chromium.launch({executablePath:process.env.XYG_CHROMIUM,args:['--use-angle=swiftshader','--enable-unsafe-swiftshader','--no-sandbox','--hide-scrollbars']});
const results={browser:browser.version(),dprs:[1.25,2],cases:[],failures:[],layoutOverrides:null,masks:[],geometryToleranceCssPixels:0.01};
const check=(name,fn)=>{try{fn();}catch(error){results.failures.push({name,message:error.message});}};
const close=(actual,expected,label)=>assert.ok(Math.abs(actual-expected)<=0.01,`${label}: ${actual} != ${expected}`);
function geometry(record,resolved){
 const p=record.plot;
 for(const e of record.axes){
  const axis=record.axisSpec[e.axis], width=resolved?Math.max(0,Number(axis.style.axis_width)):Math.max(1,Number(axis.style?.axis_width??1));
  const high=e.side==='bottom'||e.side==='right', vertical=e.axis.startsWith('y');
  const edge=vertical?p.x+(high?p.w:0):p.y+(high?p.h:0);
  const origin=edge-(resolved?width/2:high?width:0);
  close(e.box.x,vertical?origin:p.x,`${e.axis} ${e.side} x`);
  close(e.box.y,vertical?p.y:origin,`${e.axis} ${e.side} y`);
  close(e.box.width,vertical?width:p.w,`${e.axis} width`);
  close(e.box.height,vertical?p.h:width,`${e.axis} height`);
  assert.equal(e.computed.backgroundColor,e.resolvedPaint);
 }
}
try{
 for(const dpr of results.dprs){
  const page=await browser.newPage({viewport:{width:320,height:240},deviceScaleFactor:dpr});
  const errors=[];page.on('pageerror',e=>errors.push(String(e)));
  await page.goto(origin);
  await page.evaluate(async()=>{window.client=await import('/index.js');window.worker=window.client.createXygWasmWorker({workerUrl:'/wasm-worker.js',wasm:'/xyg-wasm.wasm'});await window.worker.ready;});
  for(const item of cases){
   for(const lane of ['resolved','ordinary']){
    const record=await page.evaluate(async({item,lane})=>{
     const el=document.getElementById('chart');el.replaceChildren();Object.assign(el.style,{width:'320px',height:'240px',position:'relative'});
     let view;
     if(lane==='resolved')view=await window.client.renderWasmScene({el,worker:window.worker,scene:await(await fetch(`/inputs/${item.name}.scene`)).arrayBuffer()});
     else{const spec=await(await fetch(`/inputs/${item.name}.json`)).json();spec.wasm_ticks={workerUrl:'/wasm-worker.js',wasm:'/xyg-wasm.wasm'};view=window.client.renderStandalone(el,spec,await(await fetch(`/inputs/${item.name}.bin`)).arrayBuffer());}
     window.view=view;
     await new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)));
     view._layout();view._drawNow();view._raf=null;
     const root=el.getBoundingClientRect();
     const axes=()=>[...el.querySelectorAll('[data-xy-slot="axis_line"]')].map(e=>{
      const r=e.getBoundingClientRect(),s=getComputedStyle(e),probe=document.createElement('span');probe.style.color=e.style.getPropertyValue('--xy-axis-rule-paint');el.appendChild(probe);const paint=getComputedStyle(probe).color;probe.remove();
      return {axis:e.dataset.xyAxis,side:e.dataset.xyAxisSide,box:{x:r.x-root.x,y:r.y-root.y,width:r.width,height:r.height},inline:{left:e.style.left,top:e.style.top,width:e.style.width,height:e.style.height},privateWidth:e.style.getPropertyValue('--xy-axis-rule-width'),privateHeight:e.style.getPropertyValue('--xy-axis-rule-height'),computed:{backgroundColor:s.backgroundColor,transform:s.transform,borderWidth:s.borderWidth,opacity:s.opacity},resolvedPaint:paint,className:e.getAttribute('class')};
     });
     const spines=()=>[...el.querySelectorAll('[data-xy-resolved-spine]')].map(e=>({axis:e.dataset.xyResolvedSpine,side:e.dataset.xySpineSide,attributes:Object.fromEntries([...e.firstElementChild.attributes].map(a=>[a.name,a.value])),boxPaint:el.querySelector(`[data-xy-slot="axis_line"][data-xy-axis="${e.dataset.xyResolvedSpine}"][data-xy-axis-side="${e.dataset.xySpineSide}"]`).dataset.xySpinePaint}));
     const snapshot=()=>({plot:{...view.plot},axes:axes(),axisSpec:structuredClone(view.axes),dpr:devicePixelRatio,viewDpr:view.dpr,...(lane==='resolved'?{spines:spines()}:{})});
     const initial=snapshot();
     if(item.name==='w1-bottom-left-opaque'){
      // Consumer-extension seam: clone already Rust-resolved axis descriptors
      // into extra X/Y registrations. No layout/ticks/positions are invented.
      const originalPlot={...view.plot};
      for(const [id,from,side] of [['x2','x','top'],['y3','y','right']]){
       const axis={...structuredClone(view.axes[from]),id,side};view.axes[id]=axis;view.spec.axes[id]=axis;view.view.ranges[id]=[...view.view.ranges[from]];
      }
      view._drawChrome();initial.extra=snapshot();initial.extra.originalPlot=originalPlot;
      for(const id of ['x2','y3']){delete view.axes[id];delete view.spec.axes[id];delete view.view.ranges[id];}
      const savedDom=view.spec.dom,style=document.createElement('style');style.textContent='.axis-probe{width:7px;height:9px;background:rgb(1,2,3)}';document.head.appendChild(style);
      view.spec.dom={class_names:{axis_line:'axis-probe'}};view._drawChrome();initial.classOverride=snapshot();
      view.spec.dom={class_names:{axis_line:'axis-probe'},styles:{axis_line:{width:13,height:15,left:17,top:19,background:'rgb(4,5,6)'}}};view._drawChrome();initial.inlineOverride=snapshot();
      view.spec.dom=savedDom;style.remove();view._drawChrome();
     }
     return initial;
    },{item,lane});
    const key=`${item.name}.dpr${dpr}.${lane}`;
    check(key,()=>{
     assert.equal(record.dpr,dpr);assert.equal(record.viewDpr,dpr);geometry(record,lane==='resolved');
     if(item.name!=='hidden')assert.equal(record.axes.length,item.sides==='bottom-left'?3:2);
     if(lane==='resolved')for(const state of [record,record.extra,record.classOverride,record.inlineOverride].filter(Boolean)){
      assert.equal(state.spines.length,state.axes.length);
      for(const spine of state.spines){
       const box=state.axes.find(e=>e.axis===spine.axis&&e.side===spine.side).box,a=spine.attributes,vertical=spine.axis.startsWith('y');
       assert.equal(spine.boxPaint,'svg');assert.equal(a['stroke-linecap'],'butt');
       close(Number(a.x1),box.x+(vertical?box.width/2:0),'stroke x1');close(Number(a.x2),box.x+(vertical?box.width/2:box.width),'stroke x2');
       close(Number(a.y1),box.y+(vertical?0:box.height/2),'stroke y1');close(Number(a.y2),box.y+(vertical?box.height:box.height/2),'stroke y2');
       close(Number(a['stroke-width']),vertical?box.width:box.height,'stroke width');
      }
     }
     if(record.extra){geometry(record.extra,lane==='resolved');assert.deepEqual(record.extra.plot,record.extra.originalPlot);assert.ok(record.extra.axes.some(e=>e.axis==='x2'));assert.ok(record.extra.axes.some(e=>e.axis==='y3'));}
     if(record.classOverride){
      for(let i=0;i<record.axes.length;i++){const a=record.axes[i],b=record.classOverride.axes[i];assert.equal(b.className,'axis-probe');close(b.box.width,7,'class width');close(b.box.height,9,'class height');assert.equal(b.inline.left,a.inline.left);assert.equal(b.inline.top,a.inline.top);assert.equal(b.computed.backgroundColor,'rgb(1, 2, 3)');}
      for(const e of record.inlineOverride.axes){assert.equal(e.className,'axis-probe');assert.deepEqual(e.box,{x:17,y:19,width:13,height:15});assert.equal(e.computed.backgroundColor,'rgb(4, 5, 6)');}
     }
    });
    if(lane==='resolved'||['w1-bottom-left-opaque','w0.5-top-right-alpha','w0-bottom-left-opaque','hidden'].includes(item.name)){
     await page.locator('#chart').screenshot({path:path.join(output,`${key}.png`)});
    }
    if(lane==='resolved'){
     // Actual independent native export in a browser image, never a supplied
     // plot or replacement geometry for the product chart.
     await page.evaluate(async name=>{
      const img=document.createElement('img');img.id='canonical';img.width=320;img.height=240;img.style.cssText='display:block;width:320px;height:240px';
      img.src=URL.createObjectURL(new Blob([await(await fetch(`/inputs/${name}.svg`)).text()],{type:'image/svg+xml'}));
      document.body.appendChild(img);await img.decode();
     },item.name);
     await page.locator('#canonical').screenshot({path:path.join(output,`${key}.native-svg.png`)});
     await page.evaluate(()=>{const img=document.getElementById('canonical');URL.revokeObjectURL(img.src);img.remove();});
    }
    results.cases.push({key,item,lane,...record});
    await page.evaluate(()=>window.view.destroy());
   }
  }
  check(`DPR ${dpr} browser errors`,()=>assert.deepEqual(errors,[]));await page.evaluate(()=>window.worker.dispose());await page.close();
 }
}finally{await browser.close();server.close();}
results.artifacts=Object.fromEntries(fs.readdirSync(output).filter(n=>n.endsWith('.png')).map(n=>[n,createHash('sha256').update(fs.readFileSync(path.join(output,n))).digest('hex')]));
fs.writeFileSync(path.join(output,'matrix.json'),JSON.stringify(results,null,2)+'\n');
console.log(JSON.stringify({cases:results.cases.length,failures:results.failures},null,2));
if(results.failures.length)process.exitCode=1;
