import { createXygWasmWorker, renderWasmChart, renderWasmScene, XygWasmError } from "/packages/xy-client/dist/index.js";

function writeDefaultSceneV8Chrome(bytes, view, body) {
  bytes.set([32, 32, 32, 217], body + 8); view.setFloat64(body + 16, 12, true);
  for (const offset of [body + 24, body + 112]) {
    bytes.set([0, 1, 1, 0, 0, 0, 0, 0], offset);
    bytes.set([32, 32, 32, 140], offset + 8); bytes.set([32, 32, 32, 36], offset + 12);
    bytes.set([32, 32, 32, 140], offset + 16); bytes.set([32, 32, 32, 140], offset + 24);
    bytes.set([32, 32, 32, 217], offset + 28);
    [1, 1, 1, 4, 1, 1, 0].forEach((value, index) => view.setFloat64(offset + 32 + index * 8, value, true));
  }
  view.setUint32(body + 212, 0xffffffff, true); view.setUint32(body + 220, 0xffffffff, true);
}

function coreScene(count) {
  const body = 160 + 3 * 16 + count * 56;
  const bytes = new Uint8Array(body + 232);
  const view = new DataView(bytes.buffer);
  bytes.set([88, 89, 71, 83]);
  view.setUint32(4, 8, true); view.setUint32(8, 160, true); view.setUint32(12, 56, true);
  view.setBigUint64(16, BigInt(count), true); view.setBigUint64(24, 3n, true);
  [800, 600, 60, 20, 780, 550].forEach((value, index) => view.setFloat64(32 + index * 8, value, true));
  view.setBigUint64(80, 1n, true); view.setBigUint64(88, 2n, true);
  [0, 1, 0, 1, 1, 1].forEach((value, index) => view.setFloat64(112 + index * 8, value, true));
  bytes.set([37, 99, 235, 255, 0, 0, 0, 0], 160); view.setFloat64(168, 0, true);
  bytes.set([0, 0, 0, 0, 16, 90, 180, 255], 176); view.setFloat64(184, 1.5, true);
  bytes.set([240, 150, 30, 255, 80, 40, 0, 255], 192); view.setFloat64(200, 1, true);
  const scatterEnd = Math.floor(count / 3), lineEnd = Math.floor(2 * count / 3);
  for (let index = 0; index < count; index++) {
    const record = 208 + index * 56;
    bytes[record + 1] = 1;
    bytes[record] = index < scatterEnd ? 0 : index < lineEnd ? 1 : 2;
    view.setUint32(record + 4, bytes[record], true);
    view.setBigUint64(record + 8, index < lineEnd && index >= scatterEnd ? 0xfeedn : BigInt(index), true);
    view.setFloat64(record + 16, 60 + (index % 997) / 996 * 720, true);
    view.setFloat64(record + 24, 20 + ((index * 37) % 991) / 990 * 530, true);
    if (index < scatterEnd) view.setFloat64(record + 48, 4, true);
    if (index >= lineEnd) {
      view.setFloat64(record + 32, 62 + (index % 997) / 996 * 718, true);
      view.setFloat64(record + 40, 22 + ((index * 37) % 991) / 990 * 528, true);
    }
  }
  writeDefaultSceneV8Chrome(bytes, view, body);
  return bytes;
}

function fragmentedCoreScene(count) {
  const bytes = coreScene(count);
  const scatterEnd = Math.floor(count / 3);
  for (let index = 0; index < scatterEnd; index++) bytes[208 + index * 56 + 2] = index % 2;
  return bytes;
}

async function frame() { await new Promise((resolve) => requestAnimationFrame(resolve)); }

