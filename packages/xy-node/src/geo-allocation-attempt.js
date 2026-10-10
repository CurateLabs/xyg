// Mechanical type stripping of shared private allocation recovery.
/** Private exact-request allocation recovery (§27/§29); no geometric policy. */
import {encodeGeoScaleRequest} from './geoscale.js';





function selectedPacket(receipt                ,sequence       ){const packet=new ArrayBuffer(256),v=new DataView(packet);v.setUint32(0,0x5a475958,true);v.setUint32(4,1,true);v.setUint32(8,receipt.code,true);v.setBigUint64(16,receipt.handle,true);v.setBigUint64(24,sequence,true);if(receipt.dataLength!==undefined){v.setBigUint64(32,receipt.dataLength,true);v.setBigUint64(40,receipt.sourceHandle ,true);}if(receipt.code===10)v.setUint32(48,receipt.reason ,true);return packet;}
const issuers=new WeakMap                                                                                                                                        ();
function terminal(packet            ,sequence       ,target        ){
 if(!(packet instanceof ArrayBuffer)||packet.byteLength!==256)throw new TypeError('Fixed allocation acknowledgement required');
 const b=new Uint8Array(packet),v=new DataView(packet),code=v.getUint32(8,true),handle=v.getBigUint64(16,true);
 if(v.getUint32(0,true)!==0x5a475958||v.getUint32(4,true)!==1||![0,22].includes(code)||v.getUint32(12,true)||v.getBigUint64(24,true)!==sequence||b.subarray(32).some(x=>x)||code===22&&handle!==0n||code===0&&target!==undefined&&handle!==target)throw new TypeError('Allocation acknowledgement binding mismatch');
 return code;
}
function rejection(error        ){const e=error                                                                           ;return [-9,-10,-13].includes(e?.nativeCode          )||e?.wasmStatus===3||e?.name==='XygWasmError'&&e.status===3;}
/** Constructed before dispatch, kept until its exact ACK/cleanup settles. */
export class GeoAllocationAttempt {
 #transport                  ;#request            ;#command       ;#issuer       ;#sequence       ;#nonce       ;#target=0n;
 #receipt                      ;#confirmed=false;#retired=false;#rejected=false;#uncertain=false;#active                                         ;#released=false;#slot                                                                                                                    ;#outcome                                    ;#fallback                          ;#selectedReceipt                          ;
 constructor(owner       ,transport                  ,request            ,operationSequence        ,outcome                           ){
  if(!(request instanceof ArrayBuffer)||request.byteLength<256||request.byteLength>304)throw new TypeError('Bounded allocation request required');
  const v=new DataView(request),command=v.getUint32(8,true);if(![19,26,27,28,29,35,36,45].includes(command)||v.getBigUint64(240,true)!==0n)throw new TypeError('Canonical allocation request required');
  if([35,36].includes(command)&&(request.byteLength!==264||!outcome))throw new TypeError('Authenticated selected mutation framing required');if(command===19&&(request.byteLength!==304||!outcome))throw new TypeError('Authenticated selected publication framing required');this.#outcome=outcome;
  let commands=issuers.get(owner);if(!commands){commands=new Map();issuers.set(owner,commands);}let slot=commands.get(command);if(!slot){slot={nonce:0n,dead:false};commands.set(command,slot);}
  if(slot.dead)throw new Error('Allocation issuer disposed');
  if(slot.attempt&&!slot.attempt.settled)throw new Error('Previous allocation confirmation remains pending');
  if(slot.nonce===0xffffffffffffffffn)throw new RangeError('Allocation nonce exhausted');
  this.#transport=Object.freeze({execute:transport.execute.bind(transport),read:transport.read.bind(transport)});this.#command=command;this.#issuer=v.getBigUint64(16,true);this.#sequence=operationSequence??v.getBigUint64(24,true);this.#nonce=slot.nonce+1n;this.#request=request.slice(0);new DataView(this.#request).setBigUint64(240,this.#nonce,true);this.#slot=slot;slot.nonce=this.#nonce;slot.attempt=this;
 }
 get request(){return this.#request.slice(0);}
 get settled(){return this.#rejected||!!this.#fallback||this.#confirmed&&(!this.#retired||this.#released);}get nonjournaled(){return !!this.#fallback;}get released(){return this.#released;}get retired(){return this.#retired;}get rejected(){return this.#rejected;}
 recover(validate                             )                               {
  if(this.#fallback)return Promise.resolve(selectedPacket(this.#fallback,this.#sequence));if(this.#rejected)return Promise.resolve(undefined);if(this.#retired&&this.#confirmed)return this.release().then(()=>undefined);if(this.#active)return this.#active;
  return this.#active=Promise.resolve().then(async()=>{if(this.#outcome)return this.#recoverSelected(validate);try{
   const packet=this.#receipt??await this.#call(this.#request);
   if(packet instanceof ArrayBuffer&&packet.byteLength===256&&new DataView(packet).getUint32(8,true)===22){terminal(packet,this.#sequence);this.#retired=true;}
   else{const target=validate(packet);if(target===0n||this.#target!==0n&&this.#target!==target)throw new TypeError('Allocation target changed');this.#target=target;this.#receipt=packet.slice(0);}
   const ack=await this.#call(this.#ack(0));const code=terminal(ack,this.#sequence,this.#target);if(code===22)this.#retired=true;this.#confirmed=true;this.#slot.journalNonce=this.#nonce;this.#slot.journalAttempt=this;if(this.#retired){await this.release();return undefined;}return packet;
  }catch(error){if(!this.#rejected&&!this.#uncertain&&this.#target===0n&&!this.#retired&&!this.#outcome&&rejection(error))this.#rejected=true;else if(!this.#rejected)this.#uncertain=true;throw error;}finally{this.#active=undefined;}});
 }
 async #recoverSelected(validate                             ){try{
  const receipt=this.#selectedReceipt??await this.#authenticatedCall(this.#request,packet=>{
   if(!(packet instanceof ArrayBuffer)||packet.byteLength!==256)throw new TypeError('Fixed selected receipt required');const v=new DataView(packet),code=v.getUint32(8,true);
   if(code===22){terminal(packet,this.#sequence);return Object.freeze({code:22         ,handle:0n});}
   const target=validate(packet);
   if(this.#command===36&&code===10){if(target!==0n)throw new TypeError('Nonjournaled fallback requires no target');return Object.freeze({code:10         ,handle:this.#issuer,reason:v.getUint32(48,true)});}
   if(target===0n||this.#target!==0n&&this.#target!==target)throw new TypeError('Allocation target changed');return Object.freeze({code:0         ,handle:target,...(this.#command===19?{dataLength:v.getBigUint64(32,true),sourceHandle:v.getBigUint64(40,true)}:{})});
  });
  if(receipt.code===10){this.#fallback=receipt;return selectedPacket(receipt,this.#sequence);}
  this.#selectedReceipt=receipt;if(receipt.code===22)this.#retired=true;else this.#target=receipt.handle;
  const code=await this.#authenticatedCall(this.#ack(0),packet=>terminal(packet,this.#sequence,this.#target));if(code===22)this.#retired=true;this.#confirmed=true;this.#slot.journalNonce=this.#nonce;this.#slot.journalAttempt=this;
  if(this.#retired){await this.release();return undefined;}return selectedPacket(receipt,this.#sequence);
 }catch(error){if(!this.#rejected)this.#uncertain=true;throw error;}finally{this.#active=undefined;}}
 async #call(request            ){return this.#transport.execute(request.slice(0));}
 async #authenticatedCall   (request            ,validate                        )           {
  return this.#outcome (request,async outcome=>{try{const returned=await this.#transport.execute(request.slice(0));if(!outcome(returned)?.reply){this.#uncertain=true;throw new TypeError('Selected mutation lacks genuine producer outcome');}return validate(returned);}
  catch(error){const original=outcome(error);if(!this.#uncertain&&this.#target===0n&&!this.#retired&&original&&([-9,-10,-13].includes(original.status          )||original.status===3&&['XYG_WASM_RESOURCE_LIMIT','XYG_GEO_SOURCE_RESOURCE_LIMIT'].includes(original.code??'')||original.status===7&&original.code==='XYG_GEO_SOURCE_STALE'||original.status===1&&['XYG_GEO_SOURCE_INVALID_FRAME','XYG_GEO_SOURCE_INVALID_TIME'].includes(original.code??'')))this.#rejected=true;else this.#uncertain=true;throw error;}});
 }
 #ack(action       ){const payload=new Uint8Array(16),v=new DataView(payload.buffer);v.setUint32(0,this.#command,true);v.setUint32(4,action,true);v.setBigUint64(8,this.#target,true);const request=encodeGeoScaleRequest({command:6,handle:this.#issuer,sequence:this.#sequence,payload});const h=new DataView(request);h.setUint32(8,47,true);h.setBigUint64(240,this.#nonce,true);return request;}
 async probeRetirement(validate                             ){if(this.#confirmed&&this.#target!==0n){const code=this.#outcome?await this.#authenticatedCall(this.#ack(0),packet=>terminal(packet,this.#sequence,this.#target)):terminal(await this.#call(this.#ack(0)),this.#sequence,this.#target);if(code===22){this.#retired=true;return undefined;}return this.#outcome?selectedPacket(this.#selectedReceipt ,this.#sequence):this.#receipt;}this.#receipt=undefined;this.#selectedReceipt=undefined;return this.recover(validate);}
 async release(){if(!this.#released&&!this.#rejected){if(!this.#confirmed)throw new Error('Allocation confirmation unsettled');const code=this.#outcome?await this.#authenticatedCall(this.#ack(2),packet=>terminal(packet,this.#sequence,0n)):terminal(await this.#call(this.#ack(2)),this.#sequence,0n);if(code!==0)throw new TypeError('Release acknowledgement must be successful');this.#released=true;}if(this.#slot.dead)await this.forget();}
 async forget(){if(!this.#released)return;if(this.#rejected||(this.#slot.journalNonce??this.#slot.nonce)!==this.#nonce)return;if(!this.#confirmed)throw new Error('Unconfirmed allocation cannot be forgotten');const check=(packet            )=>{if(terminal(packet,this.#sequence,0n)!==0)throw new TypeError('Forget acknowledgement mismatch');};if(this.#outcome)await this.#authenticatedCall(this.#ack(1),check);else check(await this.#call(this.#ack(1)));this.#slot.attempt=undefined;}

}
/** Called only after the genuine issuer's confirmed disposal, never public fields. */
export async function forgetGeoAllocationIssuer(owner       ){const commands=issuers.get(owner);if(!commands)return;for(const slot of commands.values()){slot.dead=true;const attempt=slot.journalAttempt??slot.attempt;if(attempt)await attempt.forget();}}

const selectedIssuers=new WeakMap                                                                    ();
/** Numeric legacy authoring resolves one bounded token per genuine captured producer/issuer. */
export function selectedGeoAllocationIssuer(bridge                  ,handle       ){
 let bank=selectedIssuers.get(bridge);if(!bank){bank=new Map();selectedIssuers.set(bridge,bank);}let token=bank.get(handle);if(!token){if(bank.size>=16)throw new RangeError('Selected issuer tracking capacity exhausted');token={attempts:new Set()};bank.set(handle,token);}return token;
}
export function preflightSelectedGeoAllocation(token                                               ){
 for(const prior of token.attempts)if(prior.released||prior.rejected||prior.nonjournaled)token.attempts.delete(prior);
 if(token.attempts.size>=16)throw new RangeError('Selected birth tracking capacity exhausted');
}
export function trackSelectedGeoAllocation(token                                               ,attempt                     ){preflightSelectedGeoAllocation(token);token.attempts.add(attempt);}

/** After actual issuer disposal, or a bounded Scope cleanup probe; never sends Source10. */
export async function forgetSelectedGeoAllocationIssuer(bridge                  ,handle       ){
 const bank=selectedIssuers.get(bridge),token=bank?.get(handle);if(!token)return;
 for(const attempt of token.attempts){if(attempt.rejected||attempt.nonjournaled||attempt.released)continue;const packet=await attempt.probeRetirement(raw=>new DataView(raw).getBigUint64(16,true));if(packet!==undefined)return;await attempt.release();}
 const commands=issuers.get(token);if(commands){for(const slot of commands.values()){const attempt=slot.journalAttempt;if(attempt)await attempt.forget();}for(const slot of commands.values())slot.dead=true;}bank .delete(handle);
}
