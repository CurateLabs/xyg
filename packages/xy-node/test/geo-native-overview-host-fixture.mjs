import {fixture,budget,U64} from './geoscale-fixture.mjs';
import {RetainedGeoSource} from '../src/geo-retained.js';
import {GeoOverviewIndex} from '../src/geo-overview-source.js';
import {geoChart,geoLayer} from '../src/charts.js';
import {nativeGeoScaleBridge,encodeGeoScaleRequest,decodeGeoScaleReply} from '../src/geoscale.js';
export async function overviewHostFixture({bridge,host=true,splitTime=false}={}){
 let query,style;const packets=await fixture(undefined,async(_,f)=>{query=f.query;style=f.style;});
 const bytes=h=>Uint8Array.from(Buffer.from(h,'hex'));let chunk=bytes(packets.chunk),manifest=bytes(packets.manifest);
 if(splitTime){const native=bridge??nativeGeoScaleBridge(budget.processorBytes),author=bytes(packets.chunk_request),v=new DataView(author.buffer),timeAt=288+Number(v.getBigUint64(256,true));v.setBigInt64(timeAt+8,0n,true);v.setBigInt64(timeAt+16,0n,true);chunk=new Uint8Array(await native.read(author.buffer));const builder=decodeGeoScaleReply(await native.execute(encodeGeoScaleRequest({command:1}))).handle;try{await native.execute(encodeGeoScaleRequest({command:2,handle:builder,payload:chunk}));await native.execute(encodeGeoScaleRequest({command:3,handle:builder,generation:U64}));manifest=new Uint8Array(await native.read(encodeGeoScaleRequest({command:21,handle:builder})));}finally{await native.execute(encodeGeoScaleRequest({command:10,handle:builder}));}}
 const source=await RetainedGeoSource.create(manifest,async()=>chunk,{budget,...bridge?{bridge}:{}});
 query={...query,sourceDigest:source.info.digest,generation:source.info.generation,cameraRevision:1n,timeRevision:1n,stateRevision:1n};
 const seed=await source.update(query,{sequence:1n,style}),pages=new Map(),control={readPage:async t=>pages.get(`${t.namespace}:${t.page}`)};
 const index=await GeoOverviewIndex.fromFrame(seed,{bridge:source.bridge,budget,maxVertices:1000000n,readChunk:async()=>chunk,readPage:async t=>control.readPage(t),writePage:async(t,b)=>pages.set(`${t.namespace}:${t.page}`,b.slice())});
 const q={...query,maxCells:0,previousDirect:false,maxProjectedVertices:0n};
 const chart=geoChart(geoLayer('density',{source:index,layerId:U64,query:q,sequence:2n}),{camera:q.camera});
 const adapter=host?chart.host():undefined;return {source,seed,index,chart,adapter,control,async dispose(){if(adapter)await adapter.realmDestroyed();await index.dispose();await seed.dispose();await source.dispose();}};
}
