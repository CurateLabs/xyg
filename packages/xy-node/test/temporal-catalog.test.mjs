import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {temporalChart,encodeTemporalScene} from '../src/index.js';
import {temporalSceneCompile} from '../src/temporal-scene.js';
import {temporalSceneSize} from '../src/temporal-scene-framing.js';
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

test('public temporal constructor refuses oversized rows before snapshot access',()=>{
 const rows=new Proxy([],{get(target,key){
  if(key==='length')return Math.floor(64*1024*1024/40)+1;
  throw new Error('public constructor copied oversized source');
 }});
 assert.throws(()=>temporalChart('event',rows,{domain:[0n,10n],timezone:'UTC'}),/framing budget/);
 const cap=64*1024*1024, count=Math.floor((cap-128-3)/40), remainder=cap-128-3-count*40;
 assert.equal(temporalSceneSize(count,'UTC','x'.repeat(remainder)),cap);
 assert.throws(()=>temporalSceneSize(count,'UTC','x'.repeat(remainder)+'é'),/framing budget/);
 for(const n of [-1,NaN,Infinity,1.5,Number.MAX_SAFE_INTEGER])assert.throws(()=>temporalSceneSize(n,'UTC'),/framing budget/);
 const source=[[1n,null,1,1n]];
 const chart=temporalChart('event',source,{domain:[0n,10n],timezone:'UTC'});
 const scene=Buffer.from(chart.toScene());source[0][2]=99;source.push([2n,null,2,2n]);
 assert.deepEqual(Buffer.from(chart.toScene()),scene);
 let lengthReads=0;
 const changingLength=new Proxy([[1n,null,1,1n]],{get(target,key){
  if(key==='length'){lengthReads++;assert.equal(lengthReads,1);return 1;}
  return Reflect.get(target,key);
 }});
 assert.deepEqual(Buffer.from(temporalChart('event',changingLength,{domain:[0n,10n],timezone:'UTC'}).toScene()),scene);
});

test('extreme finite temporal values remain visible at distinct projected heights',()=>{
 for(const values of [[-1e308,0,1e308],[-Number.MAX_VALUE,0,Number.MAX_VALUE]]){
  for(const kind of ['event','scatter']){
   const chart=temporalChart(kind,values.map((v,i)=>[BigInt(i+1),null,v,BigInt(i+1)]),{domain:[0n,10n],timezone:'UTC',width:900,height:420});
   const svg=Buffer.from(chart.toSvg()).toString();
   const circles=[...svg.matchAll(/<circle\b[^>]*\bcy="([^"]+)"[^>]*>/g)];
   assert.deepEqual(circles.map(m=>Number(m[1])),[372,210,48]);
   assert.deepEqual(Buffer.from(chart.toPng()).subarray(0,8),Buffer.from([137,80,78,71,13,10,26,10]));
  }
 }
});

for(const kind of ['event','interval','gantt','line','bar','scatter'])test(`dense public ${kind} membership, bounds and disposal`,()=>{
 const n=10000,rows=Array.from({length:n},(_,i)=>[BigInt(i),BigInt(i+1),0,2n**63n+BigInt(i)]);
 const chart=temporalChart(kind,rows,{domain:[0n,BigInt(n)],timezone:'UTC',dense:true,width:900,height:420});
 const metadata=chart.temporalMetadata(),m=new DataView(metadata.buffer,metadata.byteOffset,metadata.byteLength);
 assert.equal(m.getBigUint64(44,true),BigInt(n));
 const key=Number(m.getBigUint64(64,true)),count=Number(m.getBigUint64(72,true));
 const members=chart.temporalMembers(metadata,key),v=new DataView(members.buffer,members.byteOffset,members.byteLength);
 const columns=Math.floor((900-89)/4);
 const expected=rows.filter(([start,end])=>kind==='interval'||kind==='gantt'?start*BigInt(columns)<10000n&&end>0n:start*BigInt(columns)/10000n===0n).map(r=>r[3]);
 assert.equal(count,expected.length);assert.deepEqual(Array.from({length:(members.length-64)/8},(_,i)=>v.getBigUint64(64+i*8,true)),expected);
 assert.ok(chart.toScene().length<2e6);assert.match(Buffer.from(chart.toSvg()).toString(),/<rect/);
 chart.temporalViewport([1n,BigInt(n)]);assert.throws(()=>chart.temporalMembers(metadata,key));
 chart.temporalDispose();assert.throws(()=>chart.toScene(),/disposed/);
});
