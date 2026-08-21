import {
  aggregateWasmBin2d,
  createXygWasmWorker,
  frameWasmChart,
  encodeWasmAggregate,
  encodeWasmColumns,
  hydrateWasmPainter,
  renderWasmChart,
  renderWasmColumns,
  renderWasmScene,
  XygWasmError,
  XygWasmTemporalController,
} from "/packages/xy-client/dist/index.js";

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
  const hasLegend = legend || legendSymbols != null;
  const legendBytes = hasLegend ? primaryLegend(legendSymbols || [0]) : new Uint8Array();
  const bytes = new Uint8Array(body + 240 + textBytes + ticks.length * 8 + legendBytes.length);
  const view = new DataView(bytes.buffer);
  bytes.set([88, 89, 71, 83], 0); // XYGS
  view.setUint32(4, 10, true);
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
    let tickOffset = body + 240;
    for (const value of text) {
      bytes.set(value, tickOffset);
      tickOffset += value.length;
    }
    for (const tick of ticks) {
      view.setFloat64(tickOffset, tick, true);
      tickOffset += 8;
    }
    bytes.set(legendBytes, tickOffset);
  } else {
    bytes.set(legendBytes, body + 240);
  }
  return bytes;
}

function primaryAnnotationSceneV10() {
  const recordCount = 5, styleCount = 3;
  const records = 160 + styleCount * 16;
  const body = records + recordCount * 56;
  const bytes = new Uint8Array(body + 240), view = new DataView(bytes.buffer);
  bytes.set([88, 89, 71, 83], 0); // XYGS
  view.setUint32(4, 10, true); view.setUint32(8, 160, true); view.setUint32(12, 56, true);
  view.setBigUint64(16, BigInt(recordCount), true); view.setBigUint64(24, BigInt(styleCount), true);
  [100, 80, 10, 10, 90, 70].forEach((value, index) => view.setFloat64(32 + index * 8, value, true));
  view.setBigUint64(80, 1n, true); view.setBigUint64(88, 2n, true);
  [0, 1, 0, 1, 1, 1].forEach((value, index) => view.setFloat64(112 + index * 8, value, true));
  // rule, band, marker styles
  bytes.set([0, 0, 0, 0, 255, 0, 0, 255], 160); view.setFloat64(168, 2, true);
  bytes.set([0, 255, 0, 64, 0, 255, 0, 64], 176); view.setFloat64(184, 0, true);
  bytes.set([0, 0, 255, 255, 255, 255, 255, 255], 192); view.setFloat64(200, 1.5, true);
  const writeRecord = (index, { kind, style, id, x0, y0, x1 = 0, y1 = 0, diameter = 0, symbol = 0 }) => {
    const offset = records + index * 56;
    bytes[offset] = kind; bytes[offset + 1] = 1; bytes[offset + 2] = symbol;
    view.setUint32(offset + 4, style, true); view.setBigUint64(offset + 8, id, true);
    [x0, y0, x1, y1].forEach((value, coordinate) => view.setFloat64(offset + 16 + coordinate * 8, value, true));
    view.setFloat64(offset + 48, diameter, true);
  };
  const prefix = 0x5859000000000000n;
  writeRecord(0, { kind: 1, style: 0, id: prefix | (1n << 40n), x0: 30, y0: 10 });
  writeRecord(1, { kind: 1, style: 0, id: prefix | (1n << 40n), x0: 30, y0: 70 });
  writeRecord(2, { kind: 2, style: 1, id: prefix | (2n << 40n) | 1n, x0: 40, y0: 10, x1: 50, y1: 70 });
  writeRecord(3, { kind: 0, style: 2, id: prefix | (3n << 40n) | 2n, x0: 60, y0: 40, diameter: 10 });
  writeRecord(4, { kind: 0, style: 2, id: prefix | (3n << 40n) | 3n, x0: 70, y0: 50, diameter: 10 });
  writeDefaultSceneV9Chrome(bytes, view, body);
  return bytes;
}

function fragmentedScene(count) {
  const records = 176;
  const body = records + count * 56;
  const bytes = new Uint8Array(body + 240);
  const view = new DataView(bytes.buffer);
  bytes.set([88, 89, 71, 83], 0);
  view.setUint32(4, 10, true); view.setUint32(8, 160, true); view.setUint32(12, 56, true);
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
    "xyg_wasm_scene_compile",
    "xyg_wasm_scene_compile_prepare",
    "xyg_wasm_aggregate_bin2d",
    "xyg_wasm_aggregate_step",
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
  ];
  const arities = [0, 1, 2, 3, 4];
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
    0, 0, 0, 1, 1, 2, 1, 1, 2, 4, 4, 4, 4, 4, 3, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 3,
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
    6, 10, 64 * 1024 * 1024, 1, 0, 0, 1024, 0, 0, 0, 0, 0, 0,
    aggregateStepTrap || aggregateOutputOutOfRange || cancelTrap ? 8 : 0,
    cancelTrap ? 8 : 0,
    aggregateOutputOutOfRange ? 65520 : 0,
    aggregateOutputOutOfRange ? 32 : 0,
    0, 0,
    highBitDiagnostics ? highBit : 0,
    highBitDiagnostics ? highBit : 0,
    highBitDiagnostics ? 1 : 0,
    0, 0, 0, 0,
  ];
  const bodies = names.map((_, index) => {
    const instructions = (trap && index === 9) || (disposeTrap && index === 4)
      || (cancelTrap && index === 8)
      || (aggregateStepTrap && index === 14)
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
    expectedAbiVersion: 6,
    expectedSceneVersion: 10,
  };
}

