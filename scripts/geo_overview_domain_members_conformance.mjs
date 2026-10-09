#!/usr/bin/env node
// Actual native/WASM protocol proof; raw extension framing is test-only.
import assert from 'node:assert/strict';
import {readFile,writeFile} from 'node:fs/promises';
import {createHash} from 'node:crypto';
import {encodeGeoScaleRequest as encode,decodeGeoScaleReply as decode,encodeGeoChunkRequest,encodeGeoScaleStyle,driveGeoSession,prepareGeoSceneData,nativeGeoScaleBridge} from '../packages/xy-node/src/geoscale.js';
import {encodeGeoOverviewRequest,decodeGeoOverviewReply,parseGeoOverviewData,driveGeoOverview,prepareGeoOverviewData} from '../packages/xy-node/src/geo-overview.js';
const budget={processorBytes:128<<20,maxRowsExamined:1000000n,maxReadBytes:128n<<20n,maxChunks:65536,pageRows:4096};
const MAX=0xffffffffffffffffn,MIN=-(1n<<63n),MAX_TIME=(1n<<63n)-1n;
function request(command,handle=0n,sequence=0n,payload,query){
 if([6,7,8,9,10,23,27,28,29,30,31].includes(command))return encodeGeoOverviewRequest({command,handle,sequence,budget,payload,query});
 const b=encode({command:query?5:6,handle,sequence,budget,payload,query});new DataView(b).setUint32(8,command,true);return b;
}
function reply(b){assert.equal(b.byteLength,256);const v=new DataView(b);assert.equal(v.getUint32(0,true),0x5a475958);return {code:v.getUint32(8,true),handle:v.getBigUint64(16,true),sequence:v.getBigUint64(24,true),length:v.getBigUint64(32,true),ticket:new Uint8Array(b,64,128).slice()};}
const {instance}=await WebAssembly.instantiate(await readFile(process.env.XYG_GEO_DOMAIN_MEMBERS_WASM??'packages/xy-client/dist/xyg-wasm.wasm'),{});
const x=instance.exports,wasmInstance=x.xyg_wasm_instance_new(budget.processorBytes);assert.ok(wasmInstance);let wireSeq=0;
async function call(b,read){assert.equal(x.xyg_wasm_arena_resize(wasmInstance,b.byteLength),0);new Uint8Array(x.memory.buffer,x.xyg_wasm_arena_ptr(wasmInstance)>>>0,b.byteLength).set(new Uint8Array(b));const status=x[read?'xyg_wasm_geo_scale_read':'xyg_wasm_geo_scale_execute'](wasmInstance,++wireSeq,0,b.byteLength);if(status)throw Error(`WASM status ${status}: `+new TextDecoder().decode(new Uint8Array(x.memory.buffer,x.xyg_wasm_last_error_ptr(wasmInstance)>>>0,x.xyg_wasm_last_error_len(wasmInstance))));return new Uint8Array(x.memory.buffer,x.xyg_wasm_output_ptr(wasmInstance)>>>0,x.xyg_wasm_output_len(wasmInstance)).slice().buffer;}
const wasm={execute:b=>call(b,false),read:b=>call(b,true)};
async function run(bridge){
 const descriptor=new Uint8Array(176),v=new DataView(descriptor.buffer);descriptor.set([88,89,71,68]);[1,4,4326,1,0].forEach((n,i)=>v.setUint32(4+4*i,n,true));[3n,4n,4n,0n,0n].forEach((n,i)=>v.setBigUint64(24+8*i,n,true));[0,0,0,0,-90,0,90,0].forEach((n,i)=>v.setFloat64(64+i*8,n,true));descriptor.set([1,1,1],128);[MAX,9007199254740993n,7n].forEach((n,i)=>v.setBigUint64(136+8*i,n,true));[0,2,3,4].forEach((n,i)=>v.setUint32(160+4*i,n,true));
 const chunk=await bridge.read(encodeGeoChunkRequest({descriptor,rows:3,intervals:{starts:BigInt64Array.of(MIN,0n,10n),ends:BigInt64Array.of(0n,10n,0n),startValidity:Uint8Array.of(0,1,1),endValidity:Uint8Array.of(1,1,0)}},budget.processorBytes));
 const builder=decode(await bridge.execute(encode({command:1}))).handle;let source,frame,index;const storage=new Map();
 const close=(handle,seq=0n)=>bridge.execute(request(10,handle,seq));
 try{
  for(let i=0;i<2;i++)await bridge.execute(encode({command:2,handle:builder,payload:new Uint8Array(chunk)}));await bridge.execute(encode({command:3,handle:builder,generation:MAX}));const manifest=await bridge.read(encode({command:21,handle:builder}));source=decode(await bridge.execute(encode({command:4,payload:new Uint8Array(manifest),budget}))).handle;
  const readChunk=async()=>chunk,info=(await driveGeoSession(bridge,{handle:source,sequence:0n,budget,readChunk})).source;
  const query={camera:{crs:4326,worldWrap:true,centerX:0,centerY:0,zoom:0,width:800,height:600,bearing:0,pitch:0},reducedKind:0,maxCells:1,previousDirect:true,sourceDigest:info.digest,generation:MAX,layerId:MAX,cameraRevision:1n,timeRevision:1n,layerRevision:1n,styleRevision:1n,stateRevision:1n,time:{kind:0},maxProjectedVertices:1000000n};
  await bridge.execute(encode({command:5,handle:source,sequence:1n,budget,query}));await driveGeoSession(bridge,{handle:source,sequence:1n,budget,readChunk});frame=await prepareGeoSceneData(bridge,{handle:source,sequence:1n,budget,style:encodeGeoScaleStyle({fill:Uint8Array.of(255,0,0,255),stroke:new Uint8Array(4),strokeWidth:0,diameter:6,opacity:1,symbol:0})});
  const ceiling=new Uint8Array(8);new DataView(ceiling.buffer).setBigUint64(0,1000000n,true);index=reply(await bridge.execute(request(27,frame.handle,1n,ceiling))).handle;await frame.dispose();frame=undefined;await close(source);source=undefined;
  async function drive(handle,seq,done){const result=await driveGeoOverview(bridge,{handle,sequence:seq,budget,
   async readChunk(ticket){ticket.raw.fill(0);ticket.encodedBytes=1;ticket.kind=99;return chunk;},
   async readPage(ticket){const key=`${ticket.namespace}:${ticket.page}`,bytes=storage.get(key);assert.ok(bytes);ticket.raw.fill(0);ticket.encodedBytes=1;ticket.namespace=0n;return bytes.slice();},
   async writePage(ticket,bytes){const key=`${ticket.namespace}:${ticket.page}`;storage.set(key,bytes.slice());ticket.raw.fill(0);ticket.encodedBytes=1;ticket.namespace=0n;}});assert.equal(result.code,done);}
  await drive(index,1n,13);const outputs=[];
  const profiles=[{time:{kind:0},cell:136,rows:[0n,3n],id:MAX,matched:2n},{time:{kind:1,instant:MIN},cell:136,rows:[0n,3n],id:MAX,matched:2n},{time:{kind:1,instant:0n},cell:132,rows:[1n,4n],id:9007199254740993n,matched:1n},{time:{kind:1,instant:10n},cell:140,rows:[2n,5n],id:7n,matched:1n},{time:{kind:2,start:MIN,end:0n},cell:136,rows:[0n,3n],id:MAX,matched:2n}];
  for(let i=0;i<profiles.length;i++){
   const profile=profiles[i],seq=BigInt(2+i),q={...query,time:profile.time,maxCells:0,previousDirect:false,maxProjectedVertices:0n};
   const queryHandle=reply(await bridge.execute(request(28,index,seq,undefined,q))).handle;
   await drive(queryHandle,seq,14);
   let prior=reply(await bridge.execute(request(29,queryHandle,seq))).handle,priorSeq=seq;
   await close(queryHandle,seq);
   const all=[];
   for(let page=0;page<3;page++){
    const operation=100n+BigInt(page),payload=new Uint8Array(24),pv=new DataView(payload.buffer);
    pv.setBigUint64(0,operation,true);pv.setUint32(8,profile.cell,true);pv.setBigUint64(16,1000000n,true);
    const command=request(45,prior,priorSeq,payload),bv=new DataView(command);bv.setUint32(60,1,true);
    const handle=reply(await bridge.execute(command)).handle;await close(prior);
    for(;;){const state=reply(await bridge.execute(request(6,handle,operation)));if(state.code===21)break;assert.equal(state.code,1);const t=state.ticket;const tv=new DataView(t.buffer,t.byteOffset,t.byteLength);assert.equal(tv.getBigUint64(16,true),operation);assert.equal(tv.getUint32(24,true),1);assert.equal(tv.getBigUint64(56,true),BigInt(chunk.byteLength));const p=new Uint8Array(128+chunk.byteLength);p.set(t);p.set(new Uint8Array(chunk),128);await bridge.execute(request(7,handle,operation,p));p.fill(0);await bridge.execute(request(8,handle,operation,t));}
    // A failed publish preserves the completed Query and consumes no Data slot.
    if(page===0){const bad=request(46,handle,operation);new DataView(bad).setBigUint64(32,1n,true);await assert.rejects(bridge.execute(bad));assert.equal(reply(await bridge.execute(request(6,handle,operation))).code,21);}
    const published=reply(await bridge.execute(request(46,handle,operation)));assert.equal(published.handle,handle);
    assert.deepEqual(reply(await bridge.execute(request(6,handle,operation))),published);
    await assert.rejects(bridge.execute(request(46,handle,operation)));
    let packet=await bridge.read(request(23,handle,operation)),d=new DataView(packet);assert.equal(d.getUint32(0,true),0x4d4f5958);assert.equal(d.getUint32(4,true),1);assert.equal(d.getUint32(8,true),3);assert.equal(d.getUint32(12,true),16);assert.equal(d.getBigUint64(16,true),handle);assert.equal(d.getBigUint64(24,true),operation);assert.equal(d.getUint32(40,true),profile.cell);assert.equal(d.getBigUint64(48,true),BigInt(profile.rows.length)*profile.matched);assert.equal(d.getBigUint64(96,true),MAX);assert.equal(d.getBigUint64(64,true),6n);assert.equal(d.getBigUint64(72,true),MAX);assert.equal(d.getUint32(216,true),profile.time.kind);assert.equal(d.getUint32(104,true),4326);assert.equal(d.getUint32(108,true),4);assert.equal(d.getUint32(112,true),4326);assert.equal(d.getUint32(116,true),1);for(const [at,value] of [[120,0],[128,0],[136,0],[144,800],[152,600],[160,0],[168,0]])assert.equal(d.getFloat64(at,true),value);for(const at of [176,184,192,200,208])assert.equal(d.getBigUint64(at,true),1n);assert.equal(d.getBigInt64(224,true),profile.time.instant??profile.time.start??0n);assert.equal(d.getBigInt64(232,true),profile.time.end??0n);assert.equal(d.getBigUint64(56,true),BigInt(Math.min(page+1,2))*profile.matched);assert.equal(d.getBigUint64(240,true),page<2?profile.matched:0n);assert.equal(d.getBigUint64(248,true),0n);
    if(page<2){assert.equal(d.getBigUint64(32,true),1n);assert.equal(d.getBigUint64(256,true),profile.id);assert.equal(d.getBigUint64(264,true),profile.rows[page]);assert.equal(d.getUint32(272,true),page);assert.equal(d.getUint32(276,true),i===2?1:i===3?2:0);assert.equal(d.getBigUint64(280,true),profile.matched);all.push(d.getBigUint64(264,true));}else {assert.equal(packet.byteLength,256);assert.equal(d.getUint32(44,true),0);}
    const normalized=new Uint8Array(packet.slice(0));normalized.fill(0,16,24);outputs.push(Buffer.from(normalized));d=undefined;packet=undefined;
    // Transfer copies drop before lease disposal; the lifetime third-read gate remains exact.
    await bridge.read(request(23,handle,operation));await assert.rejects(bridge.read(request(23,handle,operation)));
    prior=handle;priorSeq=operation;
   }
   assert.deepEqual(all,profile.rows);await close(prior);
  }
  await close(index,1n);index=undefined;return outputs;
 }finally{if(frame)await frame.dispose();if(source)await close(source);if(index)await close(index,1n);await close(builder);}
}
try{
 const native=await run(nativeGeoScaleBridge(budget.processorBytes)),browser=await run(wasm);assert.deepEqual(native,browser);
 if(process.env.XYG_GEO_DOMAIN_MEMBERS_REPORT)await writeFile(process.env.XYG_GEO_DOMAIN_MEMBERS_REPORT,JSON.stringify({cases:5,pages:15,normalization:'validated process-local MemberData owner bytes16..24 only',packets:native.map(b=>({sha256:createHash('sha256').update(b).digest('hex'),base64:b.toString('base64')})),limitations:['bounded canonical source scan','allocating45 lost-reply recovery unresolved','no host factory or massive latency claim']},null,2)+'\n');
 console.log('overview domain membership: 5 temporal profiles,15 complete native/WASM packets, MultiPoint row union/full IDs, exact private ACK, failed46 retry/lost46 probe, two-copy quota PASS');
}finally{assert.equal(x.xyg_wasm_instance_dispose(wasmInstance),0);}
