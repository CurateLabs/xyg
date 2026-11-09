// Complementary raw-buffer GPU probe. The controller smoke owns packaged/CSP proof.
import {build} from 'vite';
import {chromium} from 'playwright';
import assert from 'node:assert/strict';
const out=await build({configFile:false,logLevel:'error',build:{write:false,minify:false,lib:{entry:process.cwd()+'/js/src/63_graph_gpu.ts',name:'graphGpuTest',formats:['iife']}}});
const script=(Array.isArray(out)?out:[out]).flatMap(x=>x.output).find(x=>x.type==='chunk').code;
const browser=await chromium.launch({executablePath:process.env.XYG_CHROMIUM || process.env.CHROMIUM,headless:true,args:['--no-sandbox','--use-gl=angle','--use-angle=swiftshader','--enable-unsafe-swiftshader']});
try {
 const page=await browser.newPage(); page.on('console',m=>console.log('browser:',m.text()));
 await page.setContent('<div id="graph"></div>'); await page.addScriptTag({content:script});
 const result=await page.evaluate(async()=>{
  const {decodeGraphGpu,createGraphGpuPainter}=graphGpuTest;
  const s=new Map();
  function put(name,index,dtype,values){const bytes=new Uint8Array(values.buffer,values.byteOffset,values.byteLength);s.set(`${name}#${index}`,{name,index,dtype,count:dtype===2?bytes.length/4:dtype===3||dtype===5?bytes.length/8:bytes.length,bytes});}
  put('gpu.header.u32',0,2,new Uint32Array([1,0,2,2,1,1,1,0]));
  for(let i=0;i<3;i++)put('gpu.transform.f64',i,5,new Float64Array([0,1]));
  for(const [name,columns] of [['node',[[50,150],[80,80]]],['shaft',[[60],[80],[140],[80]]],['head',[[140],[80],[132],[75],[132],[85]]],['frame',[[25],[50],[170],[110]]]])columns.forEach((c,i)=>put(`gpu.${name}.coord.bytes`,i,6,new Float32Array(c)));
  [[3],[0],[0],[0]].forEach((c,i)=>put('gpu.shaft.attr.bytes',i,6,new Float32Array(c)));
  put('gpu.frame.width.bytes',0,6,new Float32Array([1]));
  put('gpu.shaft.edge.u32',0,2,new Uint32Array([1]));put('gpu.shaft.flags.u8',0,1,new Uint8Array([1]));put('gpu.head.piece.u32',0,2,new Uint32Array([0]));put('gpu.frame.node.u32',0,2,new Uint32Array([0]));
  for(const [kind,count] of [['node',2],['edge',2]]){const styles=new Uint8Array(count*60),v=new DataView(styles.buffer);for(let n=0;n<count;n++){const at=n*60;for(const field of [0,4,28,32,36])styles.set(kind==='edge'&&n===1?[200,80,40,255]:[40,80,200,255],at+field);for(const [field,value] of [[12,20],[16,2],[20,1],[40,26],[44,4]])v.setFloat32(at+field,value,true);}put(`gpu.${kind}.style.bytes`,0,6,styles);put(`gpu.${kind}.state.u8`,0,1,new Uint8Array(count*4));}
  put('render.node_x.f64',0,5,new Float64Array(2));put('render.edge_source.u64',0,3,new BigUint64Array(2));
  const allocated=new Map(),proto=WebGL2RenderingContext.prototype;
  for(const name of ['bufferData','texStorage2D','deleteBuffer','deleteTexture']){
   const original=proto[name];proto[name]=function(...args){
    const result=original.apply(this,args);
    if(name==='bufferData')allocated.set(this.getParameter(this.ARRAY_BUFFER_BINDING),this.getBufferParameter(args[0],this.BUFFER_SIZE));
    else if(name==='texStorage2D'){
     if(![this.RGBA8UI,this.R32UI].includes(args[2]))throw Error('unexpected graph oracle texture format');
     allocated.set(this.getParameter(this.TEXTURE_BINDING_2D),args[3]*args[4]*4);
    }else allocated.delete(args[0]);
    return result;
   };
  }
  const gpu=decodeGraphGpu(s);const painter=createGraphGpuPainter(document.querySelector('#graph'));
  const camera=[-2,-3,400,400,240,180,2];painter.paint(gpu,camera);
  const ctx=painter.canvas.getContext('2d'); const before=ctx.getImageData(0,0,480,360).data.slice();
  const pixel=(x,y)=>Array.from(ctx.getImageData(x*2,y*2,1,1).data);
  const center=pixel(50,80),edge=pixel(100,80),head=pixel(138,80),frame=pixel(25,70);
  const host=globalThis[Symbol.for('reflex-dev.xy.shared-webgl-host.v2')].get(document);
  const gl=host.gl;
  const storage=[];
  function account(label){const actual=[...allocated.values()].reduce((sum,n)=>sum+BigInt(n),0n);if(host.storageSnapshot().logicalBytes!==actual)throw Error(label+': driver allocation and ledger differ');storage.push({label,bytes:String(actual)});}
  account('reference');
  // Compare every rendered RGBA byte before Canvas2D readback can change its
  // premultiplication rounding when Chromium switches readback backends.
  function pixels(){const data=new Uint8Array(480*360*4);gl.readPixels(0,0,480,360,gl.RGBA,gl.UNSIGNED_BYTE,data);return data;}
  const rendered=pixels();
  const difference=(left,right)=>{let count=0;for(let i=0;i<left.length;i++)if(left[i]!==right[i])count++;return count;};
  function dirtySamplers(){
   const sampler=gl.createSampler();
   gl.samplerParameteri(sampler,gl.TEXTURE_MIN_FILTER,gl.LINEAR);
   gl.samplerParameteri(sampler,gl.TEXTURE_MAG_FILTER,gl.LINEAR);
   for(let unit=0;unit<5;unit++)gl.bindSampler(unit,sampler);
   return sampler;
  }
  function bindings(){
   const active=gl.getParameter(gl.ACTIVE_TEXTURE),samplers=[],textures=[];
   for(let unit=0;unit<5;unit++){gl.activeTexture(gl.TEXTURE0+unit);samplers.push(gl.getParameter(gl.SAMPLER_BINDING)===null);textures.push(gl.getParameter(gl.TEXTURE_BINDING_2D)===null);}
   gl.activeTexture(active);return{samplers,textures,active:active===gl.TEXTURE0,error:gl.getError()};
  }
  const dirtySampler=dirtySamplers();
  painter.paint(gpu,camera);
  const dirtyDifference=difference(rendered,pixels()),dirtyBindings=bindings();
  gl.deleteSampler(dirtySampler);
  painter.paint(gpu,camera);
  const cleanDifference=difference(rendered,pixels());
  s.get('gpu.node.state.u8#0').bytes[1]=1;painter.paint(decodeGraphGpu(s),camera);
  const after=ctx.getImageData(0,0,480,360).data;let changes=0;for(let i=0;i<after.length;i++)if(after[i]!==before[i])changes++;
  const focused=pixels();
  host.canvas.addEventListener('webglcontextlost',()=>allocated.clear(),{once:true});
  const ext=host.gl.getExtension('WEBGL_lose_context');
  const restored=await new Promise((resolve,reject)=>{const timer=setTimeout(()=>reject(new Error('restore timeout')),5000);host.canvas.addEventListener('webglcontextrestored',()=>{clearTimeout(timer);resolve(true);},{once:true});host.canvas.addEventListener('webglcontextlost',()=>setTimeout(()=>ext.restoreContext(),50),{once:true});ext.loseContext();});
  const restoredPixel=pixel(50,80),restoredDifference=difference(focused,pixels());
  account('reference restored');
  const restoredSampler=dirtySamplers();
  painter.paint(decodeGraphGpu(s),camera);
  const restoredDirtyDifference=difference(focused,pixels()),restoredBindings=bindings();
  gl.deleteSampler(restoredSampler);
  // An offscreen frame forces the reference input binding without contributing
  // pixels. Removing only that frame selects procedural nodes. Compare every
  // GL RGBA byte with all six glyphs, alpha/halo and focus still enabled.
  const bindingParity=[];
  function frameCount(count){
   new DataView(s.get('gpu.header.u32#0').bytes.buffer).setUint32(24,count,true);
   for(let i=0;i<4;i++)put('gpu.frame.coord.bytes',i,6,new Float32Array(count?[100000+(i>1?100:0)]:[]));
   put('gpu.frame.width.bytes',0,6,new Float32Array(count?[1]:[]));
   put('gpu.frame.node.u32',0,2,new Uint32Array(count?[0]:[]));
  }
  const nodeStyle=s.get('gpu.node.style.bytes#0').bytes;
  const draw=gl.drawArrays,draws=[];
  gl.drawArrays=function(...args){draws.push(args);return draw.apply(this,args);};
  for(let shape=0;shape<6;shape++){
   for(let row=0;row<2;row++){
    nodeStyle[row*60+24]=shape;
    nodeStyle.set([40,80,200,117],row*60+32);
    nodeStyle.set([200,80,40,150],row*60+28);
   }
   frameCount(1);painter.paint(decodeGraphGpu(s),camera);const reference=pixels();account('reference glyph '+shape);
   frameCount(0);const dirty=dirtySamplers();painter.paint(decodeGraphGpu(s),camera);gl.deleteSampler(dirty);
   account('procedural glyph '+shape);
   bindingParity.push({shape,difference:difference(reference,pixels()),bindings:bindings()});
  }
  gl.drawArrays=draw;
  {
   if(draws.length!==12 || draws.some(args=>args[0]!==gl.TRIANGLES || args[1]!==0 || args[2]!==12))throw Error('procedural nodes must draw both triangles for every node and focus pass');
  }
  // A coordinate-upload failure must preserve presentation. The next pass
  // resets every used sampler/texture even after the prior pass threw.
  const accepted=ctx.getImageData(0,0,480,360).data.slice();
  const texStorage=gl.texStorage2D;let calls=0,failed=false;
  gl.texStorage2D=function(...args){if(++calls===7)throw Error('injected coordinate upload failure');return texStorage.apply(this,args);};
  try{painter.paint(decodeGraphGpu(s),camera);}catch(error){failed=String(error).includes('injected coordinate upload failure');}finally{gl.texStorage2D=texStorage;}
  if(!failed || difference(accepted,ctx.getImageData(0,0,480,360).data))throw Error('partial upload replaced accepted presentation');
  const failureSampler=dirtySamplers();painter.paint(decodeGraphGpu(s),camera);gl.deleteSampler(failureSampler);
  const failureBindings=bindings();
  account('upload retry');
  const owner=host.dashboardResourceSnapshot().clients[0],saved=pixels();
  owner._applyDashboardResidency(false);account('procedural evicted');
  if(host.clientResourceBytes(owner)!==0n)throw Error('procedural eviction retained client storage');
  owner._applyDashboardResidency(true);await Promise.resolve();account('procedural readmitted');
  if(difference(saved,pixels()))throw Error('procedural eviction/rebuild changed pixels');
  host.canvas.addEventListener('webglcontextlost',()=>allocated.clear(),{once:true});
  const proceduralRestored=await new Promise((resolve,reject)=>{const timer=setTimeout(()=>reject(new Error('procedural restore timeout')),5000);host.canvas.addEventListener('webglcontextrestored',()=>{clearTimeout(timer);resolve(true);},{once:true});host.canvas.addEventListener('webglcontextlost',()=>setTimeout(()=>ext.restoreContext(),50),{once:true});ext.loseContext();});
  account('procedural restored');
  if(!proceduralRestored || difference(saved,pixels()))throw Error('procedural context restore changed pixels');
  const errors=[];for(const mutate of [()=>s.set('gpu.unknown#0',{name:'gpu.unknown',index:0,dtype:1,count:0,bytes:new Uint8Array()}),()=>s.get('gpu.node.style.bytes#0').bytes[57]=1]){mutate();try{decodeGraphGpu(s);errors.push(false);}catch(e){errors.push(e.code==='GF_INTERACTION_INVALID');}s.delete('gpu.unknown#0');}
  // Empty publications need no program, but their storage is resident. A
  // retain callback must not turn every planner delivery into another paint.
  owner._applyDashboardResidency(false);
  const empty=new Map([...s].map(([key,value])=>[key,key.startsWith('gpu.transform.')?value:{...value,bytes:new Uint8Array(),count:0}]));
  const header=new Uint32Array([1,0,0,0,0,0,0,0]);empty.set('gpu.header.u32#0',{...s.get('gpu.header.u32#0'),bytes:new Uint8Array(header.buffer),count:8});
  painter.paint(decodeGraphGpu(empty),camera);account('empty resident');
  const emptyRevision=host.dashboardResourceSnapshot().revision;
  if(!Number.isSafeInteger(emptyRevision))throw Error('missing empty residency revision');
  for(let i=0;i<3;i++){owner._applyDashboardResidency(true);await Promise.resolve();}
  if(host.dashboardResourceSnapshot().revision!==emptyRevision)throw Error('empty resident publication repainted on retain');
  account('empty retained without churn');
  painter.dispose();painter.dispose();if(allocated.size)throw Error('graph teardown retained driver allocations');return{center,edge,head,frame,changes,errors,restored,restoredPixel,dirtyDifference,cleanDifference,dirtyBindings,restoredDifference,restoredDirtyDifference,restoredBindings,bindingParity,failureBindings,storage,removed:!document.querySelector('canvas'),hostReleased:!globalThis[Symbol.for('reflex-dev.xy.shared-webgl-host.v2')].has(document),contextReleased:gl.isContextLost()};
 });
 console.log(JSON.stringify(result));for(const key of ['center','edge','head','frame'])assert.ok(result[key][3]>0,key+' visible');assert.ok(result.changes>0);assert.deepEqual(result.errors,[true,true]);assert.equal(result.removed,true);assert.equal(result.restored,true);assert.deepEqual(result.restoredPixel,result.center);
 for(const key of ['dirtyDifference','cleanDifference','restoredDifference','restoredDirtyDifference'])assert.equal(result[key],0,key+' exact pixels');
 for(const key of ['dirtyBindings','restoredBindings'])assert.deepEqual(result[key],{samplers:[true,true,true,true,true],textures:[true,true,true,true,true],active:true,error:0},key+' state cleanup');
 assert.equal(result.bindingParity.length,6);
 for(const row of result.bindingParity){assert.equal(row.difference,0,'glyph '+row.shape+' exact binding parity');assert.deepEqual(row.bindings,result.dirtyBindings);}
 assert.deepEqual(result.failureBindings,result.dirtyBindings);
 assert.equal(result.hostReleased,true);assert.equal(result.contextReleased,true);
}finally{await browser.close();}
