/** Transferable typed-series framing for Rust-owned direct-browser compile. */
import { hydrateWasmPainter, type XygWasmSceneView } from "./48_wasm_scene";
import type { XygWasmScaleKind } from "./49_wasm_columns";
import { XygWasmWorker, type XygWasmDiagnostics, type XygWasmTask, type XygWasmScenePaint } from "./47_wasm";
import { XYG_WASM_TYPED_SERIES_DESCRIPTOR_BYTES as DESCRIPTOR, XYG_WASM_TYPED_SERIES_DESCRIPTOR_OFFSETS as D, XYG_WASM_TYPED_SERIES_FLAGS as F, XYG_WASM_TYPED_SERIES_HEADER_BYTES as HEADER, XYG_WASM_TYPED_SERIES_HEADER_FLAGS as HF, XYG_WASM_TYPED_SERIES_HEADER_OFFSETS as H, XYG_WASM_TYPED_SERIES_KINDS as K, XYG_WASM_TYPED_SERIES_MAGIC, XYG_WASM_TYPED_SERIES_MAX_RECORDS as MAX_RECORDS, XYG_WASM_TYPED_SERIES_MAX_SERIES as MAX_SERIES, XYG_WASM_TYPED_SERIES_MAX_SYMBOL_CODE as MAX_SYMBOL, XYG_WASM_TYPED_SERIES_MAX_TEXT_BYTES as MAX_TEXT_BYTES, XYG_WASM_TYPED_SERIES_PEAK_BYTES_PER_RECORD as PEAK_RECORD, XYG_WASM_TYPED_SERIES_PEAK_BYTES_PER_SERIES as PEAK_SERIES, XYG_WASM_TYPED_SERIES_PEAK_FIXED_BYTES as PEAK_FIXED, XYG_WASM_TYPED_SERIES_PEAK_INPUT_MULTIPLIER as PEAK_INPUT, XYG_WASM_TYPED_SERIES_VERSION } from "./wasm_abi_generated";

export type XygWasmChartSeriesKind = "scatter" | "line" | "bar" | "area";
export interface XygWasmChartSeries {
  kind: XygWasmChartSeriesKind; x: Float64Array; y: Float64Array;
  y1?: Float64Array; y0?: Float64Array; diameter?: number | Float64Array;
  symbol?: number;
  style?: { fillRgba?: Uint8Array | number[]; strokeRgba?: Uint8Array | number[]; strokeWidth?: number };
  stableIdBase?: bigint | number;
  /** Exact per-record identities; transferred without a main-thread row scan. */
  stableIds?: BigUint64Array;
}
export interface XygWasmChartCompileInput {
  width: number; height: number; margins?: [number, number, number, number];
  autoMargins?: boolean; autoDomain?: boolean; xAxisId?: bigint | number; yAxisId?: bigint | number;
  x?: { kind?: XygWasmScaleKind; lo?: number; hi?: number; constant?: number; maskNonpositive?: boolean };
  y?: { kind?: XygWasmScaleKind; lo?: number; hi?: number; constant?: number; maskNonpositive?: boolean };
  title?: string; xLabel?: string; yLabel?: string; series: XygWasmChartSeries[];
}
export interface XygWasmTypedSeriesRequest {
  prefix: ArrayBuffer; columns: ArrayBuffer[]; byteLength: number; peakBytes: number;
  /** Instrumented contract: framing visits descriptors, never records. */
  framedSeries: number; mainThreadRecordVisits: 0;
}
export interface XygWasmChartDiagnostics extends XygWasmDiagnostics {
  framedSeries: number; mainThreadRecordVisits: 0;
}

