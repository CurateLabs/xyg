// Bounded #934/#935 acceptance probe. Produce the Python inputs with
// XYG_GRAPH_PROPERTY_EVIDENCE=<directory> uv run pytest tests/test_graphforge.py
//   -k property_default_exports -q
// Then run XYG_NATIVE_LIB=<release lib> XYG_CHROMIUM=<chrome> node <this> <directory>.
// No layout, styling, label filtering, or screenshot masks are applied here.
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import fs from "node:fs";
import { createServer } from "node:http";
import path from "node:path";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";
import { composeGraphForgeRequest, decodeGraphForgeDocument, graphforgeChart } from "../../packages/xy-node/src/graphforge.js";
import { sceneStaticExport } from "../../packages/xy-node/src/scene.js";
import { xyAbiVersion, nativeLibraryPath } from "../../packages/xy-node/src/native.js";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
assert.ok(process.argv[2], "supply the Python evidence directory");
const output = path.resolve(process.argv[2]);
const fixture = JSON.parse(fs.readFileSync(path.join(root, "tests/fixtures/graphforge/property_default_export.json")));
const bases = path.join(root, "tests/fixtures/graphforge/results");
const base = JSON.parse(fs.readFileSync(path.join(bases, "manifest.json"))).bases.property;
const sha = (bytes) => createHash("sha256").update(bytes).digest("hex");
const json = (value) => JSON.stringify(value, (_, v) => typeof v === "bigint" ? v.toString() : v, 2);
const failures = [];
const results = { contract: fixture.contract, themes: {}, failures };
assert.equal(xyAbiVersion(), 398);
results.native = { abi: xyAbiVersion(), path: nativeLibraryPath, sha256: sha(fs.readFileSync(nativeLibraryPath)) };
results.config = { width: fixture.width, height: fixture.height, themes: fixture.themes, deviceScaleFactor: 1, layoutOverrides: null, masks: [], pixelLimits: { meanMaxChannelDiffExclusive: 3.5, fractionOver96Exclusive: 0.01 }, geometryToleranceCssPixels: 0.01 };
const check = (label, fn) => { try { fn(); } catch (error) { failures.push({ label, message: error.message }); } };

const files = new Map();
for (const side of ["nodes", "edges"]) {
  files.set(`/${side}.arrow`, { bytes: fs.readFileSync(path.join(bases, `${base[side]}.arrow`)), type: "application/octet-stream" });
}
for (const name of ["index.js", "wasm-worker.js", "xyg-wasm.wasm"]) {
  files.set(`/${name}`, { bytes: fs.readFileSync(path.join(root, "packages/xy-client/dist", name)), type: name.endsWith("wasm") ? "application/wasm" : "text/javascript" });
}
results.artifacts = Object.fromEntries([...files].map(([name, file]) => [name, { bytes: file.bytes.length, sha256: sha(file.bytes) }]));
const instance = await WebAssembly.instantiate(files.get("/xyg-wasm.wasm").bytes, {});
assert.equal(instance.instance.exports.xyg_wasm_abi_version(), 35);

