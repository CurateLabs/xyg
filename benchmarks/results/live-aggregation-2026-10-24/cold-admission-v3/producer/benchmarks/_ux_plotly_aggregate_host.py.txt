#!/usr/bin/env python3
"""Benchmark integration: Plotly axes/gestures + Datashader CPU count rasters.

This is explicitly Plotly+Datashader+Tornado, not native Plotly aggregation or
Dash. No source rows cross the socket. Each accepted range produces a PNG;
latest-view coalescing and stale-reply rejection happen in the page. Build
includes the first aggregate/JIT, PNG encoding and Plotly.js extraction.
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import hashlib
import io
import json
import time
from typing import Any

import numpy as np
import tornado.httpserver
import tornado.netutil
import tornado.web
import tornado.websocket

try:
    from ._ux_comparison_data import SENTINELS, make_data, source_identity
    from ._ux_live_host import ApplicationBytes
except ImportError:
    from _ux_comparison_data import SENTINELS, make_data, source_identity
    from _ux_live_host import ApplicationBytes

WIDTH, HEIGHT = 900, 420


def aggregate(frame: Any, domain: list[float], width: int = WIDTH, height: int = HEIGHT) -> dict:
    """Actual all-row count aggregate and independent in-window mass oracle."""
    import datashader as ds
    import datashader.transfer_functions as tf

    x0, x1, y0, y1 = domain
    if not all(np.isfinite(domain)) or x0 >= x1 or y0 >= y1:
        raise ValueError("invalid finite increasing range")
    canvas = ds.Canvas(plot_width=width, plot_height=height, x_range=(x0, x1), y_range=(y0, y1))
    grid = canvas.points(frame, "x", "y", ds.count())
    x, y = frame.x.to_numpy(), frame.y.to_numpy()
    from _ux_comparison_source import count_window

    count = count_window(x, y, domain)
    mass = int(np.asarray(grid).sum(dtype=np.uint64))
    if count != mass:
        raise AssertionError(f"Datashader mass {mass} differs from source oracle {count}")
    # Dark single-color count shading keeps sparse sentinel bins visible.
    image = tf.shade(grid, cmap=["#235789", "#081d58"], how="log", min_alpha=255).to_pil()
    output = io.BytesIO()
    image.save(output, format="PNG")
    png = output.getvalue()
    return {
        "domain": domain,
        "source": "data:image/png;base64," + base64.b64encode(png).decode("ascii"),
        "oracle": {"count": count, "grid_mass": mass, "passed": True},
        "png_sha256": hashlib.sha256(png).hexdigest(),
        "grid_shape": [height, width],
    }


PAGE = r"""<!doctype html><meta charset="utf-8"><title>Plotly + Datashader</title>
<style>html,body{margin:0;background:white}#chart{width:900px;height:420px}</style>
<div id="chart"></div><script src="/plotly.js"></script><script>
const gd = document.getElementById("chart");
const ws = new WebSocket(`ws://${location.host}/ws`);
const bytes = {layer:"websocket_application_messages", to_host:{json_bytes:0,binary_frame_bytes:0},
  from_host:{json_bytes:0,binary_frame_bytes:0}};
function record(dir, text) {bytes[dir].json_bytes += new TextEncoder().encode(text).byteLength;}
let revision=0, applied=-1, busy=false, initialized=false, decoded=null, lastFrame=null;
let requested=null, timer=null;
function domain() {const f=gd._fullLayout; return f ? [
  ...f.xaxis.range, ...f.yaxis.range] : null;}
