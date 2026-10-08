// Real wasm32/native GeoColumn equivalence, including stable failures and lifecycle.
import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";
import { geoColumnNew, geoColumnMetadata, geoColumnFree } from "../src/index.js";
import { encodeWasmGeoDescriptor } from "../../xy-client/dist/index.js";
const golden = JSON.parse(fs.readFileSync(new URL("../../../tests/fixtures/geo_cross_host.json", import.meta.url)));
const artifact = new URL("../../xy-client/dist/xyg-wasm.wasm", import.meta.url);
const kinds = {point:1,linestring:2,polygon:3,multipoint:4,multilinestring:5,multipolygon:6};
function descriptor(c) {
  const d=c.descriptor;
  return { geometry:kinds[c.extension_name.split(".")[1]], crs:Number(JSON.parse(c.extension_metadata).crs?.split(":")[1] ?? 0),
    xy:new Float64Array(BigUint64Array.from(d.xy,hex=>BigInt(`0x${hex}`)).buffer), validity:Uint8Array.from(d.validity),
    featureIds:d.feature_ids === null ? null : BigUint64Array.from(d.feature_ids,BigInt),
    ...Object.fromEntries([0,1,2].map(i=>[`offsets${i}`,Uint32Array.from(d[`offsets${i}`]??[])])) };
}
async function instance(budget=1<<20) {
  const {instance}=await WebAssembly.instantiate(fs.readFileSync(artifact),{}),x=instance.exports;
  assert.equal(x.xyg_wasm_abi_version(),31);assert.equal(x.xyg_wasm_geo_metadata_version(),1);
  const h=x.xyg_wasm_instance_new(budget);assert.ok(h>0);
  return {x,h,run(bytes,sequence=1,prefix=0) {
    assert.equal(x.xyg_wasm_arena_resize(h,bytes.byteLength+prefix),0);
    new Uint8Array(x.memory.buffer,x.xyg_wasm_arena_ptr(h)>>>0,bytes.byteLength+prefix).fill(0xa5);
    new Uint8Array(x.memory.buffer,(x.xyg_wasm_arena_ptr(h)>>>0)+prefix,bytes.byteLength).set(new Uint8Array(bytes));
    const status=x.xyg_wasm_geo_column_ingest(h,sequence,prefix,bytes.byteLength);
    assert.equal(x.xyg_wasm_arena_len(h),0,"single-use staging is released");
    const output=new Uint8Array(x.memory.buffer,x.xyg_wasm_output_ptr(h)>>>0,x.xyg_wasm_output_len(h)).slice();
    const error=new TextDecoder().decode(new Uint8Array(x.memory.buffer,x.xyg_wasm_last_error_ptr(h)>>>0,x.xyg_wasm_last_error_len(h)));
    return {status,output,error};
  },dispose(){assert.equal(x.xyg_wasm_instance_dispose(h),0);} };
}
const codes={[-1]:"INVALID_ARGUMENT",[-2]:"UNSUPPORTED_CRS",[-3]:"TYPE_MISMATCH",[-4]:"OFFSET_MISMATCH",[-5]:"NULL_CHILD",[-6]:"NON_FINITE_COORDINATE",[-7]:"COORDINATE_OUT_OF_RANGE",[-8]:"RING_NOT_CLOSED",[-9]:"RESOURCE_LIMIT",[-11]:"HOLE_OUTSIDE_SHELL",[-12]:"DEGENERATE_GEOMETRY",[-14]:"NULL_FEATURE_NOT_EMPTY"};
for(const c of golden.cases.filter(c=>c.descriptor)) {
 test(`native/wasm32 golden: ${c.name}`,async()=>{
   const desc=descriptor(c),wasm=await instance();
   try {
    const got=wasm.run(encodeWasmGeoDescriptor(desc),1,3);
    if(c.status===0){
      const handle=geoColumnNew(desc);
      try {assert.deepEqual(got.output,geoColumnMetadata(handle));} finally {geoColumnFree(handle);}
      assert.equal(got.status,0);assert.equal(Buffer.from(got.output).toString("hex"),c.metadata_hex);
    }else{
      let native;try{const handle=geoColumnNew(desc);geoColumnFree(handle);assert.fail("native accepted malformed geometry");}catch(error){native=error;}
      assert.equal(native.nativeCode,c.status);assert.equal(got.status,c.status===-9?3:2);assert.equal(got.error,`XYG_GEO_${codes[c.status]}`);assert.equal(got.output.length,0);
    }
   }finally{wasm.dispose();}
 });
}
test("bounded peak, framing rejection, cancellation, stale sequence, recovery and disposal",async()=>{
 const request=encodeWasmGeoDescriptor(descriptor(golden.cases.find(c=>c.status===0)));
 const wasm=await instance();
 try{
  assert.equal(wasm.run(request,1).status,0);
  assert.equal(wasm.run(request,1).status,7);
  assert.equal(wasm.x.xyg_wasm_cancel(wasm.h,2),0);assert.equal(wasm.run(request,2).status,6);
  for(const invalid of [request.slice(0,-1),request.slice(0,63)]) {
    const got=wasm.run(invalid,3+(invalid.byteLength===63?1:0));assert.equal(got.status,2);assert.equal(got.error,"XYG_GEO_INVALID_ARGUMENT");assert.equal(got.output.length,0);
  }
  assert.equal(wasm.run(request,5).status,0);
 }finally{wasm.dispose();}
 assert.equal(wasm.x.xyg_wasm_geo_column_ingest(wasm.h,6,0,0),1);
 const bounded=await instance(request.byteLength);
 try{const got=bounded.run(request);assert.equal(got.status,3);assert.equal(got.error,"XYG_GEO_RESOURCE_LIMIT");assert.equal(got.output.length,0);}finally{bounded.dispose();}
});
test("untrusted header lengths, flags, trailing bytes and padding fail before allocation",async()=>{
 const base=encodeWasmGeoDescriptor(descriptor(golden.cases.find(c=>c.status===0))),wasm=await instance();
 try{
  let sequence=0;
  const mutate=(offset,value)=>{const bytes=base.slice(0);new DataView(bytes).setUint32(offset,value,true);return bytes;};
  const tail=new Uint8Array(base.byteLength+8);tail.set(new Uint8Array(base));
  for(const bytes of [mutate(16,2),mutate(20,1),mutate(24,0xffffffff),mutate(28,0xffffffff),tail.buffer]){
   const got=wasm.run(bytes,++sequence);assert.ok([2,3].includes(got.status));assert.equal(got.output.length,0);
  }
 }finally{wasm.dispose();}
});

test("all-null source accounts for generated u64 identities before allocation",async()=>{
 const request=encodeWasmGeoDescriptor({geometry:1,crs:4326,xy:new Float64Array(),validity:new Uint8Array(1024)});
 const wasm=await instance(10000);
 try{const got=wasm.run(request);assert.equal(got.status,3);assert.equal(got.error,"XYG_GEO_RESOURCE_LIMIT");assert.equal(got.output.length,0);}finally{wasm.dispose();}
});
