import assert from 'node:assert/strict';
import fs from 'node:fs';
import {spawnSync} from 'node:child_process';
import test from 'node:test';
import {TemporalGraph, FrozenTemporalGraph} from '../src/index.js';
import {decodeContainer} from '../src/graphforge-container.js';
const root=new URL('../../../',import.meta.url);
const fixture=JSON.parse(fs.readFileSync(new URL('../../../tests/fixtures/temporal/frozen-history.json',import.meta.url)));
const ids=values=>Uint8Array.from(values.flatMap(v=>Array(16).fill(v)));
function graph(){return new TemporalGraph({nodeIds:ids(fixture.nodes),edgeIds:ids(fixture.edges),sourceIds:ids(fixture.sources),targetIds:ids(fixture.targets),nodeValidFrom:{values:BigInt64Array.from(fixture.validFrom,BigInt),validity:new Uint8Array(3).fill(1)},nodeValidTo:{values:BigInt64Array.from(fixture.validTo,BigInt),validity:new Uint8Array(3).fill(1)}});}
const publish=(g,f)=>g.frame({revision:BigInt(f.revision),cursor:BigInt(f.cursor),range:fixture.range.map(BigInt)});
const freeze=(g,revision,extra={})=>g.freeze({revision:BigInt(revision),timezone:fixture.timezone,window:fixture.window.map(BigInt),...extra});
test('public native freeze history, exact canonical Python bytes, import and lifetime',()=>{
  const g=graph(), snapshots=[];
  try{
    g.setSelection({nodes:ids([3]),edges:ids([13])}).setFocus({kind:'node',id:ids([3])}).setPinned(ids([3]));
    for(const frame of fixture.frames){
      publish(g,frame);
      const f=freeze(g,frame.revision),raw=f.toBytes();snapshots.push([f,raw]);const m=f.metadata;
      assert.deepEqual(m['visible.node.uuid'],ids(frame.nodes));assert.deepEqual(m['visible.edge.uuid'],ids(frame.edges));
      assert.deepEqual(m['selected.node.uuid'],ids([3]));assert.deepEqual(m['selected.edge.uuid'],ids([13]));assert.deepEqual(m['pinned.node.uuid'],ids([3]));assert.deepEqual(m['focus.uuid'],ids([3]));
      assert.deepEqual(m.time,[BigInt(frame.cursor),0n,40n]);assert.deepEqual(m.window,[0n,40n]);assert.equal(m.timezone,fixture.timezone);
      assert.equal(m.identity[1],BigInt(frame.revision));assert.deepEqual(m['render.identity'],[0n,0n]);
      m['selected.node.uuid'].fill(0);assert.deepEqual(f.metadata['selected.node.uuid'],ids([3]));
      assert.throws(()=>{m.time=[0n,0n,0n];},TypeError);
    }
    const result=spawnSync(process.env.UV??'/home/ubuntu/.local/bin/uv',['run','python','-c',`import base64,json,sys;sys.path.insert(0,'tests');from test_temporal_graph_frozen import graph,publish,freeze,FIXTURE,ids\ng=graph();g.set_selection(nodes=ids([3]),edges=ids([13])).set_focus('node',bytes([3])*16).set_pinned(ids([3]));out=[]\nfor frame in FIXTURE['frames']:\n publish(g,frame)\n with freeze(g,frame['revision']) as f:out.append(base64.b64encode(f.to_bytes()).decode())\ng.close();print(json.dumps(out))`],{cwd:root,encoding:'utf8',env:process.env});
    assert.equal(result.status,0,result.stderr);const python=JSON.parse(result.stdout);
    for(let i=0;i<snapshots.length;i++)assert.deepEqual(snapshots[i][1],new Uint8Array(Buffer.from(python[i],'base64')),'full native canonical bytes across programmatic hosts');
    g.setSelection({nodes:ids([1])}).setFocus(null).setPinned();g.close();
    for(const [f,raw] of snapshots){
      assert.deepEqual(f.toBytes(),raw);
      const imported=FrozenTemporalGraph.fromBytes(raw);try{assert.deepEqual(imported.toBytes(),raw);}finally{imported.close();}
      const peak=BigInt(raw.length*16+65536);
      assert.throws(()=>FrozenTemporalGraph.fromBytes(raw,{budgetBytes:peak-1n}),e=>e.nativeCode===-11);
      const exact=FrozenTemporalGraph.fromBytes(raw,{budgetBytes:peak});exact.close();
      const bad=raw.slice();bad[40]^=1;assert.throws(()=>FrozenTemporalGraph.fromBytes(bad));
      assert.throws(()=>FrozenTemporalGraph.fromBytes(raw.subarray(0,raw.length-1)));
    }
    if(process.env.XYG_FROZEN_RECEIPT)fs.writeFileSync(process.env.XYG_FROZEN_RECEIPT,JSON.stringify({fixture,canonicalSnapshots:snapshots.map(([,raw])=>Buffer.from(raw).toString('hex'))},null,2)+'\n');
  }finally{g.close();for(const [f]of snapshots){f.close();f.close();}}
});
test('invalid/stale scalar, timezone, window and capacity leave accepted frame usable',()=>{
  const g=graph();try{
    publish(g,fixture.frames[0]);
    for(const options of [{budgetBytes:1n},{revision:0n},{revision:1},{timezone:''},{timezone:'UTC\n'},{window:[6n,8n]},{window:[5n,5n]}])assert.throws(()=>freeze(g,1,options));
    publish(g,fixture.frames[1]);assert.throws(()=>freeze(g,1),e=>e.nativeCode===-14);
    const f=freeze(g,2);assert.equal(f.metadata.identity[1],2n);f.close();assert.throws(()=>f.toBytes());
  }finally{g.close();}
});

