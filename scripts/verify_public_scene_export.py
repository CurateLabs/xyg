#!/usr/bin/env python3
"""Validate public Scene goldens and optional local export-baseline reports.

Without a report this recomputes the checked-in hexbin / heatmap / public-route
Scene SHA-256 values. With a report it also requires finite non-negative
timings and positive payload sizes for every required public route.
"""

from __future__ import annotations

import argparse
import json
import math
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BENCH = ROOT / "scripts" / "bench_public_scene_routes.py"
REQUIRED_ROUTES = (
    "hexbin_count",
    "hexbin_mean",
    "hexbin_sum",
    "heatmap",
    "scatter",
    "literal_geometry",
    "triangle_mesh",
    "violin_vertical",
    "box_vertical",
)
HEXBIN_SHA_KEYS = {
    "hexbin_count": "count",
    "hexbin_mean": "mean",
    "hexbin_sum": "sum",
}
PAYLOAD_KEYS = (
    "scene_bytes",
    "svg_bytes",
    "png_bytes",
    "pdf_bytes",
    "painter_bytes",
    "raster_command_bytes",
)
TIME_KEYS = ("scene_ms_median", "svg_ms_median", "png_ms_median", "pdf_ms_median")


def _finite_non_negative(value: object) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
        and value >= 0
    )


def _require_goldens() -> dict[str, object]:
    proc = subprocess.run(
        [sys.executable, str(BENCH), "--warmups", "0", "--reps", "1"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise SystemExit(proc.stderr or proc.stdout or "public Scene golden recompute failed")
    report = json.loads(proc.stdout)
    if report.get("schema") != "xyg-public-scene-export-v1":
        raise SystemExit("golden recompute used an unexpected schema")
    return report


def _validate_report(report: dict[str, object], *, fixture: dict[str, object]) -> None:
    if report.get("schema") != "xyg-public-scene-export-v1":
        raise SystemExit("unexpected public Scene export schema")
    if report.get("kind") != "public-scene-export-local":
        raise SystemExit("unexpected public Scene export kind")
    rows = report.get("rows")
    if not isinstance(rows, list):
        raise SystemExit("public Scene export rows must be a list")
    names = [row.get("route") for row in rows if isinstance(row, dict)]
    if list(names) != list(REQUIRED_ROUTES):
        raise SystemExit(f"public Scene export routes must be {REQUIRED_ROUTES}, got {names}")
    hexbin_shas = fixture["public_hexbin_sha256"]
    if not isinstance(hexbin_shas, dict):
        raise SystemExit("fixture public_hexbin_sha256 is missing")
    heatmap_sha = fixture.get("public_heatmap_sha256")
    if not isinstance(heatmap_sha, str) or len(heatmap_sha) != 64:
        raise SystemExit("fixture public_heatmap_sha256 is missing")
    for row in rows:
        if not isinstance(row, dict):
            raise SystemExit("public Scene export row must be an object")
        name = row["route"]
        if row.get("public") is not True:
            raise SystemExit(f"{name} is not marked public")
        for key in PAYLOAD_KEYS:
            value = row.get(key)
            if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
                raise SystemExit(f"{name} has invalid {key}")
        for key in TIME_KEYS:
            if not _finite_non_negative(row.get(key)):
                raise SystemExit(f"{name} has invalid {key}")
        digest = row.get("scene_sha256")
        if not isinstance(digest, str) or len(digest) != 64:
            raise SystemExit(f"{name} is missing a Scene SHA-256")
        expected = row.get("expected_scene_sha256")
        if name in HEXBIN_SHA_KEYS:
            golden = hexbin_shas[HEXBIN_SHA_KEYS[name]]
            if digest != golden or expected != golden:
                raise SystemExit(f"{name} Scene digest does not match the checked-in golden")
        elif name == "heatmap":
            if digest != heatmap_sha or expected != heatmap_sha:
                raise SystemExit(f"{name} Scene digest does not match the checked-in golden")
        elif expected is not None and expected != digest:
            raise SystemExit(f"{name} Scene digest does not match its expected golden")
        if row.get("painter_magic") != "XYPB":
            raise SystemExit(f"{name} painter is not the Scene browser consumer")
    if hexbin_shas.get("mean") != hexbin_shas.get("sum"):
        raise SystemExit("hexbin mean/sum goldens must share Scene bytes for this fixture")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path, nargs="?")
    parser.add_argument(
        "--recompute-goldens",
        action="store_true",
        help="recompute public Scene goldens even when a report is supplied",
    )
    args = parser.parse_args()
    fixture = json.loads((ROOT / "tests" / "fixtures" / "figure_scene_v3.json").read_text())
    if args.report is None or args.recompute_goldens:
        computed = _require_goldens()
        _validate_report(computed, fixture=fixture)
        print("validated public Scene goldens by recompute")
    if args.report is not None:
        report = json.loads(args.report.read_text())
        _validate_report(report, fixture=fixture)
        print(f"validated public Scene export report {args.report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
