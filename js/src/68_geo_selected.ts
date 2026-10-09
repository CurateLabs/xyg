/** Explicit selected-state owners. Geometry, joining and count policy stay in Rust. */
import {encodeGeoScaleRequest,decodeGeoScaleReply,driveGeoSession,driveGeoIndexSession,prepareGeoSceneData} from './63_geo_source';
import type {XygGeoScaleBridge,XygGeoQueryBudget,XygGeoScaleQuery,XygGeoReadTicket} from './63_geo_source';

const AUTHORITY=Symbol('selected-owner');
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
export class GeoSelectedScope {
 private owner:ReturnType<typeof owned>;
 private bridge:XygGeoScaleBridge;
 constructor(bridge:XygGeoScaleBridge,handle:bigint,token:typeof AUTHORITY){if(token!==AUTHORITY)throw new TypeError('issued selected authority required');this.bridge=bridge;this.owner=owned(bridge,handle);}
 get handle(){return this.owner.handle;}
 dispose(){return this.owner.dispose();}
 async state(input:{revision:bigint;ids:BigUint64Array;fill:Uint8Array;budget:XygGeoQueryBudget}){
  this.owner.check();if(!(input.ids instanceof BigUint64Array)||input.ids.length>10000||!(input.fill instanceof Uint8Array)||input.fill.length!==4)throw new TypeError('exact selected typed planes required');
  if(!Number.isSafeInteger(input.budget.processorBytes)||input.budget.processorBytes<256||input.budget.processorBytes>128*1024*1024||280+input.ids.length*8>input.budget.processorBytes)throw new RangeError('selected framing exceeds budget');
  const p=new Uint8Array(24+input.ids.length*8),v=new DataView(p.buffer);v.setBigUint64(0,u64(input.revision),true);p.set(input.fill,8);v.setBigUint64(16,BigInt(input.ids.length),true);for(let i=0;i<input.ids.length;i++)v.setBigUint64(24+i*8,input.ids[i],true);
  const result=await execute(this.bridge,encodeGeoScaleRequest({command:33,handle:this.handle,budget:input.budget,payload:p}));return new GeoSelectedState(this.bridge,result.handle,this,AUTHORITY);
 }
 async link(state:GeoSelectedState,input:{revision:bigint;budget:XygGeoQueryBudget}){
  this.owner.check();state.check();if(!state.belongsTo(this.bridge))throw new TypeError('selected State belongs to another transport');const request=encodeGeoScaleRequest({command:34,handle:this.handle,budget:input.budget,payload:words([state.handle,input.revision])});
  const result=await execute(this.bridge,request);return new GeoSelectedState(this.bridge,result.handle,this,AUTHORITY);
 }
}
export class GeoSelectedState {
 private owner:ReturnType<typeof owned>;
 private bridge:XygGeoScaleBridge;readonly scope:GeoSelectedScope;
 constructor(bridge:XygGeoScaleBridge,handle:bigint,scope:GeoSelectedScope,token:typeof AUTHORITY){if(token!==AUTHORITY)throw new TypeError('issued selected authority required');this.bridge=bridge;this.scope=scope;this.owner=owned(bridge,handle);}
 get handle(){return this.owner.handle;}
 check(){this.owner.check();}
 belongsTo(bridge:XygGeoScaleBridge){return this.bridge===bridge;}
 dispose(){return this.owner.dispose();}
 async begin(input:{command:35|36;handle:bigint;sequence:bigint;query:XygGeoScaleQuery;budget:XygGeoQueryBudget}){
  this.check();const {command,handle,sequence}=input,budget={...input.budget};const request=encodeGeoScaleRequest({...input,budget,payload:words([this.handle])}),result=await execute(this.bridge,request);
  if(result.code===10)return {fallback:true as const,reason:result.fallbackReasonCode,state:this as GeoSelectedState};
  if(result.code!==0||result.sequence!==sequence||result.handle!==(command===35?handle:this.handle))throw new TypeError('selected begin ownership reply');
  this.owner.consume();return {fallback:false as const,operation:new GeoSelectedOperation(this.bridge,result.handle,sequence,command===36,budget,this.scope,AUTHORITY)};
 }
}
export class GeoSelectedOperation {
 private replaced=false;
 private bridge:XygGeoScaleBridge;readonly handle:bigint;readonly sequence:bigint;readonly indexed:boolean;readonly budget:XygGeoQueryBudget;readonly scope:GeoSelectedScope;
 constructor(bridge:XygGeoScaleBridge,handle:bigint,sequence:bigint,indexed:boolean,budget:XygGeoQueryBudget,scope:GeoSelectedScope,token:typeof AUTHORITY){if(token!==AUTHORITY)throw new TypeError('issued selected authority required');this.bridge=bridge;this.handle=handle;this.sequence=sequence;this.indexed=indexed;this.budget={...budget};this.scope=scope;}
 async drive(input:{readChunk?:(ticket:XygGeoReadTicket,signal?:AbortSignal)=>Promise<ArrayBuffer|Uint8Array>;readPage?:(ticket:XygGeoReadTicket,signal?:AbortSignal)=>Promise<ArrayBuffer|Uint8Array>;signal?:AbortSignal}){
  if(this.replaced)throw new Error('selected query replaced');
  if(this.indexed)return driveGeoIndexSession(this.bridge,{...input,handle:this.handle,sequence:this.sequence,budget:this.budget});
  if(!input.readChunk)throw new TypeError('canonical selected query requires explicit reader');
  return driveGeoSession(this.bridge,{...input,readChunk:input.readChunk,handle:this.handle,sequence:this.sequence,budget:this.budget});
 }
 async prepare(style:Uint8Array){
  if(this.replaced)throw new Error('selected query replaced');
  const bridge=this.indexed?{read:(r:ArrayBuffer)=>this.bridge.read(r),execute:async(r:ArrayBuffer)=>{const reply=await this.bridge.execute(r);if(new DataView(r).getUint32(8,true)===19){const parsed=decodeGeoScaleReply(reply);if(parsed.handle===this.handle&&parsed.sequence===this.sequence)this.replaced=true;}return reply;}}:this.bridge;
  const frame=await prepareGeoSceneData(bridge,{command:this.indexed?19:11,handle:this.handle,sequence:this.sequence,budget:this.budget,style});
  if(this.indexed)this.replaced=true;return frame;
 }
 async cancel(){if(this.replaced)throw new Error('selected query replaced');await execute(this.bridge,encodeGeoScaleRequest({command:9,handle:this.handle,sequence:this.sequence}));}
 async dispose(){if(!this.indexed)throw new Error('canonical SourceSession remains caller-owned');if(!this.replaced){await execute(this.bridge,encodeGeoScaleRequest({command:10,handle:this.handle}));this.replaced=true;}}
}
