// R4 actual-browser CSS/hit-region compatibility against independently built
// 188f. All styling enters through public slots/classes; no product DOM paint,
// geometry, pointer policy, native export or test reporter is monkeypatched.
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import fs from 'node:fs';
import { createServer } from 'node:http';
import path from 'node:path';
import { chromium } from 'playwright';

const [receiptArg, outputName, candidateArg] = process.argv.slice(2);
assert.ok(receiptArg && outputName && candidateArg, 'receipt, fresh output name and candidate index.js required');
const receipt = path.resolve(receiptArg), output = path.join(receipt, outputName);
assert.ok(!fs.existsSync(output), 'append-only: output must be new');
fs.mkdirSync(output);
const baseline = path.resolve('target/task-tmp/resolved-spine-188f-baseline/packages/xy-client/dist/index.js');
const candidate = path.resolve(candidateArg);
const sha = bytes => createHash('sha256').update(bytes).digest('hex');
assert.equal(sha(fs.readFileSync(baseline)), '351fa5038800204a13a99ae9cb91612472e3368f6d7ecd4829d589e39b16acd7');
const server = createServer((req, res) => {
  try {
    if (req.url === '/') {
      res.setHeader('Content-Type', 'text/html');
      res.end('<!doctype html><style>body{margin:0}</style><div id="chart"></div>'); return;
    }
    const name = path.basename(req.url);
    const file = req.url === '/baseline/index.js' ? baseline : req.url === '/candidate/index.js' ? candidate
      : name === 'slot.scene' ? path.join(receipt, name) : path.join('packages/xy-client/dist', name);
    res.setHeader('Content-Type', name.endsWith('.js') ? 'text/javascript' : name.endsWith('.wasm') ? 'application/wasm' : 'application/octet-stream');
    res.end(fs.readFileSync(file));
  } catch { res.writeHead(404); res.end(); }
});
await new Promise(r => server.listen(0, '127.0.0.1', r));
const browser = await chromium.launch({ executablePath: process.env.XYG_CHROMIUM, args: ['--no-sandbox', '--hide-scrollbars', '--use-angle=swiftshader', '--enable-unsafe-swiftshader'] });
const result = { purpose: 'Real public-slot compatibility; supported features only; no masks or supplied plot', browser: browser.version(),
  assets: Object.fromEntries([['baseline', baseline], ['candidate', candidate], ['wasm', 'packages/xy-client/dist/xyg-wasm.wasm'], ['worker', 'packages/xy-client/dist/wasm-worker.js']].map(([k, p]) => [k, { path: p, sha256: sha(fs.readFileSync(p)) }])),
  cases: [], switches: [], skipped: [], failures: [] };
