#!/usr/bin/env node
// Actual native383 / packaged WASM33 selected-state ownership and exact wire proof.
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {writeFile,mkdir} from 'node:fs/promises';
import {createHash} from 'node:crypto';
import {execFileSync} from 'node:child_process';
import {dirname} from 'node:path';
import {gzipSync} from 'node:zlib';
import {encodeGeoScaleRequest as encode,decodeGeoScaleReply as decode,encodeGeoChunkRequest,encodeGeoScaleStyle,driveGeoSession,driveGeoIndexSession,prepareGeoSceneData,prepareGeoAuxData,parseGeoRowsData,parseGeoHitData,nativeGeoScaleBridge} from '../packages/xy-node/src/geoscale.js';
import {createGeoSelectedScope} from '../packages/xy-node/src/geo-selected.js';

const budget={processorBytes:128<<20,maxRowsExamined:1000000n,maxReadBytes:128n<<20n,maxChunks:65536,pageRows:1};
const MAX=0xffffffffffffffffn,MIN=-0x8000000000000000n;
const style=encodeGeoScaleStyle({fill:new Uint8Array([255,0,0,255]),stroke:new Uint8Array(4),strokeWidth:0,diameter:6,opacity:1,symbol:0});
const path=process.env.XYG_SELECTED_WASM??'packages/xy-client/dist/xyg-wasm.wasm';
const {instance}=await WebAssembly.instantiate(await readFile(path),{}),x=instance.exports,h=x.xyg_wasm_instance_new(budget.processorBytes);
assert.ok(h);assert.equal(x.xyg_wasm_abi_version(),33);let sequence=0;
async function call(request,read){assert.equal(x.xyg_wasm_arena_resize(h,request.byteLength),0);new Uint8Array(x.memory.buffer,x.xyg_wasm_arena_ptr(h)>>>0,request.byteLength).set(new Uint8Array(request));const status=x[`xyg_wasm_geo_scale_${read?'read':'execute'}`](h,++sequence,0,request.byteLength);if(status){const error=new Error(new TextDecoder().decode(new Uint8Array(x.memory.buffer,x.xyg_wasm_last_error_ptr(h)>>>0,x.xyg_wasm_last_error_len(h))));error.nativeCode=status;throw error;}return new Uint8Array(x.memory.buffer,x.xyg_wasm_output_ptr(h)>>>0,x.xyg_wasm_output_len(h)).slice().buffer;}
const wasm={execute:r=>call(r,false),read:r=>call(r,true)};
// These test-only bridges call raw exports; they have no genuine Worker/native
// outcome capture. Native cases continue through the real public State.begin.
const rawBridges=new WeakSet([wasm]),consumedRawStates=new WeakSet();
async function beginLegacy(bridge,state,input){
 if(!rawBridges.has(bridge))return state.begin(input);
 assert.ok(!consumedRawStates.has(state),'raw State already consumed');
 const payload=new Uint8Array(8);new DataView(payload.buffer).setBigUint64(0,state.handle,true);const request=encode({...input,payload});assert.equal(new DataView(request).getBigUint64(240,true),0n);
 const packet=await bridge.execute(request),r=decode(packet);assert.equal(packet.byteLength,256);assert.equal(r.sequence,input.sequence);
 if(r.code===10){assert.equal(input.command,36);assert.equal(r.handle,input.handle);return {fallback:true,reason:new DataView(packet).getUint32(48,true),state};}
 assert.equal(r.code,0);assert.equal(r.handle,input.command===36?state.handle:input.handle);assert.ok(new Uint8Array(packet).subarray(32).every(n=>n===0));consumedRawStates.add(state);
 if(input.command===35)await assert.rejects(bridge.execute(encode({command:6,handle:state.handle,sequence:0n})),/XYG_GEO_SOURCE_STALE/);
 else{const phase=decode(await bridge.execute(encode({command:6,handle:state.handle,sequence:input.sequence,budget:input.budget})));assert.equal(phase.handle,state.handle);assert.equal(phase.sequence,input.sequence);assert.ok([1,12].includes(phase.code),'consumed raw36 owner is an IndexedQuery, not State');}
 // This is fixture plumbing, not an issued product operation/Frame. Its Scene
 // owner comes from the existing shared prepare helper and actual Rust Data.
 return {fallback:false,operation:{
  drive(options){return input.command===36?driveGeoIndexSession(bridge,{...options,handle:r.handle,sequence:input.sequence,budget:input.budget}):driveGeoSession(bridge,{...options,handle:r.handle,sequence:input.sequence,budget:input.budget});},
  prepare(style){return prepareGeoSceneData(bridge,{command:input.command===36?19:11,handle:r.handle,sequence:input.sequence,budget:input.budget,style});}
 }};
}
async function disposeState(bridge,state){if(state&&!consumedRawStates.has(state))await state.dispose();}

