"""Opt-in instrumentation around reused live hosts; no replacement renderer."""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path

import numpy as np
import tornado.web

try:
    from ._ux_comparison_source import (
        count_window,
    )
    from ._ux_comparison_source import (
        inventory as inventory,
    )
    from ._ux_comparison_source import (
        load_source as _load_source,
    )
except ImportError:
    from _ux_comparison_source import (
        count_window,
    )
    from _ux_comparison_source import (
        inventory as inventory,
    )
    from _ux_comparison_source import (
        load_source as _load_source,
    )


def add_arguments(parser):
    parser.add_argument("--comparison-source", type=Path)


def expected_count(meta, x, y, domain):
    for step in meta["windows"]:
        if np.allclose(step["window"], domain, rtol=0, atol=1e-10):
            return step["expected_count"]
    return count_window(x, y, domain)


_comparison_source = None


def load_source(path, n):
    global _comparison_source
    _comparison_source = _load_source(path, n)
    return _comparison_source


def metrics_handler(state):
    oracle = None
    if "canonical_after_build" in state and _comparison_source is not None:
        from benchmarks._ux_comparison_oracle import SourceOracle

        oracle = SourceOracle(*_comparison_source)
        state["numerical_oracle_preparation"] = oracle.preparation

    class Metrics(tornado.web.RequestHandler):
        def get(self):
            self.write(state)

        def post(self):
            from benchmarks._ux_comparison_oracle import decode_attachment

            if oracle is None:
                raise tornado.web.HTTPError(400, "no source-derived XYG oracle")
            started = time.perf_counter()
            try:
                request = json.loads(self.request.body)
                result = oracle.validate(
                    request["output"],
                    decode_attachment(request["wire"]),
                    decode_attachment(request["decoded"]),
                    cold=request["cold"],
                    target=request["target"],
                )
            except (KeyError, ValueError, TypeError) as exc:
                result = {"passed": False, "reason": str(exc)}
            result["validation_wall_ms"] = (time.perf_counter() - started) * 1000
            result["validation_http_request_bytes"] = len(self.request.body)
            state["numerical_oracle"] = result
            self.write(result)

    return Metrics


def observe_datashader(meta, x, y, state):
    """Observe the actual Canvas.points called by HoloViews; never replace its output."""
    import datashader as ds

    original = ds.Canvas.points

    def observed(canvas, *args, **kwargs):
        if args and hasattr(args[0], "columns") and {"x", "y"} <= set(args[0].columns):
            state["backend_input"] = inventory(
                (x, y), (args[0]["x"].to_numpy(), args[0]["y"].to_numpy())
            )
        grid = original(canvas, *args, **kwargs)
        domain = [*canvas.x_range, *canvas.y_range]
        mass = int(np.asarray(grid).sum(dtype=np.uint64))
        count = expected_count(meta, x, y, domain)
        state["backend_frames"] = state.get("backend_frames", 0) + 1
        state["last_output"] = {
            "domain": domain,
            "grid_shape": list(grid.shape),
            "grid_sha256": hashlib.sha256(np.asarray(grid).tobytes()).hexdigest(),
            "count": count,
            "grid_mass": mass,
            "passed": count == mass,
            "backend_revision": state["backend_frames"],
        }
        # Only bounded metadata, never retained source or raster arrays. Repeated
        # windows may reuse HoloViews' cached image; bind it to its own grid.
        key = (tuple(domain), tuple(grid.shape))
        state.setdefault("backend_outputs", {})[str(key)] = dict(state["last_output"])
        if mass != count:
            raise AssertionError("actual Datashader grid mass differs from shared source count")
        return grid

    ds.Canvas.points = observed

    from holoviews.plotting.bokeh.raster import RGBPlot

    original_get_data = RGBPlot.get_data

    def bound_data(plot, *args, **kwargs):
        data, mapping, style = original_get_data(plot, *args, **kwargs)
        if "image" in data:
            data["comparison_backend"] = [datashader_binding(data, state)]
        return data, mapping, style

    # Add metadata before the real CDS update. An after-update hook would send
    # the entire image a second time, changing the measured transport workload.
    RGBPlot.get_data = bound_data


