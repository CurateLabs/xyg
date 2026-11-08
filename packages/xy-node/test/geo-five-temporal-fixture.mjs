import {mountedHierarchyFixture} from './geo-mounted-hierarchy-temporal-fixture.mjs';
import {geoChart,geoLayer} from '../src/charts.js';

// Five issued histories, one immutable canonical store, one selected Scope.
export async function fiveTemporalFixture(options={}){
 const first=await mountedHierarchyFixture(options),views=[first];
 try{
  for(let i=1;i<5;i++){
   const lane=await first.lane.fork(),base=first.chart.layers[0].properties;
   const query={...base.query,camera:{...base.query.camera}};
   let state,frame;
   try{
    state=await first.scope.state({revision:1n,ids:BigUint64Array.of(0xffffffffffffffffn),fill:Uint8Array.of(0,255,0,255),budget:first.source.budget});
    const op=await lane.beginSelected(state,query,{sequence:4n});await op.drive();frame=await op.prepare(base.style);await state.dispose();state=undefined;
    const chart=geoChart(geoLayer('points',{source:first.source,layerId:query.layerId,query,sequence:4n,style:base.style}),{camera:query.camera});
    const adapter=chart.host({frame,selectedScope:first.scope,hierarchyLane:lane});await adapter.anchorReady;
    views.push({...first,lane,chart,adapter});
   }catch(error){await lane.dispose();throw error;}
   finally{await state?.dispose();await frame?.dispose();}
  }
  await first.source.dispose();
  return {views,async dispose(){for(const f of views){f.adapter.close();await f.adapter.cleanup;}await first.source.dispose();for(const f of views)await f.lane.dispose();await first.scope.dispose();}};
 }catch(error){for(const f of views){f.adapter.close();await f.adapter.cleanup;}await first.source.dispose();for(const f of views)await f.lane.dispose();await first.scope.dispose();throw error;}
}
