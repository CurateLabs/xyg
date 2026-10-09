/** Issued temporal-overview ownership (§27/§29/§34), never point provenance. */
import { geoSceneDataAuthority, encodeGeoScaleRequest } from './63_geo_source';
import type { XygGeoScaleBridge, XygGeoQueryBudget, XygGeoScaleQuery } from './63_geo_source';
import { encodeGeoOverviewRequest, decodeGeoOverviewReply, driveGeoOverview, parseGeoOverviewData, GeoOverviewUnsupportedSelected, validateGeoOverviewMutation, settleGeoOverviewLoan } from './67_geo_overview';
import type { GeoOverviewStorage } from './67_geo_overview';

export class GeoOverviewUncertainAllocation extends Error {
 readonly owner:GeoOverviewIndex|GeoOverviewQuery|GeoOverviewFrame;readonly cause:unknown;
 constructor(owner:GeoOverviewIndex|GeoOverviewQuery|GeoOverviewFrame,cause:unknown){super('Overview allocation confirmation is uncertain; no allocation retry or disposal is authorized');this.name='GeoOverviewUncertainAllocation';this.owner=owner;this.cause=cause;}
}
export class GeoOverviewCleanupPending extends Error {readonly owner:GeoOverviewIndex|GeoOverviewQuery|GeoOverviewFrame;readonly cause:unknown;constructor(owner:GeoOverviewIndex|GeoOverviewQuery|GeoOverviewFrame,cause:unknown){super('Overview Data cleanup remains pending; retry owner.dispose()');this.owner=owner;this.cause=cause;}}
export class GeoOverviewUnsupportedDomain extends Error {constructor(){super('Overview query domain is unsupported; no source scan was substituted');this.name='GeoOverviewUnsupportedDomain';}}
const closedStorage:GeoOverviewStorage={readChunk:async()=>{throw new Error('Closed overview storage');},readPage:async()=>{throw new Error('Closed overview storage');},writePage:async()=>{throw new Error('Closed overview storage');}};
const OWNER=Symbol("issued overview owner");
const indices=new WeakMap<GeoOverviewIndex,{bridge:XygGeoScaleBridge;transport:XygGeoScaleBridge;budget:XygGeoQueryBudget;creationSequence:bigint;handle:bigint;closed:boolean;header:Uint8Array}>();
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
 #handleValue=0n;#state:'building'|'ready'|'uncertain'|'closed'='building';#active:GeoOverviewQuery|undefined;#disposal:Promise<void>|undefined;
 #current:GeoOverviewFrame|undefined;#closing=false;
 #storage:GeoOverviewStorage;
 private constructor(cap:symbol,storage:GeoOverviewStorage,input:GeoOverviewBuildInput,sequence:bigint){if(cap!==OWNER)throw new TypeError("Issued overview constructor required");this.#storage=storage;this.#bridge=input.bridge;this.#transport=input.bridge;const b=input.budget;this.#budget=Object.freeze({processorBytes:b.processorBytes,maxRowsExamined:b.maxRowsExamined,maxReadBytes:b.maxReadBytes,maxChunks:b.maxChunks,pageRows:b.pageRows});this.#creationSequence=sequence;}
 static async fromFrame(frame:object,input:GeoOverviewBuildInput){
  const a=geoSceneDataAuthority(frame);if(!a||a.bridge!==input.bridge||(frame as {handle:bigint}).handle!==a.handle)throw new TypeError('overview build requires its privately issued SceneData transport and owner');
  if(a.selected)throw new GeoOverviewUnsupportedSelected();
  if(typeof input.maxVertices!=='bigint'||input.maxVertices<=0n||input.maxVertices>0xffffffffffffffffn)throw new TypeError('nonzero u64 vertex ceiling required');
  const owner=new GeoOverviewIndex(OWNER,{readChunk:input.readChunk,readPage:input.readPage,writePage:input.writePage},input,a.sequence);
  owner.#transport=Object.freeze({execute:a.execute.bind(a.bridge),read:a.read.bind(a.bridge)});
  indices.set(owner,{bridge:a.bridge,transport:owner.#transport,budget:owner.#budget,creationSequence:a.sequence,handle:0n,closed:false,header:a.header.slice()});
  const payload=new Uint8Array(8);new DataView(payload.buffer).setBigUint64(0,input.maxVertices,true);
  const request=encodeGeoOverviewRequest({command:27,handle:a.handle,sequence:a.sequence,budget:owner.#budget,payload});
  try{const r=decodeGeoOverviewReply(await owner.#transport.execute(request));if(r.code!==0||r.handle===0n||r.sequence!==a.sequence)throw new TypeError('invalid overview build receipt');owner.#handleValue=r.handle;indexOwner(owner).handle=r.handle;}
  catch(cause){owner.#state='uncertain';throw error(owner,cause);}
  try{const r=await driveGeoOverview(owner.#transport,{...owner.#storage,handle:owner.#handleValue,sequence:a.sequence,budget:owner.#budget});if(r.code!==13)throw new TypeError('overview build did not become a validated index');owner.#state='ready';return owner;}
  catch(cause){try{await canonicalIndexDispose.call(owner);}catch(cleanup){throw new GeoOverviewCleanupPending(owner,cleanup);}throw cause;}
 }
 get bridge(){return this.#bridge;}get budget(){return {...this.#budget};}get creationSequence(){return this.#creationSequence;}get current(){return this.#current;}
 get handle(){return this.#handleValue;}get closed(){return this.#state==='closed';}get pendingOperation():GeoOverviewIndex|GeoOverviewQuery|undefined{return this.#state==='uncertain'?this:this.#active;}
 async begin(query:XygGeoScaleQuery,{sequence}:{sequence:bigint}){
  if(this.#closing||this.#state!=='ready'||this.#active)throw new Error('Overview index is closed, busy or has unresolved allocation');
  const request=encodeGeoOverviewRequest({command:28,handle:this.#handleValue,sequence,budget:this.#budget,query});
  const operation=new GeoOverviewQuery(OWNER,this,request,sequence,this.#storage);this.#active=operation;
  await canonicalQueryAdmit.call(operation);return operation;
 }
 async update(query:XygGeoScaleQuery,input:{sequence:bigint;signal?:AbortSignal},cap?:symbol){
  const op=await canonicalIndexBegin.call(this,query,input);let frame:GeoOverviewFrame|undefined;
  try{await canonicalQueryDrive.call(op,input.signal);frame=await canonicalQueryPrepare.call(op,input.signal);await canonicalQueryDispose.call(op);if(input.signal?.aborted||this.#closing||this.#state!=='ready'){await canonicalFrameDispose.call(frame);throw abort();}if(cap!==OWNER)this.#current=frame;return frame;}
  catch(cause){if(frame){try{await canonicalFrameDispose.call(frame);}catch(cleanup){throw new GeoOverviewCleanupPending(frame,cleanup);}}if(!op.uncertain)await canonicalQueryDispose.call(op);throw cause;}
 }
 finished(op:GeoOverviewQuery,cap:symbol){if(cap!==OWNER)throw new TypeError("Private query settlement required");if(this.#active===op)this.#active=undefined;}
 async dispose(){
  if(this.#state==='closed')return;this.#closing=true;
  if(this.#state==='uncertain')throw error(this,new Error('Unknown builder owner requires protocol recovery'));
  if(this.#active)await canonicalQueryDispose.call(this.#active);
  await settleGeoOverviewLoan(this.#transport,this.#handleValue,this.#creationSequence);
  if(!this.#disposal)this.#disposal=this.#transport.execute(encodeGeoOverviewRequest({command:10,handle:this.#handleValue,sequence:this.#creationSequence})).then(packet=>{validateGeoOverviewMutation(packet,this.#handleValue,this.#creationSequence);this.#state='closed';this.#storage=closedStorage;indexOwner(this).closed=true;}).catch(cause=>{this.#disposal=undefined;throw cause;});
  return this.#disposal;
 }
}
export class GeoOverviewQuery {
 #handleValue=0n;#phase:'admitting'|'issued'|'complete'|'uncertain'|'closed'='admitting';#active:Promise<unknown>|undefined;#disposal:Promise<void>|undefined;
 #admission:Promise<void>|undefined;#publication:GeoOverviewFrame|undefined;
 #index:GeoOverviewIndex;#request:ArrayBuffer;#sequence:bigint;#storage:GeoOverviewStorage;
 constructor(cap:symbol,index:GeoOverviewIndex,request:ArrayBuffer,sequence:bigint,storage:GeoOverviewStorage){if(cap!==OWNER)throw new TypeError("Private issued query required");this.#index=index;this.#request=request;this.#sequence=sequence;this.#storage=storage;}
 get sequence(){return this.#sequence;}get handle(){return this.#handleValue;}get uncertain(){return this.#phase==='uncertain';}
 async admit(){if(this.#admission)return this.#admission;if(this.#phase!=='admitting')throw new Error('Query admission already settled');this.#admission=(async()=>{try{const r=decodeGeoOverviewReply(await indexOwner(this.#index).transport.execute(this.#request.slice(0)));if(r.code!==0||r.handle===0n||r.sequence!==this.#sequence)throw new TypeError('invalid overview query receipt');this.#handleValue=r.handle;this.#phase='issued';}catch(cause){this.#phase='uncertain';throw error(this,cause);}})();return this.#admission;}
 async drive(signal?:AbortSignal){
  if(this.#phase!=='issued'||this.#active)throw new Error('Overview query is not an idle issued operation');
  const active=driveGeoOverview(indexOwner(this.#index).transport,{...this.#storage,handle:this.#handleValue,sequence:this.#sequence,budget:indexOwner(this.#index).budget,signal});this.#active=active;
  try{const r=await active;if(r.code===15)throw new GeoOverviewUnsupportedDomain();if(r.code!==14)throw new TypeError('overview query did not complete');this.#phase='complete';}finally{this.#active=undefined;}
 }
 async prepare(signal?:AbortSignal){
  if(this.#phase!=='complete'||this.#active)throw new Error('Overview query is not complete');
  if(signal?.aborted)throw abort();
  const frame=new GeoOverviewFrame(OWNER,this.#index,this.#sequence,this.#request.slice(0));
  this.#publication=frame;const active=canonicalFramePublish.call(frame,this.#handleValue);this.#active=active;
  try{await active;if(signal?.aborted){await canonicalFrameDispose.call(frame);throw abort();}return frame;}
  catch(cause){if(frame.uncertain)this.#phase='uncertain';throw cause;}finally{this.#active=undefined;}
 }
 async dispose(){
  if(this.#phase==='closed')return;if(this.#admission){try{await this.#admission;}catch{}}if(this.#phase==='uncertain')throw error(this,new Error('Unknown query/Data owner requires protocol recovery'));
  if(this.#active){validateGeoOverviewMutation(await indexOwner(this.#index).transport.execute(encodeGeoOverviewRequest({command:9,handle:this.#handleValue,sequence:this.#sequence})),this.#handleValue,this.#sequence);try{await this.#active;}catch{} }
  if(this.#publication&&!this.#publication.published)await canonicalFrameDispose.call(this.#publication);await settleGeoOverviewLoan(indexOwner(this.#index).transport,this.#handleValue,this.#sequence);
  if(!this.#disposal)this.#disposal=indexOwner(this.#index).transport.execute(encodeGeoOverviewRequest({command:10,handle:this.#handleValue,sequence:this.#sequence})).then(packet=>{validateGeoOverviewMutation(packet,this.#handleValue,this.#sequence);this.#phase='closed';this.#storage=closedStorage;this.#publication=undefined;canonicalIndexFinished.call(this.#index,this,OWNER);}).catch(cause=>{this.#disposal=undefined;throw cause;});return this.#disposal;
 }
}
function samePlane(actual:Uint8Array,at:number,expected:Uint8Array,from:number,length:number){if(actual.subarray(at,at+length).some((n,i)=>n!==expected[from+i]))throw new TypeError('Overview Data differs from its private snapshot');}
function validateSnapshot(packet:ArrayBuffer,query:ArrayBuffer,index:GeoOverviewIndex){const b=new Uint8Array(packet),q=new Uint8Array(query),source=indexOwner(index).header;for(const [a,e,n] of [[96,64,4],[100,12,4],[112,80,56],[64,136,8],[56,144,8],[80,152,8],[176,160,40],[224,200,4],[232,208,16]])samePlane(b,a,q,e,n);for(const [a,e,n] of [[88,232,8],[76,240,4],[72,244,4]])samePlane(b,a,source,e,n);}
export class GeoOverviewFrame {
 #handleValue=0n;#value:ReturnType<typeof parseGeoOverviewData>|undefined;#phase:'new'|'owned'|'uncertain'|'closed'='new';#disposal:Promise<void>|undefined;
 #retention:GeoOverviewFrame|undefined;#index:GeoOverviewIndex;#sequence:bigint;#query:ArrayBuffer;
 constructor(cap:symbol,index:GeoOverviewIndex,sequence:bigint,query:ArrayBuffer){if(cap!==OWNER)throw new TypeError("Private issued frame required");this.#index=index;this.#sequence=sequence;this.#query=query;}
 get sequence(){return this.#sequence;}get handle(){return this.#handleValue;}get published(){return frames.has(this);}get closed(){return this.#phase==='closed';}get uncertain(){return this.#phase==='uncertain';}get data(){if(!this.#value)throw new Error('Overview frame disposed or unpublished');return this.#value;}
 async publish(queryHandle:bigint){if(this.#phase!=='new')throw new Error('Frame publication already attempted');this.#phase='uncertain';await this.issue(encodeGeoOverviewRequest({command:29,handle:queryHandle,sequence:this.#sequence,budget:indexOwner(this.#index).budget}),queryHandle);}
 private async issue(request:ArrayBuffer,sourceHandle:bigint){
  const expectedCode=new DataView(request).getUint32(8,true)===26?0:16;let expectedLength=0n;
  const issuer=indexOwner(this.#index).transport;
  try{const r=decodeGeoOverviewReply(await issuer.execute(request));if(r.code!==expectedCode||r.handle===0n||r.sequence!==this.#sequence||r.sourceHandle!==sourceHandle||r.dataLength>32n*1024n*1024n||4n*r.dataLength>BigInt(indexOwner(this.#index).budget.processorBytes))throw new TypeError('invalid overview Data receipt');expectedLength=r.dataLength;this.#handleValue=r.handle;this.#phase='owned';}
  catch(cause){this.#phase='uncertain';throw error(this,cause);}
  try{const packet=await issuer.read(encodeGeoOverviewRequest({command:23,handle:this.#handleValue,sequence:this.#sequence}));if(BigInt(packet.byteLength)!==expectedLength)throw new TypeError('overview Data length mismatch');validateSnapshot(packet,this.#query,this.#index);this.#value=parseGeoOverviewData(packet);if(this.#value.identity.queryHandle!==sourceHandle||this.#value.identity.sequence!==this.#sequence)throw new TypeError('overview publication sequence mismatch');frames.set(this,{bridge:indexOwner(this.#index).bridge,index:this.#index,handle:this.#handleValue,sequence:this.#sequence,query:this.#query.slice(0),header:new Uint8Array(packet,0,2304).slice()});}
  catch(cause){try{await canonicalFrameDispose.call(this);}catch(cleanup){throw new GeoOverviewCleanupPending(this,cleanup);}throw cause;}
 }
 async retain(){void this.data;if(this.#retention?.closed)this.#retention=undefined;if(this.#retention)throw error(this.#retention,new Error('Previous retained allocation remains unresolved'));const copy=new GeoOverviewFrame(OWNER,this.#index,this.#sequence,this.#query.slice(0));this.#retention=copy;await copy.issue(encodeGeoScaleRequest({command:26,handle:this.#handleValue,sequence:this.#sequence,budget:indexOwner(this.#index).budget}),this.#handleValue);this.#retention=undefined;return copy;}
 async dispose(){if(this.#phase==='closed')return;if(this.#phase==='uncertain')throw error(this,new Error('Unknown Data owner requires protocol recovery'));this.#value=undefined;frames.delete(this);if(!this.#disposal)this.#disposal=indexOwner(this.#index).transport.execute(encodeGeoOverviewRequest({command:10,handle:this.#handleValue,sequence:0n})).then(packet=>{validateGeoOverviewMutation(packet,this.#handleValue,0n);this.#phase='closed';}).catch(cause=>{this.#disposal=undefined;throw cause;});return this.#disposal;}
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

/** Internal controller publication has independent ownership, without a public current alias. */
export function updateOverviewIndex(index:GeoOverviewIndex,query:XygGeoScaleQuery,input:{sequence:bigint;signal?:AbortSignal}){indexOwner(index);return canonicalIndexUpdate.call(index,query,input,OWNER);}
const canonicalIndexUpdate=GeoOverviewIndex.prototype.update;