try {
  for (const lane of ['baseline', 'candidate']) {
    const page = await browser.newPage({ viewport: { width: 320, height: 240 }, deviceScaleFactor: 1 });
    const errors = []; page.on('pageerror', e => errors.push(String(e)));
    await page.goto(`http://127.0.0.1:${server.address().port}/`);
    await page.evaluate(async lane => {
      window.client = await import(`/${lane}/index.js`);
      window.worker = client.createXygWasmWorker({ workerUrl: '/wasm-worker.js', wasm: '/xyg-wasm.wasm' }); await worker.ready;
      window.support = { motion: CSS.supports('offset-path', 'path("M 60 60 L 140 140")'), reflection: CSS.supports('-webkit-box-reflect', 'below 4px') };
      window.observe = () => {
        const box = view.labels.querySelector('[data-xy-slot="axis_line"][data-xy-axis="x"]');
        const attrs = e => Object.fromEntries([...e.attributes].map(a => [a.name, a.value]));
        const read = e => { const s = getComputedStyle(e), r = e.getBoundingClientRect(); return {
          box: { x: r.x, y: r.y, width: r.width, height: r.height }, client: { width: e.clientWidth, height: e.clientHeight },
          computed: Object.fromEntries(['width', 'height', 'pointerEvents', 'zIndex', 'clipPath', 'transform', 'translate', 'rotate', 'scale', 'offsetPath', 'offsetDistance', 'offsetRotate', 'offsetAnchor', 'webkitBoxReflect'].map(k => [k, s[k] ?? null])) }; };
        return { plot: { ...view.plot }, dpr: devicePixelRatio, support, publicBox: read(box), className: box.className,
          inlinePointerEvents: box.style.pointerEvents, paint: box.dataset.xySpinePaint ?? 'html',
          ancestors: [view.labels, view.root, document.body].map(read),
          svg: [...view.labels.querySelectorAll('[data-xy-resolved-spine]')].map(e => ({ axis: e.dataset.xyResolvedSpine, side: e.dataset.xySpineSide, attributes: attrs(e.firstElementChild), matrix: Object.fromEntries(['a','b','c','d','e','f'].map(k => [k, e.getScreenCTM()[k]])) })) };
      };
      window.setup = async name => {
        window.view?.destroy(); window.css?.remove(); const el = document.getElementById('chart'); el.replaceChildren();
        Object.assign(el.style, { width: '320px', height: '240px', position: 'relative' });
        window.view = await client.renderWasmScene({ el, worker, scene: await (await fetch('/slot.scene')).arrayBuffer() });
        window.css = document.createElement('style'); document.head.appendChild(css);
        css.textContent = '.eligibility-probe[data-xy-axis^="y"]{display:none}'
          + '.pointer-probe:hover{outline:2px solid blue}'
          + '.pointer-important{pointer-events:auto!important}.pointer-off .pointer-important{pointer-events:none!important}'
          + '.motion-probe{offset-path:path("M 60 60 L 140 140");offset-distance:35px;offset-rotate:auto}'
          + '.motion-ancestor [data-xy-slot="labels"]{offset-path:path("M 150 110 L 190 150");offset-distance:20px;offset-rotate:auto}'
          + '.reflection-probe{-webkit-box-reflect:below 4px}';
        const pointer = name.startsWith('pointer-');
        let cls = 'eligibility-probe';
        if (pointer) cls += ' pointer-probe';
        if (name === 'pointer-important') cls += ' pointer-important';
        if (name === 'motion-box') cls += ' motion-probe';
        if (name === 'reflection') cls += ' reflection-probe';
        const styles = { left: name === 'motion-ancestor' ? 120 : 17, top: name === 'motion-ancestor' ? 110 : 19, width: 80, height: 8, background: 'red', 'z-index': 99, 'pointer-events': name === 'pointer-inline' ? 'auto' : 'none' };
        view.spec.dom = { class_names: { axis_line: cls }, styles: { axis_line: styles } };
        if (name === 'motion-ancestor') view.root.classList.add('motion-ancestor');
        view.refreshTheme(); await new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)));
        window.clicked = 0;
        view.labels.addEventListener('click', e => { if (e.target.closest('[data-xy-slot="axis_line"][data-xy-axis="x"]')) clicked++; });
        return observe();
      };
    }, lane);
    const interact = async () => {
      const before = await page.evaluate(() => {
        const box = view.labels.querySelector('[data-xy-slot="axis_line"][data-xy-axis="x"]'), hit = document.elementFromPoint(22, 22);
        return { hitPublicSlot: hit === box, hitTag: hit?.tagName, hitSlot: hit?.dataset.xySlot ?? null, stack: document.elementsFromPoint(22, 22).map(e => ({ tag: e.tagName, slot: e.dataset.xySlot ?? null })), clicksBefore: clicked };
      });
      await page.mouse.move(22, 22); await page.mouse.click(22, 22);
      return { ...before, ...await page.evaluate(() => ({ clicks: clicked, hover: view.labels.querySelector('[data-xy-slot="axis_line"][data-xy-axis="x"]').matches(':hover') })) };
    };
    for (const name of ['control-solid', 'pointer-inline', 'pointer-important', 'motion-box', 'motion-ancestor', 'reflection']) {
      await page.mouse.move(310, 230);
      const supported = await page.evaluate(name => name.startsWith('motion-') ? support.motion : name === 'reflection' ? support.reflection : true, name);
      if (!supported) { result.skipped.push({ lane, name, reason: 'CSS.supports false in this browser; not a passing compatibility claim' }); continue; }
      const record = await page.evaluate(name => setup(name), name);
      if (name.startsWith('pointer-')) record.interaction = await interact();
      await page.locator('#chart').screenshot({ path: path.join(output, `${name}.${lane}.png`) });
      result.cases.push({ lane, name, ...record });
    }
    for (const variant of ['pointer-inline', 'pointer-important']) {
      await page.mouse.move(310, 230); await page.evaluate(name => setup(name), variant);
      for (const mode of ['auto', 'none', 'auto']) {
        await page.mouse.move(310, 230);
        const record = await page.evaluate(async ({ variant, mode }) => {
          if (variant === 'pointer-inline') { view.spec.dom.styles.axis_line['pointer-events'] = mode; view.refreshTheme(); }
          else { view.root.classList.toggle('pointer-off', mode === 'none'); }
          await new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r))); return observe();
        }, { variant, mode });
        record.interaction = await interact();
        const iteration = result.switches.filter(r => r.lane === lane && r.variant === variant).length;
        await page.locator('#chart').screenshot({ path: path.join(output, `${variant}.switch${iteration}.${lane}.png`) });
        result.switches.push({ lane, variant, mode, iteration, ...record });
      }
    }
    assert.deepEqual(errors, []); await page.evaluate(() => { view.destroy(); worker.dispose(); }); await page.close();
  }
} finally { await browser.close(); server.close(); }
const check = (name, fn) => { try { fn(); } catch (e) { result.failures.push({ name, message: e.message }); } };
for (const row of result.cases.filter(r => r.lane === 'candidate')) {
  const baseline = result.cases.find(r => r.lane === 'baseline' && r.name === row.name);
  check(row.name, () => {
    assert.deepEqual(row.plot, baseline.plot);
    assert.deepEqual(row.publicBox.box, baseline.publicBox.box);
    if (row.name.startsWith('pointer-')) {
      assert.equal(baseline.interaction.hitPublicSlot, true, 'baseline z-index positive control must hit public slot');
      assert.equal(baseline.interaction.clicks, 1); assert.equal(baseline.interaction.hover, true);
      assert.equal(row.interaction.hitPublicSlot, true); assert.equal(row.interaction.clicks, 1); assert.equal(row.interaction.hover, true);
    }
    const expected = row.name === 'control-solid' ? 'svg' : 'html';
    assert.equal(row.paint, expected); assert.equal(row.svg.length, expected === 'svg' ? 1 : 0);
    assert.deepEqual(fs.readFileSync(path.join(output, `${row.name}.candidate.png`)), fs.readFileSync(path.join(output, `${row.name}.baseline.png`)));
  });
}
for (const row of result.switches.filter(r => r.lane === 'candidate')) {
  const baseline = result.switches.find(r => r.lane === 'baseline' && r.variant === row.variant && r.iteration === row.iteration);
  check(`${row.variant} switch ${row.iteration}`, () => {
    for (const state of [baseline, row]) {
      assert.equal(state.publicBox.computed.pointerEvents, row.mode);
      assert.equal(state.interaction.hitPublicSlot, row.mode === 'auto');
      assert.equal(state.interaction.clicks - state.interaction.clicksBefore, row.mode === 'auto' ? 1 : 0);
      assert.equal(state.interaction.hover, row.mode === 'auto');
    }
    const expected = row.mode === 'auto' ? 'html' : 'svg';
    assert.equal(row.paint, expected); assert.equal(row.svg.length, expected === 'svg' ? 1 : 0);
    assert.equal(row.publicBox.computed.clipPath, expected === 'svg' ? 'inset(100%)' : 'none');
    assert.deepEqual(fs.readFileSync(path.join(output, `${row.variant}.switch${row.iteration}.candidate.png`)), fs.readFileSync(path.join(output, `${row.variant}.switch${row.iteration}.baseline.png`)));
  });
}
fs.writeFileSync(path.join(output, 'observations.json'), JSON.stringify(result, null, 2) + '\n');
console.log(JSON.stringify({ cases: result.cases.length, switches: result.switches.length, skipped: result.skipped, failures: result.failures }, null, 2));
if (result.failures.length) process.exitCode = 1;
