import { hydrateWasmPainter, type XygWasmSceneView } from "./48_wasm_scene";
import {
  XygWasmWorker,
  type XygWasmCompiledScene,
  type XygWasmScenePaint,
  type XygWasmTask,
} from "./47_wasm";

export type { XygWasmCompiledScene };

/** Packed typed-column compile request (`XYCC`) version 1. */
export const XYG_WASM_COMPILE_VERSION = 1 as const;
export const XYG_WASM_COMPILE_HEADER_BYTES = 192 as const;
/** When set, Rust chooses Cartesian gutters via `cartesian_scene_margins`. */
export const XYG_WASM_COMPILE_FLAG_AUTO_MARGINS = 1 as const;
/** When set, Rust derives axis domains from finite column geometry. */
export const XYG_WASM_COMPILE_FLAG_AUTO_DOMAIN = 2 as const;

export type XygWasmScaleKind = "linear" | "log" | "symlog" | 0 | 1 | 2;
export type XygWasmRecordKind = "scatter" | "polyline" | "rect" | "band" | 0 | 1 | 2 | 3;

export interface XygWasmColumnStyle {
  fillRgba: Uint8Array | number[];
  strokeRgba: Uint8Array | number[];
  strokeWidth: number;
}

export interface XygWasmColumnCompileInput {
  width: number;
  height: number;
  /** Explicit left/right/top/bottom margins. Ignored when `autoMargins` is true. */
  margins?: [number, number, number, number];
  autoMargins?: boolean;
  /**
   * When true, omit explicit `x.lo`/`x.hi`/`y.lo`/`y.hi` and let Rust scan
   * finite column geometry in the Worker (FLAG_AUTO_DOMAIN).
   */
  autoDomain?: boolean;
  xAxisId?: bigint | number;
  yAxisId?: bigint | number;
  x?: {
    kind?: XygWasmScaleKind;
    lo?: number;
    hi?: number;
    constant?: number;
    maskNonpositive?: boolean;
  };
  y?: {
    kind?: XygWasmScaleKind;
    lo?: number;
    hi?: number;
    constant?: number;
    maskNonpositive?: boolean;
  };
  title?: string;
  xLabel?: string;
  yLabel?: string;
  kinds: ArrayLike<number> | XygWasmRecordKind[];
  stableIds: ArrayLike<bigint | number>;
  styleRefs: ArrayLike<number>;
  diameter: ArrayLike<number>;
  symbols: ArrayLike<number>;
  x0: ArrayLike<number>;
  y0: ArrayLike<number>;
  x1: ArrayLike<number>;
  y1: ArrayLike<number>;
  styles: XygWasmColumnStyle[];
}

function scaleCode(value: XygWasmScaleKind | undefined): number {
  if (value === undefined || value === "linear" || value === 0) return 0;
  if (value === "log" || value === 1) return 1;
  if (value === "symlog" || value === 2) return 2;
  throw new TypeError("scale kind must be linear, log, or symlog");
}

function kindCode(value: number | XygWasmRecordKind): number {
  if (typeof value === "number") {
    if (!Number.isInteger(value) || value < 0 || value > 3) {
      throw new TypeError("record kind must be an integer in 0..3");
    }
    return value;
  }
  if (value === "scatter") return 0;
  if (value === "polyline") return 1;
  if (value === "rect") return 2;
  if (value === "band") return 3;
  throw new TypeError("record kind must be scatter, polyline, rect, or band");
}

function align8(length: number): number {
  return (length + 7) & ~7;
}

function writeF64(view: DataView, offset: number, value: number) {
  if (!Number.isFinite(value)) {
    throw new TypeError("non-finite f64 is not allowed in XYCC requests");
  }
  view.setFloat64(offset, value, true);
}

function writeU64(view: DataView, offset: number, value: bigint | number) {
  const asBig = typeof value === "bigint" ? value : BigInt(value);
  if (asBig < 0n || asBig > 0xffffffffffffffffn) {
    throw new RangeError("stable ids and axis ids must fit in u64");
  }
  view.setBigUint64(offset, asBig, true);
}

