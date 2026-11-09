#!/usr/bin/env node
// Unmasked production Worker/WASM graph session keyboard/paint/ownership journey.
import assert from "node:assert/strict";
import { gunzipSync } from "node:zlib";
import { createServer } from "node:http";
import { readFile, writeFile } from "node:fs/promises";
import { extname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";
const root = fileURLToPath(new URL("..", import.meta.url));
const allowed = p => p === "/old-same-abi.wasm" || p === "/packages/xy-node/src/graphforge-container.js" || p === "/tests/browser/graph_session_controller_page.mjs" || p === "/tests/fixtures/graphforge/session_companion_nodes.arrow" || /^\/tests\/fixtures\/graphforge\/results\/[a-z_-]+\.arrow$/.test(p) || ["/packages/xy-client/dist/index.js", "/packages/xy-client/dist/wasm-worker.js", "/packages/xy-client/dist/xyg-wasm.wasm"].includes(p);
const csp = "default-src 'none'; script-src 'self' 'wasm-unsafe-eval'; worker-src 'self'; connect-src 'self'; style-src 'unsafe-inline'; object-src 'none'; base-uri 'none'";
const requests = [], violations = [], errors = [];
const server = createServer(async (req, res) => {
  const p = new URL(req.url, "http://localhost").pathname; requests.push(p); res.setHeader("Content-Security-Policy", csp);
  if (p === "/") { res.setHeader("Content-Type", "text/html"); res.end('<!doctype html><meta charset="utf-8"><script type="module" src="/tests/browser/graph_session_controller_page.mjs"></script>'); return; }
  if (p === "/old-same-abi.wasm") {
    res.setHeader("Content-Type", "application/wasm");
    res.end(gunzipSync(await readFile(resolve(root, "spec/performance/graph-s5b-attachment-2026-11-04/shipping-module.wasm.gz")))); return;
  }
  if (!allowed(p)) { res.statusCode = 404; res.end(); return; }
  try { const data = await readFile(resolve(root, `.${p}`)); res.setHeader("Content-Type", ({ ".mjs": "text/javascript", ".js": "text/javascript", ".wasm": "application/wasm" })[extname(p)] ?? "application/octet-stream"); res.end(data); } catch { res.statusCode = 404; res.end(); }
});
await new Promise(r => server.listen(0, "127.0.0.1", r));
const browser = await chromium.launch({ executablePath: process.env.XYG_CHROMIUM || process.env.CHROMIUM, args: ["--use-gl=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"] });
const count=Number(process.env.XYG_GRAPH_SCALE??100000);
assert.ok([100000,1000000].includes(count));
const report=resolve(process.env.XYG_GRAPH_SESSION_REPORT??`target/task-tmp/graph-scale-${count}.json`);
const evidence={schema:'xyg.public-graph-scale/v1',count,node:process.version,browser:browser.version(),cap:384*1024*1024,camera:[150/count,150/count,320,160,640,320,1],views:[]};

let page, cdp;
try {
 page=await browser.newPage({reducedMotion:'reduce',viewport:{width:1800,height:1200}});
 page.on('pageerror',e=>errors.push(e.message));
 await page.goto(`http://127.0.0.1:${server.address().port}/`);
 await page.waitForFunction(()=>window.__graphSession?.stage==='ready');
 cdp=await page.context().newCDPSession(page);await cdp.send('Performance.enable');
 if(process.env.XYG_GRAPH_PROFILE){await cdp.send('Profiler.enable');await cdp.send('Profiler.start');}
 evidence.heapBefore=await cdp.send('Performance.getMetrics');
 await page.evaluate(async({count,camera})=>{
   const s=window.__graphSession;await s.handle.dispose();await s.worker.dispose();s.el.remove();
   const attach=s.attach;
   s.attach=options=>{
     const owner=options.worker.worker.__graphOwner;
     options.el.dataset.scale=String(options.instanceId);options.el.style.display='inline-block';document.body.prepend(options.el);
     s.scalePublications??={};const publications=s.scalePublications[String(options.instanceId)]=[];
     s.scalePaints??={};const observations=s.scalePaints[String(options.instanceId)]=[];
     options.el.addEventListener('xy:graph-render',e=>requestAnimationFrame(()=>{
       if(!options.el.isConnected)return;const canvas=options.el.querySelector('canvas');if(!canvas)return;
       const data=canvas.getContext('2d').getImageData(0,0,640,320).data;
       let minX=640,maxX=-1,minY=320,maxY=-1,pixels=0;
       for(let i=0;i<data.length;i+=4)if(data[i+3]&&!(data[i]===255&&data[i+1]===255&&data[i+2]===255)){
         const x=(i/4)%640,y=Math.floor(i/4/640);pixels++;minX=Math.min(minX,x);maxX=Math.max(maxX,x);minY=Math.min(minY,y);maxY=Math.max(maxY,y);
       }
       observations.push({at:performance.now(),steps:e.detail.relayout?.steps,done:e.detail.relayout?.done,pixels,bounds:[minX,minY,maxX,maxY]});
     }));
     for(const kind of ['render','focus','select'])options.el.addEventListener('xy:graph-'+kind,e=>publications.push({kind,camera:[...e.detail.camera],steps:e.detail.relayout?.steps}));
     options.el.addEventListener('xy:graph-render',()=>{
       const latest=s.replies.filter(r=>r.owner===owner).at(-1);
       for(const r of s.replies.filter(r=>r.owner===owner)) {
         if(!r.digest){r.replyBytes=r.bytes.length;r.digest=crypto.subtle.digest('SHA-256',r.bytes).then(h=>{r.replySha256=Array.from(new Uint8Array(h),v=>v.toString(16).padStart(2,'0')).join('');if(s.replies.filter(x=>x.owner===owner).at(-1)!==r)delete r.bytes;return r.replySha256;});}
         else if(r!==latest&&r.replySha256)delete r.bytes;
       }
     });
     return attach(options);
   };
   const peerReady=s.progressiveFixture(1000,9102n,{},undefined,[.15,.15,320,160,640,320,1]);
   await s.progressiveFixture(count,9101n,{},384*1024*1024,camera);
   const p=s.progressives.find(p=>p.id===9101n);if(!p||p.count!==count)throw Error("primary identity/count mismatch");p.selects=[];p.focuses=[];p.pans=[];p.publications=s.scalePublications[String(p.id)];
   p.el.addEventListener('xy:graph-select',e=>p.selects.push({at:performance.now(),snapshot:e.detail}));
   p.el.addEventListener('xy:graph-focus',e=>p.focuses.push({at:performance.now(),snapshot:e.detail}));
   const button=document.createElement('button');button.dataset.pan='';button.textContent='Pan right';p.el.prepend(button);
   button.addEventListener('click',async e=>{const before=p.handle.snapshot();try{const camera=[...before.camera];camera[2]+=12;const after=await p.handle.refreshRender(camera);p.pans.push({trusted:e.isTrusted,before,after,framesAtReply:p.frames.length,publicationsAtReply:p.publications.length});}catch(e){p.pans.push({trusted:e.isTrusted,code:e.code});}});
   await peerReady;
   document.body.prepend(p.el);
 },{count,camera:evidence.camera});
 console.log('READY primary and peer');
 const primary=page.locator('[data-scale="9101"]');
 // Actual Tab navigation, with no programmatic focus on the graph surface.
 for(let i=0;i<20&&!await primary.locator('[role=application]').evaluate(el=>el===document.activeElement);i++)await page.keyboard.press('Tab');
 assert.equal(await primary.locator('[role=application]').evaluate(el=>el===document.activeElement),true,'real Tab reaches primary');
 for(const [key,field] of [['ArrowRight','focuses'],['Enter','selects']]) {
   let admitted=false;
   for(let i=0;i<40;i++) {
     const mark=await page.evaluate(()=>window.__graphSession.progressives.find(p=>p.id===9101n).trusted.length);
     await page.keyboard.press(key);
     admitted=await page.evaluate(({mark,key})=>window.__graphSession.progressives.find(p=>p.id===9101n).trusted.slice(mark).some(e=>e.key===key&&e.prevented),{mark,key});
     if(admitted)break;
   }
   assert.ok(admitted,'trusted key admitted while unfinished');
   await page.waitForFunction(field=>window.__graphSession.progressives.find(p=>p.id===9101n)[field].length>0,field,{polling:2});console.log('ACCEPTED '+key);
 }
 let picked=false;
 for(let i=0;i<40;i++) {
   const point=await page.evaluate(()=>{const s=window.__graphSession,p=s.progressives.find(p=>p.id===9101n),r=s.replies.filter(r=>r.owner===p.worker.worker.__graphOwner).at(-1),raw=s.section(r.bytes,'paint.node.center.f64'),v=new DataView(raw.buffer,raw.byteOffset,raw.byteLength),box=p.el.querySelector('canvas').getBoundingClientRect();return{x:box.x+v.getFloat64(0,true),y:box.y+v.getFloat64(8,true),n:p.selects.length,commands:s.commands.filter(c=>c.owner===p.worker.worker.__graphOwner).length};});
   await page.mouse.click(point.x,point.y);
   await page.waitForFunction(n=>window.__graphSession.progressives.find(p=>p.id===9101n).selects.length>n,point.n,{polling:2});
   picked=await page.evaluate(mark=>{const s=window.__graphSession,p=s.progressives.find(p=>p.id===9101n);return s.commands.filter(c=>c.owner===p.worker.worker.__graphOwner).slice(mark).some(c=>c.operation===1);},point.commands);
   if(picked){await page.waitForFunction(n=>window.__graphSession.progressives.find(p=>p.id===9101n).selects.length>n,point.n,{polling:2});break;}
 }
 assert.ok(picked,'trusted pointer command admitted');console.log('ACCEPTED pointer');
 for(let i=0;i<40;i++) {
   const target=await primary.locator('[data-pan]').evaluate(el=>{const b=el.getBoundingClientRect();return{x:b.x+b.width/2,y:b.y+b.height/2,n:window.__graphSession.progressives.find(p=>p.id===9101n).pans.length};});
   await page.mouse.click(target.x,target.y);
   await page.waitForFunction(n=>window.__graphSession.progressives.find(p=>p.id===9101n).pans.length>n,target.n,{polling:2});
   if(await page.evaluate(()=>window.__graphSession.progressives.find(p=>p.id===9101n).pans.some(p=>p.after)))break;
 }
 await page.waitForFunction(()=>{const p=window.__graphSession.progressives.find(p=>p.id===9101n),pan=p.pans.find(p=>p.after);return pan&&p.frames.slice(pan.framesAtReply).some(f=>f.progress.steps>pan.after.relayout.steps);},null,{polling:2});
 console.log('ACCEPTED camera and later progress');
 evidence.heapDuring=await cdp.send('Performance.getMetrics');
 evidence.gpuDuring=await page.evaluate(()=>{const key=Object.getOwnPropertySymbols(globalThis).find(k=>k.description?.endsWith('.xy.shared-webgl-host.v2')),host=key&&globalThis[key].get(document);if(!host)return null;const snapshot=host.dashboardResourceSnapshot();return{storage:host.storageSnapshot(),sharedBytes:String(host.sharedResourceBytes()),resources:snapshot.resources};});
 evidence.views=await page.evaluate(async()=>{
   const s=window.__graphSession,out=[];
   for(const id of [9101n,9102n]) {
     const p=s.progressives.find(p=>p.id===id),owner=p.worker.worker.__graphOwner;
     const beforeDispose=p.handle.snapshot(),framesAtDispose=p.frames.length;
     const canvas=p.el.querySelector("canvas");p.captures.live=canvas.toDataURL("image/png");const data=canvas.getContext("2d").getImageData(0,0,640,320).data;
     clearInterval(p.timer);await p.handle.dispose();await p.worker.dispose();
     await Promise.all(s.replies.filter(r=>r.owner===owner).map(async r=>{if(!r.digest){r.replyBytes=r.bytes.length;r.digest=crypto.subtle.digest('SHA-256',r.bytes).then(h=>r.replySha256=Array.from(new Uint8Array(h),v=>v.toString(16).padStart(2,'0')).join(''));}await r.digest;}));
     const b64=b=>{let t='';for(let i=0;i<b.length;i+=16384)t+=String.fromCharCode(...b.subarray(i,i+16384));return btoa(t);};
     const replay=s.commands.filter(c=>c.owner===owner&&c.bytes).map(c=>{const r=s.replies.find(r=>r.owner===owner&&r.requestId===c.requestId);if(!r)throw Error('missing completed reply');return{operation:c.operation,request:b64(c.bytes),replyBytes:r.replyBytes??r.bytes.length,replySha256:r.replySha256};});
     const latest=s.replies.filter(r=>r.owner===owner).at(-1);
     let minX=640,maxX=-1,minY=320,maxY=-1,pixels=0;for(let i=0;i<data.length;i+=4)if(data[i+3]&&!(data[i]===255&&data[i+1]===255&&data[i+2]===255)){const x=(i/4)%640,y=Math.floor(i/4/640);pixels++;minX=Math.min(minX,x);maxX=Math.max(maxX,x);minY=Math.min(minY,y);maxY=Math.max(maxY,y);}
     out.push({id:String(id),sourceNodes:p.count,sourceEdges:p.count,arena:p.arena,actualArena:p.worker.worker.__actualArena,replay,reply:b64(latest.bytes),beforeDispose,frames:p.frames,publications:p.publications??s.scalePublications[String(id)],painted:p.painted,paintObservations:s.scalePaints[String(id)],focuses:p.focuses??[],selects:p.selects??[],keys:p.trusted,clicks:p.clicks,pans:p.pans??[],errors:p.errors,heartbeats:p.heartbeats,bounds:[minX,minY,maxX,maxY],pixels,held:s.held.length,framesAtDispose,framesAfterDispose:p.frames.length,disposed:p.handle.snapshot()===null,children:p.el.querySelectorAll('[data-xy-graph-session],table,canvas').length,authoredChildren:p.el.children.length,captures:p.captures});
     p.el.remove();
   }await new Promise(r=>setTimeout(r,25));return out;
 });
 for(const v of evidence.views){await writeFile(`${report}.${v.id}.xygr`,Buffer.from(v.reply,'base64'));delete v.reply;for(const [name,data]of Object.entries(v.captures))await writeFile(`${report}.${v.id}.${name}.png`,Buffer.from(data.split(',')[1],'base64'));delete v.captures;}
 evidence.heapAfter=await cdp.send('Performance.getMetrics');
 evidence.gpuAfter=await page.evaluate(()=>{const key=Object.getOwnPropertySymbols(globalThis).find(k=>k.description?.endsWith('.xy.shared-webgl-host.v2')),host=key&&globalThis[key].get(document);if(!host)return null;return{storage:host.storageSnapshot(),sharedBytes:String(host.sharedResourceBytes()),resources:host.dashboardResourceSnapshot().resources};});evidence.errors=errors;evidence.violations=violations;
 await writeFile(report,JSON.stringify(evidence,(_,v)=>typeof v==='bigint'?String(v):v,2)+'\n');
 for(const v of evidence.views){assert.deepEqual(v.errors,[]);assert.equal(v.held,0);assert.equal(v.disposed,true);assert.equal(v.children,0);assert.equal(v.framesAfterDispose,v.framesAtDispose);assert.ok(v.paintObservations.some(f=>!f.done&&f.pixels>3000&&f.bounds[2]-f.bounds[0]>200&&f.bounds[3]-f.bounds[1]>200),"actual useful unfinished paint");assert.ok(v.frames.length>3);}
 const [p,peer]=evidence.views;
 assert.ok(p.pixels>3000&&p.bounds[2]-p.bounds[0]>200&&p.bounds[3]-p.bounds[1]>200,"primary retains useful paint through interaction");
 assert.equal(p.actualArena,384*1024*1024);assert.equal(peer.actualArena,16*1024*1024);
 assert.ok(p.focuses.some(e=>!e.snapshot.relayout.done));assert.ok(p.selects.some(e=>!e.snapshot.relayout.done&&e.snapshot.outcome.selected>0));
 assert.ok(p.clicks.some(e=>e.trusted&&!e.progress.done));
 assert.ok(p.keys.some(e=>e.key==='ArrowRight'&&e.trusted&&e.prevented));assert.ok(p.keys.some(e=>e.key==='Enter'&&e.trusted&&e.prevented));assert.ok(p.pans.some(e=>e.trusted&&e.after));
 assert.equal(peer.beforeDispose.selection.refs.length,0);assert.equal(peer.focuses.length,0);
 for(const pan of p.pans.filter(p=>p.after))for(const f of p.publications.slice(pan.publicationsAtReply))assert.deepEqual(f.camera,pan.after.camera,'every post-reply publication retains camera, including same-step focus/select replies');
 assert.deepEqual(errors,[]);console.log(`PASS public ${count} primary + default1k peer, live Tab/pick/camera/progress/cancel/dispose`);
} catch(e) { if(page) evidence.failureState=await page.evaluate(()=>window.__graphSession?.progressives?.map(p=>({id:String(p.id),frames:p.frames,keys:p.trusted,focuses:p.focuses,selects:p.selects,pans:p.pans,errors:p.errors,progress:p.handle?.snapshot()?.relayout}))).catch(()=>null); await writeFile(report+'.failure.json',JSON.stringify({error:String(e),stack:e.stack,evidence},(_,v)=>typeof v==='bigint'?String(v):v,2)+'\n');throw e; }
finally {if(process.env.XYG_GRAPH_PROFILE&&cdp)await writeFile(report+'.cpuprofile',JSON.stringify((await cdp.send('Profiler.stop')).profile));await browser.close();await new Promise(r=>server.close(r));}
