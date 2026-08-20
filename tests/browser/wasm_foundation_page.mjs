import {
  createXygWasmWorker,
  encodeWasmChart,
  encodeWasmColumns,
  renderWasmChart,
  renderWasmColumns,
  renderWasmScene,
  XygWasmError,
} from "/packages/xy-client/dist/index.js";

function writeDefaultSceneV8Chrome(bytes, view, body) {
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

function canonicalSceneV8({ authored = false } = {}) {
  const body = 160 + 16 + 56;
  const ticks = authored ? [0, 1, 0.5, 0, 1] : [];
  const text = authored
    ? ["Authored Cartesian chrome", "Horizontal measure", "Vertical measure"].map((value) => new TextEncoder().encode(value))
    : [new Uint8Array(), new Uint8Array(), new Uint8Array()];
  const textBytes = text.reduce((total, value) => total + value.length, 0);
  const bytes = new Uint8Array(body + 232 + textBytes + ticks.length * 8);
  const view = new DataView(bytes.buffer);
  bytes.set([88, 89, 71, 83], 0); // XYGS
  view.setUint32(4, 8, true);
  view.setUint32(8, 160, true);
  view.setUint32(12, 56, true);
  view.setBigUint64(16, 1n, true);
  view.setBigUint64(24, 1n, true);
  [100, 80, 10, 10, 90, 70].forEach((value, index) => {
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
  writeDefaultSceneV8Chrome(bytes, view, body);
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
    let tickOffset = body + 232;
    for (const value of text) {
      bytes.set(value, tickOffset);
      tickOffset += value.length;
    }
    for (const tick of ticks) {
      view.setFloat64(tickOffset, tick, true);
      tickOffset += 8;
    }
  }
  return bytes;
}

function fragmentedScene(count) {
  const records = 176;
  const body = records + count * 56;
  const bytes = new Uint8Array(body + 232);
  const view = new DataView(bytes.buffer);
  bytes.set([88, 89, 71, 83], 0);
  view.setUint32(4, 8, true); view.setUint32(8, 160, true); view.setUint32(12, 56, true);
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
  writeDefaultSceneV8Chrome(bytes, view, body);
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

async function fixtureModule({ trap = false, disposeTrap = false, highBitDiagnostics = false } = {}) {
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
    "xyg_wasm_output_ptr",
    "xyg_wasm_output_len",
    "xyg_wasm_last_error_ptr",
    "xyg_wasm_last_error_len",
    "xyg_wasm_copy_count",
    "xyg_wasm_copy_bytes_lo",
    "xyg_wasm_copy_bytes_hi",
    "xyg_wasm_last_scene_records",
    "xyg_wasm_last_scene_styles",
  ];
  const arities = [0, 1, 2, 4];
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
    0, 0, 0, 1, 1, 2, 1, 1, 2, 3, 3, 3, 3, 1, 1, 1, 1, 1, 1, 1, 1, 1,
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
    3, 8, 64 * 1024 * 1024, 1, 0, 0, 1024, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
    highBitDiagnostics ? highBit : 0,
    highBitDiagnostics ? highBit : 0,
    highBitDiagnostics ? 1 : 0,
    0, 0,
  ];
  const bodies = names.map((_, index) => {
    const instructions = (trap && index === 9) || (disposeTrap && index === 4)
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
    if (error.code !== code) throw new Error(`wanted ${code}, got ${error.code}`);
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
    expectedAbiVersion: 3,
    expectedSceneVersion: 8,
  };
}

async function run() {
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
    maxArenaBytes: 1024,
  });
  const ready = await worker.ready;
  if (ready.abiVersion !== 3 || ready.sceneVersion !== 8) {
    throw new Error(`unexpected versions ${JSON.stringify(ready)}`);
  }
  if (ready.memoryBytes < 64 * 1024) throw new Error("WASM reserved-memory diagnostics are missing");

  const canonical = canonicalSceneV8();
  const transferred = canonical.buffer;
  const valid = await worker.validateScene(transferred, { sequence: 10 }).result;
  if (transferred.byteLength !== 0) throw new Error("scene buffer was not transferred");
  if (valid.records !== 1 || valid.styles !== 1 || valid.copyCount !== 1) {
    throw new Error(`unexpected diagnostics ${JSON.stringify(valid)}`);
  }
  if (valid.copyBytesLo !== 464 || valid.copyBytesHi !== 0 || valid.arenaBytes !== 0) {
    throw new Error(`unexpected copy or arena diagnostics ${JSON.stringify(valid)}`);
  }

  const paint = await worker.prepareScene(canonicalSceneV8(), { sequence: 11 }).result;
  if (!(paint.painter instanceof ArrayBuffer) || paint.painter.byteLength < 280) {
    throw new Error("Rust Scene paint lowering did not return a transferable display list");
  }
  const host = document.body.appendChild(document.createElement("div"));
  const rendered = await renderWasmScene({ el: host, scene: canonicalSceneV8(), worker, transfer: false });
  if (!host.querySelector("canvas") || rendered.gpuTraces.length < 1) {
    throw new Error("public WASM Scene API did not hydrate the existing painter");
  }
  await new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve)));
  const labels = [...host.querySelectorAll('[data-xy-label-kind="tick"]')].map((node) => node.textContent);
  if (labels.length < 6 || !labels.includes("0.0") || !labels.includes("0.5") || !labels.includes("1.0")) {
    throw new Error(`Rust-authored Scene v8 chrome labels were not painted: ${JSON.stringify(labels)}`);
  }
  if (host.querySelectorAll('[data-xy-axis-side="bottom"], [data-xy-axis-side="left"]').length < 2) {
    throw new Error("Rust-authored Scene v8 axis chrome was not painted");
  }
  if (rendered.sceneStableId(0, 0) !== 7n) throw new Error("canonical stable id was not preserved through painter hydration");
  rendered.destroy();
  host.remove();

  const authoredWorker = createXygWasmWorker({
    workerUrl: "/packages/xy-client/dist/wasm-worker.js",
    wasm: wasmModule,
    maxArenaBytes: 1024 * 1024,
  });
  await authoredWorker.ready;
  const authoredHost = document.body.appendChild(document.createElement("div"));
  const authored = await renderWasmScene({
    el: authoredHost,
    scene: canonicalSceneV8({ authored: true }),
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
  const authoredRegion = authoredHost.querySelector('.xy[role="region"]');
  if (authoredRegion?.getAttribute("aria-label") !== "Chart: Authored Cartesian chrome"
      || !authoredRegion.textContent.includes("X axis (Horizontal measure)")
      || !authoredRegion.textContent.includes("Y axis (Vertical measure)")) {
    throw new Error("Rust-authored title and axis labels were not exposed to accessibility text");
  }
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
        x: [0.2, 0.8],
        y: [0.3, 0.7],
        stableIdBase: 70n,
        diameter: 8,
      },
      {
        kind: "line",
        x: [0.1, 0.5, 0.9],
        y: [0.2, 0.6, 0.4],
        stableIdBase: 80n,
        style: { strokeRgba: [15, 23, 42, 255], strokeWidth: 2, fillRgba: [0, 0, 0, 0] },
      },
    ],
  };
  const chartPacked = encodeWasmChart(chart);
  const chartFlags = new DataView(chartPacked).getUint32(12, true);
  if ((chartFlags & 3) !== 3) {
    throw new Error(`chart ergonomics did not set autoMargins|autoDomain flags: ${chartFlags}`);
  }
  if (new Uint8Array(chartPacked).subarray(0, 4).join(",") !== "88,89,67,67") {
    throw new Error("chart ergonomics encoder did not emit XYCC");
  }
  const chartHost = document.body.appendChild(document.createElement("div"));
  const chartView = await renderWasmChart({
    el: chartHost,
    chart,
    worker: chartWorker,
    transfer: false,
  });
  if (!chartHost.querySelector("canvas") || chartView.gpuTraces.length < 1) {
    throw new Error("chart ergonomics public API did not hydrate the existing painter");
  }
  if (chartView.sceneStableId(0, 0) !== 70n) {
    throw new Error("chart ergonomics stable id was not preserved through painter hydration");
  }
  chartView.destroy();
  chartHost.remove();
  await chartWorker.dispose();

  const malformed = canonicalSceneV8();
  malformed[0] = 0;
  await rejected(
    worker.validateScene(malformed, { sequence: 13 }).result,
    "XYG_WASM_MALFORMED_SCENE",
    5,
  );
  await rejected(
    worker.validateScene(canonicalSceneV8(), { sequence: 9 }).result,
    "XYG_WASM_STALE_SEQUENCE",
    7,
  );

  const cancelled = worker.validateScene(canonicalSceneV8(), { sequence: 14 });
  cancelled.cancel();
  await rejected(cancelled.result, "XYG_WASM_CANCELLED", 6);
  const afterRejected = await worker.validateScene(canonicalSceneV8(), { sequence: 15 }).result;
  // Cancellation may suppress the deferred staging copy when it wins the race.
  // Count every completed arena resize; bytes must match the canonical scene size.
  if (afterRejected.copyCount < 6 || afterRejected.copyCount > 7
      || afterRejected.copyBytesLo !== 464 * afterRejected.copyCount) {
    throw new Error(`rejected staging copies were not counted: ${JSON.stringify(afterRejected)}`);
  }
  await worker.dispose();
  try {
    worker.validateScene(canonicalSceneV8());
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
  const detached = canonicalSceneV8().buffer;
  await byBytes.validateScene(detached, { sequence: 1 }).result;
  try {
    byBytes.validateScene(detached, { sequence: 2 });
    throw new Error("detached scene buffer was accepted");
  } catch (error) {
    if (!(error instanceof XygWasmError) || error.code !== "XYG_WASM_INVALID_ARGUMENT") throw error;
  }
  await byBytes.validateScene(canonicalSceneV8(), { sequence: 3 }).result;
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
    trapped.validateScene(canonicalSceneV8(), { sequence: 1 }).result,
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
    doubleTrapped.validateScene(canonicalSceneV8(), { sequence: 1 }).result,
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
  error: error instanceof Error ? `${error.name}: ${error.message}` : String(error),
}));
