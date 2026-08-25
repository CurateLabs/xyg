import { createXygWasmWorker, hydrateWasmPainter, renderWasmChart, XygWasmError } from "/packages/xy-client/dist/index.js";

async function frame() { await new Promise((resolve) => requestAnimationFrame(resolve)); }

async function visualEvidence(view, count) {
  // The Scene frame carries resolved f32 screen coordinates.  A WebGL canvas
  // may land on a device pixel either side of that coordinate after DPR
  // rounding, so one device pixel is the explicit cross-renderer tolerance.
  const canvas = view.canvas;
  // ChartView may use its shared WebGL host; in that case the visible canvas
  // is the 2D presentation surface that receives the authoritative readback.
  const present = canvas?.getContext("2d");
  if (!present || !canvas.width || !canvas.height) throw new Error("authored Scene did not retain a visible presentation canvas");
  const pixels = present.getImageData(0, 0, canvas.width, canvas.height).data;
  let litPixels = 0;
  for (let index = 3; index < pixels.length; index += 4) if (pixels[index] !== 0) litPixels++;
  if (!litPixels) throw new Error("authored Scene WebGL canvas is visually blank");
  const baseline = await createImageBitmap(await (await fetch(`/authored-scenes/authored-scene-${count}.png`)).blob());
  const expected = document.createElement("canvas");
  expected.width = canvas.width; expected.height = canvas.height;
  // Rust's resolved plot box is [62, 40, 856, 458] for this fixed authored
  // fixture. ChartView paints the same scene into its device-sized plot box.
  expected.getContext("2d").drawImage(baseline, 62, 40, 856, 458, 0, 0, canvas.width, canvas.height);
  const expectedPixels = expected.getContext("2d").getImageData(0, 0, canvas.width, canvas.height).data;
  let delta = 0, different = 0;
  for (let index = 0; index < pixels.length; index += 4) {
    const pixelDelta = Math.abs(pixels[index] - expectedPixels[index]) + Math.abs(pixels[index + 1] - expectedPixels[index + 1]) + Math.abs(pixels[index + 2] - expectedPixels[index + 2]);
    delta += pixelDelta;
    if (pixelDelta > 24) different++;
  }
  const svg = await (await fetch(`/authored-scenes/authored-scene-${count}.svg`)).text();
  const match = /data-xy-slot="annotation_label_box"[^>]* x="([0-9.]+)" y="([0-9.]+)" width="([0-9.]+)" height="([0-9.]+)"/.exec(svg);
  const box = view.root.querySelector('[data-xy-slot="annotation_label_box"]');
  if (!match || !box) throw new Error("authored Scene callout geometry is missing");
  const nativeBox = match.slice(1).map(Number);
  const browserBox = [box.style.left, box.style.top, box.style.width, box.style.height].map(parseFloat);
  const calloutGeometryDeltaPx = Math.max(...nativeBox.map((value, index) => Math.abs(value - browserBox[index])));
  return {
    browserVisualTolerancePx: 1,
    visibleCanvasPixels: litPixels,
    browserCanvasWidth: canvas.width,
    browserCanvasHeight: canvas.height,
    rustRasterWidth: baseline.width,
    rustRasterHeight: baseline.height,
    plotMeanRgbDelta: delta / (canvas.width * canvas.height * 3),
    plotDifferingFraction: different / (canvas.width * canvas.height),
    calloutGeometryDeltaPx,
  };
}

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
  for (const count of [100, 10_000, 100_000, 1_000_000]) {
    const scene = await (await fetch(`/authored-scenes/authored-scene-${count}.bin`)).arrayBuffer();
    const sceneBytes = scene.byteLength;
    if (!sceneBytes) throw new Error(`authored Scene fixture for ${count} is empty`);
    const sceneWorker = createXygWasmWorker({ workerUrl: "/packages/xy-client/dist/wasm-worker.js", wasm, maxArenaBytes: 384 * 1024 * 1024 });
    await sceneWorker.ready;
    const host = document.body.appendChild(document.createElement("div"));
    const started = performance.now();
    const prepared = await sceneWorker.prepareScene(scene, { transfer: false }).result;
    const view = hydrateWasmPainter(host, prepared, { workerPrepareMs: performance.now() - started });
    await frame(); await frame();
    const legendSemantics = host.querySelector('[data-xy-slot="legend"][role="list"]') !== null
      && host.querySelectorAll('[data-xy-slot="legend_item"][role="listitem"]').length > 0;
    const colorbarSemantics = host.querySelectorAll('[data-xy-slot="colorbar_tick"]').length > 0
      && host.querySelectorAll('[data-xy-slot="colorbar_minor_tick"]').length > 0;
    const annotationSemantics = host.querySelector('[data-xy-slot="annotation_label"][role="note"]') !== null
      && host.querySelector('[data-xy-slot="annotation_label_box"][aria-hidden="true"]') !== null;
    if (!legendSemantics || !colorbarSemantics || !annotationSemantics) {
      throw new Error(`authored Scene chrome/a11y did not hydrate for ${count}`);
    }
    rows.push({
      count,
      authoredScene: true,
      sceneBytes,
      painterBytes: prepared.painter.byteLength,
      firstPaintMs: performance.now() - started,
      legendSemantics,
      colorbarSemantics,
      annotationSemantics,
      ...prepared,
      ...view.wasmMetrics,
      ...await visualEvidence(view, count),
    });
    await view.destroy(); host.remove(); await sceneWorker.dispose();
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
