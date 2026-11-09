import {attachWasmGraphSession,createXygWasmWorker,XygWasmTemporalController,XygFrozenTemporalGraph} from '/packages/xy-client/dist/index.js';
import {encodeContainer,DTYPE} from '/packages/xy-node/src/graphforge-container.js';
const ids=values=>Uint8Array.from(values.flatMap(v=>Array(16).fill(v)));
const f=(name,type,values)=>({name,dtype:DTYPE[type],values});
const makeWorker=()=>createXygWasmWorker({workerUrl:'/packages/xy-client/dist/wasm-worker.js',wasm:'/packages/xy-client/dist/xyg-wasm.wasm',maxArenaBytes:384*1024*1024});
window.frozenTest={};
window.frozenTest.open=async(shape,dpr)=>{
 const binding={nodeIds:ids([1,2,3]),edgeIds:ids([11,12,13,14]),sourceIds:ids([1,1,2,1]),targetIds:ids([2,2,3,1]),nodeValidFrom:{values:BigInt64Array.from([0n,0n,0n]),validity:new Uint8Array([1,1,1])},nodeValidTo:{values:BigInt64Array.from([30n,30n,10n]),validity:new Uint8Array([1,1,1])}};
 const document=encodeContainer('XYGF',[f('status','u32',[0]),f('kind','utf8','graph'),f('composition.version','u32',[2]),f('node.uuid','uuid',binding.nodeIds),f('edge.uuid','uuid',binding.edgeIds),f('edge.derived','u8',[0,0,0,0]),f('edge.layer','u32',[0xffffffff,0xffffffff,0xffffffff,0xffffffff]),f('edge.order','i64',[-1n,-1n,-1n,-1n]),f('edge.path','u64',[0xffffffffffffffffn,0xffffffffffffffffn,0xffffffffffffffffn,0xffffffffffffffffn]),f('edge.source','u64',[0n,0n,1n,0n]),f('edge.target','u64',[1n,1n,2n,0n]),f('node.class','u8',[shape,shape,shape]),f('node.parent','u32',[0,0,0]),f('node.parent.valid','u8',[0,1,1]),f('node.status','u8',[1,2,3]),f('node.epistemic','u8',[1,2,3]),f('edge.class','u8',[0,1,2,3]),f('edge.status','u8',[0,1,2,3]),f('edge.epistemic','u8',[1,2,3,1])]);
 const worker=makeWorker(),clockWorker=makeWorker();await Promise.all([worker.ready,clockWorker.ready]);
 const controller=await XygWasmTemporalController.create(clockWorker,{instanceId:950n,domain:[0n,40n],cursor:5n,step:1n});await controller.setRange(0n,40n);
 const el=window.document.createElement('div');el.style.setProperty('--chart-focus','rgba(77,110,159,0.75)');window.document.body.append(el);
 const session=attachWasmGraphSession({el,worker,instanceId:950n,document,load:{x:[0,40,80],y:[0,0,20]},camera:[1,1,60,60,240,180,dpr],temporal:{controller,binding,budget:40n}});await session.ready;await session.whenIdle();
 window.frozenTest.current={el,worker,clockWorker,controller,session};return true;
};
window.frozenTest.capture=async(pin=true)=>{
 const p=window.frozenTest.current;await p.session.whenIdle();if(pin)await p.session.pinFocused(true);await p.session.whenIdle();
 p.el.style.setProperty('--chart-focus','rgba(200,100,50,0.5)'); // no repaint: freeze must retain the accepted displayed color.
 const frozen=await p.session.freeze({timezone:'America/New_York',window:[0n,40n]});const before=frozen.toBytes();
 await p.controller.setCursor(10n);await p.session.whenIdle();await p.session.dispose();await p.controller.dispose();p.worker.dispose();p.clockWorker.dispose();p.el.remove();
 const worker=makeWorker();await worker.ready;const imported=await XygFrozenTemporalGraph.fromBytes(before,worker);const explicit=await imported.captureFocus([77,110,159,191],worker);const explicitBytes=explicit.toBytes();const scene=await imported.export('scene',{worker}),painter=await imported.export('painter',{worker}),svg=await imported.export('svg',{worker});
 const png=await imported.export('png',{worker}),png2=await imported.export('png',{worker,scale:2});
 for(const artifact of [png,png2]){const recovered=await XygFrozenTemporalGraph.fromArtifact(artifact,worker);if(recovered.toBytes().length!==before.length||!recovered.toBytes().every((v,i)=>v===before[i]))throw new Error('PNG recovery changed XYFG');}
 for(const artifact of [new Uint8Array(),png.subarray(0,png.length-1),Uint8Array.from(png,(v,i)=>i===40?v^1:v)]){let rejected=false;try{await XygFrozenTemporalGraph.fromArtifact(artifact,worker);}catch{rejected=true;}if(!rejected)throw new Error('malformed PNG accepted');}
 const bounded=createXygWasmWorker({workerUrl:'/packages/xy-client/dist/wasm-worker.js',wasm:'/packages/xy-client/dist/xyg-wasm.wasm'});await bounded.ready;try{const limited=await XygFrozenTemporalGraph.fromBytes(before,bounded);let rejected=false;try{await limited.export('png',{worker:bounded,scale:2});}catch(e){if(e.code!=='XYG_WASM_RESOURCE_LIMIT')throw e;rejected=true;}if(!rejected)throw new Error('default 16MiB PNG reservation bypassed');const again=await limited.export('scene',{worker:bounded});if(!again.every((v,i)=>v===scene[i])||again.length!==scene.length)throw new Error('PNG refusal changed last good state');}finally{bounded.dispose();}
 const client=new Uint8Array(await(await fetch('/packages/xy-client/dist/standalone.js')).arrayBuffer());const html=await imported.export('html',{worker,client}),html2=await imported.export('html',{worker,client,scale:2});
 const recovered=await XygFrozenTemporalGraph.fromArtifact(html,worker,client);const after=recovered.toBytes();const recovered2=await XygFrozenTemporalGraph.fromArtifact(html2,worker,client);if(!recovered2.toBytes().every((v,i)=>v===before[i])||recovered2.toBytes().length!==before.length)throw new Error('scaled HTML recovery changed XYFG');worker.dispose();
 const encode=a=>{let s='';for(let i=0;i<a.length;i+=32768)s+=String.fromCharCode(...a.subarray(i,i+32768));return btoa(s);};
 return {explicit:encode(explicitBytes),snapshot:encode(before),recovered:encode(after),scene:encode(scene),painter:encode(painter),svg:encode(svg),html:encode(html),html2:encode(html2),png:encode(png),png2:encode(png2)};
};

window.frozenTest.legacy=async()=>{const worker=makeWorker();await worker.ready;try{const raw=new Uint8Array(await(await fetch('/spec/performance/temporal-native-render-2026-11-07/artifacts/retained-later.xyfg')).arrayBuffer());const original=await XygFrozenTemporalGraph.fromBytes(raw,worker);const svg=await original.export('svg',{worker,focusRgba:[77,110,159,191]});const explicit=await original.captureFocus([77,110,159,191],worker);const recovered=await XygFrozenTemporalGraph.fromArtifact(svg,worker);const encode=a=>{let s='';for(let i=0;i<a.length;i+=32768)s+=String.fromCharCode(...a.subarray(i,i+32768));return btoa(s);};return {raw:encode(raw),svg:encode(svg),explicit:encode(explicit.toBytes()),recovered:encode(recovered.toBytes())};}finally{worker.dispose();}};
