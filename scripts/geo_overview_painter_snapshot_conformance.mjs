#!/usr/bin/env node
// Actual C ABI + packaged WASM + strict-CSP real WebGL2; small fixture only.
import assert from 'node:assert/strict';
import {readFile,writeFile,mkdir} from 'node:fs/promises';
import {createServer} from 'node:http';
import {dirname,extname,join} from 'node:path';
import {fileURLToPath} from 'node:url';
import {createHash} from 'node:crypto';
import {gzipSync} from 'node:zlib';
import {chromium} from 'playwright';
import {nativeGeoScaleBridge} from '../packages/xy-node/src/geoscale.js';
import {nativeGeoSnapshotBridge,decodeGeoSnapshotReply} from '../packages/xy-node/src/geo-snapshot.js';
import {sceneBrowserPainter} from '../packages/xy-node/src/scene.js';
import {buildOverviewPainterFixture,BUDGET,snapshotRequest,scaleRequest} from '../tests/browser/geo_overview_painter_fixture.mjs';
const root=fileURLToPath(new URL('../',import.meta.url)),artifact=await readFile(join(root,'packages/xy-client/dist/xyg-wasm.wasm'));
const {instance}=await WebAssembly.instantiate(artifact,{}),x=instance.exports,h=x.xyg_wasm_instance_new(BUDGET.processorBytes);assert.ok(h);let sequence=0;
const output=()=>new Uint8Array(x.memory.buffer,x.xyg_wasm_output_ptr(h)>>>0,x.xyg_wasm_output_len(h)).slice();
function call(family,read,r){assert.equal(x.xyg_wasm_arena_resize(h,r.byteLength),0);new Uint8Array(x.memory.buffer,x.xyg_wasm_arena_ptr(h)>>>0,r.byteLength).set(new Uint8Array(r));const code=x[`xyg_wasm_geo_${family}_${read?'read':'execute'}`](h,++sequence,0,r.byteLength);if(code)throw Error(`WASM ${code}: `+new TextDecoder().decode(new Uint8Array(x.memory.buffer,x.xyg_wasm_last_error_ptr(h)>>>0,x.xyg_wasm_last_error_len(h))));return output().buffer;}
const wasm={source:{execute:async r=>call('scale',false,r),read:async r=>call('scale',true,r)},snapshot:{execute:async r=>call('snapshot',false,r),read:async r=>call('snapshot',true,r)}};
const native={source:nativeGeoScaleBridge(BUDGET.processorBytes),snapshot:nativeGeoSnapshotBridge(384<<20)};
let a,b,af,bf,server,browser,frozen,v;const errors=[],external=[],served=[],formats={},legacyV2=[];
try{
 async function captureV2(bridge,owner){const receipt=decodeGeoSnapshotReply(await bridge.snapshot.execute(snapshotRequest(1,owner,{sequence:1n,budget:128<<20})));let bytes;try{bytes=await bridge.snapshot.read(snapshotRequest(20,receipt.handle));assert.equal(new DataView(bytes).getUint32(4,true),2);legacyV2.push({bytes:bytes.byteLength,sha256:createHash('sha256').update(new Uint8Array(bytes)).digest('hex')});}finally{bytes=undefined;await bridge.snapshot.execute(snapshotRequest(3,receipt.handle));}}
 a=await buildOverviewPainterFixture(native,{onPoint:owner=>captureV2(native,owner)});b=await buildOverviewPainterFixture(wasm,{onPoint:owner=>captureV2(wasm,owner)});assert.deepEqual(legacyV2[0],legacyV2[1]);
 assert.deepEqual(a.scene,b.scene);assert.equal(x.xyg_wasm_geo_frame_prepare(h,++sequence,b.handle,7n),0);
 let painter=output(),nativePainter=sceneBrowserPainter(a.scene,128<<20);assert.deepEqual(painter,nativePainter);
 assert.notEqual(x.xyg_wasm_geo_frame_prepare(h,++sequence,b.handle,6n),0);
 af=await a.freeze();bf=await b.freeze();assert.deepEqual(new Uint8Array(af.bytes),new Uint8Array(bf.bytes));frozen=new Uint8Array(af.bytes);v=new DataView(af.bytes);assert.equal(v.getUint32(4,true),4);assert.equal(v.getBigUint64(208,true),0xffffffffffffffffn);assert.equal(v.getBigInt64(56,true),0n);assert.equal(v.getUint32(288+8,true),3);assert.equal(v.getBigUint64(384+128*8,true),1n);assert.equal(v.getBigUint64(384+143*8,true),1n);
 await assert.rejects(native.snapshot.execute(snapshotRequest(6,a.handle,{sequence:7n,budget:4096})),/LIMIT/);await assert.rejects(wasm.snapshot.execute(snapshotRequest(6,b.handle,{sequence:7n,budget:4096})),/RESOURCE|LIMIT/);
 await assert.rejects(wasm.source.execute(scaleRequest(14,b.handle,7n,new Uint8Array(80))));
 // Native fixture lowering calls the existing C ABI Scene compiler; trusted
 // preparation is separately exercised below the WASM and Rust lifecycle seams.
 const parity={sceneBytes:a.scene.length,painterBytes:painter.length,painterSha256:createHash('sha256').update(painter).digest('hex'),frozenBytes:frozen.length,frozenSha256:createHash('sha256').update(frozen).digest('hex')};
 painter=nativePainter=undefined;
 a.scene=b.scene=undefined;await a.dispose();await b.dispose();a=b=undefined;
 let html;
 for(const format of ['svg','png','pdf','jpeg','webp','html']){
  const handle=decodeGeoSnapshotReply(await native.snapshot.execute(snapshotRequest(2,af.handle,{budget:384<<20,format,scale:1,quality:90}))).handle;
  try{const bytes=await native.snapshot.read(snapshotRequest(22,handle)),companion=await native.snapshot.read(snapshotRequest(21,handle));assert.equal(new DataView(companion).getUint32(4,true),4);assert.deepEqual(new Uint8Array(companion).subarray(208),frozen.subarray(208));formats[format]={bytes:bytes.byteLength,sha256:createHash('sha256').update(new Uint8Array(bytes)).digest('hex')};if(format==='html')html=Buffer.from(bytes);if(format==='svg')assert.ok(new TextDecoder().decode(bytes).includes('spatial refinement pending'));if(format==='png'){assert.equal(Buffer.from(bytes).subarray(0,8).toString('hex'),'89504e470d0a1a0a');assert.ok(Buffer.from(bytes).includes(Buffer.from('XYG frozen snapshot')));}}
  finally{await native.snapshot.execute(snapshotRequest(3,handle));}
 }
 await assert.rejects(wasm.snapshot.execute(snapshotRequest(2,bf.handle,{budget:128<<20,format:'png'})),/UNSUPPORTED/);
 const paths=new Set(['/tests/browser/geo_overview_painter_page.mjs','/tests/browser/geo_overview_painter_fixture.mjs','/packages/xy-node/src/geoscale.js','/packages/xy-node/src/geo-allocation-attempt.js','/packages/xy-node/src/geo-overview.js','/packages/xy-node/src/geo-overview-wire.js','/packages/xy-node/src/geo-snapshot.js','/packages/xy-client/dist/index.js','/packages/xy-client/dist/wasm-worker.js','/packages/xy-client/dist/xyg-wasm.wasm']);
 const csp="default-src 'none'; script-src 'self' 'wasm-unsafe-eval'; worker-src 'self'; connect-src 'self'; style-src 'unsafe-inline'; object-src 'none'; base-uri 'none'";
 server=createServer(async(req,res)=>{const path=new URL(req.url,'http://127.0.0.1').pathname;served.push(path);if(path==='/frozen.html'){res.setHeader('Content-Type','text/html');res.end(html);return;}res.setHeader('Content-Security-Policy',csp);if(path==='/'){res.setHeader('Content-Type','text/html');res.end('<!doctype html><script type="module" src="/tests/browser/geo_overview_painter_page.mjs"></script>');return;}if(!paths.has(path)){res.statusCode=404;res.end();return;}try{res.setHeader('Content-Type',extname(path)==='.wasm'?'application/wasm':'text/javascript');res.end(await readFile(join(root,path)));}catch{res.statusCode=404;res.end();}});await new Promise(r=>server.listen(0,'127.0.0.1',r));const origin=`http://127.0.0.1:${server.address().port}`;
 const executablePath=process.env.XYG_CHROMIUM??process.env.CHROMIUM;browser=await chromium.launch({...(executablePath?{executablePath}:{}),args:['--use-angle=swiftshader','--enable-unsafe-swiftshader','--ignore-gpu-blocklist']});const page=await browser.newPage({viewport:{width:1024,height:768}});page.on('pageerror',e=>errors.push(e.message));await page.route('**/*',r=>{const u=new URL(r.request().url());if(u.origin!==origin&&u.protocol!=='data:'){external.push(u.href);return r.abort();}return r.continue();});await page.goto(origin);await page.waitForFunction(()=>window.__overviewPainter!=null,null,{timeout:60000});const paint=await page.evaluate(()=>window.__overviewPainter);assert.ok(paint.ok,JSON.stringify(paint));
 await page.goto(origin+'/frozen.html');await page.waitForFunction(()=>document.querySelector('img')?.complete&&document.querySelector('img')?.naturalWidth===800);const replay=await page.evaluate(()=>{const c=document.createElement('canvas');c.width=800;c.height=600;const ctx=c.getContext('2d');ctx.fillStyle='white';ctx.fillRect(0,0,800,600);ctx.drawImage(document.querySelector('img'),0,0);const p=(x,y)=>[...ctx.getImageData(x,y,1,1).data];return {left:p(160,284),right:p(640,284),empty:p(400,284),scripts:document.querySelectorAll('script').length,template:document.querySelector('#xyg-frozen-snapshot').content.textContent.length};});assert.deepEqual(replay.left,[56,156,255,255]);assert.deepEqual(replay.right,[56,156,255,255]);assert.deepEqual(replay.empty,[255,255,255,255]);assert.equal(replay.scripts,0);assert.ok(replay.template>0);assert.deepEqual(errors,[]);assert.deepEqual(external,[]);
 const report={artifact:{rawBytes:artifact.length,gzipLevel6Bytes:gzipSync(artifact).length,sha256:createHash('sha256').update(artifact).digest('hex')},nativeWasm:parity,legacyV2,formats,paint,replay,network:{served,external,errors},scope:'Small actual native Scene compiler / WASM trusted painter parity, private overview Data retain/source+index disposal, exact time-domain counts and flags3, six native formats+WASM binary v4 parity, real WebGL2/offline strict-CSP cells. No source-feature picking, membership, public overview composition, final camera-space refinement or massive latency claim.'};
 if(process.env.XYG_OVERVIEW_PAINT_REPORT){await mkdir(dirname(process.env.XYG_OVERVIEW_PAINT_REPORT),{recursive:true});await writeFile(process.env.XYG_OVERVIEW_PAINT_REPORT,JSON.stringify(report,null,2)+'\n');}console.log(JSON.stringify(report));
}finally{frozen=v=undefined;if(browser)await browser.close();if(server)server.close();if(af){af.bytes=undefined;await af.dispose();}if(bf){bf.bytes=undefined;await bf.dispose();}if(a){a.scene=undefined;await a.dispose();}if(b){b.scene=undefined;await b.dispose();}assert.equal(x.xyg_wasm_instance_dispose(h),0);}
