#!/usr/bin/env node
// Node's host adapter shares the TypeScript wire implementation verbatim.
import {stripTypeScriptTypes} from 'node:module';
import {readFileSync,writeFileSync} from 'node:fs';
const source=readFileSync(new URL('../js/src/66_geo_mixed.ts',import.meta.url),'utf8');
const output='// Mechanical type stripping of js/src/66_geo_mixed.ts; no host policy.\n'+stripTypeScriptTypes(source);
const path=new URL('../packages/xy-node/src/geo-mixed-wire.js',import.meta.url);
if(process.argv.includes('--check')) {
 if(readFileSync(path,'utf8')!==output)throw Error('geo-mixed-wire.js is stale; run node scripts/gen_geo_mixed_wire.mjs');
}else writeFileSync(path,output);
