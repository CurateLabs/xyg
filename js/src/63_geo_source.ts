/** Thin XYGQ/XYGZ source-session framing. All geographic policy remains in Rust. */
import type {XygGeoCamera} from './49_wasm_geoviewport';

export const GEO_SCALE_HEADER = 256;
const MAX_PACKET = 32 * 1024 * 1024, MAX_PROCESSOR = 128 * 1024 * 1024;
export interface XygGeoQueryBudget {processorBytes:number; maxRowsExamined:bigint; maxReadBytes:bigint; maxChunks:number; pageRows:number}
export type XygGeoTime = {kind:0} | {kind:1; instant:bigint} | {kind:2; start:bigint; end:bigint};
export interface XygGeoScaleQuery {
 camera:Required<XygGeoCamera>; reducedKind:number; maxCells:number; previousDirect:boolean;
 sourceDigest:Uint8Array; generation:bigint; layerId:bigint;
 cameraRevision:bigint; timeRevision:bigint; layerRevision:bigint; styleRevision:bigint; stateRevision:bigint;
 time:XygGeoTime; maxProjectedVertices:bigint;
}
export interface XygGeoScaleRequest {command:number; handle?:bigint; sequence?:bigint; budget?:XygGeoQueryBudget; generation?:bigint; query?:XygGeoScaleQuery; payload?:ArrayBuffer|Uint8Array}
export interface XygGeoScaleBridge {execute(request:ArrayBuffer):Promise<ArrayBuffer>; read(request:ArrayBuffer):Promise<ArrayBuffer>}
function u32(n:number){if(!Number.isInteger(n)||n<0||n>0xffffffff)throw new TypeError('expected u32');return n;}
function u64(n:bigint){if(typeof n!=='bigint'||n<0n||n>0xffffffffffffffffn)throw new TypeError('expected u64 bigint');return n;}
function i64(n:bigint){if(typeof n!=='bigint'||n< -0x8000000000000000n||n>0x7fffffffffffffffn)throw new TypeError('expected i64 bigint');return n;}
function budgetBytes(n:number){if(!Number.isSafeInteger(n)||n<256||n>MAX_PROCESSOR)throw new RangeError('invalid processor budget');return n;}
function bytes(p:ArrayBuffer|Uint8Array){if(p instanceof ArrayBuffer)return new Uint8Array(p);if(p instanceof Uint8Array)return p;throw new TypeError('expected raw bytes');}
function zero(b:Uint8Array,a:number,z:number){if(b.subarray(a,z).some(v=>v!==0))throw new TypeError('nonzero reserved bytes');}
function response(buffer:ArrayBuffer){if(!(buffer instanceof ArrayBuffer)||buffer.byteLength<256||buffer.byteLength>MAX_PACKET)throw new TypeError('invalid geographic reply size');const b=new Uint8Array(buffer),v=new DataView(buffer);if(String.fromCharCode(...b.subarray(0,4))!=='XYGZ'||v.getUint32(4,true)!==1)throw new TypeError('invalid geographic reply');return {b,v};}
function count(v:DataView,at:number,max=MAX_PACKET){const n=v.getBigUint64(at,true);if(n>BigInt(max))throw new RangeError('reply count exceeds framing');return Number(n);}

