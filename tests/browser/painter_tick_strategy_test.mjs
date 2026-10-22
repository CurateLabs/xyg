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
const scene = (axis, strategy, extra = {}) => {
  const fig = new Figure({width: 110, height: 80, showLegend: false, xAxis: {domain: [0, 3000000]}, yAxis: {domain: [0, 4]}});
  fig.setAxis('y2', {side: 'right', domain: [0, 400]});
  fig.line([0, 1000000, 3000000], [1, 3, 2]);
  fig.line([0, 1000000, 3000000], [100, 300, 200], {yAxis: 'y2'});
  fig.setAxis(axis, {tick_label_strategy: strategy, ...extra});
  return fig.toScene();
};
const cases = AXES.flatMap((axis) => STRATEGIES.map((strategy) => ({axis, strategy, key: `${axis}:${strategy}`})));
cases.push(
  {axis: 'x', strategy: 'rotate', key: 'x:rotate:both', extra: {tick_label_sides: ['bottom', 'top']}},
  {axis: 'x', strategy: 'rotate', key: 'x:rotate:both:explicit', extra: {tick_label_sides: ['bottom', 'top'], tick_label_angle: 20}},
);
for (const angle of [350, -350]) {
  for (const anchor of [null, angle > 0 ? 'end' : 'start']) {
    cases.push({axis: 'x', strategy: 'preserve', key: `x:${angle}:${anchor ?? 'default'}`, extra: {tick_label_sides: ['bottom', 'top'], tick_label_angle: angle, ...(anchor ? {tick_label_anchor: anchor} : {})}});
  }
}
const scenes = Object.fromEntries(cases.map((c) => [c.key, scene(c.axis, c.strategy, c.extra)]));
const painters = Object.fromEntries(cases.map((c) => [c.key, Buffer.from(sceneBrowserPainter(scenes[c.key])).toString('base64')]));
const page_js = `import {hydrateWasmPainter} from '/index.js';
const painters = ${JSON.stringify(painters)};
window.result = {};
for (const [name, b64] of Object.entries(painters)) {
  const painter = Uint8Array.from(atob(b64), (c) => c.charCodeAt(0)).buffer;
  const host = document.createElement('div'); host.style.cssText = 'width:110px;height:80px'; document.body.appendChild(host);
  const view = hydrateWasmPainter(host, {painter, sceneBytes: 0, wasmMemoryBytes: 0, traceCount: 2}, {workerPrepareMs: 0});
  const deadline = performance.now() + 10000;
  while (host.querySelectorAll('[data-xy-slot="axis_line"]').length < 3) {
    if (performance.now() > deadline) throw new Error(name + ': chrome did not render');
    await new Promise(requestAnimationFrame);
  }
  const pick = (slot) => [...host.querySelectorAll('[data-xy-slot="' + slot + '"]')];
  window.result[name] = {
    labels: pick('tick_label').map((el) => ({text: el.textContent, axis: el.dataset.xyAxis, side: el.dataset.xyAxisSide, transform: el.style.transform, top: parseFloat(el.style.top)})),
    ticks: pick('tick_mark').map((el) => el.dataset.xyAxis),
    spines: pick('axis_line').map((el) => el.dataset.xyAxis + ':' + el.dataset.xyAxisSide),
  };
  view.destroy(); host.remove();
}`;
const svgOf = (key) => {
  const svg = Buffer.from(sceneSvg(scenes[key])).toString('utf8');
  const out = {x: [], y: [], y2: []};
  const [, left, top, width, height] = /data-xy-chrome="plot-background" x="([^"]+)" y="([^"]+)" width="([^"]+)" height="([^"]+)"/.exec(svg).map((v, i) => i ? Number(v) : v);
  const right = left + width, bottom = top + height;
  for (const m of svg.matchAll(/<text x="([^"]+)" y="([^"]+)"[^>]*text-anchor="(\w+)"( transform="rotate\(([-\d.]+) )?[^>]*>([^<]*)<\/text>/g)) {
    const [, x, y, anchor, , angle, text] = m;
    const axis = Number(x) >= left && Number(x) <= right ? 'x' : Number(x) < left ? 'y' : 'y2';
    const side = axis === 'x' ? Number(y) < top ? 'top' : 'bottom' : axis === 'y' ? 'left' : 'right';
    out[axis].push({text, side, anchor, angle: Number(angle ?? 0), y: Number(y)});
  }
  const axes = svg.slice(svg.indexOf('data-xy-chrome="axes"'));
  // Compare actual SVG frame edges, excluding the short tick-mark lines.
  const spines = [];
  for (const m of axes.matchAll(/<line x1="([^"]+)" y1="([^"]+)" x2="([^"]+)" y2="([^"]+)"/g)) {
    const [x1, y1, x2, y2] = m.slice(1).map(Number);
    if (x1 === left && x2 === right && y1 === y2 && [top, bottom].includes(y1)) spines.push(`x:${y1 === top ? 'top' : 'bottom'}`);
    if (y1 === top && y2 === bottom && x1 === x2) {
      if (x1 === left) spines.push('y:left');
      if (x1 === right) spines.push('y2:right');
    }
  }
  return {labels: out, spines};
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
  const fault = new Promise((resolve) => page.on('pageerror', (e) => { errors.push(e.message); resolve(); }));
  await page.goto(`http://127.0.0.1:${server.address().port}/`);
  await Promise.race([page.waitForFunction((n) => window.result && Object.keys(window.result).length === n, cases.length, {timeout: 120000}), fault]);
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
      // Match each duplicate label to its own side before checking rotation.
      for (const label of visible) {
        const expected = svg.labels[id].find((s) => s.text === label.text && s.side === label.side);
        assert.ok(expected, `${key} ${id} ${label.side} label ${label.text}`);
        const match = /rotate\((-?[\d.]+)deg\)/.exec(label.transform);
        const angle = match ? Number(match[1]) : 0;
        const difference = Math.abs(expected.angle - angle) % 360;
        assert.ok(Math.min(difference, 360 - difference) < 0.01, `${key} ${id} ${label.side} angle of ${label.text}: ${label.transform}`);
        if (id === 'x') {
          const shift = expected.anchor === 'end' ? '-100%' : expected.anchor === 'middle' ? '-50%' : '0%';
          assert.ok(label.transform.startsWith('translateX(' + shift + ')'), `${key} ${label.side} anchor of ${label.text}: ${label.transform}`);
          // Rank baselines outward on each side, then compare the row of every
          // label. A swapped alternating row must fail even with two rows left.
          const outward = label.side === 'top' ? -1 : 1;
          const rows = (values) => [...new Set(values)].sort((a, b) => outward * (a - b));
          const domRows = rows(visible.filter((l) => l.side === label.side).map((l) => l.top));
          const svgRows = rows(svg.labels.x.filter((l) => l.side === label.side).map((l) => l.y));
          assert.equal(domRows.indexOf(label.top), svgRows.indexOf(expected.y), `${key} ${label.side} row of ${label.text}`);
        }
      }
    }
    assert.deepEqual(dom.spines.slice().sort(), svg.spines.slice().sort(), `${key} spines match the SVG frame`);
    if (strategy === 'none') {
      assert.equal(dom.ticks.filter((a) => a === axis).length, 0, `${key} ticks`);
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
