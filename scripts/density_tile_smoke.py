"""Native Rust → binary XYDT → browser tile-cache proof (stdlib only).

Run after cargo build --release and node js/build.mjs:
python3 scripts/density_tile_smoke.py /usr/bin/google-chrome-stable
"""

from __future__ import annotations

import base64
import ctypes
import hashlib
import importlib.util
import json
import platform
import struct
import threading
from array import array
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from render_smoke_nonumpy import ROOT, STATIC, build_payload, run_probe


def main() -> None:
    module_spec = importlib.util.spec_from_file_location(
        "tile_smoke_abi", ROOT / "python/xyg/_abi_generated.py"
    )
    abi = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(abi)
    lib = ctypes.CDLL(str(ROOT / "target/release/libxyg_core.so"))
    abi.bind_generated_abi(lib)
    n = 32768
    xs = array("d", ((i * 17 % n) / n for i in range(n)))
    ys = array("d", ((i * 31 % n) / n for i in range(n)))
    rgba = array(
        "B", (v for i in range(n) for v in ((240, 50, 40, 128) if i % 3 else (20, 90, 230, 200)))
    )

    def pointer(a):
        return ctypes.c_void_p(a.buffer_info()[0])

    stores = {}
    for name in ("count", "color"):
        if name == "color":
            p = lib.xyg_pyramid_build_color(
                pointer(xs), pointer(ys), n, None, pointer(rgba), None, 0, 0.0, 1.0, 0.0, 1.0, 1024
            )
        else:
            p = lib.xyg_pyramid_build(pointer(xs), pointer(ys), n, 0.0, 1.0, 0.0, 1.0, 1024)
        stores[name] = lib.xyg_pyramid_spill(p)
        lib.xyg_pyramid_free(p)
        assert stores[name]
    records = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def do_OPTIONS(self):
            self.send_response(204)
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Headers", "content-type,x-xyg-request")
            self.end_headers()

        def do_POST(self):
            req = json.loads(self.headers["x-xyg-request"])
            control = self.rfile.read(int(self.headers["Content-Length"]))
            assert req["tile_cache"] is True and "keys" not in req
            control_owner = ctypes.create_string_buffer(control)
            bounded_w, bounded_h = ctypes.c_int32(), ctypes.c_int32()
            assert (
                lib.xyg_screen_shape(
                    req["w"], req["h"], ctypes.byref(bounded_w), ctypes.byref(bounded_h)
                )
                == 1
            )
            width, height = bounded_w.value, bounded_h.value
            capacity = lib.xyg_tile_store_paint_capacity(width, height)
            out = (ctypes.c_ubyte * capacity)()
            result = lib.xyg_tile_store_paint(
                stores[req["case"]],
                req["x0"],
                req["x1"],
                req["y0"],
                req["y1"],
                width,
                height,
                0.65,
                ctypes.cast(control_owner, ctypes.c_void_p),
                len(control),
                ctypes.cast(out, ctypes.c_void_p),
                capacity,
            )
            assert 128 <= result <= capacity
            raw = bytes(out[:result])
            records.append(
                {
                    "case": req["case"],
                    "seq": req["seq"],
                    "requested_size": [req["w"], req["h"]],
                    "served_size": [width, height],
                    "bytes": result,
                    "level": struct.unpack_from("<I", raw, 8)[0],
                    "flags": struct.unpack_from("<I", raw, 12)[0],
                    "active": struct.unpack_from("<I", raw, 20)[0],
                    "fetches": struct.unpack_from("<I", raw, 24)[0],
                    "sha256": hashlib.sha256(raw).hexdigest(),
                }
            )
            self.send_response(200)
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Content-Type", "application/octet-stream")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    spec, blob = build_payload()
    trace = spec["traces"][3]
    trace["density"].pop("sample", None)
    trace["density"].update(
        {"x_range": [0.0, 1.0], "y_range": [0.0, 1.0], "tiles": {"spilled_bytes": 1}}
    )
    trace["style"] = {"color": "#3377cc", "opacity": 0.65}
    spec.update(
        {
            "traces": [trace],
            "graph": [],
            "width": 400,
            "height": 320,
            "x_axis": {"kind": "linear", "range": [0.0, 0.5]},
            "y_axis": {"kind": "linear", "range": [0.0, 0.5]},
        }
    )
    page = (
        """<!doctype html><title>pending</title><div id=chart></div><script>"""
        + (STATIC / "standalone.js").read_text()
        + "</script><script>\n"
    )
    page += (
        "const spec="
        + json.dumps(spec)
        + ";const blob=Uint8Array.from(atob('"
        + base64.b64encode(blob).decode()
        + "'),c=>c.charCodeAt(0));\n"
    )
    page += "const endpoint=" + json.dumps(f"http://127.0.0.1:{server.server_port}/") + ";\n"
    page += r"""
(async()=>{try{
 const output={};
 const assert=(ok,msg)=>{if(!ok)throw Error(msg);};
 const sleep=ms=>new Promise(r=>setTimeout(r,ms));
 for(const kind of ['count','color']) {
  const host=document.createElement('div');document.body.append(host);
  const local=JSON.parse(JSON.stringify(spec));
  if(kind==='color')local.traces[0].color={mode:'categorical',palette:['#f03228','#145ae6'],categories:['red','blue']};
  const v=xy.renderStandalone(host,local,blob),g=v.gpuTraces[0],gl=v.gl;
  v._prefersReducedMotion=()=>true;
  let uploads=0, creates=0, requests=0,lastRaw=null,lastMessage=null,lastRequest=null,inflight=Promise.resolve();
  const image=gl.texImage2D.bind(gl),create=gl.createTexture.bind(gl);
  gl.texImage2D=(...a)=>{uploads++;return image(...a);};
  gl.createTexture=(...a)=>{creates++;return create(...a);};
  v.comm={send(msg,buffers){if(msg.type!=='density_view')return;requests++;lastRequest=msg;
   assert(msg.tile_cache===true&&buffers.length===1&&!msg.keys,'observations must be raw binary');
   inflight=fetch(endpoint,{method:'POST',headers:{'content-type':'application/octet-stream','x-xyg-request':JSON.stringify({...msg,case:kind})},body:buffers[0]})
    .then(r=>r.arrayBuffer()).then(raw=>{
      lastRaw=raw;lastMessage={type:'density_update',seq:msg.seq,traces:[{id:g.trace.id,mode:'density',visible:999999,filter:msg.filter,density:{tile_frame:0}}]};
      v._onKernelMsg(lastMessage,[raw]);
    });
  }};
  async function request(win,uncached=false) {
   clearTimeout(v._viewTimer);g._lastDensityReq=null;g._tileForceUncached=uncached;
   v.view=v._copyView({ranges:{x:win.slice(0,2),y:win.slice(2)}});
   const before=requests;v._scheduleViewRequest(v.view,{delay:0});
   for(let i=0;requests===before&&i<100;i++)await sleep(10);
   assert(requests>before,'request not sent');await inflight;clearTimeout(v._viewTimer);
   v._drawNow();v._drawNow();return {...g._tileStats,requestUploads:uploads};
  }
  function pixels(){v._drawNow();const p=new Uint8Array(v.canvas.width*v.canvas.height*4);gl.readPixels(0,0,v.canvas.width,v.canvas.height,gl.RGBA,gl.UNSIGNED_BYTE,p);return p;}
  const ownedBuffer=()=>{const b=gl.createBuffer();gl.bindBuffer(gl.ARRAY_BUFFER,b);gl.bufferData(gl.ARRAY_BUFFER,new Float32Array([0]),gl.STATIC_DRAW);return b;};
  const staleBuffer=ownedBuffer(),fadeBuffer=ownedBuffer(),sharedBuffer=ownedBuffer();
  const shared={xBuf:sharedBuffer};g.sampleOverlay=shared;g.density.overlay={xBuf:fadeBuffer};
  const legacy=overlay=>({...g.density,tex:v._uploadGrid(new Float32Array([1]),1,1,1),overlay});
  g.densityCache.push(legacy({xBuf:staleBuffer}),legacy(shared));uploads=0;creates=0;
  const summarize=async p=>({alphaPixels:p.reduce((n,v,i)=>n+(i%4===3&&v>0?1:0),0),sha256:Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',p)),v=>v.toString(16).padStart(2,'0')).join('')});
  const densityInk=p=>{const draw=v._drawDensity;v._drawDensity=()=>{};const blank=pixels();v._drawDensity=draw;let ink=0;for(let i=0;i<p.length;i+=4)if(p.slice(i,i+4).some((v,j)=>v!==blank[i+j]))ink++;assert(ink>100,'density image blank');return ink;};
  const a=await request([0,.5,0,.5]);
  assert(a?.uploads>0,'initial tiles absent');
  assert(!gl.isBuffer(staleBuffer)&&!gl.isBuffer(fadeBuffer)&&gl.isBuffer(sharedBuffer),'legacy overlay ownership leaked or shared buffer destroyed');
  const before=uploads,b=await request([.25,.75,0,.5]);const cached=pixels();
  assert(b.received===b.uploads&&uploads-before===b.uploads,'upload count mismatch');
  const cachedInk=densityInk(cached),cachedCapture=await summarize(cached);
  assert(cachedCapture.alphaPixels>0,'cached alpha blank');
  const inside=await request([.3,.7,.05,.45]);assert(inside.received===0&&inside.uploads===0,'in-cache pan transferred pixels');
  await request([.25,.75,0,.5]);
  const fresh=await request([.25,.75,0,.5],true),oracle=pixels();
  const oracleInk=densityInk(oracle),oracleCapture=await summarize(oracle);
  assert(oracleCapture.alphaPixels>0,'uncached alpha blank');
  let different=0;for(let i=0;i<cached.length;i++)if(cached[i]!==oracle[i])different++;
  assert(different===0,'cached/uncached pixel mismatch '+different);
  assert(b.received<fresh.received,'pan did not reuse overlaps');
  assert(b.gpuBytes<=b.budget,'GPU budget exceeded');
  if(kind==='color') {
    const allocated=creates;v._setLegendHover({traces:[0],cat:0},{_xyItemRows:[]},null);const dimmed=pixels();
    assert(dimmed.some((p,i)=>p!==oracle[i]),'legend hover had no effect');
    v._clearLegendHover();const restored=pixels();
    assert(restored.every((p,i)=>p===oracle[i])&&creates===allocated,'tile legend dim restore/allocation regression');
  }
  await request([.25,.75,0,.5]);
  assert(g._tileStats.received===0,'malformed-format fixture must retain every tile');
  const stable=uploads,stableCreates=creates,stableSize=g._tileTextures.size,stableMap=g._tileTextures;
  const flip=lastRaw.slice(0),fd=new DataView(flip),flag=fd.getUint32(12,true),factor=(flag&1)?1/4:4;
  fd.setUint32(12,flag^1,true);fd.setUint32(64,fd.getUint32(64,true)*factor,true);fd.setUint32(68,fd.getUint32(68,true)*factor,true);
  v._onKernelMsg({...lastMessage,seq:v.seq},[flip]);
  assert(uploads===stable&&creates===stableCreates&&g._tileTextures===stableMap,'retained format flip adopted');
  const bad=lastRaw.slice(0);new DataView(bad).setUint32(128+20,0xffffffff,true);
  v._onKernelMsg({...lastMessage,seq:v.seq},[bad]);
  v._onKernelMsg({...lastMessage,seq:v.seq-999},[lastRaw]);
  assert(uploads===stable&&creates===stableCreates&&g._tileTextures.size===stableSize,'malformed/stale allocated');
  const malformedPixels=pixels();assert(malformedPixels.every((p,i)=>p===oracle[i]),'malformed/stale changed image');
  const oldLevel=g._tileLevel,beforeZoom=g.density;
  await request([0,1,0,1]);
  const zoomPixels=pixels(),zoomInk=densityInk(zoomPixels),zoomCapture=await summarize(zoomPixels);
  assert(zoomCapture.alphaPixels>0,'zoom alpha blank');
  const zoomLevel=g._tileLevel;
  assert(Math.abs(zoomLevel-oldLevel)<=1,'ordinary zoom skipped level');
  // A live adjacent crossfade draws both actual tile levels through the
  // existing transition; a frozen presentation clock makes it reproducible.
  let adjacentFade=false;
  if(zoomLevel!==oldLevel) {
   v._prefersReducedMotion=()=>false;
   g._shownDensity=beforeZoom;g._densitySwitchPrev=null;
   let now=1000;v._now=()=>now;
   v._drawNow();now+=70;
   const drawn=[];const draw=v._drawDensity.bind(v);v._drawDensity=(gg,d,o)=>{if(d?.tileSet)drawn.push(d.level);return draw(gg,d,o);};
   v._drawNow();adjacentFade=drawn.includes(oldLevel)&&drawn.includes(zoomLevel);
   assert(adjacentFade,'adjacent crossfade did not draw both levels');
   v._drawDensity=draw;v._prefersReducedMotion=()=>true;
  }
  assert(adjacentFade,'fixture must exercise actual adjacent levels');
  // Real canvas widths may exceed the native paint resolution ceiling.
  // The server applies the same Rust screen-shape boundary as Python.
  const resize=(w,h)=>{v.fluid=true;v.fluidH=true;v._resize(w,h);clearTimeout(v._viewTimer);};
  resize(5000,320);
  await request([0,.5,0,.5]);
  assert(lastRequest.w>4096&&g.density.w===4096,`bounded large viewport frame rejected: request ${lastRequest.w}, displayed ${g.density.w}`);
  await request([.25,.75,0,.5]);
  assert(g.density.w===4096&&g.density.xRange[0]===.25,'large viewport pan stopped updating');
  const widePixels=pixels(),wideCapture=await summarize(widePixels),wideInk=densityInk(widePixels);
  const wideRequest={...g._lastDensityReq},wideMap=g._tileTextures,wideUploads=uploads,wideCreates=creates;
  for(const width of [4097,4095]) {
    const malformed=lastRaw.slice(0),d=new DataView(malformed);
    d.setUint32(72,width,true);d.setUint32(64,width*d.getUint32(76,true)*((d.getUint32(12,true)&1)?4:1)*8,true);
    g._lastDensityReq=wideRequest;v._onKernelMsg({...lastMessage,seq:v.seq},[malformed]);
    assert(g._tileTextures===wideMap&&uploads===wideUploads&&creates===wideCreates,'oversized/mismatched paint size adopted');
  }
  for(const width of [Infinity,NaN]) {
    g._lastDensityReq={...wideRequest,w:width};v._onKernelMsg({...lastMessage,seq:v.seq},[lastRaw]);
    assert(g._tileTextures===wideMap&&uploads===wideUploads&&creates===wideCreates,'non-finite requested shape adopted');
  }
  const wideAfterRefusal=pixels();assert(wideAfterRefusal.every((p,i)=>p===widePixels[i]),'paint-size refusal changed pixels');
  await request([.25,.75,0,.5],true);const wideOracle=pixels();
  assert(wideOracle.every((p,i)=>p===widePixels[i]),'wide cached/uncached pixel mismatch');
  // Build a nine-tile outgoing L0 surface, then shrink during its L1 fade.
  // The first shrink keeps L1 itself but prunes part of _densitySwitchPrev;
  // the second makes the immediately previous L1 surface incomplete too.
  resize(560,420);await request([.125,.625,.125,.625]);
  assert(g._tileLevel===0&&g.density.tileSet.length===9,`resize fade source fixture drifted: ${g._tileLevel}/${g.density.tileSet.length}, ${v.plot.w}x${v.plot.h}, budget ${g._tileStats.budget}`);
  let resizeClock=2000;v._now=()=>resizeClock;v._prefersReducedMotion=()=>false;
  await request([0,1,0,1]);
  const fadeSource=g._densitySwitchPrev,currentLevel=g._tileLevel;
  assert(fadeSource?.level===0&&currentLevel===1&&fadeSource.tileSet.every(t=>gl.isTexture(t.tex)),'resize did not begin a valid adjacent fade');
  resizeClock+=70;v._drawNow();
  async function shrink(width,height,expectedLevel,outgoing) {
    resize(width,height);const stats=await request([0,1,0,1]);
    const removed=outgoing.tileSet.filter(t=>!gl.isTexture(t.tex)).length;
    assert(removed>0,'Rust did not prune resize fixture outgoing tiles');
    assert(g._tileLevel===expectedLevel,'resize served level drifted');
    assert(!g._densitySwitchPrev&&g._shownDensity===g.density&&!g.prevDensity,'incomplete resize source still fading');
    assert((g.densityCache||[]).every(d=>!d.tileSet||d.tileSet.every(t=>gl.isTexture(t.tex))),'incomplete frame remains cached');
    // Complete count exposure only: this comparison isolates fade ownership.
    g._densityNormAnim=null;g.density.normMax=g.density.max;
    const atMidFade=pixels(),capture=await summarize(atMidFade),ink=densityInk(atMidFade);
    v._prefersReducedMotion=()=>true;await request([0,1,0,1],true);
    const completed=pixels();let differences=0;
    for(let i=0;i<completed.length;i++)if(completed[i]!==atMidFade[i])differences++;
    assert(differences===0,'resize mid-fade/uncached pixel mismatch '+differences);
    v._prefersReducedMotion=()=>false;
    return {servedLevel:expectedLevel,removedSourceTiles:removed,stats,capture:{...capture,densityPixels:ink},pixelDifferences:differences,fadeCompleted:true};
  }
  const sameLevelResize=await shrink(400,320,1,fadeSource),beforeSecondShrink=g.density;
  const adjacentResize=await shrink(300,190,2,beforeSecondShrink);
  v._prefersReducedMotion=()=>true;
  const all=[...g._tileTextures.values()].map(t=>t.tex),savedRaw=lastRaw,savedMsg=lastMessage;
  v.destroy();const destroyedUploads=uploads,destroyedCreates=creates;v._onKernelMsg(savedMsg,[savedRaw]);
  assert(uploads===destroyedUploads&&creates===destroyedCreates&&!v.gl&&g._tileTextures.size===0,'disposed reply retained tiles');
  assert(all.every(t=>!gl.isTexture(t))&&!gl.isBuffer(sharedBuffer),'disposed GPU resource live');
  output[kind]={first:a,pan:b,insidePan:inside,uncached:fresh,pixelDifferences:different,cachedCapture:{...cachedCapture,densityPixels:cachedInk},uncachedCapture:{...oracleCapture,densityPixels:oracleInk},zoomCapture:{...zoomCapture,densityPixels:zoomInk},ordinaryLevels:[oldLevel,zoomLevel],adjacentFade,wideViewport:{requestedWidth:wideRequest.w,servedWidth:4096,capture:{...wideCapture,densityPixels:wideInk},pixelDifferences:0,sizeRefusal:true},sameLevelResize,adjacentResize,malformedFormatFlip:true,legacyOverlayRetirement:true,sharedOverlayPreserved:true,malformedAndStale:true,disposed:true};
 }
 document.title='TILES:'+JSON.stringify(output);
}catch(e){document.title='FAIL:'+e.stack;}})();
</script>"""
    try:
        result = run_probe(page, timeout_s=120)
        if not result.startswith("TILES:"):
            raise SystemExit(result)
        report = {
            "schema": "xyg-density-tile-smoke-v1",
            "environment": {
                "platform": platform.platform(),
                "python": platform.python_version(),
                "native_abi": abi.ABI_VERSION,
            },
            "scope": "current-source native Rust and bundled painter; cache oracle fetches all tiles at identical Rust-served framing/level/exposure",
            "browser": json.loads(result[6:]),
            "requests": records,
        }
        print(json.dumps(report, indent=2))
    finally:
        server.shutdown()
        for store in stores.values():
            lib.xyg_tile_store_free(store)


if __name__ == "__main__":
    main()
