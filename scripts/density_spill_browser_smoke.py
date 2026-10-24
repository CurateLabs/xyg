"""Bounded colored-spill browser continuity proof (dossier §§5/27/28/29/32b).

Uses the host workload's actual mapped source and windows. This produces separate browser evidence; the standalone command remains <=1M.
The supervised authority worker may borrow its existing actual 100M figure.
"""

from __future__ import annotations

import argparse
import base64
import gc
import json
import os
import re
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "python"))

from benchmarks import _density_spill as spill  # noqa: E402
from benchmarks.environment import collect_environment_metadata  # noqa: E402

# These hooks precede renderStandalone, including first-payload/LUT/pick uploads.
# Unknown storage formats/APIs fail closed instead of silently undercounting.
GL_AUDIT = r"""
function auditNextChart() {
  const original = HTMLCanvasElement.prototype.getContext,
    contexts = new Map();
  HTMLCanvasElement.prototype.getContext = function(...a) {
    const gl = original.apply(this, a);
    if (a[0] === 'webgl2' && gl && !contexts.has(gl)) contexts.set(gl, ownedGL(gl));
    return gl;
  };
  return {
    restore() {
      HTMLCanvasElement.prototype.getContext = original;
    },
    for (gl) {
      if (!contexts.has(gl)) throw Error('initial instrumentation missing');
      return contexts.get(gl);
    }
  };
}

function ownedGL(gl) {
  const assert = (ok, msg) => {
    if (!ok) throw Error(msg);
  };
  const objects = new Map(),
    events = [];
  let phase = 'initial',
    next = 0,
    peak = 0,
    lost = false;
  const check = () => assert(!gl.isContextLost() && gl.getError() === gl.NO_ERROR, 'owned GL error/context loss');
  const record = (r, op) => {
    events.push({
      id: r.id,
      op,
      bytes: r.bytes
    });
    peak = Math.max(peak, [...objects.values()].reduce((n, r) => n + (r.deleted ? 0 : r.bytes), 0));
  };
  const wrap = (name, fn) => {
    const original = gl[name].bind(gl);
    gl[name] = (...a) => fn(original, a);
  };
  for (const kind of ['Texture', 'Buffer']) {
    wrap('create' + kind, (fn, a) => {
      const obj = fn(...a);
      check();
      assert(obj, 'owned creation failed');
      const r = {
        id: ++next,
        kind: kind.toLowerCase(),
        category: phase,
        bytes: 0,
        logicalBytes: 0,
        deleted: false,
        levels: {}
      };
      objects.set(obj, r);
      record(r, 'create');
      return obj;
    });
    wrap('delete' + kind, (fn, [obj]) => {
      const r = objects.get(obj);
      if (obj) assert(r && !r.deleted, 'unowned/repeated explicit deletion');
      const result = fn(obj);
      check();
      if (r) {
        r.deleted = true;
        record(r, 'delete');
      }
      return result;
    });
  }
  const texture = target => {
    assert(target === gl.TEXTURE_2D, 'unsupported owned texture target');
    const r = objects.get(gl.getParameter(gl.TEXTURE_BINDING_2D));
    assert(r && !r.deleted, 'unowned texture storage');
    return r;
  };
  const cell = (internal, format, type) => {
    if ((internal === gl.RGBA8 || internal === gl.RGBA) && format === gl.RGBA && type === gl.UNSIGNED_BYTE) return 4;
    if (internal === gl.R8 && format === gl.RED && type === gl.UNSIGNED_BYTE) return 1;
    throw Error('unsupported owned texture format ' + [internal, format, type]);
  };
  wrap('texImage2D', (fn, a) => {
    assert(a.length === 9, 'unsupported owned texture overload');
    const r = texture(a[0]),
      bytes = a[3] * a[4] * cell(a[2], a[6], a[7]);
    assert(Number.isSafeInteger(bytes) && bytes >= 0 && a[5] === 0, 'owned texture extent');
    const result = fn(...a);
    check();
    r.levels[a[1]] = bytes;
    r.bytes = Object.values(r.levels).reduce((n, v) => n + v, 0);
    record(r, 'storage');
    return result;
  });
  wrap('texStorage2D', (fn, a) => {
    const r = texture(a[0]),
      c = a[2] === gl.RGBA8 ? 4 : a[2] === gl.R8 ? 1 : 0;
    assert(c && a[1] > 0, 'unsupported owned immutable format');
    const result = fn(...a);
    check();
    r.levels = {};
    for (let i = 0; i < a[1]; i++) r.levels[i] = Math.max(1, a[3] >> i) * Math.max(1, a[4] >> i) * c;
    r.bytes = Object.values(r.levels).reduce((n, v) => n + v, 0);
    record(r, 'storage');
    return result;
  });
  for (const name of ['texImage3D', 'texStorage3D', 'compressedTexImage2D', 'compressedTexImage3D', 'generateMipmap', 'copyTexImage2D']) wrap(name, () => {
    throw Error('unsupported owned storage API ' + name);
  });
  wrap('bufferData', (fn, a) => {
    const bindings = new Map([
      [gl.ARRAY_BUFFER, gl.ARRAY_BUFFER_BINDING],
      [gl.ELEMENT_ARRAY_BUFFER, gl.ELEMENT_ARRAY_BUFFER_BINDING],
      [gl.COPY_READ_BUFFER, gl.COPY_READ_BUFFER_BINDING],
      [gl.COPY_WRITE_BUFFER, gl.COPY_WRITE_BUFFER_BINDING],
      [gl.PIXEL_PACK_BUFFER, gl.PIXEL_PACK_BUFFER_BINDING],
      [gl.PIXEL_UNPACK_BUFFER, gl.PIXEL_UNPACK_BUFFER_BINDING],
      [gl.UNIFORM_BUFFER, gl.UNIFORM_BUFFER_BINDING],
      [gl.TRANSFORM_FEEDBACK_BUFFER, gl.TRANSFORM_FEEDBACK_BUFFER_BINDING]
    ]);
    assert(bindings.has(a[0]), 'unsupported owned buffer target');
    const r = objects.get(gl.getParameter(bindings.get(a[0])));
    assert(r && !r.deleted, 'unowned buffer storage');
    const result = fn(...a);
    check();
    r.logicalBytes = gl.getBufferParameter(a[0], gl.BUFFER_SIZE);
    assert(Number.isSafeInteger(r.logicalBytes) && r.logicalBytes >= 0, 'owned buffer extent');
    r.bytes = Math.ceil(r.logicalBytes / 256) * 256;
    record(r, 'storage');
    return result;
  });
  const label = (obj, category) => {
    const r = objects.get(obj);
    if (r) r.category = category;
  };
  const inventory = g => {
    for (const t of (g._tileTextures || new Map()).values()) {
      label(t.tex, 'tiles');
      const r = objects.get(t.tex);
      assert(r && !r.deleted && r.bytes === t.w * t.h * (t.rgba ? 4 : 1), 'actual tile storage differs');
    }
    const bytes = [...objects.values()].filter(r => r.category === 'tiles' && !r.deleted).reduce((n, r) => n + r.bytes, 0);
    assert(bytes === g._tileStats.gpuBytes && bytes <= 8 * 512 * 512 * 4, 'owned keyed tile budget');
    return bytes;
  };
  const deleted = () => {
    check();
    assert([...objects.values()].every(r => r.deleted), 'owned explicit deletion missing ' + JSON.stringify([...objects.values()].filter(r => !r.deleted)));
  };
  const extension = gl.getExtension.bind(gl);
  gl.getExtension = name => {
    const ext = extension(name);
    if (name === 'WEBGL_lose_context' && ext && !ext.__ownedWrapped) {
      const lose = ext.loseContext.bind(ext);
      ext.loseContext = () => {
        deleted();
        lost = true;
        return lose();
      };
      ext.__ownedWrapped = true;
    }
    return ext;
  };
  const contains = (root, seen = new Set()) => {
    if (objects.has(root)) return true;
    if (!root || typeof root !== 'object' || seen.has(root) || ArrayBuffer.isView(root) || root instanceof ArrayBuffer) return false;
    seen.add(root);
    if (root instanceof Map) return [...root.values()].some(x => contains(x, seen));
    if (root instanceof Set) return [...root].some(x => contains(x, seen));
    return Object.values(root).some(x => contains(x, seen));
  };
  return {
    objects,
    events,
    label,
    inventory,
    set phase(value) {
      phase = value;
    },
    finish(v, g) {
      assert(!v.gl && !contains(g) && !contains(v), 'destroy retained owned resource references');
      assert([...objects.values()].every(r => r.deleted), 'owned explicit deletion missing');
      if (!lost) check();
      const resources = [...objects.values()].map(({
          levels,
          ...r
        }) => r),
        live = new Map();
      let tilePeakBytes = 0;
      for (const e of events) {
        live.set(e.id, e.op === 'delete' ? 0 : e.bytes);
        tilePeakBytes = Math.max(tilePeakBytes, resources.filter(r => r.category === 'tiles').reduce((n, r) => n + (live.get(r.id) || 0), 0));
      }
      assert(tilePeakBytes <= 8 * 512 * 512 * 4, 'transient keyed tile budget exceeded');
      const categories = Object.fromEntries(['initial', 'LUT', 'pick', 'chart', 'oracle', 'tiles'].map(category => [category, {
        created: resources.filter(r => r.category === category).length,
        deleted: resources.filter(r => r.category === category && r.deleted).length
      }]));
      const count = kind => resources.filter(r => r.kind === kind).length;
      return {
        createdTextures: count('texture'),
        deletedTextures: count('texture'),
        createdBuffers: count('buffer'),
        deletedBuffers: count('buffer'),
        uploads: events.filter(e => e.op === 'storage' && resources.find(r => r.id === e.id).kind === 'texture').length,
        remainingTextures: 0,
        peakInstrumentedBytes: peak,
        tilePeakBytes,
        categories,
        resources,
        events,
        explicitDeletionBeforeContextLoss: true,
        noReferences: true,
        noGLError: true
      };
    }
  };
}
"""

