// Mechanical shared71 type stripping; native export is a thin bridge.
/** Issued temporal-overview ownership (§27/§29/§34), never point provenance. */
import { geoSceneDataAuthority, onGeoSceneDataDisposed, encodeGeoScaleRequest } from './geoscale.js';

import { encodeGeoOverviewRequest, decodeGeoOverviewReply, driveGeoOverview, parseGeoOverviewData, GeoOverviewUnsupportedSelected, validateGeoOverviewMutation, settleGeoOverviewLoan } from './geo-overview.js';

import {registerOverviewMembers,captureOverviewMembers,installOverviewMembers,dropOverviewMembers,overviewMembers} from './geo-overview-members.js';

import {GeoAllocationAttempt,forgetGeoAllocationIssuer} from './geo-allocation-attempt.js';

export class GeoOverviewUncertainAllocation extends Error {
          owner                                                   ;         cause        ;
 constructor(owner                                                   ,cause        ){super('Overview allocation confirmation is uncertain; retry owner.dispose() to settle its exact allocation receipt');this.name='GeoOverviewUncertainAllocation';this.owner=owner;this.cause=cause;}
}
export class GeoOverviewCleanupPending extends Error {         owner                                                   ;         cause        ;constructor(owner                                                   ,cause        ){super('Overview Data cleanup remains pending; retry owner.dispose()');this.owner=owner;this.cause=cause;}}
export class GeoOverviewUnsupportedDomain extends Error {constructor(){super('Overview query domain is unsupported; no source scan was substituted');this.name='GeoOverviewUnsupportedDomain';}}
const closedStorage                   ={readChunk:async()=>{throw new Error('Closed overview storage');},readPage:async()=>{throw new Error('Closed overview storage');},writePage:async()=>{throw new Error('Closed overview storage');}};
const OWNER=Symbol("issued overview owner");
const issuedKinds=new WeakMap                                ();
const allocationIssuerHooks=new WeakSet        ();
const indices=new WeakMap                                                                                                                                                                                                                                                           ();
function indexOwner(index                 ){const a=indices.get(index);if(!a)throw new TypeError("Privately issued overview index required");return a;}
const frames=new WeakMap                                                                                                                                      ();
export function overviewIndexAuthority(index                 ){const a=indices.get(index);return a?Object.freeze({bridge:a.bridge,budget:a.budget,creationSequence:a.creationSequence,handle:a.handle,closed:a.closed,header:a.header.slice()}):undefined;}
export function overviewFrameAuthority(frame                 ){const a=frames.get(frame);return a?Object.freeze({...a,query:a.query.slice(0),header:a.header.slice()}):undefined;}
function error(owner                                                   ,cause        ){return new GeoOverviewUncertainAllocation(owner,cause);}
function abort(){return new DOMException('Overview operation aborted','AbortError');}


