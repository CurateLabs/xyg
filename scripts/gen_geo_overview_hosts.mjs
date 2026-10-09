#!/usr/bin/env node
// Reproduce thin shared transport/overview Node bindings; never ABI declarations.
import fs from 'node:fs';
import {stripTypeScriptTypes} from 'node:module';
import {execFileSync} from 'node:child_process';
import {mkdtempSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
const check=process.argv.includes('--check');
if(process.argv.slice(2).some(a=>a!=='--check'))throw Error('Unknown generator argument');
let mismatches=0;
function write(path,bytes){if(check){if(!fs.existsSync(path)||fs.readFileSync(path,'utf8')!==bytes){process.stderr.write(`Generated output differs: ${path}\n`);mismatches++;}}else fs.writeFileSync(path,bytes);}
const clean=s=>s.split('\n').map(l=>l.trimEnd()).join('\n');
const marker='// Load generated native bindings only when requested; framing stays host-neutral.';
const path='packages/xy-node/src/geoscale.js',old=fs.readFileSync(path,'utf8'),at=old.indexOf(marker);
if(at<0)throw Error('Canonical Node native suffix missing');
write(path,clean(stripTypeScriptTypes(fs.readFileSync('js/src/63_geo_source.ts','utf8')))+'\n'+old.slice(at));
const overview=clean(stripTypeScriptTypes(fs.readFileSync('js/src/67_geo_overview.ts','utf8'))).replaceAll("'./63_geo_source'","'./geoscale.js'");
write('packages/xy-node/src/geo-overview.js','// Mechanical type stripping of js/src/67_geo_overview.ts; no host policy.\n'+overview);
const members=clean(stripTypeScriptTypes(fs.readFileSync('js/src/73_geo_overview_members.ts','utf8'))).replaceAll("'./63_geo_source'","'./geoscale.js'");
write('packages/xy-node/src/geo-overview-members.js','// Mechanical type stripping of canonical73; no host policy.\n'+members);
const shared=clean(stripTypeScriptTypes(fs.readFileSync('js/src/71_geo_overview_owner.ts','utf8'))).replaceAll("'./63_geo_source'","'./geoscale.js'").replaceAll("'./67_geo_overview'","'./geo-overview.js'").replaceAll("'./73_geo_overview_members'","'./geo-overview-members.js'");
write('packages/xy-node/src/geo-overview-source.js','// Mechanical shared71 type stripping; native export is a thin bridge.\n'+shared+`
import {geoScaleExecute} from './geoscale.js';
import {exportGeoFrame} from './geo-snapshot.js';
const nativeIndices=new WeakSet(),fromFrame=GeoOverviewIndex.fromFrame;
GeoOverviewIndex.fromFrame=async(frame,input)=>{const native=geoSceneDataAuthority(frame)?.execute===geoScaleExecute;const index=await fromFrame(frame,input);if(native)nativeIndices.add(index);return index;};
GeoOverviewFrame.prototype.export=function(format='png',options={}){if(Object.keys(options).some(k=>!['scale','quality','budget'].includes(k)))throw new TypeError('Unsupported overview export option');const a=overviewFrameAuthority(this);if(!a||!nativeIndices.has(a.index))throw new TypeError('Native overview export requires its native issuing transport');return exportGeoFrame({_freezeCommand:6,handle:a.handle,data:this.data},a.sequence,format,options);};
`);
const output=mkdtempSync(join(tmpdir(),'xyg-overview-declarations-'));
execFileSync('node_modules/.bin/tsc',['--declaration','--emitDeclarationOnly','--target','ES2022','--module','ESNext','--moduleResolution','bundler','--skipLibCheck','--outDir',output,'js/src/71_geo_overview_owner.ts']);
const dpath='packages/xy-node/src/geoscale.d.ts',dold=fs.readFileSync(dpath,'utf8');
const camera=dold.split('\n').find(l=>l.startsWith('export interface XygGeoCamera'));
const suffix=dold.slice(dold.indexOf('export declare function geoScaleExecute('));
if(!camera||!suffix.startsWith('export declare function geoScaleExecute('))throw Error('Native declaration suffix missing');
let declaration=fs.readFileSync(join(output,'63_geo_source.d.ts'),'utf8').replace("import type { XygGeoCamera } from './49_wasm_geoviewport';",camera);
write(dpath,declaration+suffix);
write('packages/xy-node/src/geo-overview-members.d.ts',fs.readFileSync(join(output,'73_geo_overview_members.d.ts'),'utf8').replaceAll("'./63_geo_source'","'./geoscale.js'"));
write('packages/xy-node/src/geo-overview.d.ts',fs.readFileSync(join(output,'67_geo_overview.d.ts'),'utf8').replaceAll("'./63_geo_source'","'./geoscale.js'"));
declaration=fs.readFileSync(join(output,'71_geo_overview_owner.d.ts'),'utf8').replaceAll("'./63_geo_source'","'./geoscale.js'").replaceAll("'./67_geo_overview'","'./geo-overview.js'").replaceAll("'./73_geo_overview_members'","'./geo-overview-members.js'");
write('packages/xy-node/src/geo-overview-source.d.ts',declaration+`
import type {OwnedGeoArtifact} from './geo-snapshot.js';
export interface GeoOverviewFrame {export(format?:'svg'|'png'|'pdf'|'jpeg'|'webp'|'html',options?:{scale?:number;quality?:number;budget?:number}):Promise<OwnedGeoArtifact>;}
`);

if(mismatches)process.exitCode=1;