BROWSER_PROOF = r"""
(async()=>{
 const assert=(ok,msg)=>{if(!ok)throw Error(msg);};
 const sleep=ms=>new Promise(r=>setTimeout(r,ms));
 const digest=async bytes=>Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',bytes)),x=>x.toString(16).padStart(2,'0')).join('');
 const differences=(a,b)=>{assert(a.length===b.length,'pixel extent');let changed=0,max=0;for(let i=0;i<a.length;i++){const d=Math.abs(a[i]-b[i]);changed+=d>0;max=Math.max(max,d);}return {changedBytes:changed,maxError:max};};
 const captures={},runs={};
 for(const mode of ['cached','fetch-all','normal']) {
  const host=document.createElement('div');document.body.append(host);
  const hooks=auditNextChart();
  let v;try{v=xy.renderStandalone(host,structuredClone(input.spec),Uint8Array.from(atob(input.blob),c=>c.charCodeAt(0)));}finally{hooks.restore();}
  const g=v.gpuTraces[0],gl=v.gl,audit=hooks.for(gl);
  audit.label(v.pickTex,'pick');for(const tex of v._lutCache.values())audit.label(tex,'LUT');audit.phase='chart';
  assert(gl&&g.tier==='density','public density not admitted');
  const normal=mode==='normal';
  if(!normal)v._prefersReducedMotion=()=>true;
  // Resize the real chart, including its plot layout, to the shared 512² request.
  v.fluid=true;v.fluidH=true;
  for(let i=0;i<3;i++)v._resize(v.size.w+512-v.plot.w,v.size.h+512-v.plot.h);
  assert(Math.round(v.plot.w)===512&&Math.round(v.plot.h)===512,'plot must be 512 square');
  // Step presentation frames explicitly; network waits cannot race a cached
  // fallback paint ahead of the reply. Product fade/source selection runs in
  // _drawNow unchanged; neither density aliases nor inventories are invented.
  if(!normal){cancelAnimationFrame(v._raf);v._raf=null;v.draw=()=>{};}
  let clock=1000,requests=0,inflight,lastRaw,lastMessage;
  if(!normal)v._now=()=>clock;
  // Bounded first-payload policy truthfully emits exact/bin2d, without tile
  // discovery metadata. Bootstrap with a real public density_view XYDT reply;
  // admission itself enables the product's binary inventory request path.
  v._onKernelMsg({...input.seed.message,type:'density_update',seq:v.seq},[Uint8Array.from(atob(input.seed.raw),c=>c.charCodeAt(0))]);
  assert(g._tileCapable,'native bootstrap not admitted');audit.inventory(g);
  const adoptions=[],normalFrames=[];let normalDraws=[];
  if(normal){
   assert(!v._prefersReducedMotion(),'normal cadence requires actual non-reduced-motion browser');
   const drawNow=v._drawNow,drawDensity=v._drawDensity;
   v._drawDensity=function(gg,d,o=1){if(d?.tileSet)normalDraws.push({level:d.level,opacity:o,keys:d.tileSet.map(t=>t.key),sourceAlive:d.tileSet.every(t=>gl.isTexture(t.tex)&&[...g._tileTextures.values()].some(s=>s.tex===t.tex))});return drawDensity.call(this,gg,d,o);};
   v._drawNow=function(...a){normalDraws=[];const result=drawNow.apply(this,a);const p=readPixels(),outgoing=g._densitySwitchPrev;normalFrames.push({at:performance.now(),clock:v._now(),clockEnd:performance.now(),drawn:normalDraws,level:g._tileLevel,outgoingKeys:outgoing?.tileSet?.map(t=>t.key)||[],outgoingLevel:outgoing?.level??null,retired:!outgoing,pixels:p});return result;};
  }
  v.comm={send(msg,buffers){if(msg.type!=='density_view')return;requests++;
   assert(msg.tile_cache===true&&buffers.length===1&&!msg.keys,'binary XYDC observations required');
   inflight=fetch(input.endpoint,{method:'POST',headers:{'content-type':'application/octet-stream','x-xyg-request':JSON.stringify({...msg,mode})},body:buffers[0]}).then(async r=>{
    assert(r.ok,'host request failed: '+await (r.ok?Promise.resolve(''):r.text()));
    lastMessage=JSON.parse(r.headers.get('x-xyg-reply'));lastRaw=await r.arrayBuffer();v._onKernelMsg(lastMessage,[lastRaw]);adoptions.push({at:performance.now(),level:g._tileLevel,seq:lastMessage.seq});
   });
  }};
  async function request(window,uncached) {
   clearTimeout(v._viewTimer);g._lastDensityReq=null;g._tileForceUncached=uncached;
   v.view=v._copyView({ranges:{x:window.slice(0,2),y:window.slice(2)}});
   const before=requests;v._scheduleViewRequest(v.view,{delay:0});
   for(let i=0;requests===before&&i<100;i++)await sleep(10);
   assert(requests===before+1,'one scripted request required');await inflight;clearTimeout(v._viewTimer);
   assert(g._tileTextures?.size>0&&!g._tileStats.resourceCoarsened&&!g._tileNeedsRefine,'tile frame refused/coarsened/unfinished');
   assert(g._tileStats.received===g._tileStats.uploads,'upload count differs');
   const tiles=[...g._tileTextures.values()],bytes=tiles.reduce((n,t)=>n+t.w*t.h*4,0);
   assert(tiles.every(t=>gl.isTexture(t.tex)&&audit.objects.get(t.tex)?.bytes===t.w*t.h*4),'actual texture ownership/extent');
   audit.inventory(g);
   assert(bytes===g._tileStats.gpuBytes&&bytes<=g._tileStats.budget,'GPU inventory budget');
   assert(gl.getError()===gl.NO_ERROR,'WebGL error after adoption');
   return {...g._tileStats,liveTextures:tiles.length,allocatedTileBytes:bytes};
  }
  function readPixels(){const p=new Uint8Array(v.canvas.width*v.canvas.height*4);gl.readPixels(0,0,v.canvas.width,v.canvas.height,gl.RGBA,gl.UNSIGNED_BYTE,p);assert(gl.getError()===gl.NO_ERROR,'readPixels error');return p;}
  function pixels(){v._drawNow();return readPixels();}
  function blank(){const draw=v._drawDensity;try{v._drawDensity=()=>{};return pixels();}finally{v._drawDensity=draw;}}
  function ink(p,b){let count=0,red=0,blue=0;for(let i=0;i<p.length;i+=4)if(p[i]!==b[i]||p[i+1]!==b[i+1]||p[i+2]!==b[i+2]||p[i+3]!==b[i+3]){count++;red+=p[i]>p[i+2]+20;blue+=p[i+2]>p[i]+20;}assert(count>100&&red>20&&blue>20,'blank or missing endpoint colors');return {densityPixels:count,redPixels:red,bluePixels:blue};}
  // Test-only seam oracle: stitch the native guttered RGBA planes into one
  // texture, removing tile boundaries without re-binning or recoloring data.
  async function seams(tiled,background) {
   const frame=g.density,tiles=frame.tileSet,dx=(tiles[0].xRange[1]-tiles[0].xRange[0])/tiles[0].w,dy=(tiles[0].yRange[1]-tiles[0].yRange[0])/tiles[0].h;
   const xr=[Math.min(...tiles.map(t=>t.xRange[0])),Math.max(...tiles.map(t=>t.xRange[1]))],yr=[Math.min(...tiles.map(t=>t.yRange[0])),Math.max(...tiles.map(t=>t.yRange[1]))];
   const w=Math.round((xr[1]-xr[0])/dx),h=Math.round((yr[1]-yr[0])/dy),rgba=new Uint8Array(w*h*4),seen=new Uint8Array(w*h);
   assert(w*h<=2048*2048,'seam oracle allocation bound');let overlappingCells=0;
   for(const t of tiles){assert(t.paintBytes?.length===t.w*t.h*4,'native color body missing');const ox=Math.round((t.xRange[0]-xr[0])/dx),oy=Math.round((t.yRange[0]-yr[0])/dy);
    for(let y=0;y<t.h;y++)for(let x=0;x<t.w;x++){const dst=(oy+y)*w+ox+x,src=(y*t.w+x)*4;if(seen[dst]){overlappingCells++;for(let c=0;c<4;c++)assert(rgba[dst*4+c]===t.paintBytes[src+c],'gutter mismatch');}else{rgba.set(t.paintBytes.subarray(src,src+4),dst*4);seen[dst]=1;}}
   }
   assert(seen.every(Boolean)&&overlappingCells>0,'no continuous gutter coverage');
   audit.phase='oracle';const tex=gl.createTexture();audit.phase='chart';gl.bindTexture(gl.TEXTURE_2D,tex);gl.texImage2D(gl.TEXTURE_2D,0,gl.RGBA8,w,h,0,gl.RGBA,gl.UNSIGNED_BYTE,rgba);
   gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_MIN_FILTER,gl.LINEAR);gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_MAG_FILTER,gl.LINEAR);gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_WRAP_S,gl.CLAMP_TO_EDGE);gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_WRAP_T,gl.CLAMP_TO_EDGE);
   const draw=v._drawDensity;
   let mono;try{v._drawDensity=function(gg,d,o){return draw.call(this,gg,d===frame?{...tiles[0],tileSet:null,tex,w,h,xRange:xr,yRange:yr,clipRange:null,normMax:frame.normMax}:d,o);};mono=pixels();}finally{v._drawDensity=draw;gl.deleteTexture(tex);}
   const edgeX=[...new Set(tiles.flatMap(t=>t.clipRange.slice(0,2)))].filter(x=>x>v.view.x0&&x<v.view.x1),edgeY=[...new Set(tiles.flatMap(t=>t.clipRange.slice(2)))].filter(y=>y>v.view.y0&&y<v.view.y1);
   const scale=v.canvas.width/v.size.w,xs=edgeX.map(x=>(v.plot.x+(x-v.view.x0)/(v.view.x1-v.view.x0)*v.plot.w)*scale),ys=edgeY.map(y=>v.canvas.height-(v.plot.y+(1-(y-v.view.y0)/(v.view.y1-v.view.y0))*v.plot.h)*scale);
   let examined=0,densityPixels=0,maxError=0;
   for(let y=0;y<v.canvas.height;y++)for(let x=0;x<v.canvas.width;x++)if((xs.some(s=>Math.abs(x+.5-s)<=2)||ys.some(s=>Math.abs(y+.5-s)<=2))&&x>=v.plot.x*scale&&x<(v.plot.x+v.plot.w)*scale&&y>=v.canvas.height-(v.plot.y+v.plot.h)*scale&&y<v.canvas.height-v.plot.y*scale){examined++;const i=(y*v.canvas.width+x)*4;let marked=false;for(let c=0;c<4;c++){maxError=Math.max(maxError,Math.abs(tiled[i+c]-mono[i+c]));marked||=tiled[i+c]!==background[i+c];}densityPixels+=marked;}
   assert(examined>0&&densityPixels>20&&maxError<=2,'seam discontinuity '+JSON.stringify({examined,densityPixels,maxError}));
   return {method:'native-gutters-to-monolithic-texture',width:w,height:h,overlappingCells,edgeX,edgeY,examinedPixels:examined,densityPixels,maxError,tolerance:2,monolithicPixelSha256:await digest(mono),wholeImage:differences(tiled,mono)};
  }
  const samples=[];
  for(let index=-1;index<input.windows.length;index++) {
   const step=index<0?{kind:'seed',window:input.windows[0].window}:input.windows[index];
   const previousOwned=new Set([...(g._tileTextures||new Map()).values()].map(t=>t.tex)),oldLevel=g._tileLevel;
   const normalStart=normalFrames.length,adoptionStart=adoptions.length,startedAt=performance.now();
   if(!normal)v._prefersReducedMotion=()=>!(mode==='cached'&&step.kind==='zoom');
   const stats=await request(step.window,mode==='fetch-all');
   if(index>=0)assert(Math.abs(stats.level-oldLevel)===(step.kind==='zoom'?1:0),'scripted adjacent level contract');
   if(normal){
    const deadline=performance.now()+5000;
    while(performance.now()<deadline&&(normalFrames.length===normalStart||!normalFrames.at(-1).retired||normalFrames.at(-1).at<adoptions.at(-1).at))await sleep(10);
    const frames=normalFrames.slice(normalStart),adoption=adoptions.slice(adoptionStart);
    assert(frames.length&&frames.at(-1).retired&&frames.at(-1).at>=adoption[0]?.at,'normal RAF did not settle after async adoption');
    assert(adoption.length===1&&adoption[0].level===stats.level,'normal async adoption missing');
    for(const frame of frames){frame.pixelSha256=await digest(frame.pixels);frame.ink=ink(frame.pixels,new Uint8Array(frame.pixels.length));delete frame.pixels;assert(frame.drawn.length&&frame.drawn.every(d=>d.sourceAlive),'normal draw lost owned outgoing source');}
    const transitions=step.kind==='zoom'?frames.filter(f=>f.drawn.some(d=>d.level===oldLevel&&d.opacity>0&&d.opacity<1)&&f.drawn.some(d=>d.level===stats.level&&d.opacity>0&&d.opacity<1)):[];
    if(step.kind==='zoom')assert(transitions.length>0&&transitions.every(f=>f.drawn.filter(d=>d.level===oldLevel).every(d=>d.keys.every(k=>[...previousOwned].some(tex=>audit.objects.get(tex)&&[...g._tileTextures.values()].some(t=>t.key===k&&t.tex===tex))))),'normal adjacent transition/source missing');
    const end=frames.at(-1),cached=runs.cached.samples[index+1];
    assert(end.pixelSha256===cached.pixelSha256,'normal settled framebuffer differs from deterministic oracle '+index);
    samples.push({index,...step,stats,startedAt,adoption:adoption[0],frames:frames.map(({pixels,...f})=>f),transitionFrames:transitions.length,settledPixelSha256:end.pixelSha256,cachedPixelEquality:true});
    continue;
   }
   let fade=null;
   if(mode==='cached'&&step.kind==='zoom') {
    v._drawNow();const outgoing=g._densitySwitchPrev;assert(outgoing?.level===oldLevel&&outgoing.tileSet?.length>0,'actual adjacent outgoing source was not retained '+JSON.stringify({index,oldLevel,level:stats.level,outgoing:outgoing?.level,shown:g._shownDensity?.level,previous:g.prevDensity?.level,stats}));
    const source=outgoing.tileSet.map(t=>({key:t.key,tex:t.tex}));
    assert(source.every(t=>previousOwned.has(t.tex)),'outgoing source was not owned before reply');
    assert(source.every(t=>gl.isTexture(t.tex)&&[...g._tileTextures.values()].some(s=>s.tex===t.tex)),'outgoing source lost before fade');
    const start=pixels();clock+=70;
    const draw=v._drawDensity,drawn=[];
    try{v._drawDensity=function(gg,d,o=1){if(d?.tileSet)drawn.push({level:d.level,opacity:o});return draw.call(this,gg,d,o);};var middle=pixels();if(index===24)captures['adjacent-fade.png']=v.canvas.toDataURL('image/png');}finally{v._drawDensity=draw;}
    assert(drawn.some(d=>d.level===oldLevel&&d.opacity>0&&d.opacity<1)&&drawn.some(d=>d.level===stats.level&&d.opacity>0&&d.opacity<1),'both adjacent levels must actually draw');
    assert(source.every(t=>gl.isTexture(t.tex)),'fade source destroyed during draw');
    clock+=140;const end=pixels();assert(!g._densitySwitchPrev,'fade did not retire');
    const startMid=differences(start,middle),midEnd=differences(middle,end);
    assert(startMid.changedBytes>0&&midEnd.changedBytes>0,'fade pixels did not change');
    fade={sourceLevel:oldLevel,targetLevel:stats.level,sourceKeys:source.map(t=>t.key),drawn,sourceSurvived:true,startPixelSha256:await digest(start),middlePixelSha256:await digest(middle),endPixelSha256:await digest(end),startMid,midEnd,middleInk:ink(middle,blank()),retired:true};
   }
   v._prefersReducedMotion=()=>true;clock+=500;
   const p=pixels(),background=blank(),colorInk=ink(p,background),pixelSha256=await digest(p);
   const seam=await seams(p,background);
   const sample={index,...step,stats,pixelSha256,backgroundPixelSha256:await digest(background),...colorInk,seam,fade};
   if(mode==='fetch-all'){const cached=runs.cached.samples[index+1];assert(pixelSha256===cached.pixelSha256,'cached/fetch-all pixels differ at '+index);sample.cachedPixelEquality=true;}
   if(mode==='cached'&&(index===0||index===24)){pixels();captures[index===0?'pan.png':'zoom.png']=v.canvas.toDataURL('image/png');}
   samples.push(sample);
  }
  const ext=gl.getExtension('WEBGL_debug_renderer_info'),renderer={vendor:gl.getParameter(gl.VENDOR),renderer:gl.getParameter(gl.RENDERER),version:gl.getParameter(gl.VERSION),unmaskedVendor:ext?gl.getParameter(ext.UNMASKED_VENDOR_WEBGL):null,unmaskedRenderer:ext?gl.getParameter(ext.UNMASKED_RENDERER_WEBGL):null};
  v.destroy();const gpu=audit.finish(v,g),before=audit.events.length;
  v._onKernelMsg(lastMessage,[lastRaw]);await sleep(30);
  assert(audit.events.length===before,'stale reply allocated owned resources');audit.finish(v,g);gpu.staleReplyEvents=0;
  runs[mode]={samples,renderer,canvas:[v.canvas.width,v.canvas.height],gpu,destroyed:true,lateReplyIgnored:true};host.remove();
 }
 assert(runs.cached.samples.reduce((n,s)=>n+s.stats.received,0)<runs['fetch-all'].samples.reduce((n,s)=>n+s.stats.received,0),'cache did not reduce transfers');
 return {runs,captures,userAgent:navigator.userAgent,devicePixelRatio};
})()
"""