/** Independent immutable queries; there is no index-wide camera revision policy. */
export class GeoOverviewIndex {
 #budget                  ;#bridge                  ;#transport                  ;#creationSequence       ;
 #recovery                                    ;#handleValue=0n;#state                                        ='building';#active                           ;#disposal                        ;
 #current                           ;#closing=false;#attempt                               ;#disposed=false;#disposeAttempted=false;
 #storage                   ;
         constructor(cap       ,storage                   ,input                      ,sequence       ){if(cap!==OWNER)throw new TypeError("Issued overview constructor required");issuedKinds.set(this,'index');this.#storage=storage;this.#bridge=input.bridge;this.#transport=input.bridge;const b=input.budget;this.#budget=Object.freeze({processorBytes:b.processorBytes,maxRowsExamined:b.maxRowsExamined,maxReadBytes:b.maxReadBytes,maxChunks:b.maxChunks,pageRows:b.pageRows});this.#creationSequence=sequence;}
 static async fromFrame(frame       ,input                      ){
  const a=geoSceneDataAuthority(frame);if(!a||a.bridge!==input.bridge||(frame                   ).handle!==a.handle)throw new TypeError('overview build requires its privately issued SceneData transport and owner');
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
         async recoverAllocation(){const packet=await this.#attempt .recover(packet=>{const r=decodeGeoOverviewReply(packet);if(r.code!==0||r.handle===0n||r.sequence!==this.#creationSequence)throw new TypeError('invalid overview build receipt');return r.handle;});if(!packet){this.#state='closed';indexOwner(this).closed=true;return;}const r=decodeGeoOverviewReply(packet);this.#handleValue=r.handle;indexOwner(this).handle=r.handle;if(this.#state==='uncertain')this.#state='building';}
 recover(){if(this.#recovery)return this.#recovery;const task=Promise.resolve().then(()=>this.recoverOnce());this.#recovery=task;void task.finally(()=>{if(this.#recovery===task)this.#recovery=undefined;}).catch(()=>{});return task;}
         async recoverOnce(){if(this.#closing||this.#state==='closed')throw new Error('Overview index closed');if(this.#state==='uncertain')await this.recoverAllocation();if(this.closed)throw new Error('Overview allocation retired');if(this.#state==='building'){const r=await driveGeoOverview(this.#transport,{...this.#storage,handle:this.#handleValue,sequence:this.#creationSequence,budget:this.#budget});if(r.code!==13)throw new TypeError('Overview build did not complete');if(this.#closing)throw new Error('Overview index closing');this.#state='ready';}return this;}
 get bridge(){return this.#bridge;}get budget(){return {...this.#budget};}get creationSequence(){return this.#creationSequence;}get current(){return this.#current;}
 get handle(){return this.#handleValue;}get closed(){return this.#state==='closed';}get pendingOperation()                                            {return this.#state==='uncertain'?this:this.#active;}
 async begin(query                 ,{sequence,onIssued}                                                               ){
  if(this.#closing||this.#state!=='ready'||this.#active)throw new Error('Overview index is closed, busy or has unresolved allocation');
  const request=encodeGeoOverviewRequest({command:28,handle:this.#handleValue,sequence,budget:this.#budget,query});
  const operation=new GeoOverviewQuery(OWNER,this,request,sequence,this.#storage);this.#active=operation;onIssued?.(operation);
  await canonicalQueryAdmit.call(operation);return operation;
 }
 async update(query                 ,input                                                                                   ,cap        ){
  const op=await canonicalIndexBegin.call(this,query,input);let frame                           ;
  try{await canonicalQueryDrive.call(op,input.signal);frame=await canonicalQueryPrepare.call(op,input.signal);await canonicalQueryDispose.call(op);if(input.signal?.aborted||this.#closing||this.#state!=='ready'){await canonicalFrameDispose.call(frame);throw abort();}if(cap!==OWNER)this.#current=frame;return frame;}
  catch(cause){if(frame){try{await canonicalFrameDispose.call(frame);}catch(cleanup){op.holdCleanup(frame,OWNER);throw new GeoOverviewCleanupPending(frame,cleanup);}}if(!op.uncertain)await canonicalQueryDispose.call(op);throw cause;}
 }
 finished(op                 ,cap       ){if(cap!==OWNER)throw new TypeError("Private query settlement required");if(this.#active===op)this.#active=undefined;}
 async dispose(){
  if(this.#state==='closed'){await forgetGeoAllocationIssuer(this);return;}this.#closing=true;if(this.#recovery)await this.#recovery.catch(()=>{});
  if(this.#state==='uncertain'){await this.recoverAllocation();if(this.closed){await this.#attempt .release();await forgetGeoAllocationIssuer(this);return;}}
  if(this.#active)await canonicalQueryDispose.call(this.#active);
  await settleGeoOverviewLoan(this.#transport,this.#handleValue,this.#creationSequence);
  if(!this.#disposal)this.#disposal=Promise.resolve().then(async()=>{if(this.#disposeAttempted&&!this.#disposed){if(!await this.#attempt .probeRetirement(packet=>decodeGeoOverviewReply(packet).handle))this.#disposed=true;}if(!this.#disposed){this.#disposeAttempted=true;validateGeoOverviewMutation(await this.#transport.execute(encodeGeoOverviewRequest({command:10,handle:this.#handleValue,sequence:this.#creationSequence})),this.#handleValue,this.#creationSequence);this.#disposed=true;}await this.#attempt .release();await forgetGeoAllocationIssuer(this);this.#state='closed';this.#storage=closedStorage;indexOwner(this).closed=true;indexOwner(this).reader=closedStorage.readChunk;}).catch(cause=>{this.#disposal=undefined;throw cause;});
  return this.#disposal;
 }
}
export class GeoOverviewQuery {
 #cleanupFrame                           ;#handleValue=0n;#phase                                                     ='admitting';#active                           ;#disposal                        ;
 #admission                        ;#publication                           ;#attempt                     ;#consumed=false;#disposed=false;#disposeAttempted=false;#closing=false;
 #index                 ;#request            ;#sequence       ;#storage                   ;
 constructor(cap       ,index                 ,request            ,sequence       ,storage                   ){if(cap!==OWNER)throw new TypeError("Private issued query required");issuedKinds.set(this,'query');this.#index=index;this.#request=request;this.#sequence=sequence;this.#storage=storage;this.#attempt=new GeoAllocationAttempt(index,indexOwner(index).transport,request);}
 get closed(){return this.#phase==='closed';}get sequence(){return this.#sequence;}get handle(){return this.#handleValue;}get uncertain(){return this.#phase==='uncertain';}
 async admit(){if(this.#admission)return this.#admission;if(this.#phase!=='admitting'&&this.#phase!=='uncertain')throw new Error('Query admission already settled');return this.#admission=Promise.resolve().then(async()=>{try{const packet=await this.#attempt.recover(packet=>{const r=decodeGeoOverviewReply(packet);if(r.code!==0||r.handle===0n||r.sequence!==this.#sequence)throw new TypeError('invalid overview query receipt');return r.handle;});if(!packet){this.#phase='closed';canonicalIndexFinished.call(this.#index,this,OWNER);return;}this.#handleValue=decodeGeoOverviewReply(packet).handle;this.#phase='issued';}catch(cause){this.#admission=undefined;if(this.#attempt.rejected){this.#phase='closed';canonicalIndexFinished.call(this.#index,this,OWNER);throw cause;}this.#phase='uncertain';throw error(this,cause);}});}

 async recover(){if(this.#closing||this.#phase==='closed')throw new Error('Overview query closed');if(this.#publication){const frame=await canonicalFrameRecover.call(this.#publication);if(this.#closing||this.closed)throw new Error('Overview query closed');this.#consumed=frame.consumed;this.#phase='complete';return frame;}await canonicalQueryAdmit.call(this);if(this.closed)throw new Error('Overview allocation retired');return this;}
 async drive(signal             ){
  if(this.#closing||this.#phase!=='issued'||this.#active)throw new Error('Overview query is not an idle issued operation');
  const active=driveGeoOverview(indexOwner(this.#index).transport,{...this.#storage,handle:this.#handleValue,sequence:this.#sequence,budget:indexOwner(this.#index).budget,signal});this.#active=active;
  try{const r=await active;if(r.code===15)throw new GeoOverviewUnsupportedDomain();if(r.code!==14)throw new TypeError('overview query did not complete');this.#phase='complete';}finally{this.#active=undefined;}
 }
 async prepare(signal             ){
  if(this.#closing||this.#phase!=='complete'||this.#active||this.#publication||this.#consumed)throw new Error('Overview query is not complete or already published');
  if(signal?.aborted)throw abort();
  const frame=new GeoOverviewFrame(OWNER,this.#index,this.#sequence,this.#request.slice(0));
  this.#publication=frame;const active=canonicalFramePublish.call(frame,this.#handleValue,this);this.#active=active;
  try{await active;this.#consumed=frame.consumed;if(signal?.aborted){await canonicalFrameDispose.call(frame);throw abort();}return frame;}
  catch(cause){if(frame.rejected){this.#phase='complete';this.#publication=undefined;}else if(frame.uncertain)this.#phase='uncertain';throw cause;}finally{this.#consumed=frame.consumed;this.#active=undefined;}
 }
 holdCleanup(frame                 ,cap       ){if(cap!==OWNER||frame!==this.#publication)throw new TypeError('Private publication cleanup required');this.#cleanupFrame=frame;}
 async dispose(){
  if(this.#cleanupFrame){await canonicalFrameDispose.call(this.#cleanupFrame);this.#cleanupFrame=undefined;}if(this.#phase==='closed')return;this.#closing=true;if(this.#phase==='admitting')await canonicalQueryAdmit.call(this);if(this.#admission){try{await this.#admission;}catch{}}if(this.#phase==='uncertain'){if(this.#publication){if(!this.#publication.published)await canonicalFrameDispose.call(this.#publication);this.#consumed=this.#publication.consumed;}else await canonicalQueryAdmit.call(this);if(this.closed)return;}
  if(this.#active){if(!this.#publication)validateGeoOverviewMutation(await indexOwner(this.#index).transport.execute(encodeGeoOverviewRequest({command:9,handle:this.#handleValue,sequence:this.#sequence})),this.#handleValue,this.#sequence);try{await this.#active;}catch{}this.#consumed=this.#publication?.consumed??false;}
  if(this.#publication&&!this.#publication.published)await canonicalFrameDispose.call(this.#publication);if(this.#consumed){await this.#attempt.release();await forgetGeoAllocationIssuer(this);this.#phase='closed';this.#storage=closedStorage;canonicalIndexFinished.call(this.#index,this,OWNER);return;}await settleGeoOverviewLoan(indexOwner(this.#index).transport,this.#handleValue,this.#sequence);
  if(!this.#disposal)this.#disposal=Promise.resolve().then(async()=>{if(this.#disposeAttempted&&!this.#disposed){if(!await this.#attempt .probeRetirement(packet=>decodeGeoOverviewReply(packet).handle))this.#disposed=true;}if(!this.#disposed){this.#disposeAttempted=true;validateGeoOverviewMutation(await indexOwner(this.#index).transport.execute(encodeGeoOverviewRequest({command:10,handle:this.#handleValue,sequence:this.#sequence})),this.#handleValue,this.#sequence);this.#disposed=true;}await this.#attempt .release();await forgetGeoAllocationIssuer(this);this.#phase='closed';this.#storage=closedStorage;this.#publication=undefined;canonicalIndexFinished.call(this.#index,this,OWNER);}).catch(cause=>{this.#disposal=undefined;throw cause;});return this.#disposal;
 }
}
function samePlane(actual           ,at       ,expected           ,from       ,length       ){if(actual.subarray(at,at+length).some((n,i)=>n!==expected[from+i]))throw new TypeError('Overview Data differs from its private snapshot');}
function validateSnapshot(packet            ,query            ,index                 ){const b=new Uint8Array(packet),q=new Uint8Array(query),source=indexOwner(index).header;for(const [a,e,n] of [[96,64,4],[100,12,4],[112,80,56],[64,136,8],[56,144,8],[80,152,8],[176,160,40],[224,200,4],[232,208,16]])samePlane(b,a,q,e,n);for(const [a,e,n] of [[88,232,8],[76,240,4],[72,244,4]])samePlane(b,a,source,e,n);}
export class GeoOverviewFrame {
 #canonicalPacket                      ;#inspected=false;#handleValue=0n;#value                                                  ;#phase                                   ='new';#disposal                        ;
 #recovery                                    ;#closing=false;#attempt                               ;#expectedCode=16;#sourceHandle=0n;#consumed=false;#disposed=false;#disposeAttempted=false;#membershipCapture                 ;#retention                           ;#index                 ;#sequence       ;#query            ;
 constructor(cap       ,index                 ,sequence       ,query            ){if(cap!==OWNER)throw new TypeError("Private issued frame required");issuedKinds.set(this,'frame');this.#index=index;this.#sequence=sequence;this.#query=query;}
 get rejected(){return this.#attempt?.rejected??false;}get consumed(){return this.#consumed;}get sequence(){return this.#sequence;}get handle(){return this.#handleValue;}get published(){return frames.has(this);}get closed(){return this.#phase==='closed';}get uncertain(){return this.#phase==='uncertain';}get data(){if(!this.#value)throw new Error('Overview frame disposed or unpublished');return this.#value;}
 async publish(queryHandle       ,queryOwner       ){if(this.#phase!=='new')throw new Error('Frame publication already attempted');this.#phase='uncertain';await this.issue(encodeGeoOverviewRequest({command:29,handle:queryHandle,sequence:this.#sequence,budget:indexOwner(this.#index).budget}),queryHandle,queryOwner);}
         issue(request            ,sourceHandle       ,issuerOwner       ,onIssued          ){const task=Promise.resolve().then(async()=>{onIssued?.();await this.issueOnce(request,sourceHandle,issuerOwner);return this;});this.#recovery=task;void task.finally(()=>{if(this.#recovery===task)this.#recovery=undefined;}).catch(()=>{});return task;}
         async issueOnce(request            ,sourceHandle       ,issuerOwner       ){
  if(this.#closing||this.closed)throw new Error('Overview frame closing');
  const expectedCode=new DataView(request).getUint32(8,true)===26?0:16;let expectedLength=0n;
  const issuer=indexOwner(this.#index).transport;this.#expectedCode=expectedCode;this.#sourceHandle=sourceHandle;this.#attempt=new GeoAllocationAttempt(issuerOwner,issuer,request);
  try{const packet=await this.recoverAllocation();if(!packet)throw new Error('Overview allocation retired');const r=decodeGeoOverviewReply(packet);if(r.code!==expectedCode||r.handle===0n||r.sequence!==this.#sequence||r.sourceHandle!==sourceHandle||r.dataLength>32n*1024n*1024n||4n*r.dataLength>BigInt(indexOwner(this.#index).budget.processorBytes))throw new TypeError('invalid overview Data receipt');expectedLength=r.dataLength;this.#handleValue=r.handle;this.#phase='owned';}
  catch(cause){if(this.#attempt.rejected||this.closed){this.#phase='closed';throw cause;}this.#phase='uncertain';throw error(this,cause);}
  try{if(this.#closing)throw new Error('Overview frame closing');await this.readAllocated(expectedLength);}
  catch(cause){this.#recovery=undefined;try{await canonicalFrameDispose.call(this);}catch(cleanup){throw new GeoOverviewCleanupPending(this,cleanup);}throw cause;}
 }
         async recoverAllocation(){const packet=await this.#attempt .recover(packet=>{const r=decodeGeoOverviewReply(packet);if(r.code!==this.#expectedCode||r.handle===0n||r.sequence!==this.#sequence||r.sourceHandle!==this.#sourceHandle||r.dataLength>32n*1024n*1024n||4n*r.dataLength>BigInt(indexOwner(this.#index).budget.processorBytes))throw new TypeError('invalid overview Data receipt');return r.handle;});if(!packet){this.#phase='closed';this.#consumed=this.#expectedCode===16&&this.#attempt .retired;return;}this.#handleValue=decodeGeoOverviewReply(packet).handle;this.#phase='owned';if(this.#expectedCode===16)this.#consumed=true;return packet;}
         async readAllocated(expectedLength       ){const packet=await indexOwner(this.#index).transport.read(encodeGeoOverviewRequest({command:23,handle:this.#handleValue,sequence:this.#sequence}));if(BigInt(packet.byteLength)!==expectedLength)throw new TypeError('overview Data length mismatch');validateSnapshot(packet,this.#query,this.#index);if(this.#closing)throw new Error('Overview frame closing');this.#canonicalPacket=packet.slice(0);this.#value=parseGeoOverviewData(packet);if(this.#value.identity.queryHandle!==this.#sourceHandle||this.#value.identity.sequence!==this.#sequence)throw new TypeError('overview publication sequence mismatch');frames.set(this,{bridge:indexOwner(this.#index).bridge,index:this.#index,handle:this.#handleValue,sequence:this.#sequence,query:this.#query.slice(0),header:new Uint8Array(packet,0,2304).slice()});if(this.#membershipCapture){installOverviewMembers(this.#membershipCapture,this,this.#handleValue,this.#sequence);this.#membershipCapture=undefined;}else registerOverviewMembers(this,indexOwner(this.#index).transport,indexOwner(this.#index).reader         ,indexOwner(this.#index).budget,new Uint8Array(packet,0,2304),this.#handleValue,this.#sequence,indexOwner(this.#index).bridge,indexOwner(this.#index).issuerExecute);}
 recover(){if(this.#recovery)return this.#recovery;const task=Promise.resolve().then(()=>this.recoverOnce());this.#recovery=task;void task.finally(()=>{if(this.#recovery===task)this.#recovery=undefined;}).catch(()=>{});return task;}
         async recoverOnce(){if(this.#closing||this.#disposeAttempted||this.#disposed||this.#phase==='closed')throw new Error('Overview frame closed');if(this.#value)return this;const packet=await this.recoverAllocation();if(!packet)throw new Error('Overview allocation retired');try{await this.readAllocated(decodeGeoOverviewReply(packet).dataLength);if(this.#closing)throw new Error('Overview frame closing');}catch(cause){this.#recovery=undefined;try{await canonicalFrameDispose.call(this);}catch(cleanup){throw new GeoOverviewCleanupPending(this,cleanup);}throw cause;}return this;}
 inspect(cap       ){if(cap!==OWNER||this.#closing||this.closed||!this.#canonicalPacket||this.#inspected)throw new Error('Private overview inspection unavailable');this.#inspected=true;return parseGeoOverviewData(this.#canonicalPacket.slice(0));}
 members(cell       ,input                        ){void this.data;return overviewMembers(this,cell,input);}
 async retain(onIssued                                  ,cap        ){if(this.#closing||this.closed)throw new Error('Overview frame closing');void this.data;if(this.#retention?.closed||this.#retention?.published)this.#retention=undefined;if(this.#retention)throw error(this.#retention,new Error('Previous retained allocation remains unresolved'));const copy=new GeoOverviewFrame(OWNER,this.#index,this.#sequence,this.#query.slice(0));this.#retention=copy;copy.#membershipCapture=captureOverviewMembers(this);await copy.issue(encodeGeoScaleRequest({command:26,handle:this.#handleValue,sequence:this.#sequence,budget:indexOwner(this.#index).budget}),this.#handleValue,this,cap===OWNER?()=>onIssued?.(copy):undefined);this.#retention=undefined;return copy;}
 async dispose(){if(this.#phase==='closed'){await this.#attempt?.release();await forgetGeoAllocationIssuer(this);return;}this.#closing=true;if(this.#recovery)await this.#recovery.catch(()=>{});if(this.closed)return;if(this.#phase==='new'){this.#phase='closed';return;}if(this.#phase==='uncertain'){await this.recoverAllocation();if(this.closed){await this.#attempt .release();await forgetGeoAllocationIssuer(this);return;}}this.#value=undefined;this.#canonicalPacket=undefined;frames.delete(this);dropOverviewMembers(this);this.#membershipCapture=undefined;if(!this.#disposal)this.#disposal=Promise.resolve().then(async()=>{if(this.#disposeAttempted&&!this.#disposed){if(!await this.#attempt .probeRetirement(packet=>decodeGeoOverviewReply(packet).handle))this.#disposed=true;}if(!this.#disposed){this.#disposeAttempted=true;validateGeoOverviewMutation(await indexOwner(this.#index).transport.execute(encodeGeoOverviewRequest({command:10,handle:this.#handleValue,sequence:0n})),this.#handleValue,0n);this.#disposed=true;}await this.#attempt .release();await forgetGeoAllocationIssuer(this);this.#phase='closed';}).catch(cause=>{this.#disposal=undefined;throw cause;});return this.#disposal;}
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
export function updateOverviewIndex(index                 ,query                 ,input                                                                                   ){indexOwner(index);return canonicalIndexUpdate.call(index,query,input,OWNER);}
const canonicalIndexUpdate=GeoOverviewIndex.prototype.update;

/** Internal host retained-copy guard, issued before allocation26. */
export function retainOverviewFrame(frame                 ,onIssued                               ){if(!frames.has(frame))throw new TypeError("Privately issued overview frame required");return canonicalFrameRetain.call(frame,onIssued,OWNER);}
const canonicalFrameRetain=GeoOverviewFrame.prototype.retain;

/** Internal authentic ownership settlement, independent of public methods. */
export function closeOverviewOwner(owner       )              {const kind=issuedKinds.get(owner);if(kind==='index')return canonicalIndexDispose.call(owner                    );if(kind==='query')return canonicalQueryDispose.call(owner                    );if(kind==='frame')return canonicalFrameDispose.call(owner                    );throw new TypeError('Privately issued overview owner required');}
export function getOverviewFrameData(frame                 ){if(issuedKinds.get(frame)!=='frame')throw new TypeError('Privately issued overview frame required');return canonicalFrameInspect.call(frame,OWNER);}
const canonicalFrameInspect=GeoOverviewFrame.prototype.inspect;

import {geoScaleExecute} from './geoscale.js';
import {exportGeoFrame} from './geo-snapshot.js';
const nativeIndices=new WeakSet();
export function isNativeOverviewIndex(index){return nativeIndices.has(index);}
const fromFrame=GeoOverviewIndex.fromFrame;
GeoOverviewIndex.fromFrame=async(frame,input)=>{const native=geoSceneDataAuthority(frame)?.execute===geoScaleExecute;const index=await fromFrame(frame,input);if(native)nativeIndices.add(index);return index;};
GeoOverviewFrame.prototype.export=function(format='png',options={}){if(Object.keys(options).some(k=>!['scale','quality','budget'].includes(k)))throw new TypeError('Unsupported overview export option');const a=overviewFrameAuthority(this);if(!a||!nativeIndices.has(a.index))throw new TypeError('Native overview export requires its native issuing transport');return exportGeoFrame({_freezeCommand:6,handle:a.handle,data:this.data},a.sequence,format,options);};