async function dispose(bridge,handle){if(handle!==undefined)await bridge.execute(encode({command:10,handle}));}
function canonical(packet,rows=false){const b=new Uint8Array(packet.slice(0));b.fill(0,16,24);if(rows)b.fill(0,80,88);return b;}
async function fixture(bridge,vertices=2,layer=MAX,uniform=style,reducedKind=0){
 const validAt=64+16*vertices,idAt=(validAt+2+7)&~7,offsetAt=idAt+16,d=new Uint8Array(offsetAt+16),v=new DataView(d.buffer);d.set([88,89,71,68]);[1,4,4326,1,0].forEach((n,i)=>v.setUint32(4+4*i,n,true));[2n,BigInt(vertices),3n,0n,0n].forEach((n,i)=>v.setBigUint64(24+8*i,n,true));d.set([1,1],validAt);v.setBigUint64(idAt,MAX,true);v.setBigUint64(idAt+8,9007199254740993n,true);[0,vertices/2,vertices].forEach((n,i)=>v.setUint32(offsetAt+4*i,n,true));
 const chunk=await bridge.read(encodeGeoChunkRequest({descriptor:d,rows:2,intervals:{starts:new BigInt64Array([MIN,MIN]),ends:new BigInt64Array([0n,0n]),startValidity:new Uint8Array([1,1]),endValidity:new Uint8Array([1,1])}},budget.processorBytes));
 const builder=decode(await bridge.execute(encode({command:1}))).handle;let manifest;
 try{await bridge.execute(encode({command:2,handle:builder,payload:chunk}));await bridge.execute(encode({command:3,handle:builder,generation:MAX}));manifest=await bridge.read(encode({command:21,handle:builder}));}finally{await dispose(bridge,builder);}
 const source=decode(await bridge.execute(encode({command:4,payload:manifest,budget}))).handle,readChunk=async()=>chunk;
 const info=(await driveGeoSession(bridge,{handle:source,sequence:0n,budget,readChunk})).source;
 const query={camera:{crs:4326,worldWrap:true,centerX:0,centerY:0,zoom:0,width:800,height:600,bearing:0,pitch:0},reducedKind,maxCells:1,previousDirect:true,sourceDigest:info.digest,generation:info.generation,layerId:layer,cameraRevision:1n,timeRevision:1n,layerRevision:1n,styleRevision:1n,stateRevision:1n,time:{kind:1,instant:MIN},maxProjectedVertices:1000000n};
 await bridge.execute(encode({command:5,handle:source,sequence:1n,budget,query}));await driveGeoSession(bridge,{handle:source,sequence:1n,budget,readChunk});const frame=await prepareGeoSceneData(bridge,{handle:source,sequence:1n,budget,style:uniform});return {source,frame,query,readChunk};
}
async function run(bridge,vertices){
 const f=await fixture(bridge,vertices),scope=await createGeoSelectedScope(bridge,{frameHandle:f.frame.handle,sequence:1n,namespace:MAX,layerId:MAX,budget});let frame,index;
 try{
  const state=await scope.state({revision:2n,ids:new BigUint64Array([MAX,MAX]),fill:new Uint8Array([0,255,0,255]),budget});
  await assert.rejects(beginLegacy(bridge,state,{command:35,handle:f.source,sequence:1n,query:{...f.query,stateRevision:2n},budget}));
  const accepted=await beginLegacy(bridge,state,{command:35,handle:f.source,sequence:2n,query:{...f.query,stateRevision:2n},budget});assert.equal(accepted.fallback,false);await accepted.operation.drive({readChunk:f.readChunk});frame=await accepted.operation.prepare(style);
  assert.equal(frame.data.selection.id(0),MAX);assert.equal(frame.data.selection.idCount,1);assert.equal(frame.data.selection.visibleVertices,BigInt(vertices/2));assert.equal(frame.data.selection.cellCount,vertices>32768?1:0);const expected=canonical(frame.data.packet);
  // Build and query an independent index from exact immutable selected authority.
  const p=new Uint8Array(16),pv=new DataView(p.buffer);pv.setUint32(0,16,true);pv.setBigUint64(8,1000000n,true);index=decode(await bridge.execute(encode({command:17,handle:frame.handle,sequence:2n,budget,payload:p}))).handle;const pages=new Map();
  await driveGeoIndexSession(bridge,{handle:index,sequence:2n,budget,readChunk:f.readChunk,readPage:async t=>pages.get(t.page),writePage:async(t,b)=>pages.set(t.page,b.slice())});
  const indexedState=await scope.state({revision:2n,ids:new BigUint64Array([MAX]),fill:new Uint8Array([0,255,0,255]),budget});const indexed=await beginLegacy(bridge,indexedState,{command:36,handle:index,sequence:3n,query:{...f.query,stateRevision:2n},budget});assert.equal(indexed.fallback,false);await indexed.operation.drive({readPage:async t=>pages.get(t.page)});const indexedFrame=await indexed.operation.prepare(style);
  try{const b=canonical(indexedFrame.data.packet);new DataView(b.buffer).setBigUint64(24,2n,true);assert.deepEqual(b,expected);}finally{await indexedFrame.dispose();}
  await f.frame.dispose();await dispose(bridge,f.source);f.source=undefined;await dispose(bridge,index);index=undefined;
  // Private rows continuation survives Source/Index disposal and carries intent.
  let authority=frame.handle,rowsPacket;
  for(let i=0;i<2;i++){
   const rows=decode(await bridge.execute(encode({command:15,handle:authority,sequence:2n,budget}))).handle;let page;
   try{await driveGeoSession(bridge,{handle:rows,sequence:2n,budget,readChunk:f.readChunk});page=await prepareGeoAuxData(bridge,{command:16,handle:rows,sequence:2n,budget},parseGeoRowsData);assert.equal(page.data.length,1);assert.equal(page.data.record(0).selected,i===0);assert.equal(page.data.record(0).intervalStart,MIN);if(i===0){rowsPacket=canonical(page.data.packet,true);authority=page.handle;}else await page.dispose();}
   finally{await dispose(bridge,rows);}
  }
  await dispose(bridge,authority);return {scene:expected,rows:rowsPacket};
 }finally{if(frame)await frame.dispose();await f.frame.dispose();await dispose(bridge,index);await dispose(bridge,f.source);await scope.dispose();}
}
async function fiveViews(bridge){
 const frames=[],scopes=[];let state,rows,page,nextRows,next;
 try{
  for(let i=0;i<5;i++){const f=await fixture(bridge,2,BigInt(i+1));frames.push(f);scopes.push(await createGeoSelectedScope(bridge,{frameHandle:f.frame.handle,sequence:1n,namespace:BigInt(i+1),layerId:f.query.layerId,budget}));}
  const f=frames[0];state=await scopes[0].state({revision:2n,ids:new BigUint64Array([MAX]),fill:new Uint8Array([0,255,0,255]),budget});
  // Fifteen durable owners + State16: no hidden disposal or raised limit.
  await assert.rejects(bridge.execute(encode({command:15,handle:f.frame.handle,sequence:1n,budget})));
  const accepted=await beginLegacy(bridge,state,{command:35,handle:f.source,sequence:2n,query:{...f.query,stateRevision:2n},budget});assert.equal(accepted.fallback,false);await accepted.operation.drive({readChunk:f.readChunk});const selected=await accepted.operation.prepare(style);await f.frame.dispose();f.frame=selected;
  rows=decode(await bridge.execute(encode({command:15,handle:selected.handle,sequence:2n,budget}))).handle;await driveGeoSession(bridge,{handle:rows,sequence:2n,budget,readChunk:f.readChunk});await assert.rejects(prepareGeoAuxData(bridge,{command:16,handle:rows,sequence:2n,budget},parseGeoRowsData));await dispose(bridge,rows);rows=undefined;
  // Explicitly park two engines while retaining every displayed immutable frame.
  for(const parked of frames.slice(0,2)){await dispose(bridge,parked.source);parked.source=undefined;}
  rows=decode(await bridge.execute(encode({command:15,handle:selected.handle,sequence:2n,budget}))).handle;await driveGeoSession(bridge,{handle:rows,sequence:2n,budget,readChunk:f.readChunk});page=await prepareGeoAuxData(bridge,{command:16,handle:rows,sequence:2n,budget},parseGeoRowsData);await dispose(bridge,rows);rows=undefined;
  assert.equal(page.data.record(0).selected,true);
  nextRows=decode(await bridge.execute(encode({command:15,handle:page.handle,sequence:2n,budget}))).handle;
  await assert.rejects(driveGeoSession(bridge,{handle:nextRows,sequence:2n,budget,readChunk:async()=>new Uint8Array((await f.readChunk()).byteLength)}));assert.equal(page.data.record(0).featureId,MAX);await dispose(bridge,nextRows);nextRows=undefined;
  nextRows=decode(await bridge.execute(encode({command:15,handle:page.handle,sequence:2n,budget}))).handle;await driveGeoSession(bridge,{handle:nextRows,sequence:2n,budget,readChunk:f.readChunk});next=await prepareGeoAuxData(bridge,{command:16,handle:nextRows,sequence:2n,budget},parseGeoRowsData);assert.equal(next.data.record(0).selected,false);assert.equal(page.data.record(0).featureId,MAX);
  for(const f of frames)assert.ok(f.frame.data.scene.length>=160);
 }finally{
  if(next)await next.dispose();await dispose(bridge,nextRows);if(page)await page.dispose();await dispose(bridge,rows);await disposeState(bridge,state);
  for(const f of frames){await f.frame.dispose();await dispose(bridge,f.source);}for(const scope of scopes)await scope.dispose();
 }
}
async function cancelAndRecover(bridge){
 const f=await fixture(bridge),scope=await createGeoSelectedScope(bridge,{frameHandle:f.frame.handle,sequence:1n,namespace:100n,layerId:MAX,budget});let frame;
 try{
  const intent={revision:2n,ids:new BigUint64Array([MAX]),fill:new Uint8Array([0,255,0,255]),budget};
  const state=await scope.state(intent),accepted=await beginLegacy(bridge,state,{command:35,handle:f.source,sequence:2n,query:{...f.query,stateRevision:2n},budget});
  let entered,release;const gate=new Promise(r=>release=r),started=new Promise(r=>entered=r),abort=new AbortController();let settled=false;
  const pending=accepted.operation.drive({signal:abort.signal,readChunk:async()=>{entered();await gate;return f.readChunk();}});pending.then(()=>settled=true,()=>settled=true);
  await started;abort.abort();await new Promise(r=>setTimeout(r,5));assert.equal(settled,false);release();await assert.rejects(pending,error=>error.name==='AbortError');assert.equal(f.frame.data.record(0).featureId,MAX);
  const retry=await scope.state(intent),recovered=await beginLegacy(bridge,retry,{command:35,handle:f.source,sequence:3n,query:{...f.query,stateRevision:2n},budget});await recovered.operation.drive({readChunk:f.readChunk});frame=await recovered.operation.prepare(style);assert.equal(frame.data.selection.visibleVertices,1n);
 }finally{if(frame)await frame.dispose();await f.frame.dispose();await dispose(bridge,f.source);await scope.dispose();}
}
async function crossTransportCollision(){
 const owners=[];
 try{
  for(let i=0;i<2;i++){
   const {instance}=await WebAssembly.instantiate(await readFile(path),{}),e=instance.exports,id=e.xyg_wasm_instance_new(budget.processorBytes);let sequence=0,calls=0;
   const call=async(request,read)=>{calls++;assert.equal(e.xyg_wasm_arena_resize(id,request.byteLength),0);new Uint8Array(e.memory.buffer,e.xyg_wasm_arena_ptr(id)>>>0,request.byteLength).set(new Uint8Array(request));const status=e[`xyg_wasm_geo_scale_${read?'read':'execute'}`](id,++sequence,0,request.byteLength);if(status)throw Error(new TextDecoder().decode(new Uint8Array(e.memory.buffer,e.xyg_wasm_last_error_ptr(id)>>>0,e.xyg_wasm_last_error_len(id))));return new Uint8Array(e.memory.buffer,e.xyg_wasm_output_ptr(id)>>>0,e.xyg_wasm_output_len(id)).slice().buffer;};
   const bridge={execute:r=>call(r,false),read:r=>call(r,true)};rawBridges.add(bridge);const f=await fixture(bridge),scope=await createGeoSelectedScope(bridge,{frameHandle:f.frame.handle,sequence:1n,namespace:MAX,layerId:MAX,budget}),state=await scope.state({revision:2n,ids:new BigUint64Array([i?9007199254740993n:MAX]),fill:new Uint8Array([0,255,0,255]),budget});owners.push({e,id,bridge,f,scope,state,calls:()=>calls});
  }
  assert.equal(owners[0].state.handle,owners[1].state.handle);assert.equal(owners[0].scope.handle,owners[1].scope.handle);
  const before=owners[1].calls();await assert.rejects(owners[1].scope.link(owners[0].state,{revision:3n,budget}),/another transport/);assert.equal(owners[1].calls(),before);
  // Target intent remains untouched and succeeds with its own scoped owner.
  const b=owners[1],accepted=await beginLegacy(b.bridge,b.state,{command:35,handle:b.f.source,sequence:2n,query:{...b.f.query,stateRevision:2n},budget});await accepted.operation.drive({readChunk:b.f.readChunk});const frame=await accepted.operation.prepare(style);assert.equal(frame.data.selection.id(0),9007199254740993n);await frame.dispose();
 }finally{for(const b of owners){await disposeState(b.bridge,b.state);await b.f.frame.dispose();await dispose(b.bridge,b.f.source);await b.scope.dispose();assert.equal(b.e.xyg_wasm_instance_dispose(b.id),0);}}
}
async function effectiveSelectedAlpha(bridge){
 for(const test of [{vertices:2,base:255,selected:0,kind:0,expected:9007199254740993n},{vertices:2,base:0,selected:255,kind:0,expected:MAX},{vertices:40000,base:255,selected:0,kind:0,expected:null},{vertices:40000,base:255,selected:0,kind:1,expected:null}]){
  const uniform=encodeGeoScaleStyle({fill:new Uint8Array([255,0,0,test.base]),stroke:new Uint8Array(4),strokeWidth:0,diameter:6,opacity:1,symbol:0}),f=await fixture(bridge,test.vertices,MAX,uniform,test.kind),scope=await createGeoSelectedScope(bridge,{frameHandle:f.frame.handle,sequence:1n,namespace:555n,layerId:MAX,budget});let frame,hit;
  try{const state=await scope.state({revision:2n,ids:new BigUint64Array(test.vertices>32768?[MAX,9007199254740993n]:[MAX]),fill:new Uint8Array([0,255,0,test.selected]),budget}),accepted=await beginLegacy(bridge,state,{command:35,handle:f.source,sequence:2n,query:{...f.query,stateRevision:2n},budget});await accepted.operation.drive({readChunk:f.readChunk});frame=await accepted.operation.prepare(uniform);
   const p=new Uint8Array(80),v=new DataView(p.buffer);p.set(uniform);v.setFloat64(48,400,true);v.setFloat64(56,300,true);v.setUint32(72,1,true);v.setUint32(76,4,true);hit=await prepareGeoAuxData(bridge,{command:14,handle:frame.handle,sequence:2n,budget,payload:p},parseGeoHitData);
   assert.equal(hit.data.length,test.expected===null?0:1,`effectivealpha vertices${test.vertices}/kind${test.kind}/base${test.base}/selected${test.selected}`);if(test.expected!==null)assert.equal(hit.data.record(0).featureId,test.expected);
  }finally{if(hit)await hit.dispose();if(frame)await frame.dispose();await f.frame.dispose();await dispose(bridge,f.source);await scope.dispose();}
 }
}
try{
 const cases=[],hash=b=>createHash('sha256').update(b).digest('hex');
 for(const vertices of [2,40000]){const native=await run(nativeGeoScaleBridge(budget.processorBytes),vertices),actualWasm=await run(wasm,vertices);assert.deepEqual(native,actualWasm);cases.push({vertices,selectedVertices:vertices/2,scenePacketSha256:hash(native.scene),rowsPacketSha256:hash(native.rows)});}
 for(const bridge of [nativeGeoScaleBridge(budget.processorBytes),wasm]){await fiveViews(bridge);await cancelAndRecover(bridge);await effectiveSelectedAlpha(bridge);}await crossTransportCollision();
 if(process.env.XYG_SELECTED_REPORT){
  const sourceFiles=['crates/xyg-engine/src/geo_linked_state.rs','crates/xyg-engine/src/geo_linked_state_protocol.rs','crates/xyg-engine/src/geo_source_session.rs','crates/xyg-engine/src/geo_rows_session.rs','crates/xyg-engine/src/geo_scale_protocol.rs','crates/xyg-engine/src/geo_lod.rs','crates/xyg-engine/src/geo_lod_scene.rs','crates/xyg-engine/src/geo_lod_hit.rs','crates/xyg-engine/src/geo_snapshot.rs','js/src/63_geo_source.ts','js/src/68_geo_selected.ts','scripts/geo_selected_conformance.mjs'],sources={};
  for(const file of sourceFiles)sources[file]=hash(await readFile(file));const wasm=await readFile(path),native=await readFile(process.env.XYG_NATIVE_LIB);
  const report={sourceHead:execFileSync('git',['rev-parse','HEAD'],{encoding:'utf8'}).trim(),environment:{node:process.version,platform:process.platform,arch:process.arch},native:{abi:383,sha256:hash(native)},wasm:{abi:33,scene:32,painter:15,sha256:hash(wasm),rawBytes:wasm.length,gzipBytes:gzipSync(wasm).length},sources,cases,gates:{fiveViewsWithinExisting16Handles8Data:true,parkTwoEnginesForPageOverlap:true,failedPagePreservesOldPage:true,outstandingReadSettledBeforeAck:true,crossInstanceActualHandleCollisionRejected:true,effectiveSelectedAlphaDirectAndClusterDensity:true},limitations:['typed internal foundation; no public selected interaction controller','no selected frozen export or selected host journey claim','no massive timing or memory performance claim']};
  await mkdir(dirname(process.env.XYG_SELECTED_REPORT),{recursive:true});await writeFile(process.env.XYG_SELECTED_REPORT,JSON.stringify(report,null,2)+'\n');
 }
 console.log('selected native383/packagedWASM33 direct+reduced/indexed fullXYSE/Rows intent, i64MIN/u64MAX, consumption/failure, private continuation, exact packet parity, fiveview16handle/8Data pressure+explicitpark+failedpage recovery, outstanding-read cancellation/ACK/recovery and actualtwoWASMregistry handlecollision rejection PASS');
}
finally{assert.equal(x.xyg_wasm_instance_dispose(h),0);}
