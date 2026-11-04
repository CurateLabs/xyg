// Bounded P1 replay through the existing actual C ABI/WASM test harness.
// Reuse its unmodified helpers/oracles; no alternate product encoder/policy.
import fs from 'node:fs';
import path from 'node:path';
import {pathToFileURL} from 'node:url';
import {createHash} from 'node:crypto';
import assert from 'node:assert/strict';
const root=process.cwd();
const helperPath='packages/xy-node/test/graph-session-wire.test.mjs';
const source=fs.readFileSync(helperPath,'utf8');
let helpers=source.slice(0,source.indexOf('test("standalone temporal owners'))
  +source.slice(source.indexOf('function openPair('),source.indexOf('test("actual native ABI and real WASM replay'));
helpers=helpers.replace(/^const ROOT = .*;$/m,`const ROOT = ${JSON.stringify(root)};`)
  .replace(/"\.\.\/src\/([^"]+)"/g,(_,name)=>JSON.stringify(pathToFileURL(path.join(root,'packages/xy-node/src',name)).href));
helpers+='\nexport {fixture,withResultIds,openPair,field,refs,value};\n';
const {fixture,withResultIds,openPair,field,refs,value}=await import('data:text/javascript;base64,'+Buffer.from(helpers).toString('base64'));
const {decodeContainer,encodeContainer,DTYPE}=await import(pathToFileURL(path.join(root,'packages/xy-node/src/graphforge-container.js')).href);
const wasmPath=process.env.XYG_SESSION_WASM??'packages/xy-client/dist/xyg-wasm.wasm';
const wasm=fs.readFileSync(wasmPath),{instance}=await WebAssembly.instantiate(wasm,{});
const long=' 空白 λ 🦀 '.repeat(600);
const data=withResultIds(fixture(),{0:null,1:'',2:long});
data.exact={...data.exact,result:long};
data.load=[field('document.bytes','bytes',data.document),field('load.progressive.u8','u8',[1]),
  field('load.seed.u64','u64',[73n]),field('load.cose.f64','f64',[2,0.7,0.02,0.97,0.15,3]),
  field('load.cose.bounds.f64','f64',[-20,-20,20,20])];
const pair=openPair(instance.exports,data,910001n,0n);
const checkpoints=[];
const record=(bytes,label)=>{
  const steps=value(bytes,'relayout.steps.u64');
  checkpoints.push({label,steps:steps?[...steps].map(String):null,sha256:createHash('sha256').update(bytes).digest('hex'),bytes:bytes.length});
  const sections=decodeContainer(bytes,'XYGR');
  assert.deepEqual([...value(bytes,'selection.result_ids.valid.u8')],[0,1,1]);
  assert.deepEqual([...value(bytes,'selection.result_ids.texts')],['','',long]);
  const refs=value(bytes,'selection.refs.bytes'),n=new DataView(refs.buffer,refs.byteOffset,refs.byteLength).getUint32(0,true);
  assert.equal(value(bytes,'selection.indices.u64').length,n);
  const offsets=value(bytes,'selection.layer_offsets.u64'),rows=value(bytes,'selection.rows.u64');
  assert.equal(offsets.length,n+1);assert.equal(offsets[0],0n);assert.equal(offsets.at(-1),BigInt(rows.length));
  assert.ok(![...rows].includes(0xffffffffffffffffn));
  assert.equal(value(bytes,'selection.layers.u32').length,rows.length);
  assert.ok(!sections.has('outbound.bytes#0'),'unlinked snapshots remain complete');
  return bytes;
};
try {
  const first=record(pair.run(21),'first');assert.deepEqual([...value(first,'relayout.steps.u64')],[1n]);
  const both=record(pair.run(10,[field('uuids.uuid','uuid',data.nodes.subarray(0,16))]),'shared-uuid');
  assert.equal(value(both,'selection.indices.u64').length,2);
  const doc=decodeContainer(data.document,'XYGF');
  const derived=doc.get('edge.derived#0').value,orders=doc.get('edge.order#0').value;
  const index=derived.findIndex((v,i)=>v===1&&orders[i]===-1n);
  assert.ok(index>=0);
  const layer=doc.get('edge.layer#0').value[index];
  const pairRef={kind:2,layer,path:0xffffffffffffffffn,order:doc.get(`layer.edge_rows#${layer}`).value[index],result:''};
  const selection=[data.exact,pairRef];
  const selected=record(pair.run(11,[field('refs.bytes','bytes',refs(selection))]),'derived-path-pair');
  assert.equal(value(selected,'selection.indices.u64').length,2);
  const noop=record(pair.run(11,[field('refs.bytes','bytes',refs(selection))]),'noop');
  assert.equal(new DataView(value(noop,'changed.refs.bytes').buffer).getUint32(0,true),0);
  const camera=record(pair.run(21,[field('camera.f64','f64',[1,1,0,0,800,600,1])]),'camera');
  assert.deepEqual([...value(camera,'relayout.steps.u64')],[1n]);
  for(const [chunk,steps] of [[1,2n],[7,9n],[16,25n]]) {
    const reply=record(pair.run(15,[],{7:chunk}),`chunk-${chunk}`);
    assert.deepEqual([...value(reply,'relayout.steps.u64')],[steps]);
  }
  pair.run(10,[field('uuids.uuid','uuid',data.nodes.subarray(0,16))]);
  const nodeRows=doc.get('layer.node_rows#0');assert.ok(nodeRows);
  nodeRows.value[0]=(1n<<62n)+19n;
  const replacement=encodeContainer('XYGF',[...doc.values()].map(s=>({...s,values:s.value})));
  const updated=record(pair.run(20,data.load.map(s=>s.name==='document.bytes'?{...s,values:replacement}:s)),'replacement');
  assert.ok([...value(updated,'selection.rows.u64')].includes((1n<<62n)+19n));
  const clear=record(pair.run(4),'clear');assert.deepEqual([...value(clear,'selection.layer_offsets.u64')],[0n]);
  console.log(JSON.stringify({diagnosticOnly:!!process.env.XYG_SESSION_WASM,shippingGatePassed:!process.env.XYG_SESSION_WASM,
    helperPath,helperSha256:createHash('sha256').update(source).digest('hex'),node:process.version,wasmPath,
    wasmSha256:createHash('sha256').update(wasm).digest('hex'),checkpoints}));
} finally {pair.close();}
