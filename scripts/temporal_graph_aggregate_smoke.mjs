#!/usr/bin/env node
import assert from 'node:assert/strict';import {spawnSync}from'node:child_process';import {createServer}from'node:http';import{readFile,writeFile,mkdir,mkdtemp}from'node:fs/promises';import{resolve,extname}from'node:path';import{tmpdir}from'node:os';import{chromium}from'playwright';import{decodeContainer}from'../packages/xy-node/src/graphforge-container.js';import{FrozenTemporalGraph}from'../packages/xy-node/src/index.js';import{createHash}from'node:crypto';
const root=resolve(new URL('..',import.meta.url).pathname),output=resolve(process.argv[2]??await mkdtemp(resolve(tmpdir(),'xyg-aggregate-')));await mkdir(output,{recursive:true});
const allowed=new Set(['/tests/browser/temporal_graph_aggregate_page.mjs','/packages/xy-client/dist/index.js','/packages/xy-client/dist/wasm-worker.js','/packages/xy-client/dist/xyg-wasm.wasm','/packages/xy-client/dist/standalone.js','/packages/xy-node/src/graphforge-container.js','/spec/performance/temporal-native-render-2026-11-07/artifacts/retained-later.xyfg']);
const server=createServer(async(req,res)=>{const p=new URL(req.url,'http://localhost').pathname;if(p==='/'){res.setHeader('Content-Type','text/html');res.end('<!doctype html><script type="module" src="/tests/browser/temporal_graph_aggregate_page.mjs"></script>');return;}if(!allowed.has(p)){res.statusCode=404;res.end();return;}try{res.setHeader('Content-Type',extname(p)==='.wasm'?'application/wasm':extname(p)==='.xyfg'?'application/octet-stream':'text/javascript');res.end(await readFile(resolve(root,'.'+p)));}catch{res.statusCode=404;res.end();}});await new Promise(r=>server.listen(0,'127.0.0.1',r));
const browser=await chromium.launch({executablePath:process.env.XYG_CHROMIUM,headless:true,args:['--no-sandbox','--disable-dev-shm-usage']});const errors=[],report=[];
try {
 const page=await browser.newPage({viewport:{width:600,height:500}});page.on('pageerror',e=>errors.push(String(e)));
 await page.addInitScript(()=>{
 const Original=window.Worker;window.aggregateWire=[];
 window.Worker=class extends Original { constructor(...args){super(...args);this.records=new Map();this.addEventListener('message',event=>{const record=this.records.get(event.data?.requestId);if(record){record.reply=event.data.value?.bytes?Array.from(new Uint8Array(event.data.value.bytes)):null;record.responseType=event.data.type;}});}
 postMessage(message,...rest){if(message.type?.startsWith('graph.session.')&&message.request){const record={type:message.type,request:Array.from(new Uint8Array(message.request))};window.aggregateWire.push(record);this.records.set(message.requestId,record);}return super.postMessage(message,...rest);}};
 });
 await page.goto(`http://127.0.0.1:${server.address().port}`);await page.waitForFunction(()=>window.aggregateTest?.open);await page.evaluate(()=>window.aggregateTest.open());
 // Trusted keyboard events establish a canonical node focus and selection.
 await page.locator('[data-xy-graph-session]').focus();
 for(let i=0;i<2;i++){await page.keyboard.press('ArrowRight');await page.evaluate(()=>window.aggregateTest.current.session.whenIdle());}
 await page.keyboard.press('Enter');await page.evaluate(()=>window.aggregateTest.current.session.whenIdle());
 await page.evaluate(()=>window.aggregateTest.current.session.pinFocused(true));
 for(const cursor of [null,5,10,20,30,5]){await page.evaluate(cursor=>window.aggregateTest.capture(cursor),cursor);await page.locator('[data-xy-graph-session]').screenshot({path:resolve(output,`live-${report.length}.png`)});report.push(cursor);}
 await writeFile(resolve(output,'captures.json'),JSON.stringify(await page.evaluate(()=>window.aggregateTest.current.snapshots.map(a=>Array.from(a)))));
 const results=await page.evaluate(()=>window.aggregateTest.finish());await writeFile(resolve(output,'wire.json'),JSON.stringify(await page.evaluate(()=>window.aggregateWire)));
 await replayNative(JSON.parse(await readFile(resolve(output,'wire.json'),'utf8')));await writeFile(resolve(output,'worker.json'),JSON.stringify(results));
 for(const [i,row] of results.entries()){
 const bytes=Buffer.from(row.snapshot,'base64');await writeFile(resolve(output,`frame-${i}.xyfg`),bytes);
 const native=FrozenTemporalGraph.fromBytes(bytes);
 try{const m=native.metadata,p=decodeContainer(m['render.publication'],'XYGR');
 verifyMembership(m,p,i);
 for(const format of ['scene','painter','svg','png','html']){const artifact=native.export(format);assert.deepEqual(Buffer.from(artifact),Buffer.from(row[format],'base64'),`${format} native/Worker frame ${i}`);await writeFile(resolve(output,`frame-${i}.${format}`),artifact);if(['svg','png','html'].includes(format)){const recovered=FrozenTemporalGraph.fromArtifact(artifact);try{assert.deepEqual(Buffer.from(recovered.toBytes()),bytes);}finally{recovered.close();}}}
 }finally{native.close();}
 const offline=await browser.newPage({viewport:{width:600,height:500}});offline.on('pageerror',e=>errors.push(String(e)));await offline.route('http://**',route=>route.abort());await offline.route('https://**',route=>route.abort());await offline.goto('file://'+resolve(output,`frame-${i}.html`));await offline.waitForFunction(()=>document.documentElement.dataset.xyFrozenReady==='true'&&window.__xyFrozenView?.gpuTraces?.length>0);await offline.screenshot({path:resolve(output,`frame-${i}.offline.png`)});await offline.close();
 }
 const pixels=spawnSync(process.env.UV??'uv',['run','python','scripts/verify_temporal_aggregate_artifacts.py',output],{cwd:root,env:process.env,encoding:'utf8'});assert.equal(pixels.status,0,pixels.stdout+pixels.stderr);console.log(pixels.stdout);
 assert.deepEqual(errors,[]);await writeFile(resolve(output,'report.json'),JSON.stringify({frames:results.length,errors},null,2));console.log('aggregate public freeze artifact parity passed');
}finally{await browser.close();await new Promise(r=>server.close(r));}

