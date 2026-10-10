// Test-only genuine Worker dispatcher provenance; no public testing exports.
import {createXygWasmWorker,beginGeoWorkerMutationCapture,withGeoWorkerMutationOutcome} from '../../js/src/47_wasm';
import {encodeGeoScaleRequest as encode,encodeGeoChunkRequest,encodeGeoScaleStyle,decodeGeoScaleReply as decode,driveGeoSession,driveGeoIndexSession,parseGeoSceneData} from '../../js/src/63_geo_source';
const assert={equal(a,b){if(a!==b)throw Error(`expected ${String(b)}, got ${String(a)}`);}};
const MAX=0xffffffffffffffffn,MIN=-0x8000000000000000n;
const budget={processorBytes:128<<20,maxRowsExamined:1000000n,maxReadBytes:128n<<20n,maxChunks:65536,pageRows:4096};
const style=encodeGeoScaleStyle({fill:Uint8Array.of(255,0,0,255),stroke:new Uint8Array(4),strokeWidth:0,diameter:6,opacity:1,symbol:0});
function check(value,message){if(!value)throw Error(message);}
function raw(command,handle=0n,sequence=0n,payload,query,nonce=0n,limits=budget){if(ArrayBuffer.isView(payload))payload=new Uint8Array(payload.buffer,payload.byteOffset,payload.byteLength);const b=encode({command:query?5:6,handle,sequence,payload,query,budget:limits});const v=new DataView(b);v.setUint32(8,command,true);v.setBigUint64(240,nonce,true);return b;}
function fixed(packet){assert.equal(packet.byteLength,256);const v=new DataView(packet);assert.equal(v.getUint32(0,true),0x5a475958);assert.equal(v.getUint32(4,true),1);assert.equal(v.getUint32(12,true),0);return {code:v.getUint32(8,true),handle:v.getBigUint64(16,true),sequence:v.getBigUint64(24,true)};}
function ack(request,target,action=0){const v=new DataView(request),p=new Uint8Array(16),pv=new DataView(p.buffer);pv.setUint32(0,v.getUint32(8,true),true);pv.setUint32(4,action,true);pv.setBigUint64(8,target,true);return raw(47,v.getBigUint64(16,true),v.getBigUint64(24,true),p,undefined,v.getBigUint64(240,true));}
async function close(bridge,h){assert.equal(fixed(await bridge.execute(raw(10,h))).code,0);}
async function fixture(bridge,vertices,namespace=MAX){
 const validity=64+16*vertices,ids=(validity+4+7)&~7,offset=ids+32,d=new Uint8Array(offset+24),v=new DataView(d.buffer);d.set([88,89,71,68]);[1,4,4326,1,0].forEach((n,i)=>v.setUint32(4+4*i,n,true));[4n,BigInt(vertices),5n,0n,0n].forEach((n,i)=>v.setBigUint64(24+8*i,n,true));v.setFloat64(64+16*(vertices-2),1,true);v.setFloat64(64+16*(vertices-2)+8,1,true);v.setFloat64(64+16*(vertices-1),179,true);d.set([1,1,0,1],validity);[MAX,MAX,1n<<63n,9007199254740993n].forEach((n,i)=>v.setBigUint64(ids+8*i,n,true));[0,vertices-2,vertices-1,vertices-1,vertices].forEach((n,i)=>v.setUint32(offset+4*i,n,true));
 const chunk=await bridge.read(encodeGeoChunkRequest({descriptor:d,rows:4,intervals:{starts:new BigInt64Array([MIN,0n,MIN,MIN]),ends:new BigInt64Array([0n,0n,0n,0n]),startValidity:Uint8Array.of(1,1,0,1),endValidity:Uint8Array.of(1,0,0,1)}},budget.processorBytes));
 const builder=decode(await bridge.execute(raw(1))).handle;await bridge.execute(raw(2,builder,0n,chunk));const finish=encode({command:3,handle:builder,generation:MAX});await bridge.execute(finish);const manifest=await bridge.read(raw(21,builder));await close(bridge,builder);
 const source=decode(await bridge.execute(raw(4,0n,0n,manifest))).handle,readChunk=async()=>chunk;
 const info=(await driveGeoSession(bridge,{handle:source,sequence:0n,budget,readChunk})).source;
 const query={camera:{crs:4326,worldWrap:true,centerX:0,centerY:0,zoom:2,width:800,height:600,bearing:0,pitch:0},reducedKind:0,maxCells:1,previousDirect:true,sourceDigest:info.digest,generation:info.generation,layerId:MAX,cameraRevision:1n,timeRevision:1n,layerRevision:1n,styleRevision:1n,stateRevision:1n,time:{kind:1,instant:MIN},maxProjectedVertices:1000000n};
 await bridge.execute(raw(5,source,1n,undefined,query));await driveGeoSession(bridge,{handle:source,sequence:1n,budget,readChunk});const seed=fixed(await bridge.execute(raw(11,source,1n,style))).handle;
 const sp=new Uint8Array(16),sv=new DataView(sp.buffer);sv.setBigUint64(0,namespace,true);sv.setBigUint64(8,MAX,true);const scope=fixed(await bridge.execute(raw(32,seed,1n,sp))).handle;
 const publish=async()=>{const p=new Uint8Array(40),v=new DataView(p.buffer);v.setBigUint64(0,2n,true);p.set([0,255,0,255],8);v.setBigUint64(16,2n,true);v.setBigUint64(24,MAX,true);v.setBigUint64(32,MAX,true);return fixed(await bridge.execute(raw(33,scope,0n,p))).handle;};
 return {source,seed,scope,query:{...query,stateRevision:2n},readChunk,chunk,publish};
}

