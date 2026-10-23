"""Resource/authority guard and cancellation, without large allocations."""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import pytest
from benchmarks import _density_spill as spill
from benchmarks import bench_density_e2e as bench

ROOT = Path(__file__).resolve().parents[1]


def test_controls_allow_only_up_to_one_million():
    spill.guard(1_000_000, False, {}, 3600, 12, 4)
    with pytest.raises(ValueError, match="1M"):
        spill.guard(1_000_001, False, {}, 3600, 12, 4)
    # Old count-only mode retains its canonical lane rejection.
    with pytest.raises(ValueError, match="canonical"):
        bench._authority_guard(16384, False, {})


@pytest.mark.parametrize(
    ("points", "authority", "timeout", "rss", "disk"),
    [
        (0, False, 600, 12, 4),
        (True, False, 600, 12, 4),
        (100_000_000, False, 600, 12, 4),
        (1_000_000, True, 600, 12, 4),
        (16384, False, 3601, 12, 4),
        (16384, False, 600, 13, 4),
        (16384, False, 600, 12, 5),
        (16384, False, float("nan"), 12, 4),
    ],
)
def test_guard_rejects_before_allocation(points, authority, timeout, rss, disk):
    with pytest.raises(ValueError):
        spill.guard(points, authority, {}, timeout, rss, disk)


def authority_env():
    return {
        "GITHUB_ACTIONS": "true",
        "GITHUB_REF": "refs/heads/main",
        "GITHUB_EVENT_NAME": "schedule",
        "GITHUB_RUN_ID": "1234",
        "GITHUB_RUN_ATTEMPT": "1",
        "GITHUB_SHA": "a" * 40,
        "XYG_DENSITY_100M_AUTHORITY": "1",
    }


@pytest.mark.parametrize("key", spill.AUTH_ENV)
def test_authority_requires_all_ambient_capabilities(key):
    env = authority_env()
    spill.guard(100_000_000, True, env, 3600, 12, 4)  # guard only; never allocates
    env.pop(key)
    with pytest.raises(ValueError):
        spill.guard(100_000_000, True, env, 3600, 12, 4)


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("GITHUB_REF", "refs/pull/11/merge"),
        ("GITHUB_EVENT_NAME", "pull_request"),
        ("GITHUB_ACTIONS", "false"),
        ("GITHUB_RUN_ID", "not-a-run"),
    ],
)
def test_authority_refuses_forged_or_pr_execution(key, value):
    env = authority_env()
    env[key] = value
    with pytest.raises(ValueError):
        spill.guard(100_000_000, True, env, 3600, 12, 4)


def test_worker_entry_point_does_not_bypass_guard(tmp_path, monkeypatch):
    monkeypatch.delenv("XYG_DENSITY_100M_AUTHORITY", raising=False)
    config = {
        "points": 100_000_000,
        "authority": True,
        "timeout": 3600,
        "max_rss_bytes": 12 * 1024**3,
        "max_disk_bytes": 4 * 1024**3,
    }
    with pytest.raises(ValueError):
        spill.worker(config)
    assert list(tmp_path.iterdir()) == []


def test_generation_is_chunk_invariant_and_f64_mapped(tmp_path):
    outputs = []
    for name, chunk in (("small", 17), ("large", 1024)):
        path = tmp_path / name
        path.mkdir()
        x, y, color, source = spill.generate(path, 4096, chunk)
        assert all(
            isinstance(value, np.memmap) and value.dtype == np.float64 for value in (x, y, color)
        )
        assert np.unique(color).tolist() == [0.0, 1.0]
        assert all(
            spill.file_hash(path / (key + ".f64")) == record["sha256"]
            for key, record in source["columns"].items()
        )
        outputs.append(source["columns"])
        for value in (x, y, color):
            value._mmap.close()
    assert outputs[0] == outputs[1]


def test_supervisor_timeout_cleans_colored_worker(tmp_path):
    output = tmp_path / "timeout.json"
    result = subprocess.run(
        [
            sys.executable,
            "benchmarks/bench_density_e2e.py",
            "--workload",
            "colored-spill",
            "--points",
            "16384",
            "--timeout",
            ".001",
            "--output",
            str(output),
            "--temp-root",
            str(tmp_path),
        ],
        cwd=ROOT,
        capture_output=True,
        timeout=20,
    )
    report = json.loads(output.read_text())
    assert result.returncode == 1
    assert report["failure"] == "timeout" and report["report_kind"] == "density-colored-spill"
    assert (
        report["cleanup"]["orphan_pids_after_reap"] == []
        and report["cleanup"]["temp_tree_removed"] is True
    )
    assert not list(tmp_path.glob("xyg-density-e2e-*"))


def test_supervisor_cancellation_cleans_colored_worker(tmp_path):
    output = tmp_path / "cancelled.json"
    process = subprocess.Popen(
        [
            sys.executable,
            "benchmarks/bench_density_e2e.py",
            "--workload",
            "colored-spill",
            "--points",
            "1000000",
            "--timeout",
            "120",
            "--output",
            str(output),
            "--temp-root",
            str(tmp_path),
        ],
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    try:
        deadline = time.monotonic() + 10
        while not list(tmp_path.glob("xyg-density-e2e-*/config.json")):
            assert process.poll() is None and time.monotonic() < deadline
            time.sleep(0.01)
        # Wait until the supervisor's cancellation handler is installed;
        # observe a child in its owned process group before sending SIGTERM.
        while time.monotonic() < deadline:
            children = Path(f"/proc/{process.pid}/task/{process.pid}/children").read_text().split()
            if children and bench._process_group_rss(int(children[0]))[1]:
                break
            time.sleep(0.01)
        else:
            pytest.fail("supervisor did not start its worker process group")
        os.kill(process.pid, signal.SIGTERM)
        process.communicate(timeout=20)
        report = json.loads(output.read_text())
        assert process.returncode == 1 and report["failure"] == "cancelled"
        assert (
            report["cleanup"]["orphan_pids_after_reap"] == []
            and report["cleanup"]["temp_tree_removed"] is True
        )
    finally:
        if process.poll() is None:
            process.kill()
            process.communicate(timeout=10)


def test_optimized_python_cannot_disable_evidence_assertions(tmp_path):
    output = tmp_path / "optimized.json"
    result = subprocess.run(
        [
            sys.executable,
            "-O",
            "benchmarks/bench_density_e2e.py",
            "--workload",
            "colored-spill",
            "--points",
            "16384",
            "--output",
            str(output),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert result.returncode != 0 and "assertions enabled" in result.stderr
    assert not output.exists()
