import {attachWasmGraphSession,createXygWasmWorker,XygWasmTemporalController,XygFrozenTemporalGraph} from '/packages/xy-client/dist/index.js';
import {encodeContainer,DTYPE} from '/packages/xy-node/src/graphforge-container.js';
const ids=xs=>Uint8Array.from(xs.flatMap(x=>Array(16).fill(x)));
const field=(name,type,values)=>({name,dtype:DTYPE[type],values});
const makeWorker=()=>createXygWasmWorker({workerUrl:'/packages/xy-client/dist/wasm-worker.js',wasm:'/packages/xy-client/dist/xyg-wasm.wasm',maxArenaBytes:384*1024*1024});
const encode=a=>{let s='';for(let i=0;i<a.length;i+=32768)s+=String.fromCharCode(...a.subarray(i,i+32768));return btoa(s);};
window.aggregateTest={};
window.aggregateTest.open=async()=>{
 const binding={nodeIds:ids([1,2,3,4]),edgeIds:ids([11,12,13,14,15,16]),sourceIds:ids([1,1,2,3,1,4]),targetIds:ids([3,3,4,1,1,4]),nodeValidTo:{values:BigInt64Array.from([40n,10n,20n,30n]),validity:new Uint8Array(4).fill(1)}};
 const document=encodeContainer('XYGF',[field('status','u32',[0]),field('kind','utf8','graph'),field('composition.version','u32',[2]),field('node.uuid','uuid',binding.nodeIds),field('edge.uuid','uuid',binding.edgeIds),field('edge.derived','u8',Array(6).fill(0)),field('edge.layer','u32',Array(6).fill(0xffffffff)),field('edge.order','i64',Array(6).fill(-1n)),field('edge.path','u64',Array(6).fill(0xffffffffffffffffn)),field('edge.source','u64',[0n,0n,1n,2n,0n,3n]),field('edge.target','u64',[2n,2n,3n,0n,0n,3n])]);
 const worker=makeWorker(),clockWorker=makeWorker();await Promise.all([worker.ready,clockWorker.ready]);
 const controller=await XygWasmTemporalController.create(clockWorker,{instanceId:951n,domain:[0n,40n],cursor:20n,step:1n});await controller.setRange(0n,40n);
 const el=window.document.createElement('div');el.style.setProperty('--chart-focus','rgba(77,110,159,0.75)');window.document.body.append(el);
 const session=attachWasmGraphSession({el,worker,instanceId:951n,document,load:{x:[0,1,100,101],y:[0,0,0,0],budgets:[2n,8n]},camera:[1,1,30,60,240,180,1],temporal:{controller,binding,budget:80n}});await session.ready;await session.whenIdle();
 window.aggregateTest.current={el,worker,clockWorker,controller,session,snapshots:[]};
};
window.aggregateTest.capture=async(cursor)=>{const p=window.aggregateTest.current;if(cursor===5&&p.snapshots.length===5)await Promise.all([p.controller.setCursor(10n),p.controller.setCursor(30n),p.controller.setCursor(5n)]);else if(cursor!==null)await p.controller.setCursor(BigInt(cursor));await p.session.whenIdle();const f=await p.session.freeze({timezone:'UTC',window:[0n,40n]});p.snapshots.push(f.toBytes());return encode(f.toBytes());};
window.aggregateTest.finish=async()=>{
 const p=window.aggregateTest.current;await p.controller.setCursor(30n);await p.session.whenIdle();await p.session.dispose();await p.controller.dispose();p.worker.dispose();p.clockWorker.dispose();p.el.remove();
 const worker=makeWorker();await worker.ready;const client=new Uint8Array(await(await fetch('/packages/xy-client/dist/standalone.js')).arrayBuffer());const output=[];
 try{for(const bytes of p.snapshots){const f=await XygFrozenTemporalGraph.fromBytes(bytes,worker),row={snapshot:encode(bytes)};
 for(const format of ['scene','painter','svg','png','html']){let artifact;try{artifact=await f.export(format,{worker,...(format==='html'?{client}:{})});}catch(e){throw Error('snapshot '+output.length+' '+format+': '+e+' status '+e.status+' code '+e.code);}row[format]=encode(artifact);if(['svg','png','html'].includes(format)){const recovered=await XygFrozenTemporalGraph.fromArtifact(artifact,worker,client);if(encode(recovered.toBytes())!==encode(bytes))throw Error('exact recovery failed: '+format);}}
 output.push(row);}}finally{worker.dispose();}return output;
};
