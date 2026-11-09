import {createGeoSelectedScope} from '../src/geo-selected.js';
import {fixture,budget,U64,I64} from './geoscale-fixture.mjs';
import {nativeGeoScaleBridge,encodeGeoChunkRequest,encodeGeoScaleRequest as encode,decodeGeoScaleReply as decode} from '../src/geoscale.js';
import {RetainedGeoSource,attachRetainedFrame} from '../src/geo-retained.js';
import {geoChart,geoLayer} from '../src/charts.js';
export async function mountedFixture({selected=true,aggregate=false,spread=false}={}){
 let query,style;const original=await fixture(undefined,async(_,f)=>{query=f.query;style=f.style;});
 const bridge=nativeGeoScaleBridge(budget.processorBytes),input=Uint8Array.from(Buffer.from(original.chunk_request,'hex')),descriptor0=input.slice(288,408);
 const n=aggregate?32769:2,idsAt=64+n*16+Math.ceil(n/8)*8,descriptor=aggregate?new Uint8Array(idsAt+n*8):descriptor0;
 if(aggregate){const v=new DataView(descriptor.buffer);descriptor.set([88,89,71,68]);[1,1,4326,1,0].forEach((x,i)=>v.setUint32(4+i*4,x,true));[BigInt(n),BigInt(n),0n,0n,0n].forEach((x,i)=>v.setBigUint64(24+i*8,x,true));descriptor.fill(1,64+n*16,64+n*17);for(let i=0;i<n;i++)v.setBigUint64(idsAt+i*8,i?BigInt(i):U64,true);}
 if(spread)new DataView(descriptor.buffer,descriptor.byteOffset,descriptor.byteLength).setFloat64(80,45,true);
 const chunk=await bridge.read(encodeGeoChunkRequest({descriptor,rows:n,intervals:{starts:new BigInt64Array(n).fill(I64),ends:new BigInt64Array(n).fill(100000n),startValidity:new Uint8Array(n).fill(1),endValidity:new Uint8Array(n).fill(1)},values:new Float64Array(n)},budget.processorBytes));
 const builder=decode(await bridge.execute(encode({command:1}))).handle;let manifest;
 try{await bridge.execute(encode({command:2,handle:builder,payload:chunk}));await bridge.execute(encode({command:3,handle:builder,generation:U64}));manifest=await bridge.read(encode({command:21,handle:builder}));}finally{await bridge.execute(encode({command:10,handle:builder}));}
 const source=await RetainedGeoSource.create(manifest,async()=>chunk,{budget});
 query={...query,sourceDigest:source.info.digest,generation:source.info.generation,cameraRevision:1n,timeRevision:1n,stateRevision:1n,...aggregate?{maxCells:1,previousDirect:false}:{}};
 if(!selected){const chart=geoChart(geoLayer('points',{source,layerId:U64,query,sequence:1n,style}),{camera:query.camera});return {source,chart,adapter:chart.host()};}
 const canonical=await source.update(query,{sequence:1n,style});
 const scope=await createGeoSelectedScope(source.bridge,{frameHandle:canonical.handle,sequence:1n,namespace:U64,layerId:U64,budget});
 const state=await scope.state({revision:1n,ids:new BigUint64Array([U64]),fill:new Uint8Array([0,255,0,255]),budget});
 const accepted=await state.begin({command:35,handle:source.handle,sequence:2n,query,budget});
 await accepted.operation.drive({readChunk:source.readChunk});const frame=await accepted.operation.prepare(style);
 attachRetainedFrame(source,frame,2n,encode({command:35,handle:source.handle,sequence:2n,query,budget,payload:new Uint8Array(8)}),style);source.sequence=2n;
 await state.dispose();
 const chart=geoChart(geoLayer('points',{source,layerId:U64,query,sequence:2n,style}),{camera:query.camera});
 const adapter=chart.host({frame,selectedScope:scope});await adapter.anchorReady;await frame.dispose();await canonical.dispose();
 return {source,chart,adapter,scope};
}
