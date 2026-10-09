/** Scheduling/paint adapter for one retained Rust geographic source. */
import { XygWasmWorker } from './47_wasm';
import { hydrateWasmPainter, type XygWasmSceneView } from './48_wasm_scene';
import { decodeGeoScaleReply, driveGeoSession, driveGeoIndexSession, encodeGeoScaleRequest, prepareGeoSceneData, prepareGeoAuxData, parseGeoHitData, parseGeoMembershipData, parseGeoRowsData,
  type XygGeoQueryBudget, type XygGeoReadTicket, type XygGeoScaleQuery } from './63_geo_source';

type SceneLease = Awaited<ReturnType<typeof prepareGeoSceneData>>;
type RowsLease=Awaited<ReturnType<typeof prepareGeoAuxData<ReturnType<typeof parseGeoRowsData>>>>;
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
  onSourceRowFocus?: (row:ReturnType<ReturnType<typeof parseGeoRowsData>['record']>)=>void;
}

/** Constructed by the existing geographic chart surface; this is not a second
 * geometry/LOD implementation. Borrowed frame views must not outlive disposal. */
export class RetainedGeographicController {
  readonly ready: Promise<void>;
  private handle = 0n;
  private indexHandle=0n;
  private indexAbort:AbortController|null=null;
  private readIndexPage:RetainedGeographicChartOptions['readChunk']|null=null;
  private indexDecision:'indexed'|'canonical-full-scan'|null=null;
  private indexedStats:ReturnType<typeof decodeGeoScaleReply>['indexStats']=null;
  get spatialDecision(){return this.indexDecision;}
  get spatialStats(){return this.indexedStats?{...this.indexedStats}:null;}
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
  private readonly sourcePanel=document.createElement('div');
  private readonly sourceCompanion=document.createElement('div');
  private readonly loadSource=document.createElement('button');
  private readonly nextSource=document.createElement('button');
  private sourcePage:RowsLease|null=null;
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
    this.sourceCompanion.setAttribute('role','list');this.sourceCompanion.setAttribute('aria-label','Original geographic source rows');
    this.loadSource.type='button';this.loadSource.textContent='Source rows from beginning';
    this.nextSource.type='button';this.nextSource.textContent='Next source rows';this.nextSource.disabled=true;
    this.loadSource.onclick=()=>{void this.sourceRows().catch(error=>this.report(error));};
    this.nextSource.onclick=()=>{void this.sourceRows(true).catch(error=>this.report(error));};
    this.sourcePanel.append(this.loadSource,this.nextSource,this.sourceCompanion);
    (this.options.pointerSurface??this.paint).addEventListener('pointermove',this.pointer);
    options.el.append(this.paint,this.status,this.companion,this.sourcePanel,this.previous,this.next);
    this.initialization = this.initialize().catch(error=>{this.releaseManifest?.();this.releaseManifest=null;this.options={...this.options,manifest:new Uint8Array()};this.initializationFailed=true;throw error;});
    this.ready = this.update(options.query).then(()=>{}).catch(async error=>{if(this.initializationFailed)await this.dispose();throw error;});
    }catch(error){this.releaseManifest?.();this.releaseManifest=null;this.paint.remove();this.status.remove();this.companion.remove();this.sourcePanel.remove();this.previous.remove();this.next.remove();throw error;}
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
    this.operationAbort?.abort();this.indexAbort?.abort();
    this.auxiliaryAbort?.abort();
    this.preparation?.cancel();
    const abort = new AbortController(), sequence = ++this.sequence;
    this.operationAbort = abort;
    // Freeze host-owned authoring fields while the serialized operation waits.
    const frozen = {...query,camera:{...query.camera},time:{...query.time},sourceDigest:query.sourceDigest.slice()};
    const operation = this.chain.then(async()=>{
      await this.initialization;
      if(this.disposed||abort.signal.aborted)throw new DOMException('Geographic operation cancelled','AbortError');
      const queryResult=await this.prepareQuery(frozen,sequence,abort.signal);
      let candidate:SceneLease|null=queryResult.candidate;
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
        this.frame = candidate;this.indexDecision=queryResult.decision;this.indexedStats=queryResult.stats;this.frameProjectedBudget=frozen.maxProjectedVertices; candidate = null;
        this.sourceCompanion.replaceChildren();this.nextSource.disabled=true;
        const oldPage=this.sourcePage;this.sourcePage=null;if(oldPage)await oldPage.dispose();
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

  private async prepareQuery(query:XygGeoScaleQuery,sequence:bigint,signal:AbortSignal){
    let handle=this.handle,owned=false,decision:'indexed'|'canonical-full-scan'|null=null,stats:ReturnType<typeof decodeGeoScaleReply>['indexStats']=null;
    if(this.indexHandle){
      const reply=decodeGeoScaleReply(await this.bridge.execute(encodeGeoScaleRequest({command:18,handle:this.indexHandle,sequence,budget:this.options.budget,query})));
      if(reply.sequence!==sequence)throw new TypeError('Indexed query sequence mismatch');
      if(reply.code===10){if(reply.handle!==this.indexHandle)throw new TypeError('Index fallback authority mismatch');decision='canonical-full-scan';}
      else if(reply.code===0&&reply.handle!==this.indexHandle){handle=reply.handle;owned=true;decision='indexed';}
      else throw new TypeError('Invalid indexed query admission');
    }
    try{
      if(owned){
        const reply=await driveGeoIndexSession(this.bridge,{handle,sequence,budget:this.options.budget,readPage:this.readIndexPage!,signal});
        if(reply.code!==12)throw new TypeError('Indexed query did not complete');stats=reply.indexStats;
      }else{
        await this.bridge.execute(encodeGeoScaleRequest({command:5,handle,sequence,budget:this.options.budget,query}));
        const reply=await driveGeoSession(this.bridge,{handle,sequence,budget:this.options.budget,readChunk:this.options.readChunk,signal});
        if(reply.code!==4)throw new TypeError('Canonical query did not complete');
      }
      const candidate=await prepareGeoSceneData(this.bridge,{command:owned?19:11,handle,sequence,budget:this.options.budget,style:this.options.style});
      return {candidate,decision,stats};
    }finally{if(owned)await this.bridge.execute(encodeGeoScaleRequest({command:10,handle}));}
  }
  /** Explicit immutable sidecar storage, separate from the bounded live cache.
   * Callbacks must settle and drop borrowed page bytes before write ACK. */
  buildIndex(input:{grid?:number;maxVertices:bigint;writePage:(ticket:XygGeoReadTicket,bytes:Uint8Array,signal?:AbortSignal)=>Promise<void>;readPage:RetainedGeographicChartOptions['readChunk']}){
    if(this.disposed)return Promise.reject(new Error('Geographic chart disposed'));
    this.indexAbort?.abort();const abort=new AbortController();this.indexAbort=abort;
    const grid=input.grid??16,maxVertices=input.maxVertices,writePage=input.writePage,readPage=input.readPage;
    if(!Number.isInteger(grid)||grid<1||grid>256||typeof maxVertices!=='bigint'||maxVertices<=0n||maxVertices>0xffffffffffffffffn||typeof writePage!=='function'||typeof readPage!=='function')return Promise.reject(new TypeError('Explicit index options and storage required'));
    const operation=this.chain.then(async()=>{
      await this.initialization;
      if(this.disposed||abort.signal.aborted||!this.frame)throw new DOMException('Geographic index cancelled','AbortError');
      const sequence=this.frame.data.identity.sequence,payload=new Uint8Array(16),v=new DataView(payload.buffer);v.setUint32(0,grid,true);v.setBigUint64(8,maxVertices,true);
      const created=decodeGeoScaleReply(await this.bridge.execute(encodeGeoScaleRequest({command:17,handle:this.frame.handle,sequence,budget:this.options.budget,payload})));
      let handle=created.handle;
      try{
        if(created.sequence!==sequence||created.code!==0)throw new TypeError('Invalid index build admission');
        const reply=await driveGeoIndexSession(this.bridge,{handle,sequence,budget:this.options.budget,readChunk:this.options.readChunk,writePage,signal:abort.signal});
        if(reply.code!==11)throw new TypeError('Index build did not complete');
        if(this.disposed||abort.signal.aborted)throw new DOMException('Geographic index cancelled','AbortError');
        const previous=this.indexHandle;this.indexHandle=handle;handle=0n;this.readIndexPage=readPage;
        if(previous)await this.bridge.execute(encodeGeoScaleRequest({command:10,handle:previous}));
        return {pages:reply.dataLength,grid,maxVertices};
      }finally{if(handle)await this.bridge.execute(encodeGeoScaleRequest({command:10,handle}));if(this.indexAbort===abort)this.indexAbort=null;}
    });this.chain=operation.then(()=>{},()=>{});return operation;
  }

  /** Rust pages original rows regardless of visibility or temporal eligibility.
   * The next-page capability remains in a privately leased Data handle. */
  sourceRows(next=false){
    const abort=new AbortController();this.auxiliaryAbort?.abort();this.auxiliaryAbort=abort;
    const operation=this.chain.then(async()=>{
      if(this.disposed||abort.signal.aborted||!this.frame)throw new DOMException('Geographic operation cancelled','AbortError');
      const frame=this.frame,sequence=frame.data.identity.sequence;
      const prior=this.sourcePage;
      if(next&&(!prior||!prior.data.hasNext||prior.data.sequence!==sequence))throw new Error('No original-row continuation');
      const owner=next?prior!.handle:frame.handle,budget={...this.options.budget,pageRows:Math.min(50,this.options.budget.pageRows)};
      const reply=decodeGeoScaleReply(await this.bridge.execute(encodeGeoScaleRequest({command:15,handle:owner,sequence,budget}))),handle=reply.handle;
      let candidate:RowsLease|null=null;
      try{
        if(reply.sequence!==sequence)throw new TypeError('Original-row session mismatch');
        await driveGeoSession(this.bridge,{handle,sequence,budget,readChunk:this.options.readChunk,signal:abort.signal});
        candidate=await prepareGeoAuxData(this.bridge,{command:16,handle,sequence,budget},parseGeoRowsData);
        if(candidate.data.owner!==handle||candidate.data.sequence!==sequence)throw new TypeError('Original-row page mismatch');
        if(this.disposed||abort.signal.aborted)throw new DOMException('Geographic operation cancelled','AbortError');
        const records=Array.from({length:candidate.data.length},(_,i)=>candidate!.data.record(i));
        this.sourceCompanion.replaceChildren();
        for(const row of records){
          const button=document.createElement('button');button.type='button';button.setAttribute('role','listitem');
          button.textContent=`Feature ${row.featureId}, source row ${row.sourceRow}; ${row.geometryNull?'null geometry':row.timeEligible?'time eligible':'outside time predicate'}`;
          button.onfocus=()=>{this.status.textContent=`Source row ${row.sourceRow}, feature ${row.featureId}`;try{this.options.onSourceRowFocus?.(row);}catch(error){this.report(error);}};
          this.sourceCompanion.append(button);
        }
        this.nextSource.disabled=!candidate.data.hasNext;
        this.sourcePage=candidate;candidate=null;
        if(prior)await prior.dispose();
        return records;
      }finally{
        if(candidate)await candidate.dispose();
        await this.bridge.execute(encodeGeoScaleRequest({command:10,handle}));
        if(this.auxiliaryAbort===abort)this.auxiliaryAbort=null;
      }
    });this.chain=operation.then(()=>{},()=>{});return operation;
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
    this.disposed = true; this.indexAbort?.abort(); this.sourceAbort.abort(); this.operationAbort?.abort();this.auxiliaryAbort?.abort(); this.preparation?.cancel();
    return this.disposal = (async()=>{
      await Promise.allSettled([this.initialization,this.chain]);
      this.options.layer?.releasePrepared();
      this.view?.destroy(); this.view = null;
      (this.options.pointerSurface??this.paint).removeEventListener('pointermove',this.pointer);this.companion.replaceChildren();
      this.paint.remove(); this.status.remove();this.companion.remove();this.previous.remove();this.next.remove();
      this.sourceCompanion.replaceChildren();this.sourcePanel.remove();
      const page=this.sourcePage;this.sourcePage=null;if(page)await page.dispose();
      const frame = this.frame; this.frame = null;
      if(frame)await frame.dispose();
      if(this.indexHandle){await this.bridge.execute(encodeGeoScaleRequest({command:10,handle:this.indexHandle}));this.indexHandle=0n;this.readIndexPage=null;}
      if(this.handle!==0n){await this.bridge.execute(encodeGeoScaleRequest({command:10,handle:this.handle}));this.handle=0n;}
      this.options={...this.options,manifest:new Uint8Array(),style:new Uint8Array(),readChunk:async()=>{throw new Error('Geographic chart disposed');},onChange:undefined,onPick:undefined,onSourceRowFocus:undefined,onError:undefined};
    })();
  }
}
