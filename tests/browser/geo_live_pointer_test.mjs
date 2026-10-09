// Actual packaged paint client + real native GeoHostAdapter, strict binary RPC.
import assert from 'node:assert/strict';
import {createServer} from 'node:http';
import {readFile} from 'node:fs/promises';
import {chromium} from 'playwright';
import {encodeGeoViewportRequest,decodeGeoViewportResponse,geoViewportExecute} from '../../packages/xy-node/src/geoviewport.js';
import {liveFixture,release} from '../../packages/xy-node/test/geo-live-host-fixture.mjs';
const fixtures=[await liveFixture()],preparations=[];
let held,releaseHold,hold=false,corrupt=false,fault;
const server=createServer(async(req,res)=>{
 try{
  if(req.url==='/'){res.setHeader('Content-Type','text/html');res.end('<!doctype html><style>.chart{width:800px;height:600px}</style>'+Array.from({length:1},(_,i)=>`<div id="c${i}" class="chart" tabindex="0" style="touch-action:manipulation"></div>`).join('')+'<script type="module" src="/page.js"></script>');return;}
  if(req.url==='/index.js'){res.setHeader('Content-Type','text/javascript');res.end(await readFile('packages/xy-client/dist/index.js'));return;}
  if(req.url==='/page.js'){res.setHeader('Content-Type','text/javascript');res.end(`import {XygGeoHostView} from '/index.js';window.views=Array.from({length:1},(_,i)=>{let callback;return new XygGeoHostView(document.getElementById('c'+i),{onMessage:c=>{callback=c;return()=>callback=undefined;},send:(message,buffers)=>{fetch('/rpc/'+i,{method:'POST',headers:{'x-request':message.request,'x-mount':message.mount},body:buffers[0]}).then(async r=>{if(!r.ok){callback?.({type:'geo_host',request:message.request,...(await r.json())},[]);return;}const b=await r.arrayBuffer(),v=new DataView(b),out=[];let at=4;for(let j=0;j<v.getUint32(0,true);j++){const n=v.getUint32(at,true);at+=4;out.push(b.slice(at,at+n));at+=n;}callback?.({type:'geo_host',request:message.request},out);}).catch(e=>callback?.({type:'geo_host',request:message.request,error:e.message},[]));}});});window.ready=Promise.all(window.views.map(v=>v.ready));`);return;}
  const id=Number(req.url?.split('/').at(-1));if(!req.url?.startsWith('/rpc/')||!Number.isInteger(id)||id<0||id>=1){res.statusCode=404;res.end();return;}
  const chunks=[];let size=0;for await(const chunk of req){size+=chunk.length;if(size>256)throw Error('oversized request');chunks.push(chunk);}const raw=Uint8Array.from(Buffer.concat(chunks)).buffer;
  const op=new DataView(raw).getUint32(8,true);let expected;
  if(op===6){const cameraRequest=raw.slice(96,224),v=new DataView(cameraRequest);try{expected=decodeGeoViewportResponse(geoViewportExecute(cameraRequest,1<<20)).camera;}catch{}preparations.push({operation:v.getUint32(8,true),args:Array.from({length:2},(_,i)=>v.getFloat64(80+8*i,true)),sequence:new DataView(raw).getBigUint64(40,true).toString(),baseline:fixtures[id].adapter.frame.data.identity.camera});}
  const [message,attachments]=await fixtures[id].adapter.handle({type:'geo_host',request:req.headers['x-request'],mount:req.headers['x-mount']},[raw]);
  if(op===6&&!message.error)assert.deepEqual(fixtures[id].adapter.liveCandidate.frame.data.identity.camera,expected);
  if(op===6&&hold){hold=false;await new Promise(resolve=>{releaseHold=resolve;held=true;});held=false;}
  if(message.error){res.statusCode=400;res.end(JSON.stringify(message));return;}
  if(fault===op){fault=undefined;if(op===8||op===9){res.statusCode=503;res.end(JSON.stringify({error:'lost ACK confirmation'}));}else res.end(Buffer.alloc(4));return;}
  const parts=[Buffer.alloc(4)];parts[0].writeUInt32LE(attachments.length);
  for(let i=0;i<attachments.length;i++){const value=attachments[i],b=Buffer.from(value instanceof ArrayBuffer?new Uint8Array(value):value);if(op===6&&i===2&&corrupt){corrupt=false;b[0]^=1;}const n=Buffer.alloc(4);n.writeUInt32LE(b.length);parts.push(n,b);}
  res.setHeader('Content-Type','application/octet-stream');res.end(Buffer.concat(parts));
 }catch(error){res.statusCode=500;res.end(error.stack);}
});
await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
const browser=await chromium.launch({executablePath:process.env.XYG_CHROMIUM??'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',args:['--use-angle=swiftshader','--enable-unsafe-swiftshader','--ignore-gpu-blocklist']});
const page=await browser.newPage({viewport:{width:1000,height:3200}}),errors=[];page.on('pageerror',e=>errors.push(e.message));
const drain=()=>page.evaluate(()=>window.views[0].gestureChain);
const waitHeld=async()=>{for(let i=0;i<100&&!held;i++)await new Promise(r=>setTimeout(r,10));assert.equal(held,true);};
try{
 await page.goto(`http://127.0.0.1:${server.address().port}`);await page.evaluate(()=>window.ready);
 assert.equal(await page.locator('#c0').evaluate(e=>e.style.touchAction),'none');
 const registrationFailure=await page.evaluate(()=>{const el=document.createElement('div');el.style.touchAction='manipulation';document.body.append(el);let thrown=false,sends=0;try{new window.views[0].constructor(el,{send(){sends++;},onMessage(){throw Error('registration failure');}});}catch{thrown=true;}const event=new WheelEvent('wheel',{cancelable:true});el.dispatchEvent(event);const result={thrown,sends,touchAction:el.style.touchAction,defaultPrevented:event.defaultPrevented};el.remove();return result;});
 assert.deepEqual(registrationFailure,{thrown:true,sends:0,touchAction:'manipulation',defaultPrevented:false});
 const before=preparations.length;
 await page.locator('#c0').evaluate(e=>{for(const type of ['pointerdown','pointermove','pointerup'])e.dispatchEvent(new PointerEvent(type,{bubbles:true,pointerId:1,isPrimary:true,button:0,buttons:1,clientX:100,clientY:100}));e.dispatchEvent(new WheelEvent('wheel',{bubbles:true,deltaY:-120}));e.dispatchEvent(new KeyboardEvent('keydown',{bubbles:true,key:'ArrowRight'}));});
 await drain();assert.equal(preparations.length,before);
 // Screen deltas are transported to Rust, scaled to its CSS viewport; dragging
 // right moves the map right (the camera center receives the opposite delta).
 await page.mouse.move(200,200);await page.mouse.down();await page.mouse.move(240,180);await page.mouse.up();await drain();
 assert.deepEqual(preparations.at(-1).args,[-40,20]);assert.equal(preparations.at(-1).operation,3);
 await page.evaluate(()=>{window.views[0].view.canvas.style.width='400px';window.views[0].view.canvas.style.height='300px';});
 await page.mouse.move(100,100);await page.mouse.down();await page.mouse.move(160,140);await page.mouse.up();await drain();
 assert.deepEqual(preparations.at(-1).args,[-120,-80]);
 // A gesture arriving during a programmatic update waits for its accepted
 // camera/time, then serializes keyboard pan and relative wheel zoom in order.
 hold=true;await page.evaluate(()=>{const v=window.views[0],i=v.identity;window.manual=v.update({operation:8,args:[1,0],sequence:i.sequence+1n,cameraRevision:i.cameraRevision+1n,timeRevision:i.timeRevision,stateRevision:i.stateRevision,time:i.time});});await waitHeld();
 const first=preparations.length-1;
 await page.locator('#c0').focus();await page.keyboard.press('ArrowRight');await page.mouse.move(300,250);await page.mouse.wheel(0,-120);await page.mouse.wheel(0,-60);
 releaseHold();await page.evaluate(()=>window.manual);await drain();
 assert.deepEqual(preparations.slice(first).map(p=>p.operation),[8,3,4,4]);
 assert.equal(preparations.at(-2).args[0],0.25);assert.equal(preparations.at(-1).args[0],0.375);
 // Camera limits remain Rust-owned. An out-of-range wheel target is rejected
 // without changing the accepted paint; the next valid wheel input recovers.
 const zoomOwner=await page.evaluate(()=>window.views[0].owner.toString());
 await page.mouse.wheel(0,480);await drain();assert.equal(await page.evaluate(()=>window.views[0].owner.toString()),zoomOwner);
 assert.equal(await page.evaluate(()=>window.views[0].identity.camera.zoom),0.375);
 await page.mouse.wheel(0,-120);await drain();assert.equal(await page.evaluate(()=>window.views[0].identity.camera.zoom),0.625);
 // Reader failure is terminal absence. Old paint survives; a later physical
 // gesture recovers with higher exact revisions, without uncertain replay.
 const old=await page.evaluate(()=>window.views[0].owner.toString()),reader=fixtures[0].source.readChunk;
 fixtures[0].source.readChunk=async()=>{throw Error('pointer fixture reader failure');};
 await page.mouse.move(300,250);await page.mouse.down();await page.mouse.move(310,250);await page.mouse.up();await drain();
 assert.equal(await page.evaluate(()=>window.views[0].owner.toString()),old);assert.equal(fixtures[0].adapter.liveCandidate.frame,undefined);
 assert.equal(await page.locator('#c0 [role=alert]').count(),1);fixtures[0].source.readChunk=reader;
 await page.mouse.move(300,250);await page.mouse.down();await page.mouse.move(305,250);await page.mouse.up();await drain();
 assert.notEqual(await page.evaluate(()=>window.views[0].owner.toString()),old);
 // Holding one response permits genuine high-rate pointer input. Admission
 // stops at16 ordered samples and one alert; accepted samples are not summed,
 // reordered or dropped (Rust polar/world-wrap policy applies to every sample).
 hold=true;await page.mouse.move(300,250);await page.mouse.down();await page.mouse.move(301,250);await waitHeld();
 const burst=preparations.length-1;
 for(let x=302;x<=326;x++)await page.mouse.move(x,250);await page.mouse.up();
 assert.equal(await page.evaluate(()=>window.views[0].gestureQueued),16);assert.equal(await page.locator('#c0 [role=alert]').count(),1);
 releaseHold();await drain();assert.equal(preparations.length-burst,16);assert.ok(preparations.slice(burst).every(p=>p.operation===3&&p.args[0]===-1&&p.args[1]===0));
 assert.ok(preparations.every((p,i)=>i===0||BigInt(p.sequence)>BigInt(preparations[i-1].sequence)));
 if(process.env.XYG_GEO_POINTER_SCREENSHOT){await page.evaluate(()=>new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r))));await page.locator('#c0').screenshot({path:process.env.XYG_GEO_POINTER_SCREENSHOT});}
 // Close while captured and while a reply is held releases pointer capture
 // immediately; pending samples cannot issue a new preparation after close.
 hold=true;await page.mouse.move(300,250);await page.mouse.down();await page.mouse.move(301,250);await waitHeld();const atClose=preparations.length;
 await page.evaluate(()=>{window.pointerDisposed=window.views[0].dispose();});assert.equal(await page.evaluate(()=>window.views[0].pointer),undefined);
 await page.mouse.move(310,250);await page.mouse.up();releaseHold();await page.evaluate(()=>window.pointerDisposed);
 assert.equal(preparations.length,atClose);assert.equal(fixtures[0].adapter.mounted,false);assert.equal(await page.locator('#c0').evaluate(e=>e.style.touchAction),'manipulation');assert.deepEqual(errors,[]);
 console.log(JSON.stringify({ok:true,browser:browser.version(),registrationFailureCleanup:true,untrustedIgnored:true,trustedDrag:true,cssViewportScaling:true,programmaticAndGestureOrdering:true,relativeWheel:true,rustZoomLimitRecovery:true,readFailureRecovery:true,orderedSampleCap:16,oneOverflowAlert:true,closeCaptured:true,touchActionRestored:true,preparations}));
}finally{releaseHold?.();await browser.close();await new Promise(resolve=>server.close(resolve));for(const f of fixtures)await release(f);}