def guard(points: int, chunk: int, timeout: float) -> None:
    spill.guard(points, False, {}, timeout, 12, 4)
    if not 1 <= chunk <= 1_000_000:
        raise ValueError("chunk must be within 1..1M")


RENDERER_PROBE = r"""
(async()=>{const gl=document.createElement('canvas').getContext('webgl2');
if(!gl)throw Error('WebGL2 unavailable');const ext=gl.getExtension('WEBGL_debug_renderer_info');
const renderer={vendor:gl.getParameter(gl.VENDOR),renderer:gl.getParameter(gl.RENDERER),version:gl.getParameter(gl.VERSION),unmaskedVendor:ext?gl.getParameter(ext.UNMASKED_VENDOR_WEBGL):null,unmaskedRenderer:ext?gl.getParameter(ext.UNMASKED_RENDERER_WEBGL):null};
gl.clearColor(.25,.5,.75,1);gl.clear(gl.COLOR_BUFFER_BIT);const p=new Uint8Array(4);gl.readPixels(0,0,1,1,gl.RGBA,gl.UNSIGNED_BYTE,p);
if(gl.isContextLost()||gl.getError()!==gl.NO_ERROR||p[3]!==255)throw Error('renderer preflight GL failure');
return {renderer,contextLost:false,readback:[...p],userAgent:navigator.userAgent,devicePixelRatio};})()
"""


