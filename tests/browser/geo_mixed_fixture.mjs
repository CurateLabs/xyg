// Same authored raw fixture for native, wasm32 and the actual browser Worker.
import {encodeGeoScaleRequest as sourceRequest,decodeGeoScaleReply,encodeGeoChunkRequest,driveGeoSession,prepareGeoSceneData,encodeGeoScaleStyle} from '../../packages/xy-node/src/geoscale.js';
import {encodeGeoMixedRequest,decodeGeoMixedReply,prepareGeoMixedData,parseGeoMixedTileDescriptor} from '../../packages/xy-node/src/geo-mixed-wire.js';
import {encodeGeoSnapshotRequest,decodeGeoSnapshotReply} from '../../packages/xy-node/src/geo-snapshot.js';
export const MIXED_BUDGET=128<<20;
const MAX=0xffffffffffffffffn,MIN=-0x8000000000000000n;
export const check=(ok,message)=>{if(!ok)throw Error(message);};
const u64=(b,at)=>new DataView(b).getBigUint64(at,true);
export function tileRequest(command,handle=0n,{epoch=0n,view=0n,payload=new Uint8Array(),budget=0}={}){
 const out=new ArrayBuffer(128+payload.byteLength),b=new Uint8Array(out),v=new DataView(out);b.set([88,89,71,84]);v.setUint32(4,1,true);v.setUint32(8,command,true);[handle,epoch,view,BigInt(budget),BigInt(payload.byteLength)].forEach((n,i)=>v.setBigUint64(16+i*8,n,true));b.set(payload,128);return out;
}
function descriptor(x){
 const b=new Uint8Array(96),v=new DataView(b.buffer);b.set([88,89,71,68]);[1,1,4326,1].forEach((n,i)=>v.setUint32(4+i*4,n,true));v.setBigUint64(24,1n,true);v.setBigUint64(32,1n,true);v.setFloat64(64,x,true);b[80]=1;v.setBigUint64(88,MAX,true);return b;
}
function beginTile(){
 const text=new TextEncoder(),parts=[];
 for(let kind=0;kind<2;kind++){
  const locator=text.encode(kind?'local/vector':'https://example.test/{z}/{x}/{y}'),attr=text.encode(kind?'':'Tiles'),b=new Uint8Array(112+locator.length+attr.length),v=new DataView(b.buffer);
  [BigInt(kind+1),1n,BigInt(kind+7),1n,1n].forEach((n,i)=>v.setBigUint64(i*8,n,true));v.setUint32(60,kind,true);v.setBigUint64(72,kind?1024n:262144n,true);v.setBigUint64(80,1n,true);v.setBigUint64(88,1n,true);v.setUint32(96,locator.length,true);v.setUint32(100,attr.length,true);v.setUint32(104,1-kind,true);b.set(locator,112);b.set(attr,112+locator.length);parts.push(b);
 }
 const b=new Uint8Array(80+parts.reduce((n,p)=>n+p.length,0)),v=new DataView(b.buffer);v.setUint32(0,4326,true);v.setFloat64(32,64,true);v.setFloat64(40,64,true);v.setUint32(64,2,true);let at=80;for(const p of parts){b.set(p,at);at+=p.length;}return b;
}
function prepareTile(){
 const catalog=new Uint8Array(128),cv=new DataView(catalog.buffer);catalog.set([88,89,76,75]);cv.setUint32(4,1,true);cv.setUint32(16,4326,true);cv.setFloat64(48,64,true);cv.setFloat64(56,64,true);
 const b=new Uint8Array(32+64+128),v=new DataView(b.buffer);v.setBigUint64(0,42n,true);v.setUint32(8,1,true);v.setBigUint64(16,128n,true);v.setBigUint64(32,8n,true);v.setUint32(40,1,true);b.set([0,255,0,255],48);v.setFloat64(64,6,true);v.setFloat64(72,1,true);b.set(catalog,96);return b;
}
export async function buildMixedFixture(bridges){
 const {source,tile}=bridges,prepareMixed=bridges.prepareMixed??(input=>prepareGeoMixedData(tile,input)),budget={processorBytes:MIXED_BUDGET,maxRowsExamined:1000000n,maxReadBytes:128n<<20n,maxChunks:65536,pageRows:4096};
 const style=encodeGeoScaleStyle({fill:Uint8Array.of(255,0,0,255),stroke:new Uint8Array(4),strokeWidth:0,diameter:8,opacity:1,symbol:0});
 let builder,session,sourceFrame,cache,tileHandle,coordinator,frame,staged;
 const rasterColor=bridges.rasterColor??[0,0,255,255];
 const disposeSource=handle=>source.execute(sourceRequest({command:10,handle}));
 const disposeMixed=handle=>tile.execute(encodeGeoMixedRequest({command:5,handle}));
 try{
  const chunk=await source.read(encodeGeoChunkRequest({descriptor:descriptor(0),rows:1,intervals:{starts:BigInt64Array.of(MIN),ends:BigInt64Array.of(MIN+10n),startValidity:Uint8Array.of(1),endValidity:Uint8Array.of(1)}},MIXED_BUDGET));
  builder=decodeGeoScaleReply(await source.execute(sourceRequest({command:1}))).handle;
  await source.execute(sourceRequest({command:2,handle:builder,payload:new Uint8Array(chunk)}));await source.execute(sourceRequest({command:3,handle:builder,generation:MAX}));
  const manifest=await source.read(sourceRequest({command:21,handle:builder}));session=decodeGeoScaleReply(await source.execute(sourceRequest({command:4,budget,payload:new Uint8Array(manifest)}))).handle;
  const readChunk=async()=>chunk,info=(await driveGeoSession(source,{handle:session,sequence:0n,budget,readChunk})).source;
  const camera={crs:4326,worldWrap:false,centerX:0,centerY:0,zoom:0,width:64,height:64,bearing:0,pitch:0};
  const query={camera,reducedKind:0,maxCells:32768,previousDirect:true,sourceDigest:info.digest,generation:MAX,layerId:MAX,cameraRevision:1n,timeRevision:1n,layerRevision:1n,styleRevision:1n,stateRevision:1n,time:{kind:2,start:MIN,end:MIN+1n},maxProjectedVertices:100n};
  await source.execute(sourceRequest({command:5,handle:session,sequence:1n,budget,query}));await driveGeoSession(source,{handle:session,sequence:1n,budget,readChunk});sourceFrame=await prepareGeoSceneData(source,{handle:session,sequence:1n,budget,style});
  check(sourceFrame.data.record(0).featureId===MAX,'literal source ID lost');
  const originalSourceHandle=sourceFrame.handle,snapshot=new Uint8Array(160);let raw=new Uint8Array(sourceFrame.data.packet);snapshot.set(raw.subarray(80,144));snapshot.set(raw.subarray(144,208),64);snapshot.set(raw.subarray(208,212),128);snapshot.set(raw.subarray(216,232),136);raw=undefined;
  cache=u64(await tile.execute(tileRequest(1)),16);const epoch=u64(await tile.execute(tileRequest(2,cache,{view:9n,budget:MIXED_BUDGET,payload:beginTile()})),24);
  while(true){const next=await tile.execute(tileRequest(3,cache,{epoch})),id=u64(next,16);if(!id)break;const kind=new DataView(next).getUint32(148,true);let payload=kind?descriptor(10):new Uint8Array(256*256*4);if(!kind)for(let at=0;at<payload.length;at+=4)payload.set(rasterColor,at);
   await tile.execute(tileRequest(4,id,{epoch,payload}));payload=undefined;await tile.execute(tileRequest(5,id,{epoch}));
  }
  tileHandle=u64(await tile.execute(tileRequest(6,cache,{epoch,budget:MIXED_BUDGET,payload:prepareTile()})),16);
  let context=await tile.read(tileRequest(23,tileHandle,{epoch,budget:MIXED_BUDGET})),authority=parseGeoMixedTileDescriptor(context);
  check(authority.handle===tileHandle&&authority.epoch===epoch&&authority.cache===cache&&authority.view===9n,'public tile provenance identity');
  await tile.read(tileRequest(22,tileHandle,{epoch,budget:MIXED_BUDGET}));let rejected=false;try{await tile.read(tileRequest(23,tileHandle,{epoch,budget:MIXED_BUDGET}));}catch{rejected=true;}check(rejected,'third original tile read accepted');
  coordinator=decodeGeoMixedReply(await tile.execute(encodeGeoMixedRequest({command:1}))).handle;
  let input={command:2,handle:coordinator,budget:MIXED_BUDGET,sourceHandle:originalSourceHandle,sourceSequence:1n,tileHandle,tileEpoch:epoch,tileCacheHandle:cache,tileViewId:9n,tileTime:0,snapshot,stamps:authority.stamps};
  frame=await prepareMixed(input);if(bridges.stage)await bridges.stage(frame);await frame.commit();
  staged=await prepareMixed(input);if(bridges.stageFailure)await bridges.stageFailure(staged);let stale=false;try{await frame.commit();}catch{stale=true;}check(stale,'stale mixed candidate committed');await staged.cancel();let cancelled=false;try{await staged.commit();}catch{cancelled=true;}check(cancelled,'cancelled mixed candidate committed');await staged.dispose();staged=undefined;
  // Ordinary compilation failure keeps the original immutable paint authority.
  let limited=false;try{await prepareMixed({...input,budget:65536});}catch{limited=true;}check(limited,'low-budget mixed compile accepted');
  input=undefined;authority=undefined;context=undefined;
  await sourceFrame.dispose();sourceFrame=undefined;await disposeSource(session);session=undefined;await disposeSource(builder);builder=undefined;
  await tile.execute(tileRequest(10,tileHandle));tileHandle=undefined;await tile.execute(tileRequest(10,cache));cache=undefined;await disposeMixed(coordinator);coordinator=undefined;
  const sourceLease=decodeGeoMixedReply(await tile.execute(encodeGeoMixedRequest({command:6,handle:frame.handle,nonce:frame.nonce,budget:MIXED_BUDGET})));
  let retained=await source.read(sourceRequest({command:23,handle:sourceLease.handle}));check(new DataView(retained).getBigUint64(200,true)===1n,'retained state revision lost');retained=undefined;await disposeSource(sourceLease.handle);
  const data=frame.data,scene=data.scene.slice(),stamps= new Uint8Array(data.tile);check(data.visibleVertices===1n&&new DataView(data.snapshot.buffer,data.snapshot.byteOffset,160).getBigInt64(136,true)===MIN,'time/source fact mismatch');
  return {frame,scene,descriptorBytes:stamps,async freeze(){
   const frozen=decodeGeoSnapshotReply(await bridges.snapshot.execute(encodeGeoSnapshotRequest(5,frame.handle,{sequence:frame.nonce,budget:MIXED_BUDGET}))).handle;
   return {handle:frozen,bytes:await bridges.snapshot.read(encodeGeoSnapshotRequest(20,frozen)),async dispose(){await bridges.snapshot.execute(encodeGeoSnapshotRequest(3,frozen));}};
  }};
 }catch(error){if(staged)await staged.dispose();if(frame)await frame.dispose();throw error;}
 finally{if(sourceFrame)await sourceFrame.dispose();if(session!==undefined)await disposeSource(session);if(builder!==undefined)await disposeSource(builder);if(tileHandle!==undefined)await tile.execute(tileRequest(10,tileHandle));if(cache!==undefined)await tile.execute(tileRequest(10,cache));if(coordinator!==undefined)await disposeMixed(coordinator);}
}
