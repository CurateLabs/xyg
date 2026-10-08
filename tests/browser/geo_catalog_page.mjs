import {createXygWasmWorker,encodeGeoCatalogRequest,decodeGeoCatalogResponse,hydrateWasmPainter} from '/packages/xy-client/dist/index.js';
const worker=createXygWasmWorker({wasm:'/packages/xy-client/dist/xyg-wasm.wasm',workerUrl:'/packages/xy-client/dist/wasm-worker.js',maxArenaBytes:128<<20});
const camera={crs:4326,centerX:0,centerY:0,zoom:0,width:800,height:600,worldWrap:true};
const ids=BigUint64Array.of(0x5859040000000001n,0xffffffffffffffffn);
const points={geometry:1,crs:4326,xy:Float64Array.of(-60,0,60,0),validity:Uint8Array.of(1,1),featureIds:ids};
const line={geometry:2,crs:4326,xy:Float64Array.of(-5,0,5,0),validity:Uint8Array.of(1),featureIds:BigUint64Array.of(ids[1]),offsets0:Uint32Array.of(0,2)};
const polygon={geometry:3,crs:4326,xy:Float64Array.of(-5,-5,5,-5,5,5,-5,5,-5,-5),validity:Uint8Array.of(1),featureIds:BigUint64Array.of(ids[1]),offsets0:Uint32Array.of(0,1),offsets1:Uint32Array.of(0,5)};
try{
 await worker.ready;let compared=0,picks=0;
 for(let kind=1;kind<=7;kind++){
  const source=kind===3||kind===4?line:kind===5||kind===6?polygon:points;
  const layer={layerId:0xffffffffffffffffn,kind,source,style:{fill:Uint8Array.of(255,0,0,255),stroke:Uint8Array.of(255,0,0,255),strokeWidth:kind===3||kind===4?2:0,diameter:12}};
  if(kind===2||kind===6){layer.values=Float64Array.from(source.validity,()=>1);layer.valueDomain=[0,2];layer.colorStops=Uint8Array.of(0,0,255,255,0,0);}if(kind===4)layer.arc={bend:.25,steps:8};if(kind===7)layer.density={columns:8,rows:8};
  const request=encodeGeoCatalogRequest({camera,layers:[layer]}),task=worker.geoCatalogCompile(request);if(request.byteLength!==0||source.xy.byteLength===0)throw Error('catalog ownership');
  const out=decodeGeoCatalogResponse(await task.result);if(out.layers[0].layerId!==0xffffffffffffffffn||out.layers[0].featureIds[0]!==source.featureIds[0])throw Error('literal layer/source identity');
  const prepared=await worker.prepareScene(out.scene).result,host=document.createElement('div');host.style.cssText='width:800px;height:600px';document.body.appendChild(host);const view=hydrateWasmPainter(host,prepared);view._drawNow();
  if(kind===1){for(let i=0;i<2;i++){if(view.sceneStableId(0,i)!==ids[i])throw Error('catalog fullu64 hydration');const hit=view._pickAt(400+(i?1:-1)*512/6,300);if(!hit||view.sceneStableId(view.gpuTraces.findIndex(t=>t.trace.id===hit.trace),hit.index)!==ids[i])throw Error('catalog fullu64GPU pick');picks++;}const gl=view.gl,pixels=new Uint8Array(view.canvas.width*view.canvas.height*4);gl.readPixels(0,0,view.canvas.width,view.canvas.height,gl.RGBA,gl.UNSIGNED_BYTE,pixels);if(!pixels.some((v,i)=>i%4===0&&v===255&&pixels[i+1]===0&&pixels[i+2]===0&&pixels[i+3]===255))throw Error('catalog resolvedpaint');}
  if(kind===7&&out.layers[0].density.featureIndices.length!==2)throw Error('catalog density CSR');view.destroy();host.remove();compared++;
 }
 const req=()=>encodeGeoCatalogRequest({camera,layers:[{layerId:1n,kind:1,source:points}]});
 const pending=worker.pending.size,memory=new WebAssembly.Memory({initial:1});new Uint8Array(memory.buffer).set(new Uint8Array(req()));let transferError;try{worker.geoCatalogCompile(memory.buffer);}catch(e){transferError=e.code;}if(transferError!=='XYG_WASM_INVALID_ARGUMENT'||worker.pending.size!==pending)throw Error('catalog nondetachable transfer leak');
 await worker.geoCatalogCompile(req()).result;
 const cancelled=worker.geoCatalogCompile(req());cancelled.cancel();let cancel;try{await cancelled.result;}catch(e){cancel=e.code;}if(cancel!=='XYG_WASM_CANCELLED')throw Error('catalog cancel');
 await worker.geoCatalogCompile(req()).result;
 const bad=req();new Uint8Array(bad)[96]=1;try{await worker.geoCatalogCompile(bad).result;throw Error('invalid catalog accepted');}catch(e){if(e.code!=='XYG_GEO_INVALID_ARGUMENT')throw e;}
 const interaction=decodeGeoCatalogResponse(await worker.geoCatalogCompile(encodeGeoCatalogRequest({camera,layers:[{layerId:1n,kind:1,source:points}],event:{operation:6,layerId:1n,featureId:0xffffffffffffffffn}})).result);
 if(interaction.focus?.featureId!==0xffffffffffffffffn||interaction.hits[0]?.featureId!==0xffffffffffffffffn||interaction.layers[0].stateFlags[1]!==8)throw Error('catalog interaction fullu64 focus/state');
 await worker.prepareScene(interaction.scene).result;
 await worker.geoCatalogCompile(req()).result;worker.dispose();let disposed;try{worker.geoCatalogCompile(req());}catch(e){disposed=e.code;}if(disposed!=='XYG_WASM_DISPOSED')throw Error('catalog disposal');
 window.__catalog={ok:true,compared,picks,transferError,cancel,disposed};
}catch(error){worker.dispose();window.__catalog={ok:false,code:error?.code,message:error?.message};}
