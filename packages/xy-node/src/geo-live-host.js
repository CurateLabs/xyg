import {hierarchyLaneAuthority,isHierarchyFrame} from './geo-hierarchy.js';
/** Private XYGHv2 staging; Rust owns all camera/LOD/selected policy. */
import {encodeGeoScaleRequest as encode,decodeGeoScaleReply as decode,driveGeoSession,driveGeoIndexSession,prepareGeoSceneData} from './geoscale.js';
import {encodeGeoViewportRequest,decodeGeoViewportResponse,geoViewportExecute} from './geoviewport.js';
import {attachRetainedFrame} from './geo-retained.js';
import {GeoSpatialIndex,GeoSpatialFullScanRequired} from './geo-spatial.js';
import {sceneBrowserPainter} from './scene.js';
let staged;
const same=(a,b)=>a.length===b.length&&a.every((n,i)=>n===b[i]);
export class GeoLiveCandidate {
 constructor(adapter){this.adapter=adapter;this.nonce=0n;this.receipts=new Map();}
 replayPrepare(raw){if(this.cleanupFrame||this.cleanupOperation||this.cleanupState||this.cleanupAllocation)return same(new Uint8Array(raw),new Uint8Array(this.cleanupRequest));return !!this.frame&&!this.committed&&!!this.prepareRequest&&same(new Uint8Array(raw),new Uint8Array(this.prepareRequest));}
 async rejectPrepared(frame){this.cleanupFrame=frame;await frame.dispose();this.cleanupFrame=undefined;throw new DOMException("Geographic preparation cancelled","AbortError");}
 beginMount(){if(this.frame||this.retired||this.cleanupFrame||this.cleanupOperation||this.cleanupState||this.cleanupAllocation)throw Error("Outstanding geographic candidate");this.nonce=0n;this.receipts.clear();}
 releaseSlot(){if(staged===this)staged=undefined;}
 async allocateState(scope,query,selection,budget){
  const ids=new BigUint64Array(selection.idCount);for(let i=0;i<ids.length;i++)ids[i]=selection.id(i);
  this.cleanupAllocation=scope.beginState({revision:query.stateRevision,ids,fill:selection.fill,budget});
  const state=await this.cleanupAllocation.recover();this.cleanupState=state;return state;
 }
 async settleOperation(){if(this.cleanupOperation){await this.cleanupOperation.dispose();this.cleanupOperation=undefined;}if(this.cleanupAllocation){await this.cleanupAllocation.dispose();this.cleanupAllocation=undefined;}if(this.cleanupState){await this.cleanupState.dispose();this.cleanupState=undefined;}}
 async buildHierarchy(query,sequence){
  const a=this.adapter,lane=a.hierarchyLane;
  if(hierarchyLaneAuthority(lane)!==a.hierarchyAuthority||lane.closed||lane.disposing)throw Error('hierarchy lane unavailable or authority changed');
  const generation=lane.cancelGeneration;
  const state=await this.allocateState(a.selectedScope,query,a.frame.data.selection,lane.budget);let operation;
  try{if(lane.closed||lane.disposing||generation!==lane.cancelGeneration)throw new DOMException("Geographic preparation cancelled","AbortError");operation=await lane.beginSelected(state,query,{sequence});this.cleanupOperation=operation;await operation.drive();const frame=await operation.prepare(a.style);this.cleanupFrame=frame;if(lane.closed||lane.disposing||generation!==lane.cancelGeneration)await this.rejectPrepared(frame);return frame;}
  finally{this.cleanupOperation=operation??lane.pendingOperation;await this.settleOperation();}
 }
 async build(query,sequence){
  if(this.adapter.hierarchyLane)return this.buildHierarchy(query,sequence);
  const a=this.adapter,s=a.source,indexed=s instanceof GeoSpatialIndex;
  return s._run(async signal=>{
   const selected=a.frame.data.selection;
   if(selected){
    if(!a.selectedScope)throw Error('selected live frame requires explicit selected scope');
    const state=await this.allocateState(a.selectedScope,query,selected,s.budget);let operation;
    try{const accepted=await state.begin({command:indexed?36:35,handle:s.handle,sequence,query,budget:s.budget});if(accepted.fallback)throw new GeoSpatialFullScanRequired(accepted.reason);operation=accepted.operation;if(operation.indexed)this.cleanupOperation=operation;s.sequence=sequence;await operation.drive({readChunk:s.readChunk,readPage:s.readPage,signal});const frame=await operation.prepare(a.style);this.cleanupFrame=frame;if(signal?.aborted||s.closed||s.disposing){await this.rejectPrepared(frame);}attachRetainedFrame(s,frame,sequence,encode({command:indexed?36:35,handle:s.handle,sequence,query,budget:s.budget,payload:new Uint8Array(8)}),a.style);return frame;}
    finally{await this.settleOperation();}
   }
   const request=encode({command:indexed?18:5,handle:s.handle,sequence,query,budget:s.budget});let handle;
   try{const reply=decode(await s.bridge.execute(request));if(reply.code===10)throw new GeoSpatialFullScanRequired(reply.fallbackReasonCode);handle=reply.handle;s.sequence=sequence;
    const result=await (indexed?driveGeoIndexSession:driveGeoSession)(s.bridge,{handle,sequence,budget:s.budget,readChunk:s.readChunk,readPage:s.readPage,signal});if(result.code!==(indexed?12:4))throw Error('live query did not complete');
    const frame=await prepareGeoSceneData(s.bridge,{command:indexed?19:11,handle,sequence,budget:s.budget,style:a.style});this.cleanupFrame=frame;if(signal?.aborted||s.closed||s.disposing){await this.rejectPrepared(frame);}attachRetainedFrame(s,frame,sequence,request,a.style);return frame;
   }finally{if(indexed&&handle!==undefined)await s.bridge.execute(encode({command:10,handle}));}
  });
 }
 async prepare(raw){
  if(this.cleanupFrame||this.cleanupOperation||this.cleanupState||this.cleanupAllocation){if(!this.replayPrepare(raw))throw Error("Candidate cleanup requires exact preparation retry");await this.settleOperation();if(this.cleanupFrame){await this.cleanupFrame.dispose();this.cleanupFrame=undefined;}this.releaseSlot();throw new DOMException("Geographic preparation cancelled","AbortError");}
  if(this.replayPrepare(raw))return [this.frame.data.packet,this.painter];
  const a=this.adapter;if(isHierarchyFrame(a.frame)&&!a.hierarchyLane)throw Error("Hierarchy live updates require an explicit hierarchy route");const v=new DataView(raw),b=new Uint8Array(raw);
  if(raw.byteLength!==256||b.subarray(76,80).some(x=>x)||b.subarray(224).some(x=>x))throw Error('invalid live prepare framing');
  const nonce=v.getBigUint64(32,true),sequence=v.getBigUint64(40,true),cameraRevision=v.getBigUint64(48,true),timeRevision=v.getBigUint64(56,true),stateRevision=v.getBigUint64(64,true),kind=v.getUint32(72,true),start=v.getBigInt64(80,true),end=v.getBigInt64(88,true);
  if(!nonce||nonce<=this.nonce||this.frame||this.retired||sequence<=a.sequence||cameraRevision<a.query.cameraRevision||timeRevision<a.query.timeRevision||stateRevision!==a.query.stateRevision)throw Error('stale or outstanding desired snapshot');
  if(![0,1,2].includes(kind)||(kind===0&&(start||end))||(kind===1&&end))throw Error('invalid signed time framing');
  const cameraRequest=raw.slice(96,224),c=new DataView(cameraRequest),cb=new Uint8Array(cameraRequest),op=c.getUint32(8,true),baseline=new Uint8Array(encodeGeoViewportRequest(a.frame.data.identity.camera,op));
  if(op>9||!same(cb.subarray(0,8),baseline.subarray(0,8))||!same(cb.subarray(12,80),baseline.subarray(12,80))||cb.subarray(120).some(x=>x))throw Error('camera delta does not name accepted camera');
  if(staged)throw Error('another geographic replacement awaits retirement ACK');staged=this;this.cleanupRequest=raw.slice(0);let frame;
  try{const camera=decodeGeoViewportResponse(geoViewportExecute(cameraRequest,1<<20)).camera,time={kind,...kind===1?{instant:start}:kind===2?{start,end}:{}};
   if(!same(new Uint8Array(encodeGeoViewportRequest(camera)),new Uint8Array(encodeGeoViewportRequest(a.frame.data.identity.camera)))&&cameraRevision===a.query.cameraRevision)throw Error('camera change requires new revision');
   const q={...a.query,camera,time,cameraRevision,timeRevision,stateRevision};
   if(!same(new Uint8Array(encode({...{command:5,sequence,budget:a.source.budget,query:q}}),200,24),new Uint8Array(encode({command:5,sequence,budget:a.source.budget,query:{...q,time:a.query.time}}),200,24))&&timeRevision===a.query.timeRevision)throw Error('time change requires new revision');
   frame=await this.build(q,sequence);this.cleanupFrame=undefined;const painter=sceneBrowserPainter(frame.data.scene,a.budget);if(2*frame.data.packet.byteLength+painter.byteLength>a.source.budget.processorBytes)throw Error('candidate exceeds transfer ceiling');
   this.frame=frame;this.query=q;this.painter=painter;this.nonce=nonce;this.sequence=sequence;this.committed=false;this.prepareRequest=raw.slice(0);this.oldOwner=a.frame.handle;this.oldSequence=a.sequence;return [frame.data.packet,painter];
  }catch(error){await this.settleOperation();if(frame)this.cleanupFrame=frame;if(this.cleanupFrame){await this.cleanupFrame.dispose();this.cleanupFrame=undefined;}this.releaseSlot();throw error;}
 }
 repeated(op,receipt){const old=this.receipts.get(op);return !!old&&old.every((n,i)=>n===receipt?.[i]);}
 async commit(old,oldSequence,nonce,owner,sequence){const a=this.adapter,r=[old,oldSequence,nonce,owner,sequence];if(this.repeated(7,r)&&a.frame.handle===owner&&a.sequence===sequence)return;if(old!==a.frame.handle||oldSequence!==a.sequence||this.committed||!this.frame||nonce!==this.nonce||owner!==this.frame.handle||sequence!==this.sequence||a.aux)throw Error('unowned geographic commit');this.retired=a.frame;this.retiredSequence=a.sequence;a.frame=this.frame;a.painter=this.painter;a.query=this.query;a.sequence=this.sequence;this.committed=true;this.receipts.set(7,r);}
 async acknowledge(old,oldSequence,nonce,owner,sequence){const a=this.adapter,r=[old,oldSequence,nonce,owner,sequence];if(this.repeated(8,r))return;if(!this.committed||!this.retired||old!==this.retired.handle||oldSequence!==this.retiredSequence||nonce!==this.nonce||owner!==this.frame.handle||sequence!==this.sequence)throw Error('unowned retirement ACK');await this.retired.dispose();a.anchor=this.frame;this.receipts.set(8,r);this.prepareRequest=undefined;this.retired=undefined;this.frame=this.query=this.painter=undefined;this.releaseSlot();}
 async realmDestroyed(){
  const a=this.adapter;await this.settleOperation();if(this.cleanupFrame){await this.cleanupFrame.dispose();this.cleanupFrame=undefined;}if(this.retired){await this.retired.dispose();a.anchor=this.frame;this.retired=undefined;}
  if(this.frame&&!this.committed){await this.frame.dispose();}this.prepareRequest=undefined;this.frame=this.query=this.painter=undefined;this.releaseSlot();
 }
 async abort(old,oldSequence,nonce,owner,sequence){const r=[old,oldSequence,nonce,owner,sequence];if(this.repeated(9,r))return;if(old!==this.oldOwner||oldSequence!==this.oldSequence||this.committed||!this.frame||nonce!==this.nonce||owner!==this.frame.handle||sequence!==this.sequence)throw Error('unowned candidate abort ACK');await this.frame.dispose();this.receipts.set(9,r);this.prepareRequest=undefined;this.frame=this.query=this.painter=undefined;this.releaseSlot();}
}
