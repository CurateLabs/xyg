// Diagnostic only: remove the current SVG projection to inspect centered HTML
// with the Rust-final plot. Never used as a product acceptance replacement.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { createServer } from 'node:http';
import { chromium } from 'playwright';
const receipt = path.dirname(new URL(import.meta.url).pathname), out = path.join(receipt, process.argv[2]);
assert.ok(!fs.existsSync(out)); fs.mkdirSync(out);
const server = createServer((req, res) => {
  if (req.url === '/') { res.setHeader('Content-Type', 'text/html'); res.end('<!doctype html><style>body{margin:0}</style><div id="chart"></div>'); return; }
  const name = path.basename(req.url);
  const file = name.startsWith('precision.') ? path.join(receipt, name) : name === 'index.js' ? 'target/task-tmp/before-index.js' : path.join('packages/xy-client/dist', name);
  if (!fs.existsSync(file)) { res.writeHead(404); res.end(); return; }
  res.setHeader('Content-Type', name.endsWith('.js') ? 'text/javascript' : name.endsWith('.svg') ? 'image/svg+xml' : name.endsWith('.wasm') ? 'application/wasm' : 'application/octet-stream'); res.end(fs.readFileSync(file));
});
await new Promise(r => server.listen(0, '127.0.0.1', r));
const browser = await chromium.launch({ executablePath: process.env.XYG_CHROMIUM, args: ['--no-sandbox', '--hide-scrollbars', '--use-angle=swiftshader', '--enable-unsafe-swiftshader'] });
const rows = [];
try { for (const dpr of [1, 1.25, 2]) {
  const page = await browser.newPage({ viewport: { width: 320, height: 240 }, deviceScaleFactor: dpr });
  await page.goto(`http://127.0.0.1:${server.address().port}/`);
  const record = await page.evaluate(async () => {
    const client = await import('/index.js'); window.worker = client.createXygWasmWorker({ workerUrl: '/wasm-worker.js', wasm: '/xyg-wasm.wasm' }); await worker.ready;
    window.view = await client.renderWasmScene({ el: document.getElementById('chart'), worker, scene: await (await fetch('/precision.scene')).arrayBuffer() });
    await new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)));
    return { plot: { ...view.plot }, rows: [...view.labels.querySelectorAll('[data-xy-slot="axis_line"]')].map(e => ({ axis: e.dataset.xyAxis, nativeWidth: view.axes[e.dataset.xyAxis].style.axis_width, computedWidth: getComputedStyle(e).width, computedHeight: getComputedStyle(e).height })) };
  });
  await page.locator('#chart').screenshot({ path: path.join(out, `svg.dpr${dpr}.png`) });
  await page.evaluate(() => { view.labels.querySelectorAll('[data-xy-resolved-spine]').forEach(e => e.remove()); view.labels.querySelectorAll('[data-xy-slot="axis_line"]').forEach(e => e.style.removeProperty('clip-path')); });
  await page.locator('#chart').screenshot({ path: path.join(out, `html.dpr${dpr}.png`) });
  await page.evaluate(async () => { view.destroy(); worker.dispose(); const img = new Image(); img.src = '/precision.svg'; document.getElementById('chart').replaceChildren(img); await img.decode(); });
  await page.locator('#chart').screenshot({ path: path.join(out, `native-svg.dpr${dpr}.png`) });
  rows.push({ dpr, ...record, svgAndHtmlImagesIdentical: fs.readFileSync(path.join(out, `svg.dpr${dpr}.png`)).equals(fs.readFileSync(path.join(out, `html.dpr${dpr}.png`))) });
  await page.close();
} } finally { await browser.close(); server.close(); }
fs.writeFileSync(path.join(out, 'observations.json'), JSON.stringify(rows, null, 2) + '\n');
console.log(JSON.stringify(rows, null, 2));
