// Live ancestor pseudo-classes and unrelated host SVG rules, using real input.
// No refreshTheme/draw calls occur after the initial authored slot setup.
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import fs from 'node:fs';
import { createServer } from 'node:http';
import path from 'node:path';
import { chromium } from 'playwright';
const [receiptArg, outputName, assetArg] = process.argv.slice(2);
assert.ok(receiptArg && outputName && assetArg, 'receipt, fresh output name, index.js required');
const receipt = path.resolve(receiptArg), output = path.join(receipt, outputName), asset = path.resolve(assetArg);
assert.ok(!fs.existsSync(output), 'append-only: use a new output name');
fs.mkdirSync(output);
const sha = b => createHash('sha256').update(b).digest('hex');
const server = createServer((req, res) => {
  if (req.url === '/') {
    res.setHeader('Content-Type', 'text/html');
    res.end('<!doctype html><style>body{margin:0}.panel{width:320px;height:280px}button{position:absolute;left:200px;top:248px}</style><section class="panel" tabindex="0"><div id="chart"></div><button>Focus / active control</button></section>'); return;
  }
  const name = path.basename(req.url);
  const file = name === 'index.js' ? asset : name === 'slot.scene' ? path.join(receipt, name) : path.join('packages/xy-client/dist', name);
  try { res.setHeader('Content-Type', name.endsWith('.js') ? 'text/javascript' : name.endsWith('.wasm') ? 'application/wasm' : 'application/octet-stream'); res.end(fs.readFileSync(file)); }
  catch { res.writeHead(404); res.end(); }
});
await new Promise(r => server.listen(0, '127.0.0.1', r));
const browser = await chromium.launch({ executablePath: process.env.XYG_CHROMIUM, args: ['--no-sandbox', '--hide-scrollbars', '--use-angle=swiftshader', '--enable-unsafe-swiftshader'] });
const result = { browser: browser.version(), asset: { path: asset, sha256: sha(fs.readFileSync(asset)) }, cases: [], failures: [], masks: [], manualRefreshAfterSetup: false };
const check = (name, fn) => { try { fn(); } catch (e) { result.failures.push({ name, message: e.message }); } };
try {
  for (const dpr of [1, 1.25, 2]) {
    const page = await browser.newPage({ viewport: { width: 360, height: 320 }, deviceScaleFactor: dpr });
    const errors = []; page.on('pageerror', e => errors.push(String(e)));
    await page.goto(`http://127.0.0.1:${server.address().port}/`);
    await page.mouse.move(350, 310);
    await page.evaluate(async () => {
      const client = await import('/index.js');
      window.worker = client.createXygWasmWorker({ workerUrl: '/wasm-worker.js', wasm: '/xyg-wasm.wasm' }); await worker.ready;
      const el = document.getElementById('chart'); Object.assign(el.style, { width: '320px', height: '240px', position: 'relative' });
      window.view = await client.renderWasmScene({ el, worker, scene: await (await fetch('/slot.scene')).arrayBuffer() });
      const css = document.createElement('style'); document.head.appendChild(css);
      css.textContent = '.live-slot{width:80px;height:8px;background:rgb(10,20,30)}.live-slot[data-xy-axis^="y"]{display:none}'
        + '.panel:hover .live-slot{background:rgb(255,0,0)}'
        + '.panel:focus-within .live-slot{background:rgb(0,128,0)}'
        + '.panel:is(:active,:has(button:active)) .live-slot{background:rgb(0,0,255)}'
        + '.panel:hover .live-slot.dynamic-effect{background:linear-gradient(90deg,red,blue);border:2px solid cyan}'
        + '.live-slot.public-important{background:rgb(180,30,60)!important;height:12px!important}';
      view.spec.dom = { class_names: { axis_line: 'live-slot' }, styles: { axis_line: { left: 17, top: 19 } } };
      view.refreshTheme();
      await new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)));
      window.publicSlot = view.labels.querySelector('[data-xy-slot="axis_line"][data-xy-axis="x"]');
      // Unexpected redraws must fail instead of hiding stale SVG paint.
      window.manualCalls = [];
      for (const key of ['refreshTheme', 'draw', '_drawNow', '_drawChrome']) {
        const original = view[key]; view[key] = function (...args) { manualCalls.push(key); return original.apply(this, args); };
      }
      window.hostCss = document.createElement('style'); document.head.appendChild(hostCss);
      window.observe = () => {
        const box = publicSlot, s = getComputedStyle(box), r = box.getBoundingClientRect();
        const svg = view.labels.querySelector('[data-xy-resolved-spine="x"]'), line = svg?.firstElementChild, ls = line && getComputedStyle(line);
        return { plot: { ...view.plot }, samePublicSlot: box === view.labels.querySelector('[data-xy-slot="axis_line"][data-xy-axis="x"]'),
          pseudo: Object.fromEntries(['hover', 'focus-within', 'active'].map(k => [k, document.querySelector('.panel').matches(`:${k}`)])),
          controlActive: document.querySelector('button').matches(':active'),
          public: { background: s.backgroundColor, backgroundImage: s.backgroundImage, borderWidth: s.borderWidth, height: s.height, clipPath: s.clipPath, priority: box.style.getPropertyPriority('background'), rect: { x: r.x, y: r.y, width: r.width, height: r.height } },
          paint: box.dataset.xySpinePaint ?? 'html', svg: svg ? { attrs: Object.fromEntries([...line.attributes].map(a => [a.name, a.value])), computed: Object.fromEntries(['stroke', 'strokeWidth', 'transform', 'strokeDasharray', 'opacity', 'visibility', 'pointerEvents'].map(k => [k, ls[k]])), wrapper: Object.fromEntries(['display', 'width', 'height', 'transform', 'opacity', 'visibility'].map(k => [k, getComputedStyle(svg)[k]])) } : null,
          manualCalls: [...manualCalls] };
      };
    });
    const snap = async name => {
      await page.evaluate(() => new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r))));
      const record = await page.evaluate(() => observe());
      await page.locator('#chart').screenshot({ path: path.join(output, `${name}.dpr${dpr}.png`) });
      result.cases.push({ name, dpr, ...record });
      check(`${name} dpr${dpr}`, () => {
        assert.equal(record.samePublicSlot, true, 'live CSS must preserve the actual public element');
        assert.deepEqual(record.manualCalls, [], 'no redraw may mask automatic CSS');
        if (record.svg) {
          assert.equal(record.svg.computed.stroke, record.public.background, 'private paint must follow public slot');
          assert.equal(Number.parseFloat(record.svg.computed.strokeWidth), record.public.rect.height, 'public slot owns width');
          assert.equal(record.svg.computed.transform, 'none');
          assert.equal(record.svg.computed.strokeDasharray, 'none');
          assert.equal(record.svg.computed.opacity, '1');
          assert.equal(record.svg.computed.pointerEvents, 'none');
          assert.equal(record.svg.computed.visibility, 'visible');
          assert.equal(record.svg.wrapper.display, 'block');
          assert.equal(record.svg.wrapper.width, '320px'); assert.equal(record.svg.wrapper.height, '240px');
          assert.equal(record.svg.wrapper.transform, 'none');
          assert.equal(Number(record.svg.attrs.x1), record.public.rect.x);
          assert.equal(Number(record.svg.attrs.y1), record.public.rect.y + record.public.rect.height / 2);
        }
      });
      return record;
    };
    const base = await snap('idle');
    await page.mouse.move(160, 120); const hover = await snap('hover-enter');
    await page.mouse.move(350, 310); const leave = await snap('hover-leave');
    await page.locator('button').focus(); const focus = await snap('focus-within');
    await page.keyboard.down('Space'); const keyActive = await snap('keyboard-active-down');
    await page.keyboard.up('Space'); await snap('keyboard-active-up');
    await page.locator('button').blur(); const blur = await snap('focus-leave');
    await page.mouse.move(240, 260); await page.mouse.down(); const active = await snap('active-down');
    await page.mouse.up(); await snap('active-up');
    await page.locator('button').blur(); await page.mouse.move(350, 310);
    check(`pseudo controls dpr${dpr}`, () => {
      assert.equal(base.public.background, 'rgb(10, 20, 30)'); assert.equal(hover.public.background, 'rgb(255, 0, 0)');
      assert.equal(hover.pseudo.hover, true); assert.equal(leave.pseudo.hover, false); assert.equal(leave.public.background, base.public.background);
      assert.equal(focus.pseudo['focus-within'], true); assert.equal(focus.public.background, 'rgb(0, 128, 0)');
      assert.equal(keyActive.controlActive, true); assert.equal(keyActive.public.background, 'rgb(0, 0, 255)');
      assert.equal(blur.pseudo['focus-within'], false); assert.equal(active.pseudo.active, true); assert.equal(active.public.background, 'rgb(0, 0, 255)');
    });
    for (const priority of ['', '!important']) {
      for (const kind of ['hidden', 'paint-width', 'geometry']) {
        await page.evaluate(({ priority, kind }) => {
          const rule = kind === 'hidden' ? `svg line{stroke:none${priority}}`
            : kind === 'paint-width' ? `svg line{stroke:magenta${priority};stroke-width:70px${priority}}`
            : `svg line{transform:translate(40px,30px)${priority};stroke-dasharray:1 4${priority};opacity:.2${priority};visibility:hidden${priority}}svg{width:5px${priority};height:9px${priority};transform:translate(20px,10px)${priority};display:none${priority}}`;
          hostCss.textContent = rule;
        }, { priority, kind });
        await snap(`host-${kind}-${priority ? 'important' : 'normal'}`);
      }
    }
    // Public class and direct inline !important styling stay authoritative.
    await page.evaluate(() => { publicSlot.classList.add('public-important'); });
    const cls = await snap('public-class-important');
    await page.evaluate(() => { publicSlot.style.setProperty('background', 'rgb(4, 5, 6)', 'important'); publicSlot.style.setProperty('height', '10px', 'important'); });
    const inline = await snap('public-inline-important');
    check(`public cascade dpr${dpr}`, () => {
      assert.equal(cls.public.background, 'rgb(180, 30, 60)'); assert.equal(cls.public.height, '12px');
      assert.equal(inline.public.background, 'rgb(4, 5, 6)'); assert.equal(inline.public.height, '10px'); assert.equal(inline.public.priority, 'important');
    });
    await page.evaluate(() => { hostCss.textContent = ''; publicSlot.className = 'live-slot dynamic-effect'; publicSlot.style.removeProperty('background'); publicSlot.style.removeProperty('height'); });
    await snap('effect-idle');
    await page.mouse.move(160, 120); const decorated = await snap('effect-hover');
    await page.mouse.move(350, 310); const cleared = await snap('effect-leave');
    check(`live fallback dpr${dpr}`, () => {
      assert.equal(decorated.paint, 'html'); assert.equal(decorated.svg, null);
      assert.ok(decorated.public.backgroundImage.startsWith('linear-gradient('));
      assert.equal(decorated.public.borderWidth, '2px'); assert.equal(decorated.public.clipPath, 'none');
      if (cleared.svg) { assert.equal(cleared.paint, 'svg'); assert.equal(cleared.public.clipPath, 'inset(100%)'); }
      assert.equal(cleared.public.backgroundImage, 'none'); assert.equal(cleared.public.borderWidth, '0px');
    });
    // Destruction while a state update is pending must cancel it and detach
    // the state listeners; unrelated input then remains harmless.
    await page.evaluate(() => { document.dispatchEvent(new Event('pointerover')); view.destroy(); });
    await page.mouse.move(160, 120); await page.mouse.down(); await page.mouse.up();
    await page.evaluate(() => worker.dispose());
    check(`lifecycle dpr${dpr}`, () => assert.deepEqual(errors, []));
    await page.close();
  }
} finally { await browser.close(); server.close(); }
fs.writeFileSync(path.join(output, 'observations.json'), JSON.stringify(result, null, 2) + '\n');
console.log(JSON.stringify({ cases: result.cases.length, failures: result.failures }, null, 2));
if (result.failures.length) process.exitCode = 1;
