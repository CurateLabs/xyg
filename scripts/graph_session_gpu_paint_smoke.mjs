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
  function put(name,index,dtype,values){const bytes=new Uint8Array(values.buffer,values.byteOffset,values.byteLength);s.set(`${name}#${index}`,{name,index,dtype,count:dtype===2?bytes.length/4:dtype===5?bytes.length/8:bytes.length,bytes});}
  put('gpu.header.u32',0,2,new Uint32Array([1,0,2,1,1,1,1,0]));
  for(let i=0;i<3;i++)put('gpu.transform.f64',i,5,new Float64Array([0,1]));
  for(const [name,columns] of [['node',[[50,150],[80,80]]],['shaft',[[60],[80],[140],[80]]],['head',[[140],[80],[132],[75],[132],[85]]],['frame',[[25],[50],[170],[110]]]])columns.forEach((c,i)=>put(`gpu.${name}.coord.bytes`,i,6,new Float32Array(c)));
  [[3],[0],[0],[0]].forEach((c,i)=>put('gpu.shaft.attr.bytes',i,6,new Float32Array(c)));
  put('gpu.frame.width.bytes',0,6,new Float32Array([1]));
  put('gpu.shaft.edge.u32',0,2,new Uint32Array([0]));put('gpu.shaft.flags.u8',0,1,new Uint8Array([1]));put('gpu.head.piece.u32',0,2,new Uint32Array([0]));put('gpu.frame.node.u32',0,2,new Uint32Array([0]));
  for(const [kind,count] of [['node',2],['edge',1]]){const styles=new Uint8Array(count*60),v=new DataView(styles.buffer);for(let n=0;n<count;n++){const at=n*60;for(const field of [0,4,28,32,36])styles.set([40,80,200,255],at+field);for(const [field,value] of [[12,20],[16,2],[20,1],[40,26],[44,4]])v.setFloat32(at+field,value,true);}put(`gpu.${kind}.style.bytes`,0,6,styles);put(`gpu.${kind}.state.u8`,0,1,new Uint8Array(count*4));}
  put('render.node_x.f64',0,5,new Float64Array(2));put('render.edge_source.u64',0,3,new BigUint64Array(1));s.get('render.edge_source.u64#0').count=1;
  const gpu=decodeGraphGpu(s);const painter=createGraphGpuPainter(document.querySelector('#graph'));
  const camera=[-2,-3,400,400,240,180,2];painter.paint(gpu,camera);
  const ctx=painter.canvas.getContext('2d'); const before=ctx.getImageData(0,0,480,360).data.slice();
  const pixel=(x,y)=>Array.from(ctx.getImageData(x*2,y*2,1,1).data);
  const center=pixel(50,80),edge=pixel(100,80),head=pixel(138,80),frame=pixel(25,70);
  s.get('gpu.node.state.u8#0').bytes[1]=1;painter.paint(decodeGraphGpu(s),camera);
  const after=ctx.getImageData(0,0,480,360).data;let changes=0;for(let i=0;i<after.length;i++)if(after[i]!==before[i])changes++;
  const host=globalThis[Symbol.for('reflex-dev.xy.shared-webgl-host.v1')].get(document);
  const ext=host.gl.getExtension('WEBGL_lose_context');
  const restored=await new Promise((resolve,reject)=>{const timer=setTimeout(()=>reject(new Error('restore timeout')),5000);host.canvas.addEventListener('webglcontextrestored',()=>{clearTimeout(timer);resolve(true);},{once:true});host.canvas.addEventListener('webglcontextlost',()=>setTimeout(()=>ext.restoreContext(),50),{once:true});ext.loseContext();});
  const restoredPixel=pixel(50,80);
  const errors=[];for(const mutate of [()=>s.set('gpu.unknown#0',{name:'gpu.unknown',index:0,dtype:1,count:0,bytes:new Uint8Array()}),()=>s.get('gpu.node.style.bytes#0').bytes[57]=1]){mutate();try{decodeGraphGpu(s);errors.push(false);}catch(e){errors.push(e.code==='GF_INTERACTION_INVALID');}s.delete('gpu.unknown#0');}
  painter.dispose();painter.dispose();return{center,edge,head,frame,changes,errors,restored,restoredPixel,removed:!document.querySelector('canvas')};
 });
 console.log(JSON.stringify(result));for(const key of ['center','edge','head','frame'])assert.ok(result[key][3]>0,key+' visible');assert.ok(result.changes>0);assert.deepEqual(result.errors,[true,true]);assert.equal(result.removed,true);assert.equal(result.restored,true);assert.deepEqual(result.restoredPixel,result.center);
}finally{await browser.close();}
