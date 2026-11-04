// Actual native regression using the unchanged boundary harness/fixture packers.
// No WASM asset or stale shipping module is used by this repair proof.
import fs from 'node:fs';
import path from 'node:path';
import {pathToFileURL} from 'node:url';
import {createHash} from 'node:crypto';
import assert from 'node:assert/strict';
const root=process.cwd(), helperPath='packages/xy-node/test/graph-session-wire.test.mjs';
const source=fs.readFileSync(helperPath,'utf8');
let helpers=source.slice(0,source.indexOf('test("standalone temporal owners'));
helpers=helpers.replace(/^const ROOT = .*;$/m,`const ROOT = ${JSON.stringify(root)};`)
  .replace(/"\.\.\/src\/([^"]+)"/g,(_,name)=>JSON.stringify(pathToFileURL(path.join(root,'packages/xy-node/src',name)).href));
helpers+='\nexport {native,ptr,fixture,withResultIds,field,refs,value,request,nativeComplete,graphProjectionCreate,graphProjectionDestroy,temporalGraphCreate,temporalGraphDestroy};\n';
const {native,ptr,fixture,withResultIds,field,refs,value,request,nativeComplete,graphProjectionCreate,graphProjectionDestroy,temporalGraphCreate,temporalGraphDestroy}=await import('data:text/javascript;base64,'+Buffer.from(helpers).toString('base64'));
const {decodeContainer,encodeContainer}=await import(pathToFileURL(path.join(root,'packages/xy-node/src/graphforge-container.js')).href);
const checkpoints=[];
function open(document,instance,positions=true,progressive=false) {
  const c=decodeContainer(document,'XYGF'),n=c.get('node.uuid#0').value.length/16;
  const load=[field('document.bytes','bytes',document)];
  if(positions)load.push(field('load.x.f64','f64',Array.from({length:n},(_,i)=>i*30)),field('load.y.f64','f64',Array(n).fill(0)));
  if(progressive)load.push(field('load.progressive.u8','u8',[1]));
  const bytes=request(instance,0n,1,0,19,load),handle=new BigUint64Array(1);
  assert.equal(native.xyGraphforgeSessionCreate(ptr(document),BigInt(document.length),ptr(bytes),BigInt(bytes.length),instance,0n,native.pointer(handle,'uint64_t *')),0);
  let seq=1,revision=0;
  return {run(op,sections=[],words={}){
    const bytes=request(instance,0n,++seq,revision,op,sections,words);
    const fn=op===18?native.xyGraphforgeSessionBindTemporal:op===21?native.xyGraphforgeSessionRender:native.xyGraphforgeSessionInteract;
    // Existing helper proves zero/short/exact capacity, same-sequence retry bytes.
    const reply=nativeComplete(fn,handle[0],bytes);revision=value(reply,'header.u32')[0];
    checkpoints.push({instance:String(instance),op,seq,sha256:createHash('sha256').update(reply).digest('hex'),selected:value(reply,'selection.indices.u64')?.length??null,steps:value(reply,'relayout.steps.u64')?Array.from(value(reply,'relayout.steps.u64'),String):null});
    return reply;
  },close(){assert.equal(native.xyGraphforgeSessionDestroy(handle[0]),0);}};
}
const original=fixture(),aData=withResultIds(original,{2:'overlay A'}),bData=withResultIds(original,{2:'overlay B'});
const doc=decodeContainer(aData.document,'XYGF'),nodes=doc.get('node.uuid#0').value,edges=doc.get('edge.uuid#0').value;
const flags=doc.get('edge.derived#0').value,sources=doc.get('edge.source#0').value,targets=doc.get('edge.target#0').value;
const edgeIds=[],sourceIds=[],targetIds=[];
flags.forEach((flag,i)=>{if(flag===0){edgeIds.push(...edges.subarray(i*16,i*16+16));sourceIds.push(...nodes.subarray(Number(sources[i])*16,Number(sources[i])*16+16));targetIds.push(...nodes.subarray(Number(targets[i])*16,Number(targets[i])*16+16));}});
const projection=graphProjectionCreate({nodeIds:nodes,edgeIds:new Uint8Array(edgeIds),sourceIds:new Uint8Array(sourceIds),targetIds:new Uint8Array(targetIds)});
const owner=temporalGraphCreate({projectionHandle:projection}),a=open(aData.document,810001n),b=open(bData.document,810002n),fresh=open(bData.document,810003n);
try {
  const bind=[field('temporal.u64','u64',[owner])];
  a.run(18,bind);b.run(18,bind);
  const chosen={...original.exact,result:'overlay A'};
  const selected=a.run(11,[field('refs.bytes','bytes',refs([chosen]))]);
  assert.equal(value(selected,'selection.indices.u64').length,1);
  assert.equal(value(b.run(21),'selection.indices.u64').length,0,'foreign overlay is absent locally, not INVALID');
  assert.equal(value(b.run(18,bind),'selection.indices.u64').length,0,'rebind succeeds without dropping owner selection');
  assert.equal(value(fresh.run(18,bind),'selection.indices.u64').length,0,'initial bind to nonempty foreign owner succeeds');
  const noop=b.run(11,[field('refs.bytes','bytes',refs([]))],{2:1});
  assert.equal(value(noop,'outcome.u32')[2],1,'owner selected count stays global on normal outcomes');
  const retained=a.run(21);
  assert.equal(value(retained,'selection.indices.u64').length,1,'A still owns its selected overlay after every B publication');
  assert.deepEqual(value(retained,'selection.refs.bytes'),value(selected,'selection.refs.bytes'));
} finally {fresh.close();b.close();a.close();temporalGraphDestroy(owner);graphProjectionDestroy(projection);}
const emptyDoc=encodeContainer('XYGF',[
  field('status','u32',[0]),field('kind','utf8','graph'),field('composition.version','u32',[2]),
  field('node.uuid','uuid',new Uint8Array()),field('edge.uuid','uuid',new Uint8Array()),field('edge.derived','u8',[]),
  field('edge.layer','u32',[]),field('edge.order','i64',[]),field('edge.path','u64',[]),field('edge.source','u64',[]),field('edge.target','u64',[]),
]);
const empty=open(emptyDoc,810004n,false,true);
try {for(const result of [empty.run(21),empty.run(15,[],{7:64})]){
  assert.equal(value(result,'relayout.steps.u64')[0],0n);assert.equal(value(result,'relayout.done.u8')[0],1);assert.equal(value(result,'relayout.alpha.f64')[0],1);
}}finally{empty.close();}
console.log(JSON.stringify({node:process.version,wasmUsed:false,helperPath,helperSha256:createHash('sha256').update(source).digest('hex'),nativePath:process.env.XYG_NATIVE_LIB,nativeSha256:createHash('sha256').update(fs.readFileSync(process.env.XYG_NATIVE_LIB)).digest('hex'),checkpoints}));
