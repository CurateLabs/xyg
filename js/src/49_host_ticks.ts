/** Host transport for the same packed Rust XYTK/XYTO contract used by WASM. */
import { XygWasmError } from './47_wasm';

export interface XygHostTickTransport {
  resolve(request: ArrayBuffer, context: {requestId:number;sequence:number;signal:AbortSignal}): Promise<ArrayBuffer>;
  dispose?(): void | Promise<void>;
}
export class XygHostTickEngine {
  readonly ready=Promise.resolve();
  readonly hostKind='native' as const;
  private sequence=0;
  private requestId=0;
  private disposed=false;
  private pending=new Set<AbortController>();
  constructor(private readonly transport:XygHostTickTransport) {
    if(!transport||typeof transport.resolve!=='function')throw new TypeError('native tick transport is required');
  }
  allocateTickSequence():number {
    if(this.disposed)throw new XygWasmError('XYG_WASM_DISPOSED','Native tick host is disposed');
    if(this.sequence===0xffffffff)throw new RangeError('native tick sequence exhausted');
    return ++this.sequence;
  }
  resolveTicks(request:ArrayBuffer,{sequence}:{sequence:number}) {
    if(this.disposed)throw new XygWasmError('XYG_WASM_DISPOSED','Native tick host is disposed');
    if(!(request instanceof ArrayBuffer)||request.byteLength<32||request.byteLength>1024*1024||!Number.isInteger(sequence)||sequence<1||sequence>0xffffffff)throw new TypeError('invalid packed tick request');
    if(new DataView(request).getUint32(12,true)!==sequence)throw new TypeError('tick request header sequence must match the task sequence');
    this.sequence=Math.max(this.sequence,sequence);
    if(this.requestId===0xffffffff)throw new RangeError('native tick request identity exhausted');
    const requestId=++this.requestId,controller=new AbortController();this.pending.add(controller);
    let reject!:(reason:unknown)=>void;
    const aborted=new Promise<never>((_,r)=>{reject=r;});
    const cancel=()=>{if(controller.signal.aborted)return;controller.abort();reject(new XygWasmError('XYG_WASM_CANCELLED','Native tick request cancelled'));};
    controller.signal.addEventListener('abort',()=>reject(new XygWasmError('XYG_WASM_CANCELLED','Native tick request cancelled')),{once:true});
    const result=Promise.race([Promise.resolve().then(()=>{if(controller.signal.aborted||this.disposed)throw new XygWasmError('XYG_WASM_CANCELLED','Native tick request cancelled before dispatch');return this.transport.resolve(request,{requestId,sequence,signal:controller.signal});}),aborted]).then(output=>{
      if(controller.signal.aborted||this.disposed)throw new XygWasmError('XYG_WASM_CANCELLED','Native tick response superseded');
      if(!(output instanceof ArrayBuffer)||output.byteLength>4*1024*1024)throw new TypeError('invalid native packed tick response');
      return output;
    }).finally(()=>this.pending.delete(controller));
    return {requestId,sequence,result,cancel};
  }
  async dispose(){if(this.disposed)return;this.disposed=true;for(const controller of this.pending)controller.abort();this.pending.clear();await this.transport.dispose?.();}
}
export function createHostTickEngine(transport:XygHostTickTransport):XygHostTickEngine{return new XygHostTickEngine(transport);}
