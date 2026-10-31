// Bind the actual local Node host to the rebuilt core, then record its provenance.
import assert from 'node:assert/strict';
import { readFileSync, writeFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import { createHash } from 'node:crypto';
import { nativeLibraryPath, ABI_VERSION } from '../../../packages/xy-node/src/native.js';
const require = createRequire(new URL('../../../packages/xy-node/package.json', import.meta.url));
require('koffi');
const sha = bytes => createHash('sha256').update(bytes).digest('hex');
const native = readFileSync(nativeLibraryPath);
const packagePath = new URL('../../../packages/xy-node/package.json', import.meta.url);
const koffiPath = require.resolve('koffi');
const loaded = Object.keys(require.cache).filter(name => name.endsWith('.node'));
assert.equal(nativeLibraryPath, process.env.XYG_NATIVE_LIB);
assert(loaded.some(name => name.endsWith('/linux_x64/koffi.node')));
const report = {
  node: process.version, executable: process.execPath,
  package: JSON.parse(readFileSync(packagePath)), packageSha256: sha(readFileSync(packagePath)),
  nativeLibraryPath, nativeAbi: ABI_VERSION, nativeSha256: sha(native), nativeBytes: native.length,
  koffiPath, koffiEntrySha256: sha(readFileSync(koffiPath)),
  loadedNativeModules: loaded.map(path => ({ path, sha256: sha(readFileSync(path)) })),
  scope: 'checkout-local Node module and rebuilt core; no registry install, publication or wheel acceptance',
};
writeFileSync(new URL('./node-module-provenance.json', import.meta.url), JSON.stringify(report, null, 2) + '\n');
console.log(JSON.stringify(report, null, 2));
