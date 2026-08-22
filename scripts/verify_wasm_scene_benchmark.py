#!/usr/bin/env python3
"""Validate raw strict-CSP typed-series browser evidence."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

EXPECTED_COUNTS = [100, 10_000, 100_000, 1_000_000]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("report", type=Path)
    parser.add_argument("--sha")
    args = parser.parse_args()
    report = json.loads(args.report.read_text(encoding="utf-8"))
    if report.get("schema") != "xyg-wasm-scene-browser-v2":
        raise SystemExit("unexpected WASM browser benchmark schema")
    if args.sha and report.get("gitSha") != args.sha:
        raise SystemExit("WASM browser benchmark SHA does not match the hosted checkout")
    rows = report.get("measurements")
    if not isinstance(rows, list):
        raise SystemExit("WASM browser benchmark measurements must be a list")
    typed = [row for row in rows if isinstance(row, dict) and row.get("typedSeries") is True]
    if [row.get("count") for row in typed] != EXPECTED_COUNTS:
        raise SystemExit("typed-series browser evidence is missing a canonical size")
    for row in typed:
        for key in (
            "firstPaintMs",
            "copyCount",
            "copyBytesLo",
            "copyBytesHi",
            "arenaHighWaterBytes",
            "memoryBytes",
            "memoryHighWaterBytes",
        ):
            value = row.get(key)
            if (
                not isinstance(value, (int, float))
                or isinstance(value, bool)
                or not math.isfinite(value)
                or value < 0
            ):
                raise SystemExit(f"typed-series browser evidence has invalid {key}")
        if row.get("mainThreadRecordVisits") != 0 or row.get("framedSeries") != 1:
            raise SystemExit("typed-series browser evidence performed main-thread record work")
        copied_bytes = row["copyBytesLo"] + row["copyBytesHi"] * (1 << 32)
        if row["copyCount"] < 1 or copied_bytes <= 0:
            raise SystemExit("typed-series browser evidence did not record its WASM staging copy")
    fragmented = [row for row in rows if isinstance(row, dict) and row.get("fragmented") is True]
    if (
        len(fragmented) != 1
        or fragmented[0].get("rejectedTraceLimit") != 1024
        or fragmented[0].get("browserChildren") != 0
    ):
        raise SystemExit("fragmentation evidence is missing or allocated browser painter state")
    print(f"validated WASM browser evidence for {len(typed)} typed-series sizes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
