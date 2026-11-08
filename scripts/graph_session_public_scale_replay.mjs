// Complete Direct/Aggregate source and membership proof plus exact full-result replay of browser commands; test-only, no product policy.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import {createHash} from 'node:crypto';
import * as native from '../packages/xy-node/src/native.js';
import {decodeContainer,encodeContainer} from '../packages/xy-node/src/graphforge-container.js';
import {ptr,nativeCall,nativeComplete,wasmCall} from '../packages/xy-node/test/graph-session-replay-helpers.mjs';
const report=JSON.parse(fs.readFileSync(process.argv[2],'utf8'));
for(const view of report.views){
 const {instance}=await WebAssembly.instantiate(fs.readFileSync('packages/xy-client/dist/xyg-wasm.wasm'),{}),x=instance.exports;
 let canonical,previous,boundaryChecked=false;
 const handle=new BigUint64Array(1),wasm=x.xyg_wasm_instance_new(view.arena??384*1024*1024);
 try {
  for(const record of view.replay){
   const bytes=Buffer.from(record.request,'base64'),parts=decodeContainer(bytes,'XYGI'),h=parts.get('header.u64#0').value;
   const op=record.operation;
   if(op===19){const d=parts.get('document.bytes#0').value;const document=decodeContainer(d,'XYGF');canonical=document;assert.equal(document.get('node.uuid#0').value.length/16,view.sourceNodes);assert.equal(document.get('edge.uuid#0').value.length/16,view.sourceEdges);assert.equal(native.xyGraphforgeSessionCreate(ptr(d),BigInt(d.length),ptr(bytes),BigInt(bytes.length),h[0],h[1],native.pointer(handle,'uint64_t *')),0);}
   const compare=b=>{assert.equal(b.length,record.replyBytes);assert.equal(createHash('sha256').update(b).digest('hex'),record.replySha256);};
   if(op===15&&view.sourceNodes===1000000&&!boundaryChecked) {
     const alter=(word,number)=>{const fields=decodeContainer(bytes,'XYGI');fields.get('header.u32#0').value[word]=number;return encodeContainer('XYGI',[...fields.values()].map(f=>({...f,values:f.value})));};
     for(const [word,number,status,label]of [[7,3,-4,'6M work exceeds unchanged4M cap'],[0,0xffffffff,-1,'stale revision']]) {
       const invalid=alter(word,number);
       assert.equal(nativeCall(native.xyGraphforgeSessionInteract,handle[0],invalid,0).status,status,label);
       assert.equal(wasmCall(x,wasm,'xyg_wasm_graphforge_session_interact',invalid).status,status,label);
       const retry=Buffer.from(previous.request,'base64');
       const check=b=>assert.equal(createHash('sha256').update(b).digest('hex'),previous.replySha256);
       check(nativeComplete(native.xyGraphforgeSessionRender,handle[0],retry));
       const w=wasmCall(x,wasm,'xyg_wasm_graphforge_session_render',retry);assert.equal(w.status,0);check(w.output);
     }
     console.log(JSON.stringify({id:view.id,boundaries:{threeSteps:-4,staleRevision:-1,priorCacheUnchanged:true,workLimit:4000000,admittedSteps:2}}));
     boundaryChecked=true;
   }
   if(op!==19){const fn=op===21?native.xyGraphforgeSessionRender:native.xyGraphforgeSessionInteract;const first=nativeCall(fn,handle[0],bytes,record.replyBytes);assert.equal(first.status,0,'uncached complete native output capacity remains admitted');compare(first.output);compare(nativeComplete(fn,handle[0],bytes));}
   const reply=wasmCall(x,wasm,op===19?'xyg_wasm_graphforge_session_open':op===21?'xyg_wasm_graphforge_session_render':'xyg_wasm_graphforge_session_interact',bytes);assert.equal(reply.status,0);compare(reply.output);
   const publication=decodeContainer(reply.output,'XYGR');
   const gpu=publication.get('gpu.header.u32#0')?.value;
   if(gpu){
    assert.equal(publication.get('node.flags.u32#0').value.length,view.sourceNodes,'canonical node population');
    assert.equal(publication.get('edge.flags.u32#0').value.length,view.sourceEdges,'canonical edge population');
    const selected=publication.get('selection.indices.u64#0').value,selectedMask=new Uint8Array(view.sourceNodes);
    for(const i of selected){assert.ok(i<BigInt(view.sourceNodes));selectedMask[Number(i)]=1;}
    const focusBytes=publication.get('focus.bytes#0').value;
    const focused=focusBytes.length===8?-1:new DataView(focusBytes.buffer,focusBytes.byteOffset+16,16).getUint32(0,true)-1;
    const nodeFlags=publication.get('node.flags.u32#0').value,edgeFlags=publication.get('edge.flags.u32#0').value;
    for(let i=0;i<nodeFlags.length;i++)assert.equal(nodeFlags[i],(selectedMask[i]?2:0)|(i===focused?128:0),'exact canonical selected/focused source state');
    assert.ok(edgeFlags.every(v=>v===0),'neutral unselected edge state');
    const membership=publication.get('render.member_of.u64#0').value;
    assert.equal(membership.length,view.sourceNodes);
    const tier=publication.get('render.tier.u32#0').value[0];
    const missing=0xffffffffffffffffn;
    const nodes=publication.get('render.node_members.u64#0').value;
    const no=publication.get('render.node_member_offsets.u64#0').value;
    const edges=publication.get('render.edge_members.u64#0').value;
    const eo=publication.get('render.edge_member_offsets.u64#0').value;
    assert.equal(no.length,gpu[2]+1);assert.equal(eo.length,gpu[3]+1);
    assert.equal(no[0],0n);assert.equal(no.at(-1),BigInt(nodes.length));
    assert.equal(eo[0],0n);assert.equal(eo.at(-1),BigInt(edges.length));
    assert.equal(nodes.length,view.sourceNodes,'useful full-circle camera retains complete node membership');
    const seen=new Uint8Array(view.sourceNodes);
    for(let group=0;group<gpu[2];group++)for(let at=Number(no[group]);at<Number(no[group+1]);at++) {
      const i=Number(nodes[at]);assert.ok(i<view.sourceNodes);assert.equal(seen[i]++,0);assert.equal(membership[i],BigInt(group));
    }
    assert.ok(seen.every(v=>v===1));
    const a=canonical.get('edge.source#0').value,b=canonical.get('edge.target#0').value;
    const ra=publication.get('render.edge_source.u64#0').value,rb=publication.get('render.edge_target.u64#0').value;
    const edgeSeen=new Uint8Array(view.sourceEdges);
    for(let group=0;group<gpu[3];group++)for(let at=Number(eo[group]);at<Number(eo[group+1]);at++) {
      const i=Number(edges[at]);assert.ok(i<view.sourceEdges);assert.equal(edgeSeen[i]++,0);
      const x=membership[Number(a[i])],y=membership[Number(b[i])];
      assert.ok((ra[group]===x&&rb[group]===y)||(ra[group]===y&&rb[group]===x),'exact canonical edge endpoint join');
    }
    for(let i=0;i<view.sourceEdges;i++) {
      const x=membership[Number(a[i])],y=membership[Number(b[i])];
      assert.notEqual(x,missing);assert.notEqual(y,missing);
      assert.equal(edgeSeen[i],Number(tier!==2||x!==y),'all and only policy-retained edge membership; intra-cluster omissions disclosed');
    }
    const opacity={};
    for(const kind of ['node','edge']) {
      const values=publication.get(`paint.${kind}.style.bytes#0`).value;
      const bytes=new DataView(values.buffer,values.byteOffset,values.byteLength);
      const alphas=new Set();for(let at=20;at<values.length;at+=60){const v=bytes.getFloat32(at,true);assert.ok(Number.isFinite(v)&&v>=0&&v<=1);alphas.add(v);}
      opacity[kind]=[...alphas].sort();
    }
    if(op===5||op===7||op===1) {
      const ids=canonical.get('node.uuid#0').value;
      const refBytes=publication.get('focus.bytes#0').value;
      const id=refBytes.subarray(16,32),sourceIndex=new DataView(id.buffer,id.byteOffset,16).getUint32(0,true)-1;
      assert.deepEqual([...id],[...ids.subarray(sourceIndex*16,sourceIndex*16+16)],'exact literal focus UUID retained in canonical source');
      const group=Number(membership[sourceIndex]);
      const actions=publication.get('focus.action.ref.bytes#0').value;
      assert.equal(new DataView(actions.buffer,actions.byteOffset,actions.byteLength).getUint32(8,true),tier===2?3:0,'aggregate action identity is explicit');
      if(op===7) {
        const selected=publication.get('selection.indices.u64#0').value;
        assert.deepEqual([...selected].map(Number).sort((a,b)=>a-b),[...nodes.subarray(Number(no[group]),Number(no[group+1]))].map(Number).sort((a,b)=>a-b),'Enter selects exact current focused membership');
      }
      if(op===1) {
        const h=publication.get('pick.header.u32#0').value,q=publication.get('pick.query.u64#0').value;
        assert.equal(h[5],tier===2?2:1,'exact source or aggregate membership pick, never invented source identity');
        if(tier===2){assert.equal(q[4],0n,'unused source placeholder retains existing semantics');assert.equal(publication.get('pick.ref.bytes#0').value.length,8,'aggregate pick carries no invented source ref');assert.equal(q[3],no[Number(q[2])+1]-no[Number(q[2])]);}
        else {assert.equal(q[4],BigInt(view.sourceNodes-1),'last canonical overlapping node wins unchanged reverse paint order');}
        const pickedGroup=Number(q[2]),pickedMembers=[...nodes.subarray(Number(no[pickedGroup]),Number(no[pickedGroup+1]))].map(Number).sort((a,b)=>a-b);
        assert.deepEqual([...publication.get('selection.indices.u64#0').value].map(Number).sort((a,b)=>a-b),pickedMembers,'trusted pointer selects exact picked canonical membership');
        console.log(JSON.stringify({id:view.id,pickForm:h[5],pickKind:h[4],pickGroup:pickedGroup,pickMembers:String(q[3]),sourceIndex: tier===2?null:String(q[4]),sourceUuid:tier===2?null:Buffer.from(ids.subarray(Number(q[4])*16,Number(q[4])*16+16)).toString('hex')}));
      }
      console.log(JSON.stringify({id:view.id,op,focusSourceIndex:sourceIndex,focusUuid:Buffer.from(id).toString('hex'),focusGroup:group}));
    }
    assert.equal(publication.get('header.u32#0').value[1],view.sourceNodes===100000?1:0,'unchanged primitive-cap degradation is explicit');
    assert.deepEqual(opacity,{node:[1],edge:[1]},'neutral resolved opacity stays exact');
    for(const [kind,count,flags,offsets,members] of [['node',gpu[2],nodeFlags,no,nodes],['edge',gpu[3],edgeFlags,eo,edges]]) {
      const state=publication.get(`gpu.${kind}.state.u8#0`).value,visual=publication.get(`render.${kind==='node'?'visual_states':'edge_visual_states'}.u8#0`).value,emphasis=publication.get(`render.${kind==='node'?'emphasis':'edge_emphasis'}.u8#0`).value;
      assert.equal(state.length,count*4);
      for(let group=0;group<count;group++) {
        let joined=0;for(let at=Number(offsets[group]);at<Number(offsets[group+1]);at++)joined|=flags[Number(members[at])]&0x17;
        assert.deepEqual([...state.subarray(group*4,group*4+4)],[visual[group],emphasis[group],joined,0],'GPU state agrees with complete canonical membership');
      }
    }
    const admission=publication.get('relayout.admission.u32#0')?.value;
    assert.deepEqual(Array.from(admission),[1,view.sourceNodes===1000000?2:view.sourceNodes===100000?20:64]);
    console.log(JSON.stringify({id:view.id,op,tier,nodes:gpu[2],edges:gpu[3],nodeMembers:nodes.length,edgeMembers:edges.length,
      canonicalNodes:membership.length,canonicalEdges:edgeSeen.length,degraded:publication.get('header.u32#0').value[1],opacity,replyBytes:reply.output.length}));
   }
   previous=record;
   if(gpu&&view.sourceNodes===100000){assert.equal(gpu[2],view.sourceNodes,'every publication keeps all source nodes');assert.equal(gpu[3],view.sourceEdges,'every publication keeps all source edges');}
  }
  console.log(JSON.stringify({id:view.id,commands:view.replay.length,linearPeak:x.memory.buffer.byteLength,comparison:'full XYGR SHA256: browser/native/WASM'}));
 }finally{assert.equal(native.xyGraphforgeSessionDestroy(handle[0]),0);assert.equal(native.xyGraphforgeSessionDestroy(handle[0]),-10);assert.equal(x.xyg_wasm_graphforge_session_close(wasm),0);assert.equal(x.xyg_wasm_graphforge_session_close(wasm),-10);assert.equal(x.xyg_wasm_instance_dispose(wasm),0);}
}
