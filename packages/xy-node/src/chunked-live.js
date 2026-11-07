/** Transport-only native viewport lifecycle. Rust owns selection and budgets. */
import {pointer,xyChunkedColumnsChart,xyRangeIndices} from './native.js';
import {scatterChart} from './charts.js';

export class ChunkedLiveHost {
  constructor(source, chart, options, send) {
    this.source=source;this.chart=chart;this.initial=chart;this.options=options;this.send=send;
    this.generation=options.generation;this.mount=null;this.pending=null;this.active=null;
    this.mountEpoch=0n;this.closed=false;this.staged=null;this.frame=String(options.generation);
  }
  drop(chart){if(chart&&chart!==this.initial)chart.dispose();}
  payload() {
    const {spec,buffers}=this.initial.buildPayload({split:true});
    spec.chunked={frame:String(this.options.generation)};
    spec.interaction={...spec.interaction,_transport_view_change:true};
    return {spec,buffers};
  }
  message(msg) {
    if(this.closed)return;
    if(msg.type==='chunked_mount') {
      if(typeof msg.mount!=='string'||msg.mount.length>128)return;
      if(typeof msg.mount_epoch!=='string'||!/^\d{1,20}$/.test(msg.mount_epoch)||BigInt(msg.mount_epoch)<=this.mountEpoch)return;
      this.mountEpoch=BigInt(msg.mount_epoch);
      this.source.cancelBefore(++this.generation);this.drop(this.staged?.chart);this.drop(this.ready?.chart);this.drop(this.chart);this.mount=msg.mount;this.pending=this.staged=this.ready=null;
      this.chart=this.initial;this.frame=String(this.options.generation);return;
    }
    if(msg.mount!==this.mount||this.mount===null)return;
    if(msg.type==='chunked_unmount') {
      this.source.cancelBefore(++this.generation);this.drop(this.staged?.chart);this.drop(this.ready?.chart);this.mount=null;this.pending=this.staged=this.ready=null;return;
    }
    if(msg.type==='chunked_painted'||msg.type==='chunked_rejected') {
      const s=this.staged;
      if(s&&msg.intent===s.intent&&msg.frame===s.frame){if(msg.type==='chunked_painted'){this.drop(this.chart);this.chart=s.chart;this.frame=s.frame;}else this.drop(s.chart);this.staged=null;this.publish();}
      return;
    }
    if(msg.type==='select') {
      if(msg.chunked_frame!==this.frame)return;
      const bounds=[msg.x0,msg.x1,msg.y0,msg.y1];
      if(!bounds.every(Number.isFinite))return;
      const t=this.chart.traces[0],indices=new Uint32Array(t.x.length);
      const n=Number(xyRangeIndices(pointer(t.x,'double *'),pointer(t.y,'double *'),t.x.length,...bounds,pointer(indices,'uint32_t *')));
      const selected=indices.subarray(0,n),ids=new BigUint64Array(n);
      for(let i=0;i<n;i++)ids[i]=this.chart.sourceRowIds[selected[i]];
      this.send({type:'selection',chunked_frame:this.frame,traces:[{id:0,count:n,buf:0}],total:n,
        source_row_ids:[{trace:0,buffer:1,length:n,dtype:'u64'}]},[selected,ids]);
      return {indices:selected,sourceRowIds:ids};
    }
    if(msg.type==='pick'||msg.type==='click') {
      if(msg.chunked_frame!==this.frame)return;
      const i=msg.index,ids=this.chart.sourceRowIds;
      if(msg.trace!==0||!Number.isSafeInteger(i)||i<0||i>=ids.length)return;
      const t=this.chart.traces[0];
      const row={trace:0,index:i,source_row_id:String(ids[i]),x:t.x[i],y:t.y[i]};
      if(msg.type==='pick')this.send({type:'pick_result',seq:msg.seq,chunked_frame:this.frame,row},[]);
      return row;
    }
    if(msg.type!=='view_change')return;
    const x=msg.ranges?.x,y=msg.ranges?.y;
    if(!Array.isArray(x)||!Array.isArray(y)||x.length!==2||y.length!==2||![...x,...y].every(Number.isFinite)||x[0]>=x[1]||y[0]>=y[1]||typeof msg.chunked_intent!=='string'||!/^\d{1,20}$/.test(msg.chunked_intent))return;
    this.source.cancelBefore(++this.generation);
    this.pending={x,y,generation:this.generation,mount:this.mount,intent:msg.chunked_intent};
    if(!this.active){this.active=Promise.resolve().then(()=>this.pump()).finally(()=>{this.active=null;});}
  }
  async pump() {
    while(this.pending&&!this.closed) {
      const request=this.pending;this.pending=null;
      const {budgetBytes,pageBytes}=this.options,capacity=Math.floor(budgetBytes/16);
      const ids=new BigUint64Array(capacity),x=new Float64Array(capacity),y=new Float64Array(capacity),stats=new BigUint64Array(6);
      try {
        const n=await new Promise((resolve,reject)=>xyChunkedColumnsChart.async(this.source.handle,...request.x,...request.y,1,
          BigInt(budgetBytes),BigInt(request.generation),BigInt(pageBytes),pointer(ids,'uint64_t *'),pointer(x,'double *'),pointer(y,'double *'),capacity,pointer(stats,'uint64_t *'),(error,n)=>error?reject(error):resolve(n)));
        if(this.closed||request.generation!==this.generation||request.mount!==this.mount)continue;
        if(n===18446744073709551615n)throw Error(`chunked-column chart failed: native code ${stats[5]}, required ${stats[4]}, budget ${stats[3]}`);
        const count=Number(n),chart=scatterChart(x.subarray(0,count),y.subarray(0,count));
        chart.sourceRowIds=ids.subarray(0,count);
        chart.sourceProvenance={generation:stats[0],firstChunk:stats[1],chunksConsidered:stats[2],chunksRead:stats[3],bytesRead:stats[4]};
        const {spec,buffers}=chart.buildPayload({split:true});spec.chunked={frame:String(request.generation)};
        this.drop(this.ready?.chart);
        this.ready={chart,intent:request.intent,frame:String(request.generation),request,spec,buffers};
        this.publish();
      } catch(error) {
        if(!this.closed&&request.generation===this.generation)this.send({type:'chunked_error',mount:request.mount,intent:request.intent,error:String(error)},[]);
      }
    }
  }
  publish(){
    if(this.staged||!this.ready||this.closed)return;
    const r=this.ready;this.ready=null;
    if(r.request.generation!==this.generation||r.request.mount!==this.mount){this.drop(r.chart);return;}
    this.staged=r;
    this.send({type:'chunked_frame',mount:r.request.mount,intent:r.intent,spec:r.spec},r.buffers);
  }
  async whenIdle(){await this.active;}
  close(){
    if(this.closing)return this.closing;
    this.closed=true;
    let cancellationError;
    try {this.source.cancelBefore(++this.generation);}catch(error){cancellationError=error;}
    this.drop(this.staged?.chart);this.drop(this.ready?.chart);this.drop(this.chart);
    this.pending=this.staged=this.ready=null;
    return this.closing=Promise.resolve(this.active).finally(()=>{this.source.close();if(cancellationError)throw cancellationError;});
  }
}
