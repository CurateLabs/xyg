// Exercise the real browser encoder export without expanding the public surface.
import assert from 'node:assert/strict';
import {build} from 'vite';
import {fileURLToPath} from 'node:url';
import {encodeContainer,DTYPE} from '../../packages/xy-node/src/graphforge-container.js';
const result=await build({configFile:false,logLevel:'error',build:{write:false,minify:false,lib:{entry:fileURLToPath(new URL('../../js/src/49_wasm_graphforge.ts',import.meta.url)),formats:['es']}}});
const chunks=(Array.isArray(result)?result:[result]).flatMap(r=>r.output).filter(x=>x.type==='chunk');
assert.equal(chunks.length,1);
const browser=await import(`data:text/javascript;base64,${Buffer.from(chunks[0].code).toString('base64')}`);
const sections=[{name:'header.u32',dtype:DTYPE.u32,values:[0,1,0xffffffff]},{name:'header.u64',dtype:DTYPE.u64,values:[7n,9n,3n]}];
assert.deepEqual(browser.encodeGraphForgeContainer('XYGI',sections),encodeContainer('XYGI',sections));
console.log('browser DT.u32 encoder: real TypeScript module bytes equal Node codec, including u32::MAX');
