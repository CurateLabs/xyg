// Test-only genuine Worker dispatcher provenance; no public testing exports.
import {createXygWasmWorker,beginGeoWorkerMutationCapture,withGeoWorkerMutationOutcome} from '../../js/src/47_wasm';
import {encodeGeoScaleRequest as encode,encodeGeoChunkRequest,encodeGeoScaleStyle,decodeGeoScaleReply as decode,driveGeoSession,parseGeoSceneData} from '../../js/src/63_geo_source';
const assert={equal(a,b){if(a!==b)throw Error(`expected ${String(b)}, got ${String(a)}`);}};
const MAX=0xffffffffffffffffn,MIN=-0x8000000000000000n;
const budget={processorBytes:128<<20,maxRowsExamined:1000000n,maxReadBytes:128n<<20n,maxChunks:65536,pageRows:4096};
const style=encodeGeoScaleStyle({fill:Uint8Array.of(255,0,0,255),stroke:new Uint8Array(4),strokeWidth:0,diameter:6,opacity:1,symbol:0});
function check(value,message){if(!value)throw Error(message);}
function raw(command,handle=0n,sequence=0n,payload,query,nonce=0n,limits=budget){if(ArrayBuffer.isView(payload))payload=new Uint8Array(payload.buffer,payload.byteOffset,payload.byteLength);const b=encode({command:query?5:6,handle,sequence,payload,query,budget:limits});const v=new DataView(b);v.setUint32(8,command,true);v.setBigUint64(240,nonce,true);return b;}
function fixed(packet){assert.equal(packet.byteLength,256);const v=new DataView(packet);assert.equal(v.getUint32(0,true),0x5a475958);assert.equal(v.getUint32(4,true),1);assert.equal(v.getUint32(12,true),0);return {code:v.getUint32(8,true),handle:v.getBigUint64(16,true),sequence:v.getBigUint64(24,true)};}
function ack(request,target,action=0){const v=new DataView(request),p=new Uint8Array(16),pv=new DataView(p.buffer);pv.setUint32(0,v.getUint32(8,true),true);pv.setUint32(4,action,true);pv.setBigUint64(8,target,true);return raw(47,v.getBigUint64(16,true),v.getBigUint64(24,true),p,undefined,v.getBigUint64(240,true));}
async function execute(bridge,request){const v=new DataView(request),label=`command ${v.getUint32(8,true)} owner ${v.getBigUint64(16,true)} sequence ${v.getBigUint64(24,true)} nonce ${v.getBigUint64(240,true)}`;try{return await bridge.execute(request);}catch(error){error.message+=` (${label})`;throw error;}}
async function close(bridge,h,sequence=0n){assert.equal(fixed(await execute(bridge,raw(10,h,sequence))).code,0);}
async function fixture(bridge,vertices,namespace=MAX){
 const validity=64+16*vertices,ids=(validity+4+7)&~7,offset=ids+32,d=new Uint8Array(offset+24),v=new DataView(d.buffer);d.set([88,89,71,68]);[1,4,4326,1,0].forEach((n,i)=>v.setUint32(4+4*i,n,true));[4n,BigInt(vertices),5n,0n,0n].forEach((n,i)=>v.setBigUint64(24+8*i,n,true));v.setFloat64(64+16*(vertices-2),1,true);v.setFloat64(64+16*(vertices-2)+8,1,true);v.setFloat64(64+16*(vertices-1),179,true);d.set([1,1,0,1],validity);[MAX,MAX,1n<<63n,9007199254740993n].forEach((n,i)=>v.setBigUint64(ids+8*i,n,true));[0,vertices-2,vertices-1,vertices-1,vertices].forEach((n,i)=>v.setUint32(offset+4*i,n,true));
 const chunk=await bridge.read(encodeGeoChunkRequest({descriptor:d,rows:4,intervals:{starts:new BigInt64Array([MIN,0n,MIN,MIN]),ends:new BigInt64Array([0n,0n,0n,0n]),startValidity:Uint8Array.of(1,1,0,1),endValidity:Uint8Array.of(1,0,0,1)}},budget.processorBytes));
 const builder=decode(await execute(bridge,raw(1))).handle;await execute(bridge,raw(2,builder,0n,chunk));const finish=encode({command:3,handle:builder,generation:MAX});await execute(bridge,finish);const manifest=await bridge.read(raw(21,builder));await close(bridge,builder);
 const source=decode(await execute(bridge,raw(4,0n,0n,manifest))).handle,readChunk=async()=>chunk;
 const info=(await driveGeoSession(bridge,{handle:source,sequence:0n,budget,readChunk})).source;
 const query={camera:{crs:4326,worldWrap:true,centerX:0,centerY:0,zoom:2,width:800,height:600,bearing:0,pitch:0},reducedKind:0,maxCells:1,previousDirect:true,sourceDigest:info.digest,generation:info.generation,layerId:MAX,cameraRevision:1n,timeRevision:1n,layerRevision:1n,styleRevision:1n,stateRevision:1n,time:{kind:1,instant:MIN},maxProjectedVertices:1000000n};
 await execute(bridge,raw(5,source,1n,undefined,query));await driveGeoSession(bridge,{handle:source,sequence:1n,budget,readChunk});const seed=fixed(await execute(bridge,raw(11,source,1n,style))).handle;
 const sp=new Uint8Array(16),sv=new DataView(sp.buffer);sv.setBigUint64(0,namespace,true);sv.setBigUint64(8,MAX,true);const scope=fixed(await execute(bridge,raw(32,seed,1n,sp))).handle;
 const publish=async()=>{const p=new Uint8Array(40),v=new DataView(p.buffer);v.setBigUint64(0,2n,true);p.set([0,255,0,255],8);v.setBigUint64(16,2n,true);v.setBigUint64(24,MAX,true);v.setBigUint64(32,MAX,true);return fixed(await execute(bridge,raw(33,scope,0n,p))).handle;};
 return {source,seed,scope,query:{...query,stateRevision:2n},readChunk,chunk,publish};
}

