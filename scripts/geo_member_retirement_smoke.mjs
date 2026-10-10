#!/usr/bin/env node
// Test-only genuine Worker provenance under strict CSP; no public testing exports.
import {createServer} from 'node:http';
import {readFile,writeFile,mkdir} from 'node:fs/promises';
import {join,dirname} from 'node:path';
import {fileURLToPath} from 'node:url';
import {createHash} from 'node:crypto';
import {gzipSync} from 'node:zlib';
import {chromium} from 'playwright';
import {build} from 'vite';
const root=fileURLToPath(new URL('../',import.meta.url));
const output=await build({configFile:false,logLevel:'error',build:{write:false,minify:true,rollupOptions:{preserveEntrySignatures:'strict',input:join(root,'tests/browser/geo_member_retirement_entry.mjs'),output:{format:'es'}}}});
const bundle=output.output.find(x=>x.type==='chunk').code;
const csp="default-src 'none'; script-src 'self' 'wasm-unsafe-eval'; worker-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'none'";
const served=[],errors=[],external=[],violations=[];
const server=createServer(async(req,res)=>{const path=new URL(req.url,'http://localhost').pathname;served.push(path);res.setHeader('Content-Security-Policy',csp);if(path==='/'){res.setHeader('Content-Type','text/html');res.end('<!doctype html><script type="module" src="/page.js"></script>');return;}if(path==='/page.js'){res.setHeader('Content-Type','text/javascript');res.end("import {verifyMemberRetirement} from '/proof.js';verifyMemberRetirement().then(proof=>window.result={ok:true,proof},error=>window.result={ok:false,error:String(error),stack:error.stack});");return;}if(path==='/proof.js'){res.setHeader('Content-Type','text/javascript');res.end(bundle);return;}if(!['/packages/xy-client/dist/xyg-wasm.wasm','/packages/xy-client/dist/wasm-worker.js'].includes(path)){res.statusCode=404;res.end();return;}res.setHeader('Content-Type',path.endsWith('.wasm')?'application/wasm':'text/javascript');res.end(await readFile(join(root,path)));});
await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
const origin=`http://127.0.0.1:${server.address().port}`,executablePath=process.env.XYG_CHROMIUM??process.env.CHROMIUM;
const browser=await chromium.launch({...(executablePath?{executablePath}:{}),args:['--use-angle=swiftshader','--enable-unsafe-swiftshader']});
try{const page=await browser.newPage();page.on('pageerror',e=>errors.push(e.message));page.on('console',m=>{if(/Content Security Policy|Refused to/.test(m.text()))violations.push(m.text());});await page.route('**/*',route=>{if(new URL(route.request().url()).origin!==origin){external.push(route.request().url());return route.abort();}return route.continue();});await page.goto(origin);await page.waitForFunction(()=>window.result!=null,null,{timeout:120000});const result=await page.evaluate(()=>window.result);const wasm=await readFile(join(root,'packages/xy-client/dist/xyg-wasm.wasm'));const report={recordedAt:new Date().toISOString(),environment:{node:process.version,browser:browser.version(),executablePath},artifact:{sha256:createHash('sha256').update(wasm).digest('hex'),rawBytes:wasm.length,gzip6Bytes:gzipSync(wasm,{level:6}).length},result,network:{served,errors,external,violations},scope:'Known MemberData10 unresolved cleanup with purpose-specific operation6 proof; no generic SourceStale classifier or massive-performance claim.'};console.log(JSON.stringify(report,null,2));if(process.env.XYG_MEMBER_RETIREMENT_REPORT){await mkdir(dirname(process.env.XYG_MEMBER_RETIREMENT_REPORT),{recursive:true});await writeFile(process.env.XYG_MEMBER_RETIREMENT_REPORT,JSON.stringify(report,null,2)+'\n');}if(!result.ok||errors.length||external.length||violations.length)throw Error('MemberData retirement proof failed');}finally{await browser.close();server.close();}