def datashader_binding(data, state):
    """Bind the actual shaded image to its observed source grid (dossier §12).

    A browser must see this binding and its image bytes together before admission;
    the 400px bootstrap and later 512px response have separate bindings.
    """
    image = np.asarray(data["image"][0])
    domain = [
        data["x"][0],
        data["x"][0] + data["dw"][0],
        data["y"][0],
        data["y"][0] + data["dh"][0],
    ]
    matches = [
        out
        for out in state.get("backend_outputs", {}).values()
        if list(image.shape) == out["grid_shape"]
        and np.allclose(domain, out["domain"], rtol=0, atol=1e-10)
    ]
    if not matches:
        raise AssertionError("Bokeh image has no observed source-grid binding")
    return dict(matches[-1], image_sha256=hashlib.sha256(image.tobytes()).hexdigest())


XY_JS = r"""
// Explicit range/round-trip experiment. Suppress automatic request scheduling
// only here so every measured reply belongs to this exact requested window.
// The production dispatcher still owns density vs exact-points policy.
const comparison = {last:null, request:null, initial:null, buffers:null, initialBuffers:null};
const originalMessage = ws.onmessage;
ws.onmessage = ev => {
  originalMessage(ev);
  if (typeof ev.data !== "string") {
    const decoded=decodeFrame(ev.data), m=decoded.message;
    if (m.type==="density_update") {
      comparison.last=m;
      comparison.buffers=decoded.buffers;
      if(m.traces?.[0]?.mode==="density" && window.__view.gpuTraces[0].density)
        window.__view.gpuTraces[0].density._comparisonRevision=m.seq;
    }
    if(m.type==="init") {
      comparison.initial=m;comparison.initialBuffers=decoded.buffers;
      if(window.__view?.gpuTraces?.[0]?.density)
        window.__view.gpuTraces[0].density._comparisonRevision=0;
    }
  }
};
window.__comparison = {
  async validateOutput(cold,target) {
    const state=this.state(),out=state.output;
    if(!out?.adopted || comparison.validated===out.revision)return;
    const g=window.__view.gpuTraces[0],u=cold?comparison.initial.spec.traces[0]:comparison.last.traces[0];
    const buffers=cold?comparison.initialBuffers:comparison.buffers;
    const bytes=v=>v instanceof ArrayBuffer?new Uint8Array(v):new Uint8Array(v.buffer,v.byteOffset,v.byteLength);
    const b64=v=>{let s='';for(let i=0;i<v.length;i+=8192)s+=String.fromCharCode(...v.subarray(i,i+8192));return btoa(s);};
    const wire=out.mode==='density'?bytes(buffers[u.density.buf]):new Uint8Array();
    const shown=g._shownDensity;
    const decoded=out.mode==='density'?bytes(shown.grid):new Uint8Array();
    const response=await fetch('/comparison_metrics',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({output:out,wire:b64(wire),decoded:b64(decoded),cold,target})});
    comparison.numerical=await response.json();comparison.validated=out.revision;
  },
  setWindow(d) {
    const v=window.__view;
    v._scheduleViewRequest=()=>{};
    clearTimeout(v._viewTimer);
    v.setView({x:d.slice(0,2),y:d.slice(2,4)},{animate:false});
    const seq=++v.seq, g=v.gpuTraces[0];
    g._lodPendingSeq=seq;g._lodPendingView={...v.view};g._lodPendingAt=v._now();
    g._stepReqWin=[...d];
    comparison.request={seq,domain:[...d]};
    sendMessage(ws,{type:"density_view",trace:g.trace.id,seq,
      x0:d[0],x1:d[1],y0:d[2],y1:d[3],w:512,h:512});
  },
  state() {
    const v=window.__view,g=v?.gpuTraces?.[0], cold=!comparison.request && comparison.initial,
      r=comparison.last || (cold?{seq:0}:null),
      u=cold?comparison.initial.spec.traces[0]:r?.traces?.[0], d=g?.density, drill=g?.drill;
    const axes=v?[v.view.x0,v.view.x1,v.view.y0,v.view.y1]:null;
    let output=null;
    if (r && (cold || r.seq===comparison.request?.seq) && u) {
      const points=!cold && u.mode==="points";
      let displayed=null;
      if(points && drill && comparison.countSeq!==r.seq) {
        const target=comparison.request.domain;let count=0;
        for(let i=0;i<drill.n;i++) {
          const x=drill._cpuX[i]/(drill.xMeta.scale||1)+drill.xMeta.offset;
          const y=drill._cpuY[i]/(drill.yMeta.scale||1)+drill.yMeta.offset;
          if(x>=target[0] && x<=target[1] && y>=target[2] && y<=target[3])count++;
        }
        comparison.countSeq=r.seq;comparison.displayedCount=count;
      }
      const shown=g?._shownDensity;
      const sameRange=(a,b)=>a && b && a.length===b.length && a.every((v,i)=>Math.abs(v-b[i])<=1e-12);
      const equivalent=!!shown && !!d && shown.w===d.w && shown.h===d.h &&
        sameRange(shown.xRange,d.xRange) && sameRange(shown.yRange,d.yRange) &&
        !!shown.grid && !!d.grid && shown.grid.length===d.grid.length &&
        shown.grid.every((value,i)=>value===d.grid[i]);
      output={revision:r.seq,mode:points?'points':'density',tier:u.tier,
        reduction:cold?u.density.reduction:u.reduction,visible:cold?u.n_points:u.visible,
        encoding:u.density?.enc,reply_max:u.density?.max,
        adopted_max:shown?.max,
        numerical_oracle:comparison.validated===r.seq?comparison.numerical:null,
        rendered_revision:points?drill?.seq:shown?._comparisonRevision,
        equivalent_cached_raster:!points && shown!==d && equivalent,
        grid_value_equality_verified:!points && equivalent,
        reply_domain:d?[...d.xRange,...d.yRange]:null,
        rendered_revision_kind:points?"drill_subset":"density_reply",
        rendered_norm_max:shown?.normMax,reply_norm_max:d?.normMax,
        binning:u.binning || u.density?.binning,
        domain:points && drill ? [drill.win.x0,drill.win.x1,drill.win.y0,drill.win.y1]
          :shown?[...shown.xRange,...shown.yRange]:null,
        adopted:points ? !!drill && drill.seq===u.drill_seq && drill.n===u.x?.len
          :!!d && (shown===d || equivalent),
        exact_count:points ? comparison.displayedCount : null,
        payload_count:points ? drill?.n : null,
        raster_shape:points?null:[d?.h,d?.w],
        exact_fallback:points};
    }
    return {axes,output,requested:comparison.request,
      plot_shape:v?[v.plot.w,v.plot.h]:null};
  }
};
"""

