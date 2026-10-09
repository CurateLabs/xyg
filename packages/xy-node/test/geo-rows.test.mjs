// Actual native original-row paging, opaque continuation and detached-frame ownership.
import test from 'node:test';
import assert from 'node:assert/strict';
import {RetainedGeoSource} from '../src/geo-retained.js';
import {encodeGeoScaleRequest as encode,decodeGeoScaleReply as decode,encodeGeoChunkRequest,encodeGeoScaleStyle,parseGeoRowsData,nativeGeoScaleBridge} from '../src/geoscale.js';
import {budget as base,U64,I64} from './geoscale-fixture.mjs';
const budget={...base,pageRows:2};
const style=()=>encodeGeoScaleStyle({fill:new Uint8Array([255,0,0,255]),stroke:new Uint8Array(4),strokeWidth:0,diameter:6,opacity:1,symbol:0});
async function fixture(){
 const bridge=nativeGeoScaleBridge(budget.processorBytes),descriptor=new Uint8Array(264),v=new DataView(descriptor.buffer);
 descriptor.set([88,89,71,68]);[1,4,4326,1,0].forEach((n,i)=>v.setUint32(4+i*4,n,true));[5n,8n,6n,0n,0n].forEach((n,i)=>v.setBigUint64(24+i*8,n,true));
 [0,0,1,1,179,85,178,84,-179,-85,-178,-84,.5,.5,2,2].forEach((n,i)=>v.setFloat64(64+i*8,n,true));descriptor.set([1,1,0,1,1],192);[U64,7n,1n<<63n,7n,9n].forEach((n,i)=>v.setBigUint64(200+i*8,n,true));[0,2,4,4,6,8].forEach((n,i)=>v.setUint32(240+i*4,n,true));
 const chunk=await bridge.read(encodeGeoChunkRequest({descriptor,rows:5,intervals:{starts:new BigInt64Array([I64,-10n,0n,-10n,0n]),ends:new BigInt64Array([-10n,0n,0n,0n,0n]),startValidity:new Uint8Array([1,1,0,1,0]),endValidity:new Uint8Array([1,1,0,1,0])},values:new Float64Array([-0,NaN,42,Infinity,5])},budget.processorBytes));
 const builder=decode(await bridge.execute(encode({command:1}))).handle;
 try{await bridge.execute(encode({command:2,handle:builder,payload:chunk}));await bridge.execute(encode({command:3,handle:builder,generation:U64}));return {bridge,chunk,manifest:await bridge.read(encode({command:21,handle:builder}))};}finally{await bridge.execute(encode({command:10,handle:builder}));}
}
function query(info){return {camera:{crs:4326,worldWrap:true,centerX:0,centerY:0,zoom:4,width:800,height:600,bearing:0,pitch:0},reducedKind:0,maxCells:32768,previousDirect:true,sourceDigest:info.digest,generation:info.generation,layerId:U64,cameraRevision:U64,timeRevision:U64,layerRevision:U64,styleRevision:U64,stateRevision:U64,time:{kind:1,instant:-10n},maxProjectedVertices:1000000n};}
test('all original rows remain pageable after source and frame disposal',async()=>{
 const f=await fixture(),source=await RetainedGeoSource.create(f.manifest,async()=>f.chunk,{budget,bridge:f.bridge});const frame=await source.update(query(source.info),{sequence:1n,style:style()});let page=await frame.rows();
 await source.dispose();await frame.dispose();const rows=[];
 try{for(;;){const data=page.data;assert.ok(data.records instanceof Uint8Array);assert.equal(data.records.buffer,data.packet);assert.ok(data.length<=2);for(let i=0;i<data.length;i++)rows.push(data.record(i));if(!data.hasNext){assert.throws(()=>page.nextPage(),/no next/);break;}const next=await page.nextPage();await page.dispose();assert.throws(()=>page.nextPage(),/disposed/);page=next;}
 assert.deepEqual(rows.map(r=>r.sourceRow),[0n,1n,2n,3n,4n]);assert.deepEqual(rows.map(r=>r.featureId),[U64,7n,1n<<63n,7n,9n]);assert.equal(rows[0].intervalStart,I64);assert.equal(rows[0].timeEligible,false);assert.equal(rows[2].geometryNull,true);assert.equal(rows[2].eligible,false);assert.equal(rows[1].eligible,true);assert.equal(rows[3].eligible,true);assert.equal(rows[4].intervalStart,null);assert.equal(Object.is(rows[0].value,-0),true);
 }finally{await page.dispose();}
});
test('failed authenticated read preserves old paint and opaque continuation',async()=>{
 const f=await fixture();let bad=false;const source=await RetainedGeoSource.create(f.manifest,async()=>bad?new ArrayBuffer(f.chunk.byteLength):f.chunk,{budget,bridge:f.bridge});const frame=await source.update(query(source.info),{sequence:1n,style:style()}),page=await frame.rows();
 try{bad=true;await assert.rejects(page.nextPage());assert.equal(source.current,frame);assert.equal(page.data.record(0).featureId,U64);bad=false;const next=await page.nextPage();await next.dispose();assert.throws(()=>page.nextPage({cursor:new Uint8Array(8)}),/no cursor/);assert.throws(()=>frame.rows({cursor:0}),/no cursor/);
 const mutated=page.data.packet.slice(0);new DataView(mutated).setUint32(256+24,128,true);assert.throws(()=>parseGeoRowsData(mutated));await assert.rejects(f.bridge.execute(encode({command:15,handle:page.handle,sequence:1n,budget,payload:new Uint8Array(8)})));
 }finally{await page.dispose();await frame.dispose();await source.dispose();}
});
test('cancellation waits for outstanding rows read and recovers without dropping old frame',async()=>{
 const f=await fixture();let hold=false,entered,release;const gate=new Promise(r=>release=r),started=new Promise(r=>entered=r);const reader=async()=>{if(hold){entered();await gate;}return f.chunk;};const source=await RetainedGeoSource.create(f.manifest,reader,{budget,bridge:f.bridge});const frame=await source.update(query(source.info),{sequence:1n,style:style()});hold=true;const pending=frame.rows();await started;let settled=false;pending.then(()=>settled=true,()=>settled=true);const cancellation=source.cancel();await new Promise(r=>setTimeout(r,10));assert.equal(settled,false);release();await assert.rejects(pending,/abort/);await cancellation;assert.equal(source.current,frame);hold=false;const page=await frame.rows();await page.dispose();await frame.dispose();await source.dispose();
});
for(const delayed of ['read','dispose'])test(`cancelled ${delayed} settles and releases unreturned RowsData`,async()=>{
 const f=await fixture();let active=false,rowSession,rowData,entered,release;const gate=new Promise(r=>release=r),started=new Promise(r=>entered=r);
 const bridge={async execute(request){const v=new DataView(request),command=v.getUint32(8,true),handle=v.getBigUint64(16,true);if(active&&delayed==='dispose'&&command===10&&handle===rowSession){entered();await gate;}const reply=await f.bridge.execute(request);if(active&&command===15)rowSession=decode(reply).handle;if(active&&command===16)rowData=decode(reply).handle;return reply;},async read(request){const reply=await f.bridge.read(request);if(active&&delayed==='read'&&new DataView(request).getUint32(8,true)===23){entered();await gate;}return reply;}};
 const source=await RetainedGeoSource.create(f.manifest,async()=>f.chunk,{budget,bridge}),frame=await source.update(query(source.info),{sequence:1n,style:style()});active=true;const pending=frame.rows();await started;let settled=false;pending.catch(()=>settled=true);const cancellation=source.cancel();await new Promise(r=>setTimeout(r,10));assert.equal(settled,false);release();await assert.rejects(pending,/abort/);await cancellation;active=false;await assert.rejects(f.bridge.read(encode({command:23,handle:rowData})));assert.equal(source.current,frame);const page=await frame.rows();await page.dispose();await frame.dispose();await source.dispose();
});
