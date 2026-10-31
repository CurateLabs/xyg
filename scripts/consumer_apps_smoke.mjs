// Real application proof; test runner may use Python, Node consumer itself does not.
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { readFile, writeFile } from 'node:fs/promises';
import { execFileSync } from 'node:child_process';
import { parseArgs } from 'node:util';
import { chromium } from 'playwright';
import { qualifyPackagedConsumers } from './packaged_consumer_browser.mjs';
import { qualifyStreamlitGraphForge } from './streamlit_graphforge_browser.mjs';
const { values } = parseArgs({ options: {
  chromium: { type: 'string' }, 'streamlit-url': { type: 'string' }, 'node-url': { type: 'string' },
  'python-html-url': { type: 'string' }, 'qualification-url': { type: 'string' },
} });
assert.ok(values.chromium && values['streamlit-url'] && values['node-url']
  && values['python-html-url'] && values['qualification-url']);
const launchArgs = ['--no-sandbox', '--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist'];
const browser = await chromium.launch({ executablePath: values.chromium, args: launchArgs });
const report = { schema: 1, commit: execFileSync('git', ['rev-parse', 'HEAD'], {encoding: 'utf8'}).trim(),
  browser: browser.version(), node: process.version, launchArgs, hosts: {}, hashes: {} };
// An incomplete asynchronous journey must never exit successfully without proof.
process.exitCode = 1;
const paint = async (frame, nonWhite = false) => {
  // Read the actual composited plot: GPU presentation buffers may already be cleared.
  const plot = frame.locator('canvas[style*="touch-action"]').first();
  await plot.waitFor();
  const png = await plot.screenshot();
  return frame.evaluate(async ({encoded, nonWhite}) => {
    const bytes = Uint8Array.from(atob(encoded), c => c.charCodeAt(0));
    const image = await createImageBitmap(new Blob([bytes], { type: 'image/png' }));
    const canvas = document.createElement('canvas');
    canvas.width = image.width; canvas.height = image.height;
    const context = canvas.getContext('2d');
    context.drawImage(image, 0, 0); image.close();
    const pixels = context.getImageData(0, 0, canvas.width, canvas.height).data;
    let colored = 0;
    for (let i = 0; i < pixels.length; i += 4)
      if (pixels[i + 3] && (nonWhite ? Math.min(pixels[i], pixels[i + 1], pixels[i + 2]) < 200
        : Math.max(pixels[i], pixels[i + 1], pixels[i + 2]) - Math.min(pixels[i], pixels[i + 1], pixels[i + 2]) > 50)) colored++;
    return colored;
  }, { encoded: png.toString('base64'), nonWhite });
};

