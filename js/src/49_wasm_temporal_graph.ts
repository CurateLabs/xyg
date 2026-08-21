import type { XygWasmTask, XygWasmWorker } from "./47_wasm";
import type { XygWasmGraphCheckpoint, XygWasmGraphRequest } from "./49_wasm_graph";
import { layoutWasmCose } from "./49_wasm_graph";
import {
  XYG_WASM_TEMPORAL_GRAPH_CREATE_HEADER_BYTES as CREATE_HEADER,
  XYG_WASM_TEMPORAL_GRAPH_FRAME_HEADER_BYTES as FRAME_HEADER,
  XYG_WASM_TEMPORAL_GRAPH_MAGIC as MAGIC,
  XYG_WASM_TEMPORAL_GRAPH_MAX_ENTITIES as MAX_ENTITIES,
  XYG_WASM_TEMPORAL_GRAPH_OUTPUT_HEADER_BYTES as OUTPUT_HEADER,
  XYG_WASM_TEMPORAL_GRAPH_OUTPUT_MAGIC as OUTPUT_MAGIC,
  XYG_WASM_TEMPORAL_GRAPH_VERSION as VERSION,
} from "./wasm_abi_generated";

export interface XygTemporalPlane { values: BigInt64Array; validity: Uint8Array; }
export interface XygWasmTemporalGraphBinding {
  nodeIds: Uint8Array; edgeIds: Uint8Array; sourceIds: Uint8Array; targetIds: Uint8Array;
  nodeValidFrom?: XygTemporalPlane; nodeValidTo?: XygTemporalPlane; nodeEventAt?: XygTemporalPlane;
  edgeValidFrom?: XygTemporalPlane; edgeValidTo?: XygTemporalPlane; edgeEventAt?: XygTemporalPlane;
}
export interface XygWasmTemporalGraphFrame {
  revision: bigint; cursor: bigint; range: readonly [bigint, bigint];
  nodeVisibility: Uint8Array; edgeVisibility: Uint8Array;
  visibleNodeIds: Uint8Array; visibleEdgeIds: Uint8Array;
  sources: BigUint64Array; targets: BigUint64Array;
}

function header(op: number, headerBytes: number, bytes: number) { const out = new ArrayBuffer(bytes); const v = new DataView(out); MAGIC.split("").forEach((c, i) => v.setUint8(i, c.charCodeAt(0))); v.setUint32(4, VERSION, true); v.setUint32(8, headerBytes, true); v.setUint32(12, op, true); return v; }
function uuidCount(value: Uint8Array, name: string) { if (!(value instanceof Uint8Array) || value.byteLength % 16) throw new TypeError(`${name} must contain packed 16-byte UUIDs`); return value.byteLength / 16; }
function planeBytes(plane: XygTemporalPlane | undefined, count: number, name: string) { if (!plane) return 0; if (!(plane.values instanceof BigInt64Array) || !(plane.validity instanceof Uint8Array) || plane.values.length !== count || plane.validity.length !== count || plane.validity.some((v) => v > 1)) throw new TypeError(`${name} must contain equal-length i64 values and zero/one validity`); return count * 9; }

export function encodeWasmTemporalGraphCreate(binding: XygWasmTemporalGraphBinding): ArrayBuffer {
  const n = uuidCount(binding.nodeIds, "nodeIds"), m = uuidCount(binding.edgeIds, "edgeIds");
  if (n + m > MAX_ENTITIES || uuidCount(binding.sourceIds, "sourceIds") !== m || uuidCount(binding.targetIds, "targetIds") !== m) throw new RangeError("temporal graph topology exceeds bounds or has unequal edge UUID counts");
  const planes = [binding.nodeValidFrom, binding.nodeValidTo, binding.nodeEventAt, binding.edgeValidFrom, binding.edgeValidTo, binding.edgeEventAt] as const;
  let flags = 0, bytes = CREATE_HEADER + binding.nodeIds.byteLength + binding.edgeIds.byteLength + binding.sourceIds.byteLength + binding.targetIds.byteLength;
  planes.forEach((plane, index) => { if (plane) flags |= 1 << index; bytes += planeBytes(plane, index < 3 ? n : m, `plane[${index}]`); });
  const view = header(1, CREATE_HEADER, bytes); view.setUint32(16, flags, true); view.setUint32(20, n, true); view.setUint32(24, m, true); const out = new Uint8Array(view.buffer); let at = CREATE_HEADER;
  for (const value of [binding.nodeIds, binding.edgeIds, binding.sourceIds, binding.targetIds]) { out.set(value, at); at += value.byteLength; }
  planes.forEach((plane) => { if (!plane) return; out.set(new Uint8Array(plane.values.buffer, plane.values.byteOffset, plane.values.byteLength), at); at += plane.values.byteLength; out.set(plane.validity, at); at += plane.validity.byteLength; });
  return view.buffer;
}