export function encodeGeoScaleRequest(input:XygGeoScaleRequest):ArrayBuffer {
 const command=u32(input.command);if(![1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,18,19,20,21,23,24,25,26].includes(command))throw new TypeError('unknown geographic command');
 const payload=input.payload===undefined?new Uint8Array():bytes(input.payload),length=256+payload.byteLength;
 if(length>MAX_PACKET||input.budget&&length>budgetBytes(input.budget.processorBytes))throw new RangeError('request exceeds framing budget');
 if(input.query!==undefined&&![5,18].includes(command)||input.generation!==undefined&&command!==3||input.sequence!==undefined&&![5,6,9,11,12,13,14,15,16,17,18,19,24,25,26].includes(command))throw new TypeError('field does not belong to command');
 const out=new ArrayBuffer(length),b=new Uint8Array(out),v=new DataView(out);b.set([88,89,71,81]);v.setUint32(4,1,true);v.setUint32(8,command,true);v.setBigUint64(16,u64(input.handle??0n),true);v.setBigUint64(24,u64(input.sequence??0n),true);
 if(input.budget){const q=input.budget;v.setBigUint64(32,BigInt(budgetBytes(q.processorBytes)),true);v.setBigUint64(40,u64(q.maxRowsExamined),true);v.setBigUint64(48,u64(q.maxReadBytes),true);v.setUint32(56,u32(q.maxChunks),true);v.setUint32(60,u32(q.pageRows),true);}
 if(command===3)v.setBigUint64(144,u64(input.generation??0n),true);
 if(command===5||command===18){const q=input.query;if(!q)throw new TypeError('begin requires query');const c=q.camera;if(typeof c.worldWrap!=='boolean'||typeof q.previousDirect!=='boolean'||!(q.sourceDigest instanceof Uint8Array)||q.sourceDigest.length!==8)throw new TypeError('invalid query framing');v.setUint32(12,c.worldWrap?1:0,true);v.setUint32(64,u32(c.crs),true);v.setUint32(68,u32(q.reducedKind),true);v.setUint32(72,u32(q.maxCells),true);v.setUint32(76,q.previousDirect?1:0,true);
  [c.centerX,c.centerY,c.zoom,c.width,c.height,c.bearing,c.pitch].forEach((n,i)=>{if(typeof n!=='number')throw new TypeError('camera requires explicit f64 values');v.setFloat64(80+i*8,n,true);});b.set(q.sourceDigest,136);
  [q.generation,q.layerId,q.cameraRevision,q.timeRevision,q.layerRevision,q.styleRevision,q.stateRevision].forEach((n,i)=>v.setBigUint64(144+i*8,u64(n),true));
  v.setUint32(200,u32(q.time.kind),true);if(q.time.kind===1)v.setBigInt64(208,i64(q.time.instant),true);else if(q.time.kind===2){v.setBigInt64(208,i64(q.time.start),true);v.setBigInt64(216,i64(q.time.end),true);}else if(q.time.kind!==0)throw new TypeError('unknown time predicate');v.setBigUint64(224,u64(q.maxProjectedVertices),true);
 }v.setBigUint64(232,BigInt(payload.length),true);b.set(payload,256);return out;
}
export function encodeGeoScaleStyle(style:{fill:Uint8Array;stroke:Uint8Array;strokeWidth:number;diameter:number;opacity:number;symbol:number}):Uint8Array {
 const b=new Uint8Array(48),v=new DataView(b.buffer);if(!(style.fill instanceof Uint8Array)||style.fill.length!==4||!(style.stroke instanceof Uint8Array)||style.stroke.length!==4||u32(style.symbol)>255)throw new TypeError('invalid exact style framing');b.set(style.fill);b.set(style.stroke,4);[style.strokeWidth,style.diameter,style.opacity].forEach((n,i)=>{if(typeof n!=='number')throw new TypeError('style requires f64');v.setFloat64(8+i*8,n,true);});b[32]=style.symbol;return b;
}
export interface XygGeoReadTicket {raw:Uint8Array;kind:number;page:bigint;sessionId:bigint;readId:bigint;sequence:bigint;pass:number;generation:bigint;chunkIndex:number;rows:number;firstRow:bigint;encodedBytes:number;digest:Uint8Array}
function readTicket(raw:Uint8Array):XygGeoReadTicket {
 const v=new DataView(raw.buffer,raw.byteOffset,raw.byteLength),kind=v.getUint32(28,true),pass=v.getUint32(24,true);
 if(kind>3)throw new TypeError('invalid geographic ticket kind');zero(raw,72,96);
 const encodedBytes=count(v,56,kind>=2?65536:16*1024*1024);
 if(kind===1&&(pass!==0||v.getBigUint64(8,true)!==BigInt(v.getUint32(40,true))))throw new TypeError('invalid index source ticket');
 if(kind>=2){zero(raw,32,56);if(encodedBytes<64||kind===2&&![1,2].includes(pass)||kind===3&&pass!==0)throw new TypeError('invalid leaf ticket');}
 return {raw,kind,page:v.getBigUint64(8,true),sessionId:v.getBigUint64(0,true),readId:v.getBigUint64(8,true),sequence:v.getBigUint64(16,true),pass,generation:v.getBigUint64(32,true),chunkIndex:v.getUint32(40,true),rows:v.getUint32(44,true),firstRow:v.getBigUint64(48,true),encodedBytes,digest:raw.subarray(64,72)};
}
export function decodeGeoScaleReply(buffer:ArrayBuffer){
 const {b,v}=response(buffer);if(buffer.byteLength!==256)throw new TypeError('mutation reply must be fixed size');const code=v.getUint32(8,true);if(code>12)throw new TypeError('invalid step code');zero(b,12,16);
 if(code===4){if(v.getBigUint64(160,true)>4096n||v.getUint32(168,true)>1)throw new TypeError('invalid membership reply');zero(b,176,256);}
 else if(code===12){if(![1,2].includes(v.getUint32(184,true)))throw new TypeError('invalid indexed pass count');zero(b,188,256);}
 else zero(b,160,256);
 if(code===10){if(![1,2].includes(v.getUint32(48,true)))throw new TypeError('invalid indexed fallback reason');zero(b,52,160);}
 const ticket=[1,2,7,8].includes(code)?readTicket(b.subarray(64,160)):null;
 if(ticket&&([7,8].includes(code)?ticket.kind!==3:ticket.kind===3))throw new TypeError('ticket does not match step');
 return {code,fallbackReasonCode:code===10?v.getUint32(48,true):null,handle:v.getBigUint64(16,true),sequence:v.getBigUint64(24,true),dataLength:v.getBigUint64(32,true),sourceHandle:v.getBigUint64(40,true),source:{generation:v.getBigUint64(32,true),digest:b.subarray(40,48),rows:v.getBigUint64(48,true),geometry:v.getUint32(56,true),crs:v.getUint32(60,true)},ticket,indexStats:code===12?{pagesRead:v.getBigUint64(160,true),bytesRead:v.getBigUint64(168,true),candidateVertices:v.getBigUint64(176,true),passes:v.getUint32(184,true)}:null};
}

