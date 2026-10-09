import {liveFixture,request,prepare,acknowledge} from './geo-live-host-fixture.mjs';
import {GeoHierarchy} from '../src/geo-hierarchy.js';
import {createGeoSelectedScope} from '../src/geo-selected.js';
import {geoChart,geoLayer} from '../src/charts.js';
export {request,prepare,acknowledge};
export async function hierarchyFixture(){
 const original=await liveFixture(),{source}=original,q=original.adapter.query,style=original.adapter.style;
 original.adapter.close();await original.adapter.cleanup;
 const first=await source.update(q,{sequence:1n,style});
 const scope=await createGeoSelectedScope(source.bridge,{frameHandle:first.handle,sequence:1n,namespace:777n,layerId:q.layerId,budget:source.budget});
 const state=await scope.state({revision:1n,ids:new BigUint64Array([0xffffffffffffffffn]),fill:new Uint8Array([0,255,0,255]),budget:source.budget});
 const canonical=await state.begin({command:35,handle:source.handle,sequence:2n,query:q,budget:source.budget});await canonical.operation.drive({readChunk:source.readChunk});const selected=await canonical.operation.prepare(style);
 // Hierarchy creation verifies private producer registration, not raw packet metadata.
 const {attachRetainedFrame}=await import('../src/geo-retained.js');const {encodeGeoScaleRequest}=await import('../src/geoscale.js');
 attachRetainedFrame(source,selected,2n,encodeGeoScaleRequest({command:35,handle:source.handle,sequence:2n,query:q,budget:source.budget,payload:new Uint8Array(8)}),style);
 await state.dispose();
 const pages=new Map(),control={failRead:false};
 const lane=await GeoHierarchy.fromSelectedFrame(selected,source,{grid:1024,maxVertices:1000000n,maxWriteBytes:64n<<20n,readPage:t=>{if(control.failRead)throw Error('injected hierarchy read failure');return pages.get(`${t.namespace}:${t.page}`);},writePage:(t,b)=>pages.set(`${t.namespace}:${t.page}`,b.slice())});
 const issued=await scope.state({revision:1n,ids:new BigUint64Array([0xffffffffffffffffn]),fill:new Uint8Array([0,255,0,255]),budget:source.budget});
 const op=await lane.beginSelected(issued,q,{sequence:3n});await op.drive();const frame=await op.prepare(style);await issued.dispose();
 const chart=geoChart(geoLayer('points',{source,layerId:q.layerId,query:q,sequence:3n,style}),{camera:q.camera});
 const adapter=chart.host({frame,selectedScope:scope,hierarchyLane:lane});await adapter.anchorReady;
 await first.dispose();await selected.dispose();await source.dispose();await frame.dispose();
 return {source,scope,lane,chart,adapter,control,query:q,style};
}
export async function releaseHierarchy(f){
 await f.adapter.realmDestroyed();await f.adapter.cleanup;await f.lane.dispose();await f.source.dispose();await f.scope.dispose();
}
export async function hierarchyFiveFixtures(){
 const root=await hierarchyFixture(),fixtures=[root];
 try{for(let i=1;i<5;i++){
  const lane=await root.lane.fork();
  const state=await root.scope.state({revision:1n,ids:new BigUint64Array([0xffffffffffffffffn]),fill:new Uint8Array([0,255,0,255]),budget:root.source.budget});
  const op=await lane.beginSelected(state,root.query,{sequence:3n});await op.drive();const frame=await op.prepare(root.style);await state.dispose();
  const chart=geoChart(geoLayer('points',{source:root.source,layerId:root.query.layerId,query:root.query,sequence:3n,style:root.style}),{camera:root.query.camera});
  const adapter=chart.host({frame,selectedScope:root.scope,hierarchyLane:lane});await adapter.anchorReady;await frame.dispose();fixtures.push({...root,lane,chart,adapter});
 }return fixtures;}
 catch(error){await releaseFive(fixtures);throw error;}
}
export async function releaseFive(fixtures){
 for(const f of fixtures){await f.adapter.realmDestroyed();await f.adapter.cleanup;}
 for(const f of fixtures)await f.lane.dispose();
 await fixtures[0]?.source.dispose();await fixtures[0]?.scope.dispose();
}
// Canonical/flat-index controls exercise the shared State allocation seam without
// changing their established35/36 query routing.
export async function selectedLiveFixture(indexed){
 const original=await liveFixture(),origin=original.source,q=original.adapter.query,style=original.adapter.style;
 original.adapter.close();await original.adapter.cleanup;
 const first=await origin.update(q,{sequence:1n,style}),pages=new Map();
 const source=indexed?await first.spatialIndex({grid:16,maxVertices:1000000n,readPage:t=>pages.get(t.page),writePage:(t,b)=>pages.set(t.page,b.slice())}):origin;
 const scope=await createGeoSelectedScope(origin.bridge,{frameHandle:first.handle,sequence:1n,namespace:0xffffffffffffffffn,layerId:q.layerId,budget:origin.budget});
 const state=await scope.state({revision:1n,ids:new BigUint64Array([0xffffffffffffffffn]),fill:new Uint8Array([0,255,0,255]),budget:origin.budget});
 const accepted=await state.begin({command:indexed?36:35,handle:source.handle,sequence:2n,query:q,budget:source.budget});await accepted.operation.drive({readChunk:source.readChunk,readPage:source.readPage});const frame=await accepted.operation.prepare(style);
 const {attachRetainedFrame}=await import('../src/geo-retained.js'),{encodeGeoScaleRequest}=await import('../src/geoscale.js');
 attachRetainedFrame(source,frame,2n,encodeGeoScaleRequest({command:indexed?36:35,handle:source.handle,sequence:2n,query:q,budget:source.budget,payload:new Uint8Array(8)}),style);
 if(indexed)await accepted.operation.dispose();await state.dispose();
 const chart=geoChart(geoLayer('points',{source,layerId:q.layerId,query:q,sequence:2n,style}),{camera:q.camera}),adapter=chart.host({frame,selectedScope:scope});await adapter.anchorReady;await frame.dispose();await first.dispose();
 return {source,origin,scope,adapter};
}
export async function releaseSelectedLive(f){await f.adapter.realmDestroyed();await f.adapter.cleanup;await f.source.dispose();if(f.origin!==f.source)await f.origin.dispose();await f.scope.dispose();}
