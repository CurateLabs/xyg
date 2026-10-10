import {createXygWasmWorker,createGeoSelectedScope,claimGeoSelectedState,encodeGeoScaleRequest as encode,decodeGeoScaleReply as decode,encodeGeoChunkRequest,encodeGeoScaleStyle,driveGeoSession,driveGeoHierarchy,beginGeoSelectedHierarchy,encodeGeoHierarchyRequest as hierarchy,decodeGeoHierarchyReply as hierarchyReply,forgetSelectedGeoAllocationIssuer,prepareGeoSceneData,beginGeoWorkerMutationCapture} from '/hierarchy-admission-proof.js';
import {hydrateWasmPainter} from '/packages/xy-client/dist/index.js';
const budget={processorBytes:128<<20,maxRowsExamined:1000000n,maxReadBytes:128n<<20n,maxChunks:65536,pageRows:4096},MAX=0xffffffffffffffffn;
const check=(value,message)=>{if(!value)throw Error(message);},reject=async(p,message)=>{let failed=false;try{await p;}catch{failed=true;}check(failed,message);};
const nextFrame=()=>new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r))),workers=[],contexts=[],requests=[],scopes=[];
const nativePost=Worker.prototype.postMessage;
Worker.prototype.postMessage=function(message,transfer){if(['geo.scale.execute','geo.scale.read'].includes(message.type)){const v=new DataView(message.request);requests.push({worker:this,id:message.requestId,command:v.getUint32(8,true),handle:v.getBigUint64(16,true),sequence:v.getBigUint64(24,true),request:message.request.slice(0)});}return nativePost.call(this,message,transfer);};
function worker(){const w=createXygWasmWorker({workerUrl:'/packages/xy-client/dist/wasm-worker.js',wasm:'/packages/xy-client/dist/xyg-wasm.wasm',maxArenaBytes:budget.processorBytes});workers.push(w);return w;}
async function fixture(w){
 await w.ready;const bridge=w.geoScaleBridge(),descriptor=new Uint8Array(120),v=new DataView(descriptor.buffer);descriptor.set([88,89,71,68]);[1,1,4326,1,0].forEach((n,i)=>v.setUint32(4+4*i,n,true));v.setBigUint64(24,2n,true);v.setBigUint64(32,2n,true);[0,0,90,1].forEach((n,i)=>v.setFloat64(64+8*i,n,true));descriptor.set([1,1],96);v.setBigUint64(104,MAX,true);v.setBigUint64(112,9007199254740993n,true);
 const chunk=await bridge.read(encodeGeoChunkRequest({descriptor,rows:2,intervals:{starts:BigInt64Array.of(-(1n<<63n),-(1n<<63n)),ends:BigInt64Array.of((1n<<63n)-1n,(1n<<63n)-1n),startValidity:Uint8Array.of(1,1),endValidity:Uint8Array.of(1,1)}},budget.processorBytes));
 const builder=decode(await bridge.execute(encode({command:1}))).handle;let source,seed,index;
 try{await bridge.execute(encode({command:2,handle:builder,payload:new Uint8Array(chunk)}));await bridge.execute(encode({command:3,handle:builder,generation:MAX}));const manifest=await bridge.read(encode({command:21,handle:builder}));source=decode(await bridge.execute(encode({command:4,payload:new Uint8Array(manifest),budget}))).handle;
  const readChunk=async()=>chunk.slice(0),info=(await driveGeoSession(bridge,{handle:source,sequence:0n,budget,readChunk})).source;
  const query={camera:{crs:4326,worldWrap:true,centerX:0,centerY:0,zoom:0,width:800,height:600,bearing:0,pitch:0},reducedKind:0,maxCells:32768,previousDirect:true,sourceDigest:info.digest.slice(),generation:MAX,layerId:MAX,cameraRevision:1n,timeRevision:1n,layerRevision:1n,styleRevision:1n,stateRevision:1n,time:{kind:1,instant:-(1n<<63n)},maxProjectedVertices:1000000n};
  await bridge.execute(encode({command:5,handle:source,sequence:1n,query,budget}));await driveGeoSession(bridge,{handle:source,sequence:1n,budget,readChunk});const style=encodeGeoScaleStyle({fill:Uint8Array.of(255,0,0,255),stroke:new Uint8Array(4),strokeWidth:0,diameter:6,opacity:1,symbol:0});seed=await prepareGeoSceneData(bridge,{handle:source,sequence:1n,budget,style});
  const firstScope=await createGeoSelectedScope(bridge,{frameHandle:seed.handle,sequence:1n,namespace:MAX,layerId:MAX,budget});scopes.push(firstScope);
  const first=await firstScope.state({revision:2n,ids:BigUint64Array.of(MAX),fill:Uint8Array.of(0,255,0,255),budget});
  const selectedQuery={...query,stateRevision:2n},selectedOp=(await first.begin({command:35,handle:source,sequence:2n,query:selectedQuery,budget})).operation;
  await selectedOp.drive({readChunk});const selected=await selectedOp.prepare(style);await first.pendingOperation.dispose();
  const p=new Uint8Array(24),pv=new DataView(p.buffer);pv.setUint32(0,1024,true);pv.setBigUint64(8,1000000n,true);pv.setBigUint64(16,64n<<20n,true);
  index=hierarchyReply(await bridge.execute(hierarchy({command:37,handle:selected.handle,sequence:2n,budget,payload:p}))).handle;
  const pages=new Map(),readPage=async t=>pages.get(`${t.namespace}:${t.page}`).slice(),writePage=async(t,b)=>{check(pages.size<64,'external page cache bound');pages.set(`${t.namespace}:${t.page}`,b.slice());};
  await driveGeoHierarchy(bridge,{handle:index,sequence:2n,budget,readChunk,readPage,writePage});
  const context={w,bridge,source,seed,selected,scope:firstScope,index,query:selectedQuery,style,readChunk,readPage,pages};contexts.push(context);return context;
 }catch(error){if(seed)await seed.dispose();if(index)await bridge.execute(encode({command:10,handle:index}));if(source)await bridge.execute(encode({command:10,handle:source}));throw error;}finally{await bridge.execute(encode({command:10,handle:builder}));}
}
async function state(x){const scope=await createGeoSelectedScope(x.bridge,{frameHandle:x.seed.handle,sequence:1n,namespace:MAX,layerId:MAX,budget});scopes.push(scope);const s=await scope.state({revision:2n,ids:BigUint64Array.of(MAX),fill:Uint8Array.of(0,255,0,255),budget});return {scope,s};}
function fault(w,command,transform){const native=w.worker,receive=native.onmessage;let armed=true;native.onmessage=event=>{const request=requests.find(r=>r.worker===native&&r.id===event.data?.requestId);if(armed&&request?.command===command&&event.data?.ok){armed=false;transform(event,request,receive,native);return;}receive.call(native,event);};return ()=>{native.onmessage=receive;check(!armed,'fault never reached actual Worker');};}

