import {mountedFixture} from './geo-mounted-temporal-fixture.mjs';
import {GeoHierarchy,isHierarchyFrame} from '../src/geo-hierarchy.js';
import {geoChart,geoLayer} from '../src/charts.js';
import {release as releaseCanonical} from './geo-live-host-fixture.mjs';
export async function mountedHierarchyFixture(options={}){
 const base=await mountedFixture({...options,selected:true});await base.adapter.anchorReady;
 const {source,scope}=base,{query,style}=base.chart.layers[0].properties,pages=new Map();let reads=0;
 source.hierarchyReadPage=async ticket=>{reads++;return pages.get(`${ticket.namespace}:${ticket.page}`);};
 let lane,frame,state;
 try{
  lane=await GeoHierarchy.fromSelectedFrame(base.adapter.anchor,source,{grid:1024,maxVertices:1000000n,maxWriteBytes:64n<<20n,readPage:t=>source.hierarchyReadPage(t),writePage:(t,b)=>pages.set(`${t.namespace}:${t.page}`,b.slice())});
  state=await scope.state({revision:1n,ids:BigUint64Array.of(0xffffffffffffffffn),fill:Uint8Array.of(0,255,0,255),budget:source.budget});
  const operation=await lane.beginSelected(state,query,{sequence:3n});await operation.drive();frame=await operation.prepare(style);await state.dispose();state=undefined;
  if(!isHierarchyFrame(frame))throw Error('private hierarchy publication authority absent');
  const chart=geoChart(geoLayer('points',{source,layerId:query.layerId,query,sequence:3n,style}),{camera:query.camera});
  const adapter=chart.host({frame,selectedScope:scope,hierarchyLane:lane});await adapter.anchorReady;
  await frame.dispose();frame=undefined;base.adapter.close();await base.adapter.cleanup;
  return {source,scope,lane,chart,adapter,pages,pageReads:()=>reads};
 }catch(error){await state?.dispose();await frame?.dispose();base.adapter.close();await base.adapter.cleanup;await lane?.dispose();await source.dispose();await scope.dispose();throw error;}
}
export async function release(f){await releaseCanonical(f);await f.lane.dispose();}
