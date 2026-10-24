// Shared installed-host #886 cases, called by the existing consumer gate.
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { writeFile } from 'node:fs/promises';
import { join } from 'node:path';

function observe() {
  const proof = globalThis.consumerProof = { events: [], densityEvents: [], workers: [],
    urls: new Set(), violations: [], view: null };
  const OriginalWorker = globalThis.Worker;
  globalThis.Worker = class extends OriginalWorker {
    constructor(...args) {
      super(...args);
      this.record = { url: String(args[0]), terminated: false };
      proof.workers.push(this.record);
    }
    terminate() { this.record.terminated = true; return super.terminate(); }
  };
  const create = URL.createObjectURL.bind(URL), revoke = URL.revokeObjectURL.bind(URL);
  URL.createObjectURL = blob => { const url = create(blob); proof.urls.add(url); return url; };
  URL.revokeObjectURL = url => { proof.urls.delete(url); return revoke(url); };
  document.addEventListener('securitypolicyviolation', event => proof.violations.push(event.violatedDirective));
  document.addEventListener('xy:wasm_density_no_refinement', event => proof.densityEvents.push(event.detail));
  globalThis.__xygStandaloneObserver = event => {
    if (event.phase === 'attached') {
      proof.view = event.view;
      const trace = event.view.gpuTraces.find(trace => trace.tier === 'density');
      if (trace) {
        proof.original = { overview: trace.density, texture: trace.density.tex,
          grid: trace.density.grid.slice(), uploads: 0 };
        const upload = event.view._uploadGrid.bind(event.view);
        event.view._uploadGrid = (...args) => { proof.original.uploads++; return upload(...args); };
      }
    }
    proof.events.push({ phase: event.phase, code: event.code, message: event.message,
      diagnostics: event.diagnostics });
  };
}

async function dispose(page) {
  await page.evaluate(() => {
    const proof = globalThis.consumerProof;
    proof.gl = proof.view.gl;
    proof.eventCount = proof.events.length + proof.densityEvents.length;
    proof.view.destroy();
    // A disposed viewport request cannot publish a late density diagnostic.
    proof.view._scheduleViewRequest();
  });
  await page.waitForFunction(() => globalThis.consumerProof.workers.every(worker => worker.terminated));
  // Cross the normal 120ms viewport debounce and a presentation boundary.
  await page.waitForTimeout(250);
  const result = await page.evaluate(() => {
    const proof = globalThis.consumerProof, view = proof.view;
    return { destroyed: view._destroyed, glReleased: view.gl === null,
      contextLost: proof.gl.isContextLost(), listeners: view._listeners.length,
      rootConnected: view.root.isConnected,
      overviewTextureReleased: !proof.original || !proof.gl.isTexture(proof.original.texture),
      raf: !!view._raf, gpuTraces: view.gpuTraces.length, ticksReleased: view._wasmTicks === null,
      densityReleased: !view._wasmDensity, liveWorkers: proof.workers.filter(worker => !worker.terminated).length,
      objectUrls: proof.urls.size, lateEvents: proof.events.length + proof.densityEvents.length - proof.eventCount };
  });
  assert.ok(result.destroyed && result.glReleased && result.contextLost && result.ticksReleased
    && result.densityReleased && result.overviewTextureReleased && !result.rootConnected);
  for (const key of ['listeners', 'raf', 'gpuTraces', 'liveWorkers', 'objectUrls', 'lateEvents'])
    assert.ok(!result[key], `disposal retained ${key}: ${JSON.stringify(result)}`);
  return result;
}

async function screenshot(page, output, name) {
  const filename = `${name}.png`;
  const png = await page.screenshot({ path: join(output, filename) });
  return { file: filename, sha256: createHash('sha256').update(png).digest('hex') };
}