let foundationStage = "startup";
async function run() {
  const sharedFixture = await fetch("/tests/fixtures/figure_scene_v3.json").then((response) => response.json());
  const wasmResponse = await fetch("/packages/xy-client/dist/xyg-wasm.wasm");
  const wasmBytes = await wasmResponse.arrayBuffer();
  const wasmModule = await WebAssembly.compile(wasmBytes);

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
    type: "series.compile_paint",
    requestId: 105,
    sequence: 2,
    prefix: rawSeries.prefix,
    columns: rawSeries.columns,
    byteLength: rawSeries.byteLength,
  });
  if (!afterMalformedCombined.ok) {
    throw new Error(`combined-length rejection destroyed worker: ${JSON.stringify(afterMalformedCombined)}`);
  }
  await malformedSeriesWorker.request({ type: "dispose", requestId: 106 });
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
    maxArenaBytes: 4096,
  });
  const ready = await worker.ready;
  if (ready.abiVersion !== 6 || ready.sceneVersion !== 10) {
    throw new Error(`unexpected versions ${JSON.stringify(ready)}`);
  }
  if (ready.memoryBytes < 64 * 1024) throw new Error("WASM reserved-memory diagnostics are missing");

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
  await temporal.setCursor(25n);
  if (temporal.state.cursor !== 25n || temporalEvents.length < 1
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

  const canonical = canonicalSceneV9();
  const transferred = canonical.buffer;
  const valid = await worker.validateScene(transferred, { sequence: 10 }).result;
  if (transferred.byteLength !== 0) throw new Error("scene buffer was not transferred");
  if (valid.records !== 1 || valid.styles !== 1 || valid.copyCount !== 1) {
    throw new Error(`unexpected diagnostics ${JSON.stringify(valid)}`);
  }
  if (valid.copyBytesLo !== 472 || valid.copyBytesHi !== 0 || valid.arenaBytes !== 0) {
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
    throw new Error(`Rust-authored Scene v10 chrome labels were not painted: ${JSON.stringify(labels)}`);
  }
  if (host.querySelectorAll('[data-xy-axis-side="bottom"], [data-xy-axis-side="left"]').length < 2) {
    throw new Error("Rust-authored Scene v10 axis chrome was not painted");
  }
  if (rendered.sceneStableId(0, 0) !== 7n) throw new Error("canonical stable id was not preserved through painter hydration");
  rendered.destroy();
  host.remove();

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
        stableIdBase: 70n,
        diameter: 8,
      },
      {
        kind: "line",
        x: new Float64Array([0.1, 0.5, 0.9]),
        y: new Float64Array([0.2, 0.6, 0.4]),
        stableIdBase: 80n,
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
        stableIdBase: 100n,
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
  if (fixtureMagic !== sharedFixture.wasm_typed_series_v1.magic) {
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
  ]) {
    try {
      frameWasmChart({ width: 10, height: 10, series: [malformedSeries] });
      throw new Error("chart ergonomics accepted inapplicable or negative geometry");
    } catch (error) {
      if (!(error instanceof TypeError)) throw error;
    }
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
  if (chartView.sceneStableId(0, 0) !== 70n) {
    throw new Error("chart ergonomics stable id was not preserved through painter hydration");
  }
  const defaultLine = chartView.gpuTraces.find((gpu) => gpu.trace?.kind === "line")?.trace;
  if (defaultLine?.style?.color !== "rgba(37 99 235 / 1)" || defaultLine.style.width !== 1.5) {
    throw new Error(`Rust line defaults drifted from the shared fixture: ${JSON.stringify(defaultLine?.style)}`);
  }
  const renderedKinds = new Set(chartView.gpuTraces.map((gpu) => gpu.trace?.kind));
  for (const expected of ["scatter", "line", "box", "area"]) {
    if (!renderedKinds.has(expected)) throw new Error(`Rust typed-series painter omitted ${expected}`);
  }
  const chartDiagnostics = chartView.diagnostics();
  if (!chartDiagnostics || chartDiagnostics.arenaHighWaterBytes < chartPacked.byteLength
      || chartDiagnostics.memoryHighWaterBytes !== chartDiagnostics.memoryBytes) {
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
  foundationStage = "explicit typed-series transfer";
  await transferWorker.compilePrepareSeries(frameWasmChart({
    width: 320, height: 240, series: [{ kind: "scatter", x: transferredX, y: transferredY }],
  }), { transfer: true }).result;
  if (transferredX.byteLength !== 0 || transferredY.byteLength !== 0) {
    throw new Error("explicit typed-series transfer did not detach caller buffers");
  }
  await transferWorker.dispose();

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
  await rejected(firstAggregate.result, "XYG_WASM_CANCELLED", 6);
  const newer = await newerAggregate.result;
  if (newer.maxCount !== 1 || newer.width !== 2) throw new Error("new viewport did not progress after aggregate checkpoint cancellation");
  await checkpointWorker.dispose();

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
      await rejected(pendingAggregate.result, "XYG_WASM_CANCELLED", 6);
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

  const cancelled = worker.validateScene(canonicalSceneV9(), { sequence: 14 });
  cancelled.cancel();
  await rejected(cancelled.result, "XYG_WASM_CANCELLED", 6);
  const afterRejected = await worker.validateScene(canonicalSceneV9(), { sequence: 15 }).result;
  // Cancellation may suppress the deferred staging copy when it wins the race.
  // Count every completed arena resize; bytes must match the canonical scene size.
  if (afterRejected.copyCount < 6 || afterRejected.copyCount > 7
      || afterRejected.copyBytesLo !== 472 * afterRejected.copyCount) {
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
  return { ok: true };
}

globalThis.__xygWasmFoundation = run().catch((error) => ({
  ok: false,
  error: error instanceof Error ? `${foundationStage}: ${error.name}: ${error.message}` : String(error),
}));
