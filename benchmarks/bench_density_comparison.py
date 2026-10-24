#!/usr/bin/env python3
"""Programmatic equal-window comparison, separate from legacy real-wheel UX.

32 explicit shared windows, fixed fresh-host repetitions; no gesture claim.
Large allocations require the existing manual/main Blacksmith macOS M4 lane.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

import psutil

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "benchmarks")]
import _launch_interactive as interactive  # noqa: E402
from _ux_comparison_host import BOKEH_JS  # noqa: E402
from _ux_comparison_source import allocation_guard, create_source  # noqa: E402
from bench_ux import (  # noqa: E402
    DATASHADER_AGGREGATE_GUARD_JS,
    DATASHADER_ARM_JS,
    TreePeakPoller,
    byte_delta,
    drive_browser,
    provenance,
    read_meta,
)
from environment import collect_environment_metadata  # noqa: E402

ARMS = ("xy-density", "plotly-aggregate", "datashader-aggregate")


def engine_js(source, step_timeout):
    cfg = {
        "extents": source["extents"],
        "n": source["actual_rows"],
        "windows": source["windows"],
        "deadline": step_timeout * 1000,
    }
    return (
        "const DC="
        + json.dumps(cfg)
        + r""";
(async()=>{
 const raf=()=>new Promise(r=>requestAnimationFrame(r));
 const near=(a,b)=>a && b && a.length===b.length && a.every((v,i)=>
   Number.isFinite(v) && Math.abs(v-b[i])<=1e-9*Math.max(1,Math.abs(b[i])));
 const steps=[];
 function snapshot() {
   const surfaces=window.__arm.readbacks();let hash=5381,lit=0;
   for(const s of surfaces) {
     const d=s.data;
     const corners=[0,(s.w-1)*4,((s.h-1)*s.w)*4,(s.h*s.w-1)*4];
     const groups=new Map();
     for(const i of corners){const c=Array.from(d.slice(i,i+4));const k=c.join(',');
       const old=groups.get(k);groups.set(k,{c,n:(old?.n||0)+1});}
     const bg=[...groups.values()].sort((a,b)=>b.n-a.n)[0].c;
     for(let i=0;i<d.length;i+=4) {
       const pixel=i/4,px=pixel%s.w,py=Math.floor(pixel/s.w);
       if(px>=2 && py>=2 && px<s.w-2 && py<s.h-2 && d[i+3]>24 &&
          Math.abs(d[i]-255)+Math.abs(d[i+1]-255)+Math.abs(d[i+2]-255)>24)lit++;
       hash=(((hash*33)>>>0)^((d[i]<<24)^(d[i+1]<<16)^(d[i+2]<<8)^d[i+3]))>>>0;
     }
   }
   return {hash,lit,surfaces:surfaces.length};
 }
 async function checkpoint(name) {
   window.__shotDone=false;document.title='UX_SHOT '+name;
   while(!window.__shotDone)await raf();
   document.title='UX_STAGE '+JSON.stringify({completed:name});
 }
 async function settle(domain,count,start,cold=false) {
   let axesAt=null,adoptAt=null,stableAt=null,lastHash=null,stable=0,diag=null,lastError=null;
   while(performance.now()-start<DC.deadline) {
     try {
       const snap=snapshot(), state=window.__comparison.state(),now=performance.now();
       const axes=near(state.axes,domain);
       const square=near(state.plot_shape,[512,512]);
       if(axes && axesAt===null)axesAt=now;
       const out=state.output;
       const covers=out?.domain && out.domain[0]<=domain[0]+1e-9 && out.domain[1]>=domain[1]-1e-9 &&
         out.domain[2]<=domain[2]+1e-9 && out.domain[3]>=domain[3]-1e-9;
       const adopted=cold || (!!out?.adopted && (out.exact_fallback ? covers : near(out.domain,domain)));
       const oracle=cold || (out?.oracle ? out.oracle.passed && out.oracle.count===count
           :out?.exact_fallback ? out.exact_count===count : true);
       const painted=snap.surfaces>0 && (count===0?snap.lit===0:snap.lit>0);
       const correct=axes && square && adopted && oracle && painted;
       if(axes && square && adopted && adoptAt===null)adoptAt=now;
       diag={state,snap,axes,square,adopted,oracle,painted,lastError};
       if(correct && snap.hash===lastHash){
         if(stable===0)stableAt=now;
         if(++stable>=10)return {ok:true,axes_adopt_ms:axesAt-start,
           output_adopt_ms:adoptAt-start,paint_stable_ms:stableAt-start,
           stability_confirmed_ms:now-start,paint_hash32:snap.hash,lit_pixels:snap.lit,
           expected_count:count,state};
       }else{stable=0;stableAt=null;}
       lastHash=snap.hash;
     }catch(e){lastError=String(e);}
     await raf();
   }
   return {ok:false,reason:'window_not_adopted_or_painted',elapsed_ms:performance.now()-start,diag,lastError};
 }
 try {
   const coldStart=performance.now();
   while(!window.__arm?.ready() || !window.__comparison) {
     if(performance.now()-coldStart>DC.deadline)throw Error('arm never ready');
     await raf();
   }
   const cold=await settle(DC.extents,DC.n,coldStart,true);
   if(!cold.ok){document.title='UX_BENCH '+JSON.stringify({comparison_status:'cold_failed',cold,steps});return;}
   await checkpoint('visible-complete');
   for(let index=0;index<DC.windows.length;index++) {
     const target=DC.windows[index],started=performance.now();
     await window.__comparison.setWindow(target.window);
     const returned=performance.now();
     const step=await settle(target.window,target.expected_count,started);
     steps.push({index,kind:target.kind,requested_window:target.window,request_start_ms:started,request_return_ms:returned-started,...step});
     await checkpoint('step-'+index);
     if(!step.ok){document.title='UX_BENCH '+JSON.stringify({comparison_status:'step_failed',cold,steps});return;}
   }
   const e=DC.extents,dx=e[1]-e[0],dy=e[3]-e[2];
   const emptyWindow=[e[1]+dx,e[1]+1.5*dx,e[3]+dy,e[3]+1.5*dy];
   const emptyStart=performance.now();await window.__comparison.setWindow(emptyWindow);
   const empty_control={requested_window:emptyWindow,...await settle(emptyWindow,0,emptyStart)};
   await checkpoint('empty-control');
   document.title='UX_BENCH '+JSON.stringify({comparison_status:empty_control.ok?'ok':'empty_control_failed',cold,steps,empty_control});
 }catch(e){document.title='UX_BENCH '+JSON.stringify({comparison_status:'exception',error:String(e),steps});}
})();"""
    )


def json_url(url):
    with urllib.request.urlopen(url, timeout=3) as response:
        return json.load(response)


def run_arm(arm, manifest, args, repetition):
    scripts = {
        "xy-density": "_ux_live_host.py",
        "plotly-aggregate": "_ux_plotly_aggregate_host.py",
        "datashader-aggregate": "_ux_datashader_host.py",
    }
    source = json.loads(manifest.read_text())
    extra = (
        ["--density", "on"]
        if arm == "xy-density"
        else ["--aggregate-only"]
        if arm == "datashader-aggregate"
        else []
    )
    started = time.perf_counter()
    with tempfile.TemporaryFile(mode="w+", encoding="utf-8") as errors:
        host = subprocess.Popen(
            [
                sys.executable,
                str(ROOT / "benchmarks" / scripts[arm]),
                "--n",
                str(source["actual_rows"]),
                "--comparison-source",
                str(manifest),
                *extra,
            ],
            stdout=subprocess.PIPE,
            stderr=errors,
            text=True,
        )
        poller = TreePeakPoller(host.pid, int(args.memory_gib * 2**30))
        result = {"arm": arm, "n": source["actual_rows"], "repetition": repetition}
        try:
            line = read_meta(host, timeout_s=args.timeout)
            if line is None:
                result["status"] = "host_memory_limit" if poller.limit_exceeded else "host_failed"
                return result
            meta = json.loads(line[5:])
            result["host_meta"] = meta
            result["host_prepare_wall_ms"] = (time.perf_counter() - started) * 1000
            if meta["source"] != source:
                result["status"] = "source_mismatch"
                return result
            url = f"http://{meta.get('hostname', '127.0.0.1')}:{meta['port']}"

            def checkpoint(name):
                return {
                    "host_rss_bytes": interactive.tree_rss(psutil.Process(host.pid)),
                    "host_peak_rss_bytes": max(
                        poller.peak, interactive.tree_rss(psutil.Process(host.pid))
                    ),
                    "host_observation": json_url(url + "/comparison_metrics"),
                }

            injection = []
            if arm == "datashader-aggregate":
                injection = [
                    DATASHADER_ARM_JS.replace("__SENTINEL0__", "[4.6,2.2]").replace(
                        "if (ok && !this.__kicked)", "if (false)"
                    )
                    + DATASHADER_AGGREGATE_GUARD_JS
                    + BOKEH_JS
                ]
            row = drive_browser(
                url + "/",
                [*injection, engine_js(source, args.step_timeout)],
                chrome=args.chrome,
                timeout_s=args.timeout,
                memory_limit_bytes=int(args.memory_gib * 2**30),
                software=not args.hardware,
                checkpoint_details=checkpoint,
            )
            result.update(row)
            if row.get("status") == "ok":
                result["status"] = row.get("comparison_status", "missing_comparison_status")
            cps = row.get("transport", {}).get("checkpoints", {})
            previous = cps.get("visible-complete")
            for step in result.get("steps", []):
                cp = cps.get(f"step-{step['index']}")
                if cp and previous:
                    step["application_body_bytes"] = byte_delta(
                        cp["cdp_application_bytes"], previous["cdp_application_bytes"]
                    )
                    step["memory"] = {
                        k: cp[k]
                        for k in (
                            "host_rss_bytes",
                            "host_peak_rss_bytes",
                            "browser_rss_bytes",
                            "browser_peak_rss_bytes",
                        )
                    }
                    step["host_observation"] = cp["host_observation"]
                    output = cp["host_observation"].get("last_output")
                    if (
                        arm == "datashader-aggregate"
                        and step["ok"]
                        and (
                            not output
                            or not output["passed"]
                            or not np_equal(output["domain"], step["requested_window"])
                        )
                    ):
                        step["ok"] = False
                        step["reason"] = "backend_oracle_not_current"
                        result["status"] = "step_failed"
                    previous = cp
            return result
        except Exception as exc:
            result.update(
                status="host_memory_limit" if poller.limit_exceeded else "failed", error=str(exc)
            )
            return result
        finally:
            result["host_peak_rss_bytes"] = poller.stop()
            if poller.limit_exceeded:
                result["status"] = "host_memory_limit"
            if host.poll() is None:
                host.kill()
            host.wait(timeout=5)
            errors.seek(0)
            result["host_stderr"] = errors.read()[-4000:]


def np_equal(a, b):
    return len(a) == len(b) and all(
        abs(x - y) <= 1e-9 * max(1, abs(y)) for x, y in zip(a, b, strict=True)
    )


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--sizes", default="1000,100000,1000000")
    p.add_argument("--arms", default=",".join(ARMS))
    p.add_argument("--profile", choices=("f32", "f64-memmap"), default="f32")
    p.add_argument("--repetitions", type=int, choices=(2, 3), default=2)
    p.add_argument("--chunk", type=int, default=65536)
    p.add_argument("--memory-gib", type=float, default=2)
    p.add_argument("--disk-gib", type=float, default=0.25)
    p.add_argument("--timeout", type=float, default=180)
    p.add_argument("--step-timeout", type=float, default=15)
    p.add_argument("--chrome", default=os.environ.get("CHROME"))
    p.add_argument("--hardware", action="store_true")
    p.add_argument("--out", type=Path)
    p.add_argument("--source-child", type=Path)
    p.add_argument("--child-n", type=int)
    args = p.parse_args()
    if args.source_child:
        print(
            json.dumps(
                create_source(
                    args.source_child,
                    args.child_n,
                    args.profile,
                    args.chunk,
                    args.memory_gib,
                    args.disk_gib,
                )
            )
        )
        return
    sizes = [int(n) for n in args.sizes.split(",")]
    arms = args.arms.split(",")
    if (
        not args.out
        or not args.chrome
        or not set(arms) <= set(ARMS)
        or not math.isfinite(args.timeout)
        or not 0 < args.timeout <= 300
        or not math.isfinite(args.step_timeout)
        or not 0 < args.step_timeout <= 15
    ):
        p.error("out/chrome/known arms and finite phase <=300s / step <=15s timeouts required")
    # Reject before creating directories, files, subprocesses or source arrays.
    try:
        authority = [
            allocation_guard(n, args.profile, args.memory_gib, args.disk_gib) for n in sizes
        ]
    except ValueError as exc:
        p.error(str(exc))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    report = {
        "schema_version": 1,
        "experiment": "programmatic-equal-window-no-gesture-claim",
        "argv": sys.argv,
        "repetitions": args.repetitions,
        "arms": arms,
        "sizes": sizes,
        "profile": args.profile,
        "plot_css_px": [512, 512],
        "authority": authority,
        "environment": collect_environment_metadata(
            chromium=args.chrome,
            package_names=(
                "numpy",
                "plotly",
                "datashader",
                "hvplot",
                "holoviews",
                "bokeh",
                "panel",
                "pandas",
                "numba",
                "llvmlite",
                "tornado",
                "psutil",
                "websocket-client",
            ),
        ),
        "provenance_sha256": provenance(),
        "sources": {},
        "results": [],
        "timing_contract": {
            "cold": "fresh host/browser source admission/build and first correct stable paint; OS disk/JIT caches not flushed",
            "warm": "explicit programmatic range requests, never real-gesture latency",
            "axes_adopt_ms": "first observed matching browser axes since request start",
            "output_adopt_ms": "first observed adopted raster domain/revision, or exact subset covering and clipped to target axes",
            "paint_stable_ms": "first of ten stable readbacks with nonwhite opaque interior pixels (or zero for empty control)",
            "stability_confirmed_ms": "ten-frame verification overhead included; same browser performance.now clock",
            "copy_observations": "retained host arrays only, not a claim about all transient/native copies",
        },
        "runtime": {
            "temp_root": tempfile.gettempdir(),
            "thread_environment": {
                k: os.environ.get(k)
                for k in ("NUMBA_NUM_THREADS", "OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS")
            },
        },
        "limits": {
            "host_or_browser_timeout_s": args.timeout,
            "step_timeout_s": args.step_timeout,
            "rss_bytes_per_tree": int(args.memory_gib * 2**30),
            "rss_poll_ms": 50,
        },
        "historical_archive_commit": "51975d5d6f5c073e0a4b60a404f8349e45c6775c",
    }

    report["provenance_sha256"]["benchmarks/bench_density_comparison.py"] = (
        __import__("hashlib").sha256(Path(__file__).read_bytes()).hexdigest()
    )

    def save():
        args.out.write_text(json.dumps(report, indent=2))

    with tempfile.TemporaryDirectory(prefix="density-comparison-") as work:
        for n in sizes:
            directory = Path(work) / str(n)
            started = time.perf_counter()
            with tempfile.TemporaryFile(mode="w+", encoding="utf-8") as output:
                child = subprocess.Popen(
                    [
                        sys.executable,
                        __file__,
                        "--source-child",
                        str(directory),
                        "--child-n",
                        str(n),
                        "--profile",
                        args.profile,
                        "--chunk",
                        str(args.chunk),
                        "--memory-gib",
                        str(args.memory_gib),
                        "--disk-gib",
                        str(args.disk_gib),
                    ],
                    stdout=output,
                    stderr=subprocess.STDOUT,
                    text=True,
                )
                poller = TreePeakPoller(child.pid, int(args.memory_gib * 2**30))
                source_timed_out = False
                try:
                    child.wait(timeout=args.timeout)
                except subprocess.TimeoutExpired:
                    source_timed_out = True
                    child.kill()
                    child.wait()
                peak = poller.stop()
                output.seek(0)
                detail = output.read()
            if child.returncode or not (directory / "source.json").exists():
                for arm in arms:
                    for rep in range(args.repetitions):
                        report["results"].append(
                            {
                                "arm": arm,
                                "n": n,
                                "repetition": rep,
                                "status": "source_memory_limit"
                                if poller.limit_exceeded
                                else "source_timeout"
                                if source_timed_out
                                else "source_failed",
                                "detail": detail[-4000:],
                                "source_peak_rss_bytes": peak,
                            }
                        )
                save()
                if directory.exists():
                    shutil.rmtree(directory)
                continue
            source = json.loads((directory / "source.json").read_text())
            report["sources"][str(n)] = {
                **source,
                "creation_wall_ms": (time.perf_counter() - started) * 1000,
                "source_peak_rss_bytes": peak,
            }
            for arm in arms:
                for rep in range(args.repetitions):
                    row = run_arm(arm, directory / "source.json", args, rep)
                    report["results"].append(row)
                    save()
                    print(
                        json.dumps(
                            {
                                k: row.get(k)
                                for k in (
                                    "arm",
                                    "n",
                                    "repetition",
                                    "status",
                                    "host_peak_rss_bytes",
                                    "browser_peak_rss_bytes",
                                )
                            }
                        ),
                        flush=True,
                    )
            shutil.rmtree(directory)  # only this runner's own temporary source files
    save()
    print(args.out)


if __name__ == "__main__":
    main()
