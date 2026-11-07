// Exact full-result replay of browser commands; test-only, no product policy.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import {createHash} from 'node:crypto';
import * as native from '../packages/xy-node/src/native.js';
import {decodeContainer} from '../packages/xy-node/src/graphforge-container.js';
import {ptr,nativeComplete,wasmCall} from '../packages/xy-node/test/graph-session-replay-helpers.mjs';
const report=JSON.parse(fs.readFileSync(process.argv[2],'utf8'));
for(const view of report.views){
 const {instance}=await WebAssembly.instantiate(fs.readFileSync('packages/xy-client/dist/xyg-wasm.wasm'),{}),x=instance.exports;
 let canonical;
 const handle=new BigUint64Array(1),wasm=x.xyg_wasm_instance_new(view.arena??384*1024*1024);
 try {
  for(const record of view.replay){
   const bytes=Buffer.from(record.request,'base64'),parts=decodeContainer(bytes,'XYGI'),h=parts.get('header.u64#0').value;
   const op=record.operation;
   if(op===19){const d=parts.get('document.bytes#0').value;const document=decodeContainer(d,'XYGF');canonical=document;assert.equal(document.get('node.uuid#0').value.length/16,view.sourceNodes);assert.equal(document.get('edge.uuid#0').value.length/16,view.sourceEdges);assert.equal(native.xyGraphforgeSessionCreate(ptr(d),BigInt(d.length),ptr(bytes),BigInt(bytes.length),h[0],h[1],native.pointer(handle,'uint64_t *')),0);}
   const compare=b=>{assert.equal(b.length,record.replyBytes);assert.equal(createHash('sha256').update(b).digest('hex'),record.replySha256);};
   if(op!==19)compare(nativeComplete(op===21?native.xyGraphforgeSessionRender:native.xyGraphforgeSessionInteract,handle[0],bytes));
   const reply=wasmCall(x,wasm,op===19?'xyg_wasm_graphforge_session_open':op===21?'xyg_wasm_graphforge_session_render':'xyg_wasm_graphforge_session_interact',bytes);assert.equal(reply.status,0);compare(reply.output);
   const publication=decodeContainer(reply.output,'XYGR');
   const gpu=publication.get('gpu.header.u32#0')?.value;
   if(gpu){
    assert.equal(publication.get('node.flags.u32#0').value.length,view.sourceNodes,'canonical node population');
    assert.equal(publication.get('edge.flags.u32#0').value.length,view.sourceEdges,'canonical edge population');
    const membership=publication.get('render.member_of.u64#0').value;
    assert.equal(membership.length,view.sourceNodes);
    assert.equal(publication.get('render.tier.u32#0').value[0],gpu[3]<view.sourceEdges?1:0,'native tier records viewport edge omission');
    assert.equal(publication.get('render.node_x.f64#0').value.length,gpu[2]);
    assert.equal(publication.get('render.edge_source.u64#0').value.length,gpu[3]);
    const nodes=publication.get('render.node_members.u64#0').value,edges=publication.get('render.edge_members.u64#0').value;
    assert.equal(new Set(nodes.map(String)).size,gpu[2]);assert.equal(new Set(edges.map(String)).size,gpu[3]);
    for(const i of nodes)assert.ok(i<BigInt(view.sourceNodes));for(const i of edges)assert.ok(i<BigInt(view.sourceEdges));
    const missing=0xffffffffffffffffn;
    for(let i=0;i<membership.length;i++)if(membership[i]!==missing)assert.equal(nodes[Number(membership[i])],BigInt(i),'exact source/render node join');
    const a=canonical.get('edge.source#0').value,b=canonical.get('edge.target#0').value;
    const expected=Array.from(a,(_,i)=>i).filter(i=>membership[Number(a[i])]!==missing&&membership[Number(b[i])]!==missing);
    assert.deepEqual(Array.from(edges,String),expected.map(String),'all and only Rust-visible source edges; no stride sampling');
    const offsets=publication.get('render.edge_member_offsets.u64#0').value;
    for(let i=0;i<gpu[3];i++)assert.equal(offsets[i+1]-offsets[i],1n,'no edge aggregation');
   }
   if(gpu&&view.sourceNodes===10000){assert.equal(gpu[2],view.sourceNodes,'every publication keeps all source nodes');assert.equal(gpu[3],view.sourceEdges,'every publication keeps all source edges');}
  }
  console.log(JSON.stringify({id:view.id,commands:view.replay.length,linearPeak:x.memory.buffer.byteLength,comparison:'full XYGR SHA256: browser/native/WASM'}));
 }finally{assert.equal(native.xyGraphforgeSessionDestroy(handle[0]),0);assert.equal(x.xyg_wasm_graphforge_session_close(wasm),0);assert.equal(x.xyg_wasm_instance_dispose(wasm),0);}
}