def renderer_guard(renderer: dict, gpu_info: dict, mode: str) -> None:
    if mode not in {"software", "hardware"}:
        raise ValueError("colored browser GL must be software or hardware")
    if not all(
        isinstance(renderer.get(k), str) and renderer[k].strip()
        for k in ("vendor", "renderer", "version", "unmaskedVendor", "unmaskedRenderer")
    ):
        raise ValueError("missing actual WebGL vendor/version/unmasked renderer")
    if not renderer["version"].startswith("WebGL 2.0"):
        raise ValueError("actual WebGL2 context/version required")
    actual = renderer["unmaskedRenderer"]
    software = bool(re.search(r"swiftshader|llvmpipe|softpipe|software|lavapipe", actual, re.I))
    if mode == "software" and not software:
        raise ValueError("software request differs from actual renderer")
    if mode == "hardware":
        features = gpu_info.get("gpu", {}).get("featureStatus", {})
        if software or not re.search(r"Apple M4", actual) or not re.search(r"Metal", actual):
            raise ValueError("hardware requires actual Apple M4 Metal accelerated WebGL: " + actual)
        # Chromium can publish a single WebGL feature status. The successful
        # webgl2 context/version/readback proves API version; Browser GPU status
        # supplies acceleration. An explicit webgl2 status must agree too.
        if features.get("webgl") != "enabled" or (
            "webgl2" in features and features["webgl2"] != "enabled"
        ):
            raise ValueError("hardware requires Browser GPU accelerated WebGL feature status")


