// Mechanical shared TypeScript framing: no independent Node numeric policy.
import fs from 'node:fs';
import {stripTypeScriptTypes} from 'node:module';
import {execFileSync} from 'node:child_process';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
const check=process.argv.includes('--check');
const trim=s=>s.split('\n').map(line=>line.trimEnd()).join('\n');
function write(path,text){if(check){if(fs.readFileSync(path,'utf8')!==text)throw new Error(`${path} is stale`);}else fs.writeFileSync(path,text);}
const path='packages/xy-node/src/geoscale.js',old=fs.readFileSync(path,'utf8'),marker='// Load generated native bindings only when requested; framing stays host-neutral.',at=old.indexOf(marker);
if(at<0)throw new Error('missing native suffix boundary');
write(path,trim(stripTypeScriptTypes(fs.readFileSync('js/src/63_geo_source.ts','utf8')))+'\n'+old.slice(at));
write('packages/xy-node/src/geo-selected.js',trim(stripTypeScriptTypes(fs.readFileSync('js/src/68_geo_selected.ts','utf8')).replaceAll("'./63_geo_source'","'./geoscale.js'").replaceAll("import {withGeoWorkerMutationOutcome} from './47_wasm';","import {withGeoNativeMutationOutcome as withGeoWorkerMutationOutcome} from './geoscale.js';").replaceAll("'./72_geo_allocation_attempt'","'./geo-allocation-attempt.js'")));
write('packages/xy-node/src/geo-allocation-attempt.js','// Mechanical type stripping of shared private allocation recovery.\n'+trim(stripTypeScriptTypes(fs.readFileSync('js/src/72_geo_allocation_attempt.ts','utf8'))).replaceAll("'./63_geo_source'","'./geoscale.js'"));
const directory=fs.mkdtempSync(join(tmpdir(),'xyg-selected-types-'));
try{
 // Declaration-only nullability matches the canonical host generator;
 // node js/build.mjs independently typechecks the configured product source.
 execFileSync(process.execPath,['node_modules/typescript/bin/tsc','--project','js/tsconfig.json','--rootDir','js/src','--strictNullChecks','true','--noCheck','--declaration','--emitDeclarationOnly','--noEmit','false','--outDir',directory],{stdio:'pipe'});
 const path='packages/xy-node/src/geoscale.d.ts',old=fs.readFileSync(path,'utf8'),start=old.indexOf('export interface XygGeoCamera'),end=old.indexOf('export declare const GEO_SCALE_HEADER'),suffix=old.indexOf('export declare function geoScaleExecute');
 if(start<0||end<start||suffix<end)throw new Error('missing Node declaration boundaries');
 write(path,fs.readFileSync(join(directory,'63_geo_source.d.ts'),'utf8').replace("import type { XygGeoCamera } from './49_wasm_geoviewport';",old.slice(start,end).trimEnd())+old.slice(suffix));
 write('packages/xy-node/src/geo-selected.d.ts',fs.readFileSync(join(directory,'68_geo_selected.d.ts'),'utf8').replaceAll("'./63_geo_source'","'./geoscale.js'").replaceAll('"./63_geo_source"','"./geoscale.js"').replaceAll("'./72_geo_allocation_attempt'","'./geo-allocation-attempt.js'").replaceAll('"./72_geo_allocation_attempt"','"./geo-allocation-attempt.js"'));
}finally{fs.rmSync(directory,{recursive:true,force:true});}
