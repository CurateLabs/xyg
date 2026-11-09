// Actual Node/native selected hierarchy lanes and packaged strict-CSP painter.
import {diagnoseIdlePaint} from './geo_idle_paint_diagnostic.mjs';
import assert from 'node:assert/strict';
import {createServer} from 'node:http';
import {readFile} from 'node:fs/promises';
import {chromium} from 'playwright';
import {fiveTemporalFixture} from '../../packages/xy-node/test/geo-five-temporal-fixture.mjs';
import {attachGeoWebview} from '../../packages/xy-node/src/geo-webview.js';
import {temporalControllerCreate,temporalControllerSetCursor,temporalControllerSetRange,temporalControllerDestroy,temporalControllerPollEvent,temporalCoordinateDeliver} from '../../packages/xy-node/src/index.js';
function pack({message,buffers=[]}){const meta=Buffer.from(JSON.stringify(message)),parts=[Buffer.alloc(8),meta];parts[0].writeUInt32LE(meta.length);parts[0].writeUInt32LE(buffers.length,4);for(const raw of buffers){const b=Buffer.from(new Uint8Array(raw)),n=Buffer.alloc(4);n.writeUInt32LE(b.length);parts.push(n,b);}return Buffer.concat(parts);}
function unpack(raw){const ml=raw.readUInt32LE(),count=raw.readUInt32LE(4),message=JSON.parse(raw.subarray(8,8+ml));let at=8+ml;const buffers=[];for(let i=0;i<count;i++){const n=raw.readUInt32LE(at);at+=4;buffers.push(Uint8Array.from(raw.subarray(at,at+n)).buffer);at+=n;}assert.equal(at,raw.length);return {message,buffers};}

const artifactDirectory=process.env.XYG_GEO_ARTIFACT_DIR??'target/task-tmp/five-temporal-successor';
const fixture=await fiveTemporalFixture({aggregate:process.env.XYG_GEO_AGGREGATE==='1'}),channels=[],bindings=[],completions=[];
const h=temporalControllerCreate({instanceId:991n,domainStart:-(1n<<63n),domainEnd:(1n<<63n)-1n,cursor:3n,window:0n,step:1n});
let hold=false,held,unhold,peak=0,heldView,failAbort=0;
for(const [i,f] of fixture.views.entries()){
 const c={queue:[],poll:undefined,operations:new Map()};channels.push(c);
 const panel={webview:{onDidReceiveMessage(cb){c.receive=cb;return {dispose(){}};},async postMessage(envelope){
  if(hold&&envelope.message.type==='geo_host'&&envelope.buffers?.[0]&&new DataView(envelope.buffers[0]).getUint32(8,true)===6){hold=false;heldView=i;held(i);await new Promise(r=>unhold=r);}
  if(c.operations.get(envelope.message.request)===9&&failAbort>0){failAbort--;envelope={message:{...envelope.message,error:'lost five-view abort ACK'},buffers:[]};}
  peak=Math.max(peak,fixture.views.filter(f=>!!f.adapter.liveCandidate.frame||!!f.adapter.liveCandidate.cleanupFrame).length);assert.ok(peak<=1);
  const b=pack(envelope);if(c.poll){const res=c.poll;c.poll=undefined;res.end(b);}else c.queue.push(b);return true;
 }},onDidDispose(cb){c.disposed=cb;return {dispose(){}};},dispose(){c.disposed();}};
 c.host=attachGeoWebview(panel,f.adapter);bindings.push(c.host.bindTemporal(h,process.env.XYG_GEO_RANGE==='1'?'range':'cursor'));
}
const server=createServer(async(req,res)=>{try{
 const url=new URL(req.url,'http://local'),id=Number(url.searchParams.get('id')),c=channels[id];
 if(url.pathname==='/'){res.setHeader('Content-Security-Policy',"default-src 'none'; script-src 'self'; connect-src 'self'; style-src 'unsafe-inline'; object-src 'none'; base-uri 'none'");res.end('<!doctype html><style>.chart{width:800px;height:600px}</style>'+channels.map((_,i)=>`<div class="chart" id="chart${i}" tabindex="0"></div>`).join('')+'<script type="module" src="/page.js"></script>');return;}
 if(url.pathname==='/index.js'){res.setHeader('Content-Type','text/javascript');res.end(await readFile(process.env.XYG_CLIENT_ESM??'packages/xy-client/dist/index.js'));return;}
 if(url.pathname==='/page.js'){res.setHeader('Content-Type','text/javascript');res.end(`import {XygGeoHostView} from '/index.js';

 window.views=[];
 for(let id=0;id<5;id++){
 let callback;const view=new XygGeoHostView(document.getElementById('chart'+id),{onMessage:c=>{callback=c;return()=>callback=undefined;},send:(message,buffers=[])=>{const meta=new TextEncoder().encode(JSON.stringify(message)),b=new ArrayBuffer(8+meta.length+buffers.reduce((n,b)=>n+4+b.byteLength,0)),v=new DataView(b);v.setUint32(0,meta.length,true);v.setUint32(4,buffers.length,true);new Uint8Array(b,8,meta.length).set(meta);let at=8+meta.length;for(const raw of buffers){v.setUint32(at,raw.byteLength,true);at+=4;new Uint8Array(b,at,raw.byteLength).set(new Uint8Array(raw));at+=raw.byteLength;}void fetch('/host?id='+id,{method:'POST',body:b});}});window.views.push(view);
 (async()=>{while(callback){const r=await fetch('/next?id='+id),b=await r.arrayBuffer(),v=new DataView(b),ml=v.getUint32(0,true),count=v.getUint32(4,true),message=JSON.parse(new TextDecoder().decode(new Uint8Array(b,8,ml))),buffers=[];let at=8+ml;for(let i=0;i<count;i++){const n=v.getUint32(at,true);at+=4;buffers.push(b.slice(at,at+n));at+=n;}callback?.(message,buffers);}})();}
 `);return;}
 if(url.pathname==='/next'){if(c.queue.length)res.end(c.queue.shift());else{c.poll=res;res.on('close',()=>{if(c.poll===res)c.poll=undefined;});}return;}
 if(url.pathname==='/host'){const parts=[];for await(const part of req)parts.push(part);const e=unpack(Buffer.concat(parts));if(e.message.type==='geo_host')c.operations.set(e.message.request,new DataView(e.buffers[0]).getUint32(8,true));if(e.message.type==='geo_host_temporal_done')completions.push({id,...e.message});c.receive(e);res.end();return;}
 res.statusCode=404;res.end();
 }catch(e){res.statusCode=500;res.end(e.stack);}});