function same(a,b) {return a && b && a.every((v,i)=>Math.abs(v-b[i])<=1e-10*Math.max(1,Math.abs(v)));}
function request() {
  if (busy || !requested) return;
  busy=true;
  const text=JSON.stringify({seq:revision, domain:requested});
  record("to_host",text); ws.send(text); requested=null;
}
function changed(e) {
  if (!Object.keys(e).some(k=>/^[xy]axis\.range/.test(k))) return;
  revision++; requested=domain();
  clearTimeout(timer); timer=setTimeout(request,75);
}
async function apply(frame) {
  busy=false;
  if (frame.seq!==revision) {request(); return;}
  const image=new Image(); image.src=frame.source; await image.decode();
  if (frame.seq!==revision) {request(); return;}
  const [x0,x1,y0,y1]=frame.domain;
  const images=[{source:frame.source,xref:"x",yref:"y",x:x0,y:y1,
    sizex:x1-x0,sizey:y1-y0,xanchor:"left",yanchor:"top",sizing:"stretch",layer:"above"}];
  if (!initialized) {
    await Plotly.newPlot(gd,[{type:"scatter",x:[null],y:[null],mode:"markers"}],{
      width:900,height:420,margin:{l:0,r:0,t:0,b:0},showlegend:false,
      xaxis:{range:[x0,x1],showgrid:false,zeroline:false,showticklabels:false},
      yaxis:{range:[y0,y1],showgrid:false,zeroline:false,showticklabels:false},
      images,dragmode:"pan",paper_bgcolor:"white",plot_bgcolor:"white"
    },{scrollZoom:true,displayModeBar:false});
    gd.on("plotly_relayout",changed); initialized=true;
  } else await Plotly.relayout(gd,{images});
  if (frame.seq===revision) {decoded=image; applied=frame.seq; lastFrame=frame;}
  request();
}
ws.onmessage=ev=>{record("from_host",ev.data); apply(JSON.parse(ev.data)).catch(e=>{
  document.title="UX_ERROR "+JSON.stringify({why:"aggregate_apply",error:String(e)});
});};
window.__arm={
  ready:()=>initialized && applied===revision,
  domain:()=>{const d=domain();return d ? {x0:d[0],x1:d[1],y0:d[2],y1:d[3]}:null;},
  project:(x,y)=>{
    const d=domain();
    if (applied!==revision || !lastFrame || !same(d,lastFrame.domain) ||
        x<d[0] || x>d[1] || y<d[2] || y>d[3]) return null;
    const f=gd._fullLayout;
    return {px:f.xaxis._offset+f.xaxis.l2p(x),py:f.yaxis._offset+f.yaxis.l2p(y)};
  },
  // Read the displayed Plotly SVG image at its actual DOM extent. SVG images
  // have no getImageData; decode their exact PNG and composite at that extent.
  // Pending/stale/missing images yield no surfaces, never a fabricated pass.
  readbacks:()=>{
    if (!decoded || applied!==revision || !same(domain(),lastFrame.domain)) return [];
    const el=[...gd.querySelectorAll(".imagelayer image")].find(
      e=>(e.getAttribute("href")||e.getAttribute("xlink:href"))===lastFrame.source);
    if (!el) return [];
    const r=el.getBoundingClientRect(), g=gd.getBoundingClientRect();
    if (!r.width || !r.height) return [];
    const c=document.createElement("canvas");c.width=900;c.height=420;
    const ctx=c.getContext("2d");ctx.fillStyle="white";ctx.fillRect(0,0,900,420);
    ctx.drawImage(decoded,r.left-g.left,r.top-g.top,r.width,r.height);
    return [{data:ctx.getImageData(0,0,900,420).data,w:900,h:420,
      cssW:900,cssH:420,topDown:true}];
  },
  zoomInput:(fx,fy,dir)=>{
    const f=gd._fullLayout, r=gd.getBoundingClientRect(), d=domain();
    const [x,y]=__SENTINEL0__;
    const px=f.xaxis._offset+f.xaxis.l2p(x), py=f.yaxis._offset+f.yaxis.l2p(y);
    (gd.querySelector(".nsewdrag")||gd).dispatchEvent(new WheelEvent("wheel",{
      bubbles:true,cancelable:true,clientX:r.left+px,clientY:r.top+py,
      deltaY:dir>0?-120:120,deltaMode:0}));
  },
  applicationBytes:()=>{
    const s=JSON.parse(JSON.stringify(bytes));s.total_bytes=0;
    for(const d of ["to_host","from_host"]) {
      s[d].total_bytes=s[d].json_bytes+s[d].binary_frame_bytes;s.total_bytes+=s[d].total_bytes;
    }return s;
  },
  evidence:()=>({revision,applied,domain:domain(),raster:lastFrame && {
    domain:lastFrame.domain,oracle:lastFrame.oracle,png_sha256:lastFrame.png_sha256,
    grid_shape:lastFrame.grid_shape}})
};
</script>"""


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--n", type=int, required=True)
    from _ux_comparison_host import (
        PLOTLY_JS,
        add_arguments,
        inventory,
        load_source,
        metrics_handler,
    )

    add_arguments(parser)
    args = parser.parse_args()
    import pandas as pd
    from plotly.offline import get_plotlyjs

    if args.comparison_source:
        x, y, source = load_source(args.comparison_source, args.n)
    else:
        x, y = make_data(args.n)
        source = source_identity(x, y)
    t0 = time.perf_counter()
    frame = pd.DataFrame({"x": x, "y": y}, copy=False if args.comparison_source else None)
    # Same source, padding keeps planted sentinels inside the home image.
    xr, yr = float(x.max() - x.min()), float(y.max() - y.min())
    home = [
        float(x.min()) - xr * 0.05,
        float(x.max()) + xr * 0.05,
        float(y.min()) - yr * 0.05,
        float(y.max()) + yr * 0.05,
    ]
    size = (512, 512) if args.comparison_source else (WIDTH, HEIGHT)
    if args.comparison_source:
        home = source["extents"]
    initial = {"seq": 0, **aggregate(frame, home, *size)}
    page = PAGE
    state = {}
    if args.comparison_source:
        state["canonical_admission"] = inventory((x, y), (frame.x.to_numpy(), frame.y.to_numpy()))
        page = (
            page.replace("900", "512")
            .replace("420", "512")
            .replace("\n</script>", PLOTLY_JS + "\n</script>")
        )
    plotly_js = get_plotlyjs()
    build_ms = (time.perf_counter() - t0) * 1000
    accounting = ApplicationBytes()
    frames: list[dict] = []

    class Page(tornado.web.RequestHandler):
        def get(self):
            self.set_header("Content-Type", "text/html; charset=utf-8")
            self.write(page.replace("__SENTINEL0__", json.dumps(SENTINELS[0])))

    class Script(tornado.web.RequestHandler):
        def get(self):
            self.set_header("Content-Type", "application/javascript")
            self.write(plotly_js)

    class Metrics(tornado.web.RequestHandler):
        def get(self):
            self.write({**accounting.snapshot(), "frames": frames})

    class Socket(tornado.websocket.WebSocketHandler):
        def send(self, result):
            body = json.dumps(result, separators=(",", ":"))
            accounting.record("from_host", body)
            self.write_message(body)
            frames.append({k: v for k, v in result.items() if k != "source"})
            state["last_output"] = frames[-1]

        def open(self):
            self.send(initial)

        def on_message(self, body):
            accounting.record("to_host", body)
            try:
                request = json.loads(body)
                if len(request["domain"]) != 4 or not isinstance(request["seq"], int):
                    raise ValueError("invalid range request")
                started = time.perf_counter()
                result = aggregate(frame, request["domain"], *size)
                self.send(
                    {
                        "seq": request["seq"],
                        **result,
                        "aggregate_encode_oracle_ms": (time.perf_counter() - started) * 1000,
                    }
                )
            except (ValueError, KeyError, TypeError, AssertionError):
                self.close(1007, "invalid range or failed mass oracle")

    async def serve():
        app = tornado.web.Application(
            [
                (r"/", Page),
                (r"/plotly.js", Script),
                (r"/ws", Socket),
                (r"/transport_metrics", Metrics),
                (r"/comparison_metrics", metrics_handler(state)),
            ],
            websocket_max_message_size=16384,
        )
        sockets = tornado.netutil.bind_sockets(0, "127.0.0.1")
        server = tornado.httpserver.HTTPServer(app)
        server.add_sockets(sockets)
        print(
            "META "
            + json.dumps(
                {
                    "port": sockets[0].getsockname()[1],
                    "n": args.n,
                    "sentinels": SENTINELS,
                    "source": source,
                    "build_ms": build_ms,
                    "mode": "density",
                    "components": ["Plotly", "Datashader", "Tornado"],
                    "aggregation": "Datashader Canvas.points count; log shade; PNG; no raw drill",
                }
            ),
            flush=True,
        )
        await asyncio.Event().wait()

    asyncio.run(serve())


if __name__ == "__main__":
    main()
