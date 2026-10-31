import fs from 'node:fs';
import crypto from 'node:crypto';
import zlib from 'node:zlib';
const receipt = 'spec/performance/graph-s3-aggregate-style-repair-2026-10-31/';
const old = JSON.parse(fs.readFileSync('spec/performance/graph-s3-package-budget-2026-10-31/artifact.json'));
const hash = b => crypto.createHash('sha256').update(b).digest('hex');
const bytes = fs.readFileSync('packages/xy-client/dist/xyg-wasm.wasm');
const gzip = zlib.gzipSync(bytes);
const mod = await WebAssembly.compile(bytes);
const files = Object.fromEntries(Object.keys(old.files).map(path => {
  const b = fs.readFileSync(path);
  return [path, {bytes:b.length,sha256:hash(b)}];
}));
const result = {node:process.version,rawBytes:bytes.length,gzip6Bytes:gzip.length,sha256:hash(bytes),gzip6Sha256:hash(gzip),rawGate:1513*1024,gzipGate:626*1024,rawHeadroom:1513*1024-bytes.length,gzipHeadroom:626*1024-gzip.length,imports:WebAssembly.Module.imports(mod),exports:WebAssembly.Module.exports(mod),files,artifactCommit:null,reusedFoundationReceipt:'graph-s3-package-budget-2026-10-31',samePackagedFiles:Object.entries(files).every(([p,v])=>JSON.stringify(v)===JSON.stringify(old.files[p]))};
console.log(JSON.stringify(result));
if (!result.samePackagedFiles || result.rawHeadroom<0 || result.gzipHeadroom<0 || result.imports.length) process.exit(1);
