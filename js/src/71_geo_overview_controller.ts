/** Temporal-domain publication adapter; Rust owns cells, colors and projection. */
import {getGeoWorkerBridge,isGeoWorkerBridge,acquireGeoWorkerTransport,prepareGeoWorkerFrame,reserveGeoWorkerInput,type XygWasmWorker} from './47_wasm';
import {hydrateWasmPainter,type XygWasmSceneView} from './48_wasm_scene';
import {GeoOverviewIndex,GeoOverviewFrame,overviewIndexAuthority,overviewFrameAuthority,updateOverviewIndex} from './71_geo_overview_owner';
import {encodeGeoOverviewRequest} from './67_geo_overview';
import type {XygGeoScaleBridge,XygGeoScaleQuery} from './63_geo_source';

type Prepared=Awaited<ReturnType<XygWasmWorker['prepareGeoFrame']>['result']>;
export interface OverviewGeographicChartOptions {
 mode:'temporal-domain-overview';el:HTMLElement;worker:XygWasmWorker;index:GeoOverviewIndex;
 query:XygGeoScaleQuery;sequence:bigint;
 layer?:{setPrepared(prepared:Prepared):void;releasePrepared():void};
 onChange?:(frame:OverviewGeoFrameSummary)=>void;onError?:(error:unknown)=>void;
}
export interface OverviewGeoFrameSummary {
 sequence:bigint;temporalExact:true;dataSpace:true;final:false;resolution:16;
 camera:XygGeoScaleQuery['camera'];time:XygGeoScaleQuery['time'];sourceDigest:Uint8Array;
 generation:bigint;layerId:bigint;cameraRevision:bigint;timeRevision:bigint;
 layerRevision:bigint;styleRevision:bigint;stateRevision:bigint;counts:bigint[];
}
const canonicalDispose=GeoOverviewFrame.prototype.dispose;
const aborted=()=>new DOMException('Overview publication cancelled','AbortError');
function copyQuery(q:XygGeoScaleQuery):XygGeoScaleQuery {
 const digest=q.sourceDigest;if(!(digest instanceof Uint8Array)||digest.byteLength!==8)throw new TypeError('Exact8-byte overview source digest required');
 const c=q.camera,t=q.time;
 const time=t.kind===0?{kind:0 as const}:t.kind===1?{kind:1 as const,instant:t.instant}:t.kind===2?{kind:2 as const,start:t.start,end:t.end}:undefined;
 if(!time)throw new TypeError('Explicit overview time predicate required');
 return {camera:{crs:c.crs,worldWrap:c.worldWrap,centerX:c.centerX,centerY:c.centerY,zoom:c.zoom,width:c.width,height:c.height,bearing:c.bearing,pitch:c.pitch},time,sourceDigest:Uint8Array.prototype.slice.call(digest),reducedKind:q.reducedKind,maxCells:q.maxCells,previousDirect:q.previousDirect,maxProjectedVertices:q.maxProjectedVertices,generation:q.generation,layerId:q.layerId,cameraRevision:q.cameraRevision,timeRevision:q.timeRevision,layerRevision:q.layerRevision,styleRevision:q.styleRevision,stateRevision:q.stateRevision};
}
function copySummary(s:OverviewGeoFrameSummary):OverviewGeoFrameSummary{return {...s,camera:{...s.camera},time:{...s.time},sourceDigest:s.sourceDigest.slice(),counts:s.counts.slice()};}
function summary(q:XygGeoScaleQuery,sequence:bigint,header:Uint8Array):OverviewGeoFrameSummary {
 const v=new DataView(header.buffer,header.byteOffset,header.byteLength);
 return {sequence,temporalExact:true,dataSpace:true,final:false,resolution:16,camera:{...q.camera},time:{...q.time},sourceDigest:q.sourceDigest.slice(),generation:q.generation,layerId:q.layerId,cameraRevision:q.cameraRevision,timeRevision:q.timeRevision,layerRevision:q.layerRevision,styleRevision:q.styleRevision,stateRevision:q.stateRevision,counts:Array.from({length:256},(_,i)=>v.getBigUint64(256+8*i,true))};
}
/** Only the existing XygGeographicChart factory exposes this scheduling adapter. */
export class OverviewGeographicController {
 readonly ready:Promise<void>;
 #worker:XygWasmWorker;#bridge:XygGeoScaleBridge;#index:GeoOverviewIndex;
 #el:HTMLElement;#layer:OverviewGeographicChartOptions['layer'];
 #onChange:OverviewGeographicChartOptions['onChange'];#onError:OverviewGeographicChartOptions['onError'];
 #paint=document.createElement('div');#panel=document.createElement('div');#notice=document.createElement('p');
 #table=document.createElement('table');#body=document.createElement('tbody');#previous=document.createElement('button');#next=document.createElement('button');
 #page=0;#pending=0;#closed=false;#chain:Promise<void>=Promise.resolve();#disposal:Promise<void>|undefined;
 #active:AbortController|undefined;#stage:ReturnType<XygWasmWorker['prepareGeoFrame']>|undefined;
 #frame:GeoOverviewFrame|undefined;#view:XygWasmSceneView|undefined;#summary:OverviewGeoFrameSummary|undefined;
 #cleanup:GeoOverviewFrame|undefined;
 static async create(options:OverviewGeographicChartOptions){
  if(options.mode!=='temporal-domain-overview'||!(options.el instanceof HTMLElement))throw new TypeError('Explicit overview mode and geographic container required');
  const bridge=getGeoWorkerBridge(options.worker),a=overviewIndexAuthority(options.index);
  if(!a||a.closed||a.bridge!==bridge)throw new TypeError('Overview index belongs to another Worker or is closed');
  if(options.layer&&typeof options.layer.releasePrepared!=='function')throw new TypeError('Borrowed overview layer must release its prepared buffers');
  await acquireGeoWorkerTransport(options.worker,bridge);
  const current=overviewIndexAuthority(options.index);
  if(!isGeoWorkerBridge(options.worker,bridge)||!current||current.closed||current.bridge!==bridge)throw new TypeError('Overview issuer changed during admission');
  return new OverviewGeographicController(options,bridge);
 }
 private constructor(options:OverviewGeographicChartOptions,bridge:XygGeoScaleBridge){
  this.#worker=options.worker;this.#bridge=bridge;this.#index=options.index;this.#el=options.el;
  this.#layer=options.layer?Object.freeze({setPrepared:options.layer.setPrepared.bind(options.layer),releasePrepared:options.layer.releasePrepared.bind(options.layer)}):undefined;
  this.#onChange=options.onChange;this.#onError=options.onError;
  this.#panel.setAttribute('aria-label','Temporal-exact domain counts; spatial refinement pending');
  this.#notice.textContent='Temporal-exact data-domain overview; spatial refinement pending.';this.#notice.setAttribute('role','status');
  const caption=document.createElement('caption');caption.textContent='Domain cells, exact temporal vertex counts; spatial refinement pending';
  const head=document.createElement('thead'),tr=document.createElement('tr');for(const text of ['Domain cell','Exact temporal vertices']){const th=document.createElement('th');th.scope='col';th.textContent=text;tr.append(th);}head.append(tr);this.#table.append(caption,head,this.#body);
  for(const b of [this.#previous,this.#next]){b.type='button';b.disabled=true;}this.#previous.textContent='Previous 32 domain cells';this.#next.textContent='Next 32 domain cells';
  this.#previous.onclick=()=>{this.#page=Math.max(0,this.#page-1);this.#renderCounts();};this.#next.onclick=()=>{this.#page=Math.min(7,this.#page+1);this.#renderCounts();};
  this.#panel.append(this.#notice,this.#table,this.#previous,this.#next);this.#el.append(this.#paint,this.#panel);
  this.ready=this.update(options.query,{sequence:options.sequence}).then(()=>{}).catch(async error=>{await this.dispose();throw error;});
 }
 #report(error:unknown){try{this.#onError?.(error);}catch{/* Observers do not control publication. */}}
 #assertIssuer(){const a=overviewIndexAuthority(this.#index);if(!a||a.closed||a.bridge!==this.#bridge||!isGeoWorkerBridge(this.#worker,this.#bridge))throw new TypeError('Overview transport/index is unavailable');return a;}
 update(query:XygGeoScaleQuery,input:{sequence:bigint;signal?:AbortSignal}):Promise<OverviewGeoFrameSummary>{
  if(this.#closed)return Promise.reject(new Error('Overview chart disposed'));
  if(this.#pending>=16)return Promise.reject(new RangeError('Overview update queue capacity16 exceeded'));
  let release:()=>void,frozen:XygGeoScaleQuery,expected:ArrayBuffer;
  try{const a=this.#assertIssuer();release=reserveGeoWorkerInput(this.#worker,this.#bridge,4096);try{frozen=copyQuery(query);expected=encodeGeoOverviewRequest({command:28,handle:a.handle,sequence:input.sequence,budget:a.budget,query:frozen});}catch(error){release();throw error;}}
  catch(error){return Promise.reject(error);}
  const sequence=input.sequence,signal=input.signal;this.#pending++;
  const task=this.#chain.then(async()=>{
   if(this.#closed||signal?.aborted)throw aborted();
   await this.#drainCleanup();if(this.#closed||signal?.aborted)throw aborted();this.#assertIssuer();
   const abort=new AbortController(),onAbort=()=>{abort.abort();this.#stage?.cancel();};this.#active=abort;signal?.addEventListener('abort',onAbort,{once:true});
   let candidate:GeoOverviewFrame|undefined,candidateView:XygWasmSceneView|undefined,prepared:Prepared|undefined;
   try{
    candidate=await updateOverviewIndex(this.#index,frozen,{sequence,signal:abort.signal});
    if(this.#closed||abort.signal.aborted)throw aborted();this.#assertIssuer();
    const a=overviewFrameAuthority(candidate),bytes=new Uint8Array(expected);
    if(!a||a.index!==this.#index||a.bridge!==this.#bridge||a.sequence!==sequence||a.header.length!==2304||a.query.byteLength!==256)throw new TypeError('Overview frame issuer/publication mismatch');
    const actual=new Uint8Array(a.query);for(let i=0;i<256;i++)if(actual[i]!==bytes[i])throw new TypeError('Overview frame differs from accepted query');
    const accepted=summary(frozen,sequence,a.header);
    this.#stage=prepareGeoWorkerFrame(this.#worker,this.#bridge,a.handle,sequence);prepared=await this.#stage.result;this.#stage=undefined;
    if(this.#closed||abort.signal.aborted)throw aborted();this.#assertIssuer();
    let holder:HTMLElement|undefined;
    if(!this.#layer){holder=document.createElement('div');candidateView=hydrateWasmPainter(holder,prepared);}
    if(this.#layer)this.#layer.setPrepared(prepared);
    else{this.#view?.destroy();this.#view=candidateView;candidateView=undefined;this.#paint.replaceChildren(holder!);}
    prepared=undefined;const previous=this.#frame;this.#frame=candidate;candidate=undefined;this.#summary=accepted;this.#renderCounts();
    if(previous){this.#cleanup=previous;try{await this.#drainCleanup();}catch(error){this.#report(error);}}
    try{this.#onChange?.(copySummary(accepted));}catch(error){this.#report(error);}return copySummary(accepted);
   }finally{
    signal?.removeEventListener('abort',onAbort);if(this.#active===abort)this.#active=undefined;this.#stage=undefined;
    candidateView?.destroy();candidateView=undefined;prepared=undefined;
    if(candidate){this.#cleanup=candidate;candidate=undefined;await this.#drainCleanup();}
   }
  });
  const settled=task.finally(()=>{this.#pending--;release();});this.#chain=settled.then(()=>{},()=>{});return settled;
 }
 async #drainCleanup(){if(this.#cleanup){const owner=this.#cleanup;await canonicalDispose.call(owner);if(this.#cleanup===owner)this.#cleanup=undefined;}}
 #renderCounts(){
  if(!this.#summary)return;
  const focused=document.activeElement instanceof HTMLElement&&this.#body.contains(document.activeElement)?document.activeElement.dataset.domainCell:undefined;
  const rows=document.createDocumentFragment();for(let i=this.#page*32;i<(this.#page+1)*32;i++){const tr=document.createElement('tr'),cell=document.createElement('th'),value=document.createElement('td');cell.scope='row';cell.textContent=String(i);tr.tabIndex=0;tr.dataset.domainCell=String(i);const count=this.#summary?.counts[i]??0n;value.textContent=String(count);tr.setAttribute('aria-label',`Domain cell ${i}, ${count} exact temporal vertices; spatial refinement pending`);tr.append(cell,value);rows.append(tr);}this.#body.replaceChildren(rows);this.#previous.disabled=this.#page===0;this.#next.disabled=this.#page===7;if(focused)this.#body.querySelector<HTMLElement>(`[data-domain-cell="${focused}"]`)?.focus();
 }
 snapshot():OverviewGeoFrameSummary{if(!this.#summary)throw new Error('Overview frame unavailable');return copySummary(this.#summary);}
 dispose():Promise<void>{
  this.#closed=true;this.#active?.abort();this.#stage?.cancel();
  if(!this.#disposal)this.#disposal=(async()=>{await this.#chain;this.#layer?.releasePrepared();this.#view?.destroy();this.#view=undefined;this.#paint.remove();this.#panel.remove();this.#body.replaceChildren();this.#summary=undefined;this.#previous.onclick=this.#next.onclick=null;this.#onChange=this.#onError=undefined;await this.#drainCleanup();if(this.#frame){this.#cleanup=this.#frame;this.#frame=undefined;await this.#drainCleanup();}this.#layer=undefined;})().catch(error=>{this.#disposal=undefined;throw error;});return this.#disposal;
 }
}
