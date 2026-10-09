/** Scheduling/paint adapter for one retained Rust geographic source. */
import { XygWasmWorker } from './47_wasm';
import { hydrateWasmPainter, type XygWasmSceneView } from './48_wasm_scene';
import { decodeGeoScaleReply, driveGeoSession, encodeGeoScaleRequest, prepareGeoSceneData, prepareGeoAuxData, parseGeoHitData, parseGeoMembershipData,
  type XygGeoQueryBudget, type XygGeoReadTicket, type XygGeoScaleQuery } from './63_geo_source';

type SceneLease = Awaited<ReturnType<typeof prepareGeoSceneData>>;
export type RetainedGeoFrameSummary=Pick<SceneLease['data'],'aggregate'|'visibleVertices'|'projectedVertices'|'columns'|'rows'|'gridCapped'> & {identity:SceneLease['data']['identity']};
export interface RetainedGeographicChartOptions {
  el: HTMLElement;
  worker: XygWasmWorker;
  /** Optional shell-owned canvas/container for pointer events. */
  pointerSurface?: HTMLElement;
  manifest: ArrayBuffer | Uint8Array;
  budget: XygGeoQueryBudget;
  query: XygGeoScaleQuery;
  /** Exact48-byte constant style; Rust validates it. */
  style: Uint8Array;
  readChunk(ticket: XygGeoReadTicket, signal?: AbortSignal): Promise<ArrayBuffer | Uint8Array>;
  layer?: {setPrepared(prepared: Awaited<ReturnType<XygWasmWorker['prepareGeoFrame']>['result']>): void;releasePrepared():void};
  onChange?: (frame: SceneLease['data']) => void;
  onError?: (error: unknown) => void;
  onPick?: (hits: Array<ReturnType<ReturnType<typeof parseGeoHitData>['record']>>) => void;
}

/** Constructed by the existing geographic chart surface; this is not a second
 * geometry/LOD implementation. Borrowed frame views must not outlive disposal. */
