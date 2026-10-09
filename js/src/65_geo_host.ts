/** Native immutable geographic host transport. Rust owns Scene and picking.
 * One mounted copy; raw binary replies never confer WASM FrameData authority. */
import { hydrateWasmPainter } from "./48_wasm_scene";
import type { XygWasmScenePaint } from "./47_wasm";
import type { XygWasmSceneView } from "./48_wasm_scene";
import { parseGeoSceneData, parseGeoHitData, parseGeoMembershipData } from "./63_geo_source";

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
  private owner = 0n;
  private sequence = 0n;
  private view?: XygWasmSceneView;
  private data?: ReturnType<typeof parseGeoSceneData>;
  private gestureEvents = ["pointerdown","wheel","dblclick","click","keydown"];
  private freezeGesture = (event:Event) => {
    if(event instanceof KeyboardEvent && event.key === "Tab") return;
    event.preventDefault();event.stopImmediatePropagation();
  };
  private dropGestureGuard(){for(const type of this.gestureEvents)this.el.removeEventListener(type,this.freezeGesture,true);}


  constructor(private el: HTMLElement, private comm: XygGeoHostComm) {
    // An immutable native frame cannot reinterpret ordinary ChartView pan
    // or zoom as a new geographic camera. Hosts author a new Rust frame.
    for(const type of this.gestureEvents)el.addEventListener(type,this.freezeGesture,{capture:true,passive:false});
    this.unsubscribe = comm.onMessage((message, buffers) => {
      if (message?.type === "geo_host_close") { void this.dispose().catch(()=>{}); return; }
      if (message?.type !== "geo_host") return;
      const p = this.pending.get(message.request); if (!p) return;
      this.pending.delete(message.request);
      if (typeof message.error === "string") p.reject(new Error(message.error)); else p.resolve(buffers || []);
    });
    this.ready = this.enqueue(async () => {
      let buffers: any[] | undefined, data: ReturnType<typeof parseGeoSceneData> | undefined;
      let candidate: XygWasmSceneView | undefined;
      try {
        buffers = await this.rpc(header(1));
        if (buffers.length !== 3) throw new TypeError("invalid native geographic frame attachments");
        const tag = replyHeader(buffers[0],1); this.owner=tag.owner; this.sequence=tag.sequence;
        data = parseGeoSceneData(ownedBuffer(buffers[1]));
        if (!this.owner || data.identity.sequence !== this.sequence) throw new TypeError("mismatched native frame identity");
        const holder = document.createElement("div");
        // Native XYPB15 is the same Rust painter format; no Worker capability
        // or scene preparation occurs on this path.
        candidate = hydrateWasmPainter(holder, {painter:ownedBuffer(buffers[2]), memoryBytes:0} as XygWasmScenePaint);
        if (this.closing) throw new Error("native geographic view disposed during preparation");
        this.el.replaceChildren(holder); this.view=candidate; candidate.draw(); candidate=undefined; this.data=data; data=undefined;
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
  record(index:number){this.live();return this.data!.record(index);}
  pick(input:{x:number;y:number;tolerance?:number;mode?:number;maxHits?:number}) {
    this.live();
    if (![input.x,input.y,input.tolerance??0].every(n=>typeof n==="number"&&Number.isFinite(n)) || ![0,1].includes(input.mode??1) || !Number.isInteger(input.maxHits??64) || (input.maxHits??64)<1 || (input.maxHits??64)>4096) throw new TypeError("invalid native pick framing");
    const buffer=header(2,this.owner,this.sequence,32),v=new DataView(buffer);
    v.setFloat64(32,input.x,true);v.setFloat64(40,input.y,true);v.setFloat64(48,input.tolerance??0,true);v.setUint32(56,input.mode??1,true);v.setUint32(60,input.maxHits??64,true);
    return this.aux(buffer,2,parseGeoHitData);
  }
  membership(cell:number,input:{maxProjectedVertices:bigint;cursor?:Uint8Array}) {
    const cursor=input.cursor;
    this.live();if(!Number.isInteger(cell)||cell<0||cell>0xffffffff||cursor&&(cursor.byteLength!==208||cursor.buffer.byteLength!==208))throw new TypeError("invalid native membership framing");
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
    if(this.disposal)return this.disposal;this.closing=true;
    return this.disposal=this.chain.then(async()=>{
      this.view?.destroy();this.view=undefined;this.data=undefined;this.el.replaceChildren();
      if(this.owner){await this.rpc(header(4,this.owner,this.sequence));this.owner=0n;}
      this.unsubscribe();this.dropGestureGuard();
    });
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
