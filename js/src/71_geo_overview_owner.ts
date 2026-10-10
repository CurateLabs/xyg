/** Issued temporal-overview ownership (§27/§29/§34), never point provenance. */
import { geoSceneDataAuthority, onGeoSceneDataDisposed, encodeGeoScaleRequest } from './63_geo_source';
import type { XygGeoScaleBridge, XygGeoQueryBudget, XygGeoScaleQuery } from './63_geo_source';
import { encodeGeoOverviewRequest, decodeGeoOverviewReply, driveGeoOverview, parseGeoOverviewData, GeoOverviewUnsupportedSelected, validateGeoOverviewMutation, settleGeoOverviewLoan } from './67_geo_overview';
import type { GeoOverviewStorage } from './67_geo_overview';
import {registerOverviewMembers,captureOverviewMembers,installOverviewMembers,dropOverviewMembers,overviewMembers} from './73_geo_overview_members';
import type {GeoOverviewMembersInput} from './73_geo_overview_members';
import {GeoAllocationAttempt,forgetGeoAllocationIssuer} from './72_geo_allocation_attempt';

export class GeoOverviewUncertainAllocation extends Error {
 readonly owner:GeoOverviewIndex|GeoOverviewQuery|GeoOverviewFrame;readonly cause:unknown;
 constructor(owner:GeoOverviewIndex|GeoOverviewQuery|GeoOverviewFrame,cause:unknown){super('Overview allocation confirmation is uncertain; retry owner.dispose() to settle its exact allocation receipt');this.name='GeoOverviewUncertainAllocation';this.owner=owner;this.cause=cause;}
}
export class GeoOverviewCleanupPending extends Error {readonly owner:GeoOverviewIndex|GeoOverviewQuery|GeoOverviewFrame;readonly cause:unknown;constructor(owner:GeoOverviewIndex|GeoOverviewQuery|GeoOverviewFrame,cause:unknown){super('Overview Data cleanup remains pending; retry owner.dispose()');this.owner=owner;this.cause=cause;}}
export class GeoOverviewUnsupportedDomain extends Error {constructor(){super('Overview query domain is unsupported; no source scan was substituted');this.name='GeoOverviewUnsupportedDomain';}}
const closedStorage:GeoOverviewStorage={readChunk:async()=>{throw new Error('Closed overview storage');},readPage:async()=>{throw new Error('Closed overview storage');},writePage:async()=>{throw new Error('Closed overview storage');}};
const OWNER=Symbol("issued overview owner");
const issuedKinds=new WeakMap<object,'index'|'query'|'frame'>();
const allocationIssuerHooks=new WeakSet<object>();
const indices=new WeakMap<GeoOverviewIndex,{bridge:XygGeoScaleBridge;transport:XygGeoScaleBridge;issuerExecute:XygGeoScaleBridge['execute'];budget:XygGeoQueryBudget;creationSequence:bigint;handle:bigint;closed:boolean;header:Uint8Array;reader:GeoOverviewStorage['readChunk']}>();
function indexOwner(index:GeoOverviewIndex){const a=indices.get(index);if(!a)throw new TypeError("Privately issued overview index required");return a;}
const frames=new WeakMap<GeoOverviewFrame,{bridge:XygGeoScaleBridge;index:GeoOverviewIndex;handle:bigint;sequence:bigint;query:ArrayBuffer;header:Uint8Array}>();
export function overviewIndexAuthority(index:GeoOverviewIndex){const a=indices.get(index);return a?Object.freeze({bridge:a.bridge,budget:a.budget,creationSequence:a.creationSequence,handle:a.handle,closed:a.closed,header:a.header.slice()}):undefined;}
export function overviewFrameAuthority(frame:GeoOverviewFrame){const a=frames.get(frame);return a?Object.freeze({...a,query:a.query.slice(0),header:a.header.slice()}):undefined;}
function error(owner:GeoOverviewIndex|GeoOverviewQuery|GeoOverviewFrame,cause:unknown){return new GeoOverviewUncertainAllocation(owner,cause);}
function abort(){return new DOMException('Overview operation aborted','AbortError');}
export interface GeoOverviewBuildInput extends GeoOverviewStorage {bridge:XygGeoScaleBridge;budget:XygGeoQueryBudget;maxVertices:bigint}

