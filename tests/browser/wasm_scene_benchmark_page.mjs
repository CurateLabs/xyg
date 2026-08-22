import { createXygWasmWorker, renderWasmChart, XygWasmError } from "/packages/xy-client/dist/index.js";

async function frame() { await new Promise((resolve) => requestAnimationFrame(resolve)); }

async function run() {
  const wasm = await WebAssembly.compile(await (await fetch("/packages/xy-client/dist/xyg-wasm.wasm")).arrayBuffer());
  const rows = [];
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
  const fragmentedWorker = createXygWasmWorker({ workerUrl: "/packages/xy-client/dist/wasm-worker.js", wasm, maxArenaBytes: 16 * 1024 * 1024 });
  await fragmentedWorker.ready;
  const fragmentedSeries = Array.from({ length: 1025 }, (_, index) => ({
    kind: "scatter", x: new Float64Array([index]), y: new Float64Array([index]),
    style: { fillRgba: index % 2 ? [37, 99, 235, 255] : [240, 150, 30, 255] },
  }));
  const fragmentedStarted = performance.now();
  try {
    await renderWasmChart({ el: fragmentedHost, worker: fragmentedWorker, dataOwnership: "transfer", workerOwnership: "own", chart: { width: 800, height: 600, series: fragmentedSeries } });
    throw new Error("fragmented typed-series request unexpectedly rendered");
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
  await fragmentedWorker.dispose();
  return rows;
}

globalThis.__xygWasmSceneBenchmark = run();