class RendererAdmissionError(ValueError):
    def __init__(self, evidence: dict):
        super().__init__(evidence["failure"])
        self.evidence = evidence


def run_browser(
    page: str,
    chromium: str,
    timeout: float,
    gl_mode: str = "software",
    *,
    check_renderer: bool = True,
) -> dict:
    from xyg._chromium import ChromiumSession

    deadline = time.monotonic() + timeout

    def remaining() -> float:
        value = deadline - time.monotonic()
        if value <= 0:
            raise TimeoutError("colored browser probe deadline exceeded")
        return value

    with ChromiumSession(
        chromium, gl=gl_mode, sandbox=False, launch_timeout_s=min(30, remaining())
    ) as session:
        _, sid, path = session._page_session(page, remaining())
        session._call(
            "Page.navigate", {"url": path.as_uri()}, session_id=sid, timeout_s=remaining()
        )
        session._wait_event("Page.loadEventFired", session_id=sid, timeout_s=remaining())
        reply = session._call(
            "Runtime.evaluate",
            {"expression": "window.proof", "awaitPromise": True, "returnByValue": True},
            session_id=sid,
            timeout_s=remaining(),
        )
        if reply.get("exceptionDetails"):
            raise RuntimeError(f"browser proof failed: {reply['exceptionDetails']}")
        result = reply["result"]["value"]
        result["requested_gl"] = gl_mode
        result["hardware_context"] = (
            {
                key: os.environ.get(key)
                for key in (
                    "GITHUB_REPOSITORY",
                    "GITHUB_WORKFLOW_REF",
                    "GITHUB_WORKFLOW_SHA",
                )
            }
            if gl_mode == "hardware"
            else None
        )
        result["gpu_info"] = session._call("SystemInfo.getInfo", timeout_s=remaining())
        renderers = (
            [r["renderer"] for r in result["runs"].values()]
            if "runs" in result
            else [result["renderer"]]
        )
        if check_renderer:
            for renderer in renderers:
                renderer_guard(renderer, result["gpu_info"], gl_mode)
        result["cdp_version"] = session._call("Browser.getVersion", timeout_s=remaining())
        result["pid"] = session._proc.pid
        result["pgid"] = os.getpgid(session._proc.pid)
    assert session._proc.poll() is not None and not Path(session._tmp.name).exists()
    result["process_reaped"] = True
    result["profile_removed"] = True
    return result


