import { PROTOCOL } from "./00_header";
import { XygWasmError, XygWasmWorker, type XygWasmScenePaint } from "./47_wasm";
import { ChartView } from "./50_chartview";
import { XYG_WASM_PAINTER_HEADER_BYTES, XYG_WASM_PAINTER_MAX_LEGEND_BYTES, XYG_WASM_PAINTER_MAX_TRACES, XYG_WASM_PAINTER_TICK_BYTES, XYG_WASM_PAINTER_TRACE_BYTES, XYG_WASM_PAINTER_VERSION, XYG_WASM_SCENE_VERSION } from "./wasm_abi_generated";

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
  const f64 = (offset: number) => {
    const value = view.getFloat64(offset, true);
    if (!Number.isFinite(value)) throw new XygWasmError("XYG_WASM_MALFORMED_OUTPUT", "Rust painter chrome contains nonfinite geometry");
    return value;
  };
  if (String.fromCharCode(...bytes.subarray(0, 4)) !== "XYPB" || u32(4) !== XYG_WASM_PAINTER_VERSION || u32(8) !== XYG_WASM_SCENE_VERSION || u32(12) !== HEADER_BYTES || u32(16) !== TRACE_BYTES) throw new XygWasmError("XYG_WASM_MALFORMED_OUTPUT", "Rust painter contract version is incompatible");
  const traceCount = u32(20);
  if (traceCount > XYG_WASM_PAINTER_MAX_TRACES || HEADER_BYTES + traceCount * TRACE_BYTES > bytes.length) throw new XygWasmError("XYG_WASM_RESOURCE_LIMIT", "Rust painter descriptor table exceeds its bound");
  const width = f32(24), height = f32(28), left = f32(32), top = f32(36), right = f32(40), bottom = f32(44);
  if (!(width > 0 && height > 0 && right > left && bottom > top && left >= 0 && top >= 0 && right <= width && bottom <= height)) throw new XygWasmError("XYG_WASM_MALFORMED_OUTPUT", "Rust painter viewport is invalid");
  const columns: any[] = [], traces: any[] = [], annotations: any[] = [];
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
    const idHigh = count ? view.getUint32(columns[trace.scene_ids.hi].byte_offset, true) : 0;
    const annotationKind = (idHigh & 0xffff0000) === 0x58590000 ? (idHigh >>> 8) & 0xff : 0;
    if (annotationKind) {
      const px = (columnIndex: number, item = 0) => view.getFloat32(columns[columnIndex].byte_offset + item * 4, true);
      if (annotationKind === 1 && kind === 1 && count === 2) {
        const x0 = px(x), y0 = px(y), x1 = px(x, 1), y1 = px(y, 1);
        annotations.push(x0 === x1
          ? { kind: "rule", axis: "x", value: x0, style: { color: stroke, width: strokeWidth }, aria_label: "Vertical reference rule" }
          : y0 === y1
            ? { kind: "rule", axis: "y", value: y0, style: { color: stroke, width: strokeWidth }, aria_label: "Horizontal reference rule" }
            : (() => { throw new XygWasmError("XYG_WASM_MALFORMED_OUTPUT", "Rust annotation rule is not axis aligned"); })());
      } else if ((annotationKind === 2 || annotationKind === 4) && kind === 2 && count === 1) {
        const x0 = px(x), y0 = px(y), x1 = px(trace.x1), y1 = px(trace.y1);
        annotations.push(annotationKind === 2
          ? { kind: "band", axis: "x", start: x0, end: x1, style: { color: fill, opacity: 1 }, aria_label: "Vertical reference band" }
          : { kind: "band", axis: "y", start: y0, end: y1, style: { color: fill, opacity: 1 }, aria_label: "Horizontal reference band" });
      } else if (annotationKind === 3 && kind === 0 && count === 1) {
        annotations.push({ kind: "marker", x: px(x), y: px(y), size: diameter, symbol: SYMBOLS[symbol], style: { color: fill, stroke_color: stroke, stroke_width: strokeWidth, opacity: 1 }, aria_label: "Reference marker" });
      } else {
        throw new XygWasmError("XYG_WASM_MALFORMED_OUTPUT", "Rust annotation descriptor is invalid");
      }
      continue;
    }
    const markCount = kind === 4 ? 1 : count;
    Object.assign(trace, { id: index, name: null, tier: "direct", n_points: markCount, n_marks: markCount, x_axis: "x", y_axis: "y" });
    traces.push(trace);
  }
  const xTickCount = u32(48), yTickCount = u32(52), tickOffset = u32(56), stringOffset = u32(60);
  const tickCount = xTickCount + yTickCount;
  const tickBytes = tickCount * XYG_WASM_PAINTER_TICK_BYTES;
  if (!Number.isSafeInteger(tickCount) || tickCount > 400 || tickOffset !== expectedOffset || stringOffset !== tickOffset + tickBytes || stringOffset > bytes.length) throw new XygWasmError("XYG_WASM_MALFORMED_OUTPUT", "Rust painter chrome table is invalid");
  const decoder = new TextDecoder("utf-8", { fatal: true });
  const tickValues: number[] = [], tickLabels: string[] = [], tickMajor: boolean[] = [];
  let nextString = stringOffset;
  const textLengths = [u32(264), u32(268), u32(272)];
  if (textLengths.some((value) => value > 4096) || bytes.subarray(276, 280).some((value) => value !== 0)) throw new XygWasmError("XYG_WASM_MALFORMED_OUTPUT", "Rust painter chrome text header is invalid");
  const text = textLengths.map((length) => {
    const end = nextString + length;
    if (!Number.isSafeInteger(end) || end > bytes.length) throw new XygWasmError("XYG_WASM_MALFORMED_OUTPUT", "Rust painter chrome text range is invalid");
    try { return decoder.decode(bytes.subarray(nextString, end)); }
    catch { throw new XygWasmError("XYG_WASM_MALFORMED_OUTPUT", "Rust painter chrome text is invalid UTF-8"); }
    finally { nextString = end; }
  });
  for (let index = 0; index < tickCount; index++) {
    const descriptor = tickOffset + index * XYG_WASM_PAINTER_TICK_BYTES;
    const position = f32(descriptor), labelOffset = u32(descriptor + 4), labelLength = u32(descriptor + 8);
    const major = u32(descriptor + 12);
    if (major > 1 || labelOffset !== nextString || labelLength > 4096 || labelOffset + labelLength > bytes.length) throw new XygWasmError("XYG_WASM_MALFORMED_OUTPUT", "Rust painter tick descriptor is invalid");
    let label: string;
    try { label = decoder.decode(bytes.subarray(labelOffset, labelOffset + labelLength)); }
    catch { throw new XygWasmError("XYG_WASM_MALFORMED_OUTPUT", "Rust painter tick label is invalid UTF-8"); }
    tickValues.push(position); tickLabels.push(label); tickMajor.push(major === 1); nextString += labelLength;
  }
  const legendLength = u32(280);
  if (bytes.subarray(284, 288).some((value) => value !== 0) || legendLength > XYG_WASM_PAINTER_MAX_LEGEND_BYTES || nextString + legendLength !== bytes.length) throw new XygWasmError("XYG_WASM_MALFORMED_OUTPUT", "Rust painter legend range is invalid");
  let legend: any = null;
  if (legendLength) {
    const start = nextString;
    if (legendLength < 48 || String.fromCharCode(...bytes.subarray(start, start + 4)) !== "XYLG") throw new XygWasmError("XYG_WASM_MALFORMED_OUTPUT", "Rust painter legend header is invalid");
    const location = bytes[start + 4], entryCount = u32(start + 8), titleLength = u32(start + 12);
    if (location > 8 || entryCount === 0 || entryCount > 128 || bytes.subarray(start + 5, start + 8).some((value) => value !== 0) || bytes.subarray(start + 44, start + 48).some((value) => value !== 0)) throw new XygWasmError("XYG_WASM_MALFORMED_OUTPUT", "Rust painter legend metadata is invalid");
    const fontSize = f64(start + 16), titleFontSize = f64(start + 24), tableEnd = start + 48 + entryCount * 24;
    if (!(fontSize >= 1 && fontSize <= 1000 && titleFontSize >= 1 && titleFontSize <= 1000) || tableEnd > bytes.length) throw new XygWasmError("XYG_WASM_MALFORMED_OUTPUT", "Rust painter legend style is invalid");
    const textStart = tableEnd;
    let geometry = -1;
    for (let offset = start + legendLength - 4; offset >= textStart; offset--) {
      if (String.fromCharCode(...bytes.subarray(offset, offset + 4)) === "XYRG") { geometry = offset; break; }
    }
    if (geometry < textStart) throw new XygWasmError("XYG_WASM_MALFORMED_OUTPUT", "Rust painter legend geometry is invalid");
    const textLength = geometry - textStart;
    if (titleLength > textLength) throw new XygWasmError("XYG_WASM_MALFORMED_OUTPUT", "Rust painter legend title is invalid");
    const decodeLegend = (offset: number, length: number) => { try { return decoder.decode(bytes.subarray(textStart + offset, textStart + offset + length)); } catch { throw new XygWasmError("XYG_WASM_MALFORMED_OUTPUT", "Rust painter legend text is invalid UTF-8"); } };
    const title = decodeLegend(0, titleLength), items: any[] = []; let expected = titleLength;
    for (let index = 0; index < entryCount; index++) {
      const item = start + 48 + index * 24, kind = bytes[item + 4], symbol = bytes[item + 5], labelOffset = u32(item + 8), labelLength = u32(item + 12);
      if (kind > 4 || symbol >= SYMBOLS.length || (kind !== 0 && symbol !== 0) || bytes.subarray(item + 6, item + 8).some((value) => value !== 0) || labelOffset !== expected || labelLength === 0 || labelOffset + labelLength > textLength) throw new XygWasmError("XYG_WASM_MALFORMED_OUTPUT", "Rust painter legend entry is invalid");
      const fill = rgba(bytes.subarray(item + 16, item + 20)), stroke = rgba(bytes.subarray(item + 20, item + 24));
      items.push({ name: decodeLegend(labelOffset, labelLength), kind: kind === 0 ? "scatter" : kind === 1 ? "line" : "bar", style: { color: kind === 1 ? stroke : fill, fill, stroke, symbol: kind === 0 ? SYMBOLS[symbol] : undefined } });
      expected += labelLength;
    }
    if (expected !== textLength) throw new XygWasmError("XYG_WASM_MALFORMED_OUTPUT", "Rust painter legend entry is invalid");
    const tableEndGeometry = geometry + 32 + entryCount * 40;
    if (tableEndGeometry > start + legendLength || String.fromCharCode(...bytes.subarray(geometry, geometry + 4)) !== "XYRG" || u32(geometry + 4) !== 1) throw new XygWasmError("XYG_WASM_MALFORMED_OUTPUT", "Rust painter legend geometry is invalid");
    const finite = (offset: number) => { const value = f32(offset); if (!Number.isFinite(value)) throw new XygWasmError("XYG_WASM_MALFORMED_OUTPUT", "Rust painter legend geometry is non-finite"); return value; };
    const bounds = [finite(geometry + 8), finite(geometry + 12), finite(geometry + 16), finite(geometry + 20)];
    const titlePosition = [finite(geometry + 24), finite(geometry + 28)];
    let nextPath = tableEndGeometry;
    for (let index = 0; index < entryCount; index++) {
      const item = geometry + 32 + index * 40, primitive = u32(item + 24), fillNone = u32(item + 28), strokeWidth = finite(item + 32), pathLength = u32(item + 36);
      if (primitive > 3 || fillNone > 1 || strokeWidth < 0 || (primitive === 3) !== (pathLength > 0)) throw new XygWasmError("XYG_WASM_MALFORMED_OUTPUT", "Rust painter legend swatch is invalid");
      if (nextPath + pathLength > start + legendLength) throw new XygWasmError("XYG_WASM_MALFORMED_OUTPUT", "Rust painter legend swatch path is invalid");
      let path = ""; try { path = decoder.decode(bytes.subarray(nextPath, nextPath + pathLength)); } catch { throw new XygWasmError("XYG_WASM_MALFORMED_OUTPUT", "Rust painter legend swatch path is invalid UTF-8"); }
      items[index].geometry = { label: [finite(item), finite(item + 4)], swatch: [finite(item + 8), finite(item + 12), finite(item + 16), finite(item + 20)], primitive, fillNone: fillNone === 1, strokeWidth, path };
      nextPath += pathLength;
    }
    if (nextPath !== start + legendLength) throw new XygWasmError("XYG_WASM_MALFORMED_OUTPUT", "Rust painter legend geometry has trailing bytes");
    legend = { resolved: { bounds, title: titlePosition }, title: title || null, items, toggle: false, highlight: false, style: { color: rgba(bytes.subarray(start + 32, start + 36)), background: rgba(bytes.subarray(start + 36, start + 40)), border: rgba(bytes.subarray(start + 40, start + 44)), "font-size": fontSize }, title_style: { "font-size": titleFontSize } };
  }
  nextString += legendLength;
  if (nextString !== bytes.length) throw new XygWasmError("XYG_WASM_MALFORMED_OUTPUT", "Rust painter output has trailing bytes");
  const chrome = 64;
  if (bytes.subarray(chrome + 12, chrome + 16).some((value) => value !== 0)) throw new XygWasmError("XYG_WASM_MALFORMED_OUTPUT", "Rust painter chrome reserved bytes are nonzero");
  const labelSize = f64(chrome + 16);
  const axis = (id: string, range: number[], start: number, count: number, isX: boolean, axisOffset: number) => {
    if (bytes.subarray(axisOffset + 5, axisOffset + 8).some((value) => value !== 0)) throw new XygWasmError("XYG_WASM_MALFORMED_OUTPUT", "Rust painter axis reserved bytes are nonzero");
    const sideCode = bytes[axisOffset], tickMask = bytes[axisOffset + 1], labelMask = bytes[axisOffset + 2], majorDirection = bytes[axisOffset + 3], minorDirection = bytes[axisOffset + 4];
    if (sideCode > 1 || tickMask > 3 || labelMask > 3 || majorDirection > 2 || minorDirection > 2) throw new XygWasmError("XYG_WASM_MALFORMED_OUTPUT", "Rust painter axis style is invalid");
    const sides = isX ? ["bottom", "top"] : ["left", "right"];
    const direction = ["out", "in", "inout"];
    const numbers = Array.from({ length: 7 }, (_, index) => f64(axisOffset + 32 + index * 8));
    if (numbers.some((value) => value < 0 || value > 1000) || !(labelSize > 0 && labelSize <= 1000)) throw new XygWasmError("XYG_WASM_MALFORMED_OUTPUT", "Rust painter axis geometry is outside bounds");
    const majorValues: number[] = [], majorLabels: string[] = [], minorValues: number[] = [];
    for (let index = start; index < start + count; index++) {
      if (tickMajor[index]) { majorValues.push(tickValues[index]); majorLabels.push(tickLabels[index]); }
      else minorValues.push(tickValues[index]);
    }
    const labelColor = rgba(bytes.subarray(axisOffset + 28, axisOffset + 32));
    return { id, scale: "linear", range, tick_values: majorValues, minor_tick_values: minorValues, tick_labels: majorLabels, tick_label_strategy: "auto", tick_sides: sides.filter((_, index) => tickMask & (1 << index)), tick_label_sides: sides.filter((_, index) => labelMask & (1 << index)), grid: true, side: sides[sideCode], style: { axis_color: rgba(bytes.subarray(axisOffset + 8, axisOffset + 12)), grid_color: rgba(bytes.subarray(axisOffset + 12, axisOffset + 16)), tick_color: rgba(bytes.subarray(axisOffset + 16, axisOffset + 20)), tick_label_color: labelColor, label_color: labelColor, axis_width: numbers[0], grid_width: numbers[1], tick_width: numbers[2], tick_length: numbers[3], tick_direction: direction[majorDirection], tick_label_size: labelSize, label_size: labelSize }, minor_style: { grid_color: rgba(bytes.subarray(axisOffset + 20, axisOffset + 24)), tick_color: rgba(bytes.subarray(axisOffset + 24, axisOffset + 28)), grid_width: numbers[4], tick_width: numbers[5], tick_length: numbers[6], tick_direction: direction[minorDirection] } };
  };
  const xAxis = { ...axis("x", [left, right], 0, xTickCount, true, chrome + 24), label: text[1] };
  const yAxis = { ...axis("y", [bottom, top], xTickCount, yTickCount, false, chrome + 112), label: text[2] };
  return { spec: { protocol: PROTOCOL, width, height, padding: [top, width - right, height - bottom, left], title: text[0] || null, x_axis: xAxis, y_axis: yAxis, axes: { x: xAxis, y: yAxis }, traces, annotations, columns, dom: { style: { background: rgba(bytes.subarray(chrome, chrome + 4)), "--chart-bg": rgba(bytes.subarray(chrome + 4, chrome + 8)) }, styles: { title: { color: rgba(bytes.subarray(chrome + 8, chrome + 12)), "font-size": labelSize + 2 }, ...(legend ? { legend_title: { color: legend.style.color, "font-size": legend.title_style["font-size"] }, legend_label: { color: legend.style.color, "font-size": legend.style["font-size"] } } : {}) } }, legend, show_legend: legend != null, show_modebar: false, show_tooltip: false, frame_sides: [xAxis.side, yAxis.side], interaction: { drag_action: "none" }, view: { ranges: { x: [left, right], y: [bottom, top] } } }, payload: bytes };
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
