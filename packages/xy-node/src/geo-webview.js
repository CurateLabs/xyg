/** Native one-mount geographic host facade. No browser imports or source serialization. */
import {hierarchyLaneAuthority,isHierarchyFrame} from './geo-hierarchy.js';
import {retainOverviewFrame,closeOverviewOwner,getOverviewFrameData,overviewFrameAuthority,overviewIndexAuthority,updateOverviewIndex,isNativeOverviewIndex} from './geo-overview-source.js';
import {encodeGeoOverviewRequest} from './geo-overview.js';
import {GeoSelectedScope} from './geo-selected.js';
import {GeoLiveCandidate} from './geo-live-host.js';
import {sceneBrowserPainter} from './scene.js';
import {RetainedGeoSource} from './geo-retained.js';
import {encodeGeoScaleRequest,prepareGeoSceneData,geoScaleExecute} from './geoscale.js';
function buffer(value){
 if(value instanceof ArrayBuffer)return value;
 if(ArrayBuffer.isView(value)&&value.byteOffset===0&&value.byteLength===value.buffer.byteLength)return value.buffer;
 throw new TypeError('exact binary host attachment required');
}
function tag(op,owner=0n,sequence=0n){const b=new ArrayBuffer(32),v=new DataView(b);new Uint8Array(b).set([88,89,71,72]);v.setUint32(4,1,true);v.setUint32(8,op,true);v.setBigUint64(16,owner,true);v.setBigUint64(24,sequence,true);return b;}
function same(a,b){a=new Uint8Array(a);b=new Uint8Array(b);return a.length===b.length&&a.every((n,i)=>n===b[i]);}
const laneClaims=new WeakMap(),overviewHosts=new WeakMap(),overviewData=new WeakMap();
export class GeoHostAdapter {
 #overviewMode=false;#overviewProcessorBytes;
 get overviewMode(){return this.#overviewMode;}
 constructor(chart,{frame,selectedScope,hierarchyLane}={}){
  const overview=chart._overview?.();if(overview){this.initOverview(chart,overview,{frame,selectedScope,hierarchyLane});return;}this.#overviewMode=false;
  const layer=chart._retained();if(!layer||chart.tileSession||(!(layer.source instanceof RetainedGeoSource)||(!frame&&layer.source.constructor!==RetainedGeoSource)))throw new TypeError('native host requires one canonical RetainedGeoSource; indexed hosts are pending');
  if(layer.source.bridge.execute!==geoScaleExecute)throw new TypeError('native geographic host requires the native source bridge');
  const {query,sequence,style}=chart._inputs(layer);
  this.source=layer.source;this.query={...query,camera:{...query.camera},time:{...query.time},sourceDigest:query.sourceDigest.slice()};this.sequence=sequence;this.style=style.slice();this.budget=chart.budget;
  if(selectedScope!==undefined&&(!(selectedScope instanceof GeoSelectedScope)||selectedScope.bridge!==layer.source.bridge))throw TypeError('issued selected scope required');
  this.selectedScope=selectedScope;this.liveCandidate=new GeoLiveCandidate(this,{data:frame=>this.#ownerData(frame),packet:frame=>this.#wirePacket(frame),close:owner=>this.#closeOwner(owner)});
  this.chain=Promise.resolve();this.queued=0;this.closing=false;
  if(frame){
   const expected=encodeGeoScaleRequest({command:5,sequence,budget:this.source.budget,query:this.query});let actual=frame._queryPacket?.slice(0);
   if(!actual)throw new TypeError('explicit frame lacks trusted query authority');
   const actualOp=new DataView(actual).getUint32(8,true);if(actualOp===43&&!isHierarchyFrame(frame))throw TypeError("selected hierarchy frame requires private provenance");if([35,36,43].includes(actualOp)){if(actual.byteLength!==264||new DataView(actual).getBigUint64(232,true)!==8n||!frame.data.selection)throw TypeError('selected frame requires exact issued query framing');actual=actual.slice(0,256);new DataView(actual).setBigUint64(232,0n,true);}
   new Uint8Array(actual).set(new Uint8Array(expected,8,4),8);
   new Uint8Array(actual).set(new Uint8Array(expected,16,8),16);
   const packet=frame.data.packet,pv=new DataView(packet),ev=new DataView(expected),info=this.source.info;
   const identityMatches=packet.byteLength>=256&&pv.getBigUint64(24,true)===sequence&&pv.getUint32(80,true)===ev.getUint32(64,true)&&pv.getUint32(84,true)===ev.getUint32(12,true)&&same(new Uint8Array(packet,88,120),new Uint8Array(expected,80,120))&&pv.getUint32(208,true)===ev.getUint32(200,true)&&pv.getUint32(212,true)===ev.getUint32(68,true)&&same(new Uint8Array(packet,216,16),new Uint8Array(expected,208,16))&&same(info.digest,new Uint8Array(packet,144,8))&&info.generation===pv.getBigUint64(152,true)&&info.rows===pv.getBigUint64(232,true)&&info.geometry===pv.getUint32(240,true)&&info.crs===pv.getUint32(244,true);
   if(frame._source!==this.source||!identityMatches||!same(actual,expected)||!same(frame._style,this.style))throw new TypeError('explicit frame does not match this geographic composition');
   if(hierarchyLane!==undefined){
    const authority=hierarchyLaneAuthority(hierarchyLane);
    if(!authority||authority.source!==this.source||authority.bridge!==this.source.bridge||!authority.selected||!selectedScope||!frame.data.selection||!isHierarchyFrame(frame)||actualOp!==43||hierarchyLane.closed||hierarchyLane.disposing)throw TypeError('issued selected hierarchy lane must match this frame/source');
    if(laneClaims.get(hierarchyLane)?.deref())throw Error('hierarchy lane already belongs to another live adapter');
    laneClaims.set(hierarchyLane,new WeakRef(this));this.hierarchyLane=hierarchyLane;this.hierarchyAuthority=authority;
   }
   this.anchorReady=frame.retain().then(owned=>{this.anchor=owned;},error=>{this.releaseLane();throw error;});
   // Ready retains void; construction starts ownership transfer before caller disposal.
   this.anchorReady.catch(()=>{});
  }else{if(hierarchyLane!==undefined)throw TypeError("hierarchy live route requires an explicit selected frame");this.anchorReady=Promise.resolve();}
 }
 initOverview(chart,layer,{frame,selectedScope,hierarchyLane}){
  if(selectedScope!==undefined||hierarchyLane!==undefined)throw TypeError('Overview does not accept selected/hierarchy authority');
  if(!isNativeOverviewIndex(layer.source))throw TypeError('Overview host requires its genuine native issuing producer');
  const {query,sequence,packet}=chart._overviewInputs(layer);this.source=layer.source;this.query={...query,camera:{...query.camera},time:query.time.kind===0?{kind:0}:query.time.kind===1?{kind:1,instant:query.time.instant}:{kind:2,start:query.time.start,end:query.time.end},sourceDigest:query.sourceDigest.slice()};this.sequence=sequence;this.style=new Uint8Array(0);this.budget=chart.budget;this.#overviewMode=true;overviewHosts.set(this,{source:layer.source,packet:packet.slice(0),authority:overviewIndexAuthority(layer.source)});overviewData.set(this,new WeakMap());this.#overviewProcessorBytes=overviewHosts.get(this).authority.budget.processorBytes;
  this.liveCandidate=new GeoLiveCandidate(this,{overview:true,processorBytes:this.#overviewProcessorBytes,overviewBudget:overviewHosts.get(this).authority.budget,data:frame=>this.#ownerData(frame),packet:frame=>this.#wirePacket(frame),close:owner=>this.#closeOwner(owner)});this.chain=Promise.resolve();this.queued=0;this.closing=false;
  if(frame){const a=overviewFrameAuthority(frame);if(!a||a.index!==layer.source||a.sequence!==sequence||frame.handle!==a.handle||!same(a.query,packet))throw TypeError('Overview frame differs from its issued composition');const initialQuery=this.query;this.anchorReady=this.retainOverview(frame).then(async owned=>{this.anchor=owned;try{this.validateOverviewFrame(owned,initialQuery,sequence);this.liveCandidate.cleanupFrame=undefined;}catch(error){await this.releaseAnchor();throw error;}});this.anchorReady.catch(()=>{});}else this.anchorReady=Promise.resolve();
 }
 overviewSource(){const source=overviewHosts.get(this)?.source;if(!source||source!==this.source)throw TypeError('Overview issuing source changed');return source;}
 validateOverviewFrame(frame,query,sequence){const original=overviewHosts.get(this),a=overviewFrameAuthority(frame);const expected=encodeGeoOverviewRequest({command:28,handle:original.authority.handle,sequence,budget:original.authority.budget,query});if(!a||a.index!==original.source||a.handle!==frame.handle||a.sequence!==sequence||!same(a.query,expected)||!same(new Uint8Array(this.#ownerData(frame).packet,0,2304),a.header))throw TypeError('Overview private frame authority changed');}
 #ownerData(frame){if(!this.#overviewMode)return frame.data;const cache=overviewData.get(this);if(!cache.has(frame))cache.set(frame,getOverviewFrameData(frame));return cache.get(frame);}
 #wirePacket(frame){const packet=this.#ownerData(frame).packet;return this.#overviewMode?packet.slice(0):packet;}
 #closeOwner(owner){if(!this.#overviewMode)return owner.dispose();overviewData.get(this)?.delete(owner);return closeOverviewOwner(owner);}
 async retainOverview(frame){const owned=await retainOverviewFrame(frame,copy=>{this.liveCandidate.cleanupOperation=copy;});this.liveCandidate.cleanupFrame=owned;this.liveCandidate.cleanupOperation=undefined;return owned;}
 async prepareOverview(query,sequence){const source=this.overviewSource();try{const frame=await updateOverviewIndex(source,query,{sequence,onIssued:operation=>{this.liveCandidate.cleanupOperation=operation;}});this.liveCandidate.cleanupFrame=frame;this.validateOverviewFrame(frame,query,sequence);return frame;}finally{await this.liveCandidate.settleOperation();}}
 get mounted(){return this.mount!==undefined;}
 async open(mount){
  await this.anchorReady;
  if(this.closing||this.mounted)throw new Error('geographic host admits one mount; release before reopening');
  this.liveCandidate.beginMount();
  const {query,sequence,style,source}=this;
  const queryPacket=this.#overviewMode?undefined:encodeGeoScaleRequest({command:5,handle:source.handle,sequence,budget:source.budget,query});
  let frame;
  if(this.anchor)frame=this.anchor;
  else if(this.#overviewMode){const current=this.overviewSource().current,a=current&&overviewFrameAuthority(current);const expected=overviewHosts.get(this).packet;if(a&&a.index===source&&a.sequence===sequence&&same(a.query,expected))frame=await this.retainOverview(current);else frame=await this.prepareOverview(query,sequence);}
  else if(source.current&&source.sequence===sequence){
   if(!same(source.current._queryPacket,queryPacket)||!same(source.current._style,style))throw new Error('published query differs from geographic composition');
   frame=await prepareGeoSceneData(source.bridge,{handle:source.handle,sequence,budget:source.budget,style});
   frame._source=source;frame._style=style.slice();frame._queryPacket=queryPacket;
   frame.pick=options=>source.pick({...options,sequence,_owner:frame.handle});
   frame.membership=(cell,options)=>source.membership(cell,{...options,sequence,_owner:frame.handle});
  }else frame=await source.update(query,{sequence,style});
  try{
   if(this.closing)throw new Error('geographic host authoring disposed');
   if(this.#overviewMode)this.validateOverviewFrame(frame,query,sequence);
   const data=this.#ownerData(frame),painter=sceneBrowserPainter(data.scene,this.budget);
   if((this.#overviewMode?4:2)*data.packet.byteLength+painter.byteLength>(this.#overviewMode?this.#overviewProcessorBytes:source.budget.processorBytes))throw new RangeError('geographic host exceeds transfer budget');
   if(this.#overviewMode){this.anchor=frame;this.liveCandidate.cleanupFrame=undefined;}this.frame=frame;this.painter=buffer(painter);this.mount=mount;
   return [tag(1,frame.handle,sequence),this.#wirePacket(frame),this.painter];
  }catch(error){if(this.#overviewMode){this.anchor=frame;this.liveCandidate.cleanupFrame=undefined;}else if(frame!==this.anchor)await frame.dispose();throw error;}
 }
 handle(message,buffers){
  if(message?.type!=='geo_host'||typeof message.request!=='string'||message.request.length<1||message.request.length>96)return Promise.resolve(undefined);
  if(this.queued>=16)return Promise.resolve([{type:'geo_host',request:message.request,error:'native geographic host queue is full'},[]]);
  // Small requests are copied only after bounded queue admission.
  let request;
  try{const attachments=buffers??(message.buffer?[message.buffer]:[]);if(attachments.length!==1)throw new TypeError('one binary request required');const raw=buffer(attachments[0]);if(raw.byteLength<32||raw.byteLength>256)throw new TypeError('invalid request length');request=raw.slice(0);}catch(error){return Promise.resolve([{type:'geo_host',request:message.request,error:error.message},[]]);}
  const mount=message.mount,id=message.request;this.queued++;
  const operation=this.chain.then(async()=>{
   const reply={type:'geo_host',request:id};
   try{
    if(typeof mount!=='string'||mount.length<1||mount.length>96)throw new TypeError('invalid mount identity');
    const v=new DataView(request),op=v.getUint32(8,true),owner=v.getBigUint64(16,true),sequence=v.getBigUint64(24,true);
    if(v.getUint32(0,true)!==0x48475958||v.getUint32(12,true)||!(v.getUint32(4,true)===1&&[1,2,3,4,5].includes(op)||v.getUint32(4,true)===2&&[6,7,8,9].includes(op)))throw new TypeError('invalid host request');
    let out=[];
    if(v.getUint32(4,true)===2){
     const c=this.liveCandidate,repeatedCommit=op===7&&request.byteLength===64&&!new Uint8Array(request,56).some(x=>x)&&c.repeated(7,[owner,sequence,v.getBigUint64(32,true),v.getBigUint64(40,true),v.getBigUint64(48,true)]);
     if(mount!==this.mount||!this.frame||(this.closing&&(op===6&&!c.replayPrepare(request)||op===7&&!repeatedCommit)))throw Error('unowned live geographic mount');
     if(op===8){if(request.byteLength!==64||new Uint8Array(request,56).some(x=>x))throw Error('invalid retirement ACK');await c.acknowledge(owner,sequence,v.getBigUint64(32,true),v.getBigUint64(40,true),v.getBigUint64(48,true));}
     else{
      if(op===9&&request.byteLength===64&&!new Uint8Array(request,56).some(x=>x)&&c.repeated(9,[owner,sequence,v.getBigUint64(32,true),v.getBigUint64(40,true),v.getBigUint64(48,true)]))return [reply,[]];
      if(op!==7&&(owner!==this.frame.handle||sequence!==this.sequence)||this.aux)throw Error('stale candidate baseline or outstanding auxiliary');
      if(op===6){const [packet,painter]=await c.prepare(request),h=new ArrayBuffer(64),hv=new DataView(h);new Uint8Array(h).set(new Uint8Array(request,0,40));hv.setBigUint64(40,c.frame.handle,true);hv.setBigUint64(48,c.sequence,true);out=[h,packet,painter];}
      else{if(request.byteLength!==64||new Uint8Array(request,56).some(x=>x))throw Error('invalid live ACK');const args=[v.getBigUint64(32,true),v.getBigUint64(40,true),v.getBigUint64(48,true)];if(op===7){await c.commit(owner,sequence,...args);out=[request.slice(0)];}else await c.abort(owner,sequence,...args);}
     }
     return [reply,out];
    }
    if(op===1){if(request.byteLength!==32||owner||sequence)throw new TypeError('invalid open');out=await this.open(mount);}
    else{
     if(mount!==this.mount||!this.frame||sequence!==this.#ownerData(this.frame).identity.sequence)throw new Error('unowned or stale geographic frame');
     if(op===5){if(request.byteLength!==32||!this.aux||this.aux.handle!==owner)throw new Error('unowned auxiliary release');const aux=this.aux;this.aux=undefined;await aux.dispose();}
     else{
      if(owner!==this.frame.handle)throw new Error('unowned geographic frame');
      if(op===4){if(request.byteLength!==32||this.aux||this.liveCandidate.frame||this.liveCandidate.cleanupFrame||this.liveCandidate.cleanupOperation||this.liveCandidate.cleanupState||this.liveCandidate.cleanupAllocation)throw new Error('release auxiliary/candidate packets first');await this.release();}
      else if(this.#overviewMode)throw Error('Overview has domain counts, not source feature picking/membership');
      else if(op===2){if(request.byteLength!==64||this.aux)throw new Error('invalid or concurrent pick');this.aux=await this.frame.pick({style:this.frame._style,x:v.getFloat64(32,true),y:v.getFloat64(40,true),tolerance:v.getFloat64(48,true),mode:v.getUint32(56,true),maxHits:v.getUint32(60,true)});out=[tag(op,this.aux.handle,sequence),this.aux.data.packet];}
      else{if(![48,256].includes(request.byteLength)||this.aux||v.getUint32(36,true)!==Number(request.byteLength===256))throw new Error('invalid or concurrent membership');if(v.getBigUint64(40,true)>new DataView(this.frame._queryPacket).getBigUint64(224,true))throw new Error("membership exceeds committed frame work bound");this.aux=await this.frame.membership(v.getUint32(32,true),{maxProjectedVertices:v.getBigUint64(40,true),cursor:request.byteLength===256?new Uint8Array(request.slice(48)):undefined});out=[tag(op,this.aux.handle,sequence),this.aux.data.packet];}
     }
    }
    return [reply,out];
   }catch(error){return [{...reply,error:error.message,...(new DataView(request).getUint32(4,true)===2&&new DataView(request).getUint32(8,true)===6&&!this.liveCandidate.frame&&!this.liveCandidate.cleanupFrame&&!this.liveCandidate.cleanupOperation&&!this.liveCandidate.cleanupState&&!this.liveCandidate.cleanupAllocation?{prepareAbsent:true}:{})},[]];}
   finally{request=undefined;}
  });
  this.chain=operation.then(()=>{},()=>{}).finally(()=>{this.queued--;});return operation;
 }
 async release(){this.painter=undefined;const frame=this.frame;this.frame=undefined;this.mount=undefined;if(frame&&frame!==this.anchor)await this.#closeOwner(frame);if(this.closing)await this.releaseAnchor();}
 releaseLane(){const lane=this.hierarchyLane;if(lane&&laneClaims.get(lane)?.deref()===this)laneClaims.delete(lane);this.hierarchyLane=this.hierarchyAuthority=undefined;}
 async releaseAnchor(){if(this.#overviewMode){await this.liveCandidate.settleOperation();if(this.liveCandidate.cleanupFrame){await this.#closeOwner(this.liveCandidate.cleanupFrame);this.liveCandidate.cleanupFrame=undefined;}}const anchor=this.anchor;if(anchor)await this.#closeOwner(anchor);this.anchor=undefined;this.releaseLane();if(this.closing){overviewHosts.delete(this);overviewData.delete(this);}}
 close(){this.closing=true;this.source=this.query=this.style=undefined;this.cleanup=(this.#overviewMode?Promise.all([this.anchorReady.catch(()=>{}),this.chain]):this.anchorReady).then(()=>this.mounted?undefined:this.releaseAnchor());this.cleanup.catch(()=>{});}
 /** Only a real disposed renderer realm may substitute for a browser release ACK. */
 async realmDestroyed(){this.close();await this.chain;await this.liveCandidate.realmDestroyed();const aux=this.aux;this.aux=undefined;if(aux)await aux.dispose();await this.release();await this.cleanup;}
}

/** Extension-host helper. Caller supplies CSP/resource-local HTML; VS Code >=1.57. */
export function attachGeoWebview(panel,adapter){
 let stopped=false,releaseWaiters=[],transport=Promise.resolve(),queued=0;
 const receive=panel.webview.onDidReceiveMessage(envelope=>{
  if(stopped||envelope?.message?.type!=="geo_host")return;
  if(queued>=16){void panel.webview.postMessage({message:{type:"geo_host",request:envelope.message.request,error:"geographic webview queue is full"},buffers:[]});return;}
  try{if(envelope.buffers?.length!==1||buffer(envelope.buffers[0]).byteLength>256)throw Error("invalid geographic request attachment");}
  catch(error){void panel.webview.postMessage({message:{type:"geo_host",request:envelope.message.request,error:error.message},buffers:[]});return;}
  queued++;
  const operation=transport.then(async()=>{
   let reply;
   try{
    reply=await adapter.handle(envelope.message,envelope.buffers);envelope=undefined;
    if(reply){await panel.webview.postMessage({message:reply[0],buffers:reply[1]});reply=undefined;if(!adapter.mounted){for(const resolve of releaseWaiters)resolve();releaseWaiters=[];}}
   }finally{reply=envelope=undefined;}
  });
  transport=operation.then(()=>{},()=>{}).finally(()=>{queued--;});
 });
 const disposed=panel.onDidDispose(()=>{stopped=true;receive.dispose();disposed.dispose();void transport.then(()=>adapter.realmDestroyed());for(const resolve of releaseWaiters)resolve();releaseWaiters=[];});
 async function release(){if(!adapter.mounted)return;const wait=new Promise(resolve=>releaseWaiters.push(resolve));await panel.webview.postMessage({message:{type:'geo_host_close'},buffers:[]});await wait;}
 return {async reload(html){await release();panel.webview.html=html;},async dispose(){await release();panel.dispose();},get mounted(){return adapter.mounted;}};
}