const server = createServer((req, res) => {
  const file = files.get(new URL(req.url, "http://localhost").pathname);
  if (!file) { res.writeHead(404); res.end(); return; }
  res.setHeader("Content-Type", file.type); res.end(file.bytes);
});
await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
const origin = `http://127.0.0.1:${server.address().port}`;
const browser = await chromium.launch({ executablePath: process.env.XYG_CHROMIUM ?? process.env.CHROMIUM, args: ["--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--no-sandbox", "--hide-scrollbars"] });
results.browser = browser.version();
try {
  for (const theme of fixture.themes) {
    const request = fs.readFileSync(path.join(output, `${theme}.xygq`));
    const document = composeGraphForgeRequest(request);
    assert.deepEqual(Buffer.from(document), fs.readFileSync(path.join(output, `${theme}.xygf`)), "Python/Node XYGF");
    const composition = decodeGraphForgeDocument(document);
    const render = { width: fixture.width, height: fixture.height, theme };
    const fig = graphforgeChart(composition, render);
    for (const format of ["png", "svg"]) {
      assert.deepEqual(Buffer.from(sceneStaticExport(composition.scene.bytes, format, { ...render, scale: 1 })), fs.readFileSync(path.join(output, `${theme}.${format}`)), `Python/Node canonical ${format}`);
      const native = format === "png" ? fig.toPng({ scale: 1 }) : fig.toSvg();
      assert.deepEqual(Buffer.from(native), fs.readFileSync(path.join(output, `${theme}.native.${format}`)), `Python/Node public ${format}`);
    }
    files.set("/request", { bytes: request, type: "application/octet-stream" });
    files.set("/native", { bytes: fs.readFileSync(path.join(output, `${theme}.native.html`)), type: "text/html" });
    files.set("/", { bytes: Buffer.from('<!doctype html><style>body{margin:0}</style><div id="chart"></div>'), type: "text/html" });
    const page = await browser.newPage({ viewport: { width: fixture.width, height: fixture.height }, deviceScaleFactor: 1 });
    const errors = [];
    page.on("pageerror", (e) => errors.push(String(e)));
    await page.goto(origin);
    const probe = await page.evaluate(async ({ width, height, theme, generation }) => {
      const client = await import("/index.js");
      const worker = client.createXygWasmWorker({ workerUrl: "/wasm-worker.js", wasm: "/xyg-wasm.wasm" });
      await worker.ready;
      const input = await (await fetch("/request")).arrayBuffer();
      const el = document.getElementById("chart");
      Object.assign(el.style, { width: `${width}px`, height: `${height}px`, position: "relative" });
      const tables = await Promise.all(["nodes", "edges"].map(async (side) => new Uint8Array(await (await fetch(`/${side}.arrow`)).arrayBuffer())));
      const { view, composition: first } = await client.renderWasmGraphForge({ el, worker, width, height, theme, input: { base: { tables, generation } } });
      const second = await client.composeWasmGraphForge(worker, input.slice(0)).result;
      await new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve)));
      view._layout(); view._drawNow(); view._raf = null;
      const painted = new Map();
      const points = [];
      const routes = [];
      view.gpuTraces.forEach((trace, t) => {
        const column = (key) => view._columnView(view._payload, view.spec.columns[trace.trace[key]]);
        if (trace.trace.kind === "line" || trace.trace.kind === "segments") {
          const segments = trace.trace.kind === "segments";
          const x = column(segments ? "x0" : "x"), y = column(segments ? "y0" : "y");
          const x1 = segments ? column("x1") : x.subarray(1), y1 = segments ? column("y1") : y.subarray(1);
          for (let i = 0; i < x1.length; i++) {
            const id = view.sceneStableId(t, i).toString();
            routes.push({ id, points: [[x[i], y[i]], [x1[i], y1[i]]].map(([x, y]) => view._projectDataPoint(trace.xAxis, trace.yAxis, x, y, null).slice(0, 2)) });
          }
        }
        for (let i = 0; i < trace._sceneIds.lo.length; i++) {
          const stable = view.sceneStableId(t, i);
          const identity = first.identifyStableId(stable);
          if (identity) painted.set(stable.toString(), identity);
          if (identity?.kind === "node") {
            // XYPB columns are already CSS-pixel f32, without an authoring
            // column offset. Read them as the painter does.
            const x = trace._cpu.x[i], y = trace._cpu.y[i];
            points.push({ id: stable.toString(), point: view._projectDataPoint(trace.xAxis, trace.yAxis, x, y, null).slice(0, 2) });
          }
        }
      });
      return {
        document: Array.from(first.bytes), repeat: Array.from(second.bytes),
        painted: [...painted],
        points,
        routes,
        labels: [...el.querySelectorAll('[data-xy-slot="graph_label"]')].map((e) => ({ id: e.dataset.xyStableId, text: e.textContent, x: parseFloat(e.style.left), y: parseFloat(e.style.top) + parseFloat(e.style.fontSize) })),
        legend: [...el.querySelectorAll('[data-xy-slot="legend_label"]')].map((e) => e.textContent),
        legendBoxes: [...el.querySelectorAll('[data-xy-slot="legend_label"]')].map((e) => {
          const rect = e.getBoundingClientRect(), root = el.getBoundingClientRect();
          return { text: e.textContent, x: rect.x - root.x, y: rect.y - root.y, width: rect.width, height: rect.height };
        }),
      };
    }, { ...render, generation: base.generation });
    assert.deepEqual(Buffer.from(probe.document), Buffer.from(document), "packaged browser Worker/native XYGF");
    assert.deepEqual(probe.repeat, probe.document, "two real Worker compositions");
    delete probe.document; delete probe.repeat;
    check(`${theme}: every painted identity`, () => {
      assert.deepEqual(probe.painted.map(([id]) => id).sort(), [...fixture.edgeUuid.map((_, i) => String(i + 1)), ...fixture.nodeUuid.map((_, i) => String(2 ** 32 + i))].sort());
      for (const [id, identity] of probe.painted) {
        const node = BigInt(id) >= (1n << 32n);
        const index = node ? Number(BigInt(id) - (1n << 32n)) : Number(id) - 1;
        assert.equal(identity.uuid, (node ? fixture.nodeUuid : fixture.edgeUuid)[index]);
        if (!node) {
          assert.equal(identity.source, fixture.nodeUuid[fixture.source[index]]);
          assert.equal(identity.target, fixture.nodeUuid[fixture.target[index]]);
          assert.equal(identity.type, fixture.types[index]);
        }
      }
    });
    check(`${theme}: complete label legend`, () => assert.deepEqual(probe.legend, fixture.legend));
    await page.locator("#chart").screenshot({ path: path.join(output, `${theme}.wasm.browser.png`) });
    await page.goto(`${origin}/native`);
    await page.waitForFunction(() => window.__fcProbeView != null);
    const tickReady = await page.evaluate(() => window.__xygTickReady);
    check(`${theme}: native ticks ready`, () => assert.equal(tickReady.phase, "ticks_ready"));
    const native = await page.evaluate(() => {
      const view = window.__fcProbeView;
      view._layout(); view._drawNow(); view._raf = null;
      const node = view.gpuTraces.find((t) => t.trace.kind === "scatter");
      const points = Array.from(node._cpu.x, (_, i) => {
        const x = view._decodeValue(node._cpu.x, node._cpu.xMeta, i);
        const y = view._decodeValue(node._cpu.y, node._cpu.yMeta, i);
        return view._projectDataPoint(node.xAxis, node.yAxis, x, y, null).slice(0, 2);
      });
      return { points, labels: (view._graphLabelsDrawn ?? []).map(({ text, x, y, width }) => ({ text, x, y, width })), tickEvents: window.__xygTickEvents.map(({ phase }) => ({ phase })) };
    });
    await page.screenshot({ path: path.join(output, `${theme}.native.browser.png`) });
    results.themes[theme] = { wasm: probe, native, errors };
    check(`${theme}: browser errors`, () => assert.deepEqual(errors, []));
    await page.close();
  }
} finally {
  await browser.close(); server.close();
}

