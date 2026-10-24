// Repository-only #886 cases. All XYG imports/assets come from clean installs;
// the browser mounts through the actual vanilla TypeScript consumer app.
import { createServer } from 'node:http';
import { readFile, writeFile } from 'node:fs/promises';
import { createRequire, stripTypeScriptTypes } from 'node:module';
import { dirname, join } from 'node:path';
import { pathToFileURL } from 'node:url';

const resolve = createRequire(join(process.env.XYG_CONSUMER_INSTALL, 'package.json')).resolve;
const { figure } = await import(pathToFileURL(resolve('@curatelabs/xyg-node')).href);
const client = dirname(resolve('@curatelabs/xyg'));
const app = stripTypeScriptTypes(await readFile(new URL('../../examples/vanilla-ts/app.ts', import.meta.url), 'utf8'));
const payloads = new Map();
for (const kind of ['secondary', 'polar', 'density', 'missing', 'corrupt']) {
  const fig = figure({ width: 480, height: 360 });
  if (kind === 'polar') {
    fig.setPolarMeta({ thetaUnit: 'degrees' });
    fig.setAxisDomain('x', [0, 360]); fig.setAxisDomain('y', [0, 1]);
    fig.line([0, 90, 180, 270, 360], [0.5, 0.8, 0.6, 0.9, 0.5], { color: '#dc2626' });
  } else if (kind === 'density') {
    fig.setAxisDomain('x', [0, 1]); fig.setAxisDomain('y', [0, 1]);
    const values = Float64Array.from({ length: 30_000 }, (_, i) => i / 29_999);
    fig.scatter(values, values, { forceDensity: true });
  } else {
    fig.setAxis('x', { domain: [0, 4] }); fig.setAxis('y', { domain: [0, 4] });
    fig.setAxis('y2', { domain: [0, 400], side: 'right' });
    fig.line([1, 2, 3], [1, 2, 3], { color: '#dc2626' });
    fig.line([1, 2, 3], [100, 200, 300], { yAxis: 'y2', color: '#2563eb' });
  }
  const payload = fig.buildPayload({ split: kind === 'density' });
  payload.spec.wasm_ticks = { workerUrl: '/assets/wasm-worker.js',
    wasm: `/assets/${['missing', 'corrupt'].includes(kind) ? kind : 'xyg-wasm'}.wasm` };
  payloads.set(kind, payload);
  await writeFile(join(process.env.XYG_CONSUMER_EVIDENCE, `node-${kind}.spec.json`), JSON.stringify(payload.spec));
  const planes = Array.isArray(payload.buffers) ? payload.buffers : [payload.buffers];
  for (const [index, plane] of planes.entries())
    await writeFile(join(process.env.XYG_CONSUMER_EVIDENCE, `node-${kind}.buffer-${index}.bin`), plane);
}
const files = new Map([
  ['/client.js', [join(client, 'index.js'), 'text/javascript']],
  ['/assets/wasm-worker.js', [join(client, 'wasm-worker.js'), 'text/javascript']],
  ['/assets/xyg-wasm.wasm', [join(client, 'xyg-wasm.wasm'), 'application/wasm']],
]);
const server = createServer(async (req, res) => {
  res.setHeader('Cache-Control', 'no-store');
  res.setHeader('X-Content-Type-Options', 'nosniff');
  res.setHeader('Content-Security-Policy', "default-src 'none'; script-src 'self' 'unsafe-inline' 'wasm-unsafe-eval'; style-src 'unsafe-inline'; worker-src 'self'; connect-src 'self'; img-src 'self' data:; object-src 'none'; base-uri 'none'");
  try {
    const url = new URL(req.url, 'http://localhost');
    if (req.method !== 'GET') { res.writeHead(405).end(); return; }
    if (files.has(url.pathname)) {
      const [file, mime] = files.get(url.pathname);
      res.setHeader('Content-Type', mime); res.end(await readFile(file)); return;
    }
    if (url.pathname === '/assets/corrupt.wasm') {
      res.setHeader('Content-Type', 'application/wasm'); res.end(Buffer.from([0, 1, 2, 3])); return;
    }
    if (url.pathname === '/app.js') { res.setHeader('Content-Type', 'text/javascript'); res.end(app); return; }
    if (url.pathname === '/density.js') {
      res.setHeader('Content-Type', 'text/javascript');
      res.end(await readFile(new URL('./packaged_density_consumer.mjs', import.meta.url))); return;
    }
    if (['/spec', '/buffers'].includes(url.pathname)) {
      const payload = payloads.get(url.searchParams.get('kind'));
      if (!payload) { res.writeHead(400).end(); return; }
      res.setHeader('Content-Type', url.pathname === '/spec' ? 'application/json' : 'application/octet-stream');
      if (url.pathname === '/spec') res.end(JSON.stringify(payload.spec));
      else {
        const plane = Array.isArray(payload.buffers) ? payload.buffers[Number(url.searchParams.get('index'))] : payload.buffers;
        res.end(new Uint8Array(plane.buffer, plane.byteOffset, plane.byteLength));
      }
      return;
    }
    if (url.pathname !== '/') { res.writeHead(404).end(); return; }
    const kind = url.searchParams.get('kind') ?? 'secondary';
    if (!payloads.has(kind)) { res.writeHead(400).end(); return; }
    res.setHeader('Content-Type', 'text/html');
    res.end(`<!doctype html><html lang="en"><meta charset="utf-8"><title>Packaged consumer qualification</title>
<style>body{font:16px system-ui}#chart{width:480px;height:360px}</style>
<select id="kind">${[...payloads.keys()].map(k => `<option${k === kind ? ' selected' : ''}>${k}</option>`).join('')}</select>
<button id="update">Update</button><button id="dispose">Dispose</button><a id="export">Export</a>
<output id="status"></output><div id="chart"></div><output id="selection"></output>
<script type="module" src="${kind === 'density' ? '/density.js' : '/app.js'}"></script></html>`);
  } catch (error) { console.error(error); res.writeHead(500).end('fixture failed'); }
});
server.listen(Number(process.env.PORT), '127.0.0.1');
for (const signal of ['SIGINT', 'SIGTERM']) process.on(signal, () => server.close(() => process.exit(0)));
