// Mechanical shared codec projection; Node owns only native transport/owner glue.
import {stripTypeScriptTypes} from 'node:module';
import {readFile,writeFile} from 'node:fs/promises';
const root=new URL('../',import.meta.url);
const source=await readFile(new URL('js/src/70_geo_hierarchy.ts',root),'utf8');
const output='// Generated from js/src/70_geo_hierarchy.ts; run scripts/gen_geo_hierarchy_node.mjs.\n'+stripTypeScriptTypes(source,{mode:'strip'}).replace("'./63_geo_source'","'./geoscale.js'").split('\n').map(line=>line.trimEnd()).join('\n');
const target=new URL('packages/xy-node/src/geo-hierarchy-wire.js',root);
if(process.argv.includes('--check')){if(await readFile(target,'utf8')!==output)throw new Error('hierarchy codec is stale');}else await writeFile(target,output);
