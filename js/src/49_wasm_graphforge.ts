/**
 * Direct-browser GraphForge result compositions
 * (spec/design/graphforge-compositions.md §6.3).
 *
 * Framing and decoding only: GraphForge Arrow IPC bytes, generation UUIDs,
 * and explicit intent go into one `XYGQ` request; the Rust/WASM engine
 * returns the same `XYGF` document the native host returns for those bytes.
 * Recognition, joins, identity policy, planes, layout, and the Scene are
 * Rust's. This module maps Scene stable IDs back to GraphForge UUIDs and
 * result rows mechanically, and renders tables as text-only DOM.
 */
import { renderWasmScene, type XygWasmSceneView } from "./48_wasm_scene";
import { XygWasmError, type XygWasmTask, type XygWasmWorker } from "./47_wasm";

export const GRAPHFORGE_REQUEST_MAGIC = "XYGQ";
export const GRAPHFORGE_DOCUMENT_MAGIC = "XYGF";
const CONTAINER_VERSION = 1;
const HEADER_BYTES = 32;
const ENTRY_BYTES = 40;
const MAX_ENTRIES = 8192;
const NONE_U32 = 0xffffffff;
const NONE_U64 = 0xffffffffffffffffn;
const DT = { u8: 1, u32: 2, u64: 3, i64: 4, f64: 5, bytes: 6, uuid: 7, utf8: 8, texts: 9 } as const;
const WIDTH: Record<number, number> = { 1: 1, 2: 4, 3: 8, 4: 8, 5: 8, 6: 1, 7: 16, 8: 1 };
const NAME = /^[a-z0-9._]{1,64}$/;
const UUID_TEXT = /^([0-9a-f]{8})-([0-9a-f]{4})-([0-9a-f]{4})-([0-9a-f]{4})-([0-9a-f]{12})$/;
const align8 = (n: number) => (n + 7) & ~7;

type Bytes = Uint8Array | ArrayBuffer;
export type XygGraphForgeIntent = "graph" | "table" | "bar-chart" | "embedding-coordinates" | "parallel-coordinates";

export interface XygGraphForgeLayerInput {
  result: Bytes; intent: XygGraphForgeIntent; resultId?: string; generation?: string;
  missing?: "dim" | "hide" | "keep" | "error"; extra?: "error" | "drop"; rows?: ArrayLike<number | bigint>;
  coordinates?: Bytes;
}
export interface XygGraphForgeInput {
  base?: { tables?: Bytes[]; generation?: string; directed?: boolean };
  layers: XygGraphForgeLayerInput[];
  /** Node or relationship UUIDs painted in the selected state. */
  select?: string[];
  /** Lower a graph composition to the direct-tier canonical Scene. */
  render?: { width: number; height: number; theme?: "light" | "dark"; title?: string };
}

interface Section { name: string; index: number; dtype: number; count: number; value: any }

function bytesOf(value: unknown, label: string): Uint8Array {
  if (value instanceof Uint8Array) return value;
  if (value instanceof ArrayBuffer) return new Uint8Array(value);
  throw new TypeError(`${label} must be a Uint8Array or ArrayBuffer`);
}

export function uuidToBytes(text: string, label = "uuid"): Uint8Array {
  const match = typeof text === "string" ? UUID_TEXT.exec(text.toLowerCase()) : null;
  if (!match) throw new TypeError(`${label} must be a canonical UUID string`);
  const hex = match.slice(1).join(""); const out = new Uint8Array(16);
  for (let i = 0; i < 16; i++) out[i] = Number.parseInt(hex.slice(i * 2, i * 2 + 2), 16);
  return out;
}

export function uuidFromBytes(bytes: Uint8Array, offset = 0): string {
  let hex = "";
  for (let i = 0; i < 16; i++) hex += bytes[offset + i]!.toString(16).padStart(2, "0");
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
}

