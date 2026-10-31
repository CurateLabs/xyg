// Functional diagnostics after a FAILED shipping gate. Never publishes product assets.
import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath,pathToFileURL} from 'node:url';
import {execFileSync} from 'node:child_process';
import {createHash} from 'node:crypto';
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'../../..');
const stage=path.join(root,'target/task-tmp/s4-diagnostic-assets');
let source=fs.readFileSync(path.join(root,'js/package-wasm.mjs'),'utf8');
source=source.replace('"./optimize-wasm.mjs"',JSON.stringify(pathToFileURL(path.join(root,'js/optimize-wasm.mjs')).href));
source=source.replace('const root = join(here, "..");',`const root = ${JSON.stringify(root)};\nconst diagnosticRoot=${JSON.stringify(stage)};`);
for (const relative of ['packages", "xy-client", "dist", "xyg-wasm.wasm','python", "xyg", "static", "xyg-wasm.wasm','packages", "xy-client", "dist", "xyg-wasm-inline.js','python", "xyg", "static", "xyg-wasm-inline.js','packages", "xy-client", "dist", "xyg-wasm.manifest.json','python", "xyg", "static", "xyg-wasm.manifest.json']) {
  const from=`join(root, "${relative}")`;
  if(!source.includes(from))throw new Error(`missing diagnostic output rewrite: ${from}`);
  source=source.replace(from,`join(diagnosticRoot, "${relative}")`);
}
// Keep the real thresholds and all signature/import/version/worker validation.
// Record both refusals while materializing ONLY the explicit diagnostic root.
for(const prefix of ['xyg-wasm gzip is','xyg-wasm is']) {
  const before=source;
  source=source.replace(new RegExp('throw new Error\\((`'+prefix+'[^`]*`)\\);'), 'console.warn("DIAGNOSTIC ONLY; SHIPPING GATE FAIL: " + $1);');
  if(source===before)throw new Error(`missing size gate ${prefix}`);
}
fs.mkdirSync(stage,{recursive:true});
const scratch=path.join(root,'target/task-tmp/s4-diagnostic-materializer.mjs');
fs.writeFileSync(scratch,source);
execFileSync(process.execPath,[scratch],{stdio:'inherit'});
for(const relative of ['packages/xy-client/dist','python/xyg/static']){
  for(const name of ['index.js','standalone.js','wasm-worker.js','wasm-inline-worker.js'])fs.copyFileSync(path.join(root,'packages/xy-client/dist',name),path.join(stage,relative,name));
}
fs.mkdirSync(path.join(stage,'spec/wasm'),{recursive:true});fs.copyFileSync(path.join(root,'spec/wasm/abi.json'),path.join(stage,'spec/wasm/abi.json'));
const assets={};for(const name of ['index.js','standalone.js','wasm-worker.js','xyg-wasm.wasm']){
  const bytes=fs.readFileSync(path.join(stage,'packages/xy-client/dist',name));assets[name]={bytes:bytes.length,sha256:createHash('sha256').update(bytes).digest('hex')};
}
fs.writeFileSync(path.join(stage,'packages/xy-client/ASSET-MANIFEST.json'),JSON.stringify({schemaVersion:1,package:'@curatelabs/xyg',assets},null,2)+'\n');
console.log(JSON.stringify({scope:'diagnostic only, failed shipping gates remain binding',artifactCommit:null,stage,assets},null,2));

fs.copyFileSync(path.join(root,'packages/xy-client/package.json'),path.join(stage,'packages/xy-client/package.json'));
// Copies of the unchanged Node test harness run against this diagnostic root.
const nodeHost=path.join(stage,'packages/xy-node');fs.mkdirSync(nodeHost,{recursive:true});
fs.copyFileSync(path.join(root,'packages/xy-node/package.json'),path.join(nodeHost,'package.json'));
fs.cpSync(path.join(root,'packages/xy-node/test'),path.join(nodeHost,'test'),{recursive:true});
const stagedSource=path.join(nodeHost,'src');
if(fs.existsSync(stagedSource) && fs.lstatSync(stagedSource).isSymbolicLink())fs.unlinkSync(stagedSource);
fs.cpSync(path.join(root,'packages/xy-node/src'),stagedSource,{recursive:true});
if(!fs.existsSync(path.join(nodeHost,'node_modules')))fs.symlinkSync(path.join(root,'packages/xy-node/node_modules'),path.join(nodeHost,'node_modules'),'dir');
fs.mkdirSync(path.join(stage,'tests'),{recursive:true});if(!fs.existsSync(path.join(stage,'tests/fixtures')))fs.symlinkSync(path.join(root,'tests/fixtures'),path.join(stage,'tests/fixtures'),'dir');
