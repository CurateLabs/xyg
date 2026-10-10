// Real native and packaged WASM selected hierarchy owners; Rust is the oracle.
import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile,writeFile} from 'node:fs/promises';
import {createHash} from 'node:crypto';
import {RetainedGeoSource,attachRetainedFrame} from '../src/geo-retained.js';
import {GeoHierarchy,GeoHierarchyUnsupportedSelected,hierarchyLaneAuthority,isHierarchyFrame} from '../src/geo-hierarchy.js';
import {GeoHierarchyPublicationUncertain,encodeGeoHierarchyRequest,driveGeoHierarchy,prepareGeoHierarchyScene} from '../src/geo-hierarchy-wire.js';
import {createGeoSelectedScope,GeoSelectedState} from '../src/geo-selected.js';
import {encodeGeoScaleRequest as encode,encodeGeoChunkRequest,encodeGeoScaleStyle,decodeGeoScaleReply,nativeGeoScaleBridge,driveGeoSession,prepareGeoSceneData} from '../src/geoscale.js';
import {encodeGeoSnapshotRequest,decodeGeoSnapshotReply,nativeGeoSnapshotBridge} from '../src/geo-snapshot.js';
const MAX=(1n<<64n)-1n,MIN=-(1n<<63n),HIGH=9007199254740993n;
const budget={processorBytes:128<<20,maxRowsExamined:1000000n,maxReadBytes:128n<<20n,maxChunks:65536,pageRows:4096};
const style=()=>encodeGeoScaleStyle({fill:Uint8Array.of(255,0,0,255),stroke:new Uint8Array(4),strokeWidth:0,diameter:6,opacity:1,symbol:0});
const fill=()=>Uint8Array.of(0,255,0,255);
const descriptor=multi=>{const vertices=multi?6:3,out=new Uint8Array(64+vertices*16+8+32+(multi?24:0)),v=new DataView(out.buffer);out.set([88,89,71,68]);[1,multi?4:1,4326,1,0].forEach((n,i)=>v.setUint32(4+i*4,n,true));v.setBigUint64(24,4n,true);v.setBigUint64(32,BigInt(vertices),true);v.setBigUint64(40,multi?5n:0n,true);let at=64;for(let row=0;row<3;row++)for(let vertex=0;vertex<(multi?2:1);vertex++){v.setFloat64(at,(row-1)*0.0001+vertex*1e-7,true);at+=16;}out.set([1,1,1,0],at);at+=8;[MAX,HIGH,MAX,1n<<63n].forEach((n,i)=>v.setBigUint64(at+i*8,n,true));at+=32;if(multi)[0,2,4,6,6].forEach((n,i)=>v.setUint32(at+i*4,n,true));return out;};
const rawWasmBridges=new WeakSet();
async function host(name){if(name==='native')return{bridge:nativeGeoScaleBridge(budget.processorBytes),snapshot:nativeGeoSnapshotBridge(budget.processorBytes),dispose(){}};
 const artifact=await readFile(process.env.XYG_HIERARCHY_WASM??new URL('../../xy-client/dist/xyg-wasm.wasm',import.meta.url)),{instance}=await WebAssembly.instantiate(artifact,{}),x=instance.exports,id=x.xyg_wasm_instance_new(budget.processorBytes);assert.ok(id);let sequence=0;
 async function call(request,method){assert.equal(x.xyg_wasm_arena_resize(id,request.byteLength),0);new Uint8Array(x.memory.buffer,x.xyg_wasm_arena_ptr(id)>>>0,request.byteLength).set(new Uint8Array(request));const status=x[method](id,++sequence,0,request.byteLength);if(status){const error=new Error(`WASM${status}:`+new TextDecoder().decode(new Uint8Array(x.memory.buffer,x.xyg_wasm_last_error_ptr(id)>>>0,x.xyg_wasm_last_error_len(id))));error.wasmStatus=status;error.nativeCode=status===3?-9:status;throw error;}return new Uint8Array(x.memory.buffer,x.xyg_wasm_output_ptr(id)>>>0,x.xyg_wasm_output_len(id)).slice().buffer;}
 const bridge={execute:r=>call(r,'xyg_wasm_geo_scale_execute'),read:r=>call(r,'xyg_wasm_geo_scale_read')};rawWasmBridges.add(bridge);return{bridge,snapshot:{execute:r=>call(r,'xyg_wasm_geo_snapshot_execute'),read:r=>call(r,'xyg_wasm_geo_snapshot_read')},dispose(){assert.equal(x.xyg_wasm_instance_dispose(id),0);}};
}
async function setup(bridge,multi=false){
 const chunk=await bridge.read(encodeGeoChunkRequest({descriptor:descriptor(multi),rows:4,intervals:{starts:BigInt64Array.of(MIN,0n,10n,0n),ends:BigInt64Array.of(0n,10n,0n,0n),startValidity:Uint8Array.of(0,1,1,0),endValidity:Uint8Array.of(1,1,0,0)}},budget.processorBytes));
 const builder=decodeGeoScaleReply(await bridge.execute(encode({command:1}))).handle;let manifest;try{await bridge.execute(encode({command:2,handle:builder,payload:chunk}));await bridge.execute(encode({command:3,handle:builder,generation:MAX}));manifest=await bridge.read(encode({command:21,handle:builder}));}finally{await bridge.execute(encode({command:10,handle:builder}));}
 const source=await RetainedGeoSource.create(manifest,()=>chunk,{budget,bridge});const q={camera:{crs:4326,worldWrap:true,centerX:0,centerY:0,zoom:8,width:800,height:600,bearing:0,pitch:0},reducedKind:0,maxCells:32768,previousDirect:true,sourceDigest:source.info.digest,generation:MAX,layerId:MAX,cameraRevision:1n,timeRevision:1n,layerRevision:1n,styleRevision:1n,stateRevision:1n,time:{kind:0},maxProjectedVertices:1000000n};
 const original=await source.update(q,{sequence:1n,style:style()}),scope=await createGeoSelectedScope(bridge,{frameHandle:original.handle,sequence:1n,namespace:777n,layerId:MAX,budget});
 const issue=()=>scope.state({revision:2n,ids:BigUint64Array.of(MAX,1n<<63n),fill:fill(),budget});
 const state=await issue(),stateHandle=state.handle,selectedQuery={...q,stateRevision:2n},payload=new Uint8Array(8);new DataView(payload.buffer).setBigUint64(0,stateHandle,true);let selected;
 // A raw test WebAssembly callback has no canonical host issuer. Author only
 // this prerequisite through Rust nonce0; Scope33 remains typed, while raw
 // WASM43/44 prerequisites below use direct Rust ingress without host authority.
 if(rawWasmBridges.has(bridge)){await bridge.execute(encode({command:35,handle:source.handle,sequence:2n,query:selectedQuery,budget,payload}));await driveGeoSession(bridge,{handle:source.handle,sequence:2n,budget,readChunk:source.readChunk});selected=await prepareGeoSceneData(bridge,{handle:source.handle,sequence:2n,budget,style:style()});}
 else{const begun=await state.begin({command:35,handle:source.handle,sequence:2n,query:selectedQuery,budget});assert.equal(begun.fallback,false);await begun.operation.drive({readChunk:source.readChunk});selected=await begun.operation.prepare(style());}
 attachRetainedFrame(source,selected,2n,encode({command:35,handle:source.handle,sequence:2n,query:selectedQuery,budget,payload}),style());
 const pages=new Map(),options={grid:1024,maxVertices:1000000n,maxWriteBytes:64n<<20n,readPage:t=>pages.get(`${t.namespace}:${t.page}`),writePage:(t,b)=>pages.set(`${t.namespace}:${t.page}`,b.slice())};
 return{source,original,selected,scope,issue,query:selectedQuery,options,pages,async close(){await selected.dispose();await original.dispose();await source.dispose();await scope.dispose();}};
}