export async function captureModuleResponses(context, moduleUrl, external, errors, timeoutMs = 10_000) {
  const assetResponses = [], observed = [], tasks = [];
  let received, failed;
  const responseSeen = new Promise((resolve, reject) => { received = resolve; failed = reject; });
  // Navigation/tick admission can fail before the caller reaches wait().
  responseSeen.catch(() => {});
  context.on('response', response => {
    if (!response.url().endsWith('.wasm')) return;
    observed.push({ url: response.url(), status: response.status() });
    received();
  });
  await context.route('**/*', route => {
    const url = route.request().url();
    if (new URL(url).origin !== new URL(moduleUrl).origin) {
      external.push(url); return route.abort();
    }
    if (!url.endsWith('.wasm')) return route.continue();
    const task = (async () => {
      assert.equal(url, moduleUrl, 'unexpected module request');
      // Read the one upstream transfer before delivering it to the real Worker.
      // CDP response.body() can lose its target when corrupt compile terminates
      // that Worker. APIResponse bytes survive it; fulfill sends these same bytes.
      const response = await route.fetch({ timeout: timeoutMs, maxRedirects: 0, maxRetries: 0 });
      const bytes = await response.body();
      assetResponses.push({ url, status: response.status(), bytes: response.ok() ? bytes.length : null,
        sha256: response.ok() ? createHash('sha256').update(bytes).digest('hex') : null });
      await route.fulfill({ response, body: bytes });
    })();
    tasks.push(task);
    return task.catch(error => { errors.push(error.message); failed(error); return route.abort(); });
  });
  return { assetResponses, async wait() {
    let timeout;
    try {
      await Promise.race([(async () => {
        // The response event follows registration of its transfer task, even if
        // Playwright delivers the event after the tick/termination diagnostics.
        await responseSeen;
        await Promise.all(tasks);
      })(), new Promise((_, reject) => {
        timeout = setTimeout(() => reject(Error('module response collection timed out')), timeoutMs);
      })]);
      assert.equal(assetResponses.length, 1);
      assert.deepEqual(observed, assetResponses.map(({ url, status }) => ({ url, status })));
    } finally { clearTimeout(timeout); }
  } };
}

