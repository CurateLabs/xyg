// hydrateWasmPainter draws a rotated Rust painter label (XYLB v6) with the
// anchor-aware CSS rotation, in headless Chromium (#1040).
// XYG_NATIVE_LIB=$PWD/target/release/libxyg_core.so node tests/browser/painter_rotated_label_test.mjs
import assert from 'node:assert/strict';
import {createServer} from 'node:http';
import {readFile} from 'node:fs/promises';
import {chromium} from 'playwright';
import {Figure, sceneBrowserPainter} from '../../packages/xy-node/src/index.js';

const fig = new Figure({width: 320, height: 240, showLegend: false, xAxis: {domain: [0, 2]}, yAxis: {domain: [0, 4]}});
fig.line([0, 1, 2], [1, 3, 2]);
fig.annotate({kind: 'text', x: 1, y: 3, text: 'tilted', style: {rotation: 30}});
fig.annotate({kind: 'text', x: 0.5, y: 1, text: 'flat'});
const painter = Buffer.from(sceneBrowserPainter(fig.toScene()));
const page_js = `import {hydrateWasmPainter} from '/index.js';
const painter = await (await fetch('/painter.bin')).arrayBuffer();
const host = document.createElement('div'); host.style.cssText = 'width:320px;height:240px'; document.body.appendChild(host);
hydrateWasmPainter(host, {painter, sceneBytes: 0, wasmMemoryBytes: 0, traceCount: 1}, {workerPrepareMs: 0});
window.result = [...host.querySelectorAll('[data-xy-slot="annotation_label"],[data-xy-slot="graph_label"]')].map((el) => ({text: el.textContent, transform: el.style.transform, origin: el.style.transformOrigin, size: el.style.fontSize}));`;
const server = createServer(async (req, res) => {
  try {
    if (req.url === '/') { res.setHeader('Content-Type', 'text/html'); res.end('<!doctype html><script type="module" src="/page.js"></script>'); return; }
    if (req.url === '/index.js') { res.setHeader('Content-Type', 'text/javascript'); res.end(await readFile('packages/xy-client/dist/index.js')); return; }
    if (req.url === '/page.js') { res.setHeader('Content-Type', 'text/javascript'); res.end(page_js); return; }
    if (req.url === '/painter.bin') { res.setHeader('Content-Type', 'application/octet-stream'); res.end(painter); return; }
    res.statusCode = 404; res.end();
  } catch (error) { res.statusCode = 500; res.end(error.message); }
});
await new Promise((r) => server.listen(0, '127.0.0.1', r));
const browser = await chromium.launch({executablePath: process.env.XYG_CHROMIUM ?? chromium.executablePath(), args: ['--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist']});
try {
  const page = await browser.newPage(), errors = [];
  page.on('pageerror', (e) => errors.push(e.message));
  await page.goto(`http://127.0.0.1:${server.address().port}/`);
  await page.waitForFunction(() => window.result || false, null, {timeout: 30000}).catch(() => {});
  assert.deepEqual(errors, []);
  const result = await page.evaluate(() => window.result);
  const byText = Object.fromEntries(result.map((r) => [r.text, r]));
  const tilted = byText.tilted, flat = byText.flat;
  assert.ok(tilted && flat, JSON.stringify(result));
  const size = parseFloat(tilted.size);
  // Authored 30 degrees is clockwise-negative; CSS rotate is clockwise-positive.
  assert.match(tilted.transform, /rotate\(-30deg\)/);
  assert.equal(tilted.origin, `0px ${size}px`);
  assert.doesNotMatch(flat.transform, /rotate/);
  console.log(`painter rotated label: ${JSON.stringify(tilted)}`);
} finally { await browser.close(); server.close(); }
