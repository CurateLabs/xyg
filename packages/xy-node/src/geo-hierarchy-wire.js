// Generated from js/src/70_geo_hierarchy.ts; run scripts/gen_geo_hierarchy_node.mjs.
/** Thin hierarchy transport. Rust owns sorting, pruning, time and exact LOD. */
import {encodeGeoScaleRequest, decodeGeoScaleReply, parseGeoSceneData,
                                                                        } from './geoscale.js';

export function encodeGeoHierarchyRequest(input                   )             {
 if(![6,7,8,9,10,37,38,39,40,41].includes(input.command))throw new TypeError('unknown hierarchy command');
 const request=encodeGeoScaleRequest({...input,command:input.command===38?5:6});
 const view=new DataView(request);view.setUint32(8,input.command,true);return request;
}
function zero(bytes           ,start       ,end       ){if(bytes.subarray(start,end).some(n=>n!==0))throw new TypeError('nonzero hierarchy reserved bytes');}

function ticket(raw           )                    {
 const v=new DataView(raw.buffer,raw.byteOffset,raw.byteLength),kind=v.getUint32(32,true),size=v.getBigUint64(48,true);
 zero(raw,36,40);zero(raw,104,128);
 if(![1,2,3,4,5].includes(kind)||size===0n||size>BigInt(kind===1?16*1024*1024:65536))throw new TypeError('invalid hierarchy ticket');
 if(kind===1){if(v.getUint32(76,true)>65536||v.getBigUint64(88,true)!==size||raw.subarray(96,104).some((n,i)=>n!==raw[56+i]))throw new TypeError('mismatched canonical ticket');}
 else zero(raw,64,104);
 return {raw,owner:v.getBigUint64(0,true),namespace:v.getBigUint64(8,true),serial:v.getBigUint64(16,true),sequence:v.getBigUint64(24,true),kind,page:v.getBigUint64(40,true),encodedBytes:Number(size),digest:raw.slice(56,64),generation:v.getBigUint64(64,true),chunkIndex:v.getUint32(72,true),rows:v.getUint32(76,true),firstRow:v.getBigUint64(80,true)};
}
export function decodeGeoHierarchyReply(buffer            ) {
 if(!(buffer instanceof ArrayBuffer)||buffer.byteLength!==256)throw new TypeError('fixed hierarchy reply required');
 const b=new Uint8Array(buffer),v=new DataView(buffer),code=v.getUint32(8,true);
 if(String.fromCharCode(...b.subarray(0,4))!=='XYGZ'||v.getUint32(4,true)!==1)throw new TypeError('invalid hierarchy reply');zero(b,12,16);
 const handle=v.getBigUint64(16,true),sequence=v.getBigUint64(24,true);
 if(code===0||code===6||code===10){const ordinary=decodeGeoScaleReply(buffer);return {...ordinary,ticket:null,hierarchyStats:null,namespace:0n};}
 if(![1,2,7,9,17,18,19].includes(code))throw new TypeError('invalid hierarchy reply code');
 let loan                        =null;
 if([1,2,7].includes(code)){zero(b,32,64);zero(b,192,256);if(b.subarray(64,192).some(n=>n!==0)){loan=ticket(b.slice(64,192));if(loan.sequence!==sequence||code===1&&loan.kind===3||code===7&&loan.kind!==3)throw new TypeError('mismatched hierarchy loan');}else if(code!==2)throw new TypeError('missing hierarchy ticket');}
 else if(code===18){zero(b,32,40);zero(b,56,256);}
 else if(code===19){zero(b,32,160);zero(b,200,256);if(![1,2].includes(v.getUint32(192,true))||v.getUint32(196,true)>256)throw new TypeError('invalid hierarchy stats');}
 else zero(b,32,256);
 return {code,handle,sequence,ticket:loan,hierarchyStats:code===19?{directoryReads:v.getBigUint64(160,true),leafReads:v.getBigUint64(168,true),bytesRead:v.getBigUint64(176,true),decodedVertices:v.getBigUint64(184,true),passes:v.getUint32(192,true),cells:v.getUint32(196,true)}:null,namespace:code===18?v.getBigUint64(48,true):0n,fallbackReasonCode:null};
}
export class GeoHierarchyFallback extends Error {reasonCode       ;constructor(reasonCode       ){super(`Rust hierarchy requires explicit canonical fallback (${reasonCode})`);this.reasonCode=reasonCode;this.name='GeoHierarchyFallback';}}
export class GeoHierarchyUnsupportedSelected extends Error {constructor(){super('Rust hierarchy does not support selected authority');this.name='GeoHierarchyUnsupportedSelected';}}
function aborted(){return new Error('hierarchy operation aborted');}
function exact(value                       ,size       ){const b=value instanceof Uint8Array?value:new Uint8Array(value);if(b.byteLength!==size||b.buffer.byteLength>size)throw new TypeError('callback must return exact bounded storage');return b;}

