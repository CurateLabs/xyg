#!/usr/bin/env node
// Actual browser CSS conversion and existing mark/legend paint, with native-built fixtures.
import assert from 'node:assert/strict';
import {createServer} from 'node:http';
import {readFile,writeFile} from 'node:fs/promises';
import {fileURLToPath} from 'node:url';
import {createHash} from 'node:crypto';
import {chromium} from 'playwright';
const root=fileURLToPath(new URL('../',import.meta.url));
const asset=process.env.XYG_COLOR_CLIENT??root+'packages/xy-client/dist/index.js';
const fixture=root+'tests/fixtures/css_color_bridge.json';
const server=createServer(async(req,res)=>{try{
 if(req.url==='/'){res.setHeader('Content-Type','text/html');res.end('<!doctype html><meta charset="utf-8"><style>body{margin:0;color:#202020}.pair{display:flex}</style><div id="charts"></div>');return;}
 if(req.url==='/favicon.ico'){res.writeHead(204);res.end();return;}
 const file=req.url==='/client.js'?asset:req.url==='/fixture.json'?fixture:null;
 if(!file){res.writeHead(404);res.end();return;}
 res.setHeader('Content-Type',req.url.endsWith('.js')?'application/javascript':'application/json');res.end(await readFile(file));
}catch(error){res.writeHead(500);res.end(String(error));}});
await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
let browser,timer,report;const errors=[],warnings=[];
try{
 browser=await chromium.launch({executablePath:process.env.XYG_CHROMIUM,args:['--use-angle=swiftshader','--enable-unsafe-swiftshader','--ignore-gpu-blocklist']});
 const page=await browser.newPage({viewport:{width:1000,height:800}});page.on('pageerror',e=>errors.push(e.message));page.on('console',m=>{if(m.type()==='warning')warnings.push(m.text());});
 await page.goto('http://127.0.0.1:'+server.address().port);
 if(process.env.XYG_COLOR_CAPTURE)await page.exposeFunction('__captureCssColor',()=>page.locator('.xy').first().screenshot({path:process.env.XYG_COLOR_CAPTURE}));
 report=await Promise.race([page.evaluate(async()=>{
  const xy=await import('/client.js'),fixture=await(await fetch('/fixture.json')).json();
  const assert=(condition,label)=>{if(!condition)throw Error(label);};
  const reference=document.createElement('canvas');reference.width=reference.height=1;
  const ctx=reference.getContext('2d',{willReadFrequently:true});
  const nativeColor=expr=>{ctx.globalCompositeOperation='copy';ctx.fillStyle=expr;ctx.fillRect(0,0,1,1);return Array.from(ctx.getImageData(0,0,1,1).data);};
  const hex=rgba=>'#'+rgba.map(n=>n.toString(16).padStart(2,'0')).join('');
  const sha=async bytes=>Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',bytes)),n=>n.toString(16).padStart(2,'0')).join('');
  const nativeCanvases=new Set(),getContext=HTMLCanvasElement.prototype.getContext;
  HTMLCanvasElement.prototype.getContext=function(kind,...args){if(kind==='2d'&&this.width===1&&this.height===1)nativeCanvases.add(this);return getContext.call(this,kind,...args);};
  const decode=record=>Uint8Array.from(atob(record.payload),c=>c.charCodeAt(0)).buffer;
  const host=()=>{const el=document.createElement('div');document.getElementById('charts').append(el);return el;};
  const settle=()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)));
  const pixels=view=>{view._drawNow();const c=view.canvas;if(view._glHost)return view._present2d.getImageData(0,0,c.width,c.height).data;const gl=view.gl,raw=new Uint8Array(c.width*c.height*4);gl.readPixels(0,0,c.width,c.height,gl.RGBA,gl.UNSIGNED_BYTE,raw);return raw;};
  const equal=(a,b)=>a.length===b.length&&a.every((v,i)=>v===b[i]);
  const lutPixels=view=>{
   const gl=view.gl,previous=gl.getParameter(gl.FRAMEBUFFER_BINDING),fbo=gl.createFramebuffer();
   try{gl.bindFramebuffer(gl.FRAMEBUFFER,fbo);gl.framebufferTexture2D(gl.FRAMEBUFFER,gl.COLOR_ATTACHMENT0,gl.TEXTURE_2D,view.gpuTraces[0].lut,0);assert(gl.checkFramebufferStatus(gl.FRAMEBUFFER)===gl.FRAMEBUFFER_COMPLETE,'lookup texture framebuffer incomplete');const bytes=new Uint8Array(256*4);gl.readPixels(0,0,256,1,gl.RGBA,gl.UNSIGNED_BYTE,bytes);return bytes;}finally{gl.bindFramebuffer(gl.FRAMEBUFFER,previous);gl.deleteFramebuffer(fbo);}
  };
  const markCases=[],backgroundCases=[],modern=[
   'oklch(60% 0.2 30)','oklch(70% 0.15 200 / 50%)','oklab(0.65 0.1 -0.12)',
   'lab(60% 35 -25)','lch(60% 45 280)','color(srgb 0.25 0 0.75)',
   'color(display-p3 1 0.2 0.1)','color(srgb-linear 0.2 0.4 0.6)',
   'color-mix(in srgb,red 25%,blue)','color-mix(in oklab,red 70%,blue)',
   'oklch(60% 0.2 30 / 0%)','color(srgb none 0.5 0.25)',
  ];
  const spec=structuredClone(fixture.mark.spec),el=host();
  const view=xy.renderStandalone(el,spec,decode(fixture.mark));await settle();
  el.style.setProperty('--test-mark','red');view.root.style.removeProperty('--test-mark');
  // Notebook layout/focus classes are ancestor mutations, but need not change
  // any computed chart paint. They must not queue another full data picture.
  await settle();
  const invalidations=[];let draws=0;const drawNow=view._drawNow;
  view._drawNow=function(...args){draws++;return drawNow.apply(this,args);};
  for(const [name,mutate] of [
   ['unrelated-class',()=>el.classList.add('notebook-command-mode')],
   ['ancestor-translation',()=>{el.style.transform='translateX(1px)';}],
  ]){
   const before=draws;mutate();await settle();await settle();
   assert(draws===before,'unchanged computed paint must not redraw: '+name);
   invalidations.push({name,draws:draws-before});
  }
  for(const [name,mutate] of [
   ['canvas-token',()=>el.style.setProperty('--chart-text','#2470ab')],
   ['custom-mark-token',()=>el.style.setProperty('--test-mark','#2468ac')],
  ]){
   const before=draws;mutate();await settle();await settle();
   assert(draws>before,'changed paint must redraw: '+name);
   invalidations.push({name,draws:draws-before});
  }
  assert(equal(view.gpuTraces[0].color,[0x24/255,0x68/255,0xac/255,1]),'custom CSS token must update actual mark uniform');
  view.root.style.setProperty('--chart-bg','transparent');await settle();await settle();
  const beforeBackdrop=draws;el.style.background='#547698';await settle();await settle();
  assert(draws>beforeBackdrop,'changed ancestor backdrop must redraw');
  invalidations.push({name:'ancestor-backdrop',draws:draws-beforeBackdrop});
  view.root.style.setProperty('--chart-bg','white');el.style.background='';await settle();await settle();
  const beforeExplicit=draws;view.refreshTheme();await settle();
  assert(draws>beforeExplicit,'explicit refreshTheme remains unconditional');
  view._drawNow=drawNow;
  let presentations=0;const previousComm=view.comm,render=view._glHost.render;
  view.comm={onPainted:()=>{presentations++;}};
  try{
   view._glHost.render=function(client,...args){return client===view?false:render.call(this,client,...args);};
   view._drawNow();assert(presentations===0,'refused real painter must not acknowledge');
   view._glHost.render=render;view._drawNow();
   assert(presentations===1,'successful real painter must notify after presentation');
  }finally{view._glHost.render=render;view.comm=previousComm;}
  let dataUploads=0;const bufferData=view.gl.bufferData,bufferSubData=view.gl.bufferSubData;
  view.gl.bufferData=function(...args){dataUploads++;return bufferData.apply(this,args);};
  view.gl.bufferSubData=function(...args){dataUploads++;return bufferSubData.apply(this,args);};
  try{
   for(const expr of modern){
    assert(CSS.supports('color',expr),'browser must support required CSS case: '+expr);
    const rgba=nativeColor(expr);view.root.style.setProperty('--test-mark',expr);await settle();
    if(expr===modern[0]&&typeof globalThis.__captureCssColor==='function')await globalThis.__captureCssColor();
    assert(equal(view.gpuTraces[0].color,rgba.map(n=>n/255)),'mark RGBA differs from browser sRGB conversion: '+expr);
    const actual=pixels(view);spec.traces[0].color.color=hex(rgba);view.refreshTheme();await settle();
    const expected=pixels(view);assert(equal(actual,expected),'complete same-surface canvas differs from native-color literal: '+expr);
    markCases.push({expr,rgba,rgbaSha256:await sha(actual),bytes:actual.length});
    spec.traces[0].color.color='var(--test-mark)';

   }
   // Legacy RGB alpha remains the browser-computed float, rather than being
   // quantized through the modern-format RGBA8 conversion.
   view.root.style.setProperty('--test-mark','rgb(255 0 0 / 55%)');await settle();assert(equal(view.gpuTraces[0].color,[1,0,0,0.55]),'legacy RGB alpha changed');
   view.root.style.setProperty('--test-mark','#010203');await settle();assert(equal(view.gpuTraces[0].color,[1/255,2/255,3/255,1]),'valid sentinel-valued color changed');
   const accepted=[...view.gpuTraces[0].color];spec.traces[0].color.color='xy-invalid-color';view.refreshTheme();await settle();assert(equal(view.gpuTraces[0].color,accepted),'invalid literal must retain the supplied fallback');assert(view.gpuTraces[0].color.every(Number.isFinite),'nonfinite paint uniform');
   assert(dataUploads===0,'CSS color changes must not upload source geometry');
  }finally{view.gl.bufferData=bufferData;view.gl.bufferSubData=bufferSubData;view.destroy();el.remove();}
  for(const expr of [modern[0],modern[5],modern[6]]){
   const a=host(),rgba=nativeColor(expr);a.style.background=expr;
   const x=xy.renderStandalone(a,structuredClone(fixture.category.spec),decode(fixture.category));
   try{
    await settle();const row=x.root.querySelector('[data-xy-slot="legend_item"]');assert(row,'category legend missing');row.dispatchEvent(new PointerEvent('pointerenter'));await settle();assert(x._legendHover,'real legend handler did not activate');const actual=pixels(x),repeated=pixels(x),texture=x.gpuTraces[0].lut,actualLut=lutPixels(x);
    row.dispatchEvent(new PointerEvent('pointerleave'));a.style.background=hex(rgba);await settle();const nextRow=x.root.querySelector('[data-xy-slot="legend_item"]');nextRow.dispatchEvent(new PointerEvent('pointerenter'));await settle();const expected=pixels(x);
    assert(equal(actualLut,lutPixels(x)),'modern and literal backdrops must produce the same complete GPU lookup');
    const oracle=new Uint8Array(256*4);
    const dim=[Math.floor(rgba[0]*0.8),Math.floor(rgba[1]*0.8),Math.floor(255*0.2+rgba[2]*0.8),255];
    for(let i=0;i<256;i++)oracle.set(i%2?dim:[255,0,0,255],i*4);
    assert(equal(actualLut,oracle),'complete GPU lookup differs from exact native backdrop oracle: '+expr);
    let opaque=0;for(let i=0;i<actual.length;i+=4)if(actual[i+3]===255&&dim.every((v,j)=>actual[i+j]===v))opaque++;
    assert(opaque>100,'actual opaque marks did not consume the expected dimmed lookup: '+expr);
    // The established painter can vary a few low-alpha edge bytes between
    // unchanged frames. Record that observation; this color-plane proof does
    // not claim whole-image antialiasing or frame-stability acceptance.
    backgroundCases.push({expr,rgba,rgbaSha256:await sha(actual),literalRgbaSha256:await sha(expected),lutSha256:await sha(actualLut),exactLookupBytes:actualLut.length,opaqueDimPixels:opaque,repeatFrameDifferentBytes:actual.filter((v,i)=>v!==repeated[i]).length,sameLookupOwner:texture===x.gpuTraces[0].lut});

   }finally{x.destroy();a.remove();}
  }
  // Detached hydration is an existing supported lifetime. It must re-resolve
  // after insertion rather than retaining the temporary fallback uniform.
  const detached=document.createElement('div'),ds=structuredClone(fixture.mark.spec);ds.dom.style['--test-mark']=modern[0];
  const dv=xy.renderStandalone(detached,ds,decode(fixture.mark));
  try{assert(dv._themeStale,'detached theme must be marked stale');document.getElementById('charts').append(detached);await settle();dv._drawNow();assert(!dv._themeStale,'connected chart did not heal stale theme');assert(equal(dv.gpuTraces[0].color,nativeColor(modern[0]).map(n=>n/255)),'detached modern color did not heal');}finally{dv.destroy();detached.remove();HTMLCanvasElement.prototype.getContext=getContext;}
  assert(nativeCanvases.size===1,'modern conversion must reuse one bounded pixel per document');
  return {presentations,invalidations,markCases,backgroundCases,dataUploads,legacyAlpha:0.55,sentinel:true,detachedHealed:true,conversionCanvases:nativeCanvases.size,remainingCharts:document.querySelectorAll('.xy').length};
 }),new Promise((_,reject)=>timer=setTimeout(()=>reject(Error('CSS color bridge browser deadline')),60000))]);
 assert.deepEqual(errors,[],'page errors');assert(warnings.some(w=>w.includes('xy-invalid-color')),'invalid literal must emit its fallback diagnostic');assert(warnings.filter(w=>w.startsWith('xy: unresolvable color')).every(w=>w.includes('xy-invalid-color')),'valid or detached CSS color emitted a false fallback diagnostic');assert.equal(report.remainingCharts,0,'chart teardown');
 report={ok:true,browser:browser.version(),asset:{path:asset,sha256:createHash('sha256').update(await readFile(asset)).digest('hex')},fixtureSha256:createHash('sha256').update(await readFile(fixture)).digest('hex'),...report,errors,warnings};
 console.log(JSON.stringify(report));
}finally{clearTimeout(timer);if(report&&process.env.XYG_COLOR_REPORT)await writeFile(process.env.XYG_COLOR_REPORT,JSON.stringify(report,null,2)+'\n');await browser?.close();server.close();}