await new Promise(r=>server.listen(0,'127.0.0.1',r));
const browser=await chromium.launch({executablePath:process.env.XYG_CHROMIUM,args:['--use-angle=swiftshader','--enable-unsafe-swiftshader','--ignore-gpu-blocklist']}),page=await browser.newPage({viewport:{width:900,height:3200}}),errors=[];page.on('pageerror',e=>errors.push(e.message));
const idle=()=>Promise.all(bindings.map(b=>b.whenIdle()));
const pixels=()=>page.evaluate(async()=>{await new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)));return Promise.all(window.views.map(async v=>{const p=v.view;p._drawNow();const gl=p.gl,c=p.canvas;let data;if(p._glHost)data=p._present2d.getImageData(0,0,c.width,c.height).data;else{data=new Uint8Array(gl.drawingBufferWidth*gl.drawingBufferHeight*4);gl.readPixels(0,0,gl.drawingBufferWidth,gl.drawingBufferHeight,gl.RGBA,gl.UNSIGNED_BYTE,data);}let colored=0,hash=0;for(let i=0;i<data.length;i++){hash=(hash*31+data[i])>>>0;if(i%4===0&&Math.max(data[i],data[i+1],data[i+2])-Math.min(data[i],data[i+1],data[i+2])>30)colored++;}return {colored,hash,sha256:Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',data))).map(x=>x.toString(16).padStart(2,'0')).join('')};}));});
try{
 await page.goto('http://127.0.0.1:'+server.address().port);await idle();assert.ok(bindings.every(b=>!b.error));
 if(process.env.XYG_GEO_IDLE_DIAGNOSTIC==='1'){await diagnoseIdlePaint(page,artifactDirectory);}else{
 const initial=await pixels();assert.ok(initial.every(p=>p.colored>0));
 assert.deepEqual(await pixels(),initial,"idle paint stability");
 const prepared=new Promise(r=>held=r);hold=true;temporalControllerSetCursor(h,4n);await prepared;
 const old=fixture.views.map(f=>f.adapter.frame.handle);
 for(let n=10;n<1010;n++)temporalControllerSetCursor(h,BigInt(n));
 assert.equal(bindings.filter(b=>b.active).length,1);assert.equal(new Set(bindings.map(b=>b.source)).size,1);
 assert.deepEqual(await pixels(),initial);unhold();await idle();assert.ok(bindings.every(b=>!b.error));
 for(let n=1010;n<1015;n++){temporalControllerSetCursor(h,BigInt(n));temporalControllerSetRange(h,BigInt(n),BigInt(n+1));await idle();}
 const final=await pixels();assert.deepEqual(final,initial);
 for(const [i,f] of fixture.views.entries()){assert.equal(f.adapter.frame.data.selection.id(0),0xffffffffffffffffn);assert.notEqual(f.adapter.frame.handle,old[i]);const time=f.adapter.frame.data.identity.time;assert.equal(time.instant??time.start,1014n);}
 if(fixture.views[0].adapter.frame.data.aggregate){
  for(let i=0;i<5;i++){
   const membership=await page.evaluate(async i=>{let cursor,ordinal=0,pages=0;do{const p=await window.views[i].membership(0,{maxProjectedVertices:1000000n,cursor});pages++;for(const r of p.records){if(r.featureId!==(ordinal?BigInt(ordinal):0xffffffffffffffffn)||r.sourceRow!==BigInt(ordinal))throw Error('exact membership mismatch');ordinal++;}cursor=p.cursor;}while(cursor);return {ordinal,pages};},i);
   assert.deepEqual(membership,{ordinal:32769,pages:9});assert.equal(fixture.views[i].adapter.frame.data.record(0).count,32769n);
  }
 }
 // Half-open native predicates change real membership in all five views.
 temporalControllerSetRange(h,99999n,100000n);await idle();assert.deepEqual(await pixels(),initial);
 temporalControllerSetRange(h,100000n,100001n);await idle();
 const empty=await pixels();assert.ok(empty.every(p=>p.colored===0));assert.ok(empty.every(p=>p.sha256===empty[0].sha256));assert.notEqual(empty[0].sha256,initial[0].sha256);
 for(let i=0;i<5;i++){assert.equal(fixture.views[i].adapter.frame.data.visibleVertices,0n);assert.equal(fixture.views[i].adapter.frame.data.selection.id(0),0xffffffffffffffffn);const hits=await page.evaluate(i=>window.views[i].pick({x:400,y:300,maxHits:10}),i);assert.equal(hits.records.length,0);}
 temporalControllerSetRange(h,1014n,1015n);await idle();assert.deepEqual(await pixels(),initial);
 for(const f of fixture.views)assert.equal(f.adapter.frame.data.visibleVertices,f.adapter.frame.data.aggregate?32769n:2n);
 const hits=[];for(let i=0;i<5;i++)hits.push(await page.evaluate(i=>window.views[i].pick({x:400,y:300,maxHits:10}),i));assert.ok(hits.every(h=>h.records.some(r=>r.featureId===0xffffffffffffffffn||r.kind==='cell')));
 for(let i=0;i<5;i++){
  const before=fixture.views[i].adapter.frame.data.identity.camera.centerX;
  await page.locator('#chart'+i).focus();for(let n=0;n<=i;n++)await page.keyboard.press('ArrowRight');
  await page.evaluate(i=>window.views[i].gestureChain,i);
  assert.notEqual(fixture.views[i].adapter.frame.data.identity.camera.centerX,before);
 }
 assert.equal(new Set(fixture.views.map(f=>f.adapter.frame.data.identity.camera.centerX)).size,5);
 // Inject an actual external page failure, preserving the accepted picture.
 const read=fixture.views[0].source.hierarchyReadPage;let fail=true;
 fixture.views[0].source.hierarchyReadPage=async ticket=>{if(fail){fail=false;throw Error('five-view page failure');}return read(ticket);};
 const beforeFailure=await pixels();temporalControllerSetCursor(h,1016n);await idle();
 assert.equal(fail,false);assert.equal(bindings.filter(b=>!!b.error).length,1);assert.deepEqual(await pixels(),beforeFailure);
 fixture.views[0].source.hierarchyReadPage=read;temporalControllerSetCursor(h,1017n);await idle();assert.ok(bindings.every(b=>!b.error));
 // All old realms perform actual release; fresh realms handshake independently.
 const cameraBeforeReload=fixture.views.map(f=>f.adapter.frame.data.identity.camera),mounts=fixture.views.map(f=>f.adapter.mount),beforeReload=await pixels();
 const oldCompletions=[...completions];await page.evaluate(()=>Promise.all(window.views.map(v=>v.dispose())));
 assert.ok(fixture.views.every(f=>!f.adapter.mounted));await page.reload();await idle();
 assert.ok(fixture.views.every((f,i)=>f.adapter.mount!==mounts[i]));assert.deepEqual(fixture.views.map(f=>f.adapter.frame.data.identity.camera),cameraBeforeReload);assert.deepEqual(await pixels(),beforeReload);
 // Repeated close cannot free a held native owner. Replay a genuine old receipt.
 const cancellationPrepared=new Promise(r=>held=r);hold=true;temporalControllerSetCursor(h,1018n);await cancellationPrepared;
 const owner=bindings[heldView],active=owner.active,prior=oldCompletions.find(m=>m.id===heldView);
 channels[heldView].receive({message:prior,buffers:[]});assert.equal(owner.active,active);
 const closing=owner.dispose();await page.waitForFunction(i=>window.views[i].temporal?.cancelled===true,heldView);
 assert.equal(bindings.filter(b=>b.active).length,1);assert.ok(fixture.views[heldView].adapter.liveCandidate.frame);
 for(let n=1020;n<1030;n++)temporalControllerSetCursor(h,BigInt(n));assert.equal(owner.active,active);
 failAbort=2;unhold();await assert.rejects(closing,/lost five-view abort ACK/);
 assert.equal(owner.blocked,true);assert.equal(owner.active,active);assert.equal(bindings.filter(b=>b.active).length,1);
 assert.throws(()=>channels[heldView].host.bindTemporal(h),/already/);
 await owner.dispose();assert.equal(failAbort,0);bindings[heldView]=channels[heldView].host.bindTemporal(h);await idle();assert.ok(bindings.every(b=>!b.error));
 for(const f of fixture.views)assert.equal(f.adapter.frame.data.identity.time.instant??f.adapter.frame.data.identity.time.start,1029n);
 const groupOptions={groupId:777n,domainStart:-(1n<<63n),domainEnd:(1n<<63n)-1n,cursor:1029n,window:0n,step:1n};
 const groupA=temporalControllerCreate({...groupOptions,instanceId:993n}),groupB=temporalControllerCreate({...groupOptions,instanceId:994n});
 try{
  await bindings[2].dispose();await bindings[3].dispose();bindings[2]=channels[2].host.bindTemporal(groupA);bindings[3]=channels[3].host.bindTemporal(groupB);await idle();
  temporalControllerSetCursor(groupA,31n);assert.equal(temporalCoordinateDeliver(temporalControllerPollEvent(groupA)),1);await idle();
  assert.equal(fixture.views[2].adapter.frame.data.identity.time.instant,31n);assert.equal(fixture.views[3].adapter.frame.data.identity.time.instant,31n);
  assert.equal(fixture.views[0].adapter.frame.data.identity.time.instant??fixture.views[0].adapter.frame.data.identity.time.start,1029n);
 }finally{for(const i of [2,3])await bindings[i].dispose();temporalControllerDestroy(groupA);temporalControllerDestroy(groupB);}
 const independent=temporalControllerCreate({instanceId:992n,domainStart:-(1n<<63n),domainEnd:(1n<<63n)-1n,cursor:1014n,window:0n,step:1n});
 try{
  await bindings[4].dispose();bindings[4]=channels[4].host.bindTemporal(independent);await idle();
  temporalControllerSetCursor(independent,23n);await idle();assert.equal(fixture.views[4].adapter.frame.data.identity.time.instant,23n);
  assert.equal(fixture.views[0].adapter.frame.data.identity.time.instant??fixture.views[0].adapter.frame.data.identity.time.start,1029n);
 }finally{await bindings[4].dispose();temporalControllerDestroy(independent);}
 assert.ok(completions.some(m=>m.status==='superseded'&&m.drained));assert.equal(errors.length,0);
 await page.screenshot({path:artifactDirectory+'/five-'+(process.env.XYG_GEO_AGGREGATE==='1'?'reduced':process.env.XYG_GEO_RANGE==='1'?'range':'direct')+'.png',fullPage:true});
 console.log(JSON.stringify({views:5,canonicalSources:1,peakCandidates:peak,initial,final,completions:completions.length,selectedIntent:'18446744073709551615',aggregate:!!fixture.views[0].adapter.frame.data.aggregate}));
}
}catch(error){
 await page.screenshot({path:artifactDirectory+'/failure-'+(process.env.XYG_GEO_AGGREGATE==='1'?'reduced':'direct')+'.png',fullPage:true});throw error;
}finally{
 if(unhold)unhold();for(const b of bindings)await b.dispose();
 await page.evaluate(()=>Promise.all(window.views.map(v=>v.dispose())));await page.close();await browser.close();for(const c of channels)c.poll?.end();server.closeAllConnections();await new Promise(r=>server.close(r));temporalControllerDestroy(h);await fixture.dispose();
}
