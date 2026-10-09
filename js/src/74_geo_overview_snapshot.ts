/** Inert overview binary ownership; all freezing and paint validation stay in Rust. */
import {getGeoWorkerSnapshotTransport,isGeoWorkerTerminated,type XygWasmWorker} from './47_wasm';
import {overviewFrameAuthority,type GeoOverviewFrame} from './71_geo_overview_owner';
import type {XygGeoScaleBridge} from './63_geo_source';

const HEADER=256,PROFILE_BYTES=2432,MAX_SCENE=757920,MAX_PACKET=PROFILE_BYTES+MAX_SCENE;
const CAP=Symbol('issued overview binary');
export interface OverviewBinaryFreezeOptions {budgetBytes?:number;signal?:AbortSignal}
export class GeoOverviewBinaryUncertainAllocation extends Error {
 constructor(){super('Snapshot allocation confirmation is unknown; terminate the genuine issuing Worker before releasing the accepted frame');this.name='GeoOverviewBinaryUncertainAllocation';}
}
export class GeoOverviewBinaryCleanupPending extends Error {
 constructor(readonly owner:GeoOverviewFrozenBinary,readonly cause:unknown){super('Known snapshot cleanup remains pending; retry owner.dispose()');this.name='GeoOverviewBinaryCleanupPending';}
}
function request(command:number,handle:bigint,sequence=0n,budget=0){
 const b=new ArrayBuffer(HEADER),v=new DataView(b);new Uint8Array(b).set([88,89,71,74]);v.setUint32(4,1,true);v.setUint32(8,command,true);v.setBigUint64(16,handle,true);v.setBigUint64(24,sequence,true);v.setBigUint64(32,BigInt(budget),true);return b;
}
function receipt(packet:ArrayBuffer,sequence:bigint,length:number,handle?:bigint){
 if(!(packet instanceof ArrayBuffer)||packet.byteLength!==HEADER)throw new TypeError('Invalid snapshot receipt size');
 const b=new Uint8Array(packet),v=new DataView(packet);
 if(v.getUint32(0,true)!==0x57475958||v.getUint32(4,true)!==1||v.getUint32(8,true)!==0||b.subarray(12,16).some(Boolean)||b.subarray(40).some(Boolean)||v.getBigUint64(24,true)!==sequence||v.getBigUint64(32,true)!==BigInt(length))throw new TypeError('Snapshot receipt differs from its private request');
 const h=v.getBigUint64(16,true);if(h===0n||handle!==undefined&&h!==handle)throw new TypeError('Snapshot receipt owner mismatch');return h;
}
function definitive(error:unknown){return typeof error==='object'&&error!==null&&['XYG_GEO_INVALID_ARGUMENT','XYG_GEO_RESOURCE_LIMIT','XYG_GEO_STALE_HANDLE','XYG_GEO_SNAPSHOT_UNSUPPORTED_EXPORT'].includes(String((error as {code?:unknown}).code));}
function aborted(){return new DOMException('Overview binary freeze cancelled','AbortError');}
function expectedPrefix(source:Uint8Array,length:number){
 const out=new Uint8Array(PROFILE_BYTES),v=new DataView(out.buffer),s=new DataView(source.buffer,source.byteOffset,source.byteLength);
 const copy=(at:number,from:number,n:number)=>out.set(source.subarray(from,from+n),at);
 out.set([88,89,71,88]);v.setUint32(4,4,true);v.setUint32(8,32,true);v.setBigUint64(16,BigInt(length),true);v.setBigUint64(24,s.getBigUint64(32,true),true);v.setUint32(32,1,true);
 copy(52,224,4);copy(56,232,16);copy(72,96,8);copy(80,112,56);copy(136,176,8);copy(176,184,8);v.setUint32(192,1,true);v.setUint32(196,2144,true);
 copy(208,80,8);copy(224,56,8);copy(232,192,24);copy(256,64,8);copy(264,88,8);copy(272,76,4);copy(276,72,4);
 out.set([88,89,79,70],288);v.setUint32(292,1,true);v.setUint32(296,3,true);v.setUint32(300,16,true);copy(304,80,8);v.setUint32(312,1,true);copy(320,48,8);copy(328,64,8);copy(336,56,8);copy(344,88,8);copy(352,72,4);copy(356,76,4);v.setBigUint64(360,2048n,true);copy(384,256,2048);return out;
}
/** Bytes are an inert borrow; drop external views before disposal ACK. */
export class GeoOverviewFrozenBinary {
 #handle:bigint;#sequence:bigint;#worker:XygWasmWorker;#sourceBridge:XygGeoScaleBridge;#bridge:XygGeoScaleBridge;
 #header:Uint8Array|undefined;#length:number;#bytes:Uint8Array|undefined;#read:Promise<void>|undefined;#disposal:Promise<void>|undefined;#closed=false;
 constructor(cap:symbol,worker:XygWasmWorker,sourceBridge:XygGeoScaleBridge,bridge:XygGeoScaleBridge,handle:bigint,sequence:bigint,header:Uint8Array,length:number){
  if(cap!==CAP)throw new TypeError('Issued overview snapshot required');this.#worker=worker;this.#sourceBridge=sourceBridge;this.#bridge=bridge;this.#handle=handle;this.#sequence=sequence;this.#header=header;this.#length=length;
 }
 get sequence(){return this.#sequence;}get kind(){return 'xygx-v4' as const;}get closed(){return this.#closed;}
 get bytes():Readonly<Uint8Array>{if(!this.#bytes||this.#closed)throw new Error('Overview binary unavailable');return this.#bytes;}
 private initialize(){
  this.#read=this.#bridge.read(request(20,this.#handle)).then(packet=>{
   if(!(packet instanceof ArrayBuffer)||packet.byteLength!==this.#length||packet.byteLength>MAX_PACKET)throw new TypeError('Snapshot plane length mismatch');
   const bytes=new Uint8Array(packet),expected=expectedPrefix(this.#header!,this.#length);
   for(let i=0;i<PROFILE_BYTES;i++)if(bytes[i]!==expected[i])throw new TypeError(`Snapshot metadata differs from accepted overview at ${i}: ${bytes[i]} != ${expected[i]}`);
   const scene=new DataView(packet,PROFILE_BYTES);if(scene.getUint32(0,true)!==0x53475958||scene.getUint32(4,true)!==32)throw new TypeError('Snapshot Scene32 mismatch');this.#bytes=bytes;
  });return this.#read;
 }
 dispose():Promise<void>{
  this.#bytes=undefined;
  if(this.#closed)return Promise.resolve();
  if(!this.#disposal)this.#disposal=(async()=>{
   await this.#read?.catch(()=>{});this.#bytes=undefined;this.#header=undefined;
   if(!isGeoWorkerTerminated(this.#worker,this.#sourceBridge))receipt(await this.#bridge.execute(request(3,this.#handle)),0n,0,this.#handle);
   this.#closed=true;
  })().catch(error=>{this.#disposal=undefined;throw error;});return this.#disposal;
 }
}
const initialize=GeoOverviewFrozenBinary.prototype['initialize'],dispose=GeoOverviewFrozenBinary.prototype.dispose;
/** Internal factory: the private Frame issuer is checked before extracting its numeric handle. */
export function beginOverviewBinaryFreeze(worker:XygWasmWorker,bridge:XygGeoScaleBridge,frame:GeoOverviewFrame,input:OverviewBinaryFreezeOptions,onMutation:(state:'known'|'rejected'|'uncertain')=>void){
 const a=overviewFrameAuthority(frame),transport=getGeoWorkerSnapshotTransport(worker,bridge);
 if(!a||a.bridge!==bridge||a.header.byteLength!==2304)throw new TypeError('Snapshot requires the accepted issued overview frame');
 const scene=Number(new DataView(a.header.buffer,a.header.byteOffset).getBigUint64(32,true)),length=PROFILE_BYTES+scene;
 if(scene<160||scene>MAX_SCENE)throw new RangeError('Overview snapshot profile exceeded');
 const budget=input.budgetBytes??transport.budgetBytes;
 if(!Number.isSafeInteger(budget)||budget<HEADER||budget>transport.budgetBytes)throw new RangeError('Snapshot budget exceeds its issuing Worker phase');
 return (async()=>{
  let owner:GeoOverviewFrozenBinary|undefined,handle:bigint;
  if(input.signal?.aborted){onMutation('rejected');throw aborted();}
  try{handle=receipt(await transport.bridge.execute(request(6,a.handle,a.sequence,budget)),a.sequence,length);}
  catch(cause){const known=definitive(cause)||isGeoWorkerTerminated(worker,bridge);onMutation(known?'rejected':'uncertain');if(!known)throw new GeoOverviewBinaryUncertainAllocation();throw cause;}
  owner=new GeoOverviewFrozenBinary(CAP,worker,bridge,transport.bridge,handle,a.sequence,a.header,length);onMutation('known');
  try{if(input.signal?.aborted)throw aborted();await initialize.call(owner);if(input.signal?.aborted)throw aborted();return owner;}
  catch(cause){try{await dispose.call(owner);}catch(cleanup){throw new GeoOverviewBinaryCleanupPending(owner,cleanup);}throw cause;}
 })();
}
/** Internal cleanup always uses the captured canonical owner method. */
export function disposeOverviewBinary(owner:GeoOverviewFrozenBinary){return dispose.call(owner);}
