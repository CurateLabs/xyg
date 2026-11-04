// Bounded evidence consumer adapted from examples/vanilla-ts/graphforge-live.mjs.
// No production code changes: actual default live controller + normal shared painter.
import { createServer } from 'node:http';
import { readFile } from 'node:fs/promises';
import { createHash } from 'node:crypto';
import { performance } from 'node:perf_hooks';
import { GraphForgeLayoutController, graphforgeWebviewPayload, encodeGraphForgeRequest,
  composeGraphForge, graphforgeGraphData } from '../../../packages/xy-node/src/graphforge.js';
import { same } from './protocol.mjs';
const root = new URL('../../../', import.meta.url);
const hash = b => createHash('sha256').update(b).digest('hex');
const uuid = i => `00000000-0000-4000-8000-${i.toString(16).padStart(12,'0')}`;
const nodes = Array.from({length:1000}, (_,i)=>uuid(i+1));
const edgeUuid=[], edgeSourceUuid=[], edgeTargetUuid=[];
const sources=new BigUint64Array(2000), targets=new BigUint64Array(2000);
// Exact historical 1k rung: ring + chord, source order preserved by ascending UUIDs.
for(let i=0;i<1000;i++) {
  let chord=(i*7+3)%1000; if(chord===i) chord=(i+2)%1000;
  for(const target of [(i+1)%1000,chord]) {
    const at=edgeUuid.length; edgeUuid.push(uuid(10001+at));
    edgeSourceUuid.push(nodes[i]);edgeTargetUuid.push(nodes[target]);
    sources[at]=BigInt(i); targets[at]=BigInt(target);
  }
}
const input={base:{nodeUuid:nodes,edgeUuid,edgeSourceUuid,edgeTargetUuid,generation:uuid(999999)}};
// Fixture verification is outside all job timing. The measured call still receives raw input.
const data=graphforgeGraphData(composeGraphForge(input));
if(data.nNodes!==1000 || hash(Buffer.from(data.sources.buffer))!==hash(Buffer.from(sources.buffer)) || hash(Buffer.from(data.targets.buffer))!==hash(Buffer.from(targets.buffer))) throw Error('canonical topology differs from historical generator');
const fixtureIdentity={nodes:1000,edges:2000,inputSha256:hash(encodeGraphForgeRequest(input)),
 sourcesSha256:hash(Buffer.from(sources.buffer)),targetsSha256:hash(Buffer.from(targets.buffer))};
