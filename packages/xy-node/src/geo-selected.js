/** Explicit selected-state owners. Geometry, joining and count policy stay in Rust. */
import {encodeGeoScaleRequest,decodeGeoScaleReply,driveGeoSession,driveGeoIndexSession,prepareGeoSceneData} from './geoscale.js';


const AUTHORITY=Symbol('selected-owner');
const stateAuthorities=new WeakMap                                                                                         ();
function u64(n       ){if(typeof n!=='bigint'||n<0n||n>0xffffffffffffffffn)throw new TypeError('expected u64 bigint');return n;}
function words(values         ){const p=new Uint8Array(values.length*8),v=new DataView(p.buffer);values.forEach((n,i)=>v.setBigUint64(i*8,u64(n),true));return p;}
async function execute(bridge                  ,request            ){return decodeGeoScaleReply(await bridge.execute(request));}
function owned(bridge                  ,handle       ){let live=true,disposing                        ;return {
 handle,get live(){return live;},check(){if(!live||disposing)throw new Error('selected owner unavailable');},consume(){live=false;},
 dispose(){if(!live)return Promise.resolve();return disposing??=execute(bridge,encodeGeoScaleRequest({command:10,handle})).then(()=>{live=false;},error=>{disposing=undefined;throw error;});}
};}
export async function createGeoSelectedScope(bridge                  ,input                                                                                              ){
 const request=encodeGeoScaleRequest({command:32,handle:input.frameHandle,sequence:input.sequence,budget:input.budget,payload:words([input.namespace,input.layerId])});
 const result=await execute(bridge,request);return new GeoSelectedScope(bridge,result.handle,AUTHORITY);
}
export class GeoSelectedScope {
         owner                         ;
         bridge                  ;
 constructor(bridge                  ,handle       ,token                 ){if(token!==AUTHORITY)throw new TypeError('issued selected authority required');this.bridge=bridge;this.owner=owned(bridge,handle);}
 get handle(){return this.owner.handle;}
 dispose(){return this.owner.dispose();}
 async state(input                                                                              ){
  this.owner.check();if(!(input.ids instanceof BigUint64Array)||input.ids.length>10000||!(input.fill instanceof Uint8Array)||input.fill.length!==4)throw new TypeError('exact selected typed planes required');
  if(!Number.isSafeInteger(input.budget.processorBytes)||input.budget.processorBytes<256||input.budget.processorBytes>128*1024*1024||280+input.ids.length*8>input.budget.processorBytes)throw new RangeError('selected framing exceeds budget');
  const p=new Uint8Array(24+input.ids.length*8),v=new DataView(p.buffer);v.setBigUint64(0,u64(input.revision),true);p.set(input.fill,8);v.setBigUint64(16,BigInt(input.ids.length),true);for(let i=0;i<input.ids.length;i++)v.setBigUint64(24+i*8,input.ids[i],true);
  const result=await execute(this.bridge,encodeGeoScaleRequest({command:33,handle:this.handle,budget:input.budget,payload:p}));return new GeoSelectedState(this.bridge,result.handle,this,AUTHORITY);
 }
 async link(state                 ,input                                           ){
  this.owner.check();state.check();if(!state.belongsTo(this.bridge))throw new TypeError('selected State belongs to another transport');const request=encodeGeoScaleRequest({command:34,handle:this.handle,budget:input.budget,payload:words([state.handle,input.revision])});
  const result=await execute(this.bridge,request);return new GeoSelectedState(this.bridge,result.handle,this,AUTHORITY);
 }
}
export class GeoSelectedState {
         owner                         ;
         bridge                  ;         scope                 ;
 constructor(bridge                  ,handle       ,scope                 ,token                 ){if(token!==AUTHORITY)throw new TypeError('issued selected authority required');this.bridge=bridge;this.scope=scope;this.owner=owned(bridge,handle);stateAuthorities.set(this,{bridge,owner:this.owner,busy:false});}
 get handle(){return this.owner.handle;}
 check(){const authority=stateAuthorities.get(this);if(!authority||authority.busy)throw new Error('selected State already active');authority.owner.check();}
 belongsTo(bridge                  ){return this.bridge===bridge;}
 dispose(){if(stateAuthorities.get(this)?.busy)return Promise.reject(new Error('selected State already active'));return this.owner.dispose();}
 async begin(input                                                                                              ){
  this.check();const {command,handle,sequence}=input,budget={...input.budget};const request=encodeGeoScaleRequest({...input,budget,payload:words([this.handle])}),result=await execute(this.bridge,request);
  if(result.code===10)return {fallback:true         ,reason:result.fallbackReasonCode,state:this                    };
  if(result.code!==0||result.sequence!==sequence||result.handle!==(command===35?handle:this.handle))throw new TypeError('selected begin ownership reply');
  this.owner.consume();return {fallback:false         ,operation:new GeoSelectedOperation(this.bridge,result.handle,sequence,command===36,budget,this.scope,AUTHORITY)};
 }
}
export class GeoSelectedOperation {
         replaced=false;
         bridge                  ;         handle       ;         sequence       ;         indexed        ;         budget                  ;         scope                 ;
 constructor(bridge                  ,handle       ,sequence       ,indexed        ,budget                  ,scope                 ,token                 ){if(token!==AUTHORITY)throw new TypeError('issued selected authority required');this.bridge=bridge;this.handle=handle;this.sequence=sequence;this.indexed=indexed;this.budget={...budget};this.scope=scope;}
 async drive(input                                                                                                                                                                                                         ){
  if(this.replaced)throw new Error('selected query replaced');
  if(this.indexed)return driveGeoIndexSession(this.bridge,{...input,handle:this.handle,sequence:this.sequence,budget:this.budget});
  if(!input.readChunk)throw new TypeError('canonical selected query requires explicit reader');
  return driveGeoSession(this.bridge,{...input,readChunk:input.readChunk,handle:this.handle,sequence:this.sequence,budget:this.budget});
 }
 async prepare(style           ){
  if(this.replaced)throw new Error('selected query replaced');
  const bridge=this.indexed?{read:(r            )=>this.bridge.read(r),execute:async(r            )=>{const reply=await this.bridge.execute(r);if(new DataView(r).getUint32(8,true)===19){const parsed=decodeGeoScaleReply(reply);if(parsed.handle===this.handle&&parsed.sequence===this.sequence)this.replaced=true;}return reply;}}:this.bridge;
  const frame=await prepareGeoSceneData(bridge,{command:this.indexed?19:11,handle:this.handle,sequence:this.sequence,budget:this.budget,style});
  if(this.indexed)this.replaced=true;return frame;
 }
 async cancel(){if(this.replaced)throw new Error('selected query replaced');await execute(this.bridge,encodeGeoScaleRequest({command:9,handle:this.handle,sequence:this.sequence}));}
 async dispose(){if(!this.indexed)throw new Error('canonical SourceSession remains caller-owned');if(!this.replaced){await execute(this.bridge,encodeGeoScaleRequest({command:10,handle:this.handle}));this.replaced=true;}}
}

/** Internal issued capability: captures original owner/transport, never public wire fields. */
export function claimGeoSelectedState(state                 ,bridge                  ){
 const authority=stateAuthorities.get(state);
 if(!authority||authority.bridge!==bridge)throw new TypeError('issued selected State belongs to another transport');
 authority.owner.check();if(authority.busy)throw new Error('selected State already active');authority.busy=true;
 let settled=false;
 return {handle:authority.owner.handle,
  reject(){if(!settled){settled=true;authority.busy=false;}},
  consume(){if(!settled){settled=true;authority.busy=false;authority.owner.consume();}}
 };
}
