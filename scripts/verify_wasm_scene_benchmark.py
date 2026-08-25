#!/usr/bin/env python3
"""Validate raw strict-CSP browser evidence for WASM Scene transport."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

EXPECTED_COUNTS = [100, 10_000, 100_000, 1_000_000]


def require_non_negative_metrics(
    row: dict[str, object], *, kind: str, keys: tuple[str, ...]
) -> None:
    for key in keys:
        value = row.get(key)
        if (
            not isinstance(value, (int, float))
            or isinstance(value, bool)
            or not math.isfinite(value)
            or value < 0
        ):
            raise SystemExit(f"{kind} browser evidence has invalid {key}")


def require_staging_copy(row: dict[str, object], *, kind: str) -> None:
    require_non_negative_metrics(
        row,
        kind=kind,
        keys=(
            "copyCount",
            "copyBytesLo",
            "copyBytesHi",
            "arenaHighWaterBytes",
            "memoryBytes",
            "memoryHighWaterBytes",
        ),
    )
    copied_bytes = row["copyBytesLo"] + row["copyBytesHi"] * (1 << 32)
    if row["copyCount"] < 1 or copied_bytes <= 0:
        raise SystemExit(f"{kind} browser evidence did not record its WASM staging copy")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("report", type=Path)
    parser.add_argument("--sha")
    args = parser.parse_args()
    report = json.loads(args.report.read_text(encoding="utf-8"))
    if report.get("schema") != "xyg-wasm-scene-browser-v3":
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
        require_non_negative_metrics(row, kind="typed-series", keys=("firstPaintMs",))
        require_staging_copy(row, kind="typed-series")
        if row.get("mainThreadRecordVisits") != 0 or row.get("framedSeries") != 1:
            raise SystemExit("typed-series browser evidence performed main-thread record work")
    authored = [row for row in rows if isinstance(row, dict) and row.get("authoredScene") is True]
    if [row.get("count") for row in authored] != EXPECTED_COUNTS:
        raise SystemExit("authored-Scene browser evidence is missing a canonical size")
    for row in authored:
        require_non_negative_metrics(
            row,
            kind="authored-Scene",
            keys=(
                "sceneBytes",
                "painterBytes",
                "workerPrepareMs",
                "hydrateUploadMs",
                "firstPaintMs",
                "browserVisualTolerancePx",
                "visibleCanvasPixels",
            ),
        )
        if row["sceneBytes"] <= 0 or row["painterBytes"] <= 0:
            raise SystemExit("authored-Scene browser evidence has an empty payload")
        if row["browserVisualTolerancePx"] > 1 or row["visibleCanvasPixels"] <= 0:
            raise SystemExit("authored-Scene browser evidence failed the visual-tolerance probe")
        require_staging_copy(row, kind="authored-Scene")
        for key in ("legendSemantics", "colorbarSemantics", "annotationSemantics"):
            if row.get(key) is not True:
                raise SystemExit(f"authored-Scene browser evidence is missing {key}")
    fragmented = [row for row in rows if isinstance(row, dict) and row.get("fragmented") is True]
    if (
        len(fragmented) != 1
        or fragmented[0].get("rejectedTraceLimit") != 1024
        or fragmented[0].get("browserChildren") != 0
    ):
        raise SystemExit("fragmentation evidence is missing or allocated browser painter state")
    print(
        "validated WASM browser evidence for "
        f"{len(typed)} typed-series and {len(authored)} authored-Scene sizes"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
