/** Scheduling and independent native leases; Rust owns every geographic decision. */
import { temporalControllerState, temporalControllerSubscribeState } from './abi.js';
import { RetainedGeoSource } from './geo-retained.js';
const bindings = new WeakMap();
const MAX = 0xffffffffffffffffn;
function copyQuery(query) {
  const value=structuredClone(query);
  // structuredClone preserves SharedArrayBuffer backing; authoring bytes must
  // instead be owned copies, just like the binary native request framing.
  value.sourceDigest=new Uint8Array(query.sourceDigest);
  return value;
}
function copyChart(chart) {
  const layers=chart.layers.map(layer=>{
    const properties=structuredClone(layer.properties);properties.query=copyQuery(layer.properties.query);
    const style=layer.properties.style;
    if(style instanceof Uint8Array)properties.style=new Uint8Array(style);
    else {properties.style.fill=new Uint8Array(style.fill);properties.style.stroke=new Uint8Array(style.stroke);}
    return new layer.constructor(layer.kind,layer.source,layer.layerId,properties);
  });
  return new chart.constructor(layers,{camera:structuredClone(chart.camera),legend:structuredClone(chart.legend),budget:chart.budget,tileSession:chart.tileSession,tileVectorStyles:structuredClone(chart.tileVectorStyles),tileImageId:chart.tileImageId});
}

export class GeoTemporalBinding {
  #frame; #chart; #query; #retiring;
  constructor(chart, handle, mode = 'cursor') {
    if(!['cursor','range'].includes(mode))throw new TypeError('mode must be cursor or range');
    const layer=chart._retained();
    if(!layer || layer.source.constructor!==RetainedGeoSource || chart.tileSession)throw new TypeError('temporal binding requires canonical retained points');
    const {query,sequence}=chart._inputs(layer);
    if(temporalControllerState(handle).disposed)throw Error('controller disposed');
    if(bindings.has(layer.source))throw Error('source already has a temporal binding');
    this.source=layer.source;this.template=copyChart(chart);this.layer=this.template.layers[0];
    this.#query=copyQuery(query);this.sequence=sequence;this.mode=mode;
    this.closed=false;this.generation=0;this.running=Promise.resolve();this.lock=Promise.resolve();
    bindings.set(this.source,this);
    try {
      this.unsubscribe=temporalControllerSubscribeState(handle,state=>this.accept(state));
      this.accept(temporalControllerState(handle));
    } catch(error) {
      this.closed=true;this.unsubscribe?.();
      if(bindings.get(this.source)===this)bindings.delete(this.source);
      throw error;
    }
  }
  accept(state) {
    if(this.closed)return;
    if(state.disposed){this.dispose().catch(()=>{});this.detach();return;}
    const time=this.mode==='cursor'?{kind:1,instant:state.cursor}:{kind:2,start:state.rangeStart,end:state.rangeEnd};
    const old=this.time;
    if(old && old.kind===time.kind && old.instant===time.instant && old.start===time.start && old.end===time.end)return;
    this.time=time;this.#query.time=time;this.#query.timeRevision++;
    this.schedule();
  }
  exclusive(action) {
    const result=this.lock.then(action);
    this.lock=result.catch(()=>{});return result;
  }
  schedule() {
    this.generation++;
    if(this.pumping)return;
    this.pumping=true;
    this.running=this.pump().finally(()=>{this.pumping=false;});
  }
  async pump() {
    while(!this.closed) {
      const generation=this.generation;
      await this.exclusive(async()=>{
        try {
          if(this.#retiring){await this.#retiring.dispose();this.#retiring=undefined;}
          this.sequence++;
          if(this.sequence>MAX || this.#query.timeRevision>MAX || this.#query.cameraRevision>MAX)throw RangeError('geographic revision exhausted');
          const query=structuredClone(this.#query);
          const layer=new this.layer.constructor(this.layer.kind,this.source,this.layer.layerId,{...this.layer.properties,query,sequence:this.sequence});
          const chart=new this.template.constructor([layer],{camera:query.camera,budget:this.template.budget});
          const candidate=await chart.compileRetained({_publish:false});
          if(this.closed || generation!==this.generation){this.#retiring=candidate;await candidate.dispose();this.#retiring=undefined;}
          else {
            const old=this.#frame;this.#frame=candidate;this.#chart=chart;this.error=undefined;
            if(old){this.#retiring=old;await old.dispose();this.#retiring=undefined;}
          }
        }catch(error){this.error=error;}
      });
      if(generation===this.generation)return;
    }
  }
  setCamera(camera) {
    if(this.closed)throw Error('binding disposed');
    this.#query.camera=structuredClone(camera);this.#query.cameraRevision++;this.schedule();
  }
  async whenIdle() { let running;do{running=this.running;await running;}while(running!==this.running); }
  async snapshot() {
    await this.whenIdle();
    return this.exclusive(async()=>{
      if(!this.#frame)throw Error('no accepted temporal frame',{cause:this.error});
      return {chart:copyChart(this.#chart),frame:await this.#frame.retain()};
    });
  }
  detach() {this.closed=true;this.generation++;this.unsubscribe();}
  dispose() {
    return this.disposing??=Promise.resolve().then(async()=>{
      this.detach();await this.whenIdle();
      await this.exclusive(async()=>{if(this.#retiring){await this.#retiring.dispose();this.#retiring=undefined;}if(this.#frame){await this.#frame.dispose();this.#frame=undefined;}bindings.delete(this.source);});
    }).catch(error=>{this.disposing=undefined;throw error;});
  }
}
