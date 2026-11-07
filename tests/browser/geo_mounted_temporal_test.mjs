import {encodeGeoViewportRequest,decodeGeoViewportResponse,geoViewportExecute} from '../../packages/xy-node/src/geoviewport.js';
// Real Node/native host and packaged strict-CSP browser over binary attachments.
import assert from 'node:assert/strict';
import {createServer} from 'node:http';
import {readFile,writeFile} from 'node:fs/promises';
import {chromium} from 'playwright';
import {release} from '../../packages/xy-node/test/geo-live-host-fixture.mjs';
import {attachGeoWebview} from '../../packages/xy-node/src/geo-webview.js';
import {temporalControllerCreate,temporalControllerSetCursor,temporalControllerDestroy,temporalControllerSetRange,temporalControllerState,temporalControllerSetSelection} from '../../packages/xy-node/src/index.js';
const {mountedFixture}=await import('../../packages/xy-node/test/geo-mounted-temporal-fixture.mjs');
const f=await mountedFixture({selected:process.env.XYG_GEO_SELECTED!=='0',aggregate:process.env.XYG_GEO_AGGREGATE==='1'}),I64=-(1n<<63n),MAX=(1n<<63n)-1n;
let receive,disposed,poll,hold,unhold,held,caller;
const outgoing=[],receipts=[],operations=new Map(),controlWaiters=new Map(),controlFrames=[];let failAbort=0,corruptMembership=false;
function pack({message,buffers=[]}){const meta=Buffer.from(JSON.stringify(message)),parts=[Buffer.alloc(8),meta];parts[0].writeUInt32LE(meta.length);parts[0].writeUInt32LE(buffers.length,4);for(const raw of buffers){const b=Buffer.from(new Uint8Array(raw)),n=Buffer.alloc(4);n.writeUInt32LE(b.length);parts.push(n,b);}return Buffer.concat(parts);}
function unpack(raw){const ml=raw.readUInt32LE(),count=raw.readUInt32LE(4),message=JSON.parse(raw.subarray(8,8+ml));let at=8+ml;const buffers=[];for(let i=0;i<count;i++){const n=raw.readUInt32LE(at);at+=4;buffers.push(Uint8Array.from(raw.subarray(at,at+n)).buffer);at+=n;}assert.equal(at,raw.length);return {message,buffers};}
const panel={webview:{onDidReceiveMessage(callback){receive=callback;return {dispose(){}};},async postMessage(envelope){
 if(envelope.message.type==='geo_host'&&envelope.buffers?.[0]&&new DataView(envelope.buffers[0]).getUint32(8,true)===6&&hold){hold=false;held?.();await new Promise(resolve=>unhold=resolve);}
 if(envelope.message.type==='geo_host_temporal')controlFrames.push(Buffer.from(envelope.buffers[0]).toString('hex'));
 if(corruptMembership&&operations.get(envelope.message.request)===3&&envelope.buffers?.length===2){corruptMembership=false;const packet=envelope.buffers[1].slice(0);new Uint8Array(packet)[88]^=1;if(new DataView(packet).getUint32(72,true))new Uint8Array(packet)[256]^=1;envelope={message:envelope.message,buffers:[envelope.buffers[0],packet]};}
 if(operations.get(envelope.message.request)===9&&failAbort>0){failAbort--;envelope={message:{...envelope.message,error:'lost abort ACK'},buffers:[]};}
 const b=pack(envelope);if(poll){poll.end(b);poll=undefined;}else{assert.ok(outgoing.length<16);outgoing.push(b);}return true;
}},onDidDispose(callback){disposed=callback;return {dispose(){}};},dispose(){disposed();}};
const host=attachGeoWebview(panel,f.adapter);
const h=temporalControllerCreate({instanceId:31n,domainStart:I64,domainEnd:MAX,cursor:I64,window:0n,step:1n});
let originalCurrent;
let binding=host.bindTemporal(h);temporalControllerSetCursor(h,3n);
const server=createServer(async(req,res)=>{try{
 if(req.url==='/'){res.setHeader('Content-Security-Policy',"default-src 'none'; script-src 'self'; connect-src 'self'; style-src 'unsafe-inline'; img-src data:; object-src 'none'; base-uri 'none'");res.end('<!doctype html><style>#chart{width:800px;height:600px}</style><div id="chart" tabindex="0"></div><script type="module" src="/page.js"></script>');return;}
 if(req.url==='/index.js'){res.setHeader('Content-Type','text/javascript');res.end(await readFile('packages/xy-client/dist/index.js'));return;}
 if(req.url==='/page.js'){res.setHeader('Content-Type','text/javascript');res.end(`import {XygGeoHostView} from '/index.js';
 const pack=(message,buffers=[])=>{const meta=new TextEncoder().encode(JSON.stringify(message)),size=8+meta.length+buffers.reduce((n,b)=>n+4+b.byteLength,0),b=new ArrayBuffer(size),v=new DataView(b);v.setUint32(0,meta.length,true);v.setUint32(4,buffers.length,true);new Uint8Array(b,8,meta.length).set(meta);let at=8+meta.length;for(const raw of buffers){v.setUint32(at,raw.byteLength,true);at+=4;new Uint8Array(b,at,raw.byteLength).set(new Uint8Array(raw));at+=raw.byteLength;}return b;};
 let callback;window.view=new XygGeoHostView(document.getElementById('chart'),{onMessage:c=>{callback=c;return()=>callback=undefined;},send:(message,buffers)=>{void fetch('/host',{method:'POST',body:pack(message,buffers)});}});
 (async()=>{while(callback){const r=await fetch('/next'),b=await r.arrayBuffer(),v=new DataView(b),ml=v.getUint32(0,true),count=v.getUint32(4,true),message=JSON.parse(new TextDecoder().decode(new Uint8Array(b,8,ml))),buffers=[];let at=8+ml;for(let i=0;i<count;i++){const n=v.getUint32(at,true);at+=4;buffers.push(b.slice(at,at+n));at+=n;}callback?.(message,buffers);}})();`);return;}
 if(req.url==='/next'){if(outgoing.length)res.end(outgoing.shift());else poll=res;return;}
 if(req.url==='/host'){const parts=[];let size=0;for await(const part of req){size+=part.length;assert.ok(size<4096);parts.push(part);}const envelope=unpack(Buffer.concat(parts));receipts.push(envelope.message);controlWaiters.get(envelope.message.request)?.(envelope.message);if(envelope.message.type==='geo_host')operations.set(envelope.message.request,new DataView(envelope.buffers[0]).getUint32(8,true));receive(envelope);res.end();return;}
 res.statusCode=404;res.end();
 }catch(error){res.statusCode=500;res.end(error.stack);}});