def run_existing(
    *,
    fig,
    sources,
    source,
    spec,
    buffers,
    domain,
    journey,
    spill_file,
    chromium: str,
    timeout: float,
    socket_parent: Path,
    authority: bool = False,
    gl_mode: str = "software",
    preflight: dict | None = None,
) -> dict:
    """Borrow one live host figure/store; never allocate or release canonical data.

    Called only after the host kernel timer has finished. Packed first paint is
    a bounded repack of those exact split buffers, not another figure/compile.
    The caller owns source/store lifetime and process-group supervision.
    """
    spill.guard(len(sources[0]), authority, dict(os.environ), timeout, 12, 4)
    if authority and os.getpgrp() != os.getpid():
        raise ValueError("authority browser must run inside the supervised session leader")
    import copy

    from xyg import interaction

    trace = fig.traces[0]
    store = interaction._tile_store_of(trace)
    assert store and trace._pyr_colored
    assert journey == spill.windows(domain)
    mapped = {"before_browser": spill.mapping_inventory(fig, sources)}
    seed_message, seed_replies = fig.density_view(
        trace.id, *journey[0]["window"], 512, 512, tile_cache=spill.control(None)
    )
    seed_pool, seed_frame = spill.parse_frame(seed_replies[0], {})
    records, errors = [], []
    pools = {"cached": dict(seed_pool), "fetch-all": dict(seed_pool), "normal": dict(seed_pool)}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def do_OPTIONS(self):
            self.send_response(204)
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Headers", "content-type,x-xyg-request")
            self.end_headers()

        def do_POST(self):
            try:
                req = json.loads(self.headers["x-xyg-request"])
                length = int(self.headers["Content-Length"])
                assert 32 <= length <= 32 + 256 * 12
                control = self.rfile.read(length)
                assert req["tile_cache"] is True and "keys" not in req
                assert req["w"] == req["h"] == spill.SCREEN
                mode = req["mode"]
                assert mode in pools and len(records) < 99
                assert mode == (
                    "cached"
                    if len(records) < 33
                    else "fetch-all"
                    if len(records) < 66
                    else "normal"
                )
                index = sum(r["mode"] == mode for r in records) - 1
                expected = journey[max(index, 0)]["window"]
                window = [req[k] for k in ("x0", "x1", "y0", "y1")]
                assert window == expected, "browser changed scripted source window"
                msg, replies = fig.density_view(
                    trace.id,
                    *window,
                    spill.SCREEN,
                    spill.SCREEN,
                    tile_cache=control,
                )
                assert len(replies) == 1 and msg["traces"][0]["density"]["tile_frame"] == 0
                raw = replies[0]
                pools[mode], frame = spill.parse_frame(raw, pools[mode])
                assert frame["flags"] == 1
                records.append(
                    {
                        "mode": mode,
                        "index": index,
                        "window": window,
                        "control_sha256": spill.supervisor._sha256(control),
                        "control_base64": base64.b64encode(control).decode(),
                        **frame,
                        "stats": spill.stats(store),
                    }
                )
                reply = {"type": "density_update", "seq": req["seq"], **msg}
                self.send_response(200)
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Access-Control-Expose-Headers", "x-xyg-reply")
                self.send_header("x-xyg-reply", json.dumps(reply))
                self.send_header("Content-Type", "application/octet-stream")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)
            except Exception as exc:
                errors.append(repr(exc))
                self.send_error(500, str(exc))

    server = HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    cleanup = {}
    try:
        packed = copy.deepcopy(spec)
        assert packed.pop("buffer_layout") == "split"
        offsets, at = [], 0
        for buffer in buffers:
            offsets.append(at)
            at += len(buffer)
        for column in packed["columns"]:
            column["byte_offset"] += offsets[column.pop("buf")]
        blob = b"".join(buffers)
        inputs = {
            "spec": packed,
            "blob": base64.b64encode(blob).decode(),
            "windows": journey,
            "seed": {"message": seed_message, "raw": base64.b64encode(seed_replies[0]).decode()},
            "endpoint": f"http://127.0.0.1:{server.server_port}/",
        }
        page = (
            "<!doctype html><div id=chart></div><script>"
            + (ROOT / "python/xyg/static/standalone.js").read_text()
            + "</script><script>const input="
            + json.dumps(inputs)
            + ";"
            + GL_AUDIT
            + "window.proof="
            + BROWSER_PROOF
            + ";</script>"
        )
        # Chromium profile remains under the worker-owned temp tree; only its
        # Unix singleton socket uses the shorter, existing parent.
        with patch.dict(os.environ, {"TMPDIR": str(socket_parent.absolute())}):
            browser = run_browser(page, chromium, timeout, gl_mode)
        browser["preflight"] = preflight
        browser["capture_sha256"] = {
            name: spill.supervisor._sha256(base64.b64decode(encoded.split(",", 1)[1]))
            for name, encoded in browser["captures"].items()
        }
        assert not errors and len(records) == 99
        for record in records:
            sample = browser["runs"][record["mode"]]["samples"][record["index"] + 1]
            assert sample["window"] == record["window"]
            assert sample["stats"]["allocatedTileBytes"] == record["gpu_bytes"]
            assert sample["stats"]["level"] == record["level"]
            assert sample["stats"]["received"] == record["transferred_tiles"]
        mapped["after_browser"] = spill.mapping_inventory(fig, sources)
        return {
            "schema_version": 2,
            "report_kind": "density-colored-spill-browser-companion",
            "scope": "same-source-real-browser-owned-resources-and-normal-cadence",
            "status": "ok",
            "point_count": len(sources[0]),
            "source": source,
            "domain": domain,
            "windows": journey,
            "bootstrap": seed_frame,
            "spill_file": spill_file,
            "initial_payload": {
                "split_spec_sha256": spill.supervisor._sha256(spill.supervisor._json_bytes(spec)),
                "split_buffer_sha256": [spill.supervisor._sha256(b) for b in buffers],
                "spec_sha256": spill.supervisor._sha256(spill.supervisor._json_bytes(packed)),
                "blob_sha256": spill.supervisor._sha256(blob),
                "blob_bytes": len(blob),
            },
            "mapping_inventory": mapped,
            "decisions": {
                "presentation": "deterministic oracle plus separate product RAF/monotonic-clock journey; readback is not production FPS",
                "native_tile_bootstrap": True,
                "base_dim": trace._pyr_base_dim,
                "first_payload_binning": spec["traces"][0]["density"]["binning"],
                "first_payload_reduction": spec["traces"][0]["density"]["reduction"],
                "screen": [512, 512],
                "tile_budget_bytes": spill.TILE_BUDGET,
            },
            "browser": browser,
            "requests": records,
            "cleanup": cleanup,
        }
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
        cleanup["server_stopped"] = not thread.is_alive()
        assert cleanup["server_stopped"]