/** Named-section container encoder (twin of the Node and Rust codecs). */
export function encodeGraphForgeContainer(magic: string, sections: Array<{ name: string; index?: number; dtype: number; values: any }>): Uint8Array {
  if (sections.length > MAX_ENTRIES) throw new RangeError("too many container sections");
  const encoder = new TextEncoder();
  const prepared = sections.map(({ name, index = 0, dtype, values }) => {
    if (!NAME.test(name)) throw new TypeError("invalid section name");
    let payload: Uint8Array; let count: number;
    switch (dtype) {
      case DT.u8: payload = Uint8Array.from(values as ArrayLike<number>); count = payload.length; break;
      case DT.u64: { const a = BigUint64Array.from(values as ArrayLike<bigint>, (v: any) => BigInt(v)); payload = new Uint8Array(a.buffer); count = a.length; break; }
      case DT.f64: { const a = Float64Array.from(values as ArrayLike<number>); payload = new Uint8Array(a.buffer); count = a.length; break; }
      case DT.bytes: payload = values as Uint8Array; count = payload.length; break;
      case DT.uuid: payload = values as Uint8Array; if (payload.length % 16) throw new RangeError(`${name} must hold 16-byte UUIDs`); count = payload.length / 16; break;
      case DT.utf8: payload = encoder.encode(String(values)); count = payload.length; break;
      default: throw new TypeError("unsupported request dtype");
    }
    return { name: encoder.encode(name), index, dtype, count, payload };
  });
  const names = prepared.reduce((n, s) => n + s.name.length, 0);
  const namesStart = HEADER_BYTES + prepared.length * ENTRY_BYTES;
  let cursor = align8(namesStart + names);
  const offsets = prepared.map((s) => { const at = cursor; cursor = align8(cursor + s.payload.length); return at; });
  const out = new Uint8Array(cursor), view = new DataView(out.buffer);
  out.set(encoder.encode(magic), 0);
  view.setUint32(4, CONTAINER_VERSION, true); view.setUint32(8, prepared.length, true); view.setUint32(12, names, true);
  view.setBigUint64(16, BigInt(cursor), true);
  let nameAt = 0;
  prepared.forEach((s, i) => {
    const at = HEADER_BYTES + i * ENTRY_BYTES;
    view.setUint32(at, nameAt, true); view.setUint32(at + 4, s.name.length, true);
    view.setUint32(at + 8, s.dtype, true); view.setUint32(at + 12, s.index, true);
    view.setBigUint64(at + 16, BigInt(offsets[i]!), true); view.setBigUint64(at + 24, BigInt(s.count), true);
    view.setBigUint64(at + 32, BigInt(s.payload.length), true);
    out.set(s.name, namesStart + nameAt); nameAt += s.name.length;
    out.set(s.payload, offsets[i]!);
  });
  return out;
}

/** Named-section container decoder: `Map<"name#index", Section>`. */
export function decodeGraphForgeContainer(input: Bytes, magic: string): Map<string, Section> {
  const bytes = bytesOf(input, "container");
  const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  const fail = (reason: string): never => { throw new XygWasmError("GF_COMPOSE_DOCUMENT_INVALID", `malformed ${magic} container: ${reason}`); };
  if (bytes.length < HEADER_BYTES || new TextDecoder().decode(bytes.subarray(0, 4)) !== magic) fail("magic");
  if (view.getUint32(4, true) !== CONTAINER_VERSION) fail("version");
  const count = view.getUint32(8, true), names = view.getUint32(12, true);
  if (count > MAX_ENTRIES || view.getBigUint64(16, true) !== BigInt(bytes.length)) fail("header");
  const namesStart = HEADER_BYTES + count * ENTRY_BYTES, payloadStart = align8(namesStart + names);
  if (payloadStart > bytes.length) fail("names");
  const decoder = new TextDecoder("utf-8", { fatal: true });
  const sections = new Map<string, Section>();
  for (let i = 0; i < count; i++) {
    const at = HEADER_BYTES + i * ENTRY_BYTES;
    const nameOffset = view.getUint32(at, true), nameLength = view.getUint32(at + 4, true);
    if (nameOffset + nameLength > names) fail("name range");
    const name = decoder.decode(bytes.subarray(namesStart + nameOffset, namesStart + nameOffset + nameLength));
    if (!NAME.test(name)) fail("name");
    const dtype = view.getUint32(at + 8, true), index = view.getUint32(at + 12, true);
    const offset = Number(view.getBigUint64(at + 16, true)), n = Number(view.getBigUint64(at + 24, true));
    const length = Number(view.getBigUint64(at + 32, true));
    if (offset % 8 || offset < payloadStart || offset + length > bytes.length) fail("section range");
    const payload = bytes.subarray(offset, offset + length);
    const copy = () => payload.slice().buffer;
    let value: any;
    if (dtype === DT.texts) {
      const head = (n + 1) * 8; if (length < head) fail("texts");
      const offs = new BigUint64Array(payload.slice(0, head).buffer), text = payload.subarray(head);
      value = [];
      for (let k = 0; k < n; k++) {
        const start = Number(offs[k]), end = Number(offs[k + 1]);
        if (end < start || end > text.length) fail("text offsets");
        value.push(decoder.decode(text.subarray(start, end)));
      }
    } else {
      const width = WIDTH[dtype]; if (width === undefined || n * width !== length) fail("section size");
      switch (dtype) {
        case DT.u32: value = new Uint32Array(copy()); break;
        case DT.u64: value = new BigUint64Array(copy()); break;
        case DT.i64: value = new BigInt64Array(copy()); break;
        case DT.f64: value = new Float64Array(copy()); break;
        case DT.utf8: value = decoder.decode(payload); break;
        default: value = payload.slice(); break;
      }
    }
    const key = `${name}#${index}`;
    if (sections.has(key)) fail("duplicate section");
    sections.set(key, { name, index, dtype, count: n, value });
  }
  return sections;
}