const receipts=[];
function receipt(host,caseName,raw){const b=new Uint8Array(raw).slice(),v=new DataView(b.buffer);assert.equal(b.length,256);assert.equal(v.getUint32(0,true),0x5a475958);assert.equal(v.getUint32(4,true),1);assert.equal(v.getBigUint64(24,true),2n);assert.ok([0,20].includes(v.getUint32(8,true)));if(v.getUint32(8,true)===0)assert.ok(v.getBigUint64(16,true)>0n);else assert.equal(v.getBigUint64(16,true),0n);assert.ok(!b.subarray(32).some(x=>x));b.fill(0,16,24);receipts.push({host,case:caseName,raw_sha256:createHash('sha256').update(new Uint8Array(raw)).digest('hex'),normalized_hex:Buffer.from(b).toString('hex')});}
for(const name of ['native','wasm'])for(const mode of ['lost','corrupt'])test(`${name} ${mode}33 recovers same private State and retryable cleanup`,async()=>{
 const h=await host(name),f=await setup(h.bridge);const raw=h.bridge.execute.bind(h.bridge);let failed=true,issued,calls=0;
 const input={revision:2n,ids:BigUint64Array.of(MAX,1n<<63n),fill:fill(),budget};
 const attempt=f.scope.beginState(input);input.ids[0]=1n;
 h.bridge.execute=async request=>{const out=await raw(request);if(new DataView(request).getUint32(8,true)===33){calls++;receipt(name,`${mode}:${calls}`,out);const reply=decodeGeoScaleReply(out);issued??=reply.handle;assert.equal(reply.handle,issued);if(failed){failed=false;if(mode==='lost')throw Error('lost33');const b=out.slice(0);new Uint8Array(b)[0]^=1;return b;}}return out;};
 try{await assert.rejects(attempt.recover());const [state,again]=await Promise.all([attempt.recover(),attempt.recover()]);assert.equal(state,again);assert.equal(state.handle,issued);assert.equal(calls,2);await assert.rejects(f.scope.beginState(input).recover());
  let rejectCleanup=true;h.bridge.execute=async r=>{if(new DataView(r).getUint32(8,true)===10&&rejectCleanup){rejectCleanup=false;throw Error('cleanup rejected');}return raw(r);};await assert.rejects(attempt.dispose());await attempt.dispose();await attempt.dispose();
  const next=f.scope.beginState({...input,ids:BigUint64Array.of(MAX,1n<<63n)});const nextState=await next.recover();assert.notEqual(nextState.handle,issued);await next.dispose();
 }finally{h.bridge.execute=raw;await attempt.dispose();await f.close();h.dispose();}
});
for(const name of ['native','wasm'])test(`${name} nonce attempt cleanup before dispatch allocates once and consumes tombstone`,async()=>{
 const h=await host(name),f=await setup(h.bridge);try{
 const a=f.scope.beginState({revision:2n,ids:BigUint64Array.of(MAX,1n<<63n),fill:fill(),budget});await a.dispose();await assert.rejects(a.recover());
 const b=f.scope.beginState({revision:2n,ids:BigUint64Array.of(MAX,1n<<63n),fill:fill(),budget});const state=await b.recover();const request=encode({command:33,handle:f.scope.handle,budget,payload:(()=>{const p=new Uint8Array(40),v=new DataView(p.buffer);v.setBigUint64(0,2n,true);p.set(fill(),8);v.setBigUint64(16,2n,true);v.setBigUint64(24,MAX,true);v.setBigUint64(32,1n<<63n,true);return p;})()});
 new DataView(request).setBigUint64(24,2n,true);
 if(rawWasmBridges.has(h.bridge)){const payload=new Uint8Array(8);new DataView(payload.buffer).setBigUint64(0,state.handle,true);await h.bridge.execute(encode({command:35,handle:f.source.handle,sequence:3n,query:f.query,budget,payload}));await driveGeoSession(h.bridge,{handle:f.source.handle,sequence:3n,budget,readChunk:f.source.readChunk});}else{const op=await state.begin({command:35,handle:f.source.handle,sequence:3n,query:f.query,budget});await op.operation.drive({readChunk:f.source.readChunk});}await b.dispose();assert.equal(new DataView(await h.bridge.execute(request)).getUint32(8,true),20);
 }finally{await f.close();h.dispose();}
});

