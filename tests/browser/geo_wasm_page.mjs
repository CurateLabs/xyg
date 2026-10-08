// Strict-CSP native-golden descriptor ingest through the packaged browser Worker.
import {createXygWasmWorker,encodeWasmGeoDescriptor} from "/packages/xy-client/dist/index.js";
try {
 const golden=await(await fetch("/tests/fixtures/geo_cross_host.json")).json();
 const kinds={point:1,linestring:2,polygon:3,multipoint:4,multilinestring:5,multipolygon:6};
 const worker=createXygWasmWorker({workerUrl:"/packages/xy-client/dist/wasm-worker.js",wasm:"/packages/xy-client/dist/xyg-wasm.wasm",maxArenaBytes:8<<20,evidenceCapability:"geocolumn-stream-supersession-proof"});
 await worker.ready;
 const desc=c=>({geometry:kinds[c.extension_name.split(".")[1]],crs:Number(JSON.parse(c.extension_metadata).crs.split(":")[1]),xy:new Float64Array(BigUint64Array.from(c.descriptor.xy,h=>BigInt(`0x${h}`)).buffer),validity:Uint8Array.from(c.descriptor.validity),featureIds:c.descriptor.feature_ids===null?null:BigUint64Array.from(c.descriptor.feature_ids,BigInt),...Object.fromEntries([0,1,2].map(i=>[`offsets${i}`,Uint32Array.from(c.descriptor[`offsets${i}`]??[])]))});
 const hex=bytes=>Array.from(new Uint8Array(bytes),b=>b.toString(16).padStart(2,"0")).join("");
 let compared=0;
 for(const c of golden.cases.filter(c=>c.status===0)) {
  const source=desc(c),request=encodeWasmGeoDescriptor(source),task=worker.geoColumnIngest(request);
  if(request.byteLength!==0)throw Error("request ownership was not transferred");
  if(source.validity.byteLength===0&&c.descriptor.validity.length!==0)throw Error("source ownership was lost");
  const out=await task.result;if(hex(out)!==c.metadata_hex)throw Error(`golden mismatch: ${c.name}`);compared++;
 }
 const c=golden.cases.find(c=>c.status===0),bad=golden.cases.find(c=>c.status===-11);
 let stable;try{await worker.geoColumnIngest(encodeWasmGeoDescriptor(desc(bad))).result;}catch(error){stable=error.code;}
 if(stable!=="XYG_GEO_HOLE_OUTSIDE_SHELL")throw Error(`stable error: ${stable}`);
 const task=worker.geoColumnIngest(encodeWasmGeoDescriptor(desc(c)));task.cancel();
 let cancel;try{await task.result;}catch(error){cancel=error.code;}
 if(cancel!=="XYG_WASM_CANCELLED")throw Error("cancelled task published");
 if(hex(await worker.geoColumnIngest(encodeWasmGeoDescriptor(desc(c))).result)!==c.metadata_hex)throw Error("worker failed recovery");
 const stream=worker.aggregateStream({x:new Float64Array(100000),y:new Float64Array(100000)},{width:4,height:4,x0:-1,x1:1,y0:-1,y1:1});
 // Attach rejection handling before supersession; wait for actual Worker begin.
 const streamResult=stream.result.then(()=>"published",error=>error.code);
 for(let i=0;i<100&&!worker.evidenceStreamObservations().some(o=>o.requestId===stream.requestId&&o.phase==="begin");i++)await new Promise(r=>setTimeout(r,1));
 if(!worker.evidenceStreamObservations().some(o=>o.requestId===stream.requestId&&o.phase==="begin"))throw Error("stream did not enter Rust");
 if(hex(await worker.geoColumnIngest(encodeWasmGeoDescriptor(desc(c))).result)!==c.metadata_hex)throw Error("stream supersession lost geographic metadata");
 if(await streamResult!=="XYG_WASM_CANCELLED"||!worker.evidenceStreamObservations().some(o=>o.requestId===stream.requestId&&o.phase==="cancelled"))throw Error("stream promise/lifecycle was not cancelled");
 const replay=await worker.aggregateStream({x:new Float64Array([0]),y:new Float64Array([0])},{width:4,height:4,x0:-1,x1:1,y0:-1,y1:1}).result;
 if(!(replay.aggregate instanceof ArrayBuffer))throw Error("stream did not recover after geographic supersession");
 const active=worker.geoColumnIngest(encodeWasmGeoDescriptor(desc(c)));worker.dispose();
 let disposed;try{await active.result;}catch(error){disposed=error.code;}
 if(disposed!=="XYG_WASM_DISPOSED")throw Error("dispose allowed publication");
 window.__geo={ok:true,compared,stable,cancel,disposed};
}catch(error){window.__geo={ok:false,message:error.message,code:error.code};}
