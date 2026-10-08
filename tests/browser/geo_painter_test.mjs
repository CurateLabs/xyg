#!/usr/bin/env node
// Rust fixture: XYG_M6_PAINTER_FIXTURE=/tmp/xyg-m6-painter.bin cargo test -p xyg-engine triangle_batch_and_image
// XYG_PAINTER_FIXTURE=/tmp/xyg-m6-painter.bin XYG_CHROMIUM=/path/to/chromium node tests/browser/geo_painter_test.mjs
import {createServer} from 'node:http';
import {readFile,mkdtemp,rm} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {fileURLToPath} from 'node:url';
import {build} from 'vite';
import {chromium} from 'playwright';
const root=fileURLToPath(new URL('../../',import.meta.url));
const maplibre=process.env.XYG_MAPLIBRE_DIST;if(!maplibre)throw Error('Supply local MapLibre6.13.0 fixture');
const version=JSON.parse(await readFile(join(maplibre,'../package.json'),'utf8')).version;if(version!=='6.13.0')throw Error('Expected MapLibre6.13.0');
const fixture=process.env.XYG_PAINTER_FIXTURE;if(!fixture)throw Error('Supply Rust-derived XYG_PAINTER_FIXTURE');
const output=await mkdtemp(join(tmpdir(),'xyg-geo-painter-'));
await build({configFile:false,logLevel:'error',build:{outDir:output,lib:{entry:join(root,'tests/browser/geo_painter_entry.ts'),formats:['es'],fileName:()=> 'probe.js'},minify:false}});
const files=new Map([['/probe.js',join(output,'probe.js')],['/page.mjs',join(root,'tests/browser/geo_painter_page.mjs')],['/painter.bin',fixture],['/decor.bin',`${fixture}.decor`],['/maplibre-gl.mjs',join(maplibre,'maplibre-gl.mjs')],['/maplibre-gl-shared.mjs',join(maplibre,'maplibre-gl-shared.mjs')],['/maplibre-gl-worker.mjs',join(maplibre,'maplibre-gl-worker.mjs')]]),violations=[],unexpected=[];
const server=createServer(async(req,res)=>{const path=new URL(req.url,'http://localhost').pathname;res.setHeader('Content-Security-Policy',"default-src 'none'; script-src 'self'; connect-src 'self'; worker-src 'self'; style-src 'unsafe-inline'; img-src 'self' data:; object-src 'none'; base-uri 'none'");
  if(path==='/'){res.setHeader('Content-Type','text/html');res.end('<!doctype html><meta charset="utf-8"><link rel="icon" href="data:,"><script type="module" src="/page.mjs"></script>');return;}
  if(!files.has(path)){unexpected.push(path);res.writeHead(404).end();return;}
  try{res.setHeader('Content-Type',(path.endsWith('.bin')||path.endsWith('.decor'))?'application/octet-stream':'text/javascript');res.end(await readFile(files.get(path)));}catch(error){res.writeHead(500).end(error.message);}});
await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));let browser;
try{const executablePath=process.env.XYG_CHROMIUM??process.env.CHROMIUM;browser=await chromium.launch({...executablePath?{executablePath}:{},args:['--use-gl=swiftshader','--enable-unsafe-swiftshader','--ignore-gpu-blocklist']});const page=await browser.newPage();page.on('pageerror',error=>violations.push(error.message));page.on('console',m=>{if(/Content Security Policy|Refused to/.test(m.text()))violations.push(m.text());});await page.goto(`http://127.0.0.1:${server.address().port}/`);await page.waitForFunction(()=>window.__geoPainter!=null,null,{timeout:30000});const result=await page.evaluate(()=>window.__geoPainter);if(!result.ok||violations.length||unexpected.length)throw Error(JSON.stringify({result,violations,unexpected}));console.log(`geo painter smoke: ${JSON.stringify(result)}`);}finally{await browser?.close();server.close();await rm(output,{recursive:true,force:true});}