export function encodeWasmTemporalGraphFrame(revision: bigint, cursor: bigint, range: readonly [bigint, bigint], budget: bigint): ArrayBuffer {
  if (revision <= 0n || revision > 0xffffffffffffffffn || budget < 0n || budget > 0xffffffffffffffffn) throw new RangeError("revision and budget must fit u64");
  if (!Array.isArray(range) || range.length !== 2 || cursor < range[0] || cursor >= range[1]) throw new RangeError("cursor must lie in a non-empty half-open range");
  const view = header(2, FRAME_HEADER, FRAME_HEADER); view.setBigUint64(16, revision, true); view.setBigInt64(24, cursor, true); view.setBigInt64(32, range[0], true); view.setBigInt64(40, range[1], true); view.setBigUint64(48, budget, true); return view.buffer;
}

export function decodeWasmTemporalGraphFrame(buffer: ArrayBuffer): XygWasmTemporalGraphFrame {
  if (!(buffer instanceof ArrayBuffer) || buffer.byteLength < OUTPUT_HEADER) throw new TypeError("temporal graph frame is truncated"); const v = new DataView(buffer); let magic = ""; for (let i = 0; i < 4; i++) magic += String.fromCharCode(v.getUint8(i));
  if (magic !== OUTPUT_MAGIC || v.getUint32(4, true) !== VERSION || v.getUint32(8, true) !== OUTPUT_HEADER || v.getUint32(12, true) !== 0) throw new TypeError("temporal graph frame header is incompatible");
  const n = v.getUint32(48, true), m = v.getUint32(52, true), vn = v.getUint32(56, true), ve = v.getUint32(60, true); const expected = OUTPUT_HEADER + n + m + vn * 16 + ve * 16 + ve * 16; if (buffer.byteLength !== expected) throw new TypeError("temporal graph frame length is invalid"); let at = OUTPUT_HEADER;
  const take = (length: number) => { const value = new Uint8Array(buffer.slice(at, at + length)); at += length; return value; }; const nodeVisibility = take(n), edgeVisibility = take(m), visibleNodeIds = take(vn * 16), visibleEdgeIds = take(ve * 16);
  const sources = new BigUint64Array(buffer.slice(at, at + ve * 8)); at += ve * 8; const targets = new BigUint64Array(buffer.slice(at, at + ve * 8));
  return Object.freeze({ revision: v.getBigUint64(16, true), cursor: v.getBigInt64(24, true), range: Object.freeze([v.getBigInt64(32, true), v.getBigInt64(40, true)] as const), nodeVisibility, edgeVisibility, visibleNodeIds, visibleEdgeIds, sources, targets });
}

/** Latest-wins temporal-before-layout coordinator; Rust owns both filtering and layout. */
export class XygWasmTemporalGraph {
  private layout: XygWasmTask<XygWasmGraphCheckpoint> | null = null; private disposed = false; private revision = 0n; private requestedRevision = 0n;
  private constructor(private readonly worker: XygWasmWorker) {}
  static async create(worker: XygWasmWorker, binding: XygWasmTemporalGraphBinding) { await worker.temporalGraphCommand(encodeWasmTemporalGraphCreate(binding)); return new XygWasmTemporalGraph(worker); }
  async frame(options: { revision: bigint; cursor: bigint; range: readonly [bigint, bigint]; budget: bigint }) { if (this.disposed) throw new Error("TemporalGraph is disposed"); if (options.revision <= this.requestedRevision) throw new RangeError("temporal graph revision must be newer"); this.requestedRevision = options.revision; this.layout?.cancel(); this.layout = null; const frame = decodeWasmTemporalGraphFrame(await this.worker.temporalGraphCommand(encodeWasmTemporalGraphFrame(options.revision, options.cursor, options.range, options.budget))); if (frame.revision !== options.revision || this.requestedRevision !== options.revision || this.disposed) throw new Error("Rust temporal graph returned a stale revision"); this.revision = frame.revision; return frame; }
  async frameAndLayout(options: { revision: bigint; cursor: bigint; range: readonly [bigint, bigint]; budget: bigint; layout?: Omit<XygWasmGraphRequest, "sources" | "targets" | "nNodes">; onUpdate?: (checkpoint: XygWasmGraphCheckpoint) => void }) { const frame = await this.frame(options); const revision = Number(frame.revision); if (!Number.isSafeInteger(revision) || revision > 0xffffffff) throw new RangeError("layout revision must fit u32"); const task = layoutWasmCose(this.worker, { ...(options.layout ?? {}), sources: frame.sources, targets: frame.targets, nNodes: frame.visibleNodeIds.byteLength / 16 }, { revision, onUpdate: (checkpoint) => { if (this.revision === frame.revision) options.onUpdate?.(checkpoint); } }); this.layout = task; try { const result = await task.result; if (this.revision !== frame.revision || this.disposed) throw new Error("temporal graph layout reply is stale"); return { frame, layout: result }; } finally { if (this.layout === task) this.layout = null; } }
  dispose() { if (this.disposed) return; this.disposed = true; this.layout?.cancel(); this.layout = null; }
}
