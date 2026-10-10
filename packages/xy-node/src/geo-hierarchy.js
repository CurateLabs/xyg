/** Import-only hierarchy owner; external storage remains explicitly caller-owned. */
import {forgetSelectedGeoAllocationIssuer} from './geo-allocation-attempt.js';
import {RetainedGeoSource,attachRetainedFrame,retainedFrameAuthority} from './geo-retained.js';
import {encodeGeoHierarchyRequest as encode,decodeGeoHierarchyReply as decode,driveGeoHierarchy,prepareGeoHierarchyScene,beginGeoSelectedHierarchy,captureGeoHierarchyTransport,GeoHierarchyUnsupportedSelected} from './geo-hierarchy-wire.js';
export {GeoHierarchyFallback,GeoHierarchyUnsupportedSelected,GeoHierarchyPublicationUncertain,GeoSelectedHierarchyOperation} from './geo-hierarchy-wire.js';
const frames=new WeakSet();
const laneAuthorities=new WeakMap();
export function hierarchyLaneAuthority(lane){return laneAuthorities.get(lane);}
export function isHierarchyFrame(frame){return frames.has(frame);}
export class GeoHierarchy extends RetainedGeoSource {
 #owner;#creation;#origin;#storage;#budget;#bridge;#transport;#transportToken;#selected=false;#pending;#disposed=false;#cancelGeneration=0n;
 static fromFrame(frame,source,options){return GeoHierarchy.#build(frame,source,options,false);}
 static fromSelectedFrame(frame,source,options){return GeoHierarchy.#build(frame,source,options,true);}
 static async #build(frame,source,{grid,maxVertices,maxWriteBytes,readPage,writePage,signal},selected) {
  void frame.data;
  const authority=retainedFrameAuthority(frame);if(!authority||authority.source!==source||authority.bridge!==source.bridge)throw new TypeError('frame belongs to another source or transport');
  if(!selected&&frame.data.selection!==null)throw new GeoHierarchyUnsupportedSelected();
  if(selected&&frame.data.selection===null)throw new TypeError('selected hierarchy requires authentic selected frame');
  if(typeof readPage!=='function'||typeof writePage!=='function')throw new TypeError('explicit immutable page storage required');
  if(!Number.isInteger(grid)||grid<0||grid>0xffffffff)throw new TypeError('u32 grid required');
  for(const n of[maxVertices,maxWriteBytes])if(typeof n!=='bigint'||n<=0n||n>0xffffffffffffffffn)throw new TypeError('nonzero u64 work/write limits required');
  const self=new GeoHierarchy();self.#selected=selected;self.#bridge=source.bridge;self.#transport=Object.freeze({execute:self.#bridge.execute.bind(self.#bridge),read:self.#bridge.read.bind(self.#bridge)});self.#transportToken=captureGeoHierarchyTransport(self.#bridge);self.#budget={...source.budget};self.budget={...self.#budget};self.#origin=source.originSource??source;self.#storage=Object.freeze({readChunk:source.readChunk,readPage,writePage});self.closed=false;self.sequence=0n;
  self.info={...source.info,digest:source.info.digest.slice()};
  const payload=new Uint8Array(24),v=new DataView(payload.buffer);v.setUint32(0,grid,true);v.setBigUint64(8,maxVertices,true);v.setBigUint64(16,maxWriteBytes,true);
  const sequence=frame.data.identity.sequence;self.#creation=sequence;
  return self._run(async ownSignal=>{
   const abort=()=>self.abort?.abort();signal?.addEventListener('abort',abort,{once:true});
   try{if(signal?.aborted)abort();if(ownSignal.aborted)throw new Error('operation aborted');
    const r=decode(await self.#transport.execute(encode({command:37,handle:frame.handle,sequence,budget:self.#budget,payload})));
    if(r.code===17)throw new GeoHierarchyUnsupportedSelected();if(r.code!==0||r.sequence!==sequence)throw new TypeError('invalid hierarchy creation');self.#owner=r.handle;
    if(ownSignal.aborted)throw new Error('operation aborted');const result=await driveGeoHierarchy(self.#transport,{handle:self.#owner,sequence,budget:self.#budget,...self.#storage,signal:ownSignal});
    if(ownSignal.aborted)throw new Error('operation aborted');if(result.code!==18)throw new Error('hierarchy build did not complete');laneAuthorities.set(self,Object.freeze({source:self.#origin,bridge:self.#bridge,creationSequence:self.#creation,selected:self.#selected}));return self;
   }catch(error){if(self.#owner!==undefined)await self.#transport.execute(encode({command:10,handle:self.#owner,sequence}));self.closed=true;throw error;}
   finally{signal?.removeEventListener('abort',abort);}
  });
 }
 get handle(){return this.#owner;}
 get cancelGeneration(){return this.#cancelGeneration;}
 get selected(){return this.#selected;}get pendingOperation(){return this.#pending;}
 async fork(){
  if(this.closed||this.disposing||this.active)throw new Error('hierarchy owner unavailable');
  const reply=decode(await this.#transport.execute(encode({command:42,handle:this.#owner,sequence:this.#creation,budget:this.#budget})));
  if(reply.code!==0||reply.sequence!==this.#creation)throw new TypeError('invalid hierarchy fork');
  const lane=new GeoHierarchy();lane.#owner=reply.handle;lane.#creation=this.#creation;lane.#origin=this.#origin;lane.#storage=this.#storage;lane.#budget={...this.#budget};lane.#bridge=this.#bridge;lane.#transport=this.#transport;lane.#transportToken=this.#transportToken;lane.#selected=this.#selected;lane.budget={...this.#budget};lane.info={...this.info,digest:this.info.digest.slice()};lane.closed=false;lane.sequence=0n;laneAuthorities.set(lane,Object.freeze({source:lane.#origin,bridge:lane.#bridge,creationSequence:lane.#creation,selected:lane.#selected}));return lane;
 }
 #beginSelected(state,query,sequence){
  if(!this.#selected)throw new GeoHierarchyUnsupportedSelected();if(this.#pending)throw new Error('selected hierarchy operation still owned');
  let issued;return beginGeoSelectedHierarchy(this.#bridge,{state,handle:this.#owner,sequence,query,budget:this.#budget,storage:this.#storage,transportToken:this.#transportToken,
   onIssued:operation=>{this.#pending=issued=operation;},onReleased:()=>{this.#pending=undefined;},onPrepared:(frame,style)=>{const operation=issued;attachRetainedFrame(this.#origin,frame,sequence,operation.request,style,frame=>frames.add(frame));frame.hierarchyStats=operation.hierarchyStats;this.current=frame;}}).then(operation=>{this.sequence=sequence;return operation;});
 }
 beginSelected(state,query,{sequence}){return this._run(async signal=>{if(signal.aborted)throw new Error('operation aborted');return this.#beginSelected(state,query,sequence);});}
 updateSelected(state,query,{sequence,style,signal}){
  if(!(style instanceof Uint8Array)||style.byteLength!==48||style.buffer.byteLength>48)throw new TypeError('exact style required');style=style.slice();
  return this._run(async ownSignal=>{const stop=()=>this.abort?.abort();signal?.addEventListener('abort',stop,{once:true});let operation,frame;
   try{if(signal?.aborted)stop();if(ownSignal.aborted)throw new Error('operation aborted');operation=await this.#beginSelected(state,query,sequence);
    await operation.drive({signal:ownSignal});frame=await operation.prepare(style,{signal:ownSignal});if(ownSignal.aborted)throw new Error('operation aborted');
    return frame;
   }catch(error){if(frame)await frame.dispose();throw error;}finally{try{if(operation)await operation.dispose();}finally{signal?.removeEventListener('abort',stop);}}
  });
 }

 get bridge(){return this.#bridge;}
 update(query,{sequence,style,signal}) {
  if(this.#selected)throw new GeoHierarchyUnsupportedSelected();
  if(!(style instanceof Uint8Array)||style.byteLength!==48||style.buffer.byteLength>48)throw new TypeError('exact style required');style=style.slice();
  const request=encode({command:38,handle:this.#owner,sequence,budget:this.#budget,query});
  const attachment=request.slice(0);
  return this._run(async ownSignal=>{
   const abort=()=>this.abort?.abort();signal?.addEventListener('abort',abort,{once:true});let handle,frame;
   try{if(signal?.aborted)abort();if(ownSignal.aborted)throw new Error('operation aborted');
    const r=decode(await this.#transport.execute(request));if(r.code!==0||r.sequence!==sequence)throw new TypeError('invalid hierarchy query creation');handle=r.handle;this.sequence=sequence;
    if(ownSignal.aborted)throw new Error('operation aborted');const complete=await driveGeoHierarchy(this.#transport,{handle,sequence,budget:this.#budget,...this.#storage,signal:ownSignal});if(complete.code!==19)throw new Error('hierarchy query did not complete');
    frame=await prepareGeoHierarchyScene(this.#transport,{handle,sequence,budget:this.#budget,style});if(ownSignal.aborted)throw new Error('operation aborted');
    attachRetainedFrame(this.#origin,frame,sequence,attachment,style,frame=>frames.add(frame));frame.hierarchyStats=complete.hierarchyStats;
   }catch(error){if(frame)await frame.dispose();throw error;}
   finally{try{if(handle!==undefined)await this.#transport.execute(encode({command:10,handle,sequence}));if(ownSignal.aborted){if(frame)await frame.dispose();throw new Error('operation aborted');}}catch(error){if(frame)await frame.dispose();throw error;}finally{signal?.removeEventListener('abort',abort);}}
   this.current=frame;return frame;
  });
 }
 cancel(){this.#cancelGeneration++;this.abort?.abort();if(this.#pending)return this.#pending.cancel();return this.active?this.active.then(()=>{},()=>{}):Promise.resolve();}
 dispose(){this.#cancelGeneration++;if(this.closed)return Promise.resolve();if(this.disposing)return this.disposing;const task=(async()=>{this.abort?.abort();if(this.active)try{await this.active;}catch{}if(this.#pending)await this.#pending.dispose();if(this.#owner!==undefined&&!this.#disposed){const reply=decode(await this.#transport.execute(encode({command:10,handle:this.#owner,sequence:this.#creation})));if(reply.code!==0||reply.handle!==this.#owner||reply.sequence!==this.#creation)throw new TypeError('Hierarchy disposal receipt');this.#disposed=true;}if(this.#owner!==undefined)await forgetSelectedGeoAllocationIssuer(this.#bridge,this.#owner);this.closed=true;})();this.disposing=task;task.catch(()=>{if(this.disposing===task)this.disposing=undefined;});return task;}
}