const align8 = (value: number) => (value + 7) & ~7;
function finite(view: DataView, offset: number, value: number, label: string) {
  if (!Number.isFinite(value)) throw new TypeError(`${label} must be finite`);
  view.setFloat64(offset, value, true);
}
function u64(view: DataView, offset: number, value: bigint | number, label: string) {
  if (typeof value === "number" && (!Number.isSafeInteger(value) || value < 0)) throw new TypeError(`${label} must be a safe nonnegative integer or bigint`);
  const parsed = typeof value === "bigint" ? value : BigInt(value);
  if (parsed < 0n || parsed > 0xffffffffffffffffn) throw new RangeError(`${label} must fit u64`);
  view.setBigUint64(offset, parsed, true);
}
function scale(value: XygWasmScaleKind | undefined) {
  if (value === undefined || value === "linear" || value === 0) return 0;
  if (value === "log" || value === 1) return 1;
  if (value === "symlog" || value === 2) return 2;
  throw new TypeError("scale kind must be linear, log, or symlog");
}
function kind(value: XygWasmChartSeriesKind) {
  const code = K[value];
  if (code === undefined) throw new TypeError("series kind must be scatter, line, bar, or area");
  return code;
}
function column(value: unknown, count: number, label: string) {
  if (!(value instanceof Float64Array) || value.length !== count) throw new TypeError(`${label} must be a Float64Array matching x length`);
  if (!(value.buffer instanceof ArrayBuffer) || value.byteOffset || value.byteLength !== value.buffer.byteLength) throw new TypeError(`${label} must own an exact transferable ArrayBuffer`);
  return value;
}
function stableIdColumn(value: unknown, count: number) {
  if (!(value instanceof BigUint64Array) || value.length !== count) {
    throw new TypeError("stableIds must be a BigUint64Array matching x length");
  }
  if (!(value.buffer instanceof ArrayBuffer) || value.byteOffset || value.byteLength !== value.buffer.byteLength) {
    throw new TypeError("stableIds must own an exact transferable ArrayBuffer");
  }
  return value;
}
function rgba(value: Uint8Array | number[] | undefined, label: string) {
  if (value === undefined) return null;
  if (value.length !== 4) throw new TypeError(`${label} must contain four channels`);
  const out = new Uint8Array(4);
  for (let index = 0; index < 4; index++) {
    const channel = value[index]!;
    if (!Number.isInteger(channel) || channel < 0 || channel > 255) throw new TypeError(`${label} channels must be integers in 0..255`);
    out[index] = channel;
  }
  return out;
}

