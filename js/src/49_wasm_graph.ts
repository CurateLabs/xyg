import {
  XYG_WASM_GRAPH_DEFAULT_CHUNK_STEPS,
  XYG_WASM_GRAPH_DEFAULT_MAX_WALL_MS,
  XYG_WASM_GRAPH_HEADER_BYTES,
  XYG_WASM_GRAPH_MAGIC,
  XYG_WASM_GRAPH_MAX_EDGES,
  XYG_WASM_GRAPH_MAX_NODES,
  XYG_WASM_GRAPH_OUTPUT_HEADER_BYTES,
  XYG_WASM_GRAPH_OUTPUT_MAGIC,
  XYG_WASM_GRAPH_OUTPUT_VERSION,
  XYG_WASM_GRAPH_VERSION,
} from "./wasm_abi_generated";
import type { XygWasmTask, XygWasmWorker } from "./47_wasm";

export interface XygWasmCoseOptions {
  idealEdgeLength?: number; repulsionStrength?: number; gravityStrength?: number;
  coolingFactor?: number; overlapPadding?: number; componentSpacing?: number;
  bounds?: readonly [number, number, number, number];
}

export interface XygWasmGraphRequest {
  sources: BigUint64Array; targets: BigUint64Array;
  nNodes: number; totalSteps?: number; seed?: number | bigint;
  x?: Float64Array; y?: Float64Array; pinned?: Uint8Array;
  parents?: BigUint64Array; cose?: XygWasmCoseOptions;
}

export interface XygWasmGraphCheckpoint {
  revision: number; step: number; totalSteps: number; alpha: number;
  phase: "initial" | "update" | "complete";
  x: Float64Array; y: Float64Array;
}

const finite = (value: unknown, fallback: number, name: string) => {
  const resolved = value === undefined ? fallback : Number(value);
  if (!Number.isFinite(resolved)) throw new TypeError(`cose.${name} must be finite`);
  return resolved;
};

export function encodeWasmCose(request: XygWasmGraphRequest): ArrayBuffer {
  const n = Number(request?.nNodes); const m = request?.sources?.length;
  if (!Number.isInteger(n) || n < 0 || n > XYG_WASM_GRAPH_MAX_NODES) throw new RangeError("nNodes exceeds the WASM graph bound");
  if (!(request.sources instanceof BigUint64Array) || !(request.targets instanceof BigUint64Array) || m !== request.targets.length || m > XYG_WASM_GRAPH_MAX_EDGES) throw new TypeError("sources and targets must be equal-length BigUint64Array values");
  const hasPositions = request.x !== undefined || request.y !== undefined;
  if (hasPositions && (!(request.x instanceof Float64Array) || !(request.y instanceof Float64Array) || request.x.length !== n || request.y.length !== n)) throw new TypeError("x and y must both be nNodes-length Float64Array values");
  if (request.pinned !== undefined && (!(request.pinned instanceof Uint8Array) || request.pinned.length !== n || request.pinned.some((v) => v > 1))) throw new TypeError("pinned must be a zero/one nNodes-length Uint8Array");
  if (request.pinned?.some(Boolean) && !hasPositions) throw new TypeError("pinned nodes require authored x and y positions");
  if (request.parents !== undefined && (!(request.parents instanceof BigUint64Array) || request.parents.length !== n)) throw new TypeError("parents must be an nNodes-length BigUint64Array");
  const totalSteps = Number(request.totalSteps ?? 300);
  if (!Number.isInteger(totalSteps) || totalSteps <= 0 || totalSteps > 1_000_000) throw new RangeError("totalSteps must be an integer in 1..1000000");
  const c = request.cose ?? {};
  const allowed = new Set(["idealEdgeLength", "repulsionStrength", "gravityStrength", "coolingFactor", "overlapPadding", "componentSpacing", "bounds"]);
  const unknown = Object.keys(c).filter((key) => !allowed.has(key));
  if (unknown.length) throw new TypeError(`unknown CoSE option(s): ${unknown.sort().join(", ")}`);
  const seed = BigInt(request.seed ?? 0);
  if (seed < 0n || seed > 0xffffffffffffffffn) throw new RangeError("seed must fit an unsigned 64-bit integer");
  const values = [finite(c.idealEdgeLength, 1, "idealEdgeLength"), finite(c.repulsionStrength, 1.25, "repulsionStrength"), finite(c.gravityStrength, .08, "gravityStrength"), finite(c.coolingFactor, .985, "coolingFactor"), finite(c.overlapPadding, .35, "overlapPadding"), finite(c.componentSpacing, 2.5, "componentSpacing")];
  if (values[0] <= 0 || values[1] < 0 || values[2] < 0 || values[3] <= 0 || values[3] >= 1 || values[4] < 0 || values[5] < 0) throw new RangeError("CoSE options violate Rust kernel bounds");
  const bounds = c.bounds;
  if (bounds !== undefined && (!Array.isArray(bounds) || bounds.length !== 4 || bounds.some((v) => !Number.isFinite(v)) || bounds[0] > bounds[2] || bounds[1] > bounds[3])) throw new RangeError("cose.bounds must be finite ordered [x0,y0,x1,y1]");
  let flags = hasPositions ? 1 : 0; if (request.pinned) flags |= 2; if (request.parents) flags |= 4; if (bounds) flags |= 8;
  const bytes = XYG_WASM_GRAPH_HEADER_BYTES + m * 16 + (hasPositions ? n * 16 : 0) + (request.pinned ? n : 0) + (request.parents ? n * 8 : 0);
  const out = new ArrayBuffer(bytes); const view = new DataView(out);
  for (let i = 0; i < 4; i++) view.setUint8(i, XYG_WASM_GRAPH_MAGIC.charCodeAt(i));
  view.setUint32(4, XYG_WASM_GRAPH_VERSION, true); view.setUint32(8, XYG_WASM_GRAPH_HEADER_BYTES, true); view.setUint32(12, flags, true);
  view.setUint32(16, n, true); view.setUint32(20, m, true); view.setUint32(24, totalSteps, true); view.setBigUint64(32, seed, true);
  values.forEach((v, i) => view.setFloat64(40 + i * 8, v, true)); (bounds ?? [0, 0, 0, 0]).forEach((v, i) => view.setFloat64(88 + i * 8, v, true));
  let at = XYG_WASM_GRAPH_HEADER_BYTES;
  for (const array of [request.sources, request.targets]) { new Uint8Array(out, at, array.byteLength).set(new Uint8Array(array.buffer, array.byteOffset, array.byteLength)); at += array.byteLength; }
  if (hasPositions) for (const array of [request.x!, request.y!]) { new Uint8Array(out, at, array.byteLength).set(new Uint8Array(array.buffer, array.byteOffset, array.byteLength)); at += array.byteLength; }
  if (request.pinned) { new Uint8Array(out, at, n).set(request.pinned); at += n; }
  if (request.parents) new Uint8Array(out, at, request.parents.byteLength).set(new Uint8Array(request.parents.buffer, request.parents.byteOffset, request.parents.byteLength));
  return out;
}

