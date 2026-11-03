// Diagnosis only. Observe unchanged product paint and independently display its
// actual canonical SVG. No CSS/DOM intervention, screenshot masks or gate edits.
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import fs from 'node:fs';
import { createServer } from 'node:http';
import path from 'node:path';
import { pathToFileURL } from 'node:url';
import { chromium } from 'playwright';

const root = process.cwd();
const output = path.resolve(process.argv[2]);
assert.ok(process.argv[2], 'supply a fresh diagnostic output directory');
const input = path.resolve(process.argv[3]);
fs.mkdirSync(output, { recursive:true });
const { decodeGraphForgeDocument } = await import(pathToFileURL(path.join(root, 'packages/xy-node/src/graphforge.js')));
const { sceneStaticExport } = await import(pathToFileURL(path.join(root, 'packages/xy-node/src/scene.js')));
const fixture = JSON.parse(fs.readFileSync(path.join(root, 'tests/fixtures/graphforge/property_default_export.json')));
const bases = path.join(root, 'tests/fixtures/graphforge/results');
const base = JSON.parse(fs.readFileSync(path.join(bases, 'manifest.json'))).bases.property;
const sha = (bytes) => createHash('sha256').update(bytes).digest('hex');
const files = new Map();
for (const side of ['nodes','edges']) files.set(`/${side}.arrow`, { bytes:fs.readFileSync(path.join(bases, `${base[side]}.arrow`)), type:'application/octet-stream' });
for (const name of ['index.js','wasm-worker.js','xyg-wasm.wasm']) files.set(`/${name}`, { bytes:fs.readFileSync(path.join(root, 'packages/xy-client/dist', name)), type:name.endsWith('wasm')?'application/wasm':'text/javascript' });
files.set('/', { bytes:Buffer.from('<!doctype html><style>body{margin:0}</style><div id="chart"></div>'), type:'text/html' });
const server = createServer((req,res) => {
  const file = files.get(new URL(req.url,'http://localhost').pathname);
  if (!file) { res.writeHead(404); res.end(); return; }
  res.setHeader('Content-Type',file.type); res.end(file.bytes);
});
await new Promise(resolve => server.listen(0,'127.0.0.1',resolve));
const origin = `http://127.0.0.1:${server.address().port}`;
const browser = await chromium.launch({ executablePath:process.env.XYG_CHROMIUM, args:['--use-angle=swiftshader','--enable-unsafe-swiftshader','--no-sandbox','--hide-scrollbars'] });
const results = { purpose:'DIAGNOSTIC ONLY: no acceptance waiver or production fix', browser:browser.version(), interventions:[], assets:Object.fromEntries([...files].filter(([name])=>name!=='/').map(([name,file])=>[name,{ bytes:file.bytes.length,sha256:sha(file.bytes) }])), captures:{} };
try {
  for (const theme of fixture.themes) {
    const document = fs.readFileSync(path.join(input,`${theme}.xygf`));
    const scene = decodeGraphForgeDocument(Uint8Array.from(document)).scene.bytes;
    const svg = sceneStaticExport(scene,'svg',{ width:fixture.width,height:fixture.height,theme,scale:1 });
    assert.deepEqual(Buffer.from(svg),fs.readFileSync(path.join(input,`${theme}.svg`)));
    // Separate, unmodified canonical SVG control, never substituted for WASM.
    files.set('/canonical.svg', { bytes:Buffer.from(svg),type:'image/svg+xml' });
    for (const dpr of [1,2]) {
      const key = `${theme}.dpr${dpr}`;
      fs.writeFileSync(path.join(output,`${key}.canonical.png`),sceneStaticExport(scene,'png',{ width:fixture.width*dpr,height:fixture.height*dpr,theme,scale:dpr }));
      const page = await browser.newPage({ viewport:{width:fixture.width,height:fixture.height}, deviceScaleFactor:dpr });
      const errors = [];page.on('pageerror',e=>errors.push(String(e)));
      await page.goto(origin);
      const observation = await page.evaluate(async ({width,height,theme,generation}) => {
        const client = await import('/index.js');
        const worker = client.createXygWasmWorker({ workerUrl:'/wasm-worker.js',wasm:'/xyg-wasm.wasm' });
        await worker.ready;
        const tables = await Promise.all(['nodes','edges'].map(async side=>new Uint8Array(await (await fetch(`/${side}.arrow`)).arrayBuffer())));
        const el = document.getElementById('chart');
        Object.assign(el.style,{width:`${width}px`,height:`${height}px`,position:'relative'});
        const { view,composition } = await client.renderWasmGraphForge({el,worker,width,height,theme,input:{base:{tables,generation}}});
        await new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)));
        view._layout();view._drawNow();view._raf=null;
        const box = node=>{const r=node.getBoundingClientRect(),c=el.getBoundingClientRect();return {x:r.x-c.x,y:r.y-c.y,width:r.width,height:r.height};};
        const computed = node=>{const s=getComputedStyle(node);return Object.fromEntries(['position','left','top','right','bottom','width','height','boxSizing','backgroundColor','opacity','padding','borderTopWidth','borderRightWidth','borderBottomWidth','borderLeftWidth','borderTopStyle','borderTopColor','borderRadius','transform','transformOrigin','translate','scale','zoom'].map(k=>[k,s[k]]));};
        const node = n=>({box:box(n),computed:computed(n),attributes:Object.fromEntries([...n.attributes].map(a=>[a.name,a.value]))});
        return {
          devicePixelRatio:devicePixelRatio,viewDpr:view.dpr,plot:view.plot,size:view.size,
          viewport:{width:innerWidth,height:innerHeight,visualScale:visualViewport?.scale},
          root:node(view.root),labels:node(view.labels),
          axes:[...el.querySelectorAll('[data-xy-slot="axis_line"]')].map(node),
          ticks:[...el.querySelectorAll('[data-xy-slot="tick_mark"]')].map(node),
          axisSpec:{x:view.spec.axes.x,y:view.spec.axes.y},frameSides:view.spec.frame_sides,
          canvases:[view.canvas,view.chrome,view.overlay].map(n=>({...node(n),backingWidth:n.width,backingHeight:n.height,ratioX:n.width/n.getBoundingClientRect().width,ratioY:n.height/n.getBoundingClientRect().height})),
          document:Array.from(composition.bytes),
        };
      }, {width:fixture.width,height:fixture.height,theme,generation:base.generation});
      assert.deepEqual(Buffer.from(observation.document),document,'fresh Worker/native canonical XYGF');delete observation.document;
      await page.locator('#chart').screenshot({path:path.join(output,`${key}.wasm.png`)});
      await page.goto(`${origin}/canonical.svg`);
      const svgObservation = await page.evaluate(()=>({devicePixelRatio:devicePixelRatio,svg:{width:document.documentElement.width.baseVal.value,height:document.documentElement.height.baseVal.value},axes:[...document.querySelectorAll('[data-xy-chrome="axes"] line')].map(n=>({attributes:Object.fromEntries([...n.attributes].map(a=>[a.name,a.value])),box:(()=>{const r=n.getBoundingClientRect();return {x:r.x,y:r.y,width:r.width,height:r.height};})(),computed:{stroke:getComputedStyle(n).stroke,strokeWidth:getComputedStyle(n).strokeWidth,strokeLinecap:getComputedStyle(n).strokeLinecap,transform:getComputedStyle(n).transform}}))}));
      await page.screenshot({path:path.join(output,`${key}.canonical-svg-browser.png`)});
      results.captures[key]={wasm:observation,canonicalSvgBrowser:svgObservation,errors};
      assert.deepEqual(errors,[]);await page.close();
    }
  }
} finally { await browser.close();server.close(); }
results.outputs=Object.fromEntries(fs.readdirSync(output).filter(n=>n.endsWith('.png')).map(n=>[n,sha(fs.readFileSync(path.join(output,n)))]));
fs.writeFileSync(path.join(output,'dom.json'),JSON.stringify(results,null,2)+'\n');
console.log('Diagnostic DOM/PNG captures complete at DPR 1 and 2; no product intervention or acceptance classification.');
