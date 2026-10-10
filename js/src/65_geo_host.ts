/** Native immutable geographic host transport. Rust owns Scene and picking.
 * One mounted copy; raw binary replies never confer WASM FrameData authority. */
import { captureGesturePointer } from "./50_chartview";
import { encodeGeoViewportRequest } from "./49_wasm_geoviewport";
import { hydrateWasmPainter } from "./48_wasm_scene";
import type { XygWasmScenePaint } from "./47_wasm";
import type { XygWasmSceneView } from "./48_wasm_scene";
import { parseGeoSceneData, parseGeoHitData, parseGeoMembershipData } from "./63_geo_source";

import { parseGeoOverviewData } from "./67_geo_overview";
type HostData = ReturnType<typeof parseGeoSceneData> | ReturnType<typeof parseGeoOverviewData>;
function overviewData(data: HostData): data is ReturnType<typeof parseGeoOverviewData> { return "count" in data; }
function parseHostData(packet: ArrayBuffer): HostData {
  return new DataView(packet).getUint32(0,true)===0x564f5958 ? parseGeoOverviewData(packet) : parseGeoSceneData(packet);
}

export interface XygGeoHostComm {
  send(message: Record<string, unknown>, buffers?: ArrayBuffer[]): void;
  onMessage(callback: (message: any, buffers: any[]) => void): () => void;
}
function ownedBuffer(value: any): ArrayBuffer {
  if (value instanceof ArrayBuffer) return value;
  if (ArrayBuffer.isView(value) && value.byteOffset === 0 && value.byteLength === value.buffer.byteLength && value.buffer instanceof ArrayBuffer) return value.buffer;
  throw new TypeError("geographic host requires exact binary attachment storage");
}
function header(op: number, owner = 0n, sequence = 0n, extra = 0): ArrayBuffer {
  const b = new ArrayBuffer(32 + extra), v = new DataView(b);
  new Uint8Array(b).set([88,89,71,72]); v.setUint32(4,1,true); v.setUint32(8,op,true);
  v.setBigUint64(16,owner,true); v.setBigUint64(24,sequence,true); return b;
}
function replyHeader(raw: any, op: number) {
  const b = ownedBuffer(raw), v = new DataView(b);
  if (b.byteLength !== 32 || v.getUint32(0,true) !== 0x48475958 || v.getUint32(4,true) !== 1 || v.getUint32(8,true) !== op || v.getUint32(12,true)) throw new TypeError("invalid native geographic host reply");
  return {owner:v.getBigUint64(16,true), sequence:v.getBigUint64(24,true)};
}

export interface XygGeoHostUpdate {
  operation:number; args:readonly number[]; sequence:bigint;
  cameraRevision:bigint; timeRevision:bigint; stateRevision:bigint;
  time:{kind:0|1|2;instant?:bigint;start?:bigint;end?:bigint};
}
function liveHeader(op:number,old:bigint,oldSequence:bigint,nonce:bigint,owner:bigint,sequence:bigint){
 const b=header(op,old,oldSequence,32),v=new DataView(b);v.setUint32(4,2,true);v.setBigUint64(32,nonce,true);v.setBigUint64(40,owner,true);v.setBigUint64(48,sequence,true);return b;
}
function liveTag(raw:any,op:number){
 const b=ownedBuffer(raw),v=new DataView(b);if(b.byteLength!==64||v.getUint32(0,true)!==0x48475958||v.getUint32(4,true)!==2||v.getUint32(8,true)!==op||v.getUint32(12,true)||v.getBigUint64(56,true))throw TypeError('invalid live geographic tag');
 return {old:v.getBigUint64(16,true),oldSequence:v.getBigUint64(24,true),nonce:v.getBigUint64(32,true),owner:v.getBigUint64(40,true),sequence:v.getBigUint64(48,true)};
}

