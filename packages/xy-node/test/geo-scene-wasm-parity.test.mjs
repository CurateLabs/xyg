// Native executable versus the actual wasm32 geographic Scene processor.
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import {spawnSync} from "node:child_process";
import test from "node:test";
import {fileURLToPath} from "node:url";
import {encodeWasmGeoSceneRequest} from "../../xy-client/dist/index.js";
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),"../../..");
const golden=JSON.parse(fs.readFileSync(path.join(root,"tests/fixtures/geo_cross_host.json")));
const nativePath=process.env.XYG_GEO_SCENE_NATIVE??path.join(root,"target/debug/geo_scene_conformance");
const kinds={point:1,linestring:2,polygon:3,multipoint:4,multilinestring:5,multipolygon:6};
const f64=values=>new Float64Array(BigUint64Array.from(values,h=>BigInt(`0x${h}`)).buffer);
const descriptor=c=>({geometry:kinds[c.extension_name.split(".")[1]],crs:Number(JSON.parse(c.extension_metadata).crs.split(":")[1]),xy:f64(c.descriptor.xy),validity:Uint8Array.from(c.descriptor.validity),featureIds:c.descriptor.feature_ids===null?null:BigUint64Array.from(c.descriptor.feature_ids,BigInt),...Object.fromEntries([0,1,2].map(i=>[`offsets${i}`,Uint32Array.from(c.descriptor[`offsets${i}`]??[])]))});
const camera={centerX:0,centerY:0,zoom:0,width:800,height:600,worldWrap:true};
function records(scene) {
 const v=new DataView(scene.buffer,scene.byteOffset,scene.byteLength);assert.equal(Buffer.from(scene.subarray(0,4)).toString(),"XYGS");
 const count=Number(v.getBigUint64(16,true)),offset=160+16*Number(v.getBigUint64(24,true));
 return Array.from({length:count},(_,i)=>{const at=offset+56*i;return{kind:v.getUint8(at),visible:v.getUint8(at+1),identity:v.getUint8(at+3),id:v.getBigUint64(at+8,true),x:v.getFloat64(at+16,true),y:v.getFloat64(at+24,true),at};});
}
function native(request,budget=64<<20) {
 const got=spawnSync(nativePath,[String(budget)],{input:Buffer.from(request),maxBuffer:128<<20});if(got.error)throw got.error;
 return{status:got.status,bytes:new Uint8Array(got.stdout),error:got.stderr.toString().trim()};
}
async function wasm(budget=64<<20) {
 const {instance}=await WebAssembly.instantiate(fs.readFileSync(path.join(root,"packages/xy-client/dist/xyg-wasm.wasm")),{}),x=instance.exports,h=x.xyg_wasm_instance_new(budget);assert.ok(h>0);
 return{x,h,run(request,sequence=1){assert.equal(x.xyg_wasm_arena_resize(h,request.byteLength),0);new Uint8Array(x.memory.buffer,x.xyg_wasm_arena_ptr(h)>>>0,request.byteLength).set(new Uint8Array(request));const status=x.xyg_wasm_geo_scene_compile(h,sequence,0,request.byteLength);assert.equal(x.xyg_wasm_arena_len(h),0);return{status,bytes:new Uint8Array(x.memory.buffer,x.xyg_wasm_output_ptr(h)>>>0,x.xyg_wasm_output_len(h)).slice(),error:new TextDecoder().decode(new Uint8Array(x.memory.buffer,x.xyg_wasm_last_error_ptr(h)>>>0,x.xyg_wasm_last_error_len(h)))};},dispose(){assert.equal(x.xyg_wasm_instance_dispose(h),0);}};
}
function sameScene(a,b) {
 assert.equal(a.length,b.length);const aa=records(a),bb=records(b);assert.equal(aa.length,bb.length);
 const left=a.slice(),right=b.slice();const va=new DataView(left.buffer),vb=new DataView(right.buffer);
 aa.forEach((record,i)=>{
  assert.equal(record.id,bb[i].id);assert.equal(record.visible,bb[i].visible);
  for(const offset of [16,24,32,40]){const av=va.getFloat64(record.at+offset,true),bv=vb.getFloat64(record.at+offset,true);assert.ok(Number.isFinite(av)&&Number.isFinite(bv));assert.ok(Math.abs(av-bv)<=1e-6,`coordinate difference ${av-bv}`);va.setFloat64(record.at+offset,0,true);vb.setFloat64(record.at+offset,0,true);}
 });
 assert.deepEqual(left,right,"styles, record flags/IDs, header and all sidecars are exact");
}
for(const c of golden.cases.filter(c=>c.descriptor))test(`native/actual WASM Scene: ${c.name}`,async()=>{
 const request=encodeWasmGeoSceneRequest(descriptor(c),camera),expected=native(request),browser=await wasm();
 try{const got=browser.run(request);assert.equal(expected.status,c.status===0?0:2,`golden expected successful/invalid admission: ${c.name}`);assert.equal(got.status,expected.status);assert.equal(got.error,expected.error);if(got.status===0){sameScene(expected.bytes,got.bytes);for(const row of records(got.bytes))assert.equal(row.identity,128);assert.ok(records(got.bytes).filter(r=>r.visible).every(r=>c.descriptor.feature_ids===null||c.descriptor.feature_ids.includes(String(r.id))));}else assert.equal(got.bytes.length,0);}finally{browser.dispose();}
});
test("deep zoom retains visible separation after an offscreen first point and full u64 identities",async()=>{
 const input={geometry:1,crs:4326,xy:Float64Array.from([-180,0,0,0,1e-7,0]),validity:Uint8Array.from([1,1,1]),featureIds:BigUint64Array.from([1n,0x5859040000000001n,0xffffffffffffffffn])};
 const request=encodeWasmGeoSceneRequest(input,{...camera,zoom:24}),browser=await wasm();
 try{const a=native(request),b=browser.run(request);assert.equal(a.status,0);assert.equal(b.status,0);sameScene(a.bytes,b.bytes);const rows=records(b.bytes);assert.equal(rows[0].visible,0);assert.equal(rows[1].visible,1);assert.equal(rows[2].visible,1);assert.ok(Math.abs(rows[2].x-rows[1].x-2.386092942222222)<1e-6);assert.equal(rows[2].id,0xffffffffffffffffn);}finally{browser.dispose();}
});
test("dateline outlines stay independent with both endpoint identities and finite separator records",async()=>{
 const id=0x5859060000000042n,input={geometry:2,crs:4326,xy:Float64Array.from([170,-10,-170,10]),validity:Uint8Array.of(1),featureIds:BigUint64Array.of(id),offsets0:Uint32Array.of(0,2)};
 const request=encodeWasmGeoSceneRequest(input,camera),browser=await wasm();
 try{const a=native(request),b=browser.run(request);assert.equal(b.status,0);sameScene(a.bytes,b.bytes);const rows=records(b.bytes);assert.equal(rows.length,6);for(let i=0;i<6;i+=3){assert.deepEqual(rows.slice(i,i+3).map(r=>r.visible),[1,1,0]);assert.ok(rows.slice(i,i+3).every(r=>r.id===id));assert.equal(rows[i+2].x,0);assert.equal(rows[i+2].y,0);}}finally{browser.dispose();}
});
test("camera, styles, framing, unsupported pitch and allocation fail identically before output",async()=>{
 const input=descriptor(golden.cases.find(c=>c.status===0));let sequence=0;const browser=await wasm();
 try{
  for(const changes of [{pitch:20},{centerX:NaN},{zoom:25},{width:0},{strokeWidth:-1},{strokeWidth:Number.MAX_VALUE},{diameter:Number.MAX_VALUE},{width:Number.MAX_VALUE},{height:Number.MAX_VALUE},{crs:3857}]){const request=encodeWasmGeoSceneRequest(input,{...camera,...changes}),a=native(request),b=browser.run(request,++sequence);assert.notEqual(a.status,0);assert.equal(b.status,a.status);assert.equal(b.error,a.error);assert.equal(b.bytes.length,0);}
  const base=encodeWasmGeoSceneRequest(input,camera),bad=base.slice(0);new DataView(bad).setUint32(12,8,true);
  for(const request of [bad,base.slice(0,-1)]){const a=native(request),b=browser.run(request,++sequence);assert.equal(a.status,2);assert.equal(b.error,a.error);}
 }finally{browser.dispose();}
 const request=encodeWasmGeoSceneRequest(input,camera),small=await wasm(8192);
 try{const a=native(request,8192),b=small.run(request);assert.equal(a.status,3);assert.equal(b.status,3);assert.equal(b.error,a.error);assert.equal(b.bytes.length,0);}finally{small.dispose();}
});

test("actual WASM scene cancellation, stale sequence, recovery, release and disposal",async()=>{
 const input=descriptor(golden.cases.find(c=>c.status===0)),browser=await wasm(),{x,h}=browser;
 const request=()=>encodeWasmGeoSceneRequest(input,camera);
 assert.equal(browser.run(request(),1).status,0);
 assert.equal(browser.run(request(),1).status,7);
 assert.equal(x.xyg_wasm_cancel(h,2),0);
 assert.equal(browser.run(request(),2).status,6);
 assert.equal(browser.run(request(),3).status,0);
 browser.dispose();
 assert.equal(x.xyg_wasm_geo_scene_compile(h,4,0,0),1);
});
