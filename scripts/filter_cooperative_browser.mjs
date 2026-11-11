// Required by the existing Filter Tier C conformance CI command. Uses public
// session methods and real Worker turns; the scan/count oracle is independent.
export async function proveFilterCooperative(page,moduleURL='/packages/xy-client/dist/xyg-wasm.wasm') {
 return await page.evaluate(async(moduleURL)=>{
  const xy=await import('/packages/xy-client/dist/index.js');
  const module=await WebAssembly.compileStreaming(fetch(moduleURL));
  const observed=[]; window.cooperativeWorkerErrors=[]; const Original=globalThis.Worker;
  globalThis.Worker=class extends Original{constructor(...args){super(...args);this.addEventListener('error',e=>window.cooperativeWorkerErrors.push({message:e.message,filename:e.filename,line:e.lineno,stack:String(e.error?.stack)}));this.addEventListener('message',e=>{
   if(e.data?.type==='filter.progress')observed.push(e.data);
  });}};
  const make=()=>xy.createXygWasmWorker({workerUrl:'/packages/xy-client/dist/wasm-worker.js',wasm:module,maxArenaBytes:16<<20,evidenceCapability:'cooperative-filter-proof'});
  const check=(x,m)=>{if(!x)throw new Error(m);};
  const until=async(predicate)=>{const end=performance.now()+15000;while(!predicate()){
   if(performance.now()>end)throw new Error('filter progress watchdog'); await new Promise(r=>setTimeout(r,1));
  }};
  // Public constructor rollback must await its owning transport's release ACK.
  // Test the async boundary directly, including first-error preservation.
  for (const cleanupFails of [false,true]) {
   let release,closed=false,settled=false;
   const original=new Error('intentional initialization refusal');
   const fake=make();await fake.ready;const dispose=fake.dispose.bind(fake);
   fake.filterCommand=async()=>{throw original;};
   fake.dispose=()=>new Promise((resolve,reject)=>{
    release=async()=>{await dispose();cleanupFails?reject(new Error('intentional cleanup refusal')):resolve();};closed=true;
   });
   const construction=xy.createWasmFilterSession(fake,{x:[1]},{sourceId:1n,budgetBytes:1n<<20n})
    .then(()=>{settled=true;return null;},e=>{settled=true;return e;});
   await until(()=>closed);check(!settled,'constructor rejected before owner release ACK');
   release();check(await construction===original,'cleanup replaced initialization failure');
  }
  // Interleaving cannot retire another product's queued/active compilation.
  // Its exact painter must finish; a refused filter may retry after draining.
  const busy=make();await busy.ready;
  try {
   const typed=xy.frameWasmChart({width:160,height:100,series:[{kind:'scatter',
    x:new Float64Array([1,2]),y:new Float64Array([3,4])}]});
   const compile=busy.compilePrepareSeries(typed).result.then(value=>({value}),error=>({error}));
   const attempt=await xy.createWasmFilterSession(busy,{x:[1,2]},
    {sourceId:1n,epoch:2n,budgetBytes:16n<<20n}).then(value=>({value}),error=>({error}));
   const compiled=await compile;check(compiled.value&&!compiled.error,'filter attempt retired a foreign compilation');
   const referenceWorker=make();await referenceWorker.ready;
   try {
    const reference=await referenceWorker.compilePrepareSeries(xy.frameWasmChart({width:160,height:100,
     series:[{kind:'scatter',x:new Float64Array([1,2]),y:new Float64Array([3,4])}]})).result;
    const actualBytes=new Uint8Array(compiled.value.painter),expectedBytes=new Uint8Array(reference.painter);
    check(actualBytes.length===expectedBytes.length&&actualBytes.every((x,i)=>x===expectedBytes[i]),'interleaved compile painter changed');
   }finally{await referenceWorker.dispose();}
   check(attempt.error?.code==='XYG_WASM_INVALID_ARGUMENT','filter did not refuse an unsettled foreign task');
   const recovered=await xy.createWasmFilterSession(busy,{x:[1,2]},
    {sourceId:1n,epoch:2n,budgetBytes:16n<<20n});
   let duplicate=false;try{await xy.createWasmFilterSession(busy,{x:[1,2]},
    {sourceId:2n,budgetBytes:16n<<20n});}catch(error){duplicate=error.code==='XYG_WASM_INVALID_ARGUMENT';}
   check(duplicate,'duplicate source factory stole its owning Worker');
   check((await recovered.configure({id:1n,dimension:'x',cuts:[1.5]},[{id:1n,dimension:'x',cuts:[1.5]}])).status===0,'duplicate claim damaged accepted owner');
   await recovered.close();
  }finally{await busy.dispose();}
  let session,worker;
  try{
   worker=make();await worker.ready;
   const n=150003,columns={x:new Float64Array(n),y:new Float64Array(n)};
   for(let i=0;i<n;i++){columns.x[i]=i%1009===0?NaN:i%37;columns.y[i]=i%997===0?Infinity:(i*7)%41-2;}
   session=await xy.createWasmFilterSession(worker,columns,{sourceId:1n,epoch:2n,firstRow:99n,budgetBytes:16n<<20n});
   const active={id:1n,dimension:'x',cuts:[0,18]};
   const views=Array.from({length:5},(_,i)=>({id:BigInt(i+1),x:i%2?'y':'x',y:i%2?'x':'y',width:4,height:4,xRange:[-6,38],yRange:[-6,38]}));
   let before=observed.length;
   const configuring=session.configureDensity(active,views).then(x=>({value:x}),e=>({error:e}));
   await until(()=>observed.length>before);check(observed[before].rows===0n,'capture performed row work before yielding');
   const bad=new Uint8Array(96);bad.set([88,89,70,67]);const bd=new DataView(bad.buffer);bd.setUint32(4,99,true);bd.setUint32(8,4,true);bd.setBigUint64(16,999n,true);
   const malformed=xy.decodeFilterReply(await worker.filterCommand(bad.buffer,{cooperative:true}));
   check(malformed.status===1&&malformed.newestRevision===2n,'malformed header consumed cooperative job');
   await session.cancel();const cancelled=await configuring;check(cancelled.error?.code==='XYG_WASM_CANCELLED',`superseded configure did not reject: ${String(cancelled.error)} code=${cancelled.error?.code} value=${String(cancelled.value?.revision)} events=${JSON.stringify(window.cooperativeWorkerErrors)}`);
   const configured=await session.configureDensity(active,views);check(configured.revision===4n,'configure recovery revision');
   const prior=(await session.paint()).filterHash;
   before=observed.length;
   const scanning=session.range(4,12,{exact:true}).then(x=>({value:x}),e=>({error:e}));
   await until(()=>observed.length>before&&observed.slice(before).some(x=>x.rows>0n));
   await session.cancel();check((await scanning).error?.code==='XYG_WASM_CANCELLED','exact scan cancellation did not reject');
   check((await session.paint()).filterHash===prior,'cancelled scan changed accepted predicate');
   const exact=await session.range(4,12,{exact:true});check(exact.tier===2n&&exact.fallback===1n&&exact.rowsRead===BigInt(n),'exact scan work accounting');
   let selected=0;const counts=views.map(()=>Array(16).fill(0n));
   for(let i=0;i<n;i++){
    const x=columns.x[i];if(!Number.isFinite(x)||x<4||x>12)continue;selected++;
    views.forEach((v,j)=>{const x=columns[v.x][i],y=columns[v.y][i];if(!Number.isFinite(x)||!Number.isFinite(y)||x< -6||x>=38||y< -6||y>=38)return;
     counts[j][Math.floor((y+6)*4/44)*4+Math.floor((x+6)*4/44)]++;
    });
   }
   check(exact.selectedCount===BigInt(selected),'canonical selected count mismatch');
   exact.views.forEach((v,j)=>check(v.counts.every((x,i)=>x===counts[j][i]),'exact count plane mismatch'));
   before=observed.length;const membership=session.membership(1099n,40001);
   await until(()=>observed.length>before);check(observed[before].rows===0n&&observed[before].totalRows===40001n,'membership progress was not relative');
   const page=await membership;
   for(let i=0;i<40001;i++){const x=columns.x[1000+i];check(Boolean(page.membership[i>>3]&(1<<(i&7)))===(Number.isFinite(x)&&x>=4&&x<=12),'membership oracle mismatch');}
   await session.evict();const painting=session.paint({exact:true}).then(x=>({value:x}),e=>({error:e}));
   before=observed.length;await until(()=>observed.length>before);await session.cancel();check((await painting).error?.code==='XYG_WASM_CANCELLED','rebuild cancellation did not reject');
   const recovered=await session.paint({exact:true});check(recovered.selectedCount===BigInt(selected),'rebuild/exact recovery changed membership');
   before=observed.length;const pending=session.membership(1099n,40001).then(x=>({value:x}),e=>({error:e}));
   await until(()=>observed.length>before);await session.close();session=null;
   check(Boolean((await pending).error),'pending work survived owning Worker disposal');
   const fresh=make();
   const next=await xy.createWasmFilterSession(fresh,{x:[1,2],y:[3,4]},{sourceId:2n,budgetBytes:1n<<20n});
   const dispose=fresh.dispose.bind(fresh);let release;
   fresh.dispose=()=>new Promise(resolve=>{release=async()=>{await dispose();resolve();};});
   const firstClose=next.close(),secondClose=next.close();let closed=false;
   firstClose.then(()=>{closed=true;});check(firstClose===secondClose,'repeated close lost the shared release ACK');
   await Promise.resolve();check(!closed,'close settled before owner release');await release();await secondClose;
   check(window.cooperativeWorkerErrors.length===0,'Worker errors escaped the cooperative lifetime');
   return {rendered:false,readinessAdmission:1,constructorReleaseAck:2,repeatedCloseAck:1,foreignCompilePainterComparisons:1,duplicateWorkerClaims:1,progressReplies:observed.length,selected,membershipBits:40001,views:5,sourceRows:n,checks:['yield-before-rows','malformed-header-preservation','configure-cancellation','scan-cancellation','exact-count-oracle','relative-membership-progress','membership-bit-oracle','rebuild-cancellation','rebuild-scan-recovery','pending-disposal','fresh-worker-reuse']};
  }finally{if(session)await session.close();else if(worker)await worker.dispose();globalThis.Worker=Original;delete window.cooperativeWorkerErrors;}
 },moduleURL);
}
