import assert from 'node:assert/strict';
import test from 'node:test';
import {createGraphForgeIntent,isVisualizationIntent} from '../src/intent.cjs';
test('saved graph intent is explicit, serializable and native-free',()=>{
 const spec=createGraphForgeIntent({name:'Routes',result:'results/routes.json'});
 assert.equal(spec.format,'xyg.intent/v1');assert.equal(spec.graph.layout,'cose');
 assert.ok(isVisualizationIntent(JSON.parse(JSON.stringify(spec))));
});
test('rejects obsolete, remote, executable and unbounded authoring',()=>{
 const spec=createGraphForgeIntent({name:'Routes',result:'results/routes.json'});
 for(const value of [null,[],{}, {...spec,format:'old/v1'},{...spec,result:'https://example.com/x'}, {...spec,renderer:'vendor'}, {...spec,graph:{...spec.graph,callback:()=>0}},{...spec,graph:{layout:'cose',iterations:Infinity}}])assert.equal(isVisualizationIntent(value),false);
});

test('typed enum fields never coerce JSON arrays or unrelated authoring fields',()=>{
 const spec=createGraphForgeIntent({name:'Routes',result:'results/routes.json'});
 for(const value of [{...spec,graph:{...spec.graph,layout:['cose']}},{...spec,intent:['table']},{...spec,filters:[{column:'x',operator:['equals'],value:'1'}]},{...spec,chart:{mark:'line',x:'x',y:'y'}},{...spec,filters:[{column:'x',operator:'equals',value:'1',callback:'x'}]}])assert.equal(isVisualizationIntent(value),false);
});

test('histogram accepts an omitted y but rejects a non-string y',()=>{
 const base={format:'xyg.intent/v1',name:'Histogram',result:'results/x.json',kind:'chart',filters:[]};
 assert.ok(isVisualizationIntent({...base,chart:{mark:'histogram',x:'x'}}));
 assert.equal(isVisualizationIntent({...base,chart:{mark:'histogram',x:'x',y:[]}}),false);
});
