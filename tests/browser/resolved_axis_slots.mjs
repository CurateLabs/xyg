// Actual authored-CSS compatibility against the pre-adapter 188f bundle.
// Explicit CSS dimensions/positions exercise the public slot; no chart plot,
// layout, ticks, Rust geometry or full-image gate is overridden.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import {createHash} from 'node:crypto';
import {createServer} from 'node:http';
import {chromium} from 'playwright';
const [receiptArg,baselineArg,outputName='slots']=process.argv.slice(2);
assert.ok(receiptArg&&baselineArg,'receipt and independently built 188f asset directory required');
const receipt=path.resolve(receiptArg),baseline=path.resolve(baselineArg),output=path.join(receipt,outputName);fs.mkdirSync(output,{recursive:true});
const baselineBytes=fs.readFileSync(path.join(baseline,'index.js'));
assert.equal(createHash('sha256').update(baselineBytes).digest('hex'),'351fa5038800204a13a99ae9cb91612472e3368f6d7ecd4829d589e39b16acd7');
const server=createServer((req,res)=>{const name=path.basename(req.url);try{let bytes;if(req.url==='/'){res.setHeader('Content-Type','text/html');res.end('<!doctype html><style>body{margin:0}</style><div id="chart"></div>');return;}else if(req.url==='/before/index.js')bytes=baselineBytes;else bytes=fs.readFileSync(name==='slot.scene'?path.join(receipt,name):path.join('packages/xy-client/dist',name));res.setHeader('Content-Type',name.endsWith('.js')?'text/javascript':name.endsWith('.wasm')?'application/wasm':'application/octet-stream');res.end(bytes);}catch{res.writeHead(404);res.end();}});
await new Promise(r=>server.listen(0,'127.0.0.1',r));const origin=`http://127.0.0.1:${server.address().port}`;
const browser=await chromium.launch({executablePath:process.env.XYG_CHROMIUM,args:['--no-sandbox','--hide-scrollbars','--use-angle=swiftshader','--enable-unsafe-swiftshader']});
const effects=[
 ['solid','','svg'],['alpha','background:rgba(180,30,60,.5)','svg'],
 ['border','border:2px solid rgb(0,0,255)','html'],
 ['gradient','background:linear-gradient(90deg,rgb(255,0,0),rgb(0,0,255))','html'],
 ['radius','border-radius:4px','html'],['shadow','box-shadow:3px 2px 2px blue','html'],
 ['outline','outline:2px solid blue','html'],['padding','padding:2px 3px','html'],
 ['filter','filter:blur(.5px)','html'],['transform','transform:translate(2px,3px)','html'],
 ['translate','translate:2px 3px','html'],['clip','clip-path:inset(2px)','html'],
 ['overflow','overflow:hidden','html'],['pseudo','','html'],
 ['inline','','svg'],['important','width:80px!important;background:rgb(180,30,60)!important','svg'],
 ['inline-border','','html'],['inline-gradient','','html'],
 ['ancestor-transform','','html'],['visibility','visibility:hidden','svg'],['mask','mask-image:linear-gradient(black,transparent)','html'],
 ['important-clip','clip-path:none!important','html'],['transition','transition:background-color .1s','html'],['animation','animation:authored-future-animation 1s','html'],
];
const result={browser:browser.version(),baselineSha256:createHash('sha256').update(baselineBytes).digest('hex'),cases:[],switches:[],failures:[],layoutOverrides:null,masks:[]};
try{for(const dpr of [1,1.25,2]){for(const lane of ['before','after']){
 const page=await browser.newPage({viewport:{width:320,height:240},deviceScaleFactor:dpr});const errors=[];page.on('pageerror',e=>errors.push(String(e)));await page.goto(origin);
 await page.evaluate(async lane=>{window.client=await import(lane==='before'?'/before/index.js':'/index.js');window.worker=client.createXygWasmWorker({workerUrl:'/wasm-worker.js',wasm:'/xyg-wasm.wasm'});await worker.ready;const el=document.getElementById('chart');Object.assign(el.style,{width:'320px',height:'240px',position:'relative'});window.view=await client.renderWasmScene({el,worker,scene:await(await fetch('/slot.scene')).arrayBuffer()});window.css=document.createElement('style');document.head.appendChild(css);window.snapshot=()=>({plot:{...view.plot},dpr:devicePixelRatio,axes:[...el.querySelectorAll('[data-xy-slot="axis_line"]')].map(e=>{const r=e.getBoundingClientRect(),s=getComputedStyle(e);return {axis:e.dataset.xyAxis,side:e.dataset.xyAxisSide,className:e.className,box:{x:r.x,y:r.y,width:r.width,height:r.height},paint:e.dataset.xySpinePaint??'html',suppression:s.clipPath,computed:Object.fromEntries(['backgroundColor','backgroundImage','borderWidth','borderColor','borderRadius','boxShadow','outlineStyle','outlineWidth','padding','transform','translate','opacity','visibility','display'].map(k=>[k,s[k]]))};}),svg:[...el.querySelectorAll('[data-xy-resolved-spine]')].map(e=>({axis:e.dataset.xyResolvedSpine,side:e.dataset.xySpineSide,line:Object.fromEntries([...e.firstElementChild.attributes].map(a=>[a.name,a.value]))}))});},lane);
 for(const [name,css,expected] of effects){
  const record=await page.evaluate(async({name,css})=>{
   view.root.style.transform=name==='ancestor-transform'?'translate(2px,3px)':'';
   window.css.textContent=`.slot-probe{width:80px;height:8px;background:rgb(180,30,60);${css}}.slot-probe[data-xy-axis^="y"]{display:none}${name==='pseudo'?'.slot-probe::after{content:"";position:absolute;inset:0;border:2px solid blue}':''}`;
   const inline=name.startsWith('inline')||name==='important';
   const styles=inline?{width:72,height:10,left:17,top:19,background:'rgb(4,5,6)'}:{left:17,top:19};
   if(name==='inline-border')styles.border='2px solid blue';if(name==='inline-gradient')styles.background='linear-gradient(90deg,red,blue)';
   view.spec.dom={class_names:{axis_line:'slot-probe'},styles:{axis_line:styles}};view.refreshTheme();await new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)));return snapshot();
  },{name,css});
  const key=`${name}.dpr${dpr}.${lane}`;
  if(lane==='after')for(const a of record.axes){try{const actualExpected=a.computed.display==='none'?'html':expected;assert.equal(a.paint,actualExpected,key);if(actualExpected==='svg')assert.equal(a.suppression,'inset(100%)');assert.equal(record.svg.filter(s=>s.axis===a.axis).length,actualExpected==='svg'?1:0);}catch(e){result.failures.push({key,message:e.message});}}
  await page.locator('#chart').screenshot({path:path.join(output,`${key}.png`)});result.cases.push({key,name,lane,dpr,expected,...record});
 }
 // Same live chart switches through class effects AND public inline styles.
 const switches=await page.evaluate(async()=>{const rows=[];view.root.style.transform='';view.spec.dom={class_names:{axis_line:'slot-probe'},styles:{axis_line:{left:17,top:19}}};css.textContent='.slot-probe{width:80px;height:8px;background:rgb(180,30,60)}.box-border .slot-probe{border:2px solid blue}.box-gradient .slot-probe{background:linear-gradient(90deg,red,blue)}';for(const mode of ['solid','border','gradient','solid']){view.root.classList.remove('box-border','box-gradient');if(mode!=='solid')view.root.classList.add(`box-${mode}`);if(rows.length===0)view.refreshTheme();await new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)));rows.push({mode,...snapshot()});}view.spec.dom.styles.axis_line.border='2px solid blue';view.refreshTheme();await new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)));rows.push({mode:'inline-border',...snapshot()});delete view.spec.dom.styles.axis_line.border;view.refreshTheme();await new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)));rows.push({mode:'inline-clear',...snapshot()});return rows;});
 for(const row of switches){const expected=lane==='before'||['border','gradient','inline-border'].includes(row.mode)?'html':'svg';try{for(const a of row.axes){assert.equal(a.paint,expected);assert.equal(a.suppression,expected==='svg'?'inset(100%)':'none');}assert.equal(row.svg.length,expected==='svg'?row.axes.length:0);}catch(e){result.failures.push({lane,dpr,mode:row.mode,message:e.message});}}result.switches.push({lane,dpr,automaticAncestorClassObserver:true,rows:switches});
 assert.deepEqual(errors,[]);await page.evaluate(()=>{view.destroy();worker.dispose();});await page.close();
}}}finally{await browser.close();server.close();}
for(const after of result.cases.filter(r=>r.lane==='after')){const before=result.cases.find(r=>r.name===after.name&&r.dpr===after.dpr&&r.lane==='before');try{assert.deepEqual(after.plot,before.plot);assert.deepEqual(after.axes.map(({paint,suppression,...a})=>a),before.axes.map(({paint,suppression,...a})=>a));if(after.expected==='html')assert.deepEqual(fs.readFileSync(path.join(output,`${after.key}.png`)),fs.readFileSync(path.join(output,`${before.key}.png`)));}catch(e){result.failures.push({key:after.key,message:e.message});}}
fs.writeFileSync(path.join(output,'observations.json'),JSON.stringify(result,null,2)+'\n');console.log(JSON.stringify({cases:result.cases.length,switches:result.switches.length,failures:result.failures},null,2));if(result.failures.length)process.exitCode=1;
