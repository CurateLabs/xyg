// Actual native callback transport and five ordinary density views.
// Count/texture/identity qualification only; no timing/FPS claim.
import assert from 'node:assert/strict';
import {createServer} from 'node:http';
import {readFile,writeFile,mkdir} from 'node:fs/promises';
import {resolve} from 'node:path';
import {createHash,randomBytes} from 'node:crypto';
import {chromium} from 'playwright';
import {createNativeFilterSession,ChunkedColumns,scatterChart} from '../packages/xy-node/src/index.js';
const root=process.cwd(), directory=resolve(process.argv[2]??'target/task-tmp/filter-100m-fixture/small');
const out=resolve(process.argv[3]??'target/task-tmp/filter-native-bridge/browser-small');
await mkdir(out,{recursive:true});
const manifest=JSON.parse(await readFile(`${directory}/manifest.json`,'utf8'));
const names=manifest.dimensions,n=manifest.rows,first=BigInt(manifest.firstRow),domain=2**Math.ceil(Math.log2(n+1));
const lo=Math.floor(n/4),hi=Math.floor(n/2)-1;
const limits=names.map((_,i)=>i===0?domain:65536),multipliers=manifest.files.map(r=>r.multiplier),periods=manifest.files.map(r=>r.period);
// Independent scalar fixture/count oracle, no product classifier or sampling.
const total=names.map(()=>new Float64Array(10000)),selected=names.map(()=>new Float64Array(10000));
const values=new Float64Array(5),scales=limits.map(v=>100/v);
for(let row=0;row<n;row++){
 values[0]=row;
 for(let k=0;k<4;k++)values[k+1]=((row%periods[k])*multipliers[k])%periods[k];
 const yes=row>=lo&&row<=hi;
 for(let k=0;k<5;k++){
  const next=(k+1)%5,cell=Math.floor(values[next]*scales[next])*100+Math.floor(values[k]*scales[k]);
  total[k][cell]++;if(yes)selected[k][cell]++;
 }
}
const oracle=Buffer.alloc(5*10000*16);
for(let k=0;k<5;k++)for(let i=0;i<10000;i++){
 oracle.writeBigUInt64LE(BigInt(total[k][i]),k*160000+i*8);
 oracle.writeBigUInt64LE(BigInt(selected[k][i]),k*160000+80000+i*8);
}
await writeFile(`${out}/oracle.bin`,oracle);
let owner,server,browser;
try {
const sources=[];
try{for(const r of manifest.files)sources.push(new ChunkedColumns(resolve(r.path)));owner=await createNativeFilterSession({time:sources[0].column('x'),...Object.fromEntries(names.slice(1).map((name,i)=>[name,sources[i].column('y')]))},{sourceId:112n,epoch:7n,firstRow:first,budgetBytes:128n<<20n});}
finally{for(const source of sources)source.close();}
const registration=owner.takeRegistration(),assets=new Map();
for(let i=0;i<5;i++){
 const figure=scatterChart(new Float64Array(),new Float64Array(),{density:false,width:400,height:260,title:`${names[i]} × ${names[(i+1)%5]}`});
 figure.setAxis('x',{domain:[0,limits[i]]});figure.setAxis('y',{domain:[0,limits[(i+1)%5]]});
 const p=figure.buildPayload();assets.set(`/view-${i}.json`,{type:'application/json',bytes:JSON.stringify(p.spec)});assets.set(`/view-${i}.bin`,{type:'application/octet-stream',bytes:p.buffers});figure.dispose();
}
assets.set('/client.js',{type:'text/javascript',bytes:await readFile(process.env.XYG_FILTER_CLIENT ?? `${root}/packages/xy-client/dist/index.js`)});
assets.set('/oracle',{type:'application/octet-stream',bytes:oracle});
const token=randomBytes(16).toString('hex');let requests=0,pending=0,maximumPending=0;
server=createServer(async(req,res)=>{
 try{
  const url=new URL(req.url,'http://localhost'),path=url.pathname;
  res.setHeader('Content-Security-Policy',"default-src 'none'; script-src 'self' 'wasm-unsafe-eval'; connect-src 'self'; style-src 'unsafe-inline'");
  if(path==='/'){res.setHeader('Content-Type','text/html');res.end('<!doctype html><title>Native linked source</title><body style="margin:0;background:white"></body>');return;}
  if(assets.has(path)){const a=assets.get(path);res.setHeader('Content-Type',a.type);res.end(a.bytes);return;}
  if(url.searchParams.get('token')!==token){res.writeHead(403).end();return;}
  if(path==='/source'){
   res.setHeader('Content-Type','application/octet-stream');res.setHeader('X-Filter-Names',JSON.stringify(registration.names));res.setHeader('X-Filter-Budget',registration.budgetBytes.toString());res.end(registration.packet);return;
  }
  if(path==='/close'){await owner.close();res.writeHead(204).end();return;}
  if(path!=='/command'||req.method!=='POST'){res.writeHead(404).end();return;}
  if(pending>=2){res.writeHead(429).end();return;}
  pending++;maximumPending=Math.max(maximumPending,pending);
  try{
   const chunks=[];let bytes=0;
   for await(const chunk of req){bytes+=chunk.length;if(bytes>256*1024*1024)throw Error('transport extent');chunks.push(chunk);}
   const input=new Uint8Array(Buffer.concat(chunks));requests++;
   const reply=await owner.executeTransport(input);
   res.setHeader('Content-Type','application/octet-stream');res.end(reply);
  }finally{pending--;}
 }catch(error){if(!res.headersSent)res.writeHead(409);res.end(String(error.message));}
});
await new Promise(r=>server.listen(0,'127.0.0.1',r));
browser=await chromium.launch({executablePath:process.env.XYG_CHROMIUM,headless:true,args:['--use-gl=angle','--use-angle=swiftshader','--enable-unsafe-swiftshader']});
const errors=[];let report;
{
 const page=await browser.newPage({viewport:{width:1000,height:1000}});page.on('pageerror',e=>errors.push(e.message));
 await page.goto(`http://127.0.0.1:${server.address().port}/`);
 report=await page.evaluate(async({token,n,names,limits,lo,hi,first})=>{
  const xy=await import('/client.js'),url=path=>`${path}?token=${token}`;
  const registration=await fetch(url('/source'));
  const traces=[];
  const session=xy.createFilterSession(async packet=>{
   const response=await fetch(url('/command'),{method:'POST',headers:{'Content-Type':'application/octet-stream'},body:packet});
   if(!response.ok)throw Error(`native HTTP ${response.status}: ${await response.text()}`);
   const bytes=new Uint8Array(await response.arrayBuffer()),reply=xy.decodeFilterReply(bytes);
   if(reply.peakBytes>(128n<<20n))throw Error('Rust session budget exceeded');
   traces.push({op:new DataView(packet.buffer,packet.byteOffset).getUint32(8,true),rowsRead:reply.rowsRead.toString(),tier:reply.tier.toString(),sourceRows:reply.sourceRows.toString(),indexBytes:reply.indexBytes.toString(),residentBytes:reply.residentBytes.toString(),peakBytes:reply.peakBytes.toString(),fallback:reply.fallback.toString(),status:reply.status});
   return bytes;
  },async()=>{const r=await fetch(url('/close'),{method:'POST'});if(!r.ok)throw Error('close failed');},
  {names:JSON.parse(registration.headers.get('X-Filter-Names')),budgetBytes:BigInt(registration.headers.get('X-Filter-Budget')),packet:new Uint8Array(await registration.arrayBuffer())});
  const container=document.createElement('main');container.style.cssText='display:grid;grid-template-columns:repeat(2,400px);gap:12px;background:white';document.body.append(container);
  const bindings=[];let dashboard;
  const check=(v,message)=>{if(!v)throw Error(message);};
  try{
   for(let i=0;i<5;i++){
    const el=document.createElement('section');container.append(el);
    const spec=await(await fetch(`/view-${i}.json`)).json(),buffer=await(await fetch(`/view-${i}.bin`)).arrayBuffer();
    const view=xy.renderStandalone(el,spec,buffer);check(view.gpuTraces.length===1,`empty carrier trace ${i}`);
    bindings.push({view,id:BigInt(i+1),sourceId:112n,epoch:7n,dimension:names[i],cuts:i===0?[Math.floor(n/4),Math.floor(n/2),Math.floor(n*3/4)]:[16384,32768,49152],step:1,grid:{x:names[i],y:names[(i+1)%5],width:100,height:100,xRange:[0,limits[i]],yRange:[0,limits[(i+1)%5]]}});
   }
   const oracle=new DataView(await(await fetch('/oracle')).arrayBuffer());let countChecks=0,textureChecks=0;
   dashboard=await xy.attachFilterDashboard(session,bindings);
   const verify=filtered=>{
    check(dashboard.latest.sourceRows===BigInt(n),'genuine canonical source rows');
    check(dashboard.latest.selectedCount===BigInt(filtered?hi-lo+1:n),'selected canonical total');
    const hashes=[];
    for(let k=0;k<5;k++){
     const v=bindings[k].view,g=v.gpuTraces[0],plane=dashboard.latest.density.find(p=>p.id===BigInt(k+1));
     check(g.tier==='density'&&g.trace.n_points===n&&g.trace.n_marks===10000,'canonical density trace');
     for(let i=0;i<10000;i++){
      const total=oracle.getBigUint64(k*160000+i*8,true),selected=filtered?oracle.getBigUint64(k*160000+80000+i*8,true):total;
      check(plane.totals[i]===total&&plane.selected[i]===selected&&g.filterCounts.total[i]===total&&g.filterCounts.selected[i]===selected,`independent plane ${k}:${i}`);countChecks++;
     }
     v._cancelDrawFrame();v._drawNow();const gl=v.gl,saved=gl.getParameter(gl.FRAMEBUFFER_BINDING),fbo=gl.createFramebuffer();
     try{
      gl.bindFramebuffer(gl.FRAMEBUFFER,fbo);gl.framebufferTexture2D(gl.FRAMEBUFFER,gl.COLOR_ATTACHMENT0,gl.TEXTURE_2D,g.density.tex,0);
      check(gl.checkFramebufferStatus(gl.FRAMEBUFFER)===gl.FRAMEBUFFER_COMPLETE,'complete density texture');
      const p=new Uint8Array(40000);gl.readPixels(0,0,100,100,gl.RGBA,gl.UNSIGNED_BYTE,p);check(gl.getError()===gl.NO_ERROR,'density texture read');
      let hash=2166136261;
      for(let i=0;i<10000;i++)for(let c=0;c<4;c++){
       const alpha=plane.grid[i]>0?plane.rgba[i*4+3]:0,expected=c===3?alpha:Math.round(plane.rgba[i*4+c]*alpha/255);
       check(p[i*4+c]===expected,`native texture ${k}:${i}:${c}`);textureChecks++;hash=Math.imul(hash^p[i*4+c],16777619);
      }
      hashes.push(hash>>>0);
     }finally{gl.bindFramebuffer(gl.FRAMEBUFFER,saved);gl.deleteFramebuffer(fbo);}
    }
    return hashes;
   };
   const before=verify(false);await dashboard.range(1n,lo,hi);const after=verify(true);
   check(before.every((hash,i)=>hash!==after[i]),'all five derived textures changed');
   check(traces.filter(t=>t.op===10).length===1,'unchanged activation repeated a full source build');
   check(traces.filter(t=>t.op===5||t.op===11).every(t=>t.rowsRead==='0'),'indexed range/paint scanned canonical rows');
   const start=BigInt(first)+BigInt(lo)-10n,membership=await session.membership(start,40n);
   for(let i=0;i<40;i++)check(Boolean(membership.membership[i>>3]&(1<<(i&7)))===(i>=10),'canonical membership oracle');
   const result={rows:n,renderedViews:5,distinctDimensions:5,countChecks,textureChecks,membershipBits:40,before,after,sourceArraysInBrowser:0,traces,performanceQualification:false};
   window.nativeCase={bindings,dashboard,session};return result;
  }catch(error){dashboard?.destroy();for(const b of bindings)b.view.destroy();await session.close();throw error;}
 },{token,n,names,limits,lo,hi,first:first.toString()});
 await page.screenshot({path:`${out}/linked.png`});
 await page.evaluate(async()=>{const s=window.nativeCase;s.dashboard.destroy();for(const b of s.bindings)b.view.destroy();const p=s.session.close();if(s.session.close()!==p)throw Error('close ACK identity');await p;});
 assert.equal(owner.closed,true);assert.equal(pending,0);assert.deepEqual(errors,[]);
 report={...report,requests,maximumPending,pageErrors:errors,sourceManifestSha256:createHash('sha256').update(await readFile(`${directory}/manifest.json`)).digest('hex')};
 await writeFile(`${out}/report.json`,JSON.stringify(report,null,2)+'\n');console.log(JSON.stringify(report));
}
}finally{await browser?.close();await owner?.close();if(server?.listening)await new Promise(r=>server.close(r));}
