#!/usr/bin/env node
// Actual C ABI / packaged wasm32 bytes. The authored fixture is deliberately small;
// no selected public controller, source-sized mask or performance claim is implied.
import assert from 'node:assert/strict';
import {readFileSync,writeFileSync,mkdirSync} from 'node:fs';
import {dirname} from 'node:path';
import {createHash} from 'node:crypto';
import {gzipSync} from 'node:zlib';
import {chromium} from 'playwright';
import {nativeGeoScaleBridge} from '../packages/xy-node/src/geoscale.js';
import {nativeGeoTileBridge} from '../packages/xy-node/src/geo-tiles.js';
import {nativeGeoSnapshotBridge,encodeGeoSnapshotRequest,decodeGeoSnapshotReply} from '../packages/xy-node/src/geo-snapshot.js';
import {buildSelectedSnapshotFixture,MIXED_BUDGET} from '../tests/browser/geo_selected_snapshot_fixture.mjs';
const artifact=readFileSync(new URL('../packages/xy-client/dist/xyg-wasm.wasm',import.meta.url));
const {instance}=await WebAssembly.instantiate(artifact,{}),x=instance.exports,h=x.xyg_wasm_instance_new(MIXED_BUDGET);
assert.ok(h);assert.equal(x.xyg_wasm_geo_transport_acquire(h),0);let sequence=0;
function call(family,read,request){
 assert.equal(x.xyg_wasm_arena_resize(h,request.byteLength),0);
 new Uint8Array(x.memory.buffer,x.xyg_wasm_arena_ptr(h)>>>0,request.byteLength).set(new Uint8Array(request));
 const status=x[`xyg_wasm_geo_${family}_${read?'read':'execute'}`](h,++sequence,0,request.byteLength);
 if(status){const detail=new TextDecoder().decode(new Uint8Array(x.memory.buffer,x.xyg_wasm_last_error_ptr(h)>>>0,x.xyg_wasm_last_error_len(h)));throw Error(`${family} command${new DataView(request).getUint32(8,true)} handle${new DataView(request).getBigUint64(16,true)} ${status}: ${detail}`);}
 return new Uint8Array(x.memory.buffer,x.xyg_wasm_output_ptr(h)>>>0,x.xyg_wasm_output_len(h)).slice().buffer;
}
const wasm={};for(const family of ['scale','tile','snapshot'])wasm[family==='scale'?'source':family]={execute:async r=>call(family,false,r),read:async r=>call(family,true,r)};
const native={source:nativeGeoScaleBridge(MIXED_BUDGET),tile:nativeGeoTileBridge(MIXED_BUDGET),snapshot:nativeGeoSnapshotBridge(384<<20)};
function validateFrozen(packet,footer){
 const b=new Uint8Array(packet),v=new DataView(packet);assert.equal(new TextDecoder().decode(b.subarray(0,4)),'XYGX');assert.equal(v.getUint32(4,true),3);
 assert.equal(v.getBigUint64(16,true),BigInt(b.length));assert.equal(v.getUint32(192,true),1);
 const at=208+v.getUint32(32,true)*80+v.getUint32(36,true)*48+v.getUint32(40,true)*96;
 assert.equal(v.getUint32(184,true),1);const cells=Number(v.getBigUint64(at+160,true)),selected=at+232+cells*8+160;
 assert.deepEqual(b.subarray(selected,selected+footer.length),footer);
 assert.equal(v.getBigUint64(selected+16,true),0xffffffffffffffffn);
 assert.equal(v.getBigUint64(selected+40,true),1n);assert.equal(v.getBigUint64(selected+128,true),0xffffffffffffffffn);
 assert.deepEqual([...b.subarray(selected+48,selected+52)],[0,255,0,255]);
 assert.equal(v.getBigInt64(56,true),-0x8000000000000000n);
 return {bytes:b.length,selectedRecord:selected-160,sceneBytes:Number(v.getBigUint64(24,true)),tileBytes:v.getUint32(188,true)};
}
let a,b,af,bf;
try{
 a=await buildSelectedSnapshotFixture(native);b=await buildSelectedSnapshotFixture(wasm);
 const ordinary=validateFrozen(a.ordinaryFrozen,a.liveFooter);validateFrozen(b.ordinaryFrozen,b.liveFooter);
 assert.deepEqual(new Uint8Array(a.ordinaryFrozen),new Uint8Array(b.ordinaryFrozen));
 af=await a.freeze();bf=await b.freeze();const mixed=validateFrozen(af.bytes,a.liveFooter);validateFrozen(bf.bytes,b.liveFooter);
 assert.deepEqual(new Uint8Array(af.bytes),new Uint8Array(bf.bytes));assert.ok(mixed.tileBytes>0);
 const formats={};let html;
 for(const format of ['svg','png','pdf','jpeg','webp','html']){
  const out=decodeGeoSnapshotReply(await native.snapshot.execute(encodeGeoSnapshotRequest(2,af.handle,{budget:384<<20,format,quality:90,scale:1}))).handle;
  try{
   const bytes=await native.snapshot.read(encodeGeoSnapshotRequest(22,out)),companion=await native.snapshot.read(encodeGeoSnapshotRequest(21,out));
   validateFrozen(companion,a.liveFooter);formats[format]={bytes:bytes.byteLength,sha256:createHash('sha256').update(new Uint8Array(bytes)).digest('hex')};
   if(format==='svg'||format==='html'){const text=new TextDecoder().decode(bytes);assert.ok(text.includes('Tiles'));if(format==='html'){assert.ok(text.includes("default-src 'none'")&&!text.includes('<script'));html=Buffer.from(bytes);}}
  }finally{await native.snapshot.execute(encodeGeoSnapshotRequest(3,out));}
 }
 await assert.rejects(wasm.snapshot.execute(encodeGeoSnapshotRequest(2,bf.handle,{budget:MIXED_BUDGET,format:'png'})),/UNSUPPORTED/);
 // Pre-Rust caller budget refusal does not consume old frozen/frame authority.
 await assert.rejects(native.snapshot.execute(encodeGeoSnapshotRequest(5,a.frame.handle,{sequence:a.frame.nonce,budget:256})),error=>error.status===-9&&error.code==='XYG_GEO_SNAPSHOT_LIMIT');
 const recovered=await a.freeze();try{assert.deepEqual(new Uint8Array(recovered.bytes),new Uint8Array(af.bytes));}finally{await recovered.dispose();}
 const htmlPath=process.env.XYG_SELECTED_HTML??'/tmp/xyg-selected-snapshot.html';writeFileSync(htmlPath,html);html=undefined;
 const executablePath=process.env.XYG_CHROMIUM??process.env.CHROMIUM, browser=await chromium.launch({...(executablePath?{executablePath}:{}),args:['--use-angle=swiftshader','--enable-unsafe-swiftshader']});
 let replay;const errors=[],external=[];
 try{const page=await browser.newPage();page.on('pageerror',e=>errors.push(e.message));await page.route('**/*',route=>{const url=new URL(route.request().url());if(!['file:','data:'].includes(url.protocol)){external.push(url.href);return route.abort();}return route.continue();});await page.goto(new URL(`file://${htmlPath}`).href);await page.waitForFunction(()=>document.querySelector('img')?.complete&&document.querySelector('img')?.naturalWidth===64);
  replay=await page.evaluate(()=>{const canvas=document.createElement('canvas');canvas.width=canvas.height=64;const ctx=canvas.getContext('2d');ctx.drawImage(document.querySelector('img'),0,0);const region=ctx.getImageData(41,51,20,12).data;let dark=0,white=0,minimumInk=255;for(let i=0;i<region.length;i+=4){minimumInk=Math.min(minimumInk,Math.max(...region.slice(i,i+3)));if(Math.max(...region.slice(i,i+3))<64&&region[i+3]===255)dark++;if(region[i]===255&&region[i+1]===255&&region[i+2]===255&&region[i+3]===255)white++;}return {center:[...ctx.getImageData(32,32,1,1).data],background:[...ctx.getImageData(2,2,1,1).data],dark,white,minimumInk,scripts:document.querySelectorAll('script').length,attribution:document.body.textContent.includes('Tiles')};});
  assert.deepEqual(replay.center,[0,255,0,255]);assert.deepEqual(replay.background,[0,0,255,255]);assert.ok(replay.dark>0&&replay.white>0&&replay.attribution,JSON.stringify(replay));assert.equal(replay.scripts,0);assert.deepEqual(errors,[]);assert.deepEqual(external,[]);
 }finally{await browser.close();}
 const report={ordinary,mixed,formats,replay,wasm:{rawBytes:artifact.length,gzipBytes:gzipSync(artifact,{level:9}).length,sha256:createHash('sha256').update(artifact).digest('hex')},scope:'Actual native/packaged WASM ordinary+mixed selected XYGX v3 and exact live XYSE footer parity, original source/tile/coord disposal, six native formats, actual offline strict-CSP HTML pixels/attribution with no scripts/network; WASM raster Unsupported; small fixture, no live imported-source authority or interactive/performance claim.'};
 if(process.env.XYG_SELECTED_REPORT){mkdirSync(dirname(process.env.XYG_SELECTED_REPORT),{recursive:true});writeFileSync(process.env.XYG_SELECTED_REPORT,JSON.stringify(report,null,2)+'\n');}
 console.log(JSON.stringify(report));
}finally{
 if(af){af.bytes=undefined;await af.dispose();}if(bf){bf.bytes=undefined;await bf.dispose();}
 if(a){a.scene=a.descriptorBytes=a.ordinaryFrozen=a.liveFooter=undefined;await a.frame.dispose();await a.releaseScope();}
 if(b){b.scene=b.descriptorBytes=b.ordinaryFrozen=b.liveFooter=undefined;await b.frame.dispose();await b.releaseScope();}
 assert.equal(x.xyg_wasm_instance_dispose(h),0);
}
