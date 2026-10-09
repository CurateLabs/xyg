#!/usr/bin/env node
// Actual packaged Worker + existing borrowed GL painter, offline strict CSP.
import {createServer} from 'node:http';
import {readFile,writeFile,mkdir} from 'node:fs/promises';
import {dirname,extname,join} from 'node:path';
import {fileURLToPath} from 'node:url';
import {createHash} from 'node:crypto';
import {gzipSync} from 'node:zlib';
import {spawnSync} from 'node:child_process';
import {chromium} from 'playwright';
import {nativeGeoScaleBridge} from '../packages/xy-node/src/geoscale.js';
import {nativeGeoTileBridge} from '../packages/xy-node/src/geo-tiles.js';
import {nativeGeoSnapshotBridge,encodeGeoSnapshotRequest,decodeGeoSnapshotReply} from '../packages/xy-node/src/geo-snapshot.js';
import {buildMixedFixture,MIXED_BUDGET} from '../tests/browser/geo_mixed_fixture.mjs';
const root=fileURLToPath(new URL('../',import.meta.url));
const native={source:nativeGeoScaleBridge(MIXED_BUDGET),tile:nativeGeoTileBridge(MIXED_BUDGET),snapshot:nativeGeoSnapshotBridge(384<<20)};
const nativeFixture=await buildMixedFixture(native),frozen=await nativeFixture.freeze();
const artifact=decodeGeoSnapshotReply(await native.snapshot.execute(encodeGeoSnapshotRequest(2,frozen.handle,{budget:384<<20,format:'html',scale:1,quality:90}))).handle;
let frozenHtml=await native.snapshot.read(encodeGeoSnapshotRequest(22,artifact));
const frozenPages=new Map([['/frozen.html',frozenHtml]]);
for(const [name,rasterColor] of [['black',[0,0,0,255]],['white',[255,255,255,255]]]){
 const fixture=await buildMixedFixture({...native,rasterColor}),snapshot=await fixture.freeze();
 const output=decodeGeoSnapshotReply(await native.snapshot.execute(encodeGeoSnapshotRequest(2,snapshot.handle,{budget:384<<20,format:'html',scale:1,quality:90}))).handle;
 try{frozenPages.set(`/frozen-${name}.html`,await native.snapshot.read(encodeGeoSnapshotRequest(22,output)));}
 finally{await native.snapshot.execute(encodeGeoSnapshotRequest(3,output));await snapshot.dispose();fixture.scene=fixture.descriptorBytes=undefined;await fixture.frame.dispose();}
}
const paths=new Set(['/tests/browser/geo_mixed_page.mjs','/tests/browser/geo_mixed_fixture.mjs','/packages/xy-node/src/geoscale.js','/packages/xy-node/src/geo-mixed-wire.js','/packages/xy-node/src/geo-snapshot.js','/packages/xy-client/dist/index.js','/packages/xy-client/dist/wasm-worker.js','/packages/xy-client/dist/xyg-wasm.wasm']);
const csp="default-src 'none'; script-src 'self' 'wasm-unsafe-eval'; worker-src 'self'; connect-src 'self'; style-src 'unsafe-inline'; object-src 'none'; base-uri 'none'",served=[],external=[],errors=[];
const server=createServer(async(req,res)=>{const path=new URL(req.url,'http://127.0.0.1').pathname;served.push(path);if(frozenPages.has(path)){res.setHeader('Content-Security-Policy',"default-src 'none'; img-src data:; style-src 'unsafe-inline'; object-src 'none'; base-uri 'none'");res.setHeader('Content-Type','text/html');res.end(Buffer.from(frozenPages.get(path)));return;}res.setHeader('Content-Security-Policy',csp);if(path==='/'){res.setHeader('Content-Type','text/html');res.end('<!doctype html><meta charset="utf-8"><script type="module" src="/tests/browser/geo_mixed_page.mjs"></script>');return;}if(!paths.has(path)){res.statusCode=404;res.end();return;}try{res.setHeader('Content-Type',extname(path)==='.wasm'?'application/wasm':'text/javascript');res.end(await readFile(join(root,path)));}catch{res.statusCode=404;res.end();}});
await new Promise(r=>server.listen(0,'127.0.0.1',r));const origin=`http://127.0.0.1:${server.address().port}`;
const executablePath=process.env.XYG_CHROMIUM??process.env.CHROMIUM,browser=await chromium.launch({...(executablePath?{executablePath}:{}),args:['--use-angle=swiftshader','--enable-unsafe-swiftshader','--ignore-gpu-blocklist']});
try{
 const page=await browser.newPage();
 await page.route('**/*',r=>{if(new URL(r.request().url()).origin!==origin){external.push(r.request().url());return r.abort();}return r.continue();});
 page.on('pageerror',e=>errors.push(e.message));page.on('console',m=>{if(m.type()==='error')errors.push(m.text());});
 await page.goto(origin);
 const contrastScreenshots=[];
 for(let i=0;i<2;i++){
  await page.waitForFunction(()=>window.__mixed!=null||window.__mixedContrast?.waiting,null,{timeout:60000});
  const state=await page.evaluate(()=>({mixed:window.__mixed,contrast:window.__mixedContrast}));
  if(state.mixed)throw Error(JSON.stringify(state.mixed));
  const png=await page.screenshot({clip:{x:state.contrast.bounds.x,y:state.contrast.bounds.y,width:64,height:64}});
  const decoded=spawnSync(join(root,'.venv/bin/python'),['-c',"import sys,json,math;from io import BytesIO;from PIL import Image;im=Image.open(BytesIO(sys.stdin.buffer.read())).convert('RGBA');b=json.loads(sys.argv[1]);p=[im.getpixel((x,y)) for y in range(math.ceil(b['y']),math.floor(b['y']+b['height'])) for x in range(math.ceil(b['x']),math.floor(b['x']+b['width']))];print(json.dumps(dict(dark=sum(max(v[:3])<64 and v[3]==255 for v in p),white=p.count((255,255,255,255)),background=im.getpixel((2,2)))))",JSON.stringify(state.contrast.box)],{input:png,encoding:'utf8'});
  if(decoded.status!==0)throw Error(decoded.stderr);const pixels=JSON.parse(decoded.stdout);
  if(!pixels.dark||!pixels.white||pixels.background.join(',')!==state.contrast.color.join(','))throw Error(JSON.stringify({state,pixels}));
  contrastScreenshots.push({color:state.contrast.color,box:state.contrast.box,...pixels});await page.evaluate(()=>{window.__mixedContrast.waiting=false;window.__mixedContrastAck();});
 }
 await page.waitForFunction(()=>window.__mixed!=null,null,{timeout:60000});
 const proof=await page.evaluate(()=>window.__mixed);if(!proof.ok||external.length||errors.length)throw Error(JSON.stringify({proof,external,errors}));
 proof.contrastScreenshots=contrastScreenshots;
 const replayProofs=[];
 for(const [path,color] of [['/frozen.html',[0,0,255,255]],['/frozen-black.html',[0,0,0,255]],['/frozen-white.html',[255,255,255,255]]]){
  const replay=await browser.newPage();await replay.route('**/*',r=>{const url=new URL(r.request().url());if(url.origin!==origin&&url.protocol!=='data:'){external.push(url.href);return r.abort();}return r.continue();});
  await replay.goto(origin+path);await replay.waitForFunction(()=>document.querySelector('img')?.complete&&document.querySelector('img')?.naturalWidth>0);
  const receipt=await replay.evaluate(()=>{const image=document.querySelector('img'),canvas=document.createElement('canvas');canvas.width=canvas.height=64;const ctx=canvas.getContext('2d');ctx.drawImage(image,0,0);const bytes=ctx.getImageData(41,51,20,12).data;let dark=0,white=0;for(let at=0;at<bytes.length;at+=4){if(Math.max(bytes[at],bytes[at+1],bytes[at+2])<64&&bytes[at+3]===255)dark++;if(bytes[at]===255&&bytes[at+1]===255&&bytes[at+2]===255&&bytes[at+3]===255)white++;}return {attribution:document.body.textContent.includes('Tiles'),red:[...ctx.getImageData(32,32,1,1).data],background:[...ctx.getImageData(2,2,1,1).data],dark,white,scripts:document.querySelectorAll('script').length};});
  if(!receipt.attribution||receipt.red.join(',')!=='255,0,0,255'||receipt.background.join(',')!==color.join(',')||!receipt.dark||!receipt.white||receipt.scripts)throw Error(JSON.stringify({path,receipt}));
  replayProofs.push({path,...receipt});await replay.close();
 }
 proof.frozenHtmlReplay=replayProofs;
 const bytes=await readFile(join(root,'packages/xy-client/dist/xyg-wasm.wasm')),report={proof,artifact:{rawBytes:bytes.length,gzipBytes:gzipSync(bytes).length,sha256:createHash('sha256').update(bytes).digest('hex')},network:{served,external,errors},scope:'Small actual mixed authority/native-WASM fixture; strict CSP with loopback file bytes and real borrowed WebGL2; black/white footer screenshot and native offline HTML pixel evidence; no provider request or massive interactive/performance claim.'};
 if(process.env.XYG_MIXED_BROWSER_REPORT){await mkdir(dirname(process.env.XYG_MIXED_BROWSER_REPORT),{recursive:true});await writeFile(process.env.XYG_MIXED_BROWSER_REPORT,JSON.stringify(report,null,2)+'\n');}
 console.log(JSON.stringify(report));
}
finally{await browser.close();server.close();frozenHtml=undefined;frozenPages.clear();await native.snapshot.execute(encodeGeoSnapshotRequest(3,artifact));await frozen.dispose();nativeFixture.scene=nativeFixture.descriptorBytes=undefined;await nativeFixture.frame.dispose();}
