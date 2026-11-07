#!/usr/bin/env node
// Unmasked production Worker/WASM graph session keyboard/paint/ownership journey.
import assert from "node:assert/strict";
import {graphCaptureCase} from "./graph_capture_case.mjs";
import {assertProgressiveCameraPan} from "./verify_graph_progressive_camera.mjs";
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
const evidence = { schema: "xyg.graph-s5b-pointer-selection/v1", node: process.version, browser: browser.version(), cases: [] };
try {
  const page = await browser.newPage({ reducedMotion: "reduce", viewport: { width: 2800, height: 1500 } }); page.on("console", m => { if (/Content Security Policy|Refused to/.test(m.text())) violations.push(m.text()); }); page.on("pageerror", e => errors.push(e.message));
  await page.goto(`http://127.0.0.1:${server.address().port}/`);
  await page.waitForFunction(() => ["ready", "failed"].includes(window.__graphSession?.stage), null, { timeout: 60_000 });
  assert.equal(await page.evaluate(() => window.__graphSession.stage), "ready", JSON.stringify(await page.evaluate(() => window.__graphSession.failure)));
  const run = async (name, fn) => { const result = await fn(); evidence.cases.push({ name, result }); console.log(`PASS ${name}`); return result; };
  const check = async fn => { const result = await page.evaluate(fn); assert.equal(result.ok, true, JSON.stringify(result, (_, v) => typeof v === "bigint" ? v.toString() : v)); return result; };
  evidence.default1k=await page.evaluate(async()=>{
    try { await window.__graphSession.progressiveFixture(1000,16001n,{});const p=window.__graphSession.progressives.at(-1);clearInterval(p.timer);await p.handle.dispose();await p.worker.dispose();p.el.remove();return {status:'opened'}; }
    catch(e) {return {status:'refused',code:e.code};}
  });
  assert.deepEqual(evidence.default1k,{status:'opened'});
  await page.evaluate(async () => {
    const state=window.__graphSession, makeWorker=state.makeWorker, container=state.container;
    const {DTYPE,encodeContainer}=await import('/packages/xy-node/src/graphforge-container.js');
  state.progressiveFixture = async (count, id, load = {}, arena) => {
  const f = (name, dtype, values) => ({name, dtype:DTYPE[dtype], values});
  const nodes = new Uint8Array(count*16), edges = new Uint8Array(count*16);
  for (let i=0;i<count;i++) { new DataView(nodes.buffer).setUint32(i*16,i+1,true); new DataView(edges.buffer).setUint32(i*16,i+10001,true); }
  const document = encodeContainer('XYGF', [f('status','u32',[0]),f('kind','utf8','graph'),f('composition.version','u32',[2]),f('node.uuid','uuid',nodes),f('edge.uuid','uuid',edges),f('edge.derived','u8',Array(count).fill(0)),f('edge.layer','u32',Array(count).fill(0xffffffff)),f('edge.order','i64',Array(count).fill(-1n)),f('edge.path','u64',Array(count).fill(0xffffffffffffffffn)),f('edge.source','u64',Array.from({length:count},(_,i)=>BigInt(i))),f('edge.target','u64',Array.from({length:count},(_,i)=>BigInt((i+1)%count))),f('graph.directed','u8',[0])]);
  const started=performance.now();const worker=makeWorker(undefined, arena); await worker.ready;const workerReady=performance.now();
  const el=container(), p={id,count,el,worker,started,workerReady,frames:[],errors:[],beats:0,document,load:{progressive:true,...load},camera:[count===1000?.25:.01,count===1000?.25:.01,320,160,640,320,1]};
  state.progressives ??= []; state.progressives.push(p);
  const pixels=()=>el.querySelector('canvas').getContext('2d').getImageData(0,0,640,320).data;
  el.addEventListener('xy:graph-render',e=>p.frames.push({at:performance.now(),revision:e.detail.revision,progress:e.detail.relayout,camera:[...e.detail.camera],pixels:0}));
  for(const kind of ['error','stale']) el.addEventListener(`xy:graph-${kind}`,e=>p.errors.push(e.detail));
  p.painted=[]; p.clicks=[]; p.captures={};
  // Diagnostic retention only: hash complete replies without delaying delivery,
  // then release historical byte copies. Keep the latest for the pointer oracle.
  el.addEventListener('xy:graph-render',()=>{
    const replies=state.replies.filter(r=>r.owner===worker.worker.__graphOwner),latest=replies.at(-1);
    for(const r of replies) {
      if(!r.digest) {
        r.replyBytes=r.bytes.length;
        r.digest=crypto.subtle.digest('SHA-256',r.bytes).then(hash=>{
          r.replySha256=Array.from(new Uint8Array(hash),b=>b.toString(16).padStart(2,'0')).join('');
          if(state.replies.filter(x=>x.owner===r.owner).at(-1)!==r)delete r.bytes;
          return r.replySha256;
        });
      } else if(r!==latest&&r.replySha256)delete r.bytes;
    }
  });
  el.addEventListener('xy:graph-render',()=>requestAnimationFrame(()=>{
    if(!el.isConnected||!p.handle?.snapshot())return;
    const data=pixels();let hash=2166136261,nonzero=0;
    for(let i=0;i<data.length;i++){hash=Math.imul(hash^data[i],16777619)>>>0;if(i%4===3&&data[i]>0)nonzero++;}
    const progress=p.handle.snapshot().relayout;
    p.frames.at(-1).pixels=nonzero;
    p.painted.push({at:performance.now(),progress,hash,pixels:nonzero});
    const stage=progress?.done?'final':BigInt(progress?.steps??0)>=100n?'intermediate':'initial';
    if(!p.captures[stage])p.captures[stage]=el.querySelector('canvas').toDataURL('image/png');
  }));
  el.addEventListener('click',e=>{if(e.isTrusted&&e.target.tagName==='CANVAS')p.clicks.push({at:performance.now(),trusted:e.isTrusted,prevented:e.defaultPrevented,progress:p.handle.snapshot()?.relayout});});
  p.heartbeats=[]; p.trusted=[];
  el.addEventListener('keydown',e=>{if(e.isTrusted)p.trusted.push({key:e.key,at:performance.now(),progress:p.handle.snapshot()?.relayout,prevented:e.defaultPrevented});});
  p.timer=setInterval(()=>{p.beats++;p.heartbeats.push(performance.now());},5);
  p.handle=state.attach({el,worker,instanceId:id,document,load:p.load,camera:p.camera});
  try { await p.handle.ready; } catch(error) { clearInterval(p.timer); await p.handle.dispose(); await worker.dispose(); el.remove(); throw error; }
  return {revision:p.handle.snapshot().revision,progress:p.handle.snapshot().relayout};
};

  });
    if(process.env.XYG_GRAPH_CAPTURE_BASELINE)await page.evaluate(()=>{window.__graphSession.waitForCapture=async()=>{};});
    await run('capture-waits-for-recorded-request-reply',()=>graphCaptureCase(page));
    await run('public-10k-unheld-pick-camera-isolation-cleanup', async () => {
      await page.evaluate(async () => {
        const s=window.__graphSession;
        await Promise.all([s.progressiveFixture(10000,7101n,{},384*1024*1024),s.progressiveFixture(1000,7102n,{},384*1024*1024)]);
        // Deterministically exercise reverse Worker arrival order.
        const views=[7102n,7101n].map(id=>s.progressives.find(p=>p.id===id));
        for(const view of views)if(!view)throw Error('missing scheduling view');
        s.progressives=[...s.progressives.filter(p=>p.id!==7101n&&p.id!==7102n),...views];
        for(const p of [7101n,7102n].map(id=>s.progressives.find(p=>p.id===id))) {
          p.el.dataset.scheduling=String(p.id); p.selections=[]; p.pans=[]; p.keys=[];
          p.el.addEventListener('xy:graph-select',e=>p.selections.push({at:performance.now(),snapshot:e.detail}));
          p.el.addEventListener('xy:graph-focus',e=>p.keys.push({at:performance.now(),snapshot:e.detail}));
          const button=document.createElement('button');button.textContent='Pan right';button.dataset.pan='';p.el.prepend(button);
          button.addEventListener('click',async e=>{
            const before=p.handle.snapshot(),at=performance.now();
            try {const camera=[...before.camera];camera[2]+=12;const after=await p.handle.refreshRender(camera);p.pans.push({trusted:e.isTrusted,at,returned:performance.now(),framesAtReply:p.frames.length,before,after});}
            catch(e){p.pans.push({trusted:e.isTrusted,at,code:e.code});}
          });
        }
      });
      evidence.fixtureStorageOrder=await page.evaluate(()=>window.__graphSession.progressives.filter(p=>p.id===7101n||p.id===7102n).map(p=>p.id));
      assert.deepEqual(evidence.fixtureStorageOrder,[7102n,7101n]);
      const cdp=await page.context().newCDPSession(page);await cdp.send('Performance.enable');
      evidence.heapDuring=await cdp.send('Performance.getMetrics');
      const surface=page.locator('[data-scheduling="7101"] [role="application"]');
      await surface.focus();await page.keyboard.press('ArrowRight');
      for(let attempt=0;attempt<80;attempt++) {
        const point=await page.evaluate(()=>{
          const s=window.__graphSession,p=s.progressives.find(p=>p.id===7101n),snap=p.handle.snapshot();
          const reply=s.replies.filter(r=>r.owner===p.worker.worker.__graphOwner).at(-1);
          const centers=s.values(reply.bytes,'paint.node.center.f64');const r=p.el.querySelector('canvas').getBoundingClientRect();
          for(let i=0;i<centers.length;i+=2)if(centers[i]>10&&centers[i]<630&&centers[i+1]>10&&centers[i+1]<310)
            return {x:r.x+centers[i],y:r.y+centers[i+1],done:snap.relayout?.done};
          return {centers:centers.length,done:snap.relayout?.done};
        });
        if(point.done) break;
        if(point.x!==undefined)await page.mouse.click(point.x,point.y);
        if(await page.evaluate(()=>window.__graphSession.progressives.find(p=>p.id===7101n).selections.some(e=>e.snapshot.outcome.selected>0&&!e.snapshot.relayout?.done))) break;
      }
      for(let attempt=0;attempt<80;attempt++) {
        await page.locator('[data-scheduling="7101"] [data-pan]').click();
        if(await page.evaluate(()=>window.__graphSession.progressives.find(p=>p.id===7101n).pans.some(p=>p.after&&!p.after.relayout?.done)))break;
      }
      await page.waitForFunction(()=>[7101n,7102n].map(id=>window.__graphSession.progressives.find(p=>p.id===id)).every(p=>p.handle.snapshot()?.relayout?.done||p.errors.length),null,{timeout:40000});
      const failures=await page.evaluate(()=>window.__graphSession.progressives.filter(p=>p.id===7101n||p.id===7102n).map(p=>({id:String(p.id),errors:p.errors,progress:p.handle.snapshot()?.relayout,frames:p.frames.length,painted:p.painted.length})));
      console.log(JSON.stringify(failures,(_,v)=>typeof v==='bigint'?v.toString():v));
      assert.ok(failures.every(p=>p.errors.length===0),JSON.stringify(failures,(_,v)=>typeof v==='bigint'?v.toString():v));
      await page.waitForFunction(()=>[7101n,7102n].map(id=>window.__graphSession.progressives.find(p=>p.id===id)).every(p=>p.painted.some(f=>f.progress?.done)),null,{timeout:40000});
      const result=await page.evaluate(async()=>{
        const s=window.__graphSession,out=[];
        for(const p of [7101n,7102n].map(id=>s.progressives.find(p=>p.id===id))) {
          await s.waitForCapture(p);
          const at=performance.now(),frames=p.frames.length,finalSnapshot=p.handle.snapshot();const owner=p.worker.worker.__graphOwner;const commands=s.commands.filter(c=>c.owner===owner);const replies=s.replies.filter(c=>c.owner===owner);
          const base64=b=>{let text='';for(let i=0;i<b.length;i+=16384)text+=String.fromCharCode(...b.subarray(i,i+16384));return btoa(text);};
          const replay=await Promise.all(commands.filter(c=>c.bytes).map(async c=>{
            const reply=replies.find(r=>r.requestId===c.requestId);
            if(!reply)throw Error(s.json({kind:'missing reply',owner,id:p.id,command:{...c,bytes:c.bytes.length},terminal:s.transportReplies?.filter(r=>r.owner===owner&&r.requestId===c.requestId),lastCommands:commands.slice(-3).map(({bytes,...v})=>v),lastReplies:replies.slice(-3).map(({bytes,digest,...v})=>v),collectedAt:performance.now()}));
            const hash=await reply.digest;
            return {operation:c.operation,request:base64(c.bytes),replyBytes:reply.replyBytes,replySha256:hash};
          }));
          clearInterval(p.timer);await p.handle.dispose();await p.worker.dispose();
          out.push({sourceNodes:p.count,sourceEdges:p.count,replay,id:p.id,finalSnapshot,started:p.started,workerReady:p.workerReady,captures:p.captures,arena:384*1024*1024,painted:p.painted,clicks:p.clicks,payloadBytes:{requests:commands.reduce((n,c)=>n+c.bytes.length,0),replies:replies.reduce((n,c)=>n+c.replyBytes,0)},frames:p.frames,errors:p.errors,heartbeats:p.heartbeats,selections:p.selections,pans:p.pans,keys:p.keys,
            commands:s.commands.filter(c=>c.owner===p.worker.worker.__graphOwner).map(({bytes,...c})=>c),held:s.held.length,
            cleanupMs:performance.now()-at,attachmentChildren:p.el.querySelectorAll('[data-xy-graph-session],table,canvas').length,disposed:p.handle.snapshot()===null,framesAtDispose:frames});p.el.remove();
        }await new Promise(r=>setTimeout(r,25));return out;
      });
      for(const p of result) {
        if(process.env.XYG_GRAPH_SESSION_REPORT)for(const [stage,data]of Object.entries(p.captures))await writeFile(`${process.env.XYG_GRAPH_SESSION_REPORT}.${p.id}.${stage}.png`,Buffer.from(data.split(',')[1],'base64'));
        delete p.captures;
      }
      evidence.views=result;evidence.heapAfter=await cdp.send('Performance.getMetrics');
      if(process.env.XYG_GRAPH_SESSION_REPORT)await writeFile(process.env.XYG_GRAPH_SESSION_REPORT,JSON.stringify(evidence,(_,v)=>typeof v==='bigint'?v.toString():v,2)+'\n');
      for(const p of result){assert.deepEqual(p.errors,[]);assert.equal(p.held,0);assert.equal(p.disposed,true);assert.equal(p.attachmentChildren,0);assert.equal(p.frames.length,p.framesAtDispose);assert.ok(p.commands.filter(c=>c.operation).every(c=>String(c.instanceId)===String(p.id)));assert.ok(new Set(p.painted.filter(f=>!f.progress.done&&f.pixels>0).map(f=>f.progress.steps)).size>3);assert.ok(new Set(p.painted.map(f=>f.hash)).size>3);assert.ok(p.frames.filter(f=>!f.progress.done&&f.pixels>0).length>3);assert.ok(p.frames.at(-1).progress.done);}
      const primary=result.find(p=>p.id===7101n),secondary=result.find(p=>p.id===7102n);
      assert.ok(primary&&secondary);
      assert.ok(primary.selections.some(e=>e.snapshot.outcome.selected>0&&!e.snapshot.relayout?.done),'trusted unfinished pick');
      assertProgressiveCameraPan(primary);
      assert.ok(primary.clicks.some(e=>e.trusted&&e.prevented&&!e.progress?.done));
      assert.equal(secondary.selections.length,0);assert.equal(secondary.finalSnapshot.selection.refs.length,0);assert.equal(secondary.finalSnapshot.camera[2],320);assert.deepEqual(violations,[]);assert.deepEqual(errors,[]);
      return result;
    });
} finally { await browser.close(); await new Promise(r=>server.close(r)); }
