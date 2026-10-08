import {createMapLibreGeoLayer, withExternalGLState, createXygWasmWorker, encodeWasmGeoSceneRequest, hydrateWasmPainter} from "/probe.js";
import * as maplibregl from "/maplibre-gl.mjs";
const assert = (condition, message) => { if (!condition) throw Error(message); };
const pause = ms => new Promise(resolve => setTimeout(resolve, ms));
try {
  const worker = createXygWasmWorker({workerUrl:"/wasm-worker.js",wasm:"/xyg-wasm.wasm",maxArenaBytes:8<<20});
  await worker.ready;
  const id = 0xffffffffffffffffn;
  const source = {geometry:1,crs:4326,xy:Float64Array.of(0,0),validity:Uint8Array.of(1),featureIds:BigUint64Array.of(id)};
  const camera = {centerX:0,centerY:0,zoom:0,width:800,height:600,worldWrap:true,diameter:24,strokeWidth:0,fillRgba:Uint8Array.of(255,0,0,255)};
  const scene = await worker.geoSceneCompile(encodeWasmGeoSceneRequest(source,camera)).result;
  const prepared = await worker.prepareScene(scene).result;
  // Attached generic hydration must preserve Rust's resolved alpha too.
  // Deleting the explicit opacity demonstrates the inherited chart default.
  const alphaScene = await worker.geoSceneCompile(encodeWasmGeoSceneRequest(source,{...camera,fillRgba:Uint8Array.of(255,0,0,128)})).result;
  const alphaPrepared = await worker.prepareScene(alphaScene).result;
  const alphaPixels=[];
  for(const [input,expected,legacy] of [[prepared,[255,0,0,255],[204,0,0,204]],[alphaPrepared,[128,0,0,128],[102,0,0,102]]]){
    const host=document.createElement("div");host.style.cssText="width:800px;height:600px";document.body.append(host);
    const ordinary=hydrateWasmPainter(host,input),rgba=new Uint8Array(4),context=ordinary.gl;
    ordinary._drawNow();context.readPixels(400,300,1,1,context.RGBA,context.UNSIGNED_BYTE,rgba);
    assert(Array.from(rgba).every((v,i)=>v===expected[i]),`generic resolved alpha differs: ${rgba}`);
    delete ordinary.gpuTraces[0].trace.style.opacity;ordinary._drawNow();context.readPixels(400,300,1,1,context.RGBA,context.UNSIGNED_BYTE,rgba);
    assert(Array.from(rgba).every((v,i)=>v===legacy[i]),`legacy alpha proof differs: ${rgba}`);
    alphaPixels.push({resolved:expected,legacy});ordinary.destroy();host.remove();
  }
  const canvas = document.createElement("canvas");canvas.width=800;canvas.height=600;document.body.append(canvas);
  const gl=canvas.getContext("webgl2",{preserveDrawingBuffer:true,antialias:false});assert(gl,"WebGL2 required");
  const caps=[gl.BLEND,gl.CULL_FACE,gl.DEPTH_TEST,gl.STENCIL_TEST,gl.SCISSOR_TEST,gl.POLYGON_OFFSET_FILL,gl.RASTERIZER_DISCARD,gl.SAMPLE_ALPHA_TO_COVERAGE,gl.SAMPLE_COVERAGE,gl.DITHER];
  const names=[gl.CURRENT_PROGRAM,gl.VERTEX_ARRAY_BINDING,gl.ARRAY_BUFFER_BINDING,gl.ELEMENT_ARRAY_BUFFER_BINDING,gl.PIXEL_PACK_BUFFER_BINDING,gl.PIXEL_UNPACK_BUFFER_BINDING,gl.DRAW_FRAMEBUFFER_BINDING,gl.READ_FRAMEBUFFER_BINDING,gl.RENDERBUFFER_BINDING,gl.ACTIVE_TEXTURE,gl.VIEWPORT,gl.SCISSOR_BOX,gl.COLOR_WRITEMASK,gl.COLOR_CLEAR_VALUE,gl.BLEND_SRC_RGB,gl.BLEND_DST_RGB,gl.BLEND_SRC_ALPHA,gl.BLEND_DST_ALPHA,gl.BLEND_EQUATION_RGB,gl.BLEND_EQUATION_ALPHA,gl.BLEND_COLOR,gl.DEPTH_WRITEMASK,gl.PACK_ALIGNMENT,gl.PACK_ROW_LENGTH,gl.PACK_SKIP_PIXELS,gl.PACK_SKIP_ROWS,gl.UNPACK_ALIGNMENT,gl.UNPACK_ROW_LENGTH,gl.UNPACK_IMAGE_HEIGHT,gl.UNPACK_SKIP_PIXELS,gl.UNPACK_SKIP_ROWS,gl.UNPACK_SKIP_IMAGES,gl.UNPACK_FLIP_Y_WEBGL,gl.UNPACK_PREMULTIPLY_ALPHA_WEBGL,gl.UNPACK_COLORSPACE_CONVERSION_WEBGL];
  const snapshot=()=>{
    const active=gl.getParameter(gl.ACTIVE_TEXTURE),textures=[];
    for(let i=0;i<4;i++){gl.activeTexture(gl.TEXTURE0+i);textures.push(gl.getParameter(gl.TEXTURE_BINDING_2D),gl.getParameter(gl.SAMPLER_BINDING));}gl.activeTexture(active);
    const attrs=[],vao=gl.getParameter(gl.VERTEX_ARRAY_BINDING);
    const captureAttributes=()=>{
      attrs.push(gl.getParameter(gl.ELEMENT_ARRAY_BUFFER_BINDING));
      for(let i=0;i<gl.getParameter(gl.MAX_VERTEX_ATTRIBS);i++){
        for(const name of [gl.CURRENT_VERTEX_ATTRIB,gl.VERTEX_ATTRIB_ARRAY_ENABLED,gl.VERTEX_ATTRIB_ARRAY_DIVISOR,gl.VERTEX_ATTRIB_ARRAY_BUFFER_BINDING,gl.VERTEX_ATTRIB_ARRAY_SIZE,gl.VERTEX_ATTRIB_ARRAY_TYPE,gl.VERTEX_ATTRIB_ARRAY_NORMALIZED,gl.VERTEX_ATTRIB_ARRAY_STRIDE])attrs.push(gl.getVertexAttrib(i,name));
        attrs.push(gl.getVertexAttribOffset(i,gl.VERTEX_ATTRIB_ARRAY_POINTER));
      }
    };
    captureAttributes();gl.bindVertexArray(null);captureAttributes();gl.bindVertexArray(vao);
    return [...names.map(name=>gl.getParameter(name)),...caps.map(name=>gl.isEnabled(name)),...textures,...attrs];
  };
  const same=(a,b)=>a.length===b.length&&a.every((v,i)=>ArrayBuffer.isView(v)||Array.isArray(v)?Array.from(v).every((n,j)=>Object.is(n,b[i][j])):Object.is(v,b[i]));
  let checked=0;
  const unchanged=(name,action)=>{const before=snapshot();const result=action();assert(same(before,snapshot()),`${name}: foreign GL state changed`);assert(gl.getError()===gl.NO_ERROR,`${name}: GL error`);checked++;return result;};
  const createTarget=color=>{
    const fb=gl.createFramebuffer(),tex=gl.createTexture();gl.bindTexture(gl.TEXTURE_2D,tex);gl.texImage2D(gl.TEXTURE_2D,0,gl.RGBA8,800,600,0,gl.RGBA,gl.UNSIGNED_BYTE,null);gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_MIN_FILTER,gl.NEAREST);
    gl.bindFramebuffer(gl.FRAMEBUFFER,fb);gl.framebufferTexture2D(gl.FRAMEBUFFER,gl.COLOR_ATTACHMENT0,gl.TEXTURE_2D,tex,0);assert(gl.checkFramebufferStatus(gl.FRAMEBUFFER)===gl.FRAMEBUFFER_COMPLETE,"test framebuffer incomplete");gl.clearColor(...color);gl.clear(gl.COLOR_BUFFER_BIT);return fb;
  };
  gl.bindFramebuffer(gl.FRAMEBUFFER,null);gl.clearColor(0,0,1,1);gl.clear(gl.COLOR_BUFFER_BIT);
  const draw=createTarget([0,1,0,1]),read=createTarget([1,1,0,1]);
  const foreignProgram=gl.createProgram();
  for(const [type,text] of [[gl.VERTEX_SHADER,"#version 300 es\nvoid main(){gl_Position=vec4(0,0,0,1);}"],[gl.FRAGMENT_SHADER,"#version 300 es\nprecision highp float; uniform vec4 u_owner; out vec4 color; void main(){color=u_owner;}"]]){
    const shader=gl.createShader(type);gl.shaderSource(shader,text);gl.compileShader(shader);assert(gl.getShaderParameter(shader,gl.COMPILE_STATUS),gl.getShaderInfoLog(shader));gl.attachShader(foreignProgram,shader);gl.deleteShader(shader);
  }
  gl.linkProgram(foreignProgram);assert(gl.getProgramParameter(foreignProgram,gl.LINK_STATUS),gl.getProgramInfoLog(foreignProgram));gl.useProgram(foreignProgram);
  const ownerUniform=gl.getUniformLocation(foreignProgram,"u_owner");gl.uniform4f(ownerUniform,.2,.3,.4,.5);
  const vao=gl.createVertexArray();gl.bindVertexArray(vao);
  const buffer=gl.createBuffer();gl.bindBuffer(gl.ARRAY_BUFFER,buffer);gl.bufferData(gl.ARRAY_BUFFER,new Float32Array(16),gl.STATIC_DRAW);gl.enableVertexAttribArray(3);gl.vertexAttribPointer(3,2,gl.FLOAT,false,16,8);gl.vertexAttribDivisor(3,7);gl.vertexAttrib4f(4,.2,.3,.4,.5);gl.vertexAttribI4i(5,1,2,3,4);
  const element=gl.createBuffer();gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER,element);gl.bufferData(gl.ELEMENT_ARRAY_BUFFER,32,gl.STATIC_DRAW);
  for(const target of [gl.PIXEL_PACK_BUFFER,gl.PIXEL_UNPACK_BUFFER]){gl.bindBuffer(target,gl.createBuffer());gl.bufferData(target,128,gl.STATIC_DRAW);}
  const renderbuffer=gl.createRenderbuffer();gl.bindRenderbuffer(gl.RENDERBUFFER,renderbuffer);
  for(let i=0;i<4;i++){gl.activeTexture(gl.TEXTURE0+i);gl.bindTexture(gl.TEXTURE_2D,gl.createTexture());gl.bindSampler(i,gl.createSampler());}
  gl.activeTexture(gl.TEXTURE3);gl.bindFramebuffer(gl.DRAW_FRAMEBUFFER,draw);gl.bindFramebuffer(gl.READ_FRAMEBUFFER,read);
  for(const cap of caps)gl.enable(cap);
  gl.colorMask(false,true,false,true);gl.depthMask(true);gl.viewport(3,4,501,402);gl.scissor(7,8,21,22);gl.clearColor(.1,.2,.3,.4);gl.blendColor(.4,.3,.2,.1);gl.blendFuncSeparate(gl.SRC_ALPHA,gl.ONE,gl.DST_ALPHA,gl.ZERO);gl.blendEquationSeparate(gl.FUNC_REVERSE_SUBTRACT,gl.FUNC_SUBTRACT);
  for(const name of [gl.PACK_ALIGNMENT,gl.UNPACK_ALIGNMENT])gl.pixelStorei(name,8);
  for(const name of [gl.PACK_ROW_LENGTH,gl.UNPACK_ROW_LENGTH,gl.UNPACK_IMAGE_HEIGHT])gl.pixelStorei(name,9);
  for(const name of [gl.PACK_SKIP_PIXELS,gl.PACK_SKIP_ROWS,gl.UNPACK_SKIP_PIXELS,gl.UNPACK_SKIP_ROWS,gl.UNPACK_SKIP_IMAGES])gl.pixelStorei(name,2);
  gl.pixelStorei(gl.UNPACK_FLIP_Y_WEBGL,true);gl.pixelStorei(gl.UNPACK_PREMULTIPLY_ALPHA_WEBGL,true);
  const realGet=HTMLCanvasElement.prototype.getContext;let extraContexts=0;
  HTMLCanvasElement.prototype.getContext=function(kind,...args){if(kind.startsWith("webgl"))extraContexts++;return realGet.call(this,kind,...args);};
  let scheduled=0,moves=0;const listeners=new Map();
  const shell={getCanvas:()=>canvas,triggerRepaint:()=>scheduled++,on:(type,fn)=>listeners.set(type,fn),off:(type,fn)=>{if(listeners.get(type)===fn)listeners.delete(type);}};
  const layer=createMapLibreGeoLayer({id:"geo",prepared,onCameraEvent:()=>moves++});
  unchanged("construction",()=>layer.onAdd(shell,gl));
  assert(canvas.width===800&&canvas.height===600&&extraContexts===0,"layer resized canvas or acquired a WebGL context");
  const pixel=(fb,x,y)=>withExternalGLState(gl,()=>{gl.bindFramebuffer(gl.READ_FRAMEBUFFER,fb);const p=new Uint8Array(4);gl.readPixels(x,y,1,1,gl.RGBA,gl.UNSIGNED_BYTE,p);return Array.from(p);});
  assert(pixel(draw,400,300)[1]===255,"constructor painted outside shell scheduling");
  unchanged("draw",()=>layer.render(gl,{}));
  assert(pixel(draw,400,300)[0]>240&&pixel(draw,10,10)[1]===255,`borrowed framebuffer paint or basemap preservation failed: ${JSON.stringify([pixel(draw,400,300),pixel(draw,10,10)])}`);
  assert(pixel(null,400,300)[2]===255&&pixel(read,400,300)[1]===255,"foreign read/default framebuffer changed");
  assert(unchanged("pick",()=>layer.pick(400,300))===id,"point source identity changed");
  unchanged("replacement",()=>layer.setPrepared(prepared));
  const createVao=gl.createVertexArray;let allocations=0;
  gl.createVertexArray=function(){return ++allocations===2?null:createVao.call(this);};
  unchanged("failed vertex array allocation",()=>{try{layer.setPrepared(prepared);throw Error("allocation failure missing");}catch(e){assert(e.message==="xy: vertex array allocation failed","wrong allocation error");}});
  gl.createVertexArray=createVao;
  unchanged("failed replacement",()=>{try{layer.setPrepared({...prepared,painter:new ArrayBuffer(4)});throw Error("bad painter accepted");}catch(e){assert(e.message!=="bad painter accepted","bad painter accepted");}});
  unchanged("thrown callback",()=>{try{withExternalGLState(gl,()=>{gl.bindFramebuffer(gl.FRAMEBUFFER,null);gl.viewport(0,0,1,1);throw Error("injected");});}catch(e){assert(e.message==="injected","wrong injected error");}});
  const bufferData=gl.bufferData;let uploads=0;
  const pending=new Set(),resourceMethods=[];
  for(const kind of ["Buffer","Texture","Framebuffer","VertexArray","Program","Shader"]){
    for(const prefix of ["create","delete"]){
      const method=prefix+kind,original=gl[method];resourceMethods.push([method,original]);
      gl[method]=function(...args){const result=original.apply(this,args);if(prefix==="create"&&result)pending.add(result);if(prefix==="delete")pending.delete(args[0]);return result;};
    }
  }
  gl.bufferData=function(...args){if(++uploads===3)throw Error("injected upload failure");return bufferData.apply(this,args);};
  unchanged("failed upload",()=>{try{layer.setPrepared(prepared);throw Error("failure missing");}catch(e){assert(e.message==="injected upload failure","wrong upload error");}});
  gl.bufferData=bufferData;
  for(const [method,original] of resourceMethods)gl[method]=original;
  assert(pending.size===0,"failed upload leaked owned GL objects");
  unchanged("surviving draw",()=>layer.render(gl,{}));assert(unchanged("surviving pick",()=>layer.pick(400,300))===id,"failed upload replaced the prior scene");
  listeners.get("move")?.({});assert(moves===1,"camera event not forwarded");
  unchanged("destruction",()=>layer.onRemove());assert(!gl.isContextLost()&&listeners.size===0&&extraContexts===0,"removal damaged the shell or leaked listener");
  assert(Array.from(gl.getUniform(foreignProgram,ownerUniform)).every((v,i)=>Math.abs(v-[.2,.3,.4,.5][i])<1e-6),"owner program uniforms changed");
  unchanged("reattach",()=>layer.onAdd(shell,gl));
  const lose=gl.getExtension("WEBGL_lose_context");assert(lose,"context loss extension required");
  canvas.addEventListener("webglcontextlost",event=>event.preventDefault());
  const lost=new Promise(resolve=>canvas.addEventListener("webglcontextlost",resolve,{once:true}));lose.loseContext();await lost;
  assert(layer.pick(400,300)===null,"lost context remained pickable");layer.onRemove();assert(listeners.size===0,"lost removal leaked listener");
  const restored=new Promise(resolve=>canvas.addEventListener("webglcontextrestored",resolve,{once:true}));await pause(100);lose.restoreContext();await restored;
  unchanged("attach after owner restore",()=>layer.onAdd(shell,gl));unchanged("draw after owner restore",()=>layer.render(gl,{}));assert(layer.pick(400,300)===id,"restored source identity lost");
  // Remaining mounted through loss also rebuilds solely after owner restore.
  const lostMounted=new Promise(resolve=>canvas.addEventListener("webglcontextlost",resolve,{once:true}));lose.loseContext();await lostMounted;
  const restoredMounted=new Promise(resolve=>canvas.addEventListener("webglcontextrestored",resolve,{once:true}));await pause(100);lose.restoreContext();await restoredMounted;
  unchanged("mounted restoration draw",()=>layer.render(gl,{}));assert(layer.pick(400,300)===id,"mounted restoration source identity lost");
  unchanged("dispose",()=>layer.dispose());assert(!gl.isContextLost()&&extraContexts===0,"dispose lost shell or acquired context");
  HTMLCanvasElement.prototype.getContext=realGet;canvas.remove();

  // Actual pinned MapLibre, blank green basemap, no remote tiles or CDN.
  maplibregl.setWorkerUrl("/maplibre-gl-worker.mjs");
  const container=document.createElement("div");container.style.cssText="width:800px;height:600px;position:relative";document.body.append(container);
  const map=new maplibregl.Map({container,style:{version:8,sources:{},layers:[{id:"base",type:"background",paint:{"background-color":"#00ff00"}}]},center:[0,0],zoom:0,pitch:0,bearing:0,attributionControl:false,canvasContextAttributes:{preserveDrawingBuffer:true,antialias:false}});
  await new Promise((resolve,reject)=>{map.once("load",resolve);map.once("error",event=>reject(event.error));});
  const mapLayer=createMapLibreGeoLayer({id:"actual-map",prepared});let mapGl,frames=0;
  const add=mapLayer.onAdd,render=mapLayer.render;mapLayer.onAdd=(owner,context)=>{mapGl=context;add(owner,context);};mapLayer.render=(context,options)=>{frames++;render(context,options);};
  extraContexts=0;HTMLCanvasElement.prototype.getContext=function(kind,...args){if(kind.startsWith("webgl"))extraContexts++;return realGet.call(this,kind,...args);};
  map.addLayer(mapLayer);await new Promise(resolve=>map.once("idle",resolve));
  assert(frames>0&&extraContexts===0,"MapLibre failed scheduling or layer acquired extra context");
  assert(mapLayer.pick(400,300)===id,"actual MapLibre pick identity failed");
  const mapPixel=(x,y)=>withExternalGLState(mapGl,()=>{mapGl.bindFramebuffer(mapGl.READ_FRAMEBUFFER,null);const p=new Uint8Array(4);mapGl.readPixels(x,y,1,1,mapGl.RGBA,mapGl.UNSIGNED_BYTE,p);return Array.from(p);});
  // Picking uses only its own FBO; the prior color frame remains intact.
  assert(mapPixel(400,300)[0]>240&&mapPixel(10,10)[1]>240,"actual MapLibre basemap/mark pixels failed");
  map.removeLayer(mapLayer.id);assert(!mapGl.isContextLost()&&extraContexts===0,"actual MapLibre removal damaged context");map.remove();HTMLCanvasElement.prototype.getContext=realGet;
  worker.dispose();window.__externalGL={ok:true,stateChecks:checked,extraContexts,fullU64Pick:true,errorRestore:true,failedUploadResources:pending.size,lostRemoval:true,ownerRestore:true,maplibre:"6.13.0",mapFrames:frames,strictCsp:true,alphaPixels};
}catch(error){window.__externalGL={ok:false,message:error.message,stack:error.stack};}
