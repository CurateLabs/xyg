// Node 22.13+ consumer. No Python, web framework, or browser APIs in this host.
import { createServer } from 'node:http';
import { readFile } from 'node:fs/promises';
import { createRequire, stripTypeScriptTypes } from 'node:module';
import { dirname, join } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
const installed = process.env.XYG_CONSUMER_INSTALL;
const resolve = installed ? createRequire(join(installed, 'package.json')).resolve : null;
const host = resolve ? resolve('@curatelabs/xyg-node') : fileURLToPath(new URL('../../packages/xy-node/src/index.js', import.meta.url));
const { figure } = await import(pathToFileURL(host).href);
const client = resolve ? dirname(resolve('@curatelabs/xyg')) : fileURLToPath(new URL('../../packages/xy-client/dist/', import.meta.url));

const kinds = new Set(['scatter', 'line', 'bar', 'graph']);
function chart(kind, count) {
  const x = Array.from({ length: count }, (_, i) => i);
  const y = x.map(i => (i * 7) % 13);
  const fig = figure({ width: 720, height: 360, title: `${kind} · ${count} rows` });
  if (kind === 'graph') {
    const nodes = x.map(i => `n${i}`);
    fig.graph(nodes, nodes.slice(1).map((node, i) => [nodes[i], node]), { layout: 'circle' });
  } else fig[kind](x, y, { color: '#dc2626' });
  return fig;
}
const app = stripTypeScriptTypes(await readFile(new URL('./app.ts', import.meta.url), 'utf8'));
const html = `<!doctype html><html lang="en"><meta charset="utf-8"><title>XYG · vanilla TypeScript</title>
<style>body{font:16px system-ui;max-width:760px;margin:32px auto}#chart{height:360px}button,select{font:inherit;margin:8px}output{display:block}</style>
<h1>XYG in vanilla TypeScript</h1><label>Chart <select id="kind">${[...kinds].map(k => `<option>${k}</option>`).join('')}</select></label>
<button id="update">Add eight rows</button><button id="dispose">Dispose chart</button>
<a id="export" href="/export.svg?kind=scatter&count=8">Download SVG</a>
<output id="status" aria-live="polite">Loading</output><div id="chart"></div>
<output id="selection" aria-live="polite">Shift-drag to select in the browser</output>
<script type="module" src="/app.js"></script></html>`;
const assets = new Map([
  ['/client.js', [join(client, 'index.js'), 'text/javascript']],
  ['/assets/wasm-worker.js', [join(client, 'wasm-worker.js'), 'text/javascript']],
  ['/assets/xyg-wasm.wasm', [join(client, 'xyg-wasm.wasm'), 'application/wasm']],
]);
// Bounded deterministic fixture cache; the metadata and binary endpoints share one compile.
const cache = new Map();
const server = createServer(async (req, res) => {
  res.setHeader('Cache-Control', 'no-store');
  res.setHeader('X-Content-Type-Options', 'nosniff');
  res.setHeader('Content-Security-Policy', "default-src 'self'; script-src 'self' 'wasm-unsafe-eval'; style-src 'self' 'unsafe-inline'; worker-src 'self'; object-src 'none'; base-uri 'none'");
  try {
    if (req.method !== 'GET') { res.writeHead(405).end(); return; }
    const url = new URL(req.url, 'http://localhost');
    if (url.pathname === '/') { res.setHeader('Content-Type', 'text/html'); res.end(html); return; }
    if (url.pathname === '/app.js') { res.setHeader('Content-Type', 'text/javascript'); res.end(app); return; }
    if (assets.has(url.pathname)) {
      const [path, mime] = assets.get(url.pathname);
      res.setHeader('Content-Type', mime); res.end(await readFile(path)); return;
    }
    if (!['/spec', '/buffers', '/export.svg'].includes(url.pathname)) { res.writeHead(404).end(); return; }
    const kind = url.searchParams.get('kind') ?? 'scatter';
    const count = Number(url.searchParams.get('count') ?? 8);
    if (!kinds.has(kind) || ![8, 16, 24, 32].includes(count)) { res.writeHead(400).end('invalid chart request'); return; }
    const key = `${kind}:${count}`;
    if (!cache.has(key)) {
      const fig = chart(kind, count);
      const { spec, buffers } = fig.buildPayload();
      spec.wasm_ticks = { workerUrl: '/assets/wasm-worker.js', wasm: '/assets/xyg-wasm.wasm' };
      cache.set(key, { fig, spec, buffers });
    }
    const { fig, spec, buffers } = cache.get(key);
    if (url.pathname === '/spec') { res.setHeader('Content-Type', 'application/json'); res.end(JSON.stringify(spec)); }
    else if (url.pathname === '/buffers') { res.setHeader('Content-Type', 'application/octet-stream'); res.end(buffers); }
    else { res.setHeader('Content-Type', 'image/svg+xml'); res.end(fig.toSvg()); }
  } catch (error) { console.error(error); res.writeHead(500).end('chart request failed'); }
});
server.listen(Number(process.env.PORT ?? 3000), '127.0.0.1', () => {
  console.log(`XYG_CONSUMER_PACKAGE=${host}`);
  console.log(`XYG_CONSUMER_URL=http://127.0.0.1:${server.address().port}`);
});
for (const signal of ['SIGINT', 'SIGTERM']) process.on(signal, () => server.close(() => process.exit(0)));
