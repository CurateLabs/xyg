// Keep authored vector oracles; regenerate only native complete-Scene hashes.
import assert from 'node:assert/strict';
import {readFileSync,writeFileSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {encodeTemporalScene,temporalSceneCompile} from '../packages/xy-node/src/temporal-scene.js';
const file=new URL('../tests/fixtures/temporal/line-window-edges.json',import.meta.url);
const original=readFileSync(file,'utf8'),fixture=JSON.parse(original);
assert.equal(fixture.schema,'xyg.temporal-line-window/v1');assert.equal(fixture.cases.length,8);
for(const row of fixture.cases){
 const packet=encodeTemporalScene({kind:'line',rows:row.times.map((t,i)=>[t===null?null:BigInt(t),null,row.values[i],BigInt(i+42)]),domain:row.domain.map(BigInt),timezone:'UTC',width:fixture.width,height:fixture.height,strokeWidth:4});
 row.sceneSha256=createHash('sha256').update(temporalSceneCompile(packet)).digest('hex');
}
const output=JSON.stringify(fixture,null,2)+'\n';
if(process.argv.includes('--write'))writeFileSync(file,output);
else assert.equal(output,original,'line-window native oracles stale; regenerate with --write and the intended native library');
