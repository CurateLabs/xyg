/** Immutable native XYFG ownership. No graph filtering, layout or export policy. */
import {
  xyTemporalGraphFreeze, xyTemporalGraphFrozenImport,
  xyTemporalGraphFrozenCopy, xyTemporalGraphFrozenDestroy, pointer,
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