export function encodeGeoChunkRequest(input:{descriptor:ArrayBuffer|Uint8Array;rows:number;intervals?:{starts:BigInt64Array;ends:BigInt64Array;startValidity:Uint8Array;endValidity:Uint8Array};values?:Float64Array},budget:number):ArrayBuffer {
 budgetBytes(budget);const d=bytes(input.descriptor),n=u32(input.rows),t=input.intervals,s=input.values;
 if(n>65536||t&&(!(t.starts instanceof BigInt64Array)||!(t.ends instanceof BigInt64Array)||!(t.startValidity instanceof Uint8Array)||!(t.endValidity instanceof Uint8Array)||[t.starts,t.ends,t.startValidity,t.endValidity].some(p=>p.length!==n))||s!==undefined&&(!(s instanceof Float64Array)||s.length!==n))throw new TypeError('chunk requires exact typed planes');
 const size=32+d.length+n*((t?18:0)+(s?8:0));if(size>16*1024*1024||6*size+32768+256>budget)throw new RangeError('chunk exceeds peak framing budget');
 const payload=new Uint8Array(size),v=new DataView(payload.buffer);v.setBigUint64(0,BigInt(d.length),true);v.setUint32(8,(t?1:0)|(s?2:0),true);v.setBigUint64(16,BigInt(n),true);payload.set(d,32);let at=32+d.length;
 if(t){for(const p of [t.starts,t.ends]){for(let i=0;i<n;i++)v.setBigInt64(at+i*8,p[i],true);at+=n*8;}payload.set(t.startValidity,at);at+=n;payload.set(t.endValidity,at);at+=n;}if(s)for(let i=0;i<n;i++)v.setFloat64(at+i*8,s[i],true);
 return encodeGeoScaleRequest({command:20,payload});
}

