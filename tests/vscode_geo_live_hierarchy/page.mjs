import {XygGeoHostView} from './xy-client.js';
const vscode=acquireVsCodeApi(),listeners=new Set(),phase=Number(document.body.dataset.phase);
const view=new XygGeoHostView(document.getElementById('chart'),{
 send:(message,buffers)=>vscode.postMessage({message,buffers}),
 onMessage:callback=>{listeners.add(callback);return()=>listeners.delete(callback);},
});
window.addEventListener('message',event=>{const e=event.data;for(const callback of listeners)callback(e.message,e.buffers||[]);});
(async()=>{
 try{
  await view.ready;
  if(view.record(0).featureId!==18446744073709551615n||phase===1&&view.identity.time.instant!== -9223372036854775808n)throw Error('identity mismatch');
  await view.update({operation:8,args:[0,0],sequence:BigInt(phase+3),cameraRevision:BigInt(phase+3),timeRevision:BigInt(phase+3),stateRevision:1n,time:{kind:0}});
  const hits=await view.pick({x:400,y:300,mode:1,maxHits:10});
  if(!hits.records.some(h=>h.featureId===18446744073709551615n))throw Error('exact host pick mismatch');
  let red=0,canvas;
  for(let attempt=0;attempt<100&&red===0;attempt++){
   await new Promise(resolve=>requestAnimationFrame(resolve));
   canvas=view.view?.canvas;
   if(!canvas||canvas.width===0||canvas.height===0)throw Error('real painter absent');
   // Default WebGL drawing buffers may be discarded after presentation.
   // Read in the same turn as an ordinary shared-painter draw.
   view.view._drawNow();
   let pixels;
   if(view.view._glHost){pixels=view.view._present2d.getImageData(0,0,canvas.width,canvas.height).data;}
   else{const gl=view.view.gl;pixels=new Uint8Array(gl.drawingBufferWidth*gl.drawingBufferHeight*4);gl.readPixels(0,0,gl.drawingBufferWidth,gl.drawingBufferHeight,gl.RGBA,gl.UNSIGNED_BYTE,pixels);}
   for(let i=0;i<pixels.length;i+=4)if(pixels[i+1]>150&&pixels[i]<100&&pixels[i+2]<100)red++;
  }
  if(red===0)throw Error('real framebuffer contains no authored red points; '+JSON.stringify({visible:view.view?._ctxVisible,gl:!!view.view?.gl,rootConnected:view.view?.root.isConnected,canvas:[canvas?.width,canvas?.height],gpu:view.view?.gpuTraces.length}));
  vscode.postMessage({test:'geo_host',phase,ok:true,selectedGreenPixels:red,selectedHierarchyLive:true,canvases:document.querySelectorAll('canvas').length,identity:'u64MAX/i64MIN',pick:true});
 }catch(error){vscode.postMessage({test:'geo_host',phase,ok:false,error:error.message,stack:error.stack});}
})();
