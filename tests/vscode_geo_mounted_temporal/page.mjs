import {XygGeoHostView} from '../../packages/xy-client/dist/index.js';
const vscode=acquireVsCodeApi(),listeners=new Set();
const view=new XygGeoHostView(document.getElementById('chart'),{
 send:(message,buffers)=>vscode.postMessage({message,buffers}),
 onMessage:callback=>{listeners.add(callback);return()=>listeners.delete(callback);},
});
window.addEventListener('message',async event=>{
 const envelope=event.data;
 if(!envelope.action){for(const callback of listeners)callback(envelope.message,envelope.buffers||[]);return;}
 const request=envelope.request;
 try{
  await view.ready;
  if(envelope.action==='camera'){
   const i=view.identity;await view.update({operation:3,args:[40,0],sequence:i.sequence+1n,cameraRevision:i.cameraRevision+1n,timeRevision:i.timeRevision,stateRevision:i.stateRevision,time:i.time});
  }
  if(envelope.action==='empty'){
   if(view.identity.time.kind!==2||view.identity.time.start!==100000n||view.identity.time.end!==100001n)throw Error('exact range mismatch');
  }else{
   if(view.record(0).featureId!==18446744073709551615n)throw Error('full-u64 identity mismatch');
   const hits=await view.pick({x:400,y:300,tolerance:100,mode:1,maxHits:10});
   if(!hits.records.some(h=>h.featureId===18446744073709551615n))throw Error('native exact pick mismatch');
  }
  await new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)));
  const paint=view.view;paint._drawNow();const canvas=paint.canvas;let pixels;
  if(paint._glHost)pixels=paint._present2d.getImageData(0,0,canvas.width,canvas.height).data;
  else{const gl=paint.gl;pixels=new Uint8Array(gl.drawingBufferWidth*gl.drawingBufferHeight*4);gl.readPixels(0,0,gl.drawingBufferWidth,gl.drawingBufferHeight,gl.RGBA,gl.UNSIGNED_BYTE,pixels);}
  let colored=0,xsum=0;for(let i=0;i<pixels.length;i+=4)if(pixels[i+3]&&Math.max(pixels[i],pixels[i+1],pixels[i+2])-Math.min(pixels[i],pixels[i+1],pixels[i+2])>30){colored++;xsum+=(i/4)%canvas.width;}
  if(envelope.action==='empty'?colored!==0:colored===0)throw Error('unexpected actual framebuffer occupancy');
  vscode.postMessage({test:'mounted-temporal',request,ok:true,coloredPixels:colored,centroid:colored?xsum/colored:null});
 }catch(error){vscode.postMessage({test:'mounted-temporal',request,ok:false,error:error.message,stack:error.stack});}
});
view.ready.then(()=>vscode.postMessage({test:'mounted-ready',phase:document.body.dataset.phase}),error=>vscode.postMessage({test:'mounted-error',error:error.message}));
