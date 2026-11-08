// Manual Linux/Chromium 4.5-billion-row functional journey, excluded from CI.
// Usage: node scripts/chunked_massive_navigation.mjs SOURCE.xygc OUTPUT_DIRECTORY
import assert from 'node:assert/strict';
import {mkdirSync,readFileSync,writeFileSync,statSync} from 'node:fs';
import {resolve} from 'node:path';
import {createHash} from 'node:crypto';
import {spawnSync} from 'node:child_process';
import {chromium} from 'playwright';
import {createChunkedNativeApp,frame} from '../examples/vanilla-ts/chunked-native-host.mjs';
import {scatterChart} from '../packages/xy-node/src/charts.js';
const source=resolve(process.argv[2]),output=resolve(process.argv[3]);mkdirSync(output,{recursive:true});
const stat=statSync(source),physical=Number(/MemTotal:\s+(\d+)/.exec(readFileSync('/proc/meminfo','utf8'))[1])*1024;
assert.ok(stat.size>physical && stat.blocks*512>=72000000000,'materialized source exceeds physical RAM');
const y=i=>(17*i)%65521;
const clicks=[],selections=[],started=performance.now();
const app=await createChunkedNativeApp({path:source,assets:resolve('packages/xy-client/dist'),staticDirectory:output,chartOptions:{budgetBytes:4<<20,pageBytes:2<<20},callbacks:{onHover:()=>{},onClick:r=>clicks.push(r),onSelect:s=>selections.push([...s.sourceRowIds].map(String))}});
let browser;const errors=[],external=[],requests=[],snapshots=[],wire=[],accepted=[];
for(const [index,host] of app.hosts.entries()){
 const message=host.message.bind(host);host.message=control=>{if(control.type==='view_change')wire.push({chart:index,type:control.type,ranges:control.ranges,intent:control.chunked_intent,phase:control.phase});const result=message(control);if(control.type==='chunked_painted'&&control.frame===host.frame)accepted.push({chart:index,frame:host.frame,provenance:host.chart.sourceProvenance});return result;};
}
const stringify=x=>JSON.stringify(x,(_,v)=>typeof v==='bigint'?v.toString():v,2)+'\n';
try{
 browser=await chromium.launch({executablePath:process.env.XYG_CHROMIUM,args:['--no-sandbox','--use-gl=angle','--use-angle=swiftshader','--enable-unsafe-swiftshader']});
 const page=await browser.newPage({viewport:{width:1200,height:1000}});
 page.on('pageerror',e=>errors.push(e.message));
 await page.route('**/*',route=>{if(route.request().url().startsWith(app.origin))return route.continue();external.push(route.request().url());return route.abort();});
 await page.addInitScript(()=>{
  globalThis.massiveFrames=[];globalThis.massiveErrors=[];globalThis.committed=[];document.addEventListener('xy:view_change',e=>{if(e.target.closest('#chart')&&e.detail.phase==='end')committed.push(e.detail);});globalThis.trusted=[];globalThis.allocations=new Map();
  document.addEventListener('xy:chunked_frame',e=>massiveFrames.push(e.detail));
  document.addEventListener('xy:chunked_error',e=>massiveErrors.push(e.detail));
  for(const kind of ['wheel','pointerdown','pointerup'])document.addEventListener(kind,e=>trusted.push({type:e.type,trusted:e.isTrusted}),true);
  const proto=WebGL2RenderingContext.prototype;
  for(const name of ['bufferData','texImage2D','texStorage2D','deleteBuffer','deleteTexture']){
   const old=proto[name];proto[name]=function(...a){const result=old.apply(this,a);
    if(name==='bufferData'){const binding=a[0]===this.ELEMENT_ARRAY_BUFFER?this.ELEMENT_ARRAY_BUFFER_BINDING:this.ARRAY_BUFFER_BINDING;allocations.set(this.getParameter(binding),this.getBufferParameter(a[0],this.BUFFER_SIZE));}
    else if(name.startsWith('tex'))allocations.set(this.getParameter(this.TEXTURE_BINDING_2D),a[3]*a[4]*(a[2]===this.R8?1:4));
    else allocations.delete(a[0]);return result;};
  }
 });
 await page.exposeFunction('nativeCurrent',ranges=>{const host=app.hosts[0],last=wire.filter(q=>q.chart===0).at(-1);return last?.phase==='end'&&JSON.stringify(last.ranges)===JSON.stringify(ranges)&&host.frame===String(host.generation)&&!host.pending&&!host.staged&&!host.ready;});
 const settled=async previous=>{await page.waitForFunction(n=>committed.length>n,previous);const ranges=await page.evaluate(()=>committed.at(-1).ranges);await page.waitForFunction(async r=>await globalThis.nativeCurrent(r),ranges);await app.hosts[0].whenPainted();};
 await page.goto(app.origin);const canvas=page.locator('#chart canvas[data-xy-slot=canvas]');await canvas.waitFor();
 await page.evaluate(()=>new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r))));
 const initial=await canvas.evaluate(c=>{const p=c.getContext('2d').getImageData(0,0,c.width,c.height).data;let ink=0;for(let i=3;i<p.length;i+=4)if(p[i])ink++;return{width:c.width,height:c.height,ink,ranges:c.closest('.xy').xy.state().ranges};});
 assert.ok(initial.ink>100,'meaningful overview paint');
 assert.equal(app.hosts[0].initial.sourceProvenance.detailRowsRead,0n);
 assert.equal(app.hosts[1].initial.sourceProvenance.detailRowsRead,0n);
 await canvas.screenshot({path:resolve(output,'overview.png')});
 const home=app.hosts[0].payload().spec;
 const initialPeer=String(app.hosts[1].frame),initialPeerIds=[...app.hosts[1].chart.sourceRowIds].map(String);
 const overviewElapsed=performance.now()-started;
 const band=page.locator('#chart [data-xy-axis-band="x"]');const box=await band.boundingBox();assert.ok(box);
 let count=await page.evaluate(()=>committed.length);
 await page.mouse.move(box.x+box.width*.95,box.y+box.height/2);await page.mouse.wheel(0,-9000);
 await settled(count);
 const capture=async name=>{
  const ranges=await canvas.evaluate(c=>c.closest('.xy').xy.state().ranges);
  const lo=Math.max(0,Math.ceil(ranges.x[0])),hi=Math.min(4499999999,Math.floor(ranges.x[1]));assert.ok(hi-lo<262144,'bounded accepted viewport');
  const expected=[];for(let i=lo;i<=hi;i++)if(y(i)>=ranges.y[0]&&y(i)<=ranges.y[1])expected.push(i);
  const host=app.hosts[0];assert.deepEqual([...host.chart.sourceRowIds].map(Number),expected,'independent closed-form membership');assert.deepEqual([...host.chart.traces[0].x],expected);assert.deepEqual([...host.chart.traces[0].y],expected.map(y));
  const nativeHeader=Buffer.alloc(16);nativeHeader.write('XYBO');nativeHeader.writeUInt32LE(1,4);nativeHeader.writeBigUInt64LE(BigInt(expected.length),8);const nativeData=Buffer.concat([nativeHeader,...[host.chart.sourceRowIds,host.chart.traces[0].x,host.chart.traces[0].y].map(a=>Buffer.from(a.buffer,a.byteOffset,a.byteLength))]);writeFileSync(resolve(output,name+'.native'),nativeData);
  assert.ok(expected.length>100,'meaningful refined viewport');assert.ok(expected.some(id=>id>4294967295),'actual canonical IDs exceed u32');
  const oracle=scatterChart(expected,expected.map(y),{density:false});oracle.setAxis('x',{domain:home.x_axis.range,margin:0});oracle.setAxis('y',{domain:home.y_axis.range,margin:0});
  const packet=oracle.buildPayload({split:true});writeFileSync(resolve(output,'oracle.xybf'),frame({spec:packet.spec},packet.buffers));
  await page.evaluate(async ranges=>{const {render,decodeFrame}=await import('/assets/index.js');globalThis.oracleCleanup?.();const p=decodeFrame(await(await fetch('/oracle.xybf')).arrayBuffer());globalThis.oracleCleanup=render({el:document.querySelector('#oracle'),model:{get:k=>k==='spec'?p.message.spec:p.buffers,on(){},off(){},send(){}}});document.querySelector('#oracle .xy').xy.applyState({ranges},{animate:false,history:false});},ranges);
  await page.mouse.move(1,1);await page.evaluate(()=>new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r))));
  const a=await canvas.evaluate(c=>c.toDataURL('image/png').split(',')[1]),b=await page.locator('#oracle canvas[data-xy-slot=canvas]').evaluate(c=>c.toDataURL('image/png').split(',')[1]);
  writeFileSync(resolve(output,name+'.png'),Buffer.from(a,'base64'));writeFileSync(resolve(output,name+'-oracle.png'),Buffer.from(b,'base64'));
  const compare=spawnSync(process.env.XYG_PYTHON??'.venv/bin/python',['-c','from PIL import Image;import sys;a,b=[Image.open(p).convert("RGBA") for p in sys.argv[1:]];assert a.size==b.size and a.tobytes()==b.tobytes()',resolve(output,name+'.png'),resolve(output,name+'-oracle.png')],{encoding:'utf8'});assert.equal(compare.status,0,compare.stderr);
  snapshots.push({name,observedAtEpochMs:Date.now(),nativeData:{file:name+'.native',sha256:createHash('sha256').update(nativeData).digest('hex'),bytes:nativeData.length},ranges,ids:expected.map(String),provenance:host.chart.sourceProvenance,memory:host.memoryReport(),hostMemoryUsage:process.memoryUsage(),gpu:await page.evaluate(()=>({logicalDriverStorage:[...allocations.values()].reduce((s,n)=>s+n,0),objects:allocations.size,pageHeap:performance.memory?.usedJSHeapSize??null})),exactPixels:true});
  requests.push({x:ranges.x,y:ranges.y});writeFileSync(resolve(output,'partial-report.json'),stringify({initial,overviewElapsedDiagnosticMs:overviewElapsed,snapshots,requests,wire}));oracle.dispose();
 };
 await capture('zoom');
 const firstChunk=app.hosts[0].chart.sourceProvenance.firstChunk;
 let drags=0;
 while(app.hosts[0].chart.sourceProvenance.firstChunk<firstChunk+2n && drags<40){
  count=await page.evaluate(()=>committed.length);const r=await band.boundingBox();await page.mouse.move(r.x+r.width*.8,r.y+r.height/2);await page.mouse.down();await page.mouse.move(r.x+r.width*.2,r.y+r.height/2,{steps:4});await page.mouse.up();
  await settled(count);drags++;
 }
 assert.ok(app.hosts[0].chart.sourceProvenance.firstChunk>=firstChunk+2n,'trusted pans reach a genuinely new chunk');writeFileSync(resolve(output,'pan-controls.json'),stringify({accepted,wire,current:app.hosts[0].chart.sourceProvenance,drags}));/* Source I/O, including superseded reads, is checked independently from strace. */
 await capture('pan');
 for(let i=0;i<drags;i++){
  count=await page.evaluate(()=>committed.length);const r=await band.boundingBox();await page.mouse.move(r.x+r.width*.2,r.y+r.height/2);await page.mouse.down();await page.mouse.move(r.x+r.width*.8,r.y+r.height/2,{steps:4});await page.mouse.up();await settled(count);
 }
 await capture('revisit');assert.ok(app.hosts[0].chart.sourceProvenance.bytesRead<=1048576n,'return fetches at most the evicted chunk');
 count=await page.evaluate(()=>committed.length);const warm=await band.boundingBox();await page.mouse.move(warm.x+warm.width*.5,warm.y+warm.height/2);await page.mouse.down();await page.mouse.move(warm.x+warm.width*.52,warm.y+warm.height/2,{steps:2});await page.mouse.up();await settled(count);await capture('warm');assert.equal(app.hosts[0].chart.sourceProvenance.bytesRead,0n,'resident working-set pan performs zero file reads');
 assert.equal(String(app.hosts[1].frame),initialPeer);assert.deepEqual([...app.hosts[1].chart.sourceRowIds].map(String),initialPeerIds,'independent peer remains overview');
 assert.deepEqual(errors,[]);assert.deepEqual(external,[]);const trustedEvents=await page.evaluate(()=>trusted);assert.ok(trustedEvents.length>3&&trustedEvents.every(e=>e.trusted));
 await page.evaluate(()=>{globalThis.oracleCleanup?.();document.querySelector('#chart').replaceChildren();});
 const report={source:{path:source,bytes:stat.size,allocatedBytes:stat.blocks*512,physicalRamBytes:physical,rows:'4500000000',generation:JSON.parse(readFileSync(source+'.generation.json','utf8'))},initial,overviewElapsedIncludingNodeAndBrowserStartupDiagnosticMs:overviewElapsed,snapshots,requests,wire,accepted,drags,trustedEvents,errors,external,hostMemoryUsage:process.memoryUsage(),performanceQualification:false,remaining:['full-source scan comparison pending','global CPU/WASM/GPU budget and browser process accounting','coarse overview tiles/ordinary gradual zoom and all-host/competitor qualification']};
 writeFileSync(resolve(output,'requests.json'),stringify(requests));writeFileSync(resolve(output,'report.json'),stringify(report));console.log(stringify({ok:true,sourceBytes:stat.size,physicalRam:physical,rows:'4500000000',drags,snapshots:snapshots.map(s=>({name:s.name,rows:s.ids.length,provenance:s.provenance})),overviewElapsedDiagnosticMs:overviewElapsed}));
}finally{await browser?.close();await app.close();}