export async function driveGeoHierarchy(bridge                  ,input                                                                                                 ) {
 const {handle,sequence,budget,signal}=input;let cancellation                           ;
 const cancel=()=>cancellation??=bridge.execute(encodeGeoHierarchyRequest({command:9,handle,sequence}));
 const onAbort=()=>{void cancel().catch(()=>{});};signal?.addEventListener('abort',onAbort,{once:true});
 try{for(;;){if(signal?.aborted)throw aborted();const reply=decodeGeoHierarchyReply(await bridge.execute(encodeGeoHierarchyRequest({command:6,handle,sequence,budget})));
  if(reply.handle!==handle||reply.sequence!==sequence)throw new TypeError('mismatched hierarchy authority');
  if(signal?.aborted){if(!reply.ticket)throw aborted();}
  else if(reply.code===18||reply.code===19)return reply;
  else if(reply.code===10)throw new GeoHierarchyFallback(reply.fallbackReasonCode );
  const loan=reply.ticket;if(!loan||![1,7].includes(reply.code))throw new Error('hierarchy did not complete');
  const authority=loan.raw.slice(),size=loan.encodedBytes,write=loan.kind===3,publicTicket={...loan,raw:loan.raw.slice(),digest:loan.digest.slice()};
  let borrowed                                 ,view                     ,payload                     ,request                      ;
  try{if(signal?.aborted)throw aborted();if(4*(384+size)>budget.processorBytes)throw new RangeError('hierarchy transfer exceeds phase budget');
   if(write){borrowed=await bridge.read(encodeGeoHierarchyRequest({command:40,handle,sequence,payload:authority}));if(signal?.aborted)throw aborted();view=exact(borrowed,size);await input.writePage(publicTicket,view,signal);}
   else {borrowed=await (loan.kind===1?input.readChunk:input.readPage)(publicTicket,signal);if(signal?.aborted)throw aborted();view=exact(borrowed,size);payload=new Uint8Array(128+size);payload.set(authority);payload.set(view,128);request=encodeGeoHierarchyRequest({command:7,handle,sequence,payload});await bridge.execute(request);}
   if(signal?.aborted)throw aborted();
  }catch(error){borrowed=view=payload=request=undefined;await cancel().catch(()=>{});throw error;}
  finally{borrowed=view=payload=request=undefined;await bridge.execute(encodeGeoHierarchyRequest({command:write?41:8,handle,sequence,payload:authority}));}
 }}catch(error){await cancel().catch(()=>{});throw error;}finally{signal?.removeEventListener('abort',onAbort);if(cancellation)await cancellation.catch(()=>{});}
}
export async function prepareGeoHierarchyScene(bridge                  ,input                                                                          ) {
 if(!(input.style instanceof Uint8Array)||input.style.byteLength!==48||input.style.buffer.byteLength>48)throw new TypeError('exact48-byte style required');
 const r=decodeGeoScaleReply(await bridge.execute(encodeGeoHierarchyRequest({command:39,...input,payload:input.style}))),handle=r.handle;
 let packet                      ,data                                               ;
 try{if(r.code!==0||r.sourceHandle!==input.handle||r.sequence!==input.sequence||4n*r.dataLength>BigInt(input.budget.processorBytes))throw new TypeError('invalid hierarchy Scene receipt');packet=await bridge.read(encodeGeoScaleRequest({command:23,handle}));if(BigInt(packet.byteLength)!==r.dataLength||packet.byteLength>32*1024*1024)throw new TypeError('invalid Scene length');data=parseGeoSceneData(packet);if(data.identity.sessionHandle!==input.handle||data.identity.sequence!==input.sequence)throw new TypeError('mismatched Scene identity');packet=undefined;}
 catch(error){packet=data=undefined;await bridge.execute(encodeGeoScaleRequest({command:10,handle}));throw error;}
 let disposal                        ;
 return {handle,get data(){if(!data)throw new Error('SceneData disposed');return data;},dispose(){data=undefined;if(disposal)return disposal;const task=bridge.execute(encodeGeoScaleRequest({command:10,handle})).then(()=>{});disposal=task;task.catch(()=>{if(disposal===task)disposal=undefined;});return task;}};
}
