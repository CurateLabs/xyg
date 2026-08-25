#!/usr/bin/env python3
"""Strict-CSP browser evidence for the split-payload ``XYAS`` density path.

This is deliberately a wall-clock/lifecycle report, not a CodSpeed benchmark.
It starts a loopback-only package host, hydrates a real ``ChartView`` from the
Python host's ``build_payload_split`` buffers, and attaches the packaged module
Worker through the public density API.  No kernel endpoint is present.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))
import xyg  # noqa: E402
from xyg._chromium import ChromiumSession  # noqa: E402
from xyg.export import find_chromium  # noqa: E402

COUNTS = tuple(
    int(v) for v in os.environ.get("XYG_DENSITY_COUNTS", "100,10000,100000,1000000").split(",")
)
CSP = "; ".join(
    (
        "default-src 'none'",
        "script-src 'self' 'wasm-unsafe-eval'",
        "worker-src 'self'",
        "connect-src 'self'",
        "object-src 'none'",
        "base-uri 'none'",
    )
)
ASSETS = {
    "/packages/xy-client/dist/index.js": ROOT / "packages/xy-client/dist/index.js",
    "/packages/xy-client/dist/wasm-worker.js": ROOT / "packages/xy-client/dist/wasm-worker.js",
    "/packages/xy-client/dist/xyg-wasm.wasm": ROOT / "packages/xy-client/dist/xyg-wasm.wasm",
}


def chrome_path(explicit: str | None) -> str:
    if found := find_chromium(explicit):
        return found
    found = subprocess.check_output(
        ["node", "-e", "process.stdout.write(require('playwright').chromium.executablePath())"],
        text=True,
    ).strip()
    if not Path(found).is_file():
        raise RuntimeError("Chromium or Playwright Chromium is required")
    return found


def evidence_module(spec: dict, buffers: list[memoryview]) -> str:
    encoded = [base64.b64encode(bytes(buffer)).decode("ascii") for buffer in buffers]
    return f"""
