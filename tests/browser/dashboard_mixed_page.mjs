(async () => {
  const {createXygWasmWorker, applyWasmDashboardResourceBudget: apply} = await import('/index.js');
  const worker=createXygWasmWorker({workerUrl:'/wasm-worker.js',wasm:'/xyg-wasm.wasm'});
  await worker.ready;
  const assert=(value,message)=>{if(!value)throw new Error(message);};
  const wait=async predicate=>{const end=performance.now()+10000;while(!predicate()){
    assert(performance.now()<end,'mixed dashboard lifecycle timeout');
    await new Promise(resolve=>setTimeout(resolve,10));
  }};
  // Observe actual driver calls, independently of the owner's storage ledger.
  const allocations=new Map(), proto=WebGL2RenderingContext.prototype;
  for(const name of ['bufferData','texImage2D','texStorage2D','deleteBuffer','deleteTexture']) {
    const original=proto[name];
    proto[name]=function(...args) {
      const result=original.apply(this,args);
      if(name==='bufferData') {
        const binding=args[0]===this.ELEMENT_ARRAY_BUFFER?this.ELEMENT_ARRAY_BUFFER_BINDING:this.ARRAY_BUFFER_BINDING;
        allocations.set(this.getParameter(binding),this.getBufferParameter(args[0],this.BUFFER_SIZE));
      } else if(name.startsWith('tex')) {
        assert([this.R8,this.RGBA,this.RGBA8,this.RGBA8UI,this.R32UI].includes(args[2]),'known oracle texture format');
        allocations.set(this.getParameter(this.TEXTURE_BINDING_2D),args[3]*args[4]*(args[2]===this.R8?1:4));
      } else allocations.delete(args[0]);
      return result;
    };
  }
  const grid=document.getElementById('chart'); grid.replaceChildren();
  grid.style.cssText='display:grid;grid-template-columns:repeat(8,180px)';
  const views=[], rows=[], keys=[], clicks=[];
  for(let i=0;i<32;i++) {
    const payload=mixedPayloads[i%mixedPayloads.length], holder=document.createElement('div');
    grid.append(holder);
    const bytes=Uint8Array.from(atob(payload.buffer),c=>c.charCodeAt(0));
    const view=xy.renderStandalone(holder,payload.spec,bytes.buffer);
    view.canvas.dataset.mixedChart=String(i);
    view._drawNow(); view._ctxIo?.disconnect(); view._ctxVisible=i<16;
    if(i>=16)holder.style.display='none';
    views.push(view);
  }
  const host=views[0]._glHost, line=views[0], scatter=views[1], peer=views[6];
  assert(views.every(view=>view._glHost===host),'mixed views share one context');
  assert(host.storageSnapshot().contexts===1,'one actual mixed dashboard context');
  assert(new Set(views.flatMap(view=>view.gpuTraces.map(g=>g.trace.kind))).size>=5,'five distinct painted mark families');
  const actual=()=>[...allocations.values()].reduce((sum,bytes)=>sum+BigInt(bytes),0n);
  const check=label=>{
    const snapshot=host.storageSnapshot();
    assert(snapshot.logicalBytes===actual(),label+': independent allocation oracle');
    rows.push({label,bytes:String(actual()),objects:snapshot.objects});
  };
  const pixels=view=>Array.from(view._present2d.getImageData(0,0,view.canvas.width,view.canvas.height).data).join(',');
  const mask=view=>{
    const g=view.gpuTraces[0];
    assert(g.selActive && g.selBuf,'rebuilt selection has an active GPU mask');
    const result=new Float32Array(g.n);
    view.gl.bindBuffer(view.gl.ARRAY_BUFFER,g.selBuf);
    view.gl.getBufferSubData(view.gl.ARRAY_BUFFER,0,result);
    return Array.from(result);
  };
  let selectionEvents=0;
  for(const view of [line,scatter])view.root.addEventListener('xy:select',()=>selectionEvents++);
  scatter.root.xy.applyState({selection:{range:{x0:-.1,x1:1.1,y0:-.1,y1:1.1}}});
  line.root.xy.applyState({selection:{polygon:[[-.1,-.1],[1.1,-.1],[1.1,1.1],[-.1,1.1]]}});
  for(const view of [line,scatter])view._drawNow();
  assert(JSON.stringify(mask(scatter))==='[1,1,0]' && JSON.stringify(mask(line))==='[1,1,0]','authored independent selected-row oracle');
  scatter.canvas.addEventListener('keydown',event=>keys.push({key:event.key,trusted:event.isTrusted}));
  scatter.root.addEventListener('xy:click',event=>clicks.push({trace:event.detail.trace,index:event.detail.index}));
  await gpuTabTo('1');
  await gpuKey('Home');await gpuKey('ArrowRight');await gpuKey('Enter');await gpuKey('Escape');
  assert(clicks.length===1 && clicks[0].index===1 && clicks[0].trace===scatter.gpuTraces[0].trace.id,'trusted keyboard canonical row before eviction '+JSON.stringify({clicks,keys,hover:scatter._hoverTarget&&{trace:scatter._hoverTarget.trace,index:scatter._hoverTarget.index},index:scatter._a11yPointIndex,interaction:scatter.spec.interaction}));
  for(const view of views)view._drawNow();
  const saved=views.map(pixels), identities=views.map(view=>view.gpuTraces.map(g=>g.trace.id));
  assert(saved.every(picture=>picture.split(',').some((value,index)=>index%4===3 && Number(value)>0)),'all five mark families paint actual pixels');
  const states=[line,scatter].map(view=>JSON.stringify(view.root.xy.state()));
  const eventsBefore=selectionEvents, keyboardBefore=scatter._a11yPointIndex;
  const snapshot=host.dashboardResourceSnapshot(), demand=snapshot.resources.reduce((sum,r)=>sum+r.derivedBytes,0n);
  const pressure=host.sharedResourceBytes()+demand/4n, broad=host.sharedResourceBytes()+demand*16n;
  await apply(worker,host,pressure);
  check('mixed pressure');
  assert(actual()+BigInt(host.canvas.width*host.canvas.height*4)<=pressure,'mixed global GPU bound');
  assert(views.some(v=>v._glLost) && views.some(v=>!v._glLost),'real partial whole-chart eviction');
  await apply(worker,host,broad,0n);
  assert(views.every(view=>view._glLost),'per-chart zero cap evicts all five families');
  for(let i=0;i<views.length;i++) {
    const view=views[i], surface=view._ctxSnapshot;
    assert(surface && Array.from(surface.getContext('2d').getImageData(0,0,surface.width,surface.height).data).join(',')===saved[i],'evicted saved pixels '+i);
    assert(view._pickAt(10,10)===null,'no stale mixed-family pick '+i);
  }
  check('all mixed evicted');
  await apply(worker,host,broad);
  await wait(()=>views.every(view=>!view._glLost));
  const verify=label=>{
    assert(JSON.stringify(mask(scatter))==='[1,1,0]' && JSON.stringify(mask(line))==='[1,1,0]',label+': exact selected GPU rows');
    for(let i=0;i<views.length;i++) {
      views[i]._drawNow();
      assert(JSON.stringify(views[i].gpuTraces.map(g=>g.trace.id))===JSON.stringify(identities[i]),label+': trace identities '+i);
      const after=pixels(views[i]);
      if(after!==saved[i]) {
        const beforeBytes=saved[i].split(',').map(Number), afterBytes=after.split(',').map(Number);
        const differences=[];for(let j=0;j<afterBytes.length;j++)if(beforeBytes[j]!==afterBytes[j] && differences.length<12)differences.push([j,beforeBytes[j],afterBytes[j]]);
        throw Error(label+': complete RGBA equality '+i+' '+JSON.stringify(differences));
      }
    }
    assert([line,scatter].every((view,i)=>JSON.stringify(view.root.xy.state())===states[i]),label+': durable state');
    assert(selectionEvents===eventsBefore,label+': no replayed selection callbacks');
    assert(scatter._a11yPointIndex===keyboardBefore && !peer._hoverTarget && !peer.gpuTraces[0].selActive,label+': keyboard and peer isolation');
    check(label);
  };
  verify('mixed readmitted');
  host.canvas.addEventListener('webglcontextlost',()=>allocations.clear(),{once:true});
  const extension=host.gl.getExtension('WEBGL_lose_context');extension.loseContext();
  await wait(()=>host.lost);extension.restoreContext();
  await wait(()=>!host.lost && views.every(view=>!view._glLost));
  verify('mixed context restored');
  assert(document.activeElement===scatter.canvas,'per-chart focus survives eviction and shared context loss');
  await gpuKey('ArrowRight');await gpuKey('Enter');await gpuKey('Escape');
  assert(clicks.length===2 && clicks[1].index===2 && clicks[1].trace===clicks[0].trace,'keyboard resumes at next canonical row after rebuild');
  assert(keys.length===7 && keys.every(event=>event.trusted),'all keyboard events are trusted');
  await gpuCapture('mixed-restored');
  for(const view of views)view.destroy();
  assert(allocations.size===0,'mixed-family teardown releases every actual buffer/texture');
  worker.dispose();
  return {charts:32,families:5,rows,keys,clicks,selectionMasks:[[1,1,0],[1,1,0]],remainingAllocations:allocations.size};
})()