export class XygGeoHostView {
  readonly ready: Promise<void>;
  readonly mount = crypto.randomUUID();
  private serial = 0;
  private pending = new Map<string, {resolve:(buffers:any[])=>void;reject:(error:Error)=>void}>();
  private unsubscribe: ()=>void;
  private chain: Promise<void> = Promise.resolve();
  private queued = 0;
  private closing = false;
  private disposal?: Promise<void>;
  private gestureChain:Promise<void>=Promise.resolve();
  private gestureQueued=0;
  private queueGesture(args:readonly number[],operation:3|4=3){
    if(this.gestureQueued>=16){this.gestureError(new Error('Geographic gesture queue is full'));return;}
    this.gestureQueued++;
    this.gestureChain=this.gestureChain.then(async()=>{
      await this.chain;
      if(this.closing)return;
      const i=this.identity;this.gestureSequence=(this.gestureSequence>i.sequence?this.gestureSequence:i.sequence)+1n;this.gestureCameraRevision=(this.gestureCameraRevision>i.cameraRevision?this.gestureCameraRevision:i.cameraRevision)+1n;
      await this.update({operation,args:operation===4?[i.camera.zoom+args[0]]:args,sequence:this.gestureSequence,cameraRevision:this.gestureCameraRevision,timeRevision:i.timeRevision,stateRevision:i.stateRevision,time:i.time as XygGeoHostUpdate['time']});
    }).catch(error=>{if(!this.closing)this.gestureError(error);}).finally(()=>{this.gestureQueued--;});
  }
  private gestureAlert?:HTMLElement;
  private gestureError(error:unknown){if(!this.gestureAlert?.isConnected){this.gestureAlert=document.createElement('p');this.gestureAlert.setAttribute('role','alert');this.el.append(this.gestureAlert);}this.gestureAlert.textContent=error instanceof Error?error.message:String(error);}
  private liveNonce=0n;
  private updating=false;
  private activeOperation?:number;
  private desired?:{input:XygGeoHostUpdate;resolve:()=>void;reject:(e:unknown)=>void};
  private retirement?:ArrayBuffer;
  private aborted?:ArrayBuffer;
  private pendingPrepare?:ArrayBuffer;
  private pendingCommit?:{tag:ReturnType<typeof liveTag>;holder:HTMLElement;view:XygWasmSceneView;data:HostData};
  private owner = 0n;
  private sequence = 0n;
  private view?: XygWasmSceneView;
  private data?: HostData;
  private gestureEvents = ["pointerdown","pointermove","pointerup","pointercancel","wheel","dblclick","click","keydown"];
  private pointer?:{id:number;x:number;y:number;capture:ReturnType<typeof captureGesturePointer>};
  private previousTouchAction:string;
  private gestureSequence=0n;
  private gestureCameraRevision=0n;
  private freezeGesture = (event:Event) => {
    if(event.target instanceof Element && event.target.closest("[data-xy-overview-counts]") && this.el.contains(event.target)) return;
    if(event instanceof KeyboardEvent && event.key === "Tab") return;
    event.preventDefault();event.stopImmediatePropagation();
    if(!event.isTrusted||!this.data||this.closing)return;
    if(event instanceof PointerEvent){
      if(event.type==='pointerdown'&&event.isPrimary&&event.button===0){
        this.releasePointer();
        const capture=captureGesturePointer({
          _listen:(owner:HTMLElement,type:string,listener:EventListener)=>owner.addEventListener(type,listener),
          _unlisten:(listener:EventListener)=>this.el.removeEventListener('lostpointercapture',listener),
        },this.el,event,()=>this.releasePointer());
        this.pointer={id:event.pointerId,x:event.clientX,y:event.clientY,capture};
      }else if(event.pointerId===this.pointer?.id&&this.pointer.capture.guard(event)){
        if(event.type==='pointermove'&&(event.buttons&1)){
          const rect=this.view!.canvas.getBoundingClientRect(),camera=this.data.identity.camera;
          const dx=this.pointer.x-event.clientX,dy=this.pointer.y-event.clientY;
          this.pointer.x=event.clientX;this.pointer.y=event.clientY;
          if(rect.width>0&&rect.height>0&&(dx||dy))this.queueGesture([dx*camera.width/rect.width,dy*camera.height/rect.height]);
        }else if(event.type!=='pointermove'||!(event.buttons&1)){
          this.releasePointer();
        }
      }
    }else if(event instanceof WheelEvent&&event.deltaY){
      const rect=this.view!.canvas.getBoundingClientRect();
      const pixels=event.deltaY*(event.deltaMode===1?16:event.deltaMode===2?rect.height:1);
      this.queueGesture([-pixels/480],4);
    }
    if(event instanceof KeyboardEvent&&event.isTrusted&&this.data&&!this.closing){
      const moves:Record<string,readonly number[]>={ArrowLeft:[-40,0],ArrowRight:[40,0],ArrowUp:[0,-40],ArrowDown:[0,40]};
      const args=moves[event.key];if(args)this.queueGesture(args);

    }
  };
  private releasePointer(){const pointer=this.pointer;this.pointer=undefined;pointer?.capture.release();}
  private dropGestureGuard(){this.releasePointer();this.gestureAlert=undefined;if(this.el.style.touchAction==='none')this.el.style.touchAction=this.previousTouchAction;for(const type of this.gestureEvents)this.el.removeEventListener(type,this.freezeGesture,true);}