const holder=document.createElement('div');document.body.append(holder);let view,paint;
try{
 const x=await fixture(worker()),foreign=await fixture(worker());check(x.index===foreign.index,'colliding hierarchy issuers omitted');
 paint=await x.w.prepareGeoFrame(x.seed.handle,1n).result;view=hydrateWasmPainter(holder,paint);view.draw();await nextFrame();
 const selectedScope=x.scope;
 const issue=()=>selectedScope.state({revision:2n,ids:BigUint64Array.of(MAX),fill:Uint8Array.of(0,255,0,255),budget});
 const foreignState=await foreign.scope.state({revision:2n,ids:BigUint64Array.of(MAX),fill:Uint8Array.of(0,255,0,255),budget});
 const beforeForeign=requests.filter(r=>r.worker===x.w.worker&&r.command===43).length;
 await reject(beginGeoSelectedHierarchy(x.bridge,{state:foreignState,handle:x.index,sequence:3n,query:x.query,budget,storage:{readChunk:x.readChunk,readPage:x.readPage,writePage(){}},onIssued(){},onReleased(){},onPrepared(){}}),'foreign Worker State admitted');
 check(requests.filter(r=>r.worker===x.w.worker&&r.command===43).length===beforeForeign,'foreign State dispatched43');await foreignState.dispose();
 let sequence=3n;
 for(const mode of ['lost43','corrupt43','confirm47',...Array.from({length:12},(_,i)=>'micro'+(i+1))]){
  window.__selectedStage=mode;const state=await issue();let pending;
  const restore=fault(x.w,mode==='confirm47'?47:43,(event,r,receive,native)=>{
   if(mode.startsWith('micro')){receive.call(native,event);const packet=event.data.value;let n=Number(mode.slice(5));const mutate=()=>queueMicrotask(()=>{if(--n)mutate();else new DataView(packet).setBigUint64(16,999999n,true);});mutate();}
   else if(mode==='lost43')receive.call(native,{data:{...event.data,ok:false,error:{code:'XYG_WASM_RESOURCE_LIMIT',status:3,message:'after successful43'}}});
   else{new Uint8Array(event.data.value)[0]=0;receive.call(native,event);}
  });
  let operation;try{operation=await beginGeoSelectedHierarchy(x.bridge,{state,handle:x.index,sequence,query:x.query,budget,storage:{readChunk:x.readChunk,readPage:x.readPage,writePage:()=>{throw Error('query writes');}},onIssued:op=>pending=op,onReleased:()=>pending=undefined,onPrepared(){}});}catch{}
  restore();if(!operation){check(pending,'unknown43 dropped guard');operation=await pending.recover();}
  check(operation===pending,'recovery minted different operation');check(new DataView(operation.request).getBigUint64(240,true)===0n,'journal leaked into canonical query authoring');
  await operation.drive();const frame=await operation.prepare(x.style);check(frame.handle===state.handle&&frame.data.selection.visibleVertices===1n,'selected44 authority/count');await frame.dispose();check(!pending,'completed guard not released');sequence++;
 }
 // The real borrowed leaf cannot be disposed until callback and exact ACK settle.
 let entered,release;const enteredPromise=new Promise(r=>entered=r),gate=new Promise(r=>release=r);let pending;
 const op=await beginGeoSelectedHierarchy(x.bridge,{state:await issue(),handle:x.index,sequence,query:x.query,budget,storage:{readChunk:x.readChunk,readPage:async t=>{const bytes=await x.readPage(t);t.raw.fill(0);t.encodedBytes=0;entered();await gate;return bytes;},writePage(){}},onIssued:o=>pending=o,onReleased:()=>pending=undefined,onPrepared(){}});
 const drive=op.drive();await enteredPromise;let settled=false;const disposal=op.dispose().then(()=>settled=true);await new Promise(r=>setTimeout(r,20));check(!settled&&pending===op,'early borrowed disposal');release();await drive.catch(()=>{});await disposal;check(!pending,'ACK cleanup guard retained');
 // Lost successful Query10 is deliberately NOT retirement authority in this slice.
 const lostState=await issue();let lostPending;
 const lostOp=await beginGeoSelectedHierarchy(x.bridge,{state:lostState,handle:x.index,sequence:sequence+1n,query:x.query,budget,storage:{readChunk:x.readChunk,readPage:x.readPage,writePage(){}},onIssued:o=>lostPending=o,onReleased:()=>lostPending=undefined,onPrepared(){}});
 const restoreLost10=fault(x.w,10,(event,r,receive,native)=>receive.call(native,{data:{...event.data,ok:false,error:{code:'XYG_WASM_RESOURCE_LIMIT',status:3,message:'lost successful Query10'}}}));
 await reject(lostOp.dispose(),'lost Query10 treated as disposed');restoreLost10();await reject(lostOp.dispose(),'generic Stale became physical absence');check(lostPending===lostOp,'unknown Query10 guard dropped');
 await x.bridge.execute(hierarchy({command:10,handle:x.index,sequence:2n}));x.indexDisposed=true;await forgetSelectedGeoAllocationIssuer(x.bridge,x.index);
 window.__selectedMutation={ok:true,actualWorker:true,command43:true,exactReplayConfirm:true,canonicalNonce0:true,microtask12:true,privateBorrowedAck:true,lostQuery10RemainsGuarded:true,oldFrameRecordUnchanged:x.seed.data.record(0).featureId===MAX,numericCollisionsObserved:true,foreignWorkerStatePredispatchRejected:true,scope:'Bounded public43 recovery;44 publication and lostQuery10 remain explicit guards.'};
}catch(error){window.__selectedMutation={ok:false,stage:window.__selectedStage,error:error.stack??String(error),requests:requests.slice(-12).map(r=>({command:r.command,handle:String(r.handle),sequence:String(r.sequence)}))};}
finally{if(view)view.destroy();view=paint=undefined;for(const x of contexts)try{await x.selected.dispose();await x.seed.dispose();if(!x.indexDisposed)await x.bridge.execute(hierarchy({command:10,handle:x.index,sequence:2n}));await forgetSelectedGeoAllocationIssuer(x.bridge,x.index);await x.bridge.execute(encode({command:10,handle:x.source}));}catch{}for(const s of scopes)try{await s.dispose();}catch{}for(const w of workers)try{await w.dispose();}catch{}Worker.prototype.postMessage=nativePost;holder.remove();}
