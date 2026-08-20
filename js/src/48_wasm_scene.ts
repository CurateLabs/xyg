import { PROTOCOL } from "./00_header";
import { XygWasmError, XygWasmWorker, type XygWasmScenePaint } from "./47_wasm";
import { ChartView } from "./50_chartview";
import { XYG_WASM_PAINTER_HEADER_BYTES, XYG_WASM_PAINTER_MAX_TRACES, XYG_WASM_PAINTER_TICK_BYTES, XYG_WASM_PAINTER_TRACE_BYTES, XYG_WASM_PAINTER_VERSION, XYG_WASM_SCENE_VERSION } from "./wasm_abi_generated";

const HEADER_BYTES = XYG_WASM_PAINTER_HEADER_BYTES, TRACE_BYTES = XYG_WASM_PAINTER_TRACE_BYTES;
const SYMBOLS = ["circle", "square", "diamond", "triangle", "cross", "hexagon", "pentagon", "star", "triangle_down", "triangle_left", "triangle_right", "x", "point", "pixel", "thin_diamond", "plus_line", "x_line", "horizontal_line", "vertical_line"] as const;

function rgba(bytes: Uint8Array): string {
  return `rgba(${bytes[0]} ${bytes[1]} ${bytes[2]} / ${bytes[3] / 255})`;
}

