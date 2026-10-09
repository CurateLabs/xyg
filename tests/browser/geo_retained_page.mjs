import {createXygWasmWorker, XygGeographicChart, encodeGeoScaleRequest, encodeGeoScaleStyle, encodeGeoChunkRequest, encodeGeoViewportColumnRequest} from '/packages/xy-client/dist/index.js';
import {parseGeoSceneData,parseGeoMembershipData,parseGeoHitData,parseGeoRowsData} from '/tests/browser/geo_source_parser.mjs';

const assert=(ok,message)=>{if(!ok)throw Error(message);};
const red=p=>p[0]>240&&p[1]<20&&p[2]<20&&p[3]>250;
const delay=ms=>new Promise(resolve=>setTimeout(resolve,ms));
const deferred=()=>{let resolve;const promise=new Promise(r=>{resolve=r;});return {promise,resolve};};
const stage=name=>{window.__retainedStage=name;};
const MAX=0xffffffffffffffffn, MIN=-0x8000000000000000n;
const camera={crs:4326,centerX:0,centerY:0,zoom:0,width:800,height:600,bearing:0,pitch:0,worldWrap:true};
const budget={processorBytes:128<<20,maxRowsExamined:1000000n,maxReadBytes:128n<<20n,maxChunks:65536,pageRows:2};
const style=encodeGeoScaleStyle({fill:Uint8Array.of(255,0,0,255),stroke:new Uint8Array(4),strokeWidth:0,diameter:16,opacity:1,symbol:0});
const startupStarted=performance.now();
const worker=createXygWasmWorker({wasm:'/packages/xy-client/dist/xyg-wasm.wasm',workerUrl:'/packages/xy-client/dist/wasm-worker.js',maxArenaBytes:128<<20});
const charts=new Set(),hosts=[],events=[];
let result=null,teardownRelease=null;
let parserNegativeControls=0;const parserFamilies=new Set();
const retainedBuffers=[];
function bufferProof(controller){
  const buffers=new Set(),visited=new WeakSet();
  function visit(value){if(value instanceof ArrayBuffer){buffers.add(value);return;}if(ArrayBuffer.isView(value)){buffers.add(value.buffer);return;}if(!value||typeof value!=='object'||visited.has(value))return;visited.add(value);if(Array.isArray(value)||Object.getPrototypeOf(value)===Object.prototype)for(const child of Object.values(value))visit(child);}
  visit(controller.snapshot().packet);visit(controller.view._payload);visit(controller.view.gpuTraces);
  const data=controller.snapshot(),typedBytes=[...buffers].reduce((n,b)=>n+b.byteLength,0);
  const rowCharge=data.length*1024+8192;
  // Account separately for Rust's retained packet plus both permitted cmd23
  // transfer copies; the counted browser packet is one of those copies.
  const conservativePersistentBytes=3*data.packet.byteLength+typedBytes-data.packet.byteLength;
  assert(conservativePersistentBytes<rowCharge,'persistent packet+painter CPU buffers exceed Data lease');
  retainedBuffers.push({rows:data.length,packetBytes:data.packet.byteLength,painterBytes:controller.view._payload.byteLength,distinctTypedBuffers:buffers.size,typedBytes,conservativePersistentBytes,rowCharge});
}
function ordinaryAdmissionProof(){
  const graph=new ArrayBuffer(32),temporal=new ArrayBuffer(32),scene=new Uint8Array(160),annotations=new Uint8Array(16);
  const slice=Uint8Array.prototype.slice,set=Uint8Array.prototype.set,bufferSlice=ArrayBuffer.prototype.slice;
  let copies=0;
  Uint8Array.prototype.slice=function(...args){copies++;return slice.apply(this,args);};
  Uint8Array.prototype.set=function(...args){copies++;return set.apply(this,args);};
  ArrayBuffer.prototype.slice=function(...args){copies++;return bufferSlice.apply(this,args);};
  try{for(const operation of[
    ()=>worker.temporalGraphCommand(temporal),()=>worker.graphforgeCompose(graph),
    ()=>worker.prepareSceneAnnotations(scene,annotations),
  ]){let error;try{operation();}catch(value){error=value;}assert(error?.code==='XYG_WASM_INVALID_ARGUMENT'&&/separate Worker/.test(error.message),'ordinary host lane failed to reject before admission');}}
  finally{Uint8Array.prototype.slice=slice;Uint8Array.prototype.set=set;ArrayBuffer.prototype.slice=bufferSlice;}
  assert(copies===0&&graph.byteLength===32&&temporal.byteLength===32&&scene.byteLength===160&&annotations.byteLength===16,'ordinary retained-mode rejection copied/detached input');
}
function malformed(packet,parser,mutate,label){
  const changed=packet.slice();mutate(new DataView(changed),new Uint8Array(changed));
  let rejected=false;try{parser(changed);}catch{rejected=true;}
  assert(rejected,`parser accepted malformed ${label}`);parserNegativeControls++;
}
function parserProof(packet){
  if(packet.byteLength<=256||String.fromCharCode(...new Uint8Array(packet,0,4))!=='XYGZ')return;
  const v=new DataView(packet),tag=v.getUint32(8,true),family=tag<2?'scene':tag===2?'membership':tag===3?'hit':tag===4?'rows':null;
  if(!family||parserFamilies.has(family))return;parserFamilies.add(family);
  const parser=family==='scene'?parseGeoSceneData:family==='membership'?parseGeoMembershipData:family==='rows'?parseGeoRowsData:parseGeoHitData;
  parser(packet);
  for(const [label,mutate]of[
    ['magic',(v,b)=>b[0]^=1],['version',v=>v.setUint32(4,99,true)],
    ['reserved tail',(v,b)=>b[255]=1],['oversized count',v=>v.setBigUint64(32,0xffffffffffffffffn,true)],
  ])malformed(packet,parser,mutate,`${family} ${label}`);
  let truncatedRejected=false;try{parser(packet.slice(0,-1));}catch{truncatedRejected=true;}assert(truncatedRejected,`${family} accepted truncation`);parserNegativeControls++;
  if(family==='scene'){
    const at=256+Number(v.getBigUint64(32,true));
    for(const[label,mutate]of[
      ['unknown aggregate',v=>v.setUint32(8,4,true)],['unknown dropped-channel mask',v=>v.setUint32(12,8,true)],
      ['unknown source geometry',v=>v.setUint32(240,99,true)],['unknown source CRS',v=>v.setUint32(244,99,true)],
      ['unknown camera CRS',v=>v.setUint32(80,99,true)],['unknown wrap',v=>v.setUint32(84,2,true)],
      ['nonfinite camera',v=>v.setFloat64(88,NaN,true)],['unknown time',v=>v.setUint32(208,99,true)],
      ['reversed time interval',v=>{v.setUint32(208,2,true);v.setBigInt64(216,1n,true);v.setBigInt64(224,0n,true);}],
      ['Scene version',v=>v.setUint32(260,99,true)],['metadata reserved',v=>v.setUint32(at+28,1,true)],
      ['source ordinal',v=>v.setBigUint64(at+8,v.getBigUint64(232,true),true)],
      ['chunk index',v=>v.setUint32(at+16,65536,true)],['chunk row',v=>v.setUint32(at+20,65536,true)],
      ['vertex framing',v=>v.setUint32(at+24,0xffffffff,true)],
    ])malformed(packet,parser,mutate,`scene ${label}`);
  }else if(family==='membership'){
    const at=256+v.getUint32(76,true);
    for(const[label,mutate]of[
      ['owner mismatch',v=>v.setBigUint64(80,v.getBigUint64(16,true)+1n,true)],
      ['cursor flag',v=>v.setUint32(72,2,true)],['cursor length',v=>v.setUint32(76,207,true)],
      ['key geometry',v=>v.setUint32(116,99,true)],['cell index',v=>v.setUint32(12,0xffffffff,true)],
      ['record reserved',(v,b)=>b[at+24]=1],['record source ordinal',v=>v.setBigUint64(at+8,v.getBigUint64(104,true),true)],
      ['cursor key',(v,b)=>b[256]^=1],['cursor reserved',(v,b)=>b[420]=1],
    ])malformed(packet,parser,mutate,`membership ${label}`);
  }else if(family==='rows'){
    for(const[label,mutate]of[
      ['owner mismatch',v=>v.setBigUint64(80,v.getBigUint64(16,true)+1n,true)],
      ['next flag',v=>v.setUint32(40,2,true)],['key geometry',v=>v.setUint32(112,99,true)],
      ['key CRS',v=>v.setUint32(116,0,true)],['time kind',v=>v.setUint32(152,99,true)],
      ['record flags',v=>v.setUint32(280,128,true)],['record reserved',(v,b)=>b[284]=1],
      ['ordinal',v=>v.setBigUint64(264,v.getBigUint64(104,true),true)],
      ['eligibility',v=>v.setUint32(280,v.getUint32(280,true)^4,true)],
      ['chunk index',v=>v.setUint32(272,65536,true)],
      ['chunk row',v=>v.setUint32(276,65536,true)],
    ])malformed(packet,parser,mutate,`rows ${label}`);
  }else{
    for(const[label,mutate]of[
      ['owner mismatch',v=>v.setBigUint64(80,v.getBigUint64(16,true)+1n,true)],
      ['hit mode',v=>v.setUint32(40,2,true)],['max hits',v=>v.setUint32(44,0,true)],
      ['nonfinite query',v=>v.setFloat64(48,NaN,true)],['negative tolerance',v=>v.setFloat64(64,-1,true)],
      ['record kind',v=>v.setUint32(256,99,true)],['record reserved',(v,b)=>b[292]=1],
      ['record source ordinal',v=>v.setBigUint64(272,v.getBigUint64(104,true),true)],
    ])malformed(packet,parser,mutate,`hit ${label}`);
  }
}
const getContext=HTMLCanvasElement.prototype.getContext,contexts=new Set();
HTMLCanvasElement.prototype.getContext=function(type,...args){const context=getContext.call(this,type,...args);if(type==='webgl2'&&context)contexts.add(context);return context;};
const actualExecute=worker.geoScaleExecute.bind(worker);
const actualRead=worker.geoScaleRead.bind(worker);
worker.geoScaleRead=async request=>{const packet=await actualRead(request);parserProof(packet);return packet;};
worker.geoScaleExecute=request=>{
  const view=new DataView(request),command=view.getUint32(8,true),handle=view.getBigUint64(16,true),sequence=view.getBigUint64(24,true);
  const ticketSequence=command===8?view.getBigUint64(272,true):null;
  events.push({kind:'posted',command,handle,sequence,ticketSequence});
  return actualExecute(request).then(reply=>{events.push({kind:'settled',command,handle,sequence,ticketSequence});return reply;},error=>{events.push({kind:'failed',command,handle,sequence,ticketSequence,code:error.code});throw error;});
};
const execute=input=>worker.geoScaleExecute(encodeGeoScaleRequest(input));
const mutation=async input=>new DataView(await execute(input));
const read=input=>worker.geoScaleRead(encodeGeoScaleRequest(input));
const rawGeo=(type,request)=>worker.queueOwnedGeo(async()=>{
  const requestId=worker.allocateRequest(),sequence=worker.nextSequence++,result=worker.promiseFor(requestId);
  worker.worker.postMessage({type,requestId,sequence,request},[request]);return await result;
},request.byteLength);
function snapshotRequest(command,handle,sequence=0n){const request=new ArrayBuffer(256),b=new Uint8Array(request),v=new DataView(request);b.set([88,89,71,74]);v.setUint32(4,1,true);v.setUint32(8,command,true);v.setBigUint64(16,handle,true);v.setBigUint64(24,sequence,true);if(command===1)v.setBigUint64(32,32n<<20n,true);if(command===2){v.setBigUint64(32,32n<<20n,true);v.setUint32(40,1,true);v.setUint32(44,85,true);v.setFloat64(48,1,true);}return request;}
const host=()=>{const el=document.createElement('div');document.body.append(el);hosts.push(el);return el;};
function query(info,revision=1n,extra={}){
  return {camera:{...camera},reducedKind:0,maxCells:32768,previousDirect:true,sourceDigest:info.digest.slice(),generation:MAX,layerId:MAX,cameraRevision:revision,timeRevision:revision,layerRevision:revision,styleRevision:revision,stateRevision:revision,time:{kind:1,instant:MIN},maxProjectedVertices:1000000n,...extra};
}
// The fixture frames source planes through the existing public adapter and real
// Rust pure20 authoring; it never hashes, projects, selects a cell or computes LOD.
async function source(rows,coincident=false,companion=false){
  const ids=BigUint64Array.from({length:rows},(_,i)=>i===0?MAX:0x20000000000000n+BigInt(i));
  const xy=Float64Array.from({length:rows*2},(_,i)=>i%2?0:coincident||i===0?0:179);
  const column={geometry:1,crs:4326,xy,validity:new Uint8Array(rows).fill(1),featureIds:ids};
  if(companion){column.validity[2]=0;column.xy=Float64Array.from([...xy.slice(0,4),...xy.slice(6)]);ids[2]=MAX;ids[3]=MAX;}
  const descriptor=encodeGeoViewportColumnRequest(camera,column).slice(128);
  const starts=new BigInt64Array(rows).fill(MIN),ends=new BigInt64Array(rows).fill(MIN+1n),validity=new Uint8Array(rows).fill(1);
  if(companion){starts[1]=MIN+1n;ends[1]=MIN+2n;}
  const chunk=new Uint8Array(await worker.geoScaleRead(encodeGeoChunkRequest({descriptor,rows,intervals:{starts,ends,startValidity:validity,endValidity:validity}},budget.processorBytes)));
  const builder=(await mutation({command:1})).getBigUint64(16,true);
  let manifest;
  try{await execute({command:2,handle:builder,payload:chunk});await execute({command:3,handle:builder,generation:MAX});manifest=new Uint8Array(await read({command:21,handle:builder}));}
  finally{await execute({command:10,handle:builder});}
  const validation=(await mutation({command:4,budget,payload:manifest})).getBigUint64(16,true);
  let info;
  try{for(;;){const reply=await execute({command:6,handle:validation,sequence:0n,budget}),v=new DataView(reply),code=v.getUint32(8,true);
    if(code===3){info={digest:new Uint8Array(reply,40,8).slice()};break;}
    assert(code===1,'source authentication did not issue exact read');
    const ticket=new Uint8Array(reply,64,96).slice();let payload=new Uint8Array(96+chunk.length);payload.set(ticket);payload.set(chunk,96);
    await execute({command:7,handle:validation,payload});payload=null;
    await execute({command:8,handle:validation,payload:ticket});
  }}finally{await execute({command:10,handle:validation});}
  return {chunk,manifest,info,ids,xy};
}
async function chart(options){const value=await XygGeographicChart.fromSource(options);charts.add(value);return value;}
async function remove(value){await value.dispose();charts.delete(value);}
async function pixels(canvas){await new Promise(requestAnimationFrame);await new Promise(requestAnimationFrame);const x=Math.floor(canvas.width/2),y=Math.floor(canvas.height/2),present=canvas.getContext('2d');if(present)return present.getImageData(x,y,1,1).data;const gl=[...contexts].find(context=>context.canvas===canvas);assert(gl,'no chart presentation context');const rgba=new Uint8Array(4);gl.readPixels(x,canvas.height-y-1,1,1,gl.RGBA,gl.UNSIGNED_BYTE,rgba);return rgba;}
async function reject(promise,message){let error;try{await promise;}catch(value){error=value;}assert(error,message);return error;}
try{
  stage('ready');const metadata=await worker.ready,startupMs=performance.now()-startupStarted;assert(metadata.abiVersion>=33,'old packaged WASM ABI');
  stage('ordinary host admission isolation');
  const transportAdmission=worker.acquireGeoTransport();ordinaryAdmissionProof();await transportAdmission;ordinaryAdmissionProof();
  stage('concurrent ownership');
  const builders=await Promise.all([mutation({command:1}),mutation({command:1})]);
  const builderIds=builders.map(v=>v.getBigUint64(16,true));assert(builderIds[0]!==builderIds[1],'builder identity collision');
  await Promise.all(builderIds.map(handle=>execute({command:10,handle})));
  stage('queue admission before ownership');
  const queued=Array.from({length:17},()=>encodeGeoScaleRequest({command:1}));
  const admitted=await Promise.allSettled(queued.map(request=>worker.geoScaleExecute(request)));
  // The Rust builder registry has its own smaller resource limit. Every first
  // sixteen call must pass HOST admission even if Rust rejects another builder.
  assert(admitted.slice(0,16).every(r=>r.status==='fulfilled'||r.reason.code!=='XYG_WASM_BUDGET_EXCEEDED'),'bounded FIFO rejected its admitted working set');
  assert(admitted[16].status==='rejected'&&admitted[16].reason.code==='XYG_WASM_BUDGET_EXCEEDED'&&queued[16].byteLength===256,'full FIFO consumed caller ownership');
  await Promise.all(admitted.slice(0,16).filter(r=>r.status==='fulfilled').map(r=>execute({command:10,handle:new DataView(r.value).getBigUint64(16,true)})));
  stage('retained phase isolation');
  for(const operation of[
    ()=>worker.temporalGraphCommand(new ArrayBuffer(32)),
    ()=>worker.graphforgeCompose(new ArrayBuffer(32)).result,
  ]){const error=await reject(Promise.resolve().then(operation),'ordinary lane escaped retained phase');assert(error.code==='XYG_WASM_INVALID_ARGUMENT'&&/separate Worker/.test(error.message),'ordinary lane reached its processor before retained-mode rejection');}
  stage('source author/auth');const direct=await source(101);
  stage('constructor input admission');
  const beforeInputCredit=worker.ownedGeoBytes,releaseCredit=worker.reserveGeoInput((32<<20)-32768-beforeInputCredit);
  const deniedHosts=Array.from({length:5},host);
  try{
    const denied=await Promise.allSettled(deniedHosts.map(el=>XygGeographicChart.fromSource({el,worker,manifest:direct.manifest,budget,query:query(direct.info),style,readChunk:async()=>direct.chunk.slice()})));
    assert(denied.every(r=>r.status==='rejected'&&r.reason.code==='XYG_WASM_BUDGET_EXCEEDED'),'concurrent constructors copied without shared host credit');
    assert(deniedHosts.every(el=>!el.children.length),'rejected constructor created DOM');
    // Settlement must use the bounded cleanup reserve even when normal
    // retained input admission is full. Malformed authority reaches Rust and
    // rejects there; it must not be stranded by host queue admission.
    for(const [command,length,mixed] of [[8,384,false],[31,384,false],[4,256,true]]){
      const raw=new ArrayBuffer(length),header=new DataView(raw);new Uint8Array(raw).set(mixed?[88,89,77,88]:[88,89,71,81]);header.setUint32(4,1,true);header.setUint32(8,command,true);
      const error=await reject(mixed?worker.geoTileExecute(raw):worker.geoScaleExecute(raw),'invalid cleanup authority accepted');
      assert(error.code!=='XYG_WASM_BUDGET_EXCEEDED'&&raw.byteLength===0,'cleanup reserve did not admit exact extended ACK/cancel framing');
    }
    const ordinary=new ArrayBuffer(128);new Uint8Array(ordinary).set([88,89,71,84]);new DataView(ordinary).setUint32(8,4,true);
    const ordinaryError=await reject(worker.geoTileExecute(ordinary),'ordinary tile supply escaped admission');
    assert(ordinaryError.code==='XYG_WASM_BUDGET_EXCEEDED'&&ordinary.byteLength===128,'tile supply was incorrectly granted cleanup reserve');

  }finally{releaseCredit();}
  assert(worker.ownedGeoBytes===beforeInputCredit,'constructor reservation leak');
  const malformedHost=host(),malformedQuery={...query(direct.info),sourceDigest:null};
  await reject(XygGeographicChart.fromSource({el:malformedHost,worker,manifest:direct.manifest,budget,query:malformedQuery,style,readChunk:async()=>direct.chunk.slice()}),'malformed constructor query accepted');
  assert(worker.ownedGeoBytes===beforeInputCredit&&!malformedHost.children.length,'constructor throw leaked host credit/DOM');
  let readerMode='ok',pauseSequence=null,entered=null,gate=null,callbackSignal=null;
  const reader=async(ticket,signal)=>{
    // Deliberate caller mutation must not corrupt the driver's private ACK.
    ticket.raw.fill(0);
    if(ticket.sequence===pauseSequence){callbackSignal=signal;entered.resolve();await gate.promise;pauseSequence=null;}
    return readerMode==='bad'?direct.chunk.slice(0,-1):direct.chunk.slice();
  };
  const el=host(),main=await chart({el,worker,manifest:direct.manifest,budget,query:query(direct.info),style,readChunk:reader});
  stage('direct paint');await main.ready;
  assert(main.snapshot().identity.time.instant===MIN&&main.snapshot().identity.generation===MAX,'exact i64/u64 identity');
  assert(main.snapshot().record(0).featureId===MAX&&main.snapshot().record(1).featureId===0x20000000000001n,'literal u64 provenance');
  const list=()=>el.querySelector('[role=list]');
  assert(list().children.length===50,'companion firstpage bound');
  el.lastElementChild.click();assert(list().children.length===50,'companion secondpage bound');
  el.lastElementChild.click();assert(list().children.length===1,'companion thirdpage');
  const canvas=el.querySelector('canvas[role=img]'),gl=[...contexts][0];assert(gl&&canvas,'retained painter did not create real WebGL2/presentation');
  const initialPixel=await pixels(canvas);assert(red(initialPixel),`origin not visibly painted: ${Array.from(initialPixel)}, canvas ${canvas.width}x${canvas.height}`);
  assert((await main.pick(400,300))[0]?.featureId===MAX,'Rust full-ID pick');
  bufferProof(main);
  stage('original source rows and keyboard focus');
  const companionSource=await source(4,false,true);let failRows=false,focused=null;
  const rowsHost=host(),rowChart=await chart({el:rowsHost,worker,manifest:companionSource.manifest,budget,
    query:query(companionSource.info,1n,{camera:{...camera,zoom:2}}),style,
    readChunk:async()=>failRows?companionSource.chunk.slice(0,-1):companionSource.chunk.slice(),
    onSourceRowFocus(row){focused=row;}});
  await rowChart.ready;assert(rowChart.snapshot().length===1,'companion fixture did not exclude offscreen/null/time rows from paint');
  const firstRows=await rowChart.sourceRows();
  assert(firstRows.length===2&&firstRows[0].featureId===MAX&&firstRows[0].sourceRow===0n&&firstRows[0].eligible&&firstRows[1].sourceRow===1n&&!firstRows[1].timeEligible,'original rows lost first-page identity/eligibility');
  const finalRows=await rowChart.sourceRows(true),sourceList=rowsHost.querySelector('[aria-label="Original geographic source rows"]');
  assert(finalRows.length===2&&finalRows[0].geometryNull&&finalRows[0].sourceRow===2n&&finalRows[1].sourceRow===3n&&finalRows[1].featureId===MAX&&finalRows[1].eligible,'null/offscreen/duplicate original rows not paged');
  assert(sourceList.children.length===2,'source companion DOM was not page bounded');
  sourceList.lastElementChild.focus();assert(document.activeElement===sourceList.lastElementChild&&focused?.sourceRow===3n&&focused.featureId===MAX,'keyboard focus did not expose exact offscreen row');
  failRows=true;await reject(rowChart.sourceRows(),'failed source row read published');
  assert(sourceList.children.length===2&&sourceList.lastElementChild.textContent.includes('source row 3')&&(await rowChart.pick(400,300))[0]?.featureId===MAX,'failed page changed accepted companion or paint');
  failRows=false;assert((await rowChart.sourceRows())[0].sourceRow===0n,'source paging did not recover');
  stage('indexed sidecar browser publication and recovery');
  const canonicalScene=rowChart.snapshot().scene.slice(),sidecar=new Map();let badLeaf=false;
  const built=await rowChart.buildIndex({grid:16,maxVertices:4n,
    async writePage(ticket,bytes){assert(sidecar.size<16,'fixture sidecar exceeded explicit storage bound');sidecar.set(ticket.page,bytes.slice());ticket.raw.fill(0);ticket.encodedBytes=1;},
    async readPage(ticket){const page=sidecar.get(ticket.page);assert(page,'unknown sidecar page');ticket.raw.fill(0);ticket.encodedBytes=1;return badLeaf?page.slice(0,-1):page.slice();}});
  assert(built.pages>0n&&sidecar.size===Number(built.pages),'real Rust index did not publish bounded sidecar');
  await rowChart.update(query(companionSource.info,1n,{camera:{...camera,zoom:2}}));
  assert(rowChart.spatialDecision==='indexed'&&rowChart.spatialStats?.pagesRead>0n,'browser did not execute indexed query');
  assert(rowChart.snapshot().scene.length===canonicalScene.length&&rowChart.snapshot().scene.every((n,i)=>n===canonicalScene[i]),'indexed Scene differs from canonical Rust Scene');
  assert((await rowChart.pick(400,300))[0]?.featureId===MAX&&(await rowChart.sourceRows())[0].sourceRow===0n,'indexed frame lost pick/original row authority');
  const acceptedHandle=rowChart.frame.handle;badLeaf=true;
  await reject(rowChart.update(query(companionSource.info,2n,{camera:{...camera,zoom:2}})),'corrupt indexed leaf published');
  assert(rowChart.frame.handle===acceptedHandle&&(await rowChart.pick(400,300))[0]?.featureId===MAX&&red(await pixels(rowsHost.querySelector('canvas[role=img]'))),'failed indexed read changed accepted paint');
  badLeaf=false;await rowChart.update(query(companionSource.info,3n,{camera:{...camera,zoom:2}}));
  assert(rowChart.spatialDecision==='indexed'&&(await rowChart.pick(400,300))[0]?.featureId===MAX,'indexed browser failed recovery');
  stage('indexed unsettled write cancellation');
  events.length=0;const indexEntered=deferred(),indexGate=deferred();teardownRelease=indexGate.resolve;
  const abandoned=rowChart.buildIndex({grid:16,maxVertices:4n,async writePage(ticket,bytes,signal){assert(bytes.length===ticket.encodedBytes,'write authority mismatch');indexEntered.resolve(signal);await indexGate.promise;},async readPage(){throw Error('abandoned index must not publish');}});
  const abandonedRejection=reject(abandoned,'cancelled index build published');const writeSignal=await indexEntered.promise;
  const resumed=rowChart.update(query(companionSource.info,4n,{camera:{...camera,zoom:2}}));await delay(30);
  assert(writeSignal.aborted&&!events.some(e=>e.command===24),'write ACK preceded storage settlement');
  indexGate.resolve();assert((await abandonedRejection).name==='AbortError','cancelled index returned wrong result');await resumed;
  assert(events.some(e=>e.kind==='settled'&&e.command===24)&&rowChart.spatialDecision==='indexed'&&(await rowChart.pick(400,300))[0]?.featureId===MAX,'cancelled build failed ACK or replaced accepted index');
  teardownRelease=null;
  await remove(rowChart);
  stage('frozen source snapshot');
  const frozenReply=new DataView(await rawGeo('geo.snapshot.execute',snapshotRequest(1,main.frame.handle,1n))),frozenHandle=frozenReply.getBigUint64(16,true);
  let frozen=null,secondFrozen=null,frozenView=null;
  try{
    frozen=await rawGeo('geo.snapshot.read',snapshotRequest(20,frozenHandle));frozenView=new DataView(frozen);
    assert(String.fromCharCode(...new Uint8Array(frozen,0,4))==='XYGX'&&frozenView.getUint32(4,true)===2&&frozenView.getUint32(8,true)===32,'snapshot did not freeze actual Scene32');
    assert(frozenView.getUint32(52,true)===1&&frozenView.getBigInt64(56,true)===MIN&&frozenView.getBigUint64(192,true)===MAX&&frozenView.getBigUint64(208,true)===MAX&&frozenView.getBigUint64(288,true)===MAX,'frozen camera/time/layer/source/direct identity');
    const unavailable=await reject(rawGeo('geo.snapshot.execute',snapshotRequest(2,frozenHandle)),'WASM unexpectedly exposed raster artifact export');
    assert(unavailable.code==='XYG_GEO_SNAPSHOT_UNSUPPORTED_EXPORT','WASM raster feature gate gave wrong unsupported error');
    secondFrozen=await rawGeo('geo.snapshot.read',snapshotRequest(20,frozenHandle));
    {const first=new Uint8Array(frozen),second=new Uint8Array(secondFrozen);assert(secondFrozen.byteLength===frozen.byteLength&&second.every((n,i)=>n===first[i]),'unsupported export mutated frozen snapshot');}
    await reject(rawGeo('geo.snapshot.read',snapshotRequest(20,frozenHandle)),'frozen transfer read quota escaped');
  }finally{frozenView=null;frozen=null;secondFrozen=null;await rawGeo('geo.snapshot.execute',snapshotRequest(3,frozenHandle));}
  stage('cancel unsettled source read');events.length=0;pauseSequence=2n;entered=deferred();gate=deferred();teardownRelease=gate.resolve;
  const stale=main.update(query(direct.info,2n));const staleRejection=reject(stale,'superseded query succeeded');
  await entered.promise;
  const latest=main.update(query(direct.info,3n));
  await delay(30);assert(callbackSignal.aborted,'superseded read did not receive AbortSignal');
  assert(events.some(e=>e.kind==='settled'&&e.command===9&&e.sequence===2n),'Rust explicitcancel did not settle');
  assert(!events.some(e=>e.kind==='posted'&&e.command===8&&e.ticketSequence===2n),'ACK preceded unsettled read drop');
  gate.resolve();assert((await staleRejection).name==='AbortError','wrong cancellation result');await latest;
  assert(events.some(e=>e.kind==='settled'&&e.command===8&&e.ticketSequence===2n),'retired read not acknowledged');
  assert(main.snapshot().identity.sequence===3n,'stale frame committed');
  stage('failure preserves immutable frame');readerMode='bad';await reject(main.update(query(direct.info,4n)),'bad read succeeded');
  assert(main.snapshot().identity.sequence===3n,'failed query replaced frame');
  assert((await main.pick(400,300))[0]?.featureId===MAX,'old immutable frame pick failed');
  readerMode='ok';await main.update(query(direct.info,5n));
  stage('context restore');const activePresentation=el.querySelector('canvas[role=img]'),activeGl=[...contexts][0],activeCanvas=activeGl.canvas,extension=activeGl.getExtension('WEBGL_lose_context');assert(extension,'no contextloss extension');
  const before=main.snapshot().identity.sequence,lost=new Promise(resolve=>activeCanvas.addEventListener('webglcontextlost',resolve,{once:true}));
  extension.loseContext();await lost;await delay(100);
  const restored=new Promise(resolve=>activeCanvas.addEventListener('webglcontextrestored',resolve,{once:true}));extension.restoreContext();await restored;await delay(100);
  assert(main.snapshot().identity.sequence===before&&(await main.pick(400,300))[0]?.featureId===MAX,'contextrestore changed frame/pick');
  assert(red(await pixels(activePresentation)),'contextrestore lost paint');
  stage('five shared Worker views');let commits=0;
  const five=await Promise.all(Array.from({length:5},async()=>{const el=host(),value=await chart({el,worker,manifest:direct.manifest,budget,query:query(direct.info),style,readChunk:async()=>direct.chunk.slice(),onChange(){commits++;}});return {el,value};}));
  await Promise.all(five.map(async({value})=>{await value.ready;assert(value.snapshot().record(0).featureId===MAX,'sharedWorker lost literal ID');assert(value.snapshot().length===101,'sharedWorker provenance length');}));
  assert(commits===5&&five.every(({value})=>value.snapshot().identity.sequence===1n),'shared views were superseded');
  for(const{el,value}of five){const canvas=el.querySelector('canvas[role=img]');assert(canvas,'shared view has no actualpaint');canvas.scrollIntoView({block:'center'});await delay(100);assert(red(await pixels(canvas)),'shared view lost its own paintedframe');assert(el.querySelector('[role=list]').children.length===50,'sharedview unboundedDOM');bufferProof(value);}
  assert(contexts.size===1,'fiveviews created extra GL contexts');
  await Promise.all(five.map(({value})=>remove(value)));
  stage('aggregate membership');const reduced=await source(32769,true),aggregate=await chart({el:host(),worker,manifest:reduced.manifest,budget,query:query(reduced.info,1n,{maxCells:1,previousDirect:false}),style,readChunk:async()=>reduced.chunk.slice(),layer:{setPrepared(){},releasePrepared(){}}});
  await aggregate.ready;assert(aggregate.snapshot().aggregate&&aggregate.snapshot().record(0).count===32769n,'Rust cell count/LOD');
  assert((await aggregate.pick(400,300))[0]?.kind==='cell','aggregate fabricated direct ID');
  const page=await aggregate.membership(0);assert(page.records.length===2&&page.records[0].featureId===MAX&&page.cursor?.length===208,'first membership page/cursor');
  const next=await aggregate.membership(0,page.cursor);assert(next.records.length===2&&next.records[0].sourceRow===2n,'opaque cursor replay');
  const badCursor=page.cursor.slice();badCursor[0]^=1;await reject(aggregate.membership(0,badCursor),'stale cursor accepted');
  assert((await aggregate.pick(400,300))[0]?.count===32769n,'cursor failure invalidated painted frame');await remove(aggregate);
  stage('failed initialization cleanup');const brokenHost=host(),broken=await chart({el:brokenHost,worker,manifest:direct.manifest,budget,query:query(direct.info),style,readChunk:async()=>{throw Error('reader failure');}});
  await reject(broken.ready,'initial reader failure accepted');assert(!brokenHost.children.length,'failed initialization left DOM');await remove(broken);
  stage('dispose unsettled source read');pauseSequence=6n;entered=deferred();gate=deferred();teardownRelease=gate.resolve;
  const updating=main.update(query(direct.info,6n)),updatingRejection=reject(updating,'disposed update succeeded');await entered.promise;
  const disposal=main.dispose();await delay(30);assert(callbackSignal.aborted&&!events.some(e=>e.command===8&&e.ticketSequence===6n),'dispose ACK preceded read completion');
  gate.resolve();await updatingRejection;await disposal;charts.delete(main);assert(!el.children.length,'dispose left DOM');
  assert(worker.pending.size===0,'retained requests leaked');
  assert(direct.xy[0]===0&&direct.xy[2]===179&&direct.ids[0]===MAX&&new DataView(direct.manifest.buffer).getBigUint64(16,true)===MAX,'authoring source mutated');
  stage('owned queue shutdown');
  const a=encodeGeoScaleRequest({command:1}),b=encodeGeoScaleRequest({command:1});
  const pa=worker.geoScaleExecute(a),pb=worker.geoScaleExecute(b);
  const settled=Promise.allSettled([pa,pb]);
  // Permit ownership admission, but stop before a queued mutation dispatches.
  await Promise.resolve();
  const stopping=worker.dispose(),stoppingAgain=worker.dispose();
  const stopped=await settled;await Promise.all([stopping,stoppingAgain]);
  assert(stopped.every(r=>r.status==='rejected'&&r.reason.code==='XYG_WASM_DISPOSED'),'shutdown executed or stranded queued mutation');
  assert(worker.pending.size===0,'shutdown retained pending transport');
  assert(parserFamilies.size===4,'parser proof missing actual packet family');
  result={ok:true,abiVersion:metadata.abiVersion,concurrentOwnership:true,sharedViews:5,directPages:3,fullU64:true,fullI64:true,cancelledReadAck:true,oldFramePreserved:true,contextRestored:true,memberCursor:true,originalRows:true,indexedSidecar:true,indexedRecovery:true,indexedWriteCancelAck:true,offscreenKeyboardFocus:true,failedInitializationCleaned:true,pending:worker.pending.size,parserNegativeControls,frozenSnapshot:true,wasmRasterExport:'unsupported',startupMs,retainedBuffers,environment:{userAgent:navigator.userAgent,hardwareConcurrency:navigator.hardwareConcurrency,devicePixelRatio:window.devicePixelRatio}};
}catch(error){result={ok:false,stage:window.__retainedStage,code:error.code,message:error.message,stack:error.stack};}
finally{teardownRelease?.();await Promise.allSettled([...charts].map(c=>c.dispose()));await worker.dispose();hosts.forEach(el=>el.remove());HTMLCanvasElement.prototype.getContext=getContext;window.__retained=result;}