const owner=new GraphForgeLayoutController(), snapshots=new Map(), events=[], lags=[];
let started, current, accept, waiting, done=false, failure, ticker, previous;
const event=(type, detail={})=>events.push({type,ms:performance.now()-started,...detail});
const meta=p=>({spec:p.spec,nodeTrace:p.nodeTrace,jobId:p.jobId,revision:p.revision,step:p.step,phase:p.phase});
const respond=(res,v)=>{res.setHeader('Content-Type','application/json');res.end(JSON.stringify(v));};
function wake(){if(!waiting)return;if(current){respond(waiting,meta(current));waiting=null;}else if(done){waiting.writeHead(204).end();waiting=null;}else if(failure){waiting.writeHead(500).end(String(failure));waiting=null;}}
const app=String.raw`
window.proof={mode:'automatic-after-frame',deliberateHolds:0,frames:[],clicks:[],errors:[]};
const element=document.getElementById('chart');let view, displayed;
const frame=()=>new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)));
const now=()=>performance.now()-proof.started;
window.findNode=()=>{
 const g=view.gpuTraces.find(g=>g.trace.id===displayed.nodeTrace),cpu=g._cpu;
 for(let i=0;i<Math.min(cpu.x.length,1000);i++){
  const x=view._dataPx(g.xAxis,view._decodeValue(cpu.x,g.xMeta,i))-view.plot.x;
  const y=view._dataPx(g.yAxis,view._decodeValue(cpu.y,g.yMeta,i))-view.plot.y;
  const hit=view._pickAt(x,y);
  if(hit?.trace===displayed.nodeTrace){const r=view.canvas.getBoundingClientRect();return {x:r.x+x,y:r.y+y,hit:{trace:hit.trace,index:hit.index},jobId:displayed.jobId,revision:displayed.revision,step:displayed.step};}
 }
 throw Error('no real GPU node hit');
};
element.addEventListener('xy:click',async e=>{
 const checkpoint={jobId:displayed.jobId,revision:displayed.revision,step:displayed.step};
 const began=performance.now();
 const response=await fetch('/pick',{method:'POST',body:JSON.stringify({...checkpoint,hit:e.detail})});
 proof.clicks.push({...checkpoint,trusted:e.isTrusted||window.lastPointerTrusted===true,detail:e.detail,identity:await response.json(),responseMs:performance.now()-began,atMs:now()});
});
element.addEventListener('pointerdown',e=>window.lastPointerTrusted=e.isTrusted,true);
window.disposeGraph=()=>{view?.destroy();element.replaceChildren();};
window.beginGraph=async()=>{
 proof.started=performance.now();await fetch('/start',{method:'POST'});
 while(true){
  const response=await fetch('/next');if(response.status===204)break;if(!response.ok)throw Error(await response.text());
  const p=await response.json();const buffer=await(await fetch('/buffer/'+p.step)).arrayBuffer();const receivedMs=now();
  const previousView=view?{...view.view}:null;
  view?.destroy();element.replaceChildren();view=xy.renderStandalone(element,p.spec,buffer);window.graphView=view;displayed=p;
  await frame();
  // Inspect the VISIBLE Canvas2D presentation from the normal shared WebGL host.
  // No forced draw, fallback painter, layout or size policy is installed here.
  if(!view._present2d)throw Error('normal shared Canvas2D presentation unavailable');
  const pixels=view._present2d.getImageData(0,0,view.canvas.width,view.canvas.height).data;
  let colored=0;for(let i=0;i<pixels.length;i+=4)if(pixels[i+2]>pixels[i]+10||pixels[i]>pixels[i+1]+20)colored++;
  const paintedMs=now();const location=findNode();const gpuPickReadyMs=now();
  const f={jobId:p.jobId,revision:p.revision,step:p.step,phase:p.phase,receivedMs,paintedMs,gpuPickReadyMs,
   coloredPixels:colored,frame:[view.canvas.width,view.canvas.height],bufferBytes:buffer.byteLength,gpuHit:location.hit,
   previousView,view:{...view.view},renderer:view.canvas.dataset.xyGlHost};
  if(!proof.initialPng)proof.initialPng=view.canvas.toDataURL();
  if(p.phase==='complete')proof.finalPng=view.canvas.toDataURL();
  f.ackStartedMs=now();proof.frames.push(f);
  await fetch('/accept',{method:'POST',body:JSON.stringify({jobId:p.jobId,revision:p.revision,step:p.step})});
  f.ackCompletedMs=now();
 }
 proof.done=true;
};`;
const server=createServer(async(req,res)=>{
 res.setHeader('Cache-Control','no-store');
 try{
 const url=new URL(req.url,'http://localhost');
 const body=async()=>{let b='';for await(const part of req)b+=part;return JSON.parse(b);};
 if(url.pathname==='/'){res.setHeader('Content-Type','text/html');res.end(`<!doctype html><meta charset="utf-8"><title>1k Node first paint proof</title><style>body{margin:24px}#chart{width:720px;height:480px}</style><div id="chart"></div><script src="/client.js"></script><script src="/app.js"></script>`);}
 else if(url.pathname==='/client.js'){res.setHeader('Content-Type','text/javascript');res.end(await readFile(new URL('packages/xy-client/dist/standalone.js',root)));}
 else if(url.pathname==='/app.js'){res.setHeader('Content-Type','text/javascript');res.end(app);}
 else if(url.pathname==='/start'&&req.method==='POST'){
  if(started!==undefined){res.writeHead(409).end();return;}
  started=performance.now();previous=started;
  ticker=setInterval(()=>{const n=performance.now();lags.push(n-previous-5);previous=n;},5);
  const call=performance.now();
  // Existing rung requests 1+40*10=401 ticks. Chunk size and 30s wall use live defaults.
  const run=graphforgeWebviewPayload(owner,input,{width:720,height:480,layout:'cose',seed:7,iterations:401,legend:false,onPayload:p=>{
   current=p;snapshots.set(p.step,p);
   event('checkpoint',{jobId:p.jobId,revision:p.revision,step:p.step,phase:p.phase,packingMs:p.packingMs,
    positionSha256:hash(Buffer.concat([Buffer.from(p.positions.x.buffer),Buffer.from(p.positions.y.buffer)])),
    bufferSha256:hash(Buffer.from(p.buffer)),bufferBytes:p.buffer.byteLength,sourceNodes:p.positions.uuid.length,
    graph:p.spec.graph});
   const accepted=new Promise(r=>{accept=r;});wake();return accepted;
  }});
  event('call-returned',{synchronousMs:performance.now()-call});
  run.then(()=>{done=true;clearInterval(ticker);event('complete',{memory:process.memoryUsage(),resources:process.getActiveResourcesInfo()});wake();},cause=>{failure=cause;clearInterval(ticker);event('error',{code:cause.code,message:cause.message});wake();});
  respond(res,{started:true});
 }else if(url.pathname==='/next'){if(waiting){res.writeHead(409).end();return;}waiting=res;wake();}
 else if(url.pathname.startsWith('/buffer/')){const p=snapshots.get(Number(url.pathname.split('/').at(-1)));if(!p){res.writeHead(404).end();return;}res.setHeader('Content-Type','application/octet-stream');res.end(Buffer.from(p.buffer));}
 else if(url.pathname==='/accept'&&req.method==='POST'){
  const ack=await body();if(!current||!same(current,ack)){event('rejected-ack',ack);res.writeHead(409).end();return;}
  event('accepted',{...ack});current=undefined;accept();respond(res,{accepted:true});
 }else if(url.pathname==='/pick'&&req.method==='POST'){
  const request=await body(),p=snapshots.get(request.step);
  if(!same(p,request)){res.writeHead(409).end();return;}
  const hit=request.hit;const uuid=hit.trace===p.nodeTrace&&Number.isInteger(hit.index)&&hit.index>=0&&!p.pickData.aggregate?p.pickData.nodes[hit.index]?.uuid:null;
  event('pick',{...request,uuid:uuid??null});respond(res,{uuid:uuid??null});
 }else if(url.pathname==='/snapshot'){
  respond(res,[...snapshots.values()].map(p=>({...meta(p),bufferBytes:p.buffer.byteLength,
    positionsUuid:p.positions.uuid,xBase64:Buffer.from(p.positions.x.buffer).toString('base64'),yBase64:Buffer.from(p.positions.y.buffer).toString('base64')})));
 }else if(url.pathname==='/evidence')respond(res,{fixtureIdentity,events,lags,resourceUsage:process.resourceUsage(),memory:process.memoryUsage(),resources:process.getActiveResourcesInfo(),
  measurementRetention:'All presented payloads and complete source f64 snapshots retained by evidence fixture; memory is instrumented process, not production peak or VRAM.'});
 else if(url.pathname==='/dispose'&&req.method==='POST'){await owner.dispose();event('disposed',{resources:process.getActiveResourcesInfo()});respond(res,{disposed:true});}
 else if(url.pathname==='/cancel-probe'&&req.method==='POST'){
  const probe=new GraphForgeLayoutController();let calls=0;
  const begun=performance.now();let settled;
  const run=probe.render(input,{layout:'cose',seed:7,iterations:401,onPayload:()=>{calls++;probe.cancel();}}).catch(e=>{settled=e.code;});
  await run;const atSettlement=calls;await probe.dispose();
  let terminal;try{await probe.render(input);}catch(e){terminal=e.code;}
  respond(res,{scope:'separate cancellation job; no presentation cadence claim',code:settled,calls,atSettlement,terminal,ms:performance.now()-begun,resources:process.getActiveResourcesInfo()});
 }else{res.writeHead(404).end();}
 }catch(e){res.writeHead(500).end(String(e));}
});
server.listen(0,'127.0.0.1',()=>console.log('XYG_GRAPHFORGE_LIVE_URL=http://127.0.0.1:'+server.address().port));
async function shutdown(){clearInterval(ticker);await owner.dispose();server.closeAllConnections();server.close(()=>process.exit(0));}
for(const signal of ['SIGTERM','SIGINT'])process.once(signal,shutdown);
