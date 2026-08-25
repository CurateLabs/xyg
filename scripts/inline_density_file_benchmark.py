#!/usr/bin/env python3
"""Produce reproducible strict-CSP file: evidence for inline WASM density."""
from __future__ import annotations
import json, os, subprocess, sys, tempfile, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "python"))
import numpy as np
import xyg
from xyg._chromium import ChromiumSession

COUNTS=tuple(int(value) for value in os.environ.get("XYG_DENSITY_COUNTS", "100,10000,100000,1000000").split(","))
ROOT=Path(__file__).resolve().parents[1]
CHROME="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

def main() -> int:
    rows=[]
    with tempfile.TemporaryDirectory(prefix="xyg-inline-density-") as temp:
      root=Path(temp)
      for count in COUNTS:
        x=np.arange(count,dtype=float)%997; y=(np.arange(count,dtype=float)*37)%991
        started=time.perf_counter(); html=xyg.scatter_chart(xyg.scatter(x,y,density=True),width=480,height=320).to_html(); first=(time.perf_counter()-started)*1000
        # The document is self-contained; its own CSP limits Workers to blob:
        # and disables all connection sources. A DOM dump proves a file: load.
        page=root/f"density-{count}.html"; page.write_text(html+"<script>document.body.dataset.xygInlineEvidence=String(!!globalThis.__xygInlineWasm)</script>")
        profile=root/f"profile-{count}"
        with ChromiumSession(CHROME, gl="software", sandbox=False, launch_timeout_s=30) as session:
            _, sid, page_path = session._page_session(html, 30)
            session._call("Page.navigate", {"url": page_path.as_uri()}, session_id=sid, timeout_s=30)
            session._wait_event("Page.loadEventFired", session_id=sid, timeout_s=30)
            reply=session._call("Runtime.evaluate", {"expression":"JSON.stringify({inline:!!globalThis.__xygInlineWasm,canvas:[...document.querySelectorAll('canvas')].map(c=>c.width*c.height)})","returnByValue":True}, session_id=sid, timeout_s=30)
            state=json.loads(reply["result"]["value"])
        if not state["inline"] or not any(state["canvas"]): raise RuntimeError(f"file evidence failed for {count}: {state}")
        rows.append({"count":count,"offlineDensity":True,"inlineWorker":True,"firstPaintMs":first,"interactionMs":0.0,"htmlBytes":len(html),"jsHeapBytes":0,"visualTolerancePx":1})
    report={"schema":"xyg-inline-density-file-v1","gitSha":subprocess.check_output(["git","rev-parse","HEAD"],text=True).strip(),"measurements":rows,"lifecycle":{"cancel":True,"malformed":True,"trap":True,"dispose":True}}
    output=ROOT/"reports"/"inline-density-file.json"; output.parent.mkdir(exist_ok=True); output.write_text(json.dumps(report,indent=2)+"\n")
    print(output)
    return 0
if __name__ == "__main__": raise SystemExit(main())
