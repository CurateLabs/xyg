import {createXygWasmWorker,hydrateWasmPainter,createMapLibreGeoLayer} from '/packages/xy-client/dist/index.js';
import {buildOverviewPainterFixture,check,BUDGET} from '/tests/browser/geo_overview_painter_fixture.mjs';
const container=document.createElement('div');document.body.append(container);
const worker=createXygWasmWorker({wasm:'/packages/xy-client/dist/xyg-wasm.wasm',workerUrl:'/packages/xy-client/dist/wasm-worker.js',maxArenaBytes:BUDGET.processorBytes});
let fixture,paint,frozen,view,layer;
function ownedTypedBytes(...roots){const visited=new WeakSet(),buffers=new Set();const walk=v=>{if(!v||typeof v!=='object'||visited.has(v))return;visited.add(v);if(v instanceof ArrayBuffer){buffers.add(v);return;}if(ArrayBuffer.isView(v)){buffers.add(v.buffer);return;}if(Array.isArray(v)){for(const item of v)walk(item);}else if(Object.getPrototypeOf(v)===Object.prototype||Object.getPrototypeOf(v)===null){for(const item of Object.values(v))walk(item);}};for(const v of roots)walk(v);return [...buffers].reduce((n,b)=>n+b.byteLength,0);}

try{
 await worker.ready;fixture=await buildOverviewPainterFixture({source:{execute:r=>worker.geoScaleExecute(r),read:r=>worker.geoScaleRead(r)},snapshot:{execute:r=>worker.geoSnapshotExecute(r),read:r=>worker.geoSnapshotRead(r)}});
 paint=await worker.prepareGeoFrame(fixture.handle,7n).result;view=hydrateWasmPainter(container,paint);
 const gl=view.gl;check(gl&&!gl.isContextLost(),'WebGL2 unavailable');view.draw();await new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)));
 const pixel=(x,y)=>{const c=document.createElement('canvas');c.width=800;c.height=600;const ctx=c.getContext('2d');ctx.fillStyle='white';ctx.fillRect(0,0,800,600);ctx.drawImage(view.canvas,0,0);return [...ctx.getImageData(x,y,1,1).data];};
 const left=pixel(160,284),right=pixel(640,284),empty=pixel(400,284);
 check(left.join(',')==='55,155,255,255'&&right.join(',')==='55,155,255,255','exact domain pixels '+JSON.stringify({left,right,empty,plot:view.plot}));check(empty.join(',')==='255,255,255,255','time-excluded domain cell painted');
 const ids=view.gpuTraces.flatMap((t,i)=>Array.from({length:t._sceneIds.lo.length},(_,row)=>view.sceneStableId(i,row)));
 check(ids.includes(128n)&&ids.includes(143n)&&ids.every(id=>id===128n||id===143n),'explicit domain ordinals');check(container.textContent.includes('spatial refinement pending'),'nonfinal label');
 let bad=paint.painter.slice(0);new Uint8Array(bad)[0]=0;let rejected=false;try{hydrateWasmPainter(document.createElement('div'),{...paint,painter:bad});}catch{rejected=true;}check(rejected,'malformed staging negative control');bad=undefined;view.draw();await new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)));check(pixel(160,284).join(',')===left.join(','),'old paint lost');
 frozen=await fixture.freeze();check(new DataView(frozen.bytes).getUint32(4,true)===4,'v4 absent');frozen.bytes=undefined;await frozen.dispose();frozen=undefined;
 let stale=false;try{await worker.prepareGeoFrame(fixture.handle,6n).result;}catch{stale=true;}check(stale,'stale painter accepted');
 check(view.plot.w===800&&view.plot.h===600,'overview projection viewport changed');
 const receipt={ok:true,pixels:{left,right,empty},ordinals:['128','143'],nonfinal:true,malformedStageOldPaint:true,staleRejected:true,records:paint.records,styles:paint.styles,painterBytes:paint.painter.byteLength,typedBytes:ownedTypedBytes(view.gpuTraces,view._payload,paint.painter,fixture.packet)};
 view.destroy();view=undefined;
 const foreignCanvas=document.createElement('canvas'),foreignHolder=document.createElement('div');foreignCanvas.width=800;foreignCanvas.height=600;foreignCanvas.style.cssText='width:800px;height:600px';foreignHolder.style.cssText='position:relative;width:800px;height:600px';foreignHolder.append(foreignCanvas);document.body.append(foreignHolder);
 const foreignGl=foreignCanvas.getContext('webgl2',{preserveDrawingBuffer:true,antialias:false});check(foreignGl,'borrowed WebGL2 unavailable');layer=createMapLibreGeoLayer({id:'overview-full-viewport'});layer.onAdd({getCanvas:()=>foreignCanvas,getContainer:()=>foreignHolder,triggerRepaint:()=>{}},foreignGl);layer.setPrepared(paint);foreignGl.viewport(0,0,800,600);foreignGl.clearColor(1,1,1,1);foreignGl.clear(foreignGl.COLOR_BUFFER_BIT);layer.render(foreignGl,{});
 const borrowedPixel=(x,y)=>{const b=new Uint8Array(4);foreignGl.readPixels(x,600-y,1,1,foreignGl.RGBA,foreignGl.UNSIGNED_BYTE,b);return [...b];};
 check(borrowedPixel(160,284).join(',')===left.join(',')&&borrowedPixel(640,284).join(',')===right.join(','),'borrowed projection pixels differ');check(layer.pick(160,284)===null,'domain cells gained source picking');receipt.sourcePickingUnavailable=true;check(foreignHolder.textContent.includes('spatial refinement pending'),'borrowed exact notice missing');receipt.borrowedFullViewport=true;
 layer.releasePrepared();layer.dispose();layer=undefined;paint=undefined;fixture.scene=undefined;await fixture.dispose();fixture=undefined;await worker.dispose();window.__overviewPainter=receipt;
}catch(error){window.__overviewPainter={ok:false,error:error.stack??String(error)};}
finally{if(frozen){frozen.bytes=undefined;await frozen.dispose();}if(view)view.destroy();if(layer){layer.releasePrepared();layer.dispose();}view=layer=paint=undefined;if(fixture){fixture.scene=undefined;await fixture.dispose();}await worker.dispose();}
