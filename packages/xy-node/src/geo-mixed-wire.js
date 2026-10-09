// Mechanical type stripping of js/src/66_geo_mixed.ts; no host policy.
/** Thin XYMX/XYMY/XYMF framing. Rust owns every composition/admission decision. */
const MAX_MIXED_BYTES=32*1024*1024, MIXED_PHASE_BYTES=128*1024*1024;
                                   
                                                                       
                                                                                     
                                                            
                                          
 
                                                                                                                                     
function mixedU64(n       ){if(typeof n!=='bigint'||n<0n||n>0xffffffffffffffffn)throw new TypeError('expected u64 bigint');return n;}
function mixedZero(b           ){if(b.some(Boolean))throw new TypeError('nonzero mixed reserved bytes');}
function mixedCount(v         ,at       ,max=MAX_MIXED_BYTES){const n=v.getBigUint64(at,true);if(n>BigInt(max))throw new RangeError('mixed plane exceeds bound');return Number(n);}
export function encodeGeoMixedRequest(input                 )             {
 const command=input.command, budget=input.budget??0, nonce=input.nonce??0n;
 if(![1,2,3,4,5,6,20].includes(command)||!Number.isSafeInteger(budget)||budget<0||budget>MIXED_PHASE_BYTES)throw new TypeError('invalid mixed command/budget');
 if([1,3,4,5].includes(command)&&budget!==0||[2,6,20].includes(command)&&budget<65536||[1,2,5].includes(command)&&nonce!==0n)throw new TypeError('field does not belong to mixed command');
 const fields=['sourceHandle','sourceSequence','tileHandle','tileEpoch','tileCacheHandle','tileViewId','tileTime','snapshot','stamps']         ;
 if(command!==2&&fields.some(k=>input[k]!==undefined))throw new TypeError('prepare fields only belong to mixed command2');
 let count=0;
 if(command===2){if(!(input.snapshot instanceof Uint8Array)||input.snapshot.length!==160||!(input.stamps instanceof Uint8Array)||input.stamps.length%96||input.stamps.length>64*96||![0,1].includes(input.tileTime??-1))throw new TypeError('exact mixed snapshot/stamps required');count=input.stamps.length/96;}
 const payload=command===2?160+count*96:0, out=new ArrayBuffer(256+payload), b=new Uint8Array(out),v=new DataView(out);
 b.set([88,89,77,88]);v.setUint32(4,1,true);v.setUint32(8,command,true);v.setBigUint64(16,mixedU64(input.handle??0n),true);v.setBigUint64(24,mixedU64(nonce),true);v.setBigUint64(32,BigInt(budget),true);v.setBigUint64(40,BigInt(payload),true);
 if(command===2){[input.sourceHandle,input.sourceSequence,input.tileHandle,input.tileEpoch,input.tileCacheHandle,input.tileViewId].forEach((n,i)=>{if(n===undefined)throw new TypeError('explicit mixed authority required');v.setBigUint64(64+i*8,mixedU64(n),true);});v.setUint32(112,input.tileTime ,true);v.setUint32(116,count,true);b.set(input.snapshot ,256);b.set(input.stamps ,416);}
 return out;
}
export function decodeGeoMixedReply(packet            ){
 if(!(packet instanceof ArrayBuffer)||packet.byteLength!==256)throw new TypeError('fixed mixed reply required');
 const b=new Uint8Array(packet),v=new DataView(packet);
 if(String.fromCharCode(...b.subarray(0,4))!=='XYMY'||v.getUint32(4,true)!==1||v.getUint32(8,true)>2)throw new TypeError('mixed reply magic/version/kind');mixedZero(b.subarray(12,16));mixedZero(b.subarray(48));
 return {kind:v.getUint32(8,true),handle:v.getBigUint64(16,true),nonce:v.getBigUint64(24,true),coordinator:v.getBigUint64(32,true),length:mixedCount(v,40)};
}
/** All planes are views into one owned receipt; drop them before disposal ACK. */
export function parseGeoMixedData(packet            ){
 if(!(packet instanceof ArrayBuffer)||packet.byteLength<624||packet.byteLength>MAX_MIXED_BYTES)throw new TypeError('mixed data extent');
 const b=new Uint8Array(packet),v=new DataView(packet),sceneLength=mixedCount(v,32),tileLength=mixedCount(v,40);
 if(String.fromCharCode(...b.subarray(0,4))!=='XYMF'||v.getUint32(4,true)!==1||v.getUint32(8,true)!==0||v.getUint32(128,true)>1||mixedCount(v,136)!==packet.byteLength||256+sceneLength+tileLength+208!==packet.byteLength||sceneLength<160||tileLength<384)throw new TypeError('mixed data framing');
 mixedZero(b.subarray(12,16));mixedZero(b.subarray(132,136));mixedZero(b.subarray(160,256));
 const scene=b.subarray(256,256+sceneLength),sv=new DataView(packet,256,sceneLength),tile=b.subarray(256+sceneLength,256+sceneLength+tileLength),tv=new DataView(tile.buffer,tile.byteOffset,tile.byteLength);
 if(String.fromCharCode(...scene.subarray(0,4))!=='XYGS'||sv.getUint32(4,true)!==32||sv.getUint32(8,true)!==160||String.fromCharCode(...tile.subarray(0,4))!=='XYGU'||tv.getUint32(4,true)!==1||tv.getUint32(8,true)!==1||tv.getBigUint64(16,true)!==v.getBigUint64(112,true)||tv.getBigUint64(24,true)!==v.getBigUint64(104,true)||tv.getBigUint64(32,true)!==v.getBigUint64(120,true))throw new TypeError('mixed embedded authority');
 const records=mixedCount(sv,16,2000000),styles=mixedCount(sv,24,2000000),recordStart=mixedCount(v,48,records),recordEnd=mixedCount(v,56,records),styleStart=mixedCount(v,64,styles),styleEnd=mixedCount(v,72,styles);
 if(recordEnd<recordStart||styleEnd<styleStart)throw new TypeError('mixed retained ranges');
 const snapshot=b.subarray(packet.byteLength-208,packet.byteLength-48),style=b.subarray(packet.byteLength-48),q=new DataView(snapshot.buffer,snapshot.byteOffset,160);
 if(![4326,3857].includes(q.getUint32(0,true))||q.getUint32(4,true)>1||q.getUint32(128,true)>2||[8,16,24,32,40,48,56].some(at=>!Number.isFinite(q.getFloat64(at,true))))throw new TypeError('mixed snapshot framing');mixedZero(snapshot.subarray(132,136));mixedZero(snapshot.subarray(152));mixedZero(style.subarray(33));
 if([8,16,24].some(at=>!Number.isFinite(new DataView(style.buffer,style.byteOffset,48).getFloat64(at,true))))throw new TypeError('nonfinite mixed style');
 const timeKind=q.getUint32(128,true);if(timeKind===0)mixedZero(snapshot.subarray(136,152));else if(timeKind===1)mixedZero(snapshot.subarray(144,152));else if(q.getBigInt64(136,true)>=q.getBigInt64(144,true))throw new TypeError('mixed time window');
 for(let i=0;i<7;i++)if(q.getBigUint64(8+i*8,true)!==tv.getBigUint64(80+i*8,true))throw new TypeError('mixed camera mismatch');
 if(q.getUint32(0,true)!==tv.getUint32(72,true)||q.getUint32(4,true)!==tv.getUint32(76,true))throw new TypeError('mixed camera CRS/wrap mismatch');
 return {packet,scene,tile,snapshot,style,coordinator:v.getBigUint64(16,true),nonce:v.getBigUint64(24,true),sourceHandle:v.getBigUint64(80,true),sourceSequence:v.getBigUint64(88,true),tileHandle:v.getBigUint64(96,true),tileEpoch:v.getBigUint64(104,true),tileTime:v.getUint32(128,true),retainedRecords:{start:recordStart,end:recordEnd},retainedStyles:{start:styleStart,end:styleEnd},visibleVertices:v.getBigUint64(144,true),projectedVertices:v.getBigUint64(152,true)};
}
export async function prepareGeoMixedData(bridge                  ,input                                                                                                                                                                                                                                  ){
 if(input.command!==2)throw new TypeError('mixed prepare requires command2');
 const receipt=decodeGeoMixedReply(await bridge.execute(encodeGeoMixedRequest(input)));let packet                      ,data                                               ;
 try{if(receipt.kind!==1||receipt.coordinator!==input.handle||receipt.nonce===0n||receipt.length*2>(input.budget??0))throw new TypeError('mixed candidate receipt identity');packet=await bridge.read(encodeGeoMixedRequest({command:20,handle:receipt.handle,nonce:receipt.nonce,budget:input.budget}));if(packet.byteLength!==receipt.length)throw new TypeError('mixed candidate receipt length');data=parseGeoMixedData(packet);if(data.coordinator!==receipt.coordinator||data.nonce!==receipt.nonce||data.sourceHandle!==input.sourceHandle||data.sourceSequence!==input.sourceSequence||data.tileHandle!==input.tileHandle||data.tileEpoch!==input.tileEpoch)throw new TypeError('mixed candidate data identity');packet=undefined;}
 catch(error){data=undefined;packet=undefined;await bridge.execute(encodeGeoMixedRequest({command:5,handle:receipt.handle}));throw error;}
 let disposal                        ;
 return {handle:receipt.handle,nonce:receipt.nonce,get data(){if(!data)throw new Error('mixed Data disposed');return data;},async commit(){if(!data)throw new Error('mixed Data disposed');await bridge.execute(encodeGeoMixedRequest({command:3,handle:receipt.handle,nonce:receipt.nonce}));},async cancel(){await bridge.execute(encodeGeoMixedRequest({command:4,handle:receipt.handle,nonce:receipt.nonce}));},dispose(){data=undefined;return disposal??=bridge.execute(encodeGeoMixedRequest({command:5,handle:receipt.handle})).then(()=>{},error=>{disposal=undefined;throw error;});}};
}
/** Trusted Tile read23 descriptor: no host recomputation of content digests. */
export function parseGeoMixedTileDescriptor(packet            ){
 if(!(packet instanceof ArrayBuffer)||packet.byteLength<256||packet.byteLength>256+64*96)throw new TypeError('tile provenance extent');
 const b=new Uint8Array(packet),v=new DataView(packet),count=mixedCount(v,48,64);
 if(String.fromCharCode(...b.subarray(0,4))!=='XYUP'||v.getUint32(4,true)!==1||mixedCount(v,56,6400)!==packet.byteLength||packet.byteLength!==256+count*96)throw new TypeError('tile provenance framing');
 mixedZero(b.subarray(8,16));mixedZero(b.subarray(64,256));
 const stamps=b.subarray(256);
 for(let i=0;i<count;i++){const at=i*96,k=new DataView(stamps.buffer,stamps.byteOffset+at,96),z=k.getUint32(64,true);mixedZero(stamps.subarray(at+76,at+80));if(k.getUint32(56,true)>1||k.getUint32(60,true)>1||z>25||k.getUint32(68,true)>=2**z||k.getUint32(72,true)>=2**z)throw new TypeError('tile provenance key');if(k.getUint32(56,true)===0)mixedZero(stamps.subarray(at+40,at+56));else if(k.getBigInt64(40,true)>=k.getBigInt64(48,true))throw new TypeError('tile provenance time');}
 return {packet,handle:v.getBigUint64(16,true),epoch:v.getBigUint64(24,true),cache:v.getBigUint64(32,true),view:v.getBigUint64(40,true),stamps};
}
