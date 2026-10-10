/** Snapshot-local durable ownership; freezing and all metadata policy stay in Rust. */
import {getGeoWorkerSnapshotTransport,beginGeoWorkerMutationCapture,isGeoWorkerTerminated,type XygWasmWorker} from './47_wasm';
import {overviewFrameAuthority,type GeoOverviewFrame} from './71_geo_overview_owner';
import type {XygGeoScaleBridge} from './63_geo_source';
const HEADER=256,PROFILE_BYTES=2432,MAX_SCENE=757920,MAX_PACKET=PROFILE_BYTES+MAX_SCENE;
const CAP=Symbol('issued overview binary');
const nonces=new WeakMap<GeoOverviewFrame,bigint>();
export interface OverviewBinaryFreezeOptions {budgetBytes?:number;signal?:AbortSignal}
export class GeoOverviewBinaryUncertainAllocation extends Error {
 constructor(readonly owner?:GeoOverviewSnapshotAttempt){super('Snapshot confirmation remains pending; recover or dispose its issued owner');this.name='GeoOverviewBinaryUncertainAllocation';}
}
export class GeoOverviewBinaryCleanupPending extends Error {
 constructor(readonly owner:GeoOverviewFrozenBinary|GeoOverviewSnapshotAttempt,readonly cause:unknown){super('Snapshot cleanup remains pending; retry owner.dispose()');this.name='GeoOverviewBinaryCleanupPending';}
}
function request(command:number,handle:bigint,sequence=0n,budget=0,nonce=0n,target=0n,action=0){
 const b=new ArrayBuffer(HEADER),v=new DataView(b);new Uint8Array(b).set([88,89,71,74]);v.setUint32(4,1,true);v.setUint32(8,command,true);v.setBigUint64(16,handle,true);v.setBigUint64(24,sequence,true);v.setBigUint64(32,BigInt(budget),true);v.setBigUint64(40,target,true);v.setUint32(48,action,true);v.setBigUint64(240,nonce,true);return b;
}
function receipt(packet:ArrayBuffer,sequence:bigint,length:number,handle?:bigint,allowZero=false,kind=0){
 if(!(packet instanceof ArrayBuffer)||packet.byteLength!==HEADER)throw new TypeError('Invalid snapshot receipt size');
 const b=new Uint8Array(packet),v=new DataView(packet);
 if(v.getUint32(0,true)!==0x57475958||v.getUint32(4,true)!==1||v.getUint32(8,true)!==kind||b.subarray(12,16).some(Boolean)||b.subarray(40).some(Boolean)||v.getBigUint64(24,true)!==sequence||v.getBigUint64(32,true)!==BigInt(length))throw new TypeError('Snapshot receipt differs from private request');
 const h=v.getBigUint64(16,true);if(!allowZero&&h===0n||handle!==undefined&&h!==handle)throw new TypeError('Snapshot receipt owner mismatch');return h;
}
function retired(packet:ArrayBuffer,sequence:bigint){if(!(packet instanceof ArrayBuffer)||packet.byteLength!==HEADER||new DataView(packet).getUint32(8,true)!==2)return false;receipt(packet,sequence,0,0n,true,2);return true;}
type SnapshotMutationResult<T>={ok:true;value:T}|{ok:false;cause:unknown;outcome?:{code?:string;status?:number|null}};
async function mutation<T>(bridge:XygGeoScaleBridge,canonical:ArrayBuffer,validate:(packet:ArrayBuffer)=>T):Promise<SnapshotMutationResult<T>>{
 let capture:ReturnType<typeof beginGeoWorkerMutationCapture>|undefined;
 try{capture=beginGeoWorkerMutationCapture(bridge,canonical);const packet=await bridge.execute(canonical.slice(0));
  if(!capture.outcome(packet)?.reply)throw new TypeError('Snapshot mutation confirmation lacks its genuine issuing Worker outcome');
  return {ok:true,value:validate(packet)};
 }catch(cause){return {ok:false,cause,outcome:capture?.outcome(cause)};}
 finally{capture?.close();}
}
function mutationValue<T>(result:SnapshotMutationResult<T>):T{if(result.ok===false)throw result.cause;return result.value;}
function aborted(){return new DOMException('Overview binary freeze cancelled','AbortError');}
function expectedPrefix(source:Uint8Array,length:number){
 const out=new Uint8Array(PROFILE_BYTES),v=new DataView(out.buffer),s=new DataView(source.buffer,source.byteOffset,source.byteLength);
 const copy=(at:number,from:number,n:number)=>out.set(source.subarray(from,from+n),at);
 out.set([88,89,71,88]);v.setUint32(4,4,true);v.setUint32(8,32,true);v.setBigUint64(16,BigInt(length),true);v.setBigUint64(24,s.getBigUint64(32,true),true);v.setUint32(32,1,true);
 copy(52,224,4);copy(56,232,16);copy(72,96,8);copy(80,112,56);copy(136,176,8);copy(176,184,8);v.setUint32(192,1,true);v.setUint32(196,2144,true);
 copy(208,80,8);copy(224,56,8);copy(232,192,24);copy(256,64,8);copy(264,88,8);copy(272,76,4);copy(276,72,4);
 out.set([88,89,79,70],288);v.setUint32(292,1,true);v.setUint32(296,3,true);v.setUint32(300,16,true);copy(304,80,8);v.setUint32(312,1,true);copy(320,48,8);copy(328,64,8);copy(336,56,8);copy(344,88,8);copy(352,72,4);copy(356,76,4);v.setBigUint64(360,2048n,true);copy(384,256,2048);return out;
}
/** A private exact birth captured before allocation. No host-authored handle can mint one. */
export class GeoOverviewSnapshotAttempt {
 #worker:XygWasmWorker;#sourceBridge:XygGeoScaleBridge;#bridge:XygGeoScaleBridge;#request:ArrayBuffer;#issuer:bigint;#sequence:bigint;#nonce:bigint;#header:Uint8Array;#length:number;
 #target:bigint|undefined;#confirmed=false;#retired=false;#closed=false;#closing=false;#rejected=false;
 #allocation:Promise<void>|undefined;#recovery:Promise<GeoOverviewFrozenBinary>|undefined;#disposal:Promise<void>|undefined;#owner:GeoOverviewFrozenBinary|undefined;
 #notify:(state:'known'|'rejected'|'uncertain')=>void;
 constructor(cap:symbol,worker:XygWasmWorker,sourceBridge:XygGeoScaleBridge,bridge:XygGeoScaleBridge,issuer:bigint,sequence:bigint,nonce:bigint,budget:number,header:Uint8Array,length:number,notify:(state:'known'|'rejected'|'uncertain')=>void){
  if(cap!==CAP)throw new TypeError('Issued Snapshot attempt required');this.#worker=worker;this.#sourceBridge=sourceBridge;this.#bridge=bridge;this.#issuer=issuer;this.#sequence=sequence;this.#nonce=nonce;this.#header=header;this.#length=length;this.#notify=notify;this.#request=request(6,issuer,sequence,budget,nonce);
 }
 get closed(){return this.#closed;}
 #control(action:number){return request(7,this.#issuer,this.#sequence,0,this.#nonce,this.#retired?0n:this.#target??0n,action);}
 #allocate():Promise<void>{
  if(this.#closed||this.#rejected)return Promise.reject(new Error('Snapshot birth closed'));
  if(this.#confirmed||this.#retired)return Promise.resolve();
  if(!this.#allocation)this.#allocation=(async()=>{
   if(this.#target===undefined){
    const result=await mutation(this.#bridge,this.#request,packet=>retired(packet,this.#sequence)?{retired:true,target:undefined}:{retired:false,target:receipt(packet,this.#sequence,this.#length)});
    if(result.ok===false){
     if(result.outcome&&['XYG_GEO_INVALID_ARGUMENT','XYG_GEO_RESOURCE_LIMIT','XYG_GEO_STALE_HANDLE','XYG_GEO_SNAPSHOT_UNSUPPORTED_EXPORT'].includes(result.outcome.code??'')){this.#rejected=true;this.#closed=true;this.#notify('rejected');throw result.cause;}
     this.#notify('uncertain');throw new GeoOverviewBinaryUncertainAllocation(this);
    }
    if(result.value.retired)this.#retired=true;else this.#target=result.value.target;
   }
   try{const isRetired=mutationValue(await mutation(this.#bridge,this.#control(0),packet=>{if(retired(packet,this.#sequence))return true;receipt(packet,this.#sequence,0,this.#target);return false;}));if(isRetired)this.#retired=true;this.#confirmed=true;this.#notify('known');}
   catch{this.#notify('uncertain');throw new GeoOverviewBinaryUncertainAllocation(this);}
  })().finally(()=>{this.#allocation=undefined;});return this.#allocation;
 }
 recover():Promise<GeoOverviewFrozenBinary>{
  if(this.#closing||this.#closed)return Promise.reject(new Error('Snapshot birth closing'));
  if(!this.#recovery)this.#recovery=(async()=>{
   await this.#allocate();if(this.#retired||this.#closing)throw new Error('Snapshot birth retired or closing');
   if(!this.#owner)this.#owner=new GeoOverviewFrozenBinary(CAP,this,this.#bridge,this.#target!,this.#sequence,this.#header,this.#length);
   await initialize.call(this.#owner);if(this.#closing)throw new Error('Snapshot birth closing');return this.#owner;
  })().catch(cause=>{this.#recovery=undefined;throw cause;});return this.#recovery;
 }
 dispose():Promise<void>{
  this.#closing=true;if(this.#owner)dropViews.call(this.#owner);
  if(this.#closed)return Promise.resolve();
  if(!this.#disposal)this.#disposal=(async()=>{
   await this.#recovery?.catch(()=>{});await this.#allocation?.catch(()=>{});if(this.#owner)dropViews.call(this.#owner);
   if(isGeoWorkerTerminated(this.#worker,this.#sourceBridge)){this.#closed=true;this.#notify('known');return;}
   await this.#allocate();
   if(!this.#retired){
    let disposalError:unknown;
    try{receipt(await this.#bridge.execute(request(3,this.#target!)),0n,0,this.#target);}catch(cause){disposalError=cause;}
    const isRetired=mutationValue(await mutation(this.#bridge,this.#control(0),packet=>retired(packet,this.#sequence)));
    if(!isRetired)throw disposalError??new TypeError('Snapshot retirement not confirmed');
    this.#retired=true;
   }
   mutationValue(await mutation(this.#bridge,this.#control(2),packet=>receipt(packet,this.#sequence,0,0n,true)));
   this.#closed=true;this.#header=new Uint8Array(0);this.#request=new ArrayBuffer(0);this.#notify('known');
  })().catch(cause=>{this.#disposal=undefined;throw cause;});return this.#disposal;
 }
}
/** Bytes are inert application borrows; drop them before dispose ACK. */
export class GeoOverviewFrozenBinary {
 #attempt:GeoOverviewSnapshotAttempt;#bridge:XygGeoScaleBridge;#handle:bigint;#sequence:bigint;#header:Uint8Array|undefined;#length:number;#bytes:Uint8Array|undefined;#read:Promise<void>|undefined;#viewsDropped=false;
 constructor(cap:symbol,attempt:GeoOverviewSnapshotAttempt,bridge:XygGeoScaleBridge,handle:bigint,sequence:bigint,header:Uint8Array,length:number){if(cap!==CAP)throw new TypeError('Issued overview Snapshot required');this.#attempt=attempt;this.#bridge=bridge;this.#handle=handle;this.#sequence=sequence;this.#header=header;this.#length=length;}
 get sequence(){return this.#sequence;}get kind(){return 'xygx-v4' as const;}get closed(){return this.#attempt.closed;}
 get bytes():Readonly<Uint8Array>{if(!this.#bytes||this.closed||this.#viewsDropped)throw new Error('Overview binary unavailable');return this.#bytes;}
 private initialize(){
  if(!this.#read)this.#read=this.#bridge.read(request(20,this.#handle)).then(packet=>{
   if(!(packet instanceof ArrayBuffer)||packet.byteLength!==this.#length||packet.byteLength>MAX_PACKET)throw new TypeError('Snapshot plane length mismatch');
   const bytes=new Uint8Array(packet),expected=expectedPrefix(this.#header!,this.#length);
   for(let i=0;i<PROFILE_BYTES;i++)if(bytes[i]!==expected[i])throw new TypeError('Snapshot metadata differs from accepted overview');
   const scene=new DataView(packet,PROFILE_BYTES);if(scene.getUint32(0,true)!==0x53475958||scene.getUint32(4,true)!==32)throw new TypeError('Snapshot Scene32 mismatch');if(!this.#viewsDropped)this.#bytes=bytes;
  });return this.#read;
 }
 /** @internal Captured lifecycle drops inspection before native retirement. */
 dropViews(){this.#viewsDropped=true;this.#bytes=undefined;}
 dispose(){return attemptDispose.call(this.#attempt);}
}
const initialize=GeoOverviewFrozenBinary.prototype['initialize'],dropViews=GeoOverviewFrozenBinary.prototype.dropViews;
/** Private factory captures complete immutable issuer/request before any dispatch. */
export function beginOverviewBinaryFreeze(worker:XygWasmWorker,bridge:XygGeoScaleBridge,frame:GeoOverviewFrame,input:OverviewBinaryFreezeOptions,onMutation:(state:'known'|'rejected'|'uncertain')=>void){
 const a=overviewFrameAuthority(frame),transport=getGeoWorkerSnapshotTransport(worker,bridge);
 if(!a||a.bridge!==bridge||a.header.byteLength!==2304)throw new TypeError('Snapshot requires accepted issued overview');
 const scene=Number(new DataView(a.header.buffer,a.header.byteOffset).getBigUint64(32,true)),length=PROFILE_BYTES+scene,budget=input.budgetBytes??transport.budgetBytes;
 if(scene<160||scene>MAX_SCENE||!Number.isSafeInteger(budget)||budget<=34304||budget>transport.budgetBytes)throw new RangeError('Overview Snapshot profile/budget exceeded');
 if(input.signal?.aborted){onMutation('rejected');return Promise.reject(aborted());}
 const nonce=(nonces.get(frame)??0n)+1n;if(nonce>0xffffffffffffffffn)throw new RangeError('Snapshot nonce exhausted');nonces.set(frame,nonce);
 const attempt=new GeoOverviewSnapshotAttempt(CAP,worker,bridge,transport.bridge,a.handle,a.sequence,nonce,budget,a.header,length,onMutation);
 return attemptRecover.call(attempt).then(async owner=>{if(input.signal?.aborted){try{await attemptDispose.call(attempt);}catch(cause){throw new GeoOverviewBinaryCleanupPending(attempt,cause);}throw aborted();}return owner;}).catch(async cause=>{
  if(cause instanceof GeoOverviewBinaryUncertainAllocation)throw cause;
  if(!attempt.closed){try{await attemptDispose.call(attempt);}catch(cleanup){throw new GeoOverviewBinaryCleanupPending(attempt,cleanup);}}
  throw cause;
 });
}
/** Canonical dispatch cannot be replaced through application decorations. */
const binaryDispose=GeoOverviewFrozenBinary.prototype.dispose,attemptDispose=GeoOverviewSnapshotAttempt.prototype.dispose,attemptRecover=GeoOverviewSnapshotAttempt.prototype.recover;
export function disposeOverviewBinary(owner:GeoOverviewFrozenBinary|GeoOverviewSnapshotAttempt){return owner instanceof GeoOverviewFrozenBinary?binaryDispose.call(owner):attemptDispose.call(owner);}
