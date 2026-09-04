import {
  aggregateWasmBin2d,
  attachStandaloneWasmDensity,
  attachWasmDensity,
  attachWasmTicks,
  ChartView,
  createXygWasmWorker,
  decodeWasmTickBatch,
  frameWasmChart,
  encodeWasmAggregate,
  encodeWasmCose,
  encodeWasmColumns,
  encodeWasmDashboardPlan,
  encodeWasmTickBatch,
  hydrateWasmPainter,
  layoutWasmCose,
  planWasmDashboardResources,
  watchWasmDashboardResourceBudget,
  renderWasmChart,
  renderWasmColumns,
  renderWasmScene,
  encodeWasmSemanticGraph,
  renderWasmSemanticGraph,
  resolveWasmTicks,
  transitionWasmCompound,
  XygWasmError,
  XygWasmTemporalController,
  XygWasmTemporalGraph,
} from "/packages/xy-client/dist/index.js";

/** Encoded Scene version. Keep in lockstep with `scene::SCENE_VERSION`. */
const CANONICAL_SCENE_VERSION = 31;

function directDensityFixture(host, comm = null, multi = false, fullSource = false, colorbar = null) {
  const width = 16, height = 16;
  const grid = new Float32Array(width * height);
  grid[0] = 1;
  const spec = {
    protocol: 12, width: 320, height: 240, title: null,
    x_axis: { id: "x", kind: "linear", label: null, range: [0, 1], side: "bottom" },
    y_axis: { id: "y", kind: "linear", label: null, range: [0, 1], side: "left" },
    axes: {
      x: { id: "x", kind: "linear", label: null, range: [0, 1], side: "bottom" },
      y: { id: "y", kind: "linear", label: null, range: [0, 1], side: "left" },
    },
    traces: [{
      id: 0, kind: "scatter", name: null, style: { opacity: 0.8 }, tier: "density",
      n_points: 4, n_marks: width * height, visible: 4, x_axis: "x", y_axis: "y",
      density: {
        buf: 0, w: width, h: height, max: 1, enc: "f32", colormap: "viridis",
        x_range: [0, 1], y_range: [0, 1], binning: "exact", reduction: "bin2d",
        channels_dropped: false, dropped_channels: [], color: "#3987e5",
      },
    }],
    columns: [{ byte_offset: 0, len: grid.length, dtype: "f32" }],
    backend: "native", show_legend: false,
    wasm_density: { automatic: true },
    view: { ranges: { x: [0, 1], y: [0, 1] } },
    ...(colorbar ? { colorbar } : {}),
  };
  if (fullSource) {
    // Cross the generated 32,768-point stream boundary twice. The source
    // remains in ChartView for the subsequent pan/recovery proof.
    const n = 65_537, x = new Float64Array(n), y = new Float64Array(n);
    for (let i = 0; i < n; i++) { x[i] = (i % 1024) / 1023; y[i] = ((i * 37) % 1024) / 1023; }
    spec.buffer_layout = "split";
    spec.columns = [
      { buf: 0, byte_offset: 0, len: grid.length, dtype: "f32" },
      { buf: 1, byte_offset: 0, len: x.length, dtype: "f64" },
      { buf: 2, byte_offset: 0, len: y.length, dtype: "f64" },
    ];
    spec.wasm_density = { automatic: true, source: {
      kind: "cartesian-count-f64-stream-v1", x: 1, y: 2, trace_id: 0,
      point_count: n, capacity: 8000000, ownership: "retain-host-replay",
    } };
    return new ChartView(host, spec, [new Uint8Array(grid.buffer), new Uint8Array(x.buffer), new Uint8Array(y.buffer)], comm);
  }
  if (multi) {
    spec.axes.x2 = { id: "x2", kind: "linear", label: null, range: [10, 20], side: "top" };
    spec.axes.y2 = { id: "y2", kind: "linear", label: null, range: [100, 200], side: "right" };
    spec.traces.push({
      ...spec.traces[0], id: 1, x_axis: "x2", y_axis: "y2",
      density: { ...spec.traces[0].density, buf: 1, x_range: [10, 20], y_range: [100, 200] },
    });
    spec.columns.push({ byte_offset: grid.byteLength, len: grid.length, dtype: "f32" });
    spec.view = { ranges: { x: [0, 1], y: [0, 1], x2: [10, 20], y2: [100, 200] } };
    const payload = new Uint8Array(grid.byteLength * 2);
    payload.set(new Uint8Array(grid.buffer)); payload.set(new Uint8Array(grid.buffer), grid.byteLength);
    return new ChartView(host, spec, payload, comm);
  }
  return new ChartView(host, spec, new Uint8Array(grid.buffer), comm);
}

const nextTask = () => new Promise((resolve) => setTimeout(resolve, 0));

function dashboardPlanResponse(retained = true) {
  const bytes = new Uint8Array(25), view = new DataView(bytes.buffer);
  bytes.set([88, 89, 68, 79]);
  view.setUint32(4, 1, true);
  view.setUint32(8, 1, true);
  view.setBigUint64(16, retained ? 4n : 0n, true);
  bytes[24] = retained ? 1 : 0;
  return bytes.buffer;
}

function writeDefaultSceneV9Chrome(bytes, view, body) {
  bytes.set([32, 32, 32, 217], body + 8);
  view.setFloat64(body + 16, 12, true);
  for (const offset of [body + 24, body + 112]) {
    bytes.set([0, 1, 1, 0, 0, 0, 0, 0], offset);
    bytes.set([32, 32, 32, 140], offset + 8);
    bytes.set([32, 32, 32, 36], offset + 12);
    bytes.set([32, 32, 32, 140], offset + 16);
    bytes.set([32, 32, 32, 140], offset + 24);
    bytes.set([32, 32, 32, 217], offset + 28);
    [1, 1, 1, 4, 1, 1, 0].forEach((value, index) => {
      view.setFloat64(offset + 32 + index * 8, value, true);
    });
  }
  view.setUint32(body + 212, 0xffffffff, true);
  view.setUint32(body + 220, 0xffffffff, true);
}

function primaryLegend(symbols = [0]) {
  const title = new TextEncoder().encode("Series");
  const labels = symbols.map((symbol) => new TextEncoder().encode(symbols.length === 1 ? "observed" : `symbol-${symbol}`));
  const textLength = labels.reduce((total, label) => total + label.length, title.length);
  const bytes = new Uint8Array(48 + symbols.length * 24 + textLength), view = new DataView(bytes.buffer);
  bytes.set([88, 89, 76, 71]); bytes[4] = 0; view.setUint32(8, symbols.length, true); view.setUint32(12, title.length, true);
  view.setFloat64(16, 13, true); view.setFloat64(24, 15, true);
  bytes.set([126, 34, 206, 255], 32); bytes.set([255, 255, 255, 230], 36); bytes.set([32, 32, 32, 71], 40);
  let textOffset = title.length;
  for (let index = 0; index < symbols.length; index++) {
    const entry = 48 + index * 24, label = labels[index];
    view.setUint32(entry, 0, true); bytes[entry + 4] = 0; bytes[entry + 5] = symbols[index];
    view.setUint32(entry + 8, textOffset, true); view.setUint32(entry + 12, label.length, true);
    bytes.set([37, 99, 235, 255], entry + 16); bytes.set([0, 0, 0, 0], entry + 20); textOffset += label.length;
  }
  let cursor = 48 + symbols.length * 24; bytes.set(title, cursor); cursor += title.length;
  for (const label of labels) { bytes.set(label, cursor); cursor += label.length; }
  return bytes;
}

function canonicalSceneV9({ authored = false, legend = false, legendSymbols = null } = {}) {
  const body = 160 + 16 + 56;
  const ticks = authored ? [0, 1, 0.5, 0, 1] : [];
  const text = authored
    ? ["Authored Cartesian chrome", "Horizontal measure", "Vertical measure"].map((value) => new TextEncoder().encode(value))
    : [new Uint8Array(), new Uint8Array(), new Uint8Array()];
  const textBytes = text.reduce((total, value) => total + value.length, 0);
  const tickLabelFrame = (labels) => {
    const encoded = labels.map((label) => new TextEncoder().encode(label));
    const out = new Uint8Array(12 + encoded.reduce((total, label) => total + 4 + label.length, 0));
    const frame = new DataView(out.buffer); out.set([88, 89, 84, 76]);
    frame.setUint32(4, 1, true); frame.setUint32(8, encoded.length, true); let at = 12;
    for (const label of encoded) { frame.setUint32(at, label.length, true); at += 4; out.set(label, at); at += label.length; }
    return out;
  };
  const xTickLabels = authored ? tickLabelFrame(["zero", "one"]) : new Uint8Array();
  const yTickLabels = authored ? tickLabelFrame(["low", "high"]) : new Uint8Array();
  const hasLegend = legend || legendSymbols != null;
  const legendBytes = hasLegend ? primaryLegend(legendSymbols || [0]) : new Uint8Array();
  const bytes = new Uint8Array(body + 248 + textBytes + xTickLabels.length + yTickLabels.length + ticks.length * 8 + legendBytes.length);
  const view = new DataView(bytes.buffer);
  bytes.set([88, 89, 71, 83], 0); // XYGS
  view.setUint32(4, CANONICAL_SCENE_VERSION, true);
  view.setUint32(8, 160, true);
  view.setUint32(12, 56, true);
  view.setBigUint64(16, 1n, true);
  view.setBigUint64(24, 1n, true);
  const tallLegend = legendSymbols?.length > 1;
  [hasLegend ? 200 : 100, tallLegend ? 500 : hasLegend ? 120 : 80, 10, 10, hasLegend ? 190 : 90, tallLegend ? 490 : hasLegend ? 110 : 70].forEach((value, index) => {
    view.setFloat64(32 + index * 8, value, true);
  });
  view.setBigUint64(80, 1n, true);
  view.setBigUint64(88, 2n, true);
  // Linear axes, mask false, reserved bytes already zero.
  [0, 1, 0, 1, 1, 1].forEach((value, index) => {
    view.setFloat64(112 + index * 8, value, true);
  });
  bytes.set([37, 99, 235, 255, 0, 0, 0, 0], 160);
  view.setFloat64(168, 0, true);
  const record = 176;
  bytes[record] = 0;
  bytes[record + 1] = 1;
  view.setUint32(record + 4, 0, true);
  view.setBigUint64(record + 8, 7n, true);
  view.setFloat64(record + 16, 50, true);
  view.setFloat64(record + 24, 40, true);
  view.setFloat64(record + 32, 0, true);
  view.setFloat64(record + 40, 0, true);
  view.setFloat64(record + 48, 8, true);
  writeDefaultSceneV9Chrome(bytes, view, body);
  view.setUint32(body + 228, legendBytes.length, true);
  if (authored) {
    bytes.set([240, 248, 255, 255], body);
    bytes.set([248, 250, 252, 255], body + 4);
    bytes.set([211, 47, 47, 255], body + 8);
    view.setFloat64(body + 16, 17, true);
    bytes.set([1, 3, 2, 2, 1], body + 24);
    bytes.set([94, 129, 172, 255], body + 24 + 20);
    view.setFloat64(body + 24 + 80, 3, true);
    view.setUint32(body + 212, 2, true);
    view.setUint32(body + 216, 1, true);
    view.setUint32(body + 220, 2, true);
    text.forEach((value, index) => view.setUint32(body + 200 + index * 4, value.length, true));
    view.setUint32(body + 240, xTickLabels.length, true); view.setUint32(body + 244, yTickLabels.length, true);
    let tickOffset = body + 248;
    for (const value of text) {
      bytes.set(value, tickOffset);
      tickOffset += value.length;
    }
    bytes.set(xTickLabels, tickOffset); tickOffset += xTickLabels.length;
    bytes.set(yTickLabels, tickOffset); tickOffset += yTickLabels.length;
    for (const tick of ticks) {
      view.setFloat64(tickOffset, tick, true);
      tickOffset += 8;
    }
    bytes.set(legendBytes, tickOffset);
  } else {
    bytes.set(legendBytes, body + 248);
  }
  return bytes;
}

function primaryAnnotationSceneV10() {
  const recordCount = 5, styleCount = 3;
  const records = 160 + styleCount * 16;
  const body = records + recordCount * 56;
  const bytes = new Uint8Array(body + 248), view = new DataView(bytes.buffer);
  bytes.set([88, 89, 71, 83], 0); // XYGS
  view.setUint32(4, CANONICAL_SCENE_VERSION, true); view.setUint32(8, 160, true); view.setUint32(12, 56, true);
  view.setBigUint64(16, BigInt(recordCount), true); view.setBigUint64(24, BigInt(styleCount), true);
  [100, 80, 10, 10, 90, 70].forEach((value, index) => view.setFloat64(32 + index * 8, value, true));
  view.setBigUint64(80, 1n, true); view.setBigUint64(88, 2n, true);
  [0, 1, 0, 1, 1, 1].forEach((value, index) => view.setFloat64(112 + index * 8, value, true));
  // rule, band, marker styles
  bytes.set([0, 0, 0, 0, 255, 0, 0, 255], 160); view.setFloat64(168, 2, true);
  bytes.set([0, 255, 0, 64, 0, 255, 0, 64], 176); view.setFloat64(184, 0, true);
  bytes.set([0, 0, 255, 255, 255, 255, 255, 255], 192); view.setFloat64(200, 1.5, true);
  const writeRecord = (index, { kind, style, id, annotation, x0, y0, x1 = 0, y1 = 0, diameter = 0, symbol = 0 }) => {
    const offset = records + index * 56;
    bytes[offset] = kind; bytes[offset + 1] = 1; bytes[offset + 2] = symbol; bytes[offset + 3] = annotation;
    view.setUint32(offset + 4, style, true); view.setBigUint64(offset + 8, id, true);
    [x0, y0, x1, y1].forEach((value, coordinate) => view.setFloat64(offset + 16 + coordinate * 8, value, true));
    view.setFloat64(offset + 48, diameter, true);
  };
  const prefix = 0x5859000000000000n;
  writeRecord(0, { kind: 1, style: 0, id: prefix | (1n << 40n), annotation: 1, x0: 30, y0: 10 });
  writeRecord(1, { kind: 1, style: 0, id: prefix | (1n << 40n), annotation: 1, x0: 30, y0: 70 });
  writeRecord(2, { kind: 2, style: 1, id: prefix | (2n << 40n) | 1n, annotation: 2, x0: 40, y0: 10, x1: 50, y1: 70 });
  writeRecord(3, { kind: 0, style: 2, id: prefix | (3n << 40n) | 2n, annotation: 3, x0: 60, y0: 40, diameter: 10 });
  writeRecord(4, { kind: 0, style: 2, id: prefix | (3n << 40n) | 3n, annotation: 3, x0: 70, y0: 50, diameter: 10 });
  writeDefaultSceneV9Chrome(bytes, view, body);
  return bytes;
}

function fragmentedScene(count) {
  const records = 176;
  const body = records + count * 56;
  const bytes = new Uint8Array(body + 248);
  const view = new DataView(bytes.buffer);
  bytes.set([88, 89, 71, 83], 0);
  view.setUint32(4, CANONICAL_SCENE_VERSION, true); view.setUint32(8, 160, true); view.setUint32(12, 56, true);
  view.setBigUint64(16, BigInt(count), true); view.setBigUint64(24, 1n, true);
  [100, 80, 10, 10, 90, 70].forEach((value, index) => view.setFloat64(32 + index * 8, value, true));
  view.setBigUint64(80, 1n, true); view.setBigUint64(88, 2n, true);
  [0, 1, 0, 1, 1, 1].forEach((value, index) => view.setFloat64(112 + index * 8, value, true));
  bytes.set([37, 99, 235, 255, 0, 0, 0, 0], 160); view.setFloat64(168, 0, true);
  for (let index = 0; index < count; index++) {
    const record = records + index * 56;
    bytes[record] = 0; bytes[record + 1] = 1; bytes[record + 2] = index % 2;
    view.setUint32(record + 4, 0, true); view.setBigUint64(record + 8, 7n, true);
    view.setFloat64(record + 16, 50, true); view.setFloat64(record + 24, 40, true);
    view.setFloat64(record + 48, 8, true);
  }
  writeDefaultSceneV9Chrome(bytes, view, body);
  return bytes;
}

function u32(value) {
  const bytes = [];
  do {
    let byte = value & 0x7f;
    value >>>= 7;
    if (value) byte |= 0x80;
    bytes.push(byte);
  } while (value);
  return bytes;
}

function i32(value) {
  const bytes = [];
  let remaining = value | 0;
  while (true) {
    let byte = remaining & 0x7f;
    remaining >>= 7;
    const done = (remaining === 0 && (byte & 0x40) === 0)
      || (remaining === -1 && (byte & 0x40) !== 0);
    if (!done) byte |= 0x80;
    bytes.push(byte);
    if (done) return bytes;
  }
}

function section(id, payload) {
  return [id, ...u32(payload.length), ...payload];
}

function utf8(value) {
  const bytes = [...new TextEncoder().encode(value)];
  return [...u32(bytes.length), ...bytes];
}

async function fixtureModule({
  trap = false,
  disposeTrap = false,
  highBitDiagnostics = false,
  aggregateStepTrap = false,
  aggregateOutputOutOfRange = false,
  cancelTrap = false,
  graphStepTrap = false,
  paletteVersion = 1,
} = {}) {
  const names = [
    "xyg_wasm_abi_version",
    "xyg_wasm_scene_version",
    "xyg_wasm_max_arena_bytes",
    "xyg_wasm_instance_new",
    "xyg_wasm_instance_dispose",
    "xyg_wasm_arena_resize",
    "xyg_wasm_arena_ptr",
    "xyg_wasm_arena_len",
    "xyg_wasm_cancel",
    "xyg_wasm_scene_validate",
    "xyg_wasm_scene_prepare",
    "xyg_wasm_scene_prepare_annotations",
    "xyg_wasm_scene_compile",
    "xyg_wasm_scene_compile_prepare",
    "xyg_wasm_aggregate_bin2d",
    "xyg_wasm_aggregate_step",
    "xyg_wasm_aggregate_stream_begin",
    "xyg_wasm_aggregate_stream_push",
    "xyg_wasm_aggregate_stream_finish",
    "xyg_wasm_graph_begin",
    "xyg_wasm_graph_step",
    "xyg_wasm_output_ptr",
    "xyg_wasm_output_len",
    "xyg_wasm_last_error_ptr",
    "xyg_wasm_last_error_len",
    "xyg_wasm_copy_count",
    "xyg_wasm_copy_bytes_lo",
    "xyg_wasm_copy_bytes_hi",
    "xyg_wasm_arena_high_water",
    "xyg_wasm_last_scene_records",
    "xyg_wasm_last_scene_styles",
    "xyg_wasm_temporal_execute",
    "xyg_wasm_temporal_graph_execute",
    "xyg_wasm_scene_compile_begin",
    "xyg_wasm_scene_compile_step",
    "xyg_wasm_scene_compile_records_processed",
    "xyg_wasm_scene_compile_phase",
    "xyg_wasm_dashboard_plan",
    "xyg_wasm_compound_transition",
    "xyg_wasm_ticks_resolve",
    "xyg_wasm_density_first_paint_plan",
    "xyg_wasm_default_palette_version",
    "xyg_wasm_default_palette_rows",
    "xyg_wasm_default_palette_rgba8",
  ];
  const arities = [0, 1, 2, 3, 4, 5];
  const types = [
    ...u32(arities.length),
    ...arities.flatMap((arity) => [
      0x60,
      ...u32(arity),
      ...Array(arity).fill(0x7f),
      1,
      0x7f,
    ]),
  ];
  const functionTypes = [
    0, 0, 0, 1, 1, 2, 1, 1, 2, 4, 4, 4, 4, 4, 4, 3, 4, 4, 2, 5, 4, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 3, 3, 5, 3, 1, 1, 4, 3, 3, 4, 0, 0, 1,
  ];
  const functions = [...u32(functionTypes.length), ...functionTypes.flatMap(u32)];
  const memory = [1, 0, 1]; // one memory, no maximum, one 64 KiB page
  const exports = [
    ...u32(names.length + 1),
    ...utf8("memory"), 2, 0,
    ...names.flatMap((name, index) => [...utf8(name), 0, ...u32(index)]),
  ];
  const highBit = 0x80000000;
  const values = [
    25, CANONICAL_SCENE_VERSION, 64 * 1024 * 1024, 1, 0, 0, 1024, 0, 0, 0, 0, 0, 0, 0,
    aggregateStepTrap || aggregateOutputOutOfRange || cancelTrap ? 8 : 0,
    cancelTrap ? 8 : 0,
    0, 0, 0,
    0, 0,
    aggregateOutputOutOfRange ? 65520 : 0,
    aggregateOutputOutOfRange ? 32 : 0,
    0, 0,
    highBitDiagnostics ? highBit : 0,
    highBitDiagnostics ? highBit : 0,
    highBitDiagnostics ? 1 : 0,
    0, 0, 0, 0, 8, 0, 0, 0, 0, 0, 0, 0, 0, paletteVersion, 8, 0,
  ];
  if (names.length !== functionTypes.length || names.length !== values.length) {
    throw new Error("fake WASM export tables are misaligned");
  }
  const bodies = names.map((_, index) => {
    const instructions = (trap && index === 9) || (disposeTrap && index === 4)
      || (cancelTrap && index === 8)
      || (aggregateStepTrap && index === 14)
      || (graphStepTrap && index === 16)
      ? [0x00, 0x0b] // unreachable; end
      : [0x41, ...i32(values[index] ?? 0), 0x0b];
    const body = [0, ...instructions]; // no local declarations
    return [...u32(body.length), ...body];
  });
  const code = [...u32(bodies.length), ...bodies.flat()];
  return WebAssembly.compile(new Uint8Array([
    0, 97, 115, 109, 1, 0, 0, 0,
    ...section(1, types),
    ...section(3, functions),
    ...section(5, memory),
    ...section(7, exports),
    ...section(10, code),
  ]));
}

async function rejected(promise, code, status = null) {
  try {
    await promise;
  } catch (error) {
    if (!(error instanceof XygWasmError)) throw error;
    if (error.code !== code) throw new Error(`wanted ${code}, got ${error.code}: ${error.message}`);
    if (status !== null && error.status !== status) {
      throw new Error(`wanted status ${status}, got ${error.status}`);
    }
    return error;
  }
  throw new Error(`expected ${code} rejection`);
}

async function rejectedSuperseded(promise) {
  try {
    await promise;
  } catch (error) {
    if (!(error instanceof XygWasmError)) throw error;
    const valid = (error.code === "XYG_WASM_CANCELLED" && error.status === 6)
      || (error.code === "XYG_WASM_STALE_SEQUENCE" && error.status === 7);
    if (!valid) throw new Error(`wanted cancelled or stale supersession, got ${error.code}: ${error.message}`);
    return error;
  }
  throw new Error("expected superseded request rejection");
}

function rawWorkerHarness() {
  const worker = new Worker("/packages/xy-client/dist/wasm-worker.js", { type: "module" });
  const pending = new Map();
  const messages = [];
  worker.onmessage = (event) => {
    messages.push(event.data);
    const entry = pending.get(event.data?.requestId);
    if (entry) {
      clearTimeout(entry.timeout);
      entry.resolve(event.data);
    }
    pending.delete(event.data?.requestId);
  };
  const failPending = (cause) => {
    for (const entry of pending.values()) {
      clearTimeout(entry.timeout);
      entry.reject(cause);
    }
    pending.clear();
  };
  worker.onerror = (event) => failPending(new Error(event.message || "raw worker failed"));
  worker.onmessageerror = () => failPending(new Error("raw worker returned an unreadable message"));
  return {
    worker,
    messages,
    request(message) {
      const response = new Promise((resolve, reject) => {
        const timeout = setTimeout(() => {
          pending.delete(message.requestId);
          reject(new Error(`raw worker request ${message.requestId} timed out`));
        }, 2_000);
        pending.set(message.requestId, { resolve, reject, timeout });
      });
      worker.postMessage(message);
      return response;
    },
  };
}

function rawInit(requestId, source) {
  return {
    type: "init",
    requestId,
    source,
    maxArenaBytes: 1024,
    expectedAbiVersion: 25,
    expectedSceneVersion: CANONICAL_SCENE_VERSION,
  };
}

