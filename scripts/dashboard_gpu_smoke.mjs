// Real hosted dashboard pressure journey; no worker mocks or timing assertions.
import { createServer } from 'node:http';
import { readFile, writeFile, mkdir } from 'node:fs/promises';
import { spawnSync } from 'node:child_process';
import { createHash } from 'node:crypto';
import { resolve } from 'node:path';
import { chromium } from 'playwright';
const output = resolve(process.env.XYG_GPU_REPORT_DIR || 'target/task-tmp/gpu-admission');
await mkdir(output, { recursive: true });
const fixture = spawnSync('uv', ['run', 'python', '-c', `import sys; sys.path.insert(0,'tests'); from test_shared_glhost import _chart_html; print(_chart_html('globalThis.gpuFixture={spec,buf};'))`], { encoding: 'utf8' });
if (fixture.status) throw new Error(fixture.stderr);
const server = createServer(async (req, res) => {
  try {
    if (req.url === '/') { res.setHeader('Content-Type','text/html'); res.end(fixture.stdout.replace("script-src 'unsafe-inline'", "script-src 'self' 'unsafe-inline'").replace("connect-src 'none'", "connect-src 'self'").replace("worker-src blob:", "worker-src 'self' blob:")); return; }
    const name = req.url.slice(1);
    if (!['index.js','wasm-worker.js','xyg-wasm.wasm'].includes(name)) { res.writeHead(404).end(); return; }
    res.setHeader('Content-Type', name.endsWith('wasm') ? 'application/wasm' : 'text/javascript');
    res.end(await readFile(`packages/xy-client/dist/${name}`));
  } catch (e) { res.writeHead(500).end(String(e)); }
});
await new Promise(r => server.listen(0,'127.0.0.1',r));
const browser = await chromium.launch({ executablePath: process.env.XYG_CHROMIUM, headless: true, args:['--no-sandbox','--use-gl=angle','--use-angle=swiftshader','--enable-unsafe-swiftshader'] });
const page = await browser.newPage({viewport:{width:1400,height:1000}});
await page.exposeFunction('gpuCapture', async label => page.screenshot({path:`${output}/${label}.png`,fullPage:true}));
const logs=[]; page.on('console',m=>logs.push(m.type()+': '+m.text())); page.on('pageerror',e=>logs.push('pageerror: '+e.stack));
try {
  await page.goto(`http://127.0.0.1:${server.address().port}/`);
  await page.waitForFunction(()=>globalThis.gpuFixture);
  let deadline;
  let result;
  try {
    result = await Promise.race([
      page.evaluate(await readFile('tests/browser/dashboard_gpu_page.mjs','utf8')),
      new Promise((_, reject) => {
        deadline = setTimeout(() => reject(new Error('dashboard GPU journey timed out')), 90000);
      }),
    ]);
  } finally {
    clearTimeout(deadline);
  }
  await page.screenshot({path:`${output}/dashboard.png`,fullPage:true});
  const hashes={};
  for (const path of ['packages/xy-client/dist/index.js','packages/xy-client/dist/xyg-wasm.wasm',`${output}/pressure.png`,`${output}/restored.png`]) hashes[path]=createHash('sha256').update(await readFile(path)).digest('hex');
  await writeFile(`${output}/report.json`,JSON.stringify({result,hashes,node:process.version,browser:browser.version(),platform:process.platform},null,2)+'\n');
  console.log(JSON.stringify(result));
} finally { await writeFile(`${output}/browser.log`,logs.join('\n')); await browser.close(); await new Promise(r=>server.close(r)); }
