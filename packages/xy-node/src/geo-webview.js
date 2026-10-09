/** Native one-mount geographic host facade. No browser imports or source serialization. */
import {sceneBrowserPainter} from './scene.js';
import {RetainedGeoSource} from './geo-retained.js';
import {encodeGeoScaleRequest,prepareGeoSceneData,geoScaleExecute} from './geoscale.js';
function buffer(value){
 if(value instanceof ArrayBuffer)return value;
 if(ArrayBuffer.isView(value)&&value.byteOffset===0&&value.byteLength===value.buffer.byteLength)return value.buffer;
 throw new TypeError('exact binary host attachment required');
}
function tag(op,owner=0n,sequence=0n){const b=new ArrayBuffer(32),v=new DataView(b);new Uint8Array(b).set([88,89,71,72]);v.setUint32(4,1,true);v.setUint32(8,op,true);v.setBigUint64(16,owner,true);v.setBigUint64(24,sequence,true);return b;}
function same(a,b){a=new Uint8Array(a);b=new Uint8Array(b);return a.length===b.length&&a.every((n,i)=>n===b[i]);}
export class GeoHostAdapter {
 constructor(chart,{frame}={}){
  const layer=chart._retained();if(!layer||chart.tileSession||(!(layer.source instanceof RetainedGeoSource)||(!frame&&layer.source.constructor!==RetainedGeoSource)))throw new TypeError('native host requires one canonical RetainedGeoSource; indexed hosts are pending');
  if(layer.source.bridge.execute!==geoScaleExecute)throw new TypeError('native geographic host requires the native source bridge');
  const {query,sequence,style}=chart._inputs(layer);
  this.source=layer.source;this.query={...query,camera:{...query.camera},time:{...query.time},sourceDigest:query.sourceDigest.slice()};this.sequence=sequence;this.style=style.slice();this.budget=chart.budget;
  this.chain=Promise.resolve();this.queued=0;this.closing=false;
  if(frame){
   const expected=encodeGeoScaleRequest({command:5,sequence,budget:this.source.budget,query:this.query}),actual=frame._queryPacket?.slice(0);
   if(!actual)throw new TypeError('explicit frame lacks trusted query authority');
   new Uint8Array(actual).set(new Uint8Array(expected,8,4),8);
   new Uint8Array(actual).set(new Uint8Array(expected,16,8),16);
   const packet=frame.data.packet,pv=new DataView(packet),ev=new DataView(expected),info=this.source.info;
   const identityMatches=packet.byteLength>=256&&pv.getBigUint64(24,true)===sequence&&pv.getUint32(80,true)===ev.getUint32(64,true)&&pv.getUint32(84,true)===ev.getUint32(12,true)&&same(new Uint8Array(packet,88,120),new Uint8Array(expected,80,120))&&pv.getUint32(208,true)===ev.getUint32(200,true)&&pv.getUint32(212,true)===ev.getUint32(68,true)&&same(new Uint8Array(packet,216,16),new Uint8Array(expected,208,16))&&same(info.digest,new Uint8Array(packet,144,8))&&info.generation===pv.getBigUint64(152,true)&&info.rows===pv.getBigUint64(232,true)&&info.geometry===pv.getUint32(240,true)&&info.crs===pv.getUint32(244,true);
   if(frame._source!==this.source||!identityMatches||!same(actual,expected)||!same(frame._style,this.style))throw new TypeError('explicit frame does not match this geographic composition');
   this.anchorReady=frame.retain().then(async owned=>{if(this.closing)await owned.dispose();else this.anchor=owned;});
   // Ready retains void; construction starts ownership transfer before caller disposal.
   this.anchorReady.catch(()=>{});
  }else this.anchorReady=Promise.resolve();
 }
 get mounted(){return this.mount!==undefined;}
 async open(mount){
  await this.anchorReady;
  if(this.closing||this.mounted)throw new Error('geographic host admits one mount; release before reopening');
  const {query,sequence,style,source}=this;
  const queryPacket=encodeGeoScaleRequest({command:5,handle:source.handle,sequence,budget:source.budget,query});
  let frame;
  if(this.anchor)frame=this.anchor;
  else if(source.current&&source.sequence===sequence){
   if(!same(source.current._queryPacket,queryPacket)||!same(source.current._style,style))throw new Error('published query differs from geographic composition');
   frame=await prepareGeoSceneData(source.bridge,{handle:source.handle,sequence,budget:source.budget,style});
   frame._source=source;frame._style=style.slice();frame._queryPacket=queryPacket;
   frame.pick=options=>source.pick({...options,sequence,_owner:frame.handle});
   frame.membership=(cell,options)=>source.membership(cell,{...options,sequence,_owner:frame.handle});
  }else frame=await source.update(query,{sequence,style});
  try{
   if(this.closing)throw new Error('geographic host authoring disposed');
   const painter=sceneBrowserPainter(frame.data.scene,this.budget);
   if(2*frame.data.packet.byteLength+painter.byteLength>source.budget.processorBytes)throw new RangeError('geographic host exceeds transfer budget');
   this.frame=frame;this.painter=buffer(painter);this.mount=mount;
   return [tag(1,frame.handle,sequence),frame.data.packet,this.painter];
  }catch(error){if(frame!==this.anchor)await frame.dispose();throw error;}
 }
 handle(message,buffers){
  if(message?.type!=='geo_host'||typeof message.request!=='string'||message.request.length<1||message.request.length>96)return Promise.resolve(undefined);
  if(this.queued>=16)return Promise.resolve([{type:'geo_host',request:message.request,error:'native geographic host queue is full'},[]]);
  // Small requests are copied only after bounded queue admission.
  let request;
  try{const attachments=buffers??(message.buffer?[message.buffer]:[]);if(attachments.length!==1)throw new TypeError('one binary request required');const raw=buffer(attachments[0]);if(raw.byteLength<32||raw.byteLength>256)throw new TypeError('invalid request length');request=raw.slice(0);}catch(error){return Promise.resolve([{type:'geo_host',request:message.request,error:error.message},[]]);}
  const mount=message.mount,id=message.request;this.queued++;
  const operation=this.chain.then(async()=>{
   const reply={type:'geo_host',request:id};
   try{
    if(typeof mount!=='string'||mount.length<1||mount.length>96)throw new TypeError('invalid mount identity');
    const v=new DataView(request),op=v.getUint32(8,true),owner=v.getBigUint64(16,true),sequence=v.getBigUint64(24,true);
    if(v.getUint32(0,true)!==0x48475958||v.getUint32(4,true)!==1||v.getUint32(12,true)||![1,2,3,4,5].includes(op))throw new TypeError('invalid host request');
    let out=[];
    if(op===1){if(request.byteLength!==32||owner||sequence)throw new TypeError('invalid open');out=await this.open(mount);}
    else{
     if(mount!==this.mount||!this.frame||sequence!==this.frame.data.identity.sequence)throw new Error('unowned or stale geographic frame');
     if(op===5){if(request.byteLength!==32||!this.aux||this.aux.handle!==owner)throw new Error('unowned auxiliary release');const aux=this.aux;this.aux=undefined;await aux.dispose();}
     else{
      if(owner!==this.frame.handle)throw new Error('unowned geographic frame');
      if(op===4){if(request.byteLength!==32||this.aux)throw new Error('release auxiliary packets first');await this.release();}
      else if(op===2){if(request.byteLength!==64||this.aux)throw new Error('invalid or concurrent pick');this.aux=await this.frame.pick({style:this.frame._style,x:v.getFloat64(32,true),y:v.getFloat64(40,true),tolerance:v.getFloat64(48,true),mode:v.getUint32(56,true),maxHits:v.getUint32(60,true)});out=[tag(op,this.aux.handle,sequence),this.aux.data.packet];}
      else{if(![48,256].includes(request.byteLength)||this.aux||v.getUint32(36,true)!==Number(request.byteLength===256))throw new Error('invalid or concurrent membership');if(v.getBigUint64(40,true)>new DataView(this.frame._queryPacket).getBigUint64(224,true))throw new Error("membership exceeds committed frame work bound");this.aux=await this.frame.membership(v.getUint32(32,true),{maxProjectedVertices:v.getBigUint64(40,true),cursor:request.byteLength===256?new Uint8Array(request.slice(48)):undefined});out=[tag(op,this.aux.handle,sequence),this.aux.data.packet];}
     }
    }
    return [reply,out];
   }catch(error){return [{...reply,error:error.message},[]];}
   finally{request=undefined;}
  });
  this.chain=operation.then(()=>{},()=>{}).finally(()=>{this.queued--;});return operation;
 }
 async release(){this.painter=undefined;const frame=this.frame;this.frame=undefined;this.mount=undefined;if(frame&&frame!==this.anchor)await frame.dispose();if(this.closing)await this.releaseAnchor();}
 async releaseAnchor(){const anchor=this.anchor;this.anchor=undefined;if(anchor)await anchor.dispose();}
 close(){this.closing=true;this.source=this.query=this.style=undefined;this.cleanup=this.anchorReady.then(()=>this.mounted?undefined:this.releaseAnchor());this.cleanup.catch(()=>{});}
 /** Only a real disposed renderer realm may substitute for a browser release ACK. */
 async realmDestroyed(){this.close();await this.chain;const aux=this.aux;this.aux=undefined;if(aux)await aux.dispose();await this.release();await this.cleanup;}
}