function compilePainter(painter: ArrayBuffer) {
  if (!(painter instanceof ArrayBuffer) || painter.byteLength < HEADER_BYTES) throw new XygWasmError("XYG_WASM_MALFORMED_OUTPUT", "Rust painter output is truncated");
  const bytes = new Uint8Array(painter), view = new DataView(painter);
  const u32 = (offset: number) => view.getUint32(offset, true);
  const f32 = (offset: number) => {
    const value = view.getFloat32(offset, true);
    if (!Number.isFinite(value)) throw new XygWasmError("XYG_WASM_MALFORMED_OUTPUT", "Rust painter output contains nonfinite geometry");
    return value;
  };
  if (String.fromCharCode(...bytes.subarray(0, 4)) !== "XYPB" || u32(4) !== XYG_WASM_PAINTER_VERSION || u32(8) !== XYG_WASM_SCENE_VERSION || u32(12) !== HEADER_BYTES || u32(16) !== TRACE_BYTES) throw new XygWasmError("XYG_WASM_MALFORMED_OUTPUT", "Rust painter contract version is incompatible");
  const traceCount = u32(20);
  if (traceCount > XYG_WASM_PAINTER_MAX_TRACES || HEADER_BYTES + traceCount * TRACE_BYTES > bytes.length) throw new XygWasmError("XYG_WASM_RESOURCE_LIMIT", "Rust painter descriptor table exceeds its bound");
  const width = f32(24), height = f32(28), left = f32(32), top = f32(36), right = f32(40), bottom = f32(44);
  if (!(width > 0 && height > 0 && right > left && bottom > top && left >= 0 && top >= 0 && right <= width && bottom <= height)) throw new XygWasmError("XYG_WASM_MALFORMED_OUTPUT", "Rust painter viewport is invalid");
  const columns: any[] = [], traces: any[] = [];
  let expectedOffset = HEADER_BYTES + traceCount * TRACE_BYTES;
  const column = (descriptor: number, slot: number, count: number, dtype = "f32") => {
    const offset = u32(descriptor + slot), end = offset + count * 4;
    if (offset !== expectedOffset || !Number.isSafeInteger(end) || end > bytes.length) throw new XygWasmError("XYG_WASM_MALFORMED_OUTPUT", "Rust painter column range is invalid");
    expectedOffset = end;
    const index = columns.length;
    columns.push({ byte_offset: offset, len: count, ...(dtype === "u32" ? { dtype } : {}) });
    return index;
  };
  for (let index = 0; index < traceCount; index++) {
    const descriptor = HEADER_BYTES + index * TRACE_BYTES;
    const kind = bytes[descriptor], symbol = bytes[descriptor + 1], count = u32(descriptor + 4);
    if (bytes[descriptor + 2] !== 0 || bytes[descriptor + 3] !== 0 || bytes.subarray(descriptor + 48, descriptor + 64).some((value) => value !== 0) || count > 2_000_000) throw new XygWasmError("XYG_WASM_MALFORMED_OUTPUT", "Rust painter trace descriptor is invalid");
    const fill = rgba(bytes.subarray(descriptor + 32, descriptor + 36)), stroke = rgba(bytes.subarray(descriptor + 36, descriptor + 40));
    const strokeWidth = f32(descriptor + 40), diameter = f32(descriptor + 44);
    if (strokeWidth < 0 || diameter < 0) throw new XygWasmError("XYG_WASM_MALFORMED_OUTPUT", "Rust painter style is invalid");
    const x = column(descriptor, 8, count), y = column(descriptor, 12, count);
    let trace: any;
    if (kind === 0) {
      if (symbol >= SYMBOLS.length || u32(descriptor + 16) !== 0 || u32(descriptor + 20) !== 0) throw new XygWasmError("XYG_WASM_MALFORMED_OUTPUT", "Rust scatter descriptor is invalid");
      trace = { kind: "scatter", x, y, color: { mode: "constant", color: fill }, size: { mode: "constant", size: diameter }, style: { symbol: SYMBOLS[symbol], stroke, stroke_width: strokeWidth } };
    } else if (kind === 1) {
      if (symbol !== 0 || diameter !== 0 || u32(descriptor + 16) !== 0 || u32(descriptor + 20) !== 0) throw new XygWasmError("XYG_WASM_MALFORMED_OUTPUT", "Rust polyline descriptor is invalid");
      trace = { kind: "line", x, y, style: { color: stroke, width: strokeWidth } };
    } else if (kind === 2) {
      if (symbol !== 0 || diameter !== 0) throw new XygWasmError("XYG_WASM_MALFORMED_OUTPUT", "Rust rectangle descriptor is invalid");
      trace = { kind: "box", x0: x, y0: y, x1: column(descriptor, 16, count), y1: column(descriptor, 20, count), style: { color: fill, stroke, stroke_width: strokeWidth } };
    } else if (kind === 3) {
      if (symbol !== 0 || diameter !== 0) throw new XygWasmError("XYG_WASM_MALFORMED_OUTPUT", "Rust band descriptor is invalid");
      const x1 = column(descriptor, 16, count), y1 = column(descriptor, 20, count);
      // Area paint uses one x with a y-base; Rust rejects unequal band x pairs.
      trace = { kind: "area", x, y, base: y1, style: { color: fill, fill, stroke, stroke_width: strokeWidth, opacity: 1 } };
      void x1;
    } else if (kind === 4) {
      if (symbol !== 0 || diameter !== 0) throw new XygWasmError("XYG_WASM_MALFORMED_OUTPUT", "Rust polyfill descriptor is invalid");
      if (count !== 3) throw new XygWasmError("XYG_WASM_MALFORMED_OUTPUT", "Rust polyfill browser paint currently requires three vertices");
      const at = (colIndex: number, i: number) => {
        const source = columns[colIndex];
        const index = columns.length;
        columns.push({ byte_offset: source.byte_offset + i * 4, len: 1 });
        return index;
      };
      trace = {
        kind: "triangle_mesh",
        x0: at(x, 0), y0: at(y, 0), x1: at(x, 1), y1: at(y, 1), x2: at(x, 2), y2: at(y, 2),
        color: { mode: "constant", color: fill },
        style: { color: fill, stroke, stroke_width: strokeWidth },
      };
    } else throw new XygWasmError("XYG_WASM_UNSUPPORTED", `unsupported Rust painter trace ${kind}`);
    trace.scene_ids = { lo: column(descriptor, 24, count, "u32"), hi: column(descriptor, 28, count, "u32") };
    const markCount = kind === 4 ? 1 : count;
    Object.assign(trace, { id: index, name: null, tier: "direct", n_points: markCount, n_marks: markCount, x_axis: "x", y_axis: "y" });
    traces.push(trace);
  }
  const xTickCount = u32(48), yTickCount = u32(52), tickOffset = u32(56), stringOffset = u32(60);
  const tickCount = xTickCount + yTickCount;
  const tickBytes = tickCount * XYG_WASM_PAINTER_TICK_BYTES;
  if (!Number.isSafeInteger(tickCount) || tickCount > 400 || tickOffset !== expectedOffset || stringOffset !== tickOffset + tickBytes || stringOffset > bytes.length) throw new XygWasmError("XYG_WASM_MALFORMED_OUTPUT", "Rust painter chrome table is invalid");
  const decoder = new TextDecoder("utf-8", { fatal: true });
  const tickValues: number[] = [], tickLabels: string[] = [];
  let nextString = stringOffset;
  for (let index = 0; index < tickCount; index++) {
    const descriptor = tickOffset + index * XYG_WASM_PAINTER_TICK_BYTES;
    const position = f32(descriptor), labelOffset = u32(descriptor + 4), labelLength = u32(descriptor + 8);
    if (u32(descriptor + 12) !== 0 || labelOffset !== nextString || labelLength > 4096 || labelOffset + labelLength > bytes.length) throw new XygWasmError("XYG_WASM_MALFORMED_OUTPUT", "Rust painter tick descriptor is invalid");
    let label: string;
    try { label = decoder.decode(bytes.subarray(labelOffset, labelOffset + labelLength)); }
    catch { throw new XygWasmError("XYG_WASM_MALFORMED_OUTPUT", "Rust painter tick label is invalid UTF-8"); }
    tickValues.push(position); tickLabels.push(label); nextString += labelLength;
  }
  if (nextString !== bytes.length) throw new XygWasmError("XYG_WASM_MALFORMED_OUTPUT", "Rust painter output has trailing bytes");
  const axis = (id: string, range: number[], start: number, count: number, side: "bottom" | "left") => ({ id, scale: "linear", range, tick_values: tickValues.slice(start, start + count), tick_labels: tickLabels.slice(start, start + count), tick_label_strategy: "auto", tick_sides: [side], tick_label_sides: [side], grid: true, side, style: { grid_color: "rgba(32 32 32 / 0.14)", grid_width: 1, axis_color: "rgba(32 32 32 / 0.55)", axis_width: 1, tick_color: "rgba(32 32 32 / 0.55)", tick_width: 1, tick_length: 4, tick_label_color: "rgba(32 32 32 / 0.85)", tick_label_size: 12 } });
  const xAxis = axis("x", [left, right], 0, xTickCount, "bottom"), yAxis = axis("y", [bottom, top], xTickCount, yTickCount, "left");
  return { spec: { protocol: PROTOCOL, width, height, padding: [top, width - right, height - bottom, left], title: null, x_axis: xAxis, y_axis: yAxis, axes: { x: xAxis, y: yAxis }, traces, columns, show_legend: false, show_modebar: false, show_tooltip: false, frame_sides: ["bottom", "left"], interaction: { drag_action: "none" }, view: { ranges: { x: [left, right], y: [bottom, top] } } }, payload: bytes };
}

