// Mechanical type stripping of shared private allocation recovery.
/** Private exact-request allocation recovery (§27/§29); no geometric policy. */
import {encodeGeoScaleRequest} from './geoscale.js';

const issuers=new WeakMap                                                                              ();
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
 #receipt                      ;#confirmed=false;#retired=false;#rejected=false;#uncertain=false;#active                                         ;#released=false;#slot                                                          ;
 constructor(owner       ,transport                  ,request            ,operationSequence        ){
  if(!(request instanceof ArrayBuffer)||request.byteLength<256||request.byteLength>280)throw new TypeError('Bounded allocation request required');
  const v=new DataView(request),command=v.getUint32(8,true);if(![26,27,28,29,45].includes(command)||v.getBigUint64(240,true)!==0n)throw new TypeError('Canonical allocation request required');
  let commands=issuers.get(owner);if(!commands){commands=new Map();issuers.set(owner,commands);}let slot=commands.get(command);if(!slot){slot={nonce:0n,dead:false};commands.set(command,slot);}
  if(slot.dead)throw new Error('Allocation issuer disposed');
  if(slot.attempt&&!slot.attempt.settled)throw new Error('Previous allocation confirmation remains pending');
  if(slot.nonce===0xffffffffffffffffn)throw new RangeError('Allocation nonce exhausted');
  this.#transport=Object.freeze({execute:transport.execute.bind(transport),read:transport.read.bind(transport)});this.#command=command;this.#issuer=v.getBigUint64(16,true);this.#sequence=operationSequence??v.getBigUint64(24,true);this.#nonce=slot.nonce+1n;this.#request=request.slice(0);new DataView(this.#request).setBigUint64(240,this.#nonce,true);this.#slot=slot;slot.nonce=this.#nonce;slot.attempt=this;
 }
 get settled(){return this.#rejected||this.#confirmed&&(!this.#retired||this.#released);}get retired(){return this.#retired;}get rejected(){return this.#rejected;}
 recover(validate                             )                               {
  if(this.#rejected)return Promise.resolve(undefined);if(this.#retired&&this.#confirmed)return this.release().then(()=>undefined);if(this.#active)return this.#active;
  return this.#active=Promise.resolve().then(async()=>{try{
   const packet=this.#receipt??await this.#transport.execute(this.#request.slice(0));
   if(packet instanceof ArrayBuffer&&packet.byteLength===256&&new DataView(packet).getUint32(8,true)===22){terminal(packet,this.#sequence);this.#retired=true;}
   else{const target=validate(packet);if(target===0n||this.#target!==0n&&this.#target!==target)throw new TypeError('Allocation target changed');this.#target=target;this.#receipt=packet.slice(0);}
   const ack=await this.#transport.execute(this.#ack(0));const code=terminal(ack,this.#sequence,this.#target);if(code===22)this.#retired=true;this.#confirmed=true;if(this.#retired){await this.release();return undefined;}return packet;
  }catch(error){if(!this.#uncertain&&this.#target===0n&&!this.#retired&&rejection(error))this.#rejected=true;else this.#uncertain=true;throw error;}finally{this.#active=undefined;}});
 }
 #ack(action       ){const payload=new Uint8Array(16),v=new DataView(payload.buffer);v.setUint32(0,this.#command,true);v.setUint32(4,action,true);v.setBigUint64(8,this.#target,true);const request=encodeGeoScaleRequest({command:6,handle:this.#issuer,sequence:this.#sequence,payload});const h=new DataView(request);h.setUint32(8,47,true);h.setBigUint64(240,this.#nonce,true);return request;}
 async probeRetirement(validate                             ){if(this.#confirmed&&this.#target!==0n){const code=terminal(await this.#transport.execute(this.#ack(0)),this.#sequence,this.#target);if(code===22){this.#retired=true;return undefined;}return this.#receipt;}this.#receipt=undefined;return this.recover(validate);}
 async release(){if(!this.#released&&!this.#rejected){if(!this.#confirmed)throw new Error('Allocation confirmation unsettled');const packet=await this.#transport.execute(this.#ack(2));if(terminal(packet,this.#sequence,0n)!==0)throw new TypeError('Release acknowledgement must be successful');this.#released=true;}if(this.#slot.dead)await this.forget();}
 async forget(){if(!this.#released)return;if(this.#rejected||this.#slot.nonce!==this.#nonce)return;if(!this.#confirmed)throw new Error('Unconfirmed allocation cannot be forgotten');const packet=await this.#transport.execute(this.#ack(1));if(!(packet instanceof ArrayBuffer)||packet.byteLength!==256)throw new TypeError('Fixed Forget acknowledgement required');const b=new Uint8Array(packet),v=new DataView(packet);if(v.getUint32(0,true)!==0x5a475958||v.getUint32(4,true)!==1||v.getUint32(8,true)!==0||v.getUint32(12,true)||v.getBigUint64(16,true)!==0n||v.getBigUint64(24,true)!==this.#sequence||b.subarray(32).some(x=>x))throw new TypeError('Forget acknowledgement mismatch');this.#slot.attempt=undefined;}
}
/** Called only after the genuine issuer's confirmed disposal, never public fields. */
export async function forgetGeoAllocationIssuer(owner       ){const commands=issuers.get(owner);if(!commands)return;for(const slot of commands.values()){slot.dead=true;if(slot.attempt)await slot.attempt.forget();}}
