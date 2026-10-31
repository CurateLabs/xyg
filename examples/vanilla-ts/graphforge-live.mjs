// Bounded GraphForge live consumer: full ChartView replacement, as in app.ts.
// No retained graph controller or S5 host adapter is implemented by this fixture.
import { createServer } from 'node:http';
import { readFile } from 'node:fs/promises';
import { performance } from 'node:perf_hooks';
import { createHash } from 'node:crypto';
import { GraphForgeLayoutController, graphforgeWebviewPayload } from '../../packages/xy-node/src/graphforge.js';

const root = new URL('../../', import.meta.url);
const manifest = JSON.parse(await readFile(new URL('tests/fixtures/graphforge/results/manifest.json', root)));
const base = manifest.bases.cyclic;
const input = { base: { generation: base.generation, tables: await Promise.all([base.nodes, base.edges].map(name =>
  readFile(new URL(`tests/fixtures/graphforge/results/${name}.arrow`, root)))) } };
const client = new URL('packages/xy-client/dist/standalone.js', root);
const owner = new GraphForgeLayoutController();
let current, accept, waiting, failure, completed = false, started, sourceNodes;
const events = [], lags = [];
let lastTick = performance.now();
const ticker = setInterval(() => { const now = performance.now(); lags.push(now - lastTick - 5); lastTick = now; }, 5);
function event(type, detail = {}) { events.push({ type, ms: performance.now() - started, ...detail }); }
function metadata(payload) { return { spec: payload.spec, revision: payload.revision, jobId: payload.jobId,
  step: payload.step, phase: payload.phase, nodeTrace: payload.nodeTrace }; }
