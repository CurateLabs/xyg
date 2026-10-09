/** Import-only hierarchy owner; external storage remains explicitly caller-owned. */
import {RetainedGeoSource,attachRetainedFrame,retainedFrameAuthority} from './geo-retained.js';
import {encodeGeoHierarchyRequest as encode,decodeGeoHierarchyReply as decode,driveGeoHierarchy,prepareGeoHierarchyScene,GeoHierarchyUnsupportedSelected} from './geo-hierarchy-wire.js';
export {GeoHierarchyFallback,GeoHierarchyUnsupportedSelected} from './geo-hierarchy-wire.js';
const frames=new WeakSet();
export function isHierarchyFrame(frame){return frames.has(frame);}
export class GeoHierarchy extends RetainedGeoSource {
 #owner;#creation;#origin;#storage;#budget;#bridge;
 static async fromFrame(frame,source,{grid,maxVertices,maxWriteBytes,readPage,writePage,signal}) {
  void frame.data;
  const authority=retainedFrameAuthority(frame);if(!authority||authority.source!==source||authority.bridge!==source.bridge)throw new TypeError('frame belongs to another source or transport');
  if(frame.data.selection!==null)throw new GeoHierarchyUnsupportedSelected();
  if(typeof readPage!=='function'||typeof writePage!=='function')throw new TypeError('explicit immutable page storage required');
  if(!Number.isInteger(grid)||grid<0||grid>0xffffffff)throw new TypeError('u32 grid required');
  for(const n of[maxVertices,maxWriteBytes])if(typeof n!=='bigint'||n<=0n||n>0xffffffffffffffffn)throw new TypeError('nonzero u64 work/write limits required');
  const self=new GeoHierarchy();self.#bridge=source.bridge;self.#budget={...source.budget};self.budget={...self.#budget};self.#origin=source.originSource??source;self.#storage={readChunk:source.readChunk,readPage,writePage};self.closed=false;self.sequence=0n;
  self.info={...source.info,digest:source.info.digest.slice()};
  const payload=new Uint8Array(24),v=new DataView(payload.buffer);v.setUint32(0,grid,true);v.setBigUint64(8,maxVertices,true);v.setBigUint64(16,maxWriteBytes,true);
  const sequence=frame.data.identity.sequence;self.#creation=sequence;
  return self._run(async ownSignal=>{
   const abort=()=>self.abort?.abort();signal?.addEventListener('abort',abort,{once:true});
   try{if(signal?.aborted)abort();if(ownSignal.aborted)throw new Error('operation aborted');
    const r=decode(await self.#bridge.execute(encode({command:37,handle:frame.handle,sequence,budget:self.#budget,payload})));
    if(r.code===17)throw new GeoHierarchyUnsupportedSelected();if(r.code!==0||r.sequence!==sequence)throw new TypeError('invalid hierarchy creation');self.#owner=r.handle;
    if(ownSignal.aborted)throw new Error('operation aborted');const result=await driveGeoHierarchy(self.#bridge,{handle:self.#owner,sequence,budget:self.#budget,...self.#storage,signal:ownSignal});
    if(ownSignal.aborted)throw new Error('operation aborted');if(result.code!==18)throw new Error('hierarchy build did not complete');return self;
   }catch(error){if(self.#owner!==undefined)await self.#bridge.execute(encode({command:10,handle:self.#owner,sequence}));self.closed=true;throw error;}
   finally{signal?.removeEventListener('abort',abort);}
  });
 }
 get handle(){return this.#owner;}
 get bridge(){return this.#bridge;}
 update(query,{sequence,style,signal}) {
  if(!(style instanceof Uint8Array)||style.byteLength!==48||style.buffer.byteLength>48)throw new TypeError('exact style required');style=style.slice();
  const request=encode({command:38,handle:this.#owner,sequence,budget:this.#budget,query});
  const attachment=request.slice(0);
  return this._run(async ownSignal=>{
   const abort=()=>this.abort?.abort();signal?.addEventListener('abort',abort,{once:true});let handle,frame;
   try{if(signal?.aborted)abort();if(ownSignal.aborted)throw new Error('operation aborted');
    const r=decode(await this.#bridge.execute(request));if(r.code!==0||r.sequence!==sequence)throw new TypeError('invalid hierarchy query creation');handle=r.handle;this.sequence=sequence;
    if(ownSignal.aborted)throw new Error('operation aborted');const complete=await driveGeoHierarchy(this.#bridge,{handle,sequence,budget:this.#budget,...this.#storage,signal:ownSignal});if(complete.code!==19)throw new Error('hierarchy query did not complete');
    frame=await prepareGeoHierarchyScene(this.#bridge,{handle,sequence,budget:this.#budget,style});if(ownSignal.aborted)throw new Error('operation aborted');
    attachRetainedFrame(this.#origin,frame,sequence,attachment,style,frame=>frames.add(frame));frame.hierarchyStats=complete.hierarchyStats;
   }catch(error){if(frame)await frame.dispose();throw error;}
   finally{try{if(handle!==undefined)await this.#bridge.execute(encode({command:10,handle,sequence}));if(ownSignal.aborted){if(frame)await frame.dispose();throw new Error('operation aborted');}}catch(error){if(frame)await frame.dispose();throw error;}finally{signal?.removeEventListener('abort',abort);}}
   this.current=frame;return frame;
  });
 }
 cancel(){this.abort?.abort();return this.active?this.active.then(()=>{},()=>{}):Promise.resolve();}
 dispose(){if(this.closed)return Promise.resolve();if(this.disposing)return this.disposing;const task=(async()=>{this.abort?.abort();if(this.active)try{await this.active;}catch{}if(this.#owner!==undefined)await this.#bridge.execute(encode({command:10,handle:this.#owner,sequence:this.#creation}));this.closed=true;})();this.disposing=task;task.catch(()=>{if(this.disposing===task)this.disposing=undefined;});return task;}
}
