const vscode=require('vscode'),fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict'),{pathToFileURL}=require('node:url');
exports.run=async()=>{
 const root=path.resolve(__dirname,'../..'),out=process.env.XYG_GEO_VSCODE_REPORT,rows=[],waiters=new Map();let panel,f,host,binding,caller,h,unblock;
 const importFile=p=>import(pathToFileURL(path.join(root,p)).href);
 const wait=key=>new Promise((resolve,reject)=>{const timer=setTimeout(()=>{waiters.delete(key);reject(Error('VS Code test action did not complete: '+key));},45000);waiters.set(key,{resolve:value=>{clearTimeout(timer);waiters.delete(key);resolve(value);},reject:error=>{clearTimeout(timer);waiters.delete(key);reject(error);}});});
 try{
  const {mountedIndexedFixture}=await importFile('packages/xy-node/test/geo-mounted-indexed-temporal-fixture.mjs');
  const {attachGeoWebview}=await importFile('packages/xy-node/src/geo-webview.js');
  const api=await importFile('packages/xy-node/src/index.js');
  f=await mountedIndexedFixture({selected:process.env.XYG_GEO_SELECTED!=='0'});
  h=api.temporalControllerCreate({instanceId:41n,domainStart:-(1n<<63n),domainEnd:(1n<<63n)-1n,cursor:3n,window:0n,step:1n});
  panel=vscode.window.createWebviewPanel('xygMountedTemporal','XYG mounted temporal proof',vscode.ViewColumn.One,{enableScripts:true,localResourceRoots:[vscode.Uri.file(root)],retainContextWhenHidden:true});
  host=attachGeoWebview(panel,f.adapter);binding=host.bindTemporal(h);api.temporalControllerSetCursor(h,7n);
  panel.webview.onDidReceiveMessage(message=>{
   if(message.test==='mounted-ready'){waiters.get('ready:'+message.phase)?.resolve(message);return;}
   if(message.test==='mounted-error'){for(const waiter of waiters.values())waiter.reject(Error(message.error));return;}
   if(message.test!=='mounted-temporal')return;
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
  const reader=f.source.readPage;let entered;const readEntered=new Promise(resolve=>entered=resolve),gate=new Promise(resolve=>unblock=resolve);
  f.source.readPage=async ticket=>{entered();await gate;return reader(ticket);};
  api.temporalControllerSetCursor(h,8n);await readEntered;api.temporalControllerSetCursor(h,9n);unblock();f.source.readPage=reader;await binding.whenIdle();assert.equal(binding.error,undefined);assert.equal(f.adapter.frame.data.identity.time.instant,9n);assert.deepEqual(f.adapter.frame.data.identity.camera,camera);await action('after-time');
  const good=f.adapter.frame;f.source.readPage=async()=>{throw Error('VS Code injected storage failure');};api.temporalControllerSetCursor(h,10n);await binding.whenIdle();assert.match(binding.error.message,/storage failure/);assert.equal(f.adapter.frame,good);await action('failure-retained');f.source.readPage=reader;
  await binding.dispose();api.temporalControllerSetRange(h,100000n,100001n);binding=host.bindTemporal(h,'range');await binding.whenIdle();assert.equal(binding.error,undefined);await action('empty');
  await binding.dispose();api.temporalControllerSetCursor(h,6n);binding=host.bindTemporal(h);await binding.whenIdle();await action('restored');
  if(process.env.XYG_GEO_VSCODE_CAPTURE_READY){
   fs.writeFileSync(process.env.XYG_GEO_VSCODE_CAPTURE_READY,'ready\n');const deadline=Date.now()+45000;
   while(!fs.existsSync(process.env.XYG_GEO_VSCODE_CAPTURE_READY+'.done')){if(Date.now()>deadline)throw Error('VS Code capture did not settle');await new Promise(resolve=>setTimeout(resolve,20));}
  }
  const remount=wait('ready:2');await host.reload(html('2'));await remount;await binding.whenIdle();assert.equal(binding.error,undefined);assert.equal(f.adapter.frame.data.identity.time.instant,6n);await action('remounted');
  assert.equal(caller.data.record(0).featureId,0xffffffffffffffffn);assert.equal(f.source.current,originalCurrent);
  // Actual WebviewPanel disposal, while a native callback is still admitted.
  let disposedEntered;const disposedRead=new Promise(resolve=>disposedEntered=resolve),disposeGate=new Promise(resolve=>unblock=resolve);
  f.source.readPage=async ticket=>{disposedEntered();await disposeGate;return reader(ticket);};api.temporalControllerSetCursor(h,11n);await disposedRead;panel.dispose();panel=undefined;unblock();await host.dispose();await binding.dispose();assert.equal(f.adapter.mounted,false);assert.equal(f.adapter.anchor,undefined);assert.equal(caller.data.record(0).featureId,0xffffffffffffffffn);await caller.dispose();await f.source.dispose();await f.scope?.dispose();
  api.temporalControllerDestroy(h);h=undefined;
  fs.writeFileSync(out,JSON.stringify({ok:true,nativeAbi:(await importFile('packages/xy-node/src/native.js')).xyAbiVersion(),indexed:true,externalPageCount:f.pages.size,selected:!!f.scope,externalPageReads:f.pageReads(),canonicalFallbackReads:f.canonicalReads(),vscode:vscode.version,node:process.version,platform:process.platform,rows,premountLatest:true,exactI64U64:true,cameraPreserved:true,unfinishedReadSuperseded:true,failureRetained:true,rangeAndCursor:true,rebind:true,reload:true,realPanelDisposeDuringRead:true,independentCaller:true,currentPublicationPreserved:true,allNativeOwnersClosed:true},null,2)+'\n');
 }catch(error){if(out)fs.writeFileSync(out,JSON.stringify({ok:false,error:error.message,stack:error.stack,rows},null,2)+'\n');throw error;}
 finally{unblock?.();panel?.dispose();if(host)await host.dispose();await caller?.dispose();if(f){await f.source.dispose();await f.scope?.dispose();}if(h){const api=await importFile('packages/xy-node/src/index.js');api.temporalControllerDestroy(h);}}
};
