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

function startPump(binding) {
  binding.pumping=true;
  binding.running=binding.pump().then(drained=>{
    binding.pumping=false;
    // A notification may arrive after pump() returns but before this reaction.
    // Restart only for a new intent; failures of the same intent are not retried.
    if(!binding.closed && drained!==binding.generation)startPump(binding);
  },error=>{binding.pumping=false;throw error;});
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
    startPump(this);
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
      if(generation===this.generation)return generation;
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

/** Private mounted scheduler. Uses the same source claim as snapshot binding. */
export class MountedGeoTemporalBinding {
  constructor(source,handle,host,mode='cursor') {
    if(!['cursor','range'].includes(mode))throw TypeError('mode must be cursor or range');
    if(source?.constructor!==RetainedGeoSource)throw TypeError('canonical retained source required');
    if(temporalControllerState(handle).disposed)throw Error('controller disposed');
    if(bindings.has(source))throw Error('source already has a temporal binding');
    this.source=source;this.host=host;this.mode=mode;this.generation=0;this.sent=-1;this.serial=0;this.wake();
    bindings.set(source,this);
    try{this.unsubscribe=temporalControllerSubscribeState(handle,state=>this.accept(state));this.accept(temporalControllerState(handle));}
    catch(error){this.unsubscribe?.();bindings.delete(source);throw error;}
  }
  wake(){this.changed?.resolve();let resolve;const promise=new Promise(r=>resolve=r);this.changed={promise,resolve};}
  accept(state){
    if(this.closed)return;
    if(state.disposed){void this.dispose().catch(()=>{});return;}
    const time=this.mode==='cursor'?[1,state.cursor,0n]:[2,state.rangeStart,state.rangeEnd];
    if(this.time&&time.every((x,i)=>x===this.time[i]))return;
    this.time=time;this.generation++;this.schedule();
  }
  schedule(){this.wake();if(!this.scheduled){this.scheduled=true;queueMicrotask(()=>this.pump());}}
  packet(operation){const b=new ArrayBuffer(56),v=new DataView(b);v.setUint32(0,0x54485958,true);v.setUint32(4,1,true);v.setUint32(8,operation,true);if(operation<3){v.setBigInt64(16,this.time[1],true);v.setBigInt64(24,this.time[2],true);v.setBigUint64(32,this.source.sequence,true);v.setBigUint64(40,this.host.adapter.liveCandidate.timeFloor,true);v.setBigUint64(48,this.host.adapter.liveCandidate.cameraFloor,true);}return b;}
  send(operation){
    const {mount,request}=this.active;
    try{return Promise.resolve(this.host.send({type:'geo_host_temporal',mount,request},[this.packet(operation)]));}catch(error){return Promise.reject(error);}
  }
  failed(error){this.error=error;this.blocked=!!this.active;this.wake();}
  pump(){
    this.scheduled=false;
    if(this.active){if((this.closed||this.active.generation!==this.generation)&&!this.active.invalidated){const active=this.active;active.invalidated=true;this.send(3).catch(error=>{if(this.active===active)this.failed(error);});}this.wake();return;}
    if(this.closed||!this.host.mount||this.sent===this.generation){this.wake();return;}
    this.active={mount:this.host.mount,request:`temporal:${++this.host.serial}`,generation:this.generation,invalidated:false};
    this.sent=this.generation;const active=this.active;this.send(this.time[0]).catch(error=>{if(this.active===active)this.failed(error);});this.wake();
  }
  message(message){
    if(!this.active||message.mount!==this.active.mount||message.request!==this.active.request||!['accepted','superseded','failed'].includes(message.status))return;
    if(message.drained!==true){this.failed(Error(message.error??'geographic drain unconfirmed'));return;}
    this.active=undefined;this.blocked=false;this.error=message.status==='failed'?Error(message.error??'geographic update failed'):undefined;this.schedule();
  }
  released(mount){if(this.active?.mount===mount){this.active=undefined;this.blocked=false;}this.sent=-1;this.schedule();}
  async whenIdle(){for(;;){if(this.blocked||!this.active&&!this.scheduled&&(this.closed||this.host.mount&&this.sent===this.generation))return;await this.changed.promise;}}
  detach(){if(!this.closed){this.closed=true;this.unsubscribe();this.schedule();}}
  dispose(){
    if(this.disposing)return this.disposing;
    const retry=this.blocked;this.detach();
    return this.disposing=(async()=>{
      if(retry&&this.active){this.blocked=false;try{await this.send(4);}catch(error){this.failed(error);}}
      await this.whenIdle();if(this.blocked)throw this.error;
      if(bindings.get(this.source)===this)bindings.delete(this.source);
    })().catch(error=>{this.disposing=undefined;throw error;});
  }
}