def run_control(
    points: int,
    chunk: int,
    chromium: str,
    work_root: Path,
    timeout: float,
    gl_mode: str = "software",
) -> dict:
    guard(points, chunk, timeout)  # Standalone can never allocate above 1M.
    import xyg
    from xyg import interaction, kernels

    work_root.mkdir(parents=True, exist_ok=True)
    preflight = renderer_preflight(chromium, gl_mode, work_root, min(timeout, 30))
    cleanup = {}
    old_budget, old_tempdir = interaction.PYRAMID_RESIDENT_BYTES, tempfile.tempdir
    sources = ()
    fig = trace = store = None
    with tempfile.TemporaryDirectory(prefix="density-spill-browser-", dir=work_root) as name:
        tmp = Path(name)
        try:
            tempfile.tempdir = str(tmp)
            with patch.dict(os.environ, {"TMPDIR": str(tmp.resolve())}):
                x, y, color, source = spill.generate(tmp, points, chunk)
                sources = (x, y, color)
                for key, item in source["columns"].items():
                    assert spill.file_hash(tmp / f"{key}.f64") == item["sha256"]
                with patch.object(interaction, "PYRAMID_MIN_POINTS", 1):
                    interaction.sync_tile_budget(spill.TILE_BUDGET)
                    fig = xyg.scatter_chart(
                        xyg.scatter(
                            x,
                            y,
                            color=color,
                            color_domain=(0, 1),
                            colormap=spill.COLORMAP,
                            opacity=1,
                            density=True,
                            pyramid_spill=True,
                        ),
                        width=640,
                        height=640,
                    ).figure()
                    trace = fig.traces[0]
                    interaction._ensure_pyramid(trace)
                    spec, buffers = fig.build_payload_split()
                    store = interaction._tile_store_of(trace)
                    paths = list(tmp.glob("xy-tiles-*.xyts"))
                    assert len(paths) == 1
                    spill_file = {
                        "bytes": paths[0].stat().st_size,
                        "sha256": spill.file_hash(paths[0]),
                    }
                    domain = [trace.x.min, trace.x.max, trace.y.min, trace.y.max]
                    domain[1] += (domain[1] - domain[0]) * 1e-9
                    domain[3] += (domain[3] - domain[2]) * 1e-9
                    report = run_existing(
                        fig=fig,
                        sources=sources,
                        source=source,
                        spec=spec,
                        buffers=buffers,
                        domain=domain,
                        journey=spill.windows(domain),
                        spill_file=spill_file,
                        chromium=chromium,
                        timeout=timeout,
                        socket_parent=work_root,
                        gl_mode=gl_mode,
                        preflight=preflight,
                    )
                    report.update(
                        {
                            "report_kind": "density-colored-spill-browser-control",
                            "scope": "bounded-real-browser-control",
                            "authority": False,
                            "count_color_oracle": spill.count_color_oracle(
                                sources, store, domain, trace._pyr_base_dim, chunk
                            ),
                        }
                    )
                    environment = collect_environment_metadata(
                        chromium=chromium, xy_backend="native"
                    )
                    report["environment"] = environment
                    report["provenance"] = spill.provenance(environment)
                    report["provenance"]["browser_harness_sha256"] = spill.file_hash(Path(__file__))
                    report["provenance"]["chromium_sha256"] = spill.file_hash(
                        Path(chromium).resolve()
                    )
                    cleanup.update(report["cleanup"])
                    report["cleanup"] = cleanup
        finally:
            if trace is not None:
                interaction._free_pyramid(trace)
            trace = fig = None
            gc.collect()
            cleanup["store_released"] = store is None or kernels.tile_store_stats(store) is None
            cleanup["spill_files_remaining"] = [p.name for p in tmp.rglob("xy-tiles-*.xyts")]
            for mapping in sources:
                mapping._mmap.close()
            cleanup["mappings_closed"] = all(m._mmap.closed for m in sources)
            interaction.sync_tile_budget(old_budget)
            cleanup["tile_budget_restored"] = old_budget == interaction.PYRAMID_RESIDENT_BYTES
            tempfile.tempdir = old_tempdir
    cleanup["temp_tree_removed"] = not tmp.exists()
    assert all(v is True or v == [] for v in cleanup.values())
    return report


