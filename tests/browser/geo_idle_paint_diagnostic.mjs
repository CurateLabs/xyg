// Diagnostic controls only. No flags or renderer state are changed in normal tests.
import {writeFile} from 'node:fs/promises';
import {gzipSync} from 'node:zlib';
export async function diagnoseIdlePaint(page, directory){
 const report=await page.evaluate(async()=>{
  const digest=async bytes=>Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',bytes)),n=>n.toString(16).padStart(2,'0')).join('');
  const base64=bytes=>{let out='';for(let n=0;n<bytes.length;n+=16384)out+=String.fromCharCode(...bytes.subarray(n,n+16384));return btoa(out);};
  const diff=(a,b)=>{let count=0,max=0;const changes=[];for(let i=0;i<a.length;i++)if(a[i]!==b[i]){count++;max=Math.max(max,Math.abs(a[i]-b[i]));changes.push([i,a[i],b[i]]);}return {count,max,changes};};
  const views=window.views.map(v=>v.view),host=views[0]._glHost;
  if(!host||views.some(v=>v._glHost!==host))throw Error('expected one actual shared host');
  const original=host.render;let captured,mode;
  host.render=function(client,target,w,h,draw){return original.call(this,client,target,w,h,gl=>{
   if(mode==='disable-after-reset')gl.disable(gl.DITHER);
   draw(gl);
   const data=new Uint8Array(w*h*4);gl.readPixels(0,0,w,h,gl.RGBA,gl.UNSIGNED_BYTE,data);
   const program=gl.getParameter(gl.CURRENT_PROGRAM),uniforms={};
   for(let i=0;i<gl.getProgramParameter(program,gl.ACTIVE_UNIFORMS);i++){const info=gl.getActiveUniform(program,i),v=gl.getUniform(program,gl.getUniformLocation(program,info.name));uniforms[info.name]=ArrayBuffer.isView(v)?Array.from(v):v;}
   captured={data,width:w,height:h,dither:gl.isEnabled(gl.DITHER),viewport:Array.from(gl.getParameter(gl.VIEWPORT)),blend:[gl.getParameter(gl.BLEND_SRC_RGB),gl.getParameter(gl.BLEND_DST_RGB)],uniforms,shaders:gl.getAttachedShaders(program).map(s=>gl.getShaderSource(s))};
  });};
  const modes=[];
  try{
   for(mode of ['baseline','disable-after-reset','baseline-restored']){
    const frames=[];
    for(let turn=0;turn<3;turn++){
     const frame=[];
     for(const [id,v] of views.entries()){
      v._drawNow();const gpu=captured,canvas=new Uint8Array(v._present2d.getImageData(0,0,v.canvas.width,v.canvas.height).data);
      const flipped=new Uint8Array(gpu.data.length);for(let y=0;y<gpu.height;y++)flipped.set(gpu.data.subarray(y*gpu.width*4,(y+1)*gpu.width*4),(gpu.height-y-1)*gpu.width*4);
      frame.push({...gpu,data:undefined,gpu:gpu.data,canvas,gpuHash:await digest(gpu.data),canvasHash:await digest(canvas),centerGpu:Array.from(gpu.data.subarray((Math.floor(gpu.height/2)*gpu.width+Math.floor(gpu.width/2))*4,(Math.floor(gpu.height/2)*gpu.width+Math.floor(gpu.width/2))*4+4)),gpuVsCanvas:diff(flipped,canvas)});
     }
     frames.push(frame);
    }
    modes.push({mode,views:views.map((_,id)=>({id,comparisons:[1,2].map(n=>({gpu:diff(frames[0][id].gpu,frames[n][id].gpu),canvas:diff(frames[0][id].canvas,frames[n][id].canvas)})),frames:frames.map((f,n)=>({...f[id],gpu:undefined,canvas:undefined,...id===0?{gpuBase64:base64(f[id].gpu),canvasBase64:base64(f[id].canvas)}:{}}))}))});
   }
  }finally{host.render=original;}
  const copies=[];
  views[0]._drawNow();
  for(const options of [{},{willReadFrequently:false},{willReadFrequently:true}]){
   const canvas=document.createElement('canvas');canvas.width=800;canvas.height=600;
   const target=canvas.getContext('2d',options),frames=[];
   for(let n=0;n<5;n++){
    target.globalCompositeOperation='copy';target.drawImage(host.canvas,0,host.canvas.height-600,800,600,0,0,800,600);
    const first=target.getImageData(0,0,800,600).data,second=target.getImageData(0,0,800,600).data;
    frames.push({first:await digest(first),second:await digest(second)});
   }
   copies.push({options,frames});
  }
  return {modes,copies};
 });
 for(const m of report.modes)for(const view of m.views)for(const [n,frame] of view.frames.entries())for(const plane of ['gpu','canvas']){
  const key=plane+'Base64';if(frame[key]){const name=`${m.mode}-view${view.id}-frame${n}-${plane}.rgba.gz`;await writeFile(directory+'/'+name,gzipSync(Buffer.from(frame[key],'base64')));frame[plane+'Artifact']=name;delete frame[key];}
 }
 await writeFile(directory+'/idle-paint-diagnostic.json',JSON.stringify(report,null,2)+'\n');
 console.log(JSON.stringify({diagnostic:report.modes.map(m=>({mode:m.mode,views:m.views.map(v=>({id:v.id,comparisons:v.comparisons.map(c=>({gpu:c.gpu.count,canvas:c.canvas.count})),hashes:v.frames.map(f=>({gpu:f.gpuHash,canvas:f.canvasHash,dither:f.dither,center:f.centerGpu}))}))}))}));
}
