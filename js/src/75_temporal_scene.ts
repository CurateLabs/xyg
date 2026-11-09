/** XYTM framing only. Rust owns temporal membership, geometry and tick policy. */
import { attachTemporalControllerView } from './76_temporal_view';
import type { TemporalCompositionControllerBinding } from './76_temporal_view';
import type { XygWasmTemporalController } from './49_wasm_temporal';
import type { XygWasmScenePaint } from './47_wasm';
import { withWasmPresentationLane } from './49_wasm_presentation_lane';
export type { TemporalCompositionControllerBinding } from './76_temporal_view';

export interface TemporalSceneInput {
  kind: 'event'|'interval'|'gantt'|'line'|'bar'|'scatter';
  rows: readonly (readonly [bigint|null,bigint|null,number,bigint])[];
  domain: readonly [bigint,bigint]; cursor?: bigint; timezone: string;
  publication?: ArrayBuffer; dense?: boolean; operation?: 0|1|2|3; cell?: number; offset?: number; limit?: number;
  precision?: number; width?: number; height?: number; title?: string;
  color?: Uint8Array; stroke?: Uint8Array; strokeWidth?: number;
}
function exact(v: bigint, signed=true): bigint {
  if (typeof v !== 'bigint' || v < (signed ? -(1n<<63n) : 0n) || v >= (signed ? 1n<<63n : 1n<<64n)) throw new TypeError('exact timestamp/identity outside wire width');
  return v;
}
/** Exact transport envelope; shared by encoding and public source snapshots. */
export function temporalSceneSize(count: number, timezone: string, title?: string) {
  const size=128+new TextEncoder().encode(timezone).length+new TextEncoder().encode(title??'').length+count*40;
  if(!Number.isSafeInteger(count)||count<0||!Number.isSafeInteger(size)||size>64*1024*1024)throw new RangeError('temporal source exceeds framing budget');
  return size;
}
export function encodeTemporalScene(input: TemporalSceneInput): ArrayBuffer {
  const kind=['event','interval','gantt','line','bar','scatter'].indexOf(input.kind);
  if(kind<0)throw new TypeError('unknown temporal family');
  const zone=new TextEncoder().encode(input.timezone), title=new TextEncoder().encode(input.title??'');
  const n=input.rows.length, size=temporalSceneSize(n,input.timezone,input.title);
  const out=new ArrayBuffer(size), b=new Uint8Array(out), v=new DataView(out);
  b.set([88,89,84,77]);v.setUint32(4,input.dense?2:1,true);v.setUint32(8,kind,true);v.setUint32(12,n,true);
  v.setFloat64(16,input.width??900,true);v.setFloat64(24,input.height??420,true);
  v.setBigInt64(32,exact(input.domain[0]),true);v.setBigInt64(40,exact(input.domain[1]),true);v.setBigInt64(48,exact(input.cursor??input.domain[0]),true);
  v.setUint32(56,zone.length,true);v.setUint32(60,title.length,true);
  const precision=input.precision??2;if(!Number.isInteger(precision)||precision<0||precision>3)throw new TypeError('invalid source precision');
  v.setUint32(64,precision,true);
  for(const [at,paint] of [[72,input.color],[76,input.stroke]] as const){const p=paint??new Uint8Array([31,119,180,255]);if(!(p instanceof Uint8Array)||p.length!==4)throw new TypeError('paint requires RGBA8');b.set(p,at);}
  if(input.dense) {
    for(const [at,value] of [[88,input.operation??0],[92,input.cell??0],[96,input.offset??0],[100,input.limit??0]]) {
      if(!Number.isInteger(value)||value<0||value>0xffffffff)throw new RangeError('dense query fields require u32');
      v.setUint32(at,value,true);
    }
  }
  if(input.operation===1||input.operation===3){if(!input.publication||input.publication.byteLength<64)throw new TypeError('membership requires XYTL publication');b.set(new Uint8Array(input.publication,20,16),104);}
  v.setFloat64(80,input.strokeWidth??1,true);b.set(zone,128);b.set(title,128+zone.length);
  input.rows.forEach(([start,end,value,id],i)=>{const at=128+zone.length+title.length+i*40;
    v.setBigInt64(at,start===null?0n:exact(start),true);v.setBigInt64(at+8,end===null?0n:exact(end),true);
    v.setFloat64(at+16,value,true);v.setBigUint64(at+24,exact(id,false),true);b[at+32]=Number(start!==null);b[at+33]=Number(end!==null);
  });return out;
}