def renderer_preflight(chromium: str, gl_mode: str, work_root: Path, timeout: float = 30) -> dict:
    work_root.mkdir(parents=True, exist_ok=True)
    page = "<!doctype html><script>window.proof=" + RENDERER_PROBE + ";</script>"
    with patch.dict(os.environ, {"TMPDIR": str(work_root.absolute())}):
        result = run_browser(page, chromium, timeout, gl_mode, check_renderer=False)
    try:
        renderer_guard(result["renderer"], result["gpu_info"], gl_mode)
    except ValueError as exc:
        result.update(status="failed", failure=str(exc))
        raise RendererAdmissionError(result) from exc
    result["status"] = "ok"
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gl", choices=("software", "hardware"), default="software")
    parser.add_argument("--preflight-only", action="store_true")
    parser.add_argument("--points", type=int, default=16384)
    parser.add_argument("--chunk-points", type=int, default=16384)
    parser.add_argument("--chromium", required=True, help="explicit Chrome/Chromium executable")
    parser.add_argument(
        "--work-root", type=Path, required=True, help="owned on-disk temporary parent"
    )
    parser.add_argument("--timeout", type=float, default=300)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.preflight_only:
        try:
            report = renderer_preflight(
                args.chromium, args.gl, args.work_root, min(args.timeout, 30)
            )
        except RendererAdmissionError as exc:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(exc.evidence, indent=2) + "\n")
            raise
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2) + "\n")
        return
    report = run_control(
        args.points, args.chunk_points, args.chromium, args.work_root, args.timeout, args.gl
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    captures = report["browser"].pop("captures")
    report["captures"] = {}
    for name, encoded in captures.items():
        path = args.output.parent / name
        path.write_bytes(base64.b64decode(encoded.split(",", 1)[1]))
        report["captures"][name] = {"bytes": path.stat().st_size, "sha256": spill.file_hash(path)}
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(f"ok: {args.points} mapped colored rows, 32 windows, report {args.output}")


if __name__ == "__main__":
    main()
