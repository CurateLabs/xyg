// CodSpeed fixture: setup is outside measurement; no product fallback or timers.
import assert from 'node:assert/strict';
import {createServer} from 'node:http';
import {readFile, writeFile, mkdir} from 'node:fs/promises';
import {resolve} from 'node:path';
import {createInterface} from 'node:readline';
import {createHash,randomBytes} from 'node:crypto';
import {chromium} from 'playwright';
import {createNativeFilterSession,ChunkedColumns,scatterChart} from '../packages/xy-node/src/index.js';

const root=process.cwd(),directory=resolve(process.argv[2]),out=resolve(process.argv[3]);
await mkdir(out,{recursive:true});
const manifest=JSON.parse(await readFile(`${directory}/manifest.json`,'utf8'));
const names=manifest.dimensions,n=manifest.rows,first=BigInt(manifest.firstRow);
assert.deepEqual(names,['time','b','c','d','e']);assert.equal(manifest.files.length,4);
assert(Number.isSafeInteger(n)&&n>1024);
const budgetMiB=Number(process.env.XYG_FILTER_BUDGET_MIB??256);
assert([64,128,256].includes(budgetMiB));
const activeCells=process.env.XYG_FILTER_ACTIVE_CELLS??'pixel';
assert(activeCells==='pixel'||Number.isInteger(Number(activeCells))&&Number(activeCells)>=4&&Number(activeCells)<=512);
const domain=2**Math.ceil(Math.log2(n+1)),limits=names.map((_,i)=>i===0?domain:65536);
let owner,server,browser,page,rl;
let cleanupResult;
const cleanup=()=>cleanupResult??=(async()=>{
 rl?.close();await browser?.close();await owner?.close();
 if(server?.listening)await new Promise(r=>server.close(r));
})();
process.once('SIGTERM',()=>{void cleanup().finally(()=>process.exit(1));});
const errors=[],traces=[],wire=[],artifacts={};
for(const path of ['target/release/libxyg_core.so','packages/xy-client/dist/index.js']){
 const b=await readFile(path);artifacts[path]={sha256:createHash('sha256').update(b).digest('hex'),bytes:b.length};
}
const send=value=>process.stdout.write(JSON.stringify(value)+'\n');
try{
 const sources=[];
 try{
  for(const r of manifest.files)sources.push(new ChunkedColumns(resolve(r.path)));
  owner=await createNativeFilterSession({time:sources[0].column('x'),...Object.fromEntries(names.slice(1).map((name,i)=>[name,sources[i].column('y')]))},{sourceId:112n,epoch:7n,firstRow:first,budgetBytes:BigInt(budgetMiB)<<20n});
 }finally{for(const s of sources)s.close();}
 const registration=owner.takeRegistration(),assets=new Map();
 for(let i=0;i<5;i++){
  const figure=scatterChart(new Float64Array(),new Float64Array(),{density:false,width:400,height:260,title:`${names[i]} x ${names[(i+1)%5]}`});
  try{
   figure.setAxis('x',{domain:[0,limits[i]]});figure.setAxis('y',{domain:[0,limits[(i+1)%5]]});
   const p=figure.buildPayload();assets.set(`/view-${i}.json`,{type:'application/json',bytes:JSON.stringify(p.spec)});assets.set(`/view-${i}.bin`,{type:'application/octet-stream',bytes:p.buffers});
  }finally{figure.dispose();}
 }
 assets.set('/client.js',{type:'text/javascript',bytes:await readFile('packages/xy-client/dist/index.js')});
 const token=randomBytes(16).toString('hex');let pending=0;
 server=createServer(async(req,res)=>{
  try{
   const u=new URL(req.url,'http://localhost'),path=u.pathname;
   res.setHeader('Content-Security-Policy',"default-src 'none'; script-src 'self' 'wasm-unsafe-eval'; connect-src 'self'; style-src 'unsafe-inline'");
   if(path==='/'){res.setHeader('Content-Type','text/html');res.end('<!doctype html><title>Native indexed updates</title><body style="margin:0"></body>');return;}
   if(assets.has(path)){const a=assets.get(path);res.setHeader('Content-Type',a.type);res.end(a.bytes);return;}
   if(u.searchParams.get('token')!==token){res.writeHead(403).end();return;}
   if(path==='/source'){res.setHeader('X-Filter-Names',JSON.stringify(registration.names));res.setHeader('X-Filter-Budget',registration.budgetBytes.toString());res.end(registration.packet);return;}
   if(path==='/close'){await owner.close();res.writeHead(204).end();return;}
   if(path!=='/command'||req.method!=='POST'){res.writeHead(404).end();return;}
   if(pending>=2){res.writeHead(429).end();return;}
   pending++;
   try{
    let size=0;const parts=[];
    for await(const p of req){size+=p.length;if(size>256*1024*1024)throw Error('transport extent');parts.push(p);}
    const b=new Uint8Array(Buffer.concat(parts)),reply=await owner.executeTransport(b);
    traces.push(new DataView(b.buffer,b.byteOffset,b.byteLength).getUint32(8,true));
    wire.push({op:traces.at(-1),requestBytes:b.byteLength,replyBytes:reply.byteLength});
    res.setHeader('Content-Type','application/octet-stream');res.end(reply);
   }finally{pending--;}
  }catch(e){if(!res.headersSent)res.writeHead(409);res.end(String(e.message));}
 });
 await new Promise(r=>server.listen(0,'127.0.0.1',r));
 browser=await chromium.launch({executablePath:process.env.XYG_CHROMIUM,headless:true,args:['--use-gl=angle','--use-angle=swiftshader','--enable-unsafe-swiftshader']});
 page=await browser.newPage({viewport:{width:1000,height:1000}});page.on('pageerror',e=>errors.push(e.message));
 await page.goto(`http://127.0.0.1:${server.address().port}/`);
 const setup=await page.evaluate(async({token,n,names,limits,budgetMiB,activeCells})=>{
  const xy=await import('/client.js'),url=p=>`${p}?token=${token}`;
  const registration=await fetch(url('/source'));let commands=0,builds=0;
  const session=xy.createFilterSession(async packet=>{
   const response=await fetch(url('/command'),{method:'POST',headers:{'Content-Type':'application/octet-stream'},body:packet});
   if(!response.ok)throw Error(await response.text());commands++;
   const op=new DataView(packet.buffer,packet.byteOffset,packet.byteLength).getUint32(8,true);if(op===10)builds++;
   return new Uint8Array(await response.arrayBuffer());
  },async()=>{const response=await fetch(url('/close'),{method:'POST'});if(!response.ok)throw Error('close ACK');},
  {names:JSON.parse(registration.headers.get('X-Filter-Names')),packet:new Uint8Array(await registration.arrayBuffer()),budgetBytes:BigInt(registration.headers.get('X-Filter-Budget'))});
  const root=document.createElement('main');root.style.cssText='display:grid;grid-template-columns:repeat(2,400px);gap:12px';document.body.append(root);
  const bindings=[];
  try{
   for(let i=0;i<5;i++){
    const el=document.createElement('section');root.append(el);
    const spec=await(await fetch(`/view-${i}.json`)).json(),raw=await(await fetch(`/view-${i}.bin`)).arrayBuffer();
    const view=xy.renderStandalone(el,spec,raw);
    bindings.push({view,id:BigInt(i+1),sourceId:112n,epoch:7n,dimension:names[i],cuts:[],step:1,grid:{x:names[i],y:names[(i+1)%5],width:100,height:100,xRange:[0,limits[i]],yRange:[0,limits[(i+1)%5]]}});
   }
   const cells=activeCells==='pixel'?Math.ceil(bindings[0].view.plot.w):Number(activeCells);
   const domain=activeCells==='pixel'?limits[0]:n;
   const cuts=Array.from({length:cells-1},(_,i)=>Math.floor(domain*(i+1)/cells));
   bindings[0].cuts=cuts;
   for(let i=1;i<5;i++)bindings[i].cuts=[16384,32768,49152];
   const ranges=[[0,cuts[0]-1],[cuts[0],cuts[1]-1]];
   const dashboard=await xy.attachFilterDashboard(session,bindings);
   const draw=()=>{
    for(const {view} of bindings){view._cancelDrawFrame();view._drawNow();}
    for(const {view} of bindings){view.gl.finish();if(view.gl.getError()!==view.gl.NO_ERROR)throw Error('draw error');}
   };
   draw();let cursor=0;
   const summary=r=>{
    if(r.sourceRows!==BigInt(n)||r.rowsRead!==0n||r.tier!==3n||builds!==1)throw Error('indexed update invariant');
    return {selected:r.selectedCount.toString(),rowsRead:r.rowsRead.toString(),tier:r.tier.toString(),builds,commands};
   };
   window.nativePerf={bindings,dashboard,session,draw,ranges,
    async query(){
     const [lo,hi]=ranges[cursor++%ranges.length];
     const r=await session.range(lo,hi,{exact:true});
     if(r.selectedCount!==BigInt(Math.max(0,Math.min(n,hi+1)-Math.min(n,lo))))throw Error('query count');
     return summary(r);
    },
    async density(){const r=await session.paint({exact:true});if(r.density.length!==5)throw Error('density planes');return summary(r);},
    async cached(){draw();return summary(dashboard.latest);},
    async update(){
     const [lo,hi]=ranges[cursor++%ranges.length];
     await dashboard.range(1n,lo,hi);draw();const r=dashboard.latest;
     const expected=BigInt(Math.max(0,Math.min(n,hi+1)-Math.min(n,lo)));
     if(r.selectedCount!==expected||r.sourceRows!==BigInt(n)||r.rowsRead!==0n||r.tier!==3n||r.density.length!==5||builds!==1)throw Error('indexed update invariant');
     return summary(r);
    }};
   return {rows:n,cells,plot:bindings[0].view.plot,passiveGrid:[100,100],views:5,budgetMiB,indexBytes:dashboard.latest.indexBytes.toString(),residentBytes:dashboard.latest.residentBytes.toString(),peakBytes:dashboard.latest.peakBytes.toString(),builds,commands,ranges};
  }catch(e){for(const {view} of bindings)view.destroy();await session.close();return {setupFailure:String(e?.stack??e)};}
 },{token,n,names,limits,budgetMiB,activeCells});
 assert(setup && !setup.setupFailure,JSON.stringify({setup,errors,traces}));
 await writeFile(`${out}/setup.json`,JSON.stringify({setup,artifacts,manifestPath:`${directory}/manifest.json`,manifestSha256:createHash('sha256').update(await readFile(`${directory}/manifest.json`)).digest('hex'),browser:browser.version(),node:process.version,renderer:'explicit ANGLE SwiftShader',scope:'programmatic request through five synchronized paints; no pointer/RAF/FPS acceptance'},null,2)+'\n');
 send({ready:true,setup});
 rl=createInterface({input:process.stdin,crlfDelay:Infinity});
 for await(const line of rl){
  const command=JSON.parse(line);
  if(['update','query','density','cached'].includes(command.op)){send(await page.evaluate(op=>window.nativePerf[op](),command.op));continue;}
  if(command.op==='close'){
   await page.evaluate(async()=>{const s=window.nativePerf;s.dashboard.destroy();for(const {view} of s.bindings)view.destroy();await s.session.close();});
   assert(owner.closed);assert.equal(pending,0);assert.deepEqual(errors,[]);
   await writeFile(`${out}/completion.json`,JSON.stringify({closed:true,errors,traces,wire},null,2)+'\n');send({closed:true});break;
  }
  throw Error('unknown private benchmark command');
 }
}catch(error){send({error:String(error.stack??error)});process.exitCode=1;}
finally{await cleanup();}
