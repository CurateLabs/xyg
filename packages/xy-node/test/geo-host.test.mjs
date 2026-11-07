import {test} from 'node:test';
import assert from 'node:assert/strict';
import {GeoHostAdapter} from '../src/geo-webview.js';
test('native host rejects other source kinds before protocol or bridge access',()=>{
 const chart={_retained:()=>({source:{}})};
 assert.throws(()=>new GeoHostAdapter(chart),{name:'TypeError',message:'native host requires one retained source; a spatial index requires an explicit matching initial frame'});
});