globalThis.__xygStreamFailures=[]; addEventListener("error",e=>globalThis.__xygStreamFailures.push(String(e.error||e.message))); addEventListener("unhandledrejection",e=>globalThis.__xygStreamFailures.push(String(e.reason)));
import {{ChartView, createXygWasmWorker, attachWasmDensity}} from "/packages/xy-client/dist/index.js";
const spec={json.dumps(spec, separators=(",", ":"))};
const b64={json.dumps(encoded)};
const buffers=b64.map(s=>{{const raw=atob(s), out=new Uint8Array(raw.length);for(let i=0;i<raw.length;i++)out[i]=raw.charCodeAt(i);return out;}});
const sends=[]; const events=[];
const comm={{send:m=>sends.push(m),onMessage:()=>()=>{{}},wantsViewChange:()=>false}};
const view=new ChartView(document.getElementById("chart"),spec,buffers,comm);
view.root.addEventListener("xy:wasm_density_error",e=>events.push(e.detail));
const source=spec.wasm_density.source;
const x=view._columnView(view._payload,spec.columns[source.x]), y=view._columnView(view._payload,spec.columns[source.y]);
const options={{workerUrl:"/packages/xy-client/dist/wasm-worker.js",wasm:"/packages/xy-client/dist/xyg-wasm.wasm",maxArenaBytes:402653184,evidenceCapability:"strict-csp-stream-evidence"}};
let worker=createXygWasmWorker(options);
let handle;
try {{
// A missing module-worker response is itself lifecycle evidence; surface its
// captured page errors rather than letting the host harness wait for Chrome's
// global timeout.
handle=await Promise.race([
  attachWasmDensity(view,{{worker,input:{{traceId:source.trace_id,x,y}},workerOwnership:"own",delay:0,streamSource:true}}),
  new Promise((_,reject)=>setTimeout(()=>reject(new Error("module worker did not initialize within 10s")),10000)),
]);
let paints=0, rendered=0; const old=view._applySampleRebinGrid.bind(view); view._applySampleRebinGrid=(...a)=>{{paints++;rendered=handle.diagnostics()?.sequence||rendered;return old(...a)}};
const wait=async f=>{{for(let i=0;i<800;i++){{if(f())return;await new Promise(r=>setTimeout(r,25));}}throw Error("timed out");}};
const schedule=v=>handle.schedule(v,{{delay:0,force:true}});
const initial=schedule(view.view); await wait(()=>handle.diagnostics()?.sequence===initial);
const initialDiagnostics=handle.diagnostics(); const initialPaint=paints;
const cancelRevision=schedule({{...view.view,x0:view.view.x0+.1,x1:view.view.x1-.1}}); handle.cancel();
const oldRevision=schedule({{...view.view,x0:view.view.x0+.2,x1:view.view.x1-.2}}); const newest=schedule({{...view.view,x0:view.view.x0+.3,x1:view.view.x1-.3}}); await wait(()=>handle.diagnostics()?.sequence===newest);
const latest=handle.diagnostics(); const payload=view.gpuTraces[0].density;
try {{await handle.evidenceLifecycle("stream_resource")}} catch (_) {{}}
await wait(()=>events.some(e=>e.code==="XYG_WASM_RESOURCE_LIMIT"));
try {{await handle.evidenceLifecycle("trap")}} catch (_) {{}}
await wait(()=>events.some(e=>e.code==="XYG_WASM_TRAP"));
worker=createXygWasmWorker(options); handle=await attachWasmDensity(view,{{worker,input:{{traceId:source.trace_id,x,y}},workerOwnership:"own",delay:0,streamSource:true}}); const recovery=schedule(view.view); await wait(()=>handle.diagnostics()?.sequence===recovery);
const raster=document.querySelector("canvas")?.toDataURL()||"";
await handle.dispose(); view.destroy();
globalThis.__xygStreamEvidence={{initial, cancelRevision, oldRevision, newest, recovery, initialDiagnostics, latest, paints, initialPaint, visible:latest.sequence, rendered, events, sends, sourceBytes:x.byteLength+y.byteLength, sourceRetained:x.byteLength>0&&y.byteLength>0, chunkPoints:32768, payloadBytes:(payload?.grid?.byteLength||0)+(payload?.rgba?.byteLength||0), disposed:null, raster, csp:document.policy?.allowedFeatures||null}};
}} catch (error) {{
globalThis.__xygStreamEvidence={{failure:String(error?.stack||error), failures:globalThis.__xygStreamFailures, events, sends, sourceBytes:x.byteLength+y.byteLength, sourceRetained:x.byteLength>0&&y.byteLength>0}};
}}
"""


def evaluate(session, sid: str) -> dict:
    reply = session._call(
        "Runtime.evaluate",
        {
            "expression": "JSON.stringify(globalThis.__xygStreamEvidence||null)",
            "returnByValue": True,
            "awaitPromise": True,
        },
        session_id=sid,
        timeout_s=30,
    )
    value = reply.get("result", {}).get("value")
    return json.loads(value) if isinstance(value, str) else {}


def evidence_handler(body: str, module: str, requests: list[str]) -> type[BaseHTTPRequestHandler]:
    """Bind one evidence response set without closing over a ladder iteration."""

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_: object) -> None:
            return

        def do_GET(self) -> None:
            requests.append(self.path)
            self.send_response(200)
            self.send_header("Content-Security-Policy", CSP)
            self.send_header("Cache-Control", "no-store")
            if self.path == "/":
                data = body.encode()
                kind = "text/html"
            elif self.path == "/evidence.js":
                data = module.encode()
                kind = "text/javascript"
            elif self.path in ASSETS:
                data = ASSETS[self.path].read_bytes()
                kind = "application/wasm" if self.path.endswith(".wasm") else "text/javascript"
            else:
                self.send_response(404)
                self.end_headers()
                return
            self.send_header("Content-Type", kind)
            self.end_headers()
            self.wfile.write(data)

    return Handler


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--chrome")
    args = ap.parse_args()
    missing = [str(p) for p in ASSETS.values() if not p.is_file()]
    if missing:
        raise RuntimeError(f"build browser assets first: {missing}")
    rows = []
    for count in COUNTS:
        x = np.arange(count, dtype=float) % 997
        y = (np.arange(count, dtype=float) * 37) % 991
        spec, buffers = (
            xyg.scatter_chart(xyg.scatter(x, y, density=True), width=480, height=320)
            .figure()
            .build_payload_split()
        )
        if (
            spec.get("buffer_layout") != "split"
            or spec.get("wasm_density", {}).get("source", {}).get("kind")
            != "cartesian-count-f64-stream-v1"
        ):
            raise RuntimeError("host did not emit the split XYAS source contract")
        module = evidence_module(spec, buffers)
        # The evidence program must be a same-origin module: an inline module
        # would violate this deliberately strict `script-src 'self'` policy.
        body = '<!doctype html><div id="chart"></div><script type="module" src="/evidence.js"></script>'
        requests: list[str] = []

        server = ThreadingHTTPServer(("127.0.0.1", 0), evidence_handler(body, module, requests))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with ChromiumSession(
                chrome_path(args.chrome), gl="software", sandbox=False, launch_timeout_s=30
            ) as browser:
                _, sid, _ = browser._page_session("<html></html>", 30)
                browser._call(
                    "Page.navigate",
                    {"url": f"http://127.0.0.1:{server.server_address[1]}/"},
                    session_id=sid,
                    timeout_s=30,
                )
                deadline = time.monotonic() + 90
                state = {}
                while time.monotonic() < deadline:
                    state = evaluate(browser, sid)
                    if state:
                        break
                    time.sleep(0.1)
                if not state:
                    debug = browser._call(
                        "Runtime.evaluate",
                        {
                            "expression": "JSON.stringify(globalThis.__xygStreamFailures||[])",
                            "returnByValue": True,
                        },
                        session_id=sid,
                        timeout_s=30,
                    )
                    raise RuntimeError(
                        f"stream evidence did not finish: requests={requests}, failures={debug.get('result', {}).get('value')}"
                    )
        finally:
            server.shutdown()
            server.server_close()
        if state.get("failure"):
            raise RuntimeError(
                f"stream evidence browser failure: {state['failure']}; failures={state.get('failures')}; events={state.get('events')}; requests={requests}"
            )
        allowed = {"/", "/evidence.js", *ASSETS}
        state.update(
            {
                "count": count,
                "strictCsp": True,
                # The loopback host exposes only the document, same-origin evidence
                # module, packaged module Worker, and explicit WASM asset.  Any
                # other request is a real network-route violation, not a test fake.
                "cspNoNetwork": all(path in allowed for path in requests),
                "moduleWorker": requests.count("/packages/xy-client/dist/wasm-worker.js") >= 2,
                "requests": requests,
                "htmlBytes": len(body),
                "htmlSha256": hashlib.sha256(body.encode()).hexdigest(),
                "rasterBytes": len(state.get("raster", "")),
                "streamChunks": (count + 32767) // 32768,
            }
        )
        state.pop("raster", None)
        rows.append(state)
    report = {
        "schema": "xyg-hosted-stream-density-browser-v1",
        "gitSha": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
        "measurements": rows,
    }
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
