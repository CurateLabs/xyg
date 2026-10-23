"""A producer cannot silently relax #11's independent bounded-report gate."""

from __future__ import annotations

import copy
import hashlib
import json

import pytest
from scripts.verify_tier3_pyramid_report import ROOT, SOURCES, validate


@pytest.fixture(params=["python", "node"])
def report(request):
    host = request.param
    # Immutable earlier measurements supply realistic structural values. New
    # provenance/sample fields below are test data, never published evidence.
    path = ROOT / "spec/performance/tile-spill-bounded-2026-10-23" / f"{host}.json"
    value = json.loads(path.read_text())
    value.update(schema_version=1, host=host)
    value["spill"].update(
        tile_frame_samples_ms=[1.0] * 32,
        max_descriptors=4,
        max_gpu_bytes=262_144,
        gpu_budget_bytes=524_288,
        resident_samples_bytes=[1_311_200] * 64,
    )
    value["environment"] = {"git": {"commit": "a" * 40}, "platform": {"system": "test"}}
    files = SOURCES | (
        {"benchmarks/bench_tier3_pyramid.py", "python/xyg/_native.py"}
        if host == "python"
        else {"benchmarks/bench_tier3_pyramid_node.mjs", "packages/xy-node/src/pyramid.js"}
    )
    value["provenance"] = {
        "native_sha256": "b" * 64,
        "source_sha256": {
            name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in files
        },
    }
    return value


def test_accepts_hard_structure_independently_of_advisory_latency(report):
    assert validate(report, check_local=True, expected_commit="a" * 40) == []
    report["spill"]["tile_frame_samples_ms"] = [10_000.0] * 32
    report["spill"]["tile_frame_p95_ms"] = 10_000.0
    assert validate(report) == []  # shared CI does not pretend to be a perf runner


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("n",), 1_000_000_000),
        (("raw_xy_bytes",), 0),
        (("resident_bytes",), 1),
        (("compose_n",), 1),
        (("binnings",), ["exact"]),
        (("spill", "compose_oracle_frames"), 0),
        (("spill", "oracles_equal"), False),
        (("spill", "tile_frame_samples_ms"), [1.0]),
        (("spill", "tile_frame_samples_ms"), [float("nan")] * 32),
        (("spill", "resident_samples_bytes"), [1] * 63),
        (("spill", "resident_samples_bytes"), [3 << 20] * 64),
        (("spill", "tiles", "over_budget"), True),
        (("spill", "cached_transferred_tiles"), 1000),
        (("spill", "cached_reply_bytes"), 1_000_000_000),
        (("spill", "max_descriptors"), 257),
        (("spill", "gpu_budget_bytes"), 1_000_000),
        (("spill", "max_gpu_bytes"), 1_000_000),
        (("spill", "tiles", "budget_bytes"), 4 << 20),
        (("spill", "tiles", "resident_bytes"), 3 << 20),
        (("spill", "tiles", "miss"), 0),
        (("provenance", "native_sha256"), "unknown"),
        (("provenance", "source_sha256"), {}),
    ],
)
def test_rejects_weakened_or_missing_evidence(report, path, value):
    damaged = copy.deepcopy(report)
    target = damaged
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    assert validate(damaged)


def test_rejects_wrong_commit_and_stale_source(report):
    assert validate(report, expected_commit="c" * 40)
    name = next(iter(report["provenance"]["source_sha256"]))
    report["provenance"]["source_sha256"][name] = "c" * 64
    assert validate(report, check_local=True)


def test_malformed_sections_fail_with_diagnostics(report):
    for name in ("spill", "environment", "provenance"):
        damaged = copy.deepcopy(report)
        damaged[name] = None
        assert validate(damaged)