await new Promise(r=>server.listen(0,'127.0.0.1',r));
const browser=await chromium.launch({executablePath:process.env.XYG_CHROMIUM,args:['--use-angle=swiftshader','--enable-unsafe-swiftshader','--ignore-gpu-blocklist']});
const page=await browser.newPage({viewport:{width:900,height:700}}),errors=[];page.on('pageerror',e=>errors.push(e.message));
const pixels=()=>page.evaluate(async()=>{await new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)));const p=window.view.view;p._drawNow();const c=p.canvas;let data;if(p._glHost)data=p._present2d.getImageData(0,0,c.width,c.height).data;else{const gl=p.gl;data=new Uint8Array(gl.drawingBufferWidth*gl.drawingBufferHeight*4);gl.readPixels(0,0,gl.drawingBufferWidth,gl.drawingBufferHeight,gl.RGBA,gl.UNSIGNED_BYTE,data);}let red=0,xsum=0;for(let i=0;i<data.length;i+=4)if(data[i+3]>0&&Math.max(data[i],data[i+1],data[i+2])-Math.min(data[i],data[i+1],data[i+2])>30){red++;xsum+=(i/4)%c.width;}window.lastPaintCentroid=red?xsum/red:null;return red;});
try{
 await page.goto(`http://127.0.0.1:${server.address().port}`);await page.waitForFunction(()=>window.view);await page.evaluate(()=>window.view.ready);originalCurrent=f.source.current;await binding.whenIdle();assert.equal(binding.error,undefined);
 if(f.scope){assert.equal(f.adapter.frame.data.selection.namespace,0xffffffffffffffffn);assert.equal(f.adapter.frame.data.selection.id(0),0xffffffffffffffffn);}
 assert.equal(f.adapter.frame.data.identity.time.instant,3n);if(f.adapter.frame.data.aggregate){
  const membership=await page.evaluate(async()=>{let cursor,ordinal=0,pages=0;do{const page=await window.view.membership(0,{maxProjectedVertices:1000000n,cursor});pages++;for(const record of page.records){if(record.featureId!==(ordinal?BigInt(ordinal):0xffffffffffffffffn)||record.sourceRow!==BigInt(ordinal))throw Error('exact complete membership mismatch');ordinal++;}cursor=page.cursor;}while(cursor);return {ordinal,pages};});
  assert.deepEqual(membership,{ordinal:32769,pages:9});assert.equal(f.adapter.frame.data.record(0).count,32769n);
 }else assert.equal(await page.evaluate(()=>window.view.record(0).featureId),0xffffffffffffffffn);
 const framing=JSON.parse(await readFile('tests/fixtures/geo_mounted_temporal.json'));
 const fixtureDone=new Promise(resolve=>controlWaiters.set('fixture:min',resolve));
 await panel.webview.postMessage({message:{type:'geo_host_temporal',mount:f.adapter.mount,request:'fixture:min'},buffers:[Uint8Array.from(Buffer.from(framing.instantMin,'hex')).buffer]});
 assert.equal((await fixtureDone).status,'accepted');assert.equal(f.adapter.frame.data.identity.time.instant,I64);
 const noQuery=f.source.sequence;temporalControllerSetSelection(h,[0xffffffffffffffffn]);await binding.whenIdle();assert.equal(f.source.sequence,noQuery);
 if(f.adapter.frame.data.aggregate){corruptMembership=true;await assert.rejects(page.evaluate(()=>window.view.membership(0,{maxProjectedVertices:1000000n})),/unowned auxiliary/);assert.equal(f.adapter.aux,undefined);}

 const red=await pixels();assert.ok(red>0);const initialCentroid=await page.evaluate(()=>window.lastPaintCentroid);caller=await f.adapter.frame.retain();
 const hits=await page.evaluate(()=>window.view.pick({x:400,y:300,maxHits:10}));assert.ok(f.adapter.frame.data.aggregate?hits.records.some(h=>h.kind==='cell'&&h.count===32769n):hits.records.some(h=>h.featureId===0xffffffffffffffffn));
 // Hold an actual prepared native reply. New intent invalidates before CAS.
 hold=true;const prepared=new Promise(resolve=>held=resolve);temporalControllerSetCursor(h,4n);await prepared;
 const before=f.adapter.frame.handle,cameraBeforeDrag=f.adapter.frame.data.identity.camera;
 const rect=await page.locator('#chart canvas').first().boundingBox();await page.mouse.move(rect.x+rect.width/2,rect.y+rect.height/2);await page.mouse.down();await page.mouse.move(rect.x+rect.width/2+40,rect.y+rect.height/2);await page.mouse.up();
 const nativeCamera=(camera,op,args)=>decodeGeoViewportResponse(geoViewportExecute(encodeGeoViewportRequest(camera,op,args),1<<20)).camera;
 const dragged=nativeCamera(cameraBeforeDrag,3,[-40*cameraBeforeDrag.width/rect.width,0]);
 for(let i=0;i<1000;i++)temporalControllerSetCursor(h,BigInt(i+10));
 await page.waitForFunction(()=>window.view.temporal?.cancelled===true);unhold();await binding.whenIdle();assert.equal(binding.error,undefined);assert.equal(f.adapter.frame.data.identity.time.instant,1009n);
 assert.ok(receipts.some(m=>m.type==='geo_host_temporal_done'&&m.status==='superseded'&&m.drained));assert.notEqual(f.adapter.frame.handle,before);
 // Trusted wheel and ordered pans race with time and preserve native camera.
 const camera=f.adapter.frame.data.identity.camera;assert.deepEqual(camera,dragged);await page.locator('#chart').focus();await page.keyboard.press('ArrowRight');await page.keyboard.press('ArrowRight');temporalControllerSetCursor(h,1010n);
 await page.waitForFunction(x=>window.view.identity.camera.centerX!==x,camera.centerX);await binding.whenIdle();
 await page.mouse.move(400,300);await page.mouse.wheel(0,-240);temporalControllerSetCursor(h,1011n);
 await page.waitForFunction(()=>window.view.identity.camera.zoom===0.5);await binding.whenIdle();assert.equal(f.adapter.frame.data.identity.time.instant,1011n);
 const moved=f.adapter.frame.data.identity.camera;
 const panned=nativeCamera(nativeCamera(dragged,3,[40,0]),3,[40,0]);assert.deepEqual(moved,nativeCamera(panned,4,[0.5]));
 await pixels();const movedCentroid=await page.evaluate(()=>window.lastPaintCentroid);if(!f.adapter.frame.data.aggregate)assert.notEqual(movedCentroid,initialCentroid);
 // Half-open i64MAX endpoint removes all members and paint, then recovers.
 temporalControllerSetCursor(h,MAX);await binding.whenIdle();assert.equal(f.adapter.frame.data.aggregate?f.adapter.frame.data.record(0).count:BigInt(f.adapter.frame.data.length),0n);assert.equal(await pixels(),0);
 temporalControllerSetCursor(h,I64);await binding.whenIdle();assert.ok(await pixels()>0);
 const reader=f.source.readChunk;f.source.readChunk=async()=>{throw Error('injected storage failure');};const good=f.adapter.frame.data.identity;
 temporalControllerSetCursor(h,I64+1n);await binding.whenIdle();assert.match(binding.error.message,/storage failure/);assert.deepEqual(f.adapter.frame.data.identity,good);assert.ok(await pixels()>0);
 f.source.readChunk=reader;temporalControllerSetCursor(h,I64+2n);await binding.whenIdle();assert.equal(binding.error,undefined);
 await binding.dispose();assert.ok(await pixels()>0);binding=host.bindTemporal(h);await binding.whenIdle();
 // Drain failures retain the claim and last picture until an exact retry.
 hold=true;const drainPrepared=new Promise(resolve=>held=resolve);temporalControllerSetCursor(h,20n);await drainPrepared;
 temporalControllerSetCursor(h,21n);await page.waitForFunction(()=>window.view.temporal?.cancelled===true);failAbort=2;unhold();await binding.whenIdle();assert.match(binding.error.message,/lost abort/);
 assert.throws(()=>f.chart.bindTemporal(h),/already/);await binding.dispose();binding=host.bindTemporal(h);await binding.whenIdle();assert.equal(binding.error,undefined);
 // Actual native reader remains admitted through disposal; no second query pump.
 if(f.scope){
  hold=true;const closePrepared=new Promise(resolve=>held=resolve);temporalControllerSetCursor(h,22n);await Promise.race([closePrepared,binding.whenIdle().then(()=>{throw binding.error??Error("preparation completed before hold");})]);
  const close=binding.dispose();assert.throws(()=>f.chart.bindTemporal(h),/already/);unhold();await close;
 }else{
  const savedReader=f.source.readChunk;let entered,readRelease;const readEntered=new Promise(resolve=>entered=resolve),readGate=new Promise(resolve=>readRelease=resolve);
  f.source.readChunk=async ticket=>{entered();await readGate;return savedReader(ticket);};
  temporalControllerSetCursor(h,22n);await readEntered;const close=binding.dispose();assert.throws(()=>f.chart.bindTemporal(h),/already/);readRelease();await close;f.source.readChunk=savedReader;
 }
 // A real release and new mount keep the accepted anchor and latest intent.
 await page.evaluate(()=>window.view.dispose());
 binding=host.bindTemporal(h);temporalControllerSetCursor(h,23n);await page.reload();await page.waitForFunction(()=>window.view);await page.evaluate(()=>window.view.ready);await binding.whenIdle();assert.equal(binding.error,undefined);assert.equal(f.adapter.frame.data.identity.time.instant,23n);
 await binding.dispose();temporalControllerSetRange(h,21n,25n);binding=host.bindTemporal(h,'range');await binding.whenIdle();
 const state=temporalControllerState(h);assert.deepEqual(f.adapter.frame.data.identity.time,{kind:2,start:state.rangeStart,end:state.rangeEnd});temporalControllerSetRange(h,99999n,100000n);await binding.whenIdle();assert.equal(f.adapter.frame.data.aggregate?f.adapter.frame.data.record(0).count:BigInt(f.adapter.frame.data.length),f.adapter.frame.data.aggregate?32769n:2n);temporalControllerSetRange(h,100000n,100001n);await binding.whenIdle();assert.equal(f.adapter.frame.data.aggregate?f.adapter.frame.data.record(0).count:BigInt(f.adapter.frame.data.length),0n);assert.equal(await pixels(),0);await binding.dispose();
 assert.equal(caller.data.aggregate?caller.data.record(0).count:caller.data.record(0).featureId,caller.data.aggregate?32769n:0xffffffffffffffffn);await caller.dispose();await binding.dispose();
 const closingHandle=temporalControllerCreate({instanceId:33n,domainStart:I64,domainEnd:MAX,cursor:7n,window:0n,step:1n});
 hold=true;const disposedPrepared=new Promise(resolve=>held=resolve);const disposedBinding=host.bindTemporal(closingHandle);await disposedPrepared;temporalControllerDestroy(closingHandle);assert.throws(()=>host.bindTemporal(h),/already/);unhold();await disposedBinding.dispose();
 temporalControllerSetCursor(h,6n);binding=host.bindTemporal(h);await binding.whenIdle();assert.equal(binding.error,undefined);await binding.dispose();
 assert.ok(controlFrames.includes(framing.invalidate));assert.ok(controlFrames.includes(framing.drain));
 if(process.env.XYG_GEO_MOUNTED_CAPTURE)await page.screenshot({path:process.env.XYG_GEO_MOUNTED_CAPTURE});
 const finalFrame=f.adapter.frame;await page.evaluate(()=>window.view.dispose());assert.equal(f.adapter.mounted,false);assert.equal(f.adapter.liveCandidate.frame,undefined);assert.equal(f.adapter.liveCandidate.retired,undefined);assert.deepEqual(errors,[]);assert.equal(f.source.current,originalCurrent);
 await release(f);await f.scope?.dispose();assert.equal(f.adapter.anchor,undefined);assert.throws(()=>finalFrame.data,/disposed/);
 const report={ok:true,host:'packaged strict-CSP browser + attachGeoWebview + Node22 native ABI401',browser:browser.version(),coloredPixels:red,exactPick:true,heldPrepareSuperseded:true,orderedCamera:moved,initialCentroid,movedCentroid,trustedPointer:true,remount:true,range:true,detachRetry:true,closeDuringRead:!f.scope,closeDuringPreparedReply:!!f.scope,selectedFullIdentity:!!f.scope,aggregateMembership:process.env.XYG_GEO_AGGREGATE==='1',exactI64Endpoint:true,lastGoodOnFailure:true,independentCaller:true,rebind:true,releaseACK:true,allNativeOwnersClosed:true,currentPublicationPreserved:true,controllerCloseDuringPublication:true,corruptMembershipRejected:process.env.XYG_GEO_AGGREGATE==='1',receipts};
 if(process.env.XYG_GEO_MOUNTED_REPORT)await writeFile(process.env.XYG_GEO_MOUNTED_REPORT,JSON.stringify(report,(_,v)=>typeof v==='bigint'?String(v):v,2)+'\n');console.log(JSON.stringify({...report,receipts:receipts.length}));
}catch(error){console.error('PRIMARY',error.stack);throw error;}finally{unhold?.();await browser.close();poll?.end();server.closeAllConnections();await new Promise(r=>server.close(r));await caller?.dispose();await release(f);await f.scope?.dispose();try{temporalControllerDestroy(h);}catch{}}
