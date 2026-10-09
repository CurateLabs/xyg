#!/usr/bin/env node
// Actual packaged retained-source Worker/controller proof, offline strict CSP.
import { createServer } from 'node:http';
import { readFile,writeFile,mkdir } from 'node:fs/promises';
import { extname, join,dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { stripTypeScriptTypes } from 'node:module';
import {createHash} from 'node:crypto';
import {gzipSync} from 'node:zlib';
import {cpus,totalmem,platform,arch} from 'node:os';
import { chromium } from 'playwright';

const root = fileURLToPath(new URL('../', import.meta.url));
const assets = new Set(['/tests/browser/geo_retained_page.mjs',
  '/tests/browser/geo_source_parser.mjs',
  '/packages/xy-client/dist/index.js', '/packages/xy-client/dist/wasm-worker.js',
  '/packages/xy-client/dist/xyg-wasm.wasm']);
const csp = "default-src 'none'; script-src 'self' 'wasm-unsafe-eval'; worker-src 'self'; connect-src 'self'; style-src 'unsafe-inline'; object-src 'none'; base-uri 'none'";
const served = [], violations = [], diagnostics = [], outside = [];
const types = {'.js':'text/javascript', '.mjs':'text/javascript', '.wasm':'application/wasm'};
const server = createServer(async(request,response)=>{
  const path = new URL(request.url,'http://127.0.0.1').pathname;
  served.push(path);response.setHeader('Content-Security-Policy',csp);
  if(path==='/'){response.setHeader('Content-Type','text/html');response.end('<!doctype html><meta charset="utf-8"><script type="module" src="/tests/browser/geo_retained_page.mjs"></script>');return;}
  if(!assets.has(path)){response.statusCode=404;response.end();return;}
  // Test-only parser access avoids widening the public product export surface.
  if(path==='/tests/browser/geo_source_parser.mjs'){
    response.setHeader('Content-Type','text/javascript');
    response.end(stripTypeScriptTypes(await readFile(join(root,'js/src/63_geo_source.ts'),'utf8')));return;
  }
  try{response.setHeader('Content-Type',types[extname(path)]);response.end(await readFile(join(root,path)));}
  catch{response.statusCode=404;response.end();}
});
await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
const origin=`http://127.0.0.1:${server.address().port}`;
const executablePath=process.env.XYG_CHROMIUM??process.env.CHROMIUM;
const browser=await chromium.launch({...(executablePath?{executablePath}:{}),args:['--use-gl=swiftshader','--enable-unsafe-swiftshader','--ignore-gpu-blocklist']});
try{
  const page=await browser.newPage();
  await page.route('**/*',route=>{const url=new URL(route.request().url());if(url.origin!==origin){outside.push(url.href);return route.abort();}return route.continue();});
  page.on('console',message=>{diagnostics.push(message.text());if(/Content Security Policy|Refused to/.test(message.text()))violations.push(message.text());});
  page.on('pageerror',error=>diagnostics.push(error.message));
  await page.goto(origin);
  try{await page.waitForFunction(()=>window.__retained!=null,null,{timeout:60_000});}
  catch(error){throw Error(JSON.stringify({stage:await page.evaluate(()=>window.__retainedStage),error:error.message,diagnostics}));}
  const result=await page.evaluate(()=>window.__retained);
  if(!result.ok)throw Error(JSON.stringify({result,diagnostics}));
  if(!result.concurrentOwnership||result.sharedViews!==5||result.directPages!==3||!result.fullU64||!result.fullI64||!result.cancelledReadAck||!result.oldFramePreserved||!result.contextRestored||!result.memberCursor||!result.failedInitializationCleaned||!result.frozenSnapshot||result.wasmRasterExport!=='unsupported'||result.pending!==0||result.parserNegativeControls<30)throw Error(`incomplete retained contract: ${JSON.stringify(result)}`);
  if(violations.length||outside.length||served.some(path=>path!=='/'&&!assets.has(path)))throw Error(JSON.stringify({violations,outside,served}));
  const wasm=await readFile(join(root,'packages/xy-client/dist/xyg-wasm.wasm'));
  const evidence={recordedAt:new Date().toISOString(),artifact:{rawBytes:wasm.length,gzipBytes:gzipSync(wasm,{level:9}).length,gzipLevel:9,releaseGateGzipBytes:gzipSync(wasm,{level:6}).length,releaseGateGzipLevel:6,sha256:createHash('sha256').update(wasm).digest('hex')},environment:{node:process.version,browser:browser.version(),platform:platform(),architecture:arch(),cpu:cpus()[0]?.model,logicalCpus:cpus().length,physicalMemoryBytes:totalmem(),executablePath:executablePath??'Playwright default',load:'Concurrent development load was not controlled; no comparative latency claim'},startupScope:'Worker constructor to ready in a fresh browser process/profile; raw loopback HTTP without compression, warm OS file cache, excludes main ESM bundle parse; not WAN latency',proof:result,network:{served,external:outside,cspViolations:violations}};
  if(process.env.XYG_GEO_RETAINED_REPORT){await mkdir(dirname(process.env.XYG_GEO_RETAINED_REPORT),{recursive:true});await writeFile(process.env.XYG_GEO_RETAINED_REPORT,JSON.stringify(evidence,null,2)+'\n');}
  console.log(`retained geographic WASM smoke: ABI${result.abiVersion}, actual chunk/manifest/auth/query/Scene, concurrent ownership+5shared painted views, exactu64/i64, immutable-frame pick, paged membership, frozenXYGX+rasterUnsupported, unsettled-read cancellation/ACK, error recovery, realGL/contextrestore, boundedDOM and cleanup; ${result.parserNegativeControls} malformed controls; startup${result.startupMs.toFixed(3)}ms; offline strict CSP`);
}finally{await browser.close();server.close();}
