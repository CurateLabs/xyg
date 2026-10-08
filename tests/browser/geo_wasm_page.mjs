// Strict-CSP native-golden descriptor ingest through the packaged browser Worker.
import {createXygWasmWorker,encodeWasmGeoDescriptor,encodeWasmGeoSceneRequest,encodeGeoViewportRequest,encodeGeoViewportColumnRequest,decodeGeoViewportResponse,hydrateWasmPainter} from "/packages/xy-client/dist/index.js";
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
 const camera={centerX:0,centerY:0,zoom:0,width:800,height:600,worldWrap:true,diameter:12,strokeWidth:0,fillRgba:Uint8Array.of(255,0,0,255)};
 const ids=BigUint64Array.of(0x5859040000000001n,0xffffffffffffffffn);
 const sceneSource={geometry:1,crs:4326,xy:Float64Array.of(-60,0,60,0),validity:Uint8Array.of(1,1),featureIds:ids};
 const sceneRequest=encodeWasmGeoSceneRequest(sceneSource,camera),sceneTask=worker.geoSceneCompile(sceneRequest);
 if(sceneRequest.byteLength!==0||sceneSource.xy.byteLength!==32)throw Error("scene source/transfer ownership");
 const scene=await sceneTask.result,prepared=await worker.prepareScene(scene).result;
 const host=document.createElement("div");host.style.cssText="width:800px;height:600px";document.body.appendChild(host);
 const view=hydrateWasmPainter(host,prepared);view._drawNow();
 for(let i=0;i<2;i++){
  if(view.sceneStableId(0,i)!==ids[i])throw Error("full u64 scene identity lost in hydration");
  const hit=view._pickAt(400+(i?1:-1)*512/6,300);
  if(!hit||view.sceneStableId(view.gpuTraces.findIndex(t=>t.trace.id===hit.trace),hit.index)!==ids[i])throw Error(`full u64 scene identity lost in GPU picking: ${JSON.stringify({hit:hit?{trace:hit.trace,index:hit.index}:null,plot:view.plot,traces:view.gpuTraces.map(t=>({id:t.trace.id,n:t.pickCount}))})}`);
 }
 const gl=view.gl,pixels=new Uint8Array(view.canvas.width*view.canvas.height*4);view._drawNow();gl.readPixels(0,0,view.canvas.width,view.canvas.height,gl.RGBA,gl.UNSIGNED_BYTE,pixels);
 let red=0;for(let i=0;i<pixels.length;i+=4)if(pixels[i]>200&&pixels[i+1]<50&&pixels[i+2]<50)red++;
 if(red<100)throw Error("geographic scene did not paint expected pixels");
 if(!pixels.some((v,i)=>i%4===0&&v===255&&pixels[i+1]===0&&pixels[i+2]===0&&pixels[i+3]===255))throw Error("resolved opaque Rust RGBA was dimmed during hydration");
 view.destroy();host.remove();
 const halfScene=await worker.geoSceneCompile(encodeWasmGeoSceneRequest(sceneSource,{...camera,fillRgba:Uint8Array.of(255,0,0,128)})).result;
 const halfPrepared=await worker.prepareScene(halfScene).result;
 const halfHost=document.createElement("div");halfHost.style.cssText="width:800px;height:600px";document.body.appendChild(halfHost);
 const halfView=hydrateWasmPainter(halfHost,halfPrepared);halfView._drawNow();
 const halfPixels=new Uint8Array(halfView.canvas.width*halfView.canvas.height*4),halfGl=halfView.gl;
 halfGl.readPixels(0,0,halfView.canvas.width,halfView.canvas.height,halfGl.RGBA,halfGl.UNSIGNED_BYTE,halfPixels);
 if(!halfPixels.some((v,i)=>i%4===0&&v===128&&halfPixels[i+1]===0&&halfPixels[i+2]===0&&halfPixels[i+3]===128))throw Error("resolved half-alpha Rust RGBA was dimmed during hydration");
 halfView.destroy();halfHost.remove();
 const lineId=0x5859060000000042n;
 const lineScene=await worker.geoSceneCompile(encodeWasmGeoSceneRequest({geometry:2,crs:4326,xy:Float64Array.of(170,-10,-170,10),offsets0:Uint32Array.of(0,2),validity:Uint8Array.of(1),featureIds:BigUint64Array.of(lineId)},{...camera,strokeWidth:2})).result;
 const linePrepared=await worker.prepareScene(lineScene).result;
 const lineHost=document.createElement("div");lineHost.style.cssText="width:800px;height:600px";document.body.appendChild(lineHost);
 const lineView=hydrateWasmPainter(lineHost,linePrepared);lineView._drawNow();
 if(lineView.gpuTraces.length!==2)throw Error("dateline segments reconnected during hydration");
 for(let trace=0;trace<2;trace++)for(let row=0;row<2;row++)if(lineView.sceneStableId(trace,row)!==lineId)throw Error("outline endpoint identity lost");
 lineView.destroy();lineHost.remove();
 const deepSource={geometry:1,crs:4326,xy:Float64Array.of(-180,0,0,0,1e-7,0),validity:Uint8Array.of(1,1,1),featureIds:BigUint64Array.of(1n,ids[0],ids[1])};
 const deepScene=await worker.geoSceneCompile(encodeWasmGeoSceneRequest(deepSource,{...camera,zoom:24,diameter:1})).result;
 const deepPrepared=await worker.prepareScene(deepScene).result;
 const deepHost=document.createElement("div");deepHost.style.cssText="width:800px;height:600px";document.body.appendChild(deepHost);
 const deepView=hydrateWasmPainter(deepHost,deepPrepared),cpu=deepView.gpuTraces[0]._cpu;
 const delta=cpu.x[1]-cpu.x[0];
 if(cpu.x.length!==2||!Number.isFinite(delta)||Math.abs(delta-2.386092942222222)>1e-4)throw Error(`deepzoom separation lost in painter upload: delta=${delta}, n=${cpu.x.length}, meta=${JSON.stringify(cpu.xMeta)}`);
 if(deepView.sceneStableId(0,0)!==ids[0]||deepView.sceneStableId(0,1)!==ids[1])throw Error("deepzoom visible identities lost");
 deepView.destroy();deepHost.remove();
 const sceneCancel=worker.geoSceneCompile(encodeWasmGeoSceneRequest(sceneSource,camera));sceneCancel.cancel();
 let sceneCancelled;try{await sceneCancel.result;}catch(error){sceneCancelled=error.code;}
 if(sceneCancelled!=="XYG_WASM_CANCELLED")throw Error("scene cancellation published");
 await worker.geoSceneCompile(encodeWasmGeoSceneRequest(sceneSource,camera)).result;
 const cameraState={crs:4326,centerX:0,centerY:0,zoom:0,width:800,height:600,worldWrap:true};
 // WASM memory buffers are ArrayBuffers but cannot transfer; failed submission
 // must expose a typed error and retire the otherwise unreachable pending task.
 for(const method of["geoViewportExecute","geoColumnIngest","geoSceneCompile"]){
  const memory=new WebAssembly.Memory({initial:1});
  try{worker[method](memory.buffer);throw Error("non-detachable geographic buffer was accepted");}
  catch(error){if(error.code!=="XYG_WASM_INVALID_ARGUMENT")throw error;}
  if(worker.pending.size!==0)throw Error("failed geographic transfer retained pending task");
 }
 await worker.geoViewportExecute(encodeGeoViewportRequest(cameraState)).result;
 if(hex(await worker.geoColumnIngest(encodeWasmGeoDescriptor(desc(c))).result)!==c.metadata_hex)throw Error("transfer failure broke geographic recovery");
 await worker.geoSceneCompile(encodeWasmGeoSceneRequest(sceneSource,camera)).result;
 // Exercise malformed raw messages on the packaged Worker, beyond proxy guards.
 let rawRequestId=900000;
 const rawCamera=sequence=>new Promise((resolve,reject)=>{
  const requestId=rawRequestId++,request=encodeGeoViewportRequest(cameraState),raw=worker.worker;
  const timer=setTimeout(()=>{raw.removeEventListener("message",receive);reject(Error("raw camera reply timed out"));},5000);
  const receive=event=>{if(event.data.requestId!==requestId)return;clearTimeout(timer);raw.removeEventListener("message",receive);resolve(event.data);};
  raw.addEventListener("message",receive);raw.postMessage({type:"geo.viewport",requestId,sequence,request},[request]);
 });
 const guardedStream=worker.aggregateStream({x:new Float64Array(1000000),y:new Float64Array(1000000)},{width:4,height:4,x0:-1,x1:1,y0:-1,y1:1},{sequence:100000});
 const guardedResult=guardedStream.result.then(()=>"published",error=>error.code);
 for(let i=0;i<100&&!worker.evidenceStreamObservations().some(o=>o.requestId===guardedStream.requestId&&o.phase==="begin");i++)await new Promise(r=>setTimeout(r,1));
 if(!worker.evidenceStreamObservations().some(o=>o.requestId===guardedStream.requestId&&o.phase==="begin"))throw Error("guarded stream did not begin");
 for(const[sequence,code]of[[99999,"XYG_WASM_STALE_SEQUENCE"],[0,"XYG_WASM_INVALID_ARGUMENT"]]){
  const response=await rawCamera(sequence);if(response.ok||response.error?.code!==code)throw Error("stale/zero camera was not rejected before supersession");
  if(worker.evidenceStreamObservations().some(o=>o.requestId===guardedStream.requestId&&o.phase==="cancelled"))throw Error("rejected camera cancelled a newer stream");
 }
 await worker.geoViewportExecute(encodeGeoViewportRequest(cameraState),{sequence:100001}).result;
 if(await guardedResult!=="XYG_WASM_CANCELLED")throw Error("current camera failed to supersede stream");
 // A newer declaration may arrive after camera receipt but before its timer.
 const deferredCamera=rawCamera(100002);
 const newerStream=worker.aggregateStream({x:Float64Array.of(0),y:Float64Array.of(0)},{width:4,height:4,x0:-1,x1:1,y0:-1,y1:1},{sequence:100003});
 const deferredResponse=await deferredCamera;
 if(!deferredResponse.ok&&deferredResponse.error?.code!=="XYG_WASM_STALE_SEQUENCE")throw Error("deferred camera returned an unexpected status");
 if(!(await newerStream.result).aggregate)throw Error("deferred older camera destroyed newer stream");
 const normalizeReq=encodeGeoViewportRequest(cameraState),normalizeTask=worker.geoViewportExecute(normalizeReq);
 if(normalizeReq.byteLength!==0)throw Error("camera request ownership was not transferred");
 const normalizedCamera=decodeGeoViewportResponse(await normalizeTask.result);
 const point=decodeGeoViewportResponse(await worker.geoViewportExecute(encodeGeoViewportRequest(cameraState,1,[10,20])).result);
 const inverse=decodeGeoViewportResponse(await worker.geoViewportExecute(encodeGeoViewportRequest(point.camera,2,point.result)).result);
 if(Math.abs(inverse.result[0]-10)>1e-9||Math.abs(inverse.result[1]-20)>1e-9||normalizedCamera.rebuildKey.length!==64)throw Error("camera inverse/key failed");
 const polygon={geometry:3,crs:4326,xy:Float64Array.of(-170,-80,170,-80,170,80,-170,80,-170,-80),validity:Uint8Array.of(1),featureIds:BigUint64Array.of(ids[1]),offsets0:Uint32Array.of(0,1),offsets1:Uint32Array.of(0,5)};
 const topology=decodeGeoViewportResponse(await worker.geoViewportExecute(encodeGeoViewportColumnRequest({...cameraState,worldWrap:false,zoom:3},polygon)).result);
 if(topology.visibleFeatureIds.length!==1||topology.visibleFeatureIds[0]!==ids[1]||!topology.bounds||!topology.polygonFeatureIds.length||topology.ringIsHole.some(n=>n!==0))throw Error("covering polygon topology/identity lost");
 const cameraCancelled=worker.geoViewportExecute(encodeGeoViewportRequest(cameraState));cameraCancelled.cancel();
 let cameraCancel;try{await cameraCancelled.result;}catch(error){cameraCancel=error.code;}
 if(cameraCancel!=="XYG_WASM_CANCELLED")throw Error("camera cancellation published");
 await worker.geoViewportExecute(encodeGeoViewportRequest(cameraState)).result;
 const active=worker.geoColumnIngest(encodeWasmGeoDescriptor(desc(c)));worker.dispose();
 let disposed;try{await active.result;}catch(error){disposed=error.code;}
 if(disposed!=="XYG_WASM_DISPOSED")throw Error("dispose allowed publication");
 window.__geo={ok:true,compared,stable,cancel,disposed,scenePicks:2,scenePaintPixels:red,outlineSegments:2,sceneCancelled,deepzoomDelta:delta,cameraInverse:true,cameraCancel,polygonFragments:topology.polygonFeatureIds.length};
}catch(error){window.__geo={ok:false,message:error.message,code:error.code};}