export interface RenderWasmSceneOptions { el: HTMLElement; scene: ArrayBuffer | Uint8Array; worker: XygWasmWorker; transfer?: boolean }
export interface XygWasmSceneView extends ChartView {
  sceneStableId(traceIndex: number, rowIndex: number): bigint | null;
  wasmMetrics: { workerPrepareMs: number; hydrateUploadMs: number; painterBytes: number; wasmMemoryBytes: number };
}

/** Hydrate painter-ready WASM output into the existing WebGL client. */
export function hydrateWasmPainter(
  el: HTMLElement,
  prepared: XygWasmScenePaint,
  timing: { workerPrepareMs: number } = { workerPrepareMs: 0 },
): XygWasmSceneView {
  const preparedAt = performance.now();
  const compiled = compilePainter(prepared.painter);
  const view = new ChartView(el, compiled.spec, compiled.payload, null);
  (view as any).wasmMetrics = {
    workerPrepareMs: timing.workerPrepareMs,
    hydrateUploadMs: performance.now() - preparedAt,
    painterBytes: prepared.painter.byteLength,
    wasmMemoryBytes: prepared.memoryBytes,
  };
  for (const trace of view.gpuTraces) {
    const ids = trace.trace.scene_ids;
    trace._sceneIds = {
      lo: view._columnView(compiled.payload, compiled.spec.columns[ids.lo]),
      hi: view._columnView(compiled.payload, compiled.spec.columns[ids.hi]),
    };
  }
  (view as any).sceneStableId = (traceIndex: number, rowIndex: number) => {
    const ids = view.gpuTraces[traceIndex]?._sceneIds;
    if (!ids || !Number.isInteger(rowIndex) || rowIndex < 0 || rowIndex >= ids.lo.length) return null;
    return (BigInt(ids.hi[rowIndex]) << 32n) | BigInt(ids.lo[rowIndex]);
  };
  return view as XygWasmSceneView;
}

/** Validate/lower in Rust, then hydrate the existing WebGL painter. */
export async function renderWasmScene(options: RenderWasmSceneOptions): Promise<XygWasmSceneView> {
  if (!options?.el || !(options.worker instanceof XygWasmWorker)) throw new TypeError("el and an XygWasmWorker are required");
  await options.worker.ready;
  const started = performance.now();
  const prepared: XygWasmScenePaint = await options.worker.prepareScene(options.scene, { transfer: options.transfer }).result;
  return hydrateWasmPainter(options.el, prepared, { workerPrepareMs: performance.now() - started });
}
