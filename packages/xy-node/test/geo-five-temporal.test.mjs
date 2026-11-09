import assert from 'node:assert/strict';
import test from 'node:test';
import {fiveTemporalFixture} from './geo-five-temporal-fixture.mjs';
import {attachGeoWebview} from '../src/geo-webview.js';
import {temporalControllerCreate,temporalControllerDestroy} from '../src/index.js';
test('five genuine hierarchy lanes admit bindings while canonical snapshot remains excluded',async()=>{
 const fixture=await fiveTemporalFixture(),bindings=[];
 const h=temporalControllerCreate({instanceId:991n,domainStart:-100n,domainEnd:100n,cursor:0n,window:0n,step:1n});
 try{
  for(const f of fixture.views){
   assert.equal(f.source,fixture.views[0].source);
   const panel={webview:{onDidReceiveMessage(){return {dispose(){}};},postMessage(){return true;}},onDidDispose(){return {dispose(){}};}};
   const host=attachGeoWebview(panel,f.adapter);bindings.push(host.bindTemporal(h));
   assert.throws(()=>host.bindTemporal(h),/already/);
  }
  assert.equal(bindings.length,5);assert.equal(new Set(fixture.views.map(f=>f.lane.handle)).size,5);
  assert.throws(()=>fixture.views[0].chart.bindTemporal(h),/already/);
 }finally{for(const b of bindings)await b.dispose();temporalControllerDestroy(h);await fixture.dispose();}
});
