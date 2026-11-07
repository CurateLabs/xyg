/** Thin binary framing for Rust XYFG/XYFX. No geometry/style/temporal policy. */
import type {XygWasmWorker} from './47_wasm';
export function frozenPacket(data:Uint8Array,operation:number,format=0,focus?:readonly number[],scale=1,client:Uint8Array=new Uint8Array(),budget=384*1024*1024):Uint8Array<ArrayBuffer> {
  if(([1,3,4].includes(operation)&&data.byteLength>24*1024*1024)||client.byteLength>8*1024*1024||data.byteLength+client.byteLength>budget/4)throw new RangeError('frozen input exceeds admission');
  const packet=new Uint8Array(64+data.length+client.length),v=new DataView(packet.buffer);packet.set([88,89,70,88]);v.setUint32(4,1,true);v.setUint32(8,operation,true);v.setUint32(12,format,true);
  if(focus){if(focus.length!==4||focus.some(n=>!Number.isInteger(n)||n<0||n>255))throw new TypeError('four focus bytes required');packet.set(focus,16);v.setUint32(20,1,true);}
  v.setFloat64(24,scale,true);v.setBigUint64(32,BigInt(data.length),true);v.setBigUint64(40,BigInt(client.length),true);v.setBigUint64(48,BigInt(budget),true);packet.set(data,64);packet.set(client,64+data.length);return packet;
}
const issued=Symbol('Rust frozen graph');
export class XygFrozenTemporalGraph {
  #bytes:Uint8Array;
  constructor(token:symbol,bytes:Uint8Array){if(token!==issued)throw new TypeError('use session.freeze or XygFrozenTemporalGraph.fromBytes');if(!(bytes instanceof Uint8Array)||bytes.byteLength>24*1024*1024)throw new RangeError('bounded XYFG required');this.#bytes=bytes.slice();}
  toBytes():Uint8Array{return this.#bytes.slice();}
  static async fromBytes(bytes:Uint8Array,worker:XygWasmWorker):Promise<XygFrozenTemporalGraph>{await worker.ready;return new XygFrozenTemporalGraph(issued,new Uint8Array(await worker.frozenGraphCommand(frozenPacket(bytes,4).buffer)));}
  static async fromArtifact(bytes:Uint8Array,worker:XygWasmWorker,client?:Uint8Array):Promise<XygFrozenTemporalGraph>{await worker.ready;return new XygFrozenTemporalGraph(issued,new Uint8Array(await worker.frozenGraphCommand(frozenPacket(bytes,2,0,undefined,1,client).buffer)));}
  async captureFocus(focus:readonly number[],worker:XygWasmWorker):Promise<XygFrozenTemporalGraph>{await worker.ready;return new XygFrozenTemporalGraph(issued,new Uint8Array(await worker.frozenGraphCommand(frozenPacket(this.#bytes,3,0,focus).buffer)));}
  async export(format:'svg'|'png'|'html'|'scene'|'painter',options:{worker:XygWasmWorker;client?:Uint8Array;scale?:number;focusRgba?:readonly number[]}):Promise<Uint8Array>{
    await options.worker.ready;
    const code={svg:0,png:1,html:2,scene:3,painter:4}[format];if(code===undefined)throw new TypeError('unknown frozen format');
    if(format==='html'&&!options.client?.length)throw new TypeError('HTML requires the shipped standalone client bytes');
    return new Uint8Array(await options.worker.frozenGraphCommand(frozenPacket(this.#bytes,1,code,options.focusRgba,options.scale??1,options.client).buffer));
  }
}

/** @internal Issued only by the accepted retained Worker freeze reply. */
export function issuedFrozenGraph(bytes:Uint8Array):XygFrozenTemporalGraph{return new XygFrozenTemporalGraph(issued,bytes);}
