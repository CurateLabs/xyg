#!/usr/bin/env node
// Probe the actual production Reflex fixture started by the documented command.
import {chromium} from 'playwright';
import {writeFile} from 'node:fs/promises';
const origin=process.env.XYG_GEO_REFLEX_ORIGIN??'http://127.0.0.1:8143';
const browser=await chromium.launch({...(process.env.XYG_CHROMIUM?{executablePath:process.env.XYG_CHROMIUM}:{}),args:['--use-gl=swiftshader','--enable-unsafe-swiftshader','--ignore-gpu-blocklist']});
const page=await browser.newPage({viewport:{width:1200,height:900}}),errors=[],external=[];
page.on('pageerror',e=>errors.push(e.message));
await page.route('**/*',r=>{const u=new URL(r.request().url());if(!['http:','https:'].includes(u.protocol)||u.origin===origin)return r.continue();external.push(u.href);return r.abort();});
await page.addInitScript(()=>{const Native=window.WebSocket;window.__geoSockets=[];window.WebSocket=class extends Native{constructor(...args){super(...args);window.__geoSockets.push(this);}};});
try{
 await page.goto(origin);
 await page.waitForFunction(()=>window.__xy_views?.get('geo-native-overview-host'),{},{timeout:45000});
 const result=await page.evaluate(async()=>{
  const view=window.__xy_views.get('geo-native-overview-host');await view.ready;
  if(view.identity.time.instant!==-9223372036854775808n||document.querySelectorAll('[data-domain-cell]').length!==32)throw Error('native overview identity/count companion mismatch');
  const checkCounts=async()=>{if(document.querySelectorAll('[data-domain-cell]').length!==32||!document.querySelector('[data-xy-overview-counts] [role=status]').textContent.includes('spatial refinement pending'))throw Error('native overview companion missing');let rejected=false;try{view.pick({x:400,y:300});}catch{rejected=true;}if(!rejected)throw Error('overview granted feature pick');};
  await checkCounts();await view.update({operation:8,args:[0,0],sequence:3n,cameraRevision:3n,timeRevision:3n,stateRevision:1n,time:{kind:0}});if(view.identity.time.kind!==0||view.identity.sequence!==3n)throw Error('live update mismatch');let blue=0;
  for(let attempt=0;attempt<100&&!blue;attempt++){await new Promise(r=>requestAnimationFrame(r));const canvas=view.view.canvas;let pixels;if(view.view._glHost)pixels=view.view._present2d.getImageData(0,0,canvas.width,canvas.height).data;else{const gl=view.view.gl;pixels=new Uint8Array(gl.drawingBufferWidth*gl.drawingBufferHeight*4);gl.readPixels(0,0,gl.drawingBufferWidth,gl.drawingBufferHeight,gl.RGBA,gl.UNSIGNED_BYTE,pixels);}for(let i=0;i<pixels.length;i+=4)if(pixels[i+2]>pixels[i]+40&&pixels[i+2]>pixels[i+1])blue++;}
  if(!blue)throw Error('actual Reflex painter contains no overview domain pixels');
  const owner=view.owner,oldCount=window.__geoSockets.length;
  const socket=window.__geoSockets.find(s=>s.readyState===WebSocket.OPEN);if(!socket)throw Error('actual websocket absent');socket.close();
  for(let i=0;i<200;i++){if(window.__geoSockets.length>oldCount&&window.__geoSockets.at(-1).readyState===WebSocket.OPEN)break;await new Promise(r=>setTimeout(r,50));}
  if(window.__geoSockets.length<=oldCount||window.__geoSockets.at(-1).readyState!==WebSocket.OPEN)throw Error('websocket failed to reconnect');
  await checkCounts();if(window.__xy_views.get('geo-native-overview-host')!==view||view.owner!==owner)throw Error('reconnect replaced immutable owner');
  await view.dispose();if(view.owner!==0n||view.pending.size!==0)throw Error('browser release failed');
  return {bluePixels:blue,identity:'exact u64/i64MIN',domainCompanion:true,noFeaturePick:true,websocketReconnect:true,sameFrameOnReconnect:true,releaseAcknowledged:true,canvasesAfterRelease:document.querySelectorAll('#geo-native-overview-host canvas').length};
 });
 if(external.length||errors.length)throw Error(JSON.stringify({external,errors}));
 const report={ok:true,journey:'actual production Reflex + React client + socket.io binary namespace + Rust native overview painter',browser:browser.version(),liveCamera:true,signedTimeUpdate:true,...result,external,errors};
 if(process.env.XYG_GEO_OVERVIEW_REFLEX_REPORT)await writeFile(process.env.XYG_GEO_OVERVIEW_REFLEX_REPORT,JSON.stringify(report,null,2)+'\n');console.log(JSON.stringify(report));
}catch(e){throw Error(JSON.stringify({error:e.message,errors,body:await page.locator('body').innerText()}));}finally{await browser.close();}