/** Views borrow packet storage; consumers must drop every view/copy before lease disposal. */
export function parseGeoSceneData(packet:ArrayBuffer){
 const {b,v}=response(packet),aggregate=v.getUint32(8,true),droppedChannels=v.getUint32(12,true),sceneLength=count(v,32),metadataLength=count(v,40),columns=v.getUint32(64,true),rows=v.getUint32(68,true),gridCapped=v.getUint32(72,true),timeKind=v.getUint32(208,true),reducedKind=v.getUint32(212,true);
 if(aggregate>1||gridCapped>1||timeKind>2||reducedKind>1||droppedChannels&~7||256+sceneLength+metadataLength!==packet.byteLength||sceneLength<160)throw new TypeError('malformed SceneData framing');zero(b,76,80);zero(b,248,256);
 const scene=b.subarray(256,256+sceneLength),sv=new DataView(packet,256,sceneLength);if(String.fromCharCode(...scene.subarray(0,4))!=='XYGS'||sv.getUint32(4,true)!==32)throw new TypeError('invalid Scene32 packet');
 const stride=aggregate?24:40;if(metadataLength%stride||aggregate&&columns*rows!==metadataLength/stride)throw new TypeError('invalid provenance framing');
 const sourceRows=v.getBigUint64(232,true),geometry=v.getUint32(240,true);if(![1,4].includes(geometry))throw new TypeError('invalid retained source geometry');
 const metadata=new DataView(packet,256+sceneLength,metadataLength),length=metadataLength/stride;
 for(let i=0;i<length;i++){const at=i*stride;if(aggregate){if(!Number.isFinite(metadata.getFloat64(at+8,true))||!Number.isFinite(metadata.getFloat64(at+16,true)))throw new TypeError('invalid reduced coordinates');}else if(metadata.getBigUint64(at+8,true)>=sourceRows||metadata.getUint32(at+16,true)>=65536||metadata.getUint32(at+20,true)>=65536||metadata.getUint32(at+24,true)>=524288||metadata.getUint32(at+28,true)!==0||metadata.getBigUint64(at+32,true)!==0n)throw new TypeError('invalid direct reserved metadata');}
 const crs=v.getUint32(80,true),wrap=v.getUint32(84,true),sourceCrs=v.getUint32(244,true);if(![4326,3857].includes(crs)||![4326,3857].includes(sourceCrs)||wrap>1)throw new TypeError('invalid camera/source CRS');const cameraValues=[88,96,104,112,120,128,136].map(at=>v.getFloat64(at,true));if(cameraValues.some(n=>!Number.isFinite(n)))throw new TypeError('invalid camera values');
 if(timeKind===0){zero(b,216,232);}else if(timeKind===1)zero(b,224,232);else if(v.getBigInt64(216,true)>=v.getBigInt64(224,true))throw new TypeError('invalid time window');
 const time:XygGeoTime=timeKind===0?{kind:0}:timeKind===1?{kind:1,instant:v.getBigInt64(216,true)}:{kind:2,start:v.getBigInt64(216,true),end:v.getBigInt64(224,true)};
 return {packet,scene,aggregate:!!aggregate,droppedChannels,visibleVertices:v.getBigUint64(48,true),projectedVertices:v.getBigUint64(56,true),columns,rows,gridCapped:!!gridCapped,metadata,length,
  identity:{sessionHandle:v.getBigUint64(16,true),sequence:v.getBigUint64(24,true),camera:{crs,worldWrap:!!wrap,centerX:cameraValues[0],centerY:cameraValues[1],zoom:cameraValues[2],width:cameraValues[3],height:cameraValues[4],bearing:cameraValues[5],pitch:cameraValues[6]},sourceDigest:b.subarray(144,152),generation:v.getBigUint64(152,true),layerId:v.getBigUint64(160,true),cameraRevision:v.getBigUint64(168,true),timeRevision:v.getBigUint64(176,true),layerRevision:v.getBigUint64(184,true),styleRevision:v.getBigUint64(192,true),stateRevision:v.getBigUint64(200,true),time,reducedKind,sourceRows:v.getBigUint64(232,true),geometry:v.getUint32(240,true),sourceCrs},
  record(index:number){if(!Number.isInteger(index)||index<0||index>=length)throw new RangeError('provenance index');const at=index*stride;return aggregate?{count:metadata.getBigUint64(at,true),x:metadata.getFloat64(at+8,true),y:metadata.getFloat64(at+16,true)}:{featureId:metadata.getBigUint64(at,true),sourceRow:metadata.getBigUint64(at+8,true),chunkIndex:metadata.getUint32(at+16,true),chunkRow:metadata.getUint32(at+20,true),vertex:metadata.getUint32(at+24,true)};}};
}
function aborted(){return new DOMException('Geographic operation cancelled','AbortError');}
/** Service only Rust-issued reads. Caller begins/validates the source explicitly. */
export async function driveGeoSession(bridge:XygGeoScaleBridge,input:{handle:bigint;sequence:bigint;budget:XygGeoQueryBudget;readChunk:(ticket:XygGeoReadTicket,signal?:AbortSignal)=>Promise<ArrayBuffer|Uint8Array>;signal?:AbortSignal}){
 const {handle,sequence,budget,signal}=input;let cancelPromise:Promise<unknown>|undefined;
 const cancel=()=>cancelPromise??=bridge.execute(encodeGeoScaleRequest({command:9,handle,sequence}));
 const onAbort=()=>{void cancel().catch(()=>{});};signal?.addEventListener('abort',onAbort,{once:true});
 try{for(;;){if(signal?.aborted){await cancel();throw aborted();}const reply=decodeGeoScaleReply(await bridge.execute(encodeGeoScaleRequest({command:6,handle,sequence,budget})));if(reply.handle!==handle||reply.sequence!==sequence)throw new TypeError('mismatched session reply');
   if(reply.code===3||reply.code===4||reply.code===5||reply.code===6){if(signal?.aborted){await cancel();throw aborted();}return reply;}
   if(reply.code!==1||!reply.ticket)throw new TypeError('unowned outstanding read');const ticket=reply.ticket,authority=ticket.raw.slice(),callbackTicket=readTicket(authority.slice());let borrowed:ArrayBuffer|Uint8Array|undefined,chunk:Uint8Array|undefined,supply:ArrayBuffer|undefined;
   try{if(signal?.aborted){await cancel();throw aborted();}borrowed=await input.readChunk(callbackTicket,signal);chunk=bytes(borrowed);if(chunk.byteLength!==ticket.encodedBytes||chunk.buffer.byteLength>ticket.encodedBytes)throw new RangeError('read callback must return exact bounded storage');if(signal?.aborted){await cancel();throw aborted();}
    if(3*(352+chunk.byteLength)>budget.processorBytes)throw new RangeError('read transfer exceeds peak budget');let payload:Uint8Array|undefined=new Uint8Array(96+chunk.byteLength);payload.set(authority);payload.set(chunk,96);supply=encodeGeoScaleRequest({command:7,handle,payload});payload=undefined;await bridge.execute(supply);
   }catch(error){try{await cancel();}catch{/* Preserve the read/supply error; release is still required. */}throw error;
   }finally{borrowed=undefined;chunk=undefined;supply=undefined;try{if(cancelPromise)await cancelPromise;}finally{await bridge.execute(encodeGeoScaleRequest({command:8,handle,payload:authority}));}}
  }}finally{signal?.removeEventListener('abort',onAbort);if(cancelPromise)await cancelPromise;}
}
/** Disposal is explicit: first destroy painters and drop packet-derived copies/views. */
export async function prepareGeoSceneData(bridge:XygGeoScaleBridge,input:{handle:bigint;sequence:bigint;budget:XygGeoQueryBudget}&({command:26;style?:never}|{command?:11|19;style:Uint8Array})){
 if(input.command===26&&input.style!==undefined)throw new TypeError('retained frame style is Rust-owned');
 if(input.command!==26&&(!(input.style instanceof Uint8Array)||input.style.length!==48))throw new TypeError('style must be exact 48-byte Rust framing');const reply=decodeGeoScaleReply(await bridge.execute(encodeGeoScaleRequest({command:input.command??11,handle:input.handle,sequence:input.sequence,budget:input.budget,payload:input.command===26?undefined:input.style}))),handle=reply.handle;
 let data:ReturnType<typeof parseGeoSceneData>|undefined,packet:ArrayBuffer|undefined;
 try{if(reply.sourceHandle!==input.handle||reply.sequence!==input.sequence||reply.dataLength>BigInt(MAX_PACKET)||4*Number(reply.dataLength)>input.budget.processorBytes)throw new TypeError('invalid leased data reply');packet=await bridge.read(encodeGeoScaleRequest({command:23,handle}));if(BigInt(packet.byteLength)!==reply.dataLength)throw new TypeError('mismatched leased data size');data=parseGeoSceneData(packet);if(data.identity.sessionHandle!==input.handle||data.identity.sequence!==input.sequence)throw new TypeError('mismatched leased data identity');packet=undefined;}
 catch(error){data=undefined;packet=undefined;await bridge.execute(encodeGeoScaleRequest({command:10,handle}));throw error;}
 let disposal:Promise<void>|undefined;
 return {handle,get data(){if(!data)throw new Error('SceneData disposed');return data;},dispose(){data=undefined;return disposal??=bridge.execute(encodeGeoScaleRequest({command:10,handle})).then(()=>{});}};
}

