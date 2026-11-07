import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {temporalChart,encodeTemporalScene} from '../src/index.js';
import {temporalSceneCompile} from '../src/temporal-scene.js';
const oracle=JSON.parse(readFileSync(new URL('../../../tests/fixtures/temporal/catalog-six-families.json',import.meta.url)));
const digest=bytes=>createHash('sha256').update(bytes).digest('hex');
for(const kind of ['event','interval','gantt','line','bar','scatter'])test(`public temporal ${kind}`,()=>{
 const origin=9223372036854775707n;
 const rows=[[origin+1n,origin+4n,1,18446744073709551615n],[origin+5n,null,2,42n]];
 const chart=temporalChart(kind,rows,{domain:[origin,origin+10n],timezone:'UTC'});
 assert.equal(Buffer.from(chart.toScene()).subarray(0,4).toString(),'XYGS');
 assert.match(Buffer.from(chart.toSvg()).toString(),/UTC/);
 assert.deepEqual(Buffer.from(chart.toPng()).subarray(0,8),Buffer.from([137,80,78,71,13,10,26,10]));
 assert.match(chart.toHtml(),/hydrateWasmPainter/);
 const packet=encodeTemporalScene({kind,rows,domain:[origin,origin+10n],timezone:'UTC'});
 assert.equal(new DataView(packet).getBigInt64(131,true),origin+1n);
 const retained=oracle.cases.find(row=>row.kind===kind);
 const boundPacket=encodeTemporalScene({kind,rows,domain:[origin,origin+10n],timezone:'UTC',title:'LF\nCRLF\r\n'});
 assert.equal(digest(new Uint8Array(boundPacket)),retained.requestSha256);
 const scene=temporalSceneCompile(boundPacket);
 assert.equal(scene.length,retained.sceneBytes);
 assert.equal(digest(scene),retained.sceneSha256);
});

test('temporal static exports compile the requested size without mutating authoring',()=>{
 for(const kind of ['event','interval','gantt','line','bar','scatter']){
  const chart=temporalChart(kind,[[1n,4n,1,42n],[5n,8n,2,43n]],{domain:[0n,10n],timezone:'UTC'});
  const original=Buffer.from(chart.toScene());
  const authored=[chart.width,chart.height];
  for(const [width,height] of [[450,210],[1200,600]]){
   const svg=Buffer.from(chart.toSvg({width,height})).toString();
   assert.match(svg,new RegExp('width="'+width+'"'));
   assert.match(svg,new RegExp('height="'+height+'"'));
   const png=Buffer.from(chart.toPng({width,height,scale:1}));
   assert.equal(png.readUInt32BE(16),width);assert.equal(png.readUInt32BE(20),height);
   assert.deepEqual([chart.width,chart.height],authored);
   assert.deepEqual(Buffer.from(chart.toScene()),original);
  }
 }
});
