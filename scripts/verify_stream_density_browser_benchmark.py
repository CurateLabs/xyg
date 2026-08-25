#!/usr/bin/env python3
"""Verify the main-only split-payload XYAS browser evidence artifact."""

import argparse
import json
from pathlib import Path

COUNTS = [100, 10_000, 100_000, 1_000_000]


def main():
    p = argparse.ArgumentParser()
    p.add_argument("report", type=Path)
    p.add_argument("--sha")
    a = p.parse_args()
    r = json.loads(a.report.read_text())
    if r.get("schema") != "xyg-hosted-stream-density-browser-v1" or (
        a.sha and r.get("gitSha") != a.sha
    ):
        raise SystemExit("invalid stream-density report")
    rows = r.get("measurements", [])
    if [x.get("count") for x in rows] != COUNTS:
        raise SystemExit("missing canonical stream-density sizes")
    for row in rows:
        if not all(
            row.get(k) is True
            for k in ("strictCsp", "cspNoNetwork", "moduleWorker", "sourceRetained")
        ):
            raise SystemExit("strict-CSP split transport was not proven")
        if any("density_view" in str(x) for x in row.get("sends", [])):
            raise SystemExit("kernel density_view escaped the WASM route")
        if (
            not isinstance(row.get("sourceBytes"), int)
            or row["sourceBytes"] <= 0
            or not isinstance(row.get("payloadBytes"), int)
            or row["payloadBytes"] <= 0
            or not isinstance(row.get("rasterBytes"), int)
            or row["rasterBytes"] <= 0
        ):
            raise SystemExit("typed source/payload/raster counters missing")
        for diag in (row.get("initialDiagnostics"), row.get("latest")):
            if not isinstance(diag, dict) or any(
                not isinstance(diag.get(k), int) or diag[k] < 0
                for k in (
                    "copyCount",
                    "copyBytesLo",
                    "copyBytesHi",
                    "arenaBytes",
                    "arenaHighWaterBytes",
                    "memoryBytes",
                    "memoryHighWaterBytes",
                )
            ):
                raise SystemExit("Rust counters missing")
        codes = {x.get("code") for x in row.get("events", []) if isinstance(x, dict)}
        if not {"XYG_WASM_RESOURCE_LIMIT", "XYG_WASM_TRAP"}.issubset(codes) or not isinstance(
            row.get("recovery"), int
        ):
            raise SystemExit("resource/trap/recovery lifecycle evidence missing")
        if (
            not isinstance(row.get("newest"), int)
            or row.get("oldRevision", row["newest"] - 1) >= row["newest"]
            or row.get("visible") != row["newest"]
            or row.get("disposed") is not None
        ):
            raise SystemExit("newest-only/cancel/dispose proof failed")
        if row["count"] == 1_000_000 and row.get("streamChunks", 0) <= 1:
            raise SystemExit("1M did not traverse multiple XYAS chunks")
    print("validated split-payload strict-CSP XYAS browser evidence")


if __name__ == "__main__":
    main()