// An independent authored oracle: these are expectations, never runtime inputs.
function verifyMembership(m,p,i){
 const cursor=[20,5,10,20,30,5][i],validTo=[40,10,20,30],src=[0,0,1,2,0,3],dst=[2,2,3,0,0,3];
 const nodes=validTo.map(t=>+(cursor<t)),edges=src.map((s,e)=>nodes[s]&nodes[dst[e]]);
 const ids=xs=>xs.flatMap(x=>Array(16).fill(x));
 assert.deepEqual(Array.from(m['node.uuid']),ids([1,2,3,4]));assert.deepEqual(Array.from(m['edge.uuid']),ids([11,12,13,14,15,16]));
 assert.deepEqual(Array.from(m['edge.source'],Number),src);assert.deepEqual(Array.from(m['edge.target'],Number),dst);
 assert.deepEqual(Array.from(m['node.visibility']),nodes);assert.deepEqual(Array.from(m['edge.visibility']),edges);
 assert.deepEqual(Array.from(m['visible.node.uuid']),ids(nodes.flatMap((v,n)=>v?[n+1]:[])));assert.deepEqual(Array.from(m['visible.edge.uuid']),ids(edges.flatMap((v,e)=>v?[e+11]:[])));
 assert.deepEqual(m.time,[BigInt(cursor),0n,40n]);assert.deepEqual(m['render.camera'],[1,1,30,60,240,180,1]);
 const expectedNodes=[[[0],[3]],[[0,1],[2,3]],[[0],[2,3]],[[0],[3]],[[0]],[[0,1],[2,3]]][i];
 const expectedEdges=[[[4],[5]],[[0,1,2],[3]],[[0,1],[3]],[[4],[5]],[[4]],[[0,1,2],[3]]][i];
 const plane=name=>Array.from(p.get(name+'#0').value,Number);
 function exact(groups,offsets,members){assert.deepEqual(offsets,[0,...groups.map((_,j)=>groups.slice(0,j+1).flat().length)]);assert.deepEqual(members,groups.flat());}
 for(const [kind,groups]of [['node',expectedNodes],['edge',expectedEdges]]){
 const offsets=plane(`render.${kind}_member_offsets.u64`),members=plane(`render.${kind}_members.u64`);exact(groups,offsets,members);
 // These controls establish that the membership oracle detects omissions,
 // duplication and membership copied from a different temporal publication.
 assert.throws(()=>exact(groups,offsets,members.slice(1)));
 assert.throws(()=>exact(groups,offsets,[...members,members[0]]));
 assert.throws(()=>exact(groups,offsets,members.map(v=>v+1)));
 }
 assert.deepEqual(plane('render.tier.u32'),[[0],[2],[2],[0],[0],[2]][i]);
 const flags=plane('node.flags.u32');assert.deepEqual(flags,[0,0,0,i===4?0:146]);
 for(const key of ['selected.node.uuid','pinned.node.uuid'])assert.deepEqual(Array.from(m[key]),i===0?[]:ids([4]));
 assert.deepEqual(m['focus.kind'],[i===0?0:1]);assert.deepEqual(Array.from(m['focus.uuid']),ids([i===0?0:4]));
 assert.deepEqual(plane('selection.indices.u64'),[3]);
 assert.deepEqual(plane('render.emphasis.u8'),i===4?[0]:[0,1]);
 if(i===4)assert.deepEqual(plane('focus.ring.u32'),[]);
 const endpoints=i===1||i===2||i===5?[[0,1],[1,0]]:i===4?[[0],[0]]:[[0,1],[0,1]];
 assert.deepEqual(plane('render.edge_source.u64'),endpoints[0]);assert.deepEqual(plane('render.edge_target.u64'),endpoints[1]);
}
async function replayNative(records){
 const n=await import('../packages/xy-node/src/native.js'),a=await import('../packages/xy-node/src/abi.js');
 const {nativeComplete,ptr,equalBytes}=await import('../packages/xy-node/test/graph-session-replay-helpers.mjs');
 const ids=xs=>Uint8Array.from(xs.flatMap(x=>Array(16).fill(x)));
 const projection=a.graphProjectionCreate({nodeIds:ids([1,2,3,4]),edgeIds:ids([11,12,13,14,15,16]),sourceIds:ids([1,1,2,3,1,4]),targetIds:ids([3,3,4,1,1,4])});
 const column=a.temporalColumnCreate({values:BigInt64Array.from([40n,10n,20n,30n]),validity:new Uint8Array(4).fill(1),timezone:'UTC'}),owner=a.temporalGraphCreate({projectionHandle:projection,nodeValidTo:column});
 const handle=new BigUint64Array(1);let compared=0;
 try{for(const r of records){const bytes=new Uint8Array(r.request);
 if(r.type==='graph.session.freeze'){
 const {freezeTemporalGraph,FrozenTemporalGraph:Frozen}=await import('../packages/xy-node/src/temporal-graph-frozen.js');
 const v=new DataView(bytes.buffer),zone=new TextDecoder().decode(bytes.subarray(64,64+Number(v.getBigUint64(56,true))));
 const f=freezeTemporalGraph(owner,{revision:v.getBigUint64(24,true),timezone:zone,window:[v.getBigInt64(32,true),v.getBigInt64(40,true)],sessionHandle:handle[0],renderRevision:v.getUint32(12,true)}),browser=Frozen.fromBytes(new Uint8Array(r.reply));
 try{for(const [key,value]of Object.entries(f.metadata)){if(key==='version'||key==='identity')continue;assert.deepEqual(value,browser.metadata[key],`native acquisition ${key}`);}}finally{f.close();browser.close();}continue;
 }
 if(r.type==='graph.session.temporal-frame'){const v=new DataView(bytes.buffer);a.temporalGraphFrame(owner,{revision:v.getBigUint64(16,true),cursor:v.getBigInt64(24,true),range:[v.getBigInt64(32,true),v.getBigInt64(40,true)],budget:v.getBigUint64(48,true)});continue;}
 if(!['graph.session.open','graph.session.render','graph.session.interact'].includes(r.type))continue;
 const p=decodeContainer(bytes,'XYGI'),u=p.get('header.u64#0').value;
 if(r.type==='graph.session.open'){const doc=p.get('document.bytes#0').value;assert.equal(n.xyGraphforgeSessionCreate(ptr(doc),BigInt(doc.length),ptr(bytes),BigInt(bytes.length),u[0],u[1],n.pointer(handle,'uint64_t *')),0);continue;}
 let request=bytes;
 const bind=p.get('header.u32#0').value[1]===18;
 if(bind){
 const {encodeContainer}=await import('../packages/xy-node/src/graphforge-container.js');request=encodeContainer('XYGI',[...p].map(([key,v])=>({name:key.slice(0,key.lastIndexOf('#')),dtype:v.dtype,values:key==='temporal.u64#0'?[owner]:v.value})));
 }
 const fn=r.type==='graph.session.render'?n.xyGraphforgeSessionRender:bind?n.xyGraphforgeSessionBindTemporal:n.xyGraphforgeSessionInteract;
 equalBytes(nativeComplete(fn,handle[0],request),new Uint8Array(r.reply),r.type);compared++;
 }assert.ok(compared>10);console.log('complete native/browser XYGR replay comparisons',compared);
 }finally{if(handle[0])n.xyGraphforgeSessionDestroy(handle[0]);a.temporalGraphDestroy(owner);a.temporalColumnDestroy(column);a.graphProjectionDestroy(projection);}
}
