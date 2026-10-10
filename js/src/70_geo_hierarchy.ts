/** Thin hierarchy transport. Rust owns sorting, pruning, time and exact LOD. */
import {encodeGeoScaleRequest, decodeGeoScaleReply, parseGeoSceneData,
 type XygGeoScaleRequest, type XygGeoScaleBridge, type XygGeoQueryBudget, type XygGeoScaleQuery} from './63_geo_source';
import {claimGeoSelectedState,type GeoSelectedState} from './68_geo_selected';
import {GeoAllocationAttempt,selectedGeoAllocationIssuer,preflightSelectedGeoAllocation,trackSelectedGeoAllocation} from './72_geo_allocation_attempt';
import {withGeoWorkerMutationOutcome} from './47_wasm';

export function encodeGeoHierarchyRequest(input:XygGeoScaleRequest):ArrayBuffer {
 if(![6,7,8,9,10,37,38,39,40,41,42,43,44].includes(input.command))throw new TypeError('unknown hierarchy command');
 const request=encodeGeoScaleRequest({...input,command:[38,43].includes(input.command)?5:6});
 const view=new DataView(request);view.setUint32(8,input.command,true);return request;
}
function zero(bytes:Uint8Array,start:number,end:number){if(bytes.subarray(start,end).some(n=>n!==0))throw new TypeError('nonzero hierarchy reserved bytes');}
export interface GeoHierarchyTicket {raw:Uint8Array;owner:bigint;namespace:bigint;serial:bigint;sequence:bigint;kind:number;page:bigint;encodedBytes:number;digest:Uint8Array;generation:bigint;chunkIndex:number;rows:number;firstRow:bigint}
function ticket(raw:Uint8Array):GeoHierarchyTicket {
 const v=new DataView(raw.buffer,raw.byteOffset,raw.byteLength),kind=v.getUint32(32,true),size=v.getBigUint64(48,true);
 zero(raw,36,40);zero(raw,104,128);
 if(![1,2,3,4,5].includes(kind)||size===0n||size>BigInt(kind===1?16*1024*1024:65536))throw new TypeError('invalid hierarchy ticket');
 if(kind===1){if(v.getUint32(76,true)>65536||v.getBigUint64(88,true)!==size||raw.subarray(96,104).some((n,i)=>n!==raw[56+i]))throw new TypeError('mismatched canonical ticket');}
 else zero(raw,64,104);
 return {raw,owner:v.getBigUint64(0,true),namespace:v.getBigUint64(8,true),serial:v.getBigUint64(16,true),sequence:v.getBigUint64(24,true),kind,page:v.getBigUint64(40,true),encodedBytes:Number(size),digest:raw.slice(56,64),generation:v.getBigUint64(64,true),chunkIndex:v.getUint32(72,true),rows:v.getUint32(76,true),firstRow:v.getBigUint64(80,true)};
}
export function decodeGeoHierarchyReply(buffer:ArrayBuffer) {
 if(!(buffer instanceof ArrayBuffer)||buffer.byteLength!==256)throw new TypeError('fixed hierarchy reply required');
 const b=new Uint8Array(buffer),v=new DataView(buffer),code=v.getUint32(8,true);
 if(String.fromCharCode(...b.subarray(0,4))!=='XYGZ'||v.getUint32(4,true)!==1)throw new TypeError('invalid hierarchy reply');zero(b,12,16);
 const handle=v.getBigUint64(16,true),sequence=v.getBigUint64(24,true);
 if(code===0||code===6||code===10){const ordinary=decodeGeoScaleReply(buffer);return {...ordinary,ticket:null,hierarchyStats:null,namespace:0n};}
 if(![1,2,7,9,17,18,19].includes(code))throw new TypeError('invalid hierarchy reply code');
 let loan:GeoHierarchyTicket|null=null;
 if([1,2,7].includes(code)){zero(b,32,64);zero(b,192,256);if(b.subarray(64,192).some(n=>n!==0)){loan=ticket(b.slice(64,192));if(loan.sequence!==sequence||code===1&&loan.kind===3||code===7&&loan.kind!==3)throw new TypeError('mismatched hierarchy loan');}else if(code!==2)throw new TypeError('missing hierarchy ticket');}
 else if(code===18){zero(b,32,40);zero(b,56,256);}
 else if(code===19){zero(b,32,160);zero(b,200,256);if(![1,2].includes(v.getUint32(192,true))||v.getUint32(196,true)>256)throw new TypeError('invalid hierarchy stats');}
 else zero(b,32,256);
 return {code,handle,sequence,ticket:loan,hierarchyStats:code===19?{directoryReads:v.getBigUint64(160,true),leafReads:v.getBigUint64(168,true),bytesRead:v.getBigUint64(176,true),decodedVertices:v.getBigUint64(184,true),passes:v.getUint32(192,true),cells:v.getUint32(196,true)}:null,namespace:code===18?v.getBigUint64(48,true):0n,fallbackReasonCode:null};
}
export class GeoHierarchyFallback extends Error {reasonCode:number;constructor(reasonCode:number){super(`Rust hierarchy requires explicit canonical fallback (${reasonCode})`);this.reasonCode=reasonCode;this.name='GeoHierarchyFallback';}}
export class GeoHierarchyUnsupportedSelected extends Error {constructor(){super('Rust hierarchy does not support selected authority');this.name='GeoHierarchyUnsupportedSelected';}}
function aborted(){return new Error('hierarchy operation aborted');}
function exact(value:ArrayBuffer|Uint8Array,size:number){const b=value instanceof Uint8Array?value:new Uint8Array(value);if(b.byteLength!==size||b.buffer.byteLength>size)throw new TypeError('callback must return exact bounded storage');return b;}
export interface GeoHierarchyStorage {readChunk:(ticket:GeoHierarchyTicket,signal?:AbortSignal)=>Promise<ArrayBuffer|Uint8Array>|ArrayBuffer|Uint8Array;readPage:(ticket:GeoHierarchyTicket,signal?:AbortSignal)=>Promise<ArrayBuffer|Uint8Array>|ArrayBuffer|Uint8Array;writePage:(ticket:GeoHierarchyTicket,bytes:Uint8Array,signal?:AbortSignal)=>Promise<void>|void}
export async function driveGeoHierarchy(bridge:XygGeoScaleBridge,input:GeoHierarchyStorage&{handle:bigint;sequence:bigint;budget:XygGeoQueryBudget;signal?:AbortSignal}) {
 const {handle,sequence,budget,signal}=input;let cancellation:Promise<unknown>|undefined;
 const cancel=()=>cancellation??=bridge.execute(encodeGeoHierarchyRequest({command:9,handle,sequence}));
 const onAbort=()=>{void cancel().catch(()=>{});};signal?.addEventListener('abort',onAbort,{once:true});
 try{for(;;){if(signal?.aborted)throw aborted();const reply=decodeGeoHierarchyReply(await bridge.execute(encodeGeoHierarchyRequest({command:6,handle,sequence,budget})));
  if(reply.handle!==handle||reply.sequence!==sequence)throw new TypeError('mismatched hierarchy authority');
  if(signal?.aborted){if(!reply.ticket)throw aborted();}
  else if(reply.code===18||reply.code===19)return reply;
  else if(reply.code===10)throw new GeoHierarchyFallback(reply.fallbackReasonCode!);
  const loan=reply.ticket;if(!loan||![1,7].includes(reply.code))throw new Error('hierarchy did not complete');
  const authority=loan.raw.slice(),size=loan.encodedBytes,write=loan.kind===3,publicTicket={...loan,raw:loan.raw.slice(),digest:loan.digest.slice()};
  let borrowed:ArrayBuffer|Uint8Array|undefined,view:Uint8Array|undefined,payload:Uint8Array|undefined,request:ArrayBuffer|undefined;
  try{if(signal?.aborted)throw aborted();if(4*(384+size)>budget.processorBytes)throw new RangeError('hierarchy transfer exceeds phase budget');
   if(write){borrowed=await bridge.read(encodeGeoHierarchyRequest({command:40,handle,sequence,payload:authority}));if(signal?.aborted)throw aborted();view=exact(borrowed,size);await input.writePage(publicTicket,view,signal);}
   else {borrowed=await (loan.kind===1?input.readChunk:input.readPage)(publicTicket,signal);if(signal?.aborted)throw aborted();view=exact(borrowed,size);payload=new Uint8Array(128+size);payload.set(authority);payload.set(view,128);request=encodeGeoHierarchyRequest({command:7,handle,sequence,payload});await bridge.execute(request);}
   if(signal?.aborted)throw aborted();
  }catch(error){borrowed=view=payload=request=undefined;await cancel().catch(()=>{});throw error;}
  finally{borrowed=view=payload=request=undefined;await bridge.execute(encodeGeoHierarchyRequest({command:write?41:8,handle,sequence,payload:authority}));}
 }}catch(error){await cancel().catch(()=>{});throw error;}finally{signal?.removeEventListener('abort',onAbort);if(cancellation)await cancellation.catch(()=>{});}
}
export async function prepareGeoHierarchyScene(bridge:XygGeoScaleBridge,input:{handle:bigint;sequence:bigint;budget:XygGeoQueryBudget;style:Uint8Array;command?:39|44;onAttempt?:()=>void;onReceipt?:()=>void;onRelease?:()=>void}) {
 if(!(input.style instanceof Uint8Array)||input.style.byteLength!==48||input.style.buffer.byteLength>48)throw new TypeError('exact48-byte style required');
 const command=input.command??39;input.onAttempt?.();
 const r=decodeGeoScaleReply(await bridge.execute(encodeGeoHierarchyRequest({command,handle:input.handle,sequence:input.sequence,budget:input.budget,payload:input.style})));
 if(command===44&&(r.code!==0||r.handle!==input.handle||r.sourceHandle!==input.handle||r.sequence!==input.sequence))throw new TypeError('invalid same-handle publication receipt');
 const handle=r.handle;input.onReceipt?.();
 let packet:ArrayBuffer|undefined,data:ReturnType<typeof parseGeoSceneData>|undefined;
 try{if(r.code!==0||r.sourceHandle!==input.handle||r.sequence!==input.sequence||4n*r.dataLength>BigInt(input.budget.processorBytes))throw new TypeError('invalid hierarchy Scene receipt');packet=await bridge.read(encodeGeoScaleRequest({command:23,handle}));if(BigInt(packet.byteLength)!==r.dataLength||packet.byteLength>32*1024*1024)throw new TypeError('invalid Scene length');data=parseGeoSceneData(packet);if(data.identity.sessionHandle!==input.handle||data.identity.sequence!==input.sequence)throw new TypeError('mismatched Scene identity');packet=undefined;}
 catch(error){packet=data=undefined;await bridge.execute(encodeGeoScaleRequest({command:10,handle}));input.onRelease?.();throw error;}
 let disposal:Promise<void>|undefined;
 return {handle,get data(){if(!data)throw new Error('SceneData disposed');return data;},dispose(){data=undefined;if(disposal)return disposal;const task=bridge.execute(encodeGeoScaleRequest({command:10,handle})).then(()=>{});disposal=task;task.catch(()=>{if(disposal===task)disposal=undefined;});return task;}};
}

