import {test} from 'node:test';
import assert from 'node:assert/strict';
import {temporalChart,encodeTemporalScene} from '../src/index.js';
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
});