export class RetainedGeographicController {
  readonly ready: Promise<void>;
  private handle = 0n;
  private sequence = 0n;
  private chain: Promise<unknown> = Promise.resolve();
  private readonly initialization: Promise<void>;
  private readonly sourceAbort = new AbortController();
  private operationAbort: AbortController | null = null;
  private preparation: ReturnType<XygWasmWorker['prepareGeoFrame']> | null = null;
  private frame: SceneLease | null = null;
  private frameProjectedBudget=0n;
  private initializationFailed=false;
  private view: XygWasmSceneView | null = null;
  private disposed = false;
  private disposal: Promise<void> | null = null;
  private readonly paint = document.createElement('div');
  private readonly status = document.createElement('div');
  private readonly companion = document.createElement('div');
  private readonly previous = document.createElement('button');
  private readonly next = document.createElement('button');
  private companionOffset = 0;
  private auxiliaryAbort: AbortController | null = null;
  private pointerPending = false;
  private readonly pointer = (event:PointerEvent) => {
    if(this.pointerPending||!this.frame||this.disposed)return;
    const camera=this.frame.data.identity.camera,rect=(this.options.pointerSurface??this.paint).getBoundingClientRect();
    if(rect.width<=0||rect.height<=0)return;
    this.pointerPending=true;
    void this.pick((event.clientX-rect.left)*camera.width/rect.width,(event.clientY-rect.top)*camera.height/rect.height).then(hits=>this.options.onPick?.(hits)).catch(error=>this.report(error)).finally(()=>{this.pointerPending=false;});
  };
  private readonly bridge;
  private releaseManifest: (()=>void)|null=null;
  constructor(private options: RetainedGeographicChartOptions) {
    if (!(options.el instanceof HTMLElement) || !(options.worker instanceof XygWasmWorker)) throw new TypeError('Geographic container and Worker required');
    if(options.layer&&typeof options.layer.releasePrepared!=='function')throw new TypeError('A borrowed retained painter must provide releasePrepared');
    if (!(options.style instanceof Uint8Array) || options.style.length !== 48) throw new TypeError('Exact Rust style required');
    const manifestBytes = options.manifest instanceof ArrayBuffer ? new Uint8Array(options.manifest) : options.manifest;
    if(!(manifestBytes instanceof Uint8Array)||3*manifestBytes.byteLength+8192>options.budget.processorBytes)throw new RangeError('Manifest framing exceeds admission');
    this.releaseManifest=options.worker.reserveGeoInput(3*manifestBytes.byteLength+8192);
    try{
    this.options = {...options,budget:{...options.budget},style:options.style.slice(),manifest:manifestBytes.slice(),query:{...options.query,camera:{...options.query.camera},time:{...options.query.time},sourceDigest:options.query.sourceDigest.slice()}};
    const worker=options.worker;
    this.bridge = {execute:(request:ArrayBuffer)=>worker.geoScaleExecute(request),read:(request:ArrayBuffer)=>worker.geoScaleRead(request)};
    this.status.setAttribute('role','status');
    this.companion.setAttribute('role','list');this.companion.setAttribute('aria-label','Painted geographic provenance');
    this.previous.type='button';this.next.type='button';this.previous.textContent='Previous 50';this.next.textContent='Next 50';
    this.previous.onclick=()=>{this.companionOffset=Math.max(0,this.companionOffset-50);this.renderCompanion();};
    this.next.onclick=()=>{this.companionOffset+=50;this.renderCompanion();};
    (this.options.pointerSurface??this.paint).addEventListener('pointermove',this.pointer);
    options.el.append(this.paint,this.status,this.companion,this.previous,this.next);
    this.initialization = this.initialize().catch(error=>{this.releaseManifest?.();this.releaseManifest=null;this.options={...this.options,manifest:new Uint8Array()};this.initializationFailed=true;throw error;});
    this.ready = this.update(options.query).then(()=>{}).catch(async error=>{if(this.initializationFailed)await this.dispose();throw error;});
    }catch(error){this.releaseManifest?.();this.releaseManifest=null;this.paint.remove();this.status.remove();this.companion.remove();this.previous.remove();this.next.remove();throw error;}
  }
  private async initialize() {
    if (this.disposed) throw new Error('Geographic chart disposed');
    const request=encodeGeoScaleRequest({command:4,budget:this.options.budget,payload:this.options.manifest});
    this.options={...this.options,manifest:new Uint8Array()};
    this.releaseManifest?.();this.releaseManifest=null;
    const reply = decodeGeoScaleReply(await this.bridge.execute(request));
    this.handle = reply.handle;
    await driveGeoSession(this.bridge,{handle:this.handle,sequence:0n,budget:this.options.budget,readChunk:this.options.readChunk,signal:this.sourceAbort.signal});
  }
  /** New snapshots cancel superseded work; the old painted frame survives any
   * failure. All source I/O is bounded and authorized by a Rust-issued ticket. */
  update(query:XygGeoScaleQuery):Promise<RetainedGeoFrameSummary> {
    if(this.disposed)return Promise.reject(new Error('Geographic chart disposed'));
    this.operationAbort?.abort();
    this.auxiliaryAbort?.abort();
    this.preparation?.cancel();
    const abort = new AbortController(), sequence = ++this.sequence;
    this.operationAbort = abort;
    // Freeze host-owned authoring fields while the serialized operation waits.
    const frozen = {...query,camera:{...query.camera},time:{...query.time},sourceDigest:query.sourceDigest.slice()};
    const operation = this.chain.then(async()=>{
      await this.initialization;
      if(this.disposed||abort.signal.aborted)throw new DOMException('Geographic operation cancelled','AbortError');
      await this.bridge.execute(encodeGeoScaleRequest({command:5,handle:this.handle,sequence,budget:this.options.budget,query:frozen}));
      await driveGeoSession(this.bridge,{handle:this.handle,sequence,budget:this.options.budget,readChunk:this.options.readChunk,signal:abort.signal});
      let candidate:SceneLease|null = await prepareGeoSceneData(this.bridge,{handle:this.handle,sequence,budget:this.options.budget,style:this.options.style});
      let candidateView:XygWasmSceneView|null = null;
      let staging:ReturnType<XygWasmWorker['prepareGeoFrame']>|null = null;
      let prepared:Awaited<ReturnType<XygWasmWorker['prepareGeoFrame']>['result']>|null = null;
      try {
        if(this.disposed||abort.signal.aborted)throw new DOMException('Geographic operation cancelled','AbortError');
        staging = this.options.worker.prepareGeoFrame(candidate.handle,sequence);
        this.preparation = staging;
        prepared = await staging.result;
        staging = null;
        if(this.disposed||abort.signal.aborted)throw new DOMException('Geographic operation cancelled','AbortError');
        if(this.options.layer)this.options.layer.setPrepared(prepared);
        else {
          const holder = document.createElement('div');
          candidateView = hydrateWasmPainter(holder,prepared);
          this.view?.destroy(); this.view = candidateView; candidateView = null;
          this.paint.replaceChildren(holder);
        }
        prepared = null;
        const previous = this.frame;
        this.companion.replaceChildren();this.companionOffset=0;
        this.frame = candidate;this.frameProjectedBudget=frozen.maxProjectedVertices; candidate = null;
        if(previous)await previous.dispose();
        this.preparation = null;
        const frame = this.frame.data;
        this.status.textContent = `${frame.visibleVertices} visible vertices; ${frame.aggregate?'reduced':'direct'} geographic tier`;
        this.renderCompanion();
        try{this.options.onChange?.(frame);}catch(error){try{this.options.onError?.(error);}catch{/* Observer isolation. */}}
        return {aggregate:frame.aggregate,visibleVertices:frame.visibleVertices,projectedVertices:frame.projectedVertices,columns:frame.columns,rows:frame.rows,gridCapped:frame.gridCapped,identity:{...frame.identity,sourceDigest:frame.identity.sourceDigest.slice(),camera:{...frame.identity.camera},time:{...frame.identity.time}}};
      } finally {
        candidateView?.destroy(); candidateView = null;
        prepared = null; staging = null;
        this.preparation = null;
        if(candidate)await candidate.dispose();
      }
    });
    this.chain = operation.then(()=>{},()=>{});
    return operation;
  }
  private report(error:unknown){if(error instanceof DOMException&&error.name==='AbortError')return;try{this.options.onError?.(error);}catch{/* Observer isolation. */}}
  private renderCompanion(){
    const data=this.frame?.data;this.companion.replaceChildren();
    if(!data){this.previous.disabled=true;this.next.disabled=true;return;}
    const stop=Math.min(data.length,this.companionOffset+50);
    this.previous.disabled=this.companionOffset===0;this.next.disabled=stop>=data.length;
    for(let i=this.companionOffset;i<stop;i++){
      const record=data.record(i);if('count' in record&&record.count===0n)continue;
      const button=document.createElement('button');button.type='button';button.setAttribute('role','listitem');
      button.textContent='count' in record?`Cell ${i}: ${record.count} visible vertices`:`Feature ${record.featureId}, source row ${record.sourceRow}, vertex ${record.vertex}`;
      if('count' in record)button.onclick=()=>{void this.membership(i).then(page=>{this.status.textContent=`Cell ${i}: ${page.records.length} source rows in this page${page.cursor?'; more pages available':''}`;}).catch(error=>this.report(error));};
      else button.onclick=()=>{this.status.textContent=`Feature ${record.featureId}, source row ${record.sourceRow}, vertex ${record.vertex}`;};
      this.companion.append(button);
    }
  }
  /** Rust decides hit geometry and paint order. Returned records are bounded values,
   * not packet views, and remain valid after the temporary reply is released. */
  pick(x:number,y:number,tolerance=0,mode:0|1=0,maxHits=1){
    const payload=new Uint8Array(80),v=new DataView(payload.buffer);payload.set(this.options.style);
    v.setFloat64(48,x,true);v.setFloat64(56,y,true);v.setFloat64(64,tolerance,true);v.setUint32(72,mode,true);v.setUint32(76,maxHits,true);
    const operation=this.chain.then(async()=>{
      if(this.disposed||!this.frame)throw new Error('No painted geographic frame');
      const frame=this.frame,sequence=frame.data.identity.sequence;
      const lease=await prepareGeoAuxData(this.bridge,{command:14,handle:frame.handle,sequence,budget:this.options.budget,payload},parseGeoHitData);
      let data:ReturnType<typeof parseGeoHitData>|null=null;
      try{data=lease.data;if(data.owner!==frame.handle||data.sequence!==sequence)throw new TypeError('Hit frame mismatch');return Array.from({length:data.length},(_,i)=>data!.record(i));}
      finally{data=null;await lease.dispose();}
    });this.chain=operation.then(()=>{},()=>{});return operation;
  }
  /** A bounded source-row page, using Rust's opaque continuation cursor. */
  membership(cell:number,cursor:Uint8Array|null=null){
    if(!Number.isInteger(cell)||cell<0||cell>0xffffffff||cursor&&(!(cursor instanceof Uint8Array)||cursor.length!==208))return Promise.reject(new TypeError('Invalid membership framing'));
    const payload=new Uint8Array(16+(cursor?208:0)),v=new DataView(payload.buffer);v.setUint32(0,cell,true);v.setUint32(4,cursor?1:0,true);if(cursor)payload.set(cursor,16);
    const abort=new AbortController();this.auxiliaryAbort?.abort();this.auxiliaryAbort=abort;
    const operation=this.chain.then(async()=>{
      if(this.disposed||abort.signal.aborted||!this.frame)throw new DOMException('Geographic operation cancelled','AbortError');
      const frame=this.frame,sequence=frame.data.identity.sequence;v.setBigUint64(8,this.frameProjectedBudget,true);
      const reply=decodeGeoScaleReply(await this.bridge.execute(encodeGeoScaleRequest({command:12,handle:frame.handle,sequence,budget:this.options.budget,payload}))),handle=reply.handle;
      let lease:Awaited<ReturnType<typeof prepareGeoAuxData<ReturnType<typeof parseGeoMembershipData>>>>|null=null;
      let data:ReturnType<typeof parseGeoMembershipData>|null=null;
      try{
        await driveGeoSession(this.bridge,{handle,sequence,budget:this.options.budget,readChunk:this.options.readChunk,signal:abort.signal});
        lease=await prepareGeoAuxData(this.bridge,{command:13,handle,sequence,budget:this.options.budget},parseGeoMembershipData);data=lease.data;
        if(data.owner!==handle||data.sequence!==sequence||data.cell!==cell)throw new TypeError('Membership frame mismatch');
        if(abort.signal.aborted)throw new DOMException('Geographic operation cancelled','AbortError');
        return {records:Array.from({length:data.length},(_,i)=>data!.record(i)),cursor:data.cursor?.slice()??null};
      }finally{data=null;if(lease)await lease.dispose();await this.bridge.execute(encodeGeoScaleRequest({command:10,handle}));if(this.auxiliaryAbort===abort)this.auxiliaryAbort=null;}
    });this.chain=operation.then(()=>{},()=>{});return operation;
  }

  snapshot():SceneLease['data']|null {return this.frame?.data??null;}
  /** Drop painter/packet consumers before acknowledging data/session disposal. */
  dispose():Promise<void> {
    if(this.disposal)return this.disposal;
    this.disposed = true; this.sourceAbort.abort(); this.operationAbort?.abort();this.auxiliaryAbort?.abort(); this.preparation?.cancel();
    return this.disposal = (async()=>{
      await Promise.allSettled([this.initialization,this.chain]);
      this.options.layer?.releasePrepared();
      this.view?.destroy(); this.view = null;
      (this.options.pointerSurface??this.paint).removeEventListener('pointermove',this.pointer);this.companion.replaceChildren();
      this.paint.remove(); this.status.remove();this.companion.remove();this.previous.remove();this.next.remove();
      const frame = this.frame; this.frame = null;
      if(frame)await frame.dispose();
      if(this.handle!==0n){await this.bridge.execute(encodeGeoScaleRequest({command:10,handle:this.handle}));this.handle=0n;}
      this.options={...this.options,manifest:new Uint8Array(),style:new Uint8Array(),readChunk:async()=>{throw new Error('Geographic chart disposed');},onChange:undefined,onPick:undefined,onError:undefined};
    })();
  }
}
