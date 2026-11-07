import {readFileSync} from 'node:fs';
import {standaloneClientPath} from './html.js';
/** Immutable native XYFG ownership. No graph filtering, layout or export policy. */
import {
  xyTemporalGraphFreeze, xyTemporalGraphFrozenImport,
  xyTemporalGraphFrozenCopy, xyTemporalGraphFrozenDestroy, xyTemporalGraphFrozenExecute, pointer,
} from './native.js';
import { TemporalGraphError } from './abi.js';
import { decodeContainer } from './graphforge-container.js';
const MAX_BYTES = 24 * 1024 * 1024;
const MAX_PEAK = 384n * 1024n * 1024n;
const check = status => { if (status !== 0) throw new TemporalGraphError(status); };
function scalar(value, name, signed = false) {
  if (typeof value !== 'bigint' || value < (signed ? -(1n<<63n) : 0n) || value >= (signed ? 1n<<63n : 1n<<64n)) throw new TypeError(`${name} must be an exact ${signed?'i64':'u64'} bigint`);
  return value;
}
const ptr = bytes => bytes.length ? pointer(bytes, 'uint8_t *') : null;
const u64ptr = bytes => pointer(bytes, 'uint64_t *');
const issued = Symbol('native frozen graph');
export class FrozenTemporalGraph {
  #handle;
  constructor(token, handle) {
    if (token !== issued) throw new TypeError('use TemporalGraph.freeze or FrozenTemporalGraph.fromBytes');
    this.#handle = handle;
  }
  static fromBytes(data, {budgetBytes = MAX_PEAK} = {}) {
    if (!(data instanceof Uint8Array)) throw new TypeError('data must be Uint8Array');
    if (data.byteLength > MAX_BYTES) throw new TemporalGraphError(-2);
    const raw = data.slice(), handle = new BigUint64Array(1);
    check(xyTemporalGraphFrozenImport(ptr(raw), BigInt(raw.length), scalar(budgetBytes,'budgetBytes'), u64ptr(handle)));
    return new FrozenTemporalGraph(issued,handle[0]);
  }
  toBytes() {
    if (this.#handle == null) throw new Error('FrozenTemporalGraph is closed');
    const size = new BigUint64Array(1);
    const status = xyTemporalGraphFrozenCopy(this.#handle, null, 0n, u64ptr(size));
    if (status !== -9) check(status);
    const bytes = new Uint8Array(Number(size[0]));
    check(xyTemporalGraphFrozenCopy(this.#handle, ptr(bytes), BigInt(bytes.length), u64ptr(size)));
    return bytes;
  }
  export(format, {focusRgba, scale=1, budgetBytes=MAX_PEAK}={}) {
    const code={svg:0,png:1,html:2,scene:3,painter:4}[format];
    if (code===undefined) throw new TypeError('unknown frozen format');
    return executePacket(this.toBytes(),1,code,scale,focusRgba,budgetBytes,format==='html'?readFileSync(standaloneClientPath()):new Uint8Array());
  }
  static fromArtifact(data,{budgetBytes=MAX_PEAK}={}) {
    return this.fromBytes(executePacket(data,2,0,1,null,budgetBytes,new TextDecoder().decode(data.subarray(0,15))==='<!doctype html>'?readFileSync(standaloneClientPath()):new Uint8Array()),{budgetBytes});
  }
  captureFocus(focusRgba,{budgetBytes=MAX_PEAK}={}) {
    return FrozenTemporalGraph.fromBytes(executePacket(this.toBytes(),3,0,1,focusRgba,budgetBytes),{budgetBytes});
  }
  get metadata() {
    const bytes = this.toBytes();
    const fields = decodeContainer(bytes.subarray(0,bytes.length-8),'XYFG');
    const result = {};
    for (const [key,field] of fields) {
      const value = field.value;
      result[key.slice(0,-2)] = ArrayBuffer.isView(value) && !(value instanceof Uint8Array) ? Object.freeze(Array.from(value)) : value;
    }
    return Object.freeze(result); // byte getters are fresh copies, never native storage.
  }
  close() {
    const handle=this.#handle; this.#handle=null;
    if (handle!=null) check(xyTemporalGraphFrozenDestroy(handle));
  }
}
export function freezeTemporalGraph(handle, {revision, timezone, window = null, sessionHandle = 0n, renderRevision = 0, budgetBytes = MAX_PEAK}) {
  if (typeof timezone !== 'string') throw new TypeError('timezone must be a string');
  const zone = new TextEncoder().encode(timezone);
  if (zone.length > 128) throw new TemporalGraphError(-4);
  if (window !== null && (!Array.isArray(window) || window.length !== 2)) throw new TypeError('window must be null or [start,end]');
  if (!Number.isInteger(renderRevision) || renderRevision < 0 || renderRevision > 0xffffffff) throw new TypeError('renderRevision must fit u32');
  const out = new BigUint64Array(1);
  check(xyTemporalGraphFreeze(handle, scalar(revision,'revision'), window===null?0:1,
    window===null?0n:scalar(window[0],'window start',true), window===null?0n:scalar(window[1],'window end',true),
    ptr(zone),BigInt(zone.length),scalar(sessionHandle,'sessionHandle'),renderRevision,scalar(budgetBytes,'budgetBytes'),u64ptr(out)));
  return new FrozenTemporalGraph(issued,out[0]);
}

function executePacket(data,operation,format,scale,focus,budget,client=new Uint8Array()) {
  budget=scalar(budget,'budgetBytes');
  if (!(data instanceof Uint8Array) || data.length+client.length>Number((budget<MAX_PEAK?budget:MAX_PEAK)/4n) || ([1,3,4].includes(operation)&&data.length>MAX_BYTES) || client.length>8*1024*1024) throw new TypeError('bounded bytes required');
  if (focus!=null && (!Array.isArray(focus)||focus.length!==4||!focus.every(v=>Number.isInteger(v)&&v>=0&&v<=255))) throw new TypeError('focusRgba requires four byte values');
  const packet=new Uint8Array(64+data.length+client.length),v=new DataView(packet.buffer);packet.set([88,89,70,88]);v.setUint32(4,1,true);v.setUint32(8,operation,true);v.setUint32(12,format,true);
  if(focus!=null){packet.set(focus,16);v.setUint32(20,1,true);}v.setFloat64(24,scale,true);v.setBigUint64(32,BigInt(data.length),true);v.setBigUint64(40,BigInt(client.length),true);v.setBigUint64(48,budget,true);packet.set(data,64);packet.set(client,64+data.length);
  const size=new BigUint64Array(1),call=(out,cap)=>xyTemporalGraphFrozenExecute(ptr(packet),BigInt(packet.length),budget,out,cap,u64ptr(size));const status=call(null,0n);if(status!==-9)check(status);const out=new Uint8Array(Number(size[0]));check(call(ptr(out),BigInt(out.length)));return out;
}
