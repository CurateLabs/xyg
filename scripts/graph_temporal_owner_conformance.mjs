// Real ordinary-WASM co-ownership regression. Geometry and admission stay Rust-owned.
import assert from 'node:assert/strict';
import {readFile,writeFile} from 'node:fs/promises';
import {createHash} from 'node:crypto';
import {fileURLToPath} from 'node:url';
import {decodeContainer} from '../packages/xy-node/src/graphforge-container.js';
const root=fileURLToPath(new URL('../',import.meta.url));
const bytes=await readFile(process.argv[2]??root+'packages/xy-client/dist/xyg-wasm.wasm');
const fixture=await readFile(root+'tests/fixtures/graph-temporal-owners.json');
const requests=JSON.parse(fixture).requests.map(r=>({...r,bytes:Buffer.from(r.base64,'base64')}));
const fields=decodeContainer(requests[0].bytes,'XYGI'),document=fields.get('document.bytes#0').value;
const columns=decodeContainer(document,'XYGF');
assert.equal(columns.get('node.uuid#0').value.length,16000,'CI fixture must contain only 1k graph nodes');
const {instance}=await WebAssembly.instantiate(bytes,{}),w=instance.exports,cap=16*1024*1024;
const handles=[];let sequence=1;
const make=()=>{const h=w.xyg_wasm_instance_new(cap);assert.notEqual(h,0);handles.push(h);return h;};
const output=h=>Buffer.from(new Uint8Array(w.memory.buffer,w.xyg_wasm_output_ptr(h),w.xyg_wasm_output_len(h)));
const stage=(h,packet)=>{assert.equal(w.xyg_wasm_arena_resize(h,packet.length),0,'staging must fit without changing the declared limit');new Uint8Array(w.memory.buffer,w.xyg_wasm_arena_ptr(h),packet.length).set(packet);};
const graph=(h,r)=>{stage(h,r.bytes);return w[r.operation===19?'xyg_wasm_graphforge_session_open':r.operation===21?'xyg_wasm_graphforge_session_render':'xyg_wasm_graphforge_session_interact'](h,0,r.bytes.length);};
const command=(op,owner=0n,revision=0n,source=Buffer.alloc(0))=>{const b=Buffer.alloc(64+source.length);b.write('XYTJ');b.writeUInt32LE(1,4);b.writeUInt32LE(op,8);b.writeBigUInt64LE(owner,16);b.writeBigUInt64LE(revision,24);source.copy(b,64);return b;};
const temporal=(h,b)=>{stage(h,b);return w.xyg_wasm_temporal_scene_compile(h,sequence++,0,b.length);};
const sourceRows=15000,source=Buffer.alloc(131+sourceRows*40);
source.write('XYTM');source.writeUInt32LE(2,4);source.writeUInt32LE(3,8);source.writeUInt32LE(sourceRows,12);source.writeDoubleLE(900,16);source.writeDoubleLE(420,24);source.writeBigInt64LE(BigInt(sourceRows+1),40);source.writeUInt32LE(3,56);source.writeUInt32LE(2,64);source.writeDoubleLE(1,80);source.write('UTC',128);
for(let i=0;i<sourceRows;i++){const at=131+i*40;source.writeBigInt64LE(BigInt(i),at);source.writeDoubleLE(i,at+16);source.writeBigUInt64LE(BigInt(i+1),at+24);source[at+32]=1;}
try{
 const h=make(),owners=[];let parked=0;
 for(let i=0;i<20;i++){
  assert.equal(temporal(h,command(0)),0);const owner=output(h).readBigUInt64LE(16);owners.push(owner);
  const status=temporal(h,command(1,owner,1n,source));
  if(status!==0){assert.equal(status,3,'only documented resource refusal ends job admission');break;}parked++;
 }
 assert.equal(parked,12,'same bounded pressure as the independent reproduction');
 // A separate instance has its own budget: no accidental global registry charge.
 const other=make();assert.equal(graph(other,requests[0]),0);const acknowledgement=output(other);
 for(const request of requests.slice(1))assert.equal(graph(other,request),0);
 const ordinary=output(other);
 let refused=null,accepted=0;
 for(const request of requests){
  const status=graph(h,request);
  assert.ok(status===0||status===-4,'graph pressure returns success or explicit budget refusal');
  assert.equal(w.xyg_wasm_arena_resize(h,0),0,'graph work must not strand even zero-byte staging');
  if(status===-4){refused=request.operation;break;}accepted++;
 }
 assert.ok(accepted>0,'bounded ingress acknowledgement still fits');
 assert.equal(graph(h,requests[0]),0,'the exact opening retry survives resource pressure');
 assert.deepEqual(output(h),acknowledgement,'refusal preserves the complete accepted graph acknowledgement');
 // Ordinary temporal operations are unavailable while GraphSession is open.
 assert.equal(w.xyg_wasm_graphforge_session_close(h),0);
 for(const owner of owners)assert.equal(temporal(h,command(5,owner)),0,'pre-existing owners must remain closable');
 for(const request of requests)assert.equal(graph(h,request),0,'the identical requests recover after actual temporal release');
 assert.deepEqual(output(h),ordinary,'full graph reply is unchanged after releasing only foreign ownership');
 const report={ok:true,node:process.version,moduleSha256:createHash('sha256').update(bytes).digest('hex'),fixtureSha256:createHash('sha256').update(fixture).digest('hex'),cap,sourceRows,parked,acceptedCommands:accepted,refusedOperation:refused,openingRetryPreserved:true,unrelatedInstanceUnaffected:true,zeroStagingAfterEveryGraphRequest:0,identicalRetryAfterRelease:true,completeGraphReplySha256:createHash('sha256').update(ordinary).digest('hex'),wasmLinearHighWaterSeparateScope:w.memory.buffer.byteLength};
 if(process.env.XYG_GRAPH_TEMPORAL_OWNER_REPORT)await writeFile(process.env.XYG_GRAPH_TEMPORAL_OWNER_REPORT,JSON.stringify(report,null,2)+'\n');console.log(JSON.stringify(report));
}finally{for(const h of handles)assert.equal(w.xyg_wasm_instance_dispose(h),0);}