test('existing native bound publication capture preserves positions, styles and camera', async()=>{
  const native=await import('../src/native.js');
  const abi=await import('../src/abi.js');
  const {freezeTemporalGraph}=await import('../src/temporal-graph-frozen.js');
  const {DTYPE:D,encodeContainer}=await import('../src/graphforge-container.js');
  const {nativeComplete,ptr}=await import('./graph-session-replay-helpers.mjs');
  const doc=encodeContainer('XYGF',[
    ['status',D.u32,[0]],['kind',D.utf8,'graph'],['composition.version',D.u32,[2]],
    ['node.uuid',D.uuid,ids([1,2,3])],['edge.uuid',D.uuid,ids([11,12,13,14])],
    ['edge.derived',D.u8,[0,0,0,0]],['edge.layer',D.u32,[0xffffffff,0xffffffff,0xffffffff,0xffffffff]],
    ['edge.order',D.i64,[-1n,-1n,-1n,-1n]],['edge.path',D.u64,[0xffffffffffffffffn,0xffffffffffffffffn,0xffffffffffffffffn,0xffffffffffffffffn]],
    ['edge.source',D.u64,[0n,0n,1n,0n]],['edge.target',D.u64,[1n,1n,2n,0n]],
    ['node.status',D.u8,[0,1,2]],['edge.status',D.u8,[0,1,2,3]],
  ].map(([name,dtype,values])=>({name,index:0,dtype,values})));
  const request=(seq,op,rev=0,extra=[])=>encodeContainer('XYGI',[
    {name:'header.u64',dtype:D.u64,values:[971123n,9n,BigInt(seq)]},
    {name:'header.u32',dtype:D.u32,values:[rev,op,0,0,0,0,0,0,0]},...extra]);
  const opening=request(1,19,0,[{name:'document.bytes',dtype:D.bytes,values:doc},{name:'load.x.f64',dtype:D.f64,values:fixture.positions.x},{name:'load.y.f64',dtype:D.f64,values:fixture.positions.y}]);
  const projection=abi.graphProjectionCreate({nodeIds:ids(fixture.nodes),edgeIds:ids(fixture.edges),sourceIds:ids(fixture.sources),targetIds:ids(fixture.targets),directed:true});
  let temporal, session=new BigUint64Array(1),frozen;
  try{
    temporal=abi.temporalGraphCreate({projectionHandle:projection});abi.temporalGraphFrame(temporal,{revision:1n,cursor:5n,range:[0n,40n]});
    assert.equal(native.xyGraphforgeSessionCreate(ptr(doc),BigInt(doc.length),ptr(opening),BigInt(opening.length),971123n,9n,native.pointer(session,'uint64_t *')),0);
    const bound=nativeComplete(native.xyGraphforgeSessionBindTemporal,session[0],request(2,18,0,[{name:'temporal.u64',dtype:D.u64,values:[temporal]}]));
    let rev=decodeContainer(bound,'XYGR').get('header.u32#0').value[0];
    const reply=nativeComplete(native.xyGraphforgeSessionRender,session[0],request(3,21,rev,[{name:'camera.f64',dtype:D.f64,values:fixture.camera}]));
    rev=decodeContainer(reply,'XYGR').get('header.u32#0').value[0];
    frozen=freezeTemporalGraph(temporal,{revision:1n,timezone:'UTC',sessionHandle:session[0],renderRevision:rev});
    assert.deepEqual(frozen.metadata['render.publication'],reply);assert.deepEqual(frozen.metadata['render.document'],doc);assert.deepEqual(frozen.metadata['render.camera'],fixture.camera);
    const raw=frozen.toBytes();assert.equal(native.xyGraphforgeSessionDestroy(session[0]),0);session[0]=0n;abi.temporalGraphDestroy(temporal);temporal=null;
    assert.deepEqual(frozen.toBytes(),raw);const imported=FrozenTemporalGraph.fromBytes(raw);imported.close();
  }finally{frozen?.close();if(session[0])native.xyGraphforgeSessionDestroy(session[0]);if(temporal!=null)abi.temporalGraphDestroy(temporal);abi.graphProjectionDestroy(projection);}
});

test('native import refuses independently rechecksummed malformed publication planes',()=>{
  const result=spawnSync(process.env.UV??'/home/ubuntu/.local/bin/uv',['run','python','-c',`import base64,json,sys;sys.path.insert(0,'tests');from test_temporal_graph_frozen import PUBLICATION_MUTATIONS,malformed_retained_publication
print(json.dumps([base64.b64encode(malformed_retained_publication(name,values)).decode() for name,values in PUBLICATION_MUTATIONS]))`],{cwd:root,encoding:'utf8',env:process.env,maxBuffer:8*1024*1024});
  assert.equal(result.status,0,result.stderr);
  const mutations=JSON.parse(result.stdout);assert.equal(mutations.length,24);
  for(const [index,encoded] of mutations.entries())assert.throws(()=>FrozenTemporalGraph.fromBytes(new Uint8Array(Buffer.from(encoded,'base64'))),`malformed publication #${index}`);
});
