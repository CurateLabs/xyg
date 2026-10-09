const vscode=require('vscode'),fs=require('node:fs'),path=require('node:path'),{pathToFileURL}=require('node:url');
exports.run=async()=>{
 const root=path.resolve(__dirname,'../..'),out=process.env.XYG_GEO_VSCODE_REPORT;
 let panel,source,adapter;
 try{
  const {fixture,budget,U64,I64}=await import(pathToFileURL(path.join(root,'packages/xy-node/test/geoscale-fixture.mjs')).href);
  const {RetainedGeoSource,geoChart,geoLayer,attachGeoWebview}=await import(pathToFileURL(path.join(root,'packages/xy-node/src/vscode.js')).href);
  const {encodeGeoScaleStyle}=await import(pathToFileURL(path.join(root,'packages/xy-node/src/geoscale.js')).href);
  const f=await fixture(),bytes=x=>Uint8Array.from(Buffer.from(x,'hex'));
  source=await RetainedGeoSource.create(bytes(f.manifest),async()=>bytes(f.chunk),{budget});
  const camera={crs:4326,worldWrap:true,centerX:0,centerY:0,zoom:0,width:800,height:600,bearing:0,pitch:0};
  const query={camera,reducedKind:0,maxCells:32768,previousDirect:true,sourceDigest:source.info.digest,generation:source.info.generation,layerId:U64,cameraRevision:U64,timeRevision:U64,layerRevision:U64,styleRevision:U64,stateRevision:U64,time:{kind:1,instant:I64},maxProjectedVertices:1000000n};
  const style=encodeGeoScaleStyle({fill:new Uint8Array([255,0,0,255]),stroke:new Uint8Array(4),strokeWidth:0,diameter:6,opacity:1,symbol:0});
  const chart=geoChart(geoLayer('points',{source,layerId:U64,query,sequence:1n,style}),{camera});
  adapter=chart.host();
  panel=vscode.window.createWebviewPanel('xygGeoProof','XYG geographic lifecycle proof',vscode.ViewColumn.One,{enableScripts:true,localResourceRoots:[vscode.Uri.file(root)],retainContextWhenHidden:true});
  const binding=attachGeoWebview(panel,adapter),states=[],waiters=new Map();
  panel.webview.onDidReceiveMessage(message=>{if(message.test!=='geo_host')return;states.push(message);const w=waiters.get(message.phase);if(w){waiters.delete(message.phase);message.ok?w.resolve(message):w.reject(Error(JSON.stringify(message)));}});
  const wait=phase=>new Promise((resolve,reject)=>{waiters.set(phase,{resolve,reject});setTimeout(()=>{if(waiters.has(phase)){waiters.delete(phase);reject(Error('real VS Code webview timeout phase'+phase));}},45000);});
  const asset=p=>panel.webview.asWebviewUri(vscode.Uri.file(path.join(root,p))).toString();
  const pageUri=asset('tests/vscode_geo_host/page.mjs'),clientUri=asset('packages/xy-client/dist/index.js');
  // Browser module URLs are local webview resources, not the Python wheel.
  const html=phase=>`<!doctype html><meta charset="utf-8"><meta http-equiv="Content-Security-Policy" content="default-src 'none'; script-src ${panel.webview.cspSource}; style-src 'unsafe-inline'; connect-src 'none'; img-src data:; object-src 'none'; base-uri 'none'"><body data-phase="${phase}"><div id="chart"></div><script type="module" src="${pageUri}"></script>`;
  // Relative imports do not use import-map bare resolution; serve page with a
  // concrete adjacent generated copy of the client as a test-only asset.
  fs.copyFileSync(path.join(root,'packages/xy-client/dist/index.js'),path.join(__dirname,'xy-client.js'));
  const first=wait(1);panel.webview.html=html(1);await first;
  const old=adapter.frame,second=wait(2);await binding.reload(html(2));await second;
  try{old.data;throw Error('reload failed to release old frame');}catch(e){if(!/disposed/.test(e.message))throw e;}
  const newer=adapter.frame;panel.dispose();panel=undefined;
  const deadline=Date.now()+10000;while(adapter.mounted&&Date.now()<deadline)await new Promise(r=>setTimeout(r,10));
  if(adapter.mounted)throw Error('panel disposal failed to release native frame');
  try{newer.data;throw Error('disposed panel retained native frame');}catch(e){if(!/disposed/.test(e.message))throw e;}
  await source.dispose();source=undefined;
  const report={ok:true,vscode:vscode.version,states,reloadReleasedOldFrame:true,actualPanelDispose:true};
  fs.writeFileSync(out,JSON.stringify(report,null,2)+'\n');
 }catch(error){if(out)fs.writeFileSync(out,JSON.stringify({ok:false,error:error.message,stack:error.stack},null,2)+'\n');throw error;}
 finally{if(panel)panel.dispose();if(adapter)await adapter.realmDestroyed();if(source)await source.dispose();}
};