/** Retained immutable packed source; viewport changes cancel obsolete publications. */
export class TemporalComposition {
  private source: ArrayBuffer|null;
  private revision=0;
  private publications=new WeakMap<ArrayBuffer,number>();
  private busy=false;
  private session:{lifetime?:number;disposed?:boolean;disposal?:Promise<void>}={};
  private active:{cancel:()=>void}|null=null;
  private binding:TemporalCompositionControllerBinding|null=null;
  private disposal:Promise<void>|null=null;
  constructor(private worker: import('./47_wasm').XygWasmWorker, input: TemporalSceneInput) {
    this.source=encodeTemporalScene({...input,dense:true});
  }
  viewport(domain: readonly [bigint,bigint],size:{width?:number;height?:number}={}) {
    this.unbound();
    this.live();
    const lo=exact(domain[0]),hi=exact(domain[1]),view=new DataView(this.source!);
    view.setBigInt64(32,lo,true);view.setBigInt64(40,hi,true);
    view.setBigInt64(48,lo,true);
    if(size.width!==undefined)view.setFloat64(16,size.width,true);if(size.height!==undefined)view.setFloat64(24,size.height,true);
    this.cancel();return this;
  }
  private live(){if(!this.source)throw new Error('temporal composition disposed');}
  private unbound(){this.live();if(this.binding)throw new Error('temporal composition has an attached controller');}
  cancel(){this.revision++;this.active?.cancel();}
  dispose(){
    if(this.disposal)return this.disposal;
    this.cancel();this.source=null;
    return this.disposal=(async()=>{try{await this.binding?.dispose();}finally{await this.worker.temporalSceneRelease(this.session);}})();
  }

  /** Mount ordinary Scene paint driven by complete Rust controller snapshots.
   * The attachment owns presentation; the caller retains controller and Worker. */
  attachController(controller:XygWasmTemporalController,options:{el:HTMLElement;onError?:(error:unknown)=>unknown}):TemporalCompositionControllerBinding {
    this.unbound();if(this.busy)throw new Error('temporal operation already in flight');
    let binding:TemporalCompositionControllerBinding|null=null;
    binding=attachTemporalControllerView(controller,options,async state=>{
      this.live();const view=new DataView(this.source!);
      view.setBigInt64(32,exact(state.rangeStart),true);view.setBigInt64(40,exact(state.rangeEnd),true);view.setBigInt64(48,exact(state.cursor),true);
      this.cancel();let prepared:XygWasmScenePaint|null=null;
      await this.execute(0,0,0,0,undefined,undefined,async scene=>{
        const task=this.worker.prepareScene(scene);this.active=task;prepared=await task.result;
      });
      return prepared!;
    },()=>this.cancel(),()=>{if(binding&&this.binding===binding)this.binding=null;});
    this.binding=binding;return binding;
  }

  private async execute(operation:number,cell=0,offset=0,limit=0,publication?:ArrayBuffer,onProgress?:(reply:ArrayBuffer)=>void,consume?:(scene:ArrayBuffer)=>Promise<void>):Promise<ArrayBuffer>{
    this.live();if(this.busy)throw new Error('temporal operation already in flight');
    this.busy=true;const revision=this.revision;
    try {
    return await withWasmPresentationLane(this.worker,async()=>{
    if(revision!==this.revision||!this.source)throw new Error('stale temporal publication');
    const header=new DataView(this.source!);
    const preview=this.worker.temporalScenePreview(this.source!.slice(0,128+header.getUint32(56,true)+header.getUint32(60,true)));this.active=preview;await preview.result;
    if(revision!==this.revision||!this.source)throw new Error('stale temporal publication');
    const packet=this.source!.slice(0),view=new DataView(packet);
    for(const [at,value] of [[88,operation],[92,cell],[96,offset],[100,limit]]){
      if(!Number.isInteger(value)||value<0||value>0xffffffff)throw new RangeError('dense query fields require u32');
      view.setUint32(at,value,true);
    }
    if(operation===1||operation===3){
      if(!publication||this.publications.get(publication)!==revision)throw new Error('stale or foreign temporal publication');
      new Uint8Array(packet,104,16).set(new Uint8Array(publication,20,16));
    }
    const task=this.worker.temporalSceneCompile(packet,{session:this.session,onProgress});this.active=task;
    const result=await task.result;if(revision!==this.revision||!this.source)throw new Error('stale temporal publication');if(operation===2)this.publications.set(result,revision);
    // Painter preparation shares the transaction: its deferred Worker command
    // cannot be overtaken by the next composition's preview/scan sequence.
    if(consume){await consume(result);if(revision!==this.revision||!this.source)throw new Error('stale temporal publication');}
    return result;
    });
    } finally {this.busy=false;this.active=null;}
  }
  scene(options:{onProgress?:(reply:ArrayBuffer)=>void}={}){this.unbound();return this.execute(0,0,0,0,undefined,options.onProgress);}
  metadata(){this.unbound();return this.execute(2);}
  supports(publication:ArrayBuffer,cell:number,offset=0,limit=256){this.unbound();return this.execute(3,cell,offset,limit,publication);}
  members(publication:ArrayBuffer,cell:number,offset=0,limit=256){this.unbound();return this.execute(1,cell,offset,limit,publication);}
}
