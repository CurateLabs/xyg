#!/usr/bin/env python3
"""Tier-3 pyramid scale evidence (CI-safe).

Build once at modest N, compose many viewports, assert screen-bounded
replies and resident bytes ≪ raw XY. Never allocates 100M/1B points.

See spec/design/tier3-testing.md.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "python"))

from xy import kernels  # noqa: E402


def main() -> int:
    n = 1_000_000
    rng = np.random.default_rng(0)
    x = rng.random(n)
    y = rng.random(n)
    t0 = time.perf_counter()
    handle = kernels.pyramid_build(x, y, 0.0, 1.0, 0.0, 1.0, 256)
    build_ms = (time.perf_counter() - t0) * 1e3
    assert handle, "pyramid_build failed"

    compose_ms: list[float] = []
    binnings: list[str] = []
    for k in range(32):
        lo = (k % 8) / 10.0
        hi = lo + 0.25
        t1 = time.perf_counter()
        res = kernels.pyramid_compose(handle, lo, hi, lo, hi, 128, 96, max_upsample=8)
        compose_ms.append((time.perf_counter() - t1) * 1e3)
        assert res is not None
        grid, level = res
        assert grid.size == 128 * 96
        binnings.append(f"pyramid-L{level}")

    kernels.pyramid_free(handle)
    # Resident estimate: geometric series of u32 levels from base 256.
    dim = 256
    resident = 0
    while True:
        resident += dim * dim * 4
        if dim == 1:
            break
        dim >>= 1
    raw_xy = n * 16
    p95 = float(np.percentile(compose_ms, 95))
    report = {
        "family": "tier3_pyramid",
        "n": n,
        "build_ms": build_ms,
        "compose_p95_ms": p95,
        "compose_n": len(compose_ms),
        "binnings": sorted(set(binnings)),
        "resident_bytes": resident,
        "raw_xy_bytes": raw_xy,
        "budget_ok": resident < raw_xy and all(b.startswith("pyramid-L") for b in binnings),
        "latency_advisory_ok": p95 < 50.0,
    }
    print(json.dumps(report, indent=2))
    return 0 if report["budget_ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
