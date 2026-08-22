import { hydrateWasmPainter, type XygWasmSceneView } from "./48_wasm_scene";
import {
  compilePrepareWasmScene,
  compileWasmScene,
} from "./49_wasm_columns";
import type { XygWasmWorker, XygWasmCompiledScene, XygWasmScenePaint, XygWasmTask } from "./47_wasm";
import {
  XYG_WASM_SEMANTIC_GRAPH_HEADER_BYTES,
  XYG_WASM_SEMANTIC_GRAPH_HEADER_OFFSETS,
  XYG_WASM_SEMANTIC_GRAPH_MAGIC,
  XYG_WASM_SEMANTIC_GRAPH_MAX_CODE,
  XYG_WASM_SEMANTIC_GRAPH_MAX_INPUT_ELEMENTS,
  XYG_WASM_SEMANTIC_GRAPH_STATE_FLAG_MASK,
  XYG_WASM_SEMANTIC_GRAPH_THEMES,
  XYG_WASM_SEMANTIC_GRAPH_VERSION,
} from "./wasm_abi_generated";

export interface XygWasmSemanticGraphInput {
  width: number;
  height: number;
  theme?: "light" | "dark" | 0 | 1;
  title?: string;
  /** Source-indexed semantic paint is intentionally direct-tier only. */
  tier?: "direct";
  x: ArrayLike<number>;
  y: ArrayLike<number>;
  nodeClass: ArrayLike<number>;
  nodeEpistemic: ArrayLike<number>;
  nodeStatus: ArrayLike<number>;
  nodeMetric: ArrayLike<number>;
  nodeFlags: ArrayLike<number>;
  nodeLabels?: ArrayLike<string | null>;
  /** Exact compound planes. Supply all three or none; Rust owns collapse policy. */
  parents?: ArrayLike<bigint | number>;
  parentValidity?: ArrayLike<number>;
  collapsed?: ArrayLike<number>;
  sources: ArrayLike<bigint | number>;
  targets: ArrayLike<bigint | number>;
  edgeClass: ArrayLike<number>;
  edgeEpistemic: ArrayLike<number>;
  edgeStatus: ArrayLike<number>;
  edgeMetric: ArrayLike<number>;
  edgeFlags: ArrayLike<number>;
  edgeLabels?: ArrayLike<string | null>;
}

function align8(value: number): number { return (value + 7) & ~7; }

function exactCode(value: unknown, name: string): number {
  if (!Number.isInteger(value) || Number(value) < 0 || Number(value) > XYG_WASM_SEMANTIC_GRAPH_MAX_CODE) {
    throw new TypeError(`${name} values must be exact integers in 0..${XYG_WASM_SEMANTIC_GRAPH_MAX_CODE}`);
  }
  return Number(value);
}

function exactU32(value: unknown, name: string): number {
  if (!Number.isInteger(value) || Number(value) < 0 || Number(value) > 0xffffffff) {
    throw new TypeError(`${name} values must be exact u32 integers`);
  }
  return Number(value);
}

function exactFlags(value: unknown, name: string): number {
  const result = exactU32(value, name);
  if (result & ~XYG_WASM_SEMANTIC_GRAPH_STATE_FLAG_MASK) {
    throw new TypeError(`${name} contains unknown semantic state flags`);
  }
  return result;
}

function exactU64(value: unknown, name: string): bigint {
  if (typeof value !== "number" && typeof value !== "bigint") {
    throw new TypeError(`${name} values must be non-negative safe integers or bigint`);
  }
  if (typeof value === "number" && (!Number.isSafeInteger(value) || value < 0)) {
    throw new TypeError(`${name} values must be non-negative safe integers or bigint`);
  }
  const result = typeof value === "bigint" ? value : BigInt(value);
  if (result < 0n || result > 0xffffffffffffffffn) throw new RangeError(`${name} values must fit u64`);
  return result;
}

/**
 * Frame canonical graph coordinates and closed semantic planes for Rust.
 * This function performs representation checks only: palettes, state
 * precedence, scale domains, halos, dashes, arrows, and legends stay in Rust.
 */
