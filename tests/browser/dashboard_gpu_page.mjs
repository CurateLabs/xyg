(async () => {
  const {createXygWasmWorker}=await import('/index.js');
  const worker=createXygWasmWorker({workerUrl:'/wasm-worker.js',wasm:'/xyg-wasm.wasm'});
  await worker.ready;
  const {spec,buf}=gpuFixture, views=[], rows=[];
  const assert=(v,m)=>{if(!v)throw Error(m);};
  // Independent driver-facing oracle. Records calls after admission wrappers
  // and reads actual BUFFER_SIZE; it never reads the production ledger.
  const allocated=new Map(), proto=WebGL2RenderingContext.prototype;
  for(const name of ['bufferData','texImage2D','texStorage2D','deleteBuffer','deleteTexture']) {
    const original=proto[name];
    proto[name]=function(...a) {
      const result=original.apply(this,a);
      if(name==='bufferData') {
        const object=this.getParameter(this.ARRAY_BUFFER_BINDING);
        allocated.set(object,this.getBufferParameter(this.ARRAY_BUFFER,this.BUFFER_SIZE));
      } else if(name.startsWith('tex')) {
        const object=this.getParameter(this.TEXTURE_BINDING_2D);
        allocated.set(object,a[3]*a[4]*(a[2]===this.R8?1:4));
      } else allocated.delete(a[0]);
      return result;
    };
  }
  const grid=document.getElementById('chart');grid.replaceChildren();grid.style.cssText='display:grid;grid-template-columns:repeat(8,150px)';
  for(let i=0;i<32;i++) {
    const holder=document.createElement('div');grid.append(holder);
    const v=xy.renderStandalone(holder,{...spec,width:150,height:150},buf);v._drawNow();v._ctxIo?.disconnect();v._ctxVisible=i<16;if(i>=16)holder.style.display="none";views.push(v);
  }
  const host=views[0]._glHost;
  assert(views.every(v=>v._glHost===host),'one host');
  const actual=()=>[...allocated.values()].reduce((a,b)=>a+BigInt(b),0n);
  const check=label=>{
    const snapshot=host.storageSnapshot();assert(snapshot.logicalBytes===actual(),`${label}: oracle ${actual()} != ledger ${snapshot.logicalBytes}`);
    rows.push({label,bytes:String(actual()),objects:snapshot.objects});
  };
  check('32 initial');
  const picture=v=>Array.from(v._present2d.getImageData(0,0,v.canvas.width,v.canvas.height).data).join(',');
  const before=views.map(picture), identities=views.map(v=>v.gpuTraces[0].trace.id);
  const demand=host.dashboardResourceSnapshot().resources[0].derivedBytes;
  const budget=host.sharedResourceBytes()+demand*8n;
  // Keep real Rust replies pending to exercise admission ownership ordering.
  const {applyWasmDashboardResourceBudget, watchWasmDashboardResourceBudget} = await import('/index.js');
  const delayedPlanner = () => {
    const held = [];
    let commands = 0;
    let delaying = true;
    return {
      held,
      get commands() { return commands; },
      release() {
        delaying = false;
        held.splice(0).forEach(resolve => resolve());
      },
      dashboardPlan(request) {
        commands += 1;
        const operation = worker.dashboardPlan(request);
        return {result: operation.result.then(result => delaying ? new Promise(resolve => {
          held.push(() => resolve(result));
        }) : result)};
      },
    };
  };
  const waitHeld = async (planner, count) => {
    const deadline = performance.now() + 10000;
    while (planner.held.length < count) {
      assert(performance.now() < deadline, 'delayed Rust reply timed out');
      await new Promise(resolve => setTimeout(resolve, 5));
    }
  };
  const rejectedWith = (promise, message) => promise.then(
    () => { throw new Error('obsolete admission unexpectedly succeeded'); },
    error => assert(String(error).includes(message), 'stable admission rejection'),
  );
  const broadBudget = host.sharedResourceBytes() + demand * 128n;
  const older = delayedPlanner();
  const oldResult = rejectedWith(
    applyWasmDashboardResourceBudget(older, host, broadBudget), 'superseded');
  await waitHeld(older, 1);
  await applyWasmDashboardResourceBudget(worker, host, budget, 0n);
  older.release();
  await oldResult;
  assert(host._budget === budget, 'older request cannot restore its global budget');
  assert(views.every(view => view._glLost), 'newer per-chart zero cap remains applied');
  assert(older.commands === 1, 'superseded request issues no retry');
  await applyWasmDashboardResourceBudget(worker, host, broadBudget);
  await new Promise(resolve => setTimeout(resolve, 50));
  const pending = delayedPlanner();
  const cancelledWatcher = watchWasmDashboardResourceBudget(pending, host, broadBudget, 0n);
  await waitHeld(pending, 32);
  const beforeCancellation = actual();
  cancelledWatcher.dispose();
  pending.release();
  await cancelledWatcher.settled;
  await new Promise(resolve => setTimeout(resolve, 50));
  assert(actual() === beforeCancellation && views.every(view => !view._glLost),
    'disposed watcher cannot evict after a pending reply');
  assert(pending.commands === 32, 'cancelled per-chart pass never submits global planning');
  const formerWatcher = watchWasmDashboardResourceBudget(worker, host, broadBudget);
  await formerWatcher.settled;
  await applyWasmDashboardResourceBudget(worker, host, budget, 0n);
  await rejectedWith(formerWatcher.settled, 'superseded');
  host.dashboardResourceChanged(views[0]);
  await new Promise(resolve => setTimeout(resolve, 50));
  assert(host._budget === budget && views.every(view => view._glLost),
    'superseded watcher cannot reclaim future notifications');
  formerWatcher.dispose();
  await applyWasmDashboardResourceBudget(worker, host, broadBudget);
  await new Promise(resolve => setTimeout(resolve, 50));
  check('admission ownership races');
  const controller=views[0].watchDashboardResourceBudget(worker,budget);
  await controller.settled;
  await new Promise(r=>setTimeout(r,100));await controller.settled;
  check('pressure');
  const snapshot=host.dashboardResourceSnapshot();
  assert(!host.applyDashboardResidency(snapshot,snapshot.clients.map(()=>true)),'overbudget residency refused');
  await gpuCapture('pressure');
  assert(actual()+BigInt(host.canvas.width*host.canvas.height*4)<=budget,'bounded storage');
  assert(views.filter(v=>!v._glLost).length===8,'8 whole charts retained');
  assert(views.slice(16).every(v=>v._glLost),'hidden yielded');
  for(let i=0;i<32;i++)assert(picture(views[i])===before[i],'picture preserved '+i);
  const denied=views.find(v=>v._glLost); assert(denied._pickAt(10,10)===null,'no stale pick');
  await controller.settled; await new Promise(r=>setTimeout(r,100)); await controller.settled;
  check('active rebuild');
  assert(!denied._glLost,'active chart re-admitted');
  assert(denied.gpuTraces[0].trace.id===identities[views.indexOf(denied)],'identity');
  for(const v of views){assert(v.canvas.tabIndex===0 && v.canvas.getAttribute('role')==='img' && v.canvas.getAttribute('aria-label'),'per-chart keyboard and ARIA');}
  denied.root.parentElement.style.display='';denied.canvas.focus();assert(document.activeElement===denied.canvas,'focus isolated after rebuild');
  // Aliases and in-place replacement must not grow accounting, whereas a
  // refused capacity request must never reach the independent GL oracle.
  const live=views.find(v=>!v._glLost), gl=live.gl, buffer=live.gpuTraces[0].xBuf;
  const previous=actual();gl.bindBuffer(gl.ARRAY_BUFFER,buffer);
  let refused=false;
  try { gl.bufferData(gl.ARRAY_BUFFER,Number(budget)*2,gl.DYNAMIC_DRAW); }
  catch(e) { refused=String(e).includes('awaits Rust'); }
  assert(refused && actual()===previous,'synchronous refusal before allocation');
  await new Promise(r=>setTimeout(r,100));await controller.settled;check('capacity refused');
  assert(live._glLost && live._pickAt(20,20)===null,'oversized chart suspended');
  controller.dispose();
  await views[0].applyDashboardResourceBudget(worker,budget,0n);
  await new Promise(r=>setTimeout(r,50));
  check('per-chart zero cap');
  assert(views.every(v=>v._glLost),'Rust per-chart cap evicts all charts');
  const totalBudget=host.sharedResourceBytes()+budget*100n;
  const recovery=views[0].watchDashboardResourceBudget(worker,totalBudget);
  await recovery.settled;await new Promise(r=>setTimeout(r,100));await recovery.settled;
  check('all rebuilt');assert(views.every(v=>!v._glLost),'all rebuilt at larger explicit budget');
  const appendSpec=JSON.parse(JSON.stringify(spec)), trace=appendSpec.traces[0];
  const xm=appendSpec.columns[trace.x],ym=appendSpec.columns[trace.y];
  const ox=new Float32Array(buf,xm.byte_offset,xm.len),oy=new Float32Array(buf,ym.byte_offset,ym.len);
  const appended=new ArrayBuffer((ox.length+oy.length+2)*4),ax=new Float32Array(appended,0,ox.length+1),ay=new Float32Array(appended,ax.byteLength,oy.length+1);
  ax.set(ox);ay.set(oy);ax[ox.length]=(0.25-Number(xm.offset||0))*Math.abs(Number(xm.scale||1));ay[oy.length]=(0.9-Number(ym.offset||0))*Math.abs(Number(ym.scale||1));
  xm.byte_offset=0;xm.len=ax.length;ym.byte_offset=ax.byteLength;ym.len=ay.length;trace.n_points=ax.length;
  for(const v of views)v._applyAppend({spec:appendSpec,affected:[trace.id]},[appended]);
  await recovery.settled;await new Promise(r=>setTimeout(r,100));await recovery.settled;
  check('32 appends');assert(views.every(v=>!v._glLost && v.gpuTraces[0].n===4),'append canonical rebuild');
  const wait=async predicate=>{const end=performance.now()+10000;while(!predicate()){assert(performance.now()<end,'lifecycle timeout');await new Promise(r=>setTimeout(r,25));}};
  host.canvas.addEventListener('webglcontextlost',()=>allocated.clear(),{once:true});
  const extension=host.gl.getExtension('WEBGL_lose_context');extension.loseContext();
  await wait(()=>host.lost);extension.restoreContext();
  await wait(()=>!host.lost && views.every(v=>!v._glLost));
  await recovery.settled;check('context restored');await gpuCapture('restored');
  // Resize/DPR keeps the previous picture until the next complete pass.
  const resized=views[3];resized._ctxIo?.disconnect();resized.fluid=true;resized.fluidH=true;resized._resize(300,300,true);
  resized._drawNow();resized._pickAt(10,10);
  await recovery.settled;check('DPR backing growth');
  for(let i=0;i<views.length;i++) { views[i]._ctxVisible=i%2===0;views[i].root.parentElement.style.display=views[i]._ctxVisible?"":"none";host.dashboardResourceChanged(views[i]); }
  await recovery.settled;check('hide show');
  for(let i=0;i<4;i++){views[i].destroy();const holder=document.createElement('div');grid.append(holder);views[i]=xy.renderStandalone(holder,{...spec,width:150,height:150},buf);}
  await recovery.settled;await new Promise(r=>setTimeout(r,100));await recovery.settled;check('rapid replacement');
  recovery.dispose();
  for(const v of views)v.destroy();
  assert(allocated.size===0,'all buffers/textures deleted including host');
  worker.dispose();
  return {charts:32,budget:String(budget),rows,remainingAllocations:allocated.size};
})()
