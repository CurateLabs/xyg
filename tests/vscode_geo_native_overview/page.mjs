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
  if(document.querySelectorAll('[data-domain-cell]').length!==32||phase===1&&view.identity.time.instant!== -9223372036854775808n)throw Error('overview identity/count companion mismatch');const initialOwner=view.owner.toString();
  await view.update({operation:8,args:[0,0],sequence:BigInt(phase+2),cameraRevision:BigInt(phase+2),timeRevision:BigInt(phase+2),stateRevision:1n,time:{kind:0}});
  let rejected=false;try{view.pick({x:400,y:300});}catch{rejected=true;}if(!rejected)throw Error('overview granted feature pick');
  let blue=0,canvas;
  for(let attempt=0;attempt<100&&blue===0;attempt++){
   await new Promise(resolve=>requestAnimationFrame(resolve));
   canvas=view.view?.canvas;
   if(!canvas||canvas.width===0||canvas.height===0)throw Error('real painter absent');
   // Default WebGL drawing buffers may be discarded after presentation.
   // Read in the same turn as an ordinary shablue-painter draw.
   view.view._drawNow();
   let pixels;
   if(view.view._glHost){pixels=view.view._present2d.getImageData(0,0,canvas.width,canvas.height).data;}
   else{const gl=view.view.gl;pixels=new Uint8Array(gl.drawingBufferWidth*gl.drawingBufferHeight*4);gl.readPixels(0,0,gl.drawingBufferWidth,gl.drawingBufferHeight,gl.RGBA,gl.UNSIGNED_BYTE,pixels);}
   for(let i=0;i<pixels.length;i+=4)if(pixels[i+2]>pixels[i]+40&&pixels[i+2]>pixels[i+1])blue++;
  }
  if(blue===0)throw Error('real framebuffer contains no authoblue blue points; '+JSON.stringify({visible:view.view?._ctxVisible,gl:!!view.view?.gl,rootConnected:view.view?.root.isConnected,canvas:[canvas?.width,canvas?.height],gpu:view.view?.gpuTraces.length}));
  vscode.postMessage({test:'geo_host',phase,ok:true,bluePixels:blue,canvases:document.querySelectorAll('canvas').length,identity:'exact u64/i64MIN',domainRows:document.querySelectorAll('[data-domain-cell]').length,initialOwner,noFeaturePick:true});
 }catch(error){vscode.postMessage({test:'geo_host',phase,ok:false,error:error.message,stack:error.stack});}
})();