for(const name of ['native','wasm'])test(`${name} lost actual10 is settled by retired nonce receipt without a second State`,async()=>{
 const h=await host(name),f=await setup(h.bridge),raw=h.bridge.execute.bind(h.bridge);let lost=true,calls=0;
 const attempt=f.scope.beginState({revision:2n,ids:BigUint64Array.of(MAX,1n<<63n),fill:fill(),budget});const state=await attempt.recover();
 h.bridge.execute=async request=>{const out=await raw(request);if(new DataView(request).getUint32(8,true)===10){calls++;if(lost){lost=false;throw Error('lost10');}}return out;};
 try{await assert.rejects(attempt.dispose());await attempt.dispose();assert.equal(calls,1);assert.throws(()=>state.check());await attempt.dispose();}
 finally{h.bridge.execute=raw;await attempt.dispose();await f.close();h.dispose();}
});
for(const name of ['native','wasm'])test(`${name} five scopes and five serial shared-scope allocations keep original paint`,async()=>{
 const h=await host(name),f=await setup(h.bridge),scopes=[f.scope],attempts=[];
 const input={revision:2n,ids:BigUint64Array.of(MAX,1n<<63n),fill:fill(),budget};
 try{
  for(let i=1;i<5;i++)scopes.push(await createGeoSelectedScope(h.bridge,{frameHandle:f.original.handle,sequence:1n,namespace:1000n+BigInt(i),layerId:MAX,budget}));
  for(const scope of scopes){const a=scope.beginState(input);attempts.push(a);await a.recover();}
  for(const a of attempts)await a.dispose();
  for(let i=0;i<5;i++){const a=f.scope.beginState(input);const state=await a.recover();assert.ok(state.handle);await a.dispose();}
  assert.equal(f.selected.data.selection.id(1),MAX);
 }finally{for(const a of attempts)await a.dispose();for(const s of scopes.slice(1))await s.dispose();await f.close();h.dispose();}
});
for(const name of ['native','wasm'])test(`${name} definite allocation-free handle pressure closes attempt without retrying33`,async()=>{
 const h=await host(name),f=await setup(h.bridge),pressure=[],raw=h.bridge.execute.bind(h.bridge);
 const input={revision:2n,ids:BigUint64Array.of(MAX,1n<<63n),fill:fill(),budget};let calls=0;
 try{for(let i=0;i<12;i++)pressure.push(await f.scope.state(input));h.bridge.execute=r=>{if(new DataView(r).getUint32(8,true)===33)calls++;return raw(r);};const a=f.scope.beginState(input);await assert.rejects(a.recover());await pressure.pop().dispose();await a.dispose();assert.equal(calls,1);const b=f.scope.beginState(input);await b.recover();await b.dispose();assert.equal(f.selected.data.selection.id(1),MAX);
 }finally{h.bridge.execute=raw;for(const s of pressure)await s.dispose();await f.close();h.dispose();}
});
for(const name of ['native','wasm'])test(`${name} nonce tombstone cannot reconstruct consumed43 Query or44 Data`,async()=>{
 const h=await host(name),f=await setup(h.bridge),raw=h.bridge.execute.bind(h.bridge);let captured,root,op,frame;
 h.bridge.execute=r=>{if(new DataView(r).getUint32(8,true)===33)captured=r.slice(0);return raw(r);};
 const attempt=f.scope.beginState({revision:2n,ids:BigUint64Array.of(MAX,1n<<63n),fill:fill(),budget});
 try{const state=await attempt.recover();root=await GeoHierarchy.fromSelectedFrame(f.selected,f.source,f.options);
  if(rawWasmBridges.has(h.bridge)){
   // Only fixture setup uses raw nonce0 Rust ingress. A custom WASM callback
   // cannot mint the genuine producer capability required by typed43 recovery.
   const payload=new Uint8Array(8);new DataView(payload.buffer).setBigUint64(0,state.handle,true);
   const request=encodeGeoHierarchyRequest({command:43,handle:root.handle,sequence:3n,query:f.query,budget,payload});
   assert.equal(new DataView(request).getBigUint64(240,true),0n);await raw(request);
   op={drive:()=>driveGeoHierarchy(h.bridge,{handle:state.handle,sequence:3n,budget,readChunk:f.source.readChunk,...f.options}),
    prepare:async()=>{const result=await prepareGeoHierarchyScene(h.bridge,{command:44,handle:state.handle,sequence:3n,budget,style:style()});attachRetainedFrame(f.source,result,3n,request,style());op=undefined;return result;},
    dispose:()=>raw(encodeGeoHierarchyRequest({command:10,handle:state.handle,sequence:3n}))};
  }else op=await root.beginSelected(state,f.query,{sequence:3n});
  let out=await raw(captured);assert.equal(new DataView(out).getUint32(8,true),20);assert.equal(new DataView(out).getBigUint64(16,true),0n);assert.equal(new DataView(out).getBigUint64(24,true),2n);await op.drive();frame=await op.prepare(style());out=await raw(captured);assert.equal(new DataView(out).getUint32(8,true),20);receipt(name,'retiredData',out);await attempt.dispose();const rows=await frame.rows();assert.equal(rows.data.record(0).featureId,MAX);await rows.dispose();}
 finally{h.bridge.execute=raw;if(op)await op.dispose();await attempt.dispose();if(frame)await frame.dispose();if(root)await root.dispose();await f.close();h.dispose();}
});
test('two actual WASM producers with colliding handles reject edited Scope bridge before33',async()=>{
 const a=await host('wasm'),b=await host('wasm'),fa=await setup(a.bridge),fb=await setup(b.bridge,true);const original=fa.scope.bridge;let calls=0,execute=b.bridge.execute.bind(b.bridge);
 try{assert.equal(fa.scope.handle,fb.scope.handle);b.bridge.execute=r=>{calls++;return execute(r);};fa.scope.bridge=b.bridge;assert.throws(()=>fa.scope.beginState({revision:2n,ids:BigUint64Array.of(MAX),fill:fill(),budget}),/producer changed/);assert.equal(calls,0);}
 finally{fa.scope.bridge=original;b.bridge.execute=execute;await fa.close();await fb.close();a.dispose();b.dispose();}
});