  constructor(private el: HTMLElement, private comm: XygGeoHostComm) {
    // Native frames route trusted input through Rust camera authoring; the
    // ordinary ChartView must never reinterpret their immutable geometry.
    this.previousTouchAction=el.style.touchAction;el.style.touchAction='none';
    for(const type of this.gestureEvents)el.addEventListener(type,this.freezeGesture,{capture:true,passive:false});
    try{this.unsubscribe = comm.onMessage((message, buffers) => {
      if(message?.type === 'geo_host_update'){
        const request=message.request;if(typeof request!=='string'||request.length<1||request.length>96)return;
        try{
          if(buffers.length!==1)throw TypeError('one binary update required');const raw=ownedBuffer(buffers[0]),v=new DataView(raw);
          if(raw.byteLength!==128||v.getUint32(0,true)!==0x55485958||v.getUint32(4,true)!==1||v.getUint32(52,true)||new Uint8Array(raw,112).some(x=>x))throw TypeError('invalid XYHU authoring');
          const count=v.getUint32(12,true);if(count>5)throw TypeError('invalid camera argument count');
          const args=Array.from({length:count},(_,n)=>v.getFloat64(56+n*8,true));if(new Uint8Array(raw,56+count*8,40-count*8).some(x=>x))throw TypeError('nonzero unused camera arguments');
          const kind=v.getUint32(48,true) as 0|1|2,start=v.getBigInt64(96,true),end=v.getBigInt64(104,true);if(kind===0&&(start||end)||kind===1&&end)throw TypeError('noncanonical time authoring');
          const operation=v.getUint32(8,true),input={operation,args,sequence:v.getBigUint64(16,true),cameraRevision:v.getBigUint64(24,true),timeRevision:v.getBigUint64(32,true),stateRevision:v.getBigUint64(40,true),time:{kind,...kind===1?{instant:start}:kind===2?{start,end}:{}}};
          void this.update(input).then(()=>comm.send({type:'geo_host_updated',request}),error=>comm.send({type:'geo_host_updated',request,error:error instanceof Error?error.message:String(error)}));
        }catch(error){comm.send({type:'geo_host_updated',request,error:error instanceof Error?error.message:String(error)});}return;
      }
      if (message?.type === "geo_host_close") { void this.dispose().catch(()=>{}); return; }
      if (message?.type !== "geo_host") return;
      const p = this.pending.get(message.request); if (!p) return;
      this.pending.delete(message.request);
      if (typeof message.error === "string") p.reject(Object.assign(new Error(message.error),{prepareAbsent:message.prepareAbsent===true})); else p.resolve(buffers || []);
    });}catch(error){this.dropGestureGuard();throw error;}
    this.ready = this.enqueue(async () => {
      let buffers: any[] | undefined, data: HostData | undefined;
      let candidate: XygWasmSceneView | undefined;
      try {
        buffers = await this.rpc(header(1));
        if (buffers.length !== 3) throw new TypeError("invalid native geographic frame attachments");
        const tag = replyHeader(buffers[0],1); this.owner=tag.owner; this.sequence=tag.sequence;
        data = parseHostData(ownedBuffer(buffers[1]));
        if (!this.owner || data.identity.sequence !== this.sequence) throw new TypeError("mismatched native frame identity");
        const holder = document.createElement("div");
        // Native XYPB15 is the same Rust painter format; no Worker capability
        // or scene preparation occurs on this path.
        candidate = hydrateWasmPainter(holder, {painter:ownedBuffer(buffers[2]), memoryBytes:0} as XygWasmScenePaint);
        if (this.closing) throw new Error("native geographic view disposed during preparation");
        this.appendCounts(holder,data);this.el.replaceChildren(holder); this.view=candidate; candidate.draw(); candidate=undefined; this.data=data; data=undefined;
      } catch (error) {
        candidate?.destroy(); candidate=undefined; this.view=undefined; this.el.replaceChildren(); data=undefined; buffers=undefined;
        if (this.owner) { await this.rpc(header(4,this.owner,this.sequence)); this.owner=0n; }
        this.closing=true; this.unsubscribe(); this.dropGestureGuard();
        throw error;
      } finally { buffers=undefined; data=undefined; }
    });
    this.ready.catch(()=>{});
  }
  private rpc(buffer:ArrayBuffer):Promise<any[]> {
    const request = `${this.mount}:${++this.serial}`;
    return new Promise((resolve,reject) => {
      this.pending.set(request,{resolve,reject});
      try { this.comm.send({type:"geo_host",request,mount:this.mount},[buffer]); }
      catch(error) { this.pending.delete(request); reject(error instanceof Error?error:new Error(String(error))); }
    });
  }
  private enqueue<T>(run:()=>Promise<T>):Promise<T> {
    if (this.queued >= 16) return Promise.reject(new RangeError("native geographic host queue is full"));
    this.queued++; const operation=this.chain.then(run);
    this.chain=operation.then(()=>{},()=>{}).finally(()=>{this.queued--;}); return operation;
  }
  private live(){if(this.closing || !this.data)throw new Error("native geographic view is not mounted");}
  get identity(){this.live();const i=this.data!.identity;return {...i,camera:{...i.camera},time:{...i.time},sourceDigest:i.sourceDigest.slice()};}
  record(index:number){this.live();if(overviewData(this.data!))throw new Error("Overview has domain counts, not source feature records");return this.data!.record(index);}
  private countsPage=0;
  private appendCounts(holder:HTMLElement,data:HostData){
    if(!overviewData(data))return;
    holder.querySelector('[data-xy-overview-counts]')?.remove();
    const panel=document.createElement('section'),notice=document.createElement('p'),table=document.createElement('table'),caption=document.createElement('caption'),body=document.createElement('tbody'),previous=document.createElement('button'),next=document.createElement('button');
    panel.dataset.xyOverviewCounts='';
    panel.setAttribute('aria-label','Temporal-exact data-domain counts; spatial refinement pending');notice.textContent='Temporal-exact data-domain overview; spatial refinement pending.';notice.setAttribute('role','status');caption.textContent='Domain cells, exact temporal vertex counts; spatial refinement pending';table.append(caption,body);
    for(const button of [previous,next])button.type='button';previous.textContent='Previous 32 domain cells';next.textContent='Next 32 domain cells';previous.dataset.domainPage='previous';next.dataset.domainPage='next';
    const draw=()=>{const rows=document.createDocumentFragment();for(let i=this.countsPage*32;i<(this.countsPage+1)*32;i++){const tr=document.createElement('tr'),cell=document.createElement('th'),count=document.createElement('td');cell.scope='row';cell.textContent=String(i);count.textContent=String(data.count(i));tr.tabIndex=0;tr.dataset.domainCell=String(i);tr.setAttribute('aria-label',`Domain cell ${i}, ${data.count(i)} exact temporal vertices; spatial refinement pending`);tr.append(cell,count);rows.append(tr);}body.replaceChildren(rows);previous.disabled=this.countsPage===0;next.disabled=this.countsPage===7;};
    previous.onclick=()=>{this.countsPage=Math.max(0,this.countsPage-1);draw();};next.onclick=()=>{this.countsPage=Math.min(7,this.countsPage+1);draw();};draw();panel.append(notice,table,previous,next);holder.append(panel);
  }
  /** Author exact revisions/time; Rust applies the camera delta and rebuilds. */
  update(input:XygGeoHostUpdate):Promise<void>{
    this.live();
    if(input.operation===3&&this.updating)throw new Error('Incremental geographic pan requires serialized updates');
    if(this.desired&&this.desired.input.operation!==input.operation)throw new Error('Distinct geographic camera edits require serialized updates');
    if(!Number.isInteger(input.operation)||input.operation<0||input.operation>9||input.args.length>5||input.args.some(x=>!Number.isFinite(x))||![0,1,2].includes(input.time.kind))throw TypeError('invalid live authoring');
    for(const n of [input.sequence,input.cameraRevision,input.timeRevision,input.stateRevision])if(typeof n!=='bigint'||n<0n||n>0xffffffffffffffffn)throw TypeError('exact u64 live revisions required');
    if(input.sequence>this.gestureSequence)this.gestureSequence=input.sequence;if(input.cameraRevision>this.gestureCameraRevision)this.gestureCameraRevision=input.cameraRevision;
    for(const key of Object.keys(input.time))if(!(['kind',...(input.time.kind===1?['instant']:input.time.kind===2?['start','end']:[])]).includes(key))throw TypeError('unsupported signed time field');
    for(const n of input.time.kind===1?[input.time.instant]:input.time.kind===2?[input.time.start,input.time.end]:[])if(typeof n!=='bigint'||n< -0x8000000000000000n||n>0x7fffffffffffffffn)throw TypeError('exact signed i64 time required');
    const snapshot={...input,args:[...input.args],time:{...input.time}};
    const result=new Promise<void>((resolve,reject)=>{
      this.desired?.reject(new DOMException('Superseded geographic update','AbortError'));
      this.desired={input:snapshot,resolve,reject};
    });
    if(!this.updating){this.updating=true;void this.enqueue(async()=>{
      try{while(this.desired&&!this.closing){const next=this.desired;this.desired=undefined;this.activeOperation=next.input.operation;try{await this.replace(next.input);next.resolve();}catch(error){next.reject(error);}finally{this.activeOperation=undefined;}}}
      finally{this.updating=false;if(this.closing){this.desired?.reject(new Error('geographic view disposed'));this.desired=undefined;}}
    }).catch(error=>{this.updating=false;this.desired?.reject(error);this.desired=undefined;});}
    return result;
  }
  private assertSelected(data:HostData){
    if(overviewData(this.data!)){if(!overviewData(data))throw TypeError("Candidate lost overview mode");return;}
    if(overviewData(data))throw TypeError("Candidate changed native frame mode");
    const before=this.data!.selection,after=data.selection;
    if(!!before!==!!after)throw TypeError('candidate lost selected intent');
    if(before&&after){if(before.namespace!==after.namespace||before.idCount!==after.idCount||before.fill.some((x,n)=>x!==after.fill[n]))throw TypeError('candidate changed selected profile');for(let i=0;i<before.idCount;i++)if(before.id(i)!==after.id(i))throw TypeError('candidate changed selected IDs');}
  }
  /** Retry an uncertain exact commit or retirement without issuing another query. */
  recover():Promise<void>{if(this.closing)throw Error("Geographic view is closing; retry dispose instead");return this.enqueue(async()=>{await this.recoverPrepare();await this.recoverCommit();await this.abortCandidate();await this.retire();});}
  private async recoverPrepare(){
    const request=this.pendingPrepare;if(!request)return;
    let buffers:any[]|undefined;try{buffers=await this.rpc(request);}catch(error){if((error as any)?.prepareAbsent===true){this.pendingPrepare=undefined;return;}throw error;}
    if(buffers.length!==3)throw TypeError('invalid preparation recovery');
    const tag=liveTag(buffers[0],6),v=new DataView(request);
    if(tag.old!==v.getBigUint64(16,true)||tag.oldSequence!==v.getBigUint64(24,true)||tag.nonce!==v.getBigUint64(32,true)||tag.sequence!==v.getBigUint64(40,true)||!tag.owner)throw TypeError('unowned preparation recovery');
    buffers=undefined;this.aborted=liveHeader(9,tag.old,tag.oldSequence,tag.nonce,tag.owner,tag.sequence);this.pendingPrepare=undefined;await this.abortCandidate();
  }
  private async recoverCommit(){
    const pending=this.pendingCommit;if(!pending)return;const {tag}=pending;
    const response=await this.rpc(liveHeader(7,tag.old,tag.oldSequence,tag.nonce,tag.owner,tag.sequence));
    if(response.length!==1)throw TypeError('invalid commit confirmation');const h=liveTag(response[0],7);
    if(h.old!==tag.old||h.oldSequence!==tag.oldSequence||h.nonce!==tag.nonce||h.owner!==tag.owner||h.sequence!==tag.sequence)throw TypeError('mismatched commit confirmation');
    const focused=document.activeElement;const focusCell=focused instanceof HTMLElement&&this.el.contains(focused)?focused.dataset.domainCell:undefined,focusPage=focused instanceof HTMLElement&&this.el.contains(focused)?focused.dataset.domainPage:undefined;
    this.appendCounts(pending.holder,pending.data);
    let previous=this.view;this.el.replaceChildren(pending.holder);
    if(focusCell!==undefined)pending.holder.querySelector<HTMLElement>(`[data-domain-cell="${focusCell}"]`)?.focus();else if(focusPage!==undefined)pending.holder.querySelector<HTMLElement>(`[data-domain-page="${focusPage}"]`)?.focus();this.view=pending.view;this.data=pending.data;this.owner=tag.owner;this.sequence=tag.sequence;this.pendingCommit=undefined;previous?.destroy();previous=undefined;
    this.retirement=liveHeader(8,tag.old,tag.oldSequence,tag.nonce,tag.owner,tag.sequence);await this.retire();
  }
  private async abortCandidate(){if(this.aborted){await this.rpc(this.aborted);this.aborted=undefined;}}
  private async retire(){if(this.retirement){await this.rpc(this.retirement);this.retirement=undefined;}}
  private async replace(input:XygGeoHostUpdate){
    await this.recoverPrepare();await this.recoverCommit();await this.abortCandidate();await this.retire();this.live();const baseline=this.identity,old=this.owner,oldSequence=this.sequence,nonce=++this.liveNonce;
    if(nonce>0xffffffffffffffffn)throw RangeError('geographic candidate nonce exhausted');
    const request=header(6,old,oldSequence,224),v=new DataView(request);v.setUint32(4,2,true);
    [nonce,input.sequence,input.cameraRevision,input.timeRevision,input.stateRevision].forEach((n,i)=>v.setBigUint64(32+i*8,n,true));
    v.setUint32(72,input.time.kind,true);v.setBigInt64(80,input.time.kind===1?input.time.instant!:input.time.kind===2?input.time.start!:0n,true);v.setBigInt64(88,input.time.kind===2?input.time.end!:0n,true);
    new Uint8Array(request).set(new Uint8Array(encodeGeoViewportRequest(baseline.camera,input.operation,input.args)),96);
    let buffers:any[]|undefined,data:HostData|undefined,candidate:XygWasmSceneView|undefined,tag:ReturnType<typeof liveTag>|undefined,committed=false;
    try{
      this.pendingPrepare=request;buffers=await this.rpc(request);if(buffers.length!==3)throw TypeError('invalid geographic candidate attachments');const preparedTag=liveTag(buffers[0],6);
      if(preparedTag.old!==old||preparedTag.oldSequence!==oldSequence||preparedTag.nonce!==nonce||preparedTag.sequence!==input.sequence||!preparedTag.owner)throw TypeError('unowned geographic candidate');
      tag=preparedTag;this.pendingPrepare=undefined;data=parseHostData(ownedBuffer(buffers[1]));const i=data.identity;
      if(i.sequence!==input.sequence||i.cameraRevision!==input.cameraRevision||i.timeRevision!==input.timeRevision||i.stateRevision!==input.stateRevision||i.generation!==baseline.generation||i.layerId!==baseline.layerId||i.layerRevision!==baseline.layerRevision||i.styleRevision!==baseline.styleRevision||i.sourceRows!==baseline.sourceRows||i.sourceCrs!==baseline.sourceCrs||i.geometry!==baseline.geometry||i.sourceDigest.some((x,n)=>x!==baseline.sourceDigest[n])||i.time.kind!==input.time.kind||i.time.kind===1&&i.time.instant!==input.time.instant||i.time.kind===2&&(i.time.start!==input.time.start||i.time.end!==input.time.end))throw TypeError('candidate snapshot differs from authoring');
      this.assertSelected(data);
      const holder=document.createElement('div');candidate=hydrateWasmPainter(holder,{painter:ownedBuffer(buffers[2]),memoryBytes:0} as XygWasmScenePaint);candidate.draw();
      if(this.closing||this.desired&&this.desired.input.operation===input.operation)throw new DOMException('Superseded geographic update','AbortError');
      this.appendCounts(holder,data);this.pendingCommit={tag,holder,view:candidate,data};candidate=undefined;data=undefined;buffers=undefined;
      await this.recoverCommit();committed=true;

    }catch(error){if((error as any)?.prepareAbsent===true)this.pendingPrepare=undefined;candidate?.destroy();candidate=undefined;data=undefined;buffers=undefined;if(tag&&!committed&&!this.pendingCommit&&!(this.owner===tag.owner&&this.sequence===tag.sequence)){this.aborted=liveHeader(9,old,oldSequence,nonce,tag.owner,tag.sequence);await this.abortCandidate();}throw error;}
    finally{data=undefined;buffers=undefined;}
  }
  pick(input:{x:number;y:number;tolerance?:number;mode?:number;maxHits?:number}) {
    this.live();if(overviewData(this.data!))throw Error("Overview source-feature picking is unsupported");
    if (![input.x,input.y,input.tolerance??0].every(n=>typeof n==="number"&&Number.isFinite(n)) || ![0,1].includes(input.mode??1) || !Number.isInteger(input.maxHits??64) || (input.maxHits??64)<1 || (input.maxHits??64)>4096) throw new TypeError("invalid native pick framing");
    const buffer=header(2,this.owner,this.sequence,32),v=new DataView(buffer);
    v.setFloat64(32,input.x,true);v.setFloat64(40,input.y,true);v.setFloat64(48,input.tolerance??0,true);v.setUint32(56,input.mode??1,true);v.setUint32(60,input.maxHits??64,true);
    return this.aux(buffer,2,parseGeoHitData);
  }
  membership(cell:number,input:{maxProjectedVertices:bigint;cursor?:Uint8Array}) {
    const cursor=input.cursor;
    this.live();if(overviewData(this.data!))throw Error("Overview domain membership uses its distinct authority");if(!Number.isInteger(cell)||cell<0||cell>0xffffffff||cursor&&(cursor.byteLength!==208||cursor.buffer.byteLength!==208))throw new TypeError("invalid native membership framing");
    const buffer=header(3,this.owner,this.sequence,16+(cursor?208:0)),v=new DataView(buffer);
    v.setUint32(32,cell,true);v.setUint32(36,cursor?1:0,true);if(typeof input.maxProjectedVertices!=="bigint"||input.maxProjectedVertices<0n||input.maxProjectedVertices>0xffffffffffffffffn)throw new TypeError("invalid membership work bound");v.setBigUint64(40,input.maxProjectedVertices,true);if(cursor)new Uint8Array(buffer).set(cursor,48);
    return this.aux(buffer,3,parseGeoMembershipData);
  }
  private aux(buffer:ArrayBuffer,op:number,parse:typeof parseGeoHitData|typeof parseGeoMembershipData) {
    return this.enqueue(async()=>{
      let buffers:any[]|undefined, parsed:ReturnType<typeof parse>|undefined, owner=0n;
      try {
        buffers=await this.rpc(buffer);if(buffers.length!==2)throw new TypeError("invalid auxiliary attachments");
        const h=replyHeader(buffers[0],op);owner=h.owner;if(!owner||h.sequence!==this.sequence)throw new TypeError("stale auxiliary reply");
        parsed=parse(ownedBuffer(buffers[1]));if(parsed.owner!==this.owner||parsed.sequence!==this.sequence)throw new TypeError("unowned auxiliary reply");
        const records=Array.from({length:parsed.length},(_,i)=>parsed!.record(i));
        const cursor="cursor" in parsed?parsed.cursor?.slice():undefined;
        return {records,cursor};
      }finally{parsed=undefined;buffers=undefined;if(owner)await this.rpc(header(5,owner,this.sequence));}
    });
  }
  dispose():Promise<void> {
    if(this.disposal)return this.disposal;this.closing=true;this.releasePointer();this.desired?.reject(new Error('geographic view disposed'));this.desired=undefined;
    return this.disposal=this.chain.then(async()=>{
      await this.gestureChain;
      await this.recoverPrepare();await this.recoverCommit();await this.abortCandidate();await this.retire();
      this.view?.destroy();this.view=undefined;this.data=undefined;this.el.replaceChildren();
      if(this.owner){await this.rpc(header(4,this.owner,this.sequence));this.owner=0n;}
      this.unsubscribe();this.dropGestureGuard();
    }).catch(error=>{this.disposal=undefined;throw error;});
  }
  destroy(){void this.dispose().catch(()=>{});}
}

export function renderGeoHost({model,el}:{model:any;el:HTMLElement}){
  const view=new XygGeoHostView(el,{
    send:(message,buffers)=>model.send(message,undefined,buffers?.map(buffer=>new DataView(buffer))),
    onMessage:callback=>{const listener=(message:any,buffers:any[])=>callback(message,buffers);model.on("msg:custom",listener);return()=>model.off?.("msg:custom",listener);},
  });
  view.ready.catch(error=>{const alert=document.createElement("p");alert.setAttribute("role","alert");alert.textContent=error instanceof Error?error.message:String(error);el.replaceChildren(alert);});
  return ()=>{void view.dispose().catch(()=>{});};
}