const CAPTURED_TRANSPORTS=new WeakMap<object,{issuer:XygGeoScaleBridge;transport:XygGeoScaleBridge}>();
/** Internal opaque captured callables; a caller cannot substitute a foreign transport. */
export function captureGeoHierarchyTransport(issuer:XygGeoScaleBridge){
 const token=Object.freeze({});CAPTURED_TRANSPORTS.set(token,{issuer,transport:Object.freeze({execute:issuer.execute.bind(issuer),read:issuer.read.bind(issuer)})});return token;
}
function hierarchyTransport(issuer:XygGeoScaleBridge,token?:object){
 const captured=CAPTURED_TRANSPORTS.get(token??captureGeoHierarchyTransport(issuer));
 if(!captured||captured.issuer!==issuer)throw new TypeError('captured hierarchy issuer required');return captured.transport;
}
const OPERATION=Symbol('selected-hierarchy-operation');
type Phase='query'|'begin-uncertain'|'publication-uncertain'|'data'|'closed';
export type GeoHierarchyStats=NonNullable<ReturnType<typeof decodeGeoHierarchyReply>['hierarchyStats']>;
export class GeoHierarchyPublicationUncertain extends Error {constructor(){super('hierarchy publication ownership is uncertain; settle and dispose before reuse');this.name='GeoHierarchyPublicationUncertain';}}
function rustFailure(error:unknown){const e=error as {nativeCode?:unknown;wasmStatus?:unknown;name?:string;status?:unknown};return typeof e?.nativeCode==='number'||typeof e?.wasmStatus==='number'||e?.name==='XygWasmError'&&typeof e.status==='number';}
/** One issued State becomes Query then Data. No raw packet manufactures this guard. */
export class GeoSelectedHierarchyOperation {
 #phase:Phase='query';#active:Promise<unknown>|undefined;#abort:AbortController|undefined;#disposing:Promise<void>|undefined;#stats:GeoHierarchyStats|null=null;
 #admission:Promise<GeoSelectedHierarchyOperation>|undefined;#attempt:GeoAllocationAttempt|undefined;#closing=false;#issuanceReady=false;#retired=false;#queryDisposed=false;#dataDisposed=false;#claim:ReturnType<typeof claimGeoSelectedState>;#issuer:XygGeoScaleBridge;#index:bigint;
 #bridge:XygGeoScaleBridge;#handle:bigint;#sequence:bigint;#budget:XygGeoQueryBudget;#storage:GeoHierarchyStorage;#request:ArrayBuffer;#released:()=>void;#prepared:(frame:Awaited<ReturnType<typeof prepareGeoHierarchyScene>>,style:Uint8Array)=>void;
 constructor(bridge:XygGeoScaleBridge,input:{handle:bigint;sequence:bigint;budget:XygGeoQueryBudget;storage:GeoHierarchyStorage;request:ArrayBuffer;claim:ReturnType<typeof claimGeoSelectedState>;issuer:XygGeoScaleBridge;index:bigint;released:()=>void;prepared:(frame:Awaited<ReturnType<typeof prepareGeoHierarchyScene>>,style:Uint8Array)=>void},token:typeof OPERATION){
  if(token!==OPERATION)throw new TypeError('issued selected hierarchy operation required');
  this.#claim=input.claim;this.#issuer=input.issuer;this.#index=input.index;this.#phase='begin-uncertain';
  this.#bridge=Object.freeze({execute:bridge.execute.bind(bridge),read:bridge.read.bind(bridge)});this.#handle=input.handle;this.#sequence=input.sequence;this.#budget={...input.budget};this.#storage=Object.freeze({readChunk:input.storage.readChunk,readPage:input.storage.readPage,writePage:input.storage.writePage});this.#request=input.request.slice(0);this.#released=input.released;this.#prepared=input.prepared;
 }
 get handle(){return this.#handle;}get sequence(){return this.#sequence;}get hierarchyStats(){return this.#stats;}
 get request(){return this.#request.slice(0);}get closed(){return this.#phase==='closed';}
 enableAdmission(token:typeof OPERATION){if(token!==OPERATION)throw new TypeError('Issued hierarchy guard required');if(this.#isClosed())throw aborted();this.#issuanceReady=true;}
 abortUnissued(token:typeof OPERATION){if(token!==OPERATION||this.#attempt||this.#admission)throw new TypeError('Unissued hierarchy guard required');this.#claim.reject();this.#close();}
 /** Whole admission flight, exact replay and Confirm precede all query I/O. */
 recover(){if(!this.#issuanceReady)throw new Error('Hierarchy issuance callback has not settled');if(this.#closing||this.#isClosed())throw new Error('selected hierarchy operation closing');return this.#recoverAdmission();}
 #recoverAdmission(){
  if(this.#phase==='query'||this.#retired)return Promise.resolve(this);if(this.#admission)return this.#admission;
  const task=Promise.resolve().then(async()=>{
   if(!this.#attempt){if(this.#closing){this.#claim.reject();this.#close();throw aborted();}
    let issuer;try{issuer=selectedGeoAllocationIssuer(this.#issuer,this.#index);preflightSelectedGeoAllocation(issuer);this.#attempt=new GeoAllocationAttempt(issuer,this.#bridge,this.#request,this.#sequence,(request,run)=>withGeoWorkerMutationOutcome(this.#issuer,request,run));trackSelectedGeoAllocation(issuer,this.#attempt);}catch(error){this.#claim.reject();this.#close();throw error;}
   }
   try{const raw=await this.#attempt.recover(packet=>{const r=decodeGeoHierarchyReply(packet);if(r.code!==0||r.handle!==this.#handle||r.sequence!==this.#sequence)throw new TypeError('selected hierarchy begin ownership reply');return r.handle;});
    this.#claim.consume();this.#retired=raw===undefined;this.#phase='query';return this;
   }catch(error){if(this.#attempt.rejected){this.#claim.reject();this.#close();}else this.#claim.consume();throw error;}
  });this.#admission=task;task.finally(()=>{if(this.#admission===task)this.#admission=undefined;}).catch(()=>{});return task;
 }
 #isClosed(){return this.#phase==='closed';}
 #close(){this.#phase='closed';this.#released();}
 #run<T>(work:(signal:AbortSignal)=>Promise<T>,signal?:AbortSignal){
  if(this.#closing||this.#phase==='closed'||this.#phase==='data'||this.#active||this.#disposing)throw new Error('selected hierarchy operation unavailable');
  const abort=new AbortController();this.#abort=abort;const stop=()=>abort.abort();signal?.addEventListener('abort',stop,{once:true});if(signal?.aborted)stop();
  const task=Promise.resolve().then(async()=>{try{if(abort.signal.aborted)throw aborted();return await work(abort.signal);}finally{signal?.removeEventListener('abort',stop);this.#active=undefined;this.#abort=undefined;}});this.#active=task;return task;
 }
 drive(input:{signal?:AbortSignal}={}){return this.#run(async signal=>{
  if(this.#phase!=='query'||this.#retired)throw new GeoHierarchyPublicationUncertain();
  const result=await driveGeoHierarchy(this.#bridge,{...this.#storage,handle:this.#handle,sequence:this.#sequence,budget:this.#budget,signal});
  if(result.code!==19)throw new Error('selected hierarchy query did not complete');this.#stats=result.hierarchyStats;return result;
 },input.signal);}
 prepare(style:Uint8Array,input:{signal?:AbortSignal;budget?:XygGeoQueryBudget}={}){if(!(style instanceof Uint8Array)||style.byteLength!==48||style.buffer.byteLength>48)throw new TypeError('exact48-byte style required');style=style.slice();return this.#run(async signal=>{
  if(this.#phase==='begin-uncertain'||this.#retired)throw new GeoHierarchyPublicationUncertain();
  if(this.#phase==='publication-uncertain'){
   // Pure Query kind confirmation: a replaced Data never receives another44.
   let confirmed;try{confirmed=decodeGeoHierarchyReply(await this.#bridge.execute(encodeGeoHierarchyRequest({command:6,handle:this.#handle,sequence:this.#sequence,budget:this.#budget})));}catch{throw new GeoHierarchyPublicationUncertain();}
   if(confirmed.code!==19||confirmed.handle!==this.#handle||confirmed.sequence!==this.#sequence)throw new GeoHierarchyPublicationUncertain();
   this.#phase='query';this.#stats=confirmed.hierarchyStats;
  }
  if(!this.#stats)throw new Error('drive must complete before preparing selected hierarchy');
  if(signal.aborted)throw aborted();
  const frame=await prepareGeoHierarchyScene(this.#bridge,{handle:this.#handle,sequence:this.#sequence,budget:input.budget??this.#budget,style,command:44,
   onAttempt:()=>{this.#phase='publication-uncertain';},onReceipt:()=>{this.#phase='data';},onRelease:()=>{this.#dataDisposed=true;}});
  await this.#releaseBirth();
  if(signal.aborted){await frame.dispose();this.#close();throw aborted();}try{this.#prepared(frame,style);}catch(error){await frame.dispose();this.#close();throw error;}this.#close();return frame;
 },input.signal);}
 async #releaseBirth(){if(this.#attempt&&!this.#attempt.released){const live=await this.#attempt.probeRetirement(raw=>new DataView(raw).getBigUint64(16,true));if(live!==undefined)throw new Error('Hierarchy admission phase remains live');await this.#attempt.release();}}
 async cancel(){this.#abort?.abort();if(this.#active){await this.#active.catch(()=>{});return;}if(this.#phase==='query')await this.#bridge.execute(encodeGeoHierarchyRequest({command:9,handle:this.#handle,sequence:this.#sequence}));}
 dispose(){if(this.#isClosed())return Promise.resolve();if(!this.#issuanceReady){this.#claim.reject();this.#close();return Promise.resolve();}if(this.#disposing)return this.#disposing;this.#closing=true;
  const task=(async()=>{this.#abort?.abort();if(this.#admission)await this.#admission.catch(()=>{});if(this.#active)await this.#active.catch(()=>{});if(this.#isClosed())return;
   if(this.#phase==='begin-uncertain')await this.#recoverAdmission();if(this.#isClosed())return;
   // Attempt ambiguity is kept until Rust accepts exact Data/State0 or Queryseq disposal.
   if(this.#phase==='publication-uncertain'||this.#phase==='data')try{if(!this.#dataDisposed){const r=decodeGeoHierarchyReply(await this.#bridge.execute(encodeGeoHierarchyRequest({command:10,handle:this.#handle})));if(r.code!==0||r.handle!==this.#handle||r.sequence!==0n)throw new Error('hierarchy cleanup awaiting release');this.#dataDisposed=true;}await this.#releaseBirth();this.#close();return;}catch(error){if(this.#dataDisposed||!rustFailure(error))throw error;}
   if(!this.#queryDisposed){const r=decodeGeoHierarchyReply(await this.#bridge.execute(encodeGeoHierarchyRequest({command:10,handle:this.#handle,sequence:this.#sequence})));if(r.code!==0||r.handle!==this.#handle||r.sequence!==this.#sequence)throw new Error('hierarchy cleanup awaiting release');this.#queryDisposed=true;}await this.#releaseBirth();this.#close();
  })();this.#disposing=task;task.catch(()=>{if(this.#disposing===task)this.#disposing=undefined;});return task;
 }
}
const canonicalEnableAdmission=GeoSelectedHierarchyOperation.prototype.enableAdmission;
const canonicalAbortUnissued=GeoSelectedHierarchyOperation.prototype.abortUnissued;
const canonicalAdmissionRecover=GeoSelectedHierarchyOperation.prototype.recover;
const canonicalClosed=Object.getOwnPropertyDescriptor(GeoSelectedHierarchyOperation.prototype,'closed')!.get!;
export async function beginGeoSelectedHierarchy(bridge:XygGeoScaleBridge,input:{state:GeoSelectedState;handle:bigint;sequence:bigint;query:XygGeoScaleQuery;budget:XygGeoQueryBudget;storage:GeoHierarchyStorage;transportToken?:object;onIssued:(operation:GeoSelectedHierarchyOperation)=>void;onReleased:()=>void;onPrepared:(frame:Awaited<ReturnType<typeof prepareGeoHierarchyScene>>,style:Uint8Array)=>void}){
 const transport=hierarchyTransport(bridge,input.transportToken);const claim=claimGeoSelectedState(input.state,bridge);let operation:GeoSelectedHierarchyOperation|undefined;
 try{const payload=new Uint8Array(8);new DataView(payload.buffer).setBigUint64(0,claim.handle,true);
  const request=encodeGeoHierarchyRequest({command:43,handle:input.handle,sequence:input.sequence,query:input.query,budget:input.budget,payload});
  operation=new GeoSelectedHierarchyOperation(transport,{handle:claim.handle,sequence:input.sequence,budget:input.budget,storage:input.storage,request,claim,issuer:bridge,index:input.handle,released:input.onReleased,prepared:input.onPrepared},OPERATION);try{input.onIssued(operation);}catch(error){if(!canonicalClosed.call(operation))canonicalAbortUnissued.call(operation,OPERATION);throw error;}
  canonicalEnableAdmission.call(operation,OPERATION);
  return await canonicalAdmissionRecover.call(operation);
 }catch(error){if(!operation)claim.reject();throw error;}
}
