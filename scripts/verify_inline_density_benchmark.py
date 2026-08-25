#!/usr/bin/env python3
"""Reject incomplete offline inline-density browser evidence."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

COUNTS = [100, 10_000, 100_000, 1_000_000]


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("report", type=Path)
    p.add_argument("--sha")
    a = p.parse_args()
    report = json.loads(a.report.read_text())
    if report.get("schema") != "xyg-inline-density-file-v1":
        raise SystemExit("unexpected inline density evidence schema")
    if a.sha and report.get("gitSha") != a.sha:
        raise SystemExit("inline density evidence SHA mismatch")
    rows = report.get("measurements")
    if (
        not isinstance(rows, list)
        or [r.get("count") for r in rows if isinstance(r, dict) and r.get("offlineDensity")]
        != COUNTS
    ):
        raise SystemExit("missing canonical offline density sizes")
    for row in rows:
        if not isinstance(row, dict) or not row.get("offlineDensity"):
            continue
        for key in (
            "firstPaintMs",
            "interactionMs",
            "htmlBytes",
            "jsHeapBytes",
            "rasterBytes",
            "visualTolerancePx",
        ):
            value = row.get(key)
            if (
                not isinstance(value, (int, float))
                or isinstance(value, bool)
                or not math.isfinite(value)
                or value < 0
            ):
                raise SystemExit(f"invalid {key}")
        if (
            row["htmlBytes"] <= 0
            or row["rasterBytes"] <= 1024
            or row["jsHeapBytes"] <= 0
            or row["visualTolerancePx"] > 1
            or row.get("inlineWorker") is not True
        ):
            raise SystemExit("offline density visual/payload/memory contract failed")
        observed = row.get("lifecycleObserved")
        if not isinstance(observed, list):
            raise SystemExit("offline density lifecycle observations are missing")
        phases = [event.get("phase") for event in observed if isinstance(event, dict)]
        if not {
            "attached",
            "density_ready",
            "cancelled",
            "home",
            "zoom",
            "revision",
            "malformed",
            "trap",
            "recovered",
            "disposed",
        }.issubset(phases):
            raise SystemExit("offline density lifecycle observations are incomplete")
        codes = {
            event.get("phase"): event.get("code") for event in observed if isinstance(event, dict)
        }
        if (
            codes.get("malformed") != "XYG_WASM_INVALID_ARGUMENT"
            or codes.get("trap") != "XYG_WASM_TRAP"
        ):
            raise SystemExit("offline density lifecycle errors are placeholders or wrong")
        if any(
            not isinstance(event.get("at"), (int, float))
            for event in observed
            if isinstance(event, dict)
        ):
            raise SystemExit("offline density lifecycle timestamps are missing")
        if (
            not isinstance(row.get("initialDiagnostics"), dict)
            or row["initialDiagnostics"].get("sequence") != 1
        ):
            raise SystemExit("offline density initial Rust revision is missing")
    print("validated four-size offline inline-density evidence")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
