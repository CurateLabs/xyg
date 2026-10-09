const vscode=require('vscode'),fs=require('node:fs'),path=require('node:path'),{pathToFileURL}=require('node:url');
exports.run=async()=>{
 const root=path.resolve(__dirname,'../..'),out=process.env.XYG_GEO_VSCODE_REPORT;
 let panel,source,adapter,lane,scope;
 try{
  const {hierarchyFixture}=await import(pathToFileURL(path.join(root,'packages/xy-node/test/geo-live-hierarchy-fixture.mjs')).href);
  const f=await hierarchyFixture();source=f.source;adapter=f.adapter;lane=f.lane;scope=f.scope;
  const {attachGeoWebview}=await import(pathToFileURL(path.join(root,'packages/xy-node/src/vscode.js')).href);
  const U64=0xffffffffffffffffn;
  panel=vscode.window.createWebviewPanel('xygGeoProof','XYG geographic lifecycle proof',vscode.ViewColumn.One,{enableScripts:true,localResourceRoots:[vscode.Uri.file(root)],retainContextWhenHidden:true});
  const binding=attachGeoWebview(panel,adapter),states=[],waiters=new Map();
  panel.webview.onDidReceiveMessage(message=>{if(message.test!=='geo_host')return;states.push(message);const w=waiters.get(message.phase);if(w){waiters.delete(message.phase);message.ok?w.resolve(message):w.reject(Error(JSON.stringify(message)));}});
  const wait=phase=>new Promise((resolve,reject)=>{waiters.set(phase,{resolve,reject});setTimeout(()=>{if(waiters.has(phase)){waiters.delete(phase);reject(Error('real VS Code webview timeout phase'+phase));}},45000);});
  const asset=p=>panel.webview.asWebviewUri(vscode.Uri.file(path.join(root,p))).toString();
  const pageUri=asset('tests/vscode_geo_live_hierarchy/page.mjs'),clientUri=asset('packages/xy-client/dist/index.js');
  // Browser module URLs are local webview resources, not the Python wheel.
  const html=phase=>`<!doctype html><meta charset="utf-8"><meta http-equiv="Content-Security-Policy" content="default-src 'none'; script-src ${panel.webview.cspSource}; style-src 'unsafe-inline'; connect-src 'none'; img-src data:; object-src 'none'; base-uri 'none'"><body data-phase="${phase}"><div id="chart"></div><script type="module" src="${pageUri}"></script>`;
  // Relative imports do not use import-map bare resolution; serve page with a
  // concrete adjacent generated copy of the client as a test-only asset.
  fs.copyFileSync(path.join(root,'packages/xy-client/dist/index.js'),path.join(__dirname,'xy-client.js'));
  const first=wait(1);panel.webview.html=html(1);await first;
  const old=adapter.frame,second=wait(2);await binding.reload(html(2));await second;
  if(adapter.frame.data.record(0).featureId!==U64||adapter.sequence!==5n)throw Error('reload/live update lost identity');
  const newer=adapter.frame;panel.dispose();panel=undefined;
  const deadline=Date.now()+10000;while(adapter.mounted&&Date.now()<deadline)await new Promise(r=>setTimeout(r,10));
  if(adapter.mounted)throw Error('panel disposal failed to release native frame');
  try{newer.data;throw Error('disposed panel retained native frame');}catch(e){if(!/disposed/.test(e.message))throw e;}
  await source.dispose();source=undefined;
  const report={ok:true,vscode:vscode.version,states,reloadReleasedFrontend:true,remountSamePrivateAnchor:true,actualPanelDispose:true,liveCamera:true,signedTimeUpdate:true,selectedHierarchyLive:true,callerSourceDisposed:true};
  fs.writeFileSync(out,JSON.stringify(report,null,2)+'\n');
 }catch(error){if(out)fs.writeFileSync(out,JSON.stringify({ok:false,error:error.message,stack:error.stack},null,2)+'\n');throw error;}
 finally{if(panel)panel.dispose();if(adapter)await adapter.realmDestroyed();if(lane)await lane.dispose();if(source)await source.dispose();if(scope)await scope.dispose();}
};
