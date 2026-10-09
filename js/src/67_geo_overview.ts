/** Typed nonfinal data-domain counts. All temporal/geometry policy is Rust-owned. */
import { encodeGeoScaleRequest, type prepareGeoSceneData } from './63_geo_source';
import type { XygGeoQueryBudget, XygGeoScaleBridge, XygGeoScaleQuery } from './63_geo_source';

const MAX_PACKET=32*1024*1024, HEADER=256, TICKET=128;
export class GeoOverviewUnsupportedSelected extends Error {
  constructor(){super('Temporal overview does not retain selected authority');this.name='GeoOverviewUnsupportedSelected';}
}
/** Internal frame-aware ingress: the raw codec has only a numeric handle and
 * cannot detect selected authority before dispatch. Rust rechecks the owner. */
export function encodeGeoOverviewBuild(frame:Awaited<ReturnType<typeof prepareGeoSceneData>>,input:{budget:XygGeoQueryBudget;maxVertices:bigint}):ArrayBuffer{
  if(frame.data.selection!==null)throw new GeoOverviewUnsupportedSelected();
  const sequence=frame.data.identity.sequence;
  if(typeof input.maxVertices!=='bigint'||input.maxVertices<=0n||input.maxVertices>0xffffffffffffffffn)throw new TypeError('nonzero u64 overview vertex ceiling required');
  const payload=new Uint8Array(8);new DataView(payload.buffer).setBigUint64(0,input.maxVertices,true);
  return encodeGeoOverviewRequest({command:27,handle:frame.handle,sequence,budget:input.budget,payload});
}
export interface GeoOverviewRequest {command:number;handle:bigint;sequence:bigint;budget?:XygGeoQueryBudget;query?:XygGeoScaleQuery;payload?:Uint8Array}
export function encodeGeoOverviewRequest(input:GeoOverviewRequest):ArrayBuffer {
  if(![6,7,8,9,10,23,27,28,29,30,31].includes(input.command))throw new TypeError('unknown overview command');
  if(input.query!==undefined && input.command!==28)throw new TypeError('query belongs to overview begin');
  if(input.command===28 && (!input.query || input.query.reducedKind!==0 || input.query.maxCells!==0 || input.query.previousDirect!==false || input.query.maxProjectedVertices!==0n))throw new TypeError('overview requires explicit data-domain framing');
  // Shared header offsets and exact integer framing stay in the source codec.
  const b=encodeGeoScaleRequest({...input,command:input.command===28?5:6});
  new DataView(b).setUint32(8,input.command,true);return b;
}
function zeros(b:Uint8Array,a:number,z:number){if(b.subarray(a,z).some(x=>x!==0))throw new TypeError('nonzero overview reserved bytes');}
function raw(value:ArrayBuffer|Uint8Array):Uint8Array {if(value instanceof ArrayBuffer)return new Uint8Array(value);if(value instanceof Uint8Array)return value;throw new TypeError('exact overview bytes required');}
export function decodeGeoOverviewReply(packet:ArrayBuffer) {
  if(!(packet instanceof ArrayBuffer)||packet.byteLength!==HEADER)throw new TypeError('fixed overview reply required');
  const b=new Uint8Array(packet),v=new DataView(packet),code=v.getUint32(8,true);
  if(v.getUint32(0,true)!==0x5a475958||v.getUint32(4,true)!==1||![0,1,2,7,9,13,14,15,16,17].includes(code))throw new TypeError('invalid overview reply');
  zeros(b,12,16);zeros(b,192,256);
  const ticket=([1,7].includes(code)||code===2&&b.subarray(64,192).some(x=>x!==0))?b.slice(64,192):null;
  if(ticket){const t=new DataView(ticket.buffer),kind=t.getUint32(32,true),length=t.getBigUint64(48,true);zeros(ticket,36,40);zeros(ticket,104,128);if(![1,2,3].includes(kind)||length>BigInt(kind===1?16*1024*1024:65536)||length<64n||code===7&&kind!==3||code===1&&kind===3)throw new TypeError('invalid overview ticket');if(kind!==1)zeros(ticket,64,104);}
  else zeros(b,64,192);
  return {code,handle:v.getBigUint64(16,true),sequence:v.getBigUint64(24,true),dataLength:v.getBigUint64(32,true),sourceHandle:v.getBigUint64(40,true),ticket};
}
export function parseGeoOverviewData(packet:ArrayBuffer) {
  if(!(packet instanceof ArrayBuffer)||packet.byteLength<2304+160||packet.byteLength>MAX_PACKET)throw new TypeError('invalid overview data size');
  const b=new Uint8Array(packet),v=new DataView(packet);
  if(v.getUint32(0,true)!==0x564f5958||v.getUint32(4,true)!==1||v.getUint32(8,true)!==3||v.getUint32(12,true)!==16||v.getBigUint64(40,true)!==2048n)throw new TypeError('invalid nonfinal overview tier');
  for(const [a,z] of [[104,112],[168,176],[216,224],[228,232],[248,256]])zeros(b,a,z);
  const sceneLength=v.getBigUint64(32,true);if(sceneLength!==BigInt(packet.byteLength-2304))throw new TypeError('overview Scene length mismatch');
  const scene=b.subarray(2304),sv=new DataView(packet,2304);
  if(sv.getUint32(0,true)!==0x53475958||sv.getUint32(4,true)!==32)throw new TypeError('invalid overview Scene32');
  if(![4326,3857].includes(v.getUint32(72,true))||![1,4].includes(v.getUint32(76,true))||![4326,3857].includes(v.getUint32(96,true))||v.getUint32(100,true)>1)throw new TypeError('invalid overview CRS/geometry');
  const numbers=Array.from({length:7},(_,i)=>v.getFloat64(112+8*i,true));if(numbers.some(n=>!Number.isFinite(n))||numbers[3]<=0||numbers[4]<=0)throw new TypeError('invalid overview camera');
  const kind=v.getUint32(224,true),start=v.getBigInt64(232,true),end=v.getBigInt64(240,true);
  if(kind>2||kind===0&&(start!==0n||end!==0n)||kind===1&&end!==0n||kind===2&&start>=end)throw new TypeError('invalid overview time');
  if(v.getBigUint64(16,true)===0n||v.getBigUint64(24,true)===0n)throw new TypeError('missing overview publication');
  return {packet,scene,temporalExact:true as const,dataSpace:true as const,final:false as const,resolution:16 as const,
    identity:{queryHandle:v.getBigUint64(16,true),sequence:v.getBigUint64(24,true),overviewDigest:b.subarray(48,56),generation:v.getBigUint64(56,true),sourceDigest:b.subarray(64,72),sourceCrs:v.getUint32(72,true),geometry:v.getUint32(76,true),layerId:v.getBigUint64(80,true),sourceRows:v.getBigUint64(88,true),camera:{crs:v.getUint32(96,true),worldWrap:!!v.getUint32(100,true),centerX:numbers[0],centerY:numbers[1],zoom:numbers[2],width:numbers[3],height:numbers[4],bearing:numbers[5],pitch:numbers[6]},cameraRevision:v.getBigUint64(176,true),timeRevision:v.getBigUint64(184,true),layerRevision:v.getBigUint64(192,true),styleRevision:v.getBigUint64(200,true),stateRevision:v.getBigUint64(208,true),time:kind===0?{kind:0}:kind===1?{kind:1,instant:start}:{kind:2,start,end}},
    count(cell:number){if(!Number.isInteger(cell)||cell<0||cell>=256)throw new RangeError('domain cell must be 0..255');return v.getBigUint64(256+8*cell,true);}};
}
export interface GeoOverviewTicket {raw:Uint8Array;owner:bigint;namespace:bigint;page:bigint;kind:number;encodedBytes:number;chunkIndex:number}
type Reader=(ticket:GeoOverviewTicket,signal?:AbortSignal)=>Promise<ArrayBuffer|Uint8Array>;
export interface GeoOverviewStorage {readChunk:Reader;readPage:Reader;writePage:(ticket:GeoOverviewTicket,bytes:Uint8Array,signal?:AbortSignal)=>Promise<void>}
export async function driveGeoOverview(bridge:XygGeoScaleBridge,input:GeoOverviewStorage & {handle:bigint;sequence:bigint;budget:XygGeoQueryBudget;signal?:AbortSignal}) {
  const {handle,sequence,budget,signal}=input;let cancellation:Promise<ArrayBuffer>|undefined;
  const request=(command:number,payload?:Uint8Array)=>encodeGeoOverviewRequest({command,handle,sequence,budget,payload});
  const cancel=()=>cancellation??=bridge.execute(request(9));
  const aborted=()=>new DOMException('Overview operation aborted','AbortError');
  const onAbort=()=>{void cancel().catch(()=>{});};signal?.addEventListener('abort',onAbort,{once:true});
  try{for(;;){if(signal?.aborted){await cancel();throw aborted();}const r=decodeGeoOverviewReply(await bridge.execute(request(6)));if(r.handle!==handle||r.sequence!==sequence)throw new TypeError('mismatched overview operation');if([13,14,15].includes(r.code)){if(signal?.aborted){await cancel();throw aborted();}return r;}if(![1,7].includes(r.code)||!r.ticket)throw new TypeError('overview did not complete');
    const authority=r.ticket.slice(),v=new DataView(authority.buffer),kind=v.getUint32(32,true),length=Number(v.getBigUint64(48,true));
    const ticket={raw:authority.slice(),owner:v.getBigUint64(0,true),namespace:v.getBigUint64(8,true),page:v.getBigUint64(40,true),kind,encodedBytes:length,chunkIndex:v.getUint32(72,true)};
    let borrowed:ArrayBuffer|Uint8Array|undefined,view:Uint8Array|undefined,payload:Uint8Array|undefined,supply:ArrayBuffer|undefined;
    try{if(4*(HEADER+TICKET+length)>budget.processorBytes)throw new RangeError('overview transfer exceeds budget');
      if(kind===3){borrowed=await bridge.read(request(30,authority));view=raw(borrowed);if(view.length!==length||view.buffer.byteLength!==length)throw new TypeError('exact owning overview write required');await input.writePage(ticket,view,signal);}
      else{borrowed=await (kind===1?input.readChunk:input.readPage)(ticket,signal);view=raw(borrowed);if(view.length!==length||view.buffer.byteLength!==length)throw new TypeError('exact owning overview read required');if(signal?.aborted){await cancel();throw aborted();}payload=new Uint8Array(TICKET+length);payload.set(authority);payload.set(view,TICKET);supply=request(7,payload);payload=undefined;await bridge.execute(supply);}
      if(signal?.aborted){await cancel();throw aborted();}
    }catch(error){borrowed=undefined;view=undefined;payload=undefined;supply=undefined;await cancel();throw error;}
    finally{borrowed=undefined;view=undefined;payload=undefined;supply=undefined;try{if(cancellation)await cancellation;}finally{await bridge.execute(request(kind===3?31:8,authority));}}
  }}catch(error){await cancel();throw error;}finally{signal?.removeEventListener('abort',onAbort);}
}
export async function prepareGeoOverviewData(bridge:XygGeoScaleBridge,input:{handle:bigint;sequence:bigint;budget:XygGeoQueryBudget}) {
  const receipt=decodeGeoOverviewReply(await bridge.execute(encodeGeoOverviewRequest({...input,command:29}))),handle=receipt.handle;
  let data:ReturnType<typeof parseGeoOverviewData>|undefined,packet:ArrayBuffer|undefined,disposal:Promise<void>|undefined;
  const dispose=()=>{packet=undefined;data=undefined;return disposal??=bridge.execute(encodeGeoOverviewRequest({command:10,handle,sequence:0n})).then(()=>{},error=>{disposal=undefined;throw error;});};
  try{if(receipt.code!==16||receipt.sourceHandle!==input.handle||receipt.sequence!==input.sequence||receipt.dataLength>BigInt(MAX_PACKET)||4n*receipt.dataLength>BigInt(input.budget.processorBytes))throw new TypeError('invalid overview Data lease');packet=await bridge.read(encodeGeoOverviewRequest({...input,command:23,handle}));if(BigInt(packet.byteLength)!==receipt.dataLength)throw new TypeError('overview Data length mismatch');data=parseGeoOverviewData(packet);if(data.identity.queryHandle!==input.handle||data.identity.sequence!==input.sequence)throw new TypeError('overview Data identity mismatch');packet=undefined;}
  catch(error){await dispose();throw error;}
  return {handle,get data(){if(!data)throw new Error('overview Data disposed');return data;},dispose};
}