/** Independent immutable queries; there is no index-wide camera revision policy. */
export class GeoOverviewIndex {
 #budget:XygGeoQueryBudget;#bridge:XygGeoScaleBridge;#transport:XygGeoScaleBridge;#creationSequence:bigint;
 #recovery:Promise<GeoOverviewIndex>|undefined;#handleValue=0n;#state:'building'|'ready'|'uncertain'|'closed'='building';#active:GeoOverviewQuery|undefined;#disposal:Promise<void>|undefined;
 #current:GeoOverviewFrame|undefined;#closing=false;#attempt:GeoAllocationAttempt|undefined;#disposed=false;#disposeAttempted=false;
 #storage:GeoOverviewStorage;
 private constructor(cap:symbol,storage:GeoOverviewStorage,input:GeoOverviewBuildInput,sequence:bigint){if(cap!==OWNER)throw new TypeError("Issued overview constructor required");issuedKinds.set(this,'index');this.#storage=storage;this.#bridge=input.bridge;this.#transport=input.bridge;const b=input.budget;this.#budget=Object.freeze({processorBytes:b.processorBytes,maxRowsExamined:b.maxRowsExamined,maxReadBytes:b.maxReadBytes,maxChunks:b.maxChunks,pageRows:b.pageRows});this.#creationSequence=sequence;}
 static async fromFrame(frame:object,input:GeoOverviewBuildInput){
  const a=geoSceneDataAuthority(frame);if(!a||a.bridge!==input.bridge||(frame as {handle:bigint}).handle!==a.handle)throw new TypeError('overview build requires its privately issued SceneData transport and owner');
  if(a.selected)throw new GeoOverviewUnsupportedSelected();
  if(typeof input.maxVertices!=='bigint'||input.maxVertices<=0n||input.maxVertices>0xffffffffffffffffn)throw new TypeError('nonzero u64 vertex ceiling required');
  const owner=new GeoOverviewIndex(OWNER,{readChunk:input.readChunk,readPage:input.readPage,writePage:input.writePage},input,a.sequence);
  owner.#transport=Object.freeze({execute:a.execute.bind(a.bridge),read:a.read.bind(a.bridge)});
  indices.set(owner,{bridge:a.bridge,transport:owner.#transport,issuerExecute:a.execute,budget:owner.#budget,creationSequence:a.sequence,handle:0n,closed:false,header:a.header.slice(),reader:input.readChunk});
  const payload=new Uint8Array(8);new DataView(payload.buffer).setBigUint64(0,input.maxVertices,true);
  const request=encodeGeoOverviewRequest({command:27,handle:a.handle,sequence:a.sequence,budget:owner.#budget,payload});
  owner.#attempt=new GeoAllocationAttempt(frame,owner.#transport,request);if(!allocationIssuerHooks.has(frame)){onGeoSceneDataDisposed(frame,()=>forgetGeoAllocationIssuer(frame));allocationIssuerHooks.add(frame);}
  try{await owner.recoverAllocation();}
  catch(cause){if(owner.#attempt.rejected){owner.#state='closed';indexOwner(owner).closed=true;throw cause;}owner.#state='uncertain';throw error(owner,cause);}
  try{const r=await driveGeoOverview(owner.#transport,{...owner.#storage,handle:owner.#handleValue,sequence:a.sequence,budget:owner.#budget});if(r.code!==13)throw new TypeError('overview build did not become a validated index');owner.#state='ready';return owner;}
  catch(cause){try{await canonicalIndexDispose.call(owner);}catch(cleanup){throw new GeoOverviewCleanupPending(owner,cleanup);}throw cause;}
 }
 private async recoverAllocation(){const packet=await this.#attempt!.recover(packet=>{const r=decodeGeoOverviewReply(packet);if(r.code!==0||r.handle===0n||r.sequence!==this.#creationSequence)throw new TypeError('invalid overview build receipt');return r.handle;});if(!packet){this.#state='closed';indexOwner(this).closed=true;return;}const r=decodeGeoOverviewReply(packet);this.#handleValue=r.handle;indexOwner(this).handle=r.handle;if(this.#state==='uncertain')this.#state='building';}
 recover(){if(this.#recovery)return this.#recovery;const task=Promise.resolve().then(()=>this.recoverOnce());this.#recovery=task;void task.finally(()=>{if(this.#recovery===task)this.#recovery=undefined;}).catch(()=>{});return task;}
 private async recoverOnce(){if(this.#closing||this.#state==='closed')throw new Error('Overview index closed');if(this.#state==='uncertain')await this.recoverAllocation();if(this.closed)throw new Error('Overview allocation retired');if(this.#state==='building'){const r=await driveGeoOverview(this.#transport,{...this.#storage,handle:this.#handleValue,sequence:this.#creationSequence,budget:this.#budget});if(r.code!==13)throw new TypeError('Overview build did not complete');if(this.#closing)throw new Error('Overview index closing');this.#state='ready';}return this;}
 get bridge(){return this.#bridge;}get budget(){return {...this.#budget};}get creationSequence(){return this.#creationSequence;}get current(){return this.#current;}
 get handle(){return this.#handleValue;}get closed(){return this.#state==='closed';}get pendingOperation():GeoOverviewIndex|GeoOverviewQuery|undefined{return this.#state==='uncertain'?this:this.#active;}
 async begin(query:XygGeoScaleQuery,{sequence,onIssued}:{sequence:bigint;onIssued?:(operation:GeoOverviewQuery)=>void}){
  if(this.#closing||this.#state!=='ready'||this.#active)throw new Error('Overview index is closed, busy or has unresolved allocation');
  const request=encodeGeoOverviewRequest({command:28,handle:this.#handleValue,sequence,budget:this.#budget,query});
  const operation=new GeoOverviewQuery(OWNER,this,request,sequence,this.#storage);this.#active=operation;onIssued?.(operation);
  await canonicalQueryAdmit.call(operation);return operation;
 }
 async update(query:XygGeoScaleQuery,input:{sequence:bigint;signal?:AbortSignal;onIssued?:(operation:GeoOverviewQuery)=>void},cap?:symbol){
  const op=await canonicalIndexBegin.call(this,query,input);let frame:GeoOverviewFrame|undefined;
  try{await canonicalQueryDrive.call(op,input.signal);frame=await canonicalQueryPrepare.call(op,input.signal);await canonicalQueryDispose.call(op);if(input.signal?.aborted||this.#closing||this.#state!=='ready'){await canonicalFrameDispose.call(frame);throw abort();}if(cap!==OWNER)this.#current=frame;return frame;}
  catch(cause){if(frame){try{await canonicalFrameDispose.call(frame);}catch(cleanup){op.holdCleanup(frame,OWNER);throw new GeoOverviewCleanupPending(frame,cleanup);}}if(!op.uncertain)await canonicalQueryDispose.call(op);throw cause;}
 }
 finished(op:GeoOverviewQuery,cap:symbol){if(cap!==OWNER)throw new TypeError("Private query settlement required");if(this.#active===op)this.#active=undefined;}
 async dispose(){
  if(this.#state==='closed'){await forgetGeoAllocationIssuer(this);return;}this.#closing=true;if(this.#recovery)await this.#recovery.catch(()=>{});
  if(this.#state==='uncertain'){await this.recoverAllocation();if(this.closed){await this.#attempt!.release();await forgetGeoAllocationIssuer(this);return;}}
  if(this.#active)await canonicalQueryDispose.call(this.#active);
  await settleGeoOverviewLoan(this.#transport,this.#handleValue,this.#creationSequence);
  if(!this.#disposal)this.#disposal=Promise.resolve().then(async()=>{if(this.#disposeAttempted&&!this.#disposed){if(!await this.#attempt!.probeRetirement(packet=>decodeGeoOverviewReply(packet).handle))this.#disposed=true;}if(!this.#disposed){this.#disposeAttempted=true;validateGeoOverviewMutation(await this.#transport.execute(encodeGeoOverviewRequest({command:10,handle:this.#handleValue,sequence:this.#creationSequence})),this.#handleValue,this.#creationSequence);this.#disposed=true;}await this.#attempt!.release();await forgetGeoAllocationIssuer(this);this.#state='closed';this.#storage=closedStorage;indexOwner(this).closed=true;indexOwner(this).reader=closedStorage.readChunk;}).catch(cause=>{this.#disposal=undefined;throw cause;});
  return this.#disposal;
 }
}
export class GeoOverviewQuery {
 #cleanupFrame:GeoOverviewFrame|undefined;#handleValue=0n;#phase:'admitting'|'issued'|'complete'|'uncertain'|'closed'='admitting';#active:Promise<unknown>|undefined;#disposal:Promise<void>|undefined;
 #admission:Promise<void>|undefined;#publication:GeoOverviewFrame|undefined;#attempt:GeoAllocationAttempt;#consumed=false;#disposed=false;#disposeAttempted=false;#closing=false;
 #index:GeoOverviewIndex;#request:ArrayBuffer;#sequence:bigint;#storage:GeoOverviewStorage;
 constructor(cap:symbol,index:GeoOverviewIndex,request:ArrayBuffer,sequence:bigint,storage:GeoOverviewStorage){if(cap!==OWNER)throw new TypeError("Private issued query required");issuedKinds.set(this,'query');this.#index=index;this.#request=request;this.#sequence=sequence;this.#storage=storage;this.#attempt=new GeoAllocationAttempt(index,indexOwner(index).transport,request);}
 get closed(){return this.#phase==='closed';}get sequence(){return this.#sequence;}get handle(){return this.#handleValue;}get uncertain(){return this.#phase==='uncertain';}
 async admit(){if(this.#admission)return this.#admission;if(this.#phase!=='admitting'&&this.#phase!=='uncertain')throw new Error('Query admission already settled');return this.#admission=Promise.resolve().then(async()=>{try{const packet=await this.#attempt.recover(packet=>{const r=decodeGeoOverviewReply(packet);if(r.code!==0||r.handle===0n||r.sequence!==this.#sequence)throw new TypeError('invalid overview query receipt');return r.handle;});if(!packet){this.#phase='closed';canonicalIndexFinished.call(this.#index,this,OWNER);return;}this.#handleValue=decodeGeoOverviewReply(packet).handle;this.#phase='issued';}catch(cause){this.#admission=undefined;if(this.#attempt.rejected){this.#phase='closed';canonicalIndexFinished.call(this.#index,this,OWNER);throw cause;}this.#phase='uncertain';throw error(this,cause);}});}

 async recover(){if(this.#closing||this.#phase==='closed')throw new Error('Overview query closed');if(this.#publication){const frame=await canonicalFrameRecover.call(this.#publication);if(this.#closing||this.closed)throw new Error('Overview query closed');this.#consumed=frame.consumed;this.#phase='complete';return frame;}await canonicalQueryAdmit.call(this);if(this.closed)throw new Error('Overview allocation retired');return this;}
 async drive(signal?:AbortSignal){
  if(this.#closing||this.#phase!=='issued'||this.#active)throw new Error('Overview query is not an idle issued operation');
  const active=driveGeoOverview(indexOwner(this.#index).transport,{...this.#storage,handle:this.#handleValue,sequence:this.#sequence,budget:indexOwner(this.#index).budget,signal});this.#active=active;
  try{const r=await active;if(r.code===15)throw new GeoOverviewUnsupportedDomain();if(r.code!==14)throw new TypeError('overview query did not complete');this.#phase='complete';}finally{this.#active=undefined;}
 }
 async prepare(signal?:AbortSignal){
  if(this.#closing||this.#phase!=='complete'||this.#active||this.#publication||this.#consumed)throw new Error('Overview query is not complete or already published');
  if(signal?.aborted)throw abort();
  const frame=new GeoOverviewFrame(OWNER,this.#index,this.#sequence,this.#request.slice(0));
  this.#publication=frame;const active=canonicalFramePublish.call(frame,this.#handleValue,this);this.#active=active;
  try{await active;this.#consumed=frame.consumed;if(signal?.aborted){await canonicalFrameDispose.call(frame);throw abort();}return frame;}
  catch(cause){if(frame.rejected){this.#phase='complete';this.#publication=undefined;}else if(frame.uncertain)this.#phase='uncertain';throw cause;}finally{this.#consumed=frame.consumed;this.#active=undefined;}
 }
 holdCleanup(frame:GeoOverviewFrame,cap:symbol){if(cap!==OWNER||frame!==this.#publication)throw new TypeError('Private publication cleanup required');this.#cleanupFrame=frame;}
 async dispose(){
  if(this.#cleanupFrame){await canonicalFrameDispose.call(this.#cleanupFrame);this.#cleanupFrame=undefined;}if(this.#phase==='closed')return;this.#closing=true;if(this.#phase==='admitting')await canonicalQueryAdmit.call(this);if(this.#admission){try{await this.#admission;}catch{}}if(this.#phase==='uncertain'){if(this.#publication){if(!this.#publication.published)await canonicalFrameDispose.call(this.#publication);this.#consumed=this.#publication.consumed;}else await canonicalQueryAdmit.call(this);if(this.closed)return;}
  if(this.#active){if(!this.#publication)validateGeoOverviewMutation(await indexOwner(this.#index).transport.execute(encodeGeoOverviewRequest({command:9,handle:this.#handleValue,sequence:this.#sequence})),this.#handleValue,this.#sequence);try{await this.#active;}catch{}this.#consumed=this.#publication?.consumed??false;}
  if(this.#publication&&!this.#publication.published)await canonicalFrameDispose.call(this.#publication);if(this.#consumed){await this.#attempt.release();await forgetGeoAllocationIssuer(this);this.#phase='closed';this.#storage=closedStorage;canonicalIndexFinished.call(this.#index,this,OWNER);return;}await settleGeoOverviewLoan(indexOwner(this.#index).transport,this.#handleValue,this.#sequence);
  if(!this.#disposal)this.#disposal=Promise.resolve().then(async()=>{if(this.#disposeAttempted&&!this.#disposed){if(!await this.#attempt!.probeRetirement(packet=>decodeGeoOverviewReply(packet).handle))this.#disposed=true;}if(!this.#disposed){this.#disposeAttempted=true;validateGeoOverviewMutation(await indexOwner(this.#index).transport.execute(encodeGeoOverviewRequest({command:10,handle:this.#handleValue,sequence:this.#sequence})),this.#handleValue,this.#sequence);this.#disposed=true;}await this.#attempt!.release();await forgetGeoAllocationIssuer(this);this.#phase='closed';this.#storage=closedStorage;this.#publication=undefined;canonicalIndexFinished.call(this.#index,this,OWNER);}).catch(cause=>{this.#disposal=undefined;throw cause;});return this.#disposal;
 }
}
function samePlane(actual:Uint8Array,at:number,expected:Uint8Array,from:number,length:number){if(actual.subarray(at,at+length).some((n,i)=>n!==expected[from+i]))throw new TypeError('Overview Data differs from its private snapshot');}
function validateSnapshot(packet:ArrayBuffer,query:ArrayBuffer,index:GeoOverviewIndex){const b=new Uint8Array(packet),q=new Uint8Array(query),source=indexOwner(index).header;for(const [a,e,n] of [[96,64,4],[100,12,4],[112,80,56],[64,136,8],[56,144,8],[80,152,8],[176,160,40],[224,200,4],[232,208,16]])samePlane(b,a,q,e,n);for(const [a,e,n] of [[88,232,8],[76,240,4],[72,244,4]])samePlane(b,a,source,e,n);}
export class GeoOverviewFrame {
 #canonicalPacket:ArrayBuffer|undefined;#inspected=false;#handleValue=0n;#value:ReturnType<typeof parseGeoOverviewData>|undefined;#phase:'new'|'owned'|'uncertain'|'closed'='new';#disposal:Promise<void>|undefined;
 #recovery:Promise<GeoOverviewFrame>|undefined;#closing=false;#attempt:GeoAllocationAttempt|undefined;#expectedCode=16;#sourceHandle=0n;#consumed=false;#disposed=false;#disposeAttempted=false;#membershipCapture:object|undefined;#retention:GeoOverviewFrame|undefined;#index:GeoOverviewIndex;#sequence:bigint;#query:ArrayBuffer;
 constructor(cap:symbol,index:GeoOverviewIndex,sequence:bigint,query:ArrayBuffer){if(cap!==OWNER)throw new TypeError("Private issued frame required");issuedKinds.set(this,'frame');this.#index=index;this.#sequence=sequence;this.#query=query;}
 get rejected(){return this.#attempt?.rejected??false;}get consumed(){return this.#consumed;}get sequence(){return this.#sequence;}get handle(){return this.#handleValue;}get published(){return frames.has(this);}get closed(){return this.#phase==='closed';}get uncertain(){return this.#phase==='uncertain';}get data(){if(!this.#value)throw new Error('Overview frame disposed or unpublished');return this.#value;}
 async publish(queryHandle:bigint,queryOwner:object){if(this.#phase!=='new')throw new Error('Frame publication already attempted');this.#phase='uncertain';await this.issue(encodeGeoOverviewRequest({command:29,handle:queryHandle,sequence:this.#sequence,budget:indexOwner(this.#index).budget}),queryHandle,queryOwner);}
 private issue(request:ArrayBuffer,sourceHandle:bigint,issuerOwner:object,onIssued?:()=>void){const task=Promise.resolve().then(async()=>{onIssued?.();await this.issueOnce(request,sourceHandle,issuerOwner);return this;});this.#recovery=task;void task.finally(()=>{if(this.#recovery===task)this.#recovery=undefined;}).catch(()=>{});return task;}
 private async issueOnce(request:ArrayBuffer,sourceHandle:bigint,issuerOwner:object){
  if(this.#closing||this.closed)throw new Error('Overview frame closing');
  const expectedCode=new DataView(request).getUint32(8,true)===26?0:16;let expectedLength=0n;
  const issuer=indexOwner(this.#index).transport;this.#expectedCode=expectedCode;this.#sourceHandle=sourceHandle;this.#attempt=new GeoAllocationAttempt(issuerOwner,issuer,request);
  try{const packet=await this.recoverAllocation();if(!packet)throw new Error('Overview allocation retired');const r=decodeGeoOverviewReply(packet);if(r.code!==expectedCode||r.handle===0n||r.sequence!==this.#sequence||r.sourceHandle!==sourceHandle||r.dataLength>32n*1024n*1024n||4n*r.dataLength>BigInt(indexOwner(this.#index).budget.processorBytes))throw new TypeError('invalid overview Data receipt');expectedLength=r.dataLength;this.#handleValue=r.handle;this.#phase='owned';}
  catch(cause){if(this.#attempt.rejected||this.closed){this.#phase='closed';throw cause;}this.#phase='uncertain';throw error(this,cause);}
  try{if(this.#closing)throw new Error('Overview frame closing');await this.readAllocated(expectedLength);}
  catch(cause){this.#recovery=undefined;try{await canonicalFrameDispose.call(this);}catch(cleanup){throw new GeoOverviewCleanupPending(this,cleanup);}throw cause;}
 }
 private async recoverAllocation(){const packet=await this.#attempt!.recover(packet=>{const r=decodeGeoOverviewReply(packet);if(r.code!==this.#expectedCode||r.handle===0n||r.sequence!==this.#sequence||r.sourceHandle!==this.#sourceHandle||r.dataLength>32n*1024n*1024n||4n*r.dataLength>BigInt(indexOwner(this.#index).budget.processorBytes))throw new TypeError('invalid overview Data receipt');return r.handle;});if(!packet){this.#phase='closed';this.#consumed=this.#expectedCode===16&&this.#attempt!.retired;return;}this.#handleValue=decodeGeoOverviewReply(packet).handle;this.#phase='owned';if(this.#expectedCode===16)this.#consumed=true;return packet;}
 private async readAllocated(expectedLength:bigint){const packet=await indexOwner(this.#index).transport.read(encodeGeoOverviewRequest({command:23,handle:this.#handleValue,sequence:this.#sequence}));if(BigInt(packet.byteLength)!==expectedLength)throw new TypeError('overview Data length mismatch');validateSnapshot(packet,this.#query,this.#index);if(this.#closing)throw new Error('Overview frame closing');this.#canonicalPacket=packet.slice(0);this.#value=parseGeoOverviewData(packet);if(this.#value.identity.queryHandle!==this.#sourceHandle||this.#value.identity.sequence!==this.#sequence)throw new TypeError('overview publication sequence mismatch');frames.set(this,{bridge:indexOwner(this.#index).bridge,index:this.#index,handle:this.#handleValue,sequence:this.#sequence,query:this.#query.slice(0),header:new Uint8Array(packet,0,2304).slice()});if(this.#membershipCapture){installOverviewMembers(this.#membershipCapture,this,this.#handleValue,this.#sequence);this.#membershipCapture=undefined;}else registerOverviewMembers(this,indexOwner(this.#index).transport,indexOwner(this.#index).reader as never,indexOwner(this.#index).budget,new Uint8Array(packet,0,2304),this.#handleValue,this.#sequence,indexOwner(this.#index).bridge,indexOwner(this.#index).issuerExecute);}
 recover(){if(this.#recovery)return this.#recovery;const task=Promise.resolve().then(()=>this.recoverOnce());this.#recovery=task;void task.finally(()=>{if(this.#recovery===task)this.#recovery=undefined;}).catch(()=>{});return task;}
 private async recoverOnce(){if(this.#closing||this.#disposeAttempted||this.#disposed||this.#phase==='closed')throw new Error('Overview frame closed');if(this.#value)return this;const packet=await this.recoverAllocation();if(!packet)throw new Error('Overview allocation retired');try{await this.readAllocated(decodeGeoOverviewReply(packet).dataLength);if(this.#closing)throw new Error('Overview frame closing');}catch(cause){this.#recovery=undefined;try{await canonicalFrameDispose.call(this);}catch(cleanup){throw new GeoOverviewCleanupPending(this,cleanup);}throw cause;}return this;}
 inspect(cap:symbol){if(cap!==OWNER||this.#closing||this.closed||!this.#canonicalPacket||this.#inspected)throw new Error('Private overview inspection unavailable');this.#inspected=true;return parseGeoOverviewData(this.#canonicalPacket.slice(0));}
 members(cell:number,input:GeoOverviewMembersInput){void this.data;return overviewMembers(this,cell,input);}
 async retain(onIssued?:((frame:GeoOverviewFrame)=>void),cap?:symbol){if(this.#closing||this.closed)throw new Error('Overview frame closing');void this.data;if(this.#retention?.closed||this.#retention?.published)this.#retention=undefined;if(this.#retention)throw error(this.#retention,new Error('Previous retained allocation remains unresolved'));const copy=new GeoOverviewFrame(OWNER,this.#index,this.#sequence,this.#query.slice(0));this.#retention=copy;copy.#membershipCapture=captureOverviewMembers(this);await copy.issue(encodeGeoScaleRequest({command:26,handle:this.#handleValue,sequence:this.#sequence,budget:indexOwner(this.#index).budget}),this.#handleValue,this,cap===OWNER?()=>onIssued?.(copy):undefined);this.#retention=undefined;return copy;}
 async dispose(){if(this.#phase==='closed'){await this.#attempt?.release();await forgetGeoAllocationIssuer(this);return;}this.#closing=true;if(this.#recovery)await this.#recovery.catch(()=>{});if(this.closed)return;if(this.#phase==='new'){this.#phase='closed';return;}if(this.#phase==='uncertain'){await this.recoverAllocation();if(this.closed){await this.#attempt!.release();await forgetGeoAllocationIssuer(this);return;}}this.#value=undefined;this.#canonicalPacket=undefined;frames.delete(this);dropOverviewMembers(this);this.#membershipCapture=undefined;if(!this.#disposal)this.#disposal=Promise.resolve().then(async()=>{if(this.#disposeAttempted&&!this.#disposed){if(!await this.#attempt!.probeRetirement(packet=>decodeGeoOverviewReply(packet).handle))this.#disposed=true;}if(!this.#disposed){this.#disposeAttempted=true;validateGeoOverviewMutation(await indexOwner(this.#index).transport.execute(encodeGeoOverviewRequest({command:10,handle:this.#handleValue,sequence:0n})),this.#handleValue,0n);this.#disposed=true;}await this.#attempt!.release();await forgetGeoAllocationIssuer(this);this.#phase='closed';}).catch(cause=>{this.#disposal=undefined;throw cause;});return this.#disposal;}
}

// Canonical issued dispatch is captured once; public method edits cannot switch producer policy.
const canonicalIndexBegin=GeoOverviewIndex.prototype.begin;
const canonicalIndexDispose=GeoOverviewIndex.prototype.dispose;
const canonicalIndexFinished=GeoOverviewIndex.prototype.finished;
const canonicalQueryAdmit=GeoOverviewQuery.prototype.admit;
const canonicalQueryDrive=GeoOverviewQuery.prototype.drive;
const canonicalQueryPrepare=GeoOverviewQuery.prototype.prepare;
const canonicalQueryDispose=GeoOverviewQuery.prototype.dispose;
const canonicalFramePublish=GeoOverviewFrame.prototype.publish;
const canonicalFrameDispose=GeoOverviewFrame.prototype.dispose;
const canonicalFrameRecover=GeoOverviewFrame.prototype.recover;

/** Internal controller publication has independent ownership, without a public current alias. */
export function updateOverviewIndex(index:GeoOverviewIndex,query:XygGeoScaleQuery,input:{sequence:bigint;signal?:AbortSignal;onIssued?:(operation:GeoOverviewQuery)=>void}){indexOwner(index);return canonicalIndexUpdate.call(index,query,input,OWNER);}
const canonicalIndexUpdate=GeoOverviewIndex.prototype.update;

/** Internal host retained-copy guard, issued before allocation26. */
export function retainOverviewFrame(frame:GeoOverviewFrame,onIssued?:(copy:GeoOverviewFrame)=>void){if(!frames.has(frame))throw new TypeError("Privately issued overview frame required");return canonicalFrameRetain.call(frame,onIssued,OWNER);}
const canonicalFrameRetain=GeoOverviewFrame.prototype.retain;

/** Internal authentic ownership settlement, independent of public methods. */
export function closeOverviewOwner(owner:object):Promise<void>{const kind=issuedKinds.get(owner);if(kind==='index')return canonicalIndexDispose.call(owner as GeoOverviewIndex);if(kind==='query')return canonicalQueryDispose.call(owner as GeoOverviewQuery);if(kind==='frame')return canonicalFrameDispose.call(owner as GeoOverviewFrame);throw new TypeError('Privately issued overview owner required');}
export function getOverviewFrameData(frame:GeoOverviewFrame){if(issuedKinds.get(frame)!=='frame')throw new TypeError('Privately issued overview frame required');return canonicalFrameInspect.call(frame,OWNER);}
const canonicalFrameInspect=GeoOverviewFrame.prototype.inspect;
