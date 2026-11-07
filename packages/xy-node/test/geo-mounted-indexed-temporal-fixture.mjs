// Real native external pages and an explicit immutable indexed mount anchor.
import {mountedFixture} from './geo-mounted-temporal-fixture.mjs';
import {request} from './geo-live-host-fixture.mjs';
import {createGeoSelectedScope} from '../src/geo-selected.js';
import {attachRetainedFrame} from '../src/geo-retained.js';
import {encodeGeoScaleRequest as encode} from '../src/geoscale.js';
import {geoChart,geoLayer} from '../src/charts.js';
import {U64,budget} from './geoscale-fixture.mjs';

export async function mountedIndexedFixture({selected=true}={}){
 const base=await mountedFixture({selected:false,spread:true});
 let index,scope,state,frame;
 try{
  await request(base.adapter,1);
  const canonical=base.adapter.frame,pages=new Map();
  index=await canonical.spatialIndex({grid:16,maxVertices:1000000n,readPage:async t=>pages.get(t.page),writePage:async(t,p)=>pages.set(t.page,p.slice())});
  const {query,style}=base.chart.layers[0].properties;
  const q={...query,stateRevision:1n};
  if(selected){
   scope=await createGeoSelectedScope(index.bridge,{frameHandle:canonical.handle,sequence:1n,namespace:U64,layerId:U64,budget});
   state=await scope.state({revision:1n,ids:BigUint64Array.of(U64),fill:Uint8Array.of(0,255,0,255),budget});
   const accepted=await state.begin({command:36,handle:index.handle,sequence:2n,query:q,budget});
   await accepted.operation.drive({readChunk:index.readChunk,readPage:index.readPage});
   frame=await accepted.operation.prepare(style);
   attachRetainedFrame(index,frame,2n,encode({command:36,handle:index.handle,sequence:2n,query:q,budget,payload:new Uint8Array(8)}),style);index.sequence=2n;
   await state.dispose();state=undefined;
  }else frame=await index.update(q,{sequence:2n,style});
  const chart=geoChart(geoLayer('points',{source:index,layerId:U64,query:q,sequence:2n,style}),{camera:q.camera});
  const adapter=chart.host({frame,...scope?{selectedScope:scope}:{}});await adapter.anchorReady;
  await frame.dispose();frame=undefined;
  await request(base.adapter,4,{owner:canonical.handle,sequence:base.adapter.sequence});base.adapter.close();await base.adapter.cleanup;await base.source.dispose();
  let pageReads=0,canonicalReads=0;const pageReader=index.readPage;index.readPage=async t=>{pageReads++;return pageReader(t);};index.readChunk=async()=>{canonicalReads++;throw Error('indexed mount attempted canonical fallback');};
  return {source:index,chart,adapter,scope,pages,pageReads:()=>pageReads,canonicalReads:()=>canonicalReads};
 }catch(error){await frame?.dispose();await state?.dispose();base.adapter.close();await base.adapter.cleanup;await base.source.dispose();await index?.dispose();await scope?.dispose();throw error;}
}