async function hierarchy(bridge){
 const f=await fixture(bridge,4),selected={...f.query,cameraRevision:2n,timeRevision:2n,layerRevision:2n,styleRevision:2n};
 const st=await f.publish();await execute(bridge,raw(35,f.source,2n,new BigUint64Array([st]),selected));await driveGeoSession(bridge,{handle:f.source,sequence:2n,budget,readChunk:f.readChunk});
 const reference=fixed(await execute(bridge,raw(11,f.source,2n,style))).handle;
 const bp=new Uint8Array(24),bv=new DataView(bp.buffer);bv.setUint32(0,1024,true);bv.setBigUint64(8,1000000n,true);bv.setBigUint64(16,64n<<20n,true);
 const lane=fixed(await execute(bridge,raw(37,reference,2n,bp))).handle,pages=new Map();
 async function drive(handle,sequence,done){for(;;){const packet=await execute(bridge,raw(6,handle,sequence)),v=new DataView(packet),code=v.getUint32(8,true);if(code===done)return;check([1,7].includes(code),`unexpected hierarchy code ${code}`);const ticket=new Uint8Array(packet,64,128).slice(),tv=new DataView(ticket.buffer),kind=tv.getUint32(32,true),key=`${tv.getBigUint64(8,true)}:${tv.getBigUint64(40,true)}`;let bytes,payload;try{if(kind===3){bytes=await bridge.read(raw(40,handle,sequence,ticket));pages.set(key,new Uint8Array(bytes).slice());}else{bytes=kind===1?f.chunk:pages.get(key);check(bytes,'missing page');const b=bytes instanceof ArrayBuffer?new Uint8Array(bytes):bytes;payload=new Uint8Array(128+b.length);payload.set(ticket);payload.set(b,128);await execute(bridge,raw(7,handle,sequence,payload));}}finally{bytes=payload=undefined;await execute(bridge,raw(kind===3?41:8,handle,sequence,ticket));}}}
 await drive(lane,2n,18);return {...f,lane,reference,selected,drive};
}
export async function verifyHierarchyCapture(){
 const options={wasm:'/packages/xy-client/dist/xyg-wasm.wasm',workerUrl:'/packages/xy-client/dist/wasm-worker.js',maxArenaBytes:128<<20};
 const worker=createXygWasmWorker(options),foreign=createXygWasmWorker(options);await Promise.all([worker.ready,foreign.ready]);
 const bridge=worker.geoScaleBridge(),other=foreign.geoScaleBridge();
 try{
 const f=await hierarchy(bridge),g=await hierarchy(other);assert.equal(f.lane,g.lane);
 const state=await f.publish(),foreignState=await g.publish();assert.equal(state,foreignState);
 const mutation=raw(43,f.lane,3n,new BigUint64Array([state]),f.selected,1n);assert.equal(mutation.byteLength,264);
 // A genuine different Worker with colliding handles is not this issuer.
 await withGeoWorkerMutationOutcome(bridge,mutation,async outcome=>{const packet=await execute(other,mutation.slice(0));assert.equal(fixed(packet).handle,foreignState);check(!outcome(packet),'foreign colliding Worker branded');});
 await execute(other,ack(mutation,foreignState));
 let lost=false;await withGeoWorkerMutationOutcome(bridge,mutation,async outcome=>{try{await execute(bridge,mutation.slice(0));throw Error('lost actual43 reply');}catch(error){lost=true;check(!outcome(error),'lost43 generic error branded');}});check(lost,'lost43 not exercised');
 await withGeoWorkerMutationOutcome(bridge,mutation,async outcome=>{const packet=await execute(bridge,mutation.slice(0));assert.equal(fixed(packet).handle,state);check(outcome(packet)?.reply===packet,'exact43 replay missing');new Uint8Array(packet)[48]=1;check(!outcome(packet),'mutated43 branded');const clone=await execute(bridge,mutation.slice(0));check(outcome(clone)?.reply===clone,'clone43 missing');check(!outcome(packet),'old43 reply branded');});
 const confirm43=ack(mutation,state);await withGeoWorkerMutationOutcome(bridge,confirm43,async outcome=>{const packet=await execute(bridge,confirm43.slice(0));check(outcome(packet)?.reply===packet,'47 original43 missing');assert.equal(fixed(packet).handle,state);});
 const publication=raw(44,state,3n,style,undefined,1n);assert.equal(publication.byteLength,304);
 let earlier;await withGeoWorkerMutationOutcome(bridge,publication,async outcome=>{try{await execute(bridge,publication.slice(0));}catch(error){earlier=error;check(outcome(error)?.code,'genuine unready44 missing');}check(earlier,'unready44 succeeded');await f.drive(state,3n,19);const packet=await execute(bridge,publication.slice(0));check(outcome(packet)?.reply===packet,'same-call cloned44 missing');check(!outcome(earlier),'same-call older genuine rejection branded');});
 let scalar;await withGeoWorkerMutationOutcome(bridge,publication,async outcome=>{const packet=await execute(bridge,publication.slice(0));check(!outcome(earlier),'prior-call rejection branded');check(outcome(packet)?.reply===packet,'44 replay missing');scalar=fixed(packet);queueMicrotask(()=>new DataView(packet).setBigUint64(16,999n,true));});await Promise.resolve();assert.equal(scalar.handle,state);
 await withGeoWorkerMutationOutcome(bridge,publication,async outcome=>{try{await execute(bridge,publication.slice(0));throw Error('lost actual44 reply');}catch(error){check(!outcome(error),'lost44 generic error branded');}});
 const confirm44=ack(publication,state);await withGeoWorkerMutationOutcome(bridge,confirm44,async outcome=>{const packet=await execute(bridge,confirm44.slice(0));check(outcome(packet)?.reply===packet,'47 original44 missing');assert.equal(fixed(packet).handle,state);new Uint8Array(packet)[48]=1;check(!outcome(packet),'mutated47 branded');});
 await withGeoWorkerMutationOutcome(bridge,publication,async outcome=>{try{await execute(bridge,publication.slice(0));throw earlier;}catch(error){check(!outcome(error),'cloned44 success then old error branded');}});
 const scopes=Array.from({length:16},()=>beginGeoWorkerMutationCapture(bridge,publication));let capped=false;try{beginGeoWorkerMutationCapture(bridge,publication);}catch{capped=true;}check(capped,'capture17 admitted');scopes.forEach(s=>s.close());
 for(const [command,length,tag] of [[43,263,0],[43,265,0],[44,303,0],[44,305,0],[47,272,42],[47,272,45],[47,271,43],[47,273,44]]){const source=command===43?mutation:command===44?publication:confirm44,b=new ArrayBuffer(length);new Uint8Array(b).set(new Uint8Array(source).subarray(0,Math.min(length,source.byteLength)));const v=new DataView(b);v.setUint32(8,command,true);if(command===47)v.setUint32(256,tag,true);if(length>304){let rejected=false;try{beginGeoWorkerMutationCapture(bridge,b);}catch{rejected=true;}check(rejected,'oversized capture accepted');continue;}await withGeoWorkerMutationOutcome(bridge,b,async outcome=>{try{const packet=await execute(bridge,b.slice(0));check(!outcome(packet),'nonmatching packet branded');}catch(error){check(!outcome(error),'nonmatching error branded');}});}
 const scene=parseGeoSceneData(await bridge.read(raw(23,state)));assert.equal(scene.selection.id(0),MAX);assert.equal(scene.selection.visibleVertices,2n);
 await close(bridge,state);await execute(bridge,ack(publication,state));await execute(bridge,ack(publication,state,2));await execute(bridge,ack(publication,state,1));await execute(bridge,ack(mutation,state));await execute(bridge,ack(mutation,state,2));await close(bridge,f.lane,2n);await execute(bridge,ack(mutation,state,1));
 await execute(other,raw(9,foreignState,3n));await g.drive(foreignState,3n,9);await execute(other,raw(10,foreignState,3n));await execute(other,ack(mutation,foreignState));await execute(other,ack(mutation,foreignState,2));await close(other,g.lane,2n);await execute(other,ack(mutation,foreignState,1));
 for(const [b,x] of [[bridge,f],[other,g]]){await close(b,x.reference);await close(b,x.seed);await close(b,x.source);await close(b,x.scope);}
 const last=beginGeoWorkerMutationCapture(bridge,publication);last.close();check(!last.outcome(earlier),'closed scope retained authority');
 return {exact43:true,exact44:true,confirmOriginal43:true,confirmOriginal44:true,genuineRejection:true,lostReplyExactReplay:true,clonedLatestDispatch:true,olderGenuineErrorRejected:true,receiptMicrotaskCannotRetagScalar:true,foreignCollidingWorkerRejected:true,mutatedReplyRejected:true,nonmatchingLengthsTagsUnbranded:true,capacity16:true,finallyCleanup:true,literalSelectedU64:true};
 }finally{worker.dispose();foreign.dispose();}
}