async function run() {
  const wasm = await WebAssembly.compile(await (await fetch("/packages/xy-client/dist/xyg-wasm.wasm")).arrayBuffer());
  const worker = createXygWasmWorker({ workerUrl: "/packages/xy-client/dist/wasm-worker.js", wasm, maxArenaBytes: 64 * 1024 * 1024 });
  await worker.ready;
  const rows = [];
  for (const count of [10_000, 100_000, 1_000_000]) {
    const scene = coreScene(count), host = document.body.appendChild(document.createElement("div"));
    const heapBefore = performance.memory?.usedJSHeapSize ?? null;
    const started = performance.now();
    const view = await renderWasmScene({ el: host, scene, worker });
    await frame(); await frame();
    if (view.gpuTraces.length !== 3) throw new Error(`expected scatter/line/rect painter traces, got ${view.gpuTraces.length}`);
    const chromeLabels = host.querySelectorAll('[data-xy-label-kind="tick"]').length;
    const chromeRules = host.querySelectorAll("[data-xy-axis-side]").length;
    if (chromeLabels < 2 || chromeRules < 2) throw new Error(`expected Rust-authored chrome, got ${chromeLabels} labels and ${chromeRules} rules`);
    const heapAfter = performance.memory?.usedJSHeapSize ?? null;
    const lastTrace = view.gpuTraces.length - 1;
    rows.push({ count, sceneBytes: 160 + 3 * 16 + count * 56 + 232, traces: view.gpuTraces.length, chromeLabels, chromeRules, ...view.wasmMetrics,
      firstPaintMs: performance.now() - started,
      retainedJsHeapDelta: heapBefore === null ? null : Math.max(0, heapAfter - heapBefore),
      stableIdTail: String(view.sceneStableId(lastTrace, view.gpuTraces[lastTrace]._sceneIds.lo.length - 1)) });
    view.destroy(); host.remove();
  }
  for (const count of [100, 10_000, 100_000, 1_000_000]) {
    const chartWorker = createXygWasmWorker({ workerUrl: "/packages/xy-client/dist/wasm-worker.js", wasm, maxArenaBytes: 384 * 1024 * 1024 });
    await chartWorker.ready;
    const x = new Float64Array(count), y = new Float64Array(count);
    for (let index = 0; index < count; index++) { x[index] = (index % 1024) / 1023; y[index] = ((index * 37) % 1024) / 1023; }
    const host = document.body.appendChild(document.createElement("div"));
    const started = performance.now();
    const handle = await renderWasmChart({ el: host, worker: chartWorker, dataOwnership: "transfer", workerOwnership: "own", chart: { width: 800, height: 600, series: [{ kind: "scatter", x, y }] } });
    await frame(); await frame();
    const diagnostics = handle.diagnostics();
    if (diagnostics?.mainThreadRecordVisits !== 0 || diagnostics.framedSeries !== 1) {
      throw new Error(`typed-series framing scanned records on the main thread: ${JSON.stringify(diagnostics)}`);
    }
    rows.push({ count, typedSeries: true, firstPaintMs: performance.now() - started, ...diagnostics });
    await handle.dispose(); host.remove();
  }
  const fragmentedHost = document.body.appendChild(document.createElement("div"));
  const fragmentedStarted = performance.now();
  try {
    await renderWasmScene({ el: fragmentedHost, scene: fragmentedCoreScene(1_000_000), worker });
    throw new Error("fragmented million-record Scene unexpectedly rendered");
  } catch (error) {
    if (!(error instanceof XygWasmError) || error.code !== "XYG_WASM_RESOURCE_LIMIT" || error.status !== 3) throw error;
  }
  rows.push({
    count: 1_000_000,
    fragmented: true,
    rejectedTraceLimit: 1024,
    rejectionMs: performance.now() - fragmentedStarted,
    browserChildren: fragmentedHost.childNodes.length,
  });
  if (fragmentedHost.childNodes.length !== 0) throw new Error("fragmented benchmark allocated browser painter state");
  fragmentedHost.remove();
  await worker.dispose();
  return rows;
}

globalThis.__xygWasmSceneBenchmark = run();
