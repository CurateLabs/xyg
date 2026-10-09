// Actual packaged paint client + real native GeoHostAdapter, strict binary RPC.
import assert from 'node:assert/strict';
import {createServer} from 'node:http';
import {readFile} from 'node:fs/promises';
import {chromium} from 'playwright';
import {encodeGeoViewportRequest,decodeGeoViewportResponse,geoViewportExecute} from '../../packages/xy-node/src/geoviewport.js';
import {hierarchyFiveFixtures,releaseFive} from '../../packages/xy-node/test/geo-live-hierarchy-fixture.mjs';
const fixtures=await hierarchyFiveFixtures();
let held,releaseHold,hold=false,corrupt=false,fault;
const server=createServer(async(req,res)=>{
 try{
  if(req.url==='/'){res.setHeader('Content-Type','text/html');res.end('<!doctype html><style>.chart{width:800px;height:600px}</style>'+Array.from({length:5},(_,i)=>`<div id="c${i}" class="chart" tabindex="0"></div>`).join('')+'<script type="module" src="/page.js"></script>');return;}
  if(req.url==='/index.js'){res.setHeader('Content-Type','text/javascript');res.end(await readFile('packages/xy-client/dist/index.js'));return;}
  if(req.url==='/page.js'){res.setHeader('Content-Type','text/javascript');res.end(`import {XygGeoHostView} from '/index.js';window.views=Array.from({length:5},(_,i)=>{let callback;return new XygGeoHostView(document.getElementById('c'+i),{onMessage:c=>{callback=c;return()=>callback=undefined;},send:(message,buffers)=>{fetch('/rpc/'+i,{method:'POST',headers:{'x-request':message.request,'x-mount':message.mount},body:buffers[0]}).then(async r=>{if(!r.ok){callback?.({type:'geo_host',request:message.request,...(await r.json())},[]);return;}const b=await r.arrayBuffer(),v=new DataView(b),out=[];let at=4;for(let j=0;j<v.getUint32(0,true);j++){const n=v.getUint32(at,true);at+=4;out.push(b.slice(at,at+n));at+=n;}callback?.({type:'geo_host',request:message.request},out);}).catch(e=>callback?.({type:'geo_host',request:message.request,error:e.message},[]));}});});window.ready=Promise.all(window.views.map(v=>v.ready));`);return;}
  const id=Number(req.url?.split('/').at(-1));if(!req.url?.startsWith('/rpc/')||!Number.isInteger(id)||id<0||id>=5){res.statusCode=404;res.end();return;}
  const chunks=[];let size=0;for await(const chunk of req){size+=chunk.length;if(size>256)throw Error('oversized request');chunks.push(chunk);}const raw=Uint8Array.from(Buffer.concat(chunks)).buffer;
  const [message,attachments]=await fixtures[id].adapter.handle({type:'geo_host',request:req.headers['x-request'],mount:req.headers['x-mount']},[raw]);
  const op=new DataView(raw).getUint32(8,true);
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
try{
 await page.goto(`http://127.0.0.1:${server.address().port}`);await page.waitForFunction(()=>window.ready);await page.evaluate(()=>window.ready);
 const initial=await page.evaluate(()=>window.views.map(v=>({owner:v.owner.toString(),sequence:v.sequence.toString(),records:v.record(0).featureId.toString()})));assert.equal(initial.length,5);
 corrupt=true;const failed=await page.evaluate(async()=>{const v=window.views[0],i=v.identity,owner=v.owner;try{await v.update({operation:3,args:[1,0],sequence:4n,cameraRevision:4n,timeRevision:4n,stateRevision:1n,time:{kind:0}});return false;}catch{return v.owner===owner&&v.identity.sequence===i.sequence;}});assert.equal(failed,true);assert.equal(fixtures[0].adapter.liveCandidate.frame,undefined);
 hold=true;await page.evaluate(()=>{const v=window.views[0];window.first=v.update({operation:8,args:[2,0],sequence:5n,cameraRevision:5n,timeRevision:5n,stateRevision:1n,time:{kind:0}}).then(()=>false,e=>e.name==='AbortError');});
 for(let i=0;i<100&&!held;i++)await new Promise(r=>setTimeout(r,10));assert.equal(held,true);
 await page.evaluate(()=>{const v=window.views[0];window.middle=v.update({operation:8,args:[3,0],sequence:6n,cameraRevision:6n,timeRevision:6n,stateRevision:1n,time:{kind:0}}).then(()=>false,e=>e.name==='AbortError');window.last=v.update({operation:8,args:[4,0],sequence:7n,cameraRevision:7n,timeRevision:7n,stateRevision:1n,time:{kind:0}});});releaseHold();
 assert.deepEqual(await page.evaluate(async()=>{await window.last;return [await window.first,await window.middle,window.views[0].identity.sequence.toString(),window.views[0].identity.time.kind];}),[true,true,'7',0]);
 assert.equal(fixtures[0].adapter.liveCandidate.retired,undefined);
 for(const op of [6,7,8,9]){
  fault=op;if(op===9)corrupt=true;
  const before=fixtures[0].lane.sequence;
  const outcome=await page.evaluate(async seq=>{const v=window.views[0];try{await v.update({operation:8,args:[4,0],sequence:BigInt(seq),cameraRevision:BigInt(seq),timeRevision:BigInt(seq),stateRevision:1n,time:{kind:0}});return 'success';}catch{return 'failed';}},(before+1n).toString());
  assert.equal(outcome,'failed');
  await page.evaluate(()=>window.views[0].recover());assert.equal(fixtures[0].adapter.liveCandidate.frame,undefined);assert.equal(fixtures[0].adapter.liveCandidate.retired,undefined);
 }
 // A definite backend failure clears preparation uncertainty and permits a new sequence.
 fixtures[0].control.failRead=true;
 let next=fixtures[0].lane.sequence+1n;
 assert.equal(await page.evaluate(async seq=>{try{await window.views[0].update({operation:0,args:[],sequence:BigInt(seq),cameraRevision:BigInt(seq),timeRevision:BigInt(seq),stateRevision:1n,time:{kind:0}});return false;}catch{return true;}},next.toString()),true);
 fixtures[0].control.failRead=false;next=fixtures[0].lane.sequence+1n;
 await page.evaluate(seq=>window.views[0].update({operation:0,args:[],sequence:BigInt(seq),cameraRevision:BigInt(seq),timeRevision:BigInt(seq),stateRevision:1n,time:{kind:0}}),next.toString());


 for(const [firstOp,firstArgs,secondOp,secondArgs,time] of [[4,[1],6,[15],{kind:0}],[0,[],8,[0,0],{kind:1,instant:-9223372036854775808n}]]){
  const seq=fixtures[0].lane.sequence+1n,camera=fixtures[0].adapter.frame.data.identity.camera;
  const expected=decodeGeoViewportResponse(geoViewportExecute(encodeGeoViewportRequest(decodeGeoViewportResponse(geoViewportExecute(encodeGeoViewportRequest(camera,firstOp,firstArgs),1<<20)).camera,secondOp,secondArgs),1<<20)).camera;
  hold=true;await page.evaluate(({op,args,sequence,time})=>{window.serialFirst=window.views[0].update({operation:op,args,sequence,cameraRevision:sequence,timeRevision:sequence,stateRevision:1n,time});},{op:firstOp,args:firstArgs,sequence:seq,time});
  for(let i=0;i<100&&!held;i++)await new Promise(r=>setTimeout(r,10));assert.equal(held,true);
  await page.evaluate(({op,args,sequence,time})=>{window.serialSecond=window.views[0].update({operation:op,args,sequence,cameraRevision:sequence,timeRevision:sequence,stateRevision:1n,time});},{op:secondOp,args:secondArgs,sequence:seq+1n,time});releaseHold();
  await page.evaluate(()=>Promise.all([window.serialFirst,window.serialSecond]));assert.deepEqual(fixtures[0].adapter.frame.data.identity.camera,expected);assert.equal(fixtures[0].adapter.frame.data.identity.time.kind,time.kind);
 }
 const keyboardSequence=fixtures[0].adapter.sequence+1n;await page.locator('#c0').focus();await page.keyboard.press('ArrowRight');await page.waitForFunction(seq=>window.views[0].identity.sequence===BigInt(seq),keyboardSequence.toString());assert.equal(fixtures[0].adapter.sequence,keyboardSequence);
 await page.evaluate(()=>new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r))));
 const pixels=await page.evaluate(()=>window.views.map(v=>{v.view._drawNow();const gl=v.view.gl,canvas=v.view.canvas;let p;if(v.view._glHost)p=v.view._present2d.getImageData(0,0,canvas.width,canvas.height).data;else{p=new Uint8Array(gl.drawingBufferWidth*gl.drawingBufferHeight*4);gl.readPixels(0,0,gl.drawingBufferWidth,gl.drawingBufferHeight,gl.RGBA,gl.UNSIGNED_BYTE,p);}let red=0;for(let i=0;i<p.length;i+=4)if(p[i+1]>150&&p[i]<100&&p[i+2]<100)red++;return red;}));assert.ok(pixels.every(n=>n>0),JSON.stringify({pixels,views:await page.evaluate(()=>window.views.map(v=>({connected:v.view.root.isConnected,visible:v.view._ctxVisible,dimensions:[v.view.canvas.width,v.view.canvas.height],gpu:v.view.gpuTraces.length}))) }));
 await page.evaluate(()=>Promise.all(window.views.map(v=>v.dispose())));assert.ok(fixtures.every(f=>!f.adapter.mounted));assert.deepEqual(errors,[]);
 console.log(JSON.stringify({ok:true,fiveMounts:true,failedHydratePreservesOldPaint:true,latestDesired:true,trustedKeyboardPan:true,selectedGreenPixels:pixels,selectedHierarchyLive:true,privateLaneHistory:true,retireAck:true,lostStageCommitAckRecovery:true,definiteReadFailureRecovery:true,distinctAbsoluteEditsCompose:true,browser:browser.version()}));
}finally{releaseHold?.();await browser.close();await new Promise(resolve=>server.close(resolve));await releaseFive(fixtures);}
