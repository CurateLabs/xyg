import assert from 'node:assert/strict';
import {readFile,writeFile} from 'node:fs/promises';
import {join} from 'node:path';
import {createHash} from 'node:crypto';
import {runGraphNotebookRegions} from '../../scripts/graph_notebook_region_journey.mjs';
export async function runDesktopGraphRegions({root,dir,graphFrame,ui,browser,executeCell,outputText,revealCell,captureActualViews,viewportRect,nativeHover,pendingAssets,network,hostAssets,expectedClient,inspectedSources,pageErrors,external}){
 await graphFrame.locator('[data-graph-steps]').nth(1).waitFor({timeout:45000});
 await captureActualViews();
 const usedClientSources=await graphFrame.locator('[data-graph-steps] canvas[role=img]').evaluateAll(canvases=>canvases.map(canvas=>globalThis.__xygInspectedViewSources.get(canvas)));
 assert.equal(usedClientSources.length,2);assert.ok(usedClientSources.every(pin=>pin?.exactClientSource&&pin.sha256===createHash('sha256').update(expectedClient).digest('hex')));
 const host=JSON.parse(await readFile(join(dir,'extension-state.json'),'utf8'));
 const frontend={kind:'vscode-jupyter',appName:host.appName,appHost:host.appHost,version:host.vscode,extensionId:host.extension.id,jupyterExtension:host.extension.version,node:host.node,notebookType:host.notebook.type,cellCount:host.notebook.cellCount,normalGuiMode:host.normalGuiMode};
 assert.equal(frontend.appName,'Visual Studio Code');assert.equal(frontend.appHost,'desktop');assert.equal(frontend.version,'1.103.2');assert.equal(frontend.jupyterExtension,'2025.7.0');assert.equal(frontend.cellCount,4);
 const kernel={name:'python3',firstExecution:host.executed[0].execution,readiness:'Actual execution summary; final kernel identity and idle state are verified through runner sidecars'};
 assert.equal(kernel.firstExecution.success,true);assert.ok(Number.isSafeInteger(kernel.firstExecution.executionOrder));
 let sequence=0;
 const cell=executeCell;
 const report=async()=>{await cell(1);const text=outputText(1);assert.ok(text.includes('XYG graph region report'));const value=JSON.parse(text.split('XYG graph region report')[1].trim());assert.equal(value.report_sequence,++sequence);await revealCell(0);return value;};
 const cleanup=async()=>{assert.ok(outputText(3).includes('XYG graph region cleanup'));const value=JSON.parse(outputText(3).split('XYG graph region cleanup')[1].trim());assert.equal(value.released,true);};
 const dpr=await graphFrame.evaluate(()=>devicePixelRatio);assert.equal(dpr,1);
 const result=await runGraphNotebookRegions({root,temp:dir,page:graphFrame,input:ui,surfaces:graphFrame.locator('[data-graph-steps]'),cell,report,cleanup,frontend,kernel,dpr,browser,errors:pageErrors,external,
  prepareCanvas:()=>revealCell(0),canvasBounds:viewportRect,screenshotCanvas:async(canvas,path)=>{await revealCell(0);return ui.screenshot({path,clip:await viewportRect(canvas)});},
  hoverCanvas:async canvas=>{await revealCell(0);const box=await canvas.evaluate(c=>({width:c.clientWidth,height:c.clientHeight}));await nativeHover(canvas,{x:box.width/2,y:box.height/2});},moveOffCanvas:()=>ui.mouse.move(5,5),
  paintCanvas:canvas=>canvas.evaluate(canvas=>{
   const view=globalThis.__xygActualViewForCanvas(canvas),gl=view.gl;
   if(view._glHost)throw Error('desktop proof must retain default direct WebGL');
   view._drawNow();gl.finish();const w=canvas.width,h=canvas.height,raw=new Uint8Array(w*h*4);gl.readPixels(0,0,w,h,gl.RGBA,gl.UNSIGNED_BYTE,raw);if(gl.getError()!==gl.NO_ERROR)throw Error('actual framebuffer read failed');
   const copy=document.createElement('canvas');copy.width=w;copy.height=h;const ctx=copy.getContext('2d'),image=ctx.createImageData(w,h);
   for(let y=0;y<h;y++)for(let x=0;x<w;x++){const src=(y*w+x)*4,dst=((h-1-y)*w+x)*4,a=raw[src+3];for(let c=0;c<3;c++)image.data[dst+c]=a>0&&a<255?Math.min(255,Math.round(raw[src+c]*255/a)):raw[src+c];image.data[dst+3]=a;}
   ctx.putImageData(image,0,0);return copy.toDataURL('image/png').split(',')[1];
  })});
 await Promise.all([...pendingAssets]);
 result.usedClientSources=usedClientSources;result.host=JSON.parse(await readFile(join(dir,'extension-state.json'),'utf8'));result.network=network;result.hostAssets=hostAssets;result.clientSha256=createHash('sha256').update(expectedClient).digest('hex');result.inspectedClientSources=inspectedSources;result.networkScope='Renderer requests only; allowlisted host bootstrap traffic; not offline or extension-host Node network audit';result.directPaintCapture='Synchronous existing _drawNow/readPixels, vertical flip and unpremultiplication; no preserveDrawingBuffer/default changes';
 await writeFile(join(dir,'report.json'),JSON.stringify(result,null,2)+'\n');console.log('actual VSCode graph regions complete');return result;
}
