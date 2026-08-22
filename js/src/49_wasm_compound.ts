import type { XygWasmTask, XygWasmWorker } from "./47_wasm";
import { XYG_WASM_COMPOUND_TRANSITION_MAX_NODES } from "./wasm_abi_generated";

export type XygCompoundAction = "expand" | "collapse" | "toggle";
export interface XygWasmCompoundTransitionInput {
  nodeIds: ArrayLike<bigint | number>;
  parents: ArrayLike<bigint | number>;
  parentValidity: ArrayLike<number>;
  collapsed: ArrayLike<number>;
  targetId: bigint | number;
  action: XygCompoundAction;
  tier?: "direct";
}
export interface XygWasmCompoundTransitionResult { collapsed: Uint8Array; changed: boolean; }

const ACTIONS = Object.freeze({ expand: 0, collapse: 1, toggle: 2 });
function exactU64(value: unknown, name: string): bigint {
  if (typeof value === "number" && (!Number.isSafeInteger(value) || value < 0)) throw new TypeError(`${name} must be a non-negative safe integer or bigint`);
  if (typeof value !== "number" && typeof value !== "bigint") throw new TypeError(`${name} must be a non-negative safe integer or bigint`);
  const result = BigInt(value); if (result < 0n || result > 0xffffffffffffffffn) throw new RangeError(`${name} must fit u64`); return result;
}
function exactBit(value: unknown, name: string): number {
  if (value !== 0 && value !== 1) throw new TypeError(`${name} must contain only exact 0 or 1`); return value;
}

export function encodeWasmCompoundTransition(input: XygWasmCompoundTransitionInput): ArrayBuffer {
  if (!input || typeof input !== "object" || Array.isArray(input)) throw new TypeError("compound transition input must be an object");
  const nodeIds = Array.from(input.nodeIds ?? [], (value) => exactU64(value, "nodeIds"));
  const parents = Array.from(input.parents ?? [], (value) => exactU64(value, "parents"));
  const validity = Array.from(input.parentValidity ?? [], (value) => exactBit(value, "parentValidity"));
  const collapsed = Array.from(input.collapsed ?? [], (value) => exactBit(value, "collapsed"));
  const n = nodeIds.length;
  if (n === 0 || n > XYG_WASM_COMPOUND_TRANSITION_MAX_NODES || parents.length !== n || validity.length !== n || collapsed.length !== n) throw new RangeError("compound transition planes must have one bounded value per node");
  if (input.tier !== undefined && input.tier !== "direct") throw new TypeError("compound transitions require direct LOD");
  if (!Object.hasOwn(ACTIONS, input.action)) throw new TypeError("compound action must be expand, collapse, or toggle");
  const buffer = new ArrayBuffer(40 + n * 18), bytes = new Uint8Array(buffer), view = new DataView(buffer);
  bytes.set([88, 89, 71, 67]); view.setUint32(4, 1, true); view.setUint32(8, 40, true);
  view.setUint32(12, ACTIONS[input.action], true); view.setUint32(16, 0, true); view.setUint32(20, n, true); view.setBigUint64(24, exactU64(input.targetId, "targetId"), true);
  let at = 40; for (const value of nodeIds) { view.setBigUint64(at, value, true); at += 8; }
  for (const value of parents) { view.setBigUint64(at, value, true); at += 8; }
  bytes.set(validity, at); at += n; bytes.set(collapsed, at);
  return buffer;
}

export function decodeWasmCompoundTransition(buffer: ArrayBuffer, nodeCount: number): XygWasmCompoundTransitionResult {
  if (!(buffer instanceof ArrayBuffer) || !Number.isInteger(nodeCount) || nodeCount <= 0 || buffer.byteLength !== 16 + nodeCount) throw new TypeError("Rust compound transition length is invalid");
  const bytes = new Uint8Array(buffer), view = new DataView(buffer);
  if (bytes.subarray(0, 4).join(",") !== "88,89,67,79" || view.getUint32(4, true) !== 1 || view.getUint32(8, true) !== 16 || bytes[12] > 1 || bytes.subarray(13, 16).some(Boolean) || bytes.subarray(16).some((value) => value > 1)) throw new TypeError("Rust compound transition is malformed");
  return Object.freeze({ collapsed: bytes.slice(16), changed: bytes[12] !== 0 });
}

export function transitionWasmCompound(worker: XygWasmWorker, input: XygWasmCompoundTransitionInput): XygWasmTask<XygWasmCompoundTransitionResult> {
  const request = encodeWasmCompoundTransition(input), count = input.nodeIds.length;
  const task = worker.compoundTransition(request);
  return { ...task, result: task.result.then((buffer) => decodeWasmCompoundTransition(buffer, count)) };
}
