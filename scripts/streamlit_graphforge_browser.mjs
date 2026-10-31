// Bounded #1016 journey, called by the existing installed-consumer gate.
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { readFile, rm, writeFile } from 'node:fs/promises';

const sha256 = bytes => createHash('sha256').update(bytes).digest('hex');

export async function qualifyStreamlitGraphForge(browser, url, output, paint) {
  for (const name of ['streamlit-graphforge-failed.png', 'streamlit-graphforge-failed.txt',
    'streamlit-graphforge-browser.json']) await rm(`${output}/${name}`, { force: true });
  const direct = JSON.parse(await readFile(`${output}/streamlit-graphforge-direct.json`, 'utf8'));
  const page = await browser.newPage({ viewport: { width: 1100, height: 1100 } });
  const errors = [], violations = [], external = [], contexts = new Map(), retired = new Set();
  const cdp = await page.context().newCDPSession(page);
  cdp.on('Runtime.executionContextCreated', ({ context }) => {
    if (context.auxData?.isDefault) contexts.set(context.auxData.frameId, context.id);
  });
  cdp.on('Runtime.executionContextDestroyed', ({ executionContextId }) => retired.add(executionContextId));
  await cdp.send('Runtime.enable');
  page.on('pageerror', error => errors.push(error.message));
  page.on('request', request => {
    if (/^https?:/.test(request.url()) && new URL(request.url()).origin !== new URL(url).origin)
      external.push(request.url());
  });
  // Observe existing hooks only. Do not add app callbacks or repair its cleanup.
  await page.addInitScript(() => {
    globalThis.graphforgeAttached = [];
    globalThis.__xygStandaloneObserver = event => {
      if (event.phase === 'attached') globalThis.graphforgeAttached.push(event.view);
    };
    globalThis.graphforgeCsp = [];
    document.addEventListener('securitypolicyviolation', event => {
      globalThis.graphforgeCsp.push(`${event.violatedDirective}: ${event.blockedURI}`);
    });
  });
  const select = async kind => {
    const input = page.getByRole('combobox');
    // Expanding previews can scroll the selector offscreen. Scroll before
    // opening its portal: scrolling an open Streamlit menu dismisses it.
    await input.scrollIntoViewIfNeeded();
    await input.click();
    // Commit the exact option; input text alone is not app state.
    await page.getByRole('option', { name: kind, exact: true }).click();
  };
  const current = async kind => {
    const element = page.locator('iframe');
    // A caption can update before Streamlit has replaced the iframe document.
    await page.waitForFunction(title => {
      const frames = document.querySelectorAll('iframe');
      return frames.length === 1 && frames[0].srcdoc.includes(`<title>${title}</title>`)
        && document.querySelector('[data-testid="stApp"]')?.getAttribute('data-test-script-state') === 'notRunning';
    }, kind);
    assert.equal(await element.count(), 1);
    const frame = await (await element.elementHandle()).contentFrame();
    await frame.waitForFunction(() => globalThis.graphforgeAttached?.length === 1);
    const html = await element.getAttribute('srcdoc');
    assert.equal(sha256(html), direct.cases[kind].artifacts.html.sha256, `${kind}: direct HTML differs`);
    assert.equal(await frame.locator('script[src],link[rel="stylesheet"]').count(), 0);
    // PageRank defaults encode the score in size and keep neutral paint.
    const pixels = await paint(frame, kind === 'graphforge-pagerank');
    assert.ok(pixels > 5, `${kind}: no graph paint pixels`);
    const state = await frame.evaluate(() => {
      const view = globalThis.graphforgeAttached[0];
      return { live: !!view.gl && !view._destroyed, comm: view.comm == null,
        workers: !!view._wasmTicks || !!view._wasmDensity, csp: globalThis.graphforgeCsp };
    });
    assert.equal(state.live, true);
    assert.equal(state.comm, true, 'stock snapshot must have no Python comm');
    assert.equal(state.workers, false);
    violations.push(...state.csp);
    const { frameTree } = await cdp.send('Page.getFrameTree');
    const frameId = frameTree.childFrames[0].frame.id;
    const contextId = contexts.get(frameId);
    assert.ok(contextId, 'missing observed iframe execution context');
    return { frame, contextId, html, pixels };
  };
  const waitRetired = async id => {
    await page.waitForFunction(() => document.querySelectorAll('iframe').length === 1);
    // CDP delivers context destruction asynchronously with the navigation.
    for (let attempt = 0; attempt < 50 && !retired.has(id); attempt++) await page.waitForTimeout(20);
    assert.ok(retired.has(id), 'outgoing snapshot execution context survived rerun');
  };
  try {
    await page.goto(url);
    await page.getByText('scatter · 8 rows', { exact: true }).waitFor();
    const cases = {};
    for (const kind of ['graphforge-property', 'graphforge-pagerank']) {
      await select(kind);
      const first = await current(kind);
      await page.screenshot({ path: `${output}/streamlit-${kind}-home.png` });
      // Inspect the actual Rust-authored property captions and label legend.
      if (kind === 'graphforge-property') {
        const captions = await first.frame.evaluate(() => graphforgeAttached[0]._graphLabelsDrawn
          .filter(label => label.kind === 'node').map(label => label.text));
        // Rust's collision plan may admit a subset at the initial scale.
        assert.ok(captions.length > 0 && captions.every(label => direct.cases[kind].captions.includes(label)));
        assert.ok(captions.includes('ada'), 'default name caption was not painted');
        for (const label of ['Person', 'Company'])
          assert.ok((await first.frame.locator('[data-xy-slot="legend"]').innerText()).includes(label));
      }
      // Trusted browser navigation stays inside the snapshot and never reruns Python.
      const canvas = first.frame.locator('canvas[style*="touch-action"]').first();
      const box = await canvas.boundingBox();
      await page.keyboard.down('Shift');
      await page.mouse.move(box.x + box.width * 0.9, box.y + box.height * 0.9);
      await page.mouse.down();
      await page.mouse.move(box.x + box.width * 0.1, box.y + box.height * 0.1, { steps: 8 });
      await page.mouse.up();
      await page.keyboard.up('Shift');
      await first.frame.waitForFunction(() => graphforgeAttached[0]._stateSelection?.range != null);
      const before = await first.frame.evaluate(() => ({ ...graphforgeAttached[0].view }));
      await page.mouse.move(box.x + box.width / 2, box.y + 20);
      await page.mouse.wheel(0, -30);
      await first.frame.waitForFunction(old => JSON.stringify(graphforgeAttached[0].view) !== JSON.stringify(old), before);
      assert.equal(await page.locator('iframe').getAttribute('srcdoc'), first.html);
      await page.getByText('Pan, zoom and hover in the chart. Selection stays in the browser.', { exact: true }).waitFor();
      await page.getByText('Static exports', { exact: true }).click();
      const images = page.locator('[data-testid="stImage"] img');
      assert.equal(await images.count(), 2);
      await images.evaluateAll(elements => Promise.all(elements.map(image => image.decode())));
      const downloads = {};
      for (const format of ['svg', 'png']) {
        const [download] = await Promise.all([
          page.waitForEvent('download'),
          page.getByRole('button', { name: `Download ${format.toUpperCase()}`, exact: true }).click(),
        ]);
        assert.equal(await download.failure(), null);
        assert.equal(download.suggestedFilename(), `chart.${format}`);
        const path = `${output}/streamlit-${kind}-download.${format}`;
        await download.saveAs(path);
        const bytes = await readFile(path);
        const hash = sha256(bytes);
        assert.equal(hash, direct.cases[kind].artifacts[format].sha256, `${kind}: ${format} differs from direct host`);
        downloads[format] = { bytes: bytes.length, sha256: hash };
      }
      await page.screenshot({ path: `${output}/streamlit-${kind}.png` });
      // Cycle twice: prove context retirement and deterministic document remount.
      let outgoing = first.contextId;
      const lifecycles = [];
      for (let cycle = 0; cycle < 2; cycle++) {
        await select('line');
        await page.getByText('line · 8 rows', { exact: true }).waitFor();
        await waitRetired(outgoing);
        await select(kind);
        const remount = await current(kind);
        assert.notEqual(remount.contextId, outgoing);
        assert.equal(remount.html, first.html);
        outgoing = remount.contextId;
        lifecycles.push({ outgoingContextRetired: true, singleIframe: true, identicalDocument: true, paintPixels: remount.pixels });
      }
      cases[kind] = { paintPixels: first.pixels,
        pixelOracle: kind === 'graphforge-pagerank' ? 'nonwhite (neutral score-size defaults)' : 'chromatic (label-color defaults)',
        directHtmlSha256: sha256(first.html),
        localAssets: true, nativePreviews: 2, downloads, localZoom: true, lifecycles,
        localBrush: true,
        pythonSelectionCallbacks: false, lifecycle: 'browser retires snapshot execution context; no application ChartView.destroy bridge' };
    }
    assert.deepEqual(errors, []);
    assert.deepEqual(violations, []);
    assert.deepEqual(external, []);
    const report = { cases, errors, cspViolations: violations, externalRequests: external };
    await writeFile(`${output}/streamlit-graphforge-browser.json`, JSON.stringify(report, null, 2) + '\n');
    return report;
  } catch (error) {
    await page.screenshot({ path: `${output}/streamlit-graphforge-failed.png` });
    await writeFile(`${output}/streamlit-graphforge-failed.txt`, `${error.stack}\n${await page.locator('body').innerText()}\n`);
    throw error;
  } finally { await cdp.detach(); await page.close(); }
}
