import {fixture,budget,U64} from './geoscale-fixture.mjs';
import {RetainedGeoSource} from '../src/geo-retained.js';
import {geoChart,geoLayer} from '../src/charts.js';
import {encodeGeoViewportRequest} from '../src/geoviewport.js';
let saved;
export async function liveFixture(){
 if(!saved){let query,style;const packets=await fixture(undefined,async(_,f)=>{query=f.query;style=f.style;});saved={packets,query,style};}
 const fromHex=h=>Uint8Array.from(Buffer.from(h,'hex')).buffer,chunk=fromHex(saved.packets.chunk),source=await RetainedGeoSource.create(fromHex(saved.packets.manifest),async()=>chunk,{budget});
 const query={...saved.query,cameraRevision:1n,timeRevision:1n,stateRevision:1n};
 const chart=geoChart(geoLayer('points',{source,layerId:U64,query,sequence:1n,style:saved.style}),{camera:query.camera});
 return {source,chart,adapter:chart.host()};
}
export function request(adapter,op,{owner=0n,sequence=0n,mount='native',version=1,payload}={}){
 const b=new ArrayBuffer(32+(payload?.byteLength??0)),v=new DataView(b);new Uint8Array(b).set([88,89,71,72]);v.setUint32(4,version,true);v.setUint32(8,op,true);v.setBigUint64(16,owner,true);v.setBigUint64(24,sequence,true);if(payload)new Uint8Array(b).set(new Uint8Array(payload),32);
 return adapter.handle({type:'geo_host',request:`${mount}:${op}`,mount},[b]);
}
export function prepare(adapter,{nonce=1n,sequence=2n,camera}={}){
 const b=new ArrayBuffer(224),v=new DataView(b);[nonce,sequence,sequence,sequence,1n].forEach((n,i)=>v.setBigUint64(i*8,n,true));new Uint8Array(b).set(new Uint8Array(encodeGeoViewportRequest(camera??adapter.frame.data.identity.camera,3,[1,0])),64);
 return request(adapter,6,{version:2,owner:adapter.frame.handle,sequence:adapter.sequence,payload:b});
}
export function acknowledge(adapter,op,old,sequence,tag){return request(adapter,op,{version:2,owner:old,sequence,payload:tag.slice(32)});}
export async function release(f){
 const a=f.adapter,c=a.liveCandidate;
 if(c.frame){if(c.committed){const p=new ArrayBuffer(32),v=new DataView(p);[c.nonce,c.frame.handle,c.sequence].forEach((n,i)=>v.setBigUint64(i*8,n,true));await request(a,8,{version:2,owner:c.retired.handle,sequence:c.retiredSequence,payload:p});}else{const p=new ArrayBuffer(32),v=new DataView(p);[c.nonce,c.frame.handle,c.sequence].forEach((n,i)=>v.setBigUint64(i*8,n,true));await request(a,9,{version:2,owner:a.frame.handle,sequence:a.sequence,payload:p});}}
 if(a.frame)await request(a,4,{owner:a.frame.handle,sequence:a.sequence});a.close();await a.cleanup;await f.source.dispose();
}
