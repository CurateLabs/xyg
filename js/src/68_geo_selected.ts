/** Explicit selected-state owners. Geometry, joining and count policy stay in Rust. */
import {encodeGeoScaleRequest,decodeGeoScaleReply,driveGeoSession,driveGeoIndexSession,prepareGeoSceneData} from './63_geo_source';
import {withGeoWorkerMutationOutcome} from './47_wasm';
import {GeoAllocationAttempt,selectedGeoAllocationIssuer,trackSelectedGeoAllocation,preflightSelectedGeoAllocation,forgetSelectedGeoAllocationIssuer} from './72_geo_allocation_attempt';
import type {XygGeoScaleBridge,XygGeoQueryBudget,XygGeoScaleQuery,XygGeoReadTicket} from './63_geo_source';

const AUTHORITY=Symbol('selected-owner');
const scopeAuthorities=new WeakMap<GeoSelectedScope,{bridge:XygGeoScaleBridge;owner:ReturnType<typeof owned>;handle:bigint}>();
const stateAuthorities=new WeakMap<GeoSelectedState,{bridge:XygGeoScaleBridge;owner:ReturnType<typeof owned>;busy:boolean;scope:GeoSelectedScope;mutation?:GeoSelectedMutationAttempt}>();
const scopeMutationIssuers=new WeakMap<GeoSelectedScope,Map<bigint,XygGeoScaleBridge>>();
function u64(n:bigint){if(typeof n!=='bigint'||n<0n||n>0xffffffffffffffffn)throw new TypeError('expected u64 bigint');return n;}
function words(values:bigint[]){const p=new Uint8Array(values.length*8),v=new DataView(p.buffer);values.forEach((n,i)=>v.setBigUint64(i*8,u64(n),true));return p;}
async function execute(bridge:XygGeoScaleBridge,request:ArrayBuffer){return decodeGeoScaleReply(await bridge.execute(request));}
function owned(bridge:XygGeoScaleBridge,handle:bigint){let live=true,disposing:Promise<void>|undefined;return {
 handle,get live(){return live;},check(){if(!live||disposing)throw new Error('selected owner unavailable');},consume(){live=false;},
 dispose(){if(!live)return Promise.resolve();return disposing??=execute(bridge,encodeGeoScaleRequest({command:10,handle})).then(()=>{live=false;},error=>{disposing=undefined;throw error;});}
};}
export async function createGeoSelectedScope(bridge:XygGeoScaleBridge,input:{frameHandle:bigint;sequence:bigint;namespace:bigint;layerId:bigint;budget:XygGeoQueryBudget}){
 const request=encodeGeoScaleRequest({command:32,handle:input.frameHandle,sequence:input.sequence,budget:input.budget,payload:words([input.namespace,input.layerId])});
 const result=await execute(bridge,request);return new GeoSelectedScope(bridge,result.handle,AUTHORITY);
}
function stateRequest(handle:bigint,input:{revision:bigint;ids:BigUint64Array;fill:Uint8Array;budget:XygGeoQueryBudget},nonce:bigint){
 if(!(input.ids instanceof BigUint64Array)||input.ids.length>10000||!(input.fill instanceof Uint8Array)||input.fill.length!==4)throw new TypeError('exact selected typed planes required');
 if(!Number.isSafeInteger(input.budget.processorBytes)||input.budget.processorBytes<256||input.budget.processorBytes>128*1024*1024||280+input.ids.length*8>input.budget.processorBytes)throw new RangeError('selected framing exceeds budget');
 const p=new Uint8Array(24+input.ids.length*8),v=new DataView(p.buffer);v.setBigUint64(0,u64(input.revision),true);p.set(input.fill,8);v.setBigUint64(16,BigInt(input.ids.length),true);for(let i=0;i<input.ids.length;i++)v.setBigUint64(24+i*8,input.ids[i],true);
 const request=encodeGeoScaleRequest({command:33,handle,budget:input.budget,payload:p});new DataView(request).setBigUint64(24,nonce,true);return request;
}
/** Retains an immutable allocation request before dispatch; recovery never issues a new nonce. */
export class GeoSelectedStateAttempt {
 #scope:GeoSelectedScope;#bridge:XygGeoScaleBridge;#request:ArrayBuffer;#revision:bigint;
 #state:GeoSelectedState|undefined;#active:Promise<GeoSelectedState|undefined>|undefined;#cleanup:Promise<void>|undefined;#closed=false;#uncertain=false;
 constructor(scope:GeoSelectedScope,bridge:XygGeoScaleBridge,request:ArrayBuffer,revision:bigint,token:typeof AUTHORITY){if(token!==AUTHORITY)throw new TypeError('issued attempt required');this.#scope=scope;this.#bridge=bridge;this.#request=request;this.#revision=revision;}
 async recover(){if(this.#closed||this.#cleanup)throw new Error('state attempt unavailable');const state=await this.#issue();if(!state)throw new Error('state nonce retired');return state;}
 #issue(){if(this.#state&&!stateAuthorities.get(this.#state)?.owner.live){this.#closed=true;this.#request=new ArrayBuffer(0);return Promise.resolve(undefined);}return this.#active??=Promise.resolve().then(async()=>{try{
  const raw=await this.#bridge.execute(this.#request.slice(0)),b=new Uint8Array(raw),v=new DataView(raw);
  if(b.length!==256||v.getUint32(0,true)!==0x5a475958||v.getUint32(4,true)!==1||![0,20].includes(v.getUint32(8,true))||v.getUint32(12,true)||v.getBigUint64(24,true)!==this.#revision||b.subarray(32).some(x=>x))throw new TypeError('state ownership reply');
  const handle=v.getBigUint64(16,true);if(v.getUint32(8,true)===20){if(handle!==0n)throw new TypeError('retired state handle');const authority=this.#state&&stateAuthorities.get(this.#state);if(authority?.busy)throw new Error('selected State operation unsettled');authority?.owner.consume();this.#closed=true;this.#request=new ArrayBuffer(0);return undefined;}
  if(handle===0n||this.#state&&this.#state.handle!==handle)throw new TypeError('state ownership handle');return this.#state??=new GeoSelectedState(this.#bridge,handle,this.#scope,AUTHORITY);
 }catch(error){const e=error as {nativeCode?:unknown;wasmStatus?:unknown;name?:string;status?:unknown};if(!this.#uncertain&&!this.#state&&([-9,-10,-13].includes(e?.nativeCode as number)||e?.wasmStatus===3||e?.name==='XygWasmError'&&e.status===3)){this.#closed=true;this.#request=new ArrayBuffer(0);}else this.#uncertain=true;throw error;
 }finally{this.#active=undefined;}});}
 dispose(){if(this.#closed)return Promise.resolve();return this.#cleanup??=Promise.resolve().then(async()=>{try{const state=await this.#issue();if(state)await state.dispose();this.#closed=true;this.#request=new ArrayBuffer(0);}finally{this.#cleanup=undefined;}});}
}

export class GeoSelectedScope {
 private owner:ReturnType<typeof owned>;
 private bridge:XygGeoScaleBridge;
 #nonce=0n;
 constructor(bridge:XygGeoScaleBridge,handle:bigint,token:typeof AUTHORITY){if(token!==AUTHORITY)throw new TypeError('issued selected authority required');this.bridge=bridge;this.owner=owned(bridge,handle);scopeAuthorities.set(this,{bridge,owner:this.owner,handle});}
 get handle(){return this.owner.handle;}
 async dispose(){await this.owner.dispose();const tracked=scopeMutationIssuers.get(this);if(tracked)for(const [handle,bridge]of tracked){try{await forgetSelectedGeoAllocationIssuer(bridge,handle);}catch{/*Live original issuer stays charged; Scope never disposes it.*/}}}
 beginState(input:{revision:bigint;ids:BigUint64Array;fill:Uint8Array;budget:XygGeoQueryBudget},{nonce}:{nonce?:bigint}={}){
  const issuer=scopeAuthorities.get(this);if(!issuer||issuer.bridge!==this.bridge||issuer.owner!==this.owner||issuer.handle!==this.handle)throw new TypeError('Scope producer changed');issuer.owner.check();const next=u64(nonce??this.#nonce+1n);if(next===0n||next<=this.#nonce)throw new RangeError('state nonce must advance');
  const request=stateRequest(issuer.handle,input,next);this.#nonce=next;
  return new GeoSelectedStateAttempt(this,issuer.bridge,request,input.revision,AUTHORITY);
 }
 async state(input:{revision:bigint;ids:BigUint64Array;fill:Uint8Array;budget:XygGeoQueryBudget}){
  this.owner.check();const result=await execute(this.bridge,stateRequest(this.handle,input,0n));return new GeoSelectedState(this.bridge,result.handle,this,AUTHORITY);
 }
 async link(state:GeoSelectedState,input:{revision:bigint;budget:XygGeoQueryBudget}){
  this.owner.check();state.check();if(!state.belongsTo(this.bridge))throw new TypeError('selected State belongs to another transport');const request=encodeGeoScaleRequest({command:34,handle:this.handle,budget:input.budget,payload:words([state.handle,input.revision])});
  const result=await execute(this.bridge,request);return new GeoSelectedState(this.bridge,result.handle,this,AUTHORITY);
 }
}
export class GeoSelectedState {
 private owner:ReturnType<typeof owned>;
 private bridge:XygGeoScaleBridge;readonly scope:GeoSelectedScope;
 constructor(bridge:XygGeoScaleBridge,handle:bigint,scope:GeoSelectedScope,token:typeof AUTHORITY,mutation?:GeoSelectedMutationAttempt){if(token!==AUTHORITY)throw new TypeError('issued selected authority required');this.bridge=bridge;this.scope=scope;this.owner=owned(bridge,handle);stateAuthorities.set(this,{bridge,owner:this.owner,busy:false,scope});}
 get handle(){return this.owner.handle;}
 check(){const authority=stateAuthorities.get(this);if(!authority||authority.busy)throw new Error('selected State already active');authority.owner.check();}
 belongsTo(bridge:XygGeoScaleBridge){return stateAuthorities.get(this)?.bridge===bridge;}
 dispose(){if(stateAuthorities.get(this)?.busy)return Promise.reject(new Error('selected State already active'));return this.owner.dispose();}
 get pendingOperation(){return stateAuthorities.get(this)?.mutation;}
 async begin(input:{command:35|36;handle:bigint;sequence:bigint;query:XygGeoScaleQuery;budget:XygGeoQueryBudget}){
  const attempt=new GeoSelectedMutationAttempt(this,input,AUTHORITY);return attempt.recover();
 }

}
type SelectedMutationResult={fallback:true;reason:number;state:GeoSelectedState}|{fallback:false;operation:GeoSelectedOperation}|undefined;
export class GeoSelectedMutationAttempt {
 #state:WeakRef<GeoSelectedState>;#bridge:XygGeoScaleBridge;#transport:XygGeoScaleBridge;#attempt:GeoAllocationAttempt;#claim:ReturnType<typeof claimGeoSelectedState>;
 #scope:GeoSelectedScope;#issuer:bigint;#handle:bigint;#sequence:bigint;#indexed:boolean;#budget:XygGeoQueryBudget;#operation:GeoSelectedOperation|undefined;#active:Promise<SelectedMutationResult>|undefined;#cleanup:Promise<void>|undefined;#closed=false;
 constructor(state:GeoSelectedState,input:{command:35|36;handle:bigint;sequence:bigint;query:XygGeoScaleQuery;budget:XygGeoQueryBudget},token:typeof AUTHORITY){
  if(token!==AUTHORITY)throw new TypeError('Issued selected mutation required');const issued=stateAuthorities.get(state);if(!issued)throw new TypeError('Issued State required');
  if(![35,36].includes(input.command))throw new TypeError('Selected mutation command required');this.#issuer=u64(input.handle);this.#state=new WeakRef(state);this.#bridge=issued.bridge;this.#scope=issued.scope;this.#sequence=u64(input.sequence);this.#indexed=input.command===36;this.#handle=this.#indexed?issued.owner.handle:u64(input.handle);this.#budget={processorBytes:input.budget.processorBytes,maxRowsExamined:input.budget.maxRowsExamined,maxReadBytes:input.budget.maxReadBytes,maxChunks:input.budget.maxChunks,pageRows:input.budget.pageRows};
  const request=encodeGeoScaleRequest({command:input.command,handle:input.handle,sequence:this.#sequence,query:input.query,budget:this.#budget,payload:words([issued.owner.handle])});
  let tracked=scopeMutationIssuers.get(this.#scope);if(!tracked){tracked=new Map();scopeMutationIssuers.set(this.#scope,tracked);}if(tracked.size>=16&&!tracked.has(input.handle))throw new RangeError('Scope issuer tracking capacity exhausted');
  const issuer=selectedGeoAllocationIssuer(this.#bridge,input.handle);preflightSelectedGeoAllocation(issuer);this.#transport=Object.freeze({execute:this.#bridge.execute.bind(this.#bridge),read:this.#bridge.read.bind(this.#bridge)});
  this.#claim=claimGeoSelectedState(state,this.#bridge);
  try{this.#attempt=new GeoAllocationAttempt(issuer,this.#transport,request,undefined,(r,run)=>withGeoWorkerMutationOutcome(this.#bridge,r,run));trackSelectedGeoAllocation(issuer,this.#attempt);}
  catch(error){this.#claim.reject();throw error;}
  tracked.set(input.handle,this.#bridge);issued.mutation=this;
 }
 #validate=(packet:ArrayBuffer)=>{if(!(packet instanceof ArrayBuffer)||packet.byteLength!==256)throw new TypeError('Fixed selected mutation receipt required');const b=new Uint8Array(packet),v=new DataView(packet),code=v.getUint32(8,true),handle=v.getBigUint64(16,true);
  if(v.getUint32(0,true)!==0x5a475958||v.getUint32(4,true)!==1||v.getUint32(12,true)||v.getBigUint64(24,true)!==this.#sequence)throw new TypeError('Selected mutation ownership reply');
  if(code===10&&this.#indexed){const issuer=this.#issuer;if(handle!==issuer||b.subarray(32,48).some(x=>x)||b.subarray(52).some(x=>x)||![1,2].includes(v.getUint32(48,true)))throw new TypeError('Selected fallback ownership reply');return 0n;}
  if(code!==0||handle!==this.#handle||b.subarray(32).some(x=>x))throw new TypeError('Selected mutation ownership reply');return handle;
 };
 #accepted(packet:ArrayBuffer|undefined):SelectedMutationResult{
  if(!packet){if(this.#attempt.rejected)this.#claim.reject();else this.#claim.consume();this.#closed=true;return undefined;}
  const v=new DataView(packet);if(v.getUint32(8,true)===10){this.#claim.reject();this.#closed=true;return {fallback:true as const,reason:v.getUint32(48,true),state:this.#state.deref()!};}
  this.#claim.consume();return {fallback:false as const,operation:this.#operation??=new GeoSelectedOperation(this.#transport,this.#handle,this.#sequence,this.#indexed,this.#budget,this.#scope,AUTHORITY,this)};
 }
 recover(){if(this.#operation?.publicationPending)return Promise.reject(new Error('Selected19 publication remains uncertain; guard retained'));if(this.#closed||this.#cleanup)return Promise.reject(new Error('Selected mutation unavailable'));return this.#active??=Promise.resolve().then(async()=>{try{return this.#accepted(await this.#attempt.recover(this.#validate));}catch(error){if(this.#attempt.rejected){this.#claim.reject();this.#closed=true;}throw error;}finally{this.#active=undefined;}});}
 async retire(){if(this.#operation?.publicationPending)throw new Error('Selected19 publication remains uncertain; guard retained');if(await this.#attempt.probeRetirement(this.#validate)===undefined){await this.#attempt.release();return true;}return false;}
 dispose(){if(this.#operation?.publicationPending)return Promise.reject(new Error('Selected19 publication remains uncertain; guard retained'));if(this.#closed)return Promise.resolve();return this.#cleanup??=Promise.resolve().then(async()=>{try{if(this.#active)await this.#active;const accepted=this.#accepted(await this.#attempt.recover(this.#validate));if(!accepted||!('operation' in accepted))return;const op=accepted.operation;if(op.publicationPending)throw new Error('Selected19 publication remains uncertain; guard retained');if(!await this.retire()){await op.settleDrive();await op.cancel();if(this.#indexed)await op.dispose();if(!await this.retire())throw new Error('Selected mutation retirement pending');}this.#closed=true;}finally{this.#cleanup=undefined;}});}
}

export class GeoSelectedOperation {
 #replaced=false;#publicationPending=false;#mutation:GeoSelectedMutationAttempt|undefined;#active:Promise<unknown>|undefined;#abort:AbortController|undefined;
 get publicationPending(){return this.#publicationPending;}
 async settleDrive(){this.#abort?.abort();if(this.#active)try{await this.#active;}catch{/*Driver has settled callback+ACK before rejecting.*/}}
 #bridge:XygGeoScaleBridge;#handle:bigint;#sequence:bigint;#indexed:boolean;#budget:XygGeoQueryBudget;#scope:GeoSelectedScope;
 get handle(){return this.#handle;}get sequence(){return this.#sequence;}get indexed(){return this.#indexed;}get budget(){return {...this.#budget};}get scope(){return this.#scope;}
 constructor(bridge:XygGeoScaleBridge,handle:bigint,sequence:bigint,indexed:boolean,budget:XygGeoQueryBudget,scope:GeoSelectedScope,token:typeof AUTHORITY,mutation?:GeoSelectedMutationAttempt){if(token!==AUTHORITY)throw new TypeError('issued selected authority required');this.#bridge=Object.freeze({execute:bridge.execute.bind(bridge),read:bridge.read.bind(bridge)});this.#handle=handle;this.#sequence=sequence;this.#indexed=indexed;this.#budget=Object.freeze({...budget});this.#scope=scope;this.#mutation=mutation;}
 drive(input:{readChunk?:(ticket:XygGeoReadTicket,signal?:AbortSignal)=>Promise<ArrayBuffer|Uint8Array>;readPage?:(ticket:XygGeoReadTicket,signal?:AbortSignal)=>Promise<ArrayBuffer|Uint8Array>;signal?:AbortSignal}){
  if(this.#publicationPending)throw new Error('Selected19 publication remains uncertain; guard retained');if(this.#replaced||this.#active)throw new Error('Selected query replaced or active');
  const controller=new AbortController(),abort=()=>controller.abort();this.#abort=controller;input.signal?.addEventListener('abort',abort,{once:true});if(input.signal?.aborted)abort();
  return this.#active=Promise.resolve().then(async()=>{try{if(this.#indexed)return await driveGeoIndexSession(this.#bridge,{...input,signal:controller.signal,handle:this.#handle,sequence:this.#sequence,budget:this.#budget});if(!input.readChunk)throw new TypeError('Canonical selected query requires explicit reader');return await driveGeoSession(this.#bridge,{...input,readChunk:input.readChunk,signal:controller.signal,handle:this.#handle,sequence:this.#sequence,budget:this.#budget});}finally{input.signal?.removeEventListener('abort',abort);this.#active=undefined;this.#abort=undefined;}});
 }
 async prepare(style:Uint8Array){
  if(this.#publicationPending)throw new Error('Selected19 publication remains uncertain; guard retained');if(this.#replaced||this.#active)throw new Error('Selected query replaced or active');
  if(this.#indexed)this.#publicationPending=true;
  const bridge=this.#indexed?{read:(r:ArrayBuffer)=>this.#bridge.read(r),execute:async(r:ArrayBuffer)=>{const command=new DataView(r).getUint32(8,true);const reply=await this.#bridge.execute(r);if(command===19){const parsed=decodeGeoScaleReply(reply);if(parsed.handle===this.#handle&&parsed.sequence===this.#sequence)this.#replaced=true;}return reply;}}:this.#bridge;
  const frame=await prepareGeoSceneData(bridge,{command:this.#indexed?19:11,handle:this.#handle,sequence:this.#sequence,budget:this.#budget,style});
  if(this.#indexed)this.#replaced=true;this.#publicationPending=false;if(this.#indexed)await this.#mutation?.retire();return frame;
 }
 async cancel(){if(this.#publicationPending)throw new Error('Selected19 publication remains uncertain; guard retained');if(this.#active)throw new Error('Selected read/ACK settlement pending');if(this.#replaced)throw new Error('selected query replaced');await execute(this.#bridge,encodeGeoScaleRequest({command:9,handle:this.#handle,sequence:this.#sequence}));await this.#mutation?.retire();}
 async dispose(){if(this.#publicationPending)throw new Error('Selected19 publication remains uncertain; guard retained');await this.settleDrive();if(!this.#indexed)throw new Error('canonical SourceSession remains caller-owned');if(!this.#replaced){await execute(this.#bridge,encodeGeoScaleRequest({command:10,handle:this.#handle}));this.#replaced=true;await this.#mutation?.retire();}}
}

/** Internal issued capability: captures original owner/transport, never public wire fields. */
export function claimGeoSelectedState(state:GeoSelectedState,bridge:XygGeoScaleBridge){
 const authority=stateAuthorities.get(state);
 if(!authority||authority.bridge!==bridge)throw new TypeError('issued selected State belongs to another transport');
 authority.owner.check();if(authority.busy)throw new Error('selected State already active');authority.busy=true;
 let settled=false;
 return {handle:authority.owner.handle,
  reject(){if(!settled){settled=true;authority.busy=false;}},
  consume(){if(!settled){settled=true;authority.busy=false;authority.owner.consume();}}
 };
}
