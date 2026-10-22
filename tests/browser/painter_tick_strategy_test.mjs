// hydrateWasmPainter shows the axis chrome Rust resolved from each tick-label
// strategy (hidden labels, hidden spines/ticks) in headless Chromium (#1036).
// XYG_NATIVE_LIB=$PWD/target/release/libxyg_core.so node tests/browser/painter_tick_strategy_test.mjs
import assert from 'node:assert/strict';
import {createServer} from 'node:http';
import {readFile} from 'node:fs/promises';
import {chromium} from 'playwright';
import {Figure, sceneBrowserPainter, sceneSvg} from '../../packages/xy-node/src/index.js';

const scene = (strategy) => {
  const fig = new Figure({width: 320, height: 240, showLegend: false, xAxis: {domain: [0, 2]}, yAxis: {domain: [0, 4]}});
  fig.setAxis('y2', {side: 'right', domain: [0, 400]});
  fig.line([0, 1, 2], [1, 3, 2]);
  fig.line([0, 1, 2], [100, 300, 200], {yAxis: 'y2'});
  for (const axis of ['x', 'y', 'y2']) if (strategy) fig.setAxis(axis, {tick_label_strategy: strategy});
  return fig.toScene();
};
const strategies = ['auto', 'hide', 'off', 'none'];
const scenes = Object.fromEntries(strategies.map((s) => [s, scene(s)]));
const painters = Object.fromEntries(strategies.map((s) => [s, Buffer.from(sceneBrowserPainter(scenes[s])).toString('base64')]));
const page_js = `import {hydrateWasmPainter} from '/index.js';
const painters = ${JSON.stringify(painters)};
window.result = {};
for (const [name, b64] of Object.entries(painters)) {
  const painter = Uint8Array.from(atob(b64), (c) => c.charCodeAt(0)).buffer;
  const host = document.createElement('div'); host.style.cssText = 'width:320px;height:240px'; document.body.appendChild(host);
  hydrateWasmPainter(host, {painter, sceneBytes: 0, wasmMemoryBytes: 0, traceCount: 2}, {workerPrepareMs: 0});
  await new Promise((r) => setTimeout(r, 400));
  const count = (selector) => host.querySelectorAll(selector).length;
  window.result[name] = {labels: count('[data-xy-slot="tick_label"]'), ticks: count('[data-xy-slot="tick_mark"]')};
}`;
const server = createServer(async (req, res) => {
  try {
    if (req.url === '/') { res.setHeader('Content-Type', 'text/html'); res.end('<!doctype html><script type="module" src="/page.js"></script>'); return; }
    if (req.url === '/index.js') { res.setHeader('Content-Type', 'text/javascript'); res.end(await readFile('packages/xy-client/dist/index.js')); return; }
    if (req.url === '/page.js') { res.setHeader('Content-Type', 'text/javascript'); res.end(page_js); return; }
    res.statusCode = 404; res.end();
  } catch (error) { res.statusCode = 500; res.end(error.message); }
});
await new Promise((r) => server.listen(0, '127.0.0.1', r));
const browser = await chromium.launch({executablePath: process.env.XYG_CHROMIUM ?? chromium.executablePath(), args: ['--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist']});
try {
  const page = await browser.newPage(), errors = [];
  page.on('pageerror', (e) => errors.push(e.message));
  await page.goto(`http://127.0.0.1:${server.address().port}/`);
  await page.waitForFunction(() => window.result && Object.keys(window.result).length === 4, null, {timeout: 30000}).catch(() => {});
  assert.deepEqual(errors, []);
  const result = await page.evaluate(() => window.result);
  console.log(JSON.stringify(result));
  const svgLabels = (s) => (Buffer.from(sceneSvg(scenes[s])).toString('utf8').match(/<text /g) ?? []).length;
  assert.ok(result.auto.labels > 0 && result.auto.ticks > 0, JSON.stringify(result));
  for (const hidden of ['off', 'none']) assert.equal(result[hidden].labels, 0, `${hidden} labels reappear`);
  assert.equal(result.none.ticks, 0, 'none ticks reappear');
  assert.equal(result.off.ticks, result.auto.ticks, 'off keeps ticks');
  assert.equal(svgLabels('off'), 0);
  assert.equal(svgLabels('none'), 0);
  assert.equal(result.hide.labels, result.auto.labels);
} finally { await browser.close(); server.close(); }