/** O(series) framing only; Rust owns every per-record decision and expansion. */
export function frameWasmChart(input: XygWasmChartCompileInput): XygWasmTypedSeriesRequest {
  if (!input || !Array.isArray(input.series) || !input.series.length) throw new TypeError("series must be a non-empty array");
  if (input.series.length > MAX_SERIES) throw new RangeError("series exceeds the descriptor bound");
  const encode = new TextEncoder();
  const title = encode.encode(input.title ?? ""), xLabel = encode.encode(input.xLabel ?? ""), yLabel = encode.encode(input.yLabel ?? "");
  if ([title, xLabel, yLabel].some((text) => text.length > MAX_TEXT_BYTES)) throw new RangeError("chrome text exceeds the Rust scene text bound");
  const prefixLength = align8(HEADER + input.series.length * DESCRIPTOR + title.length + xLabel.length + yLabel.length);
  const prefix = new ArrayBuffer(prefixLength), bytes = new Uint8Array(prefix), view = new DataView(prefix);
  bytes.set(new TextEncoder().encode(XYG_WASM_TYPED_SERIES_MAGIC)); view.setUint32(H.version, XYG_WASM_TYPED_SERIES_VERSION, true); view.setUint32(H.header_bytes, HEADER, true);
  const explicit = input.x?.lo !== undefined || input.x?.hi !== undefined || input.y?.lo !== undefined || input.y?.hi !== undefined;
  view.setUint32(H.flags, (input.autoMargins ?? true ? HF.auto_margins : 0) | (input.autoDomain ?? !explicit ? HF.auto_domain : 0), true);
  view.setUint32(H.series_count, input.series.length, true); view.setUint32(H.title_bytes, title.length, true); view.setUint32(H.x_label_bytes, xLabel.length, true); view.setUint32(H.y_label_bytes, yLabel.length, true);
  finite(view, H.width, input.width, "width"); finite(view, H.height, input.height, "height");
  const margins = input.margins ?? [0, 0, 0, 0];
  if (margins.length !== 4) throw new TypeError("margins must have four values");
  margins.forEach((value, index) => finite(view, H.margins + index * 8, value, "margin"));
  u64(view, H.x_axis_id, input.xAxisId ?? 1, "xAxisId"); u64(view, H.y_axis_id, input.yAxisId ?? 2, "yAxisId");
  view.setUint32(H.x_scale_kind, scale(input.x?.kind), true); view.setUint32(H.y_scale_kind, scale(input.y?.kind), true);
  view.setUint32(H.x_mask_nonpositive, input.x?.maskNonpositive ? 1 : 0, true); view.setUint32(H.y_mask_nonpositive, input.y?.maskNonpositive ? 1 : 0, true);
  ([[H.x_lo, input.x?.lo ?? 0, "x.lo"], [H.x_hi, input.x?.hi ?? 1, "x.hi"], [H.x_constant, input.x?.constant ?? 1, "x.constant"], [H.y_lo, input.y?.lo ?? 0, "y.lo"], [H.y_hi, input.y?.hi ?? 1, "y.hi"], [H.y_constant, input.y?.constant ?? 1, "y.constant"]] as const).forEach(([offset, value, label]) => finite(view, offset, value, label));
  let textOffset = HEADER + input.series.length * DESCRIPTOR;
  bytes.set(title, textOffset); textOffset += title.length; bytes.set(xLabel, textOffset); textOffset += xLabel.length; bytes.set(yLabel, textOffset);
  const columns: ArrayBuffer[] = [], transferred = new Set<ArrayBuffer>(); let dataOffset = prefixLength, records = 0;
  const add = (value: Float64Array | BigUint64Array) => {
    const buffer = value.buffer as ArrayBuffer;
    if (transferred.has(buffer)) throw new TypeError("typed-series columns must own distinct transferable buffers");
    const end = dataOffset + value.byteLength;
    if (!Number.isSafeInteger(end) || end > 0xffffffff) {
      throw new RangeError("typed-series data exceeds the u32 column offset bound");
    }
    transferred.add(buffer);
    const offset = dataOffset; columns.push(buffer); dataOffset = end; return offset;
  };
  input.series.forEach((series, seriesIndex) => {
    if (!(series.x instanceof Float64Array) || !series.x.length) throw new TypeError("series x must be a non-empty Float64Array");
    if (series.kind !== "scatter" && (series.diameter !== undefined || series.symbol !== undefined)) {
      throw new TypeError("diameter and symbol are supported only for scatter series");
    }
    if ((series.kind === "scatter" || series.kind === "line")
        && (series.y0 !== undefined || series.y1 !== undefined)) {
      throw new TypeError("y0 and y1 are supported only for bar and area series");
    }
    if (series.kind === "line" && series.style?.fillRgba !== undefined) {
      throw new TypeError("line series do not support fillRgba");
    }
    const count = series.x.length, x = column(series.x, count, "x"), y = column(series.y, count, "y");
    records += count; if (records > MAX_RECORDS) throw new RangeError("typed series exceeds the record bound");
    const base = HEADER + seriesIndex * DESCRIPTOR; view.setUint32(base + D.kind, kind(series.kind), true); view.setUint32(base + D.record_count, count, true);
    const symbol = series.symbol ?? 0; if (!Number.isInteger(symbol) || symbol < 0 || symbol > MAX_SYMBOL) throw new TypeError(`symbol must be 0..${MAX_SYMBOL}`); view.setUint32(base + D.symbol, symbol, true);
    let flags = 0;
    if (series.diameter !== undefined && typeof series.diameter !== "number"
        && !(series.diameter instanceof Float64Array)) {
      throw new TypeError("diameter must be a number or a Float64Array");
    }
    const diameters = series.diameter instanceof Float64Array ? column(series.diameter, count, "diameter") : null;
    const lower = series.y0 ? column(series.y0, count, "y0") : null, upper = series.y1 ? column(series.y1, count, "y1") : null;
    if (diameters) flags |= F.diameters; if (lower) flags |= F.y0; if (upper) flags |= F.y1;
    const fill = rgba(series.style?.fillRgba, "fillRgba"), stroke = rgba(series.style?.strokeRgba, "strokeRgba");
    if (fill) { flags |= F.fill_rgba; bytes.set(fill, base + D.fill_rgba); } if (stroke) { flags |= F.stroke_rgba; bytes.set(stroke, base + D.stroke_rgba); }
    if (series.stableIdBase !== undefined && series.stableIds !== undefined) {
      throw new TypeError("stableIdBase and stableIds are mutually exclusive");
    }
    if (series.stableIdBase !== undefined) { flags |= F.stable_id_base; u64(view, base + D.stable_id_base, series.stableIdBase, "stableIdBase"); }
    view.setUint32(base + D.flags, flags, true);
    if (typeof series.diameter === "number") {
      if (series.diameter < 0) throw new TypeError("diameter must be nonnegative");
      finite(view, base + D.diameter, series.diameter, "diameter");
    } else view.setFloat64(base + D.diameter, Number.NaN, true);
    if (series.style?.strokeWidth !== undefined) {
      if (series.style.strokeWidth < 0) throw new TypeError("strokeWidth must be nonnegative");
      finite(view, base + D.stroke_width, series.style.strokeWidth, "strokeWidth");
    } else view.setFloat64(base + D.stroke_width, Number.NaN, true);
    view.setUint32(base + D.x, add(x), true); view.setUint32(base + D.y, add(y), true);
    if (lower) view.setUint32(base + D.y0, add(lower), true); if (upper) view.setUint32(base + D.y1, add(upper), true); if (diameters) view.setUint32(base + D.diameters, add(diameters), true);
    if (series.stableIds !== undefined) {
      flags |= F.stable_ids;
      view.setUint32(base + D.stable_ids, add(stableIdColumn(series.stableIds, count)), true);
      view.setUint32(base + D.flags, flags, true);
    }
  });
  view.setUint32(H.record_count, records, true);
  const peakBytes = dataOffset * PEAK_INPUT + records * PEAK_RECORD
    + input.series.length * PEAK_SERIES + PEAK_FIXED;
  if (!Number.isSafeInteger(peakBytes)) throw new RangeError("typed-series peak byte estimate overflowed");
  return { prefix, columns, byteLength: dataOffset, peakBytes, framedSeries: input.series.length, mainThreadRecordVisits: 0 };
}

