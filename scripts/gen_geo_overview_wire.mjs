#!/usr/bin/env node
// Generate the Node transport and declarations from the shared typed lifecycle.
import {stripTypeScriptTypes} from 'node:module';
import {mkdtempSync,readFileSync,writeFileSync,rmSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {spawnSync} from 'node:child_process';
const root=new URL('../',import.meta.url),source=new URL('js/src/67_geo_overview.ts',root);
const directory=mkdtempSync(join(tmpdir(),'xyg-overview-declarations-'));
try{
 const result=spawnSync(process.execPath,[new URL('node_modules/typescript/bin/tsc',root).pathname,source.pathname,'--declaration','--emitDeclarationOnly','--outDir',directory,'--target','ES2022','--module','ESNext','--moduleResolution','bundler','--skipLibCheck'],{encoding:'utf8'});
 if(result.error)throw result.error;
 if(result.status!==0)throw Error(result.stdout+result.stderr);
 const clean=s=>s.split('\n').map(line=>line.trimEnd()).join('\n');
 const imports=s=>s.replaceAll("'./63_geo_source'","'./geoscale.js'");
 const outputs={
  'geo-overview.js':'// Mechanical type stripping of js/src/67_geo_overview.ts; no host policy.\n'+imports(clean(stripTypeScriptTypes(readFileSync(source,'utf8')))),
  'geo-overview.d.ts':imports(readFileSync(join(directory,'67_geo_overview.d.ts'),'utf8')),
 };
 for(const [name,text] of Object.entries(outputs)){
  const path=new URL('packages/xy-node/src/'+name,root);
  if(process.argv.includes('--check')){if(readFileSync(path,'utf8')!==text)throw Error(name+' is stale; run node scripts/gen_geo_overview_wire.mjs');}
  else writeFileSync(path,text);
 }
}finally{rmSync(directory,{recursive:true,force:true});}