function validateGeoKey(key:Uint8Array){
 const v=new DataView(key.buffer,key.byteOffset,key.byteLength);
 if(key.length!==160||![4326,3857].includes(v.getUint32(24,true))||![1,4].includes(v.getUint32(28,true))||![4326,3857].includes(v.getUint32(56,true))||v.getUint32(60,true)>1||v.getUint32(120,true)>2||v.getUint32(124,true)>1||v.getUint32(144,true)>1||[64,72,80,88,96,104,112].some(at=>!Number.isFinite(v.getFloat64(at,true))))throw new TypeError('invalid geographic key');
 zero(key,156,160);
 if(v.getUint32(120,true)===0)zero(key,128,144);else if(v.getUint32(120,true)===1)zero(key,136,144);else if(v.getBigInt64(128,true)>=v.getBigInt64(136,true))throw new TypeError('invalid key interval');
 return {sourceRows:v.getBigUint64(16,true),columns:v.getUint32(148,true),rows:v.getUint32(152,true)};
}

/** Raw immutable key/cursor bytes retain Rust's exact f64/i64/u64 identity. */
export function parseGeoMembershipData(packet:ArrayBuffer){
 const {b,v}=response(packet),length=count(v,32,4096),present=v.getUint32(72,true),cursorLength=v.getUint32(76,true);
 if(v.getUint32(8,true)!==2||present>1||cursorLength!==(present?208:0)||packet.byteLength!==256+cursorLength+length*32)throw new TypeError('invalid membership packet');
 zero(b,248,256);if(v.getBigUint64(80,true)!==v.getBigUint64(16,true))throw new TypeError('membership owner mismatch');const key=b.subarray(88,248),cursor=present?b.subarray(256,464):null,at=256+cursorLength,k=validateGeoKey(key);
 if(v.getUint32(12,true)>=k.columns*k.rows)throw new TypeError('membership cell out of range');
 if(cursor){if(!cursor.subarray(0,160).every((n,i)=>n===key[i])||new DataView(cursor.buffer,cursor.byteOffset).getUint32(160,true)!==v.getUint32(12,true))throw new TypeError('cursor key mismatch');zero(cursor,164,168);zero(cursor,200,208);}
 for(let i=0;i<length;i++){zero(b,at+i*32+24,at+i*32+32);if(v.getBigUint64(at+i*32+8,true)>=v.getBigUint64(104,true))throw new TypeError('membership source ordinal out of range');}
 return {packet,key,cursor,length,cell:v.getUint32(12,true),owner:v.getBigUint64(16,true),sequence:v.getBigUint64(24,true),
  record(index:number){if(!Number.isInteger(index)||index<0||index>=length)throw new RangeError('membership index');const p=at+index*32;return {featureId:v.getBigUint64(p,true),sourceRow:v.getBigUint64(p+8,true),chunkIndex:v.getUint32(p+16,true),chunkRow:v.getUint32(p+20,true)};}};
}
export function parseGeoHitData(packet:ArrayBuffer){
 const {b,v}=response(packet),length=count(v,32,4096),key=b.subarray(88,248);
 if(v.getUint32(8,true)!==3||packet.byteLength!==256+length*48||v.getUint32(40,true)>1||v.getUint32(44,true)<1||v.getUint32(44,true)>4096||length>v.getUint32(44,true))throw new TypeError('invalid hit packet');
 const k=validateGeoKey(key);zero(b,12,16);zero(b,36,40);zero(b,72,80);zero(b,248,256);if(v.getBigUint64(80,true)!==v.getBigUint64(16,true))throw new TypeError('hit owner mismatch');
 if([48,56,64].some(at=>!Number.isFinite(v.getFloat64(at,true)))||v.getFloat64(64,true)<0)throw new TypeError('invalid hit query');
 for(let i=0;i<length;i++){const p=256+i*48,tag=v.getUint32(p,true);if(tag>1)throw new TypeError('unknown hit kind');zero(b,p+36,p+40);if(tag===0){zero(b,p+32,p+48);if(v.getBigUint64(p+16,true)>=v.getBigUint64(104,true))throw new TypeError('hit source ordinal out of range');}else{zero(b,p+4,p+32);if(v.getBigUint64(p+40,true)===0n||v.getUint32(p+32,true)>=k.columns*k.rows)throw new TypeError('invalid cell hit');}}
 return {packet,key,length,owner:v.getBigUint64(80,true),sequence:v.getBigUint64(24,true),record(index:number){if(!Number.isInteger(index)||index<0||index>=length)throw new RangeError('hit index');const p=256+index*48;return v.getUint32(p,true)===1?{kind:'cell' as const,cell:v.getUint32(p+32,true),count:v.getBigUint64(p+40,true)}:{kind:'direct' as const,vertex:v.getUint32(p+4,true),featureId:v.getBigUint64(p+8,true),sourceRow:v.getBigUint64(p+16,true),chunkIndex:v.getUint32(p+24,true),chunkRow:v.getUint32(p+28,true)};}};
}
/** Data readers bind a fixed mutation reply, never probe/re-execute mutations. */
export function parseGeoRowsData(packet:ArrayBuffer){
 const {b,v}=response(packet),length=count(v,32,4096),hasNext=v.getUint32(40,true);
 if(v.getUint32(8,true)!==4||hasNext>1||packet.byteLength!==256+length*64||v.getBigUint64(16,true)===0n||v.getBigUint64(24,true)===0n||v.getBigUint64(80,true)!==v.getBigUint64(16,true)||v.getBigUint64(96,true)===0n||v.getBigUint64(104,true)>1000000000n||v.getUint32(64,true)>65536||v.getUint32(68,true)>65536||![1,2,3,4,5,6].includes(v.getUint32(112,true))||![4326,3857].includes(v.getUint32(116,true)))throw new TypeError('invalid original-row packet');
 zero(b,12,16);zero(b,44,48);zero(b,72,80);zero(b,156,160);zero(b,176,256);
 const timeKind=v.getUint32(152,true);if(timeKind===0)zero(b,160,176);else if(timeKind===1)zero(b,168,176);else if(timeKind!==2||v.getBigInt64(160,true)>=v.getBigInt64(168,true))throw new TypeError('invalid original-row time');
 let previous=-1n;
 for(let i=0;i<length;i++){
  const p=256+i*64,ordinal=v.getBigUint64(p+8,true),flags=v.getUint32(p+24,true);
  if(ordinal<=previous||ordinal>=v.getBigUint64(104,true)||v.getUint32(p+16,true)>=65536||v.getUint32(p+20,true)>=65536||flags>127||Boolean(flags&4)!==(!(flags&1)&&Boolean(flags&2))||!(flags&8)&&Boolean(flags&48))throw new TypeError('invalid original-row record');previous=ordinal;
  zero(b,p+28,p+32);zero(b,p+56,p+64);if(!(flags&16))zero(b,p+32,p+40);if(!(flags&32))zero(b,p+40,p+48);if(!(flags&64))zero(b,p+48,p+56);if((flags&48)===48&&v.getBigInt64(p+32,true)>=v.getBigInt64(p+40,true))throw new TypeError('invalid row interval');
 }
 return {packet,length,hasNext:Boolean(hasNext),owner:v.getBigUint64(16,true),sequence:v.getBigUint64(24,true),key:b.subarray(88,176),
  record(index:number){if(!Number.isInteger(index)||index<0||index>=length)throw new RangeError('original-row index');const p=256+index*64,flags=v.getUint32(p+24,true);return {featureId:v.getBigUint64(p,true),sourceRow:v.getBigUint64(p+8,true),chunkIndex:v.getUint32(p+16,true),chunkRow:v.getUint32(p+20,true),geometryNull:Boolean(flags&1),timeEligible:Boolean(flags&2),eligible:Boolean(flags&4),intervalsPresent:Boolean(flags&8),intervalStart:flags&16?v.getBigInt64(p+32,true):null,intervalEnd:flags&32?v.getBigInt64(p+40,true):null,value:flags&64?v.getFloat64(p+48,true):null};}};
}
export async function prepareGeoAuxData<T>(bridge:XygGeoScaleBridge,input:{command:13|14|16;handle:bigint;sequence:bigint;budget:XygGeoQueryBudget;payload?:Uint8Array},parse:(packet:ArrayBuffer)=>T){
 const reply=decodeGeoScaleReply(await bridge.execute(encodeGeoScaleRequest(input))),handle=reply.handle;
 let packet:ArrayBuffer|undefined,data:T|undefined;
 try{if(reply.sourceHandle!==input.handle||reply.sequence!==input.sequence||reply.dataLength>BigInt(MAX_PACKET)||4*Number(reply.dataLength)>input.budget.processorBytes)throw new TypeError('invalid auxiliary data lease');packet=await bridge.read(encodeGeoScaleRequest({command:23,handle}));if(BigInt(packet.byteLength)!==reply.dataLength)throw new TypeError('auxiliary length mismatch');data=parse(packet);packet=undefined;}
 catch(error){packet=undefined;data=undefined;await bridge.execute(encodeGeoScaleRequest({command:10,handle}));throw error;}
 let disposal:Promise<void>|undefined;
 return {handle,get data(){if(data===undefined)throw new Error('Geographic data disposed');return data;},dispose(){data=undefined;return disposal??=bridge.execute(encodeGeoScaleRequest({command:10,handle})).then(()=>{});}};
}

