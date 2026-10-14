/** Verify the built Starlight reader journey and real native WebGL charts. */
import assert from 'node:assert/strict';
import { createServer } from 'node:http';
import { readFile, stat, mkdir } from 'node:fs/promises';
import path from 'node:path';
import { chromium } from 'playwright';
import { APP, outputPath } from './check-built.mjs';

const dist = path.join(APP, 'dist');
const failures = [];
const mime = { '.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css', '.json': 'application/json', '.svg': 'image/svg+xml', '.png': 'image/png', '.woff2': 'font/woff2', '.txt': 'text/plain', '.md': 'text/plain', '.wasm': 'application/wasm', '.xyf': 'application/octet-stream' };
const server = createServer(async (request, response) => {
  try {
    const url = new URL(request.url, 'http://localhost');
    let file = outputPath(dist, url.pathname);
    if (!(await stat(file)).isFile()) throw new Error('not a file');
    response.writeHead(200, { 'Content-Type': mime[path.extname(file)] ?? 'application/octet-stream' });
    response.end(await readFile(file));
  } catch {
    response.writeHead(404);
    response.end('Not found');
  }
});
await new Promise((resolve) => server.listen(0, '127.0.0.1', resolve));
const origin = `http://127.0.0.1:${server.address().port}`;
async function checkHomepageBounds(page, viewport) {
  const demos = page.locator('.xyg-demo');
  assert.equal(await demos.count(), 4, `${viewport}: homepage lost original demonstrations`);
  for (let index = 0; index < 4; index++) {
    const demo = demos.nth(index);
    await demo.scrollIntoViewIfNeeded();
    await page.waitForFunction((index) => document.querySelectorAll('.xyg-demo')[index]?.dataset.rendered === 'true', index);
    const bounds = await demo.evaluate((host) => {
      const outer = host.getBoundingClientRect();
      return [...host.querySelectorAll('canvas')].map((canvas) => {
        const inner = canvas.getBoundingClientRect();
        return {
          width: inner.width,
          height: inner.height,
          left: inner.left - outer.left,
          top: inner.top - outer.top,
          right: inner.right - outer.right,
          bottom: inner.bottom - outer.bottom,
          hostWidth: outer.width,
          hostHeight: outer.height,
        };
      }).filter((canvas) => canvas.width > 0 && canvas.height > 0);
    });
    assert.ok(bounds.length > 0, `${viewport}: demo ${index + 1} has no visible native canvas`);
    for (const canvas of bounds) {
      assert.ok(canvas.left >= -2 && canvas.top >= -2 && canvas.right <= 2 && canvas.bottom <= 2,
        `${viewport}: demo ${index + 1} crops native geometry: ${JSON.stringify(canvas)}`);
    }
  }
  assert.equal(await page.locator('.xyg-demo-error').count(), 0);
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.waitForFunction(() => window.scrollY === 0);
}
let browser;
try {
  browser = await chromium.launch({
    ...(process.env.CHROMIUM ? { executablePath: process.env.CHROMIUM } : {}),
    headless: true,
    args: ['--no-sandbox', '--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader'],
  });
  const context = await browser.newContext({ viewport: { width: 1440, height: 1000 }, reducedMotion: 'reduce' });
  await context.addInitScript(() => {
    // Preserve pixels only for this test, as in the chart conformance probe.
    const getContext = HTMLCanvasElement.prototype.getContext;
    HTMLCanvasElement.prototype.getContext = function (type, attributes) {
      return getContext.call(this, type, type === 'webgl2' ? { ...attributes, preserveDrawingBuffer: true } : attributes);
    };
    window.__docsViews = [];
    window.__xygStandaloneObserver = (event) => {
      if (event.phase === 'attached') window.__docsViews.push(event.view);
    };
  });
  const page = await context.newPage();
  page.on('pageerror', (error) => failures.push(error.message));
  page.on('console', (message) => {
    if (message.type() === 'error') failures.push(message.text());
  });
  page.on('response', (response) => {
    if (response.url().startsWith(origin) && response.status() >= 400) failures.push(`${response.status()} ${response.url()}`);
  });
  await page.goto(`${origin}/docs/xy/`, { waitUntil: 'networkidle' });
  await page.getByRole('heading', { level: 1 }).waitFor();
  assert.match(await page.title(), /XYG/);
  assert.match(await page.locator('main').innerText(), /GraphForge/);
  assert.equal(await page.locator('.xyg-demo').count(), 4, 'homepage must retain its four original native demonstrations');
  await checkHomepageBounds(page, 'desktop');
  await mkdir(path.join(APP, '.generated/screenshots'), { recursive: true });
  await page.screenshot({ path: path.join(APP, '.generated/screenshots/desktop.png'), fullPage: true });

  // Test search against the production Pagefind index, not the development stub.
  const search = page.getByRole('button', { name: /search/i }).first();
  await search.click();
  const searchInput = page.locator('.pagefind-ui__search-input');
  await searchInput.waitFor();
  await searchInput.fill('GraphForge');
  await page.locator('.pagefind-ui__result-link').first().waitFor();
  assert.ok(await page.locator('.pagefind-ui__result-link').count() > 0);
  await page.keyboard.press('Escape');

  await page.goto(`${origin}/docs/xy/charts/scatter/`, { waitUntil: 'networkidle' });
  await page.locator('.xyg-demo').first().scrollIntoViewIfNeeded();
  await page.waitForFunction(() => document.querySelector('.xyg-demo')?.dataset.rendered === 'true');
  const pixels = await page.evaluate(() => {
    const view = window.__docsViews[0];
    view._drawKeepPick();
    const gl = view.gl;
    const bytes = new Uint8Array(gl.drawingBufferWidth * gl.drawingBufferHeight * 4);
    gl.readPixels(0, 0, gl.drawingBufferWidth, gl.drawingBufferHeight, gl.RGBA, gl.UNSIGNED_BYTE, bytes);
    const colors = new Set();
    let opaque = 0;
    for (let offset = 0; offset < bytes.length; offset += 16) {
      if (bytes[offset + 3]) opaque++;
      colors.add(`${bytes[offset]},${bytes[offset + 1]},${bytes[offset + 2]}`);
    }
    return { opaque, colors: colors.size };
  });
  assert.ok(pixels.opaque > 100 && pixels.colors > 8, `native chart is blank: ${JSON.stringify(pixels)}`);
  const canvas = page.locator('.xyg-demo canvas').first();
  const box = await canvas.boundingBox();
  assert.ok(box && box.width > 200 && box.height > 100);
  const initial = await page.evaluate(() => JSON.stringify(window.__docsViews[0].view));
  await page.mouse.move(box.x + box.width * 0.55, box.y + box.height * 0.5);
  await page.mouse.wheel(0, -260);
  await page.waitForFunction((before) => JSON.stringify(window.__docsViews[0].view) !== before, initial);
  const zoomed = await page.evaluate(() => JSON.stringify(window.__docsViews[0].view));
  await page.mouse.down();
  await page.mouse.move(box.x + box.width * 0.65, box.y + box.height * 0.57, { steps: 8 });
  await page.mouse.up();
  await page.waitForFunction((before) => JSON.stringify(window.__docsViews[0].view) !== before, zoomed);

  for (const route of ['integrations/graphforge/', 'core-concepts/rust-engine-and-host-parity/', 'charts/graph/']) {
    await page.goto(`${origin}/docs/xy/${route}`, { waitUntil: 'networkidle' });
    await page.getByRole('heading', { level: 1 }).waitFor();
    assert.match(await page.title(), /XYG/);
    assert.ok((await page.locator('main').innerText()).length > 300);
    if (route === 'charts/graph/') {
      await page.locator('.xyg-demo').first().scrollIntoViewIfNeeded();
      await page.waitForFunction(() => document.querySelector('.xyg-demo')?.dataset.rendered === 'true');
      const graphPixels = await page.evaluate(() => {
        const view = window.__docsViews[0];
        view._drawKeepPick();
        const gl = view.gl;
        const pixels = new Uint8Array(gl.drawingBufferWidth * gl.drawingBufferHeight * 4);
        gl.readPixels(0, 0, gl.drawingBufferWidth, gl.drawingBufferHeight, gl.RGBA, gl.UNSIGNED_BYTE, pixels);
        const colors = new Set();
        let lit = 0;
        for (let offset = 0; offset < pixels.length; offset += 4) {
          if (pixels[offset + 3]) lit++;
          colors.add(`${pixels[offset]},${pixels[offset + 1]},${pixels[offset + 2]}`);
        }
        return { lit, colors: colors.size };
      });
      assert.ok(graphPixels.lit > 10 && graphPixels.colors > 1, 'original graph example painted no native geometry');
    }
  }
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto(`${origin}/docs/xy/`, { waitUntil: 'networkidle' });
  assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 2), 'mobile docs overflow horizontally');
  await checkHomepageBounds(page, 'mobile');
  await page.screenshot({ path: path.join(APP, '.generated/screenshots/mobile.png'), fullPage: true });
  const menu = page.locator('button[popovertarget="starlight__sidebar"]');
  await menu.click();
  assert.ok(await page.locator('#starlight__sidebar').evaluate((element) => element.matches(':popover-open')), 'mobile sidebar did not open');
  const graphforgeLink = page.locator('nav a[href="/docs/xy/integrations/graphforge/"]').first();
  await graphforgeLink.waitFor({ state: 'visible' });
  await graphforgeLink.click();
  await page.waitForURL('**/integrations/graphforge/');
  await page.getByRole('heading', { level: 1 }).waitFor();
  await page.screenshot({ path: path.join(APP, '.generated/screenshots/mobile-graphforge.png'), fullPage: true });
  assert.deepEqual(failures, [], 'production documentation emitted runtime or asset failures');
  console.log('Starlight Chromium smoke passed: desktop/mobile navigation, production search, uncropped homepage canvases, native pixels, pan/zoom, and GraphForge/parity routes.');
} finally {
  await browser?.close();
  await new Promise((resolve) => server.close(resolve));
}
