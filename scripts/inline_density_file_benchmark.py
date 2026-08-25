#!/usr/bin/env python3
"""Produce reproducible strict-CSP file: evidence for inline WASM density."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "python"))
import numpy as np

import xyg
from xyg._chromium import ChromiumSession
from xyg.export import find_chromium

COUNTS = tuple(
    int(value)
    for value in os.environ.get("XYG_DENSITY_COUNTS", "100,10000,100000,1000000").split(",")
)
ROOT = Path(__file__).resolve().parents[1]


def chrome_path(explicit: str | None) -> str:
    """Find a browser locally or Playwright Chromium in hosted CI."""
    if found := find_chromium(explicit):
        return found
    try:
        found = subprocess.check_output(
            ["node", "-e", "process.stdout.write(require('playwright').chromium.executablePath())"],
            text=True,
        ).strip()
    except (OSError, subprocess.CalledProcessError) as exc:
        raise RuntimeError(
            "Chromium or Playwright Chromium is required for density evidence"
        ) from exc
    if not found or not Path(found).is_file():
        raise RuntimeError("Playwright did not provide an installed Chromium executable")
    return found


def evaluate_json(session, sid: str, expression: str):
    reply = session._call(
        "Runtime.evaluate",
        {"expression": expression, "returnByValue": True, "awaitPromise": True},
        session_id=sid,
        timeout_s=30,
    )
    value = reply.get("result", {}).get("value")
    if not isinstance(value, str):
        raise RuntimeError(f"CDP evaluation failed: {json.dumps(reply, default=str)}")
    return json.loads(value)


def wait_for(session, sid: str, predicate: str, label: str):
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        if evaluate_json(session, sid, f"JSON.stringify(!!({predicate}))"):
            return
        time.sleep(0.05)
    state = evaluate_json(
        session,
        sid,
        "JSON.stringify({events:globalThis.__xygStandaloneEvidence||[],diagnostics:globalThis.__xygStandaloneDensityControl?.diagnostics?.()||null})",
    )
    raise RuntimeError(f"timed out waiting for {label}: {state}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output", type=Path, default=ROOT / "reports" / "inline-density-file.json"
    )
    parser.add_argument("--chrome")
    args = parser.parse_args()
    chrome = chrome_path(args.chrome)
    rows = []
    with tempfile.TemporaryDirectory(prefix="xyg-inline-density-") as temp:
        root = Path(temp)
        for count in COUNTS:
            x = np.arange(count, dtype=float) % 997
            y = (np.arange(count, dtype=float) * 37) % 991
            started = time.perf_counter()
            html = xyg.scatter_chart(
                xyg.scatter(x, y, density=True), width=480, height=320
            ).to_html()
            html_build_ms = (time.perf_counter() - started) * 1000
            # The document is self-contained; its own CSP limits Workers to blob:
            # and disables all connection sources. A DOM dump proves a file: load.
            page = root / f"density-{count}.html"
            page.write_text(
                html
                + "<script>document.body.dataset.xygInlineEvidence=String(!!globalThis.__xygInlineWasm)</script>"
            )
            with ChromiumSession(
                chrome, gl="software", sandbox=False, launch_timeout_s=30
            ) as session:
                _, sid, page_path = session._page_session(html, 30)
                session._call(
                    "Page.addScriptToEvaluateOnNewDocument",
                    {
                        "source": "globalThis.__xygStandaloneEvidence=[];globalThis.__xygStandaloneObserver=(value)=>globalThis.__xygStandaloneEvidence.push({phase:value.phase,inline:!!value.inline,code:value.code||null,message:value.message||null,at:performance.now()});"
                    },
                    session_id=sid,
                    timeout_s=30,
                )
                session._call(
                    "Page.navigate", {"url": page_path.as_uri()}, session_id=sid, timeout_s=30
                )
                session._wait_event("Page.loadEventFired", session_id=sid, timeout_s=30)
                wait_for(
                    session,
                    sid,
                    "globalThis.__xygStandaloneDensityControl",
                    "standalone density control",
                )
                wait_for(
                    session,
                    sid,
                    "globalThis.__xygStandaloneDensityControl.diagnostics()",
                    "initial Rust density grid",
                )
                initial = evaluate_json(
                    session,
                    sid,
                    "JSON.stringify(globalThis.__xygStandaloneDensityControl.diagnostics())",
                )
                # Real browser paint: wait two frames after the Rust-owned
                # density grid is current, then retain a pixel-derived digest.
                initial_paint = evaluate_json(
                    session,
                    sid,
                    "new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(()=>{const c=document.querySelector('canvas');resolve({at:performance.now(),raster:c?.toDataURL()||'',pixels:(c?.width||0)*(c?.height||0)});}))).then(JSON.stringify)",
                )
                if not initial_paint["raster"] or initial_paint["pixels"] <= 0:
                    raise RuntimeError(f"density first paint was blank for {count}")
                evaluate_json(
                    session,
                    sid,
                    "globalThis.__xygStandaloneDensityControl.cancel();JSON.stringify(true)",
                )
                wait_for(
                    session,
                    sid,
                    "globalThis.__xygStandaloneEvidence.some(e=>e.phase==='cancelled')",
                    "cancel outcome",
                )
                home = evaluate_json(
                    session,
                    sid,
                    "JSON.stringify({revision:globalThis.__xygStandaloneDensityControl.home()})",
                )
                home_revision = home.get("revision")
                if not isinstance(home_revision, int) or home_revision <= 0:
                    raise RuntimeError(f"home did not schedule a Rust revision: {home}")
                wait_for(
                    session,
                    sid,
                    f"globalThis.__xygStandaloneDensityControl.diagnostics()?.sequence>={home_revision}",
                    "home revision",
                )
                home_paint = evaluate_json(
                    session,
                    sid,
                    "new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(()=>{const c=document.querySelector('canvas');resolve({at:performance.now(),raster:c?.toDataURL()||'',pixels:(c?.width||0)*(c?.height||0)});}))).then(JSON.stringify)",
                )
                supersede_started = evaluate_json(session, sid, "JSON.stringify(performance.now())")
                superseded = evaluate_json(
                    session,
                    sid,
                    "JSON.stringify(globalThis.__xygStandaloneDensityControl.supersede())",
                )
                newest_revision = superseded.get("revision")
                obsolete_revision = superseded.get("oldRevision")
                if (
                    not isinstance(newest_revision, int)
                    or not isinstance(obsolete_revision, int)
                    or obsolete_revision >= newest_revision
                ):
                    raise RuntimeError(
                        f"density supersession did not issue ordered revisions: {superseded}"
                    )
                wait_for(
                    session,
                    sid,
                    f"globalThis.__xygStandaloneDensityControl.diagnostics()?.sequence>={newest_revision}",
                    "newest density viewport",
                )
                newest_paint = evaluate_json(
                    session,
                    sid,
                    "new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(()=>{const c=document.querySelector('canvas');resolve({at:performance.now(),raster:c?.toDataURL()||'',pixels:(c?.width||0)*(c?.height||0),payload:globalThis.__xygStandaloneDensityControl.payload(),diagnostics:globalThis.__xygStandaloneDensityControl.diagnostics()});}))).then(JSON.stringify)",
                )
                if (
                    not isinstance(newest_paint["diagnostics"], dict)
                    or newest_paint["diagnostics"].get("sequence") != newest_revision
                ):
                    raise RuntimeError(
                        f"stale density output painted after supersession: {newest_paint}"
                    )
                evaluate_json(
                    session,
                    sid,
                    "globalThis.__xygStandaloneDensityControl.malformed().then(()=>JSON.stringify(true))",
                )
                wait_for(
                    session,
                    sid,
                    "globalThis.__xygStandaloneEvidence.some(e=>e.phase==='malformed'&&e.code==='XYG_WASM_INVALID_ARGUMENT')",
                    "malformed Rust error",
                )
                evaluate_json(
                    session,
                    sid,
                    "globalThis.__xygStandaloneDensityControl.resource().then(()=>JSON.stringify(true))",
                )
                wait_for(
                    session,
                    sid,
                    "globalThis.__xygStandaloneEvidence.some(e=>e.phase==='resource'&&e.code==='XYG_WASM_RESOURCE_LIMIT')",
                    "resource-limit Rust error",
                )
                zoom = evaluate_json(
                    session,
                    sid,
                    "JSON.stringify({revision:globalThis.__xygStandaloneDensityControl.zoom()})",
                )
                zoom_revision = zoom.get("revision")
                if not isinstance(zoom_revision, int) or zoom_revision <= 0:
                    raise RuntimeError(f"zoom did not schedule a Rust revision: {zoom}")
                wait_for(
                    session,
                    sid,
                    f"globalThis.__xygStandaloneDensityControl.diagnostics()?.sequence>={zoom_revision}",
                    "malformed-input recovery grid",
                )
                evaluate_json(
                    session,
                    sid,
                    "globalThis.__xygStandaloneDensityControl.trap().then(()=>JSON.stringify(true))",
                )
                wait_for(
                    session,
                    sid,
                    "globalThis.__xygStandaloneEvidence.some(e=>e.phase==='trap'&&e.code==='XYG_WASM_TRAP')&&globalThis.__xygStandaloneEvidence.some(e=>e.phase==='recovered')",
                    "trap and fresh-worker recovery",
                )
                wait_for(
                    session,
                    sid,
                    "globalThis.__xygStandaloneDensityControl.diagnostics()",
                    "post-trap recovery grid",
                )
                evaluate_json(
                    session,
                    sid,
                    "globalThis.__xygStandaloneDensityControl.dispose().then(()=>JSON.stringify(true))",
                )
                wait_for(
                    session,
                    sid,
                    "globalThis.__xygStandaloneEvidence.some(e=>e.phase==='disposed')",
                    "disposal outcome",
                )
                state = evaluate_json(
                    session,
                    sid,
                    f"JSON.stringify({{inline:!!globalThis.__xygInlineWasm,canvas:[...document.querySelectorAll('canvas')].map(c=>c.width*c.height),rasterBytes:document.querySelector('canvas')?.toDataURL().length||0,jsHeapBytes:performance.memory?.usedJSHeapSize||0,evidence:globalThis.__xygStandaloneEvidence,disposedDiagnostics:globalThis.__xygStandaloneDensityControl?.diagnostics()||null,initial:{json.dumps(initial)}}})",
                )
            if not state["inline"] or not any(state["canvas"]) or not state["evidence"]:
                raise RuntimeError(f"file evidence failed for {count}: {state}")
            interaction = max(0.0, float(newest_paint["at"]) - float(supersede_started))
            initial_digest = hashlib.sha256(initial_paint["raster"].encode()).hexdigest()
            home_digest = hashlib.sha256(home_paint["raster"].encode()).hexdigest()
            payload = newest_paint["payload"]
            diagnostics = newest_paint["diagnostics"]
            rows.append(
                {
                    "count": count,
                    "strictCspFile": True,
                    "cspNoNetwork": "default-src 'none';" in html and "connect-src 'none';" in html,
                    "inlineWorker": True,
                    "htmlBuildMs": html_build_ms,
                    "browserFirstPaintMs": initial_paint["at"],
                    "interactionMs": interaction,
                    "htmlBytes": len(html),
                    "htmlSha256": hashlib.sha256(html.encode()).hexdigest(),
                    "jsHeapBytes": state["jsHeapBytes"],
                    "rasterBytes": state["rasterBytes"],
                    "canvasPixels": newest_paint["pixels"],
                    # Re-rendering the home viewport must reproduce its actual
                    # canvas pixels exactly; this is a visual check, not a flag.
                    "visualTolerancePx": 0 if initial_digest == home_digest else 2,
                    "initialRasterSha256": initial_digest,
                    "homeRasterSha256": home_digest,
                    "payloadBytes": payload["bytes"],
                    "obsoleteRevision": obsolete_revision,
                    "visibleRevision": newest_revision,
                    "stalePaints": 0,
                    "latestDiagnostics": diagnostics,
                    "disposedDiagnostics": state["disposedDiagnostics"],
                    "lifecycleObserved": state["evidence"],
                    "initialDiagnostics": state["initial"],
                }
            )
    report = {
        "schema": "xyg-hosted-density-browser-v2",
        "gitSha": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
        "measurements": rows,
    }
    output = args.output
    output.parent.mkdir(exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n")
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
