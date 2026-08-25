#!/usr/bin/env python3
"""Produce reproducible strict-CSP file: evidence for inline WASM density."""

from __future__ import annotations

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

COUNTS = tuple(
    int(value)
    for value in os.environ.get("XYG_DENSITY_COUNTS", "100,10000,100000,1000000").split(",")
)
ROOT = Path(__file__).resolve().parents[1]
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"


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
            first = (time.perf_counter() - started) * 1000
            # The document is self-contained; its own CSP limits Workers to blob:
            # and disables all connection sources. A DOM dump proves a file: load.
            page = root / f"density-{count}.html"
            page.write_text(
                html
                + "<script>document.body.dataset.xygInlineEvidence=String(!!globalThis.__xygInlineWasm)</script>"
            )
            with ChromiumSession(
                CHROME, gl="software", sandbox=False, launch_timeout_s=30
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
                    f"JSON.stringify({{inline:!!globalThis.__xygInlineWasm,canvas:[...document.querySelectorAll('canvas')].map(c=>c.width*c.height),rasterBytes:document.querySelector('canvas')?.toDataURL().length||0,jsHeapBytes:performance.memory?.usedJSHeapSize||0,evidence:globalThis.__xygStandaloneEvidence,initial:{json.dumps(initial)}}})",
                )
            if not state["inline"] or not any(state["canvas"]) or not state["evidence"]:
                raise RuntimeError(f"file evidence failed for {count}: {state}")
            phases = {
                event["phase"]: event["at"]
                for event in state["evidence"]
                if isinstance(event, dict) and isinstance(event.get("at"), (int, float))
            }
            interaction = max(
                0.0, float(phases.get("disposed", 0.0)) - float(phases.get("density_ready", 0.0))
            )
            rows.append(
                {
                    "count": count,
                    "offlineDensity": True,
                    "inlineWorker": True,
                    "firstPaintMs": first,
                    "interactionMs": interaction,
                    "htmlBytes": len(html),
                    "jsHeapBytes": state["jsHeapBytes"],
                    "rasterBytes": state["rasterBytes"],
                    "visualTolerancePx": 1,
                    "lifecycleObserved": state["evidence"],
                    "initialDiagnostics": state["initial"],
                }
            )
    report = {
        "schema": "xyg-inline-density-file-v1",
        "gitSha": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
        "measurements": rows,
    }
    output = ROOT / "reports" / "inline-density-file.json"
    output.parent.mkdir(exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n")
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
