#!/usr/bin/env python3
"""Reject incomplete offline inline-density browser evidence."""
from __future__ import annotations
import argparse, json, math
from pathlib import Path

COUNTS = [100, 10_000, 100_000, 1_000_000]

def main() -> int:
    p = argparse.ArgumentParser(); p.add_argument("report", type=Path); p.add_argument("--sha")
    a = p.parse_args(); report = json.loads(a.report.read_text())
    if report.get("schema") != "xyg-inline-density-file-v1": raise SystemExit("unexpected inline density evidence schema")
    if a.sha and report.get("gitSha") != a.sha: raise SystemExit("inline density evidence SHA mismatch")
    rows = report.get("measurements")
    if not isinstance(rows, list) or [r.get("count") for r in rows if isinstance(r, dict) and r.get("offlineDensity")] != COUNTS: raise SystemExit("missing canonical offline density sizes")
    for row in rows:
        if not isinstance(row, dict) or not row.get("offlineDensity"): continue
        for key in ("firstPaintMs", "interactionMs", "htmlBytes", "jsHeapBytes", "visualTolerancePx"):
            value=row.get(key)
            if not isinstance(value,(int,float)) or isinstance(value,bool) or not math.isfinite(value) or value < 0: raise SystemExit(f"invalid {key}")
        if row["htmlBytes"] <= 0 or row["visualTolerancePx"] > 1 or row.get("inlineWorker") is not True: raise SystemExit("offline density visual/payload contract failed")
    lifecycle=report.get("lifecycle")
    if not isinstance(lifecycle,dict) or not all(lifecycle.get(key) is True for key in ("cancel","malformed","trap","dispose")): raise SystemExit("offline density lifecycle evidence is incomplete")
    print("validated four-size offline inline-density evidence")
    return 0
if __name__ == "__main__": raise SystemExit(main())