// Reuse the repository's RGB decoder and documented graph pixel tolerances
// (graph-mark.md §8). Compare full images, including labels and legend.
fs.writeFileSync(path.join(output, "observations.json"), json(results.themes) + "\n");
const comparison = spawnSync("uv", ["run", "python", "-c", `
import json, sys, xml.etree.ElementTree as ET
from pathlib import Path
sys.path.insert(0, 'tests')
from test_graph_visual_goldens import _rgb
import numpy as np
out = Path(sys.argv[1]); result = {}; observations = json.loads((out/'observations.json').read_text())
for theme in ('light', 'dark'):
    pairs = [('wasm_scene', f'{theme}.png', f'{theme}.wasm.browser.png'),
             ('native_chart', f'{theme}.native.png', f'{theme}.native.browser.png'),
             ('scene_vs_initial_native', f'{theme}.png', f'{theme}.native.browser.png')]
    result[theme] = {}
    for name, reference, browser in pairs:
        a, b = _rgb((out/reference).read_bytes()), _rgb((out/browser).read_bytes())
        assert a.shape == b.shape
        diff = np.abs(a-b).max(axis=2)
        mean, fraction = float(diff.mean()), float((diff>96).mean())
        result[theme][name] = dict(mean_max_channel_diff=mean, fraction_over_96=fraction, passed=mean<3.5 and fraction<0.01)
    svg = ET.fromstring((out/f'{theme}.svg').read_bytes())
    expected = {e.get('data-xy-stable-id'): e for e in svg.iter() if e.get('data-xy-slot')=='graph_label'}
    labels = observations[theme]['wasm']['labels']
    label_errors = [max(abs(float(expected[e['id']].get(axis))-e[axis]) for axis in ('x','y')) for e in labels]
    texts_match = {e['id']: e['text'] for e in labels} == {key: e.text for key,e in expected.items()}
    error = max(label_errors, default=float('inf'))
    result[theme]['wasm_label_geometry'] = dict(max_css_pixel_error=error, texts_match=texts_match, passed=texts_match and error<=0.01)
    group = next(e for e in svg.iter() if e.get('clip-path'))
    centers = []
    for e in group:
        kind = e.tag.split('}')[-1]
        if kind=='circle': centers.append([float(e.get('cx')),float(e.get('cy'))])
        elif kind=='rect': centers.append([float(e.get('x'))+float(e.get('width'))/2,float(e.get('y'))+float(e.get('height'))/2])
        elif kind=='path':
            parts = e.get('d').split(); centers.append([float(parts[1]),float(parts[5])])
    actual = [e['point'] for e in observations[theme]['wasm']['points']]
    error = float(np.abs(np.array(centers)-np.array(actual)).max())
    result[theme]['wasm_node_geometry'] = dict(max_css_pixel_error=error, passed=len(centers)==len(actual)==5 and error<=0.01)
    expected = [[[float(v) for v in point.split(',')] for point in e.get('points').split()] for e in group if e.tag.endswith('}polyline')]
    routes = observations[theme]['wasm']['routes']
    actual = [route['points'] for route in routes]
    error = float(np.abs(np.array(expected)-np.array(actual)).max())
    counts = {str(i): sum(route['id']==str(i) for route in routes) for i in range(1,6)}
    result[theme]['wasm_route_geometry'] = dict(max_css_pixel_error=error, pieces_by_stable_id=counts, passed=error<=0.01 and list(counts.values())==[3,3,5,3,3])
print(json.dumps(result))
`, output], { cwd: root, encoding: "utf8" });
assert.equal(comparison.status, 0, comparison.stderr);
results.pixels = JSON.parse(comparison.stdout);
for (const [theme, comparisons] of Object.entries(results.pixels)) {
  for (const [name, metrics] of Object.entries(comparisons)) {
    if (!metrics.passed) failures.push({ label: `${theme}: ${name} pixels`, ...metrics });
  }
}
results.outputs = Object.fromEntries(fs.readdirSync(output).filter((name) => /\.(png|svg|xygf|xygq)$/.test(name)).map((name) => [name, sha(fs.readFileSync(path.join(output, name)))]));
fs.writeFileSync(path.join(output, "browser.json"), json(results) + "\n");
console.log(JSON.stringify({ pixels: results.pixels, failures }, null, 2));
if (failures.length) process.exitCode = 1;