function respond(res, value) { res.setHeader('Content-Type', 'application/json'); res.end(JSON.stringify(value)); }
function wake() {
  if (!waiting) return;
  if (current) { respond(waiting, metadata(current)); waiting = undefined; }
  else if (failure) { waiting.writeHead(500).end(String(failure)); waiting = undefined; }
  else if (completed) { waiting.writeHead(204).end(); waiting = undefined; }
}
const app = `
const element = document.getElementById('chart');
window.proof = { checkpoints: [], clicks: [], errors: [] };
let view, disposed = false;
const frame = () => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)));
element.addEventListener('xy:click', async e => {
 const began = performance.now();
 const response = await fetch('/pick', {method:'POST',body:JSON.stringify(e.detail)});
 proof.clicks.push({detail:e.detail,identity:await response.json(),responseMs:performance.now()-began,atMs:performance.now()-proof.started});
});
window.disposeGraph = () => { disposed=true; view?.destroy(); element.replaceChildren(); };
window.beginGraph = async () => {
 proof.started=performance.now();
 await fetch('/start',{method:'POST'});
 while(!disposed) {
  const response=await fetch('/next'); if(response.status===204) break;
  if(!response.ok) throw Error(await response.text());
  const p=await response.json(); const buffer=await (await fetch('/buffer')).arrayBuffer();
  const received=performance.now();
  view?.destroy(); element.replaceChildren();
  view=xy.renderStandalone(element,p.spec,buffer); window.graphView=view;
  await frame();
  // Read the REAL painter framebuffer after an actual frame, not a checkpoint.
  view._drawKeepPick();
  const gl=view.gl, pixels=new Uint8Array(gl.drawingBufferWidth*gl.drawingBufferHeight*4);
  gl.readPixels(0,0,gl.drawingBufferWidth,gl.drawingBufferHeight,gl.RGBA,gl.UNSIGNED_BYTE,pixels);
  let colored=0; for(let i=0;i<pixels.length;i+=4) if(pixels[i+2]>pixels[i]+10 || pixels[i]>pixels[i+1]+20) colored++;
  const record={phase:p.phase,step:p.step,revision:p.revision,jobId:p.jobId,receivedMs:received-proof.started,
   paintedMs:performance.now()-proof.started,coloredPixels:colored,bufferBytes:buffer.byteLength,frame:[gl.drawingBufferWidth,gl.drawingBufferHeight]};
  proof.checkpoints.push(record); proof.current=p;
  // Evidence harness supplies the ACK after inspecting initial and final frames.
  await new Promise(resolve=>window.acceptGraph=resolve);
  await fetch('/accept',{method:'POST',body:JSON.stringify({revision:p.revision,jobId:p.jobId,step:p.step})});
 }
 proof.done=true;
};
`;
const server = createServer(async (req, res) => {
  res.setHeader('Cache-Control', 'no-store');
  try {
    const url = new URL(req.url, 'http://localhost');
    if (url.pathname === '/') { res.setHeader('Content-Type', 'text/html'); res.end(`<!doctype html><meta charset="utf-8"><title>GraphForge live Node checkpoint consumer</title><style>body{font:16px system-ui;margin:24px}#chart{width:720px;height:480px}</style><h1>GraphForge live Node checkpoints</h1><div id="chart"></div><script src="/client.js"></script><script src="/app.js"></script>`); }
    else if (url.pathname === '/client.js') { res.setHeader('Content-Type', 'text/javascript'); res.end(await readFile(client)); }
    else if (url.pathname === '/app.js') { res.setHeader('Content-Type', 'text/javascript'); res.end(app); }
    else if (url.pathname === '/start' && req.method === 'POST') {
      if (started !== undefined) { res.writeHead(409).end(); return; }
      started = performance.now(); lastTick = started; lags.length = 0;
      const callStarted = performance.now();
      const run = graphforgeWebviewPayload(owner, input, { width: 720, height: 480, layout: 'cose', iterations: 60, chunkSteps: 1,
        legend: false, onPayload: payload => {
          current = payload; sourceNodes = payload.positions.uuid.length;
          event('checkpoint', { step: payload.step, phase: payload.phase, revision: payload.revision, jobId: payload.jobId, packingMs: payload.packingMs,
            positionSha256: createHash('sha256').update(Buffer.from(payload.positions.x.buffer)).update(Buffer.from(payload.positions.y.buffer)).digest('hex') });
          const accepted = new Promise(resolve => { accept = resolve; }); wake(); return accepted;
        } });
      event('call-returned', { synchronousMs: performance.now() - callStarted });
      run.then(() => { completed = true; event('complete'); wake(); }, cause => { failure = cause; event('error', { code: cause.code, message: cause.message }); wake(); });
      respond(res, { started: true });
    } else if (url.pathname === '/next') { if (waiting) { res.writeHead(409).end(); return; } waiting = res; wake(); }
    else if (url.pathname === '/buffer' && current) { res.setHeader('Content-Type', 'application/octet-stream'); res.end(Buffer.from(current.buffer)); }
    else if (url.pathname === '/accept' && req.method === 'POST') {
      let body = ''; for await (const chunk of req) body += chunk;
      const ack = JSON.parse(body);
      if (!current || ['step', 'revision', 'jobId'].some(key => ack[key] !== current[key])) { res.writeHead(409).end(); return; }
      event('accepted', { step: current.step }); current = undefined; accept(); respond(res, { accepted: true });
    } else if (url.pathname === '/pick' && current && req.method === 'POST') {
      let body = ''; for await (const chunk of req) body += chunk;
      const hit = JSON.parse(body);
      // Source UUIDs accompany checkpoints, never Aggregate render centroids.
      const uuid = hit.trace === current.nodeTrace ? current.positions.uuid[hit.index] : null;
      event('pick', { exact: typeof uuid === 'string', step: current.step }); respond(res, { uuid: uuid ?? null });
    } else if (url.pathname === '/evidence') respond(res, { events, maxCallerTickerLagMs: Math.max(0, ...lags), callerTickerSamples: lags.length,
      sourceNodes });
    else { res.writeHead(404).end(); }
  } catch (cause) { res.writeHead(500).end(String(cause)); }
});
server.listen(Number(process.env.PORT ?? 0), '127.0.0.1', () => console.log(`XYG_GRAPHFORGE_LIVE_URL=http://127.0.0.1:${server.address().port}`));
async function shutdown() { clearInterval(ticker); await owner.dispose(); server.closeAllConnections(); server.close(() => process.exit(0)); }
for (const signal of ['SIGTERM', 'SIGINT']) process.once(signal, shutdown);
