// Small canonical binary fixture shared by actual native/WASM/browser proofs.
import {encodeGeoScaleRequest as encode,decodeGeoScaleReply as decode,encodeGeoChunkRequest,encodeGeoScaleStyle,driveGeoSession,prepareGeoSceneData} from '../../packages/xy-node/src/geoscale.js';
import {encodeGeoOverviewRequest,decodeGeoOverviewReply,driveGeoOverview} from '../../packages/xy-node/src/geo-overview.js';
import {encodeGeoSnapshotRequest,decodeGeoSnapshotReply} from '../../packages/xy-node/src/geo-snapshot.js';
export const BUDGET={processorBytes:128<<20,maxRowsExamined:1000000n,maxReadBytes:128n<<20n,maxChunks:65536,pageRows:4096};
export const MAX=0xffffffffffffffffn;
export function check(value,message){if(!value)throw Error(message);}
export function scaleRequest(command,handle=0n,sequence=0n,payload){const b=encode({command:6,handle,sequence,budget:BUDGET,payload});new DataView(b).setUint32(8,command,true);return b;}
export function snapshotRequest(command,handle,options){const b=encodeGeoSnapshotRequest(command===6?1:command,handle,options);if(command===6)new DataView(b).setUint32(8,6,true);return b;}
export async function buildOverviewPainterFixture(bridge,{onPoint}={}){
 const sourceBridge=bridge.source,snapshotBridge=bridge.snapshot,close=(h,sequence=0n)=>sourceBridge.execute(scaleRequest(10,h,sequence));
 let builder,source,point,index,query,frame,duplicate;const storage=new Map();
 try{
  const descriptor=new Uint8Array(144),v=new DataView(descriptor.buffer);descriptor.set([88,89,71,68]);[1,1,4326,1,0].forEach((n,i)=>v.setUint32(4+4*i,n,true));v.setBigUint64(24,3n,true);v.setBigUint64(32,3n,true);[-179,0,179,0,0,0].forEach((n,i)=>v.setFloat64(64+8*i,n,true));descriptor.set([1,1,1],112);[MAX,1n<<63n,7n].forEach((n,i)=>v.setBigUint64(120+8*i,n,true));
  const chunk=await sourceBridge.read(encodeGeoChunkRequest({descriptor,rows:3,intervals:{starts:BigInt64Array.of(-5n,0n,10n),ends:BigInt64Array.of(5n,10n,20n),startValidity:Uint8Array.of(1,1,1),endValidity:Uint8Array.of(1,1,1)}},BUDGET.processorBytes));
  builder=decode(await sourceBridge.execute(encode({command:1}))).handle;
  await sourceBridge.execute(encode({command:2,handle:builder,payload:new Uint8Array(chunk)}));await sourceBridge.execute(encode({command:3,handle:builder,generation:MAX}));
  const manifest=await sourceBridge.read(encode({command:21,handle:builder}));source=decode(await sourceBridge.execute(encode({command:4,payload:new Uint8Array(manifest),budget:BUDGET}))).handle;
  const readChunk=async()=>chunk,info=(await driveGeoSession(sourceBridge,{handle:source,sequence:0n,budget:BUDGET,readChunk})).source;
  const camera={crs:4326,worldWrap:true,centerX:0,centerY:0,zoom:0,width:800,height:600,bearing:0,pitch:0};
  const q={camera,reducedKind:0,maxCells:1,previousDirect:true,sourceDigest:info.digest,generation:MAX,layerId:MAX,cameraRevision:1n,timeRevision:1n,layerRevision:1n,styleRevision:1n,stateRevision:1n,time:{kind:0},maxProjectedVertices:1000000n};
  await sourceBridge.execute(encode({command:5,handle:source,sequence:1n,budget:BUDGET,query:q}));await driveGeoSession(sourceBridge,{handle:source,sequence:1n,budget:BUDGET,readChunk});
  point=await prepareGeoSceneData(sourceBridge,{handle:source,sequence:1n,budget:BUDGET,style:encodeGeoScaleStyle({fill:Uint8Array.of(255,0,0,255),stroke:new Uint8Array(4),strokeWidth:0,diameter:6,opacity:1,symbol:0})});
  if(onPoint)await onPoint(point.handle);
  index=decodeGeoOverviewReply(await sourceBridge.execute(encodeGeoOverviewRequest({command:27,handle:point.handle,sequence:1n,budget:BUDGET,payload:new Uint8Array(new BigUint64Array([1000000n]).buffer)}))).handle;
  await point.dispose();point=undefined;await close(source);source=undefined;await close(builder);builder=undefined;
  const callbacks={readChunk,async readPage(t){const b=storage.get(`${t.namespace}:${t.page}`);check(b,'missing external prefix');return b.slice();},async writePage(t,b){storage.set(`${t.namespace}:${t.page}`,b.slice());}};
  check((await driveGeoOverview(sourceBridge,{handle:index,sequence:1n,budget:BUDGET,...callbacks})).code===13,'build incomplete');
  query=decodeGeoOverviewReply(await sourceBridge.execute(encodeGeoOverviewRequest({command:28,handle:index,sequence:7n,budget:BUDGET,query:{...q,time:{kind:1,instant:0n},maxCells:0,previousDirect:false,maxProjectedVertices:0n}}))).handle;
  check((await driveGeoOverview(sourceBridge,{handle:query,sequence:7n,budget:BUDGET,...callbacks})).code===14,'query incomplete');
  frame=decodeGeoOverviewReply(await sourceBridge.execute(encodeGeoOverviewRequest({command:29,handle:query,sequence:7n,budget:BUDGET}))).handle;
  await close(query,7n);query=undefined;await close(index,1n);index=undefined;storage.clear();
  let packet=await sourceBridge.read(encodeGeoOverviewRequest({command:23,handle:frame,sequence:7n,budget:BUDGET}));
  check(new DataView(packet).getUint32(8,true)===3,'overview must remain nonfinal');
  duplicate=decode(await sourceBridge.execute(scaleRequest(26,frame,7n))).handle;packet=undefined;await close(frame);frame=undefined;
  packet=await sourceBridge.read(encodeGeoOverviewRequest({command:23,handle:duplicate,sequence:7n,budget:BUDGET}));
  const handle=duplicate;duplicate=undefined;let ownedPacket=packet;
  return {handle,sequence:7n,get packet(){return ownedPacket;},scene:new Uint8Array(packet,2304),async freeze(){const h=decodeGeoSnapshotReply(await snapshotBridge.execute(snapshotRequest(6,handle,{sequence:7n,budget:128<<20}))).handle;return {handle:h,bytes:await snapshotBridge.read(snapshotRequest(20,h)),async dispose(){await snapshotBridge.execute(snapshotRequest(3,h));}};},async dispose(){ownedPacket=undefined;await close(handle);}};
 }finally{if(duplicate!==undefined)await close(duplicate);if(frame!==undefined)await close(frame);if(query!==undefined)await close(query,7n);if(index!==undefined)await close(index,1n);if(point)await point.dispose();if(source!==undefined)await close(source);if(builder!==undefined)await close(builder);}
}