export async function qualifyPackagedConsumers(browser, origins, output) {
  const cases = [];
  for (const host of ['python', 'node']) {
    const origin = origins[host];
    for (const kind of ['secondary', 'polar', 'missing', 'corrupt']) {
      const name = `${host}-${kind}`;
      const context = await browser.newContext({ viewport: { width: 800, height: 600 }, serviceWorkers: 'block' });
      const page = await context.newPage();
      const errors = [], requests = [], external = [];
      page.on('pageerror', error => errors.push(error.message));
      context.on('request', request => requests.push({ url: request.url(), method: request.method() }));
      const failure = ['missing', 'corrupt'].includes(kind);
      const moduleUrl = `${origin}${host === 'python' ? '' : '/assets'}/${failure ? kind : 'xyg-wasm'}.wasm`;
      const modules = await captureModuleResponses(context, moduleUrl, external, errors);
      const { assetResponses } = modules;
      await context.addInitScript(observe);
      try {
        const response = await page.goto(`${origin}${host === 'python' ? `/${kind}.html` : `/?kind=${kind}`}`);
        const csp = response.headers()['content-security-policy']
          ?? await page.locator('meta[http-equiv="Content-Security-Policy"]').getAttribute('content');
        assert.match(csp, /worker-src 'self'/); assert.match(csp, /connect-src 'self'/);
        await page.waitForFunction(failure => {
          const proof = globalThis.consumerProof;
          return proof.view && proof.events.some(event => event.phase === (failure ? 'ticks_error' : 'ticks_ready'));
        }, failure);
        if (failure) await page.waitForFunction(() => globalThis.consumerProof.workers.every(worker => worker.terminated));
        await modules.wait();
        assert.equal(assetResponses.length, 1);
        assert.equal(assetResponses[0].status, kind === 'missing' ? 404 : 200);
        if (kind === 'corrupt') {
          assert.equal(assetResponses[0].bytes, 4);
          assert.equal(assetResponses[0].sha256, createHash('sha256').update(Buffer.from([0, 1, 2, 3])).digest('hex'));
        }
        const ticks = await page.evaluate(({ failure, kind }) => {
          const proof = globalThis.consumerProof, view = proof.view;
          // The painter names polar angular/radial slots x/y; their family
          // comes from coords/theta_unit, never an invented theta/r slot.
          const ids = kind === 'polar' ? ['x', 'y'] : ['x', 'y', 'y2'];
          return { diagnostics: view._wasmTicks?.diagnostics() ?? null,
            events: proof.events, slots: Object.fromEntries(ids.map(id => [id, view._axisTicks(id, 6)])),
            labels: Object.fromEntries(ids.map(id => [id, view._axisTicks(id, 6).ticks
              .map(value => view._wasmTicks?.label(id, value))])),
            coords: view.spec.coords ?? 'cartesian', thetaUnit: view.axes.x.theta_unit,
            workers: proof.workers, attached: !!view._wasmTicks, failure,
            violations: proof.violations };
        }, { failure, kind });
        assert.equal(ticks.workers.length, 1);
        if (failure) {
          assert.equal(ticks.attached, false);
          assert.ok(ticks.events.every(event => event.phase !== 'ticks_ready'));
          for (const slot of Object.values(ticks.slots)) {
            assert.deepEqual(slot.ticks, []); assert.equal(slot.source, 'failed-closed');
          }
          const event = ticks.events.find(event => event.phase === 'ticks_error');
          assert.equal(event.code, 'XYG_WASM_INIT_FAILED');
          if (kind === 'corrupt') assert.match(event.message, /magic|compile|WebAssembly/i);
          else assert.match(event.message, /404/);
          assert.ok(ticks.workers.every(worker => worker.terminated));
        } else {
          const ids = kind === 'polar' ? ['x', 'y'] : ['x', 'y', 'y2'];
          for (const id of ids) {
            assert.ok(ticks.diagnostics.axisIds.includes(id), `missing Rust cache ${name}/${id}`);
            assert.ok(ticks.slots[id].ticks.length > 0, `empty admitted ticks ${name}/${id}`);
            assert.equal(ticks.slots[id].source, 'wasm');
            assert.ok(ticks.labels[id].some(label => typeof label === 'string' && label.length));
          }
          if (kind === 'polar') {
            assert.equal(ticks.coords, 'polar'); assert.equal(ticks.thetaUnit, 'degrees');
          }
          assert.equal(ticks.workers[0].terminated, false);
        }
        // Read the actual plot presentation, independent of tick diagnostics.
        const coloredPixels = await page.evaluate(async () => {
          const view = globalThis.consumerProof.view;
          for (let i = 0; i < 8; i++) {
            const rendered = view._drawNow();
            if (view._glHost ? rendered === true : !view._glLost && !view.gl.isContextLost()) break;
            await new Promise(resolve => requestAnimationFrame(resolve));
          }
          const canvas = document.createElement('canvas');
          canvas.width = view.canvas.width; canvas.height = view.canvas.height;
          const ctx = canvas.getContext('2d'); ctx.drawImage(view.canvas, 0, 0);
          const data = ctx.getImageData(0, 0, canvas.width, canvas.height).data;
          let colored = 0;
          for (let i = 0; i < data.length; i += 4)
            if (data[i + 3] && Math.max(data[i], data[i + 1], data[i + 2]) - Math.min(data[i], data[i + 1], data[i + 2]) > 50) colored++;
          return colored;
        });
        assert.ok(coloredPixels > 5, `${name}: blank plot`);
        const image = await screenshot(page, output, name);
        const lifecycle = await dispose(page);
        await modules.wait();
        assert.deepEqual(errors, []); assert.deepEqual(external, []); assert.deepEqual(ticks.violations, []);
        const paths = requests.map(request => new URL(request.url).pathname);
        const allowed = host === 'python' ? [`/${kind}.html`, '/wasm-worker.js', `/${failure ? kind : 'xyg-wasm'}.wasm`]
          : ['/', '/app.js', '/client.js', '/spec', '/buffers', '/assets/wasm-worker.js', `/assets/${failure ? kind : 'xyg-wasm'}.wasm`];
        assert.ok(paths.every(path => allowed.includes(path)), `hidden asset fetch: ${paths}`);
        assert.ok(paths.includes(host === 'python' ? '/wasm-worker.js' : '/assets/wasm-worker.js'));
        assert.ok(paths.includes(`${host === 'python' ? '' : '/assets'}/${failure ? kind : 'xyg-wasm'}.wasm`));
        cases.push({ name, csp, ticks, coloredPixels, screenshot: image, lifecycle, requests, assetResponses, external, errors });
      } catch (error) {
        const diagnostics = await page.evaluate(() => {
          const proof = globalThis.consumerProof;
          return { events: proof?.events, workers: proof?.workers, violations: proof?.violations,
            diagnostics: proof?.view?._wasmTicks?.diagnostics(), axes: proof?.view?.spec?.axes };
        });
        await writeFile(join(output, 'packaged-consumers.failed.json'), JSON.stringify({ name, error: error.message,
          diagnostics, requests, external, errors, cases }, null, 2) + '\n');
        await screenshot(page, output, `${name}.failed`);
        throw error;
      } finally { await context.close(); }
    }
  }
  // One real native split source qualifies the unsupported-source boundary.
  // The installed Python file-export missing/corrupt cases already own the
  // optional-inline-module branches; do not multiply them across all hosts.
  const context = await browser.newContext({ viewport: { width: 800, height: 600 }, serviceWorkers: 'block' });
  const origin = origins.node;
  const page = await context.newPage();
  const external = [], errors = [], requests = [];
  page.on('pageerror', error => errors.push(error.message));
  context.on('request', request => requests.push(request.url()));
  await context.route('**/*', route => {
    if (new URL(route.request().url()).origin !== origin) { external.push(route.request().url()); return route.abort(); }
    return route.continue();
  });
  await context.addInitScript(observe);
  try {
    const response = await page.goto(`${origin}/?kind=density`);
    const csp = response.headers()['content-security-policy'];
    assert.match(csp, /worker-src 'self'/); assert.match(csp, /connect-src 'self'/);
    await page.waitForFunction(() => globalThis.consumerProof.view?._wasmTicks?.diagnostics());
    const result = await page.evaluate(async () => {
      const proof = globalThis.consumerProof, view = proof.view, original = proof.original;
      const trace = view.gpuTraces.find(trace => trace.tier === 'density');
      const unsupported = view.spec.wasm_density?.unsupported;
      if (unsupported?.code !== 'XYG_WASM_SOURCE_UNSUPPORTED' || view.spec.wasm_density.automatic !== false
          || view.spec.buffer_layout !== 'split' || view.spec.columns.some(column => column.dtype === 'f64'))
        throw Error('fixture did not carry ordinary native unsupported-source policy');
      const hash = async data => [...new Uint8Array(await crypto.subtle.digest('SHA-256', data))]
        .map(byte => byte.toString(16).padStart(2, '0')).join('');
      const home = view.root.xy.state().ranges;
      const captures = [];
      const capture = async ranges => {
        if (!view.root.xy.applyState({ ranges }, { animate: false, history: false })) throw Error('viewport refused');
        // Exercise the ordinary live refinement scheduling and cross its debounce.
        view._scheduleViewRequest();
        await new Promise(resolve => setTimeout(resolve, 250));
        let presented = false;
        for (let i = 0; i < 8; i++) {
          const rendered = view._drawNow();
          if (view._glHost ? rendered === true : !view._glLost && !view.gl.isContextLost()) { presented = true; break; }
          await new Promise(resolve => requestAnimationFrame(resolve));
        }
        if (!presented) throw Error('no completed density presentation');
        const actual = view.root.xy.state().ranges;
        if (JSON.stringify(actual) !== JSON.stringify(ranges)) throw Error('stale viewport');
        const copy = document.createElement('canvas'); copy.width = view.canvas.width; copy.height = view.canvas.height;
        const ctx = copy.getContext('2d'); ctx.drawImage(view.canvas, 0, 0);
        const pixels = ctx.getImageData(0, 0, copy.width, copy.height).data;
        let coloredPixels = 0;
        for (let i = 0; i < pixels.length; i += 4)
          if (pixels[i + 3] && Math.max(pixels[i], pixels[i + 1], pixels[i + 2]) - Math.min(pixels[i], pixels[i + 1], pixels[i + 2]) > 20) coloredPixels++;
        if (!coloredPixels) throw Error('blank density overview');
        captures.push(pixels);
        return { sha256: await hash(pixels), ranges: actual, coloredPixels, size: [copy.width, copy.height] };
      };
      const before = await capture(home);
      const zoomed = await capture({ ...home, x: [0.25, 0.75], y: [0.25, 0.75] });
      const restored = await capture(home);
      let zoomDelta = 0, homeDelta = 0;
      if (captures.some(pixels => pixels.length !== captures[0].length)) throw Error('canvas changed dimensions');
      for (let i = 0; i < captures[0].length; i++) {
        zoomDelta = Math.max(zoomDelta, Math.abs(captures[0][i] - captures[1][i]));
        homeDelta = Math.max(homeDelta, Math.abs(captures[0][i] - captures[2][i]));
      }
      const gridSha256 = await hash(trace.density.grid);
      if (zoomDelta <= 1 || homeDelta > 1 || trace.density !== original.overview || trace.density.tex !== original.texture
          || gridSha256 !== await hash(original.grid) || original.uploads || view._wasmDensity
          || proof.workers.length !== 1 || proof.workers[0].terminated) throw Error('density fallback/replacement/stale repaint');
      const event = proof.densityEvents.find(event => event.code === unsupported.code && event.message === unsupported.message);
      if (!event || event.traceIds.join(',') !== String(trace.trace.id)) throw Error('missing native no-refinement reason');
      return { unsupported, events: proof.densityEvents, before, zoomed, restored, zoomDelta, homeDelta,
        gridSha256, replacementUploads: original.uploads, workerCount: proof.workers.length,
        densityAttached: !!view._wasmDensity, violations: proof.violations };
    });
    const image = await screenshot(page, output, 'node-unsupported-density');
    const lifecycle = await dispose(page);
    assert.deepEqual(errors, []); assert.deepEqual(external, []); assert.deepEqual(result.violations, []);
    const allowed = ['/', '/density.js', '/client.js', '/spec', '/buffers', '/assets/wasm-worker.js', '/assets/xyg-wasm.wasm'];
    assert.ok(requests.every(url => allowed.includes(new URL(url).pathname)), `hidden asset fetch: ${requests}`);
    cases.push({ name: 'node-unsupported-density', ...result, csp, lifecycle, screenshot: image, requests, external, errors });
  } catch (error) {
    await writeFile(join(output, 'packaged-consumers.failed.json'), JSON.stringify({ name: 'node-unsupported-density',
      error: error.message, external, errors, cases }, null, 2) + '\n');
    await screenshot(page, output, 'node-unsupported-density.failed');
    throw error;
  } finally { await context.close(); }
  const result = { cases, limitations: ['One ordinary split-density source; all unsupported source families and final-candidate qualification remain open.'] };
  await writeFile(join(output, 'packaged-consumers.json'), JSON.stringify(result, null, 2) + '\n');
  return result;
}
