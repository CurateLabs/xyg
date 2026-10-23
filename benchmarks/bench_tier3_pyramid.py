#!/usr/bin/env python3
"""Tier-3 pyramid scale evidence (CI-safe).

Build once at modest N, compose many viewports, assert screen-bounded
replies and resident bytes ≪ raw XYG. Never allocates 100M/1B points.

See spec/design/tier3-testing.md.
"""

from __future__ import annotations

import hashlib
import json
import struct
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "python"))
sys.path.insert(0, str(ROOT))

from benchmarks.environment import collect_environment_metadata  # noqa: E402
from xyg import _native, kernels  # noqa: E402


def spill_evidence(x: np.ndarray, y: np.ndarray) -> dict:
    """Bounded #11 structure/oracles; timings are not the dedicated 100M gate."""
    handle = kernels.pyramid_build(x, y, 0.0, 1.0, 0.0, 1.0, 1024)
    assert handle
    store = 0
    budget = 2 << 20
    resident_samples = []
    windows = [(k / 8, k / 8 + 0.5, 0.0, 0.5) for k in [0, 1, 2, 3, 4, 3, 2, 1] * 4]
    try:
        start = time.perf_counter()
        store = kernels.pyramid_spill(handle)
        spill_ms = (time.perf_counter() - start) * 1e3
        assert store
        assert kernels.tile_budget_set(budget)
        for window in windows:
            expected = kernels.pyramid_compose(handle, *window, 128, 96, max_upsample=8)
            actual = kernels.tile_store_compose(store, *window, 128, 96, max_upsample=8)
            assert expected is not None and actual is not None
            assert expected[1] == actual[1]
            np.testing.assert_array_equal(actual[0], expected[0])
            resident_samples.append(kernels.tile_store_stats(store)[2])
            assert resident_samples[-1] <= budget
        assert kernels.pyramid_free(handle)
        handle = 0

        def frame(packet: bytes, pool: dict) -> tuple[dict, dict]:
            assert packet[:8] == b"XYDT\x01\0\0\0"
            level, flags, count, active, missing, stride = struct.unpack_from("<6I", packet, 8)
            assert stride == 96 and 0 < active <= count <= 256
            generation = struct.unpack_from("<Q", packet, 32)[0]
            gpu_budget, gpu_bytes = struct.unpack_from("<2I", packet, 64)
            assert gpu_budget == 256 * 256 * (4 if flags & 1 else 1) * 8
            assert gpu_bytes <= gpu_budget
            kept, active_hashes, keys = {}, [], []
            transferred = logical = 0
            for index in range(count):
                at = 128 + index * stride
                lev, tx, ty, width, height, offset, length, visible = struct.unpack_from(
                    "<8I", packet, at
                )
                key = (generation, lev, tx, ty)
                keys.append((lev, tx, ty))
                logical += width * height * (4 if flags & 1 else 1)
                if length:
                    assert offset >= 128 + count * stride and offset + length <= len(packet)
                    assert length == width * height * (4 if flags & 1 else 1)
                    kept[key] = hashlib.sha256(packet[offset : offset + length]).hexdigest()
                    transferred += 1
                else:
                    assert key in pool, "Rust omitted a tile not held by the client"
                    kept[key] = pool[key]
                if index < active:
                    assert visible == 1 and lev == level
                    active_hashes.append((key, kept[key]))
            assert transferred == missing and logical == gpu_bytes
            return kept, {
                "generation": generation,
                "level": level,
                "keys": keys,
                "active": active_hashes,
                "normalization": packet[40:56],
                "transferred": transferred,
                "bytes": len(packet),
                "descriptors": count,
                "gpu_bytes": gpu_bytes,
                "gpu_budget": gpu_budget,
            }

        pool, state, observed, times = {}, None, [], []
        for window in windows:
            started = time.perf_counter()
            packet = kernels.tile_store_paint(
                store,
                *window,
                256,
                256,
                known_generation=state["generation"] if state else 0,
                previous_level=state["level"] if state else -1,
                known_keys=state["keys"] if state else (),
            )
            times.append((time.perf_counter() - started) * 1e3)
            assert packet is not None
            pool, state = frame(packet, pool)
            observed.append(state)
            resident_samples.append(kernels.tile_store_stats(store)[2])
            assert resident_samples[-1] <= budget
        uncached_tiles = uncached_bytes = 0
        for window, cached in zip(windows, observed, strict=True):
            packet = kernels.tile_store_paint(store, *window, 256, 256)
            assert packet is not None
            _, oracle = frame(packet, {})
            assert oracle["active"] == cached["active"]
            assert oracle["normalization"] == cached["normalization"]
            uncached_tiles += oracle["transferred"]
            uncached_bytes += oracle["bytes"]
        cached_tiles = sum(item["transferred"] for item in observed)
        assert 0 < cached_tiles < uncached_tiles
        hit, miss, resident, spilled, reported_budget, over = kernels.tile_store_stats(store)
        assert hit > 0 and miss > 0 and resident <= reported_budget == budget
        return {
            "spill_ms": spill_ms,
            "compose_oracle_frames": len(windows),
            "tile_frames": len(windows),
            "tile_frame_p95_ms": float(np.percentile(times, 95)),
            "tile_frame_samples_ms": times,
            "max_descriptors": max(item["descriptors"] for item in observed),
            "max_gpu_bytes": max(item["gpu_bytes"] for item in observed),
            "gpu_budget_bytes": observed[0]["gpu_budget"],
            "resident_samples_bytes": resident_samples,
            "timing_scope": "cached sequence before separate uncached validation; advisory only",
            "cached_transferred_tiles": cached_tiles,
            "uncached_transferred_tiles": uncached_tiles,
            "cached_reply_bytes": sum(item["bytes"] for item in observed),
            "uncached_reply_bytes": uncached_bytes,
            "tiles": {
                "hit": hit,
                "miss": miss,
                "resident_bytes": resident,
                "spilled_bytes": spilled,
                "budget_bytes": reported_budget,
                "over_budget": over,
            },
            "oracles_equal": True,
            "budget_ok": True,
        }
    finally:
        if handle:
            kernels.pyramid_free(handle)
        if store:
            kernels.tile_store_free(store)
        kernels.tile_budget_set(0)


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
        "schema_version": 1,
        "host": "python",
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
        "spill": spill_evidence(x, y),
        "environment": collect_environment_metadata(xy_backend=kernels.BACKEND),
        "provenance": {
            "native_sha256": hashlib.sha256(Path(_native._lib._name).read_bytes()).hexdigest(),
            "source_sha256": {
                path: hashlib.sha256((ROOT / path).read_bytes()).hexdigest()
                for path in (
                    "benchmarks/bench_tier3_pyramid.py",
                    "python/xyg/_native.py",
                    "crates/xyg-engine/src/tile_store.rs",
                    "crates/xyg-engine/src/tile_store/paint.rs",
                    "crates/xyg-engine/src/tiles.rs",
                    "crates/xyg-core/src/lib.rs",
                )
            },
        },
    }
    print(json.dumps(report, indent=2))
    return 0 if report["budget_ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
