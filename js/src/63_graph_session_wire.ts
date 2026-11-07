/** Internal framing only for the bounded retained GraphForge controller.
 * Rust owns graph state, identity/provenance, focus order and companion rows.
 * spec/design/graph-interaction.md §S4 wire decisions and GPU/result foundation.
 */
import { XygWasmError } from "./47_wasm";
import { decodeGraphForgeSections, encodeGraphForgeContainer, uuidFromBytes, uuidToBytes, type GraphForgeRawSection } from "./49_wasm_graphforge";

const DT = { u8: 1, u32: 2, u64: 3, f64: 5, bytes: 6, texts: 9, utf8: 8 } as const;
const MAX_U64 = 0xffffffffffffffffn;
const MAX_U32 = 0xffffffff;
const utf8 = new TextDecoder("utf-8", { fatal: true });
const fail = (reason: string): never => { throw new XygWasmError("GF_INTERACTION_INVALID", `malformed graph session result: ${reason}`, -3); };
export type GraphSessionCamera = readonly [number, number, number, number, number, number, number];
export type GraphSessionRef =
  | { kind: 0 | 1; uuid: string }
  | { kind: 2; resultId: string | null; layer: number; path: bigint; order: bigint }
  | { kind: 3; index: number; renderRevision: number };
export interface GraphSessionLoad {
  x?: ArrayLike<number>; y?: ArrayLike<number>;
  collapsed?: ArrayLike<number>; pinned?: ArrayLike<number>;
  budgets?: readonly [bigint, bigint]; seed?: bigint; progressive?: boolean;
  cose?: readonly [number, number, number, number, number, number];
  coseBounds?: readonly [number, number, number, number];
}
export interface GraphSessionRequest {
  instanceId: bigint; opSeq: bigint; revision: number;
  operation: 19 | 21 | 1 | 4 | 5 | 7 | 11 | 13 | 15 | 17 | 18;
  temporal?: boolean; pinned?: boolean;
  steps?: number;
  document?: Uint8Array | ArrayBuffer; load?: GraphSessionLoad; camera?: GraphSessionCamera;
  coordinates?: readonly [number, number];
  direction?: 1 | -1; mode?: 0 | 1 | 2; refs?: readonly GraphSessionRef[];
  page?: number; pageSize?: number;
}
function exactU64(value: bigint, label: string, nonzero = false): bigint {
  if (typeof value !== "bigint" || value < (nonzero ? 1n : 0n) || value > MAX_U64) throw new TypeError(`${label} must be an exact ${nonzero ? "nonzero " : ""}u64 bigint`);
  return value;
}
function exactU32(value: number, label: string): number {
  if (!Number.isInteger(value) || value < 0 || value > MAX_U32) throw new TypeError(`${label} must be a u32`);
  return value;
}
function numbers(value: ArrayLike<number>, label: string, count?: number): number[] {
  const out = Array.from(value);
  if ((count !== undefined && out.length !== count) || out.some((x) => typeof x !== "number")) throw new TypeError(`${label} has an invalid numeric shape`);
  return out;
}
/** Exact transport refs; no identity resolution or source-row policy. */
export function encodeGraphSessionRefs(refs: readonly GraphSessionRef[]): Uint8Array {
  if (!Array.isArray(refs) || refs.length > 20_000) throw new TypeError("invalid graph ref list");
  const encoder = new TextEncoder();
  const pool = refs.map((ref) => {
    if (ref.kind !== 2 || ref.resultId === null) return new Uint8Array();
    if (typeof ref.resultId !== "string") throw new TypeError("derived resultId must be a string or null");
    const bytes = encoder.encode(ref.resultId);
    if (utf8.decode(bytes) !== ref.resultId) throw new TypeError("derived resultId must contain Unicode scalar values");
    return bytes;
  });
  const poolSize = pool.reduce((n, bytes) => n + bytes.length, 0);
  if (poolSize >= MAX_U32) throw new RangeError("graph ref string pool is too large");
  const start = 8 + refs.length * 56, out = new Uint8Array(start + poolSize), v = new DataView(out.buffer);
  v.setUint32(0, refs.length, true); v.setUint32(4, poolSize, true);
  let cursor = 0;
  refs.forEach((ref, i) => {
    const at = 8 + i * 56;
    v.setUint32(at, ref.kind, true);
    if (ref.kind === 0 || ref.kind === 1) {
      const id = uuidToBytes(ref.uuid);
      if (!id.some((b) => b !== 0)) throw new TypeError("graph identity UUID must be nonzero");
      out.set(id, at + 8);
    } else if (ref.kind === 2) {
      if (ref.resultId !== null && typeof ref.resultId !== "string") throw new TypeError("derived resultId must be a string or null");
      v.setUint32(at + 24, exactU32(ref.layer, "ref.layer"), true);
      v.setBigUint64(at + 32, exactU64(ref.path, "ref.path"), true); v.setBigUint64(at + 40, exactU64(ref.order, "ref.order"), true);
      v.setUint32(at + 48, ref.resultId === null ? MAX_U32 : cursor, true);
      v.setUint32(at + 52, pool[i]!.length, true); out.set(pool[i]!, start + cursor); cursor += pool[i]!.length;
    } else if (ref.kind === 3) {
      v.setUint32(at + 24, exactU32(ref.index, "ref.index"), true); v.setUint32(at + 28, exactU32(ref.renderRevision, "ref.renderRevision"), true);
    } else throw new TypeError("invalid graph ref kind");
  });
  return out;
}
export function decodeGraphSessionRefs(bytes: Uint8Array): GraphSessionRef[] {
  if (bytes.length < 8) fail("refs header");
  const v = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength), n = v.getUint32(0, true), poolBytes = v.getUint32(4, true);
  const start = 8 + n * 56;
  if (n > 20_000 || start + poolBytes !== bytes.length) fail("refs length");
  let cursor = 0;
  const refs: GraphSessionRef[] = [];
  for (let i = 0; i < n; i++) {
    const at = 8 + i * 56, kind = v.getUint32(at, true), layer = v.getUint32(at + 24, true), revision = v.getUint32(at + 28, true);
    const path = v.getBigUint64(at + 32, true), order = v.getBigUint64(at + 40, true), off = v.getUint32(at + 48, true), len = v.getUint32(at + 52, true);
    const nil = !bytes.subarray(at + 8, at + 24).some((b) => b !== 0);
    if (v.getUint32(at + 4, true) !== 0) fail("ref reserved");
    if (kind === 0 || kind === 1) {
      if (nil || layer || revision || path || order || off || len) fail("canonical ref");
      refs.push({ kind, uuid: uuidFromBytes(bytes, at + 8) });
    } else if (kind === 2) {
      if (!nil || revision) fail("derived ref");
      let resultId: string | null = null;
      if (!(off === MAX_U32 && len === 0)) {
        if (off !== cursor || cursor + len > poolBytes) fail("ref string range");
        resultId = utf8.decode(bytes.subarray(start + cursor, start + cursor + len)); cursor += len;
      }
      refs.push({ kind, resultId, layer, path, order });
    } else if (kind === 3) {
      if (!nil || path || order || off || len) fail("aggregate ref");
      refs.push({ kind, index: layer, renderRevision: revision });
    } else fail("ref kind");
  }
  if (cursor !== poolBytes) fail("unused ref string bytes");
  return refs;
}
/** A bounded internal operation vocabulary. It is not a public arbitrary-command API. */
export function encodeGraphSessionRequest(input: GraphSessionRequest): Uint8Array {
  exactU64(input.instanceId, "instanceId", true); exactU64(input.opSeq, "opSeq", true); exactU32(input.revision, "revision");
  if (![19, 21, 1, 4, 5, 7, 11, 13, 15, 17, 18].includes(input.operation)) throw new TypeError("unsupported graph controller operation");
  const words = [input.revision, input.operation, 0, 0, 0, 0, 0, 0, 0];
  const sections: Array<{ name: string; dtype: number; values: any }> = [];
  const add = (name: string, dtype: number, values: any) => sections.push({ name, dtype, values });
  if (input.operation === 18) {
    if (typeof input.temporal !== "boolean") throw new TypeError("temporal binding requires a boolean");
    add("temporal.u64", DT.u64, [input.temporal ? 1n : 0n]);
  } else if (input.temporal !== undefined) throw new TypeError("temporal is only valid for binding");
  if (input.operation === 13) {
    if (typeof input.pinned !== "boolean" || input.refs?.length !== 1) throw new TypeError("pin requires one ref and a boolean");
    words[5] = input.pinned ? 1 : 0;
  } else if (input.pinned !== undefined) throw new TypeError("pinned is only valid for pin");
  if (input.operation === 15) {
    if (input.steps === undefined || !Number.isInteger(input.steps) || input.steps < 1 || input.steps > 64) throw new TypeError("relayout steps must be an integer in 1..64");
    words[7] = input.steps;
  } else if (input.steps !== undefined) throw new TypeError("steps are only valid for relayout");
  if (input.operation === 5) {
    if (input.direction !== 1 && input.direction !== -1) throw new TypeError("focus direction must be ±1");
    words[5] = input.direction === 1 ? 1 : MAX_U32;
  } else if (input.direction !== undefined) throw new TypeError("direction is only valid for focus step");
  if (input.mode !== undefined) {
    if (![1, 7, 11].includes(input.operation) || ![0, 1, 2].includes(input.mode)) throw new TypeError("invalid selection mode");
    words[2] = input.mode;
  }
  if (input.operation === 1) {
    if (!Array.isArray(input.coordinates)) throw new TypeError("select at requires two finite CSS coordinates");
    const coordinates = numbers(input.coordinates, "coordinates", 2);
    if (!coordinates.every(Number.isFinite)) throw new TypeError("select at requires two finite CSS coordinates");
    add("coordinates.f64", DT.f64, coordinates);
  } else if (input.coordinates !== undefined) throw new TypeError("coordinates are only valid for select at");
  if (input.operation === 11 || input.operation === 13) {
    if (!input.refs || input.refs.length > 10_000) throw new TypeError("select refs requires a bounded ref list");
    add("refs.bytes", DT.bytes, encodeGraphSessionRefs(input.refs));
  } else if (input.refs !== undefined) throw new TypeError("refs are only valid for select refs");
  if (input.operation === 19) {
    if (!(input.document instanceof Uint8Array || input.document instanceof ArrayBuffer)) throw new TypeError("open requires complete XYGF bytes");
    add("document.bytes", DT.bytes, input.document instanceof Uint8Array ? input.document : new Uint8Array(input.document));
    const load = input.load ?? {};
    for (const key of ["x", "y", "cose", "coseBounds"] as const) if (load[key] !== undefined) {
      add(key === "coseBounds" ? "load.cose.bounds.f64" : `load.${key}.f64`, DT.f64, numbers(load[key]!, `load.${key}`, key === "cose" ? 6 : key === "coseBounds" ? 4 : undefined));
    }
    for (const key of ["collapsed", "pinned"] as const) if (load[key] !== undefined) {
      const values = numbers(load[key]!, `load.${key}`);
      if (values.some((v) => v !== 0 && v !== 1)) throw new TypeError(`load.${key} must contain 0/1 flags`);
      add(`load.${key}.u8`, DT.u8, values);
    }
    if (load.budgets !== undefined) {
      if (load.budgets.length !== 2) throw new TypeError("load.budgets must contain two u64 values");
      add("load.budgets.u64", DT.u64, load.budgets.map((v) => exactU64(v, "load.budgets[]")));
    }
    if (load.seed !== undefined) add("load.seed.u64", DT.u64, [exactU64(load.seed, "load.seed")]);
    if (load.progressive !== undefined) {
      if (typeof load.progressive !== "boolean") throw new TypeError("load.progressive must be boolean");
      add("load.progressive.u8", DT.u8, [Number(load.progressive)]);
    }
  } else if (input.document !== undefined || input.load !== undefined) throw new TypeError("document/load are only valid for open");
  if (input.operation === 21) {
    if (!input.camera) throw new TypeError("render requires an explicit camera");
    add("camera.f64", DT.f64, numbers(input.camera, "camera", 7));
  } else if (input.camera !== undefined) throw new TypeError("camera is only valid for render");
  if (input.page !== undefined || input.pageSize !== undefined) {
    if (input.operation !== 17 && input.operation !== 21) throw new TypeError("paging is only valid for render/companion");
    const page = exactU32(input.page ?? 0, "page"), size = exactU32(input.pageSize ?? 50, "pageSize");
    if (!size || size > 200 || page * size > MAX_U32) throw new TypeError("invalid companion page");
    add("companion.u32", DT.u32, [page, size]);
  }
  return encodeGraphForgeContainer("XYGI", [
    { name: "header.u64", dtype: DT.u64, values: [input.instanceId, 0n, input.opSeq] },
    { name: "header.u32", dtype: DT.u32, values: words }, ...sections,
  ]);
}