export interface RenderWasmChartOptions {
  el: HTMLElement; chart: XygWasmChartCompileInput; worker: XygWasmWorker;
  /** Preserve caller arrays by default; opt into detaching zero-clone transfers explicitly. */
  dataOwnership?: "preserve" | "transfer";
  /** Caller-owned by default; opt in only for a Worker dedicated to this handle. */
  workerOwnership?: "borrow" | "own";
}
export class XygWasmChartHandle {
  private view: XygWasmSceneView | null = null;
  private task: XygWasmTask<XygWasmScenePaint> | null = null;
  private latest: XygWasmChartDiagnostics | null = null;
  private disposed = false;
  constructor(
    private readonly el: HTMLElement,
    private readonly worker: XygWasmWorker,
    private readonly transferData: boolean,
    private readonly ownWorker: boolean,
  ) {}
  async update(chart: XygWasmChartCompileInput): Promise<this> {
    if (this.disposed) throw new Error("XYG WASM chart handle was disposed");
    this.task?.cancel();
    const started = performance.now();
    let task: XygWasmTask<XygWasmScenePaint> | null = null;
    try {
      const framed = frameWasmChart(chart);
      task = this.worker.compilePrepareSeries(framed, {
        transfer: this.transferData,
      });
      this.task = task;
      const prepared = await task.result;
      if (this.disposed || this.task !== task) throw new Error("XYG WASM chart update became stale");
      const next = hydrateWasmPainter(this.el, prepared, { workerPrepareMs: performance.now() - started });
      this.view?.destroy(); this.view = next;
      this.latest = { ...prepared, framedSeries: framed.framedSeries, mainThreadRecordVisits: framed.mainThreadRecordVisits };
      this.task = null;
      return this;
    } catch (cause) {
      // Only the newest update owns visible-state cleanup. An older cancelled
      // task must not erase a view installed by a later successful update.
      if (!this.disposed && (task === null || this.task === task)) {
        this.task = null;
        this.view?.destroy(); this.view = null; this.latest = null;
      }
      throw cause;
    }
  }
  diagnostics(): XygWasmChartDiagnostics | null { return this.latest ? { ...this.latest } : null; }
  sceneStableId(traceIndex: number, rowIndex: number): bigint | null {
    if (!this.view) throw new Error("XYG WASM chart has not painted");
    return this.view.sceneStableId(traceIndex, rowIndex);
  }
  get gpuTraces() { return this.view?.gpuTraces ?? []; }
  async dispose(): Promise<void> {
    if (this.disposed) return; this.disposed = true; this.task?.cancel(); this.task = null;
    this.view?.destroy(); this.view = null;
    if (this.ownWorker) await this.worker.dispose();
  }
  destroy(): void { void this.dispose(); }
}
export async function renderWasmChart(options: RenderWasmChartOptions): Promise<XygWasmChartHandle> {
  if (!options?.el || !(options.worker instanceof XygWasmWorker) || !options.chart) throw new TypeError("el, chart, and an XygWasmWorker are required");
  if (options.dataOwnership !== undefined && !["preserve", "transfer"].includes(options.dataOwnership)) throw new TypeError("dataOwnership must be preserve or transfer");
  if (options.workerOwnership !== undefined && !["borrow", "own"].includes(options.workerOwnership)) throw new TypeError("workerOwnership must be borrow or own");
  await options.worker.ready;
  const handle = new XygWasmChartHandle(
    options.el,
    options.worker,
    options.dataOwnership === "transfer",
    options.workerOwnership === "own",
  );
  try {
    return await handle.update(options.chart);
  } catch (cause) {
    await handle.dispose();
    throw cause;
  }
}
