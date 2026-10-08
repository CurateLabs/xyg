import {hydrateWasmPainter,withExternalGLState,createMapLibreGeoLayer} from "/probe.js";
import * as maplibregl from "/maplibre-gl.mjs";
const assert=(value,message)=>{if(!value)throw Error(message);};
try {
  const painter=await(await fetch('/painter.bin')).arrayBuffer();
  const prepared={painter,sceneBytes:0,wasmMemoryBytes:0,traceCount:4};
  const canvas=document.createElement('canvas');canvas.width=100;canvas.height=100;document.body.append(canvas);
  const gl=canvas.getContext('webgl2',{preserveDrawingBuffer:true,antialias:false});assert(gl,'WebGL2 required');
  const makeView=(p,ratio=1)=>withExternalGLState(gl,()=>hydrateWasmPainter(document.createElement('div'),{...prepared,painter:p},{workerPrepareMs:0},{gl,pixelRatio:ratio,requestRepaint:()=>{throw Error('constructor must not schedule');}}));
  const view=makeView(painter);
  assert(view.gpuTraces.length===4&&view.gpuTraces[0].n===12,'triangle primitives were fragmented into trace objects');
  assert(view.sceneStableId(0,0)===0xffffffffffffffffn&&view.sceneStableId(0,1)===0xffffffffffffffffn,'repeated full-width feature identity lost');
  assert(view.sceneStableId(0,2)===0x8000000000000001n&&view.sceneStableId(0,3)===0x8000000000000001n&&view.sceneStableId(0,4)===7n,'per-triangle identity lost');
  withExternalGLState(gl,()=>view._renderGlFrame());
  const pixel=(x,y)=>withExternalGLState(gl,()=>{const p=new Uint8Array(4);gl.readPixels(x,99-y,1,1,gl.RGBA,gl.UNSIGNED_BYTE,p);return Array.from(p);});
  const equal=(x,y,expected)=>{const actual=pixel(x,y);assert(actual.every((v,i)=>v===expected[i]),`pixel ${x},${y}: ${actual} expected ${expected}`);return actual;};
  const opaque=equal(25,25,[255,0,0,255]);
  const halfAlpha=equal(65,25,[0,128,0,128]);
  equal(25,65,[0,0,0,0]);equal(15,65,[255,0,0,255]); // authored polygon hole
  equal(55,55,[255,0,0,255]);equal(75,55,[0,255,0,255]);
  equal(55,75,[0,0,128,128]);equal(75,75,[255,255,0,255]); // top-first density RGBA
  equal(20,90,[0,0,128,128]); equal(48,90,[255,0,0,255]);
  assert(view.gpuTraces[2]._cpu.size[0]===12 && view.gpuTraces[2]._cpu.size[1]===2,"Rust diameters were normalized or quantized");
  const smallHit=withExternalGLState(gl,()=>view._pickAt(35,90));
  assert(smallHit&&view.sceneStableId(2,smallHit.index)===42n,"small marker source pick lost");
  let rejected=0;
  const d=300,image=d+64;
  for(const [offset,value] of [[d+4,0],[d+16,0],[d+48,0],[d+56,0],[d+60,47],[image+4,2],[image+48,0],[image+52,0],[image+56,0],[image+60,15],[image+32,1],[d+128+20,1],[d+128+48,0],[d+128+60,0],[d+192+60,1],[d+192+52,0]]) {
    const bad=painter.slice(0);new DataView(bad).setUint32(offset,value,true);
    let failed=false;try{makeView(bad);}catch(error){failed=error.code==='XYG_WASM_MALFORMED_OUTPUT';}
    assert(failed,`malformed descriptor ${offset} accepted`);rejected++;
  }
  const resources=new Set(),methods=[];
  for(const kind of ['Buffer','Texture','Framebuffer','VertexArray','Program','Shader'])for(const prefix of ['create','delete']){
    const name=prefix+kind,original=gl[name];methods.push([name,original]);gl[name]=function(...args){const result=original.apply(this,args);if(prefix==='create'&&result)resources.add(result);if(prefix==='delete')resources.delete(args[0]);return result;};
  }
  const upload=gl.texImage2D;gl.texImage2D=function(){throw Error('injected image upload failure');};
  let failed=false;try{makeView(painter);}catch(error){failed=error.message==='injected image upload failure';}
  gl.texImage2D=upload;for(const[name,original]of methods)gl[name]=original;
  assert(failed&&resources.size===0,`failed image upload leaked ${resources.size} resources`);
  withExternalGLState(gl,()=>view.destroy());assert(!gl.isContextLost(),'destroy lost borrowed context');
  canvas.width=200;canvas.height=200;
  const retina=makeView(painter,2);withExternalGLState(gl,()=>retina._renderGlFrame());
  const pixel2=(x,y)=>withExternalGLState(gl,()=>{const p=new Uint8Array(4);gl.readPixels(x*2,199-y*2,1,1,gl.RGBA,gl.UNSIGNED_BYTE,p);return Array.from(p);});
  assert(pixel2(48,90).every((v,i)=>v===[255,0,0,255][i]),"DPR2 round cap changed");
  assert(pixel2(20,90).every((v,i)=>v===[0,0,128,128][i]),"DPR2 packed marker alpha changed");
  assert(pixel2(35,90)[3]>0&&pixel2(39,90)[3]===0,"DPR2 small marker diameter changed");
  assert(retina.gpuTraces[2]._cpuStyle[2]===2,"DPR baked over Rust CSS style bytes");
  withExternalGLState(gl,()=>retina.destroy());

  const decor=await(await fetch('/decor.bin')).arrayBuffer();
  maplibregl.setWorkerUrl('/maplibre-gl-worker.mjs');
  const container=document.createElement('div');container.style.cssText='width:100px;height:100px;position:relative';document.body.append(container);
  const map=new maplibregl.Map({container,style:{version:8,sources:{},layers:[{id:'base',type:'background',paint:{'background-color':'#00ff00'}}]},center:[0,0],zoom:0,attributionControl:false,canvasContextAttributes:{preserveDrawingBuffer:true,antialias:false}});
  await new Promise((resolve,reject)=>{map.once('load',resolve);map.once('error',event=>reject(event.error));});
  const layer=createMapLibreGeoLayer({id:'decorated',prepared:{...prepared,painter:decor}});
  map.addLayer(layer);await new Promise(resolve=>map.once('idle',resolve));
  const holder=container.querySelector('[data-xy-geo-decorations]');
  assert(holder&&holder.textContent.includes('Feature')&&holder.textContent.includes('Layers')&&holder.textContent.includes('Fill'),'Rust label/legend not visible in map container');
  const legend=holder.querySelector('svg'),label=holder.querySelector('[data-xy-stable-id="18446744073709551615"]');
  assert(legend&&legend.querySelector('text')&&label&&label.style.left==='10px'&&label.style.top==='40px','Rust-final decoration coordinates were not consumed');
  assert(container.querySelectorAll('canvas').length===1,'decorations introduced a second painter canvas');
  const mapGl=map.getCanvas().getContext('webgl2');
  const base=withExternalGLState(mapGl,()=>{const p=new Uint8Array(4);mapGl.readPixels(5,94,1,1,mapGl.RGBA,mapGl.UNSIGNED_BYTE,p);return p;});
  assert(base[1]===255&&base[3]===255,'decorated layer cleared basemap');
  map.removeLayer(layer.id);assert(!container.querySelector('[data-xy-geo-decorations]')&&!mapGl.isContextLost(),'decorated removal leaked DOM or lost owner context');map.remove();
  window.__geoPainter={ok:true,opaque,halfAlpha,hole:true,imageTopFirst:true,fullU64:true,negativeControls:rejected,failedUploadResources:resources.size,rawCssStyles:true,dpr2:true,roundCaps:true,smallMarkerPick:true,mapLibreDecorations:true};
}catch(error){window.__geoPainter={ok:false,message:error.message,stack:error.stack};}