/**
 * Pack typed columns into the little-endian `XYCC` request consumed by
 * `xyg_wasm_scene_compile`. No chart algorithms run here — only length checks
 * and binary framing before the Worker copies into WASM.
 */
export function encodeWasmColumns(input: XygWasmColumnCompileInput): ArrayBuffer {
  if (!input || !Array.isArray(input.styles)) {
    throw new TypeError("styles must be an array");
  }
  const recordCount = input.kinds.length;
  const styleCount = input.styles.length;
  const columns: ArrayLike<unknown>[] = [
    input.kinds,
    input.stableIds,
    input.styleRefs,
    input.diameter,
    input.symbols,
    input.x0,
    input.y0,
    input.x1,
    input.y1,
  ];
  if (columns.some((column) => column.length !== recordCount)) {
    throw new TypeError("all record columns must share the same length");
  }
  const title = new TextEncoder().encode(input.title ?? "");
  const xLabel = new TextEncoder().encode(input.xLabel ?? "");
  const yLabel = new TextEncoder().encode(input.yLabel ?? "");
  if (title.length > 4096 || xLabel.length > 4096 || yLabel.length > 4096) {
    throw new RangeError("chrome text exceeds the Rust scene text bound");
  }

  const parts: Uint8Array[] = [];
  const pushBytes = (source: ArrayLike<number>) => {
    const chunk = new Uint8Array(source.length);
    for (let index = 0; index < source.length; index++) {
      const value = source[index]!;
      if (!Number.isInteger(value) || value < 0 || value > 255) {
        throw new TypeError("byte columns must contain integers in 0..255");
      }
      chunk[index] = value;
    }
    parts.push(chunk);
  };
  const padTo8 = () => {
    const total = parts.reduce((sum, part) => sum + part.length, 0);
    const pad = align8(total) - total;
    if (pad) parts.push(new Uint8Array(pad));
  };
  const pushU32 = (source: ArrayLike<number>) => {
    padTo8();
    const chunk = new Uint8Array(source.length * 4);
    const view = new DataView(chunk.buffer);
    for (let index = 0; index < source.length; index++) {
      const value = source[index]!;
      if (!Number.isInteger(value) || value < 0 || value > 0xffffffff) {
        throw new TypeError("u32 columns must contain integers in 0..2^32-1");
      }
      view.setUint32(index * 4, value, true);
    }
    parts.push(chunk);
  };
  const pushU64 = (source: ArrayLike<bigint | number>) => {
    padTo8();
    const chunk = new Uint8Array(source.length * 8);
    const view = new DataView(chunk.buffer);
    for (let index = 0; index < source.length; index++) {
      writeU64(view, index * 8, source[index]!);
    }
    parts.push(chunk);
  };
  const pushF64 = (source: ArrayLike<number>) => {
    padTo8();
    const chunk = new Uint8Array(source.length * 8);
    const view = new DataView(chunk.buffer);
    for (let index = 0; index < source.length; index++) {
      writeF64(view, index * 8, source[index]!);
    }
    parts.push(chunk);
  };

  const kindBytes = new Uint8Array(recordCount);
  for (let index = 0; index < recordCount; index++) {
    kindBytes[index] = kindCode(input.kinds[index] as number | XygWasmRecordKind);
  }
  pushBytes(kindBytes);
  pushU64(input.stableIds);
  pushU32(input.styleRefs);
  pushF64(input.diameter);
  pushBytes(input.symbols);
  pushF64(input.x0);
  pushF64(input.y0);
  pushF64(input.x1);
  pushF64(input.y1);
  for (const style of input.styles) {
    if (style.fillRgba.length !== 4 || style.strokeRgba.length !== 4) {
      throw new TypeError("each style needs fillRgba and strokeRgba length 4");
    }
    pushBytes(style.fillRgba);
  }
  for (const style of input.styles) {
    pushBytes(style.strokeRgba);
  }
  pushF64(input.styles.map((style) => style.strokeWidth));
  parts.push(title, xLabel, yLabel);

  const payloadLength = parts.reduce((sum, part) => sum + part.length, 0);
  const bytes = new Uint8Array(XYG_WASM_COMPILE_HEADER_BYTES + payloadLength);
  const view = new DataView(bytes.buffer);
  bytes.set([88, 89, 67, 67], 0); // XYCC
  view.setUint32(4, XYG_WASM_COMPILE_VERSION, true);
  view.setUint32(8, XYG_WASM_COMPILE_HEADER_BYTES, true);
  let flags = 0;
  if (input.autoMargins) flags |= XYG_WASM_COMPILE_FLAG_AUTO_MARGINS;
  if (input.autoDomain) flags |= XYG_WASM_COMPILE_FLAG_AUTO_DOMAIN;
  view.setUint32(12, flags, true);
  view.setUint32(16, recordCount, true);
  view.setUint32(20, styleCount, true);
  view.setUint32(24, title.length, true);
  view.setUint32(28, xLabel.length, true);
  view.setUint32(32, yLabel.length, true);
  writeF64(view, 40, input.width);
  writeF64(view, 48, input.height);
  const margins = input.margins ?? [0, 0, 0, 0];
  if (margins.length !== 4) throw new TypeError("margins must be [left, right, top, bottom]");
  writeF64(view, 56, margins[0]!);
  writeF64(view, 64, margins[1]!);
  writeF64(view, 72, margins[2]!);
  writeF64(view, 80, margins[3]!);
  writeU64(view, 88, input.xAxisId ?? 1);
  writeU64(view, 96, input.yAxisId ?? 2);
  view.setUint32(104, scaleCode(input.x?.kind), true);
  view.setUint32(108, scaleCode(input.y?.kind), true);
  view.setUint32(112, input.x?.maskNonpositive ? 1 : 0, true);
  view.setUint32(116, input.y?.maskNonpositive ? 1 : 0, true);
  // Placeholder domains when autoDomain is set; Rust overwrites after the scan.
  writeF64(view, 120, input.x?.lo ?? 0);
  writeF64(view, 128, input.x?.hi ?? 1);
  writeF64(view, 136, input.x?.constant ?? 1);
  writeF64(view, 144, input.y?.lo ?? 0);
  writeF64(view, 152, input.y?.hi ?? 1);
  writeF64(view, 160, input.y?.constant ?? 1);

  let offset = XYG_WASM_COMPILE_HEADER_BYTES;
  for (const part of parts) {
    bytes.set(part, offset);
    offset += part.length;
  }
  return bytes.buffer;
}