try {
  report.packagedQualification = await qualifyPackagedConsumers(browser,
    { python: values['python-html-url'], node: values['qualification-url'] }, 'consumer-apps-smoke');
  const node = await browser.newPage({ viewport: { width: 1000, height: 800 } });
  const errors = [];
  const requested = [];
  node.on('pageerror', error => errors.push(error.message));
  node.on('request', request => {
    assert.equal(new URL(request.url()).origin, values['node-url']); requested.push(new URL(request.url()).pathname);
  });
  await node.addInitScript(() => {
    const NativeWorker = globalThis.Worker;
    globalThis.consumerWorkers = [];
    globalThis.Worker = class extends NativeWorker {
      constructor(...args) {
        super(...args);
        this.consumerRecord = { terminated: false };
        globalThis.consumerWorkers.push(this.consumerRecord);
      }
      terminate() { this.consumerRecord.terminated = true; return super.terminate(); }
    };
  });
  await node.goto(values['node-url']);
  await node.waitForFunction(() => document.getElementById('status').textContent === 'scatter · 8 rows');
  // Poll synchronously: waitForFunction treats an async predicate's Promise as truthy.
  await node.evaluate(async () => { globalThis.consumerApp = await import('/app.js'); });
  await node.waitForFunction(() => document.querySelector('#chart canvas')?.width > 0);
  const pixels = {};
  for (const kind of ['scatter', 'line', 'bar', 'graph']) {
    await node.selectOption('#kind', kind);
    await node.waitForFunction(k => document.getElementById('status').textContent === `${k} · 8 rows`, kind);
    await node.waitForTimeout(250);
    pixels[kind] = await paint(node);
    assert.ok(pixels[kind] > 5, `${kind}: no colored chart pixels`);
  }
  await node.selectOption('#kind', 'scatter');
  await node.click('#update');
  await node.waitForFunction(() => document.getElementById('status').textContent === 'scatter · 16 rows');
  // A trusted shift-drag exercises browser selection rather than injecting an event.
  const box = await node.locator('#chart canvas[style*="touch-action"]').first().boundingBox();
  await node.keyboard.down('Shift');
  await node.mouse.move(box.x + 500, box.y + 200); await node.mouse.down();
  await node.mouse.move(box.x + 150, box.y + 120, { steps: 8 }); await node.mouse.up();
  await node.keyboard.up('Shift');
  await node.waitForFunction(() => document.getElementById('selection').textContent === 'Selection changed in the browser');
  const svg = await node.request.get(`${values['node-url']}/export.svg?kind=scatter&count=16`);
  assert.equal(svg.status(), 200); assert.match(await svg.text(), /<svg/);
  assert.equal((await node.request.get(`${values['node-url']}/spec?count=999`)).status(), 400);
  await node.screenshot({ path: 'consumer-apps-smoke/node.png' });
  // Retain the actual outgoing view; DOM removal alone cannot prove teardown.
  await node.waitForFunction(() => {
    const { view } = globalThis.consumerApp;
    const axes = view?._wasmTicks?.diagnostics()?.axisIds;
    return axes?.includes('x') && axes?.includes('y');
  });
  await node.evaluate(async () => {
    const { view } = await import('/app.js');
    if (!view.gl || !view._listeners.length || !globalThis.consumerWorkers.length)
      throw new Error('cleanup proof requires an attached live view, listeners and Worker');
    globalThis.outgoingView = view;
    globalThis.outgoingGl = view.gl;
  });
  await node.click('#dispose');
  await node.waitForFunction(() => {
    const { view } = globalThis.consumerApp;
    const outgoing = globalThis.outgoingView;
    return view === undefined && outgoing._destroyed && outgoing.gl === null
      && outgoing._wasmTicks === null && outgoing._listeners.length === 0
      && !outgoing._raf && globalThis.outgoingGl.isContextLost()
      && globalThis.consumerWorkers.every(worker => worker.terminated);
  }, undefined, { timeout: 10_000 });
  assert.equal(await node.locator('#chart canvas').count(), 0);
  await node.selectOption('#kind', 'line');
  await node.waitForFunction(() => document.getElementById('status').textContent === 'line · 8 rows');
  assert.ok(await paint(node) > 5);
  await node.waitForFunction(() => {
    const { view } = globalThis.consumerApp;
    const axes = view?._wasmTicks?.diagnostics()?.axisIds;
    return axes?.includes('x') && axes?.includes('y');
  });
  assert.ok(requested.includes('/assets/wasm-worker.js') && requested.includes('/assets/xyg-wasm.wasm'));
  assert.deepEqual(errors, []);
  report.hosts.node = { kinds: pixels, update: true, browserSelection: true, export: true,
    disposeRemount: true, outgoingViewReleased: true, workersTerminated: true,
    glContextReleased: true, localWorkerAndWasmRequested: true, rustTicksAdmitted: true, errors };

  const missing = await browser.newPage();
  await missing.addInitScript(() => {
    globalThis.__xygStandaloneObserver = event => { if (event.phase === 'ticks_error') globalThis.tickFailure = event; };
  });
  await missing.route('**/spec?*', async route => {
    const response = await route.fetch();
    const spec = await response.json();
    spec.wasm_ticks.wasm = '/assets/missing.wasm';
    await route.fulfill({ response, json: spec });
  });
  await missing.goto(values['node-url']);
  await missing.waitForFunction(() => typeof globalThis.tickFailure?.code === 'string');
  assert.ok(await paint(missing) > 5, 'missing optional tick assets must preserve chart paint');
  report.hosts.node.missingWasmFailsClosed = true;
  await missing.close();

  const streamlit = await browser.newPage({ viewport: { width: 1100, height: 900 } });
  const streamlitErrors = [];
  streamlit.on('pageerror', error => streamlitErrors.push(error.message));
  await streamlit.goto(values['streamlit-url']);
  await streamlit.getByText('scatter · 8 rows', { exact: true }).waitFor();
  await streamlit.locator('iframe').waitFor();
  let frame = await (await streamlit.locator('iframe').elementHandle()).contentFrame();
  await frame.waitForTimeout(300);
  const before = await paint(frame);
  assert.ok(before > 5, 'Streamlit iframe has no colored chart pixels');
  await streamlit.getByRole('combobox').click();
  await streamlit.getByRole('option', { name: 'line', exact: true }).click();
  await streamlit.getByText('line · 8 rows', { exact: true }).waitFor();
  frame = await (await streamlit.locator('iframe').elementHandle()).contentFrame();
  await frame.waitForTimeout(300);
  assert.ok(await paint(frame) > 5);
  assert.equal(await streamlit.locator('iframe').count(), 1);
  const downloads = {};
  for (const format of ['svg', 'png']) {
    const [download] = await Promise.all([
      streamlit.waitForEvent('download'),
      streamlit.getByRole('button', { name: `Download ${format.toUpperCase()}`, exact: true }).click(),
    ]);
    assert.equal(download.suggestedFilename(), `chart.${format}`);
    assert.equal(await download.failure(), null);
    const path = `consumer-apps-smoke/${download.suggestedFilename()}`;
    await download.saveAs(path);
    const bytes = await readFile(path);
    if (format === 'svg') {
      const valid = await streamlit.evaluate(source => {
        const doc = new DOMParser().parseFromString(source, 'image/svg+xml');
        return !doc.querySelector('parsererror') && doc.documentElement.localName === 'svg'
          && doc.documentElement.namespaceURI === 'http://www.w3.org/2000/svg'
          && doc.querySelectorAll('path,polyline,line,rect,circle').length > 0;
      }, bytes.toString('utf8'));
      assert.ok(valid, 'SVG download must be a parsed chart document');
    } else {
      assert.deepEqual([...bytes.subarray(0, 8)], [137, 80, 78, 71, 13, 10, 26, 10]);
      const decoded = await streamlit.evaluate(async encoded => {
        const bytes = Uint8Array.from(atob(encoded), c => c.charCodeAt(0));
        const image = await createImageBitmap(new Blob([bytes], { type: 'image/png' }));
        const canvas = document.createElement('canvas');
        canvas.width = image.width; canvas.height = image.height;
        const context = canvas.getContext('2d');
        context.drawImage(image, 0, 0); image.close();
        const pixels = context.getImageData(0, 0, canvas.width, canvas.height).data;
        let colored = 0;
        for (let i = 0; i < pixels.length; i += 4)
          if (pixels[i + 3] && Math.max(pixels[i], pixels[i + 1], pixels[i + 2]) - Math.min(pixels[i], pixels[i + 1], pixels[i + 2]) > 50) colored++;
        return { dimensions: [canvas.width, canvas.height], colored };
      }, bytes.toString('base64'));
      assert.deepEqual(decoded.dimensions, [1440, 720]); // public PNG default is scale=2
      assert.ok(decoded.colored > 5, 'PNG download must contain chart paint');
    }
    downloads[format] = { filename: download.suggestedFilename(), bytes: bytes.length,
      sha256: createHash('sha256').update(bytes).digest('hex') };
  }
  await streamlit.screenshot({ path: 'consumer-apps-smoke/streamlit.png' });
  assert.deepEqual(streamlitErrors, []);
  report.hosts.streamlit = { coloredPixels: before, rerun: true, singleIframe: true,
    exportControls: true, downloads, pythonSelectionCallbacks: false, errors: streamlitErrors };
  report.hosts.streamlit.graphforge = await qualifyStreamlitGraphForge(browser,
    values['streamlit-url'], 'consumer-apps-smoke', paint);
  for (const file of ['target/release/libxyg_core.so', 'packages/xy-client/dist/index.js',
    'packages/xy-client/dist/xyg-wasm.wasm'])
    report.hashes[file] = createHash('sha256').update(await readFile(file)).digest('hex');
  await writeFile('consumer-apps-smoke.json', JSON.stringify(report, null, 2) + '\n');
  process.exitCode = 0;
} finally { await browser.close(); }