/** Frame a composition request. Only representation is checked here. */
export function encodeWasmGraphForgeRequest(input: XygGraphForgeInput): ArrayBuffer {
  if (!input || !Array.isArray(input.layers) || input.layers.length === 0) throw new TypeError("layers must be a non-empty array");
  const sections: Array<{ name: string; index?: number; dtype: number; values: any }> = [];
  (input.base?.tables ?? []).forEach((table, index) => sections.push({ name: "base.table", index, dtype: DT.bytes, values: bytesOf(table, "base.tables[]") }));
  if (input.base?.generation != null) sections.push({ name: "base.generation", dtype: DT.uuid, values: uuidToBytes(input.base.generation, "base.generation") });
  if (input.base?.directed != null) sections.push({ name: "base.directed", dtype: DT.u8, values: [input.base.directed ? 1 : 0] });
  input.layers.forEach((layer, index) => {
    sections.push({ name: "layer.result", index, dtype: DT.bytes, values: bytesOf(layer.result, `layers[${index}].result`) });
    if (layer.intent != null) sections.push({ name: "layer.intent", index, dtype: DT.utf8, values: layer.intent });
    if (layer.resultId != null) sections.push({ name: "layer.result_id", index, dtype: DT.utf8, values: layer.resultId });
    if (layer.generation != null) sections.push({ name: "layer.generation", index, dtype: DT.uuid, values: uuidToBytes(layer.generation, `layers[${index}].generation`) });
    if (layer.missing != null) sections.push({ name: "layer.missing", index, dtype: DT.utf8, values: layer.missing });
    if (layer.extra != null) sections.push({ name: "layer.extra", index, dtype: DT.utf8, values: layer.extra });
    if (layer.rows != null) sections.push({ name: "layer.rows", index, dtype: DT.u64, values: Array.from(layer.rows, (row) => BigInt(row)) });
    if (layer.coordinates != null) sections.push({ name: "layer.coordinates", index, dtype: DT.bytes, values: bytesOf(layer.coordinates, `layers[${index}].coordinates`) });
  });
  if (input.select != null) {
    const packed = new Uint8Array(input.select.length * 16);
    input.select.forEach((id, i) => packed.set(uuidToBytes(id, "select[]"), i * 16));
    sections.push({ name: "select.uuid", dtype: DT.uuid, values: packed });
  }
  if (input.render != null) {
    sections.push({ name: "render.width", dtype: DT.f64, values: [input.render.width] });
    sections.push({ name: "render.height", dtype: DT.f64, values: [input.render.height] });
    if (input.render.theme != null) sections.push({ name: "render.theme", dtype: DT.utf8, values: input.render.theme });
    if (input.render.title != null) sections.push({ name: "render.title", dtype: DT.utf8, values: input.render.title });
  }
  const bytes = encodeGraphForgeContainer(GRAPHFORGE_REQUEST_MAGIC, sections);
  return bytes.buffer.byteLength === bytes.byteLength ? bytes.buffer as ArrayBuffer : bytes.slice().buffer;
}

export interface XygGraphForgeLayerRow { layer: number; resultId: string | null; row: number }
export interface XygGraphForgeIdentity {
  kind: "node" | "edge"; index: number; uuid: string | null; layers: XygGraphForgeLayerRow[];
  derived?: boolean; type?: string | null; source?: string; target?: string; order?: number; path?: number;
}