export function compileWasmScene(
  worker: XygWasmWorker,
  request: ArrayBuffer | Uint8Array | XygWasmColumnCompileInput,
  options: { sequence?: number; transfer?: boolean } = {},
): XygWasmTask<XygWasmCompiledScene> {
  const buffer = request instanceof ArrayBuffer || request instanceof Uint8Array
    ? request
    : new Uint8Array(encodeWasmColumns(request));
  return (worker as any).sceneTask("scene.compile", buffer, options);
}

export function compilePrepareWasmScene(
  worker: XygWasmWorker,
  request: ArrayBuffer | Uint8Array | XygWasmColumnCompileInput,
  options: { sequence?: number; transfer?: boolean } = {},
): XygWasmTask<XygWasmScenePaint> {
  const buffer = request instanceof ArrayBuffer || request instanceof Uint8Array
    ? request
    : new Uint8Array(encodeWasmColumns(request));
  return (worker as any).sceneTask("scene.compile_paint", buffer, options);
}

export interface RenderWasmColumnsOptions {
  el: HTMLElement;
  columns: XygWasmColumnCompileInput;
  worker: XygWasmWorker;
  transfer?: boolean;
}

/**
 * Compile typed columns in the Rust WASM worker, then hydrate the shared painter.
 * TypeScript only frames the request and applies painter-ready output.
 */
export async function renderWasmColumns(
  options: RenderWasmColumnsOptions,
): Promise<XygWasmSceneView> {
  if (!options?.el || !(options.worker instanceof XygWasmWorker) || !options.columns) {
    throw new TypeError("el, columns, and an XygWasmWorker are required");
  }
  await options.worker.ready;
  const started = performance.now();
  const prepared = await compilePrepareWasmScene(options.worker, options.columns, {
    transfer: options.transfer,
  }).result;
  return hydrateWasmPainter(options.el, prepared, {
    workerPrepareMs: performance.now() - started,
  });
}
