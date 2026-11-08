const vscode=require('vscode'),fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict'),{pathToFileURL}=require('node:url');
exports.run=async()=>{
 const root=path.resolve(__dirname,'../..'),out=process.env.XYG_GEO_VSCODE_REPORT,rows=[],waiters=new Map();let panel,f,host,binding,caller,h,unblock;
 const importFile=p=>import(pathToFileURL(path.join(root,p)).href);
 const bounded=async(promise,label)=>{let timer;try{return await Promise.race([promise,new Promise((_,reject)=>timer=setTimeout(()=>reject(Error('VS Code native gate did not complete: '+label)),45000))]);}finally{clearTimeout(timer);}};
 const wait=key=>new Promise((resolve,reject)=>{const timer=setTimeout(()=>{waiters.delete(key);reject(Error('VS Code test action did not complete: '+key));},45000);waiters.set(key,{resolve:value=>{clearTimeout(timer);waiters.delete(key);resolve(value);},reject:error=>{clearTimeout(timer);waiters.delete(key);reject(error);}});});
 try{
  const {mountedHierarchyFixture}=await importFile('packages/xy-node/test/geo-mounted-hierarchy-temporal-fixture.mjs');
  const {isHierarchyFrame}=await importFile('packages/xy-node/src/geo-hierarchy.js');
  const {attachGeoWebview}=await importFile('packages/xy-node/src/geo-webview.js');
  const {xyAbiVersion}=await importFile('packages/xy-node/src/native.js');
  const api=await importFile('packages/xy-node/src/index.js');
  f=await mountedHierarchyFixture();
  h=api.temporalControllerCreate({instanceId:41n,domainStart:-(1n<<63n),domainEnd:(1n<<63n)-1n,cursor:3n,window:0n,step:1n});
  panel=vscode.window.createWebviewPanel('xygMountedTemporal','XYG mounted temporal proof',vscode.ViewColumn.One,{enableScripts:true,localResourceRoots:[vscode.Uri.file(root)],retainContextWhenHidden:true});
  const actualPanel=panel;
  let holdPrepared=false,preparedEntered,releasePrepared;
  const forward={webview:{onDidReceiveMessage:actualPanel.webview.onDidReceiveMessage.bind(actualPanel.webview),async postMessage(envelope){
   if(holdPrepared&&envelope.message?.type==='geo_host'&&envelope.buffers?.[0]&&new DataView(envelope.buffers[0]).getUint32(8,true)===6){holdPrepared=false;preparedEntered();await new Promise(r=>releasePrepared=r);}
   return actualPanel.webview.postMessage(envelope);
  },get html(){return actualPanel.webview.html;},set html(value){actualPanel.webview.html=value;}},onDidDispose:actualPanel.onDidDispose.bind(actualPanel),dispose:()=>actualPanel.dispose()};
  host=attachGeoWebview(forward,f.adapter);binding=host.bindTemporal(h);api.temporalControllerSetCursor(h,7n);
  panel.webview.onDidReceiveMessage(message=>{
   if(message.test==='mounted-ready'){waiters.get('ready:'+message.phase)?.resolve(message);return;}
   if(message.test==='mounted-error'){for(const waiter of waiters.values())waiter.reject(Error(message.error));return;}
   if(message.test!=='mounted-temporal')return;
   if(message.ok){assert.ok(isHierarchyFrame(f.adapter.frame));assert.equal(f.adapter.frame.data.selection.id(0),0xffffffffffffffffn);}
   rows.push(message);const waiter=waiters.get(message.request);message.ok?waiter?.resolve(message):waiter?.reject(Error(JSON.stringify(message)));
  });
  const uri=panel.webview.asWebviewUri(vscode.Uri.file(path.join(__dirname,'page.mjs'))).toString();
  const html=phase=>`<!doctype html><meta charset="utf-8"><meta http-equiv="Content-Security-Policy" content="default-src 'none'; script-src ${panel.webview.cspSource}; style-src 'unsafe-inline'; connect-src 'none'; img-src data:; object-src 'none'; base-uri 'none'"><body data-phase="${phase}"><div id="chart" style="width:800px;height:600px"></div><script type="module" src="${uri}"></script>`;
  const ready=wait('ready:1');panel.webview.html=html('1');await ready;await binding.whenIdle();assert.equal(binding.error,undefined);assert.equal(f.adapter.frame.data.identity.time.instant,7n);
  const originalCurrent=f.source.current;caller=await f.adapter.frame.retain();
  let serial=0;const action=async kind=>{const request='action:'+ ++serial,pending=wait(request);assert.equal(await panel.webview.postMessage({action:kind,request}),true);return pending;};
  const first=await action('initial'),moved=await action('camera');assert.notEqual(first.centroid,moved.centroid);
  const camera=f.adapter.frame.data.identity.camera;
  // A genuine unfinished native read admits a newer controller state.
  const reader=f.source.hierarchyReadPage;let entered;const readEntered=new Promise(resolve=>entered=resolve),gate=new Promise(resolve=>unblock=resolve);
  f.source.hierarchyReadPage=async ticket=>{entered();await gate;return reader(ticket);};
  api.temporalControllerSetCursor(h,8n);await bounded(readEntered,'page read');api.temporalControllerSetCursor(h,9n);unblock();f.source.hierarchyReadPage=reader;await binding.whenIdle();assert.equal(binding.error,undefined);assert.equal(f.adapter.frame.data.identity.time.instant,9n);assert.deepEqual(f.adapter.frame.data.identity.camera,camera);const afterTime=await action('after-time');
  const good=f.adapter.frame;f.source.hierarchyReadPage=async()=>{throw Error('VS Code injected storage failure');};api.temporalControllerSetCursor(h,10n);await binding.whenIdle();assert.match(binding.error.message,/storage failure/);assert.equal(f.adapter.frame,good);const failurePaint=await action('failure-retained');assert.equal(failurePaint.rgbaSha256,afterTime.rgbaSha256);f.source.hierarchyReadPage=reader;
  await binding.dispose();api.temporalControllerSetRange(h,100000n,100001n);binding=host.bindTemporal(h,'range');await binding.whenIdle();assert.equal(binding.error,undefined);await action('empty');
  await binding.dispose();api.temporalControllerSetCursor(h,6n);binding=host.bindTemporal(h);await binding.whenIdle();const restoredPaint=await action('restored');assert.equal(restoredPaint.rgbaSha256,afterTime.rgbaSha256);
  if(process.env.XYG_GEO_VSCODE_CAPTURE_READY){
   fs.writeFileSync(process.env.XYG_GEO_VSCODE_CAPTURE_READY,'ready\n');const deadline=Date.now()+45000;
   while(!fs.existsSync(process.env.XYG_GEO_VSCODE_CAPTURE_READY+'.done')){if(Date.now()>deadline)throw Error('VS Code capture did not settle');await new Promise(resolve=>setTimeout(resolve,20));}
  }
  holdPrepared=true;const prepared=new Promise(r=>preparedEntered=r);api.temporalControllerSetCursor(h,12n);await bounded(prepared,'prepared reply');
  const abortedSequence=f.adapter.liveCandidate.sequenceFloor,acceptedSequence=f.adapter.sequence;assert.ok(abortedSequence>acceptedSequence);
  const close=binding.dispose();await bounded((async()=>{while(!binding.active.invalidated)await new Promise(r=>setImmediate(r));})(),'prepared invalidation');releasePrepared();await close;
  assert.equal(f.adapter.sequence,acceptedSequence);
  const remount=wait('ready:2');await host.reload(html('2'));await remount;
  api.temporalControllerSetCursor(h,23n);binding=host.bindTemporal(h);await binding.whenIdle();assert.equal(binding.error,undefined);assert.equal(f.adapter.frame.data.identity.time.instant,23n);assert.ok(f.adapter.sequence>abortedSequence);assert.ok(isHierarchyFrame(f.adapter.frame));assert.equal(f.adapter.frame.data.selection.id(0),0xffffffffffffffffn);const remountedPaint=await action('remounted');assert.equal(remountedPaint.rgbaSha256,restoredPaint.rgbaSha256);
  assert.equal(caller.data.record(0).featureId,0xffffffffffffffffn);assert.equal(f.source.current,originalCurrent);
  // Actual WebviewPanel disposal, while a native callback is still admitted.
  let disposedEntered;const disposedRead=new Promise(resolve=>disposedEntered=resolve),disposeGate=new Promise(resolve=>unblock=resolve);
  f.source.hierarchyReadPage=async ticket=>{disposedEntered();await disposeGate;return reader(ticket);};api.temporalControllerSetCursor(h,11n);await bounded(disposedRead,'disposal page read');panel.dispose();panel=undefined;unblock();await host.dispose();await binding.dispose();assert.equal(f.adapter.mounted,false);assert.equal(f.adapter.anchor,undefined);assert.equal(caller.data.record(0).featureId,0xffffffffffffffffn);await caller.dispose();await f.lane.dispose();await f.source.dispose();await f.scope.dispose();
  api.temporalControllerDestroy(h);h=undefined;
  fs.writeFileSync(out,JSON.stringify({ok:true,selectedHierarchy:true,nativeAbi:xyAbiVersion(),preparedAbortBeforeRemount:true,abortedSequence:String(abortedSequence),acceptedSequence:String(acceptedSequence),newSequence:String(f.adapter.sequence),privateHierarchyAuthority:true,completeRgbaFailureRetention:true,completeRgbaRemountRetention:true,programmaticCamera:true,vscode:vscode.version,node:process.version,platform:process.platform,rows,premountLatest:true,exactI64U64:true,cameraPreserved:true,unfinishedReadSuperseded:true,failureRetained:true,rangeAndCursor:true,rebind:true,reload:true,realPanelDisposeDuringRead:true,independentCaller:true,currentPublicationPreserved:true,allNativeOwnersClosed:true},null,2)+'\n');
 }catch(error){if(out)fs.writeFileSync(out,JSON.stringify({ok:false,error:error.message,stack:error.stack,rows},null,2)+'\n');throw error;}
 finally{unblock?.();panel?.dispose();if(host)await host.dispose();await caller?.dispose();if(f){await f.lane.dispose();await f.source.dispose();await f.scope.dispose();}if(h){const api=await importFile('packages/xy-node/src/index.js');api.temporalControllerDestroy(h);}}
};
