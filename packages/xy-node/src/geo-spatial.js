/** Native spatial-index owner. Rust owns indexing, temporal and LOD policy. */
import { RetainedGeoSource, attachRetainedFrame } from './geo-retained.js';
import { encodeGeoScaleRequest as encode, decodeGeoScaleReply as decode,
  driveGeoIndexSession, prepareGeoSceneData } from './geoscale.js';

export class GeoSpatialFullScanRequired extends Error {
  constructor(reasonCode) { super(`Rust requires explicit canonical full-source scan (${reasonCode===1?'frontier limit':'leaf work budget'})`); this.name='GeoSpatialFullScanRequired';this.reasonCode=reasonCode; }
}
export class GeoSpatialIndex extends RetainedGeoSource {
  static async _fromFrame(frame, source, {grid, maxVertices, readPage, writePage, signal}) {
    void frame.data;
    if (typeof readPage !== 'function' || typeof writePage !== 'function') throw new TypeError('explicit readPage/writePage required');
    if (!Number.isInteger(grid) || grid<0 || grid>0xffffffff || typeof maxVertices!=='bigint' || maxVertices<0n || maxVertices>=1n<<64n) throw new TypeError('exact u32 grid/u64 maxVertices required');
    const self = new GeoSpatialIndex();
    self.bridge=source.bridge; self.budget={...source.budget};self.readChunk=source.readChunk;
    self.readPage=readPage;self.writePage=writePage;
    const identity=frame.data.identity;
    self.info={generation:identity.generation,digest:identity.sourceDigest.slice(),rows:identity.sourceRows,geometry:identity.geometry,crs:identity.sourceCrs};
    self.originSource=source.originSource??source;
    self.closed=false;self.sequence=0n;
    const payload=new Uint8Array(16), v=new DataView(payload.buffer);
    v.setUint32(0,grid,true);v.setBigUint64(8,maxVertices,true);
    const sequence=frame.data.identity.sequence;
    return self._run(async ownSignal=>{
      const abort=()=>self.abort?.abort();signal?.addEventListener('abort',abort,{once:true});
      try {
        if(signal?.aborted)abort(); if(ownSignal.aborted)throw new Error('operation aborted');
        const r=decode(await self.bridge.execute(encode({command:17,handle:frame.handle,sequence,budget:self.budget,payload})));
        self.handle=r.handle;
        if(ownSignal.aborted)throw new Error('operation aborted');
        const result=await driveGeoIndexSession(self.bridge,{handle:self.handle,sequence,budget:self.budget,readChunk:self.readChunk,readPage,writePage,signal:ownSignal});
        if(ownSignal.aborted)throw new Error('operation aborted');
        if(result.code!==11)throw new Error('index build did not complete');
        self.pageCount=result.dataLength;
        return self;
      }catch(error){
        if(self.handle!==undefined)await self.bridge.execute(encode({command:10,handle:self.handle}));
        self.closed=true;throw error;
      }finally{signal?.removeEventListener('abort',abort);}
    });
  }
  update(query,{sequence,style,signal}) {
    if(!(style instanceof Uint8Array)||style.length!==48)throw new TypeError('style must be exact48 bytes');
    const request=encode({command:18,handle:this.handle,sequence,budget:this.budget,query});
    const queryPacket=request.slice(0);style=style.slice();
    return this._run(async ownSignal=>{
      const abort=()=>this.abort?.abort();signal?.addEventListener('abort',abort,{once:true});
      let handle,frame;
      try{
        if(signal?.aborted)abort();if(ownSignal.aborted)throw new Error('operation aborted');
        const r=decode(await this.bridge.execute(request));
        if(r.code===10)throw new GeoSpatialFullScanRequired(r.fallbackReasonCode);
        if(r.code!==0)throw new Error('invalid indexed query creation');
        handle=r.handle;this.sequence=sequence;
        if(ownSignal.aborted)throw new Error('operation aborted');
        const result=await driveGeoIndexSession(this.bridge,{handle,sequence,budget:this.budget,readChunk:this.readChunk,readPage:this.readPage,writePage:this.writePage,signal:ownSignal});
        if(result.code!==12)throw new Error('indexed query did not complete');
        frame=await prepareGeoSceneData(this.bridge,{command:19,handle,sequence,budget:this.budget,style});
        if(ownSignal.aborted)throw new Error('operation aborted');
        attachRetainedFrame(this,frame,sequence,queryPacket,style);
        frame.indexStats=result.indexStats;
      }catch(error){if(frame)await frame.dispose();throw error;}
      finally{
        try{
          if(handle!==undefined)await this.bridge.execute(encode({command:10,handle}));
          if(ownSignal.aborted){if(frame)await frame.dispose();throw new Error('operation aborted');}
        }catch(error){if(frame)await frame.dispose();throw error;}
        finally{signal?.removeEventListener('abort',abort);}
      }
      this.current=frame;return frame;
    });
  }
  cancel(){
    this.abort?.abort();
    return this.active?this.active.then(()=>{},()=>{}):Promise.resolve();
  }
}