export async function verifySelected19Capture(){
 const worker=createXygWasmWorker({wasm:'/packages/xy-client/dist/xyg-wasm.wasm',workerUrl:'/packages/xy-client/dist/wasm-worker.js',maxArenaBytes:128<<20});await worker.ready;
 const bridge=worker.geoScaleBridge();
 try{
 const f=await fixture(bridge,4),bp=new Uint8Array(16);new DataView(bp.buffer).setUint32(0,2,true);new DataView(bp.buffer).setBigUint64(8,1000000n,true);
 const index=fixed(await bridge.execute(raw(17,f.seed,1n,bp))).handle,pages=new Map();
 await driveGeoIndexSession(bridge,{handle:index,sequence:1n,budget,readChunk:f.readChunk,readPage:async t=>pages.get(t.page),writePage:async(t,b)=>pages.set(t.page,b.slice())});
 const state=await f.publish(),mutation=raw(36,index,2n,new BigUint64Array([state]),f.query,1n);assert.equal(fixed(await bridge.execute(mutation.slice(0))).handle,state);await bridge.execute(ack(mutation,state));
 const publication=raw(19,state,2n,style,undefined,1n);assert.equal(publication.byteLength,304);
 let early;await withGeoWorkerMutationOutcome(bridge,publication,async outcome=>{try{await bridge.execute(publication.slice(0));}catch(error){early=error;check(outcome(error),'genuine unready19 rejection missing');}check(early,'unready publication succeeded');await driveGeoIndexSession(bridge,{handle:state,sequence:2n,budget,readPage:async t=>pages.get(t.page)});const packet=await bridge.execute(publication.slice(0));check(outcome(packet)?.reply===packet,'same-call cloned success missing');try{throw early;}catch(error){check(!outcome(error),'same-call older rejection authorized nonadmission');}});
 const failed=publication.slice(0);new DataView(failed).setBigUint64(32,8192n,true);let prior;
 await withGeoWorkerMutationOutcome(bridge,failed,async outcome=>{try{await bridge.execute(failed.slice(0));}catch(error){prior=error;check(outcome(error)?.code,'genuine19 rejection missing');}check(prior,'19 pressure unexpectedly admitted');});
 let sameCall;
 await withGeoWorkerMutationOutcome(bridge,publication,async outcome=>{
  const packet=await bridge.execute(publication.slice(0));assert.equal(fixed(packet).handle,state);check(!outcome(prior),'earlier real rejection authorized later19');check(outcome(packet)?.reply===packet,'19 success missing scoped authority');
  new Uint8Array(packet)[48]=1;check(!outcome(packet),'mutated19 reply retained authority');
  const clone=await bridge.execute(publication.slice(0));check(outcome(clone)?.reply===clone,'clone exact19 lacks latest authority');check(!outcome(packet),'superseded19 reply retained authority');sameCall=true;
 });
 const confirmation=ack(publication,state);
 await withGeoWorkerMutationOutcome(bridge,confirmation,async outcome=>{const packet=await bridge.execute(confirmation.slice(0));assert.equal(fixed(packet).code,0);check(outcome(packet)?.reply===packet,'47 original19 missing scoped authority');new Uint8Array(packet)[48]=1;check(!outcome(packet),'mutated47 retained authority');});
 // Exact-byte cloned success followed by an older genuine Error cannot mint rejection.
 await withGeoWorkerMutationOutcome(bridge,publication,async outcome=>{let threw=false;try{await bridge.execute(publication.slice(0));throw prior;}catch(error){threw=true;check(!outcome(error),'old genuine error authorized clone success');}check(threw,'older-error wrapper did not execute');});
 const scopes=Array.from({length:16},()=>beginGeoWorkerMutationCapture(bridge,publication));let capped=false;try{beginGeoWorkerMutationCapture(bridge,publication);}catch{capped=true;}check(capped,'capture17 admitted');scopes.forEach(s=>s.close());
 const unmatched=[];
 for(const [command,length,tag] of [[19,303,0],[19,305,0],[44,304,0],[47,272,44],[47,271,19],[47,273,19]]){
  const b=new ArrayBuffer(length);new Uint8Array(b).set(new Uint8Array(command===47?confirmation:publication).subarray(0,Math.min(length,command===47?272:304)));const v=new DataView(b);v.setUint32(8,command,true);if(command===47)v.setUint32(256,tag,true);
  if(length>304){let rejected=false;try{beginGeoWorkerMutationCapture(bridge,b);}catch{rejected=true;}check(rejected,'oversized capture admitted');unmatched.push(true);continue;}
  await withGeoWorkerMutationOutcome(bridge,b,async outcome=>{try{const packet=await bridge.execute(b.slice(0));check(!outcome(packet),'nonwhitelisted packet branded');}catch(error){check(!outcome(error),'nonwhitelisted rejection branded');}unmatched.push(true);});
 }
 const scene=parseGeoSceneData(await bridge.read(raw(23,state)));assert.equal(scene.selection.id(0),MAX);assert.equal(scene.selection.visibleVertices,2n);
 await close(bridge,state);await bridge.execute(ack(publication,state));await bridge.execute(ack(publication,state,2));await bridge.execute(ack(publication,state,1));await bridge.execute(ack(mutation,state));await bridge.execute(ack(mutation,state,2));await close(bridge,index);await bridge.execute(ack(mutation,state,1));await close(bridge,f.source);await close(bridge,f.seed);await close(bridge,f.scope);
 const last=beginGeoWorkerMutationCapture(bridge,publication);last.close();check(!last.outcome(prior),'closed scope retained old error');
 return {success19:true,confirmOriginal19:true,genuineRejection:true,clonedLatestDispatch:sameCall,olderErrorCannotAuthorize:true,mutatedRepliesRejected:true,nonmatchingUnbranded:unmatched.length===6,capacity16:true,finallyCleanup:true,literalSelectedU64:true};
 }finally{worker.dispose();}
}