/** Drive the shared index state machine; external immutable sidecar storage is
 * explicit. Storage callbacks must bound their cache and settle before ACK. */
export async function driveGeoIndexSession(bridge:XygGeoScaleBridge,input:{handle:bigint;sequence:bigint;budget:XygGeoQueryBudget;readChunk?:(ticket:XygGeoReadTicket,signal?:AbortSignal)=>Promise<ArrayBuffer|Uint8Array>;readPage?:(ticket:XygGeoReadTicket,signal?:AbortSignal)=>Promise<ArrayBuffer|Uint8Array>;writePage?:(ticket:XygGeoReadTicket,bytes:Uint8Array,signal?:AbortSignal)=>Promise<void>;signal?:AbortSignal}) {
 const {handle,sequence,budget,signal}=input;let cancellation:Promise<ArrayBuffer>|undefined;
 const cancel=()=>cancellation??=bridge.execute(encodeGeoScaleRequest({command:9,handle,sequence}));
 const aborted=()=>new DOMException('Geographic index operation cancelled','AbortError');
 try {for(;;){
  if(signal?.aborted){await cancel();throw aborted();}
  const reply=decodeGeoScaleReply(await bridge.execute(encodeGeoScaleRequest({command:6,handle,sequence,budget})));
  if(reply.handle!==handle||reply.sequence!==sequence)throw new TypeError('mismatched index session reply');
  if([11,12].includes(reply.code))return reply;
  if(![1,7].includes(reply.code)||!reply.ticket)throw new TypeError('unexpected index session step');
  const ticket=reply.ticket,authority=ticket.raw.slice(),authorizedBytes=ticket.encodedBytes,write=reply.code===7;
  let borrowed:ArrayBuffer|Uint8Array|undefined,chunk:Uint8Array|undefined,supply:ArrayBuffer|undefined;
  try {
   if(4*(352+authorizedBytes)>budget.processorBytes)throw new RangeError('index transfer exceeds peak budget');
   if(write){
    if(ticket.kind!==3||!input.writePage)throw new TypeError('index write storage required');
    borrowed=await bridge.read(encodeGeoScaleRequest({command:25,handle,sequence,budget,payload:authority}));chunk=bytes(borrowed);
    if(chunk.byteLength!==authorizedBytes||chunk.byteLength!==chunk.buffer.byteLength)throw new TypeError('exact owning leaf storage required');
    await input.writePage(ticket,chunk,signal);
   }else{
    const reader=ticket.kind===1?input.readChunk:ticket.kind===2?input.readPage:undefined;
    if(!reader)throw new TypeError('index read storage required');borrowed=await reader(ticket,signal);chunk=bytes(borrowed);
    if(chunk.byteLength!==authorizedBytes||chunk.byteLength!==chunk.buffer.byteLength)throw new TypeError('exact owning input storage required');
    if(4*(352+chunk.byteLength)>budget.processorBytes)throw new RangeError('index transfer exceeds peak budget');
    let payload:Uint8Array|undefined=new Uint8Array(96+chunk.byteLength);payload.set(authority);payload.set(chunk,96);supply=encodeGeoScaleRequest({command:7,handle,payload});payload=undefined;
    await bridge.execute(supply);
   }
   if(signal?.aborted){await cancel();throw aborted();}
  }catch(error){borrowed=undefined;chunk=undefined;supply=undefined;await cancel();throw error;}
  finally{borrowed=undefined;chunk=undefined;supply=undefined;if(cancellation)await cancellation;await bridge.execute(encodeGeoScaleRequest({command:write?24:8,handle,...(write?{sequence}:{}),payload:authority}));}
 }}catch(error){await cancel();throw error;}
}
