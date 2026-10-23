#!/usr/bin/env python3
"""Independent, fixed structural gate for #11's bounded host reports.

Latency is advisory here; the real 100M authority owns the latency gate.
The producer cannot raise these limits by changing its report or assertions.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
POINTS = 1_000_000
FRAMES = 32
TILE_BUDGET = 2 << 20
GPU_BUDGET = 256 * 256 * 8  # count-only R8 fixture, eight screen textures
SOURCES = {
    "crates/xyg-engine/src/tile_store.rs",
    "crates/xyg-engine/src/tile_store/paint.rs",
    "crates/xyg-engine/src/tiles.rs",
    "crates/xyg-core/src/lib.rs",
}


def _number(value):
    return _integer(value) or (isinstance(value, float) and math.isfinite(value))


def _integer(value):
    return isinstance(value, int) and not isinstance(value, bool)


def _digest(value):
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def validate(report, *, check_local=False, expected_commit=None):
    errors = []

    def require(condition, message):
        if not condition:
            errors.append(message)

    if not isinstance(report, dict):
        return ["report must be an object"]
    require(report.get("schema_version") == 1, "schema_version must be 1")
    require(report.get("family") == "tier3_pyramid", "family must be tier3_pyramid")
    host = report.get("host")
    require(isinstance(host, str) and host in {"python", "node"}, "host must be python or node")
    require(report.get("n") == POINTS, f"n must be the bounded {POINTS}-row control")
    require(report.get("raw_xy_bytes") == POINTS * 16, "raw_xy_bytes must be 16N")
    require(
        report.get("resident_bytes") == 349_524, "resident pyramid must be the 256-square fixture"
    )
    require(report.get("compose_n") == FRAMES, "compose_n must be 32")
    require(report.get("budget_ok") is True, "budget_ok must be true")
    binnings = report.get("binnings")
    require(
        isinstance(binnings, list)
        and bool(binnings)
        and all(
            isinstance(s, str) and re.fullmatch(r"pyramid-L[0-8](?:-upsampled)?", s)
            for s in binnings
        ),
        "binnings must identify resident pyramid levels",
    )
    for name in ("build_ms", "compose_p95_ms"):
        require(
            _number(report.get(name)) and report[name] >= 0, f"{name} must be finite/nonnegative"
        )
    spill = report.get("spill")
    if not isinstance(spill, dict):
        return errors + ["spill must be an object"]
    for name in ("compose_oracle_frames", "tile_frames"):
        require(spill.get(name) == FRAMES, f"spill.{name} must be 32")
    for name in ("oracles_equal", "budget_ok"):
        require(spill.get(name) is True, f"spill.{name} must be true")
    samples = spill.get("tile_frame_samples_ms")
    require(
        isinstance(samples, list)
        and len(samples) == FRAMES
        and all(_number(s) and s >= 0 for s in samples),
        "spill.tile_frame_samples_ms must contain 32 finite/nonnegative samples",
    )
    for name in ("spill_ms", "tile_frame_p95_ms"):
        require(
            _number(spill.get(name)) and spill[name] >= 0,
            f"spill.{name} must be finite/nonnegative",
        )
    residency = spill.get("resident_samples_bytes")
    require(
        isinstance(residency, list)
        and len(residency) == FRAMES * 2
        and all(_integer(n) and 0 <= n <= TILE_BUDGET for n in residency),
        "all 64 compose/painter residency samples must fit the fixed 2 MiB budget",
    )
    for cached, uncached in (
        ("cached_transferred_tiles", "uncached_transferred_tiles"),
        ("cached_reply_bytes", "uncached_reply_bytes"),
    ):
        a, b = spill.get(cached), spill.get(uncached)
        require(
            _integer(a) and _integer(b) and 0 < a < b, f"spill.{cached} must be below {uncached}"
        )
    descriptors, gpu = spill.get("max_descriptors"), spill.get("max_gpu_bytes")
    require(
        _integer(descriptors) and 0 < descriptors <= 256, "tile descriptors must be bounded by 256"
    )
    require(
        spill.get("gpu_budget_bytes") == GPU_BUDGET,
        "GPU budget must remain eight R8 screen textures",
    )
    require(_integer(gpu) and 0 < gpu <= GPU_BUDGET, "GPU bytes exceed fixed budget")
    stats = spill.get("tiles")
    if not isinstance(stats, dict):
        return errors + ["spill.tiles must be an object"]
    require(stats.get("budget_bytes") == TILE_BUDGET, "CPU tile budget must remain 2 MiB")
    require(stats.get("over_budget") is False, "bounded fixture must not report over_budget")
    resident = stats.get("resident_bytes")
    require(
        _integer(resident) and 0 <= resident <= TILE_BUDGET, "tile residency exceeds fixed budget"
    )
    for name in ("hit", "miss", "spilled_bytes"):
        require(
            _integer(stats.get(name)) and stats[name] > 0, f"spill.tiles.{name} must be positive"
        )
    environment = report.get("environment")
    if not isinstance(environment, dict):
        return errors + ["environment must be an object"]
    git = environment.get("git") or {}
    commit = git.get("commit") if isinstance(git, dict) else None
    require(
        isinstance(commit, str) and re.fullmatch(r"[0-9a-f]{40}", commit),
        "environment.git.commit must be a SHA",
    )
    if expected_commit is not None:
        require(commit == expected_commit, "environment.git.commit differs from expected commit")
    require(
        isinstance(environment.get("platform"), dict) and bool(environment["platform"]),
        "environment.platform is required",
    )
    provenance = report.get("provenance")
    if not isinstance(provenance, dict):
        return errors + ["provenance must be an object"]
    require(
        _digest(provenance.get("native_sha256")), "native_sha256 must identify the measured core"
    )
    hashes = provenance.get("source_sha256")
    expected = SOURCES | (
        {"benchmarks/bench_tier3_pyramid.py", "python/xyg/_native.py"}
        if host == "python"
        else {"benchmarks/bench_tier3_pyramid_node.mjs", "packages/xy-node/src/pyramid.js"}
    )
    if not isinstance(hashes, dict):
        return errors + ["source_sha256 must be an object"]
    require(
        set(hashes) == expected,
        "source_sha256 must cover the harness and exact native producer inputs",
    )
    for name in expected:
        digest = hashes.get(name)
        require(_digest(digest), f"invalid source digest: {name}")
        if check_local:
            require(
                hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == digest,
                f"stale source digest: {name}",
            )
    return errors


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path)
    parser.add_argument("--check-local", action="store_true")
    parser.add_argument("--expect-commit")
    parser.add_argument(
        "--native", type=Path, help="also match the measured native library's bytes"
    )
    args = parser.parse_args()
    try:
        report = json.loads(args.report.read_text())
        errors = validate(report, check_local=args.check_local, expected_commit=args.expect_commit)
        if (
            args.native
            and not errors
            and hashlib.sha256(args.native.read_bytes()).hexdigest()
            != report["provenance"]["native_sha256"]
        ):
            errors.append("native library hash mismatch")
    except (OSError, ValueError) as exc:
        errors = [str(exc)]
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1
    print("bounded tier3 report ok (structural gate; latency advisory)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