test('complete normalized native/WASM nonce controls match after original handle validation',async()=>{
 const cases=new Set(receipts.map(r=>r.case));for(const c of cases){const pair=receipts.filter(r=>r.case===c);assert.equal(pair.length,2);assert.deepEqual(new Set(pair.map(r=>r.host)),new Set(['native','wasm']));assert.equal(pair[0].normalized_hex,pair[1].normalized_hex);}
 if(process.env.XYG_NONCE_REPORT)await writeFile(process.env.XYG_NONCE_REPORT,JSON.stringify({ok:true,pairs:cases.size,normalization:'Only per-registry handle bytes16..24 after original State handle/revision/full-frame validation',receipts},null,2)+'\n');
});
for(const name of ['native','wasm'])for(const status of [6,-1])test(`${name} post-allocation status${status} remains uncertain and recovers exact State`,async()=>{
 const h=await host(name),f=await setup(h.bridge),raw=h.bridge.execute.bind(h.bridge);let fail=true,handle,calls=0;
 const attempt=f.scope.beginState({revision:2n,ids:BigUint64Array.of(MAX,1n<<63n),fill:fill(),budget});
 h.bridge.execute=async r=>{const out=await raw(r);if(new DataView(r).getUint32(8,true)===33){calls++;handle??=decodeGeoScaleReply(out).handle;if(fail){fail=false;const e=Error('after allocation');if(status===6){e.name='XygWasmError';e.status=6;}else e.nativeCode=-1;throw e;}}return out;};
 try{await assert.rejects(attempt.recover());const state=await attempt.recover();assert.equal(state.handle,handle);assert.equal(calls,2);await attempt.dispose();}
 finally{h.bridge.execute=raw;await attempt.dispose();await f.close();h.dispose();}
});
test('delayed actual33 keeps original WASM State producer despite colliding foreign Scope edit',async()=>{
 const a=await host('wasm'),b=await host('wasm'),fa=await setup(a.bridge),fb=await setup(b.bridge,true),execute=a.bridge.execute.bind(a.bridge),foreign=b.bridge.execute.bind(b.bridge);
 let arrived,release,calls=0;const entered=new Promise(r=>arrived=r),gate=new Promise(r=>release=r);
 a.bridge.execute=async r=>{const out=await execute(r);if(new DataView(r).getUint32(8,true)===33){arrived();await gate;}return out;};b.bridge.execute=r=>{calls++;return foreign(r);};
 const attempt=fa.scope.beginState({revision:2n,ids:BigUint64Array.of(MAX,1n<<63n),fill:fill(),budget});
 try{assert.equal(fa.scope.handle,fb.scope.handle);const pending=attempt.recover();await entered;fa.scope.bridge=b.bridge;release();const state=await pending;assert.equal(state.belongsTo(a.bridge),true);assert.equal(state.belongsTo(b.bridge),false);await attempt.dispose();assert.equal(calls,0);}
 finally{release();fa.scope.bridge=a.bridge;a.bridge.execute=execute;b.bridge.execute=foreign;await attempt.dispose();await fa.close();await fb.close();a.dispose();b.dispose();}
});
for(const name of ['native','wasm'])test(`${name} resource rejection during uncertain replay keeps original allocation recoverable`,async()=>{
 const h=await host(name),f=await setup(h.bridge),raw=h.bridge.execute.bind(h.bridge);let step=0,issued;
 const attempt=f.scope.beginState({revision:2n,ids:BigUint64Array.of(MAX,1n<<63n),fill:fill(),budget});
 h.bridge.execute=async r=>{if(new DataView(r).getUint32(8,true)===33){step++;if(step===2){const e=Error('replay stage pressure');e.wasmStatus=3;throw e;}const out=await raw(r);issued??=decodeGeoScaleReply(out).handle;if(step===1)throw Error('lost33');assert.equal(decodeGeoScaleReply(out).handle,issued);return out;}return raw(r);};
 try{await assert.rejects(attempt.recover());await assert.rejects(attempt.recover());assert.equal((await attempt.recover()).handle,issued);await attempt.dispose();}
 finally{h.bridge.execute=raw;await attempt.dispose();await f.close();h.dispose();}
});