export function decodeWasmGraphCheckpoint(buffer: ArrayBuffer): XygWasmGraphCheckpoint {
  if (buffer.byteLength < XYG_WASM_GRAPH_OUTPUT_HEADER_BYTES) throw new TypeError("WASM graph checkpoint is truncated");
  const v = new DataView(buffer); let magic = ""; for (let i = 0; i < 4; i++) magic += String.fromCharCode(v.getUint8(i));
  if (magic !== XYG_WASM_GRAPH_OUTPUT_MAGIC || v.getUint32(4, true) !== XYG_WASM_GRAPH_OUTPUT_VERSION || v.getUint32(8, true) !== XYG_WASM_GRAPH_OUTPUT_HEADER_BYTES) throw new TypeError("WASM graph checkpoint header is incompatible");
  const revision = v.getUint32(12, true), step = v.getUint32(16, true), totalSteps = v.getUint32(20, true), n = v.getUint32(24, true), alpha = v.getFloat64(28, true);
  if (buffer.byteLength !== XYG_WASM_GRAPH_OUTPUT_HEADER_BYTES + n * 16) throw new TypeError("WASM graph checkpoint length is invalid");
  const x = new Float64Array(buffer.slice(XYG_WASM_GRAPH_OUTPUT_HEADER_BYTES, XYG_WASM_GRAPH_OUTPUT_HEADER_BYTES + n * 8)); const y = new Float64Array(buffer.slice(XYG_WASM_GRAPH_OUTPUT_HEADER_BYTES + n * 8));
  return { revision, step, totalSteps, alpha, phase: step >= totalSteps || alpha < .001 ? "complete" : step === 1 ? "initial" : "update", x, y };
}

export const XYG_WASM_GRAPH_SCHEDULER_DEFAULTS = { chunkSteps: XYG_WASM_GRAPH_DEFAULT_CHUNK_STEPS, maxWallMs: XYG_WASM_GRAPH_DEFAULT_MAX_WALL_MS } as const;

/** Ergonomic object-input wrapper; encoding copies, so caller arrays stay usable. */
export function layoutWasmCose(
  worker: XygWasmWorker,
  request: XygWasmGraphRequest,
  options: Parameters<XygWasmWorker["layoutCose"]>[1],
): XygWasmTask<XygWasmGraphCheckpoint> {
  return worker.layoutCose(encodeWasmCose(request), options);
}
