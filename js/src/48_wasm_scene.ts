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
  let awaitingCalloutHead = false;
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
    const kind = bytes[descriptor], symbol = bytes[descriptor + 1], annotationKind = bytes[descriptor + 2], count = u32(descriptor + 4);
    if (annotationKind > 6 || bytes[descriptor + 3] !== 0 || bytes.subarray(descriptor + 48, descriptor + 64).some((value) => value !== 0) || count > 2_000_000) throw new XygWasmError("XYG_WASM_MALFORMED_OUTPUT", "Rust painter trace descriptor is invalid");
    if (awaitingCalloutHead && !(annotationKind === 6 && kind === 4 && count === 3)) throw new XygWasmError("XYG_WASM_MALFORMED_OUTPUT", "Rust Cartesian callout leader has no matching head");
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
      if (symbol > 2 || diameter !== 0) throw new XygWasmError("XYG_WASM_MALFORMED_OUTPUT", "Rust band descriptor is invalid");
      const x1 = column(descriptor, 16, count), y1 = column(descriptor, 20, count);
      // Area paint uses one x with a y-base; Rust rejects unequal band x pairs.
      trace = {
        kind: "area", x, y, base: y1,
        style: {
          color: fill,
          fill,
          line_color: stroke,
          line_width: symbol === 0 ? 0 : strokeWidth,
          line_opacity: 1,
          stroke_perimeter: symbol === 2,
          opacity: 1,
        },
      };
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
      } else if (annotationKind === 5 && kind === 1 && count === 2) {
        // A straight arrow is emitted as its canonical shaft followed by its
        // triangular head. Keep both primitives as painter traces so the
        // Rust-authored geometry remains exact, and expose one semantic note.
        annotations.push({ kind: "straight_arrow", aria_label: "Straight arrow annotation" });
      } else if (annotationKind === 5 && kind === 4 && count === 3) {
        // The matching arrow shaft owns the semantic note above; this is its
        // fixed, Rust-authored triangular head.
      } else if (annotationKind === 6 && kind === 1 && count === 2) {
        // A Cartesian callout is emitted as its Rust-authored leader followed
        // by a fixed triangular head and a scene label. Keep the primitives in
        // their exact painter order, but expose one semantic accessibility note.
        if (awaitingCalloutHead) throw new XygWasmError("XYG_WASM_MALFORMED_OUTPUT", "Rust Cartesian callout leader has no matching head");
        awaitingCalloutHead = true;
        annotations.push({ kind: "cartesian_callout", aria_label: "Cartesian callout annotation" });
      } else if (annotationKind === 6 && kind === 4 && count === 3) {
        // The matching leader owns the semantic note above; this is its head.
        awaitingCalloutHead = false;
      } else {
        throw new XygWasmError("XYG_WASM_MALFORMED_OUTPUT", "Rust annotation descriptor is invalid");
      }
      if (annotationKind !== 5 && annotationKind !== 6) continue;
    }
    const markCount = kind === 4 ? 1 : count;
    Object.assign(trace, { id: index, name: null, tier: "direct", n_points: markCount, n_marks: markCount, x_axis: "x", y_axis: "y" });
    traces.push(trace);
  }
  if (awaitingCalloutHead) throw new XygWasmError("XYG_WASM_MALFORMED_OUTPUT", "Rust Cartesian callout leader has no matching head");
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
  const legendLength = u32(280), colorbarLength = u32(284), sceneLabelLength = u32(288);
  // XYCB input (4,600 bytes) is followed by bounded XYRG/XYCT geometry and
  // resolved labels. This is deliberately the Rust-owned painter ceiling, not
  // merely the host-framed input ceiling.
  const maxColorbarPainterBytes = 4_600 + 24 + 16 + (32 + 124) * 16 + 32 * 32;
  if (legendLength > XYG_WASM_PAINTER_MAX_LEGEND_BYTES || colorbarLength > maxColorbarPainterBytes || sceneLabelLength > 18_960 || nextString + legendLength + colorbarLength + sceneLabelLength !== bytes.length) throw new XygWasmError("XYG_WASM_MALFORMED_OUTPUT", "Rust painter decoration range is invalid");
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
  let colorbar: any = null;
  if (colorbarLength) {
    const start = nextString, end = start + colorbarLength;
    if (colorbarLength < 120 || String.fromCharCode(...bytes.subarray(start, start + 4)) !== "XYCB" || u32(start + 4) !== 2) throw new XygWasmError("XYG_WASM_MALFORMED_OUTPUT", "Rust painter colorbar header is invalid");
    const flags = bytes[start + 8], count = u32(start + 12), tickCount = u32(start + 16), titleLength = u32(start + 20);
    const lo = f64(start + 24), hi = f64(start + 32), tableEnd = start + 56 + count * 12, ticksEnd = tableEnd + tickCount * 8, geometry = ticksEnd + titleLength;
    if (flags > 15 || !(flags & 2) || Boolean(flags & 8) !== Boolean(tickCount) || count < 2 || count > 16 || tickCount > 32 || titleLength > 4096 || !(lo < hi) || geometry + 40 > end || String.fromCharCode(...bytes.subarray(geometry, geometry + 4)) !== "XYRG" || u32(geometry + 4) !== 1) throw new XygWasmError("XYG_WASM_MALFORMED_OUTPUT", "Rust painter colorbar payload is invalid");
    const stops = Array.from({length: count}, (_, index) => ({ value: f64(start + 56 + index * 12), color: rgba(bytes.subarray(start + 64 + index * 12, start + 68 + index * 12)) }));
    if (stops.some((stop, index) => !Number.isFinite(stop.value) || stop.value < lo || stop.value > hi || (index && stop.value <= stops[index - 1].value))) throw new XygWasmError("XYG_WASM_MALFORMED_OUTPUT", "Rust painter colorbar stops are invalid");
    const authoredTicks = Array.from({length: tickCount}, (_, index) => f64(tableEnd + index * 8));
    if (authoredTicks.some((value, index) => !Number.isFinite(value) || value < lo || value > hi || (index && value <= authoredTicks[index - 1]))) throw new XygWasmError("XYG_WASM_MALFORMED_OUTPUT", "Rust painter colorbar ticks are invalid");
    let title: string; try { title = decoder.decode(bytes.subarray(ticksEnd, geometry)); } catch { throw new XygWasmError("XYG_WASM_MALFORMED_OUTPUT", "Rust painter colorbar title is invalid UTF-8"); }
    const tickBlock = geometry + 24;
    if (String.fromCharCode(...bytes.subarray(tickBlock, tickBlock + 4)) !== "XYCT" || u32(tickBlock + 4) !== 1) throw new XygWasmError("XYG_WASM_MALFORMED_OUTPUT", "Rust painter colorbar ticks are invalid");
    const majorCount = u32(tickBlock + 8), minorCount = u32(tickBlock + 12), total = majorCount + minorCount, records = tickBlock + 16, labels = records + total * 16;
    if (!Number.isSafeInteger(total) || majorCount > 32 || minorCount > 124 || labels > end) throw new XygWasmError("XYG_WASM_MALFORMED_OUTPUT", "Rust painter colorbar tick limits are invalid");
    let labelOffset = labels;
    const resolvedTicks = Array.from({length: total}, (_, index) => {
      const at = records + index * 16, value = f64(at), position = f32(at + 8), length = u32(at + 12);
      if (!Number.isFinite(value) || !Number.isFinite(position) || value < lo || value > hi || labelOffset + length > end) throw new XygWasmError("XYG_WASM_MALFORMED_OUTPUT", "Rust painter colorbar tick record is invalid");
      let label = ""; try { label = decoder.decode(bytes.subarray(labelOffset, labelOffset + length)); } catch { throw new XygWasmError("XYG_WASM_MALFORMED_OUTPUT", "Rust painter colorbar tick label is invalid UTF-8"); }
      labelOffset += length; return { value, position, label };
    });
    if (labelOffset !== end || resolvedTicks.slice(0, majorCount).some((tick, index, values) => index && tick.value <= values[index - 1].value) || resolvedTicks.slice(majorCount).some((tick, index, values) => index && tick.value <= values[index - 1].value)) throw new XygWasmError("XYG_WASM_MALFORMED_OUTPUT", "Rust painter colorbar tick order is invalid");
    colorbar = { domain: [lo, hi], orientation: flags & 1 ? "horizontal" : "vertical", placement: "scene", levels: count - 1, boundaries: stops.map((stop) => stop.value), band_colors: stops.slice(0, -1).map((_, index) => Array.from(bytes.subarray(start + 64 + index * 12, start + 68 + index * 12))), ticks: resolvedTicks.slice(0, majorCount).map((tick) => tick.value), minor_ticks: Boolean(flags & 4), text_color: rgba(bytes.subarray(start + 40, start + 44)), label: title || null, resolved: { bounds: [f32(geometry + 8), f32(geometry + 12), f32(geometry + 16), f32(geometry + 20)], major_ticks: resolvedTicks.slice(0, majorCount), minor_ticks: resolvedTicks.slice(majorCount) } };
  }
  nextString += colorbarLength;
  const sceneLabels: Array<{stableId: bigint; x: number; y: number; fontSize: number; color: string; anchor: number; text: string; box?: {x: number; y: number; width: number; height: number; fill: string; border?: {color: string; width: number}}}> = [];
  if (sceneLabelLength) {
    const start = nextString, end = start + sceneLabelLength;
    const version = u32(start + 4);
    if (sceneLabelLength < 16 || String.fromCharCode(...bytes.subarray(start, start + 4)) !== "XYLB" || (version !== 1 && version !== 2 && version !== 3 && version !== 4 && version !== 5)) throw new XygWasmError("XYG_WASM_MALFORMED_OUTPUT", "Rust painter label header is invalid");
    const count = u32(start + 8), textBytes = u32(start + 12), recordBytes = version === 1 ? 40 : version === 2 ? 44 : version === 3 ? 84 : version === 4 ? 100 : 104, tableEnd = start + 16 + count * recordBytes;
    if (count > 128 || textBytes > 8192 || tableEnd + textBytes !== end) throw new XygWasmError("XYG_WASM_MALFORMED_OUTPUT", "Rust painter label table is invalid");
    let textOffset = tableEnd;
    for (let index = 0; index < count; index++) {
      const record = start + 16 + index * recordBytes, x = f64(record + 8), y = f64(record + 16), fontSize = f64(record + 24);
      const anchor = version === 1 ? 0 : bytes[record + 36];
      const length = u32(record + (version === 1 ? 36 : 40));
      if (!(x >= 0 && x <= width && y >= 0 && y <= height && fontSize >= 1 && fontSize <= 1000) || anchor > 2 || (version >= 2 && bytes.subarray(record + 37, record + 40).some((value) => value !== 0)) || textOffset + length > end) throw new XygWasmError("XYG_WASM_MALFORMED_OUTPUT", "Rust painter label geometry is invalid");
      let label: string; try { label = decoder.decode(bytes.subarray(textOffset, textOffset + length)); } catch { throw new XygWasmError("XYG_WASM_MALFORMED_OUTPUT", "Rust painter label text is invalid UTF-8"); }
      if (!label || label.includes("\0")) throw new XygWasmError("XYG_WASM_MALFORMED_OUTPUT", "Rust painter label text is invalid");
      if (version === 5) { const lines = u32(record + 100); if (lines === 0 || lines > 16 || label.split("\n").length !== lines || label.split("\n").some((line) => !line)) throw new XygWasmError("XYG_WASM_MALFORMED_OUTPUT", "Rust painter wrapped label is invalid"); }
      let box: {x: number; y: number; width: number; height: number; fill: string; border?: {color: string; width: number}} | undefined;
      if (version >= 3) {
        const flags = bytes[record + 44];
        const boxX = f64(record + 48), boxY = f64(record + 56), boxWidth = f64(record + 64), boxHeight = f64(record + 72), fill = bytes.subarray(record + 80, record + 84);
        if (flags > 1 || bytes.subarray(record + 45, record + 48).some((value) => value !== 0)) throw new XygWasmError("XYG_WASM_MALFORMED_OUTPUT", "Rust painter label box flags are invalid");
        if (flags) {
          if (!(Number.isFinite(boxX) && Number.isFinite(boxY) && boxWidth > 0 && boxHeight > 0 && boxX >= 0 && boxY >= 0 && boxX + boxWidth <= width && boxY + boxHeight <= height && fill[3] > 0)) throw new XygWasmError("XYG_WASM_MALFORMED_OUTPUT", "Rust painter label box geometry is invalid");
          box = {x: boxX, y: boxY, width: boxWidth, height: boxHeight, fill: rgba(fill)};
        } else if (boxX !== 0 || boxY !== 0 || boxWidth !== 0 || boxHeight !== 0 || fill.some((value) => value !== 0)) {
          throw new XygWasmError("XYG_WASM_MALFORMED_OUTPUT", "Rust painter label box is noncanonical");
        }
      }
      if (version === 4) {
        const borderFlags = bytes[record + 84], border = bytes.subarray(record + 88, record + 92), borderWidth = f64(record + 92);
        if (borderFlags > 1 || bytes.subarray(record + 85, record + 88).some((value) => value !== 0)) throw new XygWasmError("XYG_WASM_MALFORMED_OUTPUT", "Rust painter label border flags are invalid");
        if (borderFlags) { if (!box || !(Number.isFinite(borderWidth) && borderWidth > 0 && border[3] > 0)) throw new XygWasmError("XYG_WASM_MALFORMED_OUTPUT", "Rust painter label border is invalid"); box.border = {color: rgba(border), width: borderWidth}; }
        else if (border.some((value) => value !== 0) || borderWidth !== 0) throw new XygWasmError("XYG_WASM_MALFORMED_OUTPUT", "Rust painter label border is noncanonical");
      }
      sceneLabels.push({stableId: view.getBigUint64(record, true), x, y, fontSize, color: rgba(bytes.subarray(record + 32, record + 36)), anchor, text: label, ...(box ? {box} : {})});
      textOffset += length;
    }
    if (textOffset !== end) throw new XygWasmError("XYG_WASM_MALFORMED_OUTPUT", "Rust painter label text has trailing bytes");
  }
  nextString += sceneLabelLength;
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
  return { spec: { protocol: PROTOCOL, width, height, padding: [top, width - right, height - bottom, left], title: text[0] || null, x_axis: xAxis, y_axis: yAxis, axes: { x: xAxis, y: yAxis }, traces, annotations, columns, dom: { style: { background: rgba(bytes.subarray(chrome, chrome + 4)), "--chart-bg": rgba(bytes.subarray(chrome + 4, chrome + 8)) }, styles: { title: { color: rgba(bytes.subarray(chrome + 8, chrome + 12)), "font-size": labelSize + 2 }, ...(legend ? { legend_title: { color: legend.style.color, "font-size": legend.title_style["font-size"] }, legend_label: { color: legend.style.color, "font-size": legend.style["font-size"] } } : {}) } }, legend, colorbar, show_legend: legend != null, show_modebar: false, show_tooltip: false, frame_sides: [xAxis.side, yAxis.side], interaction: { drag_action: "none" }, view: { ranges: { x: [left, right], y: [bottom, top] } } }, payload: bytes, sceneLabels };
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
  if (compiled.sceneLabels.length) {
    const layer = document.createElement("div");
    Object.assign(layer.style, {position:"absolute", inset:"0", pointerEvents:"none"});
    layer.dataset.xyChrome = "graph_labels"; layer.setAttribute("role", "list"); layer.setAttribute("aria-label", "Graph labels");
    for (const label of compiled.sceneLabels) {
      const labelType = label.stableId & 0xffff_ff00_0000_0000n;
      const annotation = labelType === 0x5859_0400_0000_0000n || labelType === 0x5859_0600_0000_0000n || labelType === 0x5859_0700_0000_0000n;
      if (label.box) {
        const box = document.createElement("span");
        box.dataset.xySlot = annotation ? "annotation_label_box" : "graph_label_box";
        box.dataset.xyStableId = label.stableId.toString();
        box.setAttribute("aria-hidden", "true");
        Object.assign(box.style, {position:"absolute", left:`${label.box.x}px`, top:`${label.box.y}px`, width:`${label.box.width}px`, height:`${label.box.height}px`, backgroundColor:label.box.fill, ...(label.box.border ? {border:`${label.box.border.width}px solid ${label.box.border.color}`, boxSizing:"border-box"} : {})});
        layer.appendChild(box);
      }
      const item = document.createElement("span");
      item.dataset.xySlot = annotation ? "annotation_label" : "graph_label"; item.dataset.xyStableId = label.stableId.toString(); item.setAttribute("role", annotation ? "note" : "listitem"); item.textContent = label.text;
      const translateX = label.anchor === 0 ? "0" : label.anchor === 1 ? "-50%" : "-100%";
      Object.assign(item.style, {position:"absolute", left:`${label.x}px`, top:`${label.y - label.fontSize}px`, color:label.color, fontSize:`${label.fontSize}px`, lineHeight:`${label.fontSize * 1.2}px`, transform:`translateX(${translateX})`, whiteSpace:label.text.includes("\n") ? "pre" : "nowrap"});
      layer.appendChild(item);
    }
    view.root.appendChild(layer);
  }
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