export function encodeWasmSemanticGraph(input: XygWasmSemanticGraphInput): ArrayBuffer {
  if (!input || input.tier !== undefined && input.tier !== "direct") {
    throw new TypeError("semantic graph Scene is direct-tier only; aggregate LOD must omit source-indexed semantic planes");
  }
  const n = input.x?.length ?? -1;
  const e = input.sources?.length ?? -1;
  if (!Number.isInteger(n) || n <= 0 || !Number.isInteger(e) || e < 0
      || n + e > XYG_WASM_SEMANTIC_GRAPH_MAX_INPUT_ELEMENTS) {
    throw new RangeError("semantic graph input exceeds the Rust direct-tier element bound");
  }
  const nodeColumns: ArrayLike<unknown>[] = [input.y, input.nodeClass, input.nodeEpistemic, input.nodeStatus, input.nodeMetric, input.nodeFlags];
  const edgeColumns: ArrayLike<unknown>[] = [input.targets, input.edgeClass, input.edgeEpistemic, input.edgeStatus, input.edgeMetric, input.edgeFlags];
  if (nodeColumns.some((column) => !column || column.length !== n)
      || edgeColumns.some((column) => !column || column.length !== e)) {
    throw new TypeError("semantic graph columns must match their node or edge count");
  }
  const compound = [input.parents, input.parentValidity, input.collapsed];
  const hasCompound = compound.some((column) => column !== undefined);
  if (hasCompound && compound.some((column) => column === undefined || column.length !== n)) {
    throw new TypeError("parents, parentValidity, and collapsed must all exactly match the node count");
  }
  for (let i=0; i<n; i++) {
    exactU64(input.parents === undefined ? 0 : input.parents[i], "parents");
    for (const [column, name] of [[input.parentValidity,"parentValidity"],[input.collapsed,"collapsed"]] as const) {
      const value = column === undefined ? 0 : column[i];
      if (value !== 0 && value !== 1) throw new TypeError(`${name} values must be exact 0 or 1 integers`);
    }
  }
  if (!Number.isFinite(input.width) || !Number.isFinite(input.height)
      || input.width < 160 || input.height < 120) {
    throw new RangeError("semantic graph viewport must be finite and at least 160 by 120 CSS pixels");
  }
  const title = new TextEncoder().encode(input.title ?? "");
  if (title.byteLength > 4096 || title.includes(0)) throw new RangeError("semantic graph title exceeds the Rust text bound");
  const encoder = new TextEncoder();
  const encodeLabels = (values: ArrayLike<string | null> | undefined, count: number, name: string) => {
    if (values !== undefined && values.length !== count) throw new TypeError(`${name} must match its graph element count`);
    return Array.from({length:count}, (_, i) => {
      const value = values === undefined ? null : values[i];
      if (value !== null && typeof value !== "string") throw new TypeError(`${name} values must be string or null`);
      return encoder.encode(value ?? "");
    });
  };
  const nodeLabels = encodeLabels(input.nodeLabels, n, "nodeLabels");
  const edgeLabels = encodeLabels(input.edgeLabels, e, "edgeLabels");
  if (nodeLabels.concat(edgeLabels).some((label) => label.byteLength > 4096 || label.includes(0))
      || nodeLabels.concat(edgeLabels).reduce((sum, label) => sum + label.byteLength, 0) > 8192) {
    throw new RangeError("semantic graph labels exceed the Rust text bounds");
  }
  let length = align8(XYG_WASM_SEMANTIC_GRAPH_HEADER_BYTES + title.byteLength);
  for (const bytes of [16*n, 3*n, 8*n, 4*n, 16*e, 3*e, 8*e, 4*e, 8*n, 2*n]) length = align8(length + bytes);
  length = align8(align8(length + 4*n) + 4*e + nodeLabels.concat(edgeLabels).reduce((sum, label) => sum + label.byteLength, 0));
  if (!Number.isSafeInteger(length)) throw new RangeError("semantic graph request byte length overflow");
  const buffer = new ArrayBuffer(length);
  const bytes = new Uint8Array(buffer);
  const view = new DataView(buffer);
  bytes.set(new TextEncoder().encode(XYG_WASM_SEMANTIC_GRAPH_MAGIC));
  view.setUint32(XYG_WASM_SEMANTIC_GRAPH_HEADER_OFFSETS.version, XYG_WASM_SEMANTIC_GRAPH_VERSION, true);
  view.setUint32(XYG_WASM_SEMANTIC_GRAPH_HEADER_OFFSETS.header_bytes, XYG_WASM_SEMANTIC_GRAPH_HEADER_BYTES, true);
  const theme = input.theme ?? "light";
  const themeCode = theme === "light" || theme === 0 ? XYG_WASM_SEMANTIC_GRAPH_THEMES.light : theme === "dark" || theme === 1 ? XYG_WASM_SEMANTIC_GRAPH_THEMES.dark : -1;
  if (themeCode < 0) throw new TypeError("semantic graph theme must be light or dark");
  view.setUint32(XYG_WASM_SEMANTIC_GRAPH_HEADER_OFFSETS.theme, themeCode, true);
  view.setUint32(XYG_WASM_SEMANTIC_GRAPH_HEADER_OFFSETS.node_count, n, true);
  view.setUint32(XYG_WASM_SEMANTIC_GRAPH_HEADER_OFFSETS.edge_count, e, true);
  view.setUint32(XYG_WASM_SEMANTIC_GRAPH_HEADER_OFFSETS.title_bytes, title.byteLength, true);
  view.setFloat64(XYG_WASM_SEMANTIC_GRAPH_HEADER_OFFSETS.width, input.width, true);
  view.setFloat64(XYG_WASM_SEMANTIC_GRAPH_HEADER_OFFSETS.height, input.height, true);
  let offset: number = XYG_WASM_SEMANTIC_GRAPH_HEADER_BYTES;
  bytes.set(title, offset); offset = align8(offset + title.byteLength);
  for (const column of [input.x, input.y]) {
    for (let i=0; i<n; i++, offset+=8) {
      const value = column[i];
      if (typeof value !== "number" || !Number.isFinite(value)) throw new TypeError("semantic graph coordinates must be finite f64 values");
      view.setFloat64(offset, value, true);
    }
  }
  for (const [column, name] of [[input.nodeClass,"nodeClass"],[input.nodeEpistemic,"nodeEpistemic"],[input.nodeStatus,"nodeStatus"]] as const) {
    for (let i=0; i<n; i++, offset++) bytes[offset] = exactCode(column[i], name);
  }
  offset = align8(offset);
  for (let i=0; i<n; i++, offset+=8) {
    const value = Number(input.nodeMetric[i]);
    if (typeof input.nodeMetric[i] !== "number" || !Number.isFinite(value) && !Number.isNaN(value)) throw new TypeError("nodeMetric values must be f64 or NaN");
    view.setFloat64(offset, value, true);
  }
  for (let i=0; i<n; i++, offset+=4) view.setUint32(offset, exactFlags(input.nodeFlags[i], "nodeFlags"), true);
  offset = align8(offset);
  for (const [column, name] of [[input.sources,"sources"],[input.targets,"targets"]] as const) {
    for (let i=0; i<e; i++, offset+=8) view.setBigUint64(offset, exactU64(column[i], name), true);
  }
  for (const [column, name] of [[input.edgeClass,"edgeClass"],[input.edgeEpistemic,"edgeEpistemic"],[input.edgeStatus,"edgeStatus"]] as const) {
    for (let i=0; i<e; i++, offset++) bytes[offset] = exactCode(column[i], name);
  }
  offset = align8(offset);
  for (let i=0; i<e; i++, offset+=8) {
    const value = Number(input.edgeMetric[i]);
    if (typeof input.edgeMetric[i] !== "number" || !Number.isFinite(value) && !Number.isNaN(value)) throw new TypeError("edgeMetric values must be f64 or NaN");
    view.setFloat64(offset, value, true);
  }
  for (let i=0; i<e; i++, offset+=4) view.setUint32(offset, exactFlags(input.edgeFlags[i], "edgeFlags"), true);
  offset = align8(offset);
  for (let i=0; i<n; i++, offset+=8) view.setBigUint64(offset, exactU64(input.parents === undefined ? 0 : input.parents[i], "parents"), true);
  for (const [column, name] of [[input.parentValidity,"parentValidity"],[input.collapsed,"collapsed"]] as const) {
    for (let i=0; i<n; i++, offset++) {
      const value = column === undefined ? 0 : column[i];
      if (value !== 0 && value !== 1) throw new TypeError(`${name} values must be exact 0 or 1 integers`);
      bytes[offset] = value;
    }
  }
  offset = align8(offset);
  for (const label of nodeLabels) { view.setUint32(offset, label.byteLength, true); offset += 4; }
  offset = align8(offset);
  for (const label of edgeLabels) { view.setUint32(offset, label.byteLength, true); offset += 4; }
  for (const label of nodeLabels.concat(edgeLabels)) { bytes.set(label, offset); offset += label.byteLength; }
  if (align8(offset) !== length) throw new Error("semantic graph framing length mismatch");
  return buffer;
}

export function compileWasmSemanticGraph(
  worker: XygWasmWorker,
  input: XygWasmSemanticGraphInput,
  options: { sequence?: number; transfer?: boolean } = {},
): XygWasmTask<XygWasmCompiledScene> {
  return compileWasmScene(worker, encodeWasmSemanticGraph(input), options);
}

export function compilePrepareWasmSemanticGraph(
  worker: XygWasmWorker,
  input: XygWasmSemanticGraphInput,
  options: { sequence?: number; transfer?: boolean } = {},
): XygWasmTask<XygWasmScenePaint> {
  return compilePrepareWasmScene(worker, encodeWasmSemanticGraph(input), options);
}

export async function renderWasmSemanticGraph(options: {
  el: HTMLElement; graph: XygWasmSemanticGraphInput; worker: XygWasmWorker; transfer?: boolean;
}): Promise<XygWasmSceneView> {
  if (!options?.el || !options.graph || !options.worker) throw new TypeError("el, graph, and worker are required");
  await options.worker.ready;
  const started = performance.now();
  const prepared = await compilePrepareWasmSemanticGraph(options.worker, options.graph, { transfer: options.transfer }).result;
  return hydrateWasmPainter(options.el, prepared, { workerPrepareMs: performance.now() - started });
}