/** A decoded `XYGF` composition (identity, provenance, and the Scene). */
export class XygGraphForgeComposition {
  readonly bytes: Uint8Array;
  readonly sections: Map<string, Section>;
  readonly kind: string;
  readonly nodeUuid: string[];
  readonly edgeUuid: Array<string | null>;
  readonly layers: Array<{ schema: string; algorithm: string; intent: string; resultId: string | null; nodeRows: BigUint64Array | null; edgeRows: BigUint64Array | null }>;
  readonly decisions: Array<{ code: string; layer: number | null; count: number }>;
  /** Canonical semantic Scene bytes when the request carried `render`. */
  readonly scene: Uint8Array | null;

  constructor(bytes: Uint8Array, sections: Map<string, Section>) {
    this.bytes = bytes; this.sections = sections;
    this.kind = this.get("kind");
    const nodes: Uint8Array | undefined = this.get("node.uuid");
    const edges: Uint8Array | undefined = this.get("edge.uuid");
    const derived: Uint8Array | undefined = this.get("edge.derived");
    this.nodeUuid = nodes ? Array.from({ length: nodes.length / 16 }, (_, i) => uuidFromBytes(nodes, i * 16)) : [];
    this.edgeUuid = edges ? Array.from({ length: edges.length / 16 }, (_, i) => (derived?.[i] ? null : uuidFromBytes(edges, i * 16))) : [];
    this.layers = [];
    for (let i = 0; sections.has(`layer.schema#${i}`); i++) {
      this.layers.push({
        schema: this.get("layer.schema", i), algorithm: this.get("layer.algorithm", i), intent: this.get("layer.intent", i),
        resultId: this.get("layer.result_id", i) ?? null, nodeRows: this.get("layer.node_rows", i) ?? null, edgeRows: this.get("layer.edge_rows", i) ?? null,
      });
    }
    const codes: string[] = this.get("decision.code") ?? [];
    const decisionLayers: Uint32Array | undefined = this.get("decision.layer");
    const counts: BigUint64Array | undefined = this.get("decision.count");
    this.decisions = codes.map((code, i) => ({ code, layer: decisionLayers![i] === NONE_U32 ? null : decisionLayers![i]!, count: Number(counts![i]) }));
    this.scene = this.get("scene.canonical") ?? null;
  }

  get(name: string, index = 0): any { return this.sections.get(`${name}#${index}`)?.value; }

  /** Identity of a composed node or edge for selection routing. */
  identify(kind: "node" | "edge", index: number): XygGraphForgeIdentity {
    const uuids = kind === "node" ? this.nodeUuid : this.edgeUuid;
    if (!Number.isInteger(index) || index < 0 || index >= uuids.length) throw new RangeError(`no composed ${kind} ${index}`);
    const layers: XygGraphForgeLayerRow[] = [];
    this.layers.forEach((layer, i) => {
      const row = (kind === "node" ? layer.nodeRows : layer.edgeRows)?.[index];
      if (row != null && row !== NONE_U64) layers.push({ layer: i, resultId: layer.resultId, row: Number(row) });
    });
    const out: XygGraphForgeIdentity = { kind, index, uuid: uuids[index] ?? null, layers };
    if (kind === "edge") {
      const source: BigUint64Array = this.get("edge.source"), target: BigUint64Array = this.get("edge.target");
      out.derived = this.get("edge.derived")[index] === 1;
      out.type = (this.get("edge.type") as string[])[index] || null;
      out.source = this.nodeUuid[Number(source[index])];
      out.target = this.nodeUuid[Number(target[index])];
      const order: BigInt64Array | undefined = this.get("edge.order");
      if (order != null && order[index]! >= 0n) { out.order = Number(order[index]); out.path = Number(this.get("edge.path")[index]); }
    }
    return out;
  }

  /** Scene stable ID (node `2^32 + i`, edge `j + 1`) → composed element identity. */
  identifyStableId(stableId: bigint): XygGraphForgeIdentity | null {
    const [nodeBase, edgeBase] = this.get("scene.stable_id_base") ?? [1n << 32n, 1n];
    if (stableId >= nodeBase && stableId - nodeBase < BigInt(this.nodeUuid.length)) return this.identify("node", Number(stableId - nodeBase));
    if (stableId >= edgeBase && stableId - edgeBase < BigInt(this.edgeUuid.length)) return this.identify("edge", Number(stableId - edgeBase));
    return null;
  }