PLOTLY_JS = r"""
window.__comparison={
  setWindow(d) {return Plotly.relayout(gd,{"xaxis.range":d.slice(0,2),"yaxis.range":d.slice(2,4)});},
  state() {
    const e=window.__arm.evidence(),o=e.raster;
    return {axes:e.domain,plot_shape:[gd._fullLayout._size.w,gd._fullLayout._size.h],
      output:o ? {domain:o.domain,revision:e.applied,adopted:e.applied===e.revision,
        mode:"density",exact_fallback:false,oracle:o.oracle,raster_shape:o.grid_shape,
        png_sha256:o.png_sha256}:null};
  }
};
"""

BOKEH_JS = r"""
const bkArm=window.__arm;
bkArm.readbacks=function() {
  const pv=this._pv();if(!pv || !this.currentRaster())return [];
  const el=pv.canvas_view.primary.el, box=pv.frame.bbox;
  const img=el.getContext("2d").getImageData(Math.round(box.x0),Math.round(box.y0),512,512);
  return [{data:img.data,w:512,h:512,cssW:512,cssH:512,topDown:true}];
};
bkArm.__kicked=true; // no legacy wheel nudge in this programmatic profile
let bkRevision=0,bkDataRevision=0,bkConnected=false,bkRequestDataRevision=-1;
let bkValidated=null;
const bkNear=(a,b)=>a && b && a.length===b.length && a.every((v,i)=>
  Number.isFinite(v) && Math.abs(v-b[i])<=1e-9*Math.max(1,Math.abs(b[i])));
function bkImage() {
  const pv=bkArm._pv();if(!pv)return null;
  for(const rv of pv.renderer_views.values()) {
    const data=rv.model.data_source?.data;
    if(data?.image && /Image/.test(rv.model.glyph?.type || ''))
      return {image:data.image[0],binding:data.comparison_backend?.[0]};
  }
  return null;
}
window.__comparison={
  setWindow(d) {
    const pv=bkArm._pv();
    bkRevision++;bkRequestDataRevision=bkDataRevision;bkValidated=null;
    pv.model.x_range.setv({start:d[0],end:d[1]});
    pv.model.y_range.setv({start:d[2],end:d[3]});
    pv.trigger_ranges_update_event();
  },
  async validateOutput(cold,target) {
    const current=bkImage(),b=current?.binding;
    if(!b || !bkNear(b.domain,target) || !bkNear(b.grid_shape,[512,512]) ||
       !b.passed || bkDataRevision<=bkRequestDataRevision)return;
    if(bkValidated?.image===current.image && bkValidated.binding===b)return;
    const raw=ArrayBuffer.isView(current.image)?current.image:current.image.data;
    const bytes=new Uint8Array(raw.buffer,raw.byteOffset,raw.byteLength);
    const digest=Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',bytes)),
      v=>v.toString(16).padStart(2,'0')).join('');
    const metrics=await (await fetch('/comparison_metrics',
      {signal:AbortSignal.timeout(1000)})).json();
    const host=metrics.last_output;
    if(digest!==b.image_sha256 || !host || !host.passed ||
       host.backend_revision!==b.backend_revision || host.grid_sha256!==b.grid_sha256 ||
       host.count!==b.count || host.grid_mass!==b.grid_mass ||
       !bkNear(host.domain,b.domain) || !bkNear(host.grid_shape,b.grid_shape))return;
    // Never validate a newly replaced image using the previous async result.
    const after=bkImage();
    if(after?.image===current.image && after.binding===b)
      bkValidated={...current,revision:bkDataRevision};
  },
  state() {
    const pv=bkArm._pv();if(!pv)return {};
    const evidence=bkArm.evidence(),d=evidence.domain;
    const r=evidence.rasters[0],current=bkImage(),b=current?.binding;
    if(!bkConnected) {
      for(const rv of pv.renderer_views.values()) if(rv.model.data_source) {
        rv.model.data_source.properties.data.change.connect(()=>{
          bkDataRevision++;bkValidated=null;
        });
      }
      bkConnected=true;
    }
    const valid=bkValidated?.image===current?.image && bkValidated?.binding===b &&
      bkValidated?.revision===bkDataRevision && bkDataRevision>bkRequestDataRevision;
    return {axes:[d.x0,d.x1,d.y0,d.y1],plot_shape:[pv.frame.bbox.width,pv.frame.bbox.height],
      output:r?{domain:[r.x,r.x+r.dw,r.y,r.y+r.dh],revision:bkDataRevision,
        requested_revision:bkRevision,adopted:!!valid && bkArm.currentRaster(),mode:"density",
        backend_binding:b,oracle:b?{passed:!!valid && b.passed,count:b.count,grid_mass:b.grid_mass}:null,
        exact_fallback:false,raster_shape:r.shape}:null};
  }
};
"""