export interface GraphSessionHeader { revision: number; degraded: boolean; unmatched: number; dropped: number }
export interface GraphSessionResult extends GraphSessionHeader {
  sections: Map<string, GraphForgeRawSection>;
  selection: { refs: GraphSessionRef[]; indices: BigUint64Array; layerOffsets: BigUint64Array; layers: Uint32Array; rows: BigUint64Array; resultIds: Array<string | null> };
  changed: GraphSessionRef[]; focus: GraphSessionRef[]; focusRing: Uint32Array;
  focusAction: { refs: GraphSessionRef[]; disclosureEligible: boolean; collapsed: boolean; pinEligible: boolean; pinned: boolean; moveCapability: boolean };
  clearAction: { applicable: boolean };
  outcome: { stateChanged: boolean; selected: number; disclosurePresent: boolean };
  disclosure: { refs: GraphSessionRef[]; collapsed: boolean[] };
  companion: { rows: string[][]; refs: GraphSessionRef[]; total: number };
  summary: string;
  relayout: { steps: bigint; alpha: number; done: boolean } | null;
}
function reader(input: Uint8Array | ArrayBuffer) {
  let sections: Map<string, GraphForgeRawSection>;
  try { sections = decodeGraphForgeSections(input, "XYGR"); } catch (error) { fail(error instanceof Error ? error.message : "container"); }
  const get = (name: string, dtype: number, count?: number): GraphForgeRawSection => {
    const s = sections.get(`${name}#0`);
    if (!s || s.dtype !== dtype || (count !== undefined && s.count !== count)) fail(name);
    return s;
  };
  const u32 = (name: string, count?: number) => {
    const s = get(name, DT.u32, count), v = new DataView(s.bytes.buffer, s.bytes.byteOffset, s.bytes.byteLength);
    return Uint32Array.from({ length: s.count }, (_, i) => v.getUint32(i * 4, true));
  };
  const u64 = (name: string, count?: number) => {
    const s = get(name, DT.u64, count), v = new DataView(s.bytes.buffer, s.bytes.byteOffset, s.bytes.byteLength);
    return BigUint64Array.from({ length: s.count }, (_, i) => v.getBigUint64(i * 8, true));
  };
  const refs = (name: string) => decodeGraphSessionRefs(get(name, DT.bytes).bytes);
  const text = (name: string) => utf8.decode(get(name, DT.utf8).bytes);
  const status = u32("status.u32", 1)[0]!;
  if (status !== 0) fail("successful reply status");
  const h = u32("header.u32", 4);
  if (h[1]! > 1) fail("header degraded flag");
  return { sections, get, u32, u64, refs, text, header: { revision: h[0]!, degraded: !!h[1], unmatched: h[2]!, dropped: h[3]! } };
}
/** OPEN carries only status/header; XYGR does not echo instance or sequence. */
export function decodeGraphSessionAck(input: Uint8Array | ArrayBuffer): GraphSessionHeader {
  return reader(input).header;
}
function unescapeCell(cell: string): string {
  let out = "";
  for (let i = 0; i < cell.length; i++) {
    if (cell[i] !== "\\") { out += cell[i]; continue; }
    const next = cell[++i];
    if (next === "\\") out += "\\";
    else if (next === "t") out += "\t";
    else if (next === "n") out += "\n";
    else fail("companion escape");
  }
  return out;
}
/** Decode only semantic planes. GPU views validate separately; CPU geometry is never materialized. */
export function decodeGraphSessionResult(input: Uint8Array | ArrayBuffer): GraphSessionResult {
  try {
    const r = reader(input), { get, u32, u64, refs } = r;
    const selectedRefs = refs("selection.refs.bytes"), indices = u64("selection.indices.u64", selectedRefs.length);
    if (selectedRefs.length > 10_000 || selectedRefs.some((ref) => ref.kind === 3)) fail("selection refs");
    const layerOffsets = u64("selection.layer_offsets.u64", selectedRefs.length + 1), layers = u32("selection.layers.u32"), rows = u64("selection.rows.u64", layers.length);
    const ids = get("selection.result_ids.texts", DT.texts), valid = get("selection.result_ids.valid.u8", DT.u8, ids.count).bytes;
    const iv = new DataView(ids.bytes.buffer, ids.bytes.byteOffset, ids.bytes.byteLength), head = (ids.count + 1) * 8, pool = ids.bytes.subarray(head);
    const resultIds: Array<string | null> = [];
    if (head > ids.bytes.length || iv.getBigUint64(0, true) !== 0n) fail("result ID offsets");
    let cursor = 0n;
    for (let i = 0; i < ids.count; i++) {
      const end = iv.getBigUint64((i + 1) * 8, true);
      if (end < cursor || end > BigInt(pool.length) || valid[i]! > 1) fail("result IDs");
      const id = utf8.decode(pool.subarray(Number(cursor), Number(end)));
      if (!valid[i] && id !== "") fail("absent result ID placeholder");
      resultIds.push(valid[i] ? id : null); cursor = end;
    }
    if (cursor !== BigInt(pool.length) || layerOffsets[0] !== 0n || layerOffsets[layerOffsets.length - 1] !== BigInt(rows.length)) fail("selection offsets");
    for (let i = 0; i < selectedRefs.length; i++) {
      const begin = layerOffsets[i]!, end = layerOffsets[i + 1]!;
      if (end < begin || end > BigInt(rows.length)) fail("selection layer range");
      let previous = -1;
      for (let j = Number(begin); j < Number(end); j++) {
        if (layers[j]! >= resultIds.length || layers[j]! <= previous || rows[j] === MAX_U64) fail("selection provenance");
        previous = layers[j]!;
      }
    }
    const changed = refs("changed.refs.bytes"), focus = refs("focus.bytes"), focusRing = u32("focus.ring.u32");
    if (focus.length > 1 || focusRing.length > 400 || focusRing.length % 2) fail("focus shape");
    const gh = u32("gpu.header.u32", 8);
    for (let i = 0; i < focusRing.length; i += 2) if (focusRing[i]! > 1 || focusRing[i + 1]! >= gh[focusRing[i] === 0 ? 2 : 3]!) fail("focus ring reference");
    const facts = u32("focus.action.u32", 8), actionRefs = refs("focus.action.ref.bytes");
    if (facts[0] !== 1 || facts.subarray(1, 6).some((v) => v > 1) || facts[6] || facts[7] || actionRefs.length > 1) fail("focus action");
    if ((!actionRefs.length || actionRefs[0]?.kind === 3) && facts.subarray(1).some((v) => v !== 0)) fail("focus action without singular target");
    if (actionRefs.some((ref) => ref.kind === 1)) fail("focus action edge");
    const clear = u32("clear.action.u32", 2);
    if (clear[0] !== 1 || clear[1]! > 1 || [...r.sections.values()].some(s => s.name === "clear.action.u32" && s.index !== 0)) fail("clear action");
    const outcome = u32("outcome.u32", 4);
    if (outcome[0] !== 1 || outcome[1]! > 1 || outcome[3]! > 1) fail("outcome");
    const disclosureRefs = refs("disclosure.ref.bytes"), collapsed = get("disclosure.collapsed.u8", DT.u8, outcome[3]).bytes;
    if (disclosureRefs.length !== outcome[3] || collapsed.some((v) => v > 1)) fail("disclosure");
    const candidates = refs("candidates.bytes"), total = u32("companion.total.u32", 1)[0]!;
    if (candidates.length > 200 || candidates.length > total || u32("candidates.total.u32", 1)[0] !== total || candidates.some((ref) => ref.kind === 3)) fail("companion candidates");
    const source = r.text("companion.text.utf8");
    // Split transport separators first: escaped tabs/newlines belong to a cell.
    const companionRows = source === "" ? [] : source.split("\n").map((row) => row.split("\t").map(unescapeCell));
    if (companionRows.length !== candidates.length || companionRows.some((row) => row.length !== 5)) fail("companion row alignment");
    const progressNames = ["relayout.steps.u64", "relayout.alpha.f64", "relayout.done.u8"];
    const progress = [...r.sections.values()].filter(s => progressNames.includes(s.name));
    let relayout: GraphSessionResult["relayout"] = null;
    if (progress.length) {
      if (progress.length !== 3 || progress.some(s => s.index !== 0)) fail("relayout planes");
      const steps = u64("relayout.steps.u64", 1)[0]!;
      const a = get("relayout.alpha.f64", DT.f64, 1), alpha = new DataView(a.bytes.buffer, a.bytes.byteOffset, a.bytes.byteLength).getFloat64(0, true);
      const done = get("relayout.done.u8", DT.u8, 1).bytes[0]!;
      if (!Number.isFinite(alpha) || alpha < 0 || alpha > 1 || done > 1) fail("relayout report");
      relayout = { steps, alpha, done: !!done };
    }
    return {
      relayout, ...r.header, sections: r.sections,
      selection: { refs: selectedRefs, indices, layerOffsets, layers, rows, resultIds }, changed, focus, focusRing,
      focusAction: { refs: actionRefs, disclosureEligible: !!facts[1], collapsed: !!facts[2], pinEligible: !!facts[3], pinned: !!facts[4], moveCapability: !!facts[5] },
      clearAction: { applicable: !!clear[1] },
      outcome: { stateChanged: !!outcome[1], selected: outcome[2]!, disclosurePresent: !!outcome[3] },
      disclosure: { refs: disclosureRefs, collapsed: Array.from(collapsed, Boolean) },
      companion: { rows: companionRows, refs: candidates, total }, summary: r.text("summary.text.utf8"),
    };
  } catch (error) {
    if (error instanceof XygWasmError && error.code === "GF_INTERACTION_INVALID") throw error;
    return fail(error instanceof Error ? error.message : "semantic planes");
  }
}