/** Extension-host helper. Caller supplies CSP/resource-local HTML; VS Code >=1.57. */
export function attachGeoWebview(panel,adapter){
 let stopped=false,releaseWaiters=[],transport=Promise.resolve(),queued=0;
 const receive=panel.webview.onDidReceiveMessage(envelope=>{
  if(stopped||envelope?.message?.type!=="geo_host")return;
  if(queued>=16){void panel.webview.postMessage({message:{type:"geo_host",request:envelope.message.request,error:"geographic webview queue is full"},buffers:[]});return;}
  try{if(envelope.buffers?.length!==1||buffer(envelope.buffers[0]).byteLength>256)throw Error("invalid geographic request attachment");}
  catch(error){void panel.webview.postMessage({message:{type:"geo_host",request:envelope.message.request,error:error.message},buffers:[]});return;}
  queued++;
  const operation=transport.then(async()=>{
   let reply;
   try{
    reply=await adapter.handle(envelope.message,envelope.buffers);envelope=undefined;
    if(reply){await panel.webview.postMessage({message:reply[0],buffers:reply[1]});reply=undefined;if(!adapter.mounted){for(const resolve of releaseWaiters)resolve();releaseWaiters=[];}}
   }finally{reply=envelope=undefined;}
  });
  transport=operation.then(()=>{},()=>{}).finally(()=>{queued--;});
 });
 const disposed=panel.onDidDispose(()=>{stopped=true;receive.dispose();disposed.dispose();void transport.then(()=>adapter.realmDestroyed());for(const resolve of releaseWaiters)resolve();releaseWaiters=[];});
 async function release(){if(!adapter.mounted)return;const wait=new Promise(resolve=>releaseWaiters.push(resolve));await panel.webview.postMessage({message:{type:'geo_host_close'},buffers:[]});await wait;}
 return {async reload(html){await release();panel.webview.html=html;},async dispose(){await release();panel.dispose();},get mounted(){return adapter.mounted;}};
}
