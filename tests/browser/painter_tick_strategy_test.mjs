// hydrateWasmPainter applies the axis layout Rust resolved for every tick-label
// strategy on x, y and y2 (crowded axes), and the browser DOM matches the static
// SVG: visible labels, rotation, staggered rows, ticks and spines (#1036).
// XYG_NATIVE_LIB=$PWD/target/release/libxyg_core.so node tests/browser/painter_tick_strategy_test.mjs
import assert from 'node:assert/strict';
import {createServer} from 'node:http';
import {readFile} from 'node:fs/promises';
import {chromium} from 'playwright';
import {Figure, sceneBrowserPainter, sceneSvg} from '../../packages/xy-node/src/index.js';

const STRATEGIES = ['auto', 'hide', 'rotate', 'stagger', 'preserve', 'none', 'off'];
const AXES = ['x', 'y', 'y2'];
const scene = (axis, strategy) => {
  const fig = new Figure({width: 110, height: 80, showLegend: false, xAxis: {domain: [0, 3000000]}, yAxis: {domain: [0, 4]}});
  fig.setAxis('y2', {side: 'right', domain: [0, 400]});
  fig.line([0, 1000000, 3000000], [1, 3, 2]);
  fig.line([0, 1000000, 3000000], [100, 300, 200], {yAxis: 'y2'});
  fig.setAxis(axis, {tick_label_strategy: strategy});
  return fig.toScene();
};
const cases = AXES.flatMap((axis) => STRATEGIES.map((strategy) => ({axis, strategy, key: `${axis}:${strategy}`})));
const scenes = Object.fromEntries(cases.map((c) => [c.key, scene(c.axis, c.strategy)]));
const painters = Object.fromEntries(cases.map((c) => [c.key, Buffer.from(sceneBrowserPainter(scenes[c.key])).toString('base64')]));
const page_js = `import {hydrateWasmPainter} from '/index.js';
const painters = ${JSON.stringify(painters)};
window.result = {};
for (const [name, b64] of Object.entries(painters)) {
  const painter = Uint8Array.from(atob(b64), (c) => c.charCodeAt(0)).buffer;
  const host = document.createElement('div'); host.style.cssText = 'width:110px;height:80px'; document.body.appendChild(host);
  hydrateWasmPainter(host, {painter, sceneBytes: 0, wasmMemoryBytes: 0, traceCount: 2}, {workerPrepareMs: 0});
  await new Promise((r) => setTimeout(r, 150));
  const pick = (slot) => [...host.querySelectorAll('[data-xy-slot="' + slot + '"]')];
  window.result[name] = {
    labels: pick('tick_label').map((el) => ({text: el.textContent, axis: el.dataset.xyAxis, transform: el.style.transform, top: parseFloat(el.style.top)})),
    ticks: pick('tick_mark').map((el) => el.dataset.xyAxis),
    spines: pick('axis_line').map((el) => el.dataset.xyAxis + ':' + el.dataset.xyAxisSide),
  };
}`;
const svgOf = (key) => {
  const svg = Buffer.from(sceneSvg(scenes[key])).toString('utf8');
  const out = {x: [], y: [], y2: []};
  for (const m of svg.matchAll(/<text x="([^"]+)" y="([^"]+)"[^>]*text-anchor="(\w+)"( transform="rotate\(([-\d.]+) )?[^>]*>([^<]*)<\/text>/g)) {
    const [, , y, anchor, , angle, text] = m;
    const label = {text, angle: Number(angle ?? 0), y: Number(y)};
    (anchor === 'start' ? out.y2 : anchor === 'middle' || angle !== undefined ? out.x : out.y).push(label);
  }
  const axes = svg.slice(svg.indexOf('data-xy-chrome="axes"'));
  // Tick marks: short axis-colored lines; spines run along a whole plot edge.
  return {labels: out, lines: [...axes.matchAll(/<line x1="([^"]+)" y1="([^"]+)" x2="([^"]+)" y2="([^"]+)"/g)].length};
};
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
  await page.waitForFunction((n) => window.result && Object.keys(window.result).length === n, cases.length, {timeout: 120000}).catch(() => {});
  assert.deepEqual(errors, []);
  const result = await page.evaluate(() => window.result);
  if (process.env.XYG_DUMP) console.log(JSON.stringify(result, null, 1));
  const baseline = Object.fromEntries(AXES.map((axis) => [axis, result[`${axis}:preserve`]]));
  for (const {axis, strategy, key} of cases) {
    const dom = result[key], svg = svgOf(key);
    for (const id of AXES) {
      // Non-empty visible labels equal the static SVG's label set.
      const visible = dom.labels.filter((l) => l.axis === id && l.text);
      assert.deepEqual(visible.map((l) => l.text).sort(), svg.labels[id].map((l) => l.text).sort(), `${key} ${id} label set`);
      // Rotation matches the SVG (both use clockwise-positive screen degrees).
      for (const label of visible) {
        const match = /rotate\((-?[\d.]+)deg\)/.exec(label.transform);
        const angle = match ? Number(match[1]) : 0;
        assert.ok(svg.labels[id].some((s) => s.text === label.text && Math.abs(s.angle - angle) < 0.01), `${key} ${id} angle of ${label.text}: ${label.transform}`);
      }
      if (id === 'x') assert.equal(new Set(visible.map((l) => l.top)).size > 1, new Set(svg.labels.x.map((l) => l.y)).size > 1, `${key} x rows`);
    }
    if (strategy === 'none') {
      assert.equal(dom.ticks.filter((a) => a === axis).length, 0, `${key} ticks`);
      // The static SVG keeps the frame spines under none (it hides ticks, grid and
      // labels), so the browser must neither add nor drop one.
      assert.deepEqual(dom.spines, baseline[axis].spines, `${key} spines match the SVG frame`);
    } else if (strategy !== 'off') {
      assert.equal(dom.ticks.filter((a) => a === axis).length, baseline[axis].ticks.filter((a) => a === axis).length, `${key} ticks kept`);
    }
  }
  // The crowded x axis really thins, rotates and staggers in the DOM.
  const xs = (strategy) => result[`x:${strategy}`].labels.filter((l) => l.axis === 'x' && l.text);
  assert.ok(xs('hide').length < xs('preserve').length, 'hide thins');
  assert.ok(xs('rotate').every((l) => /rotate/.test(l.transform)), 'rotate rotates');
  assert.ok(new Set(xs('stagger').map((l) => l.top)).size > 1, 'stagger uses two rows');
  console.log(`painter tick strategy: ${cases.length} cases match the SVG`);
} finally { await browser.close(); server.close(); }
