#!/usr/bin/env node
// Unmasked production Worker/WASM graph session keyboard/paint/ownership journey.
import assert from "node:assert/strict";
import {graphCaptureCase} from "./graph_capture_case.mjs";
import {graphProgressiveKeyboardCase} from "./graph_progressive_keyboard_case.mjs";
import {assertProgressiveCameraPan} from "./verify_graph_progressive_camera.mjs";
import { gunzipSync } from "node:zlib";
import { createServer } from "node:http";
import { readFile, writeFile } from "node:fs/promises";
import { extname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";
const root = fileURLToPath(new URL("..", import.meta.url));
const allowed = p => p === "/old-same-abi.wasm" || p === "/tests/fixtures/temporal/assertion-history.json" || p === "/packages/xy-node/src/graphforge-container.js" || p === "/tests/browser/graph_session_controller_page.mjs" || p === "/tests/fixtures/graphforge/session_companion_nodes.arrow" || /^\/tests\/fixtures\/graphforge\/results\/[a-z_-]+\.arrow$/.test(p) || ["/packages/xy-client/dist/index.js", "/packages/xy-client/dist/wasm-worker.js", "/packages/xy-client/dist/xyg-wasm.wasm"].includes(p);
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
  if (process.env.XYG_GRAPH_POINTER_BASELINE) {
    await run("before-primary-click-has-no-controller-command", async () => {
      const point = await page.evaluate(() => {
        const s = window.__graphSession, bytes = s.section(s.replies.at(-1).bytes, "paint.node.center.f64"), v = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
        const r = s.el.querySelector("canvas").getBoundingClientRect();
        return { x: r.left + v.getFloat64(0, true), y: r.top + v.getFloat64(8, true), commands: s.commands.length };
      });
      await page.mouse.click(point.x, point.y);
      const after = await page.evaluate(() => ({ commands: window.__graphSession.commands.length, selected: window.__graphSession.snapshot().outcome.selected }));
      assert.equal(after.commands, point.commands); assert.equal(after.selected, 0);
      return { ok: true, point, after, delivery: "Playwright mouse.click" };
    });
  }
  const progressiveFaultCase = async()=>{
      const delay=ms=>new Promise(r=>setTimeout(r,ms));
      const result=[];
      for(const fault of ['stale','wrong-lifetime','dispose-held']) {
        await page.evaluate(async fault=>{const s=window.__graphSession;await s.progressiveFixture(1000,4001n);s.inject=fault==='dispose-held'?null:fault;s.hold=fault==='dispose-held';},fault);
        if(fault==='dispose-held') {
          await page.waitForFunction(()=>window.__graphSession.held.length>0);
          const mark=await page.evaluate(()=>{const s=window.__graphSession,p=s.progressives.at(-1);return s.commands.filter(c=>c.owner===p.worker.worker.__graphOwner).length;});
          await delay(100);
          assert.equal(await page.evaluate(()=>{const s=window.__graphSession,p=s.progressives.at(-1);return s.commands.filter(c=>c.owner===p.worker.worker.__graphOwner).length;}),mark,'animation demand coalesces while continuation is held');
          await page.evaluate(()=>{const s=window.__graphSession,p=s.progressives.at(-1);p.disposal=p.handle.dispose();p.frameCount=p.frames.length;s.release();});
          await page.evaluate(async()=>{const p=window.__graphSession.progressives.at(-1);await p.disposal;if(p.frames.length!==p.frameCount||p.handle.snapshot()!==null)throw Error('late disposed publication');});
        } else {
          await page.waitForFunction(()=>window.__graphSession.progressives.at(-1).errors.length>0);
          const before=await page.evaluate(()=>window.__graphSession.progressives.at(-1).frames.length);
          await delay(80);
          assert.equal(await page.evaluate(()=>window.__graphSession.progressives.at(-1).frames.length),before);
        }
        result.push(await page.evaluate(async()=>{const p=window.__graphSession.progressives.at(-1),out={errors:p.errors,frames:p.frames.length};clearInterval(p.timer);await p.handle.dispose();await p.worker.dispose();p.el.remove();return out;}));
      }
      return result;

  };
  if (process.env.XYG_GRAPH_TEMPORAL_ONLY) {
    await page.evaluate(()=>window.__graphSession.temporalFixture());
    const snap=()=>page.evaluate(()=>window.__graphSession.retainedTime.handle.snapshot());
    const pixels=()=>page.evaluate(()=>{const s=window.__graphSession,p=s.retainedTime,b=s.pixel(p.el);return {at2:b.slice((165*640+300)*4,(165*640+300)*4+4),at3:b.slice((165*640+500)*4,(165*640+500)*4+4),nonzero:b.filter((v,i)=>i%4===3&&v>0).length};});
    const click=async(x,y,modifiers=[])=>{const box=await page.locator('[data-temporal-fixture] canvas').boundingBox();await page.mouse.click(box.x+x,box.y+y,{modifiers});await page.evaluate(()=>window.__graphSession.waitIdle(window.__graphSession.retainedTime.el));};
    await run('retained-temporal-initial-pixels-and-canonical-membership',async()=>{
      const result=await snap(), image=await pixels();
      assert.deepEqual(Array.from(result.temporal.nodeVisibility),[1,1,0]);assert.deepEqual(Array.from(result.temporal.edgeVisibility),[1,0]);assert.ok(image.at2[3]>0);assert.equal(image.at3[3],0);
      if(process.env.XYG_GRAPH_SESSION_REPORT)await page.locator('[data-temporal-fixture]').screenshot({path:process.env.XYG_GRAPH_SESSION_REPORT+'.initial.png'});
      const initialOrder=await page.evaluate(()=>{const s=window.__graphSession,p=s.retainedTime;return s.temporalWire.filter(r=>r.kind==='request'&&r.owner===p.worker.worker.__graphOwner).map(r=>r.type);});
      assert.deepEqual(initialOrder,['graph.session.open','graph.session.temporal-create','graph.session.temporal-frame','graph.session.interact','graph.session.render']);
      return {result,image,initialOrder};
    });
    await run('retained-temporal-native-pick-focus-select-pin',async()=>{
      await click(300,160);
      assert.equal((await snap()).selection.refs[0].uuid,'02020202-0202-0202-0202-020202020202');
      await page.locator('[data-temporal-fixture] [role=application]').focus();
      for(let i=0;i<3;i++) {if((await snap()).focus[0]?.uuid==='02020202-0202-0202-0202-020202020202')break;await page.keyboard.press('ArrowRight');await page.evaluate(()=>window.__graphSession.waitIdle(window.__graphSession.retainedTime.el));}
      await page.evaluate(()=>window.__graphSession.retainedTime.handle.pinFocused(true));
      const result=await snap();assert.equal(result.focusAction.pinned,true);assert.equal(result.focus[0].uuid,'02020202-0202-0202-0202-020202020202');return result;
    });
    await run('retained-temporal-half-open-history-pixels-and-UUID-retention',async()=>{
      const results=[];
      const frames=await page.evaluate(()=>window.__graphSession.retainedTime.history.frames);
      frames.push({cursor:10,range:[0,40],nodes:[1,1,0],edges:[1,0]});
      for(const expected of frames) {
        const cursor=BigInt(expected.cursor);
        await page.evaluate(async ({cursor,expected})=>{const p=window.__graphSession.retainedTime;await p.controller.setCursor(cursor);await p.controller.setRange(...expected.range.map(BigInt));await p.handle.whenIdle();},{cursor,expected});
        const result=await snap(),image=await pixels();results.push({result,image});
        assert.equal(result.selection.refs[0].uuid,'02020202-0202-0202-0202-020202020202');
        assert.deepEqual(Array.from(result.temporal.nodeVisibility),expected.nodes);
        assert.deepEqual(Array.from(result.temporal.edgeVisibility),expected.edges);
        assert.deepEqual(result.temporal.range,expected.range.map(BigInt));
        const renderMembers=await page.evaluate(()=>{const s=window.__graphSession,p=s.retainedTime,r=s.replies.filter(r=>r.owner===p.worker.worker.__graphOwner).at(-1);const get=name=>{const b=s.section(r.bytes,name),v=new DataView(b.buffer,b.byteOffset,b.byteLength);return Array.from({length:b.byteLength/8},(_,i)=>v.getBigUint64(i*8,true));};return {nodes:get('render.node_members.u64'),edges:get('render.edge_members.u64')};});
        assert.deepEqual(renderMembers.nodes,expected.nodes.flatMap((v,i)=>v?[BigInt(i)]:[]));assert.deepEqual(renderMembers.edges,expected.edges.flatMap((v,i)=>v?[BigInt(i)]:[]));
        results.at(-1).renderMembers=renderMembers;
        if(expected.nodes[2]){assert.equal(image.at2[3],0);assert.ok(image.at3[3]>0);if(process.env.XYG_GRAPH_SESSION_REPORT)await page.locator('[data-temporal-fixture]').screenshot({path:process.env.XYG_GRAPH_SESSION_REPORT+'.boundary.png'});}
        else if(expected.nodes[1]) {assert.ok(image.at2[3]>0);assert.equal(result.focusAction.pinned,true);assert.equal(result.focus[0].uuid,'02020202-0202-0202-0202-020202020202');}
      }
      return results;
    });
    await run('retained-temporal-step-play-pause-and-remote-snapshot',async()=>{
      await page.evaluate(async()=>{const p=window.__graphSession.retainedTime;await p.controller.setCursor(19n);await p.controller.step();await p.controller.play();await p.controller.pause();await p.handle.whenIdle();});
      let result=await snap();assert.equal(result.temporal.cursor,await page.evaluate(()=>window.__graphSession.retainedTime.controller.state.cursor));
      await page.evaluate(async()=>{const p=window.__graphSession.retainedTime;await p.controller.applyEvent({groupId:951n,sourceInstance:952n,revision:1n,rangeStart:0n,rangeEnd:40n,cursor:10n,window:40n,selection:[]});await p.handle.whenIdle();});
      result=await snap();assert.equal(result.temporal.cursor,10n);assert.equal(result.focusAction.pinned,true);return result;
    });
    await run('retained-temporal-refused-frame-keeps-picture-state-and-retries',async()=>{
      const before=await snap(), beforePixels=await page.evaluate(()=>window.__graphSession.pixel(window.__graphSession.retainedTime.el));
      // Actual Rust budget refusal, no fake reply. The test changes only the
      // submitted budget field of this one command, retaining original bytes.
      await page.evaluate(()=>{window.__graphSession.inject='temporal-budget';});
      await page.evaluate(async()=>{const p=window.__graphSession.retainedTime;await p.controller.setCursor(20n);await p.handle.whenIdle();});
      assert.deepEqual(await snap(),before);assert.deepEqual(await page.evaluate(()=>window.__graphSession.pixel(window.__graphSession.retainedTime.el)),beforePixels);
      await page.evaluate(async()=>{const p=window.__graphSession.retainedTime;await p.controller.pause();await p.handle.whenIdle();});
      const result=await snap();assert.equal(result.temporal.cursor,20n);assert.deepEqual(result.selection.refs,before.selection.refs);return result;
    });
    await run('retained-temporal-render-refusal-retains-picture-and-refreshes-matching-membership',async()=>{
      const before=await snap(),beforePixels=await page.evaluate(()=>window.__graphSession.pixel(window.__graphSession.retainedTime.el));
      await page.evaluate(async()=>{const s=window.__graphSession,p=s.retainedTime;s.inject='temporal-render-invalid';await p.controller.setCursor(10n);await p.handle.whenIdle();});
      assert.deepEqual(await snap(),before);assert.deepEqual(await page.evaluate(()=>window.__graphSession.pixel(window.__graphSession.retainedTime.el)),beforePixels);
      await page.evaluate(()=>window.__graphSession.retainedTime.handle.refreshRender());
      const refreshed=await snap();assert.equal(refreshed.temporal.cursor,10n);assert.deepEqual(Array.from(refreshed.temporal.nodeVisibility),[1,1,0]);assert.equal(refreshed.focusAction.pinned,true);
      await page.evaluate(async()=>{const p=window.__graphSession.retainedTime;await p.controller.setCursor(20n);await p.handle.whenIdle();});return {before,refreshed};
    });
    await run('retained-temporal-hidden-node-native-pick-does-not-select-hidden-UUID',async()=>{
      await page.keyboard.down('Control');await click(300,165);await page.keyboard.up('Control');
      const result=await snap();assert.deepEqual(result.selection.refs.map(r=>r.uuid),['02020202-0202-0202-0202-020202020202']);
      const pick=await page.evaluate(()=>{const s=window.__graphSession,p=s.retainedTime,r=s.replies.filter(r=>r.owner===p.worker.worker.__graphOwner).at(-1),b=s.section(r.bytes,'pick.header.u32'),v=new DataView(b.buffer,b.byteOffset,b.byteLength);return Array.from({length:b.length/4},(_,i)=>v.getUint32(i*4,true));});assert.equal(pick[4],0);return {result,pick};
    });
    await run('retained-temporal-latest-wins-held-reply-and-disposal',async()=>{
      await page.evaluate(async()=>{const s=window.__graphSession,p=s.retainedTime;s.hold=true;await p.controller.setCursor(19n);});
      await page.waitForFunction(()=>window.__graphSession.held.length>0);
      const before=await snap();
      await page.evaluate(async()=>{const s=window.__graphSession,p=s.retainedTime;p.mark=p.publications.length;const count=s.commands.length;await Promise.all([p.controller.setCursor(10n),p.controller.setCursor(20n)]);if(count!==s.commands.length)throw Error('temporal queue flooded held lane');s.release();await p.handle.whenIdle();});
      const latest=await snap();assert.equal(latest.temporal.cursor,20n);
      const tail=await page.evaluate(()=>{const p=window.__graphSession.retainedTime;return p.publications.slice(p.mark).map(x=>x.temporal.cursor);});assert.deepEqual(tail,[20n]);
      await page.evaluate(async()=>{const s=window.__graphSession,p=s.retainedTime;s.hold=true;await p.controller.setCursor(10n);});
      await page.waitForFunction(()=>window.__graphSession.held.length>0);
      const closed=await page.evaluate(async()=>{const s=window.__graphSession,p=s.retainedTime,n=p.publications.length;const closing=p.handle.dispose();s.release();await closing;await p.controller.setCursor(20n);await p.controller.dispose();await p.clockWorker.dispose();await p.worker.dispose();return {sameSource:p.document.every((v,i)=>v===p.original[i]),noLate:n===p.publications.length,empty:p.el.children.length===0,failures:p.failures,opens:s.commands.filter(c=>c.owner===p.worker.worker.__graphOwner&&c.operation===19).length,updates:s.commands.filter(c=>c.owner===p.worker.worker.__graphOwner&&c.operation===20).length};});
      assert.ok(closed.sameSource&&closed.noLate&&closed.empty);assert.equal(closed.failures.length,2);assert.equal(closed.opens,1);assert.equal(closed.updates,0);return {before,latest,tail,closed};
    });
    await run('retained-temporal-progressive-checkpoint-supersession-and-drain',async()=>{
      await page.evaluate(async()=>{const s=window.__graphSession;await s.temporalFixture(true);s.hold=true;});
      await page.waitForFunction(()=>window.__graphSession.held.length>0);
      await page.evaluate(async()=>{const s=window.__graphSession,p=s.retainedTime;p.mark=p.publications.length;await p.controller.setCursor(20n);p.idle=p.handle.whenIdle();s.release();await p.idle;});
      const result=await page.evaluate(async()=>{const s=window.__graphSession,p=s.retainedTime,r={snapshot:p.handle.snapshot(),tail:p.publications.slice(p.mark).map(x=>x.temporal.cursor),operations:s.commands.filter(c=>c.owner===p.worker.worker.__graphOwner).map(c=>c.operation),failures:p.failures};await p.controller.dispose();await p.handle.dispose();await p.clockWorker.dispose();await p.worker.dispose();return r;});
      assert.equal(result.snapshot.temporal.cursor,20n);assert.deepEqual(Array.from(result.snapshot.temporal.nodeVisibility),[1,0,1]);assert.ok(result.tail.length>0&&result.tail.every(x=>x===20n));assert.ok(result.operations.includes(15));assert.deepEqual(result.failures,[]);return result;
    });
    for (const pending of [false,true]) for (const fault of ['error','messageerror']) {
      await run(`retained-temporal-${pending?'superseded':'idle'}-worker-${fault}-preserves-first-cause`,async()=>{
        await page.evaluate(async pending=>{
          const s=window.__graphSession;await s.temporalFixture(false);
          if(pending){s.hold=true;await s.retainedTime.controller.setCursor(20n);}
        },pending);
        if(pending) await page.waitForFunction(()=>window.__graphSession.held.length>0);
        const result=await page.evaluate(async ({pending,fault})=>{
          const s=window.__graphSession,p=s.retainedTime;
          if(pending) await p.controller.setCursor(30n);
          const before=p.handle.snapshot(), mark=p.publications.length;
          const expected=fault==='error'?'XYG_WASM_WORKER_TRAP':'XYG_WASM_MESSAGE_ERROR';
          if(fault==='error') p.worker.worker.onerror({message:'first idle-or-superseded trap'});
          else p.worker.worker.onmessageerror({});
          const settle=()=>Promise.race([
            p.handle.whenIdle().then(()=>({resolved:true}),e=>({code:e.code,message:e.message})),
            new Promise(r=>setTimeout(()=>r({hung:true}),2000))
          ]);
          const first=await settle();
          // A later lifetime signal must never replace the accepted first cause.
          p.worker.worker.onerror({message:'later replacement cause'});
          const second=await settle(), count=s.commands.length;
          await p.controller.setCursor(40n);s.release();await new Promise(r=>setTimeout(r,0));
          const graphCommands=s.commands.slice(count).filter(c=>c.owner===p.worker.worker.__graphOwner).length;
          const after=p.handle.snapshot(), newPublications=p.publications.length-mark;
          const failures=p.failures.slice();
          await p.handle.dispose();await p.controller.dispose();await p.clockWorker.dispose();await p.worker.dispose();
          return {expected,first,second,graphCommands,newPublications,beforeRevision:before.revision,afterRevision:after.revision,failures};
        },{pending,fault});
        assert.equal(result.first.hung,undefined,'Worker lifetime failure must settle idle without another command');
        assert.equal(result.first.code,result.expected,'first Worker cause must survive supersession');
        assert.deepEqual(result.second,result.first,'later errors must preserve the first cause');
        if(fault==='error')assert.equal(result.first.message,'first idle-or-superseded trap');
        assert.equal(result.graphCommands,0);assert.equal(result.newPublications,0);
        assert.equal(result.afterRevision,result.beforeRevision);
        return result;
      });
    }
    await run('retained-temporal-worker-failure-settles-pending-idle',async()=>{
      await page.evaluate(async()=>{const s=window.__graphSession;await s.temporalFixture(false);s.hold=true;const p=s.retainedTime;p.refresh=p.handle.refreshRender().catch(e=>e.code);});
      await page.waitForFunction(()=>window.__graphSession.held.length>0);
      const result=await page.evaluate(async()=>{
        const s=window.__graphSession,p=s.retainedTime;
        await p.controller.setCursor(20n);
        const idle=p.handle.whenIdle().then(()=>({resolved:true}),e=>({code:e.code}));
        p.worker.worker.onerror({message:'injected terminal Worker failure'});
        const refreshCode=await p.refresh;
        const settled=await Promise.race([idle,new Promise(r=>setTimeout(()=>r({hung:true}),2000))]);
        const mark=s.commands.length;
        await p.controller.setCursor(30n);s.release();await new Promise(r=>setTimeout(r,0));
        const graphCommands=s.commands.slice(mark).filter(c=>c.owner===p.worker.worker.__graphOwner).length;
        await p.handle.dispose();await p.controller.dispose();await p.clockWorker.dispose();await p.worker.dispose();
        return {settled,refreshCode,graphCommands};
      });
      assert.equal(result.settled.hung,undefined,'terminal failure must settle pre-existing idle waiters');
      assert.equal(result.settled.code,result.refreshCode);
      assert.match(result.settled.code,/^XYG_WASM_/);
      assert.equal(result.graphCommands,0,'terminal attachments must ignore further time notifications');
      return result;
    });
    assert.deepEqual(violations,[]);assert.deepEqual(errors,[]);
    if(process.env.XYG_GRAPH_SESSION_REPORT){await writeFile(process.env.XYG_GRAPH_SESSION_REPORT+'.wire.json',JSON.stringify(await page.evaluate(()=>window.__graphSession.temporalWire),null,2)+'\n');await writeFile(process.env.XYG_GRAPH_SESSION_REPORT,JSON.stringify({...evidence,status:'passed',requests,cspViolations:violations,pageErrors:errors},(_,v)=>typeof v==='bigint'?v.toString():v,2)+'\n');
    }
    console.log('PASS public retained temporal presentation');
  } else if (process.env.XYG_GRAPH_SCHEDULING_ONLY) {
    await run('capture-waits-for-recorded-request-reply',()=>graphCaptureCase(page));
    await run('public-resource-refusals-unchanged-arenas',async()=>{
      const result=await page.evaluate(async()=>{
        const s=window.__graphSession,out=[];
        for(const [count,arena] of [[1000,16*1024*1024],[10000,384*1024*1024]]){
          const at=performance.now();try{await s.progressiveFixture(count,BigInt(8000+count),{},arena);
            const p=s.progressives.at(-1);clearInterval(p.timer);await p.handle.dispose();await p.worker.dispose();p.el.remove();out.push({count,arena,status:'opened',ms:performance.now()-at});}
          catch(e){out.push({count,arena,status:'refused',code:e.code,message:e.message,ms:performance.now()-at});}
        }return out;
      });
      evidence.refusals=result;
      assert.equal(result[0].status,'opened');
      return result;
    });
    await run('public-1k-unheld-pick-camera-isolation-cleanup', async () => {
      await page.evaluate(async () => {
        const s=window.__graphSession;
        await Promise.all([s.progressiveFixture(1000,7101n),s.progressiveFixture(1000,7102n)]);
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
      const result=await page.evaluate(async()=>{
        const s=window.__graphSession,out=[];
        for(const p of [7101n,7102n].map(id=>s.progressives.find(p=>p.id===id))) {
          await s.waitForCapture(p);
          const at=performance.now(),frames=p.frames.length,finalSnapshot=p.handle.snapshot();const owner=p.worker.worker.__graphOwner;
          const b64=b=>{let t='';for(let i=0;i<b.length;i+=16384)t+=String.fromCharCode(...b.subarray(i,i+16384));return btoa(t);};
          const replay=await Promise.all(s.commands.filter(c=>c.owner===owner&&c.bytes).map(async c=>{const r=s.replies.find(r=>r.owner===owner&&r.requestId===c.requestId);const h=await crypto.subtle.digest('SHA-256',r.bytes);return {operation:c.operation,request:b64(c.bytes),replyBytes:r.bytes.length,replySha256:Array.from(new Uint8Array(h),b=>b.toString(16).padStart(2,'0')).join('')};}));const commands=s.commands.filter(c=>c.owner===owner);const replies=s.replies.filter(c=>c.owner===owner);
          clearInterval(p.timer);await p.handle.dispose();await p.worker.dispose();
          out.push({id:p.id,replay,finalSnapshot,started:p.started,workerReady:p.workerReady,captures:p.captures,arena:p.arena,actualArena:p.worker.worker.__actualArena,defaultArena:p.defaultArena,requestedArena:p.worker.__requestedArena??null,sourceNodes:1000,sourceEdges:1000,painted:p.painted,clicks:p.clicks,payloadBytes:{requests:commands.reduce((n,c)=>n+c.bytes.length,0),replies:replies.reduce((n,c)=>n+c.bytes.length,0)},frames:p.frames,errors:p.errors,heartbeats:p.heartbeats,selections:p.selections,pans:p.pans,keys:p.keys,
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
      for(const p of result){assert.equal(p.actualArena,16*1024*1024);assert.equal(p.arena,16*1024*1024);assert.equal(p.defaultArena,true);assert.equal(p.requestedArena,null);assert.deepEqual(p.errors,[]);assert.equal(p.held,0);assert.equal(p.disposed,true);assert.equal(p.attachmentChildren,0);assert.equal(p.frames.length,p.framesAtDispose);assert.ok(p.commands.filter(c=>c.operation).every(c=>String(c.instanceId)===String(p.id)));assert.ok(new Set(p.painted.filter(f=>!f.progress.done&&f.pixels>0).map(f=>f.progress.steps)).size>3);assert.ok(new Set(p.painted.map(f=>f.hash)).size>3);assert.ok(p.frames.filter(f=>!f.progress.done&&f.pixels>0).length>3);assert.ok(p.frames.at(-1).progress.done);}
      const primary=result.find(p=>p.id===7101n),secondary=result.find(p=>p.id===7102n);
      assert.ok(primary&&secondary);
      assert.ok(primary.selections.some(e=>e.snapshot.outcome.selected>0&&!e.snapshot.relayout?.done),'trusted unfinished pick');
      assertProgressiveCameraPan(primary);
      assert.ok(primary.clicks.some(e=>e.trusted&&e.prevented&&!e.progress?.done));
      assert.equal(secondary.selections.length,0);assert.equal(secondary.finalSnapshot.selection.refs.length,0);assert.equal(secondary.finalSnapshot.camera[2],320);assert.deepEqual(violations,[]);assert.deepEqual(errors,[]);
      return result;
    });
    await run("public-1k-trusted-keyboard-focus-retention",()=>graphProgressiveKeyboardCase(page,process.env.XYG_GRAPH_SESSION_REPORT));
    await run('default1k-coalescing-stale-terminal-disposal',progressiveFaultCase);
    if(process.env.XYG_GRAPH_SESSION_REPORT)await writeFile(process.env.XYG_GRAPH_SESSION_REPORT,JSON.stringify(evidence,(_,v)=>typeof v==='bigint'?String(v):v,2)+'\n');
  } else if (process.env.XYG_GRAPH_PROGRESSIVE_ONLY) {
    const delay = ms => new Promise(r=>setTimeout(r,ms));
    for (const count of [0,4,1000]) {
      await run(`public-progressive-${count}-unheld-painter-heartbeat`, async()=>{
        const id=BigInt(2000+count);
        const initial=await page.evaluate(({count,id})=>window.__graphSession.progressiveFixture(count,id),{count,id});
        if(count===4) {
          const surface=page.locator('[data-xy-graph-session]').last();
          await surface.focus();
          for(let attempt=0;attempt<30;attempt++) {
            await page.keyboard.press('ArrowRight');
            if(await page.evaluate(()=>window.__graphSession.progressives.at(-1).handle.snapshot()?.focus.length>0)) break;
            await delay(5);
          }
        }
        await page.waitForFunction(()=>{const p=window.__graphSession.progressives.at(-1);return p.handle.snapshot()?.relayout?.done||p.errors.length;},null,{timeout:40000});
        const result=await page.evaluate(()=>{const p=window.__graphSession.progressives.at(-1);return {frames:p.frames,errors:p.errors,beats:p.beats,focus:p.handle.snapshot()?.focus,held:window.__graphSession.held.length,trusted:p.trusted,heartbeats:p.heartbeats,commands:window.__graphSession.commands.filter(c=>c.instanceId===p.id).map(c=>({at:c.at,operation:c.operation}))};});
        assert.deepEqual(result.errors,[]); assert.equal(result.held,0);
        const firstStep=result.commands.find(c=>c.operation===15);
        if(firstStep) assert.ok(firstStep.at>result.frames[0].at);
        assert.equal(result.frames.at(-1).progress.done,true);
        if(count) { assert.ok(result.frames.length>3); assert.ok(result.frames.some(f=>f.pixels>0)); if(count===4) { assert.ok(result.focus.length>0); assert.ok(result.trusted.some(e=>e.prevented&&!e.progress?.done)); } assert.ok(result.beats>3); assert.ok(result.frames[0].progress.steps < result.frames.at(-1).progress.steps); }
        else assert.equal(result.frames[0].progress.steps,0n);
        if(count===4 && process.env.XYG_GRAPH_SESSION_REPORT) {
          const capture=await page.evaluate(()=>{const s=window.__graphSession,p=s.progressives.at(-1),b64=b=>btoa(String.fromCharCode(...b));return s.commands.filter(c=>c.owner===p.worker.worker.__graphOwner).map(c=>({operation:c.operation,request:b64(c.bytes),reply:b64(s.replies.find(r=>r.owner===c.owner&&r.requestId===c.requestId)?.bytes??[])}));});
          await writeFile(process.env.XYG_GRAPH_SESSION_REPORT+'.replay.json',JSON.stringify(capture,null,2)+'\n');
        }
        await page.evaluate(async()=>{const p=window.__graphSession.progressives.at(-1);clearInterval(p.timer);await p.handle.dispose();await p.worker.dispose();p.el.remove();});
        return {initial,...result};
      });
    }
    await run('progressive-companion-page-survives-step-and-row-selection', async()=>{
      await page.evaluate(async()=>{
        const s=window.__graphSession;
        await s.progressiveFixture(64, 3064n, {}, 384*1024*1024);
        const p=s.progressives.at(-1);
        p.el.dataset.progressivePaging=''; p.pages=[]; p.choices=[]; p.choiceProgress=[];
        p.firstRefs=p.handle.snapshot().companion.refs;
        p.el.addEventListener('xy:graph-render',()=>{
          const command=s.commands.filter(c=>c.owner===p.worker.worker.__graphOwner).at(-1);
          if(![17,21].includes(command?.operation)) return;
          const bytes=s.section(command.bytes,'companion.u32');
          if(new DataView(bytes.buffer,bytes.byteOffset,bytes.byteLength).getUint32(0,true)!==1) return;
          const snapshot=p.handle.snapshot();
          p.pages.push({operation:command.operation,progress:snapshot.relayout,
            rows:snapshot.companion.rows,refs:snapshot.companion.refs,
            displayed:[...p.el.querySelectorAll('tbody tr')].map(row=>[...row.querySelectorAll('td')].slice(0,-1).map(cell=>cell.textContent))});
        });
        p.el.addEventListener('xy:graph-select',e=>{p.choices.push(e.detail.selection.refs);p.choiceProgress.push(e.detail.relayout);});
      });
      const next=page.locator('[data-progressive-paging] button[aria-label="Next graph companion page"]');
      await next.focus();
      for(let attempt=0;attempt<30;attempt++) {
        if(await page.evaluate(()=>window.__graphSession.progressives.at(-1).pages.length>0)) break;
        await page.keyboard.press('Enter');
        if(await page.evaluate(()=>window.__graphSession.progressives.at(-1).pages.length>0)) break;
        await delay(5);
      }
      await page.waitForFunction(()=>window.__graphSession.progressives.at(-1).pages.some(p=>p.operation===21),null,{timeout:10000});
      const before=await page.evaluate(()=>{const p=window.__graphSession.progressives.at(-1);return {pages:p.pages,firstRefs:p.firstRefs};});
      assert.equal(before.pages[0].operation,17);
      assert.equal(before.pages[0].progress.done,false);
      const expected=before.pages[0];
      assert.equal(expected.rows.length,50); assert.equal(expected.refs.length,50);
      assert.notDeepEqual(expected.refs,before.firstRefs);
      const stepped=before.pages.filter(p=>p.operation===21);
      assert.ok(stepped.length>0); assert.ok(stepped[0].progress.steps>expected.progress.steps);
      assert.equal(stepped[0].progress.done,false);
      for(const publication of before.pages) {
        assert.deepEqual(publication.rows,expected.rows);
        assert.deepEqual(publication.refs,expected.refs);
        assert.deepEqual(publication.displayed,publication.rows);
      }
      for(let attempt=0;attempt<30;attempt++) {
        if(await page.evaluate(()=>window.__graphSession.progressives.at(-1).choices.length>0)) break;
        await page.evaluate(()=>window.__graphSession.progressives.at(-1).el.querySelector('tbody button').focus());
        await page.keyboard.press('Enter');
        if(await page.evaluate(()=>window.__graphSession.progressives.at(-1).choices.length>0)) break;
        await delay(5);
      }
      const result=await page.evaluate(async()=>{
        const s=window.__graphSession,p=s.progressives.at(-1);
        const commands=s.commands.filter(c=>c.owner===p.worker.worker.__graphOwner);
        const result={count:64,arenaBytes:384*1024*1024,delivery:"Playwright keyboard.press Enter",pages:p.pages,choices:p.choices,choiceProgress:p.choiceProgress,errors:p.errors,held:s.held.length,
          operations:commands.map(c=>c.operation)};
        clearInterval(p.timer); await p.handle.dispose(); await p.worker.dispose(); p.el.remove();
        return result;
      });
      assert.deepEqual(result.errors,[]); assert.equal(result.held,0);
      for(const publication of result.pages) {
        assert.deepEqual(publication.rows,expected.rows);
        assert.deepEqual(publication.refs,expected.refs);
        assert.deepEqual(publication.displayed,publication.rows);
      }
      assert.deepEqual(result.choices[0],[expected.refs[0]]);
      assert.equal(result.choiceProgress[0].done,false);
      const paging=result.operations.indexOf(17), step=result.operations.indexOf(15,paging+1);
      assert.ok(paging>=0&&step>paging); assert.equal(result.operations[step+1],21);
      assert.ok(result.operations.includes(11));
      return result;
    });
    await run('1k-default-arena-opens-without-override',async()=>{
      const code=await page.evaluate(async()=>{try{await window.__graphSession.progressiveFixture(1000,3099n);const p=window.__graphSession.progressives.at(-1);clearInterval(p.timer);await p.handle.dispose();await p.worker.dispose();p.el.remove();return 'opened';}catch(e){return e.code;}});
      assert.equal(code,'opened');return {code,arenaBytes:16*1024*1024};
    });
    await run('authored-pinned-progressive-and-explicit-false-legacy',async()=>{
      const results=[];
      for(const progressive of [true,false]) {
        const initial=await page.evaluate(progressive=>window.__graphSession.progressiveFixture(4,3100n,{progressive,x:[0,1,2,3],y:[0,0,0,0],pinned:[1,0,0,0]}),progressive);
        assert.equal(initial.progress,null);
        if(progressive) await page.waitForFunction(()=>window.__graphSession.progressives.at(-1).handle.snapshot()?.relayout?.done,null,{timeout:40000});
        else await delay(100);
        results.push(await page.evaluate(async()=>{const s=window.__graphSession,p=s.progressives.at(-1),commands=s.commands.filter(c=>c.owner===p.worker.worker.__graphOwner),replies=s.replies.filter(r=>r.owner===p.worker.worker.__graphOwner),centers=replies.filter(r=>{try{s.section(r.bytes,'paint.node.center.f64');return true;}catch{return false;}}).map(r=>s.values(r.bytes,'paint.node.center.f64').slice(0,2));const result={progress:p.handle.snapshot().relayout,centers,steps:commands.filter(c=>c.operation===15).length,errors:p.errors};clearInterval(p.timer);await p.handle.dispose();await p.worker.dispose();p.el.remove();return result;}));
        const r=results.at(-1);assert.deepEqual(r.errors,[]);assert.ok(r.centers.every(c=>JSON.stringify(c)===JSON.stringify(r.centers[0])));
        assert.equal(progressive ? r.progress.done : r.steps===0,true);
      }
      return results;
    });
    await run('two-independent-progressive-attachments-dispose-recreate',async()=>{
      await page.evaluate(async()=>{const s=window.__graphSession;await Promise.all([s.progressiveFixture(4,3001n),s.progressiveFixture(4,3002n)]);});
      await page.evaluate(async()=>{const s=window.__graphSession,p=s.progressives.at(-2);clearInterval(p.timer);await p.handle.dispose();await p.worker.dispose();p.el.remove();await s.progressiveFixture(4,3001n);});
      await page.waitForFunction(()=>window.__graphSession.progressives.slice(-2).every(p=>p.handle.snapshot()?.relayout?.done),null,{timeout:40000});
      return page.evaluate(async()=>{const ps=window.__graphSession.progressives.slice(-2),result=ps.map(p=>({id:p.id,frames:p.frames.length,errors:p.errors}));for(const p of ps){clearInterval(p.timer);await p.handle.dispose();await p.worker.dispose();p.el.remove();}return result;});
    });
    await run('progressive-stale-terminal-dispose-late-reply-cleanup',progressiveFaultCase);
    assert.deepEqual(violations,[]); assert.deepEqual(errors,[]);
    if(process.env.XYG_GRAPH_SESSION_REPORT) await writeFile(process.env.XYG_GRAPH_SESSION_REPORT,JSON.stringify(evidence,(_,v)=>typeof v==='bigint'?v.toString():v,2)+'\n');
    console.log('PASS public progressive attachment');
  } else {
  await run("default16MiB-compose-attach-GPU-lastgood-signed-camera", () => check(() => {
    const s = window.__graphSession, pixel = s.pixel(s.el), image = pixel.some((v, i) => i % 4 === 3 && v > 0), before = s.handle.snapshot();
    s.initialPixels = pixel; s.initial = before;
    return { ok: image && before.camera[0] === -1 && before.outcome.selected === 0 && s.el.querySelectorAll("tbody tr").length > 0, revision: before.revision, nodes: s.load.x.length, pixels: pixel.filter((v, i) => i % 4 === 3 && v > 0).length };
  }));
  await run("real-Tab-in-arrows-visible-focus-same-revision-unchangedgeometry", async () => {
    await page.locator("#sentinel-before").focus(); await page.keyboard.press("Tab");
    assert.equal(await page.evaluate(() => document.activeElement === window.__graphSession.surface()), true);
    await page.keyboard.press("ArrowRight"); await page.evaluate(() => window.__graphSession.waitIdle());
    if (process.env.XYG_GRAPH_SESSION_SCREENSHOT) await page.screenshot({ path: process.env.XYG_GRAPH_SESSION_SCREENSHOT, clip: { x: 0, y: 0, width: 660, height: 560 } });
    return check(() => {
      const s = window.__graphSession, current = s.snapshot(), replies = s.replies.filter(r => { try { s.section(r.bytes, "gpu.header.u32"); return true; } catch { return false; } });
      const geometry = r => ["gpu.node.coord.bytes", "gpu.shaft.coord.bytes", "gpu.head.coord.bytes", "gpu.frame.coord.bytes"].flatMap(name => { const out = []; for (let i = 0; i < (name.includes("head") ? 6 : name.includes("node") ? 2 : 4); i++) out.push([...s.section(r.bytes, name, i)].join(",")); return out; }).join(";");
      return { ok: current.focus.length === 1 && current.revision === s.initial.revision && JSON.stringify(s.pixel(s.el)) !== JSON.stringify(s.initialPixels) && geometry(replies[0]) === geometry(replies.at(-1)), revision: current.revision, focus: current.focus, summary: current.summary };
    });
  });
  await run("Enter-replace-CtrlMetaToggle-Escape-authoritative-empty-propagates", async () => check(async () => {
    const s = window.__graphSession; await s.key("Enter"); const selected = s.snapshot(); await s.key("Enter", { ctrlKey: true }); const toggled = s.snapshot(); await s.key("Enter", { metaKey: true }); const meta = s.snapshot(); const cleared = await s.key("Escape"), empty = await s.key("Escape");
    const result = s.snapshot(); return { ok: selected.outcome.selected > 0 && selected.selection.refs.length > 0 && toggled.outcome.selected === 0 && meta.outcome.selected > 0 && cleared && !empty && result.outcome.selected === 0 && !result.outcome.stateChanged && s.el.querySelector('[aria-live="polite"]').textContent === result.summary, selected: selected.selection, globalCount: selected.outcome.selected, focusAction: selected.focusAction };
  }));
  await run("observer-exception-isolated-and-reduced-motion-static-focus", () => check(async () => {
    const s = window.__graphSession, surface = s.surface();
    let observed = false;
    const onError = event => { if (event.message.includes("test observer failure")) { observed = true; event.preventDefault(); } };
    const listener = () => { throw new Error("test observer failure"); };
    window.addEventListener("error", onError); surface.addEventListener("xy:graph-focus", listener);
    await s.key("ArrowRight"); surface.removeEventListener("xy:graph-focus", listener); window.removeEventListener("error", onError);
    const before = s.pixel(s.el); await new Promise(r => setTimeout(r, 100));
    return { ok: observed && s.snapshot().focus.length === 1 && matchMedia("(prefers-reduced-motion: reduce)").matches && JSON.stringify(before) === JSON.stringify(s.pixel(s.el)), observed };
  }));
  await run("Tab-forward-back-out-no-trap", async () => {
    await page.locator('[data-xy-graph-session]').focus(); await page.keyboard.press("Shift+Tab"); assert.equal(await page.locator("#sentinel-before").evaluate(el => el === document.activeElement), true);
    await page.locator('[data-xy-graph-session]').focus();
    for (let i = 0; i < 100 && !(await page.locator("#sentinel-after").evaluate(el => el === document.activeElement)); i++) await page.keyboard.press("Tab");
    assert.equal(await page.locator("#sentinel-after").evaluate(el => el === document.activeElement), true);
    await page.keyboard.press("Shift+Tab"); assert.equal(await page.locator("#sentinel-after").evaluate(el => el === document.activeElement), false);
    return { ok: true };
  });
  await run("duplicate-attach-and-competing-product-lanes-refuse-before-mutation", () => check(async () => {
    const s = window.__graphSession, original = s.snapshot(), rejected = [];
    for (const op of [() => s.attach({ el: s.container(), worker: s.worker, instanceId: 2n, document: s.document, camera: s.camera }), () => s.worker.acquireGeoTransport(), () => s.compose(s.worker, s.input), () => s.worker.temporalGraphCommand(new ArrayBuffer(32))]) {
      try { await op(); rejected.push(false); } catch (e) { rejected.push(e.code === "GF_INTERACTION_INVALID"); }
    }
    const raw = [];
    for (const type of ["geo.transport.acquire", "scene.compile", "temporal_graph.command"]) raw.push(await s.raw({ type }));
    await s.handle.refreshRender(); return { ok: raw.every(r => !r.ok && r.error.code === "GF_INTERACTION_INVALID" && !("value" in r)) && rejected.every(Boolean) && s.json(original.selection) === s.json(s.snapshot().selection), rejected };
  }));
  await run("wrong-instance-Rust-refusal-and-malformedGPU-retain-lastgood-stale-requires-refresh", () => check(async () => {
    const s = window.__graphSession, old = s.snapshot(), pixels = s.pixel(s.el), refusals = [];
    for (const [inject, code] of [["wrong-instance", "GF_INTERACTION_INVALID"], ["malformed-gpu", "GF_INTERACTION_INVALID"], ["stale", "GF_INTERACTION_STALE"]]) {
      s.inject = inject;
      if (inject === "stale") { await s.key("ArrowRight"); refusals.push(s.events.at(-1)?.kind === "stale"); }
      else { try { await s.handle.refreshRender(); refusals.push(false); } catch (e) { refusals.push(e.code === code); } }
      if (JSON.stringify(s.pixel(s.el)) !== JSON.stringify(pixels) || s.snapshot().revision !== old.revision) return { ok: false, inject, reason: "lastgood changed" };
      const count = s.commands.length, swallowed = await s.key("Enter");
      if (inject !== "wrong-instance" && (count !== s.commands.length || swallowed)) return { ok: false, inject, reason: "stale replay" };
      if (inject === "wrong-instance") { await s.key("Escape"); }
      await s.handle.refreshRender();
    }
    return { ok: refusals.every(Boolean) && s.events.some(e => e.kind === "stale"), refusals };
  }));
  await run("one-outstanding-action-busy-unaccepted-keys-and-queued-double-disposal-no-lateevents", () => check(async () => {
    const s = window.__graphSession, el = s.container(), worker = s.makeWorker(); await worker.ready;
    const h = s.attach({ el, worker, instanceId: 1n, document: s.document, load: s.load, camera: s.camera }); await h.ready;
    let events = 0; el.addEventListener("xy:graph-render", () => events++); const surface = el.querySelector('[role="application"]');
    s.hold = true; const render = h.refreshRender();
    for (let i = 0; i < 200 && !s.held.length; i++) await new Promise(r => setTimeout(r, 5));
    const ignored = new KeyboardEvent("keydown", { key: "Enter", cancelable: true, bubbles: true }); surface.dispatchEvent(ignored);
    let busyCode; try { await h.refreshRender(); } catch (e) { busyCode = e.code; }
    const a = h.dispose(), b = h.dispose(); const immediate = !el.children.length && !surface.hasAttribute("role"); s.release(); await Promise.allSettled([render]); await a;
    const reopened = await s.compose(worker, s.input).result; await worker.dispose();
    return { ok: busyCode === "XYG_WASM_GRAPH_BUSY" && a === b && immediate && !ignored.defaultPrevented && events === 0 && reopened.nodeUuid.length > 0, events };
  }));
  await run("constructor-render-failure-closes-session-and-borrowedWorker-survives", () => check(async () => {
    const s = window.__graphSession, worker = s.makeWorker(); await worker.ready; const el = s.container();
    const h = s.attach({ el, worker, instanceId: 2n, document: s.document, load: s.load, camera: [0, 1, 0, 0, 640, 320, 1] });
    let code; try { await h.ready; } catch (e) { code = e.code; } await h.dispose();
    const composed = await s.compose(worker, s.input).result; await worker.dispose();
    return { ok: code === "GF_INTERACTION_INVALID" && !el.children.length && composed.nodeUuid.length > 0, code };
  }));
  await run("twoWorkers-independent-lifetimes-and-wrong-envelope-terminal", () => check(async () => {
    const s = window.__graphSession, worker = s.makeWorker(); await worker.ready; const el = s.container();
    const h = s.attach({ el, worker, instanceId: 9007199254740993n, document: s.document, load: s.load, camera: s.camera }); await h.ready;
    const previous = h.snapshot(); s.inject = "wrong-lifetime"; let code; try { await h.refreshRender(); } catch (e) { code = e.code; } await h.dispose(); await worker.dispose();
    await s.handle.refreshRender(); return { ok: code === "XYG_WASM_MESSAGE_ERROR" && previous.outcome.selected === 0 && s.snapshot().outcome.selected === 0, code };
  }));
  await run("dirty-shared-sampler-unit2-preserves-exact-shipped-graph-pixels", () => check(async () => {
    const s = window.__graphSession, host = globalThis[Symbol.for("reflex-dev.xy.shared-webgl-host.v1")].get(document), gl = host.gl;
    await s.handle.refreshRender(); const before = s.pixel(s.el);
    const sampler = gl.createSampler(); gl.samplerParameteri(sampler, gl.TEXTURE_MIN_FILTER, gl.LINEAR); gl.samplerParameteri(sampler, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
    gl.bindSampler(2, sampler); await s.handle.refreshRender(); const dirty = s.pixel(s.el);
    const cleanup = [];
    for (let i = 0; i < 3; i++) { gl.activeTexture(gl.TEXTURE0 + i); cleanup.push(gl.getParameter(gl.SAMPLER_BINDING) === null && gl.getParameter(gl.TEXTURE_BINDING_2D) === null); }
    gl.activeTexture(gl.TEXTURE0); gl.deleteSampler(sampler);
    await s.handle.refreshRender(); const clean = s.pixel(s.el);
    const difference = actual => actual.reduce((count, value, i) => count + Number(value !== before[i]), 0);
    return { ok: difference(dirty) === 0 && difference(clean) === 0 && cleanup.every(Boolean) && gl.getError() === gl.NO_ERROR, changedChannels: { dirty: difference(dirty), clean: difference(clean) }, cleanup };
  }));
  await run("context-loss-restore-exact-last-picture-and-legacy-path-unreachable", () => check(async () => {
    const s = window.__graphSession, gl = s.gl.findLast(gl => !gl.isContextLost()), ext = gl.getExtension("WEBGL_lose_context"), before = s.pixel(s.el); ext.loseContext();
    await new Promise(r => setTimeout(r, 30)); ext.restoreContext(); await new Promise(r => setTimeout(r, 150));
    return { ok: !gl.isContextLost() && JSON.stringify(before) === JSON.stringify(s.pixel(s.el)) && s.legacyCalls.length === 0, legacyCalls: s.legacyCalls };
  }));
  await run("Rust-paged-companion51-aligned-rowSelect-textContent-focus-preservation", () => check(async () => {
    const s = window.__graphSession, worker = s.makeWorker(); await worker.ready;
    const arrow = new Uint8Array(await (await fetch("/tests/fixtures/graphforge/session_companion_nodes.arrow")).arrayBuffer());
    const composed = await s.compose(worker, { base: { tables: [arrow] } }).result, el = s.container();
    const h = s.attach({ el, worker, instanceId: 51n, document: composed.bytes, load: { x: Array.from({ length: 51 }, (_, i) => 20 + i * 8), y: Array(51).fill(50) }, camera: [1, 1, 0, 0, 640, 320, 1] }); await h.ready;
    const textSafe = !el.querySelector("img") && el.querySelector("tbody").textContent.includes("<img>");
    const first = h.snapshot(), button = el.querySelector('button[aria-label="Next graph companion page"]'); button.focus(); button.click(); await s.waitIdle(el);
    const second = h.snapshot(), focus = document.activeElement === button, rows = el.querySelectorAll("tbody tr").length;
    const aligned = second.companion.refs[0];
    el.querySelector('button[aria-label="Previous graph companion page"]').click(); await s.waitIdle(el);
    const previousRows = h.snapshot().companion.rows.length;
    button.click(); await s.waitIdle(el);
    el.querySelector("tbody button").click(); await s.waitIdle(el); const selected = h.snapshot();
    await h.dispose(); await worker.dispose();
    return { ok: first.companion.rows.length === 50 && first.companion.total === 51 && second.companion.rows.length === 1 && rows === 1 && previousRows === 50 && focus && s.json(selected.selection.refs[0]) === s.json(aligned) && textSafe, focus, textSafe, selectedRefs: selected.selection.refs, total: first.companion.total, pageLengths: [first.companion.rows.length, second.companion.rows.length], escaped: first.companion.rows[0], aligned };
  }));
  await run("trusted-dialog-Escape-Rust-applicability-admission-and-refusal", async () => {
    const results = [];
    await page.evaluate(() => {
      const dialog = document.createElement("dialog"), button = document.createElement("button"); button.textContent = "Control"; dialog.append(button); document.body.append(dialog);
      window.__graphSession.dialogControl = { dialog, cancels: [] }; dialog.addEventListener("cancel", e => window.__graphSession.dialogControl.cancels.push(e.isTrusted)); dialog.showModal(); button.focus();
    });
    await page.keyboard.press("Escape");
    await page.waitForFunction(() => !window.__graphSession.dialogControl.dialog.open);
    assert.deepEqual(await page.evaluate(() => window.__graphSession.dialogControl.cancels), [true]);
    results.push({ case: "native-control-closes", ok: true });
    await page.evaluate(() => window.__graphSession.createDialog());
    const reopen = () => page.evaluate(() => { const d = window.__graphSession.dialog; if (!d.dialog.open) d.dialog.showModal(); d.surface.focus(); });
    const idle = () => page.evaluate(() => window.__graphSession.waitIdle(window.__graphSession.dialog.el));
    const escape = async (staysOpen, label) => {
      await page.keyboard.press("Escape"); await page.waitForTimeout(40);
      const result = await page.evaluate(() => {
        const d = window.__graphSession.dialog;
        return { open: d.dialog.open, key: d.keys.at(-1), cancels: d.cancels.length, applicable: d.handle.snapshot()?.clearAction.applicable };
      });
      assert.equal(result.open, staysOpen, `${label}: ${JSON.stringify(result)}`);
      assert.equal(result.key.trusted, true); assert.equal(result.key.prevented, staysOpen);
      results.push({ case: label, ...result });
    };
    await escape(false, "empty-native-default"); await idle();
    await reopen(); await page.keyboard.press("ArrowRight"); await idle();
    assert.equal(await page.evaluate(() => window.__graphSession.dialog.handle.snapshot().clearAction.applicable), false);
    await escape(false, "focus-only-native-default"); await idle();
    await reopen(); await page.keyboard.press("Enter"); await idle();
    assert.equal(await page.evaluate(() => window.__graphSession.dialog.handle.snapshot().clearAction.applicable), true);
    await escape(true, "selected-synchronously-cancels"); await idle();
    assert.equal(await page.evaluate(() => window.__graphSession.dialog.handle.snapshot().outcome.selected), 0);
    await escape(false, "cleared-native-default"); await idle();
    await reopen(); await page.keyboard.press("Enter"); await idle();
    await page.evaluate(() => { const s = window.__graphSession; s.hold = true; s.dialog.pending = s.dialog.handle.refreshRender(); });
    await page.waitForFunction(() => window.__graphSession.held.length > 0);
    const busyCount = await page.evaluate(() => window.__graphSession.commands.length);
    await escape(false, "busy-ignores-old-true-fact");
    assert.equal(await page.evaluate(() => window.__graphSession.commands.length), busyCount);
    await page.evaluate(async () => { const s = window.__graphSession; s.release(); await s.dialog.pending; });
    await reopen(); await page.evaluate(() => { window.__graphSession.inject = "stale"; }); await page.keyboard.press("ArrowRight"); await idle();
    const staleCount = await page.evaluate(() => window.__graphSession.commands.length);
    await escape(false, "stale-ignores-old-true-fact");
    assert.equal(await page.evaluate(() => window.__graphSession.commands.length), staleCount);
    await page.evaluate(() => window.__graphSession.dialog.handle.refreshRender());
    for (const inject of ["malformed-clear", "missing-clear"]) {
      await reopen();
      const refused = await page.evaluate(async inject => {
        const s = window.__graphSession, d = s.dialog, before = s.json(d.handle.snapshot()), pixels = s.pixel(d.el); s.inject = inject;
        let code; try { await d.handle.refreshRender(); } catch(e) { code = e.code; }
        return code === "GF_INTERACTION_INVALID" && before === s.json(d.handle.snapshot()) && JSON.stringify(pixels) === JSON.stringify(s.pixel(d.el));
      }, inject);
      assert.equal(refused, true, inject);
      const count = await page.evaluate(() => window.__graphSession.commands.length);
      await escape(false, `${inject}-ignores-old-true-fact`);
      assert.equal(await page.evaluate(() => window.__graphSession.commands.length), count);
      await page.evaluate(() => window.__graphSession.dialog.handle.refreshRender());
    }
    await reopen(); await page.evaluate(() => { window.__graphSession.inject = "refuse-clear"; });
    await escape(true, "locally-accepted-then-Rust-refused-default-already-cancelled"); await idle();
    assert.equal(await page.evaluate(() => {
      const d = window.__graphSession.dialog; return d.handle.snapshot().clearAction.applicable && d.handle.snapshot().outcome.selected > 0 && d.errors.at(-1)?.code === "GF_INTERACTION_INVALID";
    }), true);
    // Terminal state must not consume the preceding true applicability fact.
    await page.evaluate(async () => { const s = window.__graphSession; s.inject = "wrong-lifetime"; try { await s.dialog.handle.refreshRender(); } catch {} });
    await escape(false, "terminal-ignores-old-true-fact");
    await page.evaluate(async () => { const d = window.__graphSession.dialog; await d.handle.dispose(); await d.worker.dispose(); d.dialog.remove(); });
    await page.evaluate(() => window.__graphSession.createDialog());
    await page.keyboard.press("ArrowRight"); await idle(); await page.keyboard.press("Enter"); await idle();
    assert.equal(await page.evaluate(() => window.__graphSession.dialog.handle.snapshot().clearAction.applicable), true);
    // Ending the borrowed Worker's lifetime makes lane admission fail while
    // the controller still displays its preceding true fact. It must not cancel.
    await page.evaluate(() => window.__graphSession.dialog.worker.dispose());
    await escape(false, "failed-local-lane-admission-does-not-cancel");
    assert.equal(await page.evaluate(() => window.__graphSession.dialog.errors.at(-1)?.code), "XYG_WASM_DISPOSED");
    await page.evaluate(async () => {
      const d = window.__graphSession.dialog; await d.handle.dispose();
      // Deliver a trusted native key to the old surface after cleanup. No
      // controller listener/fact may survive even if an owner reuses its DOM.
      d.dialog.append(d.surface); d.surface.tabIndex = 0; d.dialog.showModal(); d.surface.focus();
    });
    await escape(false, "disposed-surface-has-no-old-fact-listener");
    await page.evaluate(() => { const s = window.__graphSession; s.dialog.dialog.remove(); s.dialogControl.dialog.remove(); });
    return { ok: true, results };
  });
  if (!process.env.XYG_GRAPH_POINTER_BASELINE) {
    const pointerSnapshot = () => page.evaluate(() => window.__graphSession.pointerSnapshot());
    const pointerIdle = () => page.evaluate(() => { const s=window.__graphSession; return s.waitIdle(s.pointer.el); });
    const click = async (kind, index=0, modifiers=[]) => {
      await page.locator('[data-pointer-fixture] canvas').scrollIntoViewIfNeeded();
      const point = await page.evaluate(([kind,index]) => { const s=window.__graphSession; const css=s.pointerPoint(kind,index); return {css,client:s.pointerClient(css),count:s.commands.length,products:s.products.length}; }, [kind,index]);
      for(const key of modifiers) await page.keyboard.down(key);
      try { await page.mouse.click(...point.client.map(Math.round)); } finally { for(const key of modifiers.reverse()) await page.keyboard.up(key); }
      await pointerIdle();
      const raw = await page.evaluate(() => { const s=window.__graphSession,c=s.commands.at(-1); return {count:s.commands.length,products:s.products.slice(-1),operation:c.operation,revision:c.revision,coordinates:s.values(c.bytes,'coordinates.f64'),event:s.pointer.trusted.at(-1),words:[...new Uint32Array(s.section(c.bytes,'header.u32').slice().buffer)]}; });
      assert.equal(raw.count,point.count+1); assert.equal(raw.operation,1);
      assert.deepEqual(await page.evaluate(start=>window.__graphSession.products.slice(start),point.products),["graph.session.interact"]);
      assert.equal(raw.event.trusted,true);assert.equal(raw.event.canvas,true);
      if(process.env.XYG_GRAPH_NATIVE_BASELINE) {
      const delivered=await page.evaluate(event=>{const s=window.__graphSession,c=s.pointer.el.querySelector('canvas'),r=c.getBoundingClientRect(),style=getComputedStyle(c);const l=parseFloat(style.borderLeftWidth)+parseFloat(style.paddingLeft),t=parseFloat(style.borderTopWidth)+parseFloat(style.paddingTop),h=l+parseFloat(style.borderRightWidth)+parseFloat(style.paddingRight),v=t+parseFloat(style.borderBottomWidth)+parseFloat(style.paddingBottom),bw=parseFloat(style.width)+(style.boxSizing==='border-box'?0:h),bh=parseFloat(style.height)+(style.boxSizing==='border-box'?0:v),camera=s.pointer.handle.snapshot().camera;return [((event.clientX-r.left)*bw/r.width-l)*camera[4]/(bw-h),((event.clientY-r.top)*bh/r.height-t)*camera[5]/(bh-v)];},raw.event);
      raw.coordinates.forEach((v,i)=>assert.ok(Math.abs(v-delivered[i])<1e-8,`${v} != delivered ${delivered[i]}`));
      }else{
        assert.equal(raw.event.zoom,1);
        assert.deepEqual(raw.coordinates,raw.event.nativeCoordinates,'raw f64 must equal the synchronous native offset oracle');
      }
      return {point,raw,snapshot:await pointerSnapshot()};
    };
    await run("primary-mouse-exact-node-replace-shiftAdd-CtrlMetaToggle-and-rawf64", async () => {
      await page.evaluate(() => window.__graphSession.pointerFixture());
      const results=[];
      for(const [kind,index,mods,count] of [["node",1,[],1],["node",2,["Shift"],2],["node",1,["Control"],1],["node",1,["Meta"],2],["node",1,["Shift","Control"],1],["node",1,["Shift","Meta"],2]]) {
        const r=await click(kind,index,mods); assert.equal(r.snapshot.outcome.selected,count); results.push(r);
      }
      const p=await page.evaluate(()=>{const s=window.__graphSession,p=s.pointer;return {trusted:p.trusted,events:p.events,commands:s.commands.filter(c=>c.instanceId===p.id).map(c=>c.type),legacyCalls:s.legacyCalls};});
      assert.ok(p.trusted.every(e=>e.trusted&&e.button===0)); assert.equal(p.events.length,6); assert.deepEqual(p.legacyCalls,[]);
      assert.deepEqual(results[0].snapshot.selection.refs,[{kind:0,uuid:'02000000-0000-0000-0000-000000000000'}]);
      assert.deepEqual(Array.from(results[0].snapshot.selection.rows),[9007199254740997n]);
      return {ok:true,delivery:"Playwright mouse.click",results,...p};
    });
    await run("Rust-exact-persisted-parallel-selfloop-derived-head-and-compound-frame", async () => {
      const results=[];
      for(const [kind,index,expected] of [["piece",0,11],["piece",1,12],["piece",2,13],["head",4,null],["frame",0,1],["gap",0,2]]) {
        await page.evaluate(()=>{const p=window.__graphSession.pointer;p.el.style.transformOrigin='0 0';p.el.style.transform='scale(4)';});
        const r=await click(kind,index); const refs=r.snapshot.selection.refs;
        console.log('pointer oracle',kind,index,JSON.stringify({point:r.point,raw:r.raw,refs},(_,v)=>typeof v==='bigint'?String(v):v));
        assert.equal(refs.length,1);
        if(expected===null) {
          assert.deepEqual(refs[0],{kind:2,resultId:'exact:雪\t',layer:0,path:9007199254740995n,order:9007199254740993n});
          assert.deepEqual(Array.from(r.snapshot.selection.rows),[9007199254740999n]);
        } else {
          const node=kind==='frame'||kind==='gap', hex=node?`${expected.toString(16).padStart(2,'0')}000000000000000000000000000000`:expected.toString(16).padStart(2,'0').repeat(16);
          assert.deepEqual(refs[0],{kind:node?0:1,uuid:hex.replace(/(.{8})(.{4})(.{4})(.{4})(.{12})/,'$1-$2-$3-$4-$5')});
        }
        results.push(r);
      }
      await page.evaluate(()=>window.__graphSession.pointer.el.removeAttribute('style'));
      const interior=await click('interior'); assert.equal(interior.snapshot.outcome.selected,0);
      return {ok:true,results,interior};
    });
    await run("blank-Replace-empty-AddToggle-noops-samerevision-focus-and-geometry", async () => {
      const before=await page.evaluate(()=>{const s=window.__graphSession;return {snapshot:s.pointerSnapshot(),bytes:[...s.publication()]};});
      await click('node',1);
      const add=await click('blank',0,['Shift']), toggle=await click('blank',0,['Control']), replace=await click('blank');
      assert.equal(add.snapshot.outcome.selected,1);assert.equal(toggle.snapshot.outcome.selected,1);assert.equal(add.snapshot.outcome.stateChanged,false);assert.equal(toggle.snapshot.outcome.stateChanged,false);assert.equal(replace.snapshot.outcome.selected,0);
      const unchanged=await page.evaluate(before=>{const s=window.__graphSession,after=s.publication();const names=['paint.node.center.f64','paint.piece.geometry.f64','paint.frame.geometry.f64','render.node_members.u64','render.edge_members.u64'];return names.every(name=>s.json([...s.section(new Uint8Array(before),name)])===s.json([...s.section(after,name)]));},before.bytes);
      assert.equal(unchanged,true);assert.equal(replace.snapshot.revision,before.snapshot.revision);assert.deepEqual(replace.snapshot.focus,before.snapshot.focus);
      if(process.env.XYG_GRAPH_POINTER_CAPTURE) {
        const capture=await page.evaluate(()=>{const s=window.__graphSession;return s.commands.filter(c=>c.instanceId===36n).map(c=>({operation:c.operation,nativeEvent:c.nativeEvent,request:[...c.bytes],reply:[...s.replies.find(r=>r.requestId===c.requestId&&r.sequence===c.sequence&&r.lifetime===c.lifetime).bytes]}));});
        await writeFile(process.env.XYG_GRAPH_POINTER_CAPTURE,JSON.stringify(capture.map(c=>({operation:c.operation,nativeEvent:c.nativeEvent,request:Buffer.from(c.request).toString('base64'),reply:Buffer.from(c.reply).toString('base64')})),null,2)+'\n');
      }
      return {ok:true,add,toggle,replace,unchanged};
    });
    await run("signedcamera-DPR2-CSSscale-offset-border-padding-borderbox-scroll", async () => {
      await page.evaluate(async()=>{const s=window.__graphSession,p=s.pointer;await p.handle.refreshRender([-1,100,600,0,640,320,2]);p.el.style.cssText='margin-left:43px; margin-top:31px; width:1000px; transform-origin:0 0; transform:scale(0.8,0.75)';const c=p.el.querySelector('canvas');c.style.cssText+=';border:7px solid black;padding:11px 13px;box-sizing:border-box';});
      const r=await click('node',1);
      if(process.env.XYG_GRAPH_POINTER_SCREENSHOT) await page.locator('[data-pointer-fixture] canvas').screenshot({path:process.env.XYG_GRAPH_POINTER_SCREENSHOT});
      assert.deepEqual(r.snapshot.selection.refs,[{kind:0,uuid:'02000000-0000-0000-0000-000000000000'}]);assert.equal(r.snapshot.camera[6],2);
      const initial=await page.evaluate(()=>{const s=window.__graphSession;return s.commands.length;});
      // A real click in padding must not become a graph command.
      const pad=await page.locator('[data-pointer-fixture] canvas').boundingBox();await page.mouse.click(pad.x+8,pad.y+8);
      assert.equal(await page.evaluate(()=>window.__graphSession.commands.length),initial);
      await page.evaluate(async()=>{const s=window.__graphSession,p=s.pointer;p.el.removeAttribute('style');p.el.querySelector('canvas').removeAttribute('style');await p.handle.refreshRender(p.camera);});
      return {ok:true,result:r,paddingCommands:0};
    });
    await run("unsupported-transform-alt-secondary-and-busy-clicks-pass-without-replay", async () => {
      const initial=await page.evaluate(()=>window.__graphSession.commands.length), results=[];
      for(const transform of ['rotate(5deg)','skewX(8deg)','perspective(500px) rotateY(5deg)','scale(-1,1)']) {
        await page.evaluate(t=>window.__graphSession.pointer.el.style.transform=t,transform);
        const box=await page.locator('[data-pointer-fixture] canvas').boundingBox();await page.mouse.click(box.x+box.width/2,box.y+box.height/2);results.push(transform);
      }
      await page.evaluate(()=>window.__graphSession.pointer.el.style.transform='none');
      const point=await page.evaluate(()=>{const s=window.__graphSession;return s.pointerClient(s.pointerPoint('node',1));});
      await page.keyboard.down('Alt');await page.mouse.click(...point);await page.keyboard.up('Alt');await page.mouse.click(...point,{button:'right'});await page.mouse.click(...point,{button:'middle'});
      assert.equal(await page.evaluate(()=>window.__graphSession.commands.length),initial);
      await page.evaluate(()=>{const s=window.__graphSession;s.hold=true;s.pointer.pending=s.pointer.handle.refreshRender();});await page.waitForFunction(()=>window.__graphSession.held.length>0);
      const busy=await page.evaluate(()=>window.__graphSession.commands.length);await page.mouse.click(...point);
      assert.equal(await page.evaluate(()=>window.__graphSession.commands.length),busy);
      await page.evaluate(async()=>{const s=window.__graphSession;s.release();await s.pointer.pending;});await pointerIdle();assert.equal(await page.evaluate(()=>window.__graphSession.commands.length),busy);
      return {ok:true,results,busyDiscarded:true};
    });
    await run("held-primarySelectAt-busy-Escape-discard-focus-stable-and-samerevision-repaint", async () => {
      await click('blank');
      await page.evaluate(()=>window.__graphSession.pointer.el.querySelector('[role="application"]').focus());
      await page.keyboard.press('ArrowRight');await pointerIdle();
      const before=await pointerSnapshot();assert.equal(before.focus.length,1);
      const point=await page.evaluate(()=>{const s=window.__graphSession,p=s.pointer;p.beforePixels=s.json(s.pixel(p.el));p.beforeGeometry=s.geometryStamp(s.publication());p.beforeEvents=p.events.length;s.hold=true;return s.pointerClient(s.pointerPoint('node',1));});
      await page.mouse.click(...point);await page.waitForFunction(()=>window.__graphSession.held.length>0);
      const count=await page.evaluate(()=>window.__graphSession.commands.length);
      await page.keyboard.press('Escape');await page.mouse.click(...point);
      assert.equal(await page.evaluate(()=>window.__graphSession.commands.length),count);assert.deepEqual(await pointerSnapshot(),before);
      assert.equal(await page.evaluate(()=>{const s=window.__graphSession;return s.json(s.pixel(s.pointer.el))===s.pointer.beforePixels;}),true);
      await page.evaluate(()=>window.__graphSession.release());await pointerIdle();const after=await pointerSnapshot();
      assert.equal(after.revision,before.revision);assert.deepEqual(after.focus,before.focus);
      const proof=await page.evaluate(()=>{const s=window.__graphSession,p=s.pointer;return {geometryUnchanged:p.beforeGeometry===s.geometryStamp(s.publication()),repainted:p.beforePixels!==s.json(s.pixel(p.el)),events:p.events.length-p.beforeEvents};});
      assert.deepEqual(proof,{geometryUnchanged:true,repainted:true,events:1});return {ok:true,before,after,...proof,busyClearCommands:0,busyClickReplay:0};
    });
    await run("pointer-Rust-refusal-stale-malformed-atomic-and-explicit-refresh", async () => {
      const results=[];
      for(const inject of ['wrong-instance','budget-reply','stale','malformed-gpu','malformed-clear']) {
        const before=await pointerSnapshot(); await page.evaluate(i=>window.__graphSession.inject=i,inject);
        const r=await click('node',2); assert.deepEqual(r.snapshot,before);
        if(['stale','malformed-gpu','malformed-clear'].includes(inject)) {
          const count=await page.evaluate(()=>window.__graphSession.commands.length), point=await page.evaluate(()=>{const s=window.__graphSession;return s.pointerClient(s.pointerPoint('node',1));});await page.mouse.click(...point);assert.equal(await page.evaluate(()=>window.__graphSession.commands.length),count);
        }
        await page.evaluate(()=>window.__graphSession.pointer.handle.refreshRender());results.push({inject,retained:true});
      }
      return {ok:true,results,budget:"test-only definitive error reply seam; Rust cap covered separately"};
    });
    await run("blank-Replace-preserves-Rust-highlight-planes-and-pointer-observer-errors", async () => {
      await click('blank');
      await page.evaluate(()=>{window.__graphSession.inject='seed-highlight';});
      // This test-only transport edit seeds a real Rust External highlight; it
      // is not part of the bounded controller vocabulary or the mouse capture.
      const point=await page.evaluate(()=>{const s=window.__graphSession;return s.pointerClient(s.pointerPoint('node',1));});await page.mouse.click(...point);await pointerIdle();
      const highlighted=await page.evaluate(()=>{const s=window.__graphSession;return [...s.section(s.publication(),'node.flags.u32')];});
      await click('node',2);const blank=await click('blank');assert.equal(blank.snapshot.clearAction.applicable,true);assert.equal(blank.snapshot.outcome.selected,0);
      const after=await page.evaluate(()=>{const s=window.__graphSession;return [...s.section(s.publication(),'node.flags.u32')];});assert.deepEqual(after,highlighted);
      await page.evaluate(()=>{const s=window.__graphSession;s.pointer.observed=false;s.pointer.onError=e=>{if(e.message.includes('pointer observer failure')){s.pointer.observed=true;e.preventDefault();}};s.pointer.listener=()=>{throw Error('pointer observer failure');};window.addEventListener('error',s.pointer.onError);s.pointer.el.addEventListener('xy:graph-select',s.pointer.listener);});
      await click('node',1);const observed=await page.evaluate(()=>{const s=window.__graphSession,p=s.pointer;p.el.removeEventListener('xy:graph-select',p.listener);window.removeEventListener('error',p.onError);return p.observed;});assert.equal(observed,true);
      await page.evaluate(async()=>{const p=window.__graphSession.pointer;await p.handle.dispose();await p.worker.dispose();p.el.remove();});
      return {ok:true,highlighted,after,observed};
    });
    await run("default16MiB-10001-source-fixture-Rust-budget-refusal", async () => {
      const code=await page.evaluate(async()=>{try {await window.__graphSession.pointerFixture('pressure',40n);return 'unexpected-success';}catch(e){return e.code;}});
      assert.equal(code,'GF_INTERACTION_BUDGET');
      return {ok:true,code,sources:10001,arena:16777216,limitation:'Refused at initialization; no claim of a real 10001-member click at this arena. Typed selection-cap reply is tested at the pre-execution seam on51 sources.'};
    });
    await run("aggregate-exact-Rust-membership-and-typed-cap-refusal-default-arena", async () => {
      const results=[];
      for(const [kind,id] of [['aggregate',37n],['cap',38n]]) {
        console.log('aggregate fixture',kind);
        await page.evaluate(([kind,id])=>window.__graphSession.pointerFixture(kind,BigInt(id)),[kind,String(id)]);
        const expected=await page.evaluate(()=>{const s=window.__graphSession,p=s.pointer,bytes=s.publication(),parts=s.section(bytes,'render.node_member_offsets.u64'),offsets=new BigUint64Array(parts.slice().buffer),members=new BigUint64Array(s.section(bytes,'render.node_members.u64').slice().buffer);const ids=[...members.slice(Number(offsets[0]),Number(offsets[1]))].sort((a,b)=>Number(a-b));return ids.map(i=>({kind:0,uuid:[...p.nodes.slice(Number(i)*16,Number(i)*16+16)].map(b=>b.toString(16).padStart(2,'0')).join('').replace(/(.{8})(.{4})(.{4})(.{4})(.{12})/,'$1-$2-$3-$4-$5')}));});
        const before=await pointerSnapshot();
        if(kind==='cap') await page.evaluate(()=>window.__graphSession.inject='cap-reply');
        const result=await click('node',0);
        if(kind==='cap') {assert.deepEqual(result.snapshot,before);} else {assert.ok(result.snapshot.outcome.selected>1);assert.deepEqual(result.snapshot.selection.refs,expected);}
        const errors=await page.evaluate(()=>window.__graphSession.pointer.errors);
        if(kind==='cap') assert.equal(errors.at(-1)?.code,'GF_INTERACTION_SELECTION_TOO_LARGE');
        results.push({kind,result,errors,expectedMemberCount:expected.length,...(kind==='aggregate'?{expected}: {})});
        await page.evaluate(async()=>{const p=window.__graphSession.pointer;await p.handle.dispose();await p.worker.dispose();p.el.remove();});
      }
      return {ok:true,results};
    });
    await run("pointer-dispose-during-reply-removes-listener-and-twoWorkers-isolate", async () => {
      await page.evaluate(()=>window.__graphSession.pointerFixture('routes',39n));
      const main=await page.evaluate(()=>window.__graphSession.snapshot());
      await page.locator('[data-pointer-fixture] canvas').scrollIntoViewIfNeeded();const point=await page.evaluate(()=>{const s=window.__graphSession;return s.pointerClient(s.pointerPoint('node',1));});
      await page.evaluate(()=>window.__graphSession.hold=true);await page.mouse.click(...point);await page.waitForFunction(()=>window.__graphSession.held.length>0);
      await page.evaluate(()=>{const s=window.__graphSession,p=s.pointer;p.oldCanvas=p.el.querySelector('canvas');p.disposal=p.handle.dispose();p.el.append(p.oldCanvas);});
      const count=await page.evaluate(()=>window.__graphSession.commands.length);const box=await page.locator('[data-pointer-fixture] canvas').boundingBox();await page.mouse.click(box.x+20,box.y+20);assert.equal(await page.evaluate(()=>window.__graphSession.commands.length),count);
      const result=await page.evaluate(async()=>{const s=window.__graphSession,p=s.pointer;s.release();await p.disposal;await p.worker.dispose();p.el.remove();return {snapshot:p.handle.snapshot(),events:p.events.length};});assert.equal(result.snapshot,null);assert.equal(result.events,0);assert.deepEqual(await page.evaluate(()=>window.__graphSession.snapshot()),main);
      return {ok:true,result};
    });
    await run("terminal-pointer-input-passes-without-command-and-mainWorker-survives", async () => {
      await page.evaluate(()=>window.__graphSession.pointerFixture('routes',41n));
      await page.locator('[data-pointer-fixture] canvas').scrollIntoViewIfNeeded();
      const code=await page.evaluate(async()=>{const s=window.__graphSession;s.inject='wrong-lifetime';try{await s.pointer.handle.refreshRender();return 'unexpected-success';}catch(e){return e.code;}});assert.equal(code,'XYG_WASM_MESSAGE_ERROR');
      const before=await page.evaluate(()=>window.__graphSession.commands.length),point=await page.evaluate(()=>{const s=window.__graphSession;return s.pointerClient(s.pointerPoint('node',1));});await page.mouse.click(...point);assert.equal(await page.evaluate(()=>window.__graphSession.commands.length),before);
      await page.evaluate(async()=>{const s=window.__graphSession,p=s.pointer;await p.handle.dispose();await p.worker.dispose();p.el.remove();await s.handle.refreshRender();});return {ok:true,code,terminalCommands:0};
    });
    for (const target of ['canvas','ancestor']) {
      const baseline=!!process.env.XYG_GRAPH_MOTION_BASELINE;
      await run(`${baseline?'before-mis-pick':'reject'}-active-motion-path-on-${target}-trusted-canvas-click`, async () => {
        await page.evaluate(id=>window.__graphSession.pointerFixture('routes',BigInt(id)),target==='canvas'?'50':'51');
        await click('node',2); // Keep an accepted nonempty selection to detect a wrong blank pick.
        await page.locator('[data-pointer-fixture] canvas').scrollIntoViewIfNeeded();
        const point=await page.evaluate(target=>window.__graphSession.motionPoint(target),target);
        assert.equal(point.predicate.transform,'none');assert.equal(point.predicate.rotate,'none');assert.notEqual(point.predicate.offsetPath,'none');assert.equal(point.predicate.offsetRotate,'30deg');
        assert.equal(point.hit,'CANVAS','the actual visibly transformed graph point must hit canvas');
        const before=await page.evaluate(async()=>{const s=window.__graphSession,p=s.pointer;return {commands:s.commands.length,products:s.products.length,events:p.events.length,snapshot:s.pointerSnapshot(),pixels:await s.canvasDigest(),geometry:s.geometryStamp(s.publication()),hash:location.hash};});
        await page.mouse.click(...point.client);await pointerIdle();
        const after=await page.evaluate(async()=>{const s=window.__graphSession,p=s.pointer,c=s.commands.at(-1);return {commands:s.commands.length,products:s.products.slice(-1),events:p.events.length,snapshot:s.pointerSnapshot(),pixels:await s.canvasDigest(),geometry:s.geometryStamp(s.publication()),hash:location.hash,delivery:p.motionDelivery,lastOperation:c.operation,lastCoordinates:c.operation===1?s.values(c.bytes,'coordinates.f64'):null};});
        const result={ok:true,target,point,delivery:after.delivery,before:{commands:before.commands,events:before.events,snapshot:before.snapshot,pixels:before.pixels,hash:before.hash},after:{commands:after.commands,events:after.events,snapshot:after.snapshot,pixels:after.pixels,lastOperation:after.lastOperation,lastCoordinates:after.lastCoordinates,hash:after.hash},geometryUnchanged:before.geometry===after.geometry};
        console.log('motion-path raw proof',JSON.stringify(result,(_,v)=>typeof v==='bigint'?String(v):v));
        assert.equal(after.delivery.trusted,true);assert.equal(after.delivery.target,'CANVAS');assert.equal(after.delivery.canvas,true);
        if(baseline) {
          assert.equal(after.commands,before.commands+1);assert.equal(after.lastOperation,1);assert.equal(after.delivery.defaultPrevented,true);
          assert.equal(after.snapshot.outcome.selected,0);assert.notDeepEqual(after.snapshot,before.snapshot);assert.equal(after.hash,before.hash);
        } else {
          assert.equal(after.commands,before.commands);assert.equal(after.events,before.events);assert.equal(after.delivery.defaultPrevented,false);
          assert.deepEqual(after.snapshot,before.snapshot);assert.equal(after.pixels,before.pixels);assert.equal(after.geometry,before.geometry);assert.equal(after.hash,`#motion-path-${target}`);
          assert.equal(await page.evaluate(start=>window.__graphSession.products.length===start,before.products),true);
        }
        await page.evaluate(async()=>{const p=window.__graphSession.pointer;await p.handle.dispose();await p.worker.dispose();p.el.remove();});
        return result;
      });
    }

    for (const [kind,nested] of [['rotate',false],['motion',false],['plain',false],['scale',false],['rotate',true],['scale',true]]) {
      const unsupported=kind==='rotate'||kind==='motion',baseline=!!process.env.XYG_GRAPH_SLOT_BASELINE;
      await run(`${unsupported&&baseline?'before-mis-pick':unsupported?'reject':'accept'}-${nested?'nested-':''}slotted-${kind}-trusted-canvas`, async () => {
        await page.evaluate(id=>window.__graphSession.pointerFixture('routes',BigInt(id)),String(60+['rotate','motion','plain','scale'].indexOf(kind)+(nested?10:0)));
        await click('node',2);
        const point=await page.evaluate(([kind,nested])=>window.__graphSession.slotPoint(kind,nested),[kind,nested]);
        assert.equal(point.hit,'CANVAS');assert.equal(point.composedWalk.filter(e=>e.tag==='SLOT').length,nested?2:1);
        assert.ok(point.legacyWalk.every(e=>e.transform==='none'&&e.rotate==='none'&&e.offsetPath==='none'));
        const before=await page.evaluate(async()=>{const s=window.__graphSession,p=s.pointer;return {commands:s.commands.length,products:s.products.length,events:p.events.length,snapshot:s.pointerSnapshot(),pixels:await s.canvasDigest(),geometry:s.geometryStamp(s.publication()),hash:location.hash};});
        let positive=null;
        if(unsupported){await page.mouse.click(...point.client);await pointerIdle();}else{positive=await click('node',1);}
        const after=await page.evaluate(async()=>{const s=window.__graphSession,p=s.pointer,c=s.commands.at(-1);return {commands:s.commands.length,products:s.products.length,events:p.events.length,snapshot:s.pointerSnapshot(),pixels:await s.canvasDigest(),geometry:s.geometryStamp(s.publication()),hash:location.hash,delivery:p.slotDelivery,lastOperation:c.operation,lastCoordinates:c.operation===1?s.values(c.bytes,'coordinates.f64'):null};});
        const result={ok:true,point,delivery:after.delivery,before:{commands:before.commands,snapshot:before.snapshot,pixels:before.pixels,hash:before.hash},after:{commands:after.commands,snapshot:after.snapshot,pixels:after.pixels,hash:after.hash,lastOperation:after.lastOperation,lastCoordinates:after.lastCoordinates},geometryUnchanged:before.geometry===after.geometry,positive};
        console.log('slot raw proof',JSON.stringify(result,(_,v)=>typeof v==='bigint'?String(v):v));
        assert.equal(after.delivery.trusted,true);assert.equal(after.delivery.target,'CANVAS');assert.equal(after.delivery.canvas,true);
        if(unsupported&&!baseline){
          assert.equal(after.commands,before.commands);assert.equal(after.products,before.products);assert.equal(after.events,before.events);assert.equal(after.delivery.defaultPrevented,false);
          assert.deepEqual(after.snapshot,before.snapshot);assert.equal(after.pixels,before.pixels);assert.equal(after.geometry,before.geometry);assert.equal(after.hash,`#slot-${nested?'nested-':''}${kind}`);
        }else{
          assert.equal(after.commands,before.commands+1);assert.equal(after.lastOperation,1);assert.equal(after.delivery.defaultPrevented,true);assert.equal(after.hash,before.hash);
          if(unsupported){assert.notDeepEqual(after.snapshot,before.snapshot);assert.equal(after.snapshot.outcome.selected,0);}else{assert.deepEqual(after.snapshot.selection.refs,[{kind:0,uuid:'02000000-0000-0000-0000-000000000000'}]);assert.equal(after.snapshot.outcome.selected,1);assert.equal(after.geometry,before.geometry);assert.deepEqual(after.snapshot.focus,before.snapshot.focus);}
        }
        await page.evaluate(async()=>{const p=window.__graphSession.pointer;await p.handle.dispose();await p.worker.dispose();p.slotHost.remove();});return result;
      });
    }

    const nativeBaseline=process.env.XYG_GRAPH_NATIVE_BASELINE;
    const cdp=await page.context().newCDPSession(page);
    const closedCases=nativeBaseline?[[1,'rotate','div',true,false]]:
      [1,2].flatMap(dpr=>[
        ...['div','body'].flatMap(tag=>[true,false].flatMap(named=>['rotate','motion'].map(kind=>[dpr,kind,tag,named,false]))),
        [dpr,'zoom14','div',true,false],[dpr,'zoom125','body',false,false],
        [dpr,'net2','div',false,true],[dpr,'net14','body',true,true],
        [dpr,'rotate','div',true,true],[dpr,'motion','body',false,true]
      ]);
    for(const [dpr,kind,tag,named,nested] of closedCases){
      await run(`native-closed-${tag}-${named?'named':'default'}-${kind}-${nested?'nested-':''}DPR${dpr}`,async()=>{
        await cdp.send('Emulation.setDeviceMetricsOverride',{width:2800,height:1500,deviceScaleFactor:dpr,mobile:false});
        await page.evaluate(()=>window.__graphSession.pointerFixture('routes',90n));await click('node',2);
        const point=await page.evaluate(options=>window.__graphSession.closedPoint(options),{kind,tag,named,nested});
        assert.equal(point.hit,'CANVAS');assert.equal(point.dpr,dpr);assert.equal(point.canvasStyleZoom,'1');
        assert.ok(point.chain.every(e=>e.transform==='none'&&e.rotate==='none'&&e.offsetPath==='none'&&e.slot===null));
        const before=await page.evaluate(async()=>{const s=window.__graphSession,p=s.pointer;return {commands:s.commands.length,products:s.products.length,events:p.events.length,snapshot:s.pointerSnapshot(),pixels:await s.canvasDigest(),geometry:s.geometryStamp(s.publication()),hash:location.hash};});
        await page.mouse.click(...point.client);await pointerIdle();
        const after=await page.evaluate(async()=>{const s=window.__graphSession,p=s.pointer,c=s.commands.at(-1);return {commands:s.commands.length,products:s.products.length,events:p.events.length,snapshot:s.pointerSnapshot(),pixels:await s.canvasDigest(),geometry:s.geometryStamp(s.publication()),hash:location.hash,delivery:p.closedDelivery,event:p.trusted.at(-1),coordinates:c.operation===1?s.values(c.bytes,'coordinates.f64'):null};});
        const result={ok:true,point,before,after};console.log('closed-native raw proof',JSON.stringify(result,(_,v)=>typeof v==='bigint'?String(v):v));
        assert.equal(after.delivery.trusted,true);assert.equal(after.delivery.canvas,true);assert.equal(after.delivery.target,'CANVAS');
        const refuse=kind.startsWith('zoom');
        if(nativeBaseline==='1'){
          assert.equal(after.commands,before.commands+1);assert.equal(after.delivery.defaultPrevented,true);assert.equal(after.snapshot.outcome.selected,0);
          assert.notDeepEqual(after.coordinates,after.event.nativeCoordinates);
        }else if(refuse){
          assert.notEqual(point.zoom,1);assert.equal(after.commands,before.commands);assert.equal(after.products,before.products);assert.equal(after.events,before.events);
          assert.deepEqual(after.snapshot,before.snapshot);assert.equal(after.pixels,before.pixels);assert.equal(after.delivery.defaultPrevented,false);assert.equal(after.hash,point.fragment);assert.notEqual(before.hash,point.fragment);
        }else{
          assert.equal(point.zoom,1);assert.equal(after.commands,before.commands+1);assert.equal(after.products,before.products+1);assert.equal(after.events,before.events+1);
          assert.equal(after.delivery.defaultPrevented,true);assert.equal(after.hash,before.hash);
          assert.deepEqual(after.coordinates,after.event.nativeCoordinates);assert.deepEqual(after.snapshot.selection.refs,[{kind:0,uuid:'02000000-0000-0000-0000-000000000000'}]);
        }
        assert.equal(after.geometry,before.geometry);assert.deepEqual(after.snapshot.focus,before.snapshot.focus);assert.equal(after.snapshot.revision,before.snapshot.revision);
        await page.evaluate(async()=>{const p=window.__graphSession.pointer;await p.handle.dispose();await p.worker.dispose();p.closedHost.remove();});return result;
      });
    }
    await cdp.send('Emulation.clearDeviceMetricsOverride');await cdp.detach();
    if(!nativeBaseline) for(const capability of ['missing','nan','infinite','nonunit']){
      await run(`effective-zoom-${capability}-test-only-capability-seam-refuses-trusted-click`,async()=>{
        await page.evaluate(()=>window.__graphSession.pointerFixture('routes',91n));await click('node',2);
        const point=await page.evaluate(capability=>{const s=window.__graphSession,c=s.pointer.el.querySelector('canvas'),surface=c.parentElement,link=document.createElement('a');link.href=`#capability-refusal-${capability}`;surface.before(link);link.append(surface);
          Object.defineProperty(c,'currentCSSZoom',{configurable:true,value:({missing:undefined,nan:NaN,infinite:Infinity,nonunit:1+Number.EPSILON})[capability]});
          s.pointer.capabilityDelivery=null;c.addEventListener('click',e=>s.pointer.capabilityDelivery={trusted:e.isTrusted,canvas:e.target===c,defaultPrevented:e.defaultPrevented});return s.pointerClient(s.pointerPoint('node',1));},capability);
        const before=await page.evaluate(async()=>{const s=window.__graphSession;return {commands:s.commands.length,products:s.products.length,snapshot:s.pointerSnapshot(),pixels:await s.canvasDigest(),events:s.pointer.events.length,geometry:s.geometryStamp(s.publication())};});
        await page.mouse.click(...point);await pointerIdle();
        const after=await page.evaluate(async()=>{const s=window.__graphSession;return {commands:s.commands.length,products:s.products.length,snapshot:s.pointerSnapshot(),pixels:await s.canvasDigest(),events:s.pointer.events.length,geometry:s.geometryStamp(s.publication())};});
        const delivery=await page.evaluate(()=>window.__graphSession.pointer.capabilityDelivery);
        assert.deepEqual(after,before);assert.deepEqual(delivery,{trusted:true,canvas:true,defaultPrevented:false});assert.equal(await page.evaluate(()=>location.hash),`#capability-refusal-${capability}`);
        await page.evaluate(async()=>{const p=window.__graphSession.pointer;await p.handle.dispose();await p.worker.dispose();p.el.remove();});return {ok:true,capability,seam:'test-only own-property effective-zoom override',before,after,delivery};
      });
    }

  }
  await run("old-same-ABI-module-missing-clear-fact-fails-closed", () => check(async () => {
    const s = window.__graphSession, worker = s.makeWorker("/old-same-abi.wasm"); await worker.ready; const el = s.container();
    const handle = s.attach({ el, worker, instanceId: 80n, document: s.document, load: s.load, camera: s.camera });
    let code; try { await handle.ready; } catch(e) { code = e.code; } await handle.dispose();
    const composed = await s.compose(worker, s.input).result; await worker.dispose();
    return { ok: code === "GF_INTERACTION_INVALID" && handle.snapshot() === null && el.children.length === 0 && composed.nodeUuid.length > 0, code };
  }));
  await run("ambiguous-lost-reply-watchdog-is-terminal-no-replay-or-lateevents", async () => {
    await page.clock.install();
    await page.evaluate(async () => {
      const s = window.__graphSession, worker = s.makeWorker(); await worker.ready; const el = s.container();
      const handle = s.attach({ el, worker, instanceId: 62n, document: s.document, load: s.load, camera: s.camera }); await handle.ready;
      s.timeout = { worker, el, handle, events: 0 }; el.addEventListener("xy:graph-render", () => s.timeout.events++);
      s.hold = true; s.timeout.result = handle.refreshRender().then(() => "unexpected-success", error => error.code);
    });
    await page.waitForFunction(() => window.__graphSession.held.length > 0);
    await page.clock.fastForward(60_001);
    const result = await check(async () => {
      const s = window.__graphSession, t = s.timeout, code = await t.result;
      const ignored = new KeyboardEvent("keydown", { key: "Enter", bubbles: true, cancelable: true }); t.el.querySelector('[role="application"]').dispatchEvent(ignored);
      await t.handle.dispose(); const count = t.events; s.release(); await t.worker.dispose();
      return { ok: code === "XYG_WASM_GRAPH_REPLY_LOST" && !ignored.defaultPrevented && !t.el.children.length && count === t.events && count === 0, code, events: t.events };
    });
    await page.clock.resume(); return result;
  });
  await run("close-drains-before-ownedWorker-disposal-and-final-no-lateevents", () => check(async () => {
    const s = window.__graphSession, count = s.events.length; await s.handle.dispose(); await s.handle.dispose(); await s.worker.dispose(); await new Promise(r => setTimeout(r, 20));
    return { ok: !s.el.children.length && count === s.events.length && s.commands.some(c => c.type === "graph.session.close"), commands: s.commands.map(({ bytes, ...c }) => c), legacyCalls: s.legacyCalls };
  }));
  assert.deepEqual(violations, []); assert.deepEqual(errors, []); assert.deepEqual(requests.filter(p => p !== "/" && !allowed(p)), []);
  evidence.status = "passed"; evidence.requests = requests; evidence.cspViolations = violations; evidence.pageErrors = errors;
  if (process.env.XYG_GRAPH_SESSION_REPORT) await writeFile(process.env.XYG_GRAPH_SESSION_REPORT, JSON.stringify(evidence, (_, v) => typeof v === "bigint" ? v.toString() : v, 2) + "\n");
  console.log(`graph session strict-CSP shipping journey: ${evidence.cases.length} cases passed, zero skips`);
  }
} finally { await browser.close(); await new Promise(r => server.close(r)); }