  /** Value-free summary for host logs. */
  diagnostics() {
    return {
      kind: this.kind, nodes: this.nodeUuid.length, edges: this.edgeUuid.length,
      layers: this.layers.map((l) => ({ schema: l.schema, intent: l.intent })),
      decisions: this.decisions.map((d) => ({ ...d })),
    };
  }
}

/** Decode `XYGF` bytes; an error document throws its stable Rust code. */
export function decodeWasmGraphForgeDocument(input: Bytes): XygGraphForgeComposition {
  const bytes = bytesOf(input, "document");
  const sections = decodeGraphForgeContainer(bytes, GRAPHFORGE_DOCUMENT_MAGIC);
  const status = sections.get("status#0")?.value?.[0];
  if (status !== 0) {
    const layer = sections.get("error.layer#0")?.value?.[0];
    const error = new XygWasmError(sections.get("error.code#0")?.value ?? "GF_COMPOSE_DOCUMENT_INVALID", sections.get("error.message#0")?.value ?? "composition failed");
    Object.assign(error, { layer: layer == null || layer === NONE_U32 ? null : layer, field: sections.get("error.field#0")?.value ?? null });
    throw error;
  }
  return new XygGraphForgeComposition(bytes, sections);
}

/** Compose in the worker's Rust/WASM engine. */
export function composeWasmGraphForge(worker: XygWasmWorker, input: XygGraphForgeInput | ArrayBuffer): XygWasmTask<XygGraphForgeComposition> {
  const request = input instanceof ArrayBuffer ? input : encodeWasmGraphForgeRequest(input);
  const task = worker.graphforgeCompose(request);
  return { ...task, result: task.result.then((document) => decodeWasmGraphForgeDocument(document)) };
}

export interface XygWasmGraphForgeView { view: XygWasmSceneView; composition: XygGraphForgeComposition }

/**
 * Compose and paint a graph composition through the canonical Scene. Clicks
 * on nodes and edges dispatch `xy:graphforge-select` with the element's
 * UUID (null for derived edges), type, and per-layer result rows.
 */
export async function renderWasmGraphForge(options: {
  el: HTMLElement; worker: XygWasmWorker; input: XygGraphForgeInput;
  width: number; height: number; theme?: "light" | "dark"; title?: string;
}): Promise<XygWasmGraphForgeView> {
  if (!options?.el || !options.worker || !options.input) throw new TypeError("el, worker, and input are required");
  const render = { width: options.width, height: options.height, theme: options.theme ?? "light", ...(options.title != null ? { title: options.title } : {}) };
  const composition = await composeWasmGraphForge(options.worker, { ...options.input, render }).result;
  if (composition.kind !== "graph" || composition.scene == null) throw new XygWasmError("GF_COMPOSE_RENDER_UNSUPPORTED", "only graph compositions paint through the Scene");
  const view = await renderWasmScene({ el: options.el, scene: composition.scene.slice(), worker: options.worker });
  // Scene views disable click events by default; GraphForge picks need them.
  (view as any).interaction = { ...((view as any).interaction ?? {}), click: true };
  view.root.addEventListener("xy:click", (event: Event) => {
    const detail = (event as CustomEvent).detail;
    const stableId = view.sceneStableId(detail?.trace, detail?.index);
    const identity = stableId == null ? null : composition.identifyStableId(stableId);
    if (identity) view.root.dispatchEvent(new CustomEvent("xy:graphforge-select", { detail: identity, bubbles: true, composed: true }));
  });
  return { view, composition };
}

/** A table composition as a text-only `<table>` (cells never become markup). */
export function graphforgeTableElement(composition: XygGraphForgeComposition, doc: Document = document): HTMLTableElement {
  if (composition.kind !== "table") throw new TypeError("graphforgeTableElement needs a table composition");
  const columns: string[] = composition.get("table.columns");
  const cells: string[] = composition.get("table.cells");
  const valid: Uint8Array = composition.get("table.valid");
  const table = doc.createElement("table");
  table.className = "xyg-graphforge-table";
  const head = table.createTHead().insertRow();
  for (const column of columns) { const th = doc.createElement("th"); th.scope = "col"; th.textContent = column; head.appendChild(th); }
  const body = table.createTBody();
  for (let r = 0; r * columns.length < cells.length; r++) {
    const row = body.insertRow();
    columns.forEach((_, c) => { const i = r * columns.length + c; row.insertCell().textContent = valid[i] ? cells[i]! : ""; });
  }
  return table;
}