let foundationStage = "startup";
async function run() {
  foundationStage = "failure diagnostics snapshot contract";
  const diagnosticInput = {
    abiVersion: 11, sceneVersion: 11, defaultPaletteVersion: 1,
    defaultPaletteRows: 8, defaultPaletteFirstRgba8: 0xffe58739,
    arenaBytes: 8, arenaHighWaterBytes: 16,
    memoryBytes: 32, memoryHighWaterBytes: 64, copyCount: 1, copyBytesLo: 8,
    copyBytesHi: 0, records: 2, styles: 1,
  };
  const diagnosticError = new XygWasmError("TEST", "test", 2, diagnosticInput);
  diagnosticInput.copyCount = 99;
  if (diagnosticError.diagnostics?.copyCount !== 1
      || !Object.isFrozen(diagnosticError.diagnostics)
      || Reflect.set(diagnosticError.diagnostics, "copyCount", 7)) {
    throw new Error("failure diagnostics are not an immutable cloned snapshot");
  }
  for (const invalid of [[], { ...diagnosticInput, records: Number.NaN }, { abiVersion: 11 },
    { ...diagnosticInput, styles: "1" }]) {
    if (new XygWasmError("TEST", "test", 2, invalid).diagnostics !== null) {
      throw new Error(`invalid failure diagnostics were accepted: ${JSON.stringify(invalid)}`);
    }
  }

  const sharedFixture = await fetch("/tests/fixtures/figure_scene_v3.json").then((response) => response.json());
  const xytsFixture = await fetch("/tests/fixtures/xyts_cross_host.json").then((response) => response.json());
  const graphForgeSemanticFixture = await fetch("/tests/fixtures/graphforge/semantic_compound.json").then((response) => response.json());
  const wasmResponse = await fetch("/packages/xy-client/dist/xyg-wasm.wasm");
  const wasmBytes = await wasmResponse.arrayBuffer();
  const wasmModule = await WebAssembly.compile(wasmBytes);

  foundationStage = "Rust-owned massive density first-paint policy";
  const policyInstance = await WebAssembly.instantiate(wasmModule);
  const policyExport = policyInstance.exports.xyg_wasm_density_first_paint_plan;
  if (typeof policyExport !== "function" || policyExport.length !== 4) {
    throw new Error("massive density policy export is missing or has the wrong signature");
  }
  const densityPolicy = [1_000_000, 100_000_000].map((pointCount) => {
    const packed = policyExport(
      pointCount >>> 0,
      Math.floor(pointCount / 0x1_0000_0000) >>> 0,
      512,
      384,
    ) >>> 0;
    return {
      point_count: pointCount,
      tier: ["direct", "decimated", "density"][packed & 3] ?? "invalid",
      n_marks: packed >>> 8,
      pyramid_eligible: (packed & 4) !== 0,
      wasm_eligible: (packed & 8) !== 0,
      attach_sample: (packed & 16) !== 0,
      ship_wasm_source: (packed & 32) !== 0,
      canonical_f64_bytes: (packed & 32) !== 0 ? pointCount * 16 : 0,
      total_bytes_max: (packed >>> 8) + 2 * 4 * (8192 + 512),
    };
  });
  const [millionPolicy, hundredMillionPolicy] = densityPolicy;
  if (millionPolicy.tier !== "density" || millionPolicy.n_marks !== 512 * 384
      || millionPolicy.pyramid_eligible || !millionPolicy.wasm_eligible
      || !millionPolicy.attach_sample || millionPolicy.ship_wasm_source
      || millionPolicy.canonical_f64_bytes !== 0 || millionPolicy.total_bytes_max !== 266240
      || hundredMillionPolicy.tier !== "density" || hundredMillionPolicy.n_marks !== 512 * 384
      || !hundredMillionPolicy.pyramid_eligible || hundredMillionPolicy.wasm_eligible
      || !hundredMillionPolicy.attach_sample || hundredMillionPolicy.ship_wasm_source
      || hundredMillionPolicy.canonical_f64_bytes !== 0
      || hundredMillionPolicy.total_bytes_max !== 266240) {
    throw new Error(`massive density policy drifted: ${JSON.stringify(densityPolicy)}`);
  }

  foundationStage = "Rust-owned viewport tick codec and Worker lifecycle";
  const tickWorker = createXygWasmWorker({
    workerUrl: "/packages/xy-client/dist/wasm-worker.js",
    wasm: wasmModule,
    maxArenaBytes: 1024 * 1024,
  });
  await tickWorker.ready;
  const automaticAxes = [
    { axisId: 101, revision: 9, family: "linear", provenance: "automatic", lo: 0, hi: 1000, target: 6, format: "$,.1f" },
    { axisId: 102, revision: 9, family: "log", provenance: "automatic", lo: 0.1, hi: 100, target: 6, maskNonpositive: true },
    { axisId: 103, revision: 9, family: "symlog", provenance: "automatic", lo: -10, hi: 10, target: 7, constant: 1 },
    { axisId: 104, revision: 9, family: "category", provenance: "automatic", lo: 0, hi: 2, target: 3, categories: ["alpha", "beta", "gamma"] },
    { axisId: 105, revision: 9, family: "angular_radians", provenance: "automatic", lo: 0, hi: Math.PI * 2, target: 6 },
    { axisId: 106, revision: 9, family: "angular_degrees", provenance: "automatic", lo: 0, hi: 360, target: 6 },
    { axisId: 107, revision: 9, family: "utc_time", provenance: "automatic", lo: 0, hi: 7_200_000, target: 6, format: "%H:%M" },
  ];
  for (const axis of automaticAxes) {
    foundationStage = `Rust-owned ${axis.family} viewport ticks`;
    const sequence = tickWorker.allocateTickSequence();
    const single = await resolveWasmTicks(tickWorker, { sequence, axes: [axis] }).result;
    if (single.sequence !== sequence || single.axes[0]?.axisId !== axis.axisId) {
      throw new Error(`${axis.family} tick identity did not round-trip`);
    }
  }
  foundationStage = "atomic seven-family Rust-owned viewport ticks";
  const automaticSequence = tickWorker.allocateTickSequence();
  const automatic = await resolveWasmTicks(tickWorker, {
    sequence: automaticSequence,
    axes: automaticAxes,
  }).result;
  if (automatic.sequence !== automaticSequence || automatic.axes.length !== automaticAxes.length
      || !Object.isFrozen(automatic) || !Object.isFrozen(automatic.axes)) {
    throw new Error("atomic seven-family tick result lost its sequence or immutable batch shape");
  }
  for (const [index, axis] of automatic.axes.entries()) {
    if (axis.axisId !== automaticAxes[index].axisId || axis.revision !== 9
        || axis.provenance !== "automatic" || axis.ticks.length === 0
        || axis.labeledValues.length !== axis.labels.length
        || axis.ticks.some((value) => !Number.isFinite(value))
        || !Object.isFrozen(axis) || !Object.isFrozen(axis.ticks)
        || !Object.isFrozen(axis.labeledValues) || !Object.isFrozen(axis.labels)) {
      throw new Error(`automatic tick family ${automaticAxes[index].family} returned a malformed result`);
    }
  }
  if (!automatic.axes[0].labels.every((label) => label.startsWith("$"))
      || automatic.axes[3].labels.join("|") !== "alpha|beta|gamma"
      || !automatic.axes[5].labels.some((label) => label.includes("°"))
      || !automatic.axes[6].labels.every((label) => label.includes(":"))) {
    throw new Error(`Rust-owned tick formatting drifted: ${JSON.stringify(automatic.axes.map((axis) => axis.labels))}`);
  }

  const authoredSequence = tickWorker.allocateTickSequence();
  const authoredTicks = await resolveWasmTicks(tickWorker, {
    sequence: authoredSequence,
    axes: [
      {
        axisId: 201, revision: 3, family: "linear", provenance: "authored_values",
        lo: 0, hi: 2, target: 5, authoredValues: [-1, 0, 1, 3],
        authoredLabels: ["minus", "zero", "one", "three"], format: "$,.1f",
      },
      { axisId: 202, revision: 4, family: "linear", provenance: "authored_empty", lo: 0, hi: 1, target: 5 },
    ],
  }).result;
  if (authoredTicks.axes[0].provenance !== "authored_values"
      || authoredTicks.axes[0].ticks.join(",") !== "0,1"
      || authoredTicks.axes[0].labels.join("|") !== "zero|one"
      || authoredTicks.axes[1].provenance !== "authored_empty"
      || authoredTicks.axes[1].ticks.length !== 0 || authoredTicks.axes[1].labels.length !== 0) {
    throw new Error(`authored tick provenance drifted: ${JSON.stringify(authoredTicks.axes)}`);
  }

  const expectTickCodecFailure = (callback, constructor, label) => {
    try { callback(); }
    catch (error) {
      if (error instanceof constructor) return;
      throw new Error(`${label} raised ${error?.constructor?.name ?? typeof error}, wanted ${constructor.name}`);
    }
    throw new Error(`${label} unexpectedly succeeded`);
  };
  expectTickCodecFailure(() => encodeWasmTickBatch({ sequence: 1, axes: [] }), RangeError, "empty tick batch");
  expectTickCodecFailure(() => encodeWasmTickBatch({
    sequence: 1,
    axes: [automaticAxes[0], { ...automaticAxes[1], axisId: automaticAxes[0].axisId }],
  }), TypeError, "duplicate tick axis id");
  expectTickCodecFailure(() => encodeWasmTickBatch({
    sequence: 1,
    axes: [{ ...automaticAxes[0], format: "x".repeat(257) }],
  }), RangeError, "oversized tick format");
  expectTickCodecFailure(() => encodeWasmTickBatch({
    sequence: 1,
    axes: [{ ...automaticAxes[0], provenance: "authored_values", authoredValues: [0, 1], authoredLabels: ["zero"] }],
  }), RangeError, "authored label cardinality mismatch");
  expectTickCodecFailure(() => decodeWasmTickBatch(new ArrayBuffer(31)), TypeError, "truncated tick output");
  expectTickCodecFailure(() => tickWorker.resolveTicks(
    new ArrayBuffer(1024 * 1024 + 1),
    { sequence: 1 },
  ), TypeError, "over-budget raw tick request");

  const rawSequence = tickWorker.allocateTickSequence();
  const rawOutput = await tickWorker.resolveTicks(encodeWasmTickBatch({
    sequence: rawSequence,
    axes: [automaticAxes[0]],
  }), { sequence: rawSequence }).result;
  const decodedRaw = decodeWasmTickBatch(rawOutput);
  if (decodedRaw.sequence !== rawSequence || decodedRaw.axes[0].axisId !== automaticAxes[0].axisId) {
    throw new Error("raw tick Worker seam did not round-trip through the strict decoder");
  }
  const malformedOutput = rawOutput.slice(0);
  new Uint8Array(malformedOutput)[0] = 0;
  expectTickCodecFailure(() => decodeWasmTickBatch(malformedOutput), TypeError, "malformed tick output magic");

  const malformedSequence = tickWorker.allocateTickSequence();
  const malformedRequest = encodeWasmTickBatch({ sequence: malformedSequence, axes: [automaticAxes[0]] });
  new Uint8Array(malformedRequest)[0] = 0;
  await rejected(
    tickWorker.resolveTicks(malformedRequest, { sequence: malformedSequence }).result,
    "XYG_WASM_INVALID_ARGUMENT",
    2,
  );

  foundationStage = "independent tick cancellation lane";
  const cancelledSequence = tickWorker.allocateTickSequence();
  const cancelledTick = resolveWasmTicks(tickWorker, {
    sequence: cancelledSequence,
    axes: automaticAxes,
  });
  cancelledTick.cancel();
  await rejected(cancelledTick.result, "XYG_WASM_CANCELLED", 6);
  await tickWorker.validateScene(canonicalSceneV9(), { sequence: 1, transfer: false }).result;
  const afterCancelSequence = tickWorker.allocateTickSequence();
  const afterCancel = await resolveWasmTicks(tickWorker, {
    sequence: afterCancelSequence,
    axes: [automaticAxes[0]],
  }).result;
  if (afterCancel.sequence !== afterCancelSequence) {
    throw new Error("tick cancellation poisoned its independent sequence lane");
  }

  foundationStage = "tick Worker disposal";
  await tickWorker.dispose();
  try {
    tickWorker.allocateTickSequence();
    throw new Error("disposed tick Worker allocated another sequence");
  } catch (error) {
    if (!(error instanceof XygWasmError) || error.code !== "XYG_WASM_DISPOSED") throw error;
  }
  try {
    resolveWasmTicks(tickWorker, { sequence: 0xffff_ffff, axes: [automaticAxes[0]] });
    throw new Error("disposed tick Worker accepted another batch");
  } catch (error) {
    if (!(error instanceof XygWasmError) || error.code !== "XYG_WASM_DISPOSED") throw error;
  }

  foundationStage = "primary Cartesian ChartView ticks use Rust/WASM";
  const chartTickHost = document.createElement("div");
  chartTickHost.style.cssText = "width:320px;height:240px";
  document.body.append(chartTickHost);
  const chartTickView = directDensityFixture(chartTickHost);
  Object.assign(chartTickView.axes.x, {
    scale: "log", nonpositive: "mask", range: [0.1, 100], format: "$,.1f",
  });
  Object.assign(chartTickView.axes.y, {
    scale: "symlog", constant: 1, range: [-10, 10],
  });
  chartTickView.view0 = chartTickView._copyView({
    ranges: { x: [0.1, 100], y: [-10, 10] },
  });
  chartTickView.view = chartTickView._copyView(chartTickView.view0);
  const chartTickWorker = createXygWasmWorker({
    workerUrl: "/packages/xy-client/dist/wasm-worker.js",
    wasm: wasmModule,
    maxArenaBytes: 1024 * 1024,
  });
  const chartTickHandle = await attachWasmTicks(chartTickView, {
    worker: chartTickWorker,
    workerOwnership: "own",
  });
  await new Promise((resolve) => requestAnimationFrame(() => resolve()));
  const chartTickDiagnostics = chartTickHandle.diagnostics();
  const chartX = chartTickView._axisTicks("x", 6);
  const chartY = chartTickView._axisTicks("y", 6);
  const chartTickLabels = [...chartTickView.root.querySelectorAll(
    '[data-xy-label-kind="tick"]',
  )].map((node) => node.textContent);
  if (chartX.source !== "wasm" || chartY.source !== "wasm"
      || chartTickDiagnostics?.axisIds.join(",") !== "x,y"
      || !chartX.ticks.length || !chartY.ticks.length
      || !chartTickLabels.some((label) => label?.startsWith("$"))) {
    throw new Error(`ChartView did not consume Rust log/symlog ticks: ${JSON.stringify({
      chartTickDiagnostics,
      xSource: chartX.source,
      ySource: chartY.source,
      chartTickLabels,
    })}`);
  }
  await chartTickHandle.dispose();
  chartTickView.destroy();
  await nextTask();
  if (chartTickView._wasmTicks !== null) {
    throw new Error("destroyed ChartView retained its owned WASM tick attachment");
  }
  chartTickHost.remove();

  foundationStage = "primary Cartesian ChartView category and UTC-time ticks use Rust/WASM";
  const familyTickHost = document.createElement("div");
  familyTickHost.style.cssText = "width:320px;height:240px";
  document.body.append(familyTickHost);
  const familyTickView = directDensityFixture(familyTickHost);
  Object.assign(familyTickView.axes.x, {
    kind: "category", categories: ["alpha", "beta", "gamma"], range: [0, 2],
  });
  Object.assign(familyTickView.axes.y, {
    kind: "time", range: [0, 7_200_000], format: "%H:%M",
  });
  familyTickView.view0 = familyTickView._copyView({
    ranges: { x: [0, 2], y: [0, 7_200_000] },
  });
  familyTickView.view = familyTickView._copyView(familyTickView.view0);
  const familyTickWorker = createXygWasmWorker({
    workerUrl: "/packages/xy-client/dist/wasm-worker.js",
    wasm: wasmModule,
    maxArenaBytes: 1024 * 1024,
  });
  const familyTickHandle = await attachWasmTicks(familyTickView, {
    worker: familyTickWorker,
    workerOwnership: "own",
  });
  await new Promise((resolve) => requestAnimationFrame(() => resolve()));
  const familyX = familyTickView._axisTicks("x", 3);
  const familyY = familyTickView._axisTicks("y", 6);
  const familyTickLabels = [...familyTickView.root.querySelectorAll(
    '[data-xy-label-kind="tick"]',
  )].map((node) => node.textContent);
  const familyXLabel = familyTickView._axisTickText(familyTickView.axes.x, 0, familyX.step);
  const familyYLabel = familyTickView._axisTickText(
    familyTickView.axes.y, familyY.ticks[0], familyY.step,
  );
  if (familyX.source !== "wasm" || familyY.source !== "wasm"
      || familyTickHandle.diagnostics()?.axisIds.join(",") !== "x,y"
      || familyX.ticks.join(",") !== "0,1,2"
      || familyXLabel !== "alpha"
      || familyTickHandle.label("x", 1) !== "beta"
      || !familyY.ticks.length
      || !/^\d{2}:\d{2}$/.test(familyYLabel || "")
      || !familyTickLabels.includes("alpha")
      || !familyTickLabels.some((label) => /^\d{2}:\d{2}$/.test(label || ""))) {
    throw new Error(`ChartView did not consume Rust category/UTC-time ticks: ${JSON.stringify({
      diagnostics: familyTickHandle.diagnostics(),
      familyX,
      familyY,
      familyXLabel,
      familyYLabel,
      familyTickLabels,
    })}`);
  }
  await familyTickHandle.dispose();
  familyTickView.destroy();
  familyTickHost.remove();

  foundationStage = "primary Cartesian ChartView authored and authored-empty ticks use Rust/WASM";
  const authoredTickHost = document.createElement("div");
  authoredTickHost.style.cssText = "width:320px;height:240px";
  document.body.append(authoredTickHost);
  const authoredTickView = directDensityFixture(authoredTickHost);
  Object.assign(authoredTickView.axes.x, {
    tick_values: [-1, 0, 0.5, 1, 3],
    tick_labels: ["minus", "zero", "half", "one", "three"],
    range: [0, 1],
    format: "$,.1f",
  });
  Object.assign(authoredTickView.axes.y, {
    tick_values: [],
    range: [0, 1],
  });
  authoredTickView.view0 = authoredTickView._copyView({ ranges: { x: [0, 1], y: [0, 1] } });
  authoredTickView.view = authoredTickView._copyView(authoredTickView.view0);
  const authoredTickWorker = createXygWasmWorker({
    workerUrl: "/packages/xy-client/dist/wasm-worker.js",
    wasm: wasmModule,
    maxArenaBytes: 1024 * 1024,
  });
  const authoredTickHandle = await attachWasmTicks(authoredTickView, {
    worker: authoredTickWorker,
    workerOwnership: "own",
  });
  await new Promise((resolve) => requestAnimationFrame(() => resolve()));
  const authoredX = authoredTickView._axisTicks("x", 6);
  const authoredY = authoredTickView._axisTicks("y", 6);
  const authoredXLabel = authoredTickView._axisTickText(authoredTickView.axes.x, 0, authoredX.step);
  const authoredTickLabels = [...authoredTickView.root.querySelectorAll(
    '[data-xy-label-kind="tick"]',
  )].map((node) => node.textContent);
  if (authoredX.source !== "wasm" || authoredY.source !== "wasm"
      || !authoredTickHandle.covers("x") || !authoredTickHandle.covers("y")
      || authoredTickHandle.diagnostics()?.axisIds.join(",") !== "x,y"
      || authoredX.ticks.join(",") !== "0,0.5,1"
      || authoredY.ticks.length !== 0
      || authoredXLabel !== "zero"
      || authoredTickHandle.label("x", 0.5) !== "half"
      || authoredTickHandle.label("x", 1) !== "one"
      || authoredTickHandle.label("y", 0) !== ""
      || !authoredTickLabels.includes("zero")
      || !authoredTickLabels.includes("half")
      || authoredTickLabels.includes("minus")
      || authoredTickLabels.includes("three")
      || authoredTickLabels.includes("$0.0")) {
    throw new Error(`ChartView did not consume Rust authored/authored-empty ticks: ${JSON.stringify({
      diagnostics: authoredTickHandle.diagnostics(),
      authoredX,
      authoredY,
      authoredXLabel,
      authoredTickLabels,
    })}`);
  }
  await authoredTickHandle.dispose();
  authoredTickView.destroy();
  authoredTickHost.remove();

  foundationStage = "authored ChartView ticks on category and UTC-time axes use Rust/WASM";
  const authoredFamilyHost = document.createElement("div");
  authoredFamilyHost.style.cssText = "width:320px;height:240px";
  document.body.append(authoredFamilyHost);
  const authoredFamilyView = directDensityFixture(authoredFamilyHost);
  Object.assign(authoredFamilyView.axes.x, {
    kind: "category",
    categories: ["alpha", "beta", "gamma"],
    tick_values: [0, 2],
    range: [0, 2],
  });
  Object.assign(authoredFamilyView.axes.y, {
    kind: "time",
    tick_values: [0, 3_600_000],
    range: [0, 7_200_000],
    format: "%H:%M",
  });
  authoredFamilyView.view0 = authoredFamilyView._copyView({
    ranges: { x: [0, 2], y: [0, 7_200_000] },
  });
  authoredFamilyView.view = authoredFamilyView._copyView(authoredFamilyView.view0);
  const authoredFamilyWorker = createXygWasmWorker({
    workerUrl: "/packages/xy-client/dist/wasm-worker.js",
    wasm: wasmModule,
    maxArenaBytes: 1024 * 1024,
  });
  const authoredFamilyHandle = await attachWasmTicks(authoredFamilyView, {
    worker: authoredFamilyWorker,
    workerOwnership: "own",
  });
  await new Promise((resolve) => requestAnimationFrame(() => resolve()));
  const authoredFamilyX = authoredFamilyView._axisTicks("x", 3);
  const authoredFamilyY = authoredFamilyView._axisTicks("y", 6);
  const authoredFamilyXLabel = authoredFamilyView._axisTickText(
    authoredFamilyView.axes.x, 0, authoredFamilyX.step,
  );
  const authoredFamilyYLabel = authoredFamilyView._axisTickText(
    authoredFamilyView.axes.y, 0, authoredFamilyY.step,
  );
  if (authoredFamilyX.source !== "wasm" || authoredFamilyY.source !== "wasm"
      || authoredFamilyHandle.diagnostics()?.axisIds.join(",") !== "x,y"
      || authoredFamilyX.ticks.join(",") !== "0,2"
      || authoredFamilyXLabel !== "alpha"
      || authoredFamilyHandle.label("x", 2) !== "gamma"
      || authoredFamilyY.ticks.join(",") !== "0,3600000"
      || !/^\d{2}:\d{2}$/.test(authoredFamilyYLabel || "")) {
    throw new Error(`ChartView did not consume Rust authored category/UTC-time ticks: ${JSON.stringify({
      diagnostics: authoredFamilyHandle.diagnostics(),
      authoredFamilyX,
      authoredFamilyY,
      authoredFamilyXLabel,
      authoredFamilyYLabel,
    })}`);
  }
  await authoredFamilyHandle.dispose();
  authoredFamilyView.destroy();
  authoredFamilyHost.remove();

  foundationStage = "authored provenance switch after attach waits for a matching Rust cache";
  const authoredSwitchHost = document.createElement("div");
  authoredSwitchHost.style.cssText = "width:320px;height:240px";
  document.body.append(authoredSwitchHost);
  const authoredSwitchView = directDensityFixture(authoredSwitchHost);
  const authoredSwitchWorker = createXygWasmWorker({
    workerUrl: "/packages/xy-client/dist/wasm-worker.js",
    wasm: wasmModule,
    maxArenaBytes: 1024 * 1024,
  });
  const authoredSwitchHandle = await attachWasmTicks(authoredSwitchView, {
    worker: authoredSwitchWorker,
    workerOwnership: "own",
  });
  const automaticSwitchTicks = authoredSwitchView._axisTicks("x", 6);
  authoredSwitchView.axes.x.tick_values = [0.25, 0.75];
  authoredSwitchView.axes.x.tick_labels = ["quarter", "three-quarters"];
  const pendingAuthoredTicks = authoredSwitchView._axisTicks("x", 6);
  const pendingAuthoredLabel = authoredSwitchView._axisTickText(
    authoredSwitchView.axes.x, 0.25, pendingAuthoredTicks.step,
  );
  if (automaticSwitchTicks.source !== "wasm" || !authoredSwitchHandle.eligible("x")
      || authoredSwitchHandle.covers("x") || pendingAuthoredTicks.source === "wasm"
      || pendingAuthoredTicks.ticks.join(",") !== "0.25,0.75"
      || pendingAuthoredLabel !== "quarter") {
    throw new Error(`authored provenance switch reused a stale WASM cache: ${JSON.stringify({
      eligible: authoredSwitchHandle.eligible("x"),
      covers: authoredSwitchHandle.covers("x"),
      automaticSwitchTicks,
      pendingAuthoredTicks,
      pendingAuthoredLabel,
    })}`);
  }
  authoredSwitchHandle.schedule();
  for (let attempt = 0; attempt < 100 && !authoredSwitchHandle.covers("x"); attempt++) {
    await nextTask();
  }
  const admittedAuthoredTicks = authoredSwitchView._axisTicks("x", 6);
  if (!authoredSwitchHandle.covers("x") || admittedAuthoredTicks.source !== "wasm"
      || admittedAuthoredTicks.ticks.join(",") !== "0.25,0.75"
      || authoredSwitchHandle.label("x", 0.25) !== "quarter"
      || authoredSwitchHandle.label("x", 0.75) !== "three-quarters") {
    throw new Error(`authored provenance switch did not admit a matching cache: ${JSON.stringify({
      covers: authoredSwitchHandle.covers("x"),
      admittedAuthoredTicks,
      labels: [authoredSwitchHandle.label("x", 0.25), authoredSwitchHandle.label("x", 0.75)],
    })}`);
  }
  authoredSwitchView.axes.x.tick_values = [];
  delete authoredSwitchView.axes.x.tick_labels;
  const pendingEmptyTicks = authoredSwitchView._axisTicks("x", 6);
  if (authoredSwitchHandle.covers("x") || pendingEmptyTicks.source === "wasm"
      || pendingEmptyTicks.ticks.length !== 0) {
    throw new Error(`authored-empty switch stayed on a stale WASM cache: ${JSON.stringify({
      covers: authoredSwitchHandle.covers("x"),
      pendingEmptyTicks,
    })}`);
  }
  authoredSwitchHandle.schedule();
  for (let attempt = 0; attempt < 100 && !authoredSwitchHandle.covers("x"); attempt++) {
    await nextTask();
  }
  const admittedEmptyTicks = authoredSwitchView._axisTicks("x", 6);
  if (!authoredSwitchHandle.covers("x") || admittedEmptyTicks.source !== "wasm"
      || admittedEmptyTicks.ticks.length !== 0
      || authoredSwitchHandle.label("x", 0.25) !== "") {
    throw new Error(`authored-empty switch did not admit a matching empty cache: ${JSON.stringify({
      covers: authoredSwitchHandle.covers("x"),
      admittedEmptyTicks,
    })}`);
  }
  delete authoredSwitchView.axes.x.tick_values;
  const pendingAutomaticTicks = authoredSwitchView._axisTicks("x", 6);
  if (authoredSwitchHandle.covers("x") || pendingAutomaticTicks.source === "wasm"
      || !pendingAutomaticTicks.ticks.length) {
    throw new Error(`automatic provenance restore stayed on authored-empty WASM: ${JSON.stringify({
      covers: authoredSwitchHandle.covers("x"),
      pendingAutomaticTicks,
    })}`);
  }
  authoredSwitchHandle.schedule();
  for (let attempt = 0; attempt < 100 && !authoredSwitchHandle.covers("x"); attempt++) {
    await nextTask();
  }
  const restoredAutomaticTicks = authoredSwitchView._axisTicks("x", 6);
  if (!authoredSwitchHandle.covers("x") || restoredAutomaticTicks.source !== "wasm"
      || !restoredAutomaticTicks.ticks.length) {
    throw new Error(`automatic provenance restore did not admit a matching cache: ${JSON.stringify({
      covers: authoredSwitchHandle.covers("x"),
      restoredAutomaticTicks,
    })}`);
  }
  await authoredSwitchHandle.dispose();
  authoredSwitchView.destroy();
  authoredSwitchHost.remove();

  foundationStage = "family switch after attach waits for a matching Rust cache";
  const switchTickHost = document.createElement("div");
  switchTickHost.style.cssText = "width:320px;height:240px";
  document.body.append(switchTickHost);
  const switchTickView = directDensityFixture(switchTickHost);
  const switchTickWorker = createXygWasmWorker({
    workerUrl: "/packages/xy-client/dist/wasm-worker.js",
    wasm: wasmModule,
    maxArenaBytes: 1024 * 1024,
  });
  const switchTickHandle = await attachWasmTicks(switchTickView, {
    worker: switchTickWorker,
    workerOwnership: "own",
  });
  const linearXTicks = switchTickView._axisTicks("x", 6);
  Object.assign(switchTickView.axes.x, {
    kind: "category", categories: ["alpha", "beta", "gamma"], range: [0, 2],
  });
  switchTickView.view = switchTickView._copyView({ ranges: { x: [0, 2], y: [0, 1] } });
  const switchedXTicks = switchTickView._axisTicks("x", 3);
  const switchedXLabel = switchTickView._axisTickText(switchTickView.axes.x, 0, switchedXTicks.step);
  if (linearXTicks.source !== "wasm" || !switchTickHandle.eligible("x")
      || switchTickHandle.covers("x") || switchedXTicks.source === "wasm"
      || switchedXTicks.ticks.join(",") !== "0,1,2" || switchedXLabel !== "alpha") {
    throw new Error(`family switch reused a stale WASM cache: ${JSON.stringify({
      eligible: switchTickHandle.eligible("x"),
      covers: switchTickHandle.covers("x"),
      linearXTicks,
      switchedXTicks,
      switchedXLabel,
    })}`);
  }
  switchTickHandle.schedule();
  for (let attempt = 0; attempt < 100 && !switchTickHandle.covers("x"); attempt++) {
    await nextTask();
  }
  const admittedSwitchTicks = switchTickView._axisTicks("x", 3);
  const admittedSwitchLabel = switchTickView._axisTickText(
    switchTickView.axes.x, 1, admittedSwitchTicks.step,
  );
  if (!switchTickHandle.covers("x") || admittedSwitchTicks.source !== "wasm"
      || admittedSwitchTicks.ticks.join(",") !== "0,1,2"
      || admittedSwitchLabel !== "beta"
      || switchTickHandle.label("x", 2) !== "gamma") {
    throw new Error(`family switch did not admit a matching category cache: ${JSON.stringify({
      covers: switchTickHandle.covers("x"),
      admittedSwitchTicks,
      admittedSwitchLabel,
    })}`);
  }
  switchTickView.axes.x.categories = ["red", "green"];
  const renamedXTicks = switchTickView._axisTicks("x", 2);
  if (switchTickHandle.covers("x") || renamedXTicks.source === "wasm"
      || renamedXTicks.ticks.join(",") !== "0,1"
      || switchTickView._axisTickText(switchTickView.axes.x, 0, renamedXTicks.step) !== "red") {
    throw new Error(`category-table change stayed on a stale WASM cache: ${JSON.stringify({
      covers: switchTickHandle.covers("x"),
      renamedXTicks,
    })}`);
  }
  switchTickHandle.schedule();
  for (let attempt = 0; attempt < 100 && !switchTickHandle.covers("x"); attempt++) {
    await nextTask();
  }
  const renamedAdmitted = switchTickView._axisTicks("x", 2);
  if (!switchTickHandle.covers("x") || renamedAdmitted.source !== "wasm"
      || switchTickHandle.label("x", 0) !== "red"
      || switchTickHandle.label("x", 1) !== "green") {
    throw new Error(`category-table change did not admit a matching cache: ${JSON.stringify({
      covers: switchTickHandle.covers("x"),
      renamedAdmitted,
      labels: [switchTickHandle.label("x", 0), switchTickHandle.label("x", 1)],
    })}`);
  }
  await switchTickHandle.dispose();
  switchTickView.destroy();
  switchTickHost.remove();

  foundationStage = "sequential ChartView tick re-attach replaces the previous handle";
  const reattachHost = document.createElement("div");
  reattachHost.style.cssText = "width:320px;height:240px";
  document.body.append(reattachHost);
  const reattachView = directDensityFixture(reattachHost);
  const firstTickWorker = createXygWasmWorker({
    workerUrl: "/packages/xy-client/dist/wasm-worker.js",
    wasm: wasmModule,
    maxArenaBytes: 1024 * 1024,
  });
  const firstTickHandle = await attachWasmTicks(reattachView, {
    worker: firstTickWorker,
    workerOwnership: "own",
  });
  const firstTickRevision = firstTickHandle.diagnostics()?.revision;
  const secondTickWorker = createXygWasmWorker({
    workerUrl: "/packages/xy-client/dist/wasm-worker.js",
    wasm: wasmModule,
    maxArenaBytes: 1024 * 1024,
  });
  const secondTickHandle = await attachWasmTicks(reattachView, {
    worker: secondTickWorker,
    workerOwnership: "own",
  });
  const reattachedX = reattachView._axisTicks("x", 6);
  const reattachedY = reattachView._axisTicks("y", 6);
  if (reattachView._wasmTicks !== secondTickHandle
      || firstTickHandle.schedule() !== null
      || secondTickHandle.diagnostics()?.revision < 1
      || firstTickRevision < 1
      || reattachedX.source !== "wasm" || reattachedY.source !== "wasm"
      || !reattachedX.ticks.length || !reattachedY.ticks.length) {
    throw new Error(`sequential ChartView tick re-attach failed: ${JSON.stringify({
      sameHandle: reattachView._wasmTicks === secondTickHandle,
      firstSchedule: firstTickHandle.schedule(),
      firstTickRevision,
      secondRevision: secondTickHandle.diagnostics()?.revision,
      xSource: reattachedX.source,
      ySource: reattachedY.source,
    })}`);
  }
  await firstTickHandle.dispose();
  if (reattachView._wasmTicks !== secondTickHandle) {
    throw new Error("disposing the previous tick handle clobbered the live attachment");
  }
  await secondTickHandle.dispose();
  reattachView.destroy();
  reattachHost.remove();

  foundationStage = "secondary ChartView axes stay on the compatibility tick path";
  const secondaryTickHost = document.createElement("div");
  secondaryTickHost.style.cssText = "width:320px;height:240px";
  document.body.append(secondaryTickHost);
  const secondaryTickView = directDensityFixture(secondaryTickHost, null, true);
  const secondaryTickWorker = createXygWasmWorker({
    workerUrl: "/packages/xy-client/dist/wasm-worker.js",
    wasm: wasmModule,
    maxArenaBytes: 1024 * 1024,
  });
  const secondaryTickHandle = await attachWasmTicks(secondaryTickView, {
    worker: secondaryTickWorker,
    workerOwnership: "own",
  });
  const primaryXTicks = secondaryTickView._axisTicks("x", 6);
  const primaryYTicks = secondaryTickView._axisTicks("y", 6);
  const secondaryXTicks = secondaryTickView._axisTicks("x2", 6);
  const secondaryYTicks = secondaryTickView._axisTicks("y2", 6);
  if (primaryXTicks.source !== "wasm" || primaryYTicks.source !== "wasm"
      || secondaryXTicks.source === "wasm" || secondaryYTicks.source === "wasm"
      || secondaryTickHandle.diagnostics()?.axisIds.join(",") !== "x,y"
      || !secondaryXTicks.ticks.length || !secondaryYTicks.ticks.length
      || secondaryXTicks.ticks.every((value) => value >= 0 && value <= 1)
      || secondaryYTicks.ticks.every((value) => value >= 0 && value <= 1)) {
    throw new Error(`secondary axes were claimed by WASM ticks: ${JSON.stringify({
      axisIds: secondaryTickHandle.diagnostics()?.axisIds,
      primaryX: primaryXTicks,
      primaryY: primaryYTicks,
      secondaryX: secondaryXTicks,
      secondaryY: secondaryYTicks,
    })}`);
  }
  await secondaryTickHandle.dispose();
  secondaryTickView.destroy();
  secondaryTickHost.remove();

  foundationStage = "newly eligible axis after attach does not paint empty wasm";
  const lateTickHost = document.createElement("div");
  lateTickHost.style.cssText = "width:320px;height:240px";
  document.body.append(lateTickHost);
  const lateTickView = directDensityFixture(lateTickHost);
  Object.assign(lateTickView.axes.y, {
    theta_unit: "degrees", range: [0, 1],
  });
  lateTickView.view0 = lateTickView._copyView({ ranges: { x: [0, 1], y: [0, 1] } });
  lateTickView.view = lateTickView._copyView(lateTickView.view0);
  const lateTickWorker = createXygWasmWorker({
    workerUrl: "/packages/xy-client/dist/wasm-worker.js",
    wasm: wasmModule,
    maxArenaBytes: 1024 * 1024,
  });
  const lateTickHandle = await attachWasmTicks(lateTickView, {
    worker: lateTickWorker,
    workerOwnership: "own",
  });
  const angularYTicks = lateTickView._axisTicks("y", 2);
  delete lateTickView.axes.y.theta_unit;
  const immediateYTicks = lateTickView._axisTicks("y", 6);
  if (!lateTickHandle.eligible("y") || lateTickHandle.covers("y")
      || angularYTicks.source === "wasm"
      || immediateYTicks.source === "wasm"
      || !immediateYTicks.ticks.length) {
    throw new Error(`newly eligible y painted empty wasm before admission: ${JSON.stringify({
      eligible: lateTickHandle.eligible("y"),
      covers: lateTickHandle.covers("y"),
      angularYTicks,
      immediateYTicks,
    })}`);
  }
  lateTickHandle.schedule();
  for (let attempt = 0; attempt < 100 && !lateTickHandle.covers("y"); attempt++) {
    await nextTask();
  }
  const admittedYTicks = lateTickView._axisTicks("y", 6);
  if (!lateTickHandle.covers("y") || admittedYTicks.source !== "wasm" || !admittedYTicks.ticks.length) {
    throw new Error(`newly eligible y did not admit a Rust cache: ${JSON.stringify({
      covers: lateTickHandle.covers("y"),
      admittedYTicks,
    })}`);
  }
  await lateTickHandle.dispose();
  lateTickView.destroy();
  lateTickHost.remove();

  foundationStage = "ChartView tick latest-wins admission and fail-closed Worker error";
  const lifecycleTickHost = document.createElement("div");
  lifecycleTickHost.style.cssText = "width:320px;height:240px";
  document.body.append(lifecycleTickHost);
  const lifecycleTickView = directDensityFixture(lifecycleTickHost);
  const lifecycleTickErrors = [];
  lifecycleTickView.root.addEventListener(
    "xy:wasm_ticks_error",
    (event) => lifecycleTickErrors.push(event.detail),
  );
  const lifecycleTickWorker = createXygWasmWorker({
    workerUrl: "/packages/xy-client/dist/wasm-worker.js",
    wasm: wasmModule,
    maxArenaBytes: 1024 * 1024,
  });
  let tickProxyCalls = 0;
  let tickProxyCancels = 0;
  let tickAllocations = 0;
  const delayedTickWorker = {
    ready: lifecycleTickWorker.ready,
    allocateTickSequence() {
      tickAllocations += 1;
      return lifecycleTickWorker.allocateTickSequence();
    },
    resolveTicks(request, options) {
      const call = ++tickProxyCalls;
      let forwarded = null;
      const result = new Promise((resolve, reject) => {
        setTimeout(() => {
          try {
            forwarded = lifecycleTickWorker.resolveTicks(request, options);
            forwarded.result.then(resolve, reject);
          } catch (error) {
            reject(error);
          }
        }, call === 2 ? 50 : 0);
      });
      return {
        requestId: call,
        sequence: options.sequence,
        result,
        // Deliberately leave the delayed transport alive: the adapter must
        // reject a late result independently of cooperative cancellation.
        cancel() {
          tickProxyCancels++;
          forwarded?.cancel();
        },
      };
    },
    dispose: () => lifecycleTickWorker.dispose(),
  };
  const lifecycleTickHandle = await attachWasmTicks(lifecycleTickView, {
    worker: delayedTickWorker,
  });
  const initialTickRevision = lifecycleTickHandle.diagnostics().revision;
  lifecycleTickView.view = lifecycleTickView._copyView({
    ranges: { x: [0, 0.25], y: [0, 1] },
  });
  const staleRevision = lifecycleTickHandle.schedule();
  lifecycleTickView.view = lifecycleTickView._copyView({
    ranges: { x: [0.75, 1], y: [0, 1] },
  });
  const currentRevision = lifecycleTickHandle.schedule();
  for (let attempt = 0; attempt < 100
    && lifecycleTickHandle.diagnostics().revision < initialTickRevision + 2; attempt++) {
    await nextTask();
  }
  await new Promise((resolve) => setTimeout(resolve, 70));
  const currentTickDiagnostics = lifecycleTickHandle.diagnostics();
  const currentXTicks = lifecycleTickView._axisTicks("x", 6);
  if (staleRevision >= currentRevision || tickProxyCancels < 1
      || currentTickDiagnostics.revision !== currentRevision
      || currentTickDiagnostics.cancellations < 1
      || currentXTicks.source !== "wasm"
      || currentXTicks.ticks.some((value) => value < 0.75 || value > 1)
      || lifecycleTickErrors.length) {
    throw new Error(`ChartView tick latest-wins admission drifted: ${JSON.stringify({
      staleRevision,
      currentRevision,
      tickProxyCancels,
      currentTickDiagnostics,
      currentXTicks,
      lifecycleTickErrors,
    })}`);
  }
  const lastGoodTicks = currentXTicks.ticks.join(",");
  await lifecycleTickWorker.dispose();
  lifecycleTickView.view = lifecycleTickView._copyView({
    ranges: { x: [0.5, 0.75], y: [0, 1] },
  });
  const failedAllocations = tickAllocations;
  lifecycleTickHandle.schedule();
  await nextTask();
  lifecycleTickView.draw();
  await new Promise((resolve) => requestAnimationFrame(() => resolve()));
  const retainedXTicks = lifecycleTickView._axisTicks("x", 6);
  if (lifecycleTickErrors.length !== 1
      || lifecycleTickErrors[0].code !== "XYG_WASM_DISPOSED"
      || Object.keys(lifecycleTickErrors[0]).sort().join(",") !== "code,diagnostics,message"
      || retainedXTicks.source !== "wasm"
      || retainedXTicks.ticks.join(",") !== lastGoodTicks
      || tickAllocations <= failedAllocations) {
    throw new Error(`ChartView tick Worker failure did not fail closed: ${JSON.stringify({
      lifecycleTickErrors,
      retainedXTicks,
      lastGoodTicks,
      failedAllocations,
      tickAllocations,
    })}`);
  }
  foundationStage = "failed ChartView tick snapshot retries without a second event";
  const retryAllocations = tickAllocations;
  lifecycleTickHandle.schedule();
  await nextTask();
  if (tickAllocations <= retryAllocations || lifecycleTickErrors.length !== 1) {
    throw new Error(`failed tick snapshot did not retry or re-emitted: ${JSON.stringify({
      retryAllocations,
      tickAllocations,
      lifecycleTickErrors,
    })}`);
  }
  await lifecycleTickHandle.dispose();
  lifecycleTickView.destroy();
  lifecycleTickHost.remove();

  foundationStage = "ChartView tick missing assets reject before attachment";
  const missingTickHost = document.createElement("div");
  missingTickHost.style.cssText = "width:320px;height:240px";
  document.body.append(missingTickHost);
  const missingTickView = directDensityFixture(missingTickHost);
  const missingTickErrors = [];
  missingTickView.root.addEventListener(
    "xy:wasm_ticks_error",
    (event) => missingTickErrors.push(event.detail),
  );
  const missingTickWorker = createXygWasmWorker({
    workerUrl: "/packages/xy-client/dist/wasm-worker.js",
    wasm: "/missing.wasm",
    maxArenaBytes: 1024 * 1024,
  });
  await rejected(
    attachWasmTicks(missingTickView, {
      worker: missingTickWorker,
      workerOwnership: "own",
    }),
    "XYG_WASM_INIT_FAILED",
  );
  if (missingTickErrors.length !== 1
      || missingTickErrors[0].code !== "XYG_WASM_INIT_FAILED"
      || missingTickView._wasmTicks != null) {
    throw new Error(`missing ChartView tick assets did not reject atomically: ${JSON.stringify({
      missingTickErrors,
      attached: missingTickView._wasmTicks != null,
    })}`);
  }
  missingTickView.destroy();
  missingTickHost.remove();

  foundationStage = "uncovered ChartView tick families retain compatibility paths";
  const uncoveredTickHost = document.createElement("div");
  uncoveredTickHost.style.cssText = "width:320px;height:240px";
  document.body.append(uncoveredTickHost);
  const uncoveredTickView = directDensityFixture(uncoveredTickHost);
  Object.assign(uncoveredTickView.axes.x, {
    kind: "category", categories: [], range: [0, 1],
  });
  uncoveredTickView.view0 = uncoveredTickView._copyView({
    ranges: { x: [0, 1], y: [0, 1] },
  });
  uncoveredTickView.view = uncoveredTickView._copyView(uncoveredTickView.view0);
  const uncoveredTickWorker = createXygWasmWorker({
    workerUrl: "/packages/xy-client/dist/wasm-worker.js",
    wasm: wasmModule,
    maxArenaBytes: 1024 * 1024,
  });
  const uncoveredTickHandle = await attachWasmTicks(uncoveredTickView, {
    worker: uncoveredTickWorker,
    workerOwnership: "own",
  });
  const emptyCategoryTicks = uncoveredTickView._axisTicks("x", 3);
  const coveredYTicks = uncoveredTickView._axisTicks("y", 6);
  uncoveredTickView.axes.x.kind = "linear";
  delete uncoveredTickView.axes.x.categories;
  uncoveredTickView.axes.x.theta_unit = "degrees";
  const angularAxisTicks = uncoveredTickView._axisTicks("x", 6);
  const uncoveredTickErrors = [];
  uncoveredTickView.root.addEventListener(
    "xy:wasm_ticks_error",
    (event) => uncoveredTickErrors.push(event.detail),
  );
  uncoveredTickView.draw();
  await new Promise((resolve) => requestAnimationFrame(() => resolve()));
  const idleAngularTicks = uncoveredTickView._axisTicks("x", 6);
  if (emptyCategoryTicks.source !== undefined
      || coveredYTicks.source !== "wasm"
      || angularAxisTicks.source !== undefined || !angularAxisTicks.ticks.length
      || idleAngularTicks.source !== undefined || uncoveredTickErrors.length) {
    throw new Error(`uncovered tick family routing drifted: ${JSON.stringify({
      emptyCategoryTicks,
      coveredYTicks,
      angularAxisTicks,
      idleAngularTicks,
      uncoveredTickErrors,
    })}`);
  }
  foundationStage = "uncovered after attach does not emit";
  await uncoveredTickHandle.dispose();
  uncoveredTickView.destroy();
  uncoveredTickHost.remove();

  foundationStage = "ChartView colorbar ticks use Rust/WASM";
  const colorbarTickHost = document.createElement("div");
  colorbarTickHost.style.cssText = "width:320px;height:240px";
  document.body.append(colorbarTickHost);
  const colorbarTickView = directDensityFixture(colorbarTickHost, null, false, false, {
    domain: [0, 1], orientation: "vertical", colormap: "viridis", label: "z",
  });
  const colorbarTickWorker = createXygWasmWorker({
    workerUrl: "/packages/xy-client/dist/wasm-worker.js",
    wasm: wasmModule,
    maxArenaBytes: 1024 * 1024,
  });
  const colorbarTickHandle = await attachWasmTicks(colorbarTickView, {
    worker: colorbarTickWorker,
    workerOwnership: "own",
  });
  await new Promise((resolve) => requestAnimationFrame(() => resolve()));
  const colorbarTicks = colorbarTickView._axisTicks("colorbar", 6);
  const colorbarX = colorbarTickView._axisTicks("x", 6);
  const colorbarDom = [...colorbarTickView.root.querySelectorAll(
    '[data-xy-slot="colorbar_tick"]',
  )].map((node) => node.textContent);
  if (colorbarTicks.source !== "wasm" || colorbarX.source !== "wasm"
      || !colorbarTickHandle.covers("colorbar") || !colorbarTickHandle.covers("x")
      || colorbarTickHandle.diagnostics()?.axisIds.join(",") !== "x,y,colorbar"
      || !colorbarTicks.ticks.length
      || colorbarDom.length !== colorbarTicks.labels.length
      || colorbarDom.some((label, index) => (
        label !== colorbarTickHandle.label("colorbar", colorbarTicks.labels[index])
      ))) {
    throw new Error(`ChartView did not consume Rust colorbar ticks: ${JSON.stringify({
      diagnostics: colorbarTickHandle.diagnostics(),
      colorbarTicks,
      colorbarX,
      colorbarDom,
    })}`);
  }
  colorbarTickView.spec.colorbar.scale = "log";
  colorbarTickView.spec.colorbar.domain = [0.1, 100];
  const immediateLogColorbar = colorbarTickView._axisTicks("colorbar", 6);
  if (colorbarTickHandle.covers("colorbar") || immediateLogColorbar.source === "wasm") {
    throw new Error(`log colorbar switch painted wasm before admission: ${JSON.stringify({
      covers: colorbarTickHandle.covers("colorbar"),
      immediateLogColorbar,
    })}`);
  }
  colorbarTickHandle.schedule();
  for (let attempt = 0; attempt < 100 && !colorbarTickHandle.covers("colorbar"); attempt++) {
    await nextTask();
  }
  const logColorbarTicks = colorbarTickView._axisTicks("colorbar", 6);
  if (!colorbarTickHandle.covers("colorbar") || logColorbarTicks.source !== "wasm"
      || !logColorbarTicks.ticks.length) {
    throw new Error(`log colorbar did not admit a Rust cache: ${JSON.stringify({
      covers: colorbarTickHandle.covers("colorbar"),
      logColorbarTicks,
    })}`);
  }
  await colorbarTickHandle.dispose();
  colorbarTickView.destroy();
  colorbarTickHost.remove();

  foundationStage = "authored ChartView colorbar ticks use Rust/WASM";
  const authoredColorbarHost = document.createElement("div");
  authoredColorbarHost.style.cssText = "width:320px;height:240px";
  document.body.append(authoredColorbarHost);
  const authoredColorbarView = directDensityFixture(authoredColorbarHost, null, false, false, {
    domain: [0, 1],
    orientation: "vertical",
    ticks: [-1, 0, 0.5, 1, 3],
    tick_labels: ["minus", "zero", "half", "one", "three"],
  });
  const authoredColorbarWorker = createXygWasmWorker({
    workerUrl: "/packages/xy-client/dist/wasm-worker.js",
    wasm: wasmModule,
    maxArenaBytes: 1024 * 1024,
  });
  const authoredColorbarHandle = await attachWasmTicks(authoredColorbarView, {
    worker: authoredColorbarWorker,
    workerOwnership: "own",
  });
  await new Promise((resolve) => requestAnimationFrame(() => resolve()));
  const authoredColorbarTicks = authoredColorbarView._axisTicks("colorbar", 6);
  const authoredColorbarDom = [...authoredColorbarView.root.querySelectorAll(
    '[data-xy-slot="colorbar_tick"]',
  )].map((node) => node.textContent);
  if (authoredColorbarTicks.source !== "wasm"
      || !authoredColorbarHandle.covers("colorbar")
      || authoredColorbarTicks.ticks.join(",") !== "0,0.5,1"
      || authoredColorbarHandle.label("colorbar", 0) !== "zero"
      || authoredColorbarHandle.label("colorbar", 0.5) !== "half"
      || authoredColorbarHandle.label("colorbar", 1) !== "one"
      || authoredColorbarDom.join(",") !== "zero,half,one") {
    throw new Error(`ChartView did not consume Rust authored colorbar ticks: ${JSON.stringify({
      diagnostics: authoredColorbarHandle.diagnostics(),
      authoredColorbarTicks,
      authoredColorbarDom,
    })}`);
  }
  authoredColorbarView.spec.colorbar.ticks = [];
  delete authoredColorbarView.spec.colorbar.tick_labels;
  const immediateEmptyColorbar = authoredColorbarView._axisTicks("colorbar", 6);
  if (authoredColorbarHandle.covers("colorbar") || immediateEmptyColorbar.source === "wasm") {
    throw new Error(`authored-empty colorbar painted wasm before admission: ${JSON.stringify({
      covers: authoredColorbarHandle.covers("colorbar"),
      immediateEmptyColorbar,
    })}`);
  }
  authoredColorbarHandle.schedule();
  for (let attempt = 0; attempt < 100 && !authoredColorbarHandle.covers("colorbar"); attempt++) {
    await nextTask();
  }
  const emptyColorbarTicks = authoredColorbarView._axisTicks("colorbar", 6);
  if (!authoredColorbarHandle.covers("colorbar") || emptyColorbarTicks.source !== "wasm"
      || emptyColorbarTicks.ticks.length !== 0) {
    throw new Error(`authored-empty colorbar did not admit an empty Rust cache: ${JSON.stringify({
      covers: authoredColorbarHandle.covers("colorbar"),
      emptyColorbarTicks,
    })}`);
  }
  await authoredColorbarHandle.dispose();
  authoredColorbarView.destroy();
  authoredColorbarHost.remove();

  foundationStage = "newly eligible colorbar after attach does not paint empty wasm";
  const lateColorbarHost = document.createElement("div");
  lateColorbarHost.style.cssText = "width:320px;height:240px";
  document.body.append(lateColorbarHost);
  const lateColorbarView = directDensityFixture(lateColorbarHost);
  const lateColorbarWorker = createXygWasmWorker({
    workerUrl: "/packages/xy-client/dist/wasm-worker.js",
    wasm: wasmModule,
    maxArenaBytes: 1024 * 1024,
  });
  const lateColorbarHandle = await attachWasmTicks(lateColorbarView, {
    worker: lateColorbarWorker,
    workerOwnership: "own",
  });
  if (lateColorbarHandle.eligible("colorbar") || lateColorbarHandle.covers("colorbar")) {
    throw new Error("colorbar was eligible before spec.colorbar existed");
  }
  lateColorbarView.spec.colorbar = { domain: [0, 1], orientation: "vertical" };
  const immediateLateColorbar = lateColorbarView._axisTicks("colorbar", 6);
  if (!lateColorbarHandle.eligible("colorbar") || lateColorbarHandle.covers("colorbar")
      || immediateLateColorbar.source === "wasm"
      || !immediateLateColorbar.ticks.length) {
    throw new Error(`newly eligible colorbar painted empty wasm before admission: ${JSON.stringify({
      eligible: lateColorbarHandle.eligible("colorbar"),
      covers: lateColorbarHandle.covers("colorbar"),
      immediateLateColorbar,
    })}`);
  }
  lateColorbarHandle.schedule();
  for (let attempt = 0; attempt < 100 && !lateColorbarHandle.covers("colorbar"); attempt++) {
    await nextTask();
  }
  const admittedColorbarTicks = lateColorbarView._axisTicks("colorbar", 6);
  if (!lateColorbarHandle.covers("colorbar") || admittedColorbarTicks.source !== "wasm"
      || !admittedColorbarTicks.ticks.length) {
    throw new Error(`newly eligible colorbar did not admit a Rust cache: ${JSON.stringify({
      covers: lateColorbarHandle.covers("colorbar"),
      admittedColorbarTicks,
    })}`);
  }
  await lateColorbarHandle.dispose();
  lateColorbarView.destroy();
  lateColorbarHost.remove();

  foundationStage = "scene-placed ChartView colorbar stays off the XYTK lane";
  const sceneColorbarHost = document.createElement("div");
  sceneColorbarHost.style.cssText = "width:320px;height:240px";
  document.body.append(sceneColorbarHost);
  const sceneColorbarView = directDensityFixture(sceneColorbarHost, null, false, false, {
    domain: [0, 1],
    placement: "scene",
    resolved: {
      bounds: [280, 20, 24, 180],
      major_ticks: [
        { value: 0, label: "0", position: 200 },
        { value: 1, label: "1", position: 20 },
      ],
    },
  });
  const sceneColorbarWorker = createXygWasmWorker({
    workerUrl: "/packages/xy-client/dist/wasm-worker.js",
    wasm: wasmModule,
    maxArenaBytes: 1024 * 1024,
  });
  const sceneColorbarHandle = await attachWasmTicks(sceneColorbarView, {
    worker: sceneColorbarWorker,
    workerOwnership: "own",
  });
  const sceneColorbarTicks = sceneColorbarView._axisTicks("colorbar", 6);
  if (sceneColorbarHandle.eligible("colorbar") || sceneColorbarHandle.covers("colorbar")
      || sceneColorbarTicks.source === "wasm"
      || sceneColorbarHandle.diagnostics()?.axisIds.includes("colorbar")
      || sceneColorbarTicks.ticks.join(",") !== "0,1") {
    throw new Error(`scene-placed colorbar was claimed by XYTK: ${JSON.stringify({
      eligible: sceneColorbarHandle.eligible("colorbar"),
      covers: sceneColorbarHandle.covers("colorbar"),
      diagnostics: sceneColorbarHandle.diagnostics(),
      sceneColorbarTicks,
    })}`);
  }
  await sceneColorbarHandle.dispose();
  sceneColorbarView.destroy();
  sceneColorbarHost.remove();

  foundationStage = "polar ChartView ticks reject before attachment";
  const polarTickHost = document.createElement("div");
  polarTickHost.style.cssText = "width:320px;height:240px";
  document.body.append(polarTickHost);
  const polarTickView = directDensityFixture(polarTickHost, null, false, false, {
    domain: [0, 1], orientation: "vertical", colormap: "viridis",
  });
  polarTickView.spec.coords = "polar";
  const polarTickErrors = [];
  polarTickView.root.addEventListener(
    "xy:wasm_ticks_error",
    (event) => polarTickErrors.push(event.detail),
  );
  const polarTickWorker = createXygWasmWorker({
    workerUrl: "/packages/xy-client/dist/wasm-worker.js",
    wasm: wasmModule,
    maxArenaBytes: 1024 * 1024,
  });
  await rejected(
    attachWasmTicks(polarTickView, {
      worker: polarTickWorker,
      workerOwnership: "own",
    }),
    "XYG_WASM_INVALID_ARGUMENT",
  );
  if (polarTickErrors.length !== 1 || polarTickView._wasmTicks != null) {
    throw new Error(`polar ChartView tick attachment was not rejected: ${JSON.stringify({
      polarTickErrors,
      attached: polarTickView._wasmTicks != null,
    })}`);
  }
  polarTickView.destroy();
  polarTickHost.remove();

  const fromHex = (value) => Uint8Array.from(value.match(/../g) ?? [], (pair) => Number.parseInt(pair, 16));
  const fixtureWorker = createXygWasmWorker({
    workerUrl: "/packages/xy-client/dist/wasm-worker.js",
    wasm: wasmModule,
    maxArenaBytes: 16 * 1024 * 1024,
  });
  const fixtureReady = await fixtureWorker.ready;
  if (fixtureReady.defaultPaletteVersion !== 1 || fixtureReady.defaultPaletteRows !== 8
      || fixtureReady.defaultPaletteFirstRgba8 !== 0xffe58739) {
    throw new Error(`direct WASM default palette contract drifted: ${JSON.stringify(fixtureReady)}`);
  }
  let fixtureSequence = 1;
  for (const fixture of xytsFixture.successful) {
    const compiled = await fixtureWorker.compileScene(fromHex(fixture.request_hex), {
      sequence: fixtureSequence++, transfer: false,
    }).result;
    const expected = fromHex(fixture.scene_hex), actual = new Uint8Array(compiled.scene);
    if (actual.length !== expected.length || actual.some((value, index) => value !== expected[index])) {
      throw new Error(`direct WASM drifted from Rust-generated XYTS fixture ${fixture.name}`);
    }
    if (compiled.records !== fixture.records || compiled.styles !== fixture.styles) {
      throw new Error(`direct WASM summary drifted for ${fixture.name}`);
    }
    const prepared = await fixtureWorker.prepareScene(actual, {
      sequence: fixtureSequence++, transfer: false,
    }).result;
    const expectedPainter = fromHex(fixture.painter_hex), actualPainter = new Uint8Array(prepared.painter);
    if (actualPainter.length !== expectedPainter.length
        || actualPainter.some((value, index) => value !== expectedPainter[index])) {
      throw new Error(`direct WASM painter v14 drifted from Rust-generated fixture ${fixture.name}`);
    }
    if (fixture.name === "area_visible_stroke_perimeter"
        && (actual[160 + fixture.styles * 16 + 2] !== 2 || actualPainter[301] !== 2)) {
      throw new Error("XYTS v2 visible area stroke lost its legacy perimeter topology");
    }
  }
  for (const [mode, expectedSymbol] of [["top", 1], ["perimeter", 2], ["none", 0]]) {
    const encoded = Uint8Array.from(atob(sharedFixture.band_outlines[mode].scene_base64), (char) => char.charCodeAt(0));
    const prepared = await fixtureWorker.prepareScene(encoded, {
      sequence: fixtureSequence++, transfer: false,
    }).result;
    const painter = new Uint8Array(prepared.painter);
    if (painter[301] !== expectedSymbol) {
      throw new Error(`Rust Band ${mode} painter descriptor lost its outline mode`);
    }
    const host = document.body.appendChild(document.createElement("div"));
    const view = hydrateWasmPainter(host, prepared);
    const band = view.gpuTraces.find((candidate) => candidate.trace?.kind === "area");
    if (!band || band.trace.style.line_width !== (mode === "none" ? 0 : 2)
        || band.trace.style.stroke_perimeter !== (mode === "perimeter")
        || Boolean(band.bandLeftXBuf) !== (mode === "perimeter")
        || Boolean(band.bandRightYBuf) !== (mode === "perimeter")) {
      throw new Error(`browser Band ${mode} did not consume Rust-owned outline topology`);
    }
    view.destroy(); host.remove();
  }
  const encodedBandHarness = {
    spec: { columns: [
      { buf: 0, offset: 0, scale: 1 },
      { buf: 1, offset: 100, scale: 0.25 },
      { buf: 2, offset: -50, scale: 2 },
    ] },
    _columnView: (buffers, meta) => buffers[meta.buf],
    _smoothArrays: () => null,
    _upload: (values) => values,
    root: document.body,
    _resolveMarkFill: () => null,
  };
  const encodedBand = {};
  ChartView.prototype._buildAreaMark.call(encodedBandHarness, encodedBand, {
    x: 0, y: 1, base: 2, style: { stroke_perimeter: true },
  }, [
    new Float32Array([0, 1]),
    new Float32Array([-20, -18]),
    new Float32Array([100, 120]),
  ]);
  if (Array.from(encodedBand.bandLeftYBuf).join(",") !== "-20,-25"
      || Array.from(encodedBand.bandRightYBuf).join(",") !== "-18,-22.5") {
    throw new Error("browser Band perimeter endpoints mixed distinct y/base offset encodings");
  }
  const failureContract = {
    wrong_version: ["XYG_WASM_SCENE_VERSION", 4],
    unsupported_kind: ["XYG_WASM_INVALID_ARGUMENT", 2],
    stable_id_overflow: ["XYG_WASM_RESOURCE_LIMIT", 3],
    nonfinite_geometry: ["XYG_WASM_INVALID_ARGUMENT", 2],
  };
  for (const fixture of xytsFixture.failures) {
    const [code, status] = failureContract[fixture.name];
    await rejected(fixtureWorker.compileScene(fromHex(fixture.request_hex), {
      sequence: fixtureSequence++, transfer: false,
    }).result, code, status);
  }
  await fixtureWorker.dispose();

  const duplicate = rawWorkerHarness();
  const firstInit = duplicate.request(rawInit(100, { kind: "url", value: "/delayed.wasm" }));
  await fetch("/await-delayed");
  const secondInit = await duplicate.request(rawInit(101, { kind: "module", value: wasmModule }));
  if (secondInit.ok || secondInit.error?.code !== "XYG_WASM_ALREADY_INITIALIZED") {
    throw new Error(`concurrent duplicate init was not rejected: ${JSON.stringify(secondInit)}`);
  }
  await fetch("/release-delayed");
  const firstReady = await firstInit;
  if (!firstReady.ok) throw new Error(`first concurrent init failed: ${JSON.stringify(firstReady)}`);
  await duplicate.request({ type: "dispose", requestId: 102 });
  duplicate.worker.terminate();

  const malformedSeriesWorker = rawWorkerHarness();
  const malformedReady = await malformedSeriesWorker.request({
    ...rawInit(103, { kind: "module", value: wasmModule }),
    maxArenaBytes: 1024 * 1024,
  });
  if (!malformedReady.ok) throw new Error(`raw typed-series worker failed init: ${JSON.stringify(malformedReady)}`);
  const rawSeries = frameWasmChart({
    width: 320,
    height: 240,
    series: [{ kind: "scatter", x: new Float64Array([0.5]), y: new Float64Array([0.5]) }],
  });
  const malformedCombined = await malformedSeriesWorker.request({
    type: "series.compile_paint",
    requestId: 104,
    sequence: 1,
    prefix: rawSeries.prefix,
    columns: rawSeries.columns,
    byteLength: rawSeries.byteLength + 1,
  });
  if (malformedCombined.ok || malformedCombined.error?.code !== "XYG_WASM_INVALID_ARGUMENT") {
    throw new Error(`combined typed-series length did not fail closed: ${JSON.stringify(malformedCombined)}`);
  }
  const afterMalformedCombined = await malformedSeriesWorker.request({
    type: "scene.validate",
    requestId: 105,
    sequence: 2,
    scene: canonicalSceneV9().buffer,
  });
  if (!afterMalformedCombined.ok) {
    throw new Error(`combined-length rejection destroyed worker: ${JSON.stringify(afterMalformedCombined)}`);
  }
  if (afterMalformedCombined.value?.copyCount !== 1) {
    throw new Error(`successful raw Scene request omitted its Rust copy: ${JSON.stringify(afterMalformedCombined)}`);
  }
  const localAfterCopy = await malformedSeriesWorker.request({
    type: "series.compile_paint",
    requestId: 106,
    sequence: 3,
    prefix: rawSeries.prefix,
    columns: rawSeries.columns,
    byteLength: rawSeries.byteLength + 1,
  });
  if (localAfterCopy.ok || localAfterCopy.error?.code !== "XYG_WASM_INVALID_ARGUMENT"
      || localAfterCopy.error?.diagnostics !== null) {
    throw new Error(`local rejection inherited unrelated Rust counters: ${JSON.stringify(localAfterCopy)}`);
  }
  await malformedSeriesWorker.request({ type: "dispose", requestId: 107 });
  malformedSeriesWorker.worker.terminate();

  const disposedDuringInit = rawWorkerHarness();
  disposedDuringInit.worker.postMessage(
    rawInit(110, { kind: "url", value: "/delayed.wasm" }),
  );
  await fetch("/await-delayed");
  const disposedResponse = await disposedDuringInit.request({ type: "dispose", requestId: 111 });
  if (!disposedResponse.ok) {
    throw new Error(`dispose during init failed: ${JSON.stringify(disposedResponse)}`);
  }
  await fetch("/release-delayed");
  if (disposedDuringInit.messages.some((message) => message.requestId === 110)) {
    throw new Error("disposed initialization published a late ready or error response");
  }
  disposedDuringInit.worker.terminate();

  const worker = createXygWasmWorker({
    workerUrl: "/packages/xy-client/dist/wasm-worker.js",
    wasm: wasmModule,
    // Canonical Scene browser paint now exceeds the deliberately tiny 4 KiB
    // fixture budget; resource-limit probes below retain their narrow caps.
    maxArenaBytes: 8192,
  });
  const ready = await worker.ready;
  if (ready.abiVersion !== 25 || ready.sceneVersion !== CANONICAL_SCENE_VERSION) {
    throw new Error(`unexpected versions ${JSON.stringify(ready)}`);
  }
  if (ready.memoryBytes < 64 * 1024) throw new Error("WASM reserved-memory diagnostics are missing");

  foundationStage = "direct WASM ChartView density supersession and disposal";
  const densityHost = document.createElement("div");
  densityHost.style.cssText = "width:320px;height:240px";
  document.body.append(densityHost);
  const kernelDensityRequests = [];
  const densityView = directDensityFixture(densityHost, {
    send: (message) => kernelDensityRequests.push(message),
    onMessage: () => () => {},
  });
  const densityWorker = createXygWasmWorker({
    workerUrl: "/packages/xy-client/dist/wasm-worker.js", wasm: wasmModule, maxArenaBytes: 1024 * 1024,
  });
  const densityHandle = await attachWasmDensity(densityView, {
    worker: densityWorker,
    input: {
      traceId: 0,
      x: new Float64Array([0.05, 0.2, 0.75, 0.95]),
      y: new Float64Array([0.05, 0.8, 0.25, 0.95]),
    },
    delay: 0,
  });
  const firstDensityRevision = densityView._scheduleViewRequest(
    { ranges: { x: [0, 0.75], y: [0, 0.75] } }, { delay: 0 },
  );
  await nextTask(); // let the first aggregate enter the static Worker
  const secondDensityRevision = densityView._scheduleViewRequest(
    { ranges: { x: [0.25, 1], y: [0.25, 1] } }, { delay: 0 },
  );
  for (let attempt = 0; attempt < 100 && densityHandle.diagnostics() === null; attempt++) await nextTask();
  const densityDiagnostics = densityHandle.diagnostics();
  const densityTrace = densityView.gpuTraces.find((trace) => trace.tier === "density");
  if (!densityDiagnostics || densityDiagnostics.sequence !== secondDensityRevision
      || firstDensityRevision >= secondDensityRevision
      || densityTrace.density.xRange.join(",") !== "0.25,1"
      || densityTrace.density.yRange.join(",") !== "0.25,1"
      || kernelDensityRequests.length) {
    throw new Error(`direct WASM density failed supersession: ${JSON.stringify({
      firstDensityRevision, secondDensityRevision, densityDiagnostics,
      xRange: densityTrace?.density?.xRange, yRange: densityTrace?.density?.yRange,
      kernelDensityRequests,
    })}`);
  }
  await densityHandle.dispose();
  densityHandle.schedule({ ranges: { x: [0, 1], y: [0, 1] } });
  await nextTask();
  if (densityView._wasmDensity !== null || densityHandle.diagnostics()?.sequence !== secondDensityRevision) {
    throw new Error("disposed direct WASM density handle retained ChartView or accepted work");
  }
  densityView.destroy();
  await densityWorker.dispose();
  densityHost.remove();

  foundationStage = "automatic kernel-backed WASM density lifecycle";
  const automaticDensityHost = document.createElement("div");
  automaticDensityHost.style.cssText = "width:320px;height:240px";
  document.body.append(automaticDensityHost);
  const automaticKernelRequests = [];
  const automaticDensityView = directDensityFixture(automaticDensityHost, {
    send: (message) => automaticKernelRequests.push(message), onMessage: () => () => {},
  });
  const automaticTrace = automaticDensityView.gpuTraces.find((trace) => trace.tier === "density");
  automaticTrace.sampleOverlay = {
    trace: { color: null },
    _cpu: {
      x: new Float32Array([0.05, 0.2, 0.75, 0.95]),
      y: new Float32Array([0.05, 0.8, 0.25, 0.95]),
      xMeta: { scale: 1, offset: 0 }, yMeta: { scale: 1, offset: 0 },
    },
  };
  const automaticRevision = automaticDensityView._scheduleViewRequest(
    { ranges: { x: [0.25, 0.75], y: [0.25, 0.75] } }, { delay: 0 },
  );
  for (let attempt = 0; attempt < 100 && !automaticDensityView._wasmDensity?.diagnostics(); attempt++) await nextTask();
  if (!automaticDensityView._wasmDensity?.diagnostics()
      || automaticTrace.density.xRange.join(",") !== "0.25,0.75"
      || automaticTrace.density.yRange.join(",") !== "0.25,0.75"
      || automaticKernelRequests.length
      || automaticRevision !== undefined) {
    throw new Error(`automatic kernel-backed WASM density failed: ${JSON.stringify({
      automaticRevision, diagnostics: automaticDensityView._wasmDensity?.diagnostics(),
      xRange: automaticTrace.density.xRange, yRange: automaticTrace.density.yRange,
      automaticKernelRequests,
    })}`);
  }
  automaticDensityView._scheduleViewRequest({ ranges: { x: [0, 1], y: [0, 1] } }, { delay: 0 });
  for (let attempt = 0; attempt < 100 && automaticTrace.density.xRange.join(",") !== "0,1"; attempt++) await nextTask();
  if (automaticTrace.density.xRange.join(",") !== "0,1") {
    throw new Error("automatic kernel-backed WASM density did not aggregate the home viewport");
  }
  automaticDensityView.destroy();
  await nextTask();
  if (automaticDensityView._wasmDensity !== null) {
    throw new Error("destroyed automatic kernel-backed density retained its owned worker");
  }
  automaticDensityHost.remove();

  foundationStage = "full-source kernel WASM density lifecycle";
  const fullSourceHost = document.createElement("div");
  fullSourceHost.style.cssText = "width:320px;height:240px";
  document.body.append(fullSourceHost);
  const fullSourceEvents = [], fullSourceRequests = [];
  const fullSourceView = directDensityFixture(fullSourceHost, {
    send: (message) => fullSourceRequests.push(message), onMessage: () => () => {},
  }, false, true);
  fullSourceView.root.addEventListener("xy:wasm_density_error", (event) => fullSourceEvents.push(event.detail));
  const fullSourceWorker = createXygWasmWorker({
    workerUrl: "/packages/xy-client/dist/wasm-worker.js", wasm: wasmModule,
    maxArenaBytes: 8 * 1024 * 1024, evidenceCapability: "strict-csp-stream-resource-proof",
  });
  const fullSourceHandle = await attachWasmDensity(fullSourceView, {
    worker: fullSourceWorker, workerOwnership: "own", delay: 0, streamSource: true,
    input: {
      traceId: 0,
      x: new Float64Array(fullSourceView._payload[1].buffer),
      y: new Float64Array(fullSourceView._payload[2].buffer),
    },
  });
  const fullSourceTrace = fullSourceView.gpuTraces.find((trace) => trace.tier === "density");
  const fullSourceOverview = fullSourceTrace.density;
  fullSourceView._scheduleViewRequest({ ranges: { x: [0.25, 0.75], y: [0.25, 0.75] } }, { delay: 0 });
  for (let attempt = 0; attempt < 100 && !fullSourceView._wasmDensity?.diagnostics(); attempt++) await nextTask();
  if (!fullSourceView._wasmDensity?.diagnostics() || fullSourceTrace.density === fullSourceOverview
      || !fullSourceView.spec.wasm_density.source || fullSourceView._payload[1].byteLength !== 65_537 * 8 || fullSourceView._payload[2].byteLength !== 65_537 * 8
      || fullSourceRequests.length) {
    throw new Error(`full-source automatic WASM density did not retain/replay source correctly: ${JSON.stringify({
      diagnostics: fullSourceView._wasmDensity?.diagnostics(), source: fullSourceView.spec.wasm_density.source,
      payload: [fullSourceView._payload[1]?.byteLength, fullSourceView._payload[2]?.byteLength], requests: fullSourceRequests, events: fullSourceEvents,
      ranges: fullSourceTrace.density.xRange,
    })}`);
  }
  const fullSourceGrid = fullSourceTrace.density;
  // A capability-gated *Worker-side* XYAS declaration crosses the Rust
  // resource guard (4097² cells), then the ordinary viewport recovers on the
  // same strict-CSP module Worker. This is deliberately not a host-side
  // invalid-argument short circuit.
  await rejected(fullSourceHandle.evidenceLifecycle("stream_resource"), "XYG_WASM_RESOURCE_LIMIT");
  for (let attempt = 0; attempt < 100 && !fullSourceEvents.length; attempt++) await nextTask();
  if (fullSourceTrace.density !== fullSourceGrid || fullSourceEvents.length !== 1
      || fullSourceEvents[0].code !== "XYG_WASM_RESOURCE_LIMIT") {
    throw new Error(`full-source forced Worker failure did not retain overview/event: ${JSON.stringify(fullSourceEvents)}`);
  }
  fullSourceView._scheduleViewRequest({ ranges: { x: [0, 1], y: [0, 1] } }, { delay: 0 });
  for (let attempt = 0; attempt < 100 && fullSourceTrace.density.xRange.join(",") !== "0,1"; attempt++) await nextTask();
  if (fullSourceTrace.density.xRange.join(",") !== "0,1") throw new Error("full-source WASM density did not recover after validation failure");
  fullSourceView.destroy(); fullSourceHost.remove();

  foundationStage = "concurrent public XYAS stream supersession";
  const concurrentWorker = createXygWasmWorker({
    workerUrl: "/packages/xy-client/dist/wasm-worker.js", wasm: wasmModule, maxArenaBytes: 8 * 1024 * 1024,
  });
  await concurrentWorker.ready;
  const concurrentX = new Float64Array(65_537), concurrentY = new Float64Array(65_537);
  for (let index = 0; index < concurrentX.length; index++) {
    concurrentX[index] = index / concurrentX.length; concurrentY[index] = 1 - concurrentX[index];
  }
  const firstStream = concurrentWorker.aggregateStream({ x: concurrentX, y: concurrentY }, {
    x0: 0, x1: 1, y0: 0, y1: 1, width: 64, height: 64,
  }, { sequence: 1 });
  const secondStream = concurrentWorker.aggregateStream({ x: concurrentX, y: concurrentY }, {
    x0: 0, x1: 1, y0: 0, y1: 1, width: 64, height: 64,
  }, { sequence: 2 });
  await rejected(firstStream.result, "XYG_WASM_CANCELLED");
  const secondStreamResult = await secondStream.result;
  if (!(secondStreamResult.aggregate instanceof ArrayBuffer) || !secondStreamResult.aggregate.byteLength) {
    throw new Error("newer public XYAS stream did not settle after superseding its predecessor");
  }
  await concurrentWorker.dispose();

  foundationStage = "kernel-less retained-sample density uses local Rust/WASM";
  const standaloneDensityHost = document.createElement("div");
  standaloneDensityHost.style.cssText = "width:320px;height:240px";
  document.body.append(standaloneDensityHost);
  const standaloneDensityView = directDensityFixture(standaloneDensityHost);
  const standaloneTrace = standaloneDensityView.gpuTraces.find((trace) => trace.tier === "density");
  standaloneTrace.sampleOverlay = {
    trace: { color: null },
    _cpu: {
      x: new Float32Array([0.05, 0.2, 0.75, 0.95]),
      y: new Float32Array([0.05, 0.8, 0.25, 0.95]),
      xMeta: { scale: 1, offset: 0 }, yMeta: { scale: 1, offset: 0 },
    },
  };
  const standaloneHandle = await attachStandaloneWasmDensity(standaloneDensityView, {
    workerUrl: "/packages/xy-client/dist/wasm-worker.js", wasm: wasmModule, maxArenaBytes: 1024 * 1024, delay: 0,
  });
  const standaloneRevision = standaloneDensityView._scheduleViewRequest(
    { ranges: { x: [0.25, 0.75], y: [0.25, 0.75] } }, { delay: 0 },
  );
  for (let attempt = 0; attempt < 100 && standaloneHandle.diagnostics() === null; attempt++) await nextTask();
  const standaloneDiagnostics = standaloneHandle.diagnostics();
  if (!standaloneDiagnostics || standaloneDiagnostics.sequence !== standaloneRevision
      || standaloneTrace.density.xRange.join(",") !== "0.25,0.75"
      || !standaloneTrace._sampleRebinned) {
    throw new Error(`standalone WASM density retained-sample path failed: ${JSON.stringify({
      standaloneDiagnostics, xRange: standaloneTrace.density.xRange,
      rebinned: standaloneTrace._sampleRebinned,
    })}`);
  }
  standaloneDensityView._scheduleViewRequest({ ranges: { x: [0, 1], y: [0, 1] } }, { delay: 0 });
  await nextTask();
  if (standaloneTrace.density.xRange.join(",") !== "0,1" || standaloneTrace._sampleRebinned) {
    throw new Error("standalone WASM density did not restore the full-data home grid");
  }
  standaloneDensityView.destroy();
  await nextTask();
  if (standaloneDensityView._wasmDensity !== null) {
    throw new Error("destroyed standalone density retained its owned WASM handle");
  }
  standaloneDensityHost.remove();

  foundationStage = "standalone WASM density multi-trace supersession and scales";
  const multiDensityHost = document.createElement("div");
  multiDensityHost.style.cssText = "width:320px;height:240px";
  document.body.append(multiDensityHost);
  const multiDensityView = directDensityFixture(multiDensityHost, null, true);
  // One extra point beyond Rust's 32,768-point checkpoint leaves the first
  // trace in flight, so the next viewport cancels it before its second trace
  // can start. This exercises the grouped attachment, not just one trace.
  const slowX = new Float64Array(32769), slowY = new Float64Array(32769);
  for (let index = 0; index < slowX.length; index++) {
    slowX[index] = 0.1 + (index % 100) / 125;
    slowY[index] = 0.1 + (index % 80) / 100;
  }
  const multiSource = multiDensityView.gpuTraces.filter((trace) => trace.tier === "density");
  multiSource[0].sampleOverlay = { trace: { color: null }, _cpu: { x: slowX, y: slowY, xMeta: { scale: 1, offset: 0 }, yMeta: { scale: 1, offset: 0 } } };
  multiSource[1].sampleOverlay = { trace: { color: null }, _cpu: { x: new Float64Array([10.5, 19.5]), y: new Float64Array([105, 195]), xMeta: { scale: 1, offset: 0 }, yMeta: { scale: 1, offset: 0 } } };
  const multiApplies = [];
  const applyMultiGrid = multiDensityView._applySampleRebinGrid;
  multiDensityView._applySampleRebinGrid = function(trace, grid, ...rest) {
    multiApplies.push({ traceId: trace.trace.id, xRange: grid.xRange, yRange: grid.yRange });
    return applyMultiGrid.call(this, trace, grid, ...rest);
  };
  const multiDensityHandle = await attachStandaloneWasmDensity(multiDensityView, {
    workerUrl: "/packages/xy-client/dist/wasm-worker.js", wasm: wasmModule, maxArenaBytes: 4 * 1024 * 1024, delay: 0,
  });
  const obsoleteMultiRevision = multiDensityView._scheduleViewRequest({
    ranges: { x: [0.1, 0.9], y: [0.15, 0.85], x2: [11, 19], y2: [110, 190] },
  }, { delay: 0 });
  await nextTask();
  const multiRevision = multiDensityView._scheduleViewRequest({
    ranges: { x: [0.2, 0.8], y: [0.3, 0.7], x2: [12, 18], y2: [120, 180] },
  }, { delay: 0 });
  for (let attempt = 0; attempt < 200 && multiDensityHandle.diagnostics()?.traceId !== 1; attempt++) await nextTask();
  const multiTraces = multiDensityView.gpuTraces.filter((trace) => trace.tier === "density");
  if (obsoleteMultiRevision >= multiRevision
      || multiDensityHandle.diagnostics()?.sequence !== multiRevision
      || multiDensityHandle.diagnostics()?.traceId !== 1
      || multiTraces[0]?.density?.xRange.join(",") !== "0.2,0.8"
      || multiTraces[0]?.density?.yRange.join(",") !== "0.3,0.7"
      || multiTraces[1]?.density?.xRange.join(",") !== "12,18"
      || multiTraces[1]?.density?.yRange.join(",") !== "120,180"
      || multiApplies.some((apply) => apply.xRange.join(",") === "0.1,0.9")) {
    throw new Error(`standalone WASM density multi-trace supersession/scales drifted: ${JSON.stringify({
      obsoleteMultiRevision, multiRevision, diagnostics: multiDensityHandle.diagnostics(),
      applies: multiApplies, traces: multiTraces.map((trace) => trace.density),
    })}`);
  }
  await multiDensityHandle.dispose();
  multiDensityView.destroy();
  multiDensityHost.remove();

  foundationStage = "direct WASM ChartView density resource diagnostic";
  const constrainedHost = document.createElement("div");
  constrainedHost.style.cssText = "width:320px;height:240px";
  document.body.append(constrainedHost);
  const constrainedView = directDensityFixture(constrainedHost);
  const constrainedWorker = createXygWasmWorker({
    workerUrl: "/packages/xy-client/dist/wasm-worker.js", wasm: wasmModule, maxArenaBytes: 1024,
  });
  const constrainedHandle = await attachWasmDensity(constrainedView, {
    worker: constrainedWorker,
    input: { traceId: 0, x: new Float64Array([0.25, 0.75]), y: new Float64Array([0.25, 0.75]) }, delay: 0,
  });
  const densityErrors = [];
  constrainedView.root.addEventListener("xy:wasm_density_error", (event) => densityErrors.push(event.detail));
  constrainedHandle.schedule();
  for (let attempt = 0; attempt < 100 && !densityErrors.length; attempt++) await nextTask();
  if (densityErrors.length !== 1 || densityErrors[0]?.code !== "XYG_WASM_RESOURCE_LIMIT"
      || !densityErrors[0]?.diagnostics || constrainedHandle.diagnostics() !== null) {
    throw new Error(`direct WASM density resource diagnostics drifted: ${JSON.stringify(densityErrors)}`);
  }
  await constrainedHandle.dispose();
  constrainedView.destroy();
  await constrainedWorker.dispose();
  constrainedHost.remove();

  foundationStage = "direct WASM ChartView density malformed-output cleanup";
  const malformedDensityHost = document.createElement("div");
  malformedDensityHost.style.cssText = "width:320px;height:240px";
  document.body.append(malformedDensityHost);
  const malformedDensityView = directDensityFixture(malformedDensityHost);
  let malformedDensityWorkerDisposed = 0;
  const malformedDensityWorker = {
    ready: Promise.resolve({}),
    aggregateBin2d(_request, { sequence }) {
      return {
        requestId: 1,
        sequence,
        cancel() {},
        // Simulate a corrupted XYAO after a valid Worker transport response.
        // This exercises the browser-side contract boundary without teaching
        // the fixture WASM module a second aggregate implementation.
        result: Promise.resolve({
          sequence, aggregate: new ArrayBuffer(0), abiVersion: 22, sceneVersion: 20,
          defaultPaletteVersion: 1, defaultPaletteRows: 8,
          defaultPaletteFirstRgba8: 0xffe58739,
          records: 0, styles: 0, copyCount: 1,
          copyBytesLo: 48, copyBytesHi: 0, arenaBytes: 0,
          arenaHighWaterBytes: 48, memoryBytes: 65536,
          memoryHighWaterBytes: 65536,
        }),
      };
    },
    async dispose() { malformedDensityWorkerDisposed++; },
  };
  const malformedDensityHandle = await attachWasmDensity(malformedDensityView, {
    worker: malformedDensityWorker,
    input: { traceId: 0, x: new Float64Array([0.25]), y: new Float64Array([0.75]) },
    workerOwnership: "own", delay: 0,
  });
  const malformedDensityErrors = [];
  malformedDensityView.root.addEventListener("xy:wasm_density_error", (event) => malformedDensityErrors.push(event.detail));
  malformedDensityHandle.schedule();
  for (let attempt = 0; attempt < 100 && !malformedDensityErrors.length; attempt++) await nextTask();
  const malformedDensityTrace = malformedDensityView.gpuTraces.find((trace) => trace.tier === "density");
  if (malformedDensityErrors.length !== 1 || malformedDensityErrors[0]?.code !== "XYG_WASM_MALFORMED_OUTPUT"
      || malformedDensityErrors[0]?.diagnostics?.copyCount !== 1 || malformedDensityHandle.diagnostics() !== null
      || malformedDensityTrace.density.xRange.join(",") !== "0,1") {
    throw new Error(`direct WASM density malformed output retained state: ${JSON.stringify({
      malformedDensityErrors, diagnostics: malformedDensityHandle.diagnostics(), xRange: malformedDensityTrace?.density?.xRange,
    })}`);
  }
  await malformedDensityHandle.dispose();
  if (malformedDensityWorkerDisposed !== 1 || malformedDensityView._wasmDensity !== null) {
    throw new Error("direct WASM density malformed output retained a worker or handle");
  }
  malformedDensityView.destroy();
  malformedDensityHost.remove();

  foundationStage = "Rust dashboard resource plan";
  const sparseDashboard = new Array(1);
  for (const invalid of [
    sparseDashboard,
    [null],
    [{}],
    [{ stableId: 1, derivedBytes: 1n, lastUsed: 1n }],
    [{ stableId: 1n, derivedBytes: 1n, lastUsed: 1n, visible: 1 }],
    [{ stableId: 1n, derivedBytes: 1n, lastUsed: 1n, interacting: "yes" }],
  ]) {
    let refused = false;
    try { encodeWasmDashboardPlan(invalid, 1n); } catch (error) { refused = error instanceof TypeError; }
    if (!refused) throw new Error("dashboard encoder accepted a sparse, nonobject, or coercible resource");
  }
  let invalidBudgetRefused = false;
  try { encodeWasmDashboardPlan([], 1); } catch (error) { invalidBudgetRefused = error instanceof TypeError; }
  if (!invalidBudgetRefused) throw new Error("dashboard encoder accepted a non-bigint budget");
  const dashboardWorker = createXygWasmWorker({
    workerUrl: "/packages/xy-client/dist/wasm-worker.js", wasm: wasmModule, maxArenaBytes: 1024 * 1024,
  });
  await dashboardWorker.ready;
  const dashboardPlan = await planWasmDashboardResources(dashboardWorker, [
    { stableId: 9n, derivedBytes: 40n, lastUsed: 99n },
    { stableId: 4n, derivedBytes: 40n, lastUsed: 1n, visible: true },
    { stableId: 7n, derivedBytes: 40n, lastUsed: 0n, interacting: true },
  ], 80n);
  if (dashboardPlan.retained.join(",") !== "false,true,true"
      || dashboardPlan.retainedBytes !== 80n
      || !Object.isFrozen(dashboardPlan) || !Object.isFrozen(dashboardPlan.retained)) {
    throw new Error(`Rust dashboard priority/byte plan drifted: ${dashboardPlan.retained.join(",")}/${dashboardPlan.retainedBytes}`);
  }
  await dashboardWorker.dispose();

  foundationStage = "automatic dashboard admission concurrency lifecycle";
  let dashboardListener = null, planCalls = 0, inFlightPlans = 0, maxInFlightPlans = 0, appliedPlans = 0;
  const pendingPlans = [];
  const instrumentedWorker = {
    dashboardPlan() {
      planCalls += 1;
      inFlightPlans += 1;
      maxInFlightPlans = Math.max(maxInFlightPlans, inFlightPlans);
      let resolveResult, rejectResult;
      const result = new Promise((resolve, reject) => { resolveResult = resolve; rejectResult = reject; });
      pendingPlans.push({
        resolve() { inFlightPlans -= 1; resolveResult(dashboardPlanResponse()); },
        reject(error) { inFlightPlans -= 1; rejectResult(error); },
      });
      return { result };
    },
  };
  const instrumentedHost = {
    subscribeDashboardResources(listener) {
      dashboardListener = listener;
      return () => { if (dashboardListener === listener) dashboardListener = null; };
    },
    dashboardResourceSnapshot() {
      return Object.freeze({
        revision: 1,
        clients: Object.freeze([{}]),
        resources: Object.freeze([Object.freeze({
          stableId: 1n, derivedBytes: 4n, lastUsed: 1n, visible: true, interacting: false,
        })]),
      });
    },
    applyDashboardResidency(_snapshot, retained) {
      appliedPlans += 1;
      return retained.length === 1 && retained[0] === true;
    },
  };
  const waitForPlanCall = async (count) => {
    for (let turn = 0; turn < 20 && planCalls < count; turn++) await Promise.resolve();
    if (planCalls !== count) throw new Error(`automatic admission expected ${count} plan calls, saw ${planCalls}`);
  };
  const watcher = watchWasmDashboardResourceBudget(instrumentedWorker, instrumentedHost, 4n);
  const coalescedCycle = watcher.settled;
  await waitForPlanCall(1);
  for (let index = 0; index < 8; index++) dashboardListener();
  pendingPlans.shift().resolve();
  await waitForPlanCall(2);
  if (maxInFlightPlans !== 1 || pendingPlans.length !== 1) {
    throw new Error(`automatic admission overlapped or failed to coalesce: ${maxInFlightPlans}/${pendingPlans.length}`);
  }
  pendingPlans.shift().resolve();
  await coalescedCycle;
  if (planCalls !== 2 || appliedPlans !== 2 || inFlightPlans !== 0) {
    throw new Error(`automatic admission follow-up drifted: ${planCalls}/${appliedPlans}/${inFlightPlans}`);
  }
  dashboardListener();
  const disposedCycle = watcher.settled;
  watcher.dispose();
  await disposedCycle;
  await Promise.resolve();
  if (dashboardListener !== null || planCalls !== 2) {
    throw new Error("automatic admission disposal retained or executed queued work");
  }
  const recoveringWatcher = watchWasmDashboardResourceBudget(instrumentedWorker, instrumentedHost, 4n);
  const rejectedCycle = recoveringWatcher.settled;
  await waitForPlanCall(3);
  pendingPlans.shift().reject(new Error("deterministic planner rejection"));
  let sawPlannerRejection = false;
  try { await rejectedCycle; } catch (error) { sawPlannerRejection = error?.message === "deterministic planner rejection"; }
  if (!sawPlannerRejection) throw new Error("automatic admission did not expose planner rejection");
  dashboardListener();
  const recoveredCycle = recoveringWatcher.settled;
  await waitForPlanCall(4);
  pendingPlans.shift().resolve();
  await recoveredCycle;
  if (planCalls !== 4 || appliedPlans !== 3 || maxInFlightPlans !== 1) {
    throw new Error(`automatic admission did not recover: ${planCalls}/${appliedPlans}/${maxInFlightPlans}`);
  }
  recoveringWatcher.dispose();

  const temporalEvents = [];
  const temporalWorker = createXygWasmWorker({
    workerUrl: "/packages/xy-client/dist/wasm-worker.js", wasm: wasmModule, maxArenaBytes: 4096,
  });
  const temporal = await XygWasmTemporalController.create(temporalWorker, {
    instanceId: 7n,
    groupId: 9n,
    domain: [0n, 100n],
    cursor: 10n,
    window: 20n,
    step: 5n,
    reducedMotion: true,
    onEvent: (event) => temporalEvents.push(event),
  });
  const scrubber = document.body.appendChild(document.createElement("div"));
  scrubber.setAttribute("role", "button");
  scrubber.setAttribute("tabindex", "3");
  const firstCleanup = temporal.bindScrubber(scrubber);
  const reboundScrubber = document.body.appendChild(document.createElement("div"));
  temporal.bindScrubber(reboundScrubber);
  firstCleanup();
  if (reboundScrubber.getAttribute("role") !== "slider") {
    throw new Error("stale temporal cleanup detached the newer scrubber");
  }
  reboundScrubber.remove();
  temporal.bindScrubber(scrubber);
  await temporal.setSelection([(1n << 64n) - 1n, 7n, 7n, 0n]);
  let rejectedSnapshotMutation = 0;
  for (const mutate of [
    () => { temporal.state.cursor = 99n; },
    () => { temporal.state.selection[0] = 99n; },
    () => { temporalEvents.at(-1).selection.push(99n); },
  ]) {
    try { mutate(); } catch (error) {
      if (error instanceof TypeError) rejectedSnapshotMutation += 1;
    }
  }
  if (rejectedSnapshotMutation !== 3
      || temporal.state.cursor !== 10n
      || temporal.state.selection.join(",") !== `0,7,${(1n << 64n) - 1n}`) {
    throw new Error("browser temporal snapshots allowed host mutation after Rust canonicalization");
  }
  let rejectedSelectionBound = false;
  try {
    temporal.setSelection(Array(10_001).fill(1n));
  } catch (error) {
    rejectedSelectionBound = error instanceof RangeError;
  }
  if (!rejectedSelectionBound) throw new Error("browser temporal selection bound did not fail before allocation");
  await temporal.setCursor(25n);
  if (temporal.state.cursor !== 25n
      || temporal.state.selection.join(",") !== `0,7,${(1n << 64n) - 1n}`
      || temporalEvents.length < 1
      || scrubber.getAttribute("aria-valuenow") !== "25") {
    throw new Error("direct-browser temporal state, coordination, or ARIA did not round-trip");
  }
  scrubber.dispatchEvent(new KeyboardEvent("keydown", { key: "ArrowRight", bubbles: true }));
  scrubber.dispatchEvent(new KeyboardEvent("keydown", { key: "ArrowLeft", bubbles: true }));
  await temporal.whenIdle();
  if (temporal.state.cursor !== 25n) {
    throw new Error("rapid temporal arrow actions interleaved direction and step commands");
  }
  await temporal.play();
  if (temporal.state.playing) throw new Error("reduced motion allowed automatic temporal playback");
  await temporal.setReducedMotion(false);
  scrubber.dispatchEvent(new KeyboardEvent("keydown", { key: " ", bubbles: true }));
  scrubber.dispatchEvent(new KeyboardEvent("keydown", { key: " ", bubbles: true }));
  await temporal.whenIdle();
  if (temporal.state.playing) throw new Error("rapid temporal Space keys used stale playback state");
  await temporal.setDirection(1);
  await temporal.play();
  await temporal.tick(10n);
  await temporal.pause();
  if (temporal.state.cursor <= 25n || temporal.state.playing) {
    throw new Error("browser temporal playback did not use the Rust state machine");
  }
  const peerWorker = createXygWasmWorker({
    workerUrl: "/packages/xy-client/dist/wasm-worker.js", wasm: wasmModule, maxArenaBytes: 4096,
  });
  const peer = await XygWasmTemporalController.create(
    peerWorker,
    { instanceId: 8n, groupId: 9n, domain: [0n, 100n] },
  );
  await peer.applyEvent(temporalEvents.at(-1));
  if (peer.state.cursor !== temporalEvents.at(-1).cursor) {
    throw new Error("cross-worker temporal coordination lost exact bigint state");
  }
  if (peer.state.selection.join(",") !== temporal.state.selection.join(",")) {
    throw new Error("cross-worker temporal selection was not atomic or exact");
  }
  await rejected(peer.applyEvent(temporalEvents.at(-1)), "XYG_WASM_STALE_REVISION", 10);
  await rejected(temporal.applyEvent(temporalEvents.at(-1)), "XYG_WASM_SELF_ECHO", 11);
  let rejectedOverflow = false;
  try {
    temporal.setCursor(1n << 63n);
  } catch (error) {
    rejectedOverflow = error instanceof RangeError;
  }
  if (!rejectedOverflow) throw new Error("browser temporal i64 overflow did not fail closed");

  let reportedErrors = 0;
  let unhandledErrors = 0;
  const unhandled = (event) => { unhandledErrors += 1; event.preventDefault(); };
  window.addEventListener("unhandledrejection", unhandled);
  for (const onError of [
    () => { reportedErrors += 1; throw new Error("sync handler failure"); },
    async () => { reportedErrors += 1; throw new Error("async handler failure"); },
  ]) {
    const errorWorker = createXygWasmWorker({
      workerUrl: "/packages/xy-client/dist/wasm-worker.js", wasm: wasmModule, maxArenaBytes: 4096,
    });
    const errorController = await XygWasmTemporalController.create(errorWorker, {
      instanceId: BigInt(20 + reportedErrors), domain: [0n, 10n], onError,
    });
    const errorScrubber = document.body.appendChild(document.createElement("div"));
    errorController.bindScrubber(errorScrubber);
    await errorWorker.dispose();
    errorScrubber.dispatchEvent(new KeyboardEvent("keydown", { key: "Home", bubbles: true }));
    await errorController.whenIdle().catch(() => {});
    errorController.unbindScrubber();
    errorScrubber.remove();
  }
  window.removeEventListener("unhandledrejection", unhandled);
  if (reportedErrors !== 2 || unhandledErrors !== 0) {
    throw new Error("temporal onError containment allowed an unhandled rejection");
  }
  const disposeA = temporal.dispose();
  const disposeB = temporal.dispose();
  if (disposeA !== disposeB) throw new Error("concurrent temporal disposal did not share one promise");
  await Promise.all([disposeA, disposeB]);
  if (scrubber.getAttribute("role") !== "button" || scrubber.getAttribute("tabindex") !== "3"
      || scrubber.hasAttribute("aria-valuenow")) {
    throw new Error("temporal scrubber disposal did not restore prior DOM attributes");
  }
  await peer.dispose();
  await temporalWorker.dispose();
  await peerWorker.dispose();
  scrubber.remove();

  const temporalGraphWorker = createXygWasmWorker({
    workerUrl: "/packages/xy-client/dist/wasm-worker.js",
    wasm: wasmModule,
    maxArenaBytes: 1024 * 1024,
  });
  const uuidBytes = (...values) => Uint8Array.from(values.flatMap((value) => Array(16).fill(value)));
  const temporalGraph = await XygWasmTemporalGraph.create(temporalGraphWorker, {
    nodeIds: uuidBytes(1, 2, 3), edgeIds: uuidBytes(11, 12),
    sourceIds: uuidBytes(1, 2), targetIds: uuidBytes(2, 3),
    nodeValidFrom: { values: new BigInt64Array([0n, 10n, 20n]), validity: new Uint8Array([1, 1, 1]) },
    nodeValidTo: { values: new BigInt64Array([30n, 20n, 40n]), validity: new Uint8Array([1, 1, 1]) },
  });
  const temporalFrame = await temporalGraph.frame({ revision: 1n, cursor: 20n, range: [20n, 21n], budget: 12n });
  if (temporalFrame.revision !== 1n || temporalFrame.nodeVisibility.join(",") !== "1,0,1"
      || temporalFrame.edgeVisibility.join(",") !== "0,0" || temporalFrame.visibleNodeIds.byteLength !== 32) {
    throw new Error("direct-browser temporal graph frame lost Rust identity membership");
  }
  const rapid = await Promise.allSettled([
    temporalGraph.frame({ revision: 2n, cursor: 15n, range: [15n, 16n], budget: 12n }),
    temporalGraph.frame({ revision: 3n, cursor: 25n, range: [25n, 26n], budget: 12n }),
  ]);
  if (rapid[0].status !== "rejected" || rapid[1].status !== "fulfilled"
      || rapid[1].value.revision !== 3n) {
    throw new Error("rapid temporal graph frames applied a stale browser reply");
  }
  const temporalLayout = await temporalGraph.frameAndLayout({
    revision: 4n, cursor: 15n, range: [15n, 16n], budget: 12n,
    layout: { totalSteps: 17, seed: 9n },
  });
  if (temporalLayout.frame.sources.join(",") !== "0"
      || temporalLayout.frame.targets.join(",") !== "1"
      || temporalLayout.layout.revision !== 4
      || temporalLayout.layout.x.length !== 2
      || temporalLayout.layout.phase !== "complete") {
    throw new Error("temporal graph did not feed Rust-remapped visible topology into Rust CoSE");
  }
  const checkpointWithin = (promise, label) => new Promise((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error(`${label} did not emit a progressive checkpoint`)), 5000);
    promise.then((value) => { clearTimeout(timer); resolve(value); }, (error) => { clearTimeout(timer); reject(error); });
  });
  let superseded = false, staleLayoutUpdates = 0, resolveOldStarted;
  const oldStarted = new Promise((resolve) => { resolveOldStarted = resolve; });
  const oldLayout = temporalGraph.frameAndLayout({
    revision: 5n, cursor: 15n, range: [15n, 16n], budget: 12n,
    layout: { totalSteps: 100000, seed: 10n },
    onUpdate: () => { if (superseded) staleLayoutUpdates += 1; else resolveOldStarted(); },
  });
  await checkpointWithin(oldStarted, "superseded temporal layout");
  superseded = true;
  const newLayout = temporalGraph.frameAndLayout({
    revision: 6n, cursor: 25n, range: [25n, 26n], budget: 12n,
    layout: { totalSteps: 17, seed: 11n },
  });
  const supersession = await Promise.allSettled([oldLayout, newLayout]);
  if (supersession[0].status !== "rejected" || supersession[1].status !== "fulfilled"
      || supersession[1].value.layout.revision !== 6 || staleLayoutUpdates !== 0) {
    throw new Error("new temporal frame did not cancel and suppress the stale Rust layout");
  }
  let disposedUpdates = 0, resolveDisposedStarted;
  const disposedStarted = new Promise((resolve) => { resolveDisposedStarted = resolve; });
  const disposedLayout = temporalGraph.frameAndLayout({
    revision: 7n, cursor: 15n, range: [15n, 16n], budget: 12n,
    layout: { totalSteps: 100000, seed: 12n },
    onUpdate: () => { disposedUpdates += 1; resolveDisposedStarted(); },
  });
  await checkpointWithin(disposedStarted, "disposed temporal layout");
  temporalGraph.dispose();
  const updatesAtDispose = disposedUpdates;
  const disposedResult = await Promise.allSettled([disposedLayout]);
  await new Promise((resolve) => setTimeout(resolve, 0));
  if (disposedResult[0].status !== "rejected" || disposedUpdates !== updatesAtDispose) {
    throw new Error("disposed temporal graph accepted a late Rust layout result or update");
  }
  await temporalGraphWorker.dispose();

  const canonical = canonicalSceneV9();
  const transferred = canonical.buffer;
  const valid = await worker.validateScene(transferred, { sequence: 10 }).result;
  if (transferred.byteLength !== 0) throw new Error("scene buffer was not transferred");
  if (valid.records !== 1 || valid.styles !== 1 || valid.copyCount !== 1) {
    throw new Error(`unexpected diagnostics ${JSON.stringify(valid)}`);
  }
  if (valid.copyBytesLo !== 480 || valid.copyBytesHi !== 0 || valid.arenaBytes !== 0) {
    throw new Error(`unexpected copy or arena diagnostics ${JSON.stringify(valid)}`);
  }

  const paint = await worker.prepareScene(canonicalSceneV9(), { sequence: 11 }).result;
  if (!(paint.painter instanceof ArrayBuffer) || paint.painter.byteLength < 288) {
    throw new Error("Rust Scene paint lowering did not return a transferable display list");
  }
  const host = document.body.appendChild(document.createElement("div"));
  const rendered = await renderWasmScene({ el: host, scene: canonicalSceneV9(), worker, transfer: false });
  if (!host.querySelector("canvas") || rendered.gpuTraces.length < 1) {
    throw new Error("public WASM Scene API did not hydrate the existing painter");
  }
  await new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve)));
  const labels = [...host.querySelectorAll('[data-xy-label-kind="tick"]')].map((node) => node.textContent);
  if (labels.length < 6 || !labels.includes("0.0") || !labels.includes("0.5") || !labels.includes("1.0")) {
    throw new Error(`Rust-authored Scene v12 chrome labels were not painted: ${JSON.stringify(labels)}`);
  }
  if (host.querySelectorAll('[data-xy-axis-side="bottom"], [data-xy-axis-side="left"]').length < 2) {
    throw new Error("Rust-authored Scene v12 axis chrome was not painted");
  }
  if (rendered.sceneStableId(0, 0) !== 7n) throw new Error("canonical stable id was not preserved through painter hydration");
  rendered.destroy();
  host.remove();

  // `XYAD` encloses `XYAT`, which carries only data coordinates and plain text. The strict CSP page
  // below proves the real worker/WASM path projects it through the decoded
  // Scene rather than evaluating or inserting host markup.
  // Keep the fixed 12px/inset box wholly inside this 100px test viewport;
  // overflow remains a fail-closed Rust geometry error.
  const xyatText = "note";
  const xyatTextBytes = new TextEncoder().encode(xyatText);
  const xyat = new Uint8Array(12 + 40 + xyatTextBytes.length);
  xyat.set([0x58, 0x59, 0x41, 0x54]); // XYAT v3
  const xyatView = new DataView(xyat.buffer);
  xyatView.setUint32(4, 3, true); xyatView.setUint32(8, 1, true);
  xyatView.setFloat64(12, 0.5, true); xyatView.setFloat64(20, 0.5, true);
  xyat.set([1, 2, 3, 255], 28); xyat.set([255, 255, 255, 255], 32);
  xyat.set([18, 52, 86, 255], 36); xyatView.setFloat64(40, 1.5, true);
  xyatView.setUint32(48, xyatTextBytes.length, true); xyat.set(xyatTextBytes, 52);
  const xyad = new Uint8Array(20 + xyat.length);
  xyad.set([0x58, 0x59, 0x41, 0x44]); // XYAD
  const xyadView = new DataView(xyad.buffer);
  xyadView.setUint32(4, 1, true); xyadView.setUint32(8, xyat.length, true);
  xyad.set(xyat, 20);
  const textWorker = createXygWasmWorker({
    workerUrl: "/packages/xy-client/dist/wasm-worker.js", wasm: wasmModule, maxArenaBytes: 8192,
  });
  await textWorker.ready;
  const textPaint = await textWorker.prepareSceneAnnotations(canonicalSceneV9(), xyad, { transfer: false }).result;
  const textHost = document.body.appendChild(document.createElement("div"));
  const textView = hydrateWasmPainter(textHost, textPaint);
  await new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve)));
  const textNote = textHost.querySelector('[role="note"]');
  const textBox = textHost.querySelector('[data-xy-slot="annotation_label_box"][aria-hidden="true"]');
  if (textNote?.textContent !== xyatText || textNote.querySelector("*") !== null || !textBox
      || getComputedStyle(textBox).backgroundColor !== "rgb(255, 255, 255)" || getComputedStyle(textBox).borderTopWidth === "0px" || getComputedStyle(textBox).borderTopColor !== "rgb(18, 52, 86)") {
    throw new Error("strict-CSP direct WASM XYAT v2 did not preserve Rust-owned text-box semantics");
  }
  textView.destroy(); textHost.remove(); await textWorker.dispose();

  // `XYAL` v3 can supply one literal label background, but not placement or
  // box geometry. Rust resolves the box for this existing marker annotation.
  foundationStage = "strict-CSP direct WASM XYAL attached-label background";
  const attachedText = "box";
  const attachedTextBytes = new TextEncoder().encode(attachedText);
  const xyalV3 = new Uint8Array(12 + 32 + attachedTextBytes.length);
  xyalV3.set([0x58, 0x59, 0x41, 0x4c]); // XYAL v4
  const xyalV3View = new DataView(xyalV3.buffer);
  xyalV3View.setUint32(4, 4, true); xyalV3View.setUint32(8, 1, true);
  xyalV3View.setBigUint64(12, 0x5859030000000002n, true);
  xyalV3.set([102, 112, 133, 255], 20); // resolved label paint
  xyalV3.set([255, 255, 255, 255], 24); // literal fill; no box coordinates
  xyalV3.set([18, 52, 86, 255], 28); xyalV3View.setFloat64(32, 1.5, true);
  xyalV3View.setUint32(40, attachedTextBytes.length, true); xyalV3.set(attachedTextBytes, 44);
  const attachedTextEmpty = new Uint8Array(12), attachedArrowEmpty = new Uint8Array(12);
  attachedTextEmpty.set([0x58, 0x59, 0x41, 0x54]); // XYAT v1
  attachedArrowEmpty.set([0x58, 0x59, 0x41, 0x52]); // XYAR v1
  new DataView(attachedTextEmpty.buffer).setUint32(4, 1, true);
  new DataView(attachedArrowEmpty.buffer).setUint32(4, 1, true);
  const attachedCalloutEmpty = new Uint8Array(12);
  attachedCalloutEmpty.set([0x58, 0x59, 0x41, 0x43]); // XYAC v1
  new DataView(attachedCalloutEmpty.buffer).setUint32(4, 1, true);
  const attachedEnvelope = new Uint8Array(24 + attachedTextEmpty.length + xyalV3.length + attachedArrowEmpty.length + attachedCalloutEmpty.length);
  attachedEnvelope.set([0x58, 0x59, 0x41, 0x44]); // XYAD v2
  const attachedEnvelopeView = new DataView(attachedEnvelope.buffer);
  attachedEnvelopeView.setUint32(4, 2, true); attachedEnvelopeView.setUint32(8, attachedTextEmpty.length, true);
  attachedEnvelopeView.setUint32(12, xyalV3.length, true); attachedEnvelopeView.setUint32(16, attachedArrowEmpty.length, true);
  attachedEnvelopeView.setUint32(20, attachedCalloutEmpty.length, true);
  let attachedAt = 24; for (const part of [attachedTextEmpty, xyalV3, attachedArrowEmpty, attachedCalloutEmpty]) { attachedEnvelope.set(part, attachedAt); attachedAt += part.length; }
  const attachedWorker = createXygWasmWorker({
    workerUrl: "/packages/xy-client/dist/wasm-worker.js", wasm: wasmModule, maxArenaBytes: 1024 * 1024,
  });
  await attachedWorker.ready;
  const attachedPaint = await attachedWorker.prepareSceneAnnotations(primaryAnnotationSceneV10(), attachedEnvelope, { transfer: false }).result;
  const attachedHost = document.body.appendChild(document.createElement("div"));
  const attachedView = hydrateWasmPainter(attachedHost, attachedPaint);
  await new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve)));
  const attachedNote = [...attachedHost.querySelectorAll('[data-xy-slot="annotation_label"][role="note"]')]
    .find((node) => node.textContent === attachedText);
  const attachedBox = attachedHost.querySelector('[data-xy-slot="annotation_label_box"][aria-hidden="true"]');
  if (attachedNote?.textContent !== attachedText || !attachedBox
      || getComputedStyle(attachedBox).backgroundColor !== "rgb(255, 255, 255)" || getComputedStyle(attachedBox).borderTopWidth === "0px" || getComputedStyle(attachedBox).borderTopColor !== "rgb(18, 52, 86)") {
    throw new Error("strict-CSP direct WASM XYAL v3 did not preserve Rust-owned attached-label box semantics");
  }
  attachedView.destroy(); attachedHost.remove(); await attachedWorker.dispose();

  // `XYAC` v2 carries only a Cartesian data anchor, bounded pixel offset,
  // literal paint, fixed leader width, anchor code, UTF-8 text, and optional
  // label fill. Rust must derive the leader/head, stable identity, label box,
  // and browser-facing geometry; this page never supplies resolved pixels.
  const calloutText = "Rust";
  foundationStage = "strict-CSP direct WASM XYAC callout";
  const calloutTextBytes = new TextEncoder().encode(calloutText);
  const xyatEmpty = new Uint8Array(12), xyalEmpty = new Uint8Array(12), xyarEmpty = new Uint8Array(12);
  xyatEmpty.set([0x58, 0x59, 0x41, 0x54]); // XYAT v1
  xyalEmpty.set([0x58, 0x59, 0x41, 0x4c]); // XYAL v2
  xyarEmpty.set([0x58, 0x59, 0x41, 0x52]); // XYAR v1
  new DataView(xyatEmpty.buffer).setUint32(4, 1, true);
  new DataView(xyalEmpty.buffer).setUint32(4, 2, true);
  new DataView(xyarEmpty.buffer).setUint32(4, 1, true);
  const xyac = new Uint8Array(12 + 76 + calloutTextBytes.length);
  xyac.set([0x58, 0x59, 0x41, 0x43]); // XYAC v3
  const xyacView = new DataView(xyac.buffer);
  xyacView.setUint32(4, 3, true); xyacView.setUint32(8, 1, true);
  xyacView.setFloat64(12, 0.5, true); xyacView.setFloat64(20, 0.5, true);
  xyacView.setFloat64(28, -12, true); xyacView.setFloat64(36, -18, true);
  xyac.set([52, 64, 84, 255], 44); xyacView.setFloat64(48, 1, true); xyacView.setFloat64(56, 1.5, true);
  xyac[64] = 0; // start anchor; 65..67 remain required zero bytes.
  xyacView.setUint32(68, calloutTextBytes.length, true); xyac.set([255, 255, 255, 255], 72);
  xyac.set([18, 52, 86, 255], 76); xyacView.setFloat64(80, 1.5, true);
  xyac.set(calloutTextBytes, 88);
  const calloutEnvelope = new Uint8Array(24 + xyatEmpty.length + xyalEmpty.length + xyarEmpty.length + xyac.length);
  calloutEnvelope.set([0x58, 0x59, 0x41, 0x44]); // XYAD v2
  const calloutEnvelopeView = new DataView(calloutEnvelope.buffer);
  calloutEnvelopeView.setUint32(4, 2, true); calloutEnvelopeView.setUint32(8, xyatEmpty.length, true);
  calloutEnvelopeView.setUint32(12, xyalEmpty.length, true); calloutEnvelopeView.setUint32(16, xyarEmpty.length, true);
  calloutEnvelopeView.setUint32(20, xyac.length, true);
  let calloutAt = 24; for (const part of [xyatEmpty, xyalEmpty, xyarEmpty, xyac]) { calloutEnvelope.set(part, calloutAt); calloutAt += part.length; }
  const calloutWorker = createXygWasmWorker({
    workerUrl: "/packages/xy-client/dist/wasm-worker.js", wasm: wasmModule, maxArenaBytes: 4096,
  });
  await calloutWorker.ready;
  const calloutPaint = await calloutWorker.prepareSceneAnnotations(canonicalSceneV9(), calloutEnvelope, { transfer: false }).result;
  const calloutHost = document.body.appendChild(document.createElement("div"));
  const calloutView = hydrateWasmPainter(calloutHost, calloutPaint);
  await new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve)));
  const calloutNotes = [...calloutHost.querySelectorAll('[data-xy-slot="annotation_label"][role="note"]')];
  const calloutNote = calloutNotes.find((node) => node.textContent === calloutText);
  const calloutBox = calloutHost.querySelector('[data-xy-slot="annotation_label_box"][aria-hidden="true"]');
  if (calloutNote?.textContent !== calloutText || !calloutBox
      || getComputedStyle(calloutBox).backgroundColor !== "rgb(255, 255, 255)" || getComputedStyle(calloutBox).borderTopWidth === "0px" || getComputedStyle(calloutBox).borderTopColor !== "rgb(18, 52, 86)"
      || calloutHost.querySelectorAll('[role="note"]').length !== 2) {
    throw new Error("strict-CSP direct WASM XYAC callout did not preserve Rust-owned label semantics");
  }
  calloutView.destroy(); calloutHost.remove(); await calloutWorker.dispose();

  const annotationWorker = createXygWasmWorker({
    workerUrl: "/packages/xy-client/dist/wasm-worker.js",
    wasm: wasmModule,
    maxArenaBytes: 4096,
  });
  await annotationWorker.ready;
  const annotationHost = document.body.appendChild(document.createElement("div"));
  const annotationView = await renderWasmScene({
    el: annotationHost,
    scene: primaryAnnotationSceneV10(),
    worker: annotationWorker,
    transfer: false,
  });
  await new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve)));
  const annotationNotes = [...annotationHost.querySelectorAll('[role="note"]')]
    .map((node) => node.textContent);
  if (annotationView.gpuTraces.length !== 0
      || annotationNotes.join("|") !== "Vertical reference rule|Vertical reference band|Reference marker|Reference marker") {
    throw new Error(`Rust-authored primary annotations were not painted/accessibly exposed: ${JSON.stringify(annotationNotes)}`);
  }
  annotationView.destroy();
  annotationHost.remove();
  await annotationWorker.dispose();

  const authoredWorker = createXygWasmWorker({
    workerUrl: "/packages/xy-client/dist/wasm-worker.js",
    wasm: wasmModule,
    maxArenaBytes: 1024 * 1024,
  });
  await authoredWorker.ready;
  const authoredHost = document.body.appendChild(document.createElement("div"));
  const authored = await renderWasmScene({
    el: authoredHost,
    scene: canonicalSceneV9({ authored: true, legend: true }),
    worker: authoredWorker,
    transfer: false,
  });
  await new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve)));
  if (!authoredHost.querySelector('[data-xy-axis-side="top"]')) {
    throw new Error("Rust-authored high-side axis was not consumed by the browser painter");
  }
  if (!authoredHost.querySelector('[data-xy-tick-kind="minor"]')) {
    throw new Error("Rust-authored minor tick was not consumed by the browser painter");
  }
  if (![...authoredHost.querySelectorAll('[data-xy-label-kind="tick"]')].some((node) => node.textContent === "zero")) {
    throw new Error("Rust-authored tick-label strings were not consumed by the browser painter");
  }
  const authoredTitle = authoredHost.querySelector('[data-xy-slot="title"]');
  if (authoredTitle?.textContent !== "Authored Cartesian chrome") {
    throw new Error("Rust-authored figure title was not consumed by the browser DOM");
  }
  const authoredTitleStyle = getComputedStyle(authoredTitle);
  if (authoredTitleStyle.color !== "rgb(211, 47, 47)" || authoredTitleStyle.fontSize !== "19px") {
    throw new Error(`Rust-authored title paint was not consumed by the browser DOM: ${authoredTitleStyle.color}/${authoredTitleStyle.fontSize}`);
  }
  const axisTitles = [...authoredHost.querySelectorAll('[data-xy-label-kind="label"]')]
    .map((node) => node.textContent);
  if (!axisTitles.includes("Horizontal measure") || !axisTitles.includes("Vertical measure")) {
    throw new Error(`Rust-authored axis titles were not consumed by the browser DOM: ${JSON.stringify(axisTitles)}`);
  }
  const legendRow = authoredHost.querySelector('[data-xy-slot="legend_item"]');
  const legendTitle = authoredHost.querySelector('[data-xy-slot="legend_title"]');
  const legendLabel = authoredHost.querySelector('[data-xy-slot="legend_label"]');
  if (legendRow?.getAttribute("aria-label") !== "observed" || !legendTitle
      || getComputedStyle(legendTitle).fontSize !== "15px"
      || getComputedStyle(legendLabel).fontSize !== "13px"
      || getComputedStyle(legendLabel).color !== "rgb(126, 34, 206)") {
    throw new Error("Rust-authored primary legend was not exposed through browser DOM/accessibility");
  }
  const authoredRegion = authoredHost.querySelector('.xy[role="region"]');
  if (authoredRegion?.getAttribute("aria-label") !== "Chart: Authored Cartesian chrome"
      || !authoredRegion.textContent.includes("X axis (Horizontal measure)")
      || !authoredRegion.textContent.includes("Y axis (Vertical measure)")) {
    throw new Error("Rust-authored title and axis labels were not exposed to accessibility text");
  }
  const symbolHost = document.body.appendChild(document.createElement("div"));
  const symbolWorker = createXygWasmWorker({
    workerUrl: "/packages/xy-client/dist/wasm-worker.js",
    wasm: wasmModule,
    maxArenaBytes: 64 * 1024,
  });
  await symbolWorker.ready;
  const symbolView = await renderWasmScene({
    el: symbolHost,
    scene: canonicalSceneV9({ legendSymbols: Array.from({ length: 19 }, (_, index) => index) }),
    worker: symbolWorker,
    transfer: false,
  });
  const symbolRows = [...symbolHost.querySelectorAll('[data-xy-slot="legend_item"]')];
  if (symbolRows.length !== 19) throw new Error(`Rust symbol legend emitted ${symbolRows.length} rows`);
  symbolRows.forEach((row, symbol) => {
    const swatch = row.firstElementChild;
    const expectedTag = [0, 12].includes(symbol) ? "circle" : [1, 13].includes(symbol) ? "rect" : "path";
    if (swatch?.tagName.toLowerCase() !== expectedTag) throw new Error(`symbol ${symbol} projected as ${swatch?.tagName}, expected ${expectedTag}`);
    if (expectedTag === "path" && !swatch.getAttribute("d")) throw new Error(`symbol ${symbol} lost Rust path geometry`);
    const geometryNames = expectedTag === "circle" ? ["cx", "cy", "r"] : expectedTag === "rect" ? ["x", "y", "width", "height"] : [];
    if (geometryNames.some((name) => {
      const value = swatch.getAttribute(name);
      return value === null || !Number.isFinite(Number(value));
    })) throw new Error(`symbol ${symbol} has invalid literal geometry`);
    const expectedFill = symbol >= 15 ? "none" : "rgba(37 99 235 / 1)";
    if (swatch.getAttribute("fill") !== expectedFill) throw new Error(`symbol ${symbol} fill policy drifted: ${swatch.getAttribute("fill")}`);
  });
  const negativeStroke = await symbolWorker.prepareScene(
    canonicalSceneV9({ legendSymbols: [0] }), { sequence: 999, transfer: false },
  ).result;
  const malformedPainter = negativeStroke.painter.slice(0), malformedBytes = new Uint8Array(malformedPainter);
  const geometryOffset = malformedBytes.findIndex((_, index) =>
    String.fromCharCode(...malformedBytes.subarray(index, index + 4)) === "XYRG");
  if (geometryOffset < 0) throw new Error("Rust painter legend geometry trailer is missing");
  new DataView(malformedPainter).setFloat32(geometryOffset + 32 + 32, -1, true);
  const malformedHost = document.body.appendChild(document.createElement("div"));
  try {
    hydrateWasmPainter(malformedHost, { ...negativeStroke, painter: malformedPainter });
    throw new Error("negative legend swatch stroke width was accepted");
  } catch (error) {
    if (!(error instanceof XygWasmError) || error.code !== "XYG_WASM_MALFORMED_OUTPUT") throw error;
  }
  malformedHost.remove();
  const overlappingPainter = negativeStroke.painter.slice(0), overlappingBytes = new Uint8Array(overlappingPainter);
  const legendOffset = overlappingBytes.findIndex((_, index) =>
    String.fromCharCode(...overlappingBytes.subarray(index, index + 4)) === "XYLG");
  const overlappingGeometryOffset = overlappingBytes.findIndex((_, index) =>
    String.fromCharCode(...overlappingBytes.subarray(index, index + 4)) === "XYRG");
  if (legendOffset < 0 || overlappingGeometryOffset < 0) throw new Error("Rust painter legend payload is incomplete");
  const legendTextOffset = legendOffset + 48 + 24;
  new DataView(overlappingPainter).setUint32(legendOffset + 48 + 12, overlappingGeometryOffset - legendTextOffset + 1, true);
  const overlappingHost = document.body.appendChild(document.createElement("div"));
  try {
    hydrateWasmPainter(overlappingHost, { ...negativeStroke, painter: overlappingPainter });
    throw new Error("legend label overlapping XYRG geometry was accepted");
  } catch (error) {
    if (!(error instanceof XygWasmError) || error.code !== "XYG_WASM_MALFORMED_OUTPUT") throw error;
  }
  overlappingHost.remove();
  symbolView.destroy(); await symbolWorker.dispose(); symbolHost.remove();
  authored.destroy();
  authoredHost.remove();
  await authoredWorker.dispose();

  // This byte-exact fixture originates from the public Python Figure builder
  // (see the paired fixture test). It carries the full currently supported
  // authored Cartesian chrome subset through the real strict-CSP Worker.
  foundationStage = "strict-CSP full authored Cartesian Scene chrome";
  const authoredFixture = await (await fetch("/tests/fixtures/authored_scene_v20.json")).json();
  if (authoredFixture.schema !== "xyg-authored-scene-v25-fixture-v1") {
    throw new Error(`unexpected authored Scene fixture schema: ${authoredFixture.schema}`);
  }
  const authoredScene = Uint8Array.from(atob(authoredFixture.scene_base64), (byte) => byte.charCodeAt(0));
  const fullChromeWorker = createXygWasmWorker({
    workerUrl: "/packages/xy-client/dist/wasm-worker.js", wasm: wasmModule, maxArenaBytes: 1024 * 1024,
  });
  await fullChromeWorker.ready;
  const fullChromeHost = document.body.appendChild(document.createElement("div"));
  const fullChrome = await renderWasmScene({
    el: fullChromeHost, scene: authoredScene, worker: fullChromeWorker, transfer: false,
  });
  await new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve)));
  const fullChromeRoot = fullChromeHost.querySelector(".xy[role='region']");
  const fullChromeSurface = fullChromeHost.firstElementChild;
  const fullChromeText = fullChromeRoot?.textContent ?? "";
  const fullChromeAxisCount = fullChromeHost.querySelectorAll(
    '[data-xy-axis-side="top"], [data-xy-axis-side="right"]',
  ).length;
  const fullChromeLegend = fullChromeHost.querySelector('[data-xy-slot="legend"][role="list"]');
  const fullChromeLegendRows = [...fullChromeHost.querySelectorAll(
    '[data-xy-slot="legend_item"][role="listitem"]',
  )];
  const fullChromeColorbarTicks = fullChromeHost.querySelectorAll('[data-xy-slot="colorbar_tick"]');
  const fullChromeColorbarMinors = fullChromeHost.querySelectorAll('[data-xy-slot="colorbar_minor_tick"]');
  const fullChromeCallout = [...fullChromeHost.querySelectorAll(
    '[data-xy-slot="annotation_label"][role="note"]',
  )].find((node) => node.textContent === "representative callout");
  const fullChromeCalloutBox = fullChromeHost.querySelector(
    '[data-xy-slot="annotation_label_box"][aria-hidden="true"]',
  );
  const fullChromeStyle = fullChromeSurface ? getComputedStyle(fullChromeSurface) : null;
  if (fullChromeAxisCount < 2
      || !fullChromeLegend
      || fullChromeLegendRows.length !== 2
      || fullChromeLegendRows[0].getAttribute("aria-label") !== "observations"
      || fullChromeLegendRows[1].getAttribute("aria-label") !== "reference"
      || fullChromeColorbarTicks.length !== 3
      || fullChromeColorbarMinors.length !== 8
      || !fullChromeText.includes("Intensity")
      || !fullChromeText.includes("Fraction")
      || !fullChromeText.includes("Signal")
      || fullChromeCallout?.textContent !== "representative callout"
      || !fullChromeCalloutBox
      || fullChromeStyle?.backgroundColor !== "rgb(240, 248, 255)"
      || fullChromeStyle?.getPropertyValue("--chart-bg").trim() !== "rgba(248 250 252 / 1)"
      || getComputedStyle(fullChromeCalloutBox).backgroundColor !== "rgb(255, 255, 255)") {
    throw new Error(`strict-CSP full authored Scene chrome lost structural or perceptual parity: ${JSON.stringify({
      axes: fullChromeAxisCount,
      legend: fullChromeLegendRows.map((row) => row.getAttribute("aria-label")),
      colorbarTicks: fullChromeColorbarTicks.length,
      colorbarMinors: fullChromeColorbarMinors.length,
      text: fullChromeText,
      rootBackground: fullChromeStyle?.backgroundColor,
      plotBackground: fullChromeStyle?.getPropertyValue("--chart-bg").trim(),
      calloutBackground: fullChromeCalloutBox && getComputedStyle(fullChromeCalloutBox).backgroundColor,
    })}`);
  }
  fullChrome.destroy(); fullChromeHost.remove(); await fullChromeWorker.dispose();

  const fragmentedWorker = createXygWasmWorker({
    workerUrl: "/packages/xy-client/dist/wasm-worker.js",
    wasm: wasmModule,
    maxArenaBytes: 1024 * 1024,
  });
  await fragmentedWorker.ready;
  const fragmentedHost = document.body.appendChild(document.createElement("div"));
  const fragmentedError = await rejected(
    renderWasmScene({ el: fragmentedHost, scene: fragmentedScene(1025), worker: fragmentedWorker, transfer: false }),
    "XYG_WASM_RESOURCE_LIMIT",
    3,
  );
  if (!fragmentedError.message.includes("more than 1024 browser traces")) {
    throw new Error(`fragmented Scene diagnostic was not actionable: ${fragmentedError.message}`);
  }
  if (fragmentedHost.childNodes.length !== 0) {
    throw new Error("fragmented Scene allocated browser painter state before rejection");
  }
  fragmentedHost.remove();
  await fragmentedWorker.dispose();

  const columnWorker = createXygWasmWorker({
    workerUrl: "/packages/xy-client/dist/wasm-worker.js",
    wasm: wasmModule,
    maxArenaBytes: 1024 * 1024,
  });
  await columnWorker.ready;
  const columns = {
    width: 320,
    height: 240,
    autoMargins: true,
    x: { lo: 0, hi: 1 },
    y: { lo: 0, hi: 1 },
    kinds: ["scatter"],
    stableIds: [7n],
    styleRefs: [0],
    diameter: [8],
    symbols: [0],
    x0: [0.5],
    y0: [0.5],
    x1: [0],
    y1: [0],
    styles: [{ fillRgba: [37, 99, 235, 255], strokeRgba: [0, 0, 0, 0], strokeWidth: 0 }],
  };
  const packed = encodeWasmColumns(columns);
  if (new Uint8Array(packed).subarray(0, 4).join(",") !== "88,89,67,67") {
    throw new Error("typed-column encoder did not emit XYCC");
  }
  const compiled = await columnWorker.compileScene(new Uint8Array(packed), {
    sequence: 1,
    transfer: false,
  }).result;
  if (!(compiled.scene instanceof ArrayBuffer) || compiled.records !== 1 || compiled.styles !== 1) {
    throw new Error(`typed-column compile did not return a Scene batch: ${JSON.stringify(compiled)}`);
  }
  if (new Uint8Array(compiled.scene).subarray(0, 4).join(",") !== "88,89,71,83") {
    throw new Error("typed-column compile did not emit XYGS");
  }
  const columnHost = document.body.appendChild(document.createElement("div"));
  const columnView = await renderWasmColumns({
    el: columnHost,
    columns,
    worker: columnWorker,
    transfer: false,
  });
  if (!columnHost.querySelector("canvas") || columnView.gpuTraces.length < 1) {
    throw new Error("typed-column public API did not hydrate the existing painter");
  }
  if (columnView.sceneStableId(0, 0) !== 7n) {
    throw new Error("typed-column stable id was not preserved through painter hydration");
  }
  columnView.destroy();
  columnHost.remove();
  await columnWorker.dispose();

  foundationStage = "semantic graph labels";
  const semanticWorker = createXygWasmWorker({
    workerUrl: "/packages/xy-client/dist/wasm-worker.js",
    wasm: wasmModule,
    maxArenaBytes: 1024 * 1024,
  });
  await semanticWorker.ready;
  const semanticGraph = {
    width: 800, height: 600, theme: "dark", title: "Semantic graph", tier: "direct",
    x: [0, 1, 0.5], y: [0, 0, 1],
    nodeClass: [1, 2, 3], nodeEpistemic: [1, 0, 2], nodeStatus: [0, 1, 2],
    nodeMetric: [0, 0.5, 1], nodeFlags: [2, 64, 0],
    nodeLabels: ["Selected node with an intentionally long label that truncates", "Disabled node", "Third node"],
    parents: [0n, 0n, 0n], parentValidity: [0, 1, 0], collapsed: [1, 0, 0],
    sources: [0n, 0n, 2n, 2n], targets: [2n, 2n, 2n, 1n],
    edgeClass: [1, 2, 3, 1], edgeEpistemic: [1, 3, 2, 0], edgeStatus: [1, 0, 2, 0],
    edgeMetric: [1, 2, 3, 1], edgeFlags: [0, 16, 0, 0],
    edgeLabels: ["parallel edge", "pinned edge", "self loop", "collapsed boundary"],
  };
  const semanticPacked = encodeWasmSemanticGraph(semanticGraph);
  if (new Uint8Array(semanticPacked).subarray(0, 4).join(",") !== "88,89,71,71") {
    throw new Error("semantic graph encoder did not emit XYGG");
  }
  const semanticHost = document.body.appendChild(document.createElement("div"));
  let semanticView = await renderWasmSemanticGraph({
    el: semanticHost, graph: semanticGraph, worker: semanticWorker, transfer: false,
  });
  const legendLabels = [...semanticHost.querySelectorAll('[data-xy-slot="legend_label"]')]
    .map((node) => node.textContent);
  const legend = semanticHost.querySelector('[data-xy-slot="legend"][role="list"]');
  const legendRows = [...semanticHost.querySelectorAll('[data-xy-slot="legend_item"][role="listitem"]')];
  if (!semanticHost.querySelector("canvas") || semanticView.gpuTraces.length < 3
      || !legend || legendRows.length !== legendLabels.length
      || legendRows.some((row, index) => row.getAttribute("aria-label") !== legendLabels[index])
      || legendLabels.join("|") !== "Class 1|Class 2|Class 3|Epistemic 0|Epistemic 1|Epistemic 2|Epistemic 3|Status 0|Status 1|Status 2") {
    throw new Error(`semantic graph did not hydrate Rust painter/legend parity: ${legendLabels.join("|")}`);
  }
  const graphLabels = [...semanticHost.querySelectorAll('[data-xy-slot="graph_label"][role="listitem"]')];
  const collapsedChildId = (1n << 32n) + 1n;
  const visibleParentId = 1n << 32n;
  const visiblePeerId = (1n << 32n) + 2n;
  const nodeIds = [];
  semanticView.gpuTraces.forEach((trace, traceIndex) => {
    if (trace.trace.kind !== "scatter") return;
    for (let row=0; row<trace._sceneIds.lo.length; row++) nodeIds.push(semanticView.sceneStableId(traceIndex, row));
  });
  if (!semanticHost.querySelector('[data-xy-chrome="graph_labels"][role="list"][aria-label="Graph labels"]')
      || graphLabels.length < 2
      || graphLabels.some((label) => !label.dataset.xyStableId || !label.textContent)
      || !nodeIds.includes(visibleParentId) || !nodeIds.includes(visiblePeerId)
      || nodeIds.includes(collapsedChildId)
      || !graphLabels.some((label) => BigInt(label.dataset.xyStableId) === visibleParentId)
      || graphLabels.some((label) => BigInt(label.dataset.xyStableId) === collapsedChildId)
      || !graphLabels.some((label) => label.textContent.endsWith("…"))) {
    throw new Error(`semantic graph labels lost Rust placement/truncation/a11y: ${graphLabels.map((label) => label.textContent).join("|")}`);
  }
  foundationStage = "public compound disclosure lifecycle";
  const transitionInput = {
    nodeIds: [visibleParentId, collapsedChildId, visiblePeerId],
    parents: semanticGraph.parents,
    parentValidity: semanticGraph.parentValidity,
    collapsed: semanticGraph.collapsed,
    targetId: visibleParentId,
    action: "expand",
    tier: "direct",
  };
  const expanded = await transitionWasmCompound(semanticWorker, transitionInput).result;
  if (!expanded.changed || expanded.collapsed.join(",") !== "0,0,0") throw new Error("Rust expand transition returned the wrong atomic state");
  semanticView.destroy();
  if (semanticHost.querySelector('[data-xy-chrome="graph_labels"]')) throw new Error("expand update retained a stale label layer");
  semanticView = await renderWasmSemanticGraph({ el: semanticHost, graph: { ...semanticGraph, collapsed: expanded.collapsed }, worker: semanticWorker, transfer: false });
  const expandedIds = [];
  semanticView.gpuTraces.forEach((trace, traceIndex) => {
    if (trace.trace.kind !== "scatter") return;
    for (let row=0; row<trace._sceneIds.lo.length; row++) expandedIds.push(semanticView.sceneStableId(traceIndex, row));
  });
  const expandedLabels = [...semanticHost.querySelectorAll('[data-xy-slot="graph_label"][role="listitem"]')];
  if (!expandedIds.includes(collapsedChildId) || !expandedLabels.some((label) => BigInt(label.dataset.xyStableId) === collapsedChildId)
      || semanticHost.querySelectorAll('[data-xy-chrome="graph_labels"]').length !== 1) throw new Error("expanded child identity did not reach GPU and a11y consumers");
  const recollapsed = await transitionWasmCompound(semanticWorker, { ...transitionInput, collapsed: expanded.collapsed, action: "toggle" }).result;
  if (!recollapsed.changed || recollapsed.collapsed.join(",") !== "1,0,0") throw new Error("Rust toggle transition returned the wrong atomic state");
  semanticView.destroy();
  if (semanticHost.querySelector('[data-xy-chrome="graph_labels"]')) throw new Error("collapse update retained a stale label layer");
  semanticView = await renderWasmSemanticGraph({ el: semanticHost, graph: { ...semanticGraph, collapsed: recollapsed.collapsed }, worker: semanticWorker, transfer: false });
  const recollapsedIds = [];
  semanticView.gpuTraces.forEach((trace, traceIndex) => {
    if (trace.trace.kind !== "scatter") return;
    for (let row=0; row<trace._sceneIds.lo.length; row++) recollapsedIds.push(semanticView.sceneStableId(traceIndex, row));
  });
  if (semanticHost.querySelectorAll('[data-xy-chrome="graph_labels"]').length !== 1
      || recollapsedIds.includes(collapsedChildId)
      || [...semanticHost.querySelectorAll('[data-xy-slot="graph_label"]')].some((label) => BigInt(label.dataset.xyStableId) === collapsedChildId)) throw new Error("recollapse retained descendant a11y identity or duplicate layers");
  await new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve)));
  const semanticCanvas = semanticView.canvas;
  const semanticGl = semanticView.gl;
  if (!semanticGl) throw new Error("semantic graph canvas has no WebGL2 context");
  semanticView.draw();
  const semanticPixels = new Uint8Array(semanticCanvas.width * semanticCanvas.height * 4);
  semanticGl.readPixels(0, 0, semanticCanvas.width, semanticCanvas.height,
    semanticGl.RGBA, semanticGl.UNSIGNED_BYTE, semanticPixels);
  const paints = new Set();
  for (let index=0; index<semanticPixels.length; index+=4) {
    if (semanticPixels[index+3]) paints.add(`${semanticPixels[index]},${semanticPixels[index+1]},${semanticPixels[index+2]},${semanticPixels[index+3]}`);
  }
  const semanticTracePaints = new Set(semanticView.spec.traces.map((trace) => JSON.stringify(trace.style)));
  const edgeIds = [];
  semanticView.gpuTraces.forEach((trace, traceIndex) => {
    if (trace.trace.kind !== "line") return;
    for (let row=0; row<trace._sceneIds.lo.length; row++) edgeIds.push(semanticView.sceneStableId(traceIndex, row));
  });
  if (paints.size < 2 || semanticTracePaints.size < 4) {
    throw new Error(`semantic graph visual probe found ${paints.size} canvas colors / ${semanticTracePaints.size} resolved trace paints`);
  }
  if (!edgeIds.length || edgeIds.some((id) => id < 1n || id > 4n)
      || edgeIds.filter((id) => id === 1n).length < 4
      || !edgeIds.includes(3n) || !edgeIds.includes(4n)) {
    throw new Error(`semantic parallel/self-loop layers lost source identity: ${edgeIds.join("|")}`);
  }
  const semanticRoot = semanticHost.firstElementChild;
  if (!semanticRoot || getComputedStyle(semanticRoot).backgroundColor !== "rgb(3, 7, 18)"
      || semanticView.spec.dom.style["--chart-bg"] !== "rgba(17 24 39 / 1)") {
    throw new Error("dark semantic Scene did not apply its theme-owned chart/plot backgrounds");
  }
  try {
    encodeWasmSemanticGraph({ ...semanticGraph, tier: "aggregate" });
    throw new Error("aggregate semantic metadata was accepted");
  } catch (error) {
    if (!(error instanceof TypeError)) throw error;
  }
  for (const [malformedIndex, malformed] of [
    { ...semanticGraph, x: ["0", 1, 0.5] },
    { ...semanticGraph, sources: ["0", 0n, 2n] },
    { ...semanticGraph, nodeLabels: [1, null, "valid"] },
    { ...semanticGraph, edgeLabels: [{ toString: () => "coercible" }, null, "valid", null] },
    { ...semanticGraph, parents: [0n, 0n] },
    { ...semanticGraph, parents: [0n, 0n, 0n, 0n] },
    { ...semanticGraph, parents: [0n, "0", 0n] },
    { ...semanticGraph, parents: Object.assign(new Array(3), {0: 0n, 2: 0n}) },
    { ...semanticGraph, parentValidity: [0, 2, 0] },
    { ...semanticGraph, collapsed: [0, 0] },
    { ...semanticGraph, collapsed: [0, 0, 0, 0] },
  ].entries()) {
    try {
      encodeWasmSemanticGraph(malformed);
      throw new Error(`coercible semantic graph input ${malformedIndex} was accepted`);
    } catch (error) {
      if (!(error instanceof TypeError)) throw error;
    }
  }
  semanticView.destroy();
  if (semanticHost.querySelector('[data-xy-chrome="graph_labels"]')) {
    throw new Error("semantic graph destroy retained a stale visible/a11y label layer");
  }
  semanticView = await renderWasmSemanticGraph({
    el: semanticHost,
    graph: { ...semanticGraph, nodeLabels: ["Updated node", null, null], edgeLabels: [null, null, null, null] },
    worker: semanticWorker,
    transfer: false,
  });
  const updatedLayers = semanticHost.querySelectorAll('[data-xy-chrome="graph_labels"]');
  const updatedItems = semanticHost.querySelectorAll('[data-xy-slot="graph_label"][role="listitem"]');
  if (updatedLayers.length !== 1 || updatedItems.length !== 1 || updatedItems[0].textContent !== "Updated node") {
    throw new Error("semantic graph update did not retain exactly one current Rust label layer");
  }

  foundationStage = "Rust dashboard admission applied to shared GPU pick resources";
  const peerHost = document.body.appendChild(document.createElement("div"));
  const peerView = await renderWasmSemanticGraph({
    el: peerHost, graph: semanticGraph, worker: semanticWorker, transfer: false,
  });
  const sharedHost = semanticView._glHost;
  if (!sharedHost || peerView._glHost !== sharedHost || !semanticView.pickTex || !peerView.pickTex) {
    throw new Error("dashboard admission probe did not start with two pickable clients on one shared host");
  }
  const settleDeadline = performance.now() + 2000;
  while (semanticView._interactionTransitionActive() || peerView._interactionTransitionActive()) {
    if (performance.now() >= settleDeadline) throw new Error("dashboard admission views did not settle");
    await new Promise((resolve) => requestAnimationFrame(resolve));
  }
  semanticView._cancelDrawFrame();
  peerView._cancelDrawFrame();
  const frameBefore = sharedHost.frameSnapshot();
  semanticView.draw();
  peerView.draw();
  if (sharedHost.frameSnapshot().pending !== 2) {
    throw new Error("shared frame scheduler did not coalesce two chart paints");
  }
  await new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve)));
  const frameAfter = sharedHost.frameSnapshot();
  if (frameAfter.batches !== frameBefore.batches + 1
      || frameAfter.callbacks !== frameBefore.callbacks + 2 || frameAfter.maxBatch < 2
      || frameAfter.pending !== 0) {
    throw new Error(`shared frame scheduler diagnostics drifted: ${JSON.stringify(frameAfter)}`);
  }
  // Freeze observer-driven visibility before assigning the deterministic
  // dashboard state; hosted Chromium can deliver its first observation while
  // the worker is planning, which is a legitimate stale-plan rejection.
  semanticView._ctxIo?.disconnect();
  peerView._ctxIo?.disconnect();
  semanticView._ctxVisible = true;
  peerView._ctxVisible = true;
  sharedHost.markDashboardResourceUsed(peerView);
  sharedHost.markDashboardResourceUsed(semanticView);
  const admittedBytes = semanticView._dashboardResourceState().derivedBytes;
  const peerIds = peerView.gpuTraces.map((trace, traceIndex) =>
    Array.from(trace._sceneIds.lo, (_, row) => peerView.sceneStableId(traceIndex, row)));
  const applyResidency = sharedHost.applyDashboardResidency.bind(sharedHost);
  let admissionAttempts = 0;
  sharedHost.applyDashboardResidency = (...args) => {
    admissionAttempts += 1;
    return admissionAttempts === 1 ? false : applyResidency(...args);
  };
  const admission = await semanticView.applyDashboardResourceBudget(semanticWorker, admittedBytes);
  sharedHost.applyDashboardResidency = applyResidency;
  if (!admission.applied || admissionAttempts < 2 || admission.plan.retained.join(",") !== "true,false"
      || admission.beforeBytes !== admittedBytes * 2n || admission.afterBytes !== admittedBytes
      || !semanticView.pickTex || peerView.pickTex || peerView.pickFbo) {
    throw new Error(`Rust dashboard recency admission was not applied to two visible pick resources: retained=${admission.plan.retained} applied=${admission.applied} bytes=${admission.beforeBytes}/${admission.afterBytes}/${admittedBytes} textures=${!!semanticView.pickTex}/${!!peerView.pickTex}/${!!peerView.pickFbo}`);
  }
  peerView._pickAt(-1, -1);
  const rebuiltPeerIds = peerView.gpuTraces.map((trace, traceIndex) =>
    Array.from(trace._sceneIds.lo, (_, row) => peerView.sceneStableId(traceIndex, row)));
  if (!peerView.pickTex || JSON.stringify(peerIds, (_, value) => typeof value === "bigint" ? value.toString() : value)
      !== JSON.stringify(rebuiltPeerIds, (_, value) => typeof value === "bigint" ? value.toString() : value)) {
    throw new Error("evicted pick resources did not rebuild with stable source identity");
  }
  const automaticAdmission = semanticView.watchDashboardResourceBudget(semanticWorker, admittedBytes);
  await automaticAdmission.settled;
  if (semanticView.pickTex || !peerView.pickTex) {
    throw new Error("automatic Rust admission did not retain the most recently used peer");
  }
  semanticView._pickAt(-1, -1);
  await automaticAdmission.settled;
  if (!semanticView.pickTex || peerView.pickTex || peerView.pickFbo) {
    throw new Error("automatic Rust admission did not replan after active resource use");
  }
  automaticAdmission.dispose();
  const staleSnapshot = sharedHost.dashboardResourceSnapshot();
  const stalePlan = await planWasmDashboardResources(semanticWorker, staleSnapshot.resources, admittedBytes);
  peerView._ctxVisible = false;
  if (sharedHost.applyDashboardResidency(staleSnapshot, stalePlan.retained)) {
    throw new Error("shared host applied a Rust dashboard plan after visibility changed");
  }
  const cancelBefore = sharedHost.frameSnapshot();
  peerView.draw();
  if (sharedHost.frameSnapshot().pending !== 1) throw new Error("shared frame cancellation probe was not queued");
  peerView.destroy(); peerHost.remove();
  await new Promise((resolve) => requestAnimationFrame(resolve));
  const cancelAfter = sharedHost.frameSnapshot();
  if (cancelAfter.pending !== 0 || cancelAfter.callbacks !== cancelBefore.callbacks) {
    throw new Error("destroyed chart executed queued shared-frame GPU work");
  }
  semanticView.destroy();
  if (semanticHost.querySelector('[data-xy-chrome="graph_labels"]')) {
    throw new Error("updated semantic graph destroy retained its label layer");
  }
  semanticHost.remove();

  foundationStage = "GraphForge semantic light/dark visual and accessibility goldens";
  for (const theme of ["light", "dark"]) {
    const fixtureHost = document.body.appendChild(document.createElement("div"));
    const nodes = graphForgeSemanticFixture.nodes, edges = graphForgeSemanticFixture.edges;
    const fixtureView = await renderWasmSemanticGraph({
      el: fixtureHost, worker: semanticWorker, transfer: false,
      graph: {
        width: graphForgeSemanticFixture.width, height: graphForgeSemanticFixture.height,
        title: graphForgeSemanticFixture.title, theme, tier: "direct",
        x: nodes.x, y: nodes.y, nodeClass: nodes.class, nodeEpistemic: nodes.epistemic,
        nodeStatus: nodes.status, nodeMetric: nodes.metric, nodeFlags: nodes.state_flags,
        nodeLabels: nodes.label, sources: edges.source_index.map(BigInt), targets: edges.target_index.map(BigInt),
        edgeClass: edges.class, edgeEpistemic: edges.epistemic, edgeStatus: edges.status,
        edgeMetric: edges.metric, edgeFlags: edges.state_flags, edgeLabels: edges.label,
      },
    });
    fixtureView.draw();
    const items = [...fixtureHost.querySelectorAll('[data-xy-slot="graph_label"][role="listitem"]')];
    const legendItems = [...fixtureHost.querySelectorAll('[data-xy-slot="legend_item"][role="listitem"]')];
    const legendLabels = legendItems.map((item) => item.textContent);
    const expectedLegendLabels = ["Class 1", "Class 2", "Class 3", "Class 4", "Class 5",
      "Epistemic 0", "Epistemic 1", "Epistemic 2", "Epistemic 3", "Epistemic 4",
      "Status 0", "Status 1", "Status 2", "Status 3", "Status 4"];
    const expectedBackground = theme === "dark" ? "rgb(3, 7, 18)" : "rgb(255, 255, 255)";
    if (getComputedStyle(fixtureHost.firstElementChild).backgroundColor !== expectedBackground
        || items.length < 2 || items.some((item) => !item.dataset.xyStableId || !item.textContent)
        || !items.some((item) => item.textContent === "outside loop" && item.dataset.xyStableId === "3")
        || legendLabels.join("|") !== expectedLegendLabels.join("|")
        || legendItems.some((item) => item.getAttribute("aria-label") !== item.textContent)) {
      throw new Error(`GraphForge ${theme} visual/a11y golden drifted: labels=${items.length} legends=${legendItems.length}`);
    }
    const ids = fixtureView.gpuTraces.flatMap((trace, traceIndex) =>
      Array.from(trace._sceneIds.lo, (_, row) => fixtureView.sceneStableId(traceIndex, row)));
    const uniqueIds = [...new Set(ids)].sort((left, right) => left < right ? -1 : left > right ? 1 : 0);
    const expectedIds = [1n, 2n, 3n, 1n << 32n, (1n << 32n) + 1n, (1n << 32n) + 2n,
      (1n << 32n) + 3n, (1n << 32n) + 4n];
    if (uniqueIds.join("|") !== expectedIds.join("|")) {
      throw new Error(`GraphForge ${theme} source identities drifted: ${uniqueIds.join("|")}`);
    }
    await new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve)));
    fixtureView.draw();
    const pixels = new Uint8Array(fixtureView.canvas.width * fixtureView.canvas.height * 4);
    fixtureView.gl.readPixels(0, 0, fixtureView.canvas.width, fixtureView.canvas.height,
      fixtureView.gl.RGBA, fixtureView.gl.UNSIGNED_BYTE, pixels);
    const colors = new Set();
    for (let index = 0; index < pixels.length; index += 4) {
      if (pixels[index + 3]) colors.add(`${pixels[index]},${pixels[index + 1]},${pixels[index + 2]},${pixels[index + 3]}`);
    }
    if (colors.size < 6) throw new Error(`GraphForge ${theme} visual golden is flat (${colors.size} colors)`);
    fixtureView.destroy(); fixtureHost.remove();
  }
  await semanticWorker.dispose();

  const chartWorker = createXygWasmWorker({
    workerUrl: "/packages/xy-client/dist/wasm-worker.js",
    wasm: wasmModule,
    maxArenaBytes: 1024 * 1024,
  });
  await chartWorker.ready;
  const chart = {
    width: 320,
    height: 240,
    title: "chart ergonomics",
    series: [
      {
        kind: "scatter",
        x: new Float64Array([0.2, 0.8]),
        y: new Float64Array([0.3, 0.7]),
        stableIds: new BigUint64Array([0x5859000000000001n, 0x5859030000000002n]),
        diameter: 8,
      },
      {
        kind: "line",
        x: new Float64Array([0.1, 0.5, 0.9]),
        y: new Float64Array([0.2, 0.6, 0.4]),
        stableIds: new BigUint64Array([80n, 83n, 81n]),
      },
      {
        kind: "bar",
        x: new Float64Array([0.3]),
        y: new Float64Array([0.5]),
        stableIdBase: 90n,
      },
      {
        kind: "area",
        x: new Float64Array([0.1, 0.9]),
        y: new Float64Array([0.4, 0.6]),
        stableIds: new BigUint64Array([100n, 107n]),
      },
    ],
  };
  const chartPacked = frameWasmChart(chart);
  const chartFlags = new DataView(chartPacked.prefix).getUint32(12, true);
  if ((chartFlags & 3) !== 3) {
    throw new Error(`chart ergonomics did not set autoMargins|autoDomain flags: ${chartFlags}`);
  }
  if (new Uint8Array(chartPacked.prefix).subarray(0, 4).join(",") !== "88,89,84,83") {
    throw new Error("chart ergonomics framer did not emit XYTS");
  }
  const fixtureMagic = new TextDecoder().decode(new Uint8Array(chartPacked.prefix, 0, 4));
  if (fixtureMagic !== sharedFixture.wasm_typed_series_v2.magic) {
    throw new Error("browser typed-series framing drifted from the shared Python/Node fixture");
  }
  const aliased = new Float64Array([0, 1]);
  try {
    frameWasmChart({ width: 10, height: 10, series: [{ kind: "scatter", x: aliased, y: aliased }] });
    throw new Error("chart ergonomics accepted aliased transferable columns");
  } catch (error) {
    if (!(error instanceof TypeError) || !String(error.message).includes("distinct transferable")) throw error;
  }
  for (const malformedSeries of [
    { kind: "line", x: new Float64Array([0]), y: new Float64Array([1]), diameter: 2 },
    { kind: "scatter", x: new Float64Array([0]), y: new Float64Array([1]), y0: new Float64Array([0]) },
    { kind: "scatter", x: new Float64Array([0]), y: new Float64Array([1]), diameter: -1 },
    { kind: "scatter", x: new Float64Array([0]), y: new Float64Array([1]), diameter: [2] },
    { kind: "line", x: new Float64Array([0]), y: new Float64Array([1]), style: { fillRgba: [1, 2, 3, 4] } },
    { kind: "scatter", x: new Float64Array([0]), y: new Float64Array([1]), stableIdBase: 1n, stableIds: new BigUint64Array([2n]) },
  ]) {
    try {
      frameWasmChart({ width: 10, height: 10, series: [malformedSeries] });
      throw new Error("chart ergonomics accepted inapplicable or negative geometry");
    } catch (error) {
      if (!(error instanceof TypeError)) throw error;
    }
  }
  for (const style of [null, 1, []]) {
    try {
      frameWasmChart({
        width: 10, height: 10,
        series: [{ kind: "line", x: new Float64Array([0]), y: new Float64Array([1]), style }],
      });
      throw new Error("chart ergonomics accepted a non-object or array style");
    } catch (error) {
      if (!(error instanceof TypeError) || !String(error.message).includes("style must be a non-array object")) throw error;
    }
  }
  frameWasmChart({
    width: 10, height: 10,
    series: [{
      kind: "line", x: new Float64Array([0]), y: new Float64Array([1]),
      style: { strokeRgba: [1, 2, 3, 255], strokeWidth: 1 },
    }],
  });
  try {
    frameWasmChart({
      width: 10, height: 10,
      series: [{
        kind: "line", x: new Float64Array([0]), y: new Float64Array([1]), style: { step: "mid" },
      }],
    });
    throw new Error("chart ergonomics accepted an unsupported style key");
  } catch (error) {
    if (!(error instanceof TypeError) || !String(error.message).includes("style step is not supported")) throw error;
  }
  const oversizedX = new Float64Array(4_000), oversizedY = new Float64Array(4_000);
  try {
    chartWorker.compilePrepareSeries(frameWasmChart({
      width: 10, height: 10, series: [{ kind: "scatter", x: oversizedX, y: oversizedY }],
    }));
    throw new Error("chart ergonomics transferred a request beyond the configured peak");
  } catch (error) {
    if (!(error instanceof RangeError) || !String(error.message).includes("peak byte budget")) throw error;
  }
  if (oversizedX.byteLength === 0 || oversizedY.byteLength === 0) {
    throw new Error("oversized typed-series buffers detached before bounded rejection");
  }
  const failedOwnedWorker = createXygWasmWorker({
    workerUrl: "/packages/xy-client/dist/wasm-worker.js",
    wasm: wasmModule,
    maxArenaBytes: 1024 * 1024,
  });
  await failedOwnedWorker.ready;
  try {
    await renderWasmChart({
      el: document.body.appendChild(document.createElement("div")),
      worker: failedOwnedWorker,
      workerOwnership: "own",
      chart: { width: 10, height: 10, series: [{ kind: "scatter", x: oversizedX, y: oversizedY }] },
    });
    throw new Error("oversized initial update unexpectedly succeeded");
  } catch (error) {
    if (!(error instanceof RangeError) || !String(error.message).includes("peak byte budget")) throw error;
  }
  try {
    failedOwnedWorker.validateScene(canonicalSceneV9());
    throw new Error("failed initial update leaked its owned worker");
  } catch (error) {
    if (!(error instanceof XygWasmError) || error.code !== "XYG_WASM_DISPOSED") throw error;
  }
  const chartHost = document.body.appendChild(document.createElement("div"));
  foundationStage = "initial typed-series render";
  const chartView = await renderWasmChart({
    el: chartHost,
    chart,
    worker: chartWorker,
  });
  if (!chartHost.querySelector("canvas") || chartView.gpuTraces.length < 1) {
    throw new Error("chart ergonomics public API did not hydrate the existing painter");
  }
  if (chartView.sceneStableId(0, 0) !== 0x5859000000000001n) {
    throw new Error("chart ergonomics stable id was not preserved through painter hydration");
  }
  if (chartView.sceneStableId(0, 1) !== 0x5859030000000002n) {
    throw new Error("chart ergonomics did not preserve a non-sequential transferred stable id");
  }
  if (chartView.gpuTraces.find((gpu) => gpu.trace?.kind === "line")?.trace?.n_points !== 3
      || chartView.gpuTraces.find((gpu) => gpu.trace?.kind === "area")?.trace?.n_points !== 2
      || chartView.sceneStableId(1, 1) !== 83n || chartView.sceneStableId(3, 1) !== 107n) {
    throw new Error("arbitrary line/area row identities split Rust trace geometry or drifted through picking");
  }
  const defaultLine = chartView.gpuTraces.find((gpu) => gpu.trace?.kind === "line")?.trace;
  if (defaultLine?.style?.color !== "rgba(57 135 229 / 1)" || defaultLine.style.width !== 1.5) {
    throw new Error(`Rust line defaults drifted from the shared fixture: ${JSON.stringify(defaultLine?.style)}`);
  }
  const renderedKinds = new Set(chartView.gpuTraces.map((gpu) => gpu.trace?.kind));
  for (const expected of ["scatter", "line", "box", "area"]) {
    if (!renderedKinds.has(expected)) throw new Error(`Rust typed-series painter omitted ${expected}`);
  }
  const chartDiagnostics = chartView.diagnostics();
  if (!chartDiagnostics || chartDiagnostics.arenaHighWaterBytes < chartPacked.byteLength
      || chartDiagnostics.memoryHighWaterBytes !== chartDiagnostics.memoryBytes
      || chartDiagnostics.mainThreadRecordVisits !== 0 || chartDiagnostics.framedSeries !== 4) {
    throw new Error(`chart ergonomics did not report arena high-water: ${JSON.stringify(chartDiagnostics)}`);
  }
  const updateInput = (stableIdBase) => ({
    width: 320,
    height: 240,
    series: [{
      kind: "scatter",
      x: new Float64Array([0.25, 0.75]),
      y: new Float64Array([0.4, 0.6]),
      stableIdBase,
    }],
  });
  foundationStage = "chart update cancellation";
  const staleUpdate = chartView.update(updateInput(90n));
  const currentUpdate = chartView.update(updateInput(100n));
  await rejected(staleUpdate, "XYG_WASM_CANCELLED", 6);
  await currentUpdate;
  if (chartView.sceneStableId(0, 0) !== 100n) {
    throw new Error("chart handle did not retain only the newest update");
  }
  if (chart.series.some((series) => series.x.byteLength === 0 || series.y.byteLength === 0)) {
    throw new Error("default chart rendering detached caller-owned arrays");
  }
  if (chart.series[0].stableIds.byteLength === 0) {
    throw new Error("default chart rendering detached caller-owned stable IDs");
  }
  foundationStage = "failed chart update clears painter state";
  try {
    await chartView.update({
      width: 10,
      height: 10,
      series: [{ kind: "scatter", x: oversizedX, y: oversizedY }],
    });
    throw new Error("over-budget chart update unexpectedly succeeded");
  } catch (error) {
    if (!(error instanceof RangeError) || !String(error.message).includes("peak byte budget")) throw error;
  }
  if (chartView.diagnostics() !== null || chartView.gpuTraces.length !== 0
      || chartHost.querySelector("canvas")) {
    throw new Error("failed chart update retained stale painter state");
  }
  await chartView.dispose();
  await chartWorker.validateScene(canonicalSceneV9(), { sequence: 20 }).result;
  chartHost.remove();
  await chartWorker.dispose();
  const transferWorker = createXygWasmWorker({
    workerUrl: "/packages/xy-client/dist/wasm-worker.js",
    wasm: wasmModule,
    maxArenaBytes: 1024 * 1024,
  });
  await transferWorker.ready;
  const transferredX = new Float64Array([0.2, 0.8]), transferredY = new Float64Array([0.8, 0.2]);
  const transferredIds = new BigUint64Array([11n, 17n]);
  foundationStage = "explicit typed-series transfer";
  await transferWorker.compilePrepareSeries(frameWasmChart({
    width: 320, height: 240, series: [{ kind: "scatter", x: transferredX, y: transferredY, stableIds: transferredIds }],
  }), { transfer: true }).result;
  if (transferredX.byteLength !== 0 || transferredY.byteLength !== 0 || transferredIds.byteLength !== 0) {
    throw new Error("explicit typed-series transfer did not detach caller buffers");
  }
  await transferWorker.dispose();

  foundationStage = "typed-series fragmentation diagnostics";
  const fragmentationWorker = createXygWasmWorker({
    workerUrl: "/packages/xy-client/dist/wasm-worker.js",
    wasm: wasmModule,
    maxArenaBytes: 8 * 1024 * 1024,
  });
  await fragmentationWorker.ready;
  const fragmentedChartSeries = Array.from({ length: 1025 }, (_, index) => ({
    kind: "scatter",
    x: new Float64Array([(index + 0.5) / 1025]),
    y: new Float64Array([(index + 0.5) / 1025]),
  }));
  const fragmentedRequest = frameWasmChart({
    width: 320,
    height: 240,
    series: fragmentedChartSeries,
  });
  try {
    await fragmentationWorker.compilePrepareSeries(fragmentedRequest).result;
    throw new Error("fragmented typed series unexpectedly produced painter resources");
  } catch (error) {
    if (!(error instanceof XygWasmError)
        || error.code !== "XYG_WASM_RESOURCE_LIMIT"
        || error.status !== 3
        || !String(error.message).includes("more than 1024 browser traces")) throw error;
    const failure = error.diagnostics;
    if (!failure || failure.copyCount !== 1 || failure.copyBytesHi !== 0
        || failure.copyBytesLo !== fragmentedRequest.byteLength
        || failure.arenaBytes !== 0 || failure.records !== 1025 || failure.styles !== 1025) {
      throw new Error(`fragmentation failure omitted Rust transfer diagnostics: ${JSON.stringify(failure)}`);
    }
  }
  await fragmentationWorker.dispose();

  foundationStage = "checkpointed typed-series compile lifecycle";
  const compileWorker = createXygWasmWorker({
    workerUrl: "/packages/xy-client/dist/wasm-worker.js",
    wasm: wasmModule,
    maxArenaBytes: 64 * 1024 * 1024,
  });
  await compileWorker.ready;
  const largeChartInput = () => {
    const x = new Float64Array(100_000), y = new Float64Array(100_000);
    for (let index = 0; index < x.length; index += 1) { x[index] = index; y[index] = index % 997; }
    return { width: 640, height: 480, series: [{ kind: "scatter", x, y }] };
  };
  const massiveChartInput = () => {
    const x = new Float64Array(200_000), y = new Float64Array(200_000);
    for (let index = 0; index < x.length; index += 1) { x[index] = index; y[index] = index % 1543; }
    return { width: 640, height: 480, series: [{ kind: "scatter", x, y }] };
  };
  let compileHeartbeat = null;
  let cancelledCompile;
  cancelledCompile = compileWorker.compilePrepareSeries(frameWasmChart(largeChartInput()), {
    sequence: 1, transfer: true,
    onProgress(progress) {
      compileHeartbeat = progress;
      if (progress.phase === 3) cancelledCompile.cancel();
    },
  });
  await rejected(cancelledCompile.result, "XYG_WASM_CANCELLED", 6);
  if (!compileHeartbeat || compileHeartbeat.recordsProcessed !== 100_000 || compileHeartbeat.phase !== 3) {
    throw new Error(`compile cancellation did not follow real Rust record progress: ${JSON.stringify(compileHeartbeat)}`);
  }
  const fragmentedSeries = Array.from({ length: 5 }, (_, series) => ({
    kind: "scatter",
    x: Float64Array.from({ length: 1_000 }, (_, index) => index + series * 1_000),
    y: Float64Array.from({ length: 1_000 }, (_, index) => (index + series) % 7),
  }));
  const fragmentedFrame = frameWasmChart({ width: 64, height: 48, series: fragmentedSeries });
  if (fragmentedFrame.byteLength >= 256 * 1024) throw new Error("fragmented heartbeat fixture is not sub-256KiB");
  let fragmentedHeartbeat = null;
  let fragmentedCompile;
  fragmentedCompile = compileWorker.compilePrepareSeries(fragmentedFrame, {
    sequence: 2, transfer: true,
    onProgress(progress) { fragmentedHeartbeat = progress; fragmentedCompile.cancel(); },
  });
  await rejected(fragmentedCompile.result, "XYG_WASM_CANCELLED", 6);
  if (!fragmentedHeartbeat || fragmentedHeartbeat.recordsProcessed !== 4096) {
    throw new Error("sub-256KiB fragmented compile had no real progress heartbeat");
  }
  const currentCompile = compileWorker.compilePrepareSeries(frameWasmChart({
    width: 64, height: 48, series: [{ kind: "scatter", x: new Float64Array([1]), y: new Float64Array([2]) }],
  }), { sequence: 3, transfer: true });
  if ((await currentCompile.result).sequence !== 3) throw new Error("cancelled compile published late paint over its replacement");
  await rejected(compileWorker.compilePrepareSeries(frameWasmChart({
    width: 64, height: 48, series: [{ kind: "scatter", x: new Float64Array([3]), y: new Float64Array([4]) }],
  }), { sequence: 3, transfer: true }).result, "XYG_WASM_STALE_SEQUENCE", 7);
  const lifecycleHost = document.body.appendChild(document.createElement("div"));
  const lifecycleHandle = await renderWasmChart({
    el: lifecycleHost, worker: compileWorker,
    chart: { width: 64, height: 48, series: [{ kind: "scatter", x: new Float64Array([1]), y: new Float64Array([2]) }] },
  });
  const cancelledUpdate = lifecycleHandle.update(largeChartInput());
  await new Promise((resolve) => setTimeout(resolve, 0));
  lifecycleHandle.cancel();
  await rejected(cancelledUpdate, "XYG_WASM_CANCELLED", 6);
  if (lifecycleHost.querySelector("canvas")) throw new Error("cancelled chart update retained late paint resources");
  await lifecycleHandle.dispose(); lifecycleHost.remove();
  const disposedCompile = compileWorker.compilePrepareSeries(frameWasmChart(largeChartInput()), { sequence: 6, transfer: true });
  const disposedCompileResult = rejected(disposedCompile.result, "XYG_WASM_DISPOSED");
  await new Promise((resolve) => setTimeout(resolve, 0));
  await compileWorker.dispose();
  await disposedCompileResult;

  const phase3Supersession = async (label, invoke) => {
    foundationStage = `phase-3 ${label} supersession`;
    try {
    const operationWorker = createXygWasmWorker({ workerUrl: "/packages/xy-client/dist/wasm-worker.js", wasm: wasmModule, maxArenaBytes: 384 * 1024 * 1024 });
    await operationWorker.ready;
    let replacement = null;
    const compile = operationWorker.compilePrepareSeries(frameWasmChart(massiveChartInput()), {
      sequence: 10, transfer: true,
      onProgress(progress) { if (progress.phase === 3 && replacement === null) replacement = Promise.resolve(invoke(operationWorker)).catch(() => undefined); },
    });
    try { await rejected(compile.result, "XYG_WASM_CANCELLED", 6); }
    catch (error) { throw new Error(`${label} compile rejection: ${error}`); }
    if (replacement === null) throw new Error(`${label} did not supersede phase-3 compile`);
    await replacement;
    try { await operationWorker.validateScene(canonicalSceneV9(), { sequence: 12 }).result; }
    catch (error) { throw new Error(`${label} cleanup validation: ${error}`); }
    await operationWorker.dispose();
    } catch (error) { throw new Error(`${label} phase helper: ${error}`); }
  };
  await phase3Supersession("scene", (worker) => worker.validateScene(canonicalSceneV9(), { sequence: 11 }).result);
  await phase3Supersession("temporal", (worker) => XygWasmTemporalController.create(worker, {
    instanceId: 70n, groupId: 90n, domain: [0n, 100n], cursor: 10n,
  }));
  await phase3Supersession("temporal graph", (worker) => XygWasmTemporalGraph.create(worker, {
    nodeIds: uuidBytes(1, 2), edgeIds: uuidBytes(11),
    sourceIds: uuidBytes(1), targetIds: uuidBytes(2),
  }));

  foundationStage = "compile-to-scene global watermark";
  const compileThenStaleScene = createXygWasmWorker({ workerUrl: "/packages/xy-client/dist/wasm-worker.js", wasm: wasmModule, maxArenaBytes: 1024 * 1024 });
  await compileThenStaleScene.ready;
  await compileThenStaleScene.compilePrepareSeries(frameWasmChart({ width: 64, height: 48, series: [{ kind: "scatter", x: new Float64Array([1]), y: new Float64Array([2]) }] }), { sequence: 10, transfer: true }).result;
  await rejected(compileThenStaleScene.validateScene(canonicalSceneV9(), { sequence: 9 }).result, "XYG_WASM_STALE_SEQUENCE", 7);
  await compileThenStaleScene.dispose();
  foundationStage = "scene-to-compile global watermark";
  const sceneThenStaleCompile = createXygWasmWorker({ workerUrl: "/packages/xy-client/dist/wasm-worker.js", wasm: wasmModule, maxArenaBytes: 1024 * 1024 });
  await sceneThenStaleCompile.ready;
  await sceneThenStaleCompile.validateScene(canonicalSceneV9(), { sequence: 10 }).result;
  await rejected(sceneThenStaleCompile.compilePrepareSeries(frameWasmChart({ width: 64, height: 48, series: [{ kind: "scatter", x: new Float64Array([1]), y: new Float64Array([2]) }] }), { sequence: 9, transfer: true }).result, "XYG_WASM_STALE_SEQUENCE", 7);
  await sceneThenStaleCompile.dispose();

  foundationStage = "progressive CoSE worker scheduling";
  const graphWorker = createXygWasmWorker({ workerUrl: "/packages/xy-client/dist/wasm-worker.js", wasm: wasmModule, maxArenaBytes: 1024 * 1024 });
  const peerGraphWorker = createXygWasmWorker({ workerUrl: "/packages/xy-client/dist/wasm-worker.js", wasm: wasmModule, maxArenaBytes: 1024 * 1024 });
  await Promise.all([graphWorker.ready, peerGraphWorker.ready]);
  const graphInput = () => encodeWasmCose({
    nNodes: 3, sources: new BigUint64Array([0n, 1n]), targets: new BigUint64Array([1n, 2n]),
    x: new Float64Array([-0.5, 0, 0.5]), y: new Float64Array([0, 0, 0]), pinned: new Uint8Array([1, 0, 0]),
    parents: new BigUint64Array([0xffffffffffffffffn, 0n, 0n]), totalSteps: 17, seed: 7n,
    cose: { idealEdgeLength: 0.4, bounds: [-1, -1, 1, 1] },
  });
  const updates = [];
  const graphTask = layoutWasmCose(graphWorker, {
    nNodes: 3, sources: new BigUint64Array([0n, 1n]), targets: new BigUint64Array([1n, 2n]),
    x: new Float64Array([-0.5, 0, 0.5]), y: new Float64Array([0, 0, 0]), pinned: new Uint8Array([1, 0, 0]),
    totalSteps: 17, seed: 7n, cose: { idealEdgeLength: 0.4, bounds: [-1, -1, 1, 1] },
  }, { revision: 11, chunkSteps: 4, onUpdate: (value) => updates.push(value) });
  const peerTask = peerGraphWorker.layoutCose(graphInput(), { revision: 21, chunkSteps: 8 });
  const [graphResult, peerResult] = await Promise.all([graphTask.result, peerTask.result]);
  if (updates[0]?.phase !== "initial" || updates[0]?.step !== 1 || graphResult.phase !== "complete" || graphResult.revision !== 11 || peerResult.revision !== 21) throw new Error("graph workers did not preserve bounded initial/progressive/completion phases or independent revisions");
  if (graphResult.x[0] !== -0.5 || graphResult.y[0] !== 0) throw new Error("browser WASM CoSE moved a Rust-owned pin");
  const staleGraph = graphWorker.layoutCose(graphInput(), { sequence: 30, revision: 30, chunkSteps: 1 });
  const currentGraph = graphWorker.layoutCose(graphInput(), { sequence: 31, revision: 31, chunkSteps: 8 });
  try {
    await staleGraph.result;
    throw new Error("superseded graph request unexpectedly published");
  } catch (error) {
    const validSupersession = error instanceof XygWasmError
      && ((error.code === "XYG_WASM_CANCELLED" && error.status === 6)
        || (error.code === "XYG_WASM_STALE_SEQUENCE" && error.status === 7));
    if (!validSupersession) throw error;
  }
  if ((await currentGraph.result).revision !== 31) throw new Error("superseded graph reply crossed revisions");
  const callbackFailure = graphWorker.layoutCose(graphInput(), {
    sequence: 32,
    revision: 32,
    chunkSteps: 1,
    onUpdate: () => { throw new Error("consumer progress failed"); },
  });
  await rejected(callbackFailure.result, "XYG_WASM_PROGRESS_CALLBACK_FAILED");
  if ((await graphWorker.layoutCose(graphInput(), { sequence: 33, revision: 33 }).result).revision !== 33) {
    throw new Error("graph worker did not recover after cancelling a failed progress callback");
  }
  await Promise.all([graphWorker.dispose(), peerGraphWorker.dispose()]);
  const failedGraphWorker = createXygWasmWorker({ workerUrl: "/packages/xy-client/dist/wasm-worker.js", wasm: await fixtureModule({ graphStepTrap: true }), maxArenaBytes: 1024 });
  await failedGraphWorker.ready;
  await rejected(failedGraphWorker.layoutCose(graphInput(), { revision: 1 }).result, "XYG_WASM_TRAP");
  await rejected(failedGraphWorker.layoutCose(graphInput(), { revision: 2 }).result, "XYG_WASM_NOT_READY");
  await failedGraphWorker.dispose();

  const aggWorker = createXygWasmWorker({
    workerUrl: "/packages/xy-client/dist/wasm-worker.js",
    wasm: wasmModule,
    maxArenaBytes: 1024 * 1024,
  });
  await aggWorker.ready;
  const aggPacked = encodeWasmAggregate({
    x: [0.5, 2.5],
    y: [0.5, 2.5],
    x0: 0,
    x1: 4,
    y0: 0,
    y1: 4,
    width: 4,
    height: 4,
    rgba: [255, 0, 0, 255, 0, 0, 255, 255],
  });
  if (new Uint8Array(aggPacked).subarray(0, 4).join(",") !== "88,89,65,71") {
    throw new Error("aggregate encoder did not emit XYAG");
  }
  const agg = await aggregateWasmBin2d(aggWorker, aggPacked, {
    sequence: 1,
  }).result;
  if (!(agg.aggregate instanceof ArrayBuffer) || agg.width !== 4 || agg.height !== 4) {
    throw new Error(`aggregate bin2d did not return XYAO grid: ${JSON.stringify({
      width: agg.width, height: agg.height, maxCount: agg.maxCount,
    })}`);
  }
  if (new Uint8Array(agg.aggregate).subarray(0, 4).join(",") !== "88,89,65,79") {
    throw new Error("aggregate bin2d did not emit XYAO");
  }
  if (!(agg.maxCount >= 1) || !agg.rgba || agg.rgba.length !== 64) {
    throw new Error(`aggregate mean-color plane missing: max=${agg.maxCount}`);
  }
  let occupied = 0;
  for (let i = 0; i < agg.grid.length; i++) {
    if (agg.grid[i] > 0) occupied += 1;
  }
  if (occupied !== 2) {
    throw new Error(`aggregate expected 2 occupied cells, got ${occupied}`);
  }
  for (const rgba of [undefined, []]) {
    const empty = await aggregateWasmBin2d(aggWorker, {
      x: [], y: [], x0: 0, x1: 1, y0: 0, y1: 1, width: 3, height: 2, rgba,
    }).result;
    if (empty.maxCount !== 0 || empty.grid.length !== 6
        || empty.grid.some((value) => value !== 0)
        || (rgba && (!empty.rgba || empty.rgba.some((value) => value !== 0)))) {
      throw new Error("empty aggregate did not match the native zero-grid contract");
    }
  }
  for (const bad of [
    { x: [0], y: [0], width: 2 ** 32, height: 1 },
    { x: [0], y: [0], width: 1, height: 1, rgba: [256, 0, 0, 255] },
  ]) {
    let rejectedInput = false;
    try { encodeWasmAggregate({ x0: 0, x1: 1, y0: 0, y1: 1, ...bad }); } catch (error) { rejectedInput = error instanceof TypeError || error instanceof RangeError; }
    if (!rejectedInput) throw new Error("aggregate encoder accepted an out-of-range u32/u8 input");
  }
  const oversized = { length: 4_194_304 };
  let rejectedBytes = false;
  try {
    encodeWasmAggregate({ x: oversized, y: oversized, x0: 0, x1: 1, y0: 0, y1: 1, width: 1, height: 1 });
  } catch (error) {
    rejectedBytes = error instanceof RangeError;
  }
  if (!rejectedBytes) throw new Error("aggregate encoder allocated beyond its generated byte bound");
  let cloneRejected = false;
  try {
    aggWorker.aggregateBin2d(new Uint8Array(1), { transfer: false });
  } catch (error) {
    cloneRejected = error instanceof XygWasmError
      && error.code === "XYG_WASM_INVALID_ARGUMENT" && error.status === 2;
  }
  if (!cloneRejected) throw new Error("aggregate clone mode did not fail before postMessage");
  // The 1 MiB worker budget and 2-copy request contract bind raw input at
  // 512 KiB: above it fails before header validation, below it reaches XYAG validation.
  const copyBoundary = (1024 * 1024) / 2;
  const oversizedTransfer = aggWorker.aggregateBin2d(new Uint8Array(copyBoundary + 88 * 1024));
  await rejected(oversizedTransfer.result, "XYG_WASM_RESOURCE_LIMIT", 3);
  const rawTransferred = aggWorker.aggregateBin2d(new Uint8Array(copyBoundary - 112 * 1024));
  await rejected(rawTransferred.result, "XYG_WASM_INVALID_ARGUMENT", 2);
  await aggWorker.dispose();

  const checkpointWorker = createXygWasmWorker({ workerUrl: "/packages/xy-client/dist/wasm-worker.js", wasm: wasmModule, maxArenaBytes: 8 * 1024 * 1024 });
  await checkpointWorker.ready;
  const checkpointPoints = new Float64Array(100_000).fill(0.5);
  const firstAggregate = aggregateWasmBin2d(checkpointWorker, { x: checkpointPoints, y: checkpointPoints, x0: 0, x1: 1, y0: 0, y1: 1, width: 64, height: 64 }, { sequence: 1 });
  await new Promise((resolve) => setTimeout(resolve, 0));
  const newerAggregate = aggregateWasmBin2d(checkpointWorker, { x: [0.5], y: [0.5], x0: 0, x1: 1, y0: 0, y1: 1, width: 2, height: 2 }, { sequence: 2 });
  await rejectedSuperseded(firstAggregate.result);
  const newer = await newerAggregate.result;
  if (newer.maxCount !== 1 || newer.width !== 2) throw new Error("new viewport did not progress after aggregate checkpoint cancellation");
  await checkpointWorker.dispose();

  const dashboardSupersedeWorker = createXygWasmWorker({
    workerUrl: "/packages/xy-client/dist/wasm-worker.js", wasm: wasmModule, maxArenaBytes: 8 * 1024 * 1024,
  });
  await dashboardSupersedeWorker.ready;
  const supersededAggregate = aggregateWasmBin2d(dashboardSupersedeWorker, {
    x: checkpointPoints, y: checkpointPoints, x0: 0, x1: 1, y0: 0, y1: 1, width: 64, height: 64,
  }, { sequence: 1 });
  await new Promise((resolve) => setTimeout(resolve, 0));
  const concurrentPlan = planWasmDashboardResources(dashboardSupersedeWorker, [
    { stableId: 1n, derivedBytes: 8n, lastUsed: 1n, visible: true },
  ], 8n);
  await rejectedSuperseded(supersededAggregate.result);
  const retainedAfterCancellation = await concurrentPlan;
  if (retainedAfterCancellation.retained.join(",") !== "true" || retainedAfterCancellation.retainedBytes !== 8n) {
    throw new Error("dashboard plan did not recover the shared arena after aggregate cancellation");
  }
  await dashboardSupersedeWorker.dispose();

  const staleWorker = createXygWasmWorker({
    workerUrl: "/packages/xy-client/dist/wasm-worker.js", wasm: wasmModule, maxArenaBytes: 8 * 1024 * 1024,
  });
  await staleWorker.ready;
  const currentAggregate = aggregateWasmBin2d(staleWorker, {
    x: checkpointPoints, y: checkpointPoints, x0: 0, x1: 1, y0: 0, y1: 1, width: 64, height: 64,
  }, { sequence: 2 });
  const staleScene = staleWorker.validateScene(canonicalSceneV9(), { sequence: 1, transfer: false });
  await rejected(staleScene.result, "XYG_WASM_STALE_SEQUENCE", 7);
  const current = await currentAggregate.result;
  if (current.maxCount !== 100_000) throw new Error("stale scene request cancelled the current aggregate");
  await staleWorker.dispose();

  for (const [name, invoke] of [
    ["validate", (w) => w.validateScene(canonicalSceneV9(), { sequence: 2, transfer: false })],
    ["paint", (w) => w.prepareScene(canonicalSceneV9(), { sequence: 2, transfer: false })],
    ["compile", (w) => w.compileScene(packed.slice(0), { sequence: 2, transfer: false })],
    ["compile_paint", (w) => w.compilePrepareScene(packed.slice(0), { sequence: 2, transfer: false })],
  ]) {
    const operationWorker = createXygWasmWorker({
      workerUrl: "/packages/xy-client/dist/wasm-worker.js", wasm: wasmModule, maxArenaBytes: 8 * 1024 * 1024,
    });
    await operationWorker.ready;
    const pendingAggregate = aggregateWasmBin2d(operationWorker, {
      x: checkpointPoints, y: checkpointPoints, x0: 0, x1: 1, y0: 0, y1: 1, width: 64, height: 64,
    }, { sequence: 1 });
    const nextOperation = invoke(operationWorker);
    try {
      await rejectedSuperseded(pendingAggregate.result);
      await nextOperation.result;
    } catch (error) {
      throw new Error(`aggregate supersession by ${name} failed: ${error.message}`);
    } finally {
      await operationWorker.dispose();
    }
  }

  for (const fixture of [
    { aggregateStepTrap: true },
    { aggregateOutputOutOfRange: true },
  ]) {
    const checkpointFailure = createXygWasmWorker({
      workerUrl: "/packages/xy-client/dist/wasm-worker.js",
      wasm: await fixtureModule(fixture),
      maxArenaBytes: 1024,
    });
    await checkpointFailure.ready;
    const failed = aggregateWasmBin2d(checkpointFailure, {
      x: [0.5], y: [0.5], x0: 0, x1: 1, y0: 0, y1: 1, width: 1, height: 1,
    }, { sequence: 1 });
    await rejected(failed.result, "XYG_WASM_TRAP");
    await rejected(
      checkpointFailure.validateScene(canonicalSceneV9(), { sequence: 2 }).result,
      "XYG_WASM_NOT_READY",
    );
    await checkpointFailure.dispose();
  }

  const cleanupTrapWorker = createXygWasmWorker({
    workerUrl: "/packages/xy-client/dist/wasm-worker.js",
    wasm: await fixtureModule({ cancelTrap: true }),
    maxArenaBytes: 1024,
  });
  await cleanupTrapWorker.ready;
  const cleanupTrapAggregate = aggregateWasmBin2d(cleanupTrapWorker, {
    x: [0.5], y: [0.5], x0: 0, x1: 1, y0: 0, y1: 1, width: 1, height: 1,
  }, { sequence: 1 });
  const cleanupTrapNext = cleanupTrapWorker.validateScene(
    canonicalSceneV9(), { sequence: 2, transfer: false },
  );
  await rejected(cleanupTrapAggregate.result, "XYG_WASM_TRAP");
  await rejected(cleanupTrapNext.result, "XYG_WASM_TRAP");
  await cleanupTrapWorker.dispose();

  const cancelTrapWorker = createXygWasmWorker({
    workerUrl: "/packages/xy-client/dist/wasm-worker.js",
    wasm: await fixtureModule({ cancelTrap: true }),
    maxArenaBytes: 1024,
  });
  await cancelTrapWorker.ready;
  const cancelTrapAggregate = aggregateWasmBin2d(cancelTrapWorker, {
    x: [0.5], y: [0.5], x0: 0, x1: 1, y0: 0, y1: 1, width: 1, height: 1,
  }, { sequence: 1 });
  await new Promise((resolve) => setTimeout(resolve, 0));
  cancelTrapAggregate.cancel();
  await rejected(cancelTrapAggregate.result, "XYG_WASM_CANCELLED");
  await new Promise((resolve) => setTimeout(resolve, 0));
  await rejected(
    cancelTrapWorker.validateScene(canonicalSceneV9(), { sequence: 2 }).result,
    "XYG_WASM_NOT_READY",
  );
  await cancelTrapWorker.dispose();

  const malformed = canonicalSceneV9();
  malformed[0] = 0;
  await rejected(
    worker.validateScene(malformed, { sequence: 13 }).result,
    "XYG_WASM_MALFORMED_SCENE",
    5,
  );
  await rejected(
    worker.validateScene(canonicalSceneV9(), { sequence: 9 }).result,
    "XYG_WASM_STALE_SEQUENCE",
    7,
  );

  const beforeRejected = await worker.validateScene(canonicalSceneV9(), { sequence: 14 }).result;
  const cancelled = worker.validateScene(canonicalSceneV9(), { sequence: 15 });
  cancelled.cancel();
  await rejected(cancelled.result, "XYG_WASM_CANCELLED", 6);
  const afterRejected = await worker.validateScene(canonicalSceneV9(), { sequence: 16 }).result;
  // The final success copies exactly once; cancellation may suppress its
  // deferred copy when it wins the race. Stale work copies zero.
  const rejectedCopies = afterRejected.copyCount - beforeRejected.copyCount;
  if (rejectedCopies < 1 || rejectedCopies > 2
      || afterRejected.copyBytesLo !== 480 * afterRejected.copyCount) {
    throw new Error(`rejected staging copies were not counted: ${JSON.stringify(afterRejected)}`);
  }
  await worker.dispose();
  try {
    worker.validateScene(canonicalSceneV9());
    throw new Error("disposed worker accepted work");
  } catch (error) {
    if (!(error instanceof XygWasmError) || error.code !== "XYG_WASM_DISPOSED") throw error;
  }

  const bounded = createXygWasmWorker({
    workerUrl: "/packages/xy-client/dist/wasm-worker.js",
    wasm: wasmModule,
    maxArenaBytes: 256,
  });
  await bounded.ready;
  await rejected(
    bounded.validateScene(new Uint8Array(257), { sequence: 1 }).result,
    "XYG_WASM_RESOURCE_LIMIT",
    3,
  );
  await bounded.dispose();

  const byBytes = createXygWasmWorker({
    workerUrl: "/packages/xy-client/dist/wasm-worker.js",
    wasm: wasmBytes.slice(0),
    maxArenaBytes: 1024,
  });
  await byBytes.ready;
  const detached = canonicalSceneV9().buffer;
  await byBytes.validateScene(detached, { sequence: 1 }).result;
  try {
    byBytes.validateScene(detached, { sequence: 2 });
    throw new Error("detached scene buffer was accepted");
  } catch (error) {
    if (!(error instanceof XygWasmError) || error.code !== "XYG_WASM_INVALID_ARGUMENT") throw error;
  }
  await byBytes.validateScene(canonicalSceneV9(), { sequence: 3 }).result;
  await byBytes.dispose();

  // Explicit user URL is supported and is the only branch allowed to fetch
  // WASM. It is local here; the server rejects every unrecognized path.
  const byUrl = createXygWasmWorker({
    workerUrl: "/packages/xy-client/dist/wasm-worker.js",
    wasm: "/packages/xy-client/dist/xyg-wasm.wasm",
    maxArenaBytes: 1024,
  });
  await byUrl.ready;
  await byUrl.dispose();

  // Redirects are rejected rather than following a caller's local URL to a
  // different (possibly remote) asset.
  const redirected = createXygWasmWorker({
    workerUrl: "/packages/xy-client/dist/wasm-worker.js",
    wasm: "/redirect.wasm",
  });
  await rejected(redirected.ready, "XYG_WASM_INIT_FAILED");
  await redirected.dispose();

  const trapped = createXygWasmWorker({
    workerUrl: "/packages/xy-client/dist/wasm-worker.js",
    wasm: await fixtureModule({ trap: true }),
    maxArenaBytes: 1024,
  });
  await trapped.ready;
  await rejected(
    trapped.validateScene(canonicalSceneV9(), { sequence: 1 }).result,
    "XYG_WASM_TRAP",
  );
  await trapped.dispose();

  const doubleTrapped = createXygWasmWorker({
    workerUrl: "/packages/xy-client/dist/wasm-worker.js",
    wasm: await fixtureModule({ trap: true, disposeTrap: true }),
    maxArenaBytes: 1024,
  });
  await doubleTrapped.ready;
  await rejected(
    doubleTrapped.validateScene(canonicalSceneV9(), { sequence: 1 }).result,
    "XYG_WASM_TRAP",
  );
  await doubleTrapped.dispose();

  const unsigned = createXygWasmWorker({
    workerUrl: "/packages/xy-client/dist/wasm-worker.js",
    wasm: await fixtureModule({ highBitDiagnostics: true }),
    maxArenaBytes: 1024,
  });
  const unsignedReady = await unsigned.ready;
  if (unsignedReady.copyCount !== 0x80000000
      || unsignedReady.copyBytesLo !== 0x80000000
      || unsignedReady.copyBytesHi !== 1) {
    throw new Error(`unsigned diagnostics lost their u32 values: ${JSON.stringify(unsignedReady)}`);
  }
  const combinedCopyBytes = (BigInt(unsignedReady.copyBytesHi) << 32n)
    | BigInt(unsignedReady.copyBytesLo);
  if (combinedCopyBytes !== 0x180000000n) {
    throw new Error(`split-u64 copy accounting was corrupted: ${combinedCopyBytes}`);
  }
  await unsigned.dispose();

  const stalePalette = createXygWasmWorker({
    workerUrl: "/packages/xy-client/dist/wasm-worker.js",
    wasm: await fixtureModule({ paletteVersion: 99 }),
    maxArenaBytes: 1024,
  });
  await rejected(stalePalette.ready, "XYG_WASM_INIT_FAILED");
  await stalePalette.dispose();

  const malformedModule = await WebAssembly.compile(
    new Uint8Array([0, 97, 115, 109, 1, 0, 0, 0]),
  );
  const failed = createXygWasmWorker({
    workerUrl: "/packages/xy-client/dist/wasm-worker.js",
    wasm: malformedModule,
  });
  await rejected(failed.ready, "XYG_WASM_INIT_FAILED");
  await failed.dispose();

  // Invalid source types fail before any Worker is allocated.
  try {
    createXygWasmWorker({
      workerUrl: "/packages/xy-client/dist/wasm-worker.js",
      wasm: /** @type {any} */ ({}),
    });
    throw new Error("invalid source was accepted");
  } catch (error) {
    if (!(error instanceof TypeError)) throw error;
  }
  return { ok: true, densityPolicy };
}

globalThis.__xygWasmFoundation = run().catch((error) => ({
  ok: false,
  error: error instanceof Error ? `${foundationStage}: ${error.name}: ${error.message}` : String(error),
}));
